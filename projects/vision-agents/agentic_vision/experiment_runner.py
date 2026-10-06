"""Experiment runner for active learning instance segmentation.

Runs experiments to measure annotation efficiency: how few annotations
are needed to achieve target segmentation performance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import dspy
from loguru import logger

from agentic_vision.active_learning import AnnotationStrategy
from agentic_vision.active_learning_programme import (
    ActiveLearningResult,
    ActiveLearningSegmenter,
    SegmentationPrediction,
)
from agentic_vision.coordinates import BoxFormat, BoxValidationError, validate_box
from agentic_vision.metrics import (
    SegmentationMetrics,
    aggregate_metrics,
    calculate_segmentation_metrics,
)


@dataclass
class ExperimentConfig:
    """Configuration for an active learning experiment."""

    name: str
    strategy: AnnotationStrategy
    annotation_budget: int = 50
    bootstrap_examples: int = 0
    uncertainty_threshold: float = 0.7

    # Metric to optimize for
    primary_metric: str = "detection_f1"  # 'detection_f1', 'mean_iou', 'combined'

    # Stopping criteria
    target_performance: float | None = None  # Stop when reaching this metric value
    performance_plateau_window: int = 5  # Stop if no improvement for N steps
    performance_plateau_threshold: float = 0.01  # Min improvement to continue

    # Secondary metrics to track (always recorded)
    track_metrics: list[str] = field(
        default_factory=lambda: [
            "detection_f1",
            "detection_precision",
            "detection_recall",
            "mean_iou",
            "mask_precision",
            "mask_recall",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "strategy": self.strategy.value,
            "annotation_budget": self.annotation_budget,
            "bootstrap_examples": self.bootstrap_examples,
            "uncertainty_threshold": self.uncertainty_threshold,
            "primary_metric": self.primary_metric,
            "target_performance": self.target_performance,
            "track_metrics": self.track_metrics,
        }


@dataclass
class ExperimentResult:
    """Result of running an experiment configuration."""

    config: ExperimentConfig

    # X-Y data for efficiency curve (primary metric)
    annotations_used: list[int] = field(default_factory=list)
    primary_metric_scores: list[float] = field(default_factory=list)

    # All metrics over time
    metrics_history: list[dict[str, float]] = field(default_factory=list)

    # Detailed per-step data
    step_details: list[dict[str, Any]] = field(default_factory=list)

    # Final state
    final_metrics: dict[str, float] = field(default_factory=dict)
    total_annotations_used: int = 0
    stopped_reason: str = ""  # "budget_exhausted", "target_reached", "plateau"

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "annotations_used": self.annotations_used,
            "primary_metric_scores": self.primary_metric_scores,
            "metrics_history": self.metrics_history,
            "step_details": self.step_details,  # Include predictions for FiftyOne
            "final_metrics": self.final_metrics,
            "total_annotations_used": self.total_annotations_used,
            "stopped_reason": self.stopped_reason,
        }

    def get_metric_curve(self, metric_name: str) -> list[float]:
        """Get the curve for a specific metric."""
        return [m.get(metric_name, 0.0) for m in self.metrics_history]


class GroundTruthSimulator:
    """Simulates human annotations using ground truth data.

    This allows running experiments without actual human input,
    using existing annotations as the "oracle" that provides
    perfect labels when requested.
    """

    def __init__(
        self,
        ground_truth_annotations: list[dict[str, Any]],
        iou_threshold: float = 0.5,
    ):
        """Initialize with ground truth annotations.

        Args:
            ground_truth_annotations: List of ground truth objects with
                keys: label, box [x1, y1, x2, y2], segmentation [list of points]
            iou_threshold: IoU threshold for matching predictions to ground truth
        """
        self.ground_truth = ground_truth_annotations
        self.iou_threshold = iou_threshold
        self._match_cache: dict[int, int | None] = {}  # pred_idx -> gt_idx

        self._validate_ground_truth()

    def _validate_ground_truth(self) -> None:
        """Validate ground truth boxes and drop invalid entries."""
        valid: list[dict[str, Any]] = []
        for idx, gt in enumerate(self.ground_truth):
            gt_box = gt.get("box", gt.get("bbox"))
            try:
                validate_box(gt_box, BoxFormat.XYXY_ANY, context=f"GT[{idx}]")
                valid.append(gt)
            except BoxValidationError as exc:
                logger.warning(f"Dropping {exc}")
        dropped = len(self.ground_truth) - len(valid)
        if dropped:
            logger.warning(
                f"GroundTruthSimulator: dropped {dropped} invalid GT annotation(s)"
            )
            self.ground_truth = valid

    def find_match(
        self,
        prediction: SegmentationPrediction,
        prediction_index: int,
    ) -> dict[str, Any] | None:
        """Find the best matching ground truth annotation."""

        # Check cache
        if prediction_index in self._match_cache:
            gt_idx = self._match_cache[prediction_index]
            if gt_idx is not None:
                return self.ground_truth[gt_idx]
            return None

        # Find best match by IoU
        best_iou = 0.0
        best_match = None
        best_idx = None

        pred_box = prediction.box
        try:
            validate_box(
                pred_box, BoxFormat.XYXY_ANY, context=f"prediction[{prediction_index}]"
            )
        except BoxValidationError as exc:
            logger.warning(f"Cannot match prediction: {exc}")
            self._match_cache[prediction_index] = None
            return None

        for idx, gt in enumerate(self.ground_truth):
            gt_box = gt.get("box", gt.get("bbox", [0, 0, 0, 0]))
            iou = self._calculate_iou(pred_box, gt_box)

            if iou > best_iou:
                best_iou = iou
                best_match = gt
                best_idx = idx

        # Cache the result
        if best_iou >= self.iou_threshold:
            self._match_cache[prediction_index] = best_idx
            return best_match
        else:
            self._match_cache[prediction_index] = None
            return None

    def provide_annotation(
        self,
        prediction: SegmentationPrediction,
        prediction_index: int,
    ) -> dict[str, Any]:
        """Simulate human annotation by returning ground truth.

        Returns:
            Dict with 'label', 'box', 'segmentation' from ground truth,
            or original prediction values if no match found.
        """
        match = self.find_match(prediction, prediction_index)

        if match:
            return {
                "label": match.get("label", match.get("class_name", prediction.label)),
                "box": match.get("box", match.get("bbox", prediction.box)),
                "segmentation": match.get("segmentation", prediction.segmentation),
                "source": "ground_truth",
                "iou_with_prediction": self._calculate_iou(
                    prediction.box, match.get("box", match.get("bbox", prediction.box))
                ),
            }

        # No match - return original (simulating human confirming)
        return {
            "label": prediction.label,
            "box": prediction.box,
            "segmentation": prediction.segmentation,
            "source": "original_confirmed",
        }

    def calculate_comprehensive_metrics(
        self,
        predictions: list[SegmentationPrediction],
    ) -> SegmentationMetrics:
        """Calculate comprehensive segmentation metrics against ground truth.

        Uses the metrics module for consistent, detailed evaluation.

        Returns:
            SegmentationMetrics with detection and mask metrics
        """
        # Convert predictions to dict format expected by metrics module
        pred_dicts = [
            {
                "label": p.label,
                "box": p.box,
                "segmentation": p.segmentation,
            }
            for p in predictions
        ]

        return calculate_segmentation_metrics(
            predictions=pred_dicts,
            ground_truth=self.ground_truth,
            iou_threshold=self.iou_threshold,
        )

    @staticmethod
    def _calculate_iou(
        box_a: tuple[float, float, float, float],
        box_b: tuple[float, float, float, float],
    ) -> float:
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

    @staticmethod
    def _calculate_segmentation_iou(
        poly_a: list[tuple[float, float]],
        poly_b: list[tuple[float, float]],
    ) -> float:
        """Calculate IoU between two polygons (simplified)."""
        # Simplified: use bounding boxes as proxy
        # Real implementation would use shapely or similar

        def bbox_from_poly(poly):
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            return (min(xs), min(ys), max(xs), max(ys))

        return GroundTruthSimulator._calculate_iou(
            bbox_from_poly(poly_a), bbox_from_poly(poly_b)
        )


class ExperimentRunner:
    """Run active learning experiments with simulation.

    This runner executes experiments where the system progressively
    improves while using minimal human annotations (simulated via
    ground truth data).
    """

    def __init__(
        self,
        output_dir: str = "./experiment_results",
        dataset_name: str | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_name = dataset_name

    def run_experiment(
        self,
        config: ExperimentConfig,
        images: list[dspy.Image],
        ground_truths: list[list[dict[str, Any]]],
        frame_uris: list[str | None] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ExperimentResult:
        """Run a single experiment configuration.

        Args:
            config: Experiment configuration
            images: List of images to process
            ground_truths: Ground truth annotations for each image
            frame_uris: Optional frame URIs for SAM3 segmentation
            progress_callback: Optional callback(image_idx, total_images)

        Returns:
            ExperimentResult with efficiency curve data
        """
        result = ExperimentResult(config=config)

        logger.info(
            f"Starting experiment: {config.name} (strategy={config.strategy.value}, budget={config.annotation_budget})"
        )

        # Track cumulative state across images
        cumulative_annotations = 0
        cumulative_predictions: list[SegmentationPrediction] = []
        cumulative_metrics_list: list[SegmentationMetrics] = []

        for img_idx, (image, gt) in enumerate(zip(images, ground_truths)):
            if progress_callback:
                progress_callback(img_idx, len(images))

            # Create simulator for this image
            simulator = GroundTruthSimulator(gt)

            # Create segmenter with budget for this image
            # (In real scenario, budget is shared across all images)
            remaining_budget = config.annotation_budget - cumulative_annotations

            if remaining_budget <= 0:
                logger.info(f"Budget exhausted at image {img_idx}")
                break

            segmenter = ActiveLearningSegmenter(
                annotation_budget=remaining_budget,
                strategy=config.strategy,
                uncertainty_threshold=config.uncertainty_threshold,
                bootstrap_examples=config.bootstrap_examples,
                dataset_name=self.dataset_name,
                enable_object_memory=False,  # Disable embedding writes for simulations (retrieval still enabled)
            )

            # Process image
            frame_uri = frame_uris[img_idx] if frame_uris else None

            try:
                al_result = segmenter(image, frame_uri)

                # Simulate human annotations using ground truth
                for pred_idx, pred in enumerate(al_result.predictions):
                    if pred.is_human_annotated:
                        annotation = simulator.provide_annotation(pred, pred_idx)
                        pred.label = annotation["label"]
                        pred.box = annotation["box"]
                        pred.segmentation = annotation.get("segmentation", [])
                        pred.confidence = 0.95  # High confidence after annotation

                # Calculate metrics for this image
                metrics = simulator.calculate_comprehensive_metrics(
                    al_result.predictions
                )
                cumulative_metrics_list.append(metrics)

                # Update cumulative stats
                cumulative_annotations += al_result.annotations_used
                cumulative_predictions.extend(al_result.predictions)

                # Record step
                result.annotations_used.append(cumulative_annotations)
                primary_score = metrics.get_primary_metric(config.primary_metric)
                result.primary_metric_scores.append(primary_score)

                # Record all tracked metrics
                metrics_dict: dict[str, float] = {
                    k: float(v)
                    for k, v in metrics.to_dict().items()
                    if isinstance(v, (int, float))
                }
                result.metrics_history.append(metrics_dict)

                # Store predictions for FiftyOne visualization
                # Note: box coordinates from Gemini are [ymin, xmin, ymax, xmax] in 0-1000 space
                predictions_data = [
                    {
                        "label": p.label,
                        "box": p.box,  # [ymin, xmin, ymax, xmax] normalized 0-1000
                        "segmentation": p.segmentation,
                        "confidence": p.confidence,
                        "is_human_annotated": p.is_human_annotated,
                    }
                    for p in al_result.predictions
                ]

                result.step_details.append(
                    {
                        "image_idx": img_idx,
                        "frame_uri": frame_uri,
                        "annotations_this_image": al_result.annotations_used,
                        "cumulative_annotations": cumulative_annotations,
                        "metrics": metrics.to_dict(),
                        "metrics_summary": metrics.summary,
                        "predictions": predictions_data,
                    }
                )

                # Check stopping criteria
                stop_reason = self._check_stopping_criteria(
                    config, result.primary_metric_scores, cumulative_annotations
                )

                if stop_reason:
                    result.stopped_reason = stop_reason
                    logger.info(f"Experiment stopped: {stop_reason}")
                    break

            except Exception as exc:
                logger.error(f"Error processing image {img_idx}: {exc}")
                continue

        # Finalize results
        result.total_annotations_used = cumulative_annotations

        # Calculate final metrics from all accumulated predictions
        if cumulative_predictions:
            # Create a simulator with union of all ground truths for final eval
            all_gt = []
            for gt in ground_truths[: len(cumulative_metrics_list)]:
                all_gt.extend(gt)

            if all_gt:
                final_simulator = GroundTruthSimulator(all_gt)
                final_metrics = final_simulator.calculate_comprehensive_metrics(
                    cumulative_predictions
                )
                result.final_metrics = {
                    k: float(v)
                    for k, v in final_metrics.to_dict().items()
                    if isinstance(v, (int, float))
                }

        if not result.stopped_reason:
            result.stopped_reason = "completed_all_images"

        logger.info(
            f"Experiment complete: {config.name} | "
            f"annotations={result.total_annotations_used} | "
            f"{config.primary_metric}={result.final_metrics.get(config.primary_metric, 0):.3f} | "
            f"reason={result.stopped_reason}"
        )

        return result

    def run_comparison(
        self,
        configs: list[ExperimentConfig],
        images: list[dspy.Image],
        ground_truths: list[list[dict[str, Any]]],
        frame_uris: list[str | None] | None = None,
    ) -> dict[str, ExperimentResult]:
        """Run multiple experiment configurations and compare.

        Returns:
            Dict mapping config name to ExperimentResult
        """
        results: dict[str, ExperimentResult] = {}

        for config in configs:
            result = self.run_experiment(
                config=config,
                images=images,
                ground_truths=ground_truths,
                frame_uris=frame_uris,
            )
            results[config.name] = result

        return results

    def save_results(
        self,
        results: dict[str, ExperimentResult],
        experiment_name: str,
    ) -> Path:
        """Save experiment results to JSON."""
        output_file = self.output_dir / f"{experiment_name}.json"

        data = {name: result.to_dict() for name, result in results.items()}

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved results to {output_file}")
        return output_file

    def _check_stopping_criteria(
        self,
        config: ExperimentConfig,
        performance_history: list[float],
        annotations_used: int,
    ) -> str | None:
        """Check if experiment should stop.

        Returns:
            Stop reason string, or None if should continue
        """
        # Check budget exhausted
        if annotations_used >= config.annotation_budget:
            return "budget_exhausted"

        # Check target performance reached
        if config.target_performance is not None:
            current_perf = performance_history[-1] if performance_history else 0.0
            if current_perf >= config.target_performance:
                return "target_reached"

        # Check performance plateau
        if len(performance_history) >= config.performance_plateau_window:
            recent = performance_history[-config.performance_plateau_window :]
            improvement = max(recent) - min(recent)
            if improvement < config.performance_plateau_threshold:
                return f"plateau (improvement={improvement:.4f})"

        return None


def create_default_experiment_suite(
    annotation_budgets: list[int] = [0, 5, 10, 20, 50],
) -> list[ExperimentConfig]:
    """Create a standard set of experiment configurations for comparison."""

    configs = []

    # Uncertainty sampling with different budgets
    for budget in annotation_budgets:
        configs.append(
            ExperimentConfig(
                name=f"uncertainty_budget_{budget}",
                strategy=AnnotationStrategy.UNCERTAINTY_SAMPLING,
                annotation_budget=budget,
                target_performance=0.80,
            )
        )

    # Random sampling baseline
    configs.append(
        ExperimentConfig(
            name="random_sampling_baseline",
            strategy=AnnotationStrategy.RANDOM_SAMPLING,
            annotation_budget=50,
            target_performance=0.80,
        )
    )

    # Diversity sampling
    configs.append(
        ExperimentConfig(
            name="diversity_sampling",
            strategy=AnnotationStrategy.DIVERSITY_SAMPLING,
            annotation_budget=50,
            target_performance=0.80,
        )
    )

    # With bootstrapping
    configs.append(
        ExperimentConfig(
            name="uncertainty_with_bootstrap_10",
            strategy=AnnotationStrategy.UNCERTAINTY_SAMPLING,
            annotation_budget=50,
            bootstrap_examples=10,
            target_performance=0.80,
        )
    )

    return configs
