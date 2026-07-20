---
kind: adhoc-brief
bug_id: adhoc-execute-plan-liveness-no-true-liveness-signal
enqueued_by: lazy-adhoc
date: 2026-07-20
---

# Ad-hoc bug: execute_plan_liveness has no true liveness signal — verdict patched per-branch (structural)

execute_plan_liveness (lazy_core/markers.py) derives every verdict from marker-presence + plan-status + a write-once (never-heartbeated) marker mtime. Rounds 129 (wedge-candidate on stale marker) and 130 (commit-pending on plan-Complete) are two consecutive per-branch patches to the SAME discriminator; the class recurred >=2x. Structural fix: give the discriminator a genuine liveness signal — heartbeat the execute-plan marker mtime during the cycle, and/or collapse the per-branch candidate verdicts into a single confirm-then-recover seam that ALWAYS consults the TaskList lineage probe before recover/wait. Origin: harden Round 130 over-fit signal 2.
