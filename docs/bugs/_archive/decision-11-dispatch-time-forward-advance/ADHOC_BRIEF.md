---
kind: adhoc-brief
bug_id: decision-11-dispatch-time-forward-advance
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: Implement decision 11: forward-advance moves to dispatch time (probe path becomes PEEK; subsumes decision 3)

RESOLVED 2026-07-18 (turn-routing-enforcement NEEDS_INPUT decisions 11+3): move the forward_cycles advance OFF banner-emission to the actual dispatch bracket (guard-ALLOW consume / --cycle-begin); the inject-hook --repeat-count probe path becomes a pure PEEK. Retarget (do not invert) the pinned tests test_advance_forward_cycle_consume_gate_advances_multicycle_same_step and test_advance_forward_cycle_verbatim_real_skill_theory_1b to dispatch-time advance; preserve within-cycle idempotence and the --apply-pseudo forward-advancing-pseudo-skill apply-bracket advance. Fixes BOTH the notification-turn over-count (archived lazy-run-marker-park-arm-and-forward-cycle-inflation DEFECT 1) and decision 3's under-count. Full resolution text: docs/specs/turn-routing-enforcement/NEEDS_INPUT.md decision 11.
