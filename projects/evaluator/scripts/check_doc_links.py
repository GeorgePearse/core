#!/usr/bin/env python3
"""Check that all documentation links are valid."""

import re
import sys
from pathlib import Path

# Markdown link patterns
MARKDOWN_LINK_PATTERN = r"\[([^\]]+)\]\(([^)]+)\)"
REFERENCE_LINK_PATTERN = r"^\s*\[([^\]]+)\]:\s*(.+)$"


def find_markdown_files(docs_dir: Path) -> list[Path]:
    """Find all markdown files in docs directory."""
    return sorted(docs_dir.rglob("*.md"))


def extract_links(content: str, file_path: Path) -> list[tuple[str, str, int]]:
    """Extract all links from markdown content.

    Returns list of (link_target, link_text, line_number) tuples.
    """
    links = []

    for i, line in enumerate(content.split("\n"), 1):
        # Skip code blocks
        if line.strip().startswith("```"):
            continue

        # Find inline links [text](url)
        for match in re.finditer(MARKDOWN_LINK_PATTERN, line):
            link_target = match.group(2)
            link_text = match.group(1)

            # Skip external links (http, https, mailto)
            if link_target.startswith(("http://", "https://", "mailto:")):
                continue

            links.append((link_target, link_text, i))

    return links


def resolve_link(base_file: Path, link_target: str, docs_dir: Path) -> bool:
    """Check if a link target resolves to an existing file."""
    # Remove fragment/anchor
    file_path = link_target.split("#")[0] if "#" in link_target else link_target

    if not file_path:
        # Just a fragment on the same page
        return True

    # Resolve relative to the base file's directory
    if file_path.startswith("/"):
        # Absolute path from docs root
        resolved = docs_dir / file_path.lstrip("/")
    else:
        # Relative path
        resolved = (base_file.parent / file_path).resolve()
        docs_resolved = resolved.relative_to(docs_dir.resolve())
        resolved = docs_dir / docs_resolved

    return resolved.exists()


def check_doc_links(docs_dir: Path | None = None) -> int:
    """Check all documentation links.

    Returns 0 if all links are valid, 1 if any are broken.
    """
    if docs_dir is None:
        docs_dir = Path(__file__).parent.parent / "docs"

    docs_dir = docs_dir.resolve()

    if not docs_dir.exists():
        print(f"Error: docs directory not found: {docs_dir}", file=sys.stderr)
        return 1

    markdown_files = find_markdown_files(docs_dir)
    broken_links = []

    for md_file in markdown_files:
        content = md_file.read_text()
        links = extract_links(content, md_file)

        for link_target, link_text, line_num in links:
            if not resolve_link(md_file, link_target, docs_dir):
                rel_path = md_file.relative_to(docs_dir)
                broken_links.append(f"{rel_path}:{line_num} - Link to '{link_target}' not found")

    if broken_links:
        print("Broken documentation links found:", file=sys.stderr)
        for broken in broken_links:
            print(f"  {broken}", file=sys.stderr)
        return 1

    print(f"✓ All documentation links valid ({len(markdown_files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(check_doc_links())
