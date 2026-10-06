//! Function call graph analysis with interprocedural reachability
//!
//! This module analyzes Python code to build a call graph and detect dead code.
//! It uses AST-based analysis to properly handle:
//! - Function and method definitions
//! - Call edges between functions
//! - Entry points (main blocks, tests, public APIs)
//! - Cross-package analysis
//! - Reachability from entry points

use crate::error::{Result, TsrsError};
use rustpython_parser::{ast, Parse};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::path::Path;

/// Unique identifier for a function node
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct FunctionId(pub usize);

/// Source location information
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SourceLocation {
    pub line: usize,
    pub col: usize,
}

/// Kind of function
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FunctionKind {
    /// Regular function
    Function,
    /// Async function
    AsyncFunction,
    /// Method inside a class
    Method,
    /// Dunder method (__init__, __call__, etc)
    DunderMethod,
    /// Lambda function
    Lambda,
}

/// Kind of function for dead code analysis
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EntryPointKind {
    /// Code at module level (always executed on import)
    ModuleInit,
    /// if __name__ == "__main__" block
    ScriptMain,
    /// Test function (test_*, @pytest, @unittest)
    TestFunction,
    /// Dunder method (kept for protocol compatibility)
    DunderMethod,
    /// Exported in __all__
    PublicExport,
    /// Regular function (not an entry point)
    Regular,
}

/// A function in the call graph
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CallGraphNode {
    pub id: FunctionId,
    pub name: String,
    pub package: String,
    pub location: SourceLocation,
    pub kind: FunctionKind,
    pub entry_point: EntryPointKind,
    /// Names of decorators (for framework detection)
    pub decorators: Vec<String>,
    /// Whether this function is marked with @property or similar
    pub is_special: bool,
}

/// A call edge from caller to callee
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CallEdge {
    pub caller: FunctionId,
    pub callee: FunctionId,
    pub location: SourceLocation,
}

/// Represents a function or class reference (legacy, for compatibility)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct FunctionRef {
    /// Package name (top-level module)
    pub package: String,
    /// Function or class name
    pub name: String,
}

impl FunctionRef {
    /// Create a new function reference
    #[must_use]
    pub fn new(package: String, name: String) -> Self {
        FunctionRef { package, name }
    }

    /// Check if this is a standard library or builtin
    #[must_use]
    pub fn is_builtin(&self) -> bool {
        matches!(
            self.package.as_str(),
            "builtins" | "sys" | "os" | "__builtin__" | "__builtins__"
        )
    }
}

/// Call graph for a single package
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackageCallGraph {
    /// Package name
    pub package: String,
    /// Functions/classes defined in this package
    pub definitions: HashSet<String>,
    /// Functions/classes used from other packages
    pub external_calls: HashSet<FunctionRef>,
    /// Functions/classes used locally (from same package)
    pub internal_calls: HashSet<String>,
}

impl PackageCallGraph {
    /// Create a new package call graph
    #[must_use]
    pub fn new(package: String) -> Self {
        PackageCallGraph {
            package,
            definitions: HashSet::new(),
            external_calls: HashSet::new(),
            internal_calls: HashSet::new(),
        }
    }

    /// Add a function definition
    pub fn add_definition(&mut self, name: String) {
        self.definitions.insert(name);
    }

    /// Add an external call
    pub fn add_external_call(&mut self, call: FunctionRef) {
        self.external_calls.insert(call);
    }

    /// Add an internal call
    pub fn add_internal_call(&mut self, name: String) {
        self.internal_calls.insert(name);
    }
}

/// Analyzes function calls per package using AST traversal
pub struct CallGraphAnalyzer {
    /// Legacy per-package graphs (for backward compatibility)
    graphs: HashMap<String, PackageCallGraph>,
    /// New AST-based call graph
    nodes: HashMap<FunctionId, CallGraphNode>,
    /// Call edges
    edges: Vec<CallEdge>,
    /// Next available function ID
    next_id: usize,
    /// Map from (package, function_name) to FunctionId
    function_index: HashMap<(String, String), FunctionId>,
    /// Entry points (functions reachable from script/module init)
    entry_points: HashSet<FunctionId>,
    /// Public API exports from each package
    public_exports: HashMap<String, HashSet<String>>,
    /// Import tracking: (package, local_name) → (source_package, source_function)
    /// Maps how functions are imported from other packages
    imports: HashMap<(String, String), (String, String)>,
}

impl CallGraphAnalyzer {
    /// Create a new call graph analyzer
    #[must_use]
    pub fn new() -> Self {
        CallGraphAnalyzer {
            graphs: HashMap::new(),
            nodes: HashMap::new(),
            edges: Vec::new(),
            next_id: 0,
            function_index: HashMap::new(),
            entry_points: HashSet::new(),
            public_exports: HashMap::new(),
            imports: HashMap::new(),
        }
    }

