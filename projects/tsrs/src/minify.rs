//! Scope-aware rename planning inspired by pyminifier.

use crate::error::{Result, TsrsError};
use rustpython_parser::ast::Ranged;
use rustpython_parser::{ast, Parse};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

const PYTHON_KEYWORDS: &[&str] = &[
    "False", "None", "True", "and", "as", "assert", "async", "await", "break", "case", "class",
    "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if",
    "import", "in", "is", "lambda", "match", "nonlocal", "not", "or", "pass", "raise", "return",
    "try", "while", "with", "yield",
];

const RESERVED_IDENTIFIERS: &[&str] = &["self", "cls", "_"];

/// High-level API for computing rename plans.
pub struct Minifier;

impl Minifier {
    /// Build a plan for renaming local symbols in every function contained in the source.
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed.
    pub fn plan_from_source(module_name: &str, source: &str) -> Result<MinifyPlan> {
        let suite = ast::Suite::parse(source, module_name)
            .map_err(|err| TsrsError::ParseError(err.to_string()))?;

        let mut planner = Planner::new(module_name.to_string());
        planner.visit_suite(&suite, &mut Vec::new());

        Ok(planner.finish())
    }

    /// Rewrite source code by applying planned renames when no nested functions are present.
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed or planned.
    pub fn rewrite_source(module_name: &str, source: &str) -> Result<String> {
        let plan = Self::plan_from_source(module_name, source)?;

        Self::rewrite_with_plan_internal(module_name, source, &plan)
    }

    /// Rewrite using a precomputed plan, enabling plan curation before application.
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed.
    pub fn rewrite_with_plan(module_name: &str, source: &str, plan: &MinifyPlan) -> Result<String> {
        Self::rewrite_with_plan_internal(module_name, source, plan)
    }

    fn rewrite_with_plan_internal(
        module_name: &str,
        source: &str,
        plan: &MinifyPlan,
    ) -> Result<String> {
        let mut plan_map: HashMap<String, FunctionPlan> = HashMap::new();
        let mut invalid_plan = false;

        for function_plan in &plan.functions {
            if function_plan.range.is_none() {
                invalid_plan = true;
                continue;
            }
            if function_plan.renames.is_empty() {
                continue;
            }
            plan_map.insert(function_plan.qualified_name.clone(), function_plan.clone());
        }

        let mut rewritten = source.to_string();

        if !invalid_plan && !plan_map.is_empty() {
            let suite = ast::Suite::parse(source, module_name)
                .map_err(|err| TsrsError::ParseError(err.to_string()))?;

            let rewriter = FunctionRewriter::new(source, &plan_map);
            rewritten = rewriter.rewrite(&suite)?;
        }

        strip_docstrings(module_name, &rewritten)
    }
}

/// JSON-serializable rename plan for an entire module.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MinifyPlan {
    pub module: String,
    pub keywords: Vec<String>,
    pub functions: Vec<FunctionPlan>,
}

/// Rename mapping for a single function scope.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FunctionPlan {
    /// Fully-qualified function name (e.g. `module.Class.method`).
    pub qualified_name: String,
    /// Ordered list of original local names considered for renaming.
    pub locals: Vec<String>,
    /// Planned replacements paired with their original names.
    pub renames: Vec<RenameEntry>,
    /// Names encountered but excluded from renaming (globals, keywords, etc.).
    #[serde(default)]
    pub excluded: Vec<String>,
    /// Optional function source range (byte offsets) to support rewriting.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub range: Option<FunctionRange>,
    /// Indicates whether nested function definitions exist inside this function.
    pub has_nested_functions: bool,
    /// Indicates if the function body contains import statements.
    pub has_imports: bool,
    #[serde(default)]
    pub has_match_statement: bool,
    #[serde(default)]
    pub has_comprehension: bool,
    /// Nested function plans collected recursively.
    #[serde(default)]
    pub nested: Vec<FunctionPlan>,
}

/// Mapping from an original identifier to a generated replacement.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RenameEntry {
    pub original: String,
    pub renamed: String,
}

/// Location of a function in the original source using byte offsets.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct FunctionRange {
    pub start: usize,
    pub end: usize,
}

fn flatten_plan(mut plan: FunctionPlan, out: &mut Vec<FunctionPlan>) {
    out.push(plan.clone());
    for child in plan.nested.drain(..) {
        flatten_plan(child, out);
    }
}

struct Planner {
    module: String,
    roots: Vec<FunctionPlan>,
}

impl Planner {
    fn new(module: String) -> Self {
        Self {
            module,
            roots: Vec::new(),
        }
    }

    fn finish(self) -> MinifyPlan {
        let mut functions = Vec::new();
        for plan in self.roots {
            flatten_plan(plan, &mut functions);
        }

        MinifyPlan {
            module: self.module,
            keywords: PYTHON_KEYWORDS
                .iter()
                .map(std::string::ToString::to_string)
                .collect(),
            functions,
        }
    }

    fn visit_suite(&mut self, suite: &[ast::Stmt], path: &mut Vec<String>) {
        for stmt in suite {
            match stmt {
                ast::Stmt::FunctionDef(func) => {
                    let range = Some(range_from_node(func));
                    let plan =
                        self.plan_function(&func.name, &func.args, &func.body, path, None, range);
                    self.roots.push(plan);
                }
                ast::Stmt::AsyncFunctionDef(func) => {
                    let range = Some(range_from_node(func));
                    let plan =
                        self.plan_function(&func.name, &func.args, &func.body, path, None, range);
                    self.roots.push(plan);
                }
                ast::Stmt::ClassDef(class_def) => {
                    let class_plans = self.visit_class_collect(class_def, path);
                    self.roots.extend(class_plans);
                }
                _ => {}
            }
        }
    }

    fn visit_class_collect(
        &mut self,
        class_def: &ast::StmtClassDef,
        path: &mut Vec<String>,
    ) -> Vec<FunctionPlan> {
        path.push(class_def.name.to_string());
        let mut plans = Vec::new();
        for stmt in &class_def.body {
            match stmt {
                ast::Stmt::FunctionDef(func) => {
                    let range = Some(range_from_node(func));
                    let plan =
                        self.plan_function(&func.name, &func.args, &func.body, path, None, range);
                    plans.push(plan);
                }
                ast::Stmt::AsyncFunctionDef(func) => {
                    let range = Some(range_from_node(func));
                    let plan =
                        self.plan_function(&func.name, &func.args, &func.body, path, None, range);
                    plans.push(plan);
                }
                ast::Stmt::ClassDef(inner) => {
                    let inner_plans = self.visit_class_collect(inner, path);
                    plans.extend(inner_plans);
                }
                _ => {}
            }
        }
        path.pop();
        plans
    }

    fn plan_function(
        &mut self,
        name: &ast::Identifier,
        args: &ast::Arguments,
        body: &[ast::Stmt],
        path: &mut Vec<String>,
        parent_collector: Option<&mut FunctionCollector>,
        range: Option<FunctionRange>,
    ) -> FunctionPlan {
        let name_str = name.to_string();
        if let Some(collector) = parent_collector {
            collector.reserve_name(&name_str);
            collector.mark_nested_function();
        }

        path.push(name_str);
        let qualified_name = path.join(".");

        let mut reserved = default_reserved();
        let (globals, nonlocals) = collect_declared_names(body);
        for name in globals.iter().chain(nonlocals.iter()) {
            reserved.insert(name.clone());
        }

        let mut collector = FunctionCollector::new(reserved);
        collector.collect_parameters(args);
        collector.record_exclusions(globals.into_iter());
        collector.record_exclusions(nonlocals.into_iter());

        let nested = self.collect_in_function(&mut collector, body, path);

        let mut plan = collector.into_plan(qualified_name, range);
        plan.nested = nested;

        path.pop();
        plan
    }

