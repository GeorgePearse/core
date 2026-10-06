"""Helpers for verifying native library resources are packaged."""

from importlib.resources import files


def has_native_lib() -> bytes:
    """Return the raw contents of the bundled native library."""

    lib_path = files(__package__).joinpath("libs/libdummy.so")
    return lib_path.read_bytes()


__all__ = ["has_native_lib"]
