"""
Evaluator for Rust mask to segmentation conversion.
"""

import os
import argparse
import numpy as np
import cv2
import json
import time
import subprocess
from typing import List, Dict, Any, Tuple, Optional
from genesis.core import run_genesis_eval

# Globals
GROUND_TRUTH_MASKS = {}
BINARY_PATH = None
TEMP_DIR = "temp_rust_eval"


def generate_random_mask(height=512, width=512, num_shapes=5, seed=None):
    if seed is not None:
        np.random.seed(seed)
    mask = np.zeros((height, width), dtype=np.uint8)
    for _ in range(num_shapes):
        center = np.random.randint(0, min(height, width), 2)
        axes = np.random.randint(20, 100, 2)
        angle = np.random.randint(0, 180)
        cv2.ellipse(mask, tuple(center), tuple(axes), int(angle), 0, 360, 1, -1)
    return mask


def save_mask_txt(mask, path):
    h, w = mask.shape
    with open(path, "w") as f:
        f.write(f"{w} {h}\n")
        # Flatten and join for fast writing
        # Note: This can be large. 512*512 ~ 250KB text.
        # Optimization: The rust program could read binary P5 PGM.
        # But text is robust for the baseline.
        for row in mask:
            f.write(" ".join(map(str, row)) + "\n")


def compile_rust(program_path, output_dir):
    binary_path = os.path.join(output_dir, "main_rs")
    # Use -O for release optimization
    cmd = ["rustc", "-O", program_path, "-o", binary_path]
    try:
        subprocess.check_call(cmd, stderr=subprocess.PIPE)
        return binary_path
    except subprocess.CalledProcessError as e:
        print(f"Compilation failed: {e}")
        return None


def run_conversion(mask: np.ndarray, run_index: int) -> List[np.ndarray]:
    binary_path = os.environ.get("RUST_BINARY_PATH")
    if not binary_path or not os.path.exists(binary_path):
        # Try default location in current directory (cwd is often results_dir or root)
        # But let's rely on env var first.
        return []

    # Create unique run dir
    # We need a temp dir. If TEMP_DIR global is None (in imported module), recreate it.
    # But results_dir is unknown.
    # However, binary_path is usually results_dir/main_rs.
    base_dir = os.path.dirname(binary_path)
    run_dir = os.path.join(base_dir, "temp", f"run_{run_index}")
    os.makedirs(run_dir, exist_ok=True)

    input_path = os.path.join(run_dir, "input.txt")
    output_path = os.path.join(run_dir, "output.json")

    save_mask_txt(mask, input_path)

    # Execute
    try:
        # We measure pure binary execution time inside here if we want precision,
        # but run_genesis_eval measures this python function's time.
        # This includes IO overhead (save/read).
        # For the optimization task, minimizing IO overhead IS part of the game
        # if the protocol allows changing the format (but I fixed the format).
        # Ideally, we should allow the user to define the format?
        # No, let's stick to fixed format for simplicity, or allow LLM to optimize I/O?
        # The prompt says "mask -> segmentation".
        # If I fix the input format to text, I penalize the IO heavily.
        # But that's fine for now.

        subprocess.check_call(
            [binary_path, input_path, output_path], timeout=5, stderr=subprocess.DEVNULL
        )

        if os.path.exists(output_path):
            with open(output_path, "r") as f:
                polygons_raw = json.load(f)

            polygons = []
            for poly in polygons_raw:
                # poly is [[x,y], [x,y], ...]
                pts = np.array(poly, dtype=np.int32)
                if pts.ndim == 2 and pts.shape[1] == 2:
                    polygons.append(pts)
            return polygons
    except Exception as e:
        # print(f"Run failed: {e}")
        pass

    return []


def get_kwargs(run_index: int) -> Dict[str, Any]:
    seed = 3000 + run_index
    mask = generate_random_mask(seed=seed)
    GROUND_TRUTH_MASKS[run_index] = mask
    return {"mask": mask, "run_index": run_index}


def validate(result: List[np.ndarray]) -> Tuple[bool, Optional[str]]:
    if not isinstance(result, list):
        return False, "Result not a list"
    return True, None


def polygon_to_mask(polygons, height, width):
    mask = np.zeros((height, width), dtype=np.uint8)
    if not polygons:
        return mask
    try:
        valid_polys = [p for p in polygons if len(p) >= 3]
        if valid_polys:
            cv2.fillPoly(mask, valid_polys, 1)
    except Exception:
        pass
    return mask


def calculate_iou(mask1, mask2):
    intersection = np.logical_and(mask1, mask2).sum()
    union = np.logical_or(mask1, mask2).sum()
    if union == 0:
        return 1.0 if intersection == 0 else 0.0
    return float(intersection) / float(union)


def aggregate(results: List[Any]) -> Dict[str, Any]:
    ious = []
    for i, polygons in enumerate(results):
        gt = GROUND_TRUTH_MASKS.get(i)
        if gt is None:
            continue
        h, w = gt.shape
        pred = polygon_to_mask(polygons, h, w)
        iou = calculate_iou(gt, pred)
        ious.append(iou)

    mean_iou = np.mean(ious) if ious else 0.0
    return {"mean_iou": mean_iou}


def main(program_path: str, results_dir: str):
    global BINARY_PATH, TEMP_DIR

    # Setup temp dir
    TEMP_DIR = os.path.abspath(os.path.join(results_dir, "temp"))
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Compile first
    print(f"Compiling {program_path}...")
    BINARY_PATH = compile_rust(program_path, results_dir)

    if not BINARY_PATH:
        print("Compilation failed, returning zero score")
        # ... (omitted) ...
        return

    # Set env var for the imported module to see
    os.environ["RUST_BINARY_PATH"] = BINARY_PATH

    # Run evaluation
    metrics, correct, error = run_genesis_eval(
        program_path=__file__,
        results_dir=results_dir,
        experiment_fn_name="run_conversion",  # Python wrapper name
        num_runs=5,
        get_experiment_kwargs=get_kwargs,
        validate_fn=validate,
        aggregate_metrics_fn=aggregate,
    )

    if correct:
        mean_time = metrics.get("execution_time_mean", 1.0)
        mean_iou = metrics.get("mean_iou", 0.0)

        # Scoring: IoU * Speed factor
        # Target time < 0.1s
        # Note: This time includes Python overhead (file IO).
        # Real rust binary might be 0.01s, but overhead 0.05s.
        # The LLM can optimize the logic to be instant, maxing out the score limited by overhead.

        safe_time = max(mean_time, 1e-6)
        # Strong penalty for time > 0.5s
        time_penalty = 1.0 / (1.0 + 5.0 * safe_time)

        combined_score = mean_iou * time_penalty * 100.0

        metrics["combined_score"] = combined_score
        metrics["time_factor"] = time_penalty

        with open(os.path.join(results_dir, "metrics.json"), "w") as f:
            json.dump(metrics, f, indent=4)

    print("Metrics:", metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", default="initial.rs")
    parser.add_argument("--results_dir", default="results")
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
