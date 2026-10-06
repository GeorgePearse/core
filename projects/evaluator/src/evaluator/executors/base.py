"""Base executor interface for running tests in different environments."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from evaluator.models import AgentResponse, TestCase, TestSuite


class ExecutionContext(BaseModel):
    """Complete context from test execution including outputs and metrics."""

    agent_response: Optional[AgentResponse] = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    execution_time_ms: float = 0.0
    memory_peak_mb: Optional[float] = None
    sandbox_info: Optional[dict[str, Any]] = None
    execution_mode: str = "local"  # "local" or "e2b"
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutorBackend(ABC):
    """Abstract base class for test execution backends."""

    @abstractmethod
    def execute_test(
        self,
        test_case: TestCase,
        test_suite: TestSuite,
    ) -> ExecutionContext:
        """Execute a single test case and return execution context.

        Args:
            test_case: The test case to execute
            test_suite: The test suite context

        Returns:
            ExecutionContext with all execution details and outputs

        Raises:
            ExecutionError: If execution fails critically
        """
        pass

    @abstractmethod
    def setup(self) -> None:
        """Set up the execution environment."""
        pass

    @abstractmethod
    def teardown(self) -> None:
        """Clean up the execution environment."""
        pass


class ExecutionError(Exception):
    """Raised when test execution fails."""

    pass


class SandboxConfig(BaseModel):
    """Configuration for sandbox-based execution.

    Supports two modes:
    1. Curated templates: Use named templates like "base" or "claude-tools"
    2. Custom Dockerfiles: Point to a custom Dockerfile for full environment control
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "template": "claude-tools",
                "timeout_seconds": 600,
                "memory_limit_mb": 4096,
                "environment_vars": {"LOG_LEVEL": "DEBUG"},
            }
        }
    )

    # Template selection
    template: Optional[str] = "base"  # Name of curated template (base, claude-tools, etc.)
    custom_dockerfile: Optional[str] = None  # Path to custom Dockerfile (overrides template)

    # Resource limits
    timeout_seconds: int = 300
    memory_limit_mb: int = 2048
    cpu_cores: Optional[int] = None

    # Network and persistence
    enable_networking: bool = True
    preserve_on_error: bool = False

    # Environment variables to inject
    environment_vars: dict[str, str] = Field(default_factory=dict)
