"""The remote boundary omits holdout data and verifies received artifacts."""

import hashlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from modelmode import Workspace
from modelmode.modal_client import install_result, run_modal, training_payload
from modelmode.storage import read, write


def prepared(tmp_path: Path, rows: list[dict]) -> dict:
    workspace = Workspace(tmp_path)
    dataset = workspace.create_dataset("remote", rows)
    state = {
        "run_id": "remote",
        "dataset_id": dataset["dataset_id"],
        "status": "running",
        "started_at": time.time(),
        "config": {"budget_seconds": 20, "candidates": ["dummy", "tfidf_word"]},
        "modal": {"call_id": "fc-test"},
    }
    write(tmp_path / "runs/remote/state.json", state)
    return state


def test_remote_payload_never_contains_test(tmp_path: Path, rows: list[dict]) -> None:
    prepared(tmp_path, rows)
    data = training_payload(tmp_path, "remote")["data"]
    assert {r["split"] for r in data["rows"]} == {"train", "validation"}
    assert len(data["rows"]) == 40


def test_remote_hash_and_identity(tmp_path: Path, rows: list[dict]) -> None:
    state = prepared(tmp_path, rows)
    remote = {
        **state,
        "status": "fitted",
        "candidates": [
            {
                "name": "dummy",
                "status": "succeeded",
                "sha256": hashlib.sha256(b"model").hexdigest(),
            }
        ],
    }
    files = {"dummy.joblib": b"model", "dummy.validation.json": b"{}"}
    assert (
        install_result(tmp_path, "remote", {"state": remote, "files": files})["modal"][
            "call_id"
        ]
        == "fc-test"
    )
    files["dummy.joblib"] = b"evil"
    with pytest.raises(ValueError, match="hash mismatch"):
        install_result(tmp_path, "remote", {"state": remote, "files": files})
    remote["dataset_id"] = "different"
    with pytest.raises(ValueError, match="dataset_id differs"):
        install_result(tmp_path, "remote", {"state": remote, "files": files})


def test_cancel_propagates_to_remote(
    tmp_path: Path, rows: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared(tmp_path, rows)
    calls = []
    call = SimpleNamespace(
        object_id="fc-test", cancel=lambda **kwargs: calls.append(kwargs)
    )
    fake = SimpleNamespace(
        Function=SimpleNamespace(
            from_name=lambda *args: SimpleNamespace(spawn=lambda payload: call)
        )
    )
    monkeypatch.setitem(sys.modules, "modal", fake)
    monkeypatch.setitem(
        sys.modules, "modelmode.modal_app", SimpleNamespace(APP_NAME="modelmode")
    )
    monkeypatch.setattr(
        "modelmode.modal_client.capacity_snapshot", lambda: {"active_tasks": 0}
    )
    write(tmp_path / "runs/remote/cancel.json", {})
    run_modal(tmp_path, "remote")
    assert calls == [{"terminate_containers": True}]
    result = read(tmp_path / "runs/remote/state.json")
    assert result["status"] == "cancelled"
    assert result["modal"]["cancel_confirmed"]


def test_remote_fit_ignores_local_supervisor_pid(
    tmp_path: Path, rows: list[dict]
) -> None:
    from modelmode.data import prepare
    from modelmode.worker import fit

    state = prepared(tmp_path, rows)
    state.update(supervisor_pid=99999999, candidates=[])
    state["config"].update(seed=42, metric="macro_f1", min_score=0, objective="quality")
    write(tmp_path / "runs/remote/state.json", state)
    data = prepare(rows)
    data["rows"] = [r for r in data["rows"] if r["split"] != "test"]
    fit(tmp_path, "remote", data_override=data)
    result = read(tmp_path / "runs/remote/state.json")
    assert result["status"] == "fitted"
    assert "error" not in result
