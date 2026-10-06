# Contributing to Retrocode

Thanks for your interest in contributing to retrocode! This guide covers setup, development workflows, and our development practices.

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- Rust (for CLI tool compilation)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/retrocode.git
   cd retrocode
   ```

2. **Install dependencies with uv**
   ```bash
   # Install runtime dependencies
   uv pip install -e .

   # Install dev dependencies (includes zuban, ruff, etc.)
   uv pip install -e ".[dev]"
   ```

3. **Install git hooks**
   ```bash
   # Use prek (7x faster than pre-commit)
   uv tool install prek
   prek install

   # Alternatively, use standard pre-commit
   # uv pip install pre-commit
   # pre-commit install
   ```

## Modern Development Tools

This project uses modern Rust-based tools for faster development feedback.

### Type Checking: Ty

[Ty](https://github.com/astral-sh/ty) is an extremely fast type checker implemented in Rust by Astral (creators of Ruff).

**Run type checking locally:**
```bash
# Check source code
uvx ty check src/

# Check tests
uvx ty check tests/

# Check both
uvx ty check src/ tests/
```

**Features:**
- Mypy-compatible configuration (uses existing `[tool.mypy]` in pyproject.toml)
- Blazingly fast performance (Rust-based)
- Integrates seamlessly with Ruff (same team)
- Uses uvx for convenient invocation

**Note:** Ty is enabled in pre-commit hooks. Run it locally to check before committing.

### Linting & Formatting: Ruff

[Ruff](https://docs.astral.sh/ruff/) is a fast Python linter and formatter that replaces multiple traditional tools.

**Auto-format code:**
```bash
ruff format src/ tests/
```

**Check for linting issues:**
```bash
ruff check src/ tests/
```

**Auto-fix common issues:**
```bash
ruff check --fix src/ tests/
```

### Pre-commit Hooks: Prek

[Prek](https://prek.j178.dev/) is a Rust-based pre-commit hook framework that's 7x faster than the original.

**Run all hooks:**
```bash
prek run --all-files
```

**Run specific hook:**
```bash
prek run ruff
prek run ruff-format
```

**Update hooks:**
```bash
prek update
```

**Fallback to standard pre-commit (if needed):**
```bash
# If you prefer the original pre-commit tool
pre-commit install
pre-commit run --all-files
```

## Git Workflow

### Before Committing

1. **Auto-format your code**
   ```bash
   ruff format src/ tests/
   ```

2. **Check for linting issues**
   ```bash
   ruff check --fix src/ tests/
   ```

3. **Run type checking (optional but recommended)**
   ```bash
   zuban mypy src/ tests/
   ```

4. **Run tests**
   ```bash
   pytest tests/
   ```

### Making a Commit

```bash
# The following runs automatically:
# - ruff format (fixes formatting)
# - ruff check (checks style)
# - documentation link validation

git commit -m "Your commit message"
```

If hooks fail, they'll tell you what to fix. After fixing, stage the changes and try again.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/retrocode tests/

# Run specific test file
pytest tests/test_agent.py

# Run with verbose output
pytest -v

# Run in parallel for faster feedback
pytest -n auto
```

## Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) (enforced by ruff)
- Use type annotations (enforced by mypy/zuban configuration)
- Write docstrings for all public functions and classes
- Keep lines under 100 characters (ruff configured at 100)

Example:
```python
def process_data(data: dict[str, Any]) -> dict[str, str]:
    """Process input data and return formatted output.

    Args:
        data: Dictionary containing raw input data

    Returns:
        Dictionary with formatted key-value pairs
    """
    return {k: str(v) for k, v in data.items()}
```

## Pull Request Process

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with appropriate commits

3. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Ensure CI passes** - GitHub Actions will run:
   - Ruff formatting check
   - Type checking
   - Tests
   - Documentation validation

5. **Address review comments** - iterate until approved

6. **Merge** - maintainers will merge to main

## Common Issues

### "command not found: prek"

Install prek:
```bash
uv tool install prek
```

### "ty not found"

Ty is invoked via `uvx`, which should work automatically. If you encounter issues, you can install it globally:
```bash
uv tool install ty
ty check src/
```

### Pre-commit hooks fail

Run the failing tool to see what's wrong:
```bash
# If ruff fails
ruff check src/
ruff format src/

# If ty fails (optional)
uvx ty check src/
```

Most errors can be auto-fixed:
```bash
ruff check --fix src/ tests/
ruff format src/ tests/
```

### Tests fail locally but pass in CI

- Make sure you're using the correct Python version
- Try running tests with pytest directly: `pytest tests/`
- Check that dependencies are up to date: `uv pip install -e ".[dev]"`

## Performance Tips

1. **Use prek instead of pre-commit** - It's much faster
2. **Format with ruff instead of black** - It's faster and more capable
3. **Type-check with ty instead of mypy** - It's dramatically faster
4. **Run pytest with `-n auto`** - Parallel test execution is faster

## Architecture Overview

See [`.retrocode/`](.retrocode/README.md) for information about the test system configuration and custom Docker environments.

## Questions?

- Check existing [GitHub issues](https://github.com/yourusername/retrocode/issues)
- Ask in our [discussions](https://github.com/yourusername/retrocode/discussions)
- See `.retrocode/DOCKERFILE_GUIDE.md` for Docker/sandbox questions

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

Thanks for contributing! 🎉
