# Merged-head actionability oracle — Feature Specification

> Replace the ever-growing category-enumerated merged-head exclude set with a single per-item
> "would `compute_state` dispatch this item right now?" oracle, so the NEXT non-dispatchable
> category cannot re-introduce a merged-head-diverged stall.

**Status:** Draft
**Priority:** P0
**Last updated:** 2026-07-18
**Friction-reduction feature:** no

<!-- Classified `no` (advisory-vocabulary present, non-blocking D6-B): this is a
     correctness/robustness refactor eliminating a latent no-route defect class, not a feature whose
     success is a registry-measurable friction KPI. The registry's closed signal source/selector
     enums have no term for "recurrence count of a bug slug family," and forcing an existing
     selector (e.g. sentinel-scan open-halt-count) would mis-attribute an unrelated KPI. Success is
     measured informally (see ## Success Measurement). ⚖ policy: registry cannot express KPI → honest
     `no` + informal target, not a fabricated row. -->


**Depends on:** (none)

<!-- No upstream: the merged-head machinery this refactors is already shipped/archived
     (docs/bugs/_archive/merged-head-*). No downstream dependee declares this id (grep clean). -->

---

## Executive Summary

The `merged-head-diverged` withhold guard (`lazy_core.dispatch.merged_head_override`) is the
mechanical self-announcing guard that stops the unified feature+bug driver from silently
misrouting: when the merged (feature ∪ bug) work-list head diverges from the item the
dispatch-bound `--emit-prompt` probe is about to emit for — e.g. a P0 bug jumping the queue
mid-feature-run — it WITHHOLDS the (wrong-item) forward route so the orchestrator re-probes onto
the true head. For that guard to fire ONLY on a *genuine dispatchable* divergence and never behind
an item the pipeline would merely skip, the merged ordering must EXCLUDE every **non-dispatchable**
item (one that would be parked / deferred / gated / halted rather than actually worked).

Today that exclude set is the UNION of two approximating sources: `probe_skipped_ids(state, items)`
— the current per-pipeline probe's OWN skip decisions (context-rich, authoritative for the pipeline
being probed) — and `nondispatchable_item_ids(...)` — a **pure per-item file-predicate** that must
cover the OTHER (cross-pipeline) queue, which the current probe never walked. That file-predicate
source has accreted **five facets** — parked, operator-deferred, device-deferred, dep-unready,
research-skipped — each one added by its own `merged-head-diverged-withholds-on-<X>` /
`merged-head-*-deadlocks` bug (Rounds culminating 2026-07-17/18). Every time a NEW non-dispatchable
category appears, the enumeration is one facet short, the withhold fires behind an undriveable head,
and the run STALLS (no-route: null `cycle_prompt` AND null `terminal_reason`) until the facet is
hand-added. The facet list is documented in-code as inherently incomplete: its own "Scope boundary"
paragraph names cloud-deferral, `completion-unverified`, `stale_upstream`, and `needs-ratification`
as categories a pure file check *cannot* classify — "correctly classifying them needs the scoped
`compute_state` dispatch oracle, tracked by the spun-off actionability generalization." **This
feature is that generalization** (the 5th-facet bug's SPEC explicitly spun it off).

The fix replaces the file-predicate approximation with the AUTHORITATIVE decision it approximates.
`compute_state` already answers "would this item dispatch?" per item via the existing
`--feature-id` / `--bug-id` scoping (the concurrency-plane single-item flag). Running that scoped
probe per cross-pipeline candidate and classifying the item non-dispatchable iff the scoped probe
does **not** yield a forward dispatch collapses all five (and every future) file-predicate facets
into one oracle. Behavior stays **byte-identical for dispatchable heads by construction** (the
oracle *is* the dispatch decision the withhold already trusts); currently-uncovered non-dispatchable
categories (cloud/completion-unverified/…) become correctly excluded — the recurring class ends.

## User Experience

The "user" is the operator running an autonomous `/lazy-batch` / `/lazy-batch-cloud` /
`/lazy-bug-batch` run. Observable pipeline behavior:

- **Dispatchable divergence (unchanged):** a genuinely higher-priority *dispatchable* item (a P0
  bug jumping the queue mid-feature-run) still triggers the `merged-head-diverged` withhold →
  re-probe onto the true head. Byte-identical to today.
- **Non-dispatchable head (improved & future-proof):** an item at the merged head that the pipeline
  would skip/defer/park/gate/halt is EXCLUDED and the driver dispatches the real workable item — no
  stall. This already works for the five enumerated facets; after this feature it works for EVERY
  non-dispatchable category the scoped `compute_state` recognizes, including ones the enumeration
  never covered. No future `merged-head-diverged-withholds-on-<new-category>` bug can recur.
- **No new flags, no new sentinels, no new operator surface.** The change is entirely inside the
  `--emit-prompt` merged-head divergence computation. `/lazy-status`, `--next-merged`, and the
  existing `gated_heads` / `device_deferred_features` / `dep_gated` observability keys are
  unchanged; a merged-head skip stays surfaced via the same diagnostic line.

## Technical Design

### Current shape (what is being replaced)

`lazy-state.py --emit-prompt` (mirrored in `bug-state.py`), around the `merged_head_override` call:

```
_mo_excluded  = nondispatchable_item_ids(feats, bugs, repo, park_*, skip_needs_research)  # file-predicate, BOTH queues
_mo_excluded |= probe_skipped_ids(state, feats)                                           # same-pipeline probe skips
_mo_excluded.discard(state["feature_id"])                                                  # never exclude the dispatch target
merged_override = merged_head_override(feats, bugs, active_repo, state["feature_id"], exclude_ids=_mo_excluded)
```

Same exclude-set construction is duplicated at the `--next-merged` (`_nm_excluded`) and
`research_halt_head` (`_rh_excluded`) call sites.

### Target shape (the oracle)

Introduce a single actionability oracle in `lazy_core.dispatch` (shared, both pipelines):

> `merged_head_nondispatchable_ids(feature_items, bug_items, repo_root, current_item_id, *,
> same_pipeline, same_pipeline_state, <run flags>) -> set[str]`

that builds the exclude set as:

1. **Same-pipeline items → `probe_skipped_ids(state, same_pipeline_items)` unchanged.** The current
   probe's own skip decisions are the authoritative, context-rich source for its own queue — they
   already honor `--strict-research-halt`, the two-key skip-ahead readiness predicate, and the
   fully-gated terminal. This is NOT replaced (the oracle would LOSE the cross-item skip-ahead
   *ordering* context that `probe_skipped_ids` correctly captures — see Locked Decision L2).
2. **Cross-pipeline items → the actionability oracle.** For each cross-pipeline candidate, run that
   pipeline's SCOPED `compute_state` (`--feature-id` / `--bug-id` in-process) with the SAME run
   flags the emit probe used (park facets, `skip_needs_research`, `cloud`, `real_device`,
   `strict_research_halt`) and classify the item **non-dispatchable** iff the scoped probe does not
   yield a forward dispatch (`is_dispatchable(scoped_state)` false — see L3). This REPLACES
   `nondispatchable_item_ids`'s file-predicate coverage of the cross-pipeline queue with the
   authoritative decision.
3. `.discard(current_item_id)` — the dispatch target is never excluded (invariant preserved; a
   scoped probe of the current item would dispatch it anyway).

Bound the oracle to candidates ranked **at-or-above** the emitted item in the merged ordering,
short-circuiting at the first dispatchable head (L5) — a lower-priority item can never be the
diverging merged head, so it never needs an oracle evaluation.

### `is_dispatchable(scoped_state)` classification (L3)

An item's scoped `compute_state` is **dispatchable** iff it yields a real forward action:
`sub_skill` is a non-empty, non-`__`-prefixed real skill AND `terminal_reason` is not a
skip/defer/park/gate/halt reason (blocked / needs-input / needs-research / deferred-* /
dep-gated / host-/device-/cloud-deferred / completion-unverified / stale_upstream / budget-deferred
/ the exhaustion terminals). The classifier is a small closed predicate over the state dict — the
inverse of "this item would be worked right now." Preserving the research-surface path:
a `needs-research` head (WITHOUT `--skip-needs-research`) classifies non-dispatchable (it halts),
so it is excluded here — and `research_halt_head` RE-INCLUDES it exactly as today, so the operator
still sees the needs-research halt (Non-goals).

### In-process scoped-probe safety (implementation risk)

`compute_state` resets module-level accumulators (`_SKIP_AHEAD_BLOCKED`, `_GATED_HEADS`,
`_DIAGNOSTICS`, `_DEP_GATED`, …) at entry and mutates them as it walks. Calling it repeatedly
in-process for the oracle MUST NOT corrupt the primary emit probe's already-computed `state`. The
oracle runs AFTER the primary probe's `state` is captured, and each scoped call must snapshot/restore
(or the oracle must read only the returned dict, never the globals). This is a phases-level
correctness concern — see Validation Criteria.

### Files touched

- `lazy_core/dispatch.py` — add `is_dispatchable` + `merged_head_nondispatchable_ids` oracle;
  `probe_skipped_ids` unchanged; `merged_head_override` / `research_halt_head` signatures unchanged
  (they still take a pre-built `exclude_ids`).
- `lazy-state.py` + `bug-state.py` — the three exclude-set construction sites (`--emit-prompt`
  merged override, `--next-merged`, `research_halt`) call the oracle instead of
  `nondispatchable_item_ids ∪ probe_skipped_ids`. **Coupled-pair** (L6) — the merged marker is
  shared; mirror + `lazy_parity_audit.py`.
- `nondispatchable_item_ids` — retired from the merged-head path once all three consumers migrate;
  kept only if a non-merged consumer remains (L7 `retires:`).
- Tests — `tests/test_lazy_core/test_dispatch.py`: the five-facet regressions must stay green under
  the oracle (each currently-enumerated facet still excluded), PLUS new coverage for a
  previously-uncovered category (cloud-deferred / completion-unverified head at the merged head →
  correctly excluded, no withhold) and the dispatchable-divergence byte-identity case.

## Locked Decisions

| ID | Decision |
|----|----------|
| L1 | Replace the category-enumerated `nondispatchable_item_ids` file-predicate (five facets + an in-code-admitted incomplete "Scope boundary") with the authoritative per-item actionability oracle it approximates — the scoped `compute_state` dispatch decision. This ends the recurring `merged-head-diverged-withholds-on-<X>` class by construction. |
| L2 | Same-pipeline exclude source stays `probe_skipped_ids(state, same_pipeline_items)` — NOT replaced by the oracle. It carries cross-item skip-ahead *ordering* context (two-key readiness predicate, `--strict-research-halt`, fully-gated terminal) a per-item oracle would lose. The oracle applies ONLY to the cross-pipeline queue the current probe never walked. |
| L3 | `is_dispatchable(scoped_state)` is a small closed predicate: dispatchable iff `sub_skill` is a non-empty, non-`__`-prefixed real skill AND `terminal_reason` is not a skip/defer/park/gate/halt reason. A `needs-research` head (without `--skip-needs-research`) classifies non-dispatchable and is excluded here; `research_halt_head` RE-INCLUDES it so the operator still sees the needs-research halt (byte-identity invariant). |
| L4 | *(Open — not locked; see Open Question 1.)* In-process scoped `compute_state` with module-global snapshot/restore is PREFERRED over subprocess spawn, but isolation robustness is resolved in `/spec-phases` Phase 1; subprocess (`--bug-id` / `--feature-id`) is the documented fallback. |
| L5 | Bound the oracle to candidates ranked at-or-above the emitted item in the merged ordering, short-circuiting at the first dispatchable head — a lower-priority item can never be the diverging merged head, so it never needs an oracle evaluation. |
| L6 | Coupled-pair: the merged marker is shared across `lazy-state.py` / `bug-state.py`; the three exclude-set construction sites (`--emit-prompt` merged override, `--next-merged`, `research_halt`) must be mirrored and `lazy_parity_audit.py --repo-root .` kept exit 0. |
| L7 | `nondispatchable_item_ids` is retired from the merged-head path once all three consumers migrate; it is deleted outright only if no non-merged consumer survives (confirm via usage grep, Open Question 2). The retiring change carries a `retires:` declaration for the anti-overfit complexity check. |

L4 is intentionally the only gap in the L1–L7 sequence — it is a deferred Open Question, not a
locked decision. **Required MCP tooling: none** — this is a pure state-machine refactor validated by
the in-file `--test` smoke harness + `pytest test_dispatch.py`, so no `## Locked Decisions` MCP-tool
row is authored (nothing for the completion-time coverage gate to assert).

## Implementation Phases

1. **Oracle core (pure).** `is_dispatchable` + `merged_head_nondispatchable_ids` in
   `lazy_core.dispatch`, with injected scoped-probe callables for hermetic `--test`. Characterize
   against all five facet fixtures + the newly-covered categories.
2. **Emit-path migration + parity.** Rewire the `--emit-prompt` merged-override site on both state
   scripts; `--test` byte-identity for dispatchable heads; `lazy_parity_audit.py` green.
3. **`--next-merged` + `research_halt` migration + helper retirement.** Migrate the remaining two
   exclude-set sites; retire `nondispatchable_item_ids` from the merged path (declare `retires:`);
   full smoke-baseline re-pin.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Byte-identity for dispatchable heads | P0 bug jumps the queue mid-feature-run | `merged-head-diverged` withhold fires identically to pre-oracle | `test_dispatch.py` dispatchable-divergence fixture; smoke baseline |
| Five enumerated facets still excluded | parked / operator-deferred / device-deferred / dep-unready / research-skipped head at merged head | No withhold; driver dispatches the workable item | `test_dispatch.py` five facet regressions |
| Future category auto-excluded | a cloud-deferred / completion-unverified head at the merged head | No withhold, no stall (previously would withhold) | new `test_dispatch.py` fixture |
| No cross-probe corruption | oracle runs N scoped probes in-process during one emit | primary `state` unchanged; `_SKIP_AHEAD_BLOCKED` / diagnostics intact | `test_dispatch.py` isolation fixture |
| Coupled-pair parity | any edit to the emit-path oracle wiring | `lazy_parity_audit.py --repo-root .` exit 0 | parity audit |

<!-- MCP tooling: none. This is a pure state-machine refactor validated by the in-file --test
     smoke harness + pytest test_dispatch.py — no MCP tool surface. -->

## Success Measurement

Not a registry KPI (see the classification note in the header). Success is the post-ship
**recurrence count of the `merged-head-diverged-withholds-on-<X>` / `merged-head-*-deadlocks` bug
slug family — target 0.** Pre-ship baseline: the five archived facet bugs. This is a review-cadence
grep over `docs/bugs/**/`, not an automated computed field — the registry's closed signal
source/selector vocabulary cannot express a bug-class-recurrence count, so it is tracked informally
rather than fabricated into a misfit registry row.

## Open Questions

These are technical/implementation questions for `/spec-phases`, not research-answerable:

1. **In-process vs subprocess oracle.** Prefer in-process scoped `compute_state` (cheapest,
   no interpreter spawn) with snapshot/restore of module globals; subprocess (`bug-state.py
   --bug-id`) is the fallback if in-process isolation proves fragile. Resolve during Phase 1.
2. **`nondispatchable_item_ids` full retirement.** Whether any consumer outside the three
   merged-head sites survives; if none, delete the helper (not just unwire it). Confirm during
   Phase 3 with a usage grep.
3. **`is_dispatchable` terminal-reason enumeration.** The exact closed set of non-dispatch
   `terminal_reason` values — derive it exhaustively from `compute_state`'s terminal vocabulary
   rather than hand-listing (avoid re-introducing an enumeration that can drift).

## Research References

No external prior art — pure harness-internal routing. Grounding evidence:
`lazy_core/dispatch.py` (`merged_head_override`, `probe_skipped_ids`, `research_halt_head`),
`lazy_core/depdag.py` (`nondispatchable_item_ids`, `next_merged`), and the five archived facet
bugs: `docs/bugs/_archive/{merged-head-includes-parked-items-deadlocks-park-run,
merged-head-excludes-parked-not-operator-deferred-deadlocks,
merged-head-diverged-withholds-on-research-skipped-head}` plus the
`merged-head-diverged-stalls-on-gated-head` /
`merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone` in-code references. The 5th
facet's SPEC (`merged-head-diverged-withholds-on-research-skipped-head`, Non-goals) explicitly
spun off this generalization.
