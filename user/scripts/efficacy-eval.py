#!/usr/bin/env python3
"""
efficacy-eval.py — intervention-efficacy evaluator (the hypothesis ledger's
evaluation + consequence half).

Standalone stdlib analysis tool in the `toolify-miner.py` / `lazy-queue-doc.py`
mold: OFF the state-script compute path, READ-ONLY over the telemetry ledger,
and the SOLE post-capture writer of `docs/interventions/<id>.md` records
(written through the same `lazy_core._render_intervention_record` serializer
the capture half uses, so frontmatter stays diff-stable).

What one invocation does (D10-A — the batch orchestrators run this once at the
§1c.6 end-of-run flush; the operator runs it on demand; `/lazy-batch-retro`
shells it with `--dry-run` to cite verdicts):

  1. Enumerate `docs/interventions/*.md` (kind: intervention), skipping
     terminal records (status confirmed/refuted) and — with `--id` — anything
     but the named record.
  2. Accrue each record's post-ship window: distinct telemetry `run_id`s
     strictly newer than the FROZEN `baseline.last_run_id` (run identity is
     the marker `started_at`; lexical order == chronological). Review k
     (0-based = the record's `review_count`) is DUE when `(k+1) ×
     review_after_runs` post runs exist; it evaluates the non-overlapping
     slice `[k·R, (k+1)·R)`.
  3. Verdict per D5-A: rates are events-per-run; `rel = (post−base)/base·100`
     (base 0 with post > 0 ⇒ +100). decrease: rel ≤ −band → CONFIRMED,
     rel ≥ +band → REFUTED, else INCONCLUSIVE; increase mirrored. A verdict
     other than INCONCLUSIVE additionally requires `min_sample` combined
     events. Honest degradation reasons, never errors: `undeclared`,
     `kpi-unresolvable` (the friction-kpi-registry soft-dep seam —
     `_resolve_target_signal` resolves only `event:<type>` here),
     `invalid-direction`, `no-baseline (…)`, `min-sample x/y`, `within-band`.
  4. Confounder scan (D6): every other record whose post window overlaps this
     one is annotated on the review; a SAME-`target_signal` overlap CAPS a
     would-be-conclusive verdict at `INCONCLUSIVE (confounded)` — confounded
     data never triggers an automatic consequence. `self-emitted`
     signal independence is annotated (visibly weaker), never enforced.
  5. Write the review: append a `## Review <date>` section and update the
     frontmatter (status / review_count / escalated / reconsideration stamp)
     atomically. INCONCLUSIVE past 2 reviews escalates (D8-A, passive:
     `escalated: true` + the needs-triage listing — no sentinel, no halt).
  6. REFUTED consequence (D7-A): auto-enqueue `reconsider-<id>` through the
     SHIPPED ad-hoc route (`lazy-state.py --enqueue-adhoc --type bug`
     subprocess) behind the two-layer recurrence guard — layer 1: an existing
     `docs/bugs/reconsider-<id>/` dir, open OR archived, skips; layer 2: the
     `reconsideration_enqueued` frontmatter stamp — once stamped, NEVER
     enqueued again, even if the bug dir vanishes. Nothing is ever reverted
     here; the reconsideration item flows through /spec-bug normally.

Flags: `--repo-root` · `--json` · `--dry-run` (report only — zero writes,
zero enqueues, byte-inert) · `--id <intervention_id>` (single-record review).
Exit 0 even when verdicts are REFUTED — verdicts are data, not errors.
Exit 2 only for malformed input (nonexistent repo root).

Tests: test_efficacy_eval.py (pytest, hermetic via LAZY_STATE_DIR + temp
repos, matching test_lazy_queue_doc.py conventions).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lazy_core  # noqa: E402


# ---------------------------------------------------------------------------
# Target-signal resolution — the friction-kpi-registry soft-dep seam
# ---------------------------------------------------------------------------

def _resolve_target_signal(target_signal) -> "tuple[str, str | None]":
    """Resolve a record's target_signal to a countable ledger predicate.

    Returns ``(kind, event_type)``:
      - ``("event", <type>)`` — an ``event:<type>`` target; the evaluator
        counts matching ledger ``event`` fields directly.
      - ``("kpi", None)`` — a ``kpi:<system>.<kpi-id>`` target. The preferred
        vocabulary resolves through the friction-kpi-registry (SOFT dep, built
        concurrently); until that registry is wired here, kpi targets are
        honestly unresolvable → ``INCONCLUSIVE (kpi-unresolvable)``. This
        function is the ONE seam that feature extends (map the KPI id to its
        declared ledger event sources and return ("event", <type>)).
      - ``("undeclared", None)`` — the degrade-on-absence marker (D2-A).
      - ``("invalid", None)`` — anything else.
    """
    if not isinstance(target_signal, str) or not target_signal:
        return ("invalid", None)
    if target_signal == "undeclared":
        return ("undeclared", None)
    if target_signal.startswith("event:"):
        ev = target_signal[len("event:"):]
        return ("event", ev) if ev else ("invalid", None)
    if target_signal.startswith("kpi:"):
        return ("kpi", None)
    return ("invalid", None)


# ---------------------------------------------------------------------------
# Record IO
# ---------------------------------------------------------------------------

def _split_record_body(text: str) -> str:
    """Return the markdown body AFTER the frontmatter block (without the
    leading blank line). A file with no well-formed frontmatter returns the
    whole text (defensive — such a record is skipped upstream anyway)."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return text
    for j in range(i + 1, len(lines)):
        if lines[j].strip() == "---":
            body = "\n".join(lines[j + 1:])
            return body.lstrip("\n")
    return text


def _parse_record(path: Path) -> "dict | None":
    """parse_sentinel wrapped so a malformed record SKIPS instead of exiting
    (lazy_core._die sys.exit(2)s — an unparseable record must not kill the
    whole evaluation pass)."""
    try:
        return lazy_core.parse_sentinel(path)
    except (SystemExit, Exception):  # noqa: BLE001
        return None


