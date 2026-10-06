# Writing Tests

Complete guide to writing AI Backtest test cases.

## YAML Format Overview

All tests are defined in `.backtest.yaml` files:

```yaml
name: "Test Suite Name"
description: "What this suite tests"
instructions_version: "main"
model_under_test: "claude-3-5-sonnet-20250109"
metadata:
  instruction_file: "/path/to/CLAUDE.md"

test_cases:
  - description: "What this test validates"
    task: "The task to give the agent"
    assertions:
      - type: assertion_type
        description: "What this assertion checks"
        severity: error
        # ... assertion-specific config
```

## Top-Level Fields

### name (required)
```yaml
name: "Tool Usage Rules"
```
Short name for your test suite.

### description (required)
```yaml
description: "Validates that agents follow tool recommendations"
```
What your test suite validates.

### instructions_version (optional)
```yaml
instructions_version: "main"
```
Version of instructions being tested. Useful for tracking changes over time.

### model_under_test (optional)
```yaml
model_under_test: "claude-3-5-sonnet-20250109"
```
Which Claude model to use. Defaults to claude-3-5-sonnet-20250109.

### metadata (optional)
```yaml
metadata:
  instruction_file: "/path/to/CLAUDE.md"
  author: "team-name"
  tags: ["tooling", "quality"]
```
Custom metadata. **Required:** `instruction_file` pointing to your instructions.

## Test Cases

Each test has a task for the agent and assertions to validate the response.

### description (required)
```yaml
test_cases:
  - description: "Should use uv for package management"
```
What behavior is being tested.

### task (required)
```yaml
task: |
  Create a new Python project called 'data-processor'.
  Show me the commands to set it up.
```
The prompt/task given to the agent. Can be multi-line.

### assertions (required)
```yaml
assertions:
  - type: must_contain
    pattern: "uv"
  - type: must_not_contain
    pattern: "pip install"
```
List of assertions validating the response. [See all types](assertions.md).

### tags (optional)
```yaml
tags: ["tooling", "critical"]
```
Categorize tests for filtering.

### metadata (optional)
```yaml
metadata:
  priority: "high"
  complexity: "easy"
```
Test-specific metadata.

## Example: Complete Test Suite

```yaml
name: "Instruction Compliance"
description: "Validate that generated code follows our standards"
instructions_version: "v2.1"
model_under_test: "claude-3-5-sonnet-20250109"
metadata:
  instruction_file: "/home/user/CLAUDE.md"
  last_updated: "2024-10-25"

test_cases:
  # Test 1: Tool selection
  - description: "Should use uv and pyproject.toml"
    task: "Create a new Python project with dependencies"
    tags: ["tooling", "setup"]
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

  # Test 2: Code quality
  - description: "Generated code should have type hints"
    task: "Write a function to validate email addresses"
    tags: ["quality", "typing"]
    assertions:
      - type: code_analysis
        metadata:
          validator: "python_type_check"
        severity: error
        description: "Functions must have type hints"

      - type: code_analysis
        metadata:
          validator: "docstring_check"
        severity: error
        description: "Functions must have docstrings"

  # Test 3: Behavioral rule
  - description: "Responses should include tests"
    task: "Implement a CSV parser function"
    tags: ["best-practices"]
    assertions:
      - type: must_contain
        pattern: "def test_"
        severity: error
        description: "Should include test cases"

      - type: llm_judge
        metadata:
          judge_prompt: |
            Do the tests comprehensively cover the functionality?
            Consider edge cases, error handling, and normal cases.
            Respond with JSON: {"score": 0-1, "reasoning": "..."}
          threshold: 0.7
        severity: warning
        description: "Tests should be comprehensive"
```

## Test Organization

### File Naming
```
tests/backtests/
├── tool_usage.backtest.yaml       # Tests for tool selection rules
├── code_quality.backtest.yaml     # Tests for code quality standards
├── behavioral.backtest.yaml       # Tests for behavioral rules
└── mcp_specific.backtest.yaml     # Tests for MCP configuration
```

Files must end with `.backtest.yaml` to be discovered.

### Grouping Strategy

**Option 1: By Category**
- One file per rule category
- Better for organization
- Easier to run specific categories

**Option 2: By Instruction**
- One file per instruction (CLAUDE.md, AGENTS.md)
- Simpler to manage
- Natural grouping

**Option 3: By Priority**
- Critical rules in one file
- Nice-to-have in another
- Easy to run just critical tests

## Writing Good Tests

### ✅ DO

```yaml
# Specific, clear task
task: "Create a Python function that parses JSON"

# Specific, measurable assertion
assertion:
  - type: must_contain
    pattern: "def "
    description: "Should define a function"

# Good use of severity
severity: error  # for requirements
severity: warning  # for guidelines
```

