# Python Minification Design

## Overview
Scope-aware local renaming for functions using rustpython_parser AST. Collects function-local bindings and generates short names (a, b, c...) while respecting Python scoping rules.

## Core Data Structures

### FunctionPlan
```rust
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionPlan {
    /// Function name (for debugging/tracking)
    pub name: String,

    /// Original names in function scope (sorted for stability)
    pub local_names: Vec<String>,

    /// Mapping from original name to minified name
    pub rename_map: HashMap<String, String>,

    /// Names that cannot be renamed (globals, nonlocals, builtins, keywords)
    pub excluded_names: Vec<String>,
}
```

### MinifyPlan
```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MinifyPlan {
    /// Function plans in stable order (by source position)
    pub functions: Vec<FunctionPlan>,

    /// Python keywords that must never be renamed
    pub python_keywords: Vec<String>,

    /// Builtin names that should not be renamed
    pub builtins: Vec<String>,
}
```

## Short Name Generator

Simple sequential generator: a, b, c, ..., z, aa, ab, ..., zz, aaa, ...

```rust
pub struct ShortNameGen {
    counter: usize,
}

impl ShortNameGen {
    pub fn new() -> Self {
        Self { counter: 0 }
    }

    pub fn next(&mut self, keywords: &[String]) -> String {
        loop {
            let name = Self::generate(self.counter);
            self.counter += 1;

            if !keywords.contains(&name) {
                return name;
            }
        }
    }

    fn generate(n: usize) -> String {
        let mut num = n;
        let mut result = String::new();

        loop {
            result.push((b'a' + (num % 26) as u8) as char);
            num /= 26;
            if num == 0 {
                break;
            }
            num -= 1;
        }

        result.chars().rev().collect()
    }
}
```

## Python Keywords (Complete List)

Never rename these 35 keywords:

```rust
const PYTHON_KEYWORDS: &[&str] = &[
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return",
    "try", "while", "with", "yield",
];
```

## AST Node Types for Binding Collection

### 1. Function Parameters
```rust
// ast::StmtFunctionDef, ast::StmtAsyncFunctionDef
parameters: Parameters {
    posonlyargs: Vec<ParameterWithDefault>,  // positional-only
    args: Vec<ParameterWithDefault>,         // normal params
    vararg: Option<Parameter>,               // *args
    kwonlyargs: Vec<ParameterWithDefault>,   // keyword-only
    kwarg: Option<Parameter>,                // **kwargs
}

// Extract: .arg (Identifier) from each Parameter
```

### 2. Assignment Targets
```rust
// ast::StmtAssign
targets: Vec<Expr>  // Can be Name, Tuple, List, Subscript, Attribute

// ast::StmtAnnAssign
target: Expr

// ast::StmtAugAssign
target: Expr

// Extract Name nodes: Expr::Name(ExprName { id, .. }) -> id
```

### 3. For Loop Targets
```rust
// ast::StmtFor, ast::StmtAsyncFor
target: Expr  // Can be Name, Tuple, List

// Extract Name nodes recursively from target
```

### 4. With Statement Targets
```rust
// ast::StmtWith, ast::StmtAsyncWith
items: Vec<WithItem> {
    context_expr: Expr,
    optional_vars: Option<Expr>,  // Extract Name from this
}
```

### 5. Exception Handler Names
```rust
// ast::ExceptHandler::ExceptHandler
name: Option<Identifier>  // The 'e' in 'except Error as e'
```

### 6. Import Aliases
```rust
// ast::StmtImport
names: Vec<Alias> {
    name: Identifier,
    asname: Option<Identifier>,  // Use asname if present, else name
}

// ast::StmtImportFrom
names: Vec<Alias>  // Same structure
```

## Name Extraction Algorithm

```rust
pub fn extract_names(expr: &Expr) -> Vec<String> {
    match expr {
        Expr::Name(ExprName { id, .. }) => vec![id.to_string()],

        Expr::Tuple(ExprTuple { elts, .. }) |
        Expr::List(ExprList { elts, .. }) => {
            elts.iter()
                .flat_map(|e| extract_names(e))
                .collect()
        }

        // Subscript/Attribute don't bind new names
        _ => vec![],
    }
}
```

## Exclusion Rules

### Exclude from renaming:
1. **Keywords**: All 35 Python keywords
2. **Builtins**: Common builtins (configurable list)
3. **Global declarations**: Names in `global` statements
4. **Nonlocal declarations**: Names in `nonlocal` statements
5. **Class-scoped names**: Do not process class bodies
6. **Single underscores**: `_` (convention for unused variables)
7. **Dunder names**: `__name__`, `__init__`, etc.

### Detection:
```rust
pub fn should_exclude(name: &str) -> bool {
    name == "_" ||
    name.starts_with("__") && name.ends_with("__") ||
    PYTHON_KEYWORDS.contains(&name)
}

pub fn collect_global_nonlocal(body: &[Stmt]) -> Vec<String> {
    body.iter()
        .filter_map(|stmt| match stmt {
            Stmt::Global(g) => Some(g.names.iter()),
            Stmt::Nonlocal(n) => Some(n.names.iter()),
            _ => None,
        })
        .flatten()
        .map(|id| id.to_string())
        .collect()
}
```

