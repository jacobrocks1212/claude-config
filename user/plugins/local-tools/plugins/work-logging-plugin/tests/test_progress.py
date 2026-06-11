"""Tests for progress reporting in composite tools."""

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


async def test_generate_vault_includes_progress(tmp_path: Path) -> None:
    vault_dir = str(tmp_path / "vault")
    payload = await _call(tmp_path, "generate_vault", {"output_dir": vault_dir})
    assert "progress" in payload
    assert payload["progress"]["total_stages"] == 5
    assert len(payload["progress"]["stages_completed"]) == 5


async def test_import_includes_progress(tmp_path: Path) -> None:
    sample_dir = Path(__file__).parent / "fixtures" / "sample-artifacts"
    payload = await _call(
        tmp_path,
        "import_artifacts",
        {"directory": str(sample_dir), "project": "test"},
    )
    assert "progress" in payload
    assert payload["progress"]["files_scanned"] > 0


async def test_synthesize_includes_progress(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "skill": "fix",
            "project": "test",
            "title": "Test fix",
            "summary": "Fixed something",
            "files_modified": ["src/main.rs"],
            "timestamp": "2026-04-01T10:00:00Z",
        },
    ]
    with (tmp_path / "work-log.jsonl").open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")

    payload = await _call(tmp_path, "synthesize_features", {})
    assert "progress" in payload
    assert payload["progress"]["entries_processed"] == 1


async def test_synthesize_no_orphans_includes_progress(tmp_path: Path) -> None:
    """Empty work log returns progress with zero counts."""
    payload = await _call(tmp_path, "synthesize_features", {})
    assert "progress" in payload
    assert payload["progress"]["entries_processed"] == 0
    assert payload["progress"]["groups_found"] == 0
