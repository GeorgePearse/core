# Test Selection Guide

**What it does**: Analyze code to determine which tests are affected by code changes, then run only the minimal test subset needed.

**Primary use case**: Speed up CI/CD pipelines by running only affected tests instead of the entire suite.

**Typical savings**: 30-80% reduction in test time (depending on test organization and change scope).

**Status**: 🔄 Ready for implementation (Phase 3 work)

---

## The Problem

Modern test suites can have hundreds or thousands of tests. Running the full suite on every commit is slow:

```
$ pytest tests/
tests/unit/ (500 tests)      → 45s ✅
tests/integration/ (100 tests) → 30s ✅
tests/e2e/ (50 tests)        → 120s ✅
Total: 195 tests, 195s
```

When you change a single utility function, do you really need to run all 195 tests?

```
# Developer changed: src/utils/validation.py::validate_email()
# Impact: Only 8 tests import or use validate_email()
# Question: Why run all 195 tests? Run those 8 instead!
```

---

## How It Works

### The Inverted Approach

Most test impact analysis tools (like [pytest-testmon](https://github.com/tarpas/pytest-testmon)) work **bottom-up**:
1. Run tests and record which code they execute
2. When code changes, look up which tests touched it
3. Run only those tests

**Problem**: Only sees code actually executed in your test runs (incomplete coverage).

**Our approach** works **top-down**:
1. Analyze code structure **statically** to find all functions reachable from tests
2. When code changes, check if changed functions are in any test's reachability graph
3. Run only tests that could reach the changed code

**Advantage**: Doesn't require test execution; sees all reachable code paths.

### The Analysis Pipeline

```
Source Code + Tests
        │
        ├─→ [CallGraphAnalyzer] Build function call graphs
        │   - What functions exist
        │   - What calls what
        │
        ├─→ [ImportCollector] Extract all imports
        │   - Which packages/modules are used
        │   - Function dependencies
        │
        └─→ [TestImpactAnalyzer] Compute reachability
            - For each test function
            - What code can it reach?
            - Build reverse mapping: code → tests that reach it
```

### Example: Detecting Affected Tests

```python
# src/user_validation.py
def validate_email(email: str) -> bool:
    """Check if email format is valid"""
    return "@" in email and "." in email

# src/user_service.py
from .user_validation import validate_email

def register_user(email: str, name: str) -> dict:
    if not validate_email(email):
        raise ValueError("Invalid email")
    return {"email": email, "name": name}

# tests/test_user_service.py
from src.user_service import register_user
import pytest

def test_register_valid_user():
    user = register_user("john@example.com", "John")
    assert user["email"] == "john@example.com"

def test_register_invalid_email():
    with pytest.raises(ValueError):
        register_user("invalid", "John")

def test_other_unrelated_test():
    assert 2 + 2 == 4
```

**Static analysis reveals**:
```
validate_email (in src/user_validation.py)
    ↑ called by: register_user
        ↑ called by: test_register_valid_user
        ↑ called by: test_register_invalid_email
```

**When someone changes validate_email()**:
- Run: `test_register_valid_user`, `test_register_invalid_email`
- Skip: `test_other_unrelated_test` (doesn't reach validate_email)

**Time saved**: Skip tests that don't care about validate_email changes

---

## Planned Usage

### 1. Initial Setup (One-time)

```bash
# Analyze test reachability
tsrs-cli analyze-test-impact ./src ./tests --output test-impact.json

# Output: JSON file mapping each test to the code it reaches
```

The `test-impact.json` file is checked into version control (it's source analysis, not runtime data).

### 2. On Code Changes

```bash
# When developers push code, CI can determine affected tests:
tsrs-cli affected-tests test-impact.json src/user_validation.py

# Output:
# tests/test_user_service.py::test_register_valid_user
# tests/test_user_service.py::test_register_invalid_email
```

### 3. Run Only Affected Tests

```bash
# In your CI pipeline:
AFFECTED_TESTS=$(tsrs-cli affected-tests test-impact.json src/user_validation.py)
pytest $AFFECTED_TESTS
```

---

## Expected Implementation

### API Commands (Phase 3)

```bash
# Analyze reachability from all test functions
tsrs-cli analyze-test-impact <python_dir> <tests_dir> \
  --output test-impact.json \
  --include "tests/**" \
  --exclude "tests/fixtures/**"

# Find affected tests when files change
tsrs-cli affected-tests test-impact.json <changed_file>

# JSON output for programmatic use
tsrs-cli affected-tests test-impact.json src/utils.py --json

# Show which code each test reaches (for debugging)
tsrs-cli test-impact-report test-impact.json --test <test_path>
```

### Library API (Rust)

```rust
use tsrs::TestImpactAnalyzer;

let analyzer = TestImpactAnalyzer::new("./src", "./tests")?;
let impact = analyzer.analyze()?;

// Get all tests that reach a specific function
let affected = impact.tests_reaching_function("user_validation", "validate_email");
println!("Run: {}", affected.join(", "));
// Output: tests/test_user_service.py::test_register_valid_user, ...
```

### Python API (via PyO3)

```python
import tsrs

# Load impact analysis
impact = tsrs.load_test_impact("test-impact.json")

# Find affected tests
affected = impact.affected_by_file("src/user_validation.py")
print(f"Run {len(affected)} tests")

# Determine coverage gaps
uncovered = impact.uncovered_functions()
```

---

## Real-World Example: GitHub Actions Integration

```yaml
name: Test Impact Analysis

on: [push, pull_request]

jobs:
  select-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust tools
        run: cargo install tsrs-cli

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Generate test impact map
        run: tsrs-cli analyze-test-impact ./src ./tests --output test-impact.json

      - name: Determine affected tests
        id: affected
        run: |
          # Find files changed in this PR
          CHANGED_FILES=$(git diff --name-only origin/main...HEAD -- '*.py')

          # Accumulate affected tests
          AFFECTED_TESTS=""
          for file in $CHANGED_FILES; do
            if [[ "$file" == src/* ]]; then
              TESTS=$(tsrs-cli affected-tests test-impact.json "$file" --json)
              AFFECTED_TESTS="$AFFECTED_TESTS $TESTS"
            fi
          done

          # Deduplicate and output
          UNIQUE_TESTS=$(echo "$AFFECTED_TESTS" | tr ' ' '\n' | sort -u | tr '\n' ' ')
          echo "tests=$UNIQUE_TESTS" >> $GITHUB_OUTPUT

      - name: Run selected tests
        run: |
          if [ -z "${{ steps.affected.outputs.tests }}" ]; then
            echo "No affected tests, running full suite as fallback"
            pytest tests/
          else
            echo "Running only affected tests:"
            pytest ${{ steps.affected.outputs.tests }}
          fi

      - name: Comment PR with test stats
        uses: actions/github-script@v7
        if: github.event_name == 'pull_request'
        with:
          script: |
            const tests = "${{ steps.affected.outputs.tests }}".split(' ').filter(Boolean).length;
            const message = tests > 0
              ? `✨ Test impact analysis: Selected ${tests} affected tests (out of 195 total)`
              : '⚡ No affected tests detected';
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: message
            });
```

---

## Advantages Over Alternatives

### Comparison with pytest-testmon

| Aspect | pytest-testmon | tsrs Test Selection |
|--------|---|---|
| **How it works** | Records code coverage during test execution | Static analysis of call graphs |
| **Setup cost** | Run tests once to build database | One-time code analysis |
| **Coverage visibility** | Only sees executed code | Sees all reachable code paths |
| **Handles skipped tests** | Misses untested code | Detects impact even if test skipped |
| **Performance** | Adds tracing overhead to test runs | Zero runtime overhead |
| **False negatives** | May miss affected tests (incomplete coverage) | Comprehensive (static analysis) |
| **False positives** | Minimal | Possible if analysis conservative |
| **CI integration** | Requires test execution | Pure analysis, works on code alone |

### Comparison with grep/regex Search

| Aspect | Text Search | tsrs Analysis |
|--------|---|---|
| **Precision** | Low (matches strings, not function refs) | High (understands call graphs) |
| **False positives** | High (matches "validate" in comments, strings) | Low (understands scope) |
| **Handles aliases** | No (`import x as y` confuses search) | Yes (tracks aliases) |
| **Cross-package** | Doesn't understand imports | Follows imports across packages |
| **Scalability** | Fast but not accurate | Slower but correct |

---

## Implementation Roadmap

### Phase 3 Priority List

1. **✅ Phase 1 & 2**: Call graph analysis infrastructure (done)
   - Function definitions and calls
   - Import resolution
   - Reachability computation

2. **🔄 Phase 3a**: Test Impact Analysis (next)
   - `TestImpactAnalyzer` struct
   - Compute reachability from test functions
   - Build reverse mapping: function → tests

3. **🔄 Phase 3b**: CLI Integration
   - `analyze-test-impact` command
   - `affected-tests` command
   - `test-impact-report` command

4. **🔄 Phase 3c**: Python/Library APIs
   - PyO3 bindings for test impact
   - Serialization format for impact data
   - Library documentation

5. **🔄 Phase 3d**: Tool Integration
   - pytest plugin for automatic test selection
   - GitHub Actions integration
   - GitLab CI examples

---

## Use Cases

### 1. Fast Pull Request Validation

Run only tests affected by PR changes:

```
PR: "Fix email validation function"
  Changed: src/user_validation.py
  Affected tests: 3 (of 195)
  Time: 2 seconds (vs. 195 seconds for full suite)
```

### 2. Deployment Safety

Ensure all tests affected by deployment are passing:

```
Deploy: Update user_service module
  Affected tests: 14
  Run all 14 affected tests before deploying
  ✅ All pass → Safe to deploy
```

### 3. Developer Feedback

Instant feedback on code changes:

```
$ git commit -m "Refactor user validation"
$ tsrs affected-tests test-impact.json -p  # Find affected tests for current commit
tests/test_user_service.py::test_register_valid_user
tests/test_user_service.py::test_register_invalid_email
$ pytest tests/test_user_service.py::test_register_valid_user \
          tests/test_user_service.py::test_register_invalid_email
```

### 4. CI/CD Cost Reduction

Large test suites cost money in CI:

```
Organization: 1000 developers, 5000 tests, 3 min per run
Current: 1000 devs × 20 commits/day × 3 min = 1000 hours/day
With test selection: 1000 devs × 20 commits/day × 0.5 min = 250 hours/day
Savings: 75%, plus reduced wait times for developers
```

---

## Design Decisions

### Why Static Analysis?

**Alternative**: Runtime tracking (like pytest-testmon)
**Our choice**: Static analysis

**Reasons**:
1. **Doesn't require test execution** - Works instantly, no test setup needed
2. **Sees all code paths** - Not just the ones you tested
3. **Works offline** - CI can analyze without running tests
4. **Deterministic** - Same analysis gives same results every time
5. **Fast** - No runtime overhead

### Why Conservative Approach?

**Conservative philosophy**: Rather miss a potential optimization than break something.

If there's any chance code might be used, we'll mark it as reachable.

**Examples**:
- `eval()` or `exec()`? Assume it can reach anything
- Module-level code? Assume it can reach anything
- `__all__` not found? Assume all functions are exported

This means you'll run some unnecessary tests, but you'll never skip a test that should run.

### Why Inverted (Code → Tests) Instead of (Tests → Code)?

**Our approach**:
- Analyze which functions are reachable from each test
- Build reverse map: function → tests that reach it
- When code changes, look up affected tests

**Alternative (pytest-testmon style)**:
- Execute tests and record function calls
- Store function → test mapping
- When code changes, look up tests

**Our advantages**:
1. Works without running tests
2. Detects unreachable code paths
3. Works for new tests (before first execution)
4. Deterministic (same result every run)

**Trade-off**:
- May be more conservative (run more tests than strictly necessary)
- But guaranteed to never miss affected tests

---

## Current Status & Timeline

### ✅ Completed (v0.2.0)
- Core call graph analysis framework
- Cross-package analysis infrastructure
- Import resolution and tracking

### 🔄 In Progress (Phase 3)
- Test impact analyzer implementation
- CLI command integration
- Documentation and examples

### ⏳ Planned
- Python library bindings (PyO3)
- pytest plugin for auto-selection
- IDE integration

### Roadmap

```
Now (Nov 2025)     → Phase 3a: TestImpactAnalyzer (core logic)
                   → Phase 3b: CLI commands (analyze-test-impact, affected-tests)

Dec 2025          → Phase 3c: Library/Python APIs
                   → Phase 3d: Tool integrations (pytest, GitHub Actions)

Q1 2026           → IDE extensions, performance optimizations
```

---

## FAQ

**Q: Will this work with my test framework?**
A: For anything that has functions. pytest, unittest, nose, etc. all use functions as test units.

**Q: What about fixtures and setup/teardown?**
A: Fixtures are functions too. The analysis sees all functions that a test reaches, including fixtures it imports.

**Q: What if code is dynamic (eval, exec, import)?**
A: We're conservative. Any function that could potentially be dynamic is marked as reachable.

**Q: Can I run the full test suite as a fallback?**
A: Absolutely. Use test selection for speed, but fall back to full suite if needed:
```bash
if [ -z "$AFFECTED_TESTS" ]; then
  pytest tests/
else
  pytest $AFFECTED_TESTS
fi
```

**Q: How accurate is the analysis?**
A: Conservative and precise. We may run some unnecessary tests, but we'll never skip a test that should run.

**Q: Can I regenerate the impact file?**
A: Yes, anytime. Just run `analyze-test-impact` again. It's pure static analysis.

**Q: What if I refactor test organization?**
A: Regenerate the impact file. Since it's based on static analysis, any changes to test structure are automatically picked up.

---

## Integration Examples

### GitHub Actions

See [Real-World Example](#real-world-example-github-actions-integration) above for a complete example.

### GitLab CI

```yaml
# .gitlab-ci.yml
test-affected:
  stage: test
  script:
    - tsrs-cli analyze-test-impact ./src ./tests --output test-impact.json
    - AFFECTED=$(tsrs-cli affected-tests test-impact.json $(git diff --name-only HEAD~1 HEAD -- '*.py'))
    - |
      if [ -z "$AFFECTED" ]; then
        echo "Running full test suite"
        pytest tests/
      else
        echo "Running affected tests"
        pytest $AFFECTED
      fi
  artifacts:
    reports:
      junit: test-results.xml
```

### Local Development

```bash
#!/bin/bash
# local-test.sh - Run affected tests for your changes

BRANCH=${1:-origin/main}
CHANGED_FILES=$(git diff --name-only $BRANCH...HEAD -- '*.py')

echo "Files changed since $BRANCH:"
echo "$CHANGED_FILES"

echo ""
echo "Finding affected tests..."
AFFECTED_TESTS=""
for file in $CHANGED_FILES; do
  TESTS=$(tsrs-cli affected-tests test-impact.json "$file" 2>/dev/null)
  AFFECTED_TESTS="$AFFECTED_TESTS $TESTS"
done

UNIQUE_TESTS=$(echo "$AFFECTED_TESTS" | tr ' ' '\n' | sort -u | grep -v '^$')

if [ -z "$UNIQUE_TESTS" ]; then
  echo "No affected tests found. Running full suite..."
  pytest tests/
else
  echo ""
  echo "Running affected tests ($(echo "$UNIQUE_TESTS" | wc -l) tests):"
  echo "$UNIQUE_TESTS"
  pytest $UNIQUE_TESTS
fi
```

---

## See Also

- [Applications Overview](APPLICATIONS.md) - Other uses of the analysis framework
- [Cross-Package Analysis Guide](CROSS_PACKAGE_ANALYSIS.md) - Technical details on call graph analysis
- [API Reference](API.md) - Using tsrs programmatically
