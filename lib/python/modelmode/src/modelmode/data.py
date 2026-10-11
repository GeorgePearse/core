"""Immutable datasets with explicit evaluation boundaries."""

import hashlib
import json
import math
import unicodedata
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.model_selection import StratifiedGroupKFold


class Example(BaseModel):
    """One labelled example; group identifies a shared source or near-duplicate."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=1, max_length=100_000)
    features: list[float] | None = Field(default=None, min_length=1, max_length=100_000)
    group: str | None = Field(default=None, min_length=1)
    split: Literal["train", "validation", "test"] | None = None
    label_source: Literal["provided", "human", "teacher"] = "provided"

    @model_validator(mode="after")
    def check_input(self) -> "Example":
        """Disallow ambiguous input modes and non-finite feature vectors."""
        if (self.text is None) == (self.features is None):
            raise ValueError("Provide exactly one of text or features")
        if self.text is not None and not self.text.strip():
            raise ValueError("Text must contain a non-whitespace character")
        if self.features is not None and not all(map(math.isfinite, self.features)):
            raise ValueError("Features must be finite")
        return self


def canonical(value: Any) -> str:
    """Use the same serialization for identity, persistence and fingerprints."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    """Content identity independent of Python object layout."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def input_key(row: dict[str, Any]) -> str:
    """Catch equivalent text across splits even when IDs/groups differ."""
    value = row.get("text")
    if value is not None:
        value = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    else:
        value = row["features"]
    return fingerprint(value)


def prepare(rows: list[dict[str, Any]], seed: int = 42) -> dict[str, Any]:
    """Validate or construct a grouped 60/20/20 partition before any fitting."""
    if not 15 <= len(rows) <= 200_000:
        raise ValueError("Datasets must contain 15–200,000 examples")
    records = sorted(
        [Example.model_validate(row).model_dump() for row in rows],
        key=lambda row: row["id"],
    )
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Example IDs must be unique")
    modes = {"text" if r["text"] is not None else "features" for r in records}
    if len(modes) != 1:
        raise ValueError("Use one input modality per dataset")
    mode = modes.pop()
    if mode == "features" and len({len(r["features"]) for r in records}) != 1:
        raise ValueError("All feature vectors must have the same width")
    classes = sorted({r["label"] for r in records})
    if len(classes) < 2:
        raise ValueError("Classification needs at least two classes")

    # Connected components combine user groups and normalized duplicate inputs.
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen: dict[tuple[str, str], int] = {}
    for i, row in enumerate(records):
        keys = [("input", input_key(row))]
        if row["group"] is not None:
            keys.append(("group", row["group"]))
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            seen[key] = i
    groups = [find(i) for i in range(len(records))]
    supplied = {r["split"] is not None for r in records}
    if len(supplied) != 1:
        raise ValueError("Supply every split or omit every split")
    if supplied == {False}:
        if any(r["label_source"] == "teacher" for r in records):
            raise ValueError("Teacher labels require explicit train-only placement")
        for label in classes:
            if len({g for g, r in zip(groups, records) if r["label"] == label}) < 5:
                raise ValueError(
                    "Automatic splitting needs five independent groups per class"
                )
        splitter = StratifiedGroupKFold(5, shuffle=True, random_state=seed)
        for fold, (_, indices) in enumerate(
            splitter.split(groups, [r["label"] for r in records], groups)
        ):
            split = "test" if fold == 0 else "validation" if fold == 1 else "train"
            for i in indices:
                records[i]["split"] = split

    partitions: dict[int, set[str]] = {}
    for group, row in zip(groups, records):
        partitions.setdefault(group, set()).add(row["split"])
        if row["label_source"] == "teacher" and row["split"] != "train":
            raise ValueError("Teacher-generated labels cannot certify a model")
    if any(len(splits) > 1 for splits in partitions.values()):
        raise ValueError("Groups or duplicate inputs cross evaluation boundaries")
    counts = {}
    for split in ("train", "validation", "test"):
        counts[split] = dict(
            Counter(r["label"] for r in records if r["split"] == split)
        )
        if set(counts[split]) != set(classes):
            raise ValueError(
                f"Every class must be represented in {split}; provide explicit splits"
            )
    return {
        "rows": records,
        "mode": mode,
        "classes": classes,
        "counts": counts,
        "seed": seed,
        "feature_width": len(records[0]["features"]) if mode == "features" else None,
    }


def inputs(rows: list[dict[str, Any]], mode: str) -> list[Any]:
    """Extract only model inputs; labels/groups/split never become features."""
    return [row[mode] for row in rows]
