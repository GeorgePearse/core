"""Fixture module containing list/dict comprehensions for minify metadata."""


def build_structures(limit: int) -> tuple[list[int], dict[int, int]]:
    """Return comprehension-generated data structures."""

    squares = [value * value for value in range(limit)]
    mapping = {value: value + 1 for value in range(limit)}
    return squares, mapping
