# Testing tsrs (Tree-Shaking in Rust for Python)

## Overview

The test infrastructure validates that tsrs correctly slims virtual environments without breaking functionality.

## Test Strategy

**High Precision, Low Recall Philosophy**: We validate that after tree-shaking, the application still works perfectly. This ensures we're not removing code that's actually used.

### The Test Flow

For each test repository:

```
┌─────────────────────────────────────┐
│  1. Create Full venv                │
│  2. Install all dependencies        │
│  3. Run functionality tests ✓        │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  4. Run tsrs                        │
│  5. Create .venv-slim with only     │
│     the packages that are imported  │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  6. Run same tests with .venv-slim  │
│  7. Verify all tests still pass ✓   │
│  8. Report size savings             │
└─────────────────────────────────────┘
```

## Test Repositories

### 1. simple-data
- **Dependencies**: requests, click, pydantic
- **Purpose**: Tests HTTP, CLI, and validation libraries
- **Test**: Validates imports and Pydantic model functionality

### 2. cli-tool
- **Dependencies**: typer, rich
- **Purpose**: Tests CLI framework and output libraries
- **Test**: Validates typer and rich functionality

### How to Add More Tests

Create a new test repo:

```bash
mkdir test_repos/my-test
cd test_repos/my-test
git init

# Create pyproject.toml with dependencies
# Create Python code that uses those dependencies
# Create test.sh that validates everything works
# Commit

git add -A
git commit -m "Initial test repo"
```

The test runner will auto-discover it.

## Running Tests

### Prerequisites

```bash
# Build the CLI
cargo build --release --bin tsrs-cli

# Ensure Python 3.7+ is available
python --version
```

### Run All Tests

```bash
cd test_repos
bash run_tests.sh
```

### Run Single Test

```bash
cd test_repos/simple-data
python -m venv .venv
.venv/bin/pip install -q -e .
.venv/bin/python test.sh

# Then manually:
../../target/release/tsrs-cli slim . .venv -o .venv-slim
VIRTUAL_ENV=.venv-slim .venv-slim/bin/python test.sh
```

## What Gets Tested

✅ **Functionality**: Application code works identically before/after  
✅ **Imports**: All imported packages are available  
✅ **Size Reduction**: Quantifies how much space is saved  
✅ **Safety**: Validates nothing critical was removed  

## Success Criteria

Each test is considered successful if:

1. ✅ Original venv tests pass
2. ✅ tree-shaking completes without error
3. ✅ Slimmed venv tests pass (same test, slimmer environment)
4. ✅ Size reduction is meaningful (typically 30-70% smaller)

## Expected Results

When you run the test suite, you should see:

```
==================================================
tsrs Test Runner
==================================================

==================================================
Testing: simple-data
==================================================
[1/5] Creating virtual environment...
[2/5] Installing dependencies...
[3/5] Running test (before slimming)...
✓ Before test passed
[4/5] Running tree-shaking...
✓ Tree-shaking completed
[5/5] Running test (after slimming)...
✓ After test passed

Size comparison:
  Original: 145M
  Slimmed:  65M

==================================================
Testing: cli-tool
==================================================
[1/5] Creating virtual environment...
[2/5] Installing dependencies...
[3/5] Running test (before slimming)...
✓ Before test passed
[4/5] Running tree-shaking...
✓ Tree-shaking completed
[5/5] Running test (after slimming)...
✓ After test passed

Size comparison:
  Original: 120M
  Slimmed:  52M

==================================================
Summary
==================================================
Passed: 2
Failed: 0
==================================================
✓ All tests passed!
```

## Troubleshooting

### Test fails with "test.sh not found"
Make sure your test repo has an executable `test.sh` file.

### Original venv test fails
Install dependencies with: `.venv/bin/pip install -e .`

### Slimmed venv test fails
This indicates tsrs removed a package that's actually needed. This is the high-precision validation working - it caught a false positive.

### Check what was removed
```bash
ls .venv/lib/python*/site-packages
ls .venv-slim/lib/python*/site-packages
# Compare the two
```

## Philosophy

**Better to keep unused code than break working code.**

The test suite proves this philosophy works in practice:
- We leave room for indirect usage patterns
- We preserve all public APIs
- We validate that real applications work after slimming
- We prioritize correctness over aggressive optimization
