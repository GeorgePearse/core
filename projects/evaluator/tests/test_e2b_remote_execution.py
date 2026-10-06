"""Integration tests for E2B remote execution."""

import os
import pytest
from evaluator.executors.e2b import E2BExecutor
from evaluator.models import TestCase, TestSuite, Assertion, AssertionType
from evaluator.executors.base import SandboxConfig

# Skip tests if API keys are not configured
requires_api_keys = pytest.mark.skipif(
    not (os.getenv("E2B_API_KEY") and os.getenv("ANTHROPIC_API_KEY")),
    reason="E2B_API_KEY and ANTHROPIC_API_KEY required for integration tests",
)


class TestE2BRemoteExecution:
    """Integration tests for E2BExecutor running on real infrastructure."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create a real E2BExecutor."""
        # We rely on env vars for API keys
        return E2BExecutor(
            cache_dir=tmp_path,
            sandbox_config=SandboxConfig(timeout_seconds=300),  # Give it enough time
        )

    @requires_api_keys
    @pytest.mark.asyncio
    async def test_execute_test_real_sandbox(self, executor):
        """Execute a real test in an E2B sandbox."""

        # specific task that is quick but proves execution
        task = "Calculate 2 + 2 and print the result."

        test_case = TestCase(
            description="Simple calculation",
            task=task,
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN, description="Result should be 4", pattern="4"
                )
            ],
        )

        test_suite = TestSuite(
            name="Integration Test Suite",
            description="Testing E2B integration",
            test_cases=[test_case],
            model_under_test="claude-3-5-sonnet-20250109",
        )

        # This will actually:
        # 1. Build/Get the docker template (might take time first run)
        # 2. Spin up a sandbox
        # 3. Inject the agent code
        # 4. Run the agent (which calls Anthropic)
        # 5. Return results
        context = await executor.execute_test_async(test_case, test_suite)

        # Assertions on the real result
        assert context.execution_mode == "e2b"
        assert context.exit_code == 0
        assert context.error_message is None

        # We expect the agent to have run and produced output
        assert context.agent_response is not None
        assert context.agent_response.task == task

        # Verify the script printing happened (stdout check would need capsys,
        # but the main goal here is the execution logic)
