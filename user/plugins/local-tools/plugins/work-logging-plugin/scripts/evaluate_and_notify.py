"""Background evaluation script for surfacing notifications."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Add parent to sys.path so we can import from servers/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servers.work_logging_mcp.knowledge_bank import KnowledgeBank  # noqa: E402
from servers.work_logging_mcp.ntfy import NtfyNotifier, load_ntfy_config  # noqa: E402
from servers.work_logging_mcp.surfacing import SurfacingEvaluator, SurfacingLogWriter  # noqa: E402

_logger = logging.getLogger(__name__)

_KB_PATH = Path.home() / ".interview-prep" / "knowledge-bank"
_BASE_PATH = Path.home() / ".interview-prep"


def main(path: str) -> None:
    """Evaluate a work log entry and optionally send an ntfy notification.

    Args:
        path: Path to temp JSON file containing the work log entry's tool_input.
    """
    temp_file = Path(path)

    try:
        if not temp_file.exists():
            _logger.warning("Temp file not found: %s", path)
            return

        entry: dict[str, Any] = json.loads(temp_file.read_text(encoding="utf-8"))

        kb = KnowledgeBank(_KB_PATH)
        kb_entries: list[dict[str, Any]] = [e.model_dump() for e in kb.entries]

        evaluator = SurfacingEvaluator()
        result = evaluator.evaluate(entry, kb_entries)

        notified = False
        if result["surface"]:
            slug = result["slug"]
            domain = result["domain"]
            summary = result["summary"]

            topic_name = slug or ""
            if slug and domain:
                kb_entry = kb.get(slug, domain)
                if kb_entry:
                    topic_name = kb_entry.name

            ntfy_config = load_ntfy_config(_BASE_PATH)
            if ntfy_config and slug and domain and summary:
                notifier = NtfyNotifier(ntfy_config)
                notifier.notify(topic_name, slug, domain, summary)
                notified = True

        log_writer = SurfacingLogWriter(_BASE_PATH)
        log_writer.append(
            {
                "work_title": entry.get("title", ""),
                "work_project": entry.get("project", ""),
                "surfaced": result["surface"],
                "topic_slug": result.get("slug"),
                "topic_domain": result.get("domain"),
                "summary": result.get("summary"),
                "notified": notified,
            }
        )

    except Exception as exc:
        _logger.error("evaluate_and_notify failed: %s", exc)
        _log_error(exc)

    finally:
        temp_file.unlink(missing_ok=True)


def _log_error(exc: Exception) -> None:
    """Append error details to surfacing-errors.log."""
    import traceback
    from datetime import UTC, datetime

    error_log = _BASE_PATH / "surfacing-errors.log"
    try:
        error_log.parent.mkdir(parents=True, exist_ok=True)
        with error_log.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(UTC).isoformat()} ERROR: {exc}\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: evaluate_and_notify.py <temp-file-path>")
        sys.exit(1)
    main(sys.argv[1])
