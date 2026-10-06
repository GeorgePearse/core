"""Utility module that performs a relative import of used_pkg."""

from used_pkg import greet  # type: ignore[import-not-found]


def call() -> str:
    """Call the used_pkg greeting via a relative import."""

    return greet()
