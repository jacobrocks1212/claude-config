"""Integration tests for get_study_context MCP tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from servers.work_logging_mcp.server import create_server

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def study_env(tmp_path: Path) -> object:
    """Set up KB + features + work log with one correlated feature."""
    kb_dir = tmp_path / "kb" / "system-design"
    kb_dir.mkdir(parents=True)
    (kb_dir / "rate-limiting.yaml").write_text(
        """
slug: rate-limiting
name: Rate Limiting
domain: system-design
tags: [api, distributed-systems]
description: Token bucket and leaky bucket algorithms
interview_questions:
  - How would you implement rate limiting?
talking_points:
  - Token bucket allows bursts
related_topics:
  - load-balancing
difficulty: intermediate
""".strip(),
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    feature = {
        "id": "feat-1",
        "slug": "auth-rate-limiter",
        "project": "cognito-forms",
        "title": "Auth Rate Limiter",
        "summary": "Token bucket for auth API",
        "work_log_refs": ["2026-04-01T10:00:00Z"],
        "topic_correlations": [{"slug": "rate-limiting", "domain": "system-design", "score": 2}],
        "created": "2026-04-01T00:00:00Z",
        "updated": "2026-04-01T00:00:00Z",
    }
    (data_dir / "features.jsonl").write_text(json.dumps(feature) + "\n", encoding="utf-8")

    log_entry = {
        "skill": "fix",
        "project": "cognito-forms",
        "title": "Fix auth timeout",
        "summary": "Fixed token expiry",
        "files_modified": ["src/auth.cs"],
        "timestamp": "2026-04-01T10:00:00Z",
    }
    (data_dir / "work-log.jsonl").write_text(json.dumps(log_entry) + "\n", encoding="utf-8")

    return create_server(kb_path=tmp_path / "kb", data_path=data_dir)


async def _call_tool(server: object, tool: str, args: dict[str, object]) -> dict[str, object]:
    from mcp.server.fastmcp import FastMCP

    assert isinstance(server, FastMCP)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool(tool, args)
        assert not result.isError
        return json.loads(result.content[0].text)  # type: ignore[union-attr,no-any-return]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_study_context_returns_topic(study_env: object) -> None:
    payload = await _call_tool(
        study_env,
        "get_study_context",
        {"topic_slug": "rate-limiting", "topic_domain": "system-design"},
    )
    assert "topic" in payload
    assert payload["topic"]["slug"] == "rate-limiting"
    assert payload["topic"]["domain"] == "system-design"


async def test_study_context_returns_correlated_features(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb" / "system-design"
    kb_dir.mkdir(parents=True)
    (kb_dir / "rate-limiting.yaml").write_text(
        """
slug: rate-limiting
name: Rate Limiting
domain: system-design
tags: [api]
description: Token bucket algorithms
interview_questions:
  - How would you implement rate limiting?
talking_points:
  - Token bucket allows bursts
related_topics: []
difficulty: intermediate
""".strip(),
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Two features: only one correlated to rate-limiting
    feat_correlated = {
        "id": "feat-1",
        "slug": "auth-rate-limiter",
        "project": "cognito-forms",
        "title": "Auth Rate Limiter",
        "summary": "Token bucket for auth API",
        "work_log_refs": [],
        "topic_correlations": [{"slug": "rate-limiting", "domain": "system-design", "score": 2}],
        "created": "2026-04-01T00:00:00Z",
        "updated": "2026-04-01T00:00:00Z",
    }
    feat_unrelated = {
        "id": "feat-2",
        "slug": "caching-layer",
        "project": "cognito-forms",
        "title": "Caching Layer",
        "summary": "Redis caching implementation",
        "work_log_refs": [],
        "topic_correlations": [{"slug": "caching", "domain": "system-design", "score": 2}],
        "created": "2026-04-02T00:00:00Z",
        "updated": "2026-04-02T00:00:00Z",
    }
    features_text = json.dumps(feat_correlated) + "\n" + json.dumps(feat_unrelated) + "\n"
    (data_dir / "features.jsonl").write_text(features_text, encoding="utf-8")
    (data_dir / "work-log.jsonl").write_text("", encoding="utf-8")

    server = create_server(kb_path=tmp_path / "kb", data_path=data_dir)
    payload = await _call_tool(
        server,
        "get_study_context",
        {"topic_slug": "rate-limiting", "topic_domain": "system-design"},
    )

    assert len(payload["correlated_features"]) == 1
    assert payload["correlated_features"][0]["slug"] == "auth-rate-limiter"


async def test_study_context_returns_work_log_refs(study_env: object) -> None:
    payload = await _call_tool(
        study_env,
        "get_study_context",
        {"topic_slug": "rate-limiting", "topic_domain": "system-design"},
    )
    assert len(payload["work_log_entries"]) == 1
    assert payload["work_log_entries"][0]["timestamp"] == "2026-04-01T10:00:00Z"


async def test_study_context_topic_not_found(study_env: object) -> None:
    payload = await _call_tool(
        study_env,
        "get_study_context",
        {"topic_slug": "nonexistent-topic", "topic_domain": "system-design"},
    )
    assert "error" in payload


async def test_study_context_no_correlations(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb" / "system-design"
    kb_dir.mkdir(parents=True)
    (kb_dir / "rate-limiting.yaml").write_text(
        """
slug: rate-limiting
name: Rate Limiting
domain: system-design
tags: [api]
description: Token bucket algorithms
interview_questions:
  - How would you implement rate limiting?
talking_points:
  - Token bucket allows bursts
related_topics: []
difficulty: intermediate
""".strip(),
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Feature exists but correlates to a different topic
    feat = {
        "id": "feat-1",
        "slug": "caching-layer",
        "project": "cognito-forms",
        "title": "Caching Layer",
        "summary": "Redis caching",
        "work_log_refs": ["2026-04-01T10:00:00Z"],
        "topic_correlations": [{"slug": "caching", "domain": "system-design", "score": 2}],
        "created": "2026-04-01T00:00:00Z",
        "updated": "2026-04-01T00:00:00Z",
    }
    (data_dir / "features.jsonl").write_text(json.dumps(feat) + "\n", encoding="utf-8")
    (data_dir / "work-log.jsonl").write_text("", encoding="utf-8")

    server = create_server(kb_path=tmp_path / "kb", data_path=data_dir)
    payload = await _call_tool(
        server,
        "get_study_context",
        {"topic_slug": "rate-limiting", "topic_domain": "system-design"},
    )

    assert payload["correlated_features"] == []
    assert payload["work_log_entries"] == []


async def test_study_context_summary_counts(study_env: object) -> None:
    payload = await _call_tool(
        study_env,
        "get_study_context",
        {"topic_slug": "rate-limiting", "topic_domain": "system-design"},
    )
    summary = payload["summary"]
    assert summary["features_count"] == len(payload["correlated_features"])
    assert summary["work_log_count"] == len(payload["work_log_entries"])
