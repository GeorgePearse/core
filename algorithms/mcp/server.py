"""MCP server exposing the algorithms reference library.

Run with:
    uv run --with fastmcp python algorithms/mcp/server.py

Reads algorithms/index.json (regenerate with algorithms/tools/build_index.py
after adding algorithms).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP

ALGORITHMS_ROOT = Path(__file__).resolve().parent.parent

mcp = FastMCP(
    "algorithms",
    instructions=(
        "Reference library of classic algorithms implemented in multiple "
        "languages. Use get_algorithm to fetch a known-good implementation "
        "instead of writing one from scratch."
    ),
)


def _load_index() -> list[dict]:
    index_path = ALGORITHMS_ROOT / "index.json"
    return json.loads(index_path.read_text())["algorithms"]


@mcp.tool()
def list_algorithms(category: str | None = None, tag: str | None = None) -> list[dict]:
    """List available algorithms, optionally filtered by category or tag.

    Returns name, category, description, and available languages for each.
    """
    results = []
    for entry in _load_index():
        if category and entry["category"] != category:
            continue
        if tag and tag not in entry.get("tags", []):
            continue
        results.append(
            {
                "name": entry["name"],
                "category": entry["category"],
                "description": entry["description"],
                "languages": sorted(entry["languages"]),
            }
        )
    return results


@mcp.tool()
def get_algorithm(name: str, language: str | None = None) -> dict:
    """Fetch an algorithm's metadata and source code.

    If language is given (e.g. 'python', 'rust', 'typescript', 'go'), returns
    only that implementation; otherwise returns all of them.
    """
    for entry in _load_index():
        if entry["name"] != name:
            continue
        languages = entry["languages"]
        if language is not None:
            if language not in languages:
                return {
                    "error": f"'{name}' has no {language} implementation",
                    "available_languages": sorted(languages),
                }
            selected = {language: languages[language]}
        else:
            selected = languages
        return {
            **{k: v for k, v in entry.items() if k != "languages"},
            "implementations": {
                lang: (ALGORITHMS_ROOT / rel_path).read_text()
                for lang, rel_path in selected.items()
            },
        }
    return {"error": f"unknown algorithm '{name}'", "hint": "use list_algorithms"}


@mcp.tool()
def search_algorithms(query: str) -> list[dict]:
    """Case-insensitive substring search over names, tags, and descriptions."""
    q = query.lower()
    results = []
    for entry in _load_index():
        haystack = " ".join(
            [entry["name"], entry["description"], " ".join(entry.get("tags", []))]
        ).lower()
        if q in haystack:
            results.append(
                {
                    "name": entry["name"],
                    "category": entry["category"],
                    "description": entry["description"],
                    "languages": sorted(entry["languages"]),
                }
            )
    return results


if __name__ == "__main__":
    mcp.run()
