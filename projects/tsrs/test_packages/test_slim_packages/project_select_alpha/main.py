"""Consumer that imports only the alpha module."""

from alpha import greet_alpha  # type: ignore[import-not-found]

def main() -> str:
    """Return the greeting emitted by alpha.greet_alpha."""

    return greet_alpha()


if __name__ == "__main__":
    print(main())
