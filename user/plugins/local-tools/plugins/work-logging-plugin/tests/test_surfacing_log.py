"""Tests for SurfacingLogWriter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from servers.work_logging_mcp.surfacing import SurfacingLogWriter


def test_surfacing_log_writer_appends_entry(tmp_path: Path) -> None:
    SurfacingLogWriter(tmp_path).append({"work_title": "Test", "surfaced": True})
    record: dict[str, Any] = json.loads(
        (tmp_path / "surfacing-log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert record["work_title"] == "Test"
    assert record["surfaced"] is True


def test_surfacing_log_writer_stamps_timestamp(tmp_path: Path) -> None:
    SurfacingLogWriter(tmp_path).append({"work_title": "Test"})
    record: dict[str, Any] = json.loads(
        (tmp_path / "surfacing-log.jsonl").read_text(encoding="utf-8").strip()
    )
    assert "timestamp" in record
    assert "T" in record["timestamp"]
    assert "Z" in record["timestamp"]


def test_surfacing_log_writer_does_not_auto_commit(tmp_path: Path) -> None:
    with patch("servers.work_logging_mcp.surfacing.subprocess.run") as mock_run:
        SurfacingLogWriter(tmp_path).append({"work_title": "Test"})
    mock_run.assert_not_called()
