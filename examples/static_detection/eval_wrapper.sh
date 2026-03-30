#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${GENESIS_PYTHON:-python3}"
exec "$PYTHON" "$SCRIPT_DIR/eval_wrapper.py"
