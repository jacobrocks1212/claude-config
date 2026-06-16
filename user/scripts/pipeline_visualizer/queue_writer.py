"""queue_writer — the single guarded write path for queue.json reordering.

The visualizer is otherwise a read renderer; this module is the ONE place that
mutates `queue.json`. It honors the "one writer per file" rule and the SPEC's
reorder-safety contract (Decisions 6 + 11):

  - Permutation-validated: the posted order must be a true permutation of the
    existing IDs (no add / drop / dupe) — otherwise nothing is written.
  - Atomic: write to a temp file in the same dir, then `os.replace`, matching
    `lazy-state.py`'s `_atomic_write` convention (indent=2 + a single trailing
    newline) so `/lazy` reads the result cleanly.
  - AV-lock resilient: `os.replace` is wrapped in a 3× / 50ms retry catching
    `PermissionError` for Windows Defender file locks ([WinError 5]/[WinError 32]);
    exhausting the retries raises `QueueWriteError` (the server maps it to 503).

Refusal-while-running (the run-marker gate) lives in the server, NOT here — this
module is the mechanical write and is unaware of run state.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Sequence

# Windows Defender / AV file-lock errnos seen on os.replace.
_AV_LOCK_WINERRORS = {5, 32}
_RETRY_ATTEMPTS = 3
_RETRY_SLEEP_SECONDS = 0.05


class PermutationError(ValueError):
    """The posted order is not a permutation of the existing queue IDs."""


class QueueWriteError(RuntimeError):
    """The atomic write could not complete (e.g. AV lock survived all retries)."""


def _read_queue_doc(path: Path) -> dict:
    """Read queue.json into a dict with a top-level ``queue`` list. A bare-list
    file is normalized to ``{"queue": [...]}`` so sibling keys round-trip."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {"queue": raw}
    if isinstance(raw, dict):
        raw.setdefault("queue", [])
        return raw
    raise QueueWriteError(f"queue.json at {path} is neither a list nor an object")


def validate_permutation(existing_ids: Sequence[str], new_order: Sequence[str]) -> None:
    """Raise PermutationError unless new_order is a true permutation of existing.

    Catches add (extra id), drop (missing id), and dupe (same id twice).
    """
    existing = list(existing_ids)
    posted = list(new_order)
    if len(posted) != len(set(posted)):
        raise PermutationError("posted order contains duplicate IDs")
    if sorted(posted) != sorted(existing):
        missing = set(existing) - set(posted)
        added = set(posted) - set(existing)
        raise PermutationError(
            "posted order is not a permutation of the queue "
            f"(missing={sorted(missing)}, added={sorted(added)})"
        )


def _atomic_write_text(path: Path, text: str, retry_sleep: float) -> None:
    """Write text to a temp file in the same dir, then os.replace into place,
    retrying os.replace on transient AV file locks."""
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        last_exc: Exception | None = None
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                os.replace(tmp_name, str(path))
                return
            except PermissionError as exc:
                winerr = getattr(exc, "winerror", None)
                if winerr is not None and winerr not in _AV_LOCK_WINERRORS:
                    raise
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(retry_sleep)
        raise QueueWriteError(
            f"os.replace into {path} failed after {_RETRY_ATTEMPTS} attempts "
            f"(AV file lock?): {last_exc}"
        )
    finally:
        # If the temp file still exists (replace never succeeded), clean it up.
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except OSError:
            pass


def reorder_queue(
    path,
    new_order: Sequence[str],
    *,
    retry_sleep: float = _RETRY_SLEEP_SECONDS,
) -> dict:
    """Reorder queue.json's array to ``new_order`` and write atomically.

    Args:
        path: path to queue.json.
        new_order: the desired ID order (must be a permutation of existing IDs).
        retry_sleep: backoff between os.replace retries (0 in tests).

    Returns the written document dict.

    Raises:
        PermutationError: new_order is not a permutation of existing IDs (no write).
        QueueWriteError: the atomic write could not complete.
    """
    path = Path(path)
    doc = _read_queue_doc(path)
    queue = doc.get("queue", [])
    existing_ids = [e.get("id") for e in queue]

    validate_permutation(existing_ids, new_order)

    by_id = {e.get("id"): e for e in queue}
    doc["queue"] = [by_id[i] for i in new_order]

    text = json.dumps(doc, indent=2) + "\n"
    _atomic_write_text(path, text, retry_sleep)
    return doc
