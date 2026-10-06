"""Core dependency exercising recursive minification."""

from __future__ import annotations

def build_payload(numbers: list[int]) -> dict[str, int]:
    """Return summary metrics for ``numbers``."""

    total = 0
    for value in numbers:
        extra = value * value
        total += extra
    return {"total": total}
