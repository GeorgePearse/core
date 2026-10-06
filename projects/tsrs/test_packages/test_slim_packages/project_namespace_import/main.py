"""Consumer script that imports from a namespace package."""

from used_ns_pkg.sub.helper import greet_ns  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting from the namespace package."""

    return greet_ns()


if __name__ == "__main__":
    print(main())
