"""Integration tests for get_kb_index and get_kb_topic."""

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


# ---------------------------------------------------------------------------
# interview_kb_index
# ---------------------------------------------------------------------------


async def test_kb_index_returns_all_entries(tmp_path: Path) -> None:
    payload = await _call(tmp_path, "get_kb_index", {})
    topics = payload["topics"]
    assert isinstance(topics, list)
    assert len(topics) == payload["total"]
    assert payload["total"] >= 3


async def test_kb_index_topic_shape(tmp_path: Path) -> None:
    payload = await _call(tmp_path, "get_kb_index", {})
    topic = payload["topics"][0]
    assert "slug" in topic
    assert "name" in topic
    assert "domain" in topic
    assert "tags" in topic
    assert "description" in topic
    assert isinstance(topic["tags"], list)


async def test_kb_index_includes_known_entry(tmp_path: Path) -> None:
    payload = await _call(tmp_path, "get_kb_index", {})
    slugs = [t["slug"] for t in payload["topics"]]
    assert "observer-pattern" in slugs


# ---------------------------------------------------------------------------
# interview_detail
# ---------------------------------------------------------------------------


async def test_detail_returns_full_entry(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "get_kb_topic",
        {"slug": "observer-pattern", "domain": "system-design"},
    )
    assert payload["slug"] == "observer-pattern"
    assert payload["domain"] == "system-design"
    assert "description" in payload
    assert "interview_questions" in payload
    assert "talking_points" in payload


async def test_detail_not_found(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "get_kb_topic",
        {"slug": "nonexistent", "domain": "system-design"},
    )
    assert "error" in payload
