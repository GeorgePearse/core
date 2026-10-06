"""
Standalone evaluator for circle packing (works in E2B without genesis package).

This evaluator can run in isolated environments like E2B sandboxes
without requiring the full genesis package to be installed.
"""

import os
import sys
import json
import argparse
import importlib.util
import traceback
import numpy as np
from typing import Tuple, Optional, Dict, Any, List


def load_module_from_path(path: str):
    """Dynamically load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location("program", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["program"] = module
    spec.loader.exec_module(module)
    return module


def validate_packing(
    centers: np.ndarray,
    radii: np.ndarray,
    reported_sum: float,
    atol: float = 1e-6,
) -> Tuple[bool, Optional[str]]:
    """
    Validates circle packing results.

    Args:
        centers: np.array of shape (n, 2) with (x, y) coordinates
        radii: np.array of shape (n,) with radius of each circle
        reported_sum: The reported sum of radii

    Returns:
        (is_valid: bool, error_message: Optional[str])
    """
    if not isinstance(centers, np.ndarray):
        centers = np.array(centers)
    if not isinstance(radii, np.ndarray):
        radii = np.array(radii)

    n_expected = 26

    # Check shapes
    if centers.shape != (n_expected, 2):
        return False, f"Centers shape incorrect. Expected ({n_expected}, 2), got {centers.shape}"
    if radii.shape != (n_expected,):
        return False, f"Radii shape incorrect. Expected ({n_expected},), got {radii.shape}"

    # Check no negative radii
    if np.any(radii < 0):
        negative_indices = np.where(radii < 0)[0]
        return False, f"Negative radii found for circles at indices: {negative_indices}"

    # Check sum matches reported
    if not np.isclose(np.sum(radii), reported_sum, atol=atol):
        return False, f"Sum of radii ({np.sum(radii):.6f}) does not match reported ({reported_sum:.6f})"

    # Check all circles inside unit square
    for i in range(n_expected):
        x, y = centers[i]
        r = radii[i]
        is_outside = (
            x - r < -atol or x + r > 1 + atol or y - r < -atol or y + r > 1 + atol
        )
        if is_outside:
            return False, f"Circle {i} (x={x:.4f}, y={y:.4f}, r={r:.4f}) is outside unit square."

    # Check no overlaps
    for i in range(n_expected):
        for j in range(i + 1, n_expected):
            dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
            if dist < radii[i] + radii[j] - atol:
                return False, f"Circles {i} & {j} overlap. Dist: {dist:.4f}, Sum Radii: {(radii[i] + radii[j]):.4f}"

    return True, "All validations passed"


def main(program_path: str, results_dir: str):
    """Run circle packing evaluation."""
    print(f"Evaluating program: {program_path}")
    print(f"Saving results to: {results_dir}")
    os.makedirs(results_dir, exist_ok=True)

    metrics = {"combined_score": 0.0, "error": None}
    correct_result = {"correct": False, "error": None}

    try:
        # Load the program module
        module = load_module_from_path(program_path)

        # Check for run_packing function
        if not hasattr(module, "run_packing"):
            raise AttributeError("Program must have a 'run_packing' function")

        # Run the packing algorithm
        result = module.run_packing()

        if len(result) == 3:
            centers, radii, sum_radii = result
        elif len(result) == 2:
            centers, radii = result
            sum_radii = np.sum(radii)
        else:
            raise ValueError(f"run_packing returned {len(result)} values, expected 2 or 3")

        # Validate the result
        is_valid, error_msg = validate_packing(centers, radii, sum_radii)

        if is_valid:
            # Format centers for display
            centers_str = "\n".join(
                [f"  centers[{i}] = ({x:.4f}, {y:.4f})"
                 for i, (x, y) in enumerate(centers)]
            )

            metrics = {
                "combined_score": float(sum_radii),
                "public": {
                    "centers_str": centers_str,
                    "num_circles": int(centers.shape[0]),
                },
                "private": {
                    "reported_sum_of_radii": float(sum_radii),
                },
            }
            correct_result = {"correct": True, "error": None}
            print(f"SUCCESS: Sum of radii = {sum_radii:.6f}")
        else:
            metrics = {"combined_score": 0.0, "error": error_msg}
            correct_result = {"correct": False, "error": error_msg}
            print(f"VALIDATION FAILED: {error_msg}")

        # Save extra data
        try:
            extra_file = os.path.join(results_dir, "extra.npz")
            np.savez(extra_file, centers=centers, radii=radii, reported_sum=sum_radii)
            print(f"Saved extra data to {extra_file}")
        except Exception as e:
            print(f"Warning: Could not save extra.npz: {e}")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        metrics = {"combined_score": 0.0, "error": error_msg}
        correct_result = {"correct": False, "error": error_msg}
        print(f"EXECUTION ERROR: {e}")
        traceback.print_exc()

    # Save results
    metrics_file = os.path.join(results_dir, "metrics.json")
    correct_file = os.path.join(results_dir, "correct.json")

    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics to {metrics_file}")

    with open(correct_file, "w") as f:
        json.dump(correct_result, f, indent=2)
    print(f"Saved correct status to {correct_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Circle packing evaluator (standalone)")
    parser.add_argument(
        "--program_path",
        type=str,
        default="main.py",
        help="Path to program to evaluate (must contain 'run_packing')",
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        default="results",
        help="Directory to save results",
    )
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
