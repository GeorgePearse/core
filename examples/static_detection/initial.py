"""
Static frame detection algorithm.

Given two frames (as numpy uint8 HxWx3 arrays), compute a scalar
"difference" value. Lower values mean the frames are more similar
(static). The goal is to maximise the separation between the
difference distributions of truly-static pairs and truly-moving pairs
so that a single threshold cleanly separates them.

The algorithm must be fast (target < 5 ms per pair on CPU at 640x480)
and robust to lighting changes, sensor noise, and compression artefacts.
"""

import numpy as np

# EVOLVE-BLOCK-START


def compute_difference(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Return a scalar difference between two BGR uint8 frames.

    Lower value  => frames are more similar (static camera).
    Higher value => frames differ (motion / scene change).

    Args:
        frame_a: (H, W, 3) uint8 BGR image.
        frame_b: (H, W, 3) uint8 BGR image, same shape as frame_a.

    Returns:
        Non-negative float representing the difference magnitude.
    """
    diff = np.abs(frame_a.astype(np.int16) - frame_b.astype(np.int16))
    return float(np.sum(diff))


# EVOLVE-BLOCK-END


def run_experiment(
    static_pairs: list[tuple[np.ndarray, np.ndarray]],
    moving_pairs: list[tuple[np.ndarray, np.ndarray]],
) -> dict:
    """Evaluate compute_difference on labelled frame pairs.

    Returns a dict with:
        static_diffs  – list of difference values for static pairs
        moving_diffs  – list of difference values for moving pairs
        separation    – moving_p05 / static_p95  (higher is better)
        auc           – Mann-Whitney U based AUC
        avg_time_ms   – average wall-clock time per call in milliseconds
    """
    import time

    static_diffs: list[float] = []
    moving_diffs: list[float] = []

    t0 = time.perf_counter()
    for a, b in static_pairs:
        static_diffs.append(compute_difference(a, b))
    for a, b in moving_pairs:
        moving_diffs.append(compute_difference(a, b))
    elapsed = time.perf_counter() - t0

    total_pairs = len(static_pairs) + len(moving_pairs)
    avg_time_ms = (elapsed / max(total_pairs, 1)) * 1000.0

    static_arr = np.array(static_diffs) if static_diffs else np.array([0.0])
    moving_arr = np.array(moving_diffs) if moving_diffs else np.array([1.0])

    static_p95 = float(np.percentile(static_arr, 95)) if len(static_arr) > 0 else 1.0
    moving_p05 = float(np.percentile(moving_arr, 5)) if len(moving_arr) > 0 else 0.0

    separation = moving_p05 / max(static_p95, 1.0)

    auc = _compute_auc(static_diffs, moving_diffs)

    return {
        "static_diffs": static_diffs,
        "moving_diffs": moving_diffs,
        "separation": separation,
        "auc": auc,
        "avg_time_ms": avg_time_ms,
    }


def _compute_auc(static_diffs: list[float], moving_diffs: list[float]) -> float:
    """AUC via Mann-Whitney U. 1.0 = perfect separation, 0.5 = random."""
    n_s = len(static_diffs)
    n_m = len(moving_diffs)
    if n_s == 0 or n_m == 0:
        return 0.5

    combined = [(v, 1) for v in static_diffs] + [(v, 0) for v in moving_diffs]
    combined.sort(key=lambda x: x[0])

    rank = 1
    sum_static_ranks = 0.0
    i = 0
    total = len(combined)

    while i < total:
        j = i + 1
        while j < total and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (rank + rank + (j - i) - 1) / 2.0
        for k in range(i, j):
            if combined[k][1] == 1:
                sum_static_ranks += avg_rank
        rank += j - i
        i = j

    u = sum_static_ranks - (n_s * (n_s + 1) / 2.0)
    return u / (n_s * n_m)
