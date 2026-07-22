---
kind: fixed
feature_id: build-queue-stale-lock-detection-too-lazy
date: 2026-07-22
provenance: backfilled-unverified
validated_via: build-queue-hygiene Pester Test-ShouldReclaimLock 11/11 (incl. 5 new age-path tests); full build-queue suites 219/220, the single failure a pre-existing datetime -BeExactly flake reproduced on clean origin/main (unrelated); pwsh AST parse clean; lint-skills / lazy-state --test / bug-state --test / --fsck all OK; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-stale-lock-detection-too-lazy marked Fixed on 2026-07-22 during an inline
manual `/harden-harness` round (Round 142). This receipt was written by the harden
round, not the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Notes

Root cause (script-defect): both reclaim paths (`Test-ShouldReclaimLock` when the hygiene
module is present, and the inline fallback counter) required 3 consecutive `'dead'`
observations before removing an abandoned `active.lock`; neither the classifier nor the
reclaim decision considered lock age. An earlier in-tree WIP added an age check inside the
inline classifier, but every dead-pid branch returned `'dead'` regardless — a semantic
no-op that could not shorten the 3-tick wait, and it left the production hygiene path
age-blind. This fix supersedes that attempt by threading age into the reclaim DECISION.

Fix (commit `ed7dbea8`): `Test-ShouldReclaimLock` gains optional `LockAgeMinutes` /
`MaxAgeMinutes` (default -1 disables the age path, preserving prior behavior and existing
tests); an abandoned lock (dead holder, 30+ min old, trailing-`dead` observation, lowest
seq) now reclaims on the first dead tick. The poll loop threads the age via a new
`Get-ActiveLockAgeMinutes` helper on both the hygiene and inline-fallback paths; the no-op
age block is removed from the pid-liveness classifier. Added 5 Pester tests. This raises
reclaim responsiveness while never reclaiming a live holder — the age path still requires
a dead observation and lowest-seq gating.

Verification: `Test-ShouldReclaimLock` Pester 11/11 (5 new age cases); full build-queue
suites 219/220 (the one failure a pre-existing datetime-precision flake, reproduced on
clean origin/main); pwsh AST parse clean.
