//! Import tracking and collection

use crate::error::{Result, TsrsError};
use rustpython_parser::{ast, Parse};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::Path;

/// Set of unique imports
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ImportSet {
    /// Imported module names
    pub imports: HashSet<String>,
}

/// Detailed information about a single import statement
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DetailedImport {
    /// The module being imported from (e.g., "numpy", "os.path")
    pub module: String,
    /// Specific symbols imported from the module (empty for `import X`)
    pub symbols: Vec<String>,
    /// Whether this is a wildcard import (`from module import *`)
    pub is_wildcard: bool,
    /// The original name used to bind this in the importing scope
    /// For `from X import Y as Z`, this would be `Z`
    /// For `import X as Y`, this would be `Y`
    /// For `import X`, this would be `X`
    pub binding_name: String,
    /// Line number where the import statement appears (1-indexed)
    pub lineno: usize,
}

/// Information about symbol usage in the code
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolUsage {
    /// The symbol name being used
    pub symbol: String,
    /// The module it's imported from
    pub module: String,
    /// Line numbers where this symbol is used (1-indexed)
    pub usage_locations: Vec<usize>,
}

impl ImportSet {
    /// Create a new import set
    #[must_use]
    pub fn new() -> Self {
        ImportSet {
            imports: HashSet::new(),
        }
    }

    /// Add an import
    pub fn add(&mut self, import: String) {
        self.imports.insert(import);
    }

    /// Get all imports
    #[must_use]
    pub fn get_imports(&self) -> Vec<String> {
        let mut imports: Vec<_> = self.imports.iter().cloned().collect();
        imports.sort();
        imports
    }
}

/// Collects imports from Python code via AST traversal
pub struct ImportCollector {
    imports: ImportSet,
    /// Detailed imports with symbol-level information
    detailed_imports: Vec<DetailedImport>,
    /// Mapping from binding names to their detailed import information
    binding_to_import: HashMap<String, DetailedImport>,
    /// Source code for symbol usage analysis
    source: Option<String>,
}

impl ImportCollector {
    /// Create a new import collector
    #[must_use]
    pub fn new() -> Self {
        ImportCollector {
            imports: ImportSet::new(),
            detailed_imports: Vec::new(),
            binding_to_import: HashMap::new(),
            source: None,
        }
    }

    /// Parse a Python file and extract imports
    ///
    /// # Errors
    ///
    /// Returns an error if the file cannot be read or parsed.
    pub fn collect_from_file<P: AsRef<Path>>(&mut self, path: P) -> Result<()> {
        let path_ref = path.as_ref();
        let source = std::fs::read_to_string(path_ref).map_err(TsrsError::Io)?;
        let filename = path_ref.display().to_string();
        self.collect_from_source_with_name(&source, &filename)?;
        Ok(())
    }

    /// Parse Python source code and extract imports
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed.
    pub fn collect_from_source(&mut self, source: &str) -> Result<()> {
        self.collect_from_source_with_name(source, "<memory>")?;
        Ok(())
    }

    fn collect_from_source_with_name(&mut self, source: &str, filename: &str) -> Result<()> {
        self.source = Some(source.to_string());
        let suite = ast::Suite::parse(source, filename)
            .map_err(|err| TsrsError::ParseError(err.to_string()))?;
        self.visit_suite(&suite);
        Ok(())
    }

    fn visit_suite(&mut self, suite: &[ast::Stmt]) {
        for stmt in suite {
            self.visit_stmt(stmt);
        }
    }

