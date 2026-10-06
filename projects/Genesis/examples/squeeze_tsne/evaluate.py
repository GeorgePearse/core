"""
Evaluation script for t-SNE gradient optimization.

This evaluates the quality of t-SNE embeddings using:
1. Trustworthiness: How well local neighborhoods are preserved
2. Speed: Time to compute the embedding

Combined score = trustworthiness * speed_factor * 100
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np


def generate_test_data(n_samples: int = 200, n_features: int = 50, n_clusters: int = 5, seed: int = 42) -> np.ndarray:
    """Generate clustered test data for t-SNE evaluation."""
    np.random.seed(seed)

    samples_per_cluster = n_samples // n_clusters
    data = []

    for i in range(n_clusters):
        # Cluster center
        center = np.random.randn(n_features) * 10
        # Points around center
        cluster_points = center + np.random.randn(samples_per_cluster, n_features) * 0.5
        data.append(cluster_points)

    return np.vstack(data)


def compile_rust_program(rust_file: str, output_binary: str) -> tuple[bool, str]:
    """Compile Rust program with optimizations."""
    try:
        result = subprocess.run(
            ["rustc", "-O", "-o", output_binary, rust_file],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return False, f"Compilation failed:\n{result.stderr}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out"
    except FileNotFoundError:
        return False, "rustc not found"


def run_tsne_benchmark(
    binary_path: str,
    data: np.ndarray,
    output_file: str,
    timeout: int = 300,
) -> tuple[dict | None, float, str | None]:
    """Run t-SNE and return results."""
    # Write data to temp file
    data_file = output_file.replace(".json", "_data.txt")
    np.savetxt(data_file, data, fmt="%.6f")

    try:
        start_time = time.time()
        result = subprocess.run(
            [binary_path, data_file, output_file],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            return None, elapsed, f"Execution failed:\n{result.stderr}"

        # Parse results
        with open(output_file, "r") as f:
            results = json.load(f)

        return results, elapsed, None

    except subprocess.TimeoutExpired:
        return None, timeout, "Execution timed out"
    except json.JSONDecodeError as e:
        return None, 0.0, f"Failed to parse output: {e}"
    finally:
        # Cleanup data file
        if os.path.exists(data_file):
            os.remove(data_file)


def main(program_path: str, results_dir: str):
    """Main evaluation function for Genesis."""
    os.makedirs(results_dir, exist_ok=True)

    metrics_file = os.path.join(results_dir, "metrics.json")
    correct_file = os.path.join(results_dir, "correct.json")

    # Compile the Rust program
    binary_path = os.path.join(results_dir, "tsne_binary")
    success, error = compile_rust_program(program_path, binary_path)

    if not success:
        with open(metrics_file, "w") as f:
            json.dump({"combined_score": 0.0, "error": error}, f, indent=2)
        with open(correct_file, "w") as f:
            json.dump({"correct": False, "error": error}, f, indent=2)
        return {"combined_score": 0.0}, False, error

    # Run multiple evaluations with different data sizes
    all_trustworthiness = []
    all_times = []
    errors = []

    test_configs = [
        {"n_samples": 100, "n_features": 20, "seed": 42},
        {"n_samples": 150, "n_features": 30, "seed": 123},
        {"n_samples": 200, "n_features": 40, "seed": 456},
    ]

    for config in test_configs:
        data = generate_test_data(
            n_samples=config["n_samples"],
            n_features=config["n_features"],
            n_clusters=5,
            seed=config["seed"],
        )

        output_file = os.path.join(results_dir, f"tsne_output_{config['seed']}.json")
        results, elapsed, error = run_tsne_benchmark(binary_path, data, output_file)

        if error:
            errors.append(error)
            continue

        trust = results.get("trustworthiness", 0.0)
        all_trustworthiness.append(trust)
        all_times.append(elapsed)

    # Calculate combined score
    if not all_trustworthiness:
        combined_score = 0.0
        mean_trust = 0.0
        mean_time = 0.0
        is_correct = False
        final_error = "; ".join(errors) if errors else "No successful runs"
    else:
        mean_trust = np.mean(all_trustworthiness)
        mean_time = np.mean(all_times)

        # Trustworthiness should be > 0.5 for a valid embedding
        if mean_trust < 0.3:
            is_correct = False
            final_error = f"Trustworthiness too low: {mean_trust:.4f}"
            combined_score = 0.0
        else:
            is_correct = True
            final_error = None

            # Speed factor: faster = better (baseline ~10s for n=200)
            baseline_time = 10.0
            speed_factor = min(2.0, baseline_time / max(mean_time, 0.1))

            # Combined score: trustworthiness * speed_factor * 100
            combined_score = float(mean_trust * speed_factor * 100)

    # Save metrics
    metrics = {
        "combined_score": combined_score,
        "public": {
            "mean_trustworthiness": float(mean_trust),
            "mean_time_seconds": float(mean_time),
            "num_successful_runs": len(all_trustworthiness),
        },
        "private": {
            "all_trustworthiness": [float(t) for t in all_trustworthiness],
            "all_times": [float(t) for t in all_times],
            "errors": errors,
        },
    }

    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)

    with open(correct_file, "w") as f:
        json.dump({"correct": is_correct, "error": final_error}, f, indent=2)

    return metrics, is_correct, final_error


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate t-SNE gradient optimization")
    parser.add_argument("--program_path", required=True, help="Path to Rust program")
    parser.add_argument("--results_dir", required=True, help="Directory for results")
    args = parser.parse_args()

    metrics, correct, error = main(args.program_path, args.results_dir)
    print(f"Score: {metrics['combined_score']:.2f}, Correct: {correct}")
    if error:
        print(f"Error: {error}")
