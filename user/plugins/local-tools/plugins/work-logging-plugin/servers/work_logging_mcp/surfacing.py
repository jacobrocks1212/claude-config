"""Surfacing evaluator for passive study notifications."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, TypedDict

from servers.work_logging_mcp.headless_judge import _CLAUDE_BIN, _extract_json, _parse_outer

_logger = logging.getLogger(__name__)

_SURFACING_PROMPT_TEMPLATE = """You are an expert software engineering interview coach.

A developer just completed this work:
- Title: {title}
- Summary: {summary}
- Project: {project}
- Technologies: {technologies}
- Patterns: {patterns}

Here are 154 interview preparation topics across 4 domains:
{compact_kb_index}

Does this work DIRECTLY demonstrate any of these topics? Only surface if the
work shows intentional, deep engagement with the topic's core principles —
not tangential usage of a related technology.

Respond with JSON only:
- If strong match: {{"surface": true, "slug": "<topic-slug>", "domain": "<domain>",
  "summary": "<1-2 sentences explaining how THIS work demonstrates the topic>"}}
- If no strong match: {{"surface": false}}"""


class SurfacingResult(TypedDict):
    surface: bool
    slug: str | None
    domain: str | None
    summary: str | None


class SurfacingEvaluator:
    """Evaluate whether a work log entry surfaces a KB topic for study."""

    def __init__(self, model: str = "haiku", timeout: int = 60) -> None:
        self._model = model
        self._timeout = timeout

    def evaluate(self, entry: dict[str, Any], kb_entries: list[dict[str, Any]]) -> SurfacingResult:
        """Evaluate whether an entry matches any KB topic.

        Never raises — returns surface=False on any failure.
        """
        _no_match: SurfacingResult = {
            "surface": False,
            "slug": None,
            "domain": None,
            "summary": None,
        }

        try:
            compact_kb_index = "\n".join(
                f"{e.get('slug', '')} ({e.get('domain', '')}): {e.get('description', '')}"
                for e in kb_entries
            )

            technologies = entry.get("technologies", [])
            patterns = entry.get("patterns", [])
            tech_str = (
                ", ".join(technologies) if isinstance(technologies, list) else str(technologies)
            )
            patterns_str = ", ".join(patterns) if isinstance(patterns, list) else str(patterns)

            prompt = _SURFACING_PROMPT_TEMPLATE.format(
                title=entry.get("title", ""),
                summary=entry.get("summary", ""),
                project=entry.get("project", ""),
                technologies=tech_str,
                patterns=patterns_str,
                compact_kb_index=compact_kb_index,
            )

            result = subprocess.run(
                [_CLAUDE_BIN, "-p", "-", "--model", self._model, "--output-format", "json"],
                capture_output=True,
                input=prompt.encode(),
                timeout=self._timeout,
            )
        except Exception as exc:
            _logger.warning("SurfacingEvaluator subprocess failed: %s", exc)
            return _no_match

        try:
            inner_str = _parse_outer(result.stdout)
            inner_str = _extract_json(inner_str)
            inner: dict[str, Any] = json.loads(inner_str)

            surface = inner.get("surface")
            if not isinstance(surface, bool):
                return _no_match

            if not surface:
                return _no_match

            slug = inner.get("slug")
            domain = inner.get("domain")
            summary = inner.get("summary")

            if not slug or not domain or not summary:
                return _no_match

            return {
                "surface": True,
                "slug": str(slug),
                "domain": str(domain),
                "summary": str(summary),
            }
        except Exception as exc:
            _logger.warning("SurfacingEvaluator failed to parse response: %s", exc)
            return _no_match


class SurfacingLogWriter:
    """Append-only diagnostic log for surfacing evaluations."""

    def __init__(self, base_path: Path) -> None:
        self._base = base_path
        self._log_file = self._base / "surfacing-log.jsonl"

    def append(self, entry: dict[str, Any]) -> None:
        """Stamp timestamp and append entry as a JSON line."""
        from datetime import UTC, datetime

        entry["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._base.mkdir(parents=True, exist_ok=True)
        with self._log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
