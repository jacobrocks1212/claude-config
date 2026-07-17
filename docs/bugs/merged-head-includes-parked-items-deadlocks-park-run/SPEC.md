# Merged-head computation includes PARKED items → park-mode run deadlocks

**Status:** Concluded
**Severity:** P0
**Discovered:** 2026-07-17
**Related:** `docs/bugs/dispatch-probe-and-inject-bypass-merged-head/` (Round 54 — the
merged-head-diverged withhold this bug interacts badly with); `docs/features/unified-pipeline-orchestrator/`
(the merged-view / type-dispatch contract); `docs/specs/turn-routing-enforcement/` (hardening
stage); `docs/bugs/lazy-batch-no-mid-run-budget-or-park-controls/` (park-mode facets).

## Trigger

Orchestrator-observed friction during a live `/lazy-batch` run on AlgoBooth (2026-07-17), in
park mode (`--park --park-provisional`). The two head-of-queue P0 bugs
(`adhoc-hydra-sidecar-dist-esm-no-frames`, `adhoc-hydra-load-code-mcp-tool`) were BOTH parked on
unresolved `NEEDS_INPUT.md` (product decisions). The next **actionable** item was
`adhoc-incident-hook-deny-a51dde` (a spec-bug, lower priority). No item could be dispatched:

- `lazy-state.py --next-merged` returned the PARKED `adhoc-hydra-sidecar-dist-esm-no-frames`
  (it does not exclude parked items).
- BOTH `lazy-state.py` and `bug-state.py --emit-prompt` probes returned
  `route_overridden_by: merged-head-diverged` with `cycle_model: null` / `cycle_prompt_ref: null`
  (the `merged_head` was the parked sidecar bug), WITHHOLDING the actionable incident bug's
  emission.

Net: the merged head was a parked item that cannot be driven (driving it in park mode just
re-parks it), so every emit probe withheld the forward route → **run deadlock** (no item
dispatchable).

## Reconstructed route (divergence point)

The Round-54 merged-view harden (`docs/bugs/dispatch-probe-and-inject-bypass-merged-head/`) added
`lazy_core.dispatch.merged_head_override` + the `--emit-prompt` `route_overridden_by:
merged-head-diverged` withhold: when the merged work-list head is a DIFFERENT item than the one a
dispatch-bound probe would emit for, the probe withholds the (wrong-item) forward route so the
orchestrator re-probes `--next-merged` and type-dispatches to the merged head.

That withhold **assumes the orchestrator can DRIVE the merged head.** In park mode a merged head
that carries an unresolved `NEEDS_INPUT.md` / `BLOCKED.md` is PARKED — it cannot be driven
(compute_state skips it; the pipeline would re-park it). The divergence point:

- `lazy_core.depdag.merged_worklist` / `next_merged` (the single merged-ordering source) rank
  items by `merged_priority` ONLY — they do **not** exclude parked items.
- `lazy_core.dispatch.merged_head_override` calls `next_merged`, so its `merged_head` can be a
  parked item.
- The `--emit-prompt` withhold in `lazy-state.py` (~L13646) and `bug-state.py` (~L9412), plus the
  `--next-merged` CLI (`lazy-state.py` ~L12256), all consume that unfiltered head.

Earlier in the SAME run the withhold did NOT deadlock: the top item was BLOCKED (not parked — no
`--park-blocked`) and the next actionable item was a pseudo-skill (`__mark_fixed__`), so the
merged head matched the current item and the override was `None`. The gap is specifically
**PARKED-item exclusion from the merged-head computation** — the withhold has no way to tell a
"drive-the-other-queue's-head" divergence (its intended purpose) from a "the head is parked and
undriveable" dead end.

## Root cause

**script-defect** — `lazy_core.depdag.merged_worklist` / `next_merged` /
`lazy_core.dispatch.merged_head_override` order strictly by `merged_priority` and never exclude
PARKED items, even though the compute_state walk in both state scripts already skips those items
(populating each probe's `parked[]` array). The two views disagree: the single-queue walk parks
the item and advances to the next actionable one, while the merged-head view keeps pointing at the
parked item, and the `merged-head-diverged` withhold then withholds the actionable item's
emission indefinitely. The withhold is correct for genuine feature-vs-bug pipeline divergence; it
is wrong when the head is parked.

## Fix scope

Exclude PARKED items from the merged-head computation, reusing the SAME park predicate the probe
`parked[]` array uses, so the merged head is the highest-priority **UN-PARKED** actionable item.

1. **New shared predicate** `lazy_core.docmodel.spec_dir_would_park(spec_dir, *, park_needs_input,
   park_blocked, park_provisional)` — pure, mirroring the compute_state park branches (canonical
   `BLOCKED.md` + stray mis-named blocker under `--park-blocked`; unresolved `NEEDS_INPUT.md`
   under `--park-needs-input`, with `BLOCKED.md` precedence and provisional-eligible-routes-not-parks
   under `--park-provisional`). No facet active → `False` (byte-identical non-park behavior).
2. **New resolver** `lazy_core.depdag.parked_item_ids(feature_items, bug_items, repo_root, *,
   park facets)` — resolves each queue item's spec dir (features: `docs/features/<spec_dir>`; bugs:
   the loader-supplied `spec_path`, else `docs/bugs/<spec_dir>`) and returns the set of parked ids.
   No facet active → empty set.
3. **Thread `exclude_ids`** through `merged_worklist` / `next_merged` /
   `dispatch.merged_head_override` — items whose id ∈ `exclude_ids` are filtered from the ordering.
4. **Callers** (`lazy-state.py --next-merged`, `lazy-state.py --emit-prompt`,
   `bug-state.py --emit-prompt`) compute the effective park facets (marker-authoritative
   `fold_park_flags`) + `parked_item_ids` and pass `exclude_ids`. Marker-gated / no-facet →
   byte-identical.

**Class boundary (deliberate scope).** The predicate covers the two cited park families —
unresolved `NEEDS_INPUT.md` and `BLOCKED.md` (incl. the stray mis-named blocker, same BLOCKED
family the `parked[]` array already includes). Explicitly OUT of scope: the narrower
"unratified `NEEDS_INPUT_PROVISIONAL.md` + `VALIDATED.md` parks at completion" branch — that item
is workable up to completion, not undriveable, and is not part of the observed deadlock. A later
round may widen the boundary if a provisional-completion head is ever observed to deadlock.

## Verified symptom / regression fixture

Top-priority bug parked (unresolved `NEEDS_INPUT.md`) + a lower-priority actionable bug, park
mode active:
- `--next-merged` returns the **actionable** bug (not the parked head).
- The `--emit-prompt` probe emits a clean `cycle_prompt` with **no** `merged-head-diverged`
  withhold.

With no park facet active the merged head and all probes are byte-identical to pre-fix behavior
(the exclusion set is empty).
