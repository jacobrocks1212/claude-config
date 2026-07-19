#!/usr/bin/env python3
"""
lazy-state.py — Compute the next /lazy or /lazy-cloud state for autonomous orchestration.

Mirrors the state machine documented in:
  - user/skills/lazy/SKILL.md
  - repos/algobooth/.claude/skills/lazy-cloud/SKILL.md

Reads queue.json, ROADMAP.md, per-feature SPEC/PHASES/sentinels, and emits a
JSON object describing what to do next. Used by:
  - The thin-wrapper /lazy and /lazy-cloud (one-skill-per-invocation dispatch)
  - The /lazy-batch and /lazy-batch-cloud orchestrators (autonomous loop)

Usage:
    python3 lazy-state.py [--cloud] [--skip-needs-research]
                          [--real-device {yes,no,auto}] [--repo-root <path>]
    python3 lazy-state.py --test                    # run fixture smoke tests
    python3 lazy-state.py --run-start               # write run marker (pipeline=feature); gates registry/counter side-effects
    python3 lazy-state.py --run-end                 # delete marker + registry (run-scoped teardown)
    python3 lazy-state.py --probe [--repeat-count]  # --probe/--repeat-count fold/advance marker-persisted counters when a run marker is present; --repeat-count-peek reads without advancing

Output schema (stdout JSON):
{
  "feature_id":        "<id>"          | null,
  "feature_name":      "<name>"        | null,
  "spec_path":         "<absolute>"    | null,
  "current_step":      "<step name>"   | null,
  "sub_skill":         "<name>"        | null,
  "sub_skill_args":    "<args>"        | null,
  "terminal_reason":   null | "all-features-complete" | "cloud-queue-exhausted"
                            | "device-queue-exhausted"
                            | "queue-blocked-on-research"
                            | "blocked" | "needs-research" | "needs-input"
                            | "needs-spec-input" | "queue-missing"
                            | "completion-unverified" | "stale_upstream"
                            | "all-remaining-deferred"
                            | "scoped-id-not-found",
  "notify_message":    "<string>"      | null,
  "diagnostics":       []                                  # always present; non-empty
                                                           # surfaces backlog warnings
                                                           # (e.g. plan files missing
                                                           # frontmatter)
}

Exit codes:
  0 — success (state computed, even if terminal)
  2 — malformed input (invalid YAML frontmatter, broken queue.json, etc.)
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("lazy-state.py requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)

# Insert this directory onto sys.path so `import cli_surface` resolves when
# lazy-state.py is run directly from user/scripts/ OR via the ~/.claude/scripts
# symlink (mirrors the bug-state.py sibling-import guard).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_surface

# lazy_coord owns the coordinator leases.json (worktree-pool fencing). Imported
# for the read-only has_live_lease() helper used by the --emit-prompt merged-head
# divergence guard's serial-tail lease exemption (lazy-batch-parallel-run-harness-
# gaps round-2 gap 8). lazy_coord is stdlib-only and never imports lazy_core, so
# there is no import cycle.
import lazy_coord

# Domain-agnostic helpers live in lazy_core (WU-1.2 extraction). Import the
# module itself so lazy_core._DIAGNOSTICS is the canonical list object and
# lazy-state.py's _state() / compute_state() always reference the same list.
import lazy_core
from lazy_core import (
    _atomic_write,
    _die,
    _diag,
    clear_diagnostics,
    parse_sentinel,
    _parse_plan_frontmatter,
    _plan_status,
    _plan_lowest_phase,
    _plan_phase_set,
    _unchecked_wus_in_plan_scope,
    _all_wus_in_plan_scope,
    _plan_wu_checkbox_counts,
    _plan_unchecked_wus_are_verification_only,
    _phases_text_scoped_to,
    find_implementation_plans,
    find_retro_plans,
    latest_retro_plan,
    _has_any_complete_plan,
    retro_plan_has_significant_divergences,
    count_deliverables,
    remaining_unchecked_are_verification_only,
    _VERIFICATION_SECTION_RE,
    write_completed_receipt,
    has_completion_receipt,
    skip_waiver_refusal,
    repo_has_no_app_surface,
    repo_uses_cognito_planner,
    phases_mcp_runtime_not_required,
    phases_spike_required,
    spike_verdict_is_pass,
    spec_status,
    commit_drift_verdict,
    observation_gap_promotable,
    _coerce_evidence_count,
)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _state(
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
    # Always include any diagnostics accumulated during this compute_state()
    # invocation (e.g. legacy plan files missing frontmatter). Callers may
    # also pass explicit diagnostics; both lists merge.
    # Reference lazy_core._DIAGNOSTICS — the canonical list owned by lazy_core.
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
        # Structured list of features the device axis deferred this probe (each
        # has DEFERRED_REQUIRES_DEVICE.md + no VALIDATED.md on a no-real-device
        # host). Always present so /lazy-status and orchestrators
        # can surface lingering In-progress device-deferrals deterministically,
        # not only when the queue exhausts. Mirrors _DIAGNOSTICS.
        "device_deferred_features": list(_DEVICE_DEFERRED),
        # host-capability-declaration-for-gated-features Phase 5: features the
        # host-capability axis deferred this probe (each has
        # DEFERRED_REQUIRES_HOST.md + no VALIDATED.md because ≥1 required
        # capability is absent on THIS host). Always present (mirrors
        # device_deferred_features) so orchestrators surface lingering
        # In-progress host-deferrals deterministically, not only at exhaustion.
        "host_deferred_features": list(_HOST_DEFERRED),
        # merged-head-oracle-per-signal-supplement-churn Phase 1: features the
        # operator parked via a bare DEFERRED.md this probe (the feature-side
        # mirror of bug-state.py's operator_deferred key). Always present so
        # /lazy-status + orchestrators surface lingering operator-deferred
        # features deterministically, not only at queue exhaustion.
        "operator_deferred": list(_OPERATOR_DEFERRED),
    }
    # CRITICAL INVARIANT: "parked" is ONLY included when _PARK_MODE is True.
    # When False the key must be entirely absent so default output (no flag) is
    # byte-identical to the pre-WU-1 Phase-4 baseline.
    if _PARK_MODE:
        out["parked"] = list(_PARKED)
    # park-provisional-acceptance (SPEC D11): the pending-ratification list is
    # ONLY included in park mode AND only when non-empty — default and plain
    # non-park output stays byte-identical (non-park probes surface provisional
    # state solely via the needs-ratification terminal).
    if _PARK_MODE and _PROVISIONAL:
        out["provisional"] = list(_PROVISIONAL)
    # feature-budget-guard-and-skip-ahead Phase 2: the budget_guard trip action is
    # ONLY surfaced when a trip actually fired this probe (_BUDGET_GUARD set). When
    # None the key is entirely absent so default output (no marker / no trip) stays
    # byte-identical to the pre-feature baseline — same discipline as "parked".
    if _BUDGET_GUARD is not None:
        out["budget_guard"] = dict(_BUDGET_GUARD)
    # feature-budget-guard-and-skip-ahead Phase 3: the gated heads skip-ahead
    # advanced PAST this probe are ONLY surfaced when skip-ahead actually skipped
    # at least one gated head (_GATED_HEADS non-empty). When empty the key is
    # entirely absent so default output (no gated head / --strict-research-halt)
    # stays byte-identical to the pre-Phase-3 baseline — same discipline as
    # "parked" / "budget_guard". The Phase-4 wrapper consumes it for the
    # end-of-run gated-head flush.
    if _GATED_HEADS:
        out["gated_heads"] = list(_GATED_HEADS)
    # research-gated-head-buried-by-skip-ahead-and-merged-fallthrough: the
    # RESEARCH-pending subset of the skipped gated heads (a subset of gated_heads
    # above). Same absent-when-empty discipline so default output stays
    # byte-identical; the --emit-prompt merged-head path reads it (via
    # lazy_core.dispatch.research_halt_head) to surface a needs-research halt when
    # a research head outranks the fallthrough the driver would otherwise dispatch.
    if _RESEARCH_GATED_HEADS:
        out["research_gated_heads"] = list(_RESEARCH_GATED_HEADS)
    # merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone: the
    # candidates skip-ahead skipped because they FAILED the two-key readiness
    # predicate (dep-unready / not independent) — surfaced ONLY when the walk
    # blocked at least one (_SKIP_AHEAD_BLOCKED non-empty). Absent-when-empty so
    # default output stays byte-identical — same discipline as "gated_heads". The
    # --emit-prompt merged-head exclude path reads it (via
    # lazy_core.dispatch.probe_skipped_ids) so the merged-head-diverged guard
    # cannot withhold the route pointing at a non-dispatchable dep-unready item.
    if _SKIP_AHEAD_BLOCKED:
        out["skip_ahead_blocked"] = list(_SKIP_AHEAD_BLOCKED)
    # queue-dependency-dag Phase 2 (D10): the items the dep-gate HELD this
    # probe — [{id, missing: [<incomplete dep ids>]}] — are ONLY surfaced when
    # the walk held at least one item (_DEP_GATED non-empty). When empty the
    # key is entirely absent so default output (no `deps` fields anywhere)
    # stays byte-identical — same discipline as "parked" / "gated_heads".
    # Pure-read consumers (pipeline_visualizer, lazy-queue-doc.py) can render
    # a "waiting on <dep>" state from this without re-inferring anything.
    if _DEP_GATED:
        out["dep_gated"] = [dict(r) for r in _DEP_GATED]
    # budget-guard-defers-near-complete-feature Phase 3: the end-of-run resume
    # flush auto-resumed a near-complete budget-deferred feature this probe. Only
    # surfaced when the flush actually resumed one (_BUDGET_RESUMED set) so default
    # output stays byte-identical to the pre-flush baseline — same discipline as
    # "budget_guard" / "gated_heads".
    if _BUDGET_RESUMED is not None:
        out["budget_resumed_near_complete"] = _BUDGET_RESUMED
    # guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual):
    # the REPORT-ONLY "guards executed 0 times this run" advisory, surfaced
    # ONLY when lazy_core.guard_plane_heartbeat() returned a verdict (None
    # before the marker/min-cycle threshold — default output byte-identical
    # on a fresh/short run). NEVER gates any route.
    if _GUARD_PLANE_HEARTBEAT is not None:
        out["guard_plane_heartbeat"] = dict(_GUARD_PLANE_HEARTBEAT)
    return out


def _scoped_skip_state(
    *,
    feature_id: str,
    feature_name: str,
    spec_path: Path,
    current_step: str,
    terminal_reason: str,
    notify_message: str,
) -> dict[str, Any]:
    """Build a scoped, identity-preserving _state for a --feature-id match that
    WOULD have been skipped by one of the feature-side "skipped-but-matched"
    branches (cloud-saturated / device-saturated / host-capability-deferred /
    parked).

    bug-state-scoped-query-loses-deferred-bug-identity, Phase 2 (feature-side
    parity twin of bug-state.py's Phase-1 _scoped_skip_state): the UNIFORM
    scoped-return shape across all the feature-side scoped skip branches. Each
    branch's UNSCOPED path (scope_feature_id is None) stays byte-identical — this
    helper is reached ONLY on a scoped match. Modeled on the completion-unverified
    scoped return that already returns a scoped _state from inside the queue loop.
    """
    return _state(
        feature_id=feature_id,
        feature_name=feature_name,
        spec_path=str(spec_path),
        current_step=current_step,
        terminal_reason=terminal_reason,
        notify_message=notify_message,
    )


# Device-deferred features observed this invocation (see _state()). Reset at the
# start of each compute_state() call alongside lazy_core._DIAGNOSTICS.
_DEVICE_DEFERRED: list[str] = []

# host-capability-declaration-for-gated-features Phase 5: host-capability-deferred
# features observed this invocation (the host-axis mirror of _DEVICE_DEFERRED).
# Each carries DEFERRED_REQUIRES_HOST.md (missing ≥1 required capability on THIS
# host) + no VALIDATED.md. Surfaced in the always-present host_deferred_features
# probe key so /lazy-status + orchestrators can flush lingering host-deferrals
# deterministically. _HOST_SATURATED holds the rich per-feature {feature_id,
# missing} records for the host-capability-saturated terminal's notification.
# Both reset at the start of each compute_state().
_HOST_DEFERRED: list[str] = []
_HOST_SATURATED: list[dict] = []

# merged-head-oracle-per-signal-supplement-churn Phase 1: operator-deferred
# features (a bare DEFERRED.md sentinel is present) observed this invocation —
# the feature-side mirror of bug-state.py's _OPERATOR_DEFERRED. Surfaced in the
# always-present operator_deferred probe key; when the queue exhausts to only
# these, the global all-remaining-deferred terminal fires. Reset at the start of
# each compute_state().
_OPERATOR_DEFERRED: list[str] = []

# Park mode: when True (--park-needs-input and/or --park-blocked flag),
# NEEDS_INPUT.md and/or feature-local BLOCKED.md items are skipped (parked)
# instead of halting. The parked items accumulate in _PARKED.
# Reset at the start of each compute_state() call, alongside _DEVICE_DEFERRED.
_PARKED: list = []
_PARK_MODE: bool = False

# park-provisional-acceptance: every NEEDS_INPUT_PROVISIONAL.md-bearing feature
# observed during this walk (entries via lazy_core.build_parked_entry,
# sentinel_kind == "provisional"). Surfaced in the park-mode-only
# `provisional[]` probe key (mirrors _PARKED's _PARK_MODE gating — SPEC D11)
# so status surfaces and the flush see pending ratifications without a
# filesystem re-scan. Reset at the start of each compute_state().
_PROVISIONAL: list = []

# feature-budget-guard-and-skip-ahead Phase 2: per-feature budget guard state for
# this compute_state() invocation. _DEFERRED_BUDGET accumulates the feature ids the
# guard deferred/evicted this probe (run-scoped skip-list, NOT written to
# queue.json). _BUDGET_GUARD holds the rich trip-action metadata surfaced into the
# probe JSON (None when no trip fired → the "budget_guard" key is absent, keeping
# default output byte-identical). Both reset at the start of each compute_state().
_DEFERRED_BUDGET: list = []
_BUDGET_GUARD: dict | None = None

# feature-budget-guard-and-skip-ahead Phase 3: skip-ahead state for this
# compute_state() invocation. _GATED_HEADS accumulates the gated (research-pending
# or BLOCKED) head feature ids that skip-ahead advanced PAST this probe — a
# run-scoped surfaced list (the Phase-4 end-of-run flush consumes it via the
# "gated_heads" probe key). Reset at the start of each compute_state(); the key is
# absent from default output (no gated head / --strict-research-halt) so byte-
# identity with the pre-Phase-3 baseline is preserved.
_GATED_HEADS: list = []

# research-gated-head-buried-by-skip-ahead-and-merged-fallthrough: the RESEARCH-
# pending subset of _GATED_HEADS (heads carrying RESEARCH_PROMPT.md / NEEDS_RESEARCH.md
# with no RESEARCH*.md — NOT BLOCKED heads). Surfaced as the "research_gated_heads"
# probe key so the --emit-prompt merged-head path can distinguish an operator-
# resolvable research gap (which must SURFACE a needs-research halt when it outranks
# the fallthrough target) from a BLOCKED head (which legitimately skips-ahead to
# independent ready work). Reset + cleared in lockstep with _GATED_HEADS; the key is
# absent when empty (byte-identity with the pre-fix baseline).
_RESEARCH_GATED_HEADS: list = []

# merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone: the candidates
# skip-ahead advanced PAST this probe because they FAILED the two-key readiness
# predicate (skip_ahead_ready — a hard dep on a skipped gated id, or not
# `independent: true`) — e.g. a dependency-gated milestone with unmet hard deps.
# Formerly a write-only local (`skip_ahead_blocked`) never surfaced, so
# lazy_core.dispatch.probe_skipped_ids could not fold it into the merged-head
# exclude set — letting the merged-head-diverged guard WITHHOLD the route pointing
# at a NON-dispatchable dep-unready item (null cycle_prompt AND null
# terminal_reason → no-route, observed live 2026-07-17 on
# 'prerelease-complete-milestone'). Now surfaced via the "skip_ahead_blocked" probe
# key (mirrors _GATED_HEADS: absent when empty; cleared in the gated_head_fallback
# branch where no skip is realized) and consumed by probe_skipped_ids. Reset at the
# start of each compute_state().
_SKIP_AHEAD_BLOCKED: list = []

# budget-guard-defers-near-complete-feature Phase 3: the feature_id the end-of-run
# resume flush auto-resumed this probe (None when the flush did not resume one →
# the "budget_resumed_near_complete" probe key is absent, keeping default output
# byte-identical). Reset at the start of each compute_state().
_BUDGET_RESUMED: str | None = None

# queue-dependency-dag Phase 2: the items the dep-gate held this invocation —
# [{id, missing: [<incomplete dep ids>]}], in walk order. Surfaced via the
# "dep_gated" probe key ONLY when non-empty (byte-identity discipline). Reset
# at the start of each compute_state().
_DEP_GATED: list = []

# guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual): the
# REPORT-ONLY "guards executed 0 times this run" advisory
# (lazy_core.guard_plane_heartbeat()'s verdict dict, or None). Surfaced via
# the "guard_plane_heartbeat" probe key ONLY when not None (byte-identity
# discipline — a fresh/short run's default output is unchanged). Recomputed
# at the start of each compute_state(); NEVER gates any route.
_GUARD_PLANE_HEARTBEAT: dict | None = None


# ---------------------------------------------------------------------------
# Host-capability probe (real audio output device present?)
# ---------------------------------------------------------------------------
#
# The framework now models THREE environments, not two:
#   - cloud                          (--cloud)            — no Tauri, no MCP, no device
#   - no-real-device workstation     (--real-device no)   — WSL2/CI: HeadlessPumpDriver
#   - real-device workstation        (--real-device yes)  — native Windows etc.: CpalOutputDriver
#
# The device axis is ORTHOGONAL to the cloud axis. It exists because some MCP
# audio assertions (sustained zero-dropout / timing-stability) can only be
# certified when a real hardware device callback drives the audio clock from a
# hardware interrupt — under AlgoBooth's HeadlessPumpDriver (a normal
# OS-scheduled thread) those metrics are non-deterministic. Such assertions are
# DEFERRED on a no-device host (DEFERRED_REQUIRES_DEVICE.md) and RE-OPENED on a
# real-device host, rather than permanently skipped.

# Standing override an operator sets on a real-device host (e.g. native Windows)
# so `--real-device auto` resolves correctly without the app running. Absent →
# treat as no-device (the conservative default: defer rather than fake-certify).
REAL_DEVICE_ENV = "ALGOBOOTH_REAL_AUDIO_DEVICE"

TR_STALE_UPSTREAM = "stale_upstream"
STEP_STALE_UPSTREAM = "Step 2.9: stale-upstream"

# ---------------------------------------------------------------------------
# Scoped per-feature deferred terminal_reason / current_step constants
# (bug-state-scoped-query-loses-deferred-bug-identity, Phase 2 — feature-side
# parity twin of bug-state.py's Phase-1 scoped literals).
#
# When a --feature-id scoped query matches an entry that WOULD have been skipped
# by one of the feature-side "skipped-but-matched" branches (cloud-saturated /
# device-saturated / host-capability-deferred / parked), compute_state returns a
# SCOPED, identity-preserving _state carrying the feature's own id + a per-feature
# deferred terminal_reason — instead of `continue`-ing into the global
# null-identity terminal (cloud-queue-exhausted / device-queue-exhausted /
# host-capability-saturated / queue-exhausted-all-parked).
#
# Parity with bug-state.py's literals where the axis matches
# (cloud/device/park/operator-defer); the feature side adds the host-capability
# axis (no bug-side analog). The operator-DEFERRED.md branch is now present on
# BOTH pipelines — the former feature/bug divergence was CLOSED by
# merged-head-oracle-per-signal-supplement-churn (the feature side gained the
# bare-DEFERRED.md skip the bug side already had).
# Part 3 (curated_stage.py) maps these literals VERBATIM:
#   cloud-queue-exhausted-scoped     → Deferred
#   device-queue-exhausted-scoped    → Deferred
#   host-capability-saturated-scoped → Deferred
#   blocked-scoped                   → Blocked
#   needs-input-scoped               → Needs-input
TR_CLOUD_DEFERRED_SCOPED = "cloud-queue-exhausted-scoped"
TR_DEVICE_DEFERRED_SCOPED = "device-queue-exhausted-scoped"
TR_HOST_DEFERRED_SCOPED = "host-capability-saturated-scoped"
# merged-head-oracle-per-signal-supplement-churn Phase 1: the feature-side
# operator-deferred literals, matching bug-state.py's exactly (a scoped
# --feature-id query on a DEFERRED.md feature returns its own identity + this
# scoped terminal; the global all-remaining-deferred terminal fires when only
# operator-deferred features remain). NOT registered in SANCTIONED_STOP_TERMINAL
# — matching the bug side, which does not register them either.
TR_OPERATOR_DEFERRED_SCOPED = "operator-deferred"
TR_ALL_DEFERRED = "all-remaining-deferred"
TR_BLOCKED_SCOPED = "blocked-scoped"
TR_NEEDS_INPUT_SCOPED = "needs-input-scoped"
# A --feature-id scoped query matching an entry that is ALREADY genuinely done
# (Superseded, or Complete+receipted) returns its OWN identity + this terminal
# instead of falling through to a global terminal with no identity attached
# (lazy-queue-doc-renders-bogus-rows-for-stale-complete-entries).
TR_COMPLETE_SCOPED = "feature-complete-scoped"
# park-provisional-acceptance: the non-park halt on an unratified
# NEEDS_INPUT_PROVISIONAL.md (Step 3.6) + its scoped park-mode twin.
TR_NEEDS_RATIFICATION = "needs-ratification"
TR_NEEDS_RATIFICATION_SCOPED = "needs-ratification-scoped"

# Scoped per-feature deferred current_step strings (kept GENERIC so the curated
# stage resolves from the terminal_reason, which dominates — NOT the step).
STEP_CLOUD_DEFERRED_SCOPED = "Cloud-deferred (scoped)"
STEP_DEVICE_DEFERRED_SCOPED = "Device-deferred (scoped)"
STEP_HOST_DEFERRED_SCOPED = "Host-capability-deferred (scoped)"
STEP_BLOCKED_PARKED_SCOPED = "Blocked, parked (scoped)"
STEP_NEEDS_INPUT_PARKED_SCOPED = "Needs-input, parked (scoped)"
STEP_COMPLETE_SCOPED = "Complete (scoped)"
STEP_NEEDS_RATIFICATION = "Step 3.6: needs-ratification"
STEP_PROVISIONAL_PARKED_SCOPED = "Provisional, parked (scoped)"
# merged-head-oracle-per-signal-supplement-churn Phase 1: the operator-deferred
# scoped current_step (kept GENERIC — the curated stage resolves from the
# terminal_reason, which dominates). Mirrors bug-state.py's
# STEP_OPERATOR_DEFERRED_SCOPED.
STEP_OPERATOR_DEFERRED_SCOPED = "Operator-deferred (scoped)"


def resolve_real_device(flag_value: str) -> bool:
    """Resolve whether the CURRENT host has a real audio output device.

    Kept deliberately simple and PURE so the smoke tests stay hermetic (they run
    with no audio hardware):

    - ``yes`` / ``no`` — explicit injection. Tests and the orchestrator (which
      probes the live backend via ``get_audio_mode`` — ``mode == cpal`` and not
      ``forced`` → a real device) pass these directly. This is the injectable
      path the SPEC requires: the AlgoBooth-specific cpal-vs-headless probe lives
      in the orchestrator, NOT baked into this generic state script.
    - ``auto`` — read the ``ALGOBOOTH_REAL_AUDIO_DEVICE`` env var (``1``/``true``
      → real device); ABSENT → ``False`` (no device). Conservative: an unknown
      host defers (safe) rather than claiming real-device (which would let a
      sustained-timing assertion fake-certify under the headless pump).

    We never key this on hostname or ``ALGOBOOTH_AUDIO_HEADLESS`` heuristics —
    those mirror device presence only indirectly. The orchestrator owns the real
    probe; this resolver just makes the result injectable + testable.
    """
    if flag_value == "yes":
        return True
    if flag_value == "no":
        return False
    # auto
    raw = os.environ.get(REAL_DEVICE_ENV, "")
    return raw == "1" or raw.strip().lower() == "true"


# parse_sentinel — imported from lazy_core


def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a
    git repo / git is unavailable. Best-effort — the freshness check is
    SKIPPED (behavior unchanged) when this returns None."""
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


# ---------------------------------------------------------------------------
# queue.json + ROADMAP.md
# ---------------------------------------------------------------------------

# Discovered-feature default tier rank: a feature SPEC with no parseable
# **Priority:** sorts AFTER every explicitly-prioritized one (P0..P3 → 0..3).
# Mirrors bug-state.py's _SEVERITY_DEFAULT (Low sorts last).
_FEATURE_TIER_DEFAULT = 99


def feature_tier(spec_path: Path) -> int:
    """Return the discovered-feature ordering rank from a SPEC.md ``**Priority:**``.

    ``spec_path`` is the SPEC.md FILE path (not the dir). Maps ``P0``→0 …
    ``P3``→3; an absent/unparseable Priority returns ``_FEATURE_TIER_DEFAULT``
    (sorts last). Used ONLY to order discovered on-disk entries — explicit
    queue.json entries keep their own ``tier`` and always sort first.

    Mirrors ``bug-state.py::bug_severity``'s header-line scan, but reads the
    ``**Priority:**`` line and maps it to an int rank in one step (the feature
    pipeline orders by an int ``tier``, where the bug pipeline orders by a
    severity-string rank — the JUSTIFIED feature/bug divergence noted in the
    SPEC's Coupling Rule).
    """
    if not spec_path.exists():
        return _FEATURE_TIER_DEFAULT
    try:
        for line in spec_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\*\*Priority:\*\*\s*[Pp]([0-3])\b", line)
            if m:
                return int(m.group(1))
    except OSError:
        pass
    return _FEATURE_TIER_DEFAULT


def _find_open_feature_dirs(
    features_dir: Path, queued_ids: set[str]
) -> list[Path]:
    """Return on-disk open feature dirs NOT already in ``queued_ids``.

    Structurally mirrors ``bug-state.py::_find_open_bug_dirs`` (the
    feature-pipeline analog): scans ``features_dir`` one level deep, skips
    non-dirs, underscore-prefixed dirs (``_archive/`` etc.), and any dir whose
    name is already a queued id; requires a ``SPEC.md``; and applies the
    completed-feature exclusion filter with receipt awareness:

      - ``Superseded`` → always skipped (retired, receipt-exempt).
      - ``Complete`` WITH a valid ``COMPLETED.md`` receipt → skipped (done).
      - ``Complete`` WITHOUT a valid receipt → NOT skipped; surfaced so the
        ``compute_state`` queue-walk receipt gate fires ``completion-unverified``
        (a ``_diag`` flags the bypass), exactly as ``_find_open_bug_dirs``
        surfaces a receiptless ``Fixed``.

    Returns dirs sorted by ``(feature_tier(SPEC.md), dir name)`` — stable.

    NOTE: the parameter is the features_dir (docs/features/), NOT the repo root.
    """
    if not features_dir.exists():
        return []

    candidates: list[tuple[int, str, Path]] = []
    for child in features_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            # Skip _archive/ and any other underscore-prefixed dirs.
            continue
        if child.name in queued_ids:
            # Already covered by the explicit queue.
            continue
        spec_md = child / "SPEC.md"
        if not spec_md.exists():
            continue
        status = spec_status(child)
        if status == "Superseded":
            # Receipt-exempt: retired without completion — always skip.
            continue
        if status == "Complete":
            if has_completion_receipt(child):
                # Genuinely done: Complete with a valid COMPLETED.md receipt.
                continue
            # Complete WITHOUT receipt: do NOT silently skip. Surface this dir so
            # the queue-walk receipt gate in compute_state fires
            # completion-unverified — same as the queued-feature path.
            _diag(
                f"unqueued Complete-without-receipt dir surfaced for receipt "
                f"gate: '{child.name}' — SPEC marks Complete but no valid "
                "COMPLETED.md receipt found. Routing to completion gate "
                "(completion-unverified)."
            )
            # Fall through to append into candidates below.
        candidates.append((feature_tier(spec_md), child.name, child))

    candidates.sort(key=lambda t: (t[0], t[1]))
    return [c[2] for c in candidates]


def _queue_autodiscover_enabled(repo_root: Path) -> bool:
    """True iff docs/features/queue.json carries a top-level ``autodiscover: true``.

    Read-only, defensive (a missing/malformed queue.json ⇒ False). Used by
    ``compute_state`` to distinguish a genuinely-missing/empty queue (→
    ``queue-missing``) from an autodiscover-enabled queue that simply has no
    OPEN on-disk dirs (→ falls through to ``all-features-complete``).
    """
    queue_path = repo_root / "docs" / "features" / "queue.json"
    if not queue_path.exists():
        return False
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return data.get("autodiscover") is True


def load_queue(repo_root: Path) -> list[dict[str, Any]]:
    queue_path = repo_root / "docs" / "features" / "queue.json"
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid queue.json: {exc}", queue_path)
        return []  # pragma: no cover
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("queue.json 'queue' field must be an array", queue_path)
        return []  # pragma: no cover

    # queue-dependency-dag Phase 1: validate the optional per-entry `deps`
    # field (shape + id regex + reserved bug:/feature: prefixes + cycle
    # detection via Kahn's) BEFORE any merge. A dep-less queue is a silent
    # no-op (byte-identical); a broken declared graph _die()s exit 2 like the
    # other queue-schema violations above.
    lazy_core.validate_queue_deps(items, queue_path, queue_label="queue.json")

    # feature-queue-lacks-on-disk-autodiscovery: opt-in on-disk auto-discovery.
    # When docs/features/queue.json carries a top-level "autodiscover": true flag
    # (sibling of "queue"), merge on-disk open feature dirs NOT already queued —
    # exactly mirroring how bug-state.py::load_bug_queue merges _find_open_bug_dirs.
    # The merge is a PROBE-TIME, in-memory operation: nothing is ever written into
    # queue.json. Flag absent/falsy ⇒ return the raw queue list UNCHANGED
    # (byte-identical — every other repo, incl. AlgoBooth, is unaffected).
    if data.get("autodiscover") is True:
        queued_ids = {
            e.get("id") for e in items if isinstance(e, dict) and e.get("id")
        }
        features_dir = repo_root / "docs" / "features"
        discovered: list[dict[str, Any]] = []
        for child in _find_open_feature_dirs(features_dir, queued_ids):
            spec_md = child / "SPEC.md"
            # Discovered entry name: SPEC '# ' title, falling back to the dirname.
            name = child.name
            if spec_md.exists():
                try:
                    for line in spec_md.read_text(encoding="utf-8").splitlines():
                        m = re.match(r"^#\s+(.+?)\s*$", line)
                        if m:
                            name = m.group(1)
                            break
                except OSError:
                    pass
            # The discovered entry carries the RAW-queue-item key shape
            # (id/name/spec_dir/tier) the compute_state walk loop reads directly
            # (entry.get("spec_dir") / entry.get("tier")) — NOT the bug loader's
            # normalized spec_path shape (the two loaders' return shapes
            # legitimately differ).
            discovered.append({
                "id": child.name,
                "name": name,
                "spec_dir": child.name,
                "tier": feature_tier(spec_md),
                "queue_entry": None,
            })
        return items + discovered

    return items


def _load_bug_queue_for_merged(repo_root: Path) -> list[dict[str, Any]]:
    """Load docs/bugs/queue.json items for the merged work-list via the
    EXISTING ``bug-state.py:load_bug_queue`` loader (not a hand-reparse).

    bug-state.py is a hyphenated module so a plain ``import`` won't resolve;
    load it from its sibling path with importlib. The returned entries each
    carry at least ``id`` and ``severity`` — exactly what ``merged_priority``
    needs. Best-effort: if bug-state.py is missing/unloadable, return [] so the
    merged view degrades to features-only rather than crashing (the unified
    driver in a feature-only repo must still get its feature head).
    """
    import importlib.util

    bug_state_path = Path(__file__).parent / "bug-state.py"
    if not bug_state_path.exists():
        return []
    try:
        spec = importlib.util.spec_from_file_location(
            "_bug_state_for_merged", str(bug_state_path)
        )
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.load_bug_queue(repo_root)
    except Exception as exc:  # noqa: BLE001 — degrade to features-only on load error
        # item-3 (lazy-batch-unified-driver-parity-and-accounting Phase 2): a bug-
        # side load failure used to degrade SILENTLY (bare-except → []), hiding a
        # real bug from the merged view with no diagnostic. Emit a breadcrumb so
        # the failure is observable in merged-view diagnostics, then STILL fail
        # open (return []) so a feature-only repo's merged head is unaffected.
        _diag(
            f"merged-view bug-side load failed ({exc}) — degrading to features-only"
        )
        return []


_BUG_STATE_MODULE_CACHE: dict = {}


def _load_bug_state_module():
    """Load ``bug-state.py`` as a module (cached), or ``None`` when unavailable.

    The importlib precedent from :func:`_load_bug_queue_for_merged`, reused by
    the merged-head actionability oracle (merged-head-actionability-oracle) so
    the ``--emit-prompt`` merged-override site can run the REAL cross-pipeline
    scoped ``bug-state.compute_state`` per candidate. Cached module-level so the
    (large) script body is exec'd at most once per process. Best-effort: a
    missing/unloadable ``bug-state.py`` returns ``None`` — the oracle then treats
    every cross candidate as non-dispatchable (fail toward EMITTING the workable
    item, never toward a spurious withhold)."""
    if "mod" in _BUG_STATE_MODULE_CACHE:
        return _BUG_STATE_MODULE_CACHE["mod"]
    import importlib.util

    mod = None
    bug_state_path = Path(__file__).parent / "bug-state.py"
    if bug_state_path.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                "_bug_state_for_oracle", str(bug_state_path)
            )
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
        except Exception:  # noqa: BLE001 — degrade to None (features-only) on load error
            mod = None
    _BUG_STATE_MODULE_CACHE["mod"] = mod
    return mod


def enqueue_adhoc(
    repo_root: Path,
    feature_id: str,
    name: str,
    brief: str,
    spec_dir: str | None = None,
    tier: int = 0,
    stub: bool = False,
    at: str = "head",
    deps: list[str] | None = None,
) -> dict[str, Any]:
    """Insert an ad-hoc feature at the TOP of docs/features/queue.json.

    Deterministic bootstrap for the /lazy ad-hoc path: prepends a queue entry
    (so the next state probe picks it first), creates the spec dir, seeds
    ADHOC_BRIEF.md (which Step 4 routes to /spec), and adds a ROADMAP.md row.
    queue.json / ROADMAP.md are created if absent so ad-hoc works in a fresh
    repo. Idempotent on the brief/dir; refuses a duplicate feature_id.

    toolify-auto-promotion Phase 2 (D4-B), additive default-off params:
    ``stub=True`` adds ``"stub": true`` to the queue entry (the Step-4.5
    cross-check flag; the key is OMITTED otherwise so the default entry stays
    byte-identical to before); ``at="tail"`` appends instead of prepending
    (promotions ride normal roadmap order rather than jumping the curated
    queue). Feature-pipeline-only — the bug pipeline has no stub step and
    orders by severity, so ``bug-state.py`` deliberately has no mirror
    (justified divergence; un-audited by ``lazy_parity_audit.py``).

    queue-dependency-dag Phase 4: an optional ``deps`` id list (the
    ``--enqueue-adhoc --deps a,b`` surface) lets an ad-hoc item declare hard
    queue deps at enqueue time without waiting for ``/spec-phases`` to run
    ``--sync-deps``. Validated up front (regex + reserved ``bug:``/``feature:``
    prefixes → ``_die``, zero side effects); omitted ⇒ the entry shape is
    byte-identical to before.
    """
    repo_root = repo_root.resolve()
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", feature_id):
        _die(f"invalid feature_id (must be kebab-case): {feature_id!r}")
    if deps:
        lazy_core.validate_dep_id_list(
            deps, context=f"'--deps' (enqueue {feature_id!r})"
        )
    features = repo_root / "docs" / "features"
    features.mkdir(parents=True, exist_ok=True)
    spec_dir = spec_dir or feature_id

    queue_path = features / "queue.json"
    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _die(f"invalid queue.json: {exc}", queue_path)
            return {}  # pragma: no cover
    else:
        data = {"queue": []}
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("queue.json 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover
    if any(isinstance(e, dict) and e.get("id") == feature_id for e in items):
        _die(f"feature_id already queued: {feature_id}", queue_path)
        return {}  # pragma: no cover

    entry: dict[str, Any] = {
        "id": feature_id,
        "name": name,
        "spec_dir": spec_dir,
        "tier": tier,
        "adhoc": True,
    }
    if stub:
        entry["stub"] = True
    if deps:
        # queue-dependency-dag: the optional hard-deps declaration. Key absent
        # when not supplied — byte-identical legacy entry shape.
        entry["deps"] = list(deps)
    if at == "tail":
        items.append(entry)
        queue_position = len(items) - 1
    else:
        items.insert(0, entry)
        queue_position = 0
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")

    spec_path = (features / spec_dir).resolve()
    spec_path.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    brief_file = spec_path / "ADHOC_BRIEF.md"
    if not brief_file.exists():
        _atomic_write(
            brief_file,
            "---\n"
            "kind: adhoc-brief\n"
            f"feature_id: {feature_id}\n"
            "enqueued_by: lazy-adhoc\n"
            f"date: {today}\n"
            "---\n\n"
            f"# Ad-hoc task: {name}\n\n"
            f"{brief.strip() or '(brief not supplied — infer from context during /spec)'}\n",
        )

    roadmap = features / "ROADMAP.md"
    row = f"- {name} — (ad-hoc, enqueued {today})\n"
    if roadmap.exists():
        text = roadmap.read_text(encoding="utf-8")
        if name not in text:
            if text and not text.endswith("\n"):
                text += "\n"
            _atomic_write(roadmap, text + row)
    else:
        _atomic_write(roadmap, "# Roadmap\n\n" + row)

    return {
        "enqueued": True,
        "feature_id": feature_id,
        "feature_name": name,
        "spec_path": str(spec_path),
        "brief_path": str(brief_file),
        "queue_position": queue_position,
        "queue_length": len(items),
    }


def enqueue_adhoc_bug(
    repo_root: Path,
    bug_id: str,
    name: str,
    brief: str = "",
    spec_dir: str | None = None,
    severity: str | None = None,
    deps: list[str] | None = None,
) -> dict[str, Any]:
    """Route an ad-hoc item into docs/bugs/queue.json (the bug pipeline).

    unified-pipeline-orchestrator Phase 3: the `--type bug` path of the shared
    ad-hoc enqueue surface. The queue entry is written by the EXISTING
    ``bug-state.py --enqueue-adhoc`` (which already writes a ``spec_dir``-keyed
    ``docs/bugs/queue.json`` entry — fixtures 12/13) — we do NOT reimplement it.
    This wrapper adds the bug-doc seeding (``docs/bugs/<slug>/ADHOC_BRIEF.md``)
    around that subprocess call, mirroring ``materialize_wi``'s bug route.

    Idempotent: a second call with the same id is a no-op (bug-state.py's
    enqueue skips a duplicate id without raising; the brief is only seeded when
    absent), so this never raises on a duplicate.
    """
    repo_root = repo_root.resolve()
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", bug_id):
        _die(f"invalid bug_id (must be kebab-case): {bug_id!r}")
    spec_dir = spec_dir or bug_id
    bugs_dir = repo_root / "docs" / "bugs"
    bugs_dir.mkdir(parents=True, exist_ok=True)

    # Call bug-state.py --enqueue-adhoc via subprocess (idempotent skip-on-dup).
    # Mirrors materialize_wi's bug route: assert LAZY_ORCHESTRATOR=1 in the child
    # env so the C3 guard does not refuse this legitimate orchestrator-side
    # enqueue when an ambient cycle marker is present (hermetic against a marker).
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "bug-state.py"),
        "--enqueue-adhoc",
        "--id", bug_id,
        "--name", name,
        "--spec-dir", spec_dir,
        "--repo-root", str(repo_root),
    ]
    if severity:
        cmd += ["--severity", severity]
    if deps:
        # queue-dependency-dag Phase 4: forward the deps declaration to the
        # bug-state enqueue (which validates + stores it on the entry).
        cmd += ["--deps", ",".join(deps)]
    _enqueue_env = {**os.environ, "LAZY_ORCHESTRATOR": "1"}
    # Flush our buffered stdout/stderr BEFORE the child inherits the fds: when
    # stdout is a pipe (CI, pytest capture) the parent's buffered lines would
    # otherwise land AFTER the child's direct writes, making merged-output
    # ordering platform-dependent (the --test baseline pins one order).
    sys.stdout.flush()
    sys.stderr.flush()
    subprocess.run(cmd, check=True, env=_enqueue_env)

    # Seed the bug-doc shape: docs/bugs/<slug>/ADHOC_BRIEF.md (idempotent).
    item_dir = bugs_dir / spec_dir
    item_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    brief_file = item_dir / "ADHOC_BRIEF.md"
    if not brief_file.exists():
        _atomic_write(
            brief_file,
            "---\n"
            "kind: adhoc-brief\n"
            f"bug_id: {bug_id}\n"
            "enqueued_by: lazy-adhoc\n"
            f"date: {today}\n"
            "---\n\n"
            f"# Ad-hoc bug: {name}\n\n"
            f"{brief.strip() or '(brief not supplied — infer from context during /spec-bug)'}\n",
        )

    return {
        "enqueued": True,
        "bug_id": bug_id,
        "bug_name": name,
        "spec_dir": spec_dir,
        "brief_path": str(brief_file),
        "queue": "docs/bugs/queue.json",
    }


def materialize_wi(repo_root: Path, wi_id, type_pipeline_map: dict) -> dict:
    """Materialize an ADO work item from ado-mirror.json into a doc pipeline.

    Routes by WI type:
      - feature types  → docs/features/<slug> via enqueue_adhoc
      - bug types      → docs/bugs/<slug> via bug-state.py --enqueue-adhoc subprocess
      - unknown types  → skip (no dirs, no queue entry, no materialized record)

    Idempotent: a double-call on the same wi_id yields exactly one queue entry
    and one materialized record.
    """
    repo_root = repo_root.resolve()
    mirror_path = repo_root / "docs" / "work" / "ado-mirror.json"
    try:
        mirror_data = json.loads(mirror_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _diag(f"materialize_wi: cannot load mirror: {exc}")
        return {"status": "skipped", "reason": "mirror-load-error"}

    wi = None
    for item in mirror_data.get("workItems", []):
        if item.get("id") == wi_id:
            wi = item
            break
    if wi is None:
        _diag(f"materialize_wi: wi_id={wi_id} not found in mirror")
        return {"status": "skipped", "reason": "not-in-mirror"}

    wi_type = wi.get("type", "")
    title = wi.get("title", "")
    description = wi.get("description", "")
    ac = wi.get("acceptanceCriteria", "")
    url = wi.get("url", "")
    changed_date = wi.get("changedDate", "")

    feature_types = type_pipeline_map.get("feature", [])
    bug_types = type_pipeline_map.get("bug", [])

    if wi_type in feature_types:
        route = "feature"
    elif wi_type in bug_types:
        route = "bug"
    else:
        _diag(f"materialize_wi: unknown WI type {wi_type!r} for wi_id={wi_id}")
        return {"status": "skipped", "reason": "unknown-type"}

    # Build slug: kebab-case from title
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug or not re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
        slug = f"wi-{wi_id}"

    # Verbatim brief combining title, description, and acceptance criteria
    brief = f"Title: {title}\n\nDescription: {description}\n\nAcceptance Criteria: {ac}"

    if route == "feature":
        features_dir = repo_root / "docs" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        queue_path = features_dir / "queue.json"
        # Idempotency guard: skip enqueue_adhoc if already queued
        already_queued = False
        if queue_path.exists():
            try:
                qdata = json.loads(queue_path.read_text(encoding="utf-8"))
                if any(isinstance(e, dict) and (e.get("id") == slug or e.get("spec_dir") == slug)
                       for e in qdata.get("queue", [])):
                    already_queued = True
            except json.JSONDecodeError:
                pass
        if not already_queued:
            enqueue_adhoc(repo_root, slug, title, brief=brief, spec_dir=slug)
        # Ensure ADHOC_BRIEF.md contains all verbatim substrings
        brief_file = features_dir / slug / "ADHOC_BRIEF.md"
        brief_file.parent.mkdir(parents=True, exist_ok=True)
        if not brief_file.exists():
            _atomic_write(brief_file, f"# Ad-hoc task: {title}\n\n{brief}")
        else:
            existing = brief_file.read_text(encoding="utf-8")
            missing = [s for s in [title, description, ac] if s and s not in existing]
            if missing:
                augmented = existing.rstrip("\n") + "\n\n" + "\n".join(missing) + "\n"
                _atomic_write(brief_file, augmented)
        item_dir = features_dir / slug

    else:  # bug route
        bugs_dir = repo_root / "docs" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        # Call bug-state.py --enqueue-adhoc via subprocess (idempotent skip-on-dup).
        # cycle-subagent-runs-orchestrator-work Phase 1/2: materialize is an
        # orchestrator-side enqueue, so assert LAZY_ORCHESTRATOR=1 in the child
        # env. Without it, a --enqueue-adhoc subprocess inherits a live cycle
        # marker from whatever context is running (e.g. lazy-state.py --test
        # invoked from within a cycle subagent) and the C3 guard refuses (exit 3),
        # failing this legitimate orchestrator op. This makes the call hermetic
        # against an ambient marker.
        _materialize_env = {**os.environ, "LAZY_ORCHESTRATOR": "1"}
        # Flush before the child inherits the fds (see _enqueue_bug's twin flush:
        # keeps parent/child merged-output ordering platform-deterministic).
        sys.stdout.flush()
        sys.stderr.flush()
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "bug-state.py"),
                "--enqueue-adhoc",
                "--id", slug,
                "--name", title,
                "--spec-dir", slug,
                "--repo-root", str(repo_root),
            ],
            check=True,
            env=_materialize_env,
        )
        item_dir = bugs_dir / slug
        item_dir.mkdir(parents=True, exist_ok=True)
        # Write ADHOC_BRIEF.md (idempotent — only if absent)
        brief_file = item_dir / "ADHOC_BRIEF.md"
        if not brief_file.exists():
            _atomic_write(brief_file, f"# Ad-hoc task: {title}\n\n{brief}")

    # Both routes: write stub SPEC.md (idempotent — only if absent)
    spec_file = item_dir / "SPEC.md"
    if not spec_file.exists():
        _atomic_write(spec_file, f"**Work Item:** AB#{wi_id} ({url})\n")

    # Both routes: record in materialized.json (idempotent on wi_id)
    work_dir = repo_root / "docs" / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    lazy_core.append_materialized(work_dir, wi_id, slug, changed_date)

    return {
        "status": "materialized",
        "feature_id": slug,
        "route": route,
        "wi_id": wi_id,
    }


def check_stale_upstream(repo_root: Path, mirror: dict | None = None) -> list:
    """Scan materialized.json vs ado-mirror.json; write STALE_UPSTREAM.md where upstream changed.

    For each materialized record, compares mirror WI changedDate with the
    materialized_changedDate. ISO-8601 UTC timestamps sort lexically, so a
    simple string comparison suffices. Writes STALE_UPSTREAM.md into the
    item dir (docs/features/<feature_id>/ or docs/bugs/<feature_id>/) for
    any stale item. Does NOT touch SPEC.md.

    Returns the list of stale-item dicts (wi_id, feature_id).
    """
    repo_root = repo_root.resolve()
    work_dir = repo_root / "docs" / "work"
    records = lazy_core.read_materialized(work_dir)

    if mirror is None:
        mirror_path = work_dir / "ado-mirror.json"
        try:
            mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _diag(f"check_stale_upstream: cannot load mirror: {exc}")
            return []

    # Build a lookup by wi_id from the mirror
    mirror_by_id: dict[Any, dict] = {}
    for wi in mirror.get("workItems", []):
        mirror_by_id[wi.get("id")] = wi

    stale: list[dict] = []
    for record in records:
        wi_id = record.get("wi_id")
        feature_id = record.get("feature_id")
        materialized_date = record.get("materialized_changedDate", "")

        mirror_wi = mirror_by_id.get(wi_id)
        if mirror_wi is None:
            continue

        mirror_date = mirror_wi.get("changedDate", "")
        if mirror_date > materialized_date:
            # Find the item directory (features first, then bugs)
            feat_dir = repo_root / "docs" / "features" / feature_id
            bug_dir = repo_root / "docs" / "bugs" / feature_id
            if feat_dir.is_dir():
                item_dir = feat_dir
            elif bug_dir.is_dir():
                item_dir = bug_dir
            else:
                _diag(
                    f"check_stale_upstream: no dir found for feature_id={feature_id!r}; skipping"
                )
                continue
            diff = (
                f"Upstream WI {wi_id} changed on {mirror_date} "
                f"(materialized: {materialized_date}) — re-materialize required.\n"
            )
            lazy_core.write_stale_upstream(item_dir, diff)
            stale.append({"wi_id": wi_id, "feature_id": feature_id})

    return stale


# spec_status — imported from lazy_core


def roadmap_marks_complete(roadmap_text: str, feature_name: str) -> bool:
    """Fallback completion signal: a ROADMAP.md row mentioning the feature with
    both `~~` strikethrough AND the `COMPLETE` token. Retained for repos that
    don't follow the SPEC.md status convention.

    Anchoring: we extract the text inside the first `~~...~~` pair on the line,
    take the portion before any ` — ` (space–em-dash–space) separator (which
    separates the feature name from its description), trim whitespace, and compare
    case-insensitively for EQUALITY with feature_name. This prevents a strict
    substring like "Audio" from matching an unrelated completed row whose name is
    "Audio Engine". Word-boundary anchors are insufficient here because `\bAudio\b`
    still matches within "Audio Engine".

    ROADMAP row grammar this match relies on:
      ~~<Feature Name> — <description>~~ ... **COMPLETE**
      ~~<Feature Name>~~ ... **COMPLETE**   (no description variant)
    The extracted token is the text before the first ` — ` (or the full strikethrough
    text if no separator is present), trimmed of surrounding whitespace.  Comparison
    is case-insensitive EQUALITY against feature_name — so a feature whose name is a
    prefix or substring of a different completed row (e.g. "Audio" vs "Audio Engine")
    does NOT produce a false match.
    """
    if not roadmap_text:
        return False
    # Matches the content inside the first ~~...~~ on a line.
    strikethrough_re = re.compile(r"~~([^~]+)~~")
    for line in roadmap_text.splitlines():
        if "~~" not in line or "COMPLETE" not in line:
            continue
        m = strikethrough_re.search(line)
        if not m:
            continue
        # The strikethrough text is "Name — description"; take the name portion.
        struck_text = m.group(1)
        struck_name = struck_text.split(" — ")[0].strip()
        if struck_name.lower() == feature_name.lower():
            return True
    return False


# has_completion_receipt — imported from lazy_core


def completion_claimed(
    roadmap_text: str,
    feature_name: str,
    spec_path: Path | None = None,
) -> bool:
    """True iff the feature CLAIMS completion — SPEC.md `**Status:**` is
    `Complete`/`Superseded`, OR the ROADMAP strikethrough+COMPLETE fallback
    matches.

    A *claim* is not *proof*: a cycle subagent (or a hand edit) can flip
    `**Status:** Complete` outside the validation gate. `has_completion_receipt()`
    is the companion check that distinguishes a gated completion from a claimed
    one. Step 2 uses both: claimed + receipt → genuinely done (skip);
    claimed (Complete) without receipt → `completion-unverified` hard-halt.
    `Superseded` is exempt from the receipt requirement (a retired feature was
    never validated and never should be).
    """
    status = spec_status(spec_path)
    if status in ("Complete", "Superseded"):
        return True
    return roadmap_marks_complete(roadmap_text, feature_name)


# write_completed_receipt — imported from lazy_core


def backfill_receipts(repo_root: Path) -> dict[str, Any]:
    """One-shot migration: write a COMPLETED.md (provenance:
    backfilled-unverified) for every queue feature that currently CLAIMS
    completion but lacks a receipt.

    Grandfathers in features completed before receipt-gating shipped so they
    don't trip the `completion-unverified` hard-halt (in lazy-state.py) or the
    `spec-complete-requires-receipt` lint rule, while truthfully labeling them as
    never-gate-verified.

    Walks EVERY on-disk `SPEC.md` under `docs/features/` (excluding `_archive/`)
    whose `**Status:**` is `Complete` — NOT just queued features. The receipt is
    a repo-wide audit artifact: many shipped features have been dequeued, so a
    queue-only walk would leave them receiptless and tripping the repo lint.
    `Superseded` specs are exempt (retired, never validated). The feature_id is
    the SPEC directory basename.
    """
    repo_root = repo_root.resolve()
    features_root = repo_root / "docs" / "features"
    today = datetime.now().strftime("%Y-%m-%d")
    written: list[str] = []
    skipped_superseded: list[str] = []
    if not features_root.exists():
        return {"backfilled": [], "count": 0, "skipped_superseded": []}
    for spec_md in sorted(features_root.glob("**/SPEC.md")):
        # Skip archived specs.
        if "_archive" in spec_md.parts:
            continue
        spec_dir = spec_md.parent
        status = spec_status(spec_dir)
        if status == "Superseded":
            skipped_superseded.append(spec_dir.name)
            continue
        if status != "Complete":
            continue
        receipt = spec_dir / "COMPLETED.md"
        if receipt.exists():
            continue
        write_completed_receipt(
            receipt, spec_dir.name, today,
            provenance="backfilled-unverified",
            body_note=(
                "Grandfathered during the receipt-gating rollout. This feature "
                "was marked Complete BEFORE the completion-integrity gate existed, "
                "so its pipeline validation (MCP / retro) was NOT verified by the "
                "gate. Treat as completed-but-unverified; re-validate if its "
                "behavior is load-bearing."
            ),
        )
        written.append(spec_dir.name)
    return {
        "backfilled": written,
        "count": len(written),
        "skipped_superseded": skipped_superseded,
    }


# ---------------------------------------------------------------------------
# SPEC parsing
# ---------------------------------------------------------------------------

def _spec_text_has_stub_marker(spec_text: str) -> bool:
    """True iff the SPEC body carries an in-SPEC stub marker.

    Factored out of ``is_stub_spec`` so BOTH that function AND the Step-4.5
    lone-surviving-marker discriminator (``_stub_is_queue_flag_only``) test the
    EXACT same SPEC-text conditions — no duplicated marker list
    (stub-spec-route-loops-until-queue-stub-cleared).

    The SPEC-text markers (unlike the ``queue.json`` flag) live IN the SPEC, so
    they self-clear when ``/spec`` Phase 1 rewrites the SPEC into a structured
    baseline. The matched forms:
    - Legacy markers (`**Status:** Draft (research stub)`,
      `> Stub generated from advanced feature research`) — back-compat.
    - Canonical pre-Gemini marker `Draft (pre-Gemini)`, anchored to the
      **Status:** line OR a `>` blockquote so arbitrary inline prose mentions
      do NOT false-positive.
    """
    if "**Status:** Draft (research stub)" in spec_text:
        return True
    if "> Stub generated from advanced feature research" in spec_text:
        return True
    # Anchor the pre-Gemini stub check so it does NOT fire on arbitrary prose
    # mentions of the phrase "Draft (pre-Gemini)". We match two structural forms:
    #   (a) The **Status:** line's value contains "Draft (pre-Gemini)" — e.g.
    #       `**Status:** Draft (pre-Gemini)` as a first-class status value.
    #   (b) A blockquote line beginning with `>` contains "Draft (pre-Gemini)" —
    #       e.g. `> Draft (pre-Gemini). Open questions ...` which is the canonical
    #       stub trailer format used in older SPECs (kept for back-compat).
    # Normal inline prose ("Unlike a Draft (pre-Gemini) stub, this spec ...") does
    # NOT start with `>` and does NOT appear on the **Status:** line, so it is
    # excluded. This prevents a false-positive stub classification for researched
    # specs that merely discuss the concept.
    if re.search(r"^\s*\*\*Status:\*\*\s*.*Draft \(pre-Gemini\)", spec_text, re.MULTILINE):
        return True
    if re.search(r"^\s*>.*Draft \(pre-Gemini\)", spec_text, re.MULTILINE):
        return True
    return False


def is_stub_spec(spec_text: str, queue_entry: dict[str, Any] | None = None) -> bool:
    """Detect stub-spec markers per /lazy Step 4.5.

    A SPEC is a stub iff any of these match:
    - A SPEC-text stub marker (legacy `Draft (research stub)` / pre-Gemini
      trailer — see ``_spec_text_has_stub_marker``).
    - `queue_entry.get("stub") is True` — the queue.json cross-check (per
      AlgoBooth docs/CLAUDE.md). Triggers stub mode even when the SPEC trailer
      is absent.

    Stub mode routes to interactive /spec at Step 4.5; the baseline doesn't
    exist yet and needs design conversation. Structured-but-research-pending
    specs (no stub markers, missing RESEARCH.md) are a different state — they
    halt at Step 5 with needs-research and wait for a Gemini upload.
    """
    if _spec_text_has_stub_marker(spec_text):
        return True
    if queue_entry is not None and queue_entry.get("stub") is True:
        return True
    return False


def _stub_is_queue_flag_only(
    spec_text: str, queue_entry: dict[str, Any] | None
) -> bool:
    """True iff the queue.json `"stub"` flag is the LONE surviving stub marker.

    The Step-4.5 clear-and-advance discriminator
    (stub-spec-route-loops-until-queue-stub-cleared): after a `/spec` Phase 1
    cycle shapes the baseline, the SPEC-text stub markers are gone (the rewrite
    drops them) but the `queue.json` flag survives. That post-baseline state —
    queue flag True AND no SPEC-text marker — is reachable ONLY after a
    baseline-shaping cycle, so it is the deterministic "baseline locked" signal.
    Returns False on a TRUE pre-baseline stub (a SPEC-text marker still present),
    so the clear never fires before the baseline is shaped.
    """
    return (
        queue_entry is not None
        and queue_entry.get("stub") is True
        and not _spec_text_has_stub_marker(spec_text)
    )


# parse_dep_block RELOCATED to lazy_core.py (queue-dependency-dag D9) so both
# state scripts share ONE dep-block parser. Re-exported here so the Step 4.6
# realign check, the skip-ahead branch, and the smoke fixtures keep their
# existing call sites unchanged.
parse_dep_block = lazy_core.parse_dep_block


def _merged_skip_ahead_deps(
    spec_deps: list[dict[str, str]], queue_dep_ids: list[str]
) -> list[dict[str, str]]:
    """queue-dependency-dag Phase 3 (D7): merge the skip-ahead key-1 inputs.

    Returns SPEC-parsed deps (tagged ``source: spec``) followed by the queue
    ``deps`` ids (tagged ``source: queue``, treated as ``hard`` per D1's field
    semantics — the queue field IS the hard-only enforcement projection),
    deduped by feature_id (SPEC wins). ``skip_ahead_ready`` ignores the extra
    ``source`` key — it exists for the audit ``_diag`` line.

    Strictly-additive defense-in-depth: at the current walk order the Phase-2
    dep-gate holds a queue-deps-on-incomplete candidate BEFORE the skip-ahead
    branch evaluates it, so this union changes no outcome today — it guards
    the readiness predicate against any future re-ordering of the walk's
    branches (a SPEC authored before --sync-deps runs stays visible via the
    spec side; a synced queue field stays visible even if the SPEC block is
    later edited).
    """
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for d in spec_deps or []:
        if not isinstance(d, dict):
            continue
        fid = d.get("feature_id")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        merged.append({**d, "source": "spec"})
    for qid in queue_dep_ids or []:
        if not isinstance(qid, str) or qid in seen:
            continue
        seen.add(qid)
        merged.append({
            "feature_id": qid,
            "kind": "hard",
            "reason": "queue deps field",
            "source": "queue",
        })
    return merged


def resolve_upstream_dir(repo_root: Path, current_spec_dir: Path, feature_id: str) -> Path | None:
    """Resolve an upstream feature directory per the schema's resolution protocol."""
    # 1. Sibling-first
    sibling = current_spec_dir.parent / feature_id
    if (sibling / "SPEC.md").exists():
        return sibling
    # 2. queue.json fallback
    queue_path = repo_root / "docs" / "features" / "queue.json"
    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
            for entry in data.get("queue", []):
                if entry.get("id") == feature_id:
                    sd = entry.get("spec_dir")
                    if sd:
                        cand = (repo_root / "docs" / "features" / sd).resolve()
                        if (cand / "SPEC.md").exists():
                            return cand
                        cand2 = (repo_root / sd).resolve()
                        if (cand2 / "SPEC.md").exists():
                            return cand2
        except (json.JSONDecodeError, OSError):
            pass
    # 3. Search fallback
    features_root = repo_root / "docs" / "features"
    if features_root.exists():
        hits = list(features_root.glob(f"**/{feature_id}/SPEC.md"))
        if len(hits) == 1:
            return hits[0].parent
    return None


def upstream_is_complete(repo_root: Path, upstream_dir: Path) -> bool:
    """ROADMAP strikethrough+COMPLETE OR upstream SPEC Status: Complete."""
    roadmap = repo_root / "docs" / "features" / "ROADMAP.md"
    if roadmap.exists():
        text = roadmap.read_text(encoding="utf-8")
        upstream_name = upstream_dir.name
        # ROADMAP rows usually mention the directory name or human name; check both.
        # We apply whole-token anchoring: extract the text inside ~~...~~, take the
        # portion before any " — " separator, trim, and compare case-insensitively
        # for EQUALITY. This prevents "audio" from matching "~~audio-engine — ...~~".
        # The bare `upstream_name in line` check would produce a false positive
        # whenever upstream_name is a prefix/substring of a different completed name.
        strikethrough_re = re.compile(r"~~([^~]+)~~")
        for line in text.splitlines():
            if "~~" not in line or "COMPLETE" not in line:
                continue
            m = strikethrough_re.search(line)
            if not m:
                continue
            struck_name = m.group(1).split(" — ")[0].strip()
            if struck_name.lower() == upstream_name.lower():
                return True
    spec = upstream_dir / "SPEC.md"
    if spec.exists():
        try:
            for line in spec.read_text(encoding="utf-8").splitlines():
                if re.match(r"^\*\*Status:\*\*\s*Complete\s*$", line):
                    return True
        except OSError:
            pass
    return False


def newest_realign_plan(spec_dir: Path) -> Path | None:
    plans_dir = spec_dir / "plans"
    if not plans_dir.exists():
        return None
    candidates = sorted(plans_dir.glob("realign-*.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _phases_sha(upstream_dir: Path) -> str | None:
    """Return the sha256 hex digest of <upstream_dir>/PHASES.md, or None if absent.

    Used by realign_is_fresh to compare recorded upstream hashes in a realign
    plan's frontmatter against the current on-disk state. Git checkout/clone
    resets mtimes, making them unreliable; content hashes are stable.
    """
    phases_path = upstream_dir / "PHASES.md"
    if not phases_path.exists():
        return None
    return hashlib.sha256(phases_path.read_bytes()).hexdigest()


def realign_is_fresh(spec_dir: Path, hard_complete_upstream_dirs: list[Path]) -> bool:
    """Skip-if-fresh gate per /lazy Step 4.6a.

    Hash path (new): if the newest realign plan's frontmatter carries an
    ``upstream_phases_hashes`` dict (dir-name → sha256 hex), compare each
    recorded hash against the current PHASES.md on disk. Any mismatch or
    missing recorded entry means stale → realign needed → return False.
    All hashes match → return True (fresh, no realign needed).

    Legacy/mtime path (preserved): if the plan has no ``upstream_phases_hashes``
    field (older plan written before WU-8), fall back to the original mtime
    comparison so pre-existing realign plans are not invalidated.
    """
    plan = newest_realign_plan(spec_dir)
    if plan is None:
        return False

    # Try the hash path first: parse the plan's frontmatter and look for the
    # recorded upstream hashes dict.
    meta = _parse_plan_frontmatter(plan) or {}
    recorded_hashes = meta.get("upstream_phases_hashes")

    if recorded_hashes is not None:
        # Hash path: compare recorded sha256 against current PHASES.md content.
        # Any upstream whose hash is absent from the recorded dict OR whose
        # current sha256 differs from the recorded value triggers a re-realign.
        for ud in hard_complete_upstream_dirs:
            dir_name = ud.name
            current_sha = _phases_sha(ud)
            if current_sha is None:
                # Upstream has no PHASES.md — skip. A hashless upstream cannot
                # be hashed, so it can never appear in upstream_phases_hashes;
                # it contributes no PHASES-hash drift and MUST NOT force
                # staleness. This guard MUST precede the not-in-recorded_hashes
                # check below — otherwise a hard-complete upstream that was
                # never decomposed (e.g. audio-pipeline-v2, SPEC-only) makes
                # realign_is_fresh return False forever, deadlocking Step 4.6
                # (infinite realign loop blocking the whole queue).
                continue
            if dir_name not in recorded_hashes:
                # Upstream HAS a PHASES.md but the plan never recorded its hash
                # — treat as stale (plan was written before this dependency was
                # added, or for a different set).
                return False
            if current_sha != recorded_hashes[dir_name]:
                # Hash mismatch: upstream PHASES.md changed since the realign
                # plan was written → stale → re-realign needed.
                return False
        return True

    # Legacy/mtime fallback: no upstream_phases_hashes in the plan frontmatter
    # (old plan). Preserve exact original behaviour so pre-WU-8 plans still work.
    plan_mtime = plan.stat().st_mtime
    for ud in hard_complete_upstream_dirs:
        upstream_phases = ud / "PHASES.md"
        if not upstream_phases.exists():
            continue
        if upstream_phases.stat().st_mtime > plan_mtime:
            return False
    return True


# ---------------------------------------------------------------------------
# PHASES.md analysis — imported from lazy_core
# ---------------------------------------------------------------------------
# count_deliverables, remaining_unchecked_are_verification_only,
# _VERIFICATION_SECTION_RE — all imported from lazy_core above.

# ---------------------------------------------------------------------------
# Plan file discovery — imported from lazy_core
# ---------------------------------------------------------------------------
# _parse_plan_frontmatter, _plan_status, _plan_lowest_phase, _plan_phase_set,
# _unchecked_wus_in_plan_scope, find_implementation_plans, _has_any_complete_plan,
# find_retro_plans, latest_retro_plan, retro_plan_has_significant_divergences
# — all imported from lazy_core above.


def _plan_cloud_saturated(plan_path: Path, phases_text: str, spec_path: Path) -> bool:
    """Return True iff every unchecked WU in PHASES.md scoped to this plan's
    declared phases is documented (by substring match) in
    `<spec_path>/DEFERRED_NON_CLOUD.md`.

    Used by the Step 7a cloud-saturation gate to decide whether an
    In-progress plan should be auto-flipped to Complete because all
    cloud-runnable work is done and the only remainder is workstation-only
    deliverables explicitly deferred to the workstation MCP path.

    Conservative semantics:
      - Plans with no `phases:` field → False (we can't scope what counts as
        "in this plan", so we refuse to auto-flip).
      - Zero unchecked WUs in scope → False (the plan is already cloud-done;
        Step 8 retro would normally fire instead — let the existing flow run).
      - Any unchecked WU whose label does NOT appear (substring) in
        DEFERRED_NON_CLOUD.md → False.
    """
    deferred_file = spec_path / "DEFERRED_NON_CLOUD.md"
    if not deferred_file.exists():
        return False
    phase_set = _plan_phase_set(plan_path)
    if not phase_set:
        return False
    unchecked = _unchecked_wus_in_plan_scope(phases_text, phase_set)
    if not unchecked:
        return False
    try:
        deferred_text = deferred_file.read_text(encoding="utf-8")
    except OSError:
        return False
    for wu in unchecked:
        if wu not in deferred_text:
            return False
    return True


# find_implementation_plans, _has_any_complete_plan, find_retro_plans,
# latest_retro_plan, retro_plan_has_significant_divergences
# — all imported from lazy_core above.


# ---------------------------------------------------------------------------
# Step 10 helpers
# ---------------------------------------------------------------------------

def _write_step10_needs_input(spec_dir: Path, feature_name: str) -> None:
    """Write a well-formed NEEDS_INPUT.md sentinel into spec_dir for the Step 10
    unexpected-state defensive branch.

    The Step 10 branch fires when all phases are complete but none of the
    expected validation sentinels (VALIDATED.md, SKIP_MCP_TEST.md, or
    DEFERRED_NON_CLOUD.md) exists — a state that should be unreachable via the
    normal pipeline but may arise from manual sentinel manipulation. Writing
    NEEDS_INPUT.md here ensures the orchestrator's Step 1g decision-resume can
    surface the issue to the operator rather than silently cycling.

    Follows the NEEDS_INPUT.md schema in
    ~/.claude/skills/_components/sentinel-frontmatter.md:
      - YAML frontmatter: kind, feature_id, written_by, decisions list, date
      - Body: ## Decision Context H2 with one H3 per decision

    Idempotent: overwrites an existing NEEDS_INPUT.md without error.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    # Derive feature_id from the last component of spec_dir (standard convention:
    # docs/features/<feature-id>/). Used in both the frontmatter and body.
    feature_id = spec_dir.name

    decision_title = (
        "Resolve unexpected Step 10 state: phases complete without a validation sentinel"
    )
    content = (
        "---\n"
        "kind: needs-input\n"
        f"feature_id: {feature_id}\n"
        "written_by: lazy-state-step10\n"
        "decisions:\n"
        f'  - "{decision_title}"\n'
        f"date: {today}\n"
        "---\n"
        "\n"
        "## Decision Context\n"
        "\n"
        f"### 1. {decision_title}\n"
        "\n"
        "**Problem:** All PHASES.md deliverables are complete but none of the "
        "expected validation sentinels exist: no `VALIDATED.md`, no "
        "`SKIP_MCP_TEST.md`, and no `DEFERRED_NON_CLOUD.md`. This state is "
        "defensively unreachable via the normal pipeline — it most likely means "
        f"sentinels were deleted or renamed manually for `{feature_name}`. "
        "The pipeline cannot proceed to Step 10 (mark complete) without knowing "
        "whether MCP validation was performed.\n"
        "\n"
        "**Options:**\n"
        "- **Re-open for MCP validation** — re-run `/lazy` so the pipeline "
        "re-dispatches `/mcp-test`. Use this when the feature was never actually "
        "validated.\n"
        "- **Restore a missing sentinel** — if `VALIDATED.md` or `SKIP_MCP_TEST.md` "
        "was accidentally deleted, recreate it (check git history for the original "
        "content) and re-run `/lazy`. Use this when validation DID happen but the "
        "file was lost.\n"
        "- **Investigate and reset** — if the root cause is unclear, check "
        "`git log -- docs/features/ ` and `git log --diff-filter=D` to find when "
        "the sentinels were removed, then decide which of the above options applies.\n"
        "\n"
        "**Recommendation:** Re-open for MCP validation — this is the safest option "
        "because it forces a confirmed validation pass before `Complete` is written.\n"
    )
    needs_input_path = spec_dir / "NEEDS_INPUT.md"
    _atomic_write(needs_input_path, content)


def _phases_effectively_complete(spec_path: Path) -> bool:
    """Return True iff a feature has no remaining actionable implementation work.

    This is the precondition the Step 2 cloud/device-saturated skips used to
    encode via the presence of RETRO_DONE.md (which only ever existed once
    phases were complete and a retro round ran). With retro unwired, RETRO_DONE
    no longer exists, so we test the underlying property directly: a feature is
    "past implementation" when its PHASES.md has zero unchecked deliverables, OR
    every implementation plan is Complete and only verification-only rows remain
    (the same condition the Step-7 MCP-gate bypass keys on). A feature still
    mid-implementation (unchecked real deliverables, or an In-progress plan that
    still has actionable cloud work) is NOT saturated — it must keep dispatching
    execute-plan / Step-7a, never be silently skipped here.
    """
    phases_file = spec_path / "PHASES.md"
    if not phases_file.exists():
        return False
    phases_text = phases_file.read_text(encoding="utf-8")
    unchecked, _checked = count_deliverables(phases_text)
    if unchecked == 0:
        return True
    # Remaining unchecked rows are tolerable ONLY when they are verification-only
    # AND every implementation plan is already Complete (no execute-plan work
    # left). This mirrors the Step-7 bypass: an In-progress plan with actionable
    # rows still has work and is therefore NOT saturated.
    if (
        not find_implementation_plans(spec_path)
        and _has_any_complete_plan(spec_path)
        and remaining_unchecked_are_verification_only(phases_text)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Main state machine
# ---------------------------------------------------------------------------

def compute_state(
    repo_root: Path,
    cloud: bool,
    skip_needs_research: bool = False,
    real_device: bool = True,
    scope_feature_id: str | None = None,
    park_needs_input: bool = False,
    park_blocked: bool = False,
    park_provisional: bool = False,
    per_feature_cycle_cap: int | None = None,
    strict_research_halt: bool = False,
    host_present: set[str] | None = None,
) -> dict[str, Any]:
    # `real_device` defaults to True (behavior-preserving: a feature completes
    # exactly as before). ALL device-deferral logic below is gated on the
    # presence of a `DEFERRED_REQUIRES_DEVICE.md` sentinel, so this default has
    # NO effect on a feature that doesn't carry one. The CLI's `--real-device
    # auto` resolves the host's true capability and passes the result.
    #
    # Cloud has no audio device by definition, so cloud forces no-device: a
    # nonsensical `--cloud --real-device yes` is ignored. The device re-open
    # path lives in the workstation branch, which cloud never reaches; the
    # Step 2 device-saturated skip below is gated on `not real_device`, which
    # cloud satisfies.
    if cloud:
        real_device = False
    # Reset diagnostics for this invocation so callers get a fresh list per
    # compute_state() call (matters in run_smoke_tests() which loops).
    # clear_diagnostics() resets lazy_core._DIAGNOSTICS — the canonical list.
    clear_diagnostics()
    _DEVICE_DEFERRED.clear()
    _HOST_DEFERRED.clear()
    _HOST_SATURATED.clear()
    _OPERATOR_DEFERRED.clear()
    # Park mode: set the module global from the param so _state() can gate
    # the "parked" key on it.  _PARKED accumulates items skipped this invocation.
    global _PARK_MODE, _PARKED, _DEFERRED_BUDGET, _BUDGET_GUARD, _GATED_HEADS
    global _BUDGET_RESUMED, _DEP_GATED, _PROVISIONAL, _RESEARCH_GATED_HEADS
    global _SKIP_AHEAD_BLOCKED
    _PARK_MODE = park_needs_input or park_blocked
    _PARKED.clear()
    # park-provisional-acceptance: park_provisional is a strict modifier of
    # park_needs_input (SPEC D1 — the CLI enforces the pairing; this guard is
    # the in-process backstop for direct compute_state callers/tests).
    if park_provisional and not park_needs_input:
        _die("--park-provisional requires --park-needs-input (SPEC D1)")
    # _PROVISIONAL accumulates every NEEDS_INPUT_PROVISIONAL.md-bearing feature
    # observed during this walk (park mode only — mirrors _PARKED's gating).
    _PROVISIONAL.clear()
    # queue-dependency-dag Phase 2: reset the dep-gate hold list for this
    # invocation. _dep_dir_map is the lazily-built queued id → dir map the
    # dep-completion classifier resolves custom spec_dirs through — built only
    # when an entry actually carries `deps` (zero cost on the no-deps path).
    _DEP_GATED = []
    _dep_dir_map: dict | None = None
    # Reset the per-feature budget-guard state for this invocation.
    _DEFERRED_BUDGET = []
    _BUDGET_GUARD = None
    # feature-budget-guard-and-skip-ahead Phase 3: reset the skip-ahead gated-head
    # surfaced list for this invocation.
    _GATED_HEADS = []
    # research-gated-head-buried-by-skip-ahead-and-merged-fallthrough: reset the
    # research-pending subset in lockstep with _GATED_HEADS.
    _RESEARCH_GATED_HEADS = []
    # merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone: reset the
    # not-skip-ahead-ready (dep-unready) skip list for this invocation.
    _SKIP_AHEAD_BLOCKED = []
    # budget-guard-defers-near-complete-feature Phase 3: reset the end-of-run
    # resume-flush surfaced feature_id for this invocation.
    _BUDGET_RESUMED = None
    repo_root = repo_root.resolve()

    # guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual):
    # a REPORT-ONLY, never-halting "guards executed 0 times this run"
    # advisory. Computed once per probe (cheap: two small bounded file
    # reads); folded into the output ONLY when lazy_core returns a verdict
    # (None before the marker/min-cycle threshold — see its docstring for
    # the honesty caveat). Never gates any route below.
    global _GUARD_PLANE_HEARTBEAT
    _GUARD_PLANE_HEARTBEAT = lazy_core.guard_plane_heartbeat()

    # WU-8: auto-trigger stale-upstream detection at probe start when an ADO
    # materialization mirror exists. check_stale_upstream writes STALE_UPSTREAM.md
    # into any item dir whose upstream WI changed since materialize; Step 2.9 then
    # halts on it. This is the production writer the stale-upstream halt previously
    # lacked. Guarded by materialized.json so the common queue-only workflow is a no-op.
    if (repo_root / "docs" / "work" / "materialized.json").exists():
        check_stale_upstream(repo_root)

    queue = load_queue(repo_root)
    if not queue:
        # feature-queue-lacks-on-disk-autodiscovery: when autodiscover is enabled
        # but the merged work-list is empty, the queue did not go MISSING — disk
        # discovery simply found no OPEN feature dirs (all are Complete+receipt /
        # Superseded). Mirror the bug loader's "queue is OPTIONAL" contract: fall
        # through to the normal exhaustion logic, which resolves an empty queue to
        # all-features-complete. The queue-missing terminal stays for the genuine
        # no-queue-file / empty-queue-without-autodiscovery case.
        if not _queue_autodiscover_enabled(repo_root):
            return _state(
                terminal_reason="queue-missing",
                notify_message="queue.json not found — /lazy cannot operate.",
            )

    roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
    roadmap_text = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else ""

    # Step 2: find current feature
    current = None
    cloud_saturated_skipped: list[str] = []
    device_saturated_skipped: list[str] = []
    research_pending_skipped: list[str] = []
    seen_ids: set[str] = set()
    # Tracks whether the --feature-id scope arg matched ANY entry in the queue
    # (by raw id, before any dir/duplicate/completion skip).  If scope is set but
    # no entry matched, we emit "scoped-id-not-found" instead of "all-features-complete"
    # so callers can distinguish "queue exhausted" from "id typo / not queued".
    scope_id_seen: bool = False
    budget_deferred_skipped: list[str] = []
    # feature-budget-guard-and-skip-ahead Phase 3: skip-ahead bookkeeping.
    # gated_ids accumulates the feature ids of gated heads skipped this probe
    # (research-pending or BLOCKED) so a downstream candidate with a hard dep on
    # ANY of them is correctly NOT skipped onto. The not-skip-ahead-ready skips
    # (candidates that failed the two-key readiness predicate — downstream/unmarked
    # or dep-unready) are tracked in the SURFACED module global _SKIP_AHEAD_BLOCKED
    # (reset above) so probe_skipped_ids can fold them into the merged-head exclude
    # set — see merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone.
    gated_ids: set[str] = set()
    # The first gated head encountered — dispatched as a fallback if the loop
    # exhausts without finding a skip-ahead-ready alternative (so a single gated
    # item still reaches its per-feature terminal; only a realized skip past a
    # genuine independent alternative changes behavior).
    gated_head_fallback: dict | None = None

    # feature-budget-guard-and-skip-ahead Phase 2: per-feature budget guard setup.
    # The guard is MARKER-GATED — it only evaluates when a live run marker is
    # present (the same gate the counter advances ride). Absent a marker (single
    # /lazy, or a hermetic --test fixture without a pinned marker) the guard never
    # trips and output is byte-identical to the pre-feature baseline.
    _bg_marker = lazy_core.read_run_marker()
    _bg_per_feature = lazy_core.read_per_feature_forward_cycles(_bg_marker)
    _bg_evicted: list = list((_bg_marker or {}).get("budget_evicted", [])) \
        if isinstance(_bg_marker, dict) else []
    _bg_deferred_counts: dict = dict((_bg_marker or {}).get("budget_deferred", {})) \
        if isinstance(_bg_marker, dict) else {}
    # ready_queue_depth = count of ready (on-disk, non-completed, non-evicted) queue
    # features — the Q_depth the fair-share ceiling divides by. Computed as a
    # deterministic pre-pass over the queue (the same id-set the loop enumerates).
    _bg_ready_depth = 0
    if _bg_marker is not None:
        _bg_seen_depth: set = set()
        for _e in queue:
            _eid = _e.get("id")
            _esub = _e.get("spec_dir")
            _ename = _e.get("name")
            if not _eid or not _esub or not _ename or _eid in _bg_seen_depth:
                continue
            _bg_seen_depth.add(_eid)
            _esp = (repo_root / "docs" / "features" / _esub).resolve()
            if not _esp.exists():
                continue
            if completion_claimed(roadmap_text, _ename, _esp) and (
                spec_status(_esp) == "Superseded" or has_completion_receipt(_esp)
            ):
                continue
            if _eid in _bg_evicted:
                continue
            _bg_ready_depth += 1
    _bg_max_cycles = int((_bg_marker or {}).get("max_cycles", 0) or 0) \
        if isinstance(_bg_marker, dict) else 0
    _bg_ceiling = (
        lazy_core.compute_per_feature_ceiling(
            _bg_max_cycles, _bg_ready_depth, override=per_feature_cycle_cap
        )
        if _bg_marker is not None
        else None
    )

    # feature-budget-guard-and-skip-ahead Phase 3: gated-head detector. A queue
    # head is "gated" when it is research-pending (a RESEARCH_PROMPT.md / a
    # NEEDS_RESEARCH.md with no RESEARCH.md / RESEARCH_SUMMARY.md) OR carries a
    # BLOCKED.md. This is the SAME research-pending peek the --skip-needs-research
    # branch uses, plus BLOCKED. Cheap filesystem read; no per-feature state
    # machine. Used by the skip-ahead branch below (default-on; --strict-research-
    # halt disables it).
    def _gated_head_kind(sp: Path) -> "str | None":
        # research-gated-head-buried-by-skip-ahead-and-merged-fallthrough:
        # classify a gated head as 'research' (operator-resolvable research gap),
        # 'blocked' (canonical BLOCKED.md — external gate / host), or None (not
        # gated). Research-pending takes PRECEDENCE when a head carries BOTH a
        # research prompt and a BLOCKED.md — aligning with the Step-1h
        # research-blocked carve-out (a research gap is filled by a Gemini upload,
        # not a corrective phase). The gated-vs-not verdict is unchanged from the
        # old _is_gated_head boolean (research_pending OR BLOCKED); this only adds
        # the KIND so the merged-head path can surface research heads distinctly.
        needs_research_file = sp / "NEEDS_RESEARCH.md"
        research_prompt = sp / "RESEARCH_PROMPT.md"
        research = sp / "RESEARCH.md"
        research_summary = sp / "RESEARCH_SUMMARY.md"
        research_pending = (
            needs_research_file.exists()
            or (
                research_prompt.exists()
                and not research.exists()
                and not research_summary.exists()
            )
        )
        if research_pending:
            return "research"
        if (sp / "BLOCKED.md").exists():
            return "blocked"
        return None

    # host-capability-declaration-for-gated-features Phase 5: lazily-resolved
    # host present-capability set. Injected (host_present is not None) ⇒ used as-is
    # (the hermetic --test seam). Otherwise resolved ONCE via the real Phase-3
    # probe resolver, but ONLY when a feature actually declares requires_host: —
    # an all-ungated queue never touches the host probe (baseline-regression rail:
    # zero new I/O on the no-requires_host path). The resolver is per-run-cached
    # internally; this holder caches the per-compute_state() resolution.
    _host_present_holder: dict = {"value": host_present, "resolved": host_present is not None}

    def _resolve_host_present() -> set[str]:
        if not _host_present_holder["resolved"]:
            try:
                _host_present_holder["value"] = lazy_core.host_present_capabilities()
            except Exception:  # noqa: BLE001 — a degraded probe ⇒ empty present set
                _host_present_holder["value"] = set()
            _host_present_holder["resolved"] = True
        return set(_host_present_holder["value"] or set())

    for entry in queue:
        name = entry.get("name")
        feature_id = entry.get("id")
        spec_subdir = entry.get("spec_dir")
        if not name or not feature_id or not spec_subdir:
            missing = [k for k, v in (("id", feature_id), ("name", name), ("spec_dir", spec_subdir)) if not v]
            _diag(
                f"queue entry skipped — missing {', '.join(missing)} "
                f"(entry: {str(entry)[:120]!r})"
            )
            continue
        # FM3 anti-fabrication guard: a queue entry whose spec_dir does NOT
        # resolve to an on-disk directory is a dangling reference (typo, stale
        # entry, or — the failure this guards — a hallucinated feature). Skip it
        # with a loud diagnostic rather than returning it for dispatch; a cycle
        # against a non-existent feature is exactly what lets a subagent
        # FABRICATE the SPEC/RESEARCH/queue entries from a bare slug. The ONLY
        # sanctioned dir-creating paths are --enqueue-adhoc (seeds the dir
        # before the queue entry) and /spec on an already-seeded dir.
        spec_path = (repo_root / "docs" / "features" / spec_subdir).resolve()
        if not spec_path.exists():
            _diag(
                f"dangling queue entry: '{feature_id}' (spec_dir '{spec_subdir}') "
                "does not resolve to an on-disk directory under docs/features/ — "
                "skipped. Create the spec dir (via /spec or --enqueue-adhoc) or "
                "remove the stale queue entry. A cycle is NEVER dispatched against "
                "a feature that does not exist on disk."
            )
            continue
        # Duplicate-id guard: first entry wins; a second entry with the same id
        # is silently orphaned otherwise. Surface it.
        if feature_id in seen_ids:
            _diag(f"duplicate queue id '{feature_id}' — second entry ignored.")
            continue
        seen_ids.add(feature_id)
        # --feature-id scoping: when set, process ONLY the matching queue entry.
        # Absent the flag (None) behavior is byte-identical to single-current.
        # scope_id_seen is set here — BEFORE any completion/cloud/device skip
        # would continue past the entry — so a matched-but-skipped scoped feature
        # still counts as "seen" (not reported as scoped-id-not-found).
        if scope_feature_id is not None:
            if feature_id != scope_feature_id:
                continue
            scope_id_seen = True
        # FM1 receipt-gated completion. A feature is genuinely DONE only when it
        # CLAIMS completion AND carries a durable COMPLETED.md receipt proving it
        # passed through __mark_complete__'s integrity gate. Superseded is exempt
        # (a retired feature was never validated).
        if completion_claimed(roadmap_text, name, spec_path):
            if spec_status(spec_path) == "Superseded" or has_completion_receipt(spec_path):
                # Scoped-match identity preservation (lazy-queue-doc-renders-
                # bogus-rows-for-stale-complete-entries): a --feature-id query
                # matching an entry that is ALREADY genuinely done (Superseded,
                # or Complete+receipted) must return ITS OWN identity + a scoped
                # complete terminal — not `continue` into the rest of the walk,
                # which (under scoping) skips every other entry too and falls
                # through to whatever GLOBAL terminal the exhausted walk
                # produces (e.g. all-features-complete with unrelated
                # diagnostics). That fallthrough is exactly what let
                # pipeline_visualizer.probe / lazy-queue-doc.py render a
                # Complete+receipted queue entry as an "unknown"/Pending row —
                # the state script's own scoped answer carried no identity for
                # probe.py to key on. UNSCOPED (scope_feature_id is None) stays
                # byte-identical — this branch fires ONLY on a scoped match.
                if scope_feature_id is not None and feature_id == scope_feature_id:
                    return _scoped_skip_state(
                        feature_id=feature_id,
                        feature_name=name,
                        spec_path=spec_path,
                        current_step=STEP_COMPLETE_SCOPED,
                        terminal_reason=TR_COMPLETE_SCOPED,
                        notify_message=f"{name}: already complete.",
                    )
                continue
            # Claimed Complete WITHOUT a receipt → the SPEC/ROADMAP was flipped
            # outside the validation gate (a cycle subagent or hand edit). This
            # is the exact failure that let a feature skip /retro + /mcp-test.
            # Hard-halt and surface for reconciliation rather than silently
            # treating it as done.
            return _state(
                feature_id=feature_id,
                feature_name=name,
                spec_path=str(spec_path),
                current_step="Step 2: completion claimed without receipt",
                terminal_reason="completion-unverified",
                notify_message=(
                    f"{name}: SPEC/ROADMAP marks this Complete but no COMPLETED.md "
                    "receipt exists — it was flipped OUTSIDE the validation gate. "
                    "Reconcile: reopen to In-progress for real validation, or run "
                    "lazy-state.py --backfill-receipts to grandfather it as "
                    "completed-but-unverified."
                ),
            )
        if cloud:
            # Cloud-saturated skip. (Retro unwired: the old RETRO_DONE.md
            # precondition is replaced by _phases_effectively_complete() — the
            # underlying "past implementation" property RETRO_DONE used to
            # proxy. A cloud feature past implementation that deferred MCP to
            # workstation carries DEFERRED_NON_CLOUD.md + no VALIDATED.md. A
            # feature still mid-implementation must NOT be skipped — it has
            # actionable Step-7 work.)
            deferred = (spec_path / "DEFERRED_NON_CLOUD.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if deferred and not validated and _phases_effectively_complete(spec_path):
                # Scoped-match identity preservation (Phase 2 — feature-side
                # parity twin of bug-state.py's Phase-1 cloud-saturated scoped
                # return). A scoped --feature-id query on a cloud-saturated feature
                # returns its OWN identity + a scoped cloud-deferred terminal,
                # instead of `continue`-ing into the global null-identity
                # cloud-queue-exhausted. UNSCOPED (scope_feature_id is None) is
                # byte-identical — the guard fires ONLY on a scoped match.
                if scope_feature_id is not None and feature_id == scope_feature_id:
                    return _scoped_skip_state(
                        feature_id=feature_id,
                        feature_name=name,
                        spec_path=spec_path,
                        current_step=STEP_CLOUD_DEFERRED_SCOPED,
                        terminal_reason=TR_CLOUD_DEFERRED_SCOPED,
                        notify_message=(
                            f"{name}: cloud-saturated (DEFERRED_NON_CLOUD.md, no "
                            "VALIDATED.md). Scoped query returns its identity; "
                            "awaiting workstation /lazy validation."
                        ),
                    )
                cloud_saturated_skipped.append(name)
                continue
        if not real_device:
            # Device-saturated skip (the device-axis mirror of the cloud skip).
            # A feature past implementation whose only remaining MCP gap is
            # real-device-only assertions (deferred via DEFERRED_REQUIRES_DEVICE.md,
            # no VALIDATED.md yet) cannot be certified on THIS no-device host.
            # Skip it so the queue advances — a real-device host re-opens it
            # (Step 9) to run the deferred scenarios. This applies to cloud too
            # (cloud has no device), but in practice cloud features carry
            # DEFERRED_NON_CLOUD.md and are caught by the cloud skip above first.
            # (Retro unwired: _phases_effectively_complete() replaces the old
            # RETRO_DONE.md precondition.)
            device_deferred = (spec_path / "DEFERRED_REQUIRES_DEVICE.md").exists()
            validated = (spec_path / "VALIDATED.md").exists()
            if device_deferred and not validated and _phases_effectively_complete(spec_path):
                meta = parse_sentinel(spec_path / "DEFERRED_REQUIRES_DEVICE.md") or {}
                scen = meta.get("deferred_scenarios") or []
                scen_str = ", ".join(str(s) for s in scen) if scen else "(unspecified)"
                # Scoped-match identity preservation (Phase 2 — feature-side parity
                # twin of bug-state.py's Phase-1 device-saturated scoped return). A
                # scoped --feature-id query on a device-saturated feature returns
                # its OWN identity + a scoped device-deferred terminal, instead of
                # `continue`-ing into the global null-identity device-queue-exhausted.
                # UNSCOPED is byte-identical — fires ONLY on a scoped match.
                if scope_feature_id is not None and feature_id == scope_feature_id:
                    return _scoped_skip_state(
                        feature_id=feature_id,
                        feature_name=name,
                        spec_path=spec_path,
                        current_step=STEP_DEVICE_DEFERRED_SCOPED,
                        terminal_reason=TR_DEVICE_DEFERRED_SCOPED,
                        notify_message=(
                            f"{name}: device-saturated — real-device-only "
                            f"assertions deferred [{scen_str}] "
                            "(DEFERRED_REQUIRES_DEVICE.md). Scoped query returns "
                            "its identity; re-opens on a real-device /lazy host."
                        ),
                    )
                device_saturated_skipped.append(name)
                _DEVICE_DEFERRED.append(name)
                # Per-feature diagnostic on EVERY probe (not only when the queue
                # exhausts) so a lingering In-progress device-deferral is always
                # visible, even when a later feature is dispatched this cycle.
                _diag(
                    f"device-saturated skipped: {name} — real-device-only "
                    f"assertions deferred [{scen_str}] (DEFERRED_REQUIRES_DEVICE.md); "
                    "re-opens on a real-device /lazy host."
                )
                continue
        # host-capability-declaration-for-gated-features Phases 4 + 5: the
        # host-capability gate. Parse the feature's requires_host: set (two-source:
        # SPEC frontmatter + queue entry). An ungated feature (empty set) is
        # byte-identical to today — no probe, no defer, no fail-fast.
        try:
            _hc_spec_text = (spec_path / "SPEC.md").read_text(encoding="utf-8") \
                if (spec_path / "SPEC.md").exists() else ""
        except OSError:
            _hc_spec_text = ""
        required_host = lazy_core.parse_requires_host(_hc_spec_text, entry)
        if required_host:
            # Phase 4 — fail-fast on an unregistered capability id. An id with no
            # registry entry has no probe and could never be "present" anywhere,
            # so it would silently defer FOREVER (the starvation hazard). It is a
            # loud, immediate validation failure: write a real BLOCKED.md
            # (blocker_kind: unknown-host-capability) naming the offending id(s)
            # and the sorted registry ids, and halt on terminal_reason="blocked"
            # (the existing canonical-blocker terminal — no new sentinel name, so
            # the write-time stray-branch + noncanonical-blocker hooks cover it).
            # This MUST precede the Phase-5 match below.
            unknown = lazy_core.unknown_capability_ids(required_host)
            if unknown:
                blocked_file = spec_path / "BLOCKED.md"
                if not blocked_file.exists():
                    body = lazy_core.format_unknown_host_capability_blocker(
                        feature_id, unknown
                    )
                    _write_yaml_blocked_sentinel(
                        blocked_file,
                        feature_id=feature_id,
                        phase="Host-capability validation",
                        blocker_kind="unknown-host-capability",
                        blocked_at=lazy_core.utc_now_iso(),
                        retry_count=0,
                        body=body,
                    )
                _diag(
                    f"unknown-host-capability: {name} declares unregistered "
                    f"requires_host: id(s) {sorted(unknown)!r} — wrote BLOCKED.md "
                    f"(blocker_kind: unknown-host-capability). Fix the typo or "
                    f"register a probe."
                )
                return _state(
                    feature_id=feature_id,
                    feature_name=name,
                    spec_path=str(spec_path),
                    current_step="Step 3: blocked",
                    terminal_reason="blocked",
                    notify_message=(
                        f"BLOCKED: {name} — unregistered requires_host: "
                        f"capability id(s) {', '.join(sorted(unknown))}. "
                        "Awaiting input."
                    ),
                )
            # Phase 5 — capability match + defer-to-capability-host. Only a feature
            # PAST implementation (the device-skip precondition) whose required set
            # is not yet certified (no VALIDATED.md) can be host-deferred — a
            # mid-implementation feature still has actionable Step-7 work and must
            # NOT be skipped. Compute missing = required - host.present (flat AND;
            # any miss ⇒ defer). On a non-empty miss write DEFERRED_REQUIRES_HOST.md
            # (re-openable), skip so the queue advances, and surface the deferral.
            # An empty miss is the no-special-case re-open: fall through to dispatch.
            host_validated = (spec_path / "VALIDATED.md").exists()
            if (
                not host_validated
                and _phases_effectively_complete(spec_path)
            ):
                present = _resolve_host_present()
                missing = sorted(required_host - present)
                if missing:
                    host_deferred_file = spec_path / "DEFERRED_REQUIRES_HOST.md"
                    if not host_deferred_file.exists():
                        lazy_core.write_deferred_requires_host(
                            host_deferred_file,
                            feature_id=feature_id,
                            missing_capabilities=missing,
                            deferred_by=("lazy-batch" if _bg_marker is not None else "lazy"),
                        )
                    # Scoped-match identity preservation (Phase 2): a scoped
                    # --feature-id query on a host-capability-deferred feature
                    # returns its OWN identity + a scoped host-capability-deferred
                    # terminal, instead of `continue`-ing into the global
                    # null-identity host-capability-saturated. The
                    # DEFERRED_REQUIRES_HOST.md re-open sentinel is written ABOVE
                    # regardless (the on-disk re-open contract is scope-independent);
                    # only the queue-skip vs. scoped-return decision differs. UNSCOPED
                    # is byte-identical — fires ONLY on a scoped match. (No bug-side
                    # analog — the host-capability axis is feature-pipeline-only.)
                    if scope_feature_id is not None and feature_id == scope_feature_id:
                        return _scoped_skip_state(
                            feature_id=feature_id,
                            feature_name=name,
                            spec_path=spec_path,
                            current_step=STEP_HOST_DEFERRED_SCOPED,
                            terminal_reason=TR_HOST_DEFERRED_SCOPED,
                            notify_message=(
                                f"{name}: host-capability-saturated — requires "
                                f"{', '.join(missing)} (absent on this host); "
                                "deferred (DEFERRED_REQUIRES_HOST.md). Scoped query "
                                "returns its identity; re-opens on a capability-host."
                            ),
                        )
                    _HOST_DEFERRED.append(feature_id)
                    _HOST_SATURATED.append(
                        {"feature_id": feature_id, "missing": list(missing)}
                    )
                    _diag(
                        f"host-capability miss: {name} requires "
                        f"{', '.join(missing)} (absent on this host); deferred to a "
                        f"capability-host (DEFERRED_REQUIRES_HOST.md). Re-opens on a "
                        f"host that provides the capability."
                    )
                    continue
        # -----------------------------------------------------------------------
        # Operator-deferred skip (merged-head-oracle-per-signal-supplement-churn
        # Phase 1 — feature-side mirror of bug-state.py's operator-deferred branch,
        # closing the former feature/bug divergence): a bare DEFERRED.md means the
        # operator parked this feature. Skip and continue so the queue keeps
        # moving; re-include by deleting DEFERRED.md. UNCONDITIONAL (independent of
        # any park flag), exactly like the bug side — the merged-head oracle relies
        # on an operator-deferred feature being non-dispatchable at its own
        # pipeline. Placed after the device/host skips and before the park branches
        # to mirror the bug-side ordering. Uses the shared
        # lazy_core.spec_dir_operator_deferred predicate (never an inline
        # DEFERRED.md existence check) + _scoped_skip_state for the scoped return,
        # exactly as the sibling cloud/device/host scoped branches do.
        if lazy_core.spec_dir_operator_deferred(spec_path):
            # Scoped-match identity preservation: when --feature-id targets THIS
            # feature, return its identity + a per-feature scoped deferred terminal
            # instead of `continue`-ing into the global null-identity
            # all-remaining-deferred terminal (which renders "unknown" downstream).
            # UNSCOPED behavior (scope_feature_id is None) is byte-identical.
            if scope_feature_id is not None and feature_id == scope_feature_id:
                return _scoped_skip_state(
                    feature_id=feature_id,
                    feature_name=name,
                    spec_path=spec_path,
                    current_step=STEP_OPERATOR_DEFERRED_SCOPED,
                    terminal_reason=TR_OPERATOR_DEFERRED_SCOPED,
                    notify_message=(
                        f"{name}: operator-deferred (DEFERRED.md). Scoped query "
                        "returns its identity; re-include by deleting DEFERRED.md."
                    ),
                )
            _OPERATOR_DEFERRED.append(name)
            meta = parse_sentinel(spec_path / "DEFERRED.md") or {}
            reason = meta.get("reason") or "(no reason recorded)"
            _diag(
                f"operator-deferred skipped: {name} — DEFERRED.md "
                f"(reason: {reason}); re-include by deleting DEFERRED.md."
            )
            continue
        if skip_needs_research:
            # Cheap filesystem peek — don't run the full per-feature state machine.
            # Skip features that would terminate the loop with needs-research.
            needs_research_file = spec_path / "NEEDS_RESEARCH.md"
            research_prompt = spec_path / "RESEARCH_PROMPT.md"
            research = spec_path / "RESEARCH.md"
            research_summary = spec_path / "RESEARCH_SUMMARY.md"
            research_pending = (
                needs_research_file.exists()
                or (
                    research_prompt.exists()
                    and not research.exists()
                    and not research_summary.exists()
                )
            )
            if research_pending:
                research_pending_skipped.append(name)
                continue
        # Park-mode (BLOCKED): if --park-blocked is active and this feature has a
        # BLOCKED.md, skip (park) it instead of halting the queue with
        # terminal_reason="blocked". The item re-enters automatically once the
        # block is resolved/renamed. Evaluated BEFORE the NEEDS_INPUT park branch
        # so a feature carrying BOTH sentinels parks exactly ONCE (this branch
        # `continue`s, so the NEEDS_INPUT branch is not reached for it). This is
        # the root-cause fix for park-mode-halts-on-blocked (SPEC D1).
        if park_blocked and (spec_path / "BLOCKED.md").exists():
            # Scoped-match identity preservation (Phase 2 — feature-side parity twin
            # of bug-state.py's Phase-1 parked-blocked scoped return): a scoped
            # --feature-id on a parked-blocked feature returns a scoped BLOCKED-family
            # state naming the feature, instead of `continue`-ing into
            # queue-exhausted-all-parked. UNSCOPED is byte-identical.
            if scope_feature_id is not None and feature_id == scope_feature_id:
                return _scoped_skip_state(
                    feature_id=feature_id,
                    feature_name=name,
                    spec_path=spec_path,
                    current_step=STEP_BLOCKED_PARKED_SCOPED,
                    terminal_reason=TR_BLOCKED_SCOPED,
                    notify_message=(
                        f"{name}: feature-local BLOCKED.md, parked (park mode). "
                        "Scoped query returns its identity; re-enters when resolved."
                    ),
                )
            _PARKED.append(lazy_core.build_parked_entry(feature_id, spec_path / "BLOCKED.md"))
            lazy_core.notify_event(
                "park", f"{name} parked (BLOCKED.md)", str(repo_root),
                item_id=feature_id, detail="feature-local BLOCKED.md",
            )
            _diag(
                f"parked: {name} — feature-local BLOCKED.md; skipped (park mode). "
                "Re-enters when resolved."
            )
            continue
        # Park-mode (mis-named blocker): parity with the canonical BLOCKED park
        # branch above for a non-canonical stray (noncanonical-blocker-filename-
        # invisible-to-state-machine). When --park-blocked is active, canonical
        # BLOCKED.md is ABSENT, and the shared detector finds a stray, park it the
        # same way (it re-enters once renamed/neutralized). Keeps --park-blocked
        # semantics aligned with the canonical blocker. (The helper itself returns
        # None when canonical is present, so the `.exists()` guard is belt-and-
        # suspenders parity with the branch above.)
        if park_blocked and not (spec_path / "BLOCKED.md").exists():
            _stray = lazy_core.detect_noncanonical_blocker(spec_path)
            if _stray is not None:
                # Scoped-match identity preservation (Phase 2): a mis-named blocker
                # is a BLOCKED-family park — same scoped treatment as the canonical
                # BLOCKED park branch above. UNSCOPED is byte-identical.
                if scope_feature_id is not None and feature_id == scope_feature_id:
                    return _scoped_skip_state(
                        feature_id=feature_id,
                        feature_name=name,
                        spec_path=spec_path,
                        current_step=STEP_BLOCKED_PARKED_SCOPED,
                        terminal_reason=TR_BLOCKED_SCOPED,
                        notify_message=(
                            f"{name}: feature-local mis-named blocker "
                            f"'{_stray.name}', parked (park mode). Scoped query "
                            "returns its identity; re-enters when renamed to "
                            "BLOCKED.md or neutralized."
                        ),
                    )
                _PARKED.append(lazy_core.build_parked_entry(feature_id, _stray))
                lazy_core.notify_event(
                    "park", f"{name} parked (mis-named blocker)", str(repo_root),
                    item_id=feature_id, detail=f"stray blocker: {_stray.name}",
                )
                _diag(
                    f"parked: {name} — feature-local mis-named blocker "
                    f"'{_stray.name}'; skipped (park mode). Re-enters when "
                    "renamed to BLOCKED.md or neutralized."
                )
                continue
        # Park-mode: if --park-needs-input is active and this feature has an
        # unresolved NEEDS_INPUT.md, skip (park) it instead of halting the queue.
        # The item re-enters automatically once NEEDS_INPUT.md is resolved/renamed.
        # BLOCKED.md retains precedence when --park-blocked is NOT set: a feature
        # carrying BOTH BLOCKED.md and NEEDS_INPUT.md must still halt as "blocked",
        # not be silently parked. (When --park-blocked IS set, the BLOCKED park
        # branch above already parked + continued, so this guard is moot.)
        if (
            park_needs_input
            and (spec_path / "NEEDS_INPUT.md").exists()
            and not (spec_path / "BLOCKED.md").exists()
        ):
            # park-provisional-acceptance (SPEC D2): under --park-provisional a
            # provisional-ELIGIBLE sentinel routes the __provisional_accept__
            # pseudo-skill instead of parking — the orchestrator runs the
            # script-owned --provisionalize-sentinel action and the feature
            # keeps moving this run. Eligibility is the fail-closed
            # lazy_core.provisional_eligibility predicate (divergence two-key
            # + recommendations + never two-key-mechanical / gate-written).
            # Checked BEFORE the scoped-identity return: a scoped probe on an
            # eligible feature routes the same acceptance. Ineligible →
            # parked exactly as before, with the reason breadcrumbed.
            if park_provisional:
                _pp_eligible, _pp_reason = lazy_core.provisional_eligibility(
                    spec_path / "NEEDS_INPUT.md"
                )
                if _pp_eligible:
                    return _state(
                        feature_id=feature_id,
                        feature_name=name,
                        spec_path=str(spec_path),
                        current_step="Step 3.5: needs-input (provisional accept)",
                        sub_skill="__provisional_accept__",
                        sub_skill_args=str(spec_path),
                    )
                _diag(
                    f"provisional-ineligible: {name} — {_pp_reason}; "
                    "parking instead (fail-closed)."
                )
            # Scoped-match identity preservation (Phase 2 — feature-side parity twin
            # of bug-state.py's Phase-1 parked-needs-input scoped return): a scoped
            # --feature-id on a parked-needs-input feature returns a scoped
            # NEEDS-INPUT-family state. UNSCOPED is byte-identical.
            if scope_feature_id is not None and feature_id == scope_feature_id:
                return _scoped_skip_state(
                    feature_id=feature_id,
                    feature_name=name,
                    spec_path=spec_path,
                    current_step=STEP_NEEDS_INPUT_PARKED_SCOPED,
                    terminal_reason=TR_NEEDS_INPUT_SCOPED,
                    notify_message=(
                        f"{name}: unresolved NEEDS_INPUT.md, parked (park mode). "
                        "Scoped query returns its identity; re-enters when resolved."
                    ),
                )
            _PARKED.append(lazy_core.build_parked_entry(feature_id, spec_path / "NEEDS_INPUT.md"))
            lazy_core.notify_event(
                "park", f"{name} parked (NEEDS_INPUT.md)", str(repo_root),
                item_id=feature_id, detail="unresolved NEEDS_INPUT.md",
            )
            _diag(
                f"parked: {name} — unresolved NEEDS_INPUT.md; skipped (park mode). "
                "Re-enters when resolved."
            )
            continue
        # park-provisional-acceptance (SPEC D5/D6 layer a): a feature carrying an
        # unratified NEEDS_INPUT_PROVISIONAL.md in PARK MODE. Record it in the
        # park-mode-only provisional[] surface. When its pipeline work is
        # otherwise done (VALIDATED.md present — the only remaining route would
        # be __mark_complete__, which MUST NOT fire on an unratified
        # provisional), PARK it (sentinel_kind: provisional) so the run-end
        # flush surfaces ratification; otherwise fall through — the feature is
        # workable and keeps implementing. Non-park probes never reach this
        # branch (park_needs_input gate) — they halt at Step 3.6 instead.
        # Ordering: AFTER the NEEDS_INPUT.md park branch (a NEW decision
        # outranks a pending ratification, SPEC D5).
        if park_needs_input and (spec_path / lazy_core.PROVISIONAL_SENTINEL).exists():
            _prov_entry = lazy_core.build_parked_entry(
                feature_id, spec_path / lazy_core.PROVISIONAL_SENTINEL
            )
            if not any(p.get("id") == feature_id for p in _PROVISIONAL):
                _PROVISIONAL.append(_prov_entry)
            if (spec_path / "VALIDATED.md").exists():
                if scope_feature_id is not None and feature_id == scope_feature_id:
                    return _scoped_skip_state(
                        feature_id=feature_id,
                        feature_name=name,
                        spec_path=spec_path,
                        current_step=STEP_PROVISIONAL_PARKED_SCOPED,
                        terminal_reason=TR_NEEDS_RATIFICATION_SCOPED,
                        notify_message=(
                            f"{name}: implementation + validation done; unratified "
                            f"{lazy_core.PROVISIONAL_SENTINEL} parks completion "
                            "(park mode). Ratify or redirect at the flush."
                        ),
                    )
                _PARKED.append(_prov_entry)
                lazy_core.notify_event(
                    "park", f"{name} parked (unratified provisional)", str(repo_root),
                    item_id=feature_id,
                    detail="validated but awaiting ratification — parks at completion",
                )
                _diag(
                    f"parked: {name} — validated but awaiting ratification of "
                    f"{lazy_core.PROVISIONAL_SENTINEL}; completion deferred to "
                    "the flush (park mode)."
                )
                continue
        # feature-budget-guard-and-skip-ahead Phase 2: per-feature budget guard.
        # MARKER-GATED — only evaluates when a live run marker is present. This is
        # the FINAL skip branch (after completion / cloud / device / research /
        # park), mirroring the --park-* skip-list shape: on trip the feature is
        # appended to the run-scoped _DEFERRED_BUDGET list and we `continue` to the
        # next ready item — a run-scoped reorder that does NOT touch queue.json.
        if _bg_marker is not None and _bg_ceiling is not None:
            # An already-evicted feature is removed from the live queue for the rest
            # of the run (its on-disk progress is preserved for human audit).
            if feature_id in _bg_evicted:
                budget_deferred_skipped.append(feature_id)
                _diag(
                    f"budget-guard: {name} — already evicted this run "
                    f"(budget_evicted); skipped. On-disk progress preserved."
                )
                continue
            _bg_count = int(_bg_per_feature.get(feature_id, 0) or 0)
            # budget-guard-defers-near-complete-feature Phase 2: replace the bare
            # `_bg_count >= _bg_ceiling` comparison with the composite
            # budget_trip_signals decision so (1) a near-complete feature is
            # granted ONE grace cycle past the ceiling before it can defer, and
            # (2) legitimate validation-driven corrective cycles are discounted
            # from the trip count (effective_count = forward - corrective).
            #   - near_complete reuses the SAME "ready to validate" predicate the
            #     mid-feature gate uses (verification-only PHASES + plan-Complete +
            #     no BLOCKED.md), read at trip time from the tripped feature's dir.
            #   - corrective is read from the per_feature_corrective_cycles marker
            #     sub-map (incremented at the corrective-dispatch bracket, WU-5).
            #   - GRACE IS ONE-SHOT: a near-complete feature that has ALREADY been
            #     budget-deferred this run (`prior_defers >= 1`) is treated as NOT
            #     near-complete for the trip decision, so it cannot exploit grace
            #     to monopolize — the normal trip/escalation re-asserts.
            _bg_prior_defers = int(_bg_deferred_counts.get(feature_id, 0) or 0)
            _bg_near_complete = lazy_core.feature_is_near_complete(spec_path, repo_root)
            _bg_grace_eligible = _bg_near_complete and _bg_prior_defers < 1
            _bg_corrective = lazy_core.count_validation_corrective_cycles(
                _bg_marker, feature_id
            )
            _bg_signals = lazy_core.budget_trip_signals(
                _bg_count, _bg_corrective, _bg_ceiling, _bg_grace_eligible
            )
            if _bg_grace_eligible and not _bg_signals["should_defer"] and (
                _bg_count >= _bg_ceiling
            ):
                # The would-be trip was waived by the one-shot near-completion
                # grace — announce it and DISPATCH the feature (no defer) so it
                # reaches the terminal /mcp-test → __mark_complete__ this cycle.
                _diag(
                    f"budget-guard: {name} — near-complete (verification-only "
                    f"PHASES + plan-Complete, no BLOCKED.md); GRACE GRANTED at the "
                    f"per-feature ceiling ({_bg_count} >= {_bg_ceiling}, "
                    f"effective={_bg_signals['effective_count']}). Dispatching to "
                    f"finish validation instead of deferring (one-shot grace)."
                )
                # Surface the grace grant via the budget_guard probe key (the
                # orchestrator reports the auto-grace alongside trips). next_id is
                # back-filled below to this same dispatched feature.
                if _BUDGET_GUARD is None:
                    _BUDGET_GUARD = {
                        "feature_id": feature_id,
                        "count_at_trip": _bg_count,
                        "computed_ceiling": _bg_ceiling,
                        "action": "grace",
                        "next_id": None,
                        "sub_skill_phase": None,
                        "commit_hash": lazy_core.git_head_short_sha(repo_root),
                        "effective_count": _bg_signals["effective_count"],
                        "corrective_count": _bg_corrective,
                        "near_complete_grace_granted": True,
                    }
            if _bg_signals["should_defer"]:
                # Trip. First trip → defer to tail (bounded re-entry once); a 2nd
                # trip on the SAME feature in the SAME run → terminal eviction.
                prior_defers = _bg_prior_defers
                _bg_action = "defer" if prior_defers < 1 else "evict"
                # budget-guard-defers-near-complete-feature Phase 3: a NEAR-COMPLETE
                # feature is at the finish line — dead-lettering it via eviction is
                # exactly the bug. When the one-shot grace is spent (prior_defers>=1)
                # such a feature would otherwise evict here; instead we keep it
                # DEFERRED (never escalate to evict) so the end-of-run resume flush
                # below can rescue it to validation. Monopoly protection is
                # unchanged for NON-near-complete features (they still escalate to
                # evict on the 2nd trip).
                if _bg_action == "evict" and _bg_near_complete:
                    _bg_action = "defer"
                    _diag(
                        f"budget-guard: {name} — near-complete (verification-only "
                        f"PHASES + plan-Complete, no BLOCKED.md) but grace already "
                        f"spent this run; HELD AS DEFERRED (not evicted) so the "
                        f"end-of-run resume flush can finish its validation."
                    )
                if _bg_action == "defer":
                    _bg_deferred_counts[feature_id] = prior_defers + 1
                    _diag(
                        f"budget-guard: {name} — per-feature forward cycles "
                        f"({_bg_count}) reached the computed ceiling ({_bg_ceiling}); "
                        f"deferred to the live-queue tail (run-scoped). Advancing to "
                        f"the next ready item."
                    )
                else:
                    if feature_id not in _bg_evicted:
                        _bg_evicted.append(feature_id)
                    _diag(
                        f"budget-guard: {name} — 2nd budget trip this run "
                        f"({_bg_count} >= {_bg_ceiling}); TERMINAL EVICTION "
                        f"(dead-lettered, removed from the live queue). On-disk "
                        f"progress preserved for human audit."
                    )
                budget_deferred_skipped.append(feature_id)
                # Surface the FIRST trip's rich audit metadata (the orchestrator
                # translates it into a PushNotification reporting the COMPUTED
                # ceiling). next_id is back-filled after the loop picks a dispatch.
                if _BUDGET_GUARD is None:
                    # sub_skill_phase: cheap, best-effort PHASES current-phase of the
                    # tripped feature (audit-only context — the orchestrator reports
                    # it in the trip notification). First In-progress phase heading,
                    # else the first phase heading, else None.
                    _bg_phase = None
                    try:
                        _bg_phases_md = spec_path / "PHASES.md"
                        if _bg_phases_md.exists():
                            _bg_recs = lazy_core.parse_phases(
                                _bg_phases_md.read_text(encoding="utf-8")
                            )
                            _bg_inprog = [
                                r for r in _bg_recs
                                if (r.get("status") or "") == "In-progress"
                            ]
                            _bg_pick = _bg_inprog[0] if _bg_inprog else (
                                _bg_recs[0] if _bg_recs else None
                            )
                            if _bg_pick is not None:
                                _bg_phase = _bg_pick.get("heading")
                    except (OSError, ValueError):
                        _bg_phase = None
                    _BUDGET_GUARD = {
                        "feature_id": feature_id,
                        "count_at_trip": _bg_count,
                        "computed_ceiling": _bg_ceiling,
                        "action": _bg_action,
                        "next_id": None,
                        "sub_skill_phase": _bg_phase,
                        "commit_hash": lazy_core.git_head_short_sha(repo_root),
                        # budget-guard-defers-near-complete-feature Phase 2: the
                        # composite-signal context for this trip. A trip means
                        # grace was NOT granted (either not near-complete, or the
                        # one-shot grace was already consumed → False).
                        "effective_count": _bg_signals["effective_count"],
                        "corrective_count": _bg_corrective,
                        "near_complete_grace_granted": False,
                    }
                    # mechanize-prose-only-orchestrator-contracts (d): script-
                    # fired budget-guard trip notification — the FIRST trip
                    # surfaced this probe (mirrors the rich-audit-metadata
                    # gate above; notify_event's own content-based dedup
                    # additionally makes repeated observations across probes
                    # idempotent).
                    lazy_core.notify_event(
                        "budget-trip", f"{name} budget-guard {_bg_action}",
                        str(repo_root), item_id=feature_id,
                        detail=(
                            f"count={_bg_count} ceiling={_bg_ceiling} "
                            f"action={_bg_action}"
                        ),
                    )
                _DEFERRED_BUDGET.append(feature_id)
                continue
        # queue-dependency-dag Phase 2: the dep-gate (D2-A). An entry whose
        # queue `deps` (D1: the flat hard-only enforcement projection of the
        # SPEC dep-block) contain an id that is not receipt-gated-complete
        # (D3) is HELD — recorded in the dep_gated probe list and skipped with
        # a _diag audit line — so the walk naturally lands on the dependency
        # first (an ORDER CORRECTION, not a skip-past-halted-work: no
        # independent:true rail is demanded of the successor). Transitivity is
        # emergent — a still-queued dep is incomplete by construction, so a
        # C→B→A chain holds C and B with no graph traversal. A dangling or
        # retired (Superseded) dep is the D4 fail-fast: canonical BLOCKED.md
        # (blocker_kind: unknown-dependency) on the DEPENDENT, halting
        # terminal_reason="blocked" — the unknown-host-capability shape.
        # Placed AFTER the completion/cloud/device/host/research/park/budget
        # skips and BEFORE the skip-ahead branch; runs regardless of
        # --strict-research-halt (a correctness gate on an opt-in field, not a
        # throughput optimization — there is no legacy behavior to restore for
        # entries that carry `deps`). Entries WITHOUT `deps` never enter this
        # block — byte-identical on every path.
        #
        # queue-dependency-dag Phase 4 (D5): probe-time DRIFT diagnostic —
        # gated on the entry CARRYING a `deps` key (an opted-in entry), so
        # legacy entries (no key) emit nothing even when their SPEC has a dep
        # block. Compares the queue set against the SPEC's parsed hard-dep set
        # (reusing _hc_spec_text — the walk's existing per-entry SPEC read, so
        # zero additional file I/O). Lint-grade: a mismatch warns, never halts.
        if "deps" in entry:
            _drift_spec_hard = sorted({
                d["feature_id"]
                for d in parse_dep_block(_hc_spec_text)
                if d.get("kind") == "hard"
            })
            _drift_queue = sorted(set(lazy_core.dep_ids(entry)))
            if _drift_spec_hard != _drift_queue:
                _diag(
                    f"dep-drift: '{feature_id}' queue deps {_drift_queue!r} != "
                    f"SPEC hard deps {_drift_spec_hard!r} — re-run "
                    f"`--sync-deps --id {feature_id}` to re-project "
                    f"(lint-grade warning; not a halt)."
                )
        _dg_deps = lazy_core.dep_ids(entry)
        if _dg_deps:
            if _dep_dir_map is None:
                _dep_dir_map = {
                    e.get("id"): (
                        repo_root / "docs" / "features" / e.get("spec_dir")
                    ).resolve()
                    for e in queue
                    if isinstance(e, dict) and e.get("id") and e.get("spec_dir")
                }
            _dg_missing: list[str] = []
            _dg_bad: tuple[str, str] | None = None
            for _dg_dep in _dg_deps:
                _dg_status = lazy_core.dep_completion_status(
                    _dg_dep, repo_root, pipeline="feature",
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
                blocked_file = spec_path / "BLOCKED.md"
                if not blocked_file.exists():
                    body = lazy_core.format_unknown_dependency_blocker(
                        feature_id, _dg_bad[0], _dg_bad[1],
                        sorted(_dep_dir_map or {}),
                    )
                    _write_yaml_blocked_sentinel(
                        blocked_file,
                        feature_id=feature_id,
                        phase="Dependency validation",
                        blocker_kind="unknown-dependency",
                        blocked_at=lazy_core.utc_now_iso(),
                        retry_count=0,
                        body=body,
                    )
                _diag(
                    f"unknown-dependency: {name} declares queue dep "
                    f"'{_dg_bad[0]}' which classified {_dg_bad[1]!r} — wrote "
                    f"BLOCKED.md (blocker_kind: unknown-dependency). Fix the "
                    f"SPEC dep-block + --sync-deps, or drop the dep."
                )
                return _state(
                    feature_id=feature_id,
                    feature_name=name,
                    spec_path=str(spec_path),
                    current_step="Step 3: blocked",
                    terminal_reason="blocked",
                    notify_message=(
                        f"BLOCKED: {name} — queue dependency '{_dg_bad[0]}' is "
                        f"{_dg_bad[1]} (unknown-dependency). Awaiting input."
                    ),
                )
            if _dg_missing:
                _DEP_GATED.append({"id": feature_id, "missing": _dg_missing})
                _diag(
                    f"dep-gate: '{feature_id}' held — dep(s) "
                    f"{', '.join(repr(m) for m in _dg_missing)} not Complete "
                    f"(receipt-gated); advancing."
                )
                continue
        # feature-budget-guard-and-skip-ahead Phase 3: dependency-aware skip-ahead
        # past a gated head (default-on; --strict-research-halt disables it). This
        # is the FINAL gate before a candidate is dispatched, so it sees only
        # candidates that survived every prior skip (completion / cloud / device /
        # research-batch / park / budget). Two cases:
        #   (1) This candidate is itself GATED (research-pending or BLOCKED). Under
        #       default skip-ahead we record it as a gated head (gated_ids +
        #       _GATED_HEADS), log the audit line, and `continue` past it — its
        #       on-disk state is untouched and it is surfaced at the end-of-run
        #       flush. Under --strict-research-halt we do NOT skip: fall through to
        #       dispatch it so the legacy halt-on-first-gated-head behavior is
        #       reproduced (Step 3 BLOCKED.md / Step 5 needs-research terminal
        #       fires below exactly as before).
        #   (2) A gated head was already skipped this probe (gated_ids non-empty)
        #       and this candidate is downstream/unmarked. skip_ahead_ready is the
        #       two-key predicate (no hard dep on a gated id AND independent:true);
        #       a candidate that FAILS it is NOT dispatched (degrades to today's
        #       strict halt for that item) — recorded in skip_ahead_blocked and
        #       skipped. A candidate that PASSES dispatches normally below.
        if not strict_research_halt:
            _gk = _gated_head_kind(spec_path)
            if _gk is not None:
                gated_ids.add(feature_id)
                _GATED_HEADS.append(feature_id)
                # research-gated-head-buried-by-skip-ahead-and-merged-fallthrough:
                # track the research-pending subset so the merged-head path can
                # surface it distinctly from a BLOCKED head.
                if _gk == "research":
                    _RESEARCH_GATED_HEADS.append(feature_id)
                # Remember the FIRST gated head as a fallback dispatch target. If
                # the loop exhausts with NO skip-ahead-ready candidate found (e.g.
                # a single-item queue, or every other item is downstream/unmarked),
                # we dispatch this gated head normally so its per-feature terminal
                # (Step 3 BLOCKED / Step 5 needs-research) fires for the orchestrator
                # to act on — preserving single-/lazy behavior byte-for-byte. The
                # skip is only REALIZED when an independent alternative actually
                # exists. (This is what keeps the pre-feature single-item
                # needs-research / blocked terminals unchanged.)
                if gated_head_fallback is None:
                    gated_head_fallback = {
                        "name": name,
                        "id": feature_id,
                        "spec_path": spec_path,
                        "tier": entry.get("tier"),
                        "queue_entry": entry,
                    }
                _diag(
                    f"skip-ahead: '{feature_id}' is a gated head "
                    f"(research-pending or BLOCKED); advancing past it to the next "
                    f"skip-ahead-ready item (default-on; --strict-research-halt "
                    f"restores the legacy halt)."
                )
                continue
            if gated_ids:
                # A gated head was skipped earlier this probe — this candidate may
                # only be dispatched if it passes the two-key readiness predicate.
                try:
                    _sa_spec_text = (spec_path / "SPEC.md").read_text(encoding="utf-8") \
                        if (spec_path / "SPEC.md").exists() else ""
                except OSError:
                    _sa_spec_text = ""
                # queue-dependency-dag Phase 3 (D7): key 1 evaluates the UNION
                # of SPEC hard deps ∪ queue `deps` (queue ids treated as hard,
                # tagged source=queue for the audit line). Strictly-additive
                # defense-in-depth — see _merged_skip_ahead_deps.
                _sa_deps = _merged_skip_ahead_deps(
                    parse_dep_block(_sa_spec_text), lazy_core.dep_ids(entry)
                )
                _sa_independent = lazy_core.parse_independent_marker(
                    _sa_spec_text, entry
                )
                _sa_ready = lazy_core.skip_ahead_ready(
                    _sa_deps, gated_ids, _sa_independent
                )
                # Skip-ahead audit (RESEARCH_SUMMARY rich-audit leg): gated-head
                # id(s) + the skipped-to candidate + the evaluated dep array
                # (with each dep's source: spec | queue) + the readiness
                # verdict — emitted on EVERY skip-ahead evaluation.
                _diag(
                    f"skip-ahead audit: gated_heads={sorted(gated_ids)!r} "
                    f"candidate='{feature_id}' independent={_sa_independent} "
                    f"deps={[{'feature_id': d.get('feature_id'), 'kind': d.get('kind'), 'source': d.get('source')} for d in _sa_deps]!r} "
                    f"→ {'DISPATCH' if _sa_ready else 'SKIP (not skip-ahead-ready)'}"
                )
                if not _sa_ready:
                    _SKIP_AHEAD_BLOCKED.append(feature_id)
                    continue
        current = {
            "name": name,
            "id": feature_id,
            "spec_path": spec_path,
            "tier": entry.get("tier"),
            "queue_entry": entry,
        }
        break

    # feature-budget-guard-and-skip-ahead Phase 3: gated-head fallback (ADDITIVE
    # skip-ahead invariant). The loop exhausted without dispatching a skip-ahead-
    # ready candidate, yet at least one gated head was skipped past. A skip is only
    # ever REALIZED when an INDEPENDENT alternative actually dispatched (in which
    # case current is not None). Whenever no such alternative exists — a single
    # gated item, OR a gated head with only downstream/unmarked siblings — fall
    # back to dispatching the FIRST gated head normally so its per-feature terminal
    # (Step 3 BLOCKED / Step 5 needs-research) fires for the orchestrator to act on,
    # exactly as the pre-feature single-/lazy path did. This makes default-on skip-
    # ahead STRICTLY ADDITIVE: it changes behavior ONLY by advancing onto a genuine
    # independent item, never by stranding a gated head behind a false terminal. The
    # gated head is still surfaced (its own terminal is "not a false completion" — it
    # is the SPEC's all-gated clean terminal "or equivalent"). Byte-identity with the
    # pre-Phase-3 single-item path is preserved because _GATED_HEADS is cleared (no
    # skip was realized → no gated_heads probe key surfaces).
    if current is None and gated_head_fallback is not None:
        current = gated_head_fallback
        _GATED_HEADS = []
        # research-gated-head-buried-by-skip-ahead-and-merged-fallthrough: the
        # skip was NOT realized (the gated head IS the dispatched item → its
        # Step-5 needs-research / Step-3 blocked terminal fires directly), so
        # clear the research subset in lockstep — no research-halt surfacing is
        # needed when the research head is already the dispatched current item.
        _RESEARCH_GATED_HEADS = []
        # merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone: clear
        # the not-skip-ahead-ready skip list in lockstep — no independent skip was
        # realized (the gated head is dispatched directly), so the skip_ahead_blocked
        # probe key stays absent, preserving byte-identity with the pre-surfacing
        # baseline exactly as _GATED_HEADS is cleared here.
        _SKIP_AHEAD_BLOCKED = []
        gated_ids = set()
        _diag(
            f"skip-ahead: no skip-ahead-ready alternative to gated head "
            f"'{current['id']}' — dispatching it normally (per-feature terminal "
            f"fires). Skip not realized (additive invariant)."
        )

    # feature-budget-guard-and-skip-ahead Phase 2: persist the budget-guard marker
    # updates (deferral counts + eviction list) when any trip fired this probe.
    # Marker-gated + best-effort (a write error never breaks dispatch). The
    # deferral/eviction state must survive to the NEXT probe so a re-trip on the
    # same feature escalates (1st defer → 2nd evict) and an evicted feature stays
    # out of the live queue for the rest of the run.
    if _bg_marker is not None and _BUDGET_GUARD is not None:
        # Back-fill the dispatch target onto the surfaced trip metadata (the
        # sub_skill_phase of the TRIPPED feature was captured at trip time above).
        if current is not None:
            _BUDGET_GUARD["next_id"] = current["id"]
        try:
            _bg_fresh = lazy_core.read_run_marker()
            if isinstance(_bg_fresh, dict):
                _bg_fresh["budget_deferred"] = _bg_deferred_counts
                _bg_fresh["budget_evicted"] = _bg_evicted
                _bg_marker_path = lazy_core.claude_state_dir() / lazy_core._MARKER_FILENAME
                lazy_core._atomic_write(
                    _bg_marker_path, json.dumps(_bg_fresh, indent=2) + "\n"
                )
        except (OSError, ValueError):
            pass

    if current is None:
        # budget-guard-defers-near-complete-feature Phase 3: end-of-run
        # near-complete resume flush (the documented safety net for Theory 3).
        # The queue exhausted to ONLY budget-deferred/evicted items. Before
        # returning the queue-exhausted-budget-deferred terminal, re-scan the
        # budget-deferred features (this-probe skip list) IN QUEUE ORDER and, for
        # the FIRST one that is NOW near-complete AND was NOT evicted (terminal
        # eviction is intentional dead-lettering — never auto-resumed), DISPATCH it
        # to validation instead of parking it for a future run (where it risks a
        # 2nd-trip eviction and leaves a hot runtime idle). Near-completion is
        # re-evaluated at flush time (independent of the Phase-2 grace flag). One
        # resume per probe — the next probe resumes the next near-complete deferred
        # feature; the terminal fires only when NONE qualifies. Marker-gated (the
        # whole budget guard is marker-gated) — absent a marker budget_deferred_skipped
        # is empty and this is a no-op.
        if _bg_marker is not None and budget_deferred_skipped:
            _bg_deferred_set = set(budget_deferred_skipped)
            for _fl_entry in queue:
                _fl_id = _fl_entry.get("id")
                _fl_sub = _fl_entry.get("spec_dir")
                _fl_name = _fl_entry.get("name")
                if not _fl_id or not _fl_sub or not _fl_name:
                    continue
                if _fl_id not in _bg_deferred_set or _fl_id in _bg_evicted:
                    continue
                _fl_spec = (repo_root / "docs" / "features" / _fl_sub).resolve()
                if not _fl_spec.exists():
                    continue
                if not lazy_core.feature_is_near_complete(_fl_spec, repo_root):
                    continue
                # Resume this near-complete deferred feature to validation.
                current = {
                    "name": _fl_name,
                    "id": _fl_id,
                    "spec_path": _fl_spec,
                    "tier": _fl_entry.get("tier"),
                    "queue_entry": _fl_entry,
                }
                _BUDGET_RESUMED = _fl_id
                _diag(
                    f"budget-guard: end-of-run resume flush — deferred feature "
                    f"'{_fl_id}' is now near-complete (verification-only PHASES + "
                    f"plan-Complete, no BLOCKED.md); RESUMED to validation instead "
                    f"of parking it for a future run. (budget_resumed_near_complete)"
                )
                break

    if current is None:
        # feature-budget-guard-and-skip-ahead Phase 2: honest exhaustion terminal.
        # When the queue advanced past every workable item and the ONLY reason
        # nothing dispatched is the budget guard (deferred/evicted items), return a
        # distinct terminal — NOT all-features-complete (a false completion).
        # Placed BEFORE the generic all-parked / all-complete fallbacks but AFTER
        # the specific global terminals (cloud/device/research/scoped-id keep their
        # precedence). Gated on a budget-deferral having actually occurred.
        if _bg_marker is not None and budget_deferred_skipped and not (
            (cloud and cloud_saturated_skipped)
            or ((not real_device) and device_saturated_skipped)
            or _HOST_SATURATED
            or (skip_needs_research and research_pending_skipped)
            or (scope_feature_id is not None and not scope_id_seen)
        ):
            return _state(
                terminal_reason="queue-exhausted-budget-deferred",
                notify_message=(
                    f"Queue exhausted — {len(budget_deferred_skipped)} feature(s) "
                    "deferred/evicted by the per-feature budget guard; their on-disk "
                    "progress is preserved and surfaced at the end-of-run flush."
                ),
            )
        # feature-budget-guard-and-skip-ahead Phase 3 note: there is no separate
        # "all-gated" terminal here. The gated-head fallback above ALWAYS dispatches
        # the first gated head when no skip-ahead-ready alternative was found, so a
        # current-is-None state with gated heads cannot occur — the gated head's own
        # per-feature terminal (Step 3 blocked / Step 5 needs-research) is the SPEC's
        # all-gated clean terminal "or equivalent" (never a false completion). The
        # existing --skip-needs-research batch path below keeps its own
        # queue-blocked-on-research terminal unchanged.
        if cloud and cloud_saturated_skipped:
            return _state(
                terminal_reason="cloud-queue-exhausted",
                notify_message=(
                    f"Cloud queue exhausted — {len(cloud_saturated_skipped)} feature(s) "
                    "awaiting workstation /lazy for MCP test."
                ),
            )
        if (not real_device) and device_saturated_skipped:
            # Device-axis mirror of cloud-queue-exhausted. The no-device host has
            # done everything it can; the listed features carry deferred
            # real-device-only assertions awaiting a real-device /lazy host.
            # (Per-feature diagnostics were already emitted inline at the skip
            # site above, on every probe — not just here at exhaustion.)
            return _state(
                terminal_reason="device-queue-exhausted",
                notify_message=(
                    f"Device queue exhausted — {len(device_saturated_skipped)} feature(s) "
                    "carry real-device-only assertions deferred to a real-device "
                    "/lazy host (set ALGOBOOTH_REAL_AUDIO_DEVICE=1 or run on native "
                    "hardware)."
                ),
            )
        # host-capability-declaration-for-gated-features Phase 5: the
        # host-capability-saturated terminal (the host-axis generalization of
        # device-queue-exhausted). Placed beside device-queue-exhausted with the
        # SAME precedence ordering — after the budget-deferred / cloud / device
        # terminals, before research / scoped-id / all-complete — so a host-gated
        # remainder is an HONEST distinct terminal, NOT a false all-features-
        # complete. Gated on a host-deferral having actually occurred this probe.
        if _HOST_SATURATED:
            # The notification names the feature + missing cap id(s) per the SPEC
            # format: "host-capability miss — <feature-id> requires <cap-id>
            # (absent on this host); deferred to capability-host".
            _hc_lines = "; ".join(
                f"{rec['feature_id']} requires {', '.join(rec['missing'])}"
                for rec in _HOST_SATURATED
            )
            return _state(
                terminal_reason="host-capability-saturated",
                notify_message=(
                    f"host-capability miss — {_hc_lines} (absent on this host); "
                    f"deferred to capability-host. "
                    f"{len(_HOST_SATURATED)} feature(s) await a capability-bearing "
                    "host."
                ),
            )
        # merged-head-oracle-per-signal-supplement-churn Phase 1: the global
        # all-remaining-deferred terminal (feature-side mirror of bug-state.py).
        # When the walk advanced past every workable feature and the ONLY reason
        # nothing dispatched is that the remaining features were operator-parked
        # via DEFERRED.md, return a distinct terminal — NOT all-features-complete,
        # which would be a false completion. Placed beside the device/host
        # terminals (after budget/cloud/device/host, before research/scoped-id/
        # all-parked) so an operator-deferred remainder is honestly surfaced. The
        # queue isn't empty — it's paused by the operator; re-include by deleting
        # each DEFERRED.md. NOT in SANCTIONED_STOP_TERMINAL (matching the bug side).
        if _OPERATOR_DEFERRED:
            return _state(
                terminal_reason=TR_ALL_DEFERRED,
                current_step="All remaining features are operator-deferred",
                notify_message=(
                    f"All remaining features are operator-deferred — "
                    f"{len(_OPERATOR_DEFERRED)} feature(s) parked via DEFERRED.md. "
                    "Re-include by deleting DEFERRED.md in each feature dir."
                ),
            )
        if skip_needs_research and research_pending_skipped:
            for fname in research_pending_skipped:
                _diag(f"research-pending skipped: {fname}")
            return _state(
                terminal_reason="queue-blocked-on-research",
                notify_message=(
                    f"Queue blocked — {len(research_pending_skipped)} feature(s) "
                    "awaiting Gemini research uploads."
                ),
            )
        # scoped-id-not-found: --feature-id was given but matched no queue entry.
        # This is distinct from "queue exhausted" — the id itself is unknown.
        # Placed here (after all other specific terminals) because when the scope
        # id is a typo none of the skip-lists will have populated.
        if scope_feature_id is not None and not scope_id_seen:
            return _state(
                terminal_reason="scoped-id-not-found",
                notify_message=(
                    f"--feature-id '{scope_feature_id}' matched no entry in "
                    "docs/features/queue.json — check the id (typo?) or that the "
                    "feature is queued. No cycle was dispatched."
                ),
            )
        # queue-dependency-dag D4: honest all-dep-gated terminal. The walk
        # exhausted and at least one item was HELD on an incomplete declared
        # dependency this probe — a clean, sanctioned stop (the holds re-open
        # automatically as their deps complete), NOT all-features-complete (a
        # false completion). Placed AFTER the specific global terminals above
        # (cloud/device/host/research/scoped-id keep their precedence) and
        # BEFORE the all-parked fallback (a dep-gated item is held for a more
        # specific reason than "parked"); the flush names each held item and
        # its incomplete deps. Gated on a hold having actually occurred, so
        # dep-less queues are byte-identical.
        if _DEP_GATED:
            _dg_lines = "; ".join(
                f"{r['id']} waiting on {', '.join(r['missing'])}"
                for r in _DEP_GATED
            )
            return _state(
                terminal_reason="queue-exhausted-dependency-gated",
                notify_message=(
                    f"Queue exhausted — {len(_DEP_GATED)} item(s) "
                    f"dependency-gated: {_dg_lines}. Each re-opens "
                    "automatically once its dependencies are Complete with a "
                    "receipt."
                ),
            )
        # Honest all-parked terminal (SPEC D3): when every remaining feature was
        # parked this probe (NEEDS_INPUT and/or BLOCKED) so current is None with a
        # non-empty _PARKED, return a distinct terminal — NOT all-features-complete,
        # which would be a false completion. Placed as the fallback AFTER the
        # specific global terminals above (cloud/device/research/scoped-id keep
        # their precedence per D2) and BEFORE all-features-complete.
        if _PARKED:
            return _state(
                terminal_reason="queue-exhausted-all-parked",
                notify_message=(
                    f"Queue exhausted — {len(_PARKED)} feature(s) parked "
                    "(blocked/needs-input); surfaced at the end-of-run flush."
                ),
            )
        return _state(
            terminal_reason="all-features-complete",
            notify_message="ALL FEATURES COMPLETE — roadmap finished.",
        )

    feature_name = current["name"]
    feature_id = current["id"]
    spec_path: Path = current["spec_path"]
    spec_path_str = str(spec_path)

    common = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "spec_path": spec_path_str,
    }

    # Step 2.9: upstream WI changed since materialize — halt for re-materialize.
    if lazy_core.read_stale_upstream(spec_path) is not None:
        return _state(
            **common,
            current_step=STEP_STALE_UPSTREAM,
            terminal_reason=TR_STALE_UPSTREAM,
            notify_message=f"STALE UPSTREAM: {feature_name} — upstream WI changed since materialize; re-materialize required.",
        )

    # Step 3: BLOCKED.md
    blocked_file = spec_path / "BLOCKED.md"
    if blocked_file.exists():
        meta = parse_sentinel(blocked_file) or {}
        # spike-pipeline-role Phase 2 (WU-2): a BLOCKED.md naming Spike as its
        # resolver routes to a `spike` cycle instead of the generic manual-block
        # terminal — the second spike entry signal (the ad-hoc / blocked one).
        # Fires unconditionally on the blocker_kind (the retry-past-threshold
        # `spike_escalation` predicate is a separate Part-3-consumed signal, not
        # a gate on this routing). Placed before the generic `blocked` terminal.
        if meta.get("blocker_kind") == "runtime-spike-verdict-pending":
            # spike-pipeline-role Phase 4 (WU-2): the bounded tooling-existence
            # loop guard — a persisted spike_tooling_rounds count at/above the
            # cap means the tooling gap keeps recurring, so route to an
            # operator NEEDS_INPUT halt instead of dispatching another spike
            # round (checked BEFORE the unconditional route-to-spike below).
            if lazy_core.spike_tooling_cap_exceeded(meta):
                lazy_core.write_spike_tooling_cap_needs_input(
                    spec_path, feature_name, meta.get("spike_tooling_rounds")
                )
                lazy_core._diag(
                    "Step 3: spike_tooling_rounds cap exceeded → needs-input "
                    "(loop bounded, no further spike route)"
                )
                return _state(
                    **common,
                    current_step="Step 3: spike tooling-round cap exceeded",
                    terminal_reason="needs-input",
                    notify_message=(
                        f"NEEDS INPUT: {feature_name} — spike tooling gap "
                        "persists after the corrective-round cap; operator "
                        "decision needed."
                    ),
                )
            lazy_core._diag(
                "Step 3: BLOCKED.md blocker_kind=runtime-spike-verdict-pending "
                "→ routing to spike (blocked resolver)"
            )
            return _state(
                **common,
                current_step="Step 3: spike verdict pending (blocked resolver)",
                sub_skill="spike",
                sub_skill_args=(
                    f"resolve the spike blocker for {feature_name}: run the "
                    f"runtime proof and write SPIKE_VERDICT.md (verdict: "
                    f"PASS|FAIL, with observed evidence) in {spec_path_str}, "
                    f"then neutralize BLOCKED.md. See {spec_path_str}/SPEC.md."
                ),
            )
        phase = meta.get("phase", "unknown")
        notify_message = f"BLOCKED: {feature_name} — {phase}. Awaiting input."
        # Validation-escalation payload (Phase 11 WU-1a): blocker_kind
        # mcp-validation at retry_count >= 2 means repeated validation rounds
        # each found one more broken layer (the d8 serial-discovery pattern) —
        # the orchestrator must draft the corrective phase as a full-chain seam
        # audit, not another single-layer fix. The `validation_escalation` key
        # is added ONLY in the escalation case (post-hoc, mirroring the
        # _PARK_MODE "parked" invariant) so non-escalated output — including
        # every existing retry_count: 0 fixture — stays byte-identical.
        escalated = lazy_core.validation_escalation(meta)
        if escalated:
            notify_message += lazy_core.VALIDATION_ESCALATION_SUFFIX
        state = _state(
            **common,
            current_step="Step 3: blocked",
            terminal_reason="blocked",
            notify_message=notify_message,
        )
        if escalated:
            state["validation_escalation"] = True
        return state

    # Step 3 (cont.): mis-named blocker (noncanonical-blocker-filename-invisible-
    # to-state-machine). A blocker written under a non-canonical name — e.g.
    # BLOCKED_2026-06-09-foo.md or a lowercase blocked.md — is invisible to the
    # literal BLOCKED.md check above, so the state machine would re-route the item
    # straight back into the same wall (infinite-loop risk). Detect the stray via
    # the shared single-writer helper (which returns None when canonical BLOCKED.md
    # is present, so this only fires when canonical is ABSENT — the check above
    # already returned in that case) and halt on a DISTINCT terminal so the human
    # renames it to BLOCKED.md (or neutralizes it). Inline literals mirror the
    # canonical-BLOCKED block's style above.
    stray_blocked = lazy_core.detect_noncanonical_blocker(spec_path)
    if stray_blocked is not None:
        return _state(
            **common,
            current_step="Step 3: mis-named blocker",
            terminal_reason="blocked-misnamed",
            notify_message=(
                f"MIS-NAMED BLOCKER: {feature_name} — found '{stray_blocked.name}', "
                "which the state machine cannot see (only the canonical 'BLOCKED.md' "
                "halts the pipeline). Rename it to 'BLOCKED.md' or neutralize it."
            ),
        )

    # NEEDS_INPUT.md (batch-mode halt)
    needs_input_file = spec_path / "NEEDS_INPUT.md"
    if needs_input_file.exists():
        meta = parse_sentinel(needs_input_file) or {}
        writer = meta.get("written_by", "<unknown>")
        return _state(
            **common,
            current_step="Step 3.5: needs-input",
            terminal_reason="needs-input",
            notify_message=(
                f"NEEDS INPUT: {feature_name} — {writer} halted on an ambiguous decision."
            ),
        )

    # Step 3.6: NEEDS_INPUT_PROVISIONAL.md (park-provisional-acceptance, SPEC D5).
    # An unratified provisionally-accepted decision. In PARK MODE the file is
    # workable — the walk-loop branch recorded it in provisional[] (and parks
    # it once VALIDATED.md lands), so this halt is gated on NOT park mode: a
    # plain (non-park) probe halts here so the operator ratifies or redirects
    # via the provisional-ratification affordance before any completion.
    # Ordering: AFTER the NEEDS_INPUT.md check — a NEW decision outranks a
    # pending ratification when both sentinels exist.
    provisional_file = spec_path / lazy_core.PROVISIONAL_SENTINEL
    if provisional_file.exists() and not park_needs_input:
        prov_meta = parse_sentinel(provisional_file) or {}
        prov_writer = prov_meta.get("written_by", "<unknown>")
        return _state(
            **common,
            current_step=STEP_NEEDS_RATIFICATION,
            terminal_reason=TR_NEEDS_RATIFICATION,
            notify_message=(
                f"NEEDS RATIFICATION: {feature_name} — decision(s) originally "
                f"surfaced by {prov_writer} were provisionally auto-accepted on "
                "recommendation (--park-provisional). Ratify or redirect before "
                "this feature can complete."
            ),
        )

    # Step 4: SPEC.md
    spec_file = spec_path / "SPEC.md"
    if not spec_file.exists():
        # Check if directory has any files (research, etc.)
        has_files = spec_path.exists() and any(
            p.is_file() and p.name not in ("BLOCKED.md", "NEEDS_INPUT.md")
            for p in spec_path.iterdir()
        )
        if not has_files:
            return _state(
                **common,
                current_step="Step 4: no SPEC, no research",
                terminal_reason="needs-spec-input",
                notify_message=(
                    f"{feature_name} needs spec input — no SPEC.md or research found. "
                    "Provide direction via /spec."
                ),
            )
        # Ad-hoc enqueue path: an ADHOC_BRIEF.md seed (written by
        # --enqueue-adhoc) routes to /spec with a brief-specific arg so /spec
        # treats it as the task brief rather than "prior research".
        if (spec_path / "ADHOC_BRIEF.md").exists():
            return _state(
                **common,
                current_step="Step 4: ad-hoc brief → spec",
                sub_skill="spec",
                sub_skill_args=(
                    f"{feature_name} — ad-hoc task; see "
                    f"{spec_path_str}/ADHOC_BRIEF.md for the brief"
                ),
            )
        return _state(
            **common,
            current_step="Step 4: SPEC missing, research files present",
            sub_skill="spec",
            sub_skill_args=f"{feature_name} — see {spec_path_str} for prior research",
        )

    spec_text = spec_file.read_text(encoding="utf-8")

    # Step 4.5: Stub spec
    #
    # stub-spec-route-loops-until-queue-stub-cleared: when the queue.json
    # `"stub"` flag is the LONE surviving stub marker (the `/spec` Phase 1
    # rewrite already dropped the SPEC-text markers but nobody cleared the queue
    # flag), the baseline is locked. Clear the flag exactly once — under script
    # ownership, never an orchestrator hand-edit (HARD CONSTRAINT 1) — and FALL
    # THROUGH to Step 4.6 / Step 5, closing the commit-masked Step-4.5 loop. The
    # discriminator is reachable only post-baseline (SPEC-text markers gone), so
    # it never fires on a true pre-baseline stub.
    if _stub_is_queue_flag_only(spec_text, current.get("queue_entry")):
        clear_result = lazy_core.clear_queue_stub(
            repo_root / "docs" / "features" / "queue.json", feature_id
        )
        _diag(
            f"Step 4.5 clear-and-advance: queue stub flag was the lone surviving "
            f"marker for {feature_id} (baseline locked) — cleared "
            f"(cleared={clear_result.get('cleared')}), advancing to Step 5"
        )
        # Fall through to Step 4.6 / Step 5 (do NOT return / re-dispatch /spec).
    elif is_stub_spec(spec_text, current.get("queue_entry")):
        return _state(
            **common,
            current_step="Step 4.5: stub-spec detected",
            sub_skill="spec",
            sub_skill_args=(
                f"{feature_name} — existing stub at {spec_path_str}/SPEC.md is auto-generated "
                "from research summary; treat as starting context for Phase 1 brainstorming "
                "and overwrite when baseline is locked in"
            ),
        )

    # Step 4.6: upstream realign check
    deps = parse_dep_block(spec_text)
    hard_complete_upstream_dirs: list[Path] = []
    for dep in deps:
        if dep["kind"] != "hard":
            continue
        ud = resolve_upstream_dir(repo_root, spec_path, dep["feature_id"])
        if ud is None:
            continue
        if upstream_is_complete(repo_root, ud):
            hard_complete_upstream_dirs.append(ud)

    if hard_complete_upstream_dirs and not realign_is_fresh(spec_path, hard_complete_upstream_dirs):
        return _state(
            **common,
            current_step="Step 4.6: upstream realign needed",
            sub_skill="realign-spec",
            # --apply pushes the act-on-recommendation logic into /realign-spec
            # itself so the orchestrator subagent doesn't need follow-on logic.
            sub_skill_args=f"{spec_path_str}/SPEC.md --apply",
        )

    # Step 5: Research validation gate
    research = spec_path / "RESEARCH.md"
    research_summary = spec_path / "RESEARCH_SUMMARY.md"
    research_prompt = spec_path / "RESEARCH_PROMPT.md"
    needs_research_file = spec_path / "NEEDS_RESEARCH.md"

    # Pre-Step-5 guard (research-gate-ignores-existing-phases): the research
    # gate is a PRE-planning stage — a feature whose PHASES.md already shows
    # implementation evidence is past it, so re-running research wastes a Gemini
    # round-trip and loops the pipeline. When the file would otherwise route to
    # research (no RESEARCH*.md present) BUT PHASES.md exists with implementation
    # evidence, emit a diagnostic (D3 — never a silent skip) and fall through to
    # Step 6. The PHASES.md text read here is cached and reused at Step 6 so the
    # file is opened at most once per compute_state invocation. When research
    # already exists this branch never executes, so every existing path is
    # byte-identical (structural no-op).
    phases_file = spec_path / "PHASES.md"
    phases_text_cached: str | None = None
    skip_research_for_phases = False
    if not research.exists() and not research_summary.exists() and phases_file.exists():
        phases_text_cached = phases_file.read_text(encoding="utf-8")
        if lazy_core.phases_show_implementation(
            phases_text_cached, phases_path=phases_file
        ):
            skip_research_for_phases = True
            _diag(
                "Step 5 research gate skipped: PHASES.md present with "
                "implementation evidence — feature is past pre-planning research"
            )

    if (
        not skip_research_for_phases
        and not research.exists()
        and not research_summary.exists()
    ):
        # Persistent halt: if a NEEDS_RESEARCH sentinel is already present, the
        # orchestrator already dropped one in a prior cycle — surface and stop.
        if needs_research_file.exists():
            meta = parse_sentinel(needs_research_file) or {}
            prompt_rel = meta.get("research_prompt_path", "RESEARCH_PROMPT.md")
            return _state(
                **common,
                current_step="Step 5: needs-research (persistent)",
                terminal_reason="needs-research",
                notify_message=(
                    f"{feature_name}: research prompt exists at {prompt_rel} but no RESEARCH.md. "
                    "Run Gemini deep research and drop RESEARCH.md next to the prompt."
                ),
            )
        if research_prompt.exists():
            # Tell orchestrator to halt and (for batch orchestrators) write NEEDS_RESEARCH.md
            return _state(
                **common,
                current_step="Step 5: prompt exists, awaiting research",
                terminal_reason="needs-research",
                notify_message=(
                    f"{feature_name}: research prompt exists but no results. "
                    "Run Gemini deep research and provide results to /spec."
                ),
            )
        # No research at all → /spec Phase 2 (research prompt generation)
        return _state(
            **common,
            current_step="Step 5: generate research prompt",
            sub_skill="spec",
            sub_skill_args=(
                f"{feature_name} — SPEC.md already exists at {spec_path_str}/SPEC.md, "
                "skip to Phase 2 (research prompt generation)"
            ),
        )

    if research.exists() and not research_summary.exists():
        return _state(
            **common,
            current_step="Step 5: integrate research",
            sub_skill="spec",
            sub_skill_args=(
                f"{feature_name} — SPEC.md and RESEARCH.md exist at {spec_path_str}, "
                "skip to Phase 3 (integrate research and finalize spec)"
            ),
        )

    # Step 6: PHASES.md
    # `phases_file` was defined at the pre-Step-5 guard above; do not redefine it
    # (single definition per compute_state invocation).
    if not phases_file.exists():
        # Consolidated planning: dispatch /plan-feature (which runs /spec-phases
        # THEN /write-plan back-to-back) instead of /spec-phases alone. This
        # collapses the two planning cycles into one orchestrator round-trip —
        # the next probe sees PHASES.md + a plan on disk and routes straight to
        # /execute-plan, skipping the separate Step 7a write-plan dispatch.
        #
        # /plan-feature's hard precondition (SPEC.md + RESEARCH_SUMMARY.md both
        # present) is GUARANTEED here: the research gates above (the
        # `not research and not research_summary` and `research and not
        # research_summary` branches) make RESEARCH_SUMMARY.md a precondition of
        # ever reaching Step 6, so /plan-feature can never refuse on a missing
        # summary at this node. /plan-feature surfaces any NEEDS_INPUT.md its
        # sub-skills write (genuine design forks) and STOPs; the next probe sees
        # the sentinel and routes to needs-input as before. Step 7a (write-plan)
        # remains the fallback for a feature whose PHASES.md exists but has no
        # plan yet (e.g. after a NEEDS_INPUT resolution that neutralized the
        # sentinel write-plan halted on).
        return _state(
            **common,
            current_step="Step 6: plan feature (phases + plan)",
            sub_skill="plan-feature",
            sub_skill_args=f"{spec_path_str}/SPEC.md",
        )

    # Reuse the text already read by the pre-Step-5 guard when available
    # (no double read); only read here on the path where the guard did not run
    # (research present, so phases_text_cached is None).
    phases_text = (
        phases_text_cached
        if phases_text_cached is not None
        else phases_file.read_text(encoding="utf-8")
    )
    unchecked, checked = count_deliverables(phases_text)

    # Step 7: Phase completion
    if unchecked > 0:
        plans = find_implementation_plans(spec_path)
        verification_only = remaining_unchecked_are_verification_only(phases_text)
        # Step 7 bypass — fall through to the Step 9 MCP gate instead of
        # write-plan/execute-plan. Two DISTINCT discriminators, one per mode:
        #
        # Cloud: bypass when implementation is provably done (>=1 Complete plan
        # on disk) — cloud can't tick ANY workstation row regardless of whether
        # it's a verification or implementation row, so we can't use the
        # verification-only predicate as the "impl done" proxy; we need the
        # explicit Complete-plan receipt. Falls through to Step 9 (cloud defers
        # or honors an existing DEFERRED_NON_CLOUD.md); Step 2's cloud-saturated
        # skip eventually fires.
        #
        # Workstation: bypass when the unchecked remainder is ENTIRELY
        # verification rows — and crucially WITHOUT requiring a Complete plan on
        # disk. A verification-only remainder is itself proof that no
        # implementation work remains (write-plan is banned, Step 1c.5, from
        # emitting a verification-only re-run-/mcp-test WU), so there is nothing
        # for write-plan to plan. Requiring _has_any_complete_plan here was the
        # mcp-testing deadlock (2026-06-15): a feature implemented batch-by-batch
        # via PHASES checkboxes has NO plans/ dir, so _has_any_complete_plan is
        # False, control fell to `elif not plans` -> write-plan, which writes no
        # plan and returns -> identical state -> infinite write-plan loop. Any
        # feature implemented without a parent plans/ receipt whose only
        # remaining unchecked rows are Runtime Verification could never reach the
        # Step-9 MCP gate. The verification-only predicate is the correct,
        # plan-receipt-independent gate for the workstation case.
        #
        # The legacy combined form ALSO bypassed the workstation
        # verification-only case when a Complete plan happened to exist
        # (_has_any_complete_plan True + verification_only True); that path is
        # preserved — verification_only True now bypasses on workstation whether
        # or not a Complete plan exists. If any real implementation row is still
        # unchecked, verification_only is False and we write-plan as before.
        cloud_bypass = cloud and not plans and _has_any_complete_plan(spec_path)
        workstation_bypass = not cloud and not plans and verification_only
        if cloud_bypass or workstation_bypass:
            pass
        elif not plans:
            # Planner-name resolution (D1): the Cognito Forms repo ships a
            # repo-scoped lane planner installed as `write-plan-cognito`; emit
            # that name there so the advertised planner is the one that runs.
            # Every other repo keeps the generic `write-plan`. The executor
            # stage (Step 7b below) is unaffected — it always dispatches the
            # single generic `/execute-plan` (there is no execute-plan-cognito).
            planner = (
                "write-plan-cognito"
                if repo_uses_cognito_planner(repo_root)
                else "write-plan"
            )
            return _state(
                **common,
                current_step="Step 7a: write plan",
                sub_skill=planner,
                sub_skill_args=f"{spec_path_str}/PHASES.md",
            )
        else:
            # Use the lowest-ordered plan (sorted-name preference); if part-N
            # exists, this returns part-1 first which is what we want.
            plan = plans[0]
            # Stale-plan gate (all modes). When every work-unit referenced by
            # this plan's phases: scope is already checked ([x]) in PHASES.md,
            # the plan is stale — its work was completed in a prior session but
            # the plan's frontmatter was never flipped to Complete. Dispatching
            # /execute-plan in this state wastes an Opus cycle re-verifying work
            # that is already done (observed twice in production). Instead, flip
            # the plan Complete inline via the __flip_plan_complete_stale__
            # pseudo-action. The non-empty plan_phase_set guard is required: a
            # plan with no phases: field has an empty scope and must fall through
            # to execute-plan (its full scope is unknown so we cannot declare it
            # stale). This check runs before the cloud-saturation gate so a
            # fully-checked scope always flips stale regardless of cloud mode.
            plan_phase_set = _plan_phase_set(plan)
            if plan_phase_set:
                in_scope_unchecked = _unchecked_wus_in_plan_scope(
                    phases_text, plan_phase_set
                )
                # Phase 8 (lazy-validation-readiness) — close the /execute-plan
                # finalization gap, option (b). A plan is "finalize-stale" when,
                # within its phase scope, the only remaining-open WUs are
                # Step-9-owned Runtime-Verification rows (the impl is done; only
                # the verification subsections the MCP cycle ticks remain). The
                # plan's frontmatter is still Ready/In-progress, so without this
                # branch lazy-state re-dispatches a full /execute-plan cycle that
                # does nothing but flip the plan to Complete (d7-multi-timbral
                # Phase 11: cycle 33 ticked everything, cycle 34 burned ~97k tok
                # just to flip the status). Routing those cases to the existing
                # __flip_plan_complete_stale__ pseudo-action makes the state
                # machine self-correct regardless of which /execute-plan revision
                # ran (more robust than tightening the skill prose alone — the
                # rejected option (a); see PHASES.md Implementation Notes).
                #
                # Two finalize-stale shapes, both routed to the pseudo-action:
                #   (1) ZERO in-scope unchecked WUs (the original stale-plan
                #       gate — every referenced WU is already [x]).
                #   (2) The in-scope unchecked remainder is ENTIRELY
                #       verification-only rows (the Phase-8 addition). We scope
                #       PHASES.md down to the plan's phases and reuse the
                #       verification-only predicate so a genuine implementation
                #       row in scope still falls through to /execute-plan.
                # Empty-PHASES-scope guard (decomposition-part vacuous-stale fix,
                # f1-global-scale part-0, 2026-06-19). _unchecked_wus_in_plan_scope()
                # returning [] is AMBIGUOUS: it means EITHER (a) every referenced WU
                # is already [x] (genuinely stale) OR (b) the plan's phases: scope
                # resolves to ZERO rows in PHASES.md (scope UNDEFINED — not "done").
                # Case (b) is real: write-plan emits a `phases: [0]` decomposition
                # part for touchpoint-audit `block` verdicts but adds no matching
                # `### Phase 0` section to PHASES.md (the decomposition WUs live in
                # the PLAN BODY). Treating (b) as stale vacuously flips the plan
                # Complete and SILENTLY DROPS the decomposition. Disambiguate via the
                # TOTAL (checked + unchecked) in-scope row count.
                scope_total = _all_wus_in_plan_scope(phases_text, plan_phase_set)
                if scope_total:
                    # Phase scope has >=1 deliverable row in PHASES.md — the original
                    # PHASES-scoped gate applies (shapes (1) all-checked, (2)
                    # verification-only remainder).
                    scoped_text = _phases_text_scoped_to(phases_text, plan_phase_set)
                    finalize_stale = (
                        not in_scope_unchecked
                        or remaining_unchecked_are_verification_only(scoped_text)
                    )
                else:
                    # Phase scope resolves to ZERO PHASES.md rows -> fall back to the
                    # plan's OWN per-WU checkboxes (the ISSUE-6 machine source of truth
                    # /execute-plan ticks). Stale ONLY when the plan has parseable WU
                    # boxes AND every non-verification one is already [x]; ANY unchecked
                    # real WU, or no parseable boxes at all, -> NOT stale -> fall
                    # through to /execute-plan so the decomposition actually runs.
                    plan_text = plan.read_text(encoding="utf-8", errors="replace")
                    wu_unchecked, wu_checked = _plan_wu_checkbox_counts(plan_text)
                    finalize_stale = bool(wu_checked) and (
                        wu_unchecked == 0
                        or _plan_unchecked_wus_are_verification_only(plan_text)
                    )
                if finalize_stale:
                    # Stale already-applied plan: every implementation WU this plan
                    # references (scoped to its phases: field) is already [x] — only
                    # Step-9 verification rows (if any) remain — yet its frontmatter is
                    # still Ready/In-progress and PHASES.md still has unchecked rows
                    # elsewhere so we reached this branch. Dispatching /execute-plan
                    # would burn an Opus cycle re-verifying a plan whose work is already
                    # done (observed in production). Flip it Complete inline via the
                    # __flip_plan_complete_stale__ pseudo-action instead.
                    return _state(
                        **common,
                        current_step="Step 7a: flip plan Complete (stale — all referenced implementation deliverables already checked)",
                        sub_skill="__flip_plan_complete_stale__",
                        sub_skill_args=str(plan),
                    )
            # Cloud-saturation gate (cloud mode only). When a plan is
            # In-progress because the only unchecked WUs in its phase scope
            # are explicitly documented in DEFERRED_NON_CLOUD.md as
            # workstation-only, flipping the plan to Complete in-place is the
            # documented exit. The orchestrator handles this pseudo-skill
            # inline (Step 1c.5) — no execute-plan dispatch needed. This
            # prevents the loop where execute-plan repeatedly diagnoses "no
            # cloud work" and reports a no-op without advancing.
            if cloud and _plan_status(plan) == "In-progress" and \
                    _plan_cloud_saturated(plan, phases_text, spec_path):
                return _state(
                    **common,
                    current_step="Step 7a: flip plan Complete (cloud-saturated)",
                    sub_skill="__flip_plan_complete_cloud_saturated__",
                    sub_skill_args=str(plan),
                )
            # plan-structure-authoring-gate Phase 4 pickup backstop: validate
            # the plan part STRUCTURALLY (in-process, via validate-plan.py's
            # run_structural_checks) at first /execute-plan routing. A FRESH
            # plan (zero ticked WUs) carrying a structural ERROR refuses the
            # route (BLOCKED.md, blocker_kind: plan-structural-invalid); a
            # plan already mid-execution (>=1 ticked WU) is WARN-only and
            # falls through — never blocks in-flight work.
            _pstruct = lazy_core.plan_structural_backstop(plan)
            if not _pstruct["ok"]:
                blocked_file = spec_path / "BLOCKED.md"
                if not blocked_file.exists():
                    body = lazy_core.format_plan_structural_blocker(
                        str(plan), _pstruct["findings"],
                    )
                    _write_yaml_blocked_sentinel(
                        blocked_file,
                        feature_id=feature_id,
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
                return _state(
                    feature_id=feature_id,
                    feature_name=feature_name,
                    spec_path=spec_path_str,
                    current_step="Step 7a: blocked (plan structurally invalid)",
                    terminal_reason="blocked",
                    notify_message=(
                        f"BLOCKED: {feature_name} — plan {plan.name} fails "
                        f"structural validation (plan-structural-invalid). "
                        f"Awaiting input."
                    ),
                )
            return _state(
                **common,
                current_step="Step 7a: execute plan",
                sub_skill="execute-plan",
                sub_skill_args=str(plan),
            )

    # Phases complete — order: Step 9 (MCP gate) → Step 10 (mark complete).
    #
    # RETRO UNWIRED (operator decision, 2026-06): the Step 8 /retro phase has
    # been removed from the pipeline. The retro gate proved low-yield (a
    # docs/design-alignment audit that structurally can't see the runtime
    # defects /mcp-test catches) while costing a full Opus dispatch per feature.
    # Once all phases are Complete, the pipeline now routes DIRECTLY to the MCP
    # validation gate (Step 9) — the state previously reached only after
    # RETRO_DONE.md existed is now reached as soon as execute-plan finalization
    # is done. Git history is the restore path; /retro-feature SKILL remains in
    # place. The now-inert retro_staleness()/phase_kind parsing is left dormant
    # (harmless, aids a future restore); nothing gates on it anymore — see the
    # __mark_complete__ backstop note in lazy_core.apply_pseudo.

    validated_file = spec_path / "VALIDATED.md"
    skip_mcp_file = spec_path / "SKIP_MCP_TEST.md"
    deferred_file = spec_path / "DEFERRED_NON_CLOUD.md"
    mcp_results_file = spec_path / "MCP_TEST_RESULTS.md"

    # Step 9-pre: device-deferral re-open / guard. A feature carrying
    # DEFERRED_REQUIRES_DEVICE.md has real-device-only MCP assertions that a
    # prior no-device /mcp-test could not certify (e.g. sustained zero-dropout
    # under the HeadlessPumpDriver). This is keyed on the device axis, NOT the
    # cloud axis, and is checked BEFORE the cloud/workstation split so it
    # governs both.
    #
    # The sentinel's MERE PRESENCE blocks completion — we deliberately do NOT
    # require `not VALIDATED.md` here. The contract is that a real-device
    # /mcp-test DELETES this sentinel on success; so if a VALIDATED.md and this
    # sentinel coexist, the re-open's cleanup did not happen (a race / aborted
    # run). Rather than letting that stray VALIDATED.md flip the feature Complete
    # — leaving Complete + a deferral sentinel, the `complete-not-device-deferred`
    # lint contradiction — we re-fire the re-open on a real-device host (mcp-test
    # is idempotent: it re-certifies the deferred scenarios and deletes the
    # sentinel, self-healing the state). The completion-integrity gate enforces
    # the same invariant a second time at flip time (refuses while the sentinel
    # is present).
    #
    # The deferral ALSO takes precedence over a SKIP_MCP_TEST.md — we do NOT
    # require `not skip_mcp`. A feature can legitimately carry BOTH (some
    # assertions any-host-untestable → skip; one real-device-only → deferral);
    # the deferral must still gate completion until a real-device run certifies
    # its scenarios, even though the skip alone would otherwise validate-and-
    # complete. Once the deferral is cleared (sentinel deleted), the residual
    # skip resumes its normal `__write_validated_from_skip__` path.
    device_deferred_file = spec_path / "DEFERRED_REQUIRES_DEVICE.md"
    if device_deferred_file.exists():
        if real_device:
            # RE-OPEN — the inverse the framework previously lacked. On a
            # real-device host, route back to /mcp-test scoped to the deferred
            # scenario set so the hardware-clock-driven assertions get a real
            # certification. /mcp-test certifies them, DELETES this sentinel, and
            # writes VALIDATED.md; the next probe reaches Step 10 mark-complete.
            meta = parse_sentinel(device_deferred_file) or {}
            scenarios = meta.get("deferred_scenarios") or []
            scen_str = (
                ", ".join(str(s) for s in scenarios)
                if scenarios else "(see DEFERRED_REQUIRES_DEVICE.md)"
            )
            return _state(
                **common,
                current_step="Step 9: re-open device-deferred scenarios (real-device host)",
                sub_skill="mcp-test",
                sub_skill_args=(
                    f"re-validate {feature_name} deferred real-device assertions "
                    f"[{scen_str}] on THIS real-device host — see "
                    f"{spec_path_str}/DEFERRED_REQUIRES_DEVICE.md. On pass, delete "
                    "that sentinel and write VALIDATED.md; on a genuine failure "
                    "treat it as a real bug (BLOCKED.md), not an environment skip."
                ),
            )
        # No-device host: the feature is device-saturated. Step 2's
        # device-saturated skip catches this before Step 9, so this is a
        # defensive guard ensuring a no-device host NEVER re-dispatches /mcp-test
        # for an already-deferred scenario set (which would no-op-loop). Surface
        # the same device-queue terminal.
        return _state(
            **common,
            current_step="Step 9: device-deferred (no real device on this host)",
            terminal_reason="device-queue-exhausted",
            notify_message=(
                f"{feature_name}: real-device-only assertions are deferred and "
                "cannot be certified here. Awaiting a real-device /lazy host "
                "(set ALGOBOOTH_REAL_AUDIO_DEVICE=1 or run on native hardware)."
            ),
        )

    # Step 9: MCP gate (validate runtime).
    # Cloud defers via DEFERRED_NON_CLOUD.md; workstation runs the tests.
    if cloud:
        if not validated_file.exists() and not skip_mcp_file.exists() and not deferred_file.exists():
            # Cloud halts at Step 9 — defer to workstation. Orchestrator writes
            # the DEFERRED_NON_CLOUD.md sentinel; next cycle either completes
            # (if workstation has since produced VALIDATED.md) or hits the
            # Step 2 cloud-saturated skip.
            return _state(
                **common,
                current_step="Step 9: cloud defers MCP test",
                sub_skill="__write_deferred_non_cloud__",
                sub_skill_args=spec_path_str,
            )
        # SKIP_MCP_TEST.md from a prior workstation assessment → write VALIDATED.md
        if skip_mcp_file.exists() and not validated_file.exists():
            # Provenance gate (skip_waiver_refusal): a pipeline-self-granted
            # skip, a pipeline-authored skip with NO granted_by field, or an
            # mcp-test grant missing its spec_class citation must NOT vacuously
            # validate — the pipeline cannot waive its own MCP requirement.
            # Accepted: operator grants, legacy no-provenance files, and
            # mcp-test grants carrying a spec_class citation.
            _skip_refusal = skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {}, repo_root)
            if _skip_refusal:
                return _state(
                    **common,
                    current_step="Step 9: pipeline-granted skip needs operator confirmation",
                    terminal_reason="needs-input",
                    notify_message=(
                        f"{feature_name}: SKIP_MCP_TEST.md {_skip_refusal}"
                    ),
                )
            return _state(
                **common,
                current_step="Step 9: skip-mcp-test → validated",
                sub_skill="__write_validated_from_skip__",
                sub_skill_args=spec_path_str,
            )
    else:
        # Workstation Step 9: run MCP tests (or use existing results / skip marker).
        if not validated_file.exists():
            if skip_mcp_file.exists():
                # Provenance gate (skip_waiver_refusal): a pipeline-self-granted
                # skip, a pipeline-authored skip with NO granted_by field, or an
                # mcp-test grant missing its spec_class citation must NOT
                # vacuously validate. Accepted: operator grants, legacy
                # no-provenance files, mcp-test grants with a spec_class citation.
                _skip_refusal = skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {}, repo_root)
                if _skip_refusal:
                    return _state(
                        **common,
                        current_step="Step 9: pipeline-granted skip needs operator confirmation",
                        terminal_reason="needs-input",
                        notify_message=(
                            f"{feature_name}: SKIP_MCP_TEST.md {_skip_refusal}"
                        ),
                    )
                return _state(
                    **common,
                    current_step="Step 9: skip-mcp-test → validated",
                    sub_skill="__write_validated_from_skip__",
                    sub_skill_args=spec_path_str,
                )
            # 100%-passing results already on disk?
            if mcp_results_file.exists():
                meta = parse_sentinel(mcp_results_file) or {}
                # Accept EITHER a canonical all-passing run OR a sanctioned
                # observation-gap partial (result: partial whose every exemption
                # carries a spec_class provenance). The latter routes through the
                # SHARED observation_gap_promotable helper — the SAME predicate
                # the __write_validated_from_results__ apply gate and the
                # completion-integrity gate use. Before this mirror the Step-9
                # routing accepted ONLY 'all-passing', so a valid observation-gap
                # partial fell through to 'Run MCP tests' and re-dispatched
                # /mcp-test every cycle — the deadlock one layer UP from the
                # completion gate's warning (community-sharing: result partial,
                # 10/10 MCP-driveable scope passing, 3 spec_class'd exemptions).
                #
                # observation_gap_promotable is HALF the AND — the promotion also
                # requires the MCP-driveable scope to be fully passing
                # (pass_count == total_count), which the apply + completion gates
                # cross-check downstream. We enforce that SAME cross-check here so
                # a partial with a GENUINE MCP-scope failure (pass < total) does
                # NOT route to write-validated; it falls through to a re-run.
                _obs_gap = observation_gap_promotable(meta)
                if _obs_gap:
                    _pass = _coerce_evidence_count(meta.get("pass_count"))
                    _total = _coerce_evidence_count(meta.get("total_count"))
                    # A malformed or genuinely-failing scope is NOT promotable —
                    # drop back to result=='all-passing'-only handling (which this
                    # partial is not), i.e. fall through to the MCP re-run below.
                    if _pass is None or _total is None or _pass != _total:
                        _obs_gap = False
                if meta.get("result") == "all-passing" or _obs_gap:
                    # Freshness gate: ensure the results were validated against the
                    # CURRENT HEAD commit, not a stale one. If validated_commit is
                    # present and doesn't match HEAD, classify the drift via the
                    # SHARED commit_drift_verdict helper (the SAME docs-only carve-
                    # out evaluate_completion_evidence + the apply gate use). When
                    # _current_head returns None (not a git repo) or validated_commit
                    # is absent (legacy results), the helper returns "fresh" and we
                    # fall through to the existing write-validated path.
                    #
                    # DOCS-ONLY DRIFT carve-out (2026-06-23 DEADLOCK fix —
                    # hardening-log Round 36): an /mcp-test cycle that obeys its
                    # clean-tree turn-end contract MUST commit MCP_TEST_RESULTS.md,
                    # and that commit advances HEAD exactly one past the
                    # validated_commit it just recorded. The results file is
                    # therefore PERPETUALLY one commit stale and that drift is a
                    # PURE DOCS-ONLY (*.md) delta — strict equality is structurally
                    # unsatisfiable → an infinite re-verify loop on EVERY feature.
                    # Docs-only drift routes to write-validated; only a non-.md
                    # (source/script/config) drift OR an unresolvable diff re-
                    # verifies (genuine TOCTOU).
                    head = _current_head(repo_root)
                    validated_commit = meta.get("validated_commit")
                    drift = commit_drift_verdict(repo_root, validated_commit, head)
                    if drift["verdict"] in ("non-docs-drift", "unresolvable"):
                        # Stale results validated DIFFERENT CODE — must NOT validate
                        # current code. Re-verify by re-running MCP tests against HEAD.
                        return _state(
                            **common,
                            current_step="Step 9: stale MCP results — re-verify",
                            sub_skill="mcp-test",
                            sub_skill_args=(
                                f"re-validate {feature_name} — MCP_TEST_RESULTS.md was "
                                f"validated against a stale commit; see {spec_path_str}/SPEC.md"
                            ),
                        )
                    # verdict ∈ {"fresh", "docs-only"} → safe to write validated.
                    return _state(
                        **common,
                        current_step="Step 9b: write validated",
                        sub_skill="__write_validated_from_results__",
                        sub_skill_args=spec_path_str,
                    )
            # Structural MCP-skip short-circuit (lazy-cycle-containment
            # follow-up): a `**MCP runtime:** not-required` feature in a repo
            # with NO app surface (no src-tauri/, no package.json) is
            # mechanically untestable — grant the skip INLINE via a pseudo-skill
            # instead of dispatching a (wasted) /mcp-test Opus cycle whose only
            # job would be to confirm the obvious and write the same sentinel.
            # The grant carries granted_by: pipeline-structural, which the very
            # next probe's skip_waiver_refusal RE-VERIFIES (no-app-surface
            # predicate), so this does NOT weaken the provenance gate.
            if phases_mcp_runtime_not_required(spec_path) and repo_has_no_app_surface(
                repo_root
            ):
                return _state(
                    **common,
                    current_step="Step 9: structural MCP-skip (no app surface)",
                    sub_skill="__grant_skip_no_mcp_surface__",
                    sub_skill_args=spec_path_str,
                )
            # Run MCP tests
            return _state(
                **common,
                current_step="Step 9: run MCP tests",
                sub_skill="mcp-test",
                sub_skill_args=f"validate {feature_name} — see {spec_path_str}/SPEC.md",
            )

    # Step 9.5: spike verdict gate (spike-pipeline-role Phase 2, WU-1).
    # Control reaches here only when the Step-9 MCP gate fell through — i.e.
    # VALIDATED.md exists (or the cloud/deferred entry holds). If the active
    # PHASES.md declares `**Spike:** required` and no PASS spike verdict is on
    # disk yet, the phase's completion rests on an un-run runtime proof: route
    # to a `spike` cycle BEFORE Step 10 mark-complete instead of completing.
    # A `verdict: PASS` SPIKE_VERDICT.md (or no `**Spike:**` line at all) falls
    # through byte-identically to today's Step-10 path.
    if phases_spike_required(spec_path) and not spike_verdict_is_pass(spec_path):
        # spike-pipeline-role Phase 4 (WU-2): the bounded tooling-existence
        # loop guard on this seam too — a SPIKE_VERDICT.md carrying a
        # spike_tooling_rounds count at/above the cap means the tooling gap
        # keeps recurring across corrective rounds; route to an operator
        # NEEDS_INPUT halt instead of dispatching another spike round.
        _sv_meta = parse_sentinel(spec_path / "SPIKE_VERDICT.md") or {}
        if lazy_core.spike_tooling_cap_exceeded(_sv_meta):
            lazy_core.write_spike_tooling_cap_needs_input(
                spec_path, feature_name, _sv_meta.get("spike_tooling_rounds")
            )
            lazy_core._diag(
                "Step 9.5: spike_tooling_rounds cap exceeded → needs-input "
                "(loop bounded)"
            )
            return _state(
                **common,
                current_step="Step 9.5: spike tooling-round cap exceeded",
                terminal_reason="needs-input",
                notify_message=(
                    f"NEEDS INPUT: {feature_name} — spike tooling gap "
                    "persists after the corrective-round cap; operator "
                    "decision needed."
                ),
            )
        _variant, _goal = lazy_core._read_spike_decision(spec_path)
        lazy_core._diag("Step 9.5: **Spike:** required with no PASS verdict → routing to spike")
        return _state(
            **common,
            current_step="Step 9.5: spike verdict pending",
            sub_skill="spike",
            sub_skill_args=(
                f"run the runtime proof for {feature_name} — goal: {_goal}. "
                f"Write SPIKE_VERDICT.md (verdict: PASS|FAIL, with observed "
                f"evidence) in {spec_path_str}; see {spec_path_str}/SPEC.md."
            ),
        )

    # Step 10: Mark complete.
    # Entry: VALIDATED.md OR (cloud AND DEFERRED_NON_CLOUD.md). (Retro is
    # unwired — there is no longer a RETRO_DONE.md precondition.)
    entry_ok = validated_file.exists() or (cloud and deferred_file.exists())
    if not entry_ok:
        # No entry — should be unreachable: Step 9 either wrote validated /
        # deferred or dispatched mcp-test. Defensive.
        # Write a durable NEEDS_INPUT.md so the orchestrator's Step 1g
        # decision-resume can surface the issue to the operator.
        _write_step10_needs_input(spec_path, feature_name)
        return _state(
            **common,
            current_step="Step 10: unexpected state",
            sub_skill=None,
            terminal_reason="needs-input",
            notify_message=(
                f"{feature_name}: unexpected state at Step 10 — phases complete "
                "but no VALIDATED.md, SKIP_MCP_TEST.md, or DEFERRED_NON_CLOUD.md. "
                "Manual review needed."
            ),
        )

    # Cloud cannot finalize without VALIDATED.md — Step 2's cloud-saturated
    # skip normally catches this earlier (DEFERRED_NON_CLOUD.md + no
    # VALIDATED.md), but defensively halt here too.
    if cloud and not validated_file.exists():
        return _state(
            **common,
            current_step="Step 10a: cloud halt",
            terminal_reason="cloud-queue-exhausted",
            notify_message=(
                f"{feature_name}: cloud work complete (phases). "
                "Awaiting workstation /lazy for deferred MCP test."
            ),
        )

    # park-provisional-acceptance (SPEC D6): NEVER emit __mark_complete__ over
    # an unratified NEEDS_INPUT_PROVISIONAL.md. Normally unreachable — the
    # non-park Step 3.6 halt and the park-mode walk-loop park both fire
    # earlier — but a scoped probe or an out-of-band caller could land here,
    # and apply_pseudo would refuse anyway (layer c); halting here keeps the
    # loop honest instead of emitting a route that is guaranteed to refuse.
    if (spec_path / lazy_core.PROVISIONAL_SENTINEL).exists():
        return _state(
            **common,
            current_step=STEP_NEEDS_RATIFICATION,
            terminal_reason=TR_NEEDS_RATIFICATION,
            notify_message=(
                f"{feature_name}: ready to complete but "
                f"{lazy_core.PROVISIONAL_SENTINEL} is unratified — ratify or "
                "redirect the provisional decision(s) first."
            ),
        )

    # Mark complete via the orchestrator's __mark_complete__ pseudo-skill
    # (ROADMAP edit + sentinel cleanup + commit).
    return _state(
        **common,
        current_step="Step 10: mark complete",
        sub_skill="__mark_complete__",
        sub_skill_args=spec_path_str,
    )


# ---------------------------------------------------------------------------
# Production sentinel writers (production-sentinel-writes-bypass-atomic-write:
# these two were previously misclassified — sitting BELOW the fixture-section
# banner below while `_write_yaml_blocked_sentinel` is called from Step-3
# compute_state production fail-fasts (unknown-host-capability,
# unknown-dependency) 1700+ lines earlier. Re-bannered in place per the SPEC's
# "move or re-banner" fix scope — moving them physically would touch every
# intervening fixture-builder line for no behavioral gain.
# `_write_yaml_sentinel` is fixture-only today (every live caller is inside
# `_build_fixture` below) but is fixed for atomicity alongside its sibling per
# the SPEC's explicit fix-scope row.
# ---------------------------------------------------------------------------

def _write_yaml_sentinel(path: Path, kind: str, **fields: Any) -> None:
    fm = {"kind": kind, **fields}
    body = "---\n" + yaml.safe_dump(fm, sort_keys=False).strip() + "\n---\n\n# Sentinel\n"
    _atomic_write(path, body)


def _write_yaml_blocked_sentinel(
    path: Path, *, feature_id: str, phase: str, blocker_kind: str,
    blocked_at: str, retry_count: int = 0, body: str = "",
) -> None:
    """Write a canonical BLOCKED.md (kind: blocked) with a human-readable body.

    host-capability-declaration-for-gated-features Phase 4: the unknown-host-
    capability fail-fast routes through the EXISTING canonical BLOCKED.md path
    (no new sentinel name). Frontmatter is the parser's source of truth; the
    body is the human-readable `## Details` / `## Recovery Suggestion` context
    required by the BLOCKED.md schema. The filename is exactly `BLOCKED.md`, so
    the noncanonical-blocker + stray-branch hooks (which gate TOOL writes, not
    this in-process state-machine write) are satisfied either way.
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


# ---------------------------------------------------------------------------
# Fixture smoke tests
# ---------------------------------------------------------------------------

def _build_fixture(tmpdir: Path, name: str) -> Path:
    """Build one of the named fixtures under tmpdir/<name>/ and return its repo root."""
    root = tmpdir / name
    features = root / "docs" / "features"
    if (features / "queue.json").exists():
        # Idempotent: fixture already materialized in this temp dir (some smoke
        # cases run the same fixture under different flag combinations).
        return root
    features.mkdir(parents=True, exist_ok=True)

    if name == "fresh-queue":
        # First feature has no SPEC, no research, no files
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-a", "name": "Feature A", "spec_dir": "feat-a", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        (features / "feat-a").mkdir()
    elif name == "blocker":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-b", "name": "Feature B", "spec_dir": "feat-b", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fdir = features / "feat-b"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            fdir / "BLOCKED.md", "blocked",
            feature_id="feat-b", phase="MCP Validation",
            blocked_at="2026-05-19T12:00:00Z", retry_count=0,
        )
    elif name == "spike-blocker-resolver":
        # spike-pipeline-role WU-2: same shape as the "blocker" fixture
        # above, but blocker_kind is runtime-spike-verdict-pending — the
        # Step-3 BLOCKED block must route this to sub_skill "spike"
        # (non-terminal) instead of the generic terminal "blocked" halt.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spkb", "name": "Feature SpikeBlocker", "spec_dir": "feat-spkb", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fdir = features / "feat-spkb"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            fdir / "BLOCKED.md", "blocked",
            feature_id="feat-spkb", phase="MCP Validation",
            blocker_kind="runtime-spike-verdict-pending",
            blocked_at="2026-05-19T12:00:00Z", retry_count=0,
        )
    elif name == "operator-deferred-skip":
        # merged-head-oracle-per-signal-supplement-churn Phase 1 (feature-side
        # mirror of bug-state.py's operator-deferred-skip). Two features:
        # feat-deferred carries a bare DEFERRED.md (operator-parked, must be
        # skipped) and feat-actionable is Draft-with-no-research (must dispatch
        # /spec). Queue lists the deferred one first.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-deferred", "name": "Deferred Feature",
                 "spec_dir": "feat-deferred", "tier": 1},
                {"id": "feat-actionable", "name": "Actionable Feature",
                 "spec_dir": "feat-actionable", "tier": 2},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fdd = features / "feat-deferred"
        fdd.mkdir()
        (fdd / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            fdd / "DEFERRED.md", "deferred",
            feature_id="feat-deferred",
            reason="Operator parked pending an upstream decision.",
            deferred_at="2026-07-19",
        )
        faa = features / "feat-actionable"
        faa.mkdir()
        (faa / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
    elif name == "all-operator-deferred":
        # Only feature carries DEFERRED.md → no actionable features remain. The
        # global all-remaining-deferred terminal fires (feature_id None,
        # operator_deferred non-empty). Mirror of bug-state.py's fixture.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-only-deferred", "name": "Only Deferred Feature",
                 "spec_dir": "feat-only-deferred", "tier": 1},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fod = features / "feat-only-deferred"
        fod.mkdir()
        (fod / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            fod / "DEFERRED.md", "deferred",
            feature_id="feat-only-deferred",
            reason="Pending hardware setup.",
            deferred_at="2026-07-19",
        )
    elif name == "operator-deferred-control":
        # Control: identical shape to all-operator-deferred but with NO
        # DEFERRED.md → the feature is dispatchable (Draft SPEC + no research
        # routes /spec at Step 5), proving the bare-DEFERRED.md branch is the
        # ONLY thing that excludes it.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-ctrl", "name": "Control Feature",
                 "spec_dir": "feat-ctrl", "tier": 1},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fcc = features / "feat-ctrl"
        fcc.mkdir()
        (fcc / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
    elif name == "mid-implementation":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fdir = features / "feat-c"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (fdir / "RESEARCH.md").write_text("# Research\n")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n")
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n"
        )
        (fdir / "plans").mkdir()
        (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n")
    elif name == "cloud-saturated":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-d", "name": "Feature D", "spec_dir": "feat-d", "tier": 1},
                {"id": "feat-e", "name": "Feature E", "spec_dir": "feat-e", "tier": 2},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        d = features / "feat-d"
        d.mkdir()
        (d / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (d / "RESEARCH.md").write_text("# R\n")
        (d / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (d / "PHASES.md").write_text("# P\n\n- [x] Done\n")
        _write_yaml_sentinel(
            d / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-d", deferred_step=8, reason="cloud limitation",
            deferred_by="lazy-cloud", date="2026-05-19",
        )
        _write_yaml_sentinel(
            d / "RETRO_DONE.md", "retro-done",
            feature_id="feat-d", date="2026-05-19",
            rounds=1, retro_plans=["retro-1-feat-d.md"],
            mcp_validation_status="deferred-to-workstation",
        )
        # Feature E: empty spec dir → will be picked up next
        e = features / "feat-e"
        e.mkdir()
    elif name == "cloud-workstation-only-remainder":
        # All implementation plans Complete, PHASES.md still has unchecked
        # workstation-only rows (Runtime Verification), no DEFERRED_NON_CLOUD.md
        # yet. Cloud Step 7 must bypass to Step 8 (write deferred sentinel)
        # rather than looping on write-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-cw", "name": "Feature CW", "spec_dir": "feat-cw", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        cw = features / "feat-cw"
        cw.mkdir()
        (cw / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (cw / "RESEARCH.md").write_text("# R\n")
        (cw / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (cw / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = cw / "plans"
        plans.mkdir()
        (plans / "all-phases-cw.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-cw\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "cloud-workstation-only-with-deferred":
        # Same shape as cloud-workstation-only-remainder, but DEFERRED_NON_CLOUD.md
        # already on disk. Retro unwired: Step 2's cloud-saturated skip fires
        # (DEFERRED_NON_CLOUD.md + no VALIDATED.md) → cloud-queue-exhausted.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-cwd", "name": "Feature CWD", "spec_dir": "feat-cwd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        cwd = features / "feat-cwd"
        cwd.mkdir()
        (cwd / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (cwd / "RESEARCH.md").write_text("# R\n")
        (cwd / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (cwd / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = cwd / "plans"
        plans.mkdir()
        (plans / "all-phases-cwd.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-cwd\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
        _write_yaml_sentinel(
            cwd / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-cwd", deferred_step=8, reason="workstation MCP test",
            deferred_by="lazy-cloud", date="2026-05-19",
        )
    elif name == "workstation-all-plans-complete-phases-unchecked":
        # Workstation MCP-gate bypass: all impl plans Complete and the only
        # unchecked PHASES.md rows are workstation-only Runtime Verification
        # rows. Workstation can run those checks, so /lazy must fall through to
        # the MCP gate. Retro unwired → Step 9 mcp-test dispatches directly.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wapcpu", "name": "Feature WAPCPU",
                 "spec_dir": "feat-wapcpu", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wapcpu"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-w.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wapcpu\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "workstation-verification-only-retro-done":
        # Workstation bypass with a stale RETRO_DONE.md on disk (left over from
        # an in-flight feature; retro is unwired). RETRO_DONE.md is now ignored
        # for routing — the fall-through reaches Step 9 → mcp-test directly (the
        # dispatch that ticks the deferred Runtime Verification rows).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wvrd", "name": "Feature WVRD",
                 "spec_dir": "feat-wvrd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wvrd"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-wvrd.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wvrd\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
        _write_yaml_sentinel(
            w / "RETRO_DONE.md", "retro-done",
            feature_id="feat-wvrd", date="2026-05-22",
            rounds=1, retro_plans=["retro-1-feat-wvrd.md"],
            mcp_validation_status="pending",
        )
    elif name == "workstation-verification-only-bold-marker":
        # Bold-marker format (the real AlgoBooth PHASES.md style) rather than
        # `### Runtime Verification` headings. Locks in that the detector
        # handles `**Runtime Verification**` / `**MCP Integration Test
        # Assertions:**`. All impl plans Complete → bypass → Step 9 mcp-test
        # (retro unwired).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wbold", "name": "Feature WBOLD",
                 "spec_dir": "feat-wbold", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wbold"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Implement the thing\n\n"
            "**Runtime Verification** (workstation-only):\n\n"
            "- [ ] Live MCP smoke test passes\n\n"
            "**MCP Integration Test Assertions:**\n\n"
            "```\n- [ ] assertion one holds\n```\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-wbold.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wbold\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "workstation-all-plans-complete-real-unchecked":
        # NEGATIVE case: all impl plans Complete, but a remaining unchecked row
        # is a genuine implementation deliverable (NOT under a verification
        # subsection). Bypass must NOT fire — workstation keeps emitting
        # write-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wreal", "name": "Feature WREAL",
                 "spec_dir": "feat-wreal", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wreal"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] Done\n"
            "- [ ] Real implementation deliverable still pending\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-wreal.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wreal\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "superseded-phase-unchecked":
        # All impl plans Complete. PHASES.md has one In-progress phase whose only
        # unchecked rows are under **Runtime Verification:**, PLUS a Superseded
        # phase with plain unchecked deliverable rows. The bypass must fire (True)
        # because the Superseded phase's boxes are out-of-scope and the only
        # remaining In-progress unchecked rows are verification-only.
        # Expected: Step 8 retro (bypass fires → no write-plan loop).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sup", "name": "Feature SUP",
                 "spec_dir": "feat-sup", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-sup"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 9 is In-progress with only verification-only unchecked rows.
        # Phase 10 is Superseded with plain unchecked deliverable rows — these
        # must be ignored by remaining_unchecked_are_verification_only.
        (w / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 9: Realignment MCP tests\n\n"
            "**Status:** In-progress\n\n"
            "**Deliverables:**\n\n"
            "- [x] Scenario document authored\n\n"
            "**Runtime Verification:**\n\n"
            "- [ ] Workstation: /mcp-test passes\n\n"
            "---\n\n"
            "### Phase 10: Replay stages\n\n"
            "**Status:** Superseded\n\n"
            "> Superseded into successor-feature.\n\n"
            "**Deliverables:**\n\n"
            "- [ ] Extend the ledger with orbit_gain field\n"
            "- [ ] Implement stage 3 replay\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "all-phases-sup.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-sup\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [9]\n---\n\n"
            "# Plan (complete)\n"
        )
    elif name == "cloud-saturated-in-progress-plan":
        # In-progress plan whose only unchecked WU is documented in
        # DEFERRED_NON_CLOUD.md as workstation-only. Cloud Step 7a should emit
        # __flip_plan_complete_cloud_saturated__ rather than execute-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-cs", "name": "Feature CS",
                 "spec_dir": "feat-cs", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        cs = features / "feat-cs"
        cs.mkdir()
        (cs / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (cs / "RESEARCH.md").write_text("# R\n")
        (cs / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (cs / "PHASES.md").write_text(
            "# Phases\n\n### Phase 6\n"
            "- [x] WU1 cloud-runnable deliverable A\n"
            "- [x] WU2 cloud-runnable deliverable B\n"
            "- [x] WU3 cloud-runnable deliverable C\n"
            "- [x] WU4 cloud-runnable deliverable D\n"
            "- [ ] WU5 promote SPEC to Complete via workstation MCP\n"
        )
        plans = cs / "plans"
        plans.mkdir()
        (plans / "part-6.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-cs\n"
            "status: In-progress\ncreated: 2026-05-01\nphases: [6]\n---\n\n"
            "# Plan part 6\n"
        )
        _write_yaml_sentinel(
            cs / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-cs", deferred_step=8,
            reason="workstation MCP gate",
            deferred_by="lazy-cloud", date="2026-05-22",
        )
        # Append a body block enumerating the workstation-only WU so the
        # substring saturation check matches.
        with (cs / "DEFERRED_NON_CLOUD.md").open("a", encoding="utf-8") as fh:
            fh.write("\nDeferred WUs:\n- WU5 promote SPEC to Complete via workstation MCP\n")
    elif name == "cloud-in-progress-plan-not-saturated":
        # In-progress plan with unchecked WUs NOT documented in
        # DEFERRED_NON_CLOUD.md → must NOT auto-flip; must dispatch
        # execute-plan as usual.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-csn", "name": "Feature CSN",
                 "spec_dir": "feat-csn", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        csn = features / "feat-csn"
        csn.mkdir()
        (csn / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (csn / "RESEARCH.md").write_text("# R\n")
        (csn / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (csn / "PHASES.md").write_text(
            "# Phases\n\n### Phase 6\n"
            "- [x] WU1 done\n"
            "- [ ] WU2 still actual cloud work\n"
        )
        plans = csn / "plans"
        plans.mkdir()
        (plans / "part-6.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-csn\n"
            "status: In-progress\ncreated: 2026-05-01\nphases: [6]\n---\n\n"
            "# Plan part 6\n"
        )
        _write_yaml_sentinel(
            csn / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-csn", deferred_step=8,
            reason="workstation MCP gate",
            deferred_by="lazy-cloud", date="2026-05-22",
        )
        # NOTE: DEFERRED_NON_CLOUD.md body does NOT mention WU2 — gate
        # must NOT fire.
    elif name == "workstation-in-progress-plan-with-deferred":
        # Same shape as cloud-saturated-in-progress-plan but workstation. The
        # gate is cloud-only — workstation should keep dispatching execute-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-wcs", "name": "Feature WCS",
                 "spec_dir": "feat-wcs", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        w = features / "feat-wcs"
        w.mkdir()
        (w / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (w / "RESEARCH.md").write_text("# R\n")
        (w / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (w / "PHASES.md").write_text(
            "# Phases\n\n### Phase 6\n"
            "- [x] WU1 done\n"
            "- [ ] WU5 workstation gate\n"
        )
        plans = w / "plans"
        plans.mkdir()
        (plans / "part-6.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-wcs\n"
            "status: In-progress\ncreated: 2026-05-01\nphases: [6]\n---\n\n"
            "# Plan part 6\n"
        )
        _write_yaml_sentinel(
            w / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-wcs", deferred_step=8,
            reason="workstation MCP gate",
            deferred_by="lazy-cloud", date="2026-05-22",
        )
        with (w / "DEFERRED_NON_CLOUD.md").open("a", encoding="utf-8") as fh:
            fh.write("\nDeferred WUs:\n- WU5 workstation gate\n")
    elif name == "all-complete":
        # ROADMAP strikethrough+COMPLETE fallback AND a COMPLETED.md receipt →
        # genuinely done, queue exhausts to all-features-complete.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-f", "name": "Feature F", "spec_dir": "feat-f", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Feature F — done~~ **COMPLETE**\n"
        )
        f = features / "feat-f"
        f.mkdir()
        _write_yaml_sentinel(
            f / "COMPLETED.md", "completed",
            feature_id="feat-f", date="2026-05-19", provenance="gated",
        )
    elif name == "needs-research":
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-g", "name": "Feature G", "spec_dir": "feat-g", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        g = features / "feat-g"
        g.mkdir()
        (g / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (g / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "stub-pre-gemini-marker":
        # Canonical pre-Gemini stub: SPEC carries the `> Draft (pre-Gemini)`
        # trailer, queue.json has no `stub` field. Step 4.5 should fire.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stub-marker", "name": "Stub Marker",
                 "spec_dir": "feat-stub-marker", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sdir = features / "feat-stub-marker"
        sdir.mkdir()
        (sdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n\n"
            "> Draft (pre-Gemini). Open questions in this spec are captured "
            "in RESEARCH_PROMPT.md and will be addressed by the upcoming "
            "manual Gemini deep-research sprint.\n"
        )
        (sdir / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "stub-queue-flag-only":
        # queue.json `"stub": true` cross-check fires Step 4.5 — but here the
        # SPEC ALSO carries a genuine pre-baseline SPEC-text stub marker
        # (`> Draft (pre-Gemini)`), so this is a TRUE pre-baseline stub. The
        # lone-surviving-marker discriminator must NOT clear-and-advance: with
        # a SPEC-text marker still present the route stays at Step 4.5 (the
        # baseline has not been shaped yet).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stub-queue", "name": "Stub Queue",
                 "spec_dir": "feat-stub-queue", "tier": 1, "stub": True}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sdir = features / "feat-stub-queue"
        sdir.mkdir()
        (sdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n\n"
            "> Draft (pre-Gemini). Open questions in this spec are captured "
            "in RESEARCH_PROMPT.md and will be addressed by the upcoming "
            "manual Gemini deep-research sprint.\n"
        )
        (sdir / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "stub-queue-flag-lone-survivor":
        # stub-spec-route-loops-until-queue-stub-cleared: the queue flag is the
        # LONE surviving stub marker — `/spec` Phase 1 already rewrote the SPEC
        # into a structured baseline (no SPEC-text stub marker remains) but the
        # `"stub": true` queue flag was never cleared. The discriminator must
        # clear the flag and FALL THROUGH to Step 5 (generate research prompt)
        # in the SAME probe, instead of re-firing Step 4.5 (the commit-masked
        # loop). No research files present.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stub-lone", "name": "Stub Lone",
                 "spec_dir": "feat-stub-lone", "tier": 1, "stub": True}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sdir = features / "feat-stub-lone"
        sdir.mkdir()
        # Structured baseline: NO SPEC-text stub marker. The queue flag is the
        # lone surviving marker.
        (sdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
    elif name == "spec-status-complete":
        # SPEC.md Status: Complete WITH a COMPLETED.md receipt → genuinely done
        # even when the ROADMAP grep wouldn't match (no strikethrough/COMPLETE).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-i", "name": "Feature I", "spec_dir": "feat-i", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n\n- Feature I — still listed without COMPLETE token\n")
        idir = features / "feat-i"
        idir.mkdir()
        (idir / "SPEC.md").write_text("# Spec\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            idir / "COMPLETED.md", "completed",
            feature_id="feat-i", date="2026-05-19", provenance="gated",
        )
    elif name == "complete-no-receipt":
        # FM1: SPEC.md Status: Complete but NO COMPLETED.md receipt → flipped
        # outside the gate → completion-unverified hard-halt.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-nr", "name": "Feature NR", "spec_dir": "feat-nr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        nr = features / "feat-nr"
        nr.mkdir()
        (nr / "SPEC.md").write_text("# Spec\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
    elif name == "superseded-no-receipt":
        # Superseded is exempt from the receipt requirement (retired, never
        # validated) → skipped, queue exhausts to all-features-complete.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sup", "name": "Feature SUP", "spec_dir": "feat-sup", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sup = features / "feat-sup"
        sup.mkdir()
        (sup / "SPEC.md").write_text("# Spec\n\n**Status:** Superseded\n\n**Depends on:** (none)\n")
    elif name == "autodiscover-off":
        # feature-queue-lacks-on-disk-autodiscovery (a): an on-disk Draft feature
        # dir NOT in queue.json + NO autodiscover flag ⇒ INVISIBLE. The queue has
        # one OTHER explicit feature (feat-exp, a genuinely-Complete+receipt dir so
        # the queue exhausts to all-features-complete and the disk-only dir's
        # absence from the work-list is observable as "all complete").
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-exp", "name": "Explicit", "spec_dir": "feat-exp", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        exp = features / "feat-exp"
        exp.mkdir()
        (exp / "SPEC.md").write_text("# Explicit\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            exp / "COMPLETED.md", "completed",
            feature_id="feat-exp", date="2026-06-22", provenance="gated",
        )
        # On-disk Draft dir, NOT queued, NO autodiscover ⇒ must stay invisible.
        ad = features / "feat-ad"
        ad.mkdir()
        (ad / "SPEC.md").write_text("# Feat AD\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
    elif name == "autodiscover-on":
        # feature-queue-lacks-on-disk-autodiscovery (b): same feat-ad dir WITH
        # top-level autodiscover: true ⇒ discovered + dispatched. A Draft SPEC
        # with no research routes to Step 5 /spec.
        (features / "queue.json").write_text(json.dumps({
            "autodiscover": True,
            "queue": []
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        ad = features / "feat-ad"
        ad.mkdir()
        (ad / "SPEC.md").write_text("# Feat AD\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
    elif name == "autodiscover-excludes-complete":
        # feature-queue-lacks-on-disk-autodiscovery (c): a Complete dir WITH a
        # valid COMPLETED.md receipt + autodiscover: true ⇒ NOT re-enqueued. With
        # only that dir on disk and an empty queue, discovery yields nothing ⇒
        # all-features-complete.
        (features / "queue.json").write_text(json.dumps({
            "autodiscover": True,
            "queue": []
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        done = features / "feat-done"
        done.mkdir()
        (done / "SPEC.md").write_text("# Feat Done\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            done / "COMPLETED.md", "completed",
            feature_id="feat-done", date="2026-06-22", provenance="gated",
        )
    elif name == "autodiscover-surfaces-receiptless-complete":
        # feature-queue-lacks-on-disk-autodiscovery (d): a Complete dir with NO
        # COMPLETED.md + autodiscover: true ⇒ surfaced (→ completion-unverified),
        # exactly as the bug loader surfaces a receiptless Fixed.
        (features / "queue.json").write_text(json.dumps({
            "autodiscover": True,
            "queue": []
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        rc = features / "feat-rc"
        rc.mkdir()
        (rc / "SPEC.md").write_text("# Feat RC\n\n**Status:** Complete\n\n**Depends on:** (none)\n")
        # deliberately NO COMPLETED.md receipt
    elif name == "autodiscover-dedupes-explicit-twin":
        # feature-queue-lacks-on-disk-autodiscovery (e): feat-dup BOTH explicitly
        # queued AND on disk + autodiscover: true ⇒ appears once; explicit entry
        # wins and is listed first. The explicit entry is a Draft SPEC routing to
        # Step 5 /spec — proving the explicit (not a duplicate discovered) entry
        # is the one dispatched.
        (features / "queue.json").write_text(json.dumps({
            "autodiscover": True,
            "queue": [
                {"id": "feat-dup", "name": "Explicit Dup", "spec_dir": "feat-dup", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dup = features / "feat-dup"
        dup.mkdir()
        (dup / "SPEC.md").write_text("# Feat Dup\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
    elif name == "autodiscover-orders-by-priority":
        # feature-queue-lacks-on-disk-autodiscovery (f): two discovered dirs, one
        # **Priority:** P1 and one **Priority:** P3 ⇒ P1 sorts before P3. Both are
        # Draft SPECs; the P1 dir (feat-hi) must be the dispatched head.
        (features / "queue.json").write_text(json.dumps({
            "autodiscover": True,
            "queue": []
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        lo = features / "feat-zlo"
        lo.mkdir()
        (lo / "SPEC.md").write_text(
            "# Feat Lo\n\n**Status:** Draft\n\n**Priority:** P3\n\n**Depends on:** (none)\n"
        )
        hi = features / "feat-hi"
        hi.mkdir()
        (hi / "SPEC.md").write_text(
            "# Feat Hi\n\n**Status:** Draft\n\n**Priority:** P1\n\n**Depends on:** (none)\n"
        )
    elif name == "autodiscover-empty-queue-not-missing":
        # feature-queue-lacks-on-disk-autodiscovery (g): "queue": [] +
        # autodiscover: true + one open disk dir ⇒ NOT queue-missing; the disk dir
        # is dispatched (claude-config's own live scenario). Draft SPEC → Step 5.
        (features / "queue.json").write_text(json.dumps({
            "autodiscover": True,
            "queue": []
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        eq = features / "feat-eq"
        eq.mkdir()
        (eq / "SPEC.md").write_text("# Feat EQ\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
    elif name == "dangling-queue-entry":
        # FM3: queue entry whose spec_dir does not exist on disk → skipped with
        # a diagnostic; queue exhausts to all-features-complete (not dispatched).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "ghost", "name": "Ghost Feature", "spec_dir": "ghost", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        # NOTE: deliberately do NOT create features/ghost/
    elif name == "plan-frontmatter-filter":
        # Three plans in plans/. One Complete (filtered), one with phases: [3],
        # one with phases: [4]. Expectation: lowest phase among non-Complete
        # plans is selected.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-j", "name": "Feature J", "spec_dir": "feat-j", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        jdir = features / "feat-j"
        jdir.mkdir()
        (jdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (jdir / "RESEARCH.md").write_text("# R\n")
        (jdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (jdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 3\n- [ ] Thing A\n\n### Phase 4\n- [ ] Thing B\n"
        )
        plans = jdir / "plans"
        plans.mkdir()
        # Complete plan (should be filtered)
        (plans / "all-phases-old.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-j\n"
            "status: Complete\ncreated: 2026-05-01\nphases: [1, 2]\n---\n\n"
            "# Plan (already complete)\n"
        )
        # Phase 4 plan (Ready, but later phase number)
        (plans / "all-phases-later.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-j\n"
            "status: Ready\ncreated: 2026-05-10\nphases: [4]\n---\n\n"
            "# Plan (phase 4)\n"
        )
        # Phase 3 plan (Ready, lowest phase number — expected pick)
        (plans / "phase-3-corrective.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-j\n"
            "status: Ready\ncreated: 2026-05-15\nphases: [3]\n---\n\n"
            "# Plan (phase 3)\n"
        )
    elif name == "legacy-plan-diagnostics":
        # Plan file with no frontmatter — should be included but raise a
        # diagnostics warning.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-k", "name": "Feature K", "spec_dir": "feat-k", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        kdir = features / "feat-k"
        kdir.mkdir()
        (kdir / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (kdir / "RESEARCH.md").write_text("# R\n")
        (kdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (kdir / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [ ] T\n")
        plans = kdir / "plans"
        plans.mkdir()
        # Legacy plan — no frontmatter
        (plans / "all-phases-legacy.md").write_text("# Legacy plan\n\nNo frontmatter here.\n")
    elif name == "research-pending-skip":
        # Queue: feat-a (research prompt only — would terminate on needs-research),
        # feat-b (ready to plan — SPEC/RESEARCH/RESEARCH_SUMMARY all present, no PHASES).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-a", "name": "Feature A", "spec_dir": "feat-a", "tier": 1},
                {"id": "feat-b", "name": "Feature B", "spec_dir": "feat-b", "tier": 2},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        a = features / "feat-a"
        a.mkdir()
        (a / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (a / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
        b = features / "feat-b"
        b.mkdir()
        (b / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (b / "RESEARCH.md").write_text("# R\n")
        (b / "RESEARCH_SUMMARY.md").write_text("# S\n")
    elif name == "research-pending-only":
        # Single-feature queue with only research-pending feat-a; under
        # --skip-needs-research the script should terminate with
        # queue-blocked-on-research.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-a", "name": "Feature A", "spec_dir": "feat-a", "tier": 1},
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        a = features / "feat-a"
        a.mkdir()
        (a / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (a / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
    elif name == "phases-complete-no-retro-done":
        # All phases complete (no unchecked rows), no sentinels at all.
        # Retro unwired: Step 9 (mcp test) fires directly — expects
        # sub_skill: mcp-test, NOT retro-feature.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcnr", "name": "Feature PCNR",
                 "spec_dir": "feat-pcnr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcnr"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "phases-complete-no-mcp-surface":
        # All phases complete; PHASES declares `**MCP runtime:** not-required`
        # and the temp repo has NO app surface (no src-tauri/, no package.json).
        # Step 9 should short-circuit to the inline structural skip grant
        # (__grant_skip_no_mcp_surface__) instead of dispatching /mcp-test.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-noms", "name": "Feature NOMS",
                 "spec_dir": "feat-noms", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-noms"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text(
            "# Phases\n\n**MCP runtime:** not-required\n\n### Phase 1\n- [x] Done\n"
        )
    elif name == "spike-required-no-verdict":
        # spike-pipeline-role Phase 2 (WU-1): PHASES.md declares a
        # `**Spike:** required` header and VALIDATED.md is present (Step 9
        # satisfied, non-cloud) but NO SPIKE_VERDICT.md exists on disk. The
        # Step 9.5 spike-routing gate must intercept BEFORE Step 10 and route
        # to sub_skill "spike" instead of falling through to mark-complete.
        # RED today: the Step 9.5 gate does not exist — this fixture falls
        # straight through to Step 10 (sub_skill: "__mark_complete__").
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spk", "name": "Feature SPK",
                 "spec_dir": "feat-spk", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-spk"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text(
            "# Phases\n\n**Spike:** required — prove projector holds 30fps\n\n"
            "### Phase 1\n- [x] Done\n"
        )
        _write_yaml_sentinel(
            p / "VALIDATED.md", "validated",
            feature_id="feat-spk", date="2026-07-17",
            mcp_scenarios=[], result="all-passing",
        )
    elif name == "spike-required-pass-verdict":
        # Same shape, but a SPIKE_VERDICT.md with verdict: PASS is already on
        # disk — the gate must fall through to Step 10 exactly as it would
        # with no **Spike:** header at all (sub_skill: "__mark_complete__").
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spkp", "name": "Feature SPKP",
                 "spec_dir": "feat-spkp", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-spkp"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text(
            "# Phases\n\n**Spike:** required — prove projector holds 30fps\n\n"
            "### Phase 1\n- [x] Done\n"
        )
        _write_yaml_sentinel(
            p / "VALIDATED.md", "validated",
            feature_id="feat-spkp", date="2026-07-17",
            mcp_scenarios=[], result="all-passing",
        )
        _write_yaml_sentinel(
            p / "SPIKE_VERDICT.md", "spike-verdict",
            feature_id="feat-spkp", verdict="PASS",
        )
    elif name == "phases-complete-retro-done":
        # All phases complete + a stale RETRO_DONE.md on disk, no VALIDATED.md
        # yet. Retro unwired: RETRO_DONE.md is ignored for routing — Step 9
        # (mcp test) fires regardless — expects sub_skill: mcp-test.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcrd", "name": "Feature PCRD",
                 "spec_dir": "feat-pcrd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcrd"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            p / "RETRO_DONE.md", "retro-done",
            feature_id="feat-pcrd", date="2026-05-22",
            rounds=1, retro_plans=["retro-1-feat-pcrd.md"],
            mcp_validation_status="complete",
        )
    elif name == "phases-complete-retro-done-cloud":
        # Cloud variant: phases complete + RETRO_DONE.md, no VALIDATED.md,
        # no DEFERRED_NON_CLOUD.md. Under cloud Step 9 → defer MCP test.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcrdc", "name": "Feature PCRDC",
                 "spec_dir": "feat-pcrdc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcrdc"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            p / "RETRO_DONE.md", "retro-done",
            feature_id="feat-pcrdc", date="2026-05-22",
            rounds=1, retro_plans=["retro-1-feat-pcrdc.md"],
            mcp_validation_status="deferred-to-workstation",
        )
    elif name == "phases-complete-no-retro-done-cloud":
        # Cloud variant: phases complete, no sentinels. Retro unwired → cloud
        # routes directly to Step 9, which defers MCP to workstation
        # (__write_deferred_non_cloud__).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pcnrc", "name": "Feature PCNRC",
                 "spec_dir": "feat-pcnrc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        p = features / "feat-pcnrc"
        p.mkdir()
        (p / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (p / "RESEARCH.md").write_text("# R\n")
        (p / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (p / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "adhoc-brief":
        # Ad-hoc feature seeded by --enqueue-adhoc: queue entry at top, spec
        # dir with ADHOC_BRIEF.md but no SPEC.md yet. Step 4 must route to /spec
        # with the ad-hoc-specific arg.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "adhoc-x", "name": "Ad-hoc X", "spec_dir": "adhoc-x",
                 "tier": 0, "adhoc": True}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        a = features / "adhoc-x"
        a.mkdir()
        (a / "ADHOC_BRIEF.md").write_text(
            "---\nkind: adhoc-brief\nfeature_id: adhoc-x\n"
            "enqueued_by: lazy-adhoc\ndate: 2026-05-24\n---\n\n"
            "# Ad-hoc task: Ad-hoc X\n\nDo the thing.\n"
        )
    elif name == "needs-realign":
        # feat-h has a hard dep on feat-up (complete upstream); no realign plan yet.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-h", "name": "Feature H", "spec_dir": "feat-h", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Upstream U — done~~ **COMPLETE**\n"
        )
        up = features / "feat-up"
        up.mkdir()
        (up / "SPEC.md").write_text("# Upstream\n\n**Status:** Complete\n")
        (up / "PHASES.md").write_text("# Phases\n\n- [x] Done\n")
        h = features / "feat-h"
        h.mkdir()
        (h / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:**\n\n"
            "- feat-up — hard — relies on the upstream contract\n"
        )
    elif name == "device-deferred-pending":
        # Phases + retro complete; a prior no-device /mcp-test deferred the
        # real-device-only assertion AQ-TE-05 via DEFERRED_REQUIRES_DEVICE.md
        # (no VALIDATED.md). Exercised under BOTH device states:
        #   real_device=False → Step 2 device-saturated skip → device-queue-exhausted
        #   real_device=True  → Step 9 re-open → mcp-test scoped to AQ-TE-05
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dd", "name": "Feature DD",
                 "spec_dir": "feat-dd", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dd = features / "feat-dd"
        dd.mkdir()
        (dd / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dd / "RESEARCH.md").write_text("# R\n")
        (dd / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dd / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dd / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dd", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dd.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            dd / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-dd",
            deferred_scenarios=["AQ-TE-05"],
            reason="sustained zero-dropout not certifiable under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-05-30",
        )
    elif name == "device-deferred-cleared":
        # The real-device re-open succeeded: /mcp-test deleted
        # DEFERRED_REQUIRES_DEVICE.md and wrote VALIDATED.md. With retro already
        # done, a real-device run proceeds straight to __mark_complete__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dc", "name": "Feature DC",
                 "spec_dir": "feat-dc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dc = features / "feat-dc"
        dc.mkdir()
        (dc / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dc / "RESEARCH.md").write_text("# R\n")
        (dc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dc / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dc / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dc", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dc.md"],
            mcp_validation_status="complete",
        )
        _write_yaml_sentinel(
            dc / "VALIDATED.md", "validated",
            feature_id="feat-dc", date="2026-05-30",
            mcp_scenarios=["AQ-TE-05"], result="all-passing",
        )
    elif name == "device-deferred-stale-validated":
        # Stray-race state: a real-device re-open wrote VALIDATED.md but did NOT
        # delete DEFERRED_REQUIRES_DEVICE.md. The sentinel's presence MUST still
        # block completion — on a real-device host it re-fires the re-open
        # (idempotent, self-healing) rather than flipping Complete (which would
        # leave Complete + a deferral sentinel, the lint contradiction).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dsv", "name": "Feature DSV",
                 "spec_dir": "feat-dsv", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dsv = features / "feat-dsv"
        dsv.mkdir()
        (dsv / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dsv / "RESEARCH.md").write_text("# R\n")
        (dsv / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dsv / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dsv / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dsv", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dsv.md"],
            mcp_validation_status="complete",
        )
        _write_yaml_sentinel(
            dsv / "VALIDATED.md", "validated",
            feature_id="feat-dsv", date="2026-05-30",
            mcp_scenarios=["AQ-TE-05"], result="all-passing",
        )
        _write_yaml_sentinel(
            dsv / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-dsv",
            deferred_scenarios=["AQ-TE-05"],
            reason="sustained zero-dropout not certifiable under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-05-30",
        )
    elif name == "device-deferred-with-skip":
        # Mixed waiver: some assertions are any-host-untestable (permanent
        # SKIP_MCP_TEST.md) AND one is real-device-only (DEFERRED_REQUIRES_DEVICE.md)
        # — the learn-system-v2 shape. The deferral MUST take precedence: on a
        # real-device host the feature RE-OPENS (does not validate-from-skip and
        # complete), so the device assertion is certified before completion.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dws", "name": "Feature DWS",
                 "spec_dir": "feat-dws", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dws = features / "feat-dws"
        dws.mkdir()
        (dws / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dws / "RESEARCH.md").write_text("# R\n")
        (dws / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dws / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dws / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dws", date="2026-05-30",
            rounds=1, retro_plans=["retro-1-feat-dws.md"],
            mcp_validation_status="complete",
        )
        _write_yaml_sentinel(
            dws / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-dws",
            reason="two items need a live LLM API key / dev-console — not MCP-drivable here",
            alternative_validation="covered by the deterministic test suite",
            date="2026-05-30", skipped_by="lazy",
        )
        _write_yaml_sentinel(
            dws / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-dws",
            deferred_scenarios=["modeling-audio-in-cue"],
            reason="audio item blocked by no-device ALSA failure under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-05-30",
        )
    elif name == "host-unknown-cap-failfast":
        # host-capability-declaration Phase 4: a feature past implementation
        # declares requires_host: [typo-cap] — an id NOT in the closed registry.
        # The unknown-id fail-fast MUST write BLOCKED.md
        # (blocker_kind: unknown-host-capability) naming the typo + the sorted
        # registry ids, NOT silently defer forever.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-huc", "name": "Feature HUC",
                 "spec_dir": "feat-huc", "tier": 1,
                 "requires_host": ["typo-cap"]}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        huc = features / "feat-huc"
        huc.mkdir()
        (huc / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (huc / "RESEARCH.md").write_text("# R\n")
        (huc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (huc / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "host-registered-cap-no-failfast":
        # host-capability-declaration Phase 4 guard: a feature declaring ONLY a
        # registered id (gpu) must NOT trip the unknown-id fail-fast. On a host
        # that HAS the capability it proceeds normally (here gpu is injected
        # present in the test, so no defer either).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-hrc", "name": "Feature HRC",
                 "spec_dir": "feat-hrc", "tier": 1,
                 "requires_host": ["gpu"]}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        hrc = features / "feat-hrc"
        hrc.mkdir()
        (hrc / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (hrc / "RESEARCH.md").write_text("# R\n")
        (hrc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (hrc / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "host-cap-miss-defers":
        # host-capability-declaration Phase 5: a feature past implementation
        # declares requires_host: [gpu, real-audio-device]; the injected host
        # present-set has only real-audio-device. missing = {gpu} (composite
        # AND, any miss ⇒ defer). The capability-miss branch MUST write
        # DEFERRED_REQUIRES_HOST.md and skip so the queue advances → terminal
        # host-capability-saturated (single-item queue).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-hcm", "name": "Feature HCM",
                 "spec_dir": "feat-hcm", "tier": 1,
                 "requires_host": ["gpu", "real-audio-device"]}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        hcm = features / "feat-hcm"
        hcm.mkdir()
        (hcm / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (hcm / "RESEARCH.md").write_text("# R\n")
        (hcm / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (hcm / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "host-cap-present-reopens":
        # host-capability-declaration Phase 5 re-open: the SAME shape as
        # host-cap-miss-defers, but the injected host present-set contains EVERY
        # required cap (missing empty). The feature must NOT skip — it proceeds
        # into runtime validation (Step 9 mcp-test dispatch, no
        # DEFERRED_REQUIRES_HOST.md written). Re-open is no-special-case.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-hcp", "name": "Feature HCP",
                 "spec_dir": "feat-hcp", "tier": 1,
                 "requires_host": ["gpu"]}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        hcp = features / "feat-hcp"
        hcp.mkdir()
        (hcp / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (hcp / "RESEARCH.md").write_text("# R\n")
        (hcp / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (hcp / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "host-ungated-baseline":
        # host-capability-declaration Phase 5 baseline-regression guard: a feature
        # with NO requires_host: marker is byte-identical to today. Past
        # implementation + retro done + no VALIDATED.md → Step 9 mcp-test
        # dispatch, NEVER a host-capability deferral.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-hub", "name": "Feature HUB",
                 "spec_dir": "feat-hub", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        hub = features / "feat-hub"
        hub.mkdir()
        (hub / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (hub / "RESEARCH.md").write_text("# R\n")
        (hub / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (hub / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
    elif name == "stale-mcp-results-reverify":
        # Workstation Step 9 path: on-disk MCP_TEST_RESULTS.md claims all-passing
        # but carries a stale validated_commit (all-zeros sha) that does NOT match
        # the fixture's actual HEAD. The fixture root is a real git repo so the
        # implementation's `git rev-parse HEAD` resolves to a non-zero sha.
        # Expected: compute_state detects staleness and re-verifies (sub_skill=
        # "mcp-test"), NOT __write_validated_from_results__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-smrr", "name": "Feature SMRR",
                 "spec_dir": "feat-smrr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        smrr = features / "feat-smrr"
        smrr.mkdir()
        (smrr / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (smrr / "RESEARCH.md").write_text("# R\n")
        (smrr / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # All phases checked — no remaining unchecked rows.
        (smrr / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            smrr / "RETRO_DONE.md", "retro-done",
            feature_id="feat-smrr", date="2026-06-01",
            rounds=1, retro_plans=["retro-1-feat-smrr.md"],
            mcp_validation_status="pending",
        )
        # Stale on-disk results: all-passing but validated against the all-zeros sha
        # (a sha that cannot equal any real git HEAD). The implementation's freshness
        # check should catch this and route to re-verify rather than auto-validate.
        _write_yaml_sentinel(
            smrr / "MCP_TEST_RESULTS.md", "mcp-test-results",
            result="all-passing",
            validated_commit="0000000000000000000000000000000000000000",
        )
        # NO VALIDATED.md — not yet validated.
        # NO SKIP_MCP_TEST.md — waiver not present.

        # Make the fixture root a real git repo so `git rev-parse HEAD` resolves
        # to a genuine (non-zero) sha. The implementation compares that sha against
        # the stale validated_commit above and must detect the mismatch.
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
                    f"stale-mcp-results-reverify git setup failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
    elif name == "docsonly-drift-validate":
        # 2026-06-23 DEADLOCK fix (hardening-log Round 36): on-disk
        # MCP_TEST_RESULTS.md records validated_commit == sha A, but HEAD has
        # since advanced to sha B via a PURE DOCS-ONLY (*.md) commit — exactly
        # the structurally-unavoidable one-commit lag an /mcp-test cycle's OWN
        # MCP_TEST_RESULTS.md commit produces under the clean-tree turn-end
        # contract. The A→B drift is docs-only, so Step 9 MUST route to
        # write-validated (__write_validated_from_results__), NOT re-verify.
        # RED against pre-fix code (strict validated_commit != HEAD →
        # infinite re-verify deadlock loop).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-dod", "name": "Feature DOD",
                 "spec_dir": "feat-dod", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dod = features / "feat-dod"
        dod.mkdir()
        (dod / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (dod / "RESEARCH.md").write_text("# R\n")
        (dod / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dod / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            dod / "RETRO_DONE.md", "retro-done",
            feature_id="feat-dod", date="2026-06-23",
            rounds=1, retro_plans=["retro-1-feat-dod.md"],
            mcp_validation_status="pending",
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
                    f"docsonly-drift-validate git setup A failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
        head_a = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        if head_a.returncode != 0:
            raise RuntimeError(
                f"docsonly-drift-validate rev-parse A failed: {head_a.stderr.strip()}"
            )
        sha_a = head_a.stdout.strip()
        # Commit B: a PURE DOCS-ONLY (*.md) change. HEAD advances to sha B while
        # validated_commit stays at sha A — drift A→B is docs-only.
        (dod / "NOTES.md").write_text(
            "# Notes\n\nA docs-only follow-up commit.\n"
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
                    f"docsonly-drift-validate git setup B failed "
                    f"(cmd={cmd!r}): {result.stderr.strip()}"
                )
        # MCP_TEST_RESULTS.md records sha A (the validated tree), not HEAD (sha B).
        _write_yaml_sentinel(
            dod / "MCP_TEST_RESULTS.md", "mcp-test-results",
            result="all-passing",
            validated_commit=sha_a,
        )
        # NO VALIDATED.md, NO SKIP_MCP_TEST.md.
    elif name == "skip-pipeline-granted-needs-input":
        # WU-5 Phase-2 contract (RED fixture): SKIP_MCP_TEST.md carrying
        # `granted_by: pipeline` must NOT be accepted as a waiver by the
        # pipeline itself — a model could self-grant the skip to defeat MCP
        # validation. When `granted_by == "pipeline"`, compute_state must
        # refuse and route to terminal_reason="needs-input" rather than
        # emitting __write_validated_from_skip__.
        # This fixture is RED against current code: current Step 9 ignores
        # `granted_by` and always emits __write_validated_from_skip__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spg", "name": "Feature SPG",
                 "spec_dir": "feat-spg", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        spg = features / "feat-spg"
        spg.mkdir()
        (spg / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (spg / "RESEARCH.md").write_text("# R\n")
        (spg / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # All phases checked — retro + MCP gate reached.
        (spg / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            spg / "RETRO_DONE.md", "retro-done",
            feature_id="feat-spg", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-spg.md"],
            mcp_validation_status="pending",
        )
        # SKIP_MCP_TEST.md with granted_by: pipeline — self-grant the waiver.
        # Phase-2 contract: this must be refused (needs-input), not validated.
        _write_yaml_sentinel(
            spg / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-spg",
            reason="pipeline self-asserted skip to avoid MCP test",
            alternative_validation="none",
            date="2026-06-10", skipped_by="pipeline",
            granted_by="pipeline",
        )
        # NO VALIDATED.md — not yet validated.
        # NO DEFERRED_REQUIRES_DEVICE.md — pure skip path.

    elif name == "skip-operator-granted-validates":
        # WU-5 Phase-2 positive guard (GREEN fixture): SKIP_MCP_TEST.md
        # carrying `granted_by: operator` is a legitimate human-authored waiver.
        # compute_state must continue to emit __write_validated_from_skip__ for
        # operator grants — the existing vacuous-pass behavior is intentional
        # here and must not regress.
        # This fixture is expected GREEN even against current code (current
        # always validates-from-skip, regardless of granted_by).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sog", "name": "Feature SOG",
                 "spec_dir": "feat-sog", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sog = features / "feat-sog"
        sog.mkdir()
        (sog / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (sog / "RESEARCH.md").write_text("# R\n")
        (sog / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # All phases checked — retro + MCP gate reached.
        (sog / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            sog / "RETRO_DONE.md", "retro-done",
            feature_id="feat-sog", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-sog.md"],
            mcp_validation_status="pending",
        )
        # SKIP_MCP_TEST.md with granted_by: operator — legitimate human waiver.
        # Phase-2 contract: operator grant → __write_validated_from_skip__
        # (same as the pre-Phase-2 vacuous-pass behavior).
        _write_yaml_sentinel(
            sog / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-sog",
            reason="feature is a pure docs/config change — no runtime MCP path",
            alternative_validation="manual smoke test by operator",
            date="2026-06-10", skipped_by="operator",
            granted_by="operator",
        )
        # NO VALIDATED.md — not yet validated.
        # NO DEFERRED_REQUIRES_DEVICE.md — pure skip path.

    elif name == "skip-operator-colon-reason-validates":
        # skip-mcp-test-frontmatter-unquoted-colon Phase 2 (end-to-end fixture):
        # an operator-granted SKIP_MCP_TEST.md whose `reason:` carries an
        # UNQUOTED colon-space must still route Step 9 → __write_validated_from_skip__
        # instead of hard-halting (exit 2 via _die) at the strict YAML parse.
        # RED before Phase 1 (parse_sentinel _die'd on the colon-bearing frontmatter,
        # so compute_state exited 2 before ever reaching the skip route); GREEN after
        # (parse_sentinel's tolerant re-parse reads the colon value as a literal).
        # The SKIP_MCP_TEST.md is written RAW (NOT via _write_yaml_sentinel, whose
        # yaml.safe_dump would auto-QUOTE the colon value and mask the bug) so the
        # on-disk frontmatter reproduces the exact hand-authored failure shape.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-socr", "name": "Feature SOCR",
                 "spec_dir": "feat-socr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        socr = features / "feat-socr"
        socr.mkdir()
        (socr / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (socr / "RESEARCH.md").write_text("# R\n")
        (socr / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (socr / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            socr / "RETRO_DONE.md", "retro-done",
            feature_id="feat-socr", date="2026-07-04",
            rounds=1, retro_plans=["retro-1-feat-socr.md"],
            mcp_validation_status="pending",
        )
        # RAW SKIP_MCP_TEST.md — an UNQUOTED colon-space in the `reason` value.
        (socr / "SKIP_MCP_TEST.md").write_text(
            "---\n"
            "kind: skip-mcp-test\n"
            "feature_id: feat-socr\n"
            "reason: untestable on this host: no real audio device\n"
            "alternative_validation: manual smoke test by operator\n"
            "date: 2026-07-04\n"
            "skipped_by: operator\n"
            "granted_by: operator\n"
            "---\n\n"
            "# Skip\n",
            encoding="utf-8",
        )
        # NO VALIDATED.md — not yet validated.
        # NO DEFERRED_REQUIRES_DEVICE.md — pure skip path.

    elif name == "skip-mcp-test-granted-with-class-validates":
        # Provenance positive: granted_by: mcp-test + a spec_class citation is a
        # verified structural assessment by the validation step itself —
        # accepted as a waiver → __write_validated_from_skip__.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-smtc", "name": "Feature SMTC",
                 "spec_dir": "feat-smtc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        smtc = features / "feat-smtc"
        smtc.mkdir()
        (smtc / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (smtc / "RESEARCH.md").write_text("# R\n")
        (smtc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (smtc / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            smtc / "RETRO_DONE.md", "retro-done",
            feature_id="feat-smtc", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-smtc.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            smtc / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-smtc",
            reason="standalone crate — no MCP-reachable surface",
            alternative_validation="covered by cargo tests",
            date="2026-06-10", skipped_by="lazy",
            granted_by="mcp-test",
            spec_class="no app integration — covered by cargo tests",
        )
        # NO VALIDATED.md — not yet validated.

    elif name == "skip-mcp-test-granted-missing-class-refuses":
        # Provenance gate: granted_by: mcp-test WITHOUT a spec_class citation is
        # an unverified claim — refused (needs-input), not validated. The
        # citation is what distinguishes a verified structural assessment from
        # a convenience skip.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-smtn", "name": "Feature SMTN",
                 "spec_dir": "feat-smtn", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        smtn = features / "feat-smtn"
        smtn.mkdir()
        (smtn / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (smtn / "RESEARCH.md").write_text("# R\n")
        (smtn / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (smtn / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            smtn / "RETRO_DONE.md", "retro-done",
            feature_id="feat-smtn", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-smtn.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            smtn / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-smtn",
            reason="claims untestable but cites no class",
            alternative_validation="none",
            date="2026-06-10", skipped_by="lazy",
            granted_by="mcp-test",
        )
        # NO VALIDATED.md — not yet validated.

    elif name == "skip-pipeline-authored-no-grant-refuses":
        # Provenance omission gate: a skip whose skipped_by identifies a
        # pipeline author ("lazy") but which carries NO granted_by at all used
        # to sail through as legacy-operator — the omission side-door (observed
        # 2026-06-10: an mcp-test cycle wrote a skip without the field and it
        # auto-validated with no operator confirmation). Must now refuse.
        # Files with NEITHER provenance field stay grandfathered.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-spa", "name": "Feature SPA",
                 "spec_dir": "feat-spa", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        spa = features / "feat-spa"
        spa.mkdir()
        (spa / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        (spa / "RESEARCH.md").write_text("# R\n")
        (spa / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (spa / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        _write_yaml_sentinel(
            spa / "RETRO_DONE.md", "retro-done",
            feature_id="feat-spa", date="2026-06-10",
            rounds=1, retro_plans=["retro-1-feat-spa.md"],
            mcp_validation_status="pending",
        )
        _write_yaml_sentinel(
            spa / "SKIP_MCP_TEST.md", "skip-mcp-test",
            feature_id="feat-spa",
            reason="pipeline-written skip with no provenance field",
            alternative_validation="none",
            date="2026-06-10", skipped_by="lazy",
        )
        # NO VALIDATED.md — not yet validated.

    elif name == "roadmap-substring-collision-no-false-halt":
        # Fixture A — substring-collision bug in roadmap_marks_complete.
        # completion_claimed() passes the queue entry's `name` (not id) to
        # roadmap_marks_complete. The feature name "Audio" is a STRICT SUBSTRING
        # of the unrelated completed ROADMAP row text "Audio Engine". "Audio"
        # itself is NOT marked complete anywhere.
        #
        # Pre-fix (RED): roadmap_marks_complete does a bare re.search(re.escape("Audio"), line)
        # which matches the "Audio Engine" row → completion_claimed() returns True
        # → no COMPLETED.md receipt → hard-halt with terminal_reason="completion-unverified".
        #
        # Post-fix (GREEN): the match is anchored to whole-word / word-boundary so
        # "Audio" does NOT match the "Audio Engine" row → completion_claimed()
        # returns False → feature proceeds normally → Step 5 dispatches /spec to
        # generate a research prompt (no research files present).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-audio", "name": "Audio",
                 "spec_dir": "feat-audio", "tier": 1}
            ]
        }))
        # ROADMAP has a completed row for the UNRELATED "Audio Engine" feature.
        # "Audio" appears as a substring inside "Audio Engine" — this is the
        # exact collision the fix must prevent. Note the feature name searched by
        # roadmap_marks_complete is the queue entry name "Audio", not the id.
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n"
            "- ~~Audio Engine — deep audio processing~~ **COMPLETE**\n"
        )
        a_dir = features / "feat-audio"
        a_dir.mkdir()
        # SPEC.md Status: Draft — not complete. No receipt, no research files.
        (a_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # No RESEARCH.md, no RESEARCH_SUMMARY.md, no RESEARCH_PROMPT.md →
        # Step 5 will dispatch /spec (generate research prompt).

    elif name == "research-gate-skipped-when-phases-implemented":
        # research-gate-ignores-existing-phases P2 — the core symptom.
        # SPEC (Draft, non-stub) + a PHASES.md with one In-progress phase + a
        # plan on disk + NO RESEARCH*.md. Pre-fix (RED): the Step-5 gate sees no
        # research files and dispatches /spec for research-prompt generation,
        # wasting a Gemini round-trip on an already-implemented feature. Post-fix
        # (GREEN): the pre-Step-5 guard detects implementation evidence in
        # PHASES.md, emits the D3 diagnostic, and falls through to Step 7
        # (execute-plan).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-rgs", "name": "Feature RGS",
                 "spec_dir": "feat-rgs", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        rgs = features / "feat-rgs"
        rgs.mkdir()
        (rgs / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # PHASES.md with an In-progress phase → implementation evidence.
        (rgs / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n**Status:** In-progress\n"
            "- [ ] Build the thing\n- [ ] Tests\n"
        )
        # A plan on disk so Step 7 dispatches execute-plan deterministically.
        (rgs / "plans").mkdir()
        (rgs / "plans" / "all-phases-rgs.md").write_text("# Plan\n")
        # No RESEARCH.md / RESEARCH_SUMMARY.md / RESEARCH_PROMPT.md.

    elif name == "research-gate-fires-when-no-phases":
        # research-gate-ignores-existing-phases P2 — unchanged default guard.
        # SPEC (Draft) + NO PHASES.md + NO RESEARCH*.md → the pre-Step-5 guard
        # is a no-op (no PHASES.md) and Step 5 still dispatches /spec for
        # research-prompt generation, exactly as before the fix.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-rgn", "name": "Feature RGN",
                 "spec_dir": "feat-rgn", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        rgn = features / "feat-rgn"
        rgn.mkdir()
        (rgn / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # No PHASES.md, no research files → Step 5 generates a research prompt.

    elif name == "research-gate-fires-when-phases-stub":
        # research-gate-ignores-existing-phases P2 — SPEC Open-Q1 / D2.
        # SPEC (Draft) + an empty-stub PHASES.md (no '## Phase' headings parsed)
        # + NO RESEARCH*.md. The predicate returns False for zero parsed phases,
        # so a stub PHASES.md must NOT suppress research — Step 5 still
        # dispatches /spec for research-prompt generation.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-rgstub", "name": "Feature RGSTUB",
                 "spec_dir": "feat-rgstub", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        rgstub = features / "feat-rgstub"
        rgstub.mkdir()
        (rgstub / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # Stub PHASES.md: preamble only, NO phase headings → zero parsed phases.
        (rgstub / "PHASES.md").write_text(
            "# Implementation Phases\n\nTo be drafted after research concludes.\n"
        )
        # No research files → Step 5 generates a research prompt.

    elif name == "research-path-byte-identical-when-research-present":
        # research-gate-ignores-existing-phases P2 — guard is a structural no-op
        # whenever research already exists. SPEC + an implemented PHASES.md +
        # RESEARCH_SUMMARY.md present + a plan → the guard's `not research` /
        # `not research_summary` precondition is False, so it never runs; the
        # feature reaches Step 7 (execute-plan) exactly as today.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-rgbi", "name": "Feature RGBI",
                 "spec_dir": "feat-rgbi", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        rgbi = features / "feat-rgbi"
        rgbi.mkdir()
        (rgbi / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (rgbi / "RESEARCH.md").write_text("# Research\n")
        (rgbi / "RESEARCH_SUMMARY.md").write_text("# Summary\n")
        (rgbi / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n**Status:** In-progress\n"
            "- [ ] Build the thing\n- [ ] Tests\n"
        )
        (rgbi / "plans").mkdir()
        (rgbi / "plans" / "all-phases-rgbi.md").write_text("# Plan\n")

    elif name == "is-stub-prose-mention-not-stub":
        # Fixture B — substring-collision bug in is_stub_spec.
        # The SPEC.md has a non-stub **Status:** (just "Draft", no "(pre-Gemini)"
        # qualifier) but the body PROSE contains the literal phrase
        # "Draft (pre-Gemini)" in a sentence discussing the concept.
        #
        # Pre-fix (RED): is_stub_spec does `"Draft (pre-Gemini)" in spec_text`
        # which is a bare substring match against the ENTIRE spec body. It matches
        # the prose mention → the feature is falsely routed to Step 4.5 stub-spec
        # → sub_skill="spec" at the stub branch instead of the normal pipeline.
        #
        # Post-fix (GREEN): the check is anchored to the **Status:** line, so the
        # prose mention does NOT trigger is_stub_spec → the feature falls through
        # to the normal pipeline. With RESEARCH.md + RESEARCH_SUMMARY.md present
        # but no PHASES.md yet → Step 6 dispatches /plan-feature.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-prose-stub", "name": "Prose Stub Feature",
                 "spec_dir": "feat-prose-stub", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        ps = features / "feat-prose-stub"
        ps.mkdir()
        # **Status:** is a clean "Draft" — NOT a stub marker. The body prose
        # mentions "Draft (pre-Gemini)" as an illustrative example, which is
        # the text that the buggy bare-substring check incorrectly matches.
        (ps / "SPEC.md").write_text(
            "# Spec\n\n"
            "**Status:** Draft\n\n"
            "**Depends on:** (none)\n\n"
            "## Background\n\n"
            "Unlike a Draft (pre-Gemini) stub, this spec is fully researched "
            "and does not require a Gemini deep-research sprint before phases "
            "can be written.\n"
        )
        # Research files present → passes Step 5 gate, reaches Step 6.
        (ps / "RESEARCH.md").write_text("# Research\n\nResearch complete.\n")
        (ps / "RESEARCH_SUMMARY.md").write_text("# Summary\n\nKey findings.\n")
        # No PHASES.md → Step 6 dispatches /plan-feature.

    elif name == "upstream-substring-collision":
        # Fixture C — substring-collision bug in upstream_is_complete.
        # The upstream feature directory is named "audio". The ROADMAP contains
        # a strikethrough+COMPLETE row for the UNRELATED "audio-engine" feature.
        # upstream_is_complete checks `upstream_name in line` (bare substring) which
        # matches the "audio-engine" row when upstream_name="audio".
        #
        # Pre-fix (RED): upstream_is_complete("audio") returns True (false positive)
        # → hard_complete_upstream_dirs is non-empty → realign_is_fresh returns False
        # (no realign plan exists) → compute_state emits sub_skill="realign-spec"
        # at Step 4.6, even though "audio" upstream is NOT actually complete.
        #
        # Post-fix (GREEN): the match is anchored to word boundary / whole directory
        # name so "audio" does NOT match "audio-engine" → upstream_is_complete returns
        # False → hard_complete_upstream_dirs stays empty → Step 4.6 does not fire
        # → feature proceeds to Step 5 (no research) → sub_skill="spec".
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-downstream", "name": "Downstream Feature",
                 "spec_dir": "feat-downstream", "tier": 1}
            ]
        }))
        # ROADMAP has a completed row for "audio-engine" — NOT for "audio" (the
        # upstream the downstream feature depends on). Bare substring "audio" in
        # "audio-engine" is the collision.
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n"
            "- ~~audio-engine — deep audio processing~~ **COMPLETE**\n"
        )
        # Create the upstream "audio" feature directory. Its SPEC.md status is
        # Draft (NOT Complete), so the SPEC-based check in upstream_is_complete
        # also returns False. Only the buggy ROADMAP substring check fires.
        aud = features / "audio"
        aud.mkdir()
        (aud / "SPEC.md").write_text(
            "# Upstream Audio\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        # Create the downstream feature with a hard dep on "audio" (the upstream).
        ds = features / "feat-downstream"
        ds.mkdir()
        # The dep block references "audio" by feature_id. resolve_upstream_dir
        # finds the sibling "audio" dir (has SPEC.md).
        (ds / "SPEC.md").write_text(
            "# Downstream Spec\n\n"
            "**Status:** Draft\n\n"
            "**Depends on:**\n\n"
            "- audio — hard — this feature builds on the audio foundation\n"
        )
        # No research files → if Step 4.6 correctly does NOT fire, the feature
        # falls through to Step 5 and dispatches /spec (research prompt generation).

    elif name == "stale-plan-all-refs-checked-flips":
        # Fixture A — stale-plan detection.
        # Plan's phases: [1] scope is fully checked (all Phase 1 deliverables
        # are [x]). Phase 2 still has an unchecked row, so unchecked > 0 overall
        # and Step 7 is entered. The plan is STALE: every WU it references is
        # done, yet its frontmatter still says status: Ready (never flipped to
        # Complete by a prior session).
        #
        # Pre-fix (RED): compute_state dispatches execute-plan — it burns an
        # Opus cycle re-verifying a plan whose work is already done.
        #
        # Post-fix (GREEN): the stale-plan guard detects that
        # _unchecked_wus_in_plan_scope(phases_text, {1}) is empty → emits
        # sub_skill="__flip_plan_complete_stale__" with sub_skill_args=plan path.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stale", "name": "Feature Stale",
                 "spec_dir": "feat-stale", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        st = features / "feat-stale"
        st.mkdir()
        (st / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (st / "RESEARCH.md").write_text("# R\n")
        (st / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 1: ALL deliverables checked (the plan's scope is fully done).
        # Phase 2: one unchecked deliverable → unchecked > 0 overall so Step 7
        # is entered and plan selection runs.
        (st / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] WU1 implement core logic\n"
            "- [x] WU2 write unit tests\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = st / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] only — the fully-checked phase.
        # status: Ready (never updated after phase 1 completed) → STALE.
        (plans / "all-phases-stale.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-stale\n"
            "status: Ready\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan for Phase 1\n"
        )
        # No RETRO_DONE.md → stays in Step 7 (not past Step 8).
        # No DEFERRED_NON_CLOUD.md → cloud-saturation gate does not interfere.

    elif name == "ready-plan-unchecked-in-scope-still-executes":
        # Fixture B — discriminating guard: plan scope has genuine remaining work.
        # Phase 1 still has an unchecked deliverable inside the plan's phases: [1]
        # scope. The stale-plan guard must NOT fire — _unchecked_wus_in_plan_scope
        # returns a non-empty list so the plan is live work.
        #
        # Expected (GREEN today and must stay GREEN): sub_skill="execute-plan".
        # This fixture proves the flip fires ONLY when the scope is fully checked.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-live", "name": "Feature Live",
                 "spec_dir": "feat-live", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        lv = features / "feat-live"
        lv.mkdir()
        (lv / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (lv / "RESEARCH.md").write_text("# R\n")
        (lv / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 1: UNCHECKED deliverable still in scope → plan is NOT stale.
        # Phase 2: also unchecked, but the plan only declares phases: [1].
        (lv / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] WU1 implement core logic\n"
            "- [ ] WU2 write unit tests\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = lv / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] — phase 1 has WU2 unchecked → live work
        # remains → execute-plan must be dispatched as normal.
        (plans / "all-phases-live.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-live\n"
            "status: Ready\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan for Phase 1\n"
        )
        # No RETRO_DONE.md, no DEFERRED_NON_CLOUD.md.

    elif name == "plan-structural-backstop-refuses-fresh-invalid":
        # plan-structure-authoring-gate Phase 4 pickup backstop: a FRESH plan
        # (zero ticked WUs) carrying an unfilled WU-checklist template-row
        # placeholder must REFUSE the /execute-plan route (BLOCKED.md,
        # blocker_kind: plan-structural-invalid) rather than dispatch.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pstruct-fresh", "name": "Feature PStruct Fresh",
                 "spec_dir": "feat-pstruct-fresh", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        pf = features / "feat-pstruct-fresh"
        pf.mkdir()
        (pf / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (pf / "RESEARCH.md").write_text("# R\n")
        (pf / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (pf / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] WU1 implement the thing\n"
        )
        plans = pf / "plans"
        plans.mkdir()
        (plans / "all-phases-pstruct-fresh.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-pstruct-fresh\n"
            "status: Ready\ncreated: 2026-07-12\nphases: [1]\n---\n\n"
            "## Work Units\n- [ ] WU-N — <short title>\n"
        )

    elif name == "plan-structural-backstop-mid-execution-warns":
        # Same structural defect as above, but the plan already has >=1
        # ticked WU (mid-execution — already in flight). The backstop must
        # WARN, never refuse: sub_skill stays execute-plan.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-pstruct-mid", "name": "Feature PStruct Mid",
                 "spec_dir": "feat-pstruct-mid", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        pm = features / "feat-pstruct-mid"
        pm.mkdir()
        (pm / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (pm / "RESEARCH.md").write_text("# R\n")
        (pm / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (pm / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n"
            "- [x] WU1 implement the thing\n"
            "- [ ] WU2 more work\n"
        )
        plans = pm / "plans"
        plans.mkdir()
        (plans / "all-phases-pstruct-mid.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-pstruct-mid\n"
            "status: In-progress\ncreated: 2026-07-12\nphases: [1]\n---\n\n"
            "## Work Units\n"
            "- [x] WU-1 — did something real\n"
            "- [ ] WU-N — <short title>\n"
        )

    elif name == "finalize-plan-verification-rows-only-flips":
        # Phase 8 (lazy-validation-readiness) — close the /execute-plan
        # finalization gap, option (b). The plan's phase scope has all its
        # IMPLEMENTATION deliverables checked; the ONLY remaining unchecked rows
        # in scope sit under a Runtime Verification subsection (Step-9-owned).
        # The plan frontmatter is still Ready. Phase 2 (out of scope) has a real
        # unchecked impl row so unchecked > 0 overall and Step 7 is entered.
        #
        # Pre-fix (RED): _unchecked_wus_in_plan_scope returns the RV row as
        # unchecked → the stale-plan gate does NOT fire → execute-plan is
        # re-dispatched (a redundant cycle that only flips the plan to Complete).
        #
        # Post-fix (GREEN): the finalize-stale branch sees the in-scope unchecked
        # remainder is entirely verification-only → routes to
        # __flip_plan_complete_stale__ with no redundant execute-plan dispatch.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-fin", "name": "Feature Finalize",
                 "spec_dir": "feat-fin", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        fn = features / "feat-fin"
        fn.mkdir()
        (fn / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (fn / "RESEARCH.md").write_text("# R\n")
        (fn / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Phase 1 (plan scope): all impl WUs [x]; only a Runtime Verification
        # row remains unchecked. Phase 2 (out of scope): a real unchecked row.
        (fn / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [x] WU1 implement core logic\n"
            "- [x] WU2 write unit tests\n"
            "\n"
            "**Runtime Verification** *(checked on the next marked run):*\n"
            "- [ ] live MCP assertion certifies the surface\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = fn / "plans"
        plans.mkdir()
        # Plan scoped to phases: [1] — its only in-scope unchecked row is the
        # verification row → finalize-stale → flip, do NOT execute-plan.
        (plans / "all-phases-fin.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-fin\n"
            "status: Ready\ncreated: 2026-05-01\nphases: [1]\n---\n\n"
            "# Plan for Phase 1\n"
        )
        # No RETRO_DONE.md → stays in Step 7 (not past Step 8).

    elif name == "stale-empty-scope-decomposition-executes":
        # Empty-PHASES-scope guard (f1-global-scale part-0, 2026-06-19). A plan
        # declares phases: [0] (a write-plan touchpoint-`block` decomposition part)
        # but PHASES.md has NO `### Phase 0` section — the decomposition WUs live
        # in the PLAN BODY (WU-0A/WU-0B), still unchecked. The plan's PHASES scope
        # therefore resolves to ZERO rows.
        #
        # Pre-fix (RED): _unchecked_wus_in_plan_scope(phases, {0}) is empty →
        # finalize_stale vacuously True → __flip_plan_complete_stale__ → the
        # decomposition is SILENTLY SKIPPED.
        #
        # Post-fix (GREEN): scope_total is empty → fall back to the plan's OWN
        # per-WU checkboxes; WU-0A/WU-0B are unchecked → finalize_stale False →
        # sub_skill="execute-plan" so the decomposition actually runs.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-decomp", "name": "Feature Decomp",
                 "spec_dir": "feat-decomp", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dc = features / "feat-decomp"
        dc.mkdir()
        (dc / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (dc / "RESEARCH.md").write_text("# R\n")
        (dc / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # PHASES.md: Phases 1-2 only (NO Phase 0). Phase 1 has an unchecked row so
        # overall unchecked > 0 and Step 7 plan-selection is entered.
        (dc / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [ ] WU1 implement core logic\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = dc / "plans"
        plans.mkdir()
        # part-0 decomposition plan: phases: [0] (no PHASES Phase 0), with unchecked
        # plan-body WU boxes → real work remains → must execute, not flip.
        (plans / "all-phases-decomp-part-0.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-decomp\n"
            "status: Ready\ncreated: 2026-06-19\nphases: [0]\n---\n\n"
            "# Decomposition Prerequisite\n\n"
            "## Work Units\n"
            "- [ ] WU-0A — Extract completion arrays\n"
            "- [ ] WU-0B — Extract registration groups\n"
        )
        # No RETRO_DONE.md, no DEFERRED_NON_CLOUD.md.

    elif name == "stale-empty-scope-all-plan-wus-checked-flips":
        # Discriminating control for the empty-PHASES-scope fallback: same shape as
        # `stale-empty-scope-decomposition-executes`, but the plan-body WU boxes are
        # ALL [x] — the decomposition genuinely ran in a prior session and only the
        # plan frontmatter status was never flipped. The fallback must then flip
        # stale (avoid a wasted execute-plan cycle), proving the fix discriminates
        # done-vs-undone rather than blanket-disabling the stale gate for phases:[0].
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-decdone", "name": "Feature Decomp Done",
                 "spec_dir": "feat-decdone", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        dd = features / "feat-decdone"
        dd.mkdir()
        (dd / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (dd / "RESEARCH.md").write_text("# R\n")
        (dd / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (dd / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n"
            "- [ ] WU1 implement core logic\n"
            "\n"
            "### Phase 2\n"
            "- [ ] WU3 integration tests\n"
        )
        plans = dd / "plans"
        plans.mkdir()
        (plans / "all-phases-decdone-part-0.md").write_text(
            "---\nkind: implementation-plan\nfeature_id: feat-decdone\n"
            "status: Ready\ncreated: 2026-06-19\nphases: [0]\n---\n\n"
            "# Decomposition Prerequisite\n\n"
            "## Work Units\n"
            "- [x] WU-0A — Extract completion arrays\n"
            "- [x] WU-0B — Extract registration groups\n"
        )
        # No RETRO_DONE.md, no DEFERRED_NON_CLOUD.md.

    elif name == "realign-hash-gate-detects-changed-upstream":
        # WU-8 Fixture 1: realign freshness gate hash comparison.
        #
        # Scenario: downstream feat-rhg has a hard dep on upstream feat-rhg-up
        # (Complete). The downstream has a realign plan whose frontmatter records
        # upstream_phases_hashes: with a BOGUS hash (64 zeros) that does NOT match
        # the upstream PHASES.md actual content. The plan file's mtime is NEWER
        # than the upstream PHASES.md (simulating: upstream changed AFTER the plan
        # was written, but the plan mtime ordering is reversed by os.utime trickery
        # — actually here we write PHASES.md first so plan is naturally newer).
        #
        # RED today (mtime gate): plan mtime > upstream PHASES.md mtime → mtime
        # gate says "fresh" → no realign needed → routes onward (Step 5/6).
        # GREEN after fix (hash gate): recorded hash ≠ actual PHASES.md sha256 →
        # hash gate says "stale" → routes to Step 4.6 realign-spec.
        #
        # We write upstream PHASES.md FIRST so its mtime is older, then write the
        # realign plan so its mtime is newer — satisfying the "plan is newer"
        # condition the old mtime gate would declare as fresh.
        import time as _time_mod
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-rhg", "name": "Feature RHG", "spec_dir": "feat-rhg", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text(
            "# Roadmap\n\n- ~~Upstream RHG Up — done~~ **COMPLETE**\n"
        )
        # Complete upstream feature directory
        up_dir = features / "feat-rhg-up"
        up_dir.mkdir(parents=True, exist_ok=True)
        (up_dir / "SPEC.md").write_text("# Upstream\n\n**Status:** Complete\n")
        upstream_phases = up_dir / "PHASES.md"
        upstream_phases.write_text("# Phases\n\n- [x] Upstream done\n")
        # Force the upstream PHASES.md mtime to be clearly OLDER (10 seconds ago)
        # so the plan file written next is naturally NEWER.
        old_mtime = _time_mod.time() - 10.0
        os.utime(str(upstream_phases), (old_mtime, old_mtime))

        # Downstream feature with hard dep on the upstream
        down_dir = features / "feat-rhg"
        down_dir.mkdir(parents=True, exist_ok=True)
        (down_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n"
            "**Depends on:**\n\n"
            "- feat-rhg-up — hard — downstream relies on upstream contract\n"
        )
        (down_dir / "RESEARCH.md").write_text("# R\n")
        (down_dir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Realign plan with a BOGUS recorded hash (64 zeros) that will never match
        # the real upstream PHASES.md sha256. The impl agent's hash gate must detect
        # the mismatch and require a new realign even though plan mtime > PHASES mtime.
        plans_dir = down_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        bogus_hash = "0" * 64
        realign_plan_path = plans_dir / "realign-2026-01-01.md"
        realign_plan_path.write_text(
            "---\n"
            "kind: realign\n"
            "upstream_phases_hashes:\n"
            # Use the upstream dir NAME as the key (per task description: dir-name → sha256)
            f"  feat-rhg-up: {bogus_hash}\n"
            "---\n\n"
            "# Realign plan (with stale recorded hash)\n"
        )
        # The plan is written AFTER upstream PHASES.md (so plan mtime > PHASES mtime).
        # The old mtime gate reads plan mtime > PHASES mtime → declares fresh → no realign.
        # The new hash gate reads recorded hash ≠ real sha256 → declares stale → realign.

    elif name == "stale-upstream-auto-wired-at-probe":
        # WU-8 Fixture 2: check_stale_upstream auto-runs at probe start.
        #
        # Scenario: docs/work/materialized.json records wi_id=201, feature_id=
        # "feat-sau" with materialized_changedDate "2026-01-01T00:00:00Z".
        # docs/work/ado-mirror.json has the same WI with changedDate
        # "2026-06-01T00:00:00Z" (STRICTLY NEWER). The feature dir exists with
        # a minimal queue entry so compute_state would otherwise process it.
        # STALE_UPSTREAM.md is NOT pre-written.
        #
        # RED today: nothing auto-calls check_stale_upstream → STALE_UPSTREAM.md
        # is never written → Step 2.9 stale check finds nothing → feature routes
        # through its normal early pipeline (no stale halt).
        # GREEN after fix: compute_state auto-calls check_stale_upstream at probe
        # start → writes STALE_UPSTREAM.md → Step 2.9 reads it and halts with
        # terminal_reason="stale_upstream".
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sau", "name": "Feature SAU", "spec_dir": "feat-sau", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        sau_dir = features / "feat-sau"
        sau_dir.mkdir(parents=True, exist_ok=True)
        (sau_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
        )
        # Seed materialized.json with an OLDER changedDate for this WI
        work_dir = root / "docs" / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        lazy_core.append_materialized(
            work_dir, 201, "feat-sau", "2026-01-01T00:00:00Z"
        )
        # Mirror has a STRICTLY NEWER changedDate for the same WI
        (work_dir / "ado-mirror.json").write_text(
            json.dumps({
                "syncedAt": "2026-06-10T12:00:00Z",
                "watermark": "2026-06-10",
                "query": "SELECT ...",
                "workItems": [
                    {
                        "id": 201,
                        "type": "User Story",
                        "title": "Feature SAU upstream",
                        "description": "Updated upstream.",
                        "acceptanceCriteria": "AC.",
                        "url": "https://dev.azure.com/org/proj/_workitems/edit/201",
                        "changedDate": "2026-06-01T00:00:00Z",
                    }
                ],
            }, indent=2),
            encoding="utf-8",
        )
        # Do NOT pre-write STALE_UPSTREAM.md — the auto-wiring at probe start must create it.

    elif name == "misnamed-blocker-stray":
        # noncanonical-blocker-filename-invisible-to-state-machine: a blocker
        # written under a NON-canonical name (no canonical BLOCKED.md). Step 3
        # must surface the distinct `blocked-misnamed` terminal naming the stray
        # rather than routing past it (loop risk).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-mbs", "name": "Feature MBS", "spec_dir": "feat-mbs", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        mbs = features / "feat-mbs"
        mbs.mkdir()
        (mbs / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (mbs / "BLOCKED_2026-06-09-foo.md").write_text(
            "blocker written under a mis-spelled name\n"
        )
    elif name == "misnamed-blocker-resolved-only":
        # A neutralized blocker (BLOCKED_RESOLVED_<date>.md) is excluded by the
        # detector — it must NOT halt; the item routes normally (here: a Draft
        # SPEC with no research → Step 5 research prompt).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-mbr", "name": "Feature MBR", "spec_dir": "feat-mbr", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        mbr = features / "feat-mbr"
        mbr.mkdir()
        (mbr / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        (mbr / "BLOCKED_RESOLVED_2026-06-09.md").write_text("# Resolved blocker\n")
    elif name == "misnamed-blocker-canonical-precedence":
        # Canonical BLOCKED.md AND a stray both present → the canonical `blocked`
        # terminal must win (no `blocked-misnamed`). Proves the detector defers to
        # canonical and the Step-3 wiring order is correct.
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-mbc", "name": "Feature MBC", "spec_dir": "feat-mbc", "tier": 1}
            ]
        }))
        (features / "ROADMAP.md").write_text("# Roadmap\n")
        mbc = features / "feat-mbc"
        mbc.mkdir()
        (mbc / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            mbc / "BLOCKED.md", "blocked",
            feature_id="feat-mbc", phase="Implementation",
            blocked_at="2026-06-09T12:00:00Z", retry_count=0,
        )
        (mbc / "BLOCKED_2026-06-09-foo.md").write_text("a co-present stray\n")

    else:
        raise ValueError(f"unknown fixture: {name}")

    return root


def run_smoke_tests() -> int:
    """Build fixtures in a temp dir and assert expected state shapes."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lazy-state-fixtures-") as td:
        td_path = Path(td)
        cases = [
            # (fixture_name, cloud, skip_needs_research, expectations dict)
            ("fresh-queue", False, False, {"terminal_reason": "needs-spec-input"}),
            ("blocker", False, False, {"terminal_reason": "blocked", "feature_id": "feat-b"}),
            # spike-pipeline-role WU-2: a BLOCKED.md carrying blocker_kind:
            # runtime-spike-verdict-pending routes to the spike blocked-
            # resolver (sub_skill "spike", NON-terminal) instead of the
            # generic terminal_reason="blocked" halt above.
            ("spike-blocker-resolver", False, False, {
                "sub_skill": "spike", "feature_id": "feat-spkb",
                "current_step": "Step 3: spike verdict pending (blocked resolver)",
            }),
            # noncanonical-blocker-filename-invisible-to-state-machine: a stray
            # blocker (non-canonical name, no canonical BLOCKED.md) → distinct
            # `blocked-misnamed` terminal (loop-risk fix).
            ("misnamed-blocker-stray", False, False, {
                "terminal_reason": "blocked-misnamed",
                "feature_id": "feat-mbs",
                "current_step": "Step 3: mis-named blocker",
            }),
            # A neutralized blocker (BLOCKED_RESOLVED_<date>.md) is excluded →
            # does NOT halt; Draft SPEC + no research routes to Step 5.
            ("misnamed-blocker-resolved-only", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-mbr",
                "current_step": "Step 5: generate research prompt",
            }),
            # Canonical BLOCKED.md + a stray both present → canonical `blocked`
            # precedence (no `blocked-misnamed`).
            ("misnamed-blocker-canonical-precedence", False, False, {
                "terminal_reason": "blocked",
                "feature_id": "feat-mbc",
            }),
            ("mid-implementation", False, False, {"sub_skill": "execute-plan", "feature_id": "feat-c"}),
            ("cloud-saturated", True, False, {"feature_id": "feat-e"}),   # advances past saturated feat-d
            # Step 7 cloud bypass: all plans Complete + PHASES.md has
            # workstation-only unchecked rows → bypass triggers, falls
            # through to phases-complete logic. Retro unwired → cloud routes
            # directly to Step 9 (defer MCP to workstation).
            ("cloud-workstation-only-remainder", True, False, {
                "sub_skill": "__write_deferred_non_cloud__",
                "feature_id": "feat-cw",
                "current_step": "Step 9: cloud defers MCP test",
            }),
            # Same bypass with DEFERRED_NON_CLOUD.md already on disk. Retro
            # unwired → Step 2's cloud-saturated skip fires (deferred + no
            # validated) → cloud-queue-exhausted (only feature in queue).
            ("cloud-workstation-only-with-deferred", True, False, {
                "terminal_reason": "cloud-queue-exhausted",
            }),
            # Workstation MCP-gate bypass: all impl plans Complete, only
            # unchecked rows are Runtime Verification → fall through to the
            # MCP gate. Retro unwired → Step 9 mcp-test fires directly.
            ("workstation-all-plans-complete-phases-unchecked", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wapcpu",
                "current_step": "Step 9: run MCP tests",
            }),
            # Workstation bypass + a stale RETRO_DONE.md present (retro unwired;
            # the sentinel is ignored for routing) → Step 9 mcp-test (the
            # dispatch that actually ticks the deferred verification rows).
            ("workstation-verification-only-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wvrd",
                "current_step": "Step 9: run MCP tests",
            }),
            # Workstation bypass with bold-marker (`**Runtime Verification**`)
            # subsections instead of `### ` headings — real AlgoBooth format.
            # Retro unwired → Step 9 mcp-test.
            ("workstation-verification-only-bold-marker", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-wbold",
                "current_step": "Step 9: run MCP tests",
            }),
            # NEGATIVE: all impl plans Complete but a remaining unchecked row is
            # a real implementation deliverable (outside any verification
            # subsection) → bypass must NOT fire; write-plan still dispatched.
            ("workstation-all-plans-complete-real-unchecked", False, False, {
                "sub_skill": "write-plan",
                "feature_id": "feat-wreal",
            }),
            # Superseded-phase bypass: one In-progress phase with only
            # verification-only unchecked rows, plus a Superseded phase with
            # plain unchecked deliverable rows. Superseded boxes must be ignored
            # → bypass fires → Step 9 mcp-test (retro unwired; no write-plan loop).
            ("superseded-phase-unchecked", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-sup",
                "current_step": "Step 9: run MCP tests",
            }),
            # Ad-hoc enqueue: ADHOC_BRIEF.md present, no SPEC.md → /spec with
            # the ad-hoc-specific arg (Step 4 ad-hoc branch).
            ("adhoc-brief", False, False, {
                "sub_skill": "spec",
                "feature_id": "adhoc-x",
                "current_step": "Step 4: ad-hoc brief → spec",
            }),
            ("all-complete", False, False, {"terminal_reason": "all-features-complete"}),
            ("needs-research", False, False, {"terminal_reason": "needs-research"}),
            # research-gate-ignores-existing-phases P2 — the pre-Step-5 guard.
            # SPEC + In-progress PHASES.md + plan + NO research → past research,
            # routes to execute-plan (NOT needs-research / spec research prompt).
            ("research-gate-skipped-when-phases-implemented", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-rgs",
            }),
            # No PHASES.md → guard no-op → research still fires (unchanged).
            ("research-gate-fires-when-no-phases", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-rgn",
                "current_step": "Step 5: generate research prompt",
            }),
            # Stub PHASES.md (zero parsed phases) → predicate False → research
            # still fires (SPEC Open-Q1 / D2 — a stub must not suppress research).
            ("research-gate-fires-when-phases-stub", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-rgstub",
                "current_step": "Step 5: generate research prompt",
            }),
            # Research already present → guard never runs → execute-plan exactly
            # as today (byte-identical no-op on the existing path).
            ("research-path-byte-identical-when-research-present", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-rgbi",
            }),
            # Canonical `> Draft (pre-Gemini)` SPEC trailer → Step 4.5 stub
            # dispatch, NOT needs-research. Without this match, the script
            # would halt the queue waiting on Gemini for a SPEC whose baseline
            # doesn't exist yet.
            ("stub-pre-gemini-marker", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-stub-marker",
                "current_step": "Step 4.5: stub-spec detected",
            }),
            # queue.json `"stub": true` + a genuine pre-baseline SPEC-text
            # marker → a TRUE pre-baseline stub → Step 4.5 (NOT cleared).
            ("stub-queue-flag-only", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-stub-queue",
                "current_step": "Step 4.5: stub-spec detected",
            }),
            # stub-spec-route-loops-until-queue-stub-cleared: the queue flag is
            # the LONE surviving marker (baseline already shaped) → the
            # discriminator clears the flag and advances to Step 5 in the same
            # probe (on-disk clear asserted in the extra-assertions block).
            ("stub-queue-flag-lone-survivor", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-stub-lone",
                "current_step": "Step 5: generate research prompt",
            }),
            ("needs-realign", False, False, {
                "sub_skill": "realign-spec",
                "feature_id": "feat-h",
            }),
            ("spec-status-complete", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # FM1: Complete claim without a COMPLETED.md receipt hard-halts.
            ("complete-no-receipt", False, False, {
                "terminal_reason": "completion-unverified",
                "feature_id": "feat-nr",
            }),
            # Superseded is exempt from the receipt requirement → skipped.
            ("superseded-no-receipt", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # FM3: dangling spec_dir is skipped (not dispatched).
            ("dangling-queue-entry", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # feature-queue-lacks-on-disk-autodiscovery (a): flag-off regression.
            # An on-disk Draft dir NOT in queue.json + NO autodiscover flag is
            # INVISIBLE — the explicit Complete+receipt feature exhausts the queue,
            # the disk-only dir never enters the work-list. Byte-identical to today.
            ("autodiscover-off", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # (b): same dir WITH autodiscover: true ⇒ discovered + dispatched
            # (Draft SPEC, no research → Step 5 /spec).
            ("autodiscover-on", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-ad",
                "current_step": "Step 5: generate research prompt",
            }),
            # (c): a Complete dir WITH a valid COMPLETED.md receipt + autodiscover
            # ⇒ NOT re-enqueued; queue exhausts past it.
            ("autodiscover-excludes-complete", False, False, {
                "terminal_reason": "all-features-complete",
            }),
            # (d): a Complete dir with NO receipt + autodiscover ⇒ surfaced
            # (→ completion-unverified), mirroring the bug loader's receiptless-Fixed.
            ("autodiscover-surfaces-receiptless-complete", False, False, {
                "terminal_reason": "completion-unverified",
                "feature_id": "feat-rc",
            }),
            # (e): feat-dup BOTH explicitly queued AND on disk + autodiscover ⇒
            # appears once; explicit entry wins (Draft SPEC → Step 5 /spec).
            ("autodiscover-dedupes-explicit-twin", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-dup",
                "current_step": "Step 5: generate research prompt",
            }),
            # (f): two discovered dirs ordered by **Priority:** rank — P1 (feat-hi)
            # sorts before P3 (feat-zlo); the P1 dir is the dispatched head.
            ("autodiscover-orders-by-priority", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-hi",
                "current_step": "Step 5: generate research prompt",
            }),
            # (g): "queue": [] + autodiscover + one open disk dir ⇒ NOT
            # queue-missing; the disk dir is dispatched (claude-config's own live
            # scenario).
            ("autodiscover-empty-queue-not-missing", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-eq",
                "current_step": "Step 5: generate research prompt",
            }),
            ("plan-frontmatter-filter", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-j",
            }),
            ("legacy-plan-diagnostics", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-k",
            }),
            # --skip-needs-research: feat-a has a research prompt only (would
            # terminate on needs-research); skipping it should advance to feat-b's
            # Step 6 (generate phases).
            ("research-pending-skip", False, False, {
                "terminal_reason": "needs-research",
                "feature_id": "feat-a",
            }),
            ("research-pending-skip", False, True, {
                "sub_skill": "plan-feature",
                "feature_id": "feat-b",
            }),
            # --skip-needs-research with only research-pending features in queue
            # should terminate with queue-blocked-on-research.
            ("research-pending-only", False, True, {
                "terminal_reason": "queue-blocked-on-research",
            }),
            # Retro unwired: when all phases are complete the pipeline routes
            # DIRECTLY to the Step 9 MCP gate, never to retro-feature.
            # Workstation: phases complete, no sentinels → Step 9 mcp-test.
            ("phases-complete-no-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-pcnr",
                "current_step": "Step 9: run MCP tests",
            }),
            # PHASES not-required + no app surface → Step 9 short-circuits to the
            # inline structural skip grant (no /mcp-test dispatch).
            ("phases-complete-no-mcp-surface", False, False, {
                "sub_skill": "__grant_skip_no_mcp_surface__",
                "feature_id": "feat-noms",
                "current_step": "Step 9: structural MCP-skip (no app surface)",
            }),
            # A stale RETRO_DONE.md on disk does NOT change routing (ignored) →
            # still Step 9 mcp test.
            ("phases-complete-retro-done", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-pcrd",
                "current_step": "Step 9: run MCP tests",
            }),
            # Cloud variant: phases complete, no sentinels → Step 9 defers
            # MCP to workstation directly (retro unwired).
            ("phases-complete-no-retro-done-cloud", True, False, {
                "sub_skill": "__write_deferred_non_cloud__",
                "feature_id": "feat-pcnrc",
                "current_step": "Step 9: cloud defers MCP test",
            }),
            # Cloud variant with stale RETRO_DONE.md: ignored for routing →
            # Step 9 writes DEFERRED_NON_CLOUD.md.
            ("phases-complete-retro-done-cloud", True, False, {
                "sub_skill": "__write_deferred_non_cloud__",
                "feature_id": "feat-pcrdc",
                "current_step": "Step 9: cloud defers MCP test",
            }),
            # spike-pipeline-role Phase 2 (WU-1): PHASES.md declares
            # `**Spike:** required` and NO SPIKE_VERDICT.md exists — the
            # Step 9.5 gate must route to sub_skill "spike" instead of
            # falling through to Step 10 mark-complete.
            # RED today: no Step 9.5 gate exists yet — this fixture reaches
            # Step 10 directly (sub_skill: "__mark_complete__").
            ("spike-required-no-verdict", False, False, {
                "sub_skill": "spike",
                "feature_id": "feat-spk",
                "current_step": "Step 9.5: spike verdict pending",
            }),
            # Same PHASES.md, but a SPIKE_VERDICT.md with verdict: PASS is
            # already on disk — must fall through to Step 10 exactly as
            # today (sub_skill: "__mark_complete__"), never routed to spike.
            ("spike-required-pass-verdict", False, False, {
                "sub_skill": "__mark_complete__",
                "feature_id": "feat-spkp",
                "current_step": "Step 10: mark complete",
            }),
            # Cloud-saturation gate: In-progress plan whose only unchecked
            # WU is documented in DEFERRED_NON_CLOUD.md → flip pseudo-skill.
            ("cloud-saturated-in-progress-plan", True, False, {
                "sub_skill": "__flip_plan_complete_cloud_saturated__",
                "feature_id": "feat-cs",
                "current_step": "Step 7a: flip plan Complete (cloud-saturated)",
            }),
            # Cloud: In-progress plan but DEFERRED_NON_CLOUD.md does NOT
            # document the unchecked WU → gate must NOT fire; dispatch
            # execute-plan as usual.
            ("cloud-in-progress-plan-not-saturated", True, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-csn",
                "current_step": "Step 7a: execute plan",
            }),
            # Workstation regression: same shape as the cloud-saturated
            # fixture, but cloud=False. Gate is cloud-only — workstation
            # must keep dispatching execute-plan so the workstation runtime
            # can still complete the gated WU.
            ("workstation-in-progress-plan-with-deferred", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-wcs",
                "current_step": "Step 7a: execute plan",
            }),
            # Device-deferral (real-device axis). Same fixture under both device
            # states (5-tuple pins real_device):
            #   no-device → Step 2 device-saturated skip → device-queue-exhausted
            ("device-deferred-pending", False, False, {
                "terminal_reason": "device-queue-exhausted",
            }, False),
            #   real-device → Step 9 re-open → /mcp-test scoped to the deferred
            #   scenario set (AQ-TE-05). Asserts the scenario IDs are threaded
            #   into the dispatch args (extra check below).
            ("device-deferred-pending", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-dd",
                "current_step": "Step 9: re-open device-deferred scenarios (real-device host)",
            }, True),
            # After re-open succeeds (sentinel deleted, VALIDATED.md written),
            # a real-device run proceeds to __mark_complete__.
            ("device-deferred-cleared", False, False, {
                "sub_skill": "__mark_complete__",
                "feature_id": "feat-dc",
            }, True),
            # Stray-race hardening: VALIDATED.md present but the deferral sentinel
            # was NOT deleted. The sentinel's presence MUST block completion — a
            # real-device host re-fires the re-open (self-healing), it does NOT
            # flip Complete. Proves VALIDATED.md alone cannot bypass the deferral.
            ("device-deferred-stale-validated", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-dsv",
                "current_step": "Step 9: re-open device-deferred scenarios (real-device host)",
            }, True),
            # Mixed skip+deferral: the deferral takes precedence — a real-device
            # host RE-OPENS rather than completing via the skip. Proves a buried
            # real-device assertion can't be masked by a co-present permanent skip.
            ("device-deferred-with-skip", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-dws",
                "current_step": "Step 9: re-open device-deferred scenarios (real-device host)",
            }, True),
            # host-capability-declaration Phase 4: an unregistered requires_host:
            # id fails fast → BLOCKED.md (blocker_kind: unknown-host-capability),
            # NOT a silent defer. (host_present is irrelevant — fail-fast runs
            # before the match; pass empty set for hermeticity.)
            ("host-unknown-cap-failfast", False, False, {
                "terminal_reason": "blocked",
                "feature_id": "feat-huc",
                "current_step": "Step 3: blocked",
            }, True, set()),
            # host-capability-declaration Phase 4 guard: a feature declaring ONLY
            # a registered id (gpu) with gpu present does NOT trip the fail-fast
            # and does NOT defer — it reaches Step 9 mcp-test normally.
            ("host-registered-cap-no-failfast", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-hrc",
                "current_step": "Step 9: run MCP tests",
            }, True, {"gpu"}),
            # host-capability-declaration Phase 5 (a) composite AND-defer: two
            # caps, one present one absent ⇒ missing = {gpu} ⇒ deferral skip ⇒
            # host-capability-saturated terminal (single-item queue).
            ("host-cap-miss-defers", False, False, {
                "terminal_reason": "host-capability-saturated",
            }, True, {"real-audio-device"}),
            # host-capability-declaration Phase 5 (b) re-open: every required cap
            # present (missing empty) ⇒ no skip ⇒ dispatched into Step 9 runtime
            # validation. Re-open is no-special-case.
            ("host-cap-present-reopens", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-hcp",
                "current_step": "Step 9: run MCP tests",
            }, True, {"gpu"}),
            # host-capability-declaration Phase 5 (d) ungated-unaffected baseline
            # regression: a feature with NO requires_host: marker is byte-
            # identical to today — Step 9 mcp-test, never a deferral. (host_present
            # empty proves an ungated feature ignores the host probe entirely.)
            ("host-ungated-baseline", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-hub",
                "current_step": "Step 9: run MCP tests",
            }, True, set()),
            # Stale MCP results freshness gate (WU-4). The on-disk
            # MCP_TEST_RESULTS.md carries validated_commit=all-zeros, which cannot
            # equal the fixture's actual git HEAD. The implementation must detect
            # the mismatch and re-verify (sub_skill=mcp-test) rather than silently
            # accepting the stale results as proof of the current commit.
            # RED against current code: compute_state ignores validated_commit and
            # returns sub_skill="__write_validated_from_results__" instead.
            ("stale-mcp-results-reverify", False, False, {
                "sub_skill": "mcp-test",
                "feature_id": "feat-smrr",
                "current_step": "Step 9: stale MCP results — re-verify",
            }),
            # 2026-06-23 DEADLOCK fix (hardening-log Round 36): validated_commit
            # (sha A) != HEAD (sha B) but the A→B drift is PURE DOCS-ONLY (*.md)
            # — the structurally-unavoidable one-commit lag from the /mcp-test
            # cycle committing its own MCP_TEST_RESULTS.md under the clean-tree
            # turn-end contract. MUST route to Step 9b write-validated, NOT
            # re-verify. RED against pre-fix code (strict validated_commit !=
            # HEAD re-verified → infinite deadlock loop on EVERY feature).
            ("docsonly-drift-validate", False, False, {
                "sub_skill": "__write_validated_from_results__",
                "feature_id": "feat-dod",
                "current_step": "Step 9b: write validated",
            }),
            # WU-5: pipeline-self-granted SKIP_MCP_TEST.md must NOT vacuously
            # validate. When `granted_by: pipeline`, the pipeline is trying to
            # self-waive its own validation requirement — refuse this and route
            # to needs-input so an operator can review.
            # RED against current code: current Step 9 ignores `granted_by` and
            # emits sub_skill="__write_validated_from_skip__" instead of
            # terminal_reason="needs-input".
            ("skip-pipeline-granted-needs-input", False, False, {
                "terminal_reason": "needs-input",
                "feature_id": "feat-spg",
            }),
            # WU-5 positive guard: operator-granted SKIP_MCP_TEST.md must still
            # produce __write_validated_from_skip__ (legitimate human waiver).
            # GREEN even against current code — kept as a non-regression guard.
            # If this fixture ever turns RED, it means the Phase-2 impl broke
            # the backward-compat path for operator grants.
            ("skip-operator-granted-validates", False, False, {
                "sub_skill": "__write_validated_from_skip__",
                "feature_id": "feat-sog",
                "current_step": "Step 9: skip-mcp-test → validated",
            }),
            # skip-mcp-test-frontmatter-unquoted-colon Phase 2: an operator waiver
            # whose `reason:` carries an UNQUOTED colon-space must still route to
            # __write_validated_from_skip__ (parse_sentinel tolerant read) rather
            # than exiting 2 at the strict YAML parse. RED before Phase 1.
            ("skip-operator-colon-reason-validates", False, False, {
                "sub_skill": "__write_validated_from_skip__",
                "feature_id": "feat-socr",
                "current_step": "Step 9: skip-mcp-test → validated",
            }),
            # Provenance positive: granted_by: mcp-test WITH a spec_class
            # citation is a verified structural assessment by the validation
            # step itself — accepted → __write_validated_from_skip__.
            ("skip-mcp-test-granted-with-class-validates", False, False, {
                "sub_skill": "__write_validated_from_skip__",
                "feature_id": "feat-smtc",
                "current_step": "Step 9: skip-mcp-test → validated",
            }),
            # Provenance gate: granted_by: mcp-test WITHOUT spec_class is an
            # unverified claim — refuse (needs-input), never vacuous-validate.
            ("skip-mcp-test-granted-missing-class-refuses", False, False, {
                "terminal_reason": "needs-input",
                "feature_id": "feat-smtn",
            }),
            # Provenance omission gate: pipeline-authored skip (skipped_by:
            # lazy) with NO granted_by must refuse — closes the side-door where
            # omitting the field bypassed the WU-5 provenance gate entirely.
            ("skip-pipeline-authored-no-grant-refuses", False, False, {
                "terminal_reason": "needs-input",
                "feature_id": "feat-spa",
            }),
            # Fixture A — roadmap_marks_complete substring collision.
            # Feature name "Audio" is a strict substring of the completed ROADMAP
            # text "Audio Engine". Pre-fix: falsely halts with completion-unverified.
            # Post-fix: normal Draft routing → Step 5 /spec (no research files).
            # RED today: roadmap_marks_complete substring-matches the Audio Engine
            # row → completion_claimed returns True → no receipt → halt.
            ("roadmap-substring-collision-no-false-halt", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-audio",
                "current_step": "Step 5: generate research prompt",
            }),
            # Fixture B — is_stub_spec prose-mention false-positive.
            # SPEC.md Status is plain "Draft" (not a stub), but the body prose
            # contains the literal phrase "Draft (pre-Gemini)" as illustrative text.
            # Pre-fix: bare substring match triggers stub route → Step 4.5 /spec.
            # Post-fix: only the **Status:** line is checked → not a stub →
            # proceeds to Step 6 /plan-feature (research present, no PHASES.md).
            # RED today: "Draft (pre-Gemini)" in spec_text matches the prose.
            ("is-stub-prose-mention-not-stub", False, False, {
                "sub_skill": "plan-feature",
                "feature_id": "feat-prose-stub",
                "current_step": "Step 6: plan feature (phases + plan)",
            }),
            # Fixture C — upstream_is_complete substring collision.
            # Upstream feature dir "audio" is a strict substring of the completed
            # ROADMAP entry "audio-engine". Pre-fix: upstream_is_complete falsely
            # returns True → triggers realign-spec at Step 4.6. Post-fix: word-
            # boundary anchor prevents the collision → no realign → Step 5 /spec.
            # RED today: upstream_name in line matches "audio-engine" for "audio".
            ("upstream-substring-collision", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-downstream",
                "current_step": "Step 5: generate research prompt",
            }),
            # Fixture A — stale-plan: plan's phases: [1] scope is fully checked
            # but Phase 2 has an unchecked row so unchecked > 0 overall → Step 7
            # is entered. The plan should be recognised as stale and the pseudo-
            # skill __flip_plan_complete_stale__ emitted (not execute-plan).
            # RED today: current code emits sub_skill="execute-plan".
            # current_step is asserted via a post-loop substring check below
            # (impl agent sets the exact string; we require "stale" appear in it).
            ("stale-plan-all-refs-checked-flips", False, False, {
                "sub_skill": "__flip_plan_complete_stale__",
                "feature_id": "feat-stale",
            }),
            # Fixture B — discriminating guard: plan still has real unchecked work
            # inside its phases: [1] scope → stale-plan guard must NOT fire.
            # GREEN today and must stay GREEN after the fix lands.
            ("ready-plan-unchecked-in-scope-still-executes", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-live",
                "current_step": "Step 7a: execute plan",
            }),
            # plan-structure-authoring-gate Phase 4 pickup backstop: a FRESH
            # structurally-invalid plan (zero ticked WUs) refuses the route.
            ("plan-structural-backstop-refuses-fresh-invalid", False, False, {
                "terminal_reason": "blocked",
                "feature_id": "feat-pstruct-fresh",
            }),
            # Same defect, but mid-execution (>=1 ticked WU) — WARN-only,
            # falls through to execute-plan as normal.
            ("plan-structural-backstop-mid-execution-warns", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-pstruct-mid",
                "current_step": "Step 7a: execute plan",
            }),
            # Phase 8 — finalization gap (option b). The plan's in-scope
            # unchecked remainder is entirely Runtime-Verification rows → the
            # finalize-stale branch must route to __flip_plan_complete_stale__
            # (NOT a redundant execute-plan re-dispatch).
            # RED today: code emits sub_skill="execute-plan".
            ("finalize-plan-verification-rows-only-flips", False, False, {
                "sub_skill": "__flip_plan_complete_stale__",
                "feature_id": "feat-fin",
            }),

            # Empty-PHASES-scope guard (f1-global-scale part-0, 2026-06-19): a
            # phases:[0] decomposition part with no PHASES Phase 0 and UNCHECKED
            # plan-body WU boxes must route to execute-plan (NOT vacuously flip
            # stale and silently drop the decomposition).
            ("stale-empty-scope-decomposition-executes", False, False, {
                "sub_skill": "execute-plan",
                "feature_id": "feat-decomp",
                "current_step": "Step 7a: execute plan",
            }),
            # Discriminating control: same empty-PHASES-scope shape but the
            # plan-body WU boxes are ALL [x] → genuinely stale (decomposition done,
            # frontmatter never flipped) → the fallback flips it Complete.
            ("stale-empty-scope-all-plan-wus-checked-flips", False, False, {
                "sub_skill": "__flip_plan_complete_stale__",
                "feature_id": "feat-decdone",
            }),

            # WU-8 Fixture 1: realign hash gate detects changed upstream.
            # Downstream has a hard dep on a complete upstream. The realign plan
            # frontmatter records upstream_phases_hashes: with a BOGUS hash (64
            # zeros). The plan mtime is NEWER than the upstream PHASES.md mtime
            # (so the old mtime gate declares fresh). The hash gate must detect the
            # mismatch and require a new realign.
            # RED today: realign_is_fresh() compares mtimes → plan is newer →
            # declares fresh → no realign → routes onward (Step 5/6, not Step 4.6).
            # GREEN after fix: hash gate fires → sub_skill="realign-spec".
            ("realign-hash-gate-detects-changed-upstream", False, False, {
                "sub_skill": "realign-spec",
                "feature_id": "feat-rhg",
                "current_step": "Step 4.6: upstream realign needed",
            }),

            # WU-8 Fixture 2: check_stale_upstream auto-wired at probe start.
            # materialized.json + ado-mirror.json show upstream WI changed.
            # STALE_UPSTREAM.md NOT pre-written. compute_state must auto-call
            # check_stale_upstream and then halt at Step 2.9.
            # RED today: nothing auto-runs check_stale_upstream → no STALE_UPSTREAM.md
            # written → feature routes through normal early pipeline (e.g. Step 4/5).
            # GREEN after fix: auto-call writes STALE_UPSTREAM.md → Step 2.9 halts
            # with terminal_reason="stale_upstream".
            ("stale-upstream-auto-wired-at-probe", False, False, {
                "terminal_reason": "stale_upstream",
                "feature_id": "feat-sau",
            }),

            # merged-head-oracle-per-signal-supplement-churn Phase 1: the
            # feature-side operator-defer branch (mirror of bug-state.py). RED
            # until the walk-loop DEFERRED.md skip + global terminal land.
            # Deferred feature skipped, actionable feature dispatched; the
            # operator_deferred probe key names the parked feature.
            ("operator-deferred-skip", False, False, {
                "feature_id": "feat-actionable",
                "sub_skill": "spec",
                "operator_deferred": ["Deferred Feature"],
            }),
            # Only the deferred feature remains → the global all-remaining-deferred
            # terminal fires with a null identity (NOT all-features-complete).
            ("all-operator-deferred", False, False, {
                "terminal_reason": TR_ALL_DEFERRED,
                "feature_id": None,
                "operator_deferred": ["Only Deferred Feature"],
            }),
            # Control: DEFERRED.md absent → the same feature is dispatchable
            # (proving the branch is the sole exclusion mechanism).
            ("operator-deferred-control", False, False, {
                "sub_skill": "spec",
                "feature_id": "feat-ctrl",
                "operator_deferred": [],
            }),
            # NOTE: WU-8 Fixture 3 (step10-unexpected-writes-needs-input) is NOT a
            # compute_state routing case. The Step 10 "unexpected state" branch is
            # GENUINELY UNREACHABLE through compute_state's inputs (workstation Step 9
            # is fully guarded by `if not validated_file.exists():` and every sub-path
            # returns, so Step 10 is only reached when validated_file exists →
            # entry_ok is always True there). Forcing a RETRO_DONE + no-validation
            # state to write NEEDS_INPUT would break normal MCP-test dispatch.
            #
            # The honest, testable unit for this defensive branch is the sentinel
            # WRITE itself, which the impl agent extracts into the module-level helper
            # _write_step10_needs_input(spec_dir, feature_name). That helper is
            # exercised directly in an inline functional check AFTER this loop (search
            # for "Fixture WU-8.3" below), mirroring how enqueue_adhoc / materialize_wi
            # are tested directly rather than through compute_state.
        ]
        for case in cases:
            # Cases are 4-tuples (real_device defaults to True — behavior
            # preserving), 5-tuples that pin real_device explicitly for the
            # device-deferral fixtures, or 6-tuples whose 6th element is an
            # injected host_present set (host-capability-declaration Phase 5 —
            # the hermetic seam so --test never touches the real host probe).
            name, cloud, skip_nr, expected = case[0], case[1], case[2], case[3]
            real_device = case[4] if len(case) > 4 else True
            host_present = case[5] if len(case) > 5 else None
            root = _build_fixture(td_path, name)
            try:
                got = compute_state(
                    root, cloud=cloud, skip_needs_research=skip_nr,
                    real_device=real_device, host_present=host_present,
                )
            except SystemExit as exc:
                failures.append(f"[{name}] SystemExit: {exc.code}")
                continue
            for k, v in expected.items():
                if got.get(k) != v:
                    failures.append(
                        f"[{name}] expected {k}={v!r}, got {k}={got.get(k)!r}"
                    )
            # Extra assertions: plan-frontmatter selection prefers lowest phase
            if name == "plan-frontmatter-filter":
                args = got.get("sub_skill_args") or ""
                if "phase-3-corrective.md" not in args:
                    failures.append(
                        f"[{name}] expected phase-3 plan to be selected, got "
                        f"sub_skill_args={args!r}"
                    )
                if "all-phases-old.md" in args:
                    failures.append(
                        f"[{name}] Complete plan should be filtered out, "
                        f"sub_skill_args={args!r}"
                    )
            if name == "legacy-plan-diagnostics":
                diag = got.get("diagnostics") or []
                if not any("all-phases-legacy.md" in d for d in diag):
                    failures.append(
                        f"[{name}] expected diagnostics warning about legacy "
                        f"plan; got diagnostics={diag!r}"
                    )
            if name == "research-gate-skipped-when-phases-implemented":
                # D3 (no silent skip): the guard MUST emit the greppable
                # diagnostic when it bypasses the research gate.
                diag = got.get("diagnostics") or []
                if not any(
                    "Step 5 research gate skipped" in d for d in diag
                ):
                    failures.append(
                        f"[{name}] expected the D3 'Step 5 research gate "
                        f"skipped' diagnostic; got diagnostics={diag!r}"
                    )
            if name == "research-pending-only" and skip_nr:
                diag = got.get("diagnostics") or []
                if not any("research-pending skipped" in d for d in diag):
                    failures.append(
                        f"[{name}] expected research-pending diagnostics; "
                        f"got diagnostics={diag!r}"
                    )
            if name == "adhoc-brief":
                args = got.get("sub_skill_args") or ""
                if "ADHOC_BRIEF.md" not in args:
                    failures.append(
                        f"[{name}] expected sub_skill_args to reference "
                        f"ADHOC_BRIEF.md; got {args!r}"
                    )
            if name == "stub-queue-flag-lone-survivor":
                # The discriminator MUST have cleared the on-disk queue flag.
                qp = root / "docs" / "features" / "queue.json"
                qdata = json.loads(qp.read_text(encoding="utf-8"))
                entry = next(
                    (e for e in qdata.get("queue", [])
                     if e.get("id") == "feat-stub-lone"),
                    None,
                )
                if entry is None:
                    failures.append(
                        f"[{name}] queue entry feat-stub-lone disappeared"
                    )
                elif "stub" in entry:
                    failures.append(
                        f"[{name}] expected the queue 'stub' flag to be "
                        f"cleared on baseline-lock; got entry={entry!r}"
                    )
            if name == "stub-queue-flag-only":
                # The true pre-baseline stub MUST keep its queue flag (the
                # discriminator only clears when the SPEC-text marker is gone).
                qp = root / "docs" / "features" / "queue.json"
                qdata = json.loads(qp.read_text(encoding="utf-8"))
                entry = next(
                    (e for e in qdata.get("queue", [])
                     if e.get("id") == "feat-stub-queue"),
                    None,
                )
                if entry is None or entry.get("stub") is not True:
                    failures.append(
                        f"[{name}] a true pre-baseline stub must NOT have its "
                        f"queue flag cleared; got entry={entry!r}"
                    )
            if name == "autodiscover-dedupes-explicit-twin":
                # Direct load_queue assertion: feat-dup appears EXACTLY ONCE and
                # the explicit (queue_entry-bearing) entry is the one retained,
                # listed first — the discovered twin must be deduped out.
                merged = load_queue(root)
                dup_entries = [e for e in merged if e.get("id") == "feat-dup"]
                if len(dup_entries) != 1:
                    failures.append(
                        f"[{name}] feat-dup must appear exactly once in the merged "
                        f"work-list; got {len(dup_entries)} entries: {dup_entries!r}"
                    )
                elif "queue_entry" in dup_entries[0]:
                    # A discovered entry carries an explicit queue_entry: None key;
                    # a raw explicit queue.json item does NOT. The retained twin
                    # must be the explicit (raw) one, so the key must be ABSENT.
                    failures.append(
                        f"[{name}] the retained feat-dup must be the EXPLICIT (raw "
                        f"queue.json) entry, not the discovered twin; got "
                        f"{dup_entries[0]!r}"
                    )
                if merged and merged[0].get("id") != "feat-dup":
                    failures.append(
                        f"[{name}] the explicit entry must be listed FIRST; got "
                        f"head id={merged[0].get('id')!r}"
                    )
            if name == "autodiscover-orders-by-priority":
                # Direct load_queue assertion: the discovered P1 dir (feat-hi)
                # sorts before the P3 dir (feat-zlo) — by feature_tier rank, then
                # dir name on ties.
                merged = load_queue(root)
                ids = [e.get("id") for e in merged]
                if "feat-hi" in ids and "feat-zlo" in ids:
                    if ids.index("feat-hi") >= ids.index("feat-zlo"):
                        failures.append(
                            f"[{name}] P1 feat-hi must sort before P3 feat-zlo; "
                            f"got order={ids!r}"
                        )
                else:
                    failures.append(
                        f"[{name}] both discovered dirs must be in the merged "
                        f"work-list; got ids={ids!r}"
                    )
            if name == "device-deferred-pending" and real_device:
                # The re-open MUST thread the specific deferred scenario IDs so
                # /mcp-test knows exactly which assertions to certify.
                args = got.get("sub_skill_args") or ""
                if "AQ-TE-05" not in args:
                    failures.append(
                        f"[{name}] re-open args must name the deferred scenario "
                        f"IDs (AQ-TE-05); got {args!r}"
                    )
            if name == "device-deferred-pending" and not real_device:
                diag = got.get("diagnostics") or []
                if not any("device-saturated skipped" in d for d in diag):
                    failures.append(
                        f"[{name}] expected device-saturated diagnostics; "
                        f"got diagnostics={diag!r}"
                    )
            if name == "host-unknown-cap-failfast":
                # The fail-fast MUST have written a real BLOCKED.md whose body
                # names BOTH the offending typo'd id and the sorted registry ids.
                bf = root / "docs" / "features" / "feat-huc" / "BLOCKED.md"
                if not bf.exists():
                    failures.append(
                        f"[{name}] expected BLOCKED.md to be written by the "
                        f"unknown-host-capability fail-fast; missing"
                    )
                else:
                    meta = lazy_core.parse_sentinel(bf) or {}
                    if meta.get("blocker_kind") != "unknown-host-capability":
                        failures.append(
                            f"[{name}] expected blocker_kind: "
                            f"unknown-host-capability; got {meta.get('blocker_kind')!r}"
                        )
                    body = bf.read_text(encoding="utf-8")
                    if "typo-cap" not in body:
                        failures.append(
                            f"[{name}] BLOCKED.md body must name the offending "
                            f"id 'typo-cap'; got body={body!r}"
                        )
                    # The sorted registry ids must be named so the operator can
                    # fix the typo or register a probe.
                    for reg_id in sorted(lazy_core._HOST_CAPABILITY_REGISTRY):
                        if reg_id not in body:
                            failures.append(
                                f"[{name}] BLOCKED.md body must name registry "
                                f"id {reg_id!r}; got body={body!r}"
                            )
            if name == "host-registered-cap-no-failfast":
                # The guard against an over-broad fail-fast: a registered id must
                # NOT write BLOCKED.md.
                bf = root / "docs" / "features" / "feat-hrc" / "BLOCKED.md"
                if bf.exists():
                    failures.append(
                        f"[{name}] a registered requires_host: id must NOT trip "
                        f"the fail-fast, but BLOCKED.md was written"
                    )
            if name == "host-cap-miss-defers":
                # The capability-miss branch MUST write DEFERRED_REQUIRES_HOST.md
                # carrying the missing cap id (gpu), and surface it in the
                # host_deferred_features probe key + a per-probe diagnostic.
                df = root / "docs" / "features" / "feat-hcm" / "DEFERRED_REQUIRES_HOST.md"
                if not df.exists():
                    failures.append(
                        f"[{name}] expected DEFERRED_REQUIRES_HOST.md to be "
                        f"written on a capability miss; missing"
                    )
                else:
                    meta = lazy_core.parse_sentinel(df) or {}
                    if meta.get("kind") != "deferred-requires-host":
                        failures.append(
                            f"[{name}] expected kind: deferred-requires-host; "
                            f"got {meta.get('kind')!r}"
                        )
                    missing = meta.get("missing_capabilities") or []
                    if "gpu" not in missing:
                        failures.append(
                            f"[{name}] DEFERRED_REQUIRES_HOST.md must name the "
                            f"missing cap 'gpu'; got missing_capabilities={missing!r}"
                        )
                    # The present cap must NOT be listed as missing (composite AND).
                    if "real-audio-device" in missing:
                        failures.append(
                            f"[{name}] a present cap must NOT be in "
                            f"missing_capabilities; got {missing!r}"
                        )
                hdf = got.get("host_deferred_features") or []
                if "feat-hcm" not in hdf:
                    failures.append(
                        f"[{name}] expected feat-hcm in host_deferred_features; "
                        f"got {hdf!r}"
                    )
                diag = got.get("diagnostics") or []
                if not any("host-capability" in d and "gpu" in d for d in diag):
                    failures.append(
                        f"[{name}] expected a host-capability diagnostic naming "
                        f"the missing id; got diagnostics={diag!r}"
                    )
                nm = got.get("notify_message") or ""
                if "feat-hcm" not in nm or "gpu" not in nm:
                    failures.append(
                        f"[{name}] terminal notify_message must name the feature "
                        f"+ missing cap; got {nm!r}"
                    )
            if name == "host-cap-present-reopens":
                # Re-open: NO DEFERRED_REQUIRES_HOST.md is written when missing
                # is empty.
                df = root / "docs" / "features" / "feat-hcp" / "DEFERRED_REQUIRES_HOST.md"
                if df.exists():
                    failures.append(
                        f"[{name}] missing-empty re-open must NOT write "
                        f"DEFERRED_REQUIRES_HOST.md, but it exists"
                    )
                if got.get("host_deferred_features"):
                    failures.append(
                        f"[{name}] re-open must not surface host_deferred_features; "
                        f"got {got.get('host_deferred_features')!r}"
                    )
            if name == "host-ungated-baseline":
                # Ungated baseline regression: no requires_host: ⇒ no deferral
                # sentinel, no host_deferred_features.
                df = root / "docs" / "features" / "feat-hub" / "DEFERRED_REQUIRES_HOST.md"
                if df.exists():
                    failures.append(
                        f"[{name}] an ungated feature must NOT write "
                        f"DEFERRED_REQUIRES_HOST.md"
                    )
                if got.get("host_deferred_features"):
                    failures.append(
                        f"[{name}] ungated feature must not surface "
                        f"host_deferred_features; got "
                        f"{got.get('host_deferred_features')!r}"
                    )
            if name == "stale-plan-all-refs-checked-flips":
                # current_step substring check: after the fix the impl agent will
                # emit something containing "stale". We do NOT assert the exact
                # string so small wording changes don't break this fixture.
                # (The primary behavioral signal is sub_skill above.)
                cs = got.get("current_step") or ""
                if cs and "stale" not in cs.lower():
                    failures.append(
                        f"[{name}] expected current_step to contain 'stale'; "
                        f"got {cs!r}"
                    )
                # sub_skill_args must reference the plan file path.
                args = got.get("sub_skill_args") or ""
                if args and "all-phases-stale.md" not in args:
                    failures.append(
                        f"[{name}] expected sub_skill_args to reference the stale "
                        f"plan file; got {args!r}"
                    )
            if name == "finalize-plan-verification-rows-only-flips":
                # Phase 8 finalization gap: the flip must reference the plan file
                # and the step must read as a stale/finalize flip (not execute).
                cs = got.get("current_step") or ""
                if cs and "stale" not in cs.lower():
                    failures.append(
                        f"[{name}] expected current_step to read as a stale flip; "
                        f"got {cs!r}"
                    )
                args = got.get("sub_skill_args") or ""
                if args and "all-phases-fin.md" not in args:
                    failures.append(
                        f"[{name}] expected sub_skill_args to reference the plan "
                        f"file; got {args!r}"
                    )
            if name == "stale-upstream-auto-wired-at-probe":
                # Post-call disk check (WU-8 Fixture 2): the auto-wiring at probe
                # start must have WRITTEN STALE_UPSTREAM.md into the feature dir.
                # RED today: check_stale_upstream is never auto-called → the file
                # doesn't exist → this assertion fails regardless of terminal_reason.
                sau_stale_sentinel = (
                    root / "docs" / "features" / "feat-sau" / "STALE_UPSTREAM.md"
                )
                if not sau_stale_sentinel.exists():
                    failures.append(
                        f"[{name}] STALE_UPSTREAM.md was NOT written to "
                        f"{sau_stale_sentinel} — check_stale_upstream not auto-wired "
                        "at probe start"
                    )
            print(
                f"  [{name}] cloud={cloud} skip_nr={skip_nr} "
                f"real_device={real_device}: "
                f"{got['current_step'] or got['terminal_reason']}"
            )

        # -------------------------------------------------------------------
        # Fixture WU-8.3: _write_step10_needs_input writes a well-formed
        # NEEDS_INPUT.md sentinel (direct helper unit test).
        # -------------------------------------------------------------------
        # The Step 10 "unexpected state" defensive branch (compute_state, the
        # `if not entry_ok:` arm) is GENUINELY UNREACHABLE through compute_state's
        # inputs — workstation Step 9 is fully guarded by
        # `if not validated_file.exists():` and every sub-path returns, so Step 10
        # is reached only when validated_file exists, where entry_ok is always
        # True. We therefore can't drive this branch via a routing fixture without
        # breaking normal MCP-test dispatch. The honest, testable unit is the
        # sentinel WRITE the branch performs, which the impl agent extracts into
        # the module-level helper _write_step10_needs_input(spec_dir, feature_name)
        # and calls from the defensive arm. We exercise that helper directly here,
        # exactly the way enqueue_adhoc / materialize_wi are tested directly below.
        #
        # RED today: _write_step10_needs_input does not exist yet → calling it
        # raises NameError ("missing symbol" RED — the standard TDD red for a new
        # function). GREEN after the impl lands the helper: NEEDS_INPUT.md exists
        # on disk, parses as kind="needs-input" with a written_by field, and its
        # body carries the `## Decision Context` H2 that the orchestrator's
        # decision-resume (Step 1g) consumes.
        fix_name_s10 = "step10-unexpected-writes-needs-input"
        s10_spec_dir = td_path / fix_name_s10 / "docs" / "features" / "feat-s10u"
        s10_spec_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Reference the helper as a module-level name (mirrors how the inline
            # checks below call enqueue_adhoc / materialize_wi directly). When the
            # symbol does not yet exist this raises NameError — the intended RED.
            _write_step10_needs_input(s10_spec_dir, "Some Feature")
            s10_ok = True
            # Assertion 1: the sentinel now EXISTS on disk.
            s10_sentinel = s10_spec_dir / "NEEDS_INPUT.md"
            if not s10_sentinel.exists():
                failures.append(
                    f"[{fix_name_s10}] NEEDS_INPUT.md was NOT written to "
                    f"{s10_sentinel} — _write_step10_needs_input must create the "
                    "sentinel the defensive branch tells the orchestrator to resolve"
                )
                s10_ok = False
            else:
                # Assertion 2a: well-formed frontmatter — parse_sentinel yields the
                # required schema fields (kind: needs-input + written_by) so the
                # orchestrator's Step 1g decision-resume can consume it.
                s10_meta = parse_sentinel(s10_sentinel) or {}
                if s10_meta.get("kind") != "needs-input":
                    failures.append(
                        f"[{fix_name_s10}] NEEDS_INPUT.md frontmatter kind must be "
                        f"'needs-input'; got {s10_meta.get('kind')!r}"
                    )
                    s10_ok = False
                if not s10_meta.get("written_by"):
                    failures.append(
                        f"[{fix_name_s10}] NEEDS_INPUT.md frontmatter must carry a "
                        f"'written_by' field; got {s10_meta.get('written_by')!r}"
                    )
                    s10_ok = False
                # Assertion 2b: well-formed body — the `## Decision Context` H2 the
                # orchestrator re-prints verbatim before AskUserQuestion, plus at
                # least one decision described under it. Kept specific (the H2 must
                # be a real heading line) but not brittle (no exact wording pinned).
                s10_text = s10_sentinel.read_text(encoding="utf-8")
                s10_body_lines = s10_text.splitlines()
                has_decision_h2 = any(
                    ln.strip() == "## Decision Context" for ln in s10_body_lines
                )
                if not has_decision_h2:
                    failures.append(
                        f"[{fix_name_s10}] NEEDS_INPUT.md body must contain a "
                        "'## Decision Context' H2 heading (the structure Step 1g "
                        "requires)"
                    )
                    s10_ok = False
                else:
                    # At least one decision must be described under the H2: either a
                    # frontmatter decisions[] entry or an H3 subsection in the body.
                    has_decision_h3 = any(
                        ln.lstrip().startswith("### ") for ln in s10_body_lines
                    )
                    decisions_fm = s10_meta.get("decisions")
                    has_decision_fm = bool(
                        isinstance(decisions_fm, list) and decisions_fm
                    )
                    # Regression guard: every entry must be a plain string, not a
                    # dict. An unquoted "key: value" YAML list item (e.g. a title
                    # containing a colon-space) parses as a nested mapping — a dict —
                    # which breaks the orchestrator's Step 1g decision-resume that
                    # expects string descriptions.
                    if has_decision_fm and not all(
                        isinstance(x, str) for x in decisions_fm
                    ):
                        failures.append(
                            f"[{fix_name_s10}] NEEDS_INPUT.md decisions[] entries must "
                            "all be strings (not dicts); got "
                            f"{[type(x).__name__ for x in decisions_fm]!r} — "
                            "ensure decision_title is quoted in the YAML list item"
                        )
                        s10_ok = False
                        has_decision_fm = False  # don't double-count as passing
                    if not (has_decision_h3 or has_decision_fm):
                        failures.append(
                            f"[{fix_name_s10}] NEEDS_INPUT.md must describe at least "
                            "one decision (an H3 subsection under '## Decision "
                            "Context' or a non-empty decisions[] frontmatter list)"
                        )
                        s10_ok = False
            print(f"  {'PASS' if s10_ok else 'FAIL'} [{fix_name_s10}] "
                  "_write_step10_needs_input writes well-formed NEEDS_INPUT.md")
        except (NameError, AttributeError) as exc:
            # Missing-symbol RED: the helper genuinely does not exist yet. The impl
            # agent will create _write_step10_needs_input and this flips to GREEN.
            failures.append(
                f"[{fix_name_s10}] _write_step10_needs_input is not defined yet "
                f"(missing-helper RED — impl must extract it): {exc}"
            )
            print(f"  FAIL [{fix_name_s10}]: helper not defined — {exc}")

        # -------------------------------------------------------------------
        # Regression guard: realign_is_fresh must NOT force staleness for a
        # hard-complete upstream that has NO PHASES.md (direct helper unit test).
        # -------------------------------------------------------------------
        # Deadlock repro (2026-06-16, mcp-audio-quality-observability): a
        # downstream depends hard on TWO complete upstreams — one decomposed
        # (mcp-testing: has PHASES.md, hash recorded + matching) and one older
        # SPEC-only feature (audio-pipeline-v2: no PHASES.md, never decomposed →
        # unhashable → never appears in upstream_phases_hashes). The hash-path
        # loop used to check `dir_name not in recorded_hashes → return False`
        # BEFORE the `current_sha is None → continue` guard, so the hashless
        # upstream forced realign_is_fresh → False forever → Step 4.6 re-fired
        # every cycle (infinite realign loop blocking the whole queue).
        # GREEN after fix: the None-guard precedes the not-recorded check, so a
        # hashless upstream is skipped and freshness is decided by the hashed
        # upstreams alone.
        fix_name_rhf = "realign-fresh-hashless-upstream-not-stale"
        rhf_root = td_path / fix_name_rhf
        rhf_down = rhf_root / "down"
        (rhf_down / "plans").mkdir(parents=True, exist_ok=True)
        # Hashed upstream: PHASES.md present, hash recorded + matching.
        rhf_up_hashed = rhf_root / "up-hashed"
        rhf_up_hashed.mkdir(parents=True, exist_ok=True)
        (rhf_up_hashed / "PHASES.md").write_text("# Phases\n\n- [x] done\n")
        rhf_hashed_sha = _phases_sha(rhf_up_hashed)
        # Hashless upstream: SPEC.md only, NO PHASES.md (the deadlock trigger).
        rhf_up_nophases = rhf_root / "up-nophases"
        rhf_up_nophases.mkdir(parents=True, exist_ok=True)
        (rhf_up_nophases / "SPEC.md").write_text("# Up\n\n**Status:** Complete\n")
        # A correct realign plan records ONLY the hashable upstream (the
        # hashless one cannot be hashed, so it is legitimately omitted).
        (rhf_down / "plans" / "realign-2026-06-16.md").write_text(
            "---\n"
            "kind: realign-plan\n"
            "upstream_phases_hashes:\n"
            f"  up-hashed: {rhf_hashed_sha}\n"
            "---\n\n# Realign plan\n"
        )
        # Both upstreams are hard-complete; the hashless one MUST NOT force stale.
        rhf_fresh = realign_is_fresh(rhf_down, [rhf_up_hashed, rhf_up_nophases])
        if rhf_fresh is not True:
            failures.append(
                f"[{fix_name_rhf}] realign_is_fresh returned {rhf_fresh!r}; a "
                "hard-complete upstream with no PHASES.md must be SKIPPED, not "
                "treated as stale (deadlock guard — Step 4.6 infinite loop)"
            )
        # Negative control: genuine drift on the HASHED upstream must still
        # report stale even with the hashless upstream present — the None-guard
        # reorder must not mask real PHASES.md changes.
        (rhf_up_hashed / "PHASES.md").write_text("# Phases\n\n- [x] CHANGED\n")
        rhf_stale = realign_is_fresh(rhf_down, [rhf_up_hashed, rhf_up_nophases])
        if rhf_stale is not False:
            failures.append(
                f"[{fix_name_rhf}] realign_is_fresh returned {rhf_stale!r} after "
                "the hashed upstream PHASES.md changed; genuine drift must still "
                "report stale (the None-guard reorder must not mask real changes)"
            )
        print(f"  {'PASS' if (rhf_fresh is True and rhf_stale is False) else 'FAIL'} "
              f"[{fix_name_rhf}] hashless upstream skipped; real drift still stale")

        # Functional check (feature-budget-guard-and-skip-ahead Phase 1):
        # the per-feature forward-cycle counter rides BOTH forward-advance
        # triggers and is keyed on feature_id. Round-trip the run marker through
        # claude_state_dir() by pinning LAZY_STATE_DIR at an isolated temp dir.
        # Drive one fixture feature through ≥2 forward-advancing cycles (a
        # real-skill dispatch via advance_run_counters + a forward-advancing
        # pseudo-skill apply via advance_forward_cycle), assert the per-feature
        # count equals the run-level forward count for that feature, a meta-only
        # cycle does NOT increment it, and a second feature gets its own key.
        pf_state_dir = td_path / "per-feature-counter-state"
        pf_state_dir.mkdir(parents=True, exist_ok=True)
        _pf_prev_env = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = str(pf_state_dir)
        try:
            import time as _pf_time
            mk = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(td_path),
                max_cycles=20, now=_pf_time.time(),
            )
            if mk.get("per_feature_forward_cycles") != {}:
                failures.append(
                    "[per-feature-counter] write_run_marker did not seed "
                    f"per_feature_forward_cycles: {{}} (got "
                    f"{mk.get('per_feature_forward_cycles')!r})"
                )
            # Cycle 1 — real skill on feat-pf via the consume-oracle trigger.
            _e = lazy_core.register_emission("pf", "cycle")
            lazy_core.consume_nonce(_e["nonce"])
            m1 = lazy_core.advance_run_counters({
                "sub_skill": "execute-plan", "feature_id": "feat-pf",
                "current_step": "Step 7a: execute plan",
            })
            # Cycle 2 — forward-advancing pseudo-skill on the SAME feature via the
            # state-change trigger (no consume).
            m2 = lazy_core.advance_forward_cycle({
                "sub_skill": "__mark_complete__", "feature_id": "feat-pf",
                "current_step": "Step 10: mark complete",
            })
            # Meta-only cycle on the SAME feature — must NOT increment.
            m3 = lazy_core.advance_forward_cycle({
                "sub_skill": "__neutralize_sentinel__", "feature_id": "feat-pf",
                "current_step": "cleanup",
            })
            # A second feature gets its own independent key.
            m4 = lazy_core.advance_forward_cycle({
                "sub_skill": "execute-plan", "feature_id": "feat-pf2",
                "current_step": "Step 7a: execute plan",
            })
            pf_map = m4.get("per_feature_forward_cycles", {})
            if pf_map.get("feat-pf") != 2:
                failures.append(
                    "[per-feature-counter] per_feature_forward_cycles[feat-pf] "
                    f"expected 2 (the run-level forward count), got "
                    f"{pf_map.get('feat-pf')!r}"
                )
            if m4.get("forward_cycles") != 3:
                failures.append(
                    "[per-feature-counter] run-level forward_cycles expected 3 "
                    f"(2 feat-pf + 1 feat-pf2), got {m4.get('forward_cycles')!r}"
                )
            if pf_map.get("feat-pf2") != 1:
                failures.append(
                    "[per-feature-counter] a second feature must accrue its own "
                    f"independent count of 1, got {pf_map.get('feat-pf2')!r}"
                )
            # Round-trip via the read path + read helper.
            on_disk = lazy_core.read_run_marker(now=_pf_time.time())
            if lazy_core.read_per_feature_forward_cycles(on_disk).get("feat-pf") != 2:
                failures.append(
                    "[per-feature-counter] read_per_feature_forward_cycles did not "
                    "round-trip the marker map through claude_state_dir()"
                )
            print("  [per-feature-counter] per_feature_forward_cycles rides both "
                  "advance triggers, meta-exempt, per-feature keyed: ok")
        finally:
            if _pf_prev_env is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = _pf_prev_env

        # Functional check (feature-budget-guard-and-skip-ahead Phase 2, WU-4):
        # the per-feature budget guard trips at the computed ceiling, defers the
        # tripped feature to the live-queue tail (run-scoped reorder, NOT written
        # to queue.json), dispatches the next ready item, surfaces a budget_guard
        # probe field, escalates a 2nd trip to terminal eviction, and returns an
        # honest exhaustion terminal when only budget-deferred/evicted items remain.
        def _bg_make_feature(root: Path, fid: str) -> None:
            """Build a minimal mid-implementation feature dir that dispatches a
            real sub_skill (execute-plan)."""
            fdir = root / "docs" / "features" / fid
            fdir.mkdir(parents=True, exist_ok=True)
            (fdir / "SPEC.md").write_text(
                "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
            )
            (fdir / "RESEARCH.md").write_text("# Research\n")
            (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n")
            (fdir / "PHASES.md").write_text(
                "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n"
            )
            (fdir / "plans").mkdir(exist_ok=True)
            (fdir / "plans" / f"all-phases-{fid}.md").write_text("# Plan\n")

        bg_root = td_path / "budget-guard"
        (bg_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (bg_root / "docs" / "features" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-bg1", "name": "BG One", "spec_dir": "feat-bg1", "tier": 1},
                {"id": "feat-bg2", "name": "BG Two", "spec_dir": "feat-bg2", "tier": 1},
            ]
        }))
        (bg_root / "docs" / "features" / "ROADMAP.md").write_text("# Roadmap\n")
        _bg_make_feature(bg_root, "feat-bg1")
        _bg_make_feature(bg_root, "feat-bg2")

        bg_state_dir = td_path / "budget-guard-state"
        bg_state_dir.mkdir(parents=True, exist_ok=True)
        _bg_prev_env = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = str(bg_state_dir)
        try:
            import time as _bg_time
            # Ceiling for C=20, Q=2: min(20*4//10=8, (20//2)*2=20)=8; max(6,8)=8.
            # Pin feat-bg1's per-feature count AT the ceiling (8) so it trips; leave
            # feat-bg2 below it so it dispatches.
            def _bg_write_marker(per_feature: dict, **extra) -> None:
                lazy_core.write_run_marker(
                    pipeline="feature", cloud=False, repo_root=str(bg_root),
                    max_cycles=20, now=_bg_time.time(),
                )
                mp = bg_state_dir / lazy_core._MARKER_FILENAME
                m = json.loads(mp.read_text(encoding="utf-8"))
                m["per_feature_forward_cycles"] = per_feature
                m.update(extra)
                mp.write_text(json.dumps(m) + "\n", encoding="utf-8")

            # (a) Trip/defer: feat-bg1 count >= ceiling → deferred, feat-bg2 dispatched.
            # NOTE (per-feature-cycle-cap-defers-incomplete-work P1): the guard is now
            # OFF by default. These trip/defer/evict/exhaustion fixtures characterize the
            # OPT-IN path, so they pass per_feature_cycle_cap=8 — the exact ceiling the
            # old default formula computed for C=20, Q=2 — to re-arm the same behavior.
            _bg_write_marker({"feat-bg1": 8, "feat-bg2": 0})
            st = compute_state(
                bg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            if st.get("feature_id") != "feat-bg2":
                failures.append(
                    "[budget-guard] trip/defer: expected feat-bg2 dispatched (feat-bg1 "
                    f"deferred past ceiling), got feature_id={st.get('feature_id')!r}"
                )
            bg = st.get("budget_guard")
            if not bg or bg.get("action") != "defer":
                failures.append(
                    "[budget-guard] trip/defer: expected budget_guard.action='defer', "
                    f"got {bg!r}"
                )
            elif bg.get("feature_id") != "feat-bg1" or bg.get("computed_ceiling") != 8 \
                    or bg.get("next_id") != "feat-bg2" or bg.get("count_at_trip") != 8:
                failures.append(
                    "[budget-guard] trip/defer: budget_guard metadata wrong "
                    f"(feature_id/computed_ceiling=8/next_id=feat-bg2/count_at_trip=8), "
                    f"got {bg!r}"
                )
            # queue.json must NOT have been rewritten (run-scoped reorder only).
            q_after = json.loads(
                (bg_root / "docs" / "features" / "queue.json").read_text()
            )
            if [e["id"] for e in q_after["queue"]] != ["feat-bg1", "feat-bg2"]:
                failures.append(
                    "[budget-guard] defer must be run-scoped — queue.json order was "
                    f"rewritten: {[e['id'] for e in q_after['queue']]!r}"
                )
            # The marker must record the deferral count for feat-bg1 (== 1).
            m_after = lazy_core.read_run_marker(now=_bg_time.time())
            if (m_after or {}).get("budget_deferred", {}).get("feat-bg1") != 1:
                failures.append(
                    "[budget-guard] defer must record budget_deferred[feat-bg1]=1, "
                    f"got {(m_after or {}).get('budget_deferred')!r}"
                )

            # (b) Bounded re-trip → eviction: marker already records 1 deferral for
            # feat-bg1 AND it trips again → action=evict (terminal, no infinite loop).
            _bg_write_marker(
                {"feat-bg1": 8, "feat-bg2": 0},
                budget_deferred={"feat-bg1": 1},
            )
            st2 = compute_state(
                bg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            bg2 = st2.get("budget_guard")
            if not bg2 or bg2.get("action") != "evict":
                failures.append(
                    "[budget-guard] re-trip: expected budget_guard.action='evict' on "
                    f"the 2nd trip of the same feature, got {bg2!r}"
                )
            if st2.get("feature_id") != "feat-bg2":
                failures.append(
                    "[budget-guard] re-trip: feat-bg2 must still dispatch after "
                    f"feat-bg1 is evicted, got {st2.get('feature_id')!r}"
                )
            m_after2 = lazy_core.read_run_marker(now=_bg_time.time())
            if "feat-bg1" not in (m_after2 or {}).get("budget_evicted", []):
                failures.append(
                    "[budget-guard] re-trip: feat-bg1 must be recorded in "
                    f"budget_evicted[], got {(m_after2 or {}).get('budget_evicted')!r}"
                )

            # (c) Override: --per-feature-cycle-cap forces a fixed ceiling. With a
            # cap of 100, feat-bg1's count of 8 is below it → no trip, feat-bg1
            # dispatches normally (no budget_guard).
            _bg_write_marker({"feat-bg1": 8, "feat-bg2": 0})
            st3 = compute_state(
                bg_root, cloud=False, real_device=True, per_feature_cycle_cap=100
            )
            if st3.get("feature_id") != "feat-bg1" or st3.get("budget_guard"):
                failures.append(
                    "[budget-guard] override: --per-feature-cycle-cap 100 must lift the "
                    f"ceiling so feat-bg1 dispatches untripped, got "
                    f"feature_id={st3.get('feature_id')!r} budget_guard={st3.get('budget_guard')!r}"
                )

            # (d) Exhaustion terminal: BOTH features over the ceiling AND already
            # deferred once → both evict → only budget-handled items remain → a
            # distinct exhaustion terminal, NOT all-features-complete.
            _bg_write_marker(
                {"feat-bg1": 8, "feat-bg2": 8},
                budget_deferred={"feat-bg1": 1, "feat-bg2": 1},
            )
            st4 = compute_state(
                bg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            if st4.get("terminal_reason") != "queue-exhausted-budget-deferred":
                failures.append(
                    "[budget-guard] exhaustion: expected terminal_reason="
                    "'queue-exhausted-budget-deferred' when only budget-deferred/"
                    f"evicted items remain, got {st4.get('terminal_reason')!r}"
                )

            # (e) Marker-gated no-op: with NO run marker, the guard never trips even
            # at a high count — default output byte-identical (no budget_guard key).
            (bg_state_dir / lazy_core._MARKER_FILENAME).unlink(missing_ok=True)
            st5 = compute_state(bg_root, cloud=False, real_device=True)
            if st5.get("feature_id") != "feat-bg1" or "budget_guard" in st5:
                failures.append(
                    "[budget-guard] marker-gated: with no marker the guard must be a "
                    f"no-op (feat-bg1 dispatched, no budget_guard key), got "
                    f"feature_id={st5.get('feature_id')!r} has_bg={'budget_guard' in st5}"
                )

            # (e2) BASELINE-REGRESSION byte-identity
            # (per-feature-cycle-cap-defers-incomplete-work P1, SPEC Open Q3):
            # a no-marker / no-flag default probe carries NONE of the budget-block
            # keys (the block is marker-gated AND now ceiling-gated). The default
            # probe dict shape is byte-identical to a pre-feature run. This is the
            # focused complement to the whole-suite byte-pinned baseline.
            _BG_BUDGET_KEYS = {
                "budget_guard", "budget_resumed_near_complete",
            }
            _bg_leaked = _BG_BUDGET_KEYS & set(st5.keys())
            if _bg_leaked:
                failures.append(
                    "[budget-guard] baseline-regression: the default (no-marker / "
                    "no-flag) probe must carry NO budget-block keys, leaked: "
                    f"{sorted(_bg_leaked)!r}"
                )

            # (f1) DEFAULT-OFF (per-feature-cycle-cap-defers-incomplete-work P1):
            # a LIVE marker + feat-bg1 over the OLD floor-6/ceiling-8, NO
            # --per-feature-cycle-cap flag → compute_per_feature_ceiling returns None
            # → the ceiling-gated budget block short-circuits → NO trip. feat-bg1
            # dispatches untripped, no budget_guard key, and is NOT appended to the
            # budget-deferred set. This is the core inversion: incomplete work is now
            # COMPLETED in-flight, not deferred.
            _bg_write_marker({"feat-bg1": 8, "feat-bg2": 0})
            st_off = compute_state(bg_root, cloud=False, real_device=True)
            if st_off.get("feature_id") != "feat-bg1" or "budget_guard" in st_off:
                failures.append(
                    "[budget-guard] default-off: with a live marker but NO "
                    "--per-feature-cycle-cap the guard must NOT arm (feat-bg1 "
                    "dispatched untripped, no budget_guard key), got "
                    f"feature_id={st_off.get('feature_id')!r} "
                    f"has_bg={'budget_guard' in st_off}"
                )
            m_off = lazy_core.read_run_marker(now=_bg_time.time())
            if (m_off or {}).get("budget_deferred", {}).get("feat-bg1"):
                failures.append(
                    "[budget-guard] default-off: the disabled guard must NOT record a "
                    f"deferral for feat-bg1, got {(m_off or {}).get('budget_deferred')!r}"
                )

            # (f2) OPT-IN-ARMS (per-feature-cycle-cap-defers-incomplete-work P1):
            # the SAME marker + the SAME feat-bg1 count WITH --per-feature-cycle-cap 8
            # (the opt-in) → the guard re-arms and trips (defer); budget_guard non-null.
            # This proves the opt-in path still drives the retained trip machinery.
            # (Case (a) above is this same characterization; (f2) makes the
            # default-off↔opt-in contrast explicit against one shared marker state.)
            _bg_write_marker({"feat-bg1": 8, "feat-bg2": 0})
            st_arm = compute_state(
                bg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            _bg_arm = st_arm.get("budget_guard")
            if not _bg_arm or _bg_arm.get("action") != "defer" \
                    or _bg_arm.get("feature_id") != "feat-bg1":
                failures.append(
                    "[budget-guard] opt-in-arms: --per-feature-cycle-cap 8 must re-arm "
                    "the guard so feat-bg1 trips (action='defer'), got "
                    f"budget_guard={_bg_arm!r}"
                )

            print("  [budget-guard] trip/defer + re-trip/evict + override + "
                  "exhaustion terminal + marker-gated no-op + default-off + "
                  "opt-in-arms: ok")
        finally:
            if _bg_prev_env is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = _bg_prev_env

        # -------------------------------------------------------------------
        # Functional check: budget-guard-defers-near-complete-feature Phase 2 —
        # near-completion grace gate + corrective-cycle discount at the trip
        # site. Reproduces the d2 incident: a feature at forward=ceiling whose
        # remaining work is verification-only (plan-Complete, no BLOCKED.md) is
        # DISPATCHED (one-shot grace) instead of deferred, and a feature whose
        # forward count is over the ceiling but whose corrective cycles discount
        # it back under the ceiling also dispatches.
        # -------------------------------------------------------------------
        def _ncg_make_near_complete(root: Path, fid: str) -> None:
            """A near-complete feature: verification-only unchecked PHASES rows +
            a plan part status: Complete + no BLOCKED.md."""
            fdir = root / "docs" / "features" / fid
            fdir.mkdir(parents=True, exist_ok=True)
            (fdir / "SPEC.md").write_text(
                "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
            )
            (fdir / "RESEARCH.md").write_text("# Research\n")
            (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n")
            (fdir / "PHASES.md").write_text(
                "# Phases\n\n### Phase 1\n- [x] Built the thing\n\n"
                "**Runtime Verification** <!-- verification-only -->\n"
                "- [ ] runtime check <!-- verification-only -->\n"
            )
            (fdir / "plans").mkdir(exist_ok=True)
            (fdir / "plans" / f"all-phases-{fid}.md").write_text(
                "---\nkind: implementation-plan\nstatus: Complete\n---\n\n# Plan\n"
            )

        ncg_root = td_path / "near-complete-grace"
        (ncg_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (ncg_root / "docs" / "features" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-nc", "name": "NC One", "spec_dir": "feat-nc", "tier": 1},
                {"id": "feat-nc2", "name": "NC Two", "spec_dir": "feat-nc2", "tier": 1},
            ]
        }))
        (ncg_root / "docs" / "features" / "ROADMAP.md").write_text("# Roadmap\n")
        _ncg_make_near_complete(ncg_root, "feat-nc")
        _bg_make_feature(ncg_root, "feat-nc2")

        ncg_state_dir = td_path / "near-complete-grace-state"
        ncg_state_dir.mkdir(parents=True, exist_ok=True)
        _ncg_prev_env = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = str(ncg_state_dir)
        try:
            import time as _ncg_time

            def _ncg_write_marker(per_feature: dict, **extra) -> None:
                lazy_core.write_run_marker(
                    pipeline="feature", cloud=False, repo_root=str(ncg_root),
                    max_cycles=20, now=_ncg_time.time(),
                )
                mp = ncg_state_dir / lazy_core._MARKER_FILENAME
                m = json.loads(mp.read_text(encoding="utf-8"))
                m["per_feature_forward_cycles"] = per_feature
                m.update(extra)
                mp.write_text(json.dumps(m) + "\n", encoding="utf-8")

            # Ceiling for C=20, Q=2: 8 (same as the bg fixture).
            # (f) Grace at the ceiling: feat-nc is AT the ceiling (8) AND
            # near-complete AND no prior budget defer → DISPATCHED (grace), NOT
            # deferred; budget_guard.action='grace', near_complete_grace_granted.
            # NOTE (per-feature-cycle-cap-defers-incomplete-work P1): guard now OFF
            # by default — these grace/discount/flush fixtures characterize the OPT-IN
            # path, so they pass per_feature_cycle_cap=8 (the ceiling the old default
            # formula produced for C=20, Q=2) to re-arm the same trip behavior.
            _ncg_write_marker({"feat-nc": 8, "feat-nc2": 0})
            stf = compute_state(
                ncg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            if stf.get("feature_id") != "feat-nc":
                failures.append(
                    "[ncg-grace] near-complete feat-nc at the ceiling must be "
                    f"DISPATCHED (grace), got feature_id={stf.get('feature_id')!r}"
                )
            bgf = stf.get("budget_guard")
            if not bgf or bgf.get("action") != "grace" or not bgf.get(
                "near_complete_grace_granted"
            ):
                failures.append(
                    "[ncg-grace] expected budget_guard.action='grace' + "
                    f"near_complete_grace_granted=True, got {bgf!r}"
                )
            elif bgf.get("effective_count") != 8 or bgf.get("corrective_count") != 0:
                failures.append(
                    "[ncg-grace] grace probe must carry effective_count=8 + "
                    f"corrective_count=0, got {bgf!r}"
                )
            # feat-nc must NOT be appended to the budget-deferred set.
            m_ncg = lazy_core.read_run_marker(now=_ncg_time.time())
            if (m_ncg or {}).get("budget_deferred", {}).get("feat-nc"):
                failures.append(
                    "[ncg-grace] grace must NOT record a budget deferral for "
                    f"feat-nc, got {(m_ncg or {}).get('budget_deferred')!r}"
                )

            # (g) One-shot grace: feat-nc near-complete but ALREADY deferred once
            # this run (budget_deferred[feat-nc]=1) → grace is spent → it trips
            # (evict, since prior_defers>=1) and feat-nc2 dispatches instead.
            _ncg_write_marker(
                {"feat-nc": 8, "feat-nc2": 0},
                budget_deferred={"feat-nc": 1},
            )
            stg = compute_state(
                ncg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            bgg = stg.get("budget_guard")
            if not bgg or bgg.get("near_complete_grace_granted") is not False:
                failures.append(
                    "[ncg-grace] one-shot: a near-complete feature that already "
                    "consumed grace must trip (near_complete_grace_granted=False), "
                    f"got {bgg!r}"
                )
            if stg.get("feature_id") != "feat-nc2":
                failures.append(
                    "[ncg-grace] one-shot: feat-nc2 must dispatch after feat-nc's "
                    f"grace is spent, got {stg.get('feature_id')!r}"
                )

            # (h) Corrective discount: feat-nc2 (NOT near-complete) at forward=9
            # (ceiling+1) but with corrective=2 → effective=9-2=7 < ceiling 8 →
            # dispatches (discount). Pin feat-nc at the ceiling with grace already
            # spent (budget_deferred=1) so it evicts and feat-nc2 is evaluated.
            _ncg_write_marker(
                {"feat-nc": 8, "feat-nc2": 9},
                budget_deferred={"feat-nc": 1},
                per_feature_corrective_cycles={"feat-nc2": 2},
            )
            sth = compute_state(
                ncg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            _sth_bg = sth.get("budget_guard") or {}
            if sth.get("feature_id") != "feat-nc2" or (
                _sth_bg.get("feature_id") == "feat-nc2"
            ):
                # feat-nc2 must DISPATCH (its own forward=9 would trip, but the
                # corrective discount pulls effective to 7 < 8). The only trip
                # surfaced is feat-nc's eviction (grace spent) — never feat-nc2.
                failures.append(
                    "[ncg-grace] corrective discount: feat-nc2 at forward=9 with "
                    "corrective=2 (effective=7 < ceiling 8) must dispatch untripped "
                    "(no feat-nc2 trip), got "
                    f"feature_id={sth.get('feature_id')!r} "
                    f"budget_guard={sth.get('budget_guard')!r}"
                )

            # (i) record_corrective_cycle wiring via --record-resolution-signal:
            # the corrective-dispatch bracket increments per_feature_corrective_cycles.
            _ncg_write_marker({"feat-nc2": 0})
            _rc_marker = lazy_core.record_resolution_signal(
                {"feature_id": "feat-nc2", "current_step": "Step 7a: execute plan"}
            )
            _rc_marker = lazy_core.record_corrective_cycle(_rc_marker, "feat-nc2")
            if _rc_marker.get("per_feature_corrective_cycles", {}).get("feat-nc2") != 1:
                failures.append(
                    "[ncg-grace] record_corrective_cycle must increment "
                    f"per_feature_corrective_cycles[feat-nc2] to 1, got {_rc_marker!r}"
                )
            print("  [ncg-grace] near-completion grace + one-shot bound + "
                  "corrective discount + corrective-cycle record: ok")

            # ---------------------------------------------------------------
            # budget-guard-defers-near-complete-feature Phase 3 — end-of-run
            # near-complete resume flush. When the queue exhausts to only
            # budget-deferred items, a deferred feature that is NOW near-complete
            # is auto-resumed (dispatched to validation) at the flush instead of
            # returning the queue-exhausted-budget-deferred terminal — and the
            # near-complete escalation never evicts (the flush rescues it). The
            # genuine all-parked terminal still fires when NO deferred feature is
            # near-complete; an evicted feature is NEVER resumed.
            # ---------------------------------------------------------------
            # (j) Resume flush: feat-nc is near-complete AND already budget-deferred
            # once this run (budget_deferred[feat-nc]=1), at the ceiling so it
            # re-trips. With Phase-3 the near-complete re-trip DEFERS (never evicts),
            # and because feat-nc2 is ALSO over the ceiling (deferred/evicted) the
            # queue exhausts → the flush resumes feat-nc (near-complete) to validation
            # instead of the terminal. budget_resumed_near_complete=feat-nc.
            _ncg_write_marker(
                {"feat-nc": 8, "feat-nc2": 8},
                budget_deferred={"feat-nc": 1, "feat-nc2": 1},
            )
            stj = compute_state(
                ncg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            if stj.get("feature_id") != "feat-nc":
                failures.append(
                    "[ncg-flush] a deferred-then-near-complete feature must be "
                    "auto-resumed at the end-of-run flush, got "
                    f"feature_id={stj.get('feature_id')!r} "
                    f"terminal_reason={stj.get('terminal_reason')!r}"
                )
            if stj.get("budget_resumed_near_complete") != "feat-nc":
                failures.append(
                    "[ncg-flush] the resume must surface "
                    "budget_resumed_near_complete='feat-nc', got "
                    f"{stj.get('budget_resumed_near_complete')!r}"
                )
            if stj.get("terminal_reason") == "queue-exhausted-budget-deferred":
                failures.append(
                    "[ncg-flush] the terminal must NOT fire when a deferred feature "
                    "is resumable at the flush"
                )

            # (k) Terminal unchanged for the genuine case: BOTH deferred features
            # are NOT near-complete (plain mid-implementation dirs) and over the
            # ceiling + grace spent → both evict → no resumable feature → the
            # queue-exhausted-budget-deferred terminal STILL fires.
            ncg_term_root = td_path / "ncg-terminal"
            (ncg_term_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
            (ncg_term_root / "docs" / "features" / "queue.json").write_text(json.dumps({
                "queue": [
                    {"id": "feat-t1", "name": "T One", "spec_dir": "feat-t1", "tier": 1},
                    {"id": "feat-t2", "name": "T Two", "spec_dir": "feat-t2", "tier": 1},
                ]
            }))
            (ncg_term_root / "docs" / "features" / "ROADMAP.md").write_text("# Roadmap\n")
            _bg_make_feature(ncg_term_root, "feat-t1")
            _bg_make_feature(ncg_term_root, "feat-t2")
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(ncg_term_root),
                max_cycles=20, now=_ncg_time.time(),
            )
            mtp = ncg_state_dir / lazy_core._MARKER_FILENAME
            mt = json.loads(mtp.read_text(encoding="utf-8"))
            mt["repo_root"] = str(ncg_term_root)
            mt["per_feature_forward_cycles"] = {"feat-t1": 8, "feat-t2": 8}
            mt["budget_deferred"] = {"feat-t1": 1, "feat-t2": 1}
            mtp.write_text(json.dumps(mt) + "\n", encoding="utf-8")
            stk = compute_state(
                ncg_term_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            if stk.get("terminal_reason") != "queue-exhausted-budget-deferred":
                failures.append(
                    "[ncg-flush] when NO deferred feature is near-complete the "
                    "queue-exhausted-budget-deferred terminal must STILL fire, got "
                    f"terminal_reason={stk.get('terminal_reason')!r} "
                    f"feature_id={stk.get('feature_id')!r}"
                )
            if "budget_resumed_near_complete" in stk:
                failures.append(
                    "[ncg-flush] no resume key when nothing is resumable, got "
                    f"{stk.get('budget_resumed_near_complete')!r}"
                )

            # (l) Evicted is never resumed: feat-nc is near-complete but ALREADY in
            # the marker's budget_evicted[] (genuine monopoly eviction earlier this
            # run); feat-nc2 is a non-near-complete deferred filler so the queue
            # exhausts. The flush must NOT resume the evicted feat-nc → the terminal
            # fires (no near-complete NON-evicted feature exists).
            _ncg_write_marker(
                {"feat-nc": 8, "feat-nc2": 8},
                budget_evicted=["feat-nc"],
                budget_deferred={"feat-nc2": 1},
            )
            # feat-nc2 must be a NON-near-complete deferred filler for this case.
            # Rebuild feat-nc2 as a plain mid-implementation dir (overwrite PHASES).
            (ncg_root / "docs" / "features" / "feat-nc2" / "PHASES.md").write_text(
                "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n"
            )
            stl = compute_state(
                ncg_root, cloud=False, real_device=True, per_feature_cycle_cap=8
            )
            if stl.get("feature_id") == "feat-nc" or (
                stl.get("budget_resumed_near_complete") == "feat-nc"
            ):
                failures.append(
                    "[ncg-flush] an EVICTED near-complete feature must NEVER be "
                    "resumed by the flush, got "
                    f"feature_id={stl.get('feature_id')!r} "
                    f"resumed={stl.get('budget_resumed_near_complete')!r}"
                )
            print("  [ncg-flush] end-of-run near-complete resume flush + "
                  "genuine-terminal-unchanged + evicted-never-resumed: ok")
        finally:
            if _ncg_prev_env is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = _ncg_prev_env

        # -------------------------------------------------------------------
        # Functional check: feature-budget-guard-and-skip-ahead Phase 3 —
        # dependency-aware skip-ahead past a gated head (default-on; two-key
        # readiness predicate; --strict-research-halt opt-out).
        #
        # Queue head feat-sa-head is research-gated (RESEARCH_PROMPT.md, no
        # RESEARCH.md/RESEARCH_SUMMARY.md → needs-research). The remaining
        # candidates exercise each readiness arm:
        #   feat-sa-indep — independent: true (SPEC frontmatter), no hard dep →
        #                   skip-ahead-READY (the one that should dispatch).
        #   feat-sa-unmarked — ready to plan, NO independent marker → NOT skipped
        #                   onto (degrades to strict halt for it).
        #   feat-sa-down — independent: true BUT a HARD dep on the gated head →
        #                   downstream → NOT skipped onto.
        # Skip-ahead is NOT marker-gated (it is default-on), so no run marker is
        # written here.
        # -------------------------------------------------------------------
        def _sa_make(root: Path, fid: str, *, spec: str, research: bool = True,
                     phases: bool = True) -> None:
            fdir = root / "docs" / "features" / fid
            fdir.mkdir(parents=True, exist_ok=True)
            (fdir / "SPEC.md").write_text(spec, encoding="utf-8")
            if research:
                (fdir / "RESEARCH.md").write_text("# R\n")
                (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
            if phases:
                (fdir / "PHASES.md").write_text(
                    "# Phases\n\n### Phase 1\n- [ ] Build\n"
                )
                (fdir / "plans").mkdir(exist_ok=True)
                (fdir / "plans" / f"all-phases-{fid}.md").write_text("# Plan\n")

        sa_root = td_path / "skip-ahead"
        (sa_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (sa_root / "docs" / "features" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sa-head", "name": "SA Head",
                 "spec_dir": "feat-sa-head", "tier": 1},
                {"id": "feat-sa-down", "name": "SA Down",
                 "spec_dir": "feat-sa-down", "tier": 2},
                {"id": "feat-sa-unmarked", "name": "SA Unmarked",
                 "spec_dir": "feat-sa-unmarked", "tier": 3},
                {"id": "feat-sa-indep", "name": "SA Indep",
                 "spec_dir": "feat-sa-indep", "tier": 4},
            ]
        }))
        (sa_root / "docs" / "features" / "ROADMAP.md").write_text("# Roadmap\n")
        # Gated head: research-pending (prompt only, no research) → needs-research.
        sa_head = sa_root / "docs" / "features" / "feat-sa-head"
        sa_head.mkdir(parents=True, exist_ok=True)
        (sa_head / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
        )
        (sa_head / "RESEARCH_PROMPT.md").write_text("# Prompt\n")
        # Downstream: marked independent BUT a HARD dep on the gated head.
        _sa_make(
            sa_root, "feat-sa-down",
            spec=(
                "---\nindependent: true\n---\n\n# Spec\n\n**Status:** Draft\n\n"
                "**Depends on:**\n- feat-sa-head — hard — needs the head's output\n"
            ),
        )
        # Unmarked: ready to plan, NO independent marker.
        _sa_make(
            sa_root, "feat-sa-unmarked",
            spec="# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
        )
        # Independent + dep-free → the skip-ahead-ready dispatch target.
        _sa_make(
            sa_root, "feat-sa-indep",
            spec=(
                "---\nindependent: true\n---\n\n# Spec\n\n**Status:** Draft\n\n"
                "**Depends on:** (none)\n"
            ),
        )

        # (a) Default (no --strict-research-halt): skip past the gated head and the
        #     downstream/unmarked candidates onto the independent one.
        sa_st = compute_state(sa_root, cloud=False, real_device=True)
        if sa_st.get("feature_id") != "feat-sa-indep":
            failures.append(
                "[skip-ahead] default: expected feat-sa-indep dispatched past the "
                f"gated head, got feature_id={sa_st.get('feature_id')!r} "
                f"(terminal={sa_st.get('terminal_reason')!r})"
            )
        if sa_st.get("gated_heads") != ["feat-sa-head"]:
            failures.append(
                "[skip-ahead] default: expected gated_heads=['feat-sa-head'] "
                f"surfaced, got {sa_st.get('gated_heads')!r}"
            )

        # (b) Unmarked NOT skipped onto / downstream NOT skipped onto: remove the
        #     independent candidate so ONLY the gated head + downstream + unmarked
        #     remain. No skip-ahead-ready item exists → fall back to the gated
        #     head's per-feature terminal (needs-research), NOT a dispatch of the
        #     unmarked or downstream item, NOT a false completion.
        import shutil as _sa_shutil
        _sa_shutil.rmtree(sa_root / "docs" / "features" / "feat-sa-indep")
        sa_q2 = json.loads(
            (sa_root / "docs" / "features" / "queue.json").read_text()
        )
        sa_q2["queue"] = [e for e in sa_q2["queue"] if e["id"] != "feat-sa-indep"]
        (sa_root / "docs" / "features" / "queue.json").write_text(json.dumps(sa_q2))
        sa_st2 = compute_state(sa_root, cloud=False, real_device=True)
        if sa_st2.get("terminal_reason") != "needs-research" \
                or sa_st2.get("feature_id") != "feat-sa-head":
            failures.append(
                "[skip-ahead] no-ready-alt: expected fallback to the gated head's "
                "needs-research terminal (unmarked + downstream NOT dispatched), got "
                f"terminal={sa_st2.get('terminal_reason')!r} "
                f"feature_id={sa_st2.get('feature_id')!r}"
            )
        # The unmarked/downstream items must NOT have been dispatched.
        if sa_st2.get("feature_id") in ("feat-sa-unmarked", "feat-sa-down"):
            failures.append(
                "[skip-ahead] no-ready-alt: an unmarked/downstream item was wrongly "
                f"dispatched: {sa_st2.get('feature_id')!r}"
            )

        # (c) --strict-research-halt restores the legacy halt-on-first-gated-head:
        #     even with the independent candidate present (restore it), the gated
        #     head halts the run (needs-research) and skip-ahead does NOT advance.
        _sa_make(
            sa_root, "feat-sa-indep",
            spec=(
                "---\nindependent: true\n---\n\n# Spec\n\n**Status:** Draft\n\n"
                "**Depends on:** (none)\n"
            ),
        )
        (sa_root / "docs" / "features" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sa-head", "name": "SA Head",
                 "spec_dir": "feat-sa-head", "tier": 1},
                {"id": "feat-sa-indep", "name": "SA Indep",
                 "spec_dir": "feat-sa-indep", "tier": 4},
            ]
        }))
        sa_st3 = compute_state(
            sa_root, cloud=False, real_device=True, strict_research_halt=True
        )
        if sa_st3.get("terminal_reason") != "needs-research" \
                or sa_st3.get("feature_id") != "feat-sa-head":
            failures.append(
                "[skip-ahead] --strict-research-halt: expected the legacy "
                "halt-on-first-gated-head (needs-research on feat-sa-head), got "
                f"terminal={sa_st3.get('terminal_reason')!r} "
                f"feature_id={sa_st3.get('feature_id')!r}"
            )
        if "gated_heads" in sa_st3:
            failures.append(
                "[skip-ahead] --strict-research-halt: gated_heads key must be absent "
                f"(skip-ahead disabled), got {sa_st3.get('gated_heads')!r}"
            )
        print("  [skip-ahead] default skip-onto-independent + unmarked/downstream "
              "NOT-skipped + --strict-research-halt legacy halt: ok")

        # (d) queue-dependency-dag Phase 3 (D7): skip-ahead key 1 evaluates
        #     the UNION of SPEC hard deps ∪ queue `deps` (queue ids treated as
        #     hard per D1's field semantics). _merged_skip_ahead_deps is the
        #     merge seam: queue ids append as hard deps tagged source=queue,
        #     deduped against the SPEC-parsed set (tagged source=spec).
        _sa_merged = _merged_skip_ahead_deps(
            [{"feature_id": "feat-sa-head", "kind": "hard", "reason": "r"}],
            ["feat-sa-other", "feat-sa-head"],
        )
        if [(d.get("feature_id"), d.get("kind"), d.get("source"))
                for d in _sa_merged] != [
            ("feat-sa-head", "hard", "spec"),
            ("feat-sa-other", "hard", "queue"),
        ]:
            failures.append(
                "[skip-ahead-union] merge seam: expected SPEC dep (source=spec) "
                "+ deduped queue dep (source=queue), got "
                f"{_sa_merged!r}"
            )
        if lazy_core.skip_ahead_ready(_sa_merged, {"feat-sa-other"}, True):
            failures.append(
                "[skip-ahead-union] a queue-sourced hard dep on a gated id must "
                "block skip-ahead readiness (key 1 union)"
            )

        # (e) End-to-end layering: a queue-deps-only downstream candidate
        #     (SPEC block '(none)', independent:true, queue deps on the gated
        #     head) is NOT dispatched past the gated head — the Phase-2
        #     dep-gate holds it first (dep_gated names it), and the union is
        #     the defense-in-depth second layer. The independent, dep-free
        #     alternative dispatches.
        _sa_make(
            sa_root, "feat-sa-qdep",
            spec=(
                "---\nindependent: true\n---\n\n# Spec\n\n**Status:** Draft\n\n"
                "**Depends on:** (none)\n"
            ),
        )
        (sa_root / "docs" / "features" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sa-head", "name": "SA Head",
                 "spec_dir": "feat-sa-head", "tier": 1},
                {"id": "feat-sa-qdep", "name": "SA QDep",
                 "spec_dir": "feat-sa-qdep", "tier": 2,
                 "deps": ["feat-sa-head"]},
                {"id": "feat-sa-indep", "name": "SA Indep",
                 "spec_dir": "feat-sa-indep", "tier": 4},
            ]
        }))
        sa_st4 = compute_state(sa_root, cloud=False, real_device=True)
        if sa_st4.get("feature_id") != "feat-sa-indep":
            failures.append(
                "[skip-ahead-union] queue-deps-only candidate: expected "
                "feat-sa-indep dispatched (feat-sa-qdep held/blocked), got "
                f"{sa_st4.get('feature_id')!r}"
            )
        if sa_st4.get("dep_gated") != [
            {"id": "feat-sa-qdep", "missing": ["feat-sa-head"]},
        ]:
            failures.append(
                "[skip-ahead-union] queue-deps-only candidate: expected the "
                "dep-gate hold to surface feat-sa-qdep, got "
                f"{sa_st4.get('dep_gated')!r}"
            )
        print("  [skip-ahead-union] SPEC∪queue merged key-1 deps + "
              "queue-deps-only candidate not dispatched: ok")

        # -------------------------------------------------------------------
        # Functional check: queue-dependency-dag Phase 2 — the queue `deps`
        # dep-gate. Covers: hold + advance (B(deps:[A]) held, A dispatched),
        # transitive hold (C→B→A, no traversal special-case), the gate running
        # regardless of --strict-research-halt (D2), completion unlock
        # (receipt-gated, D3), reorder-composes (D8), the unknown-dependency
        # fail-fast for dangling + Superseded deps (D4), and the all-gated
        # clean terminal.
        # -------------------------------------------------------------------
        def _dg_make(root: Path, fid: str, *, status: str = "Draft",
                     receipt: bool = False) -> Path:
            fdir = root / "docs" / "features" / fid
            fdir.mkdir(parents=True, exist_ok=True)
            (fdir / "SPEC.md").write_text(
                f"# {fid}\n\n**Status:** {status}\n\n**Depends on:** (none)\n",
                encoding="utf-8",
            )
            if receipt:
                (fdir / "COMPLETED.md").write_text(
                    f"---\nkind: completed\nfeature_id: {fid}\n"
                    "provenance: mark-complete\n---\n\n# Completed\n",
                    encoding="utf-8",
                )
            if status not in ("Complete", "Superseded"):
                (fdir / "RESEARCH.md").write_text("# R\n")
                (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
                (fdir / "PHASES.md").write_text(
                    "# Phases\n\n### Phase 1\n- [ ] Build\n"
                )
                (fdir / "plans").mkdir(exist_ok=True)
                (fdir / "plans" / f"all-phases-{fid}.md").write_text("# Plan\n")
            return fdir

        dg_root = td_path / "dep-gate"
        dg_feats = dg_root / "docs" / "features"
        dg_feats.mkdir(parents=True, exist_ok=True)
        (dg_feats / "ROADMAP.md").write_text("# Roadmap\n")
        (dg_feats / "queue.json").write_text(json.dumps({"queue": [
            {"id": "feat-dg-c", "name": "DG C", "spec_dir": "feat-dg-c",
             "tier": 1, "deps": ["feat-dg-b"]},
            {"id": "feat-dg-b", "name": "DG B", "spec_dir": "feat-dg-b",
             "tier": 2, "deps": ["feat-dg-a"]},
            {"id": "feat-dg-a", "name": "DG A", "spec_dir": "feat-dg-a",
             "tier": 3},
        ]}))
        for _dg_fid in ("feat-dg-a", "feat-dg-b", "feat-dg-c"):
            _dg_make(dg_root, _dg_fid)

        # (a) Hold + advance + transitive: C held on B, B held on A (both
        #     incomplete-because-queued), A dispatched. dep_gated surfaces the
        #     holds in walk order with their missing dep ids.
        dg_st = compute_state(dg_root, cloud=False, real_device=True)
        if dg_st.get("feature_id") != "feat-dg-a":
            failures.append(
                "[dep-gate] hold+advance: expected feat-dg-a dispatched past the "
                f"held dependents, got {dg_st.get('feature_id')!r} "
                f"(terminal={dg_st.get('terminal_reason')!r})"
            )
        if dg_st.get("dep_gated") != [
            {"id": "feat-dg-c", "missing": ["feat-dg-b"]},
            {"id": "feat-dg-b", "missing": ["feat-dg-a"]},
        ]:
            failures.append(
                "[dep-gate] hold+advance: expected dep_gated to name C(missing B) "
                f"then B(missing A); got {dg_st.get('dep_gated')!r}"
            )

        # (b) The dep-gate is a correctness gate, NOT a throughput
        #     optimization: it runs identically under --strict-research-halt.
        dg_st2 = compute_state(
            dg_root, cloud=False, real_device=True, strict_research_halt=True
        )
        if dg_st2.get("feature_id") != "feat-dg-a" or not dg_st2.get("dep_gated"):
            failures.append(
                "[dep-gate] strict-flag independence: expected the same hold "
                f"under --strict-research-halt, got "
                f"feature_id={dg_st2.get('feature_id')!r} "
                f"dep_gated={dg_st2.get('dep_gated')!r}"
            )

        # (c) Completion unlock (D3 receipt-gated): flip A to Complete + a
        #     valid COMPLETED.md receipt → next probe dispatches B normally;
        #     C stays held on the still-queued B.
        (dg_root / "docs" / "features" / "feat-dg-a" / "SPEC.md").write_text(
            "# feat-dg-a\n\n**Status:** Complete\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (dg_root / "docs" / "features" / "feat-dg-a" / "COMPLETED.md").write_text(
            "---\nkind: completed\nfeature_id: feat-dg-a\n"
            "provenance: mark-complete\n---\n\n# Completed\n",
            encoding="utf-8",
        )
        dg_st3 = compute_state(dg_root, cloud=False, real_device=True)
        if dg_st3.get("feature_id") != "feat-dg-b":
            failures.append(
                "[dep-gate] completion unlock: expected feat-dg-b dispatched once "
                f"its dep gained Complete + receipt, got "
                f"{dg_st3.get('feature_id')!r}"
            )
        if dg_st3.get("dep_gated") != [
            {"id": "feat-dg-c", "missing": ["feat-dg-b"]},
        ]:
            failures.append(
                "[dep-gate] completion unlock: expected only C still held, got "
                f"{dg_st3.get('dep_gated')!r}"
            )

        # (d) Reorder composes (D8): queue order is pure preference, the DAG is
        #     pure constraint — moving the dependent to head is storable and the
        #     next probe simply holds it again.
        lazy_core.reorder_queue(
            dg_feats / "queue.json", "feat-dg-b", to="head",
            queue_label="queue.json",
        )
        dg_st4 = compute_state(dg_root, cloud=False, real_device=True)
        if dg_st4.get("feature_id") != "feat-dg-b":
            failures.append(
                "[dep-gate] reorder composes: expected feat-dg-b (dep already "
                f"complete) after reorder-to-head, got {dg_st4.get('feature_id')!r}"
            )
        lazy_core.reorder_queue(
            dg_feats / "queue.json", "feat-dg-c", to="head",
            queue_label="queue.json",
        )
        dg_st5 = compute_state(dg_root, cloud=False, real_device=True)
        if dg_st5.get("feature_id") != "feat-dg-b" or dg_st5.get("dep_gated") != [
            {"id": "feat-dg-c", "missing": ["feat-dg-b"]},
        ]:
            failures.append(
                "[dep-gate] reorder composes: dependent-at-head must be held, dep "
                f"worked first; got feature_id={dg_st5.get('feature_id')!r} "
                f"dep_gated={dg_st5.get('dep_gated')!r}"
            )
        print("  [dep-gate] hold+advance + transitive + strict-flag independence "
              "+ completion unlock + reorder composes: ok")

        # (e) Unknown-dependency fail-fast (D4): a DANGLING dep id (resolves
        #     nowhere) writes canonical BLOCKED.md (blocker_kind:
        #     unknown-dependency) on the DEPENDENT and halts blocked.
        dgu_root = td_path / "dep-gate-unknown"
        dgu_feats = dgu_root / "docs" / "features"
        dgu_feats.mkdir(parents=True, exist_ok=True)
        (dgu_feats / "ROADMAP.md").write_text("# Roadmap\n")
        (dgu_feats / "queue.json").write_text(json.dumps({"queue": [
            {"id": "feat-dg-d", "name": "DG D", "spec_dir": "feat-dg-d",
             "tier": 1, "deps": ["feat-dg-ghost"]},
        ]}))
        _dg_make(dgu_root, "feat-dg-d")
        dgu_st = compute_state(dgu_root, cloud=False, real_device=True)
        dgu_blocked = dgu_feats / "feat-dg-d" / "BLOCKED.md"
        if dgu_st.get("terminal_reason") != "blocked" \
                or dgu_st.get("feature_id") != "feat-dg-d":
            failures.append(
                "[dep-gate] dangling dep: expected blocked halt on feat-dg-d, got "
                f"terminal={dgu_st.get('terminal_reason')!r} "
                f"feature_id={dgu_st.get('feature_id')!r}"
            )
        if not dgu_blocked.exists():
            failures.append("[dep-gate] dangling dep: BLOCKED.md was not written")
        else:
            dgu_meta = parse_sentinel(dgu_blocked) or {}
            if dgu_meta.get("blocker_kind") != "unknown-dependency":
                failures.append(
                    "[dep-gate] dangling dep: expected blocker_kind "
                    f"unknown-dependency, got {dgu_meta.get('blocker_kind')!r}"
                )
            if "feat-dg-ghost" not in dgu_blocked.read_text(encoding="utf-8"):
                failures.append(
                    "[dep-gate] dangling dep: BLOCKED.md body must name the "
                    "offending dep id"
                )

        # (f) Superseded dep → the same unknown-dependency fail-fast (the work
        #     never happened; silently holding would starve the dependent).
        dgs_root = td_path / "dep-gate-superseded"
        dgs_feats = dgs_root / "docs" / "features"
        dgs_feats.mkdir(parents=True, exist_ok=True)
        (dgs_feats / "ROADMAP.md").write_text("# Roadmap\n")
        (dgs_feats / "queue.json").write_text(json.dumps({"queue": [
            {"id": "feat-dg-e", "name": "DG E", "spec_dir": "feat-dg-e",
             "tier": 1, "deps": ["feat-dg-old"]},
        ]}))
        _dg_make(dgs_root, "feat-dg-e")
        _dg_make(dgs_root, "feat-dg-old", status="Superseded")
        dgs_st = compute_state(dgs_root, cloud=False, real_device=True)
        if dgs_st.get("terminal_reason") != "blocked" \
                or not (dgs_feats / "feat-dg-e" / "BLOCKED.md").exists():
            failures.append(
                "[dep-gate] superseded dep: expected unknown-dependency blocked "
                f"halt on feat-dg-e, got terminal={dgs_st.get('terminal_reason')!r}"
            )
        print("  [dep-gate] dangling + superseded dep unknown-dependency "
              "fail-fast: ok")

        # (g) All-gated clean terminal: the only queued item is dep-gated on an
        #     incomplete unqueued on-disk dir → queue-exhausted-dependency-gated
        #     (an honest distinct terminal, never all-features-complete), flush
        #     naming the held item.
        dgt_root = td_path / "dep-gate-terminal"
        dgt_feats = dgt_root / "docs" / "features"
        dgt_feats.mkdir(parents=True, exist_ok=True)
        (dgt_feats / "ROADMAP.md").write_text("# Roadmap\n")
        (dgt_feats / "queue.json").write_text(json.dumps({"queue": [
            {"id": "feat-dg-h", "name": "DG H", "spec_dir": "feat-dg-h",
             "tier": 1, "deps": ["feat-dg-open"]},
        ]}))
        _dg_make(dgt_root, "feat-dg-h")
        _dg_make(dgt_root, "feat-dg-open")  # on-disk, incomplete, NOT queued
        dgt_st = compute_state(dgt_root, cloud=False, real_device=True)
        if dgt_st.get("terminal_reason") != "queue-exhausted-dependency-gated":
            failures.append(
                "[dep-gate] all-gated terminal: expected "
                "queue-exhausted-dependency-gated, got "
                f"{dgt_st.get('terminal_reason')!r}"
            )
        if dgt_st.get("dep_gated") != [
            {"id": "feat-dg-h", "missing": ["feat-dg-open"]},
        ]:
            failures.append(
                "[dep-gate] all-gated terminal: expected the flush to name the "
                f"held item + missing dep, got {dgt_st.get('dep_gated')!r}"
            )
        if "feat-dg-h" not in (dgt_st.get("notify_message") or ""):
            failures.append(
                "[dep-gate] all-gated terminal: notify_message must name the "
                f"held item, got {dgt_st.get('notify_message')!r}"
            )
        print("  [dep-gate] all-gated queue-exhausted-dependency-gated "
              "terminal: ok")

        # -------------------------------------------------------------------
        # Functional check: queue-dependency-dag Phase 4 — the feeder + drift.
        # (h) probe-time drift diagnostic: an entry CARRYING a `deps` key whose
        #     set diverges from the SPEC's parsed hard-dep set emits a
        #     lint-grade dep-drift warning (never a halt; the item still
        #     routes). Entries without the key emit nothing (byte-identity —
        #     pinned by every pre-existing fixture + the baselines).
        # -------------------------------------------------------------------
        dgr_root = td_path / "dep-drift"
        dgr_feats = dgr_root / "docs" / "features"
        dgr_feats.mkdir(parents=True, exist_ok=True)
        (dgr_feats / "ROADMAP.md").write_text("# Roadmap\n")
        (dgr_feats / "queue.json").write_text(json.dumps({"queue": [
            {"id": "feat-dg-drift", "name": "DG Drift",
             "spec_dir": "feat-dg-drift", "tier": 1, "deps": []},
        ]}))
        dgr_dir = _dg_make(dgr_root, "feat-dg-drift")
        # SPEC declares one hard dep the queue field does not carry.
        (dgr_dir / "SPEC.md").write_text(
            "# feat-dg-drift\n\n**Status:** Draft\n\n"
            "**Depends on:**\n- feat-dg-drift-up — hard — upstream contract\n",
            encoding="utf-8",
        )
        dgr_st = compute_state(dgr_root, cloud=False, real_device=True)
        if dgr_st.get("feature_id") != "feat-dg-drift":
            failures.append(
                "[dep-drift] expected the drifted entry to still route "
                f"normally (lint-grade), got {dgr_st.get('feature_id')!r} "
                f"terminal={dgr_st.get('terminal_reason')!r}"
            )
        if not any("dep-drift" in d for d in dgr_st.get("diagnostics", [])):
            failures.append(
                "[dep-drift] expected a dep-drift diagnostic naming the "
                f"diverged sets; got {dgr_st.get('diagnostics')!r}"
            )
        print("  [dep-drift] queue-vs-SPEC hard-dep drift diagnostic "
              "(lint-grade, no halt): ok")

        # -------------------------------------------------------------------
        # (i) enqueue_adhoc --deps: an ad-hoc item can declare deps at enqueue
        #     time (validated: reserved bug:/feature: prefixes refused).
        # -------------------------------------------------------------------
        enqd_root = td_path / "enqueue-deps-test"
        enqd_feats = enqd_root / "docs" / "features"
        enqd_feats.mkdir(parents=True, exist_ok=True)
        (enqd_feats / "queue.json").write_text(json.dumps({"queue": []}))
        (enqd_feats / "ROADMAP.md").write_text("# Roadmap\n")
        enqd_res = enqueue_adhoc(
            enqd_root, "adhoc-dep", "Adhoc Dep", "do it",
            deps=["feat-dg-up"],
        )
        enqd_queue = json.loads((enqd_feats / "queue.json").read_text())
        if not enqd_res.get("enqueued") \
                or enqd_queue["queue"][0].get("deps") != ["feat-dg-up"]:
            failures.append(
                "[enqueue-deps] expected the prepended entry to carry "
                f"deps=['feat-dg-up']; got {enqd_queue['queue'][0]!r}"
            )
        try:
            enqueue_adhoc(
                enqd_root, "adhoc-dep-bad", "Bad", "x", deps=["bug:some-bug"],
            )
            failures.append(
                "[enqueue-deps] a reserved bug:/feature: prefixed dep id must "
                "be refused (_die), but was accepted"
            )
        except SystemExit:
            pass
        print("  [enqueue-deps] --deps stored on the ad-hoc entry + reserved "
              "prefix refused: ok")

        # -------------------------------------------------------------------
        # (j) --sync-deps CLI (subprocess, real handler): projects the SPEC's
        #     hard deps into the queue entry (script-owned, atomic), noop:true
        #     + byte-identical on re-run, and REFUSED exit 3 with zero side
        #     effects for a cycle subagent (refuse_if_cycle_active FIRST — the
        #     --reorder-queue/--enqueue-adhoc contract).
        # -------------------------------------------------------------------
        sd_root = td_path / "sync-deps-test"
        sd_feats = sd_root / "docs" / "features"
        sd_feats.mkdir(parents=True, exist_ok=True)
        (sd_feats / "ROADMAP.md").write_text("# Roadmap\n")
        (sd_feats / "queue.json").write_text(json.dumps({"queue": [
            {"id": "feat-sd", "name": "SD", "spec_dir": "feat-sd", "tier": 1},
            {"id": "feat-sd-up", "name": "SD Up", "spec_dir": "feat-sd-up",
             "tier": 2},
        ]}, indent=2) + "\n")
        sd_dir = _dg_make(sd_root, "feat-sd")
        (sd_dir / "SPEC.md").write_text(
            "# feat-sd\n\n**Status:** Draft\n\n"
            "**Depends on:**\n- feat-sd-up — hard — upstream contract\n"
            "- feat-sd-soft — soft — optional\n",
            encoding="utf-8",
        )
        _dg_make(sd_root, "feat-sd-up")
        _sd_script = str(Path(__file__).resolve())
        _sd_state = td_path / "sd-state"
        _sd_state.mkdir(parents=True, exist_ok=True)

        def _sd_env(**extra: str) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(_sd_state)
            e.update(extra)
            return e

        # Cycle-subagent refusal FIRST (zero side effects proven below).
        sd_before = (sd_feats / "queue.json").read_bytes()
        r_sd_refuse = subprocess.run(
            [sys.executable, _sd_script, "--sync-deps", "--id", "feat-sd",
             "--repo-root", str(sd_root)],
            capture_output=True, text=True,
            env=_sd_env(LAZY_CYCLE_SUBAGENT="1"),
        )
        if r_sd_refuse.returncode != 3 \
                or (sd_feats / "queue.json").read_bytes() != sd_before:
            failures.append(
                "[sync-deps] cycle-subagent refusal: expected exit 3 with zero "
                f"side effects, got rc={r_sd_refuse.returncode} "
                f"mutated={(sd_feats / 'queue.json').read_bytes() != sd_before}"
            )
        # Orchestrator-side write.
        r_sd = subprocess.run(
            [sys.executable, _sd_script, "--sync-deps", "--id", "feat-sd",
             "--repo-root", str(sd_root)],
            capture_output=True, text=True,
            env=_sd_env(LAZY_ORCHESTRATOR="1"),
        )
        sd_queue = json.loads((sd_feats / "queue.json").read_text())
        if r_sd.returncode != 0 \
                or sd_queue["queue"][0].get("deps") != ["feat-sd-up"]:
            failures.append(
                "[sync-deps] write: expected exit 0 + deps=['feat-sd-up'] "
                f"(hard only), got rc={r_sd.returncode} "
                f"entry={sd_queue['queue'][0]!r} stderr={r_sd.stderr[:200]!r}"
            )
        # Idempotent re-run: noop true, file byte-identical.
        sd_after_first = (sd_feats / "queue.json").read_bytes()
        r_sd2 = subprocess.run(
            [sys.executable, _sd_script, "--sync-deps", "--id", "feat-sd",
             "--repo-root", str(sd_root)],
            capture_output=True, text=True,
            env=_sd_env(LAZY_ORCHESTRATOR="1"),
        )
        try:
            sd_out2 = json.loads(r_sd2.stdout)
        except json.JSONDecodeError:
            sd_out2 = {}
        if r_sd2.returncode != 0 or sd_out2.get("noop") is not True \
                or (sd_feats / "queue.json").read_bytes() != sd_after_first:
            failures.append(
                "[sync-deps] idempotent re-run: expected noop:true + "
                f"byte-identical file, got rc={r_sd2.returncode} "
                f"out={sd_out2!r}"
            )
        print("  [sync-deps] cycle-subagent exit-3 refusal + hard-only "
              "projection + idempotent noop: ok")

        # -------------------------------------------------------------------
        # byref-updatedinput-unapplied-on-background-agent-dispatch WU-2:
        # --resolve-ref <nonce> — the sanctioned consumed-nonce read a subagent
        # runs to recover its full instructions after the platform drops the
        # by-reference updatedInput rewrite (upstream #39814). Exercises the REAL
        # CLI end-to-end: hit → exact registered bytes on stdout + exit 0; miss →
        # empty stdout + exit 1; and — since a dispatched subagent MUST run it —
        # the hit path is NOT cycle-refused even under LAZY_CYCLE_SUBAGENT=1.
        # -------------------------------------------------------------------
        rref_name = "resolve-ref-cli"
        rref_ok = True
        rref_state = td_path / "rref-state"
        rref_state.mkdir(parents=True, exist_ok=True)
        rref_root = td_path / "rref-repo"
        rref_root.mkdir(parents=True, exist_ok=True)
        rref_prompt = "Execute plan part 2 for feat-rref — full resolved bytes."
        _rref_prev = os.environ.get("LAZY_STATE_DIR")
        os.environ["LAZY_STATE_DIR"] = str(rref_state)
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False,
                                       repo_root=str(rref_root))
            _rref_entry = lazy_core.register_emission(rref_prompt, cls="cycle",
                                                      item_id="feat-rref")
            rref_nonce = _rref_entry["nonce"]
            lazy_core.dispatch.consume_nonce(rref_nonce, consumer="toolu_rref")
        finally:
            if _rref_prev is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = _rref_prev

        def _rref_env(**extra: str) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(rref_state)
            e.update(extra)
            return e

        _rref_script = str(Path(__file__).resolve())
        # Hit under a subagent context — must NOT be cycle-refused; prints the
        # exact registered bytes + exit 0.
        r_rref_hit = subprocess.run(
            [sys.executable, _rref_script, "--resolve-ref", rref_nonce,
             "--repo-root", str(rref_root)],
            capture_output=True, text=True, env=_rref_env(LAZY_CYCLE_SUBAGENT="1"),
        )
        if r_rref_hit.returncode != 0 \
                or r_rref_hit.stdout.rstrip("\n") != rref_prompt:
            failures.append(
                f"[{rref_name}] hit: expected exit 0 + exact bytes (subagent NOT "
                f"cycle-refused), got rc={r_rref_hit.returncode} "
                f"stdout={r_rref_hit.stdout!r} stderr={r_rref_hit.stderr[:200]!r}"
            )
            rref_ok = False
        # Miss: an unknown nonce prints nothing + exits 1.
        r_rref_miss = subprocess.run(
            [sys.executable, _rref_script, "--resolve-ref", "deadbeef" * 4,
             "--repo-root", str(rref_root)],
            capture_output=True, text=True, env=_rref_env(),
        )
        if r_rref_miss.returncode != 1 or r_rref_miss.stdout.strip() != "":
            failures.append(
                f"[{rref_name}] miss: expected exit 1 + empty stdout, got "
                f"rc={r_rref_miss.returncode} stdout={r_rref_miss.stdout!r}"
            )
            rref_ok = False
        print(f"  {'PASS' if rref_ok else 'FAIL'} [{rref_name}]")

        # Functional check: enqueue_adhoc prepends the queue, seeds the brief,
        # creates the spec dir, and adds a ROADMAP row.
        enq_features = td_path / "enqueue-test" / "docs" / "features"
        enq_features.mkdir(parents=True, exist_ok=True)
        (enq_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-z", "name": "Z", "spec_dir": "feat-z", "tier": 1}
            ]
        }))
        (enq_features / "ROADMAP.md").write_text("# Roadmap\n")
        enq_root = td_path / "enqueue-test"
        res = enqueue_adhoc(enq_root, "adhoc-test", "Adhoc Test", "Fix the thing")
        enq_queue = json.loads((enq_features / "queue.json").read_text())
        if not res.get("enqueued"):
            failures.append("[enqueue] enqueue_adhoc did not report enqueued=True")
        if enq_queue["queue"][0].get("id") != "adhoc-test":
            failures.append(
                f"[enqueue] expected adhoc-test at queue[0]; got "
                f"{enq_queue['queue'][0].get('id')!r}"
            )
        if enq_queue["queue"][0].get("adhoc") is not True:
            failures.append("[enqueue] queue[0] missing adhoc: true")
        if len(enq_queue["queue"]) != 2:
            failures.append(
                f"[enqueue] expected 2 queue entries; got {len(enq_queue['queue'])}"
            )
        brief = enq_features / "adhoc-test" / "ADHOC_BRIEF.md"
        if not brief.exists():
            failures.append("[enqueue] ADHOC_BRIEF.md was not written")
        elif "Fix the thing" not in brief.read_text():
            failures.append("[enqueue] ADHOC_BRIEF.md missing the brief text")
        roadmap_text = (enq_features / "ROADMAP.md").read_text()
        if "Adhoc Test" not in roadmap_text:
            failures.append("[enqueue] ROADMAP.md missing the ad-hoc row")
        # Duplicate id must be refused (enqueue_adhoc calls _die → SystemExit).
        try:
            enqueue_adhoc(enq_root, "adhoc-test", "Dup", "x")
            failures.append("[enqueue] duplicate feature_id was not refused")
        except SystemExit:
            pass
        print("  [enqueue] enqueue_adhoc prepend + brief + roadmap: ok")

        # Functional check (toolify-auto-promotion Phase 2, D4-B): additive
        # --stub / --at {head,tail} flags on enqueue_adhoc, byte-identical
        # defaults. Feature-pipeline-only (bug pipeline has no stub step —
        # justified divergence, no bug-state.py mirror).
        enqf_root = td_path / "enqueue-flags-test"
        enqf_features = enqf_root / "docs" / "features"
        enqf_features.mkdir(parents=True, exist_ok=True)
        (enqf_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-y", "name": "Y", "spec_dir": "feat-y", "tier": 1}
            ]
        }))
        (enqf_features / "ROADMAP.md").write_text("# Roadmap\n")
        # (a) Default path byte-identity: head insert, NO "stub" key, the exact
        # pre-change key-set on the entry.
        res_def = enqueue_adhoc(enqf_root, "adhoc-default", "Adhoc Default", "x")
        enqf_q1 = json.loads((enqf_features / "queue.json").read_text())
        if enqf_q1["queue"][0].get("id") != "adhoc-default":
            failures.append("[enqueue-flags] default: expected head insert")
        if "stub" in enqf_q1["queue"][0]:
            failures.append("[enqueue-flags] default: entry must NOT carry a stub key")
        if set(enqf_q1["queue"][0].keys()) != {"id", "name", "spec_dir", "tier", "adhoc"}:
            failures.append(
                f"[enqueue-flags] default entry key-set drifted: "
                f"{sorted(enqf_q1['queue'][0].keys())}"
            )
        if res_def.get("queue_position") != 0:
            failures.append("[enqueue-flags] default: queue_position must be 0")
        # (b) stub=True + at='tail' + tier=2: appended AFTER existing entries,
        # honest queue_position, `"stub": true` on the entry.
        res_tail = enqueue_adhoc(
            enqf_root, "adhoc-stub-tail", "Adhoc Stub Tail", "y",
            tier=2, stub=True, at="tail",
        )
        enqf_q2 = json.loads((enqf_features / "queue.json").read_text())
        enqf_last = enqf_q2["queue"][-1]
        if enqf_last.get("id") != "adhoc-stub-tail":
            failures.append("[enqueue-flags] at=tail: entry must land at the queue tail")
        if enqf_last.get("stub") is not True:
            failures.append("[enqueue-flags] stub=True: entry missing stub: true")
        if enqf_last.get("tier") != 2:
            failures.append("[enqueue-flags] tier=2 did not thread")
        if res_tail.get("queue_position") != len(enqf_q2["queue"]) - 1:
            failures.append(
                f"[enqueue-flags] at=tail: queue_position must be the tail index; "
                f"got {res_tail.get('queue_position')!r}"
            )
        if enqf_q2["queue"][0].get("id") != "adhoc-default":
            failures.append("[enqueue-flags] at=tail: head entry must be undisturbed")
        # (c) CLI threading: --stub --at tail --tier 2 land on the entry.
        enqf_cli_root = td_path / "enqueue-flags-cli-test"
        (enqf_cli_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        enqf_env = {**os.environ, "LAZY_ORCHESTRATOR": "1"}
        sys.stdout.flush()
        sys.stderr.flush()
        enqf_cli = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--enqueue-adhoc", "--id", "adhoc-cli-stub", "--name", "Adhoc CLI Stub",
             "--tier", "2", "--stub", "--at", "tail",
             "--repo-root", str(enqf_cli_root)],
            capture_output=True, text=True, env=enqf_env,
        )
        if enqf_cli.returncode != 0:
            failures.append(
                f"[enqueue-flags] CLI --stub --at tail failed: {enqf_cli.stderr.strip()!r}"
            )
        else:
            enqf_q3 = json.loads(
                (enqf_cli_root / "docs" / "features" / "queue.json").read_text()
            )
            enqf_cli_entry = enqf_q3["queue"][-1]
            if (enqf_cli_entry.get("id") != "adhoc-cli-stub"
                    or enqf_cli_entry.get("stub") is not True
                    or enqf_cli_entry.get("tier") != 2):
                failures.append(
                    f"[enqueue-flags] CLI flags did not thread: {enqf_cli_entry!r}"
                )
        # (d) Feature-only flags: --stub with --type bug is refused loudly
        # (exit 2) BEFORE any queue write — never silently ignored.
        enqf_bug = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--enqueue-adhoc", "--type", "bug", "--stub",
             "--id", "adhoc-bug-stub", "--name", "X",
             "--repo-root", str(enqf_cli_root)],
            capture_output=True, text=True, env=enqf_env,
        )
        if enqf_bug.returncode != 2:
            failures.append(
                f"[enqueue-flags] --type bug --stub must be refused (exit 2); "
                f"got exit {enqf_bug.returncode}"
            )
        if (enqf_cli_root / "docs" / "bugs" / "queue.json").exists():
            failures.append(
                "[enqueue-flags] --type bug --stub refusal must not write docs/bugs/queue.json"
            )
        print("  [enqueue-flags] default byte-identical + stub/tail/tier + bug-type refusal: ok")

        # Functional check (unified-pipeline-orchestrator P3 WU-1):
        # enqueue_adhoc_bug routes an ad-hoc item into docs/bugs/queue.json via
        # the existing bug-state.py enqueue, seeds docs/bugs/<slug>/, and is
        # idempotent on a duplicate id (no raise, no second entry).
        enqb_root = td_path / "enqueue-bug-test"
        enqb_root.mkdir(parents=True, exist_ok=True)
        resb = enqueue_adhoc_bug(
            enqb_root, "adhoc-bug-1", "Adhoc Bug 1", "Fix the bug thing"
        )
        enqb_bugs = enqb_root / "docs" / "bugs"
        enqb_queue_path = enqb_bugs / "queue.json"
        if not enqb_queue_path.exists():
            failures.append("[enqueue-bug] docs/bugs/queue.json was not written")
        else:
            enqb_queue = json.loads(enqb_queue_path.read_text())
            if enqb_queue["queue"][0].get("id") != "adhoc-bug-1":
                failures.append(
                    f"[enqueue-bug] expected adhoc-bug-1 at queue[0]; got "
                    f"{enqb_queue['queue'][0].get('id')!r}"
                )
            if enqb_queue["queue"][0].get("spec_dir") != "adhoc-bug-1":
                failures.append(
                    "[enqueue-bug] queue[0] missing spec_dir-keyed entry"
                )
        if not resb.get("enqueued"):
            failures.append("[enqueue-bug] enqueue_adhoc_bug did not report enqueued=True")
        enqb_brief = enqb_bugs / "adhoc-bug-1" / "ADHOC_BRIEF.md"
        if not enqb_brief.exists():
            failures.append("[enqueue-bug] docs/bugs/<slug>/ADHOC_BRIEF.md not seeded")
        elif "Fix the bug thing" not in enqb_brief.read_text():
            failures.append("[enqueue-bug] ADHOC_BRIEF.md missing the brief text")
        # Idempotent: a second call with the same id is a no-op (no raise, queue unchanged).
        try:
            enqueue_adhoc_bug(enqb_root, "adhoc-bug-1", "Dup Bug", "x")
        except SystemExit:
            failures.append("[enqueue-bug] duplicate id raised instead of no-op")
        enqb_queue2 = json.loads(enqb_queue_path.read_text())
        if len(enqb_queue2["queue"]) != 1:
            failures.append(
                f"[enqueue-bug] duplicate enqueue changed queue length; "
                f"expected 1, got {len(enqb_queue2['queue'])}"
            )
        print("  [enqueue-bug] enqueue_adhoc_bug routes to docs/bugs + idempotent: ok")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-1: feature materialize (User Story → docs/features)
        # -------------------------------------------------------------------
        fix_name_fm = "materialize-feature"
        mat_root = td_path / fix_name_fm
        mat_work = mat_root / "docs" / "work"
        mat_work.mkdir(parents=True, exist_ok=True)
        (mat_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (mat_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _mat_wi_id = 42
        _mat_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _mat_wi_id,
                    "type": "User Story",
                    "title": "Build the thing",
                    "description": "Detailed description here.",
                    "acceptanceCriteria": "Given X then Y.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/42",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (mat_work / "ado-mirror.json").write_text(
            json.dumps(_mat_mirror, indent=2), encoding="utf-8"
        )
        _mat_type_map = {
            "bug": ["Bug", "Defect", "Story Bug", "Engineering Bug"],
            "feature": ["User Story", "Refactor Story", "Enabler Story", "Requirement"],
        }
        try:
            result_fm = materialize_wi(mat_root, _mat_wi_id, _mat_type_map)
            slug_fm = result_fm.get("feature_id") or result_fm.get("slug") or ""
            fm_ok = True
            # status must indicate materialized + feature pipeline
            if result_fm.get("status") not in ("materialized", "ok") and "feature" not in str(result_fm.get("status", "")):
                failures.append(
                    f"[{fix_name_fm}] expected status indicating materialized/feature, "
                    f"got {result_fm.get('status')!r}"
                )
                fm_ok = False
            # ADHOC_BRIEF.md exists and contains verbatim WI fields
            brief_fm = mat_root / "docs" / "features" / slug_fm / "ADHOC_BRIEF.md"
            if not brief_fm.exists():
                failures.append(
                    f"[{fix_name_fm}] ADHOC_BRIEF.md not found at {brief_fm}"
                )
                fm_ok = False
            else:
                brief_text = brief_fm.read_text(encoding="utf-8")
                for substr in ["Build the thing", "Detailed description here.", "Given X then Y."]:
                    if substr not in brief_text:
                        failures.append(
                            f"[{fix_name_fm}] ADHOC_BRIEF.md missing verbatim substring: {substr!r}"
                        )
                        fm_ok = False
            # SPEC.md contains the Work Item line
            spec_fm = mat_root / "docs" / "features" / slug_fm / "SPEC.md"
            if not spec_fm.exists():
                failures.append(f"[{fix_name_fm}] SPEC.md not found at {spec_fm}")
                fm_ok = False
            else:
                spec_text = spec_fm.read_text(encoding="utf-8")
                expected_wi_line = f"**Work Item:** AB#{_mat_wi_id}"
                if expected_wi_line not in spec_text:
                    failures.append(
                        f"[{fix_name_fm}] SPEC.md missing {expected_wi_line!r}"
                    )
                    fm_ok = False
            # queue.json has the slug entry
            fq_path = mat_root / "docs" / "features" / "queue.json"
            if not fq_path.exists():
                failures.append(f"[{fix_name_fm}] docs/features/queue.json not written")
                fm_ok = False
            else:
                fq = json.loads(fq_path.read_text(encoding="utf-8"))
                if not any(e.get("id") == slug_fm or e.get("spec_dir") == slug_fm for e in fq.get("queue", [])):
                    failures.append(
                        f"[{fix_name_fm}] queue.json has no entry for slug {slug_fm!r}"
                    )
                    fm_ok = False
            # read_materialized returns exactly 1 record for that wi_id
            mat_records = lazy_core.read_materialized(mat_work)
            wi_records = [r for r in mat_records if r.get("wi_id") == _mat_wi_id]
            if len(wi_records) != 1:
                failures.append(
                    f"[{fix_name_fm}] expected 1 materialized record for wi_id={_mat_wi_id}; "
                    f"got {len(wi_records)}"
                )
                fm_ok = False
            print(f"  {'PASS' if fm_ok else 'FAIL'} [{fix_name_fm}] feature materialize")
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_fm}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_fm}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-2: bug materialize (Bug → docs/bugs via subprocess)
        # -------------------------------------------------------------------
        fix_name_bm = "materialize-bug"
        bm_root = td_path / fix_name_bm
        bm_work = bm_root / "docs" / "work"
        bm_work.mkdir(parents=True, exist_ok=True)
        (bm_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (bm_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _bm_wi_id = 99
        _bm_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _bm_wi_id,
                    "type": "Bug",
                    "title": "Broken submit button",
                    "description": "The submit button does nothing.",
                    "acceptanceCriteria": "Button triggers form submission.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/99",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (bm_work / "ado-mirror.json").write_text(
            json.dumps(_bm_mirror, indent=2), encoding="utf-8"
        )
        try:
            result_bm = materialize_wi(bm_root, _bm_wi_id, _mat_type_map)
            slug_bm = result_bm.get("feature_id") or result_bm.get("slug") or ""
            bm_ok = True
            # ADHOC_BRIEF.md in docs/bugs/<slug> with verbatim fields
            brief_bm = bm_root / "docs" / "bugs" / slug_bm / "ADHOC_BRIEF.md"
            if not brief_bm.exists():
                failures.append(
                    f"[{fix_name_bm}] ADHOC_BRIEF.md not found at {brief_bm}"
                )
                bm_ok = False
            else:
                brief_bm_text = brief_bm.read_text(encoding="utf-8")
                for substr in ["Broken submit button", "The submit button does nothing.", "Button triggers form submission."]:
                    if substr not in brief_bm_text:
                        failures.append(
                            f"[{fix_name_bm}] ADHOC_BRIEF.md missing verbatim substring: {substr!r}"
                        )
                        bm_ok = False
            # docs/bugs/queue.json has a spec_dir entry for this slug
            bq_path = bm_root / "docs" / "bugs" / "queue.json"
            if not bq_path.exists():
                failures.append(f"[{fix_name_bm}] docs/bugs/queue.json not written")
                bm_ok = False
            else:
                bq = json.loads(bq_path.read_text(encoding="utf-8"))
                if not any(e.get("spec_dir") == slug_bm or e.get("id") == str(_bm_wi_id) for e in bq.get("queue", [])):
                    failures.append(
                        f"[{fix_name_bm}] bugs/queue.json has no entry with spec_dir={slug_bm!r}"
                    )
                    bm_ok = False
            # docs/features/ must NOT have a new dir for this WI
            feat_dirs_bm = [
                p.name for p in (bm_root / "docs" / "features").iterdir()
                if p.is_dir()
            ]
            if slug_bm in feat_dirs_bm:
                failures.append(
                    f"[{fix_name_bm}] bug route must NOT create docs/features/{slug_bm}"
                )
                bm_ok = False
            print(f"  {'PASS' if bm_ok else 'FAIL'} [{fix_name_bm}] bug materialize")
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_bm}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_bm}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-3: unknown type (no-op / skip)
        # -------------------------------------------------------------------
        fix_name_ut = "materialize-unknown-type"
        ut_root = td_path / fix_name_ut
        ut_work = ut_root / "docs" / "work"
        ut_work.mkdir(parents=True, exist_ok=True)
        (ut_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (ut_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _ut_wi_id = 77
        _ut_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _ut_wi_id,
                    "type": "Task",
                    "title": "A task nobody wants",
                    "description": "Just a task.",
                    "acceptanceCriteria": "Done.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/77",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (ut_work / "ado-mirror.json").write_text(
            json.dumps(_ut_mirror, indent=2), encoding="utf-8"
        )
        try:
            result_ut = materialize_wi(ut_root, _ut_wi_id, _mat_type_map)
            ut_ok = True
            # No new dir under docs/features or docs/bugs
            feat_dirs_ut = [p.name for p in (ut_root / "docs" / "features").iterdir() if p.is_dir()]
            bug_dirs_ut = [p.name for p in (ut_root / "docs" / "bugs").iterdir() if p.is_dir()]
            if feat_dirs_ut:
                failures.append(
                    f"[{fix_name_ut}] unknown-type must not create features dirs; got {feat_dirs_ut}"
                )
                ut_ok = False
            if bug_dirs_ut:
                failures.append(
                    f"[{fix_name_ut}] unknown-type must not create bugs dirs; got {bug_dirs_ut}"
                )
                ut_ok = False
            # Queue lengths unchanged (no queue files created)
            fq_ut = ut_root / "docs" / "features" / "queue.json"
            bq_ut = ut_root / "docs" / "bugs" / "queue.json"
            if fq_ut.exists() and json.loads(fq_ut.read_text())["queue"]:
                failures.append(f"[{fix_name_ut}] unknown-type must not enqueue in features")
                ut_ok = False
            if bq_ut.exists() and json.loads(bq_ut.read_text())["queue"]:
                failures.append(f"[{fix_name_ut}] unknown-type must not enqueue in bugs")
                ut_ok = False
            # materialized.json unchanged (0 records)
            ut_records = lazy_core.read_materialized(ut_work)
            if ut_records:
                failures.append(
                    f"[{fix_name_ut}] unknown-type must not append to materialized.json; "
                    f"got {ut_records}"
                )
                ut_ok = False
            # returned a skip status (did not raise)
            if result_ut.get("status") not in ("skipped", "skip", "unknown-type"):
                failures.append(
                    f"[{fix_name_ut}] expected skip status, got {result_ut.get('status')!r}"
                )
                ut_ok = False
            print(f"  {'PASS' if ut_ok else 'FAIL'} [{fix_name_ut}] unknown type → skip")
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_ut}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_ut}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-4: idempotent double-materialize
        # -------------------------------------------------------------------
        fix_name_idem = "materialize-idempotent"
        idem_root = td_path / fix_name_idem
        idem_work = idem_root / "docs" / "work"
        idem_work.mkdir(parents=True, exist_ok=True)
        (idem_root / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (idem_root / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
        _idem_wi_id = 55
        _idem_mirror = {
            "syncedAt": "2026-06-01T12:00:00Z",
            "watermark": "2026-06-01",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _idem_wi_id,
                    "type": "User Story",
                    "title": "Idempotent feature",
                    "description": "Should only appear once.",
                    "acceptanceCriteria": "Only one record.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/55",
                    "changedDate": "2026-06-01T10:00:00Z",
                }
            ],
        }
        (idem_work / "ado-mirror.json").write_text(
            json.dumps(_idem_mirror, indent=2), encoding="utf-8"
        )
        try:
            result_idem1 = materialize_wi(idem_root, _idem_wi_id, _mat_type_map)
            result_idem2 = materialize_wi(idem_root, _idem_wi_id, _mat_type_map)
            slug_idem = result_idem1.get("feature_id") or result_idem1.get("slug") or ""
            idem_ok = True
            # materialized.json must have exactly 1 record for wi_id
            idem_records = [r for r in lazy_core.read_materialized(idem_work) if r.get("wi_id") == _idem_wi_id]
            if len(idem_records) != 1:
                failures.append(
                    f"[{fix_name_idem}] expected exactly 1 materialized record after 2 calls; "
                    f"got {len(idem_records)}"
                )
                idem_ok = False
            # queue.json has exactly 1 entry for the slug
            fq_idem = idem_root / "docs" / "features" / "queue.json"
            if not fq_idem.exists():
                failures.append(f"[{fix_name_idem}] queue.json not written")
                idem_ok = False
            else:
                fq_idem_data = json.loads(fq_idem.read_text(encoding="utf-8"))
                slug_entries = [
                    e for e in fq_idem_data.get("queue", [])
                    if e.get("id") == slug_idem or e.get("spec_dir") == slug_idem
                ]
                if len(slug_entries) != 1:
                    failures.append(
                        f"[{fix_name_idem}] expected exactly 1 queue entry for {slug_idem!r}; "
                        f"got {len(slug_entries)}"
                    )
                    idem_ok = False
            print(
                f"  {'PASS' if idem_ok else 'FAIL'} [{fix_name_idem}] "
                f"idempotent: 1 record after 2 materialize calls"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_idem}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_idem}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-5: stale detection (writer)
        # -------------------------------------------------------------------
        fix_name_stale = "stale-detection-writer"
        stale_root = td_path / fix_name_stale
        stale_work = stale_root / "docs" / "work"
        stale_work.mkdir(parents=True, exist_ok=True)
        _stale_wi_id = 101
        _stale_slug = "feat-stale-wi"
        stale_feat_dir = stale_root / "docs" / "features" / _stale_slug
        stale_feat_dir.mkdir(parents=True, exist_ok=True)
        (stale_feat_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        spec_mtime_before = (stale_feat_dir / "SPEC.md").stat().st_mtime_ns
        # Seed materialized.json with an OLDER changedDate
        lazy_core.append_materialized(stale_work, _stale_wi_id, _stale_slug, "2026-06-01T00:00:00Z")
        # Mirror has a NEWER changedDate for the same WI
        _stale_mirror = {
            "syncedAt": "2026-06-10T12:00:00Z",
            "watermark": "2026-06-10",
            "query": "SELECT ...",
            "workItems": [
                {
                    "id": _stale_wi_id,
                    "type": "User Story",
                    "title": "Updated upstream WI",
                    "description": "Updated description.",
                    "acceptanceCriteria": "New AC.",
                    "url": "https://dev.azure.com/org/proj/_workitems/edit/101",
                    "changedDate": "2026-06-10T00:00:00Z",
                }
            ],
        }
        (stale_work / "ado-mirror.json").write_text(
            json.dumps(_stale_mirror, indent=2), encoding="utf-8"
        )
        try:
            check_stale_upstream(stale_root)
            stale_ok = True
            # STALE_UPSTREAM.md must now exist in the feature dir
            stale_sentinel = stale_feat_dir / "STALE_UPSTREAM.md"
            if not stale_sentinel.exists():
                failures.append(
                    f"[{fix_name_stale}] STALE_UPSTREAM.md not written to {stale_sentinel}"
                )
                stale_ok = False
            # SPEC.md must NOT have been modified (mtime_ns unchanged)
            spec_mtime_after = (stale_feat_dir / "SPEC.md").stat().st_mtime_ns
            if spec_mtime_after != spec_mtime_before:
                failures.append(
                    f"[{fix_name_stale}] SPEC.md was clobbered (mtime changed)"
                )
                stale_ok = False
            print(
                f"  {'PASS' if stale_ok else 'FAIL'} [{fix_name_stale}] "
                f"stale detection writes STALE_UPSTREAM.md, preserves SPEC.md"
            )
        except NotImplementedError as exc:
            failures.append(
                f"[{fix_name_stale}] NotImplementedError (stub not yet implemented): {exc}"
            )
            print(f"  FAIL [{fix_name_stale}]: NotImplementedError — {exc}")

        # -------------------------------------------------------------------
        # Fixture WU-3.3-6: stale halt (reader) — compute_state returns
        #   terminal_reason == "stale_upstream" when STALE_UPSTREAM.md is present
        # -------------------------------------------------------------------
        fix_name_halt = "stale-halt-reader"
        halt_root = td_path / fix_name_halt
        halt_features = halt_root / "docs" / "features"
        halt_features.mkdir(parents=True, exist_ok=True)
        (halt_features / "ROADMAP.md").write_text("# Roadmap\n")
        (halt_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-stale-halt", "name": "Stale Halt Feature",
                 "spec_dir": "feat-stale-halt", "tier": 1}
            ]
        }))
        halt_dir = halt_features / "feat-stale-halt"
        halt_dir.mkdir()
        (halt_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (halt_dir / "RESEARCH.md").write_text("# R\n")
        (halt_dir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Drop a STALE_UPSTREAM.md into the feature dir
        (halt_dir / "STALE_UPSTREAM.md").write_text(
            "Upstream WI changed on 2026-06-10 — re-materialize required.\n",
            encoding="utf-8",
        )
        try:
            got_halt = compute_state(halt_root, cloud=False, real_device=True)
            halt_ok = True
            if got_halt.get("terminal_reason") != "stale_upstream":
                failures.append(
                    f"[{fix_name_halt}] expected terminal_reason='stale_upstream', "
                    f"got {got_halt.get('terminal_reason')!r} "
                    f"(current_step={got_halt.get('current_step')!r})"
                )
                halt_ok = False
            # Must NOT have routed to a normal work step
            if got_halt.get("sub_skill") is not None:
                failures.append(
                    f"[{fix_name_halt}] stale halt must not dispatch a sub_skill; "
                    f"got sub_skill={got_halt.get('sub_skill')!r}"
                )
                halt_ok = False
            print(
                f"  {'PASS' if halt_ok else 'FAIL'} [{fix_name_halt}] "
                f"stale halt: terminal_reason={got_halt.get('terminal_reason')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_name_halt}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture WU-4.2-1: scoped-feature-id
        # Two actionable ad-hoc features; default picks the FIRST (feat-scope-alpha),
        # so scoping to the SECOND (feat-scope-beta) proves the filter took effect.
        # scope_feature_id is now implemented; the TypeError guard below is dead code
        # retained for harness symmetry.
        # -------------------------------------------------------------------
        fix_scope_root = td_path / "scope-filter"
        scope_features = fix_scope_root / "docs" / "features"
        scope_features.mkdir(parents=True, exist_ok=True)
        (scope_features / "ROADMAP.md").write_text("# Roadmap\n")
        (scope_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-scope-alpha", "name": "Scope Alpha",
                 "spec_dir": "feat-scope-alpha", "tier": 1},
                {"id": "feat-scope-beta", "name": "Scope Beta",
                 "spec_dir": "feat-scope-beta", "tier": 1},
            ]
        }))
        for fid in ("feat-scope-alpha", "feat-scope-beta"):
            fdir = scope_features / fid
            fdir.mkdir()
            (fdir / "SPEC.md").write_text(
                "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
            )
            (fdir / "RESEARCH.md").write_text("# R\n")
            (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n")
        # Defensive: scope_feature_id is implemented; the TypeError guard below is dead code retained for harness symmetry.
        try:
            got_scoped = compute_state(
                fix_scope_root, cloud=False, real_device=True,
                scope_feature_id="feat-scope-beta",
            )
            # If we reach here the param already exists; validate the filter result.
            if got_scoped.get("feature_id") != "feat-scope-beta":
                failures.append(
                    f"[scoped-feature-id] expected feature_id='feat-scope-beta', "
                    f"got {got_scoped.get('feature_id')!r}"
                )
                print("  FAIL [scoped-feature-id] scoping did not select feat-scope-beta")
            else:
                print("  PASS [scoped-feature-id] scope_feature_id selected feat-scope-beta")
        except TypeError as e:
            failures.append(
                f"[scoped-feature-id] TypeError (scope_feature_id param not yet "
                f"implemented): {e}"
            )
            print(f"  FAIL [scoped-feature-id] TypeError — {e}")

        # -------------------------------------------------------------------
        # Fixture WU-4.2-2: baseline-regression-default (GREEN GUARD)
        # Same two-feature queue; default (no scope param) must pick the FIRST
        # actionable feature (feat-scope-alpha). This fixture is intentionally
        # GREEN now and must stay GREEN after the impl lands — it proves the
        # upcoming change is non-breaking.
        # -------------------------------------------------------------------
        try:
            got_default = compute_state(
                fix_scope_root, cloud=False, real_device=True,
            )
            default_ok = True
            if got_default.get("feature_id") != "feat-scope-alpha":
                failures.append(
                    f"[baseline-regression-default] expected feature_id='feat-scope-alpha', "
                    f"got {got_default.get('feature_id')!r}"
                )
                default_ok = False
            if got_default.get("current_step") != "Step 6: plan feature (phases + plan)":
                failures.append(
                    f"[baseline-regression-default] expected current_step='Step 6: plan "
                    f"feature (phases + plan)', got {got_default.get('current_step')!r}"
                )
                default_ok = False
            print(
                f"  {'PASS' if default_ok else 'FAIL'} [baseline-regression-default] "
                f"default picks feat-scope-alpha at "
                f"{got_default.get('current_step')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[baseline-regression-default] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture: scoped-feature-id-not-found  (RED until impl lands)
        # Same two-feature queue as the scoped-feature-id fixture above; but
        # the scope_feature_id is a typo'd id that matches NO entry.
        # EXPECTED: terminal_reason == "scoped-id-not-found"
        # CURRENT (pre-fix): falls through to terminal_reason == "all-features-complete"
        # The impl agent must emit a distinct terminal so callers can distinguish
        # "queue exhausted" from "id was never in the queue at all".
        # -------------------------------------------------------------------
        fix_not_found = "scoped-feature-id-not-found"
        try:
            got_not_found = compute_state(
                fix_scope_root, cloud=False, real_device=True,
                scope_feature_id="feat-typo-does-not-exist",
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
        except (TypeError, SystemExit) as e:
            failures.append(f"[{fix_not_found}] unexpected exception: {type(e).__name__}: {e}")
            print(f"  FAIL [{fix_not_found}] {type(e).__name__} — {e}")

        # -------------------------------------------------------------------
        # Fixtures: scoped deferred identity preservation
        # (bug-state-scoped-query-loses-deferred-bug-identity, Phase 2 —
        #  feature-side parity twin of bug-state.py's Phase-1 scoped fixtures).
        #
        # A --feature-id scoped query on a feature that WOULD be skipped by the
        # cloud-saturated / device-saturated / host-capability-deferred branch must
        # return the feature's OWN identity + a scoped deferred terminal_reason,
        # NOT feature_id: null / the global exhausted terminal. UNSCOPED byte-
        # identity is guarded by the existing baseline-regression-default fixture
        # AND the table-driven cloud-saturated / host-cap-miss-defers cases above.
        # -------------------------------------------------------------------

        # Fixture A (scoped cloud-saturated identity): a cloud-saturated feature
        # (DEFERRED_NON_CLOUD.md + no VALIDATED.md + phases complete) queried with
        # --feature-id under --cloud returns its id + TR_CLOUD_DEFERRED_SCOPED.
        fix_scoped_cloud = "scoped-cloud-saturated-identity"
        sc_root = td_path / "scoped-cloud-id"
        sc_feat = sc_root / "docs" / "features"
        sc_feat.mkdir(parents=True, exist_ok=True)
        (sc_feat / "ROADMAP.md").write_text("# Roadmap\n")
        (sc_feat / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sc", "name": "Feature SC", "spec_dir": "feat-sc", "tier": 1},
            ]
        }))
        sc_d = sc_feat / "feat-sc"
        sc_d.mkdir()
        (sc_d / "SPEC.md").write_text("# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n")
        (sc_d / "RESEARCH.md").write_text("# R\n")
        (sc_d / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (sc_d / "PHASES.md").write_text("# P\n\n- [x] Done\n")
        _write_yaml_sentinel(
            sc_d / "DEFERRED_NON_CLOUD.md", "deferred-non-cloud",
            feature_id="feat-sc", deferred_step=8, reason="cloud limitation",
            deferred_by="lazy-cloud", date="2026-06-22",
        )
        try:
            got_sc = compute_state(
                sc_root, cloud=True, real_device=True,
                scope_feature_id="feat-sc",
            )
            sc_ok = True
            if got_sc.get("feature_id") != "feat-sc":
                failures.append(
                    f"[{fix_scoped_cloud}] expected feature_id='feat-sc', "
                    f"got {got_sc.get('feature_id')!r}"
                )
                sc_ok = False
            if got_sc.get("terminal_reason") != TR_CLOUD_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_cloud}] expected terminal_reason="
                    f"{TR_CLOUD_DEFERRED_SCOPED!r}, got {got_sc.get('terminal_reason')!r}"
                )
                sc_ok = False
            if not got_sc.get("spec_path"):
                failures.append(f"[{fix_scoped_cloud}] expected non-null spec_path")
                sc_ok = False
            print(
                f"  {'PASS' if sc_ok else 'FAIL'} [{fix_scoped_cloud}] "
                f"scoped cloud query returns feat-sc + scoped terminal"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_scoped_cloud}] SystemExit: {exc.code}")

        # Fixture B (scoped device-saturated identity): a device-saturated feature
        # (DEFERRED_REQUIRES_DEVICE.md + no VALIDATED.md + phases complete) queried
        # with --feature-id on a no-real-device host returns its id +
        # TR_DEVICE_DEFERRED_SCOPED.
        fix_scoped_device = "scoped-device-saturated-identity"
        sd_root = td_path / "scoped-device-id"
        sd_feat = sd_root / "docs" / "features"
        sd_feat.mkdir(parents=True, exist_ok=True)
        (sd_feat / "ROADMAP.md").write_text("# Roadmap\n")
        (sd_feat / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sd", "name": "Feature SD", "spec_dir": "feat-sd", "tier": 1},
            ]
        }))
        sd_d = sd_feat / "feat-sd"
        sd_d.mkdir()
        (sd_d / "SPEC.md").write_text("# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n")
        (sd_d / "RESEARCH.md").write_text("# R\n")
        (sd_d / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (sd_d / "PHASES.md").write_text("# P\n\n- [x] Done\n")
        _write_yaml_sentinel(
            sd_d / "DEFERRED_REQUIRES_DEVICE.md", "deferred-requires-device",
            feature_id="feat-sd",
            deferred_scenarios=["AQ-TE-05"],
            reason="sustained zero-dropout not certifiable under HeadlessPumpDriver",
            deferred_by="lazy", date="2026-06-22",
        )
        try:
            got_sd = compute_state(
                sd_root, cloud=False, real_device=False,
                scope_feature_id="feat-sd",
            )
            sd_ok = True
            if got_sd.get("feature_id") != "feat-sd":
                failures.append(
                    f"[{fix_scoped_device}] expected feature_id='feat-sd', "
                    f"got {got_sd.get('feature_id')!r}"
                )
                sd_ok = False
            if got_sd.get("terminal_reason") != TR_DEVICE_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_device}] expected terminal_reason="
                    f"{TR_DEVICE_DEFERRED_SCOPED!r}, got {got_sd.get('terminal_reason')!r}"
                )
                sd_ok = False
            print(
                f"  {'PASS' if sd_ok else 'FAIL'} [{fix_scoped_device}] "
                f"scoped device query returns feat-sd + scoped terminal"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_scoped_device}] SystemExit: {exc.code}")

        # Fixture C (scoped host-capability-deferred identity): a feature past
        # implementation declaring requires_host: [gpu] queried with --feature-id
        # on a host whose injected present-set lacks gpu returns its id +
        # TR_HOST_DEFERRED_SCOPED (NOT the global host-capability-saturated).
        fix_scoped_host = "scoped-host-capability-identity"
        sh_root = td_path / "scoped-host-id"
        sh_feat = sh_root / "docs" / "features"
        sh_feat.mkdir(parents=True, exist_ok=True)
        (sh_feat / "ROADMAP.md").write_text("# Roadmap\n")
        (sh_feat / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sh", "name": "Feature SH", "spec_dir": "feat-sh", "tier": 1,
                 "requires_host": ["gpu"]},
            ]
        }))
        sh_d = sh_feat / "feat-sh"
        sh_d.mkdir()
        (sh_d / "SPEC.md").write_text("# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n")
        (sh_d / "RESEARCH.md").write_text("# R\n")
        (sh_d / "RESEARCH_SUMMARY.md").write_text("# S\n")
        (sh_d / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
        try:
            got_sh = compute_state(
                sh_root, cloud=False, real_device=True,
                scope_feature_id="feat-sh",
                host_present=set(),  # gpu absent → missing = {gpu}
            )
            sh_ok = True
            if got_sh.get("feature_id") != "feat-sh":
                failures.append(
                    f"[{fix_scoped_host}] expected feature_id='feat-sh', "
                    f"got {got_sh.get('feature_id')!r}"
                )
                sh_ok = False
            if got_sh.get("terminal_reason") != TR_HOST_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_host}] expected terminal_reason="
                    f"{TR_HOST_DEFERRED_SCOPED!r}, got {got_sh.get('terminal_reason')!r}"
                )
                sh_ok = False
            print(
                f"  {'PASS' if sh_ok else 'FAIL'} [{fix_scoped_host}] "
                f"scoped host-capability query returns feat-sh + scoped terminal"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_scoped_host}] SystemExit: {exc.code}")

        # Fixture D (scoped operator-deferred identity):
        # merged-head-oracle-per-signal-supplement-churn Phase 1. A feature
        # carrying a bare DEFERRED.md queried with --feature-id returns its OWN
        # identity + TR_OPERATOR_DEFERRED_SCOPED, NOT the global null-identity
        # all-remaining-deferred terminal. Feature-side twin of bug-state.py's
        # scoped-operator-deferred-identity fixture.
        fix_scoped_opdef = "scoped-operator-deferred-identity"
        sod_root = td_path / "scoped-operator-deferred"
        sod_feat = sod_root / "docs" / "features"
        sod_feat.mkdir(parents=True, exist_ok=True)
        (sod_feat / "ROADMAP.md").write_text("# Roadmap\n")
        (sod_feat / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-sod", "name": "Feature SOD", "spec_dir": "feat-sod", "tier": 1},
            ]
        }))
        sod_d = sod_feat / "feat-sod"
        sod_d.mkdir()
        (sod_d / "SPEC.md").write_text("# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n")
        _write_yaml_sentinel(
            sod_d / "DEFERRED.md", "deferred",
            feature_id="feat-sod",
            reason="Operator parked for scoped-identity test.",
            deferred_at="2026-07-19",
        )
        try:
            got_sod = compute_state(
                sod_root, cloud=False, real_device=True,
                scope_feature_id="feat-sod",
            )
            sod_ok = True
            if got_sod.get("feature_id") != "feat-sod":
                failures.append(
                    f"[{fix_scoped_opdef}] expected feature_id='feat-sod', "
                    f"got {got_sod.get('feature_id')!r}"
                )
                sod_ok = False
            if got_sod.get("terminal_reason") != TR_OPERATOR_DEFERRED_SCOPED:
                failures.append(
                    f"[{fix_scoped_opdef}] expected terminal_reason="
                    f"{TR_OPERATOR_DEFERRED_SCOPED!r}, got "
                    f"{got_sod.get('terminal_reason')!r}"
                )
                sod_ok = False
            if got_sod.get("terminal_reason") == TR_ALL_DEFERRED:
                failures.append(
                    f"[{fix_scoped_opdef}] scoped query erroneously returned global "
                    f"{TR_ALL_DEFERRED!r} (identity lost)"
                )
                sod_ok = False
            print(
                f"  {'PASS' if sod_ok else 'FAIL'} [{fix_scoped_opdef}] "
                f"scoped operator-deferred query returns feat-sod + scoped terminal"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_scoped_opdef}] SystemExit: {exc.code}")

        # Unscoped regression twin: the SAME single-deferred-feature root queried
        # WITHOUT a scope id returns the global all-remaining-deferred terminal
        # (feature_id None) — proving the scoped branch fires ONLY on a match and
        # the unscoped walk still `continue`s into the global terminal.
        fix_unscoped_opdef = "unscoped-operator-deferred-regression"
        try:
            got_uod = compute_state(sod_root, cloud=False, real_device=True)
            uod_ok = True
            if got_uod.get("terminal_reason") != TR_ALL_DEFERRED:
                failures.append(
                    f"[{fix_unscoped_opdef}] expected terminal_reason="
                    f"{TR_ALL_DEFERRED!r}, got {got_uod.get('terminal_reason')!r}"
                )
                uod_ok = False
            if got_uod.get("feature_id") is not None:
                failures.append(
                    f"[{fix_unscoped_opdef}] expected feature_id=None (global), "
                    f"got {got_uod.get('feature_id')!r}"
                )
                uod_ok = False
            print(
                f"  {'PASS' if uod_ok else 'FAIL'} [{fix_unscoped_opdef}] "
                f"unscoped returns global all-remaining-deferred"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_unscoped_opdef}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture WU-1-park: --park-needs-input mode (Phase 4)
        #
        # Two-feature queue:
        #   feat-parked  — carries NEEDS_INPUT.md (well-formed, 1 decision)
        #   feat-after   — actionable (Open, SPEC+RESEARCH present)
        #
        # Sub-fixture A: WITHOUT park_needs_input → terminal_reason=="needs-input"
        #                AND "parked" key ABSENT from output.
        # Sub-fixture B: WITH park_needs_input=True → feat-after is dispatched,
        #                output has "parked" list with one entry whose id matches
        #                feat-parked and decision_count==1.
        # Sub-fixture C: RESOLVED sentinel (NEEDS_INPUT.md removed) → feat-parked
        #                is dispatched normally, "parked" is empty.
        # -------------------------------------------------------------------
        park_root = td_path / "park-needs-input"
        park_features = park_root / "docs" / "features"
        park_features.mkdir(parents=True, exist_ok=True)
        (park_features / "ROADMAP.md").write_text("# Roadmap\n")
        (park_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-parked", "name": "Parked Feature",
                 "spec_dir": "feat-parked", "tier": 1},
                {"id": "feat-after", "name": "After Feature",
                 "spec_dir": "feat-after", "tier": 1},
            ]
        }))
        # feat-parked: Open spec + RESEARCH + NEEDS_INPUT.md (1 decision, date set)
        parked_dir = park_features / "feat-parked"
        parked_dir.mkdir()
        (parked_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (parked_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (parked_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
        needs_input_content = (
            "---\n"
            "kind: needs-input\n"
            "feature_id: feat-parked\n"
            "written_by: spec-phases\n"
            "decisions:\n"
            "  - Choose auth strategy\n"
            "date: 2026-06-10\n"
            "---\n\n"
            "# Needs Input\n"
        )
        park_sentinel = parked_dir / "NEEDS_INPUT.md"
        park_sentinel.write_text(needs_input_content, encoding="utf-8")
        # feat-after: actionable (Open, SPEC+RESEARCH, no NEEDS_INPUT.md)
        after_dir = park_features / "feat-after"
        after_dir.mkdir()
        (after_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (after_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (after_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")

        # Sub-fixture A: without park_needs_input → needs-input halt, NO "parked" key
        fix_park_default = "park-needs-input-default-halt"
        try:
            got_park_default = compute_state(park_root, cloud=False, real_device=True)
            pda_ok = True
            actual_tr_park = got_park_default.get("terminal_reason")
            # CORRECT assertion: without the flag, needs-input halt must fire.
            if actual_tr_park != "needs-input":
                failures.append(
                    f"[{fix_park_default}] expected terminal_reason='needs-input', "
                    f"got {actual_tr_park!r}"
                )
                pda_ok = False
            # CRITICAL: "parked" key must be ABSENT when not in park mode.
            if "parked" in got_park_default:
                failures.append(
                    f"[{fix_park_default}] 'parked' key must be absent in default mode; "
                    f"got parked={got_park_default['parked']!r}"
                )
                pda_ok = False
            print(
                f"  {'PASS' if pda_ok else 'FAIL'} [{fix_park_default}] "
                f"default: terminal_reason={actual_tr_park!r}, parked key absent={('parked' not in got_park_default)}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_default}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_default}] SystemExit: {exc.code}")

        # Sub-fixture B: WITH park_needs_input=True → feat-after dispatched,
        # output["parked"] has one entry with id="feat-parked", decision_count=1.
        fix_park_mode = "park-needs-input-mode-skip"
        try:
            got_park_mode = compute_state(
                park_root, cloud=False, real_device=True, park_needs_input=True
            )
            pmode_ok = True
            # The halt must NOT be needs-input (feat-parked is skipped)
            actual_tr_mode = got_park_mode.get("terminal_reason")
            if actual_tr_mode == "needs-input":
                failures.append(
                    f"[{fix_park_mode}] terminal_reason must NOT be 'needs-input' in park mode; "
                    f"got {actual_tr_mode!r}"
                )
                pmode_ok = False
            # feat-after must be dispatched as current
            if got_park_mode.get("feature_id") != "feat-after":
                failures.append(
                    f"[{fix_park_mode}] expected feature_id='feat-after', "
                    f"got {got_park_mode.get('feature_id')!r}"
                )
                pmode_ok = False
            # "parked" key must be present and contain one entry
            parked_list = got_park_mode.get("parked")
            if not isinstance(parked_list, list) or len(parked_list) != 1:
                failures.append(
                    f"[{fix_park_mode}] expected parked=[...1 entry...], "
                    f"got {parked_list!r}"
                )
                pmode_ok = False
            elif parked_list[0].get("id") != "feat-parked":
                failures.append(
                    f"[{fix_park_mode}] parked[0].id must be 'feat-parked', "
                    f"got {parked_list[0].get('id')!r}"
                )
                pmode_ok = False
            elif parked_list[0].get("decision_count") != 1:
                failures.append(
                    f"[{fix_park_mode}] parked[0].decision_count must be 1, "
                    f"got {parked_list[0].get('decision_count')!r}"
                )
                pmode_ok = False
            print(
                f"  {'PASS' if pmode_ok else 'FAIL'} [{fix_park_mode}] "
                f"park mode: dispatched={got_park_mode.get('feature_id')!r}, "
                f"parked count={len(parked_list) if isinstance(parked_list, list) else 'N/A'}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_mode}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_mode}] SystemExit: {exc.code}")

        # Sub-fixture C: RESOLVED — remove NEEDS_INPUT.md → feat-parked is dispatched
        # normally and parked[] is empty.
        fix_park_resolved = "park-needs-input-resolved-reenter"
        try:
            park_sentinel.unlink()  # resolve the sentinel
            got_park_resolved = compute_state(
                park_root, cloud=False, real_device=True, park_needs_input=True
            )
            presolved_ok = True
            # feat-parked is now first and actionable — it must be dispatched.
            if got_park_resolved.get("feature_id") != "feat-parked":
                failures.append(
                    f"[{fix_park_resolved}] expected feature_id='feat-parked' after resolution, "
                    f"got {got_park_resolved.get('feature_id')!r}"
                )
                presolved_ok = False
            # parked[] must be empty (no items parked this probe).
            parked_resolved = got_park_resolved.get("parked")
            if not isinstance(parked_resolved, list) or len(parked_resolved) != 0:
                failures.append(
                    f"[{fix_park_resolved}] expected parked=[], "
                    f"got {parked_resolved!r}"
                )
                presolved_ok = False
            print(
                f"  {'PASS' if presolved_ok else 'FAIL'} [{fix_park_resolved}] "
                f"resolved: dispatched={got_park_resolved.get('feature_id')!r}, "
                f"parked={parked_resolved!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_resolved}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_resolved}] SystemExit: {exc.code}")

        # Sub-fixture D: BLOCKED.md precedence — feat-parked carries BOTH
        # BLOCKED.md AND NEEDS_INPUT.md.  Under park mode it must STILL halt as
        # "blocked", not be silently parked.  This locks FIX 1 of the code review.
        fix_park_blocked_precedence = "park-needs-input-blocked-precedence"
        try:
            # Restore NEEDS_INPUT.md (removed in sub-fixture C) and add BLOCKED.md.
            park_sentinel.write_text(needs_input_content, encoding="utf-8")
            _write_yaml_sentinel(
                parked_dir / "BLOCKED.md", "blocked",
                feature_id="feat-parked", phase="Spec",
                blocked_at="2026-06-10T00:00:00Z", retry_count=0,
            )
            got_park_blocked = compute_state(
                park_root, cloud=False, real_device=True, park_needs_input=True
            )
            pbp_ok = True
            # Must halt as "blocked" — NOT parked, not dispatched.
            actual_tr_pbp = got_park_blocked.get("terminal_reason")
            if actual_tr_pbp != "blocked":
                failures.append(
                    f"[{fix_park_blocked_precedence}] expected terminal_reason='blocked' "
                    f"(BLOCKED.md must retain precedence over park-mode); "
                    f"got {actual_tr_pbp!r}"
                )
                pbp_ok = False
            # feat-parked must be the reported feature (it is the one that is blocked).
            if got_park_blocked.get("feature_id") != "feat-parked":
                failures.append(
                    f"[{fix_park_blocked_precedence}] expected feature_id='feat-parked', "
                    f"got {got_park_blocked.get('feature_id')!r}"
                )
                pbp_ok = False
            # "parked" key must NOT contain feat-parked (it was NOT parked).
            parked_pbp = got_park_blocked.get("parked", [])
            parked_ids = [e.get("id") for e in parked_pbp if isinstance(e, dict)]
            if "feat-parked" in parked_ids:
                failures.append(
                    f"[{fix_park_blocked_precedence}] feat-parked must NOT appear in "
                    f"parked[] when BLOCKED.md is present; got parked={parked_pbp!r}"
                )
                pbp_ok = False
            print(
                f"  {'PASS' if pbp_ok else 'FAIL'} [{fix_park_blocked_precedence}] "
                f"blocked-precedence: terminal_reason={actual_tr_pbp!r}, "
                f"feat-parked in parked[]={'feat-parked' in parked_ids}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_park_blocked_precedence}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_park_blocked_precedence}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture WU-1-park-blocked: --park-blocked mode
        # (bug park-mode-halts-on-blocked, Phase 1)
        #
        # Two-feature queue in a FRESH root (independent of the needs-input
        # fixture above):
        #   blocked-feat  — carries BLOCKED.md (no NEEDS_INPUT.md)
        #   workable-feat — actionable (Draft, SPEC+RESEARCH present)
        #
        # Sub-fixture 1 (park-blocked-mode-skip): park_blocked=True →
        #   blocked-feat parked, workable-feat dispatched.
        # Sub-fixture 2 (park-blocked-default-halt): no flag → terminal_reason
        #   "blocked", "parked" key ABSENT (byte-identical to today).
        # Sub-fixture 3 (park-blocked-all-parked-terminal): every remaining
        #   feature parked → terminal_reason "queue-exhausted-all-parked".
        # Sub-fixture 4 (park-blocked-and-needs-input-single-park): a feature
        #   carrying BOTH sentinels parks exactly ONCE under both flags.
        # -------------------------------------------------------------------
        pb_root = td_path / "park-blocked"
        pb_features = pb_root / "docs" / "features"
        pb_features.mkdir(parents=True, exist_ok=True)
        (pb_features / "ROADMAP.md").write_text("# Roadmap\n")
        (pb_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "blocked-feat", "name": "Blocked Feature",
                 "spec_dir": "blocked-feat", "tier": 1},
                {"id": "workable-feat", "name": "Workable Feature",
                 "spec_dir": "workable-feat", "tier": 1},
            ]
        }))
        # blocked-feat: Draft spec + RESEARCH + BLOCKED.md (no NEEDS_INPUT.md)
        pb_blocked_dir = pb_features / "blocked-feat"
        pb_blocked_dir.mkdir()
        (pb_blocked_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (pb_blocked_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (pb_blocked_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
        _write_yaml_sentinel(
            pb_blocked_dir / "BLOCKED.md", "blocked",
            feature_id="blocked-feat", phase="Spec",
            blocked_at="2026-06-16T00:00:00Z", retry_count=0,
        )
        # workable-feat: actionable
        pb_workable_dir = pb_features / "workable-feat"
        pb_workable_dir.mkdir()
        (pb_workable_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (pb_workable_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (pb_workable_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")

        # Sub-fixture 1: park_blocked=True → blocked-feat parked, workable dispatched.
        fix_pb_skip = "park-blocked-mode-skip"
        try:
            got_pb_skip = compute_state(
                pb_root, cloud=False, real_device=True, park_blocked=True
            )
            pbskip_ok = True
            if got_pb_skip.get("terminal_reason") == "blocked":
                failures.append(
                    f"[{fix_pb_skip}] terminal_reason must NOT be 'blocked' under "
                    f"park_blocked; got {got_pb_skip.get('terminal_reason')!r}"
                )
                pbskip_ok = False
            if got_pb_skip.get("feature_id") != "workable-feat":
                failures.append(
                    f"[{fix_pb_skip}] expected feature_id='workable-feat', "
                    f"got {got_pb_skip.get('feature_id')!r}"
                )
                pbskip_ok = False
            pb_parked = got_pb_skip.get("parked")
            if not isinstance(pb_parked, list) or len(pb_parked) != 1:
                failures.append(
                    f"[{fix_pb_skip}] expected parked=[...1 entry...], got {pb_parked!r}"
                )
                pbskip_ok = False
            elif pb_parked[0].get("id") != "blocked-feat":
                failures.append(
                    f"[{fix_pb_skip}] parked[0].id must be 'blocked-feat', "
                    f"got {pb_parked[0].get('id')!r}"
                )
                pbskip_ok = False
            elif not str(pb_parked[0].get("sentinel", "")).endswith("BLOCKED.md"):
                failures.append(
                    f"[{fix_pb_skip}] parked[0].sentinel must end in BLOCKED.md, "
                    f"got {pb_parked[0].get('sentinel')!r}"
                )
                pbskip_ok = False
            print(
                f"  {'PASS' if pbskip_ok else 'FAIL'} [{fix_pb_skip}] "
                f"dispatched={got_pb_skip.get('feature_id')!r}, "
                f"parked count={len(pb_parked) if isinstance(pb_parked, list) else 'N/A'}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_pb_skip}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pb_skip}] SystemExit: {exc.code}")

        # Sub-fixture 2: NO flag → terminal_reason "blocked", "parked" key ABSENT.
        fix_pb_default = "park-blocked-default-halt"
        try:
            got_pb_default = compute_state(pb_root, cloud=False, real_device=True)
            pbdef_ok = True
            if got_pb_default.get("terminal_reason") != "blocked":
                failures.append(
                    f"[{fix_pb_default}] expected terminal_reason='blocked', "
                    f"got {got_pb_default.get('terminal_reason')!r}"
                )
                pbdef_ok = False
            if "parked" in got_pb_default:
                failures.append(
                    f"[{fix_pb_default}] 'parked' key must be absent in default mode; "
                    f"got parked={got_pb_default['parked']!r}"
                )
                pbdef_ok = False
            print(
                f"  {'PASS' if pbdef_ok else 'FAIL'} [{fix_pb_default}] "
                f"default: terminal_reason={got_pb_default.get('terminal_reason')!r}, "
                f"parked key absent={('parked' not in got_pb_default)}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_pb_default}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pb_default}] SystemExit: {exc.code}")

        # Sub-fixture 3: all-parked terminal. Mark workable-feat ALSO blocked so
        # every remaining feature is parked → queue-exhausted-all-parked.
        fix_pb_allparked = "park-blocked-all-parked-terminal"
        try:
            _write_yaml_sentinel(
                pb_workable_dir / "BLOCKED.md", "blocked",
                feature_id="workable-feat", phase="Spec",
                blocked_at="2026-06-16T00:00:00Z", retry_count=0,
            )
            got_pb_all = compute_state(
                pb_root, cloud=False, real_device=True,
                park_needs_input=True, park_blocked=True,
            )
            pball_ok = True
            if got_pb_all.get("terminal_reason") != "queue-exhausted-all-parked":
                failures.append(
                    f"[{fix_pb_allparked}] expected terminal_reason="
                    f"'queue-exhausted-all-parked', got "
                    f"{got_pb_all.get('terminal_reason')!r}"
                )
                pball_ok = False
            pb_all_parked = got_pb_all.get("parked")
            if not isinstance(pb_all_parked, list) or len(pb_all_parked) < 1:
                failures.append(
                    f"[{fix_pb_allparked}] expected non-empty parked[], "
                    f"got {pb_all_parked!r}"
                )
                pball_ok = False
            print(
                f"  {'PASS' if pball_ok else 'FAIL'} [{fix_pb_allparked}] "
                f"terminal_reason={got_pb_all.get('terminal_reason')!r}, "
                f"parked count={len(pb_all_parked) if isinstance(pb_all_parked, list) else 'N/A'}"
            )
            # cleanup: remove the workable BLOCKED.md so sub-fixture 4 has a clean
            # "workable" feature to dispatch.
            (pb_workable_dir / "BLOCKED.md").unlink()
        except SystemExit as exc:
            failures.append(f"[{fix_pb_allparked}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pb_allparked}] SystemExit: {exc.code}")

        # Sub-fixture 4: dual-sentinel single-park. blocked-feat carries BOTH
        # BLOCKED.md and NEEDS_INPUT.md; under both flags it parks exactly ONCE
        # and workable-feat is dispatched.
        fix_pb_dual = "park-blocked-and-needs-input-single-park"
        try:
            (pb_blocked_dir / "NEEDS_INPUT.md").write_text(
                "---\n"
                "kind: needs-input\n"
                "feature_id: blocked-feat\n"
                "written_by: spec-phases\n"
                "decisions:\n"
                "  - Choose strategy\n"
                "date: 2026-06-16\n"
                "---\n\n# Needs Input\n",
                encoding="utf-8",
            )
            got_pb_dual = compute_state(
                pb_root, cloud=False, real_device=True,
                park_needs_input=True, park_blocked=True,
            )
            pbdual_ok = True
            if got_pb_dual.get("feature_id") != "workable-feat":
                failures.append(
                    f"[{fix_pb_dual}] expected feature_id='workable-feat', "
                    f"got {got_pb_dual.get('feature_id')!r}"
                )
                pbdual_ok = False
            pb_dual_parked = got_pb_dual.get("parked", [])
            dual_ids = [e.get("id") for e in pb_dual_parked if isinstance(e, dict)]
            if dual_ids.count("blocked-feat") != 1:
                failures.append(
                    f"[{fix_pb_dual}] blocked-feat must appear EXACTLY once in "
                    f"parked[]; got ids={dual_ids!r}"
                )
                pbdual_ok = False
            print(
                f"  {'PASS' if pbdual_ok else 'FAIL'} [{fix_pb_dual}] "
                f"dispatched={got_pb_dual.get('feature_id')!r}, "
                f"blocked-feat park count={dual_ids.count('blocked-feat')}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_pb_dual}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pb_dual}] SystemExit: {exc.code}")

        # -------------------------------------------------------------------
        # Fixture park-provisional (park-provisional-acceptance).
        #
        # Fresh root; queue:
        #   prov-feat     — carries NEEDS_INPUT.md (rich, recommendation-first)
        #   after-feat    — actionable (Draft, SPEC+RESEARCH present)
        #
        # Sub-fixtures:
        #   1 eligible-route        — divergence two-key low → __provisional_accept__
        #   2 structural-parks      — audit_divergence: structural → parked
        #   3 single-key-parks      — audit_divergence absent → parked
        #   4 two-key-mech-parks    — class:mechanical+audit_concurs → parked (D4)
        #   5 action-happy          — provisionalize_sentinel renames + Resolution
        #   6 workable-under-park   — _PROVISIONAL file: park probe dispatches the
        #                             feature itself; provisional[] lists it
        #   7 needs-ratification    — non-park probe halts on the new terminal
        #   8 needs-input-precedence— BOTH sentinels, non-park → needs-input
        #   9 validated-parks       — _PROVISIONAL + VALIDATED.md + park → parked
        #                             (sentinel_kind provisional), queue advances
        #  10 apply-pseudo-refusal  — __mark_complete__ refuses, zero writes
        #  11 flag-pairing          — park_provisional without park_needs_input
        #                             dies (SPEC D1), in-process and via CLI
        # -------------------------------------------------------------------
        pp_root = td_path / "park-provisional"
        pp_features = pp_root / "docs" / "features"
        pp_features.mkdir(parents=True, exist_ok=True)
        (pp_features / "ROADMAP.md").write_text("# Roadmap\n")
        (pp_features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "prov-feat", "name": "Provisional Feature",
                 "spec_dir": "prov-feat", "tier": 1},
                {"id": "after-feat", "name": "After Feature",
                 "spec_dir": "after-feat", "tier": 1},
            ]
        }))
        pp_prov_dir = pp_features / "prov-feat"
        pp_prov_dir.mkdir()
        (pp_prov_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (pp_prov_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (pp_prov_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
        pp_after_dir = pp_features / "after-feat"
        pp_after_dir.mkdir()
        (pp_after_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
            encoding="utf-8",
        )
        (pp_after_dir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
        (pp_after_dir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")

        def _pp_needs_input(divergence: str | None, audit_divergence: str | None,
                            extra_fm: str = "") -> str:
            fm = [
                "---",
                "kind: needs-input",
                "feature_id: prov-feat",
                "written_by: spec",
                "decisions:",
                "  - Choose default export format",
                "date: 2026-07-09",
            ]
            if divergence is not None:
                fm.append(f"divergence: {divergence}")
            if audit_divergence is not None:
                fm.append(f"audit_divergence: {audit_divergence}")
            if extra_fm:
                fm.append(extra_fm.rstrip("\n"))
            fm.append("---")
            body = (
                "\n\n# Needs Input\n\n"
                "## Decision Context\n\n"
                "### 1. Choose default export format\n\n"
                "**Problem:** The spec must pick a v1 default export format.\n\n"
                "**Options:**\n"
                "- **WAV (Recommended)** — lossless, simple decode path.\n"
                "- **MP3** — smaller files, lossy.\n\n"
                "**Recommendation:** WAV — lossless and simple.\n"
            )
            return "\n".join(fm) + body

        pp_sentinel = pp_prov_dir / "NEEDS_INPUT.md"

        # Sub-fixture 1: eligible → __provisional_accept__ route.
        fix_pp_route = "park-provisional-eligible-route"
        try:
            pp_sentinel.write_text(
                _pp_needs_input("contained", "isolated"), encoding="utf-8"
            )
            got_pp = compute_state(
                pp_root, cloud=False, real_device=True,
                park_needs_input=True, park_provisional=True,
            )
            ppr_ok = True
            if got_pp.get("sub_skill") != "__provisional_accept__":
                failures.append(
                    f"[{fix_pp_route}] expected sub_skill='__provisional_accept__', "
                    f"got {got_pp.get('sub_skill')!r}"
                )
                ppr_ok = False
            if got_pp.get("feature_id") != "prov-feat":
                failures.append(
                    f"[{fix_pp_route}] expected feature_id='prov-feat', "
                    f"got {got_pp.get('feature_id')!r}"
                )
                ppr_ok = False
            if any(e.get("id") == "prov-feat" for e in got_pp.get("parked", [])):
                failures.append(
                    f"[{fix_pp_route}] prov-feat must NOT be parked when routed"
                )
                ppr_ok = False
            print(
                f"  {'PASS' if ppr_ok else 'FAIL'} [{fix_pp_route}] "
                f"sub_skill={got_pp.get('sub_skill')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_pp_route}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_route}] SystemExit: {exc.code}")

        # Sub-fixtures 2-4: ineligible variants each PARK instead of routing.
        for fix_pp_name, div, adiv, extra in (
            ("park-provisional-structural-parks", "contained", "structural", ""),
            ("park-provisional-single-key-parks", "contained", None, ""),
            ("park-provisional-two-key-mech-parks", "isolated", "isolated",
             "class: mechanical\naudit_concurs: true"),
            # stub-origin-provisional-exclusion: an otherwise-eligible sentinel
            # (low divergence two-key + recommendation) whose decisions shaped a
            # stub-origin baseline is NEVER provisionally accepted.
            ("park-provisional-stub-origin-parks", "isolated", "isolated",
             "stub_origin: true"),
        ):
            try:
                pp_sentinel.write_text(
                    _pp_needs_input(div, adiv, extra), encoding="utf-8"
                )
                got_pp_i = compute_state(
                    pp_root, cloud=False, real_device=True,
                    park_needs_input=True, park_provisional=True,
                )
                ppi_ok = True
                if got_pp_i.get("sub_skill") == "__provisional_accept__":
                    failures.append(
                        f"[{fix_pp_name}] ineligible sentinel must NOT route "
                        "__provisional_accept__"
                    )
                    ppi_ok = False
                if not any(e.get("id") == "prov-feat"
                           for e in got_pp_i.get("parked", [])):
                    failures.append(
                        f"[{fix_pp_name}] prov-feat must be parked "
                        f"(parked={got_pp_i.get('parked')!r})"
                    )
                    ppi_ok = False
                if got_pp_i.get("feature_id") != "after-feat":
                    failures.append(
                        f"[{fix_pp_name}] expected after-feat dispatched, "
                        f"got {got_pp_i.get('feature_id')!r}"
                    )
                    ppi_ok = False
                print(f"  {'PASS' if ppi_ok else 'FAIL'} [{fix_pp_name}] parked")
            except SystemExit as exc:
                failures.append(f"[{fix_pp_name}] SystemExit: {exc.code}")
                print(f"  FAIL [{fix_pp_name}] SystemExit: {exc.code}")

        # Sub-fixture 5: provisionalize_sentinel happy path (rename + Resolution).
        fix_pp_action = "provisionalize-sentinel-action"
        try:
            pp_sentinel.write_text(
                _pp_needs_input("contained", "isolated"), encoding="utf-8"
            )
            act = lazy_core.provisionalize_sentinel(pp_sentinel, pp_root)
            ppa_ok = True
            pp_prov_file = pp_prov_dir / lazy_core.PROVISIONAL_SENTINEL
            if not act.get("ok"):
                failures.append(f"[{fix_pp_action}] refused: {act.get('refused')!r}")
                ppa_ok = False
            elif not pp_prov_file.exists() or pp_sentinel.exists():
                failures.append(
                    f"[{fix_pp_action}] rename missing: provisional exists="
                    f"{pp_prov_file.exists()}, original exists={pp_sentinel.exists()}"
                )
                ppa_ok = False
            else:
                pp_text = pp_prov_file.read_text(encoding="utf-8")
                if ("resolved_by: auto-provisional" not in pp_text
                        or "decision_commit:" not in pp_text
                        or "**Choice:** WAV" not in pp_text):
                    failures.append(
                        f"[{fix_pp_action}] Resolution block malformed"
                    )
                    ppa_ok = False
                if act.get("choices") != [{"title": "1. Choose default export format",
                                           "choice": "WAV"}]:
                    failures.append(
                        f"[{fix_pp_action}] choices={act.get('choices')!r}"
                    )
                    ppa_ok = False
            # Refusal path: a structural file refuses with zero writes.
            (pp_after_dir / "NEEDS_INPUT.md").write_text(
                _pp_needs_input("structural", "isolated").replace(
                    "feature_id: prov-feat", "feature_id: after-feat"),
                encoding="utf-8",
            )
            act2 = lazy_core.provisionalize_sentinel(
                pp_after_dir / "NEEDS_INPUT.md", pp_root
            )
            if act2.get("ok") or not act2.get("refused"):
                failures.append(
                    f"[{fix_pp_action}] structural file must refuse; got {act2!r}"
                )
                ppa_ok = False
            if (pp_after_dir / lazy_core.PROVISIONAL_SENTINEL).exists():
                failures.append(
                    f"[{fix_pp_action}] refusal must be zero-write"
                )
                ppa_ok = False
            (pp_after_dir / "NEEDS_INPUT.md").unlink()
            print(f"  {'PASS' if ppa_ok else 'FAIL'} [{fix_pp_action}]")
        except SystemExit as exc:
            failures.append(f"[{fix_pp_action}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_action}] SystemExit: {exc.code}")

        # Sub-fixture 6: _PROVISIONAL file is workable under park mode; the
        # feature itself is dispatched and provisional[] lists it.
        fix_pp_work = "park-provisional-workable-under-park"
        try:
            got_pp_w = compute_state(
                pp_root, cloud=False, real_device=True,
                park_needs_input=True,
            )
            ppw_ok = True
            if got_pp_w.get("feature_id") != "prov-feat" or got_pp_w.get("terminal_reason"):
                failures.append(
                    f"[{fix_pp_work}] expected prov-feat dispatched with no "
                    f"terminal; got feature_id={got_pp_w.get('feature_id')!r}, "
                    f"terminal={got_pp_w.get('terminal_reason')!r}"
                )
                ppw_ok = False
            pp_prov_list = got_pp_w.get("provisional", [])
            if not any(e.get("id") == "prov-feat" and
                       e.get("sentinel_kind") == "provisional"
                       for e in pp_prov_list):
                failures.append(
                    f"[{fix_pp_work}] provisional[] must list prov-feat "
                    f"(got {pp_prov_list!r})"
                )
                ppw_ok = False
            print(f"  {'PASS' if ppw_ok else 'FAIL'} [{fix_pp_work}]")
        except SystemExit as exc:
            failures.append(f"[{fix_pp_work}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_work}] SystemExit: {exc.code}")

        # Sub-fixture 7: non-park probe halts needs-ratification; no
        # provisional key leaks into non-park output.
        fix_pp_rat = "needs-ratification-non-park-halt"
        try:
            got_pp_r = compute_state(pp_root, cloud=False, real_device=True)
            pprat_ok = True
            if got_pp_r.get("terminal_reason") != "needs-ratification":
                failures.append(
                    f"[{fix_pp_rat}] expected terminal_reason='needs-ratification', "
                    f"got {got_pp_r.get('terminal_reason')!r}"
                )
                pprat_ok = False
            if "provisional" in got_pp_r or "parked" in got_pp_r:
                failures.append(
                    f"[{fix_pp_rat}] provisional/parked keys must be absent "
                    "from non-park output"
                )
                pprat_ok = False
            print(
                f"  {'PASS' if pprat_ok else 'FAIL'} [{fix_pp_rat}] "
                f"terminal_reason={got_pp_r.get('terminal_reason')!r}"
            )
        except SystemExit as exc:
            failures.append(f"[{fix_pp_rat}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_rat}] SystemExit: {exc.code}")

        # Sub-fixture 8: BOTH NEEDS_INPUT.md and _PROVISIONAL, non-park →
        # needs-input outranks needs-ratification (SPEC D5).
        fix_pp_prec = "needs-input-outranks-ratification"
        try:
            pp_sentinel.write_text(
                _pp_needs_input("contained", "isolated"), encoding="utf-8"
            )
            got_pp_p = compute_state(pp_root, cloud=False, real_device=True)
            pprec_ok = got_pp_p.get("terminal_reason") == "needs-input"
            if not pprec_ok:
                failures.append(
                    f"[{fix_pp_prec}] expected 'needs-input', "
                    f"got {got_pp_p.get('terminal_reason')!r}"
                )
            pp_sentinel.unlink()
            print(f"  {'PASS' if pprec_ok else 'FAIL'} [{fix_pp_prec}]")
        except SystemExit as exc:
            failures.append(f"[{fix_pp_prec}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_prec}] SystemExit: {exc.code}")

        # Sub-fixture 9: _PROVISIONAL + VALIDATED.md under park → parked for
        # ratification (sentinel_kind provisional), queue advances.
        fix_pp_val = "park-provisional-validated-parks"
        try:
            _write_yaml_sentinel(
                pp_prov_dir / "VALIDATED.md", "validated",
                feature_id="prov-feat", date="2026-07-09",
                mcp_scenarios=["s1"], result="all-passing",
            )
            got_pp_v = compute_state(
                pp_root, cloud=False, real_device=True,
                park_needs_input=True,
            )
            ppv_ok = True
            if got_pp_v.get("feature_id") != "after-feat":
                failures.append(
                    f"[{fix_pp_val}] expected after-feat dispatched, "
                    f"got {got_pp_v.get('feature_id')!r}"
                )
                ppv_ok = False
            if not any(e.get("id") == "prov-feat" and
                       e.get("sentinel_kind") == "provisional"
                       for e in got_pp_v.get("parked", [])):
                failures.append(
                    f"[{fix_pp_val}] prov-feat must be parked with "
                    f"sentinel_kind='provisional' (parked={got_pp_v.get('parked')!r})"
                )
                ppv_ok = False
            print(f"  {'PASS' if ppv_ok else 'FAIL'} [{fix_pp_val}]")
        except SystemExit as exc:
            failures.append(f"[{fix_pp_val}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_val}] SystemExit: {exc.code}")

        # Sub-fixture 10: apply_pseudo __mark_complete__ refuses on an
        # unratified provisional sentinel, zero writes.
        #
        # Hermetically isolate LAZY_STATE_DIR for the duration of this ONE call
        # (state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker):
        # apply_pseudo() unconditionally calls refuse_if_cycle_active(), which
        # honors the AMBIENT LAZY_STATE_DIR (or the real per-repo keyed state
        # dir when unset) — NOT this fixture's own pp_root temp dir. Without
        # isolation, running --test from inside a genuinely-live cycle
        # (exactly the scenario a hardening/cycle subagent is in) spuriously
        # FAILs this fixture on an unrelated SystemExit(3) refusal, masking its
        # actual assertion (the provisional-sentinel refusal). Mirrors the
        # save/restore pattern used by sibling fixture groups elsewhere in this
        # file (e.g. the LAZY_STATE_DIR save/restore around lines ~7057/7253).
        fix_pp_gate = "apply-pseudo-provisional-refusal"
        _ppg_prev_env = os.environ.get("LAZY_STATE_DIR")
        try:
            with tempfile.TemporaryDirectory() as _ppg_td:
                os.environ["LAZY_STATE_DIR"] = _ppg_td
                res_gate = lazy_core.apply_pseudo(
                    pp_root, "__mark_complete__", pp_prov_dir
                )
            ppg_ok = True
            if res_gate.get("ok") or "provisional" not in str(res_gate.get("refused", "")):
                failures.append(
                    f"[{fix_pp_gate}] expected provisional refusal, got {res_gate!r}"
                )
                ppg_ok = False
            if (pp_prov_dir / "COMPLETED.md").exists():
                failures.append(f"[{fix_pp_gate}] refusal must write nothing")
                ppg_ok = False
            print(f"  {'PASS' if ppg_ok else 'FAIL'} [{fix_pp_gate}]")
        except SystemExit as exc:
            failures.append(f"[{fix_pp_gate}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_pp_gate}] SystemExit: {exc.code}")
        finally:
            if _ppg_prev_env is None:
                os.environ.pop("LAZY_STATE_DIR", None)
            else:
                os.environ["LAZY_STATE_DIR"] = _ppg_prev_env

        # -------------------------------------------------------------------
        # Walk-level convergence (mark-complete-partial-apply-noop-unrecoverable).
        # A crash between the COMPLETED.md receipt write and the SPEC status flip
        # leaves a receipt-present + Status-In-progress dir. compute_state STILL
        # routes __mark_complete__ (the item is not CLAIMED: Status not Complete,
        # ROADMAP unstruck). Before the fix, apply_pseudo noop'd forever against
        # that state — the same Step-10 route computed every probe, an
        # unrecoverable loop. Now apply_pseudo RESUMES and converges, after which
        # compute_state no longer routes __mark_complete__ (the loop is broken).
        # -------------------------------------------------------------------
        fix_res = "resume-partial-apply-walk-convergence"
        try:
            rp_root = td_path / "resume-partial"
            rp_feat = rp_root / "docs" / "features"
            rp_feat.mkdir(parents=True, exist_ok=True)
            (rp_feat / "queue.json").write_text(json.dumps({
                "queue": [
                    {"id": "feat-rp", "name": "Feature RP",
                     "spec_dir": "feat-rp", "tier": 1}
                ]
            }))
            (rp_feat / "ROADMAP.md").write_text(
                "# Roadmap\n\n- feat-rp: resume me\n"
            )
            rp = rp_feat / "feat-rp"
            rp.mkdir()
            # The crash window: receipt written, Status still In-progress,
            # VALIDATED.md + RETRO_DONE.md present, phases complete, queue entry
            # present (the exact partial state the SPEC's trace materializes).
            (rp / "SPEC.md").write_text(
                "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n"
            )
            (rp / "RESEARCH.md").write_text("# R\n")
            (rp / "RESEARCH_SUMMARY.md").write_text("# S\n")
            (rp / "PHASES.md").write_text("# Phases\n\n### Phase 1\n- [x] Done\n")
            _write_yaml_sentinel(
                rp / "RETRO_DONE.md", "retro-done",
                feature_id="feat-rp", date="2026-05-30",
                rounds=1, retro_plans=["retro-1-feat-rp.md"],
                mcp_validation_status="complete",
            )
            _write_yaml_sentinel(
                rp / "VALIDATED.md", "validated",
                feature_id="feat-rp", date="2026-05-30",
                mcp_scenarios=["AQ-TE-05"], result="all-passing",
            )
            _write_yaml_sentinel(
                rp / "COMPLETED.md", "completed",
                feature_id="feat-rp", date="2026-05-30", provenance="gated",
            )
            rp_ok = True
            # (1) The partial dir STILL routes to __mark_complete__ (routing is
            # correct — the defect was apply_pseudo noop'ing against this route).
            got_pre = compute_state(rp_root, cloud=False, real_device=True)
            if got_pre.get("sub_skill") != "__mark_complete__":
                failures.append(
                    f"[{fix_res}] partial dir must route __mark_complete__; got "
                    f"{got_pre.get('sub_skill')!r} / {got_pre.get('terminal_reason')!r}"
                )
                rp_ok = False
            # (2) apply_pseudo RESUMES (does not noop) and converges.
            #
            # Hermetically isolate LAZY_STATE_DIR for this ONE call — same
            # rationale as the apply-pseudo-provisional-refusal fixture just
            # above (state-script-test-runner-crashes-on-systemexit-from-live-
            # cycle-marker): apply_pseudo() unconditionally calls
            # refuse_if_cycle_active(), which honors the AMBIENT LAZY_STATE_DIR,
            # not this fixture's own rp_root temp dir. Discovered as a SECOND
            # instance of the same defect class during this bug's close-out
            # verification (this fixture postdates the bug's original scan).
            _rp_prev_env = os.environ.get("LAZY_STATE_DIR")
            try:
                with tempfile.TemporaryDirectory() as _rp_td:
                    os.environ["LAZY_STATE_DIR"] = _rp_td
                    res = lazy_core.apply_pseudo(
                        rp_root, "__mark_complete__", rp, feature_id="feat-rp",
                    )
            finally:
                if _rp_prev_env is None:
                    os.environ.pop("LAZY_STATE_DIR", None)
                else:
                    os.environ["LAZY_STATE_DIR"] = _rp_prev_env
            if not res.get("resumed"):
                failures.append(f"[{fix_res}] expected resumed=True, got {res!r}")
                rp_ok = False
            if "**Status:** Complete" not in (rp / "SPEC.md").read_text(encoding="utf-8"):
                failures.append(f"[{fix_res}] resume did not flip SPEC to Complete")
                rp_ok = False
            # (3) After convergence, compute_state NO LONGER routes __mark_complete__
            # (the same Step-10 route is not computed twice — loop broken).
            got_post = compute_state(rp_root, cloud=False, real_device=True)
            if got_post.get("sub_skill") == "__mark_complete__":
                failures.append(
                    f"[{fix_res}] repaired dir must NOT re-route __mark_complete__ "
                    f"(unrecoverable loop unbroken): {got_post!r}"
                )
                rp_ok = False
            print(f"  {'PASS' if rp_ok else 'FAIL'} [{fix_res}]")
        except SystemExit as exc:
            failures.append(f"[{fix_res}] SystemExit: {exc.code}")
            print(f"  FAIL [{fix_res}] SystemExit: {exc.code}")

        # Sub-fixture 11: flag pairing (SPEC D1) — in-process _die (SystemExit 2)
        # and CLI exit 2.
        fix_pp_flag = "park-provisional-flag-pairing"
        ppf_ok = True
        try:
            compute_state(
                pp_root, cloud=False, real_device=True, park_provisional=True
            )
            failures.append(f"[{fix_pp_flag}] bare park_provisional must die")
            ppf_ok = False
        except SystemExit as exc:
            if exc.code != 2:
                failures.append(
                    f"[{fix_pp_flag}] expected exit 2, got {exc.code!r}"
                )
                ppf_ok = False
        r_flag = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--park-provisional", "--repo-root", str(pp_root)],
            capture_output=True, text=True,
        )
        if r_flag.returncode != 2:
            failures.append(
                f"[{fix_pp_flag}] CLI bare --park-provisional must exit 2; "
                f"got {r_flag.returncode}"
            )
            ppf_ok = False
        print(f"  {'PASS' if ppf_ok else 'FAIL'} [{fix_pp_flag}]")

        # -------------------------------------------------------------------
        # Fixture: cycle-marker-mutation guard (cycle-subagent-runs-orchestrator-
        # work Phase 2, KEYSTONE). A SUBAGENT-context --cycle-end (no
        # LAZY_ORCHESTRATOR, marker on disk) is REFUSED (exit 3) and the marker
        # file STILL EXISTS afterward (zero side effects — the friction check +
        # clear never run). The ORCHESTRATOR --cycle-end (LAZY_ORCHESTRATOR=1)
        # clears the marker and exits 0. Same pair for --cycle-begin. Driven via
        # subprocess so the actual CLI handler (guard → handler body) runs.
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
                json.dumps({"feature_id": "feat-cmg", "nonce": "n", "kind": "real",
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
            [sys.executable, _this_script, "--cycle-begin", "--feature-id", "feat-cmg",
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
            [sys.executable, _this_script, "--cycle-begin", "--feature-id", "feat-cmg2",
             "--nonce", "cafe", "--sub-skill", "execute-plan", "--repo-root", str(td_path)],
            capture_output=True, text=True, env=_cmg_env(orchestrator=True),
        )
        if r.returncode != 0:
            failures.append(f"[{fix_cmg}] orchestrator --cycle-begin must exit 0; got {r.returncode}")
            cmg_ok = False
        if cmg_marker.exists():
            try:
                _ovr = json.loads(cmg_marker.read_text(encoding="utf-8"))
                if _ovr.get("feature_id") != "feat-cmg2":
                    failures.append(f"[{fix_cmg}] orchestrator --cycle-begin must overwrite the marker")
                    cmg_ok = False
            except (OSError, json.JSONDecodeError):
                pass
        print(f"  {'PASS' if cmg_ok else 'FAIL'} [{fix_cmg}] subagent cycle-end/begin refused, orchestrator allowed")

        # -------------------------------------------------------------------
        # Fixture: --cycle-begin git-consistency reconciliation (long-build-and-
        # runtime-ownership Phase 4 / M5 Detect). An orchestrator --cycle-begin
        # in a real git tree carrying a STALE pre-boot .git/index.lock (mtime far
        # in the past) + an uncommitted staging delta REMOVES the lock and
        # git-cleans the staging dir, surfacing git_consistency_reconciliation in
        # the JSON. The boot stamp comes from a live run marker's started_at; the
        # stale lock predates it. Driven via subprocess so the real handler runs.
        # -------------------------------------------------------------------
        fix_recon = "cycle-begin-git-consistency-reconciliation"
        recon_ok = True
        try:
            recon_state = td_path / "recon-state"
            recon_state.mkdir(parents=True, exist_ok=True)
            recon_repo = td_path / "recon-repo"
            recon_repo.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "-C", str(recon_repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(recon_repo), "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", str(recon_repo), "config", "user.name", "t"], check=True)
            (recon_repo / "seed.txt").write_text("seed", encoding="utf-8")
            subprocess.run(["git", "-C", str(recon_repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(recon_repo), "commit", "-q", "-m", "seed"], check=True)
            # A live run marker whose started_at is AFTER the stale lock mtime.
            run_marker_path = recon_state / "lazy-run-marker.json"
            run_marker_path.write_text(
                json.dumps({"pipeline": "feature", "repo_root": str(recon_repo),
                            "session_id": None,
                            "started_at": "2099-01-01T00:00:00Z"}, indent=2) + "\n",
                encoding="utf-8",
            )
            recon_lock = recon_repo / ".git" / "index.lock"
            recon_lock.write_text("", encoding="utf-8")
            os.utime(recon_lock, (1_000.0, 1_000.0))  # stale (predates boot)
            recon_staging = recon_repo / "target" / "release_staging"
            recon_staging.mkdir(parents=True, exist_ok=True)
            (recon_staging / "torn.bin").write_text("partial", encoding="utf-8")

            recon_env = {k: v for k, v in os.environ.items()
                         if k not in ("LAZY_CYCLE_SUBAGENT",)}
            recon_env["LAZY_STATE_DIR"] = str(recon_state)
            recon_env["LAZY_ORCHESTRATOR"] = "1"
            r = subprocess.run(
                [sys.executable, _this_script, "--cycle-begin",
                 "--feature-id", "feat-recon", "--nonce", "abad1dea",
                 "--sub-skill", "execute-plan",
                 "--repo-root", str(recon_repo)],
                capture_output=True, text=True, env=recon_env,
            )
            if r.returncode != 0:
                failures.append(f"[{fix_recon}] --cycle-begin must exit 0; got {r.returncode}: {r.stderr}")
                recon_ok = False
            if recon_lock.exists():
                failures.append(f"[{fix_recon}] stale pre-boot index.lock must be removed")
                recon_ok = False
            if (recon_staging / "torn.bin").exists():
                failures.append(f"[{fix_recon}] staging partial must be git-cleaned")
                recon_ok = False
            try:
                out_json = json.loads(r.stdout)
                rec = out_json.get("git_consistency_reconciliation")
                if not (isinstance(rec, dict) and rec.get("removed_lock") is True):
                    failures.append(f"[{fix_recon}] JSON must surface git_consistency_reconciliation.removed_lock")
                    recon_ok = False
            except (json.JSONDecodeError, TypeError):
                failures.append(f"[{fix_recon}] --cycle-begin stdout must be JSON; got {r.stdout!r}")
                recon_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_recon}] unexpected error: {exc!r}")
            recon_ok = False
        print(f"  {'PASS' if recon_ok else 'FAIL'} [{fix_recon}] stale pre-boot index.lock reconciled at --cycle-begin")

        # -------------------------------------------------------------------
        # Fixture: --cycle-begin --kind real requires --sub-skill
        # (adhoc-cycle-begin-real-requires-sub-skill). A --kind real dispatch
        # that omits --sub-skill must be refused (non-zero exit, no marker
        # mutation) BEFORE the marker is ever written; --kind meta remains
        # exempt and still succeeds without --sub-skill. Driven via subprocess
        # so the real CLI handler runs.
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
                 "--feature-id", "feat-rrs", "--nonce", "deadbeef",
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
                 "--feature-id", "feat-rrs", "--nonce", "cafefeed",
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
                 "--feature-id", "feat-rrs", "--nonce", "abad1dea",
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
        # Fixture: --reorder-queue (no-sanctioned-queue-reorder-command P2).
        # Operator-only / out-of-cycle queue mutation on docs/features/queue.json,
        # gated by refuse_if_cycle_active like --enqueue-adhoc. Driven via
        # subprocess so the real CLI handler (gate → parse → reorder_queue) runs.
        # -------------------------------------------------------------------
        fix_ro = "reorder-queue"
        ro_ok = True
        _ro_script = str(Path(__file__).resolve())

        def _ro_repo(ids: list) -> "Path":
            """Make a fresh repo with docs/features/queue.json carrying `ids`."""
            import uuid as _uuid
            root = td_path / f"ro-{_uuid.uuid4().hex[:8]}"
            qdir = root / "docs" / "features"
            qdir.mkdir(parents=True, exist_ok=True)
            (qdir / "queue.json").write_text(
                json.dumps({"queue": [{"id": i, "name": i} for i in ids]},
                           indent=2) + "\n",
                encoding="utf-8",
            )
            return root

        def _ro_ids(root: "Path") -> list:
            data = json.loads(
                (root / "docs" / "features" / "queue.json").read_text(encoding="utf-8"))
            return [e["id"] for e in data["queue"]]

        def _ro_env(state_dir: "Path", *, cycle_marker: bool) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(state_dir)
            if cycle_marker:
                state_dir.mkdir(parents=True, exist_ok=True)
                (state_dir / "lazy-cycle-active.json").write_text(
                    json.dumps({"feature_id": "feat-ro", "nonce": "n",
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
        if r.returncode != 0:
            failures.append(f"[{fix_ro}] --to tail must exit 0; got {r.returncode}: {r.stderr}")
            ro_ok = False
        if _ro_ids(r_root) != ["b", "c", "a"]:
            failures.append(f"[{fix_ro}] --to tail wrong order: {_ro_ids(r_root)}")
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
        # (5) missing-entry → _die (exit 2)
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "tail", item="zzz")
        if r.returncode != 2:
            failures.append(f"[{fix_ro}] missing-entry must exit 2 (_die); got {r.returncode}")
            ro_ok = False
        if _ro_ids(r_root) != ["a", "b", "c"]:
            failures.append(f"[{fix_ro}] missing-entry must NOT mutate the queue")
            ro_ok = False
        # (6) cycle-active refusal → exit 3, queue unchanged
        r_root = _ro_repo(["a", "b", "c"])
        r = _ro_run(r_root, "tail", cycle_marker=True)
        if r.returncode != 3:
            failures.append(f"[{fix_ro}] cycle-active must refuse exit 3; got {r.returncode}")
            ro_ok = False
        if _ro_ids(r_root) != ["a", "b", "c"]:
            failures.append(f"[{fix_ro}] cycle-active refusal must leave queue UNCHANGED")
            ro_ok = False
        # (7) idempotent no-op (already at head) → exit 0, file byte-stable
        r_root = _ro_repo(["a", "b", "c"])
        _ro_qp = r_root / "docs" / "features" / "queue.json"
        _ro_before = _ro_qp.read_bytes()
        r = _ro_run(r_root, "head")  # 'a' already at head
        if r.returncode != 0:
            failures.append(f"[{fix_ro}] idempotent no-op must exit 0; got {r.returncode}")
            ro_ok = False
        if _ro_qp.read_bytes() != _ro_before:
            failures.append(f"[{fix_ro}] idempotent no-op must leave the file byte-stable")
            ro_ok = False
        print(f"  {'PASS' if ro_ok else 'FAIL'} [{fix_ro}] reorder tail/head/index/remove/missing/cycle-active/no-op")

        # -------------------------------------------------------------------
        # Fixture: harness-telemetry-ledger Phase 2 — chokepoint emission.
        # (a) bracket: --run-start → --cycle-begin → --cycle-end → --run-end ⇒
        #     four envelope-valid lazy-telemetry.jsonl lines sharing ONE run_id.
        # (b) dispatch/halt: --emit-prompt under a marker emits `dispatch`
        #     (+ `halt` when terminal_reason is in the halt set); output JSON
        #     gains NO new keys.
        # (c) read-path purity: a bare probe with NO marker creates neither the
        #     state dir nor a ledger; with a marker it appends NOTHING.
        # (d) refusal capture: subagent --apply-pseudo ⇒ exit 3 + ONE
        #     containment-refusal line (its only side effect beyond stderr);
        #     --verify-ledger on a dirty/non-git tree ⇒ exit 1 + gate-refusal.
        # (e) D5-B cloud flush: a --cloud run's --run-end lands the committed
        #     docs/telemetry/cloud/<run_id colon-stripped>.jsonl segment and
        #     surfaces telemetry_flushed in the JSON.
        # Driven via subprocess so the real CLI handlers run; hermetic via
        # isolated LAZY_STATE_DIR dirs (never the live ~/.claude/state/).
        # -------------------------------------------------------------------
        fix_tl = "telemetry-ledger-chokepoints"
        tl_ok = True
        _tl_script = str(Path(__file__).resolve())
        _TL_LEDGER = "lazy-telemetry.jsonl"

        def _tl_env(state_dir: "Path", *, orchestrator: bool = True) -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(state_dir)
            if orchestrator:
                e["LAZY_ORCHESTRATOR"] = "1"
            return e

        def _tl_events(state_dir: "Path") -> list:
            ledger = state_dir / _TL_LEDGER
            if not ledger.exists():
                return []
            out = []
            for line in ledger.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
            return out

        try:
            # (a) full bracket — one run_id across all four events.
            tl_state = td_path / "tl-state"
            tl_state.mkdir(parents=True, exist_ok=True)
            tl_repo = td_path / "tl-repo"
            tl_repo.mkdir(parents=True, exist_ok=True)
            for cmd in (
                ["--run-start"],
                ["--cycle-begin", "--feature-id", "feat-tl", "--nonce", "abc123",
                 "--kind", "real", "--sub-skill", "execute-plan"],
                ["--cycle-end"],
                # --efficacy-skip-authorized: this hermetic bracket fixture does
                # not run the efficacy/canary/incident trio, so it authorizes
                # skipping the efficacy-flush gate (the gate is exercised
                # dedicated in test_lazy_core.py).
                ["--run-end", "--reason", "terminal",
                 "--terminal-reason", "all-features-complete",
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
                if ev[0].get("pipeline") != "feature":
                    failures.append(f"[{fix_tl}] pipeline must be 'feature': {ev[0]}")
                    tl_ok = False
                if ev[1].get("item_id") != "feat-tl" or ev[1]["data"].get("sub_skill") != "execute-plan":
                    failures.append(f"[{fix_tl}] cycle-begin item/sub_skill wrong: {ev[1]}")
                    tl_ok = False

            # (b) dispatch + halt at --emit-prompt (halt fixture → blocked).
            tl_state_b = td_path / "tl-state-b"
            tl_state_b.mkdir(parents=True, exist_ok=True)
            halt_root = _build_fixture(td_path, "blocker")
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
                if (disp.get("item_id") != "feat-b"
                        or disp["data"].get("terminal_reason") != "blocked"):
                    failures.append(f"[{fix_tl}] dispatch payload wrong: {disp}")
                    tl_ok = False
                if ev_b[2]["data"].get("terminal_reason") != "blocked":
                    failures.append(f"[{fix_tl}] halt payload wrong: {ev_b[2]}")
                    tl_ok = False

            # (c) read-path purity — no marker: bare probe creates NOTHING.
            tl_state_c = td_path / "tl-state-c"  # deliberately NOT created
            pure_root = _build_fixture(td_path, "all-complete")
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(pure_root)],
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
                [sys.executable, _tl_script, "--repo-root", str(pure_root)],
                capture_output=True, text=True,
                env=_tl_env(tl_state_b, orchestrator=False),
            )
            if (tl_state_b / _TL_LEDGER).read_bytes() != before:
                failures.append(f"[{fix_tl}] bare probe under a marker must append NOTHING")
                tl_ok = False

            # (d1) subagent --apply-pseudo ⇒ exit 3 + containment-refusal line.
            subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--cycle-begin", "--feature-id", "feat-b", "--nonce", "beef",
                 "--kind", "real", "--sub-skill", "execute-plan"],
                capture_output=True, text=True, env=_tl_env(tl_state_b),
            )
            n_before = len(_tl_events(tl_state_b))
            r = subprocess.run(
                [sys.executable, _tl_script, "--repo-root", str(halt_root),
                 "--apply-pseudo", "__mark_complete__",
                 str(halt_root / "docs" / "features" / "feat-b" / "SPEC.md")],
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
                 str(halt_root / "docs" / "features" / "feat-b" / "SPEC.md")],
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

            # (e) D5-B cloud flush at --run-end.
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
                 "--terminal-reason", "cloud-queue-exhausted",
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
                else:
                    seg_events = [json.loads(l) for l in
                                  seg.read_text(encoding="utf-8").splitlines() if l.strip()]
                    if [e.get("event") for e in seg_events] != ["run-start", "run-end"]:
                        failures.append(
                            f"[{fix_tl}] cloud segment events wrong: "
                            f"{[e.get('event') for e in seg_events]}"
                        )
                        tl_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_tl}] unexpected error: {exc!r}")
            tl_ok = False
        print(f"  {'PASS' if tl_ok else 'FAIL'} [{fix_tl}] bracket/dispatch/purity/refusal/cloud-flush emission")

        # -------------------------------------------------------------------
        # Fixture: --cycle-end commit-bracket append is FAIL-OPEN
        # (code-doc-provenance-linkage Phase 1 / D4-A). A directory squatting on
        # the ledger filename makes the bracket append unwritable; the
        # orchestrator --cycle-end must STILL exit 0 and clear the marker (the
        # bookkeeping never blocks the clear), and the JSON carries no
        # commit_bracket key (the append honestly reported nothing recorded).
        # Driven via subprocess so the real handler (friction check → bracket →
        # clear) runs against a real git bracket (begin → one commit → end).
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
            r = subprocess.run(
                [sys.executable, _this_script, "--cycle-begin",
                 "--feature-id", "feat-cbfo", "--nonce", "beef",
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
                [sys.executable, _this_script, "--cycle-end",
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

        # Fixture: parallel-worktree-batch-execution — lane markers (D2-A).
        # (a) --run-start --parent-run stamps the lane marker with the parent
        #     identity, born owner-bound, carrying its per-lane --max-cycles
        #     budget slice (D6 — the lane self-limits if the coordinator dies).
        # (b) rogue second --run-start at the lane root (no checkpoint) →
        #     exit 3, lane marker intact (arbitration extended, not weakened).
        # (c) malformed --parent-run → exit 2, ZERO side effects (no marker).
        # (d) containment in-lane (D9): subagent --run-end at the lane state
        #     dir → exit 3; the lane marker survives.
        # (e) serial --run-start (no flag) mints parent_run: null (stable
        #     always-minted key — serial byte-shape identity).
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

        # -------------------------------------------------------------------
        # Fixture: parallel-worktree-batch-execution — per-lane friction
        # isolation (D9's one new obligation). Two lanes = two state dirs +
        # two real git repos, each with its own open cycle bracket. A commit
        # landing in lane B while lane A's bracket is open must NOT trip lane
        # A's --cycle-end friction detector (per-lane HEAD snapshots never
        # cross-trip), and lane B's own single commit stays within budget.
        # -------------------------------------------------------------------
        fix_lf = "lane-friction-no-cross-trip"
        lf_ok = True
        _lf_script = str(Path(__file__).resolve())

        def _lf_env(state_dir: "Path") -> dict:
            e = {k: v for k, v in os.environ.items()
                 if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
            e["LAZY_STATE_DIR"] = str(state_dir)
            e["LAZY_ORCHESTRATOR"] = "1"
            # Deterministic git identity for the fixture repos' commits.
            e.update({
                "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "f@x",
                "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "f@x",
            })
            return e

        def _lf_git(cwd: "Path", *gargs: str) -> None:
            subprocess.run(
                ["git", "-C", str(cwd)] + list(gargs),
                check=True, capture_output=True, env=_lf_env(cwd),
            )

        try:
            lanes_lf = {}
            for lane_name in ("a", "b"):
                repo_lf = td_path / f"lf-repo-{lane_name}"
                state_lf = td_path / f"lf-state-{lane_name}"
                repo_lf.mkdir(parents=True, exist_ok=True)
                state_lf.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "init", "-q", "-b", "main", str(repo_lf)],
                    check=True, capture_output=True, env=_lf_env(repo_lf),
                )
                (repo_lf / "f.txt").write_text("base\n", encoding="utf-8")
                _lf_git(repo_lf, "add", "f.txt")
                _lf_git(repo_lf, "commit", "-q", "-m", "base")
                lanes_lf[lane_name] = (repo_lf, state_lf)
                for cmd in (
                    ["--run-start", "--session-id", "coordinator-sess",
                     "--max-cycles", "4"],
                    ["--cycle-begin", "--feature-id", f"feat-{lane_name}",
                     "--nonce", "abc123", "--kind", "real",
                     "--sub-skill", "execute-plan"],
                ):
                    r = subprocess.run(
                        [sys.executable, _lf_script,
                         "--repo-root", str(repo_lf)] + cmd,
                        capture_output=True, text=True, env=_lf_env(state_lf),
                    )
                    if r.returncode != 0:
                        failures.append(
                            f"[{fix_lf}] lane {lane_name} {cmd[0]} must exit 0; "
                            f"got {r.returncode}: {r.stderr[:200]}"
                        )
                        lf_ok = False
            # Sibling activity: lane B's subagent lands a commit while BOTH
            # brackets are open.
            repo_b, state_b = lanes_lf["b"]
            (repo_b / "f.txt").write_text("lane-b work\n", encoding="utf-8")
            _lf_git(repo_b, "commit", "-q", "-am", "lane-b cycle work")
            # Lane A's cycle-end: HEAD(A) never moved — the sibling commit in
            # B must NOT cross-trip A's detector.
            repo_a, state_a = lanes_lf["a"]
            r = subprocess.run(
                [sys.executable, _lf_script, "--repo-root", str(repo_a),
                 "--cycle-end"],
                capture_output=True, text=True, env=_lf_env(state_a),
            )
            out_a = json.loads(r.stdout) if r.stdout else {}
            if r.returncode != 0 or out_a.get("cycle_marker_cleared") is not True \
                    or "process_friction" in out_a:
                failures.append(
                    f"[{fix_lf}] lane A --cycle-end must clear with NO friction "
                    f"despite lane B's commit; got rc={r.returncode} {out_a!r}"
                )
                lf_ok = False
            # Lane B's own cycle-end: one commit on an execute-plan bracket is
            # within budget — no friction on the lane that DID the work either.
            r = subprocess.run(
                [sys.executable, _lf_script, "--repo-root", str(repo_b),
                 "--cycle-end"],
                capture_output=True, text=True, env=_lf_env(state_b),
            )
            out_b = json.loads(r.stdout) if r.stdout else {}
            if r.returncode != 0 or out_b.get("cycle_marker_cleared") is not True \
                    or "process_friction" in out_b:
                failures.append(
                    f"[{fix_lf}] lane B --cycle-end (1 commit, execute-plan "
                    f"budget) must clear with NO friction; got rc={r.returncode} "
                    f"{out_b!r}"
                )
                lf_ok = False
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{fix_lf}] unexpected error: {exc!r}")
            lf_ok = False
        print(f"  {'PASS' if lf_ok else 'FAIL'} [{fix_lf}] per-lane cycle-end HEAD snapshots never cross-trip")


    # -----------------------------------------------------------------------
    # operator-halt-notifications Phase 2 — call-site wiring fixture.
    # Drives main() IN-PROCESS (patched argv + captured stdout) against a
    # needs-input halt with a fake config (LAZY_NOTIFY_URL) and a
    # monkeypatched module-level ntfy sender, asserting the PRODUCTION
    # binding end-to-end: the FIRST probe pages exactly once, the SECOND
    # probe dedups on the sentinel identity (zero further sends), and a
    # LAZY_NOTIFY_DISABLE=1 probe is byte-identical to the deduped probe.
    # Hermetic: LAZY_STATE_DIR temp dir; env, sender, argv, and the active-
    # repo binding are all restored.
    # -----------------------------------------------------------------------
    fix_nh = "notify-halt-call-site"
    nh_ok = True
    try:
        import io as _nh_io
        with tempfile.TemporaryDirectory(prefix="lazy-notify-fixture-") as nh_td:
            nh_root = Path(nh_td) / "repo"
            nh_feat = nh_root / "docs" / "features" / "feat-nh"
            nh_feat.mkdir(parents=True)
            (nh_root / "docs" / "features" / "queue.json").write_text(json.dumps({
                "queue": [{"id": "feat-nh", "name": "Notify Halt",
                           "spec_dir": "feat-nh", "tier": 1}]
            }), encoding="utf-8")
            (nh_root / "docs" / "features" / "ROADMAP.md").write_text(
                "# Roadmap\n", encoding="utf-8")
            (nh_feat / "SPEC.md").write_text(
                "# Notify Halt\n\n**Status:** Draft\n", encoding="utf-8")
            (nh_feat / "NEEDS_INPUT.md").write_text(
                "---\nkind: needs-input\nfeature_id: feat-nh\nwritten_by: spec\n"
                "decisions:\n  - Which channel?\ndate: 2026-07-04\n---\nbody\n",
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
                sys.argv = ["lazy-state.py", "--repo-root", str(nh_root)]
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
                if st1.get("terminal_reason") != "needs-input":
                    failures.append(
                        f"[{fix_nh}] expected terminal_reason='needs-input', "
                        f"got {st1.get('terminal_reason')!r}")
                    nh_ok = False
                if len(nh_sends) != 1:
                    failures.append(
                        f"[{fix_nh}] first probe must page exactly once, "
                        f"got {len(nh_sends)} send(s)")
                    nh_ok = False
                else:
                    nh_url, nh_title, nh_body, _nh_link = nh_sends[0]
                    if nh_url != "https://ntfy.example/fixture-topic":
                        failures.append(
                            f"[{fix_nh}] configured topic URL must be threaded "
                            f"to the sender, got {nh_url!r}")
                        nh_ok = False
                    if not nh_title.startswith("NEEDS INPUT"):
                        failures.append(
                            f"[{fix_nh}] title must be notify_message verbatim, "
                            f"got {nh_title!r}")
                        nh_ok = False
                    if "1. Which channel?" not in nh_body:
                        failures.append(
                            f"[{fix_nh}] body must carry the decisions "
                            f"one-liner, got {nh_body!r}")
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
    print(f"  {'PASS' if nh_ok else 'FAIL'} [{fix_nh}] halt + fake sender: one page, dedup on re-probe, kill switch inert")

    # -------------------------------------------------------------------
    # hardening-intervention-records-unmeasurable-or-missing WU-2 (RED):
    # --record-intervention CLI reject + hardening hard-fail. These three
    # fixtures pin the NEW validation/reject step the handler does not yet
    # have (lazy-state.py:12469, `if args.record_intervention:`) — driven
    # via subprocess so the real CLI handler (guard -> validation -> write)
    # runs, each against its OWN hermetic temp repo_root + temp
    # LAZY_STATE_DIR (immune to any ambient run/cycle marker; mirrors the
    # cycle-marker-mutation-guard fixture's `_cmg_env` isolation).
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
    with tempfile.TemporaryDirectory(prefix="lazy-ri1-repo-") as ri1_repo_td, \
            tempfile.TemporaryDirectory(prefix="lazy-ri1-state-") as ri1_state_td:
        ri1_repo = Path(ri1_repo_td)
        ri1_id = "harden-ri1-undeclared"
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
    # 0, record written with target_signal: undeclared. This is a
    # non-regression guard for the escape hatch and MAY already be green
    # today (record_intervention already accepts "undeclared" — the
    # validator never rejects it); still authored so WU-2 cannot
    # regress it.
    fix_ri2 = "record-intervention-hardening-undeclared-explicit-ok"
    ri2_ok = True
    with tempfile.TemporaryDirectory(prefix="lazy-ri2-repo-") as ri2_repo_td, \
            tempfile.TemporaryDirectory(prefix="lazy-ri2-state-") as ri2_state_td:
        ri2_repo = Path(ri2_repo_td)
        ri2_id = "harden-ri2-explicit-undeclared"
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

    # Sub-fixture 3: an unknown event: type (default --pipeline feature)
    # -> EXPECT exit 1, stderr naming the valid vocabulary set, no record
    # written. Current handler silently degrades the unknown target to
    # "undeclared" inside record_intervention and writes the record with
    # exit 0 (RED) — WU-2 must reject it at the CLI BEFORE that degrade.
    fix_ri3 = "record-intervention-unknown-event-rejected"
    ri3_ok = True
    with tempfile.TemporaryDirectory(prefix="lazy-ri3-repo-") as ri3_repo_td, \
            tempfile.TemporaryDirectory(prefix="lazy-ri3-state-") as ri3_state_td:
        ri3_repo = Path(ri3_repo_td)
        ri3_id = "feat-ri3-unknown-event"
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

    # state-cli-contract-registry Phase 3 (D4-A): confirms the WIRING itself
    # (build_parser() returns cli_surface.DidYouMeanArgumentParser and an
    # unrecognized near-miss flag suggests the real one) — not a re-mock of
    # cli_surface.DidYouMeanArgumentParser's own unit tests
    # (test_cli_surface_gen.py), which cover the class in isolation.
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
                dym_parser.parse_args(["--emit-prompts"])  # near-miss of --emit-prompt
            except SystemExit as exc:
                dym_code = exc.code
        dym_stderr = dym_buf.getvalue()
        if dym_code != 2:
            failures.append(f"[{dym_name}] expected exit 2, got {dym_code!r}")
            dym_ok = False
        if "unrecognized arguments: --emit-prompts" not in dym_stderr:
            failures.append(f"[{dym_name}] leading error line missing/changed: "
                             f"{dym_stderr!r}")
            dym_ok = False
        if "did you mean: --emit-prompt?" not in dym_stderr:
            failures.append(f"[{dym_name}] missing did-you-mean suggestion: "
                             f"{dym_stderr!r}")
            dym_ok = False
    print(f"  {'PASS' if dym_ok else 'FAIL'} [{dym_name}]")

    # -------------------------------------------------------------------
    # concurrent-worktree-agent-coordination WU-2 (SPEC Requirement 2): the
    # concurrent_writer_commits carve-out, end-to-end through the REAL
    # --cycle-begin / --cycle-end CLI path (not just the pure
    # detect_cycle_bracket_friction unit — those live in
    # tests/test_lazy_core/test_markers.py). Two legitimate execute-plan
    # commits are made under the repo's OWN configured committer email
    # ("t@t"); three MORE commits are made under a DIFFERENT committer email
    # ("concurrent@writer.example") to simulate a sanctioned concurrent
    # writer. Budget (execute-plan, no plan file → table budget
    # _CYCLE_COMMIT_MULTI(3) + _CYCLE_COMMIT_NOISE_ALLOWANCE(1) = 4).
    # commits_since = 5 (over budget on its own), but
    # _count_concurrent_writer_commits attributes the 3 differing-email
    # commits away, leaving a chargeable count of 2 — well within budget —
    # so --cycle-end must report NO process_friction key.
    # -------------------------------------------------------------------
    fix_cwc = "concurrent-writer-commits-carve-out"
    cwc_ok = True
    try:
        cwc_state = td_path / "cwc-state"
        cwc_state.mkdir(parents=True, exist_ok=True)
        cwc_repo = td_path / "cwc-repo"
        cwc_repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(cwc_repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(cwc_repo), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(cwc_repo), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(cwc_repo), "config", "commit.gpgsign", "false"], check=True)
        (cwc_repo / "seed.txt").write_text("seed", encoding="utf-8")
        subprocess.run(["git", "-C", str(cwc_repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(cwc_repo), "commit", "-q", "-m", "seed"], check=True)
        cwc_env = {k: v for k, v in os.environ.items()
                   if k not in ("LAZY_CYCLE_SUBAGENT",)}
        cwc_env["LAZY_STATE_DIR"] = str(cwc_state)
        cwc_env["LAZY_ORCHESTRATOR"] = "1"
        r = subprocess.run(
            [sys.executable, _this_script, "--cycle-begin",
             "--feature-id", "feat-cwc", "--nonce", "beef",
             "--sub-skill", "execute-plan",
             "--repo-root", str(cwc_repo)],
            capture_output=True, text=True, env=cwc_env,
        )
        if r.returncode != 0:
            failures.append(f"[{fix_cwc}] --cycle-begin must exit 0; got {r.returncode}: {r.stderr}")
            cwc_ok = False
        # Two OWN commits (this cycle's own dispatch, same configured identity).
        for i in range(2):
            (cwc_repo / f"own{i}.txt").write_text(f"own{i}", encoding="utf-8")
            subprocess.run(["git", "-C", str(cwc_repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(cwc_repo), "commit", "-q", "-m", f"own{i}"], check=True)
        # Three CONCURRENT-WRITER commits (a different committer identity).
        for i in range(3):
            (cwc_repo / f"conc{i}.txt").write_text(f"conc{i}", encoding="utf-8")
            subprocess.run(["git", "-C", str(cwc_repo), "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", str(cwc_repo),
                 "-c", "user.email=concurrent@writer.example",
                 "-c", "user.name=concurrent-writer",
                 "commit", "-q", "-m", f"conc{i}"],
                check=True,
            )
        r = subprocess.run(
            [sys.executable, _this_script, "--cycle-end",
             "--repo-root", str(cwc_repo)],
            capture_output=True, text=True, env=cwc_env,
        )
        if r.returncode != 0:
            failures.append(f"[{fix_cwc}] --cycle-end must exit 0; got {r.returncode}: {r.stderr}")
            cwc_ok = False
        try:
            cwc_out = json.loads(r.stdout)
            if "process_friction" in cwc_out:
                failures.append(
                    f"[{fix_cwc}] a concurrent-writer HEAD advance must NOT trip "
                    f"process_friction; got {cwc_out.get('process_friction')!r}"
                )
                cwc_ok = False
        except (json.JSONDecodeError, TypeError):
            failures.append(f"[{fix_cwc}] --cycle-end stdout must be JSON; got {r.stdout!r}")
            cwc_ok = False
    except Exception as exc:  # noqa: BLE001
        failures.append(f"[{fix_cwc}] unexpected error: {exc!r}")
        cwc_ok = False
    print(f"  {'PASS' if cwc_ok else 'FAIL'} [{fix_cwc}] concurrent-writer commits suppressed via committer-email carve-out")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll smoke tests passed.")
    return 0


# ---------------------------------------------------------------------------
# Live-settings split-brain probe (Fix Scope 4 / D2)
# ---------------------------------------------------------------------------


def _load_doc_drift_module():
    """Load the sibling doc-drift-lint.py (hyphenated → importlib). Kept as a
    module-level seam so the live-settings probe stays monkeypatchable in tests."""
    import importlib.util
    p = Path(__file__).parent / "doc-drift-lint.py"
    spec = importlib.util.spec_from_file_location("_doc_drift_for_live_settings", str(p))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load doc-drift-lint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def live_settings_probe(repo_root, live_path=None):
    """(ok, detail) health of the live ~/.claude/settings.json vs the tracked
    SSOT, sourced from doc-drift-lint's live_settings_status. FAIL-OPEN benign
    default (True, <note>) if the helper is unloadable / raises — this probe
    field must NEVER hard-error or gate state computation (bug: live-settings
    split-brain, Fix Scope 4 / D2)."""
    try:
        ddl = _load_doc_drift_module()
        # live-settings-probe-false-positive-in-consumer-repo (Gap 2): resolve
        # the tracked settings SSOT against the claude-config checkout when the
        # RUN targets a consumer repo (AlgoBooth has no user/settings.json) —
        # else every consumer-repo probe false-reports 'missing settings'.
        ssot_root = ddl.settings_ssot_root(repo_root)
        ok, detail = ddl.live_settings_status(ssot_root, live_path=live_path)
        return bool(ok), str(detail)
    except Exception:  # noqa: BLE001 — benign default, never propagate
        return True, "live-settings check unavailable (doc-drift-lint not loadable)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # state-cli-contract-registry Phase 3 (D4-A): the twins' argparse error()
    # gains a "did you mean" epilogue on an unrecognized-flag misfire. The
    # leading `<prog>: error: ...` line + exit code (2) stay byte-identical
    # to stock argparse — see cli_surface.DidYouMeanArgumentParser.
    parser = cli_surface.DidYouMeanArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--cloud", action="store_true",
                        help="Use /lazy-cloud state machine variants")
    parser.add_argument("--skip-needs-research", action="store_true",
                        help=("Skip queue entries that would terminate on "
                              "needs-research; emit terminal_reason "
                              "'queue-blocked-on-research' when the queue is "
                              "exhausted with only research-pending features remaining."))
    parser.add_argument("--repo-root", default=os.getcwd(),
                        help="Project root (default: $PWD)")
    parser.add_argument("--real-device", choices=["yes", "no", "auto"], default="auto",
                        help=("Whether THIS host has a real audio output device "
                              "(governs real-device-only MCP-assertion deferral). "
                              "'auto' reads $ALGOBOOTH_REAL_AUDIO_DEVICE (absent → "
                              "'no'). The orchestrator probes the live backend "
                              "(get_audio_mode: cpal & not forced) and may pass "
                              "yes/no explicitly. Ignored under --cloud (cloud has "
                              "no device)."))
    parser.add_argument("--test", action="store_true",
                        help="Run fixture smoke tests instead of computing state")
    parser.add_argument("--backfill-receipts", action="store_true",
                        help=("One-shot migration: write COMPLETED.md "
                              "(provenance: backfilled-unverified) for every "
                              "queue feature that claims completion but lacks a "
                              "receipt. Grandfathers pre-gating completions."))
    # Ad-hoc enqueue mode: insert a feature at the top of the queue and exit.
    parser.add_argument("--enqueue-adhoc", action="store_true",
                        help=("Prepend an ad-hoc feature to docs/features/queue.json "
                              "(requires --id and --name; --brief seeds ADHOC_BRIEF.md)."))
    parser.add_argument("--id", help="Ad-hoc feature id (kebab-case).")
    parser.add_argument("--name", help="Ad-hoc feature human-readable name.")
    parser.add_argument("--brief", default="",
                        help="One-paragraph ad-hoc task brief (seeds ADHOC_BRIEF.md).")
    parser.add_argument("--spec-dir", default=None,
                        help="Spec dir under docs/features/ (default: same as --id).")
    parser.add_argument("--type", dest="adhoc_type", choices=["feature", "bug"],
                        default="feature",
                        help=("Ad-hoc enqueue target pipeline (default: feature). "
                              "--type bug routes into docs/bugs/queue.json via the "
                              "existing bug-state.py enqueue."))
    parser.add_argument("--reorder-queue", dest="reorder_queue",
                        action="store_true",
                        help=("Operator-only / out-of-cycle: move (or remove) an "
                              "existing docs/features/queue.json entry. Requires "
                              "--id and --to. Gated by refuse_if_cycle_active like "
                              "--enqueue-adhoc (exit 3 for a cycle subagent)."))
    parser.add_argument("--to", dest="reorder_to", default=None,
                        help=("Reorder destination for --reorder-queue: "
                              "tail | head | remove | <integer index>."))
    parser.add_argument("--reassert-owner", dest="reassert_owner",
                        action="store_true",
                        help=("Orchestrator-only / out-of-cycle: re-claim a live "
                              "foreign-stamped run marker for the owning session "
                              "(requires --session-id). Gated by "
                              "refuse_if_cycle_active (exit 3 for a cycle "
                              "subagent). single-slot-marker-ownership-race."))
    # lazy-batch-no-mid-run-budget-or-park-controls: operator-authorized mid-run
    # controls. Each is orchestrator-only (refuse_if_cycle_active), requires an
    # ACTIVE marker, and REFUSES without --operator-authorized (parallel to the
    # --run-end --reason checkpoint authorization gate). They mutate the active
    # marker IN PLACE — no clobber, no restart, no run-end flush.
    parser.add_argument("--set-max-cycles", dest="set_max_cycles",
                        type=int, default=None, metavar="N",
                        help=("Orchestrator-only, --operator-authorized: update the "
                              "ACTIVE run marker's max_cycles to N in place (mid-run "
                              "budget change). Atomic — no clobber/restart/run-end "
                              "flush. After this the marker is the authoritative live "
                              "budget: the cycle header and per-feature budget guard "
                              "both agree with N. Refused without --operator-authorized."))
    parser.add_argument("--set-park", dest="set_park",
                        choices=["on", "off"], default=None,
                        help=("Orchestrator-only, --operator-authorized: toggle park "
                              "mode on the ACTIVE run marker mid-run. 'on' arms BOTH "
                              "park_needs_input and park_blocked (the --park umbrella); "
                              "'off' clears both AND park_provisional. The probe reads "
                              "the marker each cycle. Refused without --operator-authorized."))
    parser.add_argument("--set-park-provisional", dest="set_park_provisional",
                        choices=["on", "off"], default=None,
                        help=("Orchestrator-only, --operator-authorized: toggle "
                              "park-provisional-acceptance on the ACTIVE run marker "
                              "mid-run. 'on' requires park mode already on "
                              "(park_provisional requires park_needs_input, SPEC D1) — "
                              "else refused. Refused without --operator-authorized."))
    # no-sanctioned-cli-for-queue-state-mutations: operator-directed in-place
    # queue mutators (the sanctioned replacement for hand-editing queue.json).
    # Each is refuse_if_cycle_active FIRST + requires --operator-authorized.
    # --set-tier atomically RE-SORTS listed order to match the new merged
    # priority (the load-bearing side effect). Coupled-pair: bug-state.py
    # exposes --set-severity (the bug analog) + the same deps mutators + --unpin.
    parser.add_argument("--set-tier", dest="set_tier", nargs=2,
                        metavar=("ID", "TIER"), default=None,
                        help=("Orchestrator-only, --operator-authorized: set feature ID's "
                              "queue tier to TIER and ATOMICALLY re-position it in listed "
                              "order to match its new merged priority — one write, never a "
                              "stale reorder. TIER is a bare int (lower = higher priority), "
                              "a named tier enum (pre-release/commercialization/milestone/"
                              "major-initiative/follow-up/non-audio/4a/4b), or a "
                              "comma-separated list of those (a multi-enum feature — "
                              "merged priority is the MIN). "
                              "refuse_if_cycle_active (exit 3 for a cycle subagent)."))
    parser.add_argument("--set-independent", dest="set_independent", nargs=2,
                        metavar=("ID", "VALUE"), default=None,
                        help=("Orchestrator-only, --operator-authorized: set (or CLEAR) "
                              "feature ID's `independent: true` shard-eligibility marker "
                              "(the /lazy-batch-parallel claim_shardable gate) — the "
                              "sanctioned replacement for hand-editing queue.json. VALUE is "
                              "true|false (false REMOVES the key, the byte-clean not-"
                              "independent state). Does NOT reposition (independent is an "
                              "isolation marker, not priority). refuse_if_cycle_active FIRST."))
    parser.add_argument("--add-deps", dest="add_deps", metavar="ID", default=None,
                        help=("Orchestrator-only, --operator-authorized: add the --deps "
                              "id list as hard queue dependencies on feature ID (post-hoc, "
                              "arbitrary — the non-SPEC sibling of --sync-deps). Deduped; "
                              "post-mutation cycle-guarded. refuse_if_cycle_active FIRST."))
    parser.add_argument("--remove-deps", dest="remove_deps", metavar="ID", default=None,
                        help=("Orchestrator-only, --operator-authorized: remove the --deps "
                              "id list from feature ID's hard queue dependencies (empty "
                              "result drops the deps key). refuse_if_cycle_active FIRST."))
    parser.add_argument("--record-intervention", dest="record_intervention",
                        action="store_true",
                        help=("intervention-efficacy-tracking: write the "
                              "intervention record (hypothesis ledger capture) "
                              "for a shipped harness change to "
                              "docs/interventions/<id>.md. Requires --id. "
                              "Optional: --spec-dir (item dir carrying the "
                              "## Intervention Hypothesis block), --pipeline, "
                              "--shipped-commit/--shipped-date (D9 backfill — "
                              "stamps provenance: backfilled), and the "
                              "hypothesis-override flags (--target-signal, "
                              "--expected-direction, --signal-independence, "
                              "--review-after-runs) for the no-SPEC hardening "
                              "path. Orchestrator-only (refuse_if_cycle_active; "
                              "exit 3 for a cycle subagent). Idempotent — an "
                              "existing record is never clobbered."))
    parser.add_argument("--pipeline", dest="intervention_pipeline",
                        choices=["feature", "bug", "hardening"],
                        default="feature",
                        help=("Pipeline stamped on a --record-intervention "
                              "record (default: feature on lazy-state.py, bug "
                              "on bug-state.py; hardening for /harden-harness "
                              "rounds)."))
    parser.add_argument("--shipped-commit", default=None,
                        help=("--record-intervention D9 backfill: override the "
                              "recorded shipped_commit (default: current HEAD). "
                              "Stamps provenance: backfilled."))
    parser.add_argument("--shipped-date", default=None,
                        help=("--record-intervention D9 backfill: override the "
                              "recorded shipped_date (YYYY-MM-DD). Stamps "
                              "provenance: backfilled."))
    parser.add_argument("--target-signal", default=None,
                        help=("--record-intervention hypothesis override: "
                              "kpi:<system>.<kpi-id> or event:<ledger-event-"
                              "type> (for captures with no SPEC block, e.g. "
                              "hardening rounds)."))
    parser.add_argument("--expected-direction", default=None,
                        choices=["decrease", "increase"],
                        help="--record-intervention hypothesis override.")
    parser.add_argument("--signal-independence", default=None,
                        help=("--record-intervention hypothesis override: "
                              "independent | self-emitted | mixed (+ optional "
                              "justification tail)."))
    parser.add_argument("--review-after-runs", type=int, default=None,
                        help=("--record-intervention hypothesis override: "
                              "post-ship run-count window before each review "
                              "(default: 20)."))
    parser.add_argument("--tier", type=int, default=0,
                        help="Tier for the ad-hoc entry (default: 0).")
    parser.add_argument("--stub", action="store_true",
                        help=("toolify-auto-promotion D4-B: mark the ad-hoc queue "
                              "entry \"stub\": true (Step-4.5 baseline-lock "
                              "cross-check flag). Default off — entry byte-"
                              "identical to before. Feature pipeline only "
                              "(refused with --type bug)."))
    parser.add_argument("--at", choices=["head", "tail"], default="head",
                        dest="enqueue_at",
                        help=("toolify-auto-promotion D4-B: queue landing "
                              "position for --enqueue-adhoc. Default head "
                              "(byte-identical prepend); tail appends so a "
                              "promotion rides roadmap order instead of "
                              "jumping the curated queue. Feature pipeline "
                              "only (tail refused with --type bug)."))
    parser.add_argument("--deps", default=None,
                        help=("queue-dependency-dag: comma-separated hard-dep "
                              "ids for --enqueue-adhoc (e.g. --deps a,b). "
                              "Validated (kebab-case ids; bug:/feature: "
                              "prefixes reserved → exit 2); stored on the "
                              "prepended entry's `deps` field; forwarded to "
                              "bug-state.py on --type bug. Omitted → the "
                              "entry shape is byte-identical to before."))
    parser.add_argument("--sync-deps", dest="sync_deps", action="store_true",
                        help=("queue-dependency-dag D5 (orchestrator-only, "
                              "wired at /spec-phases): project the SPEC "
                              "**Depends on:** block's HARD deps into the "
                              "queue entry's `deps` field (requires --id). "
                              "Script-owned load → parse → mutate → atomic "
                              "write; idempotent (noop:true when in sync; "
                              "empty hard set removes the key). Gated by "
                              "refuse_if_cycle_active FIRST (exit 3 for a "
                              "cycle subagent, zero side effects)."))
    # --- mechanize-prose-only-orchestrator-contracts (c): decision write-back ---
    parser.add_argument("--record-decision", action="store_true",
                        help=("Record a mid-run AskUserQuestion answer to an "
                              "on-disk decision record keyed by --sentinel, "
                              "so it cannot evaporate before the "
                              "apply-resolution dispatch reads it. Requires "
                              "--sentinel and --chosen; --summary optional. "
                              "Orchestrator-only (refuse_if_cycle_active "
                              "FIRST, exit 3 for a cycle subagent, zero side "
                              "effects). Survives --run-end (sibling state "
                              "file, not the run marker)."))
    parser.add_argument("--sentinel", default=None, metavar="PATH",
                        help="With --record-decision: the sentinel file path this answer resolves.")
    parser.add_argument("--chosen", default=None, metavar="TEXT",
                        help="With --record-decision: the chosen option label(s).")
    parser.add_argument("--summary", default=None, metavar="TEXT",
                        help="With --record-decision: optional resolution summary text.")
    # --- code-doc-provenance-linkage: provenance CLI (mirrored on bug-state.py) ---
    parser.add_argument("--link-provenance", action="store_true",
                        help=("Manual provenance link (the one-writer producer's "
                              "second trigger): distill out-of-pipeline work "
                              "(--commits A..B primary, --pr <n> sugar) into "
                              "IMPLEMENTED.md + docs/provenance-index.json rows "
                              "(provenance: manual). Requires --id; optional "
                              "--body-file (approved prose) and --dry-run. Gated "
                              "by refuse_if_cycle_active like --enqueue-adhoc."))
    parser.add_argument("--commits", default=None, metavar="A..B",
                        help="Commit range for --link-provenance (primary addressing).")
    parser.add_argument("--pr", type=int, default=None, metavar="N",
                        help=("PR-number sugar for --link-provenance — resolved to a "
                              "range via `gh pr view`; degrades to a clean refusal "
                              "naming the --commits fallback when gh is absent."))
    parser.add_argument("--body-file", default=None, metavar="PATH",
                        help=("Operator-approved distillate body prose for "
                              "--link-provenance (written through the producer, "
                              "which still owns frontmatter + index)."))
    parser.add_argument("--dry-run", action="store_true",
                        help=("With --link-provenance: derive + preview the "
                              "touched-file set and distillate, write NOTHING."))
    parser.add_argument("--provenance-lookup", default=None, metavar="PATH",
                        help=("Pure read: print the provenance-index rows governing "
                              "PATH ({path, governed_by: [{id, type, doc, decisions, "
                              "provenance}]}). Never mutates; missing index → empty "
                              "governed_by (degrades to a no-op)."))
    parser.add_argument("--lint-provenance", action="store_true",
                        help=("Pure read, report only (D10): dead index rows (path "
                              "gone), high-churn files with no provenance rows, and "
                              "cross-orphans (distillate↔index). Never mutates."))
    parser.add_argument("--backfill-provenance", action="store_true",
                        help=("One-shot backfill (D7): distill every receipted item "
                              "(COMPLETED.md/FIXED.md incl. docs/bugs/_archive/) "
                              "via message-grep derivation, provenance: backfilled. "
                              "Idempotent (items with IMPLEMENTED.md are skipped)."))
    parser.add_argument("--materialize-wi", type=int, default=None,
                        help="Materialize ADO work item <id> from docs/work/ado-mirror.json into a doc pipeline.")
    parser.add_argument("--feature-id", default=None,
                        help="Scope this run to a single feature by id (queue entry id). Absent → single-current default.")
    parser.add_argument("--park-needs-input", action="store_true",
                        help=(
                            "OPT-IN park mode: when active, a feature carrying an unresolved "
                            "NEEDS_INPUT.md is SKIPPED (parked) rather than halting the queue. "
                            "The parked item is reported in the 'parked[]' output array and "
                            "re-enters automatically once NEEDS_INPUT.md is resolved/renamed. "
                            "Without this flag, output is byte-identical to the default behavior "
                            "('parked' key is entirely absent and the needs-input halt fires as today)."
                        ))
    parser.add_argument("--park-blocked", action="store_true",
                        help=(
                            "OPT-IN park mode (companion to --park-needs-input): when active, a "
                            "feature carrying a feature-local BLOCKED.md is SKIPPED (parked) rather "
                            "than halting the queue with terminal_reason='blocked'. The parked item "
                            "is reported in the 'parked[]' array and re-enters automatically once "
                            "the block is resolved/renamed. Global/environment terminals "
                            "(cloud/device/research/scoped-id) still halt. When every remaining "
                            "feature is parked, the honest 'queue-exhausted-all-parked' terminal "
                            "fires instead of 'all-features-complete'. Without this flag, output is "
                            "byte-identical to the default behavior (BLOCKED still halts)."
                        ))
    parser.add_argument("--park-provisional", action="store_true",
                        help=(
                            "OPT-IN modifier of --park-needs-input (park-provisional-acceptance, "
                            "SPEC D1 — supplying it alone is a hard error): a parked-eligible "
                            "NEEDS_INPUT.md that passes the fail-closed provisional predicate "
                            "(divergence two-key: producer `divergence:` AND input-audit "
                            "`audit_divergence:` both in {isolated, contained}; every decision "
                            "carrying a **Recommendation:**; never two-key-mechanical or "
                            "completion-integrity-gate sentinels) routes the "
                            "__provisional_accept__ pseudo-skill instead of parking. The "
                            "orchestrator then runs --provisionalize-sentinel (Resolution "
                            "appended `resolved_by: auto-provisional`, file renamed "
                            "NEEDS_INPUT_PROVISIONAL.md) and the feature keeps implementing. "
                            "An unratified provisional file blocks completion mechanically and "
                            "halts non-park probes on `needs-ratification`."
                        ))
    parser.add_argument("--park", dest="park_umbrella", action="store_true",
                        help=(
                            "Umbrella park flag — the /lazy-batch `--park` invocation flag. "
                            "Arms BOTH --park-needs-input AND --park-blocked in one token "
                            "(mirroring `--set-park on`), so `--run-start --park` persists park "
                            "mode into the run marker and the probe reads it from cycle 1. "
                            "Equivalent to passing the two granular flags; combine with "
                            "--park-provisional for provisional-acceptance. Default off → "
                            "byte-identical to a non-park run. (Fixes lazy-run-marker-park-arm: "
                            "Step 0.55 forwards the operator's `--park` verbatim, no "
                            "re-translation to forget.)"
                        ))
    parser.add_argument("--provisionalize-sentinel", default=None, metavar="PATH",
                        help=(
                            "Provisionally accept the NEEDS_INPUT.md at PATH on its "
                            "recommendations (park-provisional-acceptance SPEC D2): re-validate "
                            "the fail-closed eligibility predicate, append a ## Resolution "
                            "block (resolved_by: auto-provisional, decision_commit: HEAD), and "
                            "rename to NEEDS_INPUT_PROVISIONAL.md (git-mv-aware). Refusals "
                            "exit 1 with ZERO writes. Ratification later neutralizes the "
                            "renamed file via --neutralize-sentinel."
                        ))
    parser.add_argument("--per-feature-cycle-cap", type=int, default=None,
                        metavar="N",
                        help=(
                            "feature-budget-guard-and-skip-ahead Phase 2: override the DYNAMIC "
                            "per-feature forward-cycle ceiling with a FIXED integer N. Absent "
                            "(default None) → the ceiling is computed per Locked Decision 4 as "
                            "max(6, min(C*4//10, (C//Q)*2)) from the run's max_cycles (C) and the "
                            "ready-queue depth (Q). The per-feature budget guard trips when a "
                            "feature's per_feature_forward_cycles count crosses this ceiling, "
                            "deferring it to the live-queue tail (run-scoped reorder; second trip "
                            "→ terminal eviction). Marker-gated: a no-op when no run marker is "
                            "present (output byte-identical to the pre-feature baseline)."
                        ))
    parser.add_argument("--strict-research-halt", action="store_true",
                        help=(
                            "feature-budget-guard-and-skip-ahead Phase 3: OPT OUT of the default-on "
                            "dependency-aware skip-ahead. By DEFAULT (flag absent), when the queue "
                            "head is gated (research-pending or BLOCKED), the queue-selection loop "
                            "skips past it onto the first skip-ahead-ready item — one whose deps have "
                            "no hard dependency on a gated id AND which carries an explicit "
                            "independent: true (a.k.a. no_shared_state) marker in its SPEC frontmatter "
                            "or queue entry. Unmarked/downstream items are NOT skipped onto (they "
                            "degrade to today's strict halt). With this flag SET, that skip-ahead is "
                            "DISABLED and the legacy halt-on-first-gated-head behavior is restored. "
                            "Output is byte-identical to the pre-Phase-3 baseline when set (or when "
                            "no head is gated)."
                        ))
    parser.add_argument("--verify-ledger", default=None, metavar="SPEC_PATH",
                        help=(
                            "Scripted completion-ledger guard (replaces the prose guard blocks "
                            "in the lazy skills). Verifies: (1) clean working tree, "
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
                        ))
    parser.add_argument("--apply-pseudo", nargs=2, default=None, metavar=("NAME", "SPEC_PATH"),
                        help="Single-author the deterministic sentinel/receipt write for a lazy pseudo-skill.")
    parser.add_argument("--plan", default=None,
                        help="Plan-file path for __flip_plan_complete_*__ pseudo-skills AND "
                             "for plan-scoped --verify-ledger (Phase 9 WU-3).")
    parser.add_argument("--apply-date", default=None,
                        help="Override date (YYYY-MM-DD) for --apply-pseudo writes.")
    parser.add_argument("--reason", default=None,
                        help="Reason string for __write_deferred_non_cloud__.")
    parser.add_argument("--deferred-step", type=int, default=None,
                        help="deferred_step for __write_deferred_non_cloud__.")
    parser.add_argument("--neutralize-sentinel", default=None, metavar="PATH",
                        help="Rename a resolved sentinel to the canonical *_RESOLVED_<date> form (collision-safe).")
    parser.add_argument("--repeat-count", action="store_true",
                        help="Persist the probe signature and emit a 'repeat_count' field "
                             "(consecutive identical-probe count) for mechanical loop detection. "
                             "ADVANCES the persisted streak — reserve for the single dispatch-bound "
                             "probe per cycle. Without this flag, output is byte-identical to the "
                             "default and no state file is written.")
    parser.add_argument("--repeat-count-peek", action="store_true",
                        help="Like --repeat-count but PEEK only: compute and emit the would-be "
                             "'repeat_count' WITHOUT advancing the persisted streak (no state-file "
                             "write). Use for diagnostic/inspection probes so they do not inflate "
                             "the streak. Mutually exclusive with --repeat-count.")
    parser.add_argument("--probe", action="store_true",
                        help="Fold git-guard results + a pre-formatted cycle-header line into the "
                             "probe JSON (orchestrator happy-path payload). Without this flag, output "
                             "is byte-identical to the default.")
    parser.add_argument("--emit-prompt", action="store_true",
                        help="Enrich the probe JSON with cycle_prompt + cycle_model "
                             "(script-assembled cycle dispatch prompt; composes with "
                             "--repeat-count for loop detection).")
    parser.add_argument("--forward-cycles", type=int, default=None,
                        help="Orchestrator forward-cycle count (for --probe cycle header).")
    parser.add_argument("--meta-cycles", type=int, default=None,
                        help="Orchestrator meta-cycle count (for --probe cycle header).")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="Orchestrator max-cycles ceiling (for --probe cycle header).")
    # Phase 1 run-lifecycle flags: --run-start writes the marker (pipeline=feature
    # for this script), --run-end deletes it.  Both print a JSON result and exit
    # immediately, like other action flags.  All new Phase 1 behavior (registry
    # writes, counter advances) is unreachable without first calling --run-start.
    parser.add_argument("--run-start", action="store_true",
                        help=(
                            "Write the run marker to the state dir (pipeline=feature), "
                            "gating registry and counter side-effects for this run. "
                            "Uses --cloud, --repo-root, and --max-cycles when present. "
                            "Prints the marker JSON and exits."
                        ))
    parser.add_argument("--run-end", action="store_true",
                        help=(
                            "Delete the run marker from the state dir. "
                            "Call on every terminal run path to avoid haunting the "
                            "next session. Prints {\"run_marker_deleted\": true|false} "
                            "and exits."
                        ))
    # multi-repo-concurrent-runs Phase 2 (WU-2.1): read-only marker presence
    # query for the three enforcement hooks.  Resolves the active repo
    # (--repo-root, default cwd) and asks read_run_marker() — which routes
    # through the per-repo keyed claude_state_dir() — whether a LIVE marker is
    # present FOR THIS REPO.  Exits 0 (present) / 1 (absent); read-only (never
    # creates the state dir).  The bash hooks call this so Python owns ALL
    # repo-key derivation — bash NEVER re-derives it.
    parser.add_argument("--marker-present", action="store_true",
                        help=(
                            "Read-only: exit 0 if a live run marker is present for "
                            "the current repo (--repo-root, default cwd), exit 1 if "
                            "absent. Routes through the per-repo keyed state dir. "
                            "Used by the enforcement hooks; never creates state."
                        ))
    parser.add_argument("--session-id", default=None,
                        help=(
                            "Optional session id for --marker-present (and other "
                            "read paths): a marker bound to a DIFFERENT session id "
                            "reads as absent (non-destructive session isolation)."
                        ))
    # cycle-prompt-environment-dialect Phase 1: --marker-status — a NEVER-THROWS
    # read-only presence query replacing the fragile taught
    # `cat <marker> | python -c "json.load(sys.stdin)"` idiom (cluster e, 94
    # mined tracebacks). Unlike --marker-present (exit-code-only), this prints
    # JSON and ALWAYS exits 0 — absent marker, corrupt JSON, and no-state-dir
    # all resolve to {"present": false} rather than a traceback or a nonzero
    # exit a shell script must remember to check.
    parser.add_argument("--marker-status", action="store_true",
                        help=(
                            "Read-only, never-throws: print "
                            "{\"present\": bool} for the current repo's run "
                            "marker (--repo-root, default cwd). Always exits "
                            "0 — absent/corrupt/no-state-dir all resolve to "
                            "present: false."
                        ))
    # parallel-worktree-batch-execution (D2-A): with --run-start at a WORKTREE
    # root, the /lazy-batch-parallel coordinator stamps the lane marker with the
    # PARENT run's identity so audits / --run-end sweeps can prove the lane
    # marker sanctioned. Serial runs omit the flag → parent_run: null
    # (byte-identical shape, always-minted key).
    parser.add_argument("--parent-run", default=None, metavar="JSON",
                        help=(
                            "With --run-start: JSON object "
                            "'{\"repo_root\": str, \"started_at\": str}' identifying "
                            "the PARENT run whose coordinator armed this lane "
                            "marker (parallel-worktree lanes). Malformed → exit 2, "
                            "zero side effects. Omit for serial runs."
                        ))
    # cycle-subagent-fabricates-policy-or-stray-branch Phase 2: read-only query
    # mirroring --marker-present, but it ALSO prints the run marker's
    # work_branch. Used by block-sentinel-write-on-stray-branch.sh to learn the
    # reference branch (bash never re-derives branch identity; Python owns it).
    parser.add_argument("--marker-work-branch", action="store_true",
                        help=(
                            "Read-only: print the run marker's work_branch and "
                            "exit 0 if a live marker carrying a branch is present "
                            "for the current repo (--repo-root, default cwd); exit "
                            "1 if absent/stale/legacy-no-branch. Never creates "
                            "state. Used by the stray-branch write-time hook."
                        ))
    # adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke Phase 1
    # (Gap 2): read-only pause-vs-terminal discriminator for a just-returned
    # /execute-plan cycle. Reads the execute-plan run marker
    # (~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json) NON-destructively
    # + the plan (--plan) frontmatter status; prints the JSON verdict and ALWAYS
    # exits 0 (a probe never gates). Consumed by lazy-batch/lazy-bug-batch Step
    # 1e/4a BEFORE emitting --emit-dispatch recovery. The execute-plan marker is
    # pipeline-agnostic, so this is a parity-audited coupled-pair surface
    # (identical flag on bug-state.py).
    parser.add_argument("--execute-plan-liveness", action="store_true",
                        help=(
                            "Read-only: print the execute-plan pause-vs-terminal "
                            "verdict JSON {marker_present, plan_status, verdict} "
                            "for --plan PLAN in --repo-root REPO. marker present + "
                            "plan not Complete => paused (recovery should be "
                            "suppressed); marker absent or plan Complete or any "
                            "read error => terminal (fail-safe). Always exits 0."
                        ))
    # byref-updatedinput-unapplied-on-background-agent-dispatch WU-2: the
    # sanctioned consumed-nonce read. The platform silently drops the
    # by-reference `hookSpecificOutput.updatedInput` rewrite for the Agent tool
    # as a CLASS (upstream anthropics/claude-code#39814, closed not-planned), so
    # a `@@lazy-ref nonce=<hex>` dispatch lands the BARE token at the subagent.
    # This read returns the registered prompt bytes for a nonce the guard ALREADY
    # ALLOW+consumed THIS run, so a subagent that booted with the bare token has a
    # designed recovery path. Read-only, run-scoped, never un-consumes; NOT gated
    # by refuse_if_cycle_active (a read a dispatched subagent MUST be able to run).
    parser.add_argument("--resolve-ref", metavar="NONCE", default=None,
                        help=(
                            "Read-only: print the registered prompt bytes for a "
                            "nonce the guard already ALLOW+consumed this run "
                            "(consumed + TTL-fresh + run-start-gated), exit 0; "
                            "print nothing + exit 1 on a miss (unknown / expired "
                            "/ cross-run / still-unconsumed). The subagent-side "
                            "resolve path for a bare @@lazy-ref token."
                        ))
    # unified-pipeline-orchestrator Phase 1: merged work-list view. Reads BOTH
    # docs/features/queue.json and docs/bugs/queue.json (via the existing
    # loaders), orders them (priority desc / lower-tier-or-severity first; tie →
    # feature before bug — only a genuine P0 bug precedes a P1 feature; stable
    # within each queue), and prints the next
    # actionable head as JSON {item_id, type, repo_root}. Read-only ordering
    # ONLY — never re-infers per-item state. Empty on both queues → null.
    parser.add_argument("--next-merged", action="store_true",
                        help=(
                            "Read-only: print the head of the merged feature+bug "
                            "work-list as JSON {item_id, type, repo_root} (bugs "
                            "break priority ties), or null when both queues are "
                            "empty. Pure ordering — does not re-infer per-item "
                            "state. Used by the unified /lazy-batch driver."
                        ))
    # unified-pipeline-orchestrator Phase 5: --ensure-runtime / --gate-coverage —
    # the first two of the three retro-named deterministic dances promoted to
    # lazy-state.py subcommands (the third is the enhanced --apply-pseudo
    # __mark_complete__). Shared impl in lazy_core.py.
    parser.add_argument("--ensure-runtime", action="store_true",
                        help=(
                            "Ensure the dev runtime + MCP server are up AND current; "
                            "print structured JSON {status: ready|booted|stale-rebuilt, "
                            "mcp_tools_present, health_code}. Collapses the Step-1d.0 "
                            "runtime-ensure dance. AlgoBooth specifics (port, restart "
                            "command, globs, MCP tool) are parameterized in lazy_core's "
                            "config dict, not hard-coded. Real probe/restart in "
                            "production; tests inject for determinism."
                        ))
    parser.add_argument("--gate-coverage", default=None, metavar="SPEC_PATH",
                        help=(
                            "Deterministic Gate-1 MCP-coverage verdict for a feature/bug "
                            "spec dir: print JSON {ok, decisions:[{id,title,keywords,"
                            "covered}], uncovered:[id], scenario_count}. Reads SPEC.md's "
                            "Locked-Decision surface, greps mcp-tests/*.md RESOLVING "
                            "symlink/64-byte-pointer targets (the Windows blindspot). "
                            "Exit 1 iff any decision uncovered. Promotes the "
                            "mcp-coverage-audit.md algorithm to code."
                        ))
    # lazy-cycle-containment C1 (Phase 2): the cycle-subagent marker bracket.
    # The orchestrator issues --cycle-begin immediately before every Agent
    # dispatch and --cycle-end immediately after the Agent returns (every return
    # path: success, halt, error).  The marker is the on/off switch the C3
    # refusals (Phase 3) and the C2 PreToolUse hook (Phase 4) key on.
    parser.add_argument("--cycle-begin", action="store_true",
                        help=(
                            "Write the cycle-subagent marker (lazy-cycle-active.json) "
                            "before an Agent dispatch. Requires --feature-id and --nonce; "
                            "optional --kind real|meta (default real). Self-healing: "
                            "overwrites a stale marker and logs. Prints the marker JSON "
                            "and exits."
                        ))
    parser.add_argument("--cycle-end", action="store_true",
                        help=(
                            "Clear the cycle-subagent marker after an Agent returns. "
                            "Idempotent (no-op if already absent). Prints "
                            "{\"cycle_marker_cleared\": true|false} and exits."
                        ))
    parser.add_argument("--record-resolution-signal", action="store_true",
                        help=(
                            "loop-detected-false-positives: persist the one-shot "
                            "resolution-aware reset signal on the run marker (field "
                            "last_resolution_step_key=[feature_id, current_step]) so the "
                            "NEXT same-step probe RESETS step_repeat_count to 1 — a "
                            "needs-input RESOLUTION is itself a dispatch (it consumes a "
                            "nonce), which defeats the F2 debounce and would otherwise "
                            "let the step counter survive a legitimately-resolved blocker. "
                            "Requires --feature-id and --current-step. Marker-gated "
                            "(no-op when no run marker). Prints the marker JSON and exits."
                        ))
    parser.add_argument("--current-step", default=None,
                        help=(
                            "Step name for --record-resolution-signal (the step "
                            "signature the needs-input resolution was applied at; bind "
                            "to the resolved feature's probe current_step VERBATIM)."
                        ))
    parser.add_argument("--nonce", default=None,
                        help="Dispatch nonce (hex) for --cycle-begin.")
    parser.add_argument("--kind", choices=["real", "meta"], default="real",
                        help="Dispatch kind for --cycle-begin (real|meta; default real).")
    parser.add_argument("--sub-skill", default=None,
                        help=(
                            "Dispatched sub_skill name for --cycle-begin (e.g. "
                            "execute-plan). Persisted into the cycle marker so "
                            "--cycle-end's process-friction detector selects the "
                            "correct per-sub_skill commit budget instead of the "
                            "conservative default (which false-positives on a "
                            "normal multi-commit cycle). Optional — omitting it "
                            "degrades to the default budget."
                        ))
    parser.add_argument("--sub-skill-args", default=None,
                        help=(
                            "Dispatched sub_skill_args for --cycle-begin. For an "
                            "execute-plan cycle this is the PLAN PART path; "
                            "--cycle-end reads the plan's phase count from it to "
                            "SCALE the execute-plan commit budget (one commit per "
                            "phase is normal — a fixed budget false-positives on a "
                            "4+ phase plan; hardening Round 20). Optional — omitting "
                            "it degrades to the fixed per-sub_skill budget."
                        ))
    # Phase 3/4: --emit-dispatch <class> assembles and registers a fully-bound
    # dispatch prompt for one of the seven dispatch classes (six from Phase 3
    # plus the Phase 4 'hardening' class).  It is an
    # action flag like --run-start: it exits immediately, does NOT run the
    # normal state computation, and does NOT require --repo-root.
    # Success → JSON {dispatch_prompt, dispatch_model, dispatch_class}, exit 0.
    # Refusal → JSON {dispatch_prompt: null, dispatch_model: null,
    #                  dispatch_class, dispatch_prompt_refused: <reason>}, exit 1.
    # Marker present → registers the emission (write-through to registry).
    # Marker absent  → peek semantics (prompt produced, no registry write).
    parser.add_argument("--emit-dispatch", metavar="CLASS",
                        help=(
                            "Emit a fully-bound dispatch prompt for the named "
                            "dispatch class (apply-resolution, input-audit, "
                            "investigation, recovery, coherence-recovery, "
                            "needs-runtime-redispatch, hardening). Outputs JSON and exits. "
                            "Marker present → registers the emission. "
                            "Marker absent → peek only (no registry write). "
                            "Use --context KEY=VALUE (repeatable) to supply "
                            "class-specific token bindings."
                        ))
    parser.add_argument("--context", action="append", metavar="KEY=VALUE",
                        default=[],
                        help=(
                            "Supply a context key=value for --emit-dispatch. "
                            "Repeatable. Split on the first '=' only."
                        ))
    # ISSUE 3 (d8-effect-chains live run, 2026-06-14): long/complex --context
    # values (e.g. a ~1500-char failure_summary with commas/colons/parens/newlines)
    # are brittle through the shell + a single inline --context flag. Two robust
    # large-value channels, both bypassing shell quoting entirely:
    #   --context-file PATH : read a JSON object {key: value, ...} from a file.
    #   --context-stdin     : read the SAME JSON object from stdin.
    # Both MERGE into the --context KEY=VALUE dict (inline --context wins on a key
    # collision, since it is the most explicit). Values may contain ANY characters
    # — newlines, commas, colons, parens — because JSON, not the shell, frames them.
    parser.add_argument("--context-file", default=None, metavar="PATH",
                        help=(
                            "With --emit-dispatch: read a JSON object of context "
                            "key/value pairs from PATH. Robust channel for long "
                            "values with punctuation/newlines that would be mangled "
                            "as inline --context KEY=VALUE. Merged with --context "
                            "(inline --context wins on collision)."
                        ))
    parser.add_argument("--context-stdin", action="store_true",
                        help=(
                            "With --emit-dispatch: read a JSON object of context "
                            "key/value pairs from stdin. Same merge semantics as "
                            "--context-file. Use for very large failure_summary "
                            "payloads piped from the orchestrator."
                        ))
    # Phase 7 WU-7.1 / WU-7.4: --run-end behavior modifiers.
    #   --ack-unhardened : proceed with --run-end even when unacked guard denials
    #                      remain in the deny ledger (the override is recorded in
    #                      the run-end output so retros can grade it).
    #   --next-route TEXT: the probed next route, REQUIRED for a checkpoint
    #                      run-end; written into lazy-run-checkpoint.json.
    # The run-end reason ({terminal,checkpoint}) reuses the existing free-text
    # --reason flag (default terminal) — see the run-end handler.
    parser.add_argument("--ack-unhardened", action="store_true",
                        help=(
                            "With --run-end: proceed even when unacked guard "
                            "denials remain in the deny ledger. The override is "
                            "recorded in the run-end output for retro grading."
                        ))
    # meta-dispatch-not-by-reference-and-ack-overpriced Fix Scope §1+§2: a
    # cheap per-entry ack CLI (with same-cause dedup) so a duplicate/no-fix/
    # already-fixed deny-ledger entry does not cost a full hardening dispatch.
    # Orchestrator-only (refused for a cycle subagent via
    # refuse_if_cycle_active, mirroring --backfill-receipts/--link-provenance).
    parser.add_argument("--ack-deny", default=None, metavar="SELECTOR",
                        help=(
                            "Cheaply retire unacked deny-ledger entry/entries "
                            "WITHOUT a full hardening dispatch. SELECTOR is "
                            "'oldest' (FIFO) or a denied_sha12 value/prefix. "
                            "Requires --resolution. Every OTHER unacked entry "
                            "sharing the same cause (identical denied_sha12, or "
                            "identical kind+reason_head) is deduped into the "
                            "same ack. Orchestrator-only."
                        ))
    parser.add_argument("--resolution", default=None, metavar="TEXT",
                        help="Audit note for --ack-deny (required, non-empty).")
    # efficacy-future-check-unenforced-orchestrator-prose (D1): the operator
    # override parallel to --ack-unhardened for the efficacy-flush gate — a
    # deliberate "no interventions/incidents exist, skip the trio" run-end. The
    # override is recorded in the run-end output for retro grading.
    parser.add_argument("--efficacy-skip-authorized", action="store_true",
                        help=(
                            "With --run-end: proceed even when the end-of-run "
                            "efficacy/canary/incident flush did not run this run "
                            "(no efficacy-flush breadcrumb). The override is "
                            "recorded in the run-end output for retro grading."
                        ))
    parser.add_argument("--next-route", default=None, metavar="TEXT",
                        help=(
                            "With --run-end --reason checkpoint: the probed next "
                            "route to resume with (written into the checkpoint "
                            "file and echoed by the next --run-start)."
                        ))
    # Phase 7 (lazy-validation-readiness) stop-authorization gates.
    # Motivating incident 2026-06-14: attended /lazy-batch 50 stopped at 5/50
    # without operator authorization.  These flags close the enforcement gap
    # between the prose-only prior constraint and the script gate.
    #
    # --unattended: pass at --run-start for scheduled/cron invocations.
    #   Interactive /lazy-batch does NOT pass it → defaults attended=True.
    #   An unattended run may checkpoint-stop without operator authorization
    #   (the sanctioned overnight-pause path).
    #
    # --operator-authorized: pass at --run-end when the operator has explicitly
    #   confirmed the stop via the budget-and-queue-guard AskUserQuestion.
    #   INDEPENDENT of --ack-unhardened (hardening-debt gate) — both gates can
    #   apply simultaneously; each checks its own concern.
    #
    # --terminal-reason REASON: supply the exact stop-terminal reason for
    #   --run-end --reason terminal.  If the reason is NOT in
    #   lazy_core.SANCTIONED_STOP_TERMINAL and --operator-authorized is absent,
    #   the run-end is REFUSED (exit 1, marker kept).  Omitting --terminal-reason
    #   is backward-compatible (legacy behavior) but adds a 'deprecation' note.
    parser.add_argument("--unattended", action="store_true",
                        help=(
                            "With --run-start: write attended=False into the run "
                            "marker (scheduled/cron/unattended invocation). "
                            "Interactive /lazy-batch does NOT pass this flag — the "
                            "default attended=True enables the stop-authorization "
                            "gate that prevents unilateral checkpoint stops."
                        ))
    parser.add_argument("--operator-authorized", action="store_true",
                        help=(
                            "With --run-end: bypass the stop-authorization gate "
                            "(checkpoint on attended run, or non-sanctioned terminal "
                            "reason). Pass ONLY after the operator explicitly confirms "
                            "the stop via the budget-and-queue-guard AskUserQuestion. "
                            "Independent of --ack-unhardened (hardening-debt gate)."
                        ))
    parser.add_argument("--terminal-reason", default=None, metavar="REASON",
                        help=(
                            "With --run-end --reason terminal: the explicit stop "
                            "reason token (e.g. 'all-features-complete', 'max-cycles'). "
                            "Must be in lazy_core.SANCTIONED_STOP_TERMINAL or "
                            "--operator-authorized must be passed. Omitting this flag "
                            "is backward-compatible but adds a deprecation note to the "
                            "output."
                        ))
    # Retro staleness anchor: the SINGLE source of truth for "how many phases
    # does this PHASES.md have right now". /retro's `phase_count_at_retro` writer
    # MUST use this (not an ad-hoc `grep -c '^### Phase'`) so the count it records
    # is byte-identical to what `retro_staleness()` later compares against via
    # `len(parse_phases(...))`. A divergent counter is exactly what produced the
    # d8-session-format permanent-stale loop (a `## Phase Summary` h2 the grep
    # missed but the old parse_phases regex over-counted). Prints the integer
    # count and exits; PHASES.md absent → prints 0.
    parser.add_argument("--count-phases", default=None, metavar="PHASES_PATH",
                        help=(
                            "Print len(parse_phases(PHASES_PATH)) and exit — the "
                            "canonical phase-section count for the retro staleness "
                            "anchor. Use this for `phase_count_at_retro`; never an "
                            "ad-hoc grep. Missing file → 0."
                        ))
    cli_surface.add_dump_cli_surface_flag(parser)
    cli_surface.add_ops_query_flags(parser)
    return parser


def main() -> int:
    # Eager-import the lazy_core package (PEP 562 facade) so a broken submodule
    # fails at process start, not at first attribute access (SPEC D4-A).
    lazy_core.load_all()

    parser = build_parser()
    args = parser.parse_args()

    _dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "lazy-state.py")
    if _dump is not None:
        return _dump

    # no-sanctioned-cli-for-queue-state-mutations: op-discoverability search —
    # read-only introspection, handled before any side effect (like the dump).
    _ops = cli_surface.maybe_handle_ops_query(args, parser, "lazy-state.py")
    if _ops is not None:
        return _ops

    # multi-repo-concurrent-runs: bind the active repo ONCE so claude_state_dir()
    # scopes all run-scoped state (marker/registry/ledger/cycle/checkpoint) to
    # this repo's subdir.  --repo-root defaults to os.getcwd(), so an explicit
    # flag or the cwd both bind correctly.  No-op when LAZY_STATE_DIR is set.
    lazy_core.set_active_repo_root(args.repo_root)

    # --repeat-count (advances the streak) and --repeat-count-peek (reads it
    # without advancing) are mutually exclusive — a single probe cannot both
    # advance and peek the persisted streak.
    if args.repeat_count and args.repeat_count_peek:
        _die("--repeat-count and --repeat-count-peek are mutually exclusive")

    # --park is the umbrella that arms BOTH park facets (needs-input + blocked),
    # matching the /lazy-batch `--park` invocation flag and `--set-park on`. Fold
    # it into the granular flags EARLY — BEFORE the pairing guard below and the
    # run-start marker threading — so every downstream read sees the same shape
    # whether the umbrella or the two granular flags were passed. (harden fix
    # lazy-run-marker-park-arm-and-forward-cycle-inflation: Step 0.55 forwards the
    # operator's `--park` verbatim; the CLI expands it here.)
    if getattr(args, "park_umbrella", False):
        args.park_needs_input = True
        args.park_blocked = True

    # park-provisional-acceptance (SPEC D1): --park-provisional is a strict
    # modifier of --park-needs-input — alone it is a hard CLI error, never a
    # silently-ignored token.
    if args.park_provisional and not args.park_needs_input:
        _die("--park-provisional requires --park-needs-input")

    # --count-phases: canonical phase-section count for the retro staleness
    # anchor. Exits immediately like the other action flags. Goes through the
    # SAME parse_phases() that retro_staleness() uses, so the written
    # phase_count_at_retro can never disagree with the later staleness compare.
    if args.count_phases is not None:
        phases_path = Path(args.count_phases)
        if not phases_path.exists():
            sys.stdout.write("0\n")
            return 0
        try:
            text = phases_path.read_text(encoding="utf-8")
        except OSError as exc:
            _die(f"--count-phases: cannot read {phases_path}: {exc}")
        sys.stdout.write(f"{len(lazy_core.parse_phases(text))}\n")
        return 0

    # multi-repo-concurrent-runs Phase 2 (WU-2.1): --marker-present — a read-only
    # presence query for the enforcement hooks.  Exits immediately like every
    # other action flag.  set_active_repo_root(args.repo_root) ran above, so
    # read_run_marker() resolves THIS repo's keyed state dir (or the exact
    # LAZY_STATE_DIR override under hermetic tests).  Read-only:
    # read_run_marker() uses claude_state_dir(create=False) internally, so a
    # probe that finds no marker never creates the state dir.  Exit 0 = a live
    # marker is present for this repo; exit 1 = absent (or stale / session-
    # mismatched).  Prints nothing (the exit code is the verdict).
    if args.marker_present:
        marker = lazy_core.read_run_marker(session_id=args.session_id)
        return 0 if marker is not None else 1

    # cycle-prompt-environment-dialect Phase 1: --marker-status — a
    # NEVER-THROWS mirror of --marker-present. read_run_marker() already
    # never raises (absent/corrupt/stale all resolve to None); this is
    # belt-and-braces so a future change to that contract can never turn
    # this probe into a traceback. Always exits 0.
    if args.marker_status:
        try:
            marker = lazy_core.read_run_marker(session_id=args.session_id)
            present = marker is not None
        except Exception:  # noqa: BLE001 — never-throws contract
            present = False
        sys.stdout.write(json.dumps({"present": present}) + "\n")
        return 0

    # cycle-subagent-fabricates-policy-or-stray-branch Phase 2: --marker-work-
    # branch — a read-only query mirroring --marker-present that ADDITIONALLY
    # prints the marker's work_branch. set_active_repo_root(args.repo_root) ran
    # above, so marker_work_branch() resolves THIS repo's keyed state dir. The
    # helper returns the branch (live marker carrying one) or None (absent /
    # stale / session-mismatched / legacy-no-branch). Read-only: it routes
    # through read_run_marker → claude_state_dir(create=False), so an absent
    # probe never creates the state dir. Exit 0 + print the branch when present;
    # exit 1 (no stdout branch) otherwise. The write-time stray-branch hook fails
    # OPEN on the exit-1 path (no known branch to enforce against).
    if args.marker_work_branch:
        branch = lazy_core.marker_work_branch(session_id=args.session_id)
        if branch:
            sys.stdout.write(branch + "\n")
            return 0
        return 1

    # adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke Phase 1
    # (Gap 2): --execute-plan-liveness — read-only pause-vs-terminal verdict for
    # a just-returned /execute-plan cycle. Shells the shared discriminator and
    # prints its JSON verdict. ALWAYS exits 0 (a probe never gates); a missing
    # --plan resolves fail-safe to terminal like any unreadable signal.
    if args.execute_plan_liveness:
        verdict = lazy_core.execute_plan_liveness(args.repo_root, args.plan or "")
        sys.stdout.write(json.dumps(verdict) + "\n")
        return 0

    # byref-updatedinput-unapplied-on-background-agent-dispatch WU-2:
    # --resolve-ref <nonce> — the subagent-side resolve of a consumed nonce's
    # registered prompt bytes (the platform drops the by-reference updatedInput
    # rewrite for the Agent tool, upstream #39814). set_active_repo_root ran
    # above, so resolve_consumed_emission_by_nonce resolves THIS repo's keyed
    # registry. Read-only, run-scoped, never un-consumes; deliberately NOT gated
    # by refuse_if_cycle_active (a dispatched subagent MUST be able to run it).
    # Hit → print the exact bytes + exit 0; miss → print nothing + exit 1.
    if args.resolve_ref is not None:
        resolved = lazy_core.resolve_consumed_emission_by_nonce(args.resolve_ref)
        if resolved:
            sys.stdout.write(resolved + "\n")
            return 0
        return 1

    # unified-pipeline-orchestrator Phase 1: --next-merged — read-only merged
    # work-list head. Reuses BOTH existing queue loaders (this script's
    # load_queue for features; bug-state.py's load_bug_queue for bugs, imported
    # via importlib because the filename is hyphenated) and the lazy_core
    # ordering helper (priority normalized across the two queues' divergent
    # tier/severity fields; feature breaks ties so only a genuine P0 bug precedes
    # a P1 feature; stable within each queue). Pure
    # ordering — it NEVER calls compute_state / re-infers per-item state. The
    # active repo was bound above, so repo_root in the output is the resolved
    # active repo. Prints JSON {item_id, type, repo_root} or null; exits like
    # every other action flag.
    if args.next_merged:
        repo_root = Path(args.repo_root)
        feature_items = load_queue(repo_root)
        bug_items = _load_bug_queue_for_merged(repo_root)
        # merged-head-actionability-oracle (SPEC L1/L5): EXCLUDE every
        # NON-DISPATCHABLE item so the merged head is the highest-priority item
        # that would actually DISPATCH, else the orchestrator routes to a head
        # that just re-parks/re-defers/halts (deadlock). This is a STATELESS
        # read-only ordering query — there is no live probe, so there is no
        # same-pipeline skip context to reuse (L2): EVERY at-or-above candidate
        # is scoped-probed via a TYPE-AWARE `scoped_probe` (feature → this
        # module's `compute_state`, bug → bug-state's), honoring the SAME run
        # flags a real probe would use. Effective (marker-authoritative) park
        # facets so a mid-run --set-park toggle takes effect; a dispatchable head
        # short-circuits the walk (byte-identical common path when the head is
        # dispatchable — the head is probed once and the loop stops).
        _nm_marker = lazy_core.read_run_marker()
        _nm_ni, _nm_bl, _nm_pv = lazy_core.fold_park_flags(
            args.park_needs_input, args.park_blocked, args.park_provisional, _nm_marker
        )
        _nm_bug_state_mod = _load_bug_state_module()
        _nm_real_device = resolve_real_device(args.real_device)
        _nm_types = {}
        for _it in feature_items:
            if isinstance(_it, dict) and _it.get("id"):
                _nm_types[_it["id"]] = "feature"
        for _it in bug_items:
            if isinstance(_it, dict) and _it.get("id"):
                _nm_types.setdefault(_it["id"], "bug")

        def _nm_scoped_probe(_iid):
            try:
                if _nm_types.get(_iid) == "bug":
                    if _nm_bug_state_mod is None:
                        return {}
                    return _nm_bug_state_mod.compute_state(
                        repo_root, cloud=args.cloud, real_device=_nm_real_device,
                        scope_bug_id=_iid,
                        park_needs_input=_nm_ni, park_blocked=_nm_bl,
                        park_provisional=_nm_pv,
                        strict_research_halt=args.strict_research_halt,
                    )
                return compute_state(
                    repo_root, cloud=args.cloud,
                    skip_needs_research=args.skip_needs_research,
                    real_device=_nm_real_device, scope_feature_id=_iid,
                    park_needs_input=_nm_ni, park_blocked=_nm_bl,
                    park_provisional=_nm_pv,
                    strict_research_halt=args.strict_research_halt,
                )
            except Exception:  # noqa: BLE001 — a per-candidate probe error must not break the ordering query
                return {}

        _nm_diag_snapshot = list(lazy_core._DIAGNOSTICS)
        try:
            _nm_excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
                feature_items, bug_items, str(repo_root), None,
                scoped_probe=_nm_scoped_probe,
            )
        finally:
            lazy_core._DIAGNOSTICS[:] = _nm_diag_snapshot
        head = lazy_core.next_merged(
            feature_items, bug_items, lazy_core.active_repo_root(),
            exclude_ids=_nm_excluded,
        )
        sys.stdout.write(json.dumps(head) + "\n")
        return 0

    # unified-pipeline-orchestrator Phase 5 / long-build-and-runtime-ownership
    # Phase 2 (LD2/LD3): --ensure-runtime — the M4 liveness/recovery verdict
    # {state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}
    # (the Step-1d.0 dance). Production uses the real urllib probe + dev:restart;
    # the AlgoBooth specifics live in lazy_core's default config dict (repo-agnostic
    # parameterization).
    #
    # Identity is engaged by threading the LIVE run identity as live_session_id:
    # the run marker's session_id is the controller_session_id recorded into
    # `.runtime.lock.json` (Phase 1 Integration Note — the run marker is the stable
    # run identity, NOT a second minted id). With a live marker the handler emits
    # the verifiable-ownership verdict (READY/STALE/HIJACKED/DEAD/BLOCKED); with no
    # marker (interactive, no run) live_session_id is None → ensure_runtime falls
    # back to the legacy boot/ready flow (still a verdict superset). Best-effort:
    # a marker-read error degrades to legacy mode, never blocks the subcommand.
    if args.ensure_runtime:
        live_session_id = None
        try:
            _marker = lazy_core.read_run_marker()
            if isinstance(_marker, dict):
                live_session_id = _marker.get("session_id")
        except Exception:  # noqa: BLE001 — fail-open to legacy mode
            live_session_id = None
        # ensure-runtime-recovery-starves-cold-compile (Phase 3): the production
        # two-port cold-compile discriminator needs NO new handler argument — the
        # default config (`_ENSURE_RUNTIME_DEFAULT_CONFIG`) carries the `:1420`
        # frontend keys, so `ensure_runtime` auto-binds the real
        # `_default_frontend_probe` (Phase 1 default-binding). The handler stays a
        # thin marker-read + delegate; the frontend probe is wired entirely inside
        # `lazy_core.ensure_runtime` from the config — no manual classification or
        # probe construction here. A repo without a :1420 frontend overrides the
        # key off in its own config (then the discriminator degrades to the
        # :3333-only DEAD path, byte-identical to before this fix).
        #
        # ensure-runtime-starves-pre-vite-sidecar-build (Phase 3, CLI-seam WIRED):
        # the pre-Vite boot-liveness signal ALSO needs NO new handler argument — it
        # is wired the same config-driven way. `boot_liveness` is now ENABLED in the
        # base default config (`_ENSURE_RUNTIME_DEFAULT_CONFIG`), so this no-config
        # production call auto-binds the boot-liveness source inside `ensure_runtime`
        # (a per-repo override may still set it `False` to opt OUT). The source is
        # the in-process `Popen` handle the production `restart()` closure spawns and
        # stashes in a closure-shared holder (`.poll()` None ⇒ the cold pre-Vite
        # `BeforeDevCommand`/`sidecar:build` window is in progress ⇒ alive). It lives
        # ENTIRELY inside the single `ensure_runtime` call, so the handler needs no
        # real handle and `--test` stays hermetic (tests inject `restart`/`boot_alive`
        # — with no boot spawned the holder is empty and the signal fail-safes to
        # NOT-booting, so an injected `boot_alive` still wins). The signal is
        # fail-safe by construction: with no live boot a both-ports-down host still
        # classifies `dead` and reaches bounded recovery. The existing
        # `live_session_id` threading from the run marker is UNCHANGED.
        result = lazy_core.ensure_runtime(
            Path(args.repo_root), live_session_id=live_session_id
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    # unified-pipeline-orchestrator Phase 5: --gate-coverage — deterministic,
    # symlink-resolving Gate-1 verdict. Exit 1 iff any decision uncovered so the
    # orchestrator's && chains short-circuit (parity with --verify-ledger).
    if args.gate_coverage is not None:
        result = lazy_core.gate_coverage(Path(args.gate_coverage))
        # harness-telemetry-ledger Phase 2 (D4-B): an exit-1 Gate-1 verdict is a
        # `gate-refusal` event (marker-gated + fail-open; adds NO output keys).
        if result["uncovered"]:
            lazy_core.append_telemetry_event(
                "gate-refusal",
                item_id=Path(args.gate_coverage).resolve().parent.name,
                data={"gate": "gate-coverage", "uncovered": result["uncovered"]},
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if not result["uncovered"] else 1

    # Phase 1 run-lifecycle dispatch: --run-start / --run-end exit immediately
    # like all other action flags so they compose cleanly with orchestrator
    # scripting (e.g. ``python lazy-state.py --run-start --cloud --max-cycles 20``).
    # lazy-cycle-containment C1 (Phase 2): cycle-marker bracket dispatch.  Like
    # all action flags these exit immediately.
    # cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE): a SUBAGENT must
    # not arm/clear the containment marker. Guard at the ENTRY of both handlers,
    # BEFORE any marker write/clear, via the dedicated marker-mutation guard
    # (keys on the POSITIVE LAZY_ORCHESTRATOR signal — NOT the plain
    # refuse_if_cycle_active marker-fallback, which would refuse the
    # orchestrator's own bracket because --cycle-begin/--cycle-end run WHILE the
    # marker is present). The orchestrator exports LAZY_ORCHESTRATOR=1 (Phase 1),
    # so its self-healing overwrite + bracket teardown are unaffected.
    if args.record_resolution_signal:
        # loop-detected-false-positives-from-probe-and-reboot-churn (symptom 3):
        # persist the one-shot resolution signal so the next same-step probe
        # resets step_repeat_count. Marker-gated inside the helper (no-op when no
        # run marker). Orchestrator-only at the apply-resolution bracket.
        if not args.feature_id or not args.current_step:
            _die("--record-resolution-signal requires --feature-id and --current-step")
        marker = lazy_core.record_resolution_signal(
            {"feature_id": args.feature_id, "current_step": args.current_step}
        )
        # budget-guard-defers-near-complete-feature Phase 2 (WU-5): the
        # apply-resolution bracket IS the corrective-cycle bracket — a
        # validation-failure-driven corrective dispatch is recorded here. Fold a
        # sibling per_feature_corrective_cycles increment so budget_trip_signals
        # discounts this corrective work from the budget trip count (Theory 2).
        # Marker-gated (record_resolution_signal returns None when no run marker)
        # + FAIL-OPEN (a persist error never breaks the resolution dispatch).
        if isinstance(marker, dict):
            try:
                marker = lazy_core.record_corrective_cycle(marker, args.feature_id)
                _bg_marker_path = (
                    lazy_core.claude_state_dir() / lazy_core._MARKER_FILENAME
                )
                lazy_core._atomic_write(
                    _bg_marker_path, json.dumps(marker, indent=2) + "\n"
                )
            except (OSError, ValueError):
                pass
        sys.stdout.write(json.dumps(marker, indent=2) + "\n")
        return 0

    if args.cycle_begin:
        lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-begin")
        if not args.feature_id or not args.nonce:
            _die("--cycle-begin requires --feature-id and --nonce")
        # adhoc-cycle-begin-real-requires-sub-skill: a --kind real dispatch that
        # omits --sub-skill writes a marker with sub_skill=None, which makes the
        # --cycle-end commit budget indeterminate (the recurring unexpected-
        # commits false-positive class). Require it up front, before any marker
        # mutation. --kind meta remains exempt (see lazy_core.py:10962).
        if args.kind == "real" and not (args.sub_skill or "").strip():
            _die("--cycle-begin --kind real requires --sub-skill")
        # hardening-blind-to-process-friction Phase 2 (D1): snapshot the run
        # identity (the live run marker's started_at — None when no run is live)
        # and the current HEAD sha into the cycle marker, so --cycle-end can
        # detect a torn bracket / unexpected commits. Both reads are best-effort:
        # a missing run marker / non-git tree degrades to None (no false positive).
        run_marker = lazy_core.read_run_marker()
        run_started_at = (run_marker or {}).get("started_at")
        begin_head_sha = lazy_core.head_sha_snapshot(Path(args.repo_root))
        # long-build-and-runtime-ownership Phase 4 (M5 Detect / LD4): BEFORE the
        # cycle marker write, reconcile a torn-build git-consistency delta left by
        # a PREVIOUS torn cycle — a pre-boot `.git/index.lock` (mtime older than
        # this run's boot stamp) ⇒ remove it and `git clean -fdx` the staging dir.
        # The boot stamp is the run marker's started_at parsed to epoch (None when
        # no run marker is live → the helper fail-safe-preserves any lock). This
        # COMPOSES with the --cycle-end friction detector: it makes no commits and
        # never touches the run marker, so a reconciled delta cannot false-trip
        # unexpected-commits / cycle-bracket-break. Best-effort + FAIL-OPEN — any
        # error degrades to a no-op so the marker write always proceeds.
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
            feature_id=args.feature_id, nonce=args.nonce, kind=args.kind,
            run_started_at=run_started_at, begin_head_sha=begin_head_sha,
            sub_skill=args.sub_skill, sub_skill_args=args.sub_skill_args,
        )
        # harness-telemetry-ledger Phase 2 (D4-B): cycle-bracket emission.
        # Marker-gated inside the emitter (no live run → no line) and fail-open
        # (a write failure never blocks the bracket); adds NO output keys.
        lazy_core.append_telemetry_event(
            "cycle-begin", item_id=args.feature_id,
            data={"kind": args.kind, "sub_skill": args.sub_skill},
        )
        out: dict = dict(marker)
        if reconciliation is not None and reconciliation.get("reconciled"):
            out["git_consistency_reconciliation"] = reconciliation
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.cycle_end:
        # cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE): refuse a
        # subagent's marker clear BEFORE the friction check / clear_cycle_marker
        # run (zero side effects). The orchestrator (LAZY_ORCHESTRATOR=1) is
        # allowed to clear its own bracket under its live marker.
        lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-end")
        # hardening-blind-to-process-friction Phase 2 (D1): check the two
        # process-friction signals BEFORE clearing the marker; on a hit, append a
        # kind: process-friction entry to the deny ledger (best-effort, never
        # blocks the clear).
        # harness-telemetry-ledger Phase 2: capture the cycle identity BEFORE
        # the clear (read-only) so the cycle-end event carries the item id.
        _tl_cycle = lazy_core.read_cycle_marker()
        # mechanize-prose-only-orchestrator-contracts (b) / D2-A: arm the
        # post-cycle input-audit obligation when the ending cycle was a
        # /spec or plan-feature cycle. record_audit_obligation is a no-op on
        # a non-audited sub_skill and marker-gated (no-op with no live run),
        # so this is byte-identical unless the withhold actually applies.
        # adhoc-audit-obligation-fires-on-zero-commit-failed-cycle: pass the
        # commit-delta signal (begin vs current HEAD) so a ZERO-COMMIT (failed /
        # no-op) close arms NO obligation, and a real-commit close records the
        # bracket's ACTUAL end sha + subject. The summary git call is skipped on
        # the zero-commit path (the hot failed-cycle path this bug targets).
        if _tl_cycle is not None:
            _aud_begin = _tl_cycle.get("begin_head_sha")
            _aud_end = lazy_core.head_sha_snapshot(Path(args.repo_root))
            _aud_summary = (
                lazy_core.head_commit_subject(Path(args.repo_root))
                if _aud_end and _aud_end != _aud_begin
                else None
            )
            lazy_core.record_audit_obligation(
                item_id=_tl_cycle.get("feature_id"),
                cycle_kind=_tl_cycle.get("sub_skill"),
                begin_head_sha=_aud_begin,
                end_sha=_aud_end,
                cycle_summary=_aud_summary,
            )
        friction = lazy_core.cycle_end_friction_check(repo_root=Path(args.repo_root))
        # code-doc-provenance-linkage Phase 1 (D4-A): record this cycle's commit
        # bracket (marker begin_head_sha → current HEAD) into the state-dir
        # bracket ledger BEFORE clearing the marker. Fail-open — a degraded
        # snapshot / write failure returns None and never blocks the clear.
        bracket = lazy_core.record_cycle_commit_bracket(
            repo_root=Path(args.repo_root)
        )
        # cycle-budget-counters-double-count-on-probes-and-inject-hook: THE budget
        # authority for bracketed Agent dispatches. A completed --cycle-begin/
        # --cycle-end bracket wraps exactly one dispatch, so count it here keyed on
        # the cycle marker's --kind: real → forward_cycles (+ per-feature sibling),
        # meta → meta_cycles. Read BEFORE clear_cycle_marker() so the marker's kind
        # is still available. Marker-gated (no run marker → no-op) and idempotent
        # per bracket (the marker is cleared right below). This replaces the removed
        # probe-path forward advance and the --emit-dispatch meta advance.
        lazy_core.advance_cycle_bracket_counter(_tl_cycle)
        cleared = lazy_core.clear_cycle_marker()
        # harness-telemetry-ledger Phase 2 (D4-B): cycle-bracket emission
        # (marker-gated + fail-open inside the emitter; adds NO output keys).
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
        # lazy-cycle-containment C3 (Phase 3): refuse the orchestrator-only op if
        # a cycle subagent is mid-dispatch (the cycle marker is present).  Zero
        # side effects on refusal (the guard exits before write_run_marker).
        lazy_core.refuse_if_cycle_active("--run-start")
        # D-B (hardening-blind-to-process-friction, 2026-06-16): refuse to CLOBBER
        # a live run marker owned by a DIFFERENT pipeline (e.g. a nested feature
        # --run-start overwriting an active bug run marker). Same-pipeline
        # re-run-start (checkpoint resume) is allowed. Zero side effects on refusal.
        lazy_core.refuse_run_start_clobber("feature")
        # Write the marker for the feature pipeline.  cloud, repo_root, and
        # max_cycles are taken from the matching existing flags so no new flags
        # are needed for those values.
        # Phase 7 / lazy-validation-readiness: pass attended=not args.unattended
        # so interactive /lazy-batch runs (which do NOT pass --unattended) default
        # to attended=True, enabling the stop-authorization gate on --run-end.
        # Scheduled/cron invocations pass --unattended → attended=False → the
        # overnight-pause checkpoint path is allowed without operator authorization.
        # single-slot-marker-ownership-race-disarms-owning-run Phase 1: thread the
        # orchestrator's known owning session_id into the marker so it is born
        # OWNER-BOUND rather than bind-pending — closing the UNBOUND→wrong-bind
        # window at its source (Repro A + Repro B, since the resume --run-start
        # carries --session-id too). A foreign session can no longer be the first
        # writer of the slot. When args.session_id is absent (legacy/manual
        # --run-start with no --session-id), write_run_marker still stamps
        # session_id=None exactly as before and the run falls back to the
        # _bind_marker_on_allow anchor — the fix is additive, no regression.
        # parallel-worktree-batch-execution (D2-A): validate + thread the
        # optional sanctioned-lane identity stamp. Malformed → _die exit 2
        # BEFORE any marker write (zero side effects); absent → parent_run
        # stays None and the marker is byte-identical to a serial run's.
        parent_run = lazy_core.parse_parent_run_arg(args.parent_run)
        marker = lazy_core.write_run_marker(
            pipeline="feature",
            cloud=args.cloud,
            repo_root=args.repo_root,
            max_cycles=args.max_cycles,
            session_id=args.session_id,
            attended=not args.unattended,
            parent_run=parent_run,
            # lazy-batch-no-mid-run-budget-or-park-controls: SEED park mode into
            # the marker from the invocation --park flags so the probe reads it
            # each cycle and --set-park can toggle it in place. Default False →
            # byte-identical to a non-park run's marker.
            park_needs_input=args.park_needs_input,
            park_blocked=args.park_blocked,
            park_provisional=args.park_provisional,
        )
        out: dict = dict(marker)
        # Phase 7 WU-7.4: consume any checkpoint left by a prior checkpoint
        # run-end and echo it as resume context (consume-once — the file is
        # deleted on read).  No checkpoint → field omitted.
        checkpoint = lazy_core.consume_run_checkpoint()
        if checkpoint is not None:
            out["resumed_from_checkpoint"] = checkpoint
            # ROOT-CAUSE FIX (mid-run counter reset, 2026-06-14): write_run_marker
            # above ZEROED forward_cycles/meta_cycles. A checkpoint resume is the
            # SAME run continuing after a sanctioned pause, so its monotonic
            # counters must carry forward (HARD CONSTRAINT 8 — never reset within a
            # run). restore_checkpoint_counters re-applies the paused counts to the
            # marker; reflect them in the echoed --run-start output so the
            # orchestrator's banner/headers show the continued totals, not 0/0.
            #
            # operator-checkpoint-resume-counter-reset (2026-06-17): the carry-forward
            # now fires ONLY for NON-operator-authorized resumes (automatic
            # reliability pauses + pre-fix checkpoint files). An operator-authorized
            # checkpoint is a deliberate /lazy-batch <N> re-invoke wanting a FRESH
            # 0/0 budget — restore_checkpoint_counters returns None for it (no-op),
            # so the marker keeps its just-written 0/0 and these lines are skipped.
            # The branch lives ENTIRELY in the helper (one decision site, shared
            # with bug-state.py); no logic change here.
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            if restored is not None:
                out["forward_cycles"] = restored.get("forward_cycles")
                out["meta_cycles"] = restored.get("meta_cycles")
                out["last_advance_consume_count"] = restored.get(
                    "last_advance_consume_count"
                )
            # checkpoint-resume-false-loop-flips-complex-part-to-sonnet (2026-07-12):
            # --run-end deleted the prompt registry and this --run-start recreated
            # it fresh, so the loop-debounce consume_count baseline in the OS-temp
            # signature file is now stale (registry-relative to the PRE-checkpoint
            # run). Re-baseline it to the fresh registry count so the first re-probe
            # of the deterministically-re-probed next_route HOLDS instead of
            # inflating repeat_count to 2 (false LOOP DETECTED). Preserves a genuine
            # pre-pause streak; no-op + fail-open when no signature file / no marker.
            lazy_core.rebaseline_loop_signature_after_registry_reset(
                Path(lazy_core.active_repo_root()), pipeline="feature"
            )
        # harness-telemetry-ledger Phase 2 (D4-B): run-bracket emission —
        # fires AFTER write_run_marker so the fresh marker supplies the run
        # identity (marker-gated + fail-open inside the emitter; no output keys).
        lazy_core.append_telemetry_event(
            "run-start",
            data={"cloud": args.cloud, "max_cycles": args.max_cycles,
                  "resumed_from_checkpoint": checkpoint is not None},
        )
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.run_end:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch.  Guard fires before any marker/registry deletion.
        lazy_core.refuse_if_cycle_active("--run-end")
        # Phase 7: the run-end reason reuses the existing free-text --reason flag
        # (default "terminal"; "checkpoint" triggers the WU-7.4 checkpoint write).
        reason = args.reason or "terminal"
        if reason not in ("terminal", "checkpoint"):
            _die("--run-end --reason must be 'terminal' or 'checkpoint'")

        # lazy-batch-parallel-run-harness-gaps gaps 4+5: a /lazy-batch-parallel
        # LANE marker carries a non-null `parent_run` (the coordinator's identity).
        # A lane is a coordinator-authorized CHILD retirement, not a top-level run
        # boundary — so (gap 5) it does NOT owe the efficacy/canary/incident trio
        # (the PARENT owes it once at the coordinator flush, SKILL Step 6.3), and
        # (gap 4) it may retire on a park-class terminal without
        # --operator-authorized (SKILL P6 park is the parallel mode's defining
        # failure isolation). Read the marker RAW (non-deleting) once here.
        _re_marker = lazy_core.read_run_marker()
        _is_lane_marker = bool(
            isinstance(_re_marker, dict) and _re_marker.get("parent_run")
        )

        # WU-7.1: refuse to retire the marker while unacked guard denials remain,
        # unless --ack-unhardened was passed (the override is recorded for retros).
        # This gate is INDEPENDENT of the Phase 7 stop-authorization gate below —
        # both can apply; each checks its own concern.
        pending = lazy_core.pending_hardening()
        override_note = None
        if pending > 0:
            if not args.ack_unhardened:
                # Refuse: marker is LEFT IN PLACE so the run is not falsely retired.
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
                # run-end-gate-refusals-no-telemetry-event: observability-only
                # gate-refusal emission (marker-gated, fail-open, ZERO state
                # side effects) immediately before the UNCHANGED refusal return.
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
            acked_n = lazy_core.ack_all_unacked_denies()
            override_note = (
                f"OVERRIDE: --ack-unhardened retired the run and acked {acked_n} "
                f"pending deny-ledger entry(ies) (operator-authorized blanket ack)."
            )

        # -----------------------------------------------------------------------
        # efficacy-future-check-unenforced-orchestrator-prose (D1): the
        # end-of-run efficacy/canary/incident trio must flush before the run is
        # retired.  MIRRORS the unacked-hardening gate above: refuse (exit 1,
        # marker LEFT IN PLACE) unless the trio dropped its run-scoped breadcrumb
        # this run, or --efficacy-skip-authorized retro-grades a deliberate skip.
        # Applies to checkpoint run-ends too (a checkpoint is a run boundary; the
        # loop must flush there as well — this session's real skip was a
        # checkpoint).  The check reads the marker RAW (non-deleting), so it never
        # perturbs the idempotent teardown below.
        # -----------------------------------------------------------------------
        efficacy_skip_note = None
        if _is_lane_marker:
            # gap 5: a lane child never owes the trio — the parent coordinator
            # flushes it once at Step 6.3. Skipping keeps lane retirement clean
            # (a lane cannot run the trio; it retires before the serial tail).
            pass
        elif not lazy_core.efficacy_breadcrumb_present():
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
                # run-end-gate-refusals-no-telemetry-event: observability-only
                # gate-refusal emission (marker-gated, fail-open, ZERO state
                # side effects) immediately before the UNCHANGED refusal return.
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
        #
        # Motivating incident 2026-06-14: an attended /lazy-batch 50 run stopped
        # at 5/50 cycles via --run-end --reason checkpoint without operator
        # authorization.  These gates make unilateral stops mechanically impossible.
        #
        # CHECKPOINT GATE: an attended run may NOT checkpoint-stop without
        #   --operator-authorized.  The marker's attended field defaults to True
        #   when absent (legacy marker → stricter gate = safer default).
        #   Unattended runs and operator-authorized stops proceed normally.
        #
        # TERMINAL-REASON GATE: if --terminal-reason is supplied, it must be in
        #   lazy_core.SANCTIONED_STOP_TERMINAL or --operator-authorized must be
        #   present.  A fabricated/unknown reason is refused.  Omitting
        #   --terminal-reason is backward-compatible but adds a deprecation note.
        #
        # CRITICAL: on ANY refusal, the marker MUST be left on disk.  A refused
        # stop must not retire the run — the orchestrator must continue or
        # escalate to the operator AskUserQuestion path.
        # -----------------------------------------------------------------------

        if reason == "checkpoint":
            # Read the marker to learn attendedness.  Default True when marker
            # is absent or lacks the 'attended' field (legacy → stricter gate).
            marker_now = lazy_core.read_run_marker()
            attended = True  # fallback: absent/legacy marker → treated as attended
            if marker_now is not None:
                attended = marker_now.get("attended", True)

            if attended and not args.operator_authorized:
                # REFUSE: keep marker + registry in place.  The orchestrator
                # must either continue the loop or route through the operator
                # AskUserQuestion and pass --operator-authorized only after
                # confirmation.  An attended run may never checkpoint-stop
                # unilaterally (this is the core fix for the 2026-06-14 incident).
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
                # run-end-gate-refusals-no-telemetry-event: observability-only
                # gate-refusal emission (marker-gated, fail-open, ZERO state
                # side effects) immediately before the UNCHANGED refusal return.
                lazy_core.append_telemetry_event(
                    "gate-refusal",
                    item_id=None,
                    data={"gate": "checkpoint-auth", "op": "--run-end",
                          "reason": "attended checkpoint stop without operator "
                                    "authorization"},
                )
                return 1
            # Attended + authorized, or unattended: fall through to WU-7.4 below.

        elif reason == "terminal":
            # TERMINAL-REASON GATE: validate the supplied reason against the
            # sanctioned set.  Backward-compatible: omitting --terminal-reason
            # is allowed but adds a deprecation note (the caller should migrate).
            terminal_reason = getattr(args, "terminal_reason", None)
            if terminal_reason is not None:
                # gap 4: a lane marker (parent_run set) may retire on a park-class
                # terminal (SKILL P6 park / budget-deferred) WITHOUT
                # --operator-authorized — the coordinator authorized the lane, and
                # park-on-sentinel is the parallel mode's defining failure
                # isolation. Serial runs (not a lane marker) are unaffected: the
                # lane set is consulted only when _is_lane_marker holds.
                _lane_sanctioned = (
                    _is_lane_marker
                    and terminal_reason in lazy_core.SANCTIONED_LANE_PARK_TERMINAL
                )
                if (terminal_reason not in lazy_core.SANCTIONED_STOP_TERMINAL
                        and not _lane_sanctioned
                        and not args.operator_authorized):
                    # REFUSE: non-sanctioned reason without authorization.
                    # Marker LEFT IN PLACE.
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
                # Sanctioned reason or operator-authorized: proceed.
            # else: terminal_reason is None → backward-compatible (deprecation
            # note added to the output below after deletion).

        # WU-7.4 checkpoint: requires --next-route, and writes the checkpoint
        # file BEFORE the marker/registry are cleared (it folds the marker's
        # counters as they stand at run end).
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
                operator_authorized=bool(args.operator_authorized),
            )

        # harness-telemetry-ledger Phase 2 (D4-B): run-bracket emission — MUST
        # fire BEFORE delete_run_marker (the marker supplies the run identity),
        # and before the D5-B flush so the run-end line rides the segment.
        lazy_core.append_telemetry_event(
            "run-end",
            data={"reason": reason,
                  "terminal_reason": getattr(args, "terminal_reason", None)},
        )
        # D5-B cloud run-end flush: persist this cloud run's ledger segment into
        # the repo (docs/telemetry/cloud/) so it rides the final commit+push.
        # No-op (None) for workstation runs / no matching events; fail-open.
        telemetry_flushed = lazy_core.flush_cloud_telemetry_segment(
            Path(args.repo_root)
        )

        # mechanize-prose-only-orchestrator-contracts (d): script-fired flush
        # notification — the run's end-of-run flush state transition (the
        # SPEC's 3rd event point). Read the marker BEFORE deletion for the
        # run summary; the identity includes started_at so distinct runs
        # never dedup against each other's flush.
        _flush_marker = lazy_core.read_run_marker()
        if _flush_marker is not None:
            lazy_core.notify_event(
                "flush", f"run flushed ({reason})", str(args.repo_root),
                item_id=_flush_marker.get("started_at"),
                detail=(
                    f"forward={_flush_marker.get('forward_cycles')} "
                    f"meta={_flush_marker.get('meta_cycles')} reason={reason}"
                ),
            )
        # Delete the marker AND the registry (both are run-scoped state).
        # clear_registry=True ensures the prompt registry does not bleed
        # across runs — entries from a previous run must never be dispatchable
        # in the next run's fresh startup.
        deleted = lazy_core.delete_run_marker(clear_registry=True)
        # efficacy-future-check-unenforced-orchestrator-prose (D1): the run is
        # retired — clear the run-scoped efficacy-flush breadcrumb so the next run
        # starts clean (run-scoping already prevents cross-run bleed; this is
        # tidy-up).
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
        # callers that omit --terminal-reason.
        if reason == "terminal" and not getattr(args, "terminal_reason", None):
            result_out["deprecation"] = (
                "--run-end --reason terminal should pass --terminal-reason <reason> "
                "for stop-authorization validation (Phase 7 / lazy-validation-readiness). "
                "Sanctioned reasons: " + str(sorted(lazy_core.SANCTIONED_STOP_TERMINAL))
            )
        sys.stdout.write(json.dumps(result_out, indent=2) + "\n")
        return 0

    # Phase 3: --emit-dispatch exits immediately like all other action flags.
    # Pipeline is always "feature" for lazy-state.py (the feature pipeline script).
    if args.emit_dispatch is not None:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch.  Guard fires before any prompt assembly / registry write.
        lazy_core.refuse_if_cycle_active("--emit-dispatch")
        cls = args.emit_dispatch
        # ISSUE 3 (d8-effect-chains live run): the ENTIRE handler is wrapped so it
        # NEVER emits non-JSON / partial output. Any failure — a bad --context-file
        # path, malformed context JSON, an unexpected exception inside the
        # assembler — is caught and surfaced as a structured JSON error object on
        # stdout (exit 1), never a bare traceback or empty stdout. The live run's
        # failure mode was a long --context value parsed to all-None fields; a
        # structured error object lets the orchestrator detect+retry instead of
        # silently proceeding on garbage.
        try:
            # Parse repeatable --context KEY=VALUE flags into a dict (split on first =).
            # The robust large-value channels (--context-file / --context-stdin)
            # are MERGED in first; inline --context wins on a key collision.
            context: dict = {}
            if args.context_file is not None:
                file_obj = lazy_core.load_context_json(
                    Path(args.context_file).read_text(encoding="utf-8")
                )
                context.update(file_obj)
            if args.context_stdin:
                context.update(lazy_core.load_context_json(sys.stdin.read()))
            for kv in (args.context or []):
                if "=" in kv:
                    key, _, value = kv.partition("=")
                    context[key] = value
            # no-mid-run-observed-friction-harden-dispatch §1: normalize a
            # hardening dispatch's context so the dispatch-hardening.md template's
            # shared @requires evidence keys resolve for EVERY trigger_kind. An
            # observed-friction dispatch supplies friction_summary/friction_detail/
            # blocking in place of the denial-specific keys; the normalizer rebinds
            # them into denied_prompt_summary/denial_reason (the same rebind the
            # process-friction branch performs) and injects observed-friction
            # probe_json/registry_state placeholders. Auto-trigger dispatches pass
            # through with only the {blocking} default added.
            if cls == "hardening":
                context = lazy_core.normalize_hardening_dispatch_context(context)
            # mechanize-prose-only-orchestrator-contracts (c) / D3-A: an
            # apply-resolution dispatch's chosen_path/resolution_summary are
            # bound from the recorded decision (--record-decision), not
            # trusted from orchestrator-typed context. Raises (caught by the
            # except below, formatted into the standard structured refusal)
            # when sentinel_path is named but no record exists yet.
            context = lazy_core.bind_decision_record_context(
                cls, context, "lazy-state.py",
            )
            result = lazy_core.emit_dispatch_prompt(
                cls, context,
                pipeline="feature",
                cloud=args.cloud,
            )
        except Exception as exc:  # noqa: BLE001
            # ISSUE 3: emit a STRUCTURED JSON error object for ANY failure (unknown
            # class ValueError, unreadable --context-file, malformed context JSON,
            # or an unexpected internal error) — never a bare traceback / empty
            # stdout. `error_kind` lets the orchestrator distinguish a context
            # parse/IO problem (retry with a fixed payload) from a genuine refusal.
            sys.stdout.write(json.dumps({
                "dispatch_prompt": None,
                "dispatch_model": None,
                "dispatch_class": cls,
                "dispatch_prompt_refused": str(exc),
                "error_kind": type(exc).__name__,
            }, indent=2) + "\n")
            return 1
        if result.get("ok"):
            prompt = result["prompt"]
            model = result["model"]
            # Marker present → register the emission (write-through to registry).
            # Marker absent  → peek semantics (prompt produced, no registry write).
            # Phase 7 (lazy-validation-readiness) Deliverable 3: capture the
            # returned entry so we can surface dispatch_prompt_ref (@@lazy-ref
            # nonce=<hex>) in the output JSON — mirrors how --emit-prompt adds
            # cycle_prompt_ref (lazy-state.py ~5266-5276 from Phase 3).
            # The guard's existing @@lazy-ref resolution path resolves any
            # registered class, so meta dispatches (apply-resolution, hardening,
            # etc.) can be dispatched by reference without any guard edit.
            _ref_entry = lazy_core.register_emission_if_marked(
                prompt, cls,
                item_id=context.get("item_id"),
                model=model,
            )
            # cycle-budget-counters-double-count-on-probes-and-inject-hook: the
            # meta-cycle advance formerly fired HERE at --emit-dispatch. It has moved
            # to the --cycle-end bracket (advance_cycle_bracket_counter, keyed on the
            # cycle marker's --kind meta) — every meta/recovery/apply-resolution/
            # hardening dispatch is bracketed --kind meta, so counting at emit AND at
            # the bracket would double-count. --cycle-end is now the sole budget
            # authority for bracketed dispatches; emit no longer touches the budget.
            # mechanize-prose-only-orchestrator-contracts (b) / D2-A: a
            # REGISTERED (marker-present) input-audit emission discharges the
            # D2-A obligation — this IS the "the audit dispatch itself" the
            # SPEC names as the discharge transaction. A no-marker peek
            # (_ref_entry is None) never discharges (nothing was dispatched).
            if _ref_entry is not None and cls == "input-audit":
                lazy_core.discharge_audit_obligation()
            # Phase 8 WU-8.2: emission no longer acks the deny ledger.  The ack
            # moves to GUARD-ALLOW time (lazy_guard.py, on allowing a hardening-
            # class entry) so the debt clears only when a hardening dispatch
            # actually reaches execution — repeated emissions can no longer drain
            # the debt without any hardening dispatch occurring (the Phase 7
            # emission-time ack let exactly that happen).
            out: dict = {
                "dispatch_prompt": prompt,
                "dispatch_model": model,
                "dispatch_class": cls,
            }
            # Phase 7 WU-7.5a: surface the marker-gated cycle_header when present
            # (emit_dispatch_prompt only attaches it when a run marker is active).
            if "cycle_header" in result:
                out["cycle_header"] = result["cycle_header"]
            # Phase 7 Deliverable 3: surface the @@lazy-ref reference token so
            # the orchestrator can dispatch meta prompts by reference (no retyping
            # → no transcription-slip denial for apply-resolution, hardening, etc.).
            # Null when no marker is active (peek semantics → no registry write).
            if _ref_entry is not None:
                out["dispatch_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"
            else:
                out["dispatch_prompt_ref"] = None
            sys.stdout.write(json.dumps(out, indent=2) + "\n")
            return 0
        else:
            # Refusal (missing @requires key or unbound residue).
            sys.stdout.write(json.dumps({
                "dispatch_prompt": None,
                "dispatch_model": None,
                "dispatch_class": cls,
                "dispatch_prompt_refused": result.get("refused", "unknown refusal"),
            }, indent=2) + "\n")
            return 1

    if args.neutralize_sentinel is not None:
        result = lazy_core.neutralize_sentinel(Path(args.neutralize_sentinel), date=args.apply_date)
        # harness-telemetry-ledger Phase 2 (D4-B): a successful neutralization
        # is the halt-dwell END marker (`sentinel-resolved`). Marker-gated +
        # fail-open; adds NO output keys.
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
        # park-provisional-acceptance (SPEC D2): the script-owned acceptance
        # action. Re-validates the fail-closed eligibility predicate, appends
        # the ## Resolution (resolved_by: auto-provisional + decision_commit),
        # and renames NEEDS_INPUT.md → NEEDS_INPUT_PROVISIONAL.md. Refusals
        # exit 1 with zero writes. Cycle-guarded like every other lifecycle
        # write path.
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
            # mechanize-prose-only-orchestrator-contracts (d): script-fired
            # provisional-accept notification (the SPEC's 4th event point).
            lazy_core.notify_event(
                "provisional-accept", f"{_tl_prov_item} accepted provisionally",
                str(args.repo_root), item_id=_tl_prov_item,
                detail=f"divergence={result.get('divergence')} — unratified until reviewed",
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.apply_pseudo is not None:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch.  Guard fires before any SPEC/PHASES/sentinel mutation.
        lazy_core.refuse_if_cycle_active("--apply-pseudo")
        name, spec = args.apply_pseudo
        result = lazy_core.apply_pseudo(
            Path(args.repo_root), name, Path(spec),
            plan_path=Path(args.plan) if args.plan else None,
            date=args.apply_date, reason=args.reason,
            deferred_step=args.deferred_step,
        )
        # Item-1 Fix-A (lazy-batch-unified-driver-parity-and-accounting Phase 1):
        # forward-advancing pseudo-skills run inline here (no Agent, no guard
        # ALLOW, no consume), so advance_run_counters never advances the forward
        # budget for them. After a SUCCESSFUL forward-advancing pseudo-skill apply,
        # advance the consume-independent forward/meta counter. The state key uses
        # the spec dir slug as feature_id and the pseudo-skill name as the step, so
        # each distinct apply is a distinct (feature_id, step, sub_skill) tuple —
        # idempotent if the same apply re-fires. Marker-gated (no-op when no run).
        if result.get("ok") and name in lazy_core._FORWARD_ADVANCING_PSEUDO_SKILLS:
            try:
                lazy_core.advance_forward_cycle({
                    "sub_skill": name,
                    "feature_id": Path(spec).resolve().parent.name,
                    "current_step": name,
                })
            except Exception as exc:  # noqa: BLE001 — fail-open, never block apply
                lazy_core._diag(
                    f"--apply-pseudo {name}: forward-cycle advance failed ({exc})"
                )
        # harness-telemetry-ledger Phase 2 (D4-B): a successful apply is a
        # `pseudo-applied` event; an exit-1 verdict is a `gate-refusal`.
        # Marker-gated + fail-open; adds NO output keys.
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

    if args.enqueue_adhoc:
        # lazy-cycle-containment C3 (Phase 3): refuse if a cycle subagent is
        # mid-dispatch.  Guard fires before any queue.json mutation.
        lazy_core.refuse_if_cycle_active("--enqueue-adhoc")
        if not args.id or not args.name:
            _die("--enqueue-adhoc requires --id and --name")
        # queue-dependency-dag Phase 4: optional --deps a,b (comma-separated
        # hard-dep ids). Parsed here; validated inside the enqueue helpers.
        _adhoc_deps = (
            [s.strip() for s in args.deps.split(",") if s.strip()]
            if args.deps else None
        )
        if args.adhoc_type == "bug":
            # toolify-auto-promotion Phase 2: --stub / --at tail are FEATURE-
            # queue-shaped (the bug pipeline has no stub step and orders by
            # severity). Refuse loudly BEFORE any write — never silently
            # ignore a flag the caller asked for.
            if args.stub or args.enqueue_at == "tail":
                _die("--stub/--at tail are feature-pipeline-only "
                     "(bug pipeline has no stub step); drop them or use "
                     "--type feature")
            # unified-pipeline-orchestrator P3: route into docs/bugs/queue.json
            # via the existing bug-state.py enqueue (do NOT reimplement it).
            result = enqueue_adhoc_bug(
                Path(args.repo_root),
                args.id,
                args.name,
                args.brief,
                args.spec_dir,
                deps=_adhoc_deps,
            )
        else:
            result = enqueue_adhoc(
                Path(args.repo_root),
                args.id,
                args.name,
                args.brief,
                args.spec_dir,
                args.tier,
                stub=args.stub,
                at=args.enqueue_at,
                deps=_adhoc_deps,
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.reorder_queue:
        # Operator-only / out-of-cycle queue mutation. Gated EXACTLY like
        # --enqueue-adhoc: refuse FIRST (before any mutation) so a cycle
        # subagent gets exit 3 with zero side effects.
        lazy_core.refuse_if_cycle_active("--reorder-queue")
        if not args.id or not args.reorder_to:
            _die("--reorder-queue requires --id and --to")
        # Parse --to: an integer index, else a string op (tail/head/remove).
        to_arg: "str | int"
        try:
            to_arg = int(args.reorder_to)
        except (TypeError, ValueError):
            to_arg = args.reorder_to
        result = lazy_core.reorder_queue(
            Path(args.repo_root) / "docs" / "features" / "queue.json",
            args.id,
            to=to_arg,
            queue_label="queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.sync_deps:
        # queue-dependency-dag D5: the script-owned SPEC→queue deps feeder.
        # Orchestrator-only — refuse FIRST (before any read/mutate) so a cycle
        # subagent gets exit 3 with ZERO side effects, exactly like
        # --enqueue-adhoc / --reorder-queue.
        lazy_core.refuse_if_cycle_active("--sync-deps")
        if not args.id:
            _die("--sync-deps requires --id")
        result = lazy_core.sync_deps(
            Path(args.repo_root) / "docs" / "features" / "queue.json",
            args.id,
            Path(args.repo_root) / "docs" / "features",
            queue_label="queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.record_decision:
        # mechanize-prose-only-orchestrator-contracts (c) / D3-A: orchestrator-
        # only — refuse FIRST (before any read/write) so a cycle subagent gets
        # exit 3 with ZERO side effects, exactly like --enqueue-adhoc /
        # --reorder-queue / --sync-deps.
        lazy_core.refuse_if_cycle_active("--record-decision")
        if not args.sentinel or not args.chosen:
            _die("--record-decision requires --sentinel and --chosen")
        record = lazy_core.record_decision(
            args.sentinel, args.chosen, summary=args.summary,
        )
        sys.stdout.write(json.dumps(record, indent=2) + "\n")
        return 0

    if args.reassert_owner:
        # single-slot-marker-ownership-race-disarms-owning-run Phase 2: the owner
        # RE-ARM path. Orchestrator-only — refuse FIRST (before any read/mutate)
        # so a cycle subagent gets exit 3 with ZERO side effects, exactly like
        # --run-start / --reorder-queue.
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
        # lazy-batch-no-mid-run-budget-or-park-controls: operator-authorized
        # mid-run budget change. Orchestrator-only — refuse FIRST (exit 3, zero
        # side effects), exactly like --reassert-owner / --run-start. Then require
        # --operator-authorized (parallel to the --run-end checkpoint gate) and a
        # positive N, and require an ACTIVE marker before mutating in place.
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
        # lazy-batch-no-mid-run-budget-or-park-controls: operator-authorized
        # mid-run park toggle. 'on' arms BOTH park facets (the --park umbrella);
        # 'off' clears both AND park_provisional (provisional requires needs-input).
        lazy_core.refuse_if_cycle_active("--set-park")
        if not args.operator_authorized:
            _die("--set-park requires --operator-authorized (the operator must have "
                 "approved the mid-run park toggle).")
        _on = args.set_park == "on"
        result = lazy_core.set_marker_park(
            park_needs_input=_on,
            park_blocked=_on,
            # Turning park OFF also clears the provisional modifier (it requires
            # needs-input); turning park ON leaves provisional untouched (armed
            # separately via --set-park-provisional).
            park_provisional=(None if _on else False),
        )
        if result is None:
            _die("--set-park: no active run marker to update.")
        out = {"park_updated": True, **result}
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0

    if args.set_park_provisional is not None:
        # lazy-batch-no-mid-run-budget-or-park-controls: operator-authorized
        # mid-run park-provisional toggle. set_marker_park enforces the standing
        # invariant (provisional requires needs-input) and refuses 'on' when park
        # is off (exit, zero writes).
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

    if args.set_tier is not None:
        # no-sanctioned-cli-for-queue-state-mutations: operator-directed in-place
        # tier change. Refuse FIRST (exit 3, zero side effects for a cycle
        # subagent — the --reorder-queue/--enqueue-adhoc contract), then require
        # --operator-authorized (this is an operator-directed priority change).
        # set_queue_priority ATOMICALLY re-sorts listed order to match the new
        # merged priority in the SAME write.
        lazy_core.refuse_if_cycle_active("--set-tier")
        if not args.operator_authorized:
            _die("--set-tier requires --operator-authorized (the operator must have "
                 "approved the priority change).")
        _id, _tier = args.set_tier
        result = lazy_core.set_queue_priority(
            Path(args.repo_root) / "docs" / "features" / "queue.json",
            _id, "feature", _tier, queue_label="queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.set_independent is not None:
        # no-sanctioned-cli-for-queue-state-mutations /
        # lazy-batch-parallel-run-harness-gaps gap 3: operator-directed in-place
        # independent-marker change (the sanctioned replacement for hand-editing
        # queue.json's shard-eligibility marker). Refuse FIRST (exit 3, zero side
        # effects for a cycle subagent — the --set-tier contract), then require
        # --operator-authorized. VALUE is true|false; false CLEARS the marker.
        lazy_core.refuse_if_cycle_active("--set-independent")
        if not args.operator_authorized:
            _die("--set-independent requires --operator-authorized (the operator must "
                 "have approved the shard-eligibility change).")
        _id, _raw = args.set_independent
        _norm = _raw.strip().lower()
        if _norm not in ("true", "false"):
            _die(f"--set-independent VALUE must be 'true' or 'false', got {_raw!r}.")
        result = lazy_core.set_independent_marker(
            Path(args.repo_root) / "docs" / "features" / "queue.json",
            _id, _norm == "true", queue_label="queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.add_deps or args.remove_deps:
        # no-sanctioned-cli-for-queue-state-mutations: post-hoc arbitrary deps
        # edit (the non-SPEC sibling of --sync-deps). Refuse FIRST + require
        # --operator-authorized. --add-deps / --remove-deps are separate ops so a
        # cycle-guard failure names the exact direction.
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
            Path(args.repo_root) / "docs" / "features" / "queue.json",
            _target,
            add=(_dep_ids if args.add_deps else None),
            remove=(_dep_ids if args.remove_deps else None),
            queue_label="queue.json",
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.record_intervention:
        # intervention-efficacy-tracking Phase 1: the manual / hardening-round /
        # D9-backfill capture path (the completion-gate capture lives inside
        # lazy_core.apply_pseudo — this CLI covers captures with no completion
        # event). Orchestrator-only: the record is committed pipeline state, so
        # refuse a cycle subagent FIRST (exit 3, zero side effects), exactly
        # like --enqueue-adhoc / --reorder-queue — EXCEPT a dispatched HARDENING
        # cycle subagent, which its SKILL contract REQUIRES to record its own
        # round's intervention (capture-only telemetry, no lifecycle mutation).
        # allow_hardening_subagent permits it ONLY when the cycle marker's
        # sub_skill is a hardening class; every other cycle subagent is still
        # refused (dispatched-harden-record-intervention-refused-by-containment).
        lazy_core.refuse_if_cycle_active(
            "--record-intervention", allow_hardening_subagent=True
        )
        if not args.id:
            _die("--record-intervention requires --id")
        # D9 honesty convention: an explicit shipped_commit/shipped_date
        # override means this capture reconstructs an ALREADY-shipped change →
        # provenance: backfilled (mirrors backfilled-unverified receipts).
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

    if args.materialize_wi is not None:
        # type_pipeline_map: load from the Cognito skill-config yml if available,
        # else fall back to the locked default below.
        type_map = {
            "bug": ["Bug", "Defect", "Story Bug", "Engineering Bug"],
            "feature": ["User Story", "Refactor Story", "Enabler Story", "Requirement"],
        }
        result = materialize_wi(Path(args.repo_root), args.materialize_wi, type_map)
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.backfill_receipts:
        result = backfill_receipts(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.ack_deny is not None:
        # meta-dispatch-not-by-reference-and-ack-overpriced: cheap per-entry
        # ack, gated EXACTLY like --backfill-receipts/--link-provenance (a
        # cycle subagent is refused exit 3 with zero side effects).
        lazy_core.refuse_if_cycle_active("--ack-deny")
        result = lazy_core.ack_deny_by_selector(args.ack_deny, args.resolution or "")
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result.get("ok") else 1

    if args.link_provenance:
        # code-doc-provenance-linkage Phase 3: the manual trigger of the
        # one-writer provenance producer. Operator-only / out-of-cycle —
        # gated EXACTLY like --enqueue-adhoc (a cycle subagent is refused
        # exit 3 with zero side effects).
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
        # marking a feature complete. The orchestrator's && chains short-circuit
        # on non-zero exit when any check fails. When --plan is also passed,
        # checks 3+4 narrow to that plan part's scope (Phase 9 WU-3) — reuses the
        # existing --plan flag (shared with --apply-pseudo, no dest collision).
        # verify_ledger expects a spec directory (not the SPEC.md file path).
        # Normalize: if the caller passed a .md file, use its parent directory.
        _vl_path = Path(args.verify_ledger)
        _spec_dir = _vl_path.parent if _vl_path.suffix == ".md" else _vl_path
        result = lazy_core.verify_ledger(
            Path(args.repo_root), _spec_dir,
            plan_path=Path(args.plan) if args.plan else None,
        )
        # harness-telemetry-ledger Phase 2 (D4-B): an exit-1 ledger verdict is a
        # `gate-refusal` event (marker-gated + fail-open; adds NO output keys).
        if not result["ok"]:
            lazy_core.append_telemetry_event(
                "gate-refusal", item_id=_spec_dir.resolve().name,
                data={"gate": "verify-ledger",
                      "failing_check": result.get("failing_check"),
                      # completion-gate-refusal-opacity Fix Scope §3: a
                      # compact one-line summary of failing_detail so
                      # incident mining can distinguish severities without
                      # transcript access.
                      "detail_head": lazy_core.summarize_failing_detail(result)},
            )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    if args.test:
        return run_smoke_tests()

    # lazy-batch-no-mid-run-budget-or-park-controls: resolve the EFFECTIVE park
    # state — the marker is authoritative for a live run (so a mid-run --set-park
    # toggle takes effect), with the CLI flags as the no-marker / legacy-marker
    # fallback (byte-identical back-compat). Threaded into compute_state AND the
    # emit path below so header/park behavior update immediately.
    _park_marker = lazy_core.read_run_marker()
    _eff_park_ni, _eff_park_bl, _eff_park_pv = lazy_core.fold_park_flags(
        args.park_needs_input, args.park_blocked, args.park_provisional,
        _park_marker,
    )
    state = compute_state(
        Path(args.repo_root),
        cloud=args.cloud,
        skip_needs_research=args.skip_needs_research,
        real_device=resolve_real_device(args.real_device),
        scope_feature_id=args.feature_id,
        park_needs_input=_eff_park_ni,
        park_blocked=_eff_park_bl,
        park_provisional=_eff_park_pv,
        per_feature_cycle_cap=args.per_feature_cycle_cap,
        strict_research_halt=args.strict_research_halt,
    )
    # research-gated-head-buried-by-skip-ahead-and-merged-fallthrough: when THIS
    # dispatch-bound probe (--emit-prompt) REALIZED a skip PAST a research-pending
    # gated head and that head OUTRANKS (full merged ordering incl. the type
    # tie-break) the item the driver would otherwise dispatch — a lower-priority
    # bug or feature the Round-64 merged fallthrough would route to — re-emit as
    # that head's SCOPED needs-research terminal so the driver's EXISTING
    # needs-research (Step 4) halt SURFACES the research prompt instead of burying
    # it. A research gap is operator-resolvable in seconds; a BLOCKED head is not,
    # so BLOCKED heads keep skipping-ahead to independent ready work (unchanged).
    # Loop-free: the scoped re-run lands on the head's own Step-5 needs-research
    # terminal (no re-dispatch, no stall). Feature-pipeline only + marker-gated +
    # fail-safe (any error → keep the original state; never fabricate a halt).
    if args.emit_prompt and _park_marker is not None and state.get("research_gated_heads"):
        _rh_head = None
        try:
            _rh_repo = Path(args.repo_root)
            _rh_feats = load_queue(_rh_repo)
            _rh_bugs = _load_bug_queue_for_merged(_rh_repo)
            # merged-head-actionability-oracle (SPEC L1/L2/L3 tail): build the FULL
            # merged-head exclude set via the oracle (same-pipeline = features via
            # probe_skipped_ids unchanged; cross-pipeline = bugs via the real scoped
            # bug probe), then pass it to research_halt_head, which RE-INCLUDES the
            # research-gated ids exactly as today — the byte-identity invariant that
            # keeps a research-gated merged head SURFACING its needs-research halt.
            _rh_bug_state_mod = _load_bug_state_module()
            _rh_real_device = resolve_real_device(args.real_device)
            # TYPE-AWARE scoped probe (merged-head-oracle-deadlocks-on-unreached-
            # parked-same-pipeline-head): the oracle now scope-probes a
            # same-pipeline (feature) head the emit walk never reached, not only
            # cross-pipeline (bug) candidates — so the probe dispatches each
            # candidate to the correct pipeline's compute_state via an id->type map
            # (mirrors the stateless --next-merged _nm_scoped_probe).
            _rh_types = {}
            for _rh_it in _rh_feats:
                if isinstance(_rh_it, dict) and _rh_it.get("id"):
                    _rh_types[_rh_it["id"]] = "feature"
            for _rh_it in _rh_bugs:
                if isinstance(_rh_it, dict) and _rh_it.get("id"):
                    _rh_types.setdefault(_rh_it["id"], "bug")

            def _rh_scoped_probe(_iid):
                try:
                    if _rh_types.get(_iid) == "bug":
                        if _rh_bug_state_mod is None:
                            return {}
                        return _rh_bug_state_mod.compute_state(
                            _rh_repo, cloud=args.cloud, real_device=_rh_real_device,
                            scope_bug_id=_iid,
                            park_needs_input=_eff_park_ni, park_blocked=_eff_park_bl,
                            park_provisional=_eff_park_pv,
                            strict_research_halt=args.strict_research_halt,
                        )
                    # same-pipeline feature → this module's own scoped compute_state
                    return compute_state(
                        _rh_repo, cloud=args.cloud,
                        skip_needs_research=args.skip_needs_research,
                        real_device=_rh_real_device, scope_feature_id=_iid,
                        park_needs_input=_eff_park_ni, park_blocked=_eff_park_bl,
                        park_provisional=_eff_park_pv,
                        strict_research_halt=args.strict_research_halt,
                    )
                except Exception:  # noqa: BLE001 — a per-candidate probe error must not break the base probe
                    return {}

            _rh_diag_snapshot = list(lazy_core._DIAGNOSTICS)
            try:
                _rh_excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
                    _rh_feats, _rh_bugs, str(lazy_core.active_repo_root()),
                    state.get("feature_id"),
                    same_pipeline="feature", same_pipeline_state=state,
                    scoped_probe=_rh_scoped_probe,
                )
            finally:
                lazy_core._DIAGNOSTICS[:] = _rh_diag_snapshot
            _rh_head = lazy_core.dispatch.research_halt_head(
                state, _rh_feats, _rh_bugs, str(lazy_core.active_repo_root()),
                exclude_ids=_rh_excluded,
            )
        except Exception:  # noqa: BLE001 — detection must never break the base probe
            _rh_head = None
        if _rh_head is not None:
            try:
                _rh_state = compute_state(
                    Path(args.repo_root),
                    cloud=args.cloud,
                    skip_needs_research=args.skip_needs_research,
                    real_device=resolve_real_device(args.real_device),
                    scope_feature_id=_rh_head,
                    park_needs_input=_eff_park_ni,
                    park_blocked=_eff_park_bl,
                    park_provisional=_eff_park_pv,
                    per_feature_cycle_cap=args.per_feature_cycle_cap,
                    strict_research_halt=True,
                )
            except Exception:  # noqa: BLE001 — fail toward the original state
                _rh_state = None
            # Adopt the scoped terminal ONLY when it is actually the needs-research
            # halt (fail-safe: never manufacture a halt from a mis-scoped re-run).
            if _rh_state is not None and _rh_state.get("terminal_reason") == "needs-research":
                _rh_state["route_overridden_by"] = "research-gated-head"
                state = _rh_state
    # Surface the effective park state on the probe JSON when a marker is present
    # (byte-identical no-marker output preserved) so the orchestrator can confirm
    # a --set-park toggle took effect mid-run.
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
        _counts = lazy_core.update_repeat_counts(
            Path(args.repo_root), state, peek=args.repeat_count_peek
        )
        state["repeat_count"] = _counts["repeat_count"]
        state["step_repeat_count"] = _counts["step_repeat_count"]
    # cycle-budget-counters-double-count-on-probes-and-inject-hook: the forward
    # budget advance formerly fired HERE on the --repeat-count probe path. REMOVED —
    # probes (inspection probes AND the per-turn inject hook, lazy_inject.py) fire
    # this path with NO dispatch, so coupling the budget to it double-counted /
    # inflated forward_cycles (0→3 over three distinct-item inspection probes; a
    # non-dispatch inject turn bumped 1→2). The budget now advances ONLY on a
    # completed dispatch bracket (advance_cycle_bracket_counter at --cycle-end, keyed
    # on the cycle marker's --kind) and on --apply-pseudo. update_repeat_counts
    # (the loop-detection STREAKS) stays probe-driven above — only the BUDGET
    # decoupled from the probe path.
    # --emit-prompt is strictly additive and flag-gated so that default output
    # remains byte-identical when the flag is absent. Placed AFTER the repeat
    # flags so the same-invocation count (from EITHER --repeat-count or
    # --repeat-count-peek) drives the emitter's loop-block + model decision.
    # emit_cycle_prompt(...) is None for pseudo-skills / terminal probes →
    # cycle_prompt: null, cycle_model: null (so the orchestrator's one probe
    # call is uniform); on refusal it also adds cycle_prompt_refused.
    if args.emit_prompt:
        # Phase 8 WU-8.2: routed hardening debt WITHHOLDS the forward route.
        # When (marker present AND pending_hardening() > 0) the probe must NOT
        # emit/register a cycle_prompt — the orchestrator owes a hardening
        # dispatch first.  Surfacing the debt (Phase 7) was not enough: an
        # orchestrator that field-extracted cycle_model dispatched a forward
        # route over live debt (session e076ed30).  Routing the override here
        # means no cycle_prompt/cycle_model/cycle registration side-effect this
        # probe; the extractor now fails loudly on the missing key.
        _emit_marker = lazy_core.read_run_marker()
        _emit_debt = lazy_core.pending_hardening() if _emit_marker is not None else 0
        # dispatch-probe-and-inject-bypass-merged-head: compute whether the
        # MERGED work-list head diverges from the item this feature probe would
        # emit for (a P0 bug that jumped the bug-queue head mid-feature-run).
        # The unified driver is contracted to probe --next-merged FIRST and
        # type-dispatch, but an orchestrator that calls this enriched
        # --emit-prompt probe DIRECTLY (the manual Step-1a path) would otherwise
        # get a stale feature route with no signal that a P0 bug outranks it.
        # Marker-gated + fail-safe (any error → None → emit normally; never a
        # spurious withhold). Reuses the SAME next_merged ordering the
        # --next-merged surface uses — never a second ordering rule.
        #
        # lazy-batch-parallel-run-harness-gaps gap 1: EXEMPT the lane probe form.
        # A /lazy-batch-parallel lane marker carries a non-null `parent_run`; the
        # coordinator's claim_shardable ALREADY applied the queue-order +
        # independent:true + lease arbitration when it assigned this lane its
        # --feature-id. The merged-head guard's serial premise ("only one item is
        # active and it must be the global head") is void by design in a parallel
        # run — every lane whose item is not the global head would otherwise
        # withhold forever (observed live: lanes wt-01/wt-02 stalled behind the
        # serial-held head hydra-overlay, which — being unsharded — holds no lease,
        # so lease-exclusion alone would not have cleared it). Lane arbitration is
        # coordinator-owned, not a per-lane-probe concern.
        _emit_is_lane = bool(
            isinstance(_emit_marker, dict) and _emit_marker.get("parent_run")
        )
        # lazy-batch-parallel-run-harness-gaps round-2 gap 8: EXEMPT the
        # coordinator's SERIAL-TAIL probe whose OWN feature_id holds a LIVE
        # coordinator lease. Round-1 gap 1 (above) exempted the LANE probe form
        # (parent_run set), but the post-merge validation TAIL probes run at the
        # MAIN root against the PARENT marker (parent_run null → not a lane), so
        # the serial guard still fired: when a freshly-dispatchable head (e.g. a
        # research-ingested feature) became the merged head, the tail's
        # --emit-prompt for a merged, lease-held item was WITHHELD
        # (route_overridden_by: merged-head-diverged) even though completing that
        # lease-held item is the coordinator's obligation BEFORE any new head
        # work. A live lease on the PROBED item means it is actively-owned
        # in-flight work (heartbeat fresh) — never the stale route the guard
        # exists to catch — so redirecting away from it would orphan the
        # lease-held tail. This is the exact analog of the lane exemption: a lane
        # exempts on the coordinator-arbitrated claim (parent_run); the tail
        # exempts on the probed item's OWN live lease (coordinator-owned in-flight
        # completion). Fail-safe: any read error / no leases.json / no live lease
        # → False → the guard runs exactly as before (byte-identical for every
        # non-parallel serial run, which has no leases.json). Note lease-EXCLUSION
        # (dropping other leased ids from the merged head) would NOT fix this — the
        # divergent head here is a fresh non-leased item, so it stays the head;
        # only exempting the probe for its OWN live lease clears the withhold.
        _emit_is_lease_held = False
        if _emit_marker is not None and not _emit_is_lane and state.get("feature_id"):
            try:
                _emit_is_lease_held = lazy_coord.has_live_lease(
                    lazy_core.claude_state_dir() / "leases.json",
                    state.get("feature_id"),
                )
            except Exception:  # noqa: BLE001 — lease probe must never break the base probe
                _emit_is_lease_held = False
        _merged_override = None
        if _emit_marker is not None and not _emit_is_lane and not _emit_is_lease_held:
            try:
                _mo_repo = Path(args.repo_root)
                _mo_feats = load_queue(_mo_repo)
                _mo_bugs = _load_bug_queue_for_merged(_mo_repo)
                # merged-head-actionability-oracle (SPEC L1/L2/L3/L5): build the
                # merged-head exclude set via the AUTHORITATIVE actionability
                # oracle — the single replacement for the file-predicate
                # `nondispatchable_item_ids` ∪ `probe_skipped_ids` union that had
                # accreted five/six `merged-head-diverged-withholds-on-<X>` facets.
                #   (1) same-pipeline (features) → `probe_skipped_ids(state, feats)`
                #       UNCHANGED (L2 — the cross-item skip-ahead ordering context).
                #   (2) cross-pipeline (bugs) → the REAL scoped `bug-state.compute_state`
                #       per at-or-above candidate, EXCLUDED iff non-dispatchable
                #       (`is_dispatchable` false), honoring the SAME run flags the emit
                #       probe used (cloud/real_device/park facets/strict_research_halt;
                #       the bug pipeline has no --skip-needs-research). A candidate the
                #       probe can't classify (module unloadable / probe error) is treated
                #       non-dispatchable → fail toward EMITTING the workable item.
                #   (3) `.discard(current)` (invariant preserved, inside the oracle).
                # Byte-identical for a dispatchable head (a P0 bug jumping the queue
                # still withholds); previously-uncovered non-dispatchable categories
                # (cloud/completion-unverified/blocked/…) are now correctly excluded,
                # ending the recurring stall class by construction. In-process safety
                # (Phase-1 OQ1/L4): the scoped bug probe calls `clear_diagnostics()` on
                # the SHARED lazy_core._DIAGNOSTICS, so snapshot/restore it around the
                # oracle (the primary `state` dict is already a captured snapshot).
                _mo_bug_state_mod = _load_bug_state_module()
                _mo_real_device = resolve_real_device(args.real_device)
                # TYPE-AWARE scoped probe (merged-head-oracle-deadlocks-on-
                # unreached-parked-same-pipeline-head): the oracle now scope-probes
                # a same-pipeline (feature) head the emit walk never reached, not
                # only cross-pipeline (bug) candidates — so the probe dispatches
                # each candidate to the correct pipeline's compute_state via an
                # id->type map (mirrors the stateless --next-merged _nm_scoped_probe).
                _mo_types = {}
                for _mo_it in _mo_feats:
                    if isinstance(_mo_it, dict) and _mo_it.get("id"):
                        _mo_types[_mo_it["id"]] = "feature"
                for _mo_it in _mo_bugs:
                    if isinstance(_mo_it, dict) and _mo_it.get("id"):
                        _mo_types.setdefault(_mo_it["id"], "bug")

                def _mo_scoped_probe(_iid):
                    try:
                        if _mo_types.get(_iid) == "bug":
                            if _mo_bug_state_mod is None:
                                return {}
                            return _mo_bug_state_mod.compute_state(
                                _mo_repo, cloud=args.cloud, real_device=_mo_real_device,
                                scope_bug_id=_iid,
                                park_needs_input=_eff_park_ni, park_blocked=_eff_park_bl,
                                park_provisional=_eff_park_pv,
                                strict_research_halt=args.strict_research_halt,
                            )
                        # same-pipeline feature → this module's own scoped compute_state
                        return compute_state(
                            _mo_repo, cloud=args.cloud,
                            skip_needs_research=args.skip_needs_research,
                            real_device=_mo_real_device, scope_feature_id=_iid,
                            park_needs_input=_eff_park_ni, park_blocked=_eff_park_bl,
                            park_provisional=_eff_park_pv,
                            strict_research_halt=args.strict_research_halt,
                        )
                    except Exception:  # noqa: BLE001 — a per-candidate probe error must not break the base probe
                        return {}

                _mo_diag_snapshot = list(lazy_core._DIAGNOSTICS)
                try:
                    _mo_excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
                        _mo_feats, _mo_bugs, str(lazy_core.active_repo_root()),
                        state.get("feature_id"),
                        same_pipeline="feature", same_pipeline_state=state,
                        scoped_probe=_mo_scoped_probe,
                    )
                finally:
                    lazy_core._DIAGNOSTICS[:] = _mo_diag_snapshot
                # Retained for the observability diagnostic below (the same-pipeline
                # skip set the withhold folded in) — the oracle already includes it.
                _mo_skipped = lazy_core.dispatch.probe_skipped_ids(state, _mo_feats)
                _merged_override = lazy_core.dispatch.merged_head_override(
                    _mo_feats,
                    _mo_bugs,
                    str(lazy_core.active_repo_root()),
                    state.get("feature_id"),
                    exclude_ids=_mo_excluded,
                )
                # Observability (skip is NON-withholding): a gated head the probe
                # skipped is surfaced in the existing gated_heads /
                # device_deferred_features / host_deferred_features / dep_gated
                # keys; add a diagnostic naming the skip so retro/telemetry can
                # see the merged-head divergence was correctly SKIPPED (not
                # withheld) when a workable item existed downstream.
                if _mo_skipped and _merged_override is None:
                    _diag_line = (
                        "merged-head: skipped gated/deferred head(s) "
                        f"{sorted(_mo_skipped)!r} — dispatching the workable merged "
                        f"item '{state.get('feature_id')}' (merged-head-diverged "
                        "NOT withheld; skip observable via gated_heads / "
                        "device_deferred_features / host_deferred_features / "
                        "dep_gated)."
                    )
                    if isinstance(state.get("diagnostics"), list):
                        state["diagnostics"].append(_diag_line)
            except Exception:  # noqa: BLE001 — divergence probe must never break the base probe
                _merged_override = None
        elif _emit_is_lane:
            # gap 1 observability: record that the merged-head divergence guard was
            # SKIPPED because this is a coordinator-authorized lane probe (never
            # withheld — lane arbitration is claim_shardable's job).
            if isinstance(state.get("diagnostics"), list):
                state["diagnostics"].append(
                    "merged-head: skipped divergence guard — lane probe "
                    "(parent_run set); lane arbitration is coordinator-owned "
                    "(claim_shardable)."
                )
        elif _emit_is_lease_held:
            # gap 8 observability: the merged-head divergence guard was SKIPPED
            # because this serial-tail probe's OWN feature_id holds a live
            # coordinator lease — completing the lease-held, lane-merged item is
            # the coordinator's obligation before new head work (never withheld).
            if isinstance(state.get("diagnostics"), list):
                state["diagnostics"].append(
                    "merged-head: skipped divergence guard — serial-tail probe "
                    "for a lease-held item (feature_id holds a live coordinator "
                    "lease); completing the merged, lease-held item is the "
                    "coordinator's in-flight obligation (round-2 gap 8)."
                )
        if _emit_marker is not None and _emit_debt > 0:
            # Withhold: no cycle_prompt, no cycle_model, no registration.
            _oldest = lazy_core.oldest_unacked_deny()
            state["route_overridden_by"] = "pending-hardening-debt"
            # Compact one-line probe summary for the dispatched hardening subagent.
            _probe_summary = (
                f"step={state.get('current_step')} sub_skill={state.get('sub_skill')} "
                f"feature_id={state.get('feature_id')} pending_hardening={_emit_debt}"
            )
            state["hardening_emit_command"] = lazy_core.build_hardening_emit_command(
                "lazy-state.py",
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
            # mechanize-prose-only-orchestrator-contracts (b) / D2-A: an
            # undischarged post-cycle input-audit obligation (§1d.5 promoted
            # from prose to a mechanical withhold) ALSO withholds the forward
            # route — same shape as the pending-hardening-debt withhold above
            # (checked FIRST; the two debts never both apply to one probe in
            # practice, but hardening takes priority when they do). No
            # cycle_prompt/cycle_model/registration side-effect this probe.
            _obligation = lazy_core.pending_audit_obligation()
            state["route_overridden_by"] = "audit-obligation"
            _aud_item_id = _obligation.get("item_id") or state.get("feature_id") or ""
            _aud_spec_path = (
                state.get("spec_path")
                if state.get("feature_id") == _obligation.get("item_id")
                else None
            ) or str(Path(args.repo_root) / "docs" / "features" / _aud_item_id)
            state["input_audit_emit_command"] = lazy_core.build_input_audit_emit_command(
                "lazy-state.py",
                item_id=_aud_item_id,
                item_name=state.get("feature_name") or _aud_item_id,
                spec_path=_aud_spec_path,
                cycle_kind=_obligation.get("cycle_kind") or "",
                cwd=str(args.repo_root),
                # adhoc-audit-obligation-fires-on-zero-commit-failed-cycle P2:
                # bind the emit command to the bracket's ACTUAL end commit
                # (recorded on the obligation in P1), never positional HEAD~1.
                cycle_commit_sha=_obligation.get("cycle_commit_sha"),
                cycle_summary=_obligation.get("cycle_summary"),
            )
        elif _merged_override is not None:
            # dispatch-probe-and-inject-bypass-merged-head: the MERGED head is a
            # DIFFERENT, higher-priority item than this feature probe would emit
            # for (typically a P0 bug that jumped the bug-queue head). WITHHOLD
            # the wrong-item forward route — same shape as the two withholds
            # above (no cycle_prompt/cycle_model/registration side-effect this
            # probe). The orchestrator must re-probe --next-merged and
            # type-dispatch to the merged head's script (bug → bug-state.py).
            # Lowest-precedence of the three withholds: a hardening/audit debt on
            # the CURRENT item is discharged first; only then does a merged-head
            # divergence redirect the route.
            state["route_overridden_by"] = "merged-head-diverged"
            state["merged_head"] = _merged_override["merged_head"]
        else:
            rc = state.get("repeat_count") if (args.repeat_count or args.repeat_count_peek) else None
            # Phase 9 (lazy-validation-readiness) — per-part model tiering.
            # emit_cycle_prompt selects cycle_model from the CURRENT plan part's
            # `complexity:` tag when this is an /execute-plan cycle (read off
            # state["sub_skill_args"], the plan path): mechanical → sonnet,
            # complex / absent → opus. It composes with the loop-block downgrade
            # (repeat_count >= 2 → sonnet). bug-state.py shares this exact call,
            # so the bug pipeline mirrors the tiering automatically (no separate
            # cycle-model path). Gated strictly on the explicit tag — never an
            # auto-guess at dispatch.
            emitted = lazy_core.emit_cycle_prompt(
                Path(args.repo_root), state,
                pipeline="feature", cloud=args.cloud, repeat_count=rc,
                # park-provisional-acceptance (SPEC D13): a park-mode probe
                # selects the park=park template sections (the stub-spec
                # sentinel-mediation contract). Non-park emission is
                # byte-identical (the attribute is absent on every
                # pre-existing section). lazy-batch-no-mid-run-budget-or-park-
                # controls: uses the EFFECTIVE (marker-authoritative) park state
                # so a mid-run --set-park toggle drives the emitted template.
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
            # validate hook can check it.  No marker → no-op (zero writes,
            # byte-identical output).
            # F2a: capture the returned entry so we can surface the @@lazy-ref
            # token alongside the prompt; orchestrators may use the shorter
            # token to dispatch subagents (dispatch-by-reference).
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
        # harness-telemetry-ledger Phase 2 (D4-B): --emit-prompt IS the
        # per-cycle dispatch surface — record the routed dispatch tuple (and a
        # `halt` sibling when the terminal_reason is a halt). Marker-gated
        # inside the emitter (a bare unmarked probe emits nothing) + fail-open;
        # adds NO keys to the probe JSON.
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
        # live-settings split-brain probe (Fix Scope 4 / D2): surface whether the
        # live ~/.claude/settings.json still reflects the tracked SSOT. Additive,
        # fail-open, never a state-compute dependency.
        _ls_ok, _ls_detail = live_settings_probe(Path(args.repo_root))
        state["live_settings_ok"] = _ls_ok
        state["live_settings_detail"] = _ls_detail
        # C8 self-edit reload discipline (lazy-cycle-containment Phase 1):
        # surface whether this run is editing the harness it executes from, plus
        # the governing-prose files the last commit touched (so the orchestrator's
        # reload check stays mechanical). Both are best-effort and never raise.
        state["self_edit_mode"] = lazy_core.self_edit_mode(Path(args.repo_root))
        if state["self_edit_mode"]:
            state["governing_files_touched"] = lazy_core.governing_files_touched(
                Path(args.repo_root)
            )
        # Counter fold (Phase 1): when a marker is present, fill in absent
        # --forward-cycles / --meta-cycles from the marker's persisted values.
        # Explicit flag values win over marker values (backward compat).
        # When no marker is present, behavior is byte-identical to before.
        _marker = lazy_core.read_run_marker()
        _fwd, _meta = lazy_core.fold_run_counters(
            args.forward_cycles, args.meta_cycles,
            _marker,
        )
        # lazy-batch-no-mid-run-budget-or-park-controls: the marker is the
        # authoritative live budget — fold max_cycles from it when present so a
        # mid-run --set-max-cycles update shows in the header immediately (no
        # re-passing --max-cycles). No marker → the explicit flag (byte-identical).
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
                # Phase 8 WU-8.3: warn to STDERR (never stdout — stdout must stay
                # parseable JSON; lazy_inject.py's _run_probe reads stdout only and
                # captures stderr separately, so this cannot corrupt the banner).
                sys.stderr.write(
                    f"⚠ pending_hardening: {_pending} — forward route withheld; "
                    f"run hardening_emit_command first\n"
                )
            # Residual gap B (loop-detector-false-positives-probes-and-cross-run-
            # state): a PRIOR/crashed run's unacked denials are no longer counted
            # in the mandatory pending_hardening above, but surface them
            # separately as informational debt so they are not silently invisible
            # (a T6 informational line, never a blocking one — never withholds
            # the route, never gates --run-end).
            _prior_pending = lazy_core.prior_run_pending_hardening()
            if _prior_pending > 0:
                state["prior_run_pending_hardening"] = _prior_pending
    # operator-halt-notifications (D2): the terminal-emission chokepoint —
    # page the operator on an attention-terminal halt. Config-gated (inert
    # no-op without ~/.claude/notify.json / LAZY_NOTIFY_URL), dedup-ledgered
    # per sentinel identity, fail-OPEN (never raises, never alters this JSON's
    # terminal fields or the exit code). Composes with the telemetry `halt`
    # event above — telemetry records, notify pages. Coupled-pair surface #7
    # (lazy_parity_audit.py); mirrored in bug-state.py with pipeline="bug".
    lazy_core.notify_halt(state, args.repo_root, pipeline="feature")
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
