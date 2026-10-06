import json
import os
import subprocess
import time
import numpy as np
from scipy.spatial.distance import pdist
from scipy.stats import spearmanr
from sklearn.manifold import trustworthiness


def generate_test_data(n_samples=100, n_features=10, seed=42):
    """Generate synthetic data (blobs)."""
    np.random.seed(seed)
    # 3 clusters
    centers = np.random.randn(3, n_features) * 5
    data = []
    for _ in range(n_samples):
        c = centers[np.random.randint(3)]
        point = c + np.random.randn(n_features)
        data.append(point)
    return np.array(data)


def compile_rust(source_path, binary_path):
    cmd = ["rustc", "-O", source_path, "-o", binary_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return False, res.stderr
    return True, ""


def run_evaluation(binary_path, data, output_path):
    # Save data to temp file
    data_path = output_path + ".data"
    np.savetxt(data_path, data, fmt="%.6f")

    try:
        res = subprocess.run(
            [binary_path, data_path, output_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode != 0:
            return None, f"Runtime error: {res.stderr}"

        if not os.path.exists(output_path):
            return None, "No output file created"

        with open(output_path, "r") as f:
            result = json.load(f)
        return result, ""
    except subprocess.TimeoutExpired:
        return None, "Timeout"
    finally:
        if os.path.exists(data_path):
            os.remove(data_path)


def main(program_path, results_dir):
    os.makedirs(results_dir, exist_ok=True)
    binary_path = os.path.join(results_dir, "reducer")

    # Compile
    success, err = compile_rust(program_path, binary_path)
    if not success:
        return {"combined_score": 0, "error": err}, False, err

    # Test cases
    scores = []
    trusts = []
    spearmans = []
    times = []

    configs = [(50, 10, 1), (100, 20, 2), (150, 50, 3)]

    for n, d, s in configs:
        data = generate_test_data(n, d, s)
        out_file = os.path.join(results_dir, f"out_{s}.json")

        res, err = run_evaluation(binary_path, data, out_file)
        if err:
            return {"combined_score": 0, "error": err}, False, err

        embedding = np.array(res["embedding"])
        exec_time = res["time_seconds"]

        # Calculate metrics
        # 1. Trustworthiness
        try:
            trust = trustworthiness(data, embedding, n_neighbors=5)
        except Exception as e:
            return (
                {"combined_score": 0, "error": f"Trust calc failed: {e}"},
                False,
                str(e),
            )

        # 2. Spearman Correlation of distances
        # Sample subset if N is large to save eval time
        if len(data) > 200:
            idx = np.random.choice(len(data), 200, replace=False)
            sub_data = data[idx]
            sub_emb = embedding[idx]
        else:
            sub_data = data
            sub_emb = embedding

        dist_high = pdist(sub_data)
        dist_low = pdist(sub_emb)
        spearman, _ = spearmanr(dist_high, dist_low)
        if np.isnan(spearman):
            spearman = 0

        # 3. Time Score (Target: < 1s for these sizes)
        time_score = min(2.0, 1.0 / max(exec_time, 0.01))

        # Combined for this run
        # We want to maximize trust and spearman (0-1), and minimize time
        run_score = trust * 0.4 + max(0, spearman) * 0.4 + time_score * 0.2

        scores.append(run_score)
        trusts.append(trust)
        spearmans.append(spearman)
        times.append(exec_time)

    avg_score = np.mean(scores) * 100  # Scale up

    metrics = {
        "combined_score": avg_score,
        "public": {
            "trustworthiness": np.mean(trusts),
            "spearman": np.mean(spearmans),
            "time": np.mean(times),
        },
    }

    # Save metrics
    with open(os.path.join(results_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)

    return metrics, True, ""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", required=True)
    parser.add_argument("--results_dir", required=True)
    args = parser.parse_args()

    metrics, correct, err = main(args.program_path, args.results_dir)
    print(json.dumps(metrics))
