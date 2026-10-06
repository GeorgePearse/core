# tsrs Test Packages

This directory contains integration test packages for validating tree-shaking behavior. Each package tests a specific aspect of the tsrs analyzer to ensure it correctly identifies and removes (or conservatively keeps) code.

## Testing Philosophy

tsrs prioritizes **high precision over aggressive optimization**:
- **Never remove code unless absolutely certain it's unused**
- **Keep module-level exports and public APIs** (may be used externally)
- **Keep explicitly imported packages** even if only partially used
- **Be conservative with dynamic features** (imports, reflection, etc.)

The test scenarios below verify that tsrs maintains this conservative approach while still effectively identifying dead code.

## Test Scenarios

### 1. **test_unused_function**
**Current Status**: ✅ Exists

**What it tests**: Basic dead code detection
- A standalone function defined but never called
- Verifies tsrs can identify completely unused functions

**Package structure**:
- `package_one/`: Simple package with HelloWorld class and add_one_and_one function
- `tests/`: pytest tests that validate functionality
- `scripts/demo.py`: Script demonstrating usage

**Expected behavior**:
- tsrs should flag unused functions
- But keep functions that are in `__all__` or imported (conservative approach)

**Related code**: `callgraph.rs` - `find_unused_functions()`

---

### 2. **test_unused_constant**
**Status**: 📋 Planned

**What it tests**: Dead global constants
- Module defines 5-6 module-level constants
- Only 2-3 are actually used in code
- Some are only exported in `__all__` but never used externally

**Package structure**:
```
test_unused_constant/
├── package_const/
│   ├── config.py (defines: API_KEY, DB_HOST, DEBUG, TIMEOUT, CACHE_SIZE, MAX_RETRIES)
│   ├── __init__.py (exports only API_KEY, DB_HOST via __all__)
│   └── core.py (uses only API_KEY and DB_HOST)
├── tests/
│   └── test_config.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep all module-level constants (conservative: external code may use via getattr)
- Don't remove constants even if not referenced internally
- Respect `__all__` exports

**Key insight**: Global constants are kept per philosophy ("may be used externally or through reflection")

---

### 3. **test_partially_used_class**
**Status**: 📋 Planned

**What it tests**: Class with mixed method usage
- Single class with 5-6 methods
- Only 2-3 methods are called
- Some methods are "private" (_prefix), others public

**Package structure**:
```
test_partially_used_class/
├── package_data/
│   ├── processor.py (DataProcessor class)
│   │   - __init__()
│   │   - process() [USED]
│   │   - validate() [USED]
│   │   - _internal_helper() [NOT USED]
│   │   - transform() [NOT USED]
│   │   - serialize() [NOT USED]
│   ├── __init__.py (exports DataProcessor)
├── tests/
│   └── test_processor.py (calls only process() and validate())
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep ALL class methods (conservative: inheritance, reflection, plugins)
- Don't remove methods even if not called
- Respect class integrity

**Key insight**: Classes are kept intact per philosophy

---

### 4. **test_dead_class**
**Status**: 📋 Planned

**What it tests**: Entirely unused classes
- Module exports 3 classes
- Only 1-2 classes are actually imported/used
- Unused classes are never referenced

**Package structure**:
```
test_dead_class/
├── package_models/
│   ├── models.py (defines UserModel, ProductModel, OrderModel)
│   ├── __init__.py (exports only UserModel, ProductModel)
├── tests/
│   └── test_models.py (uses only UserModel)
└── scripts/
    └── demo.py (uses only UserModel)
```

**Expected behavior**:
- Might flag unused classes per call graph analysis
- But keep them if in `__all__` (conservative: external code might use)
- Track which classes are actually instantiated vs just defined

**Key insight**: Tests the boundary between "dead code" and "public API"

---

### 5. **test_transitive_dependencies**
**Status**: 📋 Planned

**What it tests**: Function call chains across imports
- Package A defines func1, func2, func3
- Package B imports A and calls only func1
- func1 internally calls func2, but not func3
- Tests whether tsrs correctly traces call chains