    fn visit_stmt(&mut self, stmt: &ast::Stmt) {
        match stmt {
            ast::Stmt::Import(import) => self.handle_import(import),
            ast::Stmt::ImportFrom(import_from) => self.handle_import_from(import_from),
            ast::Stmt::FunctionDef(function_def) => self.visit_suite(&function_def.body),
            ast::Stmt::AsyncFunctionDef(function_def) => self.visit_suite(&function_def.body),
            ast::Stmt::ClassDef(class_def) => self.visit_suite(&class_def.body),
            ast::Stmt::For(for_stmt) => {
                self.visit_suite(&for_stmt.body);
                self.visit_suite(&for_stmt.orelse);
            }
            ast::Stmt::AsyncFor(for_stmt) => {
                self.visit_suite(&for_stmt.body);
                self.visit_suite(&for_stmt.orelse);
            }
            ast::Stmt::While(while_stmt) => {
                self.visit_suite(&while_stmt.body);
                self.visit_suite(&while_stmt.orelse);
            }
            ast::Stmt::If(if_stmt) => {
                self.visit_suite(&if_stmt.body);
                self.visit_suite(&if_stmt.orelse);
            }
            ast::Stmt::With(with_stmt) => self.visit_suite(&with_stmt.body),
            ast::Stmt::AsyncWith(with_stmt) => self.visit_suite(&with_stmt.body),
            ast::Stmt::Try(try_stmt) => {
                self.visit_suite(&try_stmt.body);
                self.visit_suite(&try_stmt.orelse);
                self.visit_suite(&try_stmt.finalbody);
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    self.visit_suite(&handler.body);
                }
            }
            ast::Stmt::TryStar(try_stmt) => {
                self.visit_suite(&try_stmt.body);
                self.visit_suite(&try_stmt.orelse);
                self.visit_suite(&try_stmt.finalbody);
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    self.visit_suite(&handler.body);
                }
            }
            ast::Stmt::Match(match_stmt) => {
                for case in &match_stmt.cases {
                    self.visit_suite(&case.body);
                }
            }
            _ => {}
        }
    }

    fn handle_import(&mut self, import: &ast::StmtImport) {
        for alias in &import.names {
            let module_name = alias.name.as_str().to_string();
            self.add_identifier_name(&alias.name);

            // For `import X` or `import X as Y`
            let binding_name = if let Some(asname) = &alias.asname {
                asname.as_str().to_string()
            } else {
                // For `import X.Y.Z`, binding name is `X`
                module_name.split('.').next().unwrap_or("").to_string()
            };

            if !binding_name.is_empty() {
                let detailed = DetailedImport {
                    module: module_name,
                    symbols: vec![],
                    is_wildcard: false,
                    binding_name: binding_name.clone(),
                    lineno: 0,
                };
                self.detailed_imports.push(detailed.clone());
                self.binding_to_import.insert(binding_name, detailed);
            }
        }
    }

    fn handle_import_from(&mut self, import_from: &ast::StmtImportFrom) {
        let level = import_from.level.as_ref().map_or(0, ast::Int::to_u32);

        if level > 0 {
            // Relative imports refer to the current package; skip to avoid
            // incorrectly attributing them to external dependencies.
            return;
        }

        if let Some(module) = &import_from.module {
            self.add_identifier_name(module);

            // For `from X import Y` or `from X import *`
            let module_str = module.as_str().to_string();
            let is_wildcard =
                import_from.names.len() == 1 && import_from.names[0].name.as_str() == "*";

            if is_wildcard {
                // `from module import *` - binding is the module itself
                let detailed = DetailedImport {
                    module: module_str.clone(),
                    symbols: vec![],
                    is_wildcard: true,
                    binding_name: module_str.clone(),
                    lineno: 0,
                };
                self.detailed_imports.push(detailed.clone());
                self.binding_to_import.insert(module_str, detailed);
            } else {
                // `from module import a, b, c` or `from module import a as x`
                for alias in &import_from.names {
                    let symbol_name = alias.name.as_str().to_string();
                    let binding_name = if let Some(asname) = &alias.asname {
                        asname.as_str().to_string()
                    } else {
                        symbol_name.clone()
                    };

                    let detailed = DetailedImport {
                        module: module_str.clone(),
                        symbols: vec![symbol_name],
                        is_wildcard: false,
                        binding_name: binding_name.clone(),
                        lineno: 0,
                    };
                    self.detailed_imports.push(detailed.clone());
                    self.binding_to_import.insert(binding_name, detailed);
                }
            }
        } else {
            // Absolute import without explicit module (rare). Fall back to alias names.
            for alias in &import_from.names {
                self.add_identifier_name(&alias.name);
            }
        }
    }

    fn add_identifier_name(&mut self, identifier: &ast::Identifier) {
        self.add_module_name(identifier.as_str());
    }

    fn add_module_name(&mut self, name: &str) {
        let top_level = name.split('.').next().unwrap_or(name);
        if top_level.is_empty() || top_level == "*" {
            return;
        }
        self.imports.add(top_level.to_string());
    }

    /// Get collected imports
    #[must_use]
    pub fn get_imports(&self) -> ImportSet {
        self.imports.clone()
    }

    /// Get detailed imports with symbol-level information
    ///
    /// # Returns
    /// A vector of `DetailedImport` structs, one for each import statement or symbol imported.
    #[must_use]
    pub fn get_detailed_imports(&self) -> Vec<DetailedImport> {
        self.detailed_imports.clone()
    }

    /// Get detailed import information by binding name
    ///
    /// This is useful for looking up an imported symbol by its name in the current scope.
    /// For example, if the code has `import numpy as np`, you can look up `"np"` to get
    /// the DetailedImport with module `"numpy"`.
    #[must_use]
    pub fn get_import_by_binding(&self, binding_name: &str) -> Option<DetailedImport> {
        self.binding_to_import.get(binding_name).cloned()
    }

    /// Analyze which imports are actually used in the source code
    ///
    /// This method scans the source code to find all Name references and determines
    /// which imports are actually used. Returns a map from binding name to a list of
    /// line numbers where that binding is used.
    ///
    /// # Returns
    /// A HashMap where keys are binding names and values are vectors of line numbers
    /// where the binding is used (1-indexed).
    ///
    /// # Note
    /// This only finds Name references. It doesn't distinguish between different uses
    /// (e.g., function call vs attribute access). This is intentional for conservatism.
    pub fn analyze_symbol_usage(&self) -> Result<HashMap<String, Vec<usize>>> {
        let source = self.source.as_ref().ok_or_else(|| {
            TsrsError::AnalysisError("no source available for symbol usage analysis".into())
        })?;

        let mut usage: HashMap<String, Vec<usize>> = HashMap::new();

        // Parse the source to get the AST
        let suite = ast::Suite::parse(source, "<analyze>")
            .map_err(|err| TsrsError::ParseError(err.to_string()))?;

        // Visit all statements to find Name references
        let mut visitor = NameVisitor::new();
        visitor.visit_suite(&suite);

        // Cross-reference discovered names with imports
        for (name, locations) in visitor.names {
            // Check if this name is an imported binding
            if self.binding_to_import.contains_key(&name) {
                usage.insert(name, locations);
            }
        }

        Ok(usage)
    }

    /// Get all symbols imported from a specific module
    ///
    /// # Arguments
    /// * `module` - The module name (e.g., "numpy", "os.path")
    ///
    /// # Returns
    /// A vector of symbol names imported from that module
    #[must_use]
    pub fn get_symbols_from_module(&self, module: &str) -> Vec<String> {
        let mut symbols = Vec::new();
        for import in &self.detailed_imports {
            if import.module == module && !import.is_wildcard && !import.symbols.is_empty() {
                symbols.extend(import.symbols.clone());
            }
        }
        symbols.sort();
        symbols.dedup();
        symbols
    }

    /// Check if a specific module is imported via wildcard
    ///
    /// # Arguments
    /// * `module` - The module name
    ///
    /// # Returns
    /// true if there's a `from module import *` statement
    #[must_use]
    pub fn has_wildcard_import(&self, module: &str) -> bool {
        self.detailed_imports
            .iter()
            .any(|imp| imp.module == module && imp.is_wildcard)
    }
}

