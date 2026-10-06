#!/usr/bin/env python3
"""Create composite source images with multiple different shapes.

This script creates source images containing multiple different shapes
that can then be used for copy-paste augmentation to demonstrate mixing.
"""

from pathlib import Path

import cv2
import numpy as np


def create_composite_image(
    shapes: list[str],
    images_dir: Path,
    masks_dir: Path,
    output_size: tuple[int, int] = (512, 512),
) -> tuple[np.ndarray, np.ndarray]:
    """Create a composite image with multiple shapes.

    Args:
        shapes: List of shape names to include (e.g., ['triangle', 'circle'])
        images_dir: Directory containing source images
        masks_dir: Directory containing source masks
        output_size: Size of output image (width, height)

    Returns:
        Tuple of (composite_image, composite_mask)
    """
    width, height = output_size
    composite = np.ones((height, width, 3), dtype=np.uint8) * 240  # Light gray bg
    composite_mask = np.zeros((height, width), dtype=np.uint8)

    # Define positions for placing shapes
    positions = [
        (128, 128),  # Top-left
        (384, 128),  # Top-right
        (128, 384),  # Bottom-left
        (384, 384),  # Bottom-right
        (256, 256),  # Center
    ]

    class_id = 1  # Start with class ID 1

    for i, shape in enumerate(shapes):
        if i >= len(positions):
            break

        # Load source image and mask
        source_path = images_dir / f"{shape}_000.png"
        mask_path = masks_dir / f"{shape}_000_mask.png"

        if not source_path.exists() or not mask_path.exists():
            print(f"⚠️  Skipping {shape}: files not found")
            continue

        source_img = cv2.imread(str(source_path))
        source_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

        if source_img is None or source_mask is None:
            print(f"⚠️  Skipping {shape}: failed to load")
            continue

        # Find the object in the source mask
        coords = np.argwhere(source_mask > 0)
        if len(coords) == 0:
            print(f"⚠️  Skipping {shape}: empty mask")
            continue

        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)

        # Extract the object
        obj_img = source_img[y_min : y_max + 1, x_min : x_max + 1]
        obj_mask = source_mask[y_min : y_max + 1, x_min : x_max + 1]

        # Calculate paste position (centered on target position)
        obj_h, obj_w = obj_img.shape[:2]
        x_pos, y_pos = positions[i]
        paste_x = max(0, x_pos - obj_w // 2)
        paste_y = max(0, y_pos - obj_h // 2)

        # Ensure we don't go out of bounds
        paste_x = min(paste_x, width - obj_w)
        paste_y = min(paste_y, height - obj_h)

        # Paste the object using the mask
        for y in range(obj_h):
            for x in range(obj_w):
                if obj_mask[y, x] > 0:
                    target_y = paste_y + y
                    target_x = paste_x + x
                    if 0 <= target_y < height and 0 <= target_x < width:
                        composite[target_y, target_x] = obj_img[y, x]
                        composite_mask[target_y, target_x] = class_id

        print(f"  ✅ Placed {shape} at position {positions[i]}")
        class_id += 1

    return composite, composite_mask


def main() -> bool:
    """Create composite source images."""
    script_dir = Path(__file__).parent
    dataset_dir = script_dir / "dummy_dataset"
    images_dir = dataset_dir / "images"
    masks_dir = dataset_dir / "masks"
    composite_dir = script_dir / "composite_sources"

    # Create output directory
    composite_dir.mkdir(exist_ok=True)

    print("🎨 Creating composite source images")

    # Define composite configurations
    composites = [
        {
            "name": "mixed_all",
            "shapes": ["triangle", "circle", "square"],
            "description": "All three shapes",
        },
        {
            "name": "triangles_circles",
            "shapes": ["triangle", "triangle", "circle", "circle"],
            "description": "Triangles and circles",
        },
        {
            "name": "circles_squares",
            "shapes": ["circle", "circle", "square", "square"],
            "description": "Circles and squares",
        },
        {
            "name": "multi_triangle",
            "shapes": ["triangle", "triangle", "triangle"],
            "description": "Multiple triangles",
        },
    ]

    for config in composites:
        print(f"\n📐 Creating {config['name']}: {config['description']}")

        composite_img, composite_mask = create_composite_image(
            config["shapes"], images_dir, masks_dir
        )

        # Save composite image and mask
        img_path = composite_dir / f"{config['name']}.png"
        mask_path = composite_dir / f"{config['name']}_mask.png"

        cv2.imwrite(str(img_path), composite_img)
        cv2.imwrite(str(mask_path), composite_mask)

        print(f"  💾 Saved to {img_path.name}")

    print(f"\n✨ Created {len(composites)} composite source images in {composite_dir}")
    return True


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"⚠️  Error creating composite sources: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
