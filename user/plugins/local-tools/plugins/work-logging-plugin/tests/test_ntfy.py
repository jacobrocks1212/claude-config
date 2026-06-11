"""Tests for NtfyNotifier — TDD red phase (implementation does not exist yet)."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from servers.work_logging_mcp.ntfy import NtfyConfig, NtfyNotifier, load_ntfy_config

_CONFIG_WITH_TOKEN: NtfyConfig = {"topic_url": "https://ntfy.sh/test-topic", "token": "tk_abc123"}
_CONFIG_NO_TOKEN: NtfyConfig = {"topic_url": "https://ntfy.sh/test-topic", "token": None}

_TOPIC_NAME = "Rate Limiting"
_SLUG = "rate-limiting"
_DOMAIN = "system-design"
_SUMMARY = "Token bucket and leaky bucket algorithms for distributed rate limiting."


def test_notify_sends_correct_headers() -> None:
    notifier = NtfyNotifier(_CONFIG_WITH_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

        assert mock_urlopen.call_count == 1
        request = mock_urlopen.call_args[0][0]

        assert request.get_header("Title") == _TOPIC_NAME
        assert request.get_header("Tags") == _DOMAIN
        assert request.get_header("Actions") == f"copy, Study, study {_SLUG}"


def test_notify_sends_auth_header_when_token_present() -> None:
    notifier = NtfyNotifier(_CONFIG_WITH_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

        request = mock_urlopen.call_args[0][0]
        assert request.get_header("Authorization") == "Bearer tk_abc123"


def test_notify_omits_auth_header_when_token_none() -> None:
    notifier = NtfyNotifier(_CONFIG_NO_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

        request = mock_urlopen.call_args[0][0]
        assert request.get_header("Authorization") is None


def test_notify_sends_correct_body() -> None:
    notifier = NtfyNotifier(_CONFIG_WITH_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

        request = mock_urlopen.call_args[0][0]
        assert request.data == _SUMMARY.encode("utf-8")


def test_notify_returns_true_on_success() -> None:
    notifier = NtfyNotifier(_CONFIG_WITH_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        result = notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

    assert result is True


def test_notify_returns_false_on_http_error() -> None:
    notifier = NtfyNotifier(_CONFIG_WITH_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(None, 403, "Forbidden", {}, None)  # type: ignore[arg-type]
        result = notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

    assert result is False


def test_notify_returns_false_on_timeout() -> None:
    notifier = NtfyNotifier(_CONFIG_WITH_TOKEN)
    with patch("servers.work_logging_mcp.ntfy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = TimeoutError
        result = notifier.notify(_TOPIC_NAME, _SLUG, _DOMAIN, _SUMMARY)

    assert result is False


def test_load_ntfy_config_returns_config_when_present(tmp_path: Path) -> None:
    config_data: dict[str, Any] = {
        "ntfy": {"topic_url": "https://ntfy.sh/test", "token": "tk_abc"}
    }
    (tmp_path / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

    result = load_ntfy_config(tmp_path)

    assert result is not None
    assert result["topic_url"] == "https://ntfy.sh/test"
    assert result["token"] == "tk_abc"


def test_load_ntfy_config_returns_none_when_absent(tmp_path: Path) -> None:
    config_data: dict[str, Any] = {"relevance_threshold": 0.7}
    (tmp_path / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

    result = load_ntfy_config(tmp_path)

    assert result is None
