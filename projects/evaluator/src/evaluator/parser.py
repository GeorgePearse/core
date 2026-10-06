"""Parser for YAML test case files."""

from pathlib import Path
from typing import Any

import yaml

from evaluator.models import (
    Assertion,
    AssertionSeverity,
    AssertionTarget,
    AssertionType,
    TestCase,
    TestSuite,
)


class YAMLTestParser:
    """Parses YAML test case files into TestSuite objects."""

    @staticmethod
    def parse_file(file_path: str) -> TestSuite:
        """Parse a YAML test file.

        Args:
            file_path: Path to the YAML file

        Returns:
            Parsed TestSuite object
        """
        path = Path(file_path)
        if not path.exists():
            msg = f"Test file not found: {file_path}"
            raise FileNotFoundError(msg)

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return YAMLTestParser._build_test_suite(data)

    @staticmethod
    def parse_directory(directory: str) -> list[TestSuite]:
        """Parse all YAML test files in a directory.

        Args:
            directory: Path to directory containing test files

        Returns:
            List of parsed TestSuite objects
        """
        path = Path(directory)
        if not path.is_dir():
            msg = f"Not a directory: {directory}"
            raise NotADirectoryError(msg)

        test_suites = []
        for yaml_file in sorted(path.glob("**/*.backtest.yaml")):
            test_suites.append(YAMLTestParser.parse_file(str(yaml_file)))

        return test_suites

    @staticmethod
    def _build_test_suite(data: dict[str, Any]) -> TestSuite:
        """Build TestSuite from parsed YAML data.

        Args:
            data: Parsed YAML dictionary

        Returns:
            TestSuite object
        """
        test_cases = []
        for test_data in data.get("test_cases", []):
            test_cases.append(YAMLTestParser._build_test_case(test_data))

        return TestSuite(
            name=data.get("name", "Unnamed Test Suite"),
            description=data.get("description", ""),
            instructions_version=data.get("instructions_version", "main"),
            model_under_test=data.get("model_under_test", "claude-3-5-sonnet-20250109"),
            test_cases=test_cases,
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _build_test_case(data: dict[str, Any]) -> TestCase:
        """Build TestCase from parsed data.

        Args:
            data: Test case data dictionary

        Returns:
            TestCase object
        """
        assertions = []
        for assertion_data in data.get("assertions", []):
            assertions.append(YAMLTestParser._build_assertion(assertion_data))

        return TestCase(
            description=data.get("description", ""),
            task=data.get("task", ""),
            assertions=assertions,
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _build_assertion(data: dict[str, Any]) -> Assertion:
        """Build Assertion from parsed data.

        Args:
            data: Assertion data dictionary

        Returns:
            Assertion object
        """
        assertion_type = AssertionType(data.get("type", "must_contain"))
        target_str = data.get("target", "full_response")

        try:
            target = AssertionTarget(target_str)
        except ValueError:
            target = AssertionTarget.FULL_RESPONSE

        severity_str = data.get("severity", "error")
        try:
            severity = AssertionSeverity(severity_str)
        except ValueError:
            severity = AssertionSeverity.ERROR

        return Assertion(
            type=assertion_type,
            target=target,
            description=data.get("description", ""),
            severity=severity,
            pattern=data.get("pattern"),
            expected_value=data.get("expected_value"),
            metadata=data.get("metadata", {}),
        )
