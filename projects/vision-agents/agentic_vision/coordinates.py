"""Coordinate validation and conversion for bounding boxes.

The codebase uses several coordinate formats that are easily confused:

- XYXY_PIXEL:   [x1, y1, x2, y2] in absolute pixel coordinates.
                 Used for ground truth from the database and annotation files.

- XYXY_NORM_1K: [x1, y1, x2, y2] normalised to [0, 1000].
                 Used internally by the active-learning segmenter after
                 converting from Gemini output.

- YXYX_NORM_1K: [y1, x1, y2, x2] normalised to [0, 1000].
                 Raw format returned by the Gemini VLM API (box_2d).

- XYWH_NORM_01: [x, y, w, h] normalised to [0, 1].
                 Required by FiftyOne's Detection.bounding_box.

This module provides:
- A ``BBox`` dataclass that carries its format and validates invariants.
- Conversion functions between all formats.
- A ``validate_box`` helper for validating raw boxes without constructing BBox.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from loguru import logger


class BoxFormat(Enum):
    """Enumerate the bounding-box coordinate formats used in this codebase."""

    XYXY_PIXEL = "xyxy_pixel"
    XYXY_NORM_1K = "xyxy_norm_1k"
    YXYX_NORM_1K = "yxyx_norm_1k"
    XYWH_NORM_01 = "xywh_norm_01"
    XYXY_ANY = "xyxy_any"


class BoxValidationError(ValueError):
    """Raised when a bounding box fails validation."""


def validate_box(
    box: Any,
    fmt: BoxFormat,
    *,
    context: str = "",
    image_width: int | None = None,
    image_height: int | None = None,
) -> list[float]:
    """Validate a raw bounding box and return it as a list of 4 floats.

    Args:
        box: Raw box value — must be a sequence of 4 numeric values.
        fmt: The coordinate format of *box*.
        context: Optional human-readable label for error messages (e.g.
            "image 5 GT annotation 2").
        image_width: Optional pixel width — used for pixel-format bounds
            checking when available.
        image_height: Optional pixel height — used for pixel-format bounds
            checking when available.

    Returns:
        A list of 4 floats representing the validated box.

    Raises:
        BoxValidationError: If the box is malformed or violates invariants.
    """
    prefix = (
        f"Box validation error ({context}): " if context else "Box validation error: "
    )

    if not isinstance(box, (list, tuple)):
        raise BoxValidationError(
            f"{prefix}expected a sequence of 4 numbers, got {type(box).__name__}"
        )

    if len(box) != 4:
        raise BoxValidationError(f"{prefix}expected 4 values, got {len(box)}")

    try:
        values = [float(v) for v in box]
    except (TypeError, ValueError) as exc:
        raise BoxValidationError(f"{prefix}non-numeric values: {exc}") from exc

    if any(v != v for v in values):  # NaN check
        raise BoxValidationError(f"{prefix}NaN detected in box {values}")

    if any(abs(v) == float("inf") for v in values):
        raise BoxValidationError(f"{prefix}Inf detected in box {values}")

    v0, v1, v2, v3 = values

    if fmt == BoxFormat.XYXY_PIXEL:
        _validate_xyxy_pixel(v0, v1, v2, v3, prefix, image_width, image_height)
    elif fmt == BoxFormat.XYXY_NORM_1K:
        _validate_xyxy_norm_1k(v0, v1, v2, v3, prefix)
    elif fmt == BoxFormat.YXYX_NORM_1K:
        _validate_yxyx_norm_1k(v0, v1, v2, v3, prefix)
    elif fmt == BoxFormat.XYWH_NORM_01:
        _validate_xywh_norm_01(v0, v1, v2, v3, prefix)
    elif fmt == BoxFormat.XYXY_ANY:
        _validate_xyxy_any(v0, v1, v2, v3, prefix)

    return values


def _validate_xyxy_pixel(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    prefix: str,
    width: int | None,
    height: int | None,
) -> None:
    if x1 < 0 or y1 < 0:
        raise BoxValidationError(
            f"{prefix}negative origin in XYXY_PIXEL: [{x1}, {y1}, {x2}, {y2}]"
        )
    if x2 <= x1:
        raise BoxValidationError(f"{prefix}x2 <= x1 in XYXY_PIXEL: x1={x1}, x2={x2}")
    if y2 <= y1:
        raise BoxValidationError(f"{prefix}y2 <= y1 in XYXY_PIXEL: y1={y1}, y2={y2}")
    if width is not None and x2 > width:
        raise BoxValidationError(f"{prefix}x2={x2} exceeds image width={width}")
    if height is not None and y2 > height:
        raise BoxValidationError(f"{prefix}y2={y2} exceeds image height={height}")


def _validate_xyxy_norm_1k(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    prefix: str,
) -> None:
    for name, val in [("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)]:
        if val < 0 or val > 1000:
            raise BoxValidationError(
                f"{prefix}{name}={val} out of [0, 1000] range in XYXY_NORM_1K"
            )
    if x2 <= x1:
        raise BoxValidationError(f"{prefix}x2 <= x1 in XYXY_NORM_1K: x1={x1}, x2={x2}")
    if y2 <= y1:
        raise BoxValidationError(f"{prefix}y2 <= y1 in XYXY_NORM_1K: y1={y1}, y2={y2}")


def _validate_yxyx_norm_1k(
    y1: float,
    x1: float,
    y2: float,
    x2: float,
    prefix: str,
) -> None:
    for name, val in [("y1", y1), ("x1", x1), ("y2", y2), ("x2", x2)]:
        if val < 0 or val > 1000:
            raise BoxValidationError(
                f"{prefix}{name}={val} out of [0, 1000] range in YXYX_NORM_1K"
            )
    if y2 <= y1:
        raise BoxValidationError(f"{prefix}y2 <= y1 in YXYX_NORM_1K: y1={y1}, y2={y2}")
    if x2 <= x1:
        raise BoxValidationError(f"{prefix}x2 <= x1 in YXYX_NORM_1K: x1={x1}, x2={x2}")


def _validate_xywh_norm_01(
    x: float,
    y: float,
    w: float,
    h: float,
    prefix: str,
) -> None:
    if x < 0 or y < 0:
        raise BoxValidationError(
            f"{prefix}negative origin in XYWH_NORM_01: x={x}, y={y}"
        )
    if w <= 0 or h <= 0:
        raise BoxValidationError(
            f"{prefix}non-positive size in XYWH_NORM_01: w={w}, h={h}"
        )
    if x + w > 1.0 + 1e-6:
        raise BoxValidationError(f"{prefix}x+w={x + w:.6f} exceeds 1.0 in XYWH_NORM_01")
    if y + h > 1.0 + 1e-6:
        raise BoxValidationError(f"{prefix}y+h={y + h:.6f} exceeds 1.0 in XYWH_NORM_01")


def _validate_xyxy_any(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    prefix: str,
) -> None:
    if x2 <= x1:
        raise BoxValidationError(f"{prefix}x2 <= x1 in XYXY_ANY: x1={x1}, x2={x2}")
    if y2 <= y1:
        raise BoxValidationError(f"{prefix}y2 <= y1 in XYXY_ANY: y1={y1}, y2={y2}")


def convert_box(
    box: Any,
    source_fmt: BoxFormat,
    target_fmt: BoxFormat,
    *,
    image_width: int | None = None,
    image_height: int | None = None,
    context: str = "",
) -> list[float]:
    """Validate and convert a bounding box from one format to another.

    Pixel formats require ``image_width`` and ``image_height`` for conversion
    to normalised formats.

    Args:
        box: Raw box value.
        source_fmt: Format of the input box.
        target_fmt: Desired output format.
        image_width: Pixel width of the source image (required for
            pixel-to-normalised conversions).
        image_height: Pixel height of the source image (required for
            pixel-to-normalised conversions).
        context: Optional label for error messages.

    Returns:
        A list of 4 floats in *target_fmt*.
    """
    values = validate_box(
        box,
        source_fmt,
        context=context,
        image_width=image_width,
        image_height=image_height,
    )

    if source_fmt == target_fmt:
        return values

    xyxy = _to_xyxy(values, source_fmt, image_width, image_height, context)
    return _from_xyxy(xyxy, target_fmt, image_width, image_height, context)


def _to_xyxy(
    box: list[float],
    fmt: BoxFormat,
    width: int | None,
    height: int | None,
    context: str,
) -> tuple[float, float, float, float]:
    """Convert any format to (x1, y1, x2, y2) normalised [0, 1]."""
    prefix = (
        f"Box conversion error ({context}): " if context else "Box conversion error: "
    )

    if fmt == BoxFormat.XYXY_NORM_1K:
        return box[0] / 1000.0, box[1] / 1000.0, box[2] / 1000.0, box[3] / 1000.0

    if fmt == BoxFormat.YXYX_NORM_1K:
        y1, x1, y2, x2 = box
        return x1 / 1000.0, y1 / 1000.0, x2 / 1000.0, y2 / 1000.0

    if fmt == BoxFormat.XYXY_PIXEL:
        if width is None or height is None:
            raise BoxValidationError(
                f"{prefix}image_width and image_height required for pixel conversion"
            )
        return box[0] / width, box[1] / height, box[2] / width, box[3] / height

    if fmt == BoxFormat.XYWH_NORM_01:
        x, y, w, h = box
        return x, y, x + w, y + h

    raise BoxValidationError(f"{prefix}unknown source format: {fmt}")


def _from_xyxy(
    xyxy: tuple[float, float, float, float],
    fmt: BoxFormat,
    width: int | None,
    height: int | None,
    context: str,
) -> list[float]:
    """Convert (x1, y1, x2, y2) normalised [0, 1] to the target format."""
    prefix = (
        f"Box conversion error ({context}): " if context else "Box conversion error: "
    )
    x1, y1, x2, y2 = xyxy

    if fmt == BoxFormat.XYXY_NORM_1K:
        return [x1 * 1000, y1 * 1000, x2 * 1000, y2 * 1000]

    if fmt == BoxFormat.YXYX_NORM_1K:
        return [y1 * 1000, x1 * 1000, y2 * 1000, x2 * 1000]

    if fmt == BoxFormat.XYXY_PIXEL:
        if width is None or height is None:
            raise BoxValidationError(
                f"{prefix}image_width and image_height required for pixel conversion"
            )
        return [x1 * width, y1 * height, x2 * width, y2 * height]

    if fmt == BoxFormat.XYWH_NORM_01:
        return [x1, y1, x2 - x1, y2 - y1]

    raise BoxValidationError(f"{prefix}unknown target format: {fmt}")


def validate_annotation_boxes(
    annotations: list[dict[str, Any]],
    fmt: BoxFormat,
    *,
    image_width: int | None = None,
    image_height: int | None = None,
    context: str = "",
) -> list[dict[str, Any]]:
    """Validate the ``box`` key of every annotation in a list.

    Invalid boxes are logged as warnings and excluded from the returned list.

    Args:
        annotations: List of dicts each containing a ``box`` (or ``bbox``) key.
        fmt: Expected coordinate format of the boxes.
        image_width: Optional pixel width for pixel-format validation.
        image_height: Optional pixel height for pixel-format validation.
        context: Optional label for error messages.

    Returns:
        A filtered copy of *annotations* containing only valid entries.
    """
    valid: list[dict[str, Any]] = []
    for idx, ann in enumerate(annotations):
        box = ann.get("box", ann.get("bbox"))
        ann_context = (
            f"{context} annotation[{idx}]" if context else f"annotation[{idx}]"
        )
        try:
            validated = validate_box(
                box,
                fmt,
                context=ann_context,
                image_width=image_width,
                image_height=image_height,
            )
            ann = dict(ann)
            ann["box"] = validated
            valid.append(ann)
        except BoxValidationError as exc:
            logger.warning(f"Dropping {ann_context}: {exc}")
    return valid


def validate_predictions_boxes(
    predictions: list[dict[str, Any]],
    fmt: BoxFormat,
    *,
    context: str = "",
) -> list[dict[str, Any]]:
    """Validate the ``box`` key of every prediction in a list.

    Invalid boxes are logged as warnings and excluded from the returned list.

    Args:
        predictions: List of dicts each containing a ``box`` key.
        fmt: Expected coordinate format of the boxes.
        context: Optional label for error messages.

    Returns:
        A filtered copy of *predictions* containing only valid entries.
    """
    valid: list[dict[str, Any]] = []
    for idx, pred in enumerate(predictions):
        box = pred.get("box")
        pred_context = (
            f"{context} prediction[{idx}]" if context else f"prediction[{idx}]"
        )
        try:
            validated = validate_box(box, fmt, context=pred_context)
            pred = dict(pred)
            pred["box"] = validated
            valid.append(pred)
        except BoxValidationError as exc:
            logger.warning(f"Dropping {pred_context}: {exc}")
    return valid
