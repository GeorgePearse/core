"""Unused fixture package that should be pruned by slim."""


def wave() -> str:
    """Return a greeting that is never imported by the consumer."""

    return "hello from unused_pkg"
