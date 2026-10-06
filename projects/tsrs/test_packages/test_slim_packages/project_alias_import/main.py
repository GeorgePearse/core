"""Consumer script that aliases the used_pkg module on import."""

import used_pkg as used  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting accessed through an alias."""

    return used.greet()


if __name__ == "__main__":
    print(main())
