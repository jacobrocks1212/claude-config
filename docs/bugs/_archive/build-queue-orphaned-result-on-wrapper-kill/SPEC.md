# Build-queue orphans the result when the wrapper is killed mid-build — Investigation Spec

> The queue wrapper writes `results/<seq>.json` and releases `active.lock` only after the detached build it is *tailing* exits. If the foreground wrapper is killed first (Bash 2-min timeout → exit 143, or any crash), the detached build runs to completion but its exit code is never recorded and the lock lingers until stale-reclaim. The caller can never learn the outcome.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-24
**Placement:** docs/bugs/build-queue-orphaned-result-on-wrapper-kill
**Related:** `docs/specs/build-queue/` (feature spec + plans); mitigation commit `5bdd74e` (10-min Bash timeout on the four routing skills); `user/scripts/build-queue-status.ps1` (reads `results/`+`active.lock`); `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` (poll `results/<seq>.json` for the exit code)
**Branch:** `build-queue`

<!-- Status lifecycle:
  - Investigating → root cause not yet proven.
  - Concluded     → root cause proven, affected area + fix scope understood; ready for /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** A queued build whose foreground wrapper is killed before the detached build finishes leaves **no `results/<seq>.json`** — the caller polling for an outcome never sees one. Proven by code path (the only writer of the result file is Step 5, reached only after the tail loop exits normally) and observed live: a sibling session abandoned a queued build and re-ran it in the background because the original produced no recoverable result.
2. **[VERIFIED]** The detached build itself is **not** killed — it keeps running and completes its work. Confirmed earlier this session (build `pid=13656` survived the wrapper's exit-143).
3. **[VERIFIED]** `active.lock` is **not** released by the dying wrapper; the slot is held until the next waiter's stale-reclaim path fires, which only happens after `build_pid` dies *and* 3 consecutive 1s poll ticks observe it dead. So even after the orphaned build finishes, the lock lingers ≥3s into the next waiter's poll. Queue ordering stays correct (no overlap), but the result is unrecoverable.

## Reproduction Steps

1. From any worktree, invoke the queue synchronously (its default mode), e.g. via `/msbuild`, on a build that runs longer than the foreground caller's timeout.
2. While the detached build is still running, kill the foreground wrapper — the Bash tool's default 2-min timeout does this automatically (SIGTERM → exit 143), or send any terminating signal / let it crash.
3. Let the detached build run to completion.

**Expected:** `results/<seq>.json` is written with the build's real `exit_code`, and `active.lock` is released, regardless of whether the wrapper survived.
**Actual:** No `results/<seq>.json` is ever written; `active.lock` lingers until stale-reclaim. The exit code is permanently lost.
**Consistency:** Deterministic whenever the wrapper dies between launching the detached build and the build's completion.

## Evidence Collected

### Source Code

All citations are `user/scripts/build-queue.ps1`.

- **Detached launch (Step 4).** Lines 283-288: the real build is started with `Start-Process … -PassThru` as a **detached** process — its lifetime is independent of the wrapper. `build_pid` (the *detached* pid) is recorded into `active.lock` at lines 292-308.
- **Wrapper blocks tailing the child (lines 317-337).** `while (-not $proc.HasExited) { … Start-Sleep 500ms }` — the wrapper's whole job after launch is to stream the child's log to its own stdout and wait. This loop is what the 2-min foreground timeout interrupts.
- **Result write + lock release happen ONLY after the loop (Step 5).** Lines 360-376: `$exitCode = $proc.ExitCode` (360) → write `results/<seq>.json` (365-370) → `Remove-Item $activeLock` (372) → `exit $exitCode` (376). **If the wrapper dies during the tail loop, none of Step 5 runs.** There is no `finally`/trap that performs the release, and the detached child has no knowledge of the result file or the lock — it just runs the filtered script and exits.
- **Stale-reclaim is the only safety net, and it does not recover the result.** The next waiter's poll loop (lines 180-246) calls `Get-ActiveLockStatus` (158-172), which returns `'dead'` once `build_pid` is no longer alive (170-171). Reclaim requires `staleTicks ≥ staleThreshold` (`$staleThreshold = 3`, line 179) *and* the waiter being the lowest live seq (189-193). This frees the **slot** but never reconstructs the missing `results/<seq>.json`.

### Consumers that depend on the result file

- `user/scripts/build-queue-status.ps1` reads `active.lock` and `results/<seq>.json` to report queue state — an orphaned seq shows as a stale/absent result.
- Post-mitigation, the four routing skills (`repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md`) explicitly instruct background callers to read `results/<seq>.json` (the `exit_code` field) for the outcome — exactly the file that never appears in the orphan path.

### Git History

- Commit `5bdd74e` (this branch) raised the four routing skills' Bash invocation to `timeout: 600000` (10 min) and documented a `run_in_background` + poll-`results/<seq>.json` fallback. This **reduces the frequency** of the orphan path (most builds now finish inside the wrapper's lifetime) but does **not** eliminate it.