def _enumerate_records(repo_root: Path, only_id: "str | None") -> list[dict]:
    """All parseable kind:intervention records, each as
    {"path", "meta", "body"} — sorted by filename for deterministic order."""
    records_dir = repo_root / "docs" / lazy_core._INTERVENTIONS_DIRNAME
    out: list[dict] = []
    if not records_dir.is_dir():
        return out
    for path in sorted(records_dir.glob("*.md")):
        meta = _parse_record(path)
        if not meta or meta.get("kind") != "intervention":
            continue
        rid = meta.get("intervention_id") or path.stem
        if only_id and rid != only_id:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append({"path": path, "meta": meta, "body": _split_record_body(text)})
    return out


def _write_record(rec: dict) -> None:
    """Atomic re-write through the SHARED serializer (diff-stable order)."""
    lazy_core._atomic_write(
        rec["path"],
        lazy_core._render_intervention_record(rec["meta"], rec["body"]),
    )


# ---------------------------------------------------------------------------
# Window + verdict arithmetic (D5-A)
# ---------------------------------------------------------------------------

def _cfg_int(meta: dict, key: str, default: int) -> int:
    try:
        return int(meta.get(key, default))
    except (TypeError, ValueError):
        return default


def _post_runs(meta: dict, run_ids: list[str]) -> list[str]:
    """Distinct run_ids strictly newer than the frozen post-window boundary
    (baseline.last_run_id; None ⇒ every run is post-ship)."""
    baseline = meta.get("baseline") or {}
    boundary = baseline.get("last_run_id") if isinstance(baseline, dict) else None
    if boundary is None:
        return list(run_ids)
    return [r for r in run_ids if isinstance(r, str) and r > boundary]


def _compute_verdict(meta: dict, events: list[dict],
                     window: list[str]) -> dict:
    """Pure verdict arithmetic for ONE due review window. Returns
    {"verdict", "reason", "delta_pct", "post_runs", "post_events",
    "post_value"} — confounder capping is applied by the caller (it needs the
    full record set)."""
    band = _cfg_int(meta, "band_pct", lazy_core.INTERVENTION_BAND_PCT)
    min_sample = _cfg_int(meta, "min_sample", lazy_core.INTERVENTION_MIN_SAMPLE)
    kind, ev_type = _resolve_target_signal(meta.get("target_signal"))
    result = {
        "verdict": "inconclusive", "reason": "", "delta_pct": None,
        "post_runs": len(window), "post_events": None, "post_value": None,
    }
    if kind == "undeclared":
        result["reason"] = "undeclared target_signal (declare an " \
                           "## Intervention Hypothesis block)"
        return result
    if kind == "kpi":
        result["reason"] = ("kpi-unresolvable (friction-kpi-registry not "
                            "wired; use event:<type> or extend "
                            "_resolve_target_signal)")
        return result
    if kind == "invalid":
        result["reason"] = f"invalid target_signal {meta.get('target_signal')!r}"
        return result

    window_set = set(window)
    post_events = sum(
        1 for e in events
        if e.get("run_id") in window_set and e.get("event") == ev_type
    )
    post_value = round(post_events / len(window), 4) if window else None
    result["post_events"] = post_events
    result["post_value"] = post_value

    direction = meta.get("expected_direction")
    if direction not in ("decrease", "increase"):
        result["reason"] = f"invalid-direction {direction!r}"
        return result

    baseline = meta.get("baseline") or {}
    if not isinstance(baseline, dict) or baseline.get("status") != "frozen":
        b_reason = (baseline or {}).get("reason") if isinstance(baseline, dict) \
            else None
        result["reason"] = f"no-baseline ({b_reason or 'not-frozen'})"
        return result

    base_events = int(baseline.get("events") or 0)
    base_value = float(baseline.get("value") or 0.0)
    total = base_events + post_events
    if total < min_sample:
        result["reason"] = f"min-sample {total}/{min_sample}"
        return result

    if base_value == 0.0:
        if post_value == 0.0:
            result["reason"] = "within-band (0 → 0; no movement)"
            result["delta_pct"] = 0.0
            return result
        rel = 100.0
    else:
        rel = round((post_value - base_value) / base_value * 100.0, 1)
    result["delta_pct"] = rel

    if direction == "decrease":
        conclusive = "confirmed" if rel <= -band else (
            "refuted" if rel >= band else None)
    else:  # increase
        conclusive = "confirmed" if rel >= band else (
            "refuted" if rel <= -band else None)
    if conclusive is None:
        result["reason"] = f"within-band (movement {rel:+.1f}% < ±{band}%)"
        return result
    result["verdict"] = conclusive
    result["reason"] = (f"movement {rel:+.1f}% vs band ±{band}% "
                        f"(direction {direction})")
    return result


def _confounders_for(rec: dict, all_records: list[dict]) -> list[dict]:
    """D6 confounder scan: every OTHER record whose post window overlaps this
    record's. Evaluated at review time, so overlap reduces to: the other
    record shipped AFTER this one (inside this post window), OR the other
    record is still under review (open/inconclusive — its window includes
    this record's ship). A record that CONCLUDED before this one shipped does
    not overlap."""
    meta = rec["meta"]
    mine_id = meta.get("intervention_id")
    mine_shipped = str(meta.get("shipped_date") or "")
    out: list[dict] = []
    for other in all_records:
        ometa = other["meta"]
        oid = ometa.get("intervention_id")
        if oid == mine_id:
            continue
        oshipped = str(ometa.get("shipped_date") or "")
        still_open = ometa.get("status") in ("open", "inconclusive")
        if (oshipped and mine_shipped and oshipped >= mine_shipped) or still_open:
            out.append({"id": oid, "target_signal": ometa.get("target_signal")})
    return out


# ---------------------------------------------------------------------------
# Consequence (D7-A) — REFUTED → reconsider-<id> via the SHIPPED enqueue
# ---------------------------------------------------------------------------