    #[allow(clippy::too_many_lines)]
    fn collect_in_function(
        &mut self,
        collector: &mut FunctionCollector,
        body: &[ast::Stmt],
        path: &mut Vec<String>,
    ) -> Vec<FunctionPlan> {
        let mut nested_plans = Vec::new();
        for stmt in body {
            match stmt {
                ast::Stmt::FunctionDef(func) => {
                    let captured = collect_used_names_in_function(func, 0);
                    for name in captured {
                        collector.reserve_name(&name);
                    }
                    let range = Some(range_from_node(func));
                    let plan = self.plan_function(
                        &func.name,
                        &func.args,
                        &func.body,
                        path,
                        Some(collector),
                        range,
                    );
                    nested_plans.push(plan);
                }
                ast::Stmt::AsyncFunctionDef(func) => {
                    let captured = collect_used_names_in_async_function(func, 0);
                    for name in captured {
                        collector.reserve_name(&name);
                    }
                    let range = Some(range_from_node(func));
                    let plan = self.plan_function(
                        &func.name,
                        &func.args,
                        &func.body,
                        path,
                        Some(collector),
                        range,
                    );
                    nested_plans.push(plan);
                }
                ast::Stmt::ClassDef(class_def) => {
                    let captured = collect_used_names_in_class(class_def, 1);
                    for name in captured {
                        collector.reserve_name(&name);
                    }
                    let class_name = class_def.name.to_string();
                    collector.reserve_name(&class_name);
                    collector.mark_nested_function();
                    let class_plans = self.visit_class_collect(class_def, path);
                    nested_plans.extend(class_plans);
                }
                ast::Stmt::Assign(assign) => {
                    for target in &assign.targets {
                        collector.add_names_from_expr(target);
                    }
                    collector.collect_from_expression(&assign.value);
                }
                ast::Stmt::AnnAssign(assign) => {
                    collector.add_names_from_expr(&assign.target);
                    if let Some(value) = &assign.value {
                        collector.collect_from_expression(value);
                    }
                }
                ast::Stmt::AugAssign(assign) => {
                    collector.add_names_from_expr(&assign.target);
                    collector.collect_from_expression(&assign.value);
                }
                ast::Stmt::For(for_stmt) => {
                    collector.add_names_from_expr(&for_stmt.target);
                    self.collect_in_function(collector, &for_stmt.body, path);
                    self.collect_in_function(collector, &for_stmt.orelse, path);
                }
                ast::Stmt::AsyncFor(for_stmt) => {
                    collector.add_names_from_expr(&for_stmt.target);
                    self.collect_in_function(collector, &for_stmt.body, path);
                    self.collect_in_function(collector, &for_stmt.orelse, path);
                }
                ast::Stmt::While(while_stmt) => {
                    self.collect_in_function(collector, &while_stmt.body, path);
                    self.collect_in_function(collector, &while_stmt.orelse, path);
                }
                ast::Stmt::If(if_stmt) => {
                    self.collect_in_function(collector, &if_stmt.body, path);
                    self.collect_in_function(collector, &if_stmt.orelse, path);
                }
                ast::Stmt::With(with_stmt) => {
                    for item in &with_stmt.items {
                        if let Some(optional) = &item.optional_vars {
                            collector.add_names_from_expr(optional);
                        }
                    }
                    self.collect_in_function(collector, &with_stmt.body, path);
                }
                ast::Stmt::AsyncWith(with_stmt) => {
                    for item in &with_stmt.items {
                        if let Some(optional) = &item.optional_vars {
                            collector.add_names_from_expr(optional);
                        }
                    }
                    self.collect_in_function(collector, &with_stmt.body, path);
                }
                ast::Stmt::Try(try_stmt) => {
                    self.collect_in_function(collector, &try_stmt.body, path);
                    self.collect_in_function(collector, &try_stmt.orelse, path);
                    self.collect_in_function(collector, &try_stmt.finalbody, path);
                    for handler in &try_stmt.handlers {
                        let ast::ExceptHandler::ExceptHandler(handler) = handler;
                        if let Some(name) = &handler.name {
                            collector.add_name(name.as_ref());
                        }
                        self.collect_in_function(collector, &handler.body, path);
                    }
                }
                ast::Stmt::TryStar(try_stmt) => {
                    self.collect_in_function(collector, &try_stmt.body, path);
                    self.collect_in_function(collector, &try_stmt.orelse, path);
                    self.collect_in_function(collector, &try_stmt.finalbody, path);
                    for handler in &try_stmt.handlers {
                        let ast::ExceptHandler::ExceptHandler(handler) = handler;
                        if let Some(name) = &handler.name {
                            collector.add_name(name.as_ref());
                        }
                        self.collect_in_function(collector, &handler.body, path);
                    }
                }
                ast::Stmt::Return(ret) => {
                    if let Some(value) = &ret.value {
                        collector.collect_from_expression(value);
                    }
                }
                ast::Stmt::Match(match_stmt) => {
                    collector.has_match_statement = true;
                    for case in &match_stmt.cases {
                        collector.add_names_from_pattern(&case.pattern);
                        if let Some(guard) = &case.guard {
                            collector.collect_from_expression(guard);
                        }
                        self.collect_in_function(collector, &case.body, path);
                    }
                }
                ast::Stmt::Import(import_stmt) => {
                    collector.mark_import();
                    for alias in &import_stmt.names {
                        if let Some(asname) = &alias.asname {
                            collector.reserve_name(asname.as_ref());
                        } else {
                            let module = alias.name.to_string();
                            let base = module.split('.').next().unwrap_or(&module);
                            if module.contains('.') {
                                collector.reserve_name(base);
                            } else {
                                collector.add_name(base);
                            }
                        }
                    }
                }
                ast::Stmt::ImportFrom(import_from) => {
                    collector.mark_import();
                    for alias in &import_from.names {
                        let name = alias.name.to_string();
                        if name == "*" {
                            continue;
                        }
                        if let Some(asname) = &alias.asname {
                            collector.reserve_name(asname.as_ref());
                        } else {
                            let base = name.split('.').next().unwrap_or(&name);
                            collector.add_name(base);
                        }
                    }
                }
                ast::Stmt::Expr(expr_stmt) => {
                    collector.collect_from_expression(&expr_stmt.value);
                }
                _ => {}
            }
        }
        nested_plans
    }
}

fn collect_declared_names(body: &[ast::Stmt]) -> (HashSet<String>, HashSet<String>) {
    let mut globals = HashSet::new();
    let mut nonlocals = HashSet::new();

    for stmt in body {
        match stmt {
            ast::Stmt::Global(glob) => {
                for name in &glob.names {
                    globals.insert(name.to_string());
                }
            }
            ast::Stmt::Nonlocal(non) => {
                for name in &non.names {
                    nonlocals.insert(name.to_string());
                }
            }
            _ => {}
        }
    }

    (globals, nonlocals)
}

fn default_reserved() -> HashSet<String> {
    let mut reserved: HashSet<String> = PYTHON_KEYWORDS
        .iter()
        .map(std::string::ToString::to_string)
        .collect();
    for ident in RESERVED_IDENTIFIERS {
        reserved.insert((*ident).to_string());
    }
    reserved
}

#[derive(Default)]
struct UsedNameCollector {
    names: HashSet<String>,
}

impl UsedNameCollector {
    fn into_names(self) -> HashSet<String> {
        self.names
    }

    fn record_name(&mut self, expr_name: &ast::ExprName) {
        if matches!(expr_name.ctx, ast::ExprContext::Load) {
            self.names.insert(expr_name.id.to_string());
        }
    }

    fn visit_suite(&mut self, suite: &[ast::Stmt], depth: usize) {
        for stmt in suite {
            self.visit_stmt(stmt, depth);
        }
    }

