#!/usr/bin/env python3
"""Test instance segmentation pipeline and load results into FiftyOne.

Usage:
    # With a local image:
    uv run python scripts/test_pipeline_fiftyone.py --image /path/to/image.jpg

    # With an image URL:
    uv run python scripts/test_pipeline_fiftyone.py --url https://example.com/image.jpg

    # With a GCS URI (requires GCS credentials):
    uv run python scripts/test_pipeline_fiftyone.py --gcs gs://bucket/path/image.jpg
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import dspy
import fiftyone as fo
import numpy as np
from loguru import logger

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_vision.instance_segmentation.programme import InstanceSegmentationAnnotator


def load_image_as_dspy_image(
    image_path: str | None = None,
    image_url: str | None = None,
    gcs_uri: str | None = None,
) -> tuple[dspy.Image, str, np.ndarray]:
    """Load image from various sources and return dspy.Image, path/uri, and numpy array."""

    if image_path:
        # Local file
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        mime_type = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
        data_uri = f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("utf-8")
        img_array = cv2.imread(image_path)
        return dspy.Image(url=data_uri), image_path, img_array

    elif image_url:
        # HTTP URL
        import requests
        response = requests.get(image_url)
        response.raise_for_status()
        image_bytes = response.content
        mime_type = "image/jpeg"
        if image_url.lower().endswith(".png"):
            mime_type = "image/png"
        data_uri = f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("utf-8")
        img_array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        return dspy.Image(url=data_uri), image_url, img_array

    elif gcs_uri:
        # GCS URI
        from google.cloud import storage
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        parts = gcs_uri[5:].split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1] if len(parts) > 1 else ""

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        image_bytes = blob.download_as_bytes()

        mime_type = "image/jpeg" if gcs_uri.lower().endswith((".jpg", ".jpeg")) else "image/png"
        data_uri = f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("utf-8")
        img_array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        return dspy.Image(url=data_uri), gcs_uri, img_array

    else:
        raise ValueError("Must provide one of: image_path, image_url, or gcs_uri")


def parse_annotations(annotations_text: str) -> list[dict[str, Any]]:
    """Parse annotation output into structured format."""
    annotations = []

    for line in annotations_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue

        # Parse: object: <label> | box: [x1, y1, x2, y2] | segmentation: [...] | confidence=0.XX
        label_match = re.search(r"object:\s*([^|]+)", line)
        box_match = re.search(r"box:\s*\[([^\]]+)\]", line)
        seg_match = re.search(r"segmentation:\s*\[([^\]]*)\]", line)
        conf_match = re.search(r"confidence=(\d+\.?\d*)", line)

        if label_match and box_match:
            label = label_match.group(1).strip()
            box = [int(float(x.strip())) for x in box_match.group(1).split(",")]

            segmentation = []
            if seg_match and seg_match.group(1).strip():
                try:
                    seg_coords = [float(x.strip()) for x in seg_match.group(1).split(",")]
                    # Convert flat list to polygon points
                    segmentation = [(seg_coords[i], seg_coords[i+1])
                                   for i in range(0, len(seg_coords)-1, 2)]
                except (ValueError, IndexError):
                    pass

            confidence = float(conf_match.group(1)) if conf_match else 0.5

            annotations.append({
                "label": label,
                "box": box,
                "segmentation": segmentation,
                "confidence": confidence,
            })

    return annotations


def create_fiftyone_dataset(
    image_array: np.ndarray,
    image_source: str,
    annotations: list[dict[str, Any]],
    dataset_name: str = "instance_segmentation_test",
) -> fo.Dataset:
    """Create FiftyOne dataset with detections and segmentations."""

    # Save image to temp file for FiftyOne
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        cv2.imwrite(f.name, image_array)
        temp_image_path = f.name

    height, width = image_array.shape[:2]

    # Create detections
    detections = []
    for ann in annotations:
        x1, y1, x2, y2 = ann["box"]

        # Normalize bounding box to [0, 1]
        rel_box = [
            x1 / width,
            y1 / height,
            (x2 - x1) / width,
            (y2 - y1) / height,
        ]

        detection_kwargs = {
            "label": ann["label"],
            "bounding_box": rel_box,
            "confidence": ann["confidence"],
        }

        # Add segmentation mask if available
        if ann["segmentation"]:
            # Create binary mask from polygon
            mask = np.zeros((height, width), dtype=np.uint8)
            polygon_points = np.array(ann["segmentation"], dtype=np.int32)
            cv2.fillPoly(mask, [polygon_points], 1)

            # Crop mask to bounding box region
            x1_int, y1_int = int(x1), int(y1)
            x2_int, y2_int = int(x2), int(y2)
            cropped_mask = mask[y1_int:y2_int, x1_int:x2_int]

            if cropped_mask.size > 0:
                detection_kwargs["mask"] = cropped_mask.astype(bool)

        detections.append(fo.Detection(**detection_kwargs))

    # Create sample
    sample = fo.Sample(filepath=temp_image_path)
    sample["source"] = image_source
    sample["detections"] = fo.Detections(detections=detections)

    # Create or get dataset
    if fo.dataset_exists(dataset_name):
        dataset = fo.load_dataset(dataset_name)
        dataset.delete()

    dataset = fo.Dataset(dataset_name)
    dataset.add_sample(sample)

    return dataset


def main():
    parser = argparse.ArgumentParser(description="Test instance segmentation and view in FiftyOne")

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--image", help="Local image file path")
    source_group.add_argument("--url", help="Image URL to download")
    source_group.add_argument("--gcs", help="GCS URI (gs://bucket/path)")

    parser.add_argument("--dataset-name", default="instance_segmentation_test",
                       help="FiftyOne dataset name")
    parser.add_argument("--max-iters", type=int, default=12,
                       help="Max ReAct iterations")
    parser.add_argument("--no-launch", action="store_true",
                       help="Don't launch FiftyOne app")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    # Configure DSPy with Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        logger.error("GEMINI_API_KEY environment variable is required")
        return 1

    lm = dspy.LM("gemini/gemini-2.0-flash", api_key=gemini_key)
    dspy.configure(lm=lm)

    logger.info("Loading image...")
    dspy_image, image_source, img_array = load_image_as_dspy_image(
        image_path=args.image,
        image_url=args.url,
        gcs_uri=args.gcs,
    )
    logger.info(f"Loaded image: {image_source} ({img_array.shape[1]}x{img_array.shape[0]})")

    # Run pipeline
    logger.info("Running instance segmentation pipeline...")
    annotator = InstanceSegmentationAnnotator(max_iters=args.max_iters)

    # Use GCS URI as frame_uri if available (for SAM3 backend)
    frame_uri = args.gcs if args.gcs else None

    result = annotator(image=dspy_image, frame_uri=frame_uri)

    logger.info("=" * 60)
    logger.info("RAW ANNOTATIONS:")
    logger.info("=" * 60)
    print(result.annotations)
    logger.info("=" * 60)

    # Parse annotations
    annotations = parse_annotations(result.annotations)
    logger.info(f"Parsed {len(annotations)} annotations")

    for i, ann in enumerate(annotations):
        logger.info(f"  [{i}] {ann['label']}: box={ann['box']}, conf={ann['confidence']:.2f}, "
                   f"seg_points={len(ann['segmentation'])}")

    # Create FiftyOne dataset
    logger.info("Creating FiftyOne dataset...")
    dataset = create_fiftyone_dataset(
        img_array, image_source, annotations, args.dataset_name
    )
    logger.info(f"Created dataset: {dataset.name} with {len(dataset)} samples")

    # Launch FiftyOne
    if not args.no_launch:
        logger.info("Launching FiftyOne app...")
        session = fo.launch_app(dataset)
        logger.info(f"FiftyOne app running at: {session.url}")
        input("Press Enter to close FiftyOne...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
