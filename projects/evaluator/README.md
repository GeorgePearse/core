# Evaluator

An AI coding task evaluator using E2B sandboxes and LLM judges. Run a task, execute it in a secure sandbox, and evaluate the results automatically.

## Quick Start

```bash
# Install
uv pip install -e .

# Run a task
evaluator "Write a Python script to calculate Fibonacci numbers"
```

## Features

- **Ad-hoc Task Execution**: Give a prompt, get code + evaluation.
- **E2B Sandbox Integration**: Code runs in a secure, isolated cloud environment.
- **LLM-as-a-Judge**: Uses Claude to evaluate the quality and correctness of the solution.
- **Backtesting**: Run suites of regression tests defined in YAML (legacy `retrocode` functionality).

## Usage

### Ad-hoc Task

```bash
evaluator "Write a React component for a login form"
```

This will:
1. Spin up an E2B sandbox.
2. Use an AI agent to write the code.
3. Run the code (if applicable).
4. Evaluate the result using an LLM judge.

### Running Test Suites

```bash
evaluator test --tests tests/backtests
```

## Architecture

The system uses:
- **Evaluator CLI**: Entry point.
- **AgentInvoker**: Interacts with Claude to generate code.
- **E2BExecutor**: Runs code in a sandbox.
- **TestRunner**: Orchestrates execution and assertions.

## License

MIT

