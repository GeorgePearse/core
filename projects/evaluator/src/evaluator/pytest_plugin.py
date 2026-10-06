"""pytest plugin for running backtests as pytest tests."""

from pathlib import Path
from typing import Any, Generator, Optional

import pytest

from evaluator.parser import YAMLTestParser
from evaluator.runner import TestRunner


def pytest_collect_file(file_path: Path, parent: Any) -> Optional["BacktestFile"]:
    """pytest hook to collect .backtest.yaml files.

    Args:
        file_path: Path being collected
        parent: Parent collector

    Returns:
        BacktestFile collector if yaml file, None otherwise
    """
    if file_path.suffix == ".yaml" and ".backtest" in file_path.name:
        return BacktestFile.from_parent(parent, path=file_path)
    return None


class BacktestFile(pytest.File):
    """pytest File collector for backtest YAML files."""

    def collect(self) -> Generator[Any, None, None]:
        """Collect test items from YAML file.

        Yields:
            BacktestItem objects for each test case
        """
        try:
            test_suite = YAMLTestParser.parse_file(str(self.path))
            for test_case in test_suite.test_cases:
                yield BacktestItem.from_parent(
                    self,
                    name=test_case.description.replace(" ", "_")[:50],
                    test_suite=test_suite,
                    test_case=test_case,
                )
        except Exception as e:
            pytest.fail(f"Failed to parse backtest file {self.path}: {e}")


class BacktestItem(pytest.Item):
    """pytest Item for a single backtest case."""

    def __init__(
        self,
        name: str,
        parent: Any,
        test_suite: Any,
        test_case: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize backtest item.

        Args:
            name: Test item name
            parent: Parent collector
            test_suite: TestSuite object
            test_case: TestCase object
            **kwargs: Additional arguments
        """
        super().__init__(name, parent, **kwargs)
        self.test_suite = test_suite
        self.test_case = test_case

    def runtest(self) -> None:
        """Run the backtest.

        Raises:
            AssertionError: If test fails
        """
        runner = TestRunner()
        result = runner.run_test(self.test_case, self.test_suite)

        if not result.passed:
            # Collect failure details
            failures = result.failures
            failure_messages = "\n".join(f"- {f.message}" for f in failures)
            msg = f"Backtest failed:\n{failure_messages}"
            pytest.fail(msg)

    def repr_failure(self, excinfo: Any) -> str:
        """Format failure message.

        Args:
            excinfo: Exception info

        Returns:
            Formatted failure message
        """
        return str(excinfo.value)
