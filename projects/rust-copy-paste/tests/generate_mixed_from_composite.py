#!/usr/bin/env python3
"""Generate labeled visualizations from composite source images.

This script applies copy-paste augmentation to composite images containing
multiple different shapes, demonstrating the mixing capabilities.
"""

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
        font_scale = 0.5
        thickness = 2

        # Get text size
        (text_width, text_height), baseline = cv2.getTextSize(
            label, font, font_scale, thickness
        )

        # Position label above the bbox
        label_x = x
        label_y = max(y - 5, text_height + 5)

        # Draw background rectangle for text
        cv2.rectangle(
            result,
            (label_x, label_y - text_height - 3),
            (label_x + text_width + 3, label_y + 3),
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
    """Generate mixed shape visualizations from composite sources."""
    # Setup paths
    script_dir = Path(__file__).parent
    composite_dir = script_dir / "composite_sources"
    output_dir = script_dir / "augmented_outputs"
    labeled_dir = output_dir / "labeled"

    # Create output directories
    output_dir.mkdir(exist_ok=True)
    labeled_dir.mkdir(exist_ok=True)

    if not composite_dir.exists():
        print(f"❌ Composite sources directory not found: {composite_dir}")
        print("   Run create_composite_sources.py first")
        return False

    print("📊 Generating visualizations from composite sources")

    # Define configurations for each composite
    configs = [
        {
            "source": "mixed_all",
            "title": "All Shapes Mixed",
            "max_objects": 5,
            "description": "Triangle, Circle, and Square",
        },
        {
            "source": "triangles_circles",
            "title": "Triangles + Circles",
            "max_objects": 6,
            "description": "Mix of Triangles and Circles",
        },
        {
            "source": "circles_squares",
            "title": "Circles + Squares",
            "max_objects": 6,
            "description": "Mix of Circles and Squares",
        },
        {
            "source": "multi_triangle",
            "title": "Multiple Triangles",
            "max_objects": 5,
            "description": "Several Triangles",
        },
    ]

    print(f"\n📸 Processing {len(configs)} composite sources")

    for config in configs:
        print(f"\n  Processing {config['source']}: {config['description']}")

        # Load composite image and mask
        img_path = composite_dir / f"{config['source']}.png"
        mask_path = composite_dir / f"{config['source']}_mask.png"

        if not img_path.exists() or not mask_path.exists():
            print(f"    ⚠️  Files not found for {config['source']}")
            continue

        original_img = cv2.imread(str(img_path))
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

        if original_img is None or mask is None:
            print(f"    ❌ Failed to load {config['source']}")
            continue

        # Detect objects in original
        original_objects = detect_objects_in_image(original_img)
        print(f"    Original has {len(original_objects)} objects")

        # Draw annotations on original
        original_annotated = draw_segmentation_and_labels(
            original_img, original_objects
        )
        original_with_title = add_title(original_annotated, "Original")

        # Create transform
        try:
            transform = CopyPasteAugmentation(
                image_width=512,
                image_height=512,
                max_paste_objects=config["max_objects"],
                scale_range=(0.7, 1.2),
                rotation_range=(0, 360),
                p=1.0,
            )
        except (RuntimeError, TypeError) as e:
            print(f"    ⚠️  Transform creation failed: {e}")
            continue

        # Apply augmentation
        try:
            augmented_img = transform.apply(original_img.copy(), mask=mask)
            if augmented_img is None:
                print("    ⚠️  Transform returned None")
                continue

            # Detect objects in augmented
            augmented_objects = detect_objects_in_image(augmented_img)
            print(f"    Augmented has {len(augmented_objects)} objects")

            # Draw annotations on augmented
            augmented_annotated = draw_segmentation_and_labels(
                augmented_img, augmented_objects
            )
            augmented_with_title = add_title(augmented_annotated, config["title"])

            # Save outputs
            cv2.imwrite(
                str(labeled_dir / f"mixed_{config['source']}_original.png"),
                original_with_title,
            )
            cv2.imwrite(
                str(labeled_dir / f"mixed_{config['source']}_augmented.png"),
                augmented_with_title,
            )

            # Create comparison
            comparison = np.hstack([original_with_title, augmented_with_title])
            cv2.imwrite(
                str(labeled_dir / f"mixed_{config['source']}_comparison.png"),
                comparison,
            )

            print("    ✅ Saved visualizations")

        except Exception as e:
            print(f"    ❌ Error during augmentation: {e}")
            import traceback

            traceback.print_exc()
            continue

    print(f"\n✨ Generated mixed visualizations in {labeled_dir}")
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
