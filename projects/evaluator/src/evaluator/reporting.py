"""Report generation for test results."""

from datetime import datetime, timezone
from pathlib import Path

from evaluator.models import TestResult


class MarkdownReporter:
    """Generates Markdown reports from test results."""

    @staticmethod
    def generate(results: list[TestResult], title: str = "Test Results") -> str:
        """Generate a Markdown report.

        Args:
            results: List of test results
            title: Report title

        Returns:
            Markdown formatted report
        """
        lines = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
        lines.append("")

        # Summary statistics
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Tests:** {total}")
        lines.append(f"- **Passed:** {passed}")
        lines.append(f"- **Failed:** {failed}")
        lines.append(f"- **Pass Rate:** {pass_rate:.1f}%")
        lines.append("")

        # Duration
        total_duration = sum(r.duration_seconds for r in results)
        lines.append(f"- **Total Duration:** {total_duration:.2f}s")
        lines.append("")

        # Test details
        lines.append("## Test Details")
        lines.append("")

        for i, result in enumerate(results, 1):
            status_icon = "✓" if result.passed else "✗"
            lines.append(f"### {i}. {status_icon} {result.test_case.description}")
            lines.append("")

            lines.append(f"**Status:** {'PASSED' if result.passed else 'FAILED'}")
            lines.append(f"**Duration:** {result.duration_seconds:.2f}s")
            lines.append("")

            if result.test_case.task:
                lines.append(f"**Task:** {result.test_case.task[:100]}...")
                lines.append("")

            # Assertion results
            if result.assertion_results:
                lines.append("**Assertions:**")
                lines.append("")
                for assertion_result in result.assertion_results:
                    icon = "✓" if assertion_result.passed else "✗"
                    lines.append(f"- {icon} {assertion_result.assertion.description}")
                    if not assertion_result.passed:
                        lines.append(f"  - {assertion_result.message}")
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def save(results: list[TestResult], output_path: str, title: str = "Test Results") -> None:
        """Save report to file.

        Args:
            results: List of test results
            output_path: Path to save report
            title: Report title
        """
        report = MarkdownReporter.generate(results, title)
        Path(output_path).write_text(report, encoding="utf-8")


class HTMLReporter:
    """Generates HTML reports from test results."""

    @staticmethod
    def generate(results: list[TestResult], title: str = "Test Results") -> str:
        """Generate an HTML report.

        Args:
            results: List of test results
            title: Report title

        Returns:
            HTML formatted report
        """
        lines = []
        lines.append("<!DOCTYPE html>")
        lines.append("<html>")
        lines.append("<head>")
        lines.append("<meta charset='utf-8'>")
        lines.append(f"<title>{title}</title>")
        lines.append("<style>")
        lines.append("""
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 20px;
    background-color: #f5f5f5;
}
.container {
    max-width: 1200px;
    margin: 0 auto;
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
h1 { color: #333; }
.summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 15px;
    margin: 20px 0;
}
.summary-item {
    padding: 15px;
    background-color: #f9f9f9;
    border-left: 4px solid #007bff;
    border-radius: 4px;
}
.summary-item.failed {
    border-left-color: #dc3545;
}
.summary-item.passed {
    border-left-color: #28a745;
}
.test-item {
    margin: 15px 0;
    padding: 15px;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
}
.test-item.passed {
    border-left: 4px solid #28a745;
    background-color: #f0f8f4;
}
.test-item.failed {
    border-left: 4px solid #dc3545;
    background-color: #fef5f5;
}
.test-title {
    font-size: 16px;
    font-weight: bold;
    margin: 0;
}
.test-status {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: bold;
    margin-right: 10px;
}
.test-status.passed {
    background-color: #28a745;
    color: white;
}
.test-status.failed {
    background-color: #dc3545;
    color: white;
}
.assertion {
    margin: 10px 0;
    padding: 8px;
    background-color: white;
    border-left: 3px solid #ddd;
    border-radius: 2px;
}
.assertion.passed {
    border-left-color: #28a745;
}
.assertion.failed {
    border-left-color: #dc3545;
}
.footer {
    margin-top: 30px;
    padding-top: 15px;
    border-top: 1px solid #ddd;
    font-size: 12px;
    color: #666;
}
""")
        lines.append("</style>")
        lines.append("</head>")
        lines.append("<body>")
        lines.append("<div class='container'>")

        # Header
        lines.append(f"<h1>{title}</h1>")
        lines.append(f"<p><strong>Generated:</strong> {datetime.now(timezone.utc).isoformat()}</p>")

        # Summary
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0
        total_duration = sum(r.duration_seconds for r in results)

        lines.append("<div class='summary'>")
        lines.append(f"<div class='summary-item'><strong>Total Tests</strong><br>{total}</div>")
        lines.append(f"<div class='summary-item passed'><strong>Passed</strong><br>{passed}</div>")
        lines.append(f"<div class='summary-item failed'><strong>Failed</strong><br>{failed}</div>")
        lines.append(
            f"<div class='summary-item'><strong>Pass Rate</strong><br>{pass_rate:.1f}%</div>"
        )
        lines.append(
            f"<div class='summary-item'><strong>Duration</strong><br>{total_duration:.2f}s</div>"
        )
        lines.append("</div>")

        # Test results
        lines.append("<h2>Test Results</h2>")
        for i, result in enumerate(results, 1):
            status_class = "passed" if result.passed else "failed"
            status_text = "PASSED" if result.passed else "FAILED"

            lines.append(f"<div class='test-item {status_class}'>")
            lines.append("<p class='test-title'>")
            lines.append(f"<span class='test-status {status_class}'>{status_text}</span>")
            lines.append(f"{result.test_case.description}")
            lines.append("</p>")
            lines.append(f"<p><strong>Duration:</strong> {result.duration_seconds:.2f}s</p>")

            if result.assertion_results:
                lines.append("<div style='margin-top: 10px;'><strong>Assertions:</strong>")
                for ar in result.assertion_results:
                    a_status = "passed" if ar.passed else "failed"
                    lines.append(f"<div class='assertion {a_status}'>")
                    lines.append(f"<strong>{ar.assertion.description}</strong>")
                    if not ar.passed:
                        lines.append(f"<p>{ar.message}</p>")
                    lines.append("</div>")
                lines.append("</div>")

            lines.append("</div>")

        # Footer
        lines.append("<div class='footer'>")
        lines.append(f"<p>Report generated at {datetime.now(timezone.utc).isoformat()}</p>")
        lines.append("</div>")

        lines.append("</div>")
        lines.append("</body>")
        lines.append("</html>")

        return "\n".join(lines)

    @staticmethod
    def save(results: list[TestResult], output_path: str, title: str = "Test Results") -> None:
        """Save HTML report to file.

        Args:
            results: List of test results
            output_path: Path to save report
            title: Report title
        """
        report = HTMLReporter.generate(results, title)
        Path(output_path).write_text(report, encoding="utf-8")
