"""Tests for the diff judge evaluation system."""

from unittest.mock import MagicMock, patch

import pytest

from evaluator.diff_judge import (
    DiffAppliesEvaluator,
    DiffJudgeEvaluator,
    DiffSyntaxEvaluator,
)
from evaluator.diff_models import (
    DiffHunk,
    DiffLine,
    DiffLineType,
    DiffValidationResult,
    FileDiff,
    GitDiff,
)
from evaluator.diff_parser import DiffParser, DiffValidator, extract_diff_from_response
from evaluator.models import (
    AgentResponse,
    Assertion,
    AssertionTarget,
    AssertionType,
)


# ============================================================================
# Sample Diffs for Testing
# ============================================================================

SIMPLE_DIFF = """diff --git a/hello.py b/hello.py
index abc123..def456 100644
--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
+    return True
"""

NEW_FILE_DIFF = """diff --git a/new_file.py b/new_file.py
new file mode 100644
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def new_function():
+    return 42
+
"""

DELETE_FILE_DIFF = """diff --git a/old_file.py b/old_file.py
deleted file mode 100644
--- a/old_file.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old_function():
-    pass
"""

MULTI_FILE_DIFF = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,2 +1,2 @@
 def func1():
-    pass
+    return 1

diff --git a/file2.py b/file2.py
--- a/file2.py
+++ b/file2.py
@@ -1,2 +1,2 @@
 def func2():
-    pass
+    return 2
"""

BINARY_DIFF = """diff --git a/image.png b/image.png
Binary files a/image.png and b/image.png differ
"""


# ============================================================================
# DiffParser Tests
# ============================================================================


class TestDiffParser:
    """Tests for DiffParser."""

    def test_parse_simple_diff(self):
        """Test parsing a simple single-file diff."""
        parser = DiffParser()
        result = parser.parse(SIMPLE_DIFF)

        assert isinstance(result, GitDiff)
        assert result.total_files_changed == 1
        assert result.files[0].old_path == "hello.py"
        assert result.files[0].new_path == "hello.py"
        assert len(result.files[0].hunks) == 1

    def test_parse_new_file_diff(self):
        """Test parsing a diff for a new file."""
        parser = DiffParser()
        result = parser.parse(NEW_FILE_DIFF)

        assert result.total_files_changed == 1
        assert result.files[0].is_new_file is True
        assert len(result.files_added) == 1

    def test_parse_delete_file_diff(self):
        """Test parsing a diff for a deleted file."""
        parser = DiffParser()
        result = parser.parse(DELETE_FILE_DIFF)

        assert result.total_files_changed == 1
        assert result.files[0].is_deleted_file is True
        assert len(result.files_deleted) == 1

    def test_parse_multi_file_diff(self):
        """Test parsing a diff with multiple files."""
        parser = DiffParser()
        result = parser.parse(MULTI_FILE_DIFF)

        assert result.total_files_changed == 2
        assert result.files[0].path == "file1.py"
        assert result.files[1].path == "file2.py"

    def test_parse_binary_diff(self):
        """Test parsing a binary file diff."""
        parser = DiffParser()
        result = parser.parse(BINARY_DIFF)

        assert result.total_files_changed == 1
        assert result.files[0].is_binary is True

    def test_hunk_line_counts(self):
        """Test that hunk line counts are correct."""
        parser = DiffParser()
        result = parser.parse(SIMPLE_DIFF)

        hunk = result.files[0].hunks[0]
        assert hunk.old_start == 1
        assert hunk.old_count == 3
        assert hunk.new_start == 1
        assert hunk.new_count == 4
        assert len(hunk.additions) == 2  # Two added lines
        assert len(hunk.deletions) == 1  # One deleted line
        assert len(hunk.context_lines) == 2  # Two context lines (def line + trailing empty)

    def test_additions_and_deletions_count(self):
        """Test total additions and deletions."""
        parser = DiffParser()
        result = parser.parse(SIMPLE_DIFF)

        assert result.total_additions == 2
        assert result.total_deletions == 1

    def test_parse_from_response_markdown_block(self):
        """Test extracting diff from markdown code block."""
        parser = DiffParser()
        response = f"""
Here's the fix for the issue:

```diff
{SIMPLE_DIFF}
```

