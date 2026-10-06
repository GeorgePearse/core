"""Fixture package that depends on extra-dep but exposes its own API."""


def greet_extra() -> str:
    """Return a greeting while the dependency remains unused by consumers."""

    return "hello from used_pkg_extra"
