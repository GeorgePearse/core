"""Explicit multiclass metrics and auditable prediction records."""

import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score

from modelmode.data import inputs
from modelmode.storage import sha256


@lru_cache(maxsize=8)
def load_estimator(path: str, expected_hash: str) -> Any:
    """Load only internally produced, hash-verified artifacts in a trusted workspace."""
    if sha256(Path(path)) != expected_hash:
        raise ValueError("Model artifact hash mismatch")
    return joblib.load(path)


def score(model: Any, rows: list[dict], mode: str, classes: list[str]) -> dict:
    """Keep macro metrics and per-class recall meaningful for imbalanced tasks."""
    started = time.perf_counter()
    probabilities = model.predict_proba(inputs(rows, mode))
    seconds = time.perf_counter() - started
    guesses = model.classes_[probabilities.argmax(axis=1)]
    labels = [r["label"] for r in rows]
    return {
        "accuracy": float(accuracy_score(labels, guesses)),
        "balanced_accuracy": float(
            recall_score(
                labels, guesses, labels=classes, average="macro", zero_division=0
            )
        ),
        "macro_f1": float(
            f1_score(labels, guesses, labels=classes, average="macro", zero_division=0)
        ),
        "classes": classes,
        "confusion_matrix": confusion_matrix(labels, guesses, labels=classes).tolist(),
        "examples": len(rows),
        "prediction_seconds": seconds,
        "predictions": [
            {
                "id": r["id"],
                "label": r["label"],
                "prediction": str(guess),
                "score": float(p.max()),
            }
            for r, guess, p in zip(rows, guesses, probabilities)
        ],
    }


def warm_timing(model: Any, rows: list[dict], mode: str) -> dict:
    """Report amortized warm CPU inference separately from model loading and fitting."""
    sample = inputs(rows[:64], mode)
    model.predict_proba(sample)
    times = []
    for _ in range(7):
        start = time.perf_counter()
        model.predict_proba(sample)
        times.append(1000 * (time.perf_counter() - start) / len(sample))
    return {
        "warm_ms_per_item": float(np.median(times)),
        "latency_batch_size": len(sample),
        "timing_repeats": len(times),
        "timing_note": "Median amortized CPU inference; includes encoding, excludes model load; not single-request latency",
    }


def summary(result: dict) -> dict:
    """Avoid copying all examples into an agent's context by default."""
    return {k: v for k, v in result.items() if k != "predictions"}
