"""Integration tests for work_log_append MCP tool."""

from __future__ import annotations

import json
import re
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from servers.work_logging_mcp.server import create_server

FIXTURES_KB = Path(__file__).parent / "fixtures" / "knowledge-bank"

ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_VALID_ARGS: dict[str, object] = {
    "skill": "fix",
    "project": "algobooth",
    "title": "Square wave near DC",
    "summary": "Fixed pw=0 default causing DC output",
    "files_modified": ["src/voice.rs"],
}


async def _call(tmp_path: Path, tool: str, args: dict[str, object]) -> dict[str, object]:
    server = create_server(kb_path=FIXTURES_KB, data_path=tmp_path)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(tool, args)
        assert not result.isError
        return json.loads(result.content[0].text)  # type: ignore[union-attr,no-any-return]


async def test_work_log_append_returns_ok(tmp_path: Path) -> None:
    payload = await _call(tmp_path, "work_log_append", dict(_VALID_ARGS))
    assert payload["status"] == "ok"
    assert "persisted_to" in payload
    assert ISO_TIMESTAMP.match(str(payload["timestamp"]))


async def test_work_log_append_persists_to_filesystem(tmp_path: Path) -> None:
    await _call(tmp_path, "work_log_append", dict(_VALID_ARGS))
    log_file = tmp_path / "work-log.jsonl"
    assert log_file.exists()
    record = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert record["skill"] == "fix"
    assert record["project"] == "algobooth"


async def test_work_log_append_with_extras(tmp_path: Path) -> None:
    args = {
        **_VALID_ARGS,
        "extra": {"bug_summary": "DC output", "root_cause": "pw=0"},
    }
    await _call(tmp_path, "work_log_append", args)
    record = json.loads((tmp_path / "work-log.jsonl").read_text(encoding="utf-8").strip())
    assert record["bug_summary"] == "DC output"
    assert record["root_cause"] == "pw=0"


async def test_work_log_append_with_interview_fields(tmp_path: Path) -> None:
    args = {
        **_VALID_ARGS,
        "technologies": ["Rust", "TypeScript"],
        "patterns": ["boundary-validation"],
        "technical_context": "Voice synthesis pipeline fix at serialization boundary.",
    }
    await _call(tmp_path, "work_log_append", args)
    record = json.loads((tmp_path / "work-log.jsonl").read_text(encoding="utf-8").strip())
    assert record["technologies"] == ["Rust", "TypeScript"]
    assert record["patterns"] == ["boundary-validation"]
    assert "serialization boundary" in record["technical_context"]


async def test_work_log_append_multiple(tmp_path: Path) -> None:
    for i in range(3):
        args = {**_VALID_ARGS, "title": f"Entry {i}"}
        await _call(tmp_path, "work_log_append", args)
    lines = (tmp_path / "work-log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


async def test_work_log_append_with_optional_common_fields(tmp_path: Path) -> None:
    args = {
        **_VALID_ARGS,
        "branch": "main",
        "commit": "abc1234",
        "phases_md": "docs/PHASES.md",
        "spec_md": "docs/SPEC.md",
    }
    payload = await _call(tmp_path, "work_log_append", args)
    assert payload["status"] == "ok"
    record = json.loads((tmp_path / "work-log.jsonl").read_text(encoding="utf-8").strip())
    assert record["branch"] == "main"
    assert record["commit"] == "abc1234"


# ---------------------------------------------------------------------------
# feature field support
# ---------------------------------------------------------------------------


async def test_work_log_append_with_feature(tmp_path: Path) -> None:
    args = {**_VALID_ARGS, "feature": "cognito-pay"}
    await _call(tmp_path, "work_log_append", args)
    record = json.loads((tmp_path / "work-log.jsonl").read_text(encoding="utf-8").strip())
    assert record["feature"] == "cognito-pay"


async def test_work_log_append_without_feature(tmp_path: Path) -> None:
    await _call(tmp_path, "work_log_append", dict(_VALID_ARGS))
    record = json.loads((tmp_path / "work-log.jsonl").read_text(encoding="utf-8").strip())
    assert record["feature"] is None
