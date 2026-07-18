# Bug: merged-head actionability oracle's cross-pipeline scoped-probe classification is blind to context-dependent skips → mutual merged-head-diverged deadlock

**Status:** Concluded
**Severity:** P1 (run-blocking — total no-route deadlock on a unified `/lazy-batch` driver with both queues populated)
**Discovered:** 2026-07-18 (observed-friction dispatch, item in flight `managed-llm-credits`, AlgoBooth)
**Related:**
- `docs/features/merged-head-actionability-oracle/SPEC.md` (the COMPLETED feature whose Locked Decision **L3** this defect is in — cross-pipeline classification via per-item scoped `compute_state` + `is_dispatchable`)
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Rounds 91/92/93/94 (the same recurring "merged-head exclude set must agree with what `compute_state` skips" class — this is the 7th facet)
- `docs/specs/spike-pipeline-role/SPEC.md` (the feature whose `runtime-spike-verdict-pending` → dispatchable-`spike` route is the specific trigger that WIDENED the hole)
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT_2026-07-18-merged-head-oracle-cross-pipeline-context.md` (the STRUCTURAL design fork this investigation hard-parks for operator ratification)

## Reconstructed route (Step 1)

Unified `/lazy-batch` driver on AlgoBooth; feature AND bug queues both populated. Each cycle the
driver probes the merged head and the two state scripts' `--emit-prompt`. Three inconsistent
merged-head computations were observed in the SAME cycle:

1. `lazy-state.py --next-merged` → `{hydra-overlay, feature}`.
2. feature probe (`lazy-state.py --emit-prompt`) embedded `merged_head` → `{worktree-rust-test-binary-entrypoint-not-found, bug}` (the P1-severity bug at the queue TAIL) → `route_overridden_by: merged-head-diverged`, `cycle_prompt` WITHHELD.
3. bug probe (`bug-state.py --emit-prompt`) embedded `merged_head` → `{hydra-overlay, feature}` → `route_overridden_by: merged-head-diverged`, `cycle_prompt` WITHHELD.

Net: the feature actionable head is `mcp-test managed-llm-credits` (Step 9) and the bug actionable
head is `spec-bug algobooth-rust-qg-excludes-lib-tests`, but each `--emit-prompt` probe WITHHOLDS
its forward route naming the OTHER pipeline's item, and `--next-merged` names a genuinely-BLOCKED
feature (`hydra-overlay`, live `BLOCKED.md`) that cannot be dispatched → **total no-route
deadlock.** The checkpoint's intended `next_route` this run was `mcp-test managed-llm-credits`.

**Deterministically reproduced** in-process against the live AlgoBooth queue (feature queue 33
items, bug queue 32): the three computations above reproduce exactly via the real callers
`dispatch.merged_head_nondispatchable_ids` (`user/scripts/lazy_core/dispatch.py:639`) +
`dispatch.merged_head_override` / `next_merged`.

## Root cause (Step 2) — `script-defect` (structural remedy)

The merged-head actionability oracle (completed feature `merged-head-actionability-oracle`) builds
its exclude set from two sources, per its Locked Decisions:

- **Same-pipeline (L2):** `probe_skipped_ids(state, same_items)` — the current full probe's OWN
  skip decisions. Context-rich and authoritative (carries the cross-item skip-ahead ordering, the
  two-key readiness predicate, `--strict-research-halt`, the fully-gated terminal).
- **Cross-pipeline + stateless `--next-merged` (L3):** a **per-item scoped `compute_state` probe**
  of each candidate, excluded iff `is_dispatchable(scoped_state)` is false
  (`user/scripts/lazy_core/dispatch.py:601`).

**The defect: a single-item scoped `compute_state` probe cannot reproduce a CONTEXT-DEPENDENT skip
that the cross-pipeline FULL probe makes.** The oracle's L2 already acknowledges scoped probes lose
"cross-item skip-ahead ordering context" — but L3 assumed the CROSS-pipeline queue does not have
that problem ("the OTHER queue, which the current probe never walked"). That assumption is FALSE:
the cross-pipeline queue has the SAME context-dependent skips, and a per-item scoped probe
systematically misclassifies context-skipped heads as **dispatchable**. Two facets confirmed live:

1. **BLOCKED-spike head (`hydra-overlay`).** Scoped probe (default, `park_blocked=False`) →
   `sub_skill=spike`, `terminal_reason=None` → `is_dispatchable=True`. But the full feature probe's
   default-on skip-ahead SKIPS it (`gated_heads`, via `_gated_head_kind` returning `"blocked"` for
   any `BLOCKED.md`, `user/scripts/lazy-state.py:1936`). The scoped probe reaches `current` only via
   the single-item `gated_head_fallback` (`lazy-state.py:2828`), and the Step-3 route
   (`lazy-state.py:3094`, introduced by `spike-pipeline-role`) turns a
   `blocker_kind: runtime-spike-verdict-pending` `BLOCKED.md` into a **dispatchable** `spike` cycle
   instead of the pre-existing non-dispatchable `terminal_reason="blocked"` terminal. **This is the
   specific regression that widened the hole:** before `spike-pipeline-role`, a scoped BLOCKED head
   returned `terminal_reason="blocked"` → non-dispatchable → the oracle excluded it correctly.
2. **Not-independent / dep-gated head (`inspector-track-dashboard`).** Scoped probe →
   `sub_skill=realign-spec`, `terminal_reason=None` → `is_dispatchable=True`. But the full feature
   probe SKIPS it: after a gated head (`hydra-overlay`) was skipped, `skip_ahead_ready` requires
   `independent: true`, which this item lacks (`independent: None`) → skipped
   (`skip_ahead_blocked`). A single-item scoped probe has no "earlier gated head skipped" context,
   so `skip_ahead_ready` never evaluates → it looks dispatchable.

Because both facets are cross-pipeline / stateless (L3-classified) but the SAME-pipeline side uses
`probe_skipped_ids` (L2, correct), the three computations disagree: the feature-emit path excludes
`hydra-overlay` (its own L2 skip) and finds the next scoped-dispatchable BUG (`worktree`, P1) →
withholds; the bug-emit path and `--next-merged` scoped-classify `hydra-overlay` as dispatchable →
name it. Neither dispatchable head is real → deadlock.

**Confirmed: fixing only facet 1 (BLOCKED-spike) does NOT resolve the deadlock** — it moves to
`inspector-track-dashboard` (facet 2). The two facets share ONE root: L3's per-item scoped
classification is structurally blind to cross-pipeline skip-ahead context.

**The correct model (verified):** the merged head is the higher-merged-priority of each pipeline's
ACTUAL full-probe dispatch head. Feature full head = `managed-llm-credits` (prio 2); bug full head =
`algobooth-rust-qg-excludes-lib-tests` (prio 99); higher = `managed-llm-credits` — **exactly the
checkpoint's intended route.** Each pipeline's full probe already applies all skip-ahead / defer /
gating context; the cross-pipeline classification should reuse THAT (as L2 does same-pipeline),
not re-derive it from per-item scoped probes.

## Fix scope — BLOCKED on operator ratification (structural)

The remedy revisits a LOCKED DECISION (**L3**) of a COMPLETED feature, changes the cross-pipeline
classification mechanism, is coupled-pair mirrored across THREE sites in two scripts
(`--emit-prompt` merged override, `--next-merged`, `research_halt`), and alters core dispatch
routing in every mixed-queue run. A wrong pick silently mis-prioritizes cross-pipeline work and is
expensive to redirect. Per the `/harden-harness` park-provisional **structural carve-out**, this is
hard-parked for the operator, not provisional-implemented. See the NEEDS_INPUT sentinel (Related)
for the recommended fix (higher-priority-of-two-full-probe-heads / reuse cross-pipeline full-probe
context) and the alternatives. A `BLOCKED.md` in this bug dir prevents the bug pipeline from
driving an un-ratified structural fix.

**Operator interim workaround (verified):** running with `--park-blocked` breaks the deadlock — it
parks `hydra-overlay` (and any BLOCKED head) consistently across all three paths, which also
un-blocks `inspector-track-dashboard`'s skip-ahead, so the driver dispatches
`inspector-track-dashboard` (`realign-spec`) rather than stalling. The dispatched item differs from
the checkpoint's `managed-llm-credits`, but the pipeline progresses.
