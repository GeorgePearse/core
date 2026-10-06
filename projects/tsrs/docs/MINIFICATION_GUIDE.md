# Minification Guide

**What it does**: Analyze Python source code to automatically rename local variables to shorter names, reducing code size while maintaining functionality.

**Primary use case**: Reduce deployment size for serverless functions (AWS Lambda), Docker containers, or any size-constrained environment.

**Typical savings**: 5-15% code reduction depending on code style (more verbose code → more savings).

---

## Quick Start

### 1. Preview What Will Change

```bash
# See which variables would be renamed
tsrs-cli minify-plan path/to/module.py

# Visual diff showing before/after
tsrs-cli minify path/to/module.py --diff

# For entire directory (preview without writing)
tsrs-cli minify-dir ./src --dry-run --diff
```

### 2. Apply Minification

#### Single File
```bash
# Print minified output to stdout
tsrs-cli minify path/to/module.py

# Minify in place (updates the file)
tsrs-cli minify path/to/module.py --in-place

# Keep a backup
tsrs-cli minify path/to/module.py --in-place --backup-ext .bak
```

#### Entire Directory
```bash
# Create a minified copy of your codebase
tsrs-cli minify-dir ./src --out-dir ./src-minified

# Minify in place with backups
tsrs-cli minify-dir ./src --in-place --backup-ext .bak

# Skip test files and other paths
tsrs-cli minify-dir ./project \
  --include "project/src/**/*.py" \
  --exclude "project/tests/**" \
  --out-dir ./project-minified
```

### 3. Review Statistics

```bash
# See how many variables were renamed per file
tsrs-cli minify path/to/module.py --stats

# Machine-readable JSON output for CI/CD
tsrs-cli minify path/to/module.py --stats --json

# Summary for entire directory
tsrs-cli minify-dir ./src --stats --out-dir ./src-minified
```

---

## Understanding Minification

### What Gets Renamed ✅

Variables **local to functions** are renamed to shorter names:

```python
# Before
def calculate_total_price(items_list, tax_rate):
    subtotal_amount = sum(item.price for item in items_list)
    tax_amount = subtotal_amount * tax_rate
    final_total = subtotal_amount + tax_amount
    return final_total

# After
def calculate_total_price(items_list, tax_rate):
    a = sum(item.price for item in items_list)
    b = a * tax_rate
    c = a + b
    return c
```

**Naming sequence**: `a, b, c, ..., z, aa, ab, ac, ..., zz, aaa, ...`

### What Does NOT Get Renamed ❌

1. **Module-level names** (can be imported/referenced externally)
   ```python
   # NOT renamed - it's module-level
   GLOBAL_CONFIG = {"key": "value"}

   def my_function():
       pass  # my_function name NOT changed
   ```

2. **Global/nonlocal declarations**
   ```python
   def outer():
       x = 1
       def inner():
           nonlocal x  # x is NOT renamed in inner()
           x = 2
       inner()
   ```

3. **Dunder names** (`__init__`, `__str__`, etc.)
   ```python
   class MyClass:
       def __init__(self):  # NOT renamed
           self.value = 1
   ```

4. **Single underscore and private conventions**
   ```python
   _ = unused_value  # NOT renamed
   _private = 10     # NOT renamed
   ```

5. **Names imported from outside**
   ```python
   from utils import helper

   def process(data):
       result = helper(data)  # helper NOT renamed
       return result
   ```

### When Minification is Skipped ⏭️

The tool **skips files that have complex scope patterns** (these would require more sophisticated analysis):

- Functions containing nested functions or classes
- Functions with `global` or `nonlocal` declarations
- Comprehensions (list/dict/set)
- Any Python 3.10+ match statements

**Why**: Ensuring correctness is more important than aggressive optimization.

---

## Workflow Examples

### Example 1: Optimize a Lambda Function

You have a Lambda deployment that's close to the 50MB size limit:

