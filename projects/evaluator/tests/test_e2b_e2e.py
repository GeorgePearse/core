"""End-to-end tests for E2B executor with real Claude-code execution.

These tests actually spin up E2B sandboxes, invoke Claude, and wait for
real results. They require both E2B_API_KEY and ANTHROPIC_API_KEY to be set.

Run with:
    pytest tests/test_e2b_e2e.py -v -s --timeout=600

Note: These tests can take 1-5 minutes each due to sandbox spin-up
and Claude API calls.
"""

import asyncio
import os
import pytest
import pytest_asyncio
from evaluator.executors.e2b import E2BExecutor
from evaluator.executors.base import SandboxConfig
from evaluator.models import (
    Assertion,
    AssertionType,
    AssertionTarget,
    TestCase,
    TestSuite,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for all async tests.

    This is necessary because the E2B SDK caches event loop references
    internally, and creating new event loops between tests causes issues.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# Skip all tests if API keys are not configured
requires_api_keys = pytest.mark.skipif(
    not (os.getenv("E2B_API_KEY") and os.getenv("ANTHROPIC_API_KEY")),
    reason="E2B_API_KEY and ANTHROPIC_API_KEY required for E2E tests",
)

# Mark all tests as slow/integration
pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    requires_api_keys,
]


class TestE2BEndToEnd:
    """End-to-end tests that execute real tasks in E2B sandboxes."""

    @pytest.fixture(scope="class")
    def executor(self, tmp_path_factory):
        """Create a real E2BExecutor with reasonable timeout.

        Using class scope to share the executor across tests and avoid
        E2B SDK event loop issues.
        """
        tmp_path = tmp_path_factory.mktemp("e2b")
        return E2BExecutor(
            cache_dir=tmp_path,
            sandbox_config=SandboxConfig(timeout_seconds=300),
        )

    @pytest.fixture(scope="class")
    def default_test_suite(self) -> TestSuite:
        """Create a default test suite for testing."""
        return TestSuite(
            name="E2E Test Suite",
            description="End-to-end tests for E2B executor",
            model_under_test="claude-sonnet-4-20250514",
            test_cases=[],
            metadata={},
        )

    # =========================================================================
    # Basic Execution Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_simple_calculation(self, executor, default_test_suite):
        """Test that Claude can perform a simple calculation in the sandbox."""
        test_case = TestCase(
            description="Simple arithmetic calculation",
            task="What is 42 multiplied by 17? Just tell me the number.",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Response should contain the correct answer",
                    pattern="714",
                )
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        # Verify execution succeeded
        assert context.execution_mode == "e2b"
        assert context.error_message is None, f"Execution error: {context.error_message}"
        assert context.exit_code == 0

        # Verify we got a real response
        assert context.agent_response is not None
        assert context.agent_response.full_response
        assert "714" in context.agent_response.full_response

        print(f"\n[RESPONSE] {context.agent_response.full_response[:500]}")

    @pytest.mark.asyncio
    async def test_code_generation_python(self, executor, default_test_suite):
        """Test that Claude generates Python code correctly."""
        test_case = TestCase(
            description="Generate a Python function",
            task="""Write a Python function called 'fibonacci' that returns the nth 
            Fibonacci number. Use recursion with memoization. Include the function 
            in a code block.""",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should define fibonacci function",
                    pattern="def fibonacci",
                ),
                Assertion(
                    type=AssertionType.REGEX_MATCH,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should use memoization or cache",
                    pattern=r"(memo|cache|lru_cache|@functools)",
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None, f"Execution error: {context.error_message}"
        assert context.agent_response is not None

        # Check code was generated
        assert context.agent_response.generated_code, "No code blocks were extracted"

        # At least one code block should contain the function
        code_text = "\n".join(context.agent_response.generated_code)
        assert (
            "def fibonacci" in code_text or "def fibonacci" in context.agent_response.full_response
        )

        print(f"\n[GENERATED CODE]\n{code_text[:1000]}")

    @pytest.mark.asyncio
    async def test_bash_command_generation(self, executor, default_test_suite):
        """Test that Claude generates shell commands correctly."""
        test_case = TestCase(
            description="Generate bash commands",
            task="""Show me the bash commands to:
            1. Create a directory called 'myproject'
            2. Navigate into it
            3. Initialize a git repository
            
            Put the commands in a bash code block.""",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should create directory",
                    pattern="mkdir",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should initialize git",
                    pattern="git init",
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.agent_response is not None

        # Verify commands were extracted
        full_response = context.agent_response.full_response
        assert "mkdir" in full_response
        assert "git init" in full_response

        print(f"\n[COMMANDS] {context.agent_response.generated_commands}")

    # =========================================================================
    # Response Quality Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_response_completeness(self, executor, default_test_suite):
        """Test that the response contains all expected components."""
        test_case = TestCase(
            description="Check response structure",
            task="Explain what a binary search tree is in 2-3 sentences.",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should mention tree structure",
                    pattern="tree",
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None

        # Check all response fields are populated
        response = context.agent_response
        assert response is not None
        assert response.task == test_case.task
        assert response.model == default_test_suite.model_under_test
        assert response.full_response
        assert isinstance(response.conversation_trace, list)
        assert len(response.conversation_trace) > 0

        # Check execution context metadata
        assert context.execution_mode == "e2b"
        assert context.execution_time_ms > 0
        assert context.sandbox_info is not None

        print(f"\n[EXECUTION TIME] {context.execution_time_ms:.2f}ms")
        print(f"[SANDBOX INFO] {context.sandbox_info}")

    @pytest.mark.asyncio
    async def test_negative_assertion(self, executor, default_test_suite):
        """Test that MUST_NOT_CONTAIN assertions work."""
        test_case = TestCase(
            description="Check content exclusion",
            task="List 3 programming languages that are NOT Python. Just list the names.",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_NOT_CONTAIN,
                    description="Should not mention Python as one of the languages",
                    pattern="Python",  # This might still appear in context, but the list shouldn't be Python
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.agent_response is not None

        # The response should list other languages
        response_lower = context.agent_response.full_response.lower()
        # Should mention at least one other language
        other_languages = ["java", "javascript", "c++", "rust", "go", "ruby", "typescript"]
        found_other = any(lang in response_lower for lang in other_languages)
        assert found_other, "Response should mention other programming languages"

        print(f"\n[RESPONSE] {context.agent_response.full_response}")

    # =========================================================================
    # Complex Task Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_multi_step_task(self, executor, default_test_suite):
        """Test that Claude can handle a multi-step coding task."""
        test_case = TestCase(
            description="Multi-step coding task",
            task="""Create a Python class called 'Stack' with the following:
            1. An __init__ method that initializes an empty list
            2. A push method that adds an item
            3. A pop method that removes and returns the top item
            4. A peek method that returns the top item without removing it
            5. An is_empty method that returns True if the stack is empty
            
            Include the complete code in a Python code block.""",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should define Stack class",
                    pattern="class Stack",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should have push method",
                    pattern="def push",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should have pop method",
                    pattern="def pop",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should have peek method",
                    pattern="def peek",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    target=AssertionTarget.FULL_RESPONSE,
                    description="Should have is_empty method",
                    pattern="is_empty",
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.agent_response is not None

        # All assertions should be verifiable from the response
        response = context.agent_response.full_response
        assert "class Stack" in response
        assert "def push" in response
        assert "def pop" in response

        print(f"\n[STACK CLASS]\n{response[:1500]}")

    @pytest.mark.asyncio
    async def test_json_generation(self, executor, default_test_suite):
        """Test that Claude can generate valid JSON."""
        test_case = TestCase(
            description="JSON generation task",
            task="""Generate a JSON object representing a user with these fields:
            - name (string)
            - age (number) 
            - email (string)
            - is_active (boolean)
            - roles (array of strings with at least 2 roles)
            
            Return ONLY the JSON object, no explanation.""",
            assertions=[
                Assertion(
                    type=AssertionType.REGEX_MATCH,
                    description="Should be valid JSON structure",
                    pattern=r"\{[^}]+\}",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should have name field",
                    pattern='"name"',
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should have roles array",
                    pattern='"roles"',
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.agent_response is not None

        # Try to extract and parse JSON from response
        import json
        import re

        response = context.agent_response.full_response
        # Find JSON object in response
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                assert "name" in parsed
                print(f"\n[PARSED JSON] {json.dumps(parsed, indent=2)}")
            except json.JSONDecodeError as e:
                print(f"\n[JSON PARSE ERROR] {e}")
                print(f"[RAW RESPONSE] {response}")

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_handles_ambiguous_task(self, executor, default_test_suite):
        """Test that Claude handles ambiguous tasks gracefully."""
        test_case = TestCase(
            description="Ambiguous task handling",
            task="Fix the bug.",  # Intentionally vague
            assertions=[
                Assertion(
                    type=AssertionType.REGEX_MATCH,
                    description="Should ask for clarification or explain the issue",
                    pattern=r"(which|what|more|information|context|specific|clarif|code|bug)",
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        # Even with vague tasks, execution should succeed
        assert context.error_message is None
        assert context.agent_response is not None
        assert len(context.agent_response.full_response) > 0

        print(f"\n[RESPONSE TO VAGUE TASK] {context.agent_response.full_response[:500]}")

    @pytest.mark.asyncio
    async def test_long_response_handling(self, executor, default_test_suite):
        """Test that long responses are handled correctly."""
        test_case = TestCase(
            description="Long response task",
            task="""Write a comprehensive Python module for a simple REST API client.
            Include:
            1. A base Client class with __init__, get, post, put, delete methods
            2. Exception classes for different HTTP errors (400, 401, 404, 500)
            3. A Response class to wrap API responses
            4. Type hints throughout
            5. Docstrings for all classes and methods
            
            Make it production-ready code.""",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should define Client class",
                    pattern="class Client",
                ),
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should have docstrings",
                    pattern='"""',
                ),
            ],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.agent_response is not None

        # Response should be substantial
        assert len(context.agent_response.full_response) > 500

        # Code should be extracted
        assert len(context.agent_response.generated_code) > 0

        print(f"\n[RESPONSE LENGTH] {len(context.agent_response.full_response)} chars")
        print(f"[CODE BLOCKS] {len(context.agent_response.generated_code)}")

    # =========================================================================
    # Synchronous Execution Tests
    # =========================================================================

    def test_sync_simple_calculation(self, executor, default_test_suite):
        """Test synchronous execution with a simple task."""
        test_case = TestCase(
            description="Sync calculation test",
            task="What is 100 divided by 4? Just give me the number.",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should contain correct answer",
                    pattern="25",
                )
            ],
        )

        # Use sync method
        context = executor.execute_test(test_case, default_test_suite)

        assert context.execution_mode == "e2b"
        assert context.error_message is None
        assert context.agent_response is not None
        assert "25" in context.agent_response.full_response

        print(f"\n[SYNC RESPONSE] {context.agent_response.full_response}")

    def test_sync_code_generation(self, executor, default_test_suite):
        """Test synchronous code generation."""
        test_case = TestCase(
            description="Sync code generation",
            task="Write a Python function called 'greet' that takes a name and returns 'Hello, {name}!'",
            assertions=[
                Assertion(
                    type=AssertionType.MUST_CONTAIN,
                    description="Should define greet function",
                    pattern="def greet",
                ),
            ],
        )

        context = executor.execute_test(test_case, default_test_suite)

        assert context.error_message is None
        assert context.agent_response is not None
        assert "def greet" in context.agent_response.full_response

        print(f"\n[SYNC CODE]\n{context.agent_response.full_response}")


class TestE2BExecutionMetrics:
    """Tests focused on execution metrics and performance."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with metrics-focused config."""
        return E2BExecutor(
            cache_dir=tmp_path,
            sandbox_config=SandboxConfig(timeout_seconds=300),
        )

    @pytest.fixture
    def default_test_suite(self) -> TestSuite:
        return TestSuite(
            name="Metrics Test Suite",
            description="Tests for execution metrics",
            model_under_test="claude-sonnet-4-20250514",
            test_cases=[],
        )

    @pytest.mark.asyncio
    async def test_execution_time_tracked(self, executor, default_test_suite):
        """Verify execution time is accurately tracked."""
        test_case = TestCase(
            description="Timing test",
            task="Count from 1 to 5.",
            assertions=[],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.execution_time_ms > 0
        # Execution should take at least a few seconds (API call + sandbox overhead)
        assert context.execution_time_ms > 1000  # > 1 second

        print(f"\n[EXECUTION TIME] {context.execution_time_ms:.2f}ms")

    @pytest.mark.asyncio
    async def test_sandbox_info_populated(self, executor, default_test_suite):
        """Verify sandbox metadata is captured."""
        test_case = TestCase(
            description="Sandbox info test",
            task="Say hello.",
            assertions=[],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        assert context.sandbox_info is not None
        assert "session_id" in context.sandbox_info
        assert "template_id" in context.sandbox_info
        assert context.sandbox_info["session_id"] is not None

        print(f"\n[SANDBOX INFO] {context.sandbox_info}")

    @pytest.mark.asyncio
    async def test_stdout_stderr_captured(self, executor, default_test_suite):
        """Verify stdout/stderr from sandbox is captured."""
        test_case = TestCase(
            description="Output capture test",
            task="Print 'test output' to the console.",
            assertions=[],
        )

        context = await executor.execute_test_async(test_case, default_test_suite)

        assert context.error_message is None
        # stdout should contain the agent script output
        assert context.stdout is not None
        assert len(context.stdout) > 0

        print(f"\n[STDOUT LENGTH] {len(context.stdout)} chars")
        print(f"[STDOUT PREVIEW] {context.stdout[:500]}")


class TestE2BParallelExecution:
    """Tests for parallel/concurrent execution scenarios."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with higher session limit for parallel tests."""
        return E2BExecutor(
            cache_dir=tmp_path,
            max_sessions=3,
            sandbox_config=SandboxConfig(timeout_seconds=300),
        )

    @pytest.fixture
    def default_test_suite(self) -> TestSuite:
        return TestSuite(
            name="Parallel Test Suite",
            description="Tests for parallel execution",
            model_under_test="claude-sonnet-4-20250514",
            test_cases=[],
        )

    @pytest.mark.asyncio
    async def test_sequential_execution(self, executor, default_test_suite):
        """Run multiple tests sequentially and verify all complete."""
        tasks = [
            "What is 2 + 2?",
            "What is 3 * 3?",
            "What is 10 - 5?",
        ]
        expected = ["4", "9", "5"]

        results = []
        for task, expect in zip(tasks, expected):
            test_case = TestCase(
                description=f"Task: {task}",
                task=task,
                assertions=[
                    Assertion(
                        type=AssertionType.MUST_CONTAIN,
                        description=f"Should contain {expect}",
                        pattern=expect,
                    )
                ],
            )
            context = await executor.execute_test_async(test_case, default_test_suite)
            results.append(context)

        # All should succeed
        for i, context in enumerate(results):
            assert context.error_message is None, f"Task {i} failed: {context.error_message}"
            assert context.agent_response is not None
            assert expected[i] in context.agent_response.full_response

        print(f"\n[SEQUENTIAL RESULTS] All {len(results)} tasks completed successfully")


# Utility function for running a quick smoke test
def run_smoke_test():
    """Run a single quick test to verify E2B is working."""
    import asyncio
    from pathlib import Path
    import tempfile

    async def _smoke():
        with tempfile.TemporaryDirectory() as tmp:
            executor = E2BExecutor(
                cache_dir=Path(tmp),
                sandbox_config=SandboxConfig(timeout_seconds=120),
            )

            test_case = TestCase(
                description="Smoke test",
                task="What is 1 + 1?",
                assertions=[],
            )

            test_suite = TestSuite(
                name="Smoke Test",
                description="Quick verification",
                model_under_test="claude-sonnet-4-20250514",
                test_cases=[test_case],
            )

            print("Starting E2B smoke test...")
            context = await executor.execute_test_async(test_case, test_suite)

            if context.error_message:
                print(f"FAILED: {context.error_message}")
                return False

            print(f"SUCCESS: {context.agent_response.full_response[:100]}")
            print(f"Execution time: {context.execution_time_ms:.2f}ms")
            return True

    return asyncio.run(_smoke())


if __name__ == "__main__":
    # Allow running smoke test directly
    import sys

    if not (os.getenv("E2B_API_KEY") and os.getenv("ANTHROPIC_API_KEY")):
        print("ERROR: E2B_API_KEY and ANTHROPIC_API_KEY must be set")
        sys.exit(1)

    success = run_smoke_test()
    sys.exit(0 if success else 1)
