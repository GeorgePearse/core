"""Assertion implementations for validating agent responses."""

import json
import re
from abc import ABC, abstractmethod

from evaluator.models import (
    AgentResponse,
    Assertion,
    AssertionResult,
    AssertionType,
)


class AssertionEvaluator(ABC):
    """Base class for assertion evaluators."""

    @abstractmethod
    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Evaluate an assertion against a response.

        Args:
            assertion: The assertion to evaluate
            response: The agent response to check

        Returns:
            AssertionResult with pass/fail and details
        """
        pass

    def _get_check_content(self, assertion: Assertion, response: AgentResponse) -> str:
        """Get the content to check based on assertion target.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            Content to validate
        """
        match assertion.target.value:
            case "generated_commands":
                return "\n".join(response.generated_commands)
            case "generated_code":
                return "\n".join(response.generated_code)
            case "tool_calls":
                return json.dumps(response.tool_calls)
            case _:
                return response.full_response


class MustContainEvaluator(AssertionEvaluator):
    """Evaluates must_contain assertions."""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check if content contains required text.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        if not assertion.pattern:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No pattern specified for must_contain assertion",
            )

        content = self._get_check_content(assertion, response)
        passed = assertion.pattern in content

        message = (
            f"✓ Found required text: {assertion.pattern}"
            if passed
            else f"✗ Required text not found: {assertion.pattern}"
        )

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=message,
            evidence={"pattern": assertion.pattern, "found": passed},
        )


class MustNotContainEvaluator(AssertionEvaluator):
    """Evaluates must_not_contain assertions."""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check if content does not contain forbidden text.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        if not assertion.pattern:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No pattern specified for must_not_contain assertion",
            )

        content = self._get_check_content(assertion, response)
        passed = assertion.pattern not in content

        message = (
            f"✓ Forbidden text not found: {assertion.pattern}"
            if passed
            else f"✗ Forbidden text found: {assertion.pattern}"
        )

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=message,
            evidence={"pattern": assertion.pattern, "found": not passed},
        )


class RegexMatchEvaluator(AssertionEvaluator):
    """Evaluates regex_match assertions."""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check if content matches regex pattern.

        Args:
            assertion: The assertion (pattern field contains regex)
            response: The agent response

        Returns:
            AssertionResult
        """
        if not assertion.pattern:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No pattern specified for regex_match assertion",
            )

        content = self._get_check_content(assertion, response)

        try:
            match = re.search(assertion.pattern, content, re.MULTILINE | re.DOTALL)
            passed = match is not None

            message = (
                f"✓ Regex matched: {assertion.pattern}"
                if passed
                else f"✗ Regex did not match: {assertion.pattern}"
            )

            return AssertionResult(
                assertion=assertion,
                passed=passed,
                message=message,
                evidence={"pattern": assertion.pattern, "matched": passed},
            )
        except re.error as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Invalid regex pattern: {e}",
            )


class JSONSchemaEvaluator(AssertionEvaluator):
    """Evaluates json_schema assertions."""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Validate JSON content against schema.

        Args:
            assertion: The assertion (metadata['schema'] contains JSON schema)
            response: The agent response

        Returns:
            AssertionResult
        """
        content = self._get_check_content(assertion, response)

        try:
            json_obj = json.loads(content)
        except json.JSONDecodeError as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Failed to parse JSON: {e}",
                evidence={"content_sample": content[:100]},
            )

        schema = assertion.metadata.get("schema")
        if not schema:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No schema provided in metadata",
            )

        try:
            from jsonschema import ValidationError, validate

            validate(instance=json_obj, schema=schema)
            return AssertionResult(
                assertion=assertion,
                passed=True,
                message="✓ JSON schema validation passed",
                evidence={"schema_valid": True},
            )
        except ValidationError as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Schema validation failed: {e.message}",
                evidence={"error": e.message},
            )
        except ImportError:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="jsonschema library not installed",
            )


class CodeContainsEvaluator(AssertionEvaluator):
    """Evaluates code_contains assertions (required code patterns)."""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check if required code patterns are present.

        Args:
            assertion: The assertion with snippet in metadata
            response: The agent response

        Returns:
            AssertionResult
        """
        snippet = assertion.metadata.get("snippet")
        if not snippet:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No snippet specified in assertion metadata",
            )

        match_type = assertion.metadata.get("match_type", "exact")
        language = assertion.metadata.get("language", "python")

        target_content = self._get_check_content(assertion, response)

        try:
            from evaluator.code_matching import get_matcher

            matcher = get_matcher(language)
            result = matcher.compare(snippet, target_content, match_type)

            return AssertionResult(
                assertion=assertion,
                passed=result.matched,
                message=f"Code pattern: {result.message}",
                score=result.score,
                evidence=result.details or {"match_type": match_type},
            )
        except ValueError as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Code matching error: {e}",
                evidence={"error": str(e)},
            )


