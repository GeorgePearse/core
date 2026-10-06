"""Simple synthetic test for active learning experiments.

Creates synthetic test data to demonstrate the experiment framework.
This generates fake images with simple shapes and runs a minimal experiment.
"""

import json
import random
from pathlib import Path
from typing import Any

import dspy
import numpy as np
from PIL import Image, ImageDraw
from loguru import logger

from agentic_vision.active_learning import AnnotationStrategy
from agentic_vision.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
    GroundTruthSimulator,
)


def create_synthetic_image(
    width: int = 640,
    height: int = 480,
    num_objects: int = 5,
    object_types: list[str] | None = None,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Create a synthetic image with random shapes as objects.

    Returns:
        (image, ground_truth_annotations)
    """
    if object_types is None:
        object_types = ["circle", "rectangle", "triangle"]

    # Create blank image
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)

    annotations = []

    for i in range(num_objects):
        # Random object type
        obj_type = random.choice(object_types)

        # Random position (avoid edges)
        margin = 50
        x1 = random.randint(margin, width - margin - 60)
        y1 = random.randint(margin, height - margin - 60)
        size = random.randint(30, 80)
        x2 = x1 + size
        y2 = y1 + size

        # Draw object
        color = tuple(random.randint(50, 200) for _ in range(3))

        if obj_type == "circle":
            draw.ellipse([x1, y1, x2, y2], fill=color, outline=(0, 0, 0), width=2)
        elif obj_type == "rectangle":
            draw.rectangle([x1, y1, x2, y2], fill=color, outline=(0, 0, 0), width=2)
        elif obj_type == "triangle":
            # Simple triangle approximation
            points = [(x1, y2), ((x1 + x2) // 2, y1), (x2, y2)]
            draw.polygon(points, fill=color, outline=(0, 0, 0), width=2)

        # Record annotation
        annotations.append(
            {
                "label": obj_type,
                "box": [x1, y1, x2, y2],
                "segmentation": [],  # Would be polygon points for real segmentation
            }
        )

    return img, annotations


def create_synthetic_dataset(
    num_images: int = 5,
    objects_per_image: tuple[int, int] = (3, 7),
    output_dir: str = "./synthetic_test_data",
) -> tuple[list[dspy.Image], list[list[dict[str, Any]]], list[str | None]]:
    """Create a synthetic dataset for testing.

    Returns:
        (images, ground_truths, frame_uris)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    images = []
    ground_truths = []
    frame_uris = []

    for i in range(num_images):
        num_objects = random.randint(objects_per_image[0], objects_per_image[1])

        # Create synthetic image
        img, annotations = create_synthetic_image(num_objects=num_objects)

        # Save image
        img_path = output_path / f"test_image_{i:03d}.png"
        img.save(img_path)

        # Convert to dspy.Image
        dspy_img = dspy.Image(str(img_path))

        images.append(dspy_img)
        ground_truths.append(annotations)
        frame_uris.append(str(img_path))

        logger.debug(f"Created synthetic image {i}: {num_objects} objects")

    logger.info(f"Created {num_images} synthetic test images in {output_dir}")

    return images, ground_truths, frame_uris


def test_metrics_module():
    """Test that the metrics module works correctly."""
    from agentic_vision.metrics import calculate_segmentation_metrics, SegmentationMetrics

    # Create fake predictions and ground truth
    predictions = [
        {"label": "circle", "box": [100, 100, 150, 150]},
        {"label": "rectangle", "box": [200, 200, 280, 260]},
        {"label": "triangle", "box": [50, 300, 100, 350]},
    ]

    ground_truth = [
        {"label": "circle", "box": [105, 105, 155, 155]},  # Good match
        {"label": "rectangle", "box": [210, 210, 290, 270]},  # Good match
        {"label": "triangle", "box": [400, 400, 450, 450]},  # Missed
    ]

    metrics = calculate_segmentation_metrics(predictions, ground_truth, iou_threshold=0.5)

    logger.info("Metrics test results:")
    logger.info(f"  Detection Precision: {metrics.detection_precision:.2f}")
    logger.info(f"  Detection Recall: {metrics.detection_recall:.2f}")
    logger.info(f"  Detection F1: {metrics.detection_f1:.2f}")
    logger.info(f"  Mean IoU: {metrics.mean_iou:.2f}")
    logger.info(f"  Summary: {metrics.summary}")

    return metrics


def run_minimal_experiment():
    """Run a minimal experiment with synthetic data."""
    logger.info("=" * 60)
    logger.info("RUNNING MINIMAL ACTIVE LEARNING EXPERIMENT")
    logger.info("=" * 60)

    # Step 1: Create synthetic dataset
    logger.info("\n1. Creating synthetic test dataset...")
    images, ground_truths, frame_uris = create_synthetic_dataset(
        num_images=3,
        objects_per_image=(3, 5),
        output_dir="./synthetic_test_data",
    )

    # Step 2: Test metrics module
    logger.info("\n2. Testing metrics calculation...")
    test_metrics = test_metrics_module()

    # Step 3: Set up experiment configs
    logger.info("\n3. Setting up experiment configurations...")
    configs = [
        ExperimentConfig(
            name="random_baseline",
            strategy=AnnotationStrategy.RANDOM_SAMPLING,
            annotation_budget=10,
            primary_metric="detection_f1",
            target_performance=0.90,  # High target - may not reach
            performance_plateau_window=3,
        ),
        ExperimentConfig(
            name="uncertainty_sampling",
            strategy=AnnotationStrategy.UNCERTAINTY_SAMPLING,
            annotation_budget=10,
            primary_metric="detection_f1",
            target_performance=0.90,
            uncertainty_threshold=0.6,
            performance_plateau_window=3,
        ),
    ]

    logger.info(f"Created {len(configs)} experiment configs:")
    for cfg in configs:
        logger.info(f"  - {cfg.name}: {cfg.strategy.value}, budget={cfg.annotation_budget}")

    # Step 4: Run experiments
    logger.info("\n4. Running experiments...")

    # For this minimal test, we'll just simulate with ground truth
    # since we don't have actual VLM APIs configured
    runner = ExperimentRunner(
        output_dir="./synthetic_experiment_results",
    )

    results = {}

    for config in configs:
        logger.info(f"\n  Running: {config.name}...")

        # Create a simple simulation result
        # In real usage, this would call runner.run_experiment()
        # Here we simulate what the result would look like

        annotations_used = []
        metric_scores = []

        # Simulate improving performance with more annotations
        for i in range(config.annotation_budget + 1):
            annotations_used.append(i)

            # Simulated learning curve: starts at 0.3, improves with annotations
            base_score = 0.3
            improvement = min(0.6, i * 0.08)  # Max improvement of 0.6
            noise = random.uniform(-0.05, 0.05)
            score = base_score + improvement + noise
            score = min(1.0, max(0.0, score))  # Clamp to [0, 1]

            metric_scores.append(score)

        # Simulate result
        from agentic_vision.experiment_runner import ExperimentResult

        result = ExperimentResult(
            config=config,
            annotations_used=annotations_used,
            primary_metric_scores=metric_scores,
            metrics_history=[
                {
                    "detection_f1": score,
                    "detection_precision": min(1.0, score + 0.1),
                    "detection_recall": max(0.0, score - 0.1),
                    "mean_iou": score * 0.8,
                }
                for score in metric_scores
            ],
            final_metrics={
                "detection_f1": metric_scores[-1],
                "detection_precision": 0.85,
                "detection_recall": 0.75,
                "mean_iou": metric_scores[-1] * 0.8,
            },
            total_annotations_used=config.annotation_budget,
            stopped_reason="simulated",
        )

        results[config.name] = result

        logger.info(f"    Final F1: {result.final_metrics.get('detection_f1', 0):.3f}")
        logger.info(f"    Annotations: {result.total_annotations_used}")

    # Step 5: Save results
    logger.info("\n5. Saving results...")
    results_file = runner.save_results(results, "synthetic_test")
    logger.info(f"Saved to: {results_file}")

    # Step 6: Generate plots
    logger.info("\n6. Generating plots...")
    try:
        from agentic_vision.experiment_plots import (
            EfficiencyCurve,
            plot_efficiency_curves,
            plot_strategy_comparison,
            create_summary_table,
        )

        # Create efficiency curves
        curves = [EfficiencyCurve.from_experiment_result(result.to_dict(), metric_name="detection_f1") for result in results.values()]

        # Plot efficiency curves
        plot_path = plot_efficiency_curves(
            curves=curves,
            output_path="./synthetic_experiment_results/efficiency_curves.png",
            title="Synthetic Test: Detection F1 vs Annotations",
            ylabel="Detection F1 Score",
        )
        logger.info(f"  Efficiency curves: {plot_path}")

        # Plot comparison
        compare_path = plot_strategy_comparison(
            curves=curves,
            output_path="./synthetic_experiment_results/strategy_comparison.png",
            metric="final_performance",
            title="Final Detection Performance",
        )
        logger.info(f"  Strategy comparison: {compare_path}")

        # Create summary table
        table_path = create_summary_table(
            curves=curves,
            output_path="./synthetic_experiment_results/results_summary.md",
            target_threshold=0.80,
        )
        logger.info(f"  Summary table: {table_path}")

    except Exception as exc:
        logger.warning(f"Plot generation failed: {exc}")

    logger.info("\n" + "=" * 60)
    logger.info("EXPERIMENT COMPLETE")
    logger.info("=" * 60)

    # Print summary
    print("\nResults Summary:")
    print("-" * 60)
    for name, result in results.items():
        print(f"{name}:")
        print(f"  Strategy: {result.config.strategy.value}")
        print(f"  Annotations: {result.total_annotations_used}")
        print(f"  Detection F1: {result.final_metrics.get('detection_f1', 0):.3f}")
        print(f"  Mean IoU: {result.final_metrics.get('mean_iou', 0):.3f}")
    print("-" * 60)

    return results


if __name__ == "__main__":
    # Run the minimal experiment
    results = run_minimal_experiment()
