"""Application entry point that relies on relative imports within the package."""

from . import utils


def main() -> str:
    """Return the greeting obtained from used_pkg via utils."""

    return utils.call()


if __name__ == "__main__":
    print(main())
