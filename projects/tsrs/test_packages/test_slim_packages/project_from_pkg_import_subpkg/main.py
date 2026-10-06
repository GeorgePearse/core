"""Consumer that imports subpackage directly from the package root."""
from used_pkg import subpkg  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting obtained from subpkg imported via from-import."""

    return subpkg.tool.get_tool_name()


if __name__ == "__main__":
    print(main())
