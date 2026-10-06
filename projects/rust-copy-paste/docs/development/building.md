# Building from Source

This guide covers building the Copy-Paste augmentation from source code.

## Requirements

- Rust 1.70 or later
- Python 3.8 or later
- C compiler (gcc, clang, or MSVC)

## Building the Rust Component

The project uses Cargo for Rust builds:

```bash
# Build debug version (faster compilation)
cargo build

# Build release version (optimized for performance)
cargo build --release

# Build with all features
cargo build --release --all-features
```

## Building the Python Extension

The Python extension is built using PyO3:

```bash
# Using maturin (recommended)
pip install maturin
maturin develop --release

# Or using setup.py
python setup.py develop
```

## Building for Distribution

To create distribution wheels:

```bash
# Install build tools
pip install maturin wheel

# Build wheels for all platforms
maturin build --release
```

The wheels will be created in the `target/wheels/` directory.

## Building Documentation

### Prerequisites

```bash
pip install mkdocs mkdocs-material pymdown-extensions mkdocstrings
```

### Build Documentation

```bash
mkdocs build
```

The documentation will be built to the `site/` directory.

### Serve Documentation Locally

```bash
mkdocs serve
```

Then visit `http://localhost:8000` in your browser.

## Troubleshooting

### Rust compilation issues
- Ensure you have the latest Rust: `rustup update`
- Clean build artifacts: `cargo clean`
- Check system dependencies are installed

### Python extension issues
- Ensure Python development headers are installed
- On Ubuntu: `sudo apt-get install python3-dev`
- On macOS: Xcode Command Line Tools are required

### Documentation build issues
- Ensure all dependencies are installed: `pip install -r docs-requirements.txt`
- Check for broken links: `mkdocs build --strict`

## CI/CD Building

The project uses GitHub Actions for automated builds. See `.github/workflows/` for CI configuration.
