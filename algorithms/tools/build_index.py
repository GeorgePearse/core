"""Regenerate algorithms/index.json from the meta.yaml files on disk.

Usage: python algorithms/tools/build_index.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ALGORITHMS_ROOT = Path(__file__).resolve().parent.parent
LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "rust": ".rs",
    "typescript": ".ts",
    "go": ".go",
    "cpp": ".cpp",
    "java": ".java",
}


def build_index() -> dict:
    entries = []
    for meta_path in sorted(ALGORITHMS_ROOT.glob("*/*/meta.yaml")):
        algo_dir = meta_path.parent
        meta = yaml.safe_load(meta_path.read_text())

        expected_name = algo_dir.name
        expected_category = algo_dir.parent.name
        if meta.get("name") != expected_name:
            sys.exit(
                f"{meta_path}: name '{meta.get('name')}' does not match "
                f"directory '{expected_name}'"
            )
        if meta.get("category") != expected_category:
            sys.exit(
                f"{meta_path}: category '{meta.get('category')}' does not "
                f"match directory '{expected_category}'"
            )

        languages = {
            language: f"{expected_category}/{expected_name}/{language}{ext}"
            for language, ext in LANGUAGE_EXTENSIONS.items()
            if (algo_dir / f"{language}{ext}").exists()
        }
        if not languages:
            sys.exit(f"{algo_dir}: no implementation files found")

        entries.append({**meta, "languages": languages})

    return {
        "count": len(entries),
        "algorithms": entries,
    }


def main() -> None:
    index = build_index()
    out_path = ALGORITHMS_ROOT / "index.json"
    out_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"Wrote {index['count']} algorithms to {out_path}")


if __name__ == "__main__":
    main()
