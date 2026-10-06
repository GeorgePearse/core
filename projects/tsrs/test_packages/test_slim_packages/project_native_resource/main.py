"""Consumer project that ensures native resources are accessible."""

from used_native import has_native_lib  # type: ignore[import-not-found]


def main() -> bool:
    """Return True when the native library resource can be loaded."""

    return bool(has_native_lib())


if __name__ == "__main__":
    print(main())
