"""Fixture module covering class/staticmethods and nested functions.

Used by minify/apply integration tests to exercise flags for:
- nested functions
- imports within a function
- reserved identifiers (self, cls)
"""


class Greeter:
    def greet(self, name: str) -> str:
        """Return a formatted greeting using a nested helper."""

        from textwrap import shorten

        def format_name(raw: str) -> str:
            return raw.strip().title()

        message = format_name(name)
        return shorten(f"Hello, {message}", width=32)

    @classmethod
    def class_signature(cls) -> str:
        """Expose class name via a nested closure."""

        def inner() -> str:
            return cls.__name__

        return inner()

    @staticmethod
    def shout(words: str) -> str:
        """Uppercase helper used to keep locals in scope."""

        return words.upper()


def outer_helper(values: list[int]) -> int:
    """Contain a nested function to accumulate values."""

    def accumulator() -> int:
        total = 0
        for value in values:
            total += value
        return total

    return accumulator()
