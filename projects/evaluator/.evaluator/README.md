# Retrocode Test System Configuration

This directory contains configuration and environment definitions for the retrocode test system.

## Directory Structure

```
.retrocode/
├── README.md                      # This file
├── DOCKERFILE_GUIDE.md            # Complete guide for Docker environments
├── environments/                  # Docker environment definitions
│   ├── base.Dockerfile            # Minimal Python environment (curated)
│   ├── claude-tools.Dockerfile    # Python + CLI tools (curated)
│   └── [custom Dockerfiles]       # Your custom environment definitions
└── cache/
    └── template-mapping.json      # Template ID cache (auto-managed)
```

## Quick Start

### Using Curated Templates

The simplest way to run tests in a sandbox:

```yaml
test_suite:
  name: "My Tests"
  model_under_test: "claude-3-5-sonnet-20241022"
  metadata:
    sandbox_environment:
      template: "base"              # Use the 'base' template
      timeout_seconds: 300
```

Available curated templates:
- **`base`** - Minimal Python 3.11 + anthropic SDK (default)
- **`claude-tools`** - Python 3.11 + all CLI tools (rg, fd, fzf, jq, yq, ast-grep, uv)

### Creating Custom Dockerfiles

For more specialized needs, create a custom Dockerfile in `environments/`:

```dockerfile
# .retrocode/environments/my-custom.Dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y your-tools
RUN pip install your-packages
WORKDIR /workspace
```

Then use it in your test suite:

```yaml
metadata:
  sandbox_environment:
    custom_dockerfile: ".retrocode/environments/my-custom.Dockerfile"
```

## Files

### DOCKERFILE_GUIDE.md
Complete guide covering:
- Available curated templates and their contents
- How to create custom Dockerfiles
- Best practices for Dockerfile development
- Caching and performance optimization
- Runtime configuration and environment variables
- Troubleshooting and examples

**Start here** if you need to create a custom Docker environment.

### environments/
Directory for Dockerfile definitions:
- **Curated templates** (included in repo)
  - `base.Dockerfile` - Minimal Python environment
  - `claude-tools.Dockerfile` - Full CLI tools environment
- **Custom templates** (you create these)
  - Store your custom Dockerfiles here
  - Use descriptive names: `node.Dockerfile`, `rust.Dockerfile`, etc.

### cache/template-mapping.json
Automatically managed cache of built templates:
- Maps template names/content hashes to e2b template IDs
- Speeds up test startup (reuses previously built templates)
- Do not edit manually - system updates it automatically

## Typical Workflow

### 1. Start with a Curated Template

```yaml
# test_suite.yaml
test_suite:
  name: "My Tests"
  metadata:
    sandbox_environment:
      template: "base"
```

### 2. Need Extra Tools? Try claude-tools

```yaml
metadata:
  sandbox_environment:
    template: "claude-tools"  # Includes rg, fd, fzf, etc.
```

### 3. Need Something Special? Create a Custom Dockerfile

1. Create `.retrocode/environments/my-env.Dockerfile`
2. Use it in your test suite:
   ```yaml
   metadata:
     sandbox_environment:
       custom_dockerfile: ".retrocode/environments/my-env.Dockerfile"
   ```

## Environment Variables

Environment variables can be injected at test runtime:

```yaml
metadata:
  sandbox_environment:
    template: "base"
    environment_vars:
      LOG_LEVEL: "debug"
      CUSTOM_VAR: "value"
```

**Note:** `ANTHROPIC_API_KEY` is automatically injected from your system environment.

## Performance and Caching

Templates are automatically cached based on:
- **Curated templates**: Template name (e.g., "base", "claude-tools")
- **Custom templates**: SHA-256 hash of Dockerfile content

This means:
- Same template across multiple tests: Fast (cache hit)
- Same custom Dockerfile content: Fast (cache hit)
- Modified Dockerfile: Rebuilt (cache miss)

Check cached templates: `cat .retrocode/cache/template-mapping.json`

## Common Tasks

### List available curated templates
```bash
ls .retrocode/environments/*.Dockerfile
```

### Create a Node.js environment
```bash
cat > .retrocode/environments/node.Dockerfile << 'EOF'
FROM python:3.11-slim
RUN apt-get update && apt-get install -y nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN pip install anthropic>=0.18.0 pydantic>=2.0 pyyaml>=6.0
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1
EOF
```

### Check template cache status
```bash
cat .retrocode/cache/template-mapping.json | jq '.'
```

### Clear template cache (optional)
```bash
rm .retrocode/cache/template-mapping.json
```
This will force rebuilding of all templates on next test run.

## Troubleshooting

**Q: Tests are slow**
- Check cache: `cat .retrocode/cache/template-mapping.json`
- If cache is empty, templates are being rebuilt
- Ensure Dockerfile content is consistent (small changes = new template ID)

**Q: Custom Dockerfile won't build**
- Test locally: `docker build -f .retrocode/environments/my.Dockerfile -t test:latest .`
- Check for syntax errors and missing dependencies
- Verify all files and packages are available

**Q: Environment variables not being set**
- Verify they're in `sandbox_environment.environment_vars`
- Check spelling (case-sensitive)
- `ANTHROPIC_API_KEY` is injected automatically from system env

## References

- **For detailed guides:** See `DOCKERFILE_GUIDE.md`
- **For API schema:** See `src/retrocode/executors/base.py` (SandboxConfig)
- **For implementation:** See `src/retrocode/executors/e2b.py` (E2BExecutor)

## Next Steps

- **Phase 2:** MCP (Model Context Protocol) server support in Dockerfiles
  - Run MCP servers inside test environments
  - Automatic process lifecycle management

- **Phase 3:** CI/CD integration
  - Pre-build templates in pipeline
  - Publish to template registry
  - Template versioning

## Contributing

When adding new curated templates:
1. Create in `.retrocode/environments/`
2. Use descriptive name and Dockerfile comments
3. Include verification steps
4. Document in `DOCKERFILE_GUIDE.md`
5. Add unit tests for template building/caching
