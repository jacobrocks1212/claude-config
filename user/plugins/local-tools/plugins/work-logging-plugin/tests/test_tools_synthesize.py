"""Integration tests for synthesize_features MCP tool."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from servers.work_logging_mcp.server import create_server

FIXTURES_KB = Path(__file__).parent / "fixtures" / "knowledge-bank"


async def _call(tmp_path: Path, tool: str, args: dict[str, object]) -> dict[str, object]:
    server = create_server(kb_path=FIXTURES_KB, data_path=tmp_path)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(tool, args)
        assert not result.isError
        return json.loads(result.content[0].text)  # type: ignore[union-attr,no-any-return]


def _seed_work_log(tmp_path: Path) -> None:
    """Create work log entries without feature tags (orphaned)."""
    entries = [
        {
            "skill": "fix",
            "project": "algobooth",
            "title": "Fix audio buffer underrun",
            "summary": "Fixed buffer underrun in real-time audio pipeline",
            "files_modified": ["src/audio.rs", "src/buffer.rs"],
            "timestamp": "2026-04-01T10:00:00Z",
        },
        {
            "skill": "implement-phase",
            "project": "algobooth",
            "title": "Add waveform visualization",
            "summary": "Implemented real-time waveform rendering using WebGL",
            "files_modified": ["src/audio.rs", "src/viz.rs"],
            "timestamp": "2026-04-02T10:00:00Z",
        },
        {
            "skill": "spec",
            "project": "cognito-forms",
            "title": "Payment gateway design",
            "summary": "Designed multi-provider payment processing architecture",
            "files_modified": ["docs/payment/SPEC.md"],
            "timestamp": "2026-04-03T10:00:00Z",
        },
    ]
    log_file = tmp_path / "work-log.jsonl"
    tmp_path.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


async def test_synthesize_creates_features(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(tmp_path, "synthesize_features", {})
    assert payload["features_created"] > 0


async def test_synthesize_groups_by_project(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(tmp_path, "synthesize_features", {"project": "algobooth"})
    # Should only synthesize algobooth entries
    assert payload["features_created"] >= 1
    # Check features.jsonl
    features_file = tmp_path / "features.jsonl"
    assert features_file.exists()
    lines = features_file.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    assert all(r["project"] == "algobooth" for r in records)


async def test_synthesize_skips_tagged_entries(tmp_path: Path) -> None:
    """Entries with a feature tag are NOT orphaned and should be skipped."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "work-log.jsonl"
    entries = [
        {
            "skill": "fix",
            "project": "algobooth",
            "title": "Tagged entry",
            "summary": "This is already tagged",
            "files_modified": ["src/main.rs"],
            "timestamp": "2026-04-01T10:00:00Z",
            "feature": "existing-feature",
        },
    ]
    with log_file.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")

    payload = await _call(tmp_path, "synthesize_features", {})
    assert payload["features_created"] == 0
    assert payload["orphaned_remaining"] == 0


async def test_synthesize_without_correlations(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(
        tmp_path,
        "synthesize_features",
        {"include_correlations": False},
    )
    assert payload["features_created"] > 0
    assert payload["correlations_added"] == 0


async def test_synthesize_accepts_use_headless_param(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(
        tmp_path,
        "synthesize_features",
        {"use_headless": True, "include_correlations": False},
    )
    assert payload["features_created"] > 0


async def test_synthesize_uses_placeholder_when_headless_false(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(
        tmp_path,
        "synthesize_features",
        {"use_headless": False, "include_correlations": True},
    )
    # Placeholder judge returns 1 (tangential) for all, so no Score 2 correlations
    assert payload["correlations_added"] == 0
