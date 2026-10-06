# Installation

## System Requirements

- **Python**: 3.9 or higher
- **Rust**: 1.70+ (for building from source)
- **OS**: Linux (x86_64), macOS, or Windows

## Pre-built Wheels

Pre-built wheels are available for Python 3.9-3.12 on Linux x86_64:

```bash
pip install copy-paste
```

## Build from Source

### Prerequisites

1. Install Rust toolchain:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

2. Clone the repository:
```bash
git clone https://github.com/GeorgePearse/rust-copy-paste.git
cd rust-copy-paste
```

### Building with Maturin

1. Install build dependencies:
```bash
pip install maturin
```

2. Build the extension:
```bash
maturin develop
```

Or build a wheel:
```bash
maturin build --release
pip install target/wheels/copy_paste-*.whl
```

### Building with pip

```bash
pip install -e .
```

This will automatically detect Rust and compile the extension.

## Installation with Development Dependencies

For development, install with optional dependencies:

```bash
pip install -e ".[benchmarks]"
```

This includes:
- `pytest-benchmark` - Benchmark testing
- `psutil` - System metrics collection
- Additional testing tools

## Verification

Verify the installation:

```python
from copy_paste import CopyPasteAugmentation
import albumentations as A

# Create a transform
transform = CopyPasteAugmentation(p=1.0)

print("✓ Copy-Paste augmentation installed successfully!")
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'copy_paste._core'"

The Rust extension failed to compile. Try:

1. Update Rust:
```bash
rustup update
```

2. Clean and rebuild:
```bash
rm -rf target/
maturin develop --release
```

### Compilation errors

Ensure you have:
- GCC/Clang installed (for C dependencies)
- Python development headers
- Rust toolchain updated

On Ubuntu:
```bash
sudo apt-get install build-essential python3-dev
rustup update
```

### Import errors after installation

Reinstall in development mode:
```bash
pip uninstall -y copy-paste
pip install -e .
```

## Next Steps

- [Quick Start](quickstart.md) - Basic usage
- [Architecture](architecture.md) - System design
- [API Reference](../user-guide/api-reference.md) - Complete API
