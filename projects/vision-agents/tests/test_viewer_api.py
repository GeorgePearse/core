"""Tests for the standalone viewer API."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
from agentic_vision.viewer_runtime import AgenticVisionRunRecorder
from fastapi.testclient import TestClient

from viewer_api.app import app


def test_start_run_creates_viewer_record(tmp_path) -> None:
    with (
        patch("viewer_api.app._get_runs_dir", return_value=str(tmp_path)),
        patch("viewer_api.app._run_agentic_vision_viewer_job", return_value=None),
    ):
        client = TestClient(app)
        response = client.post(
            "/agentic-vision-viewer/runs",
            json={
                "frame_uri": "local-test-image.jpg",
                "dataset_name": "demo-dataset",
                "run_label": "demo-run",
                "max_iters": 10,
                "sam3_handler_name": "premier",
            },
        )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    run = AgenticVisionRunRecorder(tmp_path, run_id)
    assert run.metadata["dataset_name"] == "demo-dataset"
    assert run.metadata["run_label"] == "demo-run"


def test_viewer_routes_expose_events_and_artifacts(tmp_path) -> None:
    recorder = AgenticVisionRunRecorder.create(
        root_dir=tmp_path,
        frame_uri="local-test-image.jpg",
        dataset_name="demo-dataset",
        run_label="demo-run",
    )
    recorder.emit_event("log", message="hello")
    recorder.record_artifact(
        image_bgr=np.full((20, 24, 3), 160, dtype=np.uint8),
        artifact_kind="boxes",
        stage_name="locate_with_qwen",
        payload={"annotations": [{"label": "crate"}]},
        message="Rendered locate_with_qwen",
    )

    with patch("viewer_api.app._get_runs_dir", return_value=str(tmp_path)):
        client = TestClient(app)
        list_response = client.get("/agentic-vision-viewer/runs")
        detail_response = client.get(f"/agentic-vision-viewer/runs/{recorder.run_id}")
        events_response = client.get(f"/agentic-vision-viewer/runs/{recorder.run_id}/events")

        assert list_response.status_code == 200
        assert detail_response.status_code == 200
        assert events_response.status_code == 200

        events = events_response.json()["events"]
        artifact_id = events[1]["artifact"]["artifact_id"]
        artifact_response = client.get(f"/agentic-vision-viewer/runs/{recorder.run_id}/artifacts/{artifact_id}")

    assert list_response.json()["runs"][0]["run_id"] == recorder.run_id
    assert detail_response.json()["run_id"] == recorder.run_id
    assert len(events) == 2
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"] == "image/jpeg"
