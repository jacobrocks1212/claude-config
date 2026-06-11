"""Markdown summary extraction for feature enrichment."""

from __future__ import annotations

import re
from pathlib import Path

_MAX_WORDS = 500


def extract_summary(file_path: Path) -> str:
    """Extract a summary from a markdown file.

    Returns content of '## Executive Summary' section if present,
    otherwise returns the first paragraph after the title heading.
    Returns '' on any error.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return ""

    # Try Executive Summary section first (tolerate optional bold markers)
    exec_match = re.search(
        r"^##\s+\*{0,2}Executive Summary\*{0,2}\s*\n(.*?)(?=^##|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if exec_match:
        words = exec_match.group(1).split()
        return " ".join(words[:_MAX_WORDS]).strip()

    # Fall back: content after first # heading, up to next ## heading
    after_title = re.sub(r"^#[^#][^\n]*\n", "", text, count=1, flags=re.MULTILINE)
    before_next = re.split(r"^##", after_title, maxsplit=1, flags=re.MULTILINE)[0]
    words = before_next.split()
    truncated = " ".join(words[:_MAX_WORDS])
    if truncated.strip():
        return truncated.strip()

    # Final fallback: content of the FIRST ## section
    first_section = re.search(
        r"^##[^#][^\n]*\n(.*?)(?=^##|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if first_section:
        words = first_section.group(1).split()
        return " ".join(words[:_MAX_WORDS]).strip()

    return ""
