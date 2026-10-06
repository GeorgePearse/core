# mypy: ignore-errors
"""Consumer script using a backslash continuation for imports."""

from used_pkg.subpkg.tool import \
    get_tool_name


def main() -> str:
    """Return the tool name retrieved via a backslash-continued import."""

    return get_tool_name()


if __name__ == "__main__":
    print(main())
