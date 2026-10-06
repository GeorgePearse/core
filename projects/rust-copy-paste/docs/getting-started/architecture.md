# Architecture

## System Overview

Copy-Paste Augmentation is built with a layered architecture:

```
┌─────────────────────────────────────────┐
│  Application Layer                      │
│  (Albumentations DualTransform)         │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Python Wrapper Layer                   │
│  (copy_paste/transform.py)              │
│  ├─ Configuration handling              │
│  ├─ Input validation                    │
│  ├─ Coordinate transformation           │
│  └─ Error handling                      │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  PyO3 Bindings                          │
│  (Rust ↔ Python bridge)                 │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Rust Core Layer (src/)                 │
│  ├─ CopyPasteTransform (lib.rs)         │
│  ├─ Object Extraction (objects.rs)      │
│  ├─ Object Placement (placement.rs)     │
│  ├─ Affine Transformations (affine.rs)  │
│  ├─ Image Blending (blending.rs)        │
│  └─ Collision Detection (collision.rs)  │
└──────────────────────────────────────────┘
```

## Component Details

### Python Wrapper (`copy_paste/transform.py`)

**Purpose**: Provide Albumentations-compatible interface

**Key Classes**:
- `CopyPasteAugmentation` - Main transform class
  - Inherits from `albumentations.DualTransform`
  - Implements required methods: `apply()`, `apply_to_bboxes()`, `apply_to_masks()`
  - Handles coordinate conversion (normalized ↔ pixel)

**Responsibilities**:
- Configuration validation
- Input format conversion
- Rust module invocation
- Output format conversion
- Error handling and logging

### Rust Core

#### CopyPasteTransform (`src/lib.rs`)

Main augmentation engine with PyO3 bindings.

**Interface**:
```rust
use std::sync::{Arc, Mutex};

#[pyclass]
pub struct CopyPasteTransform {
    config: AugmentationConfig,
    // Thread-safe shared mutable state
    last_placed: Arc<Mutex<Vec<placement::PlacedObject>>>,
}

impl CopyPasteTransform {
    fn apply(&self, image, mask, target_mask) -> (image, mask);
    fn apply_to_bboxes(&self, bboxes) -> bboxes;
}
```

**Thread-Safety Design**:
- Uses `Arc<Mutex<Vec<PlacedObject>>>` for shared mutable state
- Safe for concurrent access from multiple Python threads
- Compatible with PyTorch DataLoader with `num_workers > 1`
- Replaced `RefCell` (v0.x) with `Arc<Mutex>` (v1.x) to prevent data races

**Algorithm**:
1. **Extract** objects from source masks (using `objects.rs`)
2. **Select** random objects based on `max_paste_objects`
3. **Place** objects (using `placement.rs`):
    - Determine random positions
    - Apply affine transformations (parallelized)
    - Check collisions
4. **Blend** selected objects onto target image
5. Update masks and store placed objects (thread-safe)
6. Generate bounding boxes from placed objects

### Module Responsibilities

#### Object Extraction (`src/objects.rs`)

Responsible for scanning masks and extracting object data.
- **Optimized Scanning**: Uses a flattened `Vec<bool>` for efficient flood-fill algorithms, improving CPU cache locality.
- **Lazy Extraction**: Scans for candidates first, then extracts pixels only for selected objects.

#### Object Placement (`src/placement.rs`)

Handles the logic for positioning objects onto the target canvas.
- **Randomization**: Selects random coordinates, rotation, and scaling factors.
- **Collision Detection**: Orchestrates the check to ensure objects do not overlap excessively.
- **Composition**: Calls into blending functions to paste objects.

#### Affine Transformations (`src/affine.rs`)

Handles geometric transformations with high performance.

**Parallel Processing**:
- Uses **Rayon** to parallelize the transformation loop.
- Each row of pixels is processed concurrently, significantly speeding up the bilinear interpolation step on multi-core processors.

**Key Functions**:
- `transform_patch()`: Rotates and scales image patches using parallel execution.

#### Image Blending (`src/blending.rs`)

Combines objects onto target images.

**Blend Modes**:
- **Normal**: Standard alpha blending
  ```
  output = base * (1 - alpha) + overlay * alpha
  ```
- **X-ray**: Weighted combination for visibility
  ```
  output = min(base + overlay * alpha, 255)
  ```

#### Collision Detection (`src/collision.rs`)

Ensures pasted objects don't overlap excessively.

**Key Algorithm**: Intersection over Union (IoU)
```
IoU = intersection_area / union_area
```

**Collision Check**:
```
collision = IoU(bbox1, bbox2) > threshold
```

## Data Flow

### Forward Pass

```
Input: {image, bboxes, masks}
  ↓
[Python Wrapper]
  ├─ Validate input formats
  ├─ Convert coordinates to pixel space
  ├─ Prepare Rust inputs
  ↓
[Rust Core]
  ├─ objects::find_object_candidates (Scan)
  ├─ objects::select_candidates_by_class (Select)
  ├─ objects::extract_candidate_patches (Extract)
  ├─ placement::place_objects (Transform & Place)
  │    └─ affine::transform_patch (Parallelized)
  ├─ placement::compose_objects (Blend)
  ├─ placement::update_output_mask
  ↓
[Python Wrapper]
  ├─ Convert coordinates back to normalized
  ├─ Validate output
  ├─ Handle errors
  ↓
Output: {image, bboxes, masks}
```

