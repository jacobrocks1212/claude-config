# Implementation Phases — Merged-head computation includes PARKED items → park-mode run deadlocks

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure state-script / `lazy_core` dispatch-ordering logic with no MCP-reachable app surface (per `docs/features/mcp-testing/SPEC.md`, this is harness Python whose behavior is fully observable through deterministic pytest, not the live Tauri+MCP runtime).

**Status:** In-progress

> **Provenance — fix landed out-of-pipeline.** The complete fix for this bug shipped as a
> `/harden-harness` round in commit **`a8140ff8`** ("harden(script): exclude PARKED items from
> merged-head computation") BEFORE this PHASES.md was authored, and was generalized by the
> sibling bug `docs/bugs/merged-head-excludes-parked-not-operator-deferred-deadlocks` in
> `84e656ec` (park exclusion + unconditional operator-defer exclusion unified into
> `depdag.nondispatchable_item_ids`). This PHASES.md therefore documents the landed work
> retroactively so the bug pipeline can complete its contract (validation tail → `__mark_fixed__`
> → archive). Every deliverable below is already on disk, committed, and covered by green tests
> (`user/scripts/tests/test_lazy_core/test_dispatch.py`, 32 park/exclude/nondispatchable/merged
> cases passing). No re-implementation is required — the remaining work is the orchestrator-owned
> receipt + archive.

## Cross-feature Integration Notes

- **`merged-head-excludes-parked-not-operator-deferred-deadlocks` (sibling bug, generalizes this one):** that bug widened the SPEC's proposed `depdag.parked_item_ids` resolver into `depdag.nondispatchable_item_ids`, ORing the park predicate (`docmodel.spec_dir_would_park`, this bug) with an unconditional operator-defer predicate (`docmodel.spec_dir_operator_deferred`). The shipped callers therefore call `nondispatchable_item_ids`, not the SPEC's `parked_item_ids` name — a superset that subsumes this bug's exclusion set. This is a deliberate, tested convergence, not drift.

### Phase 1: Shared park predicate + non-dispatchable resolver

**Scope:** Factor the compute_state park branches into one pure predicate and a resolver that maps queue items to the ids the merged-head computation must exclude.

**Deliverables:**
- [x] `lazy_core.docmodel.spec_dir_would_park(spec_dir, *, park_needs_input, park_blocked, park_provisional)` — pure predicate mirroring the compute_state park branches (canonical/stray `BLOCKED.md` under `--park-blocked`; unresolved `NEEDS_INPUT.md` under `--park-needs-input`, with `BLOCKED.md` precedence and provisional-eligible-routes-not-parks under `--park-provisional`). No facet active / missing dir / `None` → `False`. (`docmodel.py:2207`, committed `a8140ff8`.)
- [x] `lazy_core.depdag.nondispatchable_item_ids(feature_items, bug_items, repo_root, *, park facets)` — resolves each queue item's spec dir (features → `docs/features/<spec_dir|id>`; bugs → loader `spec_path`, else `docs/bugs/<spec_dir|id>`) and returns the excluded-id set (ORs `spec_dir_would_park` with the sibling-bug `spec_dir_operator_deferred`). No facet + no `DEFERRED.md` → empty set. (`depdag.py:1496`, committed `a8140ff8`/`84e656ec`.)
- [x] Class boundary respected — the narrow "unratified `NEEDS_INPUT_PROVISIONAL.md` + `VALIDATED.md` parks at completion" branch is deliberately OUT of scope (driveable-to-completion, not the observed deadlock), documented in both docstrings.
- [x] Tests: predicate + resolver unit coverage in `test_dispatch.py`.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes `FIXED.md` once the validation tail passes — not authored as a checkbox here.

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core/docmodel.py` — `spec_dir_would_park` (+ sibling `spec_dir_operator_deferred`).
- `user/scripts/lazy_core/depdag.py` — `nondispatchable_item_ids`.

**Testing Strategy:** deterministic pytest over the predicate/resolver — park-facet-on returns the parked ids, no-facet returns the empty set, missing/unreadable spec dirs fail-safe to not-excluded.

**Integration Notes for Next Phase:** `nondispatchable_item_ids` takes the on-disk `repo_root` the queues were loaded from (NOT the echoed `active_repo_root` on `merged_head`); Phase 2 callers pass that root and the marker-authoritative folded park facets.

---

### Phase 2: Thread `exclude_ids` through merged ordering + wire the three callers

**Scope:** Plumb the exclusion set through the single merged-ordering source and its consumers so the merged head is the highest-priority UN-PARKED actionable item, and the `merged-head-diverged` withhold fires only for genuine feature-vs-bug divergence.

**Deliverables:**
- [x] `exclude_ids` threaded through `lazy_core.depdag.merged_worklist` / `next_merged` and `lazy_core.dispatch.merged_head_override` — items whose id ∈ `exclude_ids` are filtered from the ordering. (`depdag.py:1404`/`1477`, `dispatch.py:358`, committed `a8140ff8`.)
- [x] `lazy-state.py --next-merged` computes `nondispatchable_item_ids` + passes `exclude_ids`. (`lazy-state.py:12375`.)
- [x] `lazy-state.py --emit-prompt` merged-head-override path passes `exclude_ids`. (`lazy-state.py:13842`/`13866`.)
- [x] `bug-state.py --emit-prompt` merged-head-override path passes `exclude_ids`. (`bug-state.py:9405`/`9436`.)
- [x] No-facet / marker-gated path → empty exclusion set → byte-identical to pre-fix behavior.
- [x] Tests: regression fixture in `test_dispatch.py` — top-priority bug parked + lower-priority actionable bug, park mode active: `--next-merged` returns the actionable bug (not the parked head) and `--emit-prompt` emits a clean `cycle_prompt` with NO `merged-head-diverged` withhold; no-facet byte-identical.

**Runtime Verification** *(satisfied by the committed deterministic regression fixture — no live runtime applies to this state-script change):*
- [x] Regression fixture green: `python3 -m pytest user/scripts/tests/test_lazy_core/test_dispatch.py -k "park or exclude or nondispatch or merged"` → 32 passed (verified this cycle). Asserts the SPEC's "Verified symptom / regression fixture": actionable-not-parked merged head, withhold-free emit, and no-facet byte-identical ordering.

**Completion (gate-owned):** the `__mark_fixed__` gate writes `FIXED.md` and archives the bug once the validation tail passes.

**Prerequisites:** Phase 1 (the predicate + resolver must exist for the callers to compute `exclude_ids`).

**Files likely modified:**
- `user/scripts/lazy_core/depdag.py` — `merged_worklist` / `next_merged` `exclude_ids` param.
- `user/scripts/lazy_core/dispatch.py` — `merged_head_override` `exclude_ids` param.
- `user/scripts/lazy-state.py` — `--next-merged` + `--emit-prompt` caller wiring.
- `user/scripts/bug-state.py` — `--emit-prompt` caller wiring.
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — predicate/resolver/regression-fixture coverage.

**Testing Strategy:** the committed regression fixture drives the exact deadlock scenario (parked head + actionable next, park mode) through the real `--next-merged` / `--emit-prompt` code paths and asserts the forward route is emitted; a no-facet control asserts byte-identical pre-fix ordering.

**Integration Notes for Next Phase:** none — this is the terminal implementation phase; the pipeline routes to the validation tail and the gate-owned `__mark_fixed__` completion.
