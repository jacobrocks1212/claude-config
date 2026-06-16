"""probe — shell the existing state scripts and aggregate the read state.

State is NEVER re-inferred here. The probe shells lazy-state.py / bug-state.py
(the single source of truth), parses their JSON, attaches a display-only
`curated_stage`, and reads queue.json / leases.json / ROADMAP.md.

Returns one aggregate dict:
    {features: [...], bugs: [...], leases: [...], roadmap: {...}, server_time: "<ISO>"}

This is the contract the frontend renders against (locked in PHASES Phase 1).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .curated_stage import curated_stage
from .leases import read_lease_views

# The state scripts live alongside this package (user/scripts/).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_LAZY_STATE = _SCRIPTS_DIR / "lazy-state.py"
_BUG_STATE = _SCRIPTS_DIR / "bug-state.py"

# Subprocess timeout for a single state-script invocation (the git/file probe
# can be slow; keep generous but bounded so a hung script never wedges a poll).
_PROBE_TIMEOUT = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_item_state(raw: dict, pipeline: str) -> dict:
    """Attach `curated_stage` to an already-parsed state dict, preserving the
    script's own fields (feature_id/current_step/terminal_reason/…)."""
    item = dict(raw)
    item["curated_stage"] = curated_stage(
        raw.get("current_step"), raw.get("terminal_reason"), pipeline
    )
    item.setdefault("error", None)
    return item


def parse_state_output(stdout: str, item_id: Optional[str], pipeline: str) -> dict:
    """Parse one state-script stdout into a per-item dict.

    Malformed / empty output is flagged (an `error` field) rather than raising —
    a single broken item must not crash the whole probe.
    """
    try:
        raw = json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "feature_id": item_id,
            "current_step": None,
            "terminal_reason": None,
            "curated_stage": "Pending",
            "error": f"state-script output not parseable: {exc}",
        }
    if not isinstance(raw, dict):
        return {
            "feature_id": item_id,
            "current_step": None,
            "terminal_reason": None,
            "curated_stage": "Pending",
            "error": "state-script output was not a JSON object",
        }
    return parse_item_state(raw, pipeline)


def _run_state_script(script: Path, repo_root: Path, scope_flag: str, scope_id: str) -> str:
    """Run a state script scoped to one item; return its stdout (possibly empty
    on failure — the caller's parse step flags an unparseable result)."""
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root), scope_flag, scope_id],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
        )
        return proc.stdout
    except (subprocess.SubprocessError, OSError) as exc:
        return json.dumps({"feature_id": scope_id, "error": f"subprocess failed: {exc}"})


def read_queue(path) -> list:
    """Read a queue.json file; return its `queue` array (order preserved).
    Missing file → empty list (not an error)."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        return data.get("queue", [])
    if isinstance(data, list):
        return data
    return []


def read_leases(path, now: Optional[float] = None) -> list:
    """Read leases.json and return the lease views. Missing file → empty list."""
    return read_lease_views(path, now=now)


def read_roadmap(path) -> dict:
    """Read ROADMAP.md as raw text (display-only). Missing file → empty dict."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return {"text": p.read_text(encoding="utf-8")}
    except OSError:
        return {}


def probe_state(repo_root) -> dict:
    """Shell the state scripts across every queue item and aggregate.

    Returns {features, bugs, leases, roadmap, server_time}. State is read, never
    re-inferred — each item's stage comes from the script's own current_step.
    """
    repo_root = Path(repo_root)
    features_dir = repo_root / "docs" / "features"
    bugs_dir = repo_root / "docs" / "bugs"

    feature_queue = read_queue(features_dir / "queue.json")
    bug_queue = read_queue(bugs_dir / "queue.json")

    features = []
    for entry in feature_queue:
        fid = entry.get("id")
        if not fid:
            continue
        stdout = _run_state_script(_LAZY_STATE, repo_root, "--feature-id", fid)
        item = parse_state_output(stdout, fid, "feature")
        # Carry queue badge metadata onto the item for the frontend.
        item.setdefault("queue_meta", {
            "tier": entry.get("tier"),
            "adhoc": entry.get("adhoc", entry.get("ad_hoc")),
            "stub": entry.get("stub"),
        })
        features.append(item)

    bugs = []
    for entry in bug_queue:
        bid = entry.get("id")
        if not bid:
            continue
        stdout = _run_state_script(_BUG_STATE, repo_root, "--bug-id", bid)
        item = parse_state_output(stdout, bid, "bug")
        item.setdefault("queue_meta", {
            "tier": entry.get("tier"),
            "adhoc": entry.get("adhoc", entry.get("ad_hoc")),
            "severity": entry.get("severity"),
        })
        bugs.append(item)

    leases = read_leases(repo_root / "docs" / "work" / "leases.json")
    roadmap = read_roadmap(features_dir / "ROADMAP.md")

    return {
        "features": features,
        "bugs": bugs,
        "leases": leases,
        "roadmap": roadmap,
        "server_time": _now_iso(),
    }
