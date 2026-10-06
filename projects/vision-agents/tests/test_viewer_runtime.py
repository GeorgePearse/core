"""Tests for the agentic-vision viewer runtime event store."""

from __future__ import annotations

import numpy as np

from agentic_vision.viewer_runtime import (
    AgenticVisionRunRecorder,
    get_viewer_artifact_path,
    list_viewer_runs,
    load_viewer_events,
    load_viewer_run,
)


def test_viewer_runtime_persists_events_and_artifacts(tmp_path) -> None:
    recorder = AgenticVisionRunRecorder.create(
        root_dir=tmp_path,
        frame_uri="gs://bucket/frame_001.jpg",
        dataset_name="demo-dataset",
        run_label="demo-run",
        max_iters=12,
        sam3_handler_name="premier",
    )

    recorder.emit_event(
        "tool_called",
        stage_name="locate_with_qwen",
        status="running",
        message="Calling locate_with_qwen",
        payload={"prompt": "detect all objects"},
    )

    image = np.full((24, 32, 3), 180, dtype=np.uint8)
    recorder.record_artifact(
        image_bgr=image,
        artifact_kind="boxes",
        stage_name="locate_with_qwen",
        payload={"annotations": [{"label": "crate"}]},
        message="Rendered locate_with_qwen",
    )

    recorder.update_status("completed", result_annotations="object: crate | box: [1, 1, 2, 2] | confidence=0.90")

    run = load_viewer_run(tmp_path, recorder.run_id)
    assert run["status"] == "completed"
    assert run["run_label"] == "demo-run"

    events = load_viewer_events(tmp_path, recorder.run_id)
    assert len(events) == 2
    assert events[0]["event_type"] == "tool_called"
    assert events[1]["event_type"] == "overlay_generated"

    overlay_event = events[1]
    artifact = overlay_event["artifact"]
    assert isinstance(artifact, dict)
    artifact_path = get_viewer_artifact_path(tmp_path, recorder.run_id, str(artifact["artifact_id"]))
    assert artifact_path.exists()

    runs = list_viewer_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0]["run_id"] == recorder.run_id
