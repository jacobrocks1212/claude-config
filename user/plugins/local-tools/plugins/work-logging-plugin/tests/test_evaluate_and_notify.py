"""Tests for scripts/evaluate_and_notify.py — TDD red phase (implementation does not exist yet)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.evaluate_and_notify import main  # noqa: E402, I001


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_ENTRY: dict[str, Any] = {
    "title": "Test Work",
    "summary": "Test",
    "project": "test-proj",
}

_SURFACE_FALSE: dict[str, Any] = {
    "surface": False,
    "slug": None,
    "domain": None,
    "summary": None,
}

_SURFACE_TRUE: dict[str, Any] = {
    "surface": True,
    "slug": "rate-limiting",
    "domain": "system-design",
    "summary": "Your work demonstrates rate limiting implementation.",
}

_NTFY_CONFIG: dict[str, Any] = {"topic_url": "https://ntfy.sh/test", "token": None}


def _write_entry(tmp_path: Path, entry: dict[str, Any] = _BASE_ENTRY) -> Path:
    temp_file = tmp_path / "work_entry.json"
    temp_file.write_text(json.dumps(entry), encoding="utf-8")
    return temp_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("scripts.evaluate_and_notify.SurfacingEvaluator")
@patch("scripts.evaluate_and_notify.KnowledgeBank")
@patch("scripts.evaluate_and_notify.load_ntfy_config")
@patch("scripts.evaluate_and_notify.NtfyNotifier")
def test_main_calls_evaluator_with_entry(
    mock_notifier_cls: MagicMock,
    mock_load_ntfy: MagicMock,
    mock_kb_cls: MagicMock,
    mock_evaluator_cls: MagicMock,
    tmp_path: Path,
) -> None:
    """Evaluator is called and receives the entry from the temp JSON file."""
    temp_file = _write_entry(tmp_path)

    mock_kb_instance = MagicMock()
    mock_kb_instance.entries = [MagicMock()]
    mock_kb_cls.return_value = mock_kb_instance

    mock_evaluator_instance = MagicMock()
    mock_evaluator_instance.evaluate.return_value = _SURFACE_FALSE
    mock_evaluator_cls.return_value = mock_evaluator_instance

    mock_load_ntfy.return_value = None

    main(str(temp_file))

    mock_evaluator_instance.evaluate.assert_called_once()
    call_args = mock_evaluator_instance.evaluate.call_args
    entry_arg: dict[str, Any] = call_args[0][0]
    assert entry_arg["title"] == "Test Work"


@patch("scripts.evaluate_and_notify.SurfacingEvaluator")
@patch("scripts.evaluate_and_notify.KnowledgeBank")
@patch("scripts.evaluate_and_notify.load_ntfy_config")
@patch("scripts.evaluate_and_notify.NtfyNotifier")
def test_main_notifies_when_surface_true(
    mock_notifier_cls: MagicMock,
    mock_load_ntfy: MagicMock,
    mock_kb_cls: MagicMock,
    mock_evaluator_cls: MagicMock,
    tmp_path: Path,
) -> None:
    """NtfyNotifier.notify is called with KB entry name when surface=True."""
    temp_file = _write_entry(tmp_path)

    mock_kb_entry = MagicMock()
    mock_kb_entry.name = "Rate Limiting"

    mock_kb_instance = MagicMock()
    mock_kb_instance.entries = [mock_kb_entry]
    mock_kb_instance.get.return_value = mock_kb_entry
    mock_kb_cls.return_value = mock_kb_instance

    mock_evaluator_instance = MagicMock()
    mock_evaluator_instance.evaluate.return_value = _SURFACE_TRUE
    mock_evaluator_cls.return_value = mock_evaluator_instance

    mock_load_ntfy.return_value = _NTFY_CONFIG

    mock_notifier_instance = MagicMock()
    mock_notifier_cls.return_value = mock_notifier_instance

    main(str(temp_file))

    mock_notifier_instance.notify.assert_called_once()
    call_kwargs = mock_notifier_instance.notify.call_args
    # topic_name can be positional or keyword — check both
    positional = call_kwargs[0]
    keyword = call_kwargs[1]
    topic_name = positional[0] if positional else keyword.get("topic_name")
    assert topic_name == "Rate Limiting"


@patch("scripts.evaluate_and_notify.SurfacingEvaluator")
@patch("scripts.evaluate_and_notify.KnowledgeBank")
@patch("scripts.evaluate_and_notify.load_ntfy_config")
@patch("scripts.evaluate_and_notify.NtfyNotifier")
def test_main_skips_notify_when_ntfy_not_configured(
    mock_notifier_cls: MagicMock,
    mock_load_ntfy: MagicMock,
    mock_kb_cls: MagicMock,
    mock_evaluator_cls: MagicMock,
    tmp_path: Path,
) -> None:
    """NtfyNotifier is never instantiated when load_ntfy_config returns None."""
    temp_file = _write_entry(tmp_path)

    mock_kb_instance = MagicMock()
    mock_kb_instance.entries = [MagicMock()]
    mock_kb_cls.return_value = mock_kb_instance

    mock_evaluator_instance = MagicMock()
    mock_evaluator_instance.evaluate.return_value = _SURFACE_TRUE
    mock_evaluator_cls.return_value = mock_evaluator_instance

    mock_load_ntfy.return_value = None

    main(str(temp_file))

    mock_notifier_cls.assert_not_called()


@patch("scripts.evaluate_and_notify.SurfacingEvaluator")
@patch("scripts.evaluate_and_notify.KnowledgeBank")
@patch("scripts.evaluate_and_notify.load_ntfy_config")
@patch("scripts.evaluate_and_notify.NtfyNotifier")
def test_main_cleans_up_temp_file_on_success(
    mock_notifier_cls: MagicMock,
    mock_load_ntfy: MagicMock,
    mock_kb_cls: MagicMock,
    mock_evaluator_cls: MagicMock,
    tmp_path: Path,
) -> None:
    """Temp file is deleted after successful evaluation (finally block)."""
    temp_file = _write_entry(tmp_path)

    mock_kb_instance = MagicMock()
    mock_kb_instance.entries = [MagicMock()]
    mock_kb_cls.return_value = mock_kb_instance

    mock_evaluator_instance = MagicMock()
    mock_evaluator_instance.evaluate.return_value = _SURFACE_FALSE
    mock_evaluator_cls.return_value = mock_evaluator_instance

    mock_load_ntfy.return_value = None

    main(str(temp_file))

    assert temp_file.exists() is False


@patch("scripts.evaluate_and_notify.SurfacingEvaluator")
@patch("scripts.evaluate_and_notify.KnowledgeBank")
@patch("scripts.evaluate_and_notify.load_ntfy_config")
@patch("scripts.evaluate_and_notify.NtfyNotifier")
def test_main_cleans_up_temp_file_on_evaluator_error(
    mock_notifier_cls: MagicMock,
    mock_load_ntfy: MagicMock,
    mock_kb_cls: MagicMock,
    mock_evaluator_cls: MagicMock,
    tmp_path: Path,
) -> None:
    """Temp file is deleted even when the evaluator raises (finally block)."""
    temp_file = _write_entry(tmp_path)

    mock_kb_instance = MagicMock()
    mock_kb_instance.entries = [MagicMock()]
    mock_kb_cls.return_value = mock_kb_instance

    mock_evaluator_instance = MagicMock()
    mock_evaluator_instance.evaluate.side_effect = RuntimeError("boom")
    mock_evaluator_cls.return_value = mock_evaluator_instance

    mock_load_ntfy.return_value = None

    main(str(temp_file))

    assert temp_file.exists() is False


@patch("scripts.evaluate_and_notify.SurfacingEvaluator")
@patch("scripts.evaluate_and_notify.KnowledgeBank")
@patch("scripts.evaluate_and_notify.load_ntfy_config")
@patch("scripts.evaluate_and_notify.NtfyNotifier")
def test_main_exits_0_on_missing_temp_file(
    mock_notifier_cls: MagicMock,
    mock_load_ntfy: MagicMock,
    mock_kb_cls: MagicMock,
    mock_evaluator_cls: MagicMock,
) -> None:
    """main() returns normally (no unhandled exception) when the temp file is absent."""
    main("/nonexistent/path/foo.json")


def test_evaluate_and_notify_logs_surfaced_true(tmp_path: Path) -> None:
    """SurfacingLogWriter writes a line with surfaced=True when evaluator surfaces a match."""
    temp_file = _write_entry(tmp_path)
    with (
        patch("scripts.evaluate_and_notify._BASE_PATH", tmp_path),
        patch("scripts.evaluate_and_notify._KB_PATH", tmp_path),
        patch("scripts.evaluate_and_notify.SurfacingEvaluator") as mock_eval_cls,
        patch("scripts.evaluate_and_notify.KnowledgeBank") as mock_kb_cls,
        patch("scripts.evaluate_and_notify.load_ntfy_config") as mock_load_ntfy,
        patch("scripts.evaluate_and_notify.NtfyNotifier"),
    ):
        mock_kb_instance = MagicMock()
        mock_kb_instance.entries = [MagicMock()]
        mock_kb_cls.return_value = mock_kb_instance

        mock_eval_instance = MagicMock()
        mock_eval_instance.evaluate.return_value = _SURFACE_TRUE
        mock_eval_cls.return_value = mock_eval_instance

        mock_load_ntfy.return_value = None

        main(str(temp_file))

    log_file = tmp_path / "surfacing-log.jsonl"
    assert log_file.exists()
    log_line = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert log_line["surfaced"] is True


def test_evaluate_and_notify_logs_surfaced_false(tmp_path: Path) -> None:
    """SurfacingLogWriter writes a line with surfaced=False when evaluator finds no match."""
    temp_file = _write_entry(tmp_path)
    with (
        patch("scripts.evaluate_and_notify._BASE_PATH", tmp_path),
        patch("scripts.evaluate_and_notify._KB_PATH", tmp_path),
        patch("scripts.evaluate_and_notify.SurfacingEvaluator") as mock_eval_cls,
        patch("scripts.evaluate_and_notify.KnowledgeBank") as mock_kb_cls,
        patch("scripts.evaluate_and_notify.load_ntfy_config") as mock_load_ntfy,
        patch("scripts.evaluate_and_notify.NtfyNotifier"),
    ):
        mock_kb_instance = MagicMock()
        mock_kb_instance.entries = [MagicMock()]
        mock_kb_cls.return_value = mock_kb_instance

        mock_eval_instance = MagicMock()
        mock_eval_instance.evaluate.return_value = _SURFACE_FALSE
        mock_eval_cls.return_value = mock_eval_instance

        mock_load_ntfy.return_value = None

        main(str(temp_file))

    log_file = tmp_path / "surfacing-log.jsonl"
    assert log_file.exists()
    log_line = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert log_line["surfaced"] is False


def test_evaluate_and_notify_logs_error_on_exception(tmp_path: Path) -> None:
    """surfacing-errors.log is written with traceback when evaluator raises."""
    temp_file = _write_entry(tmp_path)
    with (
        patch("scripts.evaluate_and_notify._BASE_PATH", tmp_path),
        patch("scripts.evaluate_and_notify._KB_PATH", tmp_path),
        patch("scripts.evaluate_and_notify.SurfacingEvaluator") as mock_eval_cls,
        patch("scripts.evaluate_and_notify.KnowledgeBank") as mock_kb_cls,
        patch("scripts.evaluate_and_notify.load_ntfy_config"),
        patch("scripts.evaluate_and_notify.NtfyNotifier"),
    ):
        mock_kb_instance = MagicMock()
        mock_kb_instance.entries = [MagicMock()]
        mock_kb_cls.return_value = mock_kb_instance

        mock_eval_instance = MagicMock()
        mock_eval_instance.evaluate.side_effect = RuntimeError("test error")
        mock_eval_cls.return_value = mock_eval_instance

        main(str(temp_file))

    error_log = tmp_path / "surfacing-errors.log"
    assert error_log.exists()
    content = error_log.read_text(encoding="utf-8")
    assert "test error" in content
