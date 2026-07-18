# Merged-head excludes PARKED but not OPERATOR-DEFERRED items → deadlock persists

**Status:** Fixed
**Severity:** P0
**Discovered:** 2026-07-17
**Fixed:** 2026-07-18
**Fix commit:** c5a3b385
**Related:** `docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run/` (Round 56 — the
direct precedent; this bug is the "later round widens the boundary" case its own §Fix scope
invited); `docs/bugs/_archive/dispatch-probe-and-inject-bypass-merged-head/` (Round 54 — the
`merged-head-diverged` withhold this interacts badly with); `docs/features/unified-pipeline-orchestrator/`
(the merged-view / type-dispatch contract); `docs/specs/turn-routing-enforcement/` (hardening stage).

## Trigger

Orchestrator-observed friction during a live `/lazy-batch` run on AlgoBooth (2026-07-17),
**immediately after Round 56 landed** (which excluded PARKED items from the merged head). The run
was still deadlocked — but now behind a different non-actionable STATE:

- `lazy-state.py --next-merged` (with park flags) returned `non-windows-audio-output-unvalidated`.
- Scoping that item — `bug-state.py --bug-id non-windows-audio-output-unvalidated --emit-prompt` —
  returned `terminal_reason: operator-deferred`, `current_step: "Operator-deferred (scoped)"`,
  `sub_skill: null`. It is **NOT dispatchable** (operator-deferred; a `DEFERRED.md` sentinel parks
  it unconditionally — it needs a non-Windows host).
- The genuinely-actionable next item was `adhoc-incident-hook-deny-a51dde` (a spec-bug at Step 4),
  which `bug-state.py` routes **unscoped**. But its `--emit-prompt` probe **withheld** the route:
  `route_overridden_by: merged-head-diverged`, `cycle_model: null`, `cycle_prompt_ref: null`,
  `merged_head: non-windows-audio-output-unvalidated`.

Net: still deadlocked — the merged head points at an **operator-deferred** item instead of a
**parked** one. Same class Round 56 fixed (merged head pointing at a non-actionable item), a
different non-actionable STATE that Round 56's park-only exclusion does not cover.

## Reconstructed route (divergence point)

Round 56 added `lazy_core.depdag.parked_item_ids` (built from the pure predicate
`docmodel.spec_dir_would_park`) and threaded `exclude_ids` through `merged_worklist` /
`next_merged` / `dispatch.merged_head_override` so the merged head is the highest-priority
**UN-PARKED** item. But `spec_dir_would_park` only recognizes the two PARK families it was scoped
to — canonical/stray `BLOCKED.md` (under `--park-blocked`) and unresolved `NEEDS_INPUT.md` (under
`--park-needs-input`). It does **not** recognize an **operator-deferred** item.

The divergence point: `compute_state` in `bug-state.py` skips an operator-deferred bug
**unconditionally** — a `DEFERRED.md` sentinel triggers a bare `continue` (bug-state.py ~L1073),
independent of any park flag. So an operator-deferred bug is NEVER the dispatched item, yet
`parked_item_ids` does not exclude it (its `spec_dir_would_park` probe returns `False` for a
`DEFERRED.md`-only dir, and its fast-path even returns an empty set when no park flag is set). The
operator-deferred item therefore remains at the merged head, and the `merged-head-diverged`
withhold (Round 54) fires against every genuinely-actionable item forever → **run deadlock**.

This is precisely the "later round may widen the boundary" case that Round 56's own §Fix scope
(`merged-head-includes-parked-items-deadlocks-park-run/SPEC.md` §Class boundary) anticipated.

## Root cause

**script-defect** — the Round-56 exclusion set (`parked_item_ids` / `spec_dir_would_park`) models
only PARK-flag-gated non-dispatchability. It omits **operator-deferred** (`DEFERRED.md`), which
`compute_state` treats as an **unconditional** skip (no park flag required). The merged-head view
and the single-queue walk disagree exactly as they did in Round 56 — the walk skips the
operator-deferred item and advances to the next actionable one, while the merged-head view keeps
pointing at it — and the `merged-head-diverged` withhold then withholds the actionable item's
emission indefinitely.

