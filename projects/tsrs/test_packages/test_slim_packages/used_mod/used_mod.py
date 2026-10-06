"""Single-module fixture that exposes a simple greeting."""


def greet_mod() -> str:
    """Return a greeting from the single-module package."""

    return "hello from used_mod"
