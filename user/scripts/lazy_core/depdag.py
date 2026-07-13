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

import json
import re
from pathlib import Path

from ._ctx import _atomic_write, _diag
from ._monolith import _die, has_completion_receipt
from .docmodel import spec_status


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
