"""Consumer script that performs an import inside a conditional block."""

if True:
    from used_pkg import greet  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting acquired inside the if block."""

    return greet()


if __name__ == "__main__":
    print(main())
