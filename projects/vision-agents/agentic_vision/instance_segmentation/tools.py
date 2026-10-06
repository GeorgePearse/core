"""Tools for instance segmentation annotation DSPy programme.

Provides VLM detection (Gemini), SAM3 segmentation,
and zoom capabilities as dspy.Tool instances for use with dspy.ReAct.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import dspy
import modal
import numpy as np
from google import genai
from google.genai import types as genai_types
from loguru import logger
from openai import OpenAI
from PIL import Image
from skimage.segmentation import slic

from agentic_vision.coordinates import BoxFormat, BoxValidationError, validate_box
from agentic_vision.object_memory import (
    BackgroundObjectObservation,
    ObjectMemoryBackgroundStore,
    ObjectMemoryRetriever,
)
from agentic_vision.viewer_runtime import AgenticVisionRunRecorder, JsonObject

GEMINI_CLASSIFY_PROMPT = """\
You are given an image with pre-detected bounding boxes. For each detection below, \
identify and classify the object inside the box. Replace generic labels with \
specific, descriptive category names.

{detections}

For each detection, output a JSON array entry with:
- "label": specific descriptive category label (e.g. "steel I-beam", not "object")
- "box_2d": [y1, x1, y2, x2] the original bounding box in 0-1000 coordinates
- "confidence": your classification confidence 0.0-1.0

If you spot additional objects that were missed, include them too with new boxes.
Output a JSON array. If no objects are visible, output an empty array []."""

GEMINI_DETECT_PROMPT = """\
Identify and classify all distinct objects in this image. For each object, output a JSON array entry with:
- "label": specific descriptive category label
- "box_2d": [y1, x1, y2, x2] bounding box in 0-1000 coordinates
- "confidence": detection confidence 0.0-1.0

Focus on accurate classification — use specific material and object names.
Output a JSON array. If no objects are detected, output an empty array []."""

GEMINI_VERIFY_SEGMENTATION_ZOOMED_PROMPT = """\
You are performing a DETAILED, ZOOMED-IN inspection of a single segmentation mask boundary.

The image shows a CROPPED REGION of a larger image, focused on one specific object.
The colored polygon overlay shows the predicted segmentation mask boundary.

Your task is to CRITIQUE THE MASK BOUNDARY WITH EXTREME PRECISION:

1. **Boundary Accuracy** - Does the mask edge exactly follow the object's true edge?
   - Look for: bleeding into background, missing parts of the object, jagged artifacts
   - Check transition areas where object meets background
   - Examine edge cases: corners, thin protrusions, curved surfaces

2. **Fine-Grained Issues** (look for these specific problems):
   - "overshoot": mask extends past true object edge into background
   - "undershoot": mask doesn't reach the true object edge, cutting off parts
   - "jagged": boundary is unnaturally sharp/angular when it should be smooth
   - "smooth_error": boundary is too smooth, missing real indentations/protrusions
   - "opacity_bleed": due to overlay transparency, can't verify (note this)

3. **Label Verification** - Is the object label correct for what you see in this zoomed view?

Output a JSON object with:
- "mask_quality": one of ["excellent", "good", "acceptable", "poor", "unverifiable"]
- "boundary_issues": list of specific issues found (e.g., ["overshoot_top_right", "undershoot_bottom_edge"])
- "confidence": 0.0-1.0 - how confident you are in this assessment given the zoom level
- "label_correct": true/false
- "suggested_label": corrected label if needed
- "notes": detailed description of what you observe at this zoom level
- "recommendation": "keep", "refine", "reject", or "needs_higher_zoom"."""

GEMINI_VERIFY_SEGMENTATION_PROMPT = """\
You are reviewing instance segmentation masks overlaid on an image. \
Each colored polygon represents a predicted segmentation mask for a detected object.

For each segmented object, evaluate:
1. Does the mask tightly follow the object boundary, or does it bleed into the background?
2. Is the label correct for what is actually inside the mask?
3. Are there objects in the image that have no mask (missed detections)?

Output a JSON array where each entry has:
- "label": the object label
- "box_2d": [y1, x1, y2, x2] the bounding box in 0-1000 coordinates
- "mask_quality": "good", "oversized", "undersized", or "wrong_object"
- "label_correct": true or false
- "suggested_label": corrected label if label_correct is false, otherwise same as label
- "notes": brief explanation of any issues

After the per-object entries, add any missed objects as new entries with:
- "label": what the missed object is
- "box_2d": bounding box for the missed object
- "mask_quality": "missing"
- "label_correct": true
- "notes": "Not detected by prior steps"

Output a JSON array. If everything looks perfect, still output the array with mask_quality="good" for each."""

GEMINI_SEGMENTATION_REFINEMENT_PROMPT = """\
You are planning a deterministic mask-refinement step for ONE object.

You are shown a zoomed crop with:
- the current segmentation polygon overlaid in green
- the object's bounding box in red

Decide which operator should run next:
- "keep": the mask is already good enough
- "grabcut": use when the mask leaks into background or needs stronger foreground/background separation
- "superpixel_snap": use when edges should snap to local color/texture boundaries
- "cleanup": use for small holes, speckles, disconnected islands, or mild smoothing only

Output JSON only with these fields:
- "mask_quality": one of ["excellent", "good", "acceptable", "poor"]
- "failure_mode": short string like "background_leakage", "missing_boundary_detail", "noisy_islands", "good_mask"
- "recommended_operator": one of ["keep", "grabcut", "superpixel_snap", "cleanup"]
- "crop_positive_points": list of [x, y] points in CROP-LOCAL 0-1000 coordinates
- "crop_negative_points": list of [x, y] points in CROP-LOCAL 0-1000 coordinates
- "operator_params": object with optional keys:
  - "iterations" (integer, default 3)
  - "superpixel_segments" (integer, default 120)
  - "cleanup_kernel_size" (integer odd size, default 5)
  - "padding_percent" (float, default 12)
- "expected_effect": short sentence
- "notes": short explanation

Rules:
- Prefer "grabcut" as the default if you are uncertain.
- Give positive points on reliable foreground interior.
- Give negative points on obvious background regions the mask should exclude.
- If the mask already looks excellent, return "keep" with empty point lists.
- Keep point counts small and high quality, usually 1-4 positive and 1-4 negative.
"""

GEMINI_FIND_MISSED_OBJECTS_PROMPT = """\
You are reviewing an image that has already been partially annotated. \
The following objects have already been detected and segmented:

{existing_detections}

Your job is to find objects that were MISSED — things visible in the image \
that are NOT in the list above. Scan the entire image systematically: \
top-left to top-right, then middle, then bottom.

Look especially for:
- Small objects that are easy to overlook
- Partially occluded objects hidden behind other things
- Objects at the edges or corners of the image
- Objects that blend into the background
- Clusters where individual items may not have been separated

Output a JSON array of ONLY the missed objects. For each:
- "label": specific descriptive category label
- "box_2d": [y1, x1, y2, x2] bounding box in 0-1000 coordinates
- "confidence": detection confidence 0.0-1.0
- "reason_missed": brief explanation of why this was likely missed (e.g. "small", "occluded", "edge of frame")

If nothing was missed, output an empty array []."""

QWEN_LOCALIZE_PROMPT = """\
Locate all distinct objects in this image with precise bounding boxes. \
For each object provide:
object: <label> | box: [x1, y1, x2, y2] | confidence=0.XX

Coordinates are normalized 0-1000 (top-left origin).
Focus on precise, tight bounding boxes that closely fit each object. \
Be thorough — detect every distinct object or cluster visible, \
even partially occluded ones.
If no objects are detected, output: No objects detected."""

_BOX_RE = re.compile(
    r"box:\s*\[?\s*"
    r"(\d+(?:\.\d+)?)\s*,\s*"
    r"(\d+(?:\.\d+)?)\s*,\s*"
    r"(\d+(?:\.\d+)?)\s*,\s*"
    r"(\d+(?:\.\d+)?)\s*"
    r"\]?"
)
_SEGMENTATION_RE = re.compile(r"segmentation:\s*\[([^\]]*)\]")
_ALLOWED_REFINEMENT_OPERATORS = {
    "auto",
    "keep",
    "grabcut",
    "superpixel_snap",
    "cleanup",
}


@dataclass(slots=True)
class ParsedSegmentationLine:
    """Parsed segmentation entry from line-oriented DSPy output."""

    line_index: int
    raw_line: str
    label: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    polygon_points: list[tuple[float, float]]


@dataclass(slots=True)
class SegmentationRefinementPlan:
    """Structured refinement plan for one segmentation."""

    recommended_operator: str = "grabcut"
    mask_quality: str = "unknown"
    failure_mode: str = "unknown"
    positive_points: list[tuple[float, float]] = field(default_factory=list)
    negative_points: list[tuple[float, float]] = field(default_factory=list)
    iterations: int = 3
    superpixel_segments: int = 120
    cleanup_kernel_size: int = 5
    padding_percent: float = 12.0
    expected_effect: str = ""
    notes: str = ""


def _clean_json_response(text: str) -> str:
    """Strip optional fenced-code markers from JSON-like model output."""
    cleaned = text.strip()
    lines = cleaned.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "```json":
            cleaned = "\n".join(lines[index + 1 :]).split("```", maxsplit=1)[0]
            break
    return cleaned.strip()


def _parse_point_pairs(payload: object) -> list[tuple[float, float]]:
    """Parse a JSON-compatible payload into clamped full-image [0,1000] points."""
    if not isinstance(payload, list):
        return []

    points: list[tuple[float, float]] = []
    for point in payload:
        if not isinstance(point, list | tuple) or len(point) != 2:
            continue
        try:
            x = max(0.0, min(1000.0, float(point[0])))
            y = max(0.0, min(1000.0, float(point[1])))
        except (TypeError, ValueError):
            continue
        points.append((x, y))
    return points


def _parse_point_list_json(raw: str | None) -> list[tuple[float, float]]:
    """Parse a JSON list of full-image [x, y] points."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return _parse_point_pairs(payload)


def _normalize_refinement_operator(
    raw_mode: str | None, default: str = "grabcut"
) -> str:
    """Normalize a refinement operator name."""
    candidate = (raw_mode or "").strip().lower()
    if candidate in _ALLOWED_REFINEMENT_OPERATORS:
        return candidate
    return default


def _parse_segmentation_entries(
    segmentations_text: str,
) -> list[ParsedSegmentationLine]:
    """Parse segmentation lines while ignoring trailing note lines."""
    entries: list[ParsedSegmentationLine] = []
    for line_index, raw_line in enumerate(segmentations_text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue

        match = _BOX_RE.search(line)
        if match is None:
            continue

        x1, y1, x2, y2 = (float(match.group(i)) for i in range(1, 5))
        label_match = re.search(r"object:\s*(.+?)\s*\|", line)
        label = label_match.group(1).strip() if label_match else "unknown"
        conf_match = re.search(r"confidence=(\d+(?:\.\d+)?)", line)
        confidence = float(conf_match.group(1)) if conf_match else 0.5

        polygon_points: list[tuple[float, float]] = []
        seg_match = _SEGMENTATION_RE.search(line)
        if seg_match and seg_match.group(1).strip():
            values = [
                float(v.strip()) for v in seg_match.group(1).split(",") if v.strip()
            ]
            if len(values) >= 6 and len(values) % 2 == 0:
                polygon_points = [
                    (values[i], values[i + 1]) for i in range(0, len(values), 2)
                ]

        entries.append(
            ParsedSegmentationLine(
                line_index=line_index,
                raw_line=line,
                label=label,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=confidence,
                polygon_points=polygon_points,
            )
        )
    return entries


def _format_segmentation_line(
    label: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    confidence: float,
    polygon_points: list[tuple[float, float]],
    area_fraction: float,
) -> str:
    """Format one segmentation line in the standard DSPy output shape."""
    flat_points = [f"{point:.0f}" for xy in polygon_points for point in xy]
    seg_str = ", ".join(flat_points)
    return (
        f"object: {label} | box: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] | "
        f"segmentation: [{seg_str}] | area={area_fraction:.4f} | confidence={confidence:.2f}"
    )


def _coord_1000_to_point_px(coord: float, full_size: int) -> int:
    """Convert a point coordinate from [0,1000] to a valid pixel index."""
    if full_size <= 1:
        return 0
    px = int(round(max(0.0, min(1000.0, coord)) / 1000.0 * full_size))
    return max(0, min(full_size - 1, px))


def _box_1000_to_px(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    full_width: int,
    full_height: int,
) -> tuple[int, int, int, int]:
    """Convert a [0,1000]-space box into pixel-space slicing coordinates."""
    px_x1 = max(0, min(full_width - 1, int(round(x1 / 1000.0 * full_width))))
    px_y1 = max(0, min(full_height - 1, int(round(y1 / 1000.0 * full_height))))
    px_x2 = max(px_x1 + 1, min(full_width, int(round(x2 / 1000.0 * full_width))))
    px_y2 = max(px_y1 + 1, min(full_height, int(round(y2 / 1000.0 * full_height))))
    return px_x1, px_y1, px_x2, px_y2


def _points_1000_to_crop_px(
    points: list[tuple[float, float]],
    crop_px_x1: int,
    crop_px_y1: int,
    crop_width: int,
    crop_height: int,
    full_width: int,
    full_height: int,
) -> list[tuple[int, int]]:
    """Convert full-image [0,1000] points to crop-relative pixel points."""
    crop_points: list[tuple[int, int]] = []
    for x, y in points:
        full_px_x = _coord_1000_to_point_px(x, full_width)
        full_px_y = _coord_1000_to_point_px(y, full_height)
        rel_x = full_px_x - crop_px_x1
        rel_y = full_px_y - crop_px_y1
        if 0 <= rel_x < crop_width and 0 <= rel_y < crop_height:
            crop_points.append((rel_x, rel_y))
    return crop_points


def _crop_px_points_to_full_1000(
    points: list[tuple[float, float]],
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
) -> list[tuple[float, float]]:
    """Remap crop-local [0,1000] points back to full-image [0,1000] points."""
    crop_width = max(crop_x2 - crop_x1, 1.0)
    crop_height = max(crop_y2 - crop_y1, 1.0)
    full_points: list[tuple[float, float]] = []
    for x, y in points:
        clamped_x = max(0.0, min(1000.0, float(x)))
        clamped_y = max(0.0, min(1000.0, float(y)))
        full_points.append(
            (
                crop_x1 + clamped_x * crop_width / 1000.0,
                crop_y1 + clamped_y * crop_height / 1000.0,
            )
        )
    return full_points


def _polygon_to_crop_mask(
    polygon_points: list[tuple[float, float]],
    fallback_box: tuple[float, float, float, float],
    crop_px_x1: int,
    crop_px_y1: int,
    crop_width: int,
    crop_height: int,
    full_width: int,
    full_height: int,
) -> np.ndarray:
    """Rasterize a full-image polygon into a crop-relative binary mask."""
    mask = np.zeros((crop_height, crop_width), dtype=np.uint8)

    points_px = _points_1000_to_crop_px(
        polygon_points,
        crop_px_x1=crop_px_x1,
        crop_px_y1=crop_px_y1,
        crop_width=crop_width,
        crop_height=crop_height,
        full_width=full_width,
        full_height=full_height,
    )
    if len(points_px) >= 3:
        cv2.fillPoly(mask, [np.array(points_px, dtype=np.int32)], 1)
        return mask

    box_x1, box_y1, box_x2, box_y2 = fallback_box
    full_box = _box_1000_to_px(box_x1, box_y1, box_x2, box_y2, full_width, full_height)
    rel_x1 = max(0, min(crop_width - 1, full_box[0] - crop_px_x1))
    rel_y1 = max(0, min(crop_height - 1, full_box[1] - crop_px_y1))
    rel_x2 = max(rel_x1 + 1, min(crop_width, full_box[2] - crop_px_x1))
    rel_y2 = max(rel_y1 + 1, min(crop_height, full_box[3] - crop_px_y1))
    mask[rel_y1:rel_y2, rel_x1:rel_x2] = 1
    return mask


def _fill_binary_mask(mask: np.ndarray) -> np.ndarray:
    """Fill binary mask contours to remove internal holes."""
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    filled = np.zeros_like(mask, dtype=np.uint8)
    for contour in contours:
        cv2.drawContours(filled, [contour], -1, 1, thickness=-1)
    return filled


def _keep_relevant_components(
    mask: np.ndarray, positive_points_px: list[tuple[int, int]]
) -> np.ndarray:
    """Keep connected components covering positive seeds or, if none, the largest component."""
    if mask.max() == 0:
        return mask.astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    if num_labels <= 2:
        return mask.astype(np.uint8)

    keep_labels: set[int] = set()
    for x, y in positive_points_px:
        if 0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]:
            label = int(labels[y, x])
            if label > 0:
                keep_labels.add(label)

    if not keep_labels:
        largest_index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        keep_labels.add(largest_index)

    return np.isin(labels, list(keep_labels)).astype(np.uint8)


