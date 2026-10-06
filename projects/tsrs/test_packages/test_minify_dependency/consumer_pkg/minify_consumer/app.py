"""Application logic that imports the dependency package."""

from __future__ import annotations

from typing import Iterable

from minify_dep import (
    Greeter,
    combine_words,
    format_greeting,
    summarize_numbers as dependency_summarize,
)


def welcome(name: str) -> str:
    """Return a greeting that includes the dependency output."""

    prefix = "consumer"
    greeter = Greeter(template=prefix)
    return greeter.render(name)


def summarize_numbers(values: Iterable[int]) -> str:
    """Summarize numbers with both raw and decorated output."""

    raw_sum = sum(values)
    decorated = combine_words(str(value) for value in values)
    summary = format_greeting(str(raw_sum))
    payload = dependency_summarize(values)
    return f"{decorated} => {summary} (total={payload['total']}, count={payload['count']})"
