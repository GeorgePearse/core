#!/usr/bin/env python3
"""
Demonstration: Using E2B as the Backend for Genesis

This script shows how to use E2B cloud sandboxes as the execution backend
for Genesis experiments. E2B provides isolated, ephemeral environments
that enable highly parallel code evaluation.

There are THREE ways to use E2B with Genesis:
1. Direct E2B module usage (this demo)
2. Via the JobScheduler abstraction
3. Via Hydra config (CLI: genesis_launch +variant=<task>_e2b)

Prerequisites:
    pip install e2b
    export E2B_API_KEY=your_api_key  # Get from https://e2b.dev
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# Add Genesis to path if running from examples directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def demo_1_direct_e2b_usage():
    """
    Demo 1: Direct E2B Module Usage

    Shows how to use the low-level E2B functions to submit and monitor jobs.
    Useful for custom integrations or one-off evaluations.
    """
    print("\n" + "=" * 60)
    print("Demo 1: Direct E2B Module Usage")
    print("=" * 60)

    from genesis.launch.e2b import (
        submit_with_files,
        get_job_status,
        download_results,
        cleanup_sandbox,
        get_sandbox_info,
    )

    # Create a simple program to evaluate
    program_code = '''
"""Simple optimization function for E2B demo"""
import numpy as np

def optimize():
    """Return the best solution found."""
    # Simple optimization: find maximum of a quadratic
    x = np.linspace(-10, 10, 100)
    y = -(x - 2.5)**2 + 10  # Maximum at x=2.5, y=10
    best_idx = np.argmax(y)
    return {"x": float(x[best_idx]), "y": float(y[best_idx])}

def run_experiment():
    """Entry point for Genesis evaluation."""
    result = optimize()
    return result
'''

    evaluator_code = '''
"""Evaluator for E2B demo"""
import os
import sys
import json
import argparse
import importlib.util

def load_module(path):
    """Dynamically load a Python module."""
    spec = importlib.util.spec_from_file_location("program", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main(program_path, results_dir):
    os.makedirs(results_dir, exist_ok=True)

    try:
        # Load and run the program
        module = load_module(program_path)
        result = module.run_experiment()

        # Save metrics
        metrics = {
            "combined_score": result["y"],
            "public": {"best_x": result["x"], "best_y": result["y"]},
            "private": {}
        }

        with open(os.path.join(results_dir, "metrics.json"), "w") as f:
            json.dump(metrics, f, indent=2)

        with open(os.path.join(results_dir, "correct.json"), "w") as f:
            json.dump({"correct": True, "error": None}, f, indent=2)

        print(f"SUCCESS: Best y = {result['y']:.4f} at x = {result['x']:.4f}")

    except Exception as e:
        with open(os.path.join(results_dir, "metrics.json"), "w") as f:
            json.dump({"combined_score": 0.0, "error": str(e)}, f)
        with open(os.path.join(results_dir, "correct.json"), "w") as f:
            json.dump({"correct": False, "error": str(e)}, f)
        print(f"FAILED: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", default="main.py")
    parser.add_argument("--results_dir", default="results")
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
'''

    # Create temporary files
    with tempfile.TemporaryDirectory() as tmpdir:
        program_path = Path(tmpdir) / "program.py"
        eval_path = Path(tmpdir) / "evaluate.py"
        results_dir = Path(tmpdir) / "results"

        program_path.write_text(program_code)
        eval_path.write_text(evaluator_code)
        results_dir.mkdir()

        print(f"\nProgram: {program_path}")
        print(f"Evaluator: {eval_path}")
        print(f"Results: {results_dir}")

        # Submit to E2B
        print("\n>>> Submitting job to E2B sandbox...")
        job_id = submit_with_files(
            log_dir=str(results_dir),
            exec_fname=str(program_path),
            eval_program_path=str(eval_path),
            timeout=60,
            template="base",
            verbose=True,
            dependencies=["numpy"],
        )
        print(f"Job ID: {job_id}")

        # Check status
        status = get_job_status(job_id)
        print(f"Status: {'running' if status else 'completed'}")

        # Get sandbox info
        info = get_sandbox_info(job_id)
        print(f"Sandbox info: {json.dumps(info, indent=2, default=str)}")

        # Download results
        print("\n>>> Downloading results...")
        success = download_results(job_id, verbose=True)
        print(f"Download successful: {success}")

        # Read results
        metrics_file = results_dir / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file) as f:
                metrics = json.load(f)
            print(f"\nResults: {json.dumps(metrics, indent=2)}")

        # Cleanup
        cleanup_sandbox(job_id, verbose=True)
        print("\nSandbox cleaned up.")


def demo_2_job_scheduler():
    """
    Demo 2: Using the JobScheduler Abstraction

    The JobScheduler provides a unified interface for all backends
    (local, E2B). This is the recommended approach for
    production use.
    """
    print("\n" + "=" * 60)
    print("Demo 2: Using JobScheduler with E2B Backend")
    print("=" * 60)

    from genesis.launch import JobScheduler, E2BJobConfig

    # Configure E2B backend
    config = E2BJobConfig(
        eval_program_path="evaluate.py",  # Will be resolved relative to task
        template="base",
        timeout=120,
        dependencies=["numpy", "scipy"],
        additional_files={},
        env_vars={"PYTHONUNBUFFERED": "1"},
    )

    print("\nE2B Job Configuration:")
    print(f"  Template: {config.template}")
    print(f"  Timeout: {config.timeout}s")
    print(f"  Dependencies: {config.dependencies}")

    # Create scheduler (job_type="e2b" selects E2B backend)
    scheduler = JobScheduler(
        job_type="e2b",
        config=config,
        verbose=True,
    )

    print(f"\nScheduler created with job_type='e2b'")
    print("The scheduler provides these methods:")
    print("  - submit_async(exec_fname, results_dir) -> job_id")
    print("  - check_job_status(job) -> bool (True if running)")
    print("  - get_job_results(job_id, results_dir) -> Dict")
    print("  - run(exec_fname, results_dir) -> Tuple[Dict, float] (sync)")


def demo_3_hydra_config():
    """
    Demo 3: Using Hydra Configuration (CLI)

    Shows how to launch E2B experiments using Hydra config composition.
    This is the simplest way to use E2B with Genesis.
    """
    print("\n" + "=" * 60)
    print("Demo 3: Hydra Configuration for E2B")
    print("=" * 60)

    print("""