**Package structure**:
```
test_transitive_dependencies/
├── package_math/
│   ├── operations.py
│   │   - add(x, y) [DIRECTLY CALLED]
│   │   - add_with_logging(x, y) [calls add() + log()]
│   │   - multiply(x, y) [NOT CALLED]
│   │   - divide(x, y) [NOT CALLED]
│   ├── logging_utils.py (internal)
│   │   - log(msg)
│   ├── __init__.py (exports add, add_with_logging)
├── consumer.py (uses only add())
├── tests/
│   └── test_math.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep add() (directly called)
- Keep add_with_logging() (exported, even if not used)
- May flag multiply() and divide() as unused
- Must keep log() because it's called by add_with_logging()

**Key insight**: Tests call graph depth and transitive usage tracking

---

### 6. **test_star_import**
**Status**: 📋 Planned

**What it tests**: `from module import *` patterns
- Module defines `__all__` with specific exports
- Consumer code uses `from module import *`
- Some items in `__all__` are never actually used
- Some non-`__all__` items are defined but not exported

**Package structure**:
```
test_star_import/
├── package_utils/
│   ├── helpers.py
│   │   - format_string() [IN __all__, USED]
│   │   - parse_int() [IN __all__, NOT USED]
│   │   - _internal_cache() [NOT IN __all__]
│   ├── __init__.py (__all__ = ['format_string', 'parse_int'])
├── consumer.py (uses: from package_utils.helpers import *)
├── tests/
│   └── test_helpers.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep all items in `__all__` (conservative: star imports need them)
- Don't remove items just because they're not used after star import
- Treat star imports as "use all exports"

**Key insight**: Star imports are conservative by design

---

### 7. **test_decorator_usage**
**Status**: 📋 Planned

**What it tests**: Decorators and decorated functions
- Module defines multiple decorators
- Some decorators are used, others defined but never applied
- Some decorated functions are unused

**Package structure**:
```
test_decorator_usage/
├── package_decorators/
│   ├── decorators.py
│   │   - @timing_decorator [USED on process_data()]
│   │   - @logging_decorator [USED on validate()]
│   │   - @deprecated_decorator [DEFINED but NOT USED]
│   │   - @cache_decorator [DEFINED but NOT USED]
│   ├── handlers.py
│   │   - @timing_decorator process_data() [USED]
│   │   - @logging_decorator validate() [USED]
│   │   - unused_function() [NOT DECORATED, NOT CALLED]
│   ├── __init__.py
├── tests/
│   └── test_decorators.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep decorators (they might be part of public API)
- Track usage of decorated functions separately
- Flag unused decorators as dead code
- Keep decorators even if never applied (conservative)

**Key insight**: Decorator analysis and tracking

---

### 8. **test_inheritance_chain**
**Status**: 📋 Planned

**What it tests**: Class inheritance and method resolution
- Base class with several methods
- Child classes override some methods
- Some methods never called in any child class
- Tests method resolution order (MRO) and inheritance tracking

**Package structure**:
```
test_inheritance_chain/
├── package_shapes/
│   ├── shapes.py
│   │   - class Shape (base)
│   │     - area() [ABSTRACT]
│   │     - perimeter() [IMPLEMENTED, USED]
│   │     - describe() [IMPLEMENTED, NOT USED]
│   │     - _validate() [INTERNAL]
│   │   - class Circle(Shape)
│   │     - area() [OVERRIDE, USED]
│   │     - perimeter() [INHERITED, USED]
│   │   - class Rectangle(Shape)
│   │     - area() [OVERRIDE, USED]
│   ├── __init__.py
├── tests/
│   └── test_shapes.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep all methods in inheritance chain (conservative: subclass behavior)
- Don't remove overridden methods
- Don't remove base methods even if not called in specific child
- Respect __call__, __init__, and other magic methods

**Key insight**: Inheritance doesn't simplify dead code detection

---

