#!/usr/bin/env python3
"""Generate true mixed shape outputs by combining multiple source images.

This demonstrates copy-paste by:
1. Loading source images with different shapes
2. Creating a combined source pool with all shapes
3. Applying copy-paste to show all shapes mixed together
"""

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from copy_paste import CopyPasteAugmentation


def detect_objects_in_image(image: np.ndarray) -> list[dict[str, Any]]:
    """Detect colored objects in an image and extract their contours."""
    color_ranges = {
        "triangle": {
            "lower": np.array([0, 0, 200]),
            "upper": np.array([50, 50, 255]),
            "name": "triangle",
        },
        "circle": {
            "lower": np.array([0, 200, 0]),
            "upper": np.array([50, 255, 50]),
            "name": "circle",
        },
        "square": {
            "lower": np.array([200, 0, 0]),
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

    contour_colors = {
        "triangle": (0, 255, 255),  # Yellow
        "circle": (255, 0, 255),  # Magenta
        "square": (255, 255, 0),  # Cyan
    }

    for obj in objects:
        contour = obj["contour"]
        class_name = obj["class_name"]
        x, y, w, h = obj["bbox"]

        cv2.drawContours(
            result, [contour], -1, contour_colors[class_name], 2, cv2.LINE_AA
        )

        label = class_name.upper()
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 2

        (text_width, text_height), _ = cv2.getTextSize(
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

    return np.vstack([title_bar, image])


def main() -> bool:
    """Generate true mixed shape outputs."""
    script_dir = Path(__file__).parent
    composite_dir = script_dir / "composite_sources"
    output_dir = script_dir / "augmented_outputs"
    labeled_dir = output_dir / "labeled"

    output_dir.mkdir(exist_ok=True)
    labeled_dir.mkdir(exist_ok=True)

    print("🎨 Generating true mixed shape outputs from composite sources")

    if not composite_dir.exists():
        print(f"❌ Composite directory not found: {composite_dir}")
        return False

    # Use the composite sources that already have multiple shapes
    configs = [
        {
            "name": "all_shapes_mixed",
            "source": "mixed_all",
            "title": "All Shapes Combined",
            "max_objects": 4,
        },
        {
            "name": "triangles_circles_mixed",
            "source": "triangles_circles",
            "title": "Triangles + Circles Mixed",
            "max_objects": 5,
        },
        {
            "name": "circles_squares_mixed",
            "source": "circles_squares",
            "title": "Circles + Squares Mixed",
            "max_objects": 5,
        },
    ]

    for config in configs:
        print(f"\n  Generating {config['name']}")

        # Load composite source
        source_path = composite_dir / f"{config['source']}.png"
        mask_path = composite_dir / f"{config['source']}_mask.png"

        if not source_path.exists() or not mask_path.exists():
            print(f"    ⚠️  Source not found: {config['source']}")
            continue

        source_img = cv2.imread(str(source_path))
        source_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

        if source_img is None or source_mask is None:
            print(f"    ❌ Failed to load {config['source']}")
            continue

        # Detect objects in source
        source_objects = detect_objects_in_image(source_img)
        print(f"    Source has {len(source_objects)} objects")

        source_annotated = draw_segmentation_and_labels(source_img, source_objects)
        source_with_title = add_title(source_annotated, "Source")

        # Apply copy-paste augmentation
        transform = CopyPasteAugmentation(
            image_width=512,
            image_height=512,
            max_paste_objects=config["max_objects"],
            scale_range=(0.6, 1.4),
            rotation_range=(0, 360),
            p=1.0,
        )

        augmented_img = transform.apply(source_img.copy(), mask=source_mask)
        if augmented_img is None:
            print("    ⚠️  Transform returned None")
            continue

        # Detect objects in augmented
        augmented_objects = detect_objects_in_image(augmented_img)
        print(f"    Augmented has {len(augmented_objects)} objects")

        augmented_annotated = draw_segmentation_and_labels(
            augmented_img, augmented_objects
        )
        augmented_with_title = add_title(augmented_annotated, config["title"])

        # Save outputs
        cv2.imwrite(
            str(labeled_dir / f"{config['name']}_source.png"),
            source_with_title,
        )
        cv2.imwrite(
            str(labeled_dir / f"{config['name']}_augmented.png"),
            augmented_with_title,
        )

        comparison = np.hstack([source_with_title, augmented_with_title])
        cv2.imwrite(
            str(labeled_dir / f"{config['name']}_comparison.png"),
            comparison,
        )

        print("    ✅ Saved")

    print(f"\n✨ Generated mixed outputs in {labeled_dir}")
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
