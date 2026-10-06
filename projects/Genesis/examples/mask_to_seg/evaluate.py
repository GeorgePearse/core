"""
Evaluator for mask to segmentation conversion.
Metric: IoU and Speed.
"""

import os
import argparse
import numpy as np
import cv2
import json
from typing import List, Dict, Any, Tuple, Optional
from genesis.core import run_genesis_eval

# Store GT
GROUND_TRUTH_MASKS = {}


def generate_random_mask(height=512, width=512, num_shapes=5, seed=None):
    if seed is not None:
        np.random.seed(seed)

    mask = np.zeros((height, width), dtype=np.uint8)

    for _ in range(num_shapes):
        # Random blobs
        center = np.random.randint(0, min(height, width), 2)
        axes = np.random.randint(20, 100, 2)
        angle = np.random.randint(0, 180)
        cv2.ellipse(mask, tuple(center), tuple(axes), int(angle), 0, 360, 1, -1)

    return mask


def get_mask_conversion_kwargs(run_index: int) -> Dict[str, Any]:
    seed = 1000 + run_index
    mask = generate_random_mask(seed=seed)
    GROUND_TRUTH_MASKS[run_index] = mask
    return {"mask": mask}


def validate_conversion(result: List[np.ndarray]) -> Tuple[bool, Optional[str]]:
    if not isinstance(result, list):
        return False, f"Result must be a list, got {type(result)}"
    return True, None


def polygon_to_mask(polygons: List[np.ndarray], height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if not polygons:
        return mask
    try:
        # Filter out invalid polygons (needs at least 3 points)
        valid_polys = [p.astype(np.int32) for p in polygons if len(p) >= 3]
        if valid_polys:
            cv2.fillPoly(mask, valid_polys, 1)
    except Exception as e:
        print(f"Error drawing polygons: {e}")
    return mask


def calculate_iou(mask1: np.ndarray, mask2: np.ndarray) -> float:
    intersection = np.logical_and(mask1, mask2).sum()
    union = np.logical_or(mask1, mask2).sum()
    if union == 0:
        return 1.0 if intersection == 0 else 0.0
    return float(intersection) / float(union)


def aggregate_mask_metrics(results: List[Any]) -> Dict[str, Any]:
    ious = []
    for i, polygons in enumerate(results):
        gt_mask = GROUND_TRUTH_MASKS.get(i)
        if gt_mask is None:
            continue
        h, w = gt_mask.shape
        pred_mask = polygon_to_mask(polygons, h, w)
        iou = calculate_iou(gt_mask, pred_mask)
        ious.append(iou)

    mean_iou = np.mean(ious) if ious else 0.0
    return {
        "mean_iou": mean_iou,
        "combined_score": mean_iou,  # Temporary, updated in main
        "ious": ious,
    }


def main(program_path: str, results_dir: str):
    num_runs = 5  # Run 5 times to get average

    # Reset global state for safety
    GROUND_TRUTH_MASKS.clear()

    metrics, correct, error_msg = run_genesis_eval(
        program_path=program_path,
        results_dir=results_dir,
        experiment_fn_name="run_conversion",
        num_runs=num_runs,
        get_experiment_kwargs=get_mask_conversion_kwargs,
        validate_fn=validate_conversion,
        aggregate_metrics_fn=aggregate_mask_metrics,
    )

    if correct:
        # Calculate combined score rewarding speed and accuracy
        # Base score is IoU (0-1).
        # We assume a baseline time of ~0.01s is good.
        # If time > 0.1s, penalty.
        # Score = IoU * (TargetTime / max(Time, TargetTime))

        mean_time = metrics.get("execution_time_mean", 1.0)
        mean_iou = metrics.get("mean_iou", 0.0)

        # Avoid division by zero
        safe_time = max(mean_time, 1e-6)

        # Scoring function:
        # We want to maximize IoU.
        # We want to minimize Time.
        # Let's use a soft penalty.
        # Score = IoU * (1 / (1 + w * Time))
        # If w=10, Time=0.1s -> 1/(1+1) = 0.5 penalty
        # If w=10, Time=0.01s -> 1/(1+0.1) = 0.9 penalty

        w = 10.0
        time_factor = 1.0 / (1.0 + w * safe_time)
        combined_score = mean_iou * time_factor

        metrics["combined_score"] = combined_score
        metrics["time_factor"] = time_factor

        # Save updated metrics
        with open(os.path.join(results_dir, "metrics.json"), "w") as f:
            json.dump(metrics, f, indent=4)

    print("Metrics:", metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", default="initial.py")
    parser.add_argument("--results_dir", default="results")
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
