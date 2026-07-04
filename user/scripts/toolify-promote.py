#!/usr/bin/env python3
"""
toolify-promote.py — materializer + promotion ledger for toolify candidates.

toolify-auto-promotion. Stdlib-only. Sibling of the READ-ONLY miner
(`toolify-miner.py`) — ALL write paths of the toolification framework live
HERE, so the miner stays a pure reader (SPEC D1-B).

What it does (one candidate at a time, operator-driven — SPEC D3-A):

  --promote <candidate_id> --id <slug> --name "<title>" [--repo-root PATH]
      Verify the candidate is genuinely above the deterministic-only bar
      (RECOMPUTED, never trusted from a stale report), refuse ledger
      duplicates (D7-B: `promoted` is hard; `declined` re-promotes only with
      --force --reason, recorded), then materialize:
        1. shell `lazy-state.py --enqueue-adhoc --tier 2 --stub --at tail`
           (the SINGLE queue author — this script never edits queue.json);
        2. write the stub SPEC.md (canonical in-SPEC stub markers per D5, so
           the item halts at /spec Step 4.5 for the interactive baseline-lock
           — auto-draft is NOT approval);
        3. append the ledger entry LAST (failure-safe ordering: a SPEC-write
           failure leaves a routable queue item via the ADHOC_BRIEF route and
           NO ledger entry; a ledger-append failure re-runs into the loud
           duplicate-id enqueue refusal).
  --decline <candidate_id> --reason "<why>"
      Record a deliberate decline in the ledger (no repo writes).
  --status
      Fresh mine (or --from-json) ⨯ ledger join: each above-bar candidate is
      NEW / promoted → <feature_id> / declined (<reason>) / shipped.
  --acceptance-report
      Report-only (D8-A): totals, acceptance rate, cohort score/run-count
      distributions — ALWAYS naming sample sizes. The bar's constants in
      toolify-miner.py are only ever changed by a deliberate human edit.

The ledger is central + git-tracked (D6-A):
`docs/features/unified-pipeline-orchestrator/toolify-ledger.json`, keyed on
`candidate_id` (= sha256(signature)[:12], the miner's D2-A derivation).
`shipped` is DERIVED at read time from the target repo's
`docs/features/<feature_id>/COMPLETED.md` receipt — never stored, so it can
never contradict the receipt gate.

Usage:
    python3 toolify-promote.py --promote a3f9c21be04d \
        --id toolify-gate1-coverage-dance --name "Promote the Gate-1 dance" \
        [--repo-root ~/repos/claude-config] [--from-json report.json]
        [--force --reason "..."]
    python3 toolify-promote.py --decline 7c0d55e1aa02 --reason "artifact: ..."
    python3 toolify-promote.py --status
    python3 toolify-promote.py --acceptance-report

Exit codes: 0 success; 1 degraded partial failure (see stderr); 2 refusal /
user error (loud, side-effect-free).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
# claude-config repo root (…/user/scripts → …); the central ledger lives here
# even for cross-repo promotions (D6-A — one joined acceptance dataset).
_CONFIG_REPO_ROOT = _SCRIPTS_DIR.parents[1]
DEFAULT_LEDGER = (
    _CONFIG_REPO_ROOT / "docs" / "features" / "unified-pipeline-orchestrator"
    / "toolify-ledger.json"
)
DEFAULT_LOGS = Path(os.path.expanduser("~/.claude/projects"))

sys.path.insert(0, str(_SCRIPTS_DIR))
import lazy_core  # noqa: E402  (sibling module; _atomic_write is the write chokepoint)


def _load_miner():
    """Import the hyphenated miner module (test_toolify_miner.py's pattern)."""
    if "toolify_miner" in sys.modules:
        return sys.modules["toolify_miner"]
    spec = importlib.util.spec_from_file_location(
        "toolify_miner", str(_SCRIPTS_DIR / "toolify-miner.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["toolify_miner"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _die(msg: str) -> None:
    sys.stderr.write(f"ERROR: {msg}\n")
    raise SystemExit(2)


# ---------------------------------------------------------------------------
# The stub-SPEC template (SPEC D5) — the ONE place the canonical in-SPEC stub
# markers live. Two anchored forms `_spec_text_has_stub_marker` matches:
#   (a) the `**Status:**` line value contains "Draft (pre-Gemini)"
#   (b) a `>` blockquote line contains "Draft (pre-Gemini)"
# The /spec Phase-1 rewrite drops both, after which the queue's `"stub": true`
# flag alone is (correctly) read as baseline-locked and cleared by
# `lazy_core.clear_queue_stub`. The template hard-excludes everything
# decided-looking: no locked decisions, no research/phases/sentinel claims.
# ---------------------------------------------------------------------------

STUB_SPEC_TEMPLATE = """\
# {name} — Feature Specification (auto-drafted stub)

> Draft (pre-Gemini). Auto-drafted by `toolify-promote.py` from an above-bar
> `toolify-miner.py` candidate — the evidence below is mined; the direction is
> NOT locked. This stub halts at `/spec` Step 4.5 for the interactive
> baseline-lock: auto-draft is not approval.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** {date}
**Source:** toolify-promote.py --promote {candidate_id} (operator-named; mined evidence embedded)

**Depends on:** (none)

## Problem (mined evidence)

The session-log miner surfaced this recurring deterministic tool-call dance as
a toolification candidate above the deterministic-only bar (see
`docs/features/unified-pipeline-orchestrator/toolify-bar.md`):

| candidate_id | signature | occurrences | runs | est_tokens/occ | score | sample_tools | mined |
|--------------|-----------|-------------|------|----------------|-------|--------------|-------|
| `{candidate_id}` | `{signature}` | {occurrences} | {run_count} | {est_tokens_per_occurrence} | {score} | {sample_tools} | {date} |

Every occurrence is hand-re-derived from prose at roughly
{est_tokens_per_occurrence} tokens; promoting the dance to a deterministic
subcommand removes that recurring cost from the orchestrator loop.

## Direction (deliberately not locked)

Bar-checklist step 4 suggestion ONLY — a home for the promoted subcommand
(e.g. a `lazy-state.py` / sibling-script subcommand named after the dance) is
proposed as input to the `/spec` conversation, not decided by this stub.

## Open Questions (all direction unlocked)

- Subcommand name, home script, inputs, and structured return (bar checklist
  step 4); capture genuine forks as NEEDS_INPUT, not silent hard-codes.
- Which caller prose gets rewired (bar checklist step 6) and what coupled-pair
  mirroring that rewire owes.
- Whether the dance is still hot at implementation time (re-mine before /spec).
"""


def render_stub_spec(cand: dict, feature_id: str, name: str) -> str:
    """Render the stub SPEC for one candidate record (dict form)."""
    return STUB_SPEC_TEMPLATE.format(
        name=name,
        date=datetime.now().strftime("%Y-%m-%d"),
        candidate_id=cand["candidate_id"],
        signature=str(cand["signature"]).replace("|", "\\|"),
        occurrences=cand["occurrences"],
        run_count=cand["run_count"],
        est_tokens_per_occurrence=cand["est_tokens_per_occurrence"],
        score=cand["score"],
        sample_tools=", ".join(cand.get("sample_tools", ())),
    )


# ---------------------------------------------------------------------------
# Ledger (D6-A) — central, git-tracked, atomic writes only.
# ---------------------------------------------------------------------------

def load_ledger(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid ledger JSON at {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        _die(f"malformed ledger at {path}: expected {{'entries': {{...}}}}")
    return data


def save_ledger(path: Path, data: dict) -> None:
    lazy_core._atomic_write(Path(path), json.dumps(data, indent=2) + "\n")


def entry_is_shipped(entry: dict) -> bool:
    """`shipped` derived at READ time from the target repo's COMPLETED.md
    receipt — the single receipt-gated source of "done" (never stored)."""
    if entry.get("status") != "promoted":
        return False
    target_repo = entry.get("target_repo")
    feature_id = entry.get("feature_id")
    if not target_repo or not feature_id:
        return False
    return (Path(target_repo) / "docs" / "features" / feature_id
            / "COMPLETED.md").exists()


# ---------------------------------------------------------------------------
# Candidate resolution — fresh mine or a saved --from-json report; above_bar
# is RECOMPUTED from the miner's constants either way.
# ---------------------------------------------------------------------------

def resolve_candidates(logs: Path, from_json: Path | None) -> list[dict]:
    miner = _load_miner()
    rows: list[dict] = []
    if from_json is not None:
        try:
            raw = json.loads(Path(from_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _die(f"cannot read --from-json report {from_json}: {exc}")
        for r in raw:
            sig = r.get("signature", "")
            rows.append({
                "candidate_id": miner.candidate_id(sig),  # recomputed
                "signature": sig,
                "occurrences": int(r.get("occurrences", 0)),
                "run_count": int(r.get("run_count", 0)),
                "est_tokens_per_occurrence": int(
                    r.get("est_tokens_per_occurrence", 0)),
                "score": int(r.get("score", 0)),
                "deterministic": bool(r.get("deterministic", False)),
                # above_bar recomputed below — never trusted from the report.
                "sample_tools": list(r.get("sample_tools", [])),
            })
    else:
        for c in miner.mine(logs):
            rows.append({
                "candidate_id": c.candidate_id,
                "signature": c.signature,
                "occurrences": c.occurrences,
                "run_count": c.run_count,
                "est_tokens_per_occurrence": c.est_tokens_per_occurrence,
                "score": c.score,
                "deterministic": c.deterministic,
                "sample_tools": list(c.sample_tools),
            })
    for r in rows:
        r["above_bar"] = (
            r["deterministic"]
            and r["run_count"] >= miner.MIN_RUNS
            and r["score"] > miner.TOKEN_HEAVY_THRESHOLD
        )
    return rows


def find_candidate(rows: list[dict], cid: str) -> dict | None:
    for r in rows:
        if r["candidate_id"] == cid:
            return r
    return None


def failed_bar_predicates(cand: dict) -> list[str]:
    """Name each failed bar predicate (SPEC UX: judgment / run-count / score)."""
    miner = _load_miner()
    failed = []
    if not cand["deterministic"]:
        failed.append("judgment (sequence contains a judgment-marker step)")
    if cand["run_count"] < miner.MIN_RUNS:
        failed.append(
            f"run-count ({cand['run_count']} < MIN_RUNS {miner.MIN_RUNS})")
    if cand["score"] <= miner.TOKEN_HEAVY_THRESHOLD:
        failed.append(
            f"score ({cand['score']} <= TOKEN_HEAVY_THRESHOLD "
            f"{miner.TOKEN_HEAVY_THRESHOLD})")
    return failed


# ---------------------------------------------------------------------------
# Subcommand handlers.
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _write_stub_spec(path: Path, text: str) -> None:
    """Write the stub SPEC (module-level seam so tests can simulate a write
    failure without touching the promote flow)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lazy_core._atomic_write(path, text)


def _resolve_repo_root(args) -> Path:
    """--repo-root arg, else the cwd git toplevel, else the cwd (D9-A)."""
    if args.repo_root:
        return Path(args.repo_root).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except OSError:
        pass
    return Path.cwd().resolve()


def _format_prior(cid: str, entry: dict) -> str:
    return (
        f"prior ledger record for {cid}: status={entry.get('status')}, "
        f"feature_id={entry.get('feature_id')}, "
        f"decided_at={entry.get('decided_at')}, "
        f"reason={entry.get('reason')!r}"
    )


def do_promote(args) -> int:
    cid = args.promote
    # D10 — naming stays human: --id/--name are the operator's judgment inputs.
    missing = [flag for flag, val in (("--id", args.feature_id),
                                      ("--name", args.name)) if not val]
    if missing:
        _die(
            f"--promote requires {' and '.join(missing)} "
            f"(bar checklist step 3 — naming the dance stays human, D10; a "
            f"candidate you cannot name is a mining artifact)"
        )
    if not _SLUG_RE.match(args.feature_id):
        _die(f"invalid --id (must be kebab-case): {args.feature_id!r}")

    rows = resolve_candidates(args.logs, args.from_json)
    cand = find_candidate(rows, cid)
    if cand is None:
        source = "saved --from-json report" if args.from_json else "fresh mine"
        _die(
            f"unknown candidate_id {cid} — not present in the {source}; "
            f"re-mine (toolify-miner.py) or check the id"
        )
    if not cand["above_bar"]:
        _die(
            f"candidate {cid} is BELOW the deterministic-only bar — failed "
            f"predicate(s): " + "; ".join(failed_bar_predicates(cand))
            + ". --force never bypasses the bar (checklist step 2)."
        )

    ledger_data = load_ledger(args.ledger)
    entry = ledger_data["entries"].get(cid)
    forced = False
    if entry is not None:
        if entry.get("status") == "promoted":
            # D7-B: promoted is HARD — the stub/feature already exists.
            _die(
                "re-promoting a promoted candidate is refused (hard, D7-B — "
                "--force does not apply). " + _format_prior(cid, entry)
            )
        # declined → deliberate, reasoned reversal only.
        if not args.force:
            _die(
                "candidate was previously DECLINED; re-promote deliberately "
                "with --force --reason \"<why>\" (the override is recorded). "
                + _format_prior(cid, entry)
            )
        if not args.reason:
            _die("--force requires --reason (the reversal is recorded in the ledger)")
        forced = True

    repo_root = _resolve_repo_root(args)
    spec_md = repo_root / "docs" / "features" / args.feature_id / "SPEC.md"
    if spec_md.exists():
        _die(f"stub target already exists: {spec_md} — refusing to overwrite")

    # 1. Enqueue via the SINGLE queue author (D4-B flags; never a hand-edit).
    brief = (
        f"Toolify promotion of candidate {cid}: {args.name}. Deterministic "
        f"dance mined at {cand['occurrences']} occurrences across "
        f"{cand['run_count']} runs (score {cand['score']}). Evidence and a "
        f"non-locked direction suggestion are in this dir's stub SPEC.md; the "
        f"bar and promotion checklist live in "
        f"docs/features/unified-pipeline-orchestrator/toolify-bar.md."
    )
    enq = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"),
         "--enqueue-adhoc", "--id", args.feature_id, "--name", args.name,
         "--brief", brief, "--tier", "2", "--stub", "--at", "tail",
         "--repo-root", str(repo_root)],
        capture_output=True, text=True,
    )
    if enq.returncode != 0:
        # lazy-state.py's _die emits error JSON on STDOUT; surface both streams.
        detail = " ".join(s for s in (enq.stdout.strip(), enq.stderr.strip()) if s)
        _die(
            f"enqueue refused (lazy-state.py --enqueue-adhoc exit "
            f"{enq.returncode}): {detail}"
        )
    try:
        enq_result = json.loads(enq.stdout)
    except json.JSONDecodeError:
        enq_result = {}

    # 2. Stub SPEC (D5 markers). Failure here is DEGRADED, not wedged: the
    #    queue entry + ADHOC_BRIEF.md still route the item to /spec via the
    #    Step-4 brief path; the ledger stays unwritten (a re-run refuses
    #    loudly on the duplicate feature_id).
    try:
        _write_stub_spec(spec_md, render_stub_spec(cand, args.feature_id, args.name))
    except OSError as exc:
        sys.stderr.write(
            f"WARNING: stub SPEC write failed ({exc}) — DEGRADED promote: the "
            f"queue entry and ADHOC_BRIEF.md still route "
            f"'{args.feature_id}' to /spec (Step-4 brief path); NO ledger "
            f"entry was recorded. Fix the target dir and re-run --promote "
            f"(the duplicate-id enqueue refusal will name the leftover entry "
            f"to clean up or keep).\n"
        )
        return 1

    # 3. Ledger append LAST (D6-A).
    ledger_data["entries"][cid] = {
        "signature": cand["signature"],
        "status": "promoted",
        "feature_id": args.feature_id,
        "target_repo": str(repo_root),
        "decided_at": datetime.now().strftime("%Y-%m-%d"),
        "reason": args.reason or "",
        "evidence": {
            "occurrences": cand["occurrences"],
            "run_count": cand["run_count"],
            "est_tokens_per_occurrence": cand["est_tokens_per_occurrence"],
            "score": cand["score"],
            "sample_tools": list(cand.get("sample_tools", ())),
        },
        "forced": forced,
    }
    save_ledger(args.ledger, ledger_data)

    pos = enq_result.get("queue_position")
    qlen = enq_result.get("queue_length")
    print(
        f"Promoted candidate {cid} -> feature '{args.feature_id}' ({args.name})\n"
        f"  queue: docs/features/queue.json position {pos}/{qlen} "
        f"(tail, tier 2, stub: true — reorder with --reorder-queue if urgent)\n"
        f"  stub SPEC: {spec_md}\n"
        f"  ledger: {args.ledger} (status: promoted"
        + (", forced" if forced else "") + ")\n"
        f"  NOTE: the item halts at /spec Step 4.5 for the interactive "
        f"baseline-lock — auto-draft is not approval."
    )
    return 0


def do_decline(args) -> int:
    cid = args.decline
    if not args.reason:
        _die("--decline requires --reason (the ledger records WHY, D7-B)")
    rows = resolve_candidates(args.logs, args.from_json)
    cand = find_candidate(rows, cid)
    if cand is None:
        source = "saved --from-json report" if args.from_json else "fresh mine"
        _die(
            f"unknown candidate_id {cid} — not present in the {source}; "
            f"re-mine (toolify-miner.py) or check the id"
        )
    ledger_data = load_ledger(args.ledger)
    entry = ledger_data["entries"].get(cid)
    if entry is not None:
        _die("candidate already recorded — " + _format_prior(cid, entry))
    ledger_data["entries"][cid] = {
        "signature": cand["signature"],
        "status": "declined",
        "feature_id": None,
        "target_repo": None,
        "decided_at": datetime.now().strftime("%Y-%m-%d"),
        "reason": args.reason,
        "evidence": {
            "occurrences": cand["occurrences"],
            "run_count": cand["run_count"],
            "est_tokens_per_occurrence": cand["est_tokens_per_occurrence"],
            "score": cand["score"],
            "sample_tools": list(cand.get("sample_tools", ())),
        },
        "forced": False,
    }
    save_ledger(args.ledger, ledger_data)
    print(f"Declined candidate {cid} ({args.reason}) — recorded in {args.ledger}")
    return 0


def candidate_disposition(cand: dict, entries: dict) -> str:
    """One candidate's ledger disposition (shared by --status and the retro's
    report-only surface): NEW / promoted → id / declined (reason) / shipped."""
    e = entries.get(cand["candidate_id"])
    if e is None:
        return "NEW"
    if e.get("status") == "promoted":
        if entry_is_shipped(e):
            return f"shipped (-> {e.get('feature_id')})"
        return f"promoted -> {e.get('feature_id')}"
    return f"declined ({e.get('reason', '')})"


def do_status(args) -> int:
    rows = resolve_candidates(args.logs, args.from_json)
    entries = load_ledger(args.ledger)["entries"]
    print("| candidate_id | disposition | occurrences | runs | score | sample_tools |")
    print("|--------------|-------------|-------------|------|-------|--------------|")
    for r in rows:
        if not r["above_bar"]:
            continue
        disp = candidate_disposition(r, entries)
        tools = ", ".join(r.get("sample_tools", ()))
        print(
            f"| `{r['candidate_id']}` | {disp} | {r['occurrences']} | "
            f"{r['run_count']} | {r['score']} | {tools} |"
        )
    return 0


def do_acceptance_report(args) -> int:
    _die("--acceptance-report not implemented yet")
    return 2  # pragma: no cover


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materializer + promotion ledger for toolify candidates "
            "(the write-side sibling of the read-only toolify-miner.py)."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--promote", metavar="CANDIDATE_ID",
                      help="materialize one above-bar candidate (needs --id/--name)")
    mode.add_argument("--decline", metavar="CANDIDATE_ID",
                      help="record a deliberate decline (needs --reason)")
    mode.add_argument("--status", action="store_true",
                      help="fresh mine x ledger join (NEW/promoted/declined/shipped)")
    mode.add_argument("--acceptance-report", action="store_true",
                      dest="acceptance_report",
                      help="report-only acceptance-rate view (sample sizes named)")
    parser.add_argument("--id", dest="feature_id", default=None,
                        help="kebab-case feature id for --promote (operator-named, D10)")
    parser.add_argument("--name", default=None,
                        help="human feature title for --promote (operator-named, D10)")
    parser.add_argument("--repo-root", type=Path, default=None,
                        help=("target repo for the queue entry + stub SPEC "
                              "(default: cwd git toplevel; house convention, D9)"))
    parser.add_argument("--reason", default=None,
                        help="decline reason / forced re-promote justification")
    parser.add_argument("--force", action="store_true",
                        help=("re-promote a DECLINED candidate (recorded in the "
                              "ledger; never bypasses the bar or a promoted dup)"))
    parser.add_argument("--from-json", type=Path, default=None, dest="from_json",
                        help="resolve candidates from a saved render_json report "
                             "instead of a fresh mine (above_bar still recomputed)")
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOGS,
                        help="session-log corpus for the fresh mine "
                             "(default: ~/.claude/projects)")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                        help="promotion-ledger path (default: the central "
                             "git-tracked claude-config ledger)")
    args = parser.parse_args(argv)

    if args.promote:
        return do_promote(args)
    if args.decline:
        return do_decline(args)
    if args.status:
        return do_status(args)
    return do_acceptance_report(args)


if __name__ == "__main__":
    sys.exit(main())
