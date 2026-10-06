"""Structured run/event recording for agentic-vision viewer replay and live streaming."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeAlias

import cv2
import numpy as np

JsonValue: TypeAlias = str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _sanitize_name(value: str) -> str:
    """Return a filesystem-safe slug."""
    collapsed = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")
    return collapsed or "artifact"


def _atomic_write_json(path: Path, payload: JsonObject) -> None:
    """Write JSON to ``path`` atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


class AgenticVisionRunRecorder:
    """Persist structured run events and overlay artifacts for the viewer app."""

    def __init__(self, root_dir: str | Path, run_id: str) -> None:
        self._root_dir = Path(root_dir)
        self.run_id = run_id
        self.run_dir = self._root_dir / run_id
        self.artifacts_dir = self.run_dir / "artifacts"
        self.run_json_path = self.run_dir / "run.json"
        self.events_jsonl_path = self.run_dir / "events.jsonl"
        self._lock = threading.Lock()

        if not self.run_json_path.exists():
            raise FileNotFoundError(f"Run metadata not found for {run_id}: {self.run_json_path}")
        self._metadata = json.loads(self.run_json_path.read_text(encoding="utf-8"))

    @classmethod
    def create(
        cls,
        root_dir: str | Path,
        frame_uri: str,
        dataset_name: str | None = None,
        run_label: str | None = None,
        max_iters: int | None = None,
        sam3_handler_name: str | None = None,
    ) -> "AgenticVisionRunRecorder":
        """Create a new persisted run record and return a recorder."""
        now = _utc_now_iso()
        run_id = uuid.uuid4().hex
        frame_name = Path(frame_uri).name or "frame"
        frame_id = _sanitize_name(Path(frame_name).stem or frame_name)
        root = Path(root_dir)
        run_dir = root / run_id
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        events_path = run_dir / "events.jsonl"
        events_path.touch(exist_ok=True)

        metadata: JsonObject = {
            "run_id": run_id,
            "frame_id": frame_id,
            "frame_uri": frame_uri,
            "dataset_name": dataset_name,
            "run_label": run_label,
            "max_iters": max_iters,
            "sam3_handler_name": sam3_handler_name,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "last_sequence": 0,
            "result_annotations": None,
            "error": None,
        }
        _atomic_write_json(run_dir / "run.json", metadata)
        return cls(root_dir=root_dir, run_id=run_id)

    @property
    def metadata(self) -> JsonObject:
        """Return the in-memory run metadata."""
        return dict(self._metadata)

    @property
    def frame_id(self) -> str:
        """Return the primary frame identifier for the run."""
        frame_id = self._metadata.get("frame_id")
        return str(frame_id) if isinstance(frame_id, str) else "frame"

    def _save_metadata(self) -> None:
        _atomic_write_json(self.run_json_path, self._metadata)

    def update_status(
        self,
        status: str,
        *,
        result_annotations: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update top-level run status fields."""
        with self._lock:
            self._metadata["status"] = status
            self._metadata["updated_at"] = _utc_now_iso()
            self._metadata["result_annotations"] = result_annotations
            self._metadata["error"] = error
            self._save_metadata()

    def emit_event(
        self,
        event_type: str,
        *,
        stage_name: str | None = None,
        status: str = "info",
        message: str | None = None,
        payload: JsonObject | None = None,
        artifact: JsonObject | None = None,
        frame_id: str | None = None,
    ) -> JsonObject:
        """Append a structured event to the run log."""
        with self._lock:
            next_sequence = int(self._metadata.get("last_sequence", 0)) + 1
            event: JsonObject = {
                "sequence": next_sequence,
                "event_type": event_type,
                "timestamp": _utc_now_iso(),
                "run_id": self.run_id,
                "frame_id": frame_id or self.frame_id,
                "stage_name": stage_name,
                "status": status,
                "message": message,
                "payload": payload,
                "artifact": artifact,
            }
            with self.events_jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
            self._metadata["last_sequence"] = next_sequence
            self._metadata["updated_at"] = event["timestamp"]
            self._save_metadata()
        return event

    def emit_log(
        self,
        message: str,
        *,
        stage_name: str | None = None,
        status: str = "info",
        payload: JsonObject | None = None,
    ) -> JsonObject:
        """Emit a structured log event."""
        return self.emit_event(
            "log",
            stage_name=stage_name,
            status=status,
            message=message,
            payload=payload,
        )

    def record_artifact(
        self,
        *,
        image_bgr: np.ndarray,
        artifact_kind: str,
        stage_name: str | None = None,
        payload: JsonObject | None = None,
        message: str | None = None,
    ) -> JsonObject:
        """Persist an image artifact and emit a matching overlay event."""
        artifact_name = f"{int(self._metadata.get('last_sequence', 0)) + 1:05d}_{_sanitize_name(stage_name or artifact_kind)}.jpg"
        artifact_path = self.artifacts_dir / artifact_name
        if not cv2.imwrite(str(artifact_path), image_bgr):
            raise ValueError(f"Failed to write artifact image: {artifact_path}")

        height, width = image_bgr.shape[:2]
        artifact_payload: JsonObject = {
            "artifact_id": artifact_name,
            "artifact_kind": artifact_kind,
            "content_type": "image/jpeg",
            "relative_path": f"artifacts/{artifact_name}",
            "width": width,
            "height": height,
        }
        self.emit_event(
            "overlay_generated",
            stage_name=stage_name,
            status="ready",
            message=message or f"Rendered {artifact_kind}",
            payload=payload,
            artifact=artifact_payload,
        )
        return artifact_payload


def list_viewer_runs(root_dir: str | Path) -> list[JsonObject]:
    """Load run summaries ordered newest-first."""
    root = Path(root_dir)
    if not root.exists():
        return []

    runs: list[JsonObject] = []
    for run_dir in root.iterdir():
        run_json_path = run_dir / "run.json"
        if not run_json_path.exists():
            continue
        try:
            runs.append(json.loads(run_json_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    def _sort_key(item: JsonObject) -> str:
        created_at = item.get("created_at")
        return str(created_at) if isinstance(created_at, str) else ""

    runs.sort(key=_sort_key, reverse=True)
    return runs


def load_viewer_run(root_dir: str | Path, run_id: str) -> JsonObject:
    """Load metadata for one run."""
    run_path = Path(root_dir) / run_id / "run.json"
    return json.loads(run_path.read_text(encoding="utf-8"))


def load_viewer_events(root_dir: str | Path, run_id: str, *, after_sequence: int = 0) -> list[JsonObject]:
    """Load persisted events for one run."""
    events_path = Path(root_dir) / run_id / "events.jsonl"
    if not events_path.exists():
        return []

    events: list[JsonObject] = []
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            sequence = event.get("sequence")
            if isinstance(sequence, int) and sequence <= after_sequence:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def get_viewer_artifact_path(root_dir: str | Path, run_id: str, artifact_id: str) -> Path:
    """Resolve the filesystem path for a stored run artifact."""
    artifact_path = Path(root_dir) / run_id / "artifacts" / artifact_id
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_id}")
    return artifact_path
