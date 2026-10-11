"""Durable Modal invocation, bounded polling and cancellation of the remote call."""

import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from modelmode.storage import read, write
from modelmode.workspace import Workspace

logger = logging.getLogger(__name__)


def training_payload(root: Path, run_id: str) -> dict:
    """Physically remove test rows before sending any data to the GPU worker."""
    workspace = Workspace(root)
    state = workspace.get_run(run_id)
    data = dict(workspace._dataset(state["dataset_id"])["data"])
    data["rows"] = [r for r in data["rows"] if r["split"] != "test"]
    return {"state": state, "data": data}


def install_result(root: Path, run_id: str, result: dict) -> dict:
    """Reject mismatched receipts or artifacts before exposing a successful run."""
    path = Workspace(root)._run_path(run_id)
    local = read(path / "state.json")
    remote = result["state"]
    for key in ("run_id", "dataset_id", "config"):
        if remote[key] != local[key]:
            raise ValueError(f"Remote {key} differs from the submitted job")
    if (
        local.get("implementation_sha256")
        and remote.get("environment", {}).get("implementation_sha256")
        != local["implementation_sha256"]
    ):
        raise ValueError("Remote implementation differs from submitted job")
    if remote["status"] != "fitted":
        raise ValueError("Remote job did not finish fitting")
    expected = {}
    for candidate in remote["candidates"]:
        if candidate["name"] not in local["config"]["candidates"]:
            raise ValueError("Unexpected remote candidate")
        if candidate["status"] == "succeeded":
            expected[f"{candidate['name']}.joblib"] = candidate["sha256"]
            expected[f"{candidate['name']}.validation.json"] = None
    if set(expected) != set(result["files"]):
        raise ValueError("Remote artifact set differs from receipt")
    for name, checksum in expected.items():
        content = result["files"][name]
        if checksum and hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError("Remote artifact hash mismatch")
    for name, content in result["files"].items():
        temporary = path / f".{name}.tmp"
        temporary.write_bytes(content)
        temporary.replace(path / name)
    return {**remote, "modal": local["modal"]}


def capacity_snapshot() -> dict:
    """Check current task occupancy conservatively before using the shared GPU pool.

    A task is a container, not a GPU: multi-GPU jobs require an operator's GPU
    inventory as well. This application's own pool is capped at one single GPU.
    """
    result = subprocess.run(
        [sys.executable, "-m", "modal", "app", "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    active = [r for r in json.loads(result.stdout) if int(r["Tasks"])]
    tasks = sum(int(r["Tasks"]) for r in active)
    if tasks >= 40:
        raise RuntimeError(
            "At least 40 active Modal tasks; defer this non-production job"
        )
    return {
        "checked_at": time.time(),
        "active_tasks": tasks,
        "apps": active,
        "note": "Task count is not a GPU count for multi-GPU containers; pool cap is one T4",
    }


def run_modal(root: Path, run_id: str) -> None:
    """Own a remote call until artifacts arrive or confirmed cancellation completes."""
    import modal

    from modelmode.modal_app import APP_NAME

    path = Workspace(root)._run_path(run_id)
    state = read(path / "state.json")
    deadline = time.monotonic() + max(
        0,
        state["config"]["budget_seconds"]
        - (time.time() - state.get("created_at", state["started_at"])),
    )
    call = None
    try:
        capacity = capacity_snapshot()
        function = modal.Function.from_name(APP_NAME, "train")
        call = function.spawn(training_payload(root, run_id))
        state["modal"] = {
            "app": APP_NAME,
            "call_id": call.object_id,
            "gpu": "T4",
            "max_containers": 1,
            "capacity": capacity,
        }
        write(path / "state.json", state)
        while True:
            cancelled = (path / "cancel.json").exists()
            if cancelled or time.monotonic() >= deadline:
                call.cancel(terminate_containers=True)
                state["modal"]["cancel_confirmed"] = True
                state.update(
                    status="cancelled" if cancelled else "timed_out",
                    error="Remote job cancelled"
                    if cancelled
                    else "Whole-job wall-clock budget exhausted",
                )
                break
            try:
                result = call.get(
                    timeout=min(1.0, max(0.01, deadline - time.monotonic()))
                )
            except TimeoutError:
                continue
            state = install_result(root, run_id, result)
            state["status"] = "succeeded"
            break
    except Exception as error:
        logger.exception("Modal training failed")
        state.update(status="failed", error=str(error))
        if call is not None:
            try:
                call.cancel(terminate_containers=True)
                state.setdefault("modal", {})["cancel_confirmed"] = True
            except Exception as cancel_error:
                state.setdefault("modal", {})["cancel_error"] = str(cancel_error)
    finally:
        state.update(
            finished_at=time.time(),
            total_seconds=time.time() - state.get("created_at", state["started_at"]),
        )
        write(path / "state.json", state)