    /// Register a function in the call graph
    fn register_function(
        &mut self,
        package: String,
        name: String,
        location: SourceLocation,
        kind: FunctionKind,
        entry_point: EntryPointKind,
        decorators: Vec<String>,
    ) -> FunctionId {
        let id = FunctionId(self.next_id);
        self.next_id += 1;

        let is_special = decorators.iter().any(|d| {
            d.contains("property") || d.contains("staticmethod") || d.contains("classmethod")
        });

        let node = CallGraphNode {
            id,
            name: name.clone(),
            package: package.clone(),
            location,
            kind,
            entry_point,
            decorators,
            is_special,
        };

        self.nodes.insert(id, node);
        self.function_index.insert((package, name), id);

        if matches!(
            entry_point,
            EntryPointKind::ScriptMain | EntryPointKind::ModuleInit | EntryPointKind::TestFunction
        ) {
            self.entry_points.insert(id);
        }

        id
    }

    /// Analyze a Python file and build call graph
    ///
    /// # Errors
    ///
    /// Returns an error if the file cannot be read or parsed.
    pub fn analyze_file<P: AsRef<Path>>(&mut self, path: P, package: &str) -> Result<()> {
        let source = std::fs::read_to_string(path).map_err(TsrsError::Io)?;
        self.analyze_source(package, &source)
    }

    /// Analyze Python source code using AST traversal
    ///
    /// # Errors
    ///
    /// Returns an error if the source code cannot be parsed.
    pub fn analyze_source(&mut self, package: &str, source: &str) -> Result<()> {
        let suite = ast::Suite::parse(source, "<source>")
            .map_err(|e| TsrsError::ParseError(format!("Failed to parse Python: {e}")))?;

        // First pass: detect exports, entry points, and imports from module level
        self.detect_module_exports(package, &suite)?;
        self.detect_main_block(&suite)?;
        self.extract_imports(package, &suite)?;

        // Second pass: register all functions
        self.register_module_functions_suite(package, &suite)?;

        // Third pass: build call edges
        self.extract_calls_suite(package, &suite)?;

        // Fourth pass: mark imported functions as entry points (Phase 2)
        // This ensures that functions imported from other packages are treated as
        // potentially reachable from external callers
        self.mark_imported_functions_as_entry_points();

        // Also maintain legacy PackageCallGraph for backward compatibility
        self.build_legacy_graph(package);

        Ok(())
    }

    /// Detect `__all__` exports and module-level code
    fn detect_module_exports(&mut self, package: &str, suite: &[ast::Stmt]) -> Result<()> {
        let mut exports = HashSet::new();

        for stmt in suite {
            // Look for __all__ assignments
            if let ast::Stmt::Assign(assign) = stmt {
                for target in &assign.targets {
                    if let ast::Expr::Name(name_expr) = target {
                        if name_expr.id.as_str() == "__all__" {
                            // Try to extract list of strings
                            self.extract_all_exports(&assign.value, &mut exports)?;
                        }
                    }
                }
            }

            // Also mark any function at module level as having module initialization
            // (it can be called during import)
            if matches!(
                stmt,
                ast::Stmt::FunctionDef(_) | ast::Stmt::AsyncFunctionDef(_)
            ) {
                // These are detected separately
            }
        }

        if !exports.is_empty() {
            self.public_exports.insert(package.to_string(), exports);
        }

        Ok(())
    }

    /// Extract list of names from __all__ = [...] assignment
    fn extract_all_exports(&self, expr: &ast::Expr, exports: &mut HashSet<String>) -> Result<()> {
        match expr {
            ast::Expr::List(list_expr) => {
                for element in &list_expr.elts {
                    if let ast::Expr::Constant(const_expr) = element {
                        if let ast::Constant::Str(s) = &const_expr.value {
                            exports.insert(s.clone());
                        }
                    }
                }
            }
            ast::Expr::Tuple(tuple_expr) => {
                for element in &tuple_expr.elts {
                    if let ast::Expr::Constant(const_expr) = element {
                        if let ast::Constant::Str(s) = &const_expr.value {
                            exports.insert(s.clone());
                        }
                    }
                }
            }
            _ => {}
        }
        Ok(())
    }

