# E2B Backend for Genesis

This directory demonstrates using [E2B](https://e2b.dev) cloud sandboxes as the execution backend for Genesis experiments.

## What is E2B?

E2B provides isolated, ephemeral cloud sandboxes for code execution. Each sandbox is a fresh Linux environment that:
- Runs untrusted code safely
- Has no interference with other sandboxes
- Automatically cleans up after timeout
- Supports parallel execution (10+ simultaneous sandboxes)

## Quick Start

```bash
# 1. Install E2B
pip install e2b

# 2. Set your API key (get from https://e2b.dev)
export E2B_API_KEY=your_api_key

# 3. Run the demo
python demo_e2b_backend.py
```

## Three Ways to Use E2B with Genesis

### 1. CLI with Hydra (Simplest)

```bash
# Use existing E2B variant
genesis_launch +variant=squeeze_hnsw_e2b

# Or override cluster config
genesis_launch +task=circle_packing +cluster=e2b

# Full customization
genesis_launch \
    +task=circle_packing \
    +cluster=e2b \
    job_config.timeout=300 \
    job_config.dependencies="[numpy,scipy]" \
    evo_config.max_parallel_jobs=10
```

### 2. Python API

```python
from genesis.core import EvolutionRunner, EvolutionConfig
from genesis.launch import E2BJobConfig
from genesis.database import DatabaseConfig

runner = EvolutionRunner(
    evo_config=EvolutionConfig(
        job_type="e2b",
        num_generations=100,
        max_parallel_jobs=10,
    ),
    job_config=E2BJobConfig(
        eval_program_path="evaluate.py",
        template="base",
        timeout=300,
        dependencies=["numpy", "scipy"],
    ),
    db_config=DatabaseConfig(num_islands=4),
    task_name="my_optimization",
)

best_program, best_score = runner.run()
```

### 3. Direct E2B Module

```python
from genesis.launch.e2b import (
    submit_with_files,
    download_results,
    cleanup_sandbox,
)

job_id = submit_with_files(
    log_dir="./results",
    exec_fname="program.py",
    eval_program_path="evaluate.py",
    timeout=120,
    template="base",
    dependencies=["numpy"],
)

download_results(job_id)
cleanup_sandbox(job_id)
```

## E2B Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `template` | E2B sandbox template | `"base"` |
| `timeout` | Max execution time (seconds) | `300` |
| `dependencies` | pip packages to install | `[]` |
| `additional_files` | Extra files to upload | `{}` |
| `env_vars` | Environment variables | `{}` |

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     Genesis Runner                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Sample    │  │   Mutate    │  │   Submit    │        │
│  │   Parent    │──│   (LLM)     │──│   to E2B    │        │
│  └─────────────┘  └─────────────┘  └──────┬──────┘        │
└────────────────────────────────────────────┼───────────────┘
                                             │
                    ┌────────────────────────┼────────────────┐
                    │        E2B Cloud       │                │
                    │   ┌────────────────────▼──────────┐     │
                    │   │         Sandbox 1             │     │
                    │   │  ┌──────────┐  ┌──────────┐  │     │
                    │   │  │ main.py  │  │evaluate.py│ │     │
                    │   │  └────┬─────┘  └─────┬────┘  │     │
                    │   │       └───────┬──────┘       │     │
                    │   │               ▼              │     │
                    │   │       metrics.json           │     │
                    │   │       correct.json           │     │
                    │   └──────────────────────────────┘     │
                    │                                        │
                    │   ┌──────────────────────────────┐     │
                    │   │         Sandbox 2             │     │
                    │   │         (parallel)            │     │
                    │   └──────────────────────────────┘     │
                    │              ...                       │
                    └────────────────────────────────────────┘
```

## Files in This Demo

- `demo_e2b_backend.py` - Comprehensive demo of all E2B integration methods
- `run_circle_packing_e2b.py` - Run circle packing with E2B backend
- `README.md` - This file

## Configuration Files

- `configs/cluster/e2b.yaml` - Base E2B cluster config
- `configs/variant/squeeze_hnsw_e2b.yaml` - Example E2B variant

## Benefits of E2B Backend

| Feature | Local | E2B |
|---------|-------|-----|
| Isolation | ❌ | ✅ |
| Parallel | Limited | ✅ |
| Setup | None | Simple |
| Cost | Free | Pay-per-use |
| Cleanup | Manual | Automatic |
| Safe for untrusted code | ❌ | ✅ |

## Troubleshooting

**"E2B_API_KEY not set"**
```bash
export E2B_API_KEY=your_api_key
```

**"E2B package not installed"**
```bash
pip install e2b
```

**"Sandbox timeout"**
Increase timeout in config:
```yaml
job_config:
  timeout: 600  # 10 minutes
```

**"Dependencies missing in sandbox"**
Add to dependencies list:
```yaml
job_config:
  dependencies:
    - numpy
    - scipy
    - your-package
```
