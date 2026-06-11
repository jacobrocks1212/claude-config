"""Tests for managed block read/write operations."""

from __future__ import annotations

from pathlib import Path

from servers.work_logging_mcp.managed_blocks import (
    has_managed_block,
    read_managed_block,
    write_managed_block,
)


def test_write_creates_file_with_delimiters(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    write_managed_block(target, "Generated content here")
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "<!-- BEGIN MANAGED -->" in content
    assert "<!-- END MANAGED -->" in content
    assert "Generated content here" in content


def test_read_extracts_managed_content(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    write_managed_block(target, "My generated block")
    result = read_managed_block(target)
    assert result is not None
    assert "My generated block" in result


def test_write_preserves_user_content(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    # Create file with user content + managed block
    target.write_text(
        "# My Notes\n\nPersonal thoughts here.\n\n"
        "<!-- BEGIN MANAGED -->\nOld generated content\n<!-- END MANAGED -->\n\n"
        "More personal notes below.\n",
        encoding="utf-8",
    )
    # Regenerate managed block
    write_managed_block(target, "New generated content")
    content = target.read_text(encoding="utf-8")
    assert "Personal thoughts here." in content
    assert "More personal notes below." in content
    assert "New generated content" in content
    assert "Old generated content" not in content


def test_has_managed_block_true(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    write_managed_block(target, "content")
    assert has_managed_block(target) is True


def test_has_managed_block_false(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("# Just a normal file\n", encoding="utf-8")
    assert has_managed_block(target) is False


def test_has_managed_block_nonexistent(tmp_path: Path) -> None:
    target = tmp_path / "nonexistent.md"
    assert has_managed_block(target) is False


def test_read_returns_none_for_no_block(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("No managed block here\n", encoding="utf-8")
    assert read_managed_block(target) is None


def test_read_returns_none_for_nonexistent(tmp_path: Path) -> None:
    target = tmp_path / "nonexistent.md"
    assert read_managed_block(target) is None


def test_write_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    write_managed_block(target, "First version")
    assert "First version" in (read_managed_block(target) or "")
    write_managed_block(target, "Second version")
    result = read_managed_block(target)
    assert result is not None
    assert "Second version" in result
    assert "First version" not in result


def test_write_appends_block_to_existing_file_without_delimiters(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("# Existing content\n", encoding="utf-8")
    write_managed_block(target, "New managed content")
    content = target.read_text(encoding="utf-8")
    assert "Existing content" in content
    assert "New managed content" in content
    assert "<!-- BEGIN MANAGED -->" in content
