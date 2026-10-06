#!/usr/bin/env python3
"""Regenerate all augmented outputs with proper copy-paste transformations.

This script generates outputs that truly demonstrate the copy-paste algorithm:
1. Individual shapes with multiple instances (copy from source, paste with transformations)
2. Mixed shapes by using multiple source images as input
"""

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from copy_paste import CopyPasteAugmentation


def detect_objects_in_image(image: np.ndarray) -> list[dict[str, Any]]:
    """Detect colored objects in an image and extract their contours."""
    color_ranges = {
        "triangle": {
            "lower": np.array([0, 0, 200]),  # Red in BGR
            "upper": np.array([50, 50, 255]),
            "name": "triangle",
        },
        "circle": {
            "lower": np.array([0, 200, 0]),  # Green in BGR
            "upper": np.array([50, 255, 50]),
            "name": "circle",
        },
        "square": {
            "lower": np.array([200, 0, 0]),  # Blue in BGR
            "upper": np.array([255, 50, 50]),
            "name": "square",
        },
    }

    detected_objects = []

    for class_name, color_range in color_ranges.items():
        mask = cv2.inRange(image, color_range["lower"], color_range["upper"])
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 100:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            detected_objects.append(
                {
                    "contour": contour,
                    "bbox": (x, y, w, h),
                    "class_name": class_name,
                    "area": area,
                }
            )

    return detected_objects


def draw_segmentation_and_labels(
    image: np.ndarray, objects: list[dict[str, Any]]
) -> np.ndarray:
    """Draw segmentation contours and labels on image."""
    result = image.copy()

    label_colors = {
        "triangle": (255, 255, 255),
        "circle": (255, 255, 255),
        "square": (255, 255, 255),
    }

    # Draw all segmentations in yellow to verify mask boundaries
    segmentation_color = (0, 255, 255)  # Yellow in BGR

    for obj in objects:
        contour = obj["contour"]
        class_name = obj["class_name"]
        x, y, w, h = obj["bbox"]

        # Draw yellow segmentation contour for all objects
        cv2.drawContours(
            result, [contour], -1, segmentation_color, 2, cv2.LINE_AA
        )

        label = class_name.upper()
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 2

        (text_width, text_height), baseline = cv2.getTextSize(
            label, font, font_scale, thickness
        )

        label_x = x
        label_y = max(y - 5, text_height + 5)

        cv2.rectangle(
            result,
            (label_x, label_y - text_height - 3),
            (label_x + text_width + 3, label_y + 3),
            (0, 0, 0),
            -1,
        )

        cv2.putText(
            result,
            label,
            (label_x + 2, label_y),
            font,
            font_scale,
            label_colors[class_name],
            thickness,
            cv2.LINE_AA,
        )

    return result


def add_title(image: np.ndarray, title: str) -> np.ndarray:
    """Add title bar to top of image."""
    height, width = image.shape[:2]
    title_bar_height = 40
    title_bar = np.zeros((title_bar_height, width, 3), dtype=np.uint8)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    thickness = 2
    color = (255, 255, 255)

    (text_width, text_height), _ = cv2.getTextSize(title, font, font_scale, thickness)
    text_x = (width - text_width) // 2
    text_y = (title_bar_height + text_height) // 2

    cv2.putText(
        title_bar,
        title,
        (text_x, text_y),
        font,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA,
    )

    result = np.vstack([title_bar, image])
    return result


def main() -> bool:
    """Regenerate all augmented outputs."""
    script_dir = Path(__file__).parent
    dataset_dir = script_dir / "dummy_dataset"
    images_dir = dataset_dir / "images"
    masks_dir = dataset_dir / "masks"
    annotations_file = dataset_dir / "annotations" / "annotations.json"
    output_dir = script_dir / "augmented_outputs"
    labeled_dir = output_dir / "labeled"

    output_dir.mkdir(exist_ok=True)
    labeled_dir.mkdir(exist_ok=True)

    if not annotations_file.exists():
        print(f"❌ Annotations file not found: {annotations_file}")
        return False

    print("🎨 Regenerating all augmented outputs")

    with open(annotations_file) as f:
        coco_data = json.load(f)

    class_names = {cat["id"]: cat["name"] for cat in coco_data["categories"]}
    print(f"🏷️  Classes: {list(class_names.values())}")

    # Part 1: Individual shapes with copy-paste (multiple instances)
    print("\n📸 Part 1: Individual shapes")

    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=3,  # Will paste up to 3 total objects
        scale_range=(0.8, 1.3),  # Add scaling variation
        rotation_range=(0, 360),  # Full rotation
        p=1.0,
    )

    examples_per_class = {}
    for img_info in coco_data["images"]:
        class_name = img_info["file_name"].split("_")[0]
        if class_name not in examples_per_class:
            examples_per_class[class_name] = img_info["file_name"]

    for class_name, filename in examples_per_class.items():
        print(f"\n  Processing {class_name}: {filename}")

        image_path = images_dir / filename
        original_img = cv2.imread(str(image_path))
        if original_img is None:
            print("    ❌ Failed to load image")
            continue

        mask_filename = filename.replace(".png", "_mask.png")
        mask_path = masks_dir / mask_filename
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print("    ❌ Failed to load mask")
            continue

        # Detect objects in original
        original_objects = detect_objects_in_image(original_img)
        print(f"    Original: {len(original_objects)} object(s)")

        original_annotated = draw_segmentation_and_labels(
            original_img, original_objects
        )
        original_with_title = add_title(original_annotated, "Original")

        # Apply augmentation
        result = transform(image=original_img.copy(), mask=mask)
        augmented_img = result["image"]
        augmented_mask = result.get("mask")

        if augmented_img is None:
            print("    ⚠️  Transform returned None")
            continue

        # Draw yellow contours from actual mask output
        if augmented_mask is not None and augmented_mask.max() > 0:
            contours, _ = cv2.findContours(
                augmented_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            augmented_annotated = augmented_img.copy()
            # Draw yellow segmentation contours from actual masks
            cv2.drawContours(augmented_annotated, contours, -1, (0, 255, 255), 2, cv2.LINE_AA)
            print(f"    Augmented: {len(contours)} mask contour(s)")
        else:
            # Fallback to color detection if no mask
            augmented_objects = detect_objects_in_image(augmented_img)
            print(f"    Augmented: {len(augmented_objects)} object(s) (color detected)")
            augmented_annotated = draw_segmentation_and_labels(
                augmented_img, augmented_objects
            )

        augmented_with_title = add_title(augmented_annotated, "Augmented")

        # Save outputs
        cv2.imwrite(
            str(labeled_dir / f"{class_name}_original_labeled.png"),
            original_with_title,
        )
        cv2.imwrite(
            str(labeled_dir / f"{class_name}_augmented_labeled.png"),
            augmented_with_title,
        )

        comparison = np.hstack([original_with_title, augmented_with_title])
        cv2.imwrite(
            str(labeled_dir / f"{class_name}_comparison.png"),
            comparison,
        )

        print("    ✅ Saved")

    print(f"\n✨ Generated outputs in {labeled_dir}")
    return True


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"⚠️  Error: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
