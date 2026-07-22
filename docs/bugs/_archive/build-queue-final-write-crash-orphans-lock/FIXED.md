---
kind: fixed
feature_id: build-queue-final-write-crash-orphans-lock
date: 2026-07-22
provenance: backfilled-unverified
validated_via: build-queue Pester suites (await/hygiene/runner/build-queue) 219/220, the single failure a pre-existing datetime -BeExactly flake in Write-BuildQueueResult reproduced on clean origin/main (unrelated); pwsh AST parse clean; harness-gate.py gate_weakening false-positive only (retry-ceiling raise 15->50); lint-skills / lazy-state --test / bug-state --test / --fsck all OK; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-final-write-crash-orphans-lock marked Fixed on 2026-07-22 during an inline
manual `/harden-harness` round (Round 141). This receipt was written by the harden
round, not the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Notes

Root cause (script-defect): the runner's FINAL result write (pending -> complete) was
inlined but not wrapped against the write itself throwing (results-dir creation,
`ConvertTo-Json`, `File.WriteAllText`/`Replace`); a throw there left `active.lock` held
with no usable result. Co-located: build-log reads used `ReadAllText` (`FileShare.Read`),
which hits a sharing violation against the still-open child-stdout handle, and the read
retry window was too short for a slow Nx daemon's delayed flush.

Fix (commit `ed7dbea8`): serialize the result body under `Get-SafeValue`; guard the
temp-write + atomic `File.Replace` (direct-write fallback) with a `$finalWriteSucceeded`
flag; and on failure ALWAYS write a minimal fallback result (preferring the early-write
record) so a final-write crash cannot strand the lock. Added `Ensure-ResultsDirectory`
(retry, fail-open) in hygiene, called before the final write. Companion output-path
robustness in the same commit: share-tolerant build-log reads (`FileShare.ReadWrite` via
`File.Open` + `StreamReader`) and a widened read window (15 -> 50 attempts) — a raised
retry ceiling and broader share mode (strictly more robust, not a weakened gate).

Verification: build-queue Pester suites 219/220 (the one failure a pre-existing
datetime-precision flake in `Write-BuildQueueResult`, reproduced on clean origin/main);
pwsh AST parse clean; harness-gate `gate_weakening: hit` is the retry-ceiling numeric
literal only (false positive), `overfit: pass`.