    #[allow(clippy::too_many_lines)]
    fn visit_stmt(&mut self, stmt: &ast::Stmt, depth: usize) {
        match stmt {
            ast::Stmt::FunctionDef(func) => self.visit_function_def(func, depth),
            ast::Stmt::AsyncFunctionDef(func) => self.visit_async_function_def(func, depth),
            ast::Stmt::ClassDef(class_def) => self.visit_class_def(class_def, depth),
            ast::Stmt::Return(ret) => {
                if let Some(value) = &ret.value {
                    self.visit_expr(value, depth);
                }
            }
            ast::Stmt::Expr(expr_stmt) => self.visit_expr(&expr_stmt.value, depth),
            ast::Stmt::Assign(assign) => {
                for target in &assign.targets {
                    self.visit_expr(target, depth);
                }
                self.visit_expr(&assign.value, depth);
            }
            ast::Stmt::AnnAssign(assign) => {
                self.visit_expr(&assign.target, depth);
                self.visit_expr(&assign.annotation, depth);
                if let Some(value) = &assign.value {
                    self.visit_expr(value, depth);
                }
            }
            ast::Stmt::AugAssign(assign) => {
                self.visit_expr(&assign.target, depth);
                self.visit_expr(&assign.value, depth);
            }
            ast::Stmt::For(for_stmt) => {
                self.visit_expr(&for_stmt.target, depth);
                self.visit_expr(&for_stmt.iter, depth);
                self.visit_suite(&for_stmt.body, depth);
                self.visit_suite(&for_stmt.orelse, depth);
            }
            ast::Stmt::AsyncFor(for_stmt) => {
                self.visit_expr(&for_stmt.target, depth);
                self.visit_expr(&for_stmt.iter, depth);
                self.visit_suite(&for_stmt.body, depth);
                self.visit_suite(&for_stmt.orelse, depth);
            }
            ast::Stmt::While(while_stmt) => {
                self.visit_expr(&while_stmt.test, depth);
                self.visit_suite(&while_stmt.body, depth);
                self.visit_suite(&while_stmt.orelse, depth);
            }
            ast::Stmt::If(if_stmt) => {
                self.visit_expr(&if_stmt.test, depth);
                self.visit_suite(&if_stmt.body, depth);
                self.visit_suite(&if_stmt.orelse, depth);
            }
            ast::Stmt::With(with_stmt) => {
                for item in &with_stmt.items {
                    self.visit_expr(&item.context_expr, depth);
                    if let Some(optional) = &item.optional_vars {
                        self.visit_expr(optional, depth);
                    }
                }
                self.visit_suite(&with_stmt.body, depth);
            }
            ast::Stmt::AsyncWith(with_stmt) => {
                for item in &with_stmt.items {
                    self.visit_expr(&item.context_expr, depth);
                    if let Some(optional) = &item.optional_vars {
                        self.visit_expr(optional, depth);
                    }
                }
                self.visit_suite(&with_stmt.body, depth);
            }
            ast::Stmt::Try(try_stmt) => {
                self.visit_suite(&try_stmt.body, depth);
                self.visit_suite(&try_stmt.orelse, depth);
                self.visit_suite(&try_stmt.finalbody, depth);
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    if let Some(typ) = &handler.type_ {
                        self.visit_expr(typ, depth);
                    }
                    self.visit_suite(&handler.body, depth);
                }
            }
            ast::Stmt::TryStar(try_stmt) => {
                self.visit_suite(&try_stmt.body, depth);
                self.visit_suite(&try_stmt.orelse, depth);
                self.visit_suite(&try_stmt.finalbody, depth);
                for handler in &try_stmt.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    if let Some(typ) = &handler.type_ {
                        self.visit_expr(typ, depth);
                    }
                    self.visit_suite(&handler.body, depth);
                }
            }
            ast::Stmt::Raise(raise) => {
                if let Some(exc) = &raise.exc {
                    self.visit_expr(exc, depth);
                }
                if let Some(cause) = &raise.cause {
                    self.visit_expr(cause, depth);
                }
            }
            ast::Stmt::Assert(assert_stmt) => {
                self.visit_expr(&assert_stmt.test, depth);
                if let Some(msg) = &assert_stmt.msg {
                    self.visit_expr(msg, depth);
                }
            }
            ast::Stmt::Match(match_stmt) => {
                self.visit_expr(&match_stmt.subject, depth);
                for case in &match_stmt.cases {
                    if let Some(guard) = &case.guard {
                        self.visit_expr(guard, depth);
                    }
                    self.visit_suite(&case.body, depth);
                }
            }
            ast::Stmt::Delete(delete) => {
                for target in &delete.targets {
                    self.visit_expr(target, depth);
                }
            }
            ast::Stmt::Pass(_)
            | ast::Stmt::Break(_)
            | ast::Stmt::Continue(_)
            | ast::Stmt::Global(_)
            | ast::Stmt::Nonlocal(_)
            | ast::Stmt::Import(_)
            | ast::Stmt::ImportFrom(_) => {}
            ast::Stmt::TypeAlias(type_alias) => {
                self.visit_expr(&type_alias.value, depth);
            }
        }
    }

    fn visit_function_def(&mut self, func: &ast::StmtFunctionDef, depth: usize) {
        for decorator in &func.decorator_list {
            self.visit_expr(decorator, depth);
        }
        self.visit_arguments(&func.args, depth);
        if let Some(returns) = &func.returns {
            self.visit_expr(returns, depth);
        }
        if depth == 0 {
            return;
        }
        let body_depth = depth - 1;
        self.visit_suite(&func.body, body_depth);
    }

    fn visit_async_function_def(&mut self, func: &ast::StmtAsyncFunctionDef, depth: usize) {
        for decorator in &func.decorator_list {
            self.visit_expr(decorator, depth);
        }
        self.visit_arguments(&func.args, depth);
        if let Some(returns) = &func.returns {
            self.visit_expr(returns, depth);
        }
        if depth == 0 {
            return;
        }
        let body_depth = depth - 1;
        self.visit_suite(&func.body, body_depth);
    }

    fn visit_class_def(&mut self, class_def: &ast::StmtClassDef, depth: usize) {
        for decorator in &class_def.decorator_list {
            self.visit_expr(decorator, depth);
        }
        for base in &class_def.bases {
            self.visit_expr(base, depth);
        }
        for keyword in &class_def.keywords {
            self.visit_expr(&keyword.value, depth);
        }
        if depth == 0 {
            return;
        }
        let body_depth = depth - 1;
        self.visit_suite(&class_def.body, body_depth);
    }

    fn visit_arguments(&mut self, args: &ast::Arguments, depth: usize) {
        for param in &args.posonlyargs {
            self.visit_arg_with_default(param, depth);
        }
        for param in &args.args {
            self.visit_arg_with_default(param, depth);
        }
        if let Some(vararg) = &args.vararg {
            self.visit_arg(vararg, depth);
        }
        for param in &args.kwonlyargs {
            self.visit_arg_with_default(param, depth);
        }
        if let Some(kwarg) = &args.kwarg {
            self.visit_arg(kwarg, depth);
        }
    }

    fn visit_arg_with_default(&mut self, arg: &ast::ArgWithDefault, depth: usize) {
        self.visit_arg(&arg.def, depth);
        if let Some(default) = &arg.default {
            self.visit_expr(default, depth);
        }
    }

    fn visit_arg(&mut self, arg: &ast::Arg, depth: usize) {
        if let Some(annotation) = &arg.annotation {
            self.visit_expr(annotation, depth);
        }
    }

    #[allow(clippy::too_many_lines)]
    fn visit_expr(&mut self, expr: &ast::Expr, depth: usize) {
        match expr {
            ast::Expr::Name(expr_name) => self.record_name(expr_name),
            ast::Expr::BoolOp(expr_bool) => {
                for value in &expr_bool.values {
                    self.visit_expr(value, depth);
                }
            }
            ast::Expr::BinOp(expr_bin) => {
                self.visit_expr(&expr_bin.left, depth);
                self.visit_expr(&expr_bin.right, depth);
            }
            ast::Expr::UnaryOp(expr_unary) => {
                self.visit_expr(&expr_unary.operand, depth);
            }
            ast::Expr::Lambda(lambda) => {
                self.visit_arguments(&lambda.args, depth);
                let inner_depth = depth.saturating_sub(1);
                self.visit_expr(&lambda.body, inner_depth);
            }
            ast::Expr::IfExp(expr_if) => {
                self.visit_expr(&expr_if.test, depth);
                self.visit_expr(&expr_if.body, depth);
                self.visit_expr(&expr_if.orelse, depth);
            }
            ast::Expr::List(expr_list) => {
                for elt in &expr_list.elts {
                    self.visit_expr(elt, depth);
                }
            }
            ast::Expr::Tuple(expr_tuple) => {
                for elt in &expr_tuple.elts {
                    self.visit_expr(elt, depth);
                }
            }
            ast::Expr::Set(expr_set) => {
                for elt in &expr_set.elts {
                    self.visit_expr(elt, depth);
                }
            }
            ast::Expr::Dict(expr_dict) => {
                for key in expr_dict.keys.iter().flatten() {
                    self.visit_expr(key, depth);
                }
                for value in &expr_dict.values {
                    self.visit_expr(value, depth);
                }
            }
            ast::Expr::ListComp(expr) => {
                self.visit_expr(&expr.elt, depth);
                self.visit_comprehension_generators(&expr.generators, depth);
            }
            ast::Expr::SetComp(expr) => {
                self.visit_expr(&expr.elt, depth);
                self.visit_comprehension_generators(&expr.generators, depth);
            }
            ast::Expr::DictComp(expr) => {
                self.visit_expr(&expr.key, depth);
                self.visit_expr(&expr.value, depth);
                self.visit_comprehension_generators(&expr.generators, depth);
            }
            ast::Expr::GeneratorExp(expr) => {
                self.visit_expr(&expr.elt, depth);
                self.visit_comprehension_generators(&expr.generators, depth);
            }
            ast::Expr::Compare(expr_compare) => {
                self.visit_expr(&expr_compare.left, depth);
                for comp in &expr_compare.comparators {
                    self.visit_expr(comp, depth);
                }
            }
            ast::Expr::Call(expr_call) => {
                self.visit_expr(&expr_call.func, depth);
                for arg in &expr_call.args {
                    self.visit_expr(arg, depth);
                }
                for keyword in &expr_call.keywords {
                    self.visit_expr(&keyword.value, depth);
                }
            }
            ast::Expr::Attribute(expr_attr) => {
                self.visit_expr(&expr_attr.value, depth);
            }
            ast::Expr::Subscript(expr_sub) => {
                self.visit_expr(&expr_sub.value, depth);
                self.visit_expr(&expr_sub.slice, depth);
            }
            ast::Expr::Starred(expr_star) => {
                self.visit_expr(&expr_star.value, depth);
            }
            ast::Expr::Await(expr_await) => self.visit_expr(&expr_await.value, depth),
            ast::Expr::Yield(expr_yield) => {
                if let Some(value) = &expr_yield.value {
                    self.visit_expr(value, depth);
                }
            }
            ast::Expr::YieldFrom(expr_yield) => self.visit_expr(&expr_yield.value, depth),
            ast::Expr::Constant(_) => {}
            ast::Expr::Slice(slice) => self.visit_slice(slice, depth),
            ast::Expr::JoinedStr(joined) => {
                for value in &joined.values {
                    self.visit_expr(value, depth);
                }
            }
            ast::Expr::FormattedValue(formatted) => {
                self.visit_expr(&formatted.value, depth);
                if let Some(format_spec) = &formatted.format_spec {
                    self.visit_expr(format_spec, depth);
                }
            }
            ast::Expr::NamedExpr(named) => {
                self.visit_expr(&named.target, depth);
                self.visit_expr(&named.value, depth);
            }
        }
    }

    fn visit_comprehension_generators(&mut self, generators: &[ast::Comprehension], depth: usize) {
        for generator in generators {
            self.visit_expr(&generator.iter, depth);
            self.visit_expr(&generator.target, depth);
            for condition in &generator.ifs {
                self.visit_expr(condition, depth);
            }
        }
    }

    fn visit_slice(&mut self, slice: &ast::ExprSlice, depth: usize) {
        if let Some(lower) = &slice.lower {
            self.visit_expr(lower, depth);
        }
        if let Some(upper) = &slice.upper {
            self.visit_expr(upper, depth);
        }
        if let Some(step) = &slice.step {
            self.visit_expr(step, depth);
        }
    }
}

fn collect_used_names_in_function(func: &ast::StmtFunctionDef, depth: usize) -> HashSet<String> {
    let mut collector = UsedNameCollector::default();
    for decorator in &func.decorator_list {
        collector.visit_expr(decorator, depth);
    }
    collector.visit_arguments(&func.args, depth);
    if let Some(returns) = &func.returns {
        collector.visit_expr(returns, depth);
    }
    collector.visit_suite(&func.body, depth);
    collector.into_names()
}

