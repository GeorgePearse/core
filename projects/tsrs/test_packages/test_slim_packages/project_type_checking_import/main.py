from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from used_pkg import greet  # type: ignore[import-not-found]


def main() -> str:
    return "type-checking only"


if __name__ == "__main__":
    print(main())