```bash
# 1. Check current code size
du -sh ./lambda_function/

# 2. Create minified version
tsrs-cli minify-dir ./lambda_function --out-dir ./lambda_minified

# 3. Check new size
du -sh ./lambda_minified/

# 4. Package and deploy
cd ./lambda_minified
zip -r function.zip .
aws lambda update-function-code --function-name my-function --zip-file fileb://function.zip
```

**Expected result**: 8-12% reduction in code size

### Example 2: Reduce Docker Image Size

Minimize your Python application before containerization:

```dockerfile
# Dockerfile
FROM python:3.11-slim

# ... install dependencies ...

# Copy and minify application code
COPY src/ /app/src/
RUN tsrs-cli minify-dir /app/src --in-place

WORKDIR /app
CMD ["python", "src/main.py"]
```

### Example 3: Prepare Code for Review

Minify before sharing with security auditors (reduces noise):

```bash
# Create minified version for review
tsrs-cli minify-dir ./src --out-dir ./src-for-review

# Size comparison
echo "Original: $(du -sh ./src | cut -f1)"
echo "Minified: $(du -sh ./src-for-review | cut -f1)"

# Share ./src-for-review with auditors
```

### Example 4: CI/CD Pipeline Integration

Ensure code is minifiable and track statistics:

```bash
#!/bin/bash
# .github/workflows/build.yml

# Verify all files are minifiable (no bailouts)
tsrs-cli minify-dir ./src --dry-run --fail-on-bailout

# Generate stats for dashboard
tsrs-cli minify-dir ./src --stats --json > minify-stats.json

# Check file size reduction
original_size=$(du -sb ./src | cut -f1)
tsrs-cli minify-dir ./src --out-dir ./src-min
minified_size=$(du -sb ./src-min | cut -f1)
reduction=$((100 * (original_size - minified_size) / original_size))
echo "Size reduction: ${reduction}%"

# Fail if reduction is less than 2% (might indicate other issues)
if [ $reduction -lt 2 ]; then
    echo "ERROR: Expected at least 2% reduction"
    exit 1
fi
```

---

## Performance Characteristics

### Speed

- **Per-file overhead**: ~5-10ms (AST parsing + minification)
- **Typical 10K file project**: 30-60 seconds total
- **Memory usage**: Minimal (files processed independently)

### Scalability

```bash
# Process large directory with parallelization
# Automatically uses all CPU cores
tsrs-cli minify-dir ./large_project --out-dir ./output

# Control parallelization (if needed)
tsrs-cli minify-dir ./large_project --jobs 4 --out-dir ./output
```

---

## Understanding the Plan

A **minification plan** is a JSON file that documents exactly what variables get renamed:

```bash
# Generate a plan (without modifying code)
tsrs-cli minify-plan-dir ./src --out plan.json
```

**Plan structure**:
```json
{
  "format_version": "1",
  "python_version": "3.11",
  "functions": [
    {
      "name": "calculate_total_price",
      "lineno": 5,
      "local_names": ["items_list", "subtotal_amount", "tax_amount", "final_total"],
      "rename_map": {
        "subtotal_amount": "a",
        "tax_amount": "b",
        "final_total": "c"
      },
      "excluded_names": ["items_list"]
    }
  ],
  "python_keywords": [...],
  "builtins": [...]
}
```

**Benefits of plans**:
- Review minifications before applying them
- Version control (track what changes)
- Apply to multiple files/versions consistently

### Applying a Plan

```bash
# Create plan for your codebase
tsrs-cli minify-plan-dir ./src --out plan.json

# Review the plan (optional)
cat plan.json | jq '.functions[].rename_map'

# Apply to mirrored output
tsrs-cli apply-plan-dir ./src --plan plan.json --out-dir ./src-minified

# Or apply in place
tsrs-cli apply-plan-dir ./src --plan plan.json --in-place
```

