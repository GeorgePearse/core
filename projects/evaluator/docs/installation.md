# Installation

Complete installation guide for evaluator.

## System Requirements

- **Python:** 3.10 or higher
- **OS:** Linux, macOS, Windows (WSL2 recommended)
- **Memory:** 2GB minimum (for running tests and caching)

## Install Methods

### Method 1: Using uv (Recommended)

The fastest and most reliable installation:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/GeorgePearse/evaluator
cd evaluator
uv sync
```

Activate the virtual environment:
```bash
# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### Method 2: Using pip

```bash
git clone https://github.com/GeorgePearse/evaluator
cd evaluator
pip install -e .
```

### Method 3: Development Installation

For contributing to the project:

```bash
git clone https://github.com/GeorgePearse/evaluator
cd evaluator

# With uv
uv sync --all-extras

# With pip
pip install -e ".[dev,docs]"
```

## Verify Installation

```bash
# Check Python version
python --version
# Should be 3.10+

# Check evaluator is installed
evaluator --help

# Run tests (should pass)
pytest tests/
```

## API Key Setup

You'll need an Anthropic API key to run tests.

### Get an API Key

1. Visit [console.anthropic.com](https://console.anthropic.com)
2. Create an account or sign in
3. Navigate to "API keys"
4. Create a new API key
5. Copy the key (starts with `sk-ant-`)

### Configure the Key

**Option 1: Environment Variable (Recommended)**

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

Add to your shell profile for persistence:

=== "Bash/Zsh (~/.bashrc or ~/.zshrc)"
    ```bash
    export ANTHROPIC_API_KEY="sk-ant-your-key-here"
    ```

=== "Fish (~/.config/fish/config.fish)"
    ```fish
    set -gx ANTHROPIC_API_KEY "sk-ant-your-key-here"
    ```

=== "PowerShell ($PROFILE)"
    ```powershell
    $env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
    ```

**Option 2: .env File**

Create a `.env` file in the project root:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Then load it:
```bash
set -a
source .env
set +a
```

**Option 3: Pass as Argument**

Some commands accept the API key directly:
```bash
evaluator run --api-key "sk-ant-..." --tests tests/backtests/
```

### Verify Setup

```bash
# Test the API key
python -c "
from anthropic import Anthropic
client = Anthropic()
msg = client.messages.create(
    model='claude-3-5-sonnet-20250109',
    max_tokens=100,
    messages=[{'role': 'user', 'content': 'Say hello'}]
)
print('✅ API key works!')
print(msg.content[0].text)
"
```

## Optional Dependencies

### For E2B Sandbox Execution

Run tests in isolated cloud sandboxes with [E2B](https://e2b.dev):

```bash
# With uv
uv pip install 'evaluator[e2b]'

# With pip
pip install -e ".[e2b]"
```

You'll also need an E2B API key:

1. Visit [e2b.dev](https://e2b.dev) and create an account
2. Get your API key from the dashboard
3. Set the environment variable:

```bash
export E2B_API_KEY="your-e2b-api-key"
```

Then run tests in the sandbox:

```bash
evaluator run --tests tests/backtests/ --executor e2b
```

See [Sandbox Execution](guides/sandbox.md) for full documentation.

### For Documentation

To build the documentation locally:

```bash
# With uv
uv sync --extra docs

# With pip
pip install -e ".[docs]"

# Build docs
mkdocs serve
# Visit http://localhost:8000
```

### For Development

To contribute to the project:

```bash
# With uv
uv sync --extra dev

# With pip
pip install -e ".[dev]"

# Run linting
ruff check src/
mypy src/

# Run tests
pytest tests/
```

### For All

Install everything:

```bash
# With uv
uv sync --all-extras

# With pip
pip install -e ".[dev,docs,e2b]"
```

## Troubleshooting

### "command not found: evaluator"

The CLI wasn't installed properly. Try:

```bash
# If using uv
source .venv/bin/activate

# If using pip in virtualenv
which evaluator
# Should show path to executable

# If not found, reinstall
pip install -e .
```

### "ModuleNotFoundError: No module named 'anthropic'"

Dependencies weren't installed:

```bash
# With uv
uv sync

# With pip
pip install -e .
```

### "ANTHROPIC_API_KEY not found"

The environment variable isn't set:

```bash
# Check if set
echo $ANTHROPIC_API_KEY

# Set temporarily
export ANTHROPIC_API_KEY="sk-ant-..."

# Or use .env file approach
```

### "Python 3.10+ required"

Install Python 3.10 or higher:

=== "macOS (Homebrew)"
    ```bash
    brew install python@3.11
    ```

=== "Ubuntu/Debian"
    ```bash
    sudo apt-get install python3.11 python3.11-venv
    ```

=== "Windows"
    Download from [python.org](https://www.python.org/downloads/)

### "pip install" vs "pip install -e"

- `pip install .` - Regular install (can't edit source)
- `pip install -e .` - Editable install (changes to code take effect immediately)

For development, use `-e`.

## Next Steps

Once installed:

1. **[Getting Started](getting-started.md)** - Run your first test
2. **[Writing Tests](guides/writing-tests.md)** - Learn the test format
3. **[Examples](examples/basic-test.md)** - See real-world examples

## Getting Help

- 📚 [Full Documentation](index.md)
- 🐛 [Report Issues](https://github.com/GeorgePearse/evaluator/issues)
- 💬 [GitHub Discussions](https://github.com/GeorgePearse/evaluator/discussions)
