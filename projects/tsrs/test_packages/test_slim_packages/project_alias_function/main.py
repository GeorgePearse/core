"""Consumer script that aliases a function imported from used_pkg."""

from used_pkg import greet as greet_alias  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting via an aliased function import."""

    return greet_alias()


if __name__ == "__main__":
    print(main())
