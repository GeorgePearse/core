# evaluator

Test instruction files like `CLAUDE.md` and `AGENTS.md` through automated backtesting. Validate that AI agent behavior follows your guidelines and detect regressions before deployment.

## Why evaluator?

When you modify instruction files, you need confidence that:

- ✅ Your rules are still being followed
- ✅ Agent behavior hasn't regressed
- ✅ New guidelines improve performance

Traditional unit tests don't work for instruction files because outputs are non-deterministic. **evaluator** provides a rigorous framework for testing instruction changes:

## Key Features

- **13 Assertion Types** - From simple pattern checks to LLM-as-judge evaluations
- **Diff Evaluation** - Validate git diffs with syntax checks, applicability, and LLM quality scoring
- **Isolated Execution** - Run tests in secure E2B sandboxes
- **Comprehensive Scoring** - Track behavioral improvements
- **pytest Integration** - Run tests like any other test suite
- **Production Grade** - Fully typed Python, comprehensive error handling

## The Framework

Built on proven patterns from DSPy, promptfoo, and OpenAI Evals:

```
YAML Test Files
        ↓
Agent Invocation (Local / Sandbox)
        ↓
Responses
        ↓
Multi-Type Assertions
  ├─ Deterministic (regex, string matching)
  ├─ Code Analysis (AST, type hints)
  ├─ LLM-as-Judge (behavioral rules)
  ├─ Diff Evaluation (syntax, applicability, quality)
  └─ Snapshots (generated code comparison)
        ↓
Results & Reports
```

## Quick Start

### 1. Write a Test

Create `tests/backtests/my_rules.backtest.yaml`:

```yaml
name: "My Rules"
description: "Validate my instructions"
instructions_version: "main"
metadata:
  instruction_file: "/path/to/CLAUDE.md"

test_cases:
  - description: "Should use uv for package management"
    task: "Create a Python project"
    assertions:
      - type: must_contain
        target: generated_commands
        description: "Mentions uv"
        pattern: "uv"
        severity: error
      - type: must_not_contain
        target: generated_commands
        description: "Doesn't use pip"
        pattern: "pip install"
        severity: error
```

### 2. Run Tests

```bash
# Via pytest
pytest tests/backtests/

# Via CLI
evaluator run --tests tests/backtests --html report.html

# List all tests
evaluator list-tests
```

## Core Concepts

### Assertion Types

Test different aspects of agent behavior:

- **Deterministic**: Pattern matching, string containment
- **Code Analysis**: Type hints, docstrings, complexity
- **LLM Judge**: Behavioral rules ("Does this follow SOLID principles?")
- **Diff Evaluation**: Validate git diffs for syntax, applicability, and quality
- **Snapshots**: Compare against known-good outputs

## What You'll Learn


This documentation covers:

- **Getting Started** - Installation and first test
- **Writing Tests** - YAML format, test structure, best practices
- **Assertions** - All 13 types with real examples
- **Diff Evaluation** - SWE-bench style testing with git diffs
- **Advanced Features** - Custom validators, LLM judge tuning, caching
- **Python API** - Programmatic test execution
- **Research & Design** - Naming decisions, architectural patterns

## Built With

- **Pydantic** - Type-safe configuration
- **YAML** - Human-readable test format
- **pytest** - Familiar test execution
- **SQLite** - Judge result caching
- **Anthropic Claude** - As test executor and judge
- **Click** - CLI interface

## Architecture

Built on proven patterns from:

- **Promptfoo** (YAML tests, GitHub Actions)
- **DSPy** (Assertion framework, optimization)
- **Evidently** (LLM evaluation in CI/CD)
- **HumanEval** (Pass@k metrics)
- **SWE-bench** (Evaluation methodology)

## Next Steps

→ **[Get Started](getting-started.md)** - Installation and your first test

→ **[Write Tests](guides/writing-tests.md)** - Complete YAML format guide

→ **[Research](research/inspirations.md)** - See architectural patterns and design decisions

## License

MIT - See [LICENSE](https://github.com/GeorgePearse/evaluator/blob/main/LICENSE)

## Contributing

Contributions welcome! Please ensure:

- All code has type hints and docstrings
- Tests cover new functionality
- Pre-commit hooks pass

See [CONTRIBUTING.md](https://github.com/GeorgePearse/evaluator/blob/main/CONTRIBUTING.md)
