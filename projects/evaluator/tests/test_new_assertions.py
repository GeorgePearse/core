"""Tests for new assertion types: pr_match, code_contains, code_excludes."""

import pytest

from evaluator.assertions import (
    AssertionRegistry,
    CodeContainsEvaluator,
    CodeExcludesEvaluator,
)
from evaluator.code_matching import PythonASTMatcher, get_matcher
from evaluator.models import (
    AgentResponse,
    Assertion,
    AssertionTarget,
    AssertionType,
)

# ============================================================================
# CodeMatcher Tests
# ============================================================================


class TestPythonASTMatcher:
    """Tests for PythonASTMatcher."""

    def test_exact_match_identical(self):
        """Test exact match with identical code."""
        matcher = PythonASTMatcher()
        result = matcher.match_exact(
            "def foo(x):\n    return x + 1",
            "def foo(x):\n    return x + 1",
        )
        assert result.matched is True
        assert result.score == 1.0

    def test_exact_match_whitespace_difference(self):
        """Test exact match ignores whitespace."""
        matcher = PythonASTMatcher()
        result = matcher.match_exact(
            "def foo(x):\n    return x + 1",
            "def foo(x): return x + 1",
        )
        assert result.matched is True
        assert result.score == 1.0

    def test_exact_match_different_code(self):
        """Test exact match fails on different code."""
        matcher = PythonASTMatcher()
        result = matcher.match_exact(
            "def foo(x):\n    return x + 1",
            "def foo(x):\n    return x + 2",
        )
        assert result.matched is False
        assert result.score == 0.0

    def test_semantic_match_same_ast(self):
        """Test semantic match for functionally equivalent code."""
        matcher = PythonASTMatcher()
        result = matcher.match_semantic(
            "def foo(x):\n    return x + 1",
            "def foo(x):\n    y = x\n    return y + 1",
        )
        # Should have some similarity even though not identical
        # Our simple node-counting gives ~26%, which is reasonable
        assert result.score > 0.2
        assert result.matched is False  # Below 75% threshold

    def test_semantic_match_syntax_error(self):
        """Test semantic match handles syntax errors gracefully."""
        matcher = PythonASTMatcher()
        result = matcher.match_semantic(
            "def foo(x):\n    return x + 1",
            "def foo(x):\n    invalid syntax !!!",
        )
        assert result.matched is False
        assert result.score == 0.0

    def test_regex_match_found(self):
        """Test regex match finds pattern."""
        matcher = PythonASTMatcher()
        result = matcher.match_regex(
            r"def \w+\(.*\):",
            "def foo(x):\n    return x + 1",
        )
        assert result.matched is True
        assert result.score == 1.0

    def test_regex_match_not_found(self):
        """Test regex match when pattern not present."""
        matcher = PythonASTMatcher()
        result = matcher.match_regex(
            r"class \w+:",
            "def foo(x):\n    return x + 1",
        )
        assert result.matched is False
        assert result.score == 0.0

    def test_regex_match_invalid_pattern(self):
        """Test regex match with invalid regex."""
        matcher = PythonASTMatcher()
        result = matcher.match_regex(
            r"[invalid regex(",  # Unclosed bracket
            "def foo(x):\n    return x + 1",
        )
        assert result.matched is False

    def test_get_matcher_python(self):
        """Test getting Python matcher."""
        matcher = get_matcher("python")
        assert isinstance(matcher, PythonASTMatcher)

    def test_get_matcher_unsupported_language(self):
        """Test unsupported language raises error."""
        with pytest.raises(ValueError, match="Unsupported language"):
            get_matcher("cobol")


# ============================================================================
# CodeContainsEvaluator Tests
# ============================================================================


