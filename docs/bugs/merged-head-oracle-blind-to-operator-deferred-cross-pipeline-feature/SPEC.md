# Merged-head oracle blind to an operator-deferred CROSS-PIPELINE feature → deadlock

**Status:** Concluded
**Severity:** P0
**Discovered:** 2026-07-19
**Related:** `docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks/`
(Round 57 — the ORIGINAL operator-defer merged-head exclusion, whose file-predicate this bug
proves was silently retired); `docs/bugs/_archive/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/`
(Round 101, `1b7d420f` — the immediate precedent this variant SURVIVES);
`docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run/` (Round 56 — the park
progenitor); `docs/features/unified-pipeline-orchestrator/` (the merged-view / type-dispatch
contract); `docs/specs/turn-routing-enforcement/` (hardening stage).

## Trigger

Harden-harness `no-route` auto-trigger during a live `/lazy-bug-batch` run on AlgoBooth
(2026-07-19). The bug pipeline dispatch was fully withheld — `cycle_prompt_ref: null` for EVERY
probe (the merged probe AND a probe scoped to the next dispatchable bug) — behind an
OPERATOR-DEFERRED FEATURE sitting at the cross-pipeline merged head:

- The feature `native-android-pipeline-steering` carries a `DEFERRED.md`
  (`reason: operator-excluded`; body: "excluded from dispatch and merged"), SPEC status
  `Draft(stub)`.
- The FEATURE-side probe (`lazy-state.py --park-*`) returned `merged_head: null` (it reached a
  `needs-research` terminal, so `current_item_id` was falsy and `merged_head_override`
  short-circuited).
- The BUG-side probe (`bug-state.py --park-needs-input --park-blocked --park-provisional
  --emit-prompt`) returned `route_overridden_by: merged-head-diverged`,
  `merged_head: {item_id: native-android-pipeline-steering, type: feature}`,
  `cycle_prompt_ref: null` — the withhold fired against the genuinely-dispatchable next bug
  (`adhoc-harness-gate…`, `/spec-bug` Step 4) AND every other of the 19 queued bugs.

Net: run-blocking deadlock — all 19 dispatchable bugs undispatchable, the run cannot reach
`queue-exhausted-all-parked`.

## Reconstructed route (divergence point)

Bug-pipeline `--emit-prompt` `merged-head-diverged` withhold — the exclude set built by
`lazy_core.dispatch.merged_head_nondispatchable_ids` OMITTED the operator-deferred cross-pipeline
FEATURE `native-android-pipeline-steering`, so `next_merged` kept it the merged head and the
`merged-head-diverged` withhold suppressed `cycle_prompt_ref` on every probe.

The oracle classifies each candidate above the emitted item via a TYPE-AWARE scoped probe (R101):
a FEATURE candidate is scope-probed through the FEATURE `compute_state`. But the FEATURE pipeline
has **no operator-`DEFERRED.md` branch** (a documented "justified divergence" — bug-pipeline-only).
So the scoped feature probe of `native-android-pipeline-steering` IGNORES its `DEFERRED.md`, routes
`/spec` on the `Draft(stub)`, and reports `is_dispatchable: true`. The oracle therefore does NOT
exclude it → it stays the merged head → the withhold deadlocks the run.

## Root cause

**script-defect.** Round 57 (`merged-head-excludes-parked-not-operator-deferred-deadlocks`,
`c5a3b385`) fixed exactly this class by adding the pure file-predicate
`lazy_core.docmodel.spec_dir_operator_deferred` (True iff `DEFERRED.md` present) into a merged-head
exclusion set (`nondispatchable_item_ids`) that ran UNCONDITIONALLY over every candidate — feature
or bug — so an operator-deferred item was excluded regardless of which pipeline owned it.

