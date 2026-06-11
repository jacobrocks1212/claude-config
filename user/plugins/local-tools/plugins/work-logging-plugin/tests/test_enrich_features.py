from __future__ import annotations

from pathlib import Path

from servers.work_logging_mcp.extract import extract_summary


def test_enrich_extracts_executive_summary(tmp_path: Path) -> None:
    # Arrange
    md = tmp_path / "feature.md"
    md.write_text(
        "# My Feature\n\n"
        "Some intro.\n\n"
        "## Executive Summary\n\n"
        "This is the executive summary content that should be extracted.\n"
        "It spans multiple lines.\n\n"
        "## Next Section\n\n"
        "More content here.\n",
        encoding="utf-8",
    )

    # Act
    result = extract_summary(md)

    # Assert
    assert "executive summary content" in result
    assert "Next Section" not in result
    assert "More content here" not in result


def test_enrich_extracts_first_paragraph_without_heading(tmp_path: Path) -> None:
    # Arrange
    md = tmp_path / "feature.md"
    md.write_text(
        "# My Feature Title\n\n"
        "This is the first paragraph of the document. It describes the feature "
        "in detail and should be extracted when there is no Executive Summary heading.\n\n"
        "## Some Other Section\n\n"
        "Other content.\n",
        encoding="utf-8",
    )

    # Act
    result = extract_summary(md)

    # Assert
    assert "first paragraph" in result
    assert "Other content" not in result


def test_enrich_skips_already_rich_summaries(tmp_path: Path) -> None:
    # Arrange
    rich_summary = "x" * 101
    short_summary = "x" * 99

    # Act & Assert
    assert len(rich_summary) > 100, "rich summary should exceed threshold"
    assert len(short_summary) <= 100, "short summary should be at or below threshold"


def test_enrich_handles_missing_source_file() -> None:
    # Arrange
    missing = Path("/nonexistent/file.md")

    # Act
    result = extract_summary(missing)

    # Assert
    assert result == ""


def test_enrich_extracts_bold_executive_summary(tmp_path: Path) -> None:
    # Arrange
    md = tmp_path / "research.md"
    md.write_text(
        "# Research Title\n\n"
        "## **Executive Summary**\n\n"
        "This bold executive summary should be extracted.\n\n"
        "## Next Section\n\n"
        "Other content.\n",
        encoding="utf-8",
    )

    # Act
    result = extract_summary(md)

    # Assert
    assert "bold executive summary" in result
    assert "Other content" not in result


def test_enrich_extracts_first_section_when_no_preamble(tmp_path: Path) -> None:
    # Arrange
    md = tmp_path / "spec.md"
    md.write_text(
        "# My Spec Title\n\n"
        "## Problem Statement\n\n"
        "The system has a critical issue that needs fixing.\n\n"
        "## Solution\n\n"
        "The solution involves...\n",
        encoding="utf-8",
    )

    # Act
    result = extract_summary(md)

    # Assert
    assert "critical issue" in result
    assert "solution involves" not in result