def _reconsideration_dir_exists(repo_root: Path, reconsider_id: str) -> bool:
    """Guard layer 1: an open docs/bugs/<reconsider-id>/ dir OR any archived
    docs/bugs/_archive/ entry whose name starts with it (archive_fixed may
    suffix -archived-<date> on collision)."""
    bugs = repo_root / "docs" / "bugs"
    if (bugs / reconsider_id).exists():
        return True
    archive = bugs / "_archive"
    try:
        if archive.is_dir():
            for child in archive.iterdir():
                if child.name == reconsider_id or child.name.startswith(
                        reconsider_id + "-"):
                    return True
    except OSError:
        pass
    return False


def _enqueue_reconsideration(repo_root: Path, rec: dict, review: dict,
                             today: str) -> str:
    """Fire the REFUTED consequence behind the two-layer recurrence guard.

    Returns the human `consequence:` string for the review; stamps
    ``reconsideration_enqueued`` on the record meta (caller persists) for a
    successful enqueue AND for a layer-1 skip (the guard outcome is itself
    recorded — one reconsideration per intervention, ever). An enqueue
    subprocess FAILURE does NOT stamp, so the next evaluation retries.
    """
    meta = rec["meta"]
    rid = meta.get("intervention_id")
    reconsider_id = f"reconsider-{rid}"

    # Layer 2: the stamp — once set, never enqueue again, even if the bug dir
    # vanished (a refuted intervention gets exactly one reconsideration).
    if meta.get("reconsideration_enqueued"):
        return (f"skipped (already enqueued "
                f"{meta.get('reconsideration_enqueued')})")

    # Layer 1: an existing reconsideration dir, open or archived.
    if _reconsideration_dir_exists(repo_root, reconsider_id):
        meta["reconsideration_enqueued"] = today
        return f"skipped (docs/bugs/{reconsider_id} exists, open or archived)"

    record_rel = os.path.relpath(str(rec["path"]), str(repo_root))
    brief = (
        f"REFUTED intervention verdict — evidence attached.\n\n"
        f"- Intervention record: {record_rel}\n"
        f"- Intervention: {rid} (pipeline: {meta.get('pipeline')})\n"
        f"- Target signal: {meta.get('target_signal')} — expected "
        f"{meta.get('expected_direction')}, observed "
        f"{review.get('delta_pct'):+.1f}% ({review.get('reason')})\n"
        f"- Baseline (frozen at capture): "
        f"{(meta.get('baseline') or {}).get('value')} ev/run; post window: "
        f"{review.get('post_value')} ev/run over {review.get('post_runs')} "
        f"runs\n\n"
        f"Question for /spec-bug: REVERT or REDESIGN (or accept with "
        f"rationale)? Nothing was reverted automatically — the evaluator "
        f"only enqueues; this item flows through spec, plan, and normal "
        f"triage."
    )
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "lazy-state.py"),
        "--enqueue-adhoc",
        "--type", "bug",
        "--id", reconsider_id,
        "--name", f"Reconsider intervention {rid} (REFUTED)",
        "--brief", brief,
        "--repo-root", str(repo_root),
    ]
    # LAZY_ORCHESTRATOR=1 in the child env — the established pattern
    # (enqueue_adhoc_bug / materialize_wi): this is a sanctioned
    # orchestrator-side enqueue and must be hermetic against an ambient cycle
    # marker (the C3 guard would otherwise refuse it exit 3).
    env = {**os.environ, "LAZY_ORCHESTRATOR": "1"}
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        return f"enqueue-failed ({exc}) — will retry next evaluation"
    if proc.returncode != 0:
        return (f"enqueue-failed (exit {proc.returncode}) — will retry next "
                f"evaluation")
    meta["reconsideration_enqueued"] = today
    return f"enqueued {reconsider_id}"


# ---------------------------------------------------------------------------
# One record's review
# ---------------------------------------------------------------------------

def _review_record(rec: dict, all_records: list[dict], events: list[dict],
                   run_ids: list[str], repo_root: Path, *, dry_run: bool,
                   today: str) -> "dict | None":
    """Evaluate ONE reviewable record. Returns the verdict entry (and, unless
    dry_run, persists the review + any consequence), or a not-due marker
    ({"not_due": …}), or None when the record is terminal."""
    meta = rec["meta"]
    rid = meta.get("intervention_id")
    if meta.get("status") not in ("open", "inconclusive"):
        return None
    review_after = _cfg_int(
        meta, "review_after_runs", lazy_core.INTERVENTION_REVIEW_AFTER_RUNS)
    k = _cfg_int(meta, "review_count", 0)
    post = _post_runs(meta, run_ids)
    if len(post) < (k + 1) * review_after:
        return {"not_due": {
            "id": rid,
            "post_runs": max(0, len(post) - k * review_after),
            "needed": review_after,
        }}
    window = post[k * review_after:(k + 1) * review_after]
    verdict = _compute_verdict(meta, events, window)

    # D6 confounders: annotate always; cap a would-be-conclusive verdict on a
    # SAME-signal overlap (attribution genuinely impossible → INCONCLUSIVE
    # (confounded); it errs toward inaction, and INCONCLUSIVE has its own D8
    # escalation path).
    confounders = _confounders_for(rec, all_records)
    conf_strings = [f"{c['id']} ({c['target_signal']})" for c in confounders]
    mine_target = meta.get("target_signal")
    same_signal = [
        c for c in confounders
        if c.get("target_signal") == mine_target
        and mine_target not in (None, "undeclared")
    ]
    capped = False
    if same_signal and verdict["verdict"] != "inconclusive":
        capped = True
        verdict["verdict"] = "inconclusive"
        verdict["reason"] = (
            "confounded — same-signal overlap with "
            + ", ".join(c["id"] for c in same_signal)
            + f" (raw: {verdict['reason']})"
        )

    independence = meta.get("signal_independence")
    new_count = k + 1
    escalated = bool(meta.get("escalated")) or (
        verdict["verdict"] == "inconclusive" and new_count >= 2
    )

    consequence = "none"
    if verdict["verdict"] == "refuted" and not dry_run:
        consequence = _enqueue_reconsideration(repo_root, rec, verdict, today)
    elif verdict["verdict"] == "refuted" and dry_run:
        consequence = "would enqueue reconsider-{} (dry-run)".format(rid)

    entry = {
        "id": rid,
        "verdict": verdict["verdict"],
        "reason": verdict["reason"],
        "delta_pct": verdict["delta_pct"],
        "confounders": conf_strings,
        "independence": independence,
        "consequence": consequence,
    }

    if not dry_run:
        baseline = meta.get("baseline") or {}
        review_lines = [
            f"## Review {today}",
            "",
            f"- review_number: {new_count}",
            f"- verdict: {verdict['verdict'].upper()}"
            + (" (confounded cap)" if capped else ""),
            f"- reason: {verdict['reason']}",
            f"- baseline: {baseline.get('value')} ev/run "
            f"({baseline.get('events')} events / {baseline.get('runs')} runs; "
            f"status {baseline.get('status')})",
            f"- post_window: {verdict['post_value']} ev/run "
            f"({verdict['post_events']} events / {verdict['post_runs']} runs)",
            f"- delta_pct: {verdict['delta_pct']}",
            "- confounders: " + (", ".join(conf_strings) if conf_strings
                                 else "none"),
            f"- independence: {independence}"
            + (" — verdict weight reduced (self-emitted signal)"
               if independence == "self-emitted" else ""),
            f"- consequence: {consequence}",
        ]
        meta["review_count"] = new_count
        meta["status"] = verdict["verdict"]
        meta["escalated"] = escalated
        rec["body"] = rec["body"].rstrip() + "\n\n" + "\n".join(review_lines)
        _write_record(rec)
    return {"verdict_entry": entry}