This should work now.
"""
        result = parser.parse_from_response(response)

        assert result is not None
        assert result.total_files_changed == 1

    def test_parse_from_response_no_diff(self):
        """Test that None is returned when no diff is found."""
        parser = DiffParser()
        response = "This response has no diff in it."

        result = parser.parse_from_response(response)
        assert result is None

    def test_extract_diff_from_response_convenience(self):
        """Test the convenience function."""
        response = f"```diff\n{SIMPLE_DIFF}```"
        result = extract_diff_from_response(response)

        assert result is not None
        assert result.total_files_changed == 1

    def test_git_diff_summary(self):
        """Test GitDiff summary generation."""
        parser = DiffParser()
        result = parser.parse(NEW_FILE_DIFF)

        summary = result.summary()
        assert "Files changed: 1" in summary
        assert "New files:" in summary

    def test_get_file_by_path(self):
        """Test getting a specific file diff by path."""
        parser = DiffParser()
        result = parser.parse(MULTI_FILE_DIFF)

        file1 = result.get_file("file1.py")
        assert file1 is not None
        assert file1.path == "file1.py"

        nonexistent = result.get_file("nonexistent.py")
        assert nonexistent is None


# ============================================================================
# DiffValidator Tests
# ============================================================================


class TestDiffValidator:
    """Tests for DiffValidator."""

    def test_validate_syntax_valid_diff(self):
        """Test syntax validation passes for valid diff."""
        parser = DiffParser()
        validator = DiffValidator()

        diff = parser.parse(SIMPLE_DIFF)
        result = validator.validate_syntax(diff)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_syntax_empty_diff(self):
        """Test syntax validation fails for empty diff."""
        validator = DiffValidator()
        diff = GitDiff(raw_diff="")

        result = validator.validate_syntax(diff)

        assert result.is_valid is False
        assert "no file changes" in result.errors[0].lower()

    def test_validate_can_apply_success(self):
        """Test that diff can be applied to matching content."""
        parser = DiffParser()
        validator = DiffValidator()

        diff = parser.parse(SIMPLE_DIFF)
        file_contents = {
            "hello.py": 'def hello():\n    print("Hello")\n',
        }

        result = validator.validate_can_apply(diff, file_contents)
        assert result.is_valid is True

    def test_validate_can_apply_file_missing(self):
        """Test validation fails when file to modify is missing."""
        parser = DiffParser()
        validator = DiffValidator()

        diff = parser.parse(SIMPLE_DIFF)
        file_contents = {}  # No files

        result = validator.validate_can_apply(diff, file_contents)
        assert result.is_valid is False
        assert "not found" in result.errors[0].lower()

    def test_validate_can_apply_context_mismatch(self):
        """Test validation fails when context doesn't match."""
        parser = DiffParser()
        validator = DiffValidator()

        diff = parser.parse(SIMPLE_DIFF)
        file_contents = {
            "hello.py": 'def goodbye():\n    print("Goodbye")\n',  # Different content
        }

        result = validator.validate_can_apply(diff, file_contents)
        assert result.is_valid is False
        assert "mismatch" in result.errors[0].lower()

    def test_validate_new_file_already_exists(self):
        """Test validation fails when new file already exists."""
        parser = DiffParser()
        validator = DiffValidator()

        diff = parser.parse(NEW_FILE_DIFF)
        file_contents = {
            "new_file.py": "existing content",  # File already exists
        }

        result = validator.validate_can_apply(diff, file_contents)
        assert result.is_valid is False
        assert "already exists" in result.errors[0].lower()


# ============================================================================
# DiffValidationResult Tests
# ============================================================================


class TestDiffValidationResult:
    """Tests for DiffValidationResult dataclass."""

    def test_add_error(self):
        """Test adding an error invalidates the result."""
        result = DiffValidationResult(is_valid=True)
        result.add_error("Something went wrong")

        assert result.is_valid is False
        assert "Something went wrong" in result.errors

    def test_add_warning(self):
        """Test adding a warning doesn't invalidate."""
        result = DiffValidationResult(is_valid=True)
        result.add_warning("Minor issue")

        assert result.is_valid is True
        assert "Minor issue" in result.warnings


# ============================================================================
# DiffModels Tests
# ============================================================================


