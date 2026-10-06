# Advanced Features

Beyond basics: custom validators, caching, snapshots, and more.

## LLM Judge Caching

Judge results are automatically cached to save costs and time.

### How It Works

- **Cache key:** Hash of (model_under_test, response_text, judge_prompt)
- **Storage:** SQLite database (`.evaluator_cache.db`)
- **TTL:** 24 hours by default
- **Cost:** ~$0.001-0.01 per unique judge call

### Verify Cache Usage

```python
from evaluator.cache import JudgeCache

cache = JudgeCache()

# Check cache statistics
import sqlite3
conn = sqlite3.connect('.evaluator_cache.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM judge_cache")
cached_calls = cursor.fetchone()[0]
print(f"Cached judge calls: {cached_calls}")
```

### Clear Cache

```bash
# Delete cache file
rm .evaluator_cache.db

# Or programmatically
from evaluator.cache import JudgeCache
cache = JudgeCache()
cache.clear()
```

### Adjust Cache TTL

```python
from evaluator.llm_judge import LLMJudgeEvaluator

# Cache entries expire after 7 days
evaluator = LLMJudgeEvaluator(cache_ttl_hours=7*24)
```

## Custom Code Analyzers

Build your own validators for specific requirements.

### Built-in Validators

- `python_type_check` - Type hint validation
- `docstring_check` - Docstring presence
- `no_bash_find` - Prevent `find` command
- `no_sys_path_modify` - Prevent sys.path modifications

### Create Custom Validator

```python
from evaluator.code_analysis import CodeAnalyzer, CodeAnalysisRegistry
from evaluator.models import AssertionResult

class NoPrintDebugAnalyzer(CodeAnalyzer):
    """Prevent print() debugging statements"""

    def analyze(self, assertion, response):
        code_blocks = self._get_code_blocks(response)

        for code in code_blocks:
            if 'print(' in code and 'logger' not in code:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    message="Found print() statements; use logger instead",
                )

        return AssertionResult(
            assertion=assertion,
            passed=True,
            message="✓ No debug print statements found",
        )

# Register it
CodeAnalysisRegistry.register("no_print_debug", NoPrintDebugAnalyzer)
```

### Use Custom Validator

```yaml
assertions:
  - type: code_analysis
    metadata:
      validator: "no_print_debug"
    description: "Should use logger, not print()"
    severity: error
```

## Snapshot Testing

Compare outputs against known-good snapshots.

### First Run: Create Snapshot

```yaml
assertions:
  - type: snapshot
    metadata:
      snapshot_name: "api_endpoint_example"
      fields: ["generated_code"]
    description: "API endpoint example should be consistent"
```

Run the test:
```bash
pytest tests/backtests/test.backtest.yaml
```

This creates `.snapshots/api_endpoint_example.snapshot.json`.

### Subsequent Runs: Compare

Same assertion compares new output against snapshot. Test passes if they match.

### Update Snapshots

After reviewing changes, update:

```bash
# Update all snapshots
evaluator run --tests tests/backtests/ --update-snapshots

# Or via pytest
pytest tests/backtests/ --snapshot-update
```

### Review Snapshot Changes

Before updating, review the diff:

```bash
# Show what changed
diff .snapshots/old.snapshot.json .snapshots/new.snapshot.json

# Or use git
git diff .snapshots/
```

### Multiple Fields in Snapshot

```yaml
assertions:
  - type: snapshot
    metadata:
      snapshot_name: "complete_example"
      fields:
        - "full_response"
        - "generated_code"
        - "generated_commands"
    description: "Complete example output"
```

## Version Comparison

Detect regressions across instruction changes.

### Baseline vs Candidate

```bash
# Create baseline (current main branch)
evaluator run --tests tests/backtests/ --output baseline.json

# Edit CLAUDE.md or AGENTS.md...

# Create candidate (with your changes)
evaluator run --tests tests/backtests/ --output candidate.json

# Compare
evaluator compare --baseline baseline.json --candidate candidate.json
```

### Regression Report

Shows:
- Tests that were passing now fail (❌ regressions)
- Tests that were failing now pass (✅ improvements)
- Score changes for LLM judge assertions
- Detailed diff of behavioral changes

### In GitHub Actions

```yaml
- name: Compare versions
  run: evaluator compare --baseline baseline.json --candidate candidate.json
```

## Custom LLM Judge Prompts

Tune judge behavior for your needs.

### Basic Judge Prompt

```yaml
metadata:
  judge_prompt: "Is this code well-written?"
  threshold: 0.7
```

### Structured Judge Prompt

```yaml
metadata:
  judge_prompt: |
    Evaluate this code on these criteria:
    1. **Correctness** - Does it work?
    2. **Readability** - Is it clear?
    3. **Efficiency** - Is it performant?

    Respond with JSON:
    {
      "score": 0-1 average,
      "correctness": 0-1,
      "readability": 0-1,
      "efficiency": 0-1,
      "reasoning": "..."
    }
  threshold: 0.75
```

### Framework-Specific Judge

```yaml
metadata:
  judge_prompt: |
    Evaluate if this follows FastAPI best practices:
    - Uses type hints
    - Has proper error handling
    - Uses pydantic models
    - Includes docstrings

    Score 0-1 based on adherence to these practices.
    Respond: {"score": 0-1, "reasoning": "..."}
  threshold: 0.8
```