# ---------------------------------------------------------------------------
# Canary watcher (harness-change-canary-rollback Phases 2 + 3)
#
# `efficacy-eval.py --canary` is a run-boundary mode of this same evaluator:
# it accrues each OPEN canary's observation window (D2: next N completed runs
# after ship, 30-day wall-clock ceiling), applies the D2 tripwire bands + D3
# surface-based incident attribution, and on a trip flags-and-enqueues an
# evidence-bearing `canary-revert-<id>` bug stub (D4/D5 — never a silent
# revert). Read-only over every signal; the SOLE writer of `canary.*` record
# fields + the trip-time `EVIDENCE.md`. Fail-open throughout — a watcher error
# degrades to "this record accrues nothing this run" and NEVER blocks a run.
# The two cadences share readers/writers but live behind this clean `--canary`
# boundary (separate helpers, separate tests).
# ---------------------------------------------------------------------------

# D2 tripwire constants (one block; the window defaults live in lazy_core:
# CANARY_WINDOW_RUNS_DEFAULT / CANARY_WINDOW_DAYS_CEILING). Hair-triggered
# relative to the efficacy verdict bands (a trip enqueues an INVESTIGATION,
# not a verdict): a 25% regression with ≥3 post-ship occurrences, or ≥2
# attributable fresh incidents.
CANARY_REGRESSION_BAND_PCT = 25
CANARY_MIN_POST_OCCURRENCES = 3
CANARY_INCIDENT_TRIP_COUNT = 2


# --- WU-5: D2 tripwire band + D3 surface-based incident attribution ---------

def _canary_band_trip(meta: dict, canary: dict, events: list[dict],
                      window: list[str]) -> dict:
    """D2 tripwire: the targeted signal regressed past the declared band
    (default ±25% relative to the FROZEN baseline) with ≥3 post-ship
    occurrences in the accrued window. Hair-triggered relative to the efficacy
    verdict band. A kpi:<...> / undeclared / no-baseline target degrades to
    no-trip (never errors) — the KPI-registry band is the sibling seam, not
    wired here in v1."""
    out = {"trip": False, "reason": "", "rel": None,
           "band": CANARY_REGRESSION_BAND_PCT, "post_events": None,
           "post_value": None, "base_value": None}
    kind, ev_type = _resolve_target_signal(meta.get("target_signal"))
    if kind != "event":
        out["reason"] = f"band-not-evaluable (target {kind})"
        return out
    direction = meta.get("expected_direction")
    if direction not in ("decrease", "increase"):
        out["reason"] = f"band-not-evaluable (direction {direction!r})"
        return out
    baseline = meta.get("baseline") or {}
    if not isinstance(baseline, dict) or baseline.get("status") != "frozen":
        out["reason"] = "band-not-evaluable (no frozen baseline)"
        return out
    window_set = set(window)
    post_events = sum(
        1 for e in events
        if e.get("run_id") in window_set and e.get("event") == ev_type
    )
    post_value = round(post_events / len(window), 4) if window else 0.0
    base_value = float(baseline.get("value") or 0.0)
    band = _cfg_int(meta, "canary_band_pct", CANARY_REGRESSION_BAND_PCT)
    out.update({"post_events": post_events, "post_value": post_value,
                "base_value": base_value, "band": band})
    if base_value == 0.0:
        rel = 100.0 if post_value > 0 else 0.0
    else:
        rel = round((post_value - base_value) / base_value * 100.0, 1)
    out["rel"] = rel
    # A "regression" is movement AGAINST the intervention's intended direction:
    # a change that was meant to DECREASE a signal regresses when the signal
    # goes UP (rel >= +band); an INCREASE target regresses on a drop.
    regressed = rel >= band if direction == "decrease" else rel <= -band
    out["trip"] = bool(regressed and post_events >= CANARY_MIN_POST_OCCURRENCES)
    if out["trip"]:
        out["reason"] = (
            f"targeted signal {meta.get('target_signal')} regressed "
            f"{rel:+.1f}% vs frozen baseline {base_value} ev/run "
            f"(band ±{band}%, {post_events} post-ship occurrences over "
            f"{len(window)} window runs)")
    else:
        out["reason"] = (
            f"within band: {rel:+.1f}% vs ±{band}% "
            f"({post_events} post-ship occurrences)")
    return out


