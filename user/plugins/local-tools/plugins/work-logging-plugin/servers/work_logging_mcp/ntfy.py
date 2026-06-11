"""ntfy.sh notification client for interview-prep surfacing."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

_logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path.home() / ".interview-prep"


class NtfyConfig(TypedDict):
    topic_url: str
    token: str | None


class NtfyNotifier:
    def __init__(self, config: NtfyConfig) -> None:
        self._config = config

    def notify(self, topic_name: str, slug: str, domain: str, summary: str) -> bool:
        headers: dict[str, str] = {
            "Title": topic_name,
            "Tags": domain,
            "Actions": f"copy, Study, study {slug}",
            "Content-type": "text/plain",
        }
        token = self._config["token"]
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = urllib.request.Request(
            self._config["topic_url"],
            data=summary.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=10)
            return True
        except Exception as exc:
            _logger.warning("ntfy notification failed: %s", exc)
            return False


def load_ntfy_config(base_path: Path = _DEFAULT_BASE) -> NtfyConfig | None:
    config_file = base_path / "config.json"
    if not config_file.exists():
        return None
    data: Any = json.loads(config_file.read_text(encoding="utf-8"))
    ntfy = data.get("ntfy")
    if not ntfy or not ntfy.get("topic_url"):
        return None
    return NtfyConfig(topic_url=ntfy["topic_url"], token=ntfy.get("token"))
