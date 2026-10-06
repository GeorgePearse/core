"""Consumer script that aliases a used_pkg submodule."""

import used_pkg.subpkg.tool as tool_module  # type: ignore[import-not-found]


def main() -> str:
    """Return the tool name by using the aliased submodule."""

    return tool_module.get_tool_name()


if __name__ == "__main__":
    print(main())
