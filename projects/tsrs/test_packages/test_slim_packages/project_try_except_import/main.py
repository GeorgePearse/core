"""Consumer script that imports used_pkg inside a try/except block."""

try:
    from used_pkg import greet  # type: ignore[import-not-found]
except ImportError as error:  # pragma: no cover - fallback path unused
    raise SystemExit(f"missing dependency: {error}")


def main() -> str:
    """Return the greeting from the guarded import."""

    return greet()


if __name__ == "__main__":
    print(main())
