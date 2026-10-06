# Testing

The Copy-Paste augmentation project includes comprehensive testing for both Rust and Python components.

## Test Structure

Tests are organized as follows:

```
tests/
├── test_core.py          # Python core functionality tests
├── test_transforms.py    # Transform integration tests
├── test_albumentations.py # Albumentations integration tests
└── integration_tests/    # Rust integration tests
```

## Running Tests

### All Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=copy_paste --cov-report=html
```

### Python Tests

```bash
# Run only Python tests
pytest tests/ -v

# Run specific test file
pytest tests/test_core.py -v

# Run specific test
pytest tests/test_core.py::test_basic_functionality -v
```

### Rust Tests

```bash
# Run Rust unit tests
cargo test

# Run with output
cargo test -- --nocapture

# Run integration tests
cargo test --test '*'
```

## Test Categories

### Unit Tests

Unit tests verify individual function behavior:

```bash
pytest tests/ -k "unit" -v
```

### Integration Tests

Integration tests verify component interactions:

```bash
pytest tests/ -k "integration" -v
```

### Performance Tests

Performance benchmarks:

```bash
# Run benchmarks
pytest tests/ -k "benchmark" -v

# Collect metrics
python metrics/collect_metrics.py
```

## Writing Tests

### Python Tests

Example test structure:

```python
import pytest
from copy_paste import CopyPasteAugmentation

def test_basic_functionality():
    """Test basic transform initialization."""
    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=3
    )
    assert transform is not None

def test_with_bboxes():
    """Test transform with bounding boxes."""
    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512
    )
    # Apply transform...
    assert len(result['bboxes']) >= 0
```

### Rust Tests

Example Rust test:

```rust
#[test]
fn test_transform_basic() {
    let transform = CopyPaste::new(512, 512);
    assert!(transform.is_ok());
}
```

## Code Coverage

Generate coverage reports:

```bash
# HTML coverage report
pytest tests/ --cov=copy_paste --cov-report=html
# View in browser: htmlcov/index.html

# Terminal coverage report
pytest tests/ --cov=copy_paste --cov-report=term-missing
```

## Continuous Integration

Tests are automatically run on every pull request via GitHub Actions. See `.github/workflows/` for CI configuration.

## Troubleshooting

### Import Errors
- Ensure the package is installed: `pip install -e .`
- Rebuild Rust components: `cargo build`

### Test Failures
- Check for stale bytecode: `find . -type d -name __pycache__ -exec rm -r {} +`
- Rebuild everything: `cargo clean && cargo build`

### Performance Test Issues
- Ensure system is not under heavy load
- Close other applications
- Run tests multiple times for consistency
