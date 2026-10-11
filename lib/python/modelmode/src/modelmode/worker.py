"""Isolated bounded jobs survive an MCP client disconnect and expose progress."""

import importlib.metadata
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

import joblib
from threadpoolctl import threadpool_limits

from modelmode.backends import build
from modelmode.data import inputs
from modelmode.evaluation import score, summary, warm_timing
from modelmode.storage import implementation_hash, locked, read, sha256, write
from modelmode.workspace import Workspace

logger = logging.getLogger(__name__)


def fit(root: Path, run_id: str, data_override: dict | None = None) -> None:
    """Fit candidates against train only, and select on fixed validation data."""
    workspace = Workspace(root)
    path = workspace._run_path(run_id)
    state = read(path / "state.json")
    data = (
        data_override
        if data_override is not None
        else workspace._dataset(state["dataset_id"])["data"]
    )
    config = state["config"]
    train = [r for r in data["rows"] if r["split"] == "train"]
    validation = [r for r in data["rows"] if r["split"] == "validation"]
    state["environment"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("scikit-learn", "numpy", "scipy", "joblib")
        },
        "native_threads": 2,
        "implementation_sha256": implementation_hash(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        )
        if Path("/proc/cpuinfo").exists()
        else platform.processor(),
    }
    with threadpool_limits(limits=2):
        for name in config["candidates"]:
            state["current_candidate"] = name
            write(path / "state.json", state)
            start = time.perf_counter()
            try:
                model = build(
                    name, data["mode"], config["seed"], config.get("training")
                )
                model.fit(inputs(train, data["mode"]), [r["label"] for r in train])
                fit_seconds = time.perf_counter() - start
                result = score(model, validation, data["mode"], data["classes"])
                timing = warm_timing(model, validation, data["mode"])
                artifact = path / f"{name}.joblib"
                joblib.dump(model, artifact, compress=3)
                restored = joblib.load(artifact)
                import numpy as np

                probe = inputs(validation[:16], data["mode"])
                np.testing.assert_allclose(
                    model.predict_proba(probe),
                    restored.predict_proba(probe),
                    rtol=1e-6,
                    atol=1e-7,
                )
                item = {
                    "name": name,
                    "status": "succeeded",
                    "validation": summary(result),
                    "fit_seconds": fit_seconds,
                    "candidate_seconds": time.perf_counter() - start,
                    "artifact_bytes": artifact.stat().st_size,
                    "sha256": sha256(artifact),
                    "reload_verified": True,
                    **timing,
                }
                if hasattr(model, "training_receipt_"):
                    item["training"] = model.training_receipt_
                if hasattr(model, "named_steps") and "encoder" in model.named_steps:
                    encoder = model.named_steps["encoder"]
                    item["encoder"] = {
                        "model_id": encoder.model_id,
                        "revision": encoder.revision_,
                        "artifact_note": "External encoder cache is additional to classifier artifact bytes",
                    }
                write(path / f"{name}.validation.json", result)
                state["candidates"].append(item)
                del model, restored
            except Exception as error:
                logger.exception("Candidate %s failed", name)
                state["candidates"].append(
                    {
                        "name": name,
                        "status": "failed",
                        "error": str(error),
                        "candidate_seconds": time.perf_counter() - start,
                    }
                )
            write(path / "state.json", state)
    successful = [c for c in state["candidates"] if c["status"] == "succeeded"]
    if not any(c["name"] == "dummy" for c in successful) or len(successful) < 2:
        raise RuntimeError("Need a successful baseline and at least one candidate")
    eligible = [
        c
        for c in successful
        if c["validation"][config["metric"]] >= config["min_score"]
    ]
    state["quality_floor_met"] = bool(eligible)
    pool = eligible or successful
    if config["objective"] == "fastest_at_quality" and eligible:
        chosen = min(
            pool,
            key=lambda c: (c["warm_ms_per_item"], -c["validation"][config["metric"]]),
        )
    else:
        chosen = max(
            pool,
            key=lambda c: (c["validation"][config["metric"]], -c["warm_ms_per_item"]),
        )
    state.update(selected=chosen["name"], status="fitted")
    state.pop("current_candidate", None)
    write(path / "state.json", state)


def supervise(root: Path, run_id: str) -> None:
    """Own the child process, enforcing the whole-job deadline and cancellation."""
    path = Workspace(root)._run_path(run_id)
    with locked(root):
        state = read(path / "state.json")
        state.update(
            status="running", started_at=time.time(), supervisor_pid=os.getpid()
        )
        write(path / "state.json", state)
    if state["config"].get("execution") == "modal":
        from modelmode.modal_client import run_modal

        run_modal(root, run_id)
        return
    deadline = time.monotonic() + max(
        0, state["config"]["budget_seconds"] - (time.time() - state["created_at"])
    )
    child = subprocess.Popen(
        [sys.executable, "-m", "modelmode.worker", "fit", str(root), run_id],
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    status = None
    while child.poll() is None:
        if (path / "cancel.json").exists():
            status = "cancelled"
        elif time.monotonic() >= deadline:
            status = "timed_out"
        if status:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            except ProcessLookupError:
                child.wait()
            break
        time.sleep(0.05)
    with locked(root):
        final = read(path / "state.json")
        if status:
            final.update(
                status=status,
                error="Job cancelled"
                if status == "cancelled"
                else "Whole-job wall-clock budget exhausted",
            )
        elif child.returncode != 0 or final["status"] != "fitted":
            final.update(
                status="failed",
                error="Worker failed; inspect worker.log and candidate errors",
            )
        else:
            final["status"] = "succeeded"
        final.update(
            finished_at=time.time(), total_seconds=time.time() - state["created_at"]
        )
        write(path / "state.json", final)


def main() -> None:
    """Internal module entrypoint; users launch jobs through Workspace.learn."""
    logging.basicConfig(level=logging.INFO)
    action, root, run_id = sys.argv[1:]
    if action == "supervise":
        supervise(Path(root), run_id)
    elif action == "fit":
        fit(Path(root), run_id)
    else:
        raise ValueError("Unknown worker action")


if __name__ == "__main__":
    main()