## Fix scope

**This round (mechanical, unconditional operator-defer):** generalize the Round-56 mechanism from
"parked" to "not dispatchable", covering the **unconditional** operator-deferred sentinel.

1. **New shared predicate** `lazy_core.docmodel.spec_dir_operator_deferred(spec_dir)` — pure,
   `True` iff the dir carries a `DEFERRED.md`. Mirrors `compute_state`'s unconditional
   operator-deferred `continue`. Fail-safe to `False` on a missing/unreadable dir. Kept separate
   from `spec_dir_would_park` because it is **NOT park-flag-gated** — it excludes an
   operator-deferred item on EVERY run (park or not).
2. **Generalize the resolver** `parked_item_ids` → `nondispatchable_item_ids`: drops the
   "no park facet → empty set" fast-path (operator-defer is unconditional), and excludes an item
   when EITHER `spec_dir_operator_deferred` OR `spec_dir_would_park` holds. No park facet AND no
   `DEFERRED.md` → empty set (byte-identical non-defer, non-park behavior).
3. **Callers** (`lazy-state.py --next-merged` + `--emit-prompt`, `bug-state.py --emit-prompt`)
   call `nondispatchable_item_ids` — no call-shape change beyond the rename.

**Class boundary (deliberate scope).** This round covers ONLY non-dispatchable states that are
**correctly classifiable by a pure, context-free file check**: the two Round-56 park families
(flag-gated) PLUS unconditional operator-deferred (`DEFERRED.md`, bug-pipeline-only — the feature
pipeline has no operator-defer branch). Explicitly OUT of scope: the **context-conditional**
deferrals — device-deferred (`DEFERRED_REQUIRES_DEVICE.md`), cloud-deferred
(`DEFERRED_NON_CLOUD.md`), host-deferred (`DEFERRED_REQUIRES_HOST.md`) — which `compute_state`
gates on `not VALIDATED and _phases_effectively_complete` + the host-context flags
(`real_device`, `cloud`, host-capability registry); AND the **non-file terminal_reasons**
(`completion-unverified`, `stale_upstream`, `needs-research`, `needs-ratification`). Correctly
classifying those requires the run-context and PHASES/upstream state that ONLY the scoped
`compute_state` dispatch oracle holds — a pure file predicate would MISCLASSIFY them (e.g. exclude
a device-deferred item that is actually dispatchable-to-`__mark_fixed__` on a real-device host).

**Spun-off generalization (the durable structural fix):** make the merged-head computation
**fully actionability-aware** by building `exclude_ids` from the scoped `compute_state` dispatch
oracle itself (an item is excluded iff its scoped probe yields no real `sub_skill` / a
non-actionable `terminal_reason`), instead of a growing enumeration of sentinel filenames. That
subsumes this round's file predicate AND the conditional deferrals AND every terminal_reason,
without drift. Tracked as the front-enqueued `/spec-bug` this round spins off (over-fit signal 1:
this fix adds another sentinel literal to a file-existence matcher; the near-neighbor conditional
deferrals + terminal_reasons will gap on the same structure).

## Verified symptom / regression fixture

- **(a)** top bug operator-deferred (`DEFERRED.md`) + a lower-priority actionable bug →
  `--next-merged` returns the **actionable** bug; the actionable item's `--emit-prompt` probe gets
  **no** `merged-head-diverged` withhold (deadlock gone).
- **(c)** mixed queue: a parked (`NEEDS_INPUT.md`, park mode) top bug + an operator-deferred
  (`DEFERRED.md`) second bug + a lower actionable bug → merged head is the **actionable** one (both
  the parked and the operator-deferred items are excluded).
- No `DEFERRED.md` and no park facet → the exclusion set is empty; merged head + all probes are
  byte-identical to post-Round-56 behavior.

Fixture (b) from the dispatch evidence (a **host-deferred** top item) is intentionally deferred to
the spun-off oracle round: host-deferred is context-conditional, so a correct exclusion depends on
the run's host capabilities — which the pure file predicate here cannot see. Covering it in this
round would MISCLASSIFY a host-deferred item that is dispatchable on a capable host.