class CodeExcludesEvaluator(AssertionEvaluator):
    """Evaluates code_excludes assertions (forbidden code patterns)."""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check that forbidden code patterns are not present.

        Args:
            assertion: The assertion with patterns in metadata
            response: The agent response

        Returns:
            AssertionResult
        """
        patterns = assertion.metadata.get("patterns", [])
        if not patterns:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No patterns specified in assertion metadata",
            )

        # Handle both single pattern (string) and multiple patterns (list)
        if isinstance(patterns, str):
            patterns = [patterns]

        match_type = assertion.metadata.get("match_type", "regex")
        target_content = self._get_check_content(assertion, response)

        try:
            from evaluator.code_matching import get_matcher

            matcher = get_matcher("python")

            # Check each forbidden pattern
            found_patterns = []
            for pattern in patterns:
                result = matcher.compare(pattern, target_content, match_type)
                if result.matched:
                    found_patterns.append(pattern)

            if found_patterns:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message=f"Forbidden patterns found: {', '.join(found_patterns)}",
                    evidence={"forbidden_patterns": found_patterns},
                )

            return AssertionResult(
                assertion=assertion,
                passed=True,
                message=f"✓ No forbidden patterns found ({len(patterns)} patterns checked)",
                evidence={"patterns_checked": len(patterns)},
            )
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Pattern checking error: {e}",
                evidence={"error": str(e)},
            )


class AssertionRegistry:
    """Registry for assertion evaluators."""

    _evaluators: dict[AssertionType, type[AssertionEvaluator]] = {
        AssertionType.MUST_CONTAIN: MustContainEvaluator,
        AssertionType.MUST_NOT_CONTAIN: MustNotContainEvaluator,
        AssertionType.REGEX_MATCH: RegexMatchEvaluator,
        AssertionType.JSON_SCHEMA: JSONSchemaEvaluator,
        AssertionType.CODE_CONTAINS: CodeContainsEvaluator,
        AssertionType.CODE_EXCLUDES: CodeExcludesEvaluator,
    }

    @classmethod
    def evaluate(cls, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Evaluate assertion using registered evaluator.

        Args:
            assertion: The assertion to evaluate
            response: The agent response

        Returns:
            AssertionResult

        Raises:
            ValueError: If assertion type is not registered
        """
        # Special handling for LLM judge (lazy import to avoid circular dependency)
        if assertion.type == AssertionType.LLM_JUDGE:
            from evaluator.llm_judge import LLMJudgeEvaluator

            evaluator = LLMJudgeEvaluator()
            return evaluator.evaluate(assertion, response)

        # Special handling for code analysis
        if assertion.type == AssertionType.CODE_ANALYSIS:
            from evaluator.code_analysis import CodeAnalysisRegistry

            validator_name = assertion.metadata.get("validator", "python_type_check")
            return CodeAnalysisRegistry.analyze(validator_name, assertion, response)

        # Special handling for snapshots (lazy import)
        if assertion.type == AssertionType.SNAPSHOT:
            from evaluator.snapshots import SnapshotEvaluator

            evaluator = SnapshotEvaluator()
            return evaluator.evaluate(assertion, response)

        # Special handling for diff-based assertions (lazy import)
        if assertion.type == AssertionType.DIFF_JUDGE:
            from evaluator.diff_judge import DiffJudgeEvaluator

            evaluator = DiffJudgeEvaluator()
            return evaluator.evaluate(assertion, response)

        if assertion.type == AssertionType.DIFF_SYNTAX:
            from evaluator.diff_judge import DiffSyntaxEvaluator

            evaluator = DiffSyntaxEvaluator()
            return evaluator.evaluate(assertion, response)

        if assertion.type == AssertionType.DIFF_APPLIES:
            from evaluator.diff_judge import DiffAppliesEvaluator

            evaluator = DiffAppliesEvaluator()
            return evaluator.evaluate(assertion, response)

        evaluator_class = cls._evaluators.get(assertion.type)
        if not evaluator_class:
            msg = f"Unknown assertion type: {assertion.type}"
            raise ValueError(msg)

        evaluator = evaluator_class()
        return evaluator.evaluate(assertion, response)

    @classmethod
    def register(
        cls, assertion_type: AssertionType, evaluator_class: type[AssertionEvaluator]
    ) -> None:
        """Register a custom evaluator.

        Args:
            assertion_type: The assertion type
            evaluator_class: The evaluator class
        """
        cls._evaluators[assertion_type] = evaluator_class
