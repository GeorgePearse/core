# Configuration

## Configuration Overview

Configure copy-paste augmentation for your specific use case.

## Basic Configuration

```python
from copy_paste import CopyPasteAugmentation

transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    max_paste_objects=1,
    p=0.5
)
```

## Parameter Tuning Guide

### Image Size

Choose based on your dataset:

```python
# Small images - faster processing
CopyPasteAugmentation(image_width=256, image_height=256)

# Standard size
CopyPasteAugmentation(image_width=512, image_height=512)

# Large images - better quality but slower
CopyPasteAugmentation(image_width=1024, image_height=1024)
```

### Object Count

Balance augmentation diversity with speed. You can control the global maximum or specify exact counts per class.

```python
# Global limit (random classes)
CopyPasteAugmentation(max_paste_objects=3)

# Per-class control (Overrides max_paste_objects)
CopyPasteAugmentation(
    object_counts={
        'person': 2,  # Exactly 2 people
        'car': 1      # Exactly 1 car
    }
)
```

### Geometric Transformations

Configure rotation and scaling:

```python
# Conservative transformations
CopyPasteAugmentation(
    use_rotation=True,
    rotation_range=(-15, 15),
    use_scaling=True,
    scale_range=(0.9, 1.1)
)

# Moderate transformations
CopyPasteAugmentation(
    use_rotation=True,
    rotation_range=(-30, 30),
    use_scaling=True,
    scale_range=(0.8, 1.2)
)

# Aggressive transformations
CopyPasteAugmentation(
    use_rotation=True,
    rotation_range=(-45, 45),
    use_scaling=True,
    scale_range=(0.5, 2.0)
)
```

### Blending Modes

Choose blending strategy:

```python
# Standard alpha blending (most common)
CopyPasteAugmentation(blend_mode='normal')

# X-ray style (more visible overlays)
CopyPasteAugmentation(blend_mode='xray')
```

### Probability Control

Adjust application frequency:

```python
# Never apply
p=0.0

# Rarely apply
p=0.2

# Sometimes apply
p=0.5

# Often apply
p=0.8

# Always apply
p=1.0
```

## Preset Configurations

### For Detection Models

```python
detection_transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    max_paste_objects=2,
    use_rotation=True,
    rotation_range=(-30, 30),
    use_scaling=True,
    scale_range=(0.8, 1.2),
    blend_mode='normal',
    p=0.5
)
```

### For Segmentation Models

```python
segmentation_transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    max_paste_objects=3,
    use_rotation=True,
    rotation_range=(-45, 45),
    use_scaling=True,
    scale_range=(0.7, 1.3),
    blend_mode='xray',
    p=0.6
)
```

### For Small Object Detection

```python
small_object_transform = CopyPasteAugmentation(
    image_width=1024,  # Larger for better small object detail
    image_height=1024,
    max_paste_objects=5,  # More objects for diversity
    use_rotation=True,
    rotation_range=(-30, 30),
    use_scaling=True,
    scale_range=(0.5, 2.0),  # Wider range for size variation
    p=0.7
)
```

### For Real-time Applications

```python
realtime_transform = CopyPasteAugmentation(
    image_width=256,  # Smaller for speed
    image_height=256,
    max_paste_objects=1,  # Fewer objects
    use_rotation=False,  # Skip rotation for speed
    use_scaling=False,   # Skip scaling for speed
    blend_mode='normal',
    p=0.3  # Apply less frequently
)
```

## Environment-Specific Configuration

### Development

```python
dev_transform = CopyPasteAugmentation(
    image_width=256,
    image_height=256,
    max_paste_objects=1,
    p=0.5  # Quick feedback
)
```

### Training

```python
train_transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    max_paste_objects=3,
    p=0.6  # Moderate augmentation
)
```

### Validation/Testing

```python
# Don't apply augmentation during validation
val_transform = A.Compose([
    # Other transforms only
])
```

## Integration with Albumentations Pipelines

```python
import albumentations as A
from copy_paste import CopyPasteAugmentation

train_transform = A.Compose([
    # Data loading
    # Augmentation with copy-paste
    CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=2,
        p=0.5
    ),
    # Other augmentations
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.2),
    # Normalization
    A.Normalize(),
], bbox_params=A.BboxParams(format='albumentations'))
```

## Configuration Recommendations

### Based on Dataset Size

- **Small dataset** (<1000 images): Aggressive augmentation
  ```python
  max_paste_objects=5, p=0.8
  ```

- **Medium dataset** (1000-10000): Moderate augmentation
  ```python
  max_paste_objects=3, p=0.5
  ```

- **Large dataset** (>10000): Conservative augmentation
  ```python
  max_paste_objects=1, p=0.3
  ```

### Based on Object Complexity

- **Simple objects** (clear, well-separated): More aggressive
  ```python
  rotation_range=(-45, 45), scale_range=(0.5, 2.0)
  ```

- **Complex objects** (occlusions, overlaps): More conservative
  ```python
  rotation_range=(-15, 15), scale_range=(0.8, 1.2)
  ```

## Troubleshooting Configuration

### Not seeing augmentation effect

- Increase `p` (probability)
- Increase `max_paste_objects`
- Check that transforms are in correct position

### Too much augmentation

- Decrease `p` or `max_paste_objects`
- Reduce `rotation_range` or `scale_range`
- Use `blend_mode='normal'` instead of 'xray'

### Performance issues

- Reduce `image_width`/`image_height`
- Decrease `max_paste_objects`
- Set `use_rotation=False` or `use_scaling=False`
- Decrease `p` to apply less frequently

## Configuration Files

See [API Reference](api-reference.md) for all parameters and defaults.
