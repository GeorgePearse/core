"""LLM-as-judge evaluator specifically for git diffs."""

import json
from typing import Any, Optional

from anthropic import Anthropic

from evaluator.cache import JudgeCache
from evaluator.diff_models import GitDiff
from evaluator.diff_parser import DiffParser, DiffValidator
from evaluator.models import AgentResponse, Assertion, AssertionResult, AssertionType


class DiffJudgeEvaluator:
    """Evaluates git diffs using an LLM as a judge.

    This evaluator is specifically designed to assess the quality of code changes
    represented as git diffs. It can evaluate:
    - Correctness: Does the diff solve the stated problem?
    - Completeness: Does it address all requirements?
    - Code quality: Is the changed code well-written?
    - Minimal changes: Does it make only necessary modifications?
    - Safety: Does it introduce any security issues or bugs?
    """

    DEFAULT_JUDGE_PROMPT = """You are an expert code reviewer evaluating a git diff.

Analyze the following diff and evaluate it on these criteria:
1. **Correctness**: Does the diff correctly solve the stated problem?
2. **Completeness**: Does it address all requirements of the task?
3. **Code Quality**: Is the code well-written, readable, and maintainable?
4. **Minimal Changes**: Does it make only necessary modifications?
5. **No Regressions**: Does it avoid introducing bugs or breaking existing functionality?

Task/Problem Statement:
{task}

Git Diff to evaluate:
```diff
{diff}
```

Provide your evaluation as JSON with this exact structure:
{{
    "score": <float 0-1>,
    "passed": <boolean>,
    "correctness": {{
        "score": <float 0-1>,
        "reasoning": "<explanation>"
    }},
    "completeness": {{
        "score": <float 0-1>,
        "reasoning": "<explanation>"
    }},
    "code_quality": {{
        "score": <float 0-1>,
        "reasoning": "<explanation>"
    }},
    "minimal_changes": {{
        "score": <float 0-1>,
        "reasoning": "<explanation>"
    }},
    "no_regressions": {{
        "score": <float 0-1>,
        "reasoning": "<explanation>"
    }},
    "summary": "<brief overall assessment>",
    "suggestions": ["<improvement suggestion 1>", "<improvement suggestion 2>"]
}}
"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        judge_model: str = "claude-sonnet-4-20250514",
        cache: Optional[JudgeCache] = None,
        cache_ttl_hours: int = 24,
    ) -> None:
        """Initialize the diff judge evaluator.

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            judge_model: Model to use for judging
            cache: Optional cache for judge results
            cache_ttl_hours: Cache TTL in hours
        """
        self.client = Anthropic(api_key=api_key)
        self.judge_model = judge_model
        self.cache = cache or JudgeCache()
        self.cache_ttl_hours = cache_ttl_hours
        self.parser = DiffParser()
        self.validator = DiffValidator()

    def evaluate(
        self,
        assertion: Assertion,
        response: AgentResponse,
    ) -> AssertionResult:
        """Evaluate a diff assertion using LLM judge.

        Args:
            assertion: The diff_judge assertion
            response: The agent response containing the diff

        Returns:
            AssertionResult with the evaluation
        """
        if assertion.type != AssertionType.DIFF_JUDGE:
            msg = f"Invalid assertion type for DiffJudge: {assertion.type}"
            raise ValueError(msg)

        # Extract diff from response
        diff_text = self._get_diff_content(response)
        if not diff_text:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No git diff found in response",
                evidence={"error": "diff_not_found"},
            )

        # Parse the diff
        parsed_diff = self.parser.parse(diff_text)

        # Validate syntax first
        validation = self.validator.validate_syntax(parsed_diff)
        if not validation.is_valid:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Diff syntax validation failed: {'; '.join(validation.errors)}",
                evidence={
                    "validation_errors": validation.errors,
                    "validation_warnings": validation.warnings,
                },
            )

        # Get judge prompt (use custom or default)
        judge_prompt = assertion.metadata.get("judge_prompt", self.DEFAULT_JUDGE_PROMPT)

        # Format prompt with task and diff
        formatted_prompt = judge_prompt.format(
            task=response.task,
            diff=diff_text,
        )

        # Check cache
        cache_key = f"diff:{response.model}:{diff_text}:{formatted_prompt}"
        cached_result = self.cache.get(
            model_under_test=response.model,
            agent_response=diff_text,
            judge_prompt=formatted_prompt,
            judge_model=self.judge_model,
        )

        if cached_result:
            return self._process_judge_result(assertion, cached_result, parsed_diff)

        # Call the judge
        try:
            judge_result = self._call_judge(formatted_prompt, diff_text, response.task)
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Judge LLM call failed: {str(e)}",
                evidence={"error": str(e)},
            )

        # Cache result
        self.cache.set(
            model_under_test=response.model,
            agent_response=diff_text,
            judge_prompt=formatted_prompt,
            judge_model=self.judge_model,
            result=judge_result,
            ttl_hours=self.cache_ttl_hours,
        )

        return self._process_judge_result(assertion, judge_result, parsed_diff)

    def _get_diff_content(self, response: AgentResponse) -> Optional[str]:
        """Extract diff content from agent response.

        Args:
            response: The agent response

        Returns:
            Raw diff text or None if not found
        """
        # First check if diff is explicitly set
        if response.generated_diff:
            return response.generated_diff

        # Try to extract from full response
        parsed = self.parser.parse_from_response(response.full_response)
        if parsed and parsed.files:
            return parsed.raw_diff

        return None

    def _call_judge(
        self,
        prompt: str,
        diff: str,
        task: str,
    ) -> dict[str, Any]:
        """Call the LLM judge to evaluate a diff.

        Args:
            prompt: The formatted judge prompt
            diff: The diff text
            task: The original task

        Returns:
            Judge's evaluation as a dictionary
        """
        system_prompt = """You are an expert code reviewer and software engineer.
