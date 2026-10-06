"""Consumer script that uses a wildcard import from used_pkg."""

from used_pkg import *  # type: ignore[import-not-found,unused-wildcard-import]


def main() -> str:
    """Return the greeting exposed via the wildcard import."""

    return greet()  # type: ignore[name-defined]


if __name__ == "__main__":
    print(main())
