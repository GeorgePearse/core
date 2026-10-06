# Custom Docker Environments Guide

This guide explains how to use custom Docker environments with the e2b sandbox executor to run isolated tests with specific CLI tools and dependencies.

## Overview

The retrocode test system supports three ways to configure test environments:

1. **Curated Templates** (Recommended for most users)
   - Pre-built Docker images optimized for common use cases
   - Zero configuration - just specify the template name
   - Fast startup times due to caching

2. **Custom Dockerfiles** (For specialized environments)
   - Full control over environment setup
   - Supports any tools, programming languages, or system configurations
   - Automatically cached and reused

3. **Runtime Configuration** (For dynamic customization)
   - Inject environment variables at test runtime
   - Override resource limits per test
   - Control networking and sandbox persistence

## Curated Templates

### Available Templates

#### `base` (Default)
Minimal Python 3.11 environment with essential dependencies.

**Includes:**
- Python 3.11
- pip package manager
- anthropic SDK (≥0.18.0)
- pydantic (≥2.0)
- pyyaml (≥6.0)

**Use when:** You only need Python and the Anthropic SDK

**Example test suite:**
```yaml
test_suite:
  name: "Basic Claude API Tests"
  model_under_test: "claude-3-5-sonnet-20241022"
  metadata:
    sandbox_environment:
      template: "base"
      timeout_seconds: 300
```

#### `claude-tools` (Full-featured)
Complete environment with all CLI tools referenced in CLAUDE.md instructions.

**Includes:**
- Everything from `base`
- ripgrep (rg) 14.1.0 - Fast recursive grep
- fd-find (fd) 10.1.0 - User-friendly find alternative
- ast-grep 0.21.2 - AST-based code search
- uv (latest) - Fast Python package manager
- fzf 0.48.0 - Fuzzy finder
- jq 1.7 - JSON query tool
- yq 4.40.5 - YAML/XML query tool

**Use when:** Tests need access to file searching, code analysis, or data transformation tools

**Example test suite:**
```yaml
test_suite:
  name: "Claude with CLI Tools"
  model_under_test: "claude-3-5-sonnet-20241022"
  metadata:
    sandbox_environment:
      template: "claude-tools"
      timeout_seconds: 600
      memory_limit_mb: 4096
```

### Finding Template Files

Curated template Dockerfiles are located in `.retrocode/environments/`:

```
.retrocode/
├── environments/
│   ├── base.Dockerfile
│   ├── claude-tools.Dockerfile
│   └── [other curated templates]
└── cache/
    └── template-mapping.json
```

To list available curated templates:
```bash
ls .retrocode/environments/*.Dockerfile
```

## Custom Dockerfiles

### When to Use Custom Dockerfiles

Use custom Dockerfiles when:
- Your tests need specific language runtimes (Node.js, Go, Rust, etc.)
- You need custom system packages not in curated templates
- Your tests require specific software versions
- You need to compile dependencies from source
- You have specialized build requirements

### Creating a Custom Dockerfile

#### Basic Example: Node.js Environment

Create `.retrocode/environments/node.Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for agent SDK
RUN pip install --no-cache-dir \
    anthropic>=0.18.0 \
    pydantic>=2.0 \
    pyyaml>=6.0

# Install Rust and Cargo (needed for some Node tools)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
```

#### Advanced Example: Multi-Language Environment

Create `.retrocode/environments/multi-lang.Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config ca-certificates \
    git curl wget \
    # Python tools
    && rm -rf /var/lib/apt/lists/*

# Install Rust for compiled tools
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install CLI tools from source
RUN cargo install ripgrep@14.1.0 && cargo cache --autoclean
RUN cargo install fd-find@10.1.0 && cargo cache --autoclean

# Install Python tools via pip
RUN pip install --no-cache-dir \
    anthropic>=0.18.0 \
    pydantic>=2.0 \
    pyyaml>=6.0 \
    pytest>=7.0 \
    black>=22.0 \
    mypy>=0.990

# Set up working directory
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
```

### Dockerfile Best Practices

#### 1. Use Specific Versions
```dockerfile
# Good: Pinned versions for reproducibility
RUN cargo install ripgrep@14.1.0
RUN pip install anthropic==0.18.1 pydantic==2.0

# Avoid: Floating versions
# RUN cargo install ripgrep
# RUN pip install anthropic pydantic
```

