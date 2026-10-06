"""Agent invocation and response capture."""

import json
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from evaluator.models import AgentResponse


class AgentInvoker:
    """Invokes Claude with specified instructions and captures responses."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize the agent invoker.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
        """
        self.client = Anthropic(api_key=api_key)

    def load_instructions(self, instruction_file_path: str) -> str:
        """Load instruction content from file.

        Args:
            instruction_file_path: Path to instruction file (CLAUDE.md, AGENTS.md, etc.)

        Returns:
            Content of the instruction file.
        """
        path = Path(instruction_file_path)
        if not path.exists():
            msg = f"Instruction file not found: {instruction_file_path}"
            raise FileNotFoundError(msg)
        return path.read_text(encoding="utf-8")

    def invoke(
        self,
        task: str,
        instruction_file_path: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20250109",
        max_tokens: int = 4096,
    ) -> AgentResponse:
        """Invoke Claude with task and instructions.

        Args:
            task: The task to perform
            instruction_file_path: Path to instruction file (optional)
            model: Claude model to use
            max_tokens: Maximum tokens in response

        Returns:
            AgentResponse with full response and extracted components
        """
        if instruction_file_path:
            instructions = self.load_instructions(instruction_file_path)
        else:
            instructions = ""

        conversation_trace: list[dict[str, str]] = []

        system_prompt = f"""You are an AI assistant helping with software engineering tasks.

Follow these instructions exactly:

{instructions}

Respond to the user's request while adhering to these guidelines."""

        conversation_trace.append({"role": "system", "content": system_prompt})

        conversation_trace.append({"role": "user", "content": task})

        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": task}],
        )

        full_response = response.content[0].text

        conversation_trace.append({"role": "assistant", "content": full_response})

        agent_response = AgentResponse(
            task=task,
            full_response=full_response,
            model=model,
            instruction_file_path=str(Path(instruction_file_path).absolute()) if instruction_file_path else "",
            conversation_trace=conversation_trace,
            tool_calls=self._extract_tool_calls(full_response),
            generated_code=self._extract_code_blocks(full_response),
            generated_commands=self._extract_commands(full_response),
        )

        return agent_response

    @staticmethod
    def _extract_tool_calls(response: str) -> list[dict[str, str]]:
        """Extract tool calls from response.

        Args:
            response: Full response text

        Returns:
            List of extracted tool calls.
        """
        tool_calls = []
        lines = response.split("\n")

        for line in lines:
            if "Bash" in line or "Edit" in line or "Read" in line or "Write" in line:
                try:
                    tool_calls.append({"raw": line.strip()})
                except (json.JSONDecodeError, ValueError):
                    pass

        return tool_calls

    @staticmethod
    def _extract_code_blocks(response: str) -> list[str]:
        """Extract code blocks from response.

        Args:
            response: Full response text

        Returns:
            List of extracted code blocks.
        """
        code_blocks = []
        current_block = ""
        in_code = False

        for line in response.split("\n"):
            if line.startswith("```"):
                if in_code:
                    if current_block:
                        code_blocks.append(current_block.strip())
                    current_block = ""
                    in_code = False
                else:
                    in_code = True
            elif in_code:
                current_block += line + "\n"

        if current_block:
            code_blocks.append(current_block.strip())

        return code_blocks

    @staticmethod
    def _extract_commands(response: str) -> list[str]:
        """Extract shell commands from response.

        Args:
            response: Full response text

        Returns:
            List of extracted commands.
        """
        commands = []
        in_command_block = False
        current_command = ""

        for line in response.split("\n"):
            if line.startswith("```bash") or line.startswith("```sh"):
                in_command_block = True
                current_command = ""
            elif line.startswith("```") and in_command_block:
                if current_command:
                    commands.append(current_command.strip())
                in_command_block = False
                current_command = ""
            elif in_command_block:
                if line.strip():
                    current_command += line + "\n"

        if current_command:
            commands.append(current_command.strip())

        return commands
