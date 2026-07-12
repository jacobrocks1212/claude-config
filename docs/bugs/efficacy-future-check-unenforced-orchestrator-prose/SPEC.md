# Efficacy/canary/incident future-check is unenforced orchestrator prose — Investigation Spec

> The intervention-efficacy evaluator, harness-change canary, and incident scan run only if the
> orchestrator remembers to invoke them at the end-of-run flush (lazy-batch §1c.6 prose). Nothing
> mechanically guarantees they fire, so the "measure the fix against future runs" loop is skippable
> — and was skipped at a real checkpoint `--run-end` this session.

**Status:** Concluded
**Priority:** P2
**Last updated:** 2026-07-11
**Related:** `docs/interventions/intervention-efficacy-tracking.md` (the loop); lazy-batch SKILL §1c.6 (the prose wiring); `docs/bugs/no-mid-run-observed-friction-harden-dispatch/` (the observed-friction harden must feed this loop).

## Verified Symptom

The self-improving-harness observability loop — `efficacy-eval.py` (CONFIRMED/REFUTED/INCONCLUSIVE per the D5 bands, D6 same-target-signal confounder cap = the non-tautological guard, REFUTED → `reconsider-<id>` auto-enqueue) and `efficacy-eval.py --canary` (regression / ≥2-fresh-incident trip → `canary-revert-<id>`) and `incident-scan.py` — is designed to run ONCE per run at the end-of-run flush, BEFORE `--run-end`. But that invocation is **orchestrator prose only** (lazy-batch SKILL §1c.6): the orchestrator is instructed to run the three scripts, stage `docs/interventions/`, and commit. **Nothing enforces it.**

- `grep` over `lazy_core.py --run-end` / `lazy-state.py`: `--run-end` performs marker deletion, checkpoint write, and the hardening-debt refusal gate, but makes NO call to `efficacy-eval` / `incident-scan` / canary.
- Proof it is skippable: during THIS session's operator-directed checkpoint `--run-end`, the orchestrator (me) skipped the trio entirely — the marker was deleted with no efficacy/canary/incident pass.

**Blast radius (bounded, not catastrophic):** `efficacy-eval` accrues post-ship windows over telemetry `run_id`s that persist in the ledger, so a DUE verdict skipped at run N is still written at the next flush that DOES run — data is not lost, only *timeliness* degrades. The **canary is the time-sensitive loss**: a change's regression window is bounded, and a missed flush during that window can let a regression ride longer before the `canary-revert` fires. And a run of runs that all skip (e.g. a stretch of checkpoint stops) starves the whole loop.

## Root Cause

**Classification: `missing-contract` (enforcement gap).** The loop's TRIGGER — "run the trio at the first terminal / run-end" — was specified as orchestrator discipline (prose) rather than a mechanical gate. Every OTHER load-bearing run-end invariant IS mechanically enforced: `--run-end` refuses on unacked hardening debt, and the checkpoint-authorization gate refuses an attended checkpoint without `--operator-authorized`. The efficacy trio was left as the one unenforced end-of-run obligation.

## Fix Scope (Concluded)

Make the future-check fire at its appropriate future condition (run-end) mechanically, without changing ownership of the doc writes/enqueues/commits (the orchestrator still owns those, so a run's telemetry context is intact when the scripts read it):

- **Gate approach (recommended, mirrors the unacked-hardening gate):** `--run-end` REFUSES (exit 1, marker kept) unless an "efficacy flush ran this run" breadcrumb is present — the trio scripts each drop a run-scoped breadcrumb when invoked (even on a clean no-op), and `--run-end` checks it. A `--efficacy-skip-authorized` operator override (parallel to `--ack-unhardened`) exists for the genuine "no interventions/incidents exist, deliberately skip" case and prints into the run-end message (retro-graded). This keeps the trio + commit orchestrator-owned but makes skipping IMPOSSIBLE-by-accident.
  - Alternative considered — `--run-end` INVOKES the trio itself (subprocess, fail-open, before marker deletion): guarantees firing with zero orchestrator discipline, but moves doc-write/enqueue/commit ownership into `--run-end` and reorders the terminal commit. Heavier; a design fork if the gate approach proves insufficient.
- **Checkpoint run-ends included:** the gate applies to `--reason checkpoint` too (this session's skip was a checkpoint) — a checkpoint is a run boundary; the loop must flush there as well. (A checkpoint that legitimately has nothing due still runs the no-op flush + drops the breadcrumb.)
- **Coupled-trio mirroring** (lazy-batch / lazy-bug-batch / lazy-batch-cloud §1c.6 prose updated to state the gate, not just the obligation) + `test_lazy_core.py` coverage for the run-end gate (refuses without breadcrumb; passes with; override path) + full gates.

## Decisions

- **D1 — Enforcement mechanism:** the breadcrumb-gate (orchestrator still runs + commits the trio; `--run-end` refuses without the breadcrumb). Chosen over `--run-end`-invokes-the-trio to preserve commit ownership + terminal-commit ordering. If implementation shows the breadcrumb can't be reliably dropped run-scoped, escalate the invoke-approach as a NEEDS_INPUT.
- **D2 — Measurable target signals (feeds the observed-friction spec):** an auto-invoked harden's intervention SHOULD declare a MEASURABLE `target_signal` (`event:<type>`) wherever the fix targets a countable ledger signal (e.g. the friction's own recurrence), so the verdict is assertable rather than `undeclared`-INCONCLUSIVE. A genuinely-immeasurable fix (a pure diagnostic like Round 22) still records `undeclared` honestly — but the observed-friction dispatch prompt must PROMPT for a measurable signal first.
