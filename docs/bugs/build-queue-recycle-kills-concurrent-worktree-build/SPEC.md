# Build queue's machine-wide VBCSCompiler recycle can kill a concurrent worktree's build — Investigation Spec

> The crash-hygiene fix recycles VBCSCompiler machine-wide after **every** build, on the stated invariant that "the queue serializes builds, so no concurrent build's compiler server is ever killed." That invariant is violable in two ways — the stale-lock reclaim can admit a second concurrent build on a transiently-unreadable `active.lock`, and off-queue **bypass** builds run invisibly to serialization — so a build finishing in worktree A can `Stop-Process -Force` the VBCSCompiler that worktree B's build is actively using, producing MSB4166 / a partial compile / a `Build FAILED`-but-exit-0 → a stale or never-updated test DLL in worktree B.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-02
**Placement:** docs/bugs/build-queue-recycle-kills-concurrent-worktree-build
**Related:** `docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/` (introduced the machine-wide recycle + asserted the serialization-safety invariant this spec shows is violable), `docs/bugs/build-queue-copy-lock-stale-dll-false-success/` (the `build_fidelity: log-failure-override` stale-DLL path this can trigger), `docs/bugs/test-filtered-stale-check-hardcodes-bin-debug/` (false-positive exit-4 that compounds recovery), `docs/bugs/_archive/build-queue-enforce-cd-prefix-bypass/` (the enforcement escape whose fix left the *inverse* bypass-ergonomics gap in §Secondary), `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/`, `user/scripts/build-queue.ps1`, `user/scripts/build-queue-runner.ps1`, `user/scripts/build-queue-hygiene.ps1`, `user/hooks/build-queue-enforce.sh`

<!-- Status lifecycle: Investigating → active; Concluded → root cause proven, ready for /plan-bug.
     Marked Concluded: the DEFECT (a machine-wide recycle whose safety depends on an invariant the
     queue does not actually guarantee) is proven from source. Whether the specific 2026-07-02
     stale-DLL episode was this vector vs. an intra-worktree copy-lock is Theory 1 (Likely, not
     directly reproduced) — but the defect exists regardless of which vector caused that one episode. -->

---

## Verified Symptoms

<!-- Symptoms 1-3 confirmed via the user's screenshots + first-hand report this session. -->

