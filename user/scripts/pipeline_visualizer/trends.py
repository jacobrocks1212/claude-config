"""trends — pure-read aggregation over the harness telemetry ledger (D9-A).

harness-telemetry-ledger Phase 3. The state scripts record raw chokepoint
events into ``lazy-telemetry.jsonl`` (per-repo keyed state dir; cloud runs
additionally commit per-run segments under ``docs/telemetry/cloud/``). This
module derives the metrics READER-SIDE — cycles-per-completion, refusal
counts, halt dwell, run durations — as pure functions over the event stream
(plus the deny ledger). It NEVER writes anything and NEVER re-infers pipeline
state (``probe.py`` stays the state authority; this aggregates recorded facts).

Consumers:
  - ``server.py`` ``/api/trends`` (via :func:`trends_payload`, TtlCache-debounced)
  - the ``/lazy-batch-retro`` "Ledger deltas" step (D8):
        python -m pipeline_visualizer.trends --run-id <id> --repo-root <repo>
    which prints :func:`run_summary` JSON with per-figure ledger citations.

Stdlib-only. ``lazy_core`` supplies the ledger readers + per-repo state-dir
resolution; when it is unimportable the loaders honestly report no telemetry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Ensure the parent scripts/ dir is importable (lazy_core lives there) when the
# module runs as `python -m pipeline_visualizer.trends` from an arbitrary cwd —
# same bootstrapping as __main__.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# The pseudo-skills whose successful apply counts as a COMPLETION for the
# cycles-per-completion metric (the two pipelines' terminal pseudo-skills).
_COMPLETION_PSEUDOS = frozenset({"__mark_complete__", "__mark_fixed__"})

_NO_TELEMETRY_MESSAGE = "no telemetry recorded for this window"


# ---------------------------------------------------------------------------
# Loaders (the only I/O in this module — read-only)
# ---------------------------------------------------------------------------

def _bind_lazy_core(repo_root):
    """Import lazy_core bound to the visualized repo, or None if unavailable.

    Binding the active repo makes ``claude_state_dir()`` resolve THIS repo's
    keyed state subdir (mirrors ``server._run_marker_present``). When
    LAZY_STATE_DIR is set (tests / pipe-tests) the override wins inside
    lazy_core regardless of the binding.
    """
    try:
        import lazy_core
    except ImportError:
        return None
    try:
        if repo_root is not None:
            lazy_core.set_active_repo_root(str(repo_root))
    except Exception:  # noqa: BLE001 — binding failure degrades to cwd fallback
        pass
    return lazy_core


def load_events(repo_root) -> list[dict]:
    """Load all telemetry events for a repo, provenance-stamped, read-only.

    Sources, in order: the state-dir ledger (rotated segments oldest-first then
    the active file, via ``lazy_core.read_telemetry_events``) plus any committed
    cloud segments under ``<repo_root>/docs/telemetry/cloud/*.jsonl`` (D5-B),
    sorted by filename. Exact duplicate events (same run_id/ts/event/item_id/
    data — a cloud segment re-read beside a still-present state-dir line) are
    deduped. Missing sources → empty list, never an error.
    """
    lazy_core = _bind_lazy_core(repo_root)
    if lazy_core is None:
        return []
    events: list[dict] = []
    try:
        events.extend(lazy_core.read_telemetry_events(with_provenance=True))
    except Exception:  # noqa: BLE001 — a broken ledger reads as empty
        pass
    try:
        cloud_dir = Path(repo_root) / "docs" / "telemetry" / "cloud"
        if cloud_dir.is_dir():
            seg_paths = sorted(cloud_dir.glob("*.jsonl"))
            events.extend(
                lazy_core.read_telemetry_events(
                    paths=seg_paths, with_provenance=True
                )
            )
    except Exception:  # noqa: BLE001
        pass
    # Dedupe exact duplicates across sources (content identity, not provenance).
    seen: set = set()
    unique: list[dict] = []
    for e in events:
        key = (e.get("run_id"), e.get("ts"), e.get("event"), e.get("item_id"),
               json.dumps(e.get("data"), sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


def load_denies(repo_root) -> list[dict]:
    """Load the deny ledger for a repo (read-only; missing → empty list)."""
    lazy_core = _bind_lazy_core(repo_root)
    if lazy_core is None:
        return []
    try:
        return lazy_core.read_deny_ledger()
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Pure aggregation functions (no I/O; provenance keys are ignored)
# ---------------------------------------------------------------------------

def runs(events: list[dict]) -> list[dict]:
    """Group events by run_id in first-seen order.

    Returns one row per run:
        {run_id, pipeline, first_ts, last_ts, event_counts: {type: n}}
    """
    by_run: dict = {}
    order: list = []
    for e in events:
        rid = e.get("run_id")
        if rid is None:
            continue
        if rid not in by_run:
            by_run[rid] = {
                "run_id": rid,
                "pipeline": e.get("pipeline"),
                "first_ts": e.get("ts"),
                "last_ts": e.get("ts"),
                "event_counts": {},
            }
            order.append(rid)
        row = by_run[rid]
        ts = e.get("ts")
        if isinstance(ts, (int, float)):
            if row["first_ts"] is None or ts < row["first_ts"]:
                row["first_ts"] = ts
            if row["last_ts"] is None or ts > row["last_ts"]:
                row["last_ts"] = ts
        etype = e.get("event")
        row["event_counts"][etype] = row["event_counts"].get(etype, 0) + 1
    return [by_run[r] for r in order]


def run_durations(events: list[dict]) -> list[dict]:
    """Per-run wall time from the run bracket.

    duration_seconds = ts(first run-end) - ts(first run-start); an unbracketed
    run (missing either end) reports None — an honest unknown, never a
    fabricated zero.
    """
    out: list[dict] = []
    for row in runs(events):
        rid = row["run_id"]
        start_ts = None
        end_ts = None
        for e in events:
            if e.get("run_id") != rid:
                continue
            if e.get("event") == "run-start" and start_ts is None:
                start_ts = e.get("ts")
            elif e.get("event") == "run-end" and end_ts is None:
                end_ts = e.get("ts")
        duration = None
        if isinstance(start_ts, (int, float)) and isinstance(end_ts, (int, float)):
            duration = end_ts - start_ts
        out.append({"run_id": rid, "started_ts": start_ts, "ended_ts": end_ts,
                    "duration_seconds": duration})
    return out


def cycles_per_completion(events: list[dict]) -> dict:
    """Cycle counts vs completions over an event window.

    cycles = cycle-begin count (forward = data.kind == "real", meta = "meta");
    completions = pseudo-applied events whose pseudo is a terminal
    (__mark_complete__ / __mark_fixed__). cycles_per_completion is None when
    completions == 0 (never a fabricated number).
    """
    cycles = 0
    forward = 0
    meta = 0
    completions = 0
    for e in events:
        etype = e.get("event")
        if etype == "cycle-begin":
            cycles += 1
            kind = (e.get("data") or {}).get("kind")
            if kind == "meta":
                meta += 1
            else:
                forward += 1
        elif etype == "pseudo-applied":
            if (e.get("data") or {}).get("pseudo") in _COMPLETION_PSEUDOS:
                completions += 1
    ratio = round(cycles / completions, 2) if completions else None
    return {"cycles": cycles, "forward_cycles": forward, "meta_cycles": meta,
            "completions": completions, "cycles_per_completion": ratio}


def refusal_counts(events: list[dict], denies: list[dict]) -> dict:
    """Refusal/deny tallies across the telemetry AND deny ledgers.

    Telemetry side: gate-refusal (+ per-gate breakdown) and
    containment-refusal counts. Deny-ledger side: plain guard denies,
    process-friction entries, auto-readmits, and the unacked (pending
    hardening-debt) count — the two ledgers are complementary, never
    duplicated (guard denies are NOT telemetry events).
    """
    gate = 0
    containment = 0
    by_gate: dict = {}
    for e in events:
        etype = e.get("event")
        if etype == "gate-refusal":
            gate += 1
            g = (e.get("data") or {}).get("gate")
            if g:
                by_gate[g] = by_gate.get(g, 0) + 1
        elif etype == "containment-refusal":
            containment += 1
    guard_denies = 0
    friction = 0
    readmits = 0
    unacked = 0
    for d in denies:
        if d.get("auto_readmit"):
            readmits += 1
        elif d.get("kind") == "process-friction":
            friction += 1
        else:
            guard_denies += 1
        if not d.get("acked", False):
            unacked += 1
    return {"gate_refusals": gate, "containment_refusals": containment,
            "by_gate": by_gate, "guard_denies": guard_denies,
            "process_friction": friction, "auto_readmits": readmits,
            "unacked_denies": unacked}


def halt_dwell(events: list[dict]) -> list[dict]:
    """Pair each `halt` with the NEXT `sentinel-resolved` for the same item.

    Returns one row per halt event:
        {item_id, halt_ts, resolved_ts | None, dwell_seconds | None,
         terminal_reason, citation?: {source, line}}
    An unresolved halt reports None dwell (honest open halt). The citation is
    attached when the halt event carries reader provenance (_source/_line).
    """
    out: list[dict] = []
    for i, e in enumerate(events):
        if e.get("event") != "halt":
            continue
        item = e.get("item_id")
        halt_ts = e.get("ts")
        resolved_ts = None
        for later in events[i + 1:]:
            if (later.get("event") == "sentinel-resolved"
                    and later.get("item_id") == item):
                lts = later.get("ts")
                if isinstance(lts, (int, float)) and isinstance(halt_ts, (int, float)) \
                        and lts < halt_ts:
                    continue
                resolved_ts = lts
                break
        dwell = None
        if isinstance(halt_ts, (int, float)) and isinstance(resolved_ts, (int, float)):
            dwell = resolved_ts - halt_ts
        row = {
            "item_id": item,
            "halt_ts": halt_ts,
            "resolved_ts": resolved_ts,
            "dwell_seconds": dwell,
            "terminal_reason": (e.get("data") or {}).get("terminal_reason"),
        }
        if "_source" in e and "_line" in e:
            row["citation"] = {"source": e["_source"], "line": e["_line"]}
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Composed views
# ---------------------------------------------------------------------------

def _events_for_run(events: list[dict], run_id: str) -> list[dict]:
    return [e for e in events if e.get("run_id") == run_id]


def _ledger_line_windows(events: list[dict]) -> dict:
    """Per-source first/last physical line numbers (the citation window)."""
    windows: dict = {}
    for e in events:
        src = e.get("_source")
        line = e.get("_line")
        if src is None or line is None:
            continue
        w = windows.setdefault(src, {"first": line, "last": line})
        w["first"] = min(w["first"], line)
        w["last"] = max(w["last"], line)
    return windows


def trends_payload(repo_root) -> dict:
    """The /api/trends aggregate: per-run rows + window totals + deny trend.

    An absent/empty ledger renders the honest empty state
    (telemetry_available: false) rather than fabricating zeros.
    """
    events = load_events(repo_root)
    denies = load_denies(repo_root)
    if not events:
        return {
            "telemetry_available": False,
            "message": _NO_TELEMETRY_MESSAGE,
            "runs": [],
            "totals": None,
            "halts": [],
            "deny_ledger": refusal_counts([], denies),
        }
    durations = {r["run_id"]: r for r in run_durations(events)}
    run_rows: list[dict] = []
    for row in runs(events):
        rid = row["run_id"]
        run_events = _events_for_run(events, rid)
        cpc = cycles_per_completion(run_events)
        refusals = refusal_counts(run_events, [])
        halts = halt_dwell(run_events)
        run_rows.append({
            "run_id": rid,
            "pipeline": row["pipeline"],
            "forward_cycles": cpc["forward_cycles"],
            "meta_cycles": cpc["meta_cycles"],
            "completions": cpc["completions"],
            "cycles_per_completion": cpc["cycles_per_completion"],
            "gate_refusals": refusals["gate_refusals"],
            "containment_refusals": refusals["containment_refusals"],
            "halts": len(halts),
            "duration_seconds": durations.get(rid, {}).get("duration_seconds"),
        })
    return {
        "telemetry_available": True,
        "runs": run_rows,
        "totals": cycles_per_completion(events),
        "halts": halt_dwell(events),
        "deny_ledger": refusal_counts(events, denies),
    }


def run_summary(repo_root, run_id: str) -> dict:
    """The D8 retro view: one run's ledger deltas with per-figure citations.

    Missing run → {found: false, message: "no telemetry for this run …"} so the
    retro reports the miss honestly (older runs predate the ledger).
    """
    events = load_events(repo_root)
    run_events = _events_for_run(events, run_id)
    if not run_events:
        return {
            "run_id": run_id,
            "found": False,
            "message": f"no telemetry for this run ({run_id!r}) — "
                       f"the run may predate the ledger",
        }
    cpc = cycles_per_completion(run_events)
    refusals = refusal_counts(run_events, [])
    durations = {r["run_id"]: r for r in run_durations(run_events)}

    def _cite(e: dict) -> Optional[dict]:
        if "_source" in e and "_line" in e:
            return {"source": e["_source"], "line": e["_line"]}
        return None

    gate_rows = []
    containment_rows = []
    for e in run_events:
        if e.get("event") == "gate-refusal":
            gate_rows.append({
                "item_id": e.get("item_id"),
                "gate": (e.get("data") or {}).get("gate"),
                "failing_check": (e.get("data") or {}).get("failing_check"),
                "citation": _cite(e),
            })
        elif e.get("event") == "containment-refusal":
            containment_rows.append({
                "item_id": e.get("item_id"),
                "op": (e.get("data") or {}).get("op"),
                "guard": (e.get("data") or {}).get("guard"),
                "citation": _cite(e),
            })
    return {
        "run_id": run_id,
        "found": True,
        "pipeline": run_events[0].get("pipeline"),
        "event_count": len(run_events),
        "forward_cycles": cpc["forward_cycles"],
        "meta_cycles": cpc["meta_cycles"],
        "completions": cpc["completions"],
        "cycles_per_completion": cpc["cycles_per_completion"],
        "gate_refusals": gate_rows,
        "containment_refusals": containment_rows,
        "halts": halt_dwell(run_events),
        "sentinel_resolved": sum(
            1 for e in run_events if e.get("event") == "sentinel-resolved"),
        "duration_seconds": durations.get(run_id, {}).get("duration_seconds"),
        "ledger_lines": _ledger_line_windows(run_events),
    }


# ---------------------------------------------------------------------------
# CLI — the D8 retro entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pipeline_visualizer.trends",
        description="Pure-read telemetry-ledger aggregation "
                    "(harness-telemetry-ledger).",
    )
    parser.add_argument("--repo-root", required=True,
                        help="Repo whose telemetry ledger(s) to aggregate.")
    parser.add_argument("--run-id", default=None,
                        help="Emit the D8 per-run summary for this run_id "
                             "(the run marker's started_at). Omit for the "
                             "whole-window trends payload.")
    args = parser.parse_args(argv)
    if args.run_id:
        out = run_summary(args.repo_root, args.run_id)
    else:
        out = trends_payload(args.repo_root)
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
