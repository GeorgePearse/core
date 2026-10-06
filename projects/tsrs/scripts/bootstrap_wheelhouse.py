#!/usr/bin/env python3
"""Populate a local wheelhouse for integration tests.

The script reads package constraints from ``test_packages/wheelhouse.toml``
and downloads wheels into a shared directory (defaults to
``test_packages/.wheelhouse``). Wheels are fetched via ``uv pip download`` to
keep them deterministic and cached locally for repeated test runs.

Usage:
    python scripts/bootstrap_wheelhouse.py [--manifest PATH] [--dest PATH]
                                           [--python PY] [--platform TAG]

If ``uv`` is unavailable the script falls back to ``pip download``. Downloads
are skipped when an up-to-date wheel already exists in the destination.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


DEFAULT_MANIFEST = Path("test_packages/wheelhouse.toml")


def load_packages(manifest: Path) -> List[str]:
    with manifest.open("rb") as handle:
        data = tomllib.load(handle)

    packages = data.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("wheelhouse manifest must define a non-empty packages list")

    constraints: List[str] = []
    for entry in packages:
        if not isinstance(entry, dict):
            raise ValueError("each package entry must be a table")
        name = entry.get("name")
        version = entry.get("version")
        extras = entry.get("extras", [])
        markers = entry.get("markers")

        if not isinstance(name, str) or not name:
            raise ValueError("package entry missing name")
        if not isinstance(version, str) or not version:
            raise ValueError(f"package '{name}' missing version field")
        if extras and not isinstance(extras, list):
            raise ValueError(f"package '{name}' extras must be a list")

        requirement = name
        if extras:
            requirement = f"{name}[{','.join(extras)}]"
        requirement = f"{requirement}=={version}"
        if isinstance(markers, str) and markers:
            requirement = f"{requirement};{markers}"

        constraints.append(requirement)

    return constraints


def command_exists(binary: str) -> bool:
    return subprocess.call([binary, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def download_with_uv(dest: Path, requirements: Iterable[str], python: str, platform: str | None) -> None:
    args = [
        "uv",
        "pip",
        "download",
        "--dest",
        str(dest),
        "--python",
        python,
        "--resolution",
        "lowest-direct",
    ]
    if platform:
        args.extend(["--platform", platform])

    subprocess.run(args + list(requirements), check=True)


def download_with_pip(dest: Path, requirements: Iterable[str], python: str, platform: str | None) -> None:
    args = [
        python,
        "-m",
        "pip",
        "download",
        "--dest",
        str(dest),
        "--only-binary",
        ":all:",
    ]
    if platform:
        args.extend(["--platform", platform, "--implementation", "py", "--abi", "none"])

    subprocess.run(args + list(requirements), check=True)


def already_cached(dest: Path, requirement: str) -> bool:
    name = requirement.split("==")[0]
    matching = list(dest.glob(f"{name}-*.whl"))
    return bool(matching)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download wheels for integration tests")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="path to wheelhouse manifest")
    parser.add_argument("--dest", type=Path, help="wheel output directory")
    parser.add_argument("--python", default="python3", help="python interpreter to resolve markers")
    parser.add_argument("--platform", default=None, help="target platform tag (optional)")
    args = parser.parse_args()

    manifest = args.manifest
    if not manifest.exists():
        parser.error(f"manifest not found: {manifest}")

    dest = args.dest or manifest.parent / ".wheelhouse"
    dest.mkdir(parents=True, exist_ok=True)

    requirements = load_packages(manifest)
    pending = [req for req in requirements if not already_cached(dest, req)]
    if not pending:
        print(f"wheelhouse already satisfied at {dest}")
        return 0

    print(f"downloading {len(pending)} packages into {dest}")

    if command_exists("uv"):
        download_with_uv(dest, pending, args.python, args.platform)
    else:
        download_with_pip(dest, pending, args.python, args.platform)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
