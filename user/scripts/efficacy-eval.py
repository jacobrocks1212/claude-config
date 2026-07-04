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
