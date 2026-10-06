"""Tests for slide deck consistency."""

from __future__ import annotations

import re
from pathlib import Path


def test_all_slides_have_identical_sidebar():
    """Verify every slide has the same navigation sidebar entries."""
    slides_path = Path(__file__).parent.parent / "slides.md"
    content = slides_path.read_text()

    # Extract all nav blocks
    nav_pattern = r'<div class="nav">(.*?)</div>'
    nav_blocks = re.findall(nav_pattern, content, re.DOTALL)

    assert len(nav_blocks) > 0, "No nav blocks found in slides.md"

    # Extract page names from each nav block (ignore active class)
    def extract_pages(nav_html: str) -> list[str]:
        # Match <span>Page Name</span> or <span class="active">Page Name</span>
        span_pattern = r'<span[^>]*>([^<]+)</span>'
        return re.findall(span_pattern, nav_html)

    all_page_lists = [extract_pages(nav) for nav in nav_blocks]

    # All should be identical
    first = all_page_lists[0]
    for i, pages in enumerate(all_page_lists[1:], start=2):
        assert pages == first, (
            f"Slide {i} nav differs from slide 1.\n"
            f"Expected: {first}\n"
            f"Got: {pages}"
        )
