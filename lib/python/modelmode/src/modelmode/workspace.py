"""Persistent learning sessions usable from Python, CLI and MCP."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from threadpoolctl import threadpool_limits

from modelmode.backends import NUMERIC_CANDIDATES, TEXT_CANDIDATES, catalog
from modelmode.data import fingerprint, prepare
from modelmode.evaluation import load_estimator, score, summary
from modelmode.storage import identifier, implementation_hash, locked, read, write

TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}


class Workspace:
    """A local trusted artifact store; never accepts externally supplied pickles."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_path(self, run_id: str) -> Path:
        return self.root / "runs" / identifier(run_id)

    def _dataset(self, dataset_id: str) -> dict:
        data = read(self.root / "datasets" / f"{identifier(dataset_id)}.json")
        if fingerprint(data["data"]) != dataset_id:
            raise ValueError("Dataset content hash mismatch")
        return data

    def create_dataset(self, name: str, rows: list[dict], seed: int = 42) -> dict:
        """Register labelled text or feature vectors; freeze grouped partitions."""
        data = prepare(rows, seed)
        dataset_id = fingerprint(data)
        with locked(self.root):
            path = self.root / "datasets" / f"{dataset_id}.json"
            if not path.exists():
                write(path, {"name": name, "data": data})
        return self.describe_dataset(dataset_id)

    def describe_dataset(self, dataset_id: str) -> dict:
        """Describe partitions without exposing test examples to the supervisor."""
        saved = self._dataset(dataset_id)
        return {
            "dataset_id": dataset_id,
            "name": saved["name"],
            **{k: v for k, v in saved["data"].items() if k != "rows"},
            "sealed": (self.root / "datasets" / f"{dataset_id}.sealed.json").exists(),
        }

    def list_datasets(self) -> list[dict]:
        """Discover reusable local datasets after restarting the host."""
        return [
            self.describe_dataset(p.stem)
            for p in sorted((self.root / "datasets").glob("*.json"))
            if not p.name.endswith(".sealed.json")
        ]

    def learn(
        self,
        dataset_id: str,
        candidates: list[str] | None = None,
        metric: str = "macro_f1",
        min_score: float = 0.0,
        objective: str = "quality",
        budget_seconds: float = 120,
        seed: int = 42,
        execution: str = "local",
        training: dict | None = None,
    ) -> dict:
        """Start one bounded background search; use get_run to inspect completion.

        The frontier agent can launch another search after reviewing validation
        errors, until final test access seals the dataset.
        """
        data = self._dataset(dataset_id)["data"]
        allowed = TEXT_CANDIDATES if data["mode"] == "text" else NUMERIC_CANDIDATES
        candidates = (
            candidates
            if candidates is not None
            else (
                ["tfidf_word", "bert_tiny", "bert_mini"]
                if execution == "modal" and data["mode"] == "text"
                else allowed[:2]
            )
        )
        if (
            not candidates
            or len(candidates) > 8
            or len(set(candidates)) != len(candidates)
            or any(c not in allowed for c in candidates)
        ):
            raise ValueError(f"Choose 1–8 unique candidates from {allowed}")
        if metric not in {"macro_f1", "balanced_accuracy", "accuracy"}:
            raise ValueError("Unsupported metric")
        if objective not in {"quality", "fastest_at_quality"}:
            raise ValueError("Unsupported objective")
        if not 0 <= min_score <= 1 or not 0 < budget_seconds <= 3600:
            raise ValueError("Score must be in [0,1]; budget must be in (0,3600]")
        if objective == "fastest_at_quality" and min_score == 0:
            raise ValueError(
                "A positive quality floor is required when optimizing speed"
            )
        from modelmode.finetune import TrainingConfig

        training = TrainingConfig.model_validate(training or {}).model_dump()
        if execution not in {"local", "modal"}:
            raise ValueError("Execution must be local or modal")
        for prior in self.list_runs():
            self.get_run(prior["run_id"])
        with locked(self.root):
            if (self.root / "datasets" / f"{dataset_id}.sealed.json").exists():
                raise ValueError(
                    "Test has been opened: this dataset is sealed against further training"
                )
            if any(r["status"] not in TERMINAL for r in self.list_runs()):
                raise ValueError(
                    "One active search per workspace; wait or cancel it first"
                )
            run_id = uuid.uuid4().hex
            state = {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "status": "queued",
                "created_at": time.time(),
                "implementation_sha256": implementation_hash(),
                "candidates": [],
                "config": {
                    "candidates": ["dummy", *candidates],
                    "metric": metric,
                    "min_score": min_score,
                    "objective": objective,
                    "budget_seconds": budget_seconds,
                    "seed": seed,
                    "execution": execution,
                    "training": training,
                },
            }
            path = self._run_path(run_id)
            write(path / "state.json", state)
            try:
                with (path / "worker.log").open("ab") as log:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "modelmode.worker",
                            "supervise",
                            str(self.root),
                            run_id,
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                        env={
                            **os.environ,
                            "OMP_NUM_THREADS": "2",
                            "OPENBLAS_NUM_THREADS": "2",
                            "MKL_NUM_THREADS": "2",
                            "TOKENIZERS_PARALLELISM": "false",
                        },
                    )
                state["supervisor_pid"] = process.pid
                write(path / "state.json", state)
            except Exception:
                state.update(status="failed", error="Could not start worker")
                write(path / "state.json", state)
                raise
        return state

    def get_run(self, run_id: str) -> dict:
        """Return durable progress, selected recipe, timings and validation metrics."""
        path = self._run_path(run_id) / "state.json"
        state = read(path)
        if state["status"] not in TERMINAL and state.get("supervisor_pid"):
            try:
                os.kill(state["supervisor_pid"], 0)
            except ProcessLookupError:
                with locked(self.root):
                    state = read(path)
                    if state["status"] not in TERMINAL:
                        state.update(
                            status="failed",
                            error="Supervisor exited unexpectedly; inspect worker.log. A saved Modal call may need cancellation.",
                            finished_at=time.time(),
                        )
                        write(path, state)
        return state

    def list_runs(self) -> list[dict]:
        """Return the search ledger, newest first."""
        return sorted(
            [read(p) for p in (self.root / "runs").glob("*/state.json")],
            key=lambda r: r["created_at"],
            reverse=True,
        )

    def wait(self, run_id: str, timeout: float = 3605) -> dict:
        """Convenience for scripts; MCP clients should poll get_run instead."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.get_run(run_id)
            if state["status"] in TERMINAL:
                return state
            time.sleep(0.1)
        raise TimeoutError("Search is still running")

    def cancel(self, run_id: str) -> dict:
        """Ask the supervisor to terminate its own child process."""
        state = self.get_run(run_id)
        if state["status"] == "failed" and state.get("modal", {}).get("call_id"):
            import modal

            modal.FunctionCall.from_id(state["modal"]["call_id"]).cancel(
                terminate_containers=True
            )
            state["modal"]["cancel_confirmed"] = True
            write(self._run_path(run_id) / "state.json", state)
        if state["status"] not in TERMINAL:
            write(self._run_path(run_id) / "cancel.json", {"requested_at": time.time()})
        return state

    def review(self, run_id: str, limit: int = 20) -> list[dict]:
        """Show selected-model validation failures for targeted supervisor feedback."""
        if not 1 <= limit <= 100:
            raise ValueError("Review limit must be in [1,100]")
        state = self.get_run(run_id)
        if state["status"] != "succeeded":
            raise ValueError("Wait for a successful search")
        result = read(self._run_path(run_id) / f"{state['selected']}.validation.json")
        data = self._dataset(state["dataset_id"])["data"]
        rows = {r["id"]: r for r in data["rows"] if r["split"] == "validation"}
        errors = sorted(
            [p for p in result["predictions"] if p["label"] != p["prediction"]],
            key=lambda p: -p["score"],
        )
        return [{**p, "input": rows[p["id"]][data["mode"]]} for p in errors[:limit]]

    def evaluate(self, run_id: str) -> dict:
        """Open test once for the chosen candidate and dummy baseline, then seal.

        Test results are idempotent. A sealed dataset cannot launch additional
        searches; use a genuinely new evaluation cohort for subsequent work.
        """
        path = self._run_path(run_id)
        with locked(self.root):
            state = read(self._run_path(run_id) / "state.json")
            if state["status"] != "succeeded":
                raise ValueError("Only successful searches can be evaluated")
            if any(r["status"] not in TERMINAL for r in self.list_runs()):
                raise ValueError("Wait for all searches before opening test")
            seal = self.root / "datasets" / f"{state['dataset_id']}.sealed.json"
            if seal.exists() and read(seal)["run_id"] != run_id:
                raise ValueError(
                    "This test cohort was already opened for a different search"
                )
            if (path / "test.json").exists():
                return read(path / "test.json")["summary"]
            write(
                seal,
                {
                    "run_id": run_id,
                    "selected": state["selected"],
                    "opened_at": time.time(),
                },
            )
            data = self._dataset(state["dataset_id"])["data"]
            rows = [r for r in data["rows"] if r["split"] == "test"]
            outputs = {}
            with threadpool_limits(limits=2):
                for name in dict.fromkeys([state["selected"], "dummy"]):
                    item = next(c for c in state["candidates"] if c["name"] == name)
                    estimator = load_estimator(
                        str(path / f"{name}.joblib"), item["sha256"]
                    )
                    outputs[name] = score(
                        estimator, rows, data["mode"], data["classes"]
                    )
            result = {
                "run_id": run_id,
                "selected": state["selected"],
                "models": {k: summary(v) for k, v in outputs.items()},
                "dataset_sealed": True,
            }
            write(path / "test.json", {"summary": result, "full": outputs})
            return result

    def publish(self, run_id: str, name: str, abstain_below: float = 0.0) -> dict:
        """Create an immutable capability version after its quality checks pass."""
        identifier(name)
        if not 0 <= abstain_below <= 1:
            raise ValueError("Abstention threshold must be in [0,1]")
        with locked(self.root):
            state = read(self._run_path(run_id) / "state.json")
            if (
                state["status"] != "succeeded"
                or not (self._run_path(run_id) / "test.json").exists()
            ):
                raise ValueError("Complete final evaluation before publishing")
            metric = state["config"]["metric"]
            test = read(self._run_path(run_id) / "test.json")["summary"]["models"]
            selected = state["selected"]
            if selected == "dummy" or test[selected][metric] <= test["dummy"][metric]:
                raise ValueError(
                    "Selected model did not beat the dummy baseline on test"
                )
            if (
                not state["quality_floor_met"]
                or test[selected][metric] < state["config"]["min_score"]
            ):
                raise ValueError(
                    "Selected model did not meet the requested quality floor"
                )
            pointer = self.root / "capabilities" / f"{name}.json"
            previous = read(pointer) if pointer.exists() else {"versions": []}
            version = {
                "version": len(previous["versions"]) + 1,
                "run_id": run_id,
                "candidate": selected,
                "abstain_below": abstain_below,
                "published_at": time.time(),
            }
            result = {"name": name, "versions": [*previous["versions"], version]}
            write(pointer, result)
            return {"name": name, **version, "test": test[selected]}

    def list_capabilities(self) -> list[dict]:
        """Discover published model tools and all their immutable versions."""
        return [read(p) for p in sorted((self.root / "capabilities").glob("*.json"))]

    def predict(
        self, name: str, examples: list[Any], version: int | None = None
    ) -> dict:
        """Invoke a published model; uncertain outputs can be escalated by the host."""
        if not 1 <= len(examples) <= 10_000:
            raise ValueError("Predict 1–10,000 examples at a time")
        capability = read(self.root / "capabilities" / f"{identifier(name)}.json")
        versions = capability["versions"]
        if version is None:
            chosen = versions[-1]
        else:
            chosen = next((v for v in versions if v["version"] == version), None)
            if chosen is None:
                raise ValueError("Unknown capability version")
        state = self.get_run(chosen["run_id"])
        data = self._dataset(state["dataset_id"])["data"]
        if data["mode"] == "text":
            if any(
                not isinstance(x, str) or not x.strip() or len(x) > 100_000
                for x in examples
            ):
                raise ValueError(
                    "This capability expects nonempty strings up to 100,000 characters"
                )
        else:
            import numpy as np

            array = np.asarray(examples, dtype=float)
            if (
                array.shape != (len(examples), data["feature_width"])
                or not np.isfinite(array).all()
            ):
                raise ValueError("Feature shape or finite-value check failed")
        candidate = next(
            c for c in state["candidates"] if c["name"] == chosen["candidate"]
        )
        model = load_estimator(
            str(self._run_path(chosen["run_id"]) / f"{chosen['candidate']}.joblib"),
            candidate["sha256"],
        )
        with threadpool_limits(limits=2):
            probabilities = model.predict_proba(examples)
        return {
            "capability": name,
            "version": chosen["version"],
            "score_note": "Model probability, not independently calibrated correctness",
            "predictions": [
                {
                    "label": str(model.classes_[p.argmax()]),
                    "score": float(p.max()),
                    "abstained": bool(p.max() < chosen["abstain_below"]),
                }
                for p in probabilities
            ],
        }

    @staticmethod
    def catalog() -> dict:
        """Expose available local model families."""
        return catalog()
