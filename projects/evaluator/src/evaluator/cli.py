"""Command-line interface for the evaluator."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

from evaluator.executors import E2BExecutor, LocalExecutor
from evaluator.models import (
    Assertion,
    AssertionType,
    AssertionSeverity,
    AssertionTarget,
    TestCase,
    TestSuite,
)
from evaluator.parser import YAMLTestParser
from evaluator.reporting import HTMLReporter, MarkdownReporter
from evaluator.runner import TestRunner


@click.group(invoke_without_command=True)
@click.argument("task_prompt", required=False)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key",
)
@click.option(
    "--e2b-api-key",
    envvar="E2B_API_KEY",
    help="E2B API key",
)
@click.pass_context
def cli(
    ctx: click.Context,
    task_prompt: Optional[str],
    api_key: Optional[str],
    e2b_api_key: Optional[str],
) -> None:
    """Evaluator: Run and evaluate AI coding tasks.

    Usage:
      evaluator "Write a component to do X"
      evaluator test --tests tests/backtests
    """
    if ctx.invoked_subcommand is None:
        if task_prompt:
            run_ad_hoc_task(task_prompt, api_key, e2b_api_key)
        else:
            click.echo(ctx.get_help())


def run_ad_hoc_task(task: str, api_key: Optional[str], e2b_api_key: Optional[str]) -> None:
    """Run a single ad-hoc task in E2B and evaluate it."""
    click.echo(f"Running task in E2B: {task}")

    if not api_key:
        click.echo("Error: ANTHROPIC_API_KEY is required.", err=True)
        sys.exit(1)

    # Check for E2B key if using E2B (which we default to for ad-hoc)
    if not e2b_api_key and "E2B_API_KEY" not in os.environ:
        click.echo("Warning: E2B_API_KEY not found. E2B execution might fail.", err=True)

    # Construct an ad-hoc test suite
    test_case = TestCase(
        description="Ad-hoc task execution",
        task=task,
        assertions=[
            Assertion(
                type=AssertionType.LLM_JUDGE,
                description="Evaluate the solution quality",
                target=AssertionTarget.FULL_RESPONSE,
                severity=AssertionSeverity.ERROR,
                metadata={
                    "judge_prompt": (
                        f"Evaluate the solution for the task: '{task}'. "
                        "Did the agent successfully complete the task? "
                        "Is the code correct and high quality? "
                        "Respond with a score 0-1 and reasoning."
                    )
                },
            )
        ],
    )

    suite = TestSuite(
        name="Ad-hoc Evaluation",
        description=f"Evaluation of task: {task}",
        test_cases=[test_case],
        # We can create a temporary instruction file or use defaults
        metadata={},
    )

    # Setup E2B Executor
    try:
        from evaluator.executors.base import SandboxConfig

        # Use claude-tools template for better capabilities
        sandbox_config = SandboxConfig(template="claude-tools")
        executor = E2BExecutor(
            api_key=api_key,
            sandbox_config=sandbox_config,
        )
    except ImportError:
        click.echo("Error: 'evaluator[e2b]' dependencies not installed.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error initializing E2B executor: {e}", err=True)
        sys.exit(1)

    # Run the test
    runner = TestRunner(api_key=api_key, executor=executor)

    click.echo("Spinning up sandbox and running agent...")
    result = runner.run_test(test_case, suite)

    # Report results
    click.echo("\n" + "=" * 50)
    click.echo(f"Status: {'PASSED' if result.passed else 'FAILED'}")
    click.echo(f"Duration: {result.duration_seconds:.2f}s")

    click.echo("\n--- Agent Response ---")
    click.echo(
        result.agent_response.full_response[:1000]
        + ("..." if len(result.agent_response.full_response) > 1000 else "")
    )

    if result.agent_response.generated_code:
        click.echo("\n--- Generated Code ---")
        for i, code in enumerate(result.agent_response.generated_code):
            click.echo(f"\nFile {i + 1}:")
            click.echo(code[:500] + ("..." if len(code) > 500 else ""))

    click.echo("\n--- Evaluation ---")
    for assertion_result in result.assertion_results:
        click.echo(f"{assertion_result.message}")
        if assertion_result.score is not None:
            click.echo(f"Score: {assertion_result.score}")

    sys.exit(0 if result.passed else 1)


@cli.command()
@click.option(
    "--tests",
    type=click.Path(exists=True),
    default="tests/backtests",
    help="Directory containing test files",
)
@click.option(
    "--output",
    type=click.Path(),
    default="backtest_results.md",
    help="Output file for results",
)
@click.option(
    "--html",
    type=click.Path(),
    default=None,
    help="Generate HTML report at this path",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key",
)
@click.option(
    "--executor",
    type=click.Choice(["local", "e2b"]),
    default="local",
    help="Execution backend: 'local' (default) or 'e2b' (isolated sandbox)",
)
@click.option(
    "--e2b-template",
    type=str,
    default="base",
    help="E2B template to use: 'base' or 'claude-tools' (only used with --executor e2b)",
)
def test(
    tests: str,
    output: str,
    html: Optional[str],
    api_key: Optional[str],
    executor: str,
    e2b_template: str,
) -> None:
    """Run backtests defined in YAML files."""
    click.echo(f"Running backtests from {tests}...")

    # Parse tests
    try:
        test_suites = YAMLTestParser.parse_directory(tests)
        if not test_suites:
            click.echo("No test files found.", err=True)
            sys.exit(1)
        click.echo(f"Found {len(test_suites)} test suites")
    except Exception as e:
        click.echo(f"Error parsing tests: {e}", err=True)
        sys.exit(1)

    # Create executor based on choice
    if executor == "e2b":
        try:
            from evaluator.executors.base import SandboxConfig

            click.echo(f"Using E2B sandbox executor with template: {e2b_template}")
            sandbox_config = SandboxConfig(template=e2b_template)
            executor_instance = E2BExecutor(
                api_key=api_key,
                sandbox_config=sandbox_config,
            )
        except ImportError:
            click.echo(
                "E2B executor requires e2b-code-interpreter. "
                "Install with: uv pip install 'evaluator[e2b]'",
                err=True,
            )
            sys.exit(1)
    else:
        click.echo("Using local executor")
        executor_instance = LocalExecutor(api_key=api_key)

    # Run tests
    runner = TestRunner(api_key=api_key, executor=executor_instance)
    all_results = runner.run_suites(test_suites)

    # Flatten results
    flat_results = []
    for suite_name, results in all_results.items():
        flat_results.extend(results)

    # Generate reports
    passed = sum(1 for r in flat_results if r.passed)
    failed = sum(1 for r in flat_results if not r.passed)
    total = len(flat_results)

    click.echo(f"\nResults: {passed}/{total} passed, {failed} failed")

    # Save results based on extension
    if output.endswith(".json"):
        with open(output, "w", encoding="utf-8") as f:
            json.dump([r.model_dump(mode="json") for r in flat_results], f, indent=2)
        click.echo(f"JSON results saved to {output}")
    else:
        # Save markdown report
        MarkdownReporter.save(flat_results, output)
        click.echo(f"Markdown report saved to {output}")

    # Save HTML report if requested
    if html:
        HTMLReporter.save(flat_results, html)
        click.echo(f"HTML report saved to {html}")

    sys.exit(0 if failed == 0 else 1)


@cli.command()
@click.option(
    "--tests",
    type=click.Path(exists=True),
    default="tests/backtests",
    help="Directory containing test files",
)
def list_tests(tests: str) -> None:
    """List all available tests."""
    try:
        test_suites = YAMLTestParser.parse_directory(tests)
    except Exception as e:
        click.echo(f"Error parsing tests: {e}", err=True)
        sys.exit(1)

    for suite in test_suites:
        click.echo(f"\n{suite.name}")
        click.echo(f"  Description: {suite.description}")
        click.echo(f"  Instruction version: {suite.instructions_version}")
        click.echo("  Test cases:")
        for test_case in suite.test_cases:
            click.echo(f"    - {test_case.description}")
            for assertion in test_case.assertions:
                click.echo(f"      [{assertion.type.value}] {assertion.description}")


if __name__ == "__main__":
    cli()