#### 2. Minimize Image Size
```dockerfile
# Good: Combine RUN commands and clean up
RUN apt-get update && apt-get install -y package1 package2 \
    && rm -rf /var/lib/apt/lists/*

# Avoid: Multiple layers and leftover files
# RUN apt-get update
# RUN apt-get install -y package1
# RUN apt-get install -y package2
```

#### 3. Set Environment Variables
```dockerfile
# Enable unbuffered Python output for immediate logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Add Rust/Cargo to PATH
ENV PATH="/root/.cargo/bin:${PATH}"
```

#### 4. Include Verification Steps
```dockerfile
# Verify tools are installed correctly
RUN rg --version && fd --version && ast-grep --version
RUN python -c "import anthropic; print(anthropic.__version__)"
```

### Location Convention

Store custom Dockerfiles in `.retrocode/environments/` with descriptive names:

```
.retrocode/environments/
├── base.Dockerfile              # Curated: Minimal Python
├── claude-tools.Dockerfile      # Curated: Python + CLI tools
├── node.Dockerfile              # Custom: Node.js environment
├── rust.Dockerfile              # Custom: Rust environment
└── ml-training.Dockerfile       # Custom: ML with PyTorch
```

## Using Custom Dockerfiles in Test Suites

### Configuration via YAML

Specify a custom Dockerfile in your test suite metadata:

```yaml
test_suite:
  name: "Node.js Agent Tests"
  model_under_test: "claude-3-5-sonnet-20241022"
  metadata:
    sandbox_environment:
      custom_dockerfile: ".retrocode/environments/node.Dockerfile"
      timeout_seconds: 600
      memory_limit_mb: 4096
      environment_vars:
        NODE_ENV: "test"
        LOG_LEVEL: "debug"
```

### Configuration Fields

```yaml
sandbox_environment:
  # Template selection (use one or the other)
  template: "base"                          # Curated template name
  custom_dockerfile: ".retrocode/environments/custom.Dockerfile"  # Custom Dockerfile path

  # Resource limits
  timeout_seconds: 300                      # Test timeout in seconds
  memory_limit_mb: 2048                    # Memory limit in MB
  cpu_cores: 2                             # CPU core limit (optional)

  # Network and persistence
  enable_networking: true                  # Allow internet access
  preserve_on_error: false                 # Keep sandbox after failure for debugging

  # Environment variables
  environment_vars:
    CUSTOM_VAR: "value"
    LOG_LEVEL: "debug"
    API_ENDPOINT: "https://example.com"
```

## Caching and Performance

### Automatic Template Caching

The executor automatically caches templates for reuse:

1. **Curated templates**: Cached by template name
   - `base` → `tmpl_<hash_of_base_dockerfile>`
   - `claude-tools` → `tmpl_<hash_of_claude_tools_dockerfile>`

2. **Custom Dockerfiles**: Cached by content hash
   - Same Dockerfile content always produces same template ID
   - Different content gets a new template ID

### Cache Storage

Template mappings are stored in `.retrocode/cache/template-mapping.json`:

```json
{
  "curated_templates": {
    "base": {
      "description": "Minimal Python 3.11 environment with anthropic SDK",
      "dockerfile": ".retrocode/environments/base.Dockerfile",
      "template_id": "tmpl_abc123def456"
    },
    "claude-tools": {
      "description": "Full environment with CLI tools",
      "dockerfile": ".retrocode/environments/claude-tools.Dockerfile",
      "template_id": "tmpl_xyz789uvw012"
    }
  },
  "custom_templates": {
    "content_hash_1": {
      "template_id": "tmpl_custom123",
      "dockerfile_path": ".retrocode/environments/node.Dockerfile"
    }
  }
}
```

### Cache Hits and Misses

**Cache hits (fast, reuse existing template):**
- Same curated template name used in multiple tests
- Same custom Dockerfile content in different test runs
- Same content hash across different file paths

**Cache misses (build new template):**
- First time using a template
- Modified Dockerfile content (different hash)
- New custom Dockerfile

## Advanced Usage