### 9. **test_private_vs_public_api**
**Status**: 📋 Planned

**What it tests**: Public API conventions and private methods
- Module with clear public API (no underscore prefix)
- Module with private implementation (_prefix)
- Module with dunder methods (__name__)
- Tests respect for Python conventions

**Package structure**:
```
test_private_vs_public_api/
├── package_api/
│   ├── service.py
│   │   - public_endpoint() [PUBLIC, USED]
│   │   - helper_func() [PUBLIC, NOT USED]
│   │   - _internal_worker() [PRIVATE, USED]
│   │   - _unused_private() [PRIVATE, NOT USED]
│   │   - __init__() [DUNDER, USED]
│   │   - __str__() [DUNDER, NOT USED]
│   ├── __init__.py (__all__ = ['public_endpoint', 'helper_func'])
├── tests/
│   └── test_service.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep all public functions (no underscore) - they're API
- Keep private functions (_prefix) - conservative approach
- Always keep dunder methods (__name__)
- Respect `__all__` as public API definition

**Key insight**: Tests respect for Python conventions and public APIs

---

### 10. **test_circular_imports**
**Status**: 📋 Planned

**What it tests**: Circular dependencies and import loops
- Module A imports from B
- Module B imports from A
- Tests that tree-shaking doesn't infinite loop or miss dependencies

**Package structure**:
```
test_circular_imports/
├── package_circular/
│   ├── module_a.py
│   │   - from .module_b import helper_b()
│   │   - func_a() [calls helper_b()]
│   ├── module_b.py
│   │   - from .module_a import func_a()
│   │   - helper_b() [calls func_a()]
│   ├── __init__.py (exports func_a, helper_b)
├── tests/
│   └── test_circular.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Detect cycles without infinite loops
- Keep both func_a and helper_b (mutually dependent)
- Don't accidentally remove either due to circular reference
- Conservative: when in doubt, keep both

**Key insight**: Graph traversal needs cycle detection

---

### 11. **test_dynamic_imports**
**Status**: 📋 Planned

**What it tests**: Dynamic import patterns that are hard to analyze
- Uses `importlib.import_module()`
- Uses `__import__()`
- Uses `eval()` or `exec()`
- Tests conservative handling of dynamic code

**Package structure**:
```
test_dynamic_imports/
├── package_dynamic/
│   ├── loader.py
│   │   - import importlib
│   │   - get_handler(name) [dynamically imports modules]
│   │   - static_import() [regular import, USED]
│   ├── handlers/
│   │   - email.py (loaded dynamically)
│   │   - sms.py (loaded dynamically)
│   │   - push.py (defined but never loaded)
│   ├── __init__.py
├── tests/
│   └── test_loader.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Conservative: keep everything in handlers/
- Don't try to understand importlib patterns (too complex)
- Don't remove code that might be dynamically imported
- Flag as bailout/conservative analysis required

**Key insight**: Dynamic imports are essentially unknowable

---

### 12. **test_conditional_imports**
**Status**: 📋 Planned

**What it tests**: Conditional imports based on runtime conditions
- try/except import blocks for optional dependencies
- if/else import guards (Python version checks)
- Tests conservative handling of conditionals

**Package structure**:
```
test_conditional_imports/
├── package_compat/
│   ├── io_handler.py
│   │   - try:
│   │       from ujson import loads
│   │     except ImportError:
│   │       from json import loads
│   │   - if sys.version_info >= (3, 10):
│   │       from new_module import feature
│   │     else:
│   │       from legacy_module import feature
│   │   - handler(data) [uses either ujson or json]
│   ├── __init__.py
├── tests/
│   └── test_compat.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep both branches of conditional imports
- Don't try to trace version checks or environment conditions
- Conservative: keep everything that might run
- Both json and ujson modules should be kept

**Key insight**: Conditionals are unknowable at static analysis time

---

### 13. **test_method_types**
**Status**: 📋 Planned

**What it tests**: Different method types (@staticmethod, @classmethod, @property)
- Classes with static methods, class methods, properties
- Tests that different method types are handled correctly

