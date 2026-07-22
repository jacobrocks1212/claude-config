---
kind: fixed
feature_id: build-queue-await-hangs-on-stale-lock
date: 2026-07-22
provenance: backfilled-unverified
validated_via: build-queue Pester suites (await/hygiene/runner/build-queue) 219/220, the single failure a pre-existing datetime -BeExactly flake in Write-BuildQueueResult reproduced on clean origin/main (unrelated); pwsh AST parse clean; harness-gate.py gate_weakening false-positive only (retry-ceiling raise); lint-skills / lazy-state --test / bug-state --test / --fsck all OK; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-await-hangs-on-stale-lock marked Fixed on 2026-07-22 during an inline
manual `/harden-harness` round (Round 140). This receipt was written by the harden
round, not the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Notes

Root cause (script-defect): `build-queue-await.ps1`'s poll loop checked only for the
result file and the deadline, so a prior build whose runner died (dead-pid
`active.lock`, no result written) made the waiter poll the full `TimeoutSeconds`
window before a generic timeout.

Fix (commit `a2a4dda0`): a one-shot stale-active-lock check breaks the loop and exits 1
with a diagnostic when `active.lock` belongs to another seq whose `build_pid` is dead
and whose `started_at` age is >= 30 minutes. All reads are `Get-SafeValue`-guarded
(fail safe to not-stale); the waiter never removes the lock (reclaim stays the acquire
loop's job). The dead-pid + other-seq + 30-min conjunction makes a false positive
against a live holder implausible.

Verification: build-queue Pester suites 219/220 (the one failure a pre-existing
datetime-precision flake in `Write-BuildQueueResult`, reproduced on clean origin/main);
pwsh AST parse clean.