fn collect_used_names_in_async_function(
    func: &ast::StmtAsyncFunctionDef,
    depth: usize,
) -> HashSet<String> {
    let mut collector = UsedNameCollector::default();
    for decorator in &func.decorator_list {
        collector.visit_expr(decorator, depth);
    }
    collector.visit_arguments(&func.args, depth);
    if let Some(returns) = &func.returns {
        collector.visit_expr(returns, depth);
    }
    collector.visit_suite(&func.body, depth);
    collector.into_names()
}

fn collect_used_names_in_class(class_def: &ast::StmtClassDef, depth: usize) -> HashSet<String> {
    let mut collector = UsedNameCollector::default();
    for decorator in &class_def.decorator_list {
        collector.visit_expr(decorator, depth);
    }
    for base in &class_def.bases {
        collector.visit_expr(base, depth);
    }
    for keyword in &class_def.keywords {
        collector.visit_expr(&keyword.value, depth);
    }
    collector.visit_suite(&class_def.body, depth);
    collector.into_names()
}

struct FunctionCollector {
    locals: Vec<String>,
    seen: HashSet<String>,
    excluded: HashSet<String>,
    reserved: HashSet<String>,
    declared_exclusions: HashSet<String>,
    has_nested_functions: bool,
    has_imports: bool,
    has_match_statement: bool,
    has_comprehension: bool,
}

impl FunctionCollector {
    fn new(reserved: HashSet<String>) -> Self {
        Self {
            locals: Vec::new(),
            seen: HashSet::new(),
            excluded: HashSet::new(),
            reserved,
            declared_exclusions: HashSet::new(),
            has_nested_functions: false,
            has_imports: false,
            has_match_statement: false,
            has_comprehension: false,
        }
    }

    fn collect_parameters(&mut self, args: &ast::Arguments) {
        for param in &args.posonlyargs {
            self.add_name(param.def.arg.as_ref());
            if let Some(default) = &param.default {
                self.collect_from_expression(default);
            }
        }
        for param in &args.args {
            self.add_name(param.def.arg.as_ref());
            if let Some(default) = &param.default {
                self.collect_from_expression(default);
            }
        }
        if let Some(vararg) = &args.vararg {
            self.add_name(vararg.arg.as_ref());
        }
        for param in &args.kwonlyargs {
            self.add_name(param.def.arg.as_ref());
            if let Some(default) = &param.default {
                self.collect_from_expression(default);
            }
        }
        if let Some(kwarg) = &args.kwarg {
            self.add_name(kwarg.arg.as_ref());
        }

        for default in args.defaults() {
            self.collect_from_expression(default);
        }
    }

    fn record_exclusions<I>(&mut self, iter: I)
    where
        I: Iterator<Item = String>,
    {
        for name in iter {
            self.declared_exclusions.insert(name.clone());
            self.reserve_name(&name);
        }
    }

    fn add_name(&mut self, name: &str) {
        if name.is_empty() {
            return;
        }
        if self.should_skip(name) {
            self.excluded.insert(name.to_string());
            self.reserved.insert(name.to_string());
            self.locals.retain(|existing| existing != name);
            self.seen.remove(name);
            return;
        }

        if self.seen.insert(name.to_string()) {
            self.locals.push(name.to_string());
        }
    }

    fn reserve_name(&mut self, name: &str) {
        self.excluded.insert(name.to_string());
        self.reserved.insert(name.to_string());
        self.locals.retain(|existing| existing != name);
        self.seen.remove(name);
    }

    fn should_skip(&self, name: &str) -> bool {
        self.reserved.contains(name)
            || name == "_"
            || (name.starts_with("__") && name.ends_with("__"))
    }

    fn mark_nested_function(&mut self) {
        self.has_nested_functions = true;
    }

    fn mark_import(&mut self) {
        self.has_imports = true;
    }

    fn add_names_from_expr(&mut self, expr: &ast::Expr) {
        match expr {
            ast::Expr::Name(ast::ExprName { id, ctx, .. }) => {
                if matches!(ctx, ast::ExprContext::Store | ast::ExprContext::Del) {
                    self.add_name(id.to_string().as_str());
                }
            }
            ast::Expr::Tuple(ast::ExprTuple { elts, .. })
            | ast::Expr::List(ast::ExprList { elts, .. }) => {
                for elt in elts {
                    self.add_names_from_expr(elt);
                }
            }
            ast::Expr::Starred(ast::ExprStarred { value, .. }) => {
                self.add_names_from_expr(value);
            }
            _ => {}
        }
    }

    fn reserve_names_from_expr(&mut self, expr: &ast::Expr) {
        match expr {
            ast::Expr::Name(ast::ExprName { id, ctx, .. }) => {
                if matches!(ctx, ast::ExprContext::Store | ast::ExprContext::Del) {
                    self.reserve_name(id.as_ref());
                }
            }
            ast::Expr::Tuple(ast::ExprTuple { elts, .. })
            | ast::Expr::List(ast::ExprList { elts, .. }) => {
                for elt in elts {
                    self.reserve_names_from_expr(elt);
                }
            }
            ast::Expr::Starred(ast::ExprStarred { value, .. }) => {
                self.reserve_names_from_expr(value);
            }
            _ => {}
        }
    }

    fn add_names_from_pattern(&mut self, pattern: &ast::Pattern) {
        match pattern {
            ast::Pattern::MatchAs(pat) => {
                if let Some(sub) = &pat.pattern {
                    self.add_names_from_pattern(sub);
                }
                if let Some(name) = &pat.name {
                    self.add_name(name.to_string().as_str());
                }
            }
            ast::Pattern::MatchStar(pat) => {
                if let Some(name) = &pat.name {
                    self.add_name(name.to_string().as_str());
                }
            }
            ast::Pattern::MatchSequence(seq) => {
                for sub in &seq.patterns {
                    self.add_names_from_pattern(sub);
                }
            }
            ast::Pattern::MatchMapping(map) => {
                for sub in &map.patterns {
                    self.add_names_from_pattern(sub);
                }
                if let Some(rest) = &map.rest {
                    self.add_name(rest.as_ref());
                }
            }
            ast::Pattern::MatchClass(class) => {
                for sub in &class.patterns {
                    self.add_names_from_pattern(sub);
                }
                for sub in &class.kwd_patterns {
                    self.add_names_from_pattern(sub);
                }
            }
            ast::Pattern::MatchOr(pat) => {
                for sub in &pat.patterns {
                    self.add_names_from_pattern(sub);
                }
            }
            _ => {}
        }
    }

    fn collect_from_expression(&mut self, expr: &ast::Expr) {
        match expr {
            ast::Expr::NamedExpr(named) => {
                self.add_names_from_expr(&named.target);
                self.collect_from_expression(&named.value);
            }
            ast::Expr::BoolOp(ast::ExprBoolOp { values, .. })
            | ast::Expr::Tuple(ast::ExprTuple { elts: values, .. })
            | ast::Expr::List(ast::ExprList { elts: values, .. }) => {
                for value in values {
                    self.collect_from_expression(value);
                }
            }
            ast::Expr::IfExp(ast::ExprIfExp {
                test, body, orelse, ..
            }) => {
                self.collect_from_expression(test);
                self.collect_from_expression(body);
                self.collect_from_expression(orelse);
            }
            ast::Expr::Compare(ast::ExprCompare {
                left, comparators, ..
            }) => {
                self.collect_from_expression(left);
                for comp in comparators {
                    self.collect_from_expression(comp);
                }
            }
            ast::Expr::BinOp(ast::ExprBinOp { left, right, .. }) => {
                self.collect_from_expression(left);
                self.collect_from_expression(right);
            }
            ast::Expr::UnaryOp(ast::ExprUnaryOp { operand, .. }) => {
                self.collect_from_expression(operand);
            }
            ast::Expr::Call(ast::ExprCall {
                func,
                args,
                keywords,
                ..
            }) => {
                self.collect_from_expression(func);
                for arg in args {
                    self.collect_from_expression(arg);
                }
                for keyword in keywords {
                    self.collect_from_expression(&keyword.value);
                }
            }
            ast::Expr::Lambda(_) => {
                // Lambdas introduce their own scope; avoid rewriting in these cases.
                self.mark_nested_function();
            }
            ast::Expr::ListComp(expr) => {
                self.has_comprehension = true;
                self.collect_from_expression(&expr.elt);
                self.collect_from_comprehension_generators(&expr.generators);
            }
            ast::Expr::SetComp(expr) => {
                self.has_comprehension = true;
                self.collect_from_expression(&expr.elt);
                self.collect_from_comprehension_generators(&expr.generators);
            }
            ast::Expr::DictComp(expr) => {
                self.has_comprehension = true;
                self.collect_from_expression(&expr.key);
                self.collect_from_expression(&expr.value);
                self.collect_from_comprehension_generators(&expr.generators);
            }
            ast::Expr::GeneratorExp(expr) => {
                self.has_comprehension = true;
                self.collect_from_expression(&expr.elt);
                self.collect_from_comprehension_generators(&expr.generators);
            }
            _ => {}
        }
    }

    fn collect_from_comprehension_generators(&mut self, generators: &[ast::Comprehension]) {
        for generator in generators {
            self.has_comprehension = true;
            self.reserve_names_from_expr(&generator.target);
            self.collect_from_expression(&generator.iter);
            for condition in &generator.ifs {
                self.collect_from_expression(condition);
            }
        }
    }

