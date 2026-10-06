"""Consumer importing namespace modules from multiple distributions."""

from used_ns_pkg.sub.helper import greet_ns  # type: ignore[import-not-found]
from used_ns_pkg.extra.second import greet_ns_extra  # type: ignore[import-not-found]


def main() -> tuple[str, str]:
    """Return greetings from both parts of the namespace package."""

    return greet_ns(), greet_ns_extra()


if __name__ == "__main__":
    print(main())
