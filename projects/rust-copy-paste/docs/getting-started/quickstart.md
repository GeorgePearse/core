# Quick Start

Get started with copy-paste augmentation in 5 minutes.

!!! warning "Breaking Change in v1.x"
    **Upgrading from v0.x?** The `apply_to_bboxes()` behavior has changed. It now **merges** new bounding boxes with original ones instead of replacing them. This ensures proper Albumentations API compliance. See the [Migration Guide](../migration-v1.md) for details.

!!! success "Thread-Safe for Multi-Worker DataLoaders"
    As of v1.x, the augmentation pipeline is fully thread-safe. You can safely use it with PyTorch `DataLoader(num_workers > 0)` or any multi-threaded data loading pipeline without risk of data corruption.

## Basic Usage

### 1. Install the package

```bash
pip install copy-paste
```

### 2. Create a transform

```python
import albumentations as A
from copy_paste import CopyPasteAugmentation

transform = A.Compose([
    CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=3,
        use_rotation=True,
        use_scaling=True,
        p=0.5  # Apply with 50% probability
    ),
], bbox_params=A.BboxParams(format='albumentations'))
```

### 3. Apply to data

```python
import numpy as np

# Your image, bboxes, and masks
image = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
bboxes = np.array([
    [0.1, 0.1, 0.3, 0.3, 0],  # [x_min, y_min, x_max, y_max, class_id]
    [0.6, 0.6, 0.8, 0.8, 1],
])
masks = [
    np.zeros((512, 512), dtype=np.uint8),  # mask for first object
    np.zeros((512, 512), dtype=np.uint8),  # mask for second object
]

# Apply augmentation
augmented = transform(
    image=image,
    bboxes=bboxes,
    masks=masks
)

augmented_image = augmented['image']
augmented_bboxes = augmented['bboxes']
augmented_masks = augmented['masks']
```

## Configuration Options

```python
CopyPasteAugmentation(
    image_width=512,           # Output image width
    image_height=512,          # Output image height
    max_paste_objects=3,       # Max objects to paste per image
    object_counts=None,        # Optional: {'person': 2} to override max_paste_objects
    use_rotation=True,         # Enable random rotation
    use_scaling=True,          # Enable random scaling
    rotation_range=(-30, 30),  # Rotation range in degrees
    scale_range=(0.8, 1.2),    # Scaling factor range
    use_random_background=False,  # Generate random backgrounds
    blend_mode='normal',       # 'normal' or 'xray'
    p=1.0                      # Probability of applying transform
)
```

## Integration with Training Pipelines

### PyTorch Lightning Example

```python
import torch
from torch.utils.data import DataLoader, Dataset
import albumentations as A
from copy_paste import CopyPasteAugmentation

class MyDataset(Dataset):
    def __init__(self, images, bboxes, masks):
        self.transform = A.Compose([
            CopyPasteAugmentation(
                image_width=512,
                image_height=512,
                max_paste_objects=3,
                p=0.5
            ),
            # Add more transforms...
        ], bbox_params=A.BboxParams(format='albumentations'))

        self.images = images
        self.bboxes = bboxes
        self.masks = masks

    def __getitem__(self, idx):
        augmented = self.transform(
            image=self.images[idx],
            bboxes=self.bboxes[idx],
            masks=self.masks[idx]
        )

        return {
            'image': torch.from_numpy(augmented['image']).float(),
            'bboxes': torch.from_numpy(np.array(augmented['bboxes'])).float(),
            'masks': [torch.from_numpy(m).float() for m in augmented['masks']]
        }
```

### MMCV/MMDetection Example

```python
from mmdet.datasets.builder import PIPELINES
import albumentations as A
from copy_paste import CopyPasteAugmentation

# Add to pipeline config:
pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='LoadAnnotations', with_bbox=True, with_mask=True),
    dict(
        type='CopyPasteAugmentation',
        image_width=512,
        image_height=512,
        max_paste_objects=3,
        p=0.5
    ),
]
```

## Advanced Usage

### Custom Blending Modes

```python
transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    blend_mode='xray',  # Use X-ray blending instead of normal
    p=1.0
)
```

### Random Backgrounds

```python
transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    use_random_background=True,  # Generate random backgrounds
    max_paste_objects=5,
    p=0.7
)
```

### Rotation and Scaling

```python
transform = CopyPasteAugmentation(
    image_width=512,
    image_height=512,
    use_rotation=True,
    rotation_range=(-45, 45),  # Range in degrees
    use_scaling=True,
    scale_range=(0.5, 2.0),    # Scale factor range
    p=0.8
)
```

## Performance Tips

1. **Batch Processing**: Use DataLoader with multiple workers (now thread-safe!)
```python
# Safe to use multiple workers - no data corruption
loader = DataLoader(dataset, batch_size=32, num_workers=4,
                   persistent_workers=True)
```

2. **Probability Control**: Adjust `p` to balance speed vs augmentation
```python
CopyPasteAugmentation(..., p=0.3)  # Apply less frequently for speed
```

3. **Image Size**: Larger images = more computation
```python
CopyPasteAugmentation(image_width=256, image_height=256)  # Faster
```

## Next Steps

- Explore [configuration options](../user-guide/configuration.md)
- View [API reference](../user-guide/api-reference.md)
- Check [performance benchmarks](../performance/benchmarks.md)
- See [architecture overview](architecture.md)
