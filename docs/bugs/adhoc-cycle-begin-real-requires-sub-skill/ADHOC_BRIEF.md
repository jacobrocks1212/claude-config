---
kind: adhoc-brief
bug_id: adhoc-cycle-begin-real-requires-sub-skill
enqueued_by: lazy-adhoc
date: 2026-07-04
---

# Ad-hoc bug: cycle-begin --kind real should require/validate --sub-skill (write-side durable fix)

Harden-harness Round 3 spin-off from skip-mcp-test-frontmatter-unquoted-colon. The recurring unexpected-commits false-positive class (Rounds 15/16/17/19 + Round 3) all stem from a cycle marker written with sub_skill=None because the orchestrator omitted --sub-skill at --cycle-begin. Round 3 shipped the read-side fail-open guard; this item is the durable write-side fix: make bug-state.py and lazy-state.py --cycle-begin --kind real require or validate --sub-skill so the marker can never be written sub_skill-less. In scope: the --cycle-begin write-side sub_skill contract on both state scripts plus smoke fixtures. Out of scope: budget thresholds and the _MULTI_COMMIT_DISPATCH_SKILLS registry class (open bug adhoc-derive-multi-commit-budget-from-dispatch-sites) and the read-side guard already shipped.
