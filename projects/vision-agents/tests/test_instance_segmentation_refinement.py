"""Focused tests for deterministic mask refinement helpers."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import cv2
import numpy as np

from agentic_vision.instance_segmentation.tools import (
    InstanceSegmentationToolkit,
    _cleanup_binary_mask,
    _parse_segmentation_entries,
)


def _build_dummy_image() -> SimpleNamespace:
    image = np.full((96, 96, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (24, 24), (72, 72), (0, 0, 255), thickness=-1)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    url = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
    return SimpleNamespace(url=url)


def test_parse_segmentation_entries_ignores_note_lines() -> None:
    segmentations = "\n".join(
        [
            "object: red_square | box: [250, 250, 750, 750] | segmentation: [250, 250, 750, 250, 750, 750, 250, 750] | confidence=0.90",
            "[SAM3 experiment positive_points='' negative_points='' positive_prompt='' negative_prompt='' class_rename_rules='']",
        ]
    )
    entries = _parse_segmentation_entries(segmentations)
    assert len(entries) == 1
    assert entries[0].label == "red_square"
    assert len(entries[0].polygon_points) == 4


def test_cleanup_binary_mask_removes_small_islands() -> None:
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[4:20, 4:20] = 1
    mask[30:35, 30:35] = 1

    cleaned = _cleanup_binary_mask(
        mask=mask,
        positive_points_px=[(10, 10)],
        negative_points_px=[],
        kernel_size=5,
    )

    assert cleaned[10, 10] == 1
    assert cleaned[32, 32] == 0


def test_refine_mask_with_cv2_cleanup_rewrites_target_line() -> None:
    toolkit = InstanceSegmentationToolkit(image=_build_dummy_image())
    segmentations = "object: red_square | box: [250, 250, 750, 750] | segmentation: [] | confidence=0.90"

    refined = toolkit.refine_mask_with_cv2(
        segmentations=segmentations,
        target_index=0,
        mode="cleanup",
        positive_points="[[500, 500]]",
        cleanup_kernel_size=5,
    )

    assert "object: red_square" in refined
    assert "segmentation: [" in refined
    assert "[CV2 refine target_index=0" in refined
    assert "resolved_operator=cleanup" in refined
