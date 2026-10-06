# API Reference

This document describes the public API of the **tsrs** library for programmatic use.

## Overview

The tsrs library provides Rust modules for analyzing Python code and virtual environments. It can be used as a library in other Rust projects or integrated with Python via PyO3.

## Core Modules

### venv Module

Analyze Python virtual environments and discover installed packages.

```rust
use tsrs::venv::{VenvAnalyzer, VenvInfo, PackageInfo};

// Create an analyzer for a virtual environment
let analyzer = VenvAnalyzer::new("/path/to/.venv")?;

// Get information about the venv
let venv_info = analyzer.analyze()?;

// Print package names
for package in &venv_info.packages {
    println!("Package: {}", package.name);
    if let Some(version) = &package.version {
        println!("  Version: {}", version);
    }
}
```

#### VenvAnalyzer

```rust
pub struct VenvAnalyzer {
    venv_path: PathBuf,
}

impl VenvAnalyzer {
    /// Create a new venv analyzer
    ///
    /// # Errors
    ///
    /// Returns an error if the venv path does not exist.
    pub fn new<P: AsRef<Path>>(path: P) -> Result<Self>;

    /// Analyze the venv and collect package information
    ///
    /// # Errors
    ///
    /// Returns an error if the analysis fails.
    pub fn analyze(&self) -> Result<VenvInfo>;
}
```

#### VenvInfo

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VenvInfo {
    /// Path to the venv
    pub path: PathBuf,
    /// Python version (if detectable)
    pub python_version: Option<String>,
    /// List of installed packages
    pub packages: Vec<PackageInfo>,
}
```

#### PackageInfo

```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct PackageInfo {
    /// Package name
    pub name: String,
    /// Package version
    pub version: Option<String>,
    /// Path to the package
    pub path: PathBuf,
}
```

### imports Module

Extract and track import statements from Python source code.

```rust
use tsrs::imports::{ImportCollector, ImportSet};
use std::path::Path;

// Create a collector
let mut collector = ImportCollector::new();

// Collect from a file
collector.collect_from_file("src/main.py")?;

// Get all imports
let imports = collector.get_imports();
for import in imports.get_imports() {
    println!("Import: {}", import);
}
```

#### ImportCollector

```rust
pub struct ImportCollector {
    imports: ImportSet,
}

impl ImportCollector {
    /// Create a new import collector
    #[must_use]
    pub fn new() -> Self;

    /// Parse a Python file and extract imports
    ///
    /// # Errors
    ///
    /// Returns an error if the file cannot be read or parsed.
    pub fn collect_from_file<P: AsRef<Path>>(&mut self, path: P) -> Result<()>;

    /// Parse Python source code and extract imports
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed.
    pub fn collect_from_source(&mut self, source: &str) -> Result<()>;

    /// Get collected imports
    #[must_use]
    pub fn get_imports(&self) -> ImportSet;
}
```

#### ImportSet

```rust
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ImportSet {
    pub imports: HashSet<String>,
}

impl ImportSet {
    /// Create a new import set
    #[must_use]
    pub fn new() -> Self;

    /// Add an import
    pub fn add(&mut self, import: String);

    /// Get all imports
    #[must_use]
    pub fn get_imports(&self) -> Vec<String>;
}
```

### callgraph Module

Analyze function definitions and calls to build call graphs.

```rust
use tsrs::callgraph::CallGraphAnalyzer;

// Create analyzer
let mut analyzer = CallGraphAnalyzer::new()?;

// Analyze a Python file
analyzer.analyze_file("module.py", "mypackage")?;

// Find unused functions
let unused = analyzer.find_unused_functions("mypackage");
for func_name in unused {
    println!("Unused: {}", func_name);
}

// Find external dependencies
let external = analyzer.find_external_dependencies();
for dep in external {
    println!("External dependency: {}", dep);
}
```

#### CallGraphAnalyzer

```rust
pub struct CallGraphAnalyzer {
    graphs: HashMap<String, PackageCallGraph>,
}

impl CallGraphAnalyzer {
    /// Create a new call graph analyzer
    ///
    /// # Errors
    ///
    /// Returns an error if regex compilation fails.
    pub fn new() -> Result<Self>;

    /// Analyze a Python file and build call graph
    ///
    /// # Errors
    ///
    /// Returns an error if the file cannot be read.
    pub fn analyze_file<P: AsRef<Path>>(&mut self, path: P, package: &str) -> Result<()>;

    /// Get all call graphs
    #[must_use]
    pub fn get_graphs(&self) -> &HashMap<String, PackageCallGraph>;

    /// Get call graph for a specific package
    #[must_use]
    pub fn get_graph(&self, package: &str) -> Option<&PackageCallGraph>;

    /// Find unused functions in a package
    #[must_use]
    pub fn find_unused_functions(&self, package: &str) -> HashSet<String>;

    /// Find all external dependencies
    #[must_use]
    pub fn find_external_dependencies(&self) -> HashSet<String>;
}
```

### slim Module

Create minimal virtual environments based on code analysis.

```rust
use tsrs::slim::VenvSlimmer;

// Create slimmer with default output
let mut slimmer = VenvSlimmer::new("./src", "./.venv")?;
slimmer.slim()?;
// Creates ./.venv-slim

