#!/usr/bin/env python3
"""
incident-scan.py — deterministic incident collector → bug-stub enqueuer
(incident-auto-capture; SPEC: docs/features/incident-auto-capture/SPEC.md).

READ-ONLY over its inputs (the toolify-miner.py discipline): scans the
per-repo keyed state dir (deny ledger, hook-events.jsonl, legacy
hook-error.json) plus docs/bugs/** (dedup surface), clusters signals by
(repo, signal_class, signature) [D4], applies per-signal recurrence bars
[D3 — the config block below], dedups against every open and archived
incident_key [D5], and — for clusters that clear the bar — enqueues a
stub-status bug through the sanctioned `lazy-state.py --enqueue-adhoc
--type bug` path, seeding an INCIDENT.md evidence capsule beside
ADHOC_BRIEF.md [D7].

The ONLY mutations are (1) the enqueue subprocess (whose queue write is
bug-state.py's atomic write, not ours) and (2) the INCIDENT.md capsule
(lazy_core._atomic_write). `--dry-run` performs neither. The collector is
NOT on the state-machine compute path — nothing imports it.

Determinism: thresholds are config constants; clustering is pure string
composition; `--now` is injectable; the same inputs always derive the same
cluster keys and slugs (idempotent scans — an existing incident_key, open or
archived, short-circuits before any write; `enqueue_adhoc`'s duplicate-id
no-op is the second net).

Exit codes: 0 success (even when nothing clears the bar — empty state is
normal); 2 malformed input (bad --repo-root).

Usage:
    python3 incident-scan.py --repo-root <repo> [--dry-run] [--now <epoch>]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# D3 — signal inventory + per-signal recurrence bars (operator-approved
# 2026-07-04; numbers, not judgment — tune here, one-line diffs).
#
#   deny        — repeated guard-deny signature (deny ledger):    ≥3 in 24h
#   friction    — kind: process-friction (deny ledger):           ≥2, any window
#   hook-error  — hook fail-OPEN errors (events file, per hook):  ≥2 in 7d
#   hook-deny   — hook-level denies (events file, hook+signature):≥3 in 24h
# ---------------------------------------------------------------------------

SIGNAL_BARS: dict[str, dict] = {
    "deny":       {"min_occurrences": 3, "window_hours": 24},
    "friction":   {"min_occurrences": 2, "window_hours": None},
    "hook-error": {"min_occurrences": 2, "window_hours": 168},
    "hook-deny":  {"min_occurrences": 3, "window_hours": 24},
}

# ≤N new stubs per scan (highest recurrence first) so a pathological burst
# cannot flood the bug queue; the remainder is reported-only.
ENQUEUE_CAP: int = 2

# Max verbatim evidence lines embedded in an INCIDENT.md capsule (newest kept).
EXCERPT_CAP: int = 20

# ---------------------------------------------------------------------------
# Field-evidence blind window (live-settings-split-brain-disarms-enforcement-plane,
# Fix Scope 6 / Decision D3): on the DESKTOP-GHTC5K6 laptop the enforcement hooks
# (containment / sentinel-write / long-build / build-queue / push / kill guards) were
# UNREGISTERED in the live ~/.claude/settings.json from 2026-06-11T23:24 until the
# split-brain fix (2026-07-12), so hook-derived signals (deny-ledger, hook-events.jsonl)
# for that machine UNDERCOUNT across that range. This is an ANNOTATION ONLY (D3): the
# events were never generated, so backfill is impossible and silent-ignore would re-poison
# efficacy/KPI baselines. Consumers of read_hook_events()/read_deny_ledger() must read a
# ZERO/low count in this window as "partially blind", NOT as zero friction. Not consumed by
# any code path — a documented breadcrumb where a future incident-scan/efficacy read lands.
BLIND_WINDOW = {
    "machine": "DESKTOP-GHTC5K6",
    "start": "2026-06-11T23:24:00Z",
    "end": "2026-07-12T00:00:00Z",
    "reason": "live-settings-split-brain: enforcement hooks unregistered in live settings.json",
    "signals_affected": ["hook-events.jsonl", "lazy-deny-ledger.jsonl"],
    "treatment": "annotate-only (D3) — undercount, not zero friction; backfill impossible",
}

# ---------------------------------------------------------------------------
# lazy_core import (sibling module) — readers + atomic write + state-dir keying.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_core  # noqa: E402


# ---------------------------------------------------------------------------
# Readers (all read-only, corrupt-line-tolerant)
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, skipping blank/corrupt lines. Absent → []."""
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _norm_path(p: str) -> str:
    """Normalize a path string for attribution comparison."""
    try:
        return os.path.normcase(
            os.path.normpath(os.path.realpath(p))
        ).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return (p or "").replace("\\", "/")