---

## Troubleshooting

### Issue: "Skipped - bailout: nested function"

**Cause**: File contains a function inside another function

**Solution**: Not a problem—this file is just conservatively not minified. Continue with other files.

```bash
# See which files had bailouts
tsrs-cli minify-dir ./src --dry-run | grep "Bailout"
```

### Issue: Code behaves differently after minification

**This should not happen.** Local variable renaming doesn't change behavior—only names change.

**Debugging**:
1. Verify you minified the correct version
2. Check if tests pass:
   ```bash
   pytest tests/  # Run before minification
   tsrs-cli minify-dir ./src --in-place
   pytest tests/  # Run after minification (should pass)
   ```
3. Report as a bug if tests fail

### Issue: Minified code isn't smaller

**Possible causes**:
- Most code is module-level (can't minify module-level names)
- Many function parameters (parameters can't be minified)
- Many external function calls (imported names can't be minified)

**Solution**: This is fine—minification works best on code with many local variables. Not all code benefits equally.

---

## Best Practices

### ✅ Do

- **Minify before final packaging** (Lambda deployment, Docker build, etc.)
- **Keep original source** (minified is for deployment, not storage)
- **Test after minification** (though behavior shouldn't change)
- **Use `--backup-ext` when minifying in place** (easy to restore if needed)
- **Generate plans for code review** (reviewers can see what changes)

### ❌ Don't

- **Minify in your main source directory** (do it as a build step)
- **Commit minified code to version control** (minify on deployment)
- **Minify code with heavy metaprogramming** (safer to stay unminified)
- **Expect significant size reduction on module-level code** (works best on functions with many locals)

---

## Integration Examples

### With Setuptools/Poetry

```python
# setup.py
from setuptools import setup
import subprocess
import os

def minify_sources():
    """Minify source code before packaging"""
    if not os.path.exists("./src-minified"):
        subprocess.run(["tsrs-cli", "minify-dir", "./src", "--out-dir", "./src-minified"], check=True)

minify_sources()

setup(
    name="my-package",
    packages=["src_minified"],  # Use minified version for wheel
    # ...
)
```

### With Makefile

```makefile
.PHONY: build minify

minify:
	tsrs-cli minify-dir ./src --in-place --backup-ext .bak

build: minify
	python -m build

deploy: minify
	docker build -t my-app:latest .
	docker push my-app:latest
```

### With GitHub Actions

```yaml
name: Minify on Release

on:
  release:
    types: [created]

jobs:
  minify-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install tsrs
        run: cargo install tsrs-cli

      - name: Minify code
        run: tsrs-cli minify-dir ./src --out-dir ./src-minified

      - name: Build package
        run: |
          cd src-minified
          pip install .

      - name: Publish to PyPI
        run: python -m twine upload dist/*
```

---

## FAQ

**Q: Will minification break my code?**
A: No. Minification only renames local variables within functions. It doesn't change behavior, imports, or external APIs.

**Q: How much size reduction should I expect?**
A: 5-15% depending on code style. Code with many local variables benefits more.

**Q: Can I use minification in development?**
A: You could, but we recommend minifying only for deployment. Keep your source readable in version control.

**Q: What about code that uses locals() or locals inspection?**
A: Minified locals will have different names, but the functionality remains the same. This is by design (minification is conservative).

**Q: Does minification handle f-strings?**
A: Yes. f-string variable references are preserved correctly.

**Q: Can I selectively minify files?**
A: Yes. Use `--include` and `--exclude` patterns with `minify-dir`.

**Q: Is minification compatible with all Python versions?**
A: Yes, 3.7+. Plans are generated for the target Python version.

---

## See Also

- [Minification Design Specification](MINIFY_DESIGN.md) - Technical details about the algorithm
- [API Reference](API.md) - Using minification programmatically
- [Applications Overview](APPLICATIONS.md) - Other uses of the analysis framework