class TestDiffModels:
    """Tests for diff data models."""

    def test_diff_line_types(self):
        """Test DiffLine creation with different types."""
        addition = DiffLine(
            type=DiffLineType.ADDITION,
            content="new line",
            new_line_no=5,
        )
        assert addition.type == DiffLineType.ADDITION
        assert addition.old_line_no is None

        deletion = DiffLine(
            type=DiffLineType.DELETION,
            content="old line",
            old_line_no=3,
        )
        assert deletion.type == DiffLineType.DELETION
        assert deletion.new_line_no is None

    def test_file_diff_path_property(self):
        """Test FileDiff.path returns the right path."""
        # New file (only new_path)
        new_file = FileDiff(new_path="new.py", is_new_file=True)
        assert new_file.path == "new.py"

        # Deleted file (only old_path)
        deleted_file = FileDiff(old_path="old.py", is_deleted_file=True)
        assert deleted_file.path == "old.py"

        # Modified file (both paths, prefers new)
        modified = FileDiff(old_path="old.py", new_path="renamed.py")
        assert modified.path == "renamed.py"

    def test_file_diff_totals(self):
        """Test FileDiff total calculations."""
        hunk = DiffHunk(
            old_start=1,
            old_count=3,
            new_start=1,
            new_count=4,
            header="@@ -1,3 +1,4 @@",
            lines=[
                DiffLine(type=DiffLineType.CONTEXT, content="x", old_line_no=1, new_line_no=1),
                DiffLine(type=DiffLineType.DELETION, content="y", old_line_no=2),
                DiffLine(type=DiffLineType.ADDITION, content="z", new_line_no=2),
                DiffLine(type=DiffLineType.ADDITION, content="w", new_line_no=3),
            ],
        )
        file_diff = FileDiff(old_path="test.py", new_path="test.py", hunks=[hunk])

        assert file_diff.total_additions == 2
        assert file_diff.total_deletions == 1


# ============================================================================
# DiffSyntaxEvaluator Tests
# ============================================================================


