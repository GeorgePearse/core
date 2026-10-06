"""Consumer script that imports a submodule from used_pkg."""

from used_pkg.subpkg.tool import get_tool_name  # type: ignore[import-not-found]


def main() -> str:
    """Return the tool name sourced from the used_pkg submodule."""

    return get_tool_name()


if __name__ == "__main__":
    print(main())
