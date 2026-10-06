"""Create a dummy dataset with shapes for testing."""

import json
from pathlib import Path

import cv2
import numpy as np


def create_dummy_dataset(output_dir: str = "tests/dummy_dataset") -> dict:
    """
    Create a dummy dataset with triangles, circles, and squares.

    Creates:
    - Images with shapes drawn on them
    - Corresponding segmentation masks
    - COCO annotation file

    Args:
        output_dir: Directory to save the dataset

    Returns:
        Dictionary containing paths to images, masks, and annotations
    """
    output_path = Path(output_dir)
    images_dir = output_path / "images"
    masks_dir = output_path / "masks"
    annotations_dir = output_path / "annotations"

    # Create directories
    images_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)

    image_size = 512
    num_images = 9  # 3 images for each class

    # COCO format structure
    coco_data = {
        "info": {
            "description": "Dummy shapes dataset",
            "version": "1.0",
            "year": 2024,
        },
        "licenses": [],
        "images": [],
        "annotations": [],
        "categories": [
            {"id": 1, "name": "triangle", "supercategory": "shape"},
            {"id": 2, "name": "circle", "supercategory": "shape"},
            {"id": 3, "name": "square", "supercategory": "shape"},
        ],
    }

    annotation_id = 1
    image_id = 1

    # Create dataset
    shapes = [
        ("triangle", 1, draw_triangle),
        ("circle", 2, draw_circle),
        ("square", 3, draw_square),
    ]

    for shape_name, category_id, draw_func in shapes:
        for i in range(3):
            # Create image and mask
            image = (
                np.ones((image_size, image_size, 3), dtype=np.uint8) * 255
            )  # White background
            mask = np.zeros((image_size, image_size), dtype=np.uint8)

            # Draw shape
            draw_func(image, mask)

            # Save image
            image_filename = f"{shape_name}_{i:03d}.png"
            image_path = images_dir / image_filename
            cv2.imwrite(str(image_path), image)

            # Save mask
            mask_filename = f"{shape_name}_{i:03d}_mask.png"
            mask_path = masks_dir / mask_filename
            cv2.imwrite(str(mask_path), mask)

            # Add image to COCO
            coco_data["images"].append(
                {
                    "id": image_id,
                    "file_name": image_filename,
                    "height": image_size,
                    "width": image_size,
                }
            )

            # Calculate bounding box from mask
            coords = np.where(mask > 0)
            if len(coords[0]) > 0:
                y_min, y_max = int(coords[0].min()), int(coords[0].max())
                x_min, x_max = int(coords[1].min()), int(coords[1].max())
                bbox = [x_min, y_min, x_max - x_min, y_max - y_min]
                area = int(np.sum(mask > 0))

                # Add annotation to COCO
                coco_data["annotations"].append(
                    {
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": category_id,
                        "bbox": bbox,
                        "area": area,
                        "iscrowd": 0,
                        "segmentation": mask_to_coco_rle(mask),
                    }
                )

                annotation_id += 1

            image_id += 1

    # Save COCO annotations
    annotations_path = annotations_dir / "annotations.json"
    with open(annotations_path, "w") as f:
        json.dump(coco_data, f, indent=2)

    return {
        "images_dir": str(images_dir),
        "masks_dir": str(masks_dir),
        "annotations": str(annotations_path),
        "num_images": num_images,
    }


def draw_triangle(image: np.ndarray, mask: np.ndarray) -> None:
    """Draw a triangle on image and mask."""
    height, width = image.shape[:2]
    center_x, center_y = width // 2, height // 2
    size = 80

    # Define triangle points
    points = np.array(
        [
            [center_x, center_y - size],  # Top
            [center_x - size, center_y + size],  # Bottom left
            [center_x + size, center_y + size],  # Bottom right
        ],
        dtype=np.int32,
    )

    color = (0, 0, 255)  # Red in BGR
    cv2.fillPoly(image, [points], color)
    cv2.fillPoly(mask, [points], 255)


def draw_circle(image: np.ndarray, mask: np.ndarray) -> None:
    """Draw a circle on image and mask."""
    height, width = image.shape[:2]
    center = (width // 2, height // 2)
    radius = 70

    color = (0, 255, 0)  # Green in BGR
    cv2.circle(image, center, radius, color, -1)
    cv2.circle(mask, center, radius, 255, -1)


def draw_square(image: np.ndarray, mask: np.ndarray) -> None:
    """Draw a square on image and mask."""
    height, width = image.shape[:2]
    center_x, center_y = width // 2, height // 2
    size = 80

    top_left = (center_x - size, center_y - size)
    bottom_right = (center_x + size, center_y + size)

    color = (255, 0, 0)  # Blue in BGR
    cv2.rectangle(image, top_left, bottom_right, color, -1)
    cv2.rectangle(mask, top_left, bottom_right, 255, -1)


def mask_to_coco_rle(mask: np.ndarray) -> list:
    """
    Convert binary mask to COCO RLE format (simplified).
    Returns empty list as placeholder for actual RLE encoding.
    """
    # For simplicity, return empty list
    # In production, would use pycocotools.mask.encode()
    return []


if __name__ == "__main__":
    dataset_info = create_dummy_dataset()
    print("Dataset created successfully!")
    print(f"Images directory: {dataset_info['images_dir']}")
    print(f"Masks directory: {dataset_info['masks_dir']}")
    print(f"Annotations file: {dataset_info['annotations']}")
    print(f"Total images: {dataset_info['num_images']}")
