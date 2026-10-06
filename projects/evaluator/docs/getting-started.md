# Getting Started

Get up and running with AI Backtest in 5 minutes.

## Prerequisites

- Python 3.10+
- `uv` package manager (or `pip`)
- Anthropic API key

## Installation

```bash
# Clone the repository
git clone https://github.com/GeorgePearse/evaluator
cd evaluator

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Set Up API Key

```bash
# Export your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Or create a .env file
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

## Your First Test

### 1. Create a Test File

Create `tests/backtests/first_test.backtest.yaml`:

```yaml
name: "My First Test"
description: "Testing basic instructions"
instructions_version: "main"
model_under_test: "claude-3-5-sonnet-20250109"
metadata:
  instruction_file: "/path/to/your/CLAUDE.md"

test_cases:
  - description: "Should mention being helpful"
    task: "Introduce yourself briefly"
    assertions:
      - type: must_contain
        target: full_response
        description: "Mentions being helpful"
        pattern: "help"
        severity: error

      - type: regex_match
        target: full_response
        description: "Contains proper greeting"
        pattern: "Hello|Hi|Greetings"
        severity: error
```

### 2. Run the Test

**With pytest:**
```bash
pytest tests/backtests/first_test.backtest.yaml -v
```

**With CLI:**
```bash
evaluator run --tests tests/backtests/first_test.backtest.yaml
```

**With HTML report:**
```bash
evaluator run --tests tests/backtests/ --html report.html
```

### 3. Check Results

Look for:
- ✅ **PASSED** - All assertions passed
- ❌ **FAILED** - One or more assertions failed
- ⚠️ **WARNING** - Severity=warning assertions failed (non-blocking)

## Example: Testing Tool Usage Rules

Test that your instructions follow your own tool recommendations:

```yaml
name: "Tool Usage Rules"
test_cases:
  - description: "Should recommend using uv"
    task: "Create a new Python project"
    assertions:
      - type: must_contain
        target: generated_commands
        pattern: "uv"
        severity: error
        description: "Must mention uv"

      - type: must_not_contain
        target: generated_commands
        pattern: "pip install"
        severity: error
        description: "Should not use pip"

      - type: must_not_contain
        target: generated_commands
        pattern: "find "
        severity: error
        description: "Should use fd, not find"
```

## Example: Testing Code Quality Rules

Test that generated code follows your quality standards:

```yaml
name: "Code Quality"
test_cases:
  - description: "Generated code should have type hints"
    task: "Write a function to calculate fibonacci"
    assertions:
      - type: code_analysis
        metadata:
          validator: "python_type_check"
        severity: error
        description: "Must have type hints"

      - type: code_analysis
        metadata:
          validator: "docstring_check"
        severity: error
        description: "Must have docstrings"

      - type: regex_match
        target: generated_code
        pattern: "def\s+\w+\([^)]*:\s*\w+\)[^:]*->\s*\w+"
        severity: error
        description: "Function signature has type hints"
```

## Example: Using LLM-as-Judge

Use Claude to evaluate subjective aspects:

```yaml
name: "Behavioral Rules"
test_cases:
  - description: "Responses should be helpful and clear"
    task: "Explain what a REST API is"
    assertions:
      - type: llm_judge
        target: full_response
        severity: warning
        description: "Explanation is clear and helpful"
        metadata:
          judge_prompt: |
            Is this explanation of REST APIs clear and accurate?
            Consider: accuracy, clarity, examples, completeness.
            Respond with JSON: {"score": 0-1, "reasoning": "..."}
          threshold: 0.7
```

## Next Steps

- **[Write Tests](guides/writing-tests.md)** - Learn the complete YAML format
- **[Assertion Types](guides/assertions.md)** - See all 10 assertion types
- **[Advanced Features](guides/advanced.md)** - Caching, custom validators, snapshots
- **[Examples](examples/basic-test.md)** - More real-world examples

## Troubleshooting

### Tests Run Slowly

LLM judge calls take 1-2 seconds. Use `severity: warning` for non-critical tests.

### API Key Not Found

```bash
# Make sure env var is set
echo $ANTHROPIC_API_KEY

# Or update .env file
export ANTHROPIC_API_KEY="your-key-here"
```

### Tests Don't Discover

Ensure files end with `.backtest.yaml`:
```bash
# Good ✅
tests/backtests/my_test.backtest.yaml

# Bad ❌
tests/backtests/my_test.yaml
tests/backtests/test_my_rules.py
```

## Getting Help

- Check the [Full Documentation](guides/writing-tests.md)
- Review [Examples](examples/basic-test.md)
- Read [Research & Design](research/inspirations.md)
- Open an issue on [GitHub](https://github.com/GeorgePearse/evaluator/issues)
