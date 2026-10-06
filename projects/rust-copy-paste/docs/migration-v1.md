# Migration Guide: v0.x to v1.x

This guide helps you upgrade from version 0.x to 1.x of the copy-paste augmentation library. Version 1.x includes critical bug fixes, thread-safety improvements, and breaking API changes.

## Breaking Changes

### 1. Bounding Box Behavior Change (CRITICAL)

**What Changed:**
The `apply_to_bboxes()` function now **merges** newly pasted bounding boxes with the original input bboxes, rather than replacing them entirely.

**Before (v0.x):**
```python
# Original bboxes were discarded, only new pasted objects returned
original_bboxes = [(0.1, 0.2, 0.3, 0.4, 'person')]
result = transform(image=image, mask=mask, bboxes=original_bboxes)
# result['bboxes'] = only new pasted objects (original lost)
```

**After (v1.x):**
```python
# Original bboxes are preserved and merged with new ones
original_bboxes = [(0.1, 0.2, 0.3, 0.4, 'person')]
result = transform(image=image, mask=mask, bboxes=original_bboxes)
# result['bboxes'] = original_bboxes + new pasted objects
```

**Why This Change:**
This aligns with the Albumentations API contract, where transforms are expected to preserve and augment existing annotations, not replace them.

**Migration Steps:**
1. **No action needed** if you want both original and pasted objects (recommended)
2. **If you need only pasted objects:** Filter the results manually:
   ```python
   result = transform(image=image, mask=mask, bboxes=original_bboxes)
   # Get only new objects (those beyond original count)
   new_objects_only = result['bboxes'][len(original_bboxes):]
   ```

### 2. Exception Handling Changes

**What Changed:**
The library now raises specific exception types instead of generic `Exception`.

**Exception Types:**
- `ValueError`: Invalid input (dimensions ≤ 0, shape mismatches, wrong channel counts)
- `RuntimeError`: Internal Rust implementation errors

**Before (v0.x):**
```python
try:
    result = transform(image=image, mask=mask)
except Exception as e:
    # Generic exception, unclear what went wrong
    handle_error(e)
```

**After (v1.x):**
```python
try:
    result = transform(image=image, mask=mask)
except ValueError as e:
    # Input validation failed - fix your inputs
    logger.error(f"Invalid input: {e}")
except RuntimeError as e:
    # Rust implementation error - may need to report bug
    logger.error(f"Augmentation failed: {e}")
```

**Migration Steps:**
1. Update exception handlers to catch `ValueError` and `RuntimeError`
2. Review error messages - they're now much more specific
3. Remove workarounds for silent failures (validation now explicit)

## New Features

### Thread-Safety

**What's New:**
The entire augmentation pipeline is now thread-safe using `Arc<Mutex>` internally.

**Benefits:**
- ✅ Safe to use with PyTorch `DataLoader(num_workers > 0)`
- ✅ Safe for concurrent augmentation pipelines
- ✅ No data corruption in multi-threaded scenarios

**Example:**
```python
from torch.utils.data import DataLoader
from copy_paste import CopyPasteAugmentation

class AugmentedDataset(Dataset):
    def __init__(self):
        # Safe to share across workers
        self.transform = CopyPasteAugmentation(
            image_width=512,
            image_height=512,
            max_paste_objects=3
        )

    def __getitem__(self, idx):
        # Thread-safe augmentation
        return self.transform(image=img, mask=mask)

# Safe with multiple workers!
loader = DataLoader(dataset, batch_size=32, num_workers=4)
```

### Improved Input Validation

**What's New:**
Comprehensive validation prevents cryptic errors:

- ✅ Image dimensions must be > 0
- ✅ Image must have exactly 3 channels (BGR)
- ✅ Masks must have exactly 1 channel
- ✅ Image and mask dimensions must match
- ✅ object_counts values must be non-negative integers

**Example Error Messages:**
```python
# Before: Cryptic Rust panic or silent failure
# After: Clear validation error
ValueError: Image dimensions (0, 512) must be > 0
ValueError: Image dimensions (512, 512) must match mask dimensions (256, 256)
ValueError: object_counts['person'] must be non-negative integer, got -1
```

### Performance Improvements

**What's New:**
- Bounding box calculation optimized (4x fewer iterations)
- Flood fill has maximum iteration limits (DoS prevention)
- Bounds checking prevents panics

## Verification Steps

After upgrading, verify your integration:

1. **Check bounding box handling:**
   ```python
   # Ensure you're getting both original and pasted bboxes
   assert len(result['bboxes']) >= len(original_bboxes)
   ```

2. **Test thread-safety:**
   ```python
   # Run with multiple workers
   loader = DataLoader(dataset, num_workers=4)
   for batch in loader:
       assert batch is not None  # No corruption
   ```

3. **Verify error handling:**
   ```python
   # Invalid inputs should raise ValueError
   with pytest.raises(ValueError):
       transform(image=np.zeros((0, 512, 3)), mask=mask)
   ```

## Getting Help

If you encounter issues during migration:

1. Check the [FAQ](faq.md#thread-safety) for common questions
2. Review the [API Reference](user-guide/api-reference.md) for updated behavior
3. See [Albumentations Integration](user-guide/albumentations.md) for updated examples
4. Open an issue on [GitHub](https://github.com/GeorgePearse/rust-copy-paste/issues)

## Changelog Summary

**Critical Fixes:**
- Thread-safety with `Arc<Mutex>` (data race prevention)
- Bounding box merging (API compliance)
- Specific exception types (better debugging)
- Comprehensive input validation

**Improvements:**
- 4x faster bbox calculation
- DoS prevention in flood fill
- Panic prevention with bounds checking
- Clear error messages with tracebacks
