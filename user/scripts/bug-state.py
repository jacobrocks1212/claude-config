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
    python3 bug-state.py --test               # run fixture smoke tests
    python3 bug-state.py --backfill-receipts  # write FIXED.md for archived bugs
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
TR_NEEDS_INPUT = "needs-input"
TR_COMPLETION_UNVERIFIED = "completion-unverified"
TR_DEVICE_QUEUE_EXHAUSTED = "device-queue-exhausted"
TR_CLOUD_QUEUE_EXHAUSTED = "cloud-queue-exhausted"
TR_QUEUE_MISSING = "queue-missing"
TR_STALE_UPSTREAM = "stale_upstream"
TR_ALL_DEFERRED = "all-remaining-deferred"
TR_SCOPED_ID_NOT_FOUND = "scoped-id-not-found"

# sub_skill tokens for bug-specific actions
SKILL_INVESTIGATE = "spec-bug"             # root-cause investigation / spec-bug skill
SKILL_PLAN_BUG = "plan-bug"               # implementation planning for a concluded investigation (SPEC **Status:** Concluded, no PHASES.md)
SKILL_SPEC_PHASES = "spec-phases"          # break bug SPEC into PHASES
SKILL_WRITE_PLAN = "write-plan"            # write an implementation plan
SKILL_EXECUTE_PLAN = "execute-plan"        # execute a Ready plan
SKILL_RETRO = "retro-feature"             # retro pass (reused from feature pipeline)
SKILL_MCP_TEST = "mcp-test"               # MCP / runtime validation
SKILL_MARK_FIXED = "__mark_fixed__"        # archive-on-fix pseudo-skill

# current_step strings (used both in the implementation and the test assertions)
STEP_BLOCKED = "Step 3: blocked"
STEP_NEEDS_INPUT = "Step 3.5: needs-input"
STEP_INVESTIGATE = "Step 4: investigate bug"
STEP_PHASES = "Step 6: spec phases"
STEP_WRITE_PLAN = "Step 7a: write plan"
STEP_EXECUTE_PLAN = "Step 7a: execute plan"
STEP_RETRO = "Step 8: retro phase"
STEP_MCP = "Step 9: run MCP tests"
STEP_MCP_SKIP = "Step 9: skip-mcp-test → validated"
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

# Park mode: when True (--park-needs-input flag), NEEDS_INPUT.md items are
# skipped (parked) instead of halting. The parked items accumulate in _PARKED.
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