def _cleanup_binary_mask(
    mask: np.ndarray,
    positive_points_px: list[tuple[int, int]],
    negative_points_px: list[tuple[int, int]],
    kernel_size: int,
) -> np.ndarray:
    """Run deterministic cleanup over a binary mask."""
    cleaned = (mask > 0).astype(np.uint8)
    kernel_size = max(3, int(kernel_size))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    open_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (max(3, kernel_size - 2), max(3, kernel_size - 2))
    )

    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, open_kernel)

    seed_radius = max(2, kernel_size // 2)
    for x, y in negative_points_px:
        cv2.circle(cleaned, (x, y), seed_radius, 0, thickness=-1)

    cleaned = _keep_relevant_components(cleaned, positive_points_px)
    cleaned = _fill_binary_mask(cleaned)
    return cleaned.astype(np.uint8)


def _apply_grabcut_refinement(
    crop_bgr: np.ndarray,
    initial_mask: np.ndarray,
    bbox_px_rel: tuple[int, int, int, int],
    positive_points_px: list[tuple[int, int]],
    negative_points_px: list[tuple[int, int]],
    iterations: int,
    cleanup_kernel_size: int,
) -> np.ndarray:
    """Refine a mask with OpenCV GrabCut seeded by the current polygon and points."""
    height, width = initial_mask.shape
    if height < 2 or width < 2:
        return initial_mask.astype(np.uint8)

    grabcut_mask = np.full((height, width), cv2.GC_PR_BGD, dtype=np.uint8)
    x1, y1, x2, y2 = bbox_px_rel
    grabcut_mask[max(0, y1) : min(height, y2), max(0, x1) : min(width, x2)] = (
        cv2.GC_PR_FGD
    )

    mask_u8 = (initial_mask > 0).astype(np.uint8)
    if mask_u8.any():
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(mask_u8, kernel, iterations=1)
        eroded = cv2.erode(mask_u8, kernel, iterations=1)
        grabcut_mask[dilated == 0] = cv2.GC_PR_BGD
        grabcut_mask[dilated > 0] = cv2.GC_PR_FGD
        if eroded.any():
            grabcut_mask[eroded > 0] = cv2.GC_FGD

    seed_radius = max(2, int(round(min(height, width) * 0.03)))
    for x, y in positive_points_px:
        cv2.circle(grabcut_mask, (x, y), seed_radius, cv2.GC_FGD, thickness=-1)
    for x, y in negative_points_px:
        cv2.circle(grabcut_mask, (x, y), seed_radius, cv2.GC_BGD, thickness=-1)

    grabcut_mask[:2, :] = cv2.GC_BGD
    grabcut_mask[-2:, :] = cv2.GC_BGD
    grabcut_mask[:, :2] = cv2.GC_BGD
    grabcut_mask[:, -2:] = cv2.GC_BGD

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(
            crop_bgr,
            grabcut_mask,
            None,
            bgd_model,
            fgd_model,
            max(1, int(iterations)),
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error as exc:
        logger.debug(f"GrabCut refinement failed; falling back to cleanup: {exc}")
        return _cleanup_binary_mask(
            mask_u8, positive_points_px, negative_points_px, cleanup_kernel_size
        )

    refined = np.where(
        (grabcut_mask == cv2.GC_FGD) | (grabcut_mask == cv2.GC_PR_FGD), 1, 0
    ).astype(np.uint8)
    refined = _cleanup_binary_mask(
        refined, positive_points_px, negative_points_px, cleanup_kernel_size
    )
    return refined if refined.any() else mask_u8


def _apply_superpixel_refinement(
    crop_bgr: np.ndarray,
    initial_mask: np.ndarray,
    positive_points_px: list[tuple[int, int]],
    negative_points_px: list[tuple[int, int]],
    superpixel_segments: int,
    cleanup_kernel_size: int,
) -> tuple[np.ndarray, str]:
    """Snap a mask to superpixel-like regions using SLIC."""
    mask_u8 = (initial_mask > 0).astype(np.uint8)
    image_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    segments = slic(
        image_rgb,
        n_segments=max(20, int(superpixel_segments)),
        compactness=10.0,
        sigma=1.0,
        start_label=0,
        channel_axis=-1,
    )

    output_mask = np.zeros_like(mask_u8)
    dilated_mask = cv2.dilate(mask_u8, np.ones((3, 3), dtype=np.uint8), iterations=1)
    positive_ids = {
        int(segments[y, x])
        for x, y in positive_points_px
        if 0 <= x < segments.shape[1] and 0 <= y < segments.shape[0]
    }
    negative_ids = {
        int(segments[y, x])
        for x, y in negative_points_px
        if 0 <= x < segments.shape[1] and 0 <= y < segments.shape[0]
    }

    for segment_id in np.unique(segments):
        if int(segment_id) in negative_ids:
            continue

        segment_mask = segments == segment_id
        segment_area = int(segment_mask.sum())
        if segment_area == 0:
            continue

        overlap = int(np.logical_and(segment_mask, mask_u8 > 0).sum()) / segment_area
        dilated_overlap = (
            int(np.logical_and(segment_mask, dilated_mask > 0).sum()) / segment_area
        )

        if (
            int(segment_id) in positive_ids
            or overlap >= 0.35
            or (overlap >= 0.12 and dilated_overlap >= 0.75)
        ):
            output_mask[segment_mask] = 1

    refined = _cleanup_binary_mask(
        output_mask, positive_points_px, negative_points_px, cleanup_kernel_size
    )
    if refined.any():
        return refined, "superpixel_snap"
    return mask_u8, "superpixel_empty"


def _mask_to_polygon_points(
    mask: np.ndarray,
    crop_px_x1: int,
    crop_px_y1: int,
    full_width: int,
    full_height: int,
) -> list[tuple[float, float]]:
    """Convert a crop-relative binary mask into full-image polygon points in [0,1000]."""
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []

    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, closed=True)
    approx = cv2.approxPolyDP(contour, epsilon=max(1.0, 0.003 * perimeter), closed=True)
    polygon = approx if len(approx) >= 3 else contour

    points: list[tuple[float, float]] = []
    for point in polygon[:, 0, :]:
        full_px_x = crop_px_x1 + int(point[0])
        full_px_y = crop_px_y1 + int(point[1])
        points.append(
            (
                max(0.0, min(1000.0, full_px_x / full_width * 1000.0)),
                max(0.0, min(1000.0, full_px_y / full_height * 1000.0)),
            )
        )
    return points


def _replace_line(lines: list[str], line_index: int, new_line: str) -> list[str]:
    """Return a copy of ``lines`` with one line replaced."""
    updated = list(lines)
    updated[line_index] = new_line
    return updated


def _decode_dspy_image_bytes(image: dspy.Image) -> bytes:
    """Decode a dspy.Image data URI into raw bytes."""
    url = image.url
    if not url.startswith("data:"):
        raise ValueError(f"Expected data URI in dspy.Image.url, got: {url[:80]}")
    _, encoded = url.split(",", 1)
    return base64.b64decode(encoded)


def _decode_dspy_image_array(image: dspy.Image) -> np.ndarray:
    """Decode a dspy.Image into a BGR numpy array."""
    raw_bytes = _decode_dspy_image_bytes(image)
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("cv2.imdecode returned None for DSPy image data")
    return decoded


def _array_to_dspy_image(arr: np.ndarray) -> dspy.Image:
    """Encode a BGR numpy array to a temporary JPEG-backed DSPy image."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.close(tmp_fd)
    try:
        cv2.imwrite(tmp_path, arr)
        return dspy.Image(tmp_path)
    finally:
        os.unlink(tmp_path)


def _parse_gemini_detections(response_text: str) -> str:
    """Parse Gemini JSON detection response into standard detection format."""
    lines = response_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "```json":
            response_text = "\n".join(lines[index + 1 :])
            response_text = response_text.split("```", maxsplit=1)[0]
            break

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text

    if not isinstance(data, list):
        data = [data] if data else []

    detection_lines = []
    for det in data:
        label = det.get("label", "unknown")
        box = det.get("box_2d", [0, 0, 0, 0])
        confidence = det.get("confidence", 0.5)

        if len(box) == 4:
            try:
                validate_box(
                    box, BoxFormat.YXYX_NORM_1K, context=f"Gemini detection '{label}'"
                )
            except BoxValidationError as exc:
                logger.warning(f"Skipping invalid Gemini detection: {exc}")
                continue
            # Gemini returns [y1, x1, y2, x2], convert to [x1, y1, x2, y2]
            y1, x1, y2, x2 = (float(v) for v in box)
            detection_lines.append(
                f"object: {label} | box: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] | confidence={float(confidence):.2f}"
            )

    return "\n".join(detection_lines) if detection_lines else "No objects detected."


def parse_boxes_from_detections(
    detections_text: str,
) -> list[tuple[str, float, float, float, float, float]]:
    """Parse detection text into list of (label, x1, y1, x2, y2, confidence)."""
    results: list[tuple[str, float, float, float, float, float]] = []
    for line in detections_text.strip().splitlines():
        line = line.strip()
        if not line or "no objects" in line.lower():
            continue

        match = _BOX_RE.search(line)
        if not match:
            continue

        x1, y1, x2, y2 = (float(match.group(i)) for i in range(1, 5))

        label_match = re.search(r"object:\s*(.+?)\s*\|", line)
        label = label_match.group(1).strip() if label_match else "unknown"

        conf_match = re.search(r"confidence=(\d+(?:\.\d+)?)", line)
        confidence = float(conf_match.group(1)) if conf_match else 0.5

        results.append((label, x1, y1, x2, y2, confidence))

    return results


def _parse_class_rename_rules(raw: str | None) -> dict[str, str]:
    """Parse `old:new,old2:new2` style rename rules."""
    if not raw:
        return {}
    rules: dict[str, str] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        old, new = chunk.split(":", maxsplit=1)
        old_key = old.strip().lower()
        new_value = new.strip()
        if old_key and new_value:
            rules[old_key] = new_value
    return rules


def _parse_indexed_point_prompts(
    raw: str | None, num_detections: int
) -> list[list[list[float]]]:
    """Parse per-detection point prompts from JSON.

    Supported formats:
    - `{"0": [[x, y], [x, y]], "2": [[x, y]]}`
    - `[[[x, y]], [], [[x, y]]]`

    Coordinates are in full-image 0-1000 space.
    """
    points_by_detection: list[list[list[float]]] = [[] for _ in range(num_detections)]
    if not raw or not raw.strip():
        return points_by_detection

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return points_by_detection

    def _normalize_point(point: object) -> list[float] | None:
        if not isinstance(point, list | tuple) or len(point) != 2:
            return None
        try:
            x = max(0.0, min(1000.0, float(point[0])))
            y = max(0.0, min(1000.0, float(point[1])))
        except (TypeError, ValueError):
            return None
        return [x / 1000.0, y / 1000.0]

    if isinstance(payload, list):
        for detection_index, point_list in enumerate(payload[:num_detections]):
            if not isinstance(point_list, list):
                continue
            normalized_points = []
            for point in point_list:
                normalized = _normalize_point(point)
                if normalized is not None:
                    normalized_points.append(normalized)
            points_by_detection[detection_index] = normalized_points
        return points_by_detection

    if isinstance(payload, dict):
        for raw_index, point_list in payload.items():
            if not isinstance(raw_index, str) or not raw_index.isdigit():
                continue
            detection_index = int(raw_index)
            if (
                detection_index < 0
                or detection_index >= num_detections
                or not isinstance(point_list, list)
            ):
                continue
            normalized_points = []
            for point in point_list:
                normalized = _normalize_point(point)
                if normalized is not None:
                    normalized_points.append(normalized)
            points_by_detection[detection_index] = normalized_points
    return points_by_detection


def _remap_box_to_full_image(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
) -> tuple[float, float, float, float]:
    """Remap 0-1000 coordinates from crop-space back to full-image-space."""
    crop_w = crop_x2 - crop_x1
    crop_h = crop_y2 - crop_y1
    full_x1 = crop_x1 + x1 * crop_w / 1000.0
    full_y1 = crop_y1 + y1 * crop_h / 1000.0
    full_x2 = crop_x1 + x2 * crop_w / 1000.0
    full_y2 = crop_y1 + y2 * crop_h / 1000.0
    return full_x1, full_y1, full_x2, full_y2


def _remap_detections_to_full_image(
    detection_text: str,
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
) -> str:
    """Remap all bounding box coordinates in detection text from crop-space to full-image-space."""
    if crop_x1 == 0.0 and crop_y1 == 0.0 and crop_x2 == 1000.0 and crop_y2 == 1000.0:
        return detection_text

    remapped_lines: list[str] = []
    for line in detection_text.strip().splitlines():
        match = _BOX_RE.search(line)
        if match is None:
            remapped_lines.append(line)
            continue

        cx1, cy1, cx2, cy2 = (float(match.group(i)) for i in range(1, 5))
        fx1, fy1, fx2, fy2 = _remap_box_to_full_image(
            cx1,
            cy1,
            cx2,
            cy2,
            crop_x1,
            crop_y1,
            crop_x2,
            crop_y2,
        )
        remapped_box = f"[{fx1:.0f}, {fy1:.0f}, {fx2:.0f}, {fy2:.0f}]"
        remapped_lines.append(
            line[: match.start()] + "box: " + remapped_box + line[match.end() :]
        )
    return "\n".join(remapped_lines)


def _parse_mask_polygon(mask_text: str) -> list[tuple[float, float]]:
    """Parse Postgres polygon text ``((x1,y1),(x2,y2),...)`` into coordinate tuples."""
    cleaned = mask_text.replace("(", "").replace(")", "").strip()
    values = [float(v) for v in cleaned.split(",")]
    return [(values[i], values[i + 1]) for i in range(0, len(values), 2)]


def _point_in_polygon(px: float, py: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Compute IoU between two (x1, y1, x2, y2) boxes."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def deduplicate_detections(detection_text: str, iou_threshold: float = 0.5) -> str:
    """Remove duplicate detections by NMS — keep higher-confidence box per overlap."""
    parsed = parse_boxes_from_detections(detection_text)
    if len(parsed) <= 1:
        return detection_text

    # Sort by confidence descending
    indexed = sorted(enumerate(parsed), key=lambda item: -item[1][5])
    keep_indices: list[int] = []

    for _i, (orig_i, det_i) in enumerate(indexed):
        box_i = (det_i[1], det_i[2], det_i[3], det_i[4])
        suppressed = False
        for kept_orig_idx in keep_indices:
            det_k = parsed[kept_orig_idx]
            box_k = (det_k[1], det_k[2], det_k[3], det_k[4])
            if _iou(box_i, box_k) > iou_threshold:
                suppressed = True
                break
        if not suppressed:
            keep_indices.append(orig_i)

    lines = detection_text.strip().splitlines()
    # Map original parse indices back to lines (skip non-detection lines)
    detection_line_indices: list[int] = []
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped
            and "no objects" not in stripped.lower()
            and _BOX_RE.search(stripped)
        ):
            detection_line_indices.append(line_idx)

    kept_line_set = {
        detection_line_indices[i]
        for i in keep_indices
        if i < len(detection_line_indices)
    }
    # Keep non-detection lines (headers etc) plus kept detection lines
    kept_lines = []
    for line_idx, line in enumerate(lines):
        if line_idx not in detection_line_indices or line_idx in kept_line_set:
            kept_lines.append(line)

    removed = len(parsed) - len(keep_indices)
    result = "\n".join(kept_lines)
    if removed > 0:
        result += f"\n[Dedup: removed {removed} duplicate detection(s) at IoU>{iou_threshold}]"
    return result


class InstanceSegmentationToolkit:
    """Tools for instance segmentation annotation.

    Wraps Gemini, SAM3, and zoom
    as callable tools for dspy.ReAct.

    All VLM and verification tools operate on the *current working image*,
    which starts as the full image and changes when zoom_in is called.
    Coordinates returned by tools operating on a crop are automatically
    remapped to full-image-space so final output is consistent.
    Call reset_to_full_image to zoom back out.
    """

    # Type alias for the human input callback.
    # Receives a question string, returns the human's answer string.
    HumanInputFn = Callable[[str], str]

    def __init__(
        self,
        image: dspy.Image,
        frame_uri: str | None = None,
        dataset_name: str | None = None,
        sam3_handler_name: str = "premier_sam3",
        human_input_fn: Callable[[str], str] | None = None,
        viewer_recorder: AgenticVisionRunRecorder | None = None,
        enable_object_memory: bool = True,
    ) -> None:
        self._full_image = image
        self._full_image_array = _decode_dspy_image_array(image)
        self._full_height, self._full_width = self._full_image_array.shape[:2]

        # Current working image — starts as the full image
        self._image = image
        self._image_array = self._full_image_array
        self._height, self._width = self._full_height, self._full_width

        # Current crop region in full-image 0-1000 space (full image = 0,0,1000,1000)
        self._crop_x1: float = 0.0
        self._crop_y1: float = 0.0
        self._crop_x2: float = 1000.0
        self._crop_y2: float = 1000.0

        self._frame_uri = frame_uri
        self._dataset_name = dataset_name
        self._sam3_handler_name = sam3_handler_name
        self._human_input_fn = human_input_fn
        self._viewer_recorder = viewer_recorder
        self._object_memory_retriever: ObjectMemoryRetriever | None = None
        self._object_memory_background_store: ObjectMemoryBackgroundStore | None = None
        self._stage_event_counter = 0
        if dataset_name:
            # Always enable retriever for reading existing embeddings
            try:
                self._object_memory_retriever = ObjectMemoryRetriever(
                    dataset_name=dataset_name
                )
            except Exception as exc:
                logger.warning(
                    f"Object memory retriever unavailable for dataset={dataset_name}: {exc}"
                )
            # Only enable store/write if enable_object_memory is True
            if enable_object_memory:
                try:
                    self._object_memory_background_store = ObjectMemoryBackgroundStore(
                        dataset_name=dataset_name
                    )
                except Exception as exc:
                    logger.warning(
                        f"Object memory background store unavailable for dataset={dataset_name}: {exc}"
                    )
        logger.debug(
            f"InstanceSegmentationToolkit initialized | {self._full_width}x{self._full_height} "
            f"frame_uri={'yes' if frame_uri else 'no'} "
            f"dataset={dataset_name or 'none'} "
            f"human_input={'available' if human_input_fn else 'unavailable'}"
        )
        if self._viewer_recorder is not None:
            self._viewer_recorder.emit_log(
                "Initialized instance-segmentation toolkit",
                payload={
                    "frame_uri": frame_uri,
                    "dataset_name": dataset_name,
                    "sam3_handler_name": sam3_handler_name,
                    "image_width": self._full_width,
                    "image_height": self._full_height,
                },
            )
            self._viewer_recorder.record_artifact(
                image_bgr=self._full_image_array,
                artifact_kind="raw_frame",
                stage_name="frame_input",
                payload={
                    "frame_uri": frame_uri,
                    "image_width": self._full_width,
                    "image_height": self._full_height,
                },
                message="Loaded input frame",
            )

    @staticmethod
    def _truncate_text(text: str | None, limit: int = 1200) -> str:
        """Return a bounded text preview for viewer payloads."""
        if text is None:
            return ""
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _current_crop_payload(self) -> JsonObject:
        """Return current crop metadata for viewer events."""
        return {
            "is_cropped": self.is_cropped,
            "crop_region": [self._crop_x1, self._crop_y1, self._crop_x2, self._crop_y2],
        }

    def _emit_tool_called(
        self, stage_name: str, args_summary: JsonObject | None = None
    ) -> None:
        """Emit a structured tool-start event for the viewer."""
        if self._viewer_recorder is None:
            return
        payload: JsonObject = {
            "args": args_summary or {},
            **self._current_crop_payload(),
        }
        self._viewer_recorder.emit_event(
            "tool_called",
            stage_name=stage_name,
            status="running",
            message=f"Calling {stage_name}",
            payload=payload,
        )

    def _emit_nonvisual_tool_result(
        self,
        stage_name: str,
        result_text: str,
        *,
        input_text: str | None = None,
        status: str = "ok",
        extra_payload: JsonObject | None = None,
    ) -> None:
        """Emit a result event for tools that do not naturally produce overlays."""
        if self._viewer_recorder is None:
            return
        payload: JsonObject = {
            "result_preview": self._truncate_text(result_text),
            "input_preview": self._truncate_text(input_text),
            **self._current_crop_payload(),
        }
        if extra_payload:
            payload.update(extra_payload)
        self._viewer_recorder.emit_event(
            "tool_result",
            stage_name=stage_name,
            status=status,
            message=f"{stage_name} completed",
            payload=payload,
        )

    @staticmethod
    def _box_annotations_payload(detections_text: str) -> list[JsonObject]:
        """Convert line-based detections into viewer box annotations."""
        annotations: list[JsonObject] = []
        for label, x1, y1, x2, y2, confidence in parse_boxes_from_detections(
            detections_text
        ):
            annotations.append(
                {
                    "label": label,
                    "box": [x1, y1, x2, y2],
                    "confidence": confidence,
                }
            )
        return annotations

    @staticmethod
    def _segmentation_annotations_payload(segmentations_text: str) -> list[JsonObject]:
        """Convert segmentation output into viewer polygon annotations."""
        annotations: list[JsonObject] = []
        for entry in _parse_segmentation_entries(segmentations_text):
            annotations.append(
                {
                    "label": entry.label,
                    "box": [entry.x1, entry.y1, entry.x2, entry.y2],
                    "confidence": entry.confidence,
                    "polygon": [[x, y] for x, y in entry.polygon_points],
                }
            )
        return annotations

    def _render_boxes_on_full_image(self, detections_text: str) -> np.ndarray:
        """Render detection boxes on the full image."""
        overlay = self._full_image_array.copy()
        render_w, render_h = self._full_width, self._full_height
        for idx, (label, x1, y1, x2, y2, confidence) in enumerate(
            parse_boxes_from_detections(detections_text)
        ):
            color = (
                (idx * 67 + 80) % 255,
                (idx * 131 + 40) % 255,
                (idx * 197 + 120) % 255,
            )
            bx1 = int(x1 * render_w / 1000)
            by1 = int(y1 * render_h / 1000)
            bx2 = int(x2 * render_w / 1000)
            by2 = int(y2 * render_h / 1000)
            cv2.rectangle(overlay, (bx1, by1), (bx2, by2), color, 2)
            cv2.putText(
                overlay,
                f"{label} ({confidence:.2f})",
                (bx1, max(by1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
            )
        return overlay

    @staticmethod
    def _parse_crop_region_from_zoom_result(
        result_text: str,
    ) -> tuple[float, float, float, float] | None:
        """Extract crop coordinates from zoomed verification output."""
        match = re.search(
            r"Crop region:\s*\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]",
            result_text,
        )
        if match is None:
            return None
        return tuple(float(match.group(i)) for i in range(1, 5))

    def _emit_stage_viewer_event(
        self, stage_name: str, prediction_text: str, input_text: str | None = None
    ) -> None:
        """Emit structured viewer events and overlay artifacts for a completed stage."""
        if self._viewer_recorder is None:
            return

        payload: JsonObject = {
            "prediction_preview": self._truncate_text(prediction_text),
            "input_preview": self._truncate_text(input_text),
            **self._current_crop_payload(),
        }
        overlay_image: np.ndarray | None = None
        overlay_payload: JsonObject | None = None

        if stage_name in {
            "locate_with_gemini",
            "classify_with_gemini",
            "find_missed_objects_with_gemini",
            "filter_detections_by_camera_mask",
        }:
            annotations = self._box_annotations_payload(prediction_text)
            overlay_payload = {"overlay_kind": "boxes", "annotations": annotations}
            payload.update(overlay_payload)
            if annotations:
                overlay_image = self._render_boxes_on_full_image(prediction_text)
        elif stage_name == "remember_background_objects":
            source_text = input_text or ""
            annotations = self._box_annotations_payload(source_text)
            overlay_payload = {"overlay_kind": "boxes", "annotations": annotations}
            payload.update(overlay_payload)
            if annotations:
                overlay_image = self._render_boxes_on_full_image(source_text)
        elif stage_name in {"segment_with_sam3", "refine_mask_with_cv2"}:
            annotations = self._segmentation_annotations_payload(prediction_text)
            overlay_payload = {
                "overlay_kind": "segmentations",
                "annotations": annotations,
            }
            payload.update(overlay_payload)
            if annotations:
                overlay_image = self._render_segmentations_on_image(
                    prediction_text, overlay_opacity=0.35
                )
        elif stage_name == "verify_segmentation_with_gemini" and input_text:
            annotations = self._segmentation_annotations_payload(input_text)
            overlay_payload = {
                "overlay_kind": "segmentations",
                "annotations": annotations,
            }
            payload.update(overlay_payload)
            if annotations:
                overlay_image = self._render_segmentations_on_image(
                    input_text, overlay_opacity=0.35
                )
        elif stage_name == "plan_mask_refinement_with_gemini" and input_text:
            try:
                plan_payload = json.loads(_clean_json_response(prediction_text))
            except json.JSONDecodeError:
                plan_payload = {}
            if isinstance(plan_payload, dict):
                payload["plan"] = plan_payload
                target_value = plan_payload.get("target_index")
                target_index = (
                    int(target_value)
                    if isinstance(target_value, int | float | str)
                    and str(target_value).isdigit()
                    else -1
                )
                entries = _parse_segmentation_entries(input_text)
                if 0 <= target_index < len(entries):
                    target = entries[target_index]
                    crop_x1, crop_y1, crop_x2, crop_y2, avg_zoom = (
                        self._compute_focus_crop(
                            target.x1,
                            target.y1,
                            target.x2,
                            target.y2,
                            zoom_factor=2.0,
                        )
                    )
                    crop_image = self._render_segmentation_crop(
                        target.raw_line,
                        crop_x1,
                        crop_y1,
                        crop_x2,
                        crop_y2,
                        overlay_opacity=0.45,
                    )
                    if crop_image is not None:
                        overlay_image = crop_image
                        overlay_payload = {
                            "overlay_kind": "refinement_crop",
                            "target_index": target_index,
                            "approx_zoom": avg_zoom,
                            "crop_region": [crop_x1, crop_y1, crop_x2, crop_y2],
                        }
                        payload.update(overlay_payload)
        elif stage_name == "verify_segmentation_zoomed" and input_text:
            crop_region = self._parse_crop_region_from_zoom_result(prediction_text)
            if crop_region is not None:
                crop_image = self._render_segmentation_crop(
                    input_text,
                    crop_region[0],
                    crop_region[1],
                    crop_region[2],
                    crop_region[3],
                    overlay_opacity=0.45,
                )
                if crop_image is not None:
                    overlay_image = crop_image
                    overlay_payload = {
                        "overlay_kind": "zoomed_verification",
                        "crop_region": list(crop_region),
                    }
                    payload.update(overlay_payload)

        self._viewer_recorder.emit_event(
            "tool_result",
            stage_name=stage_name,
            status="ok",
            message=f"{stage_name} completed",
            payload=payload,
        )
        if overlay_image is not None:
            self._viewer_recorder.record_artifact(
                image_bgr=overlay_image,
                artifact_kind=overlay_payload.get("overlay_kind", "overlay")
                if overlay_payload
                else "overlay",
                stage_name=stage_name,
                payload=payload,
                message=f"Rendered {stage_name}",
            )

    def _record_stage_predictions(
        self, stage_name: str, prediction_text: str, input_text: str | None = None
    ) -> None:
        """Persist every stage prediction to object memory for later critique/learning."""
        self._emit_stage_viewer_event(stage_name, prediction_text, input_text)
        if self._object_memory_background_store is None or self._dataset_name is None:
            return
        if not prediction_text.strip():
            return

        image_h, image_w = self._full_height, self._full_width
        lines = [line.strip() for line in prediction_text.splitlines() if line.strip()]
        observations: list[BackgroundObjectObservation] = []
        timestamp_seed = int(time.time() * 1000)
        self._stage_event_counter += 1

        for idx, line in enumerate(lines):
            match = _BOX_RE.search(line)
            if match is None:
                continue
            x1 = float(match.group(1))
            y1 = float(match.group(2))
            x2 = float(match.group(3))
            y2 = float(match.group(4))
            px_x1 = max(0, min(image_w, int(round(x1 / 1000.0 * image_w))))
            px_y1 = max(0, min(image_h, int(round(y1 / 1000.0 * image_h))))
            px_x2 = max(0, min(image_w, int(round(x2 / 1000.0 * image_w))))
            px_y2 = max(0, min(image_h, int(round(y2 / 1000.0 * image_h))))
            if px_x2 <= px_x1 or px_y2 <= px_y1:
                continue
            crop = self._full_image_array[px_y1:px_y2, px_x1:px_x2].copy()
            if crop.size == 0:
                continue

            label_match = re.search(r"object:\s*(.+?)\s*\|", line)
            label = label_match.group(1).strip() if label_match else stage_name
            conf_match = re.search(r"confidence=(\d+(?:\.\d+)?)", line)
            confidence = float(conf_match.group(1)) if conf_match else 1.0
            line_hash = hashlib.sha1(line.encode("utf-8")).hexdigest()[:16]
            detection_id = timestamp_seed + (self._stage_event_counter * 1000) + idx
            observations.append(
                BackgroundObjectObservation(
                    detection_id=detection_id,
                    class_name=label,
                    confidence=confidence,
                    camera_id=None,
                    frame_uri=self._frame_uri,
                    dataset_name=self._dataset_name,
                    box_x1=px_x1,
                    box_y1=px_y1,
                    box_x2=px_x2,
                    box_y2=px_y2,
                    image_width=image_w,
                    image_height=image_h,
                    reason=f"stage_prediction:{stage_name}",
                    crop_bgr=crop,
                    source_stage=stage_name,
                    source_text=line[:1000],
                    extra_metadata={
                        "tool_stage": stage_name,
                        "source_line_hash": line_hash,
                        "input_text": (input_text or "")[:1000],
                    },
                )
            )

        if not observations:
            line_hash = hashlib.sha1(prediction_text.encode("utf-8")).hexdigest()[:16]
            detection_id = timestamp_seed + (self._stage_event_counter * 1000)
            observations.append(
                BackgroundObjectObservation(
                    detection_id=detection_id,
                    class_name=stage_name,
                    confidence=1.0,
                    camera_id=None,
                    frame_uri=self._frame_uri,
                    dataset_name=self._dataset_name,
                    box_x1=0,
                    box_y1=0,
                    box_x2=image_w,
                    box_y2=image_h,
                    image_width=image_w,
                    image_height=image_h,
                    reason=f"stage_prediction:{stage_name}:global",
                    crop_bgr=self._full_image_array.copy(),
                    source_stage=stage_name,
                    source_text=prediction_text[:1000],
                    extra_metadata={
                        "tool_stage": stage_name,
                        "source_line_hash": line_hash,
                        "input_text": (input_text or "")[:1000],
                    },
                )
            )
        try:
            self._object_memory_background_store.store_background_observations(
                observations
            )
        except Exception as exc:
            logger.debug(f"Stage memory persistence failed for {stage_name}: {exc}")

    @staticmethod
    def _coerce_int(value: object, default: int, minimum: int, maximum: int) -> int:
        """Coerce a scalar-like value to a bounded integer."""
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, coerced))

    @staticmethod
    def _coerce_float(
        value: object, default: float, minimum: float, maximum: float
    ) -> float:
        """Coerce a scalar-like value to a bounded float."""
        try:
            coerced = float(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, coerced))

    def _compute_focus_crop(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        zoom_factor: float,
        center_x_offset: float = 0.0,
        center_y_offset: float = 0.0,
        min_context_percent: float = 15.0,
    ) -> tuple[float, float, float, float, float]:
        """Compute a crop around a target box for zoomed review/refinement."""
        box_w = x2 - x1
        box_h = y2 - y1
        box_center_x = x1 + box_w / 2.0
        box_center_y = y1 + box_h / 2.0

        offset_x = box_w * center_x_offset / 100.0
        offset_y = box_h * center_y_offset / 100.0
        crop_center_x = box_center_x + offset_x
        crop_center_y = box_center_y + offset_y

        zoom_factor = max(1.0, float(zoom_factor))
        effective_zoom = min(zoom_factor, 100.0 / max(1.0, min_context_percent))

        crop_w = max(box_w / effective_zoom, box_w * min_context_percent / 100.0)
        crop_h = max(box_h / effective_zoom, box_h * min_context_percent / 100.0)

        crop_x1 = max(0.0, crop_center_x - crop_w / 2.0)
        crop_y1 = max(0.0, crop_center_y - crop_h / 2.0)
        crop_x2 = min(1000.0, crop_center_x + crop_w / 2.0)
        crop_y2 = min(1000.0, crop_center_y + crop_h / 2.0)

        if crop_x1 == 0.0:
            crop_x2 = min(1000.0, crop_x1 + crop_w)
        if crop_y1 == 0.0:
            crop_y2 = min(1000.0, crop_y1 + crop_h)
        if crop_x2 == 1000.0:
            crop_x1 = max(0.0, crop_x2 - crop_w)
        if crop_y2 == 1000.0:
            crop_y1 = max(0.0, crop_y2 - crop_h)

        actual_zoom_x = 1000.0 / max(crop_x2 - crop_x1, 1.0)
        actual_zoom_y = 1000.0 / max(crop_y2 - crop_y1, 1.0)
        avg_zoom = (actual_zoom_x + actual_zoom_y) / 2.0
        return crop_x1, crop_y1, crop_x2, crop_y2, avg_zoom

    def _normalize_refinement_plan_payload(
        self,
        payload: object,
        crop_x1: float,
        crop_y1: float,
        crop_x2: float,
        crop_y2: float,
        default_operator: str,
    ) -> SegmentationRefinementPlan:
        """Convert Gemini JSON output into a bounded refinement plan."""
        if not isinstance(payload, dict):
            return SegmentationRefinementPlan(recommended_operator=default_operator)

        params = payload.get("operator_params")
        params_dict = params if isinstance(params, dict) else {}

        recommended_operator = _normalize_refinement_operator(
            str(payload.get("recommended_operator", "") or ""),
            default=default_operator,
        )
        positive_points = _parse_point_pairs(payload.get("positive_points"))
        negative_points = _parse_point_pairs(payload.get("negative_points"))
        if not positive_points:
            positive_points = _crop_px_points_to_full_1000(
                _parse_point_pairs(payload.get("crop_positive_points")),
                crop_x1,
                crop_y1,
                crop_x2,
                crop_y2,
            )
        if not negative_points:
            negative_points = _crop_px_points_to_full_1000(
                _parse_point_pairs(payload.get("crop_negative_points")),
                crop_x1,
                crop_y1,
                crop_x2,
                crop_y2,
            )

        return SegmentationRefinementPlan(
            recommended_operator=recommended_operator,
            mask_quality=str(payload.get("mask_quality", "unknown"))[:32],
            failure_mode=str(payload.get("failure_mode", "unknown"))[:64],
            positive_points=positive_points,
            negative_points=negative_points,
            iterations=self._coerce_int(
                params_dict.get("iterations"), default=3, minimum=1, maximum=8
            ),
            superpixel_segments=self._coerce_int(
                params_dict.get("superpixel_segments"),
                default=120,
                minimum=20,
                maximum=400,
            ),
            cleanup_kernel_size=self._coerce_int(
                params_dict.get("cleanup_kernel_size"),
                default=5,
                minimum=3,
                maximum=21,
            ),
            padding_percent=self._coerce_float(
                params_dict.get("padding_percent"),
                default=12.0,
                minimum=2.0,
                maximum=40.0,
            ),
            expected_effect=str(payload.get("expected_effect", ""))[:240],
            notes=str(payload.get("notes", ""))[:400],
        )

    def _plan_to_json_text(
        self,
        plan: SegmentationRefinementPlan,
        target_index: int,
    ) -> str:
        """Serialize a refinement plan for tool output and chaining."""
        return json.dumps(
            {
                "target_index": target_index,
                "mask_quality": plan.mask_quality,
                "failure_mode": plan.failure_mode,
                "recommended_operator": plan.recommended_operator,
                "positive_points": [[x, y] for x, y in plan.positive_points],
                "negative_points": [[x, y] for x, y in plan.negative_points],
                "operator_params": {
                    "iterations": plan.iterations,
                    "superpixel_segments": plan.superpixel_segments,
                    "cleanup_kernel_size": plan.cleanup_kernel_size,
                    "padding_percent": plan.padding_percent,
                },
                "expected_effect": plan.expected_effect,
                "notes": plan.notes,
            },
            indent=2,
            sort_keys=True,
        )

    def _build_refinement_plan_with_gemini(
        self,
        segmentations: str,
        target_index: int,
        zoom_factor: float,
        overlay_opacity: float,
        default_operator: str,
    ) -> tuple[SegmentationRefinementPlan, str]:
        """Ask Gemini to choose a deterministic refinement operator and seed points."""

        entries = _parse_segmentation_entries(segmentations)
        if target_index < 0 or target_index >= len(entries):
            raise ValueError(
                f"target_index {target_index} out of range (0-{len(entries) - 1})"
            )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set.")

        target = entries[target_index]
        crop_x1, crop_y1, crop_x2, crop_y2, avg_zoom = self._compute_focus_crop(
            target.x1,
            target.y1,
            target.x2,
            target.y2,
            zoom_factor=zoom_factor,
        )
        annotated_array = self._render_segmentation_crop(
            target.raw_line,
            crop_x1,
            crop_y1,
            crop_x2,
            crop_y2,
            overlay_opacity=overlay_opacity,
        )
        if annotated_array is None:
            raise ValueError("Failed to render refinement crop.")

        annotated_bytes = cv2.imencode(".jpg", annotated_array)[1].tobytes()
        pil_image = Image.open(io.BytesIO(annotated_bytes)).convert("RGBA")
        pil_image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

        crop_info = (
            f"Target index: {target_index}\n"
            f"Label: {target.label}\n"
            f"Box (full image 0-1000): [{target.x1:.0f}, {target.y1:.0f}, {target.x2:.0f}, {target.y2:.0f}]\n"
            f"Crop region (full image 0-1000): [{crop_x1:.0f}, {crop_y1:.0f}, {crop_x2:.0f}, {crop_y2:.0f}]\n"
            f"Approx zoom: {avg_zoom:.1f}x\n"
            f"Default operator if uncertain: {default_operator}\n"
            "Return point prompts in crop-local 0-1000 coordinates only."
        )

        client = genai.Client(api_key=api_key)
        config = genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                GEMINI_SEGMENTATION_REFINEMENT_PROMPT + "\n\n" + crop_info,
                pil_image,
            ],
            config=config,
        )
        if response.text is None:
            raise ValueError("Gemini returned no refinement plan.")

        cleaned = _clean_json_response(response.text)
        payload = json.loads(cleaned)
        plan = self._normalize_refinement_plan_payload(
            payload,
            crop_x1=crop_x1,
            crop_y1=crop_y1,
            crop_x2=crop_x2,
            crop_y2=crop_y2,
            default_operator=default_operator,
        )
        return plan, cleaned

    def plan_mask_refinement_with_gemini(
        self,
        segmentations: str,
        target_index: int,
        zoom_factor: float = 2.0,
        overlay_opacity: float = 0.45,
        default_operator: str = "grabcut",
    ) -> str:
        """Ask Gemini to choose between keep, grabcut, superpixel_snap, and cleanup."""
        self._emit_tool_called(
            "plan_mask_refinement_with_gemini",
            {
                "target_index": target_index,
                "zoom_factor": zoom_factor,
                "overlay_opacity": overlay_opacity,
                "default_operator": default_operator,
            },
        )
        try:
            plan, _ = self._build_refinement_plan_with_gemini(
                segmentations=segmentations,
                target_index=target_index,
                zoom_factor=zoom_factor,
                overlay_opacity=overlay_opacity,
                default_operator=_normalize_refinement_operator(
                    default_operator, default="grabcut"
                ),
            )
        except Exception as exc:
            logger.warning(f"Gemini refinement planning failed: {exc}")
            return f"Error: refinement planning failed: {exc}"

        result = self._plan_to_json_text(plan, target_index=target_index)
        self._record_stage_predictions(
            "plan_mask_refinement_with_gemini", result, segmentations
        )
        return result

    def refine_mask_with_cv2(
        self,
        segmentations: str,
        target_index: int,
        mode: str = "auto",
        refinement_plan: str = "",
        positive_points: str = "",
        negative_points: str = "",
        iterations: int | None = None,
        superpixel_segments: int | None = None,
        cleanup_kernel_size: int | None = None,
        padding_percent: float | None = None,
    ) -> str:
        """Refine one segmentation with deterministic CV operators seeded by Gemini or explicit points."""
        self._emit_tool_called(
            "refine_mask_with_cv2",
            {
                "target_index": target_index,
                "mode": mode,
                "iterations": iterations,
                "superpixel_segments": superpixel_segments,
                "cleanup_kernel_size": cleanup_kernel_size,
                "padding_percent": padding_percent,
            },
        )
        entries = _parse_segmentation_entries(segmentations)
        if target_index < 0 or target_index >= len(entries):
            return f"Error: target_index {target_index} out of range (0-{len(entries) - 1})"

        requested_mode = _normalize_refinement_operator(mode, default="auto")
        plan = SegmentationRefinementPlan()
        if refinement_plan.strip():
            try:
                payload = json.loads(_clean_json_response(refinement_plan))
                plan = self._normalize_refinement_plan_payload(
                    payload,
                    crop_x1=0.0,
                    crop_y1=0.0,
                    crop_x2=1000.0,
                    crop_y2=1000.0,
                    default_operator="grabcut",
                )
            except Exception as exc:
                logger.debug(
                    f"Failed to parse supplied refinement_plan; ignoring it: {exc}"
                )

        if requested_mode == "auto" and not refinement_plan.strip():
            try:
                plan, _ = self._build_refinement_plan_with_gemini(
                    segmentations=segmentations,
                    target_index=target_index,
                    zoom_factor=2.0,
                    overlay_opacity=0.45,
                    default_operator="grabcut",
                )
                plan_text = self._plan_to_json_text(plan, target_index=target_index)
                self._record_stage_predictions(
                    "plan_mask_refinement_with_gemini", plan_text, segmentations
                )
            except Exception as exc:
                logger.warning(
                    f"Auto refinement planning failed; defaulting to grabcut: {exc}"
                )
                plan = SegmentationRefinementPlan(
                    recommended_operator="grabcut", notes=f"auto_plan_failed:{exc}"
                )

        explicit_positive_points = _parse_point_list_json(positive_points)
        explicit_negative_points = _parse_point_list_json(negative_points)
        if explicit_positive_points:
            plan.positive_points = explicit_positive_points
        if explicit_negative_points:
            plan.negative_points = explicit_negative_points

        if iterations is not None:
            plan.iterations = self._coerce_int(
                iterations, default=plan.iterations, minimum=1, maximum=8
            )
        if superpixel_segments is not None:
            plan.superpixel_segments = self._coerce_int(
                superpixel_segments,
                default=plan.superpixel_segments,
                minimum=20,
                maximum=400,
            )
        if cleanup_kernel_size is not None:
            plan.cleanup_kernel_size = self._coerce_int(
                cleanup_kernel_size,
                default=plan.cleanup_kernel_size,
                minimum=3,
                maximum=21,
            )
        if padding_percent is not None:
            plan.padding_percent = self._coerce_float(
                padding_percent,
                default=plan.padding_percent,
                minimum=2.0,
                maximum=40.0,
            )

        resolved_operator = (
            plan.recommended_operator if requested_mode == "auto" else requested_mode
        )
        resolved_operator = _normalize_refinement_operator(
            resolved_operator, default="grabcut"
        )

        target = entries[target_index]
        box_w = target.x2 - target.x1
        box_h = target.y2 - target.y1
        pad_x = max(5.0, box_w * plan.padding_percent / 100.0)
        pad_y = max(5.0, box_h * plan.padding_percent / 100.0)
        crop_x1 = max(0.0, target.x1 - pad_x)
        crop_y1 = max(0.0, target.y1 - pad_y)
        crop_x2 = min(1000.0, target.x2 + pad_x)
        crop_y2 = min(1000.0, target.y2 + pad_y)

        crop_px = _box_1000_to_px(
            crop_x1, crop_y1, crop_x2, crop_y2, self._full_width, self._full_height
        )
        crop_px_x1, crop_px_y1, crop_px_x2, crop_px_y2 = crop_px
        crop_bgr = self._full_image_array[
            crop_px_y1:crop_px_y2, crop_px_x1:crop_px_x2
        ].copy()
        if crop_bgr.size == 0:
            return "Error: refinement crop is empty."
        crop_height, crop_width = crop_bgr.shape[:2]

        initial_mask = _polygon_to_crop_mask(
            polygon_points=target.polygon_points,
            fallback_box=(target.x1, target.y1, target.x2, target.y2),
            crop_px_x1=crop_px_x1,
            crop_px_y1=crop_px_y1,
            crop_width=crop_width,
            crop_height=crop_height,
            full_width=self._full_width,
            full_height=self._full_height,
        )

        positive_points_full = list(plan.positive_points)
        negative_points_full = list(plan.negative_points)
        if not positive_points_full:
            positive_points_full = [
                ((target.x1 + target.x2) / 2.0, (target.y1 + target.y2) / 2.0)
            ]

        positive_points_px = _points_1000_to_crop_px(
            positive_points_full,
            crop_px_x1=crop_px_x1,
            crop_px_y1=crop_px_y1,
            crop_width=crop_width,
            crop_height=crop_height,
            full_width=self._full_width,
            full_height=self._full_height,
        )
        negative_points_px = _points_1000_to_crop_px(
            negative_points_full,
            crop_px_x1=crop_px_x1,
            crop_px_y1=crop_px_y1,
            crop_width=crop_width,
            crop_height=crop_height,
            full_width=self._full_width,
            full_height=self._full_height,
        )

        full_box_px = _box_1000_to_px(
            target.x1,
            target.y1,
            target.x2,
            target.y2,
            self._full_width,
            self._full_height,
        )
        bbox_px_rel = (
            max(0, full_box_px[0] - crop_px_x1),
            max(0, full_box_px[1] - crop_px_y1),
            max(1, min(crop_width, full_box_px[2] - crop_px_x1)),
            max(1, min(crop_height, full_box_px[3] - crop_px_y1)),
        )

        operator_note = resolved_operator
        if resolved_operator == "keep":
            refined_mask = initial_mask.astype(np.uint8)
        elif resolved_operator == "cleanup":
            refined_mask = _cleanup_binary_mask(
                initial_mask,
                positive_points_px,
                negative_points_px,
                plan.cleanup_kernel_size,
            )
        elif resolved_operator == "superpixel_snap":
            refined_mask, operator_note = _apply_superpixel_refinement(
                crop_bgr=crop_bgr,
                initial_mask=initial_mask,
                positive_points_px=positive_points_px,
                negative_points_px=negative_points_px,
                superpixel_segments=plan.superpixel_segments,
                cleanup_kernel_size=plan.cleanup_kernel_size,
            )
            if operator_note != "superpixel_snap":
                resolved_operator = "cleanup"
        else:
            refined_mask = _apply_grabcut_refinement(
                crop_bgr=crop_bgr,
                initial_mask=initial_mask,
                bbox_px_rel=bbox_px_rel,
                positive_points_px=positive_points_px,
                negative_points_px=negative_points_px,
                iterations=plan.iterations,
                cleanup_kernel_size=plan.cleanup_kernel_size,
            )

        if refined_mask.max() == 0:
            refined_mask = initial_mask.astype(np.uint8)
            operator_note = f"{operator_note}_empty_fallback"

        polygon_points = _mask_to_polygon_points(
            refined_mask,
            crop_px_x1=crop_px_x1,
            crop_px_y1=crop_px_y1,
            full_width=self._full_width,
            full_height=self._full_height,
        )
        if len(polygon_points) < 3:
            polygon_points = [
                (target.x1, target.y1),
                (target.x2, target.y1),
                (target.x2, target.y2),
                (target.x1, target.y2),
            ]

        area_fraction = float(refined_mask.sum()) / float(
            self._full_width * self._full_height
        )
        updated_line = _format_segmentation_line(
            label=target.label,
            x1=target.x1,
            y1=target.y1,
            x2=target.x2,
            y2=target.y2,
            confidence=target.confidence,
            polygon_points=polygon_points,
            area_fraction=area_fraction,
        )
        updated_lines = _replace_line(
            segmentations.splitlines(), target.line_index, updated_line
        )
        updated_lines.append(
            "[CV2 refine "
            f"target_index={target_index} "
            f"requested_operator={requested_mode} "
            f"resolved_operator={resolved_operator} "
            f"operator_note={operator_note} "
            f"positive_points={len(positive_points_full)} "
            f"negative_points={len(negative_points_full)} "
            f"failure_mode={plan.failure_mode}]"
        )
        result = "\n".join(updated_lines)
        input_context = (
            f"target_index={target_index}\n"
            f"mode={mode}\n"
            f"refinement_plan={refinement_plan[:800]}\n"
            f"positive_points={positive_points[:400]}\n"
            f"negative_points={negative_points[:400]}\n"
            f"requested_operator={requested_mode}\n"
            f"resolved_operator={resolved_operator}\n"
            f"operator_note={operator_note}\n"
            f"plan_failure_mode={plan.failure_mode}\n"
            f"plan_notes={plan.notes[:400]}"
        )
        self._record_stage_predictions("refine_mask_with_cv2", result, input_context)
        return result

    @property
    def is_cropped(self) -> bool:
        """True when the current working image is a crop, not the full image."""
        return not (
            self._crop_x1 == 0.0
            and self._crop_y1 == 0.0
            and self._crop_x2 == 1000.0
            and self._crop_y2 == 1000.0
        )

    def classify_with_gemini(self, detections: str) -> str:
        """Classify and refine labels for pre-detected bounding boxes using Gemini.

        Gemini excels at visual understanding and classification. Pass bounding
        box detections (e.g. from locate_with_gemini) and Gemini will assign
        specific, descriptive category labels to each detection. It may also
        identify additional objects that were missed.

        Args:
            detections: Detection text with bounding boxes to classify, or a
                description of what to look for if no prior detections exist.

        Returns:
            Classified detection results with specific labels and boxes.
        """
        self._emit_tool_called(
            "classify_with_gemini",
            {"detections_preview": self._truncate_text(detections, limit=400)},
        )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Error: GEMINI_API_KEY not set."

        client = genai.Client(api_key=api_key)
        image_bytes = _decode_dspy_image_bytes(self._image)
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        pil_image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

        # If detections look like prior box output, use the classify prompt
        has_prior_boxes = "box:" in detections.lower() or "box_2d" in detections.lower()
        if has_prior_boxes:
            full_prompt = GEMINI_CLASSIFY_PROMPT.format(detections=detections)
        else:
            full_prompt = f"{detections}\n\n{GEMINI_DETECT_PROMPT}"

        config = genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[full_prompt, pil_image],
                config=config,
            )
        except Exception as exc:
            logger.error(f"Gemini classification failed: {exc}")
            return f"Error: Gemini API call failed: {exc}"

        if response.text is None:
            return "No objects detected."

        result = _parse_gemini_detections(response.text)
        result = _remap_detections_to_full_image(
            result,
            self._crop_x1,
            self._crop_y1,
            self._crop_x2,
            self._crop_y2,
        )
        self._record_stage_predictions("classify_with_gemini", result, detections)
        logger.debug(f"Gemini classified: {result[:200]}")
        return result

    def locate_with_qwen(self, prompt: str) -> str:
        """Locate all objects with precise bounding boxes using Qwen VLM.

        Qwen excels at spatial localization — producing tight, accurate
        bounding boxes for every object in the scene. Use this as the
        primary detection step to find all objects, then pass the results
        to classify_with_gemini for specific category labels.

        Args:
            prompt: What types of objects to look for in the image.

        Returns:
            Detection results with precise bounding boxes.
        """
        self._emit_tool_called(
            "locate_with_qwen",
            {"prompt": prompt},
        )

        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            return "Error: DASHSCOPE_API_KEY not set."

        base_url = os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

        image_bytes = _decode_dspy_image_bytes(self._image)
        img_base64 = base64.b64encode(image_bytes).decode()
        full_prompt = f"{prompt}\n\n{QWEN_LOCALIZE_PROMPT}"

        try:
            completion = client.chat.completions.create(
                model="qwen3-vl-plus",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}"
                                },
                            },
                            {"type": "text", "text": full_prompt},
                        ],
                    }
                ],
            )
        except Exception as exc:
            logger.error(f"Qwen localization failed: {exc}")
            return f"Error: Qwen API call failed: {exc}"

        response_text = completion.choices[0].message.content
        if not response_text:
            return "No objects detected."

        response_text = _remap_detections_to_full_image(
            response_text,
            self._crop_x1,
            self._crop_y1,
            self._crop_x2,
            self._crop_y2,
        )
        self._record_stage_predictions("locate_with_qwen", response_text, prompt)
        logger.debug(f"Qwen located: {response_text[:200]}")
        return response_text

    def locate_with_gemini(self, prompt: str) -> str:
        """Locate objects in the image using Gemini vision.

        Gemini excels at spatial localization - producing tight, accurate
        bounding boxes for every object in the scene.

        Args:
            prompt: What types of objects to look for in the image.

        Returns:
            Detection results with precise bounding boxes in standard format:
            object: <label> | box: [x1, y1, x2, y2] | confidence=0.XX
        """
        self._emit_tool_called(
            "locate_with_gemini",
            {"prompt": prompt},
        )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Error: GEMINI_API_KEY not set."

        client = genai.Client(api_key=api_key)

        image_bytes = _decode_dspy_image_bytes(self._image)
        img_base64 = base64.b64encode(image_bytes).decode()

        localize_prompt = f"""{prompt}

Locate all distinct objects in this image with precise bounding boxes.
For each object provide EXACTLY this format, one per line:
object: <label> | box: [x1, y1, x2, y2] | confidence=0.XX

Coordinates are normalized 0-1000 (top-left origin, so x increases right, y increases down).
Focus on precise, tight bounding boxes that closely fit each object.
Be thorough — detect every distinct object or cluster visible, even partially occluded ones.
If no objects are detected, output: No objects detected."""

        try:
            image = Image.open(io.BytesIO(image_bytes))
            image = image.convert("RGB")

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[localize_prompt, image],
            )

            if not response.candidates:
                return "No objects detected."

            content = response.candidates[0].content
            if content is None or content.parts is None:
                return "No objects detected."

            response_text = ""
            for part in content.parts:
                if part.text:
                    response_text += part.text

        except Exception as exc:
            logger.error(f"Gemini localization failed: {exc}")
            return f"Error: Gemini API call failed: {exc}"

        if not response_text.strip():
            return "No objects detected."

        response_text = _remap_detections_to_full_image(
            response_text,
            self._crop_x1,
            self._crop_y1,
            self._crop_x2,
            self._crop_y2,
        )
        self._record_stage_predictions("locate_with_gemini", response_text, prompt)
        logger.debug(f"Gemini located: {response_text[:200]}")
        return response_text

    def segment_with_sam3(
        self,
        detections: str,
        positive_points: str = "",
        negative_points: str = "",
        positive_prompt: str = "",
        negative_prompt: str = "",
        class_rename_rules: str = "",
    ) -> str:
        """Generate instance segmentation masks for detected bounding boxes using SAM3.

        Args:
            detections: Detection text with bounding boxes in standard format:
                object: <label> | box: [x1, y1, x2, y2] | confidence=0.XX
            positive_points: JSON mapping of detection index -> positive points in 0-1000 space.
            negative_points: JSON mapping of detection index -> negative points in 0-1000 space.
            positive_prompt: Positive prompt text for experiment tracking.
            negative_prompt: Negative prompt text for experiment tracking.
            class_rename_rules: Label remap experiment rules as `old:new,old2:new2`.

        Returns:
            Segmentation results with polygon points per detection.
        """
        self._emit_tool_called(
            "segment_with_sam3",
            {
                "detections_preview": self._truncate_text(detections, limit=400),
                "positive_points": self._truncate_text(positive_points, limit=200),
                "negative_points": self._truncate_text(negative_points, limit=200),
                "positive_prompt": self._truncate_text(positive_prompt, limit=120),
                "negative_prompt": self._truncate_text(negative_prompt, limit=120),
                "class_rename_rules": class_rename_rules,
            },
        )
        if not self._frame_uri:
            return "Error: frame_uri required for SAM3 segmentation."

        parsed = parse_boxes_from_detections(detections)
        if not parsed:
            return "No valid bounding boxes found in detections."

        # Convert 0-1000 normalized boxes to 0-1 normalized for SAM3
        normalized_boxes = [
            [x1 / 1000.0, y1 / 1000.0, x2 / 1000.0, y2 / 1000.0]
            for _, x1, y1, x2, y2, _ in parsed
        ]
        normalized_positive_points = _parse_indexed_point_prompts(
            positive_points, len(parsed)
        )
        normalized_negative_points = _parse_indexed_point_prompts(
            negative_points, len(parsed)
        )

        segment_boxes = modal.Function.from_name(
            "sam3-vision-agents", "segment_boxes_with_points"
        )
        results = segment_boxes.remote(
            frame_uri=self._frame_uri,
            boxes=normalized_boxes,
            handler_name=self._sam3_handler_name,
            positive_points=normalized_positive_points
            if any(normalized_positive_points)
            else None,
            negative_points=normalized_negative_points
            if any(normalized_negative_points)
            else None,
        )

        rename_rules = _parse_class_rename_rules(class_rename_rules)
        output_lines = []
        for idx, (label, x1, y1, x2, y2, conf) in enumerate(parsed):
            mapped_label = rename_rules.get(label.strip().lower(), label)
            if idx < len(results):
                result = results[idx]
                points = (
                    result.points
                    if hasattr(result, "points")
                    else result.get("points", [])
                )
                seg_area = (
                    result.segmentation_area
                    if hasattr(result, "segmentation_area")
                    else result.get("segmentation_area", 0.0)
                )

                flat_points = []
                for px, py in points:
                    flat_points.extend(
                        [f"{float(px) * 1000:.0f}", f"{float(py) * 1000:.0f}"]
                    )
                seg_str = ", ".join(flat_points)

                output_lines.append(
                    f"object: {mapped_label} | box: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] | "
                    f"segmentation: [{seg_str}] | area={float(seg_area):.4f} | confidence={conf:.2f}"
                )
            else:
                output_lines.append(
                    f"object: {mapped_label} | box: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] | segmentation: [] | confidence={conf:.2f}"
                )

        result = "\n".join(output_lines)
        experiment_context = (
            f"detections={detections[:600]}\n"
            f"positive_points={positive_points[:400]}\n"
            f"negative_points={negative_points[:400]}\n"
            f"positive_prompt={positive_prompt[:200]}\n"
            f"negative_prompt={negative_prompt[:200]}\n"
            f"class_rename_rules={class_rename_rules[:200]}"
        )
        if (
            positive_points.strip()
            or negative_points.strip()
            or positive_prompt.strip()
            or negative_prompt.strip()
            or rename_rules
        ):
            result += (
                "\n"
                f"[SAM3 experiment positive_points='{positive_points[:80]}' "
                f"negative_points='{negative_points[:80]}' "
                f"positive_prompt='{positive_prompt[:80]}' "
                f"negative_prompt='{negative_prompt[:80]}' "
                f"class_rename_rules='{class_rename_rules[:80]}']"
            )
        self._record_stage_predictions("segment_with_sam3", result, experiment_context)
        return result

    def verify_segmentation_with_gemini(
        self,
        segmentations: str,
        overlay_opacity: float = 0.35,
    ) -> str:
        """Verify segmentation mask quality using Gemini as a visual critic.

        Renders the segmentation masks onto the original image and asks Gemini
        to evaluate whether each mask is accurate, correctly labeled, and whether
        any objects were missed. Use this after segment_with_sam3 to catch errors
        before producing final annotations.

        The overlay_opacity controls how transparent the mask fill is when
        rendered on the image. This is a critical parameter:
        - Too high (>0.6): masks obscure the underlying object, making it hard
          to judge whether the mask matches the real object boundary.
        - Too low (<0.15): masks are barely visible, making it hard to see
          where the segmentation boundary actually is.
        - Sweet spot is typically 0.25-0.45, but varies by scene complexity.
          Busy scenes with many overlapping objects benefit from lower opacity;
          simple scenes with isolated objects can use higher opacity.

        If verification results are unclear, try calling again with a different
        overlay_opacity value.

        Args:
            segmentations: Segmentation output from segment_with_sam3 containing
                boxes and polygon points.
            overlay_opacity: Mask fill transparency from 0.0 (invisible) to 1.0
                (fully opaque). Default 0.35. Adjust if verification is unclear.

        Returns:
            Per-object quality assessment with mask_quality ratings and
            suggested corrections. Includes missed detections if any.
        """
        self._emit_tool_called(
            "verify_segmentation_with_gemini",
            {"overlay_opacity": overlay_opacity},
        )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Error: GEMINI_API_KEY not set."

        opacity = max(0.0, min(1.0, float(overlay_opacity)))

        # Render masks onto the image
        annotated_array = self._render_segmentations_on_image(
            segmentations, overlay_opacity=opacity
        )
        annotated_bytes = cv2.imencode(".jpg", annotated_array)[1].tobytes()

        client = genai.Client(api_key=api_key)
        pil_image = Image.open(io.BytesIO(annotated_bytes)).convert("RGBA")
        pil_image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

        config = genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[GEMINI_VERIFY_SEGMENTATION_PROMPT, pil_image],
                config=config,
            )
        except Exception as exc:
            logger.error(f"Gemini segmentation verification failed: {exc}")
            return f"Error: Gemini verification failed: {exc}"

        if response.text is None:
            return "No verification results."

        # Parse and format the verification results
        result = self._format_verification_results(response.text)
        self._record_stage_predictions(
            "verify_segmentation_with_gemini", result, segmentations
        )
        logger.debug(f"Gemini verification: {result[:200]}")
        return result

    def verify_segmentation_zoomed(
        self,
        segmentations: str,
        target_index: int,
        zoom_factor: float = 2.0,
        center_x_offset: float = 0.0,
        center_y_offset: float = 0.0,
        min_context_percent: float = 15.0,
        overlay_opacity: float = 0.45,
    ) -> str:
        """Verify a single segmentation at zoomed-in resolution for detailed boundary critique.

        Unlike verify_segmentation_with_gemini which checks all objects at full-image
        resolution, this method focuses on ONE specific segmentation and renders it at
        higher zoom levels so Gemini can critique boundary details invisible at full scale.

        The crop always includes the segmentation at its center (with optional offset),
        and the zoom_factor controls how tight the crop is around the object.

        Args:
            segmentations: Full segmentation output from segment_with_sam3.
            target_index: Index (0-based) of which segmentation to verify in detail.
            zoom_factor: How much to zoom in relative to the bounding box size.
                - 1.0 = crop to the bbox size (no zoom)
                - 2.0 = crop to 50% of bbox (2x zoom)
                - 4.0 = crop to 25% of bbox (4x zoom)
                Higher values give more detail but less context.
            center_x_offset: Offset the crop center horizontally from bbox center,
                as percentage of bbox width. -50 = left edge, 0 = center, 50 = right edge.
            center_y_offset: Offset the crop center vertically from bbox center,
                as percentage of bbox height. -50 = top edge, 0 = center, 50 = bottom edge.
            min_context_percent: Minimum percentage of bbox to include as context even
                at high zoom levels. Default 15% prevents overly tight crops.
            overlay_opacity: Mask fill transparency. Default 0.45 (higher than full-image
                mode because boundaries are more visible when zoomed in).

        Returns:
            Detailed critique of the single segmentation's boundary quality at zoomed resolution.

        Example usage:
            # 2x zoom on object center for general boundary check
            verify_segmentation_zoomed(segmentations, target_index=0, zoom_factor=2.0)

            # 3x zoom on top-right corner (edge where boundary issues often occur)
            verify_segmentation_zoomed(
                segmentations, target_index=0, zoom_factor=3.0,
                center_x_offset=30, center_y_offset=-30
            )

            # 1.5x zoom with padding for full-object context at higher detail
            verify_segmentation_zoomed(segmentations, target_index=0, zoom_factor=1.5)
        """
        self._emit_tool_called(
            "verify_segmentation_zoomed",
            {
                "target_index": target_index,
                "zoom_factor": zoom_factor,
                "center_x_offset": center_x_offset,
                "center_y_offset": center_y_offset,
                "min_context_percent": min_context_percent,
                "overlay_opacity": overlay_opacity,
            },
        )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Error: GEMINI_API_KEY not set."

        entries = _parse_segmentation_entries(segmentations)
        if target_index < 0 or target_index >= len(entries):
            return f"Error: target_index {target_index} out of range (0-{len(entries) - 1})"

        target = entries[target_index]
        target_line = target.raw_line

        # Extract bbox from the target line
        crop_x1, crop_y1, crop_x2, crop_y2, avg_zoom = self._compute_focus_crop(
            target.x1,
            target.y1,
            target.x2,
            target.y2,
            zoom_factor=zoom_factor,
            center_x_offset=center_x_offset,
            center_y_offset=center_y_offset,
            min_context_percent=min_context_percent,
        )

        # Render the zoomed crop with just this one segmentation visible
        annotated_array = self._render_segmentation_crop(
            target_line,
            crop_x1,
            crop_y1,
            crop_x2,
            crop_y2,
            overlay_opacity=overlay_opacity,
        )

        if annotated_array is None:
            return "Error: Failed to render segmentation crop"

        annotated_bytes = cv2.imencode(".jpg", annotated_array)[1].tobytes()

        client = genai.Client(api_key=api_key)
        pil_image = Image.open(io.BytesIO(annotated_bytes)).convert("RGBA")
        pil_image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

        zoom_info = (
            f"This is a ZOOMED-IN view at approximately {avg_zoom:.1f}x zoom. "
            f"Crop covers region [{crop_x1:.0f}, {crop_y1:.0f}, {crop_x2:.0f}, {crop_y2:.0f}] "
            f"(full image is 0-1000). Focus on boundary precision at this scale."
        )

        if center_x_offset != 0 or center_y_offset != 0:
            zoom_info += f" Crop center is offset ({center_x_offset:+.0f}%, {center_y_offset:+.0f}%) from the object's bounding box center."

        config = genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    GEMINI_VERIFY_SEGMENTATION_ZOOMED_PROMPT + "\n\n" + zoom_info,
                    pil_image,
                ],
                config=config,
            )
        except Exception as exc:
            logger.error(f"Gemini zoomed verification failed: {exc}")
            return f"Error: Gemini zoomed verification failed: {exc}"

        if response.text is None:
            return "No zoomed verification results."

        # Parse the zoomed verification result
        result = self._format_zoomed_verification_results(
            response_text=response.text,
            target_index=target_index,
            zoom_desc=f"{avg_zoom:.1f}x",
            crop_x1=crop_x1,
            crop_y1=crop_y1,
            crop_x2=crop_x2,
            crop_y2=crop_y2,
        )
        self._record_stage_predictions(
            "verify_segmentation_zoomed", result, target_line
        )
        logger.debug(
            f"Gemini zoomed verification (index={target_index}, zoom={avg_zoom:.1f}x): {result[:200]}"
        )
        return result

    def _render_segmentation_crop(
        self,
        segmentation_line: str,
        crop_x1: float,
        crop_y1: float,
        crop_x2: float,
        crop_y2: float,
        overlay_opacity: float = 0.45,
    ) -> np.ndarray | None:
        """Render a single segmentation on a cropped region of the full image.

        Args:
            segmentation_line: One line of segmentation text with box and polygon.
            crop_x1, crop_y1, crop_x2, crop_y2: Crop region in 0-1000 full-image space.
            overlay_opacity: Alpha for mask fill.

        Returns:
            BGR numpy array of the cropped region with segmentation overlay, or None on error.
        """
        seg_re = re.compile(r"segmentation:\s*\[([^\]]*)\]")

        # Convert crop coords to pixel space
        px_x1 = max(0, int(crop_x1 * self._full_width / 1000))
        px_y1 = max(0, int(crop_y1 * self._full_height / 1000))
        px_x2 = min(self._full_width, int(crop_x2 * self._full_width / 1000))
        px_y2 = min(self._full_height, int(crop_y2 * self._full_height / 1000))

        if px_x2 <= px_x1 or px_y2 <= px_y1:
            logger.warning(
                f"Degenerate crop region: [{crop_x1}, {crop_y1}, {crop_x2}, {crop_y2}]"
            )
            return None

        # Crop the full image
        crop_array = self._full_image_array[px_y1:px_y2, px_x1:px_x2].copy()
        crop_h, crop_w = crop_array.shape[:2]

        # Extract box and segmentation from the line
        box_match = _BOX_RE.search(segmentation_line)
        if not box_match:
            return crop_array  # Return crop without overlay if no box found

        x1 = float(box_match.group(1))
        y1 = float(box_match.group(2))
        x2 = float(box_match.group(3))
        y2 = float(box_match.group(4))

        # Convert box to crop-relative pixel coords
        rel_x1 = int((x1 - crop_x1) * crop_w / (crop_x2 - crop_x1))
        rel_y1 = int((y1 - crop_y1) * crop_h / (crop_y2 - crop_y1))
        rel_x2 = int((x2 - crop_x1) * crop_w / (crop_x2 - crop_x1))
        rel_y2 = int((y2 - crop_y1) * crop_h / (crop_y2 - crop_y1))

        # Draw the bounding box (always visible in red for contrast)
        cv2.rectangle(crop_array, (rel_x1, rel_y1), (rel_x2, rel_y2), (0, 0, 255), 2)

        # Extract and draw the segmentation polygon
        seg_match = seg_re.search(segmentation_line)
        if seg_match and seg_match.group(1).strip():
            coords = [float(v) for v in seg_match.group(1).split(",") if v.strip()]
            if len(coords) >= 6 and len(coords) % 2 == 0:
                points = []
                for i in range(0, len(coords), 2):
                    # Convert to crop-relative pixel coords
                    px = int((coords[i] - crop_x1) * crop_w / (crop_x2 - crop_x1))
                    py = int((coords[i + 1] - crop_y1) * crop_h / (crop_y2 - crop_y1))
                    points.append([px, py])

                pts = np.array(points, dtype=np.int32)
                mask_layer = crop_array.copy()
                cv2.fillPoly(
                    mask_layer, [pts], (0, 255, 0)
                )  # Green fill for visibility
                cv2.addWeighted(
                    mask_layer,
                    overlay_opacity,
                    crop_array,
                    1.0 - overlay_opacity,
                    0,
                    crop_array,
                )
                cv2.polylines(
                    crop_array, [pts], isClosed=True, color=(0, 200, 0), thickness=2
                )

        # Add label text if present
        label_match = re.search(r"object:\s*(.+?)\s*\|", segmentation_line)
        if label_match:
            label = label_match.group(1).strip()
            cv2.putText(
                crop_array,
                label,
                (rel_x1, max(rel_y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
            )

        return crop_array

    @staticmethod
    def _format_zoomed_verification_results(
        response_text: str,
        target_index: int,
        zoom_desc: str,
        crop_x1: float,
        crop_y1: float,
        crop_x2: float,
        crop_y2: float,
    ) -> str:
        """Format Gemini zoomed verification JSON into readable text."""
        cleaned = response_text
        lines = response_text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() == "```json":
                cleaned = "\n".join(lines[index + 1 :])
                cleaned = cleaned.split("```", maxsplit=1)[0]
                break

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return f"[ZOOMED {zoom_desc} index={target_index}] {response_text}"

        quality = data.get("mask_quality", "unknown")
        confidence = data.get("confidence", 0.5)
        issues = data.get("boundary_issues", [])
        recommendation = data.get("recommendation", "unknown")
        notes = data.get("notes", "")

        status = "✓" if quality in ["excellent", "good"] else "⚠"
        if recommendation in ["reject", "needs_higher_zoom"]:
            status = "✗"

        result_lines = [
            f"{status} [ZOOMED {zoom_desc} index={target_index}] mask_quality={quality}, confidence={confidence:.2f}",
            f"   Crop region: [{crop_x1:.0f}, {crop_y1:.0f}, {crop_x2:.0f}, {crop_y2:.0f}]",
        ]

        if issues:
            result_lines.append(f"   Boundary issues: {', '.join(issues)}")
        if notes:
            result_lines.append(f"   Notes: {notes}")

        result_lines.append(f"   Recommendation: {recommendation}")

        return "\n".join(result_lines)

    def _render_segmentations_on_image(
        self, segmentations: str, overlay_opacity: float = 0.35
    ) -> np.ndarray:
        """Render segmentation polygons onto the full image for visual review.

        Always renders on the full original image because segmentation and
        detection coordinates are in full-image 0-1000 space (even when zoomed).

        Args:
            segmentations: Segmentation text with boxes and polygon points
                in full-image 0-1000 coordinates.
            overlay_opacity: Alpha for mask fill, 0.0 (invisible) to 1.0 (opaque).
        """
        # Always render on full image since coords are full-image-space
        overlay = self._full_image_array.copy()
        render_w, render_h = self._full_width, self._full_height
        seg_re = re.compile(r"segmentation:\s*\[([^\]]*)\]")

        for idx, line in enumerate(segmentations.strip().splitlines()):
            line = line.strip()
            if not line:
                continue

            color = (
                (idx * 67 + 80) % 255,
                (idx * 131 + 40) % 255,
                (idx * 197 + 120) % 255,
            )

            box_match = _BOX_RE.search(line)
            if box_match:
                bx1 = int(float(box_match.group(1)) * render_w / 1000)
                by1 = int(float(box_match.group(2)) * render_h / 1000)
                bx2 = int(float(box_match.group(3)) * render_w / 1000)
                by2 = int(float(box_match.group(4)) * render_h / 1000)
                cv2.rectangle(overlay, (bx1, by1), (bx2, by2), color, 2)

                label_match = re.search(r"object:\s*(.+?)\s*\|", line)
                if label_match:
                    cv2.putText(
                        overlay,
                        label_match.group(1).strip(),
                        (bx1, max(by1 - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        1,
                    )

            seg_match = seg_re.search(line)
            if seg_match and seg_match.group(1).strip():
                coords = [float(v) for v in seg_match.group(1).split(",") if v.strip()]
                if len(coords) >= 6 and len(coords) % 2 == 0:
                    points = []
                    for i in range(0, len(coords), 2):
                        px = int(coords[i] * render_w / 1000)
                        py = int(coords[i + 1] * render_h / 1000)
                        points.append([px, py])
                    pts = np.array(points, dtype=np.int32)
                    mask_layer = overlay.copy()
                    cv2.fillPoly(mask_layer, [pts], color)
                    cv2.addWeighted(
                        mask_layer,
                        overlay_opacity,
                        overlay,
                        1.0 - overlay_opacity,
                        0,
                        overlay,
                    )
                    cv2.polylines(
                        overlay, [pts], isClosed=True, color=color, thickness=2
                    )

        return overlay

    @staticmethod
    def _format_verification_results(response_text: str) -> str:
        """Format Gemini verification JSON into readable text."""
        cleaned = response_text
        lines = response_text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() == "```json":
                cleaned = "\n".join(lines[index + 1 :])
                cleaned = cleaned.split("```", maxsplit=1)[0]
                break

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return response_text

        if not isinstance(data, list):
            data = [data] if data else []

        output_lines = []
        issues_found = 0
        for entry in data:
            label = entry.get("label", "unknown")
            quality = entry.get("mask_quality", "unknown")
            label_correct = entry.get("label_correct", True)
            suggested = entry.get("suggested_label", label)
            notes = entry.get("notes", "")
            box = entry.get("box_2d", [])

            if quality != "good" or not label_correct:
                issues_found += 1

            box_str = f"[{', '.join(str(int(v)) for v in box)}]" if box else "[]"
            status = "OK" if quality == "good" and label_correct else "ISSUE"
            line = f"[{status}] {label} | box: {box_str} | mask: {quality}"
            if not label_correct:
                line += f" | relabel: {suggested}"
            if notes:
                line += f" | {notes}"
            output_lines.append(line)

        summary = (
            f"Verification: {len(data)} objects checked, {issues_found} issues found."
        )
        return summary + "\n" + "\n".join(output_lines)

    def find_missed_objects_with_gemini(self, existing_detections: str) -> str:
        """Check the original image for objects missed by prior detection steps.

        Sends the clean, unmodified original image to Gemini along with a
        list of what has already been detected. Gemini scans for anything
        that was overlooked — small objects, occluded items, edge-of-frame
        objects, or clusters that weren't separated.

        Args:
            existing_detections: Detection/segmentation text listing objects
                already found (from locate_with_gemini, classify_with_gemini,
                or segment_with_sam3).

        Returns:
            Newly found objects in standard detection format, or confirmation
            that nothing was missed.
        """
        self._emit_tool_called(
            "find_missed_objects_with_gemini",
            {
                "existing_detections_preview": self._truncate_text(
                    existing_detections, limit=400
                )
            },
        )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Error: GEMINI_API_KEY not set."

        client = genai.Client(api_key=api_key)
        # Use the clean original image — no masks rendered
        image_bytes = _decode_dspy_image_bytes(self._image)
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        pil_image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

        prompt = GEMINI_FIND_MISSED_OBJECTS_PROMPT.format(
            existing_detections=existing_detections,
        )
        config = genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, pil_image],
                config=config,
            )
        except Exception as exc:
            logger.error(f"Gemini missed-object search failed: {exc}")
            return f"Error: Gemini API call failed: {exc}"

        if response.text is None:
            return "No missed objects found."

        result = self._format_missed_objects(response.text)
        result = _remap_detections_to_full_image(
            result,
            self._crop_x1,
            self._crop_y1,
            self._crop_x2,
            self._crop_y2,
        )
        self._record_stage_predictions(
            "find_missed_objects_with_gemini", result, existing_detections
        )
        logger.debug(f"Gemini missed objects: {result[:200]}")
        return result

    @staticmethod
    def _format_missed_objects(response_text: str) -> str:
        """Format Gemini missed-objects JSON into standard detection format."""
        cleaned = response_text
        lines = response_text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() == "```json":
                cleaned = "\n".join(lines[index + 1 :])
                cleaned = cleaned.split("```", maxsplit=1)[0]
                break

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return response_text

        if not isinstance(data, list):
            data = [data] if data else []

        if not data:
            return "No missed objects found — detection appears complete."

        detection_lines = []
        for det in data:
            label = det.get("label", "unknown")
            box = det.get("box_2d", [0, 0, 0, 0])
            confidence = det.get("confidence", 0.5)
            reason = det.get("reason_missed", "")

            if len(box) == 4:
                try:
                    validate_box(
                        box, BoxFormat.YXYX_NORM_1K, context=f"missed object '{label}'"
                    )
                except BoxValidationError as exc:
                    logger.warning(f"Skipping invalid missed-object detection: {exc}")
                    continue
                y1, x1, y2, x2 = (float(v) for v in box)
                line = f"object: {label} | box: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] | confidence={float(confidence):.2f}"
                if reason:
                    line += f" | missed_reason: {reason}"
                detection_lines.append(line)

        count = len(detection_lines)
        header = f"Found {count} missed object{'s' if count != 1 else ''}:"
        return header + "\n" + "\n".join(detection_lines)

    def execute_code(self, code: str) -> str:
        """Execute a Python snippet with access to the current image and detections.

        Use this when the built-in tools are insufficient and you need custom
        logic — for example:
        - Image preprocessing (edge detection, contrast enhancement, histogram
          equalization) to make objects more visible before re-running detection.
        - Geometric analysis of detections (overlap calculation, spatial
          clustering, aspect ratio filtering).
        - Merging or filtering detection lists with custom rules.
        - Computing statistics about the current annotations.

        Available variables in scope:
          image_array  — current working image as a BGR numpy array (H, W, 3)
          full_image_array — the full original image as a BGR numpy array
          width, height — dimensions of the current working image
          full_width, full_height — dimensions of the full image
          np — numpy
          cv2 — OpenCV
          Image — PIL.Image

        To return a result, assign it to a variable called ``result``.
        If ``result`` is a numpy array, it will be set as the new working
        image (useful for preprocessing).

        Args:
            code: Python code to execute. Must be self-contained.

        Returns:
            The string representation of the ``result`` variable, or stdout
            output, or an error message if execution fails.
        """
        self._emit_tool_called(
            "execute_code",
            {"code_preview": self._truncate_text(code, limit=500)},
        )
        namespace: dict = {
            "image_array": self._image_array.copy(),
            "full_image_array": self._full_image_array.copy(),
            "width": self._width,
            "height": self._height,
            "full_width": self._full_width,
            "full_height": self._full_height,
            "np": np,
            "cv2": cv2,
            "Image": Image,
        }

        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                exec(code, namespace)
        except Exception:
            tb = traceback.format_exc()
            logger.warning(f"execute_code failed:\n{tb}")
            return f"Error executing code:\n{tb}"

        # If result is a numpy image, update the working image
        result = namespace.get("result")
        if isinstance(result, np.ndarray) and result.ndim in (2, 3):
            if result.ndim == 2:
                result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
            self._image_array = result
            self._height, self._width = result.shape[:2]
            self._image = _array_to_dspy_image(result)
            logger.debug(
                f"execute_code updated working image to {self._width}x{self._height}"
            )
            response = f"Working image updated to {self._width}x{self._height}px. Subsequent VLM tools will see the processed image."
            if self._viewer_recorder is not None:
                self._viewer_recorder.record_artifact(
                    image_bgr=self._image_array,
                    artifact_kind="processed_crop",
                    stage_name="execute_code",
                    payload=self._current_crop_payload(),
                    message="Updated working image after execute_code",
                )
            self._emit_nonvisual_tool_result("execute_code", response, input_text=code)
            return response

        stdout_text = stdout_capture.getvalue()
        if result is not None:
            response = str(result)
            self._emit_nonvisual_tool_result("execute_code", response, input_text=code)
            return response
        if stdout_text:
            response = stdout_text.strip()
            self._emit_nonvisual_tool_result("execute_code", response, input_text=code)
            return response
        response = "Code executed successfully (no output)."
        self._emit_nonvisual_tool_result("execute_code", response, input_text=code)
        return response

    def ask_for_input(self, question: str) -> str:
        """Ask a human operator for guidance when confidence is low.

        Use this when you are uncertain about:
        - What category label to assign to an ambiguous object
        - Whether a detected region is a real object or background
        - How to handle overlapping or merged objects
        - Domain-specific classification rules you're unsure about

        Do NOT use this for routine decisions the tools can handle.
        Only escalate when the alternative is guessing with low confidence.

        If no human is available (e.g. during batch processing or DSPy
        optimization), this returns a message saying so — proceed with
        your best judgment in that case.

        Args:
            question: A specific, actionable question for the human.
                Include relevant context (what you've detected so far,
                which object is ambiguous, what the options are).

        Returns:
            The human's answer, or a fallback message if unavailable.
        """
        self._emit_tool_called(
            "ask_for_input",
            {"question": question},
        )
        if self._human_input_fn is None:
            logger.debug(
                f"ask_for_input called but no human available: {question[:120]}"
            )
            response = "No human operator available — proceed with your best judgment. If unsure, use a generic label and flag confidence as low."
            self._emit_nonvisual_tool_result(
                "ask_for_input", response, input_text=question, status="warning"
            )
            return response

        logger.info(f"ask_for_input: {question[:200]}")
        try:
            answer = self._human_input_fn(question)
            logger.info(f"Human responded: {str(answer)[:200]}")
            response = str(answer)
            self._emit_nonvisual_tool_result(
                "ask_for_input", response, input_text=question
            )
            return response
        except Exception as exc:
            logger.warning(f"Human input callback failed: {exc}")
            response = f"Human input unavailable (error: {exc}). Proceed with your best judgment."
            self._emit_nonvisual_tool_result(
                "ask_for_input", response, input_text=question, status="warning"
            )
            return response

    def retrieve_similar_annotations_knn(
        self, annotation_id: int, max_neighbors: int = 5
    ) -> str:
        """Retrieve KNN-similar annotations with rich metadata.

        Uses TurboPuffer ANN lookup over maintained annotation embeddings and
        returns a JSON dump of nearest annotations including distance/proximity,
        class_name, box/image size, camera_id, frame_uri, and other metadata.
        """
        self._emit_tool_called(
            "retrieve_similar_annotations_knn",
            {"annotation_id": annotation_id, "max_neighbors": max_neighbors},
        )
        if self._object_memory_retriever is None:
            return "Object memory unavailable: dataset_name is required and TurboPuffer/PG credentials must be configured."
        if annotation_id <= 0:
            return "annotation_id must be a positive integer."
        result = self._object_memory_retriever.build_knn_dump(
            annotation_id=annotation_id,
            max_neighbors=max_neighbors,
            include_query=False,
        )
        self._record_stage_predictions(
            "retrieve_similar_annotations_knn", result, str(annotation_id)
        )
        return result

    def remember_background_objects(
        self,
        detections: str,
        camera_id: int | None = None,
        reason: str = "background_object",
    ) -> str:
        """Persist likely background detections into object memory for fast future rejection."""
        self._emit_tool_called(
            "remember_background_objects",
            {
                "camera_id": camera_id,
                "reason": reason,
                "detections_preview": self._truncate_text(detections, limit=400),
            },
        )
        if self._dataset_name is None:
            return "Object memory unavailable: dataset_name is required."
        if self._object_memory_background_store is None:
            return "Object memory unavailable: no TurboPuffer or Qdrant backend configured."

        parsed = parse_boxes_from_detections(detections)
        if not parsed:
            return "No valid detections to remember."

        observations: list[BackgroundObjectObservation] = []
        image_h, image_w = self._full_height, self._full_width
        now_ms = int(time.time() * 1000)
        for idx, (label, x1, y1, x2, y2, confidence) in enumerate(parsed):
            px_x1 = max(0, min(image_w, int(round(x1 / 1000.0 * image_w))))
            px_y1 = max(0, min(image_h, int(round(y1 / 1000.0 * image_h))))
            px_x2 = max(0, min(image_w, int(round(x2 / 1000.0 * image_w))))
            px_y2 = max(0, min(image_h, int(round(y2 / 1000.0 * image_h))))
            if px_x2 <= px_x1 or px_y2 <= px_y1:
                continue
            crop = self._full_image_array[px_y1:px_y2, px_x1:px_x2].copy()
            if crop.size == 0:
                continue
            observations.append(
                BackgroundObjectObservation(
                    detection_id=now_ms + idx,
                    class_name=label,
                    confidence=float(confidence),
                    camera_id=camera_id,
                    frame_uri=self._frame_uri,
                    dataset_name=self._dataset_name,
                    box_x1=px_x1,
                    box_y1=px_y1,
                    box_x2=px_x2,
                    box_y2=px_y2,
                    image_width=image_w,
                    image_height=image_h,
                    reason=reason,
                    crop_bgr=crop,
                )
            )

        if not observations:
            return "No valid crop regions to remember."

        try:
            result = self._object_memory_background_store.store_background_observations(
                observations
            )
        except Exception as exc:
            logger.warning(f"Failed to store background memory observations: {exc}")
            return f"Error storing background memory: {exc}"
        response = f"Stored {result['stored']} background object memories via {result['backend']}."
        self._record_stage_predictions(
            "remember_background_objects", response, detections
        )
        return response

    def filter_detections_by_camera_mask(self, detections: str, camera_id: int) -> str:
        """Remove detections whose box center falls outside configured camera masks.

        Uses ``public.masks`` polygons (normalized [0,1]) and the same center-anchor
        filtering strategy as runtime VLM inference.
        """
        self._emit_tool_called(
            "filter_detections_by_camera_mask",
            {
                "camera_id": camera_id,
                "detections_preview": self._truncate_text(detections, limit=400),
            },
        )
        if camera_id <= 0:
            return "camera_id must be a positive integer."

        parsed = parse_boxes_from_detections(detections)
        if not parsed:
            return detections

        try:
            import api.db_gen.masks as masks_db
            from api.services.sqlc_db import run_in_db, run_sync
        except ModuleNotFoundError:
            message = (
                "Error: camera-mask SQL bindings are not available in this standalone repo. "
                "Port the sqlc-generated mask query layer to enable mask filtering."
            )
            logger.warning(message)
            return message

        try:

            async def _query(conn):
                return list(
                    await masks_db.get_masks_for_camera(conn, camera_id=camera_id)
                )

            mask_texts = run_sync(run_in_db(_query))
        except Exception as exc:
            logger.warning(f"Mask lookup failed for camera_id={camera_id}: {exc}")
            return (
                f"Error: failed to load camera masks for camera_id={camera_id}: {exc}"
            )

        if not mask_texts:
            return detections

        masks = [
            _parse_mask_polygon(str(mask_text)) for mask_text in mask_texts if mask_text
        ]
        if not masks:
            return detections

        kept_lines: list[str] = []
        removed = 0
        for line in detections.strip().splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = _BOX_RE.search(stripped)
            if match is None:
                kept_lines.append(stripped)
                continue

            x1 = float(match.group(1))
            y1 = float(match.group(2))
            x2 = float(match.group(3))
            y2 = float(match.group(4))
            center_x = ((x1 + x2) / 2.0) / 1000.0
            center_y = ((y1 + y2) / 2.0) / 1000.0

            if any(_point_in_polygon(center_x, center_y, polygon) for polygon in masks):
                kept_lines.append(stripped)
            else:
                removed += 1

        if not kept_lines:
            result = f"No objects detected after mask filtering (camera_id={camera_id}, removed={removed})."
            self._record_stage_predictions(
                "filter_detections_by_camera_mask", result, detections
            )
            return result

        if removed > 0:
            kept_lines.append(
                f"[Mask filter camera_id={camera_id}: removed {removed} detection(s) outside belt region]"
            )
        result = "\n".join(kept_lines)
        self._record_stage_predictions(
            "filter_detections_by_camera_mask", result, detections
        )
        return result

    def zoom_in(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Crop and zoom into a region. All subsequent tool calls operate on this crop.

        Coordinates are in full-image 0-1000 space (even if already zoomed).
        All detection/classification/verification tools will automatically
        remap their output coordinates back to full-image space, so you can
        freely zoom in and the final annotations remain consistent.

        Call reset_to_full_image when done inspecting this region.

        Args:
            x1: Left edge (0-1000, full-image space)
            y1: Top edge (0-1000, full-image space)
            x2: Right edge (0-1000, full-image space)
            y2: Bottom edge (0-1000, full-image space)

        Returns:
            Confirmation of the new crop region and its pixel dimensions.
        """
        self._emit_tool_called(
            "zoom_in",
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        )
        # Convert to pixel coords on the full image
        px_x1 = max(0, int(float(x1) * self._full_width / 1000))
        px_y1 = max(0, int(float(y1) * self._full_height / 1000))
        px_x2 = min(self._full_width, int(float(x2) * self._full_width / 1000))
        px_y2 = min(self._full_height, int(float(y2) * self._full_height / 1000))

        if px_x2 <= px_x1 or px_y2 <= px_y1:
            logger.warning(
                f"zoom_in degenerate box [{x1},{y1},{x2},{y2}]; keeping current image"
            )
            return (
                f"Invalid crop region [{x1},{y1},{x2},{y2}]. Current image unchanged."
            )

        crop = self._full_image_array[px_y1:px_y2, px_x1:px_x2].copy()
        self._image_array = crop
        self._height, self._width = crop.shape[:2]
        self._image = _array_to_dspy_image(crop)
        self._crop_x1 = float(x1)
        self._crop_y1 = float(y1)
        self._crop_x2 = float(x2)
        self._crop_y2 = float(y2)

        logger.debug(
            f"zoom_in [{x1},{y1},{x2},{y2}] -> crop {self._width}x{self._height}"
        )
        response = (
            f"Zoomed into region [{x1},{y1},{x2},{y2}] — "
            f"crop is {self._width}x{self._height}px. "
            f"All tools now operate on this crop. "
            f"Coordinates in tool outputs are automatically remapped to full-image space. "
            f"Call reset_to_full_image when done with this region."
        )
        if self._viewer_recorder is not None:
            self._viewer_recorder.record_artifact(
                image_bgr=self._image_array,
                artifact_kind="crop",
                stage_name="zoom_in",
                payload=self._current_crop_payload(),
                message="Rendered zoomed crop",
            )
        self._emit_nonvisual_tool_result(
            "zoom_in", response, extra_payload=self._current_crop_payload()
        )
        return response

    def reset_to_full_image(self) -> str:
        """Reset the working image back to the full original image.

        Call this after zoom_in when done inspecting a region, so subsequent
        tools operate on the full scene again.

        Returns:
            Confirmation that the full image is restored.
        """
        self._emit_tool_called("reset_to_full_image")
        self._image = self._full_image
        self._image_array = self._full_image_array
        self._height, self._width = self._full_height, self._full_width
        self._crop_x1 = 0.0
        self._crop_y1 = 0.0
        self._crop_x2 = 1000.0
        self._crop_y2 = 1000.0
        logger.debug("reset_to_full_image — restored full image")
        response = f"Reset to full image ({self._full_width}x{self._full_height}px). All tools now operate on the complete scene."
        if self._viewer_recorder is not None:
            self._viewer_recorder.record_artifact(
                image_bgr=self._full_image_array,
                artifact_kind="raw_frame",
                stage_name="reset_to_full_image",
                payload=self._current_crop_payload(),
                message="Restored full-frame view",
            )
        self._emit_nonvisual_tool_result(
            "reset_to_full_image", response, extra_payload=self._current_crop_payload()
        )
        return response

    def as_tools(self) -> list[dspy.Tool]:
        """Return all tools for dspy.ReAct.

        The recommended workflow is:
        1. locate_with_gemini — find all objects with precise bounding boxes
        2. classify_with_gemini — assign specific labels to the located boxes
        3. segment_with_sam3 — primary/most-frequent iterative tool call for mask generation
           (re-run with positive/negative points plus prompt/class-name experiments)
        4. plan_mask_refinement_with_gemini — choose keep/grabcut/superpixel_snap/cleanup
        5. refine_mask_with_cv2 — refine a suspicious mask deterministically
        6. verify_segmentation_with_gemini — check mask quality after every refinement
        7. find_missed_objects_with_gemini — check clean image for anything overlooked
        8. filter_detections_by_camera_mask — remove detections outside belt mask
        9. retrieve_similar_annotations_knn — inspect nearest annotations and metadata
        10. remember_background_objects — persist likely background detections for future context
        """
        return [
            dspy.Tool(
                func=self.locate_with_gemini,
                name="locate_with_gemini",
                desc=(
                    "STEP 1: Locate all objects with precise bounding boxes using Gemini VLM. "
                    "Gemini produces tight, accurate boxes for every object in the scene. "
                    "Call this first to get bounding box detections, then pass the output "
                    "to classify_with_gemini for specific category labels."
                ),
                arg_desc={
                    "prompt": "What types of objects to look for in the image",
                },
            ),
            dspy.Tool(
                func=self.classify_with_gemini,
                name="classify_with_gemini",
                desc=(
                    "STEP 2: Classify detected objects using Gemini VLM. "
                    "Gemini excels at visual understanding and produces specific, "
                    "descriptive category labels. Pass the bounding box output from "
                    "locate_with_gemini to get accurate classifications. Can also "
                    "identify objects that were missed during localization."
                ),
                arg_desc={
                    "detections": (
                        "Detection text with bounding boxes from locate_with_gemini, or a description of what to look for if starting fresh"
                    ),
                },
            ),
            dspy.Tool(
                func=self.segment_with_sam3,
                name="segment_with_sam3",
                desc=(
                    "STEP 3 (PRIMARY ITERATIVE TOOL): Generate precise instance segmentation masks using SAM3. "
                    "This should be the most common tool call. Re-run this tool multiple times with "
                    "different positive_points/negative_points, positive_prompt/negative_prompt, and "
                    "class_rename_rules to experiment with boundary quality before finalizing annotations. "
                    "Point prompts should be JSON keyed by detection index, e.g. "
                    '{"0": [[512,410]], "1": [[220,330],[225,345]]}.'
                ),
                arg_desc={
                    "detections": "Classified detection text with bounding boxes from classify_with_gemini",
                    "positive_points": "JSON mapping detection index -> positive [x,y] points in full-image 0-1000 space.",
                    "negative_points": "JSON mapping detection index -> negative [x,y] points in full-image 0-1000 space.",
                    "positive_prompt": "Optional positive hint string for experiment tracking.",
                    "negative_prompt": "Optional negative hint string for experiment tracking.",
                    "class_rename_rules": "Optional class remap rules: `old:new,old2:new2`.",
                },
            ),
            dspy.Tool(
                func=self.plan_mask_refinement_with_gemini,
                name="plan_mask_refinement_with_gemini",
                desc=(
                    "STEP 4: Ask Gemini to critique ONE suspicious mask and choose the next "
                    "deterministic operator. Returns JSON with recommended_operator in "
                    "['keep', 'grabcut', 'superpixel_snap', 'cleanup'] plus positive/negative "
                    "points in full-image 0-1000 space. Use this before refine_mask_with_cv2 "
                    "when a SAM3 mask needs correction."
                ),
                arg_desc={
                    "segmentations": "Current segmentation output text.",
                    "target_index": "Index (0-based over segmentation entries only) of the mask to critique.",
                    "zoom_factor": "Zoom level for the critique crop. Default 2.0.",
                    "overlay_opacity": "Mask overlay opacity for the critique render. Default 0.45.",
                    "default_operator": "Fallback operator if Gemini is uncertain. Default grabcut.",
                },
            ),
            dspy.Tool(
                func=self.refine_mask_with_cv2,
                name="refine_mask_with_cv2",
                desc=(
                    "STEP 5: Refine ONE segmentation with deterministic CV operators. "
                    "Use mode='auto' to let Gemini choose between grabcut, superpixel_snap, "
                    "cleanup, or keep. This rewrites just the target segmentation line while "
                    "preserving the rest of the output. After calling this, immediately call "
                    "verify_segmentation_with_gemini or verify_segmentation_zoomed on the updated result."
                ),
                arg_desc={
                    "segmentations": "Current segmentation output text to update.",
                    "target_index": "Index (0-based over segmentation entries only) of the mask to refine.",
                    "mode": "One of auto, keep, grabcut, superpixel_snap, cleanup.",
                    "refinement_plan": "Optional JSON from plan_mask_refinement_with_gemini.",
                    "positive_points": "Optional JSON list of explicit [x,y] positive points in full-image 0-1000 space.",
                    "negative_points": "Optional JSON list of explicit [x,y] negative points in full-image 0-1000 space.",
                    "iterations": "GrabCut iteration count override (default 3).",
                    "superpixel_segments": "Superpixel target count override (default 120).",
                    "cleanup_kernel_size": "Morphology kernel size override (default 5).",
                    "padding_percent": "Extra crop context around the bbox in percent (default 12).",
                },
            ),
            dspy.Tool(
                func=self.verify_segmentation_with_gemini,
                name="verify_segmentation_with_gemini",
                desc=(
                    "STEP 6: Verify segmentation quality using Gemini as a visual critic. "
                    "Renders the SAM3 masks onto the original image and asks Gemini to "
                    "evaluate mask boundary accuracy, label correctness, and missed objects. "
                    "The overlay_opacity parameter controls mask fill transparency — "
                    "use lower values (0.15-0.25) for busy scenes so objects remain visible, "
                    "higher values (0.4-0.5) for simple scenes so mask boundaries are clear. "
                    "If results are ambiguous, call again with a different opacity. "
                    "For detailed boundary inspection of suspicious masks, use verify_segmentation_zoomed."
                ),
                arg_desc={
                    "segmentations": "Segmentation output from segment_with_sam3 with boxes and polygon points",
                    "overlay_opacity": (
                        "Mask fill transparency 0.0-1.0 (default 0.35). "
                        "Lower = more see-through (better for dense scenes), "
                        "higher = more visible masks (better for checking boundaries)"
                    ),
                },
            ),
            dspy.Tool(
                func=self.verify_segmentation_zoomed,
                name="verify_segmentation_zoomed",
                desc=(
                    "DETAILED ZOOM: Verify ONE segmentation at high zoom for boundary precision critique. "
                    "Use this AFTER verify_segmentation_with_gemini flags a suspicious mask. "
                    "Crops to a zoomed-in region around the object so Gemini can inspect "
                    "boundary details invisible at full-image resolution. "
                    "The zoom_factor controls how tight the crop is (2.0 = 2x zoom, 4.0 = 4x zoom). "
                    "Use center_x/y_offset to shift the crop center to specific edges/corners "
                    "(e.g., +30% x, -30% y for top-right corner). Higher overlay_opacity recommended."
                ),
                arg_desc={
                    "segmentations": "Full segmentation output from segment_with_sam3",
                    "target_index": "Index (0-based) of which segmentation to zoom-in and verify in detail",
                    "zoom_factor": (
                        "Zoom level relative to bbox size. 1.0 = no zoom (bbox size), "
                        "2.0 = 2x zoom (half bbox), 4.0 = 4x zoom (quarter bbox). Higher = more detail."
                    ),
                    "center_x_offset": (
                        "Horizontal offset from bbox center as % of bbox width. "
                        "-50 = left edge, 0 = center (default), 50 = right edge. "
                        "Use positive to shift right, negative to shift left."
                    ),
                    "center_y_offset": (
                        "Vertical offset from bbox center as % of bbox height. "
                        "-50 = top edge, 0 = center (default), 50 = bottom edge. "
                        "Use positive to shift down, negative to shift up."
                    ),
                    "min_context_percent": (
                        "Minimum % of bbox to include even at high zoom. Default 15%. Prevents overly tight crops that lose all context."
                    ),
                    "overlay_opacity": "Mask fill transparency. Default 0.45 (higher than full-image since zoomed)",
                },
            ),
            dspy.Tool(
                func=self.find_missed_objects_with_gemini,
                name="find_missed_objects_with_gemini",
                desc=(
                    "STEP 7: Check for missed objects using the clean original image. "
                    "Sends the unmodified image (no masks) to Gemini with a list of "
                    "what was already detected, and asks it to find anything overlooked — "
                    "small objects, occluded items, edge-of-frame objects, or unseparated "
                    "clusters. Any newly found objects can be fed back into "
                    "segment_with_sam3 to get their masks."
                ),
                arg_desc={
                    "existing_detections": (
                        "Text listing all objects detected so far (from any prior detection or segmentation step)"
                    ),
                },
            ),
            dspy.Tool(
                func=self.filter_detections_by_camera_mask,
                name="filter_detections_by_camera_mask",
                desc=(
                    "Filter detections against camera belt masks from the database. "
                    "Removes detections whose bounding-box center falls outside all "
                    "configured mask polygons for the given camera_id."
                ),
                arg_desc={
                    "detections": "Detection text with box coordinates in [0,1000] space.",
                    "camera_id": "Camera ID whose masks should be applied.",
                },
            ),
            dspy.Tool(
                func=self.retrieve_similar_annotations_knn,
                name="retrieve_similar_annotations_knn",
                desc=(
                    "Retrieve the most similar annotation instances via TurboPuffer KNN "
                    "using maintained DINOv2-style annotation embeddings. Returns full "
                    "JSON metadata for each neighbor: proximity score, class_name, box/image "
                    "dimensions, camera_id, frame_uri, and more."
                ),
                arg_desc={
                    "annotation_id": "Reference annotation_id to search neighbors for.",
                    "max_neighbors": "How many neighbors to return (default 5).",
                },
            ),
            dspy.Tool(
                func=self.remember_background_objects,
                name="remember_background_objects",
                desc=(
                    "Store detections that are likely background / non-target objects into object memory. "
                    "Generates DINOv2 embeddings for each detection crop and persists to TurboPuffer when available, "
                    "otherwise local Qdrant fallback."
                ),
                arg_desc={
                    "detections": "Detection text with boxes in [0,1000] space for objects to remember as background.",
                    "camera_id": "Optional camera ID for metadata.",
                    "reason": "Optional reason tag (default background_object).",
                },
            ),
            dspy.Tool(
                func=self.zoom_in,
                name="zoom_in",
                desc=(
                    "Zoom into a region so ALL subsequent tool calls (locate, classify, "
                    "segment, verify, find_missed) operate on that crop at higher "
                    "resolution. Use this for dense or small-object regions. "
                    "Coordinates are in full-image 0-1000 space. Output coordinates "
                    "from tools are automatically remapped to full-image space. "
                    "Call reset_to_full_image when done with the region."
                ),
                arg_desc={
                    "x1": "Left edge of the region (0-1000, full-image space)",
                    "y1": "Top edge of the region (0-1000, full-image space)",
                    "x2": "Right edge of the region (0-1000, full-image space)",
                    "y2": "Bottom edge of the region (0-1000, full-image space)",
                },
            ),
            dspy.Tool(
                func=self.reset_to_full_image,
                name="reset_to_full_image",
                desc=(
                    "Reset the working image back to the full original image after "
                    "a zoom_in. Call this when done inspecting a cropped region so "
                    "subsequent tools operate on the complete scene again."
                ),
                arg_desc={},
            ),
            dspy.Tool(
                func=self.execute_code,
                name="execute_code",
                desc=(
                    "Execute a Python snippet with access to the current image as a "
                    "numpy array. Use when built-in tools are insufficient — e.g. "
                    "image preprocessing (edge detection, contrast enhancement), "
                    "geometric analysis of detections, merging/filtering detection "
                    "lists with custom rules, or computing annotation statistics. "
                    "Available variables: image_array, full_image_array, width, height, "
                    "np, cv2, Image (PIL). Assign output to 'result'. If result is a "
                    "numpy array it becomes the new working image."
                ),
                arg_desc={
                    "code": "Self-contained Python code. Assign output to 'result'.",
                },
            ),
            dspy.Tool(
                func=self.ask_for_input,
                name="ask_for_input",
                desc=(
                    "Ask a human operator for guidance when you are uncertain. "
                    "Use this ONLY when confidence is low and the other tools cannot "
                    "resolve the ambiguity — e.g. unclear object identity, domain-specific "
                    "labeling rules, or whether something is an object or background. "
                    "Include context in your question (what you see, what the options are). "
                    "If no human is available, you'll be told to proceed with best judgment."
                ),
                arg_desc={
                    "question": (
                        "A specific question for the human. Include context: what you've detected, which object is ambiguous, what the options are."
                    ),
                },
            ),
        ]
