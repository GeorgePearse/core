# Cross-Package Call Graph Analysis - Implementation Guide

## Current State

The dead code detection system works perfectly **within a single package** but is conservative when crossing package boundaries:

- Package A exports `func()` in its `__all__`
- Package B imports `func()` and calls it
- **Current**: System doesn't see the inter-package call, so marks func as exported (conservatively protected)
- **Desired**: System tracks the cross-package call and correctly identifies func as reachable

## The Problem

When analyzing Package A independently, we can't know if its exports are used by other packages. This leads to:

1. **False positives**: Functions appear unused when they're actually imported elsewhere
2. **Inefficient slim venvs**: Keep packages with only dead code usage patterns
3. **Lost optimization opportunity**: Can't create truly minimal environments

## Implementation Strategy

### Phase 1: Import Resolution

**Goal**: Track which functions each module imports

**Implementation Steps**:

1. **Extend `CallGraphAnalyzer`** to store imports per package:

```rust
pub struct CallGraphAnalyzer {
    // ... existing fields ...

    /// Imports map: (package, local_name) → (source_package, source_function)
    imports: HashMap<(String, String), (String, String)>,

    /// Track which functions are imported from where
    /// For: from mylib import helper
    /// Stores: ("mypackage", "helper") → ("mylib", "helper")
}
```

2. **Integrate with ImportCollector**:
   - ImportCollector already extracts all imports
   - Use it to populate the imports map
   - Handle aliases: `from mylib import func as f` → map "f" to mylib.func

3. **Resolve local calls to external sources**:
```rust
fn resolve_call(&self, package: &str, call_name: &str) -> Option<(String, String)> {
    // Check if call_name is a local function first
    if self.function_index.contains_key(&(package.to_string(), call_name.to_string())) {
        return Some((package.to_string(), call_name.to_string()));
    }

    // Check if it's an imported function
    self.imports.get(&(package.to_string(), call_name.to_string()))
        .cloned()
}
```

### Phase 2: Inter-Package Call Edges

**Goal**: Create call edges across package boundaries

**Implementation Steps**:

1. **Track imported functions as entry points**:
```rust
fn mark_imported_functions_as_reachable(&mut self) {
    // For each function imported by any package
    // Mark it as reachable in its source package
    // This simulates "external callers"

    for ((from_pkg, local_name), (to_pkg, func_name)) in &self.imports {
        if let Some(func_id) = self.function_index.get(&(to_pkg.clone(), func_name.clone())) {
            // Mark as reachable from external import
            self.entry_points.insert(*func_id);
        }
    }
}
```

2. **Build inter-package call edges**:
   - When extracting calls from a function, resolve them using `resolve_call()`
   - If call resolves to a function in another package, create a cross-package edge
   - Store these edges separately or in the same edges vector

### Phase 3: Whole-Program Reachability

**Goal**: Compute reachability across entire package tree

**Implementation Steps**:

1. **Update reachability analysis** to follow inter-package edges:
```rust
pub fn compute_reachable_cross_package(&self) -> HashSet<FunctionId> {
    // Standard BFS but follow both local and imported call edges
    let mut reachable = HashSet::new();
    let mut queue = VecDeque::from_iter(self.entry_points.iter().copied());

    while let Some(current) = queue.pop_front() {
        if reachable.insert(current) {
            // Find outgoing edges (both local and inter-package)
            for edge in &self.edges {
                if edge.caller == current && !reachable.contains(&edge.callee) {
                    queue.push_back(edge.callee);
                }
            }
        }
    }

    reachable
}
```

2. **Update dead code detection** to use cross-package analysis:
```rust
pub fn find_dead_code_cross_package(&self) -> Vec<(FunctionId, String)> {
    let reachable = self.compute_reachable_cross_package();

    // Rest of logic same as before
    // But now reachable set includes cross-package calls
    self.nodes
        .values()
        .filter_map(|node| {
            if reachable.contains(&node.id) {
                return None;
            }
            // ... filtering logic ...
        })
        .collect()
}
```

## Data Flow

