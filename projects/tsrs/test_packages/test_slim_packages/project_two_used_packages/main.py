"""Consumer script that imports two used packages."""

from used_pkg import greet  # type: ignore[import-not-found]
from used_pkg2 import greet2  # type: ignore[import-not-found]


def main() -> tuple[str, str]:
    """Return greetings from both used packages."""

    return greet(), greet2()


if __name__ == "__main__":
    print(main())
