---
kind: adhoc-brief
bug_id: adhoc-derive-cycle-commit-budget
enqueued_by: lazy-adhoc
date: 2026-06-22
---

# Ad-hoc bug: Derive cycle-commit budget from a single source of truth

The _CYCLE_COMMIT_BUDGET allow-list in lazy_core.py is a hand-maintained dict keyed by dispatched sub_skill name; any multi-commit sub_skill absent from it defaults to budget 1 and false-positives unexpected-commits at --cycle-end. This missing-budget-row defect class has recurred five times: Round 15 added execute-plan, Rounds 16/17 added __mark_complete__/__mark_fixed__, a later round added mcp-test, and the 2026-06-22 d2-sample-import-ui round added write-plan/plan-feature/plan-bug. Each round reactively appends another literal row after a production false-positive (over-fit signal 1+2). Replace the reactive allow-list with a single source of truth: derive the per-sub_skill commit budget from the orchestrator dispatch-skill registry / per-skill metadata (the same place sub_skill names already originate in lazy-state.py / bug-state.py dispatch sites), so a newly added multi-commit sub_skill cannot silently default to 1. Class boundary IN: any dispatched sub_skill whose cycle legitimately commits more than once and is keyed in _CYCLE_COMMIT_BUDGET. OUT: the budget_override path (already phase-scaled for execute-plan, Round 20) and the kind==meta exemption (Round 19) — leave both intact. Propose no behavior beyond making the budget table self-populating/derived so the recurring missing-row gap closes structurally. Origin: harden-harness Round 31 (2026-06-22), commit 8039dbc.
