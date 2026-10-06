"""Metrics computation for active learning experiments.

Provides comprehensive evaluation of both detection and segmentation quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger

from agentic_vision.coordinates import BoxFormat, BoxValidationError, validate_box


@dataclass
class SegmentationMetrics:
    """Comprehensive metrics for instance segmentation evaluation.

    Combines detection metrics (did we find the objects) with
    segmentation metrics (how accurate are the masks).
    """

    # Detection metrics (object localization)
    detection_precision: float = 0.0  # TP / (TP + FP)
    detection_recall: float = 0.0  # TP / (TP + FN)
    detection_f1: float = 0.0  # 2 * (P * R) / (P + R)

    # Counts for detection
    num_predictions: int = 0
    num_ground_truth: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    # Segmentation/mask metrics
    mean_iou: float = 0.0  # Average IoU of matched masks
    mask_precision: float = 0.0  # % of predicted mask overlapping GT
    mask_recall: float = 0.0  # % of GT mask covered by prediction
    boundary_f1: float = 0.0  # Boundary pixel accuracy

    # Per-class breakdown
    per_class_detection: dict[str, dict[str, float]] = field(default_factory=dict)
    per_class_segmentation: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            # Detection
            "detection_precision": self.detection_precision,
            "detection_recall": self.detection_recall,
            "detection_f1": self.detection_f1,
            # Counts
            "num_predictions": self.num_predictions,
            "num_ground_truth": self.num_ground_truth,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            # Segmentation
            "mean_iou": self.mean_iou,
            "mask_precision": self.mask_precision,
            "mask_recall": self.mask_recall,
            "boundary_f1": self.boundary_f1,
            # Per-class
            "per_class_detection": self.per_class_detection,
            "per_class_segmentation": self.per_class_segmentation,
        }

    def get_primary_metric(self, metric_name: str = "detection_f1") -> float:
        """Get a specific metric by name.

        Common choices:
        - 'detection_f1': Overall detection quality (default)
        - 'mean_iou': Mask quality
        - 'detection_recall': Coverage of objects
        - 'combined': Weighted combination
        """
        if metric_name == "combined":
            # Weight detection and segmentation equally
            return 0.5 * self.detection_f1 + 0.5 * self.mean_iou

        return getattr(self, metric_name, 0.0)

    @property
    def summary(self) -> str:
        """Human-readable summary of key metrics."""
        return (
            f"Det: P={self.detection_precision:.2f}, R={self.detection_recall:.2f}, F1={self.detection_f1:.2f} | "
            f"Seg: mIoU={self.mean_iou:.2f} | "
            f"Counts: {self.true_positives}TP/{self.false_positives}FP/{self.false_negatives}FN"
        )


def calculate_segmentation_metrics(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    iou_threshold: float = 0.5,
) -> SegmentationMetrics:
    """Calculate comprehensive segmentation metrics.

    Args:
        predictions: List of predicted objects with 'label', 'box', 'segmentation'
        ground_truth: List of ground truth objects with same keys
        iou_threshold: IoU threshold for considering a detection correct

    Returns:
        SegmentationMetrics with detection and mask metrics
    """
    metrics = SegmentationMetrics()

    metrics.num_predictions = len(predictions)
    metrics.num_ground_truth = len(ground_truth)

    if not predictions or not ground_truth:
        # Handle edge cases
        if not predictions and ground_truth:
            metrics.false_negatives = len(ground_truth)
            metrics.detection_recall = 0.0
        elif predictions and not ground_truth:
            metrics.false_positives = len(predictions)
            metrics.detection_precision = 0.0
        return metrics

    # Match predictions to ground truth
    # Use Hungarian algorithm or greedy matching
    iou_matrix = np.zeros((len(predictions), len(ground_truth)))

    for i, pred in enumerate(predictions):
        pred_box = pred.get("box", pred.get("bbox", [0, 0, 0, 0]))
        for j, gt in enumerate(ground_truth):
            gt_box = gt.get("box", gt.get("bbox", [0, 0, 0, 0]))
            iou_matrix[i, j] = _calculate_box_iou(pred_box, gt_box)

    # Greedy matching: assign each pred to best GT, then filter by threshold
    matched_gt_indices = set()
    matched_pred_indices = set()
    matched_ious = []

    # Sort by IoU descending
    flat_indices = np.argsort(iou_matrix.flatten())[::-1]

    for flat_idx in flat_indices:
        i = flat_idx // len(ground_truth)
        j = flat_idx % len(ground_truth)

        if i in matched_pred_indices or j in matched_gt_indices:
            continue

        iou = iou_matrix[i, j]
        if iou >= iou_threshold:
            matched_pred_indices.add(i)
            matched_gt_indices.add(j)
            matched_ious.append(iou)

    # Calculate detection metrics
    metrics.true_positives = len(matched_pred_indices)
    metrics.false_positives = len(predictions) - metrics.true_positives
    metrics.false_negatives = len(ground_truth) - len(matched_gt_indices)

    metrics.detection_precision = (
        metrics.true_positives / metrics.num_predictions
        if metrics.num_predictions > 0
        else 0.0
    )
    metrics.detection_recall = (
        metrics.true_positives / metrics.num_ground_truth
        if metrics.num_ground_truth > 0
        else 0.0
    )

    if metrics.detection_precision + metrics.detection_recall > 0:
        metrics.detection_f1 = (
            2
            * metrics.detection_precision
            * metrics.detection_recall
            / (metrics.detection_precision + metrics.detection_recall)
        )

    # Calculate segmentation metrics from matched pairs
    if matched_ious:
        metrics.mean_iou = np.mean(matched_ious)

        # Calculate mask precision/recall if we have actual polygons
        mask_precisions = []
        mask_recalls = []

        for i, j in zip(matched_pred_indices, matched_gt_indices):
            pred_seg = predictions[i].get("segmentation", [])
            gt_seg = ground_truth[j].get("segmentation", [])

            if pred_seg and gt_seg:
                # Calculate mask IoU (more accurate than box IoU)
                mask_iou = _calculate_mask_iou(pred_seg, gt_seg)

                # Precision: predicted mask overlapping GT
                # Recall: GT mask covered by prediction
                # These are approximations without pixel-level masks
                mask_precisions.append(mask_iou)
                mask_recalls.append(mask_iou)

        if mask_precisions:
            metrics.mask_precision = np.mean(mask_precisions)
            metrics.mask_recall = np.mean(mask_recalls)
            # Boundary F1 approximation
            metrics.boundary_f1 = (
                2
                * metrics.mask_precision
                * metrics.mask_recall
                / (metrics.mask_precision + metrics.mask_recall + 1e-8)
            )

    # Calculate per-class metrics
    metrics.per_class_detection = _calculate_per_class_detection(
        predictions, ground_truth, matched_pred_indices, matched_gt_indices
    )

    return metrics


def _calculate_box_iou(
    box_a: list[float] | tuple[float, ...],
    box_b: list[float] | tuple[float, ...],
) -> float:
    """Calculate IoU between two bounding boxes.

    Both boxes must be in XYXY format (pixel or normalised) and in the
    same coordinate space.  Degenerate or inverted boxes return 0.0
    with a warning.
    """
    try:
        validate_box(box_a, BoxFormat.XYXY_ANY, context="IoU box_a")
    except BoxValidationError:
        logger.warning(f"Skipping degenerate box_a {box_a} in IoU calculation")
        return 0.0

    try:
        validate_box(box_b, BoxFormat.XYXY_ANY, context="IoU box_b")
    except BoxValidationError:
        logger.warning(f"Skipping degenerate box_b {box_b} in IoU calculation")
        return 0.0
    """Calculate IoU between two bounding boxes."""
    x1_a, y1_a, x2_a, y2_a = box_a
    x1_b, y1_b, x2_b, y2_b = box_b

    # Intersection
    xi1 = max(x1_a, x1_b)
    yi1 = max(y1_a, y1_b)
    xi2 = min(x2_a, x2_b)
    yi2 = min(y2_a, y2_b)

    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)

    # Union
    box_a_area = (x2_a - x1_a) * (y2_a - y1_a)
    box_b_area = (x2_b - x1_b) * (y2_b - y1_b)
    union_area = box_a_area + box_b_area - inter_area

    return inter_area / union_area if union_area > 0 else 0.0


def _calculate_mask_iou(
    poly_a: list[tuple[float, float]],
    poly_b: list[tuple[float, float]],
) -> float:
    """Calculate IoU between two polygons.

    Simplified implementation using bounding boxes.
    For accurate mask IoU, use shapely or rasterize to pixels.
    """

    def bbox_from_poly(poly):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return [min(xs), min(ys), max(xs), max(ys)]

    # Use bounding box as proxy (conservative estimate)
    return _calculate_box_iou(bbox_from_poly(poly_a), bbox_from_poly(poly_b))


def _calculate_per_class_detection(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    matched_pred_indices: set[int],
    matched_gt_indices: set[int],
) -> dict[str, dict[str, float]]:
    """Calculate detection metrics per class."""
    per_class: dict[str, dict[str, Any]] = {}

    # Count predictions by class
    for i, pred in enumerate(predictions):
        label = pred.get("label", pred.get("class_name", "unknown"))
        if label not in per_class:
            per_class[label] = {"tp": 0, "fp": 0, "fn": 0}

        if i in matched_pred_indices:
            per_class[label]["tp"] += 1
        else:
            per_class[label]["fp"] += 1

    # Count ground truth by class (for FN)
    for j, gt in enumerate(ground_truth):
        label = gt.get("label", gt.get("class_name", "unknown"))
        if label not in per_class:
            per_class[label] = {"tp": 0, "fp": 0, "fn": 0}

        if j not in matched_gt_indices:
            per_class[label]["fn"] += 1

    # Calculate precision/recall per class
    result: dict[str, dict[str, float]] = {}
    for label, counts in per_class.items():
        tp = counts["tp"]
        fp = counts["fp"]
        fn = counts["fn"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        result[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    return result


def aggregate_metrics(metrics_list: list[SegmentationMetrics]) -> SegmentationMetrics:
    """Aggregate metrics across multiple images.

    Computes macro-average across all images.
    """
    if not metrics_list:
        return SegmentationMetrics()

    aggregated = SegmentationMetrics()

    # Average detection metrics
    aggregated.detection_precision = np.mean(
        [m.detection_precision for m in metrics_list]
    )
    aggregated.detection_recall = np.mean([m.detection_recall for m in metrics_list])
    aggregated.detection_f1 = np.mean([m.detection_f1 for m in metrics_list])

    # Average segmentation metrics
    aggregated.mean_iou = np.mean([m.mean_iou for m in metrics_list])
    aggregated.mask_precision = np.mean([m.mask_precision for m in metrics_list])
    aggregated.mask_recall = np.mean([m.mask_recall for m in metrics_list])
    aggregated.boundary_f1 = np.mean([m.boundary_f1 for m in metrics_list])

    # Sum counts
    aggregated.num_predictions = sum(m.num_predictions for m in metrics_list)
    aggregated.num_ground_truth = sum(m.num_ground_truth for m in metrics_list)
    aggregated.true_positives = sum(m.true_positives for m in metrics_list)
    aggregated.false_positives = sum(m.false_positives for m in metrics_list)
    aggregated.false_negatives = sum(m.false_negatives for m in metrics_list)

    return aggregated
