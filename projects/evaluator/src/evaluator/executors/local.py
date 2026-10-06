"""Local test executor - runs tests in the current environment."""

import time
from typing import Optional

from evaluator.agent import AgentInvoker
from evaluator.executors.base import ExecutionContext, ExecutorBackend
from evaluator.models import TestCase, TestSuite


class LocalExecutor(ExecutorBackend):
    """Executor that runs tests locally without sandboxing."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize local executor.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
        """
        self.agent = AgentInvoker(api_key=api_key)

    def execute_test(
        self,
        test_case: TestCase,
        test_suite: TestSuite,
    ) -> ExecutionContext:
        """Execute test locally.

        Args:
            test_case: The test case to execute
            test_suite: The test suite context

        Returns:
            ExecutionContext with execution details
        """
        start_time = time.time()

        try:
            # Invoke agent
            agent_response = self.agent.invoke(
                task=test_case.task,
                instruction_file_path=test_suite.metadata.get(
                    "instruction_file", "/home/georgepearse/CLAUDE.md"
                ),
                model=test_suite.model_under_test,
            )

            execution_time_ms = (time.time() - start_time) * 1000

            return ExecutionContext(
                agent_response=agent_response,
                execution_time_ms=execution_time_ms,
                execution_mode="local",
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            # Return error context
            return ExecutionContext(
                agent_response=None,  # type: ignore
                execution_time_ms=execution_time_ms,
                execution_mode="local",
                error_message=str(e),
                exit_code=1,
            )

    def setup(self) -> None:
        """No setup needed for local executor."""
        pass

    def teardown(self) -> None:
        """No cleanup needed for local executor."""
        pass
