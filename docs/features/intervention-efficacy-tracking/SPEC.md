# Intervention Efficacy Tracking (Hypothesis Ledger) — Feature Specification

> Every harness change is an implicit hypothesis ("this gate/hook/contract change will reduce friction signal X") that is never tested. Record the hypothesis at ship time — targeted signal, baseline, expected direction, review-by date — then evaluate it against post-ship telemetry and write a CONFIRMED / REFUTED / INCONCLUSIVE verdict. A refuted intervention auto-enqueues a reconsideration item instead of quietly persisting as dead weight.

**Status:** Draft (pre-Gemini)
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution batch)

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock; composes with `harness-telemetry-ledger` (signal source), `friction-kpi-registry` (signal vocabulary), `code-doc-provenance-linkage` (change → commits mapping))

---

## Problem

The harness self-improves via retros and `/harden-harness`, but the loop is open: interventions
ship, their COMPLETED.md claims success, and nothing ever checks whether the targeted friction
actually declined. Interventions that didn't work — or made things worse — accumulate
indefinitely because there is no mechanism that ever concludes "this change failed."

## Direction (deliberately not locked)

- **Capture:** at `__mark_complete__`/`__mark_fixed__`/harden-round commit, an intervention record
  is written (deterministic, script-owned): item id, targeted friction signal (a KPI-registry or
  ledger event reference), baseline window stats, expected direction, review-by date.
- **Evaluation:** a scheduled/on-demand evaluator compares the post-ship window against baseline
  and writes a verdict artifact. Single-operator reality: before/after with confounder
  annotations (other interventions landing in the window are recorded on the verdict), not
  pretend A/B rigor.
- **Verdict consequences:** REFUTED → auto-enqueue a reconsideration bug stub (revert/redesign),
  evidence attached; INCONCLUSIVE past N reviews → surfaced for operator triage; CONFIRMED →
  closes the hypothesis. Verdicts are inputs to `/lazy-batch-retro`, replacing narrative claims.
- **Independence rule:** the evaluator reads telemetry the intervention does not itself emit
  wherever possible — tautology avoidance is the sibling `anti-overfit-design-gate`'s concern,
  but the record schema should carry a "signal independence" field from day one.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: record schema + residency; window
> lengths and minimum-sample rules; confounder annotation mechanics; backfill for already-shipped
> interventions. Solutions above are directional, not locked.
