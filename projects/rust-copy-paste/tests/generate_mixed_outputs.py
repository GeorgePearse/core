#!/usr/bin/env python3
"""Generate labeled visualizations with mixed shapes (copy-paste augmentation).

This script creates visualizations showing:
1. Original images (single shape per image)
2. Augmented images with multiple different shapes pasted together
"""

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from copy_paste import CopyPasteAugmentation


def detect_objects_in_image(image: np.ndarray) -> list[dict[str, Any]]:
    """Detect colored objects in an image and extract their contours.

    Args:
        image: BGR image

    Returns:
        List of detected objects with contours, bboxes, colors, and class names
    """
    # Define color ranges for each shape
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
        # Create mask for this color
        mask = cv2.inRange(image, color_range["lower"], color_range["upper"])

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            # Filter small contours (noise)
            area = cv2.contourArea(contour)
            if area < 100:  # Minimum area threshold
                continue

            # Get bounding box
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
    """Draw segmentation contours and labels on image.

    Args:
        image: Input image
        objects: List of detected objects

    Returns:
        Image with annotations
    """
    result = image.copy()

    # Color mapping for labels
    label_colors = {
        "triangle": (255, 255, 255),  # White text
        "circle": (255, 255, 255),
        "square": (255, 255, 255),
    }

    contour_colors = {
        "triangle": (0, 255, 255),  # Yellow contour
        "circle": (255, 0, 255),  # Magenta contour
        "square": (255, 255, 0),  # Cyan contour
    }

    for obj in objects:
        contour = obj["contour"]
        class_name = obj["class_name"]
        x, y, w, h = obj["bbox"]

        # Draw contour
        cv2.drawContours(
            result, [contour], -1, contour_colors[class_name], 2, cv2.LINE_AA
        )

        # Prepare label text
        label = class_name.upper()

        # Text properties
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2

        # Get text size
        (text_width, text_height), baseline = cv2.getTextSize(
            label, font, font_scale, thickness
        )

        # Position label above the bbox
        label_x = x
        label_y = max(y - 10, text_height + 5)

        # Draw background rectangle for text
        cv2.rectangle(
            result,
            (label_x, label_y - text_height - 5),
            (label_x + text_width + 5, label_y + 5),
            (0, 0, 0),
            -1,
        )

        # Draw text
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
    """Add title bar to top of image.

    Args:
        image: Input image
        title: Title text

    Returns:
        Image with title bar
    """
    height, width = image.shape[:2]

    # Create title bar
    title_bar_height = 40
    title_bar = np.zeros((title_bar_height, width, 3), dtype=np.uint8)

    # Add text to title bar
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

    # Stack title bar on top of image
    result = np.vstack([title_bar, image])
    return result


