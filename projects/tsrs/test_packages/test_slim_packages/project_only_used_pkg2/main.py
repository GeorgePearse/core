"""Consumer that imports only used_pkg2."""

from used_pkg2 import greet2  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting from used_pkg2."""

    return greet2()


if __name__ == "__main__":
    print(main())
