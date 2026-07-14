#!/usr/bin/env python3
"""
lazy_core.py — Domain-agnostic helpers extracted from lazy-state.py.

This module contains infrastructure and parsing utilities that are shared
between lazy-state.py and (in Phase 2) bug-state.py. All functions here
are pure helpers with no dependency on the /lazy pipeline's domain-specific
logic (queue loading, ROADMAP semantics, cloud/device branching, etc.).

Extracted as part of WU-1.2 (zero-behavior-change refactor). The acceptance
contract is that lazy-state.py's ``--test`` output is byte-identical before
and after extraction.

Public API (stable for Phase 2 reuse):
  Infrastructure:
    _atomic_write(path, content)
    _die(msg, path)
    _diag(msg)
    clear_diagnostics()
    reorder_queue(queue_path, item_id, *, to, queue_label)  # operator queue mutation

  Sentinel / plan parsing:
    parse_sentinel(path)
    _parse_plan_frontmatter(path)
    _plan_status(path)
    _plan_lowest_phase(path)
    _plan_series_index(path)
    _plan_sort_key(path)
    _plan_phase_set(path)
    _unchecked_wus_in_plan_scope(phases_text, phase_set)
    find_implementation_plans(spec_dir)
    find_retro_plans(spec_dir)
    latest_retro_plan(spec_dir)
    _has_any_complete_plan(spec_dir)
    retro_plan_has_significant_divergences(plan_path)

  PHASES.md analysis:
    count_deliverables(phases_text)
    remaining_unchecked_are_verification_only(phases_text)
    _VERIFICATION_SECTION_RE

  Receipts:
    write_completed_receipt(path, feature_id, date, *, provenance, ...)
    has_completion_receipt(spec_dir)
    spec_status(spec_dir)

  Runtime ownership (long-build-and-runtime-ownership):
    spawn_detached(cmd, *, cwd, ...)           # the one detached-spawn primitive
    run_transient_build(cmd, *, cwd, ...)       # M3.2 Transient Build contract
    kernel_start_time(pid, *, ...)
    write_runtime_lock / read_runtime_lock / verify_runtime_ownership
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("lazy_core.py requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)

# stale-runtime-health-200-false-blocked: the F7 freshness predicate
# (lazy-validation-readiness) — a sibling module in this same directory, always
# importable via the sys.path insertion both scripts + test_lazy_core.py already
# perform. Was previously orphaned (imported nowhere); see _default_stale_check.
import stale_binary


# ---------------------------------------------------------------------------
# Diagnostics + the atomic-write kernel now live in lazy_core._ctx (WU-2 of
# lazy-core-package-decomposition) — _DIAGNOSTICS is a shared mutable list
# (never rebound), so this import gives lazy_core._monolith._DIAGNOSTICS /
# _diag / clear_diagnostics / _atomic_write identity with the _ctx-owned
# objects. Import _ctx itself too (not just its names) so direct
# module-attribute patches on lazy_core._ctx (e.g. in tests) stay visible to
# the accessor-based rebindable globals below.
# ---------------------------------------------------------------------------

from . import _ctx
from ._ctx import _DIAGNOSTICS, _diag, clear_diagnostics, _atomic_write, _SCRIPTS_DIR

# lazy-core-package-decomposition Phase 2 Batch 2 (WU-2): the document-model
# (parsing) seam moved to docmodel.py. Unpatched names are imported by value;
# _VERIFICATION_ONLY_MARKER is a patched-census name, so the submodule itself
# is imported and referenced via attribute access at its remaining call sites
# (see the docmodel.<name> rewrites below).
from . import docmodel
from .docmodel import (
    parse_sentinel,
    repo_has_no_app_surface,
    phases_mcp_runtime_not_required,
    skip_waiver_refusal,
    spec_status,
    PROVISIONAL_SENTINEL,
    _PROVISIONAL_ELIGIBLE_GRADES,
    _parse_plan_frontmatter,
    _plan_status,
    plan_complexity,
    _DEFAULT_PLAN_COMPLEXITY,
    _plan_phase_set,
    _unchecked_wus_in_plan_scope,
    find_implementation_plans,
    _implementation_plans_exist,
    _has_any_complete_plan,
    count_deliverables,
    remaining_unchecked_are_verification_only,
    classify_blocking_unchecked_rows,
    _PHASE_HEADING_RE,
    _BOLD_STATUS_RE,
    parse_phases,
    retro_staleness,
    _phase_completion_plan,
    _coerce_evidence_count,
    _FAIL_CLOSED_EVIDENCE_SENTINELS,
    _FALSY_ENV_VALUES,
    _evidence_gate_killed,
)

from .statedir import (  # noqa: E402 — hook-surface seam (Phase 2 WU-5)
    _HOOK_EVENTS_FILENAME,
    _LEDGER_HEAD_CHARS,
    _MARKER_FILENAME,
    _REGISTRY_FILENAME,
    _load_registry,
    active_repo_root,
    claude_state_dir,
    repo_key,
)

# lazy-core-package-decomposition Phase 4 WU-3: the cycle/dispatch prompt +
# prompt-registry plane moved to dispatch.py. Names below are still referenced
# by monolith-resident code — imported back by value.
from .dispatch import (  # noqa: E402
    _CYCLE_COMMIT_BUDGET_DEFAULT,
    _CYCLE_COMMIT_MULTI,
    _CYCLE_COMMIT_NOISE_ALLOWANCE,
    _MULTI_COMMIT_CEILING_OVERRIDE,
    _emit_work_branch,
    consumed_emission_count,
    skill_declares_multi_commit,
    skill_declares_subagent_model,
)

# lazy-core-package-decomposition Phase 4 WU-2: the ledger/provenance/telemetry/
# intervention plane moved to ledgers.py. Names below are still referenced by
# monolith-resident code — imported back by value.
from .ledgers import (  # noqa: E402
    _DENY_LEDGER_FILENAME,
    _INTERVENTIONS_DIRNAME,
    _interventions_queue_flag,
    append_friction_ledger_entry,
    append_telemetry_event,
    derive_touched_from_brackets,
    derive_touched_from_grep,
    parse_intervention_hypothesis,
    record_intervention,
    write_provenance,
)

# lazy-core-package-decomposition Phase 4 WU-1: the completion-gate plane moved
# to gates.py. Names below are still referenced by monolith-resident code
# (apply_pseudo and friends) — imported back by value.
from .gates import (  # noqa: E402
    _plan_wu_checkbox_counts,
    autotick_verification_rows,
    commit_drift_verdict,
    evaluate_completion_evidence,
    gate_verdict_ok,
    observation_gap_promotable,
)


def _die(msg: str, path: Path | None = None) -> None:
    """Emit error JSON to stdout and exit 2."""
    out = {
        "error": msg,
        "path": str(path) if path else None,
    }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    sys.exit(2)


def reorder_queue(
    queue_path: "Path",
    item_id: str,
    *,
    to: "str | int",
    queue_label: str = "queue",
) -> dict:
    """Move (or remove) an existing queue entry — the operator-facing reorder primitive.

    Shared by lazy-state.py (``docs/features/queue.json``) and bug-state.py
    (``docs/bugs/queue.json``); each caller passes its OWN ``queue_path`` so the
    helper stays domain-agnostic. Mirrors ``enqueue_adhoc``'s load → validate-list
    → mutate → ``_atomic_write`` shape, reusing ``_die``/``_atomic_write``/``_diag``.

    ``to`` accepts:
      * ``"tail"``   — move the entry to the END of the queue.
      * ``"head"``   — move the entry to the FRONT of the queue.
      * ``"remove"`` — delete the entry from the queue.
      * an integer index (or its string form, e.g. ``"1"``) — move the entry to
        that index. Clamped to ``[0, len-1]``.

    A missing ``item_id`` or malformed queue JSON calls ``_die`` (exit 2, zero
    mutation) — never a silent no-op. Moving an entry already at the requested
    position rewrites NOTHING (byte-stable) and returns ``noop: True``.

    ``queue_label`` parameterizes the diagnostic/``_die`` message text
    ("queue.json" vs "bugs/queue.json") so both callers get correct diagnostics
    from the shared helper.

    Returns a JSON-serializable dict:
      ``{"reordered": bool, "noop": bool, "item_id": str, "operation": str,
         "new_position": int | None, "queue_length": int}``
    """
    # Parse the `to` argument into a canonical operation up front so a bad value
    # dies BEFORE we touch the file (zero side effects on a malformed request).
    target_index: "int | None" = None
    if isinstance(to, int):
        operation = f"index:{to}"
        target_index = to
    else:
        to_str = str(to).strip().lower()
        if to_str in ("tail", "head", "remove"):
            operation = to_str
        else:
            try:
                target_index = int(to_str)
            except (TypeError, ValueError):
                _die(
                    f"invalid --to for {queue_label}: {to!r} "
                    f"(expected tail|head|remove|<int index>)",
                    queue_path,
                )
                return {}  # pragma: no cover
            operation = f"index:{target_index}"

    # Load → validate the `queue` array is a list (same guard as enqueue_adhoc).
    if not queue_path.exists():
        _die(f"{queue_label} not found", queue_path)
        return {}  # pragma: no cover
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid {queue_label}: {exc}", queue_path)
        return {}  # pragma: no cover
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die(f"{queue_label} 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover

    # Find the entry to move/remove.
    idx = next(
        (i for i, e in enumerate(items)
         if isinstance(e, dict) and e.get("id") == item_id),
        None,
    )
    if idx is None:
        _die(f"item not queued: {item_id}", queue_path)
        return {}  # pragma: no cover

    original_len = len(items)

    if operation == "remove":
        items.pop(idx)
        data["queue"] = items
        _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
        _diag(f"reorder_queue: removed {item_id} from {queue_label}")
        return {
            "reordered": True,
            "noop": False,
            "item_id": item_id,
            "operation": "remove",
            "new_position": None,
            "queue_length": len(items),
        }

    # Resolve the destination index for a move.
    if operation == "tail":
        dest = original_len - 1
    elif operation == "head":
        dest = 0
    else:  # index:N
        dest = target_index if target_index is not None else idx
        # Clamp into range so an out-of-bounds index is a deterministic no-error.
        dest = max(0, min(dest, original_len - 1))

    if dest == idx:
        # Already at the requested position — byte-stable no-op (no rewrite).
        _diag(
            f"reorder_queue: {item_id} already at position {dest} in "
            f"{queue_label} (no-op)"
        )
        return {
            "reordered": True,
            "noop": True,
            "item_id": item_id,
            "operation": operation,
            "new_position": dest,
            "queue_length": original_len,
        }

    entry = items.pop(idx)
    items.insert(dest, entry)
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    _diag(
        f"reorder_queue: moved {item_id} to position {dest} in {queue_label}"
    )
    return {
        "reordered": True,
        "noop": False,
        "item_id": item_id,
        "operation": operation,
        "new_position": dest,
        "queue_length": len(items),
    }


def clear_queue_stub(queue_path: "Path", feature_id: str) -> dict:
    """Pop the ``"stub"`` key from a queue entry — the Step-4.5 clear-owner.

    The stub→research-pending transition (``lazy-state.py`` Step 4.5 → Step 5)
    has no clear-owner for the ``queue.json`` ``"stub"`` flag between
    baseline-lock and research-arrival: ``is_stub_spec`` keeps reading the
    surviving flag, so Step 4.5 re-fires every cycle (the commit-masked loop —
    ``docs/bugs/stub-spec-route-loops-until-queue-stub-cleared``). This helper
    clears the flag exactly once, at baseline-lock, under script ownership
    (HARD CONSTRAINT 1 forbids an orchestrator hand-edit of ``queue.json``).

    Mirrors ``reorder_queue``'s load → validate-list → mutate → ``_atomic_write``
    shape, reusing ``_die`` / ``_atomic_write`` / ``_diag``.

    A missing ``feature_id`` or malformed queue JSON calls ``_die`` (exit 2,
    zero mutation) — never a silent no-op. An entry that does NOT carry
    ``"stub"`` is a byte-stable no-op (``cleared: False`` — no rewrite).

    Returns ``{"cleared": bool, "feature_id": str, "queue_length": int}``.
    """
    if not queue_path.exists():
        _die("queue.json not found", queue_path)
        return {}  # pragma: no cover
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid queue.json: {exc}", queue_path)
        return {}  # pragma: no cover
    items = data.get("queue", [])
    if not isinstance(items, list):
        _die("queue.json 'queue' field must be an array", queue_path)
        return {}  # pragma: no cover

    idx = next(
        (i for i, e in enumerate(items)
         if isinstance(e, dict) and e.get("id") == feature_id),
        None,
    )
    if idx is None:
        _die(f"item not queued: {feature_id}", queue_path)
        return {}  # pragma: no cover

    entry = items[idx]
    if "stub" not in entry:
        # No stub key — byte-stable no-op (no rewrite).
        return {
            "cleared": False,
            "feature_id": feature_id,
            "queue_length": len(items),
        }

    entry.pop("stub", None)
    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    _diag(f"clear_queue_stub: cleared 'stub' flag for {feature_id}")
    return {
        "cleared": True,
        "feature_id": feature_id,
        "queue_length": len(items),
    }


# ---------------------------------------------------------------------------
# Validation-escalation predicate (Phase 11 WU-1a)
# ---------------------------------------------------------------------------

# Suffix the Step-3 blocked terminal appends to notify_message when the
# escalation fires. Defined HERE (not in the state scripts) so lazy-state.py
# and bug-state.py emit the byte-identical message — the orchestrators key
# corrective-phase drafting discipline on this exact text.
#
# REWORDED (mcp-validation-peels-one-seam-per-loop Deferred Follow-Up item 2,
# closed by stale-runtime-health-200-false-blocked's STATE-lane pass): the
# full-chain seam-audit mandate was RE-SCOPED by that bug's SKILLS-lane fix to
# apply at EVERY mcp-validation retry_count (starting at the first failure,
# authored into BLOCKED.md's own body), not only here at retry_count >= 2. This
# predicate's THRESHOLD is unchanged (still exactly `retry_count >= 2` — see
# below); only the WORDING is corrected so `retry_count >= 2` reads as the
# ADDITIONAL /investigate-mandatory backstop tier layered on top of the
# standing seam-audit requirement, not as the sole trigger for seam enumeration
# (a documentation-accuracy edit only — no test asserts this string's exact
# wording, only that the notify_message carries the constant verbatim; see
# test_lazy_state_blocked_escalation_payload / test_bug_state_blocked_
# escalation_payload in test_lazy_core.py).
VALIDATION_ESCALATION_SUFFIX = (
    " ESCALATION: 2+ validation failures — /investigate is now MANDATORY "
    "before the next corrective phase (the full-chain seam audit itself is "
    "required starting at the FIRST mcp-validation failure, not gated on "
    "this threshold)."
)


def validation_escalation(meta: dict[str, Any] | None) -> bool:
    """Return True when a BLOCKED.md sentinel shows repeated MCP-validation failure.

    Single source of truth for the Phase 11 WU-1a escalation policy, consumed
    by BOTH state scripts' Step-3 blocked terminals: ``blocker_kind ==
    "mcp-validation"`` AND ``retry_count >= 2``. The threshold is 2 because the
    d8-live-looping pattern showed each BLOCKED→add-phase round discovering
    exactly ONE more broken layer.

    REWORDED (mcp-validation-peels-one-seam-per-loop): this predicate's
    BEHAVIOR is unchanged — still exactly ``retry_count >= 2``. What changed is
    what firing MEANS: the full-chain seam-audit requirement itself now applies
    at every ``mcp-validation`` retry_count (the SKILLS-lane prose mandate,
    authored starting at the first failure); this predicate firing True marks
    the point past which ``/investigate`` is ADDITIONALLY mandatory before the
    next corrective phase — the backstop tier, not the sole seam-enumeration
    trigger.

    Tolerances (backward compatibility — pre-Phase-11 sentinels must never
    escalate or crash):
      - ``retry_count`` as an int is used directly.
      - ``retry_count`` as a string of digits (quoted YAML) is coerced.
      - Missing/malformed ``retry_count``, missing ``blocker_kind``, a non-
        mcp-validation ``blocker_kind``, or a None/empty meta → False.
      - YAML booleans are ints in Python (``True == 1``); they are NOT counts,
        so bool values are explicitly rejected rather than coerced.
    """
    meta = meta or {}
    if meta.get("blocker_kind") != "mcp-validation":
        return False
    raw = meta.get("retry_count")
    # bool is an int subclass — `retry_count: true` must not coerce to 1.
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        return raw >= 2
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip()) >= 2
    # Missing or malformed → no escalation (never crash the blocked terminal).
    return False


# ---------------------------------------------------------------------------
# SPEC parsing helpers
# ---------------------------------------------------------------------------

def has_completion_receipt(spec_path: Path | None, filename: str = "COMPLETED.md") -> bool:
    """True iff a durable, content-valid completion receipt exists in the feature/bug dir.

    The receipt is written ONLY by ``__mark_complete__``'s completion-integrity
    gate (or backfilled with ``provenance: backfilled-unverified``). Its presence
    AND content validity are the structural proof that a feature reached
    ``Complete`` THROUGH the pipeline gate rather than via an out-of-band
    SPEC/ROADMAP edit. See _components/completion-integrity-gate.md.

    Content-validation contract:
    - ``spec_path is None`` → ``False`` (silently; no directory to check).
    - Receipt file absent → ``False`` (silently; normal not-yet-complete case).
    - Receipt file present but MALFORMED → ``False`` + emit a ``_diag()``
      diagnostic naming the path and the specific defect. Malformed means any of:
        * empty file / no YAML frontmatter (``parse_sentinel`` returns ``{}``)
        * ``kind`` key absent from frontmatter
        * ``kind`` value not in ``{"completed", "fixed"}``
        * ``provenance`` key absent or its value is empty/whitespace
      These cases count as "completion-unverified" and halt the gate just as if
      the file were absent, while producing a loud diagnostic so the issue can
      be investigated.
    - Receipt file present and valid → ``True``.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    Default receipt filename is ``COMPLETED.md`` — matches current behavior.
    Bug-state.py passes ``filename="FIXED.md"`` for the bug receipt convention.
    """
    if spec_path is None:
        return False

    receipt_path = spec_path / filename
    if not receipt_path.exists():
        # Normal not-yet-complete case — absence is silent, not a diagnostic.
        return False

    # Receipt file exists — validate its content before trusting it.
    meta = parse_sentinel(receipt_path)

    if meta is None:
        # parse_sentinel calls _die() internally for fatal parse errors; this
        # branch is a safety net in case it ever returns None without dying.
        _diag(
            f"completion receipt at {receipt_path} could not be parsed"
            " (parse_sentinel returned None) — treating as missing"
        )
        return False

    # Empty dict means the file existed but had no YAML frontmatter fence at all.
    if not meta:
        _diag(
            f"completion receipt at {receipt_path} has no YAML frontmatter"
            " — treating as missing (expected '---' fence with kind + provenance)"
        )
        return False

    # Validate 'kind' field.
    kind = meta.get("kind")
    if kind not in {"completed", "fixed"}:
        _diag(
            f"completion receipt at {receipt_path} has invalid or missing 'kind'"
            f" (got {kind!r}; expected 'completed' or 'fixed')"
            " — treating as missing"
        )
        return False

    # Validate 'provenance' field — must be present and non-empty.
    provenance = meta.get("provenance")
    if not provenance or not str(provenance).strip():
        _diag(
            f"completion receipt at {receipt_path} is missing or has empty 'provenance'"
            f" (got {provenance!r})"
            " — treating as missing (provenance is required to trust the receipt)"
        )
        return False

    return True


def write_completed_receipt(
    path: Path,
    feature_id: str,
    date: str,
    *,
    provenance: str,
    kind: str = "completed",
    completed_commit: str | None = None,
    validated_via: str | None = None,
    mcp_pass_count: int | None = None,
    mcp_total_count: int | None = None,
    auto_ticked_rows: int | None = None,
    body_note: str = "",
) -> None:
    """Write a completion receipt (kind: completed by default) per sentinel-frontmatter.md.

    ``provenance: gated`` is written by the completion-integrity gate at flip
    time; ``provenance: backfilled-unverified`` is written by --backfill-receipts
    for features grandfathered in during the receipt-gating rollout.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    The ``kind: completed`` value and the ``# Completion Receipt`` title are
    the defaults that preserve byte-for-byte behavior at all existing call sites.

    ``kind`` is keyword-only and defaults to ``"completed"`` so that lazy-state.py's
    feature pipeline behavior is unchanged.  bug-state.py passes ``kind="fixed"``
    so that FIXED.md receipts carry the correct ``kind: fixed`` frontmatter value
    required by the Phase-5 consistency checker.
    """
    lines = [
        "---",
        f"kind: {kind}",
        f"feature_id: {feature_id}",
        f"date: {date}",
        f"provenance: {provenance}",
    ]
    if completed_commit:
        lines.append(f"completed_commit: {completed_commit}")
    if validated_via:
        lines.append(f"validated_via: {validated_via}")
    if mcp_pass_count is not None and mcp_total_count is not None:
        lines.append(f"mcp_pass_count: {mcp_pass_count}")
        lines.append(f"mcp_total_count: {mcp_total_count}")
    # auto_ticked_rows: how many unchecked verification rows the evidence-gated
    # completion gate auto-ticked this completion (completion-coherence-gate-
    # reconciliation Phase 3). Omitted when None (legacy / --backfill callers);
    # 0 is recorded explicitly so an auditor can tell "gate ran, ticked nothing"
    # from "gate did not run".
    if auto_ticked_rows is not None:
        lines.append(f"auto_ticked_rows: {auto_ticked_rows}")
    lines.append("---")
    lines.append("")
    lines.append("# Completion Receipt")
    lines.append("")
    if body_note:
        lines.append(body_note)
        lines.append("")
    _atomic_write(path, "\n".join(lines))


# ---------------------------------------------------------------------------
# Stale-upstream helpers
# ---------------------------------------------------------------------------

_STALE_UPSTREAM_FILENAME = "STALE_UPSTREAM.md"


def read_stale_upstream(item_dir: Path) -> str | None:
    """Return the full text of <item_dir>/STALE_UPSTREAM.md, or None if absent."""
    path = item_dir / _STALE_UPSTREAM_FILENAME
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_stale_upstream(item_dir: Path, diff: str) -> None:
    """Write <item_dir>/STALE_UPSTREAM.md with diff as its content (atomic)."""
    path = item_dir / _STALE_UPSTREAM_FILENAME
    _atomic_write(path, diff)


def clear_stale_upstream(item_dir: Path) -> None:
    """Remove <item_dir>/STALE_UPSTREAM.md; no-op if absent."""
    path = item_dir / _STALE_UPSTREAM_FILENAME
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Materialized-list helpers
# ---------------------------------------------------------------------------

_MATERIALIZED_FILENAME = "materialized.json"


def read_materialized(work_dir: Path) -> list[dict]:
    """Read <work_dir>/materialized.json and return the list of records.

    Returns an empty list if the file is absent.
    """
    path = work_dir / _MATERIALIZED_FILENAME
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_materialized(work_dir: Path, wi_id, feature_id, changed_date) -> None:
    """Append a record to <work_dir>/materialized.json (atomic, idempotent on wi_id).

    If a record with the given wi_id already exists, this is a no-op — the
    existing record's values are preserved and no duplicate is written.
    """
    records = read_materialized(work_dir)
    for record in records:
        if record.get("wi_id") == wi_id:
            return
    records.append({
        "wi_id": wi_id,
        "feature_id": feature_id,
        "materialized_changedDate": changed_date,
    })
    path = work_dir / _MATERIALIZED_FILENAME
    _atomic_write(path, json.dumps(records, indent=2))


def update_materialized_changeddate(work_dir: Path, wi_id, new_changed_date) -> None:
    """Update the materialized_changedDate for the record matching wi_id (atomic).

    If no record with the given wi_id is found, this is a no-op (no exception).
    """
    records = read_materialized(work_dir)
    found = False
    for record in records:
        if record.get("wi_id") == wi_id:
            record["materialized_changedDate"] = new_changed_date
            found = True
            break
    if not found:
        return
    path = work_dir / _MATERIALIZED_FILENAME
    _atomic_write(path, json.dumps(records, indent=2))


# ---------------------------------------------------------------------------
# Stage derivation
# ---------------------------------------------------------------------------

_WIP_FILENAME = "WIP.md"
_REVIEWED_FILENAME = "REVIEWED.md"


def derive_stage(item_dir) -> str:
    """Derive the current workflow stage of an item directory from its artifact set.

    Stage is DERIVED from filesystem artifacts (never asserted by a skill directly).
    Accepts any path-like object; coerces to Path internally. Never raises on a
    missing directory — returns "spec" as the documented default.

    Precedence (first match wins):
      1. done          — COMPLETED.md or FIXED.md receipt present (terminal; intentionally
                         wins over halt sentinels because receipts are permanent, irreversible).
      2. stale-upstream — STALE_UPSTREAM.md present (read_stale_upstream is not None).
      3. blocked       — BLOCKED.md present.
      4. needs-input   — NEEDS_INPUT.md present.
      5. reviewed      — REVIEWED.md present.
      6. review        — PR.md present AND PHASES.md present.  If PR.md is absent, this
                         rung is skipped and the artifact-ladder result (implement or lower)
                         stands — "omit PR.md and let implement stand" fallback.
      Artifact ladder:
      7. implement     — plans/ subdir with ≥1 *.md file AND PHASES.md has ≥1 checked
                         deliverable (line matching r"^\\s*-\\s*\\[[xX]\\]").
      8. plan          — plans/ subdir with ≥1 *.md file (but zero checked deliverables).
      9. phases        — PHASES.md exists (but no plans/).
     10. research      — RESEARCH.md or RESEARCH_SUMMARY.md exists.
     11. spec          — default / fallback.

    Returns one of: spec | research | phases | plan | implement | review |
                    reviewed | blocked | needs-input | stale-upstream | done
    """
    item_dir = Path(item_dir)
    if not item_dir.exists():
        return "spec"

    # 1. done — receipt files are terminal
    if has_completion_receipt(item_dir, "COMPLETED.md") or has_completion_receipt(item_dir, "FIXED.md"):
        return "done"

    # 2. stale-upstream
    if read_stale_upstream(item_dir) is not None:
        return "stale-upstream"

    # 3. blocked
    if (item_dir / "BLOCKED.md").exists():
        return "blocked"

    # 4. needs-input
    if (item_dir / "NEEDS_INPUT.md").exists():
        return "needs-input"

    # 5. reviewed
    if (item_dir / _REVIEWED_FILENAME).exists():
        return "reviewed"

    # 6. review — PR.md + PHASES.md both present
    if (item_dir / "PR.md").exists() and (item_dir / "PHASES.md").exists():
        return "review"

    # 7-8. Artifact ladder: plans/ subdir with ≥1 *.md
    plans_dir = item_dir / "plans"
    if plans_dir.exists() and any(plans_dir.glob("*.md")):
        # Determine implement vs plan by checking for ≥1 checked deliverable in PHASES.md
        phases_path = item_dir / "PHASES.md"
        if phases_path.exists():
            phases_text = phases_path.read_text(encoding="utf-8")
            for line in phases_text.splitlines():
                if re.match(r"^\s*-\s*\[[xX]\]", line):
                    return "implement"
        return "plan"

    # 9. phases
    if (item_dir / "PHASES.md").exists():
        return "phases"

    # 10. research
    if (item_dir / "RESEARCH.md").exists() or (item_dir / "RESEARCH_SUMMARY.md").exists():
        return "research"

    # 11. spec (default)
    return "spec"


# ---------------------------------------------------------------------------
# WIP liveness sentinel helpers
# ---------------------------------------------------------------------------

def _write_wip(item_dir: Path, fields: dict) -> None:
    """Serialize WIP frontmatter and atomically write <item_dir>/WIP.md.

    Unknown values serialize as empty (never the literal "None").
    """
    def _fmt(value):
        return "" if value is None or value == "None" else value

    lines = [
        "---",
        f"kind: {fields['kind']}",
        f"wi_id: {_fmt(fields['wi_id'])}",
        f"slug: {_fmt(fields['slug'])}",
        f"branch: {_fmt(fields['branch'])}",
        f"host: {_fmt(fields['host'])}",
        f"started_at: \"{fields['started_at']}\"",
        f"last_touched: \"{fields['last_touched']}\"",
        "---",
        "",
        "# Work in progress",
    ]
    _atomic_write(item_dir / _WIP_FILENAME, "\n".join(lines))


def track_open(item_dir, wi_id, slug, branch, host, now: str) -> None:
    """Create or refresh <item_dir>/WIP.md as the liveness sentinel for an active work item.

    Idempotent: if WIP.md already exists, ``started_at`` is preserved from the
    existing file and only ``last_touched`` is advanced to ``now``.  A refresh
    never degrades known fields: when ``wi_id``/``branch``/``host`` are missing
    (None/empty, or a stale literal "None" from a prior bad write), the existing
    values are kept.  Time is injected via ``now`` (ISO-8601 string) for
    determinism — no ``datetime.now()`` call occurs here.
    """
    item_dir = Path(item_dir)
    item_dir.mkdir(parents=True, exist_ok=True)

    def _keep(new, old):
        return new if new not in (None, "", "None") else old

    wip_path = item_dir / _WIP_FILENAME
    existing = parse_sentinel(wip_path) or {}
    started_at = existing.get("started_at") or now
    wi_id = _keep(wi_id, _keep(existing.get("wi_id"), None))
    branch = _keep(branch, _keep(existing.get("branch"), None))
    host = _keep(host, _keep(existing.get("host"), None))

    _write_wip(item_dir, {
        "kind": "wip",
        "wi_id": wi_id,
        "slug": slug,
        "branch": branch,
        "host": host,
        "started_at": started_at,
        "last_touched": now,
    })


def track_touch(item_dir, now: str) -> None:
    """Advance ``last_touched`` in an existing <item_dir>/WIP.md to ``now``.

    If WIP.md is absent, this is a no-op — the file is never created here.
    All other fields are preserved unchanged.  Time is injected via ``now``
    for determinism.
    """
    item_dir = Path(item_dir)
    wip_path = item_dir / _WIP_FILENAME
    existing = parse_sentinel(wip_path)
    if not existing:
        return
    existing["last_touched"] = now
    _write_wip(item_dir, existing)


def track_close(item_dir) -> None:
    """Remove <item_dir>/WIP.md, marking the work item as no longer active.

    No-op if WIP.md is absent.
    """
    item_dir = Path(item_dir)
    (item_dir / _WIP_FILENAME).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Pseudo-skill dispatcher — deterministic sentinel / receipt writes
# ---------------------------------------------------------------------------

# _current_head is defined once, further below (WU-4 "Persisted probe
# signature / loop detection" section) — it used to be defined a second time
# here with an identical body, an undetected F811 duplicate (silently shadowed
# at module level; production-sentinel-writes-bypass-atomic-write's "bonus
# finding," the proof this file had zero lint coverage). Consumed here by
# apply_pseudo's ``__write_validated_from_results__`` freshness backstop —
# same function, no behavior change.


def _resolve_under_repo(repo_root: Path, value) -> str:
    """Canonicalize a path that may be absolute, repo-relative, or a bare
    basename into one comparable string (lowercased, forward-slashed).

    Used by the WU-3 (unified-pipeline-orchestrator P5) queue trim to match a
    completing feature against a queue entry whose stored ``spec_dir`` may be a
    path-form value ("docs/features/foo") rather than a bare basename ("foo").
    Both the completing dir and each entry's spec_dir are run through this so a
    ``-followups`` entry is matched by its RESOLVED path, not just the basename.
    """
    p = Path(value)
    if not p.is_absolute():
        p = repo_root / p
    try:
        resolved = os.path.realpath(str(p))
    except OSError:
        resolved = str(p)
    return resolved.replace("\\", "/").rstrip("/").lower()


# Marker appended to a struck ROADMAP row (and the idempotency sentinel — a row
# already carrying this token is NOT re-struck).
_ROADMAP_COMPLETE_TOKEN = "✅ COMPLETE"


def _strike_roadmap_row(
    roadmap_path: Path, repo_root: Path, spec_path: Path, feature_id: str
) -> bool:
    """Strike the ROADMAP row(s) referencing the completed feature.

    A row "references" the feature iff it contains the feature_id token OR the
    spec dir basename as a word. Striking = wrap the row's content in ``~~``
    strikethrough and append a `` ✅ COMPLETE`` token. Idempotent: a row that
    already carries the COMPLETE token (or is already ``~~``-wrapped for this
    feature) is left untouched.

    Returns True iff at least one row was newly struck (the file was rewritten).
    Matches the WU-3 deliverable; never raises on a malformed ROADMAP — it
    simply finds no row to strike and returns False (the OSError on read/write
    is surfaced as a warning by the caller).
    """
    text = roadmap_path.read_text(encoding="utf-8")
    basename = spec_path.name
    # A row references the feature if it contains the id or the basename as a
    # whole word (avoids matching a prefix of an unrelated longer slug).
    tokens = {t for t in (feature_id, basename) if t}
    token_res = [re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])") for t in tokens]

    lines = text.splitlines(keepends=True)
    changed = False
    for i, line in enumerate(lines):
        # Skip lines with no trailing newline handling difference — operate on
        # the content, re-attach the original line ending.
        stripped = line.rstrip("\n")
        eol = line[len(stripped):]
        if not any(rx.search(stripped) for rx in token_res):
            continue
        # Idempotency: already struck for this feature → skip.
        if _ROADMAP_COMPLETE_TOKEN in stripped:
            continue
        content = stripped
        # For a markdown table row, strike only the inner cells (keep the
        # leading/trailing pipes structurally intact) so the table still parses;
        # for a bullet/plain line, strike the whole content.
        if content.lstrip().startswith("|") and content.rstrip().endswith("|"):
            inner = content.strip().strip("|")
            new_inner = f" ~~{inner.strip()}~~  {_ROADMAP_COMPLETE_TOKEN} "
            # Preserve any leading indentation before the first pipe.
            lead = content[: len(content) - len(content.lstrip())]
            new_content = f"{lead}|{new_inner}|"
        else:
            new_content = f"~~{content.rstrip()}~~  {_ROADMAP_COMPLETE_TOKEN}"
        lines[i] = new_content + eol
        changed = True

    if changed:
        _atomic_write(roadmap_path, "".join(lines))
    return changed


def _top_status_is(md_path: Path, status_value: str) -> bool:
    """True iff the FIRST ``**Status:**`` line of ``md_path`` reads ``status_value``.

    A file with NO ``**Status:**`` line counts as satisfied — the completion
    sequence's ``re.sub(count=1)`` flip is a no-op there, so a genuinely-done dir
    whose SPEC/PHASES simply carries no top status line must not be forced into a
    resume. An unreadable file also returns True (an IO error must never
    manufacture a partial-apply verdict). Used by
    ``_completion_postconditions_missing``.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return True
    m = re.search(r"^\*\*Status:\*\*[ \t]*(.*?)[ \t]*$", text, re.MULTILINE)
    if m is None:
        return True
    return m.group(1).strip() == status_value


def _roadmap_has_unstruck_row(
    roadmap_path: Path, spec_path: Path, feature_id: str
) -> bool:
    """True iff ROADMAP.md carries a row referencing the feature that is NOT yet
    struck (i.e. ``_strike_roadmap_row`` WOULD rewrite it).

    Read-only mirror of the strike loop's match + ``_ROADMAP_COMPLETE_TOKEN``
    idempotency test — the completion post-condition audit's inverse of the
    ROADMAP strike. An unreadable ROADMAP returns False (the strike itself
    surfaces the OSError as a warning; the audit must not force a resume on it).
    """
    try:
        text = roadmap_path.read_text(encoding="utf-8")
    except OSError:
        return False
    tokens = {t for t in (feature_id, spec_path.name) if t}
    if not tokens:
        return False
    token_res = [re.compile(rf"(?<![\w-]){re.escape(t)}(?![\w-])") for t in tokens]
    for line in text.splitlines():
        stripped = line.rstrip("\n")
        if not any(rx.search(stripped) for rx in token_res):
            continue
        if _ROADMAP_COMPLETE_TOKEN in stripped:
            continue
        return True
    return False


def _completion_postconditions_missing(
    spec_path: Path,
    repo_root: Path,
    feature_id: str,
    status_value: str,
    is_fixed: bool,
) -> list[str]:
    """Return the list of unsatisfied completion post-conditions for an
    already-receipted dir (empty ⇒ the completion is fully applied → noop).

    The idempotency key of ``apply_pseudo``'s ``__mark_complete__`` /
    ``__mark_fixed__`` branch (mark-complete-partial-apply-noop-unrecoverable).
    The receipt is the FIRST externally-observable post-condition written, so a
    crash between the receipt write and the SPEC status flip leaves a
    receipt-present + ``Status: In-progress`` dir that the receipt-only noop
    could never repair (the state machine re-routed to ``__mark_complete__``
    forever, zero writes). This audit checks EVERY post-condition the state
    machine routes on:

      * SPEC.md / PHASES.md first ``**Status:**`` line == ``status_value``
        (a file with no status line is satisfied — the flip is a no-op there);
      * cleanup sentinels (VALIDATED.md / RETRO_DONE.md / DEFERRED_NON_CLOUD.md)
        absent;
      * feature (complete) path ONLY: the queue.json entry trimmed AND the
        ROADMAP row struck (the bug/fixed path trims via ``archive_fixed`` and
        has no feature ROADMAP, so those two are audited only when not is_fixed).

    Any missing entry means the prior completion died mid-sequence → the caller
    RESUMES the idempotent tail. Pure read; never raises.
    """
    missing: list[str] = []

    spec_md = spec_path / "SPEC.md"
    if spec_md.exists() and not _top_status_is(spec_md, status_value):
        missing.append("SPEC.md status")

    phases_md = spec_path / "PHASES.md"
    if phases_md.exists() and not _top_status_is(phases_md, status_value):
        missing.append("PHASES.md status")

    for cleanup_name in ("VALIDATED.md", "RETRO_DONE.md", "DEFERRED_NON_CLOUD.md"):
        if (spec_path / cleanup_name).exists():
            missing.append(cleanup_name)

    if not is_fixed:
        queue_path = repo_root / "docs" / "features" / "queue.json"
        if queue_path.exists():
            try:
                qdata = json.loads(queue_path.read_text(encoding="utf-8"))
                qitems = qdata.get("queue", [])
                if isinstance(qitems, list):
                    resolved_spec = _resolve_under_repo(repo_root, spec_path)

                    def _entry_matches(e: dict) -> bool:
                        sd = e.get("spec_dir")
                        if sd == spec_path.name or e.get("id") == feature_id:
                            return True
                        if isinstance(sd, str) and sd:
                            if _resolve_under_repo(repo_root, sd) == resolved_spec:
                                return True
                        return False

                    if any(
                        isinstance(e, dict) and _entry_matches(e) for e in qitems
                    ):
                        missing.append("queue.json entry")
            except (json.JSONDecodeError, OSError):
                # A malformed queue is a non-fatal warning at trim time, not a
                # partial-apply signal — do not force a resume on it here.
                pass

        roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
        if roadmap_path.exists() and _roadmap_has_unstruck_row(
            roadmap_path, spec_path, feature_id
        ):
            missing.append("ROADMAP.md row")

    return missing


def apply_pseudo(
    repo_root: Path,
    name: str,
    spec_path: Path,
    *,
    plan_path: Path | None = None,
    date: str | None = None,
    feature_id: str | None = None,
    reason: str | None = None,
    deferred_step: int | None = None,
) -> dict:
    """Single-author the deterministic sentinel/receipt write for a lazy pseudo-skill.

    This function is the SOLE AUTHOR of every scripted file write that lazy
    pseudo-skills previously requested via prose instructions.  Moving authorship
    here gives us:
      (1) A machine-verifiable idempotency contract for every named write.
      (2) A single grep-able call-site instead of duplicated skill prose.
      (3) An easy way to dry-run or audit the writes before they happen.

    Return shape (always present — callers may JSON-dump unconditionally):
    ::

        {
            "name":    str,          # the pseudo-skill name
            "ok":      bool,         # True iff the action succeeded (or was a noop)
            "refused": str | None,   # non-None means a precondition was not met
            "wrote":   [str, ...],   # relative paths written (empty on noop/refused)
            "deleted": [str, ...],   # relative paths deleted (empty on noop/refused)
            "noop":    bool,         # True iff the file(s) already existed exactly
        }

    Extra keys some pseudo-skills attach (absent otherwise — callers may still
    JSON-dump unconditionally):
      - ``resumed`` (``__mark_complete__`` / ``__mark_fixed__``): True iff this
        call recovered a crash-window PARTIAL apply — a receipt was already
        present but a completion post-condition was missing, so the idempotent
        tail (SPEC/PHASES flip, sentinel delete, queue trim, ROADMAP strike,
        provenance) was re-applied to converge
        (mark-complete-partial-apply-noop-unrecoverable). False on the normal
        path; a genuinely-done dir returns a plain ``noop`` earlier.
      - ``flipped_phases`` (``__mark_complete__`` / ``__mark_fixed__``): phase
        headings the completion-coherence gate auto-flipped to Complete.
      - ``queue_trimmed`` (``__mark_complete__`` / ``__mark_fixed__``): True iff
        the completed feature's entry was removed from
        ``docs/features/queue.json`` this call. Always False for the bug/fixed
        path (whose queue trim lives in ``archive_fixed`` step 6). Prevents the
        AlgoBooth ``queue.no-completed`` consistency error on feature completion.
      - ``warnings`` (``__write_validated_from_results__``,
        ``__mark_complete__``): non-fatal caveats — freshness caveats (legacy
        results without ``validated_commit``, or an unresolvable HEAD) or a
        malformed ``docs/features/queue.json`` that could not be auto-trimmed;
        also echoed to stderr.

    Parameters
    ----------
    repo_root:
        Root of the repository.  Used by ``__flip_plan_complete_*`` when
        building the relative path returned in ``wrote``, and by
        ``__write_validated_from_results__`` to resolve the current
        ``git rev-parse HEAD`` for the sha-freshness backstop.
    name:
        The pseudo-skill identifier dispatched by the orchestrator.  Recognised
        values are listed below; anything else returns ``refused``.
    spec_path:
        Absolute path to the feature / bug spec directory (contains SPEC.md,
        PHASES.md, plans/, etc.).
    plan_path:
        Override for ``__flip_plan_complete_cloud_saturated__``.  When given, this
        exact file is flipped rather than auto-discovering via
        ``find_implementation_plans``.
    date:
        ISO-8601 date string (``YYYY-MM-DD``) stamped into every receipt.
        Defaults to ``datetime.date.today().isoformat()`` when ``None``.
    feature_id:
        Frontmatter ``feature_id:`` value.  Defaults to ``spec_path.name``.
    reason:
        Human-readable reason for ``__write_deferred_non_cloud__``; defaults to
        ``"deferred to workstation (no Tauri/MCP in cloud)"``.
    deferred_step:
        The step index being deferred; used only by
        ``__write_deferred_non_cloud__``.  Defaults to ``8``.

    Dispatched pseudo-skills
    ------------------------
    ``__write_validated_from_skip__``
        Gate: ``spec_path/SKIP_MCP_TEST.md`` must exist and parse to a non-None
        dict.  Writes ``spec_path/VALIDATED.md`` (kind: validated).  Idempotent:
        if VALIDATED.md already exists and parses kind=="validated" → noop.

    ``__write_validated_from_results__``
        Gates (in order; see the branch comment for why the order is
        load-bearing): (1) ``spec_path/MCP_TEST_RESULTS.md`` must exist,
        carry ``kind: mcp-test-results``, and parse a ``scenarios`` list;
        (2) noop on existing VALIDATED.md with kind=="validated";
        (3) result-literal gate — ``result: all-passing`` AND
        ``pass_count == total_count`` (ints; refusals name expected vs
        found); (4) freshness backstop — ``validated_commit`` must match
        repo_root's current HEAD (legacy field-less files and non-git roots
        pass with a ``warnings`` entry instead).  Writes VALIDATED.md
        copying ``mcp_scenarios`` (and the ``validated_commit`` anchor when
        present) from the results file.

    ``__write_deferred_non_cloud__``
        No gate input.  Writes ``spec_path/DEFERRED_NON_CLOUD.md`` (kind:
        deferred-non-cloud).  Idempotent: file already exists → noop.

    ``__flip_plan_complete_cloud_saturated__``
        Target plan: ``plan_path`` if given, else the single non-Complete plan
        returned by ``find_implementation_plans(spec_path)``.  Regex-replaces
        the first ``status:`` frontmatter line with ``status: Complete``,
        leaving every other byte intact.  Idempotent on already-Complete plan.

    ``__mark_complete__``
        Gate: ``spec_path/VALIDATED.md`` OR ``spec_path/SKIP_MCP_TEST.md``
        must be present.  Writes COMPLETED.md (kind: completed, provenance:
        gated), flips SPEC.md/PHASES.md top-level ``**Status:**``, deletes
        VALIDATED.md / RETRO_DONE.md / DEFERRED_NON_CLOUD.md, TRIMS the
        completed feature's ``docs/features/queue.json`` entry, and STRIKES its
        ``docs/features/ROADMAP.md`` row.  Idempotent on existing COMPLETED.md.

        WU-3 (unified-pipeline-orchestrator P5) enhancements:
          - The queue trim now matches by the RESOLVED ``spec_dir`` (each
            entry's stored ``spec_dir`` resolved against ``repo_root`` and
            compared to the resolved ``spec_path``), in addition to the legacy
            basename + ``id`` keys — so a ``-followups`` entry whose stored
            ``spec_dir`` is a path-form value (not the bare basename) is still
            trimmed, killing the ``-followups`` queue.no-completed recovery
            class. The returned dict's ``queue_trimmed`` reports it.
          - The ROADMAP strike (previously an orchestrator-inline step) is now
            authored HERE: the row referencing the feature is wrapped in ``~~``
            strikethrough + a ``✅ COMPLETE`` token. Idempotent (a row already
            carrying the token is skipped). The returned dict carries
            ``roadmap_struck`` (True iff a row was newly struck this call;
            always False on the bug/fixed path and when no ROADMAP.md exists).

        Completion-coherence gate (Phase 9 WU-1): when PHASES.md exists, BEFORE
        any write the function makes PHASES.md coherent the way the AlgoBooth
        ``check-docs-consistency.ts`` checker requires a Complete SPEC to be —
        (a) AUTO-FLIPS every phase with >=1 checkbox, zero unchecked, and a
        present non-Complete/non-Superseded ``**Status:**`` line to ``Complete``
        (in place; only that line changes), then (b) REFUSES with ZERO writes
        (no receipt, no status flips, no sentinel deletions) when any phase
        would remain incoherent — any unchecked box in a non-Superseded phase
        (verification rows INCLUDED at completion time) or any present
        non-Complete/non-Superseded status with no flip signal. The refusal
        message names each offending phase. Phases with no Status line are
        ignored; PHASES.md absent → gate is a no-op. The returned dict carries an
        extra ``flipped_phases`` key (list of the headings auto-flipped; ``[]``
        when none).

    ``__mark_fixed__``
        Same as ``__mark_complete__`` (including the completion-coherence gate
        and ``flipped_phases`` key) but the receipt file is FIXED.md (kind:
        fixed) and SPEC.md status is flipped to ``Fixed``.  Idempotent on
        existing FIXED.md with kind=="fixed".
    """
    # --- C3 cycle-containment at the LIBRARY boundary (integrity backstop) ---
    # refuse_if_cycle_active was historically invoked ONLY by the lazy-state.py /
    # bug-state.py `--apply-pseudo` CLI wrappers (immediately before this call).
    # That left a direct-import side-door: a dispatched cycle subagent (whose
    # process never inherits the orchestrator's `export LAZY_ORCHESTRATOR=1`) can
    # `import lazy_core` and call `apply_pseudo("__mark_complete__", ...)` in-process,
    # bypassing the CLI-only guard entirely — self-authoring COMPLETED.md + the
    # SPEC/PHASES Complete flip and pushing to main. That is exactly how a
    # first-time-login mcp-test subagent rogue-completed a feature on partial
    # evidence (hardening round, 2026-07). Guarding HERE — the sole author of every
    # scripted completion write — closes the hole no matter the caller:
    #   * The two CLI wrappers already export LAZY_ORCHESTRATOR=1 for the real
    #     orchestrator, so refuse_if_cycle_active returns silently for them
    #     (priority 1 immunity); the extra call is a harmless idempotent no-op.
    #   * A subagent CLI call was already refused at the wrapper; now a subagent
    #     DIRECT library call is refused here too (priority 2/3: LAZY_CYCLE_SUBAGENT
    #     or a present cycle marker → exit 3, zero side effects — refuse_if_cycle_active
    #     runs BEFORE any default resolution or filesystem work below).
    # Immunity honors the SAME LAZY_ORCHESTRATOR=1 signal used by every other
    # guarded op, so orchestrator behavior is byte-unchanged. In-process test
    # callers run with no marker and no subagent env → the guard is a silent no-op.
    refuse_if_cycle_active("apply_pseudo")

    # Resolve defaults for optional keyword arguments.
    if date is None:
        date = datetime.date.today().isoformat()
    if feature_id is None:
        feature_id = spec_path.name

    # Helper: build a minimal refused result without writing anything.
    def _refused(msg: str) -> dict:
        return {
            "name": name,
            "ok": False,
            "refused": msg,
            "wrote": [],
            "deleted": [],
            "noop": False,
        }

    # Helper: build a noop result.
    def _noop() -> dict:
        return {
            "name": name,
            "ok": True,
            "refused": None,
            "wrote": [],
            "deleted": [],
            "noop": True,
        }

    # Helper: build an ok result with specific wrote/deleted lists.
    def _ok(wrote: list[str], deleted: list[str] | None = None) -> dict:
        return {
            "name": name,
            "ok": True,
            "refused": None,
            "wrote": wrote,
            "deleted": deleted or [],
            "noop": False,
        }

    # ---------------------------------------------------------------------------
    # Dispatch
    # ---------------------------------------------------------------------------

    if name == "__grant_skip_no_mcp_surface__":
        # Structural MCP-skip auto-grant (lazy-cycle-containment follow-up).
        # Eliminates the wasted /mcp-test Opus dispatch for a `**MCP runtime:**
        # not-required` feature in a repo that has NO app surface at all
        # (no src-tauri/, no package.json) — there is provably nothing to boot
        # and nothing to probe. Writes SKIP_MCP_TEST.md inline so the next probe
        # routes straight to __write_validated_from_skip__ (no subagent).
        #
        # Defense in depth — refuse unless BOTH structural conditions hold, so
        # this can never auto-waive a feature that actually has an MCP surface.
        # The grant carries granted_by: pipeline-structural, which
        # skip_waiver_refusal RE-VERIFIES against the same predicate downstream.
        if not repo_has_no_app_surface(repo_root):
            return _refused(
                "repo has an app surface (src-tauri/ or package.json present) — "
                "a structural MCP-skip grant is valid ONLY in a repo with no "
                "MCP-reachable surface; route to /mcp-test instead"
            )
        if not phases_mcp_runtime_not_required(spec_path):
            return _refused(
                "PHASES.md does not declare `**MCP runtime:** not-required` — a "
                "structural MCP-skip grant requires the plan to route the feature "
                "as not-required first"
            )
        skip_path = spec_path / "SKIP_MCP_TEST.md"
        existing_skip = parse_sentinel(skip_path)
        # Idempotency: a skip sentinel already on disk → noop (never clobber a
        # richer operator / mcp-test grant).
        if skip_path.exists() and existing_skip is not None and existing_skip.get(
            "kind"
        ) == "skip-mcp-test":
            return _noop()
        head = _current_head(repo_root)
        commit_line = f"validated_commit: {head}\n" if head else ""
        content = (
            "---\n"
            "kind: skip-mcp-test\n"
            f"feature_id: {feature_id}\n"
            "reason: repo has no MCP-reachable surface (no src-tauri/, no "
            "package.json) — nothing to boot, nothing to probe; the MCP gate is "
            "structurally vacuous.\n"
            "alternative_validation: per-phase quality gates ran during "
            "/execute-plan (tests + lint green on each plan part before commit); "
            "this repo has no Tauri app or dev server to validate against.\n"
            f"date: {date}\n"
            "skipped_by: pipeline\n"
            "granted_by: pipeline-structural\n"
            "spec_class: standalone — no app integration (no Tauri/MCP surface "
            "in repo)\n"
            f"{commit_line}"
            "---\n"
            "\n"
            "# MCP Test Skip — structural (no app surface)\n"
            "\n"
            "Granted inline by the state machine: this repo contains no "
            "`src-tauri/` and no `package.json`, so there is no MCP HTTP server / "
            "dev runtime to drive any MCP tool against. The `**MCP runtime:** "
            "not-required` PHASES declaration is re-verified structurally here, so "
            "no /mcp-test subagent is dispatched. `skip_waiver_refusal()` re-checks "
            "the same structural predicate before this waiver can validate — an app "
            "repo (src-tauri/ or package.json present) would be refused.\n"
        )
        _atomic_write(skip_path, content)
        return _ok(["SKIP_MCP_TEST.md"])

    if name == "__write_validated_from_skip__":
        # Gate: SKIP_MCP_TEST.md must be present and parseable.
        skip_path = spec_path / "SKIP_MCP_TEST.md"
        skip_meta = parse_sentinel(skip_path)
        if not skip_path.exists() or skip_meta is None:
            return _refused("SKIP_MCP_TEST.md absent")
        # Provenance gate — the SAME skip_waiver_refusal() helper compute_state
        # consults in lazy-state.py / bug-state.py Step 9: a pipeline-self-
        # granted skip (and a pipeline-authored skip that simply OMITS
        # granted_by, and an mcp-test grant missing its spec_class citation)
        # must NOT vacuously validate. repo_root is passed so a
        # granted_by: pipeline-structural waiver re-verifies the no-app-surface
        # predicate.
        _waiver_refusal = skip_waiver_refusal(skip_meta, repo_root)
        if _waiver_refusal:
            return _refused(f"SKIP_MCP_TEST.md {_waiver_refusal}")
        # Idempotency: if VALIDATED.md already exists as kind=validated → noop.
        validated_path = spec_path / "VALIDATED.md"
        existing = parse_sentinel(validated_path)
        if existing is not None and existing.get("kind") == "validated":
            return _noop()
        # Write VALIDATED.md per sentinel-frontmatter.md schema.
        content = (
            "---\n"
            "kind: validated\n"
            f"feature_id: {feature_id}\n"
            f"date: {date}\n"
            "mcp_scenarios: []\n"
            "result: all-passing\n"
            "---\n"
            "\n"
            "# Validated\n"
            "\n"
            "Validated from SKIP_MCP_TEST.md — MCP test was explicitly skipped "
            "per the skip sentinel; validation recorded by apply_pseudo.\n"
        )
        _atomic_write(validated_path, content)
        return _ok(["VALIDATED.md"])

    elif name == "__write_validated_from_results__":
        # Script-executed VALIDATED.md derivation (2026-06-11 hardening): this
        # was the LAST pseudo-skill the orchestrator hand-wrote, bypassing all
        # integrity gates — a hand-authored VALIDATED.md could mint a passing
        # certification from a failing or stale results file. The gates below
        # make the derivation refuse instead.
        #
        # Gate ORDER (load-bearing — mirrors __mark_complete__'s ordering rule):
        #   1. Evidence gate (presence + kind + scenarios) — BEFORE the noop,
        #      exactly as __mark_complete__'s evidence-kind gate precedes its
        #      receipt-noop: a content-less or mis-kinded results file is a
        #      malformation to surface, not a state to noop over.
        #   2. VALIDATED.md noop (idempotent) — BEFORE the result-literal and
        #      freshness backstops, so re-running against an already-validated
        #      dir never re-refuses (the Phase-9/11 receipt-noop rule).
        #   3. Result-literal + count gate — the frontmatter must show a
        #      genuinely passing run: result == "all-passing" (the canonical
        #      passing literal per sentinel-frontmatter.md; failing runs carry
        #      "partial") AND pass_count == total_count as integers.
        #   4. Freshness backstop — validated_commit (the sha anchor the
        #      /mcp-test producers record) must match repo_root's current
        #      HEAD; stale results must not mint a fresh VALIDATED.md.
        #      Legacy files without the field (and non-git roots) are allowed
        #      with a warning, mirroring the state scripts' Step-9 leniency.
        results_path = spec_path / "MCP_TEST_RESULTS.md"
        results_meta = parse_sentinel(results_path)
        if results_meta is None:
            return _refused(
                "MCP_TEST_RESULTS.md absent — run /mcp-test to produce a "
                "results file before deriving VALIDATED.md"
            )
        if results_meta.get("kind") != "mcp-test-results":
            return _refused(
                "MCP_TEST_RESULTS.md exists but lacks 'kind: mcp-test-results' "
                f"frontmatter (parsed kind: {results_meta.get('kind')!r}) — "
                "refusing to derive VALIDATED.md from an unrecognized file"
            )
        if not isinstance(results_meta.get("scenarios"), list):
            return _refused(
                "MCP_TEST_RESULTS.md is missing its scenarios: list — "
                "cannot derive mcp_scenarios for VALIDATED.md"
            )
        scenarios = results_meta["scenarios"]

        # Idempotency: if VALIDATED.md already exists as kind=validated → noop.
        # Runs BEFORE the result-literal/freshness backstops (see ORDER above).
        validated_path = spec_path / "VALIDATED.md"
        existing = parse_sentinel(validated_path)
        if existing is not None and existing.get("kind") == "validated":
            return _noop()

        # Result-literal gate: only the canonical passing literal mints a
        # VALIDATED.md. The refusal names expected vs found so the orchestrator
        # can't guess-loop. (Real results files use "all-passing" / "partial";
        # one legacy file carries "pass" — deliberately NOT accepted, the
        # schema's passing literal is "all-passing".)
        #
        # Gap-1 observation-gap scoped-validated disposition
        # (harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1):
        # a SECOND accepted route, strictly ADDITIVE to the all-passing path. A
        # feature whose every MCP-DRIVEABLE assertion passed but whose remaining
        # surfaces are SPEC-locked observation gaps (no MCP control-API tool exists
        # to drive them end-to-end; locked to the unit/WDIO test tier per
        # docs/features/mcp-testing/SPEC.md) honestly carries `result: partial`.
        # The pre-fix binary all-passing/refuse gate looped /mcp-test forever for
        # that shape (the only escape was an operator hand-editing the literal — a
        # manual bypass, not a sanctioned disposition). This is SPEC-CONSISTENT:
        # building MCP UI drivers for these surfaces would contradict
        # mcp-testing/SPEC.md's locked unit/WDIO test-tier decision, so "accept the
        # documented observation-gap exemption" is the correct disposition, not a
        # missing test.
        #
        # The promotion is gated NARROWLY — a `result: partial` promotes ONLY when
        # BOTH hold: (a) every entry in `observation_gap_exemptions` carries a
        # non-empty `spec_class` provenance string referencing the untestable class
        # (mirroring the SKIP_MCP_TEST.md `spec_class`-required discipline — the
        # citation is what distinguishes a verified assessment from a convenience
        # skip), AND (b) the MCP-driveable scope is fully passing
        # (pass_count == total_count, enforced by the count cross-check below). A
        # `partial` with NO exemptions, with a provenance-less exemption, or with a
        # genuine MCP-scope failure (pass_count < total_count) falls through to the
        # EXISTING refusal — the genuine-failure refusal is NOT relaxed.
        result_literal = results_meta.get("result")
        observation_gap_exemptions = results_meta.get("observation_gap_exemptions")
        # Shared predicate (observation_gap_promotable) — the SINGLE home for the
        # scoped observation-gap partial rule, mirrored across this apply gate,
        # the completion-integrity gate, and the Step-9 routing so they cannot
        # diverge. This is HALF the AND: the count cross-check below
        # (pass_count == total_count) is the other half and refuses a genuine
        # MCP-scope failure on its own.
        observation_gap_promotion = observation_gap_promotable(results_meta)
        if result_literal != "all-passing" and not observation_gap_promotion:
            return _refused(
                f"MCP_TEST_RESULTS.md result is {result_literal!r} — expected "
                "'all-passing' (the canonical passing literal); a non-passing "
                "run must not mint VALIDATED.md. Re-run /mcp-test until all "
                "scenarios pass, or route the failure (BLOCKED/add-phase). "
                "(An observation-gap promotion requires a populated "
                "observation_gap_exemptions list whose every entry carries a "
                "spec_class provenance AND a fully-passing MCP-driveable scope.)"
            )

        # Count cross-check: the literal alone is not trusted — pass_count must
        # equal total_count, both present as integers. YAML booleans are ints
        # in Python (True == 1) but are NOT counts → rejected; digit strings
        # (quoted YAML) are coerced, matching validation_escalation's tolerance.
        def _coerce_count(raw):
            if isinstance(raw, bool):
                return None
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str) and raw.strip().isdigit():
                return int(raw.strip())
            return None

        raw_pass = results_meta.get("pass_count")
        raw_total = results_meta.get("total_count")
        pass_count = _coerce_count(raw_pass)
        total_count = _coerce_count(raw_total)
        if pass_count is None or total_count is None:
            return _refused(
                "MCP_TEST_RESULTS.md pass_count/total_count missing or "
                f"malformed (pass_count: {raw_pass!r}, total_count: "
                f"{raw_total!r}) — expected both as integers; the counts are "
                "the cross-check behind the result literal"
            )
        if pass_count != total_count:
            return _refused(
                f"MCP_TEST_RESULTS.md pass_count ({pass_count}) != total_count "
                f"({total_count}) — expected pass_count == total_count for a "
                "passing run; a partial pass must not mint VALIDATED.md"
            )

        # Freshness backstop: the results' validated_commit sha anchor must
        # match the target repo's current HEAD. Legacy files without the field
        # are allowed with a warning (the schema requires it going forward);
        # a non-git repo_root (HEAD unresolvable) also warns rather than
        # refusing, mirroring the state scripts' permissive Step-9 skip.
        warnings: list[str] = []
        recorded_commit = results_meta.get("validated_commit")
        # Presence-based (not truthiness): an unquoted all-zeros sha YAML-parses
        # as int 0 (falsy) — that file RECORDED a commit and must hit the
        # freshness gate, not silently downgrade to the legacy-absent path.
        if recorded_commit is not None:
            head = _current_head(repo_root)
            if head is None:
                warnings.append(
                    f"could not resolve HEAD for {repo_root} — "
                    "validated_commit freshness UNVERIFIED"
                )
            elif str(recorded_commit) != head:
                # Drift detected. Route through the SHARED commit_drift_verdict
                # helper (the same docs-only carve-out evaluate_completion_evidence
                # uses) so this apply gate cannot diverge from the Step-9 routing.
                # WHY this is not a gate-weakening: an /mcp-test cycle that obeys
                # its clean-tree contract MUST commit MCP_TEST_RESULTS.md, and
                # that commit advances HEAD exactly one past the validated_commit
                # it recorded — so a PURE DOCS-ONLY (*.md) one-commit drift is
                # STRUCTURALLY UNAVOIDABLE and strict equality is unsatisfiable
                # (the 2026-06-23 re-verify DEADLOCK — hardening-log Round 36).
                # Docs-only drift → accept-and-mint with a warning. Any non-.md
                # (source/script/config) drift STILL refuses (genuine TOCTOU: the
                # validated code is not the code being promoted).
                drift = commit_drift_verdict(repo_root, recorded_commit, head)
                if drift["verdict"] == "docs-only":
                    warnings.append(
                        f"validated_commit {recorded_commit} != HEAD {head} but "
                        "the drift is docs-only (*.md) — accepting (the "
                        "MCP_TEST_RESULTS.md commit itself is the expected "
                        "one-commit docs-only lag; no source/script/config drift)"
                    )
                else:
                    # non-docs-drift OR unresolvable → refuse-and-revalidate.
                    detail = (
                        f"source/script/config drift "
                        f"({', '.join(drift['non_docs'][:5])})"
                        if drift["verdict"] == "non-docs-drift"
                        else "the diff could not be resolved"
                    )
                    return _refused(
                        f"MCP_TEST_RESULTS.md is stale: validated_commit "
                        f"{recorded_commit} does not match current HEAD {head} "
                        f"with {detail} — stale results must not mint a fresh "
                        "VALIDATED.md; re-run /mcp-test against the current code"
                    )
        else:
            warnings.append(
                "MCP_TEST_RESULTS.md has no validated_commit field (legacy) — "
                "freshness UNVERIFIED; new results files MUST record `git "
                "rev-parse HEAD` per sentinel-frontmatter.md"
            )

        # Emit mcp_scenarios with yaml.safe_dump so that scenario strings
        # containing ":", ",", or "]" are properly quoted and round-trip
        # through parse_sentinel back to the original Python list unchanged.
        # yaml.safe_dump with default_flow_style=True produces a compact
        # flow-sequence like ['audio: no dropout', 'load, stress'].
        # .strip() removes the trailing newline that safe_dump appends.
        scenarios_inline = yaml.safe_dump(scenarios, default_flow_style=True).strip()
        # Carry the results' sha anchor into VALIDATED.md's optional
        # validated_commit field (sentinel-frontmatter.md documents it as the
        # SAME freshness anchor) so downstream consumers keep the match
        # between certification and the exact code it ran against.
        commit_line = (
            f"validated_commit: {recorded_commit}\n"
            if recorded_commit is not None else ""
        )
        # Gap-1: carry the observation-gap exemptions forward onto the receipt so
        # the SCOPED nature of the validation is auditable — a scoped-validated
        # VALIDATED.md must NOT impersonate a clean all-passing certification that
        # hides the untestable surfaces. The receipt's `result:` records
        # `validated-modulo-observation-gaps` (vs `all-passing`) and embeds the
        # exemptions block (round-tripped through yaml.safe_dump so spec_class
        # strings containing ':' / ',' quote correctly and parse_sentinel reads
        # them back unchanged).
        if observation_gap_promotion:
            exemptions_block = yaml.safe_dump(
                observation_gap_exemptions, default_flow_style=False
            ).strip()
            # Indent the multi-line block under the `observation_gap_exemptions:`
            # key so it is valid YAML frontmatter.
            exemptions_indented = "\n".join(
                "  " + ln if ln else ln for ln in exemptions_block.splitlines()
            )
            result_field = "validated-modulo-observation-gaps"
            exemptions_line = f"observation_gap_exemptions:\n{exemptions_indented}\n"
            body_note = (
                "Derived from MCP_TEST_RESULTS.md by the "
                "__write_validated_from_results__ gate (apply_pseudo): "
                "SCOPED-validated — every MCP-driveable assertion passed "
                f"({pass_count}/{total_count}), and the remaining surfaces are "
                f"documented observation-gap exemptions "
                f"({len(observation_gap_exemptions)}) verified against "
                "docs/features/mcp-testing/SPEC.md's unit/WDIO test tier. Building "
                "MCP UI drivers for these surfaces would contradict that "
                "SPEC-locked decision, so this is the SPEC-consistent disposition.\n"
            )
        else:
            result_field = "all-passing"
            exemptions_line = ""
            body_note = (
                "Derived from MCP_TEST_RESULTS.md by the "
                "__write_validated_from_results__ gate (apply_pseudo): result "
                f"all-passing, {pass_count}/{total_count} scenarios passing.\n"
            )
        content = (
            "---\n"
            "kind: validated\n"
            f"feature_id: {feature_id}\n"
            f"date: {date}\n"
            f"mcp_scenarios: {scenarios_inline}\n"
            f"result: {result_field}\n"
            f"{exemptions_line}"
            f"{commit_line}"
            "---\n"
            "\n"
            "# Validated\n"
            "\n"
            f"{body_note}"
        )
        _atomic_write(validated_path, content)
        result = _ok(["VALIDATED.md"])
        if warnings:
            # Surface in BOTH channels: the JSON result (for the orchestrator,
            # like flipped_phases) and stderr (for a human watching the run).
            result["warnings"] = warnings
            for w in warnings:
                sys.stderr.write(f"WARNING: {w}\n")
        return result

    elif name == "__write_deferred_non_cloud__":
        # No gate input — this write is always permitted.
        deferred_path = spec_path / "DEFERRED_NON_CLOUD.md"
        # Idempotency: file already exists → noop.
        if deferred_path.exists():
            return _noop()
        step = deferred_step if deferred_step is not None else 8
        resolved_reason = reason if reason is not None else "deferred to workstation (no Tauri/MCP in cloud)"
        content = (
            "---\n"
            "kind: deferred-non-cloud\n"
            f"feature_id: {feature_id}\n"
            f"deferred_step: {step}\n"
            f"reason: {resolved_reason}\n"
            "deferred_by: lazy-cloud\n"
            f"date: {date}\n"
            "---\n"
            "\n"
            "# Deferred Non-Cloud\n"
            "\n"
            "This feature step requires a local Tauri/MCP environment and has been "
            "deferred to the workstation for completion.\n"
        )
        _atomic_write(deferred_path, content)
        return _ok(["DEFERRED_NON_CLOUD.md"])

    elif name == "__flip_plan_complete_cloud_saturated__":
        # Resolve the target plan file.
        if plan_path is not None:
            target_plan = plan_path
        else:
            # find_implementation_plans returns only non-Complete plans.
            # We need exactly one; zero or multiple → refused.
            plans_dir = spec_path / "plans"
            if not plans_dir.exists():
                return _refused(
                    "no plan_path given and plans/ directory not found under spec_path"
                )
            non_complete = find_implementation_plans(spec_path)
            if len(non_complete) == 0:
                return _refused(
                    "no plan_path given and no non-Complete implementation plans found"
                )
            if len(non_complete) > 1:
                return _refused(
                    f"no plan_path given and {len(non_complete)} non-Complete plans found "
                    f"— provide --plan to disambiguate"
                )
            target_plan = non_complete[0]
        # Use _parse_plan_frontmatter to inspect the status without touching the
        # body — this lets us decide noop/refuse before doing any textual rewrite.
        fm = _parse_plan_frontmatter(target_plan)
        if fm is None:
            # File could not be read at all.
            return _refused("plan file could not be read")

        # Locate the YAML frontmatter fence span in the raw text so the textual
        # rewrite is scoped to the frontmatter block only.  A body line that
        # happens to start with "status: ..." must not be altered.
        raw = target_plan.read_text(encoding="utf-8")
        lines = raw.splitlines(keepends=True)

        # Locate the opening "---" fence (first non-blank line).
        fence_open: int | None = None
        for idx, line in enumerate(lines):
            if line.strip():
                if line.strip() == "---":
                    fence_open = idx
                break
        if fence_open is None:
            # File has no valid frontmatter block — refuse; do not touch the body.
            return _refused("plan file has no valid YAML frontmatter block (no opening ---)")

        # Locate the closing "---" fence.
        fence_close: int | None = None
        for idx in range(fence_open + 1, len(lines)):
            if lines[idx].strip() == "---":
                fence_close = idx
                break
        if fence_close is None:
            return _refused("plan file has no valid YAML frontmatter block (missing closing ---)")

        # Check for a ``status:`` key inside the frontmatter span.
        # fm is {} when there is no frontmatter; a dict when frontmatter parsed OK.
        # _parse_plan_frontmatter returns {} for a no-frontmatter file, but we
        # already ruled that out above.  If the parsed dict has no "status" key
        # the plan is malformed — refuse rather than silently inserting one.
        if "status" not in (fm or {}):
            return _refused("plan frontmatter has no status: field")

        current_status = (fm or {}).get("status", "")
        if str(current_status).strip() == "Complete":
            # Already Complete → noop (idempotent).
            return _noop()

        # Find the FIRST ``status:`` line within the frontmatter span and rewrite
        # only that line.  Every other byte — both frontmatter and body — is
        # left unchanged.
        status_re = re.compile(r"^(status:\s*\S.*)$")
        new_lines = list(lines)
        replaced = False
        for idx in range(fence_open + 1, fence_close):
            if status_re.match(lines[idx]):
                # Preserve the original line ending (splitlines(keepends=True)).
                original_ending = ""
                if lines[idx].endswith("\r\n"):
                    original_ending = "\r\n"
                elif lines[idx].endswith("\n"):
                    original_ending = "\n"
                elif lines[idx].endswith("\r"):
                    original_ending = "\r"
                new_lines[idx] = "status: Complete" + original_ending
                replaced = True
                break  # only the first occurrence

        if not replaced:
            # status key was in parsed YAML but no matching line found in the
            # fence span — this is a parse/text inconsistency; refuse safely.
            return _refused(
                "plan frontmatter parsed a status: value but no status: line found "
                "in the frontmatter text span — refusing to rewrite"
            )

        new_raw = "".join(new_lines)
        _atomic_write(target_plan, new_raw)
        # Report the plan path relative to repo_root when possible, else just name.
        try:
            rel = str(target_plan.relative_to(repo_root))
        except ValueError:
            rel = target_plan.name
        return _ok([rel])

    elif name in ("__mark_complete__", "__mark_fixed__"):
        # Determine whether this is a complete or fixed operation.
        is_fixed = name == "__mark_fixed__"
        receipt_filename = "FIXED.md" if is_fixed else "COMPLETED.md"
        receipt_kind = "fixed" if is_fixed else "completed"
        status_value = "Fixed" if is_fixed else "Complete"

        # Gate: validation evidence must be present AND carry the correct
        # sentinel kind. parse_sentinel returns {} (which is `not None`) for a
        # file with NO frontmatter, so a bare existence-plus-parse check would
        # let a content-less `touch VALIDATED.md` satisfy the gate and mint a
        # provenance: gated receipt. Require kind: validated (VALIDATED.md) /
        # kind: skip-mcp-test (SKIP_MCP_TEST.md) — consistent with the
        # idempotency check below that already requires kind == receipt_kind.
        validated_path = spec_path / "VALIDATED.md"
        skip_path = spec_path / "SKIP_MCP_TEST.md"
        validated_meta = parse_sentinel(validated_path)
        has_validated = (
            validated_meta is not None
            and validated_meta.get("kind") == "validated"
        )
        skip_meta = parse_sentinel(skip_path)
        has_skip = (
            skip_meta is not None
            and skip_meta.get("kind") == "skip-mcp-test"
        )
        if not has_validated and not has_skip:
            # Distinguish "evidence file present but malformed/content-less"
            # from "evidence absent" so the operator sees exactly why the gate
            # refused (and what kind: field the file must carry).
            malformed: list[str] = []
            if validated_meta is not None:
                malformed.append(
                    "VALIDATED.md exists but lacks 'kind: validated' "
                    f"frontmatter (parsed kind: {validated_meta.get('kind')!r})"
                )
            if skip_meta is not None:
                malformed.append(
                    "SKIP_MCP_TEST.md exists but lacks 'kind: skip-mcp-test' "
                    f"frontmatter (parsed kind: {skip_meta.get('kind')!r})"
                )
            if malformed:
                return _refused(
                    "validation evidence rejected — " + "; ".join(malformed)
                )
            return _refused(
                "no validation evidence (VALIDATED.md/SKIP_MCP_TEST.md) present "
                "to fold into receipt"
            )

        # Idempotency / crash-recovery audit
        # (mark-complete-partial-apply-noop-unrecoverable). The OLD check noop'd
        # on receipt-existence ALONE — but the receipt is the FIRST
        # externally-observable post-condition written, so a crash between the
        # receipt write and the SPEC status flip left a receipt-present +
        # `Status: In-progress` dir that the receipt-only noop could NEVER
        # repair: the state machine re-routed to __mark_complete__ every probe,
        # zero writes, unrecoverable loop.
        #
        # Now: receipt present → AUDIT every completion post-condition
        # (_completion_postconditions_missing). ALL satisfied → noop (genuinely
        # done — preserves the re-completing-never-re-refuses rule; this still
        # runs BEFORE the retro-staleness / provisional / coherence gates below,
        # exactly where the noop sat). ANY missing → RESUME: skip the gates +
        # receipt write + intervention capture (steps 1–4) and re-apply only the
        # idempotent tail (steps 5–10) to converge — mirroring archive_fixed's
        # in-file resume-not-noop posture. The tail steps are each individually
        # idempotent (count=1 status sub, exists-guarded deletes, no-op
        # trims/strikes), so re-running them is safe.
        receipt_path = spec_path / receipt_filename
        existing_receipt = parse_sentinel(receipt_path)
        receipt_present = (
            existing_receipt is not None
            and existing_receipt.get("kind") == receipt_kind
        )
        resuming = False
        if receipt_present:
            missing_postconditions = _completion_postconditions_missing(
                spec_path, repo_root, feature_id, status_value, is_fixed
            )
            if not missing_postconditions:
                # Genuinely done — carry resumed=False so the key is consistently
                # present on every __mark_complete__/__mark_fixed__ return.
                done = _noop()
                done["resumed"] = False
                return done
            resuming = True
            _diag(
                f"apply_pseudo {name}: receipt present but PARTIAL apply detected "
                f"(missing: {', '.join(missing_postconditions)}) — resuming the "
                "idempotent completion tail (steps 5–10)"
            )

        # --- Retro-staleness backstop (Phase 11 WU-5d + WU-5e) ---
        # Mechanical second key behind the state scripts' Step-8 staleness
        # routing (WU-5c lazy-state, WU-5e bug-state): when RETRO_DONE.md
        # recorded fewer phase sections than PHASES.md carries NOW, corrective
        # phases landed after the retro concluded — the retro graded work it
        # never saw finished, so completion must refuse until a fresh retro
        # round runs. ZERO writes: this check sits BEFORE the coherence gate's
        # auto-flip writes, and AFTER the receipt-noop above (matching the
        # Phase-9 ordering rule — re-completing an already-receipted dir never
        # re-refuses). Covers BOTH __mark_complete__ AND __mark_fixed__: the
        # original WU-5 scoping assumed bugs have no retro step, but
        # bug-state.py has its own Step 8 (retro-feature) and bug dirs carry
        # the identical RETRO_DONE.md + PHASES.md shape, so the bug pipeline
        # needs the same backstop. Missing field / missing PHASES.md →
        # retro_staleness returns None (grandfathered, pre-Phase-11 behavior).
        # Skipped on a RESUME: the receipt already exists, so this gate passed
        # pre-receipt on the crashed run — re-refusing here would trade a silent
        # loop for a wrong halt.
        _staleness = None if resuming else retro_staleness(spec_path)
        if _staleness is not None:
            _now_count, _retro_count = _staleness
            return _refused(
                f"retro is stale: {_now_count} phases now vs "
                f"{_retro_count} at retro — route a retro round before "
                "completion"
            )

        # --- Provisional-ratification backstop (park-provisional-acceptance,
        # SPEC D6 layer c — the load-bearing one). A feature/bug carrying an
        # unratified NEEDS_INPUT_PROVISIONAL.md was auto-accepted on a
        # recommendation under --park-provisional and the operator has not yet
        # ratified (or redirected) that choice. Completion MUST refuse with
        # ZERO writes until the sentinel is neutralized by the ratification
        # affordance — a provisionally-decided item can never silently
        # complete. Sits AFTER the receipt-noop (re-completing an
        # already-receipted dir never re-refuses) and BEFORE any auto-tick
        # write, matching the retro-staleness ordering rule above.
        if not resuming and (spec_path / PROVISIONAL_SENTINEL).exists():
            return _refused(
                f"unratified provisional decision(s) — {PROVISIONAL_SENTINEL} "
                "present; ratify or redirect via the provisional-ratification "
                "affordance before completion"
            )

        # --- anti-overfit-design-gate D3 ship seam (STATE-lane SEAM-DEFERRED
        # diff, PHASES.md Phase 3 Implementation Notes) — the completion-gate
        # half of the harness-change design gate. Re-derives whether this
        # item's shipped commits touch a committed control surface
        # (docs/gate/control-surfaces.json); a scoped item with a missing,
        # failing, or unsigned-gate-weakening GATE_VERDICT.md refuses with
        # ZERO writes. Out-of-scope / no manifest present -> no-op (in_scope:
        # False), so this is inert everywhere the manifest doesn't exist —
        # see gate_verdict_ok's own docstring for the honesty rail (this
        # feature is itself unratified/structurally-provisional; deleting the
        # manifest reverts this seam cleanly with zero code changes).
        if not resuming:
            _gv = gate_verdict_ok(spec_path, repo_root)
            if not _gv["ok"]:
                return _refused(
                    f"harness-change design gate: {_gv['reason']} — author/"
                    "repair GATE_VERDICT.md (see "
                    "_components/harness-change-gate.md) before completion"
                )

        # --- Evidence-gated auto-tick of certified verification rows ---
        # (completion-coherence-gate-reconciliation Phase 3). BEFORE the
        # coherence gate's residual-incoherence check, consult the on-disk
        # /mcp-test evidence (evaluate_completion_evidence). When that verdict
        # AUTHORIZES (exempt-and-tick / warn-exempt) and the kill-switch is OFF,
        # rewrite the remaining unchecked verification-marked rows to ``- [x]``
        # (autotick_verification_rows) FIRST, so the coherence re-check below
        # then sees ZERO unchecked verification rows and proceeds. A genuine
        # unchecked *implementation* row (no marker) is NOT touched by the
        # rewrite, so the coherence gate still refuses naming its phase — evidence,
        # not the checkbox, is the source of truth.
        #
        # Order (load-bearing): tick → re-check → write receipt. The receipt's
        # ``auto_ticked_rows`` records how many rows the gate mutated.
        #
        # Kill-switch (LAZY_STRICT_EVIDENCE_GATE / LAZY_DISABLE_AUTOTICK): when
        # truthy, the auto-tick is skipped entirely → the coherence gate falls
        # back to the legacy strict path (verification rows INCLUDED in
        # refusals), restoring byte-identical pre-feature behavior with no code
        # revert.
        auto_ticked_rows = 0
        strict_gate = _evidence_gate_killed()
        phases_md_path = spec_path / "PHASES.md"
        if not resuming and phases_md_path.exists() and not strict_gate:
            verdict = evaluate_completion_evidence(spec_path, repo_root)
            if verdict["verdict"] in ("exempt-and-tick", "warn-exempt"):
                tick_res = autotick_verification_rows(
                    phases_md_path,
                    verdict.get("validated_commit"),
                    verdict.get("pass_count") or 0,
                )
                # A cardinality-lock abort (ok: False) leaves the file
                # byte-unchanged; the coherence gate below then refuses on the
                # still-unchecked rows (the over-tick guard surfaces at the live
                # gate, exactly as the Phase-1/2 contract requires).
                if tick_res.get("ok"):
                    auto_ticked_rows = tick_res.get("ticked_count", 0)

        # --- Completion-coherence gate (Phase 9 WU-1) ---
        # Before minting the receipt and flipping the top-level Status, make
        # PHASES.md coherent the way AlgoBooth's check-docs-consistency.ts
        # requires a Complete SPEC to be: every phase Complete/Superseded with no
        # unchecked boxes. We (a) AUTO-FLIP all-ticked non-terminal phases to
        # Complete (deterministic, mirrors the checker's all-checked-but-not-
        # complete rule) and (b) REFUSE with ZERO writes when any phase would
        # remain incoherent after that flip (unchecked boxes incl. verification
        # rows NOT auto-ticked above, or a present non-Complete/non-Superseded
        # status with no flip signal). When PHASES.md is absent the gate is a
        # no-op (preserves the pre-Phase-9 behavior). ``flipped_phases`` records
        # the headings flipped.
        flipped_phases: list[str] = []
        if not resuming and phases_md_path.exists():
            # Re-read: the auto-tick above may have rewritten the file.
            phases_text = phases_md_path.read_text(encoding="utf-8")
            parsed_phases = parse_phases(phases_text)
            to_flip, refusals = _phase_completion_plan(parsed_phases)
            if refusals:
                # Residual incoherence → refuse with no filesystem writes at all
                # (no receipt, no status flips, no sentinel deletions). Name each
                # offending phase so the orchestrator can route a corrective
                # coherence cycle (per the Phase 9 refusal contract).
                #
                # ACTIONABLE advisory (harden 2026-07): split the blocking
                # unchecked rows into un-migrated verification-shim rows (clear via
                # canonical-marker migration — IF the verification actually ran)
                # vs genuine incomplete deliverables, so the orchestrator/operator
                # can tell a marker migration from real work. Diagnostic only — the
                # refusal decision is unchanged.
                cls = classify_blocking_unchecked_rows(phases_text)
                advisory = ""
                if cls["shim"] or cls["genuine"]:
                    advisory = (
                        f" — of the blocking unchecked row(s), {len(cls['shim'])} "
                        f"are un-migrated verification-shim rows (under a "
                        f"Runtime-Verification subsection WITHOUT the canonical "
                        f"{docmodel._VERIFICATION_ONLY_MARKER} marker) and "
                        f"{len(cls['genuine'])} are genuine incomplete "
                        f"deliverable(s). Migrating a shim row to the canonical "
                        f"marker lets the gate auto-tick it — but ONLY when its "
                        f"verification ACTUALLY ran; a row that could not run on "
                        f"this host must be deferred, not migrated (per-row "
                        f"host-deferral is an open design question)."
                    )
                    if cls["shim"]:
                        advisory += " Shim rows: " + " | ".join(cls["shim"])
                    if cls["genuine"]:
                        # completion-gate-refusal-opacity Fix Scope §2: print the
                        # genuine excerpts (not just the count) — previously
                        # collected at classify_blocking_unchecked_rows() above
                        # and discarded here.
                        advisory += " Genuine rows: " + " | ".join(cls["genuine"])
                return _refused(
                    f"PHASES.md is incoherent for completion — "
                    f"{len(refusals)} phase(s) block the receipt: "
                    + "; ".join(refusals)
                    + advisory
                )
            if to_flip:
                # Apply the auto-flips IN PLACE: rewrite ONLY the first
                # ``**Status:**`` line inside each to-be-flipped phase's section,
                # leaving every other byte (including line endings) untouched.
                flip_headings = {ph["heading"] for ph in to_flip}
                src_lines = phases_text.splitlines(keepends=True)
                out_lines: list[str] = []
                in_phase_to_flip = False
                status_flipped_this_phase = False
                in_fence = False
                for raw in src_lines:
                    stripped = raw.strip()
                    if stripped.startswith("```"):
                        in_fence = not in_fence
                        out_lines.append(raw)
                        continue
                    if not in_fence and _PHASE_HEADING_RE.match(raw):
                        # Entering a new phase section — decide if it's a flip target.
                        in_phase_to_flip = stripped in flip_headings
                        status_flipped_this_phase = False
                        out_lines.append(raw)
                        continue
                    if (
                        not in_fence
                        and in_phase_to_flip
                        and not status_flipped_this_phase
                        and _BOLD_STATUS_RE.match(stripped)
                    ):
                        # Flip ONLY this line's value to Complete; preserve the
                        # original line ending so byte-stability holds elsewhere.
                        ending = ""
                        if raw.endswith("\r\n"):
                            ending = "\r\n"
                        elif raw.endswith("\n"):
                            ending = "\n"
                        elif raw.endswith("\r"):
                            ending = "\r"
                        out_lines.append("**Status:** Complete" + ending)
                        status_flipped_this_phase = True
                        continue
                    out_lines.append(raw)
                _atomic_write(phases_md_path, "".join(out_lines))
                flipped_phases = [ph["heading"] for ph in to_flip]

        # --- (a) Fold evidence ---
        validated_via = "mcp" if has_validated else "skip-mcp-test"

        # Optionally copy pass_count / total_count from MCP_TEST_RESULTS.md.
        mcp_pass_count: int | None = None
        mcp_total_count: int | None = None
        results_path = spec_path / "MCP_TEST_RESULTS.md"
        results_meta = parse_sentinel(results_path)
        if results_meta:
            raw_pass = results_meta.get("pass_count")
            raw_total = results_meta.get("total_count")
            if isinstance(raw_pass, int):
                mcp_pass_count = raw_pass
            if isinstance(raw_total, int):
                mcp_total_count = raw_total

        # Write the receipt (SKIPPED on a RESUME — the receipt already exists and
        # re-writing it would clobber its original provenance / completed_commit /
        # auto_ticked_rows). The idempotent tail below re-applies steps 5–10 only.
        wrote: list[str] = []
        if not resuming:
            body_note = (
                f"Feature {feature_id} marked {status_value.lower()} via "
                f"apply_pseudo on {date}. Validated via: {validated_via}."
            )

            # Write the receipt using the existing helper.
            # code-doc-provenance-linkage Phase 1 (D4): anchor the receipt to the
            # HEAD at flip time. write_completed_receipt has always supported the
            # field; this call site simply never passed it. A non-git repo_root
            # resolves None → the field is omitted (legacy byte-shape preserved).
            write_completed_receipt(
                receipt_path,
                feature_id,
                date,
                provenance="gated",
                kind=receipt_kind,
                completed_commit=_current_head(repo_root),
                validated_via=validated_via,
                mcp_pass_count=mcp_pass_count,
                mcp_total_count=mcp_total_count,
                auto_ticked_rows=auto_ticked_rows,
                body_note=body_note,
            )
            wrote = [receipt_filename]

        # --- Intervention capture (intervention-efficacy-tracking D1-A) ---
        # AFTER the receipt write (the receipt is the completion's core; the
        # record is additive) and BEHIND the receipt-noop guard above (a
        # re-completion never re-captures). Eligibility (D2-A): the repo's
        # top-level `"interventions": true` queue flag OR a present
        # `## Intervention Hypothesis` SPEC block — otherwise this branch is
        # byte-inert (no keys, no file; every non-opted-in repo unchanged).
        # FAIL-OPEN: any capture error degrades to a `warnings` entry — the
        # completion stands; capture can never fail a completion.
        # SKIPPED on a RESUME: the record is written once at the original
        # completion (guarded by its own record-exists noop anyway); a resume
        # re-applies only the idempotent tail, never re-captures.
        intervention_result: dict | None = None
        intervention_warnings: list[str] = []
        try:
            _spec_md_path = spec_path / "SPEC.md"
            _hyp_present = False
            if not resuming and _spec_md_path.exists():
                _hyp_present = parse_intervention_hypothesis(
                    _spec_md_path.read_text(encoding="utf-8")
                ) is not None
            if not resuming and (_interventions_queue_flag(repo_root) or _hyp_present):
                intervention_result = record_intervention(
                    repo_root,
                    feature_id,
                    pipeline="bug" if is_fixed else "feature",
                    spec_path=spec_path,
                    date=date,
                    provenance="gated",
                )
        except Exception as exc:  # noqa: BLE001 — capture is fail-open
            intervention_warnings.append(
                f"intervention capture failed ({exc}) — the completion "
                f"stands; record docs/{_INTERVENTIONS_DIRNAME}/"
                f"{feature_id}.md was not written (re-capture manually via "
                f"--record-intervention)"
            )

        # --- (b) Flip status lines in SPEC.md and PHASES.md ---
        status_line_re = re.compile(r"^\*\*Status:\*\*.*$", re.MULTILINE)

        spec_md_path = spec_path / "SPEC.md"
        if spec_md_path.exists():
            spec_text = spec_md_path.read_text(encoding="utf-8")
            # Replace the first **Status:** line only.
            new_spec_text = status_line_re.sub(
                f"**Status:** {status_value}", spec_text, count=1
            )
            if new_spec_text != spec_text:
                _atomic_write(spec_md_path, new_spec_text)
                wrote.append("SPEC.md")

        phases_md_path = spec_path / "PHASES.md"
        if phases_md_path.exists():
            phases_text = phases_md_path.read_text(encoding="utf-8")
            new_phases_text = status_line_re.sub(
                f"**Status:** {status_value}", phases_text, count=1
            )
            if new_phases_text != phases_text:
                _atomic_write(phases_md_path, new_phases_text)
                wrote.append("PHASES.md")

        # --- (c) Delete cleanup sentinels ---
        # Delete VALIDATED.md, RETRO_DONE.md, DEFERRED_NON_CLOUD.md if present.
        # KEEP: SKIP_MCP_TEST.md, MCP_TEST_RESULTS.md, the receipt file itself.
        deleted: list[str] = []
        for cleanup_name in ("VALIDATED.md", "RETRO_DONE.md", "DEFERRED_NON_CLOUD.md"):
            cleanup_path = spec_path / cleanup_name
            if cleanup_path.exists():
                cleanup_path.unlink()
                deleted.append(cleanup_name)

        # --- (d) Trim the completed feature's entry from the feature queue ---
        # Symmetric to the BUG pipeline, whose ``archive_fixed`` (step 6) removes
        # the fixed bug from ``docs/bugs/queue.json``. The feature pipeline has no
        # archive step — a completed feature stays in place and only its SPEC
        # status flips — so WITHOUT this trim the feature's queue.json entry
        # lingers forever. AlgoBooth's check-docs-consistency.ts ``queue.no-completed``
        # rule then HARD-ERRORS on every feature completion (the queue is the
        # active-work list; a Complete/Superseded entry is pure noise). Match on
        # ``spec_dir`` (== this dir's name) OR ``id`` (== feature_id), mirroring
        # the bug trim's match keys. Idempotent: only rewrites when an entry was
        # actually removed (a re-run after the receipt-noop above never reaches
        # here, and a queue already trimmed is a no-write pass).
        #
        # ONLY the feature (complete) path trims here — the bug (fixed) path's
        # queue lives at docs/bugs/queue.json and is trimmed by archive_fixed,
        # so trimming it here too would be a no-op at best and a double-author at
        # worst. Gate on ``not is_fixed``.
        #
        # Malformed-queue policy: unlike archive_fixed (which refuses with a
        # PARTIAL-STATE diagnostic because its move already happened and the
        # consumer commits), the receipt + status flips here are the completion's
        # core and are already on disk. Refusing post-write would mis-report the
        # completion as failed. So a malformed queue.json degrades to a
        # non-fatal ``warnings`` entry — the completion stands; the operator is
        # told the queue could not be auto-trimmed and must be fixed by hand
        # (the lingering entry will surface as the same queue.no-completed error
        # this trim exists to prevent, so the signal is preserved either way).
        queue_trimmed = False
        queue_warnings: list[str] = []
        if not is_fixed:
            queue_path = repo_root / "docs" / "features" / "queue.json"
            if queue_path.exists():
                try:
                    qdata = json.loads(queue_path.read_text(encoding="utf-8"))
                    qitems = qdata.get("queue", [])
                    if isinstance(qitems, list):
                        # WU-3 (unified-pipeline-orchestrator P5): match by the
                        # RESOLVED spec_dir, not just the basename. The queue
                        # entry's stored ``spec_dir`` can be a path-form value
                        # (e.g. "docs/features/foo-followups") that does NOT
                        # equal the dir basename (``spec_path.name``). The legacy
                        # basename-only match MISSED those entries, leaving a
                        # ``-followups`` feature lingering and tripping AlgoBooth's
                        # ``queue.no-completed`` consistency error. We now resolve
                        # BOTH the completing dir and each entry's spec_dir
                        # (against repo_root) and compare the canonical paths,
                        # keeping the basename + id matches as additional
                        # (backward-compatible) keys.
                        resolved_spec = _resolve_under_repo(repo_root, spec_path)

                        def _entry_matches(e: dict) -> bool:
                            sd = e.get("spec_dir")
                            if sd == spec_path.name or e.get("id") == feature_id:
                                return True
                            if isinstance(sd, str) and sd:
                                if _resolve_under_repo(repo_root, sd) == resolved_spec:
                                    return True
                            return False

                        kept = [
                            e for e in qitems
                            if not (isinstance(e, dict) and _entry_matches(e))
                        ]
                        if len(kept) != len(qitems):
                            qdata["queue"] = kept
                            _atomic_write(
                                queue_path, json.dumps(qdata, indent=2) + "\n"
                            )
                            queue_trimmed = True
                    else:
                        queue_warnings.append(
                            "docs/features/queue.json 'queue' field is not an "
                            "array — could not auto-trim the completed entry"
                        )
                except (json.JSONDecodeError, OSError) as exc:
                    queue_warnings.append(
                        f"docs/features/queue.json could not be auto-trimmed "
                        f"({exc}) — fix it by hand to clear the queue.no-completed "
                        "error"
                    )

        # --- (e) Strike the completed feature's ROADMAP row ---
        # WU-3 (unified-pipeline-orchestrator P5): the ROADMAP strikethrough was
        # previously an orchestrator-inline step (the "one remaining orchestrator
        # step" after __mark_complete__). Moving it INTO apply_pseudo makes the
        # completion a single deterministic author for SPEC/PHASES/queue/ROADMAP.
        # Only the feature (complete) path strikes (bugs have no feature ROADMAP).
        # Idempotent: a row already struck (already ~~wrapped~~ or carrying a
        # COMPLETE token) is left untouched, so a re-run is a no-write pass — and
        # the whole branch sits BEHIND the receipt-noop guard above, so a noop
        # re-entry never reaches here.
        roadmap_struck = False
        if not is_fixed:
            roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
            if roadmap_path.exists():
                try:
                    struck = _strike_roadmap_row(
                        roadmap_path, repo_root, spec_path, feature_id
                    )
                    if struck:
                        wrote.append("ROADMAP.md")
                        roadmap_struck = True
                except OSError as exc:
                    queue_warnings.append(
                        f"docs/features/ROADMAP.md could not be auto-struck "
                        f"({exc}) — strike the completed row by hand"
                    )

        # --- (f) Provenance ledger (code-doc-provenance-linkage Phase 2) ---
        # AFTER the receipt write + queue trim + ROADMAP strike (the
        # completion's core is already durable), distill the item into
        # IMPLEMENTED.md + merge its touched-file rows into the committed
        # reverse index — via the ONE producer (write_provenance, D1-B).
        # Derivation (D4): recorded commit brackets primary; message-grep as
        # the explicitly-marked fallback (legacy items / cross-machine gaps).
        # FAILURE CONTAINMENT: any provenance failure degrades to a
        # ``warnings[]`` entry (the malformed-queue-trim policy) — completion
        # is NEVER blocked by its own bookkeeping.
        provenance_written = False
        try:
            derived = derive_touched_from_brackets(repo_root, feature_id)
            prov_derivation = "commit-brackets"
            if derived is None:
                derived = derive_touched_from_grep(repo_root, feature_id)
                prov_derivation = "message-grep"
            counts_part = (
                f" ({mcp_pass_count}/{mcp_total_count})"
                if mcp_pass_count is not None and mcp_total_count is not None
                else ""
            )
            prov_validated_line = (
                f"Validated via: {validated_via}{counts_part}. "
                f"Receipt: {receipt_filename} (provenance: gated)."
            )
            prov_result = write_provenance(
                repo_root, spec_path, feature_id,
                "bug" if is_fixed else "feature",
                derived["commits"], derived["files"],
                provenance="pipeline-gated",
                derivation=prov_derivation,
                date=date,
                validated_line=prov_validated_line,
            )
            if prov_result.get("ok"):
                provenance_written = True
                wrote.extend(prov_result.get("wrote", []))
            else:
                queue_warnings.append(
                    "provenance ledger could not be written "
                    f"({prov_result.get('refused')}) — the completion stands; "
                    "re-link via --link-provenance"
                )
        except Exception as exc:  # noqa: BLE001 — bookkeeping never blocks
            queue_warnings.append(
                f"provenance ledger could not be written ({exc}) — the "
                "completion stands; re-link via --link-provenance"
            )

        # Attach the Phase 9 WU-1 ``flipped_phases`` key (the per-phase headings
        # the completion-coherence gate auto-flipped to Complete this call).
        # Empty list when nothing needed flipping; documented in the docstring.
        result = _ok(wrote, deleted)
        # mark-complete-partial-apply-noop-unrecoverable: True iff this call was a
        # crash-window RESUME (receipt already present, a post-condition was
        # missing, and the idempotent tail was re-applied to converge). False on
        # the normal completion path and on a genuinely-done noop (which returns
        # earlier). The re-applied artifacts are surfaced via wrote/deleted.
        result["resumed"] = resuming
        result["flipped_phases"] = flipped_phases
        # auto_ticked_rows: count of verification rows the evidence-gated gate
        # auto-ticked this call (completion-coherence-gate-reconciliation Phase
        # 3). 0 when the kill-switch is set, the verdict did not authorize, or
        # there were no unchecked verification rows. Orchestrator-visible,
        # matching the flipped_phases surfacing pattern.
        result["auto_ticked_rows"] = auto_ticked_rows
        # WU: feature-queue trim — True iff a queue.json entry was removed this
        # call (always False for the bug/fixed path, whose trim lives in
        # archive_fixed). Callers may JSON-dump unconditionally.
        result["queue_trimmed"] = queue_trimmed
        # WU-3 (unified-pipeline-orchestrator P5): True iff a ROADMAP row was
        # struck this call (always False for the bug/fixed path and when no
        # ROADMAP.md exists or the row was already struck).
        result["roadmap_struck"] = roadmap_struck
        # code-doc-provenance-linkage Phase 2: True iff the IMPLEMENTED.md
        # distillate + index rows were written this call (False on a contained
        # provenance failure — see the warnings[] entry it leaves behind).
        result["provenance_written"] = provenance_written
        # intervention-efficacy-tracking D1-A: attach the capture keys ONLY
        # when capture fired (eligibility met) — a non-opted-in repo's result
        # stays byte-identical to pre-feature. `intervention_recorded` is True
        # for a fresh record AND for an existing-record noop (the record
        # exists either way — e.g. a prior D9 backfill).
        if intervention_result is not None:
            result["intervention_recorded"] = bool(
                intervention_result.get("recorded")
                or intervention_result.get("noop")
            )
            result["intervention_record"] = intervention_result.get("path")
        all_warnings = intervention_warnings + queue_warnings
        if all_warnings:
            existing_warnings = result.get("warnings") or []
            result["warnings"] = existing_warnings + all_warnings
            for w in all_warnings:
                print(f"WARNING: {w}", file=sys.stderr)
        return result

    else:
        # Unknown pseudo-skill name — never crash, always refuse gracefully.
        return _refused(f"unknown pseudo-skill: {name}")


# ---------------------------------------------------------------------------
# detect_noncanonical_blocker — read-time stray-blocker detector
#   (noncanonical-blocker-filename-invisible-to-state-machine). Single writer of
#   the detection logic; lazy-state.py / bug-state.py Step 3 only CALL it.
# ---------------------------------------------------------------------------

def detect_noncanonical_blocker(spec_dir: Path) -> Path | None:
    """Return the first blocker-shaped *stray* file in ``spec_dir``, or None.

    A *stray* is a mis-named blocker sentinel that the literal ``BLOCKED.md``
    Step-3 check is blind to — e.g. ``BLOCKED_2026-06-09-foo.md`` or a
    lowercase ``blocked.md``. Such a file silently loops the pipeline (the
    state machine re-routes straight back into the same wall). This detector
    surfaces it so the caller can emit a distinct ``blocked-misnamed`` terminal.

    A directory entry's basename ``name`` is a stray iff ALL hold:
      * ``name.upper().startswith("BLOCKED")`` — blocker-shaped (case-insensitive).
      * ``name.lower().endswith(".md")``       — markdown sentinel.
      * ``name != "BLOCKED.md"``                — NOT the exact canonical name
        (canonical is owned by the caller's literal check; precise, case-sensitive).
      * ``"_RESOLVED_" not in name``            — NOT an already-neutralized
        blocker. Reuses ``neutralize_sentinel``'s literal ``_RESOLVED_`` guard
        so a renamed ``BLOCKED_RESOLVED_<date>.md`` never re-halts.

    Entries are scanned in ``sorted(spec_dir.iterdir())`` order so the "first
    offending path" is deterministic across platforms — the byte-pinned
    ``--test`` baselines depend on it.

    Robustness: returns None (never raises) when ``spec_dir`` does not exist or
    holds no stray.
    """
    if not spec_dir.exists():
        return None
    try:
        entries = sorted(spec_dir.iterdir())
    except OSError:
        return None
    # Canonical precedence (belt-and-suspenders): when the EXACT canonical
    # BLOCKED.md is present, the caller's literal Step-3 check owns the halt —
    # never surface a stray alongside it (would double-emit / shadow the
    # canonical `blocked` terminal). The state machines also wire this detector
    # AFTER their canonical check, so this is a second line of defense.
    # The check is case-SENSITIVE against the listed basenames (NOT
    # ``(spec_dir / "BLOCKED.md").exists()``, which is case-insensitive on
    # Windows/macOS and would wrongly treat a lowercase ``blocked.md`` stray as
    # the canonical file).
    names = [e.name for e in entries]
    if "BLOCKED.md" in names:
        return None
    for entry in entries:
        name = entry.name
        if (
            name.upper().startswith("BLOCKED")
            and name.lower().endswith(".md")
            and name != "BLOCKED.md"
            and "_RESOLVED_" not in name
        ):
            return entry
    return None


# ---------------------------------------------------------------------------
# neutralize_sentinel — WU-3: rename a resolved sentinel to the canonical
#   *_RESOLVED_<date> form (collision-safe, git-mv-aware).
# ---------------------------------------------------------------------------

def neutralize_sentinel(path: Path, date: str | None = None) -> dict:
    """Rename a sentinel file to its canonical RESOLVED form.

    Given a sentinel like NEEDS_INPUT.md or BLOCKED.md that has been acted on,
    this function renames it to ``<stem>_RESOLVED_<date><ext>`` in the same
    directory. The rename is collision-safe: if the canonical target already
    exists, a numeric suffix is appended (``_2``, ``_3``, …) until a free name
    is found. The original file is never clobbered.

    When the file lives inside a git repo and is tracked, ``git mv`` is used to
    preserve history. If ``git mv`` returns non-zero (plain temp dir, untracked
    file, or git unavailable) the function falls back to a plain filesystem
    rename via ``Path.rename()``.

    Args:
        path: Absolute (or relative) path to the sentinel file to neutralize.
        date: ISO date string (YYYY-MM-DD) to embed in the resolved name.
              Defaults to today's date (``datetime.date.today().isoformat()``).

    Returns:
        A dict with keys:
          ok              – True on success, False on any refusal/error.
          renamed_from    – Basename of the source file (str), or None on refusal.
          renamed_to      – Basename of the target file (str), or None on refusal.
          refused         – Human-readable refusal reason (str), or None on success.
          collision_suffix – Integer n (≥2) when a collision suffix was required,
                             or None when the base target name was free.
    """
    # Default to today when no date is provided by the caller.
    if date is None:
        date = datetime.date.today().isoformat()

    # Guard 1: source must exist — never create anything for a missing path.
    if not path.exists():
        return {
            "ok": False,
            "renamed_from": None,
            "renamed_to": None,
            "refused": "sentinel not found",
            "collision_suffix": None,
        }

    # Guard 2: refuse to double-neutralize a file that already contains _RESOLVED_.
    # The literal substring check is intentional — it catches any variant like
    # NEEDS_INPUT_RESOLVED_2026-06-09.md regardless of the date.
    if "_RESOLVED_" in path.name:
        return {
            "ok": False,
            "renamed_from": None,
            "renamed_to": None,
            "refused": "already neutralized",
            "collision_suffix": None,
        }

    # Compute the canonical base target name: <stem>_RESOLVED_<date><ext>.
    # path.stem is the filename without its final extension; path.suffix is the
    # extension including the leading dot (e.g. ".md").
    stem = path.stem
    ext = path.suffix
    base_target_name = f"{stem}_RESOLVED_{date}{ext}"
    target = path.parent / base_target_name

    # Collision-safe name selection: if the base target exists, increment a
    # numeric suffix starting at 2 until a free slot is found. Never clobber.
    collision_suffix: int | None = None
    if target.exists():
        n = 2
        while True:
            candidate_name = f"{stem}_RESOLVED_{date}_{n}{ext}"
            candidate = path.parent / candidate_name
            if not candidate.exists():
                target = candidate
                collision_suffix = n
                break
            n += 1

    # Attempt rename via git mv to preserve history when the file is tracked.
    # ``git -C <dir> mv <src_basename> <dst_basename>`` keeps the operation
    # within the directory; we pass basenames so git doesn't need absolute paths.
    # Modelled after _current_head in lazy-state.py (capture_output, text, timeout,
    # OSError/SubprocessError guard).
    renamed = False
    try:
        r = subprocess.run(
            ["git", "-C", str(path.parent), "mv", path.name, target.name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            # git mv succeeded: source is gone, target is present.
            renamed = True
    except (OSError, subprocess.SubprocessError):
        # git unavailable or some other OS-level failure — fall through to
        # the plain filesystem move below.
        pass

    if not renamed:
        # Fallback: plain filesystem rename. Use Path.rename() which is atomic
        # on POSIX and behaves correctly on Windows for in-directory renames.
        path.rename(target)

    return {
        "ok": True,
        "renamed_from": path.name,
        "renamed_to": target.name,
        "refused": None,
        "collision_suffix": collision_suffix,
    }


# ---------------------------------------------------------------------------
# park-provisional-acceptance — provisional acceptance of low-divergence
# product-class NEEDS_INPUT.md decisions (`--park-provisional`).
# ---------------------------------------------------------------------------

def _split_decision_context_h3s(body: str) -> list[str]:
    """Return the H3 subsection texts under the ``## Decision Context`` H2.

    Empty list when the H2 is absent. Each returned string starts at its
    ``### `` heading line and runs to the next H3/H2 boundary. Pure text
    helper shared by provisional_eligibility / provisionalize_sentinel.
    """
    m = re.search(r"^## Decision Context\s*$", body, re.MULTILINE)
    if not m:
        return []
    # Section runs to the next H2 (or EOF).
    tail = body[m.end():]
    next_h2 = re.search(r"^## \S", tail, re.MULTILINE)
    section = tail[: next_h2.start()] if next_h2 else tail
    parts = re.split(r"(?=^### )", section, flags=re.MULTILINE)
    return [p for p in parts if p.startswith("### ")]


def _extract_recommended_label(h3_text: str) -> str | None:
    """Extract the recommended option label from one Decision-Context H3.

    Primary source: the first ``- **<label> (Recommended)**`` options bullet
    (the schema mandates recommendation-first with the ``(Recommended)``
    suffix inside or right after the bold label). Fallback: the
    ``**Recommendation:** <label> — justification`` line's leading label.
    Returns None when neither yields a non-empty label (caller refuses).
    """
    # Options bullet carrying the (Recommended) marker — bold label with the
    # marker either inside the bold (`**X (Recommended)**`) or right after.
    for bm in re.finditer(r"^\s*-\s*\*\*(.+?)\*\*", h3_text, re.MULTILINE):
        label = bm.group(1).strip()
        rest = h3_text[bm.end(): bm.end() + 40]
        if "(Recommended)" in label or rest.lstrip().startswith("(Recommended)"):
            return label.replace("(Recommended)", "").strip() or None
    # Fallback: the Recommendation line — label runs to the em/double dash.
    rm = re.search(r"\*\*Recommendation:\*\*\s*(.+)", h3_text)
    if rm:
        line = rm.group(1).strip()
        label = re.split(r"\s+—\s+|\s+--\s+|\s+-\s+", line, maxsplit=1)[0]
        label = label.strip().strip("*").strip()
        if label:
            return label
    return None


def provisional_eligibility(sentinel_path: Path) -> tuple[bool, str]:
    """Deterministic, FAIL-CLOSED provisional-acceptance predicate (SPEC D3/D4/D8).

    Returns ``(eligible, reason)`` — ``reason`` names the first failed check
    (for the probe's ``_diag`` breadcrumb) or ``"eligible"``.

    A ``NEEDS_INPUT.md`` is provisional-eligible iff ALL of:
      - the frontmatter parses with ``kind: needs-input`` and a non-empty
        ``decisions:`` list of ≤4 entries;
      - it is NOT two-key mechanical (``class: mechanical`` AND
        ``audit_concurs: true``) — the existing flush auto-accept is the
        stronger path for those (full resolution, no ratification debt);
      - ``written_by`` is not ``completion-integrity-gate`` (integrity gaps
        are never recommendations);
      - ``stub_origin`` is absent or explicitly false (stub-origin-provisional-
        exclusion: baseline-shaping decisions from a stub-spec /spec Phase-1
        round or a /spec-bug pre-conclusion halt are never provisional);
      - the divergence two-key holds: ``divergence`` (producer, Key 1) AND
        ``audit_divergence`` (input-audit, Key 2) are BOTH in
        {isolated, contained} — absence, ``structural``, or any unknown value
        fails closed;
      - the body carries ``## Decision Context`` with one H3 per decision
        (1:1) and every H3 carries a ``**Recommendation:**`` block;
      - no ``## Resolution`` section exists yet (a mid-resolution file is
        owned by another path).

    Structurally corrupt frontmatter routes through ``parse_sentinel``'s
    ``_die`` like every other sentinel read.
    """
    if sentinel_path.name != "NEEDS_INPUT.md":
        return (False, f"not a NEEDS_INPUT.md ({sentinel_path.name})")
    meta = parse_sentinel(sentinel_path)
    if meta is None:
        return (False, "sentinel missing or without frontmatter")
    if meta.get("kind") != "needs-input":
        return (False, f"kind is {meta.get('kind')!r}, not needs-input")
    decisions = meta.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return (False, "decisions: absent or empty")
    if len(decisions) > 4:
        return (False, f"{len(decisions)} decisions exceeds the 4-decision cap")
    if str(meta.get("written_by", "")).strip() == "completion-integrity-gate":
        return (False, "written_by completion-integrity-gate — never provisional")
    # stub-origin-provisional-exclusion: decisions that shaped a baseline the
    # operator never saw (park-mode stub-spec /spec Phase-1 round, /spec-bug
    # pre-conclusion halt) are NEVER provisionally accepted, regardless of
    # divergence grades — jointly they define the item's foundation.
    # FAIL-CLOSED on malformed values: any present value that is not an
    # explicit false excludes.
    if "stub_origin" in meta:
        _so = meta.get("stub_origin")
        if not (_so is False or str(_so).strip().lower() in ("false", "no")):
            return (False, "stub_origin baseline decision — never provisional "
                           "(fail-closed)")
    if meta.get("class") == "mechanical" and meta.get("audit_concurs") is True:
        return (False, "two-key mechanical — flush auto-accept path wins (D4)")
    divergence = str(meta.get("divergence", "")).strip().lower()
    audit_divergence = str(meta.get("audit_divergence", "")).strip().lower()
    if divergence not in _PROVISIONAL_ELIGIBLE_GRADES:
        return (False, f"divergence {divergence or 'absent'!s} not in "
                       "{isolated, contained} (fail-closed)")
    if audit_divergence not in _PROVISIONAL_ELIGIBLE_GRADES:
        return (False, f"audit_divergence {audit_divergence or 'absent'!s} not in "
                       "{isolated, contained} (fail-closed)")
    try:
        text = sentinel_path.read_text(encoding="utf-8")
    except OSError as exc:
        return (False, f"unreadable sentinel: {exc}")
    if re.search(r"^## Resolution\s*$", text, re.MULTILINE):
        return (False, "already carries a ## Resolution section")
    h3s = _split_decision_context_h3s(text)
    if not h3s:
        return (False, "body missing ## Decision Context")
    if len(h3s) != len(decisions):
        return (False, f"{len(h3s)} H3 subsection(s) != {len(decisions)} "
                       "decisions (1:1 schema violation)")
    for i, h3 in enumerate(h3s):
        if "**Recommendation:**" not in h3:
            return (False, f"decision {i + 1} lacks a **Recommendation:** block")
    return (True, "eligible")


def provisionalize_sentinel(path: Path, repo_root: Path,
                            date: str | None = None) -> dict:
    """Provisionally accept a NEEDS_INPUT.md on its recommendations (SPEC D2).

    Re-validates the FULL eligibility predicate (fail-closed — the CLI action
    must never trust a stale probe), extracts each decision's recommended
    option label, appends a ``## Resolution`` block carrying
    ``resolved_by: auto-provisional`` + the HEAD ``decision_commit``, and
    renames the file to ``NEEDS_INPUT_PROVISIONAL.md`` (git-mv-aware,
    refusing — zero writes — when the target already exists).

    Returns::

        {ok, refused, choices: [{title, choice}], divergence,
         audit_divergence, decision_commit, renamed_to}
    """
    def _refuse(reason: str) -> dict:
        return {
            "ok": False, "refused": reason, "choices": [],
            "divergence": None, "audit_divergence": None,
            "decision_commit": None, "renamed_to": None,
        }

    eligible, reason = provisional_eligibility(path)
    if not eligible:
        return _refuse(reason)
    target = path.parent / PROVISIONAL_SENTINEL
    if target.exists():
        return _refuse(f"{PROVISIONAL_SENTINEL} already exists — refusing to clobber")

    meta = parse_sentinel(path) or {}
    decisions = [str(d) for d in meta.get("decisions", [])]
    text = path.read_text(encoding="utf-8")
    h3s = _split_decision_context_h3s(text)
    choices: list[dict] = []
    for i, h3 in enumerate(h3s):
        label = _extract_recommended_label(h3)
        if not label:
            return _refuse(
                f"decision {i + 1}: could not extract a recommended option "
                "label (no (Recommended) bullet and no parsable "
                "**Recommendation:** line)"
            )
        title = h3.splitlines()[0].lstrip("#").strip()
        choices.append({"title": title, "choice": label})

    # decision_commit anchors any later redirect's blast-radius diff
    # (`git diff <decision_commit>..HEAD`). Best-effort: a non-git dir (test
    # fixtures) records "unknown" rather than blocking the acceptance — the
    # sha is audit metadata, not a gate.
    decision_commit = _current_head(repo_root) or "unknown"
    if date is None:
        date = datetime.date.today().isoformat()
    divergence = str(meta.get("divergence")).strip().lower()
    audit_divergence = str(meta.get("audit_divergence")).strip().lower()

    lines = [
        "",
        "## Resolution",
        "",
        f"*Recorded on {date}. Provisionally auto-accepted on recommendation "
        "(`--park-provisional` divergence two-key). Ratify or redirect via "
        "the provisional-ratification affordance before completion.*",
        "",
        "resolved_by: auto-provisional",
        f"decision_commit: {decision_commit}",
        "",
    ]
    for i, ch in enumerate(choices, start=1):
        lines += [
            f"### {i}. {ch['title']}",
            "",
            f"**Choice:** {ch['choice']}",
            f"**Notes:** Provisionally accepted — divergence graded "
            f"{divergence} (producer) / {audit_divergence} (input-audit); "
            "pending operator ratification.",
            "",
        ]
    new_text = text.rstrip("\n") + "\n" + "\n".join(lines)
    _atomic_write(path, new_text)

    # Rename via git mv (history-preserving) with plain-rename fallback —
    # same pattern as neutralize_sentinel.
    renamed = False
    try:
        r = subprocess.run(
            ["git", "-C", str(path.parent), "mv", path.name, target.name],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            renamed = True
    except (OSError, subprocess.SubprocessError):
        pass
    if not renamed:
        path.rename(target)

    return {
        "ok": True, "refused": None, "choices": choices,
        "divergence": divergence, "audit_divergence": audit_divergence,
        "decision_commit": decision_commit, "renamed_to": target.name,
    }


# ---------------------------------------------------------------------------
# Persisted probe signature / loop detection — WU-4
# ---------------------------------------------------------------------------

def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a git
    repo / git is unavailable.

    Best-effort and never raises: a missing git binary, a non-repo path, or any
    subprocess error all map to None. update_repeat_count uses this for the
    Phase 9 WU-2 HEAD-aware streak — None on both sides (e.g. a non-git
    repo_root) preserves the pre-Phase-9 same-tuple-increments behavior.

    This mirrors lazy-state.py's own _current_head (which lazy-state keeps for
    its Step-9 MCP-results freshness gate); the duplication is deliberate — the
    two scripts are independently importable and lazy_core must not depend on a
    sibling script. Both share the same best-effort contract.
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


def update_repeat_counts(
    repo_root: Path,
    state: dict,
    *,
    signature_path: Path | None = None,
    pipeline: str = "feature",
    peek: bool = False,
) -> dict:
    """Persist the probe signatures and return BOTH consecutive-repeat counts.

    Two independent counters share ONE per-pipeline state file:

    1. ``repeat_count`` — the Phase-9 dispatch-tuple streak.
       Signature = ``(feature_id, sub_skill, sub_skill_args, current_step)``.
       HEAD-AWARE: identical tuple + a NEW HEAD since the last probe RESETS to 1
       (commits between two identical probes are forward progress, not a stall).

    2. ``step_repeat_count`` — the Phase-10 step-level oscillation counter.
       Signature = ``(feature_id, current_step)`` ONLY (no sub_skill / args).
       NO head-advance reset: its whole purpose is catching
       "productive-looking" oscillation where each spurious cycle commits a file
       (HEAD advances → the dispatch streak resets every iteration) while the
       state machine keeps returning to the SAME step. It increments whenever the
       (feature_id, current_step) pair is unchanged from the prior probe.
       It RESETS to 1 on exactly THREE paths (all "genuine forward progress",
       never a HEAD/commit reset — that immunity is the d8 design constraint):
         (a) the step signature (feature_id, current_step) CHANGES;
         (b) ORDERED-ADVANCE EXEMPTION — step signature unchanged but
             ``sub_skill_args`` advanced (a multi-part /execute-plan sequence);
         (c) RESOLUTION-AWARE RESET — the prior cycle was a needs-input
             RESOLUTION at this exact step signature (the run marker carried a
             one-shot ``last_resolution_step_key`` recorded by
             ``record_resolution_signal``).  A resolution is itself an Agent
             dispatch (it consumes a nonce, defeating the F2 hold), so without
             (c) the counter would survive a legitimately-resolved blocker.
             One-shot + signal-gated: fires once across the resolution, never on
             a missing/legacy/foreign-repo marker.

    The persisted JSON shape is
    ``{"signature": [4], "count": int, "head": str|None,
       "step_signature": [2], "step_count": int, "consume_count": int}``. Legacy
    files (Phase-9 shape, no ``step_*`` keys) are honored: ``step_count`` starts
    at 1 and the new keys are added on the next write — mirroring the ``head``-field
    migration.

    ``consume_count`` (lazy-pipeline-ergonomics Phase 2 / F2, and now also F1 /
    lazy-validation-readiness) is the DOUBLE-PROBE DEBOUNCE oracle and is
    MARKER-GATED: it is written ONLY when a run marker is present
    (``read_run_marker()`` is non-None), recording the registry's consumed-entry
    count (``consumed_emission_count``) at the time of the probe.  On the next
    probe, when (a) a marker is present, (b) the relevant signature is unchanged,
    AND (c) the prior file recorded a ``consume_count`` that equals the current
    consumed-count → NO dispatch landed between the two probes (the guard consumes
    a nonce on every ALLOW), so the second probe is a RE-READ.  Both ``count``
    (F1: same-tuple same-HEAD branch) and ``step_count`` (F2) are HELD instead of
    incremented.  This stops an inspection-probe-then-dispatch-probe pair from
    inflating either counter and tripping a false LOOP DETECTED. A genuine
    oscillation still trips because
    a real dispatch (hence a consume) lands between its repeats. The key is
    legacy-tolerant exactly like ``head`` / ``step_*``: a file with no
    ``consume_count`` cannot prove a re-read, so ``step_count`` behaves as before
    (increments). When NO marker is present the key is never written and the
    debounce is inert — the no-marker path stays byte-identical (``--test``
    baselines unchanged). HEAD-blindness is preserved: the debounce keys on
    DISPATCH occurrence, never on commits — no HEAD reset is added to
    ``step_count``.

    Any missing file, OS error, or corrupt/invalid JSON is silently treated as
    «no prior» — the function never raises on a bad state file.

    ``peek`` (mirrors Phase-9 semantics): when True, compute and RETURN both
    would-be counts WITHOUT any mutation — the state file is neither created nor
    rewritten, so neither counter advances. Diagnostic / inspection probes use
    peek so only the single dispatch-bound probe advances the streaks.

    ``head`` is the repo_root's current HEAD sha (via ``_current_head``), or
    None when repo_root is not a git repo.

    Default ``signature_path`` (when None):
        feature pipeline: ``<tempdir>/lazy-state-last-<sha1_of_repo_root[:16]>.json``
        bug pipeline:     ``<tempdir>/bug-state-last-<sha1_of_repo_root[:16]>.json``
    This keeps the state file outside the repo tree — it is never committed
    and never triggers gitignore concerns. The per-``pipeline`` filename keeps
    the feature and bug resolvers from sharing one signature file (interleaved
    parallel /lazy-batch + /lazy-bug-batch probes would otherwise reset each
    other's streaks, defeating mechanical loop detection).

    Returns ``{"repeat_count": int >= 1, "step_repeat_count": int >= 1}``.
    """
    # --- Derive default path from a stable hash of the resolved repo root ----
    # The hash keeps per-repo state separate even when multiple repos live on
    # the same machine, while keeping the filename deterministic across runs.
    if signature_path is None:
        repo_hash = hashlib.sha1(
            str(repo_root.resolve()).encode("utf-8")
        ).hexdigest()[:16]
        # "feature" keeps the historical filename so existing state files
        # carry over; any other pipeline gets its own namespaced file.
        prefix = "lazy-state-last" if pipeline == "feature" else f"{pipeline}-state-last"
        signature_path = Path(tempfile.gettempdir()) / f"{prefix}-{repo_hash}.json"

    # --- Build the new signatures from the current state ---------------------
    # Dispatch tuple (Phase-9): full routing identity.
    new_sig = (
        state.get("feature_id"),
        state.get("sub_skill"),
        state.get("sub_skill_args"),
        state.get("current_step"),
    )
    # Step signature (Phase-10): feature_id + current_step ONLY. Deliberately
    # excludes sub_skill / sub_skill_args so oscillation that re-routes the SAME
    # step through different skills/args (the d8 write-plan loop) still counts.
    new_step_sig = (
        state.get("feature_id"),
        state.get("current_step"),
    )

    # --- Resolve the repo's current HEAD (None when not a git repo) ----------
    current_head = _current_head(repo_root)

    # --- Read the persisted prior signatures (fail-safe) ---------------------
    prior_count = 0
    prior_sig_list: list | None = None
    # Sentinel distinguishing "no `head` key at all" (legacy file) from an
    # explicit ``"head": null`` (a non-git repo wrote it under the new shape).
    _MISSING = object()
    prior_head: object = _MISSING
    prior_step_count = 0
    prior_step_sig_list: list | None = None
    # F2 debounce oracle: the consumed-emission count recorded by the prior
    # MARKED probe. _MISSING distinguishes "no consume_count key" (legacy file,
    # or an unmarked prior write) from a recorded count — only a recorded prior
    # count can prove a re-read, so a legacy/unmarked prior never debounces.
    prior_consume_count: object = _MISSING
    # Residual gap B (loop-detector-false-positives-probes-and-cross-run-state):
    # the run-marker's ``started_at`` the record was written under. _MISSING
    # distinguishes "no run_started_at key" (legacy file, or a probe taken with
    # no live marker) from a recorded run identity — only a recorded identity
    # can prove "this streak belongs to a DIFFERENT/no-longer-live run", so a
    # legacy/unmarked prior is never treated as foreign (conservative: it falls
    # through to the pre-existing same-run behavior).
    prior_run_started_at: object = _MISSING
    try:
        raw = signature_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Validate expected shape: {"signature": [4 items], "count": int, ...}.
        # ``head`` is OPTIONAL — a legacy pre-Phase-9 file has no head key.
        if (
            isinstance(data, dict)
            and isinstance(data.get("signature"), list)
            and len(data["signature"]) == 4
            and isinstance(data.get("count"), int)
        ):
            prior_sig_list = data["signature"]
            prior_count = data["count"]
            if "head" in data:
                prior_head = data["head"]
        # ``step_signature`` / ``step_count`` are OPTIONAL — a legacy pre-Phase-10
        # file has neither key. Validated INDEPENDENTLY of the dispatch tuple so
        # a partially-upgraded file still reads what it can.
        if (
            isinstance(data, dict)
            and isinstance(data.get("step_signature"), list)
            and len(data["step_signature"]) == 2
            and isinstance(data.get("step_count"), int)
        ):
            prior_step_sig_list = data["step_signature"]
            prior_step_count = data["step_count"]
        # ``consume_count`` is OPTIONAL (F2 migration, like ``head``/``step_*``).
        # Read it INDEPENDENTLY so a partially-upgraded file still reads what it
        # can. Only an int is honored — anything else leaves the sentinel so the
        # debounce stays inert (cannot prove a re-read).
        if isinstance(data, dict) and isinstance(data.get("consume_count"), int):
            prior_consume_count = data["consume_count"]
        # ``run_started_at`` is OPTIONAL (Residual gap B migration, like
        # ``head``/``step_*``/``consume_count``) and, like ``consume_count``,
        # is written ONLY on a marked probe (mirrored below) — so a str value
        # here always means "this record was stamped under a live run".
        # Read it INDEPENDENTLY so a partially-upgraded file still reads what
        # it can.
        if isinstance(data, dict) and isinstance(data.get("run_started_at"), str):
            prior_run_started_at = data["run_started_at"]
        # If shape is wrong, treat as no-prior (counts stay 0, sig lists None).
    except (OSError, ValueError, json.JSONDecodeError):
        # File absent, unreadable, or corrupt → treat as no prior.
        pass

    # --- Resolve the F2/F1 double-probe debounce oracle (MARKER-GATED, REPO-SCOPED)
    # Moved ABOVE both count blocks so BOTH the dispatch-tuple count (Phase 9 /
    # F1) and the step-level count (Phase 10 / F2) can share this single oracle
    # read.  (Previously it sat between the two blocks; hoisting it here is the
    # only structural change required by F1 / lazy-validation-readiness.)
    #
    # When a run marker for THIS repo is present, read the registry's
    # consumed-emission count (the guard consumes one nonce per ALLOW, so this is
    # a dispatch counter).  current_consume_count stays the _MISSING sentinel
    # otherwise → the key is never written and the debounce is inert (no-marker
    # path stays byte-identical, --test baselines unchanged).  read_run_marker is
    # a read-only path (create=False) so a probe never creates the state dir as a
    # side-effect.
    #
    # REPO SCOPING (hardening-log Round 8, 2026-06-13): the marker is a SINGLE
    # global file, but the consume-count it gates (consumed_emission_count) is a
    # global registry counter shared by whatever marked run is live.  A probe for
    # repo A must NOT engage the debounce off repo B's marker — doing so
    # (a) made this very function non-hermetic to its `repo_root` argument, so the
    # step-counter unit tests went RED whenever ANY marked run was live on the
    # machine, and (b) latently let a concurrent run in another repo spuriously
    # debounce repo A's step counter (the same cross-session hazard Rounds 3 & 5
    # closed for the marker itself).  Gate the oracle on the marker's `repo_root`
    # matching the probe's resolved `repo_root`; a marker missing `repo_root`
    # (legacy/bind-pending) is treated as non-matching → debounce stays inert.
    # Residual gap A (loop-detector-false-positives-probes-and-cross-run-state):
    # count only CYCLE-class consumptions as "a dispatch landed between probes".
    # A mid-step META dispatch (hardening / recovery / coherence-recovery /
    # investigation / input-audit / …) still consumes a registry nonce, but it
    # is not a forward attempt at the step, so it must not defeat the F1/F2
    # hold. Filtering the oracle to cls="cycle" is the localized fix (D1,
    # oracle refinement over signal generalization) — a genuine same-step
    # oscillation still dispatches a CYCLE each repeat, so it still trips.
    current_consume_count: object = _MISSING
    _marker = read_run_marker()
    _marker_started_at: object = _MISSING
    if _marker is not None:
        _marker_repo = _marker.get("repo_root")
        if _marker_repo is not None and Path(_marker_repo).resolve() == repo_root.resolve():
            current_consume_count = consumed_emission_count(cls="cycle")
            _marker_started_at = _marker.get("started_at")

    # --- Residual gap B: run-lifetime scoping of streak state ----------------
    # (loop-detector-false-positives-probes-and-cross-run-state) Streak files
    # live outside the per-repo keyed state dir (an OS-tempdir file keyed only
    # on repo_root) and NOTHING previously cleared them at --run-end/--run-start
    # — a next run's first probe landing on the same (feature_id, current_step)
    # as a dead run's last probe silently INHERITS that streak (the false-loop
    # T6 warning at run open). Stamp/compare against the run marker's
    # ``started_at`` (the established run identity, already resolved above,
    # repo-scoped the same way the F1/F2 oracle is): reset to NO PRIOR only when
    # we can PROVE the persisted record belongs to a DIFFERENT, SPECIFIC run —
    # i.e. a live marker exists now AND the record carries a DIFFERENT recorded
    # run_started_at (this is exactly the crash scenario: the dead run had a
    # live marker throughout, so every one of its probes stamped its identity).
    # A record with NO run_started_at key at all (legacy/pre-migration, or a
    # write taken with no marker) is NOT treated as foreign — same legacy-
    # tolerance discipline as the head/step_*/consume_count migrations
    # elsewhere in this function: absence is never proof, so it falls through
    # to the pre-existing same-repo streak semantics (conservative — never
    # reset on ambiguous data). When no marker is live for this repo, behavior
    # is UNCHANGED (no established run identity to compare against at all).
    if _marker_started_at is not _MISSING and prior_run_started_at is not _MISSING:
        if prior_run_started_at != _marker_started_at:
            prior_sig_list = None
            prior_step_sig_list = None

    # --- Compute the dispatch-tuple count (Phase 9 WU-2 — HEAD-aware) ---------
    # JSON round-trips tuples as lists, so compare new_sig as a list.
    if prior_sig_list is None or list(new_sig) != prior_sig_list:
        # Changed signature (or no prior) — fresh streak.
        count = 1
    elif prior_head is _MISSING:
        # Legacy file (no `head` recorded) — increment for backward-compat and
        # begin recording head going forward.
        count = prior_count + 1
    elif prior_head is not None and prior_head != current_head:
        # Same tuple but commits landed between probes (HEAD advanced) — that is
        # forward progress, not a stall, so reset the streak to 1.
        count = 1
    elif (
        # F1 (lazy-validation-readiness) double-probe debounce: HOLD count (do
        # NOT increment) when this is provably a RE-READ — the dispatch tuple is
        # unchanged, the HEAD is unchanged, AND no dispatch landed between the
        # two probes.  "No dispatch" = unchanged registry consume-count, which
        # we can only assert when BOTH this probe and the prior write recorded a
        # consume-count (i.e. both were marked probes).  A legacy/unmarked prior
        # (sentinel) or an unmarked current probe (sentinel) cannot prove a
        # re-read → fall through to the normal increment.  This prevents the
        # orchestrator from reading a spurious count=2 and firing a false LOOP
        # DETECTED when an inspection probe and a dispatch probe share the same
        # tuple with no intervening dispatch.  A genuine oscillation still trips
        # because a real dispatch (hence a consume) lands between its repeats.
        current_consume_count is not _MISSING
        and prior_consume_count is not _MISSING
        and current_consume_count == prior_consume_count
    ):
        count = prior_count
    else:
        # Same tuple AND same head (or both None) — genuine consecutive repeat.
        count = prior_count + 1

    # --- Resolve prior vs current sub_skill_args for the ordered-advance exempt
    # The dispatch tuple is (feature_id, sub_skill, sub_skill_args, current_step),
    # so index 2 of the persisted ``signature`` list is the PRIOR probe's
    # sub_skill_args. We reuse that already-persisted field rather than adding a
    # new key — no extra streak state is introduced. ``_MISSING`` when there is
    # no valid prior dispatch tuple (no prior file, or a corrupt/legacy file
    # whose signature failed the 4-element validation above → prior_sig_list is
    # None). When prior args are unknowable we CANNOT prove an advance, so we
    # fall through to the existing debounce/increment (conservative: never
    # weakens the tripwire on a missing/old file).
    current_step_args = state.get("sub_skill_args")
    prior_step_args: object = _MISSING
    if prior_sig_list is not None:  # validated as a 4-element list when set
        prior_step_args = prior_sig_list[2]

    # --- Resolve the resolution-aware reset signal (symptom 3) ---------------
    # (loop-detected-false-positives-from-probe-and-reboot-churn) A needs-input
    # RESOLUTION meta-cycle is itself an Agent dispatch → it consumes a nonce, so
    # the F2 debounce below CANNOT hold the step counter across it (a dispatch
    # provably landed).  Without this branch the HEAD-blind step_count survives a
    # legitimately-resolved blocker and false-trips LOOP-DETECTED.  The resolution
    # bracket persisted ``last_resolution_step_key`` on the run marker
    # (record_resolution_signal); read it here keyed on the CURRENT step
    # signature.  Deterministic + persisted (⚖ D7), never probe-time inference.
    #
    # The signal is ONE-SHOT: it is consumed-and-cleared so the reset fires once
    # across the resolution (not on every subsequent probe — that would
    # re-introduce d8 HEAD-advance immunity for the resolved step).  In ``peek``
    # mode we must NOT mutate the marker, so we do a READ-ONLY check there and
    # leave the consume-and-clear to the real (non-peek) probe.  Marker-gated and
    # repo-scoped inside the helper; a missing/legacy/foreign marker → False, so
    # the reset can never spuriously fire.  Reached only when the step signature
    # is UNCHANGED (the "changed step → fresh streak" branch returns first).
    _resolution_reset = False
    if prior_step_sig_list is not None and list(new_step_sig) == prior_step_sig_list:
        if peek:
            _marker_peek = read_run_marker()
            if (
                _marker_peek is not None
                and _marker_peek.get("repo_root") is not None
                and Path(_marker_peek["repo_root"]).resolve() == repo_root.resolve()
                and _marker_peek.get("last_resolution_step_key") == list(new_step_sig)
            ):
                _resolution_reset = True
        else:
            _resolution_reset = _consume_resolution_signal(repo_root, new_step_sig)

    # --- Compute the step-level count (Phase 10 WU-2 — NO HEAD reset) ---------
    # Deliberately HEAD-BLIND: identical (feature_id, current_step) increments
    # regardless of intervening commits (that is the oscillation-with-commits
    # signal). Legacy files (no step keys) → start at 1 and add the keys below.
    if prior_step_sig_list is None or list(new_step_sig) != prior_step_sig_list:
        step_count = 1
    elif (
        # ORDERED-ADVANCE EXEMPTION (audio-rate-modulation false-positive fix):
        # the step signature (feature_id, current_step) is UNCHANGED but
        # ``sub_skill_args`` ADVANCED since the prior probe. That is genuine
        # ordered forward progress — e.g. a multi-part /execute-plan sequence
        # (part-1.md → part-2.md → …) that legitimately stays on the SAME
        # "Step 7a: execute plan" while marching through plan parts — so it must
        # NOT count toward the oscillation tripwire. RESET to 1.
        #
        # This is the deliberate inverse of the Phase-10 design choice that made
        # the step signature args-BLIND: that choice was to catch the d8
        # write-plan loop, where each cycle COMMITS (HEAD advances → the
        # dispatch-tuple repeat_count resets every iteration so it never trips)
        # yet routing never leaves the step AND the work target is the SAME. The
        # discriminator between the two is precisely whether sub_skill_args moved:
        #   - d8 stuck loop:        args UNCHANGED across repeats → still counts.
        #   - ordered multi-part:   args DIFFERENT each repeat   → exempt here.
        # HEAD-advance-immunity (the d8 property) is preserved: we add NO head
        # reset; we only exempt the case where the work TARGET itself advanced.
        # Guarded on a known prior (prior_step_args is not _MISSING) so a
        # missing/legacy prior can never spuriously reset the tripwire.
        prior_step_args is not _MISSING
        and current_step_args != prior_step_args
    ):
        step_count = 1
    elif _resolution_reset:
        # RESOLUTION-AWARE RESET (symptom 3 — the residual fix). The prior cycle
        # was a needs-input RESOLUTION at this exact step signature (the marker
        # carried a matching one-shot ``last_resolution_step_key``). A resolution
        # is genuine forward progress past a legitimately-resolved blocker, NOT
        # oscillation — so RESET step_count to 1 rather than letting it survive the
        # resolution dispatch's consume (which defeated the F2 hold above).
        #
        # Ordered AFTER the ordered-advance exemption and BEFORE the F2 debounce —
        # the same "genuine forward progress → reset to 1" shape and the same guard
        # discipline (fires only on a recorded/known signal; a missing/legacy/
        # foreign marker yields _resolution_reset=False). HEAD-blindness is
        # preserved: this adds NO head/commit reset (the d8 commit-masked
        # oscillation case has NO resolution signal, so it still falls through to
        # the increment below — symptom-5 design constraint intact). One-shot: the
        # signal was consumed-and-cleared in the read above, so a subsequent probe
        # with no fresh signal increments normally.
        step_count = 1
    elif (
        # F2 double-probe debounce: HOLD step_count (do NOT increment) when this
        # is provably a RE-READ — the step signature is unchanged AND no dispatch
        # landed between the two probes. "No dispatch" = an unchanged registry
        # consume-count, which we can only assert when BOTH this probe and the
        # prior write recorded one (i.e. both were marked). A legacy/unmarked
        # prior (sentinel) or an unmarked current probe (sentinel) cannot prove a
        # re-read → fall through to the normal increment. This preserves
        # HEAD-blindness (keyed on dispatch occurrence, never on commits).
        #
        # Reached only when sub_skill_args is UNCHANGED (the ordered-advance
        # branch above already handled the advanced-args case), so the debounce
        # still governs the genuine same-target re-read it was built for.
        current_consume_count is not _MISSING
        and prior_consume_count is not _MISSING
        and current_consume_count == prior_consume_count
    ):
        step_count = prior_step_count
    else:
        step_count = prior_step_count + 1

    # --- Persist the updated record (skipped entirely in peek mode) ----------
    # peek=True returns the would-be counts WITHOUT touching the state file, so
    # diagnostic probes never inflate or reset either persisted streak.
    if not peek:
        record: dict = {
            "signature": list(new_sig),
            "count": count,
            "head": current_head,
            "step_signature": list(new_step_sig),
            "step_count": step_count,
        }
        # F2: record the consume-count ONLY on a marked probe. Omitting the key
        # on the no-marker path keeps that path's persisted shape byte-identical
        # to the pre-Phase-2 record (legacy-tolerant, like the head/step_*
        # migrations). current_consume_count is the sentinel when no marker.
        if current_consume_count is not _MISSING:
            record["consume_count"] = current_consume_count
        # Residual gap B: record the LIVE run's identity ONLY on a marked
        # probe — same legacy-tolerant discipline as consume_count. Omitting
        # the key on the no-marker path keeps that path's persisted shape
        # byte-identical to before this fix.
        if _marker_started_at is not _MISSING:
            record["run_started_at"] = _marker_started_at
        _atomic_write(signature_path, json.dumps(record))

    return {"repeat_count": count, "step_repeat_count": step_count}


def update_repeat_count(
    repo_root: Path,
    state: dict,
    *,
    signature_path: Path | None = None,
    pipeline: str = "feature",
    peek: bool = False,
) -> int:
    """Backward-compatible wrapper: return ONLY the dispatch-tuple ``repeat_count``.

    Phase-10 added the step-level oscillation counter via ``update_repeat_counts``
    (which returns both counts and persists the ``step_*`` keys in the SAME state
    file). This wrapper preserves the pre-Phase-10 int return for existing callers
    that only need the dispatch streak, while still writing the step keys (so a
    later ``update_repeat_counts`` probe of the same step sees them). Kept as a
    thin delegate — there is exactly one read/write of the shared state file.

    See ``update_repeat_counts`` for the full counting + persistence contract.
    """
    return update_repeat_counts(
        repo_root,
        state,
        signature_path=signature_path,
        pipeline=pipeline,
        peek=peek,
    )["repeat_count"]


# ---------------------------------------------------------------------------
# WU-5: Single-probe payload helpers
# ---------------------------------------------------------------------------

def _git(repo_root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a git command against repo_root, capturing output. Never raises on
    non-zero exit (callers check .returncode); raises only on OS-level failure,
    which callers wrap."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def git_head_short_sha(repo_root: Path) -> str | None:
    """Return the short SHA of ``git rev-parse --short HEAD`` for ``repo_root``,
    or ``None`` on any failure (non-git tree, OS error, non-zero exit).

    Fail-open by design (feature-budget-guard-and-skip-ahead Phase 2): the budget
    guard's ``budget_guard.commit_hash`` audit field is best-effort context, never
    a gate — a degraded snapshot must not break trip evaluation.
    """
    try:
        proc = _git(repo_root, "rev-parse", "--short", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def archive_fixed(
    repo_root: Path,
    spec_path: Path,
    *,
    date: str | None = None,
) -> dict:
    """Archive a Fixed bug directory: the deterministic successor to the prose
    archive mechanics in mark-fixed-archive.md Steps 1–5.

    Why this is script-owned (2026-06-10 incident): the orchestrator performing
    these steps as prose improvised through three consecutive failures — a
    `git mv` refused because apply_pseudo's sentinel deletions were unstaged
    (tracked-but-missing files inside the dir), a transient Windows
    "Permission denied" on the directory rename, and a repo-wide `grep -r`
    crawling node_modules. Each is handled deterministically here.

    Steps (all best-effort idempotent; safe to re-run after a partial failure):
      1. Gate: FIXED.md receipt present (kind: fixed) — or SPEC ``**Status:**
         Won't-fix`` (receipt-exempt). If spec_path is already gone and the
         archive destination exists, treat as a RESUME: skip to step 5.
      2. SPEC.md evidence header lines: ensure ``**Fixed:** <date>`` and
         ``**Fix commit:** <short sha>`` after ``**Discovered:**`` (fallback:
         after ``**Status:**``), updating them if already present.
      3. ``git add -A <spec_path>`` — stages the receipt, status flips, AND the
         sentinel deletions so the index is coherent before the move (the exact
         precondition the prose flow missed).
      4. ``git mv <spec_path> docs/bugs/_archive/<bug_id>`` with retry/backoff
         (1s/2s/4s — Windows transient handle locks), then a per-file
         ``git mv`` fallback if the directory rename never succeeds. A name
         collision in _archive/ gets a ``-archived-<date>`` suffix.
      5. Repoint inbound references: ``git grep -l`` (tracked files only — never
         node_modules/target) for ``docs/bugs/<bug_id>/`` across ``*.md``,
         replacing with ``docs/bugs/_archive/<bug_id>/``.
      6. Remove the bug's entry from docs/bugs/queue.json (matched on
         ``spec_dir`` or ``id``).
      7. Stage the touched paths and commit:
         ``fix(<bug_id>): mark fixed and archive — FIXED.md receipt gated``.

    Return shape (callers may JSON-dump unconditionally)::

        {
            "name": "archive_fixed",
            "ok": bool,
            "refused": str | None,   # non-None → nothing irreversible was done,
                                     #   OR a partial-state diagnostic (see note)
            "noop": bool,            # True iff there was nothing left to do
            "archived_to": str | None,   # repo-relative destination
            "fix_commit": str | None,    # short sha recorded in SPEC.md
            "repointed": [str, ...],     # repo-relative files whose refs moved
            "queue_removed": bool,
            "fallback_used": bool,       # per-file git mv fallback engaged
            "committed": str | None,     # short sha of the archive commit
        }

    Partial-state note: a refusal AFTER the move (e.g. commit failure) names
    the completed steps so the consumer can surface an accurate BLOCKED.md;
    re-running resumes from the archive destination rather than redoing the
    move.
    """
    if date is None:
        date = datetime.date.today().isoformat()
    repo_root = repo_root.resolve()
    bug_id = spec_path.name
    result: dict[str, Any] = {
        "name": "archive_fixed",
        "ok": False,
        "refused": None,
        "noop": False,
        "archived_to": None,
        "fix_commit": None,
        "repointed": [],
        "queue_removed": False,
        "fallback_used": False,
        "committed": None,
    }

    def _refuse(msg: str) -> dict:
        result["refused"] = msg
        return result

    archive_parent = repo_root / "docs" / "bugs" / "_archive"
    dest = archive_parent / bug_id

    try:
        # --- step 1: gate / resume detection --------------------------------
        resume = False
        if not spec_path.exists():
            if dest.exists():
                # Prior run moved the directory but died before repoint/commit.
                resume = True
            else:
                return _refuse(
                    f"spec_path does not exist and no archive at "
                    f"{dest.relative_to(repo_root).as_posix()} — nothing to archive"
                )
        if not resume:
            receipt_ok = has_completion_receipt(spec_path, "FIXED.md")
            wont_fix = (spec_status(spec_path) or "").startswith("Won't-fix")
            if not receipt_ok and not wont_fix:
                return _refuse(
                    "no FIXED.md receipt (kind: fixed) and SPEC is not "
                    "Won't-fix — run `--apply-pseudo __mark_fixed__` first; "
                    "archive_fixed never writes the receipt itself"
                )

            # --- step 2: SPEC.md evidence header lines -----------------------
            # Short sha of the last work commit BEFORE the archive commit — the
            # load-bearing evidence of when the fix landed (mark-fixed-archive
            # Step 1). Skipped for Won't-fix (no receipt → no fix commit).
            if receipt_ok:
                sha_proc = _git(repo_root, "rev-parse", "--short", "HEAD")
                fix_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
                if fix_sha:
                    result["fix_commit"] = fix_sha
                    spec_md = spec_path / "SPEC.md"
                    if spec_md.exists():
                        text = spec_md.read_text(encoding="utf-8")
                        # Update-in-place when the lines already exist…
                        text = re.sub(
                            r"^\*\*Fixed:\*\*.*$", f"**Fixed:** {date}",
                            text, count=1, flags=re.MULTILINE,
                        )
                        text = re.sub(
                            r"^\*\*Fix commit:\*\*.*$", f"**Fix commit:** {fix_sha}",
                            text, count=1, flags=re.MULTILINE,
                        )
                        # …then insert any that are still missing, after
                        # **Discovered:** (canonical field order per
                        # docs/bugs/CLAUDE.md: Status → Severity → Discovered →
                        # Fixed → Fix commit), falling back to **Status:**.
                        missing = []
                        if not re.search(r"^\*\*Fixed:\*\*", text, flags=re.MULTILINE):
                            missing.append(f"**Fixed:** {date}")
                        if not re.search(r"^\*\*Fix commit:\*\*", text, flags=re.MULTILINE):
                            missing.append(f"**Fix commit:** {fix_sha}")
                        if missing:
                            anchor = re.search(
                                r"^\*\*Discovered:\*\*.*$", text, flags=re.MULTILINE
                            ) or re.search(
                                r"^\*\*Status:\*\*.*$", text, flags=re.MULTILINE
                            )
                            if anchor:
                                insert_at = anchor.end()
                                text = (
                                    text[:insert_at]
                                    + "".join("\n" + line for line in missing)
                                    + text[insert_at:]
                                )
                            else:
                                # No header block at all — append (degenerate
                                # SPEC; keep the evidence rather than dropping it).
                                text = text.rstrip("\n") + "\n\n" + "\n".join(missing) + "\n"
                        _atomic_write(spec_md, text)

            # --- step 3: stage the bug dir (deletions included) --------------
            add_proc = _git(repo_root, "add", "-A", "--", str(spec_path))
            if add_proc.returncode != 0:
                return _refuse(
                    f"git add -A {spec_path.name} failed: {add_proc.stderr.strip()}"
                )

            # --- step 4: git mv with retry + per-file fallback ---------------
            archive_parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = archive_parent / f"{bug_id}-archived-{date}"
                if dest.exists():
                    return _refuse(
                        f"archive collision: both {bug_id} and "
                        f"{dest.name} already exist under _archive/"
                    )
            mv_err = ""
            moved = False
            for attempt, delay in enumerate((0, 1, 2, 4)):
                if delay:
                    time.sleep(delay)  # transient Windows handle/lock backoff
                mv_proc = _git(repo_root, "mv", str(spec_path), str(dest))
                if mv_proc.returncode == 0:
                    moved = True
                    break
                mv_err = mv_proc.stderr.strip()
            if not moved:
                # Per-file fallback: move every tracked file individually so a
                # single locked file is isolated instead of failing the whole
                # directory rename.
                ls_proc = _git(
                    repo_root, "ls-files", "--", str(spec_path)
                )
                if ls_proc.returncode != 0:
                    return _refuse(
                        f"git mv failed after retries ({mv_err}) and ls-files "
                        f"fallback failed: {ls_proc.stderr.strip()}"
                    )
                rel_spec = spec_path.relative_to(repo_root).as_posix()
                failed_files = []
                for rel in ls_proc.stdout.splitlines():
                    rel = rel.strip()
                    if not rel:
                        continue
                    suffix = rel[len(rel_spec):].lstrip("/")
                    target = dest / suffix
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f_proc = _git(repo_root, "mv", rel, str(target))
                    if f_proc.returncode != 0:
                        failed_files.append(f"{rel}: {f_proc.stderr.strip()}")
                if failed_files:
                    return _refuse(
                        "per-file git mv fallback left files behind — "
                        "PARTIAL STATE, resolve the locks and re-run: "
                        + "; ".join(failed_files)
                    )
                result["fallback_used"] = True
                # Remove the now-empty source tree (best-effort).
                for dirpath, dirnames, filenames in os.walk(spec_path, topdown=False):
                    if not filenames and not dirnames:
                        try:
                            os.rmdir(dirpath)
                        except OSError:
                            pass
                moved = True

        result["archived_to"] = dest.relative_to(repo_root).as_posix()

        # --- step 5: repoint inbound references (tracked *.md only) ----------
        old_ref = f"docs/bugs/{bug_id}/"
        # NOTE: dest may carry the -archived-<date> suffix; repoint to the
        # actual destination, not the canonical name.
        new_ref = dest.relative_to(repo_root).as_posix() + "/"
        grep_proc = _git(repo_root, "grep", "-l", "-F", old_ref, "--", "*.md")
        # returncode 1 = no matches (fine); >1 = real error.
        if grep_proc.returncode > 1:
            return _refuse(
                f"archived to {result['archived_to']} but inbound-reference "
                f"scan failed: {grep_proc.stderr.strip()} — PARTIAL STATE, "
                "re-run to resume"
            )
        for rel in grep_proc.stdout.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            ref_path = repo_root / rel
            try:
                content = ref_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if old_ref in content:
                _atomic_write(ref_path, content.replace(old_ref, new_ref))
                result["repointed"].append(rel)

        # --- step 6: trim queue.json ------------------------------------------
        queue_path = repo_root / "docs" / "bugs" / "queue.json"
        if queue_path.exists():
            try:
                data = json.loads(queue_path.read_text(encoding="utf-8"))
                items = data.get("queue", [])
                kept = [
                    e for e in items
                    if not (
                        isinstance(e, dict)
                        and (e.get("spec_dir") == bug_id or e.get("id") == bug_id)
                    )
                ]
                if len(kept) != len(items):
                    data["queue"] = kept
                    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
                    result["queue_removed"] = True
            except (json.JSONDecodeError, AttributeError) as exc:
                return _refuse(
                    f"archived to {result['archived_to']} but queue.json is "
                    f"malformed ({exc}) — PARTIAL STATE, fix queue.json and re-run"
                )

        # --- step 7: stage + commit -------------------------------------------
        to_stage = ["docs/bugs"] + result["repointed"]
        add_proc = _git(repo_root, "add", "-A", "--", *to_stage)
        if add_proc.returncode != 0:
            return _refuse(
                f"archived to {result['archived_to']} but final staging "
                f"failed: {add_proc.stderr.strip()} — PARTIAL STATE, re-run"
            )
        diff_proc = _git(repo_root, "diff", "--cached", "--quiet")
        if diff_proc.returncode == 0:
            # Nothing staged — a re-run after a fully-completed prior pass.
            result["ok"] = True
            result["noop"] = True
            return result
        commit_proc = _git(
            repo_root, "commit", "-m",
            f"fix({bug_id}): mark fixed and archive — FIXED.md receipt gated",
        )
        if commit_proc.returncode != 0:
            return _refuse(
                f"archived to {result['archived_to']} but commit failed: "
                f"{commit_proc.stderr.strip()} — PARTIAL STATE (changes are "
                "staged), commit manually or re-run"
            )
        sha_proc = _git(repo_root, "rev-parse", "--short", "HEAD")
        result["committed"] = (
            sha_proc.stdout.strip() if sha_proc.returncode == 0 else "unknown"
        )
        result["ok"] = True
        return result
    except (OSError, subprocess.SubprocessError) as exc:
        return _refuse(f"git unavailable or I/O failure: {exc}")


def git_guard_status(repo_root: Path) -> dict:
    """Return a three-key git status snapshot for the probe payload.

    Runs three lightweight git commands against ``repo_root`` and returns a
    dict with the following keys:

    ``clean_tree`` (bool)
        True when ``git status --short`` produces no output (no staged,
        unstaged, or untracked changes).

    ``head_matches_origin`` (bool)
        True when ``git rev-parse HEAD`` equals ``git rev-parse @{u}``.
        False when the repo has no upstream configured or any git command
        fails.

    ``unpushed`` (bool)
        True when ``git rev-list --count @{u}..HEAD`` returns an integer > 0
        (local commits are ahead of the upstream tracking ref).  False on any
        git failure or when no upstream is configured.

    Error-handling contract (best-effort, mirrors verify_ledger / _current_head):
    - Each of the three checks is independent; a failure in one does not
      prevent the others from running.
    - Any ``OSError`` or ``subprocess.SubprocessError`` (including timeout)
      silently produces the safe-default value for that check.
    - When ``@{u}`` does not resolve (no upstream), both ``head_matches_origin``
      and ``unpushed`` are False; ``clean_tree`` still reflects the status
      command result if it succeeded.
    """
    # --- check 1: clean working tree -----------------------------------------
    # Mirror the subprocess style used in verify_ledger: capture_output + text
    # + explicit timeout + catch OSError/SubprocessError.
    try:
        status_result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Require a zero returncode in addition to empty stdout.  When
        # repo_root is not a git repo, `git status --short` exits 128 with
        # empty stdout — without the returncode guard that would produce a
        # false-positive clean_tree=True (contradicting the docstring contract
        # that an invalid repo → safe-dirty False, matching checks 2 and 3).
        clean_tree = (status_result.returncode == 0 and status_result.stdout.strip() == "")
    except (OSError, subprocess.SubprocessError):
        # Git unavailable or repo_root invalid — assume dirty so callers don't
        # proceed with a false-positive clean signal.
        clean_tree = False

    # --- check 2: HEAD matches upstream tracking ref -------------------------
    # Both rev-parse commands must succeed and return identical SHA strings.
    # @{u} fails with a non-zero returncode when no upstream is configured.
    try:
        head_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        upstream_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if head_result.returncode == 0 and upstream_result.returncode == 0:
            head_sha = head_result.stdout.strip()
            upstream_sha = upstream_result.stdout.strip()
            # Require both SHAs to be non-empty before comparing.
            head_matches_origin = bool(head_sha and upstream_sha and head_sha == upstream_sha)
        else:
            # @{u} can fail when no upstream is configured; treat as mismatch.
            head_matches_origin = False
    except (OSError, subprocess.SubprocessError):
        head_matches_origin = False

    # --- check 3: unpushed local commits -------------------------------------
    # rev-list --count @{u}..HEAD returns the number of commits ahead of the
    # upstream.  A non-zero integer means at least one local commit is unpushed.
    try:
        revlist_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", "@{u}..HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if revlist_result.returncode == 0:
            unpushed = int(revlist_result.stdout.strip()) > 0
        else:
            # No upstream or other git error — cannot determine ahead-count.
            unpushed = False
    except (OSError, subprocess.SubprocessError, ValueError):
        # ValueError covers int() failing on unexpected output.
        unpushed = False

    return {
        "clean_tree": clean_tree,
        "head_matches_origin": head_matches_origin,
        "unpushed": unpushed,
    }


# ---------------------------------------------------------------------------
# Phase 1 (lazy-cycle-containment, C8) — Self-edit reload discipline.
#
# When a /lazy-batch run executes *inside* claude-config it is editing the very
# harness it runs from. Most of that harness self-refreshes mid-run and needs NO
# reload — the AUTO-REFRESH BOUNDARY below. The ONLY surfaces that go stale are
# the orchestrator's own in-context governing prose: GOVERNING_FILE_SET.
#
# AUTO-REFRESH BOUNDARY (documented no-ops — MUST NOT be flagged for reload;
# they were never stale):
#   * lazy_core.py / lazy-state.py / bug-state.py — a fresh `python3` subprocess
#     runs on every probe, so an edit is live on the next probe.
#   * lazy-batch-prompts/cycle-base-prompt.md (+ addenda + loop-block.md) —
#     re-read by emit_cycle_prompt() from disk on every probe.
#   * hook .sh bodies — `bash ~/.claude/hooks/X.sh` reads the file each
#     invocation, so a body edit is live on the next tool call.
#   * downstream skill prose (SKILL.md a dispatched subagent loads) — each
#     dispatched subagent loads its skill fresh, so the edit is live next dispatch.
# These are EXCLUDED from GOVERNING_FILE_SET by construction.
#
# The governing-file set MUST stay in lockstep with the orchestrator's
# compaction re-read list (lazy-dispatch-template.md + orchestrator-voice.md +
# completeness-policy.md + the orchestrator's own SKILL.md) — the self-edit
# reload is the SAME re-read, triggered by a self-edit commit instead of a
# compaction boundary. Paths are repo-root-relative POSIX strings (the form
# `git diff --name-only` emits).
# ---------------------------------------------------------------------------
GOVERNING_FILE_SET: frozenset[str] = frozenset({
    # Orchestrator SKILLs the running orchestrator holds in-context (coupled trio).
    "user/skills/lazy-batch/SKILL.md",
    "user/skills/lazy-bug-batch/SKILL.md",
    "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
    # Components the orchestrator holds in-context (the compaction re-read list).
    "user/skills/_components/orchestrator-voice.md",
    "user/skills/_components/completeness-policy.md",
    "user/skills/_components/lazy-dispatch-template.md",
})


def self_edit_mode(repo_root: "str | Path") -> bool:
    """True iff this run is editing the harness it executes from.

    Returns True when ``~/.claude/skills``, ``~/.claude/scripts``, AND
    ``~/.claude/hooks`` ALL resolve (after ``os.path.realpath`` symlink
    resolution) to a path UNDER the run's ``git rev-parse --show-toplevel``.

    This is the semantically-correct predicate — robust to the repo being cloned
    to any path (it compares resolved real paths, NOT a brittle cwd-basename
    match). ``~`` is resolved via ``os.path.expanduser``.

    Returns False (never raises) when:
      * ``repo_root`` is not a git repo (``--show-toplevel`` fails);
      * any of the three ``~/.claude/*`` paths is missing or resolves OUTSIDE
        the toplevel;
      * any OS/subprocess error occurs.
    """
    # Resolve the run's git toplevel; non-git repo or any git failure → False.
    try:
        proc = _git(Path(repo_root), "rev-parse", "--show-toplevel", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    toplevel_raw = proc.stdout.strip()
    if not toplevel_raw:
        return False
    toplevel = os.path.realpath(toplevel_raw)

    for name in ("skills", "scripts", "hooks"):
        candidate = os.path.join(os.path.expanduser("~"), ".claude", name)
        if not os.path.exists(candidate):
            return False
        resolved = os.path.realpath(candidate)
        # Membership test on the resolved real paths: resolved must be the
        # toplevel itself or a descendant of it.
        try:
            common = os.path.commonpath([toplevel, resolved])
        except ValueError:
            # Different drives (Windows) or otherwise incomparable → not under.
            return False
        if common != toplevel:
            return False
    return True


def governing_files_touched(repo_root: "str | Path") -> list[str]:
    """Return the GOVERNING_FILE_SET members touched by the last commit.

    Intersects the last commit's changed files (``git diff --name-only HEAD~1
    HEAD``; falls back to the root-commit file list when there is no parent)
    with GOVERNING_FILE_SET. Auto-refresh surfaces never appear (they are not in
    the set). Best-effort: any git failure returns ``[]`` (the orchestrator's
    reload check then simply finds nothing to reload).
    """
    try:
        proc = _git(repo_root if isinstance(repo_root, Path) else Path(repo_root),
                    "diff", "--name-only", "HEAD~1", "HEAD", timeout=30)
        if proc.returncode != 0:
            # No parent commit (root commit): list the commit's own files.
            proc = _git(repo_root if isinstance(repo_root, Path) else Path(repo_root),
                        "show", "--name-only", "--pretty=format:", "HEAD",
                        timeout=30)
            if proc.returncode != 0:
                return []
    except (OSError, subprocess.SubprocessError):
        return []
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return sorted(changed & GOVERNING_FILE_SET)


# Per-sub_skill Step name for the FORWARD cycle_header (the T2 sibling of
# DISPATCH_STEP_NAMES, which maps META dispatch classes). Keys are the normalized
# sub_skill (leading '/' stripped, lowercased). Canonical T2 step names per
# orchestrator-voice.md; an unmapped sub_skill falls back to itself (mirroring
# DISPATCH_STEP_NAMES.get(cls, cls)); an absent sub_skill falls back to "Cycle".
SUB_SKILL_STEP_NAMES: dict[str, str] = {
    "spec":              "Spec",
    "spec-bug":          "Investigate",
    "plan-feature":      "Plan",
    "plan-bug":          "Plan",
    "spec-phases":       "Plan",
    "write-plan":        "Plan",
    "execute-plan":      "Implement",
    "retro":             "Retro",
    "retro-feature":     "Retro",
    "mcp-test":          "Validate",
    "realign-spec":      "Realign",
    "ingest-research":   "Research",
    "__mark_complete__": "Mark Complete",
    "__mark_fixed__":    "Mark Fixed",
}


def format_cycle_header(
    state: dict,
    *,
    forward_cycles: "int | None" = None,
    max_cycles: "int | None" = None,
    meta_cycles: "int | None" = None,
) -> str:
    """Return a formatted FORWARD cycle-header line for the orchestrator probe
    payload, in the sanctioned T2 shape (em-dash separator is U+2014 ``—``):

        ### {Step} — {summary} [{fwd}/{max}]

    This is the forward-cycle sibling of ``emit_dispatch_prompt``'s META header
    (``### {Step} — {summary} [meta {m}]``). The prior WU-5 format —
    ``### Cycle fwd N/M · meta K · {feature} · {sub_skill}`` — was RETIRED by the
    orchestrator contract (lazy-batch/lazy-bug-batch SKILL.md: "the retired
    formats … must NOT reappear") and is deliberately NOT emitted here; the probe
    heading is echoed verbatim by the orchestrator, so a retired-format header
    would land the forbidden shape on every forward cycle
    (docs/bugs/format-cycle-header-emits-retired-cycle-fwd-format).

    Rendering:
    - ``{Step}``    = ``SUB_SKILL_STEP_NAMES`` lookup on the normalized
      ``state.get("sub_skill")``; unmapped → the normalized sub_skill itself;
      absent/falsy sub_skill → ``Cycle``.
    - ``{summary}`` = ``state.get("feature_id")`` if truthy else ``—`` (U+2014).
    - ``{fwd}``     = ``forward_cycles`` if not None else ``?``.
    - ``{max}``     = ``max_cycles`` if not None else ``?``.

    ``meta_cycles`` is accepted for signature back-compat but no longer rendered
    into the forward header (meta cycles carry their own header via
    ``emit_dispatch_prompt``).
    """
    # Render forward counters: value when supplied, else the '?' placeholder.
    fwd_str = str(forward_cycles) if forward_cycles is not None else "?"
    max_str = str(max_cycles) if max_cycles is not None else "?"

    # Step name from the sub_skill (normalized: strip a leading '/', lowercase).
    raw_sub_skill = state.get("sub_skill") or ""
    norm = str(raw_sub_skill).lstrip("/").strip().lower()
    if norm:
        step = SUB_SKILL_STEP_NAMES.get(norm, str(raw_sub_skill).lstrip("/").strip())
    else:
        step = "Cycle"

    # Summary: the item id, or the em-dash sentinel.
    summary = state.get("feature_id") or "—"

    return f"### {step} — {summary} [{fwd_str}/{max_str}]"


# ---------------------------------------------------------------------------
# Phase 1 — Run-state core: claude_state_dir, run marker, prompt registry,
#            persisted run counters
#
# All writes use _atomic_write (defined above) to prevent partial-write
# corruption across platforms.  All new behavior is gated on an explicit
# --run-start / marker-present path so the default (no-marker) output of
# both state scripts remains byte-identical.
# ---------------------------------------------------------------------------

# Registry TTL: unconsumed entries older than this are not dispatchable.
# 30 minutes is a deliberate approximation of "current turn window" — hooks
# have no reliable turn counter, so we use two complementary controls:
#   1. Single-use nonce + TTL (REGISTRY_ENTRY_TTL_SECONDS): entries expire 30
#      minutes after emission regardless of run marker state.
#   2. Run-start freshness gate (belt-and-braces): when a valid run marker is
#      present, lookup_emission additionally requires emitted_at >= marker's
#      started_at epoch — entries that predate the current run are never
#      dispatchable even if they are within the TTL window.  When no marker is
#      present the gate is skipped and only nonce+TTL semantics apply.
# SPEC deviation (recorded): the spec §Validate-deny step 2 says "emitted_at
# within the current turn window"; we approximate that as nonce + TTL +
# emitted_at-vs-started_at rather than a per-turn counter that hooks cannot
# observe.
REGISTRY_ENTRY_TTL_SECONDS: int = 1800  # 30 minutes

# Maximum number of entries kept in the prompt registry (ring cap).
# When a new entry would exceed the cap, the oldest entry is evicted first.
_REGISTRY_RING_CAP: int = 64


# Phase 7 WU-7.4: run-checkpoint filename (single JSON object).  Written by
# --run-end --reason checkpoint; consumed (echoed + deleted) by the next
# --run-start.  Consume-once resume context across a sanctioned pause.
_CHECKPOINT_FILENAME = "lazy-run-checkpoint.json"


# Staleness threshold: markers older than this (in seconds) are deleted.
_MARKER_STALE_SECONDS: float = 24 * 3600  # 24 hours

# ---------------------------------------------------------------------------
# Run-scoped marker field partition SSOT
# (adhoc-checkpoint-resume-field-complete-continuity, 2026-06-23)
#
# A sanctioned same-run checkpoint resume re-mints ALL run-scoped marker state on
# the resuming --run-start (write_run_marker writes the full literal at :8861).
# Continuity is then reconstructed AFTER the mint by restore_checkpoint_counters.
# Previously the reset-vs-carry decision was implicit and split across two
# functions, so a newly-added run-scoped field defaulted to the RESET side BY
# CONSTRUCTION and became the next reactive whack-a-mole.
#
# These two frozensets are the EXPLICIT, ENUMERATED SSOT that partitions every
# run-scoped key of the write_run_marker literal (:8861-8907) into:
#
#   RUN_CONTINUITY_FIELDS — CARRIED across a sanctioned (non-operator-authorized)
#     same-run pause/resume.  These are run-scoped accumulators / identity that
#     the SAME run accrues; resetting any mid-run violates the super-invariant
#     "run-scoped continuity state survives a same-run pause" (HARD CONSTRAINT 8
#     for the counters; cycle-bracket continuity for started_at; the per-feature
#     budget maps are run-scoped accumulators a sanctioned resume must continue).
#
#   RUN_FRESH_FIELDS — RESET / re-minted fresh on resume.  last_advance_consume_count
#     deliberately zeros (the registry is freshly cleared on run-start; carrying a
#     stale watermark would suppress the first post-resume advance — SPEC Out of
#     Scope).  The remaining keys are run-INVARIANT identity/config that
#     write_run_marker re-derives identically anyway (session_id is owner-bound by
#     the resuming --run-start; work_branch is re-resolved at run-start).
#
# COMPLETENESS INVARIANT (the by-construction guarantee, enforced by
# test_run_marker_continuity_partition_is_complete_and_disjoint):
#   set(RUN_CONTINUITY_FIELDS) | set(RUN_FRESH_FIELDS) == _run_marker_scoped_keys()
#   AND the two sets are disjoint.
# A newly-added run-scoped marker key is then a HARD test failure until it is
# explicitly placed in ONE set — it can never silently default to reset.
RUN_CONTINUITY_FIELDS: frozenset = frozenset({
    "forward_cycles",
    "meta_cycles",
    "started_at",
    "per_feature_forward_cycles",
    "per_feature_corrective_cycles",
})
RUN_FRESH_FIELDS: frozenset = frozenset({
    "last_advance_consume_count",
    "pipeline",
    "cloud",
    "repo_root",
    "session_id",
    "max_cycles",
    "nonce_seed",
    "attended",
    "work_branch",
    # parallel-worktree-batch-execution (D2-A): the sanctioned-lane identity
    # stamp ({repo_root, started_at} of the parent run; None on serial runs).
    # Run-INVARIANT identity re-derived at run-start — a checkpoint resume's
    # --run-start re-supplies it (or correctly resets a serial resume to None),
    # so it belongs on the FRESH side, never carried.
    "parent_run",
})


def _run_marker_scoped_keys() -> "set[str]":
    """Return the ACTUAL run-scoped key set of a freshly-minted marker.

    The completeness assertion (test) checks the RUN_CONTINUITY_FIELDS /
    RUN_FRESH_FIELDS partition against THIS — the live write_run_marker literal —
    so the assertion can never drift from a hand-copied list.  Hermetic: mints a
    throwaway marker into the active state dir with an injected ``now`` and reads
    its keys (write_run_marker has no side effect beyond the state-dir file, which
    the test fixture owns and clears).
    """
    return set(
        write_run_marker(
            pipeline="feature", cloud=False, repo_root="/r", now=0.0,
        ).keys()
    )


# ---------------------------------------------------------------------------
# Per-repo state-dir scoping (multi-repo-concurrent-runs)
#
# The run-scoped state (marker, prompt registry, deny-ledger, cycle marker,
# checkpoint) all resolve their paths through claude_state_dir().  To let a
# lazy run in one repo neither block nor be blocked by a run in another repo,
# claude_state_dir() is scoped PER REPO at this single chokepoint — when
# LAZY_STATE_DIR is unset (production), it returns
# ``~/.claude/state/<repo_key>/`` instead of the shared base dir.  When
# LAZY_STATE_DIR IS set (hermetic unit tests + hook pipe-tests) the override is
# returned EXACTLY, so every existing test's path semantics are preserved
# byte-for-byte.
#
# The active repo is set ONCE per process at each state script's main() via
# set_active_repo_root(); the 24 internal claude_state_dir() callers need no
# signature change.  A single lazy-state.py / bug-state.py invocation operates
# on exactly one repo, so the module-level active repo is unambiguous; two
# concurrent runs in different repos are different processes resolving to
# different subdirs, so they never collide on marker, registry, ledger, or
# cycle counters.
# ---------------------------------------------------------------------------

# The active repo root and the legacy-migration one-shot guard are now owned
# by lazy_core._ctx (WU-2 of lazy-core-package-decomposition) — see
# set_active_repo_root() / active_repo_root() / migrate_legacy_state_dir()
# below, which read/write them via the _ctx accessors so a direct
# lazy_core._ctx._active_repo_root / _legacy_state_migrated module-attribute
# patch (as tests do) is observed live.


# ---------------------------------------------------------------------------
# Merged work-list view (unified-pipeline-orchestrator Phase 1)
# ---------------------------------------------------------------------------
#
# A thin, stdlib-only ordering layer over the two queues. It does NOT re-infer
# per-item state — it only orders the queues' items and returns the next
# actionable head as {item_id, type, repo_root}. The unified driver still calls
# lazy-state.py / bug-state.py --probe/--emit-prompt per item for the real next
# action (see PHASES.md Phase 1 Integration Notes).
#
# Ordering-field spike (Phase 1, observed against REAL on-disk queues
# 2026-06-17): the two queues use DIFFERENT field names + scales —
#   - docs/features/queue.json items carry `tier` (int; observed value 1; lower
#     number = higher priority by convention). No `priority`/`severity` key.
#   - docs/bugs/queue.json items carry `severity` (string P0/P1/P2/Low), mapped
#     to a numeric rank by bug-state.py's _SEVERITY_RANK {P0:0,P1:1,P2:2,Low:3}.
# So a NORMALIZATION MAP is required — the comparator coerces both to a single
# "effective priority" (lower = higher priority). This is the resolution of the
# SPEC Open Question "Ordering field source".

# Severity → numeric rank (mirrors bug-state.py:_SEVERITY_RANK; duplicated here
# rather than imported because bug-state.py is a hyphenated module that imports
# lazy_core — a back-import would be circular). Lower = higher priority.
_MERGED_SEVERITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "Low": 3}
# Effective priority for an item with no comparable field — sorts last.
MERGED_PRIORITY_DEFAULT = 99
# Tie-break on equal effective priority: bugs sort before features.
_MERGED_TYPE_ORDER: dict[str, int] = {"bug": 0, "feature": 1}

# ---------------------------------------------------------------------------
# bug-queue-aging-backpressure D1-A/D2-A/D3-A: age-escalation + severity-pin
# expiry over the bug axis of the merged comparator. Feature `tier` carries no
# analogous aging signal (no `**Discovered:**` concept), so this is BUG-ONLY —
# a deliberate v1 scope narrowing (see the feature's Locked Decisions).
# ---------------------------------------------------------------------------

# One escalation notch per this many days at tail (D3-A: **Discovered:**
# wall-clock age, zero new durable state).
_AGE_ESCALATION_QUANTUM_DAYS = 7
# Escalation never passes this rank (P1-equivalent) — a genuine P0 (rank 0)
# always outranks a merely-aged bug.
_AGE_ESCALATION_FLOOR_RANK = 1
# A pin with only `pinned_at` (no explicit `pinned_until`) expires after this
# many days — the D2-A "default max pin age" fallback.
_PIN_DEFAULT_MAX_AGE_DAYS = 90


def age_escalated_rank(
    base_rank: int, discovered: "str | None", today: "datetime.date | None" = None
) -> int:
    """Age-escalate an effective priority rank toward 0 (bug-queue-aging-
    backpressure D1-A/D3-A).

    Each ``_AGE_ESCALATION_QUANTUM_DAYS``-day quantum since ``discovered``
    bumps ``base_rank`` one notch toward 0, capped at
    ``_AGE_ESCALATION_FLOOR_RANK`` — a genuine P0 always outranks escalation.
    Pure function of (base_rank, discovered, today); callers supply ``today``
    for determinism (tests inject a fixed date; production omits it).

    Fail-open: an absent/unparseable ``discovered``, a rank already at or
    past the floor, or a future-dated discovery all return ``base_rank``
    unchanged — no fabricated age, never a crash.
    """
    if base_rank <= _AGE_ESCALATION_FLOOR_RANK:
        return base_rank
    if not discovered:
        return base_rank
    try:
        discovered_date = datetime.date.fromisoformat(str(discovered).strip())
    except (ValueError, TypeError):
        return base_rank
    ref_today = today if today is not None else datetime.date.today()
    age_days = (ref_today - discovered_date).days
    if age_days < 0:
        return base_rank
    notches = age_days // _AGE_ESCALATION_QUANTUM_DAYS
    return max(base_rank - notches, _AGE_ESCALATION_FLOOR_RANK)


def pin_is_active(
    pinned_at: "str | None",
    pinned_until: "str | None",
    today: "datetime.date | None" = None,
) -> bool:
    """True iff a bug-queue severity pin (bug-queue-aging-backpressure D2-A)
    is still suppressing the entry's severity.

    False when never pinned (``pinned_at`` absent) OR the pin has expired —
    past ``pinned_until`` when present, else past ``_PIN_DEFAULT_MAX_AGE_DAYS``
    days from ``pinned_at``. Once expired, the merged view falls back to the
    SPEC's own declared severity (D2-A). Fail-open: an unparseable date is
    treated as expired — never a silently-permanent suppression from a typo.
    """
    if not pinned_at:
        return False
    ref_today = today if today is not None else datetime.date.today()
    try:
        at = datetime.date.fromisoformat(str(pinned_at).strip())
    except (ValueError, TypeError):
        return False
    if pinned_until:
        try:
            until = datetime.date.fromisoformat(str(pinned_until).strip())
        except (ValueError, TypeError):
            return False
        return ref_today <= until
    return (ref_today - at).days < _PIN_DEFAULT_MAX_AGE_DAYS


def bug_priority_marker(
    *,
    severity: "str | None",
    spec_severity: "str | None",
    discovered: "str | None",
    pinned_at: "str | None",
    pinned_until: "str | None",
    today: "datetime.date | None" = None,
) -> str:
    """Render the queue-doc pin/escalation marker for one bug row
    (bug-queue-aging-backpressure D4-A).

    ``"📌 pinned <date>"`` while an active pin suppresses the bug's severity;
    ``"⏫ escalated"`` when age-escalation has moved the EFFECTIVE priority
    (``merged_priority``) past the declared severity (queue override, or the
    SPEC's own after an expired pin); ``""`` otherwise. Honest wrinkle
    (documented in the SPEC): this is a function of ``today`` in addition to
    on-disk state, so a render CAN legitimately change across days with no
    state change — byte-stability holds for unchanged (state, date).
    """
    raw = {
        "severity": severity,
        "discovered": discovered,
        "spec_severity": spec_severity,
        "pinned_at": pinned_at,
        "pinned_until": pinned_until,
    }
    if pinned_at and pin_is_active(pinned_at, pinned_until, today):
        return f"\U0001F4CC pinned {pinned_at}"  # 📌
    declared = severity if (
        isinstance(severity, str) and severity.strip() in _MERGED_SEVERITY_RANK
    ) else spec_severity
    if not (isinstance(declared, str) and declared.strip() in _MERGED_SEVERITY_RANK):
        return ""
    declared_rank = _MERGED_SEVERITY_RANK[declared.strip()]
    effective = merged_priority("bug", raw, today=today)
    if effective < declared_rank:
        return "⏫ escalated"  # ⏫
    return ""


def merged_priority(
    item_type: str, raw_item: dict, *, today: "datetime.date | None" = None
) -> int:
    """Normalize a queue item's ordering field to a single numeric effective
    priority (lower = higher priority), bridging the two queues' divergent
    field names/scales.

    feature → ``tier`` (int); bug → ``severity`` (P0/P1/P2/Low → rank),
    age-escalated (D1-A/D3-A) via the item's ``discovered`` field. A
    missing / unrecognized field yields ``MERGED_PRIORITY_DEFAULT`` (sorts
    last) rather than raising — a malformed queue entry must not crash the
    merged view. ``today`` is caller-supplied for determinism (tests inject a
    fixed date; production omits it).

    Bug null-severity handling (D2-A): a bug carrying an EXPLICIT recognized
    ``severity`` always age-escalates. A bug with ``severity: null`` and an
    active pin (``pinned_at`` set, not yet expired per ``pin_is_active``)
    stays suppressed at ``MERGED_PRIORITY_DEFAULT`` — the deliberate,
    reviewable deprioritization holds. Once the pin EXPIRES, the merged view
    falls back to the item's ``spec_severity`` (the SPEC's own
    ``**Severity:**`` line) and resumes age-escalating from there. A bare
    ``severity: null`` with NO ``pinned_at`` (legacy / never explicitly
    pinned via the sanctioned mutation) is byte-identical to before —
    ``MERGED_PRIORITY_DEFAULT``, no fallback, no escalation — so shipping
    this does not retroactively change any already-committed queue entry's
    behavior; only bugs newly pinned via the sanctioned mutation age out.
    """
    if item_type == "feature":
        tier = raw_item.get("tier")
        if isinstance(tier, bool):  # bool is an int subclass — reject it
            return MERGED_PRIORITY_DEFAULT
        if isinstance(tier, int):
            return tier
        if isinstance(tier, str):
            try:
                return int(tier.strip())
            except (ValueError, AttributeError):
                return MERGED_PRIORITY_DEFAULT
        return MERGED_PRIORITY_DEFAULT
    if item_type == "bug":
        sev = raw_item.get("severity")
        if isinstance(sev, str) and sev.strip() in _MERGED_SEVERITY_RANK:
            base = _MERGED_SEVERITY_RANK[sev.strip()]
            return age_escalated_rank(base, raw_item.get("discovered"), today)
        pinned_at = raw_item.get("pinned_at")
        if pinned_at and not pin_is_active(
            pinned_at, raw_item.get("pinned_until"), today
        ):
            spec_sev = raw_item.get("spec_severity")
            if isinstance(spec_sev, str) and spec_sev.strip() in _MERGED_SEVERITY_RANK:
                base = _MERGED_SEVERITY_RANK[spec_sev.strip()]
                return age_escalated_rank(base, raw_item.get("discovered"), today)
        return MERGED_PRIORITY_DEFAULT
    return MERGED_PRIORITY_DEFAULT


def merged_worklist(
    feature_items: list[dict],
    bug_items: list[dict],
    repo_root: str,
    *,
    today: "datetime.date | None" = None,
) -> list[dict]:
    """Order both queues into a single work-list and return it as a list of
    ``{"item_id", "type", "repo_root"}`` dicts (head first).

    Inputs are the items already produced by the EXISTING queue loaders
    (``lazy-state.load_queue`` for features, ``bug-state.load_bug_queue`` for
    bugs) — this helper never re-parses queue.json. It is pure ordering: it
    does NOT call ``compute_state`` or otherwise re-infer per-item state.

    Ordering contract (SPEC + PHASES Phase 1):
      1. Effective priority ascending (``merged_priority`` — lower = higher
         priority; feature ``tier`` and bug ``severity`` normalized to one
         scale).
      2. Tie on equal priority → ``type == "bug"`` before ``type ==
         "feature"``.
      3. Stable for equal (priority, type): each queue's own listed order is
         preserved (Python's sort is stable, and we seed the input in
         bug-then-feature, queue-listed order before sorting on (priority,
         type-rank) only).

    Each input item is expected to carry an id field. Feature loader items use
    ``id``; bug loader items use ``id`` as well. Items missing an id are
    skipped (a malformed entry must not produce a None-id head).
    """
    annotated: list[tuple[int, int, int, dict]] = []
    seq = 0
    # Seed bugs first then features so that, at equal (priority, type-rank),
    # the stable sort preserves bug-before-feature AND each queue's listed
    # order. The (priority, type_rank) sort key alone + stable sort + this seed
    # order yields the full contract.
    for raw in bug_items:
        item_id = raw.get("id")
        if not item_id:
            continue
        annotated.append(
            (merged_priority("bug", raw, today=today), _MERGED_TYPE_ORDER["bug"], seq,
             {"item_id": item_id, "type": "bug", "repo_root": repo_root})
        )
        seq += 1
    for raw in feature_items:
        item_id = raw.get("id")
        if not item_id:
            continue
        annotated.append(
            (merged_priority("feature", raw, today=today), _MERGED_TYPE_ORDER["feature"], seq,
             {"item_id": item_id, "type": "feature", "repo_root": repo_root})
        )
        seq += 1
    # Sort by (effective priority, type-rank, original seed seq). The seq tie
    # breaker guarantees stability across Python versions and is the explicit
    # within-queue listed-order preservation.
    annotated.sort(key=lambda t: (t[0], t[1], t[2]))
    return [entry for (_p, _t, _s, entry) in annotated]


def next_merged(
    feature_items: list[dict],
    bug_items: list[dict],
    repo_root: str,
    *,
    today: "datetime.date | None" = None,
) -> dict | None:
    """Return the head of the merged work-list (``{item_id, type, repo_root}``)
    or ``None`` when both queues are empty. Thin head-of ``merged_worklist``.
    ``today`` is caller-supplied for determinism (bug-queue-aging-backpressure)."""
    worklist = merged_worklist(feature_items, bug_items, repo_root, today=today)
    return worklist[0] if worklist else None


"""Sentinel returned by ``_await_compile_serving`` when the runtime crossed from
``compiling`` to ``dead`` mid-wait (Vite went down) — the M4 caller routes this
into the bounded ``_recover_runtime`` crash path. NOT a verdict dict, so a caller
must check identity before treating the return as a verdict."""


# ---------------------------------------------------------------------------
# gate_coverage — WU-2: deterministic, symlink-resolving Gate-1 verdict.
#
# Promotes the mcp-coverage-audit.md algorithm to code: enumerate the SPEC's
# Locked-Decision surface, grep mcp-tests/*.md (RESOLVING symlink / 64-byte
# pointer targets — the Windows blindspot), return covered/uncovered per
# decision.
# ---------------------------------------------------------------------------

# Words dropped when deriving keyword anchors from a decision title.
_GATE_COVERAGE_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "be", "by", "with", "from", "as", "at", "via", "uses", "use", "only",
    "decision", "must", "should", "will", "that", "this", "it",
})


def _gate_coverage_keywords(title: str) -> list[str]:
    """Extract the distinctive content words from a decision title (lowercased,
    stopwords dropped, deduped, order-preserved)."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", title.lower())
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        if w in _GATE_COVERAGE_STOPWORDS or len(w) < 3:
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _parse_locked_decisions(spec_md: str) -> list[dict]:
    """Parse the SPEC.md Locked-Decision surface into [{id, title, keywords}].

    Priority order (first surface that yields rows wins):
      1. ``## Locked Decisions`` H2 with a table whose first column is the id.
      2. ``## Resolved by Research`` H2 with ``- [x]`` bullets.
      3. ``## Key Decisions`` / ``## Design Decisions`` numbered block.
    Returns [] when no surface exists (caller passes vacuously).
    """
    lines = spec_md.splitlines()

    def _section_body(heading_res: list[str]) -> list[str] | None:
        for i, ln in enumerate(lines):
            for pat in heading_res:
                if re.match(pat, ln.strip(), re.IGNORECASE):
                    body: list[str] = []
                    for nxt in lines[i + 1:]:
                        if re.match(r"^##\s", nxt.strip()):
                            break
                        body.append(nxt)
                    return body
        return None

    decisions: list[dict] = []

    # --- Surface 1: ## Locked Decisions table ---
    body = _section_body([r"^##\s+Locked Decisions\b"])
    if body is not None:
        for ln in body:
            s = ln.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2:
                continue
            first = cells[0]
            title = cells[1]
            # Skip the header row and the |---|---| separator row. The header's
            # id column may be labelled 'id' / 'decision' / '#' / 'no' / 'num',
            # and its SECOND (Decision/title) column literally reads "Decision" —
            # key on the title-column header for robustness, not only the id
            # label. The observed canonical header '| # | Decision | Choice |
            # Source |' slipped the id-only skip (first == '#', not in the set)
            # and became a PHANTOM decision id='#', title='Decision' that could
            # never be covered → Gate 1 unsatisfiable (harden 2026-07).
            if (
                not first
                or set(first) <= set("-: ")
                or first.lower() in ("id", "decision", "#", "no", "num", "idx")
                or title.strip().lower() == "decision"
            ):
                continue
            did = first
            decisions.append(
                {"id": did, "title": title, "keywords": _gate_coverage_keywords(title)}
            )
        if decisions:
            return decisions

    # --- Surface 2: ## Resolved by Research checked bullets ---
    body = _section_body([r"^##\s+Resolved by Research\b"])
    if body is not None:
        idx = 0
        for ln in body:
            m = re.match(r"^\s*-\s*\[x\]\s+(.*)$", ln, re.IGNORECASE)
            if m:
                idx += 1
                title = m.group(1).strip()
                # Try to lift a leading id token (R1:, L2 —, etc.).
                idm = re.match(r"^([A-Z]\d+)\b[:\.\)\-\s]", title)
                did = idm.group(1) if idm else f"R{idx}"
                decisions.append(
                    {"id": did, "title": title,
                     "keywords": _gate_coverage_keywords(title)}
                )
        if decisions:
            return decisions

    # --- Surface 3: ## Key/Design Decisions numbered block ---
    body = _section_body([r"^##\s+Key Decisions\b", r"^##\s+Design Decisions\b"])
    if body is not None:
        idx = 0
        for ln in body:
            m = re.match(r"^\s*\d+[\.\)]\s+(.*)$", ln)
            if m:
                idx += 1
                title = m.group(1).strip()
                decisions.append(
                    {"id": f"K{idx}", "title": title,
                     "keywords": _gate_coverage_keywords(title)}
                )
        if decisions:
            return decisions

    return []


def _resolve_scenario_text(path: Path) -> str:
    """Read an mcp-tests/*.md scenario, RESOLVING symlink / 64-byte pointer
    targets (the Windows blindspot).

    On a real symlink, ``read_text`` already follows it. But git on Windows
    without symlink privilege writes a tiny TEXT file whose CONTENT is the
    relative target path (the "64-byte pointer file"). We detect that case: a
    small file whose entire content is a single relative path that resolves to
    an existing file → read the TARGET instead. Best-effort; never raises.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # Pointer-file heuristic: short, single-line, no newline-y markdown, and the
    # content resolves to an existing sibling file.
    stripped = raw.strip()
    if stripped and "\n" not in stripped and len(stripped) <= 260:
        # Looks path-like (has a separator or ends in .md) and is not prose.
        looks_pathish = (
            stripped.endswith(".md")
            and ("/" in stripped or "\\" in stripped or stripped == path.name)
            and " " not in stripped
        )
        if looks_pathish:
            candidate = (path.parent / stripped).resolve()
            if candidate.exists() and candidate.is_file() and candidate != path.resolve():
                try:
                    return candidate.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return raw
    return raw


def _parse_mcp_coverage_exemptions(spec_md: str) -> dict:
    """Parse a ``## MCP Coverage Exemptions`` SPEC section → {id: rationale}.

    This is the DETERMINISTIC home for the mcp-coverage-audit.md D7 disposition
    "documented-MCP-untestable decisions get an inline SPEC test-exempt note".
    Before this parser existed, ``gate_coverage`` had NO exemption path — a
    decision was coverable ONLY by an ``mcp-tests/*.md`` scenario reference — so
    the component's prescribed inline SPEC exempt note could not actually satisfy
    the gate (a backend/miniflare-verified Locked Decision, which has no Tauri
    MCP surface to drive, was permanently ``uncovered``). harden 2026-07.

    Recognized surface — an H2 ``## MCP Coverage Exemptions`` whose body carries
    bullets of the shape ``- <ID>: <rationale>`` (or ``- <ID> — <rationale>``).
    An entry counts ONLY when BOTH the id token and a NON-EMPTY rationale are
    present (mirroring the ``observation_gap_exemptions`` ``spec_class``-required
    discipline: the citation is what distinguishes a verified untestable-class
    assessment from a convenience skip). A bare ``- D4`` with no rationale is
    IGNORED (not exempt) so an empty stub cannot launder the gate.

    Returns ``{}`` when the section is absent (the gate is unchanged for every
    SPEC that does not opt in).
    """
    lines = spec_md.splitlines()
    exemptions: dict = {}
    in_section = False
    for ln in lines:
        s = ln.strip()
        if re.match(r"^##\s+MCP Coverage Exemptions\b", s, re.IGNORECASE):
            in_section = True
            continue
        if in_section and re.match(r"^##\s", s):
            break  # next H2 ends the section
        if not in_section:
            continue
        # ``- <ID>: <rationale>`` or ``- <ID> — <rationale>`` (id = leading
        # alnum token; rationale = the remainder after the : / — / - separator).
        m = re.match(r"^-\s+([A-Za-z]?\d+|[A-Za-z]{1,4}\d*)\s*[:—\-]\s*(.+\S)\s*$", s)
        if m:
            did = m.group(1).strip()
            rationale = m.group(2).strip()
            if did and rationale:
                exemptions[did] = rationale
    return exemptions


def gate_coverage(spec_path: Path) -> dict:
    """Deterministic Gate-1 MCP-coverage verdict for a feature/bug spec dir.

    Reads ``spec_path/SPEC.md``'s Locked-Decision surface, greps
    ``spec_path/mcp-tests/*.md`` (RESOLVING symlink / pointer targets), and
    returns per-decision covered/uncovered.

    A decision is **covered** iff at least one scenario file contains the
    decision ``id`` as a literal OR contains at least 2 of the decision's
    keywords (case-insensitive) — OR it is **exempt**: listed in a
    ``## MCP Coverage Exemptions`` SPEC section with a non-empty rationale (the
    mcp-coverage-audit.md D7 disposition for documented-MCP-untestable decisions,
    e.g. backend/miniflare-verified Locked Decisions with no Tauri MCP surface).
    An exempt decision is NOT added to ``uncovered``; its entry carries
    ``exempt: True`` + the ``rationale`` so the disposition is auditable. This
    mirrors mcp-coverage-audit.md Step 3.

    Return shape::

        {"ok": True,
         "decisions": [{"id", "title", "keywords", "covered"}, ...],
         "uncovered": [id, ...],
         "scenario_count": int}

    A SPEC with no Locked-Decision surface passes vacuously (empty lists). An
    empty/absent mcp-tests dir → every decision uncovered.
    """
    spec_md_path = spec_path / "SPEC.md"
    spec_md = ""
    if spec_md_path.exists():
        try:
            spec_md = spec_md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            spec_md = ""

    decisions = _parse_locked_decisions(spec_md)
    exemptions = _parse_mcp_coverage_exemptions(spec_md)

    # Gather (resolved) scenario texts.
    mcp_dir = spec_path / "mcp-tests"
    scenario_texts: list[str] = []
    if mcp_dir.exists() and mcp_dir.is_dir():
        for p in sorted(mcp_dir.glob("*.md")):
            scenario_texts.append(_resolve_scenario_text(p))

    result_decisions: list[dict] = []
    uncovered: list[str] = []
    for d in decisions:
        did = d["id"]
        kws = d["keywords"]
        covered = False
        for text in scenario_texts:
            if did and re.search(rf"\b{re.escape(did)}\b", text):
                covered = True
                break
            low = text.lower()
            if kws and sum(1 for k in kws if k in low) >= 2:
                covered = True
                break
        # Exemption path (D7): a decision documented as MCP-untestable in the
        # ``## MCP Coverage Exemptions`` section with a non-empty rationale is
        # NOT uncovered — it is a sanctioned disposition, not a gap. Scenario
        # coverage still wins (a decision that is BOTH scenario-covered and
        # listed stays covered=True, exempt=False).
        exempt_rationale = exemptions.get(did)
        exempt = (not covered) and bool(exempt_rationale)
        entry = {"id": did, "title": d["title"], "keywords": kws, "covered": covered}
        if exempt:
            entry["exempt"] = True
            entry["rationale"] = exempt_rationale
        result_decisions.append(entry)
        if not covered and not exempt:
            uncovered.append(did)

    return {
        "ok": True,
        "decisions": result_decisions,
        "uncovered": uncovered,
        "scenario_count": len(scenario_texts),
    }


# ---------------------------------------------------------------------------
# Run-marker API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 7 (lazy-validation-readiness) — sanctioned stop-terminal set.
#
# Motivating incident 2026-06-14: an attended /lazy-batch 50 run stopped at
# 5/50 cycles via --run-end --reason terminal with a fabricated reason, without
# operator authorization.  This constant is the authoritative list of reasons
# that allow an unattended or operator-authorized terminal stop.  Any reason
# NOT in this set is refused unless --operator-authorized is passed.
#
# Both lazy-state.py and bug-state.py import this constant so the set is
# defined in exactly one place (no copy-paste drift between the coupled pair).
# ---------------------------------------------------------------------------
SANCTIONED_STOP_TERMINAL: frozenset[str] = frozenset({
    "all-features-complete",   # feature queue exhausted
    "all-bugs-fixed",          # bug queue exhausted
    "max-cycles",              # hard cycle cap reached
    "cloud-queue-exhausted",   # cloud run out of queue items
    "device-queue-exhausted",  # device run out of queue items
    # host-capability-declaration-for-gated-features Phase 6: the host-axis
    # generalization of device-queue-exhausted — every remaining feature is
    # gated on a host capability absent on THIS host (DEFERRED_REQUIRES_HOST.md).
    # A clean, sanctioned stop (re-opens on a capability-bearing host), so the
    # orchestrator may end a run on it without --operator-authorized, exactly
    # like the device terminal. Feature-pipeline-only in practice (bug-state.py
    # does not emit it), but membership is harmless for the shared frozenset.
    "host-capability-saturated",  # all remaining features gated on an absent host capability
    "queue-missing",           # queue.json absent → cannot continue
    "blocked-halt-for-manual", # script-emitted BLOCKED.md halt
    "needs-research",          # NEEDS_INPUT.md needs-research halt
    "queue-blocked-on-research",  # all queue items need research
    # queue-dependency-dag D4: every remaining queue item is dep-gated (held
    # on an incomplete declared dependency). A clean, sanctioned stop — the
    # holds re-open automatically as their deps complete — so the orchestrator
    # may end a run on it without --operator-authorized, exactly like the
    # host-capability / all-parked exhaustion terminals. Emitted by BOTH state
    # scripts (the dep-gate is a coupled-pair surface).
    "queue-exhausted-dependency-gated",  # all remaining items held on incomplete deps
})


def write_run_marker(
    pipeline: str,
    cloud: bool,
    repo_root: str,
    *,
    max_cycles: int | None = None,
    session_id: str | None = None,
    nonce_seed: str | None = None,
    attended: bool = True,
    parent_run: dict | None = None,
    now: float | None = None,
) -> dict:
    """Write (or overwrite) the run marker to the state dir.

    The marker signals that an orchestrator run is active.  Both state scripts'
    ``--run-start`` flag calls this function after preflight passes.  The marker
    is the gating signal for all Phase 1 side effects: without it, registry
    writes, counter advances, and hook injections are all no-ops.

    Fields written:
      - pipeline (str): "feature" | "bug"
      - cloud (bool): whether the run targets cloud mode
      - repo_root (str): absolute path to the project root
      - session_id (str|None): the orchestrator's Claude Code session id.
        None means "bind-on-first-hook-firing" — the inject hook stamps it.
      - started_at (str): ISO-8601 UTC timestamp ending in 'Z'
      - max_cycles (int|None): hard cap for the run
      - nonce_seed (str|None): seed used by nonce derivation (optional — callers
        may omit for fully random nonces)
      - forward_cycles (int): number of real-skill dispatch cycles so far (0)
      - meta_cycles (int): number of meta/pseudo-skill cycles so far (0)
      - attended (bool): Phase 7 — True for interactive /lazy-batch runs (the
        default); False for scheduled/cron/unattended runs.  The stop-
        authorization gate on --run-end reads this field: an attended run cannot
        checkpoint-stop without explicit operator authorization.  Legacy markers
        lacking this field are treated as attended=True (the stricter gate).

    Args:
        pipeline: "feature" or "bug"
        cloud: True when the run is a cloud run
        repo_root: absolute path to the project root as a string
        max_cycles: optional hard cap (stored for inject hook / cycle headers)
        session_id: optional Claude Code session id; None = bind-pending
        nonce_seed: optional nonce seed string
        attended: Phase 7 — True (default) for interactive runs; False for
            scheduled/unattended runs that pass --unattended to --run-start.
        parent_run: parallel-worktree-batch-execution (D2-A) — the sanctioned-
            lane identity stamp `{repo_root, started_at}` of the PARENT run
            whose coordinator armed this marker at a worktree root. None (the
            default) on every serial run — the key is ALWAYS minted so the
            marker shape is stable and the continuity-partition completeness
            test forces explicit classification. Audits and --run-end sweeps
            use it to prove a lane marker sanctioned (vs a rogue walker's).
            Run-invariant identity re-derived at run-start ⇒ RUN_FRESH_FIELDS.
        now: epoch float for started_at (injectable for hermetic tests;
             defaults to time.time())

    Returns:
        The marker dict that was written.
    """
    if now is None:
        now = time.time()
    # Convert the epoch float to an ISO-8601 UTC string ending in 'Z' —
    # the spec's exact format requirement for the started_at field.
    # Use fromtimestamp(tz=utc) — the deprecated utcfromtimestamp() produces a
    # naive datetime that is ambiguous in Python ≥3.12 deprecation warnings.
    started_at = (
        datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    )
    marker: dict = {
        "pipeline": pipeline,
        "cloud": cloud,
        "repo_root": str(repo_root),
        "session_id": session_id,
        "started_at": started_at,
        "max_cycles": max_cycles,
        "nonce_seed": nonce_seed,
        "forward_cycles": 0,
        "meta_cycles": 0,
        # feature-budget-guard-and-skip-ahead Phase 1: per-feature forward-cycle
        # consumption, keyed on feature_id. Advanced as a SIBLING write inside the
        # SAME marker mutation that advances the run-level forward_cycles (both
        # forward-advance triggers carry it), gated by the EXACT same forward-vs-
        # meta classifier. The Phase-2 trip eval reads this map vs the computed
        # ceiling. Legacy markers lacking the key default to {} on read/advance.
        "per_feature_forward_cycles": {},
        # budget-guard-defers-near-complete-feature Phase 1: per-feature count of
        # forward cycles attributable to validation-driven corrective work,
        # keyed on feature_id. Incremented at the corrective-dispatch bracket
        # (record_corrective_cycle, wired in Phase 2) and DISCOUNTED from the
        # budget-guard trip count by budget_trip_signals so a feature that did
        # legitimate corrective work is not punished as monopolization. Seeded
        # {} here in lockstep with per_feature_forward_cycles; legacy markers
        # lacking the key default to {}/0 on read (count_validation_corrective_cycles).
        "per_feature_corrective_cycles": {},
        # ISSUE 5 (d8-effect-chains live run, 2026-06-14): the consume-count
        # watermark at which a cycle counter was last advanced. A counter advances
        # only when the registry consume-count exceeds this (one consume per real
        # dispatch), so bare inject-probe firings never inflate the counter.
        # Starts at 0 — the first advance requires at least one consumed dispatch.
        "last_advance_consume_count": 0,
        # Phase 7 / lazy-validation-readiness: record whether this is an
        # attended (interactive) or unattended (scheduled/cron) run.
        # Default True ensures legacy/migrated callers default to the stricter
        # gate — an attended run cannot checkpoint-stop without operator auth.
        "attended": attended,
        # cycle-subagent-fabricates-policy-or-stray-branch Phase 2: capture the
        # work branch the orchestrator is on at run-start so the write-time
        # stray-branch hook (block-sentinel-write-on-stray-branch.sh) has a
        # reference branch to compare HEAD against. Resolved via _emit_work_branch
        # (best-effort; a non-git root yields its documented fallback string,
        # never raises). Legacy markers lacking this field read as None via
        # marker_work_branch() (back-compat, same pattern as attended /
        # per_feature_forward_cycles).
        "work_branch": _emit_work_branch(Path(repo_root)),
        # parallel-worktree-batch-execution (D2-A): sanctioned-lane identity —
        # the parent run's {repo_root, started_at} when a coordinator armed
        # this marker at a worktree root; None on every serial run. ALWAYS
        # minted (stable marker shape); classified RUN_FRESH_FIELDS.
        "parent_run": parent_run,
    }
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def parse_parent_run_arg(raw: "str | None") -> "dict | None":
    """Validate a ``--run-start --parent-run`` JSON payload (D2-A, shared).

    ``None``/empty → ``None`` (a serial run; the marker still mints
    ``parent_run: null``).  Otherwise the payload MUST be a JSON object with
    string ``repo_root`` and ``started_at`` — anything else ``_die``s exit 2
    with ZERO side effects (callers invoke this BEFORE ``write_run_marker``).
    Extra keys are dropped: the marker stores exactly the two-identity stamp.
    Shared by BOTH state scripts (coupled pair — the marker is shared).
    """
    if not raw:
        return None
    shape_msg = (
        "--parent-run must be a JSON object "
        '{"repo_root": <str>, "started_at": <str>} identifying the parent run'
    )
    try:
        val = json.loads(raw)
    except ValueError:
        _die(shape_msg)
        return None  # pragma: no cover — _die exits
    if not (
        isinstance(val, dict)
        and isinstance(val.get("repo_root"), str)
        and isinstance(val.get("started_at"), str)
    ):
        _die(shape_msg)
        return None  # pragma: no cover — _die exits
    return {"repo_root": val["repo_root"], "started_at": val["started_at"]}


def read_run_marker(
    now: float | None = None,
    session_id: str | None = None,
) -> dict | None:
    """Read the run marker from the state dir, or return None if absent/stale.

    Staleness rules — note the ASYMMETRY between paths A and B (Phase 8 WU-8.1):
      A) Age staleness (DELETE-ON-READ): the marker's ``started_at`` is more
         than 24 hours before ``now`` (injectable epoch float; defaults to
         time.time()).  The marker is DELETED and None is returned.  A crashed
         run must not haunt the next interactive session, and after 24h the
         owning run is presumed dead — destroying its marker is safe.
      B) Session-id mismatch (NON-DESTRUCTIVE — returns None WITHOUT deleting):
         BOTH of the following must be true for the marker to be session-stale:
           * The caller passes a non-None ``session_id`` argument.
           * The marker's ``session_id`` field is also non-None (i.e. the
             marker is "bound", not "bind-pending").
         When that mismatch holds, this function returns None but LEAVES THE
         MARKER FILE ON DISK.  Rationale (Phase 8): a concurrent NON-owner
         session (e.g. an interactive session running while a marked /lazy-batch
         run is live) must see "no marker" (no banner, fast-path allow) but must
         NEVER destroy the OWNING session's live run state.  Deleting here
         silently disarmed enforcement mid-run on 2026-06-12 (~14:53Z, session
         e076ed30).  The owner session_id still reads the marker successfully on
         its own subsequent calls.  If the marker's session_id is None, it is
         bind-pending and is NEVER stale on session-id alone — the inject hook
         has not yet stamped it.

    Corrupt or unparseable marker files are treated as stale (DELETED, None
    returned) so a partial write from a crash never bricks subsequent sessions.
    Corruption deletion is retained (like path A) because a corrupt marker
    belongs to no readable session — there is no owner to protect.

    Args:
        now: epoch float for age comparison (injectable; defaults to time.time())
        session_id: caller's session id for session-binding staleness check;
                    None disables the session-id staleness path

    Returns:
        The marker dict if fresh and valid, otherwise None.
    """
    if now is None:
        now = time.time()
    # Read-only path: do NOT create the directory if it doesn't exist — a
    # missing dir simply means "no marker".
    marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
    if not marker_path.exists():
        return None

    # Load — treat any parse/OS error as stale (crashed write protection).
    try:
        raw = marker_path.read_text(encoding="utf-8")
        marker = json.loads(raw)
        if not isinstance(marker, dict):
            raise ValueError("marker root is not a dict")
    except (OSError, json.JSONDecodeError, ValueError):
        # Corrupt / unparseable — delete and return None.
        try:
            marker_path.unlink()
        except OSError:
            pass
        return None

    # --- Staleness path A: age > 24h ----------------------------------------
    started_at_str = marker.get("started_at", "")
    try:
        # Parse the ISO-8601 UTC 'Z' format we write.
        started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
        started_epoch = (
            started_dt - datetime.datetime(1970, 1, 1)
        ).total_seconds()
    except (ValueError, TypeError):
        # Unrecognized format — treat as stale.
        started_epoch = 0.0
    if now - started_epoch > _MARKER_STALE_SECONDS:
        try:
            marker_path.unlink()
        except OSError:
            pass
        return None

    # --- Staleness path B: session_id mismatch (NON-DESTRUCTIVE) --------------
    # Only fires when BOTH the caller supplies a session_id AND the marker has
    # a non-None session_id (bound, not bind-pending).
    #
    # Phase 8 WU-8.1: this path returns None WITHOUT deleting the marker.  A
    # non-owner session sees "no marker" but must not destroy the owner's run
    # state.  Unlike path A (age) and the corrupt-file path above, NO unlink()
    # happens here — the owning session's next read still succeeds.
    marker_session = marker.get("session_id")
    if session_id is not None and marker_session is not None:
        if session_id != marker_session:
            return None

    return marker


def marker_work_branch(
    now: float | None = None,
    session_id: str | None = None,
) -> str | None:
    """Return the run marker's ``work_branch`` field, or None.

    cycle-subagent-fabricates-policy-or-stray-branch Phase 2: the single read
    helper the ``--marker-work-branch`` CLI query and the write-time
    stray-branch hook share — branch identity is owned in ONE place (same
    contract as ``--marker-present`` owning presence). Returns None when:
      - no live (non-stale) marker is present, OR
      - the marker is a legacy one lacking the ``work_branch`` field, OR
      - the field is present but empty/falsy.
    A None result is the hook's fail-OPEN signal: with no known work branch
    there is nothing to enforce against. Never raises on a missing field
    (back-compat, like ``attended`` / ``per_feature_forward_cycles``).
    """
    marker = read_run_marker(now=now, session_id=session_id)
    if not isinstance(marker, dict):
        return None
    branch = marker.get("work_branch")
    if isinstance(branch, str) and branch:
        return branch
    return None


def bind_marker_session(session_id: str) -> bool:
    """Stamp the run marker with the given session_id if it is currently unbound.

    Called by the inject hook (lazy_inject.py) on the first firing for a new
    run: when the marker has ``session_id: None`` (bind-pending), this function
    atomically writes the provided session_id into the marker so subsequent hook
    firings (and guard calls) can use staleness path B (session-id mismatch
    cleanup) for proper isolation across runs.

    Contract:
      - If no valid marker exists → no-op, returns False.
      - If the marker already has a non-None session_id → no-op (idempotent),
        returns False.  The first hook firing wins; subsequent firings for the
        same session are consistent.
      - If the marker's session_id is None → stamp it atomically, returns True.

    The write uses _atomic_write (temp file + os.replace) to avoid partial
    writes under concurrent hook firings.

    Args:
        session_id: the Claude Code session id from the hook-input JSON.

    Returns:
        True if the marker was stamped (was unbound and is now bound); False
        otherwise (no marker, already bound, or write failed).
    """
    try:
        marker = read_run_marker()
        if marker is None:
            return False
        if marker.get("session_id") is not None:
            # Already bound — idempotent no-op.
            return False
        # Stamp the session_id.
        marker["session_id"] = session_id
        marker_path = claude_state_dir() / _MARKER_FILENAME
        _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail silently — a bind failure is non-fatal; the inject hook proceeds
        # and the marker simply remains unbound (staleness path B stays dormant).
        return False


def marker_owner_status(
    session_id: str,
    *,
    now: float | None = None,
) -> str:
    """Owner-side, NON-DESTRUCTIVE detect: distinguish "no run" from "wrong-stamped run".

    single-slot-marker-ownership-race-disarms-owning-run Phase 2 (Proven Finding
    #4(b)). The silent disarm exists because the OWNER reading ``None`` from
    ``read_run_marker(session_id=owner)`` (staleness path B) cannot tell:
      - "no run is live" (correct fast-path allow), from
      - "my run IS live but the slot was stamped with a foreign session".
    This helper makes the two DISTINGUISHABLE, returning one of:

      - ``"absent"``        — no live marker (missing / age-stale / corrupt). It
                              REUSES ``read_run_marker``'s age + corrupt rules
                              verbatim (by delegating to it with NO session_id,
                              so path B never fires here) — an age-stale or
                              corrupt marker IS deleted by that call, exactly as
                              ``read_run_marker`` would, which is correct: a
                              presumed-dead/unreadable marker has no owner to
                              protect.
      - ``"owned-by-me"``   — a live marker whose ``session_id`` is None
                              (bind-pending — the owner's, not yet stamped) OR
                              equals the caller.
      - ``"foreign-stamped"`` — a live marker whose NON-None ``session_id``
                              differs from the caller.

    HARD CONTRACT: this function is NON-DESTRUCTIVE on the ``foreign-stamped``
    case — it NEVER deletes a live marker on a session mismatch (deleting there
    re-introduces the 2026-06-12 ~14:53Z silent-disarm-by-delete that path B's
    non-destructive rule exists to avoid). The only deletions are the age/corrupt
    ones inherited from ``read_run_marker`` (a marker with no live owner).

    Args:
        session_id: the calling owner's session id (the expected owner on record).
        now: epoch float for age comparison (injectable; defaults to time.time()).

    Returns:
        "absent" | "owned-by-me" | "foreign-stamped".
    """
    # Delegate age/corrupt staleness to read_run_marker with NO session_id, so
    # path B (session mismatch) is DISABLED and we do the owner comparison here
    # non-destructively. An age-stale/corrupt/missing marker → None → "absent".
    marker = read_run_marker(now=now)
    if marker is None:
        return "absent"
    marker_session = marker.get("session_id")
    if marker_session is None or marker_session == session_id:
        return "owned-by-me"
    return "foreign-stamped"


def reassert_marker_owner(
    session_id: str,
    *,
    now: float | None = None,
) -> bool:
    """RE-ARM: re-claim a live, foreign-stamped marker slot for the calling owner.

    single-slot-marker-ownership-race-disarms-owning-run Phase 2 (Proven Finding
    #4(c)). The owner-side re-claim path: when ``marker_owner_status`` is
    ``foreign-stamped`` (a live marker whose slot holds a non-None session OTHER
    than the caller), atomically re-stamp the slot to ``session_id`` and return
    True. For ``absent`` or ``owned-by-me`` it is a no-op returning False
    (idempotent — a second call after a re-claim sees ``owned-by-me`` and
    no-ops).

    This is the ONLY sanctioned mutator of a foreign-stamped slot. It is exposed
    ONLY through the orchestrator-only ``--reassert-owner`` CLI action (guarded by
    ``refuse_if_cycle_active``): only the run's actual orchestrator (which holds
    the ``repo_root``-keyed state dir and its own session_id) re-claims its own
    run's guard.

    Args:
        session_id: the calling owner's session id to re-stamp into the slot.
        now: epoch float for age comparison (injectable; defaults to time.time()).

    Returns:
        True if the slot was foreign-stamped and is now re-claimed; False on an
        absent / owned-by-me marker, or any read/write failure (fail-safe no-op).
    """
    try:
        if marker_owner_status(session_id, now=now) != "foreign-stamped":
            return False
        # Re-read the live marker (NO session_id → no path-B disarm) and re-stamp.
        marker = read_run_marker(now=now)
        if marker is None:
            return False
        marker["session_id"] = session_id
        marker_path = claude_state_dir() / _MARKER_FILENAME
        _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-safe: a re-arm failure is non-fatal; the owner can retry. Never
        # raise into the CLI handler.
        return False


def delete_run_marker(clear_registry: bool = False) -> bool:
    """Delete the run marker file from the state dir.

    Called by both state scripts' ``--run-end`` flag and by every terminal path
    in the orchestrator SKILLs (the 1c.6 PushNotification enumeration doubles
    as the deletion checklist: all-features-complete, cloud/device-queue-exhausted,
    queue-missing, max-cycles, operator-chosen halt, script-error).
    (meta-cap was removed 2026-06-14 — meta_cycles is now uncapped.)

    Args:
        clear_registry: when True, also delete ``lazy-prompt-registry.json`` from
                        the state dir.  Pass ``True`` from the ``--run-end`` path
                        of both state scripts — the registry is run-scoped state and
                        must not bleed across runs.  Default False preserves the
                        existing behaviour for all other callers (terminal paths in
                        orchestrator skills that only need to retire the marker).

    Returns:
        True if the marker file existed and was deleted; False if it was already
        absent (idempotent — safe to call on every terminal path without checking
        first).
    """
    # Read-only directory probe — do not create the dir just to see it's empty.
    state_dir = claude_state_dir(create=False)
    marker_path = state_dir / _MARKER_FILENAME
    deleted = False
    if marker_path.exists():
        try:
            marker_path.unlink()
            deleted = True
        except OSError:
            pass
    if clear_registry:
        registry_path = state_dir / _REGISTRY_FILENAME
        if registry_path.exists():
            try:
                registry_path.unlink()
            except OSError:
                pass
    return deleted


# ---------------------------------------------------------------------------
# Cycle-subagent marker API (lazy-cycle-containment C1 / Phase 2)
#
# The cycle marker (`lazy-cycle-active.json`) is the SIBLING of the run marker
# (`lazy-run-marker.json`) in the same state dir (respecting LAZY_STATE_DIR).
# It says "a dispatched cycle subagent is currently executing" — the on/off
# switch the C3 refusals (Phase 3) and the C2 PreToolUse hook (Phase 4) key on.
# Script-owned: the orchestrator never hand-writes it; it issues
# `--cycle-begin`/`--cycle-end` around every Agent dispatch.
# ---------------------------------------------------------------------------

# Cycle-marker filename inside the state dir (sibling of _MARKER_FILENAME).
_CYCLE_MARKER_FILENAME = "lazy-cycle-active.json"


def resolve_cycle_worker_nonce(passed_nonce: str | None) -> str | None:
    """Resolve the nonce stamped onto a subagent-model cycle marker so the
    dispatch guard's workstation sub-subagent exemption can find it.

    dispatch-guard-denies-workstation-subsubagent-split (consumed-fence wiring
    fix, 2026-07-11): the guard's exemption keys its CONSUMED FENCE on the cycle
    marker's ``nonce`` (``emission_consumed_by_nonce(cycle["nonce"])`` at
    ``lazy_guard.py``). That precise nonce-exact fence only matches when the
    marker's nonce equals the cycle's REGISTERED emission nonce (a ``uuid4().hex``
    from ``register_emission``). The orchestrator, however, is permitted by the
    ``/lazy-batch`` SKILL (Step §1d "reuse the probe's ``cycle_prompt_ref``/
    registry nonce when present, **else any fresh hex**") to pass an arbitrary
    fresh hex for ``--cycle-begin --nonce``. A fresh hex is NOT a registered
    emission nonce, so the fence can never match it → the exemption is DEAD in
    production and every worker-composed sub-subagent dispatch (``/execute-plan``
    test-agent/impl-agent split, ``/spec-phases`` phase-author, …) is denied and
    booked as false hardening debt (hardening-log Rounds 9→13 were the pre-fix
    no-exemption era; this is the post-ship mis-wiring). The unit test masked it
    by hard-coding ``cycle.nonce == emission.nonce`` (``test_hooks.py``
    ``_arm_worker_in_flight``).

    Resolution rule (only the CALLER for a subagent-model cycle invokes this):
      - If ``passed_nonce`` is ALREADY a registered emission nonce, keep it — the
        orchestrator reused the registry/ref nonce (the design-intended path).
      - Otherwise (fresh hex) rebind to THIS cycle's worker emission: the NEWEST
        UNCONSUMED ``class == "cycle"`` registry entry. ``--emit-prompt``
        registers the cycle emission IMMEDIATELY before ``--cycle-begin`` and the
        worker dispatch (which consumes it) has not happened yet, so at write
        time the newest unconsumed cycle emission is unambiguously this cycle's.
        Binding the marker to it makes the precise fence fire when the worker
        dispatch later consumes that same emission — regardless of what
        ``--nonce`` the orchestrator chose.
      - If neither applies (no unconsumed cycle emission — a degraded / no-emit
        cycle), preserve ``passed_nonce`` unchanged (the fence simply will not
        fire — the safe pre-fix degradation).

    Security window is UNCHANGED: the marker is bound to an UNCONSUMED emission,
    so in the pre-dispatch window the fence still reads consumed=False (deny); it
    opens only after the guard-ALLOWed worker dispatch consumes the emission.
    The cycle marker ``nonce`` is read by EXACTLY ONE consumer (the guard fence),
    so this rebind has no other blast radius.

    FAIL-SAFE: any error returns ``passed_nonce`` unchanged (never rebinds to a
    wrong value on a registry read failure).
    """
    try:
        entries = _load_registry().get("entries", [])
        # Reused-nonce path: the orchestrator already passed a registered emission
        # nonce (consumed or not) — keep it (this is the design-intended wiring).
        for entry in entries:
            if entry.get("nonce") == passed_nonce:
                return passed_nonce
        # Fresh-hex path: rebind to this cycle's worker emission — the newest
        # UNCONSUMED cycle-class emission (iterate newest-first / reverse
        # insertion order, mirroring _find_entry_by_sha's newest-wins rule).
        for entry in reversed(entries):
            if entry.get("class") == "cycle" and not entry.get("consumed", False):
                return entry.get("nonce") or passed_nonce
        return passed_nonce
    except Exception:  # noqa: BLE001
        return passed_nonce


def write_cycle_marker(
    feature_id: str,
    nonce: str,
    *,
    kind: str = "real",
    session_id: str | None = None,
    run_started_at: str | None = None,
    begin_head_sha: str | None = None,
    sub_skill: str | None = None,
    sub_skill_args: str | None = None,
    subagent_model: bool | None = None,
    now: float | None = None,
) -> dict:
    """Write (or overwrite) the cycle-subagent marker to the state dir.

    Called by `--cycle-begin` immediately before every Agent dispatch.

    Fields written:
      - feature_id (str): the single feature this dispatch may touch (the C2
        hook's 2nd-feature tripwire compares staged paths against it).
      - nonce (str): the dispatch nonce.
      - kind (str): "real" (a real-skill cycle) | "meta" (input-audit,
        apply-resolution, recovery, hardening, coherence-recovery,
        needs-runtime-redispatch). Default "real".
      - started_at (str): ISO-8601 UTC timestamp ending in 'Z'.
      - session_id (str|None): the parent orchestrator session id, best-effort
        from the env (CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID) when not
        passed explicitly; None when unavailable.
      - commit_tally (int): starts at 0; the C2 hook (Phase 4) increments it on
        each allowed `git commit` for the commit-count backstop.
      - run_started_at (str|None): the owning run marker's ``started_at`` snapshot
        at --cycle-begin (the stable run identity). None when no run marker was
        present. Used by detect_cycle_bracket_friction (hardening-blind-to-
        process-friction Phase 2) to detect a torn cycle bracket — a dispatched
        cycle that ran --run-end / overwrote the run marker.
      - begin_head_sha (str|None): ``git rev-parse HEAD`` snapshot at --cycle-begin.
        None when not a git tree / degraded. Used to detect unexpected commits
        (HEAD advanced beyond the per-sub_skill budget by --cycle-end).
      - sub_skill (str|None): the dispatched sub_skill name (e.g. "execute-plan").
        None for callers that omit it. detect_cycle_bracket_friction selects the
        per-sub_skill commit budget from this — WITHOUT it the detector falls back
        to the conservative default budget (1) and false-positives on a normal
        multi-commit cycle (e.g. execute-plan's test+impl commits, budget 3).
      - sub_skill_args (str|None): the dispatched sub_skill_args (for an
        execute-plan cycle this is the PLAN PART path). None for callers that omit
        it. cycle_end_friction_check uses it to read the plan's declared phase
        count and SCALE the execute-plan commit budget (one commit per phase is
        the normal /execute-plan cadence — a 6-phase plan legitimately makes ~6
        commits, which the fixed budget of 3 false-positived as unexpected-commits;
        hardening Round 20 D2). Additive (default None) → legacy markers degrade to
        the fixed per-sub_skill budget, never a crash.
      - subagent_model (bool): whether the dispatched sub_skill's SKILL.md
        frontmatter declares ``subagent-model: true`` (see
        skill_declares_subagent_model). Copied here at --cycle-begin so the
        dispatch guard's workstation sub-subagent exemption reads a marker
        field, never SKILL.md itself (dispatch-guard-denies-workstation-
        subsubagent-split, decision 4). Callers may pass an explicit bool to
        override; the default None computes it from the sub_skill, using the
        live run marker's repo_root (best-effort) for the repo-scoped lookup.
        Additive — legacy markers without the field read as falsy (no
        exemption), never a crash.

    Self-healing staleness: if a marker already EXISTS (a prior dispatch crashed
    without `--cycle-end`), it is OVERWRITTEN and the event logged. The
    orchestrator is single-threaded — only one dispatch is ever in flight — so
    overwrite-and-log is the correct recovery, never a hard error.

    Args:
        feature_id: the feature this dispatch is scoped to.
        nonce: the dispatch nonce.
        kind: "real" | "meta" (default "real").
        session_id: parent session id; None → best-effort env lookup.
        now: epoch float for started_at (injectable for tests; defaults to
             time.time()).

    Returns:
        The marker dict that was written.
    """
    if now is None:
        now = time.time()
    if session_id is None:
        session_id = (
            os.environ.get("CLAUDE_SESSION_ID")
            or os.environ.get("CLAUDE_CODE_SESSION_ID")
        )
    # decision 4: stamp the sub_skill's declared sub-subagent capability onto
    # the marker (explicit override wins; None → compute). The run marker's
    # repo_root feeds the repo-scoped SKILL.md lookup; every read is
    # best-effort and the helper is fail-closed, so a degraded read stamps
    # False (no exemption) and never blocks the marker write.
    if subagent_model is None:
        _sm_repo_root = None
        try:
            _sm_repo_root = (read_run_marker() or {}).get("repo_root")
        except Exception:  # noqa: BLE001
            _sm_repo_root = None
        subagent_model = skill_declares_subagent_model(
            sub_skill, repo_root=_sm_repo_root
        )
    # Normalize to a bool once (an explicit caller may pass any truthy/falsy).
    subagent_model = bool(subagent_model)
    # consumed-fence wiring fix (dispatch-guard-denies-workstation-subsubagent-
    # split, 2026-07-11): for a subagent-model cycle, rebind the marker's nonce
    # to this cycle's registered worker emission so the guard's exemption fence
    # (emission_consumed_by_nonce(cycle["nonce"])) can find it even when the
    # orchestrator passed a fresh, unregistered hex for --cycle-begin --nonce.
    # See resolve_cycle_worker_nonce for the full rationale + security argument.
    # Scoped to subagent_model cycles so meta/non-exempt cycles keep their passed
    # nonce byte-identically (zero behavior change off the exemption path).
    if subagent_model:
        nonce = resolve_cycle_worker_nonce(nonce)
    state_dir = claude_state_dir()
    marker_path = state_dir / _CYCLE_MARKER_FILENAME

    # Self-healing staleness: an existing marker means a prior dispatch never
    # cleared — overwrite it and log the event (single-threaded orchestrator).
    if marker_path.exists():
        prior_id = None
        try:
            prior = json.loads(marker_path.read_text(encoding="utf-8"))
            if isinstance(prior, dict):
                prior_id = prior.get("feature_id")
        except (OSError, json.JSONDecodeError):
            prior_id = "<unreadable>"
        _diag(
            f"cycle marker overwrite (stale prior dispatch never --cycle-end'd): "
            f"prior feature_id={prior_id!r} → new feature_id={feature_id!r}"
        )

    # Use fromtimestamp(tz=utc) — the deprecated utcfromtimestamp() warns in
    # Python ≥3.12 (mirrors write_run_marker's started_at formatting).
    started_at = (
        datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    )
    marker = {
        "feature_id": feature_id,
        "nonce": nonce,
        "kind": kind,
        "started_at": started_at,
        "session_id": session_id,
        "commit_tally": 0,
        # hardening-blind-to-process-friction Phase 2: additive run-identity +
        # HEAD snapshot (default None so existing 6-field callers/fixtures are
        # unbroken). --cycle-begin populates these.
        "run_started_at": run_started_at,
        "begin_head_sha": begin_head_sha,
        # hardening-blind-to-process-friction (false-positive fix): the dispatched
        # sub_skill, so cycle_end_friction_check can recover the correct per-sub_skill
        # commit budget instead of forcing the conservative default. Additive
        # (default None) → legacy markers/fixtures degrade to the default budget,
        # never a crash.
        "sub_skill": sub_skill,
        # hardening Round 20 (D2): the dispatched sub_skill_args (plan part path for
        # an execute-plan cycle) so cycle_end_friction_check can scale the
        # execute-plan commit budget by the plan's declared phase count. Additive
        # (default None) → legacy markers degrade to the fixed per-sub_skill budget.
        "sub_skill_args": sub_skill_args,
        # decision 4 (dispatch-guard-denies-workstation-subsubagent-split): the
        # sub_skill's declared sub-subagent capability, read by the guard's
        # workstation exemption. bool — never None (normalized above).
        "subagent_model": subagent_model,
    }
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def read_cycle_marker() -> dict | None:
    """Read the cycle-subagent marker from the state dir, or None if absent.

    This is the single predicate the C3 refusals (Phase 3) and the C2 hook
    fast-path (Phase 4) both consult. Read-only: never creates the state dir.
    A corrupt/unparseable marker reads as None (never bricks a caller) — the
    C2 hook fast-path uses a bare `test -f`, so the worst case of a corrupt
    marker is that the script-side refusals treat it as absent while the hook
    still denies; the orchestrator's next `--cycle-begin`/`--cycle-end`
    rewrites/clears it.

    Returns:
        The parsed marker dict if present and valid, otherwise None.
    """
    marker_path = claude_state_dir(create=False) / _CYCLE_MARKER_FILENAME
    if not marker_path.exists():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            return None
        return marker
    except (OSError, json.JSONDecodeError):
        return None


def clear_cycle_marker() -> bool:
    """Delete the cycle-subagent marker. Idempotent.

    Called by `--cycle-end` after every Agent return (success, halt, error).
    A missing marker is a no-op: returns False, raises nothing, exits cleanly.

    Returns:
        True if the marker existed and was deleted; False if already absent.
    """
    marker_path = claude_state_dir(create=False) / _CYCLE_MARKER_FILENAME
    if not marker_path.exists():
        return False
    try:
        marker_path.unlink()
        return True
    except OSError:
        return False


# Slack added on top of the plan's phase count for a phase-scaled execute-plan
# budget (hardening Round 20 D2): /execute-plan commits once per phase, but a phase
# may split into a test commit + an impl commit (TDD cadence), so allow a small
# constant cushion above the phase count before a cycle is deemed a runaway.
_EXECUTE_PLAN_PHASE_BUDGET_SLACK = 2

# Deterministic BOOKEND-cadence commits that EVERY /execute-plan cycle makes but
# the per-WU-checkbox / phase `scale_count` structurally OMITS (hardening Round 46,
# 2026-06-30). The execute-plan SKILL commits a plan STATUS FLIP at BOTH ends of a
# cycle — `chore(<id>): mark plan In-progress` at the start (SKILL Step 4e / :296)
# and `chore/docs(<id>): mark plan part N Complete` + PHASES/spin-off reconcile at
# the end (SKILL Step 4f / :105, :310) — plus an occasional in-cycle `revert(...)`
# self-correction. None of these are per-WU work units, so `scale_count` (= max of
# phase count and per-WU checkbox count) never counts them; the Round-20 SLACK of 2
# was sized for the WITHIN-phase test+impl split, NOT the two out-of-band bookend
# commits. When a plan's authored WU commits land close to its declared WU count
# AND a bookend/revert is present, the bookends push the AUTHORED (merge-excluded,
# Round 42) count past `scale_count + slack`, false-positiving a clean cycle as a
# runaway.
#
# Concrete recurrence (Round 46, AlgoBooth bug `audio-engine-clippy-warnings-fail-
# rust-gate`, Step 7a execute-plan, begin_head_sha=e01a97dd6685): the plan declares
# `phases: [1]` and 4 per-WU checkboxes → `scale_count = max(1, 4) = 4`, budget
# `4 + slack 2 = 6`. The cycle authored 7 non-merge commits — begin-chore
# `ba6049ce5 mark plan In-progress`, WU commits `5f90e4e80`/`0b1477faa`/`daef5aadd`
# (WU-1/2/3+4) + `20870de77` (feature-gated lint fix), an in-cycle
# `0325bb91d revert(...): un-commit accidentally-regenerated golden JSONs`, and the
# end reconcile `88ca68794 docs(...): reconcile — plan Complete, SPEC In-progress,
# spin-offs`. All 7 are legitimate; NONE are merges (`git rev-list --count
# --no-merges` = 7, so Round 42's merge exclusion does not help). The overflow is
# exactly the two structural bookends (In-progress flip + Complete reconcile) the
# WU budget never modeled — 7 = 4 WU-ish + 1 extra fix + 1 revert + ... but the
# load-bearing 2 that push it over `scale_count(4)+slack(2)=6` are the bookends.
#
# Budgeting the two deterministic bookends explicitly closes this: budget becomes
# `scale_count + slack + bookend`. This is a budget-DENOMINATOR structural fix (the
# same class as the Round-20 slack), narrowly scoped to execute-plan — it does NOT
# touch the friction threshold or the runaway ceiling for any other skill, and a
# genuine runaway (authored commits beyond WUs + slack + the 2 bookends) STILL trips.
_EXECUTE_PLAN_BOOKEND_COMMITS = 2


def _execute_plan_commit_budget(
    sub_skill: str | None, sub_skill_args: str | None
) -> int | None:
    """Work-scaled commit budget for an execute-plan cycle (hardening Round 20 D2;
    WU-scaling follow-up 2026-06-16).

    /execute-plan commits once per WORK UNIT — the per-WU ``tick the box + commit``
    cadence is the dominant signal, not the phase count. Round 20 scaled the budget
    by ``phase_count + slack``, but a WU-dense plan part (e.g. 5 WUs spread across
    2 phases) legitimately makes ~5 commits, which a phase-only budget of
    ``2 + slack = 4`` under-counts and false-positives as ``unexpected-commits``
    (the 2026-06-16 cycle-subagent part-1 recurrence: 5 commits vs a phase-derived
    budget of 4). This derives the budget from the GREATER of the dispatched plan
    part's declared phase count (``phases:`` frontmatter) and its parseable per-WU
    checkbox count (``- [ ] WU-N`` rows, write-plan ISSUE-6), plus a small slack —
    so a legacy phase-only plan and an ISSUE-6 per-WU plan both get an honest
    ceiling while a genuine runaway (commits beyond the work the plan declares)
    still trips.

    Returns the scaled budget, or ``None`` when it cannot be computed — for ANY of:
    a non-execute-plan sub_skill, a missing/blank sub_skill_args, an unreadable
    plan file, or a plan with NEITHER a parseable ``phases:`` field NOR any per-WU
    checkboxes. A ``None`` return makes ``detect_cycle_bracket_friction`` fall back
    to the fixed table budget, so the worst case is the pre-Round-20 behavior —
    never a false negative, never a crash.

    The sub_skill_args may carry trailing flags (e.g. ``"<plan>.md --batch"``);
    only the leading whitespace-delimited token is treated as the plan path
    (mirrors the plan-arg extraction already used in the probe-enrichment path).
    """
    if sub_skill != "execute-plan":
        return None
    if not sub_skill_args:
        return None
    plan_token = str(sub_skill_args).split()[0] if str(sub_skill_args).split() else ""
    if not plan_token:
        return None
    plan_path = Path(plan_token)
    try:
        phase_set = _plan_phase_set(plan_path)
    except Exception:  # noqa: BLE001
        phase_set = set()
    try:
        unchecked_wus, checked_wus = _plan_wu_checkbox_counts(
            plan_path.read_text(encoding="utf-8")
        )
    except Exception:  # noqa: BLE001
        unchecked_wus, checked_wus = 0, 0
    # Commits scale with WORK UNITS, so take the greater of the phase count and the
    # total (checked + unchecked) per-WU checkbox count. Either signal alone may be
    # absent (a legacy plan with no per-WU rows; an unusual plan with no phases:
    # field) — using the max means whichever the plan actually declares governs.
    scale_count = max(len(phase_set), unchecked_wus + checked_wus)
    if scale_count <= 0:
        return None
    # scale_count models per-WU authored commits; slack covers the within-phase
    # test+impl split; bookend covers the two deterministic out-of-band status-flip
    # commits (In-progress at start, Complete-reconcile at end) that EVERY cycle
    # makes but scale_count never counts (Round 46). A genuine runaway still trips.
    return scale_count + _EXECUTE_PLAN_PHASE_BUDGET_SLACK + _EXECUTE_PLAN_BOOKEND_COMMITS


def detect_cycle_bracket_friction(
    marker: dict,
    current_run_started_at: str | None,
    current_head_sha: str | None,
    sub_skill: str | None,
    *,
    commits_since: int | None = None,
    budget_override: int | None = None,
    current_branch: str | None = None,
    expected_work_branch: str | None = None,
    repo_root: "str | Path | None" = None,
    now: float | None = None,
) -> dict | None:
    """Detect process-friction at --cycle-end: a torn cycle bracket or unexpected
    commits (hardening-blind-to-process-friction Phase 2, Locked Decision D1).

    Almost pure: every signal is computed from caller-supplied values EXCEPT the
    registry-derived commit-budget membership test (branch 3 below), which reads
    the dispatched skill's own SKILL.md frontmatter via ``skill_declares_multi_commit``
    (adhoc-derive-multi-commit-budget-from-dispatch-sites, 2026-07-12) — the same
    class of deterministic, git-committed-file read ``skill_declares_subagent_model``
    already performs elsewhere in this module. The caller (--cycle-end) supplies
    every other live value: the cycle marker as snapshotted at --cycle-begin, the
    CURRENT run identity and HEAD sha resolved fresh at --cycle-end, the dispatched
    sub_skill, and the number of commits HEAD advanced since
    ``marker['begin_head_sha']``.

    Two deterministic on-disk signals (D1):
      (a) cycle-bracket-break — the run identity present at --cycle-begin
          (``marker['run_started_at']``) is absent or CHANGED at --cycle-end
          (the dispatched cycle ran --run-end, started a new run, or overwrote the
          run marker). A null begin-snapshot disables this signal (degraded
          --cycle-begin had no run marker to snapshot → no false positive).
      (b) unexpected-commits — HEAD advanced by more than the conservative
          per-sub_skill budget beyond ``marker['begin_head_sha']``. A null
          begin-snapshot or a null/None ``commits_since`` disables this signal.
          EXEMPT when ``marker['kind'] == 'meta'``: a meta cycle is an
          orchestrator-driven remediation dispatch (hardening / input-audit /
          recovery / apply-resolution) that legitimately commits an unbounded
          number of times and carries no sub_skill to budget — signal (b) is
          skipped entirely for it (signal (a) still applies). ALSO exempt when a
          NON-meta cycle carries a falsy ``sub_skill`` (the marker was written by a
          --cycle-begin that omitted --sub-skill): the commit budget is
          INDETERMINATE without a dispatch identity, so applying the single-commit
          default would false-positive every legitimately multi-commit real cycle —
          signal (b) is disabled (fail-open), signals (a)/(a.5) still fire.

    Args:
        marker: the cycle marker dict from read_cycle_marker() (snapshotted at
            --cycle-begin). May lack the additive fields (legacy/partial) → those
            signals degrade to off.
        current_run_started_at: the run marker's ``started_at`` resolved NOW, or
            None when no run marker is present.
        current_head_sha: ``git rev-parse HEAD`` resolved NOW, or None (degraded).
        sub_skill: the dispatched sub_skill name (selects the commit budget).
        commits_since: number of commits HEAD advanced since
            ``marker['begin_head_sha']`` (caller computes via ``git rev-list
            --count begin..HEAD``); None/degraded disables signal (b).
        budget_override: an explicit commit budget that SUPERSEDES the per-sub_skill
            table lookup when provided (hardening Round 20 D2). The caller
            (cycle_end_friction_check) computes this for an execute-plan cycle by
            reading the plan part's declared phase count, so a normal one-commit-
            per-phase /execute-plan cadence (e.g. a 6-phase plan → ~6 commits) does
            NOT false-positive against the fixed table budget of 3. None → fall back
            to the per-sub_skill table (legacy behavior, never a crash).
        now: unused placeholder for caller symmetry / future timing fields.

    Returns:
        A friction descriptor ``{"reason": <str>, "detail": <str>, ...}`` on the
        FIRST signal that trips (bracket-break checked before commits), or None
        when the bracket is clean / inputs are degraded.
    """
    if not isinstance(marker, dict):
        return None
    begin_run_started_at = marker.get("run_started_at")
    begin_head_sha = marker.get("begin_head_sha")

    # --- Signal (a): cycle-bracket-break ------------------------------------
    # Only meaningful when --cycle-begin actually snapshotted a run identity.
    # A null begin snapshot means there was no run marker to compare against —
    # degrade to off (never a false positive).
    if begin_run_started_at is not None:
        if current_run_started_at != begin_run_started_at:
            absent = current_run_started_at is None
            detail = (
                "run marker absent at --cycle-end (present at --cycle-begin: "
                f"started_at={begin_run_started_at!r})"
                if absent
                else (
                    "run identity changed mid-cycle: begin started_at="
                    f"{begin_run_started_at!r} != end started_at="
                    f"{current_run_started_at!r}"
                )
            )
            return {
                "reason": "cycle-bracket-break",
                "detail": detail,
                "sub_skill": sub_skill,
            }

    # --- Signal (a.5): branch-divergence (harden Round 43, 2026-06-29) -------
    # A cycle that ends on a branch OTHER than the run's work_branch strands every
    # commit/sentinel it wrote where the state scripts (which read the work_branch)
    # cannot see them. The cycle-base-prompt R10 hard-contract already forbids
    # `git checkout -b` / `git switch -c` / `git branch <new>` mid-cycle, but that
    # rule relies on SUBAGENT COMPLIANCE — and a real mcp-test cycle violated it
    # (created fix/<...>, committed the fix there, and reported success WITHOUT the
    # mandated STOP), so the divergence was caught only by manual orchestrator
    # reconciliation (ff-merge to work branch + branch delete). This signal makes the
    # violation SELF-ANNOUNCING (a kind: process-friction ledger entry → pending
    # hardening), exactly like unexpected-commits — turning a silent, manually-caught
    # integrity break into a routed one. It applies to ALL cycles (meta INCLUDED — a
    # wrong branch is always integrity-breaking), so it is checked BEFORE the
    # meta-cycle exemption below. Degrades to off when either branch is unknown
    # (legacy run marker without work_branch, a detached HEAD reading "HEAD", or a
    # degraded git read) → never a false positive.
    if (
        current_branch
        and current_branch != "HEAD"
        and expected_work_branch
        and current_branch != expected_work_branch
    ):
        return {
            "reason": "branch-divergence",
            "detail": (
                f"cycle ended on branch {current_branch!r} but the run's "
                f"work_branch is {expected_work_branch!r} — commits/sentinels this "
                f"cycle wrote are stranded off the work branch (R10 work-branch-only "
                f"hard-contract violated; reconcile by ff-merging onto "
                f"{expected_work_branch!r} and deleting the stray branch)"
            ),
            "sub_skill": sub_skill,
        }

    # --- Signal (b): unexpected-commits -------------------------------------
    # Requires a known begin HEAD snapshot AND a known commit count.
    #
    # META-CYCLE EXEMPTION (hardening-blind-to-process-friction, 2026-06-16 D-A):
    # a cycle whose marker kind=="meta" (hardening / input-audit / recovery /
    # apply-resolution / coherence-recovery / needs-runtime-redispatch) is an
    # ORCHESTRATOR-DRIVEN remediation dispatch, NOT a runaway real-skill subagent.
    # A meta cycle legitimately commits an UNBOUNDED number of times (e.g. a
    # hardening cycle commits a script fix AND a hardening-log append; an
    # apply-resolution cycle commits each resolved sentinel) and carries
    # sub_skill=None (no work-skill is dispatched), so the per-sub_skill budget
    # defaults to 1 and 2+ legit commits tripped `unexpected-commits` on EVERY
    # meta cycle — a self-perpetuating loop where each hardening cycle re-tripped
    # at its own --cycle-end (Rounds 16/17 chased the symptom via the pseudo-skill
    # budget rows + mandatory --sub-skill prose, but a meta cycle has no sub_skill
    # to budget; the structural fix is to exempt kind==meta from signal (b)).
    # Signal (a) bracket-break is NOT exempted — a meta cycle that tears the run
    # bracket (overwrites/ends the run marker, e.g. the D-B clobber) is genuine
    # corruption and must still self-announce.  The exemption is read from the
    # marker dict the caller already passes (cycle_end_friction_check threads the
    # live marker), so it is effective for the meta hardening cycle running THIS
    # very dispatch — it cannot re-trip at its own --cycle-end.
    if marker.get("kind") == "meta":
        return None
    if begin_head_sha is not None and commits_since is not None:
        # hardening Round 20 (D2): an explicit budget_override (e.g. a phase-scaled
        # execute-plan budget the caller derived from the plan frontmatter)
        # supersedes the fixed per-sub_skill table. Only a POSITIVE override is
        # honored — a None/degraded computation falls back to the table so the
        # signal never accidentally disables.
        if isinstance(budget_override, int) and budget_override > 0:
            budget = budget_override
        elif not (sub_skill or "").strip():
            # BUDGET-INDETERMINATE INPUT (adhoc-derive-multi-commit-budget…,
            # harden 2026-07-04): a NON-meta cycle whose sub_skill was never
            # recorded (the marker was written by a --cycle-begin that omitted
            # --sub-skill) has NO derivable commit budget — the dispatch identity
            # that selects the multi-commit ceiling is unknown, so the registry
            # lookup below would fall to the single-commit default and
            # false-positive EVERY legitimately multi-commit real cycle. That is
            # the observed friction: an /execute-plan cycle whose --cycle-begin
            # recorded sub_skill=None landed 3 sanctioned per-WU commits and
            # tripped budget=1 (a FALSE unexpected-commits). Disable signal (b)
            # for this degraded input — the SAME fail-open posture the meta
            # exemption and the null-HEAD / null-commits guards already take ("a
            # degraded input yields None signals, never a false positive"). The
            # integrity signals (a) bracket-break and (a.5) branch-divergence were
            # evaluated ABOVE and are sub_skill-independent, so they still fire; a
            # genuine runaway with a RECORDED sub_skill is unaffected (its budget is
            # derivable). Write-side complement: the /lazy-batch(-bug-batch) prose
            # MANDATES --sub-skill on every real --cycle-begin, so this input never
            # occurs for a sanctioned dispatch — this guard is the read-side
            # backstop that stops the mis-recorded marker from manufacturing debt.
            return None
        else:
            # Branch (3): DERIVE the budget from skill_declares_multi_commit — a
            # skill-declared `commit-cadence: multi` frontmatter flag (or pseudo-
            # skill dict membership) ⇒ the multi-commit ceiling, else the
            # single-commit default. No hand-maintained literal registry to keep in
            # sync (closes the recurring missing-row defect class:
            # adhoc-derive-multi-commit-budget-from-dispatch-sites). A flagged
            # skill's ceiling is the uniform `_CYCLE_COMMIT_MULTI` UNLESS it
            # declares a higher worst-case cadence in `_MULTI_COMMIT_CEILING_OVERRIDE`
            # (the MAGNITUDE dimension — e.g. mcp-test's self-heal + 2-part reconcile
            # + sentinel correction = 4); an unflagged skill always gets the default.
            # `_CYCLE_COMMIT_NOISE_ALLOWANCE` (adhoc-align-cycle-commit-count-with-
            # budget-population) then adds ONE shared, skill-agnostic cushion on top
            # of EITHER ceiling — the population-alignment fix — leaving
            # execute-plan's own budget_override model (handled above) untouched.
            ss = sub_skill or ""
            base_budget = (
                _MULTI_COMMIT_CEILING_OVERRIDE.get(ss, _CYCLE_COMMIT_MULTI)
                if skill_declares_multi_commit(ss, repo_root=repo_root)
                else _CYCLE_COMMIT_BUDGET_DEFAULT
            )
            budget = base_budget + _CYCLE_COMMIT_NOISE_ALLOWANCE
        if commits_since > budget:
            return {
                "reason": "unexpected-commits",
                "detail": (
                    f"HEAD advanced {commits_since} commits since --cycle-begin "
                    f"(begin_head_sha={(begin_head_sha or '')[:12]}, "
                    f"sub_skill={sub_skill!r}, budget={budget})"
                ),
                "sub_skill": sub_skill,
                "commits_since": commits_since,
            }

    return None


def head_sha_snapshot(repo_root: Path | None = None) -> str | None:
    """Best-effort ``git rev-parse HEAD`` against repo_root (cwd default).

    Returns the full HEAD sha string, or None when not a git tree / git fails /
    any OS-level error — callers treat None as a degraded snapshot (the
    unexpected-commits signal disables, never a false positive). Used by
    --cycle-begin to snapshot the begin HEAD into the cycle marker.
    """
    root = repo_root or Path.cwd()
    try:
        proc = _git(root, "rev-parse", "HEAD")
        if proc.returncode == 0:
            return (proc.stdout or "").strip() or None
    except Exception:  # noqa: BLE001
        pass
    return None


def current_branch_snapshot(repo_root: Path | None = None) -> str | None:
    """Best-effort ``git rev-parse --abbrev-ref HEAD`` against repo_root (cwd default).

    Returns the current branch NAME, or None when not a git tree / git fails / the
    output is empty / HEAD is detached (the literal ``"HEAD"``). Callers treat None
    as a degraded snapshot (the branch-divergence signal disables — never a false
    positive). Distinct from ``_emit_work_branch`` (the prompt-token resolver), which
    returns the human fallback string ``"the current branch"`` on failure — a value
    that would FALSE-trip an equality comparison; the friction detector needs a clean
    None instead, so it uses this helper. Used by --cycle-end to resolve the live
    branch for the branch-divergence signal (harden Round 43).
    """
    root = repo_root or Path.cwd()
    try:
        proc = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if proc.returncode == 0:
            branch = (proc.stdout or "").strip()
            if branch and branch != "HEAD":
                return branch
    except Exception:  # noqa: BLE001
        pass
    return None


def _count_authored_commits_since(
    repo_root: Path, begin_head_sha: str | None
) -> int | None:
    """Count AUTHORED commits HEAD advanced since ``begin_head_sha``, EXCLUDING
    merge commits (hardening Round 42, 2026-06-29).

    The ``unexpected-commits`` budget is a model of *authored work-unit commits*:
    the budget side (``_execute_plan_commit_budget``) derives the ceiling from the
    plan part's per-WU checkbox / phase count, i.e. the units of work the cycle is
    expected to author. The count side MUST measure the same thing — authored
    commits — or the comparison is apples-to-oranges. A bare
    ``git rev-list --count <begin>..HEAD`` ALSO counts merge commits, which are
    branch-integration artifacts, not authored work units: a sibling PR merged into
    ``main`` during the cycle window (or any out-of-band merge) inflates the count by
    ≥1 with ZERO corresponding work, false-positiving an otherwise-clean cycle as a
    runaway.

    Concrete recurrence (Round 42, AlgoBooth ``algorithmic-fill-buffer``, Step 7a
    execute-plan): the dispatched part-3 plan declared 5 WUs (budget = 5 + slack 2 =
    7), and the cycle authored exactly 5 WU commits — but ``begin..HEAD`` also spanned
    a merge commit (``d7b867a81`` — PR #107 pre-release-roadmap branch integration)
    plus 2 unrelated ``docs:`` roadmap/queue commits that landed on ``main`` during
    the window, so the bare count was 8 > 7 and tripped ``unexpected-commits``.
    ``--no-merges`` brings the count to exactly 7 (≤ budget) — the merge commit was
    the load-bearing overflow.

    ``--no-merges`` is the structural fix (a merge commit is NEVER an authored
    work unit, for ANY sub_skill). It is deliberately NARROW: the two unrelated
    non-merge ``docs:`` commits are still counted — filtering those would require
    per-cycle path scoping and risk masking a real runaway (false negative). Excluding
    only merges removes a category error without lowering the runaway ceiling: a
    genuine runaway authoring commits beyond budget STILL trips.

    Returns the merge-excluded count, or ``None`` on a degraded git read / no
    begin sha (caller disables signal (b) on None — never a false positive,
    never a crash). Mirrors the pre-existing best-effort contract of the inline
    count it replaces.
    """
    if not begin_head_sha:
        return None
    try:
        count_proc = _git(
            repo_root, "rev-list", "--count", "--no-merges",
            f"{begin_head_sha}..HEAD",
        )
        if count_proc.returncode != 0:
            return None
        return int((count_proc.stdout or "").strip() or "0")
    except Exception:  # noqa: BLE001  (incl. ValueError from int())
        return None


def cycle_end_friction_check(repo_root: Path | None = None) -> dict | None:
    """--cycle-end I/O wiring (hardening-blind-to-process-friction Phase 2 / D1).

    Called by the ``--cycle-end`` handler in BOTH state machines (lazy-state.py
    and bug-state.py) BEFORE it clears the cycle marker. It:
      1. reads the cycle marker (the --cycle-begin snapshot); a missing/partial
         marker → None no-op (the bracket was never armed or already cleared);
      2. resolves the CURRENT run identity (``read_run_marker().started_at``,
         None when no run marker is live) and the CURRENT HEAD sha;
      3. computes how many AUTHORED (merge-excluded) commits HEAD advanced since
         the snapshotted ``begin_head_sha``
         (``git rev-list --count --no-merges <begin>..HEAD`` via
         ``_count_authored_commits_since`` — Round 42: a merge commit is a
         branch-integration artifact, not authored work, so it must not count
         toward the per-cycle commit budget);
      4. calls the pure detect_cycle_bracket_friction(...);
      5. on a non-None descriptor, appends a kind: process-friction entry to the
         deny ledger via append_friction_ledger_entry(...).

    Every git/marker read is best-effort: a degraded input (no git tree, no run
    marker, unreadable marker) yields None signals, never a false positive and
    never a crash — the --cycle-end clear must always proceed.

    Args:
        repo_root: the repo to resolve HEAD / commit-count against. Defaults to
            cwd. Degrades to no-commit-signal when not a git tree.

    Returns:
        The friction descriptor that was logged, or None when the bracket was
        clean / inputs were degraded / no marker was present.
    """
    marker = read_cycle_marker()
    if not isinstance(marker, dict):
        return None

    # (2) current run identity — None when no run marker is live (the torn-bracket
    # signal). read_run_marker swallows its own errors and returns None.
    try:
        live_run = read_run_marker()
    except Exception:  # noqa: BLE001
        live_run = None
    current_run_started_at = (live_run or {}).get("started_at")

    # (2/3) current HEAD + commits-since-begin — best-effort git reads.
    # commits_since EXCLUDES merge commits (Round 42): the budget side models
    # authored work-unit commits, so the count side must too — a merge commit (e.g. a
    # sibling PR integrated into main during the cycle window) is a branch-integration
    # artifact with no authored work and must not count toward the runaway budget.
    # _count_authored_commits_since carries the full provenance + best-effort contract.
    root = (repo_root or Path.cwd())
    begin_head_sha = marker.get("begin_head_sha")
    current_head_sha = head_sha_snapshot(root)
    commits_since: int | None = _count_authored_commits_since(root, begin_head_sha)

    # (4) recover the dispatched sub_skill from the marker (--cycle-begin persists
    # it) so the unexpected-commits detector selects the CORRECT per-sub_skill
    # commit budget. A legacy/partial marker without the field reads None → the
    # detector falls back to the conservative default budget (never a crash). The
    # bracket-break signal is sub_skill-independent and was always fully covered;
    # this fix stops the unexpected-commits signal from false-positiving on a
    # normal multi-commit cycle (e.g. execute-plan test+impl, budget 3) that the
    # forced sub_skill=None previously squeezed under the default budget of 1.
    marker_sub_skill = marker.get("sub_skill")

    # hardening Round 20 (D2): for an execute-plan cycle, scale the commit budget
    # by the plan part's declared phase count. /execute-plan commits once per phase
    # (the standard per-phase gate+commit cadence), so a legitimate N-phase single-
    # part plan makes ~N commits — which the fixed table budget of 3 false-positived
    # as unexpected-commits on any plan with 4+ phases. The plan part path is the
    # dispatched sub_skill_args (lazy-state.py routes execute-plan with
    # sub_skill_args=str(plan)). Read the phase count via the existing
    # _plan_phase_set helper and allow one commit per phase plus a small slack for
    # the test+impl split within a phase. A genuine runaway (many commits beyond the
    # plan's phase count) still trips. Best-effort: an unreadable plan / no phases:
    # field / non-execute-plan cycle → None → the detector falls back to the fixed
    # per-sub_skill table (never a false NEGATIVE, never a crash).
    budget_override = _execute_plan_commit_budget(marker_sub_skill, marker.get("sub_skill_args"))

    # (4b) branch-divergence inputs (harden Round 43): the live branch at --cycle-end
    # vs the run's work_branch. Both best-effort — a None on either degrades the
    # signal to off (never a false positive). expected_work_branch comes from the
    # LIVE run marker (read in step 2); a legacy run marker without the field → None.
    current_branch = current_branch_snapshot(root)
    expected_work_branch = (live_run or {}).get("work_branch")

    descriptor = detect_cycle_bracket_friction(
        marker,
        current_run_started_at=current_run_started_at,
        current_head_sha=current_head_sha,
        sub_skill=marker_sub_skill,
        commits_since=commits_since,
        budget_override=budget_override,
        current_branch=current_branch,
        expected_work_branch=expected_work_branch,
        repo_root=root,
    )

    # (5) log the friction as hardening debt (fail-open).
    if descriptor is not None:
        append_friction_ledger_entry(
            descriptor.get("reason", ""),
            descriptor.get("detail", ""),
        )
    return descriptor


# ---------------------------------------------------------------------------
# Refuse-by-construction (lazy-cycle-containment C3 / Phase 3; agent_id-aware
# per hardening-blind-to-process-friction Phase 1 / D4)
#
# The orchestrator-only state-script operations REFUSE for a subagent caller —
# the belt-and-suspenders backstop if the C2 hook (lazy-cycle-containment.sh) is
# disabled or bypassed. The subagent-vs-main-thread distinction is established
# in PRIORITY ORDER (D4):
#
#   1. LAZY_ORCHESTRATOR truthy in the env → NEVER refuse (the main-thread
#      orchestrator asserts its identity). This makes the orchestrator
#      STRUCTURALLY IMMUNE to a stale/lingering cycle marker — the
#      Proven-Finding-#3 self-deny defect cannot recur even if a prior dispatch
#      crashed without --cycle-end.
#   2. LAZY_CYCLE_SUBAGENT truthy in the env → REFUSE. This is the explicit
#      subagent-context signal a dispatch may set; it does not depend on the
#      marker being armed.
#   3. Otherwise fall back to the cycle MARKER as the carrier: marker present →
#      REFUSE (the legacy backstop, retained per D4's final clause). A subagent
#      running mid-dispatch sees the orchestrator's marker; the orchestrator's
#      correct flow (set marker → dispatch → clear marker → THEN run these ops)
#      means the marker is cleared when the orchestrator reaches them.
#
# Why the env var matters (D4): a Python subprocess (lazy-state.py called from a
# subagent's Bash) CANNOT read the PreToolUse `agent_id` field — that is
# hook-input-only and does not propagate to subprocess env. So C3's reachable
# subagent signal is the env var (preferred) + the marker (fallback carrier),
# NOT agent_id. The C2 hook uses agent_id directly (it runs in the hook
# pipeline where the field IS present); C3 is the script-side backstop using the
# reachable signals. The deny SCOPE (which ops) stays in lockstep across both.
#
# CYCLE_REFUSED_OPS MUST stay in lockstep with the C2 hook's loop-formation /
# lifecycle deny-set (the agent_id trip in lazy-cycle-containment.sh:
# /lazy* Skill invocations, nested /lazy-batch, the LOOP_FORMATION_FLAGS
# routing flags, and dev:kill/dev:restart; recursive Agent/Task dispatch was
# REMOVED from the C2 deny set 2026-07-09 — the harness allows nested dispatch
# and the deny broke mandated read-only Explore fan-outs, see
# docs/bugs/adhoc-containment-denies-mandated-explore-fanout) — they are
# intentionally redundant defense-in-depth. A divergence is a coverage hole. The
# allow-listed ops a legitimately-dispatched subagent needs
# (`--neutralize-sentinel`, `--verify-ledger`) and all read/probe ops are
# deliberately NOT in this set.
#
# NOTE (cycle-subagent-runs-orchestrator-work Phase 2, KEYSTONE): `--cycle-end`
# and `--cycle-begin` are deliberately NOT added to CYCLE_REFUSED_OPS. Members of
# this set use the plain marker-fallback (refuse anyone-with-a-marker), which the
# orchestrator's own --cycle-end/--cycle-begin cannot tolerate — those run WHILE
# the orchestrator's marker is present. They are instead guarded by the dedicated
# `refuse_cycle_marker_mutation_if_subagent`, which keys on the POSITIVE
# LAZY_ORCHESTRATOR signal (orchestrator allowed under a live marker; subagent
# refused). The C2/C3 deny SCOPE still matches: the C2 hook adds --cycle-end /
# --cycle-begin to LOOP_FORMATION_FLAGS (agent_id trip), so a subagent cannot
# clear/arm the marker at EITHER layer. Keep the two in lockstep.
# ---------------------------------------------------------------------------

CYCLE_REFUSED_OPS: frozenset[str] = frozenset({
    "--run-end",
    "--run-start",
    "--apply-pseudo",
    "--enqueue-adhoc",
    "--emit-dispatch",
})


def _env_truthy(name: str) -> bool:
    """Return True when env var *name* is set to a non-empty, non-falsey value.

    Treats "", "0", "false", "no", "off" (case-insensitive) as false so a
    deliberately-cleared var doesn't read as set.
    """
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def refuse_if_cycle_active(op_name: str) -> None:
    """Refuse an orchestrator-only op when the caller is a cycle subagent (D4).

    Invoked at the ENTRY of each guarded CLI handler (`--run-end`, `--run-start`,
    `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch`) in lazy-state.py and
    bug-state.py, BEFORE any side effect (marker write/delete, queue mutation,
    prompt emission) so a refused op leaves state untouched.

    Subagent-vs-main-thread is decided in priority order (see the module comment
    above CYCLE_REFUSED_OPS):
      1. LAZY_ORCHESTRATOR truthy → return silently (never refuse the orchestrator,
         even with a stale marker present — structural immunity to the self-deny
         defect).
      2. LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal).
      3. else cycle marker present → refuse (legacy backstop carrier).
    A refusal prints a corrective message to stderr and exits 3 with ZERO side
    effects.

    Args:
        op_name: the CLI flag being guarded (e.g. "--run-end"). Echoed in the
                 corrective message so the subagent sees exactly what it tried.
    """
    # 1. The main-thread orchestrator asserts its identity → never self-refuse,
    #    even if a stale marker lingers from a crashed prior dispatch.
    #    cycle-subagent-runs-orchestrator-work Phase 1 (2026-06-16): this branch
    #    was READ-but-never-SET until the three orchestrators (lazy-batch,
    #    lazy-bug-batch, lazy-batch-cloud) began `export LAZY_ORCHESTRATOR=1` at
    #    their Step 0.55 run-start. Until then containment degraded to the
    #    deletable marker (the absence of any positive orchestrator signal). The
    #    export is now the load-bearing positive carrier; this guard's immunity
    #    actually fires for the real orchestrator.
    if _env_truthy("LAZY_ORCHESTRATOR"):
        return

    # 2/3. Explicit subagent signal, else the marker as the fallback carrier.
    explicit_subagent = _env_truthy("LAZY_CYCLE_SUBAGENT")
    marker = read_cycle_marker()
    if not explicit_subagent and marker is None:
        return

    feature_id = (marker or {}).get("feature_id", "<unknown>")
    # harness-telemetry-ledger Phase 2 (D4-B): record the containment trip AFTER
    # the refusal decision, BEFORE exit. The append-only ledger line is
    # observability, not state — the refused op still has ZERO state side
    # effects (same standing the deny ledger has at guard-deny time).
    # Marker-gated (non-destructive read) + fail-open inside the emitter.
    append_telemetry_event(
        "containment-refusal",
        item_id=(marker or {}).get("feature_id"),
        data={"op": op_name, "guard": "refuse_if_cycle_active"},
    )
    sys.stderr.write(
        f"REFUSED: `{op_name}` is an orchestrator-only operation and you are a "
        f"single cycle subagent (the lazy-cycle-active marker is present for "
        f"feature '{feature_id}'). STOP after your commit + push + report — "
        f"routing the next cycle, lifecycle teardown ({op_name}), enqueuing, and "
        f"completion are the orchestrator's job. This op was refused with zero "
        f"side effects.\n"
    )
    sys.exit(3)


def refuse_cycle_marker_mutation_if_subagent(op_name: str) -> None:
    """Refuse a cycle-MARKER MUTATION op (``--cycle-end`` / ``--cycle-begin``) for
    a subagent caller (cycle-subagent-runs-orchestrator-work Phase 2, KEYSTONE).

    Invoked at the ENTRY of the ``--cycle-end`` / ``--cycle-begin`` handlers in
    lazy-state.py and bug-state.py, BEFORE ``cycle_end_friction_check`` /
    ``clear_cycle_marker`` / ``write_cycle_marker`` — so a refused op leaves the
    marker file untouched (zero side effects).

    WHY THIS IS A SEPARATE GUARD (not ``refuse_if_cycle_active`` / not in
    ``CYCLE_REFUSED_OPS``): the ops in ``CYCLE_REFUSED_OPS`` use the plain
    marker-fallback (refuse anyone-with-a-marker), which is correct for them
    because the orchestrator's correct flow has the marker CLEARED when it runs
    them. But ``--cycle-end`` / ``--cycle-begin`` are exactly the ops the
    orchestrator runs WHILE its own marker is present (begin arms it, end clears
    it). Reusing the plain marker-fallback would refuse the orchestrator's own
    legitimate bracket and wedge the pipeline. So this guard keys on the POSITIVE
    ``LAZY_ORCHESTRATOR`` signal instead — that is why Phase 1 (the export) is a
    HARD prerequisite. The deny SCOPE still matches the C2 hook (a subagent cannot
    clear/arm the marker).

    Decided in priority order:
      1. LAZY_ORCHESTRATOR truthy → return silently (the orchestrator owns the
         bracket; allowed to clear/arm under its own live marker).
      2. else LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal).
      3. else cycle marker present (no orchestrator env) → refuse (the reachable
         subagent-context signal: a subagent mid-dispatch sees the orchestrator's
         marker but never inherits the LAZY_ORCHESTRATOR export).
      4. else (no marker, no subagent env) → return silently (the genuinely
         uncontained main-thread case with no marker armed yet — e.g. the very
         first ``--cycle-begin`` of a run before any marker exists).
    A refusal prints a corrective message to stderr and exits 3 with ZERO side
    effects (the marker is NOT mutated).

    Args:
        op_name: the CLI flag being guarded ("--cycle-end" | "--cycle-begin").
    """
    # 1. The orchestrator asserts its identity → never refuse its own bracket.
    if _env_truthy("LAZY_ORCHESTRATOR"):
        return

    # 2/3. Explicit subagent signal, else marker-present-without-orchestrator-env.
    explicit_subagent = _env_truthy("LAZY_CYCLE_SUBAGENT")
    marker = read_cycle_marker()
    if not explicit_subagent and marker is None:
        # 4. No subagent env AND no marker → genuinely uncontained main thread.
        return

    feature_id = (marker or {}).get("feature_id", "<unknown>")
    # harness-telemetry-ledger Phase 2 (D4-B): observability-only ledger line
    # (see refuse_if_cycle_active) — zero STATE side effects preserved.
    append_telemetry_event(
        "containment-refusal",
        item_id=(marker or {}).get("feature_id"),
        data={"op": op_name, "guard": "refuse_cycle_marker_mutation_if_subagent"},
    )
    sys.stderr.write(
        f"REFUSED: `{op_name}` mutates the cycle-containment marker and is an "
        f"orchestrator-only operation — you are a single cycle subagent (the "
        f"lazy-cycle-active marker is present for feature '{feature_id}'). A "
        f"subagent must NOT clear or re-arm the containment marker: clearing it "
        f"un-arms every downstream guard at once. STOP after your commit + push "
        f"+ report — the cycle bracket ({op_name}) is the orchestrator's job. "
        f"This op was refused with zero side effects (the marker is untouched).\n"
    )
    sys.exit(3)


def refuse_run_start_clobber(incoming_pipeline: str, *, now: float | None = None) -> None:
    """Refuse a ``--run-start`` that would CLOBBER a live run marker owned by a
    DIFFERENT pipeline (hardening-blind-to-process-friction, 2026-06-16 D-B).

    Invoked at the ENTRY of each ``--run-start`` handler (lazy-state.py pipeline
    "feature" / bug-state.py pipeline "bug"), AFTER ``refuse_if_cycle_active`` and
    BEFORE ``write_run_marker`` — so a refused clobber leaves the existing marker
    and all registry/counter state untouched.

    THE DEFECT THIS CLOSES: a nested ``/lazy`` (feature) dispatched mid-run ran
    ``lazy-state.py --run-start`` and ``write_run_marker`` UNCONDITIONALLY
    overwrote the ACTIVE bug run marker (pipeline:bug session X → pipeline:feature
    session Y).  That silently re-pointed the run identity, breaking the
    validate-deny / ack guard for the real orchestrator session — the bug run's
    hardening debt could never ack because its marker no longer existed.

    DISCRIMINATOR (why pipeline, not session_id): at ``--run-start`` the INCOMING
    run has no session_id yet — ``write_run_marker`` writes it bind-pending
    (None), to be stamped by the inject hook on first firing.  So an incoming-vs-
    existing session_id compare is impossible here.  The robust, mechanical
    discriminator is the PIPELINE field: a feature ``--run-start`` clobbering a
    live ``bug`` marker (or vice versa) is exactly the D-B signature and is ALWAYS
    a cross-run accident → refused.

    SAME-pipeline arbitration is CHECKPOINT-DISCRIMINATED
    (concurrent-same-branch-walkers-no-arbitration, 2026-06-20).  A same-pipeline
    re-``--run-start`` is NOT unconditionally a resume: a genuinely-concurrent
    SECOND walker on the same repo+branch+pipeline is also same-pipeline and would
    silently clobber the first walker's live marker (the residual gap left open by
    ``multi-repo-concurrent-runs``).  The discriminator is the presence of
    ``lazy-run-checkpoint.json`` on disk: a legitimate checkpoint-resume always
    carries that file (written by ``--run-end --reason checkpoint``, consumed by
    the handler's own ``consume_run_checkpoint()`` LATER), whereas a fresh second
    walker has none.  So:
      - same-pipeline + checkpoint file PRESENT  → ALLOW overwrite (sanctioned
        resume — the resume path restores its own counters).
      - same-pipeline + checkpoint file ABSENT (marker live + age-fresh)  → REFUSE
        (exit 3, zero side effects), naming the in-flight run.
    The checkpoint read here is NON-DESTRUCTIVE — an existence check ONLY, NEVER
    ``consume_run_checkpoint()`` (which deletes the resume signal the ``--run-start``
    handler legitimately consumes at a LATER step).

    Reads the marker file RAW (not via ``read_run_marker``) so the session-id
    staleness path (path B, which returns None for a non-owner caller and would
    hide the very marker we must protect) cannot mask the live owner.  Only the
    24h AGE staleness is honored: a marker older than ``_MARKER_STALE_SECONDS`` is
    a presumed-dead crashed run and may be freely overwritten (no refusal).

    Fail-open: a missing / unreadable / corrupt / unparseable marker, or a marker
    with no/blank pipeline field, never refuses — only an age-fresh, well-formed,
    DIFFERENT-pipeline marker triggers the exit-3 refusal.

    Args:
        incoming_pipeline: the pipeline of the run being started ("feature" |
            "bug").
        now: epoch float for age comparison (injectable for hermetic tests;
            defaults to time.time()).
    """
    if now is None:
        now = time.time()
    marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
    if not marker_path.exists():
        return
    try:
        existing = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            return  # corrupt root → fail-open (write_run_marker will overwrite)
    except (OSError, json.JSONDecodeError):
        return  # unreadable / unparseable → fail-open

    # Age staleness: a >24h-old marker is a presumed-dead crashed run — overwriting
    # it is the documented recovery (mirrors read_run_marker path A), so do NOT
    # refuse.  Any parse failure on started_at degrades to "not age-stale" so we
    # err toward protecting a live marker (conservative).
    started_at_str = existing.get("started_at", "")
    try:
        started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
        started_epoch = (started_dt - datetime.datetime(1970, 1, 1)).total_seconds()
    except (ValueError, TypeError):
        started_epoch = now  # unparseable → treat as fresh (protect, don't clobber)
    if now - started_epoch > _MARKER_STALE_SECONDS:
        return  # presumed-dead crashed run → safe to overwrite, no refusal

    existing_pipeline = (existing.get("pipeline") or "").strip()
    if not existing_pipeline:
        return  # no pipeline field → fail-open
    if existing_pipeline == incoming_pipeline:
        # Same-pipeline arbitration is checkpoint-discriminated: a sanctioned
        # checkpoint-resume carries lazy-run-checkpoint.json (read existence-only,
        # NON-destructively — NEVER consume_run_checkpoint, which deletes the
        # resume signal the --run-start handler consumes at a later step).
        checkpoint_present = (
            claude_state_dir(create=False) / _CHECKPOINT_FILENAME
        ).exists()
        if checkpoint_present:
            return  # same-pipeline checkpoint-resume → allow overwrite
        # Live, age-fresh, same-pipeline marker WITHOUT a checkpoint → a genuinely-
        # concurrent SECOND walker on this repo+branch+pipeline → refuse the clobber.
        existing_session = existing.get("session_id")
        forward_cycles = existing.get("forward_cycles")
        # harness-telemetry-ledger Phase 2 (D4-B): observability-only ledger
        # line, attributed to the LIVE run being protected (its marker supplies
        # the run identity). Zero STATE side effects preserved.
        append_telemetry_event(
            "containment-refusal",
            data={"op": "--run-start", "guard": "refuse_run_start_clobber",
                  "incoming_pipeline": incoming_pipeline},
            now=now,
        )
        sys.stderr.write(
            f"REFUSED: `--run-start` (pipeline={incoming_pipeline!r}) would CLOBBER "
            f"an ACTIVE run marker for the SAME pipeline with NO checkpoint waiting "
            f"(pipeline={existing_pipeline!r}, session_id={existing_session!r}, "
            f"started_at={started_at_str!r}, forward_cycles={forward_cycles!r}). A "
            f"second autonomous walker is already live on this same repo + branch + "
            f"pipeline — overwriting its marker would leave both walkers running with "
            f"no arbitration (collisions on feature selection and push ordering "
            f"surface mid-run). STOP and do NOT start a second {incoming_pipeline} "
            f"walker here. If the in-flight run is genuinely dead, end it first "
            f"(`--run-end`) from its own orchestrator; a legitimate checkpoint-resume "
            f"would carry lazy-run-checkpoint.json (absent here). This op was refused "
            f"with ZERO side effects (the existing marker is untouched).\n"
        )
        sys.exit(3)

    # Live, well-formed, DIFFERENT-pipeline marker → refuse the clobber.
    existing_session = existing.get("session_id")
    # harness-telemetry-ledger Phase 2 (D4-B): observability-only ledger line
    # (see the same-pipeline branch above). Zero STATE side effects preserved.
    append_telemetry_event(
        "containment-refusal",
        data={"op": "--run-start", "guard": "refuse_run_start_clobber",
              "incoming_pipeline": incoming_pipeline},
        now=now,
    )
    sys.stderr.write(
        f"REFUSED: `--run-start` (pipeline={incoming_pipeline!r}) would CLOBBER an "
        f"ACTIVE run marker owned by a DIFFERENT pipeline "
        f"(pipeline={existing_pipeline!r}, session_id={existing_session!r}, "
        f"started_at={started_at_str!r}). Overwriting it silently re-points the run "
        f"identity and breaks the validate-deny/ack guard for the live "
        f"{existing_pipeline} orchestrator (the D-B clobber). This is almost always "
        f"a nested/off-task pipeline dispatched inside another run — STOP and do "
        f"NOT start a {incoming_pipeline} run here. If the {existing_pipeline} run is "
        f"genuinely dead, end it first (`--run-end`) from its own orchestrator. This "
        f"op was refused with ZERO side effects (the existing marker is untouched).\n"
    )
    sys.exit(3)


# ---------------------------------------------------------------------------
# Script-persisted run counters
# ---------------------------------------------------------------------------

def fold_run_counters(
    forward_flag: int | None,
    meta_flag: int | None,
    marker: dict | None,
) -> tuple[int | None, int | None]:
    """Fold explicit CLI flags with marker-persisted counters.

    Priority: explicit flag wins over marker value wins over None.
    When both a flag and a marker value exist, the flag wins (backward compat:
    callers that pass --forward-cycles / --meta-cycles explicitly still get
    exactly those values; the marker fill-in is only for the post-compaction
    case where the flags are absent).

    Returns:
        (forward_cycles, meta_cycles) tuple where each element is:
          - the explicit flag value when it is not None, else
          - the marker's persisted value when marker is not None, else
          - None (no flag, no marker)
    """
    if marker is not None:
        # Marker exists: use its stored counters as fallback for absent flags.
        forward = (
            forward_flag
            if forward_flag is not None
            else marker.get("forward_cycles")
        )
        meta = (
            meta_flag
            if meta_flag is not None
            else marker.get("meta_cycles")
        )
    else:
        # No marker: only use explicit flag values; absent flags stay None.
        forward = forward_flag
        meta = meta_flag
    return (forward, meta)


def _bump_per_feature_forward(marker: dict, feature_id) -> None:
    """Increment ``marker["per_feature_forward_cycles"][feature_id]`` by 1, in
    place, as a SIBLING write inside whichever forward-advance mutation is already
    underway (feature-budget-guard-and-skip-ahead Phase 1).

    Called ONLY from the forward branch of ``advance_run_counters`` /
    ``advance_forward_cycle`` — so the per-feature increment rides the EXACT same
    forward-vs-meta gate as the run-level ``forward_cycles`` (no second oracle;
    meta-only advances never reach here). Legacy-tolerant: a marker lacking the key
    (a run resumed from a pre-feature marker) defaults to ``{}`` and never
    KeyErrors. A falsy/None ``feature_id`` is a no-op (no spurious key).
    """
    if not feature_id:
        return
    per_feature = marker.get("per_feature_forward_cycles")
    if not isinstance(per_feature, dict):
        per_feature = {}
    key = str(feature_id)
    per_feature[key] = int(per_feature.get(key, 0)) + 1
    marker["per_feature_forward_cycles"] = per_feature


def compute_per_feature_ceiling(
    max_cycles: int,
    ready_queue_depth: int,
    override: int | None = None,
) -> int | None:
    """Per-feature forward-cycle ceiling L_task — **OFF by default**
    (per-feature-cycle-cap-defers-incomplete-work Phase 1).

    The per-feature budget guard is DISABLED by default. With no ``override``
    (the default ``/lazy-batch`` path), this returns ``None`` — and the entire
    marker+ceiling-gated budget block in ``lazy-state.py`` short-circuits on
    ``_bg_ceiling is None`` (the trip gate is ``if _bg_marker is not None and
    _bg_ceiling is not None:``). So by default the whole-run ``max_cycles`` is the
    SOLE budget; no single feature is ever deferred/evicted for cycle-count
    monopolization. This reverses the prior default-on dynamic ceiling, which
    deferred incomplete work mid-flight instead of completing it.

    When ``override`` is supplied (the ``--per-feature-cycle-cap <N>`` path — the
    OFF-by-default OPT-IN) it is returned VERBATIM, re-arming a fixed ceiling
    ``N`` — including a deliberate ``0`` (a falsy-but-not-None cap). Only the
    opt-in re-arms the trip/defer/evict/grace/flush machinery, which is otherwise
    fully retained and unmodified; it is simply never reached by default.

    Pure + side-effect-free for direct characterization in ``test_lazy_core.py``.

    Args:
        max_cycles: the run's whole-run budget (``C_global`` / marker ``max_cycles``).
            Unused on the default-off path; retained for the stable call signature.
        ready_queue_depth: count of ready queue features. Likewise unused by default.
        override: a fixed ceiling that re-arms the guard (``None`` ⇒ OFF, return None).

    Returns:
        ``None`` by default (guard off); the ``override`` int verbatim when supplied.
    """
    if override is not None:
        return int(override)
    # Default-off: no override ⇒ the guard does not arm. Return None so the
    # ceiling-gated budget block in lazy-state.py short-circuits entirely. The
    # whole-run max_cycles is the only default budget; --per-feature-cycle-cap
    # <N> is the opt-in that re-arms a fixed ceiling.
    return None


def read_per_feature_forward_cycles(marker: dict | None) -> dict:
    """Read helper exposing the ``per_feature_forward_cycles`` map from a marker
    (feature-budget-guard-and-skip-ahead Phase 1).

    Returns the map (a ``{feature_id: int}`` dict) or ``{}`` when the marker is
    None or lacks the key (legacy tolerance). The Phase-2 trip evaluation and the
    probe path read the per-feature counts through here so the ``{}``-default lives
    in exactly one place.
    """
    if not isinstance(marker, dict):
        return {}
    value = marker.get("per_feature_forward_cycles")
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# budget-guard-defers-near-complete-feature Phase 1 — near-completion predicate
#   + corrective-cycle accounting + composite trip-signal evaluator.
#
# These four pure/near-pure helpers are wired into the trip site (Phase 2) and
# the end-of-run flush (Phase 3). They land first with direct red→green
# fixtures in test_lazy_core.py — no run marker / state-machine wiring needed to
# characterize them.
# ---------------------------------------------------------------------------


def feature_is_near_complete(feature_dir, repo_root=None) -> bool:
    """True iff a feature is within one validation cycle of done — the SAME
    "ready to validate" definition the mid-feature gate uses to fall through to
    the Step-9 ``/mcp-test``:

      - ``PHASES.md`` is present AND ``remaining_unchecked_are_verification_only``
        is True (every still-unchecked ``- [ ]`` row is a verification-only row
        owned by the runtime gate), AND
      - at least one ``plans/*.md`` part carries ``status: Complete``
        (implementation has fully landed), AND
      - no ``BLOCKED.md`` on disk (a blocker is not near-complete).

    Reuses ``remaining_unchecked_are_verification_only`` for the verification
    check (no re-implementation) so "near-complete" == the existing predicate.
    Tolerant of EVERY missing input — a missing PHASES.md, missing plans dir, or
    a nonexistent feature dir returns False and NEVER raises (the grace gate must
    fail safe toward "not near-complete" / no grace).

    ``repo_root`` is accepted for call-site symmetry with the other budget
    helpers but is not needed (everything is read relative to ``feature_dir``).
    """
    try:
        feat = Path(feature_dir)
    except (TypeError, ValueError):
        return False
    try:
        if (feat / "BLOCKED.md").exists():
            return False
        phases_md = feat / "PHASES.md"
        if not phases_md.exists():
            return False
        phases_text = phases_md.read_text(encoding="utf-8")
        if not remaining_unchecked_are_verification_only(phases_text):
            return False
        plans_dir = feat / "plans"
        if not plans_dir.is_dir():
            return False
        for plan_path in sorted(plans_dir.glob("*.md")):
            try:
                text = plan_path.read_text(encoding="utf-8")
            except OSError:
                continue
            # status lives in the frontmatter; a simple line scan suffices (the
            # frontmatter is the first block, and "status: Complete" is unique to
            # a completed plan part).
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("status:"):
                    value = stripped.split(":", 1)[1].strip()
                    if value == "Complete":
                        return True
                    break  # first status: line per file is authoritative
        return False
    except OSError:
        return False


def count_validation_corrective_cycles(marker, feature_id) -> int:
    """Read-only count of forward cycles attributable to validation-driven
    corrective work for ``feature_id``, read from the run-marker sub-map
    ``per_feature_corrective_cycles: {feature_id: int}``.

    Legacy/absent map ⇒ 0 (same tolerance pattern as
    ``read_per_feature_forward_cycles``). A None/non-dict marker, a missing key,
    or a non-int value all collapse to 0 — the discount never raises and never
    inflates the trip count.
    """
    if not isinstance(marker, dict):
        return 0
    per_feature = marker.get("per_feature_corrective_cycles")
    if not isinstance(per_feature, dict):
        return 0
    try:
        return int(per_feature.get(str(feature_id), 0) or 0)
    except (TypeError, ValueError):
        return 0


def record_corrective_cycle(marker: dict, feature_id) -> dict:
    """Increment ``marker["per_feature_corrective_cycles"][feature_id]`` by 1, in
    place, mirroring ``_bump_per_feature_forward``'s shape.

    Called at the apply-resolution / corrective-phase dispatch bracket (wired in
    Phase 2) so a validation-failure-driven corrective dispatch is counted as
    corrective and discounted from the budget trip. Legacy-tolerant: a marker
    lacking the key defaults to ``{}`` and never KeyErrors. A falsy/None
    ``feature_id`` is a no-op (no spurious key). Returns the marker (the caller
    persists it via the atomic marker write).
    """
    if not isinstance(marker, dict):
        return marker
    if not feature_id:
        return marker
    per_feature = marker.get("per_feature_corrective_cycles")
    if not isinstance(per_feature, dict):
        per_feature = {}
    key = str(feature_id)
    per_feature[key] = int(per_feature.get(key, 0) or 0) + 1
    marker["per_feature_corrective_cycles"] = per_feature
    return marker


def budget_trip_signals(
    forward_count: int,
    corrective_count: int,
    ceiling: int,
    near_complete: bool,
) -> dict:
    """Composite budget-guard trip evaluator — the SINGLE decision point Phase 2
    substitutes for the bare ``_bg_count >= _bg_ceiling`` comparison.

    Returns ``{should_defer: bool, effective_count: int, reason: str}``:

      - ``effective_count = max(0, forward_count - corrective_count)`` — discount
        validation-driven corrective work (option a), clamped at 0 so a feature
        whose corrective cycles exceed its forward cycles never goes negative.
      - ``should_defer`` is True ONLY when ``effective_count >= ceiling`` AND NOT
        ``near_complete`` — a near-complete feature is granted grace (no defer)
        even at/over the ceiling.
      - ``reason`` distinguishes the three branches for the probe/diag:
        ``near-complete-grace`` (grace short-circuited a would-be defer),
        ``corrective-discount`` (the discount dropped effective below ceiling),
        ``over-ceiling`` (a genuine trip).

    Pure: same inputs → identical dict, no marker/clock I/O.
    """
    try:
        fwd = int(forward_count or 0)
    except (TypeError, ValueError):
        fwd = 0
    try:
        corr = int(corrective_count or 0)
    except (TypeError, ValueError):
        corr = 0
    try:
        ceil = int(ceiling or 0)
    except (TypeError, ValueError):
        ceil = 0
    effective_count = max(0, fwd - corr)
    over_ceiling = effective_count >= ceil
    if near_complete and over_ceiling:
        # Grace: a near-complete feature is allowed past the ceiling.
        return {
            "should_defer": False,
            "effective_count": effective_count,
            "reason": "near-complete-grace",
        }
    if not over_ceiling:
        # Below the ceiling. If the raw forward count WOULD have tripped but the
        # corrective discount pulled it under, attribute it to the discount;
        # otherwise it simply has not reached the ceiling yet.
        reason = "corrective-discount" if (corr > 0 and fwd >= ceil) else "under-ceiling"
        return {
            "should_defer": False,
            "effective_count": effective_count,
            "reason": reason,
        }
    return {
        "should_defer": True,
        "effective_count": effective_count,
        "reason": "over-ceiling",
    }


# ---------------------------------------------------------------------------
# feature-budget-guard-and-skip-ahead Phase 3 — two-key skip-ahead predicates
#   (Locked Decision 5). Both are pure/near-pure and deterministic (no LLM
#   judgment): parse_independent_marker reads on-disk markers; skip_ahead_ready
#   combines a (caller-parsed) dep list with the gated-id set + the marker.
# ---------------------------------------------------------------------------

# The affirmative shared-state-isolation markers. `independent: true` is the
# primary; `no_shared_state: true` is a documented alias (SPEC Locked Decision 5).
_INDEPENDENT_MARKER_KEYS = ("independent", "no_shared_state")
# Matches a frontmatter line `independent: true` / `no_shared_state: true`
# (case-insensitive value; leading whitespace tolerated). Truthy ONLY for an
# explicit `true` — `false`/absent default to NOT-independent (the safe rail).
_INDEPENDENT_MARKER_RE = re.compile(
    r"^\s*(independent|no_shared_state)\s*:\s*true\s*$",
    re.IGNORECASE,
)


def _coerce_marker_truthy(value: object) -> bool:
    """True iff `value` is an explicit affirmative (bool True or a 'true' string).

    Deliberately strict: only ``True`` or a case-insensitive ``"true"`` count.
    A queue.json entry can carry either a JSON bool or a string; anything else
    (False, None, 0, "false", "") is NOT independent — the safe default.
    """
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def parse_independent_marker(spec_text: str, queue_entry: dict | None) -> bool:
    """Deterministic two-source read of the `independent: true` isolation marker
    (feature-budget-guard-and-skip-ahead Phase 3, Locked Decision 5).

    Returns ``True`` iff an explicit ``independent: true`` (or its
    ``no_shared_state: true`` alias) is present in EITHER the SPEC.md frontmatter
    OR the ``queue.json`` entry. Default (marker absent, or explicitly ``false``)
    is ``False`` — the shared-state-isolation rail that makes default-on
    skip-ahead safe (absent-flag items degrade to today's strict halt). On-disk,
    deterministic — no LLM judgment.

    Args:
        spec_text: the raw SPEC.md text (its frontmatter is scanned line-by-line;
            only the leading ``---`` fenced block is consulted when present, else
            the whole head of the file — a leading marker before any heading).
        queue_entry: the feature's ``queue.json`` entry (may be ``None``/empty).

    Returns:
        ``True`` if the affirmative marker is present in either source, else
        ``False``.
    """
    # Source 1: the queue entry (a JSON bool or string under either key).
    if isinstance(queue_entry, dict):
        for key in _INDEPENDENT_MARKER_KEYS:
            if _coerce_marker_truthy(queue_entry.get(key)):
                return True
    # Source 2: the SPEC.md frontmatter. Scan the leading `---` fenced block if
    # present; otherwise scan the head of the file up to the first markdown
    # heading (a bare leading `independent: true` line). The regex matches ONLY
    # an explicit `: true`, so a `: false` line is never a false positive.
    if isinstance(spec_text, str) and spec_text:
        lines = spec_text.splitlines()
        in_fence = False
        fence_seen = False
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                if not fence_seen and not in_fence:
                    in_fence = True
                    fence_seen = True
                    continue
                if in_fence:
                    # Closing fence — stop scanning the frontmatter block.
                    break
            if fence_seen and not in_fence:
                # We have already consumed a fenced block; don't scan the body.
                break
            if not fence_seen and stripped.startswith("#"):
                # No frontmatter fence and we hit a heading → no leading marker.
                break
            if _INDEPENDENT_MARKER_RE.match(line):
                return True
    return False


def write_deferred_requires_host(
    path: Path,
    *,
    feature_id: str,
    missing_capabilities: list[str],
    deferred_by: str = "lazy",
    date: str | None = None,
) -> None:
    """Write a capability-keyed ``DEFERRED_REQUIRES_HOST.md`` sentinel
    (host-capability-declaration Phase 5).

    The host-axis generalization of ``DEFERRED_REQUIRES_DEVICE.md``: it records
    that the feature is testable, just NOT on THIS host (≥1 required capability
    absent), so it re-opens on a host that provides the capability rather than
    being permanently waived or back-of-queued. ``missing_capabilities`` is
    LOAD-BEARING and MUST be non-empty — it is the self-limiting scope a
    capability-bearing host re-opens. Atomic write; the body keeps the
    human-readable re-open context.

    Args:
        path: destination ``DEFERRED_REQUIRES_HOST.md`` path.
        feature_id: the deferred feature's id.
        missing_capabilities: the absent required capability ids (non-empty).
        deferred_by: ``lazy`` | ``lazy-batch`` (the writer).
        date: ``YYYY-MM-DD`` (default: today).
    """
    if not missing_capabilities:
        raise ValueError(
            "write_deferred_requires_host: missing_capabilities MUST be non-empty "
            "(it is the self-limiting scope a capability-host re-opens)."
        )
    if date is None:
        date = datetime.date.today().isoformat()
    missing_sorted = sorted(set(missing_capabilities))
    fm = {
        "kind": "deferred-requires-host",
        "feature_id": feature_id,
        "missing_capabilities": missing_sorted,
        "deferred_by": deferred_by,
        "date": date,
    }
    body = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False).strip()
        + "\n---\n\n"
        "# Deferred — requires host capability\n\n"
        "## What was deferred and why\n\n"
        f"Feature `{feature_id}`'s runtime validation requires host "
        f"capability/ies {', '.join(f'`{m}`' for m in missing_sorted)}, which "
        "is absent on this host. The feature is testable — just not HERE — so it "
        "is deferred (not skipped/waived) and re-opens automatically on a host "
        "that provides the capability.\n\n"
        "## How to resume\n\n"
        "Run `/lazy` (or `/lazy-batch`) on a host that provides the missing "
        "capability/ies above. The capability-match re-opens this feature into "
        "runtime validation and deletes this sentinel on success.\n"
    )
    _atomic_write(path, body)


def skip_ahead_ready(
    deps: list[dict] | None,
    gated_ids: set[str] | frozenset[str],
    independent: bool,
) -> bool:
    """Two-key skip-ahead readiness predicate (feature-budget-guard-and-skip-ahead
    Phase 3, Locked Decision 5).

    A candidate is "skip-ahead-ready" iff BOTH keys hold:

      1. **No hard dep on a gated id.** None of its ``hard`` deps resolve to a
         currently-gated item (research-pending or BLOCKED). ``soft``/``composes``
         deps do NOT block — they need the upstream to *exist*, not be Complete,
         and a gated-but-specced upstream exists.
      2. **Affirmative isolation marker.** ``independent`` is truthy (the
         ``parse_independent_marker`` result — the shared-state isolation rail).

    Pure: ``deps`` is the caller-parsed dep list (from ``parse_dep_block``), so
    this predicate has no I/O and is directly characterizable.

    Args:
        deps: the candidate's parsed ``**Depends on:**`` deps (list of
            ``{feature_id, kind, reason}``; ``None``/empty ⇒ no deps).
        gated_ids: the set of currently-gated feature ids (research-pending or
            BLOCKED heads the loop has skipped this probe).
        independent: the ``parse_independent_marker`` verdict for this candidate.

    Returns:
        ``True`` iff both keys hold; ``False`` otherwise (degrades to strict halt
        for an unmarked or downstream candidate).
    """
    # Key 1: a HARD dep on any gated id blocks skip-ahead (it is genuinely
    # downstream of the gated head). soft/composes are ignored.
    for dep in (deps or []):
        if not isinstance(dep, dict):
            continue
        if dep.get("kind") == "hard" and dep.get("feature_id") in gated_ids:
            return False
    # Key 2: require the affirmative isolation marker.
    return bool(independent)


def advance_run_counters(state: dict) -> dict | None:
    """Advance the persisted forward_cycles or meta_cycles counter in the marker —
    ONLY when an actual dispatch (registry consume) has landed since the last
    advance.

    ROOT-CAUSE FIX (ISSUE 5 — d8-effect-chains live /lazy-batch run, 2026-06-14):
    The inject hook (lazy-route-inject.sh → lazy_inject.py) runs the full probe
    with ``--repeat-count`` on EVERY UserPromptSubmit turn while the marker is
    present — including non-dispatch turns (task notifications, the orchestrator's
    own bookkeeping turns, etc.). The prior implementation advanced the counter on
    EACH such firing, so ``forward_cycles`` reached 11 after only ~2 real
    dispatches + 2 recoveries (premature inflation → a false max-cycles halt at
    11/25 mid-run). The fix applies the SAME peek-vs-advance / consume-oracle
    discipline already used by ``update_repeat_counts`` (F2 debounce): a counter
    advances ONLY when the registry's consumed-emission count (``consume_count``,
    one consume per guard ALLOW = one real dispatch) has increased since the marker
    last recorded it. A probe firing with no intervening dispatch is a no-op.

    Classification rule (mirrors the emit_cycle_prompt None-return logic):
      - Real sub_skill: sub_skill is truthy AND does NOT start with ``"__"``
        → forward_cycles += 1  (a real dispatch cycle)
      - Pseudo/meta sub_skill: sub_skill starts with ``"__"``, OR sub_skill is
        falsy (None / empty) → meta_cycles += 1
    Meta/recovery dispatches that go through ``--emit-dispatch`` (not a probe) call
    ``advance_meta_cycle`` directly — those increment ``meta_cycles`` and bump the
    consume watermark too, so a subsequent probe in the same turn does not
    double-count.

    The marker carries ``last_advance_consume_count``: the consume-count at which a
    counter was last advanced (initialized to 0 at --run-start). The advance fires
    iff the current consume-count is strictly greater. After advancing, the
    watermark is updated to the current count. A legacy marker without the key is
    treated as 0, so the first advance still requires at least one consumed
    dispatch — a bare probe before any dispatch (consume-count 0) never advances.

    The updated marker is written atomically and returned. When no marker is
    present (read_run_marker returns None), this function returns None without
    writing anything — marker-gated, no-op when inactive. When a marker is present
    but no dispatch has landed since the last advance, the marker is returned
    UNCHANGED (no write).

    Args:
        state: the probe state dict (must contain "sub_skill")

    Returns:
        The marker dict (advanced or unchanged); None when no marker.
    """
    marker = read_run_marker()
    if marker is None:
        return None

    # Consume-oracle gate: only advance when a real dispatch landed since the last
    # advance. consumed_emission_count() is monotone-within-a-run (one consume per
    # guard ALLOW) UNTIL the ring cap evicts consumed entries, at which point the
    # LIVE census steps DOWN (non-monotonic oracle — Contributor B). A legacy marker
    # without the watermark key uses 0 so the first dispatch of the run always
    # advances.
    current_consume = consumed_emission_count()
    prior_consume = marker.get("last_advance_consume_count", 0)
    try:
        prior_consume = int(prior_consume)
    except (TypeError, ValueError):
        prior_consume = 0
    # CLAMP (Phase 2 — byref-dispatch-undercounts-forward-cycles): a non-monotonic
    # oracle can leave prior_consume STRANDED above the live census after ring-cap
    # eviction (or after advance_meta_cycle's +1 over-absorb), permanently freezing
    # the gate (current_consume <= prior_consume forever, even as real dispatches
    # land). When the census has dropped strictly BELOW the persisted watermark, the
    # watermark is stale — re-arm by clamping it down to the live census so this
    # observation (a genuine consume that crossed the eviction boundary) re-advances
    # exactly once, then the gate resumes normal strict-greater comparison. This does
    # NOT re-introduce the ISSUE-5 inflation: a bare re-probe with NO census change
    # leaves current_consume == prior_consume → still a no-op (the equality branch
    # below). Only a census that moved (rose, or dropped from eviction) can advance.
    if current_consume < prior_consume:
        prior_consume = current_consume - 1
    if current_consume <= prior_consume:
        # No dispatch consumed since the last advance — this is a bare probe/inject
        # firing (or a re-read). Do NOT advance, do NOT write. Idempotent across
        # the many inject-hook firings within one cycle.
        return marker

    sub_skill = state.get("sub_skill")
    # Real sub_skill: truthy and does not start with "__"
    if sub_skill and not str(sub_skill).startswith("__"):
        marker["forward_cycles"] = marker.get("forward_cycles", 0) + 1
        # feature-budget-guard-and-skip-ahead Phase 1: sibling per-feature
        # increment inside the SAME marker mutation, gated by the SAME forward
        # classification (a real non-`__` skill here). Reuses the existing advance
        # gate — no second oracle. Legacy-tolerant (defaults to {}).
        _bump_per_feature_forward(marker, state.get("feature_id"))
    else:
        # Pseudo or absent sub_skill → meta cycle
        marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1

    marker["last_advance_consume_count"] = current_consume

    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def advance_meta_cycle() -> dict | None:
    """Increment the marker's ``meta_cycles`` counter for a meta/recovery dispatch.

    ISSUE 5 (d8-effect-chains live run): recovery / coherence-recovery / hardening
    / apply-resolution / investigation dispatches go through ``--emit-dispatch``,
    NOT the ``--repeat-count`` probe path, so the prior code never incremented
    ``meta_cycles`` for them (it stayed 0 through 2 recoveries in the live run).
    This helper is called from the --emit-dispatch handler when it registers a
    meta-class emission so the meta budget actually advances.

    It bumps ``last_advance_consume_count`` to the current consume-count PLUS ONE
    — absorbing the meta dispatch's OWN forthcoming guard-ALLOW consume — so the
    next ``--repeat-count`` probe does not mis-attribute that consume as a forward
    cycle. (If the meta dispatch is ultimately refused/never consumed, the worst
    case is one delayed forward advance — far cheaper than the inflation bug.)
    Marker-gated: no-op (returns None) when no marker is active.

    Phase 2 hardening (byref-dispatch-undercounts-forward-cycles, Contributor A):
    the ``+1`` is intentionally retained — it is load-bearing for the
    no-double-count invariant (``test_advance_meta_cycle_increments_meta`` pins it).
    Its only PERMANENT-strand risk was when meta dispatches outpaced forward
    consumes AND a later ring-cap eviction dropped the live census below this
    inflated watermark. That tail is now subsumed by ``advance_run_counters``'s
    census-drop CLAMP (a watermark stranded above the live census re-arms on the
    next census step), so the ``+1`` can no longer freeze the gate permanently — at
    most it delays a single forward advance by one cycle, as documented above.

    Returns:
        The updated marker dict; None when no marker.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1
    # +1 absorbs this meta dispatch's own forthcoming consume (see docstring).
    marker["last_advance_consume_count"] = consumed_emission_count() + 1
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


# Forward-advancing pseudo-skills: inline (--apply-pseudo) terminals that ADVANCE
# the pipeline a step (write a receipt / flip status / archive), as opposed to
# cleanup/meta pseudo-skills. A forward-advancing pseudo-skill counts toward the
# forward budget (forward_cycles); any other __-prefixed (or falsy) sub_skill is
# meta. Kept here as the SSOT for the Fix-A classifier (item 1,
# lazy-batch-unified-driver-parity-and-accounting Phase 1).
_FORWARD_ADVANCING_PSEUDO_SKILLS = frozenset({
    "__mark_complete__",
    "__mark_fixed__",
    "__write_validated_from_skip__",
    "__write_validated_from_results__",
    "__grant_skip_no_mcp_surface__",
    "__flip_plan_complete_cloud_saturated__",
})


def advance_forward_cycle(state: dict) -> dict | None:
    """Fix-A (item 1): a CONSUME-INDEPENDENT forward/meta advance keyed on a change
    in the marker-recorded ``(feature_id, current_step, sub_skill)`` tuple.

    ROOT CAUSE (lazy-batch-unified-driver-parity-and-accounting, 2026-06-17):
    forward-advancing inline pseudo-skills (``__mark_complete__``/``__mark_fixed__``/
    ``__write_validated_*``/``__grant_skip_no_mcp_surface__``/
    ``__flip_plan_complete_cloud_saturated__``) run via ``--apply-pseudo`` — they
    dispatch no Agent, trigger no guard ALLOW, and increment no registry consume.
    ``advance_run_counters`` gates on a consume rise, so the forward budget never
    advances for them (and ``advance_meta_cycle`` only covers ``--emit-dispatch``
    meta calls). This helper closes that gap by advancing on a genuine STATE
    CHANGE — independent of the consume oracle.

    The marker carries ``last_advance_state_key``: the
    ``[feature_id, current_step, sub_skill]`` tuple at which a counter was last
    advanced (a JSON list; a legacy marker without the key is treated as None, so
    the first state change always advances). The advance fires iff the current
    tuple DIFFERS from the recorded one — so a bare probe/inject re-fire with the
    SAME tuple is a no-op (preserves the idempotence that the consume-gated
    ``advance_run_counters`` provides for re-fires). On advance the key is updated.

    Classification (a forward-advancing pseudo-skill OR a real sub_skill →
    ``forward_cycles``; any other ``__``-prefixed / falsy sub_skill → ``meta_cycles``):
      - real sub_skill (truthy, not ``__``-prefixed) → forward
      - ``__``-prefixed AND in ``_FORWARD_ADVANCING_PSEUDO_SKILLS`` → forward
      - any other ``__``-prefixed, OR falsy sub_skill → meta

    Marker-gated: returns None (no write) when no run marker is present, mirroring
    ``advance_meta_cycle``. When the tuple is unchanged, returns the marker
    UNCHANGED (no write).

    Args:
        state: the resolved probe/apply state dict (reads ``sub_skill``,
               ``feature_id``, ``current_step``).

    Returns:
        The marker dict (advanced or unchanged); None when no marker.
    """
    marker = read_run_marker()
    if marker is None:
        return None

    sub_skill = state.get("sub_skill")
    # The advance key — JSON-serializable list (json.loads round-trips a tuple to a
    # list, so compare as lists for stable equality across re-reads).
    current_key = [
        state.get("feature_id"),
        state.get("current_step"),
        sub_skill,
    ]
    prior_key = marker.get("last_advance_state_key")
    if prior_key == current_key:
        # Same state — a bare re-fire. Do NOT advance, do NOT write.
        return marker

    # Classify: forward iff a real skill OR a forward-advancing pseudo-skill.
    is_real = bool(sub_skill) and not str(sub_skill).startswith("__")
    is_forward_pseudo = sub_skill in _FORWARD_ADVANCING_PSEUDO_SKILLS
    if is_real or is_forward_pseudo:
        marker["forward_cycles"] = marker.get("forward_cycles", 0) + 1
        # feature-budget-guard-and-skip-ahead Phase 1: sibling per-feature
        # increment, gated by the SAME forward classification used above (the
        # state-change trigger). Keeps "what counts as a forward cycle" defined in
        # exactly one place; no second oracle. Legacy-tolerant (defaults to {}).
        _bump_per_feature_forward(marker, state.get("feature_id"))
    else:
        marker["meta_cycles"] = marker.get("meta_cycles", 0) + 1

    marker["last_advance_state_key"] = current_key

    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def record_resolution_signal(state: dict) -> dict | None:
    """Persist the resolution-aware reset signal on the run marker.

    ROOT CAUSE (loop-detected-false-positives-from-probe-and-reboot-churn,
    symptom 3 — the sole residual class after the F1/F2 consume-debounce):
    a needs-input *resolution* meta-cycle is itself an Agent dispatch, so it
    consumes a registry nonce.  That defeats the F2 double-probe debounce's
    "no dispatch landed between the two probes" precondition — the HEAD-blind
    ``step_repeat_count`` therefore SURVIVES a legitimately-resolved blocker and
    keeps marching toward the LOOP-DETECTED tripwire.

    The fix is a DETERMINISTIC, PERSISTED signal (⚖ D7: a recorded marker field,
    NOT a racy probe-time re-inference of cleared-sentinel state).  The resolution
    dispatch bracket calls this helper to record
    ``last_resolution_step_key = [feature_id, current_step]`` on the run marker.
    ``update_repeat_counts`` reads it and, on the NEXT probe with the SAME step
    signature, RESETS ``step_count`` to 1 and CLEARS the field — so the reset
    fires exactly ONCE across the resolution (one-shot), scoped exactly like the
    ordered-advance exemption.

    Mirrors the ``last_advance_state_key`` marker-field pattern
    (``advance_forward_cycle``).  Marker-gated: returns None and writes nothing
    when no run marker is present (so an ordinary, non-resolution cycle never
    leaves the signal asserted).  Legacy markers lacking the field simply never
    trigger the reset (same legacy-tolerance as ``head`` / ``step_*`` /
    ``consume_count``) — the reset can never spuriously fire on an old marker.

    Args:
        state: a dict carrying ``feature_id`` and ``current_step`` (the step
               signature the resolution was applied at).

    Returns:
        The updated marker dict; None when no marker is present.
    """
    marker = read_run_marker()
    if marker is None:
        return None

    # The step signature the resolution was applied at — a JSON-serializable list
    # (json round-trips a tuple to a list, so the consumer compares as lists).
    marker["last_resolution_step_key"] = [
        state.get("feature_id"),
        state.get("current_step"),
    ]
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def _consume_resolution_signal(repo_root: Path, step_sig: tuple) -> bool:
    """Read-and-clear the one-shot resolution signal for ``update_repeat_counts``.

    Returns True iff a run marker for THIS repo is present AND it carries a
    ``last_resolution_step_key`` equal to ``step_sig`` (the current
    ``(feature_id, current_step)`` step signature).  On a match the field is
    CLEARED from the marker (one-shot — the reset fires once across the
    resolution, not on every subsequent probe) and the marker is re-persisted.

    Repo-scoped exactly like the F2 debounce oracle: a marker bound to a
    DIFFERENT repo never matches (so a concurrent run in another repo can never
    reset this repo's step counter).  Fail-safe: any read/parse/path error
    returns False (the reset simply does not fire — never raises, never weakens
    the tripwire on a degraded marker).
    """
    try:
        marker = read_run_marker()
        if marker is None:
            return False
        # Repo-scope: only honor a signal whose marker belongs to THIS repo.
        marker_repo = marker.get("repo_root")
        if marker_repo is None or Path(marker_repo).resolve() != repo_root.resolve():
            return False
        recorded = marker.get("last_resolution_step_key")
        if recorded != list(step_sig):
            return False
        # One-shot: clear the signal and re-persist before returning the match.
        marker.pop("last_resolution_step_key", None)
        marker_path = claude_state_dir() / _MARKER_FILENAME
        _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


# ---------------------------------------------------------------------------
# mechanize-prose-only-orchestrator-contracts (b): post-cycle input-audit
# obligation — the §1d.5 dispatch made unskippable.
#
# ROOT CAUSE: the input-audit dispatch (--emit-dispatch input-audit) has
# existed as a registered, guard-safe emission class for a while, but WHETHER
# the orchestrator runs it after a /spec or plan-feature cycle was pure
# SKILL.md prose (§1d.5) — an orchestrator under autonomous load can skip the
# step entirely with no mechanical consequence, which is exactly the failure
# mode §1d.5 itself exists to catch for the CYCLE SUBAGENT's self-audit ("zero
# NEEDS_INPUT.md sentinels fired from /spec's self-audit across ~75 observed
# cycles"). This promotes the DISPATCH obligation itself to the same
# script-enforced withhold the pending-hardening-debt precedent uses
# (lazy-state.py ~13215: route_overridden_by == "pending-hardening-debt").
#
# Mechanism (marker-field pattern, mirroring last_advance_state_key /
# last_resolution_step_key): --cycle-end records `audit_obligation:
# {item_id, cycle_kind}` on the run marker when the ending cycle's sub_skill
# is an audited kind (spec/plan-feature on the feature pipeline; spec-bug/
# plan-bug on the bug pipeline). The NEXT --emit-prompt probe sees the
# obligation and WITHHOLDS the forward cycle_prompt (byte-identical shape to
# the hardening-debt withhold) until --emit-dispatch input-audit registers a
# real dispatch under the SAME live marker, which discharges it.
# ---------------------------------------------------------------------------

# The sub_skill kinds whose cycle-end obligates a post-cycle input audit.
# feature pipeline: spec, plan-feature (author SPEC/PHASES content).  bug
# pipeline: spec-bug, spec-phases — per the EXISTING lazy-bug-batch/SKILL.md
# Step 1d.5 skip-condition prose this mechanizes: "plan-bug is a planning
# step, not a SPEC/PHASES-authoring cycle — skip audit for plan-bug" (D5:
# a discovered ambiguity resolves in favor of existing prose semantics, not
# a naive plan-feature/plan-bug pairing). spec-phases is carried for prose
# fidelity even though bug-state.py's live routing never emits it today
# (SKILL_SPEC_PHASES is an unused constant) — harmless if it never fires,
# pre-covered if the bug pipeline ever starts emitting it. One shared set —
# a sub_skill name never collides across pipelines within a single process
# (only one state script's sub_skill vocabulary is live).
AUDITED_CYCLE_KINDS: frozenset = frozenset({
    "spec", "plan-feature", "spec-bug", "spec-phases",
})


def record_audit_obligation(item_id: str | None, cycle_kind: str | None) -> dict | None:
    """Record the post-cycle input-audit obligation on the run marker (D2-A).

    Called from --cycle-end immediately after a /spec or plan-feature (or the
    bug-pipeline spec-bug/plan-bug) cycle ends. Marker-gated: returns None and
    writes nothing when no run marker is present (mirrors
    ``record_resolution_signal``). A falsy/non-audited ``cycle_kind`` is a
    no-op (returns the marker UNCHANGED, no write) — only the four audited
    kinds ever arm the obligation.

    Overwrites any PRIOR obligation (there is at most one outstanding
    obligation at a time — cycles are serial, and the withhold this powers
    forces discharge before the next cycle can begin).

    Args:
        item_id: the feature/bug id the obligation is owed for.
        cycle_kind: the sub_skill of the cycle that just ended.

    Returns:
        The updated marker dict; None when no marker is present.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    if cycle_kind not in AUDITED_CYCLE_KINDS:
        return marker
    marker["audit_obligation"] = {"item_id": item_id, "cycle_kind": cycle_kind}
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def pending_audit_obligation() -> dict | None:
    """Read-only: the current run marker's outstanding audit_obligation, or
    None (no marker / no obligation / legacy marker lacking the field).

    Never raises, never writes. Used by the --emit-prompt withhold check and
    by any read-only probe/status surface that wants to display it.
    """
    marker = read_run_marker()
    if marker is None:
        return None
    obligation = marker.get("audit_obligation")
    return obligation if isinstance(obligation, dict) else None


def discharge_audit_obligation() -> bool:
    """Clear the run marker's audit_obligation (D2-A discharge).

    Called at the --emit-dispatch input-audit success site, AFTER the
    dispatch is registered under a live marker (register_emission_if_marked
    returned a non-None entry) — the same transaction the SPEC calls out
    ("discharged by the --emit-dispatch input-audit registration itself").

    Returns True iff a marker was present and carried a (now-cleared)
    obligation; False on a no-op (no marker, or no obligation to clear) —
    never raises.
    """
    marker = read_run_marker()
    if marker is None:
        return False
    if "audit_obligation" not in marker:
        return False
    marker.pop("audit_obligation", None)
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return True


def build_input_audit_emit_command(
    state_script_name: str,
    *,
    item_id: str,
    item_name: str,
    spec_path: str,
    cycle_kind: str,
    cwd: str,
) -> str:
    """Pre-compose the single-line shell command that discharges the D2-A
    audit obligation (mirrors ``build_hardening_emit_command``'s shape for
    the pending-hardening-debt withhold).

    ``cycle_summary`` and ``cycle_commit_sha`` are NOT script-derivable
    narrative fields per se, but a mechanical proxy is available and used so
    the command is genuinely ready-to-run (never a hand-fill placeholder):
    ``cycle_commit_sha`` defaults to the SKILL.md-sanctioned fallback
    ``"HEAD~1"``; ``cycle_summary`` defaults to the subject line of the most
    recent commit at ``cwd`` (``git log -1 --format=%s``) when resolvable,
    else an empty string (never fabricated prose).

    Returns:
        A single shell command string, safe to paste into bash.
    """
    def _ctx(key: str, value: str) -> str:
        return f"--context {key}={shlex.quote(value)}"

    cycle_summary = ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "log", "-1", "--format=%s"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            cycle_summary = proc.stdout.strip()
    except Exception:  # noqa: BLE001 — best-effort proxy, never fatal
        pass

    parts = [
        f"python3 ~/.claude/scripts/{state_script_name}",
        "--emit-dispatch input-audit",
        _ctx("item_name", item_name or ""),
        _ctx("spec_path", spec_path or ""),
        _ctx("cycle_kind", cycle_kind or ""),
        _ctx("cycle_summary", cycle_summary),
        _ctx("cycle_commit_sha", "HEAD~1"),
        _ctx("item_id", item_id or ""),
        _ctx("cwd", cwd or ""),
    ]
    return " ".join(parts)


# ---------------------------------------------------------------------------
# mechanize-prose-only-orchestrator-contracts (c): decision write-back.
#
# Mid-run AskUserQuestion answers previously evaporated between the answer
# and the apply-resolution dispatch — the orchestrator hand-typed
# chosen_path/resolution_summary into the --emit-dispatch apply-resolution
# --context args from probe output + the operator's spoken answer, a
# hand-carry across a compaction-prone context (SPEC field evidence: "Why
# was the plan not updated after my decision?" / "My answers didn't go
# through").
#
# --record-decision writes an atomic, on-disk record keyed to the sentinel
# path; --emit-dispatch apply-resolution then READS chosen_path /
# resolution_summary from the record instead of accepting them as
# orchestrator-typed context — absent a record it refuses, naming the exact
# --record-decision command to run.  The record lives in a SIBLING state-dir
# file (lazy-decisions.json), NOT the run marker — deliberately: it must
# survive --run-end (which deletes the marker + registry) so the
# answered-decisions ledger outlives the run for retro evidence (SPEC Open
# Question 2, resolved toward the sibling-file option).
# ---------------------------------------------------------------------------

_DECISIONS_FILENAME = "lazy-decisions.json"


def _normalize_sentinel_key(sentinel_path: str | Path) -> str:
    """Normalize a sentinel path into a stable dict key (D3-A).

    Uses os.path.normpath + forward slashes so the SAME sentinel recorded
    and looked up via slightly different path spellings (relative vs
    absolute, backslash vs forward slash) still round-trips. Does NOT
    require the file to exist (recording happens against a real, existing
    sentinel in practice, but the key derivation itself is pure string
    normalization — no filesystem I/O, no resolve()).
    """
    return os.path.normpath(str(sentinel_path)).replace("\\", "/")


def _load_decisions() -> dict:
    """Read lazy-decisions.json entries ({sentinel_key: record}).

    Read-only (create=False — a lookup must never create the state dir).
    Corrupt/absent ⇒ {} (fail-open, mirroring _load_notify_ledger).
    """
    try:
        path = claude_state_dir(create=False) / _DECISIONS_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        return entries if isinstance(entries, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def record_decision(
    sentinel_path: str | Path,
    chosen: str,
    *,
    summary: str | None = None,
    now: float | None = None,
) -> dict:
    """Write an atomic decision record keyed to ``sentinel_path`` (D3-A).

    Overwrites any PRIOR record for the SAME sentinel (a re-recorded answer
    supersedes — the orchestrator re-running --record-decision after a
    correction is the sanctioned override path, not a second record).

    NOT marker-gated — a decision can be recorded even between runs (a
    resumed session answering a question from a prior, now-ended run), and
    the record is deliberately independent of run-marker lifecycle (it must
    survive --run-end).

    Returns:
        The written record dict.
    """
    ts = time.time() if now is None else float(now)
    key = _normalize_sentinel_key(sentinel_path)
    record = {
        "sentinel_path": str(sentinel_path),
        "chosen_path": chosen,
        "resolution_summary": summary or "",
        "recorded_at": ts,
    }
    entries = _load_decisions()
    entries[key] = record
    payload = {"v": 1, "entries": entries}
    _atomic_write(
        claude_state_dir() / _DECISIONS_FILENAME,
        json.dumps(payload, indent=2) + "\n",
    )
    return record


def read_decision_record(sentinel_path: str | Path) -> dict | None:
    """Read-only lookup of the decision record for ``sentinel_path``, or None
    when no record has been written for it. Never raises."""
    key = _normalize_sentinel_key(sentinel_path)
    entries = _load_decisions()
    record = entries.get(key)
    return record if isinstance(record, dict) else None


def bind_decision_record_context(
    cls: str, context: dict, state_script_name: str
) -> dict:
    """D3-A binding seam: for ``cls == "apply-resolution"`` with a
    ``sentinel_path`` in context, REPLACE ``chosen_path`` /
    ``resolution_summary`` with the values from the recorded decision
    (the record is authoritative — any orchestrator-typed values for those
    two keys are overridden, closing the hand-carry failure mode).

    Every other class, and an apply-resolution context with NO
    ``sentinel_path`` key at all, passes through UNCHANGED — the existing
    ``@requires`` refusal in ``emit_dispatch_prompt`` handles a missing
    ``sentinel_path`` exactly as before (this seam only engages once a
    sentinel is named).

    Raises:
        ValueError: when ``cls == "apply-resolution"``, ``sentinel_path`` is
            present, but NO decision record exists for it — the message
            names the exact ``--record-decision`` command to run. The
            existing ``--emit-dispatch`` handler's catch-all already formats
            any raised exception into the structured JSON refusal
            (``dispatch_prompt_refused``, exit 1), so this composes with zero
            new error-handling paths.

    Returns:
        The (possibly updated) context dict.
    """
    if cls != "apply-resolution":
        return context
    sentinel_path = context.get("sentinel_path")
    if not sentinel_path:
        return context
    record = read_decision_record(sentinel_path)
    if record is None:
        cmd = (
            f"python3 ~/.claude/scripts/{state_script_name} --record-decision "
            f"--sentinel {shlex.quote(str(sentinel_path))} "
            f'--chosen "<chosen option label(s)>" '
            f'--summary "<optional resolution summary>"'
        )
        raise ValueError(
            "no recorded decision for sentinel "
            f"{sentinel_path!r} — record the operator's answer first: {cmd}"
        )
    context = dict(context)
    context["chosen_path"] = record.get("chosen_path", "")
    context["resolution_summary"] = record.get("resolution_summary", "")
    return context


# ---------------------------------------------------------------------------
# Phase 7 WU-7.4 — Run-checkpoint contract (sanctioned unattended pause)
# ---------------------------------------------------------------------------
#
# A --run-end --reason checkpoint writes lazy-run-checkpoint.json carrying the
# next route the orchestrator should resume with plus the marker's fold counters
# at run end.  The next --run-start consumes it (echoes + deletes), giving the
# resumed run its sanctioned-pause context.  This gives /lazy-batch-retro a
# mechanical sanctioned-vs-improvised signal for an early stop.


def write_run_checkpoint(
    next_route: str,
    counters: dict,
    now: float | None = None,
    operator_authorized: bool = False,
) -> dict:
    """Write lazy-run-checkpoint.json to the state dir (checkpoint run-end).

    Args:
        next_route: the probed next route the resumed run should take.
        counters: the marker's fold counters as folded at run end (e.g.
                  {"forward_cycles": N, "meta_cycles": M, "max_cycles": K}).
        now: epoch float for the ts field (injectable for hermetic tests).
        operator_authorized: whether this checkpoint was written for a deliberate
            operator-authorized stop (a `/lazy-batch <N>` re-invoke wants a fresh
            0/0 budget) vs. an automatic reliability pause (monotonic carry-forward
            on resume).  Persisted as a top-level field so restore_checkpoint_counters
            can branch on resume provenance.  Defaults False —
            backward-compatible: a pre-fix checkpoint file lacking the field reads
            as falsy, taking the carry-forward path.

    Returns:
        The checkpoint dict that was written.
    """
    if now is None:
        now = time.time()
    # cycle-bracket-break-on-checkpoint-resume (hardening Round 35, 2026-06-23):
    # capture the RUN IDENTITY (the marker's started_at) at checkpoint-write time
    # so the carry-forward resume path can RESTORE it. A non-operator-authorized
    # checkpoint resume is "the SAME run continuing after a sanctioned pause" — it
    # already carries forward the monotonic forward/meta counters (HARD CONSTRAINT
    # 8). The run IDENTITY (started_at) is the value detect_cycle_bracket_friction
    # signal (a) compares (run_started_at snapshotted at --cycle-begin vs the live
    # marker's started_at at --cycle-end). write_run_marker unconditionally MINTS a
    # fresh started_at on the resuming --run-start, so without restoring it a
    # legitimate same-run pause/resume changed the run identity mid-cycle and
    # false-tripped cycle-bracket-break on any cycle whose begin snapshot predates
    # the resume (observed: begin 03:15:38Z != end 05:41:28Z, jog-wheel-nudging).
    # Best-effort read — a missing/None marker (degraded) omits the field, and
    # restore_checkpoint_counters falls back to leaving the freshly-minted identity
    # (no crash, no false restore). Operator-authorized resumes do NOT restore it
    # (they are a genuinely NEW run wanting a fresh identity — see restore_*).
    # Read the marker RAW (not via read_run_marker, whose path-A age gate DELETES a
    # >24h-stale marker on read) — a checkpoint-write must NEVER have a destructive
    # side effect on the marker it is snapshotting.
    # adhoc-checkpoint-resume-field-complete-continuity (2026-06-23): snapshot the
    # FULL run-scoped continuity set (RUN_CONTINUITY_FIELDS) as ONE nested
    # `continuity` block — not the ad-hoc started_at-only snapshot that grew
    # reactively in lockstep with the carry-set. restore_checkpoint_counters
    # re-applies this whole block as one unit on a sanctioned resume, so a newly-
    # added continuity field rides through by construction (no third whack-a-mole).
    # Read the marker RAW (never read_run_marker, whose path-A age gate DELETES a
    # >24h-stale marker on read) — a checkpoint-write must NEVER have a destructive
    # side effect on the marker it is snapshotting. The flat run_started_at key is
    # retained as a mirror for one transition so a restore by an older code path or
    # a half-flight legacy reader still sees the identity (back-compat belt).
    run_started_at = None
    continuity: dict = {}
    try:
        _marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
        if _marker_path.exists():
            _live = json.loads(_marker_path.read_text(encoding="utf-8"))
            if isinstance(_live, dict):
                run_started_at = _live.get("started_at")
                for _k in RUN_CONTINUITY_FIELDS:
                    if _k in _live:
                        continuity[_k] = _live[_k]
    except Exception:  # pragma: no cover - defensive; never block a checkpoint
        run_started_at = None
        continuity = {}
    checkpoint = {
        "reason": "checkpoint",
        "next_route": next_route,
        "counters": counters,
        "operator_authorized": bool(operator_authorized),
        "run_started_at": run_started_at,
        "continuity": continuity,
        "ts": now,
    }
    checkpoint_path = claude_state_dir() / _CHECKPOINT_FILENAME
    _atomic_write(checkpoint_path, json.dumps(checkpoint, indent=2) + "\n")
    return checkpoint


def consume_run_checkpoint() -> dict | None:
    """Read and DELETE lazy-run-checkpoint.json (consume-once resume context).

    Called by --run-start: if a checkpoint file exists, its content is returned
    (so run-start can echo it as resume context) and the file is deleted so the
    same checkpoint is never replayed twice.  A missing or corrupt file → None.

    Returns:
        The checkpoint dict, or None when no (valid) checkpoint is present.
    """
    checkpoint_path = claude_state_dir(create=False) / _CHECKPOINT_FILENAME
    if not checkpoint_path.exists():
        return None
    data: dict | None = None
    try:
        raw = checkpoint_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, json.JSONDecodeError, ValueError):
        data = None
    # Delete regardless of parse outcome — a corrupt checkpoint must not haunt
    # every subsequent run-start.
    try:
        checkpoint_path.unlink()
    except OSError:
        pass
    return data


def restore_checkpoint_counters(checkpoint: dict | None) -> dict | None:
    """Restore a resumed run's monotonic cycle counters AND run identity from its
    checkpoint.

    Identity carry-forward (cycle-bracket-break-on-checkpoint-resume, hardening
    Round 35, 2026-06-23): in the carry-forward (non-operator-authorized) branch
    this ALSO restores the marker's ``started_at`` (the run identity) from the
    checkpoint's ``run_started_at`` field — in lockstep with the counters and for
    the same HARD CONSTRAINT 8 reason (the SAME run continues across a sanctioned
    pause, so its identity must be continuous, not freshly minted). Guarded so a
    >24h-old identity is NOT restored (it would subvert read_run_marker's age
    gate), and a missing/unparseable identity leaves the minted started_at intact.

    ROOT-CAUSE FIX (accidental mid-run counter reset, 2026-06-14): a sanctioned
    checkpoint pause writes ``lazy-run-checkpoint.json`` carrying the marker's
    ``forward_cycles`` / ``meta_cycles`` at run end (see ``write_run_checkpoint``).
    The resuming ``--run-start`` previously called ``write_run_marker`` (which
    UNCONDITIONALLY zeros both counters + the consume watermark) and then merely
    echoed the checkpoint as ``resumed_from_checkpoint`` WITHOUT writing those
    counters back. Result: a checkpoint pause/resume reset the running cycle count
    to 0 MID-RUN — a direct violation of HARD CONSTRAINT 8 (both counters are
    monotonic for the LIFE of a run and never reset on a within-run transition).
    This is the operator-observed reset.

    Two resume classes (operator-checkpoint-resume-counter-reset, 2026-06-17):
    a checkpoint carries an ``operator_authorized`` flag recorded at write time.

    * **operator-authorized** (``operator_authorized`` truthy) — a DELIBERATE
      ``/lazy-batch <N>`` re-invoke after an operator-authorized stop. The operator
      wants a FRESH authorized budget, so this helper does NOT carry the paused
      counts forward: it returns ``None`` (a no-op), leaving the just-written
      marker's by-design ``0/0`` start. This is NOT a within-run reset (no HARD
      CONSTRAINT 8 violation) — it is a NEW authorized run that happens to resume
      a route, not a within-run transition.
    * **automatic reliability pause / legacy** (``operator_authorized`` falsy or
      ABSENT) — an automatic mid-run pause (e.g. cloud ≥2 guard denials) or a
      pre-fix checkpoint file. The resumed marker must CARRY FORWARD the paused
      counts so the running total never goes backward mid-run and an auto-resume
      cannot silently exceed the authorized ``max_cycles`` (HARD CONSTRAINT 8).
      A truthy-check (``if checkpoint.get("operator_authorized"):``) makes both
      ``False`` and a missing field take this carry-forward path uniformly.

    For the carry-forward class, this helper reads the just-written marker,
    overwrites ``forward_cycles`` / ``meta_cycles`` from the checkpoint's
    ``counters`` block, and resets ``last_advance_consume_count`` to 0.

    Why ``last_advance_consume_count`` resets to 0 (and that is CORRECT, not a
    reset of a cycle counter): the registry/consume-count watermark is run-scoped
    and a fresh ``--run-start`` clears the registry (``delete_run_marker`` cleared
    it at the prior checkpoint). The watermark only gates whether a *future*
    consume since the last advance is real; carrying a stale watermark across the
    registry reset would suppress the first post-resume advance. Zeroing it means
    the first real dispatch after resume advances correctly ON TOP of the restored
    forward/meta totals — so the visible running total N never goes backward.

    A genuinely NEW ``/lazy-batch <N>`` invocation (no checkpoint on disk) is NOT
    affected: ``checkpoint`` is None → this is a no-op and the marker keeps the
    by-design 0/0 start.

    Args:
        checkpoint: the dict returned by ``consume_run_checkpoint()`` (or None).
            Only its ``counters`` sub-dict is consulted; absent/garbage values
            fall back to 0 so a malformed checkpoint can never crash run-start.

    Returns:
        The updated marker dict when counters were restored; None when there was
        no checkpoint, no active marker, no usable counters, OR the checkpoint was
        operator-authorized (fresh-budget resume — intentional no-op).
    """
    if not isinstance(checkpoint, dict):
        return None
    counters = checkpoint.get("counters")
    if not isinstance(counters, dict):
        return None
    marker = read_run_marker()
    if marker is None:
        return None
    # operator-checkpoint-resume-counter-reset (2026-06-17): an operator-authorized
    # checkpoint is a deliberate stop whose resume wants a FRESH 0/0 budget — skip
    # the carry-forward so the just-written marker keeps its by-design start. A
    # truthy-check makes False AND a missing field (pre-fix files / automatic
    # reliability pauses) fall through to the carry-forward path below.
    if checkpoint.get("operator_authorized"):
        return None

    def _coerce(value: object) -> int:
        # A checkpoint counter may legitimately be None (marker lacked the field
        # at checkpoint time) or a non-int from a hand-edited/corrupt file —
        # coerce to a non-negative int, never crash run-start.
        try:
            n = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
        return n if n >= 0 else 0

    def _restore_identity(candidate: object) -> None:
        # cycle-bracket-break-on-checkpoint-resume (hardening Round 35): restore the
        # RUN IDENTITY (started_at) in lockstep with the counters. A non-operator-
        # authorized resume is the SAME run continuing, so started_at (which
        # write_run_marker just MINTED afresh) must be the pre-pause identity —
        # otherwise detect_cycle_bracket_friction signal (a) false-trips
        # cycle-bracket-break. Only restore a well-formed, NON-stale-by-age value:
        # restoring a >24h-old identity would subvert read_run_marker's age gate
        # into auto-resuming a presumed-dead run, so KEEP the minted identity then.
        # A missing/blank/unparseable value leaves the minted started_at untouched.
        if isinstance(candidate, str) and candidate:
            try:
                _ident_dt = datetime.datetime.strptime(
                    candidate, "%Y-%m-%dT%H:%M:%SZ"
                )
                _ident_epoch = (
                    _ident_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if time.time() - _ident_epoch <= _MARKER_STALE_SECONDS:
                    marker["started_at"] = candidate
            except (ValueError, TypeError):
                pass  # unparseable identity → keep the freshly-minted started_at

    # adhoc-checkpoint-resume-field-complete-continuity (2026-06-23): re-apply the
    # FULL continuity block as one unit when the checkpoint carries one. This
    # closes the field-by-field whack-a-mole — every RUN_CONTINUITY_FIELDS key
    # (incl. both per_feature_* budget maps) survives a sanctioned same-run pause
    # by construction, with the per-field guards preserved:
    #   - the two counters coerce to a non-negative int (fail-safe);
    #   - started_at restores only when well-formed AND not >24h stale (age gate);
    #   - the two per_feature_* maps apply only when a well-formed dict (else the
    #     minted {} is left);
    #   - last_advance_consume_count stays FORCED to 0 (a RUN_FRESH_FIELD — the
    #     registry is freshly cleared, carrying a stale watermark would suppress
    #     the first post-resume advance; SPEC Out of Scope).
    continuity = checkpoint.get("continuity")
    if isinstance(continuity, dict) and continuity:
        if "forward_cycles" in continuity:
            marker["forward_cycles"] = _coerce(continuity.get("forward_cycles"))
        if "meta_cycles" in continuity:
            marker["meta_cycles"] = _coerce(continuity.get("meta_cycles"))
        _restore_identity(continuity.get("started_at"))
        for _map_key in ("per_feature_forward_cycles", "per_feature_corrective_cycles"):
            _val = continuity.get(_map_key)
            if isinstance(_val, dict):
                marker[_map_key] = _val
    else:
        # Back-compat: a legacy / pre-fix / mid-flight checkpoint with the flat
        # `counters` + `run_started_at` fields but NO `continuity` block still
        # restores identity + counters via the original legacy path.
        marker["forward_cycles"] = _coerce(counters.get("forward_cycles"))
        marker["meta_cycles"] = _coerce(counters.get("meta_cycles"))
        _restore_identity(checkpoint.get("run_started_at"))
    # Registry is freshly cleared on this run-start → the consume watermark must
    # start at 0 so the first real post-resume dispatch advances (see docstring).
    marker["last_advance_consume_count"] = 0
    marker_path = claude_state_dir() / _MARKER_FILENAME
    _atomic_write(marker_path, json.dumps(marker, indent=2) + "\n")
    return marker


def rebaseline_loop_signature_after_registry_reset(
    repo_root: Path,
    *,
    pipeline: str = "feature",
    signature_path: Path | None = None,
) -> bool:
    """Re-baseline the loop-detection signature file's ``consume_count`` to the
    current (freshly-cleared) registry consume-count on a checkpoint resume.

    ROOT CAUSE (checkpoint-resume-false-loop-flips-complex-part-to-sonnet, 2026-07-12):
    ``update_repeat_counts``'s F1/F2 double-probe debounce HOLDS a repeat count
    (rather than incrementing it) only when it can prove NO dispatch landed
    between two identical probes — i.e. the persisted ``consume_count`` equals the
    live ``consumed_emission_count()``. That ``consume_count`` lives in the OS-temp
    signature file (``lazy-state-last-<hash>.json``), which SURVIVES ``--run-end``.
    But a checkpoint ``--run-end`` deletes the prompt registry and the resuming
    ``--run-start`` recreates it fresh, so ``consumed_emission_count()`` resets to
    0 while the signature file still carries the PRE-checkpoint count. The first
    re-probe of the SAME ``next_route`` (which a checkpoint resume deterministically
    re-probes) then sees ``prior_consume != current``, cannot prove the re-read,
    and inflates ``repeat_count`` to 2 → a FALSE ``LOOP DETECTED`` on a route that
    was NEVER re-dispatched (a probe→checkpoint→probe is not a stall; a genuine
    stall requires a DISPATCH that failed to advance between two probes).

    The fix re-baselines ONLY the ``consume_count`` field to the fresh registry's
    count (``consumed_emission_count()`` — 0 at run-start, the registry having just
    been cleared), so the next probe of the unchanged route reads
    ``prior_consume == current`` and HOLDS. The persisted ``signature`` / ``count``
    / ``step_signature`` / ``step_count`` are PRESERVED untouched, so a GENUINE
    pre-pause loop streak (``count >= 2``) survives — the loop block still fires —
    while a never-re-attempted route no longer inflates.

    Called from the checkpoint-resume block of both state scripts' ``--run-start``
    handlers (coupled-pair mirror; the helper is shared, the call site per-script).
    ``signature_path`` defaults to the same per-repo/per-pipeline OS-temp path
    ``update_repeat_counts`` derives, so the two agree by construction.

    Returns True when the field was re-baselined; False (no-op) when no signature
    file exists, when it is unreadable/corrupt/wrong-shape, or when no run marker
    is present (the debounce is marker-gated — with no marker the next probe never
    engages it, so re-baselining would be meaningless). NEVER raises.
    """
    # Defensive coercion (checkpoint-resume-rebaseline-crashes-on-str-repo-root):
    # a real caller passed lazy_core.active_repo_root() here directly — that
    # helper returns str, not Path, and `.resolve()` below raised AttributeError
    # on it, breaking the documented "NEVER raises" contract. Path(Path(x)) is a
    # no-op for an already-Path caller, so this is byte-identical for every
    # existing correct call site.
    repo_root = Path(repo_root)
    if signature_path is None:
        repo_hash = hashlib.sha1(
            str(repo_root.resolve()).encode("utf-8")
        ).hexdigest()[:16]
        prefix = "lazy-state-last" if pipeline == "feature" else f"{pipeline}-state-last"
        signature_path = Path(tempfile.gettempdir()) / f"{prefix}-{repo_hash}.json"
    try:
        if not signature_path.exists():
            return False
        # The debounce is marker-gated (update_repeat_counts writes/reads
        # consume_count only under a live marker). At checkpoint resume the marker
        # was just written by --run-start, so it is present and age-fresh; a
        # missing marker means the next probe cannot engage the debounce anyway.
        if read_run_marker() is None:
            return False
        data = json.loads(signature_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data["consume_count"] = consumed_emission_count()
        _atomic_write(signature_path, json.dumps(data))
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False
