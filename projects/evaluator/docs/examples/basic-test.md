# Basic Test Example

A simple example to get started with AI Backtest.

## The Test File

Create `tests/backtests/hello_world.backtest.yaml`:

```yaml
name: "Hello World Test"
description: "First test - validate basic greeting behavior"
instructions_version: "main"
model_under_test: "claude-3-5-sonnet-20250109"
metadata:
  instruction_file: "/path/to/your/CLAUDE.md"

test_cases:
  - description: "Should greet politely"
    task: "Introduce yourself briefly"
    assertions:
      - type: must_contain
        target: full_response
        pattern: "hello"
        severity: error
        description: "Should include a greeting"
```

## Run the Test

```bash
# With pytest
pytest tests/backtests/hello_world.backtest.yaml -v

# Output:
# tests/backtests/hello_world.backtest.yaml::Should_greet_politely PASSED
```

## Understand the Result

✅ **PASSED** means:
- Agent responded to the task
- The response contains the word "hello"
- The assertion passed

## Expand the Test

Add more assertions:

```yaml
test_cases:
  - description: "Should greet politely"
    task: "Introduce yourself briefly"
    assertions:
      - type: must_contain
        pattern: "hello"
        severity: error
        description: "Should greet"

      - type: regex_match
        pattern: "I am|I'm"
        severity: error
        description: "Should introduce self"

      - type: must_not_contain
        pattern: "error"
        severity: error
        description: "Should not error"
```

## Test Code Quality

Create `tests/backtests/code_quality_example.backtest.yaml`:

```yaml
name: "Code Quality Example"
test_cases:
  - description: "Code should have type hints"
    task: "Write a function that adds two numbers"
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
        description: "Must have docstring"

      - type: regex_match
        target: generated_code
        pattern: "def add\("
        severity: error
        description: "Should define add function"
```

## Use LLM Judge

Create `tests/backtests/judge_example.backtest.yaml`:

```yaml
name: "LLM Judge Example"
test_cases:
  - description: "Explanation should be clear"
    task: "Explain what is REST API"
    assertions:
      - type: llm_judge
        metadata:
          judge_prompt: |
            Is this explanation clear and accurate?
            Consider: clarity, accuracy, conciseness.
            Respond with JSON: {"score": 0-1, "reasoning": "..."}
          threshold: 0.8
        severity: warning
        description: "Explanation should be clear"

      - type: must_contain
        pattern: "API"
        severity: error
        description: "Should mention API"
```

## View Results

### Text Output

```bash
pytest tests/backtests/ -v

# Output shows:
# PASSED  - All assertions passed
# FAILED  - One or more assertions failed
# WARNINGS - Warning assertions failed (non-blocking)
```

### HTML Report

```bash
evaluator run --tests tests/backtests --html report.html
open report.html
```

## Next Steps

- [Writing Tests](../guides/writing-tests.md) - Complete guide
- [Assertion Types](../guides/assertions.md) - All 10 assertion types explained
- [PR Validation](../examples/pr-validation.md) - Validate against PRs