def _event_dirs() -> list[Path]:
    """State dirs that may hold hook-events.jsonl: the (keyed) state dir plus
    the un-keyed base dir (the bash hooks' lazy_core-unavailable fallback).
    Deduplicated so an override dir (LAZY_STATE_DIR) is read exactly once."""
    dirs: list[Path] = []
    keyed = lazy_core.claude_state_dir(create=False)
    dirs.append(keyed)
    if not os.environ.get("LAZY_STATE_DIR"):
        base = Path.home() / ".claude" / "state"
        if _norm_path(str(base)) != _norm_path(str(keyed)):
            dirs.append(base)
    return dirs


def _attributed(entry_repo_root: str, repo_root: Path) -> bool:
    """True when an event's recorded repo_root attributes to *repo_root*
    (equal, or a path inside it)."""
    if not entry_repo_root:
        return False
    e = _norm_path(entry_repo_root)
    r = _norm_path(str(repo_root))
    return e == r or e.startswith(r + "/")


def read_hook_events(repo_root: Path) -> list[dict]:
    """hook-events.jsonl entries for *repo_root*: everything in the keyed
    state dir (it is per-repo by construction), plus base-dir entries whose
    recorded repo_root attributes to this repo. Unattributed base-dir entries
    are skipped (deterministic — no guessing). See BLIND_WINDOW: this
    machine's hook-events undercount for 2026-06-11→2026-07-12 (enforcement
    hooks were unregistered); a low count in that range is partially-blind,
    not zero friction."""
    dirs = _event_dirs()
    events: list[dict] = []
    for i, d in enumerate(dirs):
        for e in _read_jsonl(d / "hook-events.jsonl"):
            if i == 0 or _attributed(str(e.get("repo_root") or ""), repo_root):
                events.append(e)
    return events


def _parse_crumb_ts(at: str) -> float | None:
    try:
        return _dt.datetime.strptime(
            at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=_dt.timezone.utc).timestamp()
    except Exception:  # noqa: BLE001
        return None


def read_legacy_crumbs() -> list[dict]:
    """Legacy single-file hook-error.json crumbs ({hook, error, at}) from the
    keyed + base dirs. Each contributes at most one occurrence; the caller
    counts a crumb ONLY when the events file has no error entry for its hook
    (post-D2 the appender fires at the same sites, so the crumb is a
    duplicate of the newest error event)."""
    crumbs: list[dict] = []
    for d in _event_dirs():
        p = d / "hook-error.json"
        if not p.exists():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("hook"):
            crumbs.append(obj)
    return crumbs


# ---------------------------------------------------------------------------
# D4 — clustering
# ---------------------------------------------------------------------------

def _first_token(text: str) -> str:
    """First whitespace-delimited token of *text*, stripped of punctuation
    noise — the human-readable half of a deny signature."""
    tok = (text or "").split()[0] if (text or "").split() else ""
    return tok.strip(".,;:!?()[]{}'\"`—")


def _is_ledger_deny(entry: dict) -> bool:
    """A genuine guard DENY row: carries denied_sha12, is not an audit event
    (auto_readmit / dispatch-by-reference are allows) and not friction."""
    if entry.get("auto_readmit"):
        return False
    if "nonce" in entry or "resolved_sha12" in entry or "readmitted_sha12" in entry:
        return False
    if entry.get("kind") == "process-friction":
        return False
    return "denied_sha12" in entry