## Theories

### Theory 1: Result + release live on the wrong process (the wrapper, not the build) — CONFIRMED
- **Hypothesis:** Because Step 5 (write result, release lock) is owned by the *foreground wrapper* rather than the *detached build*, any wrapper death between launch and completion strands the build with no result and a held lock.
- **Supporting evidence:** Step 5 is unreachable once the tail loop (317-337) is interrupted; the detached child has no code that touches `results/` or `active.lock`; there is no `finally`/trap fallback.
- **Contradicting evidence:** None found.
- **Status:** Confirmed.

## Proven Findings

1. The exit code is captured via `$proc.ExitCode` **inside the wrapper** (line 360) and persisted **by the wrapper** (365-370). Ownership of the outcome is bound to the wrapper's survival.
2. The detached build is durable; only the *reporting* is fragile. The fix must move outcome-recording (and lock release) onto something that shares the build's lifetime, not the wrapper's.
3. The 10-min timeout mitigation is a frequency reducer, not a fix: builds >10 min, a forgotten/over-tight caller timeout, or a wrapper crash all still orphan.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Queue wrapper — launch + result/release | `user/scripts/build-queue.ps1` (283-308 launch, 317-337 tail, 360-376 Step 5) | Result write + lock release bound to wrapper lifetime; lost on wrapper death |
| Stale-reclaim safety net | `user/scripts/build-queue.ps1` (158-172, 179-194) | Frees the slot but cannot reconstruct the missing result |
| Status reporter | `user/scripts/build-queue-status.ps1` | Surfaces orphaned seqs as missing results |
| Routing skills (mitigation + result consumers) | `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` | Poll `results/<seq>.json` — the file that never appears in the orphan path |

## Proposed Fix Direction

Make the **detached child** responsible for recording its own outcome and releasing the slot, so the result survives the wrapper being killed. Sketch (for `/plan-bug` to refine, not yet committed):

- Wrap the filtered script invocation in the detached process so that, on the child's own completion, it writes `results/<seq>.json` (its real exit code) and removes `active.lock` for its `seq` — i.e. ownership of Step 5 moves into the child.
- The foreground wrapper keeps tailing the log for live output and still surfaces the exit code when it survives, but its survival is no longer load-bearing for correctness.
- Guard against double-release / double-write (wrapper *and* child both finishing the happy path): make the result write idempotent and scope the `active.lock` removal to the owning `seq` so a late wrapper cannot delete a successor's lock.

## Open Questions

- Should the child release `active.lock` directly, or only write `results/<seq>.json` and let stale-reclaim free the slot? (Direct release is faster but needs the seq-scoped guard above to avoid removing a successor's lock.)
- How to express the child wrapper portably given the existing `Start-Process … -File <filtered-script>` shape and the spaces-in-path handling already added (`Format-ProcArg`, 271-281) — wrap via an inline `-Command` that invokes the filtered script then records the outcome, vs. a small generated trampoline script.
