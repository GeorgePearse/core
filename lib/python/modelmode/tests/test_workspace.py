"""Real subprocess training and durable artifacts, without cloud dependencies."""

from pathlib import Path

import joblib
import pytest

from modelmode import Workspace
from modelmode.evaluation import load_estimator


def test_complete_lifecycle_and_sealing(tmp_path: Path, rows: list[dict]) -> None:
    workspace = Workspace(tmp_path)
    dataset = workspace.create_dataset("test", rows)
    run = workspace.learn(
        dataset["dataset_id"], candidates=["tfidf_word"], budget_seconds=45
    )
    done = workspace.wait(run["run_id"], timeout=50)
    assert done["status"] == "succeeded", done
    assert done["total_seconds"] > 0
    assert done["selected"] == "tfidf_word"
    path = tmp_path / "runs" / run["run_id"]
    model = joblib.load(path / "tfidf_word.joblib")
    assert "validation" not in model.named_steps["vectorizer"].vocabulary_
    with pytest.raises(ValueError, match="final evaluation"):
        workspace.publish(run["run_id"], "route")
    result = workspace.evaluate(run["run_id"])
    assert result == workspace.evaluate(run["run_id"])
    assert result["models"]["tfidf_word"]["accuracy"] == 1
    with pytest.raises(ValueError, match="sealed"):
        workspace.learn(dataset["dataset_id"])
    assert workspace.publish(run["run_id"], "route")["version"] == 1
    assert workspace.publish(run["run_id"], "route", abstain_below=1)["version"] == 2
    reopened = Workspace(tmp_path)
    assert (
        reopened.predict("route", ["delivery delivery"], version=1)["predictions"][0][
            "label"
        ]
        == "delivery"
    )
    assert reopened.predict("route", ["delivery delivery"])["predictions"][0][
        "abstained"
    ]
    assert reopened.list_capabilities()[0]["name"] == "route"
    load_estimator.cache_clear()
    with (path / "tfidf_word.joblib").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        reopened.predict("route", ["payment"])


def test_tiny_deadline_terminates_worker(tmp_path: Path, rows: list[dict]) -> None:
    workspace = Workspace(tmp_path)
    dataset = workspace.create_dataset("timeout", rows)
    run = workspace.learn(dataset["dataset_id"], budget_seconds=0.01)
    assert workspace.wait(run["run_id"], timeout=20)["status"] == "timed_out"
    with pytest.raises(ValueError, match="successful"):
        workspace.evaluate(run["run_id"])


def test_cancel_background_worker(tmp_path: Path, rows: list[dict]) -> None:
    workspace = Workspace(tmp_path)
    dataset = workspace.create_dataset("cancel", rows)
    run = workspace.learn(dataset["dataset_id"], budget_seconds=45)
    workspace.cancel(run["run_id"])
    assert workspace.wait(run["run_id"], timeout=20)["status"] == "cancelled"


def test_numeric_classifier(tmp_path: Path, rows: list[dict]) -> None:
    for i, row in enumerate(rows):
        row.pop("text")
        row["features"] = [
            (-1 if row["label"] == "delivery" else 1) * (i + 1),
            i * 0.01,
        ]
    workspace = Workspace(tmp_path)
    dataset = workspace.create_dataset("numeric", rows)
    run = workspace.learn(
        dataset["dataset_id"], candidates=["linear"], budget_seconds=45
    )
    assert workspace.wait(run["run_id"], timeout=50)["status"] == "succeeded"
    workspace.evaluate(run["run_id"])
    workspace.publish(run["run_id"], "numeric")
    assert (
        workspace.predict("numeric", [[-20, 0.1]])["predictions"][0]["label"]
        == "delivery"
    )


def test_invalid_training_and_objective(tmp_path: Path, rows: list[dict]) -> None:
    workspace = Workspace(tmp_path)
    dataset = workspace.create_dataset("invalid", rows)
    with pytest.raises(ValueError):
        workspace.learn(dataset["dataset_id"], training={"epochs": 100000})
    with pytest.raises(ValueError, match="positive quality floor"):
        workspace.learn(dataset["dataset_id"], objective="fastest_at_quality")


def test_publication_rejects_baseline_and_quality_regressions(tmp_path: Path) -> None:
    from modelmode.storage import write

    workspace = Workspace(tmp_path)
    state = {
        "run_id": "gates",
        "status": "succeeded",
        "selected": "tfidf_word",
        "quality_floor_met": True,
        "config": {"metric": "macro_f1", "min_score": 0.9},
    }
    path = tmp_path / "runs/gates"
    write(path / "state.json", state)
    write(
        path / "test.json",
        {
            "summary": {
                "models": {"tfidf_word": {"macro_f1": 0.8}, "dummy": {"macro_f1": 0.5}}
            }
        },
    )
    with pytest.raises(ValueError, match="quality floor"):
        workspace.publish("gates", "bad")
    state["config"]["min_score"] = 0
    write(path / "state.json", state)
    write(
        path / "test.json",
        {
            "summary": {
                "models": {"tfidf_word": {"macro_f1": 0.4}, "dummy": {"macro_f1": 0.5}}
            }
        },
    )
    with pytest.raises(ValueError, match="dummy baseline"):
        workspace.publish("gates", "bad")


def test_dead_supervisor_becomes_a_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modelmode.storage import write

    workspace = Workspace(tmp_path)
    write(
        tmp_path / "runs/dead/state.json",
        {"status": "queued", "supervisor_pid": 99999999},
    )

    def no_process(pid: int, signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("modelmode.workspace.os.kill", no_process)
    assert workspace.get_run("dead")["status"] == "failed"