## Collection Algorithm

```rust
pub fn collect_function_bindings(func: &StmtFunctionDef) -> FunctionPlan {
    let mut bindings = Vec::new();
    let mut excluded = Vec::new();

    // 1. Collect global/nonlocal declarations
    let protected = collect_global_nonlocal(&func.body);
    excluded.extend(protected.clone());

    // 2. Collect parameters
    collect_params(&func.parameters, &mut bindings);

    // 3. Traverse body for assignments, loops, withs, excepts, imports
    collect_from_body(&func.body, &mut bindings, &protected);

    // 4. Remove excluded patterns
    bindings.retain(|name| !should_exclude(name) && !protected.contains(name));

    // 5. Sort for stability
    bindings.sort();
    bindings.dedup();

    // 6. Generate rename map
    let mut gen = ShortNameGen::new();
    let mut rename_map = HashMap::new();

    for name in &bindings {
        let short = gen.next(&PYTHON_KEYWORDS.iter().map(|s| s.to_string()).collect::<Vec<_>>());
        rename_map.insert(name.clone(), short);
    }

    FunctionPlan {
        name: func.name.to_string(),
        local_names: bindings,
        rename_map,
        excluded_names: excluded,
    }
}
```

## Scope Rules

### Include in function scope:
- Function parameters (all types)
- Assignment targets (direct names only, not attributes/subscripts)
- For/AsyncFor targets
- With/AsyncWith optional_vars
- ExceptHandler names
- Import/ImportFrom aliases (the asname or name)

### Exclude from function scope:
- Class definitions (process separately, not recursively)
- Nested function definitions (process separately)
- Global/nonlocal declared names
- Attribute access (obj.attr - only rename obj)
- Subscript access (obj[key] - only rename obj/key)

## Stable Function Order

Collect functions in source order:

```rust
pub fn collect_functions_stable(module: &ast::Mod) -> Vec<&StmtFunctionDef> {
    let mut funcs = Vec::new();

    match module {
        ast::Mod::Module(m) => visit_stmts_for_functions(&m.body, &mut funcs),
        ast::Mod::Expression(_) => {},
    }

    funcs  // Already in source order
}

fn visit_stmts_for_functions<'a>(
    stmts: &'a [Stmt],
    funcs: &mut Vec<&'a StmtFunctionDef>,
) {
    for stmt in stmts {
        match stmt {
            Stmt::FunctionDef(f) => funcs.push(f),
            Stmt::AsyncFunctionDef(f) => {
                // Convert async to sync representation if needed
            }
            Stmt::ClassDef(c) => {
                // Don't recurse into class bodies
            }
            // Don't recurse into nested scopes
            _ => {}
        }
    }
}
```

## Serialization Example

```json
{
  "functions": [
    {
      "name": "calculate",
      "local_names": ["result", "temp", "value"],
      "rename_map": {
        "result": "a",
        "temp": "b",
        "value": "c"
      },
      "excluded_names": ["global_config"]
    }
  ],
  "python_keywords": ["False", "None", "True", ...],
  "builtins": ["print", "len", "range", ...]
}
```

## Implementation Checklist

- [ ] Define `FunctionPlan` and `MinifyPlan` structs with serde
- [ ] Implement `ShortNameGen` with tests
- [ ] Create `PYTHON_KEYWORDS` constant
- [ ] Implement `extract_names()` for recursive name extraction
- [ ] Implement `should_exclude()` filter
- [ ] Implement `collect_global_nonlocal()`
- [ ] Implement parameter collection
- [ ] Implement body traversal for all binding forms
- [ ] Implement stable function ordering
- [ ] Add comprehensive tests for each AST node type
- [ ] Verify serialization round-trip

## Edge Cases

1. **Tuple unpacking**: `a, b = foo()` - extract both `a` and `b`
2. **Nested unpacking**: `a, (b, c) = foo()` - extract `a`, `b`, `c`
3. **Walrus operator**: `:=` creates bindings in expressions (handle carefully)
4. **List comprehension variables**: Lexically scoped, don't leak (skip)
5. **Match patterns**: Variable bindings in match cases (include)
6. **Type parameters** (3.12+): Generic type vars (include if present)

## Notes

- This design focuses on **planning** only - no AST rewriting
- Output is JSON-serializable for external tools
- Function order is deterministic (source position)
- Name collisions avoided by checking keywords in generator
- Class scope deliberately excluded (different minification strategy needed)

## References

- [pyminifier (liftoffsoftware)](https://github.com/liftoff/pyminifier)
- [TreeShaker (sclabs)](https://github.com/sclabs/treeshaker)
- [“Build a Python tree-shaker in Rust” (dev.to)](https://dev.to/georgepearse/build-a-python-tree-shaker-in-rust-2n4h)
- [“Crude Python tree-shaking for squeezing into AWS Lambda package size limits” (sam152)](https://dev.to/sam152/crude-python-tree-shaking-for-squeezing-into-aws-lambda-package-size-limits-357a)
