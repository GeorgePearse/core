"""Dependency package that should not be copied into the slim venv."""


def get_value() -> int:
    """Return a simple value used to ensure the package works if included."""

    return 42
