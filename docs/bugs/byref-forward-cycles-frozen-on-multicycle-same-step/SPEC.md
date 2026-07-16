# `forward_cycles` Frozen at 1 Across Multi-Cycle Same-Step Dispatches — Investigation Spec

> The run marker's `forward_cycles` budget counter advances only on a CHANGE in the
> `(feature_id, current_step, sub_skill)` state tuple (`advance_forward_cycle`, the sole
> forward-advance trigger wired on the real-skill `--repeat-count` probe path since the
> `byref-dispatch-undercounts-forward-cycles` Phase-1 reconciliation). A multi-part
> `/execute-plan` implementation dispatches the SAME real sub_skill for the SAME feature at the
> SAME step, one cycle per plan part — an IDENTICAL tuple every cycle. After the first advance
> sets `last_advance_state_key`, every later same-step cycle sees `prior_key == current_key` and
> no-ops, so `forward_cycles` sticks at 1 for the entire phase. `Step 1c`'s max-cycles cap
> (`forward_cycles >= max_cycles`) can therefore NEVER trip — an unbounded run against the
> operator's cost budget. The frozen counter also freezes the derived `cycle_header` (`[1/10]`)
> and the inject-banner turn number (`forward_cycles + meta_cycles + 1` → perpetual "turn 2").

**Status:** Concluded
**Severity:** P1 (safety/cost — the max-cycles budget cap, the only mechanical ceiling on an
autonomous `/lazy-batch` run, is fully defeated for any feature whose implementation spans
multiple same-step cycles; the run is unbounded against the operator's cost budget)
**Discovered:** 2026-07-16
**Placement:** docs/bugs/byref-forward-cycles-frozen-on-multicycle-same-step
**Related:**
- `byref-dispatch-undercounts-forward-cycles` (archived-fixed) — Phase 1 REPLACED the
  consume-oracle (`advance_run_counters`) with `advance_forward_cycle` (state-change trigger) as
  the forward authority on the real-skill probe path. That replacement introduced THIS
  regression: the state tuple does not change across same-step cycles, so nothing advances.
- `hardening-log/2026-06.md` Round (NEEDS_INPUT decision 3): "forward_cycles stalled at 2 across
  three consecutive by-ref execute-plan cycles" — the SAME class, surfaced as a design fork.
- `hardening-log/2026-07.md` (line ~473): "forward_cycles lags true completed-cycle count …
  deliberately NOT fixed" — the SAME class, deferred. Both prior diagnoses blamed the
  consume-census oracle's ring-cap non-monotonicity, but that oracle is no longer even on the
  forward path — masking the real state-key-freeze root cause until this round.

## Reconstructed route (the divergence)

Observed-friction, no probe. Live `/lazy-batch` run (repo AlgoBooth, item `hydra-overlay`, marker
`~/.claude/state/37850b6e…/lazy-run-marker.json`). Two genuine execute-plan cycles ran and were
dispatched + re-probed (commits `4639cb9d8` and `3b5e2b0a8`/`63a797e08`), yet the marker read:

```
forward_cycles = 1
per_feature_forward_cycles = {hydra-overlay: 1}
last_advance_consume_count = 0
meta_cycles = 0
```

Both inject banners reported "turn 2"; every dispatch-bound probe emitted
`### Implement — hydra-overlay [1/10]` regardless of completed-cycle count.

## Root cause (`script-defect`)

`user/scripts/lazy_core/markers.py::advance_forward_cycle` advances iff the current
`[feature_id, current_step, sub_skill]` tuple DIFFERS from the marker-recorded
`last_advance_state_key`. It is the ONLY forward-advance trigger called on the real-skill
`--repeat-count` probe path (`user/scripts/lazy-state.py`, `if args.repeat_count:` →
`advance_forward_cycle(state)`) — `advance_run_counters` (the consume-oracle) was explicitly
retired from this path in the `byref-dispatch-undercounts-forward-cycles` Phase-1 reconciliation.

A multi-part `/execute-plan` phase dispatches one cycle per plan part, all with the identical
tuple `(hydra-overlay, "Step 7a: execute plan", /execute-plan)`. After cycle 1 sets
`last_advance_state_key`, cycles 2..N see `prior_key == current_key` → the "bare re-fire" no-op
branch → no advance. Hence `forward_cycles` = 1 forever.

The marker fields corroborate exactly:
- `last_advance_consume_count = 0` — NOT a contradiction: that field is written only by
  `advance_run_counters` / `advance_meta_cycle`, NEITHER of which runs on this path. It is
  vestigial here, so it never moved. (Prior rounds mis-read this as the consume-oracle failing.)
- Both inject banners "turn 2": `lazy_inject._turn_n` = `forward_cycles + meta_cycles + 1` =
  `1 + 0 + 1` = 2, every turn. A downstream symptom of the frozen counter, not a separate defect.
- `[1/10]` header: derived from the frozen `forward_cycles`.

One root cause explains all three symptoms.

## Fix scope

Add a SECOND advance trigger to `advance_forward_cycle`, opt-in via a keyword-only
`consume_gate: bool = False`: on the real-skill probe path (only), advance when the state tuple
changed OR the registry consume-census rose since the last advance (with the same down-step
CLAMP and shared `last_advance_consume_count` watermark as `advance_run_counters`, so ring-cap
eviction and the meta path's +1 absorb stay coherent). A bare re-fire (same tuple AND no new
consume) still no-ops. The pseudo `--apply-pseudo` caller keeps the default (`consume_gate=False`)
— its distinct-tuple-per-apply invariant already discriminates and it emits no consume.
`lazy-state.py`'s real-skill probe path passes `consume_gate=True`.

Regression tests (`tests/test_lazy_core/test_markers.py`): forward_cycles advances once per
distinct consumed dispatch across ≥3 identical-tuple cycles, bare re-fires no-op, and the default
(no gate) path stays byte-identical.

## Durable generalization (spun off)

`forward_cycles` accounting has now been patched across TWO triggers over three rounds
(consume-oracle ring-cap non-monotonicity, then this state-key freeze). The durable fix is a
single authoritative MONOTONIC cumulative dispatch counter incremented at consume time (never
ring-evicted), replacing both the live-census oracle and the state-key heuristic as the forward
budget's ground truth. Spun off as a `/spec-bug` (over-fit signal 2: class recurred ≥2×). This
spec's mechanical fix resolves the observed freeze and the common case; the spin-off targets the
residual long-run census-lag class.
