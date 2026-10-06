"""Consumer script that pulls exports via wildcard from a submodule."""

from used_pkg.subpkg import *  # type: ignore[import-not-found,unused-wildcard-import]


def main() -> str:
    """Return the tool name exposed through the wildcard import."""

    return get_tool_name()  # type: ignore[name-defined]


if __name__ == "__main__":
    print(main())
