# Contributing to tsrs

Thank you for your interest in contributing to **tsrs** (Tree-Shaking in Rust for Python)! This document outlines the process for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and collaborative. We're building a tool to make Python deployments better for everyone.

## Getting Started

### Prerequisites

- Rust 1.75+ (check with `rustc --version`)
- Python 3.8+ (for testing)
- Git

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/GeorgePearse/tsrs.git
cd tsrs

# Build the project
cargo build --release

# Run tests
cargo test

# Run linting and formatting
cargo fmt
cargo clippy -- -W clippy::pedantic

# Check the pre-commit hook runs successfully
./target/release/tsrs-cli --help
```

## Making Changes

### Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with clear, focused commits
   ```bash
   git add <files>
   git commit -m "Description of changes"
   ```

3. **Ensure code quality**
   ```bash
   # Format code
   cargo fmt

   # Run linting (this runs automatically in pre-commit hook)
   cargo clippy -- -W clippy::pedantic

   # Run tests
   cargo test
   ```

4. **Push and open a PR**
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Guidelines

- Use clear, descriptive messages
- Start with a verb (Add, Fix, Refactor, etc.)
- Reference issues when relevant: `Fixes #123`
- Example: `Add support for nested function analysis in minify module`

### Testing Requirements

All contributions must include tests:

```bash
# Run all tests
cargo test

# Run tests with output
cargo test -- --nocapture

# Run specific test
cargo test test_name
```

## Code Standards

### Style Guide

- **Formatting**: Use `cargo fmt` (enforced via pre-commit hook)
- **Linting**: Must pass `cargo clippy -- -W clippy::pedantic`
- **Documentation**: Add doc comments to public APIs
  ```rust
  /// Brief description
  ///
  /// Longer explanation if needed.
  ///
  /// # Errors
  ///
  /// Describe what errors this function can return.
  pub fn my_function() -> Result<T> {
      // ...
  }
  ```

### Type Safety

- Write fully typed Python code for Rust implementations
- Use type annotations in all function signatures
- Leverage Rust's type system for compile-time safety

## Project Structure

```
tsrs/
├── src/
│   ├── lib.rs              # Library root, public API
│   ├── bin/cli.rs          # CLI binary
│   ├── venv.rs             # Virtual environment analysis
│   ├── imports.rs          # Import statement extraction
│   ├── callgraph.rs        # Function call graph analysis
│   ├── slim.rs             # Venv slimming implementation
│   ├── minify.rs           # Local variable minification
│   ├── error.rs            # Error types
│   └── lib.rs              # Library entry point
├── tests/                  # Integration tests
├── Cargo.toml              # Manifest
├── README.md               # Project overview
├── CONTRIBUTING.md         # This file
├── MINIFY_DESIGN.md        # Minify algorithm details
├── TESTING.md              # Testing guide
└── TEST_REPOS_SUMMARY.md   # Test repository documentation
```

## Key Modules

### venv.rs
Analyzes Python virtual environments to discover installed packages and their metadata.

### imports.rs
Parses Python source code to extract `import` and `from...import` statements. Uses rustpython-parser for AST analysis.

### callgraph.rs
Builds a call graph of functions within packages to identify unused/dead code.

### slim.rs
Creates minimal virtual environments by analyzing code imports and copying only used packages.

### minify.rs
Implements safe local variable renaming for Python code (minification) while preserving correctness.

## Architecture Decisions

### High Precision, Low Recall Philosophy

We prioritize **correctness over comprehensiveness**:

- **Never remove code** unless we're absolutely certain it's unused
- **Keep module-level exports** (they may be used externally)
- **Preserve public APIs** even if not directly called
- **Be conservative** with dynamic features and reflection

### Error Handling

- Use `Result<T>` for fallible operations
- Provide context in error messages
- Use custom error types via `thiserror`

## Documentation

When adding features, update relevant documentation:

- **Code comments**: Explain the "why" not the "what"
- **Doc comments**: Public API documentation
- **README.md**: Update usage examples
- **MINIFY_DESIGN.md**: Algorithm or design details
- **TESTING.md**: How to test your feature

## Performance Considerations

The project uses:
- **rayon**: Parallel processing for directory operations
- **rustpython-parser**: Fast Python AST parsing
- **regex**: Pattern matching for import statements
- **walkdir**: Efficient directory traversal

When optimizing:
1. Profile first with `cargo flamegraph`
2. Benchmark changes: `cargo bench`
3. Consider parallelization opportunities

## Troubleshooting

### Pre-commit Hook Failures

If the clippy pre-commit hook fails:

```bash
# Run clippy manually to see detailed output
cargo clippy -- -W clippy::pedantic

# Fix issues or suppress with #[allow(...)] if justified
# Then try committing again
```

### Test Failures

```bash
# Run tests with backtrace
RUST_BACKTRACE=1 cargo test

# Run specific failing test
cargo test failing_test_name -- --nocapture
```

## Getting Help

- **Documentation**: See README.md, MINIFY_DESIGN.md, TESTING.md
- **Issues**: Open an issue on GitHub with details
- **Discussions**: Use GitHub Discussions for questions

## Recognition

Contributors will be recognized in the project's CONTRIBUTORS file (once created).

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (TBD).

---

Thank you for making tsrs better! 🚀