**Package structure**:
```
test_method_types/
├── package_methods/
│   ├── config.py
│   │   - class Config
│   │     - @staticmethod default_port() [USED]
│   │     - @classmethod from_file() [NOT USED]
│   │     - @property host [USED]
│   │     - @property port [NOT USED]
│   │     - regular_method() [NOT USED]
│   ├── __init__.py
├── tests/
│   └── test_config.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep all method types (static, class, property, regular)
- Don't remove any methods from classes
- Recognize that properties are callable in specific ways
- Conservative: keep everything

**Key insight**: Different method types don't change the analysis

---

### 14. **test_context_managers**
**Status**: 📋 Planned

**What it tests**: Context manager protocols (__enter__, __exit__)
- Classes implementing context manager protocol
- Proper usage in `with` statements
- Unused context managers

**Package structure**:
```
test_context_managers/
├── package_contexts/
│   ├── managers.py
│   │   - class FileHandler
│   │     - __enter__() [DUNDER, USED via with]
│   │     - __exit__() [DUNDER, USED via with]
│   │     - cleanup() [USED by __exit__]
│   │   - class DatabasePool
│   │     - __enter__() [DEFINED but NOT USED]
│   │     - __exit__() [DEFINED but NOT USED]
│   ├── __init__.py
├── tests/
│   └── test_managers.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Keep all __enter__ and __exit__ methods
- Keep methods called within dunder methods
- Flag unused context managers (DatabasePool)
- But keep them due to conservative approach

**Key insight**: Dunder methods are special - always keep them

---

### 15. **test_nested_packages**
**Status**: 📋 Planned

**What it tests**: Multi-level package structures with cross-module imports
- Deep package hierarchies (pkg/subpkg/module.py)
- Cross-level imports (sibling, parent, child)
- Tests complex import resolution

**Package structure**:
```
test_nested_packages/
├── package_nested/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine.py (defines Engine)
│   │   └── utils.py (defines helpers)
│   ├── io/
│   │   ├── __init__.py
│   │   ├── reader.py (from ..core.engine import Engine)
│   │   └── writer.py (from ..core.utils import helper)
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py (from ..io.reader import Reader)
├── tests/
│   └── test_nested.py
└── scripts/
    └── demo.py
```

**Expected behavior**:
- Correctly resolve relative imports
- Track dependencies across package boundaries
- Keep all imported functions (conservative)
- Handle __init__.py re-exports

**Key insight**: Relative imports require careful path resolution

### 16. **test_slim_packages**
**Current Status**: ✅ Exists

**What it tests**: Slim CLI retains only packages imported by the code directory
- Two local packages are installed into the source venv (`used_pkg` and `unused_pkg`)
- The consumer project imports only `used_pkg`
- Exercises multiple import styles (direct, from, alias, submodule, wildcard)
- Ensures `tsrs-cli slim` copies the used package (and metadata) while pruning the unused one