    fn into_plan(self, qualified_name: String, range: Option<FunctionRange>) -> FunctionPlan {
        let mut generator = ShortNameGenerator::new(self.reserved);
        let mut renames = Vec::with_capacity(self.locals.len());

        for name in &self.locals {
            let replacement = generator.next();
            renames.push(RenameEntry {
                original: name.clone(),
                renamed: replacement,
            });
        }

        let mut excluded: Vec<String> = self
            .excluded
            .union(&self.declared_exclusions)
            .cloned()
            .collect();
        excluded.sort();
        excluded.dedup();

        FunctionPlan {
            qualified_name,
            locals: self.locals,
            renames,
            excluded,
            range,
            has_nested_functions: self.has_nested_functions,
            has_imports: self.has_imports,
            has_match_statement: self.has_match_statement,
            has_comprehension: self.has_comprehension,
            nested: Vec::new(),
        }
    }
}

struct ShortNameGenerator {
    counter: usize,
    reserved: HashSet<String>,
    issued: HashSet<String>,
}

impl ShortNameGenerator {
    fn new(reserved: HashSet<String>) -> Self {
        Self {
            counter: 0,
            reserved,
            issued: HashSet::new(),
        }
    }

    fn next(&mut self) -> String {
        loop {
            let candidate = encode_identifier(self.counter);
            self.counter += 1;

            if self.reserved.contains(&candidate) || self.issued.contains(&candidate) {
                continue;
            }

            self.issued.insert(candidate.clone());
            return candidate;
        }
    }
}

fn encode_identifier(mut value: usize) -> String {
    let mut chars = Vec::new();
    loop {
        let rem = value % 26;
        #[allow(clippy::cast_possible_truncation)]
        chars.push((b'a' + rem as u8) as char);
        value /= 26;
        if value == 0 {
            break;
        }
        value -= 1;
    }
    chars.iter().rev().collect()
}

fn range_from_node<T: Ranged>(node: &T) -> FunctionRange {
    let text_range = node.range();
    FunctionRange {
        start: usize::from(text_range.start()),
        end: usize::from(text_range.end()),
    }
}

struct Replacement {
    start: usize,
    end: usize,
    text: String,
}

struct FunctionRewriter<'a> {
    source: &'a str,
    plans: &'a HashMap<String, FunctionPlan>,
    replacements: Vec<Replacement>,
    abort: bool,
}

impl<'a> FunctionRewriter<'a> {
    fn new(source: &'a str, plans: &'a HashMap<String, FunctionPlan>) -> Self {
        Self {
            source,
            plans,
            replacements: Vec::new(),
            abort: false,
        }
    }

    fn rewrite(mut self, suite: &[ast::Stmt]) -> Result<String> {
        self.visit_suite(suite, &mut Vec::new())?;
        if self.abort {
            Ok(self.source.to_string())
        } else {
            Ok(self.apply())
        }
    }

    fn visit_suite(&mut self, suite: &[ast::Stmt], path: &mut Vec<String>) -> Result<()> {
        for stmt in suite {
            match stmt {
                ast::Stmt::FunctionDef(func) => {
                    self.process_function(
                        &func.name,
                        &func.args,
                        func.returns.as_deref(),
                        &func.body,
                        path,
                    )?;
                }
                ast::Stmt::AsyncFunctionDef(func) => {
                    self.process_async_function(func, path)?;
                }
                ast::Stmt::ClassDef(class_def) => {
                    self.visit_class(class_def, path)?;
                }
                _ => {}
            }
        }
        Ok(())
    }

    fn visit_class(&mut self, class_def: &ast::StmtClassDef, path: &mut Vec<String>) -> Result<()> {
        path.push(class_def.name.to_string());
        self.visit_suite(&class_def.body, path)?;
        path.pop();
        Ok(())
    }

    fn process_async_function(
        &mut self,
        func: &ast::StmtAsyncFunctionDef,
        path: &mut Vec<String>,
    ) -> Result<()> {
        self.process_function(
            &func.name,
            &func.args,
            func.returns.as_deref(),
            &func.body,
            path,
        )
    }

    fn process_function(
        &mut self,
        name: &ast::Identifier,
        args: &ast::Arguments,
        returns: Option<&ast::Expr>,
        body: &[ast::Stmt],
        path: &mut Vec<String>,
    ) -> Result<()> {
        path.push(name.to_string());
        let qualified_name = path.join(".");

        if let Some(plan) = self.plans.get(&qualified_name) {
            if plan.has_match_statement {
                self.abort = true;
            } else if !plan.has_comprehension {
                self.rewrite_with_plan(plan, args, returns, body);
            }
        }

        // Visit nested scopes to apply their plans.
        self.visit_suite(body, path)?;

        path.pop();
        Ok(())
    }

    fn rewrite_with_plan(
        &mut self,
        plan: &FunctionPlan,
        args: &ast::Arguments,
        returns: Option<&ast::Expr>,
        body: &[ast::Stmt],
    ) {
        let Some(range) = &plan.range else {
            self.abort = true;
            return;
        };

        let renames: HashMap<&str, &str> = plan
            .renames
            .iter()
            .map(|entry| (entry.original.as_str(), entry.renamed.as_str()))
            .collect();

        if renames.is_empty() {
            return;
        }

        let excluded: HashSet<&str> = plan.excluded.iter().map(|name| name.as_str()).collect();
        let mut collector = OccurrenceCollector::new(self.source, range, renames, excluded);
        collector.visit_arguments(args);
        if let Some(annotation) = returns {
            collector.with_annotation(|visitor| visitor.visit_expr(annotation));
        }
        collector.visit_statements(body);

        if collector.abort {
            self.abort = true;
            return;
        }

        self.replacements.extend(collector.replacements);
    }

    fn apply(mut self) -> String {
        if self.replacements.is_empty() {
            return self.source.to_string();
        }
        self.replacements
            .sort_by(|a, b| b.start.cmp(&a.start).then(b.end.cmp(&a.end)));
        let mut result = self.source.to_string();
        for replacement in self.replacements {
            result.replace_range(replacement.start..replacement.end, &replacement.text);
        }
        result
    }
}

fn strip_docstrings(module_name: &str, source: &str) -> Result<String> {
    let suite = ast::Suite::parse(source, module_name)
        .map_err(|err| TsrsError::ParseError(err.to_string()))?;

    let mut ranges = Vec::new();
    collect_docstrings_in_suite(source, &suite, &mut ranges);

    if ranges.is_empty() {
        return Ok(source.to_string());
    }

    ranges.sort_by(|a, b| b.0.cmp(&a.0));

    let mut stripped = source.to_string();
    for (start, end) in ranges {
        stripped.replace_range(start..end, "");
    }

    Ok(stripped)
}

fn collect_docstrings_in_suite(
    source: &str,
    suite: &[ast::Stmt],
    ranges: &mut Vec<(usize, usize)>,
) {
    if let Some(first) = suite.first() {
        if is_docstring_stmt(first) {
            ranges.push(docstring_range(source, first));
        }
    }

    for stmt in suite {
        match stmt {
            ast::Stmt::FunctionDef(func) => collect_docstrings_in_suite(source, &func.body, ranges),
            ast::Stmt::AsyncFunctionDef(func) => {
                collect_docstrings_in_suite(source, &func.body, ranges)
            }
            ast::Stmt::ClassDef(class_def) => {
                collect_docstrings_in_suite(source, &class_def.body, ranges)
            }
            _ => {}
        }
    }
}

fn is_docstring_stmt(stmt: &ast::Stmt) -> bool {
    match stmt {
        ast::Stmt::Expr(ast::StmtExpr { value, .. }) => {
            matches!(
                value.as_ref(),
                ast::Expr::Constant(ast::ExprConstant {
                    value: ast::Constant::Str { .. },
                    ..
                })
            )
        }
        _ => false,
    }
}

fn docstring_range(source: &str, stmt: &ast::Stmt) -> (usize, usize) {
    let text_range = stmt.range();
    let mut start = usize::from(text_range.start());
    let mut end = usize::from(text_range.end());

    let bytes = source.as_bytes();

    while start > 0 {
        let previous = bytes[start - 1];
        if previous == b' ' || previous == b'\t' {
            start -= 1;
            continue;
        }
        if previous == b'\n' || previous == b'\r' {
            break;
        }
        break;
    }

    while end < bytes.len() {
        let current = bytes[end];
        if current == b' ' || current == b'\t' {
            end += 1;
            continue;
        }
        if current == b'\r' {
            end += 1;
            if end < bytes.len() && bytes[end] == b'\n' {
                end += 1;
            }
            break;
        }
        if current == b'\n' {
            end += 1;
            break;
        }
        break;
    }

    (start, end)
}

struct OccurrenceCollector<'a> {
    source: &'a str,
    function_range: &'a FunctionRange,
    renames: HashMap<&'a str, &'a str>,
    excluded: HashSet<&'a str>,
    replacements: Vec<Replacement>,
    in_annotation: bool,
    abort: bool,
}

impl<'a> OccurrenceCollector<'a> {
    fn new(
        source: &'a str,
        function_range: &'a FunctionRange,
        renames: HashMap<&'a str, &'a str>,
        excluded: HashSet<&'a str>,
    ) -> Self {
        Self {
            source,
            function_range,
            renames,
            excluded,
            replacements: Vec::new(),
            in_annotation: false,
            abort: false,
        }
    }

    fn with_annotation<F>(&mut self, visitor: F)
    where
        F: FnOnce(&mut Self),
    {
        let previous = self.in_annotation;
        self.in_annotation = true;
        visitor(self);
        self.in_annotation = previous;
    }

