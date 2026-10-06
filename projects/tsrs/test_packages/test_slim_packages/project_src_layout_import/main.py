"""Consumer script importing the src-layout package."""

from used_src_layout import greet_src  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting provided by the src-layout package."""

    return greet_src()


if __name__ == "__main__":
    print(main())
