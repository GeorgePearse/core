#!/usr/bin/env python3
"""
Run Circle Packing Optimization with E2B Backend

This script demonstrates running the circle packing example
using E2B cloud sandboxes for evaluation.

Usage:
    # Set your E2B API key first
    export E2B_API_KEY=your_api_key

    # Run the demo
    python run_circle_packing_e2b.py
"""

import os
import sys
from pathlib import Path

# Add Genesis to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def create_e2b_config():
    """Create configuration for E2B-backed evolution."""
    from genesis.launch import E2BJobConfig

    return E2BJobConfig(
        eval_program_path="evaluate.py",
        template="base",
        timeout=120,  # 2 minutes per evaluation
        dependencies=["numpy"],
        additional_files={},
        env_vars={"PYTHONUNBUFFERED": "1"},
    )


def main():
    """Run circle packing with E2B backend."""
    print("=" * 60)
    print("Circle Packing Optimization with E2B Backend")
    print("=" * 60)

    # Check for API key
    if not os.environ.get("E2B_API_KEY"):
        print("\nERROR: E2B_API_KEY not set!")
        print("Please run: export E2B_API_KEY=your_api_key")
        print("Get your key from: https://e2b.dev")
        sys.exit(1)

    # Show configuration
    config = create_e2b_config()
    print(f"\nE2B Configuration:")
    print(f"  Template: {config.template}")
    print(f"  Timeout: {config.timeout}s")
    print(f"  Dependencies: {config.dependencies}")

    # Path to circle packing example
    example_dir = Path(__file__).parent.parent / "circle_packing"
    initial_py = example_dir / "initial.py"
    evaluate_py = example_dir / "evaluate.py"

    if not initial_py.exists():
        print(f"\nERROR: {initial_py} not found!")
        sys.exit(1)

    print(f"\nTask files:")
    print(f"  Initial code: {initial_py}")
    print(f"  Evaluator: {evaluate_py}")

    print("\n" + "-" * 60)
    print("To run full evolution with E2B, use:")
    print("-" * 60)
    print("""
    # Option 1: CLI with Hydra
    genesis_launch \\
        +task=circle_packing \\
        +cluster=e2b \\
        evo_config.num_generations=20 \\
        evo_config.max_parallel_jobs=5

    # Option 2: Python API
    from genesis.core import EvolutionRunner, EvolutionConfig
    from genesis.launch import E2BJobConfig
    from genesis.database import DatabaseConfig

    runner = EvolutionRunner(
        evo_config=EvolutionConfig(
            job_type="e2b",
            num_generations=20,
            max_parallel_jobs=5,
        ),
        job_config=E2BJobConfig(
            eval_program_path="evaluate.py",
            template="base",
            timeout=120,
            dependencies=["numpy"],
        ),
        db_config=DatabaseConfig(num_islands=2),
        task_name="circle_packing",
    )
    best = runner.run()
""")

    # Quick test: evaluate initial code in E2B
    print("\n" + "=" * 60)
    print("Testing: Evaluate initial.py in E2B sandbox")
    print("=" * 60)

    from genesis.launch.e2b import submit_with_files, download_results, cleanup_sandbox
    import tempfile
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir) / "results"
        results_dir.mkdir()

        print(f"\nSubmitting to E2B...")
        job_id = submit_with_files(
            log_dir=str(results_dir),
            exec_fname=str(initial_py),
            eval_program_path=str(evaluate_py),
            timeout=120,
            template="base",
            verbose=True,
            dependencies=["numpy"],
        )
        print(f"Job ID: {job_id}")

        print(f"\nDownloading results...")
        success = download_results(job_id, verbose=True)

        if success:
            metrics_file = results_dir / "metrics.json"
            correct_file = results_dir / "correct.json"

            if metrics_file.exists():
                with open(metrics_file) as f:
                    metrics = json.load(f)
                print(f"\nMetrics:")
                print(f"  Combined score: {metrics.get('combined_score', 'N/A')}")
                if "public" in metrics:
                    print(f"  Num circles: {metrics['public'].get('num_circles', 'N/A')}")

            if correct_file.exists():
                with open(correct_file) as f:
                    correct = json.load(f)
                print(f"\nValidation: {'PASSED' if correct.get('correct') else 'FAILED'}")
                if correct.get("error"):
                    print(f"  Error: {correct['error']}")

            # Show logs if available
            log_file = results_dir / "job_log.out"
            if log_file.exists():
                print(f"\nEvaluation log:")
                print("-" * 40)
                print(log_file.read_text()[:500])

        cleanup_sandbox(job_id, verbose=True)
        print("\nDone!")


if __name__ == "__main__":
    main()