    fn visit_arguments(&mut self, args: &ast::Arguments) {
        for param in &args.posonlyargs {
            self.record_arg(&param.def);
            if let Some(default) = &param.default {
                self.visit_expr(default);
            }
        }
        for param in &args.args {
            self.record_arg(&param.def);
            if let Some(default) = &param.default {
                self.visit_expr(default);
            }
        }
        if let Some(vararg) = &args.vararg {
            self.record_arg(vararg);
        }
        for param in &args.kwonlyargs {
            self.record_arg(&param.def);
            if let Some(default) = &param.default {
                self.visit_expr(default);
            }
        }
        if let Some(kwarg) = &args.kwarg {
            self.record_arg(kwarg);
        }
    }

    fn visit_statements(&mut self, stmts: &[ast::Stmt]) {
        for stmt in stmts {
            self.visit_stmt(stmt);
            if self.abort {
                return;
            }
        }
    }

    #[allow(clippy::too_many_lines)]
    fn visit_stmt(&mut self, stmt: &ast::Stmt) {
        if self.abort {
            return;
        }

        match stmt {
            ast::Stmt::FunctionDef(func) => {
                let range = range_from_node(func);
                if let Some((start, end)) =
                    find_identifier_in_range(self.source, &range, func.name.as_ref())
                {
                    let name_range = FunctionRange { start, end };
                    self.record_identifier(func.name.as_ref(), name_range);
                } else {
                    self.abort = true;
                }
                // Skip body; handled in its own plan.
            }
            ast::Stmt::AsyncFunctionDef(func) => {
                let range = range_from_node(func);
                if let Some((start, end)) =
                    find_identifier_in_range(self.source, &range, func.name.as_ref())
                {
                    let name_range = FunctionRange { start, end };
                    self.record_identifier(func.name.as_ref(), name_range);
                } else {
                    self.abort = true;
                }
            }
            ast::Stmt::ClassDef(class_def) => {
                let range = range_from_node(class_def);
                if let Some((start, end)) =
                    find_identifier_in_range(self.source, &range, class_def.name.as_ref())
                {
                    let name_range = FunctionRange { start, end };
                    self.record_identifier(class_def.name.as_ref(), name_range);
                } else {
                    self.abort = true;
                }
            }
            ast::Stmt::Return(ret) => {
                if let Some(value) = &ret.value {
                    self.visit_expr(value);
                }
            }
            ast::Stmt::Assign(assign) => {
                for target in &assign.targets {
                    self.visit_expr(target);
                }
                self.visit_expr(&assign.value);
            }
            ast::Stmt::AnnAssign(assign) => {
                self.visit_expr(&assign.target);
                if let Some(value) = &assign.value {
                    self.visit_expr(value);
                }
                self.with_annotation(|collector| collector.visit_expr(&assign.annotation));
            }
            ast::Stmt::AugAssign(assign) => {
                self.visit_expr(&assign.target);
                self.visit_expr(&assign.value);
            }
            ast::Stmt::For(stmt_for) => {
                self.visit_expr(&stmt_for.target);
                self.visit_expr(&stmt_for.iter);
                self.visit_statements(&stmt_for.body);
                self.visit_statements(&stmt_for.orelse);
            }
            ast::Stmt::AsyncFor(stmt_for) => {
                self.visit_expr(&stmt_for.target);
                self.visit_expr(&stmt_for.iter);
                self.visit_statements(&stmt_for.body);
                self.visit_statements(&stmt_for.orelse);
            }
            ast::Stmt::While(stmt_while) => {
                self.visit_expr(&stmt_while.test);
                self.visit_statements(&stmt_while.body);
                self.visit_statements(&stmt_while.orelse);
            }
            ast::Stmt::If(stmt_if) => {
                self.visit_expr(&stmt_if.test);
                self.visit_statements(&stmt_if.body);
                self.visit_statements(&stmt_if.orelse);
            }
            ast::Stmt::With(stmt_with) => {
                for item in &stmt_with.items {
                    self.visit_expr(&item.context_expr);
                    if let Some(optional) = &item.optional_vars {
                        self.visit_expr(optional);
                    }
                }
                self.visit_statements(&stmt_with.body);
            }
            ast::Stmt::AsyncWith(stmt_with) => {
                for item in &stmt_with.items {
                    self.visit_expr(&item.context_expr);
                    if let Some(optional) = &item.optional_vars {
                        self.visit_expr(optional);
                    }
                }
                self.visit_statements(&stmt_with.body);
            }
            ast::Stmt::Expr(expr_stmt) => {
                self.visit_expr(&expr_stmt.value);
            }
            ast::Stmt::Try(stmt_try) => {
                self.visit_statements(&stmt_try.body);
                self.visit_statements(&stmt_try.orelse);
                self.visit_statements(&stmt_try.finalbody);
                for handler in &stmt_try.handlers {
                    self.visit_except_handler(handler);
                }
            }
            ast::Stmt::TryStar(stmt_try) => {
                self.visit_statements(&stmt_try.body);
                self.visit_statements(&stmt_try.orelse);
                self.visit_statements(&stmt_try.finalbody);
                for handler in &stmt_try.handlers {
                    self.visit_except_handler(handler);
                }
            }
            ast::Stmt::Raise(stmt_raise) => {
                if let Some(exc) = &stmt_raise.exc {
                    self.visit_expr(exc);
                }
                if let Some(cause) = &stmt_raise.cause {
                    self.visit_expr(cause);
                }
            }
            ast::Stmt::Assert(stmt_assert) => {
                self.visit_expr(&stmt_assert.test);
                if let Some(msg) = &stmt_assert.msg {
                    self.visit_expr(msg);
                }
            }
            ast::Stmt::Delete(stmt_delete) => {
                for target in &stmt_delete.targets {
                    self.visit_expr(target);
                }
            }
            ast::Stmt::TypeAlias(type_alias) => {
                self.with_annotation(|collector| collector.visit_expr(&type_alias.value));
            }
            ast::Stmt::Match(_) | ast::Stmt::Import(_) | ast::Stmt::ImportFrom(_) => {
                // Imports introduce bindings; record alias targets conservatively.
                self.visit_import(stmt);
            }
            _ => {}
        }
    }

    fn visit_import(&mut self, stmt: &ast::Stmt) {
        if self.abort {
            return;
        }

        match stmt {
            ast::Stmt::Import(import_stmt) => {
                for alias in &import_stmt.names {
                    let full_name = alias.name.to_string();
                    let binding = alias
                        .asname
                        .as_ref()
                        .map(std::string::ToString::to_string)
                        .unwrap_or_else(|| {
                            full_name
                                .split('.')
                                .next()
                                .unwrap_or(&full_name)
                                .to_string()
                        });

                    if alias.asname.is_some() {
                        continue;
                    }

                    if let Some(new_name) = self.renames.get(binding.as_str()) {
                        if binding != *new_name {
                            let range = range_from_node(alias);
                            if !full_name.contains('.') {
                                let replacement = format!("{full_name} as {new_name}");
                                self.replacements.push(Replacement {
                                    start: range.start,
                                    end: range.end,
                                    text: replacement,
                                });
                            }
                        }
                    }
                }
            }
            ast::Stmt::ImportFrom(import_from) => {
                for alias in &import_from.names {
                    if alias.name.to_string().as_str() == "*" {
                        continue;
                    }
                    let binding = alias.asname.as_ref().map_or_else(
                        || {
                            let full = alias.name.to_string();
                            full.split('.')
                                .next()
                                .map(std::string::ToString::to_string)
                                .unwrap_or(full)
                        },
                        std::string::ToString::to_string,
                    );

                    if alias.asname.is_some() {
                        continue;
                    }

                    if let Some(new_name) = self.renames.get(binding.as_str()) {
                        if binding != *new_name {
                            let range = range_from_node(alias);
                            let module_text = alias.name.to_string();
                            let replacement = format!("{module_text} as {new_name}");
                            self.replacements.push(Replacement {
                                start: range.start,
                                end: range.end,
                                text: replacement,
                            });
                        }
                    }
                }
            }
            _ => {}
        }
    }

    fn visit_except_handler(&mut self, handler: &ast::ExceptHandler) {
        if self.abort {
            return;
        }

        match handler {
            ast::ExceptHandler::ExceptHandler(ex_handler) => {
                if let Some(type_) = &ex_handler.type_ {
                    self.visit_expr(type_);
                }
                if let Some(name) = &ex_handler.name {
                    self.record_except_name(ex_handler, name.as_ref());
                }
                self.visit_statements(&ex_handler.body);
            }
        }
    }

