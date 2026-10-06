from dash_pkg import greet  # type: ignore[import-not-found]


def main() -> str:
    return greet()


if __name__ == "__main__":
    print(main())
