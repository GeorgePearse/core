"""Consumer script that imports a single-module distribution."""

from used_mod import greet_mod  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting from the single-module package."""

    return greet_mod()


if __name__ == "__main__":
    print(main())
