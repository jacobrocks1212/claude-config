"""Integration tests for atomic MCP tools."""

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
    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "skill": "fix",
            "project": "algobooth",
            "title": "Fix buffer",
            "summary": "Fixed buffer",
            "files_modified": ["src/buf.rs"],
            "timestamp": "2026-04-01T10:00:00Z",
            "feature": "audio-pipeline",
        },
        {
            "skill": "spec",
            "project": "cognito-forms",
            "title": "Payment spec",
            "summary": "Payment design",
            "files_modified": ["docs/SPEC.md"],
            "timestamp": "2026-04-02T10:00:00Z",
        },
    ]
    with (tmp_path / "work-log.jsonl").open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _seed_features(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "id": "feat-1",
            "slug": "audio-pipeline",
            "project": "algobooth",
            "title": "Audio Pipeline",
            "summary": "Real-time audio processing",
            "topic_correlations": [{"slug": "observer-pattern", "domain": "ood", "score": 2}],
        },
        {
            "id": "feat-2",
            "slug": "payment",
            "project": "cognito-forms",
            "title": "Payment Processing",
            "summary": "Multi-provider payments",
        },
    ]
    with (tmp_path / "features.jsonl").open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


# ---------------------------------------------------------------------------
# read_work_log
# ---------------------------------------------------------------------------


async def test_read_work_log_all(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(tmp_path, "read_work_log", {})
    assert payload["count"] == 2


async def test_read_work_log_filter_project(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(tmp_path, "read_work_log", {"project": "algobooth"})
    assert payload["count"] == 1


async def test_read_work_log_filter_feature(tmp_path: Path) -> None:
    _seed_work_log(tmp_path)
    payload = await _call(tmp_path, "read_work_log", {"feature": "audio-pipeline"})
    assert payload["count"] == 1


# ---------------------------------------------------------------------------
# read_features
# ---------------------------------------------------------------------------


async def test_read_features_all(tmp_path: Path) -> None:
    _seed_features(tmp_path)
    payload = await _call(tmp_path, "read_features", {})
    assert payload["count"] == 2


async def test_read_features_filter_project(tmp_path: Path) -> None:
    _seed_features(tmp_path)
    payload = await _call(tmp_path, "read_features", {"project": "algobooth"})
    assert payload["count"] == 1


async def test_read_features_filter_has_correlations(tmp_path: Path) -> None:
    _seed_features(tmp_path)
    payload = await _call(tmp_path, "read_features", {"has_correlations": True})
    assert payload["count"] == 1
    assert payload["features"][0]["slug"] == "audio-pipeline"


# ---------------------------------------------------------------------------
# evaluate_topic_match
# ---------------------------------------------------------------------------


async def test_evaluate_topic_match_returns_score(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "evaluate_topic_match",
        {
            "feature_summary": "Implemented token bucket rate limiting",
            "topic_slug": "observer-pattern",
            "topic_domain": "system-design",
        },
    )
    assert "score" in payload
    assert payload["score"] in (0, 1, 2)


async def test_evaluate_topic_match_not_found(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "evaluate_topic_match",
        {
            "feature_summary": "Some feature",
            "topic_slug": "nonexistent",
            "topic_domain": "system-design",
        },
    )
    assert "error" in payload


# ---------------------------------------------------------------------------
# write_managed_block
# ---------------------------------------------------------------------------


async def test_write_managed_block_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "vault" / "test.md"
    payload = await _call(
        tmp_path,
        "write_managed_block",
        {"file_path": str(target), "content": "Generated content"},
    )
    assert payload["status"] == "ok"
    assert target.exists()
    assert "Generated content" in target.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# calculate_hash
# ---------------------------------------------------------------------------


async def test_calculate_hash_returns_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "test.md"
    test_file.write_text("hello world", encoding="utf-8")
    payload = await _call(
        tmp_path,
        "calculate_hash",
        {"file_path": str(test_file)},
    )
    assert payload["hash"].startswith("sha256:")
    assert len(str(payload["hash"])) == 71


async def test_calculate_hash_not_found(tmp_path: Path) -> None:
    payload = await _call(
        tmp_path,
        "calculate_hash",
        {"file_path": str(tmp_path / "nonexistent.md")},
    )
    assert "error" in payload