**Package structure**:
```
test_slim_packages/
├── used_pkg/
│   ├── used_pkg/__init__.py  (defines greet())
│   └── used_pkg/subpkg/tool.py (defines get_tool_name())
├── used_pkg2/
│   └── used_pkg2/__init__.py  (defines greet2())
├── used_mod/
│   └── used_mod.py (single-module distribution)
├── used_pkg_extra/
│   └── used_pkg_extra/__init__.py (depends on extra-dep)
├── extra_dep/
│   └── extra_dep/__init__.py (transitive dependency for used_pkg_extra)
├── used_pkg_transitive/
│   └── used_pkg_transitive/__init__.py (imports extra_dep within its API)
├── used_src_layout/
│   └── src/used_src_layout (__init__.py + py.typed for typing metadata)
├── multi_mod/
│   ├── alpha.py (module used by consumers)
│   └── beta.py (module expected to be pruned)
├── used_ns_implicit/
│   └── used_ns_implicit/sub/helper.py (implicit namespace package)
├── used_ns_pkg_part/
│   └── used_ns_pkg/extra/second.py (extends used_ns_pkg namespace)
├── dash_pkg/
│   └── dash_pkg/__init__.py (dash-named distribution exposing greet())
├── used_native/
│   └── used_native/libs/libdummy.so (packaged native shared library)
├── unused_pkg/
│   └── unused_pkg/__init__.py (defines wave())
├── project/
│   └── main.py (import used_pkg; calls used_pkg.greet())
├── project_from_import/
│   └── main.py (from used_pkg import greet)
├── project_alias_import/
│   └── main.py (import used_pkg as used)
├── project_submodule_import/
│   └── main.py (from used_pkg.subpkg.tool import get_tool_name)
├── project_wildcard_import/
│   └── main.py (from used_pkg import *)
├── project_dash_import/
│   └── main.py (imports dash_pkg from a dashed distribution)
├── project_reexport_get_tool/
│   └── main.py (import re-exported attribute from used_pkg)
├── project_alias_function/
│   └── main.py (from used_pkg import greet as greet_alias)
├── project_submodule_alias/
│   └── main.py (import used_pkg.subpkg.tool as tool_module)
├── project_submodule_wildcard/
│   └── main.py (from used_pkg.subpkg import *)
├── project_multiline_import/
│   └── main.py (multiline from used_pkg.subpkg.tool import)
├── project_function_scope_import/
│   └── main.py (import inside main() function)
├── project_try_except_import/
│   └── main.py (try/except guarded import)
├── project_if_block_import/
│   └── main.py (import inside an if block)
├── project_backslash_import/
│   └── main.py (import using backslash continuation)
├── project_multi_import/
│   └── main.py (single statement importing multiple modules)
├── project_resource_access/
│   └── main.py (loads packaged JSON resource)
├── project_resource_template/
│   └── main.py (loads packaged text template)
├── project_resource_pkgutil/
│   └── main.py (loads resources via pkgutil.get_data)
├── project_resource_files/
│   └── main.py (loads resources via importlib.resources.files)
├── project_dynamic_import/
│   └── main.py (invokes used_pkg via __import__ for dynamic import coverage)
├── project_native_resource/
│   └── main.py (verifies native shared library remains packaged)
├── project_type_checking_import/
│   └── main.py (imports used_pkg only under typing guards)
├── project_package_relative/
│   └── app/main.py (package with relative imports)
├── project_single_module_import/
│   └── main.py (imports single-module used_mod)
├── project_extra_dep_unused/
│   └── main.py (imports used_pkg_extra but not extra_dep)
├── project_used_transitive/
│   └── main.py (imports used_pkg_transitive which uses extra_dep)
├── project_src_layout_import/
│   └── main.py (imports src-layout package used_src_layout)
├── project_select_alpha/
│   └── main.py (imports only alpha module from multi_mod)
├── project_two_used_packages/
│   └── main.py (imports used_pkg and used_pkg2)
├── project_namespace_multipkg/
│   └── main.py (imports used_ns_pkg and its extra namespace distribution)
├── project_implicit_namespace_import/
│   └── main.py (imports from implicit namespace package)
├── project_import_chain_subpkg/
│   └── main.py (accesses used_pkg.subpkg.tool via chained attributes)
├── project_from_pkg_import_subpkg/
│   └── main.py (from used_pkg import subpkg and uses tool)
└── project_submodule_alias_item/
    └── main.py (from used_pkg.subpkg import item as alias)
```

**Expected behavior**:
- Slim venv contains `used_pkg` but omits `unused_pkg` for all consumer variants, except for documented limitations
- Demonstrates selective package copying without manual excludes (direct import, from-import, alias import, function alias, submodule import, wildcard import, submodule wildcard, multiline import, function-scope import, try/except import, conditional import, backslash continuation, multi-import statements, submodule item alias, resource access including pkgutil/files APIs, nested templates, native shared libraries, src-layout packages with typing markers, single-module distributions, implicit namespace packages, pruning unused transitive dependencies, and retaining used transitive dependencies)
- `project_dynamic_import` highlights the current limitation: dynamically imported modules via `__import__` are not detected and may be pruned
- `project_type_checking_import` shows that TYPE_CHECKING-only imports do not keep packages in the slimmed environment
- `dash_pkg` + `project_dash_import` confirm distributions with hyphenated names are preserved when imported