def main() -> bool:
    """Generate mixed shape visualization outputs."""
    # Setup paths
    script_dir = Path(__file__).parent
    dataset_dir = script_dir / "dummy_dataset"
    images_dir = dataset_dir / "images"
    masks_dir = dataset_dir / "masks"
    annotations_file = dataset_dir / "annotations" / "annotations.json"
    output_dir = script_dir / "augmented_outputs"
    labeled_dir = output_dir / "labeled"

    # Create output directories
    output_dir.mkdir(exist_ok=True)
    labeled_dir.mkdir(exist_ok=True)

    if not annotations_file.exists():
        print(f"❌ Annotations file not found: {annotations_file}")
        return False

    print(f"📊 Generating mixed shape visualizations from {dataset_dir}")

    # Load annotations
    with open(annotations_file) as f:
        coco_data = json.load(f)

    # Create class name mapping
    class_names = {cat["id"]: cat["name"] for cat in coco_data["categories"]}
    print(f"🏷️  Classes: {list(class_names.values())}")

    # Create class name to ID mapping
    class_id_map = {cat["name"]: cat["id"] for cat in coco_data["categories"]}
    print(f"🔢 Class ID mapping: {class_id_map}")

    # Define mixed combinations to generate
    # Note: object_counts uses class IDs (integers), not names (strings)
    mixed_configs = [
        {
            "name": "triangles_and_circles",
            "base": "triangle",
            "counts": {class_id_map["triangle"]: 2, class_id_map["circle"]: 2},
            "title": "Triangles + Circles",
        },
        {
            "name": "circles_and_squares",
            "base": "circle",
            "counts": {class_id_map["circle"]: 2, class_id_map["square"]: 2},
            "title": "Circles + Squares",
        },
        {
            "name": "squares_and_triangles",
            "base": "square",
            "counts": {class_id_map["square"]: 2, class_id_map["triangle"]: 2},
            "title": "Squares + Triangles",
        },
        {
            "name": "all_shapes",
            "base": "triangle",
            "counts": {
                class_id_map["triangle"]: 1,
                class_id_map["circle"]: 1,
                class_id_map["square"]: 1,
            },
            "title": "All Shapes Mixed",
        },
        {
            "name": "many_triangles",
            "base": "triangle",
            "counts": {class_id_map["triangle"]: 4},
            "title": "Multiple Triangles",
        },
        {
            "name": "many_circles",
            "base": "circle",
            "counts": {class_id_map["circle"]: 4},
            "title": "Multiple Circles",
        },
    ]

    print(f"\n📸 Processing {len(mixed_configs)} mixed configurations")

    for config in mixed_configs:
        print(f"\n  Generating {config['name']}: {config['title']}")

        # Get a base image for this configuration
        base_class = config["base"]
        base_filename = f"{base_class}_000.png"

        # Load base image
        image_path = images_dir / base_filename
        base_img = cv2.imread(str(image_path))
        if base_img is None:
            print(f"    ❌ Failed to load base image: {base_filename}")
            continue

        # Load base mask
        mask_filename = base_filename.replace(".png", "_mask.png")
        mask_path = masks_dir / mask_filename
        if not mask_path.exists():
            print(f"    ⚠️  Base mask not found: {mask_filename}")
            continue

        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(f"    ❌ Failed to load base mask: {mask_filename}")
            continue

        # Detect objects in base image
        base_objects = detect_objects_in_image(base_img)
        print(f"    Base image has {len(base_objects)} object(s)")

        # Draw segmentation and labels on base
        base_annotated = draw_segmentation_and_labels(base_img, base_objects)
        base_with_title = add_title(base_annotated, f"Original ({base_class})")

        # Update transform with new object counts
        transform_config = CopyPasteAugmentation(
            image_width=512,
            image_height=512,
            object_counts=config["counts"],
            scale_range=(0.8, 1.2),
            rotation_range=(0, 360),
            p=1.0,
        )

        # Apply augmentation
        try:
            augmented_img = transform_config.apply(base_img.copy(), mask=mask)
            if augmented_img is None:
                print("    ⚠️  Transform returned None")
                continue

            # Detect objects in augmented image
            augmented_objects = detect_objects_in_image(augmented_img)
            print(
                f"    Augmented image has {len(augmented_objects)} object(s) after mixing"
            )

            # Draw segmentation and labels on augmented
            augmented_annotated = draw_segmentation_and_labels(
                augmented_img, augmented_objects
            )
            augmented_with_title = add_title(augmented_annotated, config["title"])

            # Save individual labeled images
            cv2.imwrite(
                str(labeled_dir / f"{config['name']}_original.png"),
                base_with_title,
            )
            cv2.imwrite(
                str(labeled_dir / f"{config['name']}_augmented.png"),
                augmented_with_title,
            )

            # Create side-by-side comparison
            comparison = np.hstack([base_with_title, augmented_with_title])
            cv2.imwrite(
                str(labeled_dir / f"{config['name']}_comparison.png"),
                comparison,
            )

            print("    ✅ Saved mixed shape outputs")

        except Exception as e:
            print(f"    ❌ Error during augmentation: {e}")
            import traceback

            traceback.print_exc()
            continue

    print(f"\n✨ Generated mixed shape visualizations in {labeled_dir}")
    return True


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"⚠️  Error generating mixed outputs: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
