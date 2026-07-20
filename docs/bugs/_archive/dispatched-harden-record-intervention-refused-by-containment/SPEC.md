# Dispatched harden-harness cannot record its own intervention (containment refuses `--record-intervention`)

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-17 (surfaced by the prior dispatched harden-harness run, Rounds 65-67; the depth-1 self-recursion guard blocked that run from hardening its own machinery)
**Fixed:** 2026-07-18
**Fix commit:** e08bf3ac
**Related:** `turn-routing-enforcement` (cycle containment C3); `intervention-efficacy-tracking` (the `--record-intervention` capture contract); `hardening-blind-to-process-friction` (the `refuse_if_cycle_active` / `LAZY_ORCHESTRATOR` identity plane); the `/harden-harness` SKILL "Intervention record for the round" contract.

## Trigger

When `/harden-harness` runs as a **dispatched cycle subagent** (the PRIMARY trigger path — a harden emitted mid-pipeline via `--emit-dispatch hardening` while a live lazy run marker is present, with `LAZY_ORCHESTRATOR` UNSET because a subagent's shell never inherits the orchestrator's export), the harden agent MUST record its round as a hypothesis-ledger intervention with a MEASURABLE `target_signal` (SKILL "Intervention record for the round" — mechanically enforced on the CLI path). But the cycle-containment C3 refusal (`lazy_core.markers.refuse_if_cycle_active`) DENIES `lazy-state.py --record-intervention` (exit 3, treated as an orchestrator-only run-lifecycle/state mutation a cycle subagent may not perform).

Net: on the primary trigger path, the required capture CLI is blocked exactly when the SKILL mandates it. The prior run had to hand-author three intervention records as `baseline: not-computable` backfills — the measurement contract degraded to prose.

## Reconstructed route (divergence point)

- `lazy-state.py` (`if args.record_intervention:`, ~13403) and `bug-state.py` (~9108) both call `lazy_core.refuse_if_cycle_active("--record-intervention")` at handler entry — the same guard `--run-end` / `--run-start` / `--emit-dispatch` / `--apply-pseudo` / `--enqueue-adhoc` use.
- `refuse_if_cycle_active` (`lazy_core/markers.py`) decides subagent-vs-orchestrator in priority order: (1) `LAZY_ORCHESTRATOR` truthy → return; (2) `LAZY_CYCLE_SUBAGENT` truthy → refuse; (3) cycle marker present → refuse (exit 3, zero side effects, `containment-refusal` telemetry).
- A dispatched harden hits case (2)/(3): `LAZY_ORCHESTRATOR` is unset, the orchestrator's cycle marker is present → **refused**.

**Divergence point:** `--record-intervention` (capture-only telemetry — it writes `docs/interventions/<id>.md`, no run-marker/registry/queue mutation) is gated by the SAME lifecycle-refusal as the genuinely-dangerous routing/lifecycle ops, so the one op a dispatched harden is REQUIRED to run is refused.

## Root cause

**`root_cause_class: missing-contract`** — the containment layer has no exemption for the capture op a dispatched hardening subagent must perform. `--record-intervention` was added to `CYCLE_REFUSED_OPS`-adjacent handlers "exactly like `--enqueue-adhoc`" without recognizing that a hardening cycle is the ONE cycle whose SKILL contract requires it. The bash C2 hook (`lazy-cycle-containment.sh`) does NOT list `--record-intervention` in `LOOP_FORMATION_FLAGS`, so the refusal is purely the Python-side C3 guard.

## Fix scope

Permit `--record-intervention` for a dispatched **hardening-class** cycle subagent, keyed on the cycle marker's own `sub_skill` (approach (a) — the marker already records `sub_skill`; the hardening dispatch is bracketed `--kind meta --sub-skill hardening`). Keep every genuinely-dangerous lifecycle op refused.

- `refuse_if_cycle_active(op_name, *, allow_hardening_subagent=False)`: in the refuse branch, when `allow_hardening_subagent` is set AND the cycle marker's `sub_skill` is a hardening class (`{"hardening"}` — the `dispatch.DISPATCH_CLASSES` tag), RETURN silently (permit) instead of exiting 3. Only `--record-intervention` passes the flag; `--run-end` / `--run-start` / `--emit-dispatch` / `--apply-pseudo` / `--enqueue-adhoc` / the routing probe do NOT — they stay refused for a cycle subagent.
- Both `lazy-state.py` and `bug-state.py` `--record-intervention` handlers pass `allow_hardening_subagent=True`.
- SKILL prose (coupled trio §1d.1): make the hardening dispatch bracket explicit — `--kind meta --sub-skill hardening` — so the marker reliably carries the `sub_skill` the exemption keys on.

## Verified symptom → target signal

- **Before:** a dispatched harden's `lazy-state.py --record-intervention` under a `sub_skill: hardening` cycle marker (`LAZY_ORCHESTRATOR` unset) exits 3 (containment refusal).
- **After (target):** the same invocation exits 0 and writes the record; a NON-hardening cycle marker (`sub_skill: execute-plan`) STILL refuses `--record-intervention` (exit 3); a hardening cycle marker STILL refuses `--run-end` / `--emit-dispatch` (exit 3). Measured signal: `event:containment-refusal` count decreases (the record-intervention false-refusal subset → 0).
