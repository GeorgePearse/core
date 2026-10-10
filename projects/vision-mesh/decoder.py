"""Decode supplied model scores to the pinned harness's PartObject inputs.

This module does no image inference and makes no database or network calls.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DecodeConfig:
    """Keep the presence threshold explicit for reproducible future benchmarks."""

    presence_threshold: float = 0.5


def decode_queries(
    boxes: Sequence[Sequence[float]],
    class_names: Sequence[str],
    presence_scores: Sequence[float],
    parent_scores: Sequence[Sequence[float]],
    config: DecodeConfig,
) -> list[dict[str, object]]:
    """Return normalized PartObjects using parent-head scores, without geometry heuristics.

    Each of Q parent-score rows has Q+1 finite logits: candidate query parents,
    then an explicit no-parent outcome. Ties choose the first column. Invalid
    self-links, cycles and links to filtered queries raise instead of silently
    changing the predicted structure. Query keys remain stable across filtering.
    """
    count = len(boxes)
    if any(
        len(values) != count for values in (class_names, presence_scores, parent_scores)
    ):
        raise ValueError("query arrays must have the same length")
    threshold = config.presence_threshold
    if (
        isinstance(threshold, bool)
        or not isfinite(threshold)
        or not 0 <= threshold <= 1
    ):
        raise ValueError("presence_threshold must be finite and in [0, 1]")
    for index in range(count):
        box = boxes[index]
        if len(box) != 4 or any(
            isinstance(v, bool) or not isfinite(v) or not 0 <= v <= 1 for v in box
        ):
            raise ValueError(
                f"query {index}: normalized box must have four finite coordinates in [0, 1]"
            )
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError(f"query {index}: box must have positive width and height")
        if not isinstance(class_names[index], str) or not class_names[index].strip():
            raise ValueError(f"query {index}: class_name must be nonempty")
        presence = presence_scores[index]
        if (
            isinstance(presence, bool)
            or not isfinite(presence)
            or not 0 <= presence <= 1
        ):
            raise ValueError(
                f"query {index}: presence score must be finite and in [0, 1]"
            )
        scores = parent_scores[index]
        if len(scores) != count + 1 or any(
            isinstance(v, bool) or not isfinite(v) for v in scores
        ):
            raise ValueError(
                f"query {index}: parent scores must have Q+1 finite logits"
            )

    retained = {i for i, score in enumerate(presence_scores) if score >= threshold}
    parents: dict[int, int] = {}
    for index in sorted(retained):
        scores = parent_scores[index]
        parent = max(range(count + 1), key=lambda i: scores[i])
        if parent == count:
            continue
        if parent == index:
            raise ValueError(f"query {index}: cannot be part of itself")
        if parent not in retained:
            raise ValueError(f"query {index}: predicted parent {parent} was filtered")
        parents[index] = parent
    for index in parents:
        seen: set[int] = set()
        current = index
        while current in parents:
            if current in seen:
                raise ValueError(f"query {index}: predicted part_of cycle")
            seen.add(current)
            current = parents[current]

    objects: list[dict[str, object]] = []
    for index in sorted(retained):
        item: dict[str, object] = {
            "key": f"q{index}",
            "class_name": class_names[index].strip(),
            "box": [float(v) for v in boxes[index]],
            "score": float(presence_scores[index]),
        }
        if index in parents:
            item["part_of"] = f"q{parents[index]}"
        objects.append(item)
    return objects