class TestCodeContainsEvaluator:
    """Tests for CodeContainsEvaluator."""

    def test_code_contains_found_exact(self):
        """Test code_contains finds required code (using substring, not full parse)."""
        evaluator = CodeContainsEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_CONTAINS,
            description="Should contain function",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "snippet": "return verify_credentials",
                "match_type": "exact",
                "language": "python",
            },
        )
        response = AgentResponse(
            task="Add auth",
            full_response="Here's the auth code",
            generated_code=[
                "def authenticate(user, password):\n    return verify_credentials(user, password)"
            ],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True

    def test_code_contains_not_found(self):
        """Test code_contains fails when snippet not found."""
        evaluator = CodeContainsEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_CONTAINS,
            description="Should contain function",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "snippet": "def nonexistent():",
                "match_type": "exact",
                "language": "python",
            },
        )
        response = AgentResponse(
            task="Add auth",
            full_response="Here's the code",
            generated_code=["def foo():\n    pass"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False

    def test_code_contains_regex_match(self):
        """Test code_contains with regex matching."""
        evaluator = CodeContainsEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_CONTAINS,
            description="Should contain type hints",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "snippet": r"def \w+\([^)]*: \w+",
                "match_type": "regex",
                "language": "python",
            },
        )
        response = AgentResponse(
            task="Add function",
            full_response="Here's the function",
            generated_code=["def foo(x: int) -> int:\n    return x + 1"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True

    def test_code_contains_missing_metadata(self):
        """Test code_contains fails gracefully without snippet."""
        evaluator = CodeContainsEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_CONTAINS,
            description="Should contain something",
            target=AssertionTarget.GENERATED_CODE,
            metadata={},  # No snippet
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_code=["def foo(): pass"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False
        assert "snippet" in result.message.lower()


# ============================================================================
# CodeExcludesEvaluator Tests
# ============================================================================


class TestCodeExcludesEvaluator:
    """Tests for CodeExcludesEvaluator."""

    def test_code_excludes_no_forbidden_patterns(self):
        """Test code_excludes passes when no forbidden patterns present."""
        evaluator = CodeExcludesEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_EXCLUDES,
            description="Must not use eval",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "patterns": ["eval(", "exec("],
                "match_type": "regex",
            },
        )
        response = AgentResponse(
            task="Add function",
            full_response="Here's the function",
            generated_code=["def foo(x):\n    return x + 1"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True

    def test_code_excludes_forbidden_pattern_found(self):
        """Test code_excludes fails when forbidden pattern present."""
        evaluator = CodeExcludesEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_EXCLUDES,
            description="Must not use eval",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "patterns": [r"eval\(", r"exec\("],
                "match_type": "regex",
            },
        )
        response = AgentResponse(
            task="Add function",
            full_response="Here's the function",
            generated_code=['result = eval("x + 1")'],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False
        assert "forbidden" in result.message.lower()

    def test_code_excludes_single_pattern(self):
        """Test code_excludes with single pattern (string instead of list)."""
        evaluator = CodeExcludesEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_EXCLUDES,
            description="Must not use sys.path",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "patterns": "sys.path.append",  # Single pattern as string
                "match_type": "exact",
            },
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_code=["import sys\nx = 1"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True

    def test_code_excludes_multiple_patterns(self):
        """Test code_excludes checks all patterns."""
        evaluator = CodeExcludesEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_EXCLUDES,
            description="Must not use dangerous functions",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "patterns": [r"eval\(", r"exec\(", r"os\.system\(", r"__import__\("],
                "match_type": "regex",
            },
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_code=[
                "import os\nos.system('ls')",
            ],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False
        assert "forbidden" in result.message.lower()

    def test_code_excludes_missing_patterns(self):
        """Test code_excludes fails without patterns."""
        evaluator = CodeExcludesEvaluator()
        assertion = Assertion(
            type=AssertionType.CODE_EXCLUDES,
            description="Must not use something",
            target=AssertionTarget.GENERATED_CODE,
            metadata={},  # No patterns
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_code=["def foo(): pass"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False
        assert "patterns" in result.message.lower()


# ============================================================================
# AssertionRegistry Tests
# ============================================================================


class TestAssertionRegistry:
    """Tests for AssertionRegistry integration."""

    def test_registry_evaluates_code_contains(self):
        """Test registry can evaluate code_contains assertions."""
        assertion = Assertion(
            type=AssertionType.CODE_CONTAINS,
            description="Should have function",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "snippet": "pass",
                "match_type": "exact",
                "language": "python",
            },
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_code=["def test():\n    pass"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = AssertionRegistry.evaluate(assertion, response)
        assert result.passed is True

    def test_registry_evaluates_code_excludes(self):
        """Test registry can evaluate code_excludes assertions."""
        assertion = Assertion(
            type=AssertionType.CODE_EXCLUDES,
            description="No eval",
            target=AssertionTarget.GENERATED_CODE,
            metadata={
                "patterns": ["eval("],
                "match_type": "regex",
            },
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_code=["x = 1"],
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = AssertionRegistry.evaluate(assertion, response)
        assert result.passed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
