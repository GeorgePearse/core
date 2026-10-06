from used_pkg import get_tool_name  # type: ignore[import-not-found]


def main() -> str:
    return get_tool_name()


if __name__ == "__main__":
    print(main())