    #[allow(clippy::too_many_lines)]
    fn visit_expr(&mut self, expr: &ast::Expr) {
        if self.abort {
            return;
        }

        match expr {
            ast::Expr::Name(expr_name) => {
                let range = range_from_node(expr_name);
                self.record_identifier(expr_name.id.as_ref(), range);
            }
            ast::Expr::BoolOp(expr_bool) => {
                for value in &expr_bool.values {
                    self.visit_expr(value);
                }
            }
            ast::Expr::BinOp(expr_bin) => {
                self.visit_expr(&expr_bin.left);
                self.visit_expr(&expr_bin.right);
            }
            ast::Expr::UnaryOp(expr_unary) => {
                self.visit_expr(&expr_unary.operand);
            }
            ast::Expr::Lambda(_) => {
                self.abort = true;
            }
            ast::Expr::IfExp(expr_if) => {
                self.visit_expr(&expr_if.test);
                self.visit_expr(&expr_if.body);
                self.visit_expr(&expr_if.orelse);
            }
            ast::Expr::List(expr_list) => {
                for elt in &expr_list.elts {
                    self.visit_expr(elt);
                }
            }
            ast::Expr::Tuple(expr_tuple) => {
                for elt in &expr_tuple.elts {
                    self.visit_expr(elt);
                }
            }
            ast::Expr::Set(expr_set) => {
                for elt in &expr_set.elts {
                    self.visit_expr(elt);
                }
            }
            ast::Expr::Dict(expr_dict) => {
                for key in expr_dict.keys.iter().flatten() {
                    self.visit_expr(key);
                }
                for value in &expr_dict.values {
                    self.visit_expr(value);
                }
            }
            ast::Expr::ListComp(expr) => {
                self.visit_expr(&expr.elt);
                self.visit_comprehension_generators(&expr.generators);
            }
            ast::Expr::SetComp(expr) => {
                self.visit_expr(&expr.elt);
                self.visit_comprehension_generators(&expr.generators);
            }
            ast::Expr::DictComp(expr) => {
                self.visit_expr(&expr.key);
                self.visit_expr(&expr.value);
                self.visit_comprehension_generators(&expr.generators);
            }
            ast::Expr::GeneratorExp(expr) => {
                self.visit_expr(&expr.elt);
                self.visit_comprehension_generators(&expr.generators);
            }
            ast::Expr::Await(expr_await) => {
                self.visit_expr(&expr_await.value);
            }
            ast::Expr::Yield(expr_yield) => {
                if let Some(value) = &expr_yield.value {
                    self.visit_expr(value);
                }
            }
            ast::Expr::YieldFrom(expr_yield) => {
                self.visit_expr(&expr_yield.value);
            }
            ast::Expr::Compare(expr_compare) => {
                self.visit_expr(&expr_compare.left);
                for comp in &expr_compare.comparators {
                    self.visit_expr(comp);
                }
            }
            ast::Expr::Call(expr_call) => {
                self.visit_expr(&expr_call.func);
                for arg in &expr_call.args {
                    self.visit_expr(arg);
                }
                for keyword in &expr_call.keywords {
                    self.visit_expr(&keyword.value);
                }
            }
            ast::Expr::Attribute(expr_attr) => {
                self.visit_expr(&expr_attr.value);
            }
            ast::Expr::Subscript(expr_sub) => {
                self.visit_expr(&expr_sub.value);
                self.visit_expr(&expr_sub.slice);
            }
            ast::Expr::Starred(expr_star) => {
                self.visit_expr(&expr_star.value);
            }
            ast::Expr::NamedExpr(expr_named) => {
                self.visit_expr(&expr_named.target);
                self.visit_expr(&expr_named.value);
            }
            ast::Expr::Slice(expr_slice) => {
                if let Some(lower) = &expr_slice.lower {
                    self.visit_expr(lower);
                }
                if let Some(upper) = &expr_slice.upper {
                    self.visit_expr(upper);
                }
                if let Some(step) = &expr_slice.step {
                    self.visit_expr(step);
                }
            }
            ast::Expr::FormattedValue(expr_format) => {
                self.visit_expr(&expr_format.value);
            }
            ast::Expr::JoinedStr(expr_joined) => {
                for value in &expr_joined.values {
                    self.visit_expr(value);
                }
            }
            ast::Expr::Constant(_) => {}
        }
    }

    fn visit_comprehension_generators(&mut self, generators: &[ast::Comprehension]) {
        for generator in generators {
            self.visit_expr(&generator.iter);
            for condition in &generator.ifs {
                self.visit_expr(condition);
            }
        }
    }

    fn record_arg(&mut self, arg: &ast::Arg) {
        let name = arg.arg.as_ref();
        let arg_range = range_from_node(arg);
        if let Some((start, end)) = find_identifier_in_range(self.source, &arg_range, name) {
            self.record_identifier(name, FunctionRange { start, end });
        } else {
            self.abort = true;
            return;
        }
        if let Some(annotation) = &arg.annotation {
            self.with_annotation(|collector| collector.visit_expr(annotation));
        }
    }

    fn record_identifier(&mut self, name: &str, node_range: FunctionRange) {
        if self.in_annotation {
            return;
        }
        if self.abort {
            return;
        }

        if self.excluded.contains(name) {
            return;
        }

        let new_name = match self.renames.get(name) {
            Some(new_name) if name != *new_name => *new_name,
            _ => return,
        };

        if node_range.start < self.function_range.start || node_range.end > self.function_range.end
        {
            self.abort = true;
            return;
        }

        let start = node_range.start;
        let end = node_range.end;

        if end > self.source.len() || start >= end {
            self.abort = true;
            return;
        }

        let slice = &self.source[start..end];
        if slice != name {
            self.abort = true;
            return;
        }

        self.replacements.push(Replacement {
            start,
            end,
            text: new_name.to_string(),
        });
    }

    fn record_except_name(&mut self, handler: &ast::ExceptHandlerExceptHandler, name: &str) {
        if self.abort {
            return;
        }

        let new_name = match self.renames.get(name) {
            Some(new_name) if name != *new_name => *new_name,
            _ => return,
        };

        let handler_range = range_from_node(handler);
        if let Some((start, end)) = find_except_name_range(self.source, &handler_range, name) {
            self.replacements.push(Replacement {
                start,
                end,
                text: new_name.to_string(),
            });
        } else {
            self.abort = true;
        }
    }
}

fn find_identifier_in_range(
    source: &str,
    range: &FunctionRange,
    name: &str,
) -> Option<(usize, usize)> {
    let start = range.start.min(source.len());
    let end = range.end.min(source.len());
    if start >= end {
        return None;
    }

    let slice = &source[start..end];
    let mut offset = 0usize;
    while let Some(rel_idx) = slice[offset..].find(name) {
        let idx = offset + rel_idx;
        let before = slice[..idx].chars().next_back();
        let after = slice[idx + name.len()..].chars().next();
        if is_identifier_boundary(before, after) {
            return Some((start + idx, start + idx + name.len()));
        }
        offset = idx + 1;
    }

    None
}

fn find_except_name_range(
    source: &str,
    handler_range: &FunctionRange,
    name: &str,
) -> Option<(usize, usize)> {
    let start = handler_range.start.min(source.len());
    let end = handler_range.end.min(source.len());
    if start >= end {
        return None;
    }

    let slice = &source[start..end];
    let mut offset = 0usize;
    while let Some(rel_idx) = slice[offset..].find(name) {
        let idx = offset + rel_idx;
        let prefix = slice[..idx].trim_end();
        if prefix.ends_with("as")
            && is_identifier_boundary(
                slice[..idx].chars().next_back(),
                slice[idx + name.len()..].chars().next(),
            )
        {
            return Some((start + idx, start + idx + name.len()));
        }
        offset = idx + 1;
    }

    None
}

fn is_identifier_boundary(prev: Option<char>, next: Option<char>) -> bool {
    let prev_ok = !prev.is_some_and(is_identifier_char);
    let next_ok = !next.is_some_and(is_identifier_char);
    prev_ok && next_ok
}

