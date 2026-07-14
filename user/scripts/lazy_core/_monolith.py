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
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("lazy_core.py requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(2)

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
from ._ctx import _DIAGNOSTICS, _diag, _atomic_write

# lazy-core-package-decomposition Phase 2 Batch 2 (WU-2): the document-model
# (parsing) seam moved to docmodel.py. Unpatched names are imported by value;
# _VERIFICATION_ONLY_MARKER is a patched-census name, so the submodule itself
# is imported and referenced via attribute access at its remaining call sites
# (see the docmodel.<name> rewrites below).
from . import docmodel
from .docmodel import (
    parse_sentinel,
    spec_status,
    PROVISIONAL_SENTINEL,
    _PROVISIONAL_ELIGIBLE_GRADES,
)

from .statedir import (  # noqa: E402 — hook-surface seam (Phase 2 WU-5)
    claude_state_dir,
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


