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
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Insert this directory onto sys.path so `import lazy_core` resolves when
# bug-state.py is run directly from user/scripts/ OR via the ~/.claude/scripts
# symlink.
sys.path.insert(0, str(Path(__file__).parent))

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
    write_completed_receipt,
    has_completion_receipt,
    skip_waiver_refusal,
    repo_has_no_app_surface,
    phases_mcp_runtime_not_required,
    spec_status,
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
    return out


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


def load_bug_queue(repo_root: Path) -> list[dict[str, Any]]:
    """Load docs/bugs/queue.json.  Returns [] if the file is absent.

    Hybrid ordering contract:
      1. Entries listed in queue.json appear first (in listed order).
      2. On-disk open bug dirs not in the queue follow, sorted by severity
         rank (P0→P1→P2→Low) then **Discovered:** date ascending.
      3. _archive/ is always skipped.

    The queue is OPTIONAL — no queue.json + no open bugs → all-bugs-fixed.
    Each returned entry is a dict with at minimum: id, name, spec_path (Path).
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
            })

    # On-disk open bug dirs not in queue, sorted by severity rank then Discovered date
    on_disk = _find_open_bug_dirs(bugs_dir, queued_ids)
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
        on_disk_entries.append({
            "id": bug_id,
            "name": name,
            "spec_path": bug_dir.resolve(),
            "severity": bug_severity(bug_dir / "SPEC.md"),
            "queue_entry": None,
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


def _find_open_bug_dirs(bugs_dir: Path, queued_ids: set[str]) -> list[Path]:
    """Return on-disk open bug dirs NOT already in queued_ids.

    Searches bugs_dir (one level deep), skips _archive/, and skips any dir
    whose SPEC.md **Status:** is a genuinely-done terminal state.  Returns
    dirs sorted by severity rank then Discovered date ascending.

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
        # Sort key: severity rank (ascending priority) + discovered date string (ascending)
        sev = bug_severity(spec_md)
        sev_rank = _SEVERITY_RANK.get(sev, _SEVERITY_DEFAULT) if sev else _SEVERITY_DEFAULT
        disc = bug_discovered(spec_md) or "9999-99-99"
        candidates.append((sev_rank, disc, child))

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
    """
    # Cloud has no audio device — force no-device like lazy-state.py does.
    if cloud:
        real_device = False

    # Reset diagnostics and deferred lists for this invocation.
    clear_diagnostics()
    _DEVICE_DEFERRED.clear()
    _OPERATOR_DEFERRED.clear()
    # Park mode: set the module global from the param so _bug_state() can gate
    # the "parked" key on it.  _PARKED accumulates items skipped this invocation.
    global _PARK_MODE, _PARKED
    _PARK_MODE = park_needs_input or park_blocked
    _PARKED.clear()
    repo_root = repo_root.resolve()

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
            continue

        if status == BUG_STATUS_FIXED:
            # Receipt required for Fixed bugs.
            if has_completion_receipt(spec_dir, filename="FIXED.md"):
                # Genuinely done.
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
                device_saturated_skipped.append(bug_name)
                _DEVICE_DEFERRED.append(bug_name)
                meta = parse_sentinel(spec_dir / "DEFERRED_REQUIRES_DEVICE.md") or {}
                scen = meta.get("deferred_scenarios") or []
                scen_str = ", ".join(str(s) for s in scen) if scen else "(unspecified)"
                _diag(
                    f"device-saturated skipped: {bug_name} — real-device-only "
                    f"assertions deferred [{scen_str}] (DEFERRED_REQUIRES_DEVICE.md); "
                    "re-opens on a real-device /lazy-bug host."
                )
                continue

        # -----------------------------------------------------------------------
        # Operator-deferred skip: DEFERRED.md present → operator parked this bug.
        # Skip and continue to the next candidate so the queue keeps moving.
        # Re-include by deleting DEFERRED.md.
        # -----------------------------------------------------------------------
        deferred_md = spec_dir / "DEFERRED.md"
        if deferred_md.exists():
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
            _PARKED.append(lazy_core.build_parked_entry(bug_id, spec_dir / "BLOCKED.md"))
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
                _PARKED.append(lazy_core.build_parked_entry(bug_id, _stray))
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
            _PARKED.append(lazy_core.build_parked_entry(bug_id, spec_dir / "NEEDS_INPUT.md"))
            _diag(
                f"parked: {bug_name} — unresolved NEEDS_INPUT.md; skipped (park mode). "
                "Re-enters when resolved."
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
            return _bug_state(
                **common,
                current_step=STEP_INVESTIGATE,
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
            # A Ready/In-progress plan exists — execute it.
            plan = plans[0]
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
                if meta.get("result") == "all-passing":
                    # Freshness gate (mirrors lazy-state.py's Step 9): the
                    # results must have been validated against the CURRENT
                    # HEAD commit. If validated_commit is present and doesn't
                    # match HEAD, the results are stale and we must re-run MCP
                    # tests against the current code before writing
                    # VALIDATED.md. When _current_head returns None (not a
                    # git repo) or validated_commit is absent (legacy
                    # results), skip the check — legacy permissive.
                    head = _current_head(repo_root)
                    validated_commit = meta.get("validated_commit")
                    if head and validated_commit and str(validated_commit) != head:
                        return _bug_state(
                            **common,
                            current_step=STEP_MCP_STALE_RESULTS,
                            sub_skill=SKILL_MCP_TEST,
                            sub_skill_args=(
                                f"re-validate {bug_name} — MCP_TEST_RESULTS.md was "
                                f"validated against a stale commit; see {spec_dir_str}/SPEC.md"
                            ),
                        )
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


def enqueue_adhoc(
    repo_root: Path,
    bug_id: str,
    name: str,
    spec_dir: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    """Prepend an ad-hoc bug entry to docs/bugs/queue.json.

    Idempotent: if bug_id is already queued, emits a diagnostic and returns
    without modifying the file (exits 0 — safe to call from a re-materialize path).
    Creates queue.json (with empty queue) and docs/bugs/ if absent.
    """
    repo_root = repo_root.resolve()
    spec_dir = spec_dir or bug_id
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

    items.insert(0, {
        "id": bug_id,
        "name": name,
        "spec_dir": spec_dir,
        "severity": severity,
    })
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    return {"id": bug_id, "spec_dir": spec_dir, "status": "queued"}


# ===========================================================================
# === SMOKE FIXTURES + --test (WU-2.1 test-agent owns this section) =========
# ===========================================================================
#
# DO NOT MODIFY this section during WU-2.2 implementation work.
# The test-agent (WU-2.1) is the sole author of everything below the banner.
#
# Structure:
#   _write_yaml_sentinel()     — helper to write sentinel files
#   _build_bug_fixture()       — builds one named fixture under a temp root
#   run_smoke_tests()          — builds each fixture, calls compute_state(),
#                                asserts expected outcomes; returns 0/1
# ===========================================================================


def _write_yaml_sentinel(path: Path, kind: str, **fields: Any) -> None:
    """Write a sentinel file with YAML frontmatter (same helper as lazy-state.py)."""
    try:
        import yaml  # type: ignore[import]
        fm = {"kind": kind, **fields}
        body = "---\n" + yaml.safe_dump(fm, sort_keys=False).strip() + "\n---\n\n# Sentinel\n"
    except ImportError:
        # Fallback: emit minimal frontmatter manually so the harness can run
        # even if PyYAML is missing (parse_sentinel treats it as freeform → {}).
        pairs = "\n".join(f"{k}: {v}" for k, v in {"kind": kind, **fields}.items())
        body = f"---\n{pairs}\n---\n\n# Sentinel\n"
    path.write_text(body, encoding="utf-8")


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
        #   current_step == STEP_INVESTIGATE (reused step label)
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
                "current_step": STEP_INVESTIGATE,
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
             "--nonce", "cafe", "--repo-root", str(td_path)],
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

def main() -> int:
    parser = argparse.ArgumentParser(
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
    args = parser.parse_args()

    # multi-repo-concurrent-runs: bind the active repo ONCE so claude_state_dir()
    # scopes all run-scoped state to this repo's subdir (parity with lazy-state.py).
    lazy_core.set_active_repo_root(args.repo_root)

    # --repeat-count (advances the streak) and --repeat-count-peek (reads it
    # without advancing) are mutually exclusive — a single probe cannot both
    # advance and peek the persisted streak.
    if args.repeat_count and args.repeat_count_peek:
        _die("--repeat-count and --repeat-count-peek are mutually exclusive")

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
    if args.cycle_begin:
        lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-begin")
        if not args.bug_id or not args.nonce:
            _die("--cycle-begin requires --bug-id and --nonce")
        # hardening-blind-to-process-friction Phase 2 (D1) — coupled-pair mirror
        # of lazy-state.py: snapshot the live run identity + current HEAD sha into
        # the cycle marker so --cycle-end can detect a torn bracket / unexpected
        # commits. Best-effort: missing run marker / non-git tree → None.
        run_marker = lazy_core.read_run_marker()
        run_started_at = (run_marker or {}).get("started_at")
        begin_head_sha = lazy_core.head_sha_snapshot(Path(args.repo_root))
        marker = lazy_core.write_cycle_marker(
            feature_id=args.bug_id, nonce=args.nonce, kind=args.kind,
            run_started_at=run_started_at, begin_head_sha=begin_head_sha,
            sub_skill=args.sub_skill, sub_skill_args=args.sub_skill_args,
        )
        sys.stdout.write(json.dumps(marker, indent=2) + "\n")
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
        friction = lazy_core.cycle_end_friction_check(repo_root=Path(args.repo_root))
        cleared = lazy_core.clear_cycle_marker()
        out: dict = {"cycle_marker_cleared": cleared}
        if friction is not None:
            out["process_friction"] = friction
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
        marker = lazy_core.write_run_marker(
            pipeline="bug",
            cloud=args.cloud,
            repo_root=args.repo_root,
            max_cycles=args.max_cycles,
            attended=not args.unattended,
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

        # Delete the marker AND the registry (both are run-scoped state).
        deleted = lazy_core.delete_run_marker(clear_registry=True)
        result_out: dict = {"run_marker_deleted": deleted, "reason": reason}
        if override_note is not None:
            result_out["override"] = override_note
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
        try:
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
            )
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
        result = enqueue_adhoc(
            Path(args.repo_root), args.id, args.name, args.spec_dir, args.severity
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.test:
        return run_smoke_tests()

    if args.backfill_receipts:
        result = backfill_receipts(Path(args.repo_root))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0

    if args.verify_ledger is not None:
        # Scripted completion-ledger guard: verify the four preconditions for
        # marking a bug fixed. The orchestrator's && chains short-circuit on
        # non-zero exit when any check fails. When --plan is also passed, checks
        # 3+4 narrow to that plan part's scope (Phase 9 WU-3) — reuses the
        # existing --plan flag (shared with --apply-pseudo, no dest collision).
        result = lazy_core.verify_ledger(
            Path(args.repo_root), Path(args.verify_ledger),
            plan_path=Path(args.plan) if args.plan else None,
        )
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    real_device = resolve_real_device(args.real_device)
    state = compute_state(
        Path(args.repo_root),
        cloud=args.cloud,
        real_device=real_device,
        scope_bug_id=args.bug_id,
        park_needs_input=args.park_needs_input,
        park_blocked=args.park_blocked,
    )
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
    # No marker present → no-op (advance_forward_cycle returns None).
    if args.repeat_count:
        lazy_core.advance_forward_cycle(state)
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
            cycle_prompt = state.get("cycle_prompt")
            if cycle_prompt:
                lazy_core.register_emission_if_marked(
                    cycle_prompt, "cycle",
                    item_id=state.get("feature_id"),
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
        state["cycle_header"] = lazy_core.format_cycle_header(
            state, forward_cycles=_fwd,
            max_cycles=args.max_cycles, meta_cycles=_meta,
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
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
