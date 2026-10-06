"""Consumer that reads a text template shipped with used_pkg."""

from used_pkg import load_template  # type: ignore[import-not-found]


def main() -> str:
    """Return the contents of the packaged welcome template."""

    return load_template()


if __name__ == "__main__":
    print(main())
