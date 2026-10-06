"""Consumer script importing the implicit namespace package."""

from used_ns_implicit.sub.helper import greet_ns_implicit  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting emitted by the implicit namespace package."""

    return greet_ns_implicit()


if __name__ == "__main__":
    print(main())
