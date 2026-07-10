# Bash-Tool Timeout Tree-Kill Reaps the "Detached" Build-Queue Runner Mid-RED-Build Sweep — Investigation Spec

> A foreground `build-queue.ps1` call that hits its Bash-tool timeout is tree-killed (exit 143), and the kill takes the supposedly-detached runner with it. On a RED build the runner is minutes deep in the failed-build quarantine sweep at that moment — past the point of writing `results/<seq>.json` protection, before the result write and lock release — so the queue strands: result lost forever, `active.lock` held by a dead pid, `build-queue-await.ps1` polls to 124 with a "may still be running" message, and no self-heal until the NEXT enqueue's 3-dead-tick reclaim.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-10
**Placement:** docs/bugs/build-queue-timeout-kill-reaps-detached-runner
**Related:** `docs/bugs/build-queue-orphaned-result-on-wrapper-kill` (the runner WAS the fix for wrapper death — this bug shows the safety net dies with the wrapper), `docs/bugs/subagent-backgrounds-verification-ends-turn-before-green` (the §4 background-enqueue contract the lane agent did not follow — contributing factor), `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build` (stale-lock reclaim mechanics), `docs/features/build-queue-generalization` (lock lifecycle contract)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** `build-queue-await.ps1 -Seq 1033` exited 124 ("result not yet present … may still be running") even though the build had completed RED (23 CS1739 errors) — confirmed by operator report + session transcript (`54c72688…/subagents/agent-a67bd41bdf63fe77d.jsonl`, 21:01:09Z) + `logs/1033.build.log` (`Build FAILED … 23 Error(s)`).
2. **[VERIFIED]** `results/1033.json` was never written and `active.lock` stayed held by dead pid 36112 — confirmed by live state-dir inspection (result absent, pid dead) and the operator's own observation in the Cognito session.
3. **[VERIFIED]** The failure reproduced identically on the very next build, seq 1034 (pid 9420): build RED at 17:18:20 EDT, runner died 17:20:39, no `results/1034.json`, lock still held — observed live during this investigation.
4. **[VERIFIED]** Clean builds are unaffected: seqs 1030–1032 (exit 0) all finalized normally (`ended_at` + `exit_code: 0` + `result_fidelity: "verified"`).
5. **[VERIFIED]** With no queued waiter, the stranded lock persists indefinitely (tickets/ empty; lock held >30 min for 1033 until seq 1034's acquire loop reclaimed it after 3 dead ticks).

## Reproduction Steps

Observed repro (exactly what happened twice on 2026-07-10; timestamps EDT):

1. In a Cognito Forms worktree, from a Claude Code Bash tool call **run in the foreground with a finite timeout** (600000 ms), invoke the wrapper:
   `powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op msbuild -Exec "<worktree>/.claude/scripts/build-filtered.ps1" -Project "Cognito.UnitTests/Cognito.UnitTests.csproj"`
   …where the project currently **fails to compile** (RED build).
2. The build itself finishes RED before the timeout (e.g. build log finalized 16:50:22; runner enters its `finally`, emitting the bare `True` to `logs/<seq>.log` at 16:50:28), and the runner begins the RED-only poisoned-artifact sweep over the whole worktree (multi-minute on Cognito).
3. The Bash tool call hits its timeout (16:51:59, "Command timed out after 10m 0s", exit 143) → the harness tree-kill terminates the wrapper AND the runner (pid 36112) mid-sweep.
4. Run `build-queue-await.ps1 -Seq <seq>` (any timeout): it polls `results/<seq>.json`, which will never exist, and exits **124** claiming "the build may still be running".

**Expected:** the queue's outcome contract survives the death of the invoking session/tool call — `results/<seq>.json` reflects the build's true RED outcome and `active.lock` is released (crash-safe release; operator-locked fix expectation), and `await` distinguishes "still building" from "runner dead, result lost".
**Actual:** no result is ever written, the lock is held by a dead pid until the next enqueue burns 3 dead-tick reclaim polls, and `await` returns 124 with a misleading "may still be running" message.
**Consistency:** deterministic given (RED build) ∧ (foreground wrapper call killed after the build ends but before the sweep finishes). Reproduced 2/2 on 2026-07-10 (seqs 1033, 1034). Green builds close the window to ~1s, which is why 1030–1032 were untouched.

## Evidence Collected

### Runtime Evidence (state dir + session transcript — the confirmed kill chain)

Session `54c72688-4561-4eff-acde-efcaf459c54d` (Cognito Forms), lane subagent `agent-a67bd41bdf63fe77d` (a `write-plan-cognito` backend lane agent). All Bash calls **foreground** (`run_in_background` unset):

| Time (EDT) | Event | Source |
|---|---|---|
| 16:41:57 | Wrapper invoked foreground, `timeout=600000` | transcript tool_use |
| 16:42:10 | Runner launched (pid 36112), `1033.err.log` created | state-dir timestamps |
| 16:50:22 | `1033.build.log` finalized: `Build FAILED … 23 Error(s)` (CS1739) | build log |
| 16:50:28 | `logs/1033.log` = 6-byte `True` — the runner entered its `finally` (unassigned `Stop-BuildJobTree` return, `build-queue-runner.ps1:235`) and began the RED-only quarantine sweep | state dir + code |
| **16:51:59** | **`Exit code 143 — Command timed out after 10m 0s`** — tree-kill reaps wrapper + runner mid-sweep | transcript tool_result |
| 16:52:03→17:01:09 | `await -Seq 1033` foreground → **exit 124** after 540 s | transcript |
| 17:10:49 | Seq 1034 wrapper invoked foreground, `timeout=590000` | transcript |
| 17:10:59 | 1034 claims the lock (1033's stale lock reclaimed via 3 dead ticks in 1034's acquire loop) | active.lock |
| 17:18:20 / 17:18:21 | `1034.build.log` RED (39 errors) / `1034.log` = `True` — sweep begins | state dir |
| **17:20:39** | **`Exit code 143 — Command timed out after 9m 50s`** — pid 9420 confirmed alive at 17:20:39 and dead by 17:22:19 (kill lands to the second) | transcript + live pid checks |
| 17:21:00→17:30:04 | `await -Seq 1034` → exit 124 | transcript |

No `TaskStop` calls and no session end near either kill — both deaths align exactly with the per-call timeout instants. Control experiment: a `Start-Process`-spawned child **survives** its parent Bash call completing normally (heartbeat kept ticking ≥22 s past parent exit) — only the **timeout kill path** reaps the detached child. `results/` stream stops at `1032.json`; `1033.json`/`1034.json` absent; `tickets/` empty; `stats/mstest.json` last updated at the 1032 completion.

### Source Code (serving-path traces — all hops cited)

**Trace 1 — missing result + held lock ← runner killed in the unprotected post-build region:**

```
results/<seq>.json absent + active.lock held (surface)
  → runner writes the result ONLY at build-queue-runner.ps1:331-337 (atomic tmp+move)
  → runner releases the lock ONLY at build-queue-runner.ps1:348-366 (seq-guarded Remove-Item)
  → BOTH sit OUTSIDE the try{131}/finally{234-249}; the trap (:126-129) only calls
    Stop-BuildJobTree — it neither writes the result nor releases the lock
  → an OS kill anywhere after build exit (:176-177) and before :331 strands both
  → the wrapper's redundant merge/release (build-queue.ps1:551-603) requires a LIVE wrapper —
    dead here (same tree-kill)
```
Fix site (crash-safe release) is on this path: the ordering/protection of :234-366. **`traced`.**

**Trace 2 — the kill window is minutes-wide only for RED builds ← RED-only quarantine sweep:**

```
runner in a multi-minute pre-result window (surface: 1s for green 1030-1032, minutes for RED 1033/1034)
  → finally block order: Stop-BuildJobTree (:235) → occupancy-gated Reset-CompilerServer (:236-243)
  → $buildFailed gate (:245): ($exitCode -ne 0) → Remove-PoisonedArtifacts sweep (:246-248),
    recursive over <worktree>/**/bin + **/obj — multi-minute on the Cognito tree
  → green builds skip the sweep entirely and reach the :331 result write ~1s after build exit
```
The bare `True` in `logs/<seq>.log` is the unassigned `Get-SafeValue { Stop-BuildJobTree … }` return at `:235` leaking to the runner's stdout — a timestamped marker that both runners died after `:235` and before `:331`. **`traced`.**

**Trace 3 — runner dies with the wrapper ← no kill isolation on the runner launch:**

```
runner (pid 36112 / 9420) dead at the exact tool-timeout instant (surface)
  → wrapper launches the runner via Start-Process -WindowStyle Hidden, build-queue.ps1:474-479 —
    no job breakaway / no scheduler indirection; the runner stays inside whatever process tree
    the Bash tool call owns
  → the harness timeout kill (exit 143) terminates that tree, runner included
  → the runner's own Job Object (New-BuildJobObject, runner :171-174) scopes ONLY the build
    grandchild — the runner itself is not isolated by it
```
Runtime-coupled claim, confirmed by the cited transcript/timestamp evidence above (two independent exact-timestamp alignments + the surviving-child control experiment). **`traced`.**

**Trace 4 — await lies ("may still be running") ← result-only polling:**

```
await exit 124 despite a dead runner (surface)
  → build-queue-await.ps1:76-91 polls ONLY Test-Path results/<seq>.json + parse
  → never reads active.lock, never Test-PidAlive on build_pid (by design: "read-only over the
    queue state", :40-42)
  → deadline path :93-99 emits 124 + "The build may still be running"
```
**`traced`.**

**Trace 5 — no self-heal without a waiter ← reclaim lives only in the acquire loop:**

```
lock held >30 min by a dead pid, tickets/ empty (surface)
  → reclaim decision Test-ShouldReclaimLock (build-queue-hygiene.ps1:1069-1133): lowest-seq live
    waiter + ≥3 consecutive 'dead' observations (staleThreshold=3, build-queue.ps1:282)
  → executed ONLY inside the wrapper's while(-not $won) acquire loop (build-queue.ps1:290-425)
  → no waiter ⇒ nothing ever reads the lock ⇒ stranded until the next enqueue
```
**`traced`.**

### Git History

- `f8cf159` / `f3b221c` — introduced the self-releasing detached runner as the fix for `build-queue-orphaned-result-on-wrapper-kill`, on the implicit assumption the runner survives to its release path. This bug falsifies that assumption for the tool-timeout kill path.
- `00b210a` — the await primitive + §4 background-enqueue contract (`subagent-backgrounds-verification-ends-turn-before-green`). The await exists precisely because wrapper calls die at tool timeouts; the runner sharing that death was not covered.
- `c65d51c` — atomic provisional lock + confirmed-dead-only reclaim (the 3-dead-tick mechanics seen working in 1034's acquire).
- `aa365b4`/`b0dee83` era — the per-project poisoned-DLL quarantine sweep that creates the multi-minute RED-build window.

### Related Documentation

- `build-queue-orphaned-result-on-wrapper-kill/SPEC.md` — closest prior art; documents the wrapper-death strand and the runner-as-fix. This bug is its direct sequel: the safety net itself is killable.
- `build-queue-generalization/SPEC.md` — locks the "self-releasing detached runner" + `results/<seq>.json` schema as invariants; `active.lock` is deleted at release, so the result file is the ONLY durable record — if it is never written, nothing survives.
- `build-queue-eta-priority-lanes/SPEC.md` — documents the wrapper's read-merge-write on `results/<seq>.json` (`build-queue.ps1:560-584`); moot here since neither writer survived.

## Theories

### Theory 1: Bash-tool timeout tree-kill reaps the runner (CONFIRMED — root cause)
- **Hypothesis:** the foreground wrapper call's timeout kill (exit 143) terminates the entire process tree including the `Start-Process`-launched runner; on RED builds the runner is mid-sweep, inside the unprotected pre-result window.
- **Supporting evidence:** two independent exact-timestamp alignments (16:51:59 and 17:20:39) between the transcript's timeout kill and the runner's death window; both stranded runs RED, all green neighbors clean; control experiment shows normal parent exit does NOT kill the child.
- **Contradicting evidence:** none.
- **Status:** Confirmed.

### Theory 2: Runner hangs or crashes in the sweep/hygiene (RULED OUT)
- The runner was alive and progressing until exactly the timeout instant (1034: alive at 17:20:39.0, killed at 17:20:39.890); a self-crash would not align to the caller's timeout twice; the trap (`:126-129`, `continue`) suppresses terminating errors and both the result write AND lock release were skipped — only process death explains both.
- **Status:** Ruled Out.

### Theory 3: TaskStop / session teardown killed the runner (RULED OUT)
- No `TaskStop` tool calls in the session; the session continued past both kills (last record 21:30:56Z); kills align with per-call timeouts, not session end.
- **Status:** Ruled Out.

## Proven Findings

1. **Root cause (composite, all links traced):** foreground-wrapper timeout tree-kill (Trace 3) × unprotected post-build critical section in the runner (Trace 1) × RED-only multi-minute quarantine sweep widening the window (Trace 2), with the blast radius amplified by result-only await polling (Trace 4) and waiter-only reclaim (Trace 5).
2. **Contributing factor:** the lane agent ran the wrapper **foreground** with a finite timeout instead of the §4 background-enqueue contract (`run_in_background` enqueue + `build-queue-await.ps1`). A backgrounded enqueue that completes normally leaves the runner alive (control experiment) — following the contract avoids the kill for the enqueue call, but any foreground-timeout path (including a foreground await that a future agent replaces with a wrapper re-run) re-opens it.
3. **Constraint for the fix:** exit-143-style termination is an unconditional process kill — the dying runner cannot trap it. Crash-safe release therefore cannot rely on the runner's own exit handlers alone; it requires shrinking the unprotected window (e.g. write the RED result IMMEDIATELY after the exit code is known, BEFORE hygiene/sweep, then finalize), and/or kill isolation at launch, and/or reclaim+result-reconstruction that does not require a live waiter. Fix scope decision (operator-locked): **crash-safe release** — the result must be written and the lock released (or reclaimable with a truthful result) even when the runner dies abnormally.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Runner post-build lifecycle | `user/scripts/build-queue-runner.ps1:234-368` | Result write + lock release unprotected; RED-sweep widens the kill window from ~1s to minutes |
| Wrapper runner launch | `user/scripts/build-queue.ps1:474-499` | No kill isolation; `build_pid` (the runner) dies with the invoking tool call's tree-kill |
| Await primitive | `user/scripts/build-queue-await.ps1:76-99` | Cannot distinguish "still building" from "runner dead, result lost"; misleading 124 message |
| Stale-lock reclaim | `user/scripts/build-queue.ps1:282,290-425`; `build-queue-hygiene.ps1:1069-1133` | Waiter-only; no waiter ⇒ indefinite strand; reclaim frees the slot but never reconstructs the lost result |
| Cognito build skills §4 contract | `/msbuild`, `/mstest`, `/nxbuild`, `/nxtest` skill prose | Foreground wrapper invocation with finite timeout is the exposure path; contract adherence is prose-only |

## Open Questions

- Should the fix also record the **build grandchild's PID** (never persisted today; `build_pid` is the runner) so a future watchdog/status can reason about the build itself?
- The queue-entry severity for this bug follows the family convention (`severity: null` deprioritized lane — Windows/Pester-only, untestable off the workstation); real severity is this SPEC's P1. Restore priority by removing the queue entry if it should jump the feature queue.
