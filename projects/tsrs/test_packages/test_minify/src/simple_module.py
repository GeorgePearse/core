"""Fixture module for minification integration tests."""


def greet(name: str) -> str:
    """Create a friendly greeting using intermediate locals."""

    message = f"Hello, {name}"
    suffix = "!"
    return message + suffix
