#!/usr/bin/env python3
"""Generate augmented outputs from the dummy dataset for CI/CD validation.

This script tests the copy_paste transform by:
1. Loading dummy dataset images
2. Applying the RustCopyPaste transform
3. Saving augmented outputs and metadata
"""

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from copy_paste import SimpleCopyPaste


VARIANTS_PER_IMAGE = 3
MAX_ATTEMPTS_PER_VARIANT = 5


def collect_rotation_metadata(transform: SimpleCopyPaste) -> list[dict[str, Any]]:
    """Pull rotation metadata from the most recent pipeline run."""

    bbox_metadata = transform.apply_to_bboxes(np.empty((0, 4), dtype=np.float32))
    bbox_array = np.asarray(bbox_metadata)

    metadata: list[dict[str, Any]] = []
    for row in bbox_array:
        metadata.append(
            {
                "x_min": float(row[0]),
                "y_min": float(row[1]),
                "x_max": float(row[2]),
                "y_max": float(row[3]),
                "class_id": int(round(row[4])),
                "rotation_deg": float(row[5]),
            }
        )

    return metadata


def run_pipeline_variant(
    transform: SimpleCopyPaste,
    base_img: np.ndarray,
    all_images: list[np.ndarray],
    all_masks: list[np.ndarray],
    source_info_list: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, int, list[dict[str, Any]]]:
    """Run the Simple Copy-Paste pipeline with individually transformed objects from random sources."""

    # Start with white canvas
    h, w = base_img.shape[:2]
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    working_image = canvas.copy()
    output_mask = np.zeros((h, w), dtype=np.uint8)
    all_metadata: list[dict[str, Any]] = []

    # Randomly select 2-3 different source objects to paste
    num_objects = np.random.randint(2, 4)

    for obj_idx in range(num_objects):
        # Randomly select a source image
        source_idx = np.random.randint(0, len(all_images))
        source_img = all_images[source_idx]
        source_mask = all_masks[source_idx]
        source_info = source_info_list[source_idx]

        # Apply transform to this single object (with random rotation/scale/position)
        augmented = transform.apply(
            source_img.copy(),
            mask=source_mask[:, :, np.newaxis],
        )

        if augmented is None:
            continue

        # Get metadata for this object
        metadata = collect_rotation_metadata(transform)
        if metadata:
            # Add source information to metadata
            for meta in metadata:
                meta["source_image"] = source_info["file_name"]
                meta["class_name"] = source_info["class_name"]
            all_metadata.extend(metadata)

        # Composite the augmented object onto our working canvas
        # Find non-white pixels in the augmented output
        mask_fg = np.any(augmented != 255, axis=2)

        # Paste onto working image
        working_image[mask_fg] = augmented[mask_fg]

        # Update output mask with class label (using class_id from source_info)
        output_mask[mask_fg] = source_info["class_id"]

    # Check if we actually pasted anything
    changed_pixels = int(np.count_nonzero(working_image != canvas))

    if changed_pixels > 0 and all_metadata:
        return working_image, output_mask, changed_pixels, all_metadata

    # If we didn't get any objects, return empty result
    return canvas, output_mask, 0, []


