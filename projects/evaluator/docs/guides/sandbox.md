# Sandbox Execution with E2B

Run your backtest agents in isolated cloud sandboxes using [E2B](https://e2b.dev).

## Why Use Sandbox Execution?

- **Isolation**: Each test runs in a fresh, isolated environment
- **Security**: Agents cannot access your local filesystem or credentials
- **Reproducibility**: Consistent environment across all test runs
- **Scalability**: Run many tests in parallel without resource contention

## Installation

Install evaluator with E2B support:

```bash
uv pip install 'evaluator[e2b]'
```

You'll also need an E2B API key. Get one at [e2b.dev](https://e2b.dev) and set it:

```bash
export E2B_API_KEY="your-e2b-api-key"
```

## Quick Start

Run tests in an E2B sandbox:

```bash
evaluator run --tests tests/backtests/ --executor e2b
```

Use a specific template:

```bash
evaluator run --tests tests/backtests/ --executor e2b --e2b-template claude-tools
```

## Available Templates

### base

Minimal Python 3.11 environment with:
- anthropic SDK
- pydantic
- pyyaml

Best for: Simple tests that don't require CLI tools.

```bash
evaluator run --executor e2b --e2b-template base
```

### claude-tools

Full environment with all CLI tools referenced in CLAUDE.md:
- ripgrep (rg) - Fast recursive grep
- fd-find (fd) - User-friendly find alternative
- ast-grep - AST-based code search
- uv - Python package manager
- fzf - Fuzzy finder
- jq - JSON query tool
- yq - YAML/XML query tool

Best for: Tests that exercise file search and manipulation behaviors.

```bash
evaluator run --executor e2b --e2b-template claude-tools
```

## Configuration in YAML

You can also configure sandbox execution per test suite:

```yaml
name: "Tool Usage Tests"
description: "Test agent CLI tool usage"
model_under_test: "claude-sonnet-4-20250514"
instructions_version: "2.0"

# Sandbox configuration
metadata:
  instruction_file: "./CLAUDE.md"
  sandbox_environment:
    template: "claude-tools"
    timeout_seconds: 600
    memory_limit_mb: 4096
    environment_vars:
      LOG_LEVEL: "DEBUG"

test_cases:
  - description: "Agent should use ripgrep for searching"
    task: "Find all Python files containing 'import asyncio'"
    assertions:
      - type: contains
        metadata:
          expected: "rg"
        description: "Should use ripgrep"
```

## Custom Dockerfiles

For complete control over the environment, use a custom Dockerfile:

```yaml
metadata:
  sandbox_environment:
    custom_dockerfile: "./my-environment.Dockerfile"
    timeout_seconds: 900
```

Example custom Dockerfile:

```dockerfile
FROM python:3.11-slim

# Install your specific dependencies
RUN pip install anthropic pydantic mypy

# Install custom tools
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install -g typescript

WORKDIR /workspace
CMD ["/bin/bash"]
```

### Template Caching

Custom Dockerfiles are cached by content hash. If you modify the Dockerfile, evaluator automatically rebuilds the template. The cache is stored in `.evaluator/cache/template-mapping.json`.

To clear the cache:

```bash
rm -rf .evaluator/cache/
```

## Environment Variables

### Automatic Injection

The following environment variables are automatically injected into sandboxes:
- `ANTHROPIC_API_KEY` - Required for agent execution

### Custom Variables

Add custom environment variables in your test suite:

```yaml
metadata:
  sandbox_environment:
    environment_vars:
      DATABASE_URL: "postgresql://..."
      FEATURE_FLAG: "enabled"
```

Or via CLI for all tests:

```bash
export MY_VAR="value"
evaluator run --executor e2b
```

## Resource Limits

Configure resource limits per test suite:

```yaml
metadata:
  sandbox_environment:
    timeout_seconds: 300    # Max execution time (default: 300)
    memory_limit_mb: 2048   # Memory limit (default: 2048)
```

## Programmatic Usage

Use E2B executor directly in Python:

```python
from evaluator.executors import E2BExecutor
from evaluator.executors.base import SandboxConfig
from evaluator.runner import TestRunner
from evaluator.parser import YAMLTestParser

# Configure sandbox
config = SandboxConfig(
    template="claude-tools",
    timeout_seconds=600,
    memory_limit_mb=4096,
)

# Create E2B executor
executor = E2BExecutor(sandbox_config=config)

# Run tests with E2B
runner = TestRunner(executor=executor)
test_suites = YAMLTestParser.parse_directory("tests/backtests")
results = runner.run_suites(test_suites)
```

### Using Custom Templates

```python
from pathlib import Path
from evaluator.executors import E2BExecutor
from evaluator.executors.base import SandboxConfig

# Use custom Dockerfile
config = SandboxConfig(
    custom_dockerfile="./my-environment.Dockerfile",
    timeout_seconds=900,
)

executor = E2BExecutor(sandbox_config=config)
```

## CI/CD Integration

### GitHub Actions with E2B

```yaml
name: Backtest with E2B

on:
  pull_request:
    paths:
      - 'CLAUDE.md'
      - 'AGENTS.md'

jobs:
  backtest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install 'evaluator[e2b]'

      - name: Run backtests in sandbox
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          E2B_API_KEY: ${{ secrets.E2B_API_KEY }}
        run: |
          evaluator run \
            --tests tests/backtests/ \
            --executor e2b \
            --e2b-template claude-tools \
            --output results.json
```

## Debugging Sandbox Issues

### View Sandbox Output

Run with verbose output to see sandbox stdout/stderr:

```bash
pytest tests/backtests/ -s --executor e2b
```

### Inspect Execution Context

```python
result = runner.run_test(test_case, test_suite)

# Check sandbox info
print(f"Sandbox ID: {result.execution_context.sandbox_info['session_id']}")
print(f"Template: {result.execution_context.sandbox_info['template']}")
print(f"Stdout: {result.execution_context.stdout}")
print(f"Stderr: {result.execution_context.stderr}")
```

### Common Issues

**"E2B_API_KEY not set"**
```bash
export E2B_API_KEY="your-key"
```

**"Template build failed"**
Check your Dockerfile syntax and ensure all dependencies are available.

**"Timeout exceeded"**
Increase timeout in sandbox config:
```yaml
metadata:
  sandbox_environment:
    timeout_seconds: 900
```

## Local vs E2B Comparison

| Feature | Local | E2B |
|---------|-------|-----|
| Speed | Faster | Network overhead |
| Isolation | None | Full |
| Security | Low | High |
| Cost | Free | Usage-based |
| Parallelism | Limited by local resources | Highly scalable |
| Reproducibility | Environment-dependent | Consistent |

**Recommendation**: Use local execution for rapid iteration during development, and E2B for CI/CD and final validation.

## Next Steps

- [Writing Tests](writing-tests.md) - Create effective backtests
- [CI/CD Integration](ci-cd.md) - Full pipeline setup
- [Advanced Features](advanced.md) - Caching, snapshots, and more