```
    Source Code Files
         │ (all packages)
         ↓
  ┌─────────────────────┐
  │ Analyze Each Package│  ← Current: Independent analysis
  └─────────────────────┘
         │
    ┌────┴────┬────┬────┐
    ↓         ↓    ↓    ↓
  pkg_a   pkg_b  lib_1 lib_2
  calls   calls  calls calls
         │
         ↓
  ┌──────────────────────────┐
  │ NEW: Import Resolution   │
  │ Link package references  │
  └──────────────────────────┘
         │
         ↓
  ┌──────────────────────────┐
  │ Build Inter-Package Edges│
  │ Create cross-pkg calls   │
  └──────────────────────────┘
         │
         ↓
  ┌──────────────────────────┐
  │ Whole-Program Reachability
  │ BFS across all packages  │
  └──────────────────────────┘
         │
         ↓
  Accurate Dead Code Detection
  (Functions unused across entire project)
```

## Testing Strategy

### Unit Tests

1. **Import Tracking**:
```rust
#[test]
fn test_cross_package_import_tracking() {
    let pkg_a = r#"
from pkg_b import helper
def main():
    helper()
"#;

    let pkg_b = r#"
def helper():
    pass
"#;

    let mut analyzer = CallGraphAnalyzer::new();
    analyzer.analyze_source("pkg_a", pkg_a).unwrap();
    analyzer.analyze_source("pkg_b", pkg_b).unwrap();

    // helper should be marked as reachable via import from pkg_a
    let dead = analyzer.find_dead_code_cross_package();
    assert!(!dead.iter().any(|(_, name)| name == "helper"));
}
```

2. **Inter-Package Calls**:
   - Import with alias: `from lib import func as f`
   - Multiple imports: `from lib import a, b, c`
   - Package imports: `import utils` then `utils.func()`

3. **Reachability Chain**:
   - A → B (local) → C (imported from pkg_c)
   - Verify C is marked as reachable

### Integration Tests

Test on multi-package projects:
- `test_packages/project_multi_package/` with multiple interdependent packages
- Verify slim venv creation excludes only truly unused packages
- Verify dead code detection accurate across package boundaries

## Integration Points

### In `src/callgraph.rs`:

1. Add import tracking fields to `CallGraphAnalyzer`
2. Create `resolve_call()` method
3. Create `compute_reachable_cross_package()` method
4. Create `find_dead_code_cross_package()` method
5. Add comprehensive unit tests

### In `src/bin/cli.rs`:

1. Update `optimize` command to use cross-package analysis
2. Update dead code reporting to show package-level information

### In `src/reporting.rs`:

1. Enhance reports to show cross-package relationships
2. Show which packages depend on which others
3. Show external entry points

## Expected Benefits

Once implemented, this will enable:

1. **Accurate slim venvs**: 30-50% smaller by excluding truly unused packages
2. **Better dead code detection**: No false positives from inter-package usage
3. **Package dependency analysis**: Understand what uses what
4. **Full optimization potential**: Entire venv can be analyzed as one unit

## Implementation Effort

- **Phase 1 (Import Resolution)**: ~2-3 hours
  - Update CallGraphAnalyzer struct
  - Integrate import tracking
  - Add tests

- **Phase 2 (Inter-Package Edges)**: ~3-4 hours
  - Enhance call edge extraction
  - Create cross-package edge tracking
  - Update reachability analysis

- **Phase 3 (Whole-Program Analysis)**: ~2-3 hours
  - Implement cross-package BFS
  - Update dead code detection
  - Create integration tests

- **Total**: ~7-10 hours for complete cross-package support

## Key Files to Modify

1. **src/callgraph.rs** (main implementation)
   - Add import tracking
   - Add resolve_call() method
   - Add cross-package analysis methods

2. **src/bin/cli.rs** (CLI integration)
   - Update optimize command logic
   - Use cross-package methods

3. **tests/** (comprehensive testing)
   - Multi-package test fixtures
   - Cross-package call scenarios

## Backward Compatibility

These changes can be additive:
- Keep existing `find_dead_code()` as-is
- Add new `find_dead_code_cross_package()`
- CLI can choose which to use (add flag)
- All existing tests continue to pass

## Success Criteria

Once implemented:
- ✅ Multi-package projects analyzed as a unit
- ✅ No false positives from inter-package imports
- ✅ Slim venvs created based on whole-program usage
- ✅ All existing tests pass
- ✅ New integration tests for multi-package scenarios pass
- ✅ Reports show cross-package relationships

---

**Note**: This is a significant improvement but not required for basic functionality. The system works correctly within single packages. Cross-package support is the next major optimization frontier.