/// Helper visitor for finding Name references in the AST
struct NameVisitor {
    /// Map from name to list of line numbers where it's used
    names: HashMap<String, Vec<usize>>,
}

impl NameVisitor {
    fn new() -> Self {
        NameVisitor {
            names: HashMap::new(),
        }
    }

    fn visit_suite(&mut self, suite: &[ast::Stmt]) {
        for stmt in suite {
            self.visit_stmt(stmt);
        }
    }

    fn visit_stmt(&mut self, stmt: &ast::Stmt) {
        match stmt {
            ast::Stmt::Expr(expr_stmt) => self.visit_expr(&expr_stmt.value),
            ast::Stmt::Assign(assign) => {
                self.visit_expr(&assign.value);
                for target in &assign.targets {
                    self.visit_expr(target);
                }
            }
            ast::Stmt::AugAssign(aug_assign) => {
                self.visit_expr(&aug_assign.value);
                self.visit_expr(&aug_assign.target);
            }
            ast::Stmt::For(for_stmt) => {
                self.visit_expr(&for_stmt.target);
                self.visit_expr(&for_stmt.iter);
                self.visit_suite(&for_stmt.body);
                self.visit_suite(&for_stmt.orelse);
            }
            ast::Stmt::AsyncFor(for_stmt) => {
                self.visit_expr(&for_stmt.target);
                self.visit_expr(&for_stmt.iter);
                self.visit_suite(&for_stmt.body);
                self.visit_suite(&for_stmt.orelse);
            }
            ast::Stmt::While(while_stmt) => {
                self.visit_expr(&while_stmt.test);
                self.visit_suite(&while_stmt.body);
                self.visit_suite(&while_stmt.orelse);
            }
            ast::Stmt::If(if_stmt) => {
                self.visit_expr(&if_stmt.test);
                self.visit_suite(&if_stmt.body);
                self.visit_suite(&if_stmt.orelse);
            }
            ast::Stmt::FunctionDef(func) => {
                for decorator in &func.decorator_list {
                    self.visit_expr(decorator);
                }
                self.visit_suite(&func.body);
            }
            ast::Stmt::AsyncFunctionDef(func) => {
                for decorator in &func.decorator_list {
                    self.visit_expr(decorator);
                }
                self.visit_suite(&func.body);
            }
            ast::Stmt::ClassDef(class_def) => {
                for decorator in &class_def.decorator_list {
                    self.visit_expr(decorator);
                }
                self.visit_suite(&class_def.body);
            }
            ast::Stmt::With(with_stmt) => {
                for item in &with_stmt.items {
                    self.visit_expr(&item.context_expr);
                    if let Some(optional_vars) = &item.optional_vars {
                        self.visit_expr(optional_vars);
                    }
                }
                self.visit_suite(&with_stmt.body);
            }
            ast::Stmt::AsyncWith(with_stmt) => {
                for item in &with_stmt.items {
                    self.visit_expr(&item.context_expr);
                    if let Some(optional_vars) = &item.optional_vars {
                        self.visit_expr(optional_vars);
                    }
                }
                self.visit_suite(&with_stmt.body);
            }
            ast::Stmt::Try(try_stmt) => {
                self.visit_suite(&try_stmt.body);
                self.visit_suite(&try_stmt.orelse);
                self.visit_suite(&try_stmt.finalbody);
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    if let Some(name) = &handler.name {
                        self.record_name(name.as_str(), None);
                    }
                    self.visit_suite(&handler.body);
                }
            }
            ast::Stmt::TryStar(try_stmt) => {
                self.visit_suite(&try_stmt.body);
                self.visit_suite(&try_stmt.orelse);
                self.visit_suite(&try_stmt.finalbody);
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    if let Some(name) = &handler.name {
                        self.record_name(name.as_str(), None);
                    }
                    self.visit_suite(&handler.body);
                }
            }
            ast::Stmt::Match(match_stmt) => {
                self.visit_expr(&match_stmt.subject);
                for case in &match_stmt.cases {
                    self.visit_suite(&case.body);
                }
            }
            ast::Stmt::Return(ret) => {
                if let Some(value) = &ret.value {
                    self.visit_expr(value);
                }
            }
            ast::Stmt::Raise(raise) => {
                if let Some(exc) = &raise.exc {
                    self.visit_expr(exc);
                }
                if let Some(cause) = &raise.cause {
                    self.visit_expr(cause);
                }
            }
            _ => {}
        }
    }

    fn visit_expr(&mut self, expr: &ast::Expr) {
        match expr {
            ast::Expr::Name(name_expr) => {
                self.record_name(name_expr.id.as_str(), None);
            }
            ast::Expr::Attribute(attr) => {
                self.visit_expr(&attr.value);
            }
            ast::Expr::Subscript(subscript) => {
                self.visit_expr(&subscript.value);
                self.visit_expr(&subscript.slice);
            }
            ast::Expr::Starred(starred) => {
                self.visit_expr(&starred.value);
            }
            ast::Expr::BinOp(binop) => {
                self.visit_expr(&binop.left);
                self.visit_expr(&binop.right);
            }
            ast::Expr::UnaryOp(unary) => {
                self.visit_expr(&unary.operand);
            }
            ast::Expr::Lambda(lambda) => {
                self.visit_expr(&lambda.body);
            }
            ast::Expr::IfExp(if_exp) => {
                self.visit_expr(&if_exp.test);
                self.visit_expr(&if_exp.body);
                self.visit_expr(&if_exp.orelse);
            }
            ast::Expr::Dict(dict) => {
                for value in &dict.values {
                    self.visit_expr(value);
                }
                for key in dict.keys.iter().flatten() {
                    self.visit_expr(key);
                }
            }
            ast::Expr::Set(set_expr) => {
                for elt in &set_expr.elts {
                    self.visit_expr(elt);
                }
            }
            ast::Expr::ListComp(comp) => {
                for gen in &comp.generators {
                    self.visit_expr(&gen.iter);
                    for if_ in &gen.ifs {
                        self.visit_expr(if_);
                    }
                }
                self.visit_expr(&comp.elt);
            }
            ast::Expr::SetComp(comp) => {
                for gen in &comp.generators {
                    self.visit_expr(&gen.iter);
                    for if_ in &gen.ifs {
                        self.visit_expr(if_);
                    }
                }
                self.visit_expr(&comp.elt);
            }
            ast::Expr::DictComp(comp) => {
                for gen in &comp.generators {
                    self.visit_expr(&gen.iter);
                    for if_ in &gen.ifs {
                        self.visit_expr(if_);
                    }
                }
                self.visit_expr(&comp.key);
                self.visit_expr(&comp.value);
            }
            ast::Expr::GeneratorExp(comp) => {
                for gen in &comp.generators {
                    self.visit_expr(&gen.iter);
                    for if_ in &gen.ifs {
                        self.visit_expr(if_);
                    }
                }
                self.visit_expr(&comp.elt);
            }
            ast::Expr::Await(await_expr) => {
                self.visit_expr(&await_expr.value);
            }
            ast::Expr::Yield(yield_expr) => {
                if let Some(value) = &yield_expr.value {
                    self.visit_expr(value);
                }
            }
            ast::Expr::YieldFrom(yield_from) => {
                self.visit_expr(&yield_from.value);
            }
            ast::Expr::Compare(compare) => {
                self.visit_expr(&compare.left);
                for comparator in &compare.comparators {
                    self.visit_expr(comparator);
                }
            }
            ast::Expr::Call(call) => {
                self.visit_expr(&call.func);
                for arg in &call.args {
                    self.visit_expr(arg);
                }
                for keyword in &call.keywords {
                    self.visit_expr(&keyword.value);
                }
            }
            ast::Expr::BoolOp(bool_op) => {
                for value in &bool_op.values {
                    self.visit_expr(value);
                }
            }
            ast::Expr::Constant(_) => {}
            ast::Expr::List(list) => {
                for elt in &list.elts {
                    self.visit_expr(elt);
                }
            }
            ast::Expr::Tuple(tuple) => {
                for elt in &tuple.elts {
                    self.visit_expr(elt);
                }
            }
            ast::Expr::JoinedStr(_joined) => {
                // JoinedStr (f-strings) - skip for now, can be enhanced later
            }
            ast::Expr::NamedExpr(named) => {
                self.visit_expr(&named.value);
            }
            ast::Expr::FormattedValue(_) => {
                // FormattedValues are part of JoinedStr, skip for now
            }
            ast::Expr::Slice(slice) => {
                if let Some(lower) = &slice.lower {
                    self.visit_expr(lower);
                }
                if let Some(upper) = &slice.upper {
                    self.visit_expr(upper);
                }
                if let Some(step) = &slice.step {
                    self.visit_expr(step);
                }
            }
        }
    }

    fn record_name(&mut self, name: &str, lineno: Option<&ast::Int>) {
        let line_num = lineno.map_or(0, ast::Int::to_usize);
        self.names
            .entry(name.to_string())
            .or_default()
            .push(line_num);
    }
}

