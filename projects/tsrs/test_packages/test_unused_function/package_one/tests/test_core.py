"""Tests for the core module."""

import pytest

from package_one.core import HelloWorld, add_one_and_one


def test_add_one_and_one() -> None:
    """Test that add_one_and_one returns 2."""
    assert add_one_and_one() == 2


def test_hello_world_greet(capsys) -> None:
    """Test that HelloWorld.greet prints hello world."""
    hello = HelloWorld()
    hello.greet()
    captured = capsys.readouterr()
    assert captured.out == "hello world\n"
