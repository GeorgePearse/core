"""Class-oriented fixture ensuring reserved identifiers stay untouched."""


class Greeter:
    """Provide instance, class, and static helpers with nested functions."""

    def greet(self, name: str) -> str:
        """Use a nested helper and inline import to trigger planner flags."""

        from textwrap import shorten

        def format_name(raw: str) -> str:
            trimmed = raw.strip()
            return trimmed.title()

        message = format_name(name)
        return shorten(f"Hello, {message}", width=40)

    @classmethod
    def describe(cls) -> str:
        """Leverage a nested closure referencing cls."""

        def inner() -> str:
            return cls.__name__

        return inner()

    @staticmethod
    def shout(words: str) -> str:
        """Static helper to populate locals available for renaming."""

        amplified = words.upper()
        return amplified + "!"


def summarize(values: list[int]) -> int:
    """Contain a nested accumulator to ensure has_nested_functions flag."""

    def accumulator() -> int:
        total = 0
        for item in values:
            total += item
        return total

    return accumulator()