impl Default for ImportCollector {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn imports_from(source: &str) -> Vec<String> {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(source)
            .expect("import collection should succeed");
        collector.get_imports().get_imports()
    }

    #[test]
    fn collects_top_level_modules() {
        let imports = imports_from(
            r#"
import os
import sys as system
import numpy.linalg
from collections import defaultdict
from pandas import (DataFrame, Series)
"#,
        );

        assert_eq!(
            imports,
            vec![
                "collections".to_string(),
                "numpy".to_string(),
                "os".to_string(),
                "pandas".to_string(),
                "sys".to_string()
            ]
        );
    }

    #[test]
    fn skips_relative_imports() {
        let imports = imports_from(
            r#"
from . import local_module
from ..package import feature
"#,
        );

        assert!(imports.is_empty());
    }

    #[test]
    fn ignores_duplicates_and_aliases() {
        let imports = imports_from(
            r#"
import os
import os.path as osp
from os import path
"#,
        );

        assert_eq!(imports, vec!["os".to_string()]);
    }

    // ============= New symbol-level tracking tests =============

    #[test]
    fn collects_detailed_imports_from_import() {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(
                r#"
import os
import sys as system
import numpy.linalg
"#,
            )
            .expect("parse should succeed");

        let detailed = collector.get_detailed_imports();
        assert_eq!(detailed.len(), 3);

        // Check import os
        assert!(detailed.iter().any(|d| {
            d.module == "os" && d.binding_name == "os" && !d.is_wildcard && d.symbols.is_empty()
        }));

        // Check import sys as system
        assert!(detailed.iter().any(|d| {
            d.module == "sys"
                && d.binding_name == "system"
                && !d.is_wildcard
                && d.symbols.is_empty()
        }));

        // Check import numpy.linalg
        assert!(detailed.iter().any(|d| {
            d.module == "numpy.linalg" && d.binding_name == "numpy" && !d.is_wildcard
        }));
    }

