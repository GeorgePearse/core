"""AI Backtesting framework for instruction files (AGENTS.md, CLAUDE.md)."""

__version__ = "0.1.0"

from evaluator.models import (
    AgentResponse,
    Assertion,
    AssertionResult,
    AssertionSeverity,
    AssertionTarget,
    AssertionType,
    TestCase,
    TestResult,
    TestSuite,
)

# Diff-related exports
from evaluator.diff_models import (
    DiffHunk,
    DiffLine,
    DiffLineType,
    DiffValidationResult,
    FileDiff,
    GitDiff,
)
from evaluator.diff_parser import DiffParser, DiffValidator, extract_diff_from_response
from evaluator.diff_judge import (
    DiffAppliesEvaluator,
    DiffJudgeEvaluator,
    DiffSyntaxEvaluator,
)

__all__ = [
    # Core models
    "AgentResponse",
    "Assertion",
    "AssertionResult",
    "AssertionSeverity",
    "AssertionTarget",
    "AssertionType",
    "TestCase",
    "TestResult",
    "TestSuite",
    # Diff models
    "DiffHunk",
    "DiffLine",
    "DiffLineType",
    "DiffValidationResult",
    "FileDiff",
    "GitDiff",
    # Diff utilities
    "DiffParser",
    "DiffValidator",
    "extract_diff_from_response",
    # Diff evaluators
    "DiffAppliesEvaluator",
    "DiffJudgeEvaluator",
    "DiffSyntaxEvaluator",
]
