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
# Diagnostics
# ---------------------------------------------------------------------------

# Diagnostics collected across helper calls. compute_state() in lazy-state.py
# resets this at the start of each invocation via clear_diagnostics(), and
# merges the list into the returned state dict before returning. Callers in
# lazy-state.py reference lazy_core._diag / lazy_core.clear_diagnostics so
# they mutate THIS list, not a separate copy.
_DIAGNOSTICS: list[str] = []


def _diag(msg: str) -> None:
    """Append a diagnostic message to the shared _DIAGNOSTICS list."""
    _DIAGNOSTICS.append(msg)


def clear_diagnostics() -> None:
    """Reset the shared _DIAGNOSTICS list (call once per compute_state invocation)."""
    _DIAGNOSTICS.clear()


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (temp file in the same dir + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
# Queue dependency DAG (queue-dependency-dag) — the optional, machine-enforced
# `deps: ["<id>", ...]` queue-entry field on BOTH pipelines.
#
# D1: the queue field is a FLAT HARD-ONLY id list — an enforcement projection
#     of the SPEC's prose `**Depends on:**` block (which stays the SSOT for
#     kinds/reasons; see _components/dep-block-schema.md "Queue projection").
# D6: v1 is same-pipeline only; `bug:` / `feature:` prefixes are RESERVED for a
#     future cross-pipeline vN and rejected loudly at every id-validation
#     chokepoint (load / --sync-deps / --enqueue-adhoc --deps).
# D4: a dependency CYCLE is corrupt script-owned machine state — `_die` exit 2
#     at queue load (Kahn's algorithm), naming the members. Dangling /
#     Superseded deps are a WALK-time fail-fast (BLOCKED.md
#     `blocker_kind: unknown-dependency` on the dependent), not a load error.
# ---------------------------------------------------------------------------

# The dep-block id regex (shared with parse_dep_block below).
_DEP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# D6 — reserved cross-pipeline prefixes (rejected in v1 so v1 bare ids stay
# forward-compatible and unambiguous when vN adds cross-queue resolution).
_RESERVED_DEP_PREFIXES: tuple[str, ...] = ("bug:", "feature:")


def parse_dep_block(spec_text: str) -> list[dict[str, str]]:
    """Parse **Depends on:** block per _components/dep-block-schema.md.

    Returns a list of {feature_id, kind, reason}. Empty list for '(none)' or
    malformed/missing block (caller decides how to handle).

    Relocated VERBATIM from lazy-state.py (queue-dependency-dag D9) so both
    state scripts share ONE parser; lazy-state.py re-exports it.
    """
    lines = spec_text.splitlines()
    deps: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip() == "**Depends on:**" or re.match(r"^\*\*Depends on:\*\*\s*\(none\)\s*$", lines[i]):
            if "(none)" in lines[i]:
                return []
            # Block-form: parse subsequent "- " lines until blank or heading
            j = i + 1
            while j < len(lines):
                line = lines[j]
                stripped = line.strip()
                if not stripped:
                    # Allow one blank line between header and list (form A in schema)
                    if not deps:
                        j += 1
                        continue
                    break
                if stripped.startswith("# ") or stripped.startswith("## ") or stripped.startswith("---"):
                    break
                if not stripped.startswith("- "):
                    break
                # Split on " — " (space em-dash space)
                payload = stripped[2:]
                parts = payload.split(" — ")
                if len(parts) >= 3:
                    feature_id, kind, reason = parts[0].strip(), parts[1].strip(), " — ".join(parts[2:]).strip()
                    if kind in ("hard", "soft", "composes") and _DEP_ID_RE.match(feature_id):
                        deps.append({"feature_id": feature_id, "kind": kind, "reason": reason})
                j += 1
            return deps
        i += 1
    return []


def dep_ids(queue_entry: "dict | None") -> list[str]:
    """Shape-tolerant read of a queue entry's optional ``deps`` field (D1).

    Returns the entry's declared hard-dependency id list. EVERY degenerate
    shape — ``None`` entry, non-dict, absent key, non-list value, non-string
    members — degrades to ``[]`` (or drops the member), because absent-field
    behavior MUST be byte-identical to today on every path. Load-time
    validation (``validate_queue_deps``) is where malformed shapes are loud;
    this read-side helper never raises.
    """
    if not isinstance(queue_entry, dict):
        return []
    raw = queue_entry.get("deps")
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, str)]


def detect_dep_cycle(entries: "list") -> "list[str] | None":
    """Detect a dependency cycle among queued entries' ``deps`` edges (D4).

    Kahn's algorithm over the sub-graph whose nodes are the QUEUED ids and
    whose edges are ``dep -> dependent`` for each declared dep that is itself
    a queued id. Edges pointing outside the queued id set (dangling deps) are
    NOT graph edges — they are the walk-time unknown-dependency surface, not a
    load-time cycle. ≤ tens of nodes in practice; cost negligible.

    Returns the SORTED list of cycle-member ids (the Kahn residue) when a
    cycle exists, else ``None``.
    """
    nodes: set[str] = set()
    for e in entries:
        if isinstance(e, dict) and isinstance(e.get("id"), str):
            nodes.add(e["id"])
    # In-degree over in-set edges only.
    indegree: dict[str, int] = {n: 0 for n in nodes}
    dependents: dict[str, list[str]] = {n: [] for n in nodes}
    for e in entries:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        if eid not in nodes:
            continue
        for d in dep_ids(e):
            if d in nodes:
                indegree[eid] += 1
                dependents[d].append(eid)
    ready = [n for n in sorted(nodes) if indegree[n] == 0]
    processed = 0
    while ready:
        n = ready.pop()
        processed += 1
        for dependent in dependents[n]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if processed == len(nodes):
        return None
    return sorted(n for n in nodes if indegree[n] > 0)


def validate_dep_id_list(
    ids: "list", queue_path: "Path | None" = None, *, context: str = "deps"
) -> None:
    """Validate a list of dependency ids at a write/load chokepoint.

    ``_die`` exit 2 (zero mutation) on: a non-string member; a reserved
    ``bug:`` / ``feature:`` prefix (D6 — cross-pipeline deps are reserved for
    vN; the message says so); an id violating the dep-block id regex. Shared
    by ``validate_queue_deps``, ``sync_deps``, and the ``--enqueue-adhoc
    --deps`` handlers so every chokepoint rejects identically.
    """
    for d in ids:
        if not isinstance(d, str):
            _die(
                f"invalid {context} member (must be a string id): {d!r}",
                queue_path,
            )
            return  # pragma: no cover
        if d.startswith(_RESERVED_DEP_PREFIXES):
            _die(
                f"invalid {context} id {d!r}: the 'bug:'/'feature:' prefixes "
                f"are reserved for future cross-pipeline deps (vN) and are "
                f"rejected in v1 — declare same-pipeline deps as bare ids",
                queue_path,
            )
            return  # pragma: no cover
        if not _DEP_ID_RE.match(d):
            _die(
                f"invalid {context} id (must match ^[a-z0-9][a-z0-9-]*$): {d!r}",
                queue_path,
            )
            return  # pragma: no cover


def validate_queue_deps(
    items: "list", queue_path: "Path", *, queue_label: str = "queue.json"
) -> None:
    """Load-time validation of the optional queue ``deps`` field (D1/D4/D6).

    Called by BOTH loaders (``load_queue`` / ``load_bug_queue``) over the raw
    queue items before any merge. ``_die`` exit 2 on: a ``deps`` value that is
    not an array; an invalid/reserved id (``validate_dep_id_list``); a
    dependency cycle among queued entries (naming the members). Entries
    without ``deps`` are untouched — a dep-less queue validates with zero
    output and zero cost beyond the key scan.
    """
    any_deps = False
    for e in items:
        if not isinstance(e, dict) or "deps" not in e:
            continue
        raw = e.get("deps")
        if not isinstance(raw, list):
            _die(
                f"{queue_label} entry {e.get('id')!r}: 'deps' must be an "
                f"array of ids, got {type(raw).__name__}",
                queue_path,
            )
            return  # pragma: no cover
        validate_dep_id_list(raw, queue_path, context=f"'deps' (entry {e.get('id')!r})")
        if raw:
            any_deps = True
    if not any_deps:
        return
    cycle = detect_dep_cycle(items)
    if cycle is not None:
        _die(
            f"{queue_label} dependency cycle detected among entries: "
            f"{', '.join(repr(c) for c in cycle)} — the queue is script-owned "
            f"state and a cycle can never unblock. Fix the SPEC dep-blocks and "
            f"re-run --sync-deps, or remove an entry via --reorder-queue --to "
            f"remove.",
            queue_path,
        )
        return  # pragma: no cover


def sync_deps(
    queue_path: "Path",
    item_id: str,
    docs_dir: "Path",
    *,
    queue_label: str = "queue.json",
) -> dict:
    """Project an item's SPEC ``**Depends on:**`` HARD deps into its queue
    entry's ``deps`` field (queue-dependency-dag D5 — the script-owned feeder).

    The SPEC dep-block stays the human/design SSOT (kinds + reasons); the
    queue field is the enforcement projection the dep-gate reads. Invoked by
    ``/spec-phases`` once the SPEC baseline is locked (deps are settled by
    then); also callable ad-hoc by the operator. Mirrors the
    ``reorder_queue``/``clear_queue_stub`` load → find → mutate →
    ``_atomic_write`` shape.

    Behavior:
      * ``hard`` deps only (``soft``/``composes`` need the upstream to exist,
        not be Complete — they stay prose-only by design), SPEC order,
        deduped, ids validated (regex + reserved ``bug:``/``feature:``
        prefixes → ``_die``).
      * Idempotent / byte-stable: equal sets → ``noop: true``, ZERO write.
      * Empty hard set: an existing ``deps`` key is REMOVED (restoring the
        byte-identical no-deps entry shape); absent key → ``noop: true``.
      * Fail-fast, zero mutation (``_die`` exit 2): missing queue id; missing
        ``SPEC.md``; a self-dep; a projection that would create a queue cycle
        (which would brick every subsequent probe at load — D4).

    Args:
        queue_path: the pipeline's queue.json.
        item_id: the queue entry id to sync.
        docs_dir: the pipeline docs root the entry's ``spec_dir`` resolves
            under (``docs/features`` or ``docs/bugs``).
        queue_label: diagnostic label ("queue.json" vs "bugs/queue.json").

    Returns ``{"synced": bool, "noop": bool, "item_id": str,
    "deps": [<ids>], "queue_length": int}``.
    """
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
    idx = next(
        (i for i, e in enumerate(items)
         if isinstance(e, dict) and e.get("id") == item_id),
        None,
    )
    if idx is None:
        _die(f"item not queued: {item_id}", queue_path)
        return {}  # pragma: no cover
    entry = items[idx]

    spec_dir = entry.get("spec_dir") or item_id
    spec_md = docs_dir / spec_dir / "SPEC.md"
    if not spec_md.exists():
        _die(
            f"--sync-deps: no SPEC.md for {item_id!r} at {spec_md} — nothing "
            f"to project (author the SPEC dep-block first)",
            queue_path,
        )
        return {}  # pragma: no cover
    try:
        spec_text = spec_md.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"--sync-deps: cannot read {spec_md}: {exc}", queue_path)
        return {}  # pragma: no cover

    hard: list[str] = []
    for d in parse_dep_block(spec_text):
        if d.get("kind") == "hard" and d["feature_id"] not in hard:
            hard.append(d["feature_id"])
    validate_dep_id_list(hard, queue_path, context=f"'deps' (sync {item_id!r})")
    if item_id in hard:
        _die(
            f"--sync-deps: {item_id!r} declares a hard dep on itself — a "
            f"self-dependency can never unblock. Fix the SPEC dep-block.",
            queue_path,
        )
        return {}  # pragma: no cover

    current = entry.get("deps")
    if hard:
        if current == hard:
            return {"synced": True, "noop": True, "item_id": item_id,
                    "deps": hard, "queue_length": len(items)}
        entry["deps"] = hard
    else:
        if "deps" not in entry:
            return {"synced": True, "noop": True, "item_id": item_id,
                    "deps": [], "queue_length": len(items)}
        entry.pop("deps", None)

    # D4 write-side guard: never persist a projection that would cycle the
    # queued graph (a cycle bricks every subsequent probe at load). Checked on
    # the POST-mutation in-memory items; _die leaves the file untouched.
    cycle = detect_dep_cycle(items)
    if cycle is not None:
        _die(
            f"--sync-deps: projecting {item_id!r}'s hard deps would create a "
            f"dependency cycle among queued entries: "
            f"{', '.join(repr(c) for c in cycle)} — refusing to write. Fix "
            f"the SPEC dep-blocks first.",
            queue_path,
        )
        return {}  # pragma: no cover

    data["queue"] = items
    _atomic_write(queue_path, json.dumps(data, indent=2) + "\n")
    _diag(
        f"sync-deps: projected {item_id!r} hard deps {hard!r} into "
        f"{queue_label}"
    )
    return {"synced": True, "noop": False, "item_id": item_id,
            "deps": hard, "queue_length": len(items)}


def dep_completion_status(
    dep_id: str,
    repo_root: "Path",
    *,
    pipeline: str,
    id_dir_map: "dict | None" = None,
) -> str:
    """Classify a declared dependency for gating purposes (D3 — receipt-gated).

    Returns one of:
      * ``"complete"`` — the dep's dir resolves with the pipeline's terminal
        status AND a content-valid completion receipt
        (feature: ``**Status:** Complete`` + ``COMPLETED.md``;
        bug: ``**Status:** Fixed`` + ``FIXED.md``) — the EXACT completion
        definition ``__mark_complete__`` / ``__mark_fixed__`` already enforce.
      * ``"incomplete"`` — the dir resolves but the dep is not (provably)
        done: any working status, a claimed terminal status WITHOUT a valid
        receipt, or a dir with no parseable SPEC yet (an ad-hoc seed). A
        still-workable queued item always classifies here, so
        "still-queued ⇒ incomplete" holds by construction.
      * ``"unsatisfiable-superseded"`` / ``"unsatisfiable-wont-fix"`` — the
        dep was retired without the work happening (``Superseded`` /
        ``Won't-fix``); the dependent must fail fast (D4), never silently
        hold.
      * ``"missing"`` — no dir resolves anywhere (a dangling id) — the D4
        fail-fast surface.

    Resolution: ``id_dir_map`` (the caller's queued id → dir map, honoring a
    custom ``spec_dir``) wins; then the canonical ``docs/features/<id>/`` —
    or, for the bug pipeline, ``docs/bugs/<id>/`` THEN
    ``docs/bugs/_archive/<id>/`` (``__mark_fixed__`` archives on fix — the D9
    justified divergence). For the FEATURE pipeline ONLY, if the flat
    canonical path does not resolve, a recursive-by-id fallback searches under
    ``docs/features`` for a directory named exactly ``<dep_id>`` that contains
    a ``SPEC.md`` (deterministic first-in-sorted-order on the improbable
    multi-match). This mirrors the ``dep-block-ids-exist`` contract
    (``<feature-id>`` may resolve to a queue.json entry id OR an existing
    ``docs/features/.../<id>/SPEC.md``) and how a queue ``spec_dir`` permits an
    arbitrary nested path — a Complete feature stays in place (no ``_archive``)
    at a domain-nested path (e.g.
    ``docs/features/mixer/dj-capabilities/domains/f1-global-scale/``) and would
    otherwise be misclassified ``missing``. Pure on-disk reads; no LLM
    judgment, no new state.
    """
    candidates: list = []
    if id_dir_map and dep_id in id_dir_map:
        candidates.append(Path(id_dir_map[dep_id]))
    if pipeline == "bug":
        candidates.append(repo_root / "docs" / "bugs" / dep_id)
        candidates.append(repo_root / "docs" / "bugs" / "_archive" / dep_id)
        terminal_status, receipt_name, retired, retired_tag = (
            "Fixed", "FIXED.md", "Won't-fix", "unsatisfiable-wont-fix",
        )
    else:
        candidates.append(repo_root / "docs" / "features" / dep_id)
        # Recursive-by-id fallback (feature pipeline only): a Complete feature
        # leaves queue.json (absent from id_dir_map) and has NO _archive/, so a
        # domain-nested Complete spec falls through both prior candidates.
        # Search docs/features for a dir named exactly <dep_id> holding a
        # SPEC.md; the existing loop then classifies it. Sorted for
        # determinism; guard against docs/features not existing.
        features_root = repo_root / "docs" / "features"
        if features_root.is_dir():
            nested = sorted(
                m.parent
                for m in features_root.rglob(f"{dep_id}/SPEC.md")
                if m.parent.name == dep_id
            )
            candidates.extend(nested)
        terminal_status, receipt_name, retired, retired_tag = (
            "Complete", "COMPLETED.md", "Superseded",
            "unsatisfiable-superseded",
        )
    for d in candidates:
        if not d.exists() or not d.is_dir():
            continue
        status = spec_status(d)
        if status == retired:
            return retired_tag
        if status == terminal_status and has_completion_receipt(
            d, filename=receipt_name
        ):
            return "complete"
        # Resolvable but not provably done (working status, claimed-terminal
        # without receipt, or no SPEC yet) — the dependent holds.
        return "incomplete"
    return "missing"


def format_unknown_dependency_blocker(
    item_id: str, dep_id: str, status: str, known_ids: "list | set"
) -> str:
    """Build the BLOCKED.md body for the D4 unknown-dependency fail-fast.

    Written on the DEPENDENT when a declared queue dep is a dangling id
    (``missing``) or a retired upstream (``unsatisfiable-superseded`` /
    ``unsatisfiable-wont-fix``). Names the offending id, WHY it can never
    complete, and the known queued-id set — the
    ``format_unknown_host_capability_blocker`` shape, for the same reason: a
    silent hold on an unsatisfiable dep is infinite queue starvation. Shared
    so the bug-pipeline parity mirror is a one-line reuse.
    """
    why = {
        "missing": (
            "the id resolves to no on-disk item (open or archived) and no "
            "queued entry — a dangling reference (typo, renamed slug, or a "
            "removed item)"
        ),
        "unsatisfiable-superseded": (
            "the upstream is Superseded — it was retired without the work "
            "happening, so this dependency can never become Complete"
        ),
        "unsatisfiable-wont-fix": (
            "the upstream is Won't-fix — it was retired without the work "
            "happening, so this dependency can never become Fixed"
        ),
    }.get(status, f"the dependency classified {status!r}")
    known_sorted = sorted(set(known_ids))
    known_line = (
        ", ".join(f"`{k}`" for k in known_sorted) if known_sorted
        else "(none queued)"
    )
    return (
        "# Blocked — unknown dependency\n\n"
        "## Details\n\n"
        f"Item `{item_id}` declares a queue dependency (`deps`) on "
        f"`{dep_id}`, but {why}.\n\n"
        f"Classification: `{status}`.\n\n"
        "An unsatisfiable dependency would hold this item forever (silent, "
        "infinite queue starvation), so this is a loud, immediate validation "
        "failure instead (blocker_kind: unknown-dependency).\n\n"
        "## Known queued ids\n\n"
        f"{known_line}\n\n"
        "## Recovery Suggestion\n\n"
        "Either fix the dep id in the item's SPEC `**Depends on:**` block and "
        "re-run `--sync-deps --id " + item_id + "`, or drop the dependency "
        "(edit the SPEC block, re-sync), or — if the upstream really is "
        "retired — redesign this item against a live upstream. Then rename/"
        "neutralize this BLOCKED.md.\n"
    )


# ---------------------------------------------------------------------------
# Sentinel parsing (per _components/sentinel-frontmatter.md)
# ---------------------------------------------------------------------------

_FENCE = "---"


# A flat top-level `key: value` frontmatter line (no leading indentation).
# Group 1 = key, group 2 = the value (everything after the first colon+space).
_FLAT_SCALAR_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]+(.*)$")


def _yaml_load_tolerant(yaml_body: str) -> dict[str, Any] | None:
    """Rescue an unquoted colon-space (or trailing-colon) scalar VALUE.

    Called ONLY on the `yaml.YAMLError` path of parse_sentinel (well-formed
    frontmatter never reaches here — it parsed strictly). Operates per-line: for
    each flat top-level ``key: value`` line whose value is a plain (unquoted, non
    flow-collection, non block-scalar) scalar, single-quote the value so an
    embedded ``: `` / trailing ``:`` is read as a literal instead of a nested
    mapping. Re-invokes ``yaml.safe_load``; returns the dict on success or None
    (caller then falls through to the original ``_die`` — genuinely-malformed
    frontmatter, e.g. a broken indented block or an unclosed flow collection, is
    NOT rescued and still hard-halts). Strict schema semantics for keys/kinds are
    preserved: only VALUES are quoted, never keys or structure.
    """
    out_lines: list[str] = []
    for line in yaml_body.splitlines():
        m = _FLAT_SCALAR_LINE_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        key, value = m.group(1), m.group(2).rstrip()
        # Leave values that are empty (null), already quoted, a flow collection,
        # a block-scalar indicator, or an anchor/alias/tag — quoting those would
        # change meaning or is unnecessary.
        if not value or value[0] in ("'", '"', "[", "{", "|", ">", "&", "*", "!", "#"):
            out_lines.append(line)
            continue
        escaped = value.replace("'", "''")
        out_lines.append(f"{key}: '{escaped}'")
    rescued = "\n".join(out_lines)
    try:
        data = yaml.safe_load(rescued)
    except yaml.YAMLError:
        return None
    if isinstance(data, dict):
        return data
    return None


def _yaml_fallback_scalar(value: Any) -> str:
    """Render a scalar VALUE for the no-PyYAML manual frontmatter fallback.

    The state scripts' ``_write_yaml_sentinel`` ImportError fallback emits
    ``f"{k}: {v}"`` pairs by hand (used only when PyYAML is unavailable). A raw
    ``str(value)`` for a value carrying a colon-space (``a: b``) or a trailing
    colon (``waiting on:``) is INVALID YAML — the sentinel would then hard-halt
    ``parse_sentinel`` on re-read. This quotes exactly those two cases (parity
    with what ``yaml.safe_dump`` emits), single-quoting the value and doubling
    any embedded single quote. A colon-free string, a colon-WITHOUT-space string
    (``build:step`` — a valid plain scalar), and non-string values are rendered
    unchanged (``str(value)``), so the common-case output is byte-identical to
    before (skip-mcp-test-frontmatter-unquoted-colon — quote-on-write).
    """
    if isinstance(value, str) and (": " in value or value.endswith(":")):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def parse_sentinel(path: Path) -> dict[str, Any] | None:
    """Parse a sentinel file's YAML frontmatter. Returns dict or None if absent."""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        _die(f"cannot read sentinel: {exc}", path)
        return None  # pragma: no cover

    lines = raw.splitlines()
    # Skip leading blank lines
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != _FENCE:
        # No frontmatter — treat as legacy/freeform; return empty dict so callers
        # can distinguish "file exists" from "file absent".
        return {}

    # Find closing fence
    start = i + 1
    end = None
    for j in range(start, len(lines)):
        if lines[j].strip() == _FENCE:
            end = j
            break
    if end is None:
        _die("sentinel frontmatter missing closing '---'", path)
        return None  # pragma: no cover

    yaml_body = "\n".join(lines[start:end])
    try:
        data = yaml.safe_load(yaml_body) or {}
    except yaml.YAMLError as exc:
        # Tolerant re-parse: an unquoted colon-space (or trailing-colon) in a
        # flat scalar value is quoted on-read and re-loaded. Only rescues that
        # narrow case; genuinely-malformed frontmatter still falls through to
        # _die below (skip-mcp-test-frontmatter-unquoted-colon).
        rescued = _yaml_load_tolerant(yaml_body)
        if rescued is not None:
            return rescued
        _die(f"invalid YAML frontmatter: {exc}", path)
        return None  # pragma: no cover
    if not isinstance(data, dict):
        _die("sentinel frontmatter must be a YAML mapping", path)
        return None  # pragma: no cover
    return data


# Pipeline-authored `skipped_by` values. A SKIP_MCP_TEST.md whose skipped_by
# identifies the pipeline as the author but which carries NO granted_by field
# is the omission side-door skip_waiver_refusal() closes — without this list,
# simply leaving granted_by off the frontmatter bypassed the WU-5 provenance
# gate (absent was unconditionally treated as legacy-operator).
_PIPELINE_SKIPPED_BY = ("lazy", "lazy-cloud", "pipeline")


# App-surface detection for the structural MCP-skip short-circuit
# (lazy-cycle-containment follow-up). A repo with NO Tauri app and NO npm
# package has no MCP-reachable / dev-server surface at all, so a feature whose
# PHASES declares `**MCP runtime:** not-required` is MECHANICALLY untestable.
# The pipeline may grant the MCP skip inline (no /mcp-test subagent) WITHOUT
# weakening skip_waiver_refusal: that gate RE-VERIFIES this same predicate
# before accepting a ``granted_by: pipeline-structural`` waiver, so a repo that
# actually has an app surface can never auto-waive.
_APP_SURFACE_MARKERS = ("src-tauri", "package.json")


def repo_has_no_app_surface(repo_root: Path) -> bool:
    """True iff repo_root contains neither a ``src-tauri/`` dir nor ``package.json``.

    Mechanical proof that the repo has no Tauri/MCP/npm surface to drive an MCP
    HTTP tool against. Conservative by design: ANY marker present → False (an app
    surface may exist, so the skip must be EARNED by /mcp-test, not auto-granted),
    and an unreadable repo root → False (cannot prove absence).
    """
    try:
        if (repo_root / "src-tauri").is_dir():
            return False
        if (repo_root / "package.json").is_file():
            return False
    except OSError:
        return False
    return True


def repo_uses_cognito_planner(repo_root: Path) -> bool:
    """True iff ``repo_root`` ships the repo-scoped ``write-plan-cognito`` planner.

    The Cognito Forms repo installs a repo-scoped lane planner at
    ``.claude/skills/write-plan-cognito/`` (the renamed-from-``write-plan``
    variant). Its presence is the deterministic signal that pipeline dispatch
    should emit ``write-plan-cognito`` for this repo rather than the generic
    ``write-plan``. Keying off the installed skill — not a hardcoded repo name
    or worktree path — keeps the discriminator aligned with the rename and
    survives additional worktrees. Conservative: an unreadable repo root or a
    missing skill dir → False, so non-Cognito repos keep the generic planner.
    """
    try:
        return (repo_root / ".claude" / "skills" / "write-plan-cognito").is_dir()
    except OSError:
        return False


def phases_mcp_runtime_not_required(spec_path: Path) -> bool:
    """True iff ``spec_path/PHASES.md`` declares ``**MCP runtime:** not-required``.

    The PHASES ``**MCP runtime:**`` line is authored by /spec-phases at
    decomposition time and is ROUTING, not a waiver — it gates the structural
    MCP-skip short-circuit alongside repo_has_no_app_surface().
    """
    phases_path = spec_path / "PHASES.md"
    if not phases_path.exists():
        return False
    try:
        text = phases_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"(?mi)^\*\*MCP runtime:\*\*\s*not-required\b", text))


def skip_waiver_refusal(
    meta: dict[str, Any] | None, repo_root: Path | None = None
) -> str | None:
    """Return a refusal reason when a SKIP_MCP_TEST.md waiver lacks trustworthy provenance.

    Single source of truth for the Step-9 / pseudo-skill provenance gate —
    called by lazy-state.py and bug-state.py (Step 9, cloud + workstation
    branches) and by apply_pseudo's ``__write_validated_from_skip__``.
    Returns None when the waiver is acceptable, else a human-readable reason
    fragment (callers prefix it with the sentinel filename / feature name).

    Provenance contract (sentinel-frontmatter.md ``granted_by``):
      - ``operator`` — human-reviewed waiver: accepted.
      - ``mcp-test`` — granted by an /mcp-test validation cycle after
        cross-checking docs/features/mcp-testing/SPEC.md. Accepted ONLY when
        the sentinel also carries a non-empty ``spec_class`` field citing the
        untestable class it verified — the citation is what distinguishes a
        verified structural assessment from a convenience skip.
      - ``pipeline-structural`` — auto-granted inline by the state machine for a
        ``**MCP runtime:** not-required`` feature in a repo with no app surface
        (lazy-cycle-containment follow-up). Accepted ONLY when ``repo_root`` is
        provided AND ``repo_has_no_app_surface(repo_root)`` RE-VERIFIES (no
        ``src-tauri/`` and no ``package.json``). This re-check is what keeps the
        gate intact: an app repo re-verifies to False and the waiver is refused,
        so a structural grant can never vacuously validate a feature that
        actually has an MCP-reachable surface.
      - ``pipeline`` (or any unrecognized value) — self-granted by a
        non-validation pipeline step: refused.
      - absent — legacy files predate the field. Accepted UNLESS ``skipped_by``
        identifies a pipeline author (``lazy`` / ``lazy-cloud`` / ``pipeline``):
        a pipeline-written skip with no provenance field is refused, closing
        the omission loophole.
    """
    meta = meta or {}
    granted = meta.get("granted_by")
    if granted == "operator":
        return None
    if granted == "mcp-test":
        spec_class = str(meta.get("spec_class") or "").strip()
        if spec_class:
            return None
        return (
            "is granted_by: mcp-test without a spec_class citation — an "
            "mcp-test-granted skip must cite the untestable class it verified "
            "against docs/features/mcp-testing/SPEC.md (add `spec_class: "
            "<class>`), or an operator must confirm via granted_by: operator."
        )
    if granted == "pipeline-structural":
        # Structural auto-grant: accept ONLY when the no-app-surface predicate
        # re-verifies against the live repo. This does not weaken the gate — it
        # is a mechanical re-proof, not a trust-the-sentinel bypass.
        if repo_root is not None and repo_has_no_app_surface(repo_root):
            return None
        return (
            "is granted_by: pipeline-structural but the repo has an app surface "
            "(src-tauri/ or package.json present) or the structural check could "
            "not be re-verified — a structural skip is valid ONLY in a repo with "
            "no MCP-reachable surface. Run /mcp-test to earn the skip, or have an "
            "operator confirm via granted_by: operator."
        )
    if granted is None:
        if meta.get("skipped_by") in _PIPELINE_SKIPPED_BY:
            return (
                f"was written by the pipeline (skipped_by: "
                f"{meta.get('skipped_by')}) with NO granted_by provenance — a "
                "pipeline-authored skip cannot vacuously validate without "
                "provenance. Set granted_by: mcp-test (+ spec_class) if an "
                "/mcp-test cycle verified structural untestability, or have an "
                "operator confirm via granted_by: operator."
            )
        # Legacy file with no provenance fields at all — grandfathered as
        # operator-granted (backward compatibility for pre-WU-5 sentinels).
        return None
    # "pipeline" and any unrecognized value: refuse.
    return (
        f"was granted_by: {granted} (self-granted) — a pipeline-granted MCP "
        "skip needs operator confirmation before it can vacuously validate. "
        "Reconcile via NEEDS_INPUT or update granted_by to 'operator'."
    )


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

def spec_status(spec_path: Path | None) -> str | None:
    """Return the feature SPEC.md ``**Status:**`` value (first occurrence), or None.

    The first ``**Status:**`` line wins; later occurrences are usually inside
    Implementation Notes blocks describing prior state.

    Generalized from lazy-state.py for reuse in bug-state.py (Phase 2).
    Default behavior (SPEC.md filename) is preserved byte-for-byte.
    """
    if spec_path is None:
        return None
    spec_md = spec_path / "SPEC.md"
    if not spec_md.exists():
        return None
    try:
        for line in spec_md.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\*\*Status:\*\*\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return None


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


# park-provisional-acceptance: the filename state a provisionally-accepted
# NEEDS_INPUT.md is renamed to by provisionalize_sentinel(). It stays
# `kind: needs-input` in frontmatter — the FILENAME is the state carrier
# (same convention as the `_RESOLVED_` rename; kind-flips are the documented
# anti-pattern). Park-mode probes treat the file as workable; non-park probes
# halt on `needs-ratification`; the completion pseudo-skills refuse while it
# exists (the triple-layer backstop, SPEC D6).
PROVISIONAL_SENTINEL = "NEEDS_INPUT_PROVISIONAL.md"

# The closed divergence-grade vocabulary (SPEC D3). File-level = the MOST
# SEVERE grade across the file's decisions. Only these two low grades are
# provisional-eligible; `structural`, unknown values, and ABSENT grades all
# fail closed (park for the operator).
_PROVISIONAL_ELIGIBLE_GRADES = frozenset({"isolated", "contained"})


def build_parked_entry(item_id: str, sentinel_path: Path) -> dict[str, Any]:
    """Build a parked-entry record for use in the ``parked[]`` output array.

    Called by lazy-state.py and bug-state.py when park mode
    (``--park-needs-input`` and/or ``--park-blocked``) is active and a queue
    entry carries an unresolved NEEDS_INPUT.md or a feature/bug-local BLOCKED.md.
    The returned dict is appended to the module-level ``_PARKED`` list in each
    script so the orchestrator can surface every parked item without halting.

    Contract (locked by WU-1 Phase 4 + park-mode-halts-on-blocked Phase 3 tests
    in test_lazy_core.py):
      - ``"id"``             → ``item_id`` (str), unchanged.
      - ``"sentinel"``       → ``str(sentinel_path)``.
      - ``"decision_count"`` → ``len(decisions)`` where ``decisions`` is the
                               ``decisions:`` YAML list in the NEEDS_INPUT.md
                               frontmatter; **0** if absent, empty, or not a list
                               (a BLOCKED.md has no ``decisions:`` list → 0).
      - ``"parked_since"``   → the ``date:`` frontmatter value (str), or
                               ``None`` if absent.
      - ``"sentinel_kind"``  → derived from ``sentinel_path.name``:
                               ``"blocked"`` for ``BLOCKED.md``,
                               ``"needs-input"`` for ``NEEDS_INPUT.md``,
                               else ``"unknown"`` (defensive — never raises).
                               Lets the flush distinguish a blocked-parked item
                               from a needs-input one without filesystem
                               inspection (SPEC D4).

    Reuses ``parse_sentinel()`` for frontmatter parsing.  Missing file,
    missing field, and wrong-type (scalar) inputs are handled defensively and
    do not raise.  Structurally corrupt frontmatter (missing closing fence,
    invalid YAML, non-mapping root) routes through ``parse_sentinel``'s
    ``_die()`` → ``sys.exit(2)``, consistent with all other sentinel parsing
    in this codebase.
    """
    meta = parse_sentinel(sentinel_path) or {}
    decisions = meta.get("decisions")
    if not isinstance(decisions, list):
        decision_count = 0
    else:
        decision_count = len(decisions)
    parked_since = meta.get("date")
    # Coerce to str if present (YAML may deserialize dates as date objects).
    if parked_since is not None:
        parked_since = str(parked_since)
    # sentinel_kind: derive from the sentinel filename (additive, never raises).
    name = sentinel_path.name
    if name == "BLOCKED.md":
        sentinel_kind = "blocked"
    elif name == "NEEDS_INPUT.md":
        sentinel_kind = "needs-input"
    elif name == PROVISIONAL_SENTINEL:
        # park-provisional-acceptance: an auto-accepted-on-recommendation
        # sentinel awaiting operator ratification (Step-10 park + flush
        # ratification branch key on this kind).
        sentinel_kind = "provisional"
    else:
        sentinel_kind = "unknown"
    return {
        "id": item_id,
        "sentinel": str(sentinel_path),
        "decision_count": decision_count,
        "parked_since": parked_since,
        "sentinel_kind": sentinel_kind,
    }


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
# Plan file parsing
# ---------------------------------------------------------------------------

def _parse_plan_frontmatter(path: Path) -> dict[str, Any] | None:
    """Parse a plan file's YAML frontmatter per _components/plan-frontmatter.md.

    Returns:
      - dict with parsed YAML if frontmatter is present and valid.
      - {} (empty dict) if the file has no frontmatter block (legacy plan).
      - None only if the file cannot be read (caller treats as missing).

    Plan files share the parsing protocol of sentinel files but live in a
    disjoint kind namespace (implementation-plan / retro-plan / fix-plan /
    realign-plan). On malformed YAML, _die() halts via the same path as
    sentinels — parse errors should not be swallowed.
    """
    if not path.exists():
        return None
    return parse_sentinel(path)


def _plan_status(path: Path) -> str:
    """Return the plan's ``status:`` field. Defaults to 'Ready' for legacy plans
    (no frontmatter); caller records a diagnostics warning in that case.
    """
    meta = _parse_plan_frontmatter(path) or {}
    if not meta:
        return "Ready"
    raw = meta.get("status")
    if isinstance(raw, str) and raw:
        return raw
    return "Ready"


# The canonical per-plan-part complexity tier set (Phase 9 —
# lazy-validation-readiness). Mirrors the ``_VALID_PHASE_KINDS`` Phase-8 pattern
# for the per-PHASE ``**Phase kind:**`` marker, but lives in plan-part YAML
# frontmatter (``complexity:``) instead. ``complex`` is the CONSERVATIVE default:
# an untagged / unrecognized / unreadable plan dispatches on Opus (the safe,
# full-capability tier). Only an explicit, recognized ``mechanical`` tag —
# emitted by /write-plan when a part's WUs are ALL genuinely mechanical —
# downgrades the /execute-plan cycle to Sonnet. The model NEVER auto-guesses the
# tier at dispatch; it trusts only the tag /write-plan deliberately wrote.
_VALID_PLAN_COMPLEXITIES = frozenset({"mechanical", "complex"})
_DEFAULT_PLAN_COMPLEXITY = "complex"


def plan_complexity(path: Path) -> str:
    """Return a plan part's ``complexity:`` tier — ``"mechanical"`` or ``"complex"``.

    Reads the per-plan-part ``complexity`` field from the plan file's YAML
    frontmatter (per ``_components/plan-frontmatter.md``). Phase 9 —
    lazy-validation-readiness; mirrors ``_plan_status``'s lookup shape.

    Defaults to the SAFE tier ``"complex"`` (→ Opus dispatch) in every uncertain
    case — a legacy plan with no frontmatter, an absent ``complexity`` field, an
    unrecognized value, or a missing/unreadable file. Only an explicit,
    case-insensitively-recognized ``mechanical`` tag returns ``"mechanical"``.
    This makes the model-tiering back-compatible (every pre-Phase-9 plan keeps
    dispatching on Opus) and conservative (an ambiguous tag never silently
    downgrades implementation quality).
    """
    meta = _parse_plan_frontmatter(path) or {}
    if not meta:
        return _DEFAULT_PLAN_COMPLEXITY
    raw = meta.get("complexity")
    if isinstance(raw, str):
        norm = raw.strip().lower()
        if norm in _VALID_PLAN_COMPLEXITIES:
            return norm
    return _DEFAULT_PLAN_COMPLEXITY


def _plan_lowest_phase(path: Path) -> tuple[int, str]:
    """Return a sort key (lowest_phase_number, plan_name).

    Falls back to (sys.maxsize, name) when the plan lacks a ``phases:`` field —
    that means feature-wide / unspecified plans sort after phase-tagged ones,
    matching the user's requested ordering (lowest declared phase wins).
    """
    meta = _parse_plan_frontmatter(path) or {}
    phases = meta.get("phases") if meta else None
    lowest = sys.maxsize
    if isinstance(phases, list):
        for entry in phases:
            try:
                n = int(entry)
            except (TypeError, ValueError):
                # Non-numeric phase identifiers (e.g. "all", "P3a") — extract
                # any leading digit run, else skip. Mirrors the lenient handling
                # in latest_retro_plan().
                if isinstance(entry, str):
                    m = re.match(r"^(\d+)", entry)
                    if m:
                        n = int(m.group(1))
                    else:
                        continue
                else:
                    continue
            if n < lowest:
                lowest = n
    return (lowest, path.name)


# Recognizes the ``-part-K`` suffix /write-plan emits when it partitions a
# feature into a multi-part plan series (see write-plan/SKILL.md Step 2.5 naming
# rule: ``all-phases-<slug>-part-1.md``, ``...-part-2.md``, etc., and the
# ``> **Plan series:** part K of N`` preamble whose contract is "Execute parts
# strictly in order"). The K is captured just before the ``.md`` suffix.
_PLAN_PART_RE = re.compile(r"-part-(\d+)(?:\.md)?$", re.IGNORECASE)


def _plan_series_index(path: Path) -> int | None:
    """Return the 1-based part index K from a ``...-part-K.md`` plan filename.

    Returns None when the filename carries no ``-part-K`` suffix (a single-part
    or legacy plan). A frontmatter ``series_index:`` field, when present, takes
    precedence over the filename — this lets a producer carry the authoritative
    order machine-readably without renaming files. ``series_index:`` is an
    OPTIONAL, lazy-only ordering hint: it is read here but is NOT in the
    plan-frontmatter REQUIRED/OPTIONAL key set parsed by AlgoBooth's
    check-docs-consistency.ts, so it MUST stay filename-derived in the common
    case to avoid forcing a consumer-lockstep schema change. Prefer the filename
    suffix; reserve the frontmatter field for the rare case where the filename
    cannot encode the order.
    """
    meta = _parse_plan_frontmatter(path) or {}
    raw = meta.get("series_index") if meta else None
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    m = _PLAN_PART_RE.search(path.name)
    if m:
        return int(m.group(1))
    return None


def _plan_sort_key(path: Path) -> tuple[int, int, str]:
    """Authoritative execution-order sort key for implementation plans.

    Returns ``(series_index, lowest_phase, name)``.

    ROOT-CAUSE FIX (ISSUE 1 — d8-effect-chains live /lazy-batch run, 2026-06-14):
    A /realign-spec corrective Phase 6 was a PREREQUISITE for the pre-existing
    Phase 5 (Phase 5 documents the ``.cab()``/``.reverb()`` API that Phase 6
    builds). /write-plan emitted part-1 ``phases: [6]`` (the prerequisite) and
    part-2/part-3 ``phases: [5]`` (depend on part-1). Sorting purely by
    ``_plan_lowest_phase`` (phase number) routed part-2 (Phase 5) BEFORE part-1
    (Phase 6) — inverting the declared "Execute parts strictly in order"
    contract — so the router oscillated (step_repeat_count hit 3) and the
    execute-plan subagent silently deviated to part-1.

    The ``-part-K`` series index is the DECLARED, authoritative execution order
    ("part K of N … Execute parts strictly in order"). It therefore sorts FIRST,
    ahead of raw phase number. This makes a prerequisite phase numbered HIGHER
    than its dependents (part-1=Phase 6 before part-2=Phase 5) route correctly
    as long as the producer wrote the parts in dependency order — which is the
    series invariant. Plans with no ``-part-K`` suffix carry series_index
    sys.maxsize so they sort after an explicit part series but among themselves
    fall back to the prior (lowest_phase, name) behavior — preserving the
    single-plan / non-series ordering exactly.
    """
    idx = _plan_series_index(path)
    series = idx if idx is not None else sys.maxsize
    lowest, name = _plan_lowest_phase(path)
    return (series, lowest, name)


def _plan_phase_set(plan_path: Path) -> set[int]:
    """Return the set of phase numbers declared in a plan's ``phases:`` field.

    Empty set when the plan has no ``phases:`` field or all entries fail to parse.
    Mirrors the leniency in _plan_lowest_phase(): non-numeric entries with a
    leading digit run (e.g. "3a") contribute that integer; pure-string entries
    (e.g. "all") are skipped.
    """
    meta = _parse_plan_frontmatter(plan_path) or {}
    raw = meta.get("phases") if meta else None
    out: set[int] = set()
    if not isinstance(raw, list):
        return out
    for entry in raw:
        try:
            out.add(int(entry))
            continue
        except (TypeError, ValueError):
            pass
        if isinstance(entry, str):
            m = re.match(r"^(\d+)", entry)
            if m:
                out.add(int(m.group(1)))
    return out


def _unchecked_wus_in_plan_scope(phases_text: str, phase_set: set[int]) -> list[str]:
    """Return the unchecked-WU label strings in PHASES.md scoped to the plan's phases.

    Walks PHASES.md tracking the current ``### Phase N`` heading; collects each
    ``- [ ] <label>`` line whose enclosing phase number is in ``phase_set``. A line
    starting with ``## `` resets phase tracking (new top-level section).
    """
    current_phase: int | None = None
    out: list[str] = []
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        # Toggle fence state; fence markers are not headings or deliverables.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Lines inside a code fence are illustrative examples — not real WUs.
            continue
        h = re.match(r"^###\s+Phase\s+(\d+)", line)
        if h:
            current_phase = int(h.group(1))
            continue
        if line.startswith("## "):
            current_phase = None
            continue
        if current_phase is None or current_phase not in phase_set:
            continue
        m = re.match(r"^\s*-\s*\[\s*\]\s*(.+?)\s*$", line)
        if m:
            out.append(m.group(1))
    return out


def _all_wus_in_plan_scope(phases_text: str, phase_set: set[int]) -> list[str]:
    """Return ALL deliverable label strings — checked ([x]) AND unchecked ([ ]) —
    in PHASES.md scoped to the plan's phases.

    Companion to ``_unchecked_wus_in_plan_scope()``. The stale-plan gate uses the
    TOTAL row count to disambiguate the two cases that an empty
    ``_unchecked_wus_in_plan_scope()`` result conflates:

      (a) every referenced WU is already ``[x]``  -> unchecked empty, TOTAL non-empty
          -> the plan is genuinely stale (work done, frontmatter never flipped).
      (b) the plan's ``phases:`` scope resolves to ZERO rows  -> unchecked empty AND
          TOTAL empty -> the scope is UNDEFINED in PHASES.md (e.g. a ``phases: [0]``
          decomposition part with no matching ``### Phase 0`` section — write-plan
          emits these for touchpoint-audit ``block`` verdicts and tracks the
          decomposition WUs in the PLAN BODY, not a PHASES Phase 0). This is NOT a
          "work done" signal; declaring it stale would vacuously flip the plan
          Complete and silently drop the work. The gate must fall through (to the
          plan's own per-WU checkboxes, then to /execute-plan) instead.

    Same fence/heading/``## `` reset walk as ``_unchecked_wus_in_plan_scope()`` — only
    the checkbox-mark class differs (``[ xX]`` here vs. unchecked-only there).
    """
    current_phase: int | None = None
    out: list[str] = []
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        h = re.match(r"^###\s+Phase\s+(\d+)", line)
        if h:
            current_phase = int(h.group(1))
            continue
        if line.startswith("## "):
            current_phase = None
            continue
        if current_phase is None or current_phase not in phase_set:
            continue
        m = re.match(r"^\s*-\s*\[\s*[xX]?\s*\]\s*(.+?)\s*$", line)
        if m:
            out.append(m.group(1))
    return out


def find_implementation_plans(spec_dir: Path) -> list[Path]:
    """Find non-retro implementation plans, filtering out plans whose
    frontmatter marks them Complete, and sorting by the lowest ``phases:``
    entry (alphabetical fallback for plans without phases:).

    Mirrors /lazy Step 7a. See _components/plan-frontmatter.md for the schema.
    Plans with no frontmatter are treated as legacy ``status: Ready`` and
    surface a diagnostics warning so AlgoBooth's lint can flag the backlog.
    """
    plans: list[Path] = []
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            meta = _parse_plan_frontmatter(p) or {}
            if meta:
                status = meta.get("status", "Ready")
                if status == "Complete":
                    continue
            else:
                _diag(
                    f"legacy plan (no frontmatter): {p} — backfill "
                    "kind/feature_id/status/created per _components/plan-frontmatter.md"
                )
            plans.append(p)
    # Legacy fallback
    legacy = spec_dir / "PLAN.md"
    if legacy.exists() and legacy not in plans:
        meta = _parse_plan_frontmatter(legacy) or {}
        if meta:
            if meta.get("status") != "Complete":
                plans.append(legacy)
        else:
            _diag(
                f"legacy plan (no frontmatter): {legacy} — backfill per "
                "_components/plan-frontmatter.md"
            )
            plans.append(legacy)
    # Sort by the authoritative execution-order key (_plan_sort_key):
    # (series_index, lowest_phase, name). The ``-part-K`` series index sorts
    # FIRST so a declared multi-part plan series ("Execute parts strictly in
    # order") always routes part-1 before part-2 — even when part-1 carries a
    # HIGHER phase number than part-2 (the d8-effect-chains corrective-Phase-6
    # inversion, ISSUE 1). Non-series plans (no ``-part-K`` suffix) carry
    # series_index sys.maxsize and fall back to the prior (lowest_phase, name)
    # ordering, so single-plan / legacy features behave exactly as before.
    plans.sort(key=_plan_sort_key)
    return plans


def _implementation_plans_exist(spec_dir: Path) -> bool:
    """Return True iff at least one IMPLEMENTATION plan file exists on disk,
    regardless of its frontmatter status (Ready / In-progress / Complete / none).

    "Implementation plan" excludes ``realign-*.md`` / ``retro-*.md`` (mirrors the
    filter in ``find_implementation_plans``) and the legacy ``PLAN.md``. Used by
    ``verify_ledger`` (harness-hardening-retro-fixes Phase 3) to distinguish
    *absent-by-design* (a plan-less / realign-only feature — no implementation
    plan, none required → ``plan_complete`` is True) from *incomplete* (an
    implementation plan exists but is not Complete → ``plan_complete`` stays
    False). Unlike ``find_implementation_plans``, this does NOT filter out
    Complete plans — it answers the pure existence question.
    """
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            return True
    legacy = spec_dir / "PLAN.md"
    if legacy.exists():
        return True
    return False


def _has_any_complete_plan(spec_dir: Path) -> bool:
    """Return True iff at least one non-retro/non-realign implementation plan
    has frontmatter ``status: Complete``.

    Used by the Step 7 cloud bypass to distinguish 'all implementation plans
    are Complete' from 'no plans authored yet' — only the former should fall
    through to Step 8 in cloud mode when PHASES.md still has unchecked rows
    (e.g. workstation-only Runtime Verification subsections).
    """
    plans_dir = spec_dir / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            name = p.name
            if name.startswith("retro-") or name.startswith("realign-"):
                continue
            meta = _parse_plan_frontmatter(p) or {}
            if meta and meta.get("status") == "Complete":
                return True
    legacy = spec_dir / "PLAN.md"
    if legacy.exists():
        meta = _parse_plan_frontmatter(legacy) or {}
        if meta and meta.get("status") == "Complete":
            return True
    return False


def find_retro_plans(spec_dir: Path) -> list[Path]:
    """Find retro plans, filtering out plans whose frontmatter marks them
    Complete. Plans without frontmatter are treated as legacy ``status: Ready``
    and surface a diagnostics warning.
    """
    plans_dir = spec_dir / "plans"
    if not plans_dir.exists():
        return []
    out: list[Path] = []
    for p in sorted(plans_dir.glob("retro-*.md")):
        meta = _parse_plan_frontmatter(p) or {}
        if meta:
            if meta.get("status") == "Complete":
                continue
        else:
            _diag(
                f"legacy retro plan (no frontmatter): {p} — backfill per "
                "_components/plan-frontmatter.md"
            )
        out.append(p)
    return out


def latest_retro_plan(spec_dir: Path) -> Path | None:
    """Return the most recent retro plan (by index then mtime), or None."""
    plans = find_retro_plans(spec_dir)
    if not plans:
        return None
    # Sort by leading number if present (retro-1-, retro-2-, etc.); fallback to mtime
    def keyfn(p: Path) -> tuple[int, float]:
        m = re.match(r"^retro-(\d+)-", p.name)
        idx = int(m.group(1)) if m else 0
        return (idx, p.stat().st_mtime)
    return max(plans, key=keyfn)


def retro_plan_has_significant_divergences(plan_path: Path) -> bool:
    """Heuristic: scan the retro plan for non-empty Significant divergence table."""
    if not plan_path.exists():
        return False
    text = plan_path.read_text(encoding="utf-8")
    # Look for a Significant table under Spec Divergences with at least one data row
    # Pattern: "### Significant" followed by table header then data row(s)
    m = re.search(
        r"### Significant.*?\n(.*?)(?=\n###|\n##|\Z)",
        text,
        flags=re.DOTALL,
    )
    if not m:
        return False
    section = m.group(1)
    # Count table rows that aren't header/separator/empty
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):  # separator
            continue
        # Skip header row (contains "Spec Requirement" or similar header text)
        if "Spec Requirement" in s or "---" in s or "Item " in s:
            continue
        # Data row with content other than '...'
        cells = [c.strip() for c in s.strip("|").split("|")]
        if any(c and c != "..." for c in cells):
            return True
    return False


# ---------------------------------------------------------------------------
# PHASES.md analysis
# ---------------------------------------------------------------------------

def count_deliverables(phases_text: str) -> tuple[int, int]:
    """Return (unchecked, checked) counts of '- [ ]' / '- [x]' lines.

    Lines that appear inside a triple-backtick code fence are skipped — they
    are illustrative examples, not real deliverables.
    """
    unchecked = 0
    checked = 0
    in_fence = False
    for line in phases_text.splitlines():
        # Toggle fence state when a line's stripped content starts with ```.
        # Handles both opening (```lang) and closing (```) fence markers.
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^\s*-\s*\[\s*\]", line):
            unchecked += 1
        elif re.match(r"^\s*-\s*\[[xX]\]", line):
            checked += 1
    return unchecked, checked


# Matches the title text of a "verification-only" subsection — rows under such
# a subsection are workstation-only runtime/MCP checks that cloud cannot tick
# and that the workstation /mcp-test step (not /write-plan) is responsible for.
#
# CANONICAL VERIFICATION-SUBSECTION HEADER SET (the source of truth this regex
# must stay in lockstep with). Every header below is authored by a /spec-phases
# or /blocked-resolution component, nests gate-owned (`/mcp-test`) unchecked
# rows, and must be recognized as a verification boundary — otherwise its only
# unchecked rows read as plannable implementation work and Step 7a loops on
# write-plan forever even though every implementation plan part is Complete. The
# whole family is gate-owned re-probe / certification work, NOT /write-plan or
# /execute-plan deliverables. Two consecutive single-phrase gaps in one run
# (`reachability smoke` Round 24 / d8d02ef, then `full-chain seam audit` this
# round) motivated enumerating the FULL convention set here rather than patching
# one phrase per incident:
#
#   1. "Runtime Verification"          — _components/phases-runtime-verification.md
#                                         (the canonical nesting heading/bold marker).
#   2. "MCP Integration Test" /
#      "MCP (test )?assertion(s)"      — same component (gate assertion subsection).
#   3. "Reachability smoke"            — same component: every phase introducing a
#                                         new user-facing API surface carries one
#                                         in-phase reachability-smoke row (a single
#                                         live MCP call proving the surface is
#                                         callable end-to-end), often emitted as its
#                                         own sibling bold header
#                                         ``**Reachability smoke (...):**``.
#   4. "Full-chain seam audit" /
#      "seam audit" /
#      "seam re-validation"            — _components/blocked-resolution.md step 1a/6
#                                         + phases-runtime-verification.md: the
#                                         retry_count>=2 escalation convention. A
#                                         corrective phase at escalation MUST carry a
#                                         full-chain seam-audit deliverable —
#                                         enumerate every boundary in the failing
#                                         path and live-probe each seam post-fix to
#                                         the final observable BEFORE full
#                                         re-validation. Those rows (plus the
#                                         certifying ``Workstation: /mcp-test ...
#                                         passes`` row) are all live-MCP re-probe
#                                         assertions owned by /mcp-test, so the
#                                         ``**Full-chain seam audit (HARD — retry_count
#                                         >= 2 escalation ...):**`` sibling header is
#                                         a verification boundary. (Live no-progress
#                                         loop: d8-session-format Phase 9, 2026-06-16
#                                         hardening round.)
#
# When a NEW verification/escalation subsection convention is added to either
# component, add it here AND add a regression fixture to test_lazy_core.py — do
# NOT wait for it to manifest as a production no-progress loop.
# ---------------------------------------------------------------------------
# Verification-only canonical marker (harness-hardening-retro-fixes Phase 2).
#
# SINGLE SOURCE OF TRUTH for the structural marker that flags a PHASES.md
# checkbox row (or its enclosing subsection) as runtime-verification-only —
# owned by the Step-9 /mcp-test gate, NOT outstanding implementation work.
#
# Open Question 2 (canonical marker form) is RESOLVED toward the per-row HTML
# comment ``<!-- verification-only -->`` rather than a single canonical
# subsection header, for two reasons:
#   1. Most robustly machine-detectable in remaining_unchecked_are_verification_only:
#      a row carries its OWN exemption marker, so no heading-scope bookkeeping is
#      needed and the detector survives NOVEL subsection phrasing by construction
#      (a never-before-seen header no longer needs a new regex alternative).
#   2. Survives the free-text-header whack-a-mole that motivated this feature
#      (two consecutive hardening rounds each grew _VERIFICATION_SECTION_RE).
#
# An HTML comment is invisible in rendered markdown, so it does not clutter the
# human-readable PHASES.md. It MAY appear on the checkbox row itself OR on the
# subsection header line (header-scope: it then exempts every row beneath that
# header until the next phase/section boundary).
#
# check-docs-consistency.ts fallback: the marker is a ROW ANNOTATION, not a
# sentinel, so it does NOT enter that script's SENTINEL_SCHEMAS. If a future
# edit to check-docs-consistency.ts cannot validate the HTML-comment form
# cleanly, fall back to a canonical subsection-header form and update BOTH this
# constant's value AND the producers that reference it by name (the lockstep
# test asserts producer prose == this constant).
# ---------------------------------------------------------------------------
_VERIFICATION_ONLY_MARKER = "<!-- verification-only -->"


# DEPRECATION SHIM (Phase 2). The legacy free-text header regex is retained ONLY
# so un-migrated PHASES.md (rows under a recognized header but WITHOUT the
# canonical marker) keep exempting cleanly — no regression. But every time the
# regex (and not the marker) is what exempts a row, the shim appends a
# _DIAGNOSTICS warning naming the un-migrated subsection so the migration gap is
# VISIBLE (a future cycle retires the regex once the shim stops firing across all
# live PHASES.md). New verification-subsection conventions should rely on the
# marker, NOT grow this regex.
_VERIFICATION_SECTION_RE = re.compile(
    r"runtime\s+verification|reachability\s+smoke"
    r"|mcp\s+(?:integration\s+test|test\s+assertion|assertion)"
    # Escalation (retry_count >= 2) seam-audit convention — blocked-resolution.md.
    # ``full[- ]chain\s+seam`` covers "full-chain seam audit"/"full chain seam
    # audit"; the bare ``seam\s+(?:audit|re-?validation)`` covers the shorter
    # "seam audit" / "seam re-validation" / "seam revalidation" header forms.
    r"|full[-\s]chain\s+seam|seam\s+(?:audit|re-?validation)",
    re.IGNORECASE,
)


# Bold subsection headers that introduce genuine IMPLEMENTATION work (`- [ ]`
# deliverables), as opposed to verification rows or prose. Entering one ENDS the
# prior verification subsection's legacy scope: a ``**Deliverables:**`` /
# ``**Implementation:**`` subsection placed AFTER a ``**Runtime Verification:**``
# / seam-audit subsection within the same phase must NOT let its implementation
# rows inherit the verification exemption (the escalation-corrective-phase shape
# `/add-phase` produces — seam audit first, deliverables second — which otherwise
# misroutes the feature straight to the MCP gate before the corrective code is
# written; burned on `adhoc-clap-live-poly-mod-producer-feed` Phase 6, 2026-06-24).
# DISTINCT from a prose bold like ``**Assessment:**`` / ``**Note:**`` (which must
# PRESERVE the enclosing verification scope — see
# test_verification_only_non_verification_bold_not_a_boundary): only a header
# naming an implementation section ends the scope. A markdown ``#`` heading already
# resets the scope structurally (the heading branch derives in_verification from
# _VERIFICATION_SECTION_RE) — this regex closes the same gap for the BOLD-marker
# subsection form the real AlgoBooth PHASES.md uses.
_DELIVERABLES_SECTION_RE = re.compile(
    r"\b(?:deliverable|implementation|work\s*unit|task)\w*\b",
    re.IGNORECASE,
)


# Deliberately-DROPPED-in-place deliverable rows (descope-in-place). A PHASES
# author (e.g. a NEEDS_INPUT.md resolution) may retire a planned deliverable by
# STRIKING IT THROUGH and tagging it with an explicit descope marker, rather
# than deleting the row (preserves the audit trail of WHY it was dropped):
#
#   - [ ] ~~<text>~~ **DROPPED** (decision N, NEEDS_INPUT.md resolution, <date>)
#
# Such a row is unambiguously not-to-be-done — exactly like a Superseded-phase
# row — and MUST count toward the "all remaining unchecked are exempt -> True"
# Step-7 bypass, else a fully-implemented item whose SOLE unchecked box is a
# descope note loops write-plan forever (live: live-settings-split-brain-...
# PHASES line 128, 2026-07-12). CONSERVATIVE BY CONSTRUCTION: BOTH a
# strikethrough span AND an explicit descope marker are required — a plain
# unchecked row, or a struck row WITHOUT a descope marker, still returns False
# (never over-exempt genuine implementation work).
#
# OVER-FIT NOTE: the descope-marker vocabulary below is a keyword set; the
# durable fix is a CANONICAL STRUCTURAL descope marker emitted by producers
# (parallel to _VERIFICATION_ONLY_MARKER, with this free-text form retained as a
# deprecation shim like _VERIFICATION_SECTION_RE). That generalization is spun
# off as its own item — until it lands, this is the free-text shim.
_DESCOPE_STRIKETHROUGH_RE = re.compile(r"~~.+?~~")
_DESCOPE_MARKER_RE = re.compile(
    r"\*\*\s*(?:DROPPED|DESCOPED|WON[’']?T[-\s]?FIX)\s*\*\*",
    re.IGNORECASE,
)


# Canonical structural descope marker (descoped-row-recognition-needs-canonical-marker).
#
# SINGLE SOURCE OF TRUTH for the per-row HTML comment that flags a PHASES.md
# checkbox row (or its enclosing subsection) as a deliberately-DROPPED-in-place
# deliverable — not-to-be-done, exactly like a Superseded row. Mirrors
# _VERIFICATION_ONLY_MARKER exactly: a per-row HTML comment, invisible in
# rendered markdown, PHRASING-INDEPENDENT. It is the PRIMARY descope signal —
# a row carrying it (or under a header carrying it) is exempt regardless of the
# free-text keyword, and needs NO accompanying strikethrough (unlike the legacy
# _DESCOPE_STRIKETHROUGH_RE + _DESCOPE_MARKER_RE shim path, which requires BOTH).
#
# The legacy free-text keyword pair below is now a DEPRECATION SHIM (parallel to
# _VERIFICATION_SECTION_RE): it still exempts un-migrated rows (no regression),
# but when the shim (and not this marker) is what exempts a row, a _DIAGNOSTICS
# warning names the un-migrated row so the migration gap is VISIBLE.
#
# check-docs-consistency.ts fallback: the marker is a ROW ANNOTATION, not a
# sentinel, so it does NOT enter that script's SENTINEL_SCHEMAS. If a future
# edit there cannot validate the HTML-comment form cleanly, fall back to a
# canonical subsection-header form and update BOTH this constant's value AND the
# producers that reference it by name (a lockstep test asserts producer == this).
_DESCOPED_MARKER = "<!-- descoped -->"


def _row_is_descoped_in_place(row_text: str) -> bool:
    """A deliberately-dropped deliverable row: struck-through AND descope-marked.

    LEGACY free-text path ONLY (the deprecation shim): BOTH a strikethrough span
    AND an explicit descope keyword marker are required — a plain unchecked row,
    or a bare strikethrough without a descope marker, is NOT exempt. Case-
    insensitive marker match; supports DROPPED / DESCOPED / WON'T-FIX.

    The canonical structural path (the caller checking ``_DESCOPED_MARKER``,
    row- or header-scope) requires NO strikethrough — this free-text function is
    consulted only as a fallback for un-migrated rows lacking the canonical marker.
    """
    return bool(_DESCOPE_STRIKETHROUGH_RE.search(row_text)) and bool(
        _DESCOPE_MARKER_RE.search(row_text)
    )


def remaining_unchecked_are_verification_only(phases_text: str) -> bool:
    """Return True iff every '- [ ]' line in PHASES.md is runtime-verification-only.

    Used by the Step 7 workstation bypass: when all implementation plans are
    Complete and the only remaining unchecked rows are workstation-only
    verification rows, /lazy should fall through to the retro→MCP gate rather
    than loop on write-plan.

    A row is verification-exempt when ANY of:
      - the row itself carries the canonical ``_VERIFICATION_ONLY_MARKER``
        (per-row HTML comment) — the PRIMARY, structural, header-text-independent
        path (Phase 2);
      - its enclosing subsection's HEADER line carries the marker (header-scope);
      - LEGACY (deprecation shim): its enclosing heading/bold-marker header text
        matches ``_VERIFICATION_SECTION_RE``. When the regex (and not a marker) is
        what exempts a row, a ``_DIAGNOSTICS`` warning is appended naming the
        un-migrated subsection — the rows still exempt (no regression) but the
        migration gap is surfaced (does NOT silently pass).

    Marker-based exemption is INDEPENDENT of the bold-header/heading free text, so
    a NOVEL verification-subsection phrasing no longer gaps the gate.

    Conservative: an unchecked row that is neither marker-exempt nor under a
    regex-matched header returns False (caller keeps write-plan / execute-plan).
    Returns False if no unchecked rows are present.

    Returns True when the ONLY remaining unchecked rows are all exempt — whether
    verification-only OR inside a Superseded phase (or a mix). This is the
    Step-7 bypass signal: no genuine implementation work remains, so fall through
    to the Step-9 MCP gate instead of looping on write-plan.

    Superseded phases: a ``### Phase N:`` (or ``## Phase N:``) heading enters a
    new phase and resets tracking. The first ``**Status:** Superseded`` bold-status
    line seen inside that phase marks the entire phase exempt; its unchecked rows
    count toward the True return (bypass-eligible) — they are descoped to a
    successor feature, never remaining implementation work.

    Descoped-in-place rows: the canonical structural ``_DESCOPED_MARKER``
    (``<!-- descoped -->``, row- or header-scope) is now the PRIMARY exemption
    signal — no strikethrough or keyword required, exactly parallel to
    ``_VERIFICATION_ONLY_MARKER``. LEGACY (deprecation shim): an unchecked row
    that is BOTH struck through (``~~...~~``) AND carries an explicit descope
    marker (``**DROPPED**``/``**DESCOPED**``/``**WON'T-FIX**``) is also a
    deliberately-dropped deliverable — not-to-be-done, exactly like a Superseded
    row — and counts toward the True return (see ``_row_is_descoped_in_place``),
    but emits a ``_DIAGNOSTICS`` migration warning since the canonical marker is
    absent. Conservative: a plain unchecked row, or a struck row without a
    descope marker AND without the canonical marker, still returns False.
    """
    in_verification = False        # legacy: enclosing header matched the regex
    section_has_marker = False     # marker present on the enclosing header line
    current_header_text = ""       # for the deprecation-shim diagnostic
    warned_headers: set[str] = set()  # de-dupe diagnostics per header text
    in_superseded_phase = False
    saw_unchecked = False
    # Superseded-phase unchecked rows are exempt (deliverables descoped to a
    # successor feature) and MUST count toward the "all remaining unchecked are
    # exempt → True" return exactly like verification-only rows. They are
    # `continue`d before ``saw_unchecked`` is set, so without a separate flag a
    # feature whose ONLY remaining unchecked rows all sit inside a Superseded
    # phase returns ``saw_unchecked=False`` — the Step-7 workstation bypass never
    # fires and the state machine loops on write-plan forever against an
    # already-implemented + MCP-validated feature (split-editor Phase 6,
    # 2026-07-01; the __mark_complete__ gate itself already exempts Superseded,
    # so the bypass was the sole hold-out).
    saw_superseded_unchecked = False
    # Deliberately-DROPPED-in-place rows (struck-through + descope marker) are
    # exempt like Superseded rows and MUST count toward the True return — see
    # _row_is_descoped_in_place. Tracked separately so an all-descoped remainder
    # still bypasses (mirrors saw_superseded_unchecked).
    saw_descoped_unchecked = False
    section_has_descope_marker = False   # descope marker present on the enclosing header line
    warned_descope_rows: set[str] = set()  # de-dupe descope-shim diagnostics per row text
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        # Toggle fence state; fence markers are not section headers or deliverables.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Lines inside a code fence are illustrative examples — skip entirely.
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            heading_text = heading.group(1)
            # A Phase-level heading (e.g. "### Phase 10: ...") starts a new phase
            # block — reset all subsection tracking so the new phase begins clean.
            if re.match(r"Phase\s+\d+", heading_text):
                in_superseded_phase = False
                in_verification = False
                section_has_marker = False
                section_has_descope_marker = False
                current_header_text = ""
            else:
                # Non-phase heading (e.g. "### Runtime Verification" or a NOVEL
                # header). Marker on the header line → header-scope exemption,
                # text-independent. Else fall back to the legacy regex.
                section_has_marker = _VERIFICATION_ONLY_MARKER in line
                section_has_descope_marker = _DESCOPED_MARKER in line
                in_verification = bool(_VERIFICATION_SECTION_RE.search(heading_text))
                current_header_text = heading_text
            continue
        # Bold-marker subsection header (e.g. ``**Runtime Verification** ...``).
        # A list item like ``- **x**`` starts with '-', so it is not caught here.
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                # Detect a per-phase "**Status:** Superseded" status line.
                # Mark the entire current phase exempt; do not alter scope flags
                # because a Superseded phase has no effective verification rows.
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                # Descope header-scope marker (orthogonal to the verification
                # if/elif below): a bold header carrying _DESCOPED_MARKER exempts
                # every plain row beneath it until the next phase / named-subsection
                # boundary. A new verification or deliverables subsection header
                # ends that scope (mirrors how section_has_marker is reset).
                if _DESCOPED_MARKER in line:
                    section_has_descope_marker = True
                elif _VERIFICATION_SECTION_RE.search(bold_text) or _DELIVERABLES_SECTION_RE.search(bold_text):
                    section_has_descope_marker = False
                # A bold subsection header enters verification scope via the
                # marker (text-independent) OR the legacy regex; an
                # implementation-section header (**Deliverables:** etc.) EXITS it;
                # any other non-matching bold (e.g. **Assessment:** / **Status:**)
                # is prose structure, NOT a section boundary — preserve current
                # scope.
                if _VERIFICATION_ONLY_MARKER in line:
                    section_has_marker = True
                    current_header_text = bold_text
                elif _VERIFICATION_SECTION_RE.search(bold_text):
                    in_verification = True
                    section_has_marker = False
                    current_header_text = bold_text
                elif _DELIVERABLES_SECTION_RE.search(bold_text):
                    # Implementation/deliverables subsection: rows beneath it are
                    # genuine implementation work. End the prior verification scope
                    # so they are NOT swept verification-only (the marker-based
                    # exemptions — per-row marker / section_has_marker — are
                    # unaffected; a genuinely-marked row beneath still exempts).
                    in_verification = False
                    section_has_marker = False
                    current_header_text = bold_text
                # else: do nothing (preserve current scope).
                continue
        if re.match(r"^-\s*\[\s*\]", stripped):
            # Unchecked boxes inside a Superseded phase are out of scope —
            # deliverables moved to a successor feature; do not treat as remaining
            # implementation work. Record that we saw one so an all-Superseded
            # remainder still returns True (bypass-eligible) at the end.
            if in_superseded_phase:
                saw_superseded_unchecked = True
                continue
            # A deliberately-DROPPED-in-place row (struck-through AND descope-
            # marked) is not-to-be-done, exactly like a Superseded-phase row.
            # Count it toward the all-remaining-exempt -> True bypass; do NOT
            # set saw_unchecked (it is not a verification row). Conservative:
            # _row_is_descoped_in_place requires BOTH signals, so a plain
            # unchecked row / a struck row without a marker falls through below.
            # PRIMARY descope path: a row carrying the canonical _DESCOPED_MARKER
            # (or under a header carrying it) is a deliberately-dropped deliverable,
            # exempt regardless of the free-text keyword and with NO strikethrough
            # required. No migration diagnostic — this is the non-deprecated path.
            if _DESCOPED_MARKER in line or section_has_descope_marker:
                saw_descoped_unchecked = True
                continue
            # LEGACY deprecation shim: struck-through AND a free-text descope keyword
            # (_DESCOPE_STRIKETHROUGH_RE + _DESCOPE_MARKER_RE) but NO canonical marker.
            # Still exempt (no regression for un-migrated PHASES.md), but surface the
            # migration gap so a future cycle can retire the shim.
            if _row_is_descoped_in_place(stripped):
                saw_descoped_unchecked = True
                if stripped not in warned_descope_rows:
                    warned_descope_rows.add(stripped)
                    _diag(
                        "descope marker absent (un-migrated producer): the "
                        f"unchecked row {stripped!r} is exempted by the legacy "
                        f"_DESCOPE_MARKER_RE deprecation shim, not the canonical "
                        f"{_DESCOPED_MARKER} marker. The producer should emit the "
                        f"marker per lazy_core:_DESCOPED_MARKER."
                    )
                continue
            saw_unchecked = True
            row_has_marker = _VERIFICATION_ONLY_MARKER in line
            # PRIMARY: a marker on the row or its enclosing subsection exempts,
            # independent of header free text.
            if row_has_marker or section_has_marker:
                continue
            # LEGACY deprecation shim: the header matched the regex but neither
            # the row nor the header carries the canonical marker. Still exempt
            # (no regression for un-migrated PHASES.md), but surface the gap.
            if in_verification:
                if current_header_text not in warned_headers:
                    warned_headers.add(current_header_text)
                    _diag(
                        "verification-only marker absent (un-migrated producer): "
                        f"unchecked rows under verification subsection "
                        f"{current_header_text!r} are exempted by the legacy "
                        f"_VERIFICATION_SECTION_RE deprecation shim, not the "
                        f"canonical {_VERIFICATION_ONLY_MARKER} marker. The "
                        f"producer should emit the marker per "
                        f"lazy_core:_VERIFICATION_ONLY_MARKER."
                    )
                continue
            # Neither marker nor regex-matched header → genuine implementation row.
            return False
    # True iff there were remaining unchecked rows AND every one was exempt —
    # verification-only (saw_unchecked, all reached a `continue`), inside a
    # Superseded phase (saw_superseded_unchecked), OR a deliberately-dropped-in-
    # place row (saw_descoped_unchecked). A genuine implementation row would
    # have returned False above. Genuinely-zero-unchecked returns False (all
    # flags stay False) — unchanged.
    return saw_unchecked or saw_superseded_unchecked or saw_descoped_unchecked


def classify_blocking_unchecked_rows(phases_text: str) -> dict:
    """Split completion-blocking unchecked PHASES rows for an ACTIONABLE refusal.

    ``--apply-pseudo __mark_complete__`` auto-ticks canonically
    ``<!-- verification-only -->``-marked rows, then REFUSES on any phase that
    still has an unchecked box — the DELIBERATE "the verification carve-out does
    not apply at completion time" strictness (see ``_phase_completion_plan`` /
    the parse note at its docstring). The bare "N unchecked box(es)" refusal
    could not distinguish two very different causes, which is exactly the friction
    observed on managed-llm-credits (5 of 7 blocking rows were merely un-migrated
    verification rows; 2 were genuine gaps). This helper classifies the STILL
    unchecked (post-autotick), non-Superseded rows into:

      - ``shim``    – exempt by the LEGACY ``_VERIFICATION_SECTION_RE`` subsection
                      shim (under a "Runtime Verification"-style header) but
                      LACKING the canonical marker. Such a row would clear the
                      gate IF migrated to the canonical marker — but migration →
                      auto-tick ASSERTS the row was actually validated, so a row
                      whose verification genuinely did not run on this host must
                      NOT be blindly migrated (the open per-row host-deferral
                      design question — see the turn-routing-enforcement
                      NEEDS_INPUT).
      - ``genuine`` – neither a canonical marker nor the legacy shim: a real
                      incomplete deliverable.

    DIAGNOSTIC ONLY — mirrors ``remaining_unchecked_are_verification_only``'s
    scope tracking; does NOT change the gate's decision (the refusal still fires).
    Returns ``{"shim": [row_excerpt, ...], "genuine": [row_excerpt, ...]}`` —
    each excerpt is prefixed ``L<N>: `` with the row's 1-based line number
    (completion-gate-refusal-opacity Fix Scope §2: both classes carry line
    numbers so the coherence-gate advisory is actionable without a second
    probe or a manual PHASES.md line count).
    """
    shim: list[str] = []
    genuine: list[str] = []
    in_verification = False
    section_has_marker = False
    in_superseded_phase = False
    in_fence = False
    for lineno, line in enumerate(phases_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            heading_text = heading.group(1)
            if re.match(r"Phase\s+\d+", heading_text):
                in_superseded_phase = False
                in_verification = False
                section_has_marker = False
            else:
                section_has_marker = _VERIFICATION_ONLY_MARKER in line
                in_verification = bool(_VERIFICATION_SECTION_RE.search(heading_text))
            continue
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                if _VERIFICATION_ONLY_MARKER in line:
                    section_has_marker = True
                elif _VERIFICATION_SECTION_RE.search(bold_text):
                    in_verification = True
                    section_has_marker = False
                elif _DELIVERABLES_SECTION_RE.search(bold_text):
                    in_verification = False
                    section_has_marker = False
                continue
        if re.match(r"^-\s*\[\s*\]", stripped):
            if in_superseded_phase:
                continue
            # Canonical-marked rows are auto-ticked before this classifier runs,
            # so they are not blocking — skip them defensively if any remain.
            if _VERIFICATION_ONLY_MARKER in line or section_has_marker:
                continue
            excerpt = f"L{lineno}: " + stripped[:80] + ("…" if len(stripped) > 80 else "")
            if in_verification:
                shim.append(excerpt)
            else:
                genuine.append(excerpt)
    return {"shim": shim, "genuine": genuine}


# A phase heading in PHASES.md: ``## Phase ...`` or ``### Phase ...`` (two or
# three leading hashes, then the literal word "Phase"). Critically, "Phase" must
# be followed by an actual phase IDENTIFIER — NOT an English word. This mirrors
# the intent of the AlgoBooth repo checker's PHASE_HEADER_RE
# (``/^(#{2,4})\s+Phase\s+([A-Za-z0-9.+]+)\s*[:—-]\s*(.*)$/`` in
# check-docs-consistency.ts), whose author comment is explicit: the identifier
# must be delimited "to prevent matching headers like '### Phase Dependency
# Graph' where 'Phase' is just an English word, not a phase marker."
#
# The bare ``^#{2,3}\s+Phase\b`` form this replaced was a false-positive bug: it
# counted an h2 ``## Phase Summary`` summary section as an 8th phase for
# d8-session-format (7 real ``### Phase N`` headers + the summary). That made
# retro_staleness() return (8,7) on EVERY probe — a permanent "stale retro" loop
# that re-ran /retro forever and never advanced (hardening-log 2026-06 round).
#
# Discriminator (digit-OR-delimiter), strictly wider than the checker's
# delimiter-required form ONLY for bare numeric ids (``### Phase 1`` with no
# ``:``), which real PHASES.md and the existing parse_phases fixtures use:
#   - identifier CONTAINS a digit  → real phase   (``Phase 1``, ``Phase 4A``, ``Phase 10``)
#   - OR identifier is followed by a phase delimiter ``[:—-]`` → real phase
#     (``Phase G+:`` — a non-numeric id is only a phase when delimited)
#   - else (``Phase Summary``, ``Phase Dependency Graph``, ``Phase Implementation
#     Notes``) → NOT a phase.
# This is the SINGLE counter behind both retro_staleness() and lazy-state.py's
# ``--count-phases`` (the /retro phase_count_at_retro writer), so the staleness
# anchor and the recorded count can never disagree.
_PHASE_HEADING_RE = re.compile(
    r"^#{2,3}\s+Phase\s+(?:[A-Za-z.+]*\d[A-Za-z0-9.+]*|[A-Za-z0-9.+]+\s*[:—-])"
)

# A per-phase / top-level bold status line: ``**Status:** <value>``.
_BOLD_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$")

# A per-phase ``**Phase kind:** corrective | design`` marker (Phase 8 —
# lazy-validation-readiness). Mirrors the ``**Status:**`` per-phase convention
# and survives the docs-consistency parse. The captured value is normalized to
# lowercase and validated against {corrective, design}; anything else (including
# an absent line) falls back to the safe ``design`` default so legacy PHASES.md
# re-trigger retro exactly as before. Only the first occurrence inside a phase
# section wins (a later mention inside Implementation Notes is ignored).
_PHASE_KIND_RE = re.compile(r"^\*\*Phase kind:\*\*\s*(.+?)\s*$")

# The canonical phase-kind tier set. ``design`` is the conservative default:
# a design (or unknown / untagged) phase re-triggers /retro; only an explicit
# ``corrective`` tag suppresses the retro re-stale.
_VALID_PHASE_KINDS = frozenset({"corrective", "design"})
_DEFAULT_PHASE_KIND = "design"


def parse_phases(phases_text: str) -> list[dict]:
    """Parse PHASES.md into one record per phase section (Phase 9 WU-1).

    A phase starts at a heading matching ``^##{1,2} Phase\\b`` (i.e. ``## Phase
    ...`` or ``### Phase ...``) and runs to the next phase heading or EOF.

    For each phase the record captures:
      - ``heading``   – the full heading line text (stripped of a trailing
                        newline; leading/trailing whitespace stripped).
      - ``status``    – the value of the FIRST ``**Status:**`` line inside the
                        section, stripped; ``None`` when the section has no
                        status line. A top-level (pre-first-phase) Status line is
                        NEVER captured — content before the first phase heading
                        is not a phase.
      - ``unchecked`` – count of ``- [ ]`` rows in the section, FENCE-AWARE.
      - ``checked``   – count of ``- [x]`` / ``- [X]`` rows in the section,
                        FENCE-AWARE.
      - ``phase_kind`` – ``"corrective"`` or ``"design"``, read from the FIRST
                        ``**Phase kind:** ...`` line inside the section
                        (Phase 8 — lazy-validation-readiness). Defaults to
                        ``"design"`` when the line is absent or carries an
                        unrecognized value (back-compat: a legacy / untagged
                        phase re-triggers /retro exactly as before).

    Fence-awareness reuses the established ``in_fence`` toggle pattern (see
    ``count_deliverables``): a line whose stripped form starts with ``` (a fence
    open/close, including a ```lang opener) toggles fence state, and checkbox
    rows inside a fence are illustrative examples that do NOT count.

    Returns an empty list when ``phases_text`` contains no phase heading.
    """
    phases: list[dict] = []
    current: dict | None = None
    in_fence = False
    for line in phases_text.splitlines():
        stripped = line.strip()
        # Fence markers are never headings, status lines, or deliverables.
        # Toggle the fence and skip — but note that a fence opened/closed inside
        # a phase still belongs to that phase, so we keep ``current`` as-is.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Inside a fenced block: nothing counts (examples only). We still do
            # NOT start/stop phases here — fence content is opaque body.
            continue
        # A phase heading starts a new section (and closes the previous one).
        if _PHASE_HEADING_RE.match(line):
            current = {
                "heading": stripped,
                "status": None,
                "unchecked": 0,
                "checked": 0,
                # Tracks whether a **Phase kind:** line has been consumed yet
                # (first-wins, like status). The public ``phase_kind`` value is
                # set to the default here and overwritten by the first valid
                # marker; an unknown value leaves the default in place.
                "phase_kind": _DEFAULT_PHASE_KIND,
                "_phase_kind_seen": False,
            }
            phases.append(current)
            continue
        # Everything below only matters once we are inside a phase section.
        # Content before the first phase heading (top-level Status, preamble,
        # stray checkboxes) is intentionally ignored.
        if current is None:
            continue
        # First **Status:** line inside the section wins; later ones (e.g. inside
        # an Implementation Notes block describing prior state) are ignored.
        if current["status"] is None:
            sm = _BOLD_STATUS_RE.match(stripped)
            if sm:
                current["status"] = sm.group(1).strip()
                continue
        # First **Phase kind:** line inside the section wins; later mentions
        # (e.g. inside an Implementation Notes block) are ignored. An
        # unrecognized value leaves the safe ``design`` default in place.
        if not current["_phase_kind_seen"]:
            km = _PHASE_KIND_RE.match(stripped)
            if km:
                current["_phase_kind_seen"] = True
                kind = km.group(1).strip().lower()
                if kind in _VALID_PHASE_KINDS:
                    current["phase_kind"] = kind
                continue
        # Checkbox accounting (fence-aware — fenced rows already skipped above).
        if re.match(r"^-\s*\[\s*\]", stripped):
            current["unchecked"] += 1
        elif re.match(r"^-\s*\[[xX]\]", stripped):
            current["checked"] += 1
    # Drop the private bookkeeping key so the returned records expose only the
    # documented public fields (heading/status/unchecked/checked/phase_kind).
    for ph in phases:
        ph.pop("_phase_kind_seen", None)
    return phases


# Line-start "Implementation Notes" heading (## or ###). The body-evidence
# signal for phases_show_implementation — an Implementation Notes block is
# appended by /execute-plan after a phase lands, so its presence is positive
# proof the feature is past the pre-planning research stage. Matched only at
# line start (re.M); a fenced occurrence is a non-issue for this signal.
_IMPL_NOTES_HEADING_RE = re.compile(r"^#{2,3}\s+Implementation Notes\b", re.MULTILINE)

# Sibling IMPLEMENTATION_NOTES.md evidence signal. After the D3 writer flip,
# /execute-plan appends per-batch notes blocks (headed ``#### Implementation
# Notes (Phase N)``) to a sibling IMPLEMENTATION_NOTES.md instead of embedding
# them in PHASES.md. The block heading can be authored at any level (## / ### /
# ####), so this matches 2–4 leading hashes — broader than the embedded-PHASES
# regex above. A bare scaffold sibling (title + preamble only, no notes block)
# does NOT match, so it cannot falsely suppress research.
_SIBLING_IMPL_NOTES_HEADING_RE = re.compile(
    r"^#{2,4}\s+Implementation Notes\b", re.MULTILINE
)


def _sibling_impl_notes_present(phases_path: Path) -> bool:
    """Return True iff a sibling ``IMPLEMENTATION_NOTES.md`` next to ``phases_path``
    exists and carries at least one Implementation Notes block.

    Sibling = same directory as the PHASES.md being checked (the D3 writer
    resolves the sibling that way). Presence of a notes block (``#### / ### / ##
    Implementation Notes``) is the relocated equivalent of the legacy embedded
    heading; a bare title/preamble-only scaffold returns False. Read errors and
    a missing file return False (degrade to the embedded fallback).
    """
    sibling = phases_path.parent / "IMPLEMENTATION_NOTES.md"
    try:
        if not sibling.is_file():
            return False
        text = sibling.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(_SIBLING_IMPL_NOTES_HEADING_RE.search(text))


def phases_show_implementation(
    phases_text: str, phases_path: Path | None = None
) -> bool:
    """Return True iff a PHASES.md shows implementation EVIDENCE.

    The reusable primitive the Step-5 research-gate guard consults
    (research-gate-ignores-existing-phases): a feature whose PHASES.md already
    shows implementation is past the pre-planning research stage, so the
    research gate must NOT send it back for research.

    Composes the existing parsers — adds NO new parsing surface:

    - **Zero-phase stub guard (FIRST):** when ``parse_phases(phases_text)``
      yields zero phases (no ``## Phase`` heading — a stub / empty PHASES.md),
      return ``False`` unconditionally. A stub is treated exactly like "no
      PHASES.md" so a placeholder file does NOT suppress legitimate research
      (SPEC Open-Q1 / D2).
    - Otherwise return ``True`` when ANY of these signals holds:
        1. a parsed phase's ``status`` is ``Complete`` or ``In-progress``
           (case-insensitive compare on the stripped value), OR
        2. ``count_deliverables(phases_text)[1] >= 1`` — at least one checked
           ``- [x]`` deliverable (fence-awareness inherited from
           ``count_deliverables``: a checkbox inside a ``` fence does not
           count), OR
        3. **(sibling-then-embedded, D3)** when ``phases_path`` is supplied, a
           sibling ``IMPLEMENTATION_NOTES.md`` next to it carries an
           Implementation Notes block (the relocated-notes shape) — checked
           FIRST; OR
        4. an embedded ``## Implementation Notes`` (or ``###``) heading is
           present at a line start in PHASES.md (legacy in-flight features).
      Else ``False``.

    The sibling check (3) and the embedded fallback (4) make the predicate
    tolerant of the D3 split: a relocated-notes feature whose PHASES.md is now a
    thin checklist still reads as "implemented" and is NOT re-routed to research.
    When ``phases_path`` is ``None`` (legacy callers passing only text), only the
    embedded heading is consulted — behavior is unchanged for those callers.

    Side-effect-free apart from the optional sibling read. It emits NO ``_diag``
    — the diagnostic is the caller's responsibility (the Step-5 guard in
    ``lazy-state.py`` emits the D3 ``_diag`` line), keeping this predicate
    reusable elsewhere.
    """
    phases = parse_phases(phases_text)
    if not phases:
        # Stub / empty PHASES.md — treat as "no PHASES.md": do not suppress
        # research.
        return False
    for ph in phases:
        if (ph.get("status") or "").strip().lower() in {"complete", "in-progress"}:
            return True
    if count_deliverables(phases_text)[1] >= 1:
        return True
    # Sibling-then-embedded: prefer the relocated IMPLEMENTATION_NOTES.md, then
    # fall back to the embedded heading for legacy in-flight features.
    if phases_path is not None and _sibling_impl_notes_present(phases_path):
        return True
    if _IMPL_NOTES_HEADING_RE.search(phases_text):
        return True
    return False


def retro_staleness(spec_path: Path) -> tuple[int, int] | None:
    """Detect a stale retro: a DESIGN phase landed AFTER the retro concluded.

    Shared predicate for Phase 11 WU-5c (lazy-state Step-8 routing) and WU-5d
    (the ``apply_pseudo __mark_complete__`` backstop) — both keys compare the
    CURRENT number of phase sections in PHASES.md against the count the retro
    recorded at conclusion time (``phase_count_at_retro`` in RETRO_DONE.md
    frontmatter, written by /retro per the Phase 11 WU-5a prose half).

    Returns ``(current_count, recorded_count)`` when the retro is STALE, else
    None.

    **Phase-8 phase-kind gate (lazy-validation-readiness).** A retro is stale
    only when ``>= 1`` of the phases added SINCE the retro is a ``design``
    (non-corrective) phase. The phases added since the retro are the ones at
    index ``>= recorded_count`` (the recorded count is the number of phase
    sections at retro time, so the trailing ``current - recorded`` sections are
    the post-retro additions). A run of PURELY ``corrective`` additions does NOT
    re-trigger retro — corrective phases make the impl satisfy the EXISTING
    spec and change no design surface, so the retro that graded the design has
    nothing to re-audit. A ``design`` (or untagged / unknown-kind, which
    defaults to ``design``) addition DOES re-stale retro. This narrows the
    pre-Phase-8 "any added phase re-stales" behavior; legacy untagged corrective
    tails still re-trigger (the safe default), preserving back-compat.

    Grandfathering / no-signal cases (all → None, preserving prior behavior):
      - RETRO_DONE.md absent, or present without frontmatter.
      - ``phase_count_at_retro`` missing or malformed (not an int / digit
        string; YAML bools rejected — not counts).
      - PHASES.md absent (nothing to compare against).
      - Equal or FEWER phases now (consolidation is not staleness).
      - More phases now, but every post-retro addition is ``corrective``
        (Phase-8 gate — design surface unchanged, no re-audit warranted).
    """
    retro_meta = parse_sentinel(spec_path / "RETRO_DONE.md")
    if not retro_meta:
        # Absent (None) or frontmatter-less ({}) — no recorded count, no signal.
        return None
    raw = retro_meta.get("phase_count_at_retro")
    # bool is an int subclass — reject before the int branch (see
    # validation_escalation for the same YAML-boolean pitfall).
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        recorded = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        recorded = int(raw.strip())
    else:
        # Missing or malformed — grandfathered (current behavior).
        return None
    phases_path = spec_path / "PHASES.md"
    if not phases_path.exists():
        return None
    try:
        phases_text = phases_path.read_text(encoding="utf-8")
    except OSError:
        # Unreadable PHASES.md: treat as no signal rather than crashing the
        # routing/gate — the doc-consistency lints own malformed-file policing.
        return None
    parsed = parse_phases(phases_text)
    current = len(parsed)
    if current <= recorded:
        # Equal or fewer phases now — consolidation is not staleness.
        return None
    # Phase-8 phase-kind gate: only a DESIGN phase added since the retro
    # re-stales. The post-retro additions are the trailing sections at index
    # >= recorded. ``recorded`` may exceed ``current`` only when current <=
    # recorded (already returned above), so this slice is always valid here.
    # A negative/over-large recorded is defended by clamping to [0, current].
    added = parsed[max(0, recorded):]
    if any(ph.get("phase_kind", _DEFAULT_PHASE_KIND) == "design" for ph in added):
        return (current, recorded)
    # Every post-retro addition is corrective — design surface unchanged,
    # nothing for the retro to re-audit. Not stale.
    return None


# Canonical terminal phase statuses (case-insensitive). A phase whose status is
# one of these is "done" and never refuses / auto-flips at completion time.
# Mirrors check-docs-consistency.ts's Complete/Superseded acceptance in the
# spec-complete-phases-not and complete-but-unchecked coherence rules.
_TERMINAL_PHASE_STATUSES = frozenset({"complete", "superseded"})


def _phase_completion_plan(phases: list[dict]) -> tuple[list[dict], list[str]]:
    """Compute the auto-flip set and residual-incoherence refusals for completion.

    Given the parsed ``phases`` (from ``parse_phases``), this mirrors the three
    coherence rules check-docs-consistency.ts enforces under a Complete SPEC —
    but evaluated PRE-flip at ``__mark_complete__`` / ``__mark_fixed__`` time:

      (auto-flip) a phase with >=1 checkbox, zero unchecked, and a PRESENT
        Status not in {Complete, Superseded} → flip to ``Complete`` (mirrors the
        checker's ``all-checked-but-not-complete`` rule; deterministic + safe).

      (refuse) AFTER hypothetically applying the auto-flips, a phase is residually
        incoherent — and the whole completion refuses — when, for a phase that is
        NOT Superseded:
          * it has >=1 unchecked checkbox (verification rows INCLUDED — by
            completion time the verification exemption's job is done), OR
          * its (post-flip) Status is PRESENT but not Complete/Superseded
            (this catches zero-checkbox non-Complete phases too: no mechanical
            signal to flip on → refuse).

        Null-status handling (deliberate, completeness-first / D7): the
        status-straggler check (the second bullet) exempts a phase with NO
        Status line — canonical-null is a non-straggler exactly as the repo
        checker's ``spec-complete-phases-not`` rule (which filters
        ``canonical !== null``) treats it. The unchecked-box check (the first
        bullet) is NOT exempted for null-status phases: the deliverable's box
        rule is "any phase with >=1 unchecked checkbox", so a status-less phase
        with visibly-unfinished work still refuses (the stricter, safer option —
        a feature must not complete with unfinished deliverables hiding under a
        status-less phase).

    Returns ``(flip, refusals)`` where ``flip`` is the list of phase records to
    auto-flip and ``refusals`` is a list of human-readable per-phase reasons
    (empty ⇒ coherent, proceed).
    """
    flip: list[dict] = []
    refusals: list[str] = []
    for ph in phases:
        status = ph["status"]
        status_norm = status.strip().lower() if status else None
        is_superseded = status_norm == "superseded"
        is_terminal = status_norm in _TERMINAL_PHASE_STATUSES
        has_boxes = (ph["checked"] + ph["unchecked"]) > 0
        all_checked = has_boxes and ph["unchecked"] == 0

        # --- (a) auto-flip candidates ---
        # A present, non-terminal status whose every box is checked → flip.
        will_flip = (
            status is not None
            and not is_terminal
            and all_checked
        )
        if will_flip:
            flip.append(ph)

        # --- (b/c) residual incoherence AFTER the hypothetical flip ---
        # Superseded is terminal: its unchecked boxes and status are acceptable.
        if is_superseded:
            continue

        # Unchecked boxes in a non-Superseded phase always block completion —
        # the verification carve-out does not apply at completion time.
        if ph["unchecked"] > 0:
            refusals.append(
                f'{ph["heading"]}: {ph["unchecked"]} unchecked box(es)'
            )
            continue

        # No unchecked boxes. The phase is coherent iff, post-flip, its status is
        # Complete/Superseded. A phase we just flipped lands at Complete → OK.
        # A phase with a present non-terminal status that did NOT qualify for the
        # flip (e.g. zero-checkbox In-progress) has no mechanical flip signal →
        # refuse. A phase with no status line is ignored.
        if status is not None and not is_terminal and not will_flip:
            refusals.append(
                f'{ph["heading"]}: status "{status}" not Complete/Superseded'
            )
    return flip, refusals


# ---------------------------------------------------------------------------
# evaluate_completion_evidence — authoritative-evidence decision table
#   (completion-coherence-gate-reconciliation Phase 1).
#
# A PURE, side-effect-free read of a feature's on-disk /mcp-test receipts that
# returns one of three LOCKED verdict literals — ``exempt-and-tick`` /
# ``warn-exempt`` / ``refuse`` — implementing the SPEC's Technical Design
# (LOCKED) authoritative-evidence decision table. The completion gate (Phase 3)
# branches on these literals; once landed they are a contract.
#
# It NEVER mutates PHASES.md (that is autotick_verification_rows, Phase 2) and
# is NOT wired into the completion gate here (Phase 3). The only I/O is reading
# the sentinel files + (for the HEAD-drift row) one ``git diff --name-only``
# via the existing subprocess pattern. It reuses parse_sentinel + _current_head
# and the SAME pass/total/validated_commit parse shape the
# __write_validated_from_results__ freshness backstop uses — no parallel reader.
# ---------------------------------------------------------------------------

def _coerce_evidence_count(raw):
    """Coerce a YAML count field to int, or None. Mirrors the
    __write_validated_from_results__ ``_coerce_count`` tolerance: a bool is NOT
    a count (YAML ``True`` is int 1 in Python), an int passes through, and a
    digit-string (quoted YAML) is coerced.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


# Sentinel filenames that, in the ABSENCE of passing results, mean "skip" or
# "defer" — both fail CLOSED (refuse, do NOT tick) per the decision table.
_FAIL_CLOSED_EVIDENCE_SENTINELS = (
    "SKIP_MCP_TEST.md",
    "DEFERRED_NON_CLOUD.md",
    "DEFERRED_REQUIRES_DEVICE.md",
    # host-capability-declaration-for-gated-features Phase 5: the host-axis
    # generalization of DEFERRED_REQUIRES_DEVICE.md. A capability-deferred
    # feature is defer-NOT-evidence — the completion gate must treat it as a
    # skip/defer (fail CLOSED: refuse, do NOT tick), exactly like the device
    # sentinel, so a host-deferred feature never reaches Complete on a host that
    # lacks the capability.
    "DEFERRED_REQUIRES_HOST.md",
)

# Kill-switch env vars (completion-coherence-gate-reconciliation Phase 3 /
# research §8 reversibility hardening). When EITHER is set to a truthy value,
# the evidence-gated auto-tick relaxation is disabled: the completion gate falls
# back to the legacy strict path (verification rows INCLUDED in refusals) and
# the PHASES.md auto-tick rewrite is skipped entirely — frictionless rollback
# without a code revert.
_EVIDENCE_GATE_KILL_SWITCHES = ("LAZY_STRICT_EVIDENCE_GATE", "LAZY_DISABLE_AUTOTICK")
_FALSY_ENV_VALUES = frozenset({"", "0", "false", "no", "off"})


def _evidence_gate_killed() -> bool:
    """True iff a kill-switch env var is set to a truthy value.

    Read once per completion call. A var set to an explicitly-falsy value
    (``""`` / ``0`` / ``false`` / ``no`` / ``off``, case-insensitive) does NOT
    arm the switch, so an inherited empty export cannot accidentally disable the
    feature.
    """
    for var in _EVIDENCE_GATE_KILL_SWITCHES:
        val = os.environ.get(var)
        if val is not None and val.strip().lower() not in _FALSY_ENV_VALUES:
            return True
    return False


def evaluate_completion_evidence(feature_dir: Path, repo_root: Path) -> dict:
    """Evaluate a feature's on-disk /mcp-test evidence → completion verdict.

    Returns ``{verdict, reason, pass_count, validated_commit}`` where:
      - ``verdict`` ∈ {``"exempt-and-tick"``, ``"warn-exempt"``, ``"refuse"``}
        (the LOCKED contract Phase 3 branches on).
      - ``reason``  — a human-readable explanation (for diagnostics / receipts).
      - ``pass_count`` — the cardinality numerator Phase 2's auto-tick asserts
        against (``int`` on an exempt/warn verdict; ``None`` on most refusals).
      - ``validated_commit`` — the sha Phase 2 stamps into each auto-tick audit
        comment (``str`` on exempt/warn; ``None`` when unavailable).

    Decision table (SPEC Technical Design, LOCKED). The gate requires the UNION
    of VALIDATED.md (kind: validated, the VSA attestation envelope) AND
    MCP_TEST_RESULTS.md (kind: mcp-test-results, result: all-passing,
    pass==total, pass>0, the raw provenance) — neither file alone suffices:

      * both present + passing + validated_commit == HEAD → exempt-and-tick
      * VALIDATED.md present, results missing/malformed       → refuse (forged)
      * results present, VALIDATED.md missing                 → refuse (no VSA)
      * SKIP_MCP_TEST.md / DEFERRED_* (no passing results)    → refuse (closed)
      * pass==total==0                                        → refuse (zero-test)
      * validated_commit != HEAD, docs-only (*.md) drift      → warn-exempt
      * validated_commit != HEAD, any source/script/config    → refuse (TOCTOU)
      * neither file                                          → refuse (no evidence)
    """
    def _refuse(reason: str, *, pass_count=None, validated_commit=None) -> dict:
        return {
            "verdict": "refuse",
            "reason": reason,
            "pass_count": pass_count,
            "validated_commit": validated_commit,
        }

    validated_meta = parse_sentinel(feature_dir / "VALIDATED.md")
    has_validated = (
        validated_meta is not None
        and validated_meta.get("kind") == "validated"
    )

    results_meta = parse_sentinel(feature_dir / "MCP_TEST_RESULTS.md")
    has_results_kind = (
        results_meta is not None
        and results_meta.get("kind") == "mcp-test-results"
    )

    # --- Fail-closed sentinels (skip / defer) when no passing results back them.
    # These are checked when the passing-results union is NOT satisfied; a
    # passing run alongside a stray skip file still evaluates on the evidence.
    def _fail_closed_present() -> str | None:
        for fname in _FAIL_CLOSED_EVIDENCE_SENTINELS:
            if (feature_dir / fname).exists():
                return fname
        return None

    # --- Neither evidence file → no evidence of verification execution.
    if not has_validated and not has_results_kind:
        closed = _fail_closed_present()
        if closed:
            return _refuse(
                f"{closed} present without passing /mcp-test evidence — "
                "skip/defer fails closed (no auto-tick)"
            )
        return _refuse(
            "neither VALIDATED.md nor MCP_TEST_RESULTS.md present — "
            "no evidence of verification execution"
        )

    # --- results present, VALIDATED.md missing → policy/VSA layer never ran.
    if not has_validated:
        return _refuse(
            "MCP_TEST_RESULTS.md present but VALIDATED.md (kind: validated) "
            "missing — the attestation/VSA layer never ran"
        )

    # --- VALIDATED.md present, results missing/malformed → forged-attestation.
    if not has_results_kind:
        closed = _fail_closed_present()
        if closed:
            return _refuse(
                f"{closed} present without passing MCP_TEST_RESULTS.md — "
                "skip/defer fails closed (no auto-tick)"
            )
        return _refuse(
            "VALIDATED.md present but MCP_TEST_RESULTS.md missing or malformed "
            "(no 'kind: mcp-test-results') — forged-attestation risk"
        )

    # --- Both present. Require a genuinely-passing run — OR a scoped-validated
    # observation-gap disposition (Gap 1 coupling,
    # harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1). This
    # MUST mirror the __write_validated_from_results__ apply gate's promotion rule
    # exactly: a `result: partial` is accepted ONLY when its
    # `observation_gap_exemptions` block is populated and EVERY entry carries a
    # non-empty `spec_class` provenance (the citation that distinguishes a verified
    # untestable-class assessment from a convenience skip) AND the MCP-driveable
    # scope is fully passing (the pass==total cross-check below). Without this
    # parallel acceptance the scoped VALIDATED.md minted by the apply gate would
    # still be re-refused here, perpetuating the deadlock one layer deeper at the
    # completion-integrity gate. A genuine MCP-scope failure (pass < total) or a
    # provenance-less exemption falls through to the unchanged refusal.
    _result_literal = results_meta.get("result")
    # Shared predicate (observation_gap_promotable) — the SINGLE home for the
    # scoped observation-gap partial rule. This gate MUST mirror the apply gate
    # and the Step-9 routing exactly; routing all three through one helper is
    # what keeps them from diverging (the divergence that reintroduced the
    # deadlock one layer up at the Step-9 MCP routing — community-sharing).
    _observation_gap_ok = observation_gap_promotable(results_meta)
    if _result_literal != "all-passing" and not _observation_gap_ok:
        return _refuse(
            f"MCP_TEST_RESULTS.md result is "
            f"{results_meta.get('result')!r} — expected 'all-passing' "
            "(or a scoped observation-gap partial whose every exemption carries "
            "a spec_class provenance and whose MCP scope fully passes)"
        )
    pass_count = _coerce_evidence_count(results_meta.get("pass_count"))
    total_count = _coerce_evidence_count(results_meta.get("total_count"))
    if pass_count is None or total_count is None:
        return _refuse(
            "MCP_TEST_RESULTS.md pass_count/total_count missing or malformed"
        )
    if pass_count != total_count:
        return _refuse(
            f"MCP_TEST_RESULTS.md pass_count ({pass_count}) != total_count "
            f"({total_count}) — a partial pass cannot exempt"
        )
    # pass>0 mandatory: pass==total==0 is the CI false-positive anti-pattern.
    if pass_count == 0:
        return _refuse(
            "MCP_TEST_RESULTS.md reports pass_count == total_count == 0 — a "
            "zero-test suite cannot certify (pass>0 required)"
        )

    validated_commit = results_meta.get("validated_commit")
    if validated_commit is not None:
        validated_commit = str(validated_commit)

    # --- Freshness / HEAD-drift carve-out.
    head = _current_head(repo_root)
    if validated_commit is None or head is None:
        # No recorded commit, or HEAD unresolvable (non-git tree): cannot prove
        # drift either way. Treat as fresh-enough (warn) — the upstream
        # __write_validated_from_results__ gate already required a fresh commit
        # to MINT VALIDATED.md, so a missing field here is the legacy path.
        return {
            "verdict": "exempt-and-tick",
            "reason": "passing evidence; validated_commit/HEAD unresolved "
                      "(legacy/non-git) — freshness UNVERIFIED",
            "pass_count": pass_count,
            "validated_commit": validated_commit,
        }
    if validated_commit == head:
        return {
            "verdict": "exempt-and-tick",
            "reason": "VALIDATED.md + passing MCP_TEST_RESULTS.md, "
                      "validated_commit == HEAD",
            "pass_count": pass_count,
            "validated_commit": validated_commit,
        }

    # validated_commit != HEAD → classify the drift via the SHARED
    # commit_drift_verdict helper (the SINGLE home for the docs-only carve-out;
    # the Step-9 state-script gates + the __write_validated_from_results__ apply
    # gate route through the same helper). Docs-only (*.md) → warn + exempt-and-
    # tick; any non-.md (source/script/config) path → refuse-and-revalidate
    # (TOCTOU: the validated code is not the code being promoted); an
    # unresolvable diff → refuse conservatively.
    drift = commit_drift_verdict(repo_root, validated_commit, head)
    if drift["verdict"] == "unresolvable":
        # Diff unresolvable (e.g. validated_commit not in this repo). Conservative
        # — cannot prove the drift is docs-only, so refuse-and-revalidate.
        return _refuse(
            f"validated_commit {validated_commit} != HEAD {head} and the diff "
            "could not be resolved — re-run /mcp-test against current HEAD",
            pass_count=pass_count,
            validated_commit=validated_commit,
        )
    if drift["verdict"] == "non-docs-drift":
        return _refuse(
            f"validated_commit {validated_commit} != HEAD {head} with "
            f"source/script/config drift ({', '.join(drift['non_docs'][:5])}) — "
            "refuse-and-revalidate (TOCTOU)",
            pass_count=pass_count,
            validated_commit=validated_commit,
        )
    # drift["verdict"] == "docs-only"
    return {
        "verdict": "warn-exempt",
        "reason": f"validated_commit {validated_commit} != HEAD {head} but the "
                  "drift is docs-only (*.md) — safe to exempt-and-tick",
        "pass_count": pass_count,
        "validated_commit": validated_commit,
    }


def _git_diff_name_only(
    repo_root: Path, base: str, head: str
) -> list[str] | None:
    """Return the list of paths changed between ``base`` and ``head``, or None.

    Best-effort, mirroring _current_head's subprocess posture: a non-git root,
    an unknown commit, or an unavailable git all yield None (the caller treats
    None conservatively as "cannot prove docs-only" → refuse).
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", base, head],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def observation_gap_promotable(meta: dict) -> bool:
    """Is this MCP_TEST_RESULTS.md metadata a sanctioned observation-gap partial?

    The SINGLE home for the "scoped observation-gap partial" promotion predicate.
    THREE routing/gate sites route through this helper so they cannot diverge
    (the divergence that produced the 2026-07 Step-9 observation-gap DEADLOCK —
    see hardening-log Round for community-sharing): (1) the
    ``__write_validated_from_results__`` apply gate in ``apply_pseudo``, (2) the
    completion-integrity gate in ``evaluate_completion_evidence``, and (3) the
    Step-9 MCP routing in ``lazy-state.py`` / ``bug-state.py``.

    Background (Gap 1 coupling,
    harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 1): some
    behavior classes are SPEC-LOCKED to the unit/WDIO test tier (see
    ``docs/features/mcp-testing/SPEC.md``) and thus have no MCP UI driver to
    exercise them end-to-end. A run over such a feature honestly carries
    ``result: partial`` even though its MCP-driveable scope fully passes. The
    downstream apply + completion gates ALREADY accept this disposition; the
    Step-9 routing did not, so a valid observation-gap partial re-dispatched
    ``/mcp-test`` every cycle — an infinite loop ONE LAYER UP from the deadlock
    the completion gate's comment warns about.

    Promotion is gated NARROWLY — a ``result: partial`` promotes ONLY when its
    ``observation_gap_exemptions`` is a NON-EMPTY list whose EVERY entry is a
    mapping carrying a non-empty ``spec_class`` provenance string (the citation
    that distinguishes a verified untestable-class assessment from a convenience
    skip — mirroring the SKIP_MCP_TEST.md ``spec_class``-required discipline).

    This predicate is HALF of the AND: callers MUST still enforce the
    ``pass_count == total_count`` cross-check separately, so a ``partial`` with a
    GENUINE MCP-scope failure (pass < total) is NOT promoted. A ``partial`` with
    no exemptions, or a provenance-less exemption, returns False here.
    """
    if meta.get("result") != "partial":
        return False
    exemptions = meta.get("observation_gap_exemptions")
    return (
        isinstance(exemptions, list)
        and len(exemptions) > 0
        and all(
            isinstance(e, dict)
            and isinstance(e.get("spec_class"), str)
            and e.get("spec_class", "").strip() != ""
            for e in exemptions
        )
    )


def _is_noninvalidating_drift_path(path: str) -> bool:
    """Can this changed path NOT invalidate an MCP validation? (drift carve-out)

    Two STRUCTURAL classes of changed file cannot make a recorded
    ``validated_commit`` stale relative to HEAD for the Step-9 staleness gate,
    because neither is the code-under-test:

      * any Markdown file (``*.md``) — MCP_TEST_RESULTS.md, PHASES.md
        reconciliation, spec docs. The original Round-36 (2026-06-23) carve-out.
      * an MCP test-SCENARIO definition (``*.yaml`` / ``*.yml``) that lives under
        an ``mcp-test`` / ``mcp-tests`` path segment — the scenario CORPUS
        (e.g. ``docs/testing/mcp-tests/corpus/live/<name>.yaml``). An /mcp-test
        FIRST-RUN authors these scenario files and commits them alongside
        MCP_TEST_RESULTS.md, so the structurally-unavoidable one-commit results
        lag includes them. A scenario definition IS the test, never the
        product code it exercises, so it cannot invalidate the validation
        (harden 2026-07: the ``.md``-only carve-out forced a wasted re-verify
        cycle on every first-run validation — the scenario ``.yaml`` in the same
        commit tripped ``non-docs-drift``).

    The mcp-test path-segment scope is what keeps a product ``config.yaml`` /
    ``.github/workflows/*.yml`` OUT of the carve-out — those carry no
    ``mcp-test(s)`` segment, so they still (correctly) classify as invalidating
    (TOCTOU) drift. Suffix + segment checks are case-insensitive and
    separator-normalized.
    """
    p = path.lower().replace("\\", "/")
    if p.endswith(".md"):
        return True
    if p.endswith((".yaml", ".yml")):
        return any(seg in ("mcp-test", "mcp-tests") for seg in p.split("/"))
    return False


def commit_drift_verdict(
    repo_root: Path, validated_commit, head
) -> dict:
    """Classify the drift between a recorded ``validated_commit`` and ``head``.

    The SINGLE home for the "stale MCP results" docs-only carve-out. Three call
    sites route through this helper so they cannot diverge (the divergence that
    produced the 2026-06-23 Step-9 re-verify DEADLOCK — see hardening-log Round
    36): (1) ``evaluate_completion_evidence`` (completion-coverage audit), (2)
    the Step-9 freshness gate in ``lazy-state.py`` / ``bug-state.py``, and (3)
    the ``__write_validated_from_results__`` apply gate in ``apply_pseudo``.

    WHY a docs-only carve-out is correct (and not a gate-weakening): an
    ``/mcp-test`` cycle that obeys its turn-end clean-tree contract MUST commit
    ``MCP_TEST_RESULTS.md`` — and that commit advances HEAD exactly one past the
    ``validated_commit`` it just recorded. On a FIRST-RUN validation the same
    commit ALSO carries the newly-authored mcp-test SCENARIO files
    (``*.yaml``/``*.yml`` under the ``mcp-test(s)`` corpus). The results file is
    therefore PERPETUALLY one commit stale, and that one-commit drift is a
    PURE NON-INVALIDATING delta (docs + scenario definitions — see
    ``_is_noninvalidating_drift_path``). Strict ``validated_commit == HEAD`` is
    structurally unsatisfiable in that bracket → an infinite re-verify loop on
    EVERY feature/bug (and the ``.md``-only carve-out forced a wasted re-verify
    on every first-run whose commit included scenario ``.yaml`` — harden
    2026-07). Accepting non-invalidating drift restores liveness WITHOUT
    weakening the TOCTOU guard: any real source / script / product-config drift
    still refuses, because that is genuine "the validated code is not the code
    being promoted" risk.

    Returns ``{verdict, non_docs, changed}`` where ``verdict`` ∈:
      - ``"fresh"``         — ``validated_commit`` / ``head`` unresolved (None /
                              blank) OR equal. The caller's existing
                              legacy-permissive / equality path applies; this
                              helper does NOT run ``git diff`` in that case.
      - ``"docs-only"``     — drift is exclusively NON-INVALIDATING validation
                              artifacts (``*.md`` docs, or mcp-test SCENARIO
                              ``*.yaml``/``*.yml`` under an ``mcp-test(s)`` path
                              segment — see ``_is_noninvalidating_drift_path``)
                              → safe to accept-and-validate. (Verdict string kept
                              as ``"docs-only"`` for call-site compatibility even
                              though scenario files are not ``.md``.)
      - ``"non-docs-drift"``— ≥1 non-``.md`` path changed → refuse-and-revalidate
                              (TOCTOU). ``non_docs`` lists the offending paths.
      - ``"unresolvable"``  — the diff could not be computed (non-git root,
                              unknown commit, git unavailable) → caller refuses
                              conservatively (cannot prove docs-only).

    Best-effort and side-effect-free, mirroring ``_git_diff_name_only`` /
    ``_current_head`` subprocess posture.
    """
    vc = str(validated_commit).strip() if validated_commit is not None else ""
    hd = str(head).strip() if head is not None else ""
    if not vc or not hd or vc == hd:
        # Unresolved or equal — not a drift this helper classifies. The caller
        # owns the legacy-permissive (missing field / non-git) + equality paths.
        return {"verdict": "fresh", "non_docs": [], "changed": []}
    changed = _git_diff_name_only(repo_root, vc, hd)
    if changed is None:
        return {"verdict": "unresolvable", "non_docs": [], "changed": []}
    non_docs = [p for p in changed if not _is_noninvalidating_drift_path(p)]
    if non_docs:
        return {
            "verdict": "non-docs-drift",
            "non_docs": non_docs,
            "changed": changed,
        }
    return {"verdict": "docs-only", "non_docs": [], "changed": changed}


# ---------------------------------------------------------------------------
# autotick_verification_rows — atomic, line-anchored, audited auto-tick rewrite
#   (completion-coherence-gate-reconciliation Phase 2).
#
# Given a feature whose Phase-1 verdict is exempt-and-tick / warn-exempt, rewrite
# every remaining unchecked verification-marked row (``- [ ]`` carrying the
# canonical ``_VERIFICATION_ONLY_MARKER`` on the SAME line) to ``- [x]`` —
# atomically (via _atomic_write), fence-safely, with a byte-stable audit comment,
# under a cardinality over-relaxation guard, and Superseded-aware. NOT wired into
# the completion gate here (Phase 3 owns the ordering: tick → re-check → receipt).
# ---------------------------------------------------------------------------

# An unchecked checkbox row, capturing the leading dash+bracket so the rewrite
# preserves indentation and replaces ONLY the inner blank with 'x'. Tolerates
# variable interior whitespace (``- [ ]`` / ``- [  ]``).
_UNCHECKED_ROW_RE = re.compile(r"^(\s*-\s+\[)\s+(\]\s.*)$")

# Idempotency marker: a row already carrying this comment is NOT re-ticked and
# the comment is NOT duplicated.
_AUTOTICK_COMMENT_PREFIX = "<!-- auto-ticked: validated_commit="


def autotick_verification_rows(
    phases_path: Path, validated_commit, pass_count: int
) -> dict:
    """Rewrite unchecked verification-marked rows to ``- [x]`` atomically.

    Returns ``{ticked_count: int, ok: bool, reason: str|None}``.

    A row is rewritten iff ALL hold:
      * it matches ``^\\s*-\\s+\\[\\s+\\]`` (an unchecked box, variable interior
        whitespace tolerated),
      * it carries ``_VERIFICATION_ONLY_MARKER`` (or its enclosing subsection
        header does — header-scope, mirroring
        ``remaining_unchecked_are_verification_only``),
      * it is NOT inside a ``` code fence,
      * it is NOT under a phase whose Status is ``Superseded``.

    Each rewritten row gets a byte-stable
    ``<!-- auto-ticked: validated_commit=<sha> -->`` audit comment appended so a
    later auditor distinguishes gate mutations from human/agent edits.

    **Cardinality lock (over-relaxation guard):** if the number of rows that
    WOULD be ticked exceeds ``pass_count``, the rewrite ABORTS writing nothing
    (``ok: False``) — catching marker-drift hallucination / forged evidence.

    **Atomic:** the file is rewritten via ``_atomic_write`` (temp-in-same-dir →
    ``os.replace``); a cardinality abort leaves the file byte-identical (no
    partial write — the count is computed BEFORE any write).

    **Idempotent:** a row already carrying the audit comment is skipped (not
    re-ticked, no duplicate comment); ``ticked_count`` counts only rows newly
    flipped this call.
    """
    text = phases_path.read_text(encoding="utf-8")
    src_lines = text.splitlines(keepends=True)

    # First PASS — identify the line indices to tick (cardinality computed
    # BEFORE any mutation so an abort writes nothing).
    to_tick: list[int] = []
    section_has_marker = False
    in_superseded_phase = False
    in_fence = False
    for idx, raw in enumerate(src_lines):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if heading:
            heading_text = heading.group(1)
            if re.match(r"Phase\s+\d+", heading_text):
                # New phase block — reset subsection + superseded tracking.
                in_superseded_phase = False
                section_has_marker = False
            else:
                section_has_marker = _VERIFICATION_ONLY_MARKER in raw
            continue
        if stripped.startswith("**"):
            bold = re.match(r"^\*\*(.+?)\*\*", stripped)
            if bold:
                bold_text = bold.group(1)
                if re.match(r"Status\s*:", bold_text) and "Superseded" in stripped:
                    in_superseded_phase = True
                    continue
                if _VERIFICATION_ONLY_MARKER in raw:
                    section_has_marker = True
                # else: preserve current scope (non-marker bold is prose).
                continue
        m = _UNCHECKED_ROW_RE.match(raw.rstrip("\r\n"))
        if not m:
            continue
        if in_superseded_phase:
            continue
        row_has_marker = _VERIFICATION_ONLY_MARKER in raw
        if not (row_has_marker or section_has_marker):
            continue
        # Idempotency: an already-audited row is not re-ticked.
        if _AUTOTICK_COMMENT_PREFIX in raw:
            continue
        to_tick.append(idx)

    # Cardinality lock — abort writing nothing on over-relaxation.
    if len(to_tick) > pass_count:
        return {
            "ticked_count": 0,
            "ok": False,
            "reason": (
                f"cardinality lock: {len(to_tick)} verification row(s) would be "
                f"ticked but only {pass_count} test(s) passed — refusing the "
                "auto-tick (marker-drift / forged-evidence guard)"
            ),
        }

    if not to_tick:
        return {"ticked_count": 0, "ok": True, "reason": None}

    # Second PASS — rewrite the identified rows in place, preserving the line
    # ending and flipping ONLY the inner blank to 'x', then appending the audit
    # comment before the line ending.
    audit = f"{_AUTOTICK_COMMENT_PREFIX}{validated_commit} -->"
    tick_set = set(to_tick)
    out_lines: list[str] = []
    for idx, raw in enumerate(src_lines):
        if idx not in tick_set:
            out_lines.append(raw)
            continue
        # Split the line ending off.
        ending = ""
        body = raw
        if raw.endswith("\r\n"):
            ending, body = "\r\n", raw[:-2]
        elif raw.endswith("\n"):
            ending, body = "\n", raw[:-1]
        elif raw.endswith("\r"):
            ending, body = "\r", raw[:-1]
        m = _UNCHECKED_ROW_RE.match(body)
        # ``m`` is guaranteed (idx came from the same regex in pass 1).
        new_body = f"{m.group(1)}x{m.group(2)} {audit}"
        out_lines.append(new_body + ending)

    _atomic_write(phases_path, "".join(out_lines))
    return {"ticked_count": len(to_tick), "ok": True, "reason": None}


# ---------------------------------------------------------------------------
# Completion ledger verification
# ---------------------------------------------------------------------------

def _phases_text_scoped_to(phases_text: str, phase_set: set[int]) -> str:
    """Return the subset of PHASES.md lines belonging to phases in ``phase_set``.

    Phase 9 WU-3 helper: the plan-scoped ``deliverables_done`` check must apply
    the SAME verification-only exemption mid-feature
    (``remaining_unchecked_are_verification_only``) but only over the plan's
    phases. ``_unchecked_wus_in_plan_scope`` already collects in-scope unchecked
    rows but does NOT distinguish verification rows, so instead we slice the
    PHASES body down to the in-scope ``### Phase N`` sections (each section runs
    from its ``### Phase N`` heading until the next phase heading or a ``## ``
    top-level boundary) and hand that slice to the existing exemption helper.

    Fence-aware in the same spirit as ``_unchecked_wus_in_plan_scope``: a fenced
    block opened inside an in-scope phase stays part of that phase's slice (the
    downstream helper re-tracks fences itself, so we simply preserve the lines).
    """
    out: list[str] = []
    current_phase: int | None = None
    for line in phases_text.splitlines():
        h = re.match(r"^###\s+Phase\s+(\d+)", line)
        if h:
            current_phase = int(h.group(1))
            if current_phase in phase_set:
                out.append(line)
            continue
        # A top-level ``## `` heading (NOT ``### Phase``) closes phase tracking —
        # content after it is not part of any in-scope phase. Keep the verification
        # heading recognizable to the exemption helper by re-emitting the line only
        # when we are still inside an in-scope phase.
        if line.startswith("## ") and not line.startswith("### "):
            current_phase = None
            continue
        if current_phase is not None and current_phase in phase_set:
            out.append(line)
    return "\n".join(out)


# A per-WU plan progress checkbox: ``- [ ] WU-N — <title>`` / ``- [x] WU-N …``.
# Made mandatory by write-plan ISSUE-6 (d8-effect-chains run 2026-06-14): every
# work unit in every generated plan part carries exactly one such row in a
# ``## Work Units`` checklist. ``/execute-plan`` ticks each as it lands the WU,
# so these rows are the MACHINE source of truth for plan-part deliverable
# completion (PHASES.md per-deliverable ticks are demoted to human documentation
# — see the verify_ledger docstring + write-plan/execute-plan SKILL prose).
#
# The WU id may be a bare number (``WU-3``) or a dotted sub-id (``WU-9.0``,
# ``WU-3a``) — accept any ``[A-Za-z0-9.]+`` run after ``WU-``. The separator after
# the id is the em-dash convention but we do not require it (a ``- [ ] WU-3``
# with no title still counts as a progress row). The match is anchored at the
# list-item bullet so a mid-prose mention of "WU-3" is NOT a false checkbox.
_PLAN_WU_CHECKBOX_RE = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX])\]\s*WU-[A-Za-z0-9.]+\b",
)


# ---------------------------------------------------------------------------
# completion-gate-refusal-opacity: verify_ledger `failing_detail` collectors.
#
# The `--verify-ledger` refusal historically named only the boolean
# `failing_check` — every axis had already computed the offending items
# (dirty files, divergent shas, incomplete plans, unchecked rows) and thrown
# them away, forcing the orchestrator to re-probe by hand. These collectors
# reuse the SAME fence-aware walks as count_deliverables /
# _plan_wu_checkbox_counts / _unchecked_wus_in_plan_scope so the diagnostic
# rows are byte-identical in shape to what the gate already computes — no new
# parsing surface, just line-number-annotated capture instead of a boolean
# reduction. Cap (`_DETAIL_MAX_ITEMS`) and excerpt truncation (`_excerpt`)
# mirror `classify_blocking_unchecked_rows`'s 80-char convention.
# ---------------------------------------------------------------------------
_DETAIL_MAX_ITEMS = 10


def _excerpt(text: str, max_chars: int = 80) -> str:
    """Truncate ``text`` to ``max_chars`` with an ellipsis marker — the same
    80-char convention ``classify_blocking_unchecked_rows`` uses."""
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _phases_unchecked_row_detail(
    phases_text: str, phase_set: set[int] | None = None, limit: int = _DETAIL_MAX_ITEMS
) -> dict:
    """Collect unchecked PHASES.md ``- [ ]`` rows with 1-based line numbers.

    Fence-aware, mirroring ``count_deliverables``. When ``phase_set`` is given,
    only rows inside a ``### Phase N`` section whose N is a member are
    collected (mirrors ``_unchecked_wus_in_plan_scope``'s heading-tracking
    walk — the legacy plan-scoped fallback); ``None`` scans the whole file
    (feature-level / unscoped-legacy-plan semantics).

    Returns ``{"rows": [{"line": N, "text": <=80-char excerpt}, ...], "total": M}``
    — ``rows`` capped at ``limit``, ``total`` uncapped (so a caller can report
    "N more" truncation honestly).
    """
    rows: list[dict] = []
    total = 0
    in_fence = False
    current_phase: int | None = None
    tracking = phase_set is not None
    for lineno, line in enumerate(phases_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if tracking:
            h = re.match(r"^###\s+Phase\s+(\d+)", line)
            if h:
                current_phase = int(h.group(1))
                continue
            if line.startswith("## "):
                current_phase = None
                continue
            if current_phase is None or current_phase not in phase_set:
                continue
        if re.match(r"^\s*-\s*\[\s*\]", line):
            total += 1
            if len(rows) < limit:
                rows.append({"line": lineno, "text": _excerpt(stripped)})
    return {"rows": rows, "total": total}


def _plan_wu_unchecked_row_detail(plan_text: str, limit: int = _DETAIL_MAX_ITEMS) -> dict:
    """Collect unchecked ISSUE-6 ``- [ ] WU-N`` rows with 1-based line numbers.

    Fence-aware, mirroring ``_plan_wu_checkbox_counts``'s walk. Same return
    shape as ``_phases_unchecked_row_detail`` — the ``deliverables_done``
    diagnostic for the ``plan-wu-checkboxes`` source.
    """
    rows: list[dict] = []
    total = 0
    in_fence = False
    for lineno, line in enumerate(plan_text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _PLAN_WU_CHECKBOX_RE.match(line)
        if not m or m.group("mark") != " ":
            continue
        total += 1
        if len(rows) < limit:
            stripped = line.strip()
            rows.append({"line": lineno, "text": _excerpt(stripped)})
    return {"rows": rows, "total": total}


def _plan_wu_checkbox_counts(plan_text: str) -> tuple[int, int]:
    """Return ``(unchecked, checked)`` counts of per-WU plan progress checkboxes.

    Parses the ISSUE-6 ``- [ ] WU-N — <title>`` / ``- [x] WU-N …`` rows from a
    plan part's body. Fence-aware in the same spirit as ``count_deliverables``:
    a checkbox inside a triple-backtick code fence is an illustrative example
    (e.g. the write-plan SKILL's own format sample) and is NOT counted.

    ``(0, 0)`` means the plan has NO parseable per-WU checkboxes at all — a
    legacy pre-ISSUE-6 plan. The caller uses that to fall back to the
    PHASES-phase-level behavior (with a diagnostic) rather than vacuously pass.
    """
    unchecked = 0
    checked = 0
    in_fence = False
    for line in plan_text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _PLAN_WU_CHECKBOX_RE.match(line)
        if not m:
            continue
        if m.group("mark") == " ":
            unchecked += 1
        else:
            checked += 1
    return unchecked, checked


def _plan_unchecked_wus_are_verification_only(plan_text: str) -> bool:
    """Return True iff every UNCHECKED ``- [ ] WU-N`` row in the plan body sits
    under a Runtime Verification / MCP Integration Test subsection.

    Preserves the verification-only-row exemption (the same one
    ``remaining_unchecked_are_verification_only`` applies to PHASES.md) but at
    the PLAN-WU granularity: a per-WU checkbox under a gate-owned
    ``**Runtime Verification**`` / ``## MCP Integration Test`` subsection is
    ticked by the Step-9 ``/mcp-test`` gate, NOT by ``/execute-plan``, so it must
    not fail the plan-part ``deliverables_done`` verdict.

    Reuses ``remaining_unchecked_are_verification_only`` over the plan body so the
    section-detection logic (markdown headings AND bold markers, fence-aware,
    Superseded-phase aware) is identical to the PHASES.md path — but only the
    ``- [ ] WU-N`` rows participate, because the underlying helper returns False
    on the FIRST unchecked ``- [ ]`` it sees outside a verification subsection,
    and an ISSUE-6-compliant plan body's only ``- [ ]`` rows ARE the WU rows plus
    any verification rows. (A stray non-WU ``- [ ]`` in the plan body would
    conservatively be treated as non-verification work — the safe direction.)
    """
    return remaining_unchecked_are_verification_only(plan_text)


def verify_ledger(repo_root: Path, spec_path: Path, plan_path: Path | None = None) -> dict:
    """Verify the four completion-ledger preconditions for a feature.

    Called by lazy-state.py and bug-state.py with ``--verify-ledger <spec_path>``
    as a scripted replacement for the five duplicated prose "completion ledger"
    guard blocks across the lazy skills (lazy/SKILL.md Step 4).

    Checks (evaluated in this exact order; ALL four are always computed):

    1. ``clean_tree`` — ``git -C <repo_root> status --short`` produces no output.
       An untracked, modified, or staged file means the feature's changes have
       not been fully committed. Any OSError or subprocess failure returns False.

    2. ``head_matches_origin`` — ``git rev-parse HEAD`` equals
       ``git rev-parse @{u}`` (the upstream tracking ref). A local commit that
       has not been pushed, or a repo with no upstream configured, returns False.

    3. ``plan_complete`` — at least one non-retro implementation plan exists AND
       every such plan has ``status: Complete`` in its frontmatter. Uses
       ``_has_any_complete_plan`` (at least one Complete) combined with
       ``find_implementation_plans`` (no non-Complete plans remain), which together
       are equivalent to "all plans exist and all are Complete". False when any
       plan has a non-Complete status.
       ABSENT-BY-DESIGN (harness-hardening-retro-fixes Phase 3): a feature with
       NO implementation plan on disk and none required (only ``realign-*.md`` /
       ``retro-*.md``, or no plans at all — ``_implementation_plans_exist`` is
       False) is treated as plan_complete=True (a diagnostic notes it fired),
       NOT a false-alarm False. A feature WITH an incomplete implementation plan
       still returns False (the regression guard). Feature-level only — the
       plan-SCOPED branch reads the named plan's own status and is unaffected.

    4. ``deliverables_done`` — zero real (non-verification) unchecked
       deliverables remain. The SURFACE this reads depends on scope (see below).
       "Real" / verification-exempt is defined by
       ``remaining_unchecked_are_verification_only``: rows under a
       "Runtime Verification / MCP Integration Test" subsection heading are
       exempt workstation-only checks ticked by the Step-9 ``/mcp-test`` gate.

    Plan-scoped mode (``plan_path`` given) — deliverables_done SOURCE OF TRUTH
    (2026-06-15, d8-effect-chains review
    ``docs/features/audio/audio-vision/domains/d8-effect-chains/LAZY_BATCH_REVIEW_2026-06-15.md``):
      Multi-part plans split one feature across several plan files (each with a
      ``phases:`` set). Feature-level checks 3 + 4 fire false alarms while later
      parts are legitimately pending. When ``plan_path`` is provided, checks 3
      and 4 narrow to THAT plan's scope; checks 1 and 2 are unchanged:
        - ``plan_complete`` = THIS plan's frontmatter ``status:`` == ``Complete``
          (read via ``_plan_status`` — the same parser ``find_implementation_plans``
          and the stale-flip logic use). A missing ``plan_path`` file parses to the
          legacy default ``Ready`` → False.
        - ``deliverables_done`` reads the PLAN PART's own per-WU checkboxes
          (``- [ ] WU-N`` — mandatory since write-plan ISSUE-6) as the MACHINE
          record, NOT the PHASES.md phase-level deliverable rows. The plan part is
          the unit of execution and its WUs never span parts or phases, so this
          eliminates BOTH false-fail classes the PHASES-scoped read suffered:
          (a) cross-part — a phase-level deliverable belonging to part-3 failing
          the part-2 check (a phase spans parts); (b) cross-phase attribution — a
          deliverable filed under Phase 5 but built in corrective Phase 6 sitting
          done-but-unticked. Done iff no unchecked ``- [ ] WU-N`` rows remain,
          with the verification-only exemption applied at the WU level
          (``_plan_unchecked_wus_are_verification_only``).
        - LEGACY FALLBACK: a pre-ISSUE-6 plan with NO parseable per-WU checkboxes
          falls back to the prior PHASES-phase-level behavior (scoped to the
          plan's ``phases:``; or feature-level when the plan has no ``phases:`` —
          unknown scope must not vacuously pass) and records
          ``deliverables_source: "phases-fallback (legacy plan — no per-WU
          checkboxes)"`` so the operator knows the legacy path fired. Legacy plans
          are NOT hard-failed.
      ``plan_path=None`` → byte-for-byte the original feature-level behavior
      (the whole feature's PHASES.md via ``count_deliverables`` +
      ``remaining_unchecked_are_verification_only``). If PHASES.md does not exist
      at feature level, returns False (no evidence phases were completed).

    Return shape:
    ```
    {
        "ok": bool,                  # True iff ALL four checks are True
        "failing_check": str | None, # First False check key (order above), or None
        "checks": {
            "clean_tree": bool,
            "head_matches_origin": bool,
            "plan_complete": bool,
            "deliverables_done": bool,
        },
        "deliverables_source": str,  # diagnostic (additive, never gates):
                                     #   "plan-wu-checkboxes"       — new machine record
                                     #   "phases-fallback (…)"      — legacy plan path fired
                                     #   "phases-feature-level"     — no plan_path (whole feature)
        "failing_detail": dict,      # diagnostic (additive, never gates) — the
                                     # offending items for EVERY False check,
                                     # keyed by check name; {} when ok is True
                                     # (completion-gate-refusal-opacity):
                                     #   clean_tree -> {dirty_files: [...], total_count, git_error?}
                                     #   head_matches_origin -> {no_upstream, head_sha?, upstream_sha?, ahead?, behind?}
                                     #   plan_complete -> scoped: {plan_file, plan_status}
                                     #                    feature-level: {incomplete_plans: [{file, status}], total_count}
                                     #   deliverables_done -> {rows: [{line, text}], total, note?}
    }
    ```

    ``ok`` is True only when all four checks are True. ``failing_check`` names
    the FIRST False check in the defined order; None when ok is True. All four
    ``checks`` values are always populated and accurate regardless of which check
    fails first — no short-circuit pruning is applied to the ``checks`` dict.
    """
    # --- check 1: clean working tree ---
    # Mirror the subprocess style used in _current_head in lazy-state.py:
    # capture_output + text + timeout guard, catch OSError/SubprocessError.
    # `_clean_tree_stdout` / `_clean_tree_errored` are retained (not just the
    # boolean) so a False verdict's failing_detail can name the dirty files
    # instead of discarding the already-captured `git status --short` output
    # (completion-gate-refusal-opacity Fix Scope §1).
    _clean_tree_stdout = ""
    _clean_tree_errored = False
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        clean_tree = result.stdout.strip() == ""
        _clean_tree_stdout = result.stdout
    except (OSError, subprocess.SubprocessError):
        clean_tree = False
        _clean_tree_errored = True

    # --- check 2: HEAD matches upstream tracking ref ---
    # Both rev-parse commands must succeed and return identical SHA strings.
    # `_head_sha` / `_upstream_sha` / `_no_upstream` are retained for the
    # failing_detail payload (short shas + an explicit no-upstream
    # discriminator, distinct from a genuine divergence).
    _head_sha = ""
    _upstream_sha = ""
    _no_upstream = True
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
            head_matches_origin = bool(head_sha and upstream_sha and head_sha == upstream_sha)
            _head_sha, _upstream_sha, _no_upstream = head_sha, upstream_sha, False
        else:
            # @{u} can fail when no upstream is configured — treat as mismatch.
            head_matches_origin = False
            _head_sha = head_result.stdout.strip() if head_result.returncode == 0 else ""
            _no_upstream = upstream_result.returncode != 0
    except (OSError, subprocess.SubprocessError):
        head_matches_origin = False

    # --- Plan scope (Phase 9 WU-3): None → feature-level (original behavior) ---
    # When plan_path is given, checks 3 + 4 narrow to that plan's declared phase
    # set. An empty phase set (no `phases:`) means unknown scope → fall back to
    # the feature-level deliverables_done semantics below.
    scoped = plan_path is not None
    plan_phase_set: set[int] = _plan_phase_set(plan_path) if scoped else set()

    # --- check 3: implementation plan(s) Complete ---
    if scoped:
        # Plan-scoped: ONLY this plan's own frontmatter status matters. Read it
        # via _plan_status (the same parser find_implementation_plans uses); a
        # missing plan_path file parses to the legacy default "Ready" → not
        # Complete → False.
        plan_complete = _plan_status(plan_path) == "Complete"
    else:
        # Feature-level: every implementation plan must be Complete (≥1 exists).
        # _has_any_complete_plan: at least one plan has status: Complete.
        # find_implementation_plans: returns only non-Complete plans.
        # Together: any_complete AND no_incomplete → all plans Complete (and ≥1).
        any_complete = _has_any_complete_plan(spec_path)
        incomplete_plans = find_implementation_plans(spec_path)
        plan_complete = any_complete and len(incomplete_plans) == 0
        # --- absent-by-design (harness-hardening-retro-fixes Phase 3, WU-1) ---
        # A plan-less / realign-plan-only feature has NO implementation plan and
        # never needed one. The rule above returns False for it (any_complete is
        # False — there is no Complete IMPLEMENTATION plan), producing a
        # benign-but-noisy false-alarm plan_complete:false + recovery chase.
        # Distinguish absent-by-design (no implementation plan present, none
        # required) from incomplete (an implementation plan exists but is not
        # Complete): when there are zero incomplete plans AND no Complete plan
        # AND genuinely NO implementation plan on disk (only realign-*/retro-*,
        # or no plans at all — _implementation_plans_exist is False), treat
        # plan_complete as True (absent-by-design). A feature WITH an incomplete
        # implementation plan keeps plan_complete=False (the regression guard) —
        # _implementation_plans_exist is True in that case.
        if not plan_complete and len(incomplete_plans) == 0 and not any_complete:
            if not _implementation_plans_exist(spec_path):
                plan_complete = True
                _diag(
                    "plan_complete: no implementation plan required "
                    "(absent-by-design)"
                )

    # --- check 4: no real (non-verification) unchecked deliverables ---
    #
    # SOURCE OF TRUTH (2026-06-15 — d8-effect-chains review):
    #   * Plan-scoped (``plan_path`` given): the PLAN PART's own per-WU
    #     checkboxes (``- [ ] WU-N`` — mandatory since write-plan ISSUE-6) are
    #     the machine record. The plan part is the unit of execution and its WUs
    #     never span parts or phases, so reading them eliminates BOTH the
    #     cross-part false-fail (a Phase-5 deliverable belonging to part-3 failing
    #     the part-2 check) AND the cross-phase-attribution false-fail (a
    #     deliverable filed under Phase 5 but built in corrective Phase 6 sitting
    #     done-but-unticked). PHASES.md per-deliverable ticks are now
    #     human-readable documentation, NOT the gate.
    #   * Legacy fallback: a pre-ISSUE-6 plan with NO parseable per-WU checkboxes
    #     falls back to the prior PHASES-phase-level behavior and records
    #     ``deliverables_source`` so the operator knows the legacy path fired.
    #   * Feature-level (no ``plan_path`` — used by /mcp-test cycles): unchanged;
    #     it legitimately checks the whole feature's PHASES.md.
    phases_file = spec_path / "PHASES.md"
    # Diagnostic: which surface produced the deliverables_done verdict.
    deliverables_source = "phases-feature-level"
    if scoped:
        # Plan-scoped: prefer the plan part's own per-WU checkboxes.
        plan_text = ""
        if plan_path is not None and plan_path.exists():
            try:
                plan_text = plan_path.read_text(encoding="utf-8")
            except OSError:
                plan_text = ""
        wu_unchecked, wu_checked = _plan_wu_checkbox_counts(plan_text)
        if wu_unchecked or wu_checked:
            # ISSUE-6-compliant plan: the per-WU checkboxes ARE the machine
            # record. Done iff no unchecked WU rows remain — with the
            # verification-only exemption (a WU row under a Runtime Verification /
            # MCP Integration Test subsection is ticked by the Step-9 /mcp-test
            # gate, not by /execute-plan).
            deliverables_source = "plan-wu-checkboxes"
            if wu_unchecked == 0:
                deliverables_done = True
            else:
                deliverables_done = _plan_unchecked_wus_are_verification_only(plan_text)
        else:
            # Legacy pre-ISSUE-6 plan (no per-WU checkboxes): fall back to the
            # PHASES-phase-level behavior, scoped to the plan's phases. Emit a
            # diagnostic so the operator knows the legacy path fired.
            deliverables_source = "phases-fallback (legacy plan — no per-WU checkboxes)"
            if not phases_file.exists():
                deliverables_done = False
            else:
                phases_text = phases_file.read_text(encoding="utf-8")
                if plan_phase_set:
                    in_scope_unchecked = _unchecked_wus_in_plan_scope(phases_text, plan_phase_set)
                    if not in_scope_unchecked:
                        deliverables_done = True
                    else:
                        scoped_text = _phases_text_scoped_to(phases_text, plan_phase_set)
                        deliverables_done = remaining_unchecked_are_verification_only(scoped_text)
                else:
                    # Legacy plan with NO `phases:` set → unknown scope → must NOT
                    # vacuously pass; use feature-level semantics over all of PHASES.
                    unchecked, _checked = count_deliverables(phases_text)
                    if unchecked == 0:
                        deliverables_done = True
                    else:
                        deliverables_done = remaining_unchecked_are_verification_only(phases_text)
    else:
        # Feature-level (no plan_path): the whole feature's PHASES.md.
        if not phases_file.exists():
            # No PHASES.md means we have no evidence of phases being completed.
            deliverables_done = False
        else:
            phases_text = phases_file.read_text(encoding="utf-8")
            unchecked, _checked = count_deliverables(phases_text)
            if unchecked == 0:
                deliverables_done = True
            else:
                # Remaining unchecked rows may be exempted if they are all under
                # a Runtime Verification / MCP Integration Test subsection.
                deliverables_done = remaining_unchecked_are_verification_only(phases_text)

    # --- assemble result: determine first failing check in defined order ---
    checks = {
        "clean_tree": clean_tree,
        "head_matches_origin": head_matches_origin,
        "plan_complete": plan_complete,
        "deliverables_done": deliverables_done,
    }
    failing_check: str | None = None
    for key in ("clean_tree", "head_matches_origin", "plan_complete", "deliverables_done"):
        if not checks[key]:
            failing_check = key
            break

    # --- failing_detail (completion-gate-refusal-opacity, Fix Scope §1) ---
    # Populate the offending items for EVERY False check (not just the first),
    # so a single probe is diagnostic on every axis instead of the
    # orchestrator fixing one check and re-probing for the next. Additive
    # only — `ok`/`failing_check`/`checks`/`deliverables_source` are
    # byte-identical to before; an `ok: true` payload carries an empty dict.
    failing_detail: dict = {}
    if not clean_tree:
        dirty_lines = [ln for ln in _clean_tree_stdout.splitlines() if ln.strip()]
        detail_ct: dict = {
            "dirty_files": dirty_lines[:_DETAIL_MAX_ITEMS],
            "total_count": len(dirty_lines),
        }
        if _clean_tree_errored:
            detail_ct["git_error"] = True
        failing_detail["clean_tree"] = detail_ct
    if not head_matches_origin:
        detail_hm: dict = {"no_upstream": _no_upstream}
        if _head_sha:
            detail_hm["head_sha"] = _head_sha[:12]
        if not _no_upstream and _upstream_sha:
            detail_hm["upstream_sha"] = _upstream_sha[:12]
            try:
                lr = subprocess.run(
                    ["git", "-C", str(repo_root), "rev-list", "--left-right",
                     "--count", "@{u}...HEAD"],
                    capture_output=True, text=True, timeout=30,
                )
                if lr.returncode == 0:
                    parts = lr.stdout.split()
                    if len(parts) == 2:
                        detail_hm["behind"] = int(parts[0])
                        detail_hm["ahead"] = int(parts[1])
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        failing_detail["head_matches_origin"] = detail_hm
    if not plan_complete:
        if scoped:
            failing_detail["plan_complete"] = {
                "plan_file": plan_path.name if plan_path is not None else None,
                "plan_status": _plan_status(plan_path) if plan_path is not None else None,
            }
        else:
            failing_detail["plan_complete"] = {
                "incomplete_plans": [
                    {"file": p.name, "status": _plan_status(p)}
                    for p in incomplete_plans[:_DETAIL_MAX_ITEMS]
                ],
                "total_count": len(incomplete_plans),
            }
    if not deliverables_done:
        if deliverables_source == "plan-wu-checkboxes":
            failing_detail["deliverables_done"] = _plan_wu_unchecked_row_detail(plan_text)
        elif phases_file.exists():
            # phases-fallback (legacy plan) or phases-feature-level: re-read
            # PHASES.md fresh here so this block never depends on which
            # branch above happened to bind `phases_text` — diagnostic-only,
            # on the refusal path (not a hot loop).
            _pt = phases_file.read_text(encoding="utf-8")
            _scope = plan_phase_set if (scoped and plan_phase_set) else None
            failing_detail["deliverables_done"] = _phases_unchecked_row_detail(_pt, phase_set=_scope)
        else:
            failing_detail["deliverables_done"] = {"rows": [], "total": 0, "note": "PHASES.md absent"}

    return {
        "ok": failing_check is None,
        "failing_check": failing_check,
        "checks": checks,
        # Diagnostic (additive — never gates): which surface produced the
        # deliverables_done verdict. "plan-wu-checkboxes" is the new machine
        # source of truth; the "phases-fallback …" / "phases-feature-level"
        # values mark the legacy / feature-level paths for the operator.
        "deliverables_source": deliverables_source,
        # Diagnostic (additive — never gates): the offending items for every
        # False check, keyed by check name. Empty dict when ok is True.
        "failing_detail": failing_detail,
    }


def summarize_failing_detail(result: dict) -> str:
    """Compact one-line summary of a ``verify_ledger`` refusal's
    ``failing_detail``, for the ``gate-refusal`` telemetry event
    (completion-gate-refusal-opacity Fix Scope §3 — lets incident mining
    distinguish "dirty tree: 1 stray log file" from "dirty tree: 14
    uncommitted source files" without transcript access). Returns ``""``
    when ``result["ok"]`` is True or ``failing_detail`` has no entry for
    ``result["failing_check"]``. Never raises — a malformed/legacy payload
    (missing keys) degrades to ``""``, never a telemetry-path exception.
    """
    check = result.get("failing_check")
    detail = (result.get("failing_detail") or {}).get(check) if check else None
    if not check or not isinstance(detail, dict):
        return ""
    try:
        if check == "clean_tree":
            total = detail.get("total_count", 0)
            files = detail.get("dirty_files") or []
            head = f" (first: {files[0]})" if files else ""
            return f"dirty tree: {total} file(s){head}"
        if check == "head_matches_origin":
            if detail.get("no_upstream"):
                return "no upstream configured"
            ahead, behind = detail.get("ahead"), detail.get("behind")
            if ahead is not None and behind is not None:
                return f"{ahead} ahead / {behind} behind upstream"
            return "HEAD does not match upstream"
        if check == "plan_complete":
            if "incomplete_plans" in detail:
                total = detail.get("total_count", 0)
                plans = detail.get("incomplete_plans") or []
                head = f" (first: {plans[0]['file']} — {plans[0]['status']})" if plans else ""
                return f"{total} incomplete plan(s){head}"
            return (
                f"plan {detail.get('plan_file')} not Complete "
                f"(status: {detail.get('plan_status')})"
            )
        if check == "deliverables_done":
            total = detail.get("total", 0)
            rows = detail.get("rows") or []
            if rows:
                head = f" (first: {rows[0]['text']})"
            elif detail.get("note"):
                head = f" ({detail['note']})"
            else:
                head = ""
            return f"{total} unchecked row(s){head}"
    except (KeyError, IndexError, TypeError):
        return ""
    return ""


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
                        f"{_VERIFICATION_ONLY_MARKER} marker) and "
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
# Phase 8 WU-2: script-assembled cycle dispatch prompt (emit_cycle_prompt)
# ---------------------------------------------------------------------------
#
# Moves the LAST unscripted deterministic orchestrator mechanic — re-typing the
# ~2K-token cycle dispatch prompt every dispatch — into the state scripts. The
# emitter parses the sectioned, parameterized `cycle-base-prompt.md`, selects
# the sections that apply to this (pipeline, mode, sub_skill) cycle, binds the
# 14 tokens, optionally appends the loop block, and returns the finished prompt
# + the model to dispatch it under. See the template file's header comment for
# the authoritative marker grammar / selection semantics / token inventory.

# Default cycle-prompt template directory, resolved through this module's own
# path. lazy_core.py lives at <claude-config>/user/scripts/lazy_core.py, so
# parent.parent is <claude-config>/user, and the templates live under
# skills/_components/lazy-batch-prompts/. The PHASES "Validated Assumptions"
# table confirms this resolves correctly through the ~/.claude symlink chain.
_CYCLE_TEMPLATE_DIRNAME = ("skills", "_components", "lazy-batch-prompts")

# The marker line shape the emitter parses, e.g.:
#   <!-- @section task pipelines=feature,bug modes=workstation skills=all -->
# with an optional `variant=runtime-up|no-runtime` token before the closing
# `-->`. Attributes are matched by key=value tokens (order-tolerant), so the
# variant attribute's position in the file is not load-bearing.
_SECTION_MARKER_RE = re.compile(r"^<!--\s*@section\s+(?P<rest>.*?)\s*-->\s*$")

# Residue regex: any `{lower_snake_or_digit}` token surviving the bind is an
# unbound token the emitter REFUSES on (never emits a half-bound prompt).
# Widened to include digits so tokens like {item_id} and {item_id2} are caught —
# previously `\{[a-z_]+\}` allowed digit-bearing tokens to pass through silently.
_PROMPT_RESIDUE_RE = re.compile(r"\{[a-z0-9_]+\}")


def _default_cycle_template_dir() -> Path:
    """Resolve the default cycle-prompt template dir from this module's path."""
    return Path(__file__).resolve().parent.parent.joinpath(*_CYCLE_TEMPLATE_DIRNAME)


def _standard_dispatch_bindings(pipeline: str) -> dict[str, str]:
    """Return the standard pipeline-token bindings shared by emit_cycle_prompt and
    emit_dispatch_prompt.

    These seven tokens appear across the dispatch templates and the cycle base
    template.  Factored out here so the two emitters stay byte-identical on the
    same input without code duplication.

    The last two tokens split the ``forbidden_status`` compound into its two
    distinct terminal statuses so a template can reference them separately
    (``dispatch-apply-resolution.md`` needs this: the receipt-EXEMPT terminal —
    ``Won't-fix``/``Superseded`` — is a legitimate operator-directed close that
    carries no receipt, whereas the receipt-GATED terminal — ``Fixed``/``Complete``
    — must never be set without a receipt).  ``forbidden_status`` itself is
    UNCHANGED (still the compound "Fixed or Won't-fix"/"Complete") because the
    other dispatch templates + the cycle base template use it as the blanket
    "set no terminal status" ban where that broad reading is correct.

    Args:
        pipeline: ``"feature"`` or ``"bug"``.

    Returns:
        A fresh dict with the standard pipeline tokens bound to their
        pipeline-appropriate values.
    """
    is_bug = pipeline == "bug"
    return {
        "item_label":            "Bug" if is_bug else "Feature",
        "pipeline_phrase":       "bug pipeline" if is_bug else "feature pipeline",
        "receipt_name":          "FIXED.md" if is_bug else "COMPLETED.md",
        "mark_pseudo":           "__mark_fixed__" if is_bug else "__mark_complete__",
        "forbidden_status":      "Fixed or Won't-fix" if is_bug else "Complete",
        # Split terminals (apply-resolution terminal-disposition contract):
        "receipt_gated_status":  "Fixed" if is_bug else "Complete",
        "receipt_exempt_status": "Won't-fix" if is_bug else "Superseded",
    }


def _dedup_residue(tokens: list[str]) -> list[str]:
    """Return ``tokens`` deduplicated while preserving first-seen order.

    Used by the residue guard in both emit_cycle_prompt and emit_dispatch_prompt
    to produce a stable, human-readable list of unbound {token} names.
    """
    seen: list[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.append(tok)
    return seen


def _emit_work_branch(repo_root: Path) -> str:
    """Resolve repo_root's current branch name for the {work_branch} token.

    Best-effort, mirroring _current_head's subprocess guard: any non-zero exit,
    empty output, or OS/subprocess error falls back to the literal string
    ``"the current branch"`` so the emitter never raises on a non-git root."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            branch = r.stdout.strip()
            if branch:
                return branch
    except (OSError, subprocess.SubprocessError):
        pass
    return "the current branch"


def _parse_section_attrs(rest: str) -> dict[str, str]:
    """Parse the attribute tokens of a `@section` marker into a dict.

    `rest` is the text between `@section` and the closing `-->` (already
    stripped), e.g. ``task pipelines=feature,bug modes=workstation skills=all``.
    The first whitespace token is the section NAME (stored under the special
    key ``"name"``); every remaining ``key=value`` token is stored verbatim.
    Tokens without an ``=`` (other than the leading name) are ignored.
    """
    tokens = rest.split()
    if not tokens:
        return {}
    attrs: dict[str, str] = {"name": tokens[0]}
    for tok in tokens[1:]:
        if "=" in tok:
            key, _, value = tok.partition("=")
            attrs[key] = value
    return attrs


def _parse_cycle_template(text: str) -> list[dict[str, Any]]:
    """Split a cycle-base-prompt template into its `@section` blocks.

    Everything BEFORE the first marker line is template metadata and is dropped.
    Each returned dict has: ``attrs`` (the parsed marker attributes, incl.
    ``name``) and ``content`` (the section body with leading/trailing blank
    lines stripped). A section's content runs from the line AFTER its marker to
    the line BEFORE the next marker (or EOF).
    """
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    body: list[str] = []

    def _flush():
        if current is not None:
            # Strip leading/trailing blank lines from the accumulated body.
            content_lines = body[:]
            while content_lines and not content_lines[0].strip():
                content_lines.pop(0)
            while content_lines and not content_lines[-1].strip():
                content_lines.pop()
            current["content"] = "\n".join(content_lines)
            sections.append(current)

    for line in lines:
        m = _SECTION_MARKER_RE.match(line)
        if m:
            # New section starts — finish the previous one (if any).
            _flush()
            current = {"attrs": _parse_section_attrs(m.group("rest"))}
            body = []
        elif current is not None:
            # Accumulate content (lines before the first marker are metadata).
            body.append(line)
    _flush()
    return sections


def _csv_set(value: str | None) -> set[str]:
    """Split a comma-separated attribute value into a set of trimmed tokens."""
    if not value:
        return set()
    return {tok.strip() for tok in value.split(",") if tok.strip()}


def _read_mcp_runtime_decision(spec_path: str | None) -> tuple[str, str | None]:
    """Decide the mcp-test runtime variant + untestability reason from PHASES.md.

    Reads ``{spec_path}/PHASES.md`` and looks for a line starting
    ``**MCP runtime:**``:
      - contains ``not-required`` → ``("no-runtime", <reason>)`` where reason is
        the text after the first ``-`` / ``—`` dash on that line (or a fallback
        when no dash is present).
      - any other value, line absent, or file/dir absent → ``("runtime-up", None)``.

    Never raises: an unreadable file is treated as "line absent" → runtime-up.
    """
    fallback_reason = "the plan declares no MCP-reachable surface"
    if not spec_path:
        return ("runtime-up", None)
    phases = Path(spec_path) / "PHASES.md"
    try:
        text = phases.read_text(encoding="utf-8")
    except OSError:
        return ("runtime-up", None)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**MCP runtime:**"):
            # ANCHORED value-token test — mirror phases_mcp_runtime_not_required
            # (line ~449). Match ``not-required`` ONLY as the VALUE token right
            # after the marker (word-boundary terminated), NOT as a substring
            # anywhere on the line. Without the anchor, a ``**MCP runtime:**
            # required`` line whose REASON PROSE mentions "not-required" (e.g.
            # "... not eligible for not-required") is mis-classified as
            # no-runtime, deadlocking a required-runtime mcp-test cycle
            # (first-time-login, 2026-07).
            if re.match(r"(?i)\*\*MCP runtime:\*\*\s*not-required\b", stripped):
                # Reason = text after the first dash (ASCII '-' or em-dash '—').
                reason = fallback_reason
                for dash in ("—", "-"):
                    idx = stripped.find(dash)
                    if idx != -1:
                        candidate = stripped[idx + len(dash):].strip()
                        if candidate:
                            reason = candidate
                        break
                return ("no-runtime", reason)
            # Line present but not the not-required value → runtime-up.
            return ("runtime-up", None)
    # No **MCP runtime:** line at all → runtime-up.
    return ("runtime-up", None)


def _mcp_test_cycle_model(spec_path: str | None) -> str:
    """Return the dispatch model (``"haiku"`` | ``"sonnet"``) for an mcp-test
    cycle, derived from the item's candidate scenarios via the script-derived
    tier signal (``surface_resolver.route_mcp_test_tier``).

    OPTION-(b) conservative escalation (docs/bugs/mcp-test-legacy-md-routes-to-haiku
    PHASES.md decision): enumerate the candidate scenarios under the resolved
    spec/bug dir — legacy ``mcp-tests/*.md`` + converted ``corpus/live/*.yaml``
    (recursively, so the canonical ``mcp-tests/corpus/live/`` nesting is covered)
    — and return ``"haiku"`` ONLY when at least one candidate resolves AND every
    candidate resolves to ``"haiku"`` via the tier router (ready converted YAML).
    Otherwise return ``"sonnet"``.

    Fail-safe: zero resolvable candidates, or any enumeration/resolution error,
    → ``"sonnet"`` (matches ``route_mcp_test_tier``'s own "unknown → Sonnet"
    bias). NEVER a silent haiku fallback — that is the exact defect this fixes.
    """
    # Lazy in-function import: surface_resolver is a sibling module in
    # user/scripts/. Import here (not at module top) to avoid any import-time
    # coupling/cycle and to keep the helper a no-op cost on non-mcp-test cycles.
    try:
        try:
            from surface_resolver import route_mcp_test_tier
        except ImportError:
            _here = Path(__file__).parent
            if str(_here) not in sys.path:
                sys.path.insert(0, str(_here))
            from surface_resolver import route_mcp_test_tier

        if not spec_path:
            return "sonnet"  # no item dir to resolve scenarios from.
        item_dir = Path(spec_path)
        if not item_dir.is_dir():
            return "sonnet"

        # Candidate scenarios: legacy .md + converted .yaml under mcp-tests/
        # (recursive — covers both a flat mcp-tests/*.md and the canonical
        # mcp-tests/corpus/live/*.yaml nesting).
        mcp_root = item_dir / "mcp-tests"
        candidates: list[Path] = []
        if mcp_root.is_dir():
            candidates.extend(sorted(mcp_root.rglob("*.md")))
            candidates.extend(sorted(mcp_root.rglob("*.yaml")))
            candidates.extend(sorted(mcp_root.rglob("*.yml")))

        if not candidates:
            return "sonnet"  # no scenario resolves → conservative escalation.

        # haiku only when EVERY candidate is a ready converted YAML (the router
        # returns "haiku"); a single legacy-.md (or any sonnet verdict) escalates.
        for scenario in candidates:
            if route_mcp_test_tier(scenario) != "haiku":
                return "sonnet"
        return "haiku"
    except Exception:
        # Any unexpected failure fails safe toward the capable tier.
        return "sonnet"


def emit_cycle_prompt(
    repo_root: Path,
    state: dict,
    *,
    pipeline: str,
    cloud: bool = False,
    repeat_count: int | None = None,
    template_dir: Path | None = None,
    park_mode: bool = False,
) -> dict | None:
    """Assemble the cycle dispatch prompt for one orchestrator cycle.

    The state scripts call this under ``--emit-prompt`` so the orchestrator
    never re-types the boilerplate prompt (the 2026-06-10 audit found this was
    ~70% of the orchestrator's output tokens). The emitter is the single
    assembler: it parses the sectioned ``cycle-base-prompt.md``, selects the
    sections matching this cycle, binds the tokens, optionally appends the loop
    block, and returns the finished prompt + dispatch model.

    Args:
        repo_root: the project root (used for {cwd} and {work_branch}).
        state: the dict ``compute_state`` produced. Consumed keys:
            ``feature_id``, ``feature_name``, ``spec_path``, ``current_step``,
            ``sub_skill``, ``sub_skill_args`` (bug-state reuses the feature_*
            keys for bugs).
        pipeline: ``"feature"`` or ``"bug"`` — selects per-pipeline sections and
            the bug/feature token bindings.
        cloud: when True the mode is ``"cloud"``, else ``"workstation"``.
        repeat_count: the consecutive-identical-probe count; when ``>= 2`` the
            loop block is appended and the dispatch model flips to ``"sonnet"``.
        template_dir: override the template directory (for tests). Defaults to
            the resolved ``skills/_components/lazy-batch-prompts/`` dir.
        park_mode: True when the emitting probe ran under ``--park-needs-input``
            (park-provisional-acceptance, SPEC D13). Selects sections whose
            ``park=park`` attribute marks them park-only (e.g. the stub-spec
            sentinel-mediation contract). Sections without a ``park=``
            attribute — every pre-existing section — are selected exactly as
            before, so non-park emission is byte-identical.

    Returns:
        ``None`` when the probe is not a dispatchable real-skill cycle —
        ``sub_skill`` is falsy, ``sub_skill`` starts with ``"__"`` (a pseudo-skill
        the orchestrator applies via ``--apply-pseudo``, not a dispatched skill),
        or ``feature_id`` is falsy (a terminal / idle probe). This keeps the
        orchestrator's single probe call uniform — the field is always present.

        Otherwise a dict: ``{"ok": True, "prompt": <str>, "model": "opus"|"sonnet"}``
        on success, or ``{"ok": False, "refused": <reason>}`` when binding leaves
        an unbound ``{token}`` (the emitter never emits a half-bound prompt). The
        function never raises on bad template content — it refuses instead.
    """
    sub_skill = state.get("sub_skill")
    # Not a dispatchable real-skill cycle → None (uniform "no prompt" signal).
    if not sub_skill or sub_skill.startswith("__"):
        return None
    if not state.get("feature_id"):
        return None

    if template_dir is None:
        template_dir = _default_cycle_template_dir()

    mode = "cloud" if cloud else "workstation"
    # Normalize the sub_skill for skills-csv matching: strip a leading "/".
    norm_skill = sub_skill[1:] if sub_skill.startswith("/") else sub_skill

    # --- Read + parse the base template (refuse, never raise, on bad input) ---
    base_path = template_dir / "cycle-base-prompt.md"
    try:
        base_text = base_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "refused": f"cannot read cycle-base-prompt.md: {exc}"}

    sections = _parse_cycle_template(base_text)

    # --- mcp-test runtime variant decision (only consulted for mcp-test) ------
    runtime_variant, untestability_reason = _read_mcp_runtime_decision(
        state.get("spec_path")
    )

    # --- Select the sections that apply to this cycle -------------------------
    selected: list[str] = []
    for sec in sections:
        attrs = sec["attrs"]
        pipelines = _csv_set(attrs.get("pipelines"))
        modes = _csv_set(attrs.get("modes"))
        skills = attrs.get("skills", "")
        if pipeline not in pipelines:
            continue
        if mode not in modes:
            continue
        # skills=all OR the normalized sub_skill is in the csv.
        if skills != "all" and norm_skill not in _csv_set(skills):
            continue
        # variant= sections are mcp-test-only and additionally filtered by the
        # runtime decision (the emitter picks EXACTLY ONE variant).
        variant = attrs.get("variant")
        if variant is not None:
            if norm_skill != "mcp-test" or variant != runtime_variant:
                continue
        # park= filter (park-provisional-acceptance, SPEC D13): `park=park`
        # sections are selected ONLY under a park-mode probe; absent attribute
        # (or `park=both`) keeps the pre-existing always-selected behavior.
        if attrs.get("park") == "park" and not park_mode:
            continue
        if sec["content"]:
            selected.append(sec["content"])

    # --- Repo prompt addenda (Phase 10 WU-3) ----------------------------------
    # After the base sections (and BEFORE the loop block), append any matching
    # sections from the OPTIONAL repo addenda file. The addenda path is keyed off
    # repo_root (NOT template_dir): it is the established per-repo config surface
    # (.claude/skill-config/). Parsing + selection reuse the SAME helpers as the
    # base template (no duplicated grammar), and the appended content is bound +
    # residue-guarded by the SAME map below — so a bad addenda section refuses the
    # WHOLE emission exactly like a bad base section. Absent file (or a file with
    # no matching sections) → no change, byte-identical to base-only behavior.
    # Orchestrators must NEVER hand-append to cycle_prompt; repo-specific gates
    # live here (a live orchestrator hand-spliced the AlgoBooth audio-INVARIANTS
    # gate onto the emitted prompt on 2026-06-11 — that path is now closed).
    addenda_path = repo_root / ".claude" / "skill-config" / "cycle-prompt-addenda.md"
    # Track addenda-contributed content separately so the residue guard can name
    # the addenda file when an unbound token came from a (mis-authored) addenda
    # section rather than the base template.
    addenda_selected: list[str] = []
    try:
        addenda_text = addenda_path.read_text(encoding="utf-8")
    except OSError:
        # Absent / unreadable → no addenda (the common, byte-identical path).
        addenda_text = None
    if addenda_text is not None:
        for sec in _parse_cycle_template(addenda_text):
            attrs = sec["attrs"]
            if pipeline not in _csv_set(attrs.get("pipelines")):
                continue
            if mode not in _csv_set(attrs.get("modes")):
                continue
            skills = attrs.get("skills", "")
            if skills != "all" and norm_skill not in _csv_set(skills):
                continue
            # Addenda sections may carry a variant= attribute too (same mcp-test
            # one-variant rule), kept for parity with the base selection logic.
            variant = attrs.get("variant")
            if variant is not None:
                if norm_skill != "mcp-test" or variant != runtime_variant:
                    continue
            # park= filter — same rule as the base selection (SPEC D13).
            if attrs.get("park") == "park" and not park_mode:
                continue
            if sec["content"]:
                addenda_selected.append(sec["content"])
    # Appended AFTER base sections — order: base → addenda → (loop block below).
    selected.extend(addenda_selected)

    # --- Token bindings (per-pipeline + per-state) ----------------------------
    # Standard pipeline tokens come from the shared helper; cycle-specific tokens
    # are layered on top (context wins on collision, same as emit_dispatch_prompt).
    bindings = _standard_dispatch_bindings(pipeline)
    bindings.update({
        "item_name": state.get("feature_name") or "",
        "item_id": state.get("feature_id") or "",
        "cwd": str(repo_root),
        "current_step": state.get("current_step") or "",
        "sub_skill": sub_skill,
        # sub_skill_args binds to "" when None so the prompt never shows "None".
        "sub_skill_args": state.get("sub_skill_args") or "",
        "spec_path": state.get("spec_path") or "",
        "work_branch": _emit_work_branch(repo_root),
        # untestability_reason is only present in the no-runtime mcp-test section;
        # bind it whenever a reason was derived (fallback applies otherwise).
        "untestability_reason": untestability_reason
        or "the plan declares no MCP-reachable surface",
    })

    prompt = "\n\n".join(selected)

    # --- Per-part complexity model tiering (Phase 9 — lazy-validation-readiness)
    # The /execute-plan cycle's dispatch model is selected from the CURRENT plan
    # part's `complexity:` frontmatter tag:
    #     mechanical → sonnet ; complex / absent / untagged → opus.
    # The plan part is `state["sub_skill_args"]` (the plan path) when the cycle
    # is an /execute-plan dispatch — the ONLY cycle this tiering applies to (a
    # /retro, /spec, /mcp-test, etc. cycle is unaffected and stays opus). Gated
    # strictly on the explicit tag /write-plan emitted: `plan_complexity` returns
    # the SAFE `complex`/opus default for any uncertain case, so the model never
    # auto-guesses cheaper. This baseline composes with the loop-block downgrade
    # below WITH A COMPLEXITY FLOOR (checkpoint-resume-false-loop-flips-complex-part-
    # to-sonnet, 2026-07-12): a `mechanical`/sonnet part stays sonnet, but a
    # `complex`/opus (or untagged-default-complex) /execute-plan part that loops
    # does NOT flip to sonnet — the cycle prompt HARD-refuses complex work under a
    # sonnet dispatch (`BLOCKED model-tier-mismatch`, cycle-base-prompt.md:260,287),
    # so a loop-flip to sonnet cannot advance the part and only climbs the stall
    # streak toward a halt. Such a cycle is `complexity_pinned_opus` and the loop
    # block below leaves it on opus.
    norm_sub_skill = norm_skill  # already leading-"/"-stripped above
    # Per-sub_skill base model tier.
    #
    # mcp-test is TIER-ROUTED at emit time via surface_resolver.route_mcp_test_tier
    # (docs/bugs/mcp-test-legacy-md-routes-to-haiku). The dispatch model is bound
    # by the orchestrator BEFORE the cycle subagent resolves which scenario it
    # runs, so a literal haiku here lands an UNCONVERTED legacy `.md` scenario on
    # haiku — which cannot author the `.md`→v1-YAML conversion and writes
    # BLOCKED.md. The fix consults the same script-derived tier signal the
    # interactive mcp-test SKILL.md uses (harness-hardening-retro-fixes Phase 4),
    # using OPTION-(b) CONSERVATIVE ESCALATION (per the bug's PHASES.md decision):
    # enumerate the item's candidate scenarios under the resolved spec/bug dir
    # (legacy `mcp-tests/*.md` + converted `corpus/live/*.yaml`); stay haiku ONLY
    # when at least one candidate resolves AND EVERY candidate is a ready
    # converted YAML (route_mcp_test_tier → "haiku"); otherwise escalate to
    # sonnet. Fail-safe: zero resolvable candidates OR an enumeration error →
    # sonnet (matches the router's own "unknown → Sonnet" bias) — NEVER a silent
    # haiku fallback. Every other sub_skill keeps the conservative opus base.
    #
    # The loop-block downgrade below sets model = "sonnet" UNCONDITIONALLY — from
    # a haiku/opus base that is the correct ESCALATION/downgrade toward sonnet; it
    # composes with this tier routing (both only ever move toward sonnet, never
    # away). Opus-on-failure for mcp-test is handled separately by the
    # needs-runtime-redispatch recovery path (dispatch_model "opus", tagged
    # "(opus, recovery)"), not here.
    if norm_sub_skill == "mcp-test":
        model = _mcp_test_cycle_model(state.get("spec_path"))
    else:
        model = "opus"
    # complexity_pinned_opus: True when this is an /execute-plan cycle whose plan
    # part's declared complexity is NOT mechanical (i.e. `complex`, or the SAFE
    # untagged/unknown default). Such a cycle is HARD-refused on sonnet by the
    # subagent, so the loop-block downgrade below must NOT drop it to sonnet.
    complexity_pinned_opus = False
    if norm_sub_skill in ("execute-plan", "execute_plan"):
        plan_arg = state.get("sub_skill_args")
        plan_token = ""
        if plan_arg:
            # sub_skill_args may carry trailing flags (e.g. "<plan> --batch");
            # the plan path is the first whitespace-delimited token.
            parts = str(plan_arg).split()
            plan_token = parts[0] if parts else ""
        # plan_complexity defaults to the SAFE `complex` for any uncertain case
        # (no arg, unreadable, untagged) — so an /execute-plan cycle is pinned to
        # opus unless the part is EXPLICITLY `mechanical`. This matches the
        # subagent's model-tier-mismatch refusal condition exactly.
        part_complexity = (
            plan_complexity(Path(plan_token)) if plan_token else _DEFAULT_PLAN_COMPLEXITY
        )
        if part_complexity == "mechanical":
            model = "sonnet"
        else:
            complexity_pinned_opus = True

    # --- Loop block: appended when the same signature repeated (>= 2) ---------
    # The loop block lives in loop-block.md inside a ``` fence; strip the fence
    # lines and bind its tokens. The loop-flip downgrades to sonnet to break a
    # stall cheaply — BUT never below a complexity-pinned-opus /execute-plan part
    # (a complex part on sonnet is refused as model-tier-mismatch, so the flip
    # would only climb the stall streak). Such cycles keep opus AND still get the
    # loop block appended (the loop guidance is model-independent).
    if repeat_count is not None and repeat_count >= 2:
        loop_path = template_dir / "loop-block.md"
        try:
            loop_text = loop_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "refused": f"cannot read loop-block.md: {exc}"}
        loop_inner = _strip_loop_fence(loop_text)
        if loop_inner:
            prompt = prompt + "\n\n" + loop_inner if prompt else loop_inner
            if not complexity_pinned_opus:
                model = "sonnet"

    # --- Bind all tokens (all occurrences, all sections + loop block) ---------
    for token, value in bindings.items():
        prompt = prompt.replace("{" + token + "}", value)

    # --- Residue guard: any surviving {token} → refuse (never half-bound) -----
    residue = _PROMPT_RESIDUE_RE.findall(prompt)
    if residue:
        seen = _dedup_residue(residue)
        # Attribute the residue to the addenda file when an unbound token traces
        # back to a (mis-authored) addenda section — so the operator knows which
        # file to fix. We bind the addenda blob in isolation and check whether
        # any of the surviving tokens originated there.
        suffix = ""
        if addenda_selected:
            addenda_blob = "\n\n".join(addenda_selected)
            for token, value in bindings.items():
                addenda_blob = addenda_blob.replace("{" + token + "}", value)
            addenda_residue = set(_PROMPT_RESIDUE_RE.findall(addenda_blob))
            if addenda_residue & set(seen):
                suffix = (
                    " (from .claude/skill-config/cycle-prompt-addenda.md — fix or "
                    "remove the offending addenda section)"
                )
        return {"ok": False, "refused": "unbound tokens: " + ", ".join(seen) + suffix}

    return {"ok": True, "prompt": prompt, "model": model}


def _strip_loop_fence(loop_text: str) -> str:
    """Extract the inner text of loop-block.md, dropping its ``` code fence.

    loop-block.md wraps its emittable body in a single ```-fenced block (after a
    metadata header comment). This returns the content BETWEEN the opening and
    closing fence lines, with leading/trailing blank lines stripped. When no
    fence is found (defensive), the whole text minus blank edges is returned.
    """
    lines = loop_text.splitlines()
    fence_idxs = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    if len(fence_idxs) >= 2:
        inner = lines[fence_idxs[0] + 1: fence_idxs[1]]
    else:
        inner = lines
    while inner and not inner[0].strip():
        inner.pop(0)
    while inner and not inner[-1].strip():
        inner.pop()
    return "\n".join(inner)


# ---------------------------------------------------------------------------
# Phase 3 — emit_dispatch_prompt: every remaining dispatch class becomes
#            script-emitted.  Reuses the same template grammar and binding/
#            residue machinery as emit_cycle_prompt — no reimplementation.
#
# Six classes (Phase 3); 'hardening' is deferred to Phase 4.
# Model assignments derive from the SOURCE COMPONENTS (not the SPEC.md, which
# pins no per-class models):
#   apply-resolution → opus  (blocked-resolution.md dispatches its apply subagent
#                             as Opus: judgment work — enacting Add-a-phase,
#                             Defer, or custom operator directives)
#   recovery / coherence-recovery → sonnet (bounded mechanical reconciliation)
#   input-audit / investigation / needs-runtime-redispatch → opus (judgment)
# ---------------------------------------------------------------------------

# The ordered tuple of dispatch classes.  Phase 3 added the first 6; Phase 4
# appends 'hardening' as the 7th entry (the harness-hardening stage class).
DISPATCH_CLASSES: tuple[str, ...] = (
    "apply-resolution",
    "input-audit",
    "investigation",
    "recovery",
    "coherence-recovery",
    "needs-runtime-redispatch",
    "corrective-coverage",  # harden Round 44 — Gate-1 MCP-coverage authoring cycle
    "ingest-research",      # harden Round 44 — pre-loop / in-session staged-research ingest
    "hardening",          # Phase 4 — harness-hardening stage (always Opus)
)

# Model to use when dispatching each class.  'opus' for judgment work;
# 'sonnet' for bounded mechanical work.  Source: the dispatch SOURCE COMPONENTS
# (blocked-resolution.md, decision-resume.md, investigation-dispatch.md, etc.).
DISPATCH_MODELS: dict[str, str] = {
    "apply-resolution":        "opus",    # blocked-resolution.md: Opus apply subagent
    "input-audit":             "opus",
    "investigation":           "opus",
    "recovery":                "sonnet",
    "coherence-recovery":      "sonnet",
    "needs-runtime-redispatch": "opus",
    "corrective-coverage":     "opus",   # harden Round 44 — classify + author + run coverage = Opus
    "ingest-research":         "sonnet", # harden Round 44 — bounded mechanical ingest = Sonnet
    "hardening":               "opus",   # Phase 4 — root-cause + mechanical fixes = Opus
}

# Regex to extract @requires keys from the first non-empty line of a dispatch
# template, e.g.: <!-- @requires item_id,spec_path,sentinel_path -->
_DISPATCH_REQUIRES_RE = re.compile(r"^<!--\s*@requires\s+([a-z0-9_,]+)\s*-->")


def load_context_json(text: str) -> dict:
    """Parse a --context-file / --context-stdin JSON payload into a context dict.

    ISSUE 3 (d8-effect-chains live /lazy-batch run, 2026-06-14): a ~1500-char
    ``failure_summary`` with commas/colons/parens/newlines was unreliable as an
    inline ``--context KEY=VALUE`` flag (the shell — not the script — mangled it).
    The JSON channel sidesteps shell quoting entirely: the orchestrator writes the
    payload to a file (or pipes it) and the value may contain ANY characters.

    Validation is strict so a malformed payload becomes a STRUCTURED error in the
    --emit-dispatch handler rather than silently-empty context:
      - The decoded JSON MUST be an object (dict). A list/str/number → ValueError.
      - Every key MUST be a string. A non-string key → ValueError.
      - Values are coerced to str (None → "") to match the inline-flag contract
        (emit_dispatch_prompt stringifies all bindings anyway).

    Raises:
        ValueError: on invalid JSON, a non-object top level, or a non-string key.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"context payload is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(
            f"context payload must be a JSON object, got {type(obj).__name__}"
        )
    out: dict = {}
    for key, value in obj.items():
        if not isinstance(key, str):
            raise ValueError(f"context key must be a string, got {key!r}")
        out[key] = "" if value is None else str(value)
    return out

# Phase 7 WU-7.5a: per-class Step name for the meta cycle_header.  The header
# the orchestrator echoes is `### {Step} — {summary} [meta {m}]` (bare count, no
# cap — meta_cycles is uncapped as of 2026-06-14); this map
# pins {Step} per the PHASES.md Phase 7 interface contract so every meta dispatch
# carries a canonical heading (0/8 meta cycles carried one before this WU).
DISPATCH_STEP_NAMES: dict[str, str] = {
    "investigation":            "Investigate",
    "apply-resolution":         "Resolve",
    "recovery":                 "Recover",
    "coherence-recovery":       "Recover",
    "hardening":                "Harden",
    "input-audit":              "Audit",
    "needs-runtime-redispatch": "Validate",
}


def emit_dispatch_prompt(
    cls: str,
    context: dict,
    *,
    pipeline: str,
    cloud: bool = False,
    template_dir: "Path | None" = None,
) -> dict:
    """Assemble a fully-bound dispatch prompt for one of the Phase 3 dispatch
    classes.

    Unlike ``emit_cycle_prompt`` (which assembles cycle prompts from state-script
    probe output), this assembler is called with an *explicit* context dict that
    the orchestrator builds from probe output + sentinel paths.  The matched
    template lives at ``dispatch-<cls>.md`` inside the same
    ``lazy-batch-prompts/`` directory used by the cycle emitter.

    The template grammar is identical to ``cycle-base-prompt.md``:
      - First non-empty line MUST be ``<!-- @requires key1,key2,... -->``
        declaring the *class-specific* context keys this template needs.
      - Subsequent lines use ``<!-- @section name pipelines=... modes=... -->``
        markers and ``{lower_snake}`` token placeholders.

    Standard pipeline tokens are always bound (same set as emit_cycle_prompt):
      {item_label}, {pipeline_phrase}, {receipt_name}, {mark_pseudo},
      {forbidden_status}
    Context dict values are overlaid on top (context wins on collision).

    Refusal semantics (mirrors emit_cycle_prompt — never half-binds):
      - Missing @requires key in context → refused, names the first missing key.
      - Unbound {token} residue after binding → refused, names the residue.
      - Unknown cls → ValueError (not a refusal dict — caller error).

    Args:
        cls: dispatch class name.  Must be in DISPATCH_CLASSES or DISPATCH_MODELS
             (Phase 4 will add 'hardening' before that class's template exists).
        context: dict of class-specific token values supplied by the caller.
        pipeline: ``"feature"`` or ``"bug"`` — section filtering + standard tokens.
        cloud: ``True`` → mode ``"cloud"``; ``False`` → mode ``"workstation"``.
        template_dir: override the template directory (for tests and Phase 4).
                      Defaults to the same ``lazy-batch-prompts/`` dir used by
                      emit_cycle_prompt.

    Returns:
        On success: ``{"ok": True, "prompt": <str>, "model": <"opus"|"sonnet">}``;
          additionally ``"cycle_header"`` (Phase 7 WU-7.5a) when a run marker is
          present (marker-gated — omitted entirely with no marker so no-marker
          callers stay byte-identical).
        On refusal: ``{"ok": False, "refused": <reason_str>}``

    Raises:
        ValueError: when ``cls`` is not a known dispatch class.
    """
    # --- Unknown-class guard (caller error — must raise, not refuse) -----------
    # Combine DISPATCH_CLASSES + DISPATCH_MODELS keys so Phase 4 can extend
    # DISPATCH_MODELS before or after appending to DISPATCH_CLASSES without a gap.
    all_known = set(DISPATCH_CLASSES) | set(DISPATCH_MODELS.keys())
    if cls not in all_known:
        raise ValueError(
            f"emit_dispatch_prompt: unknown dispatch class {cls!r}. "
            f"Known classes: {sorted(all_known)}"
        )

    if template_dir is None:
        template_dir = _default_cycle_template_dir()

    mode = "cloud" if cloud else "workstation"

    # --- Read the dispatch template -------------------------------------------
    tpl_path = template_dir / f"dispatch-{cls}.md"
    try:
        tpl_text = tpl_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "refused": f"cannot read dispatch-{cls}.md: {exc}"}

    # --- Parse @requires from line 1 ------------------------------------------
    # The first non-empty line must declare the class-specific required keys.
    first_line = next((ln for ln in tpl_text.splitlines() if ln.strip()), "")
    m = _DISPATCH_REQUIRES_RE.match(first_line)
    if not m:
        return {
            "ok": False,
            "refused": (
                f"dispatch-{cls}.md: first non-empty line must be "
                f"'<!-- @requires key1,key2,... -->' (only [a-z0-9_,] chars); "
                f"got: {first_line!r}"
            ),
        }
    requires_keys = [k.strip() for k in m.group(1).split(",") if k.strip()]

    # --- Validate that all @requires keys are present in context ---------------
    for key in requires_keys:
        if key not in context:
            return {
                "ok": False,
                "refused": (
                    f"dispatch-{cls}.md requires context key {key!r} which is "
                    f"absent from the supplied context dict. "
                    f"All @requires keys: {requires_keys}"
                ),
            }

    # --- Parse sections (reuse the same machinery as emit_cycle_prompt) --------
    sections = _parse_cycle_template(tpl_text)

    # --- Section selection by pipeline + mode (no skills= filtering needed) ---
    selected: list[str] = []
    for sec in sections:
        attrs = sec["attrs"]
        pipelines = _csv_set(attrs.get("pipelines"))
        modes = _csv_set(attrs.get("modes"))
        if pipeline not in pipelines:
            continue
        if mode not in modes:
            continue
        if sec["content"]:
            selected.append(sec["content"])

    prompt = "\n\n".join(selected)

    # --- Build the binding map -------------------------------------------------
    # Standard pipeline tokens come from the shared helper; context dict values
    # are overlaid on top (context wins on collision — the caller provides the
    # class-specific tokens; standard tokens above are the fallback defaults).
    bindings: dict[str, str] = _standard_dispatch_bindings(pipeline)
    for key, value in context.items():
        bindings[key] = str(value) if value is not None else ""

    # --- Bind all tokens -------------------------------------------------------
    for token, value in bindings.items():
        prompt = prompt.replace("{" + token + "}", value)

    # --- Residue guard: any surviving {lower_snake_or_digit} → refuse ----------
    residue = _PROMPT_RESIDUE_RE.findall(prompt)
    if residue:
        seen = _dedup_residue(residue)
        return {
            "ok": False,
            "refused": (
                f"dispatch-{cls}.md: unbound token(s) after binding: "
                + ", ".join(seen)
                + " — either add to @requires or remove from the template"
            ),
        }

    # --- Return assembled prompt + model assignment ----------------------------
    model = DISPATCH_MODELS.get(cls, "opus")
    result: dict = {"ok": True, "prompt": prompt, "model": model}

    # --- Meta cycle_header (Phase 7 WU-7.5a — MARKER-GATED) --------------------
    # When a run marker is present, attach a canonical cycle heading the
    # orchestrator echoes verbatim:  ### {Step} — {summary} [meta {m}]
    #   Step    : from DISPATCH_STEP_NAMES (per the Phase 7 interface contract).
    #   summary : the work summary — context item_name, fallback item_id, fallback
    #             the class name.
    #   m       : the marker's persisted meta counter + 1 — the cycle THIS dispatch
    #             will consume (1-based current-cycle semantics, matching the
    #             forward cycle_header's POST-advance convention noted in Phase 1).
    # COUNT ONLY — no "/cap" denominator: meta_cycles has NO ceiling (operator
    # decision 2026-06-14 — the meta loop is unbounded; only forward_cycles is
    # capped at max_cycles).
    # No marker → no cycle_header key at all, so no-marker emissions remain
    # byte-identical to the Phase 3/4 shape.
    marker = read_run_marker()
    if marker is not None:
        step = DISPATCH_STEP_NAMES.get(cls, cls)
        summary = (
            context.get("item_name")
            or context.get("item_id")
            or cls
        )
        meta_now = marker.get("meta_cycles", 0) or 0
        m = meta_now + 1
        result["cycle_header"] = f"### {step} — {summary} [meta {m}]"

    return result


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

# Marker filename inside the state dir.
_MARKER_FILENAME = "lazy-run-marker.json"

# Registry filename inside the state dir.
_REGISTRY_FILENAME = "lazy-prompt-registry.json"

# Phase 7 WU-7.1: deny-ledger filename (one JSON object per line; JSONL).
# The guard appends one entry on EVERY deny; --emit-dispatch hardening acks the
# oldest unacked entry (FIFO); --run-end refuses on unacked entries unless
# --ack-unhardened is passed.
_DENY_LEDGER_FILENAME = "lazy-deny-ledger.jsonl"

# Phase 7 WU-7.4: run-checkpoint filename (single JSON object).  Written by
# --run-end --reason checkpoint; consumed (echoed + deleted) by the next
# --run-start.  Consume-once resume context across a sanctioned pause.
_CHECKPOINT_FILENAME = "lazy-run-checkpoint.json"

# incident-auto-capture Phase 1 (D2): hook-events filename (JSONL, append-only).
# Countable history of hook deny/error events — the single overwritten
# hook-error.json breadcrumb stays byte-identical (it remains the at-a-glance
# "is a hook broken" file); this file is what makes recurrence observable for
# incident-scan.py.
_HOOK_EVENTS_FILENAME = "hook-events.jsonl"

# Phase 7: max characters retained for the ledger's reason_head / prompt_head
# summary fields (keeps the JSONL line bounded regardless of prompt size).
_LEDGER_HEAD_CHARS: int = 200

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

# The active repo root for this process.  None = fall back to the cwd's git
# toplevel (set_active_repo_root is the precise binding done at main()).
_active_repo_root: str | None = None

# One-shot guard so the legacy-base-dir migration runs at most once per process.
_legacy_state_migrated: bool = False

# Run-scoped state filenames that live directly under the state dir and must
# migrate together from the legacy (un-keyed) base dir into the keyed subdir.
_LEGACY_STATE_FILENAMES: tuple[str, ...] = (
    "lazy-run-marker.json",
    "lazy-prompt-registry.json",
    "lazy-deny-ledger.jsonl",
    "lazy-cycle-active.json",
    "lazy-run-checkpoint.json",
)


def set_active_repo_root(repo_root: str | None) -> None:
    """Bind the active repo root for this process (called once at main()).

    Passing a falsy value clears the binding, reverting active_repo_root() to
    the cwd-git-toplevel fallback.  Idempotent within a process.
    """
    global _active_repo_root
    _active_repo_root = str(repo_root) if repo_root else None


def active_repo_root() -> str:
    """Return the active repo root: the explicit binding, else the cwd's git
    toplevel, else the cwd itself.  Always returns a non-empty string."""
    if _active_repo_root:
        return _active_repo_root
    try:
        cp = _git(Path.cwd(), "rev-parse", "--show-toplevel")
        top = (cp.stdout or "").strip()
        if cp.returncode == 0 and top:
            return top
    except Exception:  # noqa: BLE001
        pass
    return str(Path.cwd())


def repo_key(repo_root: str) -> str:
    """The ONE canonical per-repo state-dir key.  SHA-1 of the normalized real
    path (resolve symlinks → forward slashes → strip trailing slash → lowercase
    a Windows drive letter).  Single source of truth — the bash hooks never
    re-derive this; they call ``lazy-state.py --marker-present`` which routes
    through here.  Normalization-invariant: trailing-slash / separator /
    drive-case variants of the same path collapse to one key."""
    norm = os.path.realpath(str(repo_root)).replace("\\", "/").rstrip("/")
    if len(norm) >= 2 and norm[1] == ":":  # lowercase a Windows drive letter
        norm = norm[0].lower() + norm[1:]
    if not norm:  # realpath of an empty string can normalize to cwd; guard anyway
        norm = "/"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


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


def merged_priority(item_type: str, raw_item: dict) -> int:
    """Normalize a queue item's ordering field to a single numeric effective
    priority (lower = higher priority), bridging the two queues' divergent
    field names/scales.

    feature → ``tier`` (int); bug → ``severity`` (P0/P1/P2/Low → rank). A
    missing / unrecognized field yields ``MERGED_PRIORITY_DEFAULT`` (sorts
    last) rather than raising — a malformed queue entry must not crash the
    merged view.
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
        if isinstance(sev, str):
            return _MERGED_SEVERITY_RANK.get(sev.strip(), MERGED_PRIORITY_DEFAULT)
        return MERGED_PRIORITY_DEFAULT
    return MERGED_PRIORITY_DEFAULT


def merged_worklist(
    feature_items: list[dict],
    bug_items: list[dict],
    repo_root: str,
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
            (merged_priority("bug", raw), _MERGED_TYPE_ORDER["bug"], seq,
             {"item_id": item_id, "type": "bug", "repo_root": repo_root})
        )
        seq += 1
    for raw in feature_items:
        item_id = raw.get("id")
        if not item_id:
            continue
        annotated.append(
            (merged_priority("feature", raw), _MERGED_TYPE_ORDER["feature"], seq,
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
) -> dict | None:
    """Return the head of the merged work-list (``{item_id, type, repo_root}``)
    or ``None`` when both queues are empty. Thin head-of ``merged_worklist``."""
    worklist = merged_worklist(feature_items, bug_items, repo_root)
    return worklist[0] if worklist else None


# ===========================================================================
# unified-pipeline-orchestrator Phase 5 — first three subcommands
#
# Three retro-named deterministic dances promoted from skill prose to code:
#   1. ensure_runtime() — the Step-1d.0 runtime-ensure dance.
#   2. gate_coverage()  — the Gate-1 MCP-coverage audit (mcp-coverage-audit.md).
#   3. apply_pseudo __mark_complete__ enhancement (ROADMAP strike + resolved
#      spec_dir queue trim) — lives in the existing apply_pseudo above.
# ===========================================================================

# Default AlgoBooth runtime config. These specifics (TCP 3333 health endpoint,
# the dev:restart command, the native-source globs, and the MCP tool name we
# assert) are AlgoBooth-coupled — but lazy-state.py is the repo-AGNOSTIC harness
# script, so they are PARAMETERIZED here as a default dict, NOT hard-coded into
# the control flow. A different repo overrides via the `config` argument (or the
# orchestrator passes a repo-specific config). The SPEC's Locked Decision puts
# --ensure-runtime ON lazy-state.py; this default dict is the clean
# parameterization that keeps the AlgoBooth specifics out of the algorithm.
_ENSURE_RUNTIME_DEFAULT_CONFIG: dict[str, Any] = {
    "health_url": "http://localhost:3333/health",
    "restart_command": "npm run dev:restart",
    "mcp_tool_name": "",          # empty → mcp_tools_present check is skipped
    "native_globs": ["src-tauri", "crates"],
    # Runtime-ownership sentinel (long-build-and-runtime-ownership Phase 1, LD1).
    # The `.runtime.lock.json` filename and the runtime's TCP port are
    # PARAMETERIZED here, NOT hard-coded into the read/write flow — a different
    # repo overrides via the `config` argument, keeping the shared harness
    # function repo-agnostic (same discipline as the keys above).
    "lock_filename": ".runtime.lock.json",
    "port": 3333,
    # Sidecar-pipe (is_connected) readiness dimension
    # (env-transient-counts-against-validation-retry-budget Phase 1, Leg A).
    # A runtime can be HTTP-healthy (/health 200) while the MCP sidecar named
    # pipe is dead (a zombie node process holding it after a dev:restart). The
    # HTTP-only gate then dispatches an mcp-test cycle against an
    # MCP-functionally-dead runtime, and the env transient gets mislabeled
    # `mcp-validation`. When `assert_sidecar_connected` is truthy, the M4 Health
    # phase additionally asserts `get_sidecar_status.is_connected: true` and
    # routes a pipe-dead-but-HTTP-200 runtime through recovery → BLOCKED
    # (mcp-runtime-unready, escalation-immune) instead of a bare READY.
    # Default OFF → repo-agnostic (non-AlgoBooth repos are unaffected); AlgoBooth
    # opts in via its config override.
    "assert_sidecar_connected": False,
    "sidecar_status_url": "http://localhost:3333/tools/get_sidecar_status",
    # Two-port cold-compile discriminator
    # (ensure-runtime-recovery-starves-cold-compile, Phase 1). A cold `tauri dev`
    # boot brings the Vite dev server up on :1420 within seconds, while the Rust
    # backend's :3333 /health endpoint refuses connections until the (potentially
    # multi-minute) cold Rust compile finishes. Probing ONLY :3333 cannot tell a
    # still-compiling backend (be patient) from a genuinely-dead one (recover) —
    # so a :3333-down/:1420-up observation is "compiling", not "dead". These keys
    # parameterize the Vite-up signal exactly like the :3333 keys above; a repo
    # without a :1420 frontend simply omits them (or overrides) and the
    # discriminator degrades to today's :3333-only DEAD behavior (frontend_probe
    # binds to lambda: False — see ensure_runtime). Read via .get() everywhere so
    # a legacy config override lacking the keys never raises.
    "frontend_health_url": "http://localhost:1420",
    "frontend_port": 1420,
    # Pre-Vite boot-liveness signal
    # (ensure-runtime-starves-pre-vite-sidecar-build, Phase 1). The two-port
    # discriminator above can only tell a still-booting cold runtime from a dead
    # one by Vite (:1420) being up — but a cold `tauri dev` spends its first
    # ~1-2 min in `BeforeDevCommand` (`npm run sidecar:build && vite`) with BOTH
    # ports down while the spawned boot process is alive. During that pre-Vite
    # window `frontend_up` is False, so the discriminator returned `dead` and
    # kill-restarted a healthy cold boot into a false BLOCKED. When this key is
    # truthy, ensure_runtime binds a real boot-liveness source (the liveness of
    # the `restart()`-spawned boot process, read from the in-process `Popen`
    # handle the harness already owns — NOT a URL probe, so no `_default_*` URL
    # helper is needed) and a both-ports-down-but-live-boot observation
    # classifies `compiling` (patient-wait), not `dead`. Default ABSENT → the
    # boot-liveness branch is INERT (boot_alive binds `lambda: False`), so every
    # repo without the key degrades to today's `dead` behavior — read via .get()
    # everywhere so a legacy override lacking the key never raises (mirror the
    # `assert_sidecar_connected` / `frontend_health_url` back-compat pattern).
    #
    # ensure-runtime-starves-pre-vite-sidecar-build Phase 3 (CLI-seam wiring):
    # ENABLED in the base default. The signal is fail-safe BY CONSTRUCTION — the
    # boot-liveness source is the liveness of the `restart()`-spawned `Popen`
    # handle THIS harness owns in-process (see `ensure_runtime`). When no boot was
    # spawned this call (or the spawn failed), `boot_alive()` reports NOT-booting,
    # so a non-AlgoBooth repo with both ports down still classifies `dead` and
    # reaches bounded recovery — byte-identical to the inert default. The signal
    # can only flip a both-ports-down observation to the patient-wait `compiling`
    # when this harness genuinely has a live boot process running, which is
    # exactly the cold pre-Vite `BeforeDevCommand`/`sidecar:build` window the M4
    # classifier was starving. The only production caller
    # (`lazy-state.py --ensure-runtime`) passes NO config override, so flipping the
    # base default here is what wires the signal end-to-end — a per-repo override
    # may still set it `False` to opt OUT.
    "boot_liveness": True,
}


def _sidecar_is_connected(payload: dict | None) -> bool:
    """True iff the get_sidecar_status payload reports ``is_connected: true``.

    Strict: only a literal boolean ``True`` counts as connected — a missing
    field, a non-dict payload, or a truthy-but-non-bool value (e.g. the string
    ``"true"``) is treated as NOT connected (fail-safe toward recovery). Pure
    payload-parsing helper, never raises.
    """
    if not isinstance(payload, dict):
        return False
    return payload.get("is_connected") is True


def _default_sidecar_probe(sidecar_status_url: str) -> bool:
    """Real get_sidecar_status probe (stdlib urllib) → ``is_connected`` bool.

    Mirrors ``_default_runtime_probe``: best-effort + never raises (any error →
    False so the caller treats the sidecar as disconnected and enters recovery).
    Only invoked when ``ensure_runtime`` is called WITHOUT an injected
    ``sidecar_check`` AND the config asserts the sidecar (production); tests
    always inject a ``sidecar_check``.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(sidecar_status_url, timeout=5) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            payload = None
        return _sidecar_is_connected(payload)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _default_frontend_probe(frontend_health_url: str) -> bool:
    """Real Vite (:1420) reachability probe (stdlib urllib) → bool.

    The cold-compile discriminator's "frontend up" signal
    (ensure-runtime-recovery-starves-cold-compile, Phase 1). A cold `tauri dev`
    brings Vite up on :1420 within seconds; reachability there while :3333
    /health still refuses means the Rust backend is still COMPILING (be patient),
    not dead. Mirrors ``_default_sidecar_probe``: best-effort + never raises (any
    error — connection refused, timeout, DNS — → False, so the caller treats the
    frontend as down and the runtime as dead). Only invoked when ``ensure_runtime``
    is called WITHOUT an injected ``frontend_probe`` AND the config carries the
    frontend keys (production); tests always inject a ``frontend_probe``. Any 2xx
    OR a connection that completes the HTTP round-trip counts as up — Vite answers
    on :1420 regardless of the path, so a non-200 status still proves reachability.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(frontend_health_url, timeout=5):  # noqa: S310
            return True
    except urllib.error.HTTPError:
        # An HTTP error response (4xx/5xx) still means Vite is LISTENING and
        # answered — the frontend is up (compiling backend, not a dead host).
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _classify_compile_state(
    backend_code: int, frontend_up: bool, boot_alive: bool = False
) -> str:
    """Map a two-port (+ boot-liveness) observation to
    ``"serving" | "compiling" | "dead"`` (pure).

    The cold-compile discriminator (ensure-runtime-recovery-starves-cold-compile,
    Phase 1) EXTENDED for the pre-Vite window
    (ensure-runtime-starves-pre-vite-sidecar-build, Phase 1). No I/O — the caller
    supplies the already-probed backend /health code, the frontend-up boolean,
    and (optionally) the boot-process-liveness boolean:

      - ``backend_code == 200`` ⇒ ``"serving"`` (the backend answers — regardless
        of the frontend OR boot-liveness signal; a serving backend is ready by
        definition).
      - ``backend_code != 200`` AND ``frontend_up`` ⇒ ``"compiling"`` (Vite is up
        but the backend is not yet serving — the cold Rust compile is still
        running; be PATIENT, do NOT kill-restart). UNCHANGED by ``boot_alive``.
      - ``backend_code != 200`` AND NOT ``frontend_up`` AND ``boot_alive`` ⇒
        ``"compiling"`` (the NEW pre-Vite branch — both ports down, but the
        orchestrator-spawned boot process is still ALIVE, i.e. the multi-minute
        ``BeforeDevCommand``/``sidecar:build`` window before Vite binds :1420.
        This is a cold boot in progress, NOT a crash — patient-wait it on the
        SAME path as the Vite-up compiling case rather than kill-restarting it.
        Reuses the ``"compiling"`` label so no new state ripples through the
        routers — ensure-runtime-starves-pre-vite-sidecar-build Phase 1).
      - ``backend_code != 200`` AND NOT ``frontend_up`` AND NOT ``boot_alive`` ⇒
        ``"dead"`` (nothing is listening AND no live boot — never booted or truly
        crashed and not restarting; the bounded crash-recovery loop is correct
        here). UNCHANGED — ``boot_alive`` DEFAULTS to ``False`` so every existing
        positional caller is byte-identical to the prior three-branch table.
    """
    if backend_code == 200:
        return "serving"
    if frontend_up:
        return "compiling"
    if boot_alive:
        return "compiling"
    return "dead"


def _default_runtime_probe(health_url: str):
    """Real /health probe (stdlib urllib). Returns (http_code, payload_dict).

    Best-effort + never raises: any error → (0, None) so the caller treats the
    runtime as down. Only invoked when ``ensure_runtime`` is called WITHOUT an
    injected ``probe`` (production); tests always inject.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(health_url, timeout=5) as resp:  # noqa: S310
            code = resp.getcode() or 0
            body = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                payload = None
        except (ValueError, TypeError):
            payload = None
        return (code, payload)
    except (urllib.error.URLError, OSError, ValueError):
        return (0, None)


def _default_stale_check(repo_root, cfg: dict) -> bool:
    """Production default binding for ``ensure_runtime``'s ``stale_check`` seam —
    wires the previously-orphaned F7 freshness predicate
    (``stale_binary.native_source_newer_than``) so the STALE verdict is REACHABLE
    in production (``docs/bugs/stale-runtime-health-200-false-blocked``).

    Boot signal (D1 — reuses what already exists, no new state):
      1. ``read_boot_stamp(repo_root)`` — the persisted ``dev:restart`` spawn
         epoch (``.runtime.boot.json``), written by ``ensure_runtime``'s own
         default ``restart()`` closure.
      2. Fallback: the ``.runtime.lock.json`` recorded kernel ``start_time`` (the
         owning process's boot time) via ``read_runtime_lock`` — covers a
         runtime that booted before a boot stamp existed (legacy-booted /
         foreign-adopted lock) so a genuinely stale binary is still caught.
      3. No signal at all → **not stale** (fail-safe; D2 below).

    The native-source glob list is ``cfg["native_globs"]`` (per-repo
    configurable via ``_ENSURE_RUNTIME_DEFAULT_CONFIG`` / a repo's ``config``
    override — AlgoBooth: ``src-tauri``, ``crates``, plus sidecar-bundle globs
    the repo config adds), never hard-coded here.

    Fail-safe direction (D2, unchanged from ``stale_binary.py``'s own contract):
    ANY missing/unreadable boot signal, unparseable epoch, or predicate error
    reports **False** (not stale) — the health=200 gate stays the primary guard.
    A spurious False costs nothing further; a spurious True would force a
    gratuitous multi-minute rebuild every cycle. Never raises.

    Only invoked when ``ensure_runtime`` is called WITHOUT an injected
    ``stale_check`` (production); ``--test`` always injects one directly (a
    legitimate allow-listed seam — see test_lazy_core.py's production-binding
    discipline note, ``_PRODUCTION_BINDING_ALLOWED_KWARGS``).
    """
    boot_epoch = None
    try:
        boot_epoch = read_boot_stamp(repo_root)
    except Exception:  # noqa: BLE001 — fail-safe: fall through to the lock
        boot_epoch = None
    if boot_epoch is None:
        lock = None
        try:
            lock = read_runtime_lock(repo_root, config=cfg)
        except Exception:  # noqa: BLE001 — fail-safe: no fallback signal
            lock = None
        if isinstance(lock, dict):
            boot_epoch = lock.get("start_time")
    if boot_epoch is None:
        return False
    try:
        boot_iso = datetime.datetime.fromtimestamp(
            float(boot_epoch), tz=datetime.timezone.utc
        ).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return False
    globs = cfg.get("native_globs") or _ENSURE_RUNTIME_DEFAULT_CONFIG["native_globs"]
    try:
        return bool(
            stale_binary.native_source_newer_than(
                boot_iso, Path(repo_root), globs=list(globs)
            )
        )
    except Exception:  # noqa: BLE001 — native_source_newer_than never raises by
        # its own contract, but a defensive guard keeps this binding fail-safe
        # even against a future change to that contract.
        return False


def _mcp_tool_in_payload(payload: dict | None, tool_name: str) -> bool:
    """True iff ``tool_name`` appears in the health payload's tool listing.

    Tolerant of the two shapes a /health payload may carry the tool set in:
      - ``{"tools": ["a", "b"]}`` (list of names), or
      - ``{"tools": [{"name": "a"}, ...]}`` (list of dicts).
    Empty ``tool_name`` → vacuously True (no assertion configured).
    """
    if not tool_name:
        return True
    if not isinstance(payload, dict):
        return False
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return False
    for t in tools:
        if isinstance(t, str) and t == tool_name:
            return True
        if isinstance(t, dict) and t.get("name") == tool_name:
            return True
    return False


def _mcp_tools_present_honest(payload: dict | None, tool_name: str,
                             health_code: int) -> bool:
    """``mcp_tools_present`` that is NOT vacuously True for a non-serving runtime
    (ensure-runtime-legacy-mode-optimistic-ready-verdict, Phase 1 / SPEC Open
    Question 3).

    ``_mcp_tool_in_payload`` returns vacuously True for an empty ``tool_name`` (no
    assertion configured). That is correct for a SERVING runtime (health 200), but
    misleading for one that is not serving — it claimed ``mcp_tools_present: true``
    alongside ``health_code: 0``. Here: an empty ``tool_name`` paired with a
    non-200 ``health_code`` reports ``False`` (the runtime is demonstrably not
    serving its tools); a 200 health code with no configured tool name keeps the
    vacuous-True default; a configured tool name defers to ``_mcp_tool_in_payload``
    in every case (unchanged).
    """
    if not tool_name and int(health_code or 0) != 200:
        return False
    return _mcp_tool_in_payload(payload, tool_name)


# long-build-and-runtime-ownership Phase 2 (LD3) — the M4 liveness/recovery
# verdict state enum. A `.runtime.lock.json`-owned runtime evaluates through
# Identity → Staleness → Health into exactly one of these (BLOCKED is the
# recovery-exhausted terminal added in WU-2).
_RUNTIME_STATES = ("READY", "STALE", "HIJACKED", "DEAD", "BLOCKED")

# Legacy `status` ↔ M4 `state` mapping (LD2 — the verdict is a SUPERSET of the
# old {status,...} dict so part-5 migration is incremental). The pre-M4 flow
# only ever yielded a *good* runtime (booted/ready/stale-rebuilt all end at
# health=200), so each maps to a non-terminal verdict state.
_LEGACY_STATUS_TO_STATE = {
    "ready": "READY",
    "booted": "READY",
    "stale-rebuilt": "STALE",
}


# long-build-and-runtime-ownership Phase 2 (LD3) — the bounded-recovery cap. A
# STALE/DEAD runtime auto-recovers via restart() in an exponential-backoff loop
# capped at this many attempts; on exhaustion the verdict is BLOCKED. The cap is
# the loop-prevention guarantee that replaces the hand-rolled poll loops.
_RUNTIME_RECOVERY_MAX_ATTEMPTS = 5
# Exponential-backoff base seconds (1, 2, 4, 8, 16 …) — multiplied by the
# injected/real sleep so --test asserts the schedule without real sleeps.
_RUNTIME_RECOVERY_BACKOFF_BASE = 1.0

# Cold-compile patient-wait ceiling (ensure-runtime-recovery-starves-cold-compile,
# Phase 2). A runtime classified `compiling` (Vite :1420 up, backend :3333 not yet
# serving) is WAITED on — never kill-restarted — on a cold-compile-sized budget.
# REUSES the existing production restart()-awaiter's `90 × 5s` ≈ 7.5-min sizing
# (NOT the ≤5×backoff ~31s crash budget, which would starve a cold Rust compile —
# the root cause). Injected sleep keeps --test hermetic (no real 7.5-min wait).
_COLD_COMPILE_WAIT_MAX_POLLS = 90
_COLD_COMPILE_WAIT_INTERVAL = 5.0

# Boot-spawn grace window (ensure-runtime-recovery-starves-cold-compile-round-2 —
# the Windows-wrapper-exits-early refix). The pre-Vite boot-liveness signal cannot
# rely SOLELY on the `restart()`-spawned `Popen.poll()` being None, because on
# Windows the production `restart_command` (`npm run dev:restart` =
# `node scripts/kill-dev.js && cross-env … tauri dev`) spawns a SHORT-LIVED
# npm/cmd shell-chain WRAPPER whose handle `.poll()` returns an exit code within
# seconds — long before the detached `tauri dev` / `cargo build` child finishes
# the ~3.5-min cold compile. Reading only that wrapper handle misclassifies a
# genuinely-compiling cold boot as `dead` (the Round-32 false-green: its test
# fed a fake `Popen` whose `.poll()` stayed None, so it never exercised the
# wrapper-exits-early production reality). The robust signal is a TIME-WINDOW
# grace: when a boot was spawned within this many seconds, a both-ports-down
# observation is the cold-compile window in progress — patient-wait it. The
# window is sized to the cold-compile ceiling (`_COLD_COMPILE_WAIT_MAX_POLLS ×
# _COLD_COMPILE_WAIT_INTERVAL` ≈ 7.5 min) so a boot that is genuinely stuck past
# the patient-wait budget still ages out of the grace and reaches bounded
# recovery → BLOCKED (fail-safe: a dead host is never patient-waited forever).
_BOOT_SPAWN_GRACE_SECONDS = _COLD_COMPILE_WAIT_MAX_POLLS * _COLD_COMPILE_WAIT_INTERVAL


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phase 2
#   Active-invocation probe primitives (hermetic, injected).
#
# Each per-capability host check is an injected callable, modeled on
# ensure_runtime's probe/restart/stale_check contract (real defaults bound only
# when the callable is None). Binary capabilities use ACTIVE INVOCATION — run the
# tool and check its exit code — NEVER shutil.which()/os.path.exists(). That is
# load-bearing on this Windows host: a zero-byte `python3.exe`/`python.exe` App
# Execution Alias stub in \WindowsApps on $PATH resolves under which() but its
# invocation opens a GUI Microsoft Store prompt and silently HANGS the pipeline
# (research Area 2). Stale path caches are the same hazard class. The exit-code
# gate (and the short timeout in the real default) is what guards against it.
# ---------------------------------------------------------------------------

# The real-default binary-probe invocation timeout (seconds). A probe that hangs
# is the exact failure mode active invocation exists to prevent, so bound it.
_BINARY_PROBE_TIMEOUT_SECONDS = 5


def probe_binary_capability(argv, *, run=None) -> bool:
    """Return True iff invoking ``argv`` exits 0 — the active-invocation binary
    capability probe (host-capability-declaration Phase 2).

    Runs ``argv`` (e.g. ``[tool, "--version"]``) via the injected ``run``
    callable and returns ``exit code == 0``. NEVER consults the filesystem for
    presence (no ``shutil.which`` / ``os.path.exists``) — that is the
    \\WindowsApps App-Execution-Alias false-positive guard.

    The default ``run`` is a real ``subprocess.run`` with a short timeout,
    ``capture_output=True`` and ``shell=False``; ``--test`` injects a stub so no
    real binary is ever invoked. Any invocation error (timeout, OSError, a stub
    that raises) is swallowed and reported as ``False`` — an un-runnable tool is
    an absent capability, never a propagated exception that bricks the probe.

    Args:
        argv: the command + args to invoke (list of str).
        run: injectable invoker returning an object with a ``returncode`` attr
            (a ``subprocess.CompletedProcess``-shape). ``None`` ⇒ real default.

    Returns:
        ``True`` iff the invocation completed with exit code 0, else ``False``.
    """
    if run is None:
        def run(_argv, **_kwargs):  # noqa: ANN001 — real default
            return subprocess.run(
                _argv,
                capture_output=True,
                shell=False,
                timeout=_BINARY_PROBE_TIMEOUT_SECONDS,
            )
    try:
        completed = run(argv)
    except Exception:  # noqa: BLE001 — any invocation failure ⇒ absent
        return False
    return getattr(completed, "returncode", 1) == 0


def probe_env_capability(var_name, *, environ=None) -> bool:
    """Return True iff env var ``var_name`` is set to a non-falsy value — the
    env-var capability probe (host-capability-declaration Phase 2).

    Generalizes the ``$ALGOBOOTH_REAL_AUDIO_DEVICE`` device read. Truthy iff the
    var is present AND its stripped, lowercased value is NOT in the shared
    ``_FALSY_ENV_VALUES`` set (``""``/``0``/``false``/``no``/``off``) — so an
    inherited empty export does not register a capability as present.

    Args:
        var_name: the environment variable name.
        environ: injectable mapping (``--test`` passes a dict). ``None`` ⇒
            the real ``os.environ``.

    Returns:
        ``True`` iff set to a non-falsy value, else ``False``.
    """
    env = os.environ if environ is None else environ
    val = env.get(var_name)
    if val is None:
        return False
    return str(val).strip().lower() not in _FALSY_ENV_VALUES


# Predicate vocabulary for the "platform" probe kind (host-capability OS axis).
# A predicate name maps to a pure function of the host OS name (platform.system()
# returns "Windows"/"Linux"/"Darwin"). Closed set — an unknown predicate yields a
# constant-False probe (fail-safe absent, never a crash), mirroring the registry's
# missing-config fallback.
_PLATFORM_PREDICATES: dict[str, object] = {
    # The OS is anything OTHER than Windows (Linux or macOS). Backs the
    # non-windows-host capability: cfg(unix) code is un-runnable on Windows, so a
    # Windows host reports the capability ABSENT and defers (host-capability-
    # saturated) instead of looping a real-device re-open.
    "non-windows": (lambda system_name: system_name.strip().lower() != "windows"),
}


def probe_platform_capability(predicate, *, system_fn=platform.system) -> bool:
    """Return True iff the host OS satisfies ``predicate`` — the OS/platform
    capability probe (device-vs-host mis-classification, Round 41, 2026-06-29).

    The OS is DETERMINISTICALLY detectable (unlike a network peer), so this is a
    real probe, not a constant-False placeholder. ``predicate`` is a key into the
    closed ``_PLATFORM_PREDICATES`` map; each value is a pure function of the OS
    name string returned by ``system_fn`` ("Windows"/"Linux"/"Darwin"). An unknown
    predicate (or any evaluation error) reports ``False`` — an unrecognized OS
    constraint is an absent capability, never a propagated exception.

    Args:
        predicate: a key into ``_PLATFORM_PREDICATES`` (e.g. ``"non-windows"``).
        system_fn: injectable OS-name source (``--test`` / unit tests pass a stub
            returning ``"Windows"`` / ``"Linux"``). ``platform.system`` ⇒ the real
            host OS.

    Returns:
        ``True`` iff the host OS satisfies the named predicate, else ``False``.
    """
    fn = _PLATFORM_PREDICATES.get(predicate)
    if fn is None:
        return False
    try:
        return bool(fn(system_fn()))
    except Exception:  # noqa: BLE001 — any probe failure ⇒ absent
        return False


def ensure_runtime(
    repo_root: Path,
    *,
    config: dict | None = None,
    probe=None,
    restart=None,
    stale_check=None,
    read_lock=None,
    live_session_id=None,
    kernel_start_time_fn=None,
    sleep=None,
    write_lock=None,
    recover_identity=None,
    kill=None,
    sidecar_check=None,
    frontend_probe=None,
    boot_alive=None,
) -> dict:
    """Ensure the dev runtime + MCP server are up, CURRENT, **and verifiably
    owned**; return the M4 liveness/recovery verdict.

    REVERSE-REFERENCE (ensure-runtime-recovery-starves-cold-compile): the
    long-build-and-runtime-ownership LD3 bounded-recovery contract below was
    RE-SCOPED by ``docs/bugs/ensure-runtime-recovery-starves-cold-compile``. The
    ≤5×backoff ``_recover_runtime`` loop is now reserved for a genuinely *dead*
    runtime (both ports down — a real crash); a runtime still *compiling* (the
    cold Rust build: Vite :1420 up, backend :3333 not yet serving) is instead
    PATIENTLY WAITED on via ``_await_compile_serving`` (never kill-restarted),
    because restart-and-immediately-probe starved a multi-minute cold compile
    into 5 wasted kill-restarts → a false BLOCKED. See ``_ensure_runtime_m4`` /
    ``_classify_compile_state`` / ``_await_compile_serving``.

    REVERSE-REFERENCE (ensure-runtime-starves-pre-vite-sidecar-build): the
    cold-compile re-scope above covered only the *Vite-up* window (its sole
    "still booting" signal is Vite :1420 being up). The PRE-VITE window — the
    multi-minute ``BeforeDevCommand``/``sidecar:build`` phase where BOTH ports are
    still down while the spawned boot process is alive — was still misclassified
    ``dead`` and kill-restarted. ``docs/bugs/ensure-runtime-starves-pre-vite-
    sidecar-build`` (the pre-Vite sibling of ``ensure-runtime-recovery-starves-
    cold-compile``) adds a SECOND "still booting" signal, ``boot_alive`` (the
    liveness of the ``restart()``-spawned boot process), threaded here alongside
    ``frontend_probe``: a both-ports-down-but-live-boot observation now classifies
    ``compiling`` (patient-wait), not ``dead``. Default-off (``boot_liveness``
    config key absent / ``boot_alive → False``) is byte-identical to the prior
    behavior. See ``_classify_compile_state`` (3rd ``boot_alive`` arg),
    ``_route_legacy_non_serving`` / ``_route_non_serving``, and
    ``_await_compile_serving`` (the went-dead check is now an OR of both signals).

    long-build-and-runtime-ownership Phase 2 (LD2/LD3) reworks this IN PLACE
    into the idempotent M4 gatekeeper. The verdict is a **superset** of the
    legacy ``{status, mcp_tools_present, health_code}`` shape::

        {"state": "READY"|"STALE"|"HIJACKED"|"DEAD"|"BLOCKED",
         "ownership_verified": bool,
         "health_code": int,
         "mcp_tools_present": bool,
         "terminal_blocker": str | None,
         "status": "ready"|"booted"|"stale-rebuilt"}   # legacy, retained

    Two call modes (backward-compatible):

      - **M4 mode** (Identity engaged) — the caller injects a `live_session_id`
        (and/or `read_lock` / `kernel_start_time_fn`). ``ensure_runtime`` runs
        the three-phase evaluation:

          1. **Identity** — ``read_lock()`` parses ``.runtime.lock.json``;
             ``verify_runtime_ownership`` compares the recorded
             ``(start_time, controller_session_id)`` against the live kernel /
             session. A live PID whose ownership does NOT verify (divergent
             start_time / foreign session) while ``/health`` answers is a foreign
             port-holder ⇒ ``HIJACKED``. A missing/dead PID (kernel start_time
             ``None``) ⇒ ``DEAD``. No lock + ``/health`` answering ⇒ ``HIJACKED``
             (health=200 is NOT proof of ownership — LD1); no lock + nothing
             answering ⇒ ``DEAD``.
          2. **Staleness** — for an owned runtime, ``stale_check()`` True ⇒
             ``STALE`` (default binding: ``_default_stale_check`` — the boot
             stamp vs. native-source-commit freshness predicate; see below).
          3. **Health** — for an owned, current runtime, ``probe()`` 200 ⇒
             ``READY``; a refused ``/health`` despite a live owned PID ⇒
             ``DEAD``.

        (WU-1 CLASSIFIES; the bounded-recovery / BLOCKED / never-SIGKILL
        fail-safe land in WU-2 — STALE/DEAD here do NOT yet auto-recover.)

      - **Legacy mode** (no Identity callables) — the pre-M4 boot/stale/ready
        flow runs unchanged (DOWN→restart→booted; UP+stale→restart→stale-rebuilt;
        UP+current→ready). The returned dict is upgraded to the verdict superset
        (``state`` derived via ``_LEGACY_STATUS_TO_STATE``, ``ownership_verified:
        False``, ``terminal_blocker: None``) so a caller never sees a missing key.

    Determinism / injection (the parameters that make ``--test`` hermetic):
      - ``probe``               — callable() -> (http_code:int, payload:dict|None).
      - ``restart``             — callable() -> bool (truthy on success).
      - ``stale_check``         — callable() -> bool (True == stale binary).
      - ``read_lock``           — callable() -> lock dict | None (default: a
                                  best-effort ``read_runtime_lock`` over the
                                  config's ``lock_filename``).
      - ``live_session_id``     — the controller session id threaded into
                                  ``verify_runtime_ownership`` (None ⇒ legacy mode).
      - ``kernel_start_time_fn``— callable(pid, *, platform) -> float|None
                                  (default: the real ``kernel_start_time``).

    AlgoBooth specifics (port, restart command, globs, the asserted MCP tool,
    the lock filename) are read from ``config`` (default
    ``_ENSURE_RUNTIME_DEFAULT_CONFIG``) — NOT hard-coded into the control flow,
    keeping this shared-harness function repo-agnostic.
    """
    cfg = dict(_ENSURE_RUNTIME_DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    health_url = cfg["health_url"]
    tool_name = cfg.get("mcp_tool_name", "")

    if probe is None:
        probe = lambda: _default_runtime_probe(health_url)
    # Pre-Vite boot-liveness holder (ensure-runtime-starves-pre-vite-sidecar-build
    # Phase 3 — production-seam wiring). The default `restart()` closure below
    # spawns the `dev:restart` boot process and STASHES the resulting `Popen`
    # handle here; the default `boot_alive()` (bound further down when
    # `boot_liveness` is configured) reads it back via `.poll()` — None ⇒ the boot
    # process is still running ⇒ the cold pre-Vite `BeforeDevCommand`/`sidecar:build`
    # window is in progress, NOT a dead host. A plain dict (not `nonlocal`) is the
    # closure-shared holder so BOTH the `restart` and `boot_alive` closures mutate /
    # read the SAME live handle without rebinding. When `restart` is INJECTED (every
    # `--test` path), this holder stays empty, so the default `boot_alive` reports
    # NOT-booting (fail-safe) — and an injected `boot_alive` overrides it entirely,
    # so the test contract "injected boot_alive still wins" is preserved.
    _boot_handle: dict[str, Any] = {"proc": None}
    if restart is None:
        def restart() -> bool:
            # Fire dev:restart in the background, then poll /health to 200.
            #
            # ensure-runtime-cold-boot-starvation-round-3 (the LIVE-confirmed root
            # cause the two prior unit-test-green fixes never reached): the spawn is
            # PLATFORM-BLIND. `restart_command` is `npm run dev:restart`, and on
            # Windows `npm` is `npm.cmd` — a batch shim that Windows `CreateProcess`
            # will NOT resolve from a bare-token argv (no `.cmd`/PATHEXT lookup
            # without a shell). So `subprocess.Popen(shlex.split("npm run …"))` with
            # the default `shell=False` raises `FileNotFoundError` ([WinError 2]) —
            # caught by the `(OSError, ValueError)` guard below, which returns False
            # BEFORE the boot is ever spawned, BEFORE `_boot_handle` is stashed, and
            # BEFORE `write_boot_stamp` runs. The whole boot-liveness / time-window-
            # grace / patient-wait machinery (rounds 32 + 2) is therefore DEAD on
            # Windows: no boot ⇒ no stamp ⇒ `boot_alive()` always False ⇒ every
            # `_recover_runtime` iteration classifies `dead` and "kill-restarts" a
            # boot that never launched, exhausting the ≤5× cap in ~60-80s → false
            # `mcp-runtime-unready` BLOCKED. (The manual `npm run dev:restart` works
            # because the interactive shell DOES resolve `npm.cmd`; the asymmetry is
            # exactly the shell.) Both prior fixes were unit-green because EVERY test
            # either injects `restart` or monkeypatches `lazy_core.subprocess` with a
            # fake whose `.Popen` always succeeds — so the real, platform-blind spawn
            # was never exercised.
            #
            # Fix: on Windows, spawn through the shell (`shell=True` with the command
            # STRING — a list arg is ignored under `shell=True` on Windows) so the
            # `.cmd` shim resolves exactly as it does for a manual invocation. On
            # POSIX keep the safer no-shell shlex-split argv (the command is a repo
            # config value, and `cmd.exe`/`/bin/sh` quoting differences are avoided).
            try:
                if os.name == "nt":
                    proc = subprocess.Popen(  # noqa: S602 — repo-config command, not user input
                        cfg["restart_command"],
                        cwd=str(repo_root),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=True,
                    )
                else:
                    proc = subprocess.Popen(  # noqa: S603 — repo-config command, not user input
                        shlex.split(cfg["restart_command"]),
                        cwd=str(repo_root),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            except (OSError, ValueError):
                return False
            # Stash the live boot handle so the boot-liveness signal can read its
            # `.poll()` during the pre-Vite window while BOTH ports are still down.
            _boot_handle["proc"] = proc
            # ALSO record the spawn epoch to a persistent stamp file
            # (ensure-runtime-recovery-starves-cold-compile-round-2). The handle
            # `.poll()` is NOT trustworthy on Windows — `restart_command` spawns a
            # short-lived npm/cmd shell-chain wrapper that exits seconds after
            # launching the detached `tauri dev`/`cargo build` child, so its
            # `.poll()` reports an exit code long before the ~3.5-min cold compile
            # finishes. The persistent stamp drives the time-window grace in
            # `boot_alive()` below, which survives the wrapper exiting AND survives
            # across the bounded `_recover_runtime` loop (so the loop's first
            # restart spawns ONE compile and every subsequent iteration sees "a
            # boot is in progress" and STOPS re-killing it — the murder-site fix).
            write_boot_stamp(repo_root, spawn_ts=time.time())
            for _ in range(90):  # ~7.5 min ceiling (90 × 5s)
                code, _payload = probe()
                if code == 200:
                    return True
                time.sleep(5)
            return False
    if stale_check is None:
        # stale-runtime-health-200-false-blocked: bind the REAL freshness
        # predicate (previously this defaulted to `lambda: False`, making the
        # STALE verdict UNREACHABLE in production — stale_binary.py shipped as
        # an orphaned predicate with no production caller). The fail-safe
        # direction (missing signal / any error → not stale) is preserved
        # INSIDE `_default_stale_check` itself, so the health=200 gate stays
        # the primary guard exactly as before whenever no boot signal exists.
        stale_check = lambda: _default_stale_check(repo_root, cfg)
    if sidecar_check is None:
        # Sidecar-pipe readiness (Leg A,
        # env-transient-counts-against-validation-retry-budget). When the config
        # asserts the sidecar, bind the real get_sidecar_status probe; otherwise
        # the assertion is skipped (the sidecar is treated as connected — the
        # default-off, repo-agnostic path). A legacy config dict without the key
        # is tolerated via .get(), so an un-migrated override never raises.
        if cfg.get("assert_sidecar_connected"):
            _sidecar_url = cfg.get(
                "sidecar_status_url",
                _ENSURE_RUNTIME_DEFAULT_CONFIG["sidecar_status_url"],
            )
            sidecar_check = lambda: _default_sidecar_probe(_sidecar_url)
        else:
            sidecar_check = lambda: True
    if frontend_probe is None:
        # Two-port cold-compile discriminator
        # (ensure-runtime-recovery-starves-cold-compile, Phase 1). When the config
        # carries the :1420 frontend keys, bind the real Vite reachability probe;
        # otherwise the discriminator degrades to today's :3333-only behavior
        # (frontend treated as DOWN → a non-serving backend classifies as `dead`,
        # the bounded-recovery path — byte-identical to today for a non-:1420
        # repo). A legacy config dict without the key is tolerated via .get(), so
        # an un-migrated override never raises. Mirrors the sidecar_check binding.
        _frontend_url = cfg.get("frontend_health_url")
        if _frontend_url:
            frontend_probe = lambda: _default_frontend_probe(_frontend_url)
        else:
            frontend_probe = lambda: False
    if boot_alive is None:
        # Pre-Vite boot-liveness signal
        # (ensure-runtime-starves-pre-vite-sidecar-build, Phase 1). When the
        # config asserts the boot-liveness signal, bind the real source — the
        # liveness of the `restart()`-spawned boot process. That boot process is
        # the `Popen` the production `restart()` closure already owns (see the
        # default `restart` above): in production a boot-liveness read consults
        # that in-process handle's `.poll()` (None ⇒ still running ⇒ alive), so
        # NO URL probe / `_default_*` helper is needed — the handle reaches the
        # classifier in-process via this same `ensure_runtime` call. Tests always
        # INJECT `boot_alive`, so the production-only branch below is a documented
        # placeholder that fail-safes toward NOT-booting (lambda: False) until the
        # CLI-seam handle-threading wires a live handle (Phase 3 / consumer). A
        # legacy config dict without the key is tolerated via .get(), so an
        # un-migrated override never raises. Mirrors the frontend_probe binding.
        if cfg.get("boot_liveness"):
            # Production source: the in-process boot-process `Popen` handle's
            # liveness (ensure-runtime-starves-pre-vite-sidecar-build Phase 3 —
            # the CLI-seam wiring this branch's placeholder was waiting on). The
            # default `restart()` closure above stashes the spawned boot handle in
            # `_boot_handle["proc"]`; a live signal reads it back here:
            #   - no handle yet (restart not called / spawn failed) ⇒ None ⇒ NOT
            #     booting (fail-safe — a genuinely dead host still reaches bounded
            #     recovery, never a forever patient-wait);
            #   - handle present + `.poll()` is None ⇒ the boot process is STILL
            #     RUNNING ⇒ the pre-Vite cold window is in progress ⇒ alive
            #     (`_classify_compile_state` returns `compiling`, patient-wait);
            #   - handle present + `.poll()` is an exit code ⇒ the boot process
            #     EXITED. On Windows this is the COMMON case while the compile is
            #     still running — the npm/cmd wrapper exits early
            #     (ensure-runtime-recovery-starves-cold-compile-round-2). So an
            #     exited handle does NOT by itself mean "dead": fall through to the
            #     persistent boot-spawn TIME-WINDOW grace, which reports the cold
            #     boot as still in progress for `_BOOT_SPAWN_GRACE_SECONDS` after
            #     the spawn regardless of the wrapper handle's fate.
            #   - no handle AND no fresh stamp ⇒ NOT booting (fail-safe — a
            #     genuinely dead host still reaches bounded recovery and ages out of
            #     the grace into BLOCKED; never a forever patient-wait).
            # `.poll()` never raises for a valid handle; a defensive guard keeps a
            # surprising handle state fail-safe toward the grace check.
            def boot_alive() -> bool:
                proc = _boot_handle.get("proc")
                if proc is not None:
                    try:
                        if proc.poll() is None:
                            return True  # wrapper still alive ⇒ definitely booting
                    except Exception:  # noqa: BLE001 — fall through to the grace
                        pass
                # Wrapper exited (or no handle this call): trust the persistent
                # time-window grace — the Windows-robust cold-boot-in-progress
                # detector that survives the npm/cmd wrapper exiting early.
                return boot_recently_spawned(repo_root)
        else:
            boot_alive = lambda: False

    # ---- M4 mode: Identity engaged (LD3) -------------------------------------
    # Identity is "engaged" iff the caller threads a controller session id OR an
    # explicit lock/kernel reader — i.e. it wants verifiable-ownership routing.
    identity_engaged = (
        live_session_id is not None
        or read_lock is not None
        or kernel_start_time_fn is not None
    )
    if identity_engaged:
        if read_lock is None:
            read_lock = lambda: read_runtime_lock(repo_root, config=cfg)
        if kernel_start_time_fn is None:
            kernel_start_time_fn = kernel_start_time
        if sleep is None:
            sleep = time.sleep
        if write_lock is None:
            def write_lock(**kw):
                write_runtime_lock(repo_root, config=cfg, **kw)
        # recover_identity / kill default to None — recovery rewrites the lock
        # only when an identity discovery callable is supplied, and the HIJACKED
        # fail-safe NEVER kills (kill is wired only so a test can assert it is
        # not called; production passes None and no kill path exists).
        return _ensure_runtime_m4(
            cfg,
            probe=probe,
            restart=restart,
            stale_check=stale_check,
            read_lock=read_lock,
            live_session_id=live_session_id,
            kernel_start_time_fn=kernel_start_time_fn,
            sleep=sleep,
            write_lock=write_lock,
            recover_identity=recover_identity,
            tool_name=tool_name,
            sidecar_check=sidecar_check,
            frontend_probe=frontend_probe,
            boot_alive=boot_alive,
        )

    # ---- Legacy mode: pre-M4 boot/stale/ready flow ---------------------------
    # ensure-runtime-legacy-mode-optimistic-ready-verdict (Phase 1): the down /
    # stale-rebuild arms used to hard-set status='booted'/'stale-rebuilt'
    # UNCONDITIONALLY after the post-restart re-probe, so a still-dead runtime
    # returned state: READY with a non-200 health_code (the optimistic lie). The
    # verdict is now DERIVED from the re-probe code, reusing the SAME honest M4
    # routing helpers (_classify_compile_state → patient-wait / bounded-recovery)
    # so a non-200 re-probe yields DEAD→READY-on-200|BLOCKED, never a false READY.
    # The 200 paths are byte-identical to before (booted / stale-rebuilt / ready).
    if sleep is None:
        sleep = time.sleep

    code, payload = probe()
    if code != 200:
        # Runtime DOWN → boot it, then re-probe.
        restart()
        code, payload = probe()
        if code == 200:
            status = "booted"  # recovered on the first restart (unchanged)
        else:
            # Still non-serving after the boot attempt. Route the re-probe code
            # through the same honest classifier the M4 path uses instead of
            # claiming READY: a `compiling` runtime (frontend up) is patiently
            # waited on; a genuinely `dead` runtime enters bounded recovery and
            # ends READY only on a healthy re-probe, else BLOCKED.
            return _route_legacy_non_serving(
                cfg, code=code, payload=payload, probe=probe, restart=restart,
                frontend_probe=frontend_probe, sleep=sleep, tool_name=tool_name,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            )
    elif stale_check():
        # Runtime UP but binary STALE → force a rebuild, then re-probe.
        restart()
        code, payload = probe()
        if code == 200:
            status = "stale-rebuilt"  # rebuilt and serving (unchanged)
        else:
            # The rebuild left the runtime non-serving — do NOT claim STALE/READY
            # honestly; route the re-probe through the same recovery machinery.
            return _route_legacy_non_serving(
                cfg, code=code, payload=payload, probe=probe, restart=restart,
                frontend_probe=frontend_probe, sleep=sleep, tool_name=tool_name,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            )
    else:
        # Runtime UP and CURRENT.
        status = "ready"

    # 200-path verdict (booted / stale-rebuilt / ready) — unchanged honest shape.
    # (code == 200 here, so _mcp_tools_present_honest is byte-identical to the
    # bare _mcp_tool_in_payload; used for consistency with the verdict builder.)
    return {
        "status": status,
        "state": _LEGACY_STATUS_TO_STATE.get(status, "READY"),
        "ownership_verified": False,
        "mcp_tools_present": _mcp_tools_present_honest(payload, tool_name, code),
        "health_code": code,
        "terminal_blocker": None,
    }


def _route_legacy_non_serving(
    cfg, *, code, payload, probe, restart, frontend_probe, sleep, tool_name,
    sidecar_check=None, boot_alive=None,
):
    """Honest verdict for a legacy-mode runtime still non-serving after a boot /
    rebuild attempt (ensure-runtime-legacy-mode-optimistic-ready-verdict, Phase 1).

    Mirrors the M4 path's ``_route_non_serving``: branch the non-200 re-probe on
    ``_classify_compile_state(code, frontend_up, boot_alive)`` — a ``compiling``
    runtime (Vite :1420 up, backend not yet serving — OR, per
    ensure-runtime-starves-pre-vite-sidecar-build Phase 2, BOTH ports down but the
    boot process still ALIVE: the pre-Vite ``BeforeDevCommand``/``sidecar:build``
    window) is PATIENTLY WAITED on via ``_await_compile_serving`` (never
    kill-restarted); a genuinely ``dead`` runtime (frontend also down AND no live
    boot) enters the bounded ``_recover_runtime`` crash loop → READY on a healthy
    re-probe, else BLOCKED.

    Legacy mode has no ownership identity, so ``ownership_verified=False`` and the
    lock-rewrite is skipped (``recover_identity=None``, ``write_lock`` a no-op).
    The result is the verdict SUPERSET — it NEVER returns ``state: READY`` with a
    non-200 ``health_code`` (the honest invariant). ``mcp_tools_present`` is read
    from whatever payload the recovery machinery resolves, so a non-serving
    runtime with no configured tool name reports ``False`` (not vacuously True).
    """
    if boot_alive is None:
        boot_alive = lambda: False
    try:
        frontend_up = bool(frontend_probe())
    except Exception:  # noqa: BLE001 — a probe error is treated as down (dead)
        frontend_up = False
    try:
        boot_up = bool(boot_alive())
    except Exception:  # noqa: BLE001 — a probe error is treated as not-booting
        boot_up = False

    def _noop_write_lock(**_kw):
        # Legacy mode has no ownership lock to rewrite.
        return None

    if _classify_compile_state(code, frontend_up, boot_up) == "compiling":
        verdict = _await_compile_serving(
            cfg, ownership_verified=False, probe=probe,
            frontend_probe=frontend_probe, sleep=sleep, write_lock=_noop_write_lock,
            recover_identity=None, tool_name=tool_name,
            initial_code=code, initial_payload=payload,
            sidecar_check=sidecar_check, boot_alive=boot_alive,
        )
        if verdict is not _COMPILE_WENT_DEAD:
            return verdict
        # compiling → dead mid-wait: fall through to bounded crash recovery.
    return _recover_runtime(
        cfg, "DEAD", ownership_verified=False, probe=probe, restart=restart,
        sleep=sleep, write_lock=_noop_write_lock, recover_identity=None,
        tool_name=tool_name, initial_code=code, initial_payload=payload,
        sidecar_check=sidecar_check,
        # ensure-runtime-recovery-starves-cold-compile-round-2: the legacy path gets
        # the SAME murder-site handoff as M4 — once the bounded loop's first
        # restart() puts a real compile in flight (fresh boot stamp), hand off to the
        # patient wait instead of re-killing it. Without this, the legacy
        # no-run-marker `--ensure-runtime` call (live_session_id None) was still
        # starved.
        frontend_probe=frontend_probe, boot_alive=boot_alive,
        await_compile=lambda init_code, init_payload: _await_compile_serving(
            cfg, ownership_verified=False, probe=probe,
            frontend_probe=frontend_probe, sleep=sleep, write_lock=_noop_write_lock,
            recover_identity=None, tool_name=tool_name,
            initial_code=init_code, initial_payload=init_payload,
            sidecar_check=sidecar_check, boot_alive=boot_alive,
        ),
    )


def _runtime_verdict(state, *, ownership_verified, health_code, payload,
                     tool_name, terminal_blocker=None, status=None):
    """Build the M4 verdict dict (the superset shape).

    ``status`` (the legacy field) is derived from ``state`` when not supplied so
    every caller — old or new — sees both keys. ``READY``→``ready``,
    ``STALE``→``stale-rebuilt``, ``HIJACKED``/``DEAD``/``BLOCKED``→``booted``
    (the legacy flow never modelled a failed runtime; the legacy field is purely
    for the un-migrated part-5 reader and is superseded by ``state``)."""
    if status is None:
        status = {
            "READY": "ready",
            "STALE": "stale-rebuilt",
        }.get(state, "booted")
    return {
        "status": status,
        "state": state,
        "ownership_verified": bool(ownership_verified),
        "mcp_tools_present": _mcp_tools_present_honest(
            payload, tool_name, health_code
        ),
        "health_code": int(health_code or 0),
        "terminal_blocker": terminal_blocker,
    }


def _hijacked_blocker(lock):
    """The HIJACKED terminal_blocker message (LD3). Names the foreign port-holder
    and the never-SIGKILL safety rule so Phase 5 can surface it verbatim into a
    BLOCKED.md ``blocker_kind: mcp-runtime-unready``."""
    port = lock.get("port") if isinstance(lock, dict) else None
    where = f"port {port}" if port else "the runtime port"
    return (
        f"Runtime ownership could not be verified — a foreign process is holding "
        f"{where} (recorded PID/start_time/session diverges from the live kernel). "
        f"Refusing to SIGKILL an unowned process (LD3 safety/stability rule); "
        f"surface as BLOCKED (blocker_kind: mcp-runtime-unready) for operator "
        f"intervention."
    )


def _blocked_blocker(attempts):
    """The recovery-exhausted BLOCKED terminal_blocker message (LD3)."""
    return (
        f"Runtime recovery exhausted — restart() retried {attempts} times "
        f"(bounded cap {_RUNTIME_RECOVERY_MAX_ATTEMPTS}) with exponential backoff "
        f"without restoring a healthy, owned runtime. Halting with no further "
        f"retries (blocker_kind: mcp-runtime-unready)."
    )


def _cold_compile_timeout_blocker():
    """The patient-wait cold-compile-timeout terminal_blocker message
    (ensure-runtime-recovery-starves-cold-compile, Phase 2 / Open Question 5).

    DISTINCT verbatim text from ``_blocked_blocker`` so the operator can tell a
    cold-compile that genuinely never finished apart from a generic
    crash-recovery exhaustion — but it still maps to the SAME downstream
    ``blocker_kind: mcp-runtime-unready`` (no new blocker_kind). It describes the
    patient-wait semantics: the runtime was COMPILING (Vite up, backend not yet
    serving) and was WAITED on — never kill-restarted — for the full
    cold-compile budget without the backend ever reaching a serving state.
    """
    secs = int(_COLD_COMPILE_WAIT_MAX_POLLS * _COLD_COMPILE_WAIT_INTERVAL)
    return (
        f"Cold compile timed out — the runtime was still COMPILING (Vite dev "
        f"server up, backend /health not yet serving) and was patiently waited "
        f"on for ~{secs}s ({_COLD_COMPILE_WAIT_MAX_POLLS} polls) WITHOUT a "
        f"kill-restart, but the backend never reached a serving state. The "
        f"compile genuinely never finished (not a crash-recovery exhaustion). "
        f"Halting (blocker_kind: mcp-runtime-unready)."
    )


def _ensure_runtime_m4(
    cfg,
    *,
    probe,
    restart,
    stale_check,
    read_lock,
    live_session_id,
    kernel_start_time_fn,
    sleep,
    write_lock,
    recover_identity,
    tool_name,
    sidecar_check=None,
    frontend_probe=None,
    boot_alive=None,
):
    """The M4 Identity → Staleness → Health classifier + bounded recovery (LD3).

    Identity classifies the runtime; HIJACKED is a strict fail-safe (terminal
    blocker, NEVER restart/kill); STALE/DEAD enter the bounded exponential-backoff
    recovery loop (≤ ``_RUNTIME_RECOVERY_MAX_ATTEMPTS`` restarts) → READY on a
    re-probe success (lock rewritten) or BLOCKED on exhaustion.

    ensure-runtime-recovery-starves-cold-compile (Phase 2): the LD3 bounded loop is
    RE-SCOPED to genuine crashes. Each point that today routes a non-serving runtime
    into ``_recover_runtime`` now first consults ``_classify_compile_state(code,
    frontend_probe())``: a ``compiling`` runtime (Vite :1420 up, backend :3333 not
    yet serving — a cold Rust compile in progress) is PATIENTLY WAITED on via
    ``_await_compile_serving`` (never kill-restarted); only a genuinely ``dead``
    runtime (both ports down) enters the ≤5×backoff crash loop. A ``compiling → dead``
    transition mid-wait falls through to that same crash loop. Default-off: when no
    frontend signal is present (``frontend_probe → False``), every non-serving runtime
    classifies as ``dead`` ⇒ byte-identical to today's recovery behavior.
    """
    if frontend_probe is None:
        # Defensive default for legacy/un-threaded callers (e.g. a test that does
        # not inject one): no frontend signal ⇒ never `compiling` ⇒ today's path.
        frontend_probe = lambda: False
    if boot_alive is None:
        # Defensive default (ensure-runtime-starves-pre-vite-sidecar-build): no
        # boot-liveness signal ⇒ a both-ports-down runtime is never the pre-Vite
        # `compiling` case ⇒ today's `dead`/recovery path. Default-off byte-
        # identity preserved for every legacy/un-threaded caller.
        boot_alive = lambda: False
    code, payload = probe()
    lock = read_lock()

    def _route_non_serving(from_state, *, ownership_verified, code, payload):
        """Branch a non-serving runtime on the two-port (+ boot-liveness)
        classifier: `compiling` → patient wait (never restart); `dead`/default-off
        → bounded crash recovery. A `compiling` here covers BOTH the Vite-up
        backend-compiling window AND the pre-Vite both-ports-down-but-live-boot
        window (ensure-runtime-starves-pre-vite-sidecar-build Phase 2). A
        `compiling → dead` transition during the patient wait routes back here as
        the bounded crash loop."""
        try:
            frontend_up = bool(frontend_probe())
        except Exception:  # noqa: BLE001 — a probe error is treated as down (dead)
            frontend_up = False
        try:
            boot_up = bool(boot_alive())
        except Exception:  # noqa: BLE001 — a probe error is treated as not-booting
            boot_up = False
        if _classify_compile_state(code, frontend_up, boot_up) == "compiling":
            verdict = _await_compile_serving(
                cfg, ownership_verified=ownership_verified, probe=probe,
                frontend_probe=frontend_probe, sleep=sleep, write_lock=write_lock,
                recover_identity=recover_identity, tool_name=tool_name,
                initial_code=code, initial_payload=payload,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            )
            if verdict is not _COMPILE_WENT_DEAD:
                return verdict
            # compiling → dead mid-wait: fall through to bounded crash recovery.
        return _recover_runtime(
            cfg, from_state, ownership_verified=ownership_verified, probe=probe,
            restart=restart, sleep=sleep, write_lock=write_lock,
            recover_identity=recover_identity, tool_name=tool_name,
            initial_code=code, initial_payload=payload, sidecar_check=sidecar_check,
            # ensure-runtime-recovery-starves-cold-compile-round-2: thread the
            # cold-boot-in-progress signals so the bounded crash loop HANDS OFF to
            # the patient wait the instant its own first `restart()` puts a genuine
            # compile in flight — instead of re-killing it on the next iteration.
            frontend_probe=frontend_probe, boot_alive=boot_alive,
            await_compile=lambda init_code, init_payload: _await_compile_serving(
                cfg, ownership_verified=ownership_verified, probe=probe,
                frontend_probe=frontend_probe, sleep=sleep, write_lock=write_lock,
                recover_identity=recover_identity, tool_name=tool_name,
                initial_code=init_code, initial_payload=init_payload,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            ),
        )

    # ---- Phase 1: Identity ---------------------------------------------------
    if not isinstance(lock, dict):
        # No recorded ownership. A /health that answers is, by default, an
        # unverified foreign port-holder (health=200 is NOT proof of ownership —
        # LD1) ⇒ HIJACKED (strict fail-safe: never kill it); nothing answering ⇒
        # DEAD (recover).
        #
        # Gap-2 soft owned-unverified-serving READY on the lock-is-None (and
        # lock-diverged) branch (harness-mcp-observation-gap-disposition-and-
        # hijacked-runtime, Phase 2). The post-mcp-test HIJACKED case falls HERE:
        # an /mcp-test cycle does its OWN dev:restart / engine boot inside the
        # cycle subagent, which overwrites or invalidates `.runtime.lock.json`'s
        # ownership record (the lock no longer matches the live kernel/session, or
        # is absent), so read_lock() returns None on the orchestrator's next
        # --ensure-runtime probe. Pre-fix this returned terminal HIJACKED even
        # though the serving runtime is PROVABLY this app's (its MCP tools are
        # present in `payload`), forcing a dev:kill + cold reboot every cycle
        # (which re-introduces cold-boot flake). The lock divergence is
        # bookkeeping-only here, NOT a foreign takeover.
        #
        # `_mcp_tools_present_honest(payload, tool_name, code)` is the honest
        # "serving MY app" signal — the SAME signal the lock-present soft-READY
        # path at the `owned == False` branch below consults (see the
        # is_owned_unverified_serving rationale further down). When it confirms
        # THIS app's tool surface at health 200, re-adopt ownership by rewriting
        # the lock for the live serving process and return a non-terminal soft
        # READY (ownership_verified False) instead of the terminal HIJACKED
        # fail-safe. A genuinely foreign port-holder serving a DIFFERENT app's tool
        # surface FAILS `_mcp_tools_present_honest` and stays terminal HIJACKED —
        # so the LD3 strict fail-safe (never SIGKILL / never re-adopt a foreign
        # process) is preserved. A stale-but-serving runtime is NOT masked: route
        # it through STALE/rebuild FIRST (mirrors the owned-unverified ordering so
        # the soft-READY shortcut never short-circuits a stale rebuild).
        if code == 200 and _mcp_tools_present_honest(payload, tool_name, code):
            if stale_check():
                # Stale binary on a lock-diverged-but-serving-our-tools runtime:
                # route through STALE/rebuild (do NOT mask with a soft READY).
                return _route_non_serving(
                    "STALE", ownership_verified=False, code=code, payload=payload,
                )
            # Re-adopt ownership: rewrite `.runtime.lock.json` for the live serving
            # process (best-effort, mirroring the existing recover_identity →
            # write_lock pattern used on the post-recovery READY path) so the NEXT
            # cycle verifies against the now-recorded ownership instead of
            # re-deriving lock-is-None.
            if recover_identity is not None:
                try:
                    ident = recover_identity()
                except Exception:  # noqa: BLE001 — identity discovery is best-effort
                    ident = None
                if isinstance(ident, dict):
                    try:
                        write_lock(
                            pid=ident.get("pid"),
                            start_time=ident.get("start_time"),
                            port=cfg.get("port"),
                            artifact_hash=ident.get("artifact_hash"),
                            controller_session_id=ident.get("controller_session_id"),
                        )
                    except Exception:  # noqa: BLE001 — a lock-write error never
                        # downgrades a provably-ours serving runtime to HIJACKED.
                        pass
            return _runtime_verdict(
                "READY", ownership_verified=False, health_code=code,
                payload=payload, tool_name=tool_name, terminal_blocker=None,
            )
        if code == 200:
            # Health answers but the tool surface is NOT ours (or the honest signal
            # reports not-serving) — an unverified foreign port-holder. HIJACKED
            # strict fail-safe: never kill, never re-adopt (LD3).
            return _runtime_verdict(
                "HIJACKED", ownership_verified=False, health_code=code,
                payload=payload, tool_name=tool_name,
                terminal_blocker=_hijacked_blocker(lock),
            )
        return _route_non_serving(
            "DEAD", ownership_verified=False, code=code, payload=payload,
        )

    owned = verify_runtime_ownership(
        lock,
        live_session_id=live_session_id,
        kernel_start_time_fn=kernel_start_time_fn,
    )
    if not owned:
        # The recorded PID is either dead (kernel start_time None ⇒ DEAD, a
        # recovery candidate) or held by a foreign process whose start_time/
        # session diverges (a LIVE foreign owner ⇒ HIJACKED, NEVER killed).
        live_start = None
        try:
            live_start = kernel_start_time_fn(lock.get("pid"))
        except TypeError:
            live_start = kernel_start_time_fn(lock.get("pid"), platform=sys.platform)
        except Exception:  # noqa: BLE001 — best-effort
            live_start = None
        if live_start is None:
            return _route_non_serving(
                "DEAD", ownership_verified=False, code=code, payload=payload,
            )
        # ensure-runtime-false-hijacked-on-owned-serving-runtime (P1) — SOFT
        # owned-unverified READY. `verify_runtime_ownership` is False here, but a
        # live PID whose kernel start_time MATCHES the recorded lock start_time is
        # the run's OWN booted process (start_time match defeats PID reuse — a
        # foreign port-holder via a reused PID reports a divergent start_time). So
        # if ALL of: (a) the lock PID is that same serving process
        # (`live_start == lock['start_time']`), (b) /health answers 200, AND
        # (c) the runtime is provably serving THIS app's MCP tools
        # (`_mcp_tools_present_honest`, derived the SAME way the verdict builder
        # does so guard and verdict agree) — then the divergence is bookkeeping-
        # only (the lock's controller_session_id and the threaded live_session_id
        # come from different sources; see verify_runtime_ownership). The runtime
        # is provably alive, ours, and serving, so we proceed with a non-terminal
        # READY (`ownership_verified: False`) instead of the terminal HIJACKED
        # fail-safe — and we NEVER SIGKILL (no restart on this path). If any
        # condition is False we fall through to the unchanged terminal HIJACKED
        # below. A genuinely STALE binary is NOT masked: stale_check() runs FIRST,
        # routing a stale-but-owned-unverified-serving runtime through the same
        # STALE/rebuild path a verified-owned one takes (the soft-READY shortcut
        # never short-circuits a stale rebuild).
        is_owned_unverified_serving = (
            code == 200
            and _mcp_tools_present_honest(payload, tool_name, code)
            and live_start == lock.get("start_time")
        )
        if is_owned_unverified_serving:
            if stale_check():
                # Stale binary on an owned-unverified-but-serving runtime: route
                # through STALE/rebuild (do NOT mask it with a soft READY).
                return _route_non_serving(
                    "STALE", ownership_verified=False, code=code, payload=payload,
                )
            return _runtime_verdict(
                "READY", ownership_verified=False, health_code=code,
                payload=payload, tool_name=tool_name, terminal_blocker=None,
            )
        # Live foreign PID — HIJACKED strict fail-safe: set the terminal_blocker
        # and return WITHOUT restart() or any kill of the foreign process (LD3).
        return _runtime_verdict(
            "HIJACKED", ownership_verified=False, health_code=code,
            payload=payload, tool_name=tool_name,
            terminal_blocker=_hijacked_blocker(lock),
        )

    # Ownership verified (the recorded PID is ours, alive, current session).
    # ---- Phase 2: Staleness --------------------------------------------------
    if stale_check():
        # A serving-but-stale runtime (code==200) classifies as `serving`, so it
        # rebuilds via _recover_runtime (the existing STALE→rebuild path). A stale
        # runtime that is ALSO not yet serving while Vite is up (a new-crate STALE
        # during a cold compile) classifies `compiling` ⇒ patient wait, not a
        # starved kill-restart (the cold-compile re-scope).
        return _route_non_serving(
            "STALE", ownership_verified=True, code=code, payload=payload,
        )

    # ---- Phase 3: Health -----------------------------------------------------
    if code == 200:
        # HTTP-healthy. But a runtime can be /health-200 while the MCP sidecar
        # named pipe is dead (a zombie node process holding it after a
        # dev:restart — env-transient-counts-against-validation-retry-budget,
        # Leg A). When the config asserts the sidecar, a disconnected pipe is NOT
        # READY: route into recovery (a dev:restart that reaps the stale pipe).
        # Default-off (sidecar_check None or lambda: True) preserves the bare
        # READY byte-for-byte. The recovery re-probe re-asserts the pipe, so a
        # restart that fixes HTTP but not the pipe ends BLOCKED, never READY.
        if sidecar_check is not None and not sidecar_check():
            # code==200 ⇒ classifies `serving`, so _route_non_serving falls through
            # to the existing _recover_runtime pipe-reap path (unchanged behavior).
            return _route_non_serving(
                "DEAD", ownership_verified=True, code=code, payload=payload,
            )
        return _runtime_verdict(
            "READY", ownership_verified=True, health_code=code,
            payload=payload, tool_name=tool_name,
        )
    # Owned, alive, current — but /health refused ⇒ the runtime endpoint is not
    # serving. Branch on the two-port classifier: a cold compile (Vite up) is
    # PATIENTLY WAITED on (the starvation fix); a genuinely dead backend (Vite
    # also down) enters today's bounded crash recovery.
    return _route_non_serving(
        "DEAD", ownership_verified=True, code=code, payload=payload,
    )


_COMPILE_WENT_DEAD = object()
"""Sentinel returned by ``_await_compile_serving`` when the runtime crossed from
``compiling`` to ``dead`` mid-wait (Vite went down) — the M4 caller routes this
into the bounded ``_recover_runtime`` crash path. NOT a verdict dict, so a caller
must check identity before treating the return as a verdict."""


def _await_compile_serving(
    cfg,
    *,
    ownership_verified,
    probe,
    frontend_probe,
    sleep,
    write_lock,
    recover_identity,
    tool_name,
    initial_code,
    initial_payload,
    sidecar_check=None,
    boot_alive=None,
):
    """Patient, NON-killing wait for a `compiling` runtime to reach serving
    (ensure-runtime-recovery-starves-cold-compile, Phase 2; pre-Vite extension
    ensure-runtime-starves-pre-vite-sidecar-build, Phase 2).

    A runtime classified ``compiling`` (Vite :1420 up, backend :3333 not yet
    serving — OR both ports down but the boot process still ALIVE: the pre-Vite
    ``BeforeDevCommand``/``sidecar:build`` window) is the cold boot/compile still
    in progress — it must be WAITED on, never kill-restarted (the starvation root
    cause). This poller:

      - polls ``probe()`` on the cold-compile-sized ceiling
        (``_COLD_COMPILE_WAIT_MAX_POLLS × _COLD_COMPILE_WAIT_INTERVAL`` ≈ 7.5 min,
        REUSING the production restart()-awaiter sizing — NOT the ≤5×backoff crash
        budget), NEVER calling ``restart()``/``kill`` while compiling;
      - returns a READY verdict once ``probe()`` answers 200 (AND, when
        ``sidecar_check`` is asserted, the sidecar pipe is connected — REUSING the
        existing recovery sidecar composition; rewriting the ownership lock via
        ``recover_identity``/``write_lock`` exactly like ``_recover_runtime``);
      - returns the ``_COMPILE_WENT_DEAD`` sentinel if the runtime goes dead
        mid-wait — the frontend goes down AND the boot process is no longer alive
        (``compiling → dead``) — so the M4 caller falls through to bounded
        ``_recover_runtime``. The pre-Vite analog of the Vite-up went-dead check:
        a live boot crossing to dead (``boot_alive`` going false) with both ports
        still down is the same fall-through (ensure-runtime-starves-pre-vite-
        sidecar-build Phase 2);
      - on ceiling exhaustion while STILL compiling, returns a BLOCKED verdict
        whose ``terminal_blocker`` is the DISTINCT ``_cold_compile_timeout_blocker``
        text (still ``blocker_kind: mcp-runtime-unready`` downstream).

    ``sleep`` is injected so ``--test`` is hermetic (no real 7.5-min wait).
    """
    if boot_alive is None:
        # Defensive default: no boot-liveness signal ⇒ the went-dead check is the
        # frontend-only check (byte-identical to the Vite-up-only prior behavior).
        boot_alive = lambda: False
    code, payload = initial_code, initial_payload
    for poll in range(_COLD_COMPILE_WAIT_MAX_POLLS):
        if code == 200:
            # Backend is serving. Compose the sidecar assertion (a serving-but-
            # pipe-dead runtime is NOT ready — keep waiting for the pipe, exactly
            # as _recover_runtime does on its healthy re-probe).
            if sidecar_check is not None and not sidecar_check():
                pass  # fall through to the re-poll below (pipe not yet connected)
            else:
                # Serving + (sidecar connected | not asserted) → READY. Rewrite
                # the ownership lock so the NEXT cycle verifies against the now-
                # serving process (best-effort, mirroring _recover_runtime).
                if recover_identity is not None:
                    try:
                        ident = recover_identity()
                    except Exception:  # noqa: BLE001
                        ident = None
                    if isinstance(ident, dict):
                        try:
                            write_lock(
                                pid=ident.get("pid"),
                                start_time=ident.get("start_time"),
                                port=cfg.get("port"),
                                artifact_hash=ident.get("artifact_hash"),
                                controller_session_id=ident.get("controller_session_id"),
                            )
                        except Exception:  # noqa: BLE001
                            pass
                return _runtime_verdict(
                    "READY", ownership_verified=ownership_verified,
                    health_code=code, payload=payload, tool_name=tool_name,
                )
        else:
            # Backend not yet serving — is it still compiling (Vite up OR boot
            # process alive) or has it crossed to dead (BOTH false)? The pre-Vite
            # window keeps the runtime `compiling` on the boot-liveness signal even
            # while Vite is still down (ensure-runtime-starves-pre-vite-sidecar-
            # build Phase 2). Only when NEITHER signal reports "still alive" does
            # the runtime cross to dead.
            try:
                still_frontend = bool(frontend_probe())
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as down
                still_frontend = False
            try:
                still_boot = bool(boot_alive())
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as not-booting
                still_boot = False
            if not still_frontend and not still_boot:
                # compiling → dead: abandon the patient wait, route to bounded
                # crash-recovery (the M4 caller checks the sentinel identity).
                return _COMPILE_WENT_DEAD
        # Still compiling (or serving-but-pipe-dead). Wait — NEVER restart/kill.
        try:
            sleep(_COLD_COMPILE_WAIT_INTERVAL)
        except Exception:  # noqa: BLE001 — a sleep error never aborts the wait
            pass
        code, payload = probe()

    # Final re-check after the loop's last probe: a 200 that landed exactly on the
    # last poll should still resolve READY rather than time out.
    if code == 200 and (sidecar_check is None or sidecar_check()):
        return _runtime_verdict(
            "READY", ownership_verified=ownership_verified,
            health_code=code, payload=payload, tool_name=tool_name,
        )

    # Ceiling exhausted while still compiling (or pipe never reconnected) → a
    # DISTINCT cold-compile-timeout BLOCKED (same blocker_kind downstream).
    return _runtime_verdict(
        "BLOCKED", ownership_verified=ownership_verified, health_code=code,
        payload=payload, tool_name=tool_name,
        terminal_blocker=_cold_compile_timeout_blocker(),
    )


def _recover_runtime(
    cfg,
    from_state,
    *,
    ownership_verified,
    probe,
    restart,
    sleep,
    write_lock,
    recover_identity,
    tool_name,
    initial_code,
    initial_payload,
    sidecar_check=None,
    frontend_probe=None,
    boot_alive=None,
    await_compile=None,
):
    """Bounded exponential-backoff recovery for a STALE/DEAD runtime (LD3).

    Up to ``_RUNTIME_RECOVERY_MAX_ATTEMPTS`` iterations of:
    ``sleep(backoff)`` → ``restart()`` → re-``probe()``. On a 200 re-probe the
    runtime is back: rewrite ``.runtime.lock.json`` with the recovered identity
    (when ``recover_identity`` supplies one) and return READY. On exhaustion
    (no healthy re-probe within the cap) return BLOCKED with a terminal_blocker —
    the loop-prevention guarantee that replaces the hand-rolled poll loops.

    ``sidecar_check`` (env-transient-counts-against-validation-retry-budget,
    Leg A): when supplied (the config asserts the sidecar), a healthy HTTP
    re-probe is NOT sufficient — the recovered runtime must ALSO reconnect the
    sidecar pipe. A restart that restores /health 200 but leaves the pipe dead
    (the zombie persists) does NOT count as recovered: the loop continues and,
    on exhaustion, the verdict is BLOCKED — never a READY against a pipe-dead
    runtime. ``None`` (legacy / default-off) preserves the HTTP-only contract.

    ``frontend_probe`` / ``boot_alive`` / ``await_compile`` (ensure-runtime-
    recovery-starves-cold-compile-round-2): the cold-boot-in-progress HANDOFF. The
    first ``restart()`` here legitimately spawns a cold ``tauri dev`` whose Rust
    compile runs ~3.5 min with both ports down. After EACH restart, if the re-probe
    is non-200 but ``_classify_compile_state`` reports ``compiling`` (Vite up OR the
    boot-spawn time-window grace is fresh), the loop HANDS OFF to the patient,
    non-killing ``await_compile`` instead of looping a second kill-``restart()``
    that would murder the in-progress compile (the root cause of the 5-restarts-in-
    60s starvation). Only the M4 path threads these (production); the legacy /
    default-off callers pass ``None`` and are byte-identical to the prior
    HTTP-only crash loop.
    """
    code, payload = initial_code, initial_payload
    attempts = 0
    for attempt in range(_RUNTIME_RECOVERY_MAX_ATTEMPTS):
        # Exponential backoff BEFORE each restart (1, 2, 4, 8, 16 …s). Injected
        # sleep makes --test assert the schedule with no real wait.
        try:
            sleep(_RUNTIME_RECOVERY_BACKOFF_BASE * (2 ** attempt))
        except Exception:  # noqa: BLE001 — a sleep error never aborts recovery
            pass
        attempts += 1
        try:
            restart()
        except Exception:  # noqa: BLE001 — a restart raising is a failed attempt
            continue
        code, payload = probe()
        # ensure-runtime-recovery-starves-cold-compile-round-2 — the murder-site
        # handoff. This `restart()` may have legitimately put a COLD COMPILE in
        # flight (the production `restart_command` kills then re-spawns `tauri dev`;
        # the Rust build then takes ~3.5 min with both ports down). If the re-probe
        # is still non-200 BUT the cold boot is genuinely in progress — Vite up, OR
        # the time-window boot-spawn grace reports a fresh spawn — DO NOT loop to a
        # second kill-`restart()` (which would run `kill-dev.js` and MURDER the
        # compile). Hand off to the patient, NON-killing `_await_compile_serving`
        # instead. The grace ages out past the cold-compile ceiling, so a host that
        # never actually compiles still exhausts the wait and reaches BLOCKED —
        # never a forever patient-wait of a dead host (fail-safe preserved). Only
        # wired in the M4 path (await_compile supplied); the legacy/None callers are
        # byte-identical to before.
        if code != 200 and await_compile is not None:
            try:
                fe_up = bool(frontend_probe()) if frontend_probe is not None else False
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as down
                fe_up = False
            try:
                boot_up = bool(boot_alive()) if boot_alive is not None else False
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as not-booting
                boot_up = False
            if _classify_compile_state(code, fe_up, boot_up) == "compiling":
                verdict = await_compile(code, payload)
                if verdict is not _COMPILE_WENT_DEAD:
                    return verdict
                # compiling → dead during the patient wait: resume the bounded
                # crash loop where we left off (the kill is now warranted — the
                # boot really did die).
                code, payload = probe()
        if code == 200:
            # HTTP is back — but if the config asserts the sidecar, the pipe must
            # ALSO be reconnected for this to count as recovered. A restart that
            # fixes /health but not the zombie-held pipe keeps retrying (and
            # ultimately BLOCKs) rather than declaring a pipe-dead runtime READY.
            if sidecar_check is not None and not sidecar_check():
                continue
            # Recovered. Rewrite the ownership lock with the new identity so the
            # NEXT cycle verifies against the restarted process (Persistent
            # Service re-attach contract). Best-effort: a missing identity or a
            # write error never downgrades a healthy runtime.
            if recover_identity is not None:
                try:
                    ident = recover_identity()
                except Exception:  # noqa: BLE001
                    ident = None
                if isinstance(ident, dict):
                    try:
                        write_lock(
                            pid=ident.get("pid"),
                            start_time=ident.get("start_time"),
                            port=cfg.get("port"),
                            artifact_hash=ident.get("artifact_hash"),
                            controller_session_id=ident.get("controller_session_id"),
                        )
                    except Exception:  # noqa: BLE001
                        pass
            return _runtime_verdict(
                "READY", ownership_verified=True, health_code=code,
                payload=payload, tool_name=tool_name,
            )

    # Exhausted the bounded cap without restoring health → BLOCKED, no retries.
    return _runtime_verdict(
        "BLOCKED", ownership_verified=ownership_verified, health_code=code,
        payload=payload, tool_name=tool_name,
        terminal_blocker=_blocked_blocker(attempts),
    )


# ===========================================================================
# Long-Build + Runtime Ownership (Phase 1) — cross-platform detached-spawn
# primitive + verifiable on-disk ownership sentinel.
#
# Four stdlib-only, hermetically-testable primitives consumed by Phase 2's
# reworked ``ensure_runtime`` M4 state machine:
#   spawn_detached          — one cross-platform wrapper that spawns a child
#                             detached from the parent (and any subagent)
#                             process tree (SPEC M2 / LD6).
#   kernel_start_time       — temporal-identity extraction, the PID-reuse
#                             defense (SPEC M1 / LD6).
#   write/read_runtime_lock — atomic `.runtime.lock.json` persistence (LD1).
#   verify_runtime_ownership — the verifiability predicate (LD1) — "200 on
#                             /health" is NOT proof of ownership.
#
# Every external interaction is an injected callable (``spawn`` / ``platform``
# / ``which`` / ``kernel_start_time_fn`` / ``replace``) so ``--test`` is
# hermetic without a real cross-platform host — mirroring how ``ensure_runtime``
# injects ``probe``/``restart``/``stale_check``.
# ===========================================================================

# Windows process-creation flags (SPEC M2 / LD6). The breakaway flag escapes a
# parent Job Object's KILL_ON_JOB_CLOSE reaping; the OSError fallback drops it
# when the parent Job forbids breakaway (ERROR_ACCESS_DENIED).
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# FILETIME epoch offset: 100ns intervals between 1601-01-01 and 1970-01-01.
_FILETIME_EPOCH_OFFSET = 116444736000000000
_FILETIME_TICKS_PER_SEC = 10_000_000


def spawn_detached(
    cmd,
    *,
    cwd,
    spawn=None,
    platform=None,
    which=None,
    kernel_start_time_fn=None,
):
    """Spawn ``cmd`` as a child detached from the parent (and any subagent)
    process tree; return ``{"pid": int, "start_time": float | None}``.

    The one cross-platform spawn primitive (SPEC M2 / LD6). It escapes the two
    process-tree-teardown reaping mechanisms a feature-cycle subagent boundary
    triggers:

      - **Windows** — Job Objects with ``KILL_ON_JOB_CLOSE``. The first spawn
        carries ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP |
        CREATE_BREAKAWAY_FROM_JOB``; if the parent Job forbids breakaway the
        OS raises ``OSError`` (``ERROR_ACCESS_DENIED``) and we retry WITHOUT
        the breakaway flag (plain ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP``).
      - **POSIX/WSL** — the WSL utility-VM idle suspend. ``start_new_session=True``
        always; on WSL the command is wrapped in
        ``systemd-run --user --scope --quiet --same-dir`` (bypasses
        ``instanceIdleTimeout``/``vmIdleTimeout``) when ``systemd-run`` is on
        PATH, else a ``setsid`` + ``nohup … sleep infinity`` keep-alive fallback.

    ``PR_SET_PDEATHSIG`` is DELIBERATELY NOT USED — it would kill the child WITH
    the parent, the exact opposite of the requirement.

    Determinism / injection (keeps ``--test`` hermetic):
      - ``spawn`` — callable(cmd, **kwargs) -> object with a ``.pid``. Default:
        ``subprocess.Popen``.
      - ``platform`` — OS sniff override (``sys.platform`` value). Default:
        ``sys.platform``.
      - ``which`` — callable(name) -> path|None (PATH lookup). Default:
        ``shutil.which``.
      - ``kernel_start_time_fn`` — callable(pid, *, platform) -> float|None,
        used to fill ``start_time`` from the live child PID (WU-2). Default:
        None → ``start_time`` is None (WU-1 is independently testable; Phase 2
        binds the real extractor).
    """
    if spawn is None:
        spawn = subprocess.Popen  # noqa: S603 — repo-config command, not user input
    if platform is None:
        platform = sys.platform
    if which is None:
        import shutil
        which = shutil.which

    is_windows = str(platform).startswith("win")

    if is_windows:
        # Try the breakaway flag first; fall back without it on a Job-Object
        # ERROR_ACCESS_DENIED (the parent Job forbids breakaway).
        breakaway = (
            _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_BREAKAWAY_FROM_JOB
        )
        try:
            proc = spawn(cmd, cwd=str(cwd), creationflags=breakaway)
        except OSError:
            plain = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
            proc = spawn(cmd, cwd=str(cwd), creationflags=plain)
    else:
        # POSIX/WSL — wrap the command so the child outlives both the subagent
        # turn and (on WSL) the utility-VM idle suspend.
        launch = list(cmd)
        if which("systemd-run"):
            launch = [
                "systemd-run", "--user", "--scope", "--quiet", "--same-dir",
            ] + launch
        elif which("setsid"):
            # setsid detaches into a new session; nohup + a keep-alive guards
            # the WSL idle-suspend race when systemd-run is unavailable.
            launch = ["setsid", "nohup"] + launch
        proc = spawn(launch, cwd=str(cwd), start_new_session=True)

    pid = proc.pid
    start_time = None
    if kernel_start_time_fn is not None:
        try:
            start_time = kernel_start_time_fn(pid, platform=platform)
        except Exception:  # noqa: BLE001 — best-effort; start_time stays None
            start_time = None
    return {"pid": pid, "start_time": start_time}


def run_transient_build(
    cmd,
    *,
    cwd,
    spawn=None,
    wait=None,
    platform=None,
    which=None,
    kernel_start_time_fn=None,
):
    """Run a TRANSIENT long build under the M3.2 Transient Build contract; return
    ``{"exit_code": int, "stdout": str, "pid": int, "start_time": float | None}``.

    One of LD5's two supervisory contracts over the single ``spawn_detached``
    primitive. The build is spawned **detached** ONLY to survive a feature-cycle
    subagent boundary's process-tree reaping — but unlike the Persistent Service
    contract (``ensure_runtime``), this contract:

      - **synchronously AWAITS** the build's conclusion (gathering stdout for
        telemetry), then returns the exit code, and
      - does **NOT** write ``.runtime.lock.json`` and does **NOT** leave the
        process behind for a later cycle to re-attach to.

    Atomic Artifact Promotion (Phase 4 / M5 Detect) is composed AROUND this — it
    is deliberately kept OUT of ``run_transient_build`` itself, so this function
    stays a pure spawn-detached-and-await primitive.

    Determinism / injection (keeps ``--test`` hermetic):
      - ``spawn`` / ``platform`` / ``which`` / ``kernel_start_time_fn`` — passed
        straight through to ``spawn_detached`` (see its docstring).
      - ``wait`` — callable(proc) -> ``(exit_code: int, stdout: str)``. Awaits the
        spawned process and returns its result. Default: a real awaiter that
        ``proc.communicate()``-style waits and reads captured stdout.
    """
    spawned = spawn_detached(
        cmd,
        cwd=cwd,
        spawn=spawn,
        platform=platform,
        which=which,
        kernel_start_time_fn=kernel_start_time_fn,
    )

    if wait is None:
        wait = _default_build_wait

    # NOTE: spawn_detached returns {"pid", "start_time"} (NOT the Popen handle),
    # so the default awaiter re-attaches by PID. Tests ALWAYS inject ``wait``
    # (hermetic), so the default path is exercised only in production where a
    # real awaiter is supplied by the caller's config; we pass the spawn result
    # dict through so an injected awaiter can use the pid.
    exit_code, stdout = wait(spawned)

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "pid": spawned.get("pid"),
        "start_time": spawned.get("start_time"),
    }


def _default_build_wait(spawned):
    """Default production awaiter for ``run_transient_build``: block on the
    detached child by PID and return ``(exit_code, stdout)``.

    Tests inject ``wait`` so this is exercised only in production. spawn_detached
    returns a ``{pid, start_time}`` dict (not the Popen handle, which would be
    torn down with the orchestrator turn if held), so the default awaiter polls
    the PID via ``os.waitpid`` where the child is a direct child, falling back to
    a best-effort liveness poll otherwise. stdout capture in the no-handle case is
    best-effort; production callers that need full stdout telemetry inject a
    ``wait`` that owns the pipe.
    """
    pid = spawned.get("pid")
    if pid is None:
        return (None, "")
    try:
        _, status = os.waitpid(int(pid), 0)
        # POSIX exit-status decode; on Windows os.waitpid returns the exit code
        # shifted, so normalize via os.waitstatus_to_exitcode when available.
        if hasattr(os, "waitstatus_to_exitcode"):
            return (os.waitstatus_to_exitcode(status), "")
        return (status, "")
    except (ChildProcessError, OSError, ValueError):
        # Not a direct child (detached) or already reaped — best-effort poll.
        return (None, "")


def promote_artifact_atomically(
    staging_dir,
    final_dir,
    *,
    exit_code,
    replace=None,
):
    """Atomically promote a staging build artifact into its production path —
    ONLY on a clean build exit. Returns ``{"promoted": bool, "reason": str}``.

    The detect-half of LD4 (SPEC M5 Detect / Atomic Artifact Promotion). It is
    deliberately composed AROUND ``run_transient_build`` (NOT folded inside it),
    so the build target writes into ``staging_dir`` and this function swaps it
    into ``final_dir`` in a SINGLE atomic ``os.replace`` rename — atomic on NTFS
    (``MoveFileEx``) and POSIX (``rename``) — but ONLY when ``exit_code == 0``.

    A non-zero ``exit_code`` (a failed or torn-mid-flight build) is the
    load-bearing safety case: ``replace`` is NEVER called, so the production
    artifact at ``final_dir`` is left byte-for-byte untouched and the partial
    output stays quarantined in ``staging_dir``. A torn build is therefore
    mathematically harmless to production.

    Atomicity contract: promotion is a single ``os.replace`` (rename), never a
    copy-then-delete. Tests inject ``replace`` and assert it is the only mutation
    + called staging→final exactly once.

    Args:
        staging_dir: path the build wrote into (``target/release_staging``).
        final_dir: the production artifact path (``target/release``).
        exit_code: the build's exit code. Promotion happens iff this is 0.
        replace: injectable ``callable(src, dst)`` performing the atomic rename
            (default: ``os.replace``). Hermetic tests inject a spy.

    Returns:
        ``{"promoted": True}`` on a clean-exit promotion, or
        ``{"promoted": False, "reason": <str>}`` when promotion was withheld
        (non-zero exit) or the rename failed (best-effort — a rename error never
        raises; it returns ``promoted: False`` with the error reason).
    """
    if replace is None:
        replace = os.replace

    if exit_code != 0:
        return {
            "promoted": False,
            "reason": (
                f"build exit_code={exit_code} (non-zero) — production artifact "
                "left untouched, partial output quarantined in staging"
            ),
        }

    try:
        replace(staging_dir, final_dir)
    except OSError as exc:  # noqa: BLE001
        # A rename failure must not crash the promotion caller — report it as a
        # non-promotion so the production artifact is treated as unchanged.
        return {
            "promoted": False,
            "reason": f"atomic replace failed: {exc!r}",
        }
    return {"promoted": True}


def reconcile_cycle_begin_git_consistency(
    repo_root,
    *,
    boot_stamp,
    staging_dir=None,
    lock_mtime=None,
    remove=None,
    git_clean=None,
):
    """At --cycle-begin, neutralize a torn-build uncommitted delta left by a
    PREVIOUS torn cycle: a pre-boot ``.git/index.lock`` ⇒ remove it and
    ``git clean -fdx`` the staging dir. Returns a reconciliation record.

    The git-consistency detect-half of LD4 (SPEC M5 Detect). The discriminator
    is the lock's modification time vs ``boot_stamp`` (the orchestrator/run-marker
    boot epoch): a lock OLDER than the boot stamp was left by a torn op that ran
    BEFORE this run booted, so it is safe to clear; a lock NEWER than the boot
    stamp is a LIVE in-flight git op of the current run and is PRESERVED (never
    clobber a live lock).

    Best-effort + FAIL-OPEN (consistent with lazy-cycle-containment): a non-git
    tree, no lock, an unreadable mtime, or a git/remove error all degrade to a
    no-op and NEVER raise — the --cycle-begin marker write must always proceed.

    Crucially this COMPOSES with the --cycle-end friction detector rather than
    duplicating it: it makes NO commits and never touches the run marker, so HEAD
    and the run identity are unchanged. detect_cycle_bracket_friction therefore
    sees zero advanced commits and an intact run identity — a reconciled delta
    cannot false-trip ``unexpected-commits`` / ``cycle-bracket-break``.

    Args:
        repo_root: the repo whose ``.git/index.lock`` is examined.
        boot_stamp: the orchestrator/run boot epoch float (e.g. the run marker's
            ``started_at`` parsed to epoch). A lock with mtime < this is stale.
            None disables the staleness comparison → no removal (fail-safe: a
            missing boot stamp must not clobber any lock).
        staging_dir: the build staging dir to ``git clean -fdx`` when a stale lock
            is reconciled. None → skip the clean (lock removal still happens).
        lock_mtime: injectable lock mtime epoch float (hermetic tests / overriding
            the on-disk stat). None → stat the lock file.
        remove: injectable ``callable(path)`` removing the lock (default os.remove).
        git_clean: injectable ``callable(repo_root, staging_dir) -> bool`` running
            the staging clean (default: a real ``git clean -fdx <staging>``).

    Returns:
        ``{"reconciled": bool, "removed_lock": bool, "staging_cleaned": bool,
        "reason": str}``. ``reconciled`` is True iff a stale lock was removed.
    """
    result = {
        "reconciled": False,
        "removed_lock": False,
        "staging_cleaned": False,
        "reason": "",
    }
    try:
        root = Path(repo_root)
        git_dir = root / ".git"
        # Non-git tree (no .git dir/file) → fail-open no-op.
        if not git_dir.exists():
            result["reason"] = "not a git tree — no-op"
            return result

        lock_path = git_dir / "index.lock"
        if not lock_path.exists():
            result["reason"] = "no index.lock — no-op"
            return result

        # Resolve the lock's mtime (injectable for hermetic tests).
        if lock_mtime is None:
            try:
                lock_mtime = lock_path.stat().st_mtime
            except OSError as exc:
                result["reason"] = f"could not stat index.lock: {exc!r} — no-op"
                return result

        # A missing boot stamp must NOT clobber a lock (fail-safe).
        if boot_stamp is None:
            result["reason"] = "no boot stamp — lock preserved"
            return result

        # Fresh/own lock (mtime >= boot stamp) → a live git op; PRESERVE it.
        if lock_mtime >= boot_stamp:
            result["reason"] = (
                f"fresh lock (mtime={lock_mtime} >= boot_stamp={boot_stamp}) — "
                "live git op, preserved"
            )
            return result

        # Stale pre-boot lock → remove it.
        if remove is None:
            remove = os.remove
        try:
            remove(str(lock_path))
            result["removed_lock"] = True
            result["reconciled"] = True
        except OSError as exc:
            result["reason"] = f"stale lock removal failed: {exc!r} — no-op"
            return result

        # git clean -fdx the staging dir (best-effort).
        if staging_dir is not None:
            if git_clean is None:
                git_clean = _default_git_clean_staging
            try:
                cleaned = git_clean(root, staging_dir)
                result["staging_cleaned"] = bool(cleaned)
            except Exception as exc:  # noqa: BLE001
                # Lock removal already succeeded; a clean failure is non-fatal.
                result["reason"] = (
                    f"stale lock removed; staging clean failed: {exc!r}"
                )
                return result

        result["reason"] = "stale pre-boot index.lock reconciled"
        return result
    except Exception as exc:  # noqa: BLE001
        # FAIL-OPEN: any unexpected error degrades to a no-op record.
        result["reason"] = f"reconciliation error (fail-open): {exc!r}"
        return result


def _default_git_clean_staging(repo_root: Path, staging_dir: str) -> bool:
    """Default production staging cleaner: ``git clean -fdx <staging_dir>``.

    Best-effort — returns True on a clean exit, False otherwise; never raises
    (the caller wraps it, but keep this defensive too)."""
    try:
        proc = _git(repo_root, "clean", "-fdx", str(staging_dir))
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def kernel_start_time(
    pid,
    *,
    platform=None,
    read_stat=None,
    get_process_times=None,
    boot_time=None,
    clk_tck=None,
):
    """Return the kernel-reported absolute start time of ``pid`` as a Unix epoch
    float, or ``None`` on any error (best-effort, NEVER raises).

    The temporal-identity half of LD1 — the PID-reuse defense. A reused PID held
    by a foreign process reports a DIFFERENT start_time, so ``verify_runtime_ownership``
    can reject it. ``None`` flows cleanly into Phase 2's DEAD/HIJACKED classification.

    Extraction (stdlib-only, SPEC M1 / LD6):
      - **Windows** — ``ctypes`` → ``kernel32.GetProcessTimes`` returns a
        creation FILETIME (100ns intervals since 1601-01-01); converted to a
        Unix epoch float.
      - **POSIX/WSL** — ``/proc/[pid]/stat`` field 22 (``starttime``, in clock
        ticks since boot) → epoch via ``boot_time + ticks / SC_CLK_TCK``.

    Injection (hermetic ``--test``):
      - ``read_stat`` — callable(pid) -> the raw ``/proc/[pid]/stat`` line.
      - ``get_process_times`` — callable(pid) -> creation FILETIME int.
      - ``boot_time`` / ``clk_tck`` — POSIX constants (default: read live).
    """
    if platform is None:
        platform = sys.platform
    is_windows = str(platform).startswith("win")

    try:
        if is_windows:
            if get_process_times is None:
                get_process_times = _win_process_creation_filetime
            filetime = get_process_times(pid)
            if filetime is None:
                return None
            return (filetime - _FILETIME_EPOCH_OFFSET) / _FILETIME_TICKS_PER_SEC

        # POSIX/WSL: /proc/[pid]/stat field 22 (starttime, clock ticks).
        if read_stat is None:
            def read_stat(p):
                return Path(f"/proc/{p}/stat").read_text(encoding="utf-8", errors="replace")
        if clk_tck is None:
            clk_tck = os.sysconf("SC_CLK_TCK")
        if boot_time is None:
            boot_time = _posix_boot_time()
        if boot_time is None or not clk_tck:
            return None

        raw = read_stat(pid)
        # Field 2 (comm) may contain spaces/parens; it is wrapped in (...).
        # Split off everything through the LAST ')' so the remaining fields are
        # whitespace-delimitable. Field 22 (starttime) is index 19 of the tail
        # (tail starts at field 3 = state).
        rparen = raw.rfind(")")
        if rparen < 0:
            return None
        tail = raw[rparen + 1:].split()
        # tail[0] is field 3 (state); field 22 is tail index 19.
        if len(tail) < 20:
            return None
        ticks = int(tail[19])
        return boot_time + (ticks / clk_tck)
    except Exception:  # noqa: BLE001 — best-effort, never raises
        return None


def _win_process_creation_filetime(pid):
    """Default Windows creation-FILETIME extractor via ctypes →
    kernel32.GetProcessTimes. Returns the creation FILETIME int, or None on any
    error. Only invoked when ``kernel_start_time`` is called WITHOUT an injected
    ``get_process_times`` (production); tests inject."""
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_t = wintypes.FILETIME()
            kernel_t = wintypes.FILETIME()
            user_t = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_t),
                ctypes.byref(kernel_t), ctypes.byref(user_t),
            )
            if not ok:
                return None
            return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return None


def _posix_boot_time():
    """Read system boot time (Unix epoch sec) from /proc/stat ``btime``.
    Returns None on any error."""
    try:
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except Exception:  # noqa: BLE001
        return None
    return None


def _runtime_lock_path(repo_root, config=None):
    """Resolve the `.runtime.lock.json` path at the repo root from the config
    dict's ``lock_filename`` (parameterized, NOT a hard-coded literal)."""
    cfg = dict(_ENSURE_RUNTIME_DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    return Path(repo_root) / cfg["lock_filename"]


def write_runtime_lock(
    repo_root,
    *,
    pid,
    start_time,
    port,
    artifact_hash,
    controller_session_id,
    config=None,
):
    """Atomically write the `.runtime.lock.json` ownership sentinel (LD1) at the
    repo root with the five LD1 fields.

    Uses the shared ``_atomic_write`` (temp file in the same dir + ``os.replace``)
    so a mid-write failure never leaves a partial production sentinel — the same
    atomic-write discipline as the cycle marker / tally writers already in tree.
    The lock filename comes from ``config['lock_filename']`` (default config),
    never a literal in the flow.
    """
    lock = {
        "controller_session_id": controller_session_id,
        "pid": pid,
        "start_time": start_time,
        "port": port,
        "artifact_hash": artifact_hash,
    }
    path = _runtime_lock_path(repo_root, config)
    _atomic_write(path, json.dumps(lock, indent=2) + "\n")


def read_runtime_lock(repo_root, *, config=None):
    """Best-effort read of the `.runtime.lock.json` sentinel → dict, or ``None``
    on missing/corrupt (NEVER raises)."""
    path = _runtime_lock_path(repo_root, config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Boot-spawn stamp (ensure-runtime-recovery-starves-cold-compile-round-2). A tiny
# per-repo sidecar to `.runtime.lock.json` recording WHEN the last `dev:restart`
# boot was spawned. It is the persistence behind the `_BOOT_SPAWN_GRACE_SECONDS`
# time-window grace: the production `boot_alive()` reads it to answer "is a cold
# boot in progress?" ROBUSTLY — independent of the short-lived npm/cmd wrapper
# `Popen` handle whose `.poll()` exits early on Windows (the Round-32 false-green).
#
# Why a FILE (not just an in-process holder): the murder site is the bounded
# `_recover_runtime` loop INSIDE a SINGLE `ensure_runtime` call — its first
# `restart()` legitimately spawns the compile, and every SUBSEQUENT loop iteration
# must see "a boot is in progress" to STOP re-killing it. The stamp written by that
# first `restart()` is read back by `boot_alive()` later in the SAME call (and by a
# follow-up `--ensure-runtime` invocation), so the grace survives both the wrapper
# exiting AND the process boundary between orchestrator calls.
# ---------------------------------------------------------------------------

_BOOT_STAMP_FILENAME = ".runtime.boot.json"


def _boot_stamp_path(repo_root) -> Path:
    """Resolve the boot-spawn stamp path at the repo root (sibling of the runtime
    lock). A fixed filename — the stamp is repo-scoped, never port-/config-scoped."""
    return Path(repo_root) / _BOOT_STAMP_FILENAME


def write_boot_stamp(repo_root, *, spawn_ts: float) -> None:
    """Atomically record the boot-spawn epoch (best-effort, never raises). Written
    by the production `restart()` closure the instant it spawns `dev:restart`."""
    try:
        _atomic_write(
            _boot_stamp_path(repo_root),
            json.dumps({"spawn_ts": float(spawn_ts)}, indent=2) + "\n",
        )
    except Exception:  # noqa: BLE001 — a stamp-write failure must never abort a boot
        pass


def read_boot_stamp(repo_root) -> float | None:
    """Best-effort read of the boot-spawn epoch → float, or ``None`` on
    missing/corrupt (NEVER raises)."""
    try:
        data = json.loads(_boot_stamp_path(repo_root).read_text(encoding="utf-8"))
        ts = data.get("spawn_ts") if isinstance(data, dict) else None
        return float(ts) if ts is not None else None
    except (OSError, ValueError, TypeError):
        return None


def boot_recently_spawned(
    repo_root, *, now: float | None = None,
    grace_seconds: float = _BOOT_SPAWN_GRACE_SECONDS,
) -> bool:
    """True iff a `dev:restart` boot was spawned within ``grace_seconds`` of ``now``
    (the time-window grace). The Windows-robust cold-boot-in-progress detector: a
    fresh stamp means a compile is genuinely underway regardless of whether the
    short-lived npm/cmd wrapper `Popen` has already exited. Ages out past the
    cold-compile ceiling so a stuck/dead host is never patient-waited forever."""
    stamp = read_boot_stamp(repo_root)
    if stamp is None:
        return False
    current = time.time() if now is None else now
    return (current - stamp) < grace_seconds


def verify_runtime_ownership(lock, *, live_session_id, kernel_start_time_fn):
    """Return ``True`` iff the recorded runtime is provably owned by the live
    controller (LD1) — the verifiability predicate.

    ``True`` iff BOTH:
      - the recorded ``start_time`` matches the kernel-reported start_time for
        ``lock['pid']`` (defeats PID reuse — a foreign process holding a reused
        PID reports a different start_time, and a dead PID reports ``None``), AND
      - ``lock['controller_session_id'] == live_session_id`` (defeats a previous
        crashed controller's leftover runtime).

    "200 on /health" is NOT proof of ownership — only this ``(start_time,
    controller_session_id)`` match is. ``kernel_start_time_fn`` is injected
    (callable(pid, *, platform) -> float|None) so the predicate is hermetic.
    """
    if not isinstance(lock, dict):
        return False
    if lock.get("controller_session_id") != live_session_id:
        return False
    recorded = lock.get("start_time")
    if recorded is None:
        return False
    try:
        live = kernel_start_time_fn(lock.get("pid"))
    except TypeError:
        # Tolerate a fn that requires the keyword (production binds platform).
        live = kernel_start_time_fn(lock.get("pid"), platform=sys.platform)
    except Exception:  # noqa: BLE001 — best-effort
        return False
    if live is None:
        return False
    return live == recorded


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


def migrate_legacy_state_dir(base: Path) -> bool:
    """Move legacy un-keyed base-dir run state into the per-repo keyed subdir.

    Runs at most once per process (the ``_legacy_state_migrated`` guard).
    Best-effort and idempotent:
      - No legacy ``lazy-run-marker.json`` in ``base`` → nothing to migrate
        (fresh machine / already migrated) → returns False.
      - A legacy marker whose ``repo_root`` cannot be resolved → the marker is
        treated as stale and removed; no subdir is created.
      - Otherwise the five run-scoped files are moved into
        ``base/<repo_key(marker.repo_root)>/`` (a file already present at the
        target wins; the legacy copy is dropped).

    NEVER called for a LAZY_STATE_DIR-overridden dir (that path returns the
    override verbatim before reaching here), so hermetic tests are untouched.
    """
    global _legacy_state_migrated
    if _legacy_state_migrated:
        return False
    _legacy_state_migrated = True
    legacy_marker = base / _MARKER_FILENAME
    if not legacy_marker.exists():
        return False
    try:
        m = json.loads(legacy_marker.read_text(encoding="utf-8"))
        rr = m.get("repo_root") if isinstance(m, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        rr = None
    if not rr:
        # Unresolvable owner — the marker belongs to no readable repo; drop it.
        try:
            legacy_marker.unlink()
        except OSError:
            pass
        return False
    target = base / repo_key(rr)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    moved = False
    for name in _LEGACY_STATE_FILENAMES:
        src = base / name
        if not (src.exists() and src.is_file()):
            continue
        dst = target / name
        try:
            if dst.exists():
                src.unlink()  # target already populated — drop the legacy copy
            else:
                src.replace(dst)
            moved = True
        except OSError:
            pass
    return moved


def claude_state_dir(create: bool = True) -> Path:
    """Return the Claude state directory, optionally creating it on demand.

    Default resolution: ``~/.claude/state/``.

    Override: set the ``LAZY_STATE_DIR`` environment variable to any absolute
    path — the function will use that directory instead of the default.  This
    env-var override exists for two purposes:
      1. **Hermetic unit tests** (test_lazy_core.py): each test that touches
         the state dir sets ``LAZY_STATE_DIR`` to a ``tempfile.TemporaryDirectory``
         and clears it afterward, so tests never touch ``~/.claude/state/``.
      2. **Hook pipe-tests** (Phase 2): the inject/validate hooks can point at a
         fixture state dir via env var for scriptable, reproducible pipe-test runs
         on both Windows (git-bash) and WSL without affecting the live session.

    Args:
        create: when True (default) create the directory if absent — used by
                write paths (write_run_marker, register_emission, etc.).
                Pass ``create=False`` from read-only paths (read_run_marker,
                _load_registry, lookup_emission, delete_run_marker, etc.) so a
                probe that finds no marker never creates ``~/.claude/state/``
                as a side-effect.  A missing directory on a read path simply
                means "no state" — callers treat a missing path the same as an
                empty result.
    """
    override = os.environ.get("LAZY_STATE_DIR")
    if override:
        # Hermetic override: return the exact dir (tests + hook pipe-tests).
        # No per-repo keying, no migration — preserves byte-for-byte path
        # semantics for every test that sets LAZY_STATE_DIR.
        d = Path(override)
    else:
        # Production: scope the state dir per repo so concurrent runs in
        # different repos are isolated.  Migrate any legacy un-keyed base-dir
        # state into the keyed subdir once, then resolve the active repo's dir.
        base = Path.home() / ".claude" / "state"
        migrate_legacy_state_dir(base)
        d = base / repo_key(active_repo_root())
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


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


# Frontmatter flag a skill declares to state "my contract orchestrates
# sub-subagents" (e.g. /execute-plan's test-agent/impl-agent split,
# /spec-phases' phase-writer launch, /spec's Explore fan-outs). The cycle
# marker copies this capability at --cycle-begin so the dispatch guard can
# honor the workstation sub-subagent exemption WITHOUT a hardcoded skill list
# (dispatch-guard-denies-workstation-subsubagent-split, decision 4 Round-11
# amendment: the discriminator MUST be a general skill-declared predicate —
# an allow-list re-opens the gap for every new sub-subagent-model skill).
_SUBAGENT_MODEL_FLAG_RE = re.compile(
    r"^subagent-model:\s*true\s*$", re.IGNORECASE | re.MULTILINE
)


def skill_declares_subagent_model(
    sub_skill: str | None,
    *,
    repo_root: "str | Path | None" = None,
) -> bool:
    """True iff *sub_skill*'s SKILL.md frontmatter declares ``subagent-model: true``.

    The predicate source of truth for the guard's workstation sub-subagent
    exemption (decision 4). Resolution order:

      1. Repo-scoped skill: ``<repo_root>/.claude/skills/<name>/SKILL.md``
         (when *repo_root* is provided) — covers repo-local skills like
         AlgoBooth's mcp-test family.
      2. User-level skill: ``<this module's parent.parent>/skills/<name>/SKILL.md``
         — resolves to ``~/.claude/skills/`` for the live copy and
         ``<claude-config>/user/skills/`` for the repo copy (the same
         module-path trick _default_cycle_template_dir uses).

    Only the leading YAML frontmatter block (between the first two ``---``
    lines) is consulted, so prose mentioning the flag never false-positives.

    FAIL-CLOSED: a falsy/pseudo (``__*``) sub_skill, a missing SKILL.md, an
    unreadable file, or an absent flag all return False — the exemption never
    fires on uncertainty (the pre-fix deny is the safe degradation).

    Args:
        sub_skill: dispatched skill name (leading "/" tolerated); None → False.
        repo_root: optional repo root for the repo-scoped lookup.

    Returns:
        True only when the frontmatter flag is explicitly ``true``.
    """
    try:
        if not sub_skill or sub_skill.startswith("__"):
            return False
        norm = sub_skill[1:] if sub_skill.startswith("/") else sub_skill
        # Refuse path-traversal shapes outright (the name is a directory key).
        if not re.fullmatch(r"[A-Za-z0-9._-]+", norm):
            return False
        candidates: list[Path] = []
        if repo_root:
            candidates.append(
                Path(repo_root) / ".claude" / "skills" / norm / "SKILL.md"
            )
        candidates.append(
            Path(__file__).resolve().parent.parent / "skills" / norm / "SKILL.md"
        )
        for skill_md in candidates:
            try:
                if not skill_md.is_file():
                    continue
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            # Extract the leading frontmatter block only.
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end == -1:
                continue
            frontmatter = text[3:end]
            if _SUBAGENT_MODEL_FLAG_RE.search(frontmatter):
                return True
        return False
    except Exception:  # noqa: BLE001
        return False


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


# ---------------------------------------------------------------------------
# Process-friction detector (hardening-blind-to-process-friction Phase 2 / D1)
#
# The conservative expected-commit budget per dispatched sub_skill. Most cycles
# commit 0–1 times (one atomic gate+commit per plan-part / batch completion);
# anything beyond the budget is "unexpected commits" hardening signal. The budget
# is deliberately generous (defensible default = 1 for every sub_skill) so the
# detector never false-positives on a legitimate single-commit cycle — only a
# genuinely runaway cycle that strings several commits trips D1(b). A sub_skill
# absent from the map falls back to the default. (D1-out: no runtime-death
# heuristic — both signals are deterministic on-disk facts.)
# ---------------------------------------------------------------------------
_CYCLE_COMMIT_BUDGET_DEFAULT = 1
# The uniform commit ceiling granted to a multi-commit dispatch identity. Every
# multi-commit skill historically used the SAME number (3) — the per-skill budget
# never varied, so the budget is a binary "single-commit (default 1) vs.
# multi-commit (this ceiling)" decision keyed on registry membership below.
_CYCLE_COMMIT_MULTI = 3

# ---------------------------------------------------------------------------
# Per-skill ceiling OVERRIDE (commit-budget MAGNITUDE, not membership).
#
# `_MULTI_COMMIT_DISPATCH_SKILLS` above answers WHICH skills are multi-commit
# (the membership SSOT). This map answers HOW MANY commits a specific skill's
# WORST-CASE cadence legitimately makes, for the cases where the uniform
# `_CYCLE_COMMIT_MULTI` ceiling of 3 is too low for a skill's own documented
# cadence. A skill ABSENT from this map keeps the uniform ceiling — so this is
# additive and never lowers any skill's budget.
#
# `mcp-test` (4): the Step-9 /mcp-test validation cycle's documented worst-case
# cadence exceeds the original Round-23 "self-heal + sentinel/PHASES-reconcile"
# 2-commit estimate. A real cycle (2026-06-26 `pattern-abstractions`,
# begin_head_sha=0dd654ae39ce, budget=3, HEAD advanced 4 commits) committed FOUR
# legitimate, non-overlapping mcp-test-owned units, ALL within the mcp-test SKILL
# Step 3.4/Step 5 reconcile surface:
#   1. `4b9b3ddaa` self-heal (scenario `unlock_master_editor` fix + verdict/artifact)
#      + Phase-5 Runtime-Verification tick;
#   2. `0db5974e4` PHASES reconcile — tick Phase 1-4 RVs covered by the Phase-5 run;
#   3. `7b119b512` PHASES top-level Complete;
#   4. `d744204da` correct the engine-written VALIDATED.md schema.
# The PHASES reconcile (Step 5.2) legitimately fans out into sub-phase RV ticks +
# the top-level Complete flip (two commits), and the engine-written sentinel may
# need a schema correction — so the honest worst case is self-heal + 2-part
# reconcile + sentinel correction = 4. Budget 3 was exactly one short. Raising the
# SHARED `_CYCLE_COMMIT_MULTI` to 4 would loosen the runaway ceiling for `spec`,
# `write-plan`, `plan-feature`, etc. — a per-skill override keeps everyone else at
# 3 (no gate weakening) and gives only `mcp-test` its honest ceiling. The runaway
# ceiling for `mcp-test` itself is unchanged in KIND — a cycle beyond its declared
# cadence (>4) STILL trips `unexpected-commits`.
#
# NOTE — distinct from the `adhoc-derive-multi-commit-budget-from-dispatch-sites`
# spin-off (harden Round 38): that bug targets MEMBERSHIP derivation (which skills
# are multi-commit) and explicitly scopes OUT "any change to the friction-detection
# thresholds or the runaway ceiling". This map is the orthogonal MAGNITUDE
# dimension (how many commits a member legitimately makes) — see the over-fit
# spin-off for the magnitude class below.
# ---------------------------------------------------------------------------
_MULTI_COMMIT_CEILING_OVERRIDE: dict[str, int] = {
    "mcp-test": 4,
}

# ---------------------------------------------------------------------------
# SSOT: the multi-commit dispatch-skill registry.
#
# `_MULTI_COMMIT_DISPATCH_SKILLS` names EVERY dispatch identity whose cycle
# legitimately commits MORE THAN ONCE. It is the single source of truth the
# per-sub_skill commit budget DERIVES from (see `detect_cycle_bracket_friction`
# branch (3)): a name in this set ⇒ `_CYCLE_COMMIT_MULTI`; any other name ⇒
# `_CYCLE_COMMIT_BUDGET_DEFAULT` (1).
#
# These are the SAME string identities the dispatch sites already pass — the
# `bug-state.py` `SKILL_*` constants (`SKILL_EXECUTE_PLAN`, `SKILL_MCP_TEST`,
# `SKILL_WRITE_PLAN`, `SKILL_PLAN_BUG`, `SKILL_MARK_FIXED`, … `:159-166`) and the
# `lazy-state.py` bare-literal `sub_skill="..."` dispatch sites — so this set is
# the natural SSOT for BOTH pipelines (the shared `lazy_core` helper serves both;
# no coupled-pair mirror).
#
# ADDING A NEW MULTI-COMMIT DISPATCH SKILL means adding its identity HERE,
# co-located with the dispatch-skill set — NEVER a separate hand-maintained budget
# row. This structural derivation replaces the prior reactive literal
# `_CYCLE_COMMIT_BUDGET` table, whose five dated per-row provenance comments each
# recorded a production `unexpected-commits` false-positive that was patched AFTER
# the fact (Round 15 `execute-plan`; Rounds 16/17 the `__mark_complete__` /
# `__mark_fixed__` pseudo-skills; a later round `mcp-test`; 2026-06-22
# `write-plan` / `plan-feature` / `plan-bug`). Membership here closes that
# missing-row CLASS: a newly-dispatched multi-commit skill can no longer silently
# default to budget 1.
#
# The forward-advancing terminal PSEUDO-skills (`__mark_complete__` /
# `__mark_fixed__`) are members: they dispatch no Agent subagent, but they ARE
# dispatch identities the friction detector keys on, and their completion cycle
# legitimately commits more than once (receipt+flip plus a Gate-1
# corrective-coverage scenario commit).
# ---------------------------------------------------------------------------
_MULTI_COMMIT_DISPATCH_SKILLS: frozenset[str] = frozenset({
    # Multi-batch plan execution commits once per batch.
    "execute-plan",
    "retro-feature",
    # The Step-9 /mcp-test validation cycle commits the audited mechanics-only
    # self-heal separately from the terminal sentinel + PHASES reconcile.
    "mcp-test",
    # Planning dispatch: /plan-feature runs /spec-phases (commits PHASES.md) THEN
    # /write-plan, which may emit a multi-part plan series (one commit per part);
    # /plan-bug is the bug-pipeline analog.
    "write-plan",
    "plan-feature",
    "plan-bug",
    # Spec authoring dispatch (2026-06-25 recurrence: begin_head_sha=641e96163faa,
    # sub_skill='spec', budget=1, 2 commits). /spec is multi-phase and a single
    # dispatched cycle legitimately commits more than once — most acutely a STUB
    # feature's Phase 1, which (a) locks in the baseline SPEC over the
    # auto-generated stub, then (b) retires the stub markers and advances to
    # needs-research (the exact two commits that tripped: `9def1bfab docs(...):
    # /spec Phase 1 — lock in baseline over auto-generated stub` + `a96d51df4
    # docs(...): retire stub markers — baseline locked, advance to needs-research`).
    # /spec-bug is the bug-pipeline investigation analog (evidence-gathering +
    # investigation-spec commits), added alongside per the Round 31 plan-feature/
    # plan-bug precedent of covering the bug analog at the same commit.
    "spec",
    "spec-bug",
    # Forward-advancing terminal pseudo-skills (receipt+flip + corrective-coverage).
    "__mark_complete__",
    "__mark_fixed__",
})

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
    now: float | None = None,
) -> dict | None:
    """Detect process-friction at --cycle-end: a torn cycle bracket or unexpected
    commits (hardening-blind-to-process-friction Phase 2, Locked Decision D1).

    Pure function — NO I/O. The caller (--cycle-end) supplies the live values:
    the cycle marker as snapshotted at --cycle-begin, the CURRENT run identity
    and HEAD sha resolved fresh at --cycle-end, the dispatched sub_skill, and the
    number of commits HEAD advanced since ``marker['begin_head_sha']``.

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
            # Branch (3): DERIVE the budget from the `_MULTI_COMMIT_DISPATCH_SKILLS`
            # registry SSOT — membership ⇒ the multi-commit ceiling, else the
            # single-commit default. No hand-maintained literal table to keep in
            # sync (closes the recurring missing-row defect class). A member's
            # ceiling is the uniform `_CYCLE_COMMIT_MULTI` UNLESS it declares a
            # higher worst-case cadence in `_MULTI_COMMIT_CEILING_OVERRIDE` (the
            # MAGNITUDE dimension — e.g. mcp-test's self-heal + 2-part reconcile +
            # sentinel correction = 4); a non-member always gets the default.
            ss = sub_skill or ""
            budget = (
                _MULTI_COMMIT_CEILING_OVERRIDE.get(ss, _CYCLE_COMMIT_MULTI)
                if ss in _MULTI_COMMIT_DISPATCH_SKILLS
                else _CYCLE_COMMIT_BUDGET_DEFAULT
            )
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
# Prompt-registry API
# ---------------------------------------------------------------------------

def normalize_prompt_for_hash(prompt: str) -> str:
    """Normalize a prompt before hashing so cosmetic copy artifacts cannot defeat
    the registry match while semantic edits still do.

    Five transforms, applied in order (Phase 7 WU-7.3b widened the original
    Phase 1 pair with two more — trailing-whitespace strip + Unicode NFC; leg 5
    added by F2b / lazy-validation-readiness Phase 2):
      1. CRLF (\\r\\n) → LF (\\n)
      2. Lone CR (\\r not followed by \\n) → LF (\\n)
      3. Per-line trailing-whitespace strip (rstrip each line) — a copy/paste
         that picks up trailing spaces or tabs on some lines must not change the
         hash (observed in session 2f6f27dc as a transcription-slip deny source).
      4. Unicode NFC normalization — a decomposed (NFD) variant of an accented
         character (e.g. an editor that emits combining marks) must hash equal to
         the composed (NFC) form.
      5. [F2b / lazy-validation-readiness] Fold Unicode characters the model trivially
         substitutes when retyping a script-emitted prompt:
           - em-dash U+2014, en-dash U+2013, horizontal bar U+2015,
             figure dash U+2012  →  hyphen-minus '-'
           - left single curly quote U+2018, right single curly quote U+2019  →  '
           - left double curly quote U+201C, right double curly quote U+201D  →  "
           - non-breaking space U+00A0, narrow NBSP U+202F  →  regular space
         Applied AFTER NFC so code-point normalization happens first.  These are
         purely cosmetic punctuation/space variants; a genuine word change still
         alters the hash (the fold cannot collapse distinct words).  This makes an
         em-dash/curly-quote/NBSP slip on an otherwise-verbatim emitted prompt
         hash-equal → ALLOW without any guard change.  It also improves the F1b
         auto-readmit near-match (shares this normalize) for free.

    This ensures that a prompt registered on Windows (with CRLF line endings,
    trailing whitespace, or NFD text) produces the same sha256 as the same prompt
    re-typed clean, so Windows/WSL round-trips and editor quirks cannot defeat the
    registry match.  A genuine word change still alters the hash (the deny still
    fires for a real edit).  The SPEC requires CRLF normalization in §Validate-deny
    step 1; WU-7.3b adds the trailing-whitespace + NFC legs; F2b / lazy-validation-
    readiness Phase 2 adds the dash/quote/NBSP folding leg.
    """
    # Step 1: collapse CRLF → LF
    normalized = prompt.replace("\r\n", "\n")
    # Step 2: replace any remaining lone CRs with LF
    normalized = normalized.replace("\r", "\n")
    # Step 3: strip trailing whitespace from each line (newlines preserved).
    # Splitting on "\n" after steps 1+2 means every line boundary is a single LF.
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    # Step 4: Unicode NFC — fold decomposed sequences into their composed form so
    # an NFD copy hashes identically to the clean NFC form.
    normalized = unicodedata.normalize("NFC", normalized)
    # Step 5 (F2b / lazy-validation-readiness): fold cosmetic Unicode punctuation/
    # space substitutes that the model trivially introduces when retyping a prompt.
    # Applied after NFC so we operate on fully-composed code points.
    # Translation table built once (str.translate is O(n) and very fast).
    normalized = normalized.translate(_NORM_FOLD_TABLE)
    return normalized


# F2b (lazy-validation-readiness Phase 2): translation table for leg 5 of
# normalize_prompt_for_hash.  Maps Unicode cosmetic-substitute code points to their
# ASCII equivalents.  Keys are Unicode code-point integers; values are the folded
# strings (str.translate allows multi-char replacements via a mapping str→str on the
# table, but for 1-to-1 folds it is more efficient to map ord→ord or ord→str).
#
# Dashes: em-dash U+2014, en-dash U+2013, horizontal bar U+2015, figure dash U+2012
#         → hyphen-minus U+002D '-'
# Single quotes: U+2018 LEFT SINGLE QUOTATION MARK, U+2019 RIGHT SINGLE QUOTATION MARK
#                → apostrophe U+0027 "'"
# Double quotes: U+201C LEFT DOUBLE QUOTATION MARK, U+201D RIGHT DOUBLE QUOTATION MARK
#                → quotation mark U+0022 '"'
# Spaces: U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE → U+0020 ' '
_NORM_FOLD_TABLE: dict = str.maketrans(
    {
        0x2014: "-",   # EM DASH
        0x2013: "-",   # EN DASH
        0x2015: "-",   # HORIZONTAL BAR
        0x2012: "-",   # FIGURE DASH
        0x2018: "'",   # LEFT SINGLE QUOTATION MARK
        0x2019: "'",   # RIGHT SINGLE QUOTATION MARK
        0x201C: '"',   # LEFT DOUBLE QUOTATION MARK
        0x201D: '"',   # RIGHT DOUBLE QUOTATION MARK
        0x00A0: " ",   # NO-BREAK SPACE
        0x202F: " ",   # NARROW NO-BREAK SPACE
    }
)


def prompt_sha256(prompt: str) -> str:
    """Return the hex sha256 of a prompt after normalizing line endings.

    Uses normalize_prompt_for_hash() before hashing so CRLF and LF variants
    of the same prompt produce identical digests.
    """
    normalized = normalize_prompt_for_hash(prompt)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_registry() -> dict:
    """Load the prompt registry from disk.  Returns ``{"entries": []}`` on any
    read/parse error (fail-open — the validate hook also fails open separately).

    Corrupt registry → start fresh so a bad write never bricks subsequent
    sessions.  The old file is left in place; the next write (via
    register_emission) will atomically replace it with a clean copy.

    Read-only path: passes ``create=False`` to ``claude_state_dir()`` so a
    registry probe never creates ``~/.claude/state/`` as a side-effect.
    """
    # Read-only — do not create the directory if absent; treat as empty.
    registry_path = claude_state_dir(create=False) / _REGISTRY_FILENAME
    if not registry_path.exists():
        return {"entries": []}
    try:
        raw = registry_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    # Corrupt / wrong shape — start fresh.
    return {"entries": []}


def registry_summary() -> str:
    """Return a short one-line summary of the prompt-registry state.

    Phase 8 WU-8.2: bound into the routed-hardening-debt ``hardening_emit_command``
    as ``--context registry_state=...`` so the dispatched hardening subagent has
    a snapshot of how many emissions are outstanding.  Read-only.

    Returns:
        ``"empty"`` when there are no entries, otherwise
        ``"<N> entries, <M> unconsumed"``.
    """
    entries = _load_registry().get("entries", [])
    if not entries:
        return "empty"
    unconsumed = sum(1 for e in entries if not e.get("consumed", False))
    return f"{len(entries)} entries, {unconsumed} unconsumed"


def consumed_emission_count(cls: str | None = None) -> int:
    """Return the number of CONSUMED registry entries — the dispatch oracle.

    The validate-deny guard calls ``consume_nonce`` on every ALLOW (one consume
    per dispatch), so this monotone-within-the-ring count is a sound "how many
    dispatches have landed" signal.  ``update_repeat_counts`` (F2) reads it twice
    around a re-read: an UNCHANGED consumed-count between two identical step
    probes means NO dispatch happened between them → the second probe is a
    re-read, not a re-attempt → hold the step counter (double-probe debounce).

    ``cls`` (loop-detector-false-positives-probes-and-cross-run-state, Residual
    gap A): when given, count ONLY consumed entries whose ``class`` field equals
    ``cls`` (e.g. ``"cycle"``) instead of every consumed entry regardless of
    class. The F1/F2 oracle in ``update_repeat_counts`` uses ``cls="cycle"`` so
    a mid-step META-class dispatch (``hardening``, ``recovery``,
    ``coherence-recovery``, ``investigation``, ``input-audit``, …) no longer
    counts as "a dispatch landed between probes" for the streak debounce — only
    a genuine forward CYCLE attempt does. Every OTHER caller (the
    forward/meta-cycle watermark machinery in ``advance_run_counters`` etc.)
    keeps calling this with no argument (``cls=None``), which is
    byte-identical to the pre-existing unfiltered count.

    Read-only: ``_load_registry`` passes ``create=False`` so a probe never
    creates the state dir as a side-effect, and returns ``{"entries": []}`` (→ 0)
    on any missing / corrupt registry.  The registry ring-cap can evict the
    oldest entries, but the debounce only compares two consecutive probes within
    one run, where eviction of a consumed entry between adjacent probes is not a
    concern (it would only *lower* the count, never spuriously raise it, so it
    can at worst fail-open into an increment — never a spurious hold).

    NON-MONOTONIC CAVEAT (Phase 2, byref-dispatch-undercounts-forward-cycles): this
    census is a LIVE count over the ring-capped registry, so once cumulative
    emissions cross ``_REGISTRY_RING_CAP`` (64) the oldest CONSUMED entries are
    evicted and this count steps DOWN.  The run-lifetime ``last_advance_consume_count``
    watermark in ``advance_run_counters`` (NOT the F2 double-probe debounce above —
    that compares only adjacent probes) is now CLAMPED against this one-time downward
    step: a watermark stranded above the live census re-arms (advances once) instead
    of no-oping forever, so ring-cap eviction can no longer permanently strand the
    forward/meta gate.  The forward-cycle COUNT itself no longer depends on this
    oracle at all (Phase 1 routed it through the consume-independent
    ``advance_forward_cycle`` state-change trigger); this caveat governs only the
    residual watermark consumers.

    Returns:
        The count of entries whose ``consumed`` flag is truthy (0 when empty),
        optionally restricted to entries whose ``class`` equals ``cls``.
    """
    entries = _load_registry().get("entries", [])
    if cls is not None:
        return sum(
            1 for e in entries
            if e.get("consumed", False) and e.get("class") == cls
        )
    return sum(1 for e in entries if e.get("consumed", False))


def _save_registry(data: dict) -> None:
    """Persist the registry dict to disk atomically."""
    registry_path = claude_state_dir() / _REGISTRY_FILENAME
    _atomic_write(registry_path, json.dumps(data, indent=2) + "\n")


def register_emission(
    prompt: str,
    cls: str,
    item_id: str | None = None,
    now: float | None = None,
) -> dict:
    """Register a prompt emission in the prompt registry.

    Each registration creates one entry in ``lazy-prompt-registry.json`` with:
      - nonce (str): unique uuid4 hex string — single-use control
      - prompt_sha256 (str): sha256 of the normalized prompt
      - prompt_norm (str): the normalize_prompt_for_hash-normalized prompt text.
        Stored verbatim (not just hashed) so the validate-deny guard can do a
        pure trailing-suffix superset match for F1b auto-readmit
        (lazy-pipeline-ergonomics Phase 1).  Registry entries are ephemeral
        (ring-cap + TTL) so storing the text is size-safe.
      - prompt_raw (str): the EXACT original prompt bytes before any normalization.
        F2a (lazy-validation-readiness Phase 3): stored so that
        resolve_emission_by_nonce() can return the EXACT original text for a
        by-reference dispatch — the guard resolves nonce → prompt_raw and returns
        it via hookSpecificOutput.updatedInput, so the spawned subagent receives
        the fully-expanded prompt without any retyping.
      - emitted_at (float): epoch timestamp of the emission
      - class (str): dispatch class tag (e.g. "cycle", "recovery", "hardening")
      - item_id (str|None): the feature/bug id for context (optional)
      - consumed (bool): False until consume_nonce() is called

    Ring cap: when the registry would exceed ``_REGISTRY_RING_CAP`` (64) entries,
    the oldest entry (lowest index, earliest emitted_at) is evicted first.  This
    keeps the registry bounded regardless of run length.

    Args:
        prompt: the dispatch prompt text (normalized before hashing)
        cls: the dispatch class tag (e.g. "cycle")
        item_id: the feature or bug id associated with this dispatch (optional)
        now: epoch float for emitted_at (injectable for hermetic tests;
             defaults to time.time())

    Returns:
        The newly created entry dict.
    """
    if now is None:
        now = time.time()

    entry: dict = {
        "nonce": uuid.uuid4().hex,
        "prompt_sha256": prompt_sha256(prompt),
        # F1b: store the normalized prompt text so the guard can prefix-match a
        # pure trailing suffix (auto-readmit) using identical normalization.
        "prompt_norm": normalize_prompt_for_hash(prompt),
        # F2a (lazy-validation-readiness Phase 3): store the EXACT original bytes
        # so resolve_emission_by_nonce() can return them verbatim for by-reference
        # dispatch — the guard copies prompt_raw into updatedInput.prompt so the
        # spawned subagent receives the fully-expanded original prompt, eliminating
        # the byte-exact-retype requirement for the orchestrator.
        "prompt_raw": prompt,
        "emitted_at": now,
        "class": cls,
        "item_id": item_id,
        "consumed": False,
    }

    data = _load_registry()
    entries: list = data["entries"]
    entries.append(entry)

    # Ring cap: evict the oldest entry (index 0) when over the cap.
    # The list is ordered by insertion time; oldest is always index 0.
    while len(entries) > _REGISTRY_RING_CAP:
        entries.pop(0)

    data["entries"] = entries
    _save_registry(data)
    return entry


def lookup_emission(
    prompt: str,
    now: float | None = None,
) -> dict | None:
    """Look up an unconsumed, fresh registry entry by prompt hash.

    Freshness has two components (belt-and-braces):
      1. Nonce + TTL: entry must be unconsumed AND within
         REGISTRY_ENTRY_TTL_SECONDS (1800 s) of ``emitted_at``.
      2. Run-start gate (when a non-stale run marker exists): additionally
         require ``emitted_at`` >= marker's ``started_at`` epoch — entries
         that were written before the current run started are never
         dispatchable even if they are within the TTL.  When no run marker is
         present this gate is skipped and only nonce+TTL semantics apply.

    Returns the first matching entry, or None when:
      - no entry with this prompt's sha256 exists, OR
      - all matching entries are consumed, beyond the TTL, OR predate the
        current run's started_at.

    Args:
        prompt: the prompt text to look up (normalized before hashing)
        now: epoch float for TTL comparison (injectable; defaults to time.time())

    Returns:
        The matching entry dict, or None.
    """
    if now is None:
        now = time.time()
    target_sha = prompt_sha256(prompt)

    # Compute the run-start epoch once for all entry comparisons.
    # read_run_marker is a read-only path (no mkdir) and returns None when
    # there is no active (or non-stale) run — in that case the freshness gate
    # is skipped and only nonce+TTL semantics apply.
    marker = read_run_marker(now=now)
    run_started_epoch: float | None = None
    if marker is not None:
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(
                started_at_str, "%Y-%m-%dT%H:%M:%SZ"
            )
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            # Unrecognised format — skip the run-start gate for safety.
            run_started_epoch = None

    data = _load_registry()
    for entry in data["entries"]:
        if entry.get("prompt_sha256") != target_sha:
            continue
        if entry.get("consumed", True):
            # Already consumed — not dispatchable.
            continue
        emitted_at = entry.get("emitted_at", 0.0)
        if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
            # Beyond TTL — not dispatchable (re-probe required).
            continue
        if run_started_epoch is not None and emitted_at < run_started_epoch:
            # Entry predates the current run — not dispatchable.  A re-probe
            # (new register_emission call) is required to get a fresh entry.
            continue
        return entry
    return None


def resolve_emission_by_nonce(
    nonce: str,
    *,
    now: float | None = None,
) -> dict | None:
    """Look up a registry entry by nonce and return it ONLY when dispatchable.

    F2a (lazy-validation-readiness Phase 3): the by-reference dispatch path.
    The guard calls this when it receives a ``@@lazy-ref nonce=<hex>`` prompt
    token.  If the nonce resolves to a fresh, unconsumed, run-start-gated entry,
    the guard returns ``permissionDecision: "allow"`` PLUS
    ``hookSpecificOutput.updatedInput`` (with ``prompt = entry["prompt_raw"] or
    entry["prompt_norm"]``), so the spawned subagent receives the fully-expanded
    prompt without any retyping.

    Freshness gates mirror ``lookup_emission`` exactly:
      1. Nonce + TTL: entry must be unconsumed AND within
         REGISTRY_ENTRY_TTL_SECONDS (1800 s) of ``emitted_at``.
      2. Run-start gate (when a non-stale run marker exists): additionally
         require ``emitted_at >= marker.started_at`` epoch — entries predating
         the current run are not dispatchable even if within TTL.

    This function is READ-ONLY and fail-safe: any error → None (fail-open to
    deny, never a spurious allow).  The guard is responsible for consuming the
    nonce after resolving it.

    Args:
        nonce: the nonce hex string from the ``@@lazy-ref`` token.
        now: epoch float for TTL comparison (injectable for hermetic tests;
             defaults to time.time()).

    Returns:
        The matching registry entry dict when dispatchable, or None when:
          - the nonce does not exist in the registry, OR
          - the entry is consumed, OR
          - the entry is beyond TTL, OR
          - the entry predates the current run's started_at.
    """
    if now is None:
        now = time.time()

    try:
        # Compute the run-start epoch gate (mirrors lookup_emission).
        marker = read_run_marker(now=now)
        run_started_epoch: float | None = None
        if marker is not None:
            started_at_str = marker.get("started_at", "")
            try:
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                run_started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
            except (ValueError, TypeError):
                run_started_epoch = None

        data = _load_registry()
        for entry in data["entries"]:
            if entry.get("nonce") != nonce:
                continue
            # Gate 1: must be unconsumed.
            if entry.get("consumed", True):
                return None
            # Gate 2: must be within TTL.
            emitted_at = entry.get("emitted_at", 0.0)
            if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
                return None
            # Gate 3: must not predate the current run (when a marker is present).
            if run_started_epoch is not None and emitted_at < run_started_epoch:
                return None
            # All gates passed — this entry is dispatchable by reference.
            return entry
        # Nonce not found in registry.
        return None
    except Exception:  # noqa: BLE001
        # Fail-safe: any error → None so the guard falls through to deny,
        # never a spurious allow.
        return None


def append_dispatch_by_reference_event(
    *,
    tool_use_id: str,
    nonce: str,
    resolved_sha12: str,
    item_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``dispatch_by_reference: true`` audit event to the deny ledger.

    F2a (lazy-validation-readiness Phase 3): every by-reference allow must write
    an auditable record to the same deny ledger (JSONL) used by denies and
    auto-readmits, so the path is retro-gradable and distinguishable from a
    verbatim allow.

    Event shape (mirrors append_auto_readmit_event for reader uniformity):

        {"ts": <epoch float>, "tool_use_id": <str>,
         "dispatch_by_reference": true, "nonce": <hex>,
         "resolved_sha12": <12 hex chars of the resolved prompt's sha256>,
         "item_id": <str|None>, "acked": true}

    ``acked`` is True because a by-reference allow owes NO hardening debt —
    it is a sanctioned dispatch path, not a harness gap.

    Best-effort / fail-open: mirrors the contract of append_auto_readmit_event —
    the caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising.

    Args:
        tool_use_id: the dispatched Agent tool_use_id.
        nonce: the ``@@lazy-ref`` nonce that was resolved.
        resolved_sha12: first 12 hex chars of the resolved prompt's sha256
                        (for retro correlation without storing the full sha).
        item_id: the matched entry's feature/bug id (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        event = {
            "ts": now,
            "tool_use_id": tool_use_id,
            # Discriminator field: retro readers filter on this to see
            # by-reference dispatches separately from verbatim allows and denies.
            "dispatch_by_reference": True,
            "nonce": nonce,
            "resolved_sha12": resolved_sha12,
            "item_id": item_id,
            # Pre-acked: by-reference dispatches owe no hardening debt — they are
            # the SAFE path (bytes come from the registered emission, not from
            # hand-composition), so they must never inflate pending_hardening()
            # or block --run-end.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        # Plain append (same pattern as append_deny_ledger_entry and
        # append_auto_readmit_event): the ledger is append-only and a torn final
        # line is tolerated by the corrupt-line-skipping reader.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate to the guard.
        return False


def emission_consumed_by_nonce(nonce: str) -> bool:
    """Return True iff a registry entry with this nonce exists AND is consumed.

    dispatch-guard-denies-workstation-subsubagent-split (decision 4, 2026-07-10):
    this is the CONSUMED FENCE for the guard's workstation sub-subagent
    exemption. The cycle marker is written by ``--cycle-begin`` BEFORE the
    orchestrator's own worker dispatch, so "cycle marker active" alone would
    open a window where the orchestrator itself could improvise an unregistered
    dispatch under its freshly-armed cycle marker. Requiring the cycle's OWN
    registered emission to already be consumed closes that window: consumption
    happens only on the guard-ALLOWed worker dispatch, session tool calls are
    serial, and the marker is cleared at ``--cycle-end`` — so any unregistered
    Agent prompt arriving while (marker active AND its emission consumed) can
    only originate INSIDE the in-flight cycle worker.

    Deliberately ignores TTL and the run-start gate: the question is "did the
    dispatch land", not "is the entry still dispatchable" (a long cycle may
    outlive the 1800 s registry TTL and its sub-subagent dispatches must not
    start re-denying mid-cycle).

    Read-only and FAIL-CLOSED: any error (missing/corrupt registry, absent
    nonce) returns False — the exemption never fires on uncertainty, so a
    failure here degrades to the pre-fix deny, never to a spurious allow.

    Args:
        nonce: the cycle marker's dispatch nonce.

    Returns:
        True when the entry exists and its ``consumed`` flag is truthy.
    """
    try:
        if not nonce:
            return False
        for entry in _load_registry().get("entries", []):
            if entry.get("nonce") == nonce:
                return bool(entry.get("consumed", False))
        return False
    except Exception:  # noqa: BLE001
        return False


def append_worker_subdispatch_event(
    *,
    tool_use_id: str,
    sha12: str,
    item_id: str | None = None,
    sub_skill: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``worker_subdispatch: true`` audit event to the deny ledger.

    dispatch-guard-denies-workstation-subsubagent-split (decision 4): every
    guard ALLOW taken through the workstation sub-subagent exemption writes an
    auditable record to the same deny ledger used by denies, auto-readmits, and
    by-reference dispatches, so the exemption path is retro-gradable and
    distinguishable from a registered-prompt allow.

    Event shape (mirrors append_dispatch_by_reference_event for reader
    uniformity):

        {"ts": <epoch float>, "tool_use_id": <str>,
         "worker_subdispatch": true, "sha12": <12 hex chars>,
         "item_id": <str|None>, "sub_skill": <str|None>, "acked": true}

    ``acked`` is True because an exempted sub-subagent dispatch owes NO
    hardening debt — it is a sanctioned dispatch path (the cycle worker
    following its skill's own orchestration model), not a harness gap — so it
    must never inflate ``pending_hardening()`` or block ``--run-end``.

    Best-effort / fail-open: swallows its own write errors and returns False
    rather than raising (a ledger failure must never affect the allow).

    Args:
        tool_use_id: the dispatched Agent tool_use_id.
        sha12: first 12 hex chars of the dispatched prompt's sha256.
        item_id: the active cycle marker's feature/bug id (optional).
        sub_skill: the active cycle marker's sub_skill (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        event = {
            "ts": now,
            "tool_use_id": tool_use_id,
            # Discriminator field: retro readers filter on this to see exempted
            # worker sub-subagent dispatches separately from other allow paths.
            "worker_subdispatch": True,
            "sha12": sha12,
            "item_id": item_id,
            "sub_skill": sub_skill,
            # Pre-acked: a sanctioned dispatch path owes no hardening debt.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def consume_nonce(nonce: str, consumer: str | None = None) -> bool:
    """Mark a registry entry's nonce as consumed (one dispatch per emission).

    After consumption, ``lookup_emission`` will no longer return this entry,
    enforcing the single-use constraint: a re-dispatch requires a re-probe,
    which is the continuation-cycles-must-re-emit rule made mechanical.

    Phase 2 extension: when ``consumer`` is provided (non-None), the
    ``consumed_by`` field is written onto the entry.  This enables the
    idempotent re-fire logic in ``lazy_guard.py`` — when the PreToolUse hook
    fires twice for the same denied dispatch (same tool_use_id, E4 spike
    finding), the guard reads ``consumed_by`` and allows the second call if
    the consumer matches.

    Backward compatibility: ``consumer=None`` (the default) preserves Phase 1
    behavior exactly — the entry is consumed but no ``consumed_by`` field is
    written.  All 264 existing test_lazy_core.py tests rely on this.

    Args:
        nonce: the nonce string from a previously registered entry
        consumer: optional string identifying the consumer (e.g. tool_use_id);
                  stored as ``consumed_by`` on the entry when provided.

    Returns:
        True if the nonce was found and consumed; False if not found or already
        consumed.
    """
    data = _load_registry()
    changed = False
    for entry in data["entries"]:
        if entry.get("nonce") == nonce:
            if entry.get("consumed", False):
                # Already consumed — idempotent False.
                return False
            entry["consumed"] = True
            # Phase 2: record the consuming tool_use_id when provided so the
            # guard can distinguish idempotent re-fire (same consumer) from a
            # legitimately distinct second attempt (different consumer → deny).
            if consumer is not None:
                entry["consumed_by"] = consumer
            changed = True
            break
    if not changed:
        return False
    _save_registry(data)
    return True


def register_emission_if_marked(
    prompt: str,
    cls: str,
    item_id: str | None = None,
    now: float | None = None,
) -> dict | None:
    """Register a prompt emission only when a valid run marker is present.

    This is the primary integration point for both state scripts' --emit-prompt
    handling: after computing a cycle_prompt, the script calls this function.
    If no marker is active → no-op (returns None, writes nothing).  This
    ensures default (no-marker) invocations remain byte-identical and the
    registry file is never created by accident.

    SPEC: all new Phase 1 behavior is unreachable without an explicit --run-start
    call (A10: byte-identical default output guarantee).

    Args:
        prompt: the dispatch prompt text
        cls: the dispatch class (e.g. "cycle")
        item_id: the feature or bug id (optional)
        now: epoch float (injectable; defaults to time.time())

    Returns:
        The registry entry dict if a marker is present and the registration
        succeeded; None otherwise (no marker = no write).
    """
    if now is None:
        now = time.time()
    # read_run_marker applies all staleness guards — if it returns None there
    # is no active run and we must not write.
    marker = read_run_marker(now=now)
    if marker is None:
        return None
    return register_emission(prompt, cls=cls, item_id=item_id, now=now)


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


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phase 1
#   The `requires_host:` declaration parse + the closed-registry vocabulary.
#
# A feature records the named host capabilities its runtime validation requires
# in a `requires_host:` set (SPEC frontmatter and/or queue.json entry). The set
# is matched against the host's probed-present set; a miss defers the feature to
# a capability-bearing host. The vocabulary is a CLOSED registry: a capability id
# exists only if the registry maps it to a probe callable (the callable wiring
# lands in Phase 3 — Phase 1 defines the id vocabulary as the dict's KEYS). An
# unregistered id is a loud fail-fast (Phase 4), never a silent defer-forever.
# ---------------------------------------------------------------------------

# Capability ids share the feature-id shape: lowercase alnum, internal dashes.
_HOST_CAPABILITY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The closed v1 registry. KEYS are the closed vocabulary (the only ids a feature
# may declare); VALUES are probe-callable PLACEHOLDERS — Phase 3 (WU-3) rebinds
# each to a real injected probe via host_present_capabilities' production
# bindings. A capability id only "exists" if it is a key here; an id absent from
# this map is an unknown-capability fail-fast (Phase 4). Keep this the single
# source of truth for "what ids exist" — both the fail-fast and the Phase-5
# match read it.
_HOST_CAPABILITY_REGISTRY: dict[str, object] = {
    # Generalizes the proven $ALGOBOOTH_REAL_AUDIO_DEVICE device axis.
    "real-audio-device": None,
    # A C++ toolchain (Zimtohrli golden:report) — the canonical binary-host gap
    # (session a0eae4be: audio-quality-analysis et al. gate on this absent).
    "zimtohrli-toolchain": None,
    # A GPU device.
    "gpu": None,
    # A motorized/MCU MIDI control surface (physical fader travel, MCU Device
    # Query handshake byte observation). The device axis ($ALGOBOOTH_REAL_AUDIO_
    # DEVICE) is AUDIO-only and cannot express this — a host with real audio but
    # no MIDI surface MUST defer (not re-open) MIDI-hardware scenarios. Added for
    # motorized-fader-sync, whose 2 hardware RV rows looped on the audio-axis
    # device re-open (Round 40). The fix: features needing MIDI hardware declare
    # `requires_host: midi-controller` + DEFERRED_REQUIRES_HOST.md, so a non-MIDI
    # host defers cleanly (host-capability-saturated) instead of looping.
    "midi-controller": None,
    # A 2nd Ableton Link peer reachable on the LAN (device-vs-host mis-
    # classification, Round 41, 2026-06-29). d5-ableton-link's multi-peer
    # scenarios (peerCount:0 on a solo host) were written DEFERRED_REQUIRES_DEVICE
    # by the cycle and looped: a real-audio-device host re-opens them (Step 9) but
    # cannot certify them (no 2nd peer), tripping the step-repeat tripwire. The
    # unmet prerequisite is a HOST capability (a peer), not an audio device. No
    # automated probe exists — a solo host cannot self-detect a 2nd peer — so this
    # id intentionally has NO _HOST_CAPABILITY_PROBE_CONFIG entry and binds to the
    # constant-False placeholder (fail-safe absent: it re-opens only when a future
    # mock_peers / peer probe is configured).
    "link-multi-peer": None,
    # A Linux or macOS host (device-vs-host mis-classification, Round 41,
    # 2026-06-29). non-windows-audio-hardening's cfg(unix) code is un-runnable on
    # Windows; the cycle wrote DEFERRED_REQUIRES_DEVICE and looped (a real-audio-
    # device WINDOWS host re-opens but can never run cfg(unix) code). The unmet
    # prerequisite is the OS, not an audio device. Unlike link-multi-peer, the OS
    # IS deterministically detectable — this id DOES have a probe (kind "platform",
    # predicate "non-windows") so a non-Windows host reports it present and certifies.
    "non-windows-host": None,
}

# Module-load assertion: every registered id is shape-valid (a typo in the
# registry itself is a developer error, surfaced at import, never at runtime).
assert all(
    _HOST_CAPABILITY_ID_RE.match(_cap_id) for _cap_id in _HOST_CAPABILITY_REGISTRY
), "every _HOST_CAPABILITY_REGISTRY key must match ^[a-z0-9][a-z0-9-]*$"


def _coerce_capability_ids(value: object) -> set[str]:
    """Coerce a raw `requires_host:` value into a set of shape-valid capability
    ids (tolerant input, same spirit as the independent-marker coercion).

    Accepts a list/tuple of strings OR a single string (comma- and/or
    whitespace-separated). Each token is stripped; tokens that do NOT match the
    capability-id shape are DROPPED (the parse never emits a shape-invalid id —
    an unregistered-but-shaped typo is caught later by ``unknown_capability_ids``
    at the fail-fast; a mis-shaped token is simply not a capability). Anything
    that is neither a string nor a list/tuple yields the empty set.
    """
    def _split(raw: str) -> list[str]:
        # Tolerate an inline YAML/JSON flow-list literal `[a, b]` (frontmatter is
        # scanned as raw lines, not YAML-parsed) by stripping the surrounding
        # brackets, then split on commas/whitespace and strip any quotes.
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        return [tok.strip().strip("'\"") for tok in re.split(r"[,\s]+", raw)]

    tokens: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                tokens.extend(_split(item))
    elif isinstance(value, str):
        tokens.extend(_split(value))
    return {t for t in tokens if t and _HOST_CAPABILITY_ID_RE.match(t)}


# Matches a frontmatter line `requires_host: <value>` (case-insensitive key,
# leading whitespace tolerated). The captured tail is coerced by
# _coerce_capability_ids — a list literal `[a, b]` or a bare comma/space string.
_REQUIRES_HOST_RE = re.compile(
    r"^\s*requires_host\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)


def parse_requires_host(spec_text: str, queue_entry: dict | None) -> set[str]:
    """Deterministic two-source read of a feature's `requires_host:` capability
    set (host-capability-declaration-for-gated-features Phase 1).

    Mirrors ``parse_independent_marker``'s two-source fenced-block walk. Returns
    the UNION of the capability ids declared in EITHER the SPEC.md frontmatter OR
    the ``queue.json`` entry. Absent/legacy (no ``requires_host:`` anywhere) ⇒
    the EMPTY set — the ungated baseline-regression rail (a feature without the
    field behaves exactly as today). On-disk, deterministic — no LLM judgment.

    Input is tolerant (via ``_coerce_capability_ids``): a YAML/JSON list value
    ``[a, b]`` and a bare comma/space-separated string both parse to the same
    set; shape-invalid tokens are dropped (never emitted).

    Args:
        spec_text: the raw SPEC.md text (its leading ``---`` fenced frontmatter
            block is scanned when present, else the head of the file up to the
            first markdown heading — a bare leading marker).
        queue_entry: the feature's ``queue.json`` entry (may be ``None``/empty).

    Returns:
        The set of declared capability ids (possibly empty).
    """
    result: set[str] = set()
    # Source 1: the queue entry (a JSON list or string under `requires_host`).
    if isinstance(queue_entry, dict) and "requires_host" in queue_entry:
        result |= _coerce_capability_ids(queue_entry.get("requires_host"))
    # Source 2: the SPEC.md frontmatter. Scan the leading `---` fenced block if
    # present; otherwise scan the head of the file up to the first heading.
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
            m = _REQUIRES_HOST_RE.match(line)
            if m:
                result |= _coerce_capability_ids(m.group(1))
    return result


def unknown_capability_ids(required: set[str]) -> set[str]:
    """Return the subset of ``required`` ids NOT in the closed registry.

    Pure helper — the fail-fast input for Phase 4 (an unregistered id is a loud,
    immediate validation failure, never a silent defer-forever). Empty set ⇒
    every required id is registered.
    """
    return set(required) - set(_HOST_CAPABILITY_REGISTRY)


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phase 3
#   Host-present-set resolver + per-run probe cache + production bindings.
#
# Composes the Phase-2 primitives into ONE resolver returning the host's
# present-capability set, bound to the closed registry, hermetic via injection
# (real production bindings used only when probes is None). The result is cached
# in the per-repo keyed state dir keyed to the run-marker identity: cache for the
# run, re-probe on a new run marker (the cheapest correct option). No marker ⇒
# probe fresh (no cache). Phase-5's match diffs each candidate's requires_host
# set against this present set.
# ---------------------------------------------------------------------------

_HOST_PROBE_CACHE_FILENAME = "lazy-host-capability-cache.json"

# AlgoBooth-specific probe configuration — kept config-overridable here, NOT
# hard-coded into the resolver flow (so a non-AlgoBooth repo can override the
# binary argv / env var names without touching the resolver). Each entry names
# the probe primitive + its argument for the production binding below.
_HOST_CAPABILITY_PROBE_CONFIG: dict[str, dict] = {
    "real-audio-device": {"kind": "env", "var": "ALGOBOOTH_REAL_AUDIO_DEVICE"},
    "zimtohrli-toolchain": {"kind": "binary", "argv": ["zimtohrli", "--version"]},
    # GPU presence on this Windows host: a documented active-invocation probe
    # (nvidia-smi exits 0 iff an NVIDIA GPU + driver are present). A host without
    # the binary reports absent — never a which()/exists() false positive.
    "gpu": {"kind": "binary", "argv": ["nvidia-smi", "-L"]},
    # A motorized/MCU MIDI control surface, probed via an explicit env var
    # (mirrors the real-audio-device env probe). A host with a motorized fader
    # connected sets ALGOBOOTH_REAL_MIDI_DEVICE=1; absent ⇒ defer. An env probe
    # (not live MIDI-port enumeration) is the conservative v1 — a virtual/aggregate
    # MIDI port would false-positive "real hardware present" for the servo-travel
    # assertion, exactly the false-certify the device axis guards against.
    "midi-controller": {"kind": "env", "var": "ALGOBOOTH_REAL_MIDI_DEVICE"},
    # A Linux or macOS host. The OS is deterministically detectable, so this binds
    # a real "platform" probe (predicate "non-windows" → platform.system() != Windows).
    # A Windows host reports absent and defers cfg(unix)-only scenarios cleanly.
    # (link-multi-peer is deliberately ABSENT from this config — no self-probe for a
    # 2nd network peer — so it binds to the constant-False placeholder below.)
    "non-windows-host": {"kind": "platform", "predicate": "non-windows"},
}


def _default_host_probes() -> dict:
    """Build the production ``{capability-id: callable}`` map from the closed
    registry + the (config-overridable) probe config.

    Each callable closes over its config entry and calls the matching Phase-2
    primitive with the real default invoker/environ. An id present in the
    registry but missing a config entry binds to a constant-False probe (it can
    never be present until a probe is configured — fail-safe absent, never a
    crash). Real defaults are bound ONLY here (the resolver passes ``probes=None``
    through to this), mirroring ``ensure_runtime``'s injected-callable contract.
    """
    probes: dict[str, object] = {}
    for cap_id in _HOST_CAPABILITY_REGISTRY:
        cfg = _HOST_CAPABILITY_PROBE_CONFIG.get(cap_id)
        if not cfg:
            probes[cap_id] = (lambda: False)
        elif cfg.get("kind") == "env":
            var = cfg["var"]
            probes[cap_id] = (lambda v=var: probe_env_capability(v))
        elif cfg.get("kind") == "binary":
            argv = cfg["argv"]
            probes[cap_id] = (lambda a=argv: probe_binary_capability(a))
        elif cfg.get("kind") == "platform":
            predicate = cfg["predicate"]
            probes[cap_id] = (lambda p=predicate: probe_platform_capability(p))
        else:
            probes[cap_id] = (lambda: False)
    return probes


def host_present_capabilities(*, probes=None, cache: bool = True) -> set[str]:
    """Resolve the host's present-capability set (host-capability-declaration
    Phase 3).

    For each ``_HOST_CAPABILITY_REGISTRY`` id, evaluates its bound probe callable
    and returns the set of ids whose probe returned truthy. ``probes`` injects a
    ``{capability-id: callable}`` map so ``--test`` stays hermetic; ``None`` binds
    the real production probes (``_default_host_probes``). A registry id with no
    entry in ``probes`` is treated as absent.

    Caching (cache=True, the default): the present-set is cached as JSON under
    ``claude_state_dir()`` keyed to the live run marker's identity (``started_at``).
    A second call within the SAME run hits the cache (no re-probe); a NEW run
    marker (different ``started_at``) re-probes and rewrites the cache. With NO
    run marker present there is no run identity to key on, so the probe runs
    FRESH every call (no cache write/read). The cache read is non-destructive.

    Args:
        probes: injected ``{capability-id: callable() -> bool}`` map; ``None`` ⇒
            real production bindings.
        cache: when True, read/write the per-run cache; when False, always probe
            fresh (used by callers that want a one-shot uncached resolution).

    Returns:
        The set of present capability ids.
    """
    probe_map = _default_host_probes() if probes is None else probes

    # Resolve the live run identity (the cache key). Read-only marker access —
    # never creates the state dir, never mutates the marker.
    run_id = None
    if cache:
        marker = read_run_marker()
        if isinstance(marker, dict):
            run_id = marker.get("started_at")

    cache_path = None
    if cache and run_id is not None:
        cache_path = claude_state_dir(create=False) / _HOST_PROBE_CACHE_FILENAME
        # Cache hit: same run id ⇒ return the cached present-set without probing.
        try:
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if (
                    isinstance(cached, dict)
                    and cached.get("run_id") == run_id
                    and isinstance(cached.get("present"), list)
                ):
                    return set(cached["present"])
        except (OSError, json.JSONDecodeError, ValueError):
            # Corrupt/unreadable cache ⇒ ignore and re-probe (non-fatal).
            pass

    # Probe fresh: evaluate each registry id's bound callable.
    present: set[str] = set()
    for cap_id in _HOST_CAPABILITY_REGISTRY:
        probe = probe_map.get(cap_id)
        if probe is None:
            continue
        try:
            if probe():
                present.add(cap_id)
        except Exception:  # noqa: BLE001 — a misbehaving probe ⇒ absent
            continue

    # Write the cache only when there is a run identity to key on.
    if cache and run_id is not None and cache_path is not None:
        try:
            payload = {"run_id": run_id, "present": sorted(present)}
            _atomic_write(cache_path, json.dumps(payload, indent=2) + "\n")
        except OSError:
            pass  # cache write best-effort — never fail the resolution

    return present


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phases 4 + 5
#   Shared blocker-body formatter (Phase 4) + DEFERRED_REQUIRES_HOST.md writer
#   (Phase 5). Both live in lazy_core so the bug-pipeline parity mirror in Part 3
#   is a one-line reuse, not a re-implementation (the marker/sentinel infra is
#   shared between lazy-state.py and bug-state.py).
# ---------------------------------------------------------------------------

def utc_now_iso(now: float | None = None) -> str:
    """Return an ISO-8601 UTC timestamp with a trailing ``Z`` (the BLOCKED.md
    ``blocked_at`` format). ``now`` (epoch seconds) is injectable for hermetic
    tests; default is the real wall clock. Timezone-aware (no naive-UTC
    deprecation warning under Python ≥3.12).
    """
    if now is None:
        now = time.time()
    return (
        datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    )


def format_unknown_host_capability_blocker(
    feature_id: str, unknown: set[str] | list[str]
) -> str:
    """Build the human-readable BLOCKED.md body for the Phase-4
    unknown-host-capability fail-fast.

    Names BOTH the offending unregistered id(s) AND the sorted closed-registry
    ids so the operator can either fix the typo or register a new probe — the
    Bazel "No matching toolchains found" / Nix evaluation-failure shape (fail
    fast at parse, never spin on an unfulfillable requirement). Shared so the
    bug-pipeline parity mirror is a one-line reuse.
    """
    unknown_sorted = sorted(set(unknown))
    registry_sorted = sorted(_HOST_CAPABILITY_REGISTRY)
    return (
        "# Blocked — unregistered host capability\n\n"
        "## Details\n\n"
        f"Feature `{feature_id}` declares a `requires_host:` capability id that is "
        f"NOT in the closed host-capability registry: "
        f"{', '.join(f'`{u}`' for u in unknown_sorted)}.\n\n"
        "An unregistered id has no probe and could never be reported present on "
        "ANY host, so deferring it would strand the feature in silent, infinite "
        "queue starvation. This is a loud, immediate validation failure instead.\n\n"
        "## Known (registered) capability ids\n\n"
        f"{', '.join(f'`{r}`' for r in registry_sorted)}\n\n"
        "## Recovery Suggestion\n\n"
        "Either fix the typo in the feature's `requires_host:` set to a known id "
        "above, or register a new probe for the capability in "
        "`lazy_core._HOST_CAPABILITY_REGISTRY` (+ a binding in "
        "`_HOST_CAPABILITY_PROBE_CONFIG`). Then rename/neutralize this BLOCKED.md.\n"
    )


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
# Phase 7 WU-7.1 — Deny ledger (routed hardening debt)
# ---------------------------------------------------------------------------
#
# Every guard deny appends one JSON line to lazy-deny-ledger.jsonl (best-effort,
# fail-open — the guard's own writer wraps this in try/except so a ledger failure
# never changes the deny response).  The ledger is the ground truth for "how many
# denials this run still owe a hardening round": --emit-dispatch hardening acks
# the OLDEST unacked entry (FIFO, one per emission), and --run-end refuses to
# retire the marker while unacked entries remain unless --ack-unhardened is passed.
#
# The deny path is the ONLY writer of new entries; allows never write.  Reads and
# acks tolerate a missing or partially-corrupt file: unparseable lines are skipped
# rather than treated as a fatal error (a single bad append must not brick the
# whole ledger).


def append_deny_ledger_entry(
    tool_use_id: str,
    denied_sha12: str,
    reason_head: str,
    prompt_head: str,
    now: float | None = None,
) -> bool:
    """Append one deny entry to the deny ledger (JSONL), best-effort.

    Called by lazy_guard.py on EVERY deny.  The caller wraps this in its own
    try/except so a ledger-write failure never changes the guard's deny output
    or exit code (fail-open is sacred) — this function additionally swallows its
    own write errors and returns False rather than raising, so it is safe to call
    from any context.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "tool_use_id": <str>, "denied_sha12": <12 hex>,
         "reason_head": <≤200 chars>, "prompt_head": <≤200 chars>, "acked": false}

    Args:
        tool_use_id: the denied Agent dispatch's tool_use_id (may be "").
        denied_sha12: the first 12 hex chars of the computed prompt sha256.
        reason_head: the deny reason, truncated to the first ~200 chars.
        prompt_head: the dispatched prompt, truncated to the first ~200 chars.
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "tool_use_id": tool_use_id,
            "denied_sha12": denied_sha12,
            "reason_head": (reason_head or "")[:_LEDGER_HEAD_CHARS],
            "prompt_head": (prompt_head or "")[:_LEDGER_HEAD_CHARS],
            "acked": False,
            # Residual gap B (loop-detector-false-positives-probes-and-cross-run-state):
            # stamp the entry with the LIVE run marker's identity (None when no
            # marker exists — e.g. a manual/no-marker deny). `pending_hardening()`
            # et al. compare this against the CURRENT live marker so a crashed
            # run's leftover unacked entries no longer force the NEXT run to
            # drain debt it never saw. Non-destructive read — never creates the
            # state dir as a side effect.
            "run_started_at": _raw_marker_started_at(),
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        # Append a single compact JSON line.  Plain append (not _atomic_write):
        # the ledger is append-only and a torn final line is tolerated by the
        # corrupt-line-skipping reader, so the atomic-rewrite ceremony would only
        # add a read-modify-write race window with the ack path.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def append_friction_ledger_entry(
    reason_head: str,
    detail: str,
    now: float | None = None,
) -> bool:
    """Append one process-friction entry to the SAME deny ledger (JSONL).

    hardening-blind-to-process-friction Phase 2 (D1): when --cycle-end detects a
    torn cycle bracket or unexpected commits, it records the friction as
    hardening debt by appending to ``lazy-deny-ledger.jsonl`` — the SAME file the
    guard's denies use. A ``kind: "process-friction"`` discriminator lets a single
    reader walk denies + friction, while the existing consumers
    (``pending_hardening()`` / ``oldest_unacked_deny()`` / the ``--run-end`` gate /
    the ``--emit-prompt`` probe's withholding) count any unacked entry unchanged —
    so a runaway self-announces as hardening debt with NO new routing machinery.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "kind": "process-friction",
         "reason_head": <≤200 chars — the signal: cycle-bracket-break /
         unexpected-commits>, "detail": <≤200 chars — the human-readable
         specifics>, "acked": false}

    Best-effort / fail-open — identical contract to append_deny_ledger_entry: the
    caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising, so a ledger-write failure never derails the
    --cycle-end marker clear.

    Args:
        reason_head: the friction signal name (e.g. "cycle-bracket-break"),
            truncated to the head-char cap.
        detail: the human-readable specifics of the friction, truncated to the cap.
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "kind": "process-friction",
            "reason_head": (reason_head or "")[:_LEDGER_HEAD_CHARS],
            "detail": (detail or "")[:_LEDGER_HEAD_CHARS],
            "acked": False,
            # Residual gap B — same run-identity stamp as append_deny_ledger_entry
            # (None when no live run marker exists, e.g. the torn-bracket case
            # where the marker is already gone by the time --cycle-end runs).
            "run_started_at": _raw_marker_started_at(),
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def append_hook_event(
    kind: str,
    hook: str,
    signature: str,
    detail: str,
    repo_root: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one hook deny/error event to ``hook-events.jsonl`` (JSONL).

    incident-auto-capture Phase 1 (D2): the shared, best-effort appender that
    makes hook-level denies and fail-open errors COUNTABLE. The single
    overwritten ``hook-error.json`` breadcrumb keeps being written byte-
    identically by its existing writers; this append-only file is the countable
    history the ``incident-scan.py`` collector clusters over.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "kind": "error"|"deny", "hook": <str>,
         "repo_root": <str — best-effort attribution, may be "">,
         "signature": <≤200 chars — the hook's own deny-signature token /
         classified op / takeover signature; "" for errors>,
         "detail": <≤500 chars — human-readable specifics>}

    Best-effort / fail-open — the SAME sacred contract as
    ``append_deny_ledger_entry`` / ``append_friction_ledger_entry``: an append
    failure can NEVER change a hook's deny/allow output. This function swallows
    its own write errors and returns False rather than raising, and callers
    additionally wrap it, so it is safe to call from any deny/error site.

    The file lives beside the deny ledger in ``claude_state_dir()`` — the keyed
    per-repo dir in production (repo resolvable via the active-repo binding),
    the exact ``LAZY_STATE_DIR`` dir in hermetic tests, and the un-keyed base
    dir when no repo is resolvable (matching the breadcrumbs' residency rules).

    Args:
        kind: "deny" or "error" (the collector's kind discriminator).
        hook: the emitting hook's name (e.g. "lazy-cycle-containment").
        signature: the hook's per-class cluster signature (D4); "" for errors.
        detail: human-readable specifics (deny reason head / error message).
        repo_root: best-effort repo attribution recorded on the entry; None → "".
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "kind": kind,
            "hook": hook,
            "repo_root": repo_root or "",
            "signature": (signature or "")[:_LEDGER_HEAD_CHARS],
            # Detail gets a slightly larger cap than the ledger heads: raw deny
            # reasons are the collector's capsule evidence, but the line must
            # stay bounded.
            "detail": (detail or "")[:500],
        }
        events_path = claude_state_dir() / _HOOK_EVENTS_FILENAME
        # Plain append (not _atomic_write): append-only file whose reader is
        # corrupt-line-tolerant — same rationale as the deny ledger.
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: an events write must never propagate.
        return False


# ---------------------------------------------------------------------------
# Commit-bracket ledger (code-doc-provenance-linkage Phase 1 / SPEC D4-A)
#
# Per-cycle commit brackets are the deterministic raw material for the
# provenance producer's touched-file-set derivation: at --cycle-end (BOTH state
# scripts — coupled pair) the cycle marker's begin_head_sha → current-HEAD span
# is appended as {feature_id, begin_sha, end_sha, ts} to
# ``lazy-commit-brackets.jsonl`` in the per-repo keyed state dir. Append-only,
# FAIL-OPEN — the identical contract to append_friction_ledger_entry: a write
# failure returns False and never blocks the --cycle-end marker clear.
# ---------------------------------------------------------------------------

_COMMIT_BRACKETS_FILENAME = "lazy-commit-brackets.jsonl"


def append_commit_bracket(
    feature_id: str,
    begin_sha: str,
    end_sha: str,
    now: float | None = None,
) -> bool:
    """Append one commit-bracket record to the state-dir bracket ledger.

    Entry shape (one JSON object per line):
        {"ts": <epoch float>, "feature_id": <str>,
         "begin_sha": <str>, "end_sha": <str>}

    Best-effort / fail-open: swallows its own write errors and returns False
    rather than raising, so a ledger-write failure never derails the
    --cycle-end marker clear (identical to append_friction_ledger_entry).

    Returns:
        True if the line was appended; False on any write failure.
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "feature_id": feature_id,
            "begin_sha": begin_sha,
            "end_sha": end_sha,
        }
        ledger_path = claude_state_dir() / _COMMIT_BRACKETS_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def read_commit_brackets(item_id: str) -> list[dict]:
    """Return the recorded commit brackets for ``item_id`` (pure read).

    Reads ``lazy-commit-brackets.jsonl`` from the state dir and filters by the
    ``feature_id`` field (the bug pipeline records its bug ids in the same
    field — the cycle marker's id slot is shared). Malformed lines are skipped;
    a missing ledger / any read error degrades to ``[]`` (never raises, never
    creates the state dir).
    """
    try:
        ledger_path = claude_state_dir(create=False) / _COMMIT_BRACKETS_FILENAME
        if not ledger_path.is_file():
            return []
        out: list[dict] = []
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("feature_id") == item_id:
                out.append(entry)
        return out
    except Exception:  # noqa: BLE001
        return []


def record_cycle_commit_bracket(
    repo_root: Path | None = None,
    now: float | None = None,
) -> dict | None:
    """--cycle-end bracket recording (called by BOTH state scripts' handlers
    immediately BEFORE clear_cycle_marker — coupled pair).

    Reads the live cycle marker (the --cycle-begin snapshot), resolves the
    current HEAD, and appends the {feature_id, begin_sha, end_sha} bracket to
    the ledger via append_commit_bracket.

    Degradations (all return None; NEVER raise — the clear must proceed):
      - no/partial cycle marker (no feature_id or no begin_head_sha snapshot);
      - HEAD unresolvable (non-git tree);
      - begin == end (an empty bracket contributes no touched files and would
        only bloat the ledger — skipped);
      - the append itself failing (fail-open, returns False).

    Returns:
        The recorded bracket dict {feature_id, begin_sha, end_sha}, or None.
    """
    try:
        marker = read_cycle_marker()
        if not isinstance(marker, dict):
            return None
        feature_id = marker.get("feature_id")
        begin_sha = marker.get("begin_head_sha")
        if not feature_id or not begin_sha:
            return None
        root = repo_root or Path.cwd()
        end_sha = head_sha_snapshot(root)
        if not end_sha or end_sha == begin_sha:
            return None
        if not append_commit_bracket(feature_id, begin_sha, end_sha, now=now):
            return None
        return {
            "feature_id": feature_id,
            "begin_sha": begin_sha,
            "end_sha": end_sha,
        }
    except Exception:  # noqa: BLE001
        # Fail-open: bracket bookkeeping must never block the marker clear.
        return None


# ---------------------------------------------------------------------------
# Provenance producer (code-doc-provenance-linkage Phase 2)
#
# ONE WRITER, TWO TRIGGERS (SPEC D1-B): write_provenance is the SOLE author of
# the per-item IMPLEMENTED.md distillate (D2-A) and the committed per-repo
# reverse index docs/provenance-index.json (D3-A). It is called from:
#   1. the __mark_complete__/__mark_fixed__ branch of apply_pseudo (the
#      automatic completion-gate trigger, provenance: pipeline-gated), and
#   2. the --link-provenance / --backfill-provenance CLI handlers (the manual
#      trigger, provenance: manual | backfilled).
# The provenance enum (D9): pipeline-gated | manual (+ linked_by) | backfilled.
# The derivation enum (D4): commit-brackets | commit-range | message-grep.
# ---------------------------------------------------------------------------

_PROVENANCE_VALUES = ("pipeline-gated", "manual", "backfilled")
_PROVENANCE_KINDS = ("feature", "bug")


def _provenance_index_path(repo_root: Path) -> Path:
    """The committed per-repo reverse-index location (D3-A)."""
    return Path(repo_root) / "docs" / "provenance-index.json"


def _normalize_index_key(repo_root: Path, path_str: str) -> str:
    """Normalize a file path to the index's repo-relative POSIX key form."""
    s = str(path_str).replace("\\", "/").strip()
    # Strip an absolute repo_root prefix when present.
    root_posix = str(Path(repo_root)).replace("\\", "/").rstrip("/")
    if root_posix and s.startswith(root_posix + "/"):
        s = s[len(root_posix) + 1:]
    while s.startswith("./"):
        s = s[2:]
    return s.strip("/")


def _spec_summary_paragraph(item_dir: Path) -> str | None:
    """Extract the SPEC's leading ``>`` blockquote summary paragraph, verbatim
    (unwrapped to a single flowing paragraph). None when SPEC.md is absent or
    carries no leading blockquote."""
    spec_md_path = Path(item_dir) / "SPEC.md"
    if not spec_md_path.is_file():
        return None
    try:
        lines = spec_md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    quote: list[str] = []
    seen_quote = False
    for ln in lines:
        s = ln.strip()
        if s.startswith(">"):
            seen_quote = True
            quote.append(s.lstrip(">").strip())
        elif seen_quote:
            break  # the first blockquote block ended
        elif s.startswith("#") or not s:
            continue  # title / blanks before the summary
        else:
            break  # prose before any blockquote → no leading summary
    text = " ".join(q for q in quote if q).strip()
    return text or None


def _git_capture_lines(repo_root: Path, args: list[str]) -> list[str] | None:
    """Run a git command under repo_root and return stdout lines, or None on
    any failure (non-git tree, bad revision, git unavailable). Never raises."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root)] + args,
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return None
        return r.stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None


def derive_touched_from_range(repo_root: Path, rev_range: str) -> dict | None:
    """Derive {commits, files} from a git revision range (e.g. ``A..B``).

    commits = authored (merge-excluded) short shas in the range, oldest first;
    files = the range's ``git diff --name-only`` set, sorted. None when the
    range cannot be resolved (the caller decides the fallback)."""
    commits = _git_capture_lines(
        repo_root, ["rev-list", "--no-merges", "--reverse", rev_range])
    files = _git_capture_lines(repo_root, ["diff", "--name-only", rev_range])
    if commits is None or files is None:
        return None
    return {
        "commits": [c.strip()[:7] for c in commits if c.strip()],
        "files": sorted({f.strip() for f in files if f.strip()}),
    }


def derive_touched_from_brackets(repo_root: Path, item_id: str) -> dict | None:
    """Union {commits, files} over the item's recorded commit brackets (D4-A,
    the pipeline-primary derivation). None when no bracket resolves (no
    brackets recorded, or every recorded sha is unreachable) — the caller
    falls back to message-grep with an honest derivation label."""
    brackets = read_commit_brackets(item_id)
    if not brackets:
        return None
    commits: list[str] = []
    files: set[str] = set()
    any_resolved = False
    for b in brackets:
        begin = b.get("begin_sha")
        end = b.get("end_sha")
        if not begin or not end:
            continue
        r = derive_touched_from_range(repo_root, f"{begin}..{end}")
        if r is None:
            continue
        any_resolved = True
        for c in r["commits"]:
            if c not in commits:
                commits.append(c)
        files.update(r["files"])
    if not any_resolved:
        return None
    return {"commits": commits, "files": sorted(files)}


def derive_touched_from_grep(repo_root: Path, item_id: str) -> dict:
    """Message-grep fallback derivation (D4-B, explicitly degraded): commits
    whose message contains the item id literal (fixed-string), plus their
    touched files. Empty lists when nothing matches / not a git tree."""
    out = _git_capture_lines(
        repo_root,
        ["log", "--no-merges", "--fixed-strings", f"--grep={item_id}",
         "--name-only", "--pretty=format:%H"],
    )
    if out is None:
        return {"commits": [], "files": []}
    commits: list[str] = []
    files: set[str] = set()
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for ln in out:
        s = ln.strip()
        if not s:
            continue
        if sha_re.match(s):
            short = s[:7]
            if short not in commits:
                commits.append(short)
        else:
            files.add(s)
    return {"commits": commits, "files": sorted(files)}


def write_provenance(
    repo_root: Path,
    item_dir: Path,
    item_id: str,
    kind: str,
    commits: list[str],
    files: list[str],
    *,
    provenance: str = "pipeline-gated",
    derivation: str = "commit-brackets",
    date: str | None = None,
    body: str | None = None,
    linked_by: str | None = None,
    validated_line: str | None = None,
    dry_run: bool = False,
) -> dict:
    """THE provenance producer — sole author of IMPLEMENTED.md + the index.

    Writes (atomically, via _atomic_write):
      1. ``item_dir/IMPLEMENTED.md`` — the D2-A distillate: frontmatter
         (kind: implemented, feature_id, date, provenance, [linked_by,]
         derivation, commits, decisions) + a deterministic body (the SPEC's
         leading ``>`` summary verbatim, the Locked-Decision id — title rows
         via _parse_locked_decisions, and the receipt-facts line). A manual
         ``body`` (the D8 operator-approved prose) replaces the deterministic
         body; the producer still owns the frontmatter and the index either way.
      2. ``repo_root/docs/provenance-index.json`` — the D3-A reverse index:
         repo-relative POSIX path → sorted [{id, type, provenance}] rows. This
         item's existing rows are REPLACED (re-linking never duplicates);
         other items' rows are preserved byte-for-byte modulo canonical
         ordering. The index write is skipped entirely when the item touches
         no files AND no index exists yet (nothing to record, nothing to trim).

    ``dry_run=True`` computes everything (including ``distillate_preview``)
    and writes NOTHING.

    Returns a dict: {ok, refused, wrote, files, commits, decisions, dry_run}
    (+ distillate_preview on dry_run). Any write/parse failure returns
    ok: False with the refusal text — callers inside the completion gate fold
    that into warnings[]; the manual CLI surfaces it verbatim.
    """
    if date is None:
        date = datetime.date.today().isoformat()
    if kind not in _PROVENANCE_KINDS:
        return {"ok": False, "refused": f"unknown item kind {kind!r} "
                f"(expected one of {_PROVENANCE_KINDS})", "wrote": []}
    if provenance not in _PROVENANCE_VALUES:
        return {"ok": False, "refused": f"unknown provenance {provenance!r} "
                f"(expected one of {_PROVENANCE_VALUES})", "wrote": []}

    repo_root = Path(repo_root)
    item_dir = Path(item_dir)

    # Canonicalize inputs (deterministic, byte-stable re-runs).
    norm_files: list[str] = sorted({
        _normalize_index_key(repo_root, f) for f in (files or []) if str(f).strip()
    })
    norm_commits: list[str] = []
    for c in commits or []:
        c = str(c).strip()
        if c and c not in norm_commits:
            norm_commits.append(c)

    # Decisions from the SPEC's canonical Locked-Decision surface (zero new
    # parsing — the same enumeration gate_coverage uses).
    spec_md = ""
    spec_md_path = item_dir / "SPEC.md"
    if spec_md_path.is_file():
        try:
            spec_md = spec_md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            spec_md = ""
    decisions = _parse_locked_decisions(spec_md)
    decision_ids = [d["id"] for d in decisions]

    # --- Assemble the distillate ---
    commits_inline = yaml.safe_dump(
        norm_commits, default_flow_style=True).strip() if norm_commits else "[]"
    decisions_inline = yaml.safe_dump(
        decision_ids, default_flow_style=True).strip() if decision_ids else "[]"
    linked_by_line = f"linked_by: {linked_by}\n" if linked_by else ""
    fm = (
        "---\n"
        "kind: implemented\n"
        f"feature_id: {item_id}\n"
        f"date: {date}\n"
        f"provenance: {provenance}\n"
        f"{linked_by_line}"
        f"derivation: {derivation}\n"
        f"commits: {commits_inline}\n"
        f"decisions: {decisions_inline}\n"
        "---\n"
        "\n"
    )
    if body is not None:
        body_text = "# Implementation Ledger\n\n" + body.strip() + "\n"
    else:
        summary = _spec_summary_paragraph(item_dir) or "(no SPEC summary available)"
        if decisions:
            decision_rows = "\n".join(
                f"- {d['id']} — {d['title']}" for d in decisions)
            decisions_block = f"**Decisions that drove it:**\n{decision_rows}\n"
        else:
            decisions_block = (
                "**Decisions that drove it:** (none — the SPEC carries "
                "no Locked-Decision surface)\n"
            )
        validated_block = f"\n**{validated_line}**\n" if validated_line else ""
        body_text = (
            "# Implementation Ledger\n"
            "\n"
            f"**What shipped:** {summary}\n"
            "\n"
            f"{decisions_block}"
            f"{validated_block}"
        )
    distillate = fm + body_text

    # --- Merge the index (load → replace-this-item's-rows → serialize) ---
    index_path = _provenance_index_path(repo_root)
    try:
        index: dict = {}
        if index_path.is_file():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, dict):
                return {"ok": False, "refused":
                        f"{index_path} is not a JSON object — refusing to "
                        "merge; fix the index by hand", "wrote": []}
        merged: dict = {}
        for key, rows in index.items():
            if not isinstance(rows, list):
                continue
            kept = [
                r for r in rows
                if not (isinstance(r, dict)
                        and r.get("id") == item_id and r.get("type") == kind)
            ]
            if kept:
                merged[key] = kept
        for f in norm_files:
            merged.setdefault(f, []).append(
                {"id": item_id, "type": kind, "provenance": provenance})
        # Canonical form: sorted keys; per-key rows sorted by (type, id) and
        # rebuilt to the canonical field order — byte-stable re-runs.
        canonical = {}
        for key in sorted(merged):
            rows = sorted(
                merged[key],
                key=lambda r: (str(r.get("type")), str(r.get("id"))),
            )
            canonical[key] = [
                {"id": r.get("id"), "type": r.get("type"),
                 "provenance": r.get("provenance")}
                for r in rows
            ]
        index_serialized = json.dumps(canonical, indent=2) + "\n"
        # Nothing to record and nothing on disk to trim → skip the index write.
        index_write_needed = bool(canonical) or index_path.is_file()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "refused": f"provenance index could not be "
                f"merged ({exc})", "wrote": []}

    result_base = {
        "files": norm_files,
        "commits": norm_commits,
        "decisions": decision_ids,
        "dry_run": dry_run,
    }
    if dry_run:
        return {"ok": True, "refused": None, "wrote": [],
                "distillate_preview": distillate,
                "index_preview": index_serialized if index_write_needed else None,
                **result_base}

    # --- Writes (atomic; a failure surfaces as ok: False, refused) ---
    wrote: list[str] = []
    try:
        item_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(item_dir / "IMPLEMENTED.md", distillate)
        wrote.append("IMPLEMENTED.md")
        if index_write_needed:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(index_path, index_serialized)
            try:
                wrote.append(str(index_path.relative_to(repo_root)).replace("\\", "/"))
            except ValueError:
                wrote.append(str(index_path))
    except (OSError, ValueError) as exc:
        return {"ok": False, "refused": f"provenance write failed ({exc})",
                "wrote": wrote, **result_base}
    return {"ok": True, "refused": None, "wrote": wrote, **result_base}


def _resolve_provenance_item_dir(repo_root: Path, item_id: str) -> tuple[Path, str]:
    """Resolve an item id to its docs dir + type for the manual link path.

    Search order: docs/features/<id> (feature) → docs/bugs/<id> (bug) →
    docs/bugs/_archive/<id> (bug). When none exists, D8 says the manual path
    creates a MINIMAL decision-record dir — docs/features/<id>/ with the
    distillate as its primary doc (never a fabricated SPEC); the producer's
    mkdir handles the creation.
    """
    repo_root = Path(repo_root)
    candidates: list[tuple[Path, str]] = [
        (repo_root / "docs" / "features" / item_id, "feature"),
        (repo_root / "docs" / "bugs" / item_id, "bug"),
        (repo_root / "docs" / "bugs" / "_archive" / item_id, "bug"),
    ]
    for cand, kind in candidates:
        if cand.is_dir():
            return cand, kind
    return candidates[0]


def _resolve_pr_range(repo_root: Path, pr: int) -> tuple[str | None, str | None]:
    """Resolve a PR number to a ``base..head`` range via `gh pr view` (the D8
    `--pr` sugar). Returns (range, None) on success or (None, refusal) —
    degrading CLEANLY when gh is absent/unauthenticated (the refusal names the
    --commits fallback)."""
    try:
        r = subprocess.run(
            ["gh", "pr", "view", str(pr), "--json", "baseRefOid,headRefOid"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, (f"gh is unavailable ({exc}) — resolve the PR range "
                      "yourself and pass --commits <base>..<head>")
    if r.returncode != 0:
        return None, (f"gh pr view {pr} failed ({(r.stderr or '').strip()[:200]}) "
                      "— pass --commits <base>..<head> instead")
    try:
        data = json.loads(r.stdout)
        base = data["baseRefOid"]
        head = data["headRefOid"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, (f"gh pr view {pr} returned an unexpected payload ({exc}) "
                      "— pass --commits <base>..<head> instead")
    return f"{base}..{head}", None


def link_provenance(
    repo_root: Path,
    item_id: str,
    *,
    commit_range: str | None = None,
    pr: int | None = None,
    body_file: Path | None = None,
    linked_by: str | None = None,
    date: str | None = None,
    dry_run: bool = False,
) -> dict:
    """The MANUAL trigger of the one-writer producer (D8-A+C, D9).

    Addressing is commit-range-primary (``--commits A..B``); ``--pr <n>`` is
    sugar resolved via `gh pr view` to a range (clean refusal when gh is
    absent). The touched-file set and commit list are derived from the range
    (derivation: commit-range) and written THROUGH write_provenance with
    ``provenance: manual`` + ``linked_by:`` — so manual entries are
    shape-identical to pipeline entries by construction.

    ``body_file`` carries the operator-APPROVED distillate prose (the
    `/link-provenance` skill's draft-then-approve loop); omitted → the
    deterministic extract. ``dry_run`` derives + previews, writes nothing.
    """
    repo_root = Path(repo_root)

    def _refused(msg: str) -> dict:
        return {"ok": False, "refused": msg, "wrote": [], "dry_run": dry_run}

    if pr is not None and commit_range:
        return _refused("--commits and --pr are mutually exclusive — pass one")
    if pr is not None:
        commit_range, err = _resolve_pr_range(repo_root, pr)
        if err:
            return _refused(err)
    if not commit_range:
        return _refused("--link-provenance requires --commits <A..B> or --pr <n>")

    derived = derive_touched_from_range(repo_root, commit_range)
    if derived is None:
        return _refused(
            f"could not resolve commit range {commit_range!r} under "
            f"{repo_root} — nothing was written"
        )
    if not derived["commits"] and not derived["files"]:
        return _refused(
            f"commit range {commit_range!r} is empty (no authored commits, "
            "no touched files) — nothing to link"
        )

    body: str | None = None
    if body_file is not None:
        try:
            body = Path(body_file).read_text(encoding="utf-8")
        except OSError as exc:
            return _refused(f"--body-file could not be read ({exc})")

    item_dir, kind = _resolve_provenance_item_dir(repo_root, item_id)
    result = write_provenance(
        repo_root, item_dir, item_id, kind,
        derived["commits"], derived["files"],
        provenance="manual", derivation="commit-range",
        date=date, body=body,
        linked_by=(linked_by or "operator"),
        dry_run=dry_run,
    )
    result["commit_range"] = commit_range
    result["kind"] = kind
    try:
        result["item_dir"] = str(item_dir.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        result["item_dir"] = str(item_dir)
    return result


def _provenance_doc_path(repo_root: Path, item_id: str, kind: str) -> str:
    """Resolve an index row's distillate doc path (repo-relative POSIX),
    honoring archive residency for bugs. Falls back to the canonical
    non-archive location string when nothing exists on disk."""
    repo_root = Path(repo_root)
    if kind == "bug":
        candidates = [
            f"docs/bugs/{item_id}/IMPLEMENTED.md",
            f"docs/bugs/_archive/{item_id}/IMPLEMENTED.md",
        ]
    else:
        candidates = [f"docs/features/{item_id}/IMPLEMENTED.md"]
    for rel in candidates:
        if (repo_root / rel).is_file():
            return rel
    return candidates[0]


def provenance_lookup(repo_root: Path, path_str: str) -> dict:
    """PURE READ (D6-A): which decision records govern ``path_str``?

    Loads docs/provenance-index.json, normalizes the query to the index's
    repo-relative POSIX key form, and returns::

        {"path": <key>, "governed_by": [
            {"id", "type", "doc", "decisions", "provenance"}, ...]}

    ``doc`` is the item's IMPLEMENTED.md (archive residency resolved);
    ``decisions`` come from that distillate's frontmatter ([] when unreadable).
    Never mutates, never creates directories, never re-infers state — a
    missing/malformed index degrades to an empty ``governed_by`` (the consumer
    step is a no-op where no index exists)."""
    repo_root = Path(repo_root)
    key = _normalize_index_key(repo_root, path_str)
    out: dict = {"path": key, "governed_by": []}
    index_path = _provenance_index_path(repo_root)
    if not index_path.is_file():
        return out
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return out
    rows = index.get(key) if isinstance(index, dict) else None
    if not isinstance(rows, list):
        return out
    for r in rows:
        if not isinstance(r, dict):
            continue
        item_id = str(r.get("id"))
        kind = str(r.get("type"))
        doc_rel = _provenance_doc_path(repo_root, item_id, kind)
        decisions: list[str] = []
        doc_meta = parse_sentinel(repo_root / doc_rel)
        if doc_meta and isinstance(doc_meta.get("decisions"), list):
            decisions = [str(d) for d in doc_meta["decisions"]]
        out["governed_by"].append({
            "id": item_id,
            "type": kind,
            "doc": doc_rel,
            "decisions": decisions,
            "provenance": r.get("provenance"),
        })
    return out


# Churn-lint defaults (D10) — placeholder thresholds, tunable in one place:
# a file with >= _PROVENANCE_CHURN_THRESHOLD authored commits in the last
# _PROVENANCE_CHURN_DAYS days and NO index rows is a hotspot (the prompt to
# run the manual --link-provenance pass over teammate churn).
_PROVENANCE_CHURN_DAYS = 90
_PROVENANCE_CHURN_THRESHOLD = 5


def _iter_receipted_item_dirs(repo_root: Path):
    """Yield (item_dir, kind, receipt_name) for every dir holding a valid
    completion receipt: docs/features/*/COMPLETED.md (feature),
    docs/bugs/*/FIXED.md and docs/bugs/_archive/*/FIXED.md (bug)."""
    repo_root = Path(repo_root)
    roots = [
        (repo_root / "docs" / "features", "feature", "COMPLETED.md", "completed"),
        (repo_root / "docs" / "bugs", "bug", "FIXED.md", "fixed"),
        (repo_root / "docs" / "bugs" / "_archive", "bug", "FIXED.md", "fixed"),
    ]
    for base, kind, receipt_name, receipt_kind in roots:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            meta = parse_sentinel(d / receipt_name)
            if meta is not None and meta.get("kind") == receipt_kind:
                yield d, kind, receipt_name


def backfill_provenance(repo_root: Path, date: str | None = None) -> dict:
    """One-shot backfill (D7-A): distill every already-receipted item through
    the ONE producer with honest degraded provenance.

    Walks items with a valid COMPLETED.md/FIXED.md (features, bugs, AND
    docs/bugs/_archive/), skips items already carrying IMPLEMENTED.md
    (idempotent — never clobbers a richer pipeline/manual distillate), derives
    the touched-file set via message-grep (no commit brackets exist for
    pre-feature history), and writes provenance: backfilled +
    derivation: message-grep. A zero-hit slug still gets a distillate
    (commits: []) and contributes no index rows — honest, never silent.
    """
    repo_root = Path(repo_root)
    backfilled: list[str] = []
    skipped_existing: list[str] = []
    no_commit_matches: list[str] = []
    failures: list[str] = []
    for item_dir, kind, receipt_name in _iter_receipted_item_dirs(repo_root):
        item_id = item_dir.name
        if (item_dir / "IMPLEMENTED.md").exists():
            skipped_existing.append(item_id)
            continue
        derived = derive_touched_from_grep(repo_root, item_id)
        receipt_meta = parse_sentinel(item_dir / receipt_name) or {}
        receipt_prov = receipt_meta.get("provenance", "gated")
        if not derived["commits"]:
            no_commit_matches.append(item_id)
            validated_line = (
                f"Backfilled: message-grep resolved NO commits for this slug "
                f"(pre-feature history). Receipt: {receipt_name} "
                f"(provenance: {receipt_prov})."
            )
        else:
            validated_line = (
                f"Backfilled from message-grep history. Receipt: "
                f"{receipt_name} (provenance: {receipt_prov})."
            )
        result = write_provenance(
            repo_root, item_dir, item_id, kind,
            derived["commits"], derived["files"],
            provenance="backfilled", derivation="message-grep",
            date=date, validated_line=validated_line,
        )
        if result.get("ok"):
            backfilled.append(item_id)
        else:
            failures.append(f"{item_id}: {result.get('refused')}")
    out = {
        "ok": not failures,
        "backfilled": backfilled,
        "skipped_existing": skipped_existing,
        "no_commit_matches": no_commit_matches,
        "count": len(backfilled),
    }
    if failures:
        out["failures"] = failures
    return out


def lint_provenance(
    repo_root: Path,
    churn_days: int = _PROVENANCE_CHURN_DAYS,
    churn_threshold: int = _PROVENANCE_CHURN_THRESHOLD,
) -> dict:
    """Maintenance lint (D10) — PURE READ, report only, never mutates.

    Three checks:
      (a) dead_rows — index keys whose path no longer exists in the working
          tree (D5's rename/delete correction prompt: re-link or accept the
          tombstone);
      (b) churn_hotspots — files with >= churn_threshold authored commits in
          the last churn_days days and NO index rows (the prompt to run the
          manual pass over teammate churn). ``docs/**`` paths are excluded —
          decision records/queues churn by design and are not governed code;
      (c) cross_orphans — distillates (with a non-empty commits list) that
          have no index rows, and index rows citing a missing distillate.
    """
    repo_root = Path(repo_root)
    index_path = _provenance_index_path(repo_root)
    index: dict = {}
    index_error: str | None = None
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index = loaded
            else:
                index_error = "index is not a JSON object"
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            index_error = f"index unreadable ({exc})"

    # (a) dead rows.
    dead_rows: list[dict] = []
    for key in sorted(index):
        if not (repo_root / key).exists():
            ids = [r.get("id") for r in index[key] if isinstance(r, dict)]
            dead_rows.append({"path": key, "ids": ids})

    # (b) churn hotspots with no rows.
    churn_hotspots: list[dict] = []
    out = _git_capture_lines(
        repo_root,
        ["log", "--no-merges", f"--since={churn_days} days ago",
         "--name-only", "--pretty=format:"],
    )
    if out is not None:
        counts: dict[str, int] = {}
        for ln in out:
            s = ln.strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
        for path, n in sorted(counts.items()):
            if n < churn_threshold:
                continue
            if path in index:
                continue
            if path.startswith("docs/"):
                continue  # decision records / queues churn by design
            if not (repo_root / path).exists():
                continue  # deleted since — not an actionable hotspot
            churn_hotspots.append({"path": path, "commits": n})

    # (c) cross-orphans.
    ids_with_rows: set[tuple[str, str]] = set()
    for rows in index.values():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict):
                ids_with_rows.add((str(r.get("id")), str(r.get("type"))))
    distillates_without_rows: list[str] = []
    known_distillate_ids: set[str] = set()
    dist_globs = [
        ("docs/features", "feature"),
        ("docs/bugs", "bug"),
        ("docs/bugs/_archive", "bug"),
    ]
    for rel_base, kind in dist_globs:
        base = repo_root / rel_base
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            doc = d / "IMPLEMENTED.md"
            meta = parse_sentinel(doc)
            if meta is None or meta.get("kind") != "implemented":
                continue
            known_distillate_ids.add(d.name)
            commits = meta.get("commits")
            has_commits = isinstance(commits, list) and len(commits) > 0
            if has_commits and (d.name, kind) not in ids_with_rows:
                distillates_without_rows.append(
                    str(doc.relative_to(repo_root)).replace("\\", "/"))
    rows_without_distillate: list[dict] = []
    seen_missing: set[tuple[str, str]] = set()
    for key in sorted(index):
        rows = index[key]
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            item_id = str(r.get("id"))
            kind = str(r.get("type"))
            if (item_id, kind) in seen_missing:
                continue
            doc_rel = _provenance_doc_path(repo_root, item_id, kind)
            if not (repo_root / doc_rel).is_file():
                seen_missing.add((item_id, kind))
                rows_without_distillate.append(
                    {"path": key, "id": item_id, "type": kind})
    report = {
        "ok": True,
        "index_present": index_path.is_file(),
        "dead_rows": dead_rows,
        "churn_hotspots": churn_hotspots,
        "cross_orphans": {
            "distillates_without_rows": distillates_without_rows,
            "rows_without_distillate": rows_without_distillate,
        },
        "thresholds": {
            "churn_days": churn_days,
            "churn_threshold": churn_threshold,
        },
    }
    if index_error:
        report["index_error"] = index_error
    return report


def append_auto_readmit_event(
    tool_use_id: str,
    readmitted_sha12: str,
    suffix_head: str,
    item_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Append one ``auto_readmit: true`` event to the deny ledger (JSONL).

    F1b (lazy-pipeline-ergonomics Phase 1): when the validate-deny guard
    auto-readmits a pure trailing-suffix superset of a fresh cycle-class entry
    (instead of denying it), it MUST write an auditable record so the readmit is
    never silent — the retro grader reads the same JSONL stream as the denies.

    The event reuses the deny-ledger shape so a single reader walks both denies
    and auto-readmits, distinguished by the ``auto_readmit`` flag:

        {"ts": <epoch float>, "tool_use_id": <str>, "auto_readmit": true,
         "readmitted_sha12": <12 hex of the MATCHED entry>,
         "suffix_head": <≤200 chars of the appended trailing suffix>,
         "item_id": <str|None>, "acked": true}

    ``acked`` is True because an auto-readmit owes NO hardening debt (the dispatch
    was allowed, not denied) — it must never inflate ``pending_hardening()`` or
    block ``--run-end``.

    Best-effort / fail-open: identical contract to append_deny_ledger_entry — the
    caller wraps this, and it additionally swallows its own write errors and
    returns False rather than raising.

    Args:
        tool_use_id: the auto-readmitted Agent dispatch's tool_use_id.
        readmitted_sha12: first 12 hex chars of the MATCHED entry's prompt_sha256.
        suffix_head: the appended trailing suffix, truncated to the head-char cap.
        item_id: the matched entry's feature/bug id (optional).
        now: epoch float for ts (injectable for hermetic tests).

    Returns:
        True if the line was appended; False on any write failure (fail-open).
    """
    if now is None:
        now = time.time()
    try:
        entry = {
            "ts": now,
            "tool_use_id": tool_use_id,
            "auto_readmit": True,
            "readmitted_sha12": readmitted_sha12,
            "suffix_head": (suffix_head or "")[:_LEDGER_HEAD_CHARS],
            "item_id": item_id,
            # Auto-readmits owe no hardening debt — pre-acked so they never count
            # toward pending_hardening() / --run-end refusal.
            "acked": True,
        }
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a ledger write must never propagate.
        return False


def find_auto_readmit_entry(
    prompt: str,
    now: float | None = None,
) -> dict | None:
    """Find an unconsumed, fresh, ``class == "cycle"`` registry entry whose stored
    normalized prompt text is a PURE TRAILING-SUFFIX PREFIX of *prompt*.

    F1b (lazy-pipeline-ergonomics Phase 1): the common validate-deny accident is
    an ORCHESTRATOR NOTE appended to a script-emitted ``cycle_prompt``.  The full
    hash misses (lookup_emission → None), so the guard would deny.  This helper
    lets the guard instead AUTO-READMIT the dispatch when the only difference is a
    trailing suffix appended to a sanctioned cycle prompt.

    Match criteria (ALL must hold):
      - the entry is unconsumed AND within REGISTRY_ENTRY_TTL_SECONDS AND
        (when a run marker exists) emitted at/after the run's started_at — the
        SAME freshness gate as lookup_emission, so a stale entry never readmits;
      - the entry's ``class`` is exactly ``"cycle"`` — NEVER ``"hardening"``
        (the depth-1 cap stays intact) and never any other ad-hoc class;
      - ``dispatched_norm.startswith(entry_norm)`` after identical
        normalize_prompt_for_hash normalization, with a NON-EMPTY remainder
        (a pure suffix superset — an exact equal would have hit lookup_emission,
        and an in-body edit is not a prefix so it never matches).

    Returns the matched entry dict (the FIRST qualifying entry in insertion
    order), or None when nothing qualifies.  Read-only — does NOT consume; the
    caller consumes the nonce on a successful readmit.

    Args:
        prompt: the dispatched prompt text (normalized before comparison).
        now: epoch float for the TTL/run-start gate (injectable for tests).

    Returns:
        The matching entry dict, or None.
    """
    if now is None:
        now = time.time()
    dispatched_norm = normalize_prompt_for_hash(prompt)

    # Compute the run-start epoch the same way lookup_emission does so the
    # freshness gate is identical (entries predating the current run never
    # readmit).
    marker = read_run_marker(now=now)
    run_started_epoch: float | None = None
    if marker is not None:
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(
                started_at_str, "%Y-%m-%dT%H:%M:%SZ"
            )
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            run_started_epoch = None

    for entry in _load_registry()["entries"]:
        # Hard class exclusion FIRST — never readmit anything but a cycle entry.
        if entry.get("class") != "cycle":
            continue
        if entry.get("consumed", True):
            continue
        entry_norm = entry.get("prompt_norm")
        # Legacy entries (registered before F1b) have no prompt_norm — skip them
        # (they can still be denied; auto-readmit just doesn't apply).
        if not isinstance(entry_norm, str) or not entry_norm:
            continue
        emitted_at = entry.get("emitted_at", 0.0)
        if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
            continue
        if run_started_epoch is not None and emitted_at < run_started_epoch:
            continue
        # Pure trailing-suffix superset: the dispatched prompt must START WITH the
        # registered prompt AND add a non-empty trailing remainder.  An exact
        # match (no remainder) would already have hit lookup_emission, and an
        # in-body edit is not a prefix so it never qualifies.
        if dispatched_norm.startswith(entry_norm) and len(dispatched_norm) > len(entry_norm):
            return entry
    return None


def find_transcription_slip_entry(
    prompt: str,
    *,
    now: float | None = None,
    threshold: float = 0.97,
) -> dict | None:
    """F2c (lazy-validation-readiness Phase 2): find a registry entry that the
    dispatched *prompt* is a TRANSCRIPTION SLIP of.

    A transcription slip is an otherwise-faithful reproduction of a script-emitted
    prompt that was mangled by cosmetic editing (e.g. one word retyped, an NBSP
    introduced) in a way that F2b's dash/quote/NBSP folding does NOT cover.  The
    high similarity ratio (>= *threshold*, default 0.97) means the orchestrator was
    clearly trying to dispatch a KNOWN registered prompt — the body is almost
    identical — but the bytes differ just enough to miss the hash gate.

    When this function returns an entry, the corrective action is always:
      re-run the Step 1a probe and dispatch the registered ``cycle_prompt``
      **verbatim or by-reference** — do NOT hand-edit the prompt again.

    A genuinely unregistered / hand-composed prompt has NO close registered entry
    (the difflib ratio is low) and falls through to the existing corrective deny
    with hardening debt (the no-match case returns None, so the caller continues to
    ``_deny_and_ledger``).

    Scope (F2c applies ONLY here):
      - Only applies when a valid run marker is present (this is a marked-run
        concern; if no marker, return None immediately — fail-safe for unmarked
        runs and ``--test`` baselines which must remain byte-identical).
      - Scans only entries emitted in the CURRENT run (emitted_at >= run-start
        epoch from ``read_run_marker``), mirroring ``lookup_emission``'s run-start
        gate, so stale cross-run entries cannot mis-classify a real gap.
      - EXCLUDES ``class == "hardening"`` entries unconditionally — the depth-1
        hardening cap must stay fully intact; a slip against a hardening-class
        entry must still go to ``_deny_and_ledger`` (which writes hardening debt).
      - Uses ``difflib.SequenceMatcher`` against the NFC-normalized text (stored
        as ``prompt_norm`` on the entry; falls back to normalizing a raw prompt
        field if ``prompt_norm`` is missing; skips the entry if neither is
        available).

    FAIL-SAFE / FAIL-OPEN contract:
      - Read-only; does NOT consume any nonce or write any state.
      - Any exception is caught and returns None so the caller falls through to
        the existing deny path — a slip-check error must NEVER turn a deny into
        a spurious allow and must NEVER cause an unhandled exception in the guard.

    Args:
        prompt: the dispatched prompt text (normalized before comparison).
        now: epoch float for the TTL / run-start gate (injectable for tests;
             defaults to time.time()).
        threshold: minimum SequenceMatcher ratio to classify as a slip (default
                   0.97 — very high so only near-verbatim copies qualify).

    Returns:
        The highest-ratio entry whose ratio >= *threshold*, or None.
    """
    # Fail-safe: all errors return None (never raise from a guard sub-path).
    try:
        if now is None:
            now = time.time()

        # Marker-gated: F2c is a marked-run concern.  No marker → not applicable.
        marker = read_run_marker(now=now)
        if marker is None:
            return None

        # Compute the run-start epoch (same logic as lookup_emission).
        run_started_epoch: float | None = None
        started_at_str = marker.get("started_at", "")
        try:
            started_dt = datetime.datetime.strptime(started_at_str, "%Y-%m-%dT%H:%M:%SZ")
            run_started_epoch = (
                started_dt - datetime.datetime(1970, 1, 1)
            ).total_seconds()
        except (ValueError, TypeError):
            run_started_epoch = None

        # Normalize the dispatched prompt for comparison.
        dispatched_norm = normalize_prompt_for_hash(prompt)

        import difflib as _difflib  # stdlib; imported lazily to keep startup cost low

        best_entry: dict | None = None
        best_ratio: float = 0.0

        for entry in _load_registry().get("entries", []):
            try:
                # Hard class exclusion: never classify a hardening-class entry as a
                # slip — the depth-1 cap must stay intact regardless.
                if entry.get("class") == "hardening":
                    continue

                # Run-start gate: only consider entries from the CURRENT run.
                emitted_at = entry.get("emitted_at", 0.0)
                if run_started_epoch is not None and emitted_at < run_started_epoch:
                    continue

                # TTL gate: entries beyond the TTL window are never candidates.
                if now - emitted_at > REGISTRY_ENTRY_TTL_SECONDS:
                    continue

                # Consumed entries can still be slip candidates — we only want to
                # classify the DENY path (the slip did not get an ALLOW), so the
                # relevant registered entries may or may not be consumed.
                # (If the exact-sha match had succeeded, the guard would already
                # have allowed via lookup_emission or _find_entry_by_sha, so we
                # only reach here when the sha did NOT match.)

                # Retrieve normalized form for comparison.
                entry_norm = entry.get("prompt_norm")
                if not isinstance(entry_norm, str) or not entry_norm:
                    # Legacy entry without prompt_norm — skip (no text to compare).
                    continue

                # SequenceMatcher similarity ratio.
                ratio = _difflib.SequenceMatcher(
                    None, dispatched_norm, entry_norm
                ).ratio()
                if ratio >= threshold and ratio > best_ratio:
                    best_ratio = ratio
                    best_entry = entry
            except Exception:  # noqa: BLE001
                # Skip a single bad entry — don't abort the scan.
                continue

        return best_entry

    except Exception:  # noqa: BLE001
        # Fail-open: any outer exception → return None so the caller falls through
        # to the existing deny path.  Never raise from a guard sub-path.
        return None


def read_deny_ledger() -> list[dict]:
    """Read all deny-ledger entries, skipping any unparseable lines.

    A missing ledger file → empty list (no denials yet).  A corrupt line (e.g.
    a torn final append) is skipped rather than aborting the whole read.

    Returns:
        The list of parsed entry dicts in file (FIFO insertion) order.
    """
    ledger_path = claude_state_dir(create=False) / _DENY_LEDGER_FILENAME
    if not ledger_path.exists():
        return []
    entries: list[dict] = []
    try:
        raw = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # Skip an unparseable line — a single torn append must not brick
            # the whole ledger.
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def pending_hardening(*, current_run_only: bool = True) -> int:
    """Return the count of unacked deny-ledger entries (the routed hardening debt).

    An entry is "pending" when its ``acked`` field is falsy.  A missing or empty
    ledger → 0.

    ``current_run_only`` (Residual gap B,
    loop-detector-false-positives-probes-and-cross-run-state; default True): when
    a LIVE run marker exists, count only unacked entries whose ``run_started_at``
    matches the live marker's ``started_at`` — i.e. debt this run actually owes.
    An unacked entry stamped with a DIFFERENT run's identity (or no identity at
    all — a legacy/pre-fix entry) belongs to a run that already ended (a crash
    left it undrained); it remains in the ledger for retro/incident mining but no
    longer forces the NEXT run to dispatch a hardening round for a denial it
    never saw (symptom 4). When NO live marker exists, there is no run identity
    to scope against, so this returns the unfiltered total — byte-identical to
    the pre-fix behavior for every no-marker caller/test. Pass
    ``current_run_only=False`` for the informational/retro total.
    """
    entries = [e for e in read_deny_ledger() if not e.get("acked", False)]
    if not current_run_only:
        return len(entries)
    current_started = _raw_marker_started_at()
    if current_started is None:
        return len(entries)
    return sum(1 for e in entries if e.get("run_started_at") == current_started)


def pending_denial_reasons(*, current_run_only: bool = True) -> list[str]:
    """Return the ``reason_head`` strings of all unacked deny-ledger entries, in
    FIFO order.  Used to surface ``pending_denials`` in the marker-gated probe
    enrichment so the orchestrator sees WHAT it still owes a hardening round for.

    ``current_run_only`` mirrors ``pending_hardening`` — see its docstring for the
    Residual-gap-B run-scoping contract.
    """
    entries = [e for e in read_deny_ledger() if not e.get("acked", False)]
    if current_run_only:
        current_started = _raw_marker_started_at()
        if current_started is not None:
            entries = [e for e in entries if e.get("run_started_at") == current_started]
    return [e.get("reason_head", "") for e in entries]


def prior_run_pending_hardening() -> int:
    """Return the count of unacked deny-ledger entries that belong to a run OTHER
    than the live one (Residual gap B — the informational T6 counterpart to
    ``pending_hardening()``'s now run-scoped mandatory debt).

    ``pending_hardening()`` (default ``current_run_only=True``) excludes these
    from the MANDATORY hardening-withholding count; this helper surfaces them
    separately so the orchestrator can report "N denial(s) from a prior/crashed
    run remain unacked" as an informational line, never a blocking one. When no
    live marker exists, returns 0 (there is no "other run" to compare against —
    ``pending_hardening()`` itself falls back to the unfiltered total in that
    case, so nothing is silently hidden).
    """
    current_started = _raw_marker_started_at()
    if current_started is None:
        return 0
    return sum(
        1 for e in read_deny_ledger()
        if not e.get("acked", False) and e.get("run_started_at") != current_started
    )


# ---------------------------------------------------------------------------
# efficacy-future-check-unenforced-orchestrator-prose (D1) — the end-of-run
# efficacy-flush breadcrumb + gate.
#
# The self-improving-harness observability loop (efficacy-eval.py review,
# efficacy-eval.py --canary, incident-scan.py — the "trio") is designed to run
# ONCE per run at the §1c.6 end-of-run flush, BEFORE --run-end.  That invocation
# was orchestrator PROSE only — nothing enforced it, and it WAS skipped at a real
# checkpoint --run-end.  This breadcrumb gate MIRRORS the unacked-hardening gate:
# each trio member drops a RUN-SCOPED breadcrumb when invoked (even on a clean
# no-op), and --run-end REFUSES (exit 1, marker kept) unless the breadcrumb is
# present OR --efficacy-skip-authorized retro-grades a deliberate skip.  The trio
# + the commit stay orchestrator-owned (D1, over run-end-invokes-the-trio) so the
# run's telemetry context is intact when the scripts read it and the terminal
# commit ordering is preserved.
#
# RUN-SCOPING: the breadcrumb records the current run marker's ``started_at``
# (the run identity used throughout the telemetry ledger — see
# efficacy-eval.py).  --run-end matches the breadcrumb's ``run_started_at``
# against the LIVE marker, so a stale breadcrumb left by a crashed prior run
# (different started_at) never satisfies the next run's gate.
# ---------------------------------------------------------------------------

_EFFICACY_BREADCRUMB_FILENAME = "lazy-efficacy-flush.json"


def _raw_marker_started_at() -> str | None:
    """RAW, NON-destructive read of the live run marker's ``started_at`` (the run
    identity), or None when no well-formed marker exists.

    Unlike ``read_run_marker`` this NEVER deletes a stale/corrupt marker and NEVER
    applies staleness or session gating — the efficacy gate reads it from the
    --run-end path (which must not double-delete) and the trio scripts drop the
    breadcrumb from any session.  A degraded/absent marker yields None.
    """
    try:
        marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
        if not marker_path.exists():
            return None
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            return None
        started_at = marker.get("started_at")
        return started_at if isinstance(started_at, str) and started_at else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _run_marker_state_dir(*, now: float | None = None) -> "tuple[Path, str] | None":
    """Resolve the LIVE run marker's state dir: the active repo's dir when it
    holds a live marker, else the most-recent live marker found in a keyed
    sibling subdir of the state base (interventions-telemetry-repo-scope-split-brain
    WU-2).

    The active (flat) state dir can hold NO marker at all when the run
    originated for a DIFFERENT repo than the one currently bound as active —
    the same split-brain ``_originating_telemetry_paths`` was built to close,
    whose scan approach this helper reuses (state base = ``LAZY_STATE_DIR`` if
    set else ``~/.claude/state``; enumerate subdirs; RAW-read each marker;
    age-filter via ``_MARKER_STALE_SECONDS``).

    RAW, NON-destructive reads only (never ``read_run_marker``, which deletes
    stale markers); no state-dir creation on this read path. Fully fail-open —
    any error yields None.

    Returns:
        ``(state_dir, started_at)`` for the most-recent live marker found, or
        None when no live marker exists anywhere.
    """
    if now is None:
        now = time.time()
    try:
        active = claude_state_dir(create=False)
        try:
            marker_path = active / _MARKER_FILENAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if isinstance(marker, dict):
                started_at_str = marker.get("started_at", "")
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if now - started_epoch <= _MARKER_STALE_SECONDS:
                    return (active, started_at_str)
        except Exception:  # noqa: BLE001 — fall through to the sibling scan
            pass

        override = os.environ.get("LAZY_STATE_DIR")
        base = Path(override) if override else (Path.home() / ".claude" / "state")
        if not base.is_dir():
            return None
        best_dir: Path | None = None
        best_started: float | None = None
        best_started_str: str | None = None
        for d in sorted(base.iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            try:
                marker_path = d / _MARKER_FILENAME
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if not isinstance(marker, dict):
                    continue
                started_at_str = marker.get("started_at", "")
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if now - started_epoch > _MARKER_STALE_SECONDS:
                    continue  # stale
            except Exception:  # noqa: BLE001
                continue  # unparseable marker in this subdir — skip it
            if best_started is None or started_epoch > best_started:
                best_started = started_epoch
                best_dir = d
                best_started_str = started_at_str
        if best_dir is None or best_started_str is None:
            return None
        return (best_dir, best_started_str)
    except Exception:  # noqa: BLE001
        return None


def _repo_is_interventions_bearing(repo_root) -> bool:
    """True iff ``repo_root`` opts into interventions capture: the
    ``docs/features/queue.json`` ``interventions: true`` flag, OR a
    ``docs/interventions/*.md`` hypothesis-ledger file other than
    ``CLAUDE.md``/``README.md``.

    Read-only, defensive: any error (missing dir, malformed queue.json, a
    permission error) yields False rather than raising — a scope-coverage
    breadcrumb must never wedge on a bad repo path.
    """
    try:
        root = Path(repo_root)
        if _interventions_queue_flag(root):
            return True
        interventions_dir = root / "docs" / "interventions"
        if interventions_dir.is_dir():
            for p in interventions_dir.glob("*.md"):
                if p.name not in ("CLAUDE.md", "README.md"):
                    return True
        return False
    except Exception:  # noqa: BLE001
        return False


def drop_efficacy_breadcrumb(
    covered_repo_root: str | None = None, *, now: float | None = None
) -> bool:
    """Drop the run-scoped "efficacy flush ran this run" breadcrumb that the
    --run-end gate checks (efficacy-future-check-unenforced-orchestrator-prose).

    Called by EACH trio member (efficacy-eval.py review + --canary, incident-scan)
    on a real (non-dry-run) invocation, EVEN on a clean no-op — running the flush
    is what discharges the gate.  MARKER-GATED (no live run marker anywhere —
    neither the active repo's state dir nor any keyed sibling — → no write,
    return False) and FAIL-OPEN (any error → False; the flush must never wedge
    on a breadcrumb write).

    interventions-telemetry-repo-scope-split-brain WU-2: the breadcrumb now
    ALSO records covered repo-scope(s) — which repo(s) this run's flush(es)
    actually covered (``covered_scopes``, a sorted list of ``repo_key``s) and
    whether ANY covered scope opts into interventions capture
    (``interventions_covered``) — so a flush that never covers the
    interventions-bearing repo can be told apart from one that genuinely did.
    The breadcrumb is written into the LIVE run marker's OWN state dir (see
    ``_run_marker_state_dir`` — this may differ from the active repo's dir),
    read-merged (accumulated) across calls sharing the SAME ``run_started_at``.

    Args:
        covered_repo_root: the repo whose scope this call covers. Defaults to
            the active repo (back-compat for the legacy no-arg call — e.g.
            incident-scan.py, which binds the active repo before calling).
        now: epoch float for the ``ts`` field (injectable for hermetic tests).

    Returns:
        True when the breadcrumb was written; False when marker-gated or on any
        write failure.
    """
    if now is None:
        now = time.time()
    loc = _run_marker_state_dir(now=now)
    if loc is None:
        return False
    try:
        run_dir, started_at = loc
        covered_root = covered_repo_root
        if covered_root is None:
            # Prefer the LIVE marker's OWN recorded repo_root — the run's
            # authoritative scope — over the process-global active_repo_root()
            # cwd fallback, which can diverge from the marker's repo when the
            # caller never bound it via set_active_repo_root/--repo-root
            # (interventions-telemetry-repo-scope-split-brain: a divergent cwd
            # fallback must never be mistaken for the run's actual scope).
            try:
                marker = json.loads(
                    (run_dir / _MARKER_FILENAME).read_text(encoding="utf-8")
                )
                if isinstance(marker, dict) and marker.get("repo_root"):
                    covered_root = marker["repo_root"]
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            if covered_root is None:
                covered_root = active_repo_root()
        covered_key = repo_key(str(covered_root))
        interventions_bearing = _repo_is_interventions_bearing(covered_root)

        crumb_path = run_dir / _EFFICACY_BREADCRUMB_FILENAME
        covered: set = set()
        interv = False
        try:
            if crumb_path.exists():
                prev = json.loads(crumb_path.read_text(encoding="utf-8"))
                if isinstance(prev, dict) and prev.get("run_started_at") == started_at:
                    covered = set(prev.get("covered_scopes") or [])
                    interv = bool(prev.get("interventions_covered"))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

        covered.add(covered_key)
        interv = interv or interventions_bearing

        body = json.dumps({
            "run_started_at": started_at,
            "ts": now,
            "covered_scopes": sorted(covered),
            "interventions_covered": interv,
        }) + "\n"
        _atomic_write(crumb_path, body)
        return True
    except Exception:  # noqa: BLE001 — fail-open: a breadcrumb write never wedges
        return False


def efficacy_breadcrumb_present(now: float | None = None) -> bool:
    """Return True iff the end-of-run efficacy flush ran for the CURRENT run
    AND covered an interventions-bearing scope — i.e. a breadcrumb exists whose
    ``run_started_at`` matches the LIVE run marker's ``started_at`` (run-scoped:
    a stale breadcrumb from a prior run never satisfies the gate) AND whose
    ``interventions_covered`` flag is True (coverage-scoped: a flush that only
    ever touched non-interventions-bearing scopes never satisfies the gate —
    closing the interventions-telemetry-repo-scope-split-brain COVERAGE hole;
    the sibling gate that inspects the trio's INVOCATION verified only that the
    flush ran, never that it ran against a scope where intervention records
    actually live).

    Returns True when there is NO live run marker — the gate is then MOOT (a
    --run-end with no marker is an idempotent no-op that must not be refused).
    Any read/parse error → False (fail-safe: a degraded breadcrumb does not
    satisfy the gate, exactly as a degraded deny-ledger never clears hardening
    debt).
    """
    started_at = _raw_marker_started_at()
    if started_at is None:
        return True  # no live run to have flushed — gate is moot
    try:
        crumb_path = claude_state_dir(create=False) / _EFFICACY_BREADCRUMB_FILENAME
        if not crumb_path.exists():
            return False
        crumb = json.loads(crumb_path.read_text(encoding="utf-8"))
        if not isinstance(crumb, dict):
            return False
        if crumb.get("run_started_at") != started_at:
            return False
        return crumb.get("interventions_covered") is True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def clear_efficacy_breadcrumb() -> None:
    """Remove the efficacy-flush breadcrumb (best-effort).  Called by --run-end
    AFTER the gate passes and the marker is deleted, so the next run starts clean
    (run-scoping already prevents a stale breadcrumb from satisfying a later gate;
    this is tidy-up, not correctness)."""
    try:
        crumb_path = claude_state_dir(create=False) / _EFFICACY_BREADCRUMB_FILENAME
        if crumb_path.exists():
            crumb_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# harness-telemetry-ledger — the telemetry ledger (sibling of the deny ledger).
#
# An append-only JSONL ledger of the pipeline's deterministic chokepoint events
# (run/cycle brackets, dispatches, halts, gate/containment refusals, pseudo-skill
# completions, sentinel resolutions — the D4-B vocabulary), written by BOTH state
# scripts through this ONE shared emitter (D2-A: parity by construction) into the
# per-repo keyed state dir beside lazy-deny-ledger.jsonl.
#
# Contract (clones the deny-ledger precedent wholesale):
#   - MARKER-GATED (D3-A): no live run marker → no write, no file, return False.
#     Bare probes and unmarked interactive invocations stay side-effect-free.
#     The marker read here is RAW and NON-DESTRUCTIVE (never read_run_marker,
#     whose stale path DELETES the marker) — emission also fires from exit-3
#     refusal paths that promise ZERO side effects.
#   - FAIL-OPEN (D2-A): plain `open(..., "a")` append (never _atomic_write — an
#     atomic rewrite adds a read-modify-write race on an append-only file whose
#     torn final line the reader already tolerates); every exception is
#     swallowed → False. The emitter NEVER calls _diag — a failed append must
#     not perturb the diagnostics[] surface of the op it rides on.
#   - RAW EVENTS ONLY (D9-A): metrics are derived reader-side
#     (pipeline_visualizer/trends.py); nothing here aggregates.
#   - ROTATION (D6-B): at emit time an over-cap active file rotates to `.1`
#     (shifting `.1`→`.2` … and dropping the oldest beyond
#     _TELEMETRY_ROTATED_SEGMENTS); a rotation failure degrades to plain append.
# ---------------------------------------------------------------------------

_TELEMETRY_LEDGER_FILENAME = "lazy-telemetry.jsonl"
_TELEMETRY_SCHEMA_VERSION = 1
_TELEMETRY_ROTATE_BYTES = 10 * 1024 * 1024  # D6-B: 10 MB active-file cap
_TELEMETRY_ROTATED_SEGMENTS = 4             # D6-B: .1 (newest) … .4 (oldest)

# D4-B: the dispatch terminal_reasons that ALSO emit a `halt` event (the
# halt-dwell start marker; the matching `sentinel-resolved` ends the dwell).
TELEMETRY_HALT_TERMINAL_REASONS: frozenset[str] = frozenset({
    "blocked",
    "needs-input",
    "needs-spec-input",
    "needs-research",
    "completion-unverified",
    "blocked-misnamed",
})


def _telemetry_run_marker(now: float | None = None) -> dict | None:
    """RAW, NON-destructive run-marker read for telemetry gating (D3-A).

    Returns the marker dict when a well-formed, age-fresh (≤24h) marker exists;
    otherwise None. Unlike ``read_run_marker`` this NEVER deletes a stale or
    corrupt marker and NEVER applies session-id gating — the emitter is called
    from refusal paths whose contract is "zero side effects", and from any
    session that runs a marker-gated op (the run identity is the marker's, not
    the caller's). Mirrors ``refuse_run_start_clobber``'s own raw read.

    Args:
        now: epoch float for the age check (injectable for hermetic tests).
    """
    if now is None:
        now = time.time()
    try:
        marker_path = claude_state_dir(create=False) / _MARKER_FILENAME
        if not marker_path.exists():
            return None
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict):
            return None
        started_at_str = marker.get("started_at", "")
        started_dt = datetime.datetime.strptime(
            started_at_str, "%Y-%m-%dT%H:%M:%SZ"
        )
        started_epoch = (
            started_dt - datetime.datetime(1970, 1, 1)
        ).total_seconds()
        if now - started_epoch > _MARKER_STALE_SECONDS:
            return None  # age-stale → gated; deletion is read_run_marker's job
        return marker
    except Exception:  # noqa: BLE001
        # Fail-open gate: any read/parse error means "no live run" → no emit.
        return None


def _rotate_telemetry_segments(ledger_path: Path) -> None:
    """D6-B size-based rollover, called at emit time BEFORE the append.

    When the active file is at/over ``_TELEMETRY_ROTATE_BYTES``: drop the oldest
    segment (``.N``), shift ``.i`` → ``.i+1``, and rename the active file to
    ``.1``. Best-effort — any failure returns silently so the caller degrades to
    a plain append on the (over-cap) active file rather than losing the event.
    """
    try:
        if not ledger_path.exists():
            return
        if ledger_path.stat().st_size < _TELEMETRY_ROTATE_BYTES:
            return
        oldest = Path(f"{ledger_path}.{_TELEMETRY_ROTATED_SEGMENTS}")
        if oldest.exists():
            oldest.unlink()
        for i in range(_TELEMETRY_ROTATED_SEGMENTS - 1, 0, -1):
            src = Path(f"{ledger_path}.{i}")
            if src.exists():
                src.rename(Path(f"{ledger_path}.{i + 1}"))
        ledger_path.rename(Path(f"{ledger_path}.1"))
    except OSError:
        # Degrade to plain append on the over-cap active file — never raise.
        return


def append_telemetry_event(
    event: str,
    *,
    item_id: str | None = None,
    data: dict | None = None,
    now: float | None = None,
) -> bool:
    """Append one telemetry event to the telemetry ledger (JSONL), best-effort.

    The ONE shared writer both state scripts (and the shared exit-3 refusal
    helpers) call at their CLI write-path chokepoints (D2-A / D3-A). Envelope
    (D1-A), one compact JSON object per line:

        {"v": 1, "ts": <epoch float>, "run_id": <marker started_at>,
         "pipeline": "feature"|"bug", "event": "<type>",
         "item_id": <str|None>, "data": {…}}

    MARKER-GATED: no live (age-fresh) run marker → nothing is written and False
    is returned — bare probes / unmarked interactive invocations never create
    the ledger. FAIL-OPEN: swallows every exception and returns False; callers
    never branch on the return value (telemetry can never block the pipeline).
    The ledger line is observability, not state — a refused op that emits one
    still has zero STATE side effects.

    Args:
        event: the D4-B event type (e.g. "run-start", "dispatch", "gate-refusal").
        item_id: the feature/bug id the event concerns (None for run-level events).
        data: small per-event payload map (untyped by design — D1-A).
        now: epoch float for ts + the marker age gate (injectable for tests).

    Returns:
        True iff a line was appended; False when gated or on any write failure.
    """
    if now is None:
        now = time.time()
    try:
        marker = _telemetry_run_marker(now=now)
        if marker is None:
            return False  # D3-A: no live run → no emit
        entry = {
            "v": _TELEMETRY_SCHEMA_VERSION,
            "ts": now,
            "run_id": marker.get("started_at"),
            "pipeline": marker.get("pipeline"),
            "event": event,
            "item_id": item_id,
            "data": data or {},
        }
        ledger_path = claude_state_dir() / _TELEMETRY_LEDGER_FILENAME
        _rotate_telemetry_segments(ledger_path)
        # Plain append (not _atomic_write) — deny-ledger precedent: append-only
        # file, torn final line tolerated by the reader.
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: a telemetry write must never propagate.
        return False


def read_telemetry_events(
    paths: "list[Path] | None" = None,
    with_provenance: bool = False,
) -> list[dict]:
    """Read telemetry events, skipping unparseable lines and unknown ``v``.

    Default path set: the rotated segments OLDEST-first (``.4`` → ``.1``) then
    the active file, so the returned list is in chronological append order
    across the whole retained window (D6-B). A missing file / unreadable path /
    torn line / non-dict line / line whose ``v`` is not a known schema version
    is skipped, never fatal (D1-A: tolerate what you don't understand).

    Args:
        paths: explicit files to read (e.g. committed cloud segments); None →
            the state-dir default set.
        with_provenance: when True, stamp ``_source`` (str path) and ``_line``
            (1-based physical line number) onto each event for the retro's
            per-figure ledger citations (D8). Default False keeps the envelope
            pure for aggregation.

    Returns:
        The list of parsed event dicts in file/line order.
    """
    if paths is None:
        base = claude_state_dir(create=False)
        active = base / _TELEMETRY_LEDGER_FILENAME
        paths = [
            Path(f"{active}.{i}")
            for i in range(_TELEMETRY_ROTATED_SEGMENTS, 0, -1)
        ] + [active]
    events: list[dict] = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue  # torn append — skip, never brick the ledger
            if not isinstance(obj, dict):
                continue
            if obj.get("v") != _TELEMETRY_SCHEMA_VERSION:
                continue  # unknown schema version — a future writer's line
            if with_provenance:
                obj = dict(obj)
                obj["_source"] = str(p)
                obj["_line"] = lineno
            events.append(obj)
    return events


def flush_cloud_telemetry_segment(
    repo_root: Path,
    *,
    now: float | None = None,
) -> dict | None:
    """D5-B cloud run-end flush: persist the live cloud run's ledger segment
    into the repo so it survives the container.

    Called by both scripts' ``--run-end`` handlers AFTER the run-end emission
    and BEFORE ``delete_run_marker`` (the marker supplies the run identity).
    Gated on a live marker with ``cloud: true`` — workstation runs return None
    untouched. Filters the state-dir ledger to lines whose ``run_id`` equals
    the marker's ``started_at`` and writes them (one-shot, via _atomic_write —
    this is a segment REWRITE, not an append-only file) to:

        <repo_root>/docs/telemetry/cloud/<run_id with colons stripped>.jsonl

    The colon-strip keeps the committed filename legal on a Windows checkout
    (run_id is ``2026-07-04T09:12:03Z``); each line's ``run_id`` FIELD is
    unchanged, so aggregation keys on content, never the filename. Zero
    matching events → None (nothing to persist; pre-feature byte-identity).
    Fail-open: any error returns None and never blocks the run-end.

    Args:
        repo_root: the repo the segment lands in (rides the final cloud push).
        now: epoch float for the marker age gate (injectable for tests).

    Returns:
        {"path": <str>, "events": <int>} when a segment was written, else None.
    """
    try:
        marker = _telemetry_run_marker(now=now)
        if marker is None or not marker.get("cloud"):
            return None
        run_id = marker.get("started_at")
        if not run_id:
            return None
        lines = [
            e for e in read_telemetry_events() if e.get("run_id") == run_id
        ]
        if not lines:
            return None
        seg_dir = Path(repo_root) / "docs" / "telemetry" / "cloud"
        seg_dir.mkdir(parents=True, exist_ok=True)
        seg_path = seg_dir / (run_id.replace(":", "") + ".jsonl")
        _atomic_write(
            seg_path, "\n".join(json.dumps(e) for e in lines) + "\n"
        )
        return {"path": str(seg_path), "events": len(lines)}
    except Exception:  # noqa: BLE001
        # Fail-open: the flush must never block --run-end.
        return None


# ---------------------------------------------------------------------------
# intervention-efficacy-tracking — the hypothesis ledger (capture half).
#
# Every shipped harness change is an implicit hypothesis ("this change will
# move friction signal X in direction D"). Capture writes a deterministic,
# script-owned intervention record (a frontmatter-sentinel markdown file at
# docs/interventions/<id>.md — committed, durable, GitHub-mobile readable;
# D4-A central residency) at the completion chokepoint:
#
#   * apply_pseudo __mark_complete__ / __mark_fixed__ — ONE shared call site,
#     so both pipelines inherit capture by construction (D1-A). Eligibility:
#     a top-level `"interventions": true` in docs/features/queue.json (the
#     `"autodiscover": true` precedent — only claude-config sets it) OR a
#     present `## Intervention Hypothesis` SPEC block. Otherwise the
#     completion is byte-identical to pre-feature (no keys, no file).
#   * the orchestrator-only `--record-intervention` CLI on BOTH state scripts
#     (the /harden-harness round path, manual capture, and the D9 opt-in
#     backfill — `--shipped-commit`/`--shipped-date` stamp
#     `provenance: backfilled`, mirroring `backfilled-unverified` honesty).
#
# The baseline is FROZEN into the record at capture time (D3): the raw
# telemetry ledger is untracked + rotation-eligible, so verdicts must never
# depend on raw-event retention. Missing/undeclared inputs degrade honestly
# (`unavailable` / `not-computable` / `target_signal: undeclared`) — capture
# NEVER errors a completion (D2-A: fail-open to a warnings entry).
#
# The evaluation half lives OFF the state-script compute path in
# user/scripts/efficacy-eval.py (the toolify-miner/lazy-queue-doc precedent),
# which re-reads these records via parse_sentinel and re-writes them through
# the same _render_intervention_record serializer (diff-stable field order).
# ---------------------------------------------------------------------------

# D5-A declared defaults — one block, per-record overridable via the
# `## Intervention Hypothesis` block (baseline_runs / review_after_runs /
# min_sample / band_pct). Starting points to be tuned by this feature's own
# ledger, not laws.
INTERVENTION_BASELINE_RUNS = 20
INTERVENTION_REVIEW_AFTER_RUNS = 20
INTERVENTION_MIN_SAMPLE = 5
INTERVENTION_BAND_PCT = 20

_INTERVENTIONS_DIRNAME = "interventions"

_INTERVENTION_HYPOTHESIS_HEADING_RE = re.compile(
    r"(?mi)^##\s+Intervention Hypothesis\s*$"
)
_INTERVENTION_FIELD_RE = re.compile(r"^[-*]\s*([a-z_]+)\s*:\s*(.+?)\s*$")
# The three signal_independence enum heads (D3); the justification sentence
# rides in `signal_independence_note` and the record body.
_INTERVENTION_INDEPENDENCE_ENUM = ("independent", "self-emitted", "mixed")
_INTERVENTION_INT_FIELDS = (
    "review_after_runs", "baseline_runs", "min_sample", "band_pct",
    "canary_window_runs",
)


def parse_intervention_hypothesis(spec_text: str) -> dict | None:
    """Parse a SPEC's ``## Intervention Hypothesis`` block (D2-A).

    Returns a dict of the declared fields, or None when the heading is absent
    (the degrade-on-absence discriminator — an absent block still captures,
    as ``target_signal: undeclared``). Recognized list-item fields:
    ``target_signal``, ``expected_direction``, ``signal_independence`` (enum
    head extracted to the field; the full raw value — including a wrapped
    justification continuation line — lands in ``signal_independence_note``),
    ``review_after_runs`` and the optional D5 overrides ``baseline_runs`` /
    ``min_sample`` / ``band_pct`` (ints; a malformed int is OMITTED, never
    raised — capture must never break a completion).
    """
    m = _INTERVENTION_HYPOTHESIS_HEADING_RE.search(spec_text or "")
    if m is None:
        return None
    fields: dict = {}
    raw: dict[str, str] = {}
    current: str | None = None
    for line in spec_text[m.end():].splitlines():
        if line.startswith("##"):
            break  # next section — the block has ended
        stripped = line.strip()
        if not stripped:
            current = None
            continue
        fm = _INTERVENTION_FIELD_RE.match(stripped)
        if fm:
            current = fm.group(1)
            raw[current] = fm.group(2)
            continue
        if current is not None and line[:1] in (" ", "\t"):
            # Wrapped continuation of the previous list item (the SPEC's UX
            # example wraps the signal_independence justification).
            raw[current] = raw[current] + " " + stripped
            continue
        current = None  # non-field prose — stop folding
    for key in ("target_signal", "expected_direction",
                "canary_degraded_revert_note"):
        if key in raw:
            fields[key] = raw[key]
    # canary_revert_unsafe (bool, D5 degraded-note trigger): tolerant truthy.
    if "canary_revert_unsafe" in raw:
        fields["canary_revert_unsafe"] = (
            raw["canary_revert_unsafe"].strip().lower()
            in ("true", "yes", "1", "on")
        )
    if "signal_independence" in raw:
        value = raw["signal_independence"]
        head = value.split()[0].rstrip(":,;") if value.split() else value
        fields["signal_independence"] = (
            head if head in _INTERVENTION_INDEPENDENCE_ENUM else value
        )
        fields["signal_independence_note"] = value
    for key in _INTERVENTION_INT_FIELDS:
        if key in raw:
            try:
                fields[key] = int(raw[key])
            except (TypeError, ValueError):
                pass  # malformed int → omitted (defaults apply downstream)
    return fields


def _intervention_signal_event(target_signal: str) -> str | None:
    """Return the ledger event type for an ``event:<type>`` target, else None.

    ``kpi:<system>.<kpi-id>`` targets are carried VERBATIM on the record and
    resolve through the friction-kpi-registry (soft dep) at evaluation time —
    this helper deliberately does NOT resolve them (the evaluator owns the
    resolution seam and degrades a miss to ``INCONCLUSIVE (kpi-unresolvable)``).
    """
    if isinstance(target_signal, str) and target_signal.startswith("event:"):
        return target_signal[len("event:"):] or None
    return None


# The CLOSED vocabulary of telemetry event types (intervention-target-signal-
# validation). These are the exact string literals passed as the FIRST
# POSITIONAL argument to every ``append_telemetry_event(...)`` call site
# across lazy_core.py / lazy-state.py / bug-state.py — the D4-B ledger
# vocabulary plus ``sentinel-provisionalized``. Kept in lockstep with the
# real emitters by the AST-driven lock test
# ``test_intervention_event_vocabulary_matches_live_emit_set`` (never edit
# this set without re-running that test — a silent drift here would let
# ``validate_intervention_target_signal`` accept/reject the wrong things).
_INTERVENTION_EVENT_VOCABULARY: frozenset[str] = frozenset({
    "run-start",
    "run-end",
    "cycle-begin",
    "cycle-end",
    "pseudo-applied",
    "dispatch",
    "halt",
    "sentinel-resolved",
    "gate-refusal",
    "containment-refusal",
    "sentinel-provisionalized",
})


def validate_intervention_target_signal(target_signal: str) -> str | None:
    """Validate an intervention hypothesis ``target_signal`` string. PURE.

    Only ``event:<type>`` targets are checked against the closed
    ``_INTERVENTION_EVENT_VOCABULARY``: an unknown type returns a
    human-readable error string naming the valid set. A ``kpi:<sys>.<id>``
    target, the literal ``"undeclared"``, or any other non-``event:`` string
    is always valid (returns ``None``) — kpi targets resolve later through
    the friction-kpi-registry, and ``undeclared`` is the honest no-hypothesis
    default.
    """
    if isinstance(target_signal, str) and target_signal.startswith("event:"):
        ev_type = target_signal[len("event:"):]
        if ev_type in _INTERVENTION_EVENT_VOCABULARY:
            return None
        valid = ", ".join(sorted(_INTERVENTION_EVENT_VOCABULARY))
        return (
            f"unknown intervention event type {ev_type!r}; "
            f"valid event types: {valid}"
        )
    return None


def _originating_telemetry_paths(current_repo_root, *, now: float | None = None) -> "list[Path]":
    """Resolve the telemetry-ledger paths of the run's ORIGINATING TARGET repo
    (interventions-telemetry-repo-scope-split-brain D1 v1).

    The interventions-bearing repo (claude-config) must be evaluated against the
    TARGET repo's runs' telemetry, which appends to the TARGET's repo_key-keyed
    state dir (the split-brain). Find the MOST-RECENT live (age <= _MARKER_STALE_SECONDS)
    run marker in a keyed sibling state dir whose recorded repo_root differs from
    current_repo_root, and return that keyed dir's telemetry ledger + rotated
    segments, OLDEST-first (matching read_telemetry_events' default ordering).

    RAW, NON-destructive marker reads (never read_run_marker — its age gate
    deletes a stale marker). No state-dir creation on this read path. FAIL-OPEN:
    any error contributes nothing -> returns [].
    """
    if now is None:
        now = time.time()
    try:
        override = os.environ.get("LAZY_STATE_DIR")
        base = Path(override) if override else (Path.home() / ".claude" / "state")
        if not base.is_dir():
            return []
        current_key = repo_key(str(current_repo_root))
        best_dir: Path | None = None
        best_started: float | None = None
        for d in sorted(base.iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            try:
                marker_path = d / _MARKER_FILENAME
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if not isinstance(marker, dict):
                    continue
                started_at_str = marker.get("started_at", "")
                started_dt = datetime.datetime.strptime(
                    started_at_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                started_epoch = (
                    started_dt - datetime.datetime(1970, 1, 1)
                ).total_seconds()
                if now - started_epoch > _MARKER_STALE_SECONDS:
                    continue  # stale
                marker_repo_root = marker.get("repo_root")
                if repo_key(str(marker_repo_root)) == current_key:
                    continue  # self-exclusion
            except Exception:  # noqa: BLE001
                continue  # unparseable marker in this subdir — skip it
            if best_started is None or started_epoch > best_started:
                best_started = started_epoch
                best_dir = d
        if best_dir is None:
            return []
        active = best_dir / _TELEMETRY_LEDGER_FILENAME
        return [
            Path(f"{active}.{i}")
            for i in range(_TELEMETRY_ROTATED_SEGMENTS, 0, -1)
        ] + [active]
    except Exception:  # noqa: BLE001
        return []


def read_intervention_telemetry(repo_root: Path) -> list[dict]:
    """Merged, deduped, chronological telemetry read for intervention windows.

    State-dir ledger (``read_telemetry_events`` — rotated segments + active
    file) PLUS any committed cloud segments under
    ``<repo_root>/docs/telemetry/cloud/*.jsonl`` (the trends-aggregator read
    pattern — cloud runs' events survive only as committed segments) PLUS the
    run's originating target repo's keyed-sibling ledger (see
    ``_originating_telemetry_paths`` — interventions-telemetry-repo-scope-split-brain
    D1 v1). Deduped on ``(run_id, ts, event, item_id)``; sorted by
    ``(run_id, ts)`` so consumers see run-grouped chronological order.
    Read-only and fail-open — any error contributes nothing rather than raising.
    """
    events = list(read_telemetry_events())
    try:
        seg_dir = Path(repo_root) / "docs" / "telemetry" / "cloud"
        if seg_dir.is_dir():
            seg_paths = sorted(seg_dir.glob("*.jsonl"))
            if seg_paths:
                events += read_telemetry_events(paths=seg_paths)
    except OSError:
        pass
    try:
        sibling_paths = _originating_telemetry_paths(repo_root)
        if sibling_paths:
            events += read_telemetry_events(paths=sibling_paths)
    except OSError:
        pass
    seen: set = set()
    merged: list[dict] = []
    for e in events:
        key = (e.get("run_id"), e.get("ts"), e.get("event"), e.get("item_id"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda e: (e.get("run_id") or "", e.get("ts") or 0.0))
    return merged


# The record's frontmatter field order — ONE serializer owns it so capture
# writes and evaluator re-writes stay diff-stable.
_INTERVENTION_FIELD_ORDER = (
    "kind", "intervention_id", "pipeline", "provenance", "shipped_date",
    "shipped_commit", "commit_set", "target_signal", "expected_direction",
    "signal_independence", "baseline", "review_after_runs", "min_sample",
    "band_pct", "review_count", "status", "escalated",
    "reconsideration_enqueued",
)


def _render_intervention_record(meta: dict, body: str) -> str:
    """Serialize an intervention record (frontmatter sentinel form, D3).

    Field order follows ``_INTERVENTION_FIELD_ORDER`` (unknown extras append
    in insertion order). ``yaml.safe_dump`` handles the nested ``baseline:``
    map, None → ``null``, and QUOTES strings that would otherwise re-parse as
    timestamps (run ids / dates) — so ``parse_sentinel`` round-trips every
    value type-preserved (the SPEC's formerly-deferred empirical check).
    """
    ordered: dict = {}
    for key in _INTERVENTION_FIELD_ORDER:
        if key in meta:
            ordered[key] = meta[key]
    for key, value in meta.items():
        if key not in ordered:
            ordered[key] = value
    fm = yaml.safe_dump(
        ordered, sort_keys=False, default_flow_style=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{fm}\n---\n\n{body.rstrip()}\n"


# ---------------------------------------------------------------------------
# harness-change-canary-rollback Phase 1 — canary registration helpers.
#
# A shipped control-surface change enters a canary observation window: at
# capture time (record_intervention below), if the change's touched-file set
# (from the provenance change->commit-set mapping) intersects the
# control-surface manifest, the record gains a `canary:` sub-map. All the
# defaults live in ONE constants block; the manifest, when present, takes
# precedence over the canary-owned fallback glob constant (which mirrors the
# anti-overfit-design-gate's initial control-surface set until
# docs/gate/control-surfaces.json ships). Read-only + fail-open throughout —
# capture must NEVER error a completion.
# ---------------------------------------------------------------------------

# Window defaults (D2-A): next 10 completed runs after ship, 30-day ceiling.
CANARY_WINDOW_RUNS_DEFAULT = 10
CANARY_WINDOW_DAYS_CEILING = 30

# The canary-owned fallback control-surface set — used only when
# docs/gate/control-surfaces.json is absent (anti-overfit-design-gate ships
# that manifest; the manifest takes precedence when present). Mirrors the
# anti-overfit SPEC's initial set. Segment-aware glob semantics: `**` crosses
# directory separators, `*`/`?` stay within a path segment.
_CANARY_CONTROL_SURFACES_FALLBACK: tuple[str, ...] = (
    "user/hooks/**",
    "user/scripts/lazy-state.py",
    "user/scripts/bug-state.py",
    "user/scripts/lazy_core.py",
    "user/scripts/lazy_guard.py",
    "user/scripts/lazy_inject.py",
    "user/scripts/lazy-parity-manifest.json",
    "user/scripts/build-queue*.ps1",
    "user/skills/lazy*/**",
    "user/skills/harden-harness/**",
    "user/skills/_components/*gate*.md",
    "user/settings.json",
)

_CANARY_CONTROL_SURFACES_FILE = ("docs", "gate", "control-surfaces.json")


def _canary_control_surfaces(repo_root: Path) -> list[str] | tuple[str, ...]:
    """Resolve the control-surface glob set (manifest-when-present, else the
    fallback constant).

    Reads ``docs/gate/control-surfaces.json`` when present — a dict carrying a
    ``globs`` / ``surfaces`` / ``control_surfaces`` list, or a bare list. Any
    read/parse failure or an unrecognized shape degrades to the fallback
    constant (never raises)."""
    manifest_path = Path(repo_root).joinpath(*_CANARY_CONTROL_SURFACES_FILE)
    try:
        if manifest_path.is_file():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            globs: list | None = None
            if isinstance(data, list):
                globs = data
            elif isinstance(data, dict):
                for key in ("globs", "surfaces", "control_surfaces"):
                    if isinstance(data.get(key), list):
                        globs = data[key]
                        break
            if globs is not None:
                cleaned = [str(g).strip() for g in globs if str(g).strip()]
                if cleaned:
                    return cleaned
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return _CANARY_CONTROL_SURFACES_FALLBACK


def _canary_glob_to_re(glob: str) -> "re.Pattern":
    """Compile a control-surface glob to an anchored regex with segment-aware
    semantics: ``**`` crosses ``/`` (any depth), ``*`` matches within a segment,
    ``?`` matches one non-separator char."""
    out: list[str] = []
    i = 0
    n = len(glob)
    while i < n:
        if glob[i:i + 2] == "**":
            out.append(".*")
            i += 2
            if i < n and glob[i] == "/":
                i += 1  # swallow the trailing slash so `a/**` matches `a/x`
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _canary_touched_files(repo_root: Path, commit_set) -> list[str]:
    """Derive the sorted, repo-relative POSIX file set touched by a commit set.

    Reuses the provenance git helper ``_git_capture_lines`` (NOT an ad-hoc
    subprocess) — one ``git show --name-only`` per sha, unioned. Any
    unresolvable sha / non-git tree contributes nothing; the result is empty
    rather than an error."""
    files: set[str] = set()
    for sha in commit_set or []:
        sha = str(sha).strip()
        if not sha:
            continue
        lines = _git_capture_lines(
            repo_root, ["show", "--name-only", "--pretty=format:", sha])
        if not lines:
            continue
        for ln in lines:
            s = ln.strip()
            if s:
                files.add(_normalize_index_key(repo_root, s))
    return sorted(files)


def _canary_intersects(touched_files, surfaces) -> tuple[bool, list[str]]:
    """Return (arm, matched_surfaces): whether any touched file matches a
    control-surface glob, and the sorted list of the matching touched files
    (the resolved file-identity ``surfaces:`` the watcher's D3 attribution
    matches incident surfaces against — repo-relative POSIX paths)."""
    pats = [_canary_glob_to_re(g) for g in (surfaces or [])]
    hits = sorted({
        f for f in (touched_files or [])
        if any(p.match(f) for p in pats)
    })
    return (bool(hits), hits)


# The coupled-pair table from the root CLAUDE.md, folded in as DATA for any
# pair absent from lazy-parity-manifest.json (D5 — the pair scope must be
# computable even for pairs the machine-readable manifest does not carry).
# Kept in lockstep with the root CLAUDE.md "Coupled Skill Pairs" table.
_CANARY_CLAUDE_MD_PAIRS: tuple[tuple[str, str], ...] = (
    ("user/skills/lazy/SKILL.md",
     "repos/algobooth/.claude/skills/lazy-cloud/SKILL.md"),
    ("user/skills/lazy-batch/SKILL.md",
     "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md"),
    ("user/skills/lazy/SKILL.md", "user/skills/lazy-bug/SKILL.md"),
    ("user/skills/lazy-batch/SKILL.md", "user/skills/lazy-bug-batch/SKILL.md"),
    ("user/skills/lazy-status/SKILL.md",
     "user/skills/lazy-bug-status/SKILL.md"),
)


def _canary_load_parity_pairs(manifest_path: Path) -> list[tuple[str, str]]:
    """Read (canonical, derived) pairs from lazy-parity-manifest.json. Any
    read/parse failure or unexpected shape degrades to an empty list (the
    caller still folds in the CLAUDE.md pairs-table data)."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    pairs: list[tuple[str, str]] = []
    for p in (data.get("pairs") if isinstance(data, dict) else None) or []:
        if not isinstance(p, dict):
            continue
        canonical = p.get("canonical")
        derived = p.get("derived")
        if isinstance(canonical, str) and isinstance(derived, str):
            pairs.append((canonical, derived))
    return pairs


_CANARY_DEFAULT_REVERT_UNSAFE_NOTE = (
    "Change flagged revert-unsafe at ship time (e.g. it migrated on-disk state "
    "or a schema). A plain `git revert` of the commit set may not fully back it "
    "out — the bug pipeline must determine actual revert feasibility with the "
    "repo checked out (v1 records this note; no `git revert` dry-run machinery)."
)


def _maybe_arm_canary(
    repo_root: Path,
    intervention_id: str,
    shipped_commit: str | None,
    hyp: dict,
    opened_date: str,
) -> dict | None:
    """Build the canary sub-map for a shipped change, or None when the change
    does not touch the control-surface manifest (D1/D5).

    Derives the touched-file + commit sets from the provenance change->commit-set
    mapping (bracket-primary, message-grep fallback, single-commit last resort),
    intersects them with the control-surface manifest, and — on a scope hit —
    returns ``{opened, window_runs, surfaces, commit_set, pair_scope,
    degraded_revert_note, status: open}`` (the frozen Phase-2 key set). Read-only
    and fail-open: any derivation miss simply yields None (no canary)."""
    touched = (derive_touched_from_brackets(repo_root, intervention_id)
               or derive_touched_from_grep(repo_root, intervention_id))
    commit_set = list(touched.get("commits") or [])
    files = list(touched.get("files") or [])
    if not commit_set and shipped_commit and shipped_commit != "unknown":
        commit_set = [shipped_commit]
    if not files:
        files = _canary_touched_files(repo_root, commit_set)
    arm, surfaces = _canary_intersects(files, _canary_control_surfaces(repo_root))
    if not arm:
        return None
    manifest_path = (
        Path(repo_root) / "user" / "scripts" / "lazy-parity-manifest.json"
    )
    pair_scope = _compute_pair_scope(files, manifest_path)
    window_runs = hyp.get("canary_window_runs")
    if not isinstance(window_runs, int) or window_runs <= 0:
        window_runs = CANARY_WINDOW_RUNS_DEFAULT
    note = hyp.get("canary_degraded_revert_note")
    if not note and hyp.get("canary_revert_unsafe"):
        note = _CANARY_DEFAULT_REVERT_UNSAFE_NOTE
    return {
        "opened": opened_date,
        "window_runs": window_runs,
        "surfaces": surfaces,
        "commit_set": commit_set,
        "pair_scope": pair_scope,
        "degraded_revert_note": note if note else None,
        "status": "open",
    }


def _compute_pair_scope(touched_files, manifest_path: Path) -> list[str]:
    """Compute the coupled-pair scope for a set of touched files (D5).

    A touched file matching EITHER half of a coupled pair yields BOTH halves in
    the scope (reverting one half of a parity-guarded pair breaks the audit).
    Pairs come from ``lazy-parity-manifest.json`` UNIONed with the root
    CLAUDE.md pairs-table entries (folded in as data for any pair the manifest
    does not carry). Result is de-duplicated, order-stable."""
    pairs = _canary_load_parity_pairs(manifest_path)
    seen_pairs = {frozenset(p) for p in pairs}
    for p in _CANARY_CLAUDE_MD_PAIRS:
        if frozenset(p) not in seen_pairs:
            pairs.append(p)
            seen_pairs.add(frozenset(p))
    touched = set(touched_files or [])
    scope: list[str] = []
    for canonical, derived in pairs:
        if canonical in touched or derived in touched:
            for half in (canonical, derived):
                if half not in scope:
                    scope.append(half)
    return scope


def record_intervention(
    repo_root: Path,
    intervention_id: str,
    *,
    pipeline: str,
    spec_path: Path | None = None,
    date: str | None = None,
    shipped_commit: str | None = None,
    shipped_date: str | None = None,
    provenance: str = "gated",
    hypothesis_overrides: dict | None = None,
) -> dict:
    """Write the intervention record for a shipped harness change (capture, D1-A).

    Freezes the baseline window from the telemetry ledger AT THIS MOMENT into
    the record (D3 — the raw ledger is untracked and rotation-eligible; the
    baseline must not depend on raw-event retention) and atomically writes the
    frontmatter-sentinel record to ``docs/interventions/<id>.md`` (D4-A).

    Hypothesis inputs, in precedence order: the ``## Intervention Hypothesis``
    block of ``spec_path``'s SPEC.md (when given), then ``hypothesis_overrides``
    (the CLI's no-SPEC path — hardening rounds). Absent both → the record is
    written ``target_signal: undeclared`` (INCONCLUSIVE-by-construction,
    surfaced for triage; completion NEVER blocked — D2-A).

    Baseline degradation is honest, never an error: ``frozen`` (trailing
    ``baseline_runs`` distinct run_ids counted for an ``event:`` target),
    ``unavailable`` (no ledger data), ``not-computable`` (undeclared or
    non-``event:`` target — kpi targets resolve at evaluation time).
    ``last_run_id`` (the post-window boundary) is recorded in every case.

    Idempotent and never-clobbering: an EXISTING file at the record path →
    noop (``{"recorded": False, "noop": True}``) — a prior capture/backfill is
    never overwritten. All writes go through ``_atomic_write``. This function
    never raises for missing/degraded inputs and never calls ``_die``; callers
    on the completion path additionally wrap it fail-open.

    Args:
        repo_root: repo the record lands in (``docs/interventions/``).
        intervention_id: item slug or ``harden-<YYYY-MM>-r<N>`` (D3).
        pipeline: ``feature`` | ``bug`` | ``hardening``.
        spec_path: the item's spec DIR (or a SPEC.md file) to read the
            hypothesis block from; None for the no-SPEC paths.
        date: ISO capture date (defaults to today).
        shipped_commit: HEAD override (D9 backfill); defaults to the repo's
            current HEAD (None on a non-git tree → recorded ``unknown``).
        shipped_date: ship-date override (D9 backfill); defaults to ``date``.
        provenance: ``gated`` (completion gate) | ``manual`` (CLI) |
            ``backfilled`` (CLI with shipped-* overrides).
        hypothesis_overrides: dict merged OVER the parsed SPEC block.

    Returns:
        ``{"recorded": bool, "noop": bool, "path": str, "target_signal": str,
        "baseline_status": str}``.
    """
    repo_root = Path(repo_root)
    if date is None:
        date = datetime.date.today().isoformat()
    record_path = (
        repo_root / "docs" / _INTERVENTIONS_DIRNAME / f"{intervention_id}.md"
    )
    if record_path.exists():
        # Never clobber a prior capture/backfill — idempotency by existence.
        return {
            "recorded": False,
            "noop": True,
            "path": str(record_path),
            "target_signal": None,
            "baseline_status": None,
        }

    # --- Hypothesis resolution (SPEC block, then overrides) ---
    hyp: dict = {}
    if spec_path is not None:
        spec_md = Path(spec_path)
        if spec_md.is_dir():
            spec_md = spec_md / "SPEC.md"
        try:
            parsed = parse_intervention_hypothesis(
                spec_md.read_text(encoding="utf-8")
            )
        except OSError:
            parsed = None
        if parsed:
            hyp.update(parsed)
    if hypothesis_overrides:
        hyp.update(
            {k: v for k, v in hypothesis_overrides.items() if v is not None}
        )
    target_signal = hyp.get("target_signal") or "undeclared"
    _rejected_target = target_signal
    _target_err = validate_intervention_target_signal(target_signal)
    if _target_err is not None:
        target_signal = "undeclared"
        _diag(
            f"record_intervention: unknown event target "
            f"'{_rejected_target}' degraded to undeclared ({_target_err})"
        )
    expected_direction = hyp.get("expected_direction") or "undeclared"
    signal_independence = hyp.get("signal_independence") or "undeclared"

    def _cfg_int(key: str, default: int) -> int:
        try:
            return int(hyp.get(key, default))
        except (TypeError, ValueError):
            return default

    review_after_runs = _cfg_int(
        "review_after_runs", INTERVENTION_REVIEW_AFTER_RUNS)
    baseline_runs_cfg = _cfg_int("baseline_runs", INTERVENTION_BASELINE_RUNS)
    min_sample = _cfg_int("min_sample", INTERVENTION_MIN_SAMPLE)
    band_pct = _cfg_int("band_pct", INTERVENTION_BAND_PCT)

    if shipped_commit is None:
        shipped_commit = head_sha_snapshot(repo_root)
    if shipped_date is None:
        shipped_date = date

    # --- Baseline freeze (read-only over the merged ledger; fail-open) ---
    try:
        events = read_intervention_telemetry(repo_root)
    except Exception:  # noqa: BLE001 — capture must never error a completion
        events = []
    run_ids = sorted({
        e.get("run_id") for e in events if e.get("run_id")
    })
    last_run_id = run_ids[-1] if run_ids else None
    ev_type = _intervention_signal_event(target_signal)
    if ev_type is None:
        baseline: dict = {
            "status": "not-computable",
            "reason": ("undeclared" if target_signal == "undeclared"
                       else "non-event-target"),
            "last_run_id": last_run_id,
        }
    elif not run_ids:
        baseline = {
            "status": "unavailable",
            "reason": "no-ledger-data",
            "last_run_id": None,
        }
    else:
        window = run_ids[-baseline_runs_cfg:]
        window_set = set(window)
        count = sum(
            1 for e in events
            if e.get("run_id") in window_set and e.get("event") == ev_type
        )
        baseline = {
            "status": "frozen",
            "runs": len(window),
            "events": count,
            "value": round(count / len(window), 4),
            "window_start_run": window[0],
            "window_end_run": window[-1],
            "last_run_id": last_run_id,
        }

    meta = {
        "kind": "intervention",
        "intervention_id": intervention_id,
        "pipeline": pipeline,
        "provenance": provenance,
        "shipped_date": shipped_date,
        "shipped_commit": shipped_commit or "unknown",
        # v1 commit_set = the capture commit; enriched to the full
        # change→commit-set mapping when code-doc-provenance-linkage ships.
        "commit_set": shipped_commit or "unknown",
        "target_signal": target_signal,
        "expected_direction": expected_direction,
        "signal_independence": signal_independence,
        "baseline": baseline,
        "review_after_runs": review_after_runs,
        "min_sample": min_sample,
        "band_pct": band_pct,
        "review_count": 0,
        "status": "open",
        "escalated": False,
        "reconsideration_enqueued": None,
    }
    note = hyp.get("signal_independence_note") or ""
    body_lines = [
        f"# Intervention: {intervention_id}",
        "",
        (f"Hypothesis: shipping `{intervention_id}` ({pipeline} pipeline) "
         f"moves `{target_signal}` in direction `{expected_direction}` "
         f"within {review_after_runs} post-ship runs."),
    ]
    if note:
        body_lines += ["", f"Signal independence: {note}"]
    body_lines += [
        "",
        "Reviews are appended below by `user/scripts/efficacy-eval.py` "
        "(`## Review <date>` sections). Do not hand-edit the frontmatter — "
        "the evaluator is its sole post-capture writer.",
    ]
    # --- Canary registration post-step (harness-change-canary-rollback D1/D5) ---
    # Arm a canary window when the shipped change touches the control-surface
    # manifest. Fail-open — a canary failure must never error a completion; a
    # non-scoped change registers no canary (byte-identical to before).
    try:
        canary = _maybe_arm_canary(
            repo_root, intervention_id, shipped_commit, hyp, shipped_date)
        if canary is not None:
            meta["canary"] = canary
    except Exception:  # noqa: BLE001 — capture must never error a completion
        pass

    _atomic_write(
        record_path, _render_intervention_record(meta, "\n".join(body_lines))
    )
    return {
        "recorded": True,
        "noop": False,
        "path": str(record_path),
        "target_signal": target_signal,
        "baseline_status": baseline["status"],
    }


def _interventions_queue_flag(repo_root: Path) -> bool:
    """True iff docs/features/queue.json carries top-level ``interventions: true``.

    The repo-opt-in capture flag (the ``autodiscover`` precedent — top-level
    sibling of ``queue``, set only by claude-config; every other repo omits it
    and completion output stays byte-identical). Read-only, defensive: a
    missing/malformed queue.json ⇒ False. The flag lives in the FEATURE queue
    for BOTH pipelines (one repo-level switch, not per-queue).
    """
    queue_path = Path(repo_root) / "docs" / "features" / "queue.json"
    if not queue_path.exists():
        return False
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, dict) and data.get("interventions") is True


def oldest_unacked_deny(*, current_run_only: bool = True) -> dict | None:
    """Return the OLDEST (FIFO) unacked deny-ledger entry, or None when there is
    no pending debt.

    Phase 8 WU-8.2: the probe's routed-hardening-debt override pre-composes a
    ``--emit-dispatch hardening`` command whose ``--context`` bindings are derived
    from this entry (``prompt_head`` → denied_prompt_summary, ``reason_head`` →
    denial_reason).  Read-only — does NOT mutate the ledger (the guard's
    allow-time ack is the only mutator now).

    ``current_run_only`` (Residual gap B, default True): mirrors
    ``pending_hardening()`` — when a live run marker exists, skip an unacked
    entry whose ``run_started_at`` does not match it (a prior/crashed run's
    leftover), so the entry bound into the hardening-dispatch command is always
    the one that actually drove ``pending_hardening() > 0`` for THIS run. When no
    live marker exists, behavior is unchanged (oldest unacked overall).
    """
    current_started = _raw_marker_started_at() if current_run_only else None
    for entry in read_deny_ledger():
        if entry.get("acked", False):
            continue
        if current_started is not None and entry.get("run_started_at") != current_started:
            continue
        return entry
    return None


def build_hardening_emit_command(
    state_script_name: str,
    *,
    item_id: str,
    oldest_deny: dict | None,
    probe_summary: str,
    registry_summary: str,
    cwd: str,
    observed_friction: dict | None = None,
) -> str:
    """Pre-compose the single-line shell command that dispatches a hardening
    round (Phase 8 WU-8.2; observed-friction branch:
    no-mid-run-observed-friction-harden-dispatch).

    The returned string is meant to be pasted verbatim into bash by the
    orchestrator when the probe withholds the forward route over pending
    hardening debt.  Every ``--context`` VALUE is shell-quoted via ``shlex.quote``
    (POSIX single-quote escaping) so embedded spaces, quotes, and newlines round-
    trip safely regardless of the host platform — the command targets ``bash`` /
    ``python3`` on the operator's machine, not the Windows host that emits it.

    Args:
        state_script_name: ``"lazy-state.py"`` or ``"bug-state.py"`` — the script
            whose ``--emit-dispatch hardening`` retires this debt.
        item_id: the current feature/bug id (becomes ``--context item_id=...``).
        oldest_deny: the oldest unacked deny-ledger entry (from
            ``oldest_unacked_deny()``), or None.  Its ``prompt_head`` /
            ``reason_head`` bind denied_prompt_summary / denial_reason; absent →
            empty strings.
        probe_summary: a compact one-line summary of the withholding probe.
        registry_summary: a short registry-state summary (e.g. "N entries, M
            unconsumed" or "empty").
        cwd: the repo root the dispatch should run against.
        observed_friction: when supplied (a dict with ``friction_summary`` /
            ``friction_detail`` / ``blocking``), build the OBSERVED-FRICTION
            command instead — ``trigger_kind=observed-friction`` driven by
            ORCHESTRATOR-SUPPLIED context, NOT a deny-ledger entry
            (no-mid-run-observed-friction-harden-dispatch §1). The emitted
            ``--context friction_summary`` / ``friction_detail`` / ``blocking``
            keys are re-bound into the template's shared @requires evidence keys
            by ``normalize_hardening_dispatch_context`` when the command runs, so
            the dispatch-hardening.md template resolves. ``oldest_deny`` is
            ignored in this mode.

    Returns:
        A single shell command string, safe to paste into bash.
    """
    def _ctx(key: str, value: str) -> str:
        # shlex.quote escapes the VALUE only; the key=value join stays literal.
        return f"--context {key}={shlex.quote(value)}"

    # no-mid-run-observed-friction-harden-dispatch §1: the observed-friction
    # branch is driven by ORCHESTRATOR-SUPPLIED context (a mid-run harness gap
    # the orchestrator named through its own reasoning), NOT a deny/friction
    # ledger entry — there is no probe withholding behind it.  The command emits
    # the friction-specific keys (friction_summary / friction_detail / blocking);
    # normalize_hardening_dispatch_context re-binds them into the shared
    # @requires evidence keys (friction_summary → denied_prompt_summary,
    # friction_detail → denial_reason) and injects observed-friction placeholders
    # for probe_json / registry_state when the emitted command actually runs, so
    # emit_dispatch_prompt does not refuse on a missing @requires key.
    if observed_friction is not None:
        friction_summary = observed_friction.get("friction_summary", "") or ""
        friction_detail = observed_friction.get("friction_detail", "") or ""
        blocking_raw = observed_friction.get("blocking", False)
        blocking_str = (
            "true"
            if (blocking_raw is True or str(blocking_raw).strip().lower() == "true")
            else "false"
        )
        parts = [
            f"python3 ~/.claude/scripts/{state_script_name}",
            "--emit-dispatch hardening",
            _ctx("trigger_kind", "observed-friction"),
            _ctx("item_id", item_id or ""),
            _ctx("friction_summary", friction_summary),
            _ctx("friction_detail", friction_detail),
            _ctx("blocking", blocking_str),
            _ctx("cwd", cwd or ""),
        ]
        return " ".join(parts)

    entry = oldest_deny or {}

    # hardening-blind-to-process-friction Phase 2: a process-friction entry
    # (kind: "process-friction", from a torn cycle bracket / unexpected commits)
    # binds trigger_kind=process-friction and surfaces the friction reason+detail.
    #
    # The dispatch-hardening.md template @requires the SHARED evidence keys
    # (denied_prompt_summary / denial_reason) for EVERY trigger_kind — it has a
    # single evidence section, not a friction-specific one.  So the friction
    # reason+detail MUST be bound INTO those keys (friction_reason →
    # denied_prompt_summary, friction_detail → denial_reason), exactly as the
    # template header + hardening-dispatch.md document.  Emitting friction-specific
    # context keys instead left denied_prompt_summary/denial_reason unbound, and
    # emit_dispatch_prompt refused the whole route ("requires context key
    # 'denied_prompt_summary' which is absent") — the broken-hardening-route defect.
    if entry.get("kind") == "process-friction":
        friction_reason = entry.get("reason_head", "") or ""
        friction_detail = entry.get("detail", "") or ""
        parts = [
            f"python3 ~/.claude/scripts/{state_script_name}",
            "--emit-dispatch hardening",
            _ctx("trigger_kind", "process-friction"),
            _ctx("item_id", item_id or ""),
            _ctx("denied_prompt_summary", friction_reason),
            _ctx("denial_reason", friction_detail),
            _ctx("probe_json", probe_summary),
            _ctx("registry_state", registry_summary),
            _ctx("cwd", cwd or ""),
        ]
        return " ".join(parts)

    denied_prompt_summary = entry.get("prompt_head", "") or ""
    denial_reason = entry.get("reason_head", "") or ""

    parts = [
        f"python3 ~/.claude/scripts/{state_script_name}",
        "--emit-dispatch hardening",
        _ctx("trigger_kind", "validate-deny"),
        _ctx("item_id", item_id or ""),
        _ctx("denied_prompt_summary", denied_prompt_summary),
        _ctx("denial_reason", denial_reason),
        _ctx("probe_json", probe_summary),
        _ctx("registry_state", registry_summary),
        _ctx("cwd", cwd or ""),
    ]
    return " ".join(parts)


# Observed-friction placeholders for the two template @requires evidence keys
# that have no meaning behind an ORCHESTRATOR-OBSERVED harness gap (there is no
# probe withholding + no registry state driving it).  Bound as literals so the
# dispatch-hardening.md template resolves for trigger_kind=observed-friction.
_OBSERVED_FRICTION_PROBE_PLACEHOLDER = (
    "observed-friction: no probe (orchestrator-observed mid-run harness gap)"
)
_OBSERVED_FRICTION_REGISTRY_PLACEHOLDER = (
    "observed-friction: n/a (not a routing/deny failure)"
)


def normalize_hardening_dispatch_context(context: dict) -> dict:
    """Normalize the ``--context`` dict for an ``--emit-dispatch hardening`` call
    so the dispatch-hardening.md template's @requires keys resolve regardless of
    trigger_kind (no-mid-run-observed-friction-harden-dispatch §1).

    Two entry shapes converge on the same template:

      * AUTO-TRIGGER (validate-deny / no-route / inject-hook-error /
        process-friction): ``build_hardening_emit_command`` already pre-binds the
        shared evidence keys (denied_prompt_summary / denial_reason / probe_json /
        registry_state), so this normalizer only defaults ``blocking`` for them.

      * OBSERVED-FRICTION (an orchestrator-observed mid-run harness gap): the
        orchestrator supplies ``friction_summary`` / ``friction_detail`` /
        ``blocking`` / ``item_id`` / ``cwd`` in place of the denial-specific keys.
        This normalizer performs the SAME rebind ``build_hardening_emit_command``'s
        process-friction branch does — friction_summary → denied_prompt_summary,
        friction_detail → denial_reason — and injects observed-friction
        placeholders for ``probe_json`` / ``registry_state`` (there is no probe or
        registry behind an observed gap), so ``emit_dispatch_prompt`` does not
        refuse on a missing @requires key.  This coupling mirrors the
        process-friction binding the existing regression test guards, so the two
        cannot silently drift.

    Non-destructive: returns a NEW dict; the caller's ``context`` is unchanged.
    A non-observed-friction context passes through with only the ``blocking``
    default added — the auto-trigger paths keep binding the shared evidence keys
    exactly as before, and the template's shared ``{blocking}`` token never goes
    unbound for them.  An explicit override of any target key is never clobbered
    (fill-only-when-absent), so the operator/composer stays authoritative.
    """
    ctx = dict(context)
    if ctx.get("trigger_kind") == "observed-friction":
        if "denied_prompt_summary" not in ctx and "friction_summary" in ctx:
            ctx["denied_prompt_summary"] = ctx["friction_summary"]
        if "denial_reason" not in ctx and "friction_detail" in ctx:
            ctx["denial_reason"] = ctx["friction_detail"]
        ctx.setdefault("probe_json", _OBSERVED_FRICTION_PROBE_PLACEHOLDER)
        ctx.setdefault("registry_state", _OBSERVED_FRICTION_REGISTRY_PLACEHOLDER)
    # `blocking` is an observed-friction concept (foreground-await vs
    # backgrounded — the §3 block/background policy); the auto-triggers have no
    # block policy.  Default it so a shared {blocking} token in the template
    # never goes unbound for the auto-trigger paths (which never supply it).
    ctx.setdefault("blocking", "n/a (auto-trigger)")
    return ctx


def ack_oldest_deny(now: float | None = None) -> dict | None:
    """Ack the OLDEST unacked deny-ledger entry (FIFO), rewriting the ledger.

    Called once per successful ``--emit-dispatch hardening`` emission so the
    one-dispatch-per-deny cadence (locked decision 4) is preserved: each hardening
    dispatch retires exactly one unit of routed hardening debt.

    The oldest unacked entry's ``acked`` flips to True and gains an ``acked_ts``.
    The whole ledger is then rewritten atomically (the file is small — one line
    per deny, bounded by run length).

    Args:
        now: epoch float for acked_ts (injectable for hermetic tests).

    Returns:
        The entry dict that was acked, or None when there were no pending
        entries (no-op — not an error).
    """
    if now is None:
        now = time.time()
    entries = read_deny_ledger()
    target: dict | None = None
    for entry in entries:
        if not entry.get("acked", False):
            entry["acked"] = True
            entry["acked_ts"] = now
            target = entry
            break
    if target is None:
        # Nothing pending — no-op, no rewrite.
        return None
    # Rewrite the whole ledger (one JSON object per line) atomically.
    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        # A rewrite failure leaves the on-disk ledger unchanged; report the ack
        # as not-applied so callers do not over-count.  The next emission retries.
        return None
    return target


def ack_all_unacked_denies(now: float | None = None) -> int:
    """Ack EVERY unacked deny-ledger entry (operator override), rewriting the ledger.

    The operator-override counterpart to ``ack_oldest_deny`` (which retires exactly
    ONE unit of debt per hardening dispatch).  Called by the ``--run-end
    --ack-unhardened`` path: when the operator explicitly authorizes retiring the
    run while hardening debt is still pending, that authorization must actually
    CLEAR the debt — otherwise the entries stay ``acked: false`` on disk and the
    NEXT run's advancing probe keeps withholding the forward route over
    ``pending-hardening-debt`` that the operator already discharged (the
    unclearable-debt deadlock — turn-routing-enforcement hardening Round 20).

    The override clears ALL unacked entries REGARDLESS of kind (validate-deny
    denials AND ``kind: process-friction`` entries) and REGARDLESS of any
    ``session_id`` field — ``pending_hardening()`` itself never filtered by
    session, so a session-less process-friction entry (written by ``--cycle-end``
    with no session_id) is exactly the entry that previously could never be
    discharged by the operator.  The operator override is a deliberate, audited
    blanket ack; it is the ONLY ack path that retires more than one entry.

    Args:
        now: epoch float for acked_ts (injectable for hermetic tests).

    Returns:
        The number of entries that were flipped from unacked → acked (0 when the
        ledger was already clean — a no-op, not an error).  On a rewrite failure
        the on-disk ledger is left unchanged and 0 is returned (the caller must
        not over-report the discharge).
    """
    if now is None:
        now = time.time()
    entries = read_deny_ledger()
    acked_count = 0
    for entry in entries:
        if not entry.get("acked", False):
            entry["acked"] = True
            entry["acked_ts"] = now
            acked_count += 1
    if acked_count == 0:
        # Nothing pending — no-op, no rewrite.
        return 0
    # Rewrite the whole ledger (one JSON object per line) atomically.
    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        # A rewrite failure leaves the on-disk ledger unchanged; report 0 acked so
        # the caller does not claim a discharge that did not persist.
        return 0
    return acked_count


def _deny_entry_same_cause_key(entry: dict) -> tuple | None:
    """Return a hashable "same cause" key for a deny-ledger entry, or ``None``
    when the entry carries no usable identity (meta-dispatch-not-by-reference-
    and-ack-overpriced Fix Scope §2).

    Prefers ``denied_sha12`` (the sha256-of-prompt identity a validate-deny
    entry always carries — a byte-identical repeat denial). Falls back to
    ``(kind, reason_head)`` for entries with no ``denied_sha12`` (e.g.
    ``kind: process-friction``, which has no dispatched-prompt sha at all) —
    an identical kind+reason repeat is the SPEC's named fallback identity.
    """
    sha = entry.get("denied_sha12")
    if sha:
        return ("sha", sha)
    reason = entry.get("reason_head")
    if reason:
        return ("reason", entry.get("kind"), reason)
    return None


def ack_deny_by_selector(
    selector: str, resolution: str, *, now: float | None = None
) -> dict:
    """Cheaply retire unacked deny-ledger entries by SELECTOR, WITHOUT a full
    hardening dispatch (meta-dispatch-not-by-reference-and-ack-overpriced Fix
    Scope §1+§2 — the ``--ack-deny <selector> --resolution <text>`` CLI).

    Unlike ``ack_oldest_deny`` (called ONLY from a hardening dispatch reaching
    guard-allow — one full Opus round per entry), this is a cheap, audited,
    gate-free ledger operation for the two cases where a full round is
    wasteful: (a) the entry's root cause was already fixed by an earlier round
    THIS run (the redundant-second-dispatch case), (b) an explicit, recorded
    no-fix classification. It must be invoked from a CLI handler that calls
    ``refuse_if_cycle_active`` first (never reachable from a cycle subagent) —
    this function itself performs no cycle check, matching the other
    ledger-mutation helpers in this module (the CLI layer owns the guard).

    Args:
        selector: ``"oldest"`` (the FIFO-oldest unacked entry, mirroring
            ``ack_oldest_deny``'s default ordering) or a ``denied_sha12``
            value/prefix (case-insensitive, >=1 hex char) matched against the
            first unacked entry whose ``denied_sha12`` starts with it.
        resolution: REQUIRED non-empty audit note — who/why this entry is
            being retired without a hardening round. Recorded verbatim on the
            acked entry (and, deduped-mirrored, on every same-cause sibling)
            so ``/lazy-batch-retro`` can grade the op for abuse.
        now: epoch float for ``acked_ts`` (injectable for hermetic tests).

    Same-cause dedup (Fix Scope §2): after resolving the selected target entry,
    every OTHER unacked entry sharing the same cause key
    (``_deny_entry_same_cause_key`` — identical ``denied_sha12``, or identical
    ``kind``+``reason_head`` when no sha exists) is acked in the SAME ledger
    rewrite, with ``ack_method: "manual-ack-dedup"`` and a resolution note that
    cross-references the primary ack — so one oscillating cause never costs
    more than one unit of retirement effort, regardless of how many times it
    was denied.

    Returns:
        ``{"ok": bool, "acked": <entry dict> | None, "deduped": [<entry dict>, ...],
        "error": str | None}``. ``ok`` is False (ledger untouched) when
        ``resolution`` is blank, no unacked entry exists at all, or (sha12
        selector) no unacked entry's ``denied_sha12`` matches.
    """
    if not resolution or not resolution.strip():
        return {
            "ok": False, "acked": None, "deduped": [],
            "error": "resolution must be a non-empty audit note",
        }
    if now is None:
        now = time.time()
    entries = read_deny_ledger()

    target: dict | None = None
    if selector == "oldest":
        for entry in entries:
            if not entry.get("acked", False):
                target = entry
                break
    else:
        sel = selector.strip().lower()
        for entry in entries:
            if entry.get("acked", False):
                continue
            sha = str(entry.get("denied_sha12") or "")
            if sha and sha.lower().startswith(sel):
                target = entry
                break

    if target is None:
        return {
            "ok": False, "acked": None, "deduped": [],
            "error": f"no unacked deny-ledger entry matches selector {selector!r}",
        }

    resolution = resolution.strip()
    target["acked"] = True
    target["acked_ts"] = now
    target["ack_method"] = "manual-ack"
    target["resolution"] = resolution

    deduped: list[dict] = []
    cause_key = _deny_entry_same_cause_key(target)
    if cause_key is not None:
        for entry in entries:
            if entry is target or entry.get("acked", False):
                continue
            if _deny_entry_same_cause_key(entry) == cause_key:
                entry["acked"] = True
                entry["acked_ts"] = now
                entry["ack_method"] = "manual-ack-dedup"
                entry["resolution"] = (
                    f"same-cause dedup of the entry acked at {now}: {resolution}"
                )
                deduped.append(entry)

    try:
        ledger_path = claude_state_dir() / _DENY_LEDGER_FILENAME
        body = "".join(json.dumps(e) + "\n" for e in entries)
        _atomic_write(ledger_path, body)
    except Exception:  # noqa: BLE001
        return {
            "ok": False, "acked": None, "deduped": [],
            "error": "ledger rewrite failed",
        }
    return {"ok": True, "acked": target, "deduped": deduped, "error": None}


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


# ---------------------------------------------------------------------------
# operator-halt-notifications — the script-owned halt notifier
# ---------------------------------------------------------------------------
#
# A NEEDS_INPUT.md/BLOCKED.md halt is honest but passive: it sits silently
# until the operator checks in.  notify_halt() pages the operator's phone at
# the terminal-emission chokepoint — called as ONE line by BOTH state scripts'
# main() immediately before the state-JSON write (D2; parity surface #7 in
# lazy_parity_audit.py).  Contracts (SPEC docs/features/operator-halt-notifications,
# all decisions operator-approved 2026-07-04):
#
#   D1  ntfy behind a minimal channel seam: notify_halt dispatches through an
#       injected `sender(title, body, link)` callable (hermetic tests inject a
#       fake); production binds _ntfy_send — one stdlib urllib POST to the
#       configured topic URL.
#   D3  Attention terminals only (_NOTIFY_ATTENTION_TERMINALS, the locked
#       11-terminal list) page by default; the 5 named clean stops
#       (_NOTIFY_CLEAN_STOP_TERMINALS) page only under notify_on_clean_stop.
#       NOTE: a sibling of SANCTIONED_STOP_TERMINAL, NOT its complement —
#       needs-research / queue-blocked-on-research / queue-missing are
#       sanctioned stops that still demand operator action.  The telemetry
#       TELEMETRY_HALT_TERMINAL_REASONS set is a DIFFERENT vocabulary
#       (halt-dwell recording) and deliberately not shared.
#   D4  Notify-once per sentinel identity (_notify_identity): sentinel-backed
#       terminals key on (pipeline, item, reason, mtime_ns, size) — a
#       --neutralize-sentinel rename retires the identity, a re-halt's new
#       sentinel re-arms; sentinel-less terminals key on the UTC date.
#   D5  Rich payload: title = notify_message verbatim; body = repo basename ·
#       pipeline · item · halt kind (+ needs-input `decisions:` one-liners via
#       a TOLERANT frontmatter read — parse_sentinel would _die() on a
#       malformed file, corrupting the halt JSON, so it is NOT used here);
#       link = the normalized GitHub remote + /tree/main/<item dir> (remote
#       derivation failure ⇒ link omitted, still send).
#   D7  Config: ~/.claude/notify.json (untracked; {channel, url,
#       notify_on_clean_stop, reping_hours}) with LAZY_NOTIFY_URL overriding
#       the url and LAZY_NOTIFY_DISABLE=1 as the kill switch.  Absent config ⇒
#       notify_halt is a COMPLETE no-op (byte-identical probe, zero writes).
#   D8  Dedup ledger notify-ledger.json in claude_state_dir() (per-repo keyed;
#       LAZY_STATE_DIR-hermetic), written via _atomic_write, entries older
#       than 30 days dropped on write; updated ONLY on a successful send.
#   D9  Fail-OPEN: nothing here may raise, print to stdout, or change the exit
#       code.  Send failure → notify-error.json breadcrumb (single overwritten
#       file, the hook-error.json pattern) + a "why no page" line appended to
#       state["diagnostics"] (the dict's own list — a _diag() call after
#       compute_state cannot reach the printed JSON), NO ledger entry (the
#       next observation retries).
#   D10 Environment-agnostic: no --cloud branch; cloud containers provision
#       LAZY_NOTIFY_URL via env.
# ---------------------------------------------------------------------------

_NOTIFY_CONFIG_FILENAME = "notify.json"          # under ~/.claude/ (untracked)
_NOTIFY_LEDGER_FILENAME = "notify-ledger.json"   # under claude_state_dir()
_NOTIFY_ERROR_FILENAME = "notify-error.json"     # under claude_state_dir()
# Same bound as _default_sidecar_probe / _default_frontend_probe (D9).
_NOTIFY_SEND_TIMEOUT_SECONDS = 5
_NOTIFY_LEDGER_MAX_AGE_SECONDS = 30 * 24 * 3600  # D8: 30-day prune on write

# D3 (locked 2026-07-04): the terminals where the operator's action is the
# unblocker — these page by default.
_NOTIFY_ATTENTION_TERMINALS: frozenset[str] = frozenset({
    "blocked",
    "blocked-misnamed",
    "needs-input",
    "needs-spec-input",
    "needs-research",
    "queue-blocked-on-research",
    "completion-unverified",
    "stale_upstream",
    "queue-exhausted-all-parked",
    "queue-exhausted-budget-deferred",
    "queue-missing",
})

# D3: clean run-end terminals — page ONLY when the config sets
# notify_on_clean_stop: true.  Everything in neither set never pages (e.g.
# queue-exhausted-dependency-gated: holds re-open by themselves as deps
# complete; scoped per-item terminals: the run continues past them).
_NOTIFY_CLEAN_STOP_TERMINALS: frozenset[str] = frozenset({
    "all-features-complete",
    "all-bugs-fixed",
    "cloud-queue-exhausted",
    "device-queue-exhausted",
    "host-capability-saturated",
})

# D4: terminal → candidate sentinel basenames (first existing wins) for the
# identity stat.  blocked-misnamed is special-cased onto the stray file via
# detect_noncanonical_blocker.
_NOTIFY_SENTINEL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "blocked": ("BLOCKED.md",),
    "needs-input": ("NEEDS_INPUT.md",),
    "needs-research": ("NEEDS_RESEARCH.md", "RESEARCH_PROMPT.md"),
}


def _load_notify_config() -> dict | None:
    """Resolve the notifier config (D7), or None ⇒ the feature does not exist.

    Precedence: LAZY_NOTIFY_DISABLE truthy → None (kill switch, dominates
    everything); else merge ~/.claude/notify.json (when readable/valid — a
    malformed file degrades silently, fail-open) with the LAZY_NOTIFY_URL env
    override (env wins on `url`; file booleans survive).  No usable url ⇒
    None.  Never raises, never writes.
    """
    if os.environ.get("LAZY_NOTIFY_DISABLE"):
        return None
    cfg: dict = {}
    try:
        cfg_path = Path.home() / ".claude" / _NOTIFY_CONFIG_FILENAME
        if cfg_path.is_file():
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
    except Exception:  # noqa: BLE001 — malformed/unreadable file is fail-open
        pass
    env_url = os.environ.get("LAZY_NOTIFY_URL")
    if env_url:
        cfg["url"] = env_url
    url = cfg.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    cfg.setdefault("channel", "ntfy")
    cfg["notify_on_clean_stop"] = bool(cfg.get("notify_on_clean_stop"))
    return cfg


def _notify_sentinel_path(state: dict, terminal_reason: str) -> Path | None:
    """Resolve the halt's sentinel file from the state's spec_path (D4).

    Returns the first existing candidate for the terminal (the stray file for
    blocked-misnamed), or None for sentinel-less terminals (queue-missing,
    exhaustion terminals, needs-spec-input's empty dir, …).  Never raises.
    """
    spec = state.get("spec_path")
    if not spec:
        return None
    try:
        spec_dir = Path(spec)
        if terminal_reason == "blocked-misnamed":
            return detect_noncanonical_blocker(spec_dir)
        for name in _NOTIFY_SENTINEL_CANDIDATES.get(terminal_reason, ()):
            candidate = spec_dir / name
            if candidate.is_file():
                return candidate
    except OSError:
        pass
    return None


def _notify_identity(state: dict, pipeline: str, *, now: float | None = None) -> str:
    """The D4 dedup key: one halt, one page, no matter how many probes see it.

    Sentinel-backed: ``{pipeline}|{item}|{reason}|{mtime_ns}|{size}`` — a
    rename (--neutralize-sentinel) kills the identity, a rewritten sentinel is
    a NEW identity (re-arm).  Sentinel-less: ``{pipeline}|{item}|{reason}|d:{UTC date}``
    (bounded: at most one page per day per such terminal).
    """
    reason = state.get("terminal_reason") or ""
    item = state.get("feature_id") or ""
    sentinel = _notify_sentinel_path(state, reason)
    if sentinel is not None:
        try:
            st = sentinel.stat()
            return f"{pipeline}|{item}|{reason}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            pass
    ts = time.time() if now is None else float(now)
    day = datetime.datetime.fromtimestamp(
        ts, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d")
    return f"{pipeline}|{item}|{reason}|d:{day}"


def _load_notify_ledger() -> dict:
    """Read notify-ledger.json entries ({identity: {notified_at, …}}).

    Read-only (create=False — a probe that never sends must not create the
    state dir).  Corrupt/absent ⇒ {} (fail-open).
    """
    try:
        path = claude_state_dir(create=False) / _NOTIFY_LEDGER_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        return entries if isinstance(entries, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _record_notify_send(identity: str, state: dict, pipeline: str,
                        *, now: float | None = None) -> None:
    """Ledger a successful send (D8) via _atomic_write, pruning entries older
    than 30 days.  The schema is re-ping-ready: notified_at is the timestamp a
    future reping_hours key would compare against (D4-B, additive later)."""
    ts = time.time() if now is None else float(now)
    cutoff = ts - _NOTIFY_LEDGER_MAX_AGE_SECONDS
    entries = {
        k: v for k, v in _load_notify_ledger().items()
        if isinstance(v, dict)
        and isinstance(v.get("notified_at"), (int, float))
        and v["notified_at"] >= cutoff
    }
    entries[identity] = {
        "notified_at": ts,
        "pipeline": pipeline,
        "item_id": state.get("feature_id"),
        "terminal_reason": state.get("terminal_reason"),
    }
    payload = {"v": 1, "entries": entries}
    _atomic_write(
        claude_state_dir() / _NOTIFY_LEDGER_FILENAME,
        json.dumps(payload, indent=2) + "\n",
    )


def _write_notify_error(message: str, identity: str | None,
                        *, now: float | None = None) -> None:
    """Overwrite the notify-error.json breadcrumb (the hook-error.json
    pattern: a single at-a-glance 'why no page' file, D9)."""
    entry = {
        "ts": time.time() if now is None else float(now),
        "source": "notify_halt",
        "error": str(message)[:500],
        "identity": identity,
    }
    _atomic_write(
        claude_state_dir() / _NOTIFY_ERROR_FILENAME,
        json.dumps(entry, indent=2) + "\n",
    )


def _notify_decisions(sentinel_path: Path) -> list[str]:
    """Tolerant read of a NEEDS_INPUT.md frontmatter ``decisions:`` list (≤4).

    Deliberately NOT parse_sentinel: that helper _die()s (error JSON on stdout
    + exit 2) on a malformed file, which would corrupt the halt this notifier
    merely observes (D9).  Any problem ⇒ [] (notify without decision lines).
    """
    try:
        lines = sentinel_path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines) or lines[i].strip() != "---":
            return []
        end = None
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == "---":
                end = j
                break
        if end is None:
            return []
        data = yaml.safe_load("\n".join(lines[i + 1:end])) or {}
        if not isinstance(data, dict):
            return []
        decisions = data.get("decisions")
        if not isinstance(decisions, list):
            return []
        return [str(d).strip() for d in decisions if str(d).strip()][:4]
    except Exception:  # noqa: BLE001
        return []


def _normalize_git_remote_url(raw: str | None) -> str | None:
    """Normalize a git remote URL to a plain browsable http(s) URL (D5).

    Handles scp-style SSH (git@host:owner/repo.git), ssh:// (optional user +
    port), and http(s) (credentials stripped, .git suffix dropped).  Anything
    else (file://, empty, garbage) ⇒ None — the caller omits the link and
    still sends.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    m = re.match(r"^git@([^:/]+):(.+)$", raw)
    if m:
        raw = f"https://{m.group(1)}/{m.group(2)}"
    elif raw.startswith("ssh://"):
        m2 = re.match(r"^ssh://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", raw)
        if not m2:
            return None
        raw = f"https://{m2.group(1)}/{m2.group(2)}"
    if not (raw.startswith("http://") or raw.startswith("https://")):
        return None
    scheme, rest = raw.split("://", 1)
    authority, _, tail = rest.partition("/")
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]  # strip credentials
    raw = f"{scheme}://{authority}" + (f"/{tail}" if tail else "")
    if raw.endswith(".git"):
        raw = raw[: -len(".git")]
    return raw.rstrip("/")


def _github_remote_url(repo_root: str) -> str | None:
    """``git config --get remote.origin.url`` → normalized URL, or None."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "config", "--get",
             "remote.origin.url"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            return None
        return _normalize_git_remote_url(proc.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def _compose_notify_payload(state: dict, repo_root: str,
                            pipeline: str) -> tuple[str, str, str | None]:
    """Build the D5 rich payload: (title, body, link).

    title = the script's composed notify_message verbatim (already
    item-naming); body = repo basename · pipeline · item · halt kind, the
    needs-input ``decisions:`` one-liners, and the LAZY_QUEUE/answer-path
    pointer; link = normalized remote + /tree/main/<item dir> (None when the
    remote cannot be derived — omit link, still send).
    """
    reason = state.get("terminal_reason") or ""
    title = state.get("notify_message") or f"PIPELINE HALT: {reason}"
    try:
        repo_name = Path(repo_root).name or str(repo_root)
    except Exception:  # noqa: BLE001
        repo_name = str(repo_root)
    item = state.get("feature_id") or "(no item)"
    body_lines = [f"{repo_name} · {pipeline} · {item} · {reason}"]
    if reason == "needs-input":
        sentinel = _notify_sentinel_path(state, reason)
        if sentinel is not None:
            for n, decision in enumerate(_notify_decisions(sentinel), 1):
                body_lines.append(f"{n}. {decision}")
    body_lines.append(
        "Queue: LAZY_QUEUE.md · answer in the Claude app / next session"
    )
    link = None
    base = _github_remote_url(repo_root)
    if base:
        link = base
        spec = state.get("spec_path")
        if spec:
            try:
                rel = Path(spec).resolve().relative_to(
                    Path(repo_root).resolve()
                ).as_posix()
                link = f"{base}/tree/main/{rel}"
            except Exception:  # noqa: BLE001 — spec outside root → repo link
                pass
    return title, "\n".join(body_lines), link


def _rfc2047_header(value: str) -> str:
    """Encode a header value as RFC 2047 UTF-8 Base64 when it is not
    latin-1-safe (http.client raises UnicodeEncodeError otherwise — and
    notify_message strings routinely carry em-dashes).  ntfy documents RFC
    2047 support for its Title/Click headers.  Latin-1-safe values pass
    through verbatim."""
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        import base64
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"=?UTF-8?B?{encoded}?="


def _ntfy_send(url: str, title: str, body: str, link: str | None = None) -> None:
    """The v1 ntfy channel (D1): one stdlib urllib POST to the topic URL —
    message = body, Title/Click headers, timeout=5.  Raises on failure (the
    notify_halt wrapper owns fail-OPEN)."""
    import urllib.request
    headers = {"Title": _rfc2047_header(" ".join(title.split()))}
    if link:
        headers["Click"] = _rfc2047_header(link.strip())
    req = urllib.request.Request(
        url, data=body.encode("utf-8"), headers=headers, method="POST",
    )
    with urllib.request.urlopen(  # noqa: S310 — operator-configured URL
        req, timeout=_NOTIFY_SEND_TIMEOUT_SECONDS
    ) as resp:
        resp.read()


def notify_halt(state: dict, repo_root: str, *, pipeline: str = "feature",
                sender=None, now: float | None = None) -> None:
    """Page the operator about an attention-terminal halt.  Fail-OPEN observer:
    NEVER raises, never prints to stdout, never changes the exit code, and is
    a complete no-op (zero writes, state dict untouched) without config.

    Called by BOTH state scripts' main() immediately before the state-JSON
    write (D2 — the one chokepoint every halt passes through; parity-audited).
    ``sender(title, body, link)`` is the injected channel seam (tests inject a
    fake; production binds _ntfy_send to the configured topic URL).
    """
    identity: str | None = None
    try:
        config = _load_notify_config()
        if config is None:
            return  # D7: absent config ⇒ the feature does not exist.
        reason = state.get("terminal_reason")
        if not reason:
            return  # forward routes never page
        if reason in _NOTIFY_ATTENTION_TERMINALS:
            pass
        elif (reason in _NOTIFY_CLEAN_STOP_TERMINALS
                and config.get("notify_on_clean_stop")):
            pass
        else:
            return  # D3: everything else never pages
        identity = _notify_identity(state, pipeline, now=now)
        if identity in _load_notify_ledger():
            return  # D4: already paged this halt
        title, body, link = _compose_notify_payload(state, repo_root, pipeline)
        if sender is None:
            url = config["url"]
            def sender(t, b, l, _url=url):  # noqa: E731 — production binding
                _ntfy_send(_url, t, b, l)
        diagnostics = state.get("diagnostics")
        try:
            sender(title, body, link)
        except Exception as send_exc:  # noqa: BLE001 — D9 fail-OPEN
            _write_notify_error(
                f"{send_exc.__class__.__name__}: {send_exc}", identity, now=now,
            )
            if isinstance(diagnostics, list):
                diagnostics.append(
                    "notify_halt: send failed "
                    f"({send_exc.__class__.__name__}: {send_exc}) — "
                    "notify-error.json written; halt unaffected, "
                    "no ledger entry (next observation retries)"
                )
            return
        _record_notify_send(identity, state, pipeline, now=now)
        if isinstance(diagnostics, list):
            diagnostics.append(
                f"notify_halt: paged terminal_reason={reason} "
                "(recorded in notify-ledger.json)"
            )
    except Exception as exc:  # noqa: BLE001 — D9: nothing may propagate
        try:
            _write_notify_error(
                f"internal error: {exc.__class__.__name__}: {exc}",
                identity, now=now,
            )
        except Exception:  # noqa: BLE001 — even the breadcrumb is best-effort
            pass