def _canary_hook_surface(hook) -> "str | None":
    """Map a hook name to its repo-relative script path (`user/hooks/<name>`).
    A non-hook / empty value → None (conservative: never attributes)."""
    if not isinstance(hook, str) or not hook.strip():
        return None
    base = hook.strip().replace("\\", "/").split("/")[-1]
    if base.endswith(".sh") or base.endswith(".ps1"):
        return "user/hooks/" + base
    return None


def _canary_entry_surface(entry: dict) -> "str | None":
    """Resolve a fresh-incident entry's emitting surface to a repo-relative
    path (D3). Explicit surface fields win; else a hook name maps to its
    script. An unresolvable surface returns None and NEVER attributes."""
    if not isinstance(entry, dict):
        return None
    for key in ("surface", "surface_file", "source_file"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().replace("\\", "/")
    return _canary_hook_surface(entry.get("hook"))


def _load_incident_scan():
    """Import the dash-named incident-scan module for its READ-ONLY fresh-
    incident readers. Fail-open — an import failure degrades to deny-ledger-
    only attribution (never raises)."""
    try:
        import importlib.util
        path = _SCRIPTS_DIR / "incident-scan.py"
        spec = importlib.util.spec_from_file_location("incident_scan", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001
        return None


def _canary_gather_incidents(repo_root: Path) -> list[dict]:
    """Read fresh incidents from the deny ledger + hook-events + legacy
    breadcrumbs (the incident-scan.py reader surface — clustered incidents are
    the preferred input, raw deny/breadcrumb the fallback), each resolved to
    {ts, surface, kind, line}. Read-only + fail-open."""
    incidents: list[dict] = []

    def _add(ts, surface, kind, entry):
        if not isinstance(ts, (int, float)):
            return
        incidents.append({"ts": float(ts), "surface": surface, "kind": kind,
                          "line": json.dumps(entry, sort_keys=True)})

    try:
        for e in lazy_core.read_deny_ledger():
            kind = "friction" if e.get("kind") == "process-friction" else "deny"
            _add(e.get("ts"), _canary_entry_surface(e), kind, e)
    except Exception:  # noqa: BLE001
        pass

    inc = _load_incident_scan()
    if inc is not None:
        try:
            for e in inc.read_hook_events(repo_root):
                _add(e.get("ts"), _canary_entry_surface(e),
                     f"hook-{e.get('kind') or ''}", e)
        except Exception:  # noqa: BLE001
            pass
        try:
            for c in inc.read_legacy_crumbs():
                ts = inc._parse_crumb_ts(str(c.get("at") or ""))
                _add(ts, _canary_entry_surface(c), "hook-error", c)
        except Exception:  # noqa: BLE001
            pass
    return incidents


def _canary_window_start_ts(opened) -> float:
    """The window's lower time bound: the `opened` date at 00:00 UTC. An
    unparseable date → 0.0 (attribute all fresh incidents — favors detection,
    a false trip costs one triaged stub per the SPEC's D2 philosophy)."""
    try:
        d = datetime.datetime.strptime(str(opened), "%Y-%m-%d")
        return d.replace(tzinfo=datetime.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _canary_attribute(canary: dict,
                      incidents: list[dict]) -> "tuple[list, list]":
    """D3 surface-based attribution: an incident attributes iff (i) its
    timestamp is inside the window (≥ the canary's opened epoch) AND (ii) its
    emitting surface ∈ canary.surfaces. Unknown/unresolvable surfaces NEVER
    attribute. Returns (attributed, unattributed_in_window) — the latter is
    listed-but-not-counted per D3. A shared surface counts against every
    matching open canary because each is attributed independently."""
    start = _canary_window_start_ts(canary.get("opened"))
    surfaces = set(canary.get("surfaces") or [])
    attributed: list[dict] = []
    unattributed: list[dict] = []
    for inc in incidents:
        if inc["ts"] < start:
            continue  # pre-window — not fresh for this canary
        if inc.get("surface") and inc["surface"] in surfaces:
            attributed.append(inc)
        else:
            unattributed.append(inc)
    return (attributed, unattributed)


# --- WU-6: trip consequence (flag-and-enqueue + EVIDENCE.md + once-ever) -----

def _canary_revert_dir_exists(repo_root: Path, revert_id: str) -> bool:
    """Guard layer 1: an open docs/bugs/<revert-id>/ dir OR any archived
    docs/bugs/_archive/ entry whose name starts with it (mirrors
    _reconsideration_dir_exists)."""
    bugs = repo_root / "docs" / "bugs"
    if (bugs / revert_id).exists():
        return True
    archive = bugs / "_archive"
    try:
        if archive.is_dir():
            for child in archive.iterdir():
                if child.name == revert_id or child.name.startswith(
                        revert_id + "-"):
                    return True
    except OSError:
        pass
    return False


_CANARY_PARITY_INSTRUCTION = (
    "This change touches a parity-guarded coupled pair. Any revert MUST cover "
    "the WHOLE pair and END with `python3 user/scripts/lazy_parity_audit.py "
    "--repo-root .` green — reverting one half breaks the audit."
)


def _canary_evidence_text(rec: dict, ev: dict, repo_root: Path,
                          today: str) -> str:
    """Serialize the trip evidence (D5) — trip reason verbatim, full commit
    set, coupled-pair scope + the parity-audit instruction, degraded note, and
    linked docs — for the seeded bug dir's EVIDENCE.md."""
    meta = rec["meta"]
    rid = meta.get("intervention_id")
    record_rel = os.path.relpath(str(rec["path"]), str(repo_root))
    pipeline = meta.get("pipeline") or "feature"
    item_root = "bugs" if pipeline == "bug" else "features"
    commit_lines = "\n".join(f"- {c}" for c in ev["commit_set"]) or "- (none derived)"
    attributed = [i["line"] for i in ev["attributed"]]
    band = ev["band"]
    fm = [
        "---",
        "kind: canary-evidence",
        f"canary_revert_of: {rid}",
        f"intervention_record: {record_rel}",
        f"tripped: {today}",
        "---",
    ]
    body = [
        "",
        f"# Canary Trip Evidence — {rid}",
        "",
        "Flag-and-enqueue only — NOTHING was reverted automatically (D4). "
        "Triage this like any bug: revert (covering the pair scope + parity "
        "audit below), redesign, or close-as-noise (itself a signal for "
        "tuning the canary bands).",
        "",
        "## Trip reason",
        "",
        ev["reason"] or "(trip detected)",
        "",
        "### Band numbers",
        "",
        f"- relative movement: {band.get('rel')}% (band ±{band.get('band')}%)",
        f"- post-ship occurrences: {band.get('post_events')} "
        f"(baseline {band.get('base_value')} ev/run → "
        f"post {band.get('post_value')} ev/run)",
        "",
        "### Attributed fresh incidents (verbatim)",
        "",
        "```",
        *(attributed or ["(none — band-only trip)"]),
        "```",
        "",
        "## Commit set (revert target)",
        "",
        commit_lines,
        "",
        "## Coupled-pair scope",
        "",
    ]
    if ev["pair_scope"]:
        body.append(_CANARY_PARITY_INSTRUCTION)
        body.append("")
        body.extend(f"- {half}" for half in ev["pair_scope"])
    else:
        body.append(
            "No coupled-pair scope — the commit set touches no parity-guarded "
            "pair, so a revert need not span a sibling.")
    body += [
        "",
        "## Degraded-revert note",
        "",
        ev["degraded_revert_note"] or (
            "none — a plain `git revert` of the commit set is expected to back "
            "the change out."),
        "",
        "## Linked docs",
        "",
        f"- Intervention record: {record_rel}",
        f"- SPEC: docs/{item_root}/{rid}/SPEC.md",
        f"- Gate verdict (if present): docs/{item_root}/{rid}/GATE_VERDICT.md",
        "",
    ]
    return "\n".join(fm + body)


def _canary_enqueue_revert(repo_root: Path, revert_id: str, rid: str,
                           record_rel: str) -> bool:
    """Shell the SHIPPED bug enqueue (copies the _enqueue_reconsideration
    subprocess + LAZY_ORCHESTRATOR=1 env pattern verbatim — NEVER a queue.json
    hand-edit). Returns True on a clean enqueue."""
    brief = (
        f"Canary tripped for a shipped control-surface change — evidence "
        f"attached (EVIDENCE.md in this dir).\n\n"
        f"- Intervention record: {record_rel}\n"
        f"- Canary: {rid}\n\n"
        f"Question for /spec-bug: REVERT (covering the coupled-pair scope + a "
        f"green parity audit), REDESIGN, or close-as-noise? Nothing was "
        f"reverted automatically — the canary only flags and enqueues; this "
        f"item flows through spec, plan, and normal triage under full gates."
    )
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "lazy-state.py"),
        "--enqueue-adhoc",
        "--type", "bug",
        "--id", revert_id,
        "--name", f"Revert-or-redesign canary trip: {rid}",
        "--brief", brief,
        "--repo-root", str(repo_root),
    ]
    env = {**os.environ, "LAZY_ORCHESTRATOR": "1"}
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, check=False)
    except OSError:
        return False
    return proc.returncode == 0