A LATER refactor — `merged-head-actionability-oracle` (`merged_head_nondispatchable_ids` +
`is_dispatchable`) — RETIRED that file-predicate union, replacing it with per-candidate scoped
`compute_state` re-inference (`is_dispatchable` keyed on the CLOSED `compute_state` output
contract). Its premise: "any truthy `terminal_reason` ⇒ non-dispatchable, so the oracle covers
every non-dispatch category by construction." That premise is TRUE for a BUG candidate
(`bug-state.py`'s operator-defer branch surfaces `terminal_reason: operator-deferred`) but FALSE
for a cross-pipeline FEATURE candidate — the FEATURE `compute_state` deliberately models no
operator-defer, so the signal (`DEFERRED.md`) is INVISIBLE to the probe the oracle trusts. The
retired file-predicate was the ONLY thing catching an operator-deferred FEATURE at the merged
head; dropping it re-opened the Round-57 deadlock for the cross-pipeline-feature case.

The misleading docstrings that encode the false premise:
`docmodel.spec_dir_operator_deferred` (lines ~2312-2321 — "the merged-head exclude computation is
now the actionability oracle … so an operator-deferred item is excluded from the merged head
regardless of the active facets" AND "a feature spec dir never carries the file"); `depdag.merged_worklist`
(~L1441 — "built by `dispatch.merged_head_nondispatchable_ids` — the actionability oracle that
RETIRED the former `nondispatchable_item_ids` file-predicate").

This is the "later round may widen the boundary" case Round 56/57 anticipated, on the axis the
actionability-oracle generalization missed: a non-dispatchable UNCONDITIONAL file-signal that the
OWNING pipeline's `compute_state` does not model.

## Fix scope

**Mechanical (this round — restore the retired file-predicate at the ONE oracle landing site).**
In `lazy_core.dispatch.merged_head_nondispatchable_ids`, supplement the scoped `is_dispatchable`
walk with the pure file-predicate `spec_dir_operator_deferred`: for each candidate above the
emitted item, resolve its spec dir (feature → `<repo>/docs/features/<spec_dir|id>`; bug →
the item's already-absolute `spec_path` dir) and EXCLUDE it when `DEFERRED.md` is present, BEFORE
the scoped `is_dispatchable` check. Type-agnostic (covers feature AND bug candidates identically)
and applied at the single oracle used by BOTH pipelines' merged-head paths + the stateless
`--next-merged` path, so the bug-side and feature-side merged heads exclude operator-deferred
FEATURES identically. Fail-safe: no resolvable dir / no `DEFERRED.md` → not excluded →
byte-identical when no `DEFERRED.md` exists (existing injected-`scoped_probe` unit tests, whose
fake ids resolve to no real dir, are unchanged). Add a regression fixture: a bug-probe merged head
that is an operator-deferred cross-pipeline feature — excluded, no withhold, dispatchable bug
routed. Correct the two false-premise docstrings.

**Structural generalization (spun off — NOT this round).** The oracle keeps accreting per-signal
supplements because the FEATURE `compute_state` does not model an unconditional non-dispatchable
file-signal it can carry (`DEFERRED.md`). The durable fix is to make the FEATURE pipeline honor
operator-defer in `compute_state` (retiring the "no operator-defer branch" divergence), so the
oracle's `is_dispatchable` premise holds universally and the file-predicate supplement can be
retired — AND the feature pipeline stops dispatching `/spec` on an operator-EXCLUDED feature (the
"excluded from **dispatch**" half of the `DEFERRED.md` body this round does not address). Class
boundary: the ONE unconditional file-signal the feature pipeline fails to model; explicitly OUT of
scope: the context-conditional deferrals (device/cloud/host — already modeled) and non-file
terminal reasons.

## Reproduction Steps

1. Bug queue with ≥1 dispatchable bug; a `docs/features/<slug>/` carrying `DEFERRED.md` +
   `Draft` SPEC, ranked at-or-above the bug in the merged ordering.
2. `bug-state.py --park-needs-input --park-blocked --emit-prompt` → observe
   `route_overridden_by: merged-head-diverged`, `merged_head` = the deferred feature,
   `cycle_prompt_ref: null` (the deadlock).
3. With the fix: the deferred feature is excluded from the merged head, `merged-head-diverged`
   does NOT fire, and the dispatchable bug's `cycle_prompt_ref` is emitted.
