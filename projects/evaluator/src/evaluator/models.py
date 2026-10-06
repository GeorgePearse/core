"""Data models for the backtesting framework."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class AssertionType(str, Enum):
    """Types of assertions supported by the framework."""

    MUST_CONTAIN = "must_contain"
    MUST_NOT_CONTAIN = "must_not_contain"
    REGEX_MATCH = "regex_match"
    JSON_SCHEMA = "json_schema"
    LLM_JUDGE = "llm_judge"
    CODE_ANALYSIS = "code_analysis"
    SNAPSHOT = "snapshot"
    CODE_CONTAINS = "code_contains"
    CODE_EXCLUDES = "code_excludes"
    # Diff-specific assertion types
    DIFF_JUDGE = "diff_judge"  # LLM evaluation of diff quality
    DIFF_SYNTAX = "diff_syntax"  # Validates diff is syntactically correct
    DIFF_APPLIES = "diff_applies"  # Validates diff can be cleanly applied


class AssertionSeverity(str, Enum):
    """Severity levels for assertion failures."""

    ERROR = "error"
    WARNING = "warning"


class AssertionTarget(str, Enum):
    """What part of the response to check."""

    GENERATED_COMMANDS = "generated_commands"
    GENERATED_CODE = "generated_code"
    FULL_RESPONSE = "full_response"
    TOOL_CALLS = "tool_calls"
    GENERATED_DIFF = "generated_diff"  # Git diff output from model


class Assertion(BaseModel):
    """Definition of an assertion to run on agent responses."""

    type: AssertionType
    target: AssertionTarget = Field(default=AssertionTarget.FULL_RESPONSE)
    description: str
    severity: AssertionSeverity = Field(default=AssertionSeverity.ERROR)
    pattern: Optional[str] = None
    expected_value: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestCase(BaseModel):
    """A single test case within a test suite."""

    description: str
    task: str
    assertions: list[Assertion]
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestSuite(BaseModel):
    """A suite of related test cases."""

    name: str
    description: str
    instructions_version: str = Field(default="main")
    model_under_test: str = Field(default="claude-3-5-sonnet-20250109")
    test_cases: list[TestCase]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssertionResult(BaseModel):
    """Result of evaluating a single assertion."""

    assertion: Assertion
    passed: bool
    message: str
    score: Optional[float] = None  # For LLM judge results (0-1)
    evidence: Optional[dict[str, Any]] = None  # Supporting data
    timestamp: datetime = Field(default_factory=_utc_now)


class AgentResponse(BaseModel):
    """Response from the AI agent."""

    task: str
    full_response: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    generated_code: list[str] = Field(default_factory=list)
    generated_commands: list[str] = Field(default_factory=list)
    generated_diff: Optional[str] = None  # Raw git diff output from model
    model: str
    timestamp: datetime = Field(default_factory=_utc_now)
    instruction_file_path: str
    conversation_trace: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestResult(BaseModel):
    """Result of running a test case."""

    test_case: TestCase
    agent_response: AgentResponse
    assertion_results: list[AssertionResult]
    passed: bool
    timestamp: datetime = Field(default_factory=_utc_now)
    duration_seconds: float

    @property
    def failures(self) -> list[AssertionResult]:
        """Get all failed assertions."""
        return [r for r in self.assertion_results if not r.passed]

    @property
    def warnings(self) -> list[AssertionResult]:
        """Get all warnings (non-error assertions that failed)."""
        return [
            r
            for r in self.assertion_results
            if not r.passed and r.assertion.severity == AssertionSeverity.WARNING
        ]
