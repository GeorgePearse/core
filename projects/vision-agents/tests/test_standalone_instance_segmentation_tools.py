"""Tests for standalone-safe instance-segmentation tool behavior."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import cv2
import numpy as np

from agentic_vision.instance_segmentation.tools import InstanceSegmentationToolkit


def _build_dummy_image() -> SimpleNamespace:
    image = np.full((96, 96, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (24, 24), (72, 72), (0, 0, 255), thickness=-1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    url = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
    return SimpleNamespace(url=url)


def test_segment_with_sam3_returns_explicit_message_when_backend_missing() -> None:
    toolkit = InstanceSegmentationToolkit(image=_build_dummy_image(), frame_uri="local-test-image.jpg")
    detections = "object: red_square | box: [250, 250, 750, 750] | confidence=0.90"

    result = toolkit.segment_with_sam3(detections=detections)

    assert "SAM3 backend is not installed" in result


def test_filter_detections_by_camera_mask_returns_explicit_message_when_bindings_missing() -> None:
    toolkit = InstanceSegmentationToolkit(image=_build_dummy_image())
    detections = "object: red_square | box: [250, 250, 750, 750] | confidence=0.90"

    result = toolkit.filter_detections_by_camera_mask(detections=detections, camera_id=7)

    assert "camera-mask SQL bindings are not available" in result
