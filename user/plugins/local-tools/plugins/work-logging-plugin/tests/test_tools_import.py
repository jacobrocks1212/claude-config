"""Integration tests for import_artifacts MCP tool."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from servers.work_logging_mcp.server import create_server

FIXTURES_KB = Path(__file__).parent / "fixtures" / "knowledge-bank"
SAMPLE_ARTIFACTS = Path(__file__).parent / "fixtures" / "sample-artifacts"


async def _call(tmp_path: Path, tool: str, args: dict[str, object]) -> dict[str, object]:
    server = create_server(kb_path=FIXTURES_KB, data_path=tmp_path)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(tool, args)
        assert not result.isError
        return json.loads(result.content[0].text)  # type: ignore[union-attr,no-any-return]


async def test_import_scans_directory(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "import_artifacts",
        {"directory": str(SAMPLE_ARTIFACTS), "project": "algobooth"},
    )
    assert payload["total"] > 0
    assert len(payload["imported"]) > 0


async def test_import_dedup_on_reimport(tmp_path: Path) -> None:
    args = {"directory": str(SAMPLE_ARTIFACTS), "project": "algobooth"}
    await _call(tmp_path, "import_artifacts", args)
    payload = await _call(tmp_path, "import_artifacts", args)
    assert len(payload["skipped"]) > 0
    assert len(payload["imported"]) == 0


async def test_import_dry_run(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "import_artifacts",
        {"directory": str(SAMPLE_ARTIFACTS), "project": "algobooth", "dry_run": True},
    )
    assert payload["total"] > 0
    assert not (tmp_path / "features.jsonl").exists()


async def test_import_extracts_title(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "import_artifacts",
        {"directory": str(SAMPLE_ARTIFACTS), "project": "algobooth"},
    )
    titles = [item["title"] for item in payload["imported"]]
    assert "Audio Vision Pipeline" in titles


async def test_import_filters_artifact_types(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "import_artifacts",
        {
            "directory": str(SAMPLE_ARTIFACTS),
            "project": "algobooth",
            "artifact_types": ["spec"],
        },
    )
    # Only SPEC.md files should be imported (2 of them), not PHASES.md
    assert payload["total"] == 2
    assert len(payload["imported"]) == 2