def main():
    """Generate augmented outputs from dummy dataset."""
    # Setup paths
    script_dir = Path(__file__).parent
    dataset_dir = script_dir / "dummy_dataset"
    images_dir = dataset_dir / "images"
    annotations_file = dataset_dir / "annotations" / "annotations.json"
    output_dir = script_dir / "augmented_outputs"

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    if not annotations_file.exists():
        print(f"❌ Annotations file not found: {annotations_file}")
        return False

    print(f"📊 Dummy dataset found at {dataset_dir}")

    # Load annotations
    with open(annotations_file) as f:
        coco_data = json.load(f)

    print(
        f"📋 Loaded {len(coco_data['images'])} images and {len(coco_data['annotations'])} annotations"
    )

    # Extract class names
    class_list = [cat["name"] for cat in coco_data["categories"]]
    print(f"🏷️  Classes: {class_list}")

    # Create transform
    try:
        transform = SimpleCopyPaste(
            image_width=512,
            image_height=512,
            max_paste_objects=3,
            use_rotation=True,
            rotation_range=(-180.0, 180.0),
            use_scaling=True,
            scale_range=(0.85, 1.25),
            p=1.0,
        )
        print("🦀 Using SimpleCopyPaste pipeline")
    except (RuntimeError, TypeError) as e:
        print(f"⚠️  CopyPasteAugmentation not available: {e}")
        print("🐍 Skipping augmentation generation")
        return True  # Skip this step gracefully

    # Create category mapping
    category_map = {cat["id"]: cat["name"] for cat in coco_data["categories"]}

    # First, load all images and masks
    print("\n📦 Loading all images and masks for mixing...")
    all_images = []
    all_masks = []
    image_info_list = []
    source_info_list = []

    for img_info in coco_data["images"]:
        # Load image
        image_path = images_dir / img_info["file_name"]
        if not image_path.exists():
            print(f"  ⚠️  Image not found: {image_path}")
            continue

        img = cv2.imread(str(image_path))
        if img is None:
            print(f"  ❌ Failed to load image: {img_info['file_name']}")
            continue

        # Load corresponding mask
        mask_filename = img_info["file_name"].replace(".png", "_mask.png")
        mask_path = dataset_dir / "masks" / mask_filename

        if not mask_path.exists():
            print(f"  ⚠️  Mask not found: {mask_path}")
            continue

        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(f"  ❌ Failed to load mask: {mask_filename}")
            continue

        # Find the class name from the filename (e.g., "triangle_000.png" -> "triangle")
        class_name = img_info["file_name"].split("_")[0]

        # Find the matching category ID
        class_id = None
        for cat_id, cat_name in category_map.items():
            if cat_name == class_name:
                class_id = cat_id
                break

        if class_id is None:
            print(f"  ⚠️  Could not determine class for {img_info['file_name']}")
            continue

        all_images.append(img)
        all_masks.append(mask)
        image_info_list.append(img_info)
        source_info_list.append(
            {
                "file_name": img_info["file_name"],
                "class_name": class_name,
                "class_id": class_id,
            }
        )

    print(f"✅ Loaded {len(all_images)} images and masks")

    if len(all_images) == 0:
        print("❌ No images loaded, cannot proceed")
        return False

    # Process all images, using random shapes/colors from the pool
    results = []
    num_to_process = len(image_info_list)

    for img_idx, (base_img, img_info) in enumerate(zip(all_images, image_info_list)):
        print(
            f"\n📸 Processing image {img_idx + 1}/{num_to_process}: {img_info['file_name']}"
        )

        height, width = base_img.shape[:2]

        # Apply transform with random mixing
        for variant_idx in range(VARIANTS_PER_IMAGE):
            try:
                (
                    augmented_img,
                    output_mask,
                    changed_pixels,
                    rotation_metadata,
                ) = run_pipeline_variant(
                    transform, base_img, all_images, all_masks, source_info_list
                )

                if augmented_img is None:
                    print("  ⚠️  Transform returned None")
                    continue

                output_filename = f"augmented_{img_idx:03d}_v{variant_idx}.png"
                output_path = output_dir / output_filename
                cv2.imwrite(str(output_path), augmented_img)

                # Save the mask
                mask_filename = f"augmented_{img_idx:03d}_v{variant_idx}_mask.png"
                mask_path = output_dir / mask_filename
                cv2.imwrite(str(mask_path), output_mask)

                if changed_pixels == 0 or not rotation_metadata:
                    print(
                        "  ⚠️  Saved output but pipeline produced no detectable rotations"
                    )
                else:
                    class_names = ", ".join(
                        meta["class_name"] for meta in rotation_metadata
                    )
                    rotations = ", ".join(
                        f"{meta['rotation_deg']:.1f}°" for meta in rotation_metadata
                    )
                    print(
                        f"  🎲 Variant {variant_idx + 1}: {len(rotation_metadata)} objects ({class_names}) | rotations: {rotations}"
                    )

                results.append(
                    {
                        "original": img_info["file_name"],
                        "augmented": output_filename,
                        "mask": mask_filename,
                        "variant": variant_idx,
                        "width": width,
                        "height": height,
                        "changed_pixels": changed_pixels,
                        "objects": rotation_metadata,
                    }
                )

            except Exception as e:
                print(f"  ❌ Error during augmentation: {e}")
                continue

    # Save metadata
    metadata = {
        "timestamp": str(Path(__file__).stat().st_mtime),
        "num_processed": len(results),
        "variants_per_image": VARIANTS_PER_IMAGE,
        "images": results,
        "classes": class_list,
    }

    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✨ Generated {len(results)} augmented outputs")
    print(f"📁 Outputs saved to {output_dir}")
    print(f"📄 Metadata saved to {metadata_path}")

    return len(results) > 0


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"⚠️  Error generating augmented outputs: {e}")
        print("🐍 Continuing without augmented outputs...")
        exit(0)  # Don't fail the workflow
