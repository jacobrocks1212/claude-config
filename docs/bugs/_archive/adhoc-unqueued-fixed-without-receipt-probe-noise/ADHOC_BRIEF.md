---
kind: adhoc-brief
bug_id: adhoc-unqueued-fixed-without-receipt-probe-noise
enqueued_by: lazy-adhoc
date: 2026-07-12
---

# Ad-hoc bug: Unqueued Fixed-without-receipt dirs surface as perpetual probe diagnostics

Seven unqueued docs/bugs dirs (subagent-baseline-* x5, efficacy-future-check-unenforced-orchestrator-prose, no-mid-run-observed-friction-harden-dispatch) have SPEC Status Fixed but no valid FIXED.md receipt, so every bug-state.py probe re-emits a 'unqueued Fixed-without-receipt dir surfaced for receipt gate ... completion-unverified' diagnostic per dir. Unqueued so never acted on — perpetual probe noise. Reconcile: backfill receipts / archive, or downgrade the diagnostic for unqueued dirs. Observed during /lazy-bug-batch run 2026-07-12.
