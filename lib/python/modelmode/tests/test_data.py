"""Leaks are rejected before a search has access to any examples."""

import pytest

from modelmode.data import prepare


def test_normalized_duplicate_crossing_splits(rows: list[dict]) -> None:
    rows[20]["text"] = rows[0]["text"].upper().replace(" ", "  ")
    with pytest.raises(ValueError, match="cross evaluation"):
        prepare(rows)


def test_transitive_group_crossing_splits(rows: list[dict]) -> None:
    rows[0]["group"] = "camera-A"
    rows[1]["group"] = "camera-A"
    rows[20]["text"] = rows[1]["text"]
    with pytest.raises(ValueError, match="cross evaluation"):
        prepare(rows)


def test_teacher_labels_train_only(rows: list[dict]) -> None:
    rows[0]["label_source"] = "teacher"
    assert prepare(rows)["rows"]
    rows[20]["label_source"] = "teacher"
    with pytest.raises(ValueError, match="cannot certify"):
        prepare(rows)


def test_auto_split_stable_under_row_reordering(rows: list[dict]) -> None:
    for row in rows:
        row.pop("split")
    assert prepare(rows) == prepare(list(reversed(rows)))


def test_feature_validation(rows: list[dict]) -> None:
    for row in rows:
        row.pop("text")
        row["features"] = [float(row["id"].rsplit("-", 1)[1]), 0.1]
    rows[0]["features"] = [float("nan"), 1.0]
    with pytest.raises(ValueError, match="finite"):
        prepare(rows)
