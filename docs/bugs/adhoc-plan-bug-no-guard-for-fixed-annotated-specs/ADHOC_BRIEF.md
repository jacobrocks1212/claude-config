---
kind: adhoc-brief
bug_id: adhoc-plan-bug-no-guard-for-fixed-annotated-specs
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: plan-bug Step 0.4 lacks a guard for Fixed-annotated / already-implemented SPECs

Five pipeline cycles across two runs burned full plan-bug dispatches (~100-200k tokens each) discovering a Concluded SPEC's fix scope was already fully implemented out-of-pipeline. plan-bug's Step 0.4 status gate reads only the literal Status line; it ignores the '**Fixed:** <date> - implemented out-of-pipeline' annotation line and has no cheap on-disk fix-scope pre-check. Fix shape: Step 0.4 gains a mechanical pre-gate - if the SPEC carries a **Fixed:** annotation (or the fix-scope grep-anchors all resolve present), refuse the planning round with a distinct 'fixed-unreconciled' outcome that instructs the orchestrator to run the docs/bugs/CLAUDE.md reconciliation contract instead; consider a bug-state.py probe-time diagnostic for the same signature so the item never routes to plan-bug at all. Related: Round 90 (harden-side reconciliation contract, 38144ada), this run's 6-bug reconciliation sweep.
