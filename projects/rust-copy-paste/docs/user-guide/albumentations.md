# Albumentations Integration

The Copy-Paste augmentation is fully integrated with Albumentations, allowing seamless integration into your existing augmentation pipelines.

## Basic Usage

```python
import albumentations as A
from copy_paste import CopyPasteAugmentation

# Create transform
transform = A.Compose([
    CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=3,
        p=0.5
    ),
], bbox_params=A.BboxParams(format='albumentations'))

# Apply to image data
result = transform(
    image=image,
    bboxes=bboxes,
    masks=masks
)
```

## Parameters

The `CopyPasteAugmentation` transform accepts the following parameters:

- `image_width` (int): Target image width
- `image_height` (int): Target image height
- `max_paste_objects` (int): Maximum number of objects to paste
- `use_rotation` (bool): Enable object rotation
- `use_scaling` (bool): Enable object scaling
- `blend_mode` (str): Blending mode ('normal' or 'xray')
- `p` (float): Probability of applying the transform (0-1)

## Bounding Box Support

The transform automatically handles bounding box transformations:

```python
bbox_params = A.BboxParams(
    format='albumentations',
    min_area=0,
    min_visibility=0
)

transform = A.Compose([
    CopyPasteAugmentation(...),
], bbox_params=bbox_params)
```

## Mask Support

Both binary masks and instance segmentation masks are supported:

```python
result = transform(
    image=image,
    bboxes=bboxes,
    masks=masks  # List of boolean arrays
)
```

## Pipeline Integration

Combine with other Albumentations transforms:

```python
transform = A.Compose([
    A.Resize(512, 512),
    CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=3,
        p=0.8
    ),
    A.HorizontalFlip(p=0.5),
    A.RandomBrightnessContrast(p=0.2),
    A.Normalize(),
], bbox_params=bbox_params)
```

## PyTorch DataLoader Integration

This library is fully thread-safe and designed for production use with PyTorch's multi-worker data loading. Here's a complete, production-ready example.

### Complete Example

```python
import os
import numpy as np
import cv2
import torch
from torch.utils.data import Dataset, DataLoader
import albumentations as A
from copy_paste import CopyPasteAugmentation

class ObjectDetectionDataset(Dataset):
    """
    Production-ready Dataset for object detection with copy-paste augmentation.

    Handles variable numbers of bounding boxes per image and integrates
    seamlessly with multi-worker DataLoaders.
    """

    def __init__(self, image_paths, annotations, transform=None):
        """
        Args:
            image_paths: List of paths to images
            annotations: List of dicts with 'boxes' (pascal_voc format) and 'labels'
            transform: Albumentations Compose pipeline
        """
        self.image_paths = image_paths
        self.annotations = annotations
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        # Load image (BGR format for OpenCV)
        image = cv2.imread(self.image_paths[idx])
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Get annotations
        boxes = self.annotations[idx]['boxes']  # [[x_min, y_min, x_max, y_max], ...]
        labels = self.annotations[idx]['labels']  # [class_id, class_id, ...]

        # Apply augmentations
        if self.transform:
            try:
                transformed = self.transform(
                    image=image,
                    bboxes=boxes,
                    labels=labels
                )
                image = transformed['image']
                boxes = transformed['bboxes']
                labels = transformed['labels']
            except (ValueError, RuntimeError) as e:
                # Augmentation failed - return original data
                # This handles edge cases like empty masks or invalid inputs
                print(f"Augmentation failed for {self.image_paths[idx]}: {e}")

        # Convert to tensors
        image = torch.from_numpy(image).permute(2, 0, 1).float()  # HWC -> CHW

        # Handle case where all boxes were removed by augmentation
        if len(boxes) == 0:
            boxes = torch.zeros((0, 4), dtype=torch.float32)
            labels = torch.zeros((0,), dtype=torch.int64)
        else:
            boxes = torch.as_tensor(boxes, dtype=torch.float32)
            labels = torch.as_tensor(labels, dtype=torch.int64)

        # Return in torchvision format (dict per image)
        target = {
            'boxes': boxes,
            'labels': labels,
            'image_id': torch.tensor([idx])
        }

        return image, target

def collate_fn(batch):
    """
    Custom collate function for object detection.

    Required because each image has a variable number of bounding boxes.
    The default PyTorch collate would fail trying to stack them.
    """
    images, targets = tuple(zip(*batch))
    images = torch.stack(images, dim=0)
    return images, targets

# Setup augmentation pipeline
transform = A.Compose([
    A.Resize(512, 512),

    # Copy-paste augmentation - adds new objects to images
    # Note: This merges new bboxes with original ones (v1.x behavior)
    CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=3,
        use_rotation=True,
        rotation_range=(-30, 30),
        use_scaling=True,
        scale_range=(0.8, 1.2),
        p=0.5
    ),

    # Additional spatial augmentations
    A.HorizontalFlip(p=0.5),
    A.RandomSizedBBoxSafeCrop(512, 512, p=0.3),

    # Pixel-level augmentations
    A.RandomBrightnessContrast(p=0.2),
    A.RGBShift(p=0.2),
    A.Blur(blur_limit=3, p=0.1),

    # Normalization
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
], bbox_params=A.BboxParams(
    format='pascal_voc',  # [x_min, y_min, x_max, y_max]
    label_fields=['labels'],  # CRITICAL: Don't forget this!
    min_area=1,
    min_visibility=0.3
))

# Create dataset and dataloader
dataset = ObjectDetectionDataset(
    image_paths=['path/to/img1.jpg', 'path/to/img2.jpg'],
    annotations=[
        {'boxes': [[10, 20, 100, 200]], 'labels': [1]},
        {'boxes': [[50, 60, 150, 250], [200, 100, 300, 400]], 'labels': [1, 2]},
    ],
    transform=transform
)

# Multi-worker DataLoader - SAFE with thread-safe augmentation!
dataloader = DataLoader(
    dataset,
    batch_size=4,
    shuffle=True,
    num_workers=4,  # Thread-safe! ✅
    collate_fn=collate_fn,
    pin_memory=True,
    persistent_workers=True  # Keeps workers alive between epochs
)

# Training loop
for epoch in range(num_epochs):
    for images, targets in dataloader:
        # images: tensor of shape [batch_size, 3, 512, 512]
        # targets: list of dicts, one per image
        #   Each dict has:
        #     'boxes': tensor of shape [num_boxes_in_image, 4]
        #     'labels': tensor of shape [num_boxes_in_image]
        #     'image_id': tensor of shape [1]

        # IMPORTANT: Number of boxes varies per image due to:
        # 1. Original annotations (variable object counts)
        # 2. Copy-paste augmentation (adds objects)
        # 3. Cropping augmentations (removes objects)

        images = images.to(device)
        targets = [{k: v.to(device) for k, v in t.items()} for t in targets]

        # Forward pass
        loss_dict = model(images, targets)
        losses = sum(loss for loss in loss_dict.values())

        # Backward pass
        optimizer.zero_grad()
        losses.backward()
        optimizer.step()
```