    #[test]
    fn collects_detailed_imports_from_from_import() {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(
                r#"
from os import path
from collections import defaultdict, Counter
from typing import List as L
"#,
            )
            .expect("parse should succeed");

        let detailed = collector.get_detailed_imports();
        assert_eq!(detailed.len(), 4);

        // Check from os import path
        assert!(detailed.iter().any(|d| {
            d.module == "os"
                && d.binding_name == "path"
                && d.symbols == vec!["path"]
                && !d.is_wildcard
        }));

        // Check from collections import defaultdict, Counter
        assert!(detailed.iter().any(|d| {
            d.module == "collections"
                && d.binding_name == "defaultdict"
                && d.symbols == vec!["defaultdict"]
        }));
        assert!(detailed.iter().any(|d| {
            d.module == "collections" && d.binding_name == "Counter" && d.symbols == vec!["Counter"]
        }));

        // Check from typing import List as L
        assert!(detailed.iter().any(|d| {
            d.module == "typing"
                && d.binding_name == "L"
                && d.symbols == vec!["List"]
                && !d.is_wildcard
        }));
    }

    #[test]
    fn detects_wildcard_imports() {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(
                r#"
from os import *
from collections import namedtuple
"#,
            )
            .expect("parse should succeed");

        let detailed = collector.get_detailed_imports();
        assert_eq!(detailed.len(), 2);

        // Check wildcard import
        assert!(detailed
            .iter()
            .any(|d| { d.module == "os" && d.is_wildcard }));

        // Check regular import
        assert!(detailed
            .iter()
            .any(|d| { d.module == "collections" && !d.is_wildcard }));
    }

