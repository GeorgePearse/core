"""Small independent labelled cohorts for boundary and lifecycle tests."""

import pytest


@pytest.fixture
def rows() -> list[dict]:
    return [
        {
            "id": f"{split}-{label}-{i}",
            "text": f"{label} {label} request {split} number {i}",
            "label": label,
            "split": split,
        }
        for split in ("train", "validation", "test")
        for label in ("payment", "delivery")
        for i in range(10)
    ]