**Related code**: `tests/cli_integration.rs` – `slim_keeps_used_package_and_prunes_unused`

---

### 17. **test_minify**
**Current Status**: ✅ Exists

**What it tests**: Minify subcommands emit rename plans and rewrite Python files
- Contains small Python modules with locals that should be renamed
- Exercises `tsrs-cli minify-plan`, `minify`, `apply-plan`, and `minify-plan-dir` / `apply-plan-dir`
- Ensures nested directories, structural pattern matching, comprehensions, and class metadata are captured in plan outputs
- Integration coverage includes glob includes/excludes and applying plans via stdin (`--plan-stdin`)

**Package structure**:
```
test_minify/
├── src/
│   ├── simple_module.py (module-level function with temporary locals)
│   ├── nested/
│   │   └── calculator.py (nested path exercising plan-dir recursion)
│   ├── patterns.py (stores structural pattern matching source used in tests)
│   ├── comprehension_module.py (list/dict comprehensions for metadata flags)
│   ├── class_module.py (class-based fixture validating reserved names)
│   └── class_methods.py (legacy class fixture used by plan-dir tests)
```

**Expected behavior**:
- `minify-plan` returns JSON for `simple_module.py` with rename entries
- `minify` rewrites locals in place without altering semantics
- `minify-plan-dir` bundles multiple files, preserves nested paths, and marks match/comprehension/class metadata

**Related code**: `tests/minify_integration.rs`, `tests/apply_integration.rs`

---

### 18. **test_minify_dependency**
**Current Status**: ✅ Exists

**What it tests**: Minifying a dependency package (and all of its local dependencies) does not break a downstream consumer's test suite
- Installs a transitive dependency (`minify-core`), a dependency (`minify-dep`), and a consumer (`minify-consumer`) into an isolated uv/venv environment
- Recursively runs `tsrs-cli minify`/`minify-dir` against the dependency tree before installation, following mappings defined in `[tool.tsrs.local-dependencies]`
- Executes the consumer's `pytest` suite to confirm behavior is preserved after minification

**Package structure**:
```
test_minify_dependency/
├── core_pkg/
│   ├── pyproject.toml (defines transitive dependency minify-core)
│   └── minify_core/
│       └── __init__.py (loop with locals targeted by minification)
├── dependency_pkg/
│   ├── pyproject.toml (minify-dep + `[tool.tsrs.local-dependencies]` mapping to ../core_pkg)
│   └── minify_dep/
│       └── __init__.py (delegates to minify_core and exposes consumer-facing helpers)
└── consumer_pkg/
    ├── pyproject.toml (depends on minify-dep)
    ├── minify_consumer/
    │   ├── __init__.py (exports helper functions)
    │   └── app.py (imports minify_dep and exercises recursive behavior)
    └── tests/
        └── test_app.py (pytest suite validating greetings & summaries)
```

**Expected behavior**:
- Minification rewrites local variables inside both `minify_dep` and its transitive dependency `minify_core`
- Installing the minified packages alongside the consumer succeeds via uv/pip
- `pytest` passes for the consumer package, demonstrating compatibility between minified dependency tree and consumer

**Related code**: `tests/minify_consumer_integration.rs`

---

## Running Tests

### Run a single test package:
```bash
cd test_packages/test_unused_function/package_one
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -e .
pytest tests/
```

### Run all test packages:
```bash
# TODO: Add automated test runner script
cd test_packages
./run_all_tests.sh
```

### Wheelhouse cache for third-party dependencies

To avoid re-downloading heavy packages for integration tests, populate the
local wheelhouse once and reuse it:

