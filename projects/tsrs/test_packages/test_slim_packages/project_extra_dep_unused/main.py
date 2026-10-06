"""Consumer that imports used_pkg_extra but never touches its dependency."""

from used_pkg_extra import greet_extra  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting exposed by used_pkg_extra."""

    return greet_extra()


if __name__ == "__main__":
    print(main())
