#!/bin/bash
# Installation script for UMAP development environment
# Uses pip for dependency installation (conda no longer supported)

set -e

echo "Setting up UMAP development environment with pip..."

# Check Python version
python --version

# Create virtual environment (recommended but not required)
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python -m venv venv
  source venv/bin/activate
fi

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo "Installing core dependencies..."
pip install numpy scipy scikit-learn numba pynndescent tqdm

# Install optional dependencies for testing and visualization
echo "Installing optional dependencies..."
pip install pytest pytest-benchmark pytest-cov
pip install pandas bokeh holoviews matplotlib datashader scikit-image

# Install parametric UMAP dependencies (TensorFlow - pre-PyTorch migration)
echo "Installing TensorFlow for Parametric UMAP..."
pip install "tensorflow>=2.10.0"

# Install the package in development mode
echo "Installing UMAP in development mode..."
pip install -e .

# Verify installation
echo ""
echo "Installation complete. Verifying versions..."
python --version
python -c "import numpy; print('numpy %s' % numpy.__version__)"
python -c "import scipy; print('scipy %s' % scipy.__version__)"
python -c "import numba; print('numba %s' % numba.__version__)"
python -c "import sklearn; print('scikit-learn %s' % sklearn.__version__)"
python -c "import umap; print('UMAP loaded successfully')"

echo ""
echo "Setup complete! Run tests with: pytest"
