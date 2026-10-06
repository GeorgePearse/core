"""Gemini 3 Flash Agentic Vision client.

Uses the google-genai SDK with code execution enabled to perform
Think-Act-Observe loops: the model analyzes images, generates Python
code to manipulate/analyze them, then observes the results.
"""

import io
import os
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from PIL import Image


@dataclass
class CodeExecutionStep:
    """A single code execution step from the agentic vision loop."""

    code: str
    output: str


@dataclass
class AgenticVisionResult:
    """Structured result from a Gemini Agentic Vision call."""

    text_parts: list[str] = field(default_factory=list)
    code_execution_steps: list[CodeExecutionStep] = field(default_factory=list)
    raw_response_text: str = ""


class GeminiAgenticVisionClient:
    """Client for Gemini 3 Flash with code execution (agentic vision).

    The model uses a Think-Act-Observe loop: it analyzes images, generates
    Python code to manipulate/analyze them (crop, zoom, annotate, calculate),
    then observes the results.

    Args:
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        model: Model name. Defaults to gemini-3-flash.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-3-flash") -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def analyze_image(self, image_bytes: bytes, prompt: str) -> AgenticVisionResult:
        """Analyze an image using Gemini with code execution enabled.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.).
            prompt: The analysis prompt to send alongside the image.

        Returns:
            AgenticVisionResult with text parts, code execution steps, and raw response.
        """
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")

        config = types.GenerateContentConfig(
            tools=[types.Tool(code_execution=types.ToolCodeExecution())],
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt, image],
            config=config,
        )

        return self._parse_response(response)

    def _parse_response(self, response: types.GenerateContentResponse) -> AgenticVisionResult:
        """Parse a multi-part Gemini response into structured result.

        The response may contain interleaved text, executable_code, and
        code_execution_result parts from the Think-Act-Observe loop.
        """
        result = AgenticVisionResult()

        # Build raw response text for storage
        raw_parts: list[str] = []

        # Track pending code to pair with its output
        pending_code: str | None = None

        if not response.candidates:
            return result

        content = response.candidates[0].content
        if content is None or content.parts is None:
            return result

        for part in content.parts:
            if part.text:
                result.text_parts.append(part.text)
                raw_parts.append(part.text)
            elif part.executable_code:
                pending_code = part.executable_code.code or ""
                raw_parts.append(f"```python\n{pending_code}\n```")
            elif part.code_execution_result:
                output = part.code_execution_result.output or ""
                raw_parts.append(f"[Output]: {output}")
                result.code_execution_steps.append(
                    CodeExecutionStep(
                        code=pending_code or "",
                        output=output,
                    )
                )
                pending_code = None

        # If there was code without a result part, still record it
        if pending_code is not None:
            result.code_execution_steps.append(CodeExecutionStep(code=pending_code, output=""))

        result.raw_response_text = "\n\n".join(raw_parts)
        return result