class TestDiffSyntaxEvaluator:
    """Tests for DiffSyntaxEvaluator."""

    def test_evaluate_valid_diff(self):
        """Test evaluation of a valid diff passes."""
        evaluator = DiffSyntaxEvaluator()
        assertion = Assertion(
            type=AssertionType.DIFF_SYNTAX,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should be valid",
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True
        assert "valid" in result.message.lower()

    def test_evaluate_no_diff(self):
        """Test evaluation fails when no diff is provided."""
        evaluator = DiffSyntaxEvaluator()
        assertion = Assertion(
            type=AssertionType.DIFF_SYNTAX,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should be valid",
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix (but no actual diff)",
            generated_diff=None,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False
        assert "no git diff" in result.message.lower()

    def test_evaluate_extracts_diff_from_response(self):
        """Test that evaluator can extract diff from full response."""
        evaluator = DiffSyntaxEvaluator()
        assertion = Assertion(
            type=AssertionType.DIFF_SYNTAX,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should be valid",
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response=f"Here's the fix:\n```diff\n{SIMPLE_DIFF}```",
            generated_diff=None,  # Not set explicitly
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True

    def test_evaluate_wrong_assertion_type(self):
        """Test that wrong assertion type raises error."""
        evaluator = DiffSyntaxEvaluator()
        assertion = Assertion(
            type=AssertionType.MUST_CONTAIN,  # Wrong type
            target=AssertionTarget.GENERATED_DIFF,
            description="Wrong type",
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        with pytest.raises(ValueError, match="Invalid assertion type"):
            evaluator.evaluate(assertion, response)


# ============================================================================
# DiffAppliesEvaluator Tests
# ============================================================================


class TestDiffAppliesEvaluator:
    """Tests for DiffAppliesEvaluator."""

    def test_evaluate_applies_cleanly(self):
        """Test evaluation passes when diff applies cleanly."""
        evaluator = DiffAppliesEvaluator()
        assertion = Assertion(
            type=AssertionType.DIFF_APPLIES,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should apply",
            metadata={
                "file_contents": {
                    "hello.py": 'def hello():\n    print("Hello")\n',
                }
            },
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is True

    def test_evaluate_missing_file_contents(self):
        """Test evaluation fails without file contents."""
        evaluator = DiffAppliesEvaluator()
        assertion = Assertion(
            type=AssertionType.DIFF_APPLIES,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should apply",
            metadata={},  # No file_contents
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False
        assert "file contents" in result.message.lower()

    def test_evaluate_context_mismatch(self):
        """Test evaluation fails when context doesn't match."""
        evaluator = DiffAppliesEvaluator()
        assertion = Assertion(
            type=AssertionType.DIFF_APPLIES,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should apply",
            metadata={
                "file_contents": {
                    "hello.py": 'def different():\n    print("Different")\n',  # Wrong content
                }
            },
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)
        assert result.passed is False

    def test_evaluate_wrong_assertion_type(self):
        """Test that wrong assertion type raises error."""
        evaluator = DiffAppliesEvaluator()
        assertion = Assertion(
            type=AssertionType.MUST_CONTAIN,  # Wrong type
            target=AssertionTarget.GENERATED_DIFF,
            description="Wrong type",
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        with pytest.raises(ValueError, match="Invalid assertion type"):
            evaluator.evaluate(assertion, response)


# ============================================================================
# DiffJudgeEvaluator Tests
# ============================================================================


class TestDiffJudgeEvaluator:
    """Tests for DiffJudgeEvaluator."""

    @patch("evaluator.diff_judge.JudgeCache")
    @patch("evaluator.diff_judge.Anthropic")
    def test_evaluate_calls_llm(self, mock_anthropic, mock_cache_class):
        """Test that evaluation calls the LLM."""
        # Setup mock
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"score": 0.85, "passed": true, "summary": "Good fix"}')]
        mock_client.messages.create.return_value = mock_message

        # Mock cache to return None (no cached result)
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        evaluator = DiffJudgeEvaluator(api_key="test-key")
        assertion = Assertion(
            type=AssertionType.DIFF_JUDGE,
            target=AssertionTarget.GENERATED_DIFF,
            description="Judge the diff quality",
            metadata={"threshold": 0.7},
        )
        response = AgentResponse(
            task="Fix the hello function",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)

        assert result.passed is True
        assert result.score == 0.85
        mock_client.messages.create.assert_called_once()

    @patch("evaluator.diff_judge.JudgeCache")
    @patch("evaluator.diff_judge.Anthropic")
    def test_evaluate_below_threshold(self, mock_anthropic, mock_cache_class):
        """Test evaluation fails when score is below threshold."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"score": 0.5, "passed": false, "summary": "Needs work"}')]
        mock_client.messages.create.return_value = mock_message

        # Mock cache to return None (no cached result)
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        evaluator = DiffJudgeEvaluator(api_key="test-key")
        assertion = Assertion(
            type=AssertionType.DIFF_JUDGE,
            target=AssertionTarget.GENERATED_DIFF,
            description="Judge the diff quality",
            metadata={"threshold": 0.7},
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)

        assert result.passed is False
        assert result.score == 0.5
        assert "below" in result.message.lower()

    def test_evaluate_no_diff(self):
        """Test evaluation fails when no diff is provided."""
        with patch("evaluator.diff_judge.Anthropic"):
            evaluator = DiffJudgeEvaluator(api_key="test-key")
            assertion = Assertion(
                type=AssertionType.DIFF_JUDGE,
                target=AssertionTarget.GENERATED_DIFF,
                description="Judge the diff",
            )
            response = AgentResponse(
                task="Fix the bug",
                full_response="No diff here",
                generated_diff=None,
                model="claude-3-5-sonnet",
                instruction_file_path="CLAUDE.md",
            )

            result = evaluator.evaluate(assertion, response)

            assert result.passed is False
            assert "no git diff" in result.message.lower()

    def test_evaluate_invalid_diff_syntax(self):
        """Test evaluation fails for syntactically invalid diff."""
        with patch("evaluator.diff_judge.Anthropic"):
            evaluator = DiffJudgeEvaluator(api_key="test-key")
            assertion = Assertion(
                type=AssertionType.DIFF_JUDGE,
                target=AssertionTarget.GENERATED_DIFF,
                description="Judge the diff",
            )
            response = AgentResponse(
                task="Fix the bug",
                full_response="Here's the fix",
                generated_diff="not a valid diff format",
                model="claude-3-5-sonnet",
                instruction_file_path="CLAUDE.md",
            )

            result = evaluator.evaluate(assertion, response)

            assert result.passed is False

    def test_evaluate_wrong_assertion_type(self):
        """Test that wrong assertion type raises error."""
        with patch("evaluator.diff_judge.Anthropic"):
            evaluator = DiffJudgeEvaluator(api_key="test-key")
            assertion = Assertion(
                type=AssertionType.MUST_CONTAIN,  # Wrong type
                target=AssertionTarget.GENERATED_DIFF,
                description="Wrong type",
            )
            response = AgentResponse(
                task="Test",
                full_response="Test",
                model="claude-3-5-sonnet",
                instruction_file_path="CLAUDE.md",
            )

            with pytest.raises(ValueError, match="Invalid assertion type"):
                evaluator.evaluate(assertion, response)

    @patch("evaluator.diff_judge.JudgeCache")
    @patch("evaluator.diff_judge.Anthropic")
    def test_evaluate_with_custom_prompt(self, mock_anthropic, mock_cache_class):
        """Test evaluation with custom judge prompt."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"score": 0.9, "passed": true}')]
        mock_client.messages.create.return_value = mock_message

        # Mock cache to return None (no cached result)
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        evaluator = DiffJudgeEvaluator(api_key="test-key")
        custom_prompt = "Is this diff adding proper error handling? {task} {diff}"
        assertion = Assertion(
            type=AssertionType.DIFF_JUDGE,
            target=AssertionTarget.GENERATED_DIFF,
            description="Check error handling",
            metadata={
                "judge_prompt": custom_prompt,
                "threshold": 0.8,
            },
        )
        response = AgentResponse(
            task="Add error handling",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)

        assert result.passed is True
        # Verify the custom prompt was used
        call_args = mock_client.messages.create.call_args
        assert "error handling" in call_args.kwargs["messages"][0]["content"].lower()

    @patch("evaluator.diff_judge.JudgeCache")
    @patch("evaluator.diff_judge.Anthropic")
    def test_evaluate_handles_percentage_scores(self, mock_anthropic, mock_cache_class):
        """Test that scores over 1 are normalized from percentages."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"score": 85, "passed": true}')]  # Score as percentage
        mock_client.messages.create.return_value = mock_message

        # Mock cache to return None (no cached result)
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        evaluator = DiffJudgeEvaluator(api_key="test-key")
        assertion = Assertion(
            type=AssertionType.DIFF_JUDGE,
            target=AssertionTarget.GENERATED_DIFF,
            description="Judge the diff - percentage test",
            metadata={"threshold": 0.7},
        )
        response = AgentResponse(
            task="Fix the bug - percentage test",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)

        assert result.score == 0.85  # Normalized from 85
        assert result.passed is True

    @patch("evaluator.diff_judge.JudgeCache")
    @patch("evaluator.diff_judge.Anthropic")
    def test_evaluate_includes_diff_stats(self, mock_anthropic, mock_cache_class):
        """Test that evaluation includes diff statistics."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"score": 0.8, "passed": true}')]
        mock_client.messages.create.return_value = mock_message

        # Mock cache to return None (no cached result)
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache_class.return_value = mock_cache

        evaluator = DiffJudgeEvaluator(api_key="test-key")
        assertion = Assertion(
            type=AssertionType.DIFF_JUDGE,
            target=AssertionTarget.GENERATED_DIFF,
            description="Judge the diff",
        )
        response = AgentResponse(
            task="Fix the bug",
            full_response="Here's the fix",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = evaluator.evaluate(assertion, response)

        assert "diff_stats" in result.evidence
        assert result.evidence["diff_stats"]["files_changed"] == 1
        assert result.evidence["diff_stats"]["additions"] == 2
        assert result.evidence["diff_stats"]["deletions"] == 1


# ============================================================================
# Integration Tests
# ============================================================================


class TestDiffAssertionRegistryIntegration:
    """Test that diff assertions work through AssertionRegistry."""

    def test_registry_evaluates_diff_syntax(self):
        """Test registry can evaluate diff_syntax assertions."""
        from evaluator.assertions import AssertionRegistry

        assertion = Assertion(
            type=AssertionType.DIFF_SYNTAX,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should be valid",
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = AssertionRegistry.evaluate(assertion, response)
        assert result.passed is True

    def test_registry_evaluates_diff_applies(self):
        """Test registry can evaluate diff_applies assertions."""
        from evaluator.assertions import AssertionRegistry

        assertion = Assertion(
            type=AssertionType.DIFF_APPLIES,
            target=AssertionTarget.GENERATED_DIFF,
            description="Diff should apply",
            metadata={
                "file_contents": {
                    "hello.py": 'def hello():\n    print("Hello")\n',
                }
            },
        )
        response = AgentResponse(
            task="Test",
            full_response="Test",
            generated_diff=SIMPLE_DIFF,
            model="claude-3-5-sonnet",
            instruction_file_path="CLAUDE.md",
        )

        result = AssertionRegistry.evaluate(assertion, response)
        assert result.passed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