def _canary_fire_consequence(repo_root: Path, rec: dict, ev: dict,
                             today: str) -> str:
    """Fire the trip consequence behind the two-layer once-ever guard (mirrors
    _enqueue_reconsideration): enqueue canary-revert-<id>, write EVIDENCE.md,
    and stamp canary.status: tripped + the record-level guard stamp. The
    watcher stays the SOLE writer of canary.* fields. Flag-and-enqueue ONLY —
    no revert, no writes outside record/evidence/queue."""
    meta = rec["meta"]
    canary = meta["canary"]
    rid = meta.get("intervention_id")
    revert_id = f"canary-revert-{rid}"

    # Layer 2: the record-level stamp — once set, never enqueue again (even if
    # the bug dir vanished). One revert item per canary, ever.
    if meta.get("canary_revert_enqueued"):
        return f"skipped (already enqueued {meta.get('canary_revert_enqueued')})"

    # Layer 1: an existing revert dir, open or archived.
    if _canary_revert_dir_exists(repo_root, revert_id):
        canary["status"] = "tripped"
        meta["canary_revert_enqueued"] = today
        _write_record(rec)
        return f"skipped (docs/bugs/{revert_id} exists, open or archived)"

    record_rel = os.path.relpath(str(rec["path"]), str(repo_root))
    if not _canary_enqueue_revert(repo_root, revert_id, rid, record_rel):
        # No stamp on failure — the next run retries (status stays open).
        return "enqueue-failed — will retry next run"

    # The enqueue seeded docs/bugs/<revert_id>/; drop the EVIDENCE.md capsule.
    evidence_path = repo_root / "docs" / "bugs" / revert_id / "EVIDENCE.md"
    try:
        lazy_core._atomic_write(
            evidence_path, _canary_evidence_text(rec, ev, repo_root, today))
    except OSError:
        pass  # evidence is best-effort; the guard stamp still fires

    canary["status"] = "tripped"
    meta["canary_revert_enqueued"] = today
    _write_record(rec)
    return f"enqueued {revert_id}"


def _canary_open_records(records: list[dict]) -> list[dict]:
    """The subset of enumerated records carrying an OPEN canary sub-map — the
    watcher's wake predicate (a closed-clean / tripped / no-canary record is
    skipped)."""
    out: list[dict] = []
    for rec in records:
        canary = rec["meta"].get("canary")
        if isinstance(canary, dict) and canary.get("status") == "open":
            out.append(rec)
    return out


def _canary_window_runs(canary: dict) -> int:
    """The record's canary window size (per-record overridable via the frozen
    `window_runs` field; falls back to the module default)."""
    wr = canary.get("window_runs")
    if isinstance(wr, int) and wr > 0:
        return wr
    return lazy_core.CANARY_WINDOW_RUNS_DEFAULT


