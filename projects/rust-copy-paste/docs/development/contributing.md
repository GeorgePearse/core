# Contributing

We welcome contributions! This guide will help you get started with developing the Copy-Paste augmentation project.

## Prerequisites

- Rust 1.70+
- Python 3.8+
- Git

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/GeorgePearse/rust-copy-paste.git
cd rust-copy-paste
```

2. Install development dependencies:
```bash
uv pip install -e ".[dev]"
```

3. Build the Rust components:
```bash
cargo build
```

## Making Changes

### Rust Changes

1. Make your changes in the `src/` directory
2. Run tests: `cargo test`
3. Run clippy for linting: `cargo clippy`
4. Format code: `cargo fmt`

### Python Changes

1. Make changes in the `copy_paste/` directory
2. Run type checking with `pyright`
3. Format with `black`
4. Run linting with `ruff`

## Testing

### Unit Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_core.py -v

# Run with coverage
pytest tests/ --cov=copy_paste
```

### Integration Tests

```bash
# Run Rust integration tests
cargo test --test integration_tests
```

## Submitting Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes and commit: `git commit -am 'Add feature'`
3. Push to your fork: `git push origin feature/your-feature`
4. Submit a pull request

## Code Style

- Python: Follow PEP 8, use type hints
- Rust: Follow Rust conventions, use clippy recommendations
- Documentation: Write docstrings for all public functions

## Concurrency Guidelines

This library is thread-safe and designed for use with multi-worker PyTorch DataLoaders. When contributing, follow these guidelines:

### Thread-Safety Requirements

1. **Use Arc<Mutex> for Shared Mutable State**
   ```rust
   use std::sync::{Arc, Mutex};

   #[pyclass]
   pub struct CopyPasteTransform {
       config: AugmentationConfig,
       // CORRECT: Thread-safe shared state
       last_placed: Arc<Mutex<Vec<objects::PlacedObject>>>,
   }
   ```

   ❌ **Don't use RefCell** - not thread-safe:
   ```rust
   // WRONG: Will cause data races in multi-threaded contexts
   last_placed: RefCell<Vec<objects::PlacedObject>>
   ```

2. **Minimize Lock Contention**
   - Keep critical sections small
   - Don't hold locks across expensive operations
   - Consider using `RwLock` for read-heavy workloads

3. **Test Concurrency**
   - Add tests that verify thread-safety
   - Use `std::thread::spawn` to simulate concurrent access
   - Test with PyTorch DataLoader with `num_workers > 1`

   Example test:
   ```rust
   #[test]
   fn test_concurrent_access() {
       let transform = Arc::new(CopyPasteTransform::new(config));
       let handles: Vec<_> = (0..10)
           .map(|_| {
               let t = Arc::clone(&transform);
               thread::spawn(move || {
                   t.apply(&image, &mask).unwrap();
               })
           })
           .collect();

       for handle in handles {
           handle.join().unwrap();
       }
   }
   ```

### Error Handling Standards

The library uses specific exception types to provide clear error messages. Follow these standards:

1. **Use Specific Exception Types**
   - `ValueError`: Invalid input data (dimensions, format, shape mismatches)
   - `RuntimeError`: Internal implementation errors

   ```python
   # In Python wrapper code:
   try:
       result = self._core.apply(img)
   except ValueError as e:
       # Input validation failed - user error
       logger.warning(f"Invalid input: {e}")
       return img  # Return original unchanged
   except RuntimeError as e:
       # Internal error - may be a bug
       logger.error(f"Augmentation failed: {e}", exc_info=True)
       raise  # Re-raise for visibility
   ```

2. **Validate Inputs Early**
   - Check dimensions > 0
   - Verify channel counts (3 for images, 1 for masks)
   - Ensure image and mask dimensions match
   - Validate bbox formats and ranges

   ```python
   # Example validation
   if image_width <= 0 or image_height <= 0:
       raise ValueError(f"Image dimensions must be > 0, got ({image_width}, {image_height})")

   if img.ndim != 3 or img.shape[2] != 3:
       raise ValueError(f"Image must have 3 channels (BGR format), got shape {img.shape}")
   ```

3. **Provide Clear Error Messages**
   - Include expected vs actual values
   - Suggest fixes when possible
   - Use proper context in error messages

   ```rust
   // In Rust code:
   if width == 0 || height == 0 {
       return Err(PyValueError::new_err(format!(
           "Image dimensions must be > 0, got ({}, {})",
           width, height
       )));
   }
   ```

4. **Handle Edge Cases Gracefully**
   - Empty masks → return empty results
   - All bboxes removed by crop → return valid empty tensors
   - Invalid augmentation → return original data with warning

### API Contract Compliance

When modifying transform behavior, ensure compliance with Albumentations API:

1. **Preserve Original Annotations**
   - `apply_to_bboxes()` must **merge** new bboxes with originals
   - Don't discard input annotations unless explicitly transformed away

2. **Handle Variable-Length Outputs**
   - Bboxes and masks can have different lengths after augmentation
   - Return proper empty structures when no objects remain

3. **Support Standard Parameters**
   - All transforms should support `p` (probability parameter)
   - Implement `get_transform_init_args_names()` for serialization

### Performance Considerations

1. **Avoid Unnecessary Allocations**
   - Reuse buffers when possible
   - Use `Vec::with_capacity()` when size is known

2. **Optimize Hot Paths**
   - Bbox calculation is performance-critical
   - Minimize iterations (e.g., single-pass bbox extraction)
   - Add iteration limits to prevent DoS (e.g., flood fill)

3. **Profile Before Optimizing**
   ```bash
   # Profile with cargo flamegraph
   cargo install flamegraph
   cargo flamegraph --test integration_tests
   ```

### Documentation Requirements

1. **Public APIs Must Have Docstrings**
   - Python: Use Google-style docstrings
   - Rust: Use rustdoc with examples

2. **Module-Level Documentation**
   ```rust
   //! Brief description of module purpose.
   //!
   //! More detailed explanation of functionality,
   //! use cases, and implementation notes.
   ```

3. **Breaking Changes**
   - Document in CHANGELOG.md
   - Add migration guide for API changes
   - Update all relevant documentation

## Reporting Issues

Please report issues on the [GitHub issue tracker](https://github.com/GeorgePearse/rust-copy-paste/issues).

Include:
- Python version
- Rust version (if applicable)
- Minimal reproducible example
- Error messages or stack traces

## Questions?

Feel free to open an issue or discussion on GitHub!
