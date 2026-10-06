"""Consumer script combining multiple imports in a single statement."""

import used_pkg, used_pkg.subpkg.tool as tool_module  # type: ignore[import-not-found]


def main() -> tuple[str, str]:
    """Return both the greeting and tool name from a multi-import statement."""

    return used_pkg.greet(), tool_module.get_tool_name()


if __name__ == "__main__":
    print(main())
