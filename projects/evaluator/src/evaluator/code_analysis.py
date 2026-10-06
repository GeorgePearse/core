"""Static code analysis validators."""

import ast
import re
from abc import ABC, abstractmethod

from evaluator.models import AgentResponse, Assertion, AssertionResult


class CodeAnalyzer(ABC):
    """Base class for code analysis validators."""

    @abstractmethod
    def analyze(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Analyze code in response.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        pass

    def _get_code_blocks(self, response: AgentResponse) -> list[str]:
        """Get all code blocks from response.

        Args:
            response: The agent response

        Returns:
            List of code blocks
        """
        return response.generated_code


class PythonTypeCheckAnalyzer(CodeAnalyzer):
    """Checks if generated Python code has type hints."""

    def analyze(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check for type hints in code.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        code_blocks = self._get_code_blocks(response)
        if not code_blocks:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No Python code found in response",
            )

        issues = []
        for code in code_blocks:
            issues.extend(self._check_types(code))

        if issues:
            message = f"Found {len(issues)} type hint issues:\n" + "\n".join(
                f"- {issue}" for issue in issues[:5]
            )
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=message,
                evidence={"issues": issues},
            )

        return AssertionResult(
            assertion=assertion,
            passed=True,
            message="✓ Code has proper type hints",
        )

    @staticmethod
    def _check_types(code: str) -> list[str]:
        """Check for missing type hints in functions.

        Args:
            code: Python code to check

        Returns:
            List of issues found
        """
        issues = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check return type
                if node.returns is None and node.name != "__init__":
                    issues.append(f"Function '{node.name}' missing return type hint")

                # Check parameter types
                for arg in node.args.args:
                    if arg.annotation is None:
                        issues.append(f"Parameter '{arg.arg}' in '{node.name}' missing type hint")

        return issues


class DocstringAnalyzer(CodeAnalyzer):
    """Checks if code has docstrings."""

    def analyze(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check for docstrings.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        code_blocks = self._get_code_blocks(response)
        if not code_blocks:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No code found in response",
            )

        missing_docs = []
        for code in code_blocks:
            missing_docs.extend(self._check_docstrings(code))

        if missing_docs:
            message = f"Found {len(missing_docs)} missing docstrings:\n" + "\n".join(
                f"- {doc}" for doc in missing_docs[:5]
            )
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=message,
                evidence={"missing": missing_docs},
            )

        return AssertionResult(
            assertion=assertion,
            passed=True,
            message="✓ Code has proper docstrings",
        )

    @staticmethod
    def _check_docstrings(code: str) -> list[str]:
        """Check for missing docstrings.

        Args:
            code: Python code to check

        Returns:
            List of missing docstrings
        """
        missing = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                docstring = ast.get_docstring(node)
                if not docstring:
                    missing.append(f"{node.__class__.__name__} '{node.name}' missing docstring")

        return missing


class NoBashFindAnalyzer(CodeAnalyzer):
    """Checks that code doesn't use 'find' command."""

    def analyze(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check for bash find command usage.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        full_response = response.full_response
        commands = response.generated_commands

        # Check full response for find
        if re.search(r"\bfind\s", full_response, re.IGNORECASE):
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="✗ Found use of 'find' command (should use 'fd' instead)",
            )

        # Check generated commands
        for cmd in commands:
            if re.search(r"\bfind\s", cmd, re.IGNORECASE):
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message=f"✗ Found use of 'find' command: {cmd}",
                )

        return AssertionResult(
            assertion=assertion,
            passed=True,
            message="✓ No use of 'find' command (correctly uses alternatives)",
        )


class NoSysPathModifyAnalyzer(CodeAnalyzer):
    """Checks that code doesn't modify sys.path."""

    def analyze(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        """Check for sys.path modifications.

        Args:
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult
        """
        code_blocks = self._get_code_blocks(response)

        for code in code_blocks:
            if "sys.path" in code and ("append" in code or "insert" in code or "extend" in code):
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message="✗ Code modifies sys.path (should fix imports instead)",
                )

        return AssertionResult(
            assertion=assertion,
            passed=True,
            message="✓ Code does not modify sys.path",
        )


class CodeAnalysisRegistry:
    """Registry for code analysis validators."""

    _validators: dict[str, type[CodeAnalyzer]] = {
        "python_type_check": PythonTypeCheckAnalyzer,
        "docstring_check": DocstringAnalyzer,
        "no_bash_find": NoBashFindAnalyzer,
        "no_sys_path_modify": NoSysPathModifyAnalyzer,
    }

    @classmethod
    def analyze(
        cls,
        validator_name: str,
        assertion: Assertion,
        response: AgentResponse,
    ) -> AssertionResult:
        """Run code analysis using registered validator.

        Args:
            validator_name: Name of the validator
            assertion: The assertion
            response: The agent response

        Returns:
            AssertionResult

        Raises:
            ValueError: If validator not found
        """
        validator_class = cls._validators.get(validator_name)
        if not validator_class:
            msg = f"Unknown code analyzer: {validator_name}"
            raise ValueError(msg)

        validator = validator_class()
        return validator.analyze(assertion, response)

    @classmethod
    def register(cls, name: str, validator_class: type[CodeAnalyzer]) -> None:
        """Register custom code analyzer.

        Args:
            name: Name for the validator
            validator_class: The validator class
        """
        cls._validators[name] = validator_class
