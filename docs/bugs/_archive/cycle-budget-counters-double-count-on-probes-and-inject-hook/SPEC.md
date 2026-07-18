# Cycle-budget counters double-count on probes + the per-turn inject hook

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-17 (captured live in the act during a `/lazy-batch` run on AlgoBooth)
**Fixed:** 2026-07-18
**Fix commit:** 7ad7feaf
**Related:** `feature-budget-guard-and-skip-ahead` (per-feature forward cycles); Round-era fixes
`byref-dispatch-undercounts-forward-cycles`, `byref-forward-cycles-frozen-on-multicycle-same-step`,
and ISSUE-5 (`advance_run_counters` consume-oracle) — this bug supersedes their probe-coupled
advance with a bracket-coupled advance; `lazy-cycle-containment` (the `--cycle-begin`/`--cycle-end`
bracket); `docs/features/unified-pipeline-orchestrator/` (the driver contract).

## Trigger

Operator directive (Jacob, 2026-07-17): the cycle-budget counters (`forward_cycles` / `meta_cycles`)
are DOUBLE-COUNTING because counting is coupled to PROBE invocations (and to orchestrator-remembered
`increment` / `do-not-increment` bookkeeping). Offload cycle-counting to the SCRIPT so a cycle counts
when-and-only-when a real dispatch actually happens, decoupled from probes.

## Live evidence (captured in the act)

1. **Probe advances the budget.** Three `lazy-state.py … --repeat-count --emit-prompt --probe`
   routing-DISCOVERY probes (zero dispatches between them) drove `forward_cycles` 0 → 3 with
   `per_feature_forward_cycles = {hydra-overlay:1, adhoc-incident-hook-deny-9b8ff7:1,
   protocol-generic-claims-drift:1}`. Each probe had a DIFFERENT `(feature_id, current_step,
   sub_skill)` tuple, so `advance_forward_cycle`'s state-change trigger fired on each — no dispatch,
   yet the budget rose by 3.
2. **The inject hook advances the budget on a NON-dispatch turn.** After ONE real dispatch
   (`forward_cycles=1`), the operator sent a chat message (no cycle dispatched); the per-turn inject
   hook (`lazy-route-inject.sh` → `lazy_inject.py`) fired its full `--repeat-count` probe and bumped
   `forward_cycles` to 2, adding a phantom `adhoc-incident-hook-deny-9b8ff7:1`.

## Reconstructed route (divergence point)

`forward_cycles` is advanced by `lazy_core.advance_forward_cycle(state, consume_gate=True)` on the
`--repeat-count` probe path (`lazy-state.py` ~13685; `bug-state.py` ~9336). It advances on EITHER a
`(feature_id, current_step, sub_skill)` state-change OR a consume-census rise. The state-change
trigger (added for the multi-part execute-plan freeze) makes DISTINCT-item probes each advance, so
ANY probe caller — an inspection probe, the dispatch-bound probe, AND the per-turn inject-hook probe —
inflates the budget with no dispatch. `meta_cycles` is advanced separately at `--emit-dispatch`
(`advance_meta_cycle`, ~13038). The orchestrator ALSO carries ~15 prose "increment / do-not-increment"
instructions it must remember across compaction — fragile.

**Divergence point:** budget counting is a side effect of the PROBE / `update_repeat_counts` path
instead of a real dispatch event the script observes.

## Root cause

**`root_cause_class: script-defect`** — the budget counters are coupled to probe invocations. The
loop-detection streaks (`repeat_count` / `step_repeat_count`) legitimately advance on probes, but the
BUDGET counters must not: they should advance only on a completed dispatch the script already
brackets.

## Fix scope

Make the SCRIPT the sole budget authority, keyed on the dispatch events it already observes; DECOUPLE
the budget counters from the probe / `update_repeat_counts` streak path.

- **`--cycle-end` is the bracket increment point** (the `--cycle-begin`/`--cycle-end` bracket wraps
  exactly ONE Agent dispatch and carries `--kind real|meta` + `--sub-skill`): on `--cycle-end`,
  increment `forward_cycles` (+ the sibling `per_feature_forward_cycles` bump) when the cycle marker's
  `kind == "real"`, or `meta_cycles` when `kind == "meta"`. Idempotent per bracket (one cycle marker =
  one dispatch = one increment; the marker is cleared at `--cycle-end`).
- **`--apply-pseudo` keeps its increment** (pseudo-skills dispatch no Agent, so they are not
  bracketed): forward-advancing pseudos (`__mark_complete__` / `__mark_fixed__` / `__write_validated_*`
  / `__grant_skip_no_mcp_surface__` / `__flip_plan_complete_cloud_saturated__`) → `forward_cycles`;
  cleanup pseudos (`__flip_plan_complete_stale__`) → `meta_cycles`. Unchanged (it is already
  script-owned + probe-decoupled).
- **REMOVE the probe-path forward advance** (`lazy-state.py` ~13685, `bug-state.py` ~9336) and the
  **`--emit-dispatch` meta advance** (`advance_meta_cycle`, ~13038): meta dispatches are bracketed
  `--kind meta`, so `--cycle-end` now counts them — counting at `--emit-dispatch` would double-count.
  The probe no longer touches the budget; `update_repeat_counts` (streaks) is untouched.

**Safety:** `forward_cycles` is the only capped counter (`>= max_cycles`). It now advances only on a
bracketed real dispatch (the SKILL mandates bracketing every dispatch) or a forward pseudo-apply — so
inspection / inject-hook probes are budget-neutral (requirements a, b) and a real bracket counts
exactly once (c). `meta_cycles` is uncapped, so any residual meta under-count (an unbracketed meta
dispatch, contract-forbidden) is harmless to the halt.

## Coupled-pair / parity note

`--cycle-begin`/`--cycle-end` + `--apply-pseudo` are mirrored in `lazy-state.py` and `bug-state.py`;
the increment logic lands in a shared `lazy_core.markers` helper consumed by both. The inject hook
(`lazy_inject.py`) needs no change — removing the probe-path advance makes its per-turn probe
budget-neutral automatically (it advances only the streaks, a separate concern with its own debounce).
The coupled trio (`/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud`) prose is reconciled: the ~15
orchestrator "increment forward_cycles / increment meta_cycles / DO NOT increment" instructions become
"the SCRIPT increments on `--cycle-end` (keyed on `--kind`) / `--apply-pseudo`" — the orchestrator no
longer hand-counts. The two-counter semantics (forward capped at `max_cycles`, meta uncapped) and the
monotonic-across-feature-transitions rule (HARD CONSTRAINT 8) are preserved. `lazy_parity_audit.py`
stays green.

## Regression tests

(a) N inspection probes with zero dispatches leave `forward_cycles` unchanged; (b) the inject-hook
per-turn probe on a non-dispatch turn leaves `forward_cycles` unchanged; (c) one real `--cycle-begin
--kind real … / --cycle-end` bracket increments `forward_cycles` by exactly 1 (+ per-feature bump);
(d) a `--kind meta` bracket increments `meta_cycles` not `forward_cycles`, and a cleanup
`--apply-pseudo` increments `meta_cycles`; (e) a forward-advancing `--apply-pseudo` increments
`forward_cycles`.