def _canary_ceiling_matured(opened, today: str) -> bool:
    """True when the 30-day wall-clock ceiling has elapsed since `opened`
    (closes a rarely-run repo's canary even with < window_runs runs). An
    unparseable date is treated as NOT matured (fail-safe — never a spurious
    close)."""
    try:
        o = datetime.date.fromisoformat(str(opened))
        t = datetime.date.fromisoformat(str(today))
    except (ValueError, TypeError):
        return False
    return (t - o).days >= lazy_core.CANARY_WINDOW_DAYS_CEILING


def _canary_evaluate_record(rec: dict, events: list[dict], run_ids: list[str],
                            incidents: list[dict], today: str) -> dict:
    """Evaluate ONE open-canary record for this run boundary. Pure (no writes);
    the caller applies any consequence. Returns:
    {"id", "window_runs", "post_runs", "window", "matured", "no_data", "trip",
     "band", "attributed", "unattributed", "reason", "pair_scope",
     "commit_set", "degraded_revert_note"}."""
    meta = rec["meta"]
    canary = meta.get("canary") or {}
    rid = meta.get("intervention_id")
    window_runs = _canary_window_runs(canary)
    post = _post_runs(meta, run_ids)
    window = post[:window_runs]
    run_matured = len(post) >= window_runs
    ceiling_matured = _canary_ceiling_matured(canary.get("opened"), today)
    matured = run_matured or ceiling_matured

    band = _canary_band_trip(meta, canary, events, window)
    attributed, unattributed = _canary_attribute(canary, incidents)
    incident_trip = len(attributed) >= CANARY_INCIDENT_TRIP_COUNT
    trip = bool(band.get("trip")) or incident_trip

    # A matured window with ZERO observable runs is honest no-data (D2/D7) —
    # only when it did NOT trip (an incident trip needs no runs).
    no_data = bool(matured and len(window) == 0 and not trip)

    reasons: list[str] = []
    if band.get("trip"):
        reasons.append(band.get("reason", ""))
    if incident_trip:
        surfaces = sorted({i["surface"] for i in attributed if i.get("surface")})
        reasons.append(
            f"{len(attributed)} attributable fresh incident(s) on "
            f"{', '.join(surfaces) or '(surface)'} within the window"
        )
    return {
        "id": rid,
        "window_runs": window_runs,
        "post_runs": len(post),
        "window": len(window),
        "matured": matured,
        "no_data": no_data,
        "trip": trip,
        "band": band,
        "attributed": attributed,
        "unattributed": unattributed,
        "reason": " AND ".join(r for r in reasons if r),
        "pair_scope": list(canary.get("pair_scope") or []),
        "commit_set": list(canary.get("commit_set") or []),
        "degraded_revert_note": canary.get("degraded_revert_note"),
    }


def _canary_close_section(ev: dict, today: str) -> str:
    """The `## Canary <date>` record-body section (D7 steady-state handoff):
    runs observed, signal movement, and incidents attributed (none/list)."""
    band = ev.get("band") or {}
    attributed = ev.get("attributed") or []
    unattributed = ev.get("unattributed") or []
    lines = [
        f"## Canary {today}",
        "",
        f"- window: closed after {ev['window']}/{ev['window_runs']} observed "
        f"post-ship run(s) (matured: {ev['matured']})",
        f"- signal movement: {band.get('reason') or 'n/a (no observable runs)'}",
    ]
    if attributed:
        surfaces = sorted({i.get("surface") for i in attributed
                           if i.get("surface")})
        lines.append(
            f"- incidents attributed: {len(attributed)} on "
            f"{', '.join(surfaces) or '(surface)'}")
        lines.append("")
        lines.append("```")
        lines.extend(i["line"] for i in attributed)
        lines.append("```")
    else:
        lines.append("- incidents attributed: none")
    if unattributed:
        lines.append(
            f"- unattributed in-window incidents: {len(unattributed)} "
            f"(listed, never counted)")
    lines.append(
        "- handoff: the efficacy review proceeds on its own longer cadence — "
        "a clean canary does NOT pre-judge the efficacy verdict, and the "
        "watcher stops waking this record.")
    return "\n".join(lines)


def _canary_stamp_closed(rec: dict, ev: dict, today: str, status: str) -> None:
    """Close a matured, no-trip canary window (D7): stamp `canary.status`
    (`closed-clean` or `closed-clean (no-data)`) and append a `## Canary <date>`
    record-body section. The watcher stays the SOLE writer of `canary.*` and
    NEVER touches an efficacy verdict field (status / review_count / …)."""
    rec["meta"]["canary"]["status"] = status
    rec["body"] = rec["body"].rstrip() + "\n\n" + _canary_close_section(ev, today)
    _write_record(rec)


