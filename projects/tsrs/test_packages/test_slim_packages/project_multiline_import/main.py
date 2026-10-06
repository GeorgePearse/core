"""Consumer script that uses a multiline import list."""

from used_pkg.subpkg.tool import (  # type: ignore[import-not-found]
    get_tool_name,
)


def main() -> str:
    """Return the tool name from a multiline import statement."""

    return get_tool_name()


if __name__ == "__main__":
    print(main())
