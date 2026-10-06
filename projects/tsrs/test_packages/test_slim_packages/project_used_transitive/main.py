"""Consumer that triggers the transitive dependency usage."""

from used_pkg_transitive import combined_value  # type: ignore[import-not-found]
from extra_dep import get_value  # type: ignore[import-not-found]


def main() -> tuple[str, int]:
    """Return values produced by used_pkg_transitive and extra_dep."""

    return combined_value(), get_value()


if __name__ == "__main__":
    print(main())
