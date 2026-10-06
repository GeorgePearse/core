"""Run active learning experiments to measure annotation efficiency.

This script runs experiments to determine how few human annotations are needed
to achieve target segmentation performance. It uses existing ground truth
annotations to simulate the active learning process.

Usage:
    cd lib/python/agentic_vision
    uv run python scripts/run_active_learning_experiment.py \
        --dataset-name construction_demolition \
        --num-images 50 \
        --budgets 0,5,10,20,50

The experiment generates efficiency curves showing:
- X-axis: Number of human annotations used
- Y-axis: Segmentation performance (mean IoU)

Strategies compared:
- Uncertainty sampling (annotate most uncertain objects)
- Random sampling (baseline)
- Diversity sampling (spread annotations across classes)
- Bootstrap with pre-loaded examples
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import dspy
from loguru import logger

from agentic_vision.active_learning import AnnotationStrategy
from agentic_vision.active_learning_programme import ActiveLearningSegmenter
from agentic_vision.experiment_plots import (
    analyze_experiment_results,
    plot_efficiency_curves,
)
from agentic_vision.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
    GroundTruthSimulator,
    create_default_experiment_suite,
)


def load_ground_truth_from_db(
    dataset_name: str,
    num_images: int,
) -> tuple[list[dspy.Image], list[list[dict[str, Any]]], list[str | None]]:
    """Load images and ground truth from database.

    Returns:
        Tuple of (images, ground_truths, frame_uris)
    """
    logger.info(f"Loading ground truth from dataset: {dataset_name}")

    # This would query the actual database
    # For now, return placeholder data

    images = []
    ground_truths = []
    frame_uris = []

    logger.info(f"Loaded {len(images)} images")
    return images, ground_truths, frame_uris


def load_ground_truth_from_file(
    annotations_file: str,
) -> tuple[list[dspy.Image], list[list[dict[str, Any]]], list[str | None]]:
    """Load images and ground truth from a JSON file.

    Expected format:
    {
        "images": [
            {
                "frame_uri": "gs://...",
                "annotations": [
                    {"label": "...", "box": [x1,y1,x2,y2], "segmentation": [...]}
                ]
            }
        ]
    }
    """
    logger.info(f"Loading ground truth from: {annotations_file}")

    with open(annotations_file) as f:
        data = json.load(f)

    images = []
    ground_truths = []
    frame_uris = []

    for img_data in data.get("images", []):
        # Load image (would download from GCS in real implementation)
        # images.append(dspy.Image(...))

        ground_truths.append(img_data.get("annotations", []))
        frame_uris.append(img_data.get("frame_uri"))

    logger.info(f"Loaded {len(images)} images from file")
    return images, ground_truths, frame_uris


def parse_budget_list(budgets_str: str) -> list[int]:
    """Parse comma-separated budget list."""
    return [int(x.strip()) for x in budgets_str.split(",")]


def main():
    parser = argparse.ArgumentParser(description="Run active learning efficiency experiments")

    # Data source
    parser.add_argument(
        "--dataset-name",
        help="Dataset name to query from database",
    )
    parser.add_argument(
        "--annotations-file",
        help="JSON file with ground truth annotations",
    )
    parser.add_argument(
        "--num-images",
        type=int,
        default=50,
        help="Number of images to process",
    )

    # Experiment configuration
    parser.add_argument(
        "--budgets",
        type=str,
        default="0,5,10,20,50",
        help="Comma-separated annotation budgets to test",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        default="uncertainty,random",
        help="Comma-separated strategies: uncertainty,random,diversity",
    )
    parser.add_argument(
        "--uncertainty-threshold",
        type=float,
        default=0.7,
        help="Threshold above which to request annotation",
    )
    parser.add_argument(
        "--target-performance",
        type=float,
        default=0.80,
        help="Target IoU to achieve (stops experiment when reached)",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./experiment_results",
        help="Directory to save results",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="active_learning_efficiency",
        help="Name for this experiment run",
    )

    # Debugging
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # Validate arguments
    if not args.dataset_name and not args.annotations_file:
        parser.error("Must provide either --dataset-name or --annotations-file")

    # Load data
    if args.annotations_file:
        images, ground_truths, frame_uris = load_ground_truth_from_file(args.annotations_file)
    else:
        images, ground_truths, frame_uris = load_ground_truth_from_db(
            args.dataset_name,
            args.num_images,
        )

    if not images:
        logger.error("No images loaded. Cannot run experiment.")
        return 1

    # Parse budgets
    budgets = parse_budget_list(args.budgets)
    logger.info(f"Testing budgets: {budgets}")

    # Parse strategies
    strategy_map = {
        "uncertainty": AnnotationStrategy.UNCERTAINTY_SAMPLING,
        "random": AnnotationStrategy.RANDOM_SAMPLING,
        "diversity": AnnotationStrategy.DIVERSITY_SAMPLING,
        "threshold": AnnotationStrategy.CONFIDENCE_THRESHOLD,
    }

    strategies = []
    for s in args.strategies.split(","):
        s = s.strip().lower()
        if s in strategy_map:
            strategies.append(strategy_map[s])
        else:
            logger.warning(f"Unknown strategy: {s}, skipping")

    if not strategies:
        strategies = [AnnotationStrategy.UNCERTAINTY_SAMPLING]

    logger.info(f"Testing strategies: {[s.value for s in strategies]}")

    # Create experiment configurations
    configs = []

    for budget in budgets:
        for strategy in strategies:
            name = f"{strategy.value}_budget_{budget}"
            configs.append(
                ExperimentConfig(
                    name=name,
                    strategy=strategy,
                    annotation_budget=budget,
                    uncertainty_threshold=args.uncertainty_threshold,
                    target_performance=args.target_performance,
                )
            )

    # Add bootstrap configuration
    configs.append(
        ExperimentConfig(
            name="uncertainty_with_bootstrap_10",
            strategy=AnnotationStrategy.UNCERTAINTY_SAMPLING,
            annotation_budget=50,
            bootstrap_examples=10,
            uncertainty_threshold=args.uncertainty_threshold,
            target_performance=args.target_performance,
        )
    )

    # Run experiments
    logger.info(f"Running {len(configs)} experiment configurations...")

    runner = ExperimentRunner(
        output_dir=args.output_dir,
        dataset_name=args.dataset_name,
    )

    results = runner.run_comparison(
        configs=configs,
        images=images,
        ground_truths=ground_truths,
        frame_uris=frame_uris,
    )

    # Save results
    results_file = runner.save_results(results, args.experiment_name)
    logger.info(f"Results saved to: {results_file}")

    # Generate plots
    logger.info("Generating plots and analysis...")

    plot_outputs = analyze_experiment_results(
        results_file=results_file,
        output_dir=Path(args.output_dir) / f"{args.experiment_name}_plots",
    )

    logger.info("Generated outputs:")
    for name, path in plot_outputs.items():
        logger.info(f"  - {name}: {path}")

    # Print summary
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)

    for name, result in results.items():
        final_performance = result.final_metrics.get(result.config.primary_metric, 0.0)
        print(f"\n{name}:")
        print(f"  Annotations used: {result.total_annotations_used}/{result.config.annotation_budget}")
        print(f"  Final performance: {final_performance:.3f} IoU")
        print(f"  Stopped because: {result.stopped_reason}")

    print("\n" + "=" * 60)
    print(f"Results saved to: {args.output_dir}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