### Runtime Environment Injection

Inject environment variables at test runtime without modifying Dockerfile:

```yaml
test_suite:
  name: "Tests with Runtime Config"
  metadata:
    sandbox_environment:
      template: "base"
      environment_vars:
        ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"  # Injected at runtime
        DEBUG: "true"
        DATABASE_URL: "postgresql://localhost/testdb"
```

**Note:** The ANTHROPIC_API_KEY is always automatically injected from the environment.

### Resource Customization Per Test

Different tests can use different resource limits:

```yaml
test_cases:
  - task: "Simple API call"
    assertions: [...]
    metadata:
      sandbox_environment:
        timeout_seconds: 30
        memory_limit_mb: 512

  - task: "Complex analysis"
    assertions: [...]
    metadata:
      sandbox_environment:
        timeout_seconds: 600
        memory_limit_mb: 8192
        cpu_cores: 4
```

### Building from Private Registries

For Dockerfiles that reference private registries:

```dockerfile
FROM my-private-registry.com/custom-image:v1.0

# ... rest of Dockerfile
```

Authentication is handled via Docker credentials in the e2b execution environment.

## Troubleshooting

### Template Build Failures

If a custom Dockerfile fails to build:

1. **Verify syntax**
   ```bash
   docker build -f .retrocode/environments/custom.Dockerfile -t test:latest .
   ```

2. **Check dependencies**
   ```dockerfile
   # Add verification step
   RUN your-tool --version && echo "Tool installed successfully"
   ```

3. **View logs**
   - e2b logs are printed in test output
   - Look for error messages during `docker build` phase

### Slow Template Building

If tests are slow:

1. **Check cache**
   ```bash
   cat .retrocode/cache/template-mapping.json
   ```

2. **Verify content hash consistency**
   - Small Dockerfile changes create new template ID
   - Consider using a version in the template name: `node-18.Dockerfile`

3. **Optimize Dockerfile**
   - Combine RUN commands
   - Put frequently-changing lines later in Dockerfile
   - Use `.dockerignore` to exclude unnecessary files

### Permission Issues

If tests fail with permission errors:

1. **Ensure working directory is writable**
   ```dockerfile
   WORKDIR /workspace
   RUN chmod 777 /workspace
   ```

2. **Run as non-root if needed**
   ```dockerfile
   RUN useradd -m -u 1000 testuser
   USER testuser
   ```

## Examples

### Example 1: Python with Data Science Libraries

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    anthropic>=0.18.0 \
    pydantic>=2.0 \
    pyyaml>=6.0 \
    numpy>=1.24.0 \
    pandas>=1.5.0 \
    scikit-learn>=1.2.0

WORKDIR /workspace
ENV PYTHONUNBUFFERED=1
```

### Example 2: Go Environment

```dockerfile
FROM golang:1.21-alpine

RUN apk add --no-cache git curl ca-certificates

RUN go install github.com/google/goimports@latest

WORKDIR /workspace
```

### Example 3: Complete ML Training Environment

```dockerfile
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3.11 python3-pip python3.11-venv \
    git curl build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    anthropic>=0.18.0 \
    torch>=2.0.0 \
    torchvision>=0.15.0 \
    transformers>=4.30.0 \
    pydantic>=2.0

WORKDIR /workspace
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0
```

## Next Steps

- **Phase 2:** Support for MCP (Model Context Protocol) servers in Dockerfiles
  - Automated MCP process management
  - Health checks and readiness probes
  - Configuration injection

- **Phase 3:** Template pre-building in CI/CD
  - Publish curated templates to registry
  - Cache warming for faster tests
  - Template versioning and rollback

## Reference

### Environment Variables

Variables automatically injected into sandboxes:
- `ANTHROPIC_API_KEY` - Anthropic API key (always injected)
- Additional variables from `sandbox_environment.environment_vars`

### Path Conventions

- **Dockerfile location:** `.retrocode/environments/<name>.Dockerfile`
- **Cache location:** `.retrocode/cache/template-mapping.json`
- **Instruction files:** Referenced in test suite metadata (usually `CLAUDE.md` or similar)

### API Reference

See `src/retrocode/executors/base.py` for `SandboxConfig` schema and validation.
