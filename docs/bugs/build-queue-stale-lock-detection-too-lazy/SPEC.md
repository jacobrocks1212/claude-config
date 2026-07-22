# Bug: build-queue stale-lock reclaim is age-blind — an abandoned lock waits 3 dead ticks

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-22
**Placement:** docs/bugs/build-queue-stale-lock-detection-too-lazy
**Related:** `docs/bugs/build-queue-timeout-kill-reaps-detached-runner` (the crashed-runner state that leaves a dead-pid lock the acquire loop must reclaim), `docs/bugs/build-queue-await-hangs-on-stale-lock` + `docs/bugs/build-queue-final-write-crash-orphans-lock` (companions in the orphaned-lock class), `docs/features/build-queue-generalization` (lock lifecycle contract)

## Verified Symptom

When a runner dies leaving `active.lock` held by a dead pid, the next waiter's acquire loop (`build-queue.ps1`) must reclaim the lock before it can run. Reclaim is gated on `Test-ShouldReclaimLock` (hygiene module present, the production path) or an inline fallback counter (module absent) — BOTH require `$staleThreshold` (3) CONSECUTIVE `'dead'` observations before removing the lock. Classification (`Get-ActiveLockStatusFromText` / the inline `Get-ActiveLockStatusOnce`) keys purely on pid liveness; neither the classifier nor the reclaim decision considers the lock's `started_at` age. So a lock that is provably abandoned — dead holder pid AND older than any real build's lifetime — still waits for three poll cycles instead of being reclaimed on first observation.

## Root Cause

**Root cause class:** script-defect (`user/scripts/build-queue-hygiene.ps1` `Test-ShouldReclaimLock`; `user/scripts/build-queue.ps1` poll loop + inline fallback)

Reclaim policy was expressed only as "N consecutive dead ticks," with no age input threaded to the decision. `active.lock` already carries `started_at`, but neither the pure `Test-ShouldReclaimLock` nor the inline fallback branch consumed it.

**Note on the initial in-tree attempt:** an earlier WIP added a 30-minute age check INSIDE the inline `Get-ActiveLockStatusOnce` classifier, but every dead-pid branch there returned `'dead'` either way — so the added check was a semantic no-op on the classification, and (because it lived in the classifier, not the reclaim decision) it could not shorten the 3-tick wait regardless. It also only touched the inline fallback, leaving the production (hygiene-present) reclaim path age-blind. The fix below supersedes that attempt by threading age into the reclaim DECISION on both paths.

## Fix Scope

1. **`Test-ShouldReclaimLock` becomes age-aware** (`build-queue-hygiene.ps1`): two optional params — `[double]$LockAgeMinutes = -1`, `[double]$MaxAgeMinutes = 30`. Reclaim returns `$true` when `IsLowestSeq` AND EITHER the existing consecutive-dead run >= `StaleThreshold`, OR the lock is age-stale (`LockAgeMinutes >= MaxAgeMinutes` AND the trailing observation is `'dead'`). The trailing-dead requirement guarantees a lock never observed dead is never reclaimed on age alone. `LockAgeMinutes < 0` ("age unknown") disables the age path — so existing callers that pass no age keep the exact prior behavior (existing tests unchanged).
2. **Poll loop threads the age** (`build-queue.ps1`): a new `Get-ActiveLockAgeMinutes` helper parses `active.lock`'s `started_at` (timezone-normalized to UTC, returns -1 on absent/unreadable/unparseable). The loop passes it to `Test-ShouldReclaimLock`, and the inline fallback branch mirrors the same age fast-path (`status -eq 'dead' -and lockAge -ge 30`). The no-op age block is removed from `Get-ActiveLockStatusOnce`, which is once again a pure pid-liveness classifier.
3. **Regression tests** (`build-queue-hygiene.Tests.ps1`): age-stale reclaims on first dead below threshold; no reclaim when trailing is non-dead; no reclaim below the age threshold; no reclaim when age is unknown (default); no reclaim when not lowest seq.

This makes reclaim MORE responsive (an abandoned lock frees on the first dead tick instead of the third) while never reclaiming a live holder — the age path still requires a dead observation and lowest-seq gating. It raises responsiveness; it does not weaken any guard.