def compute_state(
    repo_root: Path,
    cloud: bool,
    real_device: bool = True,
    scope_bug_id: str | None = None,
    park_needs_input: bool = False,
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
    _PARK_MODE = park_needs_input
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
        # Cloud-saturated skip (mirrors lazy-state.py lines ~912-919).
        # A bug that has RETRO_DONE.md + DEFERRED_NON_CLOUD.md but no VALIDATED.md
        # cannot be certified on a cloud host (cloud cannot run MCP tests).  Skip it
        # so the queue advances; TR_CLOUD_QUEUE_EXHAUSTED is emitted if no other bug
        # is actionable.
        # -----------------------------------------------------------------------
        if cloud:
            retro_done = (spec_dir / "RETRO_DONE.md").exists()
            deferred = (spec_dir / "DEFERRED_NON_CLOUD.md").exists()
            validated = (spec_dir / "VALIDATED.md").exists()
            if retro_done and deferred and not validated:
                cloud_saturated_skipped.append(bug_name)
                _diag(
                    f"cloud-saturated skipped: {bug_name} — DEFERRED_NON_CLOUD.md "
                    "present, no VALIDATED.md; awaiting workstation /lazy-bug."
                )
                continue

        # -----------------------------------------------------------------------
        # Device-saturated skip (mirrors lazy-state.py's device-axis logic).
        # -----------------------------------------------------------------------
        if not real_device:
            retro_done = (spec_dir / "RETRO_DONE.md").exists()
            device_deferred = (spec_dir / "DEFERRED_REQUIRES_DEVICE.md").exists()
            validated = (spec_dir / "VALIDATED.md").exists()
            if retro_done and device_deferred and not validated:
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

        # Park-mode: if --park-needs-input is active and this bug has an
        # unresolved NEEDS_INPUT.md, skip (park) it instead of halting the queue.
        # The item re-enters automatically once NEEDS_INPUT.md is resolved/renamed.
        # BLOCKED.md retains precedence: a bug carrying BOTH BLOCKED.md and
        # NEEDS_INPUT.md must still halt as "blocked", not be silently parked.
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
        return _bug_state(
            **common,
            current_step=STEP_BLOCKED,
            terminal_reason=TR_BLOCKED,
            notify_message=f"BLOCKED: {bug_name} — {phase}. Awaiting input.",
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

    # Step 8: Retro phase — runs before MCP.
    retro_done_file = spec_dir / "RETRO_DONE.md"
    if not retro_done_file.exists():
        return _bug_state(
            **common,
            current_step=STEP_RETRO,
            sub_skill=SKILL_RETRO,
            sub_skill_args=f"{spec_dir_str} --batch",
        )

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
                    return _bug_state(
                        **common,
                        current_step="Step 9b: write validated",
                        sub_skill="__write_validated_from_results__",
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
    # Entry: RETRO_DONE.md + VALIDATED.md (+ Status not yet Fixed).
    #
    # Cloud defensive backstop (mirrors lazy-state.py lines ~1441-1453).
    # The Step-2 cloud-saturated skip normally prevents a cloud host from ever
    # reaching this point without VALIDATED.md (RETRO_DONE.md + DEFERRED_NON_CLOUD.md
    # → skip in queue walk → TR_CLOUD_QUEUE_EXHAUSTED at exhaustion).  But if somehow
    # a bug arrives here on a cloud host without VALIDATED.md, halt rather than
    # silently archiving with zero validation.
    if cloud and not validated_file.exists():
        return _bug_state(
            **common,
            current_step="Step 10a: cloud halt",
            terminal_reason=TR_CLOUD_QUEUE_EXHAUSTED,
            notify_message=(
                f"{bug_name}: cloud work complete (phases + retro). "
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
        # All PHASES.md deliverables checked; no RETRO_DONE.md.
        # Expected: sub_skill == retro-feature (Step 8)
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
        # 3. Mid-fix — In-progress + PHASES + Ready plan → execute-plan
        (
            "mid-fix", False, True,
            {
                "feature_id": "bug-midfix",
                "sub_skill": SKILL_EXECUTE_PLAN,
                "current_step": STEP_EXECUTE_PLAN,
            },
        ),
        # 4. Phases complete, no retro → retro-feature (Step 8)
        (
            "phases-complete-no-retro", False, True,
            {
                "feature_id": "bug-pcnr",
                "sub_skill": SKILL_RETRO,
                "current_step": STEP_RETRO,
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
        "--verify-ledger", default=None, metavar="SPEC_PATH",
        help=(
            "Scripted completion-ledger guard (replaces the prose guard blocks "
            "in the lazy-bug skills). Verifies: (1) clean working tree, "
            "(2) HEAD == @{u}, (3) all implementation plans are status: Complete, "
            "(4) no real (non-verification) unchecked deliverables in SPEC_PATH/PHASES.md. "
            "Emits a JSON verdict and exits 0 on pass, 1 on first failing check."
        ),
    )
    args = parser.parse_args()

    if args.enqueue_adhoc:
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
        # non-zero exit when any check fails.
        result = lazy_core.verify_ledger(Path(args.repo_root), Path(args.verify_ledger))
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0 if result["ok"] else 1

    real_device = resolve_real_device(args.real_device)
    state = compute_state(
        Path(args.repo_root),
        cloud=args.cloud,
        real_device=real_device,
        scope_bug_id=args.bug_id,
        park_needs_input=args.park_needs_input,
    )
    sys.stdout.write(json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
