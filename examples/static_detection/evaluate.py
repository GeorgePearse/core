"""
Evaluator for static-detection algorithm evolution.

Generates synthetic frame pairs with known ground truth (static vs moving)
covering lighting shifts, sensor noise, compression artefacts, and real
scene changes. The evolved algorithm is scored on how well it separates
the two distributions (AUC) while remaining fast.
"""

import argparse
import os
from typing import Any

import numpy as np

from genesis.core import run_genesis_eval

RNG = np.random.RandomState(42)
H, W = 480, 640


def _base_scene(idx: int) -> np.ndarray:
    """Deterministic synthetic scene with edges, gradients and flat regions."""
    rng = np.random.RandomState(idx)
    scene = np.zeros((H, W, 3), dtype=np.uint8)
    # gradient background
    for c in range(3):
        base_val = rng.randint(40, 180)
        grad = np.linspace(base_val, min(base_val + 60, 255), W, dtype=np.uint8)
        scene[:, :, c] = grad[np.newaxis, :]
    # random rectangles (simulate objects)
    for _ in range(rng.randint(3, 8)):
        x1, y1 = rng.randint(0, W - 50), rng.randint(0, H - 50)
        x2, y2 = x1 + rng.randint(20, 120), y1 + rng.randint(20, 80)
        color = rng.randint(0, 256, 3).tolist()
        scene[y1:min(y2, H), x1:min(x2, W)] = color
    return scene


def _add_noise(frame: np.ndarray, sigma: float) -> np.ndarray:
    noise = RNG.normal(0, sigma, frame.shape).astype(np.int16)
    return np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def _shift_brightness(frame: np.ndarray, delta: int) -> np.ndarray:
    return np.clip(frame.astype(np.int16) + delta, 0, 255).astype(np.uint8)


def _jpeg_artefact(frame: np.ndarray, quality: int = 50) -> np.ndarray:
    """Simulate JPEG compression artefacts via quantisation noise."""
    q = max(quality, 10)
    step = max(1, (100 - q) // 4)
    quantised = (frame // step) * step
    return quantised.astype(np.uint8)


def _generate_pairs() -> tuple[
    list[tuple[np.ndarray, np.ndarray]],
    list[tuple[np.ndarray, np.ndarray]],
]:
    """Build labelled static and moving pairs."""
    static_pairs: list[tuple[np.ndarray, np.ndarray]] = []
    moving_pairs: list[tuple[np.ndarray, np.ndarray]] = []

    for scene_idx in range(5):
        scene = _base_scene(scene_idx)

        # --- static variants ---
        # identical
        static_pairs.append((scene.copy(), scene.copy()))
        # sensor noise only
        static_pairs.append((scene.copy(), _add_noise(scene, sigma=3)))
        static_pairs.append((scene.copy(), _add_noise(scene, sigma=8)))
        # brightness shift (lighting change)
        static_pairs.append((scene.copy(), _shift_brightness(scene, 15)))
        static_pairs.append((scene.copy(), _shift_brightness(scene, -20)))
        # JPEG artefacts
        static_pairs.append((scene.copy(), _jpeg_artefact(scene, quality=40)))
        # combined: noise + brightness
        noisy_bright = _shift_brightness(_add_noise(scene, sigma=5), 10)
        static_pairs.append((scene.copy(), noisy_bright))

        # --- moving variants ---
        other = _base_scene(scene_idx + 100)
        moving_pairs.append((scene.copy(), other))
        # shifted scene (camera bump)
        shifted = np.roll(scene, 40, axis=1)
        moving_pairs.append((scene.copy(), shifted))
        # partial occlusion (object enters)
        occluded = scene.copy()
        occluded[100:300, 200:450] = RNG.randint(0, 256, (200, 250, 3), dtype=np.uint8)
        moving_pairs.append((scene.copy(), occluded))

    return static_pairs, moving_pairs


def get_experiment_kwargs(run_index: int) -> dict[str, Any]:
    static_pairs, moving_pairs = _generate_pairs()
    return {"static_pairs": static_pairs, "moving_pairs": moving_pairs}


def validate_fn(result: dict) -> tuple[bool, str | None]:
    if not isinstance(result, dict):
        return False, "run_experiment must return a dict"
    for key in ("separation", "auc", "avg_time_ms"):
        if key not in result:
            return False, f"Missing key: {key}"
    if result["auc"] < 0.0 or result["auc"] > 1.0:
        return False, f"AUC out of range: {result['auc']}"
    return True, None


def aggregate_metrics(results: list[dict], results_dir: str = "") -> dict[str, Any]:
    if not results:
        return {"combined_score": 0.0, "error": "No results"}

    r = results[0]
    auc = r["auc"]
    separation = r["separation"]
    avg_time_ms = r["avg_time_ms"]

    # Speed bonus: full bonus below 5ms, linear decay up to 50ms, zero above
    if avg_time_ms <= 5.0:
        speed_factor = 1.0
    elif avg_time_ms <= 50.0:
        speed_factor = 1.0 - (avg_time_ms - 5.0) / 45.0
    else:
        speed_factor = 0.0

    # Combined score: 70% AUC + 20% separation (capped at 10x) + 10% speed
    sep_score = min(separation / 10.0, 1.0)
    combined = 0.70 * auc + 0.20 * sep_score + 0.10 * speed_factor

    return {
        "combined_score": float(combined),
        "public": {
            "auc": round(auc, 4),
            "separation": round(separation, 2),
            "avg_time_ms": round(avg_time_ms, 2),
            "speed_factor": round(speed_factor, 3),
        },
        "private": {
            "static_diffs_sample": r["static_diffs"][:5],
            "moving_diffs_sample": r["moving_diffs"][:5],
        },
    }


def main(program_path: str, results_dir: str):
    os.makedirs(results_dir, exist_ok=True)

    def _agg(results):
        return aggregate_metrics(results, results_dir)

    metrics, correct, error_msg = run_genesis_eval(
        program_path=program_path,
        results_dir=results_dir,
        experiment_fn_name="run_experiment",
        num_runs=1,
        get_experiment_kwargs=get_experiment_kwargs,
        validate_fn=validate_fn,
        aggregate_metrics_fn=_agg,
    )

    if correct:
        print("Evaluation passed.")
    else:
        print(f"Evaluation failed: {error_msg}")

    for k, v in metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", type=str, default="initial.py")
    parser.add_argument("--results_dir", type=str, default="results")
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
