"""Dependency fixture used to validate minification against a consumer package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from minify_core import build_payload


def format_greeting(name: str) -> str:
    """Return a deterministic greeting for the supplied ``name``."""

    message = f"Hello, {name}"
    suffix = "!"
    combined = message + suffix
    return combined


def combine_words(words: Iterable[str]) -> str:
    """Join ``words`` into a space separated sentence."""

    pieces: List[str] = []
    for index, word in enumerate(words):
        decorated = f"{index}:{word}"
        pieces.append(decorated)
    return " ".join(pieces)


def summarize_numbers(numbers: Iterable[int]) -> dict[str, int]:
    """Delegate to minify_core to compute derived metrics."""

    values = list(numbers)
    payload = build_payload(values)
    payload["count"] = len(values)
    return payload


@dataclass
class Greeter:
    """Simple class that stores a template and renders greetings."""

    template: str

    def render(self, name: str) -> str:
        prefix = self.template
        formatted = format_greeting(name)
        return f"{prefix} {formatted}"
