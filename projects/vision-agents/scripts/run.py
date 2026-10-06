#!/usr/bin/env python3
"""Run active learning experiments with real database data.

This script connects to the PostgreSQL database to fetch images and ground truth
annotations, runs active learning experiments, and stores results.

Usage:
    # Run with database connection (auto-loads .env from parent directory)
    uv run python scripts/run.py \
        --dataset-name construction_demolition \
        --num-images 50 \
        --budgets 0,5,10,20,50

    # Run with local annotation file
    uv run python scripts/run.py \
        --annotations-file ./annotations.json \
        --budgets 0,5,10,20,50

Environment Variables:
    PG_DATABASE_URL: PostgreSQL connection string (auto-loaded from ../../.env)
    GEMINI_API_KEY: API key for Gemini VLM (optional, for real inference)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from google.cloud import storage

# FiftyOne import (optional)
try:
    import fiftyone as fo

    FIFTYONE_AVAILABLE = True
except ImportError:
    fo = None
    FIFTYONE_AVAILABLE = False


# Load .env file from parent directory before other imports
def _load_env_file():
    """Load environment variables from .env file in parent directory."""
    script_dir = Path(__file__).parent.absolute()
    # Go up from scripts/ to repo root
    env_file = script_dir.parent / ".env"

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value
        print(f"Loaded environment from: {env_file}")
    else:
        print(f"Warning: .env file not found at {env_file}")


_load_env_file()

import dspy
import psycopg
from loguru import logger

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_vision.active_learning import AnnotationStrategy
from agentic_vision.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
    create_default_experiment_suite,
)
from agentic_vision.experiment_plots import (
    EfficiencyCurve,
    analyze_experiment_results,
    plot_efficiency_curves,
    plot_strategy_comparison,
    create_summary_table,
)
from agentic_vision.coordinates import (
    BoxFormat,
    BoxValidationError,
    convert_box,
    validate_annotation_boxes,
    validate_box,
    validate_predictions_boxes,
)


def get_db_connection() -> psycopg.Connection[Any]:
    """Create a database connection using PG_DATABASE_URL."""
    database_url = os.environ.get("PG_DATABASE_URL")
    if not database_url:
        raise ValueError(
            "PG_DATABASE_URL environment variable is required.\nExample: PG_DATABASE_URL='postgresql://user:pass@host:5432/dbname'"
        )
    return psycopg.connect(database_url)


def get_dataset_images_from_db(
    conn: psycopg.Connection[Any],
    dataset_name: str,
    num_images: int = 50,
) -> list[dict[str, Any]]:
    """Fetch images with ground truth annotations from database.

    Returns list of dicts with:
        - image_id
        - frame_uri
        - annotations: list of {label, box, segmentation}
    """
    logger.info(f"Querying database for dataset/task: {dataset_name}")

    with conn.cursor() as cur:
        # Get images - can query by task_name or dataset_name
        # First try task_name (common pattern)
        cur.execute(
            """
            SELECT 
                i.image_id,
                i.frame_uri,
                i.task_name,
                d.dataset_name
            FROM machine_learning.images i
            LEFT JOIN machine_learning.datasets d ON i.dataset_id = d.id
            WHERE i.task_name = %s
              AND i.frame_uri IS NOT NULL
            ORDER BY i.image_id
            LIMIT %s
            """,
            (dataset_name, num_images),
        )

        rows = cur.fetchall()

        # If no results, try by dataset_name
        if not rows:
            cur.execute(
                """
                SELECT 
                    i.image_id,
                    i.frame_uri,
                    i.task_name,
                    d.dataset_name
                FROM machine_learning.images i
                JOIN machine_learning.datasets d ON i.dataset_id = d.id
                WHERE d.dataset_name = %s
                  AND i.frame_uri IS NOT NULL
                ORDER BY i.image_id
                LIMIT %s
                """,
                (dataset_name, num_images),
            )
            rows = cur.fetchall()

        logger.info(f"Found {len(rows)} images in database")

        images_data = []

        for row in rows:
            image_id, frame_uri, task_name, ds_name = row

            # Get annotations for this image
            cur.execute(
                """
                SELECT 
                    a.id as annotation_id,
                    ic.name as class_name,
                    a.box_x1,
                    a.box_y1,
                    a.box_width,
                    a.box_height,
                    a.segmentations
                FROM machine_learning.annotations a
                JOIN public.inference_category ic ON a.inference_category_id = ic.id
                WHERE a.image_id = %s
                  AND a.is_deleted = false
                """,
                (image_id,),
            )

            ann_rows = cur.fetchall()

            annotations = []
            for ann_row in ann_rows:
                ann_id, class_name, x1, y1, width, height, segmentations = ann_row

                # Convert to x1, y1, x2, y2 format
                x2 = x1 + width if width else x1
                y2 = y1 + height if height else y1

                box = [x1, y1, x2, y2]
                try:
                    validate_box(
                        box,
                        BoxFormat.XYXY_PIXEL,
                        context=f"DB image_id={image_id} ann_id={ann_id}",
                    )
                except BoxValidationError as exc:
                    logger.warning(f"Skipping invalid DB annotation: {exc}")
                    continue

                annotations.append(
                    {
                        "annotation_id": ann_id,
                        "label": class_name,
                        "box": box,
                        "segmentation": [],  # segmentations is polygon type, would need parsing
                    }
                )

            images_data.append(
                {
                    "image_id": image_id,
                    "frame_uri": frame_uri,
                    "task_name": task_name,
                    "dataset_name": ds_name,
                    "annotations": annotations,
                }
            )

            logger.debug(f"Image {image_id}: {len(annotations)} annotations")

        return images_data


def load_annotations_from_file(filepath: str) -> list[dict[str, Any]]:
    """Load annotations from a JSON file.

    Expected format:
    {
        "images": [
            {
                "image_id": 123,
                "frame_uri": "<machine_learning.images.frame_uri or local image path>",
                "annotations": [
                    {
                        "label": "person",
                        "box": [100, 200, 150, 250],
                        "segmentation": [...]
                    }
                ]
            }
        ]
    }
    """
    with open(filepath) as f:
        data = json.load(f)

    images_data = data.get("images", [])

    placeholder_indices = [
        idx
        for idx, image in enumerate(images_data)
        if str(image.get("frame_uri", "")).startswith(
            "REPLACE_WITH_MACHINE_LEARNING_IMAGES_FRAME_URI"
        )
    ]
    if placeholder_indices:
        raise ValueError(
            "Annotation file contains placeholder frame_uri values. "
            "Use the exact values from machine_learning.images.frame_uri "
            "or valid local image paths before running experiments."
        )

    logger.info(f"Loaded {len(images_data)} images from {filepath}")

    for img_idx, img_data in enumerate(images_data):
        annotations = img_data.get("annotations", [])
        valid = validate_annotation_boxes(
            annotations,
            BoxFormat.XYXY_PIXEL,
            context=f"file image[{img_idx}]",
        )
        img_data["annotations"] = valid
        dropped = len(annotations) - len(valid)
        if dropped:
            logger.warning(
                f"file image[{img_idx}]: dropped {dropped} invalid annotation(s)"
            )

    return images_data


def download_image_from_gcs(frame_uri: str) -> bytes:
    """Download image from GCS and return bytes."""
    if not frame_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {frame_uri}")

    parts = frame_uri[5:].split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def image_bytes_to_data_uri(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Convert image bytes to a data URI."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def create_fiftyone_dataset(
    images_data: list[dict[str, Any]],
    dataset_name: str,
    results_file: str | None = None,
) -> "fo.Dataset":
    """Create FiftyOne dataset from images data and optionally add predictions.

    Args:
        images_data: List of dicts with frame_uri, annotations, etc.
            Ground truth boxes are in pixel coordinates [x1, y1, x2, y2].
        dataset_name: Name for the FiftyOne dataset
        results_file: Optional path to experiment results JSON containing predictions.
            Predictions from Gemini are stored as [ymin, xmin, ymax, xmax] in 0-1000
            normalized space. This function converts them to FiftyOne's expected
            format: [x, y, width, height] normalized to [0, 1].

    Returns:
        FiftyOne Dataset object with 'ground_truth' and 'predictions' fields.

    Note:
        Coordinate format conversions:
        - Ground truth: pixel [x1, y1, x2, y2] -> normalized [x, y, w, h]
        - Predictions: Gemini [ymin, xmin, ymax, xmax] 0-1000 -> normalized [x, y, w, h]
    """
    if not FIFTYONE_AVAILABLE:
        raise RuntimeError(
            "FiftyOne is not available. Install with: pip install fiftyone"
        )

    # Delete existing dataset if it exists
    if fo.dataset_exists(dataset_name):
        fo.delete_dataset(dataset_name)

    dataset = fo.Dataset(dataset_name)
    dataset.persistent = True

    # Load predictions from results file if provided
    predictions_by_image: dict[int, list[dict]] = {}
    if results_file and Path(results_file).exists():
        logger.info(f"Loading predictions from: {results_file}")
        with open(results_file) as f:
            results = json.load(f)

        # Extract predictions from step_details - use the best experiment's predictions
        # (highest budget with uncertainty strategy, or fall back to any with predictions)
        best_exp = None
        for exp_name, exp_result in results.items():
            if "step_details" in exp_result and exp_result["step_details"]:
                if best_exp is None or "uncertainty" in exp_name:
                    best_exp = exp_name

        if best_exp:
            logger.info(f"Using predictions from experiment: {best_exp}")
            for step in results[best_exp]["step_details"]:
                img_idx = step.get("image_idx", -1)
                preds = step.get("predictions", [])
                if img_idx >= 0 and preds:
                    predictions_by_image[img_idx] = preds
            logger.info(f"Loaded predictions for {len(predictions_by_image)} images")

    # Process each image
    temp_dir = tempfile.mkdtemp()

    for idx, img_data in enumerate(images_data):
        frame_uri = img_data.get("frame_uri", "")
        annotations = img_data.get("annotations", [])

        try:
            # Download image from GCS
            image_bytes = download_image_from_gcs(frame_uri)
            img_array = cv2.imdecode(
                np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR
            )

            if img_array is None:
                logger.warning(f"Skipping image {idx}: could not decode {frame_uri}")
                continue

            height, width = img_array.shape[:2]

            # Save to temp file
            temp_path = Path(temp_dir) / f"image_{idx}.jpg"
            cv2.imwrite(str(temp_path), img_array)

            # Create sample
            sample = fo.Sample(filepath=str(temp_path))
            sample["frame_uri"] = frame_uri
            sample["frame_id"] = img_data.get("frame_id", idx)

            # Add ground truth detections
            gt_detections = []
            for ann in annotations:
                box = ann.get("box", ann.get("bbox", [0, 0, 1, 1]))

                try:
                    validated_pixel = validate_box(
                        box,
                        BoxFormat.XYXY_PIXEL,
                        context=f"FiftyOne GT image[{idx}]",
                        image_width=width,
                        image_height=height,
                    )
                except BoxValidationError as exc:
                    logger.warning(f"Skipping GT detection for image[{idx}]: {exc}")
                    continue

                x1, y1, x2, y2 = validated_pixel

                rel_box = convert_box(
                    validated_pixel,
                    BoxFormat.XYXY_PIXEL,
                    BoxFormat.XYWH_NORM_01,
                    image_width=width,
                    image_height=height,
                    context=f"FiftyOne GT image[{idx}]",
                )

                detection_kwargs = {
                    "label": ann.get("label", "unknown"),
                    "bounding_box": rel_box,
                }

                # Add segmentation mask if available
                if ann.get("segmentation"):
                    try:
                        seg_points = ann["segmentation"]
                        if isinstance(seg_points, list) and len(seg_points) >= 6:
                            mask = np.zeros((height, width), dtype=np.uint8)
                            if isinstance(seg_points[0], (list, tuple)):
                                polygon_points = np.array(seg_points, dtype=np.int32)
                            else:
                                polygon_points = np.array(
                                    [
                                        (seg_points[i], seg_points[i + 1])
                                        for i in range(0, len(seg_points) - 1, 2)
                                    ],
                                    dtype=np.int32,
                                )
                            cv2.fillPoly(mask, [polygon_points], (1,))

                            x1_int, y1_int = int(x1), int(y1)
                            x2_int, y2_int = int(x2), int(y2)
                            cropped_mask = mask[y1_int:y2_int, x1_int:x2_int]

                            if cropped_mask.size > 0:
                                detection_kwargs["mask"] = cropped_mask.astype(bool)
                    except Exception as e:
                        logger.debug(f"Could not create mask: {e}")

                gt_detections.append(fo.Detection(**detection_kwargs))

            sample["ground_truth"] = fo.Detections(detections=gt_detections)

            # Add predictions if available for this image
            if idx in predictions_by_image:
                pred_detections = []
                for pred in predictions_by_image[idx]:
                    box = pred.get("box", [0, 0, 1, 1])

                    try:
                        validated_yxyx = validate_box(
                            box,
                            BoxFormat.YXYX_NORM_1K,
                            context=f"FiftyOne pred image[{idx}]",
                        )
                    except BoxValidationError as exc:
                        logger.warning(f"Skipping prediction for image[{idx}]: {exc}")
                        continue

                    # Convert from Gemini [y1, x1, y2, x2] 0-1000 -> XYWH [0,1] for FiftyOne
                    rel_box = convert_box(
                        validated_yxyx,
                        BoxFormat.YXYX_NORM_1K,
                        BoxFormat.XYWH_NORM_01,
                        context=f"FiftyOne pred image[{idx}]",
                    )

                    # Also get pixel coords for mask cropping
                    pixel_box = convert_box(
                        validated_yxyx,
                        BoxFormat.YXYX_NORM_1K,
                        BoxFormat.XYXY_PIXEL,
                        image_width=width,
                        image_height=height,
                        context=f"FiftyOne pred mask image[{idx}]",
                    )
                    x1_px, y1_px, x2_px, y2_px = (int(v) for v in pixel_box)

                    pred_kwargs = {
                        "label": pred.get("label", "unknown"),
                        "bounding_box": rel_box,
                        "confidence": pred.get("confidence", 0.5),
                    }

                    # Add prediction mask if available
                    if pred.get("segmentation"):
                        try:
                            seg_points = pred["segmentation"]
                            if isinstance(seg_points, list) and len(seg_points) >= 6:
                                mask = np.zeros((height, width), dtype=np.uint8)
                                if isinstance(seg_points[0], (list, tuple)):
                                    polygon_points = np.array(
                                        [
                                            [
                                                int(p[0] * width / 1000),
                                                int(p[1] * height / 1000),
                                            ]
                                            for p in seg_points
                                        ],
                                        dtype=np.int32,
                                    )
                                else:
                                    polygon_points = np.array(
                                        [
                                            (
                                                int(seg_points[i] * width / 1000),
                                                int(seg_points[i + 1] * height / 1000),
                                            )
                                            for i in range(0, len(seg_points) - 1, 2)
                                        ],
                                        dtype=np.int32,
                                    )
                                cv2.fillPoly(mask, [polygon_points], (1,))

                                cropped_mask = mask[y1_px:y2_px, x1_px:x2_px]

                                if cropped_mask.size > 0:
                                    pred_kwargs["mask"] = cropped_mask.astype(bool)
                        except Exception as e:
                            logger.debug(f"Could not create prediction mask: {e}")

                    pred_detections.append(fo.Detection(**pred_kwargs))

                sample["predictions"] = fo.Detections(detections=pred_detections)
                logger.debug(
                    f"Added {len(pred_detections)} predictions for image {idx}"
                )

            dataset.add_sample(sample)
            logger.info(
                f"Added image {idx}: {len(gt_detections)} GT, {len(predictions_by_image.get(idx, []))} predictions"
            )

        except Exception as e:
            logger.warning(f"Skipping image {idx}: {e}")
            continue

    logger.info(f"Created dataset '{dataset_name}' with {len(dataset)} samples")
    return dataset


def prepare_images_for_experiment(
    images_data: list[dict[str, Any]],
    max_images: int | None = None,
) -> tuple[list[dspy.Image], list[list[dict[str, Any]]], list[str | None]]:
    """Convert database/file data to format needed for experiments.

    Downloads images from GCS and converts to data URIs for dspy.Image.

    Returns:
        (images, ground_truths, frame_uris)
    """
    if max_images:
        images_data = images_data[:max_images]

    images: list[dspy.Image] = []
    ground_truths: list[list[dict[str, Any]]] = []
    frame_uris: list[str | None] = []

    for img_data in images_data:
        frame_uri = img_data.get("frame_uri", "")

        try:
            # Download image from GCS and convert to data URI
            logger.debug(f"Downloading image: {frame_uri}")
            image_bytes = download_image_from_gcs(frame_uri)

            # Determine mime type from extension
            mime_type = "image/jpeg"
            if frame_uri.lower().endswith(".png"):
                mime_type = "image/png"
            elif frame_uri.lower().endswith(".webp"):
                mime_type = "image/webp"

            data_uri = image_bytes_to_data_uri(image_bytes, mime_type)
            img = dspy.Image(url=data_uri)
            images.append(img)
        except Exception as exc:
            logger.warning(f"Could not load image {frame_uri}: {exc}")
            continue

        # Extract ground truth annotations
        annotations = img_data.get("annotations", [])
        ground_truths.append(annotations)
        frame_uris.append(frame_uri)

    logger.info(f"Prepared {len(images)} images for experiment")
    return images, ground_truths, frame_uris


def run_experiment_from_db(
    dataset_name: str,
    num_images: int,
    budgets: list[int],
    strategies: list[AnnotationStrategy],
    output_dir: str,
    experiment_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run experiment using database as data source.

    Returns:
        Tuple of (results dict, images_data list for FiftyOne)
    """

    # Connect to database
    conn = get_db_connection()

    try:
        # Fetch images and annotations
        images_data = get_dataset_images_from_db(conn, dataset_name, num_images)

        if not images_data:
            logger.error(f"No images found for dataset: {dataset_name}")
            return {}, []

        # Prepare for experiment
        images, ground_truths, frame_uris = prepare_images_for_experiment(images_data)

        if not images:
            logger.error("No valid images to process")
            return {}, []

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
                        primary_metric="detection_f1",
                        target_performance=0.80,
                        performance_plateau_window=5,
                    )
                )

        # Run experiments
        runner = ExperimentRunner(
            output_dir=output_dir,
            dataset_name=dataset_name,
        )

        results = runner.run_comparison(
            configs=configs,
            images=images,
            ground_truths=ground_truths,
            frame_uris=frame_uris,
        )

        # Save results
        results_file = runner.save_results(results, experiment_name)
        logger.info(f"Results saved to: {results_file}")

        # Generate plots
        logger.info("Generating plots and analysis...")
        plot_outputs = analyze_experiment_results(
            results_file=results_file,
            output_dir=Path(output_dir) / f"{experiment_name}_plots",
        )

        logger.info("Generated outputs:")
        for name, path in plot_outputs.items():
            logger.info(f"  - {name}: {path}")

        return results, images_data

    finally:
        conn.close()


