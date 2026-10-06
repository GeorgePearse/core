"""Tests for ad-hoc task execution and CLI workflow."""

import io
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from evaluator.cli import cli, run_ad_hoc_task
from evaluator.executors.e2b import E2BExecutor
from evaluator.models import TestResult, AgentResponse, AssertionResult, Assertion, AssertionType


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up environment variables."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("E2B_API_KEY", "fake-e2b-key")


class TestAdHocExecution:
    """Test the ad-hoc task execution flow."""

    def test_cli_invokes_run_ad_hoc_task(self, mock_env_vars):
        """Test that the CLI invokes run_ad_hoc_task with arguments."""
        runner = CliRunner()

        with patch("evaluator.cli.run_ad_hoc_task") as mock_run:
            result = runner.invoke(cli, ["Write a hello world function"])

            assert result.exit_code == 0
            mock_run.assert_called_once()
            args = mock_run.call_args
            assert args[0][0] == "Write a hello world function"

    @patch("evaluator.cli.E2BExecutor")
    @patch("evaluator.cli.TestRunner")
    def test_run_ad_hoc_task_flow(self, MockRunner, MockExecutor, mock_env_vars):
        """Test the full orchestration of run_ad_hoc_task."""
        # Setup mocks
        mock_executor_instance = MockExecutor.return_value
        mock_runner_instance = MockRunner.return_value

        # Mock successful result
        mock_result = MagicMock(spec=TestResult)
        mock_result.passed = True
        mock_result.duration_seconds = 1.5
        mock_result.agent_response = AgentResponse(
            task="task",
            full_response="Here is the code",
            generated_code=["def hello(): print('hello')"],
            model="claude",
            instruction_file_path="",
        )
        mock_result.assertion_results = [
            AssertionResult(
                assertion=MagicMock(spec=Assertion), passed=True, message="Good job", score=1.0
            )
        ]
        mock_runner_instance.run_test.return_value = mock_result

        # Execute
        with pytest.raises(SystemExit) as excinfo:
            run_ad_hoc_task("Write a hello world function", "fake-key", "fake-e2b-key")
        assert excinfo.value.code == 0

        # Verify Executor Init
        MockExecutor.assert_called_once()
        _, kwargs = MockExecutor.call_args
        assert kwargs["api_key"] == "fake-key"
        assert kwargs["sandbox_config"].template == "claude-tools"

        # Verify Runner Usage
        MockRunner.assert_called_once_with(api_key="fake-key", executor=mock_executor_instance)
        mock_runner_instance.run_test.assert_called_once()

        # Verify Test Suite Construction
        call_args = mock_runner_instance.run_test.call_args
        test_case = call_args[0][0]
        test_suite = call_args[0][1]

        assert test_case.task == "Write a hello world function"
        assert len(test_case.assertions) == 1
        assert test_case.assertions[0].type == AssertionType.LLM_JUDGE
        assert test_suite.description == "Evaluation of task: Write a hello world function"


class TestCodeUpload:
    """Test the local code upload functionality in E2BExecutor."""

    def test_upload_local_code_creates_tarball(self, tmp_path):
        """Test that _upload_local_code creates and uploads a tarball."""
        # Create dummy source structure
        src_dir = tmp_path / "src" / "evaluator"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "main.py").write_text("print('hello')")

        # Mock executor and sandbox
        executor = E2BExecutor(api_key="fake", cache_dir=tmp_path / ".cache")
        mock_sandbox = MagicMock()

        # We need to patch Path to return our tmp_path when looking for "src/evaluator"
        # But "src/evaluator" is hardcoded in the method.
        # We can chdir to tmp_path for this test.

        import os

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            executor._upload_local_code(mock_sandbox)
        finally:
            os.chdir(cwd)

        # Verify sandbox interaction
        # 1. wrote file
        mock_sandbox.files.write.assert_called_once()
        args = mock_sandbox.files.write.call_args
        path = args[0][0]
        content = args[0][1]

        assert path == "/tmp/evaluator.tar.gz"
        assert isinstance(content, bytes)

        # Verify content is a valid tarball containing our files
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            names = tar.getnames()
            assert "evaluator/__init__.py" in names
            assert "evaluator/main.py" in names

        # 2. extracted file
        mock_sandbox.commands.run.assert_called_once()
        cmd = mock_sandbox.commands.run.call_args[0][0]
        assert "tar -xzf" in cmd
        assert "-C /workspace/pkg" in cmd
