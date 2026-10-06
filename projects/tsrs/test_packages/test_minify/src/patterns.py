"""Pattern-matching fixture helpers for minify integration tests."""

from __future__ import annotations

PATTERN_MATCH_SOURCE = """
def describe(value: int) -> str:
    match value:
        case 0:
            message = "zero"
        case 1 | 2:
            message = "one or two"
        case _:
            message = "other"
    return message
"""


def describe(value: int) -> str:
    """Runtime fallback using classic conditionals (for Python <3.10)."""

    if value == 0:
        return "zero"
    if value in (1, 2):
        return "one or two"
    return "other"
