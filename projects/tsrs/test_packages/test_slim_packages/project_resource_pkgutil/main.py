"""Consumer script that loads used_pkg resources via pkgutil.get_data."""

from used_pkg import load_config_pkgutil  # type: ignore[import-not-found]


def main() -> str:
    """Return the greeting loaded via pkgutil."""

    config = load_config_pkgutil()
    return config["greeting"]


if __name__ == "__main__":
    print(main())
