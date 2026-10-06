"""Consumer that accesses submodule via chained attribute access."""
import used_pkg  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting resolved through used_pkg.subpkg."""

    return used_pkg.subpkg.tool.get_tool_name()  # type: ignore[attr-defined]


if __name__ == "__main__":
    print(main())
