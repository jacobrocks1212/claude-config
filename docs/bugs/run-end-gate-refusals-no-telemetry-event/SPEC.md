# Run-end gate refusals emit no `gate-refusal` telemetry event — Investigation Spec

> The state scripts' `--run-end` gates refuse (exit 1, marker kept) — unacked-hardening-debt,
> the new efficacy-flush-missing gate, and checkpoint-authorization — WITHOUT emitting a
> telemetry event, so those refusals are invisible to the efficacy loop that measures harness
> health. The mechanism already exists (`append_telemetry_event`, already emitted for
> `containment-refusal` and the `--verify-ledger` `gate-refusal`); the run-end refusal sites
> just don't call it — so a fix targeting run-end refusals has no countable signal to grade against.

**Status:** Concluded
**Priority:** P3
**Severity:** low
**Last updated:** 2026-07-11
**Related:** `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` (its Round 24 noted this gap); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 24; `docs/bugs/no-mid-run-observed-friction-harden-dispatch/` + the efficacy spec (the loop this feeds); `docs/bugs/completion-gate-refusal-opacity/` (sibling `gate-refusal` observability item); `harness-telemetry-ledger` Phase 2 / D4-B (`append_telemetry_event`, `lazy_core.py:15812`).

## Provenance

Spun off from the 2026-07-11 harden-harness follow-up run (Gap B). Gap A of that run
(`project-skills-under-projects-machine-variable-repos-dir`) landed as commits `011aa7d` +
`367711a` (hardening Round 26); Gap B was deferred to the bug pipeline (operator decision
2026-07-11) so a `/lazy-bug-batch` run could proceed without a concurrent writer. The design
below is fully captured from Round 24's "recorded, not chased" note + the efficacy spec — no
information was lost in the deferral.

## Verified Symptom

The run-end gates in `lazy-state.py` / `bug-state.py` refuse (exit 1, **marker kept**) at three sites, none of which emit a telemetry event:

1. **Unacked-hardening-debt** — `pending_hardening() > 0` without `--ack-unhardened` (`lazy_core.py` ~:14191, `pending_hardening()` ~:15564).
2. **Efficacy-flush-missing** — the gate landed in commit `7d49490`: `--run-end` refuses without the run-scoped efficacy-flush breadcrumb (and without `--efficacy-skip-authorized`).
3. **Checkpoint-authorization** — an attended `--run-end --reason checkpoint` without `--operator-authorized` (`lazy_core.py` ~:10531).

The telemetry mechanism is present and the pattern is established elsewhere: `append_telemetry_event("gate-refusal", ...)` is already emitted for `--verify-ledger` refusals (see `lazy-state.py` test refs ~:10197 / ~:10366), and `append_telemetry_event("containment-refusal", ...)` for the cycle-active guard (`lazy_core.py` ~:12091). The run-end refusal family simply does not participate.

**Consequence:** `efficacy-eval.py` cannot measure run-end refusal rates. The just-landed efficacy-flush gate (`7d49490`) and the observed-friction / efficacy specs therefore have no countable ledger signal to assert against — their intervention records degrade to `target_signal: undeclared` (INCONCLUSIVE-by-construction) purely because the signal is never emitted.

**Blast radius (bounded):** observability only. No state is lost and no refusal decision changes — the gates already behave correctly. The gap is purely *measurement blindness* to how often each run-end gate fires.

## Root Cause

**Classification: `missing-contract` (observability gap).** The telemetry ledger (harness-telemetry-ledger Phase 2, D4-B) instrumented the containment guard and the `--verify-ledger` gate but never extended to the run-end refusal family. Each run-end refusal computes its decision and exits without the observability-only append its siblings perform.

## Fix Scope (Concluded)

- Emit `append_telemetry_event("gate-refusal", item_id=<marker feature/bug id>, data={"gate": "unacked-hardening" | "efficacy-flush-missing" | "checkpoint-auth", "op": "--run-end", "reason": <short>})` at each of the three run-end refusal sites, mirroring the existing `containment-refusal` / `--verify-ledger` `gate-refusal` call sites — **observability-only, marker-gated, fail-open, ZERO new state side effects, gate behavior UNCHANGED** (still refuses / exits 1).
- **Coupled-pair:** mirror across both `lazy-state.py` and `bug-state.py`.
- **Tests** in `test_lazy_core.py`: assert the event is appended on each refusal path (unacked-hardening / efficacy-flush-missing / checkpoint-auth); register every new `def test_*` in a `_TESTS` list (the `test_no_orphaned_test_functions` guard fails otherwise).
- **Loop closure:** this supplies the measurement half for run-end refusals, so the efficacy gate from `7d49490` and the observed-friction / efficacy interventions can declare a real `target_signal: event:gate-refusal` (`--expected-direction decrease`) instead of `undeclared`.

## Decisions

- **D1 — Reuse the existing `gate-refusal` kind** (already emitted for `--verify-ledger`) with a `data.gate` discriminator, rather than a new per-gate telemetry kind — keeps the efficacy loop's aggregation simple and lets one `event:gate-refusal` signal cover the whole gate family.
- **D2 — Observability-only, fail-open:** the event is additive; it must NEVER change the refusal decision or add a state side effect (same standing the deny ledger has at guard-deny time). A telemetry append failure is a silent no-op, never a gate change.
- **D3 — Worked via `/lazy-bug-batch`, not `/harden-harness`** (operator decision 2026-07-11): so it will NOT get a HARDENING.md round or a harden intervention record. Accepted tradeoff — the efficacy-loop signal is the deliverable, not the harden audit ritual. The bug pipeline's `__mark_fixed__` receipt is the audit trail.