```bash
python scripts/bootstrap_wheelhouse.py
```

This stores wheels under `test_packages/.wheelhouse`. Tests automatically look
for this directory (or the path specified via `TSRS_WHEELHOUSE`) and pass
`--find-links` / `--no-index` flags when installing third-party requirements.
If the directory is absent, the tests fall back to PyPI.

### Using tsrs-minify-tree locally

`tsrs-minify-tree` is a helper binary that runs `tsrs-cli minify`/`minify-dir`
in-place for a package and any local dependencies recorded in
`pyproject.toml` under `[tool.tsrs.local-dependencies]`. It mirrors the
recursive traversal used by the integration tests and ensures each package is
minified exactly once before you run a consumer test suite.

pyproject snippet:
```toml
[tool.tsrs.local-dependencies]
minify-core = "../core_pkg"
```

Usage:
```bash
# Minify the dependency tree rooted at dependency_pkg
tsrs-minify-tree test_packages/test_minify_dependency/dependency_pkg

# Omit the argument to operate on the current directory
cd test_packages/test_minify_dependency/dependency_pkg
tsrs-minify-tree .
```

Notes:
- Only packages that appear in `project.dependencies` and have a matching entry
  in `[tool.tsrs.local-dependencies]` are traversed.
- Each discovered package is canonicalized and minified once to avoid cycles.
- All minification happens in-place; commit or back up sources first if
  needed.

### Test with tsrs tree-shaking:
```bash
# Create a slim venv
cd test_packages/test_unused_function
../../target/release/tsrs-cli slim . ./package_one/.venv -o .venv-slim

# Run tests against slim venv
.venv-slim/bin/pytest package_one/tests/
```

## Adding New Test Scenarios

1. **Create directory structure**:
   ```bash
   mkdir test_packages/test_<scenario_name>
   ```

2. **Create package with pyproject.toml**:
   ```bash
   mkdir test_packages/test_<scenario_name>/package_<name>
   # Create pyproject.toml (use uv)
   # Create package_<name>/ with __init__.py and modules
   ```

3. **Write test code**:
   - Include pytest tests that validate functionality
   - Use both public and private functions
   - Create scenarios that demonstrate the behavior to test

4. **Create demo script** (optional):
   ```bash
   mkdir test_packages/test_<scenario_name>/scripts
   # Create demo.py that demonstrates usage
   ```

5. **Document in this README**:
   - Add section with description
   - Explain what behavior is being tested
   - Document expected tsrs behavior

## Key Principles for Tests

- **Clarity**: Each test should test one aspect
- **Completeness**: Include pytest tests that verify functionality
- **Realism**: Use patterns found in real Python code
- **Conservation**: Test edge cases where tsrs should be conservative
- **Measurement**: Track code size reduction when applicable

## Expected Behavior Summary

| Scenario | Tsrs Behavior | Reason |
|----------|---------------|--------|
| Unused function | May flag as dead, but keep if exported | High precision, public API |
| Unused constant | Keep always | May be used externally |
| Unused class method | Keep always | Inheritance, reflection |
| Dead class | Keep if in __all__ | Public API safety |
| Transitive deps | Keep all in call chain | Conservative |
| Star import items | Keep all in __all__ | Star imports need them |
| Unused decorator | May flag, but keep | Public API |
| Inheritance methods | Keep all | MRO and subclassing |
| Private functions | Keep | Conservative |
| Dunder methods | Keep always | Protocol requirements |
| Circular imports | Keep both | Mutual dependency |
| Dynamic imports | Keep all | Unknowable at analysis time |
| Conditional imports | Keep all branches | Environment unknowable |
| Method types | Keep all | Different calling patterns |
| Context managers | Keep __enter__/__exit__ | Protocol requirements |
| Nested packages | Keep all in hierarchy | Relative imports complex |

## References

- [tsrs README](../README.md)
- [Callgraph Analysis](../src/callgraph.rs)
- [Import Analysis](../src/imports.rs)
- [Minification](../src/minify.rs)