    #[test]
    fn lookup_import_by_binding() {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(
                r#"
import numpy as np
from collections import defaultdict
"#,
            )
            .expect("parse should succeed");

        // Lookup np -> should find numpy import
        let np_import = collector.get_import_by_binding("np");
        assert!(np_import.is_some());
        let np_import = np_import.unwrap();
        assert_eq!(np_import.module, "numpy");
        assert_eq!(np_import.binding_name, "np");

        // Lookup defaultdict -> should find collections import
        let dd_import = collector.get_import_by_binding("defaultdict");
        assert!(dd_import.is_some());
        let dd_import = dd_import.unwrap();
        assert_eq!(dd_import.module, "collections");
        assert_eq!(dd_import.symbols, vec!["defaultdict"]);

        // Lookup nonexistent -> should return None
        assert!(collector.get_import_by_binding("nonexistent").is_none());
    }

    #[test]
    fn analyze_symbol_usage() {
        let mut collector = ImportCollector::new();
        let source = r#"
import os
import sys as system
from collections import defaultdict

result = os.path.join("a", "b")
d = defaultdict(list)
print(system.version)
"#;
        collector
            .collect_from_source(source)
            .expect("parse should succeed");

        let usage = collector
            .analyze_symbol_usage()
            .expect("usage analysis should succeed");

        // os should be used
        assert!(usage.contains_key("os"));
        // system should be used
        assert!(usage.contains_key("system"));
        // defaultdict should be used
        assert!(usage.contains_key("defaultdict"));
    }