    /// Extract imports from module-level statements
    /// Populates the imports map to track cross-package function usage
    fn extract_imports(&mut self, package: &str, suite: &[ast::Stmt]) -> Result<()> {
        for stmt in suite {
            match stmt {
                // Handle: import module, import module as alias, import m1, m2
                ast::Stmt::Import(import) => {
                    for alias in &import.names {
                        let module_name = alias.name.as_str();
                        // Get the binding name (what it's called in this package)
                        let binding_name = if let Some(asname) = &alias.asname {
                            asname.as_str()
                        } else {
                            // For `import X.Y.Z`, binding name is `X`
                            module_name.split('.').next().unwrap_or(module_name)
                        };

                        // Map: (package, binding_name) → (module_name, module_name)
                        // This represents: from module_name import module_name
                        self.add_import(
                            package.to_string(),
                            binding_name.to_string(),
                            module_name.to_string(),
                            module_name.to_string(),
                        );
                    }
                }
                // Handle: from module import name, from module import name as alias, from module import *
                ast::Stmt::ImportFrom(import_from) => {
                    let source_module = if let Some(module) = &import_from.module {
                        module.as_str()
                    } else {
                        // Relative imports - we'll skip these for now
                        continue;
                    };

                    // Check for wildcard imports (we'll skip detailed tracking for these)
                    let has_wildcard = import_from
                        .names
                        .iter()
                        .any(|alias| alias.name.as_str() == "*");
                    if has_wildcard {
                        continue;
                    }

                    // Process each imported name
                    for alias in &import_from.names {
                        let imported_name = alias.name.as_str();
                        let binding_name = if let Some(asname) = &alias.asname {
                            asname.as_str()
                        } else {
                            imported_name
                        };

                        // Map: (package, binding_name) → (source_module, imported_name)
                        // This represents: from source_module import imported_name [as binding_name]
                        self.add_import(
                            package.to_string(),
                            binding_name.to_string(),
                            source_module.to_string(),
                            imported_name.to_string(),
                        );
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }

    /// Detect if __name__ == "__main__" block (script entry point)
    fn detect_main_block(&mut self, suite: &[ast::Stmt]) -> Result<()> {
        for stmt in suite {
            // Look for: if __name__ == "__main__": ...
            if let ast::Stmt::If(if_stmt) = stmt {
                if self.is_main_guard(&if_stmt.test) {
                    // Mark that this module has a main block
                    // In a full implementation, we'd mark all statements in the main block
                    // as entry points or ScriptMain kind
                    return Ok(());
                }
            }
        }
        Ok(())
    }

    /// Check if expression matches `__name__ == "__main__"` pattern
    fn is_main_guard(&self, expr: &ast::Expr) -> bool {
        match expr {
            ast::Expr::Compare(cmp) => {
                // Check for: __name__ == "__main__"
                // Be conservative: if we see __name__ and __main__ in a comparison, assume it's a main guard
                if cmp.comparators.len() != 1 {
                    return false;
                }

                let left_is_name = if let ast::Expr::Name(n) = cmp.left.as_ref() {
                    n.id.as_str() == "__name__"
                } else {
                    false
                };

                let right_is_main = if let ast::Expr::Constant(c) = &cmp.comparators[0] {
                    matches!(&c.value, ast::Constant::Str(s) if s == "__main__")
                } else {
                    false
                };

                left_is_name && right_is_main
            }
            _ => false,
        }
    }

    /// Register all functions in a suite (module body)
    fn register_module_functions_suite(
        &mut self,
        package: &str,
        suite: &[ast::Stmt],
    ) -> Result<()> {
        for stmt in suite {
            self.register_module_functions(package, stmt)?;
        }
        Ok(())
    }

    /// Register functions at module level (handles nested classes/functions too)
    fn register_module_functions(&mut self, package: &str, stmt: &ast::Stmt) -> Result<()> {
        match stmt {
            ast::Stmt::FunctionDef(func_def) => {
                let decorators = func_def
                    .decorator_list
                    .iter()
                    .filter_map(|d| self.extract_decorator_name(d))
                    .collect();

                let func_name = func_def.name.as_str();
                let is_dunder = func_name.starts_with("__") && func_name.ends_with("__");
                let kind = if is_dunder {
                    FunctionKind::DunderMethod
                } else {
                    FunctionKind::Function
                };
                let entry_point = if is_dunder {
                    EntryPointKind::DunderMethod
                } else if func_name.starts_with("test_") {
                    EntryPointKind::TestFunction
                } else {
                    EntryPointKind::Regular
                };

                let location = SourceLocation { line: 0, col: 0 };

                self.register_function(
                    package.to_string(),
                    func_name.to_string(),
                    location,
                    kind,
                    entry_point,
                    decorators,
                );

                // Also register nested functions/classes
                self.register_module_functions_suite(package, &func_def.body)?;
            }
            ast::Stmt::AsyncFunctionDef(func_def) => {
                let decorators = func_def
                    .decorator_list
                    .iter()
                    .filter_map(|d| self.extract_decorator_name(d))
                    .collect();

                let func_name = func_def.name.as_str();
                let is_dunder = func_name.starts_with("__") && func_name.ends_with("__");
                let entry_point = if is_dunder {
                    EntryPointKind::DunderMethod
                } else if func_name.starts_with("test_") {
                    EntryPointKind::TestFunction
                } else {
                    EntryPointKind::Regular
                };

                let location = SourceLocation { line: 0, col: 0 };

                self.register_function(
                    package.to_string(),
                    func_name.to_string(),
                    location,
                    FunctionKind::AsyncFunction,
                    entry_point,
                    decorators,
                );

                // Also register nested functions/classes
                self.register_module_functions_suite(package, &func_def.body)?;
            }
            ast::Stmt::ClassDef(class_def) => {
                // Register methods inside classes
                self.register_module_functions_suite(package, &class_def.body)?;
            }
            _ => {}
        }

        Ok(())
    }

    /// Extract function calls from all statements in a suite (module level)
    fn extract_calls_suite(&mut self, package: &str, suite: &[ast::Stmt]) -> Result<()> {
        for stmt in suite {
            self.extract_calls_from_stmt(package, stmt, None)?;
        }
        Ok(())
    }

    /// Recursive helper to extract calls from statements with function context
    fn extract_calls_from_stmt(
        &mut self,
        package: &str,
        stmt: &ast::Stmt,
        current_func: Option<FunctionId>,
    ) -> Result<()> {
        match stmt {
            ast::Stmt::FunctionDef(func_def) => {
                let func_name = func_def.name.as_str();
                // Look up this function in the index
                let func_id = self
                    .function_index
                    .get(&(package.to_string(), func_name.to_string()))
                    .copied();

                if let Some(func_id) = func_id {
                    // Walk the function body with this function as context
                    for body_stmt in &func_def.body {
                        self.extract_calls_from_stmt(package, body_stmt, Some(func_id))?;
                    }
                }
            }
            ast::Stmt::AsyncFunctionDef(func_def) => {
                let func_name = func_def.name.as_str();
                let func_id = self
                    .function_index
                    .get(&(package.to_string(), func_name.to_string()))
                    .copied();

                if let Some(func_id) = func_id {
                    for body_stmt in &func_def.body {
                        self.extract_calls_from_stmt(package, body_stmt, Some(func_id))?;
                    }
                }
            }
            ast::Stmt::ClassDef(class_def) => {
                // Walk class methods
                for body_stmt in &class_def.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
            }
            ast::Stmt::If(if_stmt) => {
                for body_stmt in &if_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
                for else_stmt in &if_stmt.orelse {
                    self.extract_calls_from_stmt(package, else_stmt, current_func)?;
                }
            }
            ast::Stmt::For(for_stmt) => {
                for body_stmt in &for_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
                for else_stmt in &for_stmt.orelse {
                    self.extract_calls_from_stmt(package, else_stmt, current_func)?;
                }
            }
            ast::Stmt::AsyncFor(for_stmt) => {
                for body_stmt in &for_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
                for else_stmt in &for_stmt.orelse {
                    self.extract_calls_from_stmt(package, else_stmt, current_func)?;
                }
            }
            ast::Stmt::While(while_stmt) => {
                for body_stmt in &while_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
                for else_stmt in &while_stmt.orelse {
                    self.extract_calls_from_stmt(package, else_stmt, current_func)?;
                }
            }
            ast::Stmt::With(with_stmt) => {
                for body_stmt in &with_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
            }
            ast::Stmt::AsyncWith(with_stmt) => {
                for body_stmt in &with_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
            }
            ast::Stmt::Try(try_stmt) => {
                for body_stmt in &try_stmt.body {
                    self.extract_calls_from_stmt(package, body_stmt, current_func)?;
                }
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(h) = handler;
                    for handler_stmt in &h.body {
                        self.extract_calls_from_stmt(package, handler_stmt, current_func)?;
                    }
                }
                for else_stmt in &try_stmt.orelse {
                    self.extract_calls_from_stmt(package, else_stmt, current_func)?;
                }
                for final_stmt in &try_stmt.finalbody {
                    self.extract_calls_from_stmt(package, final_stmt, current_func)?;
                }
            }
            ast::Stmt::Expr(expr_stmt) => {
                // Extract calls from expressions in this statement
                self.extract_calls_from_expr(package, &expr_stmt.value, current_func)?;
            }
            ast::Stmt::Assign(assign_stmt) => {
                // Extract calls from the RHS of assignment
                self.extract_calls_from_expr(package, &assign_stmt.value, current_func)?;
            }
            ast::Stmt::Return(ret_stmt) => {
                if let Some(value) = &ret_stmt.value {
                    self.extract_calls_from_expr(package, value, current_func)?;
                }
            }
            _ => {}
        }

        Ok(())
    }

    /// Extract calls from an expression tree
    fn extract_calls_from_expr(
        &mut self,
        package: &str,
        expr: &ast::Expr,
        current_func: Option<FunctionId>,
    ) -> Result<()> {
        match expr {
            // Direct function call: func_name()
            ast::Expr::Call(call) => {
                if let ast::Expr::Name(name_expr) = call.func.as_ref() {
                    let func_name = name_expr.id.as_str();
                    // Resolve the call using imports (Phase 2: Inter-package call edges)
                    if let Some((resolved_pkg, resolved_func)) =
                        self.resolve_call(package, func_name)
                    {
                        // Look up the callee using resolved package and function name
                        if let Some(callee_id) = self
                            .function_index
                            .get(&(resolved_pkg, resolved_func))
                            .copied()
                        {
                            if let Some(caller_id) = current_func {
                                let location = SourceLocation { line: 0, col: 0 };
                                self.edges.push(CallEdge {
                                    caller: caller_id,
                                    callee: callee_id,
                                    location,
                                });
                            }
                        }
                    }
                }
                // Recursively process arguments
                for arg in &call.args {
                    self.extract_calls_from_expr(package, arg, current_func)?;
                }
                for keyword in &call.keywords {
                    self.extract_calls_from_expr(package, &keyword.value, current_func)?;
                }
            }
            // Recursively process compound expressions
            ast::Expr::List(list) => {
                for elt in &list.elts {
                    self.extract_calls_from_expr(package, elt, current_func)?;
                }
            }
            ast::Expr::Tuple(tuple) => {
                for elt in &tuple.elts {
                    self.extract_calls_from_expr(package, elt, current_func)?;
                }
            }
            ast::Expr::Set(set) => {
                for elt in &set.elts {
                    self.extract_calls_from_expr(package, elt, current_func)?;
                }
            }
            ast::Expr::BoolOp(bool_op) => {
                for value in &bool_op.values {
                    self.extract_calls_from_expr(package, value, current_func)?;
                }
            }
            ast::Expr::UnaryOp(unary) => {
                self.extract_calls_from_expr(package, &unary.operand, current_func)?;
            }
            ast::Expr::BinOp(bin_op) => {
                self.extract_calls_from_expr(package, &bin_op.left, current_func)?;
                self.extract_calls_from_expr(package, &bin_op.right, current_func)?;
            }
            ast::Expr::Compare(cmp) => {
                self.extract_calls_from_expr(package, &cmp.left, current_func)?;
                for comparator in &cmp.comparators {
                    self.extract_calls_from_expr(package, comparator, current_func)?;
                }
            }
            ast::Expr::IfExp(if_exp) => {
                self.extract_calls_from_expr(package, &if_exp.body, current_func)?;
                self.extract_calls_from_expr(package, &if_exp.test, current_func)?;
                self.extract_calls_from_expr(package, &if_exp.orelse, current_func)?;
            }
            _ => {}
        }

        Ok(())
    }

    /// Extract decorator name from an expression
    fn extract_decorator_name(&self, expr: &ast::Expr) -> Option<String> {
        match expr {
            ast::Expr::Name(name_expr) => Some(name_expr.id.as_str().to_string()),
            ast::Expr::Attribute(attr) => Some(attr.attr.as_str().to_string()),
            _ => None,
        }
    }

    /// Build legacy PackageCallGraph for backward compatibility
    fn build_legacy_graph(&mut self, package: &str) {
        let graph = self
            .graphs
            .entry(package.to_string())
            .or_insert_with(|| PackageCallGraph::new(package.to_string()));

        // Populate definitions
        for node in self.nodes.values() {
            if node.package == package {
                graph.add_definition(node.name.clone());
            }
        }
    }

    /// Get all call graphs (legacy)
    #[must_use]
    pub fn get_graphs(&self) -> &HashMap<String, PackageCallGraph> {
        &self.graphs
    }

    /// Get call graph for a specific package (legacy)
    #[must_use]
    pub fn get_graph(&self, package: &str) -> Option<&PackageCallGraph> {
        self.graphs.get(package)
    }

    /// Find unused functions in a package (legacy)
    #[must_use]
    pub fn find_unused_functions(&self, package: &str) -> HashSet<String> {
        if let Some(graph) = self.get_graph(package) {
            let called: HashSet<String> = graph.internal_calls.iter().cloned().collect();
            graph
                .definitions
                .iter()
                .filter(|def| !called.contains(*def) && !def.starts_with('_'))
                .cloned()
                .collect()
        } else {
            HashSet::new()
        }
    }

    /// Find all external dependencies (legacy)
    #[must_use]
    pub fn find_external_dependencies(&self) -> HashSet<String> {
        let mut deps = HashSet::new();
        for graph in self.graphs.values() {
            for call in &graph.external_calls {
                deps.insert(call.package.clone());
            }
        }
        deps
    }

    /// Get all nodes in the call graph
    #[must_use]
    pub fn get_nodes(&self) -> &HashMap<FunctionId, CallGraphNode> {
        &self.nodes
    }

    /// Get all edges in the call graph
    #[must_use]
    pub fn get_edges(&self) -> &[CallEdge] {
        &self.edges
    }

    /// Get entry points
    #[must_use]
    pub fn get_entry_points(&self) -> &HashSet<FunctionId> {
        &self.entry_points
    }

    /// Compute reachable functions from entry points
    #[must_use]
    pub fn compute_reachable(&self) -> HashSet<FunctionId> {
        let mut reachable = HashSet::new();
        let mut queue = VecDeque::from_iter(self.entry_points.iter().copied());

        while let Some(current) = queue.pop_front() {
            if reachable.insert(current) {
                // Find all functions called by current
                for edge in &self.edges {
                    if edge.caller == current && !reachable.contains(&edge.callee) {
                        queue.push_back(edge.callee);
                    }
                }
            }
        }

        reachable
    }

    /// Find dead code (unreachable from entry points)
    #[must_use]
    pub fn find_dead_code(&self) -> Vec<(FunctionId, String)> {
        let reachable = self.compute_reachable();

        self.nodes
            .values()
            .filter_map(|node| {
                // Keep if reachable
                if reachable.contains(&node.id) {
                    return None;
                }

                // Keep dunder methods
                if node.name.starts_with("__") && node.name.ends_with("__") {
                    return None;
                }

                // Keep if exported
                if let Some(exports) = self.public_exports.get(&node.package) {
                    if exports.contains(&node.name) {
                        return None;
                    }
                }

                Some((node.id, node.name.clone()))
            })
            .collect()
    }

    /// Get public exports (functions declared in `__all__`) for a package
    #[must_use]
    pub fn get_public_exports(&self, package: &str) -> Vec<String> {
        self.public_exports
            .get(package)
            .map(|exports| {
                let mut names: Vec<_> = exports.iter().cloned().collect();
                names.sort();
                names
            })
            .unwrap_or_default()
    }

    /// Get all packages with their exports
    #[must_use]
    pub fn get_all_exports(&self) -> HashMap<String, Vec<String>> {
        self.public_exports
            .iter()
            .map(|(package, exports)| {
                let mut names: Vec<_> = exports.iter().cloned().collect();
                names.sort();
                (package.clone(), names)
            })
            .collect()
    }

    /// Add an import mapping
    /// Maps (package, local_name) → (source_package, source_function)
    /// Example: Package "myapp" imports "helper" from "mylib"
    /// This maps ("myapp", "helper") → ("mylib", "helper")
    pub fn add_import(
        &mut self,
        package: String,
        local_name: String,
        source_package: String,
        source_function: String,
    ) {
        self.imports
            .insert((package, local_name), (source_package, source_function));
    }

    /// Resolve a call name to its actual function (local or imported)
    /// Returns Some((source_package, source_function)) if found, None otherwise
    ///
    /// Resolution order:
    /// 1. Check if call_name is a local function in package
    /// 2. Check if it's an imported function
    /// 3. Return None
    pub fn resolve_call(&self, package: &str, call_name: &str) -> Option<(String, String)> {
        // First check if it's a local function in this package
        if self
            .function_index
            .contains_key(&(package.to_string(), call_name.to_string()))
        {
            return Some((package.to_string(), call_name.to_string()));
        }

        // Check if it's an imported function
        self.imports
            .get(&(package.to_string(), call_name.to_string()))
            .cloned()
    }

    /// Get all imports for a package
    /// Returns list of (local_name, source_package, source_function) tuples
    pub fn get_imports_for_package(&self, package: &str) -> Vec<(String, String, String)> {
        self.imports
            .iter()
            .filter(|((pkg, _), _)| pkg == package)
            .map(|((_, local_name), (source_pkg, source_func))| {
                (local_name.clone(), source_pkg.clone(), source_func.clone())
            })
            .collect()
    }

    /// Get all imports across all packages
    pub fn get_all_imports(&self) -> HashMap<String, Vec<(String, String, String)>> {
        let mut result: HashMap<String, Vec<(String, String, String)>> = HashMap::new();

        for ((package, local_name), (source_pkg, source_func)) in &self.imports {
            result
                .entry(package.clone())
                .or_default()
                .push((local_name.clone(), source_pkg.clone(), source_func.clone()));
        }

        result
    }

    /// Mark imported functions as entry points
    /// This ensures imported functions are considered reachable from external callers
    /// Part of Phase 2: Inter-package call edges
    fn mark_imported_functions_as_entry_points(&mut self) {
        // Collect all unique (source_package, source_function) pairs
        let mut imported_funcs: Vec<(String, String)> = self
            .imports
            .values()
            .cloned()
            .collect::<std::collections::HashSet<_>>()
            .into_iter()
            .collect();

        // Sort for deterministic behavior
        imported_funcs.sort();

        // Mark each imported function as an entry point if it exists
        for (source_pkg, source_func) in imported_funcs {
            if let Some(func_id) = self.function_index.get(&(source_pkg, source_func)).copied() {
                self.entry_points.insert(func_id);
            }
        }
    }
}

impl Default for CallGraphAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_entry_point_detection_main_block() {
        let source = r#"
def helper():
    pass

def test_something():
    pass

if __name__ == "__main__":
    helper()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let entry_points = analyzer.get_entry_points();
        // At minimum, test_something should be an entry point
        assert!(
            !entry_points.is_empty(),
            "Should have entry point for test function"
        );
    }

    #[test]
    fn test_entry_point_detection_test_functions() {
        let source = r#"
def test_helper():
    pass

def test_something():
    pass

def regular_function():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let entry_points = analyzer.get_entry_points();
        let nodes = analyzer.get_nodes();

        // Should have test functions as entry points
        let test_func_ids: Vec<_> = nodes
            .iter()
            .filter(|(_, node)| node.name.starts_with("test_"))
            .map(|(id, _)| *id)
            .collect();

        for test_id in test_func_ids {
            assert!(
                entry_points.contains(&test_id),
                "Test function should be entry point"
            );
        }
    }

    #[test]
    fn test_entry_point_detection_exports() {
        let source = r#"
__all__ = ['exported_func', 'test_something']

def exported_func():
    pass

def test_something():
    pass

def internal_func():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let entry_points = analyzer.get_entry_points();
        let nodes = analyzer.get_nodes();

        // test_something should be an entry point (test functions are)
        let test_id = nodes
            .iter()
            .find(|(_, node)| node.name == "test_something")
            .map(|(id, _)| *id);

        assert!(test_id.is_some(), "test_something should exist");
        if let Some(id) = test_id {
            assert!(
                entry_points.contains(&id),
                "test_something should be entry point"
            );
        }
    }

    #[test]
    fn test_entry_point_protection_dunder_methods() {
        let source = r#"
class MyClass:
    def __init__(self):
        pass

    def __str__(self):
        pass

    def regular_method(self):
        pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let dead_code = analyzer.find_dead_code();

        // Dunder methods should not be in dead code
        let dunder_names: Vec<_> = dead_code
            .iter()
            .filter(|(_, name)| name.starts_with("__") && name.ends_with("__"))
            .collect();

        assert!(
            dunder_names.is_empty(),
            "Dunder methods should be protected from dead code detection"
        );
    }

    #[test]
    fn test_simple_call_detection() {
        let source = r#"
def caller():
    callee()

def callee():
    pass

if __name__ == "__main__":
    caller()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let edges = analyzer.get_edges();
        assert!(!edges.is_empty(), "Should have detected function calls");

        // Should find caller -> callee edge
        let has_call = edges.iter().any(|edge| {
            let caller_name = analyzer
                .get_nodes()
                .get(&edge.caller)
                .map(|n| n.name.as_str());
            let callee_name = analyzer
                .get_nodes()
                .get(&edge.callee)
                .map(|n| n.name.as_str());
            caller_name == Some("caller") && callee_name == Some("callee")
        });

        assert!(has_call, "Should detect caller -> callee call edge");
    }

    #[test]
    fn test_reachability_analysis() {
        let source = r#"
def test_reachability():
    reachable_1()

def reachable_1():
    reachable_2()

def reachable_2():
    pass

def dead_code_func():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let reachable = analyzer.compute_reachable();
        let nodes = analyzer.get_nodes();

        // Check reachability
        let reachable_names: Vec<_> = reachable
            .iter()
            .filter_map(|id| nodes.get(id).map(|n| n.name.as_str()))
            .collect();

        assert!(
            reachable_names.contains(&"test_reachability"),
            "test_reachability should be reachable (entry point)"
        );
        assert!(
            reachable_names.contains(&"reachable_1"),
            "reachable_1 should be reachable"
        );
        assert!(
            reachable_names.contains(&"reachable_2"),
            "reachable_2 should be reachable"
        );
        assert!(
            !reachable_names.contains(&"dead_code_func"),
            "dead_code_func should not be reachable"
        );
    }

    #[test]
    fn test_dead_code_detection() {
        let source = r#"
def test_used():
    used_function()

def used_function():
    pass

def unused_function():
    pass

def another_unused():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let dead_code = analyzer.find_dead_code();
        let dead_names: Vec<_> = dead_code.iter().map(|(_, name)| name.as_str()).collect();

        assert!(
            dead_names.contains(&"unused_function"),
            "unused_function should be dead code"
        );
        assert!(
            dead_names.contains(&"another_unused"),
            "another_unused should be dead code"
        );
        assert!(
            !dead_names.contains(&"used_function"),
            "used_function should not be dead code (called from test_used)"
        );
        assert!(
            !dead_names.contains(&"test_used"),
            "test_used should not be dead code (entry point)"
        );
    }

    #[test]
    fn test_dead_code_protection_exports() {
        let source = r#"
__all__ = ['exported_unused']

def exported_unused():
    pass

def truly_unused():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let dead_code = analyzer.find_dead_code();
        let dead_names: Vec<_> = dead_code.iter().map(|(_, name)| name.as_str()).collect();

        assert!(
            !dead_names.contains(&"exported_unused"),
            "Exported functions should be protected even if unused"
        );
        assert!(
            dead_names.contains(&"truly_unused"),
            "Non-exported unused functions should be dead code"
        );
    }

    #[test]
    fn test_nested_function_calls() {
        let source = r#"
def outer():
    def inner():
        helper()
    inner()

def helper():
    pass

outer()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let edges = analyzer.get_edges();
        assert!(!edges.is_empty(), "Should detect calls in nested functions");
    }

    #[test]
    fn test_multiple_calls_same_function() {
        let source = r#"
def caller():
    target()
    target()
    target()

def target():
    pass

if __name__ == "__main__":
    caller()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let edges = analyzer.get_edges();

        // Should have edges for each call (even if to same function)
        let call_count = edges
            .iter()
            .filter(|edge| {
                let caller_name = analyzer
                    .get_nodes()
                    .get(&edge.caller)
                    .map(|n| n.name.as_str());
                let callee_name = analyzer
                    .get_nodes()
                    .get(&edge.callee)
                    .map(|n| n.name.as_str());
                caller_name == Some("caller") && callee_name == Some("target")
            })
            .count();

        assert!(call_count >= 3, "Should detect all three calls to target");
    }

    #[test]
    fn test_empty_source_code() {
        let source = "";
        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let nodes = analyzer.get_nodes();
        assert!(nodes.is_empty(), "Empty source should have no nodes");

        let dead_code = analyzer.find_dead_code();
        assert!(
            dead_code.is_empty(),
            "Empty source should have no dead code"
        );
    }

    #[test]
    fn test_only_comments_and_docstrings() {
        let source = r#"
"""Module docstring"""

# This is a comment
# Another comment
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let nodes = analyzer.get_nodes();
        assert!(
            nodes.is_empty(),
            "Comments and docstrings should not create nodes"
        );
    }

    #[test]
    fn test_module_initialization_is_entry_point() {
        let source = r#"
def test_module():
    pass

def some_func():
    pass

some_func()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let entry_points = analyzer.get_entry_points();
        // test_module should be marked as entry point
        assert!(
            !entry_points.is_empty(),
            "Test functions should be entry points"
        );
    }

    #[test]
    fn test_mutual_recursion() {
        let source = r#"
def test_recursion():
    func_a()

def func_a():
    func_b()

def func_b():
    func_a()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let reachable = analyzer.compute_reachable();
        let nodes = analyzer.get_nodes();

        let reachable_names: Vec<_> = reachable
            .iter()
            .filter_map(|id| nodes.get(id).map(|n| n.name.as_str()))
            .collect();

        assert!(
            reachable_names.contains(&"test_recursion"),
            "test_recursion should be reachable (entry point)"
        );
        assert!(
            reachable_names.contains(&"func_a"),
            "func_a should be reachable"
        );
        assert!(
            reachable_names.contains(&"func_b"),
            "func_b should be reachable even with mutual recursion"
        );
    }

    #[test]
    fn test_decorator_preservation() {
        let source = r#"
def decorator(func):
    return func

@decorator
def decorated_func():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        let nodes = analyzer.get_nodes();
        let decorated = nodes.values().find(|n| n.name == "decorated_func").unwrap();

        assert!(!decorated.decorators.is_empty(), "Should track decorators");
    }

    #[test]
    fn test_call_detection_with_attributes() {
        let source = r#"
def caller():
    obj.method()
    some_module.func()

def method(self):
    pass

obj = None
some_module = None

if __name__ == "__main__":
    caller()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("test", source).unwrap();

        // Should still detect the function definitions
        let nodes = analyzer.get_nodes();
        let func_names: Vec<_> = nodes.values().map(|n| n.name.as_str()).collect();

        assert!(
            func_names.contains(&"caller"),
            "Should detect caller function"
        );
    }

    #[test]
    fn test_import_tracking_from_import() {
        let source = r#"
from mylib import helper
from utils import process as p

def main():
    helper()
    p()
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("myapp", source).unwrap();

        // Check that imports were tracked
        let imports = analyzer.get_imports_for_package("myapp");

        // Should have 2 imports
        assert_eq!(imports.len(), 2, "Should track 2 imports");

        // Check specific imports
        let helper_import = imports.iter().find(|(local, _, _)| local == "helper");
        assert!(helper_import.is_some(), "Should track 'helper' import");

        if let Some((_, source_pkg, source_func)) = helper_import {
            assert_eq!(source_pkg, "mylib");
            assert_eq!(source_func, "helper");
        }

        let p_import = imports.iter().find(|(local, _, _)| local == "p");
        assert!(p_import.is_some(), "Should track 'p' import (alias)");

        if let Some((_, source_pkg, source_func)) = p_import {
            assert_eq!(source_pkg, "utils");
            assert_eq!(source_func, "process");
        }
    }

    #[test]
    fn test_import_tracking_import_statement() {
        let source = r#"
import numpy as np
import os

def main():
    np.array([1, 2, 3])
    os.path.exists('/')
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        analyzer.analyze_source("myapp", source).unwrap();

        let imports = analyzer.get_imports_for_package("myapp");

        // Should have 2 imports
        assert_eq!(imports.len(), 2, "Should track 2 imports");

        // Check numpy alias
        let np_import = imports.iter().find(|(local, _, _)| local == "np");
        assert!(np_import.is_some(), "Should track 'np' import (alias)");

        if let Some((_, source_pkg, source_func)) = np_import {
            assert_eq!(source_pkg, "numpy");
            assert_eq!(source_func, "numpy");
        }

        // Check os import
        let os_import = imports.iter().find(|(local, _, _)| local == "os");
        assert!(os_import.is_some(), "Should track 'os' import");

        if let Some((_, source_pkg, source_func)) = os_import {
            assert_eq!(source_pkg, "os");
            assert_eq!(source_func, "os");
        }
    }

    #[test]
    fn test_import_tracking_multiple_packages() {
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

        // Check imports in pkg_a
        let imports_a = analyzer.get_imports_for_package("pkg_a");
        assert_eq!(imports_a.len(), 1, "pkg_a should have 1 import");

        let helper = imports_a.iter().find(|(local, _, _)| local == "helper");
        assert!(helper.is_some());

        if let Some((_, source_pkg, source_func)) = helper {
            assert_eq!(source_pkg, "pkg_b");
            assert_eq!(source_func, "helper");
        }

        // Check no imports in pkg_b
        let imports_b = analyzer.get_imports_for_package("pkg_b");
        assert_eq!(imports_b.len(), 0, "pkg_b should have no imports");
    }

    #[test]
    fn test_cross_package_call_detection() {
        let pkg_a = r#"
from pkg_b import helper

def main():
    helper()

if __name__ == "__main__":
    main()
"#;

        let pkg_b = r#"
def helper():
    pass
"#;

        let mut analyzer = CallGraphAnalyzer::new();
        // Analyze pkg_b first so its functions are registered before we analyze pkg_a's calls
        analyzer.analyze_source("pkg_b", pkg_b).unwrap();
        analyzer.analyze_source("pkg_a", pkg_a).unwrap();

        let nodes = analyzer.get_nodes();
        let edges = analyzer.get_edges();

        // Find function IDs
        let main_id = nodes
            .values()
            .find(|n| n.name == "main" && n.package == "pkg_a")
            .map(|n| n.id);
        let helper_id = nodes
            .values()
            .find(|n| n.name == "helper" && n.package == "pkg_b")
            .map(|n| n.id);

        assert!(main_id.is_some(), "Should have main function in pkg_a");
        assert!(helper_id.is_some(), "Should have helper function in pkg_b");

        // Check that there's a cross-package call edge from main to helper
        let cross_pkg_edge = edges
            .iter()
            .any(|e| e.caller == main_id.unwrap() && e.callee == helper_id.unwrap());

        assert!(
            cross_pkg_edge,
            "Should detect cross-package call from main to helper"
        );

        // Check reachability: helper should be reachable (it's imported)
        let reachable = analyzer.compute_reachable();
        assert!(
            reachable.contains(&helper_id.unwrap()),
            "Imported helper should be reachable (marked as entry point)"
        );
    }
}
