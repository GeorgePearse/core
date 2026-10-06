# Visual Outputs - Copy-Paste Pipeline Examples

This directory contains visual examples and pipeline outputs demonstrating the copy-paste augmentation algorithm in action.

## Directory Structure

```
visual_outputs/
├── README.md                          # This file
├── pipeline_stages/                   # Step-by-step pipeline visualization
│   ├── 01_input_image.jpg            # Original source image
│   ├── 02_object_extraction.jpg      # Extracted objects with bounding boxes
│   ├── 03_selected_objects.jpg       # Objects selected for pasting
│   ├── 04_object_placement.jpg       # Objects placed on target (before blending)
│   └── 05_final_output.jpg           # Final augmented image
├── comparisons/                       # Side-by-side comparisons
│   ├── original_vs_augmented.png
│   └── collision_detection_demo.png
└── algorithm_flow/                    # Algorithm flow diagrams
    ├── extraction_flow.txt
    ├── placement_flow.txt
    └── composition_flow.txt
```

## Pipeline Stages

### 1. Object Extraction
- **Input**: Source image + mask
- **Process**: Flood-fill algorithm identifies connected components
- **Output**: List of `ExtractedObject` with image patches and bounding boxes

### 2. Per-Class Selection
- **Input**: Extracted objects + object_counts config
- **Process**: Random selection without replacement per class
- **Output**: Selected objects based on exact class counts

### 3. Placement with Collision Detection
- **Input**: Selected objects + target dimensions
- **Process**: Random position, rotation, scaling + IoU-based collision detection
- **Output**: `PlacedObject` instances with transformed bounding boxes

### 4. Image Composition
- **Input**: Target image + placed objects
- **Process**: Alpha blending using object masks
- **Output**: Augmented image with pasted objects

### 5. Mask Generation
- **Input**: Output mask + placed objects
- **Process**: Update mask with new object class IDs
- **Output**: Updated segmentation mask for new objects

## Example Usage with Visualization

```python
from copy_paste import CopyPasteAugmentation
import cv2
import numpy as np
from pathlib import Path

# Create transform
transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    object_counts={'person': 2, 'car': 1},
    use_rotation=True,
    use_scaling=True,
    p=1.0
)

# Load data
image = cv2.imread('input_image.jpg')
mask = cv2.imread('input_mask.png', cv2.IMREAD_GRAYSCALE)

# Apply augmentation
augmented = transform(image=image, mask=mask)
augmented_image = augmented['image']

# Save results
output_dir = Path(__file__).parent / 'pipeline_stages'
output_dir.mkdir(exist_ok=True)

cv2.imwrite(str(output_dir / '01_input_image.jpg'), image)
cv2.imwrite(str(output_dir / '05_final_output.jpg'), augmented_image)
```

## Configuration Examples

### High-Precision Pasting
```python
transform = CopyPasteAugmentation(
    image_width=1024,
    image_height=1024,
    object_counts={'person': 3, 'vehicle': 2},
    use_rotation=False,          # No rotation for precision
    use_scaling=False,           # No scaling for consistency
    rotation_range=(0, 0),
    scale_range=(1.0, 1.0),
    blend_mode='normal'
)
```

### Natural Augmentation
```python
transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    object_counts={'person': 2, 'bicycle': 1},
    use_rotation=True,
    use_scaling=True,
    rotation_range=(-30, 30),
    scale_range=(0.8, 1.2),
    blend_mode='normal'
)
```

### X-Ray Blending (for overlays)
```python
transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    object_counts={'annotation': 5},
    use_rotation=False,
    use_scaling=False,
    blend_mode='xray'            # X-ray blend for visibility
)
```

## Key Parameters Explained

- **object_counts**: Dict mapping class names (str) to exact counts
  - Example: `{'person': 2, 'car': 1}` means paste exactly 2 people and 1 car
  - Uses random selection without replacement

- **rotation_range**: Min/max rotation in degrees
  - Example: `(-30, 30)` for ±30 degree random rotation
  - Set `(0, 0)` to disable rotation

- **scale_range**: Min/max scale factors
  - Example: `(0.8, 1.2)` for 80-120% scale variation
  - Set `(1.0, 1.0)` to disable scaling

- **blend_mode**: `'normal'` or `'xray'`
  - `'normal'`: Standard alpha blending
  - `'xray'`: Lighter blend for overlay effects

## Performance Characteristics

All logic implemented in Rust for maximum performance:
- Object extraction: ~1-5ms for 256x256 image
- Object placement: ~2-10ms for 5 objects
- Composition: ~5-20ms for 512x512 image
- **Total**: ~10-35ms per augmentation

See `../benchmarks/` for detailed performance metrics.

## Generating Output Visualizations

To generate visualizations of the pipeline:

```bash
# Run the example script (when available)
python examples/visualize_pipeline.py \
    --input-image input.jpg \
    --input-mask mask.png \
    --output-dir examples/visual_outputs/pipeline_stages \
    --class-counts person:2 car:1
```

## Classes Represented

The examples use COCO dataset classes:
- **person**: 0
- **bicycle**: 1
- **car**: 2
- **motorcycle**: 3
- **bus**: 5
- **truck**: 8
- (and 80+ additional COCO classes)

Customize `object_counts` to control which classes appear in augmented images.
