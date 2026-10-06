# Applications of the Cross-Package Analysis Framework

**Date**: 2025-11-02
**Framework Version**: Phase 1 & 2 Complete, Phase 3 Pending

The cross-package analysis framework in **tsrs** provides a foundation for analyzing Python code dependencies, dead code, and function reachability across multiple packages. This document outlines both current and potential applications of this technology.

---

## 1. Dead Code Elimination (Primary Use Case)

**Status**: ✅ Implemented

The primary application: identify and remove unused functions, classes, and modules across package boundaries.

### Current Implementation
- **Import tracking**: Maps imports across packages
- **Call graph analysis**: Builds function call graphs spanning multiple packages
- **Reachability analysis**: Determines which functions are reachable from entry points
- **Dead code filtering**: Identifies unreachable code conservatively

### Example Workflow
```bash
tsrs-cli analyze /path/to/venv              # Map available packages
tsrs-cli find-dead-code /path/to/project    # Find unreachable code
```

### Real-World Benefit
- Deploy only the code you use
- Reduce package sizes by 30-70%
- Improve security by removing unused dependencies

---

## 2. Test Impact Analysis (Inverted Framework)

**Status**: 🔄 Conceptual (Ready for Implementation)

One of the most powerful applications: **invert the framework** to determine which tests are affected by code changes, similar to [pytest-testmon](https://github.com/tarpas/pytest-testmon).

### Concept: From Bottom-Up

**Conventional approach** (pytest-testmon):
- Track which code each test executes
- When code changes, look up affected tests
- Run only the minimal test subset

**Our inverted approach**:
- Analyze code to find all functions that would be reached from tests
- When code changes, check if changed functions are in the reachability graph
- Run tests that depend on the changed code

### Implementation Strategy

```rust
// Phase 3: Test Impact Analysis Feature
struct TestImpactAnalyzer {
    // For each test function, compute its reachability closure
    test_reachability: HashMap<String, HashSet<String>>,  // test_name -> {reachable functions}

    // Reverse mapping: which tests reach each function
    function_test_dependents: HashMap<String, HashSet<String>>,
}

impl TestImpactAnalyzer {
    pub fn compute_test_impact(&self, changed_functions: &[String]) -> Vec<String> {
        // Find all tests that reach any of the changed functions
        changed_functions
            .iter()
            .flat_map(|func| self.function_test_dependents.get(func).cloned())
            .collect()
    }
}
```

### Workflow

```bash
# 1. Analyze test reachability (run once after test changes)
tsrs-cli analyze-test-impact /path/to/project /path/to/tests > test-impact.json

# 2. When code changes, determine affected tests
tsrs-cli affected-tests test-impact.json src/changed_module.py

# Output: List of affected test IDs to run
# E.g., ["test_utils.py::test_validate_email", "test_integration.py::test_register_user"]

# 3. Run only affected tests
pytest $(tsrs-cli affected-tests test-impact.json src/changed_module.py)
```

### Advantages Over pytest-testmon

| Aspect | pytest-testmon | tsrs Inversion |
|--------|---|---|
| **Approach** | Runtime tracking | Static analysis |
| **Overhead** | Minimal runtime tracing | One-time upfront analysis |
| **Coverage** | Only tests that ran | All reachable code paths |
| **CI Optimization** | Faster test runs | Broader impact detection |
| **Maintenance** | Requires execution | Works offline |

### Example Use Case

```python
# src/user_validation.py
def validate_email(email: str) -> bool:
    """Validate email format"""
    return "@" in email and "." in email

# src/user_service.py
from .user_validation import validate_email

def register_user(email: str, name: str) -> User:
    if not validate_email(email):
        raise ValueError("Invalid email")
    return User(email=email, name=name)

# tests/test_user_service.py
def test_register_user_valid():
    user = register_user("user@example.com", "John")
    assert user.email == "user@example.com"

def test_register_user_invalid():
    with pytest.raises(ValueError):
        register_user("invalid", "John")
```

**Impact Analysis**:
```
changed: src/user_validation.py::validate_email
↑ Called by: src/user_service.py::register_user
↑ Called by: tests/test_user_service.py::test_register_user_valid
           tests/test_user_service.py::test_register_user_invalid
Run tests: test_register_user_valid, test_register_user_invalid
```

---

## 3. Package Dependency Visualization

**Status**: ✅ Partially Implemented (Graphviz export available)

Generate visual representations of package dependencies and call graphs.

### Current Features
- **Graphviz DOT export**: Visualize dependency graphs
- **HTML reports**: Interactive dead code reports
- **JSON output**: Machine-readable analysis results

### Example

```bash
tsrs-cli find-dead-code /path/to/project --format graphviz > dependencies.dot
dot -Tpng dependencies.dot -o dependencies.png
```

### Future Enhancements
- Interactive HTML dependency explorer
- Package boundary visualization
- Import cycle detection

---

## 4. Package Slimming (Minimal venv Creation)

**Status**: ✅ Implemented

Create minimal virtual environments containing only necessary packages.

### Use Case

Large projects often have many unused dependencies:
- Test dependencies not used in production
- Optional features never activated
- Outdated libraries kept for compatibility

### Workflow

```bash
# Create a slim venv containing only used packages
tsrs-cli slim /path/to/project /path/to/venv -o /path/to/.venv-slim

# Results: ~30-70% smaller venv
ls -lah /path/to/venv           # Original: 1.2 GB
ls -lah /path/to/.venv-slim     # Slim: 400-800 MB
```

### Real-World Scenarios
- **Docker images**: Smaller container sizes
- **Lambda/Serverless**: Reduced deployment packages
- **CI/CD**: Faster dependency installation
- **Embedded Python**: Constrained environments

---

## 5. Incremental Code Analysis

**Status**: 🔄 Planned (Phase 3)

Track code changes between runs and only analyze modified files.

### Concept

```rust
struct IncrementalAnalyzer {
    // Store previous analysis
    previous_analysis: CallGraph,
    source_hashes: HashMap<String, String>,

    // Compare and analyze only changed files
    fn analyze_incremental(&self, project: &Path) -> Result<CallGraph> {
        // ...
    }
}
```

### Benefits
- CI pipelines with thousands of files
- Continuous analysis without performance degradation
- Fine-grained change tracking

---

## 6. Automatic Import Optimization

**Status**: 🔄 Phase 3 Work

Detect and remove unnecessary imports, consolidate redundant imports.

### Examples

```python
# Before
from utils import validate_email, format_date, unused_helper
from helpers import parse_json

# After (optimized)
from utils import validate_email, format_date
from helpers import parse_json
```

### Use Case
- Reduce module load times
- Improve code clarity
- Detect circular dependencies

---

## 7. Coverage-Guided Testing

**Status**: 🔄 Conceptual

Use the call graph to guide test generation, ensuring comprehensive coverage.

### Idea

```
Test Generation Pipeline:
Code Analysis → Function Graph → Uncovered Functions → Generate Tests
```

### Tools Integration
- Hypothesis: Property-based testing of uncovered functions
- Coverage.py: Combine with line coverage for better insights
- pytest: Parameterized test generation

---

## 8. Multi-Version Compatibility Analysis

**Status**: 🔄 Planned

Determine which code paths are reachable across different Python versions.

### Example

```python
# src/compatibility.py
if sys.version_info >= (3, 10):
    def use_match_statement():
        match value:
            case 1: ...
else:
    def use_if_chain():
        if value == 1: ...
```

**Analysis Output**:
```
Python 3.9: use_if_chain is reachable
Python 3.10+: use_match_statement is reachable
Python 3.12+: both reachable
```

---

## 9. Performance Hotspot Detection

**Status**: 🔄 Conceptual

Identify frequently-called functions or deep call chains.

### Example

```rust
struct PerformanceAnalyzer {
    // Count call paths to each function
    call_depth: HashMap<String, usize>,
    call_frequency: HashMap<String, usize>,
}

pub fn find_hotspots(&self) -> Vec<(String, usize)> {
    // Functions reachable through many paths = potential optimization targets
}
```

### Use Case
- Focus optimization efforts on high-impact functions
- Identify unnecessarily deep call chains
- Suggest refactoring opportunities

---

## 10. Documentation Auto-Generation

**Status**: 🔄 Planned

Generate documentation from the call graph and reachability analysis.

### Example Output

```markdown
## Module: user_service

### Public API
- `register_user(email, name)` - Register a new user
  - Depends on: `validate_email`, `create_user_record`
  - Called by: [3 test functions]
  - Reach depth: 4

### Internal Functions
- `_hash_password()` - Not exposed in public API
  - Used by: `register_user`, `update_password`

### Unused Functions
- `_legacy_validation()` - Dead code, candidates for removal
```

---

## Framework Applications Summary

| Application | Status | Effort | Impact | References |
|---|---|---|---|---|
| Dead code elimination | ✅ Complete | Low | High | Primary use case |
| Test impact analysis | 🔄 Ready | Medium | **Very High** | pytest-testmon |
| Dependency visualization | ✅ Partial | Low | Medium | Graphviz export |
| Package slimming | ✅ Complete | Low | High | Docker, Lambda |
| Incremental analysis | 🔄 Phase 3 | High | High | Performance |
| Import optimization | 🔄 Phase 3 | Medium | Medium | Code quality |
| Coverage-guided testing | 🔄 Research | High | Medium | Hypothesis, Coverage.py |
| Multi-version analysis | 🔄 Planned | Medium | Medium | Version compatibility |
| Performance analysis | 🔄 Planned | Medium | Medium | Optimization |
| Documentation generation | 🔄 Planned | Medium | Low | Knowledge |

---

## Integration Points

### With Popular Tools

**Testing**:
- pytest: Test impact analysis, fixture dependency tracking
- pytest-testmon: Inverse approach for test selection
- hypothesis: Coverage-guided property testing

**Code Quality**:
- pylint: Dead code detection complement
- vulture: Dead code detection (similar goals)
- bandit: Security with dependency awareness

**Performance**:
- py-spy: Combine CPU profiling with call graph
- memory-profiler: Identify heavy code paths
- cProfile: Annotate with reachability info

**CI/CD**:
- GitHub Actions: Run only affected tests
- GitLab CI: Conditional pipeline stages
- Jenkins: Parallel test execution with impact analysis

**Deployment**:
- Docker: Slim venv for smaller images
- AWS Lambda: Minimal deployment packages
- Kubernetes: Reduced container sizes

---

## Research Opportunities

1. **Formal Verification**: Use call graph for safety properties
2. **Machine Learning**: Predict code changes likely to break tests
3. **Fuzzing**: Generate test cases for uncovered code
4. **Type Inference**: Combine with type checkers for better analysis
5. **Distributed Systems**: Track cross-service dependencies

---

## References

### Tools with Similar Goals

- **pytest-testmon**: Runtime test impact analysis ([GitHub](https://github.com/tarpas/pytest-testmon))
  - Tracks which code each test executes
  - Suggests tests to run based on code changes
  - Our inversion: static analysis instead of runtime tracking

- **vulture**: Dead code finder ([GitHub](https://github.com/jendrikseipp/vulture))
  - Single-package analysis
  - Conservative approach
  - No cross-package support

- **Graphviz**: Graph visualization ([Website](https://graphviz.org))
  - DOT format output
  - Used for dependency visualization

- **Coverage.py**: Code coverage measurement ([Website](https://coverage.readthedocs.io))
  - Runtime coverage tracking
  - Can be combined with call graph for comprehensive analysis

- **Hypothesis**: Property-based testing ([Website](https://hypothesis.readthedocs.io))
  - Could use uncovered code detection for test generation

---

## Next Steps

### Phase 3 Priority List

1. **Test impact analysis** - Highest potential impact
2. **Incremental analysis** - Performance for large codebases
3. **Import optimization** - Quick wins for code quality
4. **Multi-version analysis** - Version compatibility
5. **Performance analysis** - Optimization guidance

### Community Feedback Needed

- Are you interested in test impact analysis?
- Which integration (pytest, GitHub Actions, etc.) is most valuable?
- Would you use cross-package analysis in your projects?

---

**Status**: Framework ready for Phase 3 applications. Test impact analysis identified as highest-value next feature.

**Contributes to**: Better testing, faster CI/CD, smaller deployments, improved code quality.
