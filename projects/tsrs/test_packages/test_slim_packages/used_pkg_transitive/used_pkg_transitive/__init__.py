"""Fixture package that imports extra_dep within its public API."""

from extra_dep import get_value  # type: ignore[import-not-found]


def combined_value() -> str:
    """Return a string showing the value sourced from extra_dep."""

    return f"extra_dep returned {get_value()}"
