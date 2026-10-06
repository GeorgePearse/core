# Copy-Paste Augmentation

A high-performance, Rust-based copy-paste augmentation transform for object detection and instance segmentation, with full Albumentations integration.

## 🚀 Features

- **Pure Rust Core**: High-performance implementation using PyO3 bindings
- **Albumentations Compatible**: Drop-in replacement for Albumentations DualTransform
- **Type Safe**: Full type safety in both Rust and Python
- **Production Ready**: Comprehensive testing and CI/CD pipelines
- **Performance Metrics**: Automated benchmarking and metrics dashboard
- **Flexible Configuration**: Extensive parameters for fine-tuning augmentation

## 📊 Key Capabilities

- **Image Augmentation**: Copy objects from source images and paste onto targets
- **Geometric Transformations**: Support for rotation, scaling, and translation
- **Advanced Blending**: Normal and X-ray blending modes
- **Collision Detection**: IoU-based overlap checking
- **Mask Support**: Automatic mask generation and transformation
- **Bbox Support**: Automatic bounding box transformation

## ✨ Performance

Rust implementation enables **5-10x speedup** over pure Python implementations while maintaining full compatibility with Albumentations pipelines.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  Python Application / Training Pipeline         │
│         (Albumentations-based)                  │
└──────────────┬──────────────────────────────────┘
               │
        ┌──────▼──────┐
        │  Transform  │
        │  (Python)   │
        └──────┬──────┘
               │
        ┌──────▼──────────────┐
        │  Rust Core (_core)  │
        │  ├─ CopyPaste       │
        │  ├─ Affine          │
        │  ├─ Blending        │
        │  └─ Collision       │
        └─────────────────────┘
```

## 🚀 Quick Start

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
        p=0.5
    ),
], bbox_params=A.BboxParams(format='albumentations'))

# Apply to image with bboxes and masks
result = transform(
    image=image,
    bboxes=bboxes,
    masks=masks
)
```

## 📚 Documentation

- [Getting Started](getting-started/installation.md) - Installation and setup
- [Quick Start](getting-started/quickstart.md) - Basic usage example
- [Architecture](getting-started/architecture.md) - System design overview
- [API Reference](user-guide/api-reference.md) - Complete API documentation
- [Performance Metrics](performance/metrics.md) - Benchmark results and trends

## 🧪 Testing

Comprehensive test suite with 50+ tests covering:
- Transform initialization and configuration
- Image format handling
- Bounding box transformations
- Mask processing
- Edge cases and error handling

Run tests with:
```bash
pytest tests/ -v
```

## 📈 Benchmarks

View performance metrics and trends on the [Metrics Dashboard](https://georgepearse.github.io/rust-copy-paste/).

## 📝 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions are welcome! See [Contributing Guide](development/contributing.md) for details.
