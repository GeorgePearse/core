"""Consumer script that reads package resources after importing used_pkg."""

from used_pkg import load_config  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting stored inside the packaged resource file."""

    config = load_config()
    return config["greeting"]


if __name__ == "__main__":
    print(main())