def run_experiment_from_file(
    annotations_file: str,
    budgets: list[int],
    strategies: list[AnnotationStrategy],
    output_dir: str,
    experiment_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run experiment using local annotation file as data source.

    Returns:
        Tuple of (results dict, images_data list for FiftyOne)
    """
    # Load annotations
    images_data = load_annotations_from_file(annotations_file)

    if not images_data:
        logger.error(f"No images loaded from: {annotations_file}")
        return {}, []

    # Prepare for experiment
    images, ground_truths, frame_uris = prepare_images_for_experiment(images_data)

    if not images:
        logger.error("No valid images to process")
        return {}, []

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
                    primary_metric="detection_f1",
                    target_performance=0.80,
                    performance_plateau_window=5,
                )
            )

    # Run experiments
    runner = ExperimentRunner(
        output_dir=output_dir,
        dataset_name=None,
    )

    results = runner.run_comparison(
        configs=configs,
        images=images,
        ground_truths=ground_truths,
        frame_uris=frame_uris,
    )

    # Save results
    results_file = runner.save_results(results, experiment_name)
    logger.info(f"Results saved to: {results_file}")

    # Generate plots
    logger.info("Generating plots and analysis...")
    plot_outputs = analyze_experiment_results(
        results_file=results_file,
        output_dir=Path(output_dir) / f"{experiment_name}_plots",
    )

    logger.info("Generated outputs:")
    for name, path in plot_outputs.items():
        logger.info(f"  - {name}: {path}")

    return results, images_data


def parse_budget_list(budgets_str: str) -> list[int]:
    """Parse comma-separated budget list."""
    return [int(x.strip()) for x in budgets_str.split(",")]


def parse_strategies(strategies_str: str) -> list[AnnotationStrategy]:
    """Parse comma-separated strategy list."""
    strategy_map = {
        "uncertainty": AnnotationStrategy.UNCERTAINTY_SAMPLING,
        "random": AnnotationStrategy.RANDOM_SAMPLING,
        "diversity": AnnotationStrategy.DIVERSITY_SAMPLING,
        "threshold": AnnotationStrategy.CONFIDENCE_THRESHOLD,
    }

    strategies = []
    for s in strategies_str.split(","):
        s = s.strip().lower()
        if s in strategy_map:
            strategies.append(strategy_map[s])
        else:
            logger.warning(f"Unknown strategy: {s}, skipping")

    return strategies if strategies else [AnnotationStrategy.UNCERTAINTY_SAMPLING]


def main():
    parser = argparse.ArgumentParser(
        description="Run active learning experiments with database or file data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Database mode
  PG_DATABASE_URL="postgresql://..." uv run python scripts/run.py \\
      --dataset-name construction_demolition \\
      --num-images 50 \\
      --budgets 0,5,10,20,50

  # File mode
  uv run python scripts/run.py \\
      --annotations-file ./annotations.json \\
      --budgets 0,5,10,20,50

File-mode note:
  Each frame_uri should be copied directly from machine_learning.images.frame_uri
  or point at a real local image file. Do not reconstruct bucket URLs manually.
        """,
    )

    # Data source arguments
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--dataset-name",
        help="Dataset name to query from database",
    )
    source_group.add_argument(
        "--annotations-file",
        help="JSON file with ground truth annotations",
    )

    # Experiment configuration
    parser.add_argument(
        "--num-images",
        type=int,
        default=50,
        help="Number of images to process (default: 50)",
    )
    parser.add_argument(
        "--budgets",
        type=str,
        default="0,5,10,20,50",
        help="Comma-separated annotation budgets to test (default: 0,5,10,20,50)",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        default="uncertainty,random",
        help="Comma-separated strategies: uncertainty,random,diversity,threshold",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./experiment_results",
        help="Directory to save results (default: ./experiment_results)",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="active_learning_experiment",
        help="Name for this experiment run",
    )

    # Debugging
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    # FiftyOne visualization
    parser.add_argument(
        "--no-fiftyone",
        action="store_true",
        help="Skip launching FiftyOne visualization",
    )
    parser.add_argument(
        "--fiftyone-port",
        type=int,
        default=5151,
        help="Port for FiftyOne app (default: 5151)",
    )
    parser.add_argument(
        "--fiftyone-dataset-name",
        type=str,
        help="Name for FiftyOne dataset (default: {dataset_name}_experiment)",
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    # Parse budgets and strategies
    budgets = parse_budget_list(args.budgets)
    strategies = parse_strategies(args.strategies)

    logger.info("=" * 70)
    logger.info("ACTIVE LEARNING EXPERIMENT")
    logger.info("=" * 70)
    logger.info(f"Budgets: {budgets}")
    logger.info(f"Strategies: {[s.value for s in strategies]}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info("=" * 70)

    try:
        # Run experiment based on data source
        if args.dataset_name:
            logger.info(f"Running with database dataset: {args.dataset_name}")
            results, images_data = run_experiment_from_db(
                dataset_name=args.dataset_name,
                num_images=args.num_images,
                budgets=budgets,
                strategies=strategies,
                output_dir=args.output_dir,
                experiment_name=args.experiment_name,
            )
        else:
            logger.info(f"Running with annotation file: {args.annotations_file}")
            results, images_data = run_experiment_from_file(
                annotations_file=args.annotations_file,
                budgets=budgets,
                strategies=strategies,
                output_dir=args.output_dir,
                experiment_name=args.experiment_name,
            )

        # Print summary
        if results:
            print("\n" + "=" * 70)
            print("RESULTS SUMMARY")
            print("=" * 70)
            for name, result in results.items():
                print(f"\n{name}:")
                print(f"  Strategy: {result.config.strategy.value}")
                print(f"  Annotations: {result.total_annotations_used}")
                print(
                    f"  Detection F1: {result.final_metrics.get('detection_f1', 0):.3f}"
                )
                print(f"  Mean IoU: {result.final_metrics.get('mean_iou', 0):.3f}")
                print(f"  Stopped: {result.stopped_reason}")
            print("=" * 70)
            print(f"\nResults saved to: {args.output_dir}")
            print("=" * 70)

            # Launch FiftyOne visualization
            if not args.no_fiftyone and images_data:
                if not FIFTYONE_AVAILABLE:
                    logger.warning(
                        "FiftyOne not available. Install with: pip install fiftyone"
                    )
                else:
                    fo_dataset_name = (
                        args.fiftyone_dataset_name
                        or f"{args.dataset_name or 'experiment'}_experiment"
                    )
                    results_file = (
                        Path(args.output_dir) / f"{args.experiment_name}.json"
                    )

                    logger.info(f"Creating FiftyOne dataset: {fo_dataset_name}")
                    try:
                        # Set MongoDB URI if not set (use local MongoDB without auth)
                        if "FIFTYONE_DATABASE_URI" not in os.environ:
                            os.environ["FIFTYONE_DATABASE_URI"] = (
                                "mongodb://localhost:27017"
                            )

                        dataset = create_fiftyone_dataset(
                            images_data=images_data,
                            dataset_name=fo_dataset_name,
                            results_file=str(results_file)
                            if results_file.exists()
                            else None,
                        )

                        logger.info(
                            f"Launching FiftyOne app on port {args.fiftyone_port}..."
                        )
                        session = fo.launch_app(
                            dataset, port=args.fiftyone_port, address="0.0.0.0"
                        )
                        logger.info(
                            f"FiftyOne app running at: http://0.0.0.0:{args.fiftyone_port}"
                        )
                        print(
                            f"\nFiftyOne is running at: http://localhost:{args.fiftyone_port}"
                        )
                        print("Press Enter to close FiftyOne and exit...")
                        input()
                    except Exception as e:
                        logger.error(f"Failed to launch FiftyOne: {e}")
                        logger.info(
                            "Results are still saved. You can view them later with load_results_fiftyone.py"
                        )
        else:
            logger.error("Experiment produced no results")
            return 1

        return 0

    except Exception as exc:
        logger.exception(f"Experiment failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
