# Bug: a crash during the runner's final result write orphans active.lock with no result

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-22
**Fixed:** 2026-07-22
**Fix commit:** ed7dbea8
**Placement:** docs/bugs/build-queue-final-write-crash-orphans-lock
**Related:** `docs/bugs/build-queue-timeout-kill-reaps-detached-runner` (wrapper-kill variant of the same orphaned-lock class), `docs/bugs/build-queue-await-hangs-on-stale-lock` (the waiter that hangs on the orphaned lock this bug produces), `docs/bugs/build-queue-orphaned-result-on-wrapper-kill` (prior art), `docs/features/build-queue-generalization` (lock lifecycle contract)

## Verified Symptom

`build-queue-runner.ps1` finishes a build and performs a FINAL result write that flips the early `pending` record to `complete` with the real hygiene fields, then the acquire loop releases `active.lock`. If ANY step of that final write throws — results-dir creation racing/failing, `ConvertTo-Json` on an unexpected object, `File.WriteAllText`/`File.Replace` I/O — the runner aborts before a usable `results/<seq>.json` exists, and `active.lock` is left held. Waiters then poll to timeout (see the companion await bug) and the slot is not freed until the NEXT enqueue's dead-pid reclaim. The early-write safety net reduces but does not close this: the final write is a second, independent failure point after the early record.

A separate but co-located fragility on the runner's OUTPUT path: the build-log read used `System.IO.File.ReadAllText` (opens with `FileShare.Read`), which hits a sharing violation against the still-open redirected-stdout handle of the child build process — so classification could intermittently miss the log, and the read-retry ceiling (`Read-WithRetry -MaxAttempts 15`, ~1.5s) was too short for a slow Nx/rspack daemon's delayed final flush.

## Root Cause

**Root cause class:** script-defect (`user/scripts/build-queue-runner.ps1`, `user/scripts/build-queue-hygiene.ps1`)

The final-write block was inlined without wrapping the whole write in error handling — the deliberate INLINE choice (surviving a failed hygiene dot-source) protected against a *missing module*, not against the write itself throwing. Results-dir creation was a bare `New-Item` inside a `Get-SafeValue` with no retry. On the read path, `ReadAllText`'s default share mode is incompatible with an open writer, and the retry window was tuned for fast dotnet builds only.

## Fix Scope

1. **Crash-proof the final write** (`build-queue-runner.ps1`): serialize the result body under `Get-SafeValue`; wrap the temp-write + atomic `File.Replace` (with direct-write fallback) in a `$finalWriteSucceeded` guard; and on failure, a fallback ALWAYS writes at least a minimal result — preferring the existing early-write record if present, otherwise a fresh `{ seq, exit_code, ended_at }` — via its own temp+replace/direct-write path. A crash in the final write can no longer leave the runner without a result, so `active.lock` is not stranded.
2. **`Ensure-ResultsDirectory` helper** (`build-queue-hygiene.ps1`): retry-with-backoff (5 attempts x 50ms) results-dir creation, fail-open (returns `$true` best-effort, never throws), with a final concurrent-creation re-check. The runner calls it before the final write, replacing the bare inline `New-Item`.
3. **Share-tolerant build-log reads + widened window** (`build-queue-runner.ps1`, companion output-path robustness shipped in the same commit): open the build log with `FileShare.ReadWrite` via `File.Open` + `StreamReader` (matching the existing test-log read pattern) instead of `ReadAllText`, so the still-open child-stdout handle no longer causes a sharing violation; and widen the extended-window read retry from 15 to 50 attempts (100ms each, ~5s ceiling) to absorb a slow Nx/rspack daemon's delayed flush. Fast dotnet builds settle on the first attempts and are unaffected by the raised ceiling. This is a raised retry ceiling (more attempts) and a broadened share mode (more tolerant reads) — strictly more robust, not a weakened gate.
