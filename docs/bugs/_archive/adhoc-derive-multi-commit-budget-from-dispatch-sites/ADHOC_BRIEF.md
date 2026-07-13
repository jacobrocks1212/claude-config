---
kind: adhoc-brief
bug_id: adhoc-derive-multi-commit-budget-from-dispatch-sites
enqueued_by: lazy-adhoc
date: 2026-06-25
---

# Ad-hoc bug: Derive multi-commit cycle-commit budget from dispatch sites, not a hand-maintained registry

The _MULTI_COMMIT_DISPATCH_SKILLS frozenset in lazy_core.py still requires a human/agent to manually enumerate every multi-commit dispatch identity; a newly-dispatched multi-commit skill silently defaults to budget 1 and false-positives unexpected-commits until someone remembers to add it. This missing-row class has recurred 6+ times (hardening Rounds 15 execute-plan, 16/17 pseudo-skills, 23 mcp-test, 31 plan-feature/plan-bug, and 2026-06-25 spec/spec-bug). The adhoc-derive-cycle-commit-budget refactor that introduced the frozenset only relocated the enumeration from a literal dict to a hand-maintained set; it did not close the class. Class boundary: derive the per-sub_skill commit budget structurally from the dispatch sites themselves (the sub_skill= literals in lazy-state.py and the SKILL_* constants in bug-state.py) or from a per-skill commit-cadence declaration the skills own, so any newly-dispatched multi-commit skill is budgeted correctly without a manual registry append. In scope: the cycle-commit-budget derivation only. Out of scope: any change to the friction-detection thresholds or the runaway ceiling. Origin: harden-harness Round 38 (2026-06-25), commit 0ece589, lazy_core.py:_MULTI_COMMIT_DISPATCH_SKILLS.
