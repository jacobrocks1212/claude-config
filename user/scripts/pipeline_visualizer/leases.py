"""leases — parse leases.json and compute per-entry heartbeat freshness.

Reuses lazy_coord.py's freshness arithmetic: a lease is fresh iff
    heartbeat_epoch + ttl_seconds >= now
(exactly-at-expiry counts as fresh; one second past is stale — matching
lazy_coord's `>=` boundary in acquire_lease/reclaim_expired).

The ISO-8601 'Z' parse is sourced from lazy_coord._parse_iso when that module
imports cleanly; otherwise we replicate the EXACT parse so the visualizer agrees
with the state machine byte-for-byte even when lazy_coord cannot be imported
(e.g. its transitive imports are unavailable). The replicated form is identical
to lazy_coord._parse_iso:

    datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _replicated_parse_iso(ts: str) -> float:
    """Replica of lazy_coord._parse_iso — kept in lockstep (see module docstring)."""
    return (
        datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


try:  # Prefer the canonical helper so any future change there propagates here.
    import lazy_coord as _lazy_coord  # type: ignore

    _parse_iso = _lazy_coord._parse_iso  # noqa: N816 (mirror the source name)
except Exception:  # pragma: no cover - fallback path
    _parse_iso = _replicated_parse_iso


def lease_view(wi_id: str, entry: dict, now: float) -> dict:
    """Compute the display view of one lease entry.

    Args:
        wi_id: the work-item id key for this lease.
        entry: the leases.json entry
            {worker_pid, worktree_slot, term_token, heartbeat_timestamp, ttl_seconds}.
        now: current epoch seconds (injected for determinism).

    Returns:
        {wi_id, worker_pid, worktree_slot, term_token, heartbeat_fresh, age_seconds}.
        `heartbeat_fresh` is True iff heartbeat_epoch + ttl_seconds >= now.
    """
    heartbeat_epoch = _parse_iso(entry["heartbeat_timestamp"])
    ttl = entry["ttl_seconds"]
    age_seconds = now - heartbeat_epoch
    fresh = heartbeat_epoch + ttl >= now
    return {
        "wi_id": wi_id,
        "worker_pid": entry.get("worker_pid"),
        "worktree_slot": entry.get("worktree_slot"),
        "term_token": entry.get("term_token"),
        "heartbeat_fresh": fresh,
        "age_seconds": age_seconds,
    }


def read_lease_views(path, now: Optional[float] = None) -> list:
    """Read leases.json and return a list of lease_view dicts.

    Missing file → empty list (not an error). Each entry keyed by wi_id.
    """
    import time as _time

    p = Path(path)
    if not p.exists():
        return []
    if now is None:
        now = _time.time()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [lease_view(wi_id, entry, now) for wi_id, entry in data.items()]
