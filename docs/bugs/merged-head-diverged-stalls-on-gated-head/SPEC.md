# Merged-driver stalls on a gated merged head (`merged-head-diverged` withhold)

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-17 (observed live during a `/lazy-batch` run on AlgoBooth)
**Related:** `docs/bugs/dispatch-probe-and-inject-bypass-merged-head` (introduced the
`merged-head-diverged` withhold this bug refines); `docs/bugs/merged-head-excludes-parked-not-operator-deferred-deadlocks`
(the file-predicate exclude set + the SPUN-OFF "make the merged head fully actionability-aware"
generalization this bug IS); `docs/features/unified-pipeline-orchestrator/` (the merged-view /
type-dispatch contract).

## Trigger

Orchestrator-observed friction during a live `/lazy-batch` run on AlgoBooth (2026-07-17). Jacob
had just marked 8 pre-release features (incl. `cross-platform-distribution`) as tier `pre-release`
(priority 1) so they stay VISIBLE / not-forgotten. `cross-platform-distribution` is a BLOCKED
external-gate feature (`blocker_kind: external-gate`, Windows CI smoke, un-clearable
autonomously). With it pinned at priority 1 it sat at the merged work-list head.

The per-pipeline `lazy-state.py --emit-prompt` probe correctly applied default-on **skip-ahead** —
it advanced past the BLOCKED gated head to the next workable independent feature (`hydra-overlay`)
and computed a valid `cycle_prompt` for it. But the merged-head divergence check disagreed:

```
lazy-state.py --next-merged            → cross-platform-distribution  (gated, priority 1)
lazy-state.py --emit-prompt feature_id → hydra-overlay                (the workable item)
→ route_overridden_by: "merged-head-diverged", merged_head: cross-platform-distribution,
  cycle_prompt: null   ← WITHHELD → driver cannot dispatch → STALL
```

The only way to break the stall mid-run was to manually demote the feature's tier — which defeats
the point of pinning it.

## Reconstructed route (divergence point)

The `--emit-prompt` merged-head withhold (`lazy-state.py` / `bug-state.py`, mirrored) builds its
exclude set from `lazy_core.nondispatchable_item_ids(...)`, which covers only the NARROW
file-predicate set: park families (`--park-blocked` BLOCKED.md / `--park-needs-input`
NEEDS_INPUT.md) + unconditional operator-defer (`DEFERRED.md`). The per-pipeline **skip-ahead**
(default-on; `compute_state`) is BROADER: it advances past a research-pending / BLOCKED gated
head (`gated_heads`), a host-deferred head (`host_deferred_features`), a device-deferred head
(`device_deferred_features`), and a dependency-gated head (`dep_gated`) — none of which the file
predicate excludes when no park flag is set.

**Divergence point:** a BLOCKED head with no `--park-blocked` flag is skipped by the per-pipeline
probe but NOT excluded from the merged-head computation, so `merged_head_override` sees the merged
head (the gated item) ≠ the item the probe dispatched (the workable item) and WITHHOLDS the
forward route — stalling the driver behind an item it will never dispatch.

## Root cause

**`root_cause_class: script-defect`** — the merged-head exclude set (`nondispatchable_item_ids`)
is a NARROWER predicate than the per-pipeline skip-ahead it must agree with. This is precisely the
"make the merged head fully actionability-aware" generalization spun off by
`merged-head-excludes-parked-not-operator-deferred-deadlocks` (over-fit signal 1: that round added
another sentinel-filename literal to the file matcher; the near-neighbor context-conditional
deferrals + gated heads gap on the same structure).

The `merged-head-diverged` mechanism itself is correct — its JOB is to catch a genuinely
higher-priority DISPATCHABLE item (a P0 bug jumping the queue) that the current probe ignored. It
must NOT fire behind a gated head the probe already, correctly, skipped.

## Fix scope (mechanical — no gate weakened, no marker/pipeline-lifecycle change)

Reuse the per-pipeline probe's OWN same-cycle skip decisions instead of re-inferring per-item
state:

1. **`lazy_core/dispatch.py`** — new pure helper `probe_skipped_ids(state, items)`: folds the
   probe's `gated_heads` / `host_deferred_features` / `device_deferred_features` (name→id
   resolved) / `dep_gated` (and, bug-side, `operator_deferred`) into one id set. Because these are
   the probe's own realized skips, the merged head stays in EXACT parity with skip-ahead — it
   honors `--strict-research-halt` (under it `gated_heads` is empty → the gated head is NOT
   excluded → the run halts on it, opt-in preserved), the two-key skip-ahead predicate, and the
   fully-gated terminal (when no skip-ahead-ready alternative exists the probe clears `gated_heads`
   and dispatches the gated head as its blocked/needs-research terminal → the set is empty → the
   merged head equals that terminal head → the existing terminal, NOT an infinite skip). A skipped
   item is by definition never the dispatched item, so the current dispatch target is never
   excluded.
2. **`lazy-state.py --emit-prompt`** — union `probe_skipped_ids(state, feats)` into the existing
   `nondispatchable_item_ids` exclude set feeding `merged_head_override` (defensively discard the
   current `feature_id`). Add a NON-withholding observability diagnostic when a gated head is
   skipped (the skip also stays visible in the existing `gated_heads` / `*_deferred_features` /
   `dep_gated` keys).
3. **`bug-state.py --emit-prompt`** — coupled-pair mirror (bug pipeline has NO skip-ahead, so its
   skip set is `device_deferred_features` + `operator_deferred`).
4. **`--next-merged` stays PURE** — untouched. It is used only for type-dispatch + as the
   divergence reference; the emit-prompt override is the authoritative skip gate, so
   `--next-merged`'s documented "pure ordering, no per-item state inference" contract is preserved
   intact (a gated head returned there is harmless: the driver type-dispatches to the correct
   state script, which then emits the workable item / redirects across type via the override).

**Not weakened:** no gate softened; the `pending-hardening-debt` / `audit-obligation` withholds
untouched; the `merged-head-diverged` withhold still fires for a genuine dispatchable-item
divergence (a P0 bug jumping the queue). The no-skip common path (single-type workable head; no
gated head) is byte-identical.

## Verified symptom / regression fixtures (`test_lazy_core`)

- **(a) blocked gated head skipped** — a BLOCKED external-gate feature pinned at the merged head
  (tier 0) + a workable independent feature downstream → end-to-end `--emit-prompt` returns NO
  `route_overridden_by`, dispatches the workable feature with a real `cycle_prompt`, and the
  skipped gated head stays observable in `gated_heads`.
- **(b) fully-gated terminal** — every feature BLOCKED → `terminal_reason: blocked` surfaces (the
  existing terminal), NO withhold, no infinite skip.
- **(c) single-type workable head** — byte-identical: normal `cycle_prompt`, no
  `route_overridden_by`, no `gated_heads`.
- **helper unit** — `probe_skipped_ids` collects all id-keyed + name-keyed skip lists (name→id
  resolved) and returns the empty set when the probe skipped nothing.
- **override unit** — with the gated head fed via `exclude_ids`, `merged_head_override` returns
  None (no false withhold) when the workable item is current, yet STILL withholds for a
  dispatchable P0 bug (the withhold retains its precise meaning).

Host-deferred + research-pending gated heads are covered at the helper/unit level (their scoped
sentinel/host fixtures are heavier); the same `probe_skipped_ids` fold handles them via
`host_deferred_features` / `gated_heads`.
