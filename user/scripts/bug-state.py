#!/usr/bin/env python3
"""
bug-state.py — Compute the next /lazy-bug or /lazy-bug-cloud state for autonomous bug triage.

Mirrors the state machine documented in the lazy-bug-family plan:
  user/scripts/plans/lazy-bug-family.md
  docs/specs/lazy-bug-family/PHASES.md (Phase 2)

Reads docs/bugs/queue.json, per-bug SPEC/PHASES/sentinels, and emits a JSON
object describing what to do next for the current bug. Used by:
  - The /lazy-bug thin wrapper (one sub-skill per invocation)
  - The /lazy-bug-batch orchestrator (autonomous loop)

Bug lifecycle:
  SPEC (Open) → investigate → PHASES → plan → execute-plan (In-progress)
             → retro (RETRO_DONE.md) → MCP/test validation (VALIDATED.md / skip / device-defer)
             → __mark_fixed__  (FIXED.md receipt → Status: Fixed + git mv → _archive/)

Ordering is HYBRID: docs/bugs/queue.json listed entries first (listed order),
then on-disk open bug dirs NOT in the queue, sorted by severity rank
(P0→P1→P2→Low) then **Discovered:** date ascending. Skips _archive/.

Status vocab (bare canonical token on the first **Status:** line):
  Open | Investigating | In-progress | Fixed | Won't-fix

Completion semantics:
  - Fixed + FIXED.md receipt → genuinely done (receipt-gated)
  - Fixed WITHOUT receipt → completion-unverified halt
  - Won't-fix → receipt-EXEMPT (retired without fix; skipped unconditionally)

Output schema (stdout JSON) — same keys as lazy-state.py:
{
  "feature_id":        "<bug-id>"      | null,
  "feature_name":      "<bug-title>"   | null,
  "spec_path":         "<absolute>"    | null,
  "current_step":      "<step name>"   | null,
  "sub_skill":         "<name>"        | null,
  "sub_skill_args":    "<args>"        | null,
  "terminal_reason":   null | "all-bugs-fixed" | "cloud-queue-exhausted"
                            | "device-queue-exhausted" | "blocked"
                            | "needs-input" | "completion-unverified"
                            | "queue-missing" | "all-remaining-deferred"
                            | "stale_upstream" | "scoped-id-not-found",
  "notify_message":    "<string>"      | null,
  "diagnostics":       [],
  "device_deferred_features": [],
  "operator_deferred": [],
}

Exit codes:
  0 — success (state computed, even if terminal)
  2 — malformed input (invalid YAML frontmatter, broken queue.json, etc.)

Usage:
    python3 bug-state.py [--cloud] [--real-device {yes,no,auto}]
                         [--repo-root <path>]
    python3 bug-state.py --test                     # run fixture smoke tests
    python3 bug-state.py --backfill-receipts        # write FIXED.md for archived bugs
    python3 bug-state.py --run-start                # write run marker (pipeline=bug); gates registry/counter side-effects
    python3 bug-state.py --run-end                  # delete marker + registry (run-scoped teardown)
    python3 bug-state.py --probe [--repeat-count]   # --probe/--repeat-count fold/advance marker-persisted counters when a run marker is present; --repeat-count-peek reads without advancing
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

# production-sentinel-writes-bypass-atomic-write (SPEC D3): explicit hard-exit
# PyYAML import, mirroring lazy-state.py's own posture — one posture, not two.
# (`import lazy_core` below already enforces this transitively at import time,
# since lazy_core.py hard-exits when PyYAML is absent; this explicit import
# makes bug-state.py self-documenting/self-contained about the same
# requirement, and gives `_write_yaml_sentinel`/`_write_yaml_blocked_sentinel`
# a bare module-level `yaml` name to call instead of a dead per-call fallback.)
try:
    import yaml
except ImportError:
    sys.stderr.write("bug-state.py requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)

# Insert this directory onto sys.path so `import lazy_core` resolves when
# bug-state.py is run directly from user/scripts/ OR via the ~/.claude/scripts
# symlink.
sys.path.insert(0, str(Path(__file__).parent))

import cli_surface
import lazy_core
from lazy_core import (
    _atomic_write,
    _die,
    _diag,
    clear_diagnostics,
    parse_sentinel,
    find_implementation_plans,
    find_retro_plans,
    _has_any_complete_plan,
    count_deliverables,
    remaining_unchecked_are_verification_only,
    # Stale-plan flip helpers (bug-pipeline-missing-stale-plan-flip) — the
    # workstation __flip_plan_complete_stale__ mirror of lazy-state.py Step 7a.
    # All shared in lazy_core; the cloud-saturation gate is feature-only.
    _plan_phase_set,
    _unchecked_wus_in_plan_scope,
    _all_wus_in_plan_scope,
    _phases_text_scoped_to,
    _plan_wu_checkbox_counts,
    _plan_unchecked_wus_are_verification_only,
    write_completed_receipt,
    has_completion_receipt,
    skip_waiver_refusal,
    repo_has_no_app_surface,
    phases_mcp_runtime_not_required,
    spec_status,
    commit_drift_verdict,
    observation_gap_promotable,
    _coerce_evidence_count,
)

# ---------------------------------------------------------------------------
# Module-level constants — SINGLE SOURCE OF TRUTH for string tokens asserted
# in both the test harness and the implementation.  The impl-agent MUST NOT
# redefine these; it reads them from here.
# ---------------------------------------------------------------------------

# terminal_reason tokens
TR_ALL_BUGS_FIXED = "all-bugs-fixed"
TR_BLOCKED = "blocked"
# noncanonical-blocker-filename-invisible-to-state-machine: a blocker written
# under a non-canonical name (invisible to the literal BLOCKED.md check) halts
# on this DISTINCT terminal. The VALUE is identical to the feature pipeline's
# lazy-state.py "blocked-misnamed" literal (parity is the whole point).
TR_BLOCKED_MISNAMED = "blocked-misnamed"
TR_NEEDS_INPUT = "needs-input"
TR_COMPLETION_UNVERIFIED = "completion-unverified"
TR_DEVICE_QUEUE_EXHAUSTED = "device-queue-exhausted"
TR_CLOUD_QUEUE_EXHAUSTED = "cloud-queue-exhausted"
TR_QUEUE_MISSING = "queue-missing"
TR_STALE_UPSTREAM = "stale_upstream"
TR_ALL_DEFERRED = "all-remaining-deferred"
TR_SCOPED_ID_NOT_FOUND = "scoped-id-not-found"
TR_QUEUE_EXHAUSTED_ALL_PARKED = "queue-exhausted-all-parked"

# -------------------------------------------------------------------------
# Scoped per-bug deferred terminal_reasons (bug-state-scoped-query-loses-
# deferred-bug-identity, Phase 1).
#
# When --bug-id (scope_bug_id) matches a queue entry that WOULD be skipped by
# one of the four "skipped-but-matched" branches (operator-deferred, cloud-
# saturated, device-saturated, parked), compute_state returns a SCOPED
# _bug_state carrying the bug's OWN identity (feature_id/feature_name/
# spec_path) + one of these per-bug terminals — instead of `continue`-ing into
# the global, null-identity terminal in the no-actionable block (which renders
# as "unknown" downstream in LAZY_QUEUE.md).
#
# These are NEW literals, distinct from the global unscoped terminals
# (TR_ALL_DEFERRED / TR_CLOUD_QUEUE_EXHAUSTED / TR_DEVICE_QUEUE_EXHAUSTED /
# TR_QUEUE_EXHAUSTED_ALL_PARKED) so the curated-stage mapping (Part 3,
# curated_stage._SIDE_STATE_BY_TERMINAL) maps each verbatim without overloading
# a global terminal with scoped fields. The UNSCOPED path stays byte-identical.
#
# Part 3 (curated_stage.py) maps each → its curated node:
#   operator-deferred            → Deferred
#   cloud-queue-exhausted-scoped → Deferred
#   device-queue-exhausted-scoped→ Deferred
#   blocked-scoped               → Blocked
#   needs-input-scoped           → Needs-input
# Part 2 (lazy-state.py) mirrors the analogous feature-side cloud/device
# scoped literals (the feature pipeline has NO operator DEFERRED.md branch).
TR_OPERATOR_DEFERRED_SCOPED = "operator-deferred"
TR_CLOUD_DEFERRED_SCOPED = "cloud-queue-exhausted-scoped"
TR_DEVICE_DEFERRED_SCOPED = "device-queue-exhausted-scoped"
TR_BLOCKED_SCOPED = "blocked-scoped"
TR_NEEDS_INPUT_SCOPED = "needs-input-scoped"
# Coupled-pair mirror of lazy-state.py's TR_COMPLETE_SCOPED
# (lazy-queue-doc-renders-bogus-rows-for-stale-complete-entries): a --bug-id
# scoped query matching an already-Fixed(+receipted)/Won't-fix entry returns
# its OWN identity + this terminal instead of falling through to a global
# terminal with no identity attached.
TR_FIXED_SCOPED = "bug-fixed-scoped"
# park-provisional-acceptance (coupled-pair mirror of lazy-state.py): the
# non-park halt on an unratified NEEDS_INPUT_PROVISIONAL.md + its scoped twin.
TR_NEEDS_RATIFICATION = "needs-ratification"
TR_NEEDS_RATIFICATION_SCOPED = "needs-ratification-scoped"

# sub_skill tokens for bug-specific actions
SKILL_INVESTIGATE = "spec-bug"             # root-cause investigation / spec-bug skill
SKILL_PLAN_BUG = "plan-bug"               # implementation planning for a concluded investigation (SPEC **Status:** Concluded, no PHASES.md)
SKILL_SPEC_PHASES = "spec-phases"          # break bug SPEC into PHASES
SKILL_WRITE_PLAN = "write-plan"            # write an implementation plan
SKILL_EXECUTE_PLAN = "execute-plan"        # execute a Ready plan
SKILL_RETRO = "retro-feature"             # DORMANT (retro unwired 2026-06) — kept for restore path  # noqa: F841
SKILL_MCP_TEST = "mcp-test"               # MCP / runtime validation
SKILL_MARK_FIXED = "__mark_fixed__"        # archive-on-fix pseudo-skill

# current_step strings (used both in the implementation and the test assertions)
STEP_BLOCKED = "Step 3: blocked"
STEP_BLOCKED_MISNAMED = "Step 3: mis-named blocker"
STEP_NEEDS_INPUT = "Step 3.5: needs-input"
STEP_INVESTIGATE = "Step 4: investigate bug"
# Distinct routing label for the plan-bug node (SPEC Concluded, no PHASES.md yet).
# plan-bug is a genuinely different routing step from spec-bug (it authors PHASES.md
# from the concluded investigation), so it MUST carry its own current_step: the
# HEAD-blind step_repeat_count oscillation counter is keyed on (feature_id,
# current_step) ONLY (sub_skill-blind), and a distinct routing node sharing the
# spec-bug label makes a legitimate spec-bug -> plan-bug forward transition
# indistinguishable from same-step oscillation (false LOOP-DETECTED). The feature
# pipeline already gives plan-feature its own step ("Step 6: plan feature (phases +
# plan)", lazy-state.py); this is the bug-pipeline mirror. See
# docs/bugs/plan-bug-reuses-investigate-step-inflates-loop-detector.
STEP_PLAN_BUG = "Step 5: plan bug from concluded investigation"
STEP_PHASES = "Step 6: spec phases"
STEP_WRITE_PLAN = "Step 7a: write plan"
STEP_EXECUTE_PLAN = "Step 7a: execute plan"
STEP_RETRO = "Step 8: retro phase"  # DORMANT (retro unwired 2026-06) — kept for restore path
STEP_MCP = "Step 9: run MCP tests"
STEP_MCP_SKIP = "Step 9: skip-mcp-test → validated"
# Provenance gate: a SKIP_MCP_TEST.md with granted_by: pipeline (self-granted)
# halts for operator confirmation instead of vacuously validating.
# Mirrors lazy-state.py's identical Step-9 step string.
STEP_MCP_SKIP_PIPELINE_GRANTED = "Step 9: pipeline-granted skip needs operator confirmation"
# Freshness gate: MCP_TEST_RESULTS.md whose validated_commit does not match the
# current HEAD must re-verify rather than auto-validate stale results.
# Mirrors lazy-state.py's identical Step-9 step string.
STEP_MCP_STALE_RESULTS = "Step 9: stale MCP results — re-verify"
STEP_MARK_FIXED = "Step 10: mark fixed"
STEP_CLOUD_DEFER_MCP = "Step 9: cloud defers MCP test"
STEP_DEVICE_DEFERRED_GUARD = "Step 9: device-deferred (no real device on this host)"
STEP_DEVICE_REOPEN = "Step 9: re-open device-deferred scenarios (real-device host)"
STEP_COMPLETION_UNVERIFIED = "Step 2: completion claimed without receipt"
STEP_STALE_UPSTREAM = "Step 2.9: stale-upstream"

# Scoped per-bug deferred current_step strings (bug-state-scoped-query-loses-
# deferred-bug-identity, Phase 1). Kept GENERIC so the curated stage resolves
# from the terminal_reason (which dominates), NOT the step.
STEP_OPERATOR_DEFERRED_SCOPED = "Operator-deferred (scoped)"
STEP_CLOUD_DEFERRED_SCOPED = "Cloud-deferred (scoped)"
STEP_DEVICE_DEFERRED_SCOPED = "Device-deferred (scoped)"
STEP_BLOCKED_PARKED_SCOPED = "Blocked, parked (scoped)"
STEP_NEEDS_INPUT_PARKED_SCOPED = "Needs-input, parked (scoped)"
# park-provisional-acceptance (coupled-pair mirror of lazy-state.py).
STEP_NEEDS_RATIFICATION = "Step 3.6: needs-ratification"
STEP_PROVISIONAL_PARKED_SCOPED = "Provisional, parked (scoped)"
STEP_FIXED_SCOPED = "Fixed (scoped)"

# Severity rank for on-disk ordering (lower number = higher priority)
_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "Low": 3}
_SEVERITY_DEFAULT = 99  # unrecognized / absent severity sorts last

# Bug status tokens
BUG_STATUS_OPEN = "Open"
BUG_STATUS_INVESTIGATING = "Investigating"
BUG_STATUS_IN_PROGRESS = "In-progress"
BUG_STATUS_FIXED = "Fixed"
BUG_STATUS_WONT_FIX = "Won't-fix"

# Terminal statuses — a bug with one of these (plus valid receipt/exemption)
# is genuinely done and should be skipped.
_BUG_DONE_STATUSES = {BUG_STATUS_FIXED, BUG_STATUS_WONT_FIX}

# Device env var (mirrors lazy-state.py)
REAL_DEVICE_ENV = "ALGOBOOTH_REAL_AUDIO_DEVICE"

# Module-level mutable list for device-deferred bugs (mirrors lazy-state.py's
# _DEVICE_DEFERRED).  Reset at the start of each compute_state() call.
_DEVICE_DEFERRED: list[str] = []

# Module-level mutable list for operator-deferred bugs (DEFERRED.md sentinel).
# Reset at the start of each compute_state() call, mirroring _DEVICE_DEFERRED.
_OPERATOR_DEFERRED: list[str] = []

# Park mode: when True (--park-needs-input and/or --park-blocked flag),
# NEEDS_INPUT.md and/or bug-local BLOCKED.md items are skipped (parked) instead
# of halting. The parked items accumulate in _PARKED.
# Reset at the start of each compute_state() call, mirroring _DEVICE_DEFERRED.
_PARKED: list = []
_PARK_MODE: bool = False

# park-provisional-acceptance (coupled-pair mirror of lazy-state.py): every
# NEEDS_INPUT_PROVISIONAL.md-bearing bug observed during this walk. Surfaced in
# the park-mode-only `provisional[]` probe key when non-empty (byte-identity
# discipline). Reset at each compute_state().
_PROVISIONAL: list = []

# queue-dependency-dag Phase 2 (coupled-pair mirror of lazy-state.py): the
# bugs the dep-gate held this invocation — [{id, missing: [<incomplete dep
# ids>]}], in walk order. Surfaced via the "dep_gated" probe key ONLY when
# non-empty (byte-identity discipline). Reset at each compute_state().
_DEP_GATED: list = []

# guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual,
# coupled-pair mirror of lazy-state.py — the marker/hook-events channel is
# SHARED between pipelines): the REPORT-ONLY "guards executed 0 times this
# run" advisory (lazy_core.guard_plane_heartbeat()'s verdict dict, or None).
# Surfaced via the "guard_plane_heartbeat" probe key ONLY when not None.
# Recomputed at the start of each compute_state(); NEVER gates any route.
_GUARD_PLANE_HEARTBEAT: dict | None = None


# ===========================================================================
# === IMPLEMENTATION (WU-2.2 impl-agent owns the bodies below) ==============
# ===========================================================================
#
# The impl-agent fills in these function bodies.  The test harness (below the
# "SMOKE FIXTURES" banner) calls compute_state() and asserts against the module
# constants defined above.  Signatures are fixed — do NOT change them.
#
# Note: _bug_state() mirrors lazy-state.py's _state() — it merges
# lazy_core._DIAGNOSTICS and _DEVICE_DEFERRED into the returned dict.
# ===========================================================================


def _bug_state(
    *,
    feature_id: str | None = None,
    feature_name: str | None = None,
    spec_path: str | None = None,
    current_step: str | None = None,
    sub_skill: str | None = None,
    sub_skill_args: str | None = None,
    terminal_reason: str | None = None,
    notify_message: str | None = None,
    diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    """Build a bug state dict (same schema as lazy-state.py's _state()).

    Merges lazy_core._DIAGNOSTICS and the module-level _DEVICE_DEFERRED list
    into the returned dict, exactly mirroring lazy-state.py's _state().
    """
    merged_diag = list(lazy_core._DIAGNOSTICS)
    if diagnostics:
        merged_diag.extend(diagnostics)
    out = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "spec_path": spec_path,
        "current_step": current_step,
        "sub_skill": sub_skill,
        "sub_skill_args": sub_skill_args,
        "terminal_reason": terminal_reason,
        "notify_message": notify_message,
        "diagnostics": merged_diag,
        # Structured list of bugs the device axis deferred this probe.  Always
        # present so /lazy-bug-status and orchestrators can surface lingering
        # In-progress device-deferrals deterministically.
        "device_deferred_features": list(_DEVICE_DEFERRED),
        # Structured list of bugs the operator explicitly deferred via DEFERRED.md.
        # Present so orchestrators can surface parked bugs without halting the queue.
        "operator_deferred": list(_OPERATOR_DEFERRED),
    }
    # CRITICAL INVARIANT: "parked" is ONLY included when _PARK_MODE is True.
    # When False the key must be entirely absent so default output (no flag) is
    # byte-identical to the pre-WU-1 Phase-4 baseline.
    if _PARK_MODE:
        out["parked"] = list(_PARKED)
    # park-provisional-acceptance (coupled-pair mirror of lazy-state.py, SPEC
    # D11): pending ratifications — park mode only AND only when non-empty, so
    # default and plain non-park output stays byte-identical.
    if _PARK_MODE and _PROVISIONAL:
        out["provisional"] = list(_PROVISIONAL)
    # queue-dependency-dag Phase 2 (D10, coupled-pair mirror of lazy-state.py):
    # the bugs the dep-gate HELD this probe. ONLY surfaced when non-empty so
    # default output (no `deps` fields anywhere) stays byte-identical.
    if _DEP_GATED:
        out["dep_gated"] = [dict(r) for r in _DEP_GATED]
    # guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual,
    # coupled-pair mirror of lazy-state.py): the REPORT-ONLY advisory,
    # surfaced ONLY when lazy_core.guard_plane_heartbeat() returned a
    # verdict. NEVER gates any route.
    if _GUARD_PLANE_HEARTBEAT is not None:
        out["guard_plane_heartbeat"] = dict(_GUARD_PLANE_HEARTBEAT)
    return out


def _scoped_skip_state(
    *,
    bug_id: str,
    bug_name: str,
    spec_dir: Path,
    current_step: str,
    terminal_reason: str,
    notify_message: str,
) -> dict[str, Any]:
    """Build a scoped, identity-preserving _bug_state for a --bug-id match that
    WOULD have been skipped by one of the four "skipped-but-matched" branches
    (operator-deferred / cloud-saturated / device-saturated / parked).

    bug-state-scoped-query-loses-deferred-bug-identity, Phase 1: the UNIFORM
    scoped-return shape used across all four scoped skip branches. Each branch's
    UNSCOPED path (scope_bug_id is None) stays byte-identical — this helper is
    reached ONLY on a scoped match. Modeled on the completion-unverified scoped
    return that already returns a scoped _bug_state from inside the queue loop.
    """
    return _bug_state(
        feature_id=bug_id,
        feature_name=bug_name,
        spec_path=str(spec_dir),
        current_step=current_step,
        terminal_reason=terminal_reason,
        notify_message=notify_message,
    )


def resolve_real_device(flag_value: str) -> bool:
    """Resolve whether the current host has a real audio output device.

    Mirrors lazy-state.py's resolve_real_device() exactly:
      - 'yes' → True
      - 'no'  → False
      - 'auto' → read $ALGOBOOTH_REAL_AUDIO_DEVICE; absent → False (conservative).
    """
    if flag_value == "yes":
        return True
    if flag_value == "no":
        return False
    # auto: read env var; absent means no-device (conservative default)
    raw = os.environ.get(REAL_DEVICE_ENV, "")
    return raw == "1" or raw.strip().lower() == "true"


def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a
    git repo / git is unavailable. Best-effort — the MCP-results freshness
    check is SKIPPED (legacy-permissive) when this returns None.

    Mirrors lazy-state.py's _current_head() exactly.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def load_bug_queue(
    repo_root: Path, *, today: "date | None" = None
) -> list[dict[str, Any]]:
    """Load docs/bugs/queue.json.  Returns [] if the file is absent.

    Hybrid ordering contract:
      1. Entries listed in queue.json appear first (in listed order).
      2. On-disk open bug dirs not in the queue follow, sorted by
         age-escalated severity rank (P0→P1→P2→Low, bug-queue-aging-backpressure
         D1-A/D3-A) then **Discovered:** date ascending.
      3. _archive/ is always skipped.

    The queue is OPTIONAL — no queue.json + no open bugs → all-bugs-fixed.
    Each returned entry is a dict with at minimum: id, name, spec_path (Path).
    ``today`` is caller-supplied for determinism (production omits it).
    """
    bugs_dir = repo_root / "docs" / "bugs"
    queue_path = bugs_dir / "queue.json"

    queued_entries: list[dict[str, Any]] = []
    queued_ids: set[str] = set()

    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _die(f"invalid bugs/queue.json: {exc}", queue_path)
            return []  # pragma: no cover
        items = data.get("queue", [])
        if not isinstance(items, list):
            _die("bugs/queue.json 'queue' field must be an array", queue_path)
            return []  # pragma: no cover

        # queue-dependency-dag Phase 1 (coupled-pair mirror of load_queue):
        # validate the optional per-entry `deps` field (shape + id regex +
        # reserved bug:/feature: prefixes + cycle detection) BEFORE the disk
        # merge. Dep-less queues are byte-identical; a broken declared graph
        # _die()s exit 2 like the other queue-schema violations above.
        lazy_core.validate_queue_deps(
            items, queue_path, queue_label="bugs/queue.json"
        )

        for entry in items:
            if not isinstance(entry, dict):
                continue
            bug_id = entry.get("id")
            name = entry.get("name")
            spec_subdir = entry.get("spec_dir", bug_id)
            if not bug_id or not name:
                # Malformed entry — diagnose HERE (not in the compute_state
                # walk loop): load_bug_queue normalizes entries before the
                # walk ever sees them, so this is the only place the drop is
                # observable. Mirrors lazy-state.py's walk-loop diagnostic
                # wording for queue entries missing id/name.
                missing = [k for k, v in (("id", bug_id), ("name", name)) if not v]
                _diag(
                    f"bug queue entry skipped — missing {', '.join(missing)} "
                    f"(entry: {str(entry)[:120]!r})"
                )
                continue
            spec_path = (bugs_dir / spec_subdir).resolve() if spec_subdir else None
            if spec_path is None or not spec_path.exists():
                # Dangling reference — skip with diagnostic
                _diag(
                    f"dangling bug queue entry: '{bug_id}' (spec_dir '{spec_subdir}') "
                    "does not resolve to an on-disk directory under docs/bugs/ — skipped."
                )
                continue
            if bug_id in queued_ids:
                _diag(f"duplicate bug queue id '{bug_id}' — second entry ignored.")
                continue
            queued_ids.add(bug_id)
            queued_entries.append({
                "id": bug_id,
                "name": name,
                "spec_path": spec_path,
                "severity": entry.get("severity"),
                "queue_entry": entry,
                # bug-queue-aging-backpressure D1-A/D2-A/D3-A: the merged-view
                # comparator (lazy_core.merged_priority) reads these three to
                # age-escalate and to fall back past an expired severity pin.
                # `spec_severity` is the SPEC's OWN **Severity:** line — distinct
                # from `severity` above (the queue.json OVERRIDE, which may be
                # a deliberate null pin) — see merged_priority's docstring.
                "discovered": bug_discovered(spec_path / "SPEC.md"),
                "spec_severity": bug_severity(spec_path / "SPEC.md"),
                "pinned_at": entry.get("pinned_at"),
                "pinned_until": entry.get("pinned_until"),
            })

    # On-disk open bug dirs not in queue, sorted by severity rank then Discovered date
    on_disk = _find_open_bug_dirs(bugs_dir, queued_ids, today=today)
    on_disk_entries: list[dict[str, Any]] = []
    for bug_dir in on_disk:
        spec_path = bug_dir / "SPEC.md"
        # Use directory name as id, derive name from SPEC.md title or fallback to id
        bug_id = bug_dir.name
        name = bug_id  # fallback
        if spec_path.exists():
            try:
                for line in spec_path.read_text(encoding="utf-8").splitlines():
                    m = re.match(r"^#\s+(.+?)\s*$", line)
                    if m:
                        name = m.group(1)
                        break
            except OSError:
                pass
        _on_disk_severity = bug_severity(bug_dir / "SPEC.md")
        on_disk_entries.append({
            "id": bug_id,
            "name": name,
            "spec_path": bug_dir.resolve(),
            "severity": _on_disk_severity,
            "queue_entry": None,
            # An unqueued dir has no queue-level pin — `spec_severity` mirrors
            # `severity` (both read the SPEC directly) so merged_priority's
            # bug branch treats it uniformly.
            "discovered": bug_discovered(bug_dir / "SPEC.md"),
            "spec_severity": _on_disk_severity,
            "pinned_at": None,
            "pinned_until": None,
        })

    return queued_entries + on_disk_entries


def bug_severity(spec_path: Path) -> str | None:
    """Return the **Severity:** value from a bug SPEC.md, or None if absent.

    Mirrors lazy_core.spec_status()'s **Status:** parsing approach, but reads
    the **Severity:** header line instead.
    """
    if not spec_path.exists():
        return None
    try:
        for line in spec_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\*\*Severity:\*\*\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return None


def bug_discovered(spec_path: Path) -> str | None:
    """Return the **Discovered:** value from a bug SPEC.md, or None if absent.

    Mirrors the **Status:** parsing approach from lazy_core.spec_status(),
    but reads the **Discovered:** header line instead.
    """
    if not spec_path.exists():
        return None
    try:
        for line in spec_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\*\*Discovered:\*\*\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return None


def _find_open_bug_dirs(
    bugs_dir: Path, queued_ids: set[str], *, today: "date | None" = None
) -> list[Path]:
    """Return on-disk open bug dirs NOT already in queued_ids.

    Searches bugs_dir (one level deep), skips _archive/, and skips any dir
    whose SPEC.md **Status:** is a genuinely-done terminal state.  Returns
    dirs sorted by AGE-ESCALATED severity rank (bug-queue-aging-backpressure
    D1-A/D3-A — mirrors lazy_core.merged_priority's bug branch so autodiscovered
    ordering agrees with the merged view) then Discovered date ascending.
    ``today`` is caller-supplied for determinism (production omits it).

    Done-status semantics:
      - Won't-fix → always skipped (receipt-exempt, retired without fix).
      - Fixed WITH a valid FIXED.md receipt → skipped (genuinely done).
      - Fixed WITHOUT a valid FIXED.md receipt → NOT skipped; returned so
        compute_state's queue-walk receipt gate can fire TR_COMPLETION_UNVERIFIED.
        A diagnostic is emitted to surface the bypass to the operator.

    Note: the first parameter is the bugs_dir (docs/bugs/), NOT the repo root.
    """
    if not bugs_dir.exists():
        return []

    candidates: list[tuple[int, str, Path]] = []
    for child in bugs_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            # Skip _archive/ and any other underscore-prefixed dirs
            continue
        if child.name in queued_ids:
            # Already covered by the queue
            continue
        spec_md = child / "SPEC.md"
        if not spec_md.exists():
            continue
        # Read status and apply done-status filtering with receipt awareness.
        status = spec_status(child)
        if status == BUG_STATUS_WONT_FIX:
            # Receipt-exempt: retired without fix — always skip.
            continue
        if status == BUG_STATUS_FIXED:
            if has_completion_receipt(child, filename="FIXED.md"):
                # Genuinely done: Fixed with a valid FIXED.md receipt — skip.
                continue
            # Fixed WITHOUT receipt: do NOT silently skip.  Surface this dir so
            # the queue-walk receipt gate in compute_state fires
            # TR_COMPLETION_UNVERIFIED — same as the queued-bug path.
            _diag(
                f"unqueued Fixed-without-receipt dir surfaced for receipt gate: "
                f"'{child.name}' — SPEC marks Fixed but no valid FIXED.md receipt found. "
                "Routing to completion gate (completion-unverified)."
            )
            # Fall through to append into candidates below.
        # Sort key: age-escalated severity rank (ascending priority) + discovered
        # date string (ascending). age_escalated_rank no-ops when there's no
        # real severity signal (sev_rank == _SEVERITY_DEFAULT) or no parseable
        # Discovered date — fail-open, matches lazy_core.merged_priority.
        sev = bug_severity(spec_md)
        sev_rank = _SEVERITY_RANK.get(sev, _SEVERITY_DEFAULT) if sev else _SEVERITY_DEFAULT
        disc = bug_discovered(spec_md)
        if sev_rank != _SEVERITY_DEFAULT:
            sev_rank = lazy_core.age_escalated_rank(sev_rank, disc, today)
        candidates.append((sev_rank, disc or "9999-99-99", child))

    candidates.sort(key=lambda t: (t[0], t[1]))
    return [c[2] for c in candidates]


def _phases_effectively_complete(spec_dir: Path) -> bool:
    """Return True iff a bug has no remaining actionable implementation work.

    Mirror of lazy-state.py::_phases_effectively_complete. This is the
    precondition the Step 2 cloud/device-saturated skips used to encode via the
    presence of RETRO_DONE.md (which only ever existed once phases were complete
    and a retro round ran). With retro unwired, RETRO_DONE no longer exists, so
    we test the underlying property directly: a bug is "past implementation"
    when its PHASES.md has zero unchecked deliverables, OR every implementation
    plan is Complete and only verification-only rows remain. A bug still
    mid-implementation must NOT be skipped here — it has actionable work.
    """
    phases_file = spec_dir / "PHASES.md"
    if not phases_file.exists():
        return False
    phases_text = phases_file.read_text(encoding="utf-8")
    unchecked, _checked = count_deliverables(phases_text)
    if unchecked == 0:
        return True
    if (
        not find_implementation_plans(spec_dir)
        and _has_any_complete_plan(spec_dir)
        and remaining_unchecked_are_verification_only(phases_text)
    ):
        return True
    return False


def compute_state(
    repo_root: Path,
    cloud: bool,
    real_device: bool = True,
    scope_bug_id: str | None = None,
    park_needs_input: bool = False,
    park_blocked: bool = False,
    park_provisional: bool = False,
    per_feature_cycle_cap: int | None = None,
    strict_research_halt: bool = False,
) -> dict[str, Any]:
    """Walk the bug lifecycle and return the next action as a JSON-serializable dict.

    Mirrors lazy-state.py's compute_state() structure:
      - Resets lazy_core._DIAGNOSTICS and _DEVICE_DEFERRED at entry.
      - Returns _bug_state(...) with the same JSON contract.

    Bug-specific differences from the feature pipeline:
      - No Step 4.5 stub-spec, Step 4.6 realign, or Step 5 research gate.
      - Step 4: if SPEC.md present with Open/Investigating status but no
        PHASES.md → dispatch spec-bug (investigation).
      - Step 10: __mark_fixed__ (archive-on-fix) instead of __mark_complete__.
      - Receipt file is FIXED.md (kind: fixed).
      - Won't-fix is receipt-exempt.
      - Ordering is hybrid (queue.json + severity fallback) not ROADMAP-based.

    park_needs_input: OPT-IN flag. When True, a bug carrying NEEDS_INPUT.md is
      SKIPPED (parked) rather than halting the queue. The parked item is reported
      in the 'parked[]' output array. Without this flag, behavior is byte-identical
      to the pre-WU-1 Phase-4 baseline (needs-input halt fires, 'parked' key absent).
    park_blocked: OPT-IN flag (companion to park_needs_input). When True, a bug
      carrying a bug-local BLOCKED.md is SKIPPED (parked) rather than halting the
      queue with terminal_reason='blocked'; the item re-enters once the block is
      resolved. When every remaining bug is parked, the honest
      'queue-exhausted-all-parked' terminal fires instead of 'all-bugs-fixed'.
      Without this flag, BLOCKED still halts (byte-identical). Mirrors lazy-state.py
      (SPEC park-mode-halts-on-blocked, Phase 2 / Open-Q1 bug parity).
    per_feature_cycle_cap: PARITY-ONLY param (feature-budget-guard-and-skip-ahead
      Phase 2). The per-feature budget guard is a FEATURE-pipeline mechanic; the bug
      pipeline does NOT trip in v1. This param exists ONLY so the bug-state argparse
      mirrors lazy-state's `--per-feature-cycle-cap` parse surface (audited by
      lazy_parity_audit.py) — matching the `--type bug` benign-parse precedent. It
      is accepted and ignored here (no behavior change; output byte-identical).
    strict_research_halt: PARITY-ONLY param (feature-budget-guard-and-skip-ahead
      Phase 3). Dependency-aware skip-ahead past a research-pending/BLOCKED head is
      a FEATURE-pipeline mechanic — the bug pipeline has NO research gate, so the
      flag is a no-op here. This param exists ONLY so the bug-state argparse mirrors
      lazy-state's `--strict-research-halt` parse surface (audited by
      lazy_parity_audit.py), matching the `--per-feature-cycle-cap` benign-parse
      precedent. Accepted and ignored (no behavior change; output byte-identical).
    """
    # per_feature_cycle_cap / strict_research_halt are accepted for argparse parity
    # only; the bug pipeline has no budget-guard trip and no research gate in v1.
    # Referenced here to silence unused-arg lints.
    _ = per_feature_cycle_cap
    _ = strict_research_halt
    # Cloud has no audio device — force no-device like lazy-state.py does.
    if cloud:
        real_device = False

    # Reset diagnostics and deferred lists for this invocation.
    clear_diagnostics()
    _DEVICE_DEFERRED.clear()
    _OPERATOR_DEFERRED.clear()
    # Park mode: set the module global from the param so _bug_state() can gate
    # the "parked" key on it.  _PARKED accumulates items skipped this invocation.
    global _PARK_MODE, _PARKED, _DEP_GATED, _PROVISIONAL
    _PARK_MODE = park_needs_input or park_blocked
    _PARKED.clear()
    # park-provisional-acceptance (SPEC D1, coupled-pair mirror): the flag is a
    # strict modifier of park_needs_input; the CLI enforces the pairing and this
    # guard backstops direct compute_state callers/tests.
    if park_provisional and not park_needs_input:
        _die("--park-provisional requires --park-needs-input (SPEC D1)")
    _PROVISIONAL.clear()
    # queue-dependency-dag Phase 2: reset the dep-gate hold list; the lazily-
    # built queued id → dir map resolves deps through normalized spec_paths
    # (built only when an entry actually carries `deps` — zero cost otherwise).
    _DEP_GATED = []
    _dep_dir_map: dict | None = None
    repo_root = repo_root.resolve()

    # guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual,
    # coupled-pair mirror of lazy-state.py): a REPORT-ONLY, never-halting
    # "guards executed 0 times this run" advisory. Computed once per probe;
    # folded into the output ONLY when lazy_core returns a verdict.
    global _GUARD_PLANE_HEARTBEAT
    _GUARD_PLANE_HEARTBEAT = lazy_core.guard_plane_heartbeat()

    # Load the hybrid-ordered bug queue.
    # Track whether queue.json is entirely absent (distinct from "present but empty"),
    # so we can emit TR_QUEUE_MISSING instead of TR_ALL_BUGS_FIXED.
    _queue_path = repo_root / "docs" / "bugs" / "queue.json"
    _queue_json_absent = not _queue_path.exists()
    queue = load_bug_queue(repo_root)

    # Walk the queue to find the current (first actionable) bug.
    current = None
    device_saturated_skipped: list[str] = []
    # cloud_saturated_skipped: bugs that have RETRO_DONE.md + DEFERRED_NON_CLOUD.md
    # but no VALIDATED.md.  Cloud cannot run MCP tests, so we skip them here and
    # emit TR_CLOUD_QUEUE_EXHAUSTED if nothing else is actionable (mirrors
    # lazy-state.py lines ~848, ~912-919, ~975-982).
    cloud_saturated_skipped: list[str] = []
    # Tracks whether the --bug-id scope arg matched ANY raw entry id in the queue
    # (set BEFORE any completion/cloud/device skip would continue past a matched entry).
    # If scope is set but no entry matched, we emit TR_SCOPED_ID_NOT_FOUND instead
    # of TR_ALL_BUGS_FIXED so callers can distinguish "queue exhausted" from "typo".
    scope_id_seen: bool = False

    for entry in queue:
        bug_id = entry.get("id")
        bug_name = entry.get("name")
        spec_dir: Path = entry.get("spec_path")

        if not bug_id or not bug_name or not spec_dir:
            # Emit a diagnostic naming the missing fields so the operator can
            # fix the malformed queue entry.  Matches the WU-7 deliverable.
            missing = [f for f, v in [("id", bug_id), ("name", bug_name), ("spec_dir", spec_dir)] if not v]
            _diag(
                f"queue entry skipped — missing {', '.join(missing)} "
                f"(entry: {str(entry)[:120]!r})"
            )
            continue

        # --bug-id scoping: when set, process ONLY the matching queue entry.
        # scope_id_seen is set here — BEFORE any completion/cloud/device skip
        # would continue past a matched entry — so a matched-but-skipped entry
        # still counts as "seen" (not reported as scoped-id-not-found).
        if scope_bug_id is not None:
            if str(bug_id) != str(scope_bug_id):
                continue
            scope_id_seen = True

        # -----------------------------------------------------------------------
        # Completion gate: Fixed + receipt → genuinely done (skip).
        # Fixed WITHOUT receipt → halt (completion-unverified).
        # Won't-fix → receipt-exempt; treat as done (skip unconditionally).
        # -----------------------------------------------------------------------
        status = spec_status(spec_dir)

        if status == BUG_STATUS_WONT_FIX:
            # Receipt-exempt: retired without fix. Skip.
            # Coupled-pair mirror of lazy-state.py's TR_COMPLETE_SCOPED
            # (lazy-queue-doc-renders-bogus-rows-for-stale-complete-entries): a
            # scoped match on an already-done bug must return ITS OWN identity,
            # not `continue` into a global terminal with no identity attached.
            if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                return _scoped_skip_state(
                    bug_id=bug_id,
                    bug_name=bug_name,
                    spec_dir=spec_dir,
                    current_step=STEP_FIXED_SCOPED,
                    terminal_reason=TR_FIXED_SCOPED,
                    notify_message=f"{bug_name}: already resolved (Won't-fix).",
                )
            continue

        if status == BUG_STATUS_FIXED:
            # Receipt required for Fixed bugs.
            if has_completion_receipt(spec_dir, filename="FIXED.md"):
                # Genuinely done. Same scoped-identity mirror as above.
                if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                    return _scoped_skip_state(
                        bug_id=bug_id,
                        bug_name=bug_name,
                        spec_dir=spec_dir,
                        current_step=STEP_FIXED_SCOPED,
                        terminal_reason=TR_FIXED_SCOPED,
                        notify_message=f"{bug_name}: already fixed.",
                    )
                continue
            # Claimed Fixed WITHOUT a FIXED.md receipt.
            return _bug_state(
                feature_id=bug_id,
                feature_name=bug_name,
                spec_path=str(spec_dir),
                current_step=STEP_COMPLETION_UNVERIFIED,
                terminal_reason=TR_COMPLETION_UNVERIFIED,
                notify_message=(
                    f"{bug_name}: SPEC marks this Fixed but no FIXED.md receipt "
                    "exists — it was flipped OUTSIDE the validation gate. "
                    "Reconcile: reopen to In-progress for real validation, or run "
                    "bug-state.py --backfill-receipts to grandfather it."
                ),
            )

        # -----------------------------------------------------------------------
        # Cloud-saturated skip (mirrors lazy-state.py).
        # A bug past implementation that has DEFERRED_NON_CLOUD.md but no
        # VALIDATED.md cannot be certified on a cloud host (cloud cannot run MCP
        # tests).  Skip it so the queue advances; TR_CLOUD_QUEUE_EXHAUSTED is
        # emitted if no other bug is actionable. (Retro unwired: the old
        # RETRO_DONE.md precondition is replaced by _phases_effectively_complete()
        # — the underlying "past implementation" property RETRO_DONE proxied. A
        # bug still mid-implementation must NOT be skipped.)
        # -----------------------------------------------------------------------
        if cloud:
            deferred = (spec_dir / "DEFERRED_NON_CLOUD.md").exists()
            validated = (spec_dir / "VALIDATED.md").exists()
            if deferred and not validated and _phases_effectively_complete(spec_dir):
                # Scoped-match identity preservation (Phase 1) — see the
                # operator-deferred branch below for the canonical comment.
                if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                    return _scoped_skip_state(
                        bug_id=bug_id,
                        bug_name=bug_name,
                        spec_dir=spec_dir,
                        current_step=STEP_CLOUD_DEFERRED_SCOPED,
                        terminal_reason=TR_CLOUD_DEFERRED_SCOPED,
                        notify_message=(
                            f"{bug_name}: cloud-saturated (DEFERRED_NON_CLOUD.md, "
                            "no VALIDATED.md). Scoped query returns its identity; "
                            "awaiting workstation /lazy-bug validation."
                        ),
                    )
                cloud_saturated_skipped.append(bug_name)
                _diag(
                    f"cloud-saturated skipped: {bug_name} — DEFERRED_NON_CLOUD.md "
                    "present, no VALIDATED.md; awaiting workstation /lazy-bug."
                )
                continue

        # -----------------------------------------------------------------------
        # Device-saturated skip (mirrors lazy-state.py's device-axis logic).
        # (Retro unwired: _phases_effectively_complete() replaces the old
        # RETRO_DONE.md precondition.)
        # -----------------------------------------------------------------------
        if not real_device:
            device_deferred = (spec_dir / "DEFERRED_REQUIRES_DEVICE.md").exists()
            validated = (spec_dir / "VALIDATED.md").exists()
            if device_deferred and not validated and _phases_effectively_complete(spec_dir):
                meta = parse_sentinel(spec_dir / "DEFERRED_REQUIRES_DEVICE.md") or {}
                scen = meta.get("deferred_scenarios") or []
                scen_str = ", ".join(str(s) for s in scen) if scen else "(unspecified)"
                # Scoped-match identity preservation (Phase 1) — see the
                # operator-deferred branch below for the canonical comment.
                if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                    return _scoped_skip_state(
                        bug_id=bug_id,
                        bug_name=bug_name,
                        spec_dir=spec_dir,
                        current_step=STEP_DEVICE_DEFERRED_SCOPED,
                        terminal_reason=TR_DEVICE_DEFERRED_SCOPED,
                        notify_message=(
                            f"{bug_name}: device-saturated — real-device-only "
                            f"assertions deferred [{scen_str}] "
                            "(DEFERRED_REQUIRES_DEVICE.md). Scoped query returns "
                            "its identity; re-opens on a real-device /lazy-bug host."
                        ),
                    )
                device_saturated_skipped.append(bug_name)
                _DEVICE_DEFERRED.append(bug_name)
                _diag(
                    f"device-saturated skipped: {bug_name} — real-device-only "
                    f"assertions deferred [{scen_str}] (DEFERRED_REQUIRES_DEVICE.md); "
                    "re-opens on a real-device /lazy-bug host."
                )
                continue

        # -----------------------------------------------------------------------
        # host-capability-declaration-for-gated-features Phase 6 (bug-pipeline
        # PARITY). Mirror the feature pipeline's requires_host: PARSE + the
        # unknown-id FAIL-FAST. A bug whose SPEC/queue entry declares a
        # requires_host: id NOT in the closed registry has no probe and could
        # never be reported present on ANY host, so deferring it would strand the
        # bug in silent, infinite queue starvation. It is a loud, immediate
        # validation failure: a canonical BLOCKED.md (blocker_kind:
        # unknown-host-capability) naming the offending id(s) + the registry's
        # known ids, halting on terminal_reason="blocked".
        #
        # PARITY SCOPE (justified divergence, registered in
        # lazy-parity-manifest.json): the PARSE (lazy_core.parse_requires_host) +
        # the fail-fast are mirrored identically. The feature pipeline's
        # capability-MISS DEFER (DEFERRED_REQUIRES_HOST.md skip + the
        # host-capability-saturated terminal) is NOT mirrored here — that branch
        # is queue-selection/curation-shaped on the feature side; the bug pipeline
        # does not gate runtime validation by an N-capability axis in v1 (it has
        # only the single device axis above). The SHARED lazy_core helpers do not
        # diverge — bug-state.py simply does not expose the capability-miss branch.
        # -----------------------------------------------------------------------
        try:
            _hc_spec_text = (spec_dir / "SPEC.md").read_text(encoding="utf-8") \
                if (spec_dir / "SPEC.md").exists() else ""
        except OSError:
            _hc_spec_text = ""
        required_host = lazy_core.parse_requires_host(_hc_spec_text, entry)
        if required_host:
            unknown = lazy_core.unknown_capability_ids(required_host)
            if unknown:
                blocked_file = spec_dir / "BLOCKED.md"
                if not blocked_file.exists():
                    body = lazy_core.format_unknown_host_capability_blocker(
                        bug_id, unknown
                    )
                    _write_yaml_blocked_sentinel(
                        blocked_file,
                        feature_id=bug_id,
                        phase="Host-capability validation",
                        blocker_kind="unknown-host-capability",
                        blocked_at=lazy_core.utc_now_iso(),
                        retry_count=0,
                        body=body,
                    )
                _diag(
                    f"unknown-host-capability: {bug_name} declares unregistered "
                    f"requires_host: id(s) {sorted(unknown)!r} — wrote BLOCKED.md "
                    f"(blocker_kind: unknown-host-capability). Fix the typo or "
                    f"register a probe."
                )
                return _bug_state(
                    feature_id=bug_id,
                    feature_name=bug_name,
                    spec_path=str(spec_dir),
                    current_step=STEP_BLOCKED,
                    terminal_reason=TR_BLOCKED,
                    notify_message=(
                        f"BLOCKED: {bug_name} — unregistered requires_host: "
                        f"capability id(s) {', '.join(sorted(unknown))}. "
                        "Awaiting input."
                    ),
                )

        # -----------------------------------------------------------------------
        # Operator-deferred skip: DEFERRED.md present → operator parked this bug.
        # Skip and continue to the next candidate so the queue keeps moving.
        # Re-include by deleting DEFERRED.md.
        # -----------------------------------------------------------------------
        deferred_md = spec_dir / "DEFERRED.md"
        if deferred_md.exists():
            # Scoped-match identity preservation (bug-state-scoped-query-loses-
            # deferred-bug-identity, Phase 1): when --bug-id targets THIS bug,
            # return a scoped _bug_state carrying its identity + a per-bug
            # deferred terminal — instead of `continue`-ing into the global
            # null-identity TR_ALL_DEFERRED terminal (which renders "unknown"
            # downstream). UNSCOPED behavior (scope_bug_id is None) is unchanged.
            if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                return _scoped_skip_state(
                    bug_id=bug_id,
                    bug_name=bug_name,
                    spec_dir=spec_dir,
                    current_step=STEP_OPERATOR_DEFERRED_SCOPED,
                    terminal_reason=TR_OPERATOR_DEFERRED_SCOPED,
                    notify_message=(
                        f"{bug_name}: operator-deferred (DEFERRED.md). Scoped "
                        "query returns its identity; re-include by deleting "
                        "DEFERRED.md."
                    ),
                )
            _OPERATOR_DEFERRED.append(bug_name)
            meta = parse_sentinel(deferred_md) or {}
            reason = meta.get("reason") or "(no reason recorded)"
            _diag(
                f"operator-deferred skipped: {bug_name} — DEFERRED.md "
                f"(reason: {reason}); re-include by deleting DEFERRED.md."
            )
            continue

        # Park-mode (BLOCKED): if --park-blocked is active and this bug has a
        # BLOCKED.md, skip (park) it instead of halting the queue with
        # terminal_reason="blocked". Evaluated BEFORE the NEEDS_INPUT park branch
        # so a bug carrying BOTH sentinels parks exactly ONCE (this branch
        # `continue`s). Mirror of lazy-state.py (SPEC park-mode-halts-on-blocked).
        if park_blocked and (spec_dir / "BLOCKED.md").exists():
            # Scoped-match identity preservation (Phase 1): a scoped --bug-id on
            # a parked-blocked bug returns a scoped BLOCKED-family state naming
            # the bug, instead of `continue`-ing into queue-exhausted-all-parked.
            if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                return _scoped_skip_state(
                    bug_id=bug_id,
                    bug_name=bug_name,
                    spec_dir=spec_dir,
                    current_step=STEP_BLOCKED_PARKED_SCOPED,
                    terminal_reason=TR_BLOCKED_SCOPED,
                    notify_message=(
                        f"{bug_name}: bug-local BLOCKED.md, parked (park mode). "
                        "Scoped query returns its identity; re-enters when resolved."
                    ),
                )
            _PARKED.append(lazy_core.build_parked_entry(bug_id, spec_dir / "BLOCKED.md"))
            lazy_core.notify_event(
                "park", f"{bug_name} parked (BLOCKED.md)", str(repo_root),
                pipeline="bug", item_id=bug_id, detail="bug-local BLOCKED.md",
            )
            _diag(
                f"parked: {bug_name} — bug-local BLOCKED.md; skipped (park mode). "
                "Re-enters when resolved."
            )
            continue

        # Park-mode (mis-named blocker): parity with the canonical BLOCKED park
        # branch above for a non-canonical stray (noncanonical-blocker-filename-
        # invisible-to-state-machine). Mirror of lazy-state.py's feature-pipeline
        # park parity. When --park-blocked is active, canonical BLOCKED.md is
        # ABSENT, and the shared detector finds a stray, park it the same way (it
        # re-enters once renamed/neutralized).
        if park_blocked and not (spec_dir / "BLOCKED.md").exists():
            _stray = lazy_core.detect_noncanonical_blocker(spec_dir)
            if _stray is not None:
                # Scoped-match identity preservation (Phase 1): a mis-named
                # blocker is a BLOCKED-family park — same scoped treatment.
                if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                    return _scoped_skip_state(
                        bug_id=bug_id,
                        bug_name=bug_name,
                        spec_dir=spec_dir,
                        current_step=STEP_BLOCKED_PARKED_SCOPED,
                        terminal_reason=TR_BLOCKED_SCOPED,
                        notify_message=(
                            f"{bug_name}: bug-local mis-named blocker "
                            f"'{_stray.name}', parked (park mode). Scoped query "
                            "returns its identity; re-enters when renamed to "
                            "BLOCKED.md or neutralized."
                        ),
                    )
                _PARKED.append(lazy_core.build_parked_entry(bug_id, _stray))
                lazy_core.notify_event(
                    "park", f"{bug_name} parked (mis-named blocker)", str(repo_root),
                    pipeline="bug", item_id=bug_id,
                    detail=f"stray blocker: {_stray.name}",
                )
                _diag(
                    f"parked: {bug_name} — bug-local mis-named blocker "
                    f"'{_stray.name}'; skipped (park mode). Re-enters when "
                    "renamed to BLOCKED.md or neutralized."
                )
                continue

        # Park-mode: if --park-needs-input is active and this bug has an
        # unresolved NEEDS_INPUT.md, skip (park) it instead of halting the queue.
        # The item re-enters automatically once NEEDS_INPUT.md is resolved/renamed.
        # BLOCKED.md retains precedence when --park-blocked is NOT set: a bug
        # carrying BOTH BLOCKED.md and NEEDS_INPUT.md must still halt as "blocked",
        # not be silently parked. (When --park-blocked IS set, the BLOCKED park
        # branch above already parked + continued, so this guard is moot.)
        if (
            park_needs_input
            and (spec_dir / "NEEDS_INPUT.md").exists()
            and not (spec_dir / "BLOCKED.md").exists()
        ):
            # park-provisional-acceptance (SPEC D2, coupled-pair mirror of
            # lazy-state.py): under --park-provisional a provisional-ELIGIBLE
            # sentinel routes __provisional_accept__ instead of parking.
            # Checked BEFORE the scoped-identity return; ineligible → parked
            # exactly as before with the reason breadcrumbed.
            if park_provisional:
                _pp_eligible, _pp_reason = lazy_core.provisional_eligibility(
                    spec_dir / "NEEDS_INPUT.md"
                )
                if _pp_eligible:
                    return _bug_state(
                        feature_id=bug_id,
                        feature_name=bug_name,
                        spec_path=str(spec_dir),
                        current_step="Step 3.5: needs-input (provisional accept)",
                        sub_skill="__provisional_accept__",
                        sub_skill_args=str(spec_dir),
                    )
                _diag(
                    f"provisional-ineligible: {bug_name} — {_pp_reason}; "
                    "parking instead (fail-closed)."
                )
            # Scoped-match identity preservation (Phase 1): a scoped --bug-id on
            # a parked-needs-input bug returns a scoped NEEDS-INPUT-family state.
            if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                return _scoped_skip_state(
                    bug_id=bug_id,
                    bug_name=bug_name,
                    spec_dir=spec_dir,
                    current_step=STEP_NEEDS_INPUT_PARKED_SCOPED,
                    terminal_reason=TR_NEEDS_INPUT_SCOPED,
                    notify_message=(
                        f"{bug_name}: unresolved NEEDS_INPUT.md, parked (park "
                        "mode). Scoped query returns its identity; re-enters when "
                        "resolved."
                    ),
                )
            _PARKED.append(lazy_core.build_parked_entry(bug_id, spec_dir / "NEEDS_INPUT.md"))
            lazy_core.notify_event(
                "park", f"{bug_name} parked (NEEDS_INPUT.md)", str(repo_root),
                pipeline="bug", item_id=bug_id, detail="unresolved NEEDS_INPUT.md",
            )
            _diag(
                f"parked: {bug_name} — unresolved NEEDS_INPUT.md; skipped (park mode). "
                "Re-enters when resolved."
            )
            continue

        # park-provisional-acceptance (SPEC D5/D6 layer a, coupled-pair mirror
        # of lazy-state.py): a bug carrying an unratified
        # NEEDS_INPUT_PROVISIONAL.md in PARK MODE. Record it in the park-mode-
        # only provisional[] surface; once VALIDATED.md lands (the only
        # remaining route would be __mark_fixed__, which must not fire on an
        # unratified provisional), PARK it (sentinel_kind: provisional) so the
        # flush surfaces ratification; otherwise fall through (workable).
        if park_needs_input and (spec_dir / lazy_core.PROVISIONAL_SENTINEL).exists():
            _prov_entry = lazy_core.build_parked_entry(
                bug_id, spec_dir / lazy_core.PROVISIONAL_SENTINEL
            )
            if not any(p.get("id") == bug_id for p in _PROVISIONAL):
                _PROVISIONAL.append(_prov_entry)
            if (spec_dir / "VALIDATED.md").exists():
                if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):
                    return _scoped_skip_state(
                        bug_id=bug_id,
                        bug_name=bug_name,
                        spec_dir=spec_dir,
                        current_step=STEP_PROVISIONAL_PARKED_SCOPED,
                        terminal_reason=TR_NEEDS_RATIFICATION_SCOPED,
                        notify_message=(
                            f"{bug_name}: implementation + validation done; "
                            f"unratified {lazy_core.PROVISIONAL_SENTINEL} parks "
                            "the fix (park mode). Ratify or redirect at the flush."
                        ),
                    )
                _PARKED.append(_prov_entry)
                lazy_core.notify_event(
                    "park", f"{bug_name} parked (unratified provisional)",
                    str(repo_root), pipeline="bug", item_id=bug_id,
                    detail="validated but awaiting ratification — parks at completion",
                )
                _diag(
                    f"parked: {bug_name} — validated but awaiting ratification "
                    f"of {lazy_core.PROVISIONAL_SENTINEL}; __mark_fixed__ "
                    "deferred to the flush (park mode)."
                )
                continue

        # queue-dependency-dag Phase 2: the dep-gate (D2-A; coupled-pair
        # mirror of lazy-state.py's). A bug whose queue `deps` contain an id
        # that is not receipt-gated-complete (D3: **Status:** Fixed + a valid
        # FIXED.md — resolution consults docs/bugs/<id>/ THEN
        # docs/bugs/_archive/<id>/, the D9 archive-aware divergence) is HELD
        # and the walk advances to the dependency. A dangling or Won't-fix dep
        # is the D4 fail-fast (canonical BLOCKED.md, blocker_kind:
        # unknown-dependency). This is the FINAL check before dispatch (the
        # bug pipeline has no skip-ahead branch — justified divergence).
        # Entries WITHOUT `deps` never enter this block — byte-identical.
        #
        # queue-dependency-dag Phase 4 (D5): probe-time DRIFT diagnostic —
        # gated on the raw entry CARRYING a `deps` key. Compares the queue set
        # against the SPEC's parsed hard-dep set (reusing _hc_spec_text — the
        # walk's existing per-entry SPEC read; zero additional file I/O).
        # Lint-grade: a mismatch warns, never halts. Mirror of lazy-state.py.
        _dg_raw_entry = entry.get("queue_entry")
        if isinstance(_dg_raw_entry, dict) and "deps" in _dg_raw_entry:
            _drift_spec_hard = sorted({
                d["feature_id"]
                for d in lazy_core.parse_dep_block(_hc_spec_text)
                if d.get("kind") == "hard"
            })
            _drift_queue = sorted(set(lazy_core.dep_ids(_dg_raw_entry)))
            if _drift_spec_hard != _drift_queue:
                _diag(
                    f"dep-drift: '{bug_id}' queue deps {_drift_queue!r} != "
                    f"SPEC hard deps {_drift_spec_hard!r} — re-run "
                    f"`--sync-deps --id {bug_id}` to re-project "
                    f"(lint-grade warning; not a halt)."
                )
        _dg_deps = lazy_core.dep_ids(entry.get("queue_entry"))
        if _dg_deps:
            if _dep_dir_map is None:
                _dep_dir_map = {
                    e.get("id"): e.get("spec_path")
                    for e in queue
                    if isinstance(e, dict) and e.get("id") and e.get("spec_path")
                }
            _dg_missing: list[str] = []
            _dg_bad: tuple[str, str] | None = None
            for _dg_dep in _dg_deps:
                _dg_status = lazy_core.dep_completion_status(
                    _dg_dep, repo_root, pipeline="bug",
                    id_dir_map=_dep_dir_map,
                )
                if _dg_status == "complete":
                    continue
                if _dg_status == "incomplete":
                    _dg_missing.append(_dg_dep)
                    continue
                # missing / unsatisfiable-* → D4 fail-fast on the FIRST bad dep.
                _dg_bad = (_dg_dep, _dg_status)
                break
            if _dg_bad is not None:
                blocked_file = spec_dir / "BLOCKED.md"
                if not blocked_file.exists():
                    body = lazy_core.format_unknown_dependency_blocker(
                        bug_id, _dg_bad[0], _dg_bad[1],
                        sorted(_dep_dir_map or {}),
                    )
                    _write_yaml_blocked_sentinel(
                        blocked_file,
                        feature_id=bug_id,
                        phase="Dependency validation",
                        blocker_kind="unknown-dependency",
                        blocked_at=lazy_core.utc_now_iso(),
                        retry_count=0,
                        body=body,
                    )
                _diag(
                    f"unknown-dependency: {bug_name} declares queue dep "
                    f"'{_dg_bad[0]}' which classified {_dg_bad[1]!r} — wrote "
                    f"BLOCKED.md (blocker_kind: unknown-dependency). Fix the "
                    f"SPEC dep-block + --sync-deps, or drop the dep."
                )
                return _bug_state(
                    feature_id=bug_id,
                    feature_name=bug_name,
                    spec_path=str(spec_dir),
                    current_step=STEP_BLOCKED,
                    terminal_reason=TR_BLOCKED,
                    notify_message=(
                        f"BLOCKED: {bug_name} — queue dependency "
                        f"'{_dg_bad[0]}' is {_dg_bad[1]} (unknown-dependency). "
                        "Awaiting input."
                    ),
                )
            if _dg_missing:
                _DEP_GATED.append({"id": bug_id, "missing": _dg_missing})
                _diag(
                    f"dep-gate: '{bug_id}' held — dep(s) "
                    f"{', '.join(repr(m) for m in _dg_missing)} not Fixed "
                    f"(receipt-gated); advancing."
                )
                continue

        # This bug is actionable — stop scanning.
        current = {
            "id": bug_id,
            "name": bug_name,
            "spec_path": spec_dir,
        }
        break

    # -----------------------------------------------------------------------
    # No actionable bug found.
    # -----------------------------------------------------------------------
    if current is None:
        # Cloud-saturated: cloud host has DEFERRED_NON_CLOUD bugs awaiting workstation
        # MCP validation.  Emit TR_CLOUD_QUEUE_EXHAUSTED so the orchestrator knows to
        # pause until a workstation /lazy-bug run validates and writes VALIDATED.md.
        # Mirrors lazy-state.py lines ~975-982.
        if cloud and cloud_saturated_skipped:
            return _bug_state(
                terminal_reason=TR_CLOUD_QUEUE_EXHAUSTED,
                notify_message=(
                    f"Cloud queue exhausted — {len(cloud_saturated_skipped)} bug(s) "
                    "carry DEFERRED_NON_CLOUD.md awaiting workstation /lazy-bug validation."
                ),
            )
        if (not real_device) and device_saturated_skipped:
            return _bug_state(
                terminal_reason=TR_DEVICE_QUEUE_EXHAUSTED,
                notify_message=(
                    f"Device queue exhausted — {len(device_saturated_skipped)} bug(s) "
                    "carry real-device-only assertions deferred to a real-device "
                    "/lazy-bug host."
                ),
            )
        if _OPERATOR_DEFERRED:
            # All remaining bugs were explicitly parked by the operator via DEFERRED.md.
            # Report this as a distinct terminal rather than all-bugs-fixed so the
            # orchestrator knows the queue isn't empty — just paused by the operator.
            return _bug_state(
                terminal_reason=TR_ALL_DEFERRED,
                current_step="All remaining bugs are operator-deferred",
                notify_message=(
                    f"All remaining bugs are operator-deferred — "
                    f"{len(_OPERATOR_DEFERRED)} bug(s) parked via DEFERRED.md. "
                    "Re-include by deleting DEFERRED.md in each bug dir."
                ),
            )
        # queue.json is entirely absent (no bugs dir or no queue file) — this is
        # distinct from "queue present but all bugs done" (which is all-bugs-fixed).
        # TR_QUEUE_MISSING signals that the queue file was never created, so the
        # operator should run --enqueue-adhoc or create docs/bugs/queue.json manually.
        if _queue_json_absent:
            return _bug_state(
                terminal_reason=TR_QUEUE_MISSING,
                notify_message=(
                    "docs/bugs/queue.json is absent — no bug queue exists yet. "
                    "Run bug-state.py --enqueue-adhoc to create it, or create "
                    "docs/bugs/queue.json manually."
                ),
            )
        # scoped-id-not-found: --bug-id was given but matched no queue entry.
        # Placed here (after all other specific terminals) because when the scope
        # id is a typo none of the skip-lists will have populated.
        if scope_bug_id is not None and not scope_id_seen:
            return _bug_state(
                terminal_reason=TR_SCOPED_ID_NOT_FOUND,
                notify_message=(
                    f"--bug-id '{scope_bug_id}' matched no entry in the bug queue — "
                    "check the id (typo?) or that the bug is queued. No cycle was dispatched."
                ),
            )
        # queue-dependency-dag D4 (coupled-pair mirror of lazy-state.py):
        # honest all-dep-gated terminal. The walk exhausted and at least one
        # bug was HELD on an incomplete declared dependency this probe — a
        # clean, sanctioned stop (holds re-open as their deps are fixed +
        # archived), NOT all-bugs-fixed. Placed AFTER the specific global
        # terminals above and BEFORE the all-parked fallback (a dep-gated bug
        # is held for a more specific reason than "parked"); the flush names
        # each held bug and its incomplete deps. Gated on a hold having
        # occurred — dep-less queues are byte-identical.
        if _DEP_GATED:
            _dg_lines = "; ".join(
                f"{r['id']} waiting on {', '.join(r['missing'])}"
                for r in _DEP_GATED
            )
            return _bug_state(
                terminal_reason="queue-exhausted-dependency-gated",
                notify_message=(
                    f"Queue exhausted — {len(_DEP_GATED)} bug(s) "
                    f"dependency-gated: {_dg_lines}. Each re-opens "
                    "automatically once its dependencies are Fixed with a "
                    "receipt."
                ),
            )
        # Honest all-parked terminal (SPEC D3): when every remaining bug was
        # parked this probe (NEEDS_INPUT and/or BLOCKED under park mode) so current
        # is None with a non-empty _PARKED, return a distinct terminal — NOT
        # all-bugs-fixed, which would be a false completion. Placed AFTER the
        # specific global terminals above (cloud/device/operator-deferred/
        # queue-missing/scoped-id keep their precedence) and BEFORE all-bugs-fixed.
        # Distinct from TR_ALL_DEFERRED (operator DEFERRED.md), which is its own
        # terminal handled above.
        if _PARKED:
            return _bug_state(
                terminal_reason=TR_QUEUE_EXHAUSTED_ALL_PARKED,
                notify_message=(
                    f"Queue exhausted — {len(_PARKED)} bug(s) parked "
                    "(blocked/needs-input); surfaced at the end-of-run flush."
                ),
            )
        return _bug_state(
            terminal_reason=TR_ALL_BUGS_FIXED,
            notify_message="ALL BUGS FIXED — no open bugs remain.",
        )

    # -----------------------------------------------------------------------
    # Walk the lifecycle for the selected bug.
    # -----------------------------------------------------------------------
    bug_id = current["id"]
    bug_name = current["name"]
    spec_dir: Path = current["spec_path"]
    spec_dir_str = str(spec_dir)

    common = {
        "feature_id": bug_id,
        "feature_name": bug_name,
        "spec_path": spec_dir_str,
    }

    # Step 2.9: STALE_UPSTREAM.md — upstream work item diverged; halt before
    # normal gates so the human can absorb or reject the change.
    if lazy_core.read_stale_upstream(spec_dir) is not None:
        return _bug_state(
            **common,
            current_step=STEP_STALE_UPSTREAM,
            terminal_reason=TR_STALE_UPSTREAM,
            notify_message=f"STALE UPSTREAM: {bug_name} — work item changed upstream. Absorb or reject.",
        )

    # Step 3: BLOCKED.md
    blocked_file = spec_dir / "BLOCKED.md"
    if blocked_file.exists():
        meta = parse_sentinel(blocked_file) or {}
        phase = meta.get("phase", "unknown")
        notify_message = f"BLOCKED: {bug_name} — {phase}. Awaiting input."
        # Validation-escalation payload (Phase 11 WU-1a) — exact mirror of
        # lazy-state.py's Step-3 blocked terminal: blocker_kind mcp-validation
        # at retry_count >= 2 gains `validation_escalation: true` plus the
        # shared lazy_core.VALIDATION_ESCALATION_SUFFIX on notify_message. The
        # key is added ONLY in the escalation case (post-hoc, mirroring the
        # _PARK_MODE "parked" invariant) so non-escalated output — including
        # every existing retry_count: 0 fixture — stays byte-identical.
        escalated = lazy_core.validation_escalation(meta)
        if escalated:
            notify_message += lazy_core.VALIDATION_ESCALATION_SUFFIX
        state = _bug_state(
            **common,
            current_step=STEP_BLOCKED,
            terminal_reason=TR_BLOCKED,
            notify_message=notify_message,
        )
        if escalated:
            state["validation_escalation"] = True
        return state

    # Step 3 (cont.): mis-named blocker (noncanonical-blocker-filename-invisible-
    # to-state-machine). EXACT mirror of lazy-state.py's feature-pipeline wiring.
    # A blocker under a non-canonical name (e.g. BLOCKED_2026-06-09-foo.md or a
    # lowercase blocked.md) is invisible to the literal BLOCKED.md check above, so
    # the state machine would loop the item back into the same wall. The shared
    # detector returns None when canonical BLOCKED.md is present (the check above
    # already returned in that case), so this fires only when canonical is ABSENT.
    # The terminal_reason VALUE is identical to the feature pipeline's.
    stray_blocked = lazy_core.detect_noncanonical_blocker(spec_dir)
    if stray_blocked is not None:
        return _bug_state(
            **common,
            current_step=STEP_BLOCKED_MISNAMED,
            terminal_reason=TR_BLOCKED_MISNAMED,
            notify_message=(
                f"MIS-NAMED BLOCKER: {bug_name} — found '{stray_blocked.name}', "
                "which the state machine cannot see (only the canonical 'BLOCKED.md' "
                "halts the pipeline). Rename it to 'BLOCKED.md' or neutralize it."
            ),
        )

    # Step 3.5: NEEDS_INPUT.md
    needs_input_file = spec_dir / "NEEDS_INPUT.md"
    if needs_input_file.exists():
        meta = parse_sentinel(needs_input_file) or {}
        writer = meta.get("written_by", "<unknown>")
        return _bug_state(
            **common,
            current_step=STEP_NEEDS_INPUT,
            terminal_reason=TR_NEEDS_INPUT,
            notify_message=(
                f"NEEDS INPUT: {bug_name} — {writer} halted on an ambiguous decision."
            ),
        )

    # Step 3.6: NEEDS_INPUT_PROVISIONAL.md (park-provisional-acceptance, SPEC
    # D5 — coupled-pair mirror of lazy-state.py). A non-park probe halts on the
    # unratified provisional so the operator ratifies or redirects before any
    # completion; park-mode probes treat the file as workable (the walk-loop
    # branch recorded/parked it). Ordering: AFTER the NEEDS_INPUT.md check — a
    # NEW decision outranks a pending ratification.
    provisional_file = spec_dir / lazy_core.PROVISIONAL_SENTINEL
    if provisional_file.exists() and not park_needs_input:
        prov_meta = parse_sentinel(provisional_file) or {}
        prov_writer = prov_meta.get("written_by", "<unknown>")
        return _bug_state(
            **common,
            current_step=STEP_NEEDS_RATIFICATION,
            terminal_reason=TR_NEEDS_RATIFICATION,
            notify_message=(
                f"NEEDS RATIFICATION: {bug_name} — decision(s) originally "
                f"surfaced by {prov_writer} were provisionally auto-accepted on "
                "recommendation (--park-provisional). Ratify or redirect before "
                "this bug can be marked fixed."
            ),
        )

    # Step 4: SPEC.md present but no PHASES.md → investigation or planning dispatch.
    # (SPEC.md is guaranteed to exist at this point: load_bug_queue only returns
    # dirs that have one.)
    # If the SPEC status is "Concluded", the investigation is done and PHASES.md has not
    # been authored yet — route to plan-bug so it can create PHASES.md from the concluded
    # spec.  Any other status (e.g. "Investigating", "Open") → spec-bug to continue the
    # investigation.  This avoids an infinite spec-bug loop after a concluded investigation.
    phases_file = spec_dir / "PHASES.md"
    if not phases_file.exists():
        _status = spec_status(spec_dir)
        if _status == "Concluded":
            # Investigation concluded; hand off to plan-bug to author PHASES.md.
            # DISTINCT step label (STEP_PLAN_BUG, not the reused STEP_INVESTIGATE) so
            # the spec-bug -> plan-bug forward transition visibly advances current_step
            # and is not mis-counted as same-step oscillation by step_repeat_count.
            return _bug_state(
                **common,
                current_step=STEP_PLAN_BUG,
                sub_skill=SKILL_PLAN_BUG,
                sub_skill_args=f"{spec_dir_str}/SPEC.md",
            )
        return _bug_state(
            **common,
            current_step=STEP_INVESTIGATE,
            sub_skill=SKILL_INVESTIGATE,
            sub_skill_args=f"{spec_dir_str}/SPEC.md",
        )

    phases_text = phases_file.read_text(encoding="utf-8")
    unchecked, checked = count_deliverables(phases_text)

    # Step 6: PHASES.md exists but no implementation plan yet.
    # (In the bug pipeline we skip the /spec-phases intermediate — the
    # investigate step produces PHASES.md directly.  If PHASES.md is absent we
    # already dispatched spec-bug above.  If PHASES.md exists but no plan → write-plan.)
    if unchecked > 0:
        plans = find_implementation_plans(spec_dir)
        if not plans and _has_any_complete_plan(spec_dir) and \
                remaining_unchecked_are_verification_only(phases_text):
            # All implementation plans are Complete; remaining PHASES.md
            # unchecked rows are verification-only (e.g. per-phase Runtime
            # Verification / MCP-assertion subsections ticked at MCP test
            # time).  Fall through to Step 8 (retro) → Step 9 (/mcp-test),
            # which is the dispatch that actually ticks them.  Without this
            # carve-out the script loops: find_implementation_plans filters
            # out Complete plans → plans is empty → write-plan dispatched
            # forever.  Mirrors the identical bypass in lazy-state.py.
            pass
        elif not plans:
            return _bug_state(
                **common,
                current_step=STEP_WRITE_PLAN,
                sub_skill=SKILL_WRITE_PLAN,
                sub_skill_args=f"{spec_dir_str}/PHASES.md",
            )
        else:
            # A Ready/In-progress plan exists — execute it, UNLESS it is stale.
            plan = plans[0]
            # Stale-plan gate — workstation mirror of lazy-state.py Step 7a
            # (bug-pipeline-missing-stale-plan-flip). When every WU referenced by
            # this plan's phases: scope is already checked ([x]) in PHASES.md (or
            # the only in-scope unchecked remainder is verification-only), the plan
            # is STALE: its work is done but its frontmatter was never flipped to
            # Complete. Dispatching /execute-plan then burns an Opus cycle whose
            # ONLY job is the frontmatter flip, and LOOPS if a subagent turn ends
            # before that flip. Emit __flip_plan_complete_stale__ (applied inline
            # by the orchestrator — lazy-bug-batch/SKILL.md already documents it)
            # instead. The cloud-saturation gate is feature/cloud-specific
            # (_plan_cloud_saturated is lazy-state.py-local) and is intentionally
            # NOT mirrored here — bug-state.py has no cloud-saturated flip.
            plan_phase_set = _plan_phase_set(plan)
            if plan_phase_set:
                in_scope_unchecked = _unchecked_wus_in_plan_scope(
                    phases_text, plan_phase_set
                )
                # Empty-PHASES-scope guard (mirror of the feature-side
                # decomposition-part fix): an empty in-scope unchecked list is
                # AMBIGUOUS — either every referenced WU is already [x] (stale)
                # OR the plan's phases: scope resolves to ZERO PHASES.md rows
                # (scope UNDEFINED, not "done"). Disambiguate via the TOTAL
                # (checked + unchecked) in-scope row count; a zero-row scope
                # falls back to the plan's OWN per-WU checkboxes so a
                # decomposition part with unchecked plan-body WUs still executes.
                scope_total = _all_wus_in_plan_scope(phases_text, plan_phase_set)
                if scope_total:
                    scoped_text = _phases_text_scoped_to(
                        phases_text, plan_phase_set
                    )
                    finalize_stale = (
                        not in_scope_unchecked
                        or remaining_unchecked_are_verification_only(scoped_text)
                    )
                else:
                    plan_text = plan.read_text(encoding="utf-8", errors="replace")
                    wu_unchecked, wu_checked = _plan_wu_checkbox_counts(plan_text)
                    finalize_stale = bool(wu_checked) and (
                        wu_unchecked == 0
                        or _plan_unchecked_wus_are_verification_only(plan_text)
                    )
                if finalize_stale:
                    return _bug_state(
                        **common,
                        current_step=(
                            "Step 7a: flip plan Complete (stale — all referenced "
                            "implementation deliverables already checked)"
                        ),
                        sub_skill="__flip_plan_complete_stale__",
                        sub_skill_args=str(plan),
                    )
            # plan-structure-authoring-gate Phase 4 pickup backstop (bug-
            # pipeline parity mirror of lazy-state.py Step 7a): validate the
            # plan part STRUCTURALLY (in-process, via validate-plan.py's
            # run_structural_checks) at first /execute-plan routing. A FRESH
            # plan (zero ticked WUs) carrying a structural ERROR refuses the
            # route (BLOCKED.md, blocker_kind: plan-structural-invalid); a
            # plan already mid-execution (>=1 ticked WU) is WARN-only and
            # falls through — never blocks in-flight work.
            _pstruct = lazy_core.plan_structural_backstop(plan)
            if not _pstruct["ok"]:
                blocked_file = spec_dir / "BLOCKED.md"
                if not blocked_file.exists():
                    body = lazy_core.format_plan_structural_blocker(
                        str(plan), _pstruct["findings"],
                    )
                    _write_yaml_blocked_sentinel(
                        blocked_file,
                        feature_id=bug_id,
                        phase="Plan structural validation",
                        blocker_kind="plan-structural-invalid",
                        blocked_at=lazy_core.utc_now_iso(),
                        retry_count=0,
                        body=body,
                    )
                _diag(
                    f"plan-structural-invalid: {plan} fails structural "
                    f"validation with zero ticked WUs (fresh) — wrote "
                    f"BLOCKED.md (blocker_kind: plan-structural-invalid)."
                )
                return _bug_state(
                    feature_id=bug_id,
                    feature_name=bug_name,
                    spec_path=spec_dir_str,
                    current_step="Step 7a: blocked (plan structurally invalid)",
                    terminal_reason="blocked",
                    notify_message=(
                        f"BLOCKED: {bug_name} — plan {plan.name} fails "
                        f"structural validation (plan-structural-invalid). "
                        f"Awaiting input."
                    ),
                )
            return _bug_state(
                **common,
                current_step=STEP_EXECUTE_PLAN,
                sub_skill=SKILL_EXECUTE_PLAN,
                sub_skill_args=str(plan),
            )

    # All PHASES.md deliverables are checked.

    # RETRO UNWIRED (operator decision, 2026-06) — bug-pipeline parity with
    # lazy-state.py. The Step 8 /retro phase has been removed: once all phases
    # are complete the pipeline routes DIRECTLY to the Step 9 MCP gate, never to
    # retro-feature. Git history is the restore path; /retro-feature SKILL stays
    # in place. The now-inert retro_staleness() backstop in lazy_core.apply_pseudo
    # is left dormant (harmless; returns None when RETRO_DONE.md is absent, which
    # it now always is for new bugs) — nothing gates on it anymore.

    # Step 9-pre: device-deferral re-open / guard.
    # Mirrors lazy-state.py's exact Step 9-pre logic.
    device_deferred_file = spec_dir / "DEFERRED_REQUIRES_DEVICE.md"
    if device_deferred_file.exists():
        if real_device:
            # Real-device host: re-open the deferred scenarios for certification.
            meta = parse_sentinel(device_deferred_file) or {}
            scenarios = meta.get("deferred_scenarios") or []
            scen_str = (
                ", ".join(str(s) for s in scenarios)
                if scenarios else "(see DEFERRED_REQUIRES_DEVICE.md)"
            )
            return _bug_state(
                **common,
                current_step=STEP_DEVICE_REOPEN,
                sub_skill=SKILL_MCP_TEST,
                sub_skill_args=(
                    f"re-validate {bug_name} deferred real-device assertions "
                    f"[{scen_str}] on THIS real-device host — see "
                    f"{spec_dir_str}/DEFERRED_REQUIRES_DEVICE.md. On pass, delete "
                    "that sentinel and write VALIDATED.md; on a genuine failure "
                    "treat it as a real bug (BLOCKED.md), not an environment skip."
                ),
            )
        # No-device host: device-saturated guard.
        return _bug_state(
            **common,
            current_step=STEP_DEVICE_DEFERRED_GUARD,
            terminal_reason=TR_DEVICE_QUEUE_EXHAUSTED,
            notify_message=(
                f"{bug_name}: real-device-only assertions are deferred and "
                "cannot be certified here. Awaiting a real-device /lazy-bug host."
            ),
        )

    # Step 9: MCP gate (retro complete; now validate runtime).
    validated_file = spec_dir / "VALIDATED.md"
    skip_mcp_file = spec_dir / "SKIP_MCP_TEST.md"
    deferred_file = spec_dir / "DEFERRED_NON_CLOUD.md"
    mcp_results_file = spec_dir / "MCP_TEST_RESULTS.md"

    if cloud:
        if not validated_file.exists() and not skip_mcp_file.exists() and not deferred_file.exists():
            # Cloud halts at Step 9 — defer to workstation.
            return _bug_state(
                **common,
                current_step=STEP_CLOUD_DEFER_MCP,
                sub_skill="__write_deferred_non_cloud__",
                sub_skill_args=spec_dir_str,
            )
        # SKIP_MCP_TEST.md from a prior workstation assessment → write VALIDATED.md
        if skip_mcp_file.exists() and not validated_file.exists():
            # Provenance gate (skip_waiver_refusal — mirrors lazy-state.py's
            # Step 9): a pipeline-self-granted skip, a pipeline-authored skip
            # with NO granted_by field, or an mcp-test grant missing its
            # spec_class citation must NOT vacuously validate. Accepted:
            # operator grants, legacy no-provenance files, and mcp-test grants
            # carrying a spec_class citation.
            _skip_refusal = skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {}, repo_root)
            if _skip_refusal:
                return _bug_state(
                    **common,
                    current_step=STEP_MCP_SKIP_PIPELINE_GRANTED,
                    terminal_reason=TR_NEEDS_INPUT,
                    notify_message=(
                        f"{bug_name}: SKIP_MCP_TEST.md {_skip_refusal}"
                    ),
                )
            return _bug_state(
                **common,
                current_step=STEP_MCP_SKIP,
                sub_skill="__write_validated_from_skip__",
                sub_skill_args=spec_dir_str,
            )
    else:
        # Workstation Step 9: run MCP tests (or use existing results / skip marker).
        if not validated_file.exists():
            if skip_mcp_file.exists():
                # Provenance gate (skip_waiver_refusal — mirrors lazy-state.py's
                # Step 9): a pipeline-self-granted skip, a pipeline-authored
                # skip with NO granted_by field, or an mcp-test grant missing
                # its spec_class citation must NOT vacuously validate. Accepted:
                # operator grants, legacy no-provenance files, and mcp-test
                # grants carrying a spec_class citation.
                _skip_refusal = skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {}, repo_root)
                if _skip_refusal:
                    return _bug_state(
                        **common,
                        current_step=STEP_MCP_SKIP_PIPELINE_GRANTED,
                        terminal_reason=TR_NEEDS_INPUT,
                        notify_message=(
                            f"{bug_name}: SKIP_MCP_TEST.md {_skip_refusal}"
                        ),
                    )
                return _bug_state(
                    **common,
                    current_step=STEP_MCP_SKIP,
                    sub_skill="__write_validated_from_skip__",
                    sub_skill_args=spec_dir_str,
                )
            # 100%-passing results already on disk?
            if mcp_results_file.exists():
                meta = parse_sentinel(mcp_results_file) or {}
                # Accept EITHER a canonical all-passing run OR a sanctioned
                # observation-gap partial — mirrors lazy-state.py's Step 9 via the
                # SHARED observation_gap_promotable helper (the SAME predicate the
                # apply gate + completion-integrity gate use). Without this mirror
                # a valid observation-gap partial re-dispatched /mcp-test every
                # cycle (the deadlock one layer UP from the completion gate). The
                # helper is HALF the AND — the promotion also requires the
                # MCP-driveable scope fully passing (pass_count == total_count),
                # cross-checked here so a genuine MCP-scope failure does NOT
                # route to write-validated.
                _obs_gap = observation_gap_promotable(meta)
                if _obs_gap:
                    _pass = _coerce_evidence_count(meta.get("pass_count"))
                    _total = _coerce_evidence_count(meta.get("total_count"))
                    if _pass is None or _total is None or _pass != _total:
                        _obs_gap = False
                if meta.get("result") == "all-passing" or _obs_gap:
                    # Freshness gate (mirrors lazy-state.py's Step 9): the
                    # results must have been validated against the CURRENT
                    # HEAD commit. If validated_commit is present and doesn't
                    # match HEAD, classify the drift via the SHARED
                    # commit_drift_verdict helper (the SAME docs-only carve-out
                    # evaluate_completion_evidence + the apply gate use). When
                    # _current_head returns None (not a git repo) or
                    # validated_commit is absent (legacy results), the helper
                    # returns "fresh" — legacy permissive.
                    #
                    # DOCS-ONLY DRIFT carve-out (2026-06-23 DEADLOCK fix —
                    # hardening-log Round 36): an /mcp-test cycle that obeys its
                    # clean-tree turn-end contract MUST commit
                    # MCP_TEST_RESULTS.md, and that commit advances HEAD exactly
                    # one past the validated_commit it just recorded. The results
                    # file is therefore PERPETUALLY one commit stale and that
                    # drift is a PURE DOCS-ONLY (*.md) delta — strict equality is
                    # structurally unsatisfiable → an infinite re-verify loop on
                    # EVERY bug. Docs-only drift routes to write-validated; only a
                    # non-.md (source/script/config) drift OR an unresolvable diff
                    # re-verifies (genuine TOCTOU).
                    head = _current_head(repo_root)
                    validated_commit = meta.get("validated_commit")
                    drift = commit_drift_verdict(repo_root, validated_commit, head)
                    if drift["verdict"] in ("non-docs-drift", "unresolvable"):
                        return _bug_state(
                            **common,
                            current_step=STEP_MCP_STALE_RESULTS,
                            sub_skill=SKILL_MCP_TEST,
                            sub_skill_args=(
                                f"re-validate {bug_name} — MCP_TEST_RESULTS.md was "
                                f"validated against a stale commit; see {spec_dir_str}/SPEC.md"
                            ),
                        )
                    # verdict ∈ {"fresh", "docs-only"} → safe to write validated.
                    return _bug_state(
                        **common,
                        current_step="Step 9b: write validated",
                        sub_skill="__write_validated_from_results__",
                        sub_skill_args=spec_dir_str,
                    )
            # Structural MCP-skip short-circuit (lazy-cycle-containment
            # follow-up — mirrors lazy-state.py's Step 9): a `**MCP runtime:**
            # not-required` bug fix in a repo with NO app surface (no src-tauri/,
            # no package.json) is mechanically untestable — grant the skip INLINE
            # via a pseudo-skill instead of a wasted /mcp-test cycle. The grant's
            # granted_by: pipeline-structural is re-verified by skip_waiver_refusal.
            if phases_mcp_runtime_not_required(spec_dir) and repo_has_no_app_surface(
                repo_root
            ):
                return _bug_state(
                    **common,
                    current_step="Step 9: structural MCP-skip (no app surface)",
                    sub_skill="__grant_skip_no_mcp_surface__",
                    sub_skill_args=spec_dir_str,
                )
            # Run MCP tests.
            return _bug_state(
                **common,
                current_step=STEP_MCP,
                sub_skill=SKILL_MCP_TEST,
                sub_skill_args=f"validate {bug_name} — see {spec_dir_str}/SPEC.md",
            )

    # Step 10: Mark fixed.
    # Entry: VALIDATED.md (+ Status not yet Fixed). (Retro unwired — no
    # RETRO_DONE.md precondition.)
    #
    # Cloud defensive backstop (mirrors lazy-state.py).
    # The Step-2 cloud-saturated skip normally prevents a cloud host from ever
    # reaching this point without VALIDATED.md (DEFERRED_NON_CLOUD.md + phases
    # complete → skip in queue walk → TR_CLOUD_QUEUE_EXHAUSTED at exhaustion).
    # But if somehow a bug arrives here on a cloud host without VALIDATED.md,
    # halt rather than silently archiving with zero validation.
    if cloud and not validated_file.exists():
        return _bug_state(
            **common,
            current_step="Step 10a: cloud halt",
            terminal_reason=TR_CLOUD_QUEUE_EXHAUSTED,
            notify_message=(
                f"{bug_name}: cloud work complete (phases). "
                "Awaiting workstation /lazy-bug for deferred MCP validation."
            ),
        )
    # park-provisional-acceptance (SPEC D6, coupled-pair mirror of
    # lazy-state.py): NEVER emit __mark_fixed__ over an unratified
    # NEEDS_INPUT_PROVISIONAL.md. Normally unreachable (Step 3.6 halts
    # non-park; the park-mode walk branch parks) — defensive honesty so the
    # route is never a guaranteed apply_pseudo refusal.
    if (spec_dir / lazy_core.PROVISIONAL_SENTINEL).exists():
        return _bug_state(
            **common,
            current_step=STEP_NEEDS_RATIFICATION,
            terminal_reason=TR_NEEDS_RATIFICATION,
            notify_message=(
                f"{bug_name}: ready to mark fixed but "
                f"{lazy_core.PROVISIONAL_SENTINEL} is unratified — ratify or "
                "redirect the provisional decision(s) first."
            ),
        )
    return _bug_state(
        **common,
        current_step=STEP_MARK_FIXED,
        sub_skill=SKILL_MARK_FIXED,
        sub_skill_args=spec_dir_str,
    )


def backfill_receipts(repo_root: Path) -> dict[str, Any]:
    """Write FIXED.md (provenance: backfilled-unverified) for every Fixed bug
    that lacks one.  Mirrors lazy-state.py's backfill_receipts().

    Walks ALL on-disk SPEC.md files under docs/bugs/ (including _archive/) for
    bugs with **Status:** Fixed (or archived) lacking FIXED.md, and writes one
    via lazy_core.write_completed_receipt(..., kind="fixed", filename="FIXED.md").
    Won't-fix bugs are exempt (receipt-exempt, never fixed).
    """
    repo_root = repo_root.resolve()
    bugs_root = repo_root / "docs" / "bugs"
    today = datetime.now().strftime("%Y-%m-%d")
    written: list[str] = []

    if not bugs_root.exists():
        return {"backfilled": [], "count": 0}

    for spec_md in sorted(bugs_root.glob("**/SPEC.md")):
        spec_dir = spec_md.parent
        status = spec_status(spec_dir)
        if status != BUG_STATUS_FIXED:
            continue
        receipt = spec_dir / "FIXED.md"
        if receipt.exists():
            continue
        # Write a backfill receipt using the generalized write_completed_receipt helper.
        # The helper's defaults write kind: completed and title: Completion Receipt,
        # so we pass explicit overrides in the body note.
        bug_id = spec_dir.name
        write_completed_receipt(
            receipt, bug_id, today,
            provenance="backfilled-unverified",
            kind="fixed",
            body_note=(
                "Grandfathered during the receipt-gating rollout. This bug was "
                "marked Fixed BEFORE the FIXED.md receipt gate existed, so its "
                "pipeline validation was NOT verified by the gate. Treat as "
                "fixed-but-unverified; re-validate if its behavior is load-bearing."
            ),
        )
        written.append(bug_id)

    return {"backfilled": written, "count": len(written)}


def fsck(repo_root: Path) -> dict[str, Any]:
    """Read-only lint: assert the archive-on-fix invariants across docs/bugs/.

    fixed-bugs-unarchived-fsck Fix Scope §3 — the deterministic check that a
    ``Status: Fixed`` dir outside ``_archive/``, or a ``Fixed``-without-receipt
    dir, is surfaced LOUDLY rather than silently accumulating (the debris this
    bug's own reconciliation sweep, commit ``efaf93b3``, cleaned up once —
    this is what keeps it from silently recurring). Three invariants:

      (a) ``unarchived-fixed`` — a ``Status: Fixed`` dir with a VALID
          ``FIXED.md`` receipt sitting OUTSIDE ``_archive/``. The
          ``__mark_fixed__ → --archive-fixed`` sequence minted the receipt
          but the ``git mv`` into ``_archive/`` never ran (or ran only
          partially) for it. Remedy: ``--archive-fixed <spec_dir>``.
      (b) ``fixed-without-receipt`` — a ``Status: Fixed`` dir with NO valid
          ``FIXED.md`` receipt. Completion-unverified debt — the sanctioned
          remedy is ``--backfill-receipts`` (grandfathers it as
          ``provenance: backfilled-unverified``), never silencing the signal
          (see ``docs/bugs/unqueued-fixed-without-receipt-dirs-perpetual-
          diagnostic-noise``, which resolved this exact class via the
          backfill route, not suppression). ``Won't-fix`` dirs are exempt
          (a different status — this check only fires on literal ``Fixed``).
      (c) ``stale-queue-entry`` — a ``docs/bugs/queue.json`` row whose
          ``spec_dir`` resolves to a ``Fixed`` or already-archived directory
          — debris the ``archive_fixed`` queue-trim step should have removed.

    Read-only over the filesystem — never writes, never mutates queue.json,
    never archives anything. Runnable standalone (``--fsck``), at
    ``--run-end``, or as a future ``docs/features/claude-config-ci/`` lane.

    Returns ``{"ok": bool, "violations": [{"kind", "bug_id", "detail"}, ...]}``
    — ``ok`` is True iff ``violations`` is empty. The CLI handler maps this to
    exit 0 (clean) / exit 1 (violations found), per the SPEC's "exit
    non-zero with named violations" contract.
    """
    repo_root = repo_root.resolve()
    bugs_root = repo_root / "docs" / "bugs"
    violations: list[dict[str, str]] = []
    if not bugs_root.exists():
        return {"ok": True, "violations": []}

    archive_root = bugs_root / "_archive"
    archive_prefix = str(archive_root.resolve()).replace("\\", "/").rstrip("/") + "/"

    def _under_archive(p: Path) -> bool:
        try:
            resolved = str(p.resolve()).replace("\\", "/")
        except OSError:
            return False
        return (resolved + "/").startswith(archive_prefix) or resolved == archive_prefix.rstrip("/")

    # (a) + (b): walk every on-disk SPEC.md, archived and unarchived alike.
    for spec_md in sorted(bugs_root.glob("**/SPEC.md")):
        spec_dir = spec_md.parent
        status = spec_status(spec_dir)
        if status != BUG_STATUS_FIXED:
            continue
        bug_id = spec_dir.name
        under_archive = _under_archive(spec_dir)
        has_receipt = has_completion_receipt(spec_dir, filename="FIXED.md")
        try:
            rel = spec_dir.relative_to(bugs_root)
        except ValueError:
            rel = spec_dir
        if has_receipt and not under_archive:
            violations.append({
                "kind": "unarchived-fixed",
                "bug_id": bug_id,
                "detail": (
                    f"docs/bugs/{rel} is Status: Fixed with a valid FIXED.md "
                    "receipt but sits outside _archive/ — run "
                    f"`--archive-fixed docs/bugs/{rel}`."
                ),
            })
        if not has_receipt and not under_archive:
            violations.append({
                "kind": "fixed-without-receipt",
                "bug_id": bug_id,
                "detail": (
                    f"docs/bugs/{rel} is Status: Fixed with NO valid FIXED.md "
                    "receipt — run --backfill-receipts, or flip to Won't-fix "
                    "if the fix claim cannot be evidenced."
                ),
            })

    # (c): queue.json rows pointing at a Fixed or already-archived dir.
    queue_path = bugs_root / "queue.json"
    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        items = data.get("queue", []) if isinstance(data, dict) else []
        if isinstance(items, list):
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                bug_id = entry.get("id")
                spec_subdir = entry.get("spec_dir", bug_id)
                if not spec_subdir:
                    continue
                spec_path = bugs_root / spec_subdir
                under_archive = _under_archive(spec_path)
                status = spec_status(spec_path) if spec_path.exists() else None
                if under_archive or status == BUG_STATUS_FIXED:
                    reason = "archived" if under_archive else "Status: Fixed"
                    violations.append({
                        "kind": "stale-queue-entry",
                        "bug_id": bug_id or "<unknown>",
                        "detail": (
                            f"docs/bugs/queue.json entry '{bug_id}' points at "
                            f"'{spec_subdir}' which is {reason} — trim the row "
                            "(archive_fixed's queue-trim step, or a manual "
                            "_atomic_write edit)."
                        ),
                    })

    return {"ok": len(violations) == 0, "violations": violations}


def enqueue_adhoc(
    repo_root: Path,
    bug_id: str,
    name: str,
    spec_dir: str | None = None,
    severity: str | None = None,
    deps: list[str] | None = None,
) -> dict[str, Any]:
    """Prepend an ad-hoc bug entry to docs/bugs/queue.json.

    Idempotent: if bug_id is already queued, emits a diagnostic and returns
    without modifying the file (exits 0 — safe to call from a re-materialize path).
    Creates queue.json (with empty queue) and docs/bugs/ if absent.

    queue-dependency-dag Phase 4 (coupled-pair mirror of lazy-state.py's
    enqueue): an optional ``deps`` id list (``--deps a,b``) declares hard queue
    deps at enqueue time. Validated up front (regex + reserved
    ``bug:``/``feature:`` prefixes → ``_die``, zero side effects); omitted ⇒
    the entry shape is byte-identical to before.
    """
    repo_root = repo_root.resolve()
    spec_dir = spec_dir or bug_id
    if deps:
        lazy_core.validate_dep_id_list(
            deps, context=f"'--deps' (enqueue {bug_id!r})"
        )
    bugs_dir = repo_root / "docs" / "bugs"
    bugs_dir.mkdir(parents=True, exist_ok=True)
    queue_path = bugs_dir / "queue.json"

    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _die(f"invalid bugs/queue.json: {exc}", queue_path)
            return {}  # pragma: no cover
    else:
        data = {"queue": []}

    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("bugs/queue.json 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover

    if any(isinstance(e, dict) and e.get("id") == bug_id for e in items):
        _diag(f"bug already queued: {bug_id} — enqueue is a no-op")
        return {"id": bug_id, "spec_dir": spec_dir, "status": "duplicate"}

    _new_entry: dict[str, Any] = {
        "id": bug_id,
        "name": name,
        "spec_dir": spec_dir,
        "severity": severity,
    }
    if deps:
        # queue-dependency-dag: the optional hard-deps declaration. Key absent
        # when not supplied — byte-identical legacy entry shape.
        _new_entry["deps"] = list(deps)
    items.insert(0, _new_entry)
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    return {"id": bug_id, "spec_dir": spec_dir, "status": "queued"}


def pin_bug_severity(
    repo_root: Path,
    bug_id: str,
    *,
    until: str | None = None,
    reason: str | None = None,
    today: "date | None" = None,
) -> dict[str, Any]:
    """Deprioritize a bug via a REVIEWABLE, expiring pin (bug-queue-aging-
    backpressure D2-A) — the sanctioned replacement for hand-editing
    ``docs/bugs/queue.json`` to ``"severity": null``.

    Sets ``severity: null`` + ``pinned_at`` (today, script-stamped) +
    ``pinned_until`` (optional, validated ISO date) + ``pin_reason`` on the
    bug's queue entry, creating one (appended, not prepended — a
    deprioritization should not jump the queue) if the bug is not already
    queued. ``lazy_core.merged_priority``/``pin_is_active`` consult these
    fields: the pin suppresses the bug's effective priority
    (``MERGED_PRIORITY_DEFAULT``) until ``pinned_until`` passes (or, absent
    it, ``_PIN_DEFAULT_MAX_AGE_DAYS`` from ``pinned_at``), after which the
    merged view falls back to the SPEC's own ``**Severity:**`` line and
    resumes age-escalating.

    A malformed ``until`` (`_die`, exit 2, zero mutation) or a ``bug_id`` that
    resolves to no on-disk dir under ``docs/bugs/`` (`_die`) refuse cleanly.
    Re-pinning an already-pinned entry OVERWRITES its pin fields (the latest
    ``--pin`` call is authoritative — not additive).
    """
    repo_root = repo_root.resolve()
    if until:
        try:
            date.fromisoformat(until.strip())
        except (ValueError, AttributeError):
            _die(f"invalid --until date: {until!r} (expected YYYY-MM-DD)")
            return {}  # pragma: no cover

    bugs_dir = repo_root / "docs" / "bugs"
    bugs_dir.mkdir(parents=True, exist_ok=True)
    queue_path = bugs_dir / "queue.json"

    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _die(f"invalid bugs/queue.json: {exc}", queue_path)
            return {}  # pragma: no cover
    else:
        data = {"queue": []}

    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("bugs/queue.json 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover

    ref_today = today if today is not None else date.today()
    pinned_at = ref_today.isoformat()

    existing = next(
        (e for e in items if isinstance(e, dict) and e.get("id") == bug_id), None
    )
    if existing is not None:
        existing["severity"] = None
        existing["pinned_at"] = pinned_at
        existing["pinned_until"] = until
        existing["pin_reason"] = reason
        status = "updated"
    else:
        bug_dir = bugs_dir / bug_id
        if not bug_dir.is_dir():
            _die(f"cannot pin unknown bug: {bug_id!r} (no docs/bugs/{bug_id}/ dir)")
            return {}  # pragma: no cover
        name = bug_id
        spec_md = bug_dir / "SPEC.md"
        if spec_md.exists():
            try:
                for line in spec_md.read_text(encoding="utf-8").splitlines():
                    m = re.match(r"^#\s+(.+?)\s*$", line)
                    if m:
                        name = m.group(1)
                        break
            except OSError:
                pass
        items.append({
            "id": bug_id,
            "name": name,
            "spec_dir": bug_id,
            "severity": None,
            "pinned_at": pinned_at,
            "pinned_until": until,
            "pin_reason": reason,
        })
        status = "pinned"

    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    return {
        "id": bug_id,
        "status": status,
        "pinned_at": pinned_at,
        "pinned_until": until,
        "pin_reason": reason,
    }


def unpin_bug_severity(
    repo_root: Path, bug_id: str, *, today: "date | None" = None
) -> dict[str, Any]:
    """Un-pin a bug — the INVERSE of ``pin_bug_severity``
    (no-sanctioned-cli-for-queue-state-mutations).

    Clears ``pinned_at``/``pinned_until``/``pin_reason`` and restores the
    entry's ``severity`` from the SPEC's own ``**Severity:**`` line (so the bug
    re-enters effective ordering at its declared severity rather than the
    suppressed ``severity: null``), then ATOMICALLY re-positions it in listed
    order to match its restored merged priority (via
    ``lazy_core.reposition_by_priority``) in the SAME ``_atomic_write``.

    A bug that is not queued ``_die``s (exit 2, zero mutation). A queued bug
    that carries NO active pin (``pinned_at`` absent) is a byte-stable no-op
    (``unpinned: False`` — ZERO write), mirroring ``sync_deps``' no-op contract.

    Returns ``{"id", "unpinned": bool, "noop": bool, "restored_severity",
    "new_position", "queue_length"}``.
    """
    repo_root = repo_root.resolve()
    bugs_dir = repo_root / "docs" / "bugs"
    queue_path = bugs_dir / "queue.json"
    if not queue_path.exists():
        _die("bugs/queue.json not found", queue_path)
        return {}  # pragma: no cover
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid bugs/queue.json: {exc}", queue_path)
        return {}  # pragma: no cover
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("bugs/queue.json 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover

    entry = next(
        (e for e in items if isinstance(e, dict) and e.get("id") == bug_id), None
    )
    if entry is None:
        _die(f"--unpin: bug not queued: {bug_id!r}", queue_path)
        return {}  # pragma: no cover

    # Byte-stable no-op when the bug carries no active pin fields at all.
    if not any(
        entry.get(k) is not None
        for k in ("pinned_at", "pinned_until", "pin_reason")
    ) and entry.get("severity") is not None:
        return {
            "id": bug_id, "unpinned": False, "noop": True,
            "restored_severity": entry.get("severity"),
            "new_position": items.index(entry), "queue_length": len(items),
        }

    # Restore severity from the SPEC's **Severity:** line (fallback: leave the
    # existing severity as-is if the SPEC has none — never fabricate a rank).
    spec_subdir = entry.get("spec_dir", bug_id)
    spec_md = (bugs_dir / spec_subdir / "SPEC.md") if spec_subdir else None
    restored = bug_severity(spec_md) if (spec_md and spec_md.exists()) else None
    if restored is not None:
        entry["severity"] = restored
    for _pk in ("pinned_at", "pinned_until", "pin_reason"):
        entry.pop(_pk, None)

    new_position = lazy_core.reposition_by_priority(
        items, bug_id, "bug", today=today
    )
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    return {
        "id": bug_id, "unpinned": True, "noop": False,
        "restored_severity": entry.get("severity"),
        "new_position": new_position, "queue_length": len(items),
    }


# ---------------------------------------------------------------------------
# Production sentinel writers (production-sentinel-writes-bypass-atomic-write:
# these two used to sit BELOW the "SMOKE FIXTURES" banner below (a stale
# WU-2.1/WU-2.2 historical note) even though `_write_yaml_blocked_sentinel` is
# called from PRODUCTION compute_state fail-fasts (unknown-host-capability,
# unknown-dependency) far above — the same misclassification lazy-state.py had.
# Re-bannered in place; `_write_yaml_sentinel` is fixture-only today (every
# live caller is inside `_build_bug_fixture` below) but is fixed for atomicity
# alongside its sibling per the SPEC's fix-scope row.
#
# PyYAML-fallback reconciliation (SPEC D3): the per-call `except ImportError`
# fallback below was DEAD CODE — `import lazy_core` (module import, above)
# already hard-exits the process at import time when PyYAML is absent
# (lazy_core.py's own `try: import yaml / except ImportError: sys.exit(2)`),
# so this function body can never observe a missing PyYAML. Removed in favor
# of lazy-state.py's hard-exit posture (this module now also hard-exits at
# import time, see the `import yaml` block above) — one posture, not two. This
# ALSO makes the "byte-for-byte mirror of the lazy-state.py helper" docstring
# claim below true (both are now the same body: build fm, safe_dump,
# _atomic_write) instead of aspirational.
# ---------------------------------------------------------------------------

def _write_yaml_sentinel(path: Path, kind: str, **fields: Any) -> None:
    """Write a sentinel file with YAML frontmatter (same helper as lazy-state.py)."""
    fm = {"kind": kind, **fields}
    body = "---\n" + yaml.safe_dump(fm, sort_keys=False).strip() + "\n---\n\n# Sentinel\n"
    _atomic_write(path, body)


def _write_yaml_blocked_sentinel(
    path: Path, *, feature_id: str, phase: str, blocker_kind: str,
    blocked_at: str, retry_count: int = 0, body: str = "",
) -> None:
    """Write a canonical BLOCKED.md (kind: blocked) with a human-readable body.

    host-capability-declaration-for-gated-features Phase 6 (bug-pipeline parity):
    the unknown-host-capability fail-fast routes through the EXISTING canonical
    BLOCKED.md path (no new sentinel name) — a byte-for-byte mirror of the
    lazy-state.py helper of the same name, so the shared blocker body formatter
    (lazy_core.format_unknown_host_capability_blocker) is reused identically.
    Frontmatter is the parser's source of truth; the body is the human-readable
    context required by the BLOCKED.md schema. The filename is exactly
    `BLOCKED.md`, so the noncanonical-blocker + stray-branch hooks are satisfied.
    """
    fm = {
        "kind": "blocked",
        "feature_id": feature_id,
        "phase": phase,
        "blocker_kind": blocker_kind,
        "blocked_at": blocked_at,
        "retry_count": retry_count,
    }
    text = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False).strip()
        + "\n---\n\n"
        + (body if body else "# Blocked\n")
    )
    _atomic_write(path, text)


# ===========================================================================
# === SMOKE FIXTURES + --test (WU-2.1 test-agent owns this section) =========
# ===========================================================================
#
# DO NOT MODIFY this section during WU-2.2 implementation work.
# The test-agent (WU-2.1) is the sole author of everything below the banner.
#
# Structure:
#   _build_bug_fixture()       — builds one named fixture under a temp root
#   run_smoke_tests()          — builds each fixture, calls compute_state(),
#                                asserts expected outcomes; returns 0/1
# ===========================================================================


def _build_bug_fixture(tmpdir: Path, name: str) -> Path:
    """Build one named fixture under tmpdir/<name>/ and return its repo root.

    Each fixture constructs a minimal docs/bugs/ tree that represents a
    specific point in the bug lifecycle.  The impl-agent reads these to
    understand the expected on-disk shape; the harness calls compute_state()
    against them and checks the returned dict against the constants defined
    in the module-level "single source of truth" block above.

    Fixture inventory (10 required + 1 bonus):
      fresh-open-bug          — SPEC Open, no investigation/PHASES/plan
      blocked                 — BLOCKED.md present
      mid-fix                 — In-progress, PHASES + Ready plan, unchecked WUs
      phases-complete-no-retro— all PHASES checked, no RETRO_DONE.md
      retro-done-needs-mcp    — RETRO_DONE.md, no VALIDATED.md, no-device host
      ready-to-mark-fixed     — RETRO_DONE.md + VALIDATED.md
      device-deferred         — RETRO_DONE.md + DEFERRED_REQUIRES_DEVICE.md,
                                no VALIDATED.md, no-real-device host
      hybrid-ordering         — 2 bugs: one in queue.json, one on-disk only
                                (higher severity); queued bug must be picked first
      wont-fix-exempt         — Won't-fix with NO receipt → skip (receipt-exempt)
      fixed-no-receipt-halt   — Fixed with NO FIXED.md → completion-unverified
      all-bugs-fixed          — no open bugs remain → all-bugs-fixed terminal
      operator-deferred-skip  — 2 bugs: one with DEFERRED.md (parked), one actionable;
                                the actionable bug must be selected (DEFERRED.md skipped)
      all-operator-deferred   — only bug has DEFERRED.md → all-remaining-deferred terminal
      queue-json-missing      — docs/bugs/ exists but queue.json absent → queue-missing terminal
      unqueued-fixed-no-receipt-halt — on-disk Fixed bug NOT in queue.json, no FIXED.md
                                       → must halt with completion-unverified (not silently
                                         skip to all-bugs-fixed via _find_open_bug_dirs)
    """
    root = tmpdir / name
    bugs_dir = root / "docs" / "bugs"
    # Idempotent: if the directory already exists, the fixture is already built.
    if bugs_dir.exists():
        return root
    bugs_dir.mkdir(parents=True, exist_ok=True)

    if name == "fresh-open-bug":
        # A bug dir with SPEC.md **Status:** Open, nothing else.
        # Expected: dispatch spec-bug (investigation step).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-fresh", "name": "Fresh Open Bug", "spec_dir": "bug-fresh"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-fresh"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Fresh Open Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-01\n\n"
            "## Description\n\nSomething is broken.\n",
            encoding="utf-8",
        )

    elif name == "blocked":
        # A bug with BLOCKED.md present.
        # Expected: terminal_reason == "blocked"
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-blocked", "name": "Blocked Bug", "spec_dir": "bug-blocked"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-blocked"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Blocked Bug\n\n"
            "**Status:** Investigating\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-05-02\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "BLOCKED.md", "blocked",
            bug_id="bug-blocked", phase="Investigation",
            blocked_at="2026-05-10T09:00:00Z", retry_count=0,
        )

    elif name == "mid-fix":
        # In-progress: PHASES.md has unchecked WUs, a Ready plan is present.
        # Expected: sub_skill == execute-plan
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-midfix", "name": "Mid Fix Bug", "spec_dir": "bug-midfix"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-midfix"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Mid Fix Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P0\n\n"
            "**Discovered:** 2026-04-15\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [ ] Implement fix\n"
            "- [ ] Add regression test\n",
            encoding="utf-8",
        )
        plans = bdir / "plans"
        plans.mkdir()
        (plans / "all-phases-midfix.md").write_text(
            "---\n"
            "kind: implementation-plan\n"
            "feature_id: bug-midfix\n"
            "status: Ready\n"
            "created: 2026-05-15\n"
            "phases: [1]\n"
            "---\n\n"
            "# Fix Plan\n",
            encoding="utf-8",
        )

    elif name == "plan-structural-backstop-refuses-fresh-invalid":
        # plan-structure-authoring-gate Phase 4 pickup backstop (bug-pipeline
        # parity mirror): a FRESH plan (zero ticked WUs) carrying an unfilled
        # WU-checklist template-row placeholder must REFUSE the /execute-plan
        # route (BLOCKED.md, blocker_kind: plan-structural-invalid).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-pstruct-fresh", "name": "Bug PStruct Fresh",
                 "spec_dir": "bug-pstruct-fresh"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-pstruct-fresh"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Bug PStruct Fresh\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-07-12\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] WU1 implement the fix\n",
            encoding="utf-8",
        )
        plans = bdir / "plans"
        plans.mkdir()
        (plans / "all-phases-pstruct-fresh.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: bug-pstruct-fresh\n"
            "status: Ready\ncreated: 2026-07-12\nphases: [1]\n---\n\n"
            "## Work Units\n- [ ] WU-N — <short title>\n",
            encoding="utf-8",
        )

    elif name == "plan-structural-backstop-mid-execution-warns":
        # Same structural defect, but the plan already has >=1 ticked WU
        # (mid-execution — already in flight). The backstop must WARN, never
        # refuse: sub_skill stays execute-plan.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-pstruct-mid", "name": "Bug PStruct Mid",
                 "spec_dir": "bug-pstruct-mid"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-pstruct-mid"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Bug PStruct Mid\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-07-12\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n"
            "- [x] WU1 implement the fix\n"
            "- [ ] WU2 more work\n",
            encoding="utf-8",
        )
        plans = bdir / "plans"
        plans.mkdir()
        (plans / "all-phases-pstruct-mid.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: bug-pstruct-mid\n"
            "status: In-progress\ncreated: 2026-07-12\nphases: [1]\n---\n\n"
            "## Work Units\n"
            "- [x] WU-1 — did something real\n"
            "- [ ] WU-N — <short title>\n",
            encoding="utf-8",
        )

    elif name == "bug-stale-plan-flips":
        # Stale-plan flip (bug-pipeline-missing-stale-plan-flip): the head plan's
        # phases: [1] scope is fully checked ([x]), but Phase 2 has an unchecked
        # row so unchecked > 0 overall and Step 7a is entered. The plan's
        # frontmatter is still In-progress (never flipped after Phase 1 finished)
        # -> STALE. Expected: sub_skill == __flip_plan_complete_stale__ (NOT a
        # redundant execute-plan re-dispatch). The "mid-fix" fixture (Phase 1 has
        # genuine unchecked WUs in scope) is the discriminating control that must
        # stay execute-plan.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-stale", "name": "Stale Plan Bug",
                 "spec_dir": "bug-stale"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-stale"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Stale Plan Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-20\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n"
            "\n"
            "### Phase 2\n"
            "- [ ] Add regression test\n",
            encoding="utf-8",
        )
        plans = bdir / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] only — the fully-checked phase.
        # status: In-progress (never flipped after Phase 1 completed) -> STALE.
        (plans / "all-phases-stale-part-1.md").write_text(
            "---\n"
            "kind: implementation-plan\n"
            "feature_id: bug-stale\n"
            "status: In-progress\n"
            "created: 2026-05-20\n"
            "phases: [1]\n"
            "---\n\n"
            "# Fix Plan Part 1\n",
            encoding="utf-8",
        )

    elif name == "phases-complete-no-retro":
        # All PHASES.md deliverables checked; no sentinels.
        # Retro unwired: Step 9 mcp-test fires directly (NOT retro-feature).
        # Expected: sub_skill == mcp-test (Step 9)
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-pcnr", "name": "Phases Complete No Retro",
                 "spec_dir": "bug-pcnr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-pcnr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Phases Complete No Retro\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-04-20\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n"
            "- [x] Add regression test\n",
            encoding="utf-8",
        )

    elif name == "phases-complete-no-mcp-surface":
        # All PHASES checked; PHASES declares `**MCP runtime:** not-required` and
        # the temp repo has NO app surface (no src-tauri/, no package.json) →
        # Step 9 short-circuits to the inline structural skip grant.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-noms", "name": "No MCP Surface",
                 "spec_dir": "bug-noms"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-noms"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# No MCP Surface\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-04-20\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "**MCP runtime:** not-required\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )

    elif name == "retro-done-needs-mcp":
        # RETRO_DONE.md present; no VALIDATED.md; not cloud, not real-device.
        # Expected: sub_skill == mcp-test (Step 9 workstation run)
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-rdnm", "name": "Retro Done Needs MCP",
                 "spec_dir": "bug-rdnm"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-rdnm"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Retro Done Needs MCP\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-rdnm", date="2026-05-25",
            rounds=1,
        )

    elif name == "ready-to-mark-fixed":
        # RETRO_DONE.md + VALIDATED.md present.
        # Expected: sub_skill == __mark_fixed__
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-rtmf", "name": "Ready To Mark Fixed",
                 "spec_dir": "bug-rtmf"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-rtmf"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Ready To Mark Fixed\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-rtmf", date="2026-05-25", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "VALIDATED.md", "validated",
            bug_id="bug-rtmf", date="2026-05-26", result="all-passing",
        )

    elif name == "device-deferred":
        # RETRO_DONE.md + DEFERRED_REQUIRES_DEVICE.md present, no VALIDATED.md.
        # On a no-real-device host → device-queue-exhausted terminal.
        # device_deferred_features must be populated.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-dd", "name": "Device Deferred Bug", "spec_dir": "bug-dd"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-dd"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Device Deferred Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P0\n\n"
            "**Discovered:** 2026-04-10\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-dd", date="2026-05-20", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "DEFERRED_REQUIRES_DEVICE.md", "device-deferred",
            bug_id="bug-dd",
            deferred_scenarios=["BQ-AUDIO-01", "BQ-AUDIO-02"],
            date="2026-05-21",
        )

    elif name == "requires-host-unknown-failfast":
        # host-capability-declaration-for-gated-features Phase 6 (bug-pipeline
        # parity). A bug whose SPEC declares a requires_host: id NOT in the closed
        # registry must FAIL FAST — a loud BLOCKED.md (blocker_kind:
        # unknown-host-capability), NEVER a silent defer-forever — identically to
        # the feature pipeline. The leading `---` frontmatter block is required so
        # lazy_core.parse_requires_host scans it (bug SPECs that open with `# Title`
        # have no pre-heading head to scan).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-rhuf", "name": "Requires Host Unknown Bug",
                 "spec_dir": "bug-rhuf"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-rhuf"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "---\n"
            "requires_host: [typo-cap]\n"
            "---\n\n"
            "# Requires Host Unknown Bug\n\n"
            "**Status:** Investigating\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )

    elif name == "requires-host-registered-no-failfast":
        # host-capability-declaration-for-gated-features Phase 6 (bug-pipeline
        # parity, discriminating guard). A bug declaring ONLY registered
        # requires_host: ids must NOT trip the fail-fast — it proceeds to its
        # normal lifecycle step (here: spec-bug investigation). Proves the
        # fail-fast is scoped to UNREGISTERED ids, not any requires_host: at all.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-rhrn", "name": "Requires Host Registered Bug",
                 "spec_dir": "bug-rhrn"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-rhrn"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "---\n"
            "requires_host: [zimtohrli-toolchain]\n"
            "---\n\n"
            "# Requires Host Registered Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-02\n\n"
            "## Description\n\nSomething is broken.\n",
            encoding="utf-8",
        )

    elif name == "hybrid-ordering":
        # Two bugs: bug-queued is listed in queue.json; bug-unlisted is only
        # on-disk with higher severity (P0 vs P2 for the queued bug).
        # The queue.json entry MUST be returned first (queue overrides severity).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-queued", "name": "Queued Bug (P2)",
                 "spec_dir": "bug-queued"}
            ]
        }), encoding="utf-8")
        # Queued bug (P2 severity)
        bq = bugs_dir / "bug-queued"
        bq.mkdir()
        (bq / "SPEC.md").write_text(
            "# Queued Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-05-10\n",
            encoding="utf-8",
        )
        # Unlisted on-disk bug with higher severity P0 — must NOT be first
        bu = bugs_dir / "bug-unlisted"
        bu.mkdir()
        (bu / "SPEC.md").write_text(
            "# Unlisted Bug (P0)\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P0\n\n"
            "**Discovered:** 2026-04-01\n",
            encoding="utf-8",
        )

    elif name == "wont-fix-exempt":
        # Won't-fix with NO FIXED.md receipt.
        # MUST be treated as done (receipt-exempt, skip it).
        # With this as the only bug, expect all-bugs-fixed terminal.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-wf", "name": "Wont Fix Bug", "spec_dir": "bug-wf"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-wf"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Wont Fix Bug\n\n"
            "**Status:** Won't-fix\n\n"
            "**Severity:** Low\n\n"
            "**Discovered:** 2026-03-01\n",
            encoding="utf-8",
        )
        # No FIXED.md — still exempt because Won't-fix

    elif name == "fixed-no-receipt-halt":
        # Fixed with NO FIXED.md receipt → completion-unverified halt.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-fnr", "name": "Fixed No Receipt Bug",
                 "spec_dir": "bug-fnr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-fnr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Fixed No Receipt Bug\n\n"
            "**Status:** Fixed\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-04-05\n",
            encoding="utf-8",
        )
        # Intentionally NO FIXED.md

    elif name == "all-bugs-fixed":
        # No open bugs at all (empty queue, no on-disk dirs except _archive/).
        # Expected: terminal_reason == "all-bugs-fixed"
        (bugs_dir / "queue.json").write_text(json.dumps({"queue": []}),
                                             encoding="utf-8")
        # Archived bug — must be skipped
        archive = bugs_dir / "_archive"
        archive.mkdir()
        adir = archive / "bug-old"
        adir.mkdir()
        (adir / "SPEC.md").write_text(
            "# Old Bug\n\n**Status:** Fixed\n", encoding="utf-8"
        )
        _write_yaml_sentinel(
            adir / "FIXED.md", "fixed",
            bug_id="bug-old", date="2026-01-01",
            provenance="gated",
        )

    elif name == "enqueue-adhoc-writes-entry":
        # Fixture root for testing enqueue_adhoc writes a spec_dir-keyed entry.
        # The bug dir must exist so load_bug_queue can resolve it.
        bugs_dir.mkdir(parents=True, exist_ok=True)
        # Pre-create queue.json with no entries (enqueue_adhoc will prepend to it).
        (bugs_dir / "queue.json").write_text(json.dumps({"queue": []}), encoding="utf-8")
        bdir = bugs_dir / "fix-the-thing"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "SPEC.md").write_text(
            "# Fix the thing\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )

    elif name == "enqueue-adhoc-idempotent":
        # Fixture root for testing enqueue_adhoc skips duplicate ids cleanly.
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (bugs_dir / "queue.json").write_text(json.dumps({"queue": []}), encoding="utf-8")
        bdir = bugs_dir / "dup-bug"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "SPEC.md").write_text(
            "# Dup Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )

    elif name == "stale-upstream-halt":
        # Bug dir with SPEC.md (Open, no PHASES → would normally dispatch spec-bug)
        # PLUS a STALE_UPSTREAM.md file.  Expected: terminal_reason == "stale_upstream".
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-stale", "name": "Stale Upstream Bug",
                 "spec_dir": "bug-stale"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-stale"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Stale Upstream Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )
        # Write a STALE_UPSTREAM.md with a representative upstream diff.
        (bdir / "STALE_UPSTREAM.md").write_text(
            "Upstream changes detected:\n\n"
            "--- a/Cognito/SomeFile.cs\n"
            "+++ b/Cognito/SomeFile.cs\n"
            "@@ -10,3 +10,4 @@\n"
            " existing line\n"
            "+new upstream line\n",
            encoding="utf-8",
        )

    elif name == "scope-bug-id-two-bugs":
        # Two actionable bugs in queue.json order:
        #   1st: "bug-scope-alpha" (Open, P1) — the one default picks
        #   2nd: "bug-scope-beta"  (Open, P2) — the one scope_bug_id targets
        # Both have only a SPEC.md at an actionable status (Open), so both are
        # normally actionable.  The queue order guarantees alpha is always first
        # under the default path, making a result of beta non-tautological.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-scope-alpha", "name": "Scope Alpha Bug",
                 "spec_dir": "bug-scope-alpha"},
                {"id": "bug-scope-beta", "name": "Scope Beta Bug",
                 "spec_dir": "bug-scope-beta"},
            ]
        }), encoding="utf-8")
        # First bug (alpha) — default walk would pick this one
        ba = bugs_dir / "bug-scope-alpha"
        ba.mkdir()
        (ba / "SPEC.md").write_text(
            "# Scope Alpha Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-01\n\n"
            "## Description\n\nFirst actionable bug.\n",
            encoding="utf-8",
        )
        # Second bug (beta) — scope_bug_id targets this one
        bb = bugs_dir / "bug-scope-beta"
        bb.mkdir()
        (bb / "SPEC.md").write_text(
            "# Scope Beta Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-05-02\n\n"
            "## Description\n\nSecond actionable bug.\n",
            encoding="utf-8",
        )

    elif name == "operator-deferred-skip":
        # Two bugs: bug-deferred (DEFERRED.md present) and bug-actionable (Open, no sentinel).
        # Queue lists deferred first; the actionable bug must be selected instead.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-deferred", "name": "Deferred Bug", "spec_dir": "bug-deferred"},
                {"id": "bug-actionable", "name": "Actionable Bug", "spec_dir": "bug-actionable"},
            ]
        }), encoding="utf-8")
        # Deferred bug: Open status + DEFERRED.md sentinel
        bd = bugs_dir / "bug-deferred"
        bd.mkdir()
        (bd / "SPEC.md").write_text(
            "# Deferred Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bd / "DEFERRED.md", "deferred",
            bug_id="bug-deferred",
            reason="Needs human audio audition — cannot be validated autonomously.",
            deferred_at="2026-06-01",
        )
        # Actionable bug: Open status, no sentinels → should dispatch spec-bug
        ba = bugs_dir / "bug-actionable"
        ba.mkdir()
        (ba / "SPEC.md").write_text(
            "# Actionable Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-05-15\n",
            encoding="utf-8",
        )

    elif name == "all-operator-deferred":
        # Only bug has DEFERRED.md — no actionable bugs remain.
        # Expected: terminal_reason == TR_ALL_DEFERRED and operator_deferred non-empty.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-only-deferred", "name": "Only Deferred Bug",
                 "spec_dir": "bug-only-deferred"},
            ]
        }), encoding="utf-8")
        bod = bugs_dir / "bug-only-deferred"
        bod.mkdir()
        (bod / "SPEC.md").write_text(
            "# Only Deferred Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-20\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bod / "DEFERRED.md", "deferred",
            bug_id="bug-only-deferred",
            reason="Pending hardware setup.",
            deferred_at="2026-06-01",
        )

    elif name == "cloud-defer-mcp":
        # RETRO_DONE.md present; cloud=True; no VALIDATED.md / SKIP_MCP_TEST.md /
        # DEFERRED_NON_CLOUD.md / DEFERRED_REQUIRES_DEVICE.md.
        # Expected: current_step == STEP_CLOUD_DEFER_MCP,
        #           sub_skill == "__write_deferred_non_cloud__"
        # Exercises compute_state lines ~704-712 (cloud Step-9 defer branch).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-cdm", "name": "Cloud Defer MCP Bug",
                 "spec_dir": "bug-cdm"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-cdm"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Cloud Defer MCP Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-10\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-cdm", date="2026-05-28", rounds=1,
        )
        # Intentionally no VALIDATED.md, no SKIP_MCP_TEST.md,
        # no DEFERRED_NON_CLOUD.md, no DEFERRED_REQUIRES_DEVICE.md

    elif name == "cloud-skip-mcp":
        # RETRO_DONE.md + SKIP_MCP_TEST.md present; cloud=True; no VALIDATED.md.
        # Expected: current_step == STEP_MCP_SKIP,
        #           sub_skill == "__write_validated_from_skip__"
        # Exercises compute_state lines ~713-720 (cloud SKIP_MCP_TEST branch).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-csm", "name": "Cloud Skip MCP Bug",
                 "spec_dir": "bug-csm"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-csm"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Cloud Skip MCP Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-11\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-csm", date="2026-05-29", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-csm", reason="No MCP-testable surface",
            approved_by="human", date="2026-05-29",
        )
        # Intentionally no VALIDATED.md

    elif name == "device-reopen":
        # RETRO_DONE.md + DEFERRED_REQUIRES_DEVICE.md present; real_device=True;
        # no VALIDATED.md.
        # Expected: current_step == STEP_DEVICE_REOPEN,
        #           sub_skill == SKILL_MCP_TEST
        # Exercises compute_state lines ~665-686 (real-device re-open branch).
        # This is the real-device twin of the no-device "device-deferred" fixture.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-dro", "name": "Device Reopen Bug",
                 "spec_dir": "bug-dro"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-dro"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Device Reopen Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P0\n\n"
            "**Discovered:** 2026-04-20\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-dro", date="2026-05-22", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "DEFERRED_REQUIRES_DEVICE.md", "device-deferred",
            bug_id="bug-dro",
            deferred_scenarios=["SOME-SCEN-01"],
            date="2026-05-23",
        )
        # Intentionally no VALIDATED.md

    elif name == "step9-skip-mcp":
        # Workstation: RETRO_DONE.md + SKIP_MCP_TEST.md; no VALIDATED.md;
        # no DEFERRED_REQUIRES_DEVICE.md.  cloud=False, real_device=True.
        # Expected: current_step == STEP_MCP_SKIP,
        #           sub_skill == "__write_validated_from_skip__"
        # Exercises compute_state lines ~723-730 (workstation skip branch).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-s9sm", "name": "Step9 Skip MCP Bug",
                 "spec_dir": "bug-s9sm"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-s9sm"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Step9 Skip MCP Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-05-12\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-s9sm", date="2026-05-30", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-s9sm", reason="No MCP-testable surface (workstation)",
            approved_by="human", date="2026-05-30",
        )
        # Intentionally no VALIDATED.md, no DEFERRED_REQUIRES_DEVICE.md

    elif name == "step9-skip-colon-reason":
        # skip-mcp-test-frontmatter-unquoted-colon Phase 2 (bug-pipeline mirror of
        # the lazy-state.py skip-operator-colon-reason-validates fixture): a
        # SKIP_MCP_TEST.md whose `reason:` carries an UNQUOTED colon-space must
        # still route Step 9 → __write_validated_from_skip__ rather than exiting 2
        # at the strict YAML parse. RED before Phase 1 (parse_sentinel _die'd);
        # GREEN after (tolerant re-parse reads the colon value as a literal).
        # The SKIP_MCP_TEST.md is written RAW (NOT via _write_yaml_sentinel, whose
        # yaml.safe_dump would auto-QUOTE the colon value and mask the bug).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-s9cr", "name": "Step9 Skip Colon Reason Bug",
                 "spec_dir": "bug-s9cr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-s9cr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Step9 Skip Colon Reason Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-07-04\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-s9cr", date="2026-07-04", rounds=1,
        )
        # RAW SKIP_MCP_TEST.md — an UNQUOTED colon-space in the `reason` value.
        (bdir / "SKIP_MCP_TEST.md").write_text(
            "---\n"
            "kind: skip-mcp-test\n"
            "bug_id: bug-s9cr\n"
            "reason: untestable on this host: no real audio device\n"
            "approved_by: human\n"
            "date: 2026-07-04\n"
            "---\n\n"
            "# Skip\n",
            encoding="utf-8",
        )
        # Intentionally no VALIDATED.md, no DEFERRED_REQUIRES_DEVICE.md

    elif name == "step9-mcp-results":
        # Workstation: RETRO_DONE.md + MCP_TEST_RESULTS.md with result: all-passing;
        # no VALIDATED.md; no SKIP_MCP_TEST.md.  cloud=False, real_device=True.
        # Expected: current_step == "Step 9b: write validated",
        #           sub_skill == "__write_validated_from_results__"
        # Exercises compute_state lines ~731-740 (workstation results branch).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-s9mr", "name": "Step9 MCP Results Bug",
                 "spec_dir": "bug-s9mr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-s9mr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Step9 MCP Results Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-13\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-s9mr", date="2026-05-31", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "MCP_TEST_RESULTS.md", "mcp-test-results",
            bug_id="bug-s9mr", result="all-passing", date="2026-05-31",
        )
        # Intentionally no VALIDATED.md, no SKIP_MCP_TEST.md

    elif name == "severity-ordering":
        # Two on-disk open bugs with NO queue.json entry (empty queue).
        # bug-sev-p2: Severity P2 (rank 2)
        # bug-sev-p0: Severity P0 (rank 0)
        # Per _SEVERITY_RANK the P0 bug must be selected FIRST.
        # Proves severity rank orders UNLISTED (on-disk) bugs; distinct from
        # hybrid-ordering which proves queue.json overrides severity.
        (bugs_dir / "queue.json").write_text(json.dumps({"queue": []}),
                                             encoding="utf-8")
        # P2 bug (lower priority — must NOT be selected first)
        bp2 = bugs_dir / "bug-sev-p2"
        bp2.mkdir()
        (bp2 / "SPEC.md").write_text(
            "# Severity P2 Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )
        # P0 bug (highest priority — MUST be selected first)
        bp0 = bugs_dir / "bug-sev-p0"
        bp0.mkdir()
        (bp0 / "SPEC.md").write_text(
            "# Severity P0 Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P0\n\n"
            "**Discovered:** 2026-05-02\n",
            encoding="utf-8",
        )

    elif name == "cloud-defer-no-validate-halts":
        # cloud=True; RETRO_DONE.md + DEFERRED_NON_CLOUD.md present; no VALIDATED.md,
        # no SKIP_MCP_TEST.md, no DEFERRED_REQUIRES_DEVICE.md.
        #
        # BUG being pinned (WU-2): the first cloud if-branch in Step 9 is False
        # (deferred_file.exists() makes it skip), the second is also False (no
        # skip_mcp_file), so control FALLS THROUGH to Step 10 __mark_fixed__ —
        # archiving without validation.
        #
        # NEW (post-fix) behavior: cloud MUST halt with
        #   terminal_reason == TR_CLOUD_QUEUE_EXHAUSTED ("cloud-queue-exhausted")
        # mirroring lazy-state.py's Step-10 hard-halt for cloud hosts that have no
        # VALIDATED.md.  sub_skill MUST NOT be SKILL_MARK_FIXED.
        #
        # This fixture is RED against current code (current code routes to
        # __mark_fixed__); GREEN only after the WU-2.2 impl-agent adds the guard.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-cdnv", "name": "Cloud Defer No Validate Bug",
                 "spec_dir": "bug-cdnv"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-cdnv"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Cloud Defer No Validate Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-15\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-cdnv", date="2026-05-30", rounds=1,
        )
        _write_yaml_sentinel(
            bdir / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            bug_id="bug-cdnv",
            reason="MCP validation requires workstation audio stack",
            deferred_at="2026-05-30",
        )
        # Intentionally no VALIDATED.md, no SKIP_MCP_TEST.md,
        # no DEFERRED_REQUIRES_DEVICE.md.

    elif name == "queue-json-missing":
        # docs/bugs/ directory exists but queue.json is absent entirely.
        # No on-disk open bug dirs either — only missing queue file.
        # Expected: terminal_reason == TR_QUEUE_MISSING ("queue-missing").
        # Characterization test for the newly-wired TR_QUEUE_MISSING terminal.
        bugs_dir.mkdir(parents=True, exist_ok=True)
        # Intentionally NO queue.json — the trigger for TR_QUEUE_MISSING.

    elif name == "unqueued-fixed-no-receipt-halt":
        # Pin the bypass: an on-disk bug dir marked **Status:** Fixed but with NO
        # FIXED.md receipt and NOT listed in queue.json must NOT be silently skipped
        # by _find_open_bug_dirs.  It must surface through the completion gate and
        # halt with terminal_reason == TR_COMPLETION_UNVERIFIED.
        #
        # Current behavior (RED): _find_open_bug_dirs pre-filters every dir whose
        # status ∈ _BUG_DONE_STATUSES (which includes "Fixed"), so the bug never
        # reaches the queue-walk receipt gate.  The pipeline sees no open bugs and
        # returns TR_ALL_BUGS_FIXED, silently treating the Fixed-without-receipt bug
        # as done.
        #
        # Expected behavior (GREEN after impl-agent fix): _find_open_bug_dirs only
        # pre-filters Fixed dirs that HAVE a FIXED.md receipt (genuinely done) and
        # Won't-fix dirs (receipt-exempt).  Fixed-WITHOUT-receipt dirs are returned
        # so the queue-walk receipt gate at line ~457-475 can halt with
        # TR_COMPLETION_UNVERIFIED.
        #
        # The queue.json is present but does NOT list this bug dir — forcing the
        # _find_open_bug_dirs code path (not the queued-bug path).
        (bugs_dir / "queue.json").write_text(json.dumps({"queue": []}),
                                             encoding="utf-8")
        bdir = bugs_dir / "bug-unqueued-fnr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Unqueued Fixed No Receipt Bug\n\n"
            "**Status:** Fixed\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n\n"
            "## Description\n\nFixed outside validation gate — no FIXED.md receipt.\n",
            encoding="utf-8",
        )
        # Intentionally NO FIXED.md receipt — the absence triggers the bypass being pinned.

    elif name == "concluded-investigation-plan-bug":
        # SPEC.md has **Status:** Concluded; no PHASES.md.
        # Pinning the infinite-loop bug: after a /spec-bug investigation concludes, the
        # SPEC is marked Concluded but PHASES.md is absent.  The next cycle must dispatch
        # plan-bug (which authors PHASES.md from the concluded spec) NOT spec-bug again.
        #
        # Current behavior (RED): Step 4 always dispatches SKILL_INVESTIGATE ("spec-bug")
        # when PHASES.md is absent, regardless of the SPEC status.
        #
        # Expected behavior (GREEN after impl-agent fix):
        #   sub_skill == "plan-bug"
        #   current_step == STEP_PLAN_BUG (DISTINCT plan label — spec-bug -> plan-bug
        #     transition advances current_step so step_repeat_count is not inflated)
        #   sub_skill_args ends with "SPEC.md"  (points at concluded spec)
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-concluded", "name": "Concluded Investigation Bug",
                 "spec_dir": "bug-concluded"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-concluded"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Concluded Investigation Bug\n\n"
            "**Status:** Concluded\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n\n"
            "## Description\n\n"
            "Investigation has concluded; root cause identified. "
            "Awaiting plan-bug to produce PHASES.md.\n",
            encoding="utf-8",
        )
        # Intentionally NO PHASES.md — triggers the discriminating guard being pinned.

    elif name == "concluded-investigation-guard-still-spec-bug":
        # SPEC.md has **Status:** Investigating; no PHASES.md.
        # Guard fixture: the discriminating marker must NOT change behavior when the
        # investigation is still in progress.  Proves the "Concluded" marker is the
        # exclusive trigger — an Investigating SPEC still routes to spec-bug.
        #
        # Expected behavior (GREEN today AND after impl-agent fix):
        #   sub_skill == "spec-bug"   (SKILL_INVESTIGATE — unchanged)
        #   current_step == STEP_INVESTIGATE
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-still-investigating", "name": "Still Investigating Bug",
                 "spec_dir": "bug-still-investigating"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-still-investigating"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Still Investigating Bug\n\n"
            "**Status:** Investigating\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-02\n\n"
            "## Description\n\n"
            "Investigation still in progress — must remain on spec-bug, not plan-bug.\n",
            encoding="utf-8",
        )
        # Intentionally NO PHASES.md.

    elif name == "step9-skip-pipeline-granted":
        # D-3(a) provenance gate: SKIP_MCP_TEST.md carrying granted_by: pipeline
        # must NOT vacuously validate — the pipeline cannot self-waive its own
        # MCP requirement. Workstation host (cloud=False).
        # Expected: terminal_reason == TR_NEEDS_INPUT,
        #           current_step == STEP_MCP_SKIP_PIPELINE_GRANTED,
        #           sub_skill is NOT "__write_validated_from_skip__".
        # RED against pre-fix code (which ignored granted_by and always emitted
        # __write_validated_from_skip__); GREEN after the gate mirrors lazy-state.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-spg", "name": "Skip Pipeline Granted Bug",
                 "spec_dir": "bug-spg"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-spg"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Skip Pipeline Granted Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-spg", date="2026-06-05", rounds=1,
        )
        # Self-granted skip — must be refused (needs-input), not validated.
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-spg",
            reason="pipeline self-asserted skip to avoid MCP test",
            date="2026-06-05", skipped_by="pipeline",
            granted_by="pipeline",
        )
        # Intentionally no VALIDATED.md.

    elif name == "step9-skip-operator-granted":
        # D-3(a) positive guard: SKIP_MCP_TEST.md with granted_by: operator is a
        # legitimate human-authored waiver — must continue to emit
        # __write_validated_from_skip__ (same as the legacy absent-granted_by path
        # pinned by the step9-skip-mcp fixture).
        # Expected: current_step == STEP_MCP_SKIP,
        #           sub_skill == "__write_validated_from_skip__".
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-sog", "name": "Skip Operator Granted Bug",
                 "spec_dir": "bug-sog"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-sog"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Skip Operator Granted Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-02\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-sog", date="2026-06-06", rounds=1,
        )
        # Operator-granted skip — legitimate human waiver.
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-sog",
            reason="pure docs/config fix — no runtime MCP surface",
            date="2026-06-06", skipped_by="operator",
            granted_by="operator",
        )
        # Intentionally no VALIDATED.md.

    elif name == "step9-skip-mcp-test-granted-with-class":
        # Provenance gate positive: granted_by: mcp-test + a spec_class citation
        # is a verified structural assessment by the validation step itself —
        # accepted as a waiver → __write_validated_from_skip__.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-smtc", "name": "Skip McpTest Class Bug",
                 "spec_dir": "bug-smtc"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-smtc"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Skip McpTest Class Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-08\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-smtc", date="2026-06-09", rounds=1,
        )
        # mcp-test-granted skip WITH the required spec_class citation.
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-smtc",
            reason="standalone crate — no MCP-reachable surface",
            date="2026-06-09", skipped_by="lazy",
            granted_by="mcp-test",
            spec_class="no app integration — covered by cargo tests",
        )
        # Intentionally no VALIDATED.md.

    elif name == "step9-skip-mcp-test-granted-missing-class":
        # Provenance gate: granted_by: mcp-test WITHOUT a spec_class citation is
        # an unverified claim — refused (needs-input), not validated. The
        # citation is what distinguishes a verified structural assessment from
        # a convenience skip.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-smtn", "name": "Skip McpTest NoClass Bug",
                 "spec_dir": "bug-smtn"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-smtn"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Skip McpTest NoClass Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-08\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-smtn", date="2026-06-09", rounds=1,
        )
        # mcp-test-granted skip MISSING the spec_class citation — refused.
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-smtn",
            reason="claims untestable but cites no class",
            date="2026-06-09", skipped_by="lazy",
            granted_by="mcp-test",
        )
        # Intentionally no VALIDATED.md.

    elif name == "step9-skip-pipeline-authored-no-grant":
        # Provenance omission gate: a skip whose skipped_by identifies a
        # pipeline author ("lazy") but which carries NO granted_by at all used
        # to sail through as legacy-operator — the omission side-door. Must now
        # refuse (needs-input). Files with NEITHER field stay grandfathered
        # (pinned by step9-skip-mcp).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-spa", "name": "Skip Pipeline Authored Bug",
                 "spec_dir": "bug-spa"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-spa"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Skip Pipeline Authored Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-08\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-spa", date="2026-06-09", rounds=1,
        )
        # Pipeline-authored (skipped_by: lazy), NO granted_by — refused.
        _write_yaml_sentinel(
            bdir / "SKIP_MCP_TEST.md", "skip-mcp-test",
            bug_id="bug-spa",
            reason="pipeline-written skip with no provenance field",
            date="2026-06-09", skipped_by="lazy",
        )
        # Intentionally no VALIDATED.md.

    elif name == "step9-stale-mcp-results":
        # D-3(b) freshness gate: MCP_TEST_RESULTS.md claims all-passing but its
        # validated_commit (all-zeros sha) cannot equal the fixture's actual git
        # HEAD. The fixture root is a real git repo so `git rev-parse HEAD`
        # resolves to a non-zero sha; the mismatch must route to re-verify
        # (sub_skill=mcp-test), NOT __write_validated_from_results__.
        # RED against pre-fix code (which ignored validated_commit entirely).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-smr", "name": "Stale MCP Results Bug",
                 "spec_dir": "bug-smr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-smr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Stale MCP Results Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-03\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-smr", date="2026-06-07", rounds=1,
        )
        # Stale results: all-passing but validated against the all-zeros sha
        # (which cannot equal any real git HEAD).
        _write_yaml_sentinel(
            bdir / "MCP_TEST_RESULTS.md", "mcp-test-results",
            bug_id="bug-smr", result="all-passing",
            validated_commit="0000000000000000000000000000000000000000",
            date="2026-06-07",
        )
        # Intentionally no VALIDATED.md, no SKIP_MCP_TEST.md.
        # Make the fixture root a real git repo so `git rev-parse HEAD`
        # resolves to a genuine (non-zero) sha (mirrors lazy-state.py's
        # stale-mcp-results-reverify fixture setup).
        for cmd in [
            ["git", "-C", str(root), "init", "-q"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "add", "-A"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "fixture"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"step9-stale-mcp-results git setup failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )

    elif name == "step9-fresh-mcp-results":
        # D-3(b) positive guard: MCP_TEST_RESULTS.md whose validated_commit
        # EQUALS the fixture's actual git HEAD is fresh — must auto-validate via
        # __write_validated_from_results__ (Step 9b), not re-verify.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-fmr", "name": "Fresh MCP Results Bug",
                 "spec_dir": "bug-fmr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-fmr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Fresh MCP Results Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-04\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-fmr", date="2026-06-08", rounds=1,
        )
        # Commit the tree FIRST so HEAD exists, then write the results file
        # carrying that exact sha. The post-commit write dirties the working
        # tree but `git rev-parse HEAD` is unaffected.
        for cmd in [
            ["git", "-C", str(root), "init", "-q"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "add", "-A"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "fixture"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"step9-fresh-mcp-results git setup failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
        head_proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        if head_proc.returncode != 0:
            raise RuntimeError(
                f"step9-fresh-mcp-results rev-parse failed: {head_proc.stderr.strip()}"
            )
        fresh_sha = head_proc.stdout.strip()
        _write_yaml_sentinel(
            bdir / "MCP_TEST_RESULTS.md", "mcp-test-results",
            bug_id="bug-fmr", result="all-passing",
            validated_commit=fresh_sha,
            date="2026-06-08",
        )
        # Intentionally no VALIDATED.md, no SKIP_MCP_TEST.md.

    elif name == "step9-docsonly-drift":
        # 2026-06-23 DEADLOCK fix (hardening-log Round 36): MCP_TEST_RESULTS.md
        # records validated_commit == sha A, but HEAD has since advanced to sha B
        # via a PURE DOCS-ONLY (*.md) commit — exactly the structurally-
        # unavoidable one-commit lag that an /mcp-test cycle's own
        # MCP_TEST_RESULTS.md commit produces under the clean-tree turn-end
        # contract. The drift is docs-only, so Step 9 MUST route to write-validated
        # (__write_validated_from_results__), NOT re-verify. RED against pre-fix
        # code (strict validated_commit != HEAD → re-verify deadlock).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-dod", "name": "Docs-Only Drift Bug",
                 "spec_dir": "bug-dod"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-dod"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Docs-Only Drift Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-23\n",
            encoding="utf-8",
        )
        (bdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] Root cause identified\n"
            "- [x] Implement fix\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "RETRO_DONE.md", "retro-done",
            bug_id="bug-dod", date="2026-06-23", rounds=1,
        )
        # Commit A: the validated tree. Capture sha A as the validated_commit.
        for cmd in [
            ["git", "-C", str(root), "init", "-q"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "add", "-A"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "fixture A (validated)"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"step9-docsonly-drift git setup A failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
        head_a = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        if head_a.returncode != 0:
            raise RuntimeError(
                f"step9-docsonly-drift rev-parse A failed: {head_a.stderr.strip()}"
            )
        sha_a = head_a.stdout.strip()
        # Commit B: a PURE DOCS-ONLY (*.md) change. HEAD advances to sha B while
        # validated_commit stays at sha A — drift A→B is docs-only.
        (bdir / "NOTES.md").write_text(
            "# Notes\n\nA docs-only follow-up commit.\n", encoding="utf-8"
        )
        for cmd in [
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "add", "-A"],
            ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "fixture B (docs-only *.md)"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"step9-docsonly-drift git setup B failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
        # MCP_TEST_RESULTS.md records sha A (the validated tree), not HEAD (sha B).
        _write_yaml_sentinel(
            bdir / "MCP_TEST_RESULTS.md", "mcp-test-results",
            bug_id="bug-dod", result="all-passing",
            validated_commit=sha_a,
            date="2026-06-23",
        )
        # Intentionally no VALIDATED.md, no SKIP_MCP_TEST.md.

    elif name == "malformed-queue-entry-diagnostic":
        # D-5: a queue entry missing `name` (or `id`) is dropped inside
        # load_bug_queue BEFORE the compute_state walk loop ever sees it, so
        # the walk-loop diagnostic can never fire. load_bug_queue itself must
        # emit a diagnostic naming the dropped entry. The fixture also carries
        # a dangling-spec_dir entry so the PRE-EXISTING dangling diagnostic is
        # pinned alongside the new one, plus one valid bug that must still be
        # selected normally.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                # Missing `name` → must produce the new load_bug_queue diagnostic.
                {"id": "bug-no-name", "spec_dir": "bug-no-name"},
                # Dangling spec_dir → must keep producing the existing diagnostic.
                {"id": "bug-dangling", "name": "Dangling Bug",
                 "spec_dir": "does-not-exist"},
                # Valid entry → must be selected despite the malformed siblings.
                {"id": "bug-valid", "name": "Valid Bug", "spec_dir": "bug-valid"},
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-valid"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Valid Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-05\n",
            encoding="utf-8",
        )

    elif name == "misnamed-blocker-stray":
        # noncanonical-blocker-filename-invisible-to-state-machine (bug mirror):
        # a blocker under a NON-canonical name, no canonical BLOCKED.md → distinct
        # `blocked-misnamed` terminal.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-mbs", "name": "Misnamed Blocker Bug", "spec_dir": "bug-mbs"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-mbs"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Misnamed Blocker Bug\n\n"
            "**Status:** Investigating\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-09\n",
            encoding="utf-8",
        )
        (bdir / "BLOCKED_2026-06-09-foo.md").write_text(
            "blocker written under a mis-spelled name\n", encoding="utf-8"
        )

    elif name == "misnamed-blocker-resolved-only":
        # A neutralized blocker (BLOCKED_RESOLVED_<date>.md) is excluded by the
        # detector → does NOT halt; an Investigating SPEC with no PHASES routes
        # to spec-bug (investigate) as normal.
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-mbr", "name": "Resolved Blocker Bug", "spec_dir": "bug-mbr"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-mbr"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Resolved Blocker Bug\n\n"
            "**Status:** Investigating\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-09\n",
            encoding="utf-8",
        )
        (bdir / "BLOCKED_RESOLVED_2026-06-09.md").write_text(
            "# Resolved blocker\n", encoding="utf-8"
        )

    elif name == "misnamed-blocker-canonical-precedence":
        # Canonical BLOCKED.md AND a stray both present → canonical `blocked`
        # terminal precedence (no `blocked-misnamed`).
        (bugs_dir / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-mbc", "name": "Canonical Precedence Bug", "spec_dir": "bug-mbc"}
            ]
        }), encoding="utf-8")
        bdir = bugs_dir / "bug-mbc"
        bdir.mkdir()
        (bdir / "SPEC.md").write_text(
            "# Canonical Precedence Bug\n\n"
            "**Status:** Investigating\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-09\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bdir / "BLOCKED.md", "blocked",
            bug_id="bug-mbc", phase="Investigation",
            blocked_at="2026-06-09T09:00:00Z", retry_count=0,
        )
        (bdir / "BLOCKED_2026-06-09-foo.md").write_text(
            "a co-present stray\n", encoding="utf-8"
        )

    else:
        raise ValueError(f"Unknown fixture name: {name!r}")

    return root


def run_smoke_tests() -> int:
    """Build fixtures in a temp dir, call compute_state(), assert expected shapes.

    Prints PASS/FAIL per fixture and a summary.  Returns 0 when all fixtures pass,
    1 otherwise.  Each fixture builds a synthetic repo tree, calls the fully
    implemented compute_state() (and a few helper functions directly such as
    enqueue_adhoc), and asserts the returned dict against expected values.
    """
    failures: list[str] = []

    # -----------------------------------------------------------------------
    # Fixture table.  Each entry is a tuple:
    #   (fixture_name, cloud, real_device, expected_dict, extra_assertions?)
    # extra_assertions is an optional callable(got, failures, fixture_name).
    # -----------------------------------------------------------------------

    def _assert_device_deferred_populated(
        got: dict[str, Any], failures: list[str], name: str
    ) -> None:
        """device_deferred_features must be non-empty for the device-deferred fixture."""
        ddf = got.get("device_deferred_features")
        if not ddf:
            failures.append(
                f"[{name}] expected device_deferred_features to be populated; "
                f"got {ddf!r}"
            )

    def _assert_queued_bug_first(
        got: dict[str, Any], failures: list[str], name: str
    ) -> None:
        """hybrid-ordering: the bug listed in queue.json must be returned first."""
        fid = got.get("feature_id")
        if fid != "bug-queued":
            failures.append(
                f"[{name}] expected queued bug ('bug-queued') to be selected first "
                f"(queue overrides severity); got feature_id={fid!r}"
            )

    def _assert_unknown_host_capability_blocked(
        got: dict[str, Any], failures: list[str], name: str
    ) -> None:
        """host-capability parity: the fail-fast must write a canonical BLOCKED.md
        carrying blocker_kind: unknown-host-capability whose body names the
        offending unregistered id (mirrors the feature-pipeline assertion)."""
        spec_path = got.get("spec_path")
        if not spec_path:
            failures.append(f"[{name}] no spec_path in state to locate BLOCKED.md")
            return
        blocked = Path(spec_path) / "BLOCKED.md"
        if not blocked.exists():
            failures.append(
                f"[{name}] expected a BLOCKED.md to be written by the "
                f"unknown-host-capability fail-fast at {blocked}"
            )
            return
        meta = parse_sentinel(blocked) or {}
        if meta.get("blocker_kind") != "unknown-host-capability":
            failures.append(
                f"[{name}] expected blocker_kind 'unknown-host-capability'; "
                f"got {meta.get('blocker_kind')!r}"
            )
        text = blocked.read_text(encoding="utf-8")
        if "typo-cap" not in text:
            failures.append(
                f"[{name}] BLOCKED.md body must name the offending id 'typo-cap'; "
                f"not found in {blocked}"
            )

    cases: list[tuple] = [
        # 1. Fresh Open Bug — no investigation, no PHASES → spec-bug (investigate)
        (
            "fresh-open-bug", False, True,
            {
                "feature_id": "bug-fresh",
                "sub_skill": SKILL_INVESTIGATE,
                "current_step": STEP_INVESTIGATE,
            },
        ),
        # 2. Blocked — BLOCKED.md present → terminal blocked
        (
            "blocked", False, True,
            {
                "feature_id": "bug-blocked",
                "terminal_reason": TR_BLOCKED,
                "current_step": STEP_BLOCKED,
            },
        ),
        # 2a. Mis-named blocker (stray, no canonical) → blocked-misnamed terminal
        # (noncanonical-blocker-filename-invisible-to-state-machine, bug mirror).
        # terminal_reason value is IDENTICAL to the feature pipeline's.
        (
            "misnamed-blocker-stray", False, True,
            {
                "feature_id": "bug-mbs",
                "terminal_reason": TR_BLOCKED_MISNAMED,
                "current_step": STEP_BLOCKED_MISNAMED,
            },
        ),
        # 2b. Neutralized blocker (BLOCKED_RESOLVED_<date>.md) excluded → does NOT
        # halt; Investigating SPEC + no PHASES → spec-bug (investigate).
        (
            "misnamed-blocker-resolved-only", False, True,
            {
                "feature_id": "bug-mbr",
                "sub_skill": SKILL_INVESTIGATE,
                "current_step": STEP_INVESTIGATE,
            },
        ),
        # 2c. Canonical BLOCKED.md + stray both present → canonical `blocked`
        # precedence (no `blocked-misnamed`).
        (
            "misnamed-blocker-canonical-precedence", False, True,
            {
                "feature_id": "bug-mbc",
                "terminal_reason": TR_BLOCKED,
            },
        ),
        # 3. Mid-fix — In-progress + PHASES + Ready plan → execute-plan
        (
            "mid-fix", False, True,
            {
                "feature_id": "bug-midfix",
                "sub_skill": SKILL_EXECUTE_PLAN,
                "current_step": STEP_EXECUTE_PLAN,
            },
        ),
        # 3a. plan-structure-authoring-gate Phase 4 pickup backstop (bug-
        # pipeline parity): a FRESH structurally-invalid plan (zero ticked
        # WUs) refuses the route.
        (
            "plan-structural-backstop-refuses-fresh-invalid", False, True,
            {
                "feature_id": "bug-pstruct-fresh",
                "terminal_reason": TR_BLOCKED,
            },
        ),
        # 3a'. Same defect, mid-execution (>=1 ticked WU) — WARN-only, falls
        # through to execute-plan as normal.
        (
            "plan-structural-backstop-mid-execution-warns", False, True,
            {
                "feature_id": "bug-pstruct-mid",
                "sub_skill": SKILL_EXECUTE_PLAN,
                "current_step": STEP_EXECUTE_PLAN,
            },
        ),
        # 3b. Stale-plan flip (bug-pipeline-missing-stale-plan-flip) — the head
        # plan's phases: [1] scope is fully [x] but Phase 2 has an unchecked row
        # (unchecked > 0 overall). The plan's frontmatter is still In-progress →
        # STALE → __flip_plan_complete_stale__ (workstation mirror of
        # lazy-state.py Step 7a), NOT a redundant execute-plan re-dispatch.
        (
            "bug-stale-plan-flips", False, True,
            {
                "feature_id": "bug-stale",
                "sub_skill": "__flip_plan_complete_stale__",
            },
        ),
        # 4. Phases complete (retro unwired) → Step 9 mcp-test directly
        (
            "phases-complete-no-retro", False, True,
            {
                "feature_id": "bug-pcnr",
                "sub_skill": SKILL_MCP_TEST,
                "current_step": STEP_MCP,
            },
        ),
        # 4b. PHASES not-required + no app surface → Step 9 short-circuits to
        # the inline structural skip grant (no /mcp-test dispatch).
        (
            "phases-complete-no-mcp-surface", False, True,
            {
                "feature_id": "bug-noms",
                "sub_skill": "__grant_skip_no_mcp_surface__",
                "current_step": "Step 9: structural MCP-skip (no app surface)",
            },
        ),
        # 5. Retro done, no VALIDATED.md, non-cloud non-device host → mcp-test
        (
            "retro-done-needs-mcp", False, True,
            {
                "feature_id": "bug-rdnm",
                "sub_skill": SKILL_MCP_TEST,
                "current_step": STEP_MCP,
            },
        ),
        # 6. RETRO_DONE + VALIDATED → __mark_fixed__
        (
            "ready-to-mark-fixed", False, True,
            {
                "feature_id": "bug-rtmf",
                "sub_skill": SKILL_MARK_FIXED,
                "current_step": STEP_MARK_FIXED,
            },
        ),
        # 7. Device-deferred on a no-real-device host → device-queue-exhausted
        #    AND device_deferred_features populated.
        (
            "device-deferred", False, False,
            {
                "terminal_reason": TR_DEVICE_QUEUE_EXHAUSTED,
            },
            _assert_device_deferred_populated,
        ),
        # 8. Hybrid ordering: queued bug (P2) must come before unlisted P0 bug
        (
            "hybrid-ordering", False, True,
            {
                "feature_id": "bug-queued",
            },
            _assert_queued_bug_first,
        ),
        # 9. Won't-fix (no receipt) → receipt-EXEMPT → all-bugs-fixed (only bug)
        (
            "wont-fix-exempt", False, True,
            {
                "terminal_reason": TR_ALL_BUGS_FIXED,
            },
        ),
        # 10. Fixed + no FIXED.md receipt → completion-unverified halt
        (
            "fixed-no-receipt-halt", False, True,
            {
                "feature_id": "bug-fnr",
                "terminal_reason": TR_COMPLETION_UNVERIFIED,
                "current_step": STEP_COMPLETION_UNVERIFIED,
            },
        ),
        # Bonus: all-bugs-fixed — no open bugs anywhere
        (
            "all-bugs-fixed", False, True,
            {
                "terminal_reason": TR_ALL_BUGS_FIXED,
            },
        ),
        # 12. STALE_UPSTREAM.md present → compute_state halts with terminal_reason "stale_upstream"
        (
            "stale-upstream-halt", False, True,
            {
                "terminal_reason": "stale_upstream",
            },
        ),
        # 13. Operator-deferred skip: deferred bug is skipped; actionable bug is selected
        (
            "operator-deferred-skip", False, True,
            {
                "feature_id": "bug-actionable",
                "sub_skill": SKILL_INVESTIGATE,
                "current_step": STEP_INVESTIGATE,
            },
        ),
        # 14. All operator-deferred: only remaining bug has DEFERRED.md → all-remaining-deferred
        (
            "all-operator-deferred", False, True,
            {
                "terminal_reason": TR_ALL_DEFERRED,
            },
        ),
        # 15. Cloud-defer-mcp: cloud=True, RETRO_DONE present, no VALIDATED/SKIP/DEFERRED files
        #     → cloud defers MCP to workstation (STEP_CLOUD_DEFER_MCP)
        (
            "cloud-defer-mcp", True, False,
            {
                "current_step": STEP_CLOUD_DEFER_MCP,
                "sub_skill": "__write_deferred_non_cloud__",
            },
        ),
        # 16. Cloud-skip-mcp: cloud=True, RETRO_DONE + SKIP_MCP_TEST present, no VALIDATED
        #     → STEP_MCP_SKIP with __write_validated_from_skip__
        (
            "cloud-skip-mcp", True, False,
            {
                "current_step": STEP_MCP_SKIP,
                "sub_skill": "__write_validated_from_skip__",
            },
        ),
        # 17. Device-reopen: real_device=True, RETRO_DONE + DEFERRED_REQUIRES_DEVICE present
        #     → re-open deferred device scenarios (STEP_DEVICE_REOPEN)
        (
            "device-reopen", False, True,
            {
                "current_step": STEP_DEVICE_REOPEN,
                "sub_skill": SKILL_MCP_TEST,
            },
        ),
        # 18. Step-9 workstation skip: RETRO_DONE + SKIP_MCP_TEST, no VALIDATED, no device deferral
        #     → STEP_MCP_SKIP with __write_validated_from_skip__
        (
            "step9-skip-mcp", False, True,
            {
                "current_step": STEP_MCP_SKIP,
                "sub_skill": "__write_validated_from_skip__",
            },
        ),
        # 18b. skip-mcp-test-frontmatter-unquoted-colon Phase 2: SKIP_MCP_TEST.md
        #      with an UNQUOTED colon-space `reason:` → STEP_MCP_SKIP with
        #      __write_validated_from_skip__ (parse_sentinel tolerant read), not
        #      an exit-2 hard-halt at the strict YAML parse. RED before Phase 1.
        (
            "step9-skip-colon-reason", False, True,
            {
                "current_step": STEP_MCP_SKIP,
                "sub_skill": "__write_validated_from_skip__",
            },
        ),
        # 19. Step-9 workstation MCP results: RETRO_DONE + MCP_TEST_RESULTS (all-passing)
        #     → "Step 9b: write validated" with __write_validated_from_results__
        (
            "step9-mcp-results", False, True,
            {
                "current_step": "Step 9b: write validated",
                "sub_skill": "__write_validated_from_results__",
            },
        ),
        # 20. Severity ordering: empty queue, two unlisted P0/P2 bugs → P0 selected first
        (
            "severity-ordering", False, True,
            {
                "feature_id": "bug-sev-p0",
                "current_step": STEP_INVESTIGATE,
            },
        ),
        # 21. Cloud + DEFERRED_NON_CLOUD.md present + no VALIDATED.md → must HALT
        #     (cloud-queue-exhausted), NOT silently __mark_fixed__.
        #     RED against current code; GREEN after WU-2.2 impl-agent adds the guard.
        (
            "cloud-defer-no-validate-halts", True, False,
            {
                "terminal_reason": TR_CLOUD_QUEUE_EXHAUSTED,
            },
            # Extra assertion: must NOT route to __mark_fixed__ regardless of what
            # current_step says.  Catches the silent fall-through bug.
            lambda got, failures, name: (
                failures.append(
                    f"[{name}] sub_skill must NOT be SKILL_MARK_FIXED "
                    f"({SKILL_MARK_FIXED!r}); got sub_skill={got.get('sub_skill')!r}"
                )
                if got.get("sub_skill") == SKILL_MARK_FIXED
                else None
            ),
        ),
        # 22. queue.json entirely absent → queue-missing terminal (not all-bugs-fixed).
        #     Characterization test for the newly-wired TR_QUEUE_MISSING terminal.
        (
            "queue-json-missing", False, True,
            {
                "terminal_reason": TR_QUEUE_MISSING,
            },
        ),
        # 23. Unqueued Fixed-no-receipt bypass pin (WU-3).
        #     An on-disk bug marked Fixed but lacking FIXED.md, NOT in queue.json,
        #     must be surfaced by _find_open_bug_dirs and halted by the receipt gate
        #     with terminal_reason == TR_COMPLETION_UNVERIFIED.
        #     RED against current code (_find_open_bug_dirs pre-filters all Fixed dirs,
        #     so it returns [] → pipeline sees no open bugs → TR_ALL_BUGS_FIXED).
        (
            "unqueued-fixed-no-receipt-halt", False, True,
            {
                "terminal_reason": TR_COMPLETION_UNVERIFIED,
            },
        ),
        # 24. concluded-investigation-plan-bug (RED — pin the infinite-loop bug).
        #     SPEC.md marked **Status:** Concluded + no PHASES.md → must dispatch
        #     plan-bug (not spec-bug again) so the pipeline can author PHASES.md.
        #     Current code always routes to SKILL_INVESTIGATE ("spec-bug") at Step 4
        #     regardless of SPEC status → this fixture is RED until impl-agent fixes it.
        (
            "concluded-investigation-plan-bug", False, True,
            {
                "feature_id": "bug-concluded",
                "sub_skill": "plan-bug",
                "current_step": STEP_PLAN_BUG,
            },
            # Extra: sub_skill_args must point at the SPEC.md (path ends with SPEC.md).
            lambda got, failures, name: (
                failures.append(
                    f"[{name}] sub_skill_args must end with 'SPEC.md'; "
                    f"got sub_skill_args={got.get('sub_skill_args')!r}"
                )
                if not str(got.get("sub_skill_args") or "").endswith("SPEC.md")
                else None
            ),
        ),
        # 25. concluded-investigation-guard-still-spec-bug (GREEN — discriminating guard).
        #     SPEC.md marked **Status:** Investigating + no PHASES.md → must still dispatch
        #     spec-bug.  Proves the "Concluded" marker is the exclusive trigger; an
        #     Investigating SPEC must remain on spec-bug both before AND after the fix.
        (
            "concluded-investigation-guard-still-spec-bug", False, True,
            {
                "feature_id": "bug-still-investigating",
                "sub_skill": SKILL_INVESTIGATE,
                "current_step": STEP_INVESTIGATE,
            },
        ),
        # 26. D-3(a) provenance gate: pipeline-self-granted SKIP_MCP_TEST.md must
        #     NOT vacuously validate — halt with needs-input for operator review.
        #     RED against pre-fix code (which emitted __write_validated_from_skip__).
        (
            "step9-skip-pipeline-granted", False, True,
            {
                "feature_id": "bug-spg",
                "terminal_reason": TR_NEEDS_INPUT,
                "current_step": STEP_MCP_SKIP_PIPELINE_GRANTED,
            },
            # Extra: must NOT route to the vacuous-validate write.
            lambda got, failures, name: (
                failures.append(
                    f"[{name}] sub_skill must NOT be '__write_validated_from_skip__'; "
                    f"got sub_skill={got.get('sub_skill')!r}"
                )
                if got.get("sub_skill") == "__write_validated_from_skip__"
                else None
            ),
        ),
        # 27. D-3(a) positive guard: operator-granted SKIP_MCP_TEST.md remains a
        #     legitimate waiver → __write_validated_from_skip__ (non-regression).
        (
            "step9-skip-operator-granted", False, True,
            {
                "feature_id": "bug-sog",
                "current_step": STEP_MCP_SKIP,
                "sub_skill": "__write_validated_from_skip__",
            },
        ),
        # 27a. Provenance positive: granted_by: mcp-test + spec_class citation is
        #      a verified structural assessment → __write_validated_from_skip__.
        (
            "step9-skip-mcp-test-granted-with-class", False, True,
            {
                "feature_id": "bug-smtc",
                "current_step": STEP_MCP_SKIP,
                "sub_skill": "__write_validated_from_skip__",
            },
        ),
        # 27b. Provenance gate: granted_by: mcp-test WITHOUT spec_class is an
        #      unverified claim → needs-input, never vacuous-validate.
        (
            "step9-skip-mcp-test-granted-missing-class", False, True,
            {
                "feature_id": "bug-smtn",
                "terminal_reason": TR_NEEDS_INPUT,
                "current_step": STEP_MCP_SKIP_PIPELINE_GRANTED,
            },
            lambda got, failures, name: (
                failures.append(
                    f"[{name}] sub_skill must NOT be '__write_validated_from_skip__'; "
                    f"got sub_skill={got.get('sub_skill')!r}"
                )
                if got.get("sub_skill") == "__write_validated_from_skip__"
                else None
            ),
        ),
        # 27c. Provenance omission gate: pipeline-authored skip (skipped_by:
        #      lazy) with NO granted_by → needs-input (closes the side-door
        #      where omitting the field bypassed the WU-5 gate).
        (
            "step9-skip-pipeline-authored-no-grant", False, True,
            {
                "feature_id": "bug-spa",
                "terminal_reason": TR_NEEDS_INPUT,
                "current_step": STEP_MCP_SKIP_PIPELINE_GRANTED,
            },
            lambda got, failures, name: (
                failures.append(
                    f"[{name}] sub_skill must NOT be '__write_validated_from_skip__'; "
                    f"got sub_skill={got.get('sub_skill')!r}"
                )
                if got.get("sub_skill") == "__write_validated_from_skip__"
                else None
            ),
        ),
        # 28. D-3(b) freshness gate: all-passing MCP_TEST_RESULTS.md with a stale
        #     validated_commit (all-zeros ≠ real HEAD) must re-verify via mcp-test,
        #     NOT auto-validate. RED against pre-fix code.
        (
            "step9-stale-mcp-results", False, True,
            {
                "feature_id": "bug-smr",
                "current_step": STEP_MCP_STALE_RESULTS,
                "sub_skill": SKILL_MCP_TEST,
            },
        ),
        # 29. D-3(b) positive guard: validated_commit == actual HEAD is fresh →
        #     Step 9b auto-validate via __write_validated_from_results__.
        (
            "step9-fresh-mcp-results", False, True,
            {
                "feature_id": "bug-fmr",
                "current_step": "Step 9b: write validated",
                "sub_skill": "__write_validated_from_results__",
            },
        ),
        # 29b. 2026-06-23 DEADLOCK fix (hardening-log Round 36): validated_commit
        #      (sha A) != HEAD (sha B) but the A→B drift is PURE DOCS-ONLY (*.md)
        #      — the structurally-unavoidable one-commit lag from the /mcp-test
        #      cycle committing its own MCP_TEST_RESULTS.md. MUST route to Step 9b
        #      write-validated, NOT re-verify. RED against pre-fix code (strict
        #      validated_commit != HEAD re-verified → infinite deadlock loop).
        (
            "step9-docsonly-drift", False, True,
            {
                "feature_id": "bug-dod",
                "current_step": "Step 9b: write validated",
                "sub_skill": "__write_validated_from_results__",
            },
        ),
        # 30. D-5: queue entry missing `name` is dropped by load_bug_queue and
        #     must be DIAGNOSED there (the walk-loop diagnostic is unreachable
        #     for it). The dangling-spec_dir diagnostic must keep firing, and
        #     the valid sibling bug must still be dispatched normally.
        #     RED against pre-fix code (load_bug_queue dropped silently →
        #     diagnostics empty).
        (
            "malformed-queue-entry-diagnostic", False, True,
            {
                "feature_id": "bug-valid",
                "current_step": STEP_INVESTIGATE,
            },
            lambda got, failures, name: (
                failures.append(
                    f"[{name}] expected a load_bug_queue diagnostic naming the "
                    f"entry missing 'name' (id 'bug-no-name') AND the dangling "
                    f"'bug-dangling' diagnostic; got diagnostics="
                    f"{got.get('diagnostics')!r}"
                )
                if not (
                    any(
                        "missing name" in d and "bug-no-name" in d
                        for d in got.get("diagnostics") or []
                    )
                    and any(
                        "dangling" in d and "bug-dangling" in d
                        for d in got.get("diagnostics") or []
                    )
                )
                else None
            ),
        ),
        # 31. host-capability parity (Phase 6): a bug declaring an UNREGISTERED
        #     requires_host: id must FAIL FAST — terminal_reason "blocked" with
        #     blocker_kind: unknown-host-capability — exactly like the feature
        #     pipeline, NEVER a silent defer-forever.
        (
            "requires-host-unknown-failfast", False, True,
            {
                "feature_id": "bug-rhuf",
                "terminal_reason": TR_BLOCKED,
                "current_step": STEP_BLOCKED,
            },
            # Extra: BLOCKED.md must carry blocker_kind: unknown-host-capability
            # and the body must name the offending id.
            lambda got, failures, name: _assert_unknown_host_capability_blocked(
                got, failures, name
            ),
        ),
        # 32. host-capability parity (Phase 6, discriminating guard): a bug
        #     declaring ONLY registered requires_host: ids must NOT trip the
        #     fail-fast — it proceeds to its normal lifecycle step (spec-bug).
        (
            "requires-host-registered-no-failfast", False, True,
            {
                "feature_id": "bug-rhrn",
                "sub_skill": SKILL_INVESTIGATE,
                "current_step": STEP_INVESTIGATE,
            },
        ),
    ]

    with tempfile.TemporaryDirectory(prefix="bug-state-fixtures-") as td:
        td_path = Path(td)

        for case in cases:
            # Unpack: required 4 elements + optional extra_assertions callable
            fix_name: str = case[0]
            cloud: bool = case[1]
            real_device: bool = case[2]
            expected: dict[str, Any] = case[3]
            extra_fn = case[4] if len(case) > 4 else None

            root = _build_bug_fixture(td_path, fix_name)

            try:
                got = compute_state(root, cloud=cloud, real_device=real_device)
            except NotImplementedError as exc:
                # Defensive: compute_state is implemented, so this NotImplementedError guard is now dead code retained for harness symmetry.
                failures.append(
                    f"[{fix_name}] NotImplementedError (stub not yet implemented): {exc}"
                )
                print(
                    f"  FAIL [{fix_name}] cloud={cloud} real_device={real_device}: "
                    f"NotImplementedError — {exc}"
                )
                continue
            except SystemExit as exc:
                failures.append(f"[{fix_name}] unexpected SystemExit: {exc.code}")
                print(f"  FAIL [{fix_name}]: SystemExit({exc.code})")
                continue

            # Assert each expected key
            case_ok = True
            for k, v in expected.items():
                if got.get(k) != v:
                    failures.append(
                        f"[{fix_name}] expected {k}={v!r}, got {k}={got.get(k)!r}"
                    )
                    case_ok = False

            # Run extra per-fixture assertions if provided
            if extra_fn is not None:
                pre_fail_count = len(failures)
                extra_fn(got, failures, fix_name)
                if len(failures) > pre_fail_count:
                    case_ok = False

            step_or_terminal = got.get("current_step") or got.get("terminal_reason")
            status_marker = "PASS" if case_ok else "FAIL"
            print(
                f"  {status_marker} [{fix_name}] cloud={cloud} "
                f"real_device={real_device}: {step_or_terminal}"
            )

        # -------------------------------------------------------------------
        # Fixture 12: enqueue_adhoc writes a spec_dir-keyed queue entry.
        # Calls enqueue_adhoc directly (not via compute_state).
        # Defensive: enqueue_adhoc is implemented; the NotImplementedError guard below is dead code retained for harness symmetry.
        # -------------------------------------------------------------------
        fix_name_ea = "enqueue-adhoc-writes-entry"
        root_ea = _build_bug_fixture(td_path, fix_name_ea)
        try:
            enqueue_adhoc(
                root_ea, "1234", "Fix the thing",
                spec_dir="fix-the-thing", severity="P1",
            )
            # If we reach here (post-impl), assert the queue entry was written.
            queue_path_ea = root_ea / "docs" / "bugs" / "queue.json"
            data_ea = json.loads(queue_path_ea.read_text(encoding="utf-8"))
            queue_ea = data_ea.get("queue", [])
            entry_ea = next((e for e in queue_ea if e.get("id") == "1234"), None)
            ea_ok = True
            if entry_ea is None:
                failures.append(
                    f"[{fix_name_ea}] no queue entry with id='1234' found in queue.json"
                )
                ea_ok = False
            else:
                for field, val in [
                    ("name", "Fix the thing"),
                    ("spec_dir", "fix-the-thing"),
                    ("severity", "P1"),
                ]:
                    if entry_ea.get(field) != val:
                        failures.append(
                            f"[{fix_name_ea}] expected entry[{field!r}]={val!r}, "
                            f"got {entry_ea.get(field)!r}"
                        )
                        ea_ok = False
            print(
                f"  {'PASS' if ea_ok else 'FAIL'} [{fix_name_ea}] "
                f"entry written with correct fields"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_ea}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_ea}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture 13: enqueue_adhoc is idempotent — duplicate id is a no-op.
        # Calls enqueue_adhoc twice with the same id; second call MUST NOT raise.
        # Defensive: enqueue_adhoc is implemented; the NotImplementedError guard below is dead code retained for harness symmetry.
        # -------------------------------------------------------------------
        fix_name_idem = "enqueue-adhoc-idempotent"
        root_idem = _build_bug_fixture(td_path, fix_name_idem)
        try:
            enqueue_adhoc(
                root_idem, "9999", "Dup Bug",
                spec_dir="dup-bug", severity="P2",
            )
            # Second call: same id, different name+severity — MUST be a silent no-op.
            enqueue_adhoc(
                root_idem, "9999", "Dup Bug (second attempt)",
                spec_dir="dup-bug", severity="P1",
            )
            # Assert exactly one entry for id "9999".
            queue_path_idem = root_idem / "docs" / "bugs" / "queue.json"
            data_idem = json.loads(queue_path_idem.read_text(encoding="utf-8"))
            entries_for_id = [e for e in data_idem.get("queue", []) if e.get("id") == "9999"]
            idem_ok = True
            if len(entries_for_id) != 1:
                failures.append(
                    f"[{fix_name_idem}] expected exactly 1 entry for id='9999' after "
                    f"two enqueue calls; got {len(entries_for_id)}"
                )
                idem_ok = False
            print(
                f"  {'PASS' if idem_ok else 'FAIL'} [{fix_name_idem}] "
                f"idempotent: {len(entries_for_id)} entry(ies) after 2 calls"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_idem}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_idem}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # scoped-bug-id: compute_state() with scope_bug_id="bug-scope-beta"
        # must advance the SECOND bug in the queue, not the default first one.
        # scope_bug_id is now implemented; the TypeError guard below is dead code
        # retained for harness symmetry.
        # -------------------------------------------------------------------
        fix_name_scope = "scope-bug-id-two-bugs"
        root_scope = _build_bug_fixture(td_path, fix_name_scope)
        try:
            got_scope = compute_state(
                root_scope, cloud=False, real_device=True,
                scope_bug_id="bug-scope-beta",
            )
            # Post-impl: assert it advanced beta, not alpha.
            scope_ok = True
            fid_scope = got_scope.get("feature_id")
            if fid_scope != "bug-scope-beta":
                failures.append(
                    f"[{fix_name_scope}] scoped-bug-id: expected feature_id='bug-scope-beta', "
                    f"got {fid_scope!r}"
                )
                scope_ok = False
            # Also must NOT have advanced alpha (the default pick).
            if fid_scope == "bug-scope-alpha":
                failures.append(
                    f"[{fix_name_scope}] scoped-bug-id: erroneously advanced 'bug-scope-alpha' "
                    "instead of scoped 'bug-scope-beta'"
                )
                scope_ok = False
            print(
                f"  {'PASS' if scope_ok else 'FAIL'} [{fix_name_scope}] "
                f"scoped-bug-id: feature_id={fid_scope!r}"
            )
        except TypeError as exc:
            # Defensive: compute_state is implemented, so this TypeError guard is now dead code retained for harness symmetry.
            failures.append(
                f"[{fix_name_scope}] scoped-bug-id: TypeError (scope_bug_id param missing): {exc}"
            )
            print(
                f"  FAIL [{fix_name_scope}] scoped-bug-id: "
                f"TypeError — {exc}"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_scope}] scoped-bug-id: NotImplementedError: {exc}"
            )
            print(f"  FAIL [{fix_name_scope}] scoped-bug-id: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # baseline-regression-default (GREEN guard): compute_state() WITHOUT
        # scope_bug_id on the SAME two-bug queue must still advance the FIRST
        # actionable bug (bug-scope-alpha).  Proves the new param is non-breaking.
        # This is intentionally GREEN before AND after impl — a regression guard.
        # -------------------------------------------------------------------
        fix_name_base = "scope-bug-id-two-bugs"  # reuse same fixture root
        root_base = _build_bug_fixture(td_path, fix_name_base)
        try:
            got_base = compute_state(root_base, cloud=False, real_device=True)
            base_ok = True
            fid_base = got_base.get("feature_id")
            step_base = got_base.get("current_step")
            if fid_base != "bug-scope-alpha":
                failures.append(
                    f"[baseline-regression-default] expected feature_id='bug-scope-alpha' "
                    f"(default queue order), got {fid_base!r}"
                )
                base_ok = False
            if step_base != STEP_INVESTIGATE:
                failures.append(
                    f"[baseline-regression-default] expected current_step={STEP_INVESTIGATE!r}, "
                    f"got {step_base!r}"
                )
                base_ok = False
            print(
                f"  {'PASS' if base_ok else 'FAIL'} [baseline-regression-default] "
                f"default picks alpha: feature_id={fid_base!r} step={step_base!r}"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[baseline-regression-default] NotImplementedError: {exc}"
            )
            print(
                f"  FAIL [baseline-regression-default]: NotImplementedError — {exc}"
            )

        # -------------------------------------------------------------------
        # scoped-bug-id-not-found  (RED until impl lands)
        # Same two-bug queue as the scope-bug-id-two-bugs fixture above; but
        # the scope_bug_id is a typo'd id that matches NO queue entry.
        # EXPECTED: terminal_reason == "scoped-id-not-found"
        # CURRENT (pre-fix): falls through to terminal_reason == "all-bugs-fixed"
        # The impl agent must emit a distinct terminal so callers can distinguish
        # "queue exhausted" from "id was never in the queue at all".
        # -------------------------------------------------------------------
        fix_not_found = "scoped-bug-id-not-found"
        root_not_found = _build_bug_fixture(td_path, "scope-bug-id-two-bugs")
        try:
            got_not_found = compute_state(
                root_not_found, cloud=False, real_device=True,
                scope_bug_id="bug-typo-does-not-exist",
            )
            actual_tr = got_not_found.get("terminal_reason")
            if actual_tr == "scoped-id-not-found":
                print(f"  PASS [{fix_not_found}] terminal_reason='scoped-id-not-found' (impl landed)")
            else:
                failures.append(
                    f"[{fix_not_found}] expected terminal_reason='scoped-id-not-found', "
                    f"got {actual_tr!r}"
                )
                print(f"  FAIL [{fix_not_found}] expected 'scoped-id-not-found', got {actual_tr!r}")
        except (TypeError, NotImplementedError, SystemExit) as e:
            failures.append(f"[{fix_not_found}] unexpected exception: {type(e).__name__}: {e}")
            print(f"  FAIL [{fix_not_found}] {type(e).__name__} — {e}")

        # -------------------------------------------------------------------
        # scoped-deferred-identity bespoke block
        # (bug-state-scoped-query-loses-deferred-bug-identity, Phase 1).
        #
        # A scoped --bug-id query against a SKIPPED-but-matched queue entry must
        # return the bug's OWN identity + a scoped per-bug deferred terminal —
        # NOT fall through to the global null-identity terminal (which renders
        # "unknown" downstream in LAZY_QUEUE.md).
        #
        #   Fixture A (scoped operator-deferred): one DEFERRED.md bug, scoped to
        #     it → feature_id == bug-id, spec_path non-null & ends in the bug-id,
        #     terminal_reason == "operator-deferred" (the scoped literal). NOT
        #     feature_id None / "all-remaining-deferred".
        #   Fixture B (unscoped baseline regression): SAME fixture, no scope →
        #     terminal_reason == "all-remaining-deferred", feature_id is None
        #     (byte-identical to pre-fix global behavior).
        #   Fixture C1 (scoped cloud-saturated): a DEFERRED_NON_CLOUD.md bug past
        #     implementation, cloud=True, scoped → bug-id + scoped cloud terminal.
        #   Fixture C2 (scoped device-saturated): a DEFERRED_REQUIRES_DEVICE.md
        #     bug past implementation, real_device=False, scoped → bug-id +
        #     scoped device terminal.
        # -------------------------------------------------------------------

        def _seed_phases_complete(bdir: Path) -> None:
            # Minimal PHASES.md that _phases_effectively_complete() treats as
            # past-implementation (no unchecked impl rows). Required so the
            # cloud/device skip branches engage.
            (bdir / "PHASES.md").write_text(
                "# Implementation Phases\n\n"
                "**Status:** In-progress\n\n"
                "### Phase 1: Done\n\n"
                "**Deliverables:**\n"
                "- [x] Everything implemented.\n",
                encoding="utf-8",
            )

        # --- Fixtures A + B: scoped operator-deferred + unscoped regression ---
        scoped_def_root = td_path / "scoped-operator-deferred"
        scoped_def_bugs = scoped_def_root / "docs" / "bugs"
        scoped_def_bugs.mkdir(parents=True, exist_ok=True)
        (scoped_def_bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-scoped-def", "name": "Scoped Deferred Bug",
                 "spec_dir": "bug-scoped-def"},
            ]
        }), encoding="utf-8")
        bsd = scoped_def_bugs / "bug-scoped-def"
        bsd.mkdir()
        (bsd / "SPEC.md").write_text(
            "# Scoped Deferred Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bsd / "DEFERRED.md", "deferred",
            bug_id="bug-scoped-def",
            reason="Operator parked for scoped-identity test.",
            deferred_at="2026-06-01",
        )

        # Fixture A — scoped query returns the bug's identity + scoped terminal.
        fix_scoped_def = "scoped-operator-deferred-identity"
        try:
            got_sda = compute_state(
                scoped_def_root, cloud=False, real_device=True,
                scope_bug_id="bug-scoped-def",
            )
            sda_ok = True
            if got_sda.get("feature_id") != "bug-scoped-def":
                failures.append(
                    f"[{fix_scoped_def}] expected feature_id='bug-scoped-def', "
                    f"got {got_sda.get('feature_id')!r}"
                )
                sda_ok = False
            sp = got_sda.get("spec_path")
            if not sp or not str(sp).replace("\\", "/").endswith("bug-scoped-def"):
                failures.append(
                    f"[{fix_scoped_def}] expected non-null spec_path ending in "
                    f"'bug-scoped-def', got {sp!r}"
                )
                sda_ok = False
            if got_sda.get("terminal_reason") != TR_OPERATOR_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_def}] expected terminal_reason="
                    f"{TR_OPERATOR_DEFERRED_SCOPED!r}, got "
                    f"{got_sda.get('terminal_reason')!r}"
                )
                sda_ok = False
            # Must NOT be the global null-identity terminal.
            if got_sda.get("terminal_reason") == TR_ALL_DEFERRED:
                failures.append(
                    f"[{fix_scoped_def}] scoped query erroneously returned global "
                    f"{TR_ALL_DEFERRED!r} (identity lost)"
                )
                sda_ok = False
            print(
                f"  {'PASS' if sda_ok else 'FAIL'} [{fix_scoped_def}] "
                f"feature_id={got_sda.get('feature_id')!r} "
                f"terminal_reason={got_sda.get('terminal_reason')!r}"
            )
        except Exception as exc:
            failures.append(f"[{fix_scoped_def}] unexpected error: {type(exc).__name__}: {exc}")
            print(f"  FAIL [{fix_scoped_def}] {type(exc).__name__} — {exc}")

        # Fixture B — UNSCOPED baseline regression: same fixture, no scope.
        fix_unscoped_def = "unscoped-operator-deferred-regression"
        try:
            got_usd = compute_state(scoped_def_root, cloud=False, real_device=True)
            usd_ok = True
            if got_usd.get("terminal_reason") != TR_ALL_DEFERRED:
                failures.append(
                    f"[{fix_unscoped_def}] expected terminal_reason="
                    f"{TR_ALL_DEFERRED!r} (global, unscoped), got "
                    f"{got_usd.get('terminal_reason')!r}"
                )
                usd_ok = False
            if got_usd.get("feature_id") is not None:
                failures.append(
                    f"[{fix_unscoped_def}] expected feature_id=None (global "
                    f"terminal), got {got_usd.get('feature_id')!r}"
                )
                usd_ok = False
            print(
                f"  {'PASS' if usd_ok else 'FAIL'} [{fix_unscoped_def}] "
                f"feature_id={got_usd.get('feature_id')!r} "
                f"terminal_reason={got_usd.get('terminal_reason')!r}"
            )
        except Exception as exc:
            failures.append(f"[{fix_unscoped_def}] unexpected error: {type(exc).__name__}: {exc}")
            print(f"  FAIL [{fix_unscoped_def}] {type(exc).__name__} — {exc}")

        # --- Fixture C1: scoped cloud-saturated ---
        scoped_cloud_root = td_path / "scoped-cloud-saturated"
        scoped_cloud_bugs = scoped_cloud_root / "docs" / "bugs"
        scoped_cloud_bugs.mkdir(parents=True, exist_ok=True)
        (scoped_cloud_bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-scoped-cloud", "name": "Scoped Cloud Bug",
                 "spec_dir": "bug-scoped-cloud"},
            ]
        }), encoding="utf-8")
        bsc = scoped_cloud_bugs / "bug-scoped-cloud"
        bsc.mkdir()
        (bsc / "SPEC.md").write_text(
            "# Scoped Cloud Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )
        _seed_phases_complete(bsc)
        (bsc / "DEFERRED_NON_CLOUD.md").write_text(
            "---\nkind: deferred-non-cloud\nfeature_id: bug-scoped-cloud\n---\n"
            "Workstation MCP validation pending.\n",
            encoding="utf-8",
        )
        fix_scoped_cloud = "scoped-cloud-saturated-identity"
        try:
            got_sc = compute_state(
                scoped_cloud_root, cloud=True, real_device=True,
                scope_bug_id="bug-scoped-cloud",
            )
            sc_ok = True
            if got_sc.get("feature_id") != "bug-scoped-cloud":
                failures.append(
                    f"[{fix_scoped_cloud}] expected feature_id='bug-scoped-cloud', "
                    f"got {got_sc.get('feature_id')!r}"
                )
                sc_ok = False
            if got_sc.get("terminal_reason") != TR_CLOUD_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_cloud}] expected terminal_reason="
                    f"{TR_CLOUD_DEFERRED_SCOPED!r}, got "
                    f"{got_sc.get('terminal_reason')!r}"
                )
                sc_ok = False
            if got_sc.get("terminal_reason") == TR_CLOUD_QUEUE_EXHAUSTED:
                failures.append(
                    f"[{fix_scoped_cloud}] scoped query erroneously returned global "
                    f"{TR_CLOUD_QUEUE_EXHAUSTED!r} (identity lost)"
                )
                sc_ok = False
            print(
                f"  {'PASS' if sc_ok else 'FAIL'} [{fix_scoped_cloud}] "
                f"feature_id={got_sc.get('feature_id')!r} "
                f"terminal_reason={got_sc.get('terminal_reason')!r}"
            )
        except Exception as exc:
            failures.append(f"[{fix_scoped_cloud}] unexpected error: {type(exc).__name__}: {exc}")
            print(f"  FAIL [{fix_scoped_cloud}] {type(exc).__name__} — {exc}")

        # --- Fixture C2: scoped device-saturated ---
        scoped_dev_root = td_path / "scoped-device-saturated"
        scoped_dev_bugs = scoped_dev_root / "docs" / "bugs"
        scoped_dev_bugs.mkdir(parents=True, exist_ok=True)
        (scoped_dev_bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-scoped-dev", "name": "Scoped Device Bug",
                 "spec_dir": "bug-scoped-dev"},
            ]
        }), encoding="utf-8")
        bsdev = scoped_dev_bugs / "bug-scoped-dev"
        bsdev.mkdir()
        (bsdev / "SPEC.md").write_text(
            "# Scoped Device Bug\n\n"
            "**Status:** In-progress\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-01\n",
            encoding="utf-8",
        )
        _seed_phases_complete(bsdev)
        _write_yaml_sentinel(
            bsdev / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="bug-scoped-dev",
            deferred_scenarios=["sustained-timing"],
        )
        fix_scoped_dev = "scoped-device-saturated-identity"
        try:
            got_sdev = compute_state(
                scoped_dev_root, cloud=False, real_device=False,
                scope_bug_id="bug-scoped-dev",
            )
            sdev_ok = True
            if got_sdev.get("feature_id") != "bug-scoped-dev":
                failures.append(
                    f"[{fix_scoped_dev}] expected feature_id='bug-scoped-dev', "
                    f"got {got_sdev.get('feature_id')!r}"
                )
                sdev_ok = False
            if got_sdev.get("terminal_reason") != TR_DEVICE_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_dev}] expected terminal_reason="
                    f"{TR_DEVICE_DEFERRED_SCOPED!r}, got "
                    f"{got_sdev.get('terminal_reason')!r}"
                )
                sdev_ok = False
            if got_sdev.get("terminal_reason") == TR_DEVICE_QUEUE_EXHAUSTED:
                failures.append(
                    f"[{fix_scoped_dev}] scoped query erroneously returned global "
                    f"{TR_DEVICE_QUEUE_EXHAUSTED!r} (identity lost)"
                )
                sdev_ok = False
            print(
                f"  {'PASS' if sdev_ok else 'FAIL'} [{fix_scoped_dev}] "
                f"feature_id={got_sdev.get('feature_id')!r} "
                f"terminal_reason={got_sdev.get('terminal_reason')!r}"
            )
        except Exception as exc:
            failures.append(f"[{fix_scoped_dev}] unexpected error: {type(exc).__name__}: {exc}")
            print(f"  FAIL [{fix_scoped_dev}] {type(exc).__name__} — {exc}")

        # -------------------------------------------------------------------
        # backfill_receipts bespoke block: call backfill_receipts() directly
        # on a tree with one Fixed bug (no FIXED.md) and one Won't-fix bug
        # (receipt-exempt; must NOT be backfilled).
        # We assert: count == 1, the Fixed bug id is in backfilled, FIXED.md
        # was written, and the Won't-fix bug has no FIXED.md.
        # CRITICAL: we do NOT assert the date or body content — backfill_receipts
        # uses datetime.now() and any date assertion would rot daily.
        # -------------------------------------------------------------------
        fix_name_br = "backfill-receipts-direct"
        root_br = td_path / fix_name_br
        bugs_br = root_br / "docs" / "bugs"
        bugs_br.mkdir(parents=True, exist_ok=True)
        # Fixed bug with no FIXED.md — must get a receipt.
        bfixed = bugs_br / "bug-needs-receipt"
        bfixed.mkdir()
        (bfixed / "SPEC.md").write_text(
            "# Needs Receipt Bug\n\n"
            "**Status:** Fixed\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )
        # Won't-fix bug with no FIXED.md — must NOT get a receipt (exempt).
        bwontfix = bugs_br / "bug-wont-fix-exempt"
        bwontfix.mkdir()
        (bwontfix / "SPEC.md").write_text(
            "# Won't Fix Exempt\n\n"
            "**Status:** Won't-fix\n\n"
            "**Severity:** Low\n\n"
            "**Discovered:** 2026-03-01\n",
            encoding="utf-8",
        )
        br_ok = True
        try:
            result_br = backfill_receipts(root_br)
            # Assert return dict shape (no date/body assertions)
            if result_br.get("count") != 1:
                failures.append(
                    f"[{fix_name_br}] expected count=1, got {result_br.get('count')!r}"
                )
                br_ok = False
            if "bug-needs-receipt" not in result_br.get("backfilled", []):
                failures.append(
                    f"[{fix_name_br}] expected 'bug-needs-receipt' in backfilled, "
                    f"got {result_br.get('backfilled')!r}"
                )
                br_ok = False
            # Assert the FIXED.md was actually written on disk
            if not (bfixed / "FIXED.md").exists():
                failures.append(
                    f"[{fix_name_br}] FIXED.md not created for 'bug-needs-receipt'"
                )
                br_ok = False
            # Assert Won't-fix bug did NOT get a receipt
            if (bwontfix / "FIXED.md").exists():
                failures.append(
                    f"[{fix_name_br}] FIXED.md erroneously created for Won't-fix bug"
                )
                br_ok = False
            print(
                f"  {'PASS' if br_ok else 'FAIL'} [{fix_name_br}] "
                f"backfilled={result_br.get('backfilled')!r} count={result_br.get('count')!r} "
                f"fixed_md_written={(bfixed / 'FIXED.md').exists()}"
            )
        except Exception as exc:
            failures.append(f"[{fix_name_br}] unexpected error: {exc}")
            print(f"  FAIL [{fix_name_br}]: {type(exc).__name__} — {exc}")

        # -------------------------------------------------------------------
        # fsck bespoke block (fixed-bugs-unarchived-fsck Fix Scope §3): each
        # of the three violation classes fires independently, and a clean
        # tree (Fixed+receipt properly archived, no stale queue rows) → ok.
        # -------------------------------------------------------------------
        fix_name_fsck = "fsck-violations"
        root_fsck = td_path / fix_name_fsck
        bugs_fsck = root_fsck / "docs" / "bugs"
        bugs_fsck.mkdir(parents=True, exist_ok=True)

        # (a) unarchived-fixed: Status Fixed + valid FIXED.md, NOT under _archive/.
        unarchived = bugs_fsck / "bug-unarchived-fixed"
        unarchived.mkdir()
        (unarchived / "SPEC.md").write_text(
            "# Unarchived Fixed Bug\n\n**Status:** Fixed\n\n"
            "**Severity:** P2\n\n**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )
        write_completed_receipt(
            unarchived / "FIXED.md", "bug-unarchived-fixed", "2026-05-02",
            provenance="gated", kind="fixed",
        )

        # (b) fixed-without-receipt: Status Fixed, no FIXED.md at all.
        no_receipt = bugs_fsck / "bug-fixed-no-receipt"
        no_receipt.mkdir()
        (no_receipt / "SPEC.md").write_text(
            "# Fixed No Receipt Bug\n\n**Status:** Fixed\n\n"
            "**Severity:** P3\n\n**Discovered:** 2026-05-01\n",
            encoding="utf-8",
        )

        # Clean control: a properly-archived Fixed+receipted bug must NOT
        # trip (a) or (b) — it IS under _archive/.
        archived_ok = bugs_fsck / "_archive" / "bug-properly-archived"
        archived_ok.mkdir(parents=True)
        (archived_ok / "SPEC.md").write_text(
            "# Properly Archived Bug\n\n**Status:** Fixed\n\n"
            "**Severity:** P2\n\n**Discovered:** 2026-04-01\n",
            encoding="utf-8",
        )
        write_completed_receipt(
            archived_ok / "FIXED.md", "bug-properly-archived", "2026-04-02",
            provenance="gated", kind="fixed",
        )

        # (c) stale-queue-entry: queue.json row pointing at the Fixed dir
        # from (b) (still Fixed, not archived) — the queue-trim never ran.
        (bugs_fsck / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": "bug-fixed-no-receipt", "name": "Fixed No Receipt Bug",
                 "spec_dir": "bug-fixed-no-receipt", "severity": "P3"},
            ]}),
            encoding="utf-8",
        )

        try:
            result_fsck = fsck(root_fsck)
            fsck_ok = True
            if result_fsck.get("ok") is not False:
                failures.append(
                    f"[{fix_name_fsck}] expected ok=False with violations present, "
                    f"got {result_fsck.get('ok')!r}"
                )
                fsck_ok = False
            kinds_seen = {v.get("kind") for v in result_fsck.get("violations", [])}
            ids_seen = {v.get("bug_id") for v in result_fsck.get("violations", [])}
            for expected_kind in ("unarchived-fixed", "fixed-without-receipt", "stale-queue-entry"):
                if expected_kind not in kinds_seen:
                    failures.append(
                        f"[{fix_name_fsck}] expected a {expected_kind!r} violation; "
                        f"kinds seen: {kinds_seen!r}"
                    )
                    fsck_ok = False
            if "bug-unarchived-fixed" not in ids_seen:
                failures.append(
                    f"[{fix_name_fsck}] expected 'bug-unarchived-fixed' to be flagged"
                )
                fsck_ok = False
            if "bug-properly-archived" in ids_seen:
                failures.append(
                    f"[{fix_name_fsck}] the properly-archived control bug must NOT "
                    f"be flagged; ids_seen={ids_seen!r}"
                )
                fsck_ok = False
            print(
                f"  {'PASS' if fsck_ok else 'FAIL'} [{fix_name_fsck}] "
                f"ok={result_fsck.get('ok')!r} kinds={sorted(kinds_seen)!r}"
            )
        except Exception as exc:
            failures.append(f"[{fix_name_fsck}] unexpected error: {exc}")
            print(f"  FAIL [{fix_name_fsck}]: {type(exc).__name__} — {exc}")

        # Clean-tree control: fsck on a tree with ONLY the properly-archived
        # bug (no unarchived/no-receipt/stale-queue debris) → ok=True, [].
        fix_name_fsck_clean = "fsck-clean-tree"
        root_fsck_clean = td_path / fix_name_fsck_clean
        bugs_fsck_clean = root_fsck_clean / "docs" / "bugs" / "_archive" / "bug-properly-archived"
        bugs_fsck_clean.mkdir(parents=True)
        (bugs_fsck_clean / "SPEC.md").write_text(
            "# Properly Archived Bug\n\n**Status:** Fixed\n\n"
            "**Severity:** P2\n\n**Discovered:** 2026-04-01\n",
            encoding="utf-8",
        )
        write_completed_receipt(
            bugs_fsck_clean / "FIXED.md", "bug-properly-archived", "2026-04-02",
            provenance="gated", kind="fixed",
        )
        try:
            result_fsck_clean = fsck(root_fsck_clean)
            clean_ok = (
                result_fsck_clean.get("ok") is True
                and result_fsck_clean.get("violations") == []
            )
            if not clean_ok:
                failures.append(
                    f"[{fix_name_fsck_clean}] expected ok=True, violations=[]; "
                    f"got {result_fsck_clean!r}"
                )
            print(f"  {'PASS' if clean_ok else 'FAIL'} [{fix_name_fsck_clean}] {result_fsck_clean!r}")
        except Exception as exc:
            failures.append(f"[{fix_name_fsck_clean}] unexpected error: {exc}")
            print(f"  FAIL [{fix_name_fsck_clean}]: {type(exc).__name__} — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-1-park (bug): --park-needs-input mode (Phase 4)
        #
        # Two-bug queue:
        #   bug-parked  — carries NEEDS_INPUT.md (well-formed, 1 decision)
        #   bug-after   — actionable (Open, SPEC present)
        #
        # Sub-fixture A: WITHOUT park_needs_input → terminal_reason=="needs-input"
        #                AND "parked" key ABSENT from output.
        # Sub-fixture B: WITH park_needs_input=True → bug-after is dispatched,
        #                output has "parked" list with one entry whose id matches
        #                bug-parked and decision_count==1.
        # Sub-fixture C: RESOLVED sentinel (NEEDS_INPUT.md removed) → bug-parked
        #                is dispatched normally, "parked" is empty.
        # -------------------------------------------------------------------
        bug_park_root = td_path / "bug-park-needs-input"
        bug_park_bugs = bug_park_root / "docs" / "bugs"
        bug_park_bugs.mkdir(parents=True, exist_ok=True)
        # Write queue.json
        (bug_park_bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-parked", "name": "Parked Bug",
                 "spec_dir": "bug-parked"},
                {"id": "bug-after", "name": "After Bug",
                 "spec_dir": "bug-after"},
            ]
        }), encoding="utf-8")
        # bug-parked: Open spec + NEEDS_INPUT.md (1 decision, date set)
        bug_parked_dir = bug_park_bugs / "bug-parked"
        bug_parked_dir.mkdir()
        (bug_parked_dir / "SPEC.md").write_text(
            "# Parked Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P1\n\n"
            "**Discovered:** 2026-06-10\n",
            encoding="utf-8",
        )
        bug_needs_input_content = (
            "---\n"
            "kind: needs-input\n"
            "feature_id: bug-parked\n"
            "written_by: spec-bug\n"
            "decisions:\n"
            "  - Confirm reproduction path\n"
            "date: 2026-06-10\n"
            "---\n\n"
            "# Needs Input\n"
        )
        bug_park_sentinel = bug_parked_dir / "NEEDS_INPUT.md"
        bug_park_sentinel.write_text(bug_needs_input_content, encoding="utf-8")
        # bug-after: actionable (Open, SPEC present, no NEEDS_INPUT.md)
        bug_after_dir = bug_park_bugs / "bug-after"
        bug_after_dir.mkdir()
        (bug_after_dir / "SPEC.md").write_text(
            "# After Bug\n\n"
            "**Status:** Open\n\n"
            "**Severity:** P2\n\n"
            "**Discovered:** 2026-06-10\n",
            encoding="utf-8",
        )

        # Sub-fixture A: without park_needs_input → needs-input halt, NO "parked" key
        fix_bug_park_default = "bug-park-needs-input-default-halt"
        try:
            got_bug_park_default = compute_state(bug_park_root, cloud=False, real_device=True)
            bpd_ok = True
            actual_tr_bpd = got_bug_park_default.get("terminal_reason")
            if actual_tr_bpd != TR_NEEDS_INPUT:
                failures.append(
                    f"[{fix_bug_park_default}] expected terminal_reason={TR_NEEDS_INPUT!r}, "
                    f"got {actual_tr_bpd!r}"
                )
                bpd_ok = False
            # CRITICAL: "parked" key must be ABSENT when not in park mode.
            if "parked" in got_bug_park_default:
                failures.append(
                    f"[{fix_bug_park_default}] 'parked' key must be absent in default mode; "
                    f"got parked={got_bug_park_default['parked']!r}"
                )
                bpd_ok = False
            print(
                f"  {'PASS' if bpd_ok else 'FAIL'} [{fix_bug_park_default}] "
                f"default: terminal_reason={actual_tr_bpd!r}, parked key absent={('parked' not in got_bug_park_default)}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bug_park_default}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bug_park_default}] SystemExit: {exc.code}")

        # Sub-fixture B: WITH park_needs_input=True → bug-after dispatched,
        # output["parked"] has one entry with id="bug-parked", decision_count=1.
        fix_bug_park_mode = "bug-park-needs-input-mode-skip"
        try:
            got_bug_park_mode = compute_state(
                bug_park_root, cloud=False, real_device=True, park_needs_input=True
            )
            bpm_ok = True
            actual_tr_bpm = got_bug_park_mode.get("terminal_reason")
            if actual_tr_bpm == TR_NEEDS_INPUT:
                failures.append(
                    f"[{fix_bug_park_mode}] terminal_reason must NOT be {TR_NEEDS_INPUT!r} in park mode; "
                    f"got {actual_tr_bpm!r}"
                )
                bpm_ok = False
            if got_bug_park_mode.get("feature_id") != "bug-after":
                failures.append(
                    f"[{fix_bug_park_mode}] expected feature_id='bug-after', "
                    f"got {got_bug_park_mode.get('feature_id')!r}"
                )
                bpm_ok = False
            bug_parked_list = got_bug_park_mode.get("parked")
            if not isinstance(bug_parked_list, list) or len(bug_parked_list) != 1:
                failures.append(
                    f"[{fix_bug_park_mode}] expected parked=[...1 entry...], "
                    f"got {bug_parked_list!r}"
                )
                bpm_ok = False
            elif bug_parked_list[0].get("id") != "bug-parked":
                failures.append(
                    f"[{fix_bug_park_mode}] parked[0].id must be 'bug-parked', "
                    f"got {bug_parked_list[0].get('id')!r}"
                )
                bpm_ok = False
            elif bug_parked_list[0].get("decision_count") != 1:
                failures.append(
                    f"[{fix_bug_park_mode}] parked[0].decision_count must be 1, "
                    f"got {bug_parked_list[0].get('decision_count')!r}"
                )
                bpm_ok = False
            print(
                f"  {'PASS' if bpm_ok else 'FAIL'} [{fix_bug_park_mode}] "
                f"park mode: dispatched={got_bug_park_mode.get('feature_id')!r}, "
                f"parked count={len(bug_parked_list) if isinstance(bug_parked_list, list) else 'N/A'}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bug_park_mode}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bug_park_mode}] SystemExit: {exc.code}")

        # Sub-fixture C: RESOLVED — remove NEEDS_INPUT.md → bug-parked dispatched
        # normally, parked[] is empty.
        fix_bug_park_resolved = "bug-park-needs-input-resolved-reenter"
        try:
            bug_park_sentinel.unlink()  # resolve the sentinel
            got_bug_park_resolved = compute_state(
                bug_park_root, cloud=False, real_device=True, park_needs_input=True
            )
            bpr_ok = True
            if got_bug_park_resolved.get("feature_id") != "bug-parked":
                failures.append(
                    f"[{fix_bug_park_resolved}] expected feature_id='bug-parked' after resolution, "
                    f"got {got_bug_park_resolved.get('feature_id')!r}"
                )
                bpr_ok = False
            bug_parked_resolved = got_bug_park_resolved.get("parked")
            if not isinstance(bug_parked_resolved, list) or len(bug_parked_resolved) != 0:
                failures.append(
                    f"[{fix_bug_park_resolved}] expected parked=[], "
                    f"got {bug_parked_resolved!r}"
                )
                bpr_ok = False
            print(
                f"  {'PASS' if bpr_ok else 'FAIL'} [{fix_bug_park_resolved}] "
                f"resolved: dispatched={got_bug_park_resolved.get('feature_id')!r}, "
                f"parked={bug_parked_resolved!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bug_park_resolved}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bug_park_resolved}] SystemExit: {exc.code}")

        # Sub-fixture D: BLOCKED.md precedence — bug-parked carries BOTH
        # BLOCKED.md AND NEEDS_INPUT.md.  Under park mode it must STILL halt as
        # "blocked", not be silently parked.  This locks FIX 1 of the code review.
        fix_bug_park_blocked_precedence = "bug-park-needs-input-blocked-precedence"
        try:
            # Restore NEEDS_INPUT.md (removed in sub-fixture C) and add BLOCKED.md.
            bug_park_sentinel.write_text(bug_needs_input_content, encoding="utf-8")
            _write_yaml_sentinel(
                bug_parked_dir / "BLOCKED.md", "blocked",
                bug_id="bug-parked", phase="Investigation",
                blocked_at="2026-06-10T00:00:00Z", retry_count=0,
            )
            got_bug_park_blocked = compute_state(
                bug_park_root, cloud=False, real_device=True, park_needs_input=True
            )
            bpbp_ok = True
            # Must halt as "blocked" — NOT parked, not dispatched.
            actual_tr_bpbp = got_bug_park_blocked.get("terminal_reason")
            if actual_tr_bpbp != TR_BLOCKED:
                failures.append(
                    f"[{fix_bug_park_blocked_precedence}] expected terminal_reason={TR_BLOCKED!r} "
                    f"(BLOCKED.md must retain precedence over park-mode); "
                    f"got {actual_tr_bpbp!r}"
                )
                bpbp_ok = False
            # bug-parked must be the reported feature (it is the one that is blocked).
            if got_bug_park_blocked.get("feature_id") != "bug-parked":
                failures.append(
                    f"[{fix_bug_park_blocked_precedence}] expected feature_id='bug-parked', "
                    f"got {got_bug_park_blocked.get('feature_id')!r}"
                )
                bpbp_ok = False
            # "parked" key must NOT contain bug-parked (it was NOT parked).
            parked_bpbp = got_bug_park_blocked.get("parked", [])
            parked_bpbp_ids = [e.get("id") for e in parked_bpbp if isinstance(e, dict)]
            if "bug-parked" in parked_bpbp_ids:
                failures.append(
                    f"[{fix_bug_park_blocked_precedence}] bug-parked must NOT appear in "
                    f"parked[] when BLOCKED.md is present; got parked={parked_bpbp!r}"
                )
                bpbp_ok = False
            print(
                f"  {'PASS' if bpbp_ok else 'FAIL'} [{fix_bug_park_blocked_precedence}] "
                f"blocked-precedence: terminal_reason={actual_tr_bpbp!r}, "
                f"bug-parked in parked[]={'bug-parked' in parked_bpbp_ids}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bug_park_blocked_precedence}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bug_park_blocked_precedence}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture WU-2-park-blocked (bug): --park-blocked mode
        # (bug park-mode-halts-on-blocked, Phase 2 — mirror of lazy-state.py P1)
        #
        # Two-bug queue in a FRESH root:
        #   blocked-bug   — carries BLOCKED.md (no NEEDS_INPUT.md)
        #   workable-bug  — actionable (Open, SPEC present)
        #
        # Sub-fixture 1 (bug-park-blocked-mode-skip): park_blocked=True →
        #   blocked-bug parked, workable-bug dispatched.
        # Sub-fixture 2 (bug-park-blocked-default-halt): no flag → "blocked",
        #   "parked" key ABSENT.
        # Sub-fixture 3 (bug-park-blocked-all-parked-terminal): every remaining
        #   bug parked → terminal_reason "queue-exhausted-all-parked".
        # Sub-fixture 4 (bug-park-blocked-and-needs-input-single-park): a bug
        #   carrying BOTH sentinels parks exactly ONCE under both flags.
        # Sub-fixture E (bug-park-blocked-reenter-under-flag): a bug carrying
        #   BLOCKED.md IS parked under park_blocked=True (the SPEC Open-Q1 mirror
        #   of sub-fixture D, which proves it is NOT parked WITHOUT the flag).
        # -------------------------------------------------------------------
        bpb_root = td_path / "bug-park-blocked"
        bpb_bugs = bpb_root / "docs" / "bugs"
        bpb_bugs.mkdir(parents=True, exist_ok=True)
        (bpb_bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "blocked-bug", "name": "Blocked Bug",
                 "spec_dir": "blocked-bug"},
                {"id": "workable-bug", "name": "Workable Bug",
                 "spec_dir": "workable-bug"},
            ]
        }), encoding="utf-8")
        bpb_blocked_dir = bpb_bugs / "blocked-bug"
        bpb_blocked_dir.mkdir()
        (bpb_blocked_dir / "SPEC.md").write_text(
            "# Blocked Bug\n\n**Status:** Open\n\n**Severity:** P1\n\n"
            "**Discovered:** 2026-06-16\n",
            encoding="utf-8",
        )
        _write_yaml_sentinel(
            bpb_blocked_dir / "BLOCKED.md", "blocked",
            bug_id="blocked-bug", phase="Investigation",
            blocked_at="2026-06-16T00:00:00Z", retry_count=0,
        )
        bpb_workable_dir = bpb_bugs / "workable-bug"
        bpb_workable_dir.mkdir()
        (bpb_workable_dir / "SPEC.md").write_text(
            "# Workable Bug\n\n**Status:** Open\n\n**Severity:** P2\n\n"
            "**Discovered:** 2026-06-16\n",
            encoding="utf-8",
        )

        # Sub-fixture 1: park_blocked=True → blocked-bug parked, workable dispatched.
        fix_bpb_skip = "bug-park-blocked-mode-skip"
        try:
            got_bpb_skip = compute_state(
                bpb_root, cloud=False, real_device=True, park_blocked=True
            )
            bpbskip_ok = True
            if got_bpb_skip.get("terminal_reason") == TR_BLOCKED:
                failures.append(
                    f"[{fix_bpb_skip}] terminal_reason must NOT be {TR_BLOCKED!r} under "
                    f"park_blocked; got {got_bpb_skip.get('terminal_reason')!r}"
                )
                bpbskip_ok = False
            if got_bpb_skip.get("feature_id") != "workable-bug":
                failures.append(
                    f"[{fix_bpb_skip}] expected feature_id='workable-bug', "
                    f"got {got_bpb_skip.get('feature_id')!r}"
                )
                bpbskip_ok = False
            bpb_parked = got_bpb_skip.get("parked")
            if not isinstance(bpb_parked, list) or len(bpb_parked) != 1:
                failures.append(
                    f"[{fix_bpb_skip}] expected parked=[...1 entry...], got {bpb_parked!r}"
                )
                bpbskip_ok = False
            elif bpb_parked[0].get("id") != "blocked-bug":
                failures.append(
                    f"[{fix_bpb_skip}] parked[0].id must be 'blocked-bug', "
                    f"got {bpb_parked[0].get('id')!r}"
                )
                bpbskip_ok = False
            elif not str(bpb_parked[0].get("sentinel", "")).endswith("BLOCKED.md"):
                failures.append(
                    f"[{fix_bpb_skip}] parked[0].sentinel must end in BLOCKED.md, "
                    f"got {bpb_parked[0].get('sentinel')!r}"
                )
                bpbskip_ok = False
            print(
                f"  {'PASS' if bpbskip_ok else 'FAIL'} [{fix_bpb_skip}] "
                f"dispatched={got_bpb_skip.get('feature_id')!r}, "
                f"parked count={len(bpb_parked) if isinstance(bpb_parked, list) else 'N/A'}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bpb_skip}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpb_skip}] SystemExit: {exc.code}")

        # Sub-fixture 2: NO flag → terminal_reason "blocked", "parked" key ABSENT.
        fix_bpb_default = "bug-park-blocked-default-halt"
        try:
            got_bpb_default = compute_state(bpb_root, cloud=False, real_device=True)
            bpbdef_ok = True
            if got_bpb_default.get("terminal_reason") != TR_BLOCKED:
                failures.append(
                    f"[{fix_bpb_default}] expected terminal_reason={TR_BLOCKED!r}, "
                    f"got {got_bpb_default.get('terminal_reason')!r}"
                )
                bpbdef_ok = False
            if "parked" in got_bpb_default:
                failures.append(
                    f"[{fix_bpb_default}] 'parked' key must be absent in default mode; "
                    f"got parked={got_bpb_default['parked']!r}"
                )
                bpbdef_ok = False
            print(
                f"  {'PASS' if bpbdef_ok else 'FAIL'} [{fix_bpb_default}] "
                f"default: terminal_reason={got_bpb_default.get('terminal_reason')!r}, "
                f"parked key absent={('parked' not in got_bpb_default)}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bpb_default}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpb_default}] SystemExit: {exc.code}")

        # Sub-fixture 3: all-parked terminal. Mark workable-bug ALSO blocked so
        # every remaining bug is parked → queue-exhausted-all-parked.
        fix_bpb_allparked = "bug-park-blocked-all-parked-terminal"
        try:
            _write_yaml_sentinel(
                bpb_workable_dir / "BLOCKED.md", "blocked",
                bug_id="workable-bug", phase="Investigation",
                blocked_at="2026-06-16T00:00:00Z", retry_count=0,
            )
            got_bpb_all = compute_state(
                bpb_root, cloud=False, real_device=True,
                park_needs_input=True, park_blocked=True,
            )
            bpball_ok = True
            if got_bpb_all.get("terminal_reason") != TR_QUEUE_EXHAUSTED_ALL_PARKED:
                failures.append(
                    f"[{fix_bpb_allparked}] expected terminal_reason="
                    f"{TR_QUEUE_EXHAUSTED_ALL_PARKED!r}, got "
                    f"{got_bpb_all.get('terminal_reason')!r}"
                )
                bpball_ok = False
            bpb_all_parked = got_bpb_all.get("parked")
            if not isinstance(bpb_all_parked, list) or len(bpb_all_parked) < 1:
                failures.append(
                    f"[{fix_bpb_allparked}] expected non-empty parked[], "
                    f"got {bpb_all_parked!r}"
                )
                bpball_ok = False
            print(
                f"  {'PASS' if bpball_ok else 'FAIL'} [{fix_bpb_allparked}] "
                f"terminal_reason={got_bpb_all.get('terminal_reason')!r}, "
                f"parked count={len(bpb_all_parked) if isinstance(bpb_all_parked, list) else 'N/A'}"
            )
            # cleanup: remove workable BLOCKED.md so sub-fixture 4/E run clean.
            (bpb_workable_dir / "BLOCKED.md").unlink()
        except SystemExit as exc:
            failures.append(f"[{fix_bpb_allparked}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpb_allparked}] SystemExit: {exc.code}")

        # Sub-fixture 4: dual-sentinel single-park. blocked-bug carries BOTH
        # BLOCKED.md and NEEDS_INPUT.md; under both flags it parks exactly ONCE.
        fix_bpb_dual = "bug-park-blocked-and-needs-input-single-park"
        try:
            (bpb_blocked_dir / "NEEDS_INPUT.md").write_text(
                "---\n"
                "kind: needs-input\n"
                "feature_id: blocked-bug\n"
                "written_by: spec-bug\n"
                "decisions:\n"
                "  - Confirm repro\n"
                "date: 2026-06-16\n"
                "---\n\n# Needs Input\n",
                encoding="utf-8",
            )
            got_bpb_dual = compute_state(
                bpb_root, cloud=False, real_device=True,
                park_needs_input=True, park_blocked=True,
            )
            bpbdual_ok = True
            if got_bpb_dual.get("feature_id") != "workable-bug":
                failures.append(
                    f"[{fix_bpb_dual}] expected feature_id='workable-bug', "
                    f"got {got_bpb_dual.get('feature_id')!r}"
                )
                bpbdual_ok = False
            bpb_dual_parked = got_bpb_dual.get("parked", [])
            bpb_dual_ids = [e.get("id") for e in bpb_dual_parked if isinstance(e, dict)]
            if bpb_dual_ids.count("blocked-bug") != 1:
                failures.append(
                    f"[{fix_bpb_dual}] blocked-bug must appear EXACTLY once in "
                    f"parked[]; got ids={bpb_dual_ids!r}"
                )
                bpbdual_ok = False
            print(
                f"  {'PASS' if bpbdual_ok else 'FAIL'} [{fix_bpb_dual}] "
                f"dispatched={got_bpb_dual.get('feature_id')!r}, "
                f"blocked-bug park count={bpb_dual_ids.count('blocked-bug')}"
            )
            # cleanup: remove NEEDS_INPUT.md so sub-fixture E tests BLOCKED-only.
            (bpb_blocked_dir / "NEEDS_INPUT.md").unlink()
        except SystemExit as exc:
            failures.append(f"[{fix_bpb_dual}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpb_dual}] SystemExit: {exc.code}")

        # Sub-fixture E: a BLOCKED-only bug IS parked under park_blocked=True (the
        # mirror of the needs-input sub-fixture D, which proves NOT-parked without
        # the flag). SPEC Open-Q1 bug parity.
        fix_bpb_E = "bug-park-blocked-reenter-under-flag"
        try:
            got_bpb_E = compute_state(
                bpb_root, cloud=False, real_device=True, park_blocked=True
            )
            bpbE_ok = True
            parked_E = got_bpb_E.get("parked", [])
            parked_E_ids = [e.get("id") for e in parked_E if isinstance(e, dict)]
            if "blocked-bug" not in parked_E_ids:
                failures.append(
                    f"[{fix_bpb_E}] blocked-bug MUST be parked under park_blocked=True; "
                    f"got parked ids={parked_E_ids!r}"
                )
                bpbE_ok = False
            if got_bpb_E.get("terminal_reason") == TR_BLOCKED:
                failures.append(
                    f"[{fix_bpb_E}] must NOT halt as {TR_BLOCKED!r} under park_blocked; "
                    f"got {got_bpb_E.get('terminal_reason')!r}"
                )
                bpbE_ok = False
            print(
                f"  {'PASS' if bpbE_ok else 'FAIL'} [{fix_bpb_E}] "
                f"blocked-bug parked under flag={'blocked-bug' in parked_E_ids}, "
                f"dispatched={got_bpb_E.get('feature_id')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_bpb_E}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpb_E}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture park-provisional (bug — park-provisional-acceptance,
        # coupled-pair mirror of lazy-state.py's fixture; the shared
        # lazy_core predicate/action mechanics are exhaustively covered
        # there, so this block asserts the bug-side WIRING):
        #   1 eligible-route      — divergence two-key low → __provisional_accept__
        #   2 structural-parks    — audit_divergence: structural → parked
        #   3 workable-under-park — _PROVISIONAL file: bug itself dispatched,
        #                           provisional[] lists it
        #   4 needs-ratification  — non-park probe halts on the new terminal
        #   5 flag-pairing        — park_provisional alone dies (SPEC D1)
        # -------------------------------------------------------------------
        bpp_root = td_path / "bug-park-provisional"
        bpp_bugs = bpp_root / "docs" / "bugs"
        bpp_bugs.mkdir(parents=True, exist_ok=True)
        (bpp_bugs / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "prov-bug", "name": "Provisional Bug",
                 "spec_dir": "prov-bug"},
                {"id": "after-bug", "name": "After Bug",
                 "spec_dir": "after-bug"},
            ]
        }), encoding="utf-8")
        bpp_prov_dir = bpp_bugs / "prov-bug"
        bpp_prov_dir.mkdir()
        (bpp_prov_dir / "SPEC.md").write_text(
            "# Provisional Bug\n\n**Status:** Open\n\n**Severity:** P1\n\n"
            "**Discovered:** 2026-07-09\n",
            encoding="utf-8",
        )
        bpp_after_dir = bpp_bugs / "after-bug"
        bpp_after_dir.mkdir()
        (bpp_after_dir / "SPEC.md").write_text(
            "# After Bug\n\n**Status:** Open\n\n**Severity:** P2\n\n"
            "**Discovered:** 2026-07-09\n",
            encoding="utf-8",
        )

        def _bpp_needs_input(audit_divergence: str) -> str:
            return (
                "---\n"
                "kind: needs-input\n"
                "feature_id: prov-bug\n"
                "written_by: spec-bug\n"
                "decisions:\n"
                "  - Choose regression-test tier\n"
                "date: 2026-07-09\n"
                "divergence: isolated\n"
                f"audit_divergence: {audit_divergence}\n"
                "---\n\n"
                "# Needs Input\n\n"
                "## Decision Context\n\n"
                "### 1. Choose regression-test tier\n\n"
                "**Problem:** The fix needs a serving-path regression test tier.\n\n"
                "**Options:**\n"
                "- **Unit (Recommended)** — fast, serving-path covered.\n"
                "- **E2E** — slower, broader.\n\n"
                "**Recommendation:** Unit — serving-path covered and fast.\n"
            )

        bpp_sentinel = bpp_prov_dir / "NEEDS_INPUT.md"

        # 1: eligible route.
        fix_bpp_route = "bug-park-provisional-eligible-route"
        try:
            bpp_sentinel.write_text(_bpp_needs_input("contained"), encoding="utf-8")
            got_bpp = compute_state(
                bpp_root, cloud=False, real_device=True,
                park_needs_input=True, park_provisional=True,
            )
            bppr_ok = True
            if got_bpp.get("sub_skill") != "__provisional_accept__":
                failures.append(
                    f"[{fix_bpp_route}] expected sub_skill='__provisional_accept__', "
                    f"got {got_bpp.get('sub_skill')!r}"
                )
                bppr_ok = False
            if got_bpp.get("feature_id") != "prov-bug":
                failures.append(
                    f"[{fix_bpp_route}] expected feature_id='prov-bug', "
                    f"got {got_bpp.get('feature_id')!r}"
                )
                bppr_ok = False
            print(f"  {'PASS' if bppr_ok else 'FAIL'} [{fix_bpp_route}]")
        except SystemExit as exc:
            failures.append(f"[{fix_bpp_route}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpp_route}] SystemExit: {exc.code}")

        # 2: structural audit grade parks instead of routing.
        fix_bpp_struct = "bug-park-provisional-structural-parks"
        try:
            bpp_sentinel.write_text(_bpp_needs_input("structural"), encoding="utf-8")
            got_bpp_s = compute_state(
                bpp_root, cloud=False, real_device=True,
                park_needs_input=True, park_provisional=True,
            )
            bpps_ok = True
            if got_bpp_s.get("sub_skill") == "__provisional_accept__":
                failures.append(
                    f"[{fix_bpp_struct}] structural grade must NOT route acceptance"
                )
                bpps_ok = False
            if not any(e.get("id") == "prov-bug"
                       for e in got_bpp_s.get("parked", [])):
                failures.append(
                    f"[{fix_bpp_struct}] prov-bug must be parked "
                    f"(parked={got_bpp_s.get('parked')!r})"
                )
                bpps_ok = False
            print(f"  {'PASS' if bpps_ok else 'FAIL'} [{fix_bpp_struct}]")
        except SystemExit as exc:
            failures.append(f"[{fix_bpp_struct}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpp_struct}] SystemExit: {exc.code}")

        # 2b (stub-origin-provisional-exclusion): an otherwise-eligible
        # sentinel marked stub_origin: true parks instead of routing.
        fix_bpp_stub = "bug-park-provisional-stub-origin-parks"
        try:
            bpp_sentinel.write_text(
                _bpp_needs_input("contained").replace(
                    "audit_divergence: contained",
                    "audit_divergence: contained" + chr(10) + "stub_origin: true"),
                encoding="utf-8",
            )
            got_bpp_so = compute_state(
                bpp_root, cloud=False, real_device=True,
                park_needs_input=True, park_provisional=True,
            )
            bppso_ok = True
            if got_bpp_so.get("sub_skill") == "__provisional_accept__":
                failures.append(
                    f"[{fix_bpp_stub}] stub_origin sentinel must NOT route acceptance"
                )
                bppso_ok = False
            if not any(e.get("id") == "prov-bug"
                       for e in got_bpp_so.get("parked", [])):
                failures.append(
                    f"[{fix_bpp_stub}] prov-bug must be parked "
                    f"(parked={got_bpp_so.get('parked')!r})"
                )
                bppso_ok = False
            print(f"  {'PASS' if bppso_ok else 'FAIL'} [{fix_bpp_stub}]")
        except SystemExit as exc:
            failures.append(f"[{fix_bpp_stub}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpp_stub}] SystemExit: {exc.code}")

        # 3+4: rename to _PROVISIONAL → workable under park (provisional[]
        # lists it), needs-ratification halt non-park.
        fix_bpp_work = "bug-park-provisional-workable-and-ratification"
        try:
            bpp_sentinel.write_text(_bpp_needs_input("contained"), encoding="utf-8")
            act_bpp = lazy_core.provisionalize_sentinel(bpp_sentinel, bpp_root)
            bppw_ok = True
            if not act_bpp.get("ok"):
                failures.append(
                    f"[{fix_bpp_work}] provisionalize refused: {act_bpp.get('refused')!r}"
                )
                bppw_ok = False
            got_bpp_w = compute_state(
                bpp_root, cloud=False, real_device=True, park_needs_input=True,
            )
            if got_bpp_w.get("feature_id") != "prov-bug" or got_bpp_w.get("terminal_reason"):
                failures.append(
                    f"[{fix_bpp_work}] park probe must dispatch prov-bug; got "
                    f"feature_id={got_bpp_w.get('feature_id')!r}, "
                    f"terminal={got_bpp_w.get('terminal_reason')!r}"
                )
                bppw_ok = False
            if not any(e.get("id") == "prov-bug" and
                       e.get("sentinel_kind") == "provisional"
                       for e in got_bpp_w.get("provisional", [])):
                failures.append(
                    f"[{fix_bpp_work}] provisional[] must list prov-bug "
                    f"(got {got_bpp_w.get('provisional')!r})"
                )
                bppw_ok = False
            got_bpp_r = compute_state(bpp_root, cloud=False, real_device=True)
            if got_bpp_r.get("terminal_reason") != TR_NEEDS_RATIFICATION:
                failures.append(
                    f"[{fix_bpp_work}] non-park probe must halt "
                    f"'{TR_NEEDS_RATIFICATION}'; got "
                    f"{got_bpp_r.get('terminal_reason')!r}"
                )
                bppw_ok = False
            print(f"  {'PASS' if bppw_ok else 'FAIL'} [{fix_bpp_work}]")
        except SystemExit as exc:
            failures.append(f"[{fix_bpp_work}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_bpp_work}] SystemExit: {exc.code}")

        # 5: flag pairing (SPEC D1).
        fix_bpp_flag = "bug-park-provisional-flag-pairing"
        bppf_ok = True
        try:
            compute_state(
                bpp_root, cloud=False, real_device=True, park_provisional=True
            )
            failures.append(f"[{fix_bpp_flag}] bare park_provisional must die")
            bppf_ok = False
        except SystemExit as exc:
            if exc.code != 2:
                failures.append(f"[{fix_bpp_flag}] expected exit 2, got {exc.code!r}")
                bppf_ok = False
        print(f"  {'PASS' if bppf_ok else 'FAIL'} [{fix_bpp_flag}]")

        # -------------------------------------------------------------------
        # Fixture: cycle-marker-mutation guard (cycle-subagent-runs-orchestrator-
        # work Phase 2, KEYSTONE — coupled-pair mirror of lazy-state.py). A
        # SUBAGENT --cycle-end (no LAZY_ORCHESTRATOR, marker on disk) is REFUSED
        # (exit 3) and the marker SURVIVES; the ORCHESTRATOR (LAZY_ORCHESTRATOR=1)
        # clears it (exit 0). Same pair for --cycle-begin (bug-state uses
        # --bug-id). Driven via subprocess so the real CLI handler runs.
        # -------------------------------------------------------------------
        fix_cmg = "cycle-marker-mutation-guard"
        cmg_state = td_path / "cmg-state"
        cmg_state.mkdir(parents=True, exist_ok=True)
        cmg_marker = cmg_state / "lazy-cycle-active.json"
        _this_script = str(Path(__file__).resolve())

        def _cmg_env(orchestrator: bool) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(cmg_state)
            if orchestrator:
                e["LAZY_ORCHESTRATOR"] = "1"
            return e

        def _write_cmg_marker() -> None:
            cmg_marker.write_text(
                json.dumps({"feature_id": "bug-cmg", "nonce": "n", "kind": "real",
                            "commit_tally": 0, "started_at": "2026-06-16T00:00:00Z",
                            "session_id": None}, indent=2) + "\n",
                encoding="utf-8",
            )

        cmg_ok = True
        # (a) subagent --cycle-end → refused, marker survives.
        _write_cmg_marker()
        r = subprocess.run(
            [sys.executable, _this_script, "--cycle-end", "--repo-root", str(td_path)],
            capture_output=True, text=True, env=_cmg_env(orchestrator=False),
        )
        if r.returncode != 3:
            failures.append(f"[{fix_cmg}] subagent --cycle-end must exit 3; got {r.returncode}")
            cmg_ok = False
        if not cmg_marker.exists():
            failures.append(f"[{fix_cmg}] subagent --cycle-end must NOT delete the marker")
            cmg_ok = False
        # (b) orchestrator --cycle-end → clears marker, exit 0.
        _write_cmg_marker()
        r = subprocess.run(
            [sys.executable, _this_script, "--cycle-end", "--repo-root", str(td_path)],
            capture_output=True, text=True, env=_cmg_env(orchestrator=True),
        )
        if r.returncode != 0:
            failures.append(f"[{fix_cmg}] orchestrator --cycle-end must exit 0; got {r.returncode}")
            cmg_ok = False
        if cmg_marker.exists():
            failures.append(f"[{fix_cmg}] orchestrator --cycle-end must clear the marker")
            cmg_ok = False
        # (c) subagent --cycle-begin → refused, marker survives (re-arm blocked).
        _write_cmg_marker()
        r = subprocess.run(
            [sys.executable, _this_script, "--cycle-begin", "--bug-id", "bug-cmg",
             "--nonce", "deadbeef", "--repo-root", str(td_path)],
            capture_output=True, text=True, env=_cmg_env(orchestrator=False),
        )
        if r.returncode != 3:
            failures.append(f"[{fix_cmg}] subagent --cycle-begin must exit 3; got {r.returncode}")
            cmg_ok = False
        if not cmg_marker.exists():
            failures.append(f"[{fix_cmg}] subagent --cycle-begin must NOT mutate the marker")
            cmg_ok = False
        # (d) orchestrator --cycle-begin → self-healing overwrite, exit 0.
        _write_cmg_marker()
        r = subprocess.run(
            [sys.executable, _this_script, "--cycle-begin", "--bug-id", "bug-cmg2",
             "--nonce", "cafe", "--sub-skill", "execute-plan", "--repo-root", str(td_path)],
            capture_output=True, text=True, env=_cmg_env(orchestrator=True),
        )
        if r.returncode != 0:
            failures.append(f"[{fix_cmg}] orchestrator --cycle-begin must exit 0; got {r.returncode}")
            cmg_ok = False
        if cmg_marker.exists():
            try:
                _ovr = json.loads(cmg_marker.read_text(encoding="utf-8"))
                if _ovr.get("feature_id") != "bug-cmg2":
                    failures.append(f"[{fix_cmg}] orchestrator --cycle-begin must overwrite the marker")
                    cmg_ok = False
            except (OSError, json.JSONDecodeError):
                pass
        print(f"  {'PASS' if cmg_ok else 'FAIL'} [{fix_cmg}] subagent cycle-end/begin refused, orchestrator allowed")

        # -------------------------------------------------------------------
        # Fixture: --cycle-begin --kind real requires --sub-skill
        # (adhoc-cycle-begin-real-requires-sub-skill) — coupled-pair mirror of
        # lazy-state.py. A --kind real dispatch that omits --sub-skill must be
        # refused (non-zero exit, no marker mutation) BEFORE the marker is
        # ever written; --kind meta remains exempt and still succeeds without
        # --sub-skill. Driven via subprocess so the real CLI handler runs.
        # -------------------------------------------------------------------
        fix_rrs = "cycle-begin-real-requires-sub-skill"
        rrs_ok = True
        try:
            rrs_state = td_path / "rrs-state"
            rrs_state.mkdir(parents=True, exist_ok=True)
            rrs_marker = rrs_state / "lazy-cycle-active.json"
            rrs_env = {k: v for k, v in os.environ.items()
                       if k not in ("LAZY_CYCLE_SUBAGENT",)}
            rrs_env["LAZY_STATE_DIR"] = str(rrs_state)
            rrs_env["LAZY_ORCHESTRATOR"] = "1"
            # (a) --kind real without --sub-skill ⇒ non-zero exit, no marker.
            r = subprocess.run(
                [sys.executable, _this_script, "--cycle-begin",
                 "--bug-id", "bug-rrs", "--nonce", "deadbeef",
                 "--kind", "real", "--repo-root", str(td_path)],
                capture_output=True, text=True, env=rrs_env,
            )
            if r.returncode == 0:
                failures.append(f"[{fix_rrs}] real cycle w/o --sub-skill must exit non-zero; got 0")
                rrs_ok = False
            if rrs_marker.exists():
                failures.append(f"[{fix_rrs}] refused real cycle must NOT write a marker")
                rrs_ok = False
            # (b) --kind meta without --sub-skill ⇒ exit 0 (exemption preserved).
            r = subprocess.run(
                [sys.executable, _this_script, "--cycle-begin",
                 "--bug-id", "bug-rrs", "--nonce", "cafefeed",
                 "--kind", "meta", "--repo-root", str(td_path)],
                capture_output=True, text=True, env=rrs_env,
            )
            if r.returncode != 0:
                failures.append(f"[{fix_rrs}] meta cycle w/o --sub-skill must exit 0; got {r.returncode}: {r.stderr}")
                rrs_ok = False
            if not rrs_marker.exists():
                failures.append(f"[{fix_rrs}] meta cycle must write a marker")
                rrs_ok = False
            # (c) regression: --kind real WITH --sub-skill still succeeds.
            r = subprocess.run(
                [sys.executable, _this_script, "--cycle-begin",
                 "--bug-id", "bug-rrs", "--nonce", "abad1dea",
                 "--kind", "real", "--sub-skill", "execute-plan",
                 "--repo-root", str(td_path)],
                capture_output=True, text=True, env=rrs_env,
            )
            if r.returncode != 0:
                failures.append(f"[{fix_rrs}] real cycle w/ --sub-skill must exit 0; got {r.returncode}: {r.stderr}")
                rrs_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_rrs}] unexpected error: {exc!r}")
            rrs_ok = False
        print(f"  {'PASS' if rrs_ok else 'FAIL'} [{fix_rrs}] real requires --sub-skill, meta exempt, regression green")

        # -------------------------------------------------------------------
        # Fixture: --reorder-queue (no-sanctioned-queue-reorder-command P3).
        # Coupled-pair mirror of lazy-state.py --reorder-queue, on
        # docs/bugs/queue.json. Operator-only / out-of-cycle, gated by
        # refuse_if_cycle_active. Driven via subprocess so the real CLI handler
        # (gate → parse → reorder_queue) runs.
        # -------------------------------------------------------------------
        fix_ro = "reorder-queue"
        ro_ok = True
        _ro_script = str(Path(__file__).resolve())

        def _ro_repo(ids: list) -> "Path":
            import uuid as _uuid
            root = td_path / f"ro-{_uuid.uuid4().hex[:8]}"
            qdir = root / "docs" / "bugs"
            qdir.mkdir(parents=True, exist_ok=True)
            (qdir / "queue.json").write_text(
                json.dumps({"queue": [{"id": i, "name": i} for i in ids]},
                           indent=2) + "\n",
                encoding="utf-8",
            )
            return root

        def _ro_ids(root: "Path") -> list:
            data = json.loads(
                (root / "docs" / "bugs" / "queue.json").read_text(encoding="utf-8"))
            return [e["id"] for e in data["queue"]]

        def _ro_env(state_dir: "Path", *, cycle_marker: bool) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(state_dir)
            if cycle_marker:
                state_dir.mkdir(parents=True, exist_ok=True)
                (state_dir / "lazy-cycle-active.json").write_text(
                    json.dumps({"feature_id": "bug-ro", "nonce": "n",
                                "kind": "real", "commit_tally": 0,
                                "started_at": "2026-06-20T00:00:00Z",
                                "session_id": None}, indent=2) + "\n",
                    encoding="utf-8",
                )
            return e

        def _ro_run(root: "Path", to: str, *, item="a", cycle_marker=False):
            st = root / "ro-state"
            return subprocess.run(
                [sys.executable, _ro_script, "--repo-root", str(root),
                 "--reorder-queue", "--id", item, "--to", to],
                capture_output=True, text=True,
                env=_ro_env(st, cycle_marker=cycle_marker),
            )

        # (1) defer-to-tail
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "tail")
        if r.returncode != 0 or _ro_ids(r_root) != ["b", "c", "a"]:
            failures.append(f"[{fix_ro}] --to tail wrong: exit={r.returncode} order={_ro_ids(r_root)}: {r.stderr}")
            ro_ok = False
        # (2) move-to-head
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "head", item="c")
        if r.returncode != 0 or _ro_ids(r_root) != ["c", "a", "b"]:
            failures.append(f"[{fix_ro}] --to head wrong: exit={r.returncode} order={_ro_ids(r_root)}")
            ro_ok = False
        # (3) move-to-index
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "1")
        if r.returncode != 0 or _ro_ids(r_root) != ["b", "a", "c"]:
            failures.append(f"[{fix_ro}] --to 1 wrong: exit={r.returncode} order={_ro_ids(r_root)}")
            ro_ok = False
        # (4) remove
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "remove", item="b")
        if r.returncode != 0 or _ro_ids(r_root) != ["a", "c"]:
            failures.append(f"[{fix_ro}] --to remove wrong: exit={r.returncode} order={_ro_ids(r_root)}")
            ro_ok = False
        # (5) missing-entry → _die (exit 2), queue unchanged
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "tail", item="zzz")
        if r.returncode != 2 or _ro_ids(r_root) != ["a", "b", "c"]:
            failures.append(f"[{fix_ro}] missing-entry must exit 2 + not mutate; got {r.returncode}")
            ro_ok = False
        # (6) cycle-active refusal → exit 3, queue unchanged
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "tail", cycle_marker=True)
        if r.returncode != 3 or _ro_ids(r_root) != ["a", "b", "c"]:
            failures.append(f"[{fix_ro}] cycle-active must refuse exit 3 + leave queue unchanged; got {r.returncode}")
            ro_ok = False
        # (7) idempotent no-op (already at head) → exit 0, byte-stable
        r_root = _ro_repo(["a", "b", "c"])
        _ro_qp = r_root / "docs" / "bugs" / "queue.json"
        _ro_before = _ro_qp.read_bytes()
        r = _ro_run(r_root, "head")
        if r.returncode != 0 or _ro_qp.read_bytes() != _ro_before:
            failures.append(f"[{fix_ro}] idempotent no-op must exit 0 + byte-stable; got {r.returncode}")
            ro_ok = False
        print(f"  {'PASS' if ro_ok else 'FAIL'} [{fix_ro}] reorder tail/head/index/remove/missing/cycle-active/no-op")

        # -------------------------------------------------------------------
        # Fixture: cycle_prompt_ref surfacing (bug-pipeline-cycle-dispatch-
        # omits-cycle-prompt-ref Phase 1).
        #
        # When a run marker is active and --emit-prompt produces a non-null
        # cycle_prompt, bug-state.py must capture the register_emission_if_marked
        # return value and surface state["cycle_prompt_ref"] as a "@@lazy-ref
        # nonce=<hex>" token — mirroring lazy-state.py exactly.
        # When no marker is active, cycle_prompt_ref must be None.
        #
        # Uses the existing "mid-fix" fixture which routes to execute-plan
        # (emit_cycle_prompt returns a non-null prompt for that step).
        # Driven via subprocess so the full CLI path (--emit-prompt flag-gate,
        # register_emission_if_marked, state["cycle_prompt_ref"] assignment)
        # runs end-to-end.
        # -------------------------------------------------------------------
        fix_cpr = "cycle-prompt-ref-surfacing"
        cpr_ok = True
        _cpr_script = str(Path(__file__).resolve())
        cpr_root = _build_bug_fixture(td_path, "mid-fix")

        # Build a hermetic state dir scoped to this fixture.
        cpr_state = td_path / "cpr-state"
        cpr_state.mkdir(parents=True, exist_ok=True)

        def _cpr_env(*, with_marker: bool) -> dict:
            """Env for cpr subprocess; LAZY_STATE_DIR pinned to the fixture dir."""
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(cpr_state)
            return e

        # (a) Write a live run marker into the state dir so
        #     register_emission_if_marked sees an active run.
        import datetime as _cpr_dt
        _cpr_marker = {
            "pipeline": "bug",
            "cloud": False,
            "repo_root": str(cpr_root),
            "session_id": "test-session-cpr",
            "started_at": _cpr_dt.datetime.now(_cpr_dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ) + "Z",
            "max_cycles": None,
            "nonce_seed": None,
            "forward_cycles": 0,
            "meta_cycles": 0,
            "attended": True,
            "last_advance_consume_count": 0,
            "last_advance_state_key": None,
            "per_feature_forward_cycles": {},
            "per_feature_corrective_cycles": {},
            "work_branch": "main",
        }
        (cpr_state / "lazy-run-marker.json").write_text(
            json.dumps(_cpr_marker, indent=2) + "\n", encoding="utf-8"
        )

        # (b) With a live marker: --emit-prompt must surface cycle_prompt_ref
        #     as a @@lazy-ref token.
        r_cpr = subprocess.run(
            [sys.executable, _cpr_script,
             "--repo-root", str(cpr_root),
             "--emit-prompt"],
            capture_output=True, text=True,
            env=_cpr_env(with_marker=True),
        )
        if r_cpr.returncode != 0:
            failures.append(
                f"[{fix_cpr}] --emit-prompt with marker must exit 0; "
                f"got {r_cpr.returncode}: {r_cpr.stderr[:200]!r}"
            )
            cpr_ok = False
        else:
            try:
                cpr_state_out = json.loads(r_cpr.stdout)
                cpr_ref = cpr_state_out.get("cycle_prompt_ref")
                if not isinstance(cpr_ref, str) or not cpr_ref.startswith(
                    "@@lazy-ref nonce="
                ):
                    failures.append(
                        f"[{fix_cpr}] cycle_prompt_ref must be a '@@lazy-ref nonce=…' "
                        f"token when a run marker is active; got {cpr_ref!r}"
                    )
                    cpr_ok = False
            except (json.JSONDecodeError, ValueError) as exc:
                failures.append(
                    f"[{fix_cpr}] --emit-prompt stdout is not valid JSON: {exc}; "
                    f"stdout={r_cpr.stdout[:200]!r}"
                )
                cpr_ok = False

        # (c) Without a marker: cycle_prompt_ref must be None (absent marker →
        #     register_emission_if_marked no-ops → no ref to surface).
        cpr_state_nomark = td_path / "cpr-state-nomark"
        cpr_state_nomark.mkdir(parents=True, exist_ok=True)

        def _cpr_env_nomark() -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(cpr_state_nomark)
            return e

        r_cpr_nm = subprocess.run(
            [sys.executable, _cpr_script,
             "--repo-root", str(cpr_root),
             "--emit-prompt"],
            capture_output=True, text=True,
            env=_cpr_env_nomark(),
        )
        if r_cpr_nm.returncode != 0:
            failures.append(
                f"[{fix_cpr}] --emit-prompt without marker must exit 0; "
                f"got {r_cpr_nm.returncode}"
            )
            cpr_ok = False
        else:
            try:
                cpr_nm_out = json.loads(r_cpr_nm.stdout)
                cpr_nm_ref = cpr_nm_out.get("cycle_prompt_ref")
                if cpr_nm_ref is not None:
                    failures.append(
                        f"[{fix_cpr}] cycle_prompt_ref must be None (absent) when no "
                        f"marker is active; got {cpr_nm_ref!r}"
                    )
                    cpr_ok = False
            except (json.JSONDecodeError, ValueError) as exc:
                failures.append(
                    f"[{fix_cpr}] --emit-prompt (no marker) stdout is not valid JSON: "
                    f"{exc}; stdout={r_cpr_nm.stdout[:200]!r}"
                )
                cpr_ok = False

        print(
            f"  {'PASS' if cpr_ok else 'FAIL'} [{fix_cpr}] "
            f"cycle_prompt_ref surfaced with marker / None without"
        )

        # -------------------------------------------------------------------
        # Fixture: harness-telemetry-ledger Phase 2 — chokepoint emission
        # (coupled-pair mirror of the lazy-state.py fixture; --bug-id item ids,
        # pipeline "bug", no --gate-coverage — the documented divergence).
        # (a) bracket: --run-start → --cycle-begin → --cycle-end → --run-end ⇒
        #     four envelope-valid lines sharing ONE run_id (pipeline "bug").
        # (b) dispatch/halt at --emit-prompt (blocked bug ⇒ dispatch + halt).
        # (c) read-path purity: bare probe creates/appends nothing.
        # (d) refusal capture: subagent --apply-pseudo ⇒ exit 3 + ONE
        #     containment-refusal line; --verify-ledger dirty ⇒ gate-refusal.
        # (e) D5-B cloud flush at --cloud --run-end ⇒ committed segment +
        #     telemetry_flushed key.
        # -------------------------------------------------------------------
        fix_tl = "telemetry-ledger-chokepoints"
        tl_ok = True
        _tl_script = str(Path(__file__).resolve())
        _TL_LEDGER = "lazy-telemetry.jsonl"

        def _tl_env(state_dir: Path, *, orchestrator: bool = True) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(state_dir)
            if orchestrator:
                e["LAZY_ORCHESTRATOR"] = "1"
            return e

        def _tl_events(state_dir: Path) -> list:
            ledger = state_dir / _TL_LEDGER
            if not ledger.exists():
                return []
            return [json.loads(l) for l in
                    ledger.read_text(encoding="utf-8").splitlines() if l.strip()]

        try:
            # (a) full bracket — one run_id, pipeline "bug".
            tl_state = td_path / "tl-state"
            tl_state.mkdir(parents=True, exist_ok=True)
            tl_repo = td_path / "tl-repo"
            tl_repo.mkdir(parents=True, exist_ok=True)
            for cmd in (
                ["--run-start"],
                ["--cycle-begin", "--bug-id", "bug-tl", "--nonce", "abc123",
                 "--kind", "real", "--sub-skill", "execute-plan"],
                ["--cycle-end"],
                # --efficacy-skip-authorized: this hermetic bracket fixture does
                # not run the efficacy/canary/incident trio (the gate is
                # exercised dedicated in test_lazy_core.py).
                ["--run-end", "--reason", "terminal",
                 "--terminal-reason", "all-bugs-fixed",
                 "--efficacy-skip-authorized"],
            ):
                r = subprocess.run(
                    [sys.executable, _tl_script, "--repo-root", str(tl_repo)] + cmd,
                    capture_output=True, text=True, env=_tl_env(tl_state),
                )
                if r.returncode != 0:
                    failures.append(
                        f"[{fix_tl}] {cmd[0]} must exit 0; got {r.returncode}: "
                        f"{r.stderr[:200]}"
                    )
                    tl_ok = False
            ev = _tl_events(tl_state)
            got_types = [e.get("event") for e in ev]
            if got_types != ["run-start", "cycle-begin", "cycle-end", "run-end"]:
                failures.append(f"[{fix_tl}] bracket events wrong: {got_types}")
                tl_ok = False
            if ev:
                run_ids = {e.get("run_id") for e in ev}
                if len(run_ids) != 1 or None in run_ids:
                    failures.append(f"[{fix_tl}] bracket must share ONE run_id: {run_ids}")
                    tl_ok = False
                for e in ev:
                    if set(e) != {"v", "ts", "run_id", "pipeline", "event",
                                  "item_id", "data"}:
                        failures.append(f"[{fix_tl}] envelope keys wrong: {sorted(e)}")
                        tl_ok = False
                        break
                if ev[0].get("pipeline") != "bug":
                    failures.append(f"[{fix_tl}] pipeline must be 'bug': {ev[0]}")
                    tl_ok = False
                if ev[1].get("item_id") != "bug-tl":
                    failures.append(f"[{fix_tl}] cycle-begin item_id wrong: {ev[1]}")
                    tl_ok = False

            # (b) dispatch + halt at --emit-prompt (blocked bug fixture).
            tl_state_b = td_path / "tl-state-b"
            tl_state_b.mkdir(parents=True, exist_ok=True)
            halt_root = _build_bug_fixture(td_path, "blocked")
            subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--run-start"],
                capture_output=True, text=True, env=_tl_env(tl_state_b),
            )
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--emit-prompt"],
                capture_output=True, text=True, env=_tl_env(tl_state_b),
            )
            probe_json = json.loads(r.stdout)
            if "telemetry_flushed" in probe_json:
                failures.append(f"[{fix_tl}] --emit-prompt output must gain no telemetry keys")
                tl_ok = False
            ev_b = _tl_events(tl_state_b)
            types_b = [e.get("event") for e in ev_b]
            if types_b != ["run-start", "dispatch", "halt"]:
                failures.append(f"[{fix_tl}] emit-prompt events wrong: {types_b}")
                tl_ok = False
            else:
                disp = ev_b[1]
                if (disp.get("item_id") != "bug-blocked"
                        or disp["data"].get("terminal_reason") != "blocked"):
                    failures.append(f"[{fix_tl}] dispatch payload wrong: {disp}")
                    tl_ok = False

            # (c) read-path purity — no marker: bare probe creates NOTHING.
            tl_state_c = td_path / "tl-state-c"  # deliberately NOT created
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root)],
                capture_output=True, text=True,
                env=_tl_env(tl_state_c, orchestrator=False),
            )
            if r.returncode != 0:
                failures.append(f"[{fix_tl}] bare probe must exit 0; got {r.returncode}")
                tl_ok = False
            if tl_state_c.exists():
                failures.append(f"[{fix_tl}] bare probe (no marker) must not create the state dir")
                tl_ok = False
            #     — marker present: bare probe appends nothing.
            before = (tl_state_b / _TL_LEDGER).read_bytes()
            subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root)],
                capture_output=True, text=True,
                env=_tl_env(tl_state_b, orchestrator=False),
            )
            if (tl_state_b / _TL_LEDGER).read_bytes() != before:
                failures.append(f"[{fix_tl}] bare probe under a marker must append NOTHING")
                tl_ok = False

            # (d1) subagent --apply-pseudo ⇒ exit 3 + containment-refusal line.
            subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--cycle-begin", "--bug-id", "bug-blocked", "--nonce", "beef",
                 "--kind", "real", "--sub-skill", "execute-plan"],
                capture_output=True, text=True, env=_tl_env(tl_state_b),
            )
            n_before = len(_tl_events(tl_state_b))
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--apply-pseudo", "__mark_fixed__",
                 str(halt_root / "docs" / "bugs" / "bug-blocked" / "SPEC.md")],
                capture_output=True, text=True,
                env=_tl_env(tl_state_b, orchestrator=False),
            )
            if r.returncode != 3:
                failures.append(f"[{fix_tl}] subagent --apply-pseudo must exit 3; got {r.returncode}")
                tl_ok = False
            ev_d = _tl_events(tl_state_b)
            if len(ev_d) != n_before + 1 or ev_d[-1].get("event") != "containment-refusal":
                failures.append(
                    f"[{fix_tl}] refusal must append exactly ONE containment-refusal "
                    f"line: {[e.get('event') for e in ev_d[n_before:]]}"
                )
                tl_ok = False
            elif ev_d[-1]["data"].get("op") != "--apply-pseudo":
                failures.append(f"[{fix_tl}] containment-refusal op wrong: {ev_d[-1]}")
                tl_ok = False

            # (d2) --verify-ledger on a non-git tree ⇒ exit 1 + gate-refusal.
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--verify-ledger",
                 str(halt_root / "docs" / "bugs" / "bug-blocked")],
                capture_output=True, text=True, env=_tl_env(tl_state_b),
            )
            if r.returncode != 1:
                failures.append(f"[{fix_tl}] --verify-ledger dirty must exit 1; got {r.returncode}")
                tl_ok = False
            ev_d2 = _tl_events(tl_state_b)
            if not ev_d2 or ev_d2[-1].get("event") != "gate-refusal" \
                    or ev_d2[-1]["data"].get("gate") != "verify-ledger" \
                    or not ev_d2[-1]["data"].get("failing_check"):
                failures.append(f"[{fix_tl}] gate-refusal (verify-ledger) missing/wrong: {ev_d2[-1:]}")
                tl_ok = False

            # (e) D5-B cloud flush at --cloud --run-end.
            tl_state_e = td_path / "tl-state-e"
            tl_state_e.mkdir(parents=True, exist_ok=True)
            tl_repo_e = td_path / "tl-repo-e"
            tl_repo_e.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(tl_repo_e),
                 "--cloud", "--run-start"],
                capture_output=True, text=True, env=_tl_env(tl_state_e),
            )
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(tl_repo_e),
                 "--cloud", "--run-end", "--reason", "terminal",
                 "--terminal-reason", "all-bugs-fixed",
                 "--efficacy-skip-authorized"],
                capture_output=True, text=True, env=_tl_env(tl_state_e),
            )
            if r.returncode != 0:
                failures.append(f"[{fix_tl}] cloud --run-end must exit 0; got {r.returncode}")
                tl_ok = False
            out_e = json.loads(r.stdout) if r.stdout else {}
            flushed = out_e.get("telemetry_flushed")
            if not (isinstance(flushed, dict) and flushed.get("events", 0) >= 2):
                failures.append(f"[{fix_tl}] cloud --run-end must surface telemetry_flushed: {out_e}")
                tl_ok = False
            else:
                seg = Path(flushed["path"])
                if not seg.exists() or ":" in seg.name \
                        or seg.parent != tl_repo_e / "docs" / "telemetry" / "cloud":
                    failures.append(f"[{fix_tl}] cloud segment missing/misplaced: {flushed}")
                    tl_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_tl}] unexpected error: {exc!r}")
            tl_ok = False
        print(f"  {'PASS' if tl_ok else 'FAIL'} [{fix_tl}] bracket/dispatch/purity/refusal/cloud-flush emission")
        # Fixture: queue-dependency-dag Phase 2 — the bug-pipeline dep-gate
        # (coupled-pair mirror of lazy-state.py's). Covers: hold + advance,
        # ARCHIVE-AWARE dep resolution (D9 divergence 2: a dep fixed +
        # archived under docs/bugs/_archive/<id>/ counts complete), the
        # Won't-fix / dangling unknown-dependency fail-fast (D4), and the
        # all-gated queue-exhausted-dependency-gated terminal.
        # -------------------------------------------------------------------
        fix_dg = "dep-gate"
        dg_ok = True

        def _dg_bug(root: Path, bid: str, *, status: str = "Open",
                    receipt: bool = False, archived: bool = False) -> Path:
            base = root / "docs" / "bugs"
            if archived:
                base = base / "_archive"
            d = base / bid
            d.mkdir(parents=True, exist_ok=True)
            (d / "SPEC.md").write_text(
                f"# {bid}\n\n**Status:** {status}\n**Severity:** P2\n"
                "**Discovered:** 2026-07-04\n",
                encoding="utf-8",
            )
            if receipt:
                (d / "FIXED.md").write_text(
                    f"---\nkind: fixed\nbug_id: {bid}\n"
                    "provenance: mark-fixed\n---\n\n# Fixed\n",
                    encoding="utf-8",
                )
            return d

        # (a) Hold + advance: bug-dg-b (deps:[bug-dg-a]) ahead of bug-dg-a →
        #     bug-dg-a dispatched, dep_gated names bug-dg-b.
        dg_root = td_path / "bug-dep-gate"
        dg_bugs = dg_root / "docs" / "bugs"
        dg_bugs.mkdir(parents=True, exist_ok=True)
        (dg_bugs / "queue.json").write_text(json.dumps({"queue": [
            {"id": "bug-dg-b", "name": "DG Bug B", "spec_dir": "bug-dg-b",
             "severity": "P1", "deps": ["bug-dg-a"]},
            {"id": "bug-dg-a", "name": "DG Bug A", "spec_dir": "bug-dg-a",
             "severity": "P2"},
        ]}))
        _dg_bug(dg_root, "bug-dg-a")
        _dg_bug(dg_root, "bug-dg-b")
        dg_st = compute_state(dg_root, cloud=False, real_device=True)
        if dg_st.get("feature_id") != "bug-dg-a":
            failures.append(
                f"[{fix_dg}] hold+advance: expected bug-dg-a dispatched past the "
                f"held dependent, got {dg_st.get('feature_id')!r} "
                f"(terminal={dg_st.get('terminal_reason')!r})"
            )
            dg_ok = False
        if dg_st.get("dep_gated") != [
            {"id": "bug-dg-b", "missing": ["bug-dg-a"]},
        ]:
            failures.append(
                f"[{fix_dg}] hold+advance: expected dep_gated to name bug-dg-b "
                f"missing bug-dg-a, got {dg_st.get('dep_gated')!r}"
            )
            dg_ok = False

        # (b) Archive-aware unlock: bug-dg-c deps a bug that exists ONLY under
        #     docs/bugs/_archive/ (Fixed + FIXED.md receipt — the
        #     __mark_fixed__ end-state) → the dep is complete, c dispatches.
        dga_root = td_path / "bug-dep-gate-archive"
        dga_bugs = dga_root / "docs" / "bugs"
        dga_bugs.mkdir(parents=True, exist_ok=True)
        (dga_bugs / "queue.json").write_text(json.dumps({"queue": [
            {"id": "bug-dg-c", "name": "DG Bug C", "spec_dir": "bug-dg-c",
             "severity": "P1", "deps": ["bug-dg-x"]},
        ]}))
        _dg_bug(dga_root, "bug-dg-c")
        _dg_bug(dga_root, "bug-dg-x", status="Fixed", receipt=True,
                archived=True)
        dga_st = compute_state(dga_root, cloud=False, real_device=True)
        if dga_st.get("feature_id") != "bug-dg-c" or dga_st.get("dep_gated"):
            failures.append(
                f"[{fix_dg}] archive-aware: expected bug-dg-c dispatched (its dep "
                f"is fixed + archived), got {dga_st.get('feature_id')!r} "
                f"dep_gated={dga_st.get('dep_gated')!r}"
            )
            dg_ok = False

        # (c) Won't-fix dep → unknown-dependency fail-fast on the DEPENDENT
        #     (the bug-side analog of a Superseded feature upstream — the work
        #     never happened).
        dgw_root = td_path / "bug-dep-gate-wontfix"
        dgw_bugs = dgw_root / "docs" / "bugs"
        dgw_bugs.mkdir(parents=True, exist_ok=True)
        (dgw_bugs / "queue.json").write_text(json.dumps({"queue": [
            {"id": "bug-dg-d", "name": "DG Bug D", "spec_dir": "bug-dg-d",
             "severity": "P1", "deps": ["bug-dg-w"]},
        ]}))
        _dg_bug(dgw_root, "bug-dg-d")
        _dg_bug(dgw_root, "bug-dg-w", status="Won't-fix")
        dgw_st = compute_state(dgw_root, cloud=False, real_device=True)
        dgw_blocked = dgw_bugs / "bug-dg-d" / "BLOCKED.md"
        if dgw_st.get("terminal_reason") != TR_BLOCKED \
                or dgw_st.get("feature_id") != "bug-dg-d" \
                or not dgw_blocked.exists():
            failures.append(
                f"[{fix_dg}] wont-fix dep: expected unknown-dependency blocked "
                f"halt on bug-dg-d, got "
                f"terminal={dgw_st.get('terminal_reason')!r} "
                f"blocked_exists={dgw_blocked.exists()}"
            )
            dg_ok = False
        else:
            dgw_meta = parse_sentinel(dgw_blocked) or {}
            if dgw_meta.get("blocker_kind") != "unknown-dependency":
                failures.append(
                    f"[{fix_dg}] wont-fix dep: expected blocker_kind "
                    f"unknown-dependency, got {dgw_meta.get('blocker_kind')!r}"
                )
                dg_ok = False

        # (d) Dangling dep id (resolves nowhere, open or archived) → the same
        #     fail-fast.
        dgd_root = td_path / "bug-dep-gate-dangling"
        dgd_bugs = dgd_root / "docs" / "bugs"
        dgd_bugs.mkdir(parents=True, exist_ok=True)
        (dgd_bugs / "queue.json").write_text(json.dumps({"queue": [
            {"id": "bug-dg-e", "name": "DG Bug E", "spec_dir": "bug-dg-e",
             "severity": "P1", "deps": ["bug-dg-ghost"]},
        ]}))
        _dg_bug(dgd_root, "bug-dg-e")
        dgd_st = compute_state(dgd_root, cloud=False, real_device=True)
        if dgd_st.get("terminal_reason") != TR_BLOCKED \
                or not (dgd_bugs / "bug-dg-e" / "BLOCKED.md").exists():
            failures.append(
                f"[{fix_dg}] dangling dep: expected unknown-dependency blocked "
                f"halt on bug-dg-e, got "
                f"terminal={dgd_st.get('terminal_reason')!r}"
            )
            dg_ok = False

        # (e) All-gated clean terminal: the dependent is dep-gated and its dep
        #     is parked (BLOCKED.md under --park-blocked) → nothing dispatches
        #     → queue-exhausted-dependency-gated (checked BEFORE the all-parked
        #     fallback; an honest distinct terminal, never all-bugs-fixed).
        dgt_root = td_path / "bug-dep-gate-terminal"
        dgt_bugs = dgt_root / "docs" / "bugs"
        dgt_bugs.mkdir(parents=True, exist_ok=True)
        (dgt_bugs / "queue.json").write_text(json.dumps({"queue": [
            {"id": "bug-dg-f", "name": "DG Bug F", "spec_dir": "bug-dg-f",
             "severity": "P1", "deps": ["bug-dg-g"]},
            {"id": "bug-dg-g", "name": "DG Bug G", "spec_dir": "bug-dg-g",
             "severity": "P2"},
        ]}))
        _dg_bug(dgt_root, "bug-dg-f")
        dgt_g = _dg_bug(dgt_root, "bug-dg-g")
        _write_yaml_blocked_sentinel(
            dgt_g / "BLOCKED.md", feature_id="bug-dg-g", phase="Fix",
            blocker_kind="external", blocked_at="2026-07-04T00:00:00Z",
            retry_count=0,
        )
        dgt_st = compute_state(
            dgt_root, cloud=False, real_device=True, park_blocked=True
        )
        if dgt_st.get("terminal_reason") != "queue-exhausted-dependency-gated":
            failures.append(
                f"[{fix_dg}] all-gated terminal: expected "
                f"queue-exhausted-dependency-gated, got "
                f"{dgt_st.get('terminal_reason')!r}"
            )
            dg_ok = False
        if dgt_st.get("dep_gated") != [
            {"id": "bug-dg-f", "missing": ["bug-dg-g"]},
        ]:
            failures.append(
                f"[{fix_dg}] all-gated terminal: expected the flush to name the "
                f"held item + missing dep, got {dgt_st.get('dep_gated')!r}"
            )
            dg_ok = False

        print(
            f"  {'PASS' if dg_ok else 'FAIL'} [{fix_dg}] "
            f"hold+advance / archive-aware / wont-fix+dangling fail-fast / "
            f"all-gated terminal"
        )

        # -------------------------------------------------------------------
        # Fixture: queue-dependency-dag Phase 4 — the bug-pipeline feeder
        # (coupled-pair mirror of lazy-state.py's --sync-deps) + --enqueue-adhoc
        # --deps. --sync-deps projects the bug SPEC's hard deps into
        # docs/bugs/queue.json (script-owned, atomic), is a byte-stable
        # noop:true on re-run, and is REFUSED exit 3 with zero side effects for
        # a cycle subagent.
        # -------------------------------------------------------------------
        fix_sd = "sync-deps"
        sd_ok = True
        sd_root = td_path / "bug-sync-deps"
        sd_bugs = sd_root / "docs" / "bugs"
        sd_bugs.mkdir(parents=True, exist_ok=True)
        (sd_bugs / "queue.json").write_text(json.dumps({"queue": [
            {"id": "bug-sd", "name": "SD Bug", "spec_dir": "bug-sd",
             "severity": "P1"},
            {"id": "bug-sd-up", "name": "SD Bug Up", "spec_dir": "bug-sd-up",
             "severity": "P2"},
        ]}, indent=2) + "\n")
        _dg_bug(sd_root, "bug-sd")
        (sd_bugs / "bug-sd" / "SPEC.md").write_text(
            "# bug-sd\n\n**Status:** Open\n**Severity:** P1\n"
            "**Discovered:** 2026-07-04\n\n"
            "**Depends on:**\n- bug-sd-up — hard — must land first\n",
            encoding="utf-8",
        )
        _dg_bug(sd_root, "bug-sd-up")
        _sd_script = str(Path(__file__).resolve())
        _sd_state = td_path / "bug-sd-state"
        _sd_state.mkdir(parents=True, exist_ok=True)

        def _sd_env(**extra: str) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(_sd_state)
            e.update(extra)
            return e

        sd_before = (sd_bugs / "queue.json").read_bytes()
        r_sd_refuse = subprocess.run(
            [sys.executable, _sd_script, "--sync-deps", "--id", "bug-sd",
             "--repo-root", str(sd_root)],
            capture_output=True, text=True,
            env=_sd_env(LAZY_CYCLE_SUBAGENT="1"),
        )
        if r_sd_refuse.returncode != 3 \
                or (sd_bugs / "queue.json").read_bytes() != sd_before:
            failures.append(
                f"[{fix_sd}] cycle-subagent refusal: expected exit 3 with zero "
                f"side effects, got rc={r_sd_refuse.returncode}"
            )
            sd_ok = False
        r_sd = subprocess.run(
            [sys.executable, _sd_script, "--sync-deps", "--id", "bug-sd",
             "--repo-root", str(sd_root)],
            capture_output=True, text=True,
            env=_sd_env(LAZY_ORCHESTRATOR="1"),
        )
        sd_queue = json.loads((sd_bugs / "queue.json").read_text())
        if r_sd.returncode != 0 \
                or sd_queue["queue"][0].get("deps") != ["bug-sd-up"]:
            failures.append(
                f"[{fix_sd}] write: expected exit 0 + deps=['bug-sd-up'], got "
                f"rc={r_sd.returncode} entry={sd_queue['queue'][0]!r} "
                f"stderr={r_sd.stderr[:200]!r}"
            )
            sd_ok = False
        sd_after_first = (sd_bugs / "queue.json").read_bytes()
        r_sd2 = subprocess.run(
            [sys.executable, _sd_script, "--sync-deps", "--id", "bug-sd",
             "--repo-root", str(sd_root)],
            capture_output=True, text=True,
            env=_sd_env(LAZY_ORCHESTRATOR="1"),
        )
        try:
            sd_out2 = json.loads(r_sd2.stdout)
        except json.JSONDecodeError:
            sd_out2 = {}
        if r_sd2.returncode != 0 or sd_out2.get("noop") is not True \
                or (sd_bugs / "queue.json").read_bytes() != sd_after_first:
            failures.append(
                f"[{fix_sd}] idempotent re-run: expected noop:true + "
                f"byte-identical file, got rc={r_sd2.returncode} out={sd_out2!r}"
            )
            sd_ok = False

        # Probe-time drift diagnostic (bug-side mirror): the synced entry now
        # carries deps ['bug-sd-up']; rewriting the SPEC block to (none) makes
        # the sets diverge → a lint-grade dep-drift diagnostic (no halt).
        (sd_bugs / "bug-sd" / "SPEC.md").write_text(
            "# bug-sd\n\n**Status:** Open\n**Severity:** P1\n"
            "**Discovered:** 2026-07-04\n\n"
            "**Depends on:** (none)\n",
            encoding="utf-8",
        )
        sd_drift_st = compute_state(sd_root, cloud=False, real_device=True)
        if not any("dep-drift" in d for d in sd_drift_st.get("diagnostics", [])):
            failures.append(
                f"[{fix_sd}] drift: expected a dep-drift diagnostic after the "
                f"SPEC block diverged from the synced queue deps, got "
                f"{sd_drift_st.get('diagnostics')!r}"
            )
            sd_ok = False

        # --enqueue-adhoc --deps (function-level): the prepended bug entry
        # carries the validated deps list; a reserved prefix is refused.
        enqd_root = td_path / "bug-enqueue-deps"
        enqd_root.mkdir(parents=True, exist_ok=True)
        enqd_res = enqueue_adhoc(
            enqd_root, "adhoc-bug-dep", "Adhoc Bug Dep", deps=["bug-sd-up"],
        )
        enqd_queue = json.loads(
            (enqd_root / "docs" / "bugs" / "queue.json").read_text()
        )
        if enqd_res.get("status") != "queued" \
                or enqd_queue["queue"][0].get("deps") != ["bug-sd-up"]:
            failures.append(
                f"[{fix_sd}] enqueue --deps: expected deps=['bug-sd-up'] on the "
                f"prepended entry, got {enqd_queue['queue'][0]!r}"
            )
            sd_ok = False
        try:
            enqueue_adhoc(
                enqd_root, "adhoc-bug-dep-bad", "Bad",
                deps=["feature:some-feat"],
            )
            failures.append(
                f"[{fix_sd}] enqueue --deps: a reserved feature: prefixed dep "
                f"id must be refused (_die), but was accepted"
            )
            sd_ok = False
        except SystemExit:
            pass

        print(
            f"  {'PASS' if sd_ok else 'FAIL'} [{fix_sd}] "
            f"cycle-subagent exit-3 refusal + hard-only projection + "
            f"idempotent noop + enqueue --deps"
        )

        # -------------------------------------------------------------------
        # Fixture: --cycle-end commit-bracket append is FAIL-OPEN
        # (code-doc-provenance-linkage Phase 1 / D4-A) — coupled-pair mirror of
        # lazy-state.py's fixture. A directory squatting on the ledger filename
        # makes the bracket append unwritable; the orchestrator --cycle-end
        # must STILL exit 0 and clear the marker, with no commit_bracket key.
        # -------------------------------------------------------------------
        fix_cbfo = "cycle-end-bracket-fail-open"
        cbfo_ok = True
        try:
            cbfo_state = td_path / "cbfo-state"
            cbfo_state.mkdir(parents=True, exist_ok=True)
            # Squat a DIRECTORY on the ledger name so open(..., "a") fails.
            (cbfo_state / "lazy-commit-brackets.jsonl").mkdir()
            cbfo_repo = td_path / "cbfo-repo"
            cbfo_repo.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "-C", str(cbfo_repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(cbfo_repo), "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", str(cbfo_repo), "config", "user.name", "t"], check=True)
            # Hermetic: never depend on the host's commit-signing setup.
            subprocess.run(["git", "-C", str(cbfo_repo), "config", "commit.gpgsign", "false"], check=True)
            (cbfo_repo / "seed.txt").write_text("seed", encoding="utf-8")
            subprocess.run(["git", "-C", str(cbfo_repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(cbfo_repo), "commit", "-q", "-m", "seed"], check=True)
            cbfo_env = {k: v for k, v in os.environ.items()
                        if k not in ("LAZY_CYCLE_SUBAGENT",)}
            cbfo_env["LAZY_STATE_DIR"] = str(cbfo_state)
            cbfo_env["LAZY_ORCHESTRATOR"] = "1"
            _cbfo_script = str(Path(__file__).resolve())
            r = subprocess.run(
                [sys.executable, _cbfo_script, "--cycle-begin",
                 "--bug-id", "bug-cbfo", "--nonce", "beef",
                 "--sub-skill", "execute-plan",
                 "--repo-root", str(cbfo_repo)],
                capture_output=True, text=True, env=cbfo_env,
            )
            if r.returncode != 0:
                failures.append(f"[{fix_cbfo}] --cycle-begin must exit 0; got {r.returncode}: {r.stderr}")
                cbfo_ok = False
            # Advance HEAD so a real (non-empty) bracket is attempted.
            (cbfo_repo / "work.txt").write_text("work", encoding="utf-8")
            subprocess.run(["git", "-C", str(cbfo_repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(cbfo_repo), "commit", "-q", "-m", "work"], check=True)
            r = subprocess.run(
                [sys.executable, _cbfo_script, "--cycle-end",
                 "--repo-root", str(cbfo_repo)],
                capture_output=True, text=True, env=cbfo_env,
            )
            if r.returncode != 0:
                failures.append(f"[{fix_cbfo}] --cycle-end must exit 0 despite the unwritable ledger; got {r.returncode}: {r.stderr}")
                cbfo_ok = False
            if (cbfo_state / "lazy-cycle-active.json").exists():
                failures.append(f"[{fix_cbfo}] --cycle-end must still clear the marker (fail-open)")
                cbfo_ok = False
            try:
                cbfo_out = json.loads(r.stdout)
                if cbfo_out.get("cycle_marker_cleared") is not True:
                    failures.append(f"[{fix_cbfo}] JSON must report cycle_marker_cleared: true")
                    cbfo_ok = False
                if "commit_bracket" in cbfo_out:
                    failures.append(f"[{fix_cbfo}] a failed append must NOT report a commit_bracket")
                    cbfo_ok = False
            except (json.JSONDecodeError, TypeError):
                failures.append(f"[{fix_cbfo}] --cycle-end stdout must be JSON; got {r.stdout!r}")
                cbfo_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_cbfo}] unexpected error: {exc!r}")
            cbfo_ok = False
        print(f"  {'PASS' if cbfo_ok else 'FAIL'} [{fix_cbfo}] unwritable bracket ledger never blocks the --cycle-end clear")

        # Fixture: parallel-worktree-batch-execution — lane markers (D2-A,
        # coupled-pair mirror of lazy-state.py; the marker is SHARED).
        # (a) --run-start --parent-run stamps the lane marker (owner-bound,
        #     per-lane --max-cycles slice); (b) rogue second --run-start →
        #     exit 3, marker intact; (c) malformed --parent-run → exit 2,
        #     zero side effects; (d) subagent --run-end at the lane state dir
        #     → exit 3; (e) serial --run-start mints parent_run: null.
        # -------------------------------------------------------------------
        fix_lane = "lane-parent-run-marker"
        lane_ok = True
        _lane_script = str(Path(__file__).resolve())

        def _lane_env(state_dir: "Path", **extra: str) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(state_dir)
            e.update(extra)
            return e

        try:
            lane_state = td_path / "lane-state"
            lane_state.mkdir(parents=True, exist_ok=True)
            lane_repo = td_path / "lane-repo"
            lane_repo.mkdir(parents=True, exist_ok=True)
            parent_identity = (
                '{"repo_root": "/main/root", "started_at": "2026-07-04T00:00:00Z"}'
            )
            r = subprocess.run(
                [sys.executable, _lane_script, "--repo-root", str(lane_repo),
                 "--run-start", "--session-id", "coordinator-sess",
                 "--max-cycles", "8", "--parent-run", parent_identity],
                capture_output=True, text=True,
                env=_lane_env(lane_state, LAZY_ORCHESTRATOR="1"),
            )
            out_lane = json.loads(r.stdout) if r.stdout else {}
            if r.returncode != 0 \
                    or out_lane.get("parent_run") != {
                        "repo_root": "/main/root",
                        "started_at": "2026-07-04T00:00:00Z"} \
                    or out_lane.get("session_id") != "coordinator-sess" \
                    or out_lane.get("max_cycles") != 8:
                failures.append(
                    f"[{fix_lane}] lane --run-start must stamp parent_run + the "
                    f"owner session + the per-lane max-cycles slice; got "
                    f"rc={r.returncode} {out_lane!r}"
                )
                lane_ok = False
            marker_path_lane = lane_state / "lazy-run-marker.json"
            marker_bytes_lane = marker_path_lane.read_bytes()
            # (b) rogue second walker at the lane root → exit 3, marker intact.
            r = subprocess.run(
                [sys.executable, _lane_script, "--repo-root", str(lane_repo),
                 "--run-start"],
                capture_output=True, text=True,
                env=_lane_env(lane_state, LAZY_ORCHESTRATOR="1"),
            )
            if r.returncode != 3 or marker_path_lane.read_bytes() != marker_bytes_lane:
                failures.append(
                    f"[{fix_lane}] rogue second --run-start at the lane root must "
                    f"refuse exit 3 with the lane marker intact; got {r.returncode}"
                )
                lane_ok = False
            # (d) containment in-lane: subagent --run-end → exit 3, marker survives.
            r = subprocess.run(
                [sys.executable, _lane_script, "--repo-root", str(lane_repo),
                 "--run-end", "--reason", "terminal"],
                capture_output=True, text=True,
                env=_lane_env(lane_state, LAZY_CYCLE_SUBAGENT="1"),
            )
            if r.returncode != 3 or not marker_path_lane.exists():
                failures.append(
                    f"[{fix_lane}] subagent --run-end at the lane state dir must "
                    f"refuse exit 3 leaving the lane marker; got {r.returncode}"
                )
                lane_ok = False
            # (c) malformed --parent-run in a FRESH state dir → exit 2, no marker.
            lane_state_bad = td_path / "lane-state-bad"
            lane_state_bad.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                [sys.executable, _lane_script, "--repo-root", str(lane_repo),
                 "--run-start", "--parent-run", '["not", "a", "dict"]'],
                capture_output=True, text=True,
                env=_lane_env(lane_state_bad, LAZY_ORCHESTRATOR="1"),
            )
            if r.returncode != 2 or (lane_state_bad / "lazy-run-marker.json").exists():
                failures.append(
                    f"[{fix_lane}] malformed --parent-run must exit 2 with ZERO "
                    f"side effects; got {r.returncode}"
                )
                lane_ok = False
            # (e) serial --run-start mints parent_run: null (stable shape).
            lane_state_serial = td_path / "lane-state-serial"
            lane_state_serial.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                [sys.executable, _lane_script, "--repo-root", str(lane_repo),
                 "--run-start"],
                capture_output=True, text=True,
                env=_lane_env(lane_state_serial, LAZY_ORCHESTRATOR="1"),
            )
            out_serial = json.loads(r.stdout) if r.stdout else {}
            if r.returncode != 0 or "parent_run" not in out_serial \
                    or out_serial.get("parent_run") is not None:
                failures.append(
                    f"[{fix_lane}] serial --run-start must mint parent_run: null; "
                    f"got rc={r.returncode} {out_serial.get('parent_run')!r}"
                )
                lane_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_lane}] unexpected error: {exc!r}")
            lane_ok = False
        print(f"  {'PASS' if lane_ok else 'FAIL'} [{fix_lane}] parent_run stamp/rogue-refusal/containment/serial-null")


    # -----------------------------------------------------------------------
    # operator-halt-notifications Phase 2 — call-site wiring fixture
    # (coupled-pair mirror of lazy-state.py's [notify-halt-call-site]).
    # Drives main() IN-PROCESS against a BLOCKED.md bug halt with a fake
    # config + monkeypatched module ntfy sender: first probe pages once
    # (ledger identity carries pipeline="bug"), second probe dedups, kill
    # switch is byte-inert. Hermetic: LAZY_STATE_DIR temp dir; env, sender,
    # argv, and the active-repo binding restored.
    # -----------------------------------------------------------------------
    fix_nh = "notify-halt-call-site"
    nh_ok = True
    try:
        import io as _nh_io
        with tempfile.TemporaryDirectory(prefix="bug-notify-fixture-") as nh_td:
            nh_root = Path(nh_td) / "repo"
            nh_bug = nh_root / "docs" / "bugs" / "bug-nh"
            nh_bug.mkdir(parents=True)
            (nh_root / "docs" / "bugs" / "queue.json").write_text(json.dumps({
                "queue": [{"id": "bug-nh", "name": "Notify Halt Bug",
                           "spec_dir": "bug-nh"}]
            }), encoding="utf-8")
            (nh_bug / "SPEC.md").write_text(
                "# Notify Halt Bug\n\n**Status:** Investigating\n\n"
                "**Severity:** P1\n\n**Discovered:** 2026-07-04\n",
                encoding="utf-8",
            )
            (nh_bug / "BLOCKED.md").write_text(
                "---\nkind: blocked\nfeature_id: bug-nh\nphase: fix\n"
                "blocked_at: 2026-07-04T00:00:00Z\nretry_count: 0\n---\n"
                "## Details\nblocked\n",
                encoding="utf-8",
            )
            nh_state_dir = Path(nh_td) / "state"
            nh_state_dir.mkdir()
            nh_saved_env = {k: os.environ.get(k) for k in
                            ("LAZY_STATE_DIR", "LAZY_NOTIFY_URL",
                             "LAZY_NOTIFY_DISABLE")}
            os.environ["LAZY_STATE_DIR"] = str(nh_state_dir)
            os.environ["LAZY_NOTIFY_URL"] = "https://ntfy.example/fixture-topic"
            os.environ.pop("LAZY_NOTIFY_DISABLE", None)
            nh_sends: list = []
            nh_real_send = lazy_core.notifyplane._ntfy_send
            nh_prev_repo = getattr(lazy_core, "_active_repo_root", None)
            lazy_core.notifyplane._ntfy_send = (
                lambda url, t, b, l=None: nh_sends.append((url, t, b, l))
            )
            nh_argv = sys.argv

            def _nh_run() -> str:
                buf = _nh_io.StringIO()
                sys.argv = ["bug-state.py", "--repo-root", str(nh_root)]
                real_stdout = sys.stdout
                sys.stdout = buf
                try:
                    rc = main()
                finally:
                    sys.stdout = real_stdout
                    sys.argv = nh_argv
                if rc != 0:
                    raise AssertionError(f"main() must exit 0, got {rc}")
                return buf.getvalue()

            try:
                out1 = _nh_run()
                st1 = json.loads(out1)
                if st1.get("terminal_reason") != TR_BLOCKED:
                    failures.append(
                        f"[{fix_nh}] expected terminal_reason='blocked', "
                        f"got {st1.get('terminal_reason')!r}")
                    nh_ok = False
                if len(nh_sends) != 1:
                    failures.append(
                        f"[{fix_nh}] first probe must page exactly once, "
                        f"got {len(nh_sends)} send(s)")
                    nh_ok = False
                # The ledger identity must carry the BUG pipeline (the call
                # site threads pipeline="bug" — the coupled-pair divergence).
                nh_ledger = json.loads(
                    (nh_state_dir / "notify-ledger.json").read_text(
                        encoding="utf-8")
                ).get("entries", {})
                if not all(k.startswith("bug|bug-nh|blocked|")
                           for k in nh_ledger) or len(nh_ledger) != 1:
                    failures.append(
                        f"[{fix_nh}] ledger identity must be "
                        f"bug|bug-nh|blocked|<stat>, got {list(nh_ledger)!r}")
                    nh_ok = False
                out2 = _nh_run()
                if len(nh_sends) != 1:
                    failures.append(
                        f"[{fix_nh}] second probe must dedup (still 1 send), "
                        f"got {len(nh_sends)}")
                    nh_ok = False
                os.environ["LAZY_NOTIFY_DISABLE"] = "1"
                out3 = _nh_run()
                if out3 != out2:
                    failures.append(
                        f"[{fix_nh}] LAZY_NOTIFY_DISABLE probe must be "
                        f"byte-identical to a deduped probe")
                    nh_ok = False
                if len(nh_sends) != 1:
                    failures.append(
                        f"[{fix_nh}] kill switch must not send, "
                        f"got {len(nh_sends)}")
                    nh_ok = False
            finally:
                lazy_core.notifyplane._ntfy_send = nh_real_send
                lazy_core._active_repo_root = nh_prev_repo
                for k, v in nh_saved_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
    except Exception as exc:  # noqa: BLE001
        failures.append(f"[{fix_nh}] unexpected error: {exc!r}")
        nh_ok = False
    print(f"  {'PASS' if nh_ok else 'FAIL'} [{fix_nh}] bug halt + fake sender: one page (bug| identity), dedup on re-probe, kill switch inert")

    # -------------------------------------------------------------------
    # hardening-intervention-records-unmeasurable-or-missing WU-3 (RED):
    # --record-intervention CLI reject + hardening hard-fail. Coupled-pair
    # mirror of lazy-state.py's WU-2 fixtures (grep
    # [record-intervention-hardening-undeclared-rejected] there) — these
    # three fixtures pin the SAME NEW validation/reject step the
    # bug-state.py handler does not yet have (bug-state.py:7713,
    # `if args.record_intervention:`), driven via subprocess so the real
    # CLI handler (guard -> validation -> write) runs, each against its
    # OWN hermetic temp repo_root + temp LAZY_STATE_DIR (immune to any
    # ambient run/cycle marker; mirrors the notify-halt fixture's
    # isolation above).
    # -------------------------------------------------------------------
    def _ri_env(state_dir: Path) -> dict:
        e = {k: v for k, v in os.environ.items()
             if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
        e["LAZY_STATE_DIR"] = str(state_dir)
        return e

    def _ri_run(repo_root: Path, state_dir: Path, extra_args: list):
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--record-intervention", "--repo-root", str(repo_root)]
            + extra_args,
            capture_output=True, text=True, env=_ri_env(state_dir),
        )

    # Sub-fixture 1: --pipeline hardening with NO --target-signal → the
    # undeclared-hardening hard-fail. EXPECT exit 1, no record written,
    # stderr carries the sibling-D2 guidance (naming the explicit
    # --target-signal undeclared escape hatch). Current handler has no
    # such check -> writes the record + exits 0 (RED).
    fix_ri1 = "record-intervention-hardening-undeclared-rejected"
    ri1_ok = True
    with tempfile.TemporaryDirectory(prefix="bug-ri1-repo-") as ri1_repo_td, \
            tempfile.TemporaryDirectory(prefix="bug-ri1-state-") as ri1_state_td:
        ri1_repo = Path(ri1_repo_td)
        ri1_id = "harden-ri1-undeclared-bug"
        ri1_record = ri1_repo / "docs" / "interventions" / f"{ri1_id}.md"
        r = _ri_run(
            ri1_repo, Path(ri1_state_td),
            ["--id", ri1_id, "--pipeline", "hardening"],
        )
        if r.returncode != 1:
            failures.append(
                f"[{fix_ri1}] expected exit 1 (undeclared hardening "
                f"reject), got {r.returncode} (stdout={r.stdout!r} "
                f"stderr={r.stderr!r})"
            )
            ri1_ok = False
        if ri1_record.exists():
            failures.append(
                f"[{fix_ri1}] reject must write NO {ri1_record.name}"
            )
            ri1_ok = False
        if not r.stderr.strip():
            failures.append(
                f"[{fix_ri1}] reject must print guidance to stderr, got "
                f"empty stderr (stdout={r.stdout!r})"
            )
            ri1_ok = False
        elif "undeclared" not in r.stderr:
            failures.append(
                f"[{fix_ri1}] stderr must carry the sibling-D2 guidance "
                f"(naming --target-signal undeclared), got {r.stderr!r}"
            )
            ri1_ok = False
    print(f"  {'PASS' if ri1_ok else 'FAIL'} [{fix_ri1}]")

    # Sub-fixture 2: --pipeline hardening --target-signal undeclared
    # (EXPLICIT escape hatch) -> must NOT trip the hard-fail. EXPECT exit
    # 0, record written with target_signal: undeclared. Non-regression
    # guard for the escape hatch — MAY already be green today (the
    # underlying record_intervention already accepts "undeclared"); still
    # authored so the WU-3 handler edit cannot regress it.
    fix_ri2 = "record-intervention-hardening-undeclared-explicit-ok"
    ri2_ok = True
    with tempfile.TemporaryDirectory(prefix="bug-ri2-repo-") as ri2_repo_td, \
            tempfile.TemporaryDirectory(prefix="bug-ri2-state-") as ri2_state_td:
        ri2_repo = Path(ri2_repo_td)
        ri2_id = "harden-ri2-explicit-undeclared-bug"
        ri2_record = ri2_repo / "docs" / "interventions" / f"{ri2_id}.md"
        r = _ri_run(
            ri2_repo, Path(ri2_state_td),
            ["--id", ri2_id, "--pipeline", "hardening",
             "--target-signal", "undeclared"],
        )
        if r.returncode != 0:
            failures.append(
                f"[{fix_ri2}] explicit --target-signal undeclared must "
                f"exit 0, got {r.returncode} (stdout={r.stdout!r} "
                f"stderr={r.stderr!r})"
            )
            ri2_ok = False
        if not ri2_record.exists():
            failures.append(
                f"[{fix_ri2}] explicit --target-signal undeclared must "
                f"write {ri2_record.name}"
            )
            ri2_ok = False
        else:
            ri2_text = ri2_record.read_text(encoding="utf-8")
            if "target_signal: undeclared" not in ri2_text:
                failures.append(
                    f"[{fix_ri2}] record frontmatter must carry "
                    f"target_signal: undeclared, got {ri2_text!r}"
                )
                ri2_ok = False
    print(f"  {'PASS' if ri2_ok else 'FAIL'} [{fix_ri2}] "
          f"(non-regression guard for the explicit escape hatch)")

    # Sub-fixture 3: an unknown event: type (default --pipeline bug on
    # bug-state.py) -> EXPECT exit 1, stderr naming the valid vocabulary
    # set, no record written. Current handler silently degrades the
    # unknown target to "undeclared" inside record_intervention and
    # writes the record with exit 0 (RED) — WU-3 must reject it at the
    # CLI BEFORE that degrade, identical to the lazy-state.py mirror.
    fix_ri3 = "record-intervention-unknown-event-rejected"
    ri3_ok = True
    with tempfile.TemporaryDirectory(prefix="bug-ri3-repo-") as ri3_repo_td, \
            tempfile.TemporaryDirectory(prefix="bug-ri3-state-") as ri3_state_td:
        ri3_repo = Path(ri3_repo_td)
        ri3_id = "bug-ri3-unknown-event"
        ri3_record = ri3_repo / "docs" / "interventions" / f"{ri3_id}.md"
        r = _ri_run(
            ri3_repo, Path(ri3_state_td),
            ["--id", ri3_id, "--target-signal", "event:route-loop"],
        )
        if r.returncode != 1:
            failures.append(
                f"[{fix_ri3}] expected exit 1 (unknown event: type "
                f"reject), got {r.returncode} (stdout={r.stdout!r} "
                f"stderr={r.stderr!r})"
            )
            ri3_ok = False
        if ri3_record.exists():
            failures.append(
                f"[{fix_ri3}] reject must write NO {ri3_record.name}"
            )
            ri3_ok = False
        if "valid event types:" not in r.stderr:
            failures.append(
                f"[{fix_ri3}] stderr must name the valid vocabulary set "
                f"(the validate_intervention_target_signal message), got "
                f"{r.stderr!r}"
            )
            ri3_ok = False
    print(f"  {'PASS' if ri3_ok else 'FAIL'} [{fix_ri3}]")

    # state-cli-contract-registry Phase 3 (D4-A): coupled-pair mirror of the
    # same did-you-mean wiring confirmation on lazy-state.py.
    dym_name = "did-you-mean-cli-suggestion"
    dym_ok = True
    dym_parser = build_parser()
    if not isinstance(dym_parser, cli_surface.DidYouMeanArgumentParser):
        failures.append(f"[{dym_name}] build_parser() must return a "
                         f"DidYouMeanArgumentParser, got {type(dym_parser)!r}")
        dym_ok = False
    else:
        import io as _dym_io
        dym_buf = _dym_io.StringIO()
        dym_code = None
        with contextlib.redirect_stderr(dym_buf):
            try:
                dym_parser.parse_args(["--fsk"])  # near-miss of --fsck
            except SystemExit as exc:
                dym_code = exc.code
        dym_stderr = dym_buf.getvalue()
        if dym_code != 2:
            failures.append(f"[{dym_name}] expected exit 2, got {dym_code!r}")
            dym_ok = False
        if "unrecognized arguments: --fsk" not in dym_stderr:
            failures.append(f"[{dym_name}] leading error line missing/changed: "
                             f"{dym_stderr!r}")
            dym_ok = False
        if "did you mean: --fsck?" not in dym_stderr:
            failures.append(f"[{dym_name}] missing did-you-mean suggestion: "
                             f"{dym_stderr!r}")
            dym_ok = False
    print(f"  {'PASS' if dym_ok else 'FAIL'} [{dym_name}]")

    # Summary
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        total = len(cases)
        fail_count = sum(
            1 for f in failures
            if not f.endswith(")")  # rough dedup: count fixture-level entries
        )
        print(
            f"\n{len(failures)} assertion(s) failed across {total} fixture(s)."
        )
        return 1

    print("\nAll smoke tests passed.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # state-cli-contract-registry Phase 3 (D4-A): coupled-pair mirror of the
    # same DidYouMeanArgumentParser swap on lazy-state.py.
    parser = cli_surface.DidYouMeanArgumentParser(
        description="Compute the next /lazy-bug state for autonomous bug triage."
    )
    parser.add_argument(
        "--cloud", action="store_true",
        help="Use cloud state-machine variants (no Tauri/MCP/device).",
    )
    parser.add_argument(
        "--real-device", choices=["yes", "no", "auto"], default="auto",
        help=(
            "Whether this host has a real audio output device "
            "(governs device-deferred MCP-assertion handling). "
            "'auto' reads $ALGOBOOTH_REAL_AUDIO_DEVICE (absent → 'no'). "
            "Ignored under --cloud."
        ),
    )
    parser.add_argument(
        "--repo-root", default=os.getcwd(),
        help="Project root (default: $PWD).",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run fixture smoke tests instead of computing state.",
    )
    parser.add_argument(
        "--backfill-receipts", action="store_true",
        help=(
            "One-shot migration: write FIXED.md (provenance: backfilled-unverified) "
            "for every Fixed/archived bug that lacks a receipt."
        ),
    )
    parser.add_argument(
        "--fsck", action="store_true",
        help=(
            "Read-only lint (fixed-bugs-unarchived-fsck): assert (a) no "
            "Status: Fixed dir with a valid receipt sits outside _archive/, "
            "(b) no Status: Fixed dir lacks a valid receipt, (c) no "
            "queue.json row points at a Fixed/archived dir. Exit 0 clean / "
            "1 with named violations. Never mutates."
        ),
    )
    parser.add_argument(
        "--enqueue-adhoc", action="store_true",
        help="Prepend an ad-hoc bug entry to docs/bugs/queue.json.",
    )
    parser.add_argument(
        "--id",
        help="Bug id (required for --enqueue-adhoc).",
    )
    parser.add_argument(
        "--name",
        help="Bug name/title (required for --enqueue-adhoc).",
    )
    # --- code-doc-provenance-linkage: provenance CLI (coupled-pair mirror of
    # lazy-state.py — the implementation is shared lazy_core; only these thin
    # handlers are mirrored). ---
    parser.add_argument(
        "--link-provenance", action="store_true",
        help=("Manual provenance link (the one-writer producer's second "
              "trigger): distill out-of-pipeline work (--commits A..B primary, "
              "--pr <n> sugar) into IMPLEMENTED.md + docs/provenance-index.json "
              "rows (provenance: manual). Requires --id; optional --body-file "
              "(approved prose) and --dry-run. Gated by refuse_if_cycle_active "
              "like --enqueue-adhoc."),
    )
    parser.add_argument(
        "--commits", default=None, metavar="A..B",
        help="Commit range for --link-provenance (primary addressing).",
    )
    parser.add_argument(
        "--pr", type=int, default=None, metavar="N",
        help=("PR-number sugar for --link-provenance — resolved to a range via "
              "`gh pr view`; degrades to a clean refusal naming the --commits "
              "fallback when gh is absent."),
    )
    parser.add_argument(
        "--body-file", default=None, metavar="PATH",
        help=("Operator-approved distillate body prose for --link-provenance "
              "(written through the producer, which still owns frontmatter + "
              "index)."),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=("With --link-provenance: derive + preview the touched-file set "
              "and distillate, write NOTHING."),
    )
    parser.add_argument(
        "--provenance-lookup", default=None, metavar="PATH",
        help=("Pure read: print the provenance-index rows governing PATH "
              "({path, governed_by: [{id, type, doc, decisions, provenance}]}). "
              "Never mutates; missing index → empty governed_by."),
    )
    parser.add_argument(
        "--lint-provenance", action="store_true",
        help=("Pure read, report only (D10): dead index rows (path gone), "
              "high-churn files with no provenance rows, and cross-orphans "
              "(distillate↔index). Never mutates."),
    )
    parser.add_argument(
        "--backfill-provenance", action="store_true",
        help=("One-shot backfill (D7): distill every receipted item "
              "(COMPLETED.md/FIXED.md incl. docs/bugs/_archive/) via "
              "message-grep derivation, provenance: backfilled. Idempotent "
              "(items with IMPLEMENTED.md are skipped)."),
    )
    parser.add_argument(
        "--spec-dir", default=None,
        help="Spec subdirectory under docs/bugs/ (defaults to --id).",
    )
    parser.add_argument(
        "--severity", default=None,
        help="Bug severity, e.g. P0/P1/P2/Low (optional for --enqueue-adhoc).",
    )
    parser.add_argument(
        "--type", dest="adhoc_type", choices=["bug"], default="bug",
        help=("Ad-hoc enqueue target pipeline. Accepts only 'bug' (this is the "
              "bug state script); present so the unified-pipeline-orchestrator "
              "'bug-state.py --enqueue-adhoc --type bug' form parses cleanly. "
              "No behavior change — bug-state always enqueues a bug."),
    )
    parser.add_argument(
        "--deps", default=None,
        help=("queue-dependency-dag: comma-separated hard-dep ids for "
              "--enqueue-adhoc (e.g. --deps a,b). Validated (kebab-case ids; "
              "bug:/feature: prefixes reserved → exit 2); stored on the "
              "prepended entry's `deps` field. Omitted → the entry shape is "
              "byte-identical to before. Coupled-pair mirror of lazy-state.py "
              "--deps."),
    )
    parser.add_argument(
        "--record-decision", action="store_true",
        help=("mechanize-prose-only-orchestrator-contracts (c) — coupled-pair "
              "mirror of lazy-state.py: record a mid-run AskUserQuestion "
              "answer to an on-disk decision record keyed by --sentinel. "
              "Requires --sentinel and --chosen; --summary optional. "
              "Orchestrator-only (refuse_if_cycle_active FIRST)."),
    )
    parser.add_argument(
        "--sentinel", default=None, metavar="PATH",
        help="With --record-decision: the sentinel file path this answer resolves.",
    )
    parser.add_argument(
        "--chosen", default=None, metavar="TEXT",
        help="With --record-decision: the chosen option label(s).",
    )
    parser.add_argument(
        "--summary", default=None, metavar="TEXT",
        help="With --record-decision: optional resolution summary text.",
    )
    parser.add_argument(
        "--sync-deps", dest="sync_deps", action="store_true",
        help=("queue-dependency-dag D5 (orchestrator-only): project the bug "
              "SPEC **Depends on:** block's HARD deps into the "
              "docs/bugs/queue.json entry's `deps` field (requires --id). "
              "Idempotent (noop:true when in sync; empty hard set removes the "
              "key). Gated by refuse_if_cycle_active FIRST (exit 3 for a "
              "cycle subagent, zero side effects). Coupled-pair mirror of "
              "lazy-state.py --sync-deps."),
    )
    parser.add_argument(
        "--reorder-queue", dest="reorder_queue", action="store_true",
        help=("Operator-only / out-of-cycle: move (or remove) an existing "
              "docs/bugs/queue.json entry. Requires --id and --to. Gated by "
              "refuse_if_cycle_active like --enqueue-adhoc (exit 3 for a cycle "
              "subagent). Coupled-pair mirror of lazy-state.py --reorder-queue."),
    )
    parser.add_argument(
        "--to", dest="reorder_to", default=None,
        help=("Reorder destination for --reorder-queue: "
              "tail | head | remove | <integer index>."),
    )
    parser.add_argument(
        "--pin", dest="pin", action="store_true",
        help=("bug-queue-aging-backpressure D2-A: deprioritize a bug via a "
              "reviewable, expiring pin — the sanctioned replacement for "
              "hand-editing docs/bugs/queue.json to `\"severity\": null`. "
              "Requires --id; optional --until <YYYY-MM-DD> (default: expires "
              "after a fixed max pin age) and --reason <text>. Creates the "
              "queue entry (appended) if the bug is not already queued. "
              "Gated by refuse_if_cycle_active like --enqueue-adhoc "
              "(exit 3 for a cycle subagent). Bug-pipeline-only — no "
              "lazy-state.py mirror (feature tier has no analogous "
              "null-severity pin concept)."),
    )
    parser.add_argument(
        "--until", dest="pin_until", default=None, metavar="YYYY-MM-DD",
        help="Pin expiry date for --pin (optional — omit for the default max pin age).",
    )
    parser.add_argument(
        "--reassert-owner", dest="reassert_owner", action="store_true",
        help=("Orchestrator-only / out-of-cycle: re-claim a live foreign-stamped "
              "run marker for the owning session (requires --session-id). Gated "
              "by refuse_if_cycle_active (exit 3 for a cycle subagent). "
              "Coupled-pair mirror of lazy-state.py --reassert-owner "
              "(single-slot-marker-ownership-race; the marker is shared)."),
    )
    # lazy-batch-no-mid-run-budget-or-park-controls: operator-authorized mid-run
    # controls (coupled-pair mirror of lazy-state.py; the marker is shared).
    # Each is orchestrator-only (refuse_if_cycle_active), requires an ACTIVE
    # marker, and REFUSES without --operator-authorized (parallel to the
    # --run-end --reason checkpoint gate). They mutate the active marker in place.
    parser.add_argument(
        "--set-max-cycles", dest="set_max_cycles", type=int, default=None,
        metavar="N",
        help=("Orchestrator-only, --operator-authorized: update the ACTIVE run "
              "marker's max_cycles to N in place (mid-run budget change). Atomic — "
              "no clobber/restart/run-end flush. After this the marker is the "
              "authoritative live budget (header + budget guard agree with N). "
              "Refused without --operator-authorized."),
    )
    parser.add_argument(
        "--set-park", dest="set_park", choices=["on", "off"], default=None,
        help=("Orchestrator-only, --operator-authorized: toggle park mode on the "
              "ACTIVE run marker mid-run. 'on' arms BOTH park_needs_input and "
              "park_blocked (the --park umbrella); 'off' clears both AND "
              "park_provisional. The probe reads the marker each cycle. Refused "
              "without --operator-authorized."),
    )
    parser.add_argument(
        "--set-park-provisional", dest="set_park_provisional",
        choices=["on", "off"], default=None,
        help=("Orchestrator-only, --operator-authorized: toggle "
              "park-provisional-acceptance on the ACTIVE run marker mid-run. 'on' "
              "requires park mode already on (park_provisional requires "
              "park_needs_input, SPEC D1) — else refused. Refused without "
              "--operator-authorized."),
    )
    # no-sanctioned-cli-for-queue-state-mutations (coupled-pair mirror of
    # lazy-state.py): operator-directed in-place bug-queue mutators — the
    # sanctioned replacement for hand-editing bugs/queue.json. Each is
    # refuse_if_cycle_active FIRST + requires --operator-authorized. --set-severity
    # atomically RE-SORTS listed order to match the new merged priority (the
    # load-bearing side effect); --unpin is the inverse of --pin.
    parser.add_argument(
        "--set-severity", dest="set_severity", nargs=2,
        metavar=("ID", "SEVERITY"), default=None,
        help=("Orchestrator-only, --operator-authorized: set bug ID's queue "
              "severity to SEVERITY (P0/P1/P2/Low) and ATOMICALLY re-position it "
              "in listed order to match its new merged priority — one write, never "
              "a stale reorder. Clears any active pin (an explicit severity is the "
              "inverse of a null-pin). refuse_if_cycle_active (exit 3 for a cycle "
              "subagent). The promote/demote sibling of --pin."),
    )
    parser.add_argument(
        "--unpin", dest="unpin", metavar="ID", default=None,
        help=("Orchestrator-only, --operator-authorized: un-pin bug ID (the inverse "
              "of --pin) — clear pinned_at/pinned_until/pin_reason, restore severity "
              "from the SPEC's **Severity:** line, and re-position in listed order. "
              "A not-pinned bug is a byte-stable no-op. refuse_if_cycle_active FIRST."),
    )
    parser.add_argument(
        "--add-deps", dest="add_deps", metavar="ID", default=None,
        help=("Orchestrator-only, --operator-authorized: add the --deps id list as "
              "hard queue dependencies on bug ID (post-hoc, arbitrary — the non-SPEC "
              "sibling of --sync-deps). Deduped; post-mutation cycle-guarded. "
              "refuse_if_cycle_active FIRST. Coupled-pair mirror of lazy-state.py."),
    )
    parser.add_argument(
        "--remove-deps", dest="remove_deps", metavar="ID", default=None,
        help=("Orchestrator-only, --operator-authorized: remove the --deps id list "
              "from bug ID's hard queue dependencies (empty result drops the deps "
              "key). refuse_if_cycle_active FIRST. Coupled-pair mirror of "
              "lazy-state.py."),
    )
    parser.add_argument(
        "--record-intervention", dest="record_intervention",
        action="store_true",
        help=("intervention-efficacy-tracking: write the intervention record "
              "(hypothesis ledger capture) to docs/interventions/<id>.md. "
              "Requires --id. Optional: --spec-dir (item dir carrying the "
              "## Intervention Hypothesis block), --pipeline, "
              "--shipped-commit/--shipped-date (D9 backfill — stamps "
              "provenance: backfilled), and the hypothesis-override flags. "
              "Orchestrator-only (refuse_if_cycle_active). Idempotent. "
              "Coupled-pair mirror of lazy-state.py --record-intervention "
              "(the capture helper is shared lazy_core)."),
    )
    parser.add_argument(
        "--pipeline", dest="intervention_pipeline",
        choices=["feature", "bug", "hardening"], default="bug",
        help=("Pipeline stamped on a --record-intervention record (default: "
              "bug on bug-state.py; hardening for /harden-harness rounds)."),
    )
    parser.add_argument(
        "--shipped-commit", default=None,
        help=("--record-intervention D9 backfill: override the recorded "
              "shipped_commit (default: current HEAD). Stamps "
              "provenance: backfilled."),
    )
    parser.add_argument(
        "--shipped-date", default=None,
        help=("--record-intervention D9 backfill: override the recorded "
              "shipped_date (YYYY-MM-DD). Stamps provenance: backfilled."),
    )
    parser.add_argument(
        "--target-signal", default=None,
        help=("--record-intervention hypothesis override: "
              "kpi:<system>.<kpi-id> or event:<ledger-event-type>."),
    )
    parser.add_argument(
        "--expected-direction", default=None, choices=["decrease", "increase"],
        help="--record-intervention hypothesis override.",
    )
    parser.add_argument(
        "--signal-independence", default=None,
        help=("--record-intervention hypothesis override: independent | "
              "self-emitted | mixed (+ optional justification tail)."),
    )
    parser.add_argument(
        "--review-after-runs", type=int, default=None,
        help=("--record-intervention hypothesis override: post-ship run-count "
              "window before each review (default: 20)."),
    )
    parser.add_argument(
        "--bug-id", default=None,
        help="Scope this run to a single bug by id. Absent → default behavior.",
    )
    parser.add_argument(
        "--park-needs-input", action="store_true",
        help=(
            "OPT-IN park mode: when active, a bug carrying an unresolved "
            "NEEDS_INPUT.md is SKIPPED (parked) rather than halting the queue. "
            "The parked item is reported in the 'parked[]' output array and "
            "re-enters automatically once NEEDS_INPUT.md is resolved/renamed. "
            "Without this flag, output is byte-identical to the default behavior "
            "('parked' key is entirely absent and the needs-input halt fires as today)."
        ),
    )
    parser.add_argument(
        "--park-blocked", action="store_true",
        help=(
            "OPT-IN park mode (companion to --park-needs-input): when active, a "
            "bug carrying a bug-local BLOCKED.md is SKIPPED (parked) rather than "
            "halting the queue with terminal_reason='blocked'. The parked item is "
            "reported in the 'parked[]' array and re-enters once the block is "
            "resolved/renamed. Global/environment terminals still halt. When every "
            "remaining bug is parked, the honest 'queue-exhausted-all-parked' "
            "terminal fires instead of 'all-bugs-fixed'. Without this flag, output "
            "is byte-identical to the default behavior (BLOCKED still halts)."
        ),
    )
    parser.add_argument(
        "--park-provisional", action="store_true",
        help=(
            "OPT-IN modifier of --park-needs-input (park-provisional-acceptance, "
            "SPEC D1 — supplying it alone is a hard error): a parked-eligible "
            "NEEDS_INPUT.md passing the fail-closed provisional predicate "
            "(divergence two-key both in {isolated, contained}; every decision "
            "carrying a **Recommendation:**; never two-key-mechanical or "
            "completion-integrity-gate sentinels) routes __provisional_accept__ "
            "instead of parking. An unratified NEEDS_INPUT_PROVISIONAL.md blocks "
            "__mark_fixed__ mechanically and halts non-park probes on "
            "'needs-ratification'. Coupled-pair mirror of lazy-state.py."
        ),
    )
    parser.add_argument(
        "--provisionalize-sentinel", default=None, metavar="PATH",
        help=(
            "Provisionally accept the NEEDS_INPUT.md at PATH on its "
            "recommendations (park-provisional-acceptance SPEC D2): re-validate "
            "the fail-closed eligibility predicate, append a ## Resolution block "
            "(resolved_by: auto-provisional, decision_commit: HEAD), and rename "
            "to NEEDS_INPUT_PROVISIONAL.md (git-mv-aware). Refusals exit 1 with "
            "ZERO writes. Coupled-pair mirror of lazy-state.py."
        ),
    )
    parser.add_argument(
        "--per-feature-cycle-cap", type=int, default=None, metavar="N",
        help=(
            "PARITY-ONLY (feature-budget-guard-and-skip-ahead Phase 2): mirrors "
            "lazy-state.py's --per-feature-cycle-cap so the documented unified flag "
            "surface parses on both scripts (audited by lazy_parity_audit.py). The "
            "per-feature budget guard is a FEATURE-pipeline mechanic and the bug "
            "pipeline does not trip in v1, so this flag is accepted and ignored here "
            "(benign no-op; output byte-identical). Matches the --type bug precedent."
        ),
    )
    parser.add_argument(
        "--strict-research-halt", action="store_true",
        help=(
            "PARITY-ONLY (feature-budget-guard-and-skip-ahead Phase 3): mirrors "
            "lazy-state.py's --strict-research-halt so the documented unified flag "
            "surface parses on both scripts (audited by lazy_parity_audit.py). "
            "Dependency-aware skip-ahead past a gated head is a FEATURE-pipeline "
            "mechanic — the bug pipeline has NO research gate, so this flag is "
            "accepted and ignored here (benign no-op; output byte-identical)."
        ),
    )
    parser.add_argument(
        "--verify-ledger", default=None, metavar="SPEC_PATH",
        help=(
            "Scripted completion-ledger guard (replaces the prose guard blocks "
            "in the lazy-bug skills). Verifies: (1) clean working tree, "
            "(2) HEAD == @{u}, (3) all implementation plans are status: Complete, "
            "(4) no real (non-verification) unchecked deliverables. "
            "With --plan PLAN, checks 3+4 narrow to that plan part's scope "
            "(plan_complete = the plan's own status: Complete; deliverables_done = "
            "no unchecked non-verification `- [ ] WU-N` rows in the PLAN PART itself "
            "— the ISSUE-6 per-WU checkboxes are the machine source of truth; a "
            "legacy plan with no per-WU checkboxes falls back to PHASES-phase-level "
            "and reports deliverables_source). Without --plan, check 4 reads the "
            "whole feature's PHASES.md. "
            "Emits a JSON verdict (incl. diagnostic deliverables_source) and exits "
            "0 on pass, 1 on first failing check."
        ),
    )
    parser.add_argument(
        "--apply-pseudo", nargs=2, default=None, metavar=("NAME", "SPEC_PATH"),
        help="Single-author the deterministic sentinel/receipt write for a lazy pseudo-skill.",
    )
    parser.add_argument(
        "--plan", default=None,
        help="Plan-file path for __flip_plan_complete_*__ pseudo-skills AND "
             "for plan-scoped --verify-ledger (Phase 9 WU-3).",
    )
    parser.add_argument(
        "--apply-date", default=None,
        help="Override date (YYYY-MM-DD) for --apply-pseudo writes.",
    )
    parser.add_argument(
        "--reason", default=None,
        help="Reason string for __write_deferred_non_cloud__.",
    )
    parser.add_argument(
        "--deferred-step", type=int, default=None,
        help="deferred_step for __write_deferred_non_cloud__.",
    )
    parser.add_argument(
        "--neutralize-sentinel", default=None, metavar="PATH",
        help="Rename a resolved sentinel to the canonical *_RESOLVED_<date> form (collision-safe).",
    )
    parser.add_argument(
        "--repeat-count", action="store_true",
        help="Persist the probe signature and emit a 'repeat_count' field "
             "(consecutive identical-probe count) for mechanical loop detection. "
             "ADVANCES the persisted streak — reserve for the single dispatch-bound "
             "probe per cycle. Without this flag, output is byte-identical to the "
             "default and no state file is written.",
    )
    parser.add_argument(
        "--repeat-count-peek", action="store_true",
        help="Like --repeat-count but PEEK only: compute and emit the would-be "
             "'repeat_count' WITHOUT advancing the persisted streak (no state-file "
             "write). Use for diagnostic/inspection probes so they do not inflate "
             "the streak. Mutually exclusive with --repeat-count.",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="Fold git-guard results + a pre-formatted cycle-header line into the "
             "probe JSON (orchestrator happy-path payload). Without this flag, output "
             "is byte-identical to the default.",
    )
    parser.add_argument(
        "--archive-fixed", metavar="SPEC_PATH", default=None,
        help="Archive a Fixed bug directory to docs/bugs/_archive/: SPEC.md "
             "evidence header lines, staged-deletion-coherent git mv (with "
             "Windows lock retry + per-file fallback), tracked-only inbound "
             "reference repoint, queue.json trim, and the archive commit. "
             "Run AFTER `--apply-pseudo __mark_fixed__` (the receipt gate). "
             "Prints a JSON result; exit 1 on refusal.",
    )
    parser.add_argument(
        "--emit-prompt", action="store_true",
        help="Enrich the probe JSON with cycle_prompt + cycle_model "
             "(script-assembled cycle dispatch prompt; composes with "
             "--repeat-count for loop detection).",
    )
    parser.add_argument(
        "--forward-cycles", type=int, default=None,
        help="Orchestrator forward-cycle count (for --probe cycle header).",
    )
    parser.add_argument(
        "--meta-cycles", type=int, default=None,
        help="Orchestrator meta-cycle count (for --probe cycle header).",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=None,
        help="Orchestrator max-cycles ceiling (for --probe cycle header).",
    )
    # Phase 1 run-lifecycle flags: --run-start writes the marker (pipeline=bug
    # for this script), --run-end deletes it.  Both print a JSON result and exit
    # immediately, like other action flags.  All new Phase 1 behavior (registry
    # writes, counter advances) is unreachable without first calling --run-start.
    parser.add_argument(
        "--run-start", action="store_true",
        help=(
            "Write the run marker to the state dir (pipeline=bug), "
            "gating registry and counter side-effects for this run. "
            "Uses --cloud, --repo-root, and --max-cycles when present. "
            "Prints the marker JSON and exits."
        ),
    )
    parser.add_argument(
        "--run-end", action="store_true",
        help=(
            "Delete the run marker from the state dir. "
            "Call on every terminal run path to avoid haunting the "
            "next session. Prints {\"run_marker_deleted\": true|false} "
            "and exits."
        ),
    )
    # lazy-cycle-containment C1 (Phase 2): cycle-subagent marker bracket —
    # coupled-pair mirror of lazy-state.py (shared lazy_core backing). Bug
    # pipeline scopes by --bug-id, so --cycle-begin uses --bug-id for feature_id.
    parser.add_argument(
        "--cycle-begin", action="store_true",
        help=(
            "Write the cycle-subagent marker (lazy-cycle-active.json) before an "
            "Agent dispatch. Requires --bug-id and --nonce; optional --kind "
            "real|meta (default real). Self-healing: overwrites a stale marker "
            "and logs. Prints the marker JSON and exits."
        ),
    )
    parser.add_argument(
        "--cycle-end", action="store_true",
        help=(
            "Clear the cycle-subagent marker after an Agent returns. Idempotent. "
            "Prints {\"cycle_marker_cleared\": true|false} and exits."
        ),
    )
    parser.add_argument(
        "--record-resolution-signal", action="store_true",
        help=(
            "loop-detected-false-positives (coupled-pair mirror of lazy-state.py): "
            "persist the one-shot resolution-aware reset signal on the run marker "
            "(last_resolution_step_key=[bug_id, current_step]) so the NEXT same-step "
            "probe RESETS step_repeat_count to 1 — a needs-input RESOLUTION is itself "
            "a dispatch (consumes a nonce), defeating the F2 debounce. Requires "
            "--bug-id and --current-step. Marker-gated. Prints marker JSON and exits."
        ),
    )
    parser.add_argument(
        "--current-step", default=None,
        help=(
            "Step name for --record-resolution-signal (the step the needs-input "
            "resolution was applied at; bind to the resolved bug's probe "
            "current_step VERBATIM)."
        ),
    )
    parser.add_argument(
        "--nonce", default=None,
        help="Dispatch nonce (hex) for --cycle-begin.",
    )
    parser.add_argument(
        "--kind", choices=["real", "meta"], default="real",
        help="Dispatch kind for --cycle-begin (real|meta; default real).",
    )
    parser.add_argument(
        "--sub-skill", default=None,
        help=(
            "Dispatched sub_skill name for --cycle-begin (coupled-pair mirror of "
            "lazy-state.py). Persisted into the cycle marker so --cycle-end's "
            "process-friction detector selects the correct per-sub_skill commit "
            "budget instead of the conservative default. Optional."
        ),
    )
    parser.add_argument(
        "--sub-skill-args", default=None,
        help=(
            "Dispatched sub_skill_args for --cycle-begin (coupled-pair mirror of "
            "lazy-state.py). For an execute-plan cycle this is the PLAN PART path; "
            "--cycle-end reads its phase count to scale the execute-plan commit "
            "budget (hardening Round 20). Optional — omitting it degrades to the "
            "fixed per-sub_skill budget."
        ),
    )
    # Phase 3: --emit-dispatch <class> — coupled-pair mirror of lazy-state.py.
    # Pipeline is always "bug" for bug-state.py (the bug pipeline script).
    parser.add_argument(
        "--emit-dispatch", metavar="CLASS",
        help=(
            "Emit a fully-bound dispatch prompt for the named dispatch class "
            "(apply-resolution, input-audit, investigation, recovery, "
            "coherence-recovery, needs-runtime-redispatch, hardening). Outputs JSON and "
            "exits. Marker present → registers the emission. Marker absent → "
            "peek only (no registry write). Use --context KEY=VALUE "
            "(repeatable) to supply class-specific token bindings."
        ),
    )
    parser.add_argument(
        "--context", action="append", metavar="KEY=VALUE",
        default=[],
        help=(
            "Supply a context key=value for --emit-dispatch. "
            "Repeatable. Split on the first '=' only."
        ),
    )
    # Phase 7 WU-7.1 / WU-7.4: --run-end behavior modifiers (mirror lazy-state.py).
    #   --ack-unhardened : proceed with --run-end even when unacked guard denials
    #                      remain in the deny ledger (override recorded in output).
    #   --next-route TEXT: the probed next route, REQUIRED for a checkpoint
    #                      run-end; written into lazy-run-checkpoint.json.
    # The run-end reason ({terminal,checkpoint}) reuses the existing free-text
    # --reason flag (default terminal) — see the run-end handler.
    parser.add_argument(
        "--ack-unhardened", action="store_true",
        help=(
            "With --run-end: proceed even when unacked guard denials remain in "
            "the deny ledger. The override is recorded in the run-end output "
            "for retro grading."
        ),
    )
    # meta-dispatch-not-by-reference-and-ack-overpriced Fix Scope §1+§2
    # (coupled-pair mirror of lazy-state.py): a cheap per-entry ack CLI (with
    # same-cause dedup) so a duplicate/no-fix/already-fixed deny-ledger entry
    # does not cost a full hardening dispatch. Orchestrator-only.
    parser.add_argument(
        "--ack-deny", default=None, metavar="SELECTOR",
        help=(
            "Cheaply retire unacked deny-ledger entry/entries WITHOUT a full "
            "hardening dispatch. SELECTOR is 'oldest' (FIFO) or a "
            "denied_sha12 value/prefix. Requires --resolution. Every OTHER "
            "unacked entry sharing the same cause (identical denied_sha12, or "
            "identical kind+reason_head) is deduped into the same ack. "
            "Orchestrator-only."
        ),
    )
    parser.add_argument(
        "--resolution", default=None, metavar="TEXT",
        help="Audit note for --ack-deny (required, non-empty).",
    )
    # efficacy-future-check-unenforced-orchestrator-prose (D1, coupled-pair
    # mirror of lazy-state.py): the operator override for the efficacy-flush gate.
    parser.add_argument(
        "--efficacy-skip-authorized", action="store_true",
        help=(
            "With --run-end: proceed even when the end-of-run "
            "efficacy/canary/incident flush did not run this run (no "
            "efficacy-flush breadcrumb). The override is recorded in the run-end "
            "output for retro grading."
        ),
    )
    parser.add_argument(
        "--next-route", default=None, metavar="TEXT",
        help=(
            "With --run-end --reason checkpoint: the probed next route to resume "
            "with (written into the checkpoint file and echoed by --run-start)."
        ),
    )
    # Phase 7 (lazy-validation-readiness) stop-authorization gates — coupled-pair
    # mirror of lazy-state.py.  See lazy-state.py for full rationale.
    # Motivating incident 2026-06-14: attended /lazy-batch 50 stopped at 5/50.
    parser.add_argument(
        "--unattended", action="store_true",
        help=(
            "With --run-start: write attended=False into the run marker "
            "(scheduled/cron/unattended invocation). Interactive /lazy-bug-batch "
            "does NOT pass this flag — the default attended=True enables the "
            "stop-authorization gate that prevents unilateral checkpoint stops."
        ),
    )
    parser.add_argument(
        "--operator-authorized", action="store_true",
        help=(
            "With --run-end: bypass the stop-authorization gate (checkpoint on "
            "attended run, or non-sanctioned terminal reason). Pass ONLY after "
            "the operator explicitly confirms via the budget-and-queue-guard "
            "AskUserQuestion. Independent of --ack-unhardened (hardening-debt)."
        ),
    )
    parser.add_argument(
        "--terminal-reason", default=None, metavar="REASON",
        help=(
            "With --run-end --reason terminal: the explicit stop reason token "
            "(e.g. 'all-bugs-fixed', 'max-cycles'). Must be in "
            "lazy_core.SANCTIONED_STOP_TERMINAL or --operator-authorized must "
            "be passed. Omitting adds a deprecation note to the output."
        ),
    )
    # cycle-subagent-fabricates-policy-or-stray-branch Phase 2 (parity with
    # lazy-state.py): --marker-work-branch read-only query + the --session-id it
    # honors. The run marker is shared between the feature and bug pipelines, so
    # the stray-branch write-time hook can query either script.
    parser.add_argument(
        "--marker-work-branch", action="store_true",
        help=(
            "Read-only: print the run marker's work_branch and exit 0 if a live "
            "marker carrying a branch is present for the current repo "
            "(--repo-root, default cwd); exit 1 if absent/stale/legacy-no-branch. "
            "Never creates state. Used by the stray-branch write-time hook."
        ),
    )
    parser.add_argument(
        "--session-id", default=None,
        help=(
            "Optional session id for --marker-work-branch (and other read paths): "
            "a marker bound to a DIFFERENT session id reads as absent "
            "(non-destructive session isolation)."
        ),
    )
    # cycle-prompt-environment-dialect Phase 1 (parity with lazy-state.py): a
    # NEVER-THROWS read-only presence query. The run marker is SHARED with the
    # feature pipeline (same per-repo keyed state dir), so either script can
    # answer this probe.
    parser.add_argument(
        "--marker-status", action="store_true",
        help=(
            "Read-only, never-throws: print {\"present\": bool} for the "
            "current repo's run marker (--repo-root, default cwd). Always "
            "exits 0 — absent/corrupt/no-state-dir all resolve to "
            "present: false."
        ),
    )
    # parallel-worktree-batch-execution (D2-A, coupled-pair mirror of
    # lazy-state.py — the marker is SHARED): with --run-start at a worktree
    # root, stamp the lane marker with the PARENT run's identity. Serial runs
    # omit the flag → parent_run: null (byte-identical shape).
    parser.add_argument(
        "--parent-run", default=None, metavar="JSON",
        help=(
            "With --run-start: JSON object "
            "'{\"repo_root\": str, \"started_at\": str}' identifying the PARENT "
            "run whose coordinator armed this lane marker (parallel-worktree "
            "lanes). Malformed → exit 2, zero side effects. Omit for serial runs."
        ),
    )
    cli_surface.add_dump_cli_surface_flag(parser)
    cli_surface.add_ops_query_flags(parser)
    return parser


def main() -> int:
    # Eager-import the lazy_core package (PEP 562 facade) so a broken submodule
    # fails at process start, not at first attribute access (SPEC D4-A).
    lazy_core.load_all()

    parser = build_parser()
    args = parser.parse_args()

    _dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "bug-state.py")
    if _dump is not None:
        return _dump

    # no-sanctioned-cli-for-queue-state-mutations (parity with lazy-state.py):
    # op-discoverability search — read-only, handled before any side effect.
    _ops = cli_surface.maybe_handle_ops_query(args, parser, "bug-state.py")
    if _ops is not None:
        return _ops

    # multi-repo-concurrent-runs: bind the active repo ONCE so claude_state_dir()
    # scopes all run-scoped state to this repo's subdir (parity with lazy-state.py).
    lazy_core.set_active_repo_root(args.repo_root)

    # --repeat-count (advances the streak) and --repeat-count-peek (reads it
    # without advancing) are mutually exclusive — a single probe cannot both
    # advance and peek the persisted streak.
    if args.repeat_count and args.repeat_count_peek:
        _die("--repeat-count and --repeat-count-peek are mutually exclusive")

    # park-provisional-acceptance (SPEC D1, parity with lazy-state.py):
    # --park-provisional is a strict modifier of --park-needs-input.
    if args.park_provisional and not args.park_needs_input:
        _die("--park-provisional requires --park-needs-input")

    # cycle-subagent-fabricates-policy-or-stray-branch Phase 2 (parity with
    # lazy-state.py): --marker-work-branch — a read-only query that prints the
    # run marker's work_branch. The marker is SHARED with the feature pipeline
    # (both resolve the same per-repo keyed state dir), so the bug pipeline's
    # write-time stray-branch hook can query EITHER script. set_active_repo_root
    # ran above; marker_work_branch() routes through read_run_marker →
    # claude_state_dir(create=False) (read-only, never creates state). Exit 0 +
    # print the branch when a live marker carries one; exit 1 otherwise.
    if args.marker_work_branch:
        branch = lazy_core.marker_work_branch(session_id=args.session_id)
        if branch:
            sys.stdout.write(branch + "\n")
            return 0
        return 1

    # cycle-prompt-environment-dialect Phase 1 (parity with lazy-state.py):
    # --marker-status — a NEVER-THROWS mirror of --marker-present (which
    # lazy-state.py-only exposes as an exit-code-only probe). Always exits 0.
    if args.marker_status:
        try:
            marker = lazy_core.read_run_marker(session_id=args.session_id)
            present = marker is not None
        except Exception:  # noqa: BLE001 — never-throws contract
            present = False
        sys.stdout.write(json.dumps({"present": present}) + "\n")
        return 0

    # Phase 1 run-lifecycle dispatch: --run-start / --run-end exit immediately
    # like all other action flags so they compose cleanly with orchestrator
    # scripting (e.g. ``python bug-state.py --run-start --cloud --max-cycles 20``).
    # lazy-cycle-containment C1 (Phase 2): cycle-marker bracket dispatch
    # (coupled-pair mirror of lazy-state.py).
    # cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE, coupled-pair
    # mirror): a SUBAGENT must not arm/clear the containment marker. Guard at the
    # ENTRY of both handlers via the dedicated marker-mutation guard (keys on the
    # POSITIVE LAZY_ORCHESTRATOR signal). The orchestrator exports
    # LAZY_ORCHESTRATOR=1 (Phase 1), so its bracket is unaffected.
    if args.record_resolution_signal:
        # loop-detected-false-positives-from-probe-and-reboot-churn (symptom 3,
        # coupled-pair mirror of lazy-state.py): persist the one-shot resolution
        # signal keyed on the bug's step signature so the next same-step probe
        # resets step_repeat_count. Marker-gated inside the helper.
        if not args.bug_id or not args.current_step:
            _die("--record-resolution-signal requires --bug-id and --current-step")
        marker = lazy_core.record_resolution_signal(
            {"feature_id": args.bug_id, "current_step": args.current_step}
        )
        sys.stdout.write(json.dumps(marker, indent=2) + "\n")
        return 0

    if args.cycle_begin:
        lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-begin")
        if not args.bug_id or not args.nonce:
            _die("--cycle-begin requires --bug-id and --nonce")
        # adhoc-cycle-begin-real-requires-sub-skill: coupled-pair mirror of
        # lazy-state.py — a --kind real dispatch that omits --sub-skill writes
        # a marker with sub_skill=None, making the --cycle-end commit budget
        # indeterminate. Require it up front, before any marker mutation.
        # --kind meta remains exempt (see lazy_core.py:10962).
        if args.kind == "real" and not (args.sub_skill or "").strip():
            _die("--cycle-begin --kind real requires --sub-skill")
        # hardening-blind-to-process-friction Phase 2 (D1) — coupled-pair mirror
        # of lazy-state.py: snapshot the live run identity + current HEAD sha into
        # the cycle marker so --cycle-end can detect a torn bracket / unexpected
        # commits. Best-effort: missing run marker / non-git tree → None.
        run_marker = lazy_core.read_run_marker()
        run_started_at = (run_marker or {}).get("started_at")
        begin_head_sha = lazy_core.head_sha_snapshot(Path(args.repo_root))
        # long-build-and-runtime-ownership Phase 4 (M5 Detect / LD4) — coupled-pair
        # mirror of lazy-state.py: BEFORE the cycle marker write, reconcile a
        # torn-build git-consistency delta (pre-boot .git/index.lock older than the
        # run boot stamp ⇒ remove + git clean the staging dir). Composes with the
        # --cycle-end friction detector (no commits, no run-marker touch). Best-
        # effort + FAIL-OPEN so the marker write always proceeds.
        boot_stamp = None
        if run_started_at:
            try:
                _boot_dt = datetime.strptime(
                    run_started_at, "%Y-%m-%dT%H:%M:%SZ"
                )
                boot_stamp = (
                    _boot_dt - datetime(1970, 1, 1)
                ).total_seconds()
            except (ValueError, TypeError):
                boot_stamp = None
        reconciliation = None
        try:
            staging_dir = str(Path(args.repo_root) / "target" / "release_staging")
            reconciliation = lazy_core.reconcile_cycle_begin_git_consistency(
                Path(args.repo_root), boot_stamp=boot_stamp, staging_dir=staging_dir,
            )
        except Exception:  # noqa: BLE001  (defense-in-depth; helper is fail-open)
            reconciliation = None
        marker = lazy_core.write_cycle_marker(
            feature_id=args.bug_id, nonce=args.nonce, kind=args.kind,
            run_started_at=run_started_at, begin_head_sha=begin_head_sha,
            sub_skill=args.sub_skill, sub_skill_args=args.sub_skill_args,
        )
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: cycle-bracket emission (marker-gated + fail-open
        # inside the emitter; adds NO output keys). Bug pipeline passes --bug-id.
        lazy_core.append_telemetry_event(
            "cycle-begin", item_id=args.bug_id,
            data={"kind": args.kind, "sub_skill": args.sub_skill},
        )
        out: dict = dict(marker)
        if reconciliation is not None and reconciliation.get("reconciled"):
            out["git_consistency_reconciliation"] = reconciliation
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.cycle_end:
        # cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE, coupled-pair
        # mirror): refuse a subagent's marker clear BEFORE the friction check /
        # clear_cycle_marker run (zero side effects). The orchestrator
        # (LAZY_ORCHESTRATOR=1) is allowed to clear its own bracket.
        lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-end")
        # hardening-blind-to-process-friction Phase 2 (D1) — coupled-pair mirror:
        # check the two process-friction signals BEFORE clearing the marker; on a
        # hit append a kind: process-friction entry to the deny ledger.
        # harness-telemetry-ledger Phase 2 — coupled-pair mirror: capture the
        # cycle identity BEFORE the clear (read-only) for the cycle-end event.
        _tl_cycle = lazy_core.read_cycle_marker()
        # mechanize-prose-only-orchestrator-contracts (b) / D2-A — coupled-pair
        # mirror of lazy-state.py: arm the post-cycle input-audit obligation
        # when the ending cycle was spec-bug or plan-bug.
        if _tl_cycle is not None:
            lazy_core.record_audit_obligation(
                item_id=_tl_cycle.get("feature_id"),
                cycle_kind=_tl_cycle.get("sub_skill"),
            )
        friction = lazy_core.cycle_end_friction_check(repo_root=Path(args.repo_root))
        # code-doc-provenance-linkage Phase 1 (D4-A) — coupled-pair mirror:
        # record this cycle's commit bracket (marker begin_head_sha → current
        # HEAD) into the state-dir bracket ledger BEFORE clearing the marker.
        # Fail-open — a degraded snapshot / write failure returns None and
        # never blocks the clear.
        bracket = lazy_core.record_cycle_commit_bracket(
            repo_root=Path(args.repo_root)
        )
        cleared = lazy_core.clear_cycle_marker()
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py (marker-gated + fail-open; adds NO output keys).
        lazy_core.append_telemetry_event(
            "cycle-end", item_id=(_tl_cycle or {}).get("feature_id"),
            data={"cleared": cleared,
                  "process_friction": (friction or {}).get("reason")},
        )
        out: dict = {"cycle_marker_cleared": cleared}
        if friction is not None:
            out["process_friction"] = friction
        if bracket is not None:
            out["commit_bracket"] = bracket
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.run_start:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch (coupled-pair mirror). Zero side effects on refusal.
        lazy_core.refuse_if_cycle_active("--run-start")
        # D-B (hardening-blind-to-process-friction, 2026-06-16): refuse to CLOBBER
        # a live run marker owned by a DIFFERENT pipeline (coupled-pair mirror of
        # lazy-state.py). A nested feature --run-start must NOT overwrite this
        # active bug run marker. Same-pipeline resume is allowed. Zero side effects.
        lazy_core.refuse_run_start_clobber("bug")
        # Write the marker for the bug pipeline.  cloud, repo_root, and
        # max_cycles are taken from the matching existing flags so no new flags
        # are needed for those values.
        # Phase 7 / lazy-validation-readiness (coupled-pair mirror of lazy-state.py):
        # pass attended=not args.unattended so interactive /lazy-bug-batch runs
        # default to attended=True, enabling the stop-authorization gate.
        # single-slot-marker-ownership-race-disarms-owning-run Phase 1 (coupled-pair
        # mirror of lazy-state.py): thread the orchestrator's owning session_id so
        # the bug-pipeline marker is born OWNER-BOUND, closing the bind-pending
        # window at its source. The marker is SHARED between pipelines, so this
        # threading must match lazy-state.py exactly. Absent --session-id →
        # session_id=None as before (legacy path, _bind_marker_on_allow fallback).
        # parallel-worktree-batch-execution (D2-A, coupled-pair mirror of
        # lazy-state.py): validate + thread the optional sanctioned-lane
        # identity stamp. Malformed → _die exit 2 BEFORE any marker write.
        parent_run = lazy_core.parse_parent_run_arg(args.parent_run)
        marker = lazy_core.write_run_marker(
            pipeline="bug",
            cloud=args.cloud,
            repo_root=args.repo_root,
            max_cycles=args.max_cycles,
            session_id=args.session_id,
            attended=not args.unattended,
            parent_run=parent_run,
            # lazy-batch-no-mid-run-budget-or-park-controls (coupled-pair mirror):
            # SEED park mode into the marker from the invocation --park flags so
            # the probe reads it each cycle and --set-park can toggle it in place.
            park_needs_input=args.park_needs_input,
            park_blocked=args.park_blocked,
            park_provisional=args.park_provisional,
        )
        out: dict = dict(marker)
        # Phase 7 WU-7.4: consume any checkpoint left by a prior checkpoint
        # run-end and echo it as resume context (consume-once — deleted on read).
        checkpoint = lazy_core.consume_run_checkpoint()
        if checkpoint is not None:
            out["resumed_from_checkpoint"] = checkpoint
            # ROOT-CAUSE FIX (mid-run counter reset, 2026-06-14) — coupled-pair
            # mirror of lazy-state.py. write_run_marker above zeroed the counters;
            # a checkpoint resume is the SAME run continuing, so its monotonic
            # forward/meta counts must carry forward (HARD CONSTRAINT 8 — never
            # reset within a run). Restore them and echo the continued totals.
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            if restored is not None:
                out["forward_cycles"] = restored.get("forward_cycles")
                out["meta_cycles"] = restored.get("meta_cycles")
                out["last_advance_consume_count"] = restored.get(
                    "last_advance_consume_count"
                )
            # checkpoint-resume-false-loop-flips-complex-part-to-sonnet (2026-07-12)
            # — coupled-pair mirror of lazy-state.py. Re-baseline the loop-debounce
            # consume_count baseline against the freshly-recreated registry so the
            # first re-probe of the re-probed next_route HOLDS instead of inflating
            # to a false LOOP DETECTED. Shared helper; no-op + fail-open otherwise.
            lazy_core.rebaseline_loop_signature_after_registry_reset(
                Path(lazy_core.active_repo_root()), pipeline="bug"
            )
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: run-bracket emission AFTER write_run_marker (the fresh
        # marker supplies the run identity; marker-gated + fail-open).
        lazy_core.append_telemetry_event(
            "run-start",
            data={"cloud": args.cloud, "max_cycles": args.max_cycles,
                  "resumed_from_checkpoint": checkpoint is not None},
        )
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.run_end:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch (coupled-pair mirror). Guard fires before any deletion.
        lazy_core.refuse_if_cycle_active("--run-end")
        # Phase 7: the run-end reason reuses the existing free-text --reason flag
        # (default "terminal"; "checkpoint" triggers the WU-7.4 checkpoint write).
        reason = args.reason or "terminal"
        if reason not in ("terminal", "checkpoint"):
            _die("--run-end --reason must be 'terminal' or 'checkpoint'")

        # WU-7.1: refuse to retire the marker while unacked guard denials remain,
        # unless --ack-unhardened was passed (the override is recorded for retros).
        # INDEPENDENT of the Phase 7 stop-authorization gate below.
        pending = lazy_core.pending_hardening()
        override_note = None
        if pending > 0:
            if not args.ack_unhardened:
                sys.stdout.write(json.dumps({
                    "run_marker_deleted": False,
                    "refused": (
                        f"{pending} unacked guard denial(s) remain in the deny "
                        f"ledger. Each denial owes a hardening round: re-run "
                        f"`--emit-dispatch hardening` once per pending denial "
                        f"(FIFO-acked), or pass --ack-unhardened to override. "
                        f"The marker was NOT deleted."
                    ),
                    "pending_hardening": pending,
                }, indent=2) + "\n")
                # run-end-gate-refusals-no-telemetry-event (coupled-pair mirror
                # of lazy-state.py): observability-only gate-refusal emission
                # (marker-gated, fail-open, ZERO state side effects) immediately
                # before the UNCHANGED refusal return. Identical data.gate string.
                lazy_core.append_telemetry_event(
                    "gate-refusal",
                    item_id=None,
                    data={"gate": "unacked-hardening", "op": "--run-end",
                          "reason": "pending unacked hardening debt"},
                )
                return 1
            # Override path: the operator authorized retiring the run, so the
            # authorization must ACTUALLY CLEAR the pending debt — flip every
            # unacked entry to acked (regardless of kind/session_id) before
            # deleting the marker.  Without this the entries linger acked:false
            # and the NEXT run's advancing probe keeps withholding the forward
            # route over pending-hardening-debt the operator already discharged
            # (the unclearable-debt deadlock — hardening Round 20; session-less
            # process-friction entries from --cycle-end were the trigger).
            # Coupled-pair mirror of lazy-state.py.
            acked_n = lazy_core.ack_all_unacked_denies()
            override_note = (
                f"OVERRIDE: --ack-unhardened retired the run and acked {acked_n} "
                f"pending deny-ledger entry(ies) (operator-authorized blanket ack)."
            )

        # -----------------------------------------------------------------------
        # efficacy-future-check-unenforced-orchestrator-prose (D1, coupled-pair
        # mirror of lazy-state.py): the end-of-run efficacy/canary/incident trio
        # must flush before the run is retired. Refuse (exit 1, marker LEFT IN
        # PLACE) unless the run-scoped efficacy-flush breadcrumb is present, or
        # --efficacy-skip-authorized retro-grades a deliberate skip. Applies to
        # checkpoint run-ends too. The check reads the marker RAW (non-deleting).
        # -----------------------------------------------------------------------
        efficacy_skip_note = None
        if not lazy_core.efficacy_breadcrumb_present():
            if not args.efficacy_skip_authorized:
                sys.stdout.write(json.dumps({
                    "run_marker_deleted": False,
                    "refused": (
                        "No efficacy-flush breadcrumb COVERING THE "
                        "INTERVENTIONS-BEARING SCOPE for this run. The end-of-run "
                        "efficacy/canary/incident trio must run before --run-end "
                        "against the interventions-bearing scope (claude-config, "
                        "where intervention records actually live) IN ADDITION TO "
                        "the target repo: "
                        "`efficacy-eval.py --repo-root <claude-config>`, "
                        "`efficacy-eval.py --canary --repo-root <claude-config>`, and "
                        "`incident-scan.py --repo-root <claude-config>` — alongside "
                        "the same trio with `--repo-root .` in the target repo (SKILL "
                        "§1c.6 flush). Each drops a run-scoped breadcrumb even on a "
                        "clean no-op, but a target-only flush no longer discharges "
                        "this gate. Run the trio against the interventions-bearing "
                        "scope and re-invoke --run-end, or pass "
                        "--efficacy-skip-authorized to deliberately skip (recorded "
                        "for retro grading). The marker was NOT deleted. "
                        "[efficacy-future-check-unenforced-orchestrator-prose] "
                        "[interventions-telemetry-repo-scope-split-brain]"
                    ),
                }, indent=2) + "\n")
                # run-end-gate-refusals-no-telemetry-event (coupled-pair mirror
                # of lazy-state.py): observability-only gate-refusal emission
                # (marker-gated, fail-open, ZERO state side effects) immediately
                # before the UNCHANGED refusal return. Identical data.gate string.
                lazy_core.append_telemetry_event(
                    "gate-refusal",
                    item_id=None,
                    data={"gate": "efficacy-coverage-missing", "op": "--run-end",
                          "reason": "efficacy flush did not cover the "
                                    "interventions-bearing scope"},
                )
                return 1
            efficacy_skip_note = (
                "OVERRIDE: --efficacy-skip-authorized retired the run without an "
                "efficacy-flush breadcrumb (operator-authorized deliberate skip)."
            )

        # -----------------------------------------------------------------------
        # Phase 7 (lazy-validation-readiness) stop-authorization gates.
        # Coupled-pair mirror of lazy-state.py — see lazy-state.py for rationale.
        # Motivating incident 2026-06-14: attended /lazy-batch 50 stopped at 5/50.
        #
        # CRITICAL: on ANY refusal, the marker MUST be left on disk.
        # -----------------------------------------------------------------------

        if reason == "checkpoint":
            marker_now = lazy_core.read_run_marker()
            attended = True  # legacy marker → stricter gate (safe default)
            if marker_now is not None:
                attended = marker_now.get("attended", True)

            if attended and not args.operator_authorized:
                sys.stdout.write(json.dumps({
                    "run_marker_deleted": False,
                    "refused": (
                        "Stop-authorization gate: this is an ATTENDED run "
                        "(attended=True in the marker). A checkpoint stop requires "
                        "explicit operator authorization. The orchestrator must "
                        "either (a) continue the loop, or (b) present the "
                        "budget-and-queue-guard AskUserQuestion to the operator "
                        "and re-invoke --run-end --reason checkpoint --operator-authorized "
                        "only after the operator confirms. The marker was NOT deleted. "
                        "[Phase 7 / lazy-validation-readiness — 2026-06-14 incident fix]"
                    ),
                    "attended": True,
                }, indent=2) + "\n")
                # run-end-gate-refusals-no-telemetry-event (coupled-pair mirror
                # of lazy-state.py): observability-only gate-refusal emission
                # (marker-gated, fail-open, ZERO state side effects) immediately
                # before the UNCHANGED refusal return. Identical data.gate string.
                lazy_core.append_telemetry_event(
                    "gate-refusal",
                    item_id=None,
                    data={"gate": "checkpoint-auth", "op": "--run-end",
                          "reason": "attended checkpoint stop without operator "
                                    "authorization"},
                )
                return 1

        elif reason == "terminal":
            terminal_reason = getattr(args, "terminal_reason", None)
            if terminal_reason is not None:
                if (terminal_reason not in lazy_core.SANCTIONED_STOP_TERMINAL
                        and not args.operator_authorized):
                    sys.stdout.write(json.dumps({
                        "run_marker_deleted": False,
                        "refused": (
                            f"Stop-authorization gate: non-sanctioned terminal reason "
                            f"'{terminal_reason}'. Sanctioned reasons: "
                            f"{sorted(lazy_core.SANCTIONED_STOP_TERMINAL)}. "
                            f"Pass --operator-authorized to override (operator must "
                            f"explicitly confirm). The marker was NOT deleted. "
                            f"[Phase 7 / lazy-validation-readiness]"
                        ),
                    }, indent=2) + "\n")
                    return 1

        # WU-7.4 checkpoint: requires --next-route, written BEFORE teardown so it
        # folds the marker's counters as they stand at run end.
        checkpoint_written = None
        if reason == "checkpoint":
            if not args.next_route:
                _die("--run-end --reason checkpoint requires --next-route")
            marker_now2 = lazy_core.read_run_marker()
            counters = {}
            if marker_now2 is not None:
                counters = {
                    "forward_cycles": marker_now2.get("forward_cycles"),
                    "meta_cycles": marker_now2.get("meta_cycles"),
                    "max_cycles": marker_now2.get("max_cycles"),
                }
            checkpoint_written = lazy_core.write_run_checkpoint(
                args.next_route, counters,
            )

        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: run-bracket emission BEFORE delete_run_marker (the
        # marker supplies the run identity) and before the D5-B flush so the
        # run-end line rides the segment.
        lazy_core.append_telemetry_event(
            "run-end",
            data={"reason": reason,
                  "terminal_reason": getattr(args, "terminal_reason", None)},
        )
        # D5-B cloud run-end flush (coupled-pair mirror): persist this cloud
        # run's ledger segment into docs/telemetry/cloud/ so it rides the final
        # commit+push. No-op (None) for workstation runs; fail-open.
        telemetry_flushed = lazy_core.flush_cloud_telemetry_segment(
            Path(args.repo_root)
        )

        # mechanize-prose-only-orchestrator-contracts (d) — coupled-pair
        # mirror of lazy-state.py: script-fired flush notification, read
        # BEFORE the marker is deleted.
        _flush_marker = lazy_core.read_run_marker()
        if _flush_marker is not None:
            lazy_core.notify_event(
                "flush", f"run flushed ({reason})", str(args.repo_root),
                pipeline="bug", item_id=_flush_marker.get("started_at"),
                detail=(
                    f"forward={_flush_marker.get('forward_cycles')} "
                    f"meta={_flush_marker.get('meta_cycles')} reason={reason}"
                ),
            )
        # Delete the marker AND the registry (both are run-scoped state).
        deleted = lazy_core.delete_run_marker(clear_registry=True)
        # efficacy-future-check-unenforced-orchestrator-prose (D1, coupled-pair
        # mirror): clear the run-scoped efficacy-flush breadcrumb on teardown.
        lazy_core.clear_efficacy_breadcrumb()
        result_out: dict = {"run_marker_deleted": deleted, "reason": reason}
        if telemetry_flushed is not None:
            # Only a cloud run WITH telemetry events gains this key — every
            # pre-feature output shape is byte-identical (no events → None).
            result_out["telemetry_flushed"] = telemetry_flushed
        if override_note is not None:
            result_out["override"] = override_note
        if efficacy_skip_note is not None:
            result_out["efficacy_skip"] = efficacy_skip_note
        if checkpoint_written is not None:
            result_out["checkpoint"] = checkpoint_written
        # Phase 7: backward-compat deprecation note for legacy --reason terminal
        # callers that omit --terminal-reason (coupled-pair mirror of lazy-state.py).
        if reason == "terminal" and not getattr(args, "terminal_reason", None):
            result_out["deprecation"] = (
                "--run-end --reason terminal should pass --terminal-reason <reason> "
                "for stop-authorization validation (Phase 7 / lazy-validation-readiness). "
                "Sanctioned reasons: " + str(sorted(lazy_core.SANCTIONED_STOP_TERMINAL))
            )
        sys.stdout.write(json.dumps(result_out, indent=2) + "\n")
        return 0

    # Phase 3: --emit-dispatch exits immediately like all other action flags.
    # Pipeline is always "bug" for bug-state.py.
    if args.emit_dispatch is not None:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch (coupled-pair mirror). Fires before any prompt assembly.
        lazy_core.refuse_if_cycle_active("--emit-dispatch")
        cls = args.emit_dispatch
        context: dict = {}
        for kv in (args.context or []):
            if "=" in kv:
                key, _, value = kv.partition("=")
                context[key] = value
        # no-mid-run-observed-friction-harden-dispatch §1 (coupled-pair mirror of
        # lazy-state.py): normalize a hardening dispatch's context so the shared
        # @requires evidence keys resolve for every trigger_kind — an
        # observed-friction dispatch rebinds friction_summary/friction_detail into
        # denied_prompt_summary/denial_reason and gets observed-friction
        # probe_json/registry_state placeholders; auto-triggers pass through with
        # only the {blocking} default added.
        if cls == "hardening":
            context = lazy_core.normalize_hardening_dispatch_context(context)
        try:
            # mechanize-prose-only-orchestrator-contracts (c) / D3-A —
            # coupled-pair mirror of lazy-state.py: bind apply-resolution's
            # chosen_path/resolution_summary from the recorded decision
            # (raises ValueError, caught below, when a sentinel_path is
            # named but no --record-decision has been run for it yet).
            context = lazy_core.bind_decision_record_context(
                cls, context, "bug-state.py",
            )
            result = lazy_core.emit_dispatch_prompt(
                cls, context,
                pipeline="bug",
                cloud=args.cloud,
            )
        except ValueError as exc:
            sys.stdout.write(json.dumps({
                "dispatch_prompt": None,
                "dispatch_model": None,
                "dispatch_class": cls,
                "dispatch_prompt_refused": str(exc),
            }, indent=2) + "\n")
            return 1
        if result.get("ok"):
            prompt = result["prompt"]
            model = result["model"]
            # Phase 7 (lazy-validation-readiness) Deliverable 3: capture the
            # returned entry so we can surface dispatch_prompt_ref (@@lazy-ref
            # nonce=<hex>) in the output JSON.  Coupled-pair mirror of
            # lazy-state.py.  The guard's existing @@lazy-ref resolution path
            # resolves any registered class (no guard edit needed).
            _ref_entry = lazy_core.register_emission_if_marked(
                prompt, cls,
                item_id=context.get("item_id"),
                model=model,
            )
            # mechanize-prose-only-orchestrator-contracts (b) / D2-A —
            # coupled-pair mirror of lazy-state.py: a registered input-audit
            # emission discharges the obligation.
            if _ref_entry is not None and cls == "input-audit":
                lazy_core.discharge_audit_obligation()
            # Phase 8 WU-8.2: emission no longer acks the deny ledger.  The ack
            # moves to GUARD-ALLOW time (lazy_guard.py, on allowing a hardening-
            # class entry) so the debt clears only when a hardening dispatch
            # actually reaches execution.  Mirror of lazy-state.py.
            out: dict = {
                "dispatch_prompt": prompt,
                "dispatch_model": model,
                "dispatch_class": cls,
            }
            # Phase 7 WU-7.5a: surface the marker-gated cycle_header when present
            # (emit_dispatch_prompt only attaches it when a run marker is active).
            if "cycle_header" in result:
                out["cycle_header"] = result["cycle_header"]
            # Phase 7 Deliverable 3: surface @@lazy-ref reference token for
            # meta dispatch by reference (no retyping → no transcription slips).
            if _ref_entry is not None:
                out["dispatch_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"
            else:
                out["dispatch_prompt_ref"] = None
            sys.stdout.write(json.dumps(out, indent=2) + "\n")
            return 0
        else:
            sys.stdout.write(json.dumps({
                "dispatch_prompt": None,
                "dispatch_model": None,
                "dispatch_class": cls,
                "dispatch_prompt_refused": result.get("refused", "unknown refusal"),
            }, indent=2) + "\n")
            return 1

    if args.neutralize_sentinel is not None:
        result = lazy_core.neutralize_sentinel(Path(args.neutralize_sentinel), date=args.apply_date)
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: a successful neutralization is the halt-dwell END
        # marker (`sentinel-resolved`). Marker-gated + fail-open.
        if result.get("ok"):
            _tl_sentinel = Path(args.neutralize_sentinel)
            lazy_core.append_telemetry_event(
                "sentinel-resolved",
                item_id=_tl_sentinel.resolve().parent.name,
                data={"sentinel": _tl_sentinel.name},
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.provisionalize_sentinel is not None:
        # park-provisional-acceptance (SPEC D2) — coupled-pair mirror of
        # lazy-state.py: the script-owned acceptance action. Refusals exit 1
        # with zero writes. Cycle-guarded like every other lifecycle write path.
        lazy_core.refuse_if_cycle_active("--provisionalize-sentinel")
        result = lazy_core.provisionalize_sentinel(
            Path(args.provisionalize_sentinel), Path(args.repo_root),
            date=args.apply_date,
        )
        if result.get("ok"):
            _tl_prov = Path(args.provisionalize_sentinel)
            _tl_prov_item = _tl_prov.resolve().parent.name
            lazy_core.append_telemetry_event(
                "sentinel-provisionalized",
                item_id=_tl_prov_item,
                data={
                    "decision_commit": result.get("decision_commit"),
                    "divergence": result.get("divergence"),
                    "audit_divergence": result.get("audit_divergence"),
                },
            )
            # mechanize-prose-only-orchestrator-contracts (d) — coupled-pair
            # mirror of lazy-state.py.
            lazy_core.notify_event(
                "provisional-accept", f"{_tl_prov_item} accepted provisionally",
                str(args.repo_root), pipeline="bug", item_id=_tl_prov_item,
                detail=f"divergence={result.get('divergence')} — unratified until reviewed",
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.apply_pseudo is not None:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch (coupled-pair mirror). Fires before any SPEC/PHASES write.
        lazy_core.refuse_if_cycle_active("--apply-pseudo")
        name, spec = args.apply_pseudo
        result = lazy_core.apply_pseudo(
            Path(args.repo_root), name, Path(spec),
            plan_path=Path(args.plan) if args.plan else None,
            date=args.apply_date, reason=args.reason,
            deferred_step=args.deferred_step,
        )
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: `pseudo-applied` on success / `gate-refusal` on an
        # exit-1 verdict (marker-gated + fail-open; adds NO output keys).
        _tl_item = Path(spec).resolve().parent.name
        if result.get("ok"):
            lazy_core.append_telemetry_event(
                "pseudo-applied", item_id=_tl_item, data={"pseudo": name},
            )
        else:
            lazy_core.append_telemetry_event(
                "gate-refusal", item_id=_tl_item,
                data={"gate": "apply-pseudo", "pseudo": name},
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.archive_fixed is not None:
        result = lazy_core.archive_fixed(
            Path(args.repo_root), Path(args.archive_fixed),
            date=args.apply_date,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.enqueue_adhoc:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch (coupled-pair mirror). Fires before any queue.json write.
        lazy_core.refuse_if_cycle_active("--enqueue-adhoc")
        if not args.id:
            _die("--enqueue-adhoc requires --id")
        if not args.name:
            _die("--enqueue-adhoc requires --name")
        # queue-dependency-dag Phase 4: optional --deps a,b (comma-separated
        # hard-dep ids). Parsed here; validated inside enqueue_adhoc.
        _adhoc_deps = (
            [s.strip() for s in args.deps.split(",") if s.strip()]
            if args.deps else None
        )
        result = enqueue_adhoc(
            Path(args.repo_root), args.id, args.name, args.spec_dir,
            args.severity, deps=_adhoc_deps,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.record_decision:
        # mechanize-prose-only-orchestrator-contracts (c) / D3-A — coupled-pair
        # mirror of lazy-state.py.
        lazy_core.refuse_if_cycle_active("--record-decision")
        if not args.sentinel or not args.chosen:
            _die("--record-decision requires --sentinel and --chosen")
        record = lazy_core.record_decision(
            args.sentinel, args.chosen, summary=args.summary,
        )
        sys.stdout.write(json.dumps(record, indent=2) + "\n")
        return 0

    if args.sync_deps:
        # queue-dependency-dag D5 (coupled-pair mirror of lazy-state.py
        # --sync-deps): the script-owned SPEC→queue deps feeder for the bug
        # pipeline. Orchestrator-only — refuse FIRST so a cycle subagent gets
        # exit 3 with ZERO side effects.
        lazy_core.refuse_if_cycle_active("--sync-deps")
        if not args.id:
            _die("--sync-deps requires --id")
        result = lazy_core.sync_deps(
            Path(args.repo_root) / "docs" / "bugs" / "queue.json",
            args.id,
            Path(args.repo_root) / "docs" / "bugs",
            queue_label="bugs/queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.reorder_queue:
        # Operator-only / out-of-cycle queue mutation (coupled-pair mirror of
        # lazy-state.py --reorder-queue). Refuse FIRST so a cycle subagent gets
        # exit 3 with zero side effects.
        lazy_core.refuse_if_cycle_active("--reorder-queue")
        if not args.id or not args.reorder_to:
            _die("--reorder-queue requires --id and --to")
        to_arg: "str | int"
        try:
            to_arg = int(args.reorder_to)
        except (TypeError, ValueError):
            to_arg = args.reorder_to
        result = lazy_core.reorder_queue(
            Path(args.repo_root) / "docs" / "bugs" / "queue.json",
            args.id,
            to=to_arg,
            queue_label="bugs/queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.pin:
        # bug-queue-aging-backpressure D2-A. Orchestrator-only / out-of-cycle —
        # refuse FIRST so a cycle subagent gets exit 3 with zero side effects
        # (same contract as --reorder-queue / --enqueue-adhoc).
        lazy_core.refuse_if_cycle_active("--pin")
        if not args.id:
            _die("--pin requires --id")
        result = pin_bug_severity(
            Path(args.repo_root), args.id,
            until=args.pin_until, reason=args.reason,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.set_severity is not None:
        # no-sanctioned-cli-for-queue-state-mutations (coupled-pair mirror of
        # lazy-state.py --set-tier): operator-directed in-place severity change.
        # Refuse FIRST (exit 3 for a cycle subagent), then require
        # --operator-authorized. set_queue_priority ATOMICALLY re-sorts listed
        # order to match the new merged priority in the SAME write.
        lazy_core.refuse_if_cycle_active("--set-severity")
        if not args.operator_authorized:
            _die("--set-severity requires --operator-authorized (the operator must "
                 "have approved the priority change).")
        _id, _sev = args.set_severity
        result = lazy_core.set_queue_priority(
            Path(args.repo_root) / "docs" / "bugs" / "queue.json",
            _id, "bug", _sev, queue_label="bugs/queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.unpin is not None:
        # no-sanctioned-cli-for-queue-state-mutations: the inverse of --pin.
        # Same gate contract as --pin + operator-authorization.
        lazy_core.refuse_if_cycle_active("--unpin")
        if not args.operator_authorized:
            _die("--unpin requires --operator-authorized.")
        result = unpin_bug_severity(Path(args.repo_root), args.unpin)
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.add_deps or args.remove_deps:
        # no-sanctioned-cli-for-queue-state-mutations (coupled-pair mirror of
        # lazy-state.py): post-hoc arbitrary deps edit. Refuse FIRST + require
        # --operator-authorized. --add-deps / --remove-deps are mutually exclusive.
        lazy_core.refuse_if_cycle_active("--add-deps/--remove-deps")
        if args.add_deps and args.remove_deps:
            _die("--add-deps and --remove-deps are mutually exclusive (one op per call).")
        if not args.operator_authorized:
            _die("--add-deps/--remove-deps requires --operator-authorized.")
        _target = args.add_deps or args.remove_deps
        _dep_ids = (
            [s.strip() for s in args.deps.split(",") if s.strip()]
            if args.deps else None
        )
        if not _dep_ids:
            _die("--add-deps/--remove-deps requires a non-empty --deps id list.")
        result = lazy_core.mutate_queue_deps(
            Path(args.repo_root) / "docs" / "bugs" / "queue.json",
            _target,
            add=(_dep_ids if args.add_deps else None),
            remove=(_dep_ids if args.remove_deps else None),
            queue_label="bugs/queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.reassert_owner:
        # single-slot-marker-ownership-race-disarms-owning-run Phase 2 (coupled-pair
        # mirror of lazy-state.py --reassert-owner). The owner RE-ARM path. The run
        # marker is SHARED between pipelines, so this action is identical here.
        # Orchestrator-only — refuse FIRST so a cycle subagent gets exit 3 with
        # ZERO side effects.
        lazy_core.refuse_if_cycle_active("--reassert-owner")
        if not args.session_id:
            _die("--reassert-owner requires --session-id")
        prior = lazy_core.marker_owner_status(args.session_id)
        reasserted = lazy_core.reassert_marker_owner(args.session_id)
        sys.stdout.write(json.dumps(
            {"reasserted": reasserted, "prior_status": prior}, indent=2
        ) + "\n")
        return 0

    if args.set_max_cycles is not None:
        # lazy-batch-no-mid-run-budget-or-park-controls (coupled-pair mirror of
        # lazy-state.py; the marker is shared): operator-authorized mid-run budget
        # change. Orchestrator-only — refuse FIRST (exit 3, zero side effects).
        lazy_core.refuse_if_cycle_active("--set-max-cycles")
        if not args.operator_authorized:
            _die("--set-max-cycles requires --operator-authorized (the operator must "
                 "have approved the mid-run budget change).")
        if args.set_max_cycles < 1:
            _die("--set-max-cycles requires a positive integer N (>= 1).")
        result = lazy_core.set_marker_max_cycles(args.set_max_cycles)
        if result is None:
            _die("--set-max-cycles: no active run marker to update.")
        out = {"max_cycles_updated": True, **result}
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.set_park is not None:
        # lazy-batch-no-mid-run-budget-or-park-controls (coupled-pair mirror):
        # operator-authorized mid-run park toggle. 'on' arms BOTH park facets (the
        # --park umbrella); 'off' clears both AND park_provisional.
        lazy_core.refuse_if_cycle_active("--set-park")
        if not args.operator_authorized:
            _die("--set-park requires --operator-authorized (the operator must have "
                 "approved the mid-run park toggle).")
        _on = args.set_park == "on"
        result = lazy_core.set_marker_park(
            park_needs_input=_on,
            park_blocked=_on,
            park_provisional=(None if _on else False),
        )
        if result is None:
            _die("--set-park: no active run marker to update.")
        out = {"park_updated": True, **result}
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.set_park_provisional is not None:
        # lazy-batch-no-mid-run-budget-or-park-controls (coupled-pair mirror):
        # operator-authorized mid-run park-provisional toggle. set_marker_park
        # enforces the standing invariant (provisional requires needs-input).
        lazy_core.refuse_if_cycle_active("--set-park-provisional")
        if not args.operator_authorized:
            _die("--set-park-provisional requires --operator-authorized (the operator "
                 "must have approved the mid-run park-provisional toggle).")
        result = lazy_core.set_marker_park(
            park_provisional=(args.set_park_provisional == "on"),
        )
        if result is None:
            _die("--set-park-provisional: no active run marker to update.")
        out = {"park_updated": True, **result}
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.record_intervention:
        # intervention-efficacy-tracking Phase 1 (coupled-pair mirror of
        # lazy-state.py --record-intervention; the capture helper is shared
        # lazy_core.record_intervention). Manual / hardening-round / D9-backfill
        # capture path — the completion-gate capture lives inside
        # lazy_core.apply_pseudo. Orchestrator-only: refuse a cycle subagent
        # FIRST (exit 3, zero side effects).
        lazy_core.refuse_if_cycle_active("--record-intervention")
        if not args.id:
            _die("--record-intervention requires --id")
        provenance = (
            "backfilled" if (args.shipped_commit or args.shipped_date)
            else "manual"
        )
        overrides = {
            "target_signal": args.target_signal,
            "expected_direction": args.expected_direction,
            "signal_independence": args.signal_independence,
            "review_after_runs": args.review_after_runs,
        }
        overrides = {k: v for k, v in overrides.items() if v is not None}
        # hardening-intervention-records-unmeasurable-or-missing WU-2: reject
        # unknown --target-signal vocabulary at the CLI (before it silently
        # degrades to "undeclared" inside record_intervention), then hard-fail
        # an undeclared --pipeline hardening record (the escape hatch is the
        # EXPLICIT --target-signal undeclared, checked via `is None` so that
        # string never trips this branch).
        if args.target_signal is not None:
            err = lazy_core.validate_intervention_target_signal(args.target_signal)
            if err is not None:
                sys.stderr.write(err + "\n")
                return 1
        if args.intervention_pipeline == "hardening" and args.target_signal is None:
            sys.stderr.write(
                "--record-intervention --pipeline hardening requires an "
                "explicit --target-signal: a hardening round cannot be "
                "recorded with an undeclared measurement target. Pass "
                "--target-signal undeclared for a genuinely-immeasurable "
                "hardening round (the deliberate escape hatch), or a "
                "concrete event:<type> / kpi:<sys>.<id> target.\n"
            )
            return 1
        spec_path = None
        if args.spec_dir:
            spec_path = Path(args.spec_dir)
            if not spec_path.is_absolute():
                spec_path = Path(args.repo_root) / spec_path
        result = lazy_core.record_intervention(
            Path(args.repo_root),
            args.id,
            pipeline=args.intervention_pipeline,
            spec_path=spec_path,
            shipped_commit=args.shipped_commit,
            shipped_date=args.shipped_date,
            provenance=provenance,
            hypothesis_overrides=overrides or None,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.test:
        return run_smoke_tests()

    if args.backfill_receipts:
        result = backfill_receipts(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.fsck:
        # fixed-bugs-unarchived-fsck Fix Scope §3: read-only, never mutates —
        # no refuse_if_cycle_active guard needed (there is nothing to guard).
        result = fsck(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result.get("ok") else 1

    if args.ack_deny is not None:
        # meta-dispatch-not-by-reference-and-ack-overpriced (coupled-pair
        # mirror of lazy-state.py): cheap per-entry ack, gated EXACTLY like
        # --backfill-receipts/--link-provenance (a cycle subagent is refused
        # exit 3 with zero side effects).
        lazy_core.refuse_if_cycle_active("--ack-deny")
        result = lazy_core.ack_deny_by_selector(args.ack_deny, args.resolution or "")
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result.get("ok") else 1

    if args.link_provenance:
        # code-doc-provenance-linkage Phase 3 (coupled-pair mirror of
        # lazy-state.py): the manual trigger of the one-writer provenance
        # producer. Operator-only / out-of-cycle — gated EXACTLY like
        # --enqueue-adhoc (a cycle subagent is refused exit 3 with zero side
        # effects).
        lazy_core.refuse_if_cycle_active("--link-provenance")
        if not args.id:
            _die("--link-provenance requires --id")
        result = lazy_core.link_provenance(
            Path(args.repo_root), args.id,
            commit_range=args.commits, pr=args.pr,
            body_file=Path(args.body_file) if args.body_file else None,
            dry_run=args.dry_run,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result.get("ok") else 1

    if args.provenance_lookup is not None:
        # code-doc-provenance-linkage Phase 4 (D6-A): PURE READ — which
        # decision records govern this file. Not cycle-guarded: dispatched
        # subagents are the intended consumers (read-only, like --verify-ledger).
        result = lazy_core.provenance_lookup(
            Path(args.repo_root), args.provenance_lookup
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.lint_provenance:
        # code-doc-provenance-linkage Phase 5 (D10): PURE READ, report only.
        result = lazy_core.lint_provenance(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.backfill_provenance:
        # code-doc-provenance-linkage Phase 5 (D7-A): one-shot backfill of
        # already-receipted items through the ONE producer (honest degraded
        # provenance: backfilled + message-grep). Operator-only — cycle-guarded
        # like --backfill-receipts' sibling mutations.
        lazy_core.refuse_if_cycle_active("--backfill-provenance")
        result = lazy_core.backfill_provenance(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result.get("ok") else 1

    if args.verify_ledger is not None:
        # Scripted completion-ledger guard: verify the four preconditions for
        # marking a bug fixed. The orchestrator's && chains short-circuit on
        # non-zero exit when any check fails. When --plan is also passed, checks
        # 3+4 narrow to that plan part's scope (Phase 9 WU-3) — reuses the
        # existing --plan flag (shared with --apply-pseudo, no dest collision).
        # verify_ledger expects a spec directory (not the SPEC.md file path).
        # Normalize: if the caller passed a .md file, use its parent directory —
        # coupled-pair mirror of lazy-state.py (bug `verify-ledger-planning-scope-
        # and-file-arg`). Computing `_spec_dir` here (not passing args.verify_ledger
        # raw) also stamps the correct `gate-refusal` item_id (the bug-dir name, not
        # "SPEC.md"). verify_ledger itself also normalizes at the source; this keeps
        # the telemetry item_id correct regardless.
        _vl_path = Path(args.verify_ledger)
        _spec_dir = _vl_path.parent if _vl_path.suffix == ".md" else _vl_path
        result = lazy_core.verify_ledger(
            Path(args.repo_root), _spec_dir,
            plan_path=Path(args.plan) if args.plan else None,
        )
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: an exit-1 ledger verdict is a `gate-refusal` event.
        if not result["ok"]:
            lazy_core.append_telemetry_event(
                "gate-refusal",
                item_id=_spec_dir.resolve().name,
                data={"gate": "verify-ledger",
                      "failing_check": result.get("failing_check"),
                      # completion-gate-refusal-opacity Fix Scope §3
                      # (coupled-pair mirror of lazy-state.py).
                      "detail_head": lazy_core.summarize_failing_detail(result)},
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    real_device = resolve_real_device(args.real_device)
    # lazy-batch-no-mid-run-budget-or-park-controls (coupled-pair mirror of
    # lazy-state.py): resolve the EFFECTIVE park state — the marker is
    # authoritative for a live run (mid-run --set-park takes effect), CLI flags
    # are the no-marker / legacy-marker fallback (byte-identical back-compat).
    _park_marker = lazy_core.read_run_marker()
    _eff_park_ni, _eff_park_bl, _eff_park_pv = lazy_core.fold_park_flags(
        args.park_needs_input, args.park_blocked, args.park_provisional,
        _park_marker,
    )
    state = compute_state(
        Path(args.repo_root),
        cloud=args.cloud,
        real_device=real_device,
        scope_bug_id=args.bug_id,
        park_needs_input=_eff_park_ni,
        park_blocked=_eff_park_bl,
        park_provisional=_eff_park_pv,
        per_feature_cycle_cap=args.per_feature_cycle_cap,
        strict_research_halt=args.strict_research_halt,
    )
    # Surface the effective park state when a marker is present (byte-identical
    # no-marker output preserved) so the orchestrator can confirm a --set-park
    # toggle took effect mid-run.
    if _park_marker is not None and "park_needs_input" in _park_marker:
        state["park_active"] = {
            "park_needs_input": _eff_park_ni,
            "park_blocked": _eff_park_bl,
            "park_provisional": _eff_park_pv,
        }
    # --repeat-count / --repeat-count-peek are strictly additive and flag-gated
    # so that default output remains byte-identical when neither is passed.
    # --repeat-count ADVANCES the persisted streak; --repeat-count-peek computes
    # the same fields via peek=True (no state-file write). Both populate the
    # 'repeat_count' (Phase-9 dispatch-tuple) AND 'step_repeat_count' (Phase-10
    # step-level oscillation) output fields — emitted together so no new flag is
    # needed and the default (no flag) output stays byte-identical.
    if args.repeat_count or args.repeat_count_peek:
        # pipeline="bug" namespaces the persisted signature file so a parallel
        # /lazy-batch session's lazy-state.py probes (which share the repo
        # root) cannot reset this pipeline's repeat streak — and vice versa.
        _counts = lazy_core.update_repeat_counts(
            Path(args.repo_root), state, pipeline="bug", peek=args.repeat_count_peek
        )
        state["repeat_count"] = _counts["repeat_count"]
        state["step_repeat_count"] = _counts["step_repeat_count"]
    # Counter advance: at dispatch-bound probe time (--repeat-count, NOT
    # --repeat-count-peek) advance the marker-persisted forward/meta counters.
    # Mirror of the peek discipline for update_repeat_counts: only the one
    # dispatch-bound probe per cycle advances any persisted state.
    #
    # FORWARD-CYCLE AUTHORITY (byref-dispatch-undercounts-forward-cycles, Phase 1,
    # WU-2 — verbatim mirror of lazy-state.py's WU-1 form-1 reconciliation):
    # advance_forward_cycle is the AUTHORITATIVE forward-advance trigger on this
    # real-skill (by-reference) probe path. It keys on the consume-INDEPENDENT
    # [feature_id, current_step, sub_skill] state change, so a by-ref dispatch that
    # does NOT bump the consume census (the frozen-census / Theory-1b case) still
    # advances forward_cycles. advance_run_counters (the consume-gated oracle) is NO
    # LONGER the forward authority on this path — it undercounted, letting the
    # max-cycles cap never fire. The two state scripts' advance wiring stays in
    # lockstep (lazy_parity_audit.py). Meta accounting via --emit-dispatch /
    # advance_meta_cycle is untouched, so nothing on this path double-counts.
    #
    # SECOND TRIGGER (byref-forward-cycles-frozen-on-multicycle-same-step — verbatim
    # mirror of lazy-state.py): pass consume_gate=True so a genuine NEXT cycle sharing
    # an IDENTICAL [feature_id, current_step, sub_skill] tuple (the multi-part
    # execute-plan case: same bug, same step, same real sub_skill, one cycle per plan
    # part) still advances forward_cycles off the registry consume-census rise. The
    # state-change trigger ALONE froze the counter at 1 for the whole phase, so
    # max_cycles could never trip. The two state scripts' advance wiring stays in
    # lockstep (lazy_parity_audit.py).
    # No marker present → no-op (advance_forward_cycle returns None).
    if args.repeat_count:
        lazy_core.advance_forward_cycle(state, consume_gate=True)
    # --emit-prompt is strictly additive and flag-gated so that default output
    # remains byte-identical when the flag is absent. Placed AFTER the repeat
    # flags so the same-invocation count (from EITHER --repeat-count or
    # --repeat-count-peek) drives the emitter's loop-block + model decision.
    # Pipeline is "bug" here (bug-state reuses the feature_* keys for bugs).
    # emit_cycle_prompt(...) is None for pseudo-skills / terminal probes →
    # cycle_prompt: null, cycle_model: null (so the orchestrator's one probe
    # call is uniform); on refusal it also adds cycle_prompt_refused.
    if args.emit_prompt:
        # Phase 8 WU-8.2: routed hardening debt WITHHOLDS the forward route.
        # When (marker present AND pending_hardening() > 0) the probe must NOT
        # emit/register a cycle_prompt — the orchestrator owes a hardening
        # dispatch first.  Mirror of lazy-state.py (coupled-pair).
        _emit_marker = lazy_core.read_run_marker()
        _emit_debt = lazy_core.pending_hardening() if _emit_marker is not None else 0
        if _emit_marker is not None and _emit_debt > 0:
            # Withhold: no cycle_prompt, no cycle_model, no registration.
            _oldest = lazy_core.oldest_unacked_deny()
            state["route_overridden_by"] = "pending-hardening-debt"
            _probe_summary = (
                f"step={state.get('current_step')} sub_skill={state.get('sub_skill')} "
                f"feature_id={state.get('feature_id')} pending_hardening={_emit_debt}"
            )
            state["hardening_emit_command"] = lazy_core.build_hardening_emit_command(
                "bug-state.py",
                item_id=state.get("feature_id") or "",
                oldest_deny=_oldest,
                probe_summary=_probe_summary,
                registry_summary=lazy_core.registry_summary(),
                cwd=str(args.repo_root),
            )
        elif (
            _emit_marker is not None
            and lazy_core.pending_audit_obligation() is not None
        ):
            # mechanize-prose-only-orchestrator-contracts (b) / D2-A —
            # coupled-pair mirror of lazy-state.py.
            _obligation = lazy_core.pending_audit_obligation()
            state["route_overridden_by"] = "audit-obligation"
            _aud_item_id = _obligation.get("item_id") or state.get("feature_id") or ""
            _aud_spec_path = (
                state.get("spec_path")
                if state.get("feature_id") == _obligation.get("item_id")
                else None
            ) or str(Path(args.repo_root) / "docs" / "bugs" / _aud_item_id)
            state["input_audit_emit_command"] = lazy_core.build_input_audit_emit_command(
                "bug-state.py",
                item_id=_aud_item_id,
                item_name=state.get("feature_name") or _aud_item_id,
                spec_path=_aud_spec_path,
                cycle_kind=_obligation.get("cycle_kind") or "",
                cwd=str(args.repo_root),
            )
        else:
            rc = state.get("repeat_count") if (args.repeat_count or args.repeat_count_peek) else None
            # Phase 9 (lazy-validation-readiness) — per-part model tiering.
            # Shares lazy-state.py's exact emit_cycle_prompt path: the cycle_model
            # for an /execute-plan cycle is selected from the current plan part's
            # `complexity:` tag (mechanical → sonnet, complex / absent → opus),
            # composing with the loop-block downgrade. The bug pipeline reuses the
            # SAME execute-plan cycle-model path, so the tiering mirrors here
            # automatically — no separate logic.
            emitted = lazy_core.emit_cycle_prompt(
                Path(args.repo_root), state,
                pipeline="bug", cloud=args.cloud, repeat_count=rc,
                # park-provisional-acceptance (SPEC D13, coupled-pair mirror):
                # park-mode probes select the park=park template sections.
                # lazy-batch-no-mid-run-budget-or-park-controls: EFFECTIVE
                # (marker-authoritative) park state, so --set-park drives it.
                park_mode=_eff_park_ni,
            )
            if emitted is None:
                state["cycle_prompt"] = None
                state["cycle_model"] = None
            elif emitted.get("ok"):
                state["cycle_prompt"] = emitted["prompt"]
                state["cycle_model"] = emitted["model"]
            else:
                state["cycle_prompt"] = None
                state["cycle_model"] = None
                state["cycle_prompt_refused"] = emitted.get("refused")
            # Registry integration (Phase 1): when a marker is active and the
            # emission produced a non-null cycle_prompt, register it so the
            # validate hook can check it.  No marker → no-op (byte-identical).
            # Bug pipeline: feature_id in state holds the bug id (same key name).
            # F2a (bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref): capture
            # the returned entry so we can surface the @@lazy-ref token alongside
            # the prompt; orchestrators may use the shorter token to dispatch
            # subagents (dispatch-by-reference).  Mirrors lazy-state.py exactly.
            cycle_prompt = state.get("cycle_prompt")
            if cycle_prompt:
                _ref_entry = lazy_core.register_emission_if_marked(
                    cycle_prompt, "cycle",
                    item_id=state.get("feature_id"),
                    model=state.get("cycle_model"),
                )
                if _ref_entry is not None:
                    # Surface the @@lazy-ref token so the orchestrator can use
                    # dispatch-by-reference instead of repeating the full text.
                    state["cycle_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"
                else:
                    # No marker active or registration failed — no ref available.
                    state["cycle_prompt_ref"] = None
            else:
                state["cycle_prompt_ref"] = None
        # harness-telemetry-ledger Phase 2 (D4-B) — coupled-pair mirror of
        # lazy-state.py: --emit-prompt IS the per-cycle dispatch surface —
        # record the routed dispatch tuple (+ a `halt` sibling when the
        # terminal_reason is a halt). Marker-gated + fail-open; adds NO keys
        # to the probe JSON. Bug pipeline: state's feature_id holds the bug id.
        _tl_dispatch_data = {
            "current_step": state.get("current_step"),
            "sub_skill": state.get("sub_skill"),
            "terminal_reason": state.get("terminal_reason"),
        }
        if state.get("route_overridden_by"):
            _tl_dispatch_data["route_overridden_by"] = state["route_overridden_by"]
        lazy_core.append_telemetry_event(
            "dispatch", item_id=state.get("feature_id"), data=_tl_dispatch_data,
        )
        if state.get("terminal_reason") in lazy_core.TELEMETRY_HALT_TERMINAL_REASONS:
            lazy_core.append_telemetry_event(
                "halt", item_id=state.get("feature_id"),
                data={"terminal_reason": state.get("terminal_reason"),
                      "current_step": state.get("current_step")},
            )
    # --probe is strictly additive and flag-gated so that default output remains
    # byte-identical when the flag is absent.  Composes independently with
    # --repeat-count (both may be present simultaneously).
    if args.probe:
        state["git_guards"] = lazy_core.git_guard_status(Path(args.repo_root))
        # Counter fold (Phase 1): when a marker is present, fill in absent
        # --forward-cycles / --meta-cycles from the marker's persisted values.
        # Explicit flag values win over marker values (backward compat).
        # When no marker is present, behavior is byte-identical to before.
        _marker = lazy_core.read_run_marker()
        _fwd, _meta = lazy_core.fold_run_counters(
            args.forward_cycles, args.meta_cycles,
            _marker,
        )
        # lazy-batch-no-mid-run-budget-or-park-controls (coupled-pair mirror): the
        # marker is the authoritative live budget — fold max_cycles from it when
        # present so a mid-run --set-max-cycles shows in the header immediately.
        _max_cycles = lazy_core.fold_max_cycles(args.max_cycles, _marker)
        state["cycle_header"] = lazy_core.format_cycle_header(
            state, forward_cycles=_fwd,
            max_cycles=_max_cycles, meta_cycles=_meta,
        )
        # Phase 7 WU-7.1: deny-ledger enrichment — MARKER-GATED so default
        # (no-marker) probe output stays byte-identical to the committed
        # baselines.  When a marker is present, surface the routed hardening
        # debt: pending_hardening (count) always, pending_denials (reason heads)
        # only when there is debt.
        if _marker is not None:
            _pending = lazy_core.pending_hardening()
            state["pending_hardening"] = _pending
            if _pending > 0:
                state["pending_denials"] = lazy_core.pending_denial_reasons()
                # Phase 8 WU-8.3: warn to STDERR only (stdout must stay parseable
                # JSON; lazy_inject.py's _run_probe captures stderr separately).
                sys.stderr.write(
                    f"⚠ pending_hardening: {_pending} — forward route withheld; "
                    f"run hardening_emit_command first\n"
                )
            # Residual gap B (loop-detector-false-positives-probes-and-cross-run-
            # state): surface a PRIOR/crashed run's leftover unacked denials as
            # informational debt (never blocking — never withholds the route,
            # never gates --run-end). Coupled-pair mirror of lazy-state.py.
            _prior_pending = lazy_core.prior_run_pending_hardening()
            if _prior_pending > 0:
                state["prior_run_pending_hardening"] = _prior_pending
    # operator-halt-notifications (D2): the terminal-emission chokepoint —
    # coupled-pair mirror of lazy-state.py (parity surface #7). Config-gated,
    # dedup-ledgered, fail-OPEN; state's feature_id holds the bug id.
    lazy_core.notify_halt(state, args.repo_root, pipeline="bug")
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
