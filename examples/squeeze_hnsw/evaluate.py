"""
Evaluator for HNSW k-NN search optimization.

Metrics:
- Recall@10: Fraction of true nearest neighbors found
- Speed: Queries per second
- Combined score: recall * speed_factor (higher is better)
"""

import os
import argparse
import numpy as np
import json
import time
import subprocess
from typing import List, Dict, Any, Tuple, Optional
from genesis.core import run_genesis_eval

# Globals for ground truth
GROUND_TRUTH = {}
BINARY_PATH = None


def generate_random_data(n_points: int, dim: int, seed: int) -> np.ndarray:
    """Generate random dataset."""
    np.random.seed(seed)
    return np.random.randn(n_points, dim).astype(np.float32)


def generate_queries(data: np.ndarray, n_queries: int, seed: int) -> np.ndarray:
    """Generate query points (slightly perturbed from data points)."""
    np.random.seed(seed + 1000)
    indices = np.random.choice(len(data), n_queries, replace=False)
    queries = data[indices] + np.random.randn(n_queries, data.shape[1]).astype(np.float32) * 0.1
    return queries


def compute_ground_truth(data: np.ndarray, queries: np.ndarray, k: int) -> List[List[int]]:
    """Compute exact k-NN using brute force."""
    ground_truth = []
    for query in queries:
        distances = np.sqrt(np.sum((data - query) ** 2, axis=1))
        indices = np.argsort(distances)[:k]
        ground_truth.append(indices.tolist())
    return ground_truth


def save_data_txt(data: np.ndarray, path: str):
    """Save data to text file (one vector per line, space-separated)."""
    with open(path, "w") as f:
        for row in data:
            f.write(" ".join(f"{x:.6f}" for x in row) + "\n")


def compile_rust(program_path: str, output_dir: str) -> Optional[str]:
    """Compile Rust program."""
    binary_path = os.path.join(output_dir, "hnsw_search")
    cmd = ["rustc", "-O", program_path, "-o", binary_path]
    try:
        subprocess.check_call(cmd, stderr=subprocess.PIPE, timeout=60)
        return binary_path
    except subprocess.CalledProcessError as e:
        print(f"Compilation failed: {e}")
        return None
    except subprocess.TimeoutExpired:
        print("Compilation timed out")
        return None


def run_search(data: np.ndarray, queries: np.ndarray, run_index: int) -> List[List[Tuple[int, float]]]:
    """Run HNSW search and return results."""
    binary_path = os.environ.get("HNSW_BINARY_PATH")
    if not binary_path or not os.path.exists(binary_path):
        return []

    base_dir = os.path.dirname(binary_path)
    run_dir = os.path.join(base_dir, "temp", f"run_{run_index}")
    os.makedirs(run_dir, exist_ok=True)

    data_path = os.path.join(run_dir, "data.txt")
    query_path = os.path.join(run_dir, "queries.txt")
    output_path = os.path.join(run_dir, "results.json")

    save_data_txt(data, data_path)
    save_data_txt(queries, query_path)

    try:
        subprocess.check_call(
            [binary_path, data_path, query_path, output_path],
            timeout=30,
            stderr=subprocess.DEVNULL
        )

        if os.path.exists(output_path):
            with open(output_path, "r") as f:
                results_raw = json.load(f)

            # Parse results: [[idx, dist], [idx, dist], ...]
            results = []
            for query_results in results_raw:
                parsed = [(int(r[0]), float(r[1])) for r in query_results]
                results.append(parsed)
            return results
    except Exception as e:
        print(f"Run failed: {e}")

    return []


def get_kwargs(run_index: int) -> Dict[str, Any]:
    """Generate test case."""
    # Different sizes for robustness
    configs = [
        (1000, 64, 50),   # Small: 1000 points, 64 dims, 50 queries
        (2000, 128, 50),  # Medium: 2000 points, 128 dims
        (5000, 64, 100),  # Larger: 5000 points
        (1000, 256, 50),  # High-dim: 256 dimensions
        (3000, 96, 75),   # Mixed
    ]

    config_idx = run_index % len(configs)
    n_points, dim, n_queries = configs[config_idx]
    seed = 42 + run_index * 100

    data = generate_random_data(n_points, dim, seed)
    queries = generate_queries(data, n_queries, seed)

    # Compute ground truth
    k = 10
    gt = compute_ground_truth(data, queries, k)
    GROUND_TRUTH[run_index] = gt

    return {"data": data, "queries": queries, "run_index": run_index}


def validate(result: List[List[Tuple[int, float]]]) -> Tuple[bool, Optional[str]]:
    """Validate search results."""
    if not isinstance(result, list):
        return False, "Result not a list"
    if len(result) == 0:
        return False, "Empty results"
    return True, None


def compute_recall(results: List[List[Tuple[int, float]]], ground_truth: List[List[int]], k: int = 10) -> float:
    """Compute recall@k."""
    if not results or not ground_truth:
        return 0.0

    recalls = []
    for pred, gt in zip(results, ground_truth):
        pred_indices = set(r[0] for r in pred[:k])
        gt_set = set(gt[:k])
        if len(gt_set) > 0:
            recall = len(pred_indices & gt_set) / len(gt_set)
            recalls.append(recall)

    return np.mean(recalls) if recalls else 0.0


def aggregate(results: List[Any]) -> Dict[str, Any]:
    """Aggregate metrics across runs."""
    recalls = []

    for i, result in enumerate(results):
        gt = GROUND_TRUTH.get(i)
        if gt is None or not result:
            continue

        recall = compute_recall(result, gt, k=10)
        recalls.append(recall)

    mean_recall = np.mean(recalls) if recalls else 0.0

    return {
        "mean_recall": float(mean_recall),
        "num_successful_runs": len(recalls),
    }


def main(program_path: str, results_dir: str):
    """Main evaluation function."""
    global BINARY_PATH

    os.makedirs(results_dir, exist_ok=True)
    temp_dir = os.path.join(results_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Compile Rust program
    print(f"Compiling {program_path}...")
    BINARY_PATH = compile_rust(program_path, results_dir)

    if not BINARY_PATH:
        print("Compilation failed, returning zero score")
        metrics = {
            "combined_score": 0.0,
            "mean_recall": 0.0,
            "correct": False,
            "error": "compilation_failed"
        }
        with open(os.path.join(results_dir, "metrics.json"), "w") as f:
            json.dump(metrics, f, indent=4)
        return

    os.environ["HNSW_BINARY_PATH"] = BINARY_PATH

    # Run evaluation
    metrics, correct, error = run_genesis_eval(
        program_path=__file__,
        results_dir=results_dir,
        experiment_fn_name="run_search",
        num_runs=5,
        get_experiment_kwargs=get_kwargs,
        validate_fn=validate,
        aggregate_metrics_fn=aggregate,
    )

    if correct:
        mean_time = metrics.get("execution_time_mean", 1.0)
        mean_recall = metrics.get("mean_recall", 0.0)

        # Speed factor: penalize slow execution
        # Target: < 1 second per run
        safe_time = max(mean_time, 1e-6)
        speed_factor = 1.0 / (1.0 + safe_time)

        # Combined score: recall * speed * 100
        # High recall is essential, but speed matters too
        combined_score = mean_recall * speed_factor * 100.0

        metrics["combined_score"] = combined_score
        metrics["speed_factor"] = speed_factor
        metrics["correct"] = True
    else:
        metrics["combined_score"] = 0.0
        metrics["correct"] = False
        metrics["error"] = error

    with open(os.path.join(results_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=4)

    print("Metrics:", json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", default="initial.rs")
    parser.add_argument("--results_dir", default="results")
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
