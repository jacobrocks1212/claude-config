"""Tests for HeadlessJudge and BatchHeadlessJudge."""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

from servers.work_logging_mcp.headless_judge import BatchHeadlessJudge, HeadlessJudge

_FEATURE: dict[str, Any] = {
    "slug": "auth-rate-limiter",
    "summary": "Implemented rate limiting",
}

_TOPIC: dict[str, Any] = {
    "slug": "rate-limiting",
    "domain": "system-design",
    "description": "Token bucket rate limiting",
}

_CANDIDATES: list[dict[str, Any]] = [
    {
        "slug": "rate-limiting",
        "domain": "system-design",
        "description": "Token bucket rate limiting",
    },
    {
        "slug": "caching",
        "domain": "system-design",
        "description": "Cache invalidation strategies",
    },
    {
        "slug": "observer-pattern",
        "domain": "ood",
        "description": "Publish-subscribe patterns",
    },
]


def _make_mock_result(result_payload: str, returncode: int = 0) -> MagicMock:
    outer = {"type": "result", "subtype": "success", "result": result_payload}
    mock = MagicMock(spec=subprocess.CompletedProcess)
    mock.returncode = returncode
    mock.stdout = json.dumps(outer).encode()
    return mock


def test_headless_judge_parses_valid_json() -> None:
    mock_result = _make_mock_result('{"score": 2}')

    with patch("servers.work_logging_mcp.headless_judge.subprocess.run", return_value=mock_result):
        judge = HeadlessJudge()
        score = judge(_FEATURE, _TOPIC)

    assert score == 2


def test_headless_judge_handles_malformed_output() -> None:
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = b"this is not json at all"

    with patch("servers.work_logging_mcp.headless_judge.subprocess.run", return_value=mock_result):
        judge = HeadlessJudge()
        score = judge(_FEATURE, _TOPIC)

    assert score == 0


def test_headless_judge_handles_subprocess_failure() -> None:
    with patch(
        "servers.work_logging_mcp.headless_judge.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "claude"),
    ):
        judge = HeadlessJudge()
        score = judge(_FEATURE, _TOPIC)

    assert score == 0


def test_batch_judge_constructs_prompt_correctly() -> None:
    mock_result = _make_mock_result('{"rate-limiting": 2, "caching": 1, "observer-pattern": 0}')

    with patch(
        "servers.work_logging_mcp.headless_judge.subprocess.run", return_value=mock_result
    ) as mock_run:
        judge = BatchHeadlessJudge()
        judge.evaluate(_FEATURE, _CANDIDATES)

    _, kwargs = mock_run.call_args
    prompt = kwargs.get("input", b"").decode()

    assert "Implemented rate limiting" in prompt
    assert "rate-limiting" in prompt
    assert "Token bucket rate limiting" in prompt
    assert "caching" in prompt
    assert "observer-pattern" in prompt
    assert any(word in prompt.lower() for word in ("rubric", "score"))


def test_batch_judge_parses_multi_score_response() -> None:
    mock_result = _make_mock_result('{"rate-limiting": 2, "caching": 1, "observer-pattern": 0}')

    with patch("servers.work_logging_mcp.headless_judge.subprocess.run", return_value=mock_result):
        judge = BatchHeadlessJudge()
        scores = judge.evaluate(_FEATURE, _CANDIDATES)

    assert scores["rate-limiting"] == 2
    assert scores["caching"] == 1
    assert scores["observer-pattern"] == 0


def test_headless_judge_implements_protocol() -> None:
    import inspect

    judge = HeadlessJudge()

    assert callable(judge)
    sig = inspect.signature(judge.__call__)
    params = list(sig.parameters.keys())
    # expects (self is excluded by inspect on bound methods) feature and topic
    assert "feature" in params
    assert "topic" in params
