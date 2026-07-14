"""lazy_core.depdag — the queue dependency-DAG plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 2, WU-1) — a move-only refactor with zero behavior change. Owns the
optional, machine-enforced ``deps: ["<id>", ...]`` queue-entry field on BOTH
pipelines: SPEC dep-block parsing, load-time validation + cycle detection,
the --sync-deps feeder, the receipt-gated completion classifier, and the
unknown-dependency BLOCKED.md body. See docs/features/queue-dependency-dag
and user/scripts/CLAUDE.md -> "Queue dependency DAG" for the full contract.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from ._ctx import _atomic_write, _diag, _die
from .docmodel import spec_status
from .gates import has_completion_receipt


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


# lazy-core-package-decomposition Phase 5 WU-3 (residue sweep): the queue.json
# mutation ops (reorder_queue / clear_queue_stub), the merged feature+bug
# ordering plane (merged_priority / merged_worklist / next_merged + the
# severity/age-escalation/pin helpers), and the dependency-aware skip_ahead_ready
# moved here from _monolith.py — verbatim (call-graph proximity: the queue plane).

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
