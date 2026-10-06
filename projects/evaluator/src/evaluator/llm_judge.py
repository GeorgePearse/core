"""LLM-as-judge assertion evaluator."""

import json
from typing import Any, Optional

from anthropic import Anthropic

from evaluator.cache import JudgeCache
from evaluator.models import AgentResponse, Assertion, AssertionResult, AssertionType


class LLMJudgeEvaluator:
    """Evaluates assertions using another LLM as a judge."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        judge_model: str = "claude-3-5-sonnet-20250109",
        cache: Optional[JudgeCache] = None,
        cache_ttl_hours: int = 24,
    ) -> None:
        """Initialize LLM judge.

        Args:
            api_key: Anthropic API key
            judge_model: Model to use for judging (should be most capable available)
            cache: Cache instance (created if None)
            cache_ttl_hours: Cache time-to-live in hours
        """
        self.client = Anthropic(api_key=api_key)
        self.judge_model = judge_model
        self.cache = cache or JudgeCache()
        self.cache_ttl_hours = cache_ttl_hours

    def evaluate(
        self,
        assertion: Assertion,
        response: AgentResponse,
    ) -> AssertionResult:
        """Evaluate assertion using LLM judge.

        Args:
            assertion: The LLM judge assertion
            response: The agent response

        Returns:
            AssertionResult with LLM judgment
        """
        if assertion.type != AssertionType.LLM_JUDGE:
            msg = f"Invalid assertion type for LLM judge: {assertion.type}"
            raise ValueError(msg)

        # Get content to judge
        content = self._get_check_content(assertion, response)

        # Check cache first
        judge_prompt = assertion.metadata.get(
            "judge_prompt",
            f"Evaluate this response: {content}",
        )

        cached_result = self.cache.get(
            model_under_test=response.model,
            agent_response=content,
            judge_prompt=judge_prompt,
            judge_model=self.judge_model,
        )

        if cached_result:
            return self._process_judge_result(assertion, cached_result)

        # Call LLM judge
        try:
            judge_result = self._call_judge(
                judge_prompt=judge_prompt,
                response=content,
                schema=assertion.metadata.get("response_schema"),
            )
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Judge LLM call failed: {str(e)}",
            )

        # Cache result
        self.cache.set(
            model_under_test=response.model,
            agent_response=content,
            judge_prompt=judge_prompt,
            judge_model=self.judge_model,
            result=judge_result,
            ttl_hours=self.cache_ttl_hours,
        )

        return self._process_judge_result(assertion, judge_result)

    def _call_judge(
        self,
        judge_prompt: str,
        response: str,
        schema: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Call LLM judge to evaluate response.

        Args:
            judge_prompt: Prompt for the judge
            response: Response to evaluate
            schema: Optional response schema (for structured outputs)

        Returns:
            Judge's response as dict
        """
        system_prompt = """You are an expert evaluator assessing AI agent responses.
Respond ONLY with valid JSON containing your evaluation.
Be objective and provide clear reasoning."""

        user_message = f"""Please evaluate the following AI response:

---RESPONSE START---
{response}
---RESPONSE END---

{judge_prompt}

Provide your evaluation as JSON."""

        message = self.client.messages.create(
            model=self.judge_model,
            max_tokens=1024,
            temperature=0,  # Deterministic
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        response_text = message.content[0].text

        # Try to extract JSON from response
        try:
            # First try direct JSON parsing
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON in response
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            # If all else fails, return a structured format
            return {"raw_response": response_text, "error": "Could not parse JSON"}

    def _process_judge_result(
        self,
        assertion: Assertion,
        judge_result: dict[str, Any],
    ) -> AssertionResult:
        """Process judge result into AssertionResult.

        Args:
            assertion: The assertion
            judge_result: Result from judge LLM

        Returns:
            AssertionResult
        """
        # Extract score if available
        score = judge_result.get("score")
        if isinstance(score, str):
            try:
                score = float(score)
            except ValueError:
                score = None

        # Normalize score to 0-1 if needed
        if score is not None:
            if score > 1:
                score = score / 100

        # Check threshold
        threshold = assertion.metadata.get("threshold", 0.7)
        passed = False
        message = "Judge evaluation completed"

        if score is not None:
            passed = score >= threshold
            message = (
                f"✓ Judge score {score:.2f} meets threshold {threshold}"
                if passed
                else f"✗ Judge score {score:.2f} below threshold {threshold}"
            )

        # Also check for explicit pass/fail
        if "passed" in judge_result:
            passed = bool(judge_result["passed"])

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=message or judge_result.get("reasoning", "No reasoning provided"),
            score=score,
            evidence=judge_result,
        )

    @staticmethod
    def _get_check_content(assertion: Assertion, response: AgentResponse) -> str:
        """Get content to check based on assertion target.

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
