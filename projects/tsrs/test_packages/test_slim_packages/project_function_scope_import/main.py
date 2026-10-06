"""Consumer script that performs an import inside the main function."""


def main() -> str:
    """Import within function scope and call the greeting."""

    from used_pkg import greet  # type: ignore[import-not-found]

    return greet()


if __name__ == "__main__":
    print(main())
