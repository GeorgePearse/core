# Python API Reference

Use AI Backtest programmatically from Python code.

## Core Classes

### AgentInvoker

Invoke Claude with instruction files.

```python
from evaluator.agent import AgentInvoker

invoker = AgentInvoker(api_key="sk-ant-...")

response = invoker.invoke(
    task="Write a Python function",
    instruction_file_path="/path/to/CLAUDE.md",
    model="claude-3-5-sonnet-20250109",
    max_tokens=4096
)

print(response.full_response)
print(response.generated_code)
print(response.generated_commands)
```

### TestRunner

Run test suites and collect results.

```python
from evaluator.runner import TestRunner
from evaluator.parser import YAMLTestParser

# Parse tests
test_suites = YAMLTestParser.parse_directory("tests/backtests")

# Run tests
runner = TestRunner()
results = runner.run_suites(test_suites)

# Or run single test
result = runner.run_test(test_case, test_suite)
```

### YAMLTestParser

Parse YAML test files.

```python
from evaluator.parser import YAMLTestParser

# Parse single file
test_suite = YAMLTestParser.parse_file("tests/backtests/test.backtest.yaml")

# Parse directory
test_suites = YAMLTestParser.parse_directory("tests/backtests")

# Access test data
for suite in test_suites:
    print(f"Suite: {suite.name}")
    for test_case in suite.test_cases:
        print(f"  Test: {test_case.description}")
        for assertion in test_case.assertions:
            print(f"    Assert: {assertion.description}")
```

### AssertionRegistry

Evaluate assertions on responses.

```python
from evaluator.assertions import AssertionRegistry

# Evaluate single assertion
result = AssertionRegistry.evaluate(assertion, response)

print(f"Passed: {result.passed}")
print(f"Message: {result.message}")
print(f"Score: {result.score}")
```

### VersionComparator

Compare test results across versions.

```python
from evaluator.comparison import VersionComparator

# Compare results
comparison = VersionComparator.compare(baseline_results, candidate_results)

# Check for regressions
if VersionComparator.has_regressions(comparison):
    report = VersionComparator.regression_report(comparison)
    print(report)

# Access comparison data
print(f"Regressions: {len(comparison.regressions)}")
print(f"Improvements: {len(comparison.improvements)}")
print(f"Score deltas: {comparison.score_deltas}")
```

## Reporting

### MarkdownReporter

Generate Markdown reports.

```python
from evaluator.reporting import MarkdownReporter

# Generate report
report = MarkdownReporter.generate(results, title="Test Results")
print(report)

# Save to file
MarkdownReporter.save(results, "report.md")
```

### HTMLReporter

Generate HTML reports.

```python
from evaluator.reporting import HTMLReporter

# Generate report
html = HTMLReporter.generate(results, title="Test Results")

# Save to file
HTMLReporter.save(results, "report.html")
```

## Advanced

### Custom Validators

```python
from evaluator.code_analysis import CodeAnalyzer, CodeAnalysisRegistry
from evaluator.models import AssertionResult

class CustomValidator(CodeAnalyzer):
    def analyze(self, assertion, response):
        # Your validation logic
        passed = True  # Your check

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message="Your message"
        )

# Register
CodeAnalysisRegistry.register("custom", CustomValidator)
```

### LLM Judge Caching

```python
from evaluator.cache import JudgeCache

cache = JudgeCache()

# Cleanup expired entries
deleted = cache.cleanup_expired()

# Clear all
cache.clear()

# Access database
import sqlite3
conn = sqlite3.connect('.evaluator_cache.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM judge_cache")
print(f"Cached entries: {cursor.fetchone()[0]}")
```

## Complete Example