To run Genesis with E2B via CLI:

    # Option 1: Use an existing E2B variant
    genesis_launch +variant=squeeze_hnsw_e2b

    # Option 2: Override cluster config to use E2B
    genesis_launch +task=circle_packing +cluster=e2b

    # Option 3: Full customization
    genesis_launch \\
        +task=circle_packing \\
        +cluster=e2b \\
        job_config.timeout=300 \\
        job_config.dependencies="[numpy,scipy]" \\
        evo_config.max_parallel_jobs=10

Configuration files:
    configs/cluster/e2b.yaml        - Base E2B config
    configs/variant/*_e2b.yaml      - Task-specific E2B variants

Key E2B settings in config:
    job_config:
      _target_: genesis.launch.E2BJobConfig
      template: "base"           # E2B sandbox template
      timeout: 300               # Sandbox timeout (seconds)
      dependencies:              # pip packages to install
        - numpy
        - scipy
      additional_files: {}       # Extra files to upload
      env_vars: {}               # Environment variables

    evo_config:
      job_type: "e2b"            # Select E2B backend
      max_parallel_jobs: 10      # Parallel sandbox limit
""")


def demo_4_full_evolution():
    """
    Demo 4: Full Evolution Run with E2B

    Shows how to programmatically run a complete evolution
    using E2B as the backend.
    """
    print("\n" + "=" * 60)
    print("Demo 4: Full Evolution with E2B Backend")
    print("=" * 60)

    print("""
Example code for running a full evolution with E2B:

```python
from genesis.core import EvolutionRunner, EvolutionConfig
from genesis.launch import E2BJobConfig, JobScheduler
from genesis.database import DatabaseConfig

# Configure E2B job execution
job_config = E2BJobConfig(
    eval_program_path="evaluate.py",
    template="base",
    timeout=300,
    dependencies=["numpy", "scipy"],
)

# Configure database (multi-island model)
db_config = DatabaseConfig(
    num_islands=4,
    archive_size=50,
    db_type="sqlite",
)

# Configure evolution parameters
evo_config = EvolutionConfig(
    job_type="e2b",              # Use E2B backend
    num_generations=100,
    max_parallel_jobs=10,        # 10 sandboxes in parallel
    temperature=0.8,
    initial_code_path="initial.py",
)

# Create and run the evolution
runner = EvolutionRunner(
    evo_config=evo_config,
    job_config=job_config,
    db_config=db_config,
    task_name="my_optimization",
)

# This runs the evolutionary loop
best_program, best_score = runner.run()

print(f"Best score: {best_score}")
print(f"Best code:\\n{best_program.code}")
```
""")


def demo_5_e2b_with_mcp():
    """
    Demo 5: E2B via MCP Server

    Shows how to use E2B through the Genesis MCP server,
    which can be called from Claude Code or other MCP clients.
    """
    print("\n" + "=" * 60)
    print("Demo 5: E2B via Genesis MCP Server")
    print("=" * 60)

    print("""
The Genesis MCP server exposes E2B functionality:

1. List experiments (including E2B runs):
   mcp__genesis__list_experiments()

2. Launch E2B experiment:
   mcp__genesis__launch_experiment(
       variant="squeeze_hnsw_e2b",  # E2B variant
       generations=50
   )

3. Get metrics from E2B run:
   mcp__genesis__get_experiment_metrics(
       run_path="genesis_squeeze_hnsw_e2b/2025..."
   )

4. Read best code discovered:
   mcp__genesis__read_best_code(
       run_path="genesis_squeeze_hnsw_e2b/2025..."
   )

The MCP server handles E2B configuration automatically
based on the variant chosen.
""")


def main():
    """Run all demos."""
    print("\n" + "#" * 60)
    print("# Genesis E2B Backend Demonstration")
    print("#" * 60)

    # Check for E2B API key
    api_key = os.environ.get("E2B_API_KEY")
    if not api_key:
        print("\n" + "!" * 60)
        print("WARNING: E2B_API_KEY not set!")
        print("Set it with: export E2B_API_KEY=your_api_key")
        print("Get your key from: https://e2b.dev")
        print("!" * 60)
        run_live = False
    else:
        print(f"\nE2B API key detected: {api_key[:8]}...")
        run_live = True

    # Run demos
    if run_live:
        try:
            demo_1_direct_e2b_usage()
        except Exception as e:
            print(f"\nDemo 1 failed (E2B may not be available): {e}")
    else:
        print("\n[Skipping Demo 1 - requires E2B_API_KEY]")

    demo_2_job_scheduler()
    demo_3_hydra_config()
    demo_4_full_evolution()
    demo_5_e2b_with_mcp()

    print("\n" + "=" * 60)
    print("Demonstration complete!")
    print("=" * 60)
    print("""
Summary:
- E2B provides isolated cloud sandboxes for code evaluation
- Genesis supports E2B through multiple interfaces:
  1. Direct e2b module (genesis.launch.e2b)
  2. JobScheduler abstraction (genesis.launch.JobScheduler)
  3. Hydra config (genesis_launch +cluster=e2b)
  4. MCP server (genesis_launch_experiment)

Key benefits of E2B backend:
- Parallel execution (10+ sandboxes simultaneously)
- Isolated environments (no interference between jobs)
- Automatic cleanup (ephemeral sandboxes)
- No local resource constraints
- Safe code execution (untrusted code runs in sandbox)
""")


if __name__ == "__main__":
    main()