def collect_clusters(repo_root: Path, now: float) -> list[dict]:
    """Cluster every observable signal; apply the D3 in-window occurrence
    counts. Returns one dict per observed cluster (bar-cleared or not):
    {signal_class, signature, occurrences, in_window, first_ts, last_ts,
     lines (newest last), cleared}."""
    raw: dict[tuple[str, str], list[tuple[float, dict]]] = {}

    def _add(cls: str, sig: str, ts: float, entry: dict) -> None:
        raw.setdefault((cls, sig), []).append((ts, entry))

    # Deny ledger: guard denies + process-friction rows.
    for e in lazy_core.read_deny_ledger():
        ts = e.get("ts")
        if not isinstance(ts, (int, float)):
            continue
        if e.get("kind") == "process-friction":
            _add("friction", str(e.get("reason_head") or ""), float(ts), e)
        elif _is_ledger_deny(e):
            sig = f"{e.get('denied_sha12', '')}-{_first_token(str(e.get('reason_head') or ''))}"
            _add("deny", sig, float(ts), e)

    # Hook events: kind error (per hook) + kind deny (per hook+signature).
    events = read_hook_events(repo_root)
    hooks_with_error_events: set[str] = set()
    for e in events:
        ts = e.get("ts")
        if not isinstance(ts, (int, float)):
            continue
        hook = str(e.get("hook") or "")
        if e.get("kind") == "error":
            hooks_with_error_events.add(hook)
            _add("hook-error", hook, float(ts), e)
        elif e.get("kind") == "deny":
            _add("hook-deny", f"{hook}|{e.get('signature') or ''}", float(ts), e)

    # Legacy crumbs: one occurrence, ONLY when no error event exists for the
    # hook (otherwise it duplicates the newest error event).
    for c in read_legacy_crumbs():
        hook = str(c.get("hook") or "")
        if hook in hooks_with_error_events:
            continue
        ts = _parse_crumb_ts(str(c.get("at") or "")) or now
        _add("hook-error", hook, ts, c)
        hooks_with_error_events.add(hook)  # at most one crumb per hook

    clusters: list[dict] = []
    for (cls, sig), rows in sorted(raw.items()):
        bar = SIGNAL_BARS[cls]
        window = bar["window_hours"]
        rows.sort(key=lambda r: r[0])
        if window is None:
            in_rows = rows
        else:
            cutoff = now - window * 3600.0
            in_rows = [r for r in rows if r[0] >= cutoff]
        clusters.append({
            "signal_class": cls,
            "signature": sig,
            "occurrences": len(in_rows),
            "total_seen": len(rows),
            "first_ts": in_rows[0][0] if in_rows else None,
            "last_ts": in_rows[-1][0] if in_rows else None,
            "lines": [json.dumps(r[1]) for r in in_rows],
            "cleared": len(in_rows) >= bar["min_occurrences"],
        })
    return clusters


def _window_label(cls: str) -> str:
    w = SIGNAL_BARS[cls]["window_hours"]
    if w is None:
        return "all"
    if w % 24 == 0 and w > 24:
        return f"{w // 24}d"
    return f"{w}h"


def incident_key(repo_root: Path, cluster: dict) -> str:
    """D4 cluster key rendered for the dedup surface. The repo component is
    the readable basename (the SPEC's UX form) — a scan is scoped to ONE
    repo and dedup matches inside that repo's own docs/bugs/, so no
    cross-repo ambiguity is possible."""
    return f"{repo_root.name}|{cluster['signal_class']}|{cluster['signature']}"


def slug_for(key: str, cls: str) -> str:
    short = hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]
    return f"adhoc-incident-{cls}-{short}"


# ---------------------------------------------------------------------------
# D5 — dedup surface
# ---------------------------------------------------------------------------

def scan_incident_keys(repo_root: Path) -> dict[str, dict]:
    """Scan docs/bugs/*/INCIDENT.md and docs/bugs/_archive/*/INCIDENT.md for
    incident_key frontmatter. Returns {key: {"open": [slugs], "archived":
    [slugs]}} (slugs sorted for determinism)."""
    bugs = repo_root / "docs" / "bugs"
    found: dict[str, dict] = {}

    def _scan(base: Path, archived: bool) -> None:
        if not base.is_dir():
            return
        for child in sorted(base.iterdir()):
            # Skip files and _-prefixed dirs (_archive is scanned explicitly
            # by the second _scan call below).
            if not child.is_dir() or child.name.startswith("_"):
                continue
            cap = child / "INCIDENT.md"
            if not cap.is_file():
                continue
            try:
                text = cap.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                if line.startswith("incident_key:"):
                    key = line.split(":", 1)[1].strip()
                    if key:
                        bucket = found.setdefault(
                            key, {"open": [], "archived": []}
                        )
                        bucket["archived" if archived else "open"].append(
                            child.name
                        )
                    break

    _scan(bugs, archived=False)
    _scan(bugs / "_archive", archived=True)
    return found


