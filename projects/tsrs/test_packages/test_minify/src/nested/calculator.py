"""Nested fixture module containing additional locals."""


def accumulate(values: list[int]) -> int:
    """Return the sum of the provided values using an accumulator."""

    total = 0
    for value in values:
        total += value
    return total
