"""Used fixture package for slim integration tests."""

from __future__ import annotations

import json
import pkgutil
from typing import Any, Dict

import importlib.resources as resources
from importlib.resources import files
from .subpkg.tool import get_tool_name


def greet() -> str:
    """Return a friendly greeting used by the consumer project."""

    return "hello from used_pkg"


def load_config() -> Dict[str, Any]:
    """Load JSON configuration bundled with the package resources."""

    with resources.open_text("used_pkg.resources", "config.json", encoding="utf-8") as handle:
        return json.load(handle)


def load_template(name: str = "welcome.txt") -> str:
    """Read a text template stored under the resources/templates directory."""

    with resources.open_text("used_pkg.resources.templates", name, encoding="utf-8") as handle:
        return handle.read()


def load_config_pkgutil() -> Dict[str, Any]:
    """Load JSON configuration using pkgutil.get_data."""

    data = pkgutil.get_data("used_pkg", "resources/config.json")
    if data is None:
        raise FileNotFoundError("config.json not found via pkgutil")
    return json.loads(data.decode("utf-8"))


def load_config_files_api() -> Dict[str, Any]:
    """Load JSON configuration using importlib.resources.files."""

    config_path = files("used_pkg").joinpath("resources/config.json")
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