```python
from evaluator.parser import YAMLTestParser
from evaluator.runner import TestRunner
from evaluator.comparison import VersionComparator
from evaluator.reporting import HTMLReporter, MarkdownReporter

# 1. Parse tests
test_suites = YAMLTestParser.parse_directory("tests/backtests")
print(f"Loaded {len(test_suites)} test suites")

# 2. Run tests with baseline
runner = TestRunner()
baseline_results = []
for suite in test_suites:
    results = runner.run_suite(suite)
    baseline_results.extend(results)

# 3. Save baseline
MarkdownReporter.save(baseline_results, "baseline.md")

# ... Make changes to CLAUDE.md / AGENTS.md ...

# 4. Run tests with candidate
candidate_results = []
for suite in test_suites:
    results = runner.run_suite(suite)
    candidate_results.extend(results)

# 5. Compare versions
comparison = VersionComparator.compare(baseline_results, candidate_results)

# 6. Check for regressions
if VersionComparator.has_regressions(comparison):
    print("❌ Regressions detected!")
    print(VersionComparator.regression_report(comparison))
else:
    print("✅ No regressions!")

# 7. Generate reports
MarkdownReporter.save(candidate_results, "candidate.md")
HTMLReporter.save(candidate_results, "report.html")

# 8. Print statistics
total = len(candidate_results)
passed = sum(1 for r in candidate_results if r.passed)
print(f"\nResults: {passed}/{total} passed ({100*passed/total:.1f}%)")
```

## Diff Evaluation

### DiffParser

Parse unified diff format (git diff output).

```python
from evaluator import DiffParser

parser = DiffParser()

# Parse raw diff text
diff = parser.parse("""
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,5 @@
 def process(data):
+    if data is None:
+        return None
     return data.strip()
""")

# Access diff properties
print(f"Files changed: {diff.total_files_changed}")
print(f"Additions: {diff.total_additions}")
print(f"Deletions: {diff.total_deletions}")
print(f"Summary:\n{diff.summary()}")

# Get specific file
file_diff = diff.get_file("src/utils.py")
print(f"Is new file: {file_diff.is_new_file}")
print(f"Is deleted: {file_diff.is_deleted_file}")

# Access hunks
for hunk in file_diff.hunks:
    print(f"Hunk: {hunk.header}")
    print(f"  Additions: {len(hunk.additions)}")
    print(f"  Deletions: {len(hunk.deletions)}")
```

### DiffParser.parse_from_response

Extract diff from LLM response text.

```python
from evaluator import DiffParser

parser = DiffParser()

# Extract from markdown code block
response = """
Here's the fix:

```diff
diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1,2 +1,3 @@
 def foo():
-    pass
+    return 42
```
"""

diff = parser.parse_from_response(response)
if diff:
    print(f"Found diff with {diff.total_files_changed} files")
else:
    print("No diff found in response")
```

### DiffValidator

Validate diff syntax and applicability.

```python
from evaluator import DiffParser, DiffValidator

parser = DiffParser()
validator = DiffValidator()

diff = parser.parse(diff_text)

# Validate syntax
result = validator.validate_syntax(diff)
print(f"Is valid: {result.is_valid}")
print(f"Errors: {result.errors}")
print(f"Warnings: {result.warnings}")

# Validate can be applied to source
file_contents = {
    "src/utils.py": "def process(data):\n    return data.strip()\n"
}
result = validator.validate_can_apply(diff, file_contents)
print(f"Can apply: {result.is_valid}")
if not result.is_valid:
    for error in result.errors:
        print(f"  Error: {error}")
```

### DiffJudgeEvaluator

Evaluate diff quality using LLM.

```python
from evaluator import (
    DiffJudgeEvaluator,
    Assertion,
    AssertionType,
    AssertionTarget,
    AgentResponse,
)

evaluator = DiffJudgeEvaluator(
    api_key="sk-ant-...",
    judge_model="claude-sonnet-4-20250514",
)

assertion = Assertion(
    type=AssertionType.DIFF_JUDGE,
    target=AssertionTarget.GENERATED_DIFF,
    description="Diff fixes the bug correctly",
    metadata={"threshold": 0.7},
)

response = AgentResponse(
    task="Fix the null pointer bug",
    full_response="Here's the fix...",
    generated_diff=diff_text,
    model="claude-3-5-sonnet",
    instruction_file_path="CLAUDE.md",
)

result = evaluator.evaluate(assertion, response)
print(f"Passed: {result.passed}")
print(f"Score: {result.score}")
print(f"Evidence: {result.evidence}")
```

