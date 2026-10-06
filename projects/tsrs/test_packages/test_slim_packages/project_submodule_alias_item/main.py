"""Consumer script aliasing an item imported from a submodule."""

from used_pkg.subpkg import get_tool_name as fetch_tool  # type: ignore[import-not-found]


def main() -> str:
    """Return the tool name via the aliased item."""

    return fetch_tool()


if __name__ == "__main__":
    print(main())
