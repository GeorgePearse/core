"""Consumer script using importlib.resources.files API."""

from used_pkg import load_config_files_api  # type: ignore[import-not-found]


def main() -> str:
    """Return greeting loaded via the modern resources API."""

    config = load_config_files_api()
    return config["greeting"]


if __name__ == "__main__":
    print(main())