def scan_archived_evidence_timestamps(repo_root: Path) -> dict[str, set[float]]:
    """Union of raw evidence-line ``ts`` values already captured by every
    ARCHIVED ``INCIDENT.md`` capsule, keyed by ``incident_key``
    (adhoc-incident-scan-rereports-archived-evidence).

    A recurrence stub's cluster (``collect_clusters``) re-sweeps the FULL
    signal history for a signature — it has no memory of what an earlier,
    now-archived incident already reported. When that earlier incident's
    disposition closed (e.g. Won't-fix, working-as-designed) WITHOUT
    changing the underlying deny/friction mechanism, its exact timestamps
    remain in the ledger forever and get re-swept + re-counted on every
    later scan under the SAME ``incident_key`` — inflating the recurrence's
    occurrence count and duplicating already-adjudicated evidence lines in
    the new capsule (live: ``docs/bugs/_archive/adhoc-incident-hook-deny-
    19343d-r2`` re-reported the 3 timestamps ``docs/bugs/_archive/adhoc-
    incident-hook-deny-19343d`` had already investigated and closed,
    alongside 4 genuinely-new ones).

    This reads every ``docs/bugs/_archive/*/INCIDENT.md``'s fenced evidence
    block, parses each line as the same raw JSON the ledger/events readers
    produced, and unions the ``"ts"`` field per ``incident_key`` — the exact
    identity a byte-for-byte re-report shares with its prior report. Callers
    exclude a cluster row whose ``ts`` is in this set for the row's own
    ``incident_key`` (``_exclude_archived_evidence``), so a recurrence
    reports ONLY occurrences an archived incident's own capsule never saw.

    Best-effort / non-destructive, mirroring ``scan_incident_keys``: a
    missing/malformed capsule or non-JSON evidence line is skipped, never
    raised. Returns ``{}`` when ``docs/bugs/_archive/`` is absent.
    """
    archive = repo_root / "docs" / "bugs" / "_archive"
    out: dict[str, set[float]] = {}
    if not archive.is_dir():
        return out
    for child in sorted(archive.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        cap = child / "INCIDENT.md"
        if not cap.is_file():
            continue
        try:
            text = cap.read_text(encoding="utf-8")
        except OSError:
            continue
        key: str | None = None
        for line in text.splitlines():
            if line.startswith("incident_key:"):
                key = line.split(":", 1)[1].strip()
                break
        if not key:
            continue
        bucket = out.setdefault(key, set())
        in_fence = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "```":
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            try:
                obj = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                continue
            ts = obj.get("ts") if isinstance(obj, dict) else None
            if isinstance(ts, (int, float)):
                bucket.add(float(ts))
    return out


def _exclude_archived_evidence(cluster: dict, covered: set[float]) -> dict:
    """Return *cluster* with any row whose ``ts`` is in *covered* removed,
    recomputing ``lines``/``occurrences``/``first_ts``/``last_ts``/``cleared``
    from the SURVIVING rows only (adhoc-incident-scan-rereports-archived-
    evidence). A malformed/non-JSON line is conservatively KEPT (never
    silently dropped just because it could not be parsed for a ts).

    Returns the SAME cluster object unchanged (by identity — no copy) when
    *covered* is empty or nothing was excluded, so the common (no prior
    archived incident) case does zero extra work.
    """
    if not covered:
        return cluster
    kept: list[str] = []
    kept_ts: list[float] = []
    excluded_any = False
    for line in cluster["lines"]:
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            kept.append(line)
            continue
        ts = obj.get("ts") if isinstance(obj, dict) else None
        if isinstance(ts, (int, float)) and float(ts) in covered:
            excluded_any = True
            continue
        kept.append(line)
        if isinstance(ts, (int, float)):
            kept_ts.append(float(ts))
    if not excluded_any:
        return cluster
    new_cluster = dict(cluster)
    new_cluster["lines"] = kept
    new_cluster["occurrences"] = len(kept)
    new_cluster["first_ts"] = min(kept_ts) if kept_ts else None
    new_cluster["last_ts"] = max(kept_ts) if kept_ts else None
    bar = SIGNAL_BARS[cluster["signal_class"]]
    new_cluster["cleared"] = len(kept) >= bar["min_occurrences"]
    return new_cluster


def _queued_ids(repo_root: Path) -> set[str]:
    qp = repo_root / "docs" / "bugs" / "queue.json"
    if not qp.exists():
        return set()
    try:
        data = json.loads(qp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        str(e.get("id")) for e in data.get("queue", [])
        if isinstance(e, dict) and e.get("id")
    }


# ---------------------------------------------------------------------------
# D7 — proposals, enqueue, capsule
# ---------------------------------------------------------------------------

def _iso(ts: float | None) -> str:
    if ts is None:
        return ""
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _title(cluster: dict) -> str:
    cls = cluster["signal_class"]
    n = cluster["occurrences"]
    w = _window_label(cls)
    sig = cluster["signature"]
    if cls == "deny":
        tok = sig.split("-", 1)[1] if "-" in sig else sig
        return f"Repeated deny: {tok or sig} ({n}x/{w})"
    if cls == "friction":
        return f"Process friction: {sig} ({n}x)"
    if cls == "hook-error":
        return f"Hook fail-open errors: {sig} ({n}x/{w})"
    hook, _, hsig = sig.partition("|")
    return f"Repeated hook deny: {hook} {hsig} ({n}x/{w})"


def _brief(cluster: dict, key: str, recurrence_of: str | None) -> str:
    parts = [
        f"Auto-captured by incident-scan: {cluster['occurrences']} occurrences "
        f"of signal class {cluster['signal_class']} with signature "
        f"{cluster['signature']} between {_iso(cluster['first_ts'])} and "
        f"{_iso(cluster['last_ts'])} (incident_key {key}).",
        "Raw evidence lines are in this dir's INCIDENT.md capsule; /spec-bug "
        "owns root-cause investigation.",
    ]
    if recurrence_of:
        parts.append(
            f"RECURRENCE after an archived fix ({recurrence_of}) — the prior "
            "investigation is in docs/bugs/_archive/ and this signature "
            "recurring means the fix did not hold."
        )
    # One paragraph, no newlines/quotes (shell-quoting-safe per the component).
    return " ".join(parts).replace('"', "'")


def _capsule_text(cluster: dict, key: str, recurrence_of: str | None) -> str:
    lines = cluster["lines"][-EXCERPT_CAP:]
    fm = [
        "---",
        "kind: incident-capture",
        # park-provisional-parks-claude-config-auto-generated-stubs: durable
        # provenance that this bug stub was machine-enqueued by the harness (NOT
        # operator-authored). spec-bug propagates these two fields onto its
        # pre-conclusion NEEDS_INPUT.md, where lazy_core.provisional_eligibility's
        # claude-config carve-out reads them to auto-accept under --park-provisional.
        "auto_generated: true",
        "auto_generated_origin: incident-capture",
        f"incident_key: {key}",
        f"signal_class: {cluster['signal_class']}",
        f"occurrences: {cluster['occurrences']}",
        f"window: {_window_label(cluster['signal_class'])}",
        f"first_ts: {_iso(cluster['first_ts'])}",
        f"last_ts: {_iso(cluster['last_ts'])}",
    ]
    if recurrence_of:
        fm.append(f"recurrence_of: {recurrence_of}")
    fm.append("---")
    body = [
        "",
        "# Incident Evidence",
        "",
        f"Raw matching ledger/event lines (verbatim, newest last; capped at "
        f"{EXCERPT_CAP}):",
        "",
        "```",
        *lines,
        "```",
        "",
        "Captured by `incident-scan.py` (incident-auto-capture). The collector "
        "proposes evidence; `/spec-bug` owns root cause. Severity is the "
        "enqueue default — the collector never sets it.",
        "",
    ]
    return "\n".join(fm + body)


def _enqueue(repo_root: Path, slug: str, name: str, brief: str) -> bool:
    """Shell the sanctioned enqueue path. Environment is inherited UNCHANGED —
    the C3 cycle-containment guard's verdict applies to the real caller (this
    script must never launder a subagent past it)."""
    cmd = [
        sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"),
        "--enqueue-adhoc", "--type", "bug",
        "--id", slug, "--name", name, "--brief", brief,
        "--repo-root", str(repo_root),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"incident-scan: enqueue failed for {slug}: {exc}", file=sys.stderr)
        return False
    if r.returncode != 0:
        head = (r.stderr or r.stdout or "").strip().splitlines()
        print(
            f"incident-scan: enqueue failed for {slug} "
            f"(exit {r.returncode}): {head[:3]}",
            file=sys.stderr,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic incident collector -> bug-stub enqueuer."
    )
    parser.add_argument("--repo-root", default=".",
                        help="Repo to scan (state dir keyed off it; dedup "
                             "surface is its docs/bugs/).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report proposals (would-enqueue) without "
                             "writing anything.")
    parser.add_argument("--now", type=float, default=None,
                        help=argparse.SUPPRESS)  # hermetic test seam
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"incident-scan: --repo-root not a directory: {repo_root}",
              file=sys.stderr)
        return 2
    lazy_core.set_active_repo_root(str(repo_root))
    now = args.now if args.now is not None else time.time()

    # efficacy-future-check-unenforced-orchestrator-prose (D1): drop the
    # run-scoped "efficacy flush ran this run" breadcrumb the --run-end gate
    # checks (incident-scan is one of the trio). A real (non-dry-run) invocation
    # satisfies the gate even on a clean no-op (no clusters cleared the bar).
    # --dry-run is byte-inert and must NOT satisfy the gate. Marker-gated +
    # fail-open inside the helper (no run marker → no-op).
    if not args.dry_run:
        lazy_core.drop_efficacy_breadcrumb()

    clusters = collect_clusters(repo_root, now)

    # adhoc-incident-scan-rereports-archived-evidence: exclude, PER
    # incident_key, any evidence row whose exact ts an archived incident's
    # own capsule already reported — BEFORE the bar filter, so a recurrence
    # whose only "occurrences" are re-reports of already-adjudicated
    # timestamps correctly drops below the bar instead of re-clearing it.
    archived_evidence = scan_archived_evidence_timestamps(repo_root)
    if archived_evidence:
        clusters = [
            _exclude_archived_evidence(
                c, archived_evidence.get(incident_key(repo_root, c), set())
            )
            for c in clusters
        ]

    cleared = [c for c in clusters if c["cleared"]]

    known_keys = scan_incident_keys(repo_root)
    queued = _queued_ids(repo_root)

    proposals: list[dict] = []
    deduped = 0
    for c in cleared:
        key = incident_key(repo_root, c)
        base_slug = slug_for(key, c["signal_class"])
        info = known_keys.get(key, {"open": [], "archived": []})
        if info["open"] or base_slug in queued:
            deduped += 1
            continue
        recurrence_of = None
        slug = base_slug
        if info["archived"]:
            # D5-A: post-archive recurrence → NEW stub, fresh slug, linked
            # back; the archive is never suppressed against or mutated.
            recurrence_of = sorted(info["archived"])[-1]
            slug = f"{base_slug}-r{len(info['archived']) + 1}"
            if slug in queued:
                deduped += 1
                continue
        proposals.append({
            "cluster": c, "key": key, "slug": slug,
            "recurrence_of": recurrence_of,
            "name": _title(c),
        })

    # Cap: highest recurrence first; deterministic tie-break on the key.
    proposals.sort(key=lambda p: (-p["cluster"]["occurrences"], p["key"]))
    to_enqueue = proposals[:ENQUEUE_CAP]
    over_cap = proposals[ENQUEUE_CAP:]

    enqueued = 0
    announce: list[str] = []
    if args.dry_run:
        for p in to_enqueue:
            announce.append(
                f"➕ would-enqueue ad-hoc bug **{p['name']}** (`{p['slug']}`)"
                + (f" recurrence_of={p['recurrence_of']}"
                   if p["recurrence_of"] else "")
                + f" incident_key={p['key']}"
            )
    else:
        for p in to_enqueue:
            brief = _brief(p["cluster"], p["key"], p["recurrence_of"])
            if not _enqueue(repo_root, p["slug"], p["name"], brief):
                continue
            stub_dir = repo_root / "docs" / "bugs" / p["slug"]
            capsule = stub_dir / "INCIDENT.md"
            if not capsule.exists():  # idempotent — never clobber
                stub_dir.mkdir(parents=True, exist_ok=True)
                lazy_core._atomic_write(
                    capsule,
                    _capsule_text(p["cluster"], p["key"], p["recurrence_of"]),
                )
            enqueued += 1
            announce.append(
                f"➕ Enqueued ad-hoc bug **{p['name']}** (`{p['slug']}`) at "
                f"the top of the bugs queue"
            )

    verb = "would-enqueue" if args.dry_run else "enqueued"
    print(
        f"incident-scan: {len(clusters)} clusters observed, "
        f"{len(cleared)} cleared the bar, {enqueued if not args.dry_run else len(to_enqueue)} {verb}, "
        f"{deduped} deduped"
    )
    for line in announce:
        print(line)
    for p in over_cap:
        print(
            f"⚠ over enqueue cap ({ENQUEUE_CAP}/scan) — reported-only: "
            f"**{p['name']}** (`{p['slug']}`)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