1. **[VERIFIED]** A build in one worktree reported success (`/msbuild` seq 536, `exit_code=0`) but the test DLL was **never updated** (still dated 07-01), and `/mstest` bounced on a stale DLL. *(User screenshots #1–#2.)*
2. **[VERIFIED]** A **separate agent in a different git worktree was running the same `build-filtered.ps1` (via `/msbuild` + `/mstest`) at the same time** as the affected session. *(User first-hand report this session — the trigger for this investigation.)*
3. **[VERIFIED]** The affected session then tried to bypass the queue (`cd "…\Cognito Forms" && BUILD_QUEUE_BYPASS=1 powershell … build-filtered.ps1 …`) and was **denied** by `build-queue-enforce.sh`, because the bypass token is leading-anchored and the `cd …&&` prefix defeats it — costing a wasted turn before the agent led with the token. *(User screenshot #3.)* See §Secondary defect.
4. **[REPORTED]** The friction recurs: session-mining (see Evidence) found the build→stale-DLL→rebuild→re-run loop in **4 / 28 sessions that ran both `/msbuild` and `/mstest` (~14%)**, ~300K+ output tokens of aggregate churn. Those 4 were single-worktree variants (copy-lock, `--no-restore` no-op, false-positive exit-4); none *isolated* a cross-worktree recycle-kill, so symptom #2's causation is Theory 1 (Likely), not a reproduced log.

## Reproduction Steps

**Vector A — reclaim admits a concurrent build:**
1. Worktree A holds `active.lock`; a reader in worktree B opens it (`FileShare.ReadWrite`) during the sub-second window when the provisional lock is a raw, non-atomic `Write`/`Flush` → reads a truncated/empty lock → `Get-ActiveLockStatus` returns `'unknown'`.
2. Three consecutive `'unknown'`/`'dead'` ticks (`staleThreshold = 3`) and B being lowest live seq → B deletes `active.lock` and claims the slot. **Two builds now run simultaneously.**
3. Whichever build finishes first runs the machine-wide recycle → `Stop-Process -Force VBCSCompiler` → the other build's live compile loses its compiler server.

**Vector B — off-queue bypass build (the realistic common case):**
1. Worktree B runs a build **off-queue** — `BUILD_QUEUE_BYPASS=1 …`, or any build the enforcement hook doesn't catch — so the queue's `active.lock` never knows about it.
2. Worktree A runs a normal queued `/msbuild`; on completion its runner recycles VBCSCompiler machine-wide.
3. B's in-flight compile is force-killed mid-build.

**Expected:** A build in one worktree never disturbs a concurrent build in another (the queue's whole premise).
**Actual:** The machine-wide recycle tears down a concurrent build's compiler → MSB4166 "child node exited prematurely" / partial compile / `Build FAILED`-but-exit-0 → stale/never-updated DLL, recorded as a clean pass.
**Consistency:** Conditional — requires two overlapping builds (via Vector A's narrow race or Vector B's off-queue build). Deterministic once overlap occurs.

## Evidence Collected

### Source Code
- **The recycle is machine-wide and fires after every build.** `build-queue-hygiene.ps1` `Reset-CompilerServer`: `dotnet build-server shutdown` (shuts down *all* build servers for the user, ~:380) and the fallback `Get-Process -Name 'VBCSCompiler' | Stop-Process -Force` (kills *every* VBCSCompiler on the machine, ~:389-390). Neither is scoped to a worktree or pid. Invoked at `build-queue-runner.ps1:148` (every build's `finally`) and again in the wrapper at `build-queue.ps1:399`.
- **The safety invariant is stated in the code itself.** `build-queue-hygiene.ps1` (~:356-368): the recycle is "safe ONLY because the build queue serializes builds machine-wide — by the time a build finishes, no other queued build's compiler server can be mid-use." This spec shows that premise is not actually guaranteed.
- **Serialization hole (Vector A).** `build-queue.ps1`: state is machine-global under `$HOME/.claude/state/build-queue` with a single `active.lock` (~:64-70). Stale-lock reclaim (~:184-198) deletes the lock after 3 `'unknown'`/`'dead'` ticks; `'unknown'` is returned whenever the lock fails to parse (`data`/`build_pid` null, ~:168-173). The provisional lock is written with a raw `Write`/`Flush` into the `CreateNew` stream (~:219-221) — **not** the atomic `File.Replace` used for the final lock (~:313) — and readers open `FileShare.ReadWrite` (~:164-166), so a reader in the sub-second window can read a truncated lock → `'unknown'`. `Test-PidAlive` is conservative (fails safe to *alive*, ~:51-62), so the realistic hole is the unreadable-lock reclaim, not pid misjudgment.
- **Off-queue builds are invisible (Vector B).** The queue only knows about builds routed through it; `BUILD_QUEUE_BYPASS=1` and any enforcement miss run with no `active.lock` entry.
- **Cross-worktree locker-reap blind spot (compounds).** `build-queue-hygiene.ps1` `Stop-DllLockers` reaps DLL lockers only within `<WorktreeRoot>/**/bin/Debug` (~:566-575) — it cannot see a locker held by a *sibling* worktree's concurrent build.
- **Output is per-worktree — the shared-output clobber theory is RULED OUT.** `build-filtered.ps1:13,22` resolves the build target from the current worktree; no `OutputPath`/`OutDir`/`Directory.Build.props` override exists (grep/glob returned none). `bin\Cognito.Services\` is a per-worktree content subfolder, not a shared output root. So a concurrent worktree does **not** overwrite another's DLL via a shared path — the damage is via the shared *compiler process*, not shared *files*.
- **`--no-restore` is the default but is NOT the general cause.** `build-filtered.ps1:24-26` appends `--no-restore` unless `-Restore` is passed. This skips NuGet restore only; it has no effect on incremental compilation or the DLL copy step. (One narrow real defect: after a wiped `obj/`, `--no-restore` has no `project.assets.json` → the build silently no-ops. Tracked as a separate candidate — see Open Questions.)

### Runtime / Session Evidence
- `/mine-sessions` over 360 Cognito Forms sessions (canonical + worktree siblings): the stale-DLL loop in **4/28** both-build+test sessions (~14%), concentrated in the `-C` hardening worktree, ~50–105K output tokens per episode. Five sub-variants observed: (1) `--no-restore` obj-wipe no-op, (2) copy-lock false-success, (3) mixed-assembly/custom-output staleness, (4) copy-lock via stray `dotnet.exe`, (5) staleness-heuristic path mismatch (exit-4 false positive). Highest-signal: `abb3e30c` (#197–235, #649–740), `6e4c639c` (#32–235, WARN+exit-4 at #143), `c4b138d4`, `a3f31c70`.
- The affected session's **empty `536.log` was a diagnostic red herring** — for build ops the real transcript goes to `<seq>.build.log` (`build-queue-runner.ps1` ~:104-106); the agent burned turns reading the empty `<seq>.log`. Skills/docs don't state this.

### Related Documentation
- `build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md` — introduced the machine-wide recycle; its Locked Decision 1 ("force-recycle every build … safe because the queue already serializes") is the invariant this spec falsifies.
- Root `CLAUDE.md` Hooks table + `user/scripts/CLAUDE.md` — build-queue serializer and hygiene contract.

## Theories

### Theory 1: Cross-worktree recycle-kill caused the 2026-07-02 stale DLL
- **Hypothesis:** The concurrent sibling-worktree build (symptom #2) and the affected build overlapped; one's machine-wide VBCSCompiler recycle killed the other's compile → partial/failed compile recorded as success → stale DLL.
- **Supporting evidence:** Concurrent worktree build confirmed by the user; recycle is machine-wide + fires every build (source-confirmed); overlap is reachable via Vector A or B (source-confirmed).
- **Contradicting evidence:** Mining did not isolate a cross-worktree recycle-kill event; the same stale-DLL symptom is independently produced by intra-worktree copy-lock (a different, already-filed defect).
- **Status:** **Likely** (not directly reproduced).

### Theory 2: The recycle's safety invariant is violable (the defect itself)
- **Hypothesis:** `Reset-CompilerServer` being machine-wide is only safe under perfect serialization, which the queue does not guarantee (Vector A reclaim race + Vector B off-queue builds).
- **Supporting evidence:** All source-confirmed above (recycle scope, reclaim on unreadable lock, off-queue invisibility).
- **Contradicting evidence:** None.
- **Status:** **Confirmed.**

## Proven Findings
- The machine-wide VBCSCompiler recycle after every build is **unsafe under any concurrency**, and the queue does **not** guarantee the serialization it assumes: a transiently-unreadable `active.lock` can trip the stale-lock reclaim into admitting a second build, and off-queue bypass builds are entirely invisible to the lock.
- Cross-worktree DLL clobber via a *shared output path* is **ruled out** (output is per-worktree); the cross-worktree damage channel is the **shared compiler process**, not shared files.
- Flipping the `--no-restore` default would **not** fix this and is not recommended; the only restore-related defect is the narrow obj-wipe no-op.

## Secondary defect (coupled — bypass ergonomics)
The fix for `build-queue-enforce-cd-prefix-bypass` made the **deny** unanchored (a build is caught anywhere in the command) but left the **bypass** token leading-anchored: `_BYPASS_RE` (`build-queue-enforce.sh:76`) matches only an optional `NAME=value` prefix before `BUILD_QUEUE_BYPASS=1`, not a `cd "…" &&` prefix. Result: a legitimate, user-authorized `cd … && BUILD_QUEUE_BYPASS=1 …` is now **denied** (symptom #3), and the deny message ("Emergency one-off: BUILD_QUEUE_BYPASS=1 …") gives no hint the token must be first. This is the *inverse* of the cd-prefix-bypass spec (which closed a build *escaping*); it is uncovered there. It matters here because bypass builds are Vector B — so the durable answer is to make the queue safe under concurrency rather than to make bypassing (which *removes* the safety) easier.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Compiler-server recycle | `user/scripts/build-queue-hygiene.ps1` (`Reset-CompilerServer` ~:378-395) | Machine-wide `Stop-Process -Force VBCSCompiler` / `build-server shutdown` — must not kill a concurrent build's server |
| Queue lock / reclaim | `user/scripts/build-queue.ps1` (~:164-198, :219-221, :313) | Non-atomic provisional lock write + reclaim on unreadable lock → can admit a 2nd concurrent build |
| Runner recycle callsite | `user/scripts/build-queue-runner.ps1` (~:148) | Fires the recycle every build |
| Enforcement / bypass hook | `user/hooks/build-queue-enforce.sh` (:76 bypass anchor) | Bypass builds run off-queue (Vector B); legit `cd …&&`-prefixed bypass denied (secondary) |
| Build diagnostics | `repos/cognito-forms/.claude/skills/{msbuild,mstest}/SKILL.md` | Point at `<seq>.build.log`, not the empty `<seq>.log` |

## Open Questions
- **Fix direction for the recycle (defer to `/plan-bug`):** (a) make the recycle no-op when any other build is active/known, (b) atomic provisional lock write so the reclaim can't misfire on an unreadable lock (closes Vector A), (c) scope the recycle to the build's own descendant tree (Job Object) instead of by process name, or (d) some combination. Options must also account for Vector B (off-queue builds the lock can't see).
- Should the `--no-restore` obj-wipe silent no-op (auto-restore when `project.assets.json` is missing) be its own small bug dir, or folded into a build-skill robustness fix?
- Should the bypass-ergonomics secondary be a follow-up phase on `build-queue-enforce-cd-prefix-bypass` (same hook, same regex family) rather than a phase here?
- Can Vector A be reproduced deterministically (e.g. inject a truncated `active.lock` read) for a regression test, or is it too timing-dependent to guard directly — leaving the atomic-write fix as the only assertable guard?
