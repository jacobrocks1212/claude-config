"""Headless Claude CLI judge for topic correlation scoring."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Any

_logger = logging.getLogger(__name__)

_CLAUDE_BIN = shutil.which("claude") or "claude"

_SINGLE_PROMPT_TEMPLATE = """You are an expert software engineering interview coach.

Feature summary:
{summary}

Topic:
- slug: {slug}
- description: {description}

Score how relevant this topic is to the feature using this rubric:
- 0: irrelevant (no meaningful connection)
- 1: tangential (loosely related but not a strong match)
- 2: strong match (directly demonstrates this topic)

Respond with JSON only: {{"score": <0|1|2>}}"""

_BATCH_PROMPT_TEMPLATE = """You are an expert software engineering interview coach.

Feature summary:
{summary}

Score each of the following topics for relevance to the feature using this rubric:
- 0: irrelevant (no meaningful connection)
- 1: tangential (loosely related but not a strong match)
- 2: strong match (directly demonstrates this topic)

Topics:
{candidates}

Respond with JSON only — a single object mapping each slug to its score.
Example: {{"slug-a": 2, "slug-b": 0}}"""


def _extract_json(text: str) -> str:
    """Extract JSON from text that may contain markdown fences and trailing prose."""
    # Try fenced code block first (captures content between ``` and ```)
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    # Fall back to first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0).strip()
    return text.strip()


def _parse_outer(stdout: bytes) -> str:
    """Parse the Claude CLI outer envelope and return the inner result string."""
    outer = json.loads(stdout.decode())
    return str(outer["result"])


class HeadlessJudge:
    """Invoke Claude CLI as a subprocess to score a single Feature×Topic pair."""

    def __init__(self, model: str = "haiku", timeout: int = 60) -> None:
        self._model = model
        self._timeout = timeout

    def __call__(self, feature: dict[str, Any], topic: dict[str, Any]) -> int:
        summary = feature.get("summary", "")
        slug = topic.get("slug", "")
        description = topic.get("description", "")

        prompt = _SINGLE_PROMPT_TEMPLATE.format(
            summary=summary,
            slug=slug,
            description=description,
        )

        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "-p", "-", "--model", self._model, "--output-format", "json"],
                capture_output=True,
                input=prompt.encode(),
                timeout=self._timeout,
            )
        except Exception as exc:
            _logger.warning("HeadlessJudge subprocess failed: %s", exc)
            return 0

        try:
            inner_str = _parse_outer(result.stdout)
            inner_str = _extract_json(inner_str)
            inner = json.loads(inner_str)
            return int(inner["score"])
        except Exception as exc:
            _logger.warning("HeadlessJudge failed to parse response: %s", exc)
            return 0


class BatchHeadlessJudge:
    """Invoke Claude CLI once to score a feature against multiple topic candidates."""

    def __init__(self, model: str = "haiku", timeout: int = 60) -> None:
        self._model = model
        self._timeout = timeout

    def evaluate(
        self,
        feature: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, int]:
        summary = feature.get("summary", "")

        candidate_lines = "\n".join(
            f"- slug: {c.get('slug', '')} | description: {c.get('description', '')}"
            for c in candidates
        )

        prompt = _BATCH_PROMPT_TEMPLATE.format(
            summary=summary,
            candidates=candidate_lines,
        )

        try:
            result = subprocess.run(
                [_CLAUDE_BIN, "-p", "-", "--model", self._model, "--output-format", "json"],
                capture_output=True,
                input=prompt.encode(),
                timeout=self._timeout,
            )
        except Exception as exc:
            _logger.warning("BatchHeadlessJudge subprocess failed: %s", exc)
            return {}

        try:
            inner_str = _parse_outer(result.stdout)
            inner_str = _extract_json(inner_str)
            raw: dict[str, Any] = json.loads(inner_str)
            return {k: int(v) for k, v in raw.items()}
        except Exception as exc:
            _logger.warning("BatchHeadlessJudge failed to parse response: %s", exc)
            return {}
