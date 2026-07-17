# Dispatch-bound enriched probe + inject hook bypass the merged-view head

**Status:** Concluded
**Severity:** P0
**Discovered:** 2026-07-16
**Related:** `docs/features/unified-pipeline-orchestrator/` (the merged-view / type-dispatch
contract this violates); `docs/specs/turn-routing-enforcement/` (hardening stage);
`docs/bugs/lazy-batch-unified-driver-parity-and-accounting/` (`_load_bug_queue_for_merged`
+ merged-view diagnostics precedent).

## Trigger

Orchestrator-observed friction during a live `/lazy-batch` run on AlgoBooth (2026-07-17), with
`hydra-overlay` (a feature) in flight. Two P0 bugs
(`adhoc-hydra-sidecar-dist-esm-no-frames`, `adhoc-hydra-load-code-mcp-tool`) sat at the head of
`docs/bugs/queue.json`, both actionable (`bug-state.py` returned
`adhoc-hydra-sidecar-dist-esm-no-frames` Step 7a execute-plan, plan Ready). The merged-view
head probe was CORRECT:

```
lazy-state.py --next-merged  →  {item_id: adhoc-hydra-sidecar-dist-esm-no-frames, type: bug}
```

Yet BOTH dispatch-bound routing surfaces returned the lower-priority `hydra-overlay` FEATURE
(execute-plan part-5) as the route:

- the **enriched dispatch-bound probe** `lazy-state.py --repeat-count --emit-prompt --probe`, and
- the **hook-injected `LAZY-ROUTE` banner** (`lazy-route-inject.sh` → `lazy_inject.py`).

Result: the two P0 bugs were **silently skipped** and a lower-priority feature was worked first.
`lazy_core.merged_priority` ordering was correct; the divergence was entirely in the
dispatch/hook probe paths that never consulted it.

## Reconstructed route (divergence point)

The unified driver contract (`unified-pipeline-orchestrator` Phase 2; `lazy-batch/SKILL.md`
Step 1 "Unified driver — merged-view dispatch", lines 363-394) is:

> each cycle probe the merged work-list head with `lazy-state.py --next-merged` FIRST → learn
> `{item_id, type}` → **type-dispatch** the rest of the cycle: `type == "feature"` → drive with
> `lazy-state.py`; `type == "bug"` → drive with `bug-state.py`.

Two dispatch-bound surfaces bypass that first step:

1. **Inject hook (`lazy_inject.py::_run_probe`, lines 111-119).** It selects the state script
   purely from the run marker's **sticky** `pipeline` field
   (`pipeline = marker.get("pipeline", "feature")` → `bug-state.py` iff `pipeline == "bug"`,
   else `lazy-state.py`). The marker's `pipeline` is a per-run CONSTANT written once at
   `--run-start` (`markers.py` refuses a different-pipeline `--run-start` over an active marker),
   but a unified run's correct per-cycle type is the MERGED HEAD's type — which changes mid-run
   when a P0 bug jumps the bug-queue head. So the hook keeps injecting a `feature` banner
   (`lazy-state.py --emit-prompt`) over a P0-bug merged head. **`lazy-batch/SKILL.md` line 406
   tells the orchestrator to CONSUME the injected banner directly and NOT re-probe** — so the
   stale-type banner short-circuits the `--next-merged` type-dispatch and the bug is never seen.

2. **Enriched dispatch-bound probe (`lazy-state.py --emit-prompt`).** `compute_state` runs the
   FEATURE state machine over `docs/features/queue.json` only and emits a feature `cycle_prompt`
   for `state["feature_id"]`. It has withhold guards for `pending-hardening-debt` and
   `audit-obligation` (`route_overridden_by`) but NONE for "the merged head is a different,
   higher-priority item". When the orchestrator calls this probe directly (the manual Step-1a
   path when no banner is present) it gets a feature route with no signal that a P0 bug outranks
   it.

**Divergence point:** the dispatch-bound routing surfaces (inject-hook script selection +
enriched `--emit-prompt`) route by sticky-pipeline / feature-only state instead of the merged
head, so the `--next-merged` type-dispatch is bypassed.

## Root cause

**`root_cause_class: hook-defect`** (primary — the inject hook is the automatic path the
orchestrator is contractually told to trust, and it built a stale-type banner), with a paired
**script-defect** gap: the enriched `--emit-prompt` probe has no merged-head withhold.

The underlying defect is shared: a dispatch-bound surface consulted the wrong routing SOURCE
(marker sticky `pipeline` / single-queue state) rather than the merged head that
`lazy_core.merged_priority` already orders correctly. `merged_priority`/`next_merged` were never
wrong — the dispatch/hook paths just never asked them.

## Verified symptom

- `lazy-state.py --next-merged` → the bug (correct).
- `lazy-state.py --repeat-count --emit-prompt --probe` and the hook-injected `LAZY-ROUTE` banner
  → the feature (wrong): a P0 bug at the bug-queue head + an actionable feature yields a feature
  route, silently skipping the bug.

## Fix scope (mechanical — no marker-lifecycle change)

The unified marker already drives `bug-state.py` under a feature-started marker (Step 1a
type-dispatch), so cross-pipeline routing is established; NO new marker/pipeline-lifecycle
contract is needed. The fix makes the bypass **impossible / self-announcing** by wiring the
SAME `next_merged` ordering into both dispatch-bound surfaces:

1. **`lazy_core/dispatch.py`** — add pure, fail-safe helper `merged_head_override(feature_items,
   bug_items, repo_root, current_item_id)`: reuses `next_merged`; returns
   `{route_overridden_by: "merged-head-diverged", merged_head: {item_id, type}}` when the merged
   head's `item_id` differs from the item the probe would emit for, else `None` (byte-identical
   common path).
2. **`lazy-state.py --emit-prompt`** — add a third `route_overridden_by` withhold
   (`merged-head-diverged`) after the `pending-hardening-debt` / `audit-obligation` withholds:
   withhold the (wrong-item) feature route so the orchestrator must re-probe `--next-merged` and
   type-dispatch. Marker-gated + fail-safe (byte-identical when no bug outranks).
3. **`bug-state.py --emit-prompt`** — coupled-pair mirror (add `_load_feature_queue_for_merged`
   + the same withhold), so a bug run whose merged head jumped to a different item also
   withholds.
4. **`lazy_inject.py::_run_probe`** — select the probe script by the MERGED HEAD's type (probe
   `--next-merged` first), not the marker's sticky `pipeline`; fail-open to the marker pipeline.
   The injected banner then reflects the true merged head — exactly what the Step-1a
   type-dispatch would produce.
5. **Regression fixtures** — `test_lazy_core.py` (helper unit test) + `test_hooks.py` (inject
   banner routes `bug-state.py` when a P0 bug is the merged head).

**Not weakened:** no gate softened; the existing hardening-debt/audit withholds are untouched;
the no-divergence common path (feature run whose head IS the feature; single-populated-queue
runs) stays byte-identical.
