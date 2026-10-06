"""Consumer script that imports the used_pkg package directly."""

import used_pkg  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting from the used package."""

    return used_pkg.greet()


if __name__ == "__main__":
    print(main())
