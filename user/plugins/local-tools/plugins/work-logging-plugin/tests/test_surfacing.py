"""Tests for SurfacingEvaluator."""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

from servers.work_logging_mcp.surfacing import SurfacingEvaluator, SurfacingResult

_ENTRY: dict[str, Any] = {
    "title": "Cognito Pay — Payment Processing Integration",
    "summary": "Implemented rate limiting for payment processing",
    "project": "cognito-forms",
    "technologies": ["C#", ".NET"],
    "patterns": ["rate-limiting"],
}

_KB_ENTRIES: list[dict[str, Any]] = [
    {
        "slug": "rate-limiting",
        "domain": "system-design",
        "name": "Rate Limiting",
        "description": "Token bucket and sliding window rate limiting",
    },
    {
        "slug": "caching",
        "domain": "system-design",
        "name": "Caching",
        "description": "Cache invalidation strategies",
    },
]


def _make_mock_result(result_payload: str, returncode: int = 0) -> MagicMock:
    outer = {"type": "result", "subtype": "success", "result": result_payload}
    mock = MagicMock(spec=subprocess.CompletedProcess)
    mock.returncode = returncode
    mock.stdout = json.dumps(outer).encode()
    return mock


def test_evaluate_surface_true_parses_correctly() -> None:
    payload = json.dumps(
        {
            "surface": True,
            "slug": "rate-limiting",
            "domain": "system-design",
            "summary": "Your work demonstrates rate limiting implementation.",
        }
    )
    mock_result = _make_mock_result(payload)

    with patch("servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result):
        evaluator = SurfacingEvaluator()
        result: SurfacingResult = evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    assert result["surface"] is True
    assert result["slug"] == "rate-limiting"
    assert result["domain"] == "system-design"
    assert result["summary"] == "Your work demonstrates rate limiting implementation."


def test_evaluate_surface_false_parses_correctly() -> None:
    payload = json.dumps({"surface": False})
    mock_result = _make_mock_result(payload)

    with patch("servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result):
        evaluator = SurfacingEvaluator()
        result: SurfacingResult = evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    assert result["surface"] is False
    assert result["slug"] is None


def test_evaluate_handles_malformed_json() -> None:
    mock_result = _make_mock_result("this is not valid json at all")

    with patch("servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result):
        evaluator = SurfacingEvaluator()
        result: SurfacingResult = evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    assert result["surface"] is False


def test_evaluate_handles_subprocess_failure() -> None:
    with patch(
        "servers.work_logging_mcp.surfacing.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "claude"),
    ):
        evaluator = SurfacingEvaluator()
        result: SurfacingResult = evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    assert result["surface"] is False


def test_evaluate_handles_missing_slug_on_surface_true() -> None:
    payload = json.dumps({"surface": True})
    mock_result = _make_mock_result(payload)

    with patch("servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result):
        evaluator = SurfacingEvaluator()
        result: SurfacingResult = evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    assert result["surface"] is False


def test_prompt_contains_entry_fields() -> None:
    payload = json.dumps({"surface": False})
    mock_result = _make_mock_result(payload)

    with patch(
        "servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result
    ) as mock_run:
        evaluator = SurfacingEvaluator()
        evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    _, kwargs = mock_run.call_args
    prompt = kwargs.get("input", b"").decode()

    assert _ENTRY["title"] in prompt
    assert _ENTRY["summary"] in prompt
    assert _ENTRY["project"] in prompt


def test_prompt_contains_kb_entries() -> None:
    payload = json.dumps({"surface": False})
    mock_result = _make_mock_result(payload)

    with patch(
        "servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result
    ) as mock_run:
        evaluator = SurfacingEvaluator()
        evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    _, kwargs = mock_run.call_args
    prompt = kwargs.get("input", b"").decode()

    slugs = [entry["slug"] for entry in _KB_ENTRIES]
    assert any(slug in prompt for slug in slugs)


def test_evaluate_handles_markdown_fenced_response() -> None:
    inner_json = json.dumps(
        {
            "surface": True,
            "slug": "rate-limiting",
            "domain": "system-design",
            "summary": "Your work demonstrates rate limiting implementation.",
        }
    )
    fenced_payload = f"```json\n{inner_json}\n```"
    mock_result = _make_mock_result(fenced_payload)

    with patch("servers.work_logging_mcp.surfacing.subprocess.run", return_value=mock_result):
        evaluator = SurfacingEvaluator()
        result: SurfacingResult = evaluator.evaluate(_ENTRY, _KB_ENTRIES)

    assert result["surface"] is True
    assert result["slug"] == "rate-limiting"
    assert result["domain"] == "system-design"
    assert result["summary"] == "Your work demonstrates rate limiting implementation."