### Key Features Demonstrated

1. **Thread-Safe Multi-Worker Loading**
   - `num_workers=4` safely parallelizes data loading
   - No data corruption or race conditions (Arc<Mutex> internally)
   - `persistent_workers=True` for even better performance

2. **Bbox Merging Behavior (v1.x)**
   - Copy-paste augmentation **merges** new objects with original ones
   - Training loop receives variable numbers of boxes per image
   - Loss function must handle variable-length targets

3. **Robust Error Handling**
   - Try/except in `__getitem__` handles augmentation failures gracefully
   - Empty bbox handling prevents training crashes
   - Validates inputs before Rust processing

4. **Production Best Practices**
   - Custom `collate_fn` for variable-sized targets
   - Proper tensor conversions (HWC → CHW for images)
   - Pin memory for faster GPU transfers
   - Torchvision-compatible target format

### Important Notes

!!! warning "Bbox Merging in v1.x"
    The copy-paste transform **merges** new bounding boxes with the original ones instead of replacing them. This means:

    - Input: 2 original objects
    - After copy-paste with `max_paste_objects=3`: Up to 5 total objects (2 original + 3 pasted)
    - Your model and loss function must handle variable numbers of boxes per image

    See the [Migration Guide](../migration-v1.md) for details if upgrading from v0.x.

!!! success "Thread-Safe for DataLoader"
    As of v1.x, all operations are thread-safe. You can safely use `num_workers > 1` without risk of data corruption, race conditions, or segfaults.

### Integration with Popular Frameworks

#### Torchvision Models (Faster R-CNN, RetinaNet, etc.)

```python
from torchvision.models.detection import fasterrcnn_resnet50_fpn

model = fasterrcnn_resnet50_fpn(pretrained=True)
model.train()

# The dataset format above works directly with torchvision models
for images, targets in dataloader:
    loss_dict = model(images, targets)
    # ... training logic
```

#### YOLO / Ultralytics

```python
# Convert targets to YOLO format in __getitem__
def __getitem__(self, idx):
    # ... augmentation code ...

    # Convert pascal_voc to YOLO format [x_center, y_center, width, height]
    boxes_yolo = []
    for box in boxes:
        x_min, y_min, x_max, y_max = box
        x_center = (x_min + x_max) / 2 / image_width
        y_center = (y_min + y_max) / 2 / image_height
        width = (x_max - x_min) / image_width
        height = (y_max - y_min) / image_height
        boxes_yolo.append([x_center, y_center, width, height])

    return image, torch.tensor(boxes_yolo), labels
```

## Performance Considerations

- The Rust backend provides **5-10x speedup** compared to pure Python implementations
- Optimal performance with batch sizes of 32 or larger
- Memory usage scales linearly with object database size
- Multi-worker DataLoader (4-8 workers) recommended for maximum throughput

## Troubleshooting

### Objects not being pasted
- Ensure `p > 0` to enable the transform
- Check that `max_paste_objects` is greater than 0
- Verify source images contain valid objects

### Bounding box issues
- Ensure bboxes are in the correct format (albumentations format: [x_min, y_min, x_max, y_max])
- Set appropriate `min_area` and `min_visibility` in `BboxParams`

### Performance issues
- Reduce `max_paste_objects` if processing is slow
- Consider reducing image dimensions if memory is constrained
