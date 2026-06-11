"""Managed block read/write for Obsidian vault files.

Managed blocks are delimited by HTML comments:
    <!-- BEGIN MANAGED -->
    ...generated content...
    <!-- END MANAGED -->

Content outside these delimiters is preserved across regenerations.
"""

from __future__ import annotations

from pathlib import Path

_BEGIN = "<!-- BEGIN MANAGED -->"
_END = "<!-- END MANAGED -->"


def has_managed_block(file_path: Path) -> bool:
    """Check if a file contains managed block delimiters."""
    if not file_path.exists():
        return False
    content = file_path.read_text(encoding="utf-8")
    return _BEGIN in content and _END in content


def read_managed_block(file_path: Path) -> str | None:
    """Extract content between managed block delimiters.

    Returns None if file doesn't exist or has no managed block.
    """
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    begin_idx = content.find(_BEGIN)
    end_idx = content.find(_END)
    if begin_idx == -1 or end_idx == -1 or end_idx <= begin_idx:
        return None
    start = begin_idx + len(_BEGIN)
    return content[start:end_idx]


def write_managed_block(file_path: Path, content: str) -> None:
    """Write content into the managed block region of a file.

    If the file doesn't exist, creates it with managed block delimiters.
    If the file exists but has no managed block, appends delimiters.
    If the file has a managed block, replaces only the managed content.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if not file_path.exists():
        file_path.write_text(
            f"{_BEGIN}\n{content}\n{_END}\n",
            encoding="utf-8",
        )
        return

    existing = file_path.read_text(encoding="utf-8")
    begin_idx = existing.find(_BEGIN)
    end_idx = existing.find(_END)

    if begin_idx == -1 or end_idx == -1 or end_idx <= begin_idx:
        # No valid managed block — append one
        file_path.write_text(
            f"{existing}\n{_BEGIN}\n{content}\n{_END}\n",
            encoding="utf-8",
        )
        return

    # Replace managed block content
    before = existing[: begin_idx + len(_BEGIN)]
    after = existing[end_idx:]
    file_path.write_text(
        f"{before}\n{content}\n{after}",
        encoding="utf-8",
    )