// Or specify custom output
let mut slimmer = VenvSlimmer::new_with_output(
    "./src",
    "./.venv",
    "./output/.venv-slim"
)?;
slimmer.slim()?;
```

#### VenvSlimmer

```rust
pub struct VenvSlimmer {
    code_directory: PathBuf,
    source_venv: PathBuf,
    output_venv: PathBuf,
}

impl VenvSlimmer {
    /// Create a new venv slimmer that analyzes code_directory and slims source_venv
    ///
    /// # Errors
    ///
    /// Returns an error if either path does not exist.
    pub fn new<P: AsRef<Path>>(code_directory: P, source_venv: P) -> Result<Self>;

    /// Create a new venv slimmer with custom output path
    ///
    /// # Errors
    ///
    /// Returns an error if either path does not exist.
    pub fn new_with_output<P: AsRef<Path>>(
        code_directory: P,
        source_venv: P,
        output_venv: P,
    ) -> Result<Self>;

    /// Create a slim venv by analyzing code imports and copying only used packages
    ///
    /// # Errors
    ///
    /// Returns an error if the analysis or copying fails.
    pub fn slim(&self) -> Result<()>;
}
```

### minify Module

Analyze and rewrite Python code with minified local variable names.

```rust
use tsrs::minify::Minifier;

// Create a minification plan
let plan = Minifier::plan_from_source("mymodule", source_code)?;

// Rewrite code with the plan
let minified = Minifier::rewrite_with_plan("mymodule", source_code, &plan)?;
println!("{}", minified);
```

#### Minifier

```rust
pub struct Minifier;

impl Minifier {
    /// Build a plan for renaming local symbols in every function contained in the source
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed.
    pub fn plan_from_source(module_name: &str, source: &str) -> Result<MinifyPlan>;

    /// Rewrite source code by applying planned renames when no nested functions are present
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed or planned.
    pub fn rewrite_source(module_name: &str, source: &str) -> Result<String>;

    /// Rewrite using a precomputed plan, enabling plan curation before application
    ///
    /// # Errors
    ///
    /// Returns an error if the source cannot be parsed.
    pub fn rewrite_with_plan(
        module_name: &str,
        source: &str,
        plan: &MinifyPlan,
    ) -> Result<String>;
}
```

#### MinifyPlan

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MinifyPlan {
    pub module: String,
    pub keywords: HashSet<String>,
    pub functions: Vec<FunctionPlan>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionPlan {
    pub qualified_name: String,
    pub renames: Vec<RenameEntry>,
    pub range: Option<FunctionRange>,
    pub has_nested_functions: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RenameEntry {
    pub original: String,
    pub renamed: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct FunctionRange {
    pub start: usize,
    pub end: usize,
}
```

## Error Handling

All fallible operations return `Result<T>`:

```rust
use tsrs::error::{Result, TsrsError};

match some_operation() {
    Ok(value) => println!("Success: {}", value),
    Err(TsrsError::ParseError(msg)) => eprintln!("Parse error: {}", msg),
    Err(TsrsError::Io(err)) => eprintln!("IO error: {}", err),
    Err(TsrsError::InvalidVenvPath(msg)) => eprintln!("Invalid venv: {}", msg),
}
```

## Examples

### Complete Analysis Workflow

```rust
use tsrs::{
    venv::VenvAnalyzer,
    imports::ImportCollector,
    callgraph::CallGraphAnalyzer,
    slim::VenvSlimmer,
};

fn main() -> tsrs::error::Result<()> {
    // 1. Analyze venv
    let analyzer = VenvAnalyzer::new("./.venv")?;
    let venv_info = analyzer.analyze()?;
    println!("Found {} packages", venv_info.packages.len());

    // 2. Collect imports from code
    let mut import_collector = ImportCollector::new();
    import_collector.collect_from_file("./src/main.py")?;
    let imports = import_collector.get_imports();
    println!("Found {} imports", imports.get_imports().len());

    // 3. Build call graph
    let mut call_graph = CallGraphAnalyzer::new()?;
    call_graph.analyze_file("./src/main.py", "myapp")?;
    let unused = call_graph.find_unused_functions("myapp");
    println!("Found {} unused functions", unused.len());

    // 4. Create slim venv
    let slimmer = VenvSlimmer::new("./src", "./.venv")?;
    slimmer.slim()?;
    println!("Created slim venv");

    Ok(())
}
```

## Thread Safety

All public types are safe to use across threads. The library uses:
- `Arc` for shared state
- `Mutex` where needed for interior mutability
- No global mutable state

## Performance Notes

- **Parallel Processing**: Directory operations use `rayon` for parallelization
- **Caching**: Import sets use `HashSet` for O(1) lookups
- **Streaming**: Large files are streamed where possible
- **Allocation**: Minimal allocations in hot paths

## Version Compatibility

- **Rust**: 1.75+
- **Python**: 3.8+ (for code being analyzed)

## See Also

- [MINIFY_DESIGN.md](MINIFY_DESIGN.md) - Minification algorithm details
- [README.md](README.md) - Project overview and CLI usage
- [TESTING.md](TESTING.md) - Testing guide