    #[test]
    fn analyze_symbol_usage_unused() {
        let mut collector = ImportCollector::new();
        let source = r#"
import os
import sys
from collections import defaultdict

result = "hello"
"#;
        collector
            .collect_from_source(source)
            .expect("parse should succeed");

        let usage = collector
            .analyze_symbol_usage()
            .expect("usage analysis should succeed");

        // All imports are unused
        assert!(!usage.contains_key("os"));
        assert!(!usage.contains_key("sys"));
        assert!(!usage.contains_key("defaultdict"));
    }

    #[test]
    fn get_symbols_from_module() {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(
                r#"
from collections import defaultdict, Counter, deque
from os import path
from typing import List
"#,
            )
            .expect("parse should succeed");

        let symbols = collector.get_symbols_from_module("collections");
        assert_eq!(symbols, vec!["Counter", "defaultdict", "deque"]);

        let symbols = collector.get_symbols_from_module("os");
        assert_eq!(symbols, vec!["path"]);

        let symbols = collector.get_symbols_from_module("typing");
        assert_eq!(symbols, vec!["List"]);

        // Module with no symbols
        let symbols = collector.get_symbols_from_module("numpy");
        assert!(symbols.is_empty());
    }

    #[test]
    fn has_wildcard_import() {
        let mut collector = ImportCollector::new();
        collector
            .collect_from_source(
                r#"
from os import *
from collections import Counter
"#,
            )
            .expect("parse should succeed");

        assert!(collector.has_wildcard_import("os"));
        assert!(!collector.has_wildcard_import("collections"));
        assert!(!collector.has_wildcard_import("numpy"));
    }

    #[test]
    fn symbol_usage_in_nested_scopes() {
        let mut collector = ImportCollector::new();
        let source = r#"
import os

def func():
    path = os.path.join("a", "b")
    return path

class MyClass:
    def method(self):
        return os.getcwd()

if True:
    result = os.listdir(".")
"#;
        collector
            .collect_from_source(source)
            .expect("parse should succeed");

        let usage = collector
            .analyze_symbol_usage()
            .expect("usage analysis should succeed");

        // os should be found even in nested scopes
        assert!(usage.contains_key("os"));
    }

    #[test]
    fn symbol_usage_in_comprehensions() {
        let mut collector = ImportCollector::new();
        let source = r#"
from collections import defaultdict

data = [defaultdict(list) for _ in range(10)]
"#;
        collector
            .collect_from_source(source)
            .expect("parse should succeed");

        let usage = collector
            .analyze_symbol_usage()
            .expect("usage analysis should succeed");

        assert!(usage.contains_key("defaultdict"));
    }

    #[test]
    fn symbol_usage_in_function_calls() {
        let mut collector = ImportCollector::new();
        let source = r#"
from functools import lru_cache
from itertools import chain

@lru_cache(maxsize=128)
def func():
    return list(chain([1, 2], [3, 4]))
"#;
        collector
            .collect_from_source(source)
            .expect("parse should succeed");

        let usage = collector
            .analyze_symbol_usage()
            .expect("usage analysis should succeed");

        assert!(usage.contains_key("lru_cache"));
        assert!(usage.contains_key("chain"));
    }
}