### DiffSyntaxEvaluator

Validate diff is syntactically correct.

```python
from evaluator import DiffSyntaxEvaluator

evaluator = DiffSyntaxEvaluator()
result = evaluator.evaluate(assertion, response)
```

### DiffAppliesEvaluator

Validate diff can be applied to source files.

```python
from evaluator import DiffAppliesEvaluator

evaluator = DiffAppliesEvaluator()

# file_contents passed via assertion.metadata
assertion = Assertion(
    type=AssertionType.DIFF_APPLIES,
    target=AssertionTarget.GENERATED_DIFF,
    description="Diff applies cleanly",
    metadata={
        "file_contents": {
            "src/utils.py": "original source code..."
        }
    },
)

result = evaluator.evaluate(assertion, response)
```

### Diff Models

```python
from evaluator import (
    GitDiff,
    FileDiff,
    DiffHunk,
    DiffLine,
    DiffLineType,
    DiffValidationResult,
)

# DiffLineType enum
DiffLineType.CONTEXT    # Unchanged line (space prefix)
DiffLineType.ADDITION   # Added line (+ prefix)
DiffLineType.DELETION   # Deleted line (- prefix)
DiffLineType.HEADER     # Diff header line
DiffLineType.HUNK_HEADER  # @@ line

# DiffLine - single line in a diff
line = DiffLine(
    type=DiffLineType.ADDITION,
    content="new line content",
    new_line_no=5,
)

# DiffHunk - section starting with @@
hunk = DiffHunk(
    old_start=1,
    old_count=3,
    new_start=1,
    new_count=4,
    header="@@ -1,3 +1,4 @@",
    lines=[...],
)
hunk.additions  # List of added lines
hunk.deletions  # List of deleted lines
hunk.context_lines  # List of context lines

# FileDiff - diff for single file
file_diff = FileDiff(
    old_path="src/utils.py",
    new_path="src/utils.py",
    hunks=[hunk],
    is_new_file=False,
    is_deleted_file=False,
    is_renamed=False,
    is_binary=False,
)
file_diff.path  # Most relevant path
file_diff.total_additions
file_diff.total_deletions

# GitDiff - complete parsed diff
git_diff = GitDiff(
    raw_diff="...",
    files=[file_diff],
)
git_diff.total_files_changed
git_diff.total_additions
git_diff.total_deletions
git_diff.files_added
git_diff.files_deleted
git_diff.files_modified
git_diff.get_file("path/to/file.py")
git_diff.summary()

# DiffValidationResult
result = DiffValidationResult(is_valid=True)
result.add_error("Error message")  # Sets is_valid=False
result.add_warning("Warning message")  # Doesn't affect is_valid
```

## Models

### AgentResponse
Response from agent invocation.

```python
@dataclass
class AgentResponse:
    task: str
    full_response: str
    generated_code: list[str]
    generated_commands: list[str]
    generated_diff: Optional[str]  # Git diff output
    tool_calls: list[dict]
    model: str
    conversation_trace: list[dict]
    # ... more fields
```

### TestResult
Result of running a test case.

```python
@dataclass
class TestResult:
    test_case: TestCase
    agent_response: AgentResponse
    assertion_results: list[AssertionResult]
    passed: bool
    duration_seconds: float
    # ... more fields
```

### AssertionResult
Result of evaluating an assertion.

```python
@dataclass
class AssertionResult:
    assertion: Assertion
    passed: bool
    message: str
    score: Optional[float]
    evidence: Optional[dict]
    timestamp: datetime
```

## See Also

- [Writing Tests](../guides/writing-tests.md) - YAML test format
- [Assertion Types](../guides/assertions.md) - All 13 assertion types
- [Diff Evaluation](../guides/diff-evaluation.md) - Git diff testing guide
- [Advanced Features](../guides/advanced.md) - Custom validators, caching
