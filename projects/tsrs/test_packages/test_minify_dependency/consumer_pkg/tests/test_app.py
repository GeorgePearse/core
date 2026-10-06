"""Pytest suite that verifies the consumer behavior after minification."""

from __future__ import annotations

from minify_consumer import summarize_numbers, welcome


def test_welcome_uses_dependency_output() -> None:
    message = welcome("Ada")
    assert message == "consumer Hello, Ada!"


def test_summarize_numbers_formats_output() -> None:
    summary = summarize_numbers([1, 2, 3])
    assert summary == "0:1 1:2 2:3 => Hello, 6! (total=14, count=3)"