## Custom Assertion Types

Extend the framework with domain-specific assertions.

### Create Custom Assertion

```python
from evaluator.assertions import AssertionEvaluator, AssertionRegistry
from evaluator.models import AssertionResult, AssertionType, Assertion, AgentResponse

class SecurityAnalysisEvaluator(AssertionEvaluator):
    """Check for security issues"""

    def evaluate(self, assertion: Assertion, response: AgentResponse) -> AssertionResult:
        code = self._get_check_content(assertion, response)

        security_issues = []

        # Check for hardcoded secrets
        if 'password' in code and '"' in code:
            security_issues.append("Hardcoded password found")

        # Check for SQL injection vulnerabilities
        if 'f"SELECT' in code or "f'SELECT" in code:
            security_issues.append("Potential SQL injection")

        if security_issues:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=f"Security issues: {', '.join(security_issues)}",
                evidence={"issues": security_issues}
            )

        return AssertionResult(
            assertion=assertion,
            passed=True,
            message="✓ No security issues detected"
        )

# Register the new evaluator
class SecurityAssertionType(str, Enum):
    SECURITY_ANALYSIS = "security_analysis"

AssertionRegistry.register(SecurityAssertionType.SECURITY_ANALYSIS, SecurityAnalysisEvaluator)
```

### Use Custom Assertion

```yaml
assertions:
  - type: security_analysis
    description: "Check for security vulnerabilities"
    severity: error
```

## Programmatic API Usage

Run tests from Python code.

### Basic Usage

```python
from evaluator.parser import YAMLTestParser
from evaluator.runner import TestRunner
from evaluator.reporting import HTMLReporter

# Parse tests
test_suites = YAMLTestParser.parse_directory("tests/backtests")

# Run tests
runner = TestRunner()
results = runner.run_suites(test_suites)

# Generate report
all_results = [r for results_list in results.values() for r in results_list]
HTMLReporter.save(all_results, "report.html")
```

### With Filtering

```python
# Parse specific file
test_suite = YAMLTestParser.parse_file("tests/backtests/tool_usage.backtest.yaml")

# Run specific test case
runner = TestRunner()
result = runner.run_test(test_suite.test_cases[0], test_suite)

# Check results
if result.passed:
    print("✅ Test passed!")
else:
    for failure in result.failures:
        print(f"❌ {failure.message}")
```

### Version Comparison

```python
from evaluator.comparison import VersionComparator

# Compare two runs
comparison = VersionComparator.compare(baseline_results, candidate_results)

# Check for regressions
if VersionComparator.has_regressions(comparison):
    print("⚠️ Regressions detected!")
    print(VersionComparator.regression_report(comparison))
else:
    print("✅ No regressions!")
```

## Performance Optimization

### Cache Management

```python
from evaluator.cache import JudgeCache

cache = JudgeCache()

# Clean up expired entries (> 24 hours old)
deleted = cache.cleanup_expired()
print(f"Deleted {deleted} expired entries")
```

### Parallel Testing

```bash
# With pytest-xdist
pip install pytest-xdist

# Run tests in parallel (4 workers)
pytest tests/backtests/ -n 4

# Auto-detect CPU count
pytest tests/backtests/ -n auto
```

### Skip Expensive Tests

```yaml
test_cases:
  - description: "Expensive LLM judge test"
    task: "..."
    assertions:
      - type: llm_judge  # This is slow
        metadata:
          judge_prompt: "..."
```

Run without judge tests:

```bash
# Skip LLM judge assertions
pytest tests/backtests/ -m "not llm"
```

## Testing Different Models

```python
from evaluator.runner import TestRunner

# Test with Claude 3 Opus (more capable, more expensive)
runner = TestRunner()
test_suite.model_under_test = "claude-3-opus-20250729"
results = runner.run_suite(test_suite)
```

## Debugging

### See Full Response

```bash
pytest tests/backtests/ -s  # Don't capture output
```

### Check Agent Trace

```python
result = runner.run_test(test_case, test_suite)

# Full conversation history
for msg in result.agent_response.conversation_trace:
    print(f"{msg['role']}: {msg['content'][:100]}...")
```

### Inspect Assertion Details

```python
result = runner.run_test(test_case, test_suite)

for assertion_result in result.assertion_results:
    print(f"Assertion: {assertion_result.assertion.description}")
    print(f"Passed: {assertion_result.passed}")
    print(f"Message: {assertion_result.message}")
    print(f"Evidence: {assertion_result.evidence}")
```

## Sandbox Execution

For isolated, reproducible test execution, use E2B cloud sandboxes:

```bash
# Run tests in isolated sandbox
evaluator run --tests tests/backtests/ --executor e2b

# Use a template with CLI tools
evaluator run --executor e2b --e2b-template claude-tools
```

See [Sandbox Execution](sandbox.md) for full documentation on E2B integration.

## Next Steps

- [Sandbox Execution](sandbox.md) - Isolated cloud sandbox testing with E2B
- [CI/CD Integration](ci-cd.md) - GitHub Actions setup
- [Examples](../examples/basic-test.md) - Real-world test suites
- [API Reference](../reference/api.md) - Complete API documentation