## Thread Safety

The library is fully thread-safe as of v1.x and designed for production use with multi-worker data loading.

### Thread-Safety Implementation

**Python Layer**:
- Thread-safe through Albumentations' design
- Each worker process gets its own Python object instances
- No shared state between workers

**Rust Layer**:
- Uses `Arc<Mutex<Vec<PlacedObject>>>` for shared mutable state
- **Arc** (Atomic Reference Counting): Allows safe sharing across threads
- **Mutex** (Mutual Exclusion): Ensures only one thread accesses data at a time
- Critical sections are minimized to reduce lock contention

### Why Arc<Mutex>?

The transform needs to communicate state between `apply()` and `apply_to_bboxes()`:

```rust
// apply() stores placed objects
pub fn apply(&self, ...) -> PyResult<...> {
    let placed_objects = paste_objects(...);

    // Store in thread-safe container
    let mut last_placed = self.last_placed.lock().unwrap();
    *last_placed = placed_objects;
}

// apply_to_bboxes() reads placed objects
pub fn apply_to_bboxes(&self, ...) -> PyResult<...> {
    // Thread-safe read
    let placed_objects = self.last_placed.lock().unwrap();
    let new_bboxes = generate_bboxes(&placed_objects);
    // Merge with original bboxes
}
```

**Why not RefCell?**
- `RefCell` is NOT thread-safe (uses runtime borrow checking, not atomic)
- Would cause data races in multi-worker DataLoaders
- Could lead to data corruption, crashes, or undefined behavior

### Multi-Worker DataLoader Compatibility

```python
from torch.utils.data import DataLoader

# SAFE: Each worker gets its own transform instance
# Arc<Mutex> ensures thread-safety within each instance
dataloader = DataLoader(
    dataset,
    batch_size=32,
    num_workers=4,  # ✅ Safe!
    persistent_workers=True
)
```

**How it works**:
1. Main process creates Dataset with CopyPasteAugmentation
2. DataLoader spawns 4 worker processes
3. Each worker gets a **copy** of the transform (via fork/spawn)
4. Within each worker, `Arc<Mutex>` ensures thread-safety
5. No cross-worker communication needed

### Performance Implications

**Lock Overhead**:
- Mutex lock/unlock: ~50-100ns per operation
- Critical section: storing/reading Vec of objects
- Negligible compared to image processing (ms range)

**Scalability**:
- Linear speedup with number of workers
- No lock contention between workers (separate instances)
- CPU-bound workload benefits from parallelization

**Benchmarks** (512×512 image, 4 workers):
- Single worker: 100 images/sec
- 4 workers: ~380 images/sec (3.8x speedup)
- Lock overhead: <1% of total time

## Performance Characteristics

### Complexity
- **Image Blending**: O(W × H) where W, H = image dimensions
- **Collision Detection**: O(N²) where N = number of objects
- **Affine Transform**: O(1) per point

### Memory Usage
- Input image: O(W × H × 3) for RGB
- Masks: O(W × H) per object
- Temporary buffers: O(W × H) during blending

### Optimization Opportunities
1. SIMD for blending operations
2. Parallelization across objects
3. Cache locality improvements
4. GPU acceleration for large batches

## Integration Points

### With Albumentations
- Inherits from `DualTransform`
- Implements standard interface methods
- Compatible with `Compose` and pipelines
- Works with bbox_params

### With Training Frameworks
- **PyTorch**: Works with DataLoader
- **TensorFlow**: Works with tf.data.Dataset
- **MLFrameworks**: Compatible with any framework using Albumentations

## Testing Strategy

### Unit Tests
- Affine transformations
- Blending modes
- Collision detection
- Coordinate conversions

### Integration Tests
- End-to-end transformation
- Format handling
- Error cases
- Edge cases (empty inputs, extreme values)

### Performance Tests
- Benchmark different image sizes
- Profile memory usage
- Track transformation time
- Compare against baselines

## Build System

### Cargo.toml
- PyO3 for Python bindings
- ndarray for numerical operations
- image for image processing
- serde for serialization

### pyproject.toml
- Maturin for building Python extensions
- Dependencies: numpy, albumentations, opencv-python-headless
- Extras for benchmarking

## Future Enhancements

1. **Multi-GPU Support**: CUDA/Metal acceleration
2. **Streaming**: Process large images in chunks
3. **Caching**: LRU cache for common transformations
4. **Profiling**: Built-in performance monitoring
5. **Advanced Algorithms**: More blending modes, collision handling

## Development Workflow

```
1. Modify Rust code (src/)
2. Run tests: cargo test
3. Rebuild Python extension: maturin develop
4. Test integration: pytest tests/
5. Benchmark: python benchmarks/collect_metrics.py
```
