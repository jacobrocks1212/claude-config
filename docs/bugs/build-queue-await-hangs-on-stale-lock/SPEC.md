# Bug: build-queue-await polls to timeout behind a stale active.lock instead of failing fast

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-22
**Placement:** docs/bugs/build-queue-await-hangs-on-stale-lock
**Related:** `docs/bugs/build-queue-timeout-kill-reaps-detached-runner` (the runner-death class that strands `active.lock` held by a dead pid with no result written — the exact state this waiter mis-handles), `docs/bugs/build-queue-final-write-crash-orphans-lock` (companion — the write-side of the same orphaned-lock class), `docs/bugs/build-queue-stale-lock-detection-too-lazy` (the acquire-loop's own age-blind reclaim), `docs/features/build-queue-generalization` (lock lifecycle contract)

## Verified Symptom

`build-queue-await.ps1 -Seq <n>` is the followable-wait primitive an enqueuer blocks on for its own build's `results/<seq>.json`. When a PRIOR build's runner died without writing its result (wrapper tree-kill, final-write crash), `active.lock` is left held by a dead pid and no result for the waiter's seq will ever appear. The await loop only ever checks two things per tick — is the result file present, and has the deadline passed — so it polls the FULL `TimeoutSeconds` window (default multi-minute) before exiting non-zero, even though the blocking condition (a dead-pid lock older than any real build) is observable within the first tick. The caller experiences a long unexplained hang followed by a generic timeout, with no signal that a crashed prior build is the cause.

## Root Cause

**Root cause class:** script-defect (`user/scripts/build-queue-await.ps1`)

The await poll loop had no stale-active-lock escape:

```powershell
while ($true) {
    if (Test-Path -LiteralPath $resultPath) { ...; if ($null -ne $result) { break } }
    if ([DateTime]::UtcNow -ge $deadline) { break }
    Start-Sleep -Milliseconds $PollIntervalMs
}
```

The runner's own crash-resilience (result write + lock release) is the primary safety net; when that net fails (the runner is killed or crashes mid-finalize), the waiter has no independent detection and degrades to a full-timeout hang. `active.lock` already carries `seq`, `build_pid`, and `started_at`, so the waiter has everything it needs to recognize an abandoned lock owned by another build.

## Fix Scope

Add a stale-active-lock check to the await poll loop, evaluated at most once (a latch, `$staleActiveLockDetected`): read `active.lock`, and treat it as stale only when ALL hold — it belongs to a DIFFERENT seq than the waiter's, its `build_pid` is dead (`GetProcessById` throws `ArgumentException`), and its `started_at` age is >= 30 minutes. On detection, break the loop and, when no result is present, emit a diagnostic naming the stale lock and pointing at `/build-queue-status` / manual removal, and `exit 1` (distinct from the existing `124` "not yet present" and `125` "present but unreadable" exits). All reads are wrapped in `Get-SafeValue` so a malformed/racing lock never throws — the check fails safe to "not stale" and the loop continues to its normal deadline. The waiter never removes the lock itself (reclaim remains the acquire-loop's job); it only stops waiting on a provably-abandoned one.

The 30-minute floor plus dead-pid plus other-seq conjunction makes a false positive against a live holder impossible in practice: a real build does not run 30 minutes with a dead pid.
