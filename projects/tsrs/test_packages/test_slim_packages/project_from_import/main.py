"""Consumer script that uses a from-import of used_pkg."""

from used_pkg import greet  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting imported via from-import."""

    return greet()


if __name__ == "__main__":
    print(main())