fn is_identifier_char(c: char) -> bool {
    c == '_' || c.is_ascii_alphanumeric()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plans_parameters_and_locals() {
        let source = r#"
def outer(value, *, option=None):
    temp = value + 1
    for idx in range(3):
        result = temp + idx
    with context() as handle:
        extra = handle.do()
    return result + extra
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert_eq!(plan.functions.len(), 1);

        let outer = &plan.functions[0];
        assert_eq!(outer.qualified_name, "outer");
        assert_eq!(
            outer.locals,
            vec!["value", "option", "temp", "idx", "result", "handle", "extra"]
        );
        assert_eq!(outer.renames.len(), outer.locals.len());
        assert_eq!(outer.renames[0].renamed, "a");
        assert_eq!(outer.renames[1].renamed, "b");
        // ensure reserved names recorded when encountered
        assert!(!outer.excluded.contains(&"context".to_string()));
        assert!(!outer.has_nested_functions);
        assert!(!outer.has_imports);
        assert!(outer.range.is_some());
    }

    #[test]
    fn plans_nested_functions() {
        let source = r#"
def outer():
    x = 1
    def inner(y):
        z = y + x
        return z
    return inner(2)
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert_eq!(plan.functions.len(), 2);

        let outer = &plan.functions[0];
        assert_eq!(outer.qualified_name, "outer");
        assert!(outer.locals.is_empty());
        assert!(outer.renames.is_empty());
        assert!(outer.has_nested_functions);
        assert!(!outer.has_imports);
        assert_eq!(outer.nested.len(), 1);
        assert_eq!(outer.nested[0].qualified_name, "outer.inner");

        let inner = &plan.functions[1];
        assert_eq!(inner.qualified_name, "outer.inner");
        assert_eq!(inner.locals, vec!["y", "z"]);
        assert_eq!(inner.renames[0].renamed, "a");
        assert_eq!(inner.renames[1].renamed, "b");
        assert!(!inner.has_nested_functions);
        assert!(!inner.has_imports);
        assert!(inner.range.is_some());
    }

    #[test]
    fn plan_records_globals_and_nonlocals() {
        let source = r#"
G = 0

def outer():
    global G
    x = 1
    def inner():
        nonlocal x
        return x
    return x
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert_eq!(plan.functions.len(), 2);

        let outer = plan
            .functions
            .iter()
            .find(|f| f.qualified_name == "outer")
            .expect("outer plan present");
        assert!(outer.excluded.contains(&"G".to_string()));

        let inner = plan
            .functions
            .iter()
            .find(|f| f.qualified_name == "outer.inner")
            .expect("inner plan present");
        assert!(inner.excluded.contains(&"x".to_string()));
    }

    #[test]
    fn rewrite_nested_functions_preserves_closure() {
        let source = r#"
def outer(value):
    captured = value * 2
    def inner(extra):
        total = captured + extra
        return total
    result = inner(value)
    return result
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("def outer(a):"));
        assert!(rewritten.contains("def inner(a):"));
        assert!(rewritten.contains("captured = a * 2"));
        assert!(rewritten.contains("b = captured + a"));
        assert!(rewritten.contains("b = inner(a)"));
    }

    #[test]
    fn rewrite_plain_import_adds_alias() {
        let source = r#"
def loader(path):
    import json
    data = json.load(open(path))
    return data
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("import json as b"));
        assert!(rewritten.contains("b.load(open(a))"));
    }

    #[test]
    fn rewrite_applies_simple_plan() {
        let source = r#"
def identity(value):
    result = value + 1
    return result
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        let expected = r#"
def identity(a):
    b = a + 1
    return b
"#;
        assert_eq!(rewritten, expected);
    }

    #[test]
    fn rewrite_with_plan_matches_rewrite_source() {
        let source = r#"
def identity(value):
    result = value + 1
    return result
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        let via_source = Minifier::rewrite_source("sample", source).unwrap();
        let via_plan = Minifier::rewrite_with_plan("sample", source, &plan).unwrap();
        assert_eq!(via_source, via_plan);
    }

    #[test]
    fn rewrite_noop_with_nested_function() {
        let source = r#"
def wrapper(value):
    def inner(x):
        return x + value
    return inner(value)
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("def wrapper(value):"));
        assert!(rewritten.contains("def inner(a):"));
        assert!(rewritten.contains("return a + value"));
        assert!(rewritten.contains("return inner(value)"));
    }

    #[test]
    fn rewrite_handles_import_alias() {
        let source = r#"
def loader(path):
    import json as j
    data = j.load(path)
    return data
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert!(plan.functions[0].excluded.contains(&"j".to_string()));
        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("import json as j"));
        assert!(rewritten.contains("j.load(a)"));
    }

    #[test]
    fn rewrite_handles_from_import_without_alias() {
        let source = r#"
def join(parts):
    from os import path
    return path.join(*parts)
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("from os import path as b"));
        assert!(rewritten.contains("return b.join(*a)"));
    }

    #[test]
    fn rewrite_handles_from_import_alias() {
        let source = r#"
def normalize(parts):
    from os.path import join as join_path
    return join_path(*parts)
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert!(plan.functions[0]
            .excluded
            .contains(&"join_path".to_string()));
        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("from os.path import join as join_path"));
        assert!(rewritten.contains("return join_path(*a)"));
    }

    #[test]
    fn rewrite_handles_comprehension() {
        let source = r#"
def transform(data, offset):
    threshold = offset - 1
    return [value + offset for value in data if value > threshold]
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert_eq!(rewritten, source);
    }

    #[test]
    fn rewrite_respects_global_and_nonlocal() {
        let source = r#"
counter = 0

def outer(value):
    global counter
    total = value + counter
    counter = total
    def inner():
        nonlocal total
        total = total + 1
        return total
    return inner()
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("global counter"));
        assert!(rewritten.contains("nonlocal total"));
        assert!(rewritten.contains("total = a + counter"));
        assert!(rewritten.contains("counter = total"));
        assert!(rewritten.contains("total = total + 1"));
        assert!(rewritten.contains("def inner():"));
    }

    #[test]
    fn annassign_annotation_not_renamed() {
        let source = r#"
def assign(value):
    data: value = value
    return data
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("def assign(a):"));
        assert!(rewritten.contains("b: value = a"));
        assert!(rewritten.contains("return b"));
    }

    #[test]
    fn arg_annotation_not_renamed() {
        let source = r#"
def annotate(value: value) -> value:
    return value
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("def annotate(a: value) -> value:"));
        assert!(rewritten.contains("return a"));
    }

    #[test]
    fn rewrite_skips_from_import_star() {
        let source = r#"
from tools import *

def outer(value):
    helper = value + 1
    return helper
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("from tools import *"));
        assert!(rewritten.contains("def outer(a):"));
        assert!(rewritten.contains("b = a + 1"));
    }

    #[test]
    fn rewrite_handles_import_alias_mixture() {
        let source = r#"
def combine(a):
    import json
    import yaml as y
    data = json.dumps(a)
    return y.safe_load(data)
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert!(plan.functions[0].excluded.contains(&"y".to_string()));
        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("import json as b"));
        assert!(rewritten.contains("import yaml as y"));
        assert!(rewritten.contains("c = b.dumps(a)"));
        assert!(rewritten.contains("return y.safe_load(c)"));
    }

    #[test]
    fn rewrite_strips_module_and_function_docstrings() {
        let source = "\"\"\"Module doc\"\"\"\n\n\ndef demo(value):\n    \"\"\"Function doc\"\"\"\n    return value\n";

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        let expected = r#"

def demo(a):
    return a
"#;
        assert_eq!(rewritten, expected);
    }

    #[test]
    fn rewrite_strips_class_docstrings() {
        let source = "\"\"\"Module doc\"\"\"\n\n\nclass Demo:\n    \"\"\"Class doc\"\"\"\n\n    def value(self):\n        \"\"\"Method doc\"\"\"\n        return 1\n";

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        let expected = r#"

class Demo:

    def value(self):
        return 1
"#;
        assert_eq!(rewritten, expected);
    }

    #[test]
    fn rewrite_preserves_non_docstring_literals() {
        let source = r#"
def demo():
    helper = "keep me"
    return helper
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("= \"keep me\""));
    }

    #[test]
    fn rewrite_strips_nested_function_docstrings() {
        let source = "def outer():\n    \"\"\"Outer doc\"\"\"\n    def inner():\n        \"\"\"Inner doc\"\"\"\n        return 1\n    return inner()\n";

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(!rewritten.contains("Outer doc"));
        assert!(!rewritten.contains("Inner doc"));
        assert!(rewritten.contains("def outer():"));
        assert!(rewritten.contains("def inner():"));
        assert!(rewritten.contains("return inner()"));
    }

    #[test]
    fn rewrite_strips_async_function_docstrings() {
        let source = "async def fetch():\n    \"\"\"Fetch doc\"\"\"\n    return 1\n";

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(!rewritten.contains("Fetch doc"));
        assert!(rewritten.contains("async def fetch():"));
        assert!(rewritten.contains("return 1"));
    }

    #[test]
    fn rewrite_strips_docstrings_with_decorators() {
        let source = "@decorator\nclass Demo:\n    \"\"\"Class doc\"\"\"\n\n    @property\n    def value(self):\n        \"\"\"Property doc\"\"\"\n        return 1\n";

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.starts_with("@decorator"));
        assert!(rewritten.contains("@property"));
        assert!(rewritten.contains("def value(self):"));
        assert!(!rewritten.contains("Class doc"));
        assert!(!rewritten.contains("Property doc"));
    }

    #[test]
    fn rewrite_strips_multiline_docstrings_preserving_body() {
        let source = "def describe():\n    \"\"\"Line one.\n\n    Line two.\n    \"\"\"\n    return \"ok\"\n";

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(!rewritten.contains("Line one"));
        assert!(rewritten.contains("def describe():"));
        assert!(rewritten.contains("return \"ok\""));
    }

    #[test]
    fn plans_comprehension_sets_flag() {
        let source = r#"
def build(nums):
    return [n * 2 for n in nums]
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert_eq!(plan.functions.len(), 1);
        assert!(plan.functions[0].has_comprehension);
    }

    #[test]
    fn rewrite_bails_on_comprehension() {
        let source = r#"
def outer(values):
    total = 0
    def inner(items):
        return [item * 2 for item in items]
    total = total + len(values)
    return total
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("def outer(a):"));
        assert!(rewritten.contains("b = 0"));
        assert!(rewritten.contains("def inner(items):"));
        assert!(rewritten.contains("return [item * 2 for item in items]"));
        assert!(rewritten.contains("b = b + len(a)"));
    }

    #[test]
    fn rewrite_replacements_stable() {
        let source = r#"
def demo(alpha, beta):
    alpha_beta_gamma = alpha + beta
    alpha_beta = alpha + beta
    return alpha_beta_gamma + alpha_beta
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        let expected = r#"
def demo(a, b):
    c = a + b
    d = a + b
    return c + d
"#;
        assert_eq!(rewritten, expected);
    }

    #[test]
    fn rewrite_skips_dotted_import_without_alias() {
        let source = r#"
def make_path(parts):
    import os.path
    return os.path.join(*parts)
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert!(plan.functions[0].excluded.contains(&"os".to_string()));
        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("import os.path"));
        assert!(rewritten.contains("return os.path.join(*a)"));
    }

    #[test]
    fn rewrite_handles_from_import_multiple() {
        let source = r#"
def use_pkg(a, b):
    from pkg import thing, another
    return thing(a) + another(b)
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert!(rewritten.contains("from pkg import thing as c, another as d"));
        assert!(rewritten.contains("return c(a) + d(b)"));
    }

    #[test]
    fn rewrite_noop_with_match() {
        let source = r#"
def classify(value):
    match value:
        case 0:
            return "zero"
        case other:
            return other
    temp = value + 1
    return temp
"#;

        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert_eq!(rewritten, source);
    }

    #[test]
    fn comprehensions_preserve_outer_names() {
        let source = r#"
def make_lists(values):
    total = 0
    squares = [total + num for num in values]
    return squares, total
"#;

        let plan = Minifier::plan_from_source("sample", source).unwrap();
        assert!(plan.functions[0].has_comprehension);
        let rewritten = Minifier::rewrite_source("sample", source).unwrap();
        assert_eq!(rewritten, source);
    }
}