### ❌ DON'T

```yaml
# Vague task
task: "Write code"

# Unmeasurable assertion
assertion:
  - type: must_contain
    pattern: "something"
    description: "Should have something"

# Overloaded severity
severity: error  # for everything
```

## Running Tests

### Run all tests
```bash
pytest tests/backtests/
```

### Run specific file
```bash
pytest tests/backtests/tool_usage.backtest.yaml
```

### Run with pattern
```bash
pytest tests/backtests/ -k "uv"
```

### Run with options
```bash
# Verbose output
pytest tests/backtests/ -vv

# Show print statements
pytest tests/backtests/ -s

# Stop on first failure
pytest tests/backtests/ -x
```

### Use CLI
```bash
evaluator run --tests tests/backtests/ --html report.html
```

## Validating Your Tests

Before committing:

```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('tests/backtests/test.backtest.yaml'))"

# Run with verbose output
pytest tests/backtests/ -vv

# Check coverage
evaluator list-tests
# Review all discovered tests
```

## Common Patterns

### Pattern 1: Tool Usage Validation

```yaml
test_cases:
  - description: "Uses recommended tool"
    task: "Set up a project using [tool]"
    assertions:
      - type: must_contain
        target: generated_commands
        pattern: "[tool]"
        severity: error

      - type: must_not_contain
        target: generated_commands
        pattern: "[old_tool]"
        severity: error
```

### Pattern 2: Code Quality

```yaml
test_cases:
  - description: "Code meets standards"
    task: "Implement [feature]"
    assertions:
      - type: code_analysis
        metadata:
          validator: "python_type_check"

      - type: code_analysis
        metadata:
          validator: "docstring_check"

      - type: must_not_contain
        target: generated_code
        pattern: "# TODO"
```

### Pattern 3: Behavioral Validation

```yaml
test_cases:
  - description: "Behavior is correct"
    task: "Help with [task]"
    assertions:
      - type: llm_judge
        metadata:
          judge_prompt: "Is this [quality]?"
          threshold: 0.8

      - type: regex_match
        pattern: "[pattern]"
```

### Pattern 4: Diff Evaluation (SWE-bench Style)

```yaml
test_cases:
  - description: "Bug fix generates correct patch"
    task: |
      Fix the bug in src/utils.py where process_data()
      doesn't handle None values. Return a git diff.
    assertions:
      # Validate diff syntax
      - type: diff_syntax
        target: generated_diff
        description: "Diff must be syntactically valid"
        severity: error

      # Validate diff applies to source
      - type: diff_applies
        target: generated_diff
        description: "Diff must apply cleanly"
        metadata:
          file_contents:
            "src/utils.py": |
              def process_data(data):
                  return data.strip()
        severity: error

      # LLM evaluation of diff quality
      - type: diff_judge
        target: generated_diff
        description: "Diff correctly fixes the bug"
        metadata:
          threshold: 0.8
        severity: error
```

## Handling Multiple Requirements

### ❌ Wrong: One assertion for multiple requirements
```yaml
assertions:
  - type: must_contain
    pattern: "uv|pip|poetry"  # Don't do this
    description: "Should use a package manager"
```

### ✅ Right: Separate assertions
```yaml
assertions:
  - type: must_contain
    pattern: "uv"
    description: "Should use uv"

  - type: must_not_contain
    pattern: "pip install"
    description: "Should not use pip"
```

## Debugging Tests

### See Agent Response

Add `--capture=no` to see full output:
```bash
pytest tests/backtests/test.backtest.yaml -s
```

### Check What Was Tested

Use `evaluator list-tests`:
```bash
evaluator list-tests --tests tests/backtests/
```

### Re-run with Cache Cleared

LLM judge results are cached. Clear for fresh evaluation:
```bash
rm .evaluator_cache.db
pytest tests/backtests/
```

## Advanced: Custom Metadata

Add any custom fields you need:

```yaml
metadata:
  instruction_file: "/path/to/CLAUDE.md"
  author: "team-name"
  created: "2024-10-25"
  last_reviewed: "2024-10-25"
  review_frequency: "monthly"
  expected_pass_rate: 0.95
  tags: ["critical", "tooling"]
```

These are available in results JSON but don't affect test execution.

## Next Steps

- [Assertion Types](assertions.md) - All assertion types with examples
- [Advanced Features](advanced.md) - Custom validators, caching, snapshots
- [Examples](../examples/basic-test.md) - Real test suites
- [Running Tests](ci-cd.md) - GitHub Actions integration