def run_canary(repo_root: Path, args, today: str) -> dict:
    """The `--canary` mode entry point. Enumerates open-canary records, accrues
    each window, detects trips (D2/D3), fires the flag-and-enqueue consequence
    (D4/D5) unless `--dry-run`, and stamps honest no-data closes. Returns the
    payload dict."""
    records = _enumerate_records(repo_root, args.id)
    open_recs = _canary_open_records(records)
    events = lazy_core.read_intervention_telemetry(repo_root)
    run_ids = sorted({
        e.get("run_id") for e in events
        if isinstance(e.get("run_id"), str) and e.get("run_id")
    })
    incidents = _canary_gather_incidents(repo_root)

    trips: list[dict] = []
    closed_no_data: list[str] = []
    closed_clean: list[str] = []
    monitoring: list[dict] = []
    for rec in open_recs:
        ev = _canary_evaluate_record(rec, events, run_ids, incidents, today)
        if ev["trip"]:
            consequence = "would enqueue canary-revert-{} (dry-run)".format(
                ev["id"]) if args.dry_run else _canary_fire_consequence(
                repo_root, rec, ev, today)
            trips.append({
                "id": ev["id"],
                "revert_id": f"canary-revert-{ev['id']}",
                "reason": ev["reason"],
                "attributed": [i["line"] for i in ev["attributed"]],
                "unattributed": [i["line"] for i in ev["unattributed"]],
                "band": {k: ev["band"].get(k) for k in
                         ("trip", "rel", "band", "post_events", "post_value",
                          "base_value")},
                "pair_scope": ev["pair_scope"],
                "consequence": consequence,
            })
        elif ev["matured"]:
            # D7 window close: a matured window with no trip closes clean. Zero
            # observable runs is the honest `(no-data)` variant; both append a
            # `## Canary <date>` record section and stop waking the record.
            status = "closed-clean (no-data)" if ev["no_data"] \
                else "closed-clean"
            if not args.dry_run:
                _canary_stamp_closed(rec, ev, today, status)
            if ev["no_data"]:
                closed_no_data.append(ev["id"])
            else:
                closed_clean.append(ev["id"])
        else:
            monitoring.append({
                "id": ev["id"],
                "window": f"{ev['window']}/{ev['window_runs']} runs",
                "matured": ev["matured"],
                "attributed": len(ev["attributed"]),
                "unattributed": len(ev["unattributed"]),
            })

    notify = None
    if trips:
        notify = "canary tripped: " + ", ".join(t["id"] for t in trips)
    return {
        "mode": "canary",
        "open_canaries": len(open_recs),
        "trips": trips,
        "closed_no_data": closed_no_data,
        "closed_clean": closed_clean,
        "monitoring": monitoring,
        "notify": notify,
        "dry_run": bool(args.dry_run),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate intervention records against post-ship "
                    "telemetry (intervention-efficacy-tracking).")
    parser.add_argument("--repo-root", default=os.getcwd(),
                        help="Repo whose docs/interventions/ ledger to "
                             "evaluate (default: cwd).")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report verdicts WITHOUT writing reviews or "
                             "enqueuing consequences (byte-inert).")
    parser.add_argument("--id", default=None,
                        help="Review only the named intervention_id.")
    parser.add_argument("--canary", action="store_true",
                        help="Run the harness-change canary watcher mode "
                             "(D2/D3 tripwire over open canary windows) "
                             "instead of the efficacy review.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    if not repo_root.is_dir():
        payload = {"error": f"--repo-root is not a directory: {repo_root}"}
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 2
    repo_root = repo_root.resolve()

    # Bind the active repo so the state-dir ledger resolves per repo when
    # LAZY_STATE_DIR is unset (production) — the read-side chokepoint.
    try:
        lazy_core.set_active_repo_root(str(repo_root))
    except Exception:  # noqa: BLE001 — binding failure degrades to cwd rules
        pass

    today = datetime.date.today().isoformat()

    # --canary: the run-boundary watcher cadence (a fully separate branch;
    # never blocks a run — every read is fail-open).
    if args.canary:
        try:
            payload = run_canary(repo_root, args, today)
        except Exception as exc:  # noqa: BLE001 — fail-open: never block a run
            payload = {"mode": "canary", "error": f"canary watcher degraded: "
                       f"{exc}", "trips": [], "closed_no_data": [],
                       "monitoring": [], "notify": None,
                       "dry_run": bool(args.dry_run)}
        if args.json:
            sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        else:
            trips = payload.get("trips", [])
            sys.stdout.write(
                f"efficacy-eval --canary: {payload.get('open_canaries', 0)} "
                f"open, {len(trips)} tripped, "
                f"{len(payload.get('closed_clean', []))} closed-clean, "
                f"{len(payload.get('closed_no_data', []))} closed no-data\n")
            for t in trips:
                sys.stdout.write(
                    f"  ⚠ canary tripped: {t['id']}\n"
                    f"    reason: {t['reason']}\n"
                    f"    {t['consequence']}\n")
        return 0

    records = _enumerate_records(repo_root, args.id)
    events = lazy_core.read_intervention_telemetry(repo_root)
    run_ids = sorted({
        e.get("run_id") for e in events
        if isinstance(e.get("run_id"), str) and e.get("run_id")
    })

    verdicts: list[dict] = []
    not_due: list[dict] = []
    for rec in records:
        outcome = _review_record(
            rec, records, events, run_ids, repo_root,
            dry_run=args.dry_run, today=today,
        )
        if outcome is None:
            continue
        if "not_due" in outcome:
            not_due.append(outcome["not_due"])
        else:
            verdicts.append(outcome["verdict_entry"])

    # Needs-triage (D8 passive surfacing): every escalated, still-unresolved
    # record — re-read from the (possibly just-updated) metas.
    needs_triage: list[str] = []
    for rec in records:
        meta = rec["meta"]
        if meta.get("escalated") and meta.get("status") not in (
                "confirmed", "refuted"):
            needs_triage.append(
                f"{meta.get('intervention_id')} (escalated: "
                f"{meta.get('review_count')} inconclusive reviews)"
            )

    payload = {
        "reviewed": len(verdicts),
        "verdicts": verdicts,
        "needs_triage": needs_triage,
        "not_due": not_due,
        "dry_run": bool(args.dry_run),
    }
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        mode = " (dry-run — nothing written)" if args.dry_run else ""
        sys.stdout.write(
            f"efficacy-eval: {len(verdicts)} review(s){mode}, "
            f"{len(not_due)} not due, {len(needs_triage)} need triage\n")
        for v in verdicts:
            delta = (f"{v['delta_pct']:+.1f}%" if isinstance(
                v.get("delta_pct"), (int, float)) else "n/a")
            sys.stdout.write(
                f"  {v['id']}: {v['verdict'].upper()} ({delta}) — "
                f"{v['reason']}"
                + (f" [consequence: {v['consequence']}]"
                   if v.get("consequence") not in (None, "none") else "")
                + "\n")
        for nd in not_due:
            sys.stdout.write(
                f"  {nd['id']}: not due ({nd['post_runs']}/{nd['needed']} "
                f"post-ship runs accrued)\n")
        for t in needs_triage:
            sys.stdout.write(f"  needs triage: {t}\n")
    # Verdicts — including REFUTED — are data, not errors.
    return 0


if __name__ == "__main__":
    sys.exit(main())
