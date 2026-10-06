"""Dash named package for slim integration tests."""


def greet() -> str:
    return "hello from dash_pkg"


__all__ = ["greet"]