Your job is to evaluate git diffs and assess whether they correctly and completely solve the given task.
Be objective, thorough, and constructive in your evaluation.
Always respond with valid JSON matching the requested schema."""

        message = self.client.messages.create(
            model=self.judge_model,
            max_tokens=2048,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        # Parse JSON response
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            return {
                "raw_response": response_text,
                "error": "Could not parse JSON response",
                "score": 0,
                "passed": False,
            }

    def _process_judge_result(
        self,
        assertion: Assertion,
        judge_result: dict[str, Any],
        parsed_diff: GitDiff,
    ) -> AssertionResult:
        """Process judge result into AssertionResult.

        Args:
            assertion: The assertion
            judge_result: Result from judge LLM
            parsed_diff: The parsed diff

        Returns:
            AssertionResult
        """
        # Extract overall score
        score = judge_result.get("score")
        if isinstance(score, str):
            try:
                score = float(score)
            except ValueError:
                score = None

        # Normalize score to 0-1
        if score is not None and score > 1:
            score = score / 100

        # Check threshold
        threshold = assertion.metadata.get("threshold", 0.7)
        passed = False

        if score is not None:
            passed = score >= threshold

        # Also check explicit passed field
        if "passed" in judge_result:
            passed = bool(judge_result["passed"])

        # Build message
        if score is not None:
            message = (
                f"Diff evaluation score {score:.2f} {'meets' if passed else 'below'} "
                f"threshold {threshold}"
            )
        else:
            message = judge_result.get("summary", "Diff evaluation completed")

        # Build evidence with diff statistics
        evidence = {
            **judge_result,
            "diff_stats": {
                "files_changed": parsed_diff.total_files_changed,
                "additions": parsed_diff.total_additions,
                "deletions": parsed_diff.total_deletions,
                "files_added": len(parsed_diff.files_added),
                "files_deleted": len(parsed_diff.files_deleted),
            },
        }

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=message,
            score=score,
            evidence=evidence,
        )


class DiffSyntaxEvaluator:
    """Evaluates that a diff is syntactically valid."""

    def __init__(self) -> None:
        """Initialize the evaluator."""
        self.parser = DiffParser()
        self.validator = DiffValidator()

    def evaluate(
        self,
        assertion: Assertion,
        response: AgentResponse,
    ) -> AssertionResult:
        """Evaluate that the diff is syntactically correct.

        Args:
            assertion: The diff_syntax assertion
            response: The agent response containing the diff

        Returns:
            AssertionResult
        """
        if assertion.type != AssertionType.DIFF_SYNTAX:
            msg = f"Invalid assertion type: {assertion.type}"
            raise ValueError(msg)

        # Extract diff
        diff_text = response.generated_diff
        if not diff_text:
            # Try to extract from response
            parsed = self.parser.parse_from_response(response.full_response)
            if parsed:
                diff_text = parsed.raw_diff

        if not diff_text:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No git diff found in response",
            )

        # Parse and validate
        parsed_diff = self.parser.parse(diff_text)
        validation = self.validator.validate_syntax(parsed_diff)

        if validation.is_valid:
            return AssertionResult(
                assertion=assertion,
                passed=True,
                message=f"Diff is syntactically valid ({parsed_diff.total_files_changed} files)",
                evidence={
                    "files_changed": parsed_diff.total_files_changed,
                    "warnings": validation.warnings,
                },
            )
        else:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Diff syntax errors: {'; '.join(validation.errors)}",
                evidence={
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                },
            )


class DiffAppliesEvaluator:
    """Evaluates that a diff can be cleanly applied to source files."""

    def __init__(self) -> None:
        """Initialize the evaluator."""
        self.parser = DiffParser()
        self.validator = DiffValidator()

    def evaluate(
        self,
        assertion: Assertion,
        response: AgentResponse,
        file_contents: Optional[dict[str, str]] = None,
    ) -> AssertionResult:
        """Evaluate that the diff can be applied.

        Args:
            assertion: The diff_applies assertion
            response: The agent response containing the diff
            file_contents: Dictionary of file path -> content for validation
                          (if None, uses metadata from assertion)

        Returns:
            AssertionResult
        """
        if assertion.type != AssertionType.DIFF_APPLIES:
            msg = f"Invalid assertion type: {assertion.type}"
            raise ValueError(msg)

        # Get file contents from assertion metadata if not provided
        if file_contents is None:
            file_contents = assertion.metadata.get("file_contents", {})

        if not file_contents:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No file contents provided for diff application check",
                evidence={"error": "missing_file_contents"},
            )

        # Extract diff
        diff_text = response.generated_diff
        if not diff_text:
            parsed = self.parser.parse_from_response(response.full_response)
            if parsed:
                diff_text = parsed.raw_diff

        if not diff_text:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No git diff found in response",
            )

        # Parse and validate applicability
        parsed_diff = self.parser.parse(diff_text)
        validation = self.validator.validate_can_apply(parsed_diff, file_contents)

        if validation.is_valid:
            return AssertionResult(
                assertion=assertion,
                passed=True,
                message=f"Diff can be cleanly applied to {len(file_contents)} file(s)",
                evidence={
                    "files_checked": list(file_contents.keys()),
                    "warnings": validation.warnings,
                },
            )
        else:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Diff cannot be applied: {'; '.join(validation.errors)}",
                evidence={
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                },
            )
