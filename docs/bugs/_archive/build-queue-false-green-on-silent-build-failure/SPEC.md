# Build Queue Reports False-Green on a Silently-Broken Build — Investigation Spec

> The build queue reports `RESULT=PASS` for a backend build that never compiled — a per-project 0-byte DLL evades the quarantine sweep and an exit-0 empty-log build has no output-fidelity gate — eroding agent trust to the point of `BUILD_QUEUE_BYPASS=1` + manual process kills.

**Status:** Fixed
**Severity:** P0
**Discovered:** 2026-07-03
**Fixed:** 2026-07-13
**Fix commit:** 544c41e
**Placement:** docs/bugs/build-queue-false-green-on-silent-build-failure
**Related:** docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash (origin of `Remove-PoisonedArtifacts` + `result_fidelity`), docs/bugs/build-queue-copy-lock-stale-dll-false-success (origin of `build_fidelity` + `Test-BuildLogFailure`), docs/bugs/build-queue-outcome-opacity-and-inspect-deny (just-completed banner/inspect-deny fix — adjacent, non-overlapping)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- Symptoms 1-4 confirmed via the user's own build-failure writeup (image, symptom 1),
     the last-2h session-log scan (symptoms 2-4), and source-code root-cause reads. -->

1. **[VERIFIED]** A **0-byte `Cognito/bin/Debug/netstandard2.0/Cognito.dll`** was accepted as "success with no compilation." `Cognito.Core` references that assembly, so an empty DLL made every type from the `Cognito` project vanish → **6,805 phantom CS0246 errors on committed code**. Deleting `Cognito/obj`+`bin` and rebuilding produced a real 2.8 MB DLL and everything compiled. This is *exactly* the truncated-DLL quarantine case the build-queue hygiene is meant to catch — **it slipped through.** — confirmed by the user's build-failure writeup.

2. **[VERIFIED]** Backend **build ops report `exit 0` with 0-byte logs and no output**, and are recorded as a clean pass. Session `ef43777c` L465: *"Cognito.Core.dll is from 13:38 but my edits are 14:56 — none of my changes have actually compiled. Every queued build since ~13:38 reports exit 0 but produces 0-byte logs and no output. The build queue itself is broken."* Session `81e40be6` L252/L400: *"build reports success but produces no output and empty logs"*, *"71-byte log, no results."* — confirmed by session-log scan.

3. **[VERIFIED]** **Test-op log capture drops per-test lines / has a flush lag**, so an agent cannot read the pass/fail detail from `logs/<seq>.log` and bypasses the capture. Session `79ed5a88` L236: *"the log capture has a flush lag"*; L882: *"the queue's log capture drops the per-test lines for test ops. Let me bypass the capture race and run the filtered script directly."* — confirmed by session-log scan.

4. **[VERIFIED]** **Trust-erosion fallout:** because the queue lies about outcomes, agents abandon it — `BUILD_QUEUE_BYPASS=1 dotnet build` (session `ef43777c` L435/L438) and manual `Get-Process dotnet,testhost,VBCSCompiler,MSBuild | Stop-Process -Force` (session `81e40be6` L651). This defeats the queue's serialization guarantee (machine-load protection) and its process-hygiene ownership. — confirmed by session-log scan.

## Reproduction Steps

1. In a Cognito worktree, trigger a build that leaves a poisoned artifact under a **project subdir** — e.g. a crashed/killed/copy-raced build that writes a 0-byte `Cognito/bin/Debug/netstandard2.0/Cognito.dll` (NOT the worktree-root `bin/`).
2. Run `/msbuild` (or `/mstest --no-build`) again via the build queue.
3. **Observed:** `Remove-PoisonedArtifacts` sweeps only `<WorktreeRoot>/bin` + `<WorktreeRoot>/obj`, never the project subdir, so the poisoned DLL survives. MSBuild's timestamp up-to-date check treats it as current → does not recompile → the downstream referencing project (`Cognito.Core`) fails with CS0246, OR the build exits 0 with an empty log and the queue records `build_fidelity: verified` (a clean PASS). The banner prints `RESULT=PASS`.

**Expected:** the queue detects the poisoned/no-output build, quarantines the per-project artifact, and reports a non-`verified` fidelity (a FAIL or an explicit `no-output` / `no-artifact` signal) so the agent rebuilds instead of trusting a green.
**Actual:** the queue reports `RESULT=PASS` / `build_fidelity: verified` for a build that produced nothing.
**Consistency:** conditional — fires whenever a poisoned per-project artifact exists or a build exits 0 with no captured output; not every build. Manual workaround: delete `obj`+`bin` and rebuild.

## Evidence Collected

### Source Code

**Root cause A — quarantine sweep scope (per-project bin/obj never swept):**
- `user/scripts/build-queue-hygiene.ps1:620-625` — `Remove-PoisonedArtifacts` builds its roots as exactly `Join-Path $WorktreeRoot 'bin'` and `Join-Path $WorktreeRoot 'obj'`, then `Get-ChildItem -Recurse` *inside those two dirs only* (`:632`).
- `user/scripts/build-queue-runner.ps1:163` — invoked as `Remove-PoisonedArtifacts -WorktreeRoot $Worktree` (`$Worktree` = worktree root).
- A Cognito solution keeps each project in its own subdir (`Cognito/`, `Cognito.Core/`, `Cognito.UnitTests/`, …), each with `<Project>/bin` + `<Project>/obj`. `<worktree>/Cognito/bin/Debug/netstandard2.0/Cognito.dll` is **not** under `<WorktreeRoot>/bin|obj`, so the recursive sweep never reaches it.
- **Convergence target:** `Get-DllLockers`'s own doc comment (`build-queue-hygiene.ps1:917-918`) claims it scopes to `<WorktreeRoot>/**/bin/Debug` "mirroring how Remove-PoisonedArtifacts scopes its sweep" — but the implemented quarantine does NOT do that `**/bin` recursion. The correct per-project sweep pattern the quarantine should adopt may already exist in `Get-DllLockers` (verify during fix).

**Root cause B — no build-output fidelity gate (exit-0 empty-log build = clean PASS):**
- `user/scripts/build-queue-runner.ps1:137-153` — for a build op, `build_fidelity` is set ONLY via the negative `Test-BuildLogFailure` log-signature scan: lines 146-149 override exit-0→failure on a matched signature (`log-failure-override`); the `else` at `:150-152` labels **everything else `verified`**.
- `build-queue-runner.ps1:139` — the log guard tests `[string]::IsNullOrWhiteSpace($buildLogPath) -or -not (Test-Path $buildLogPath)` — path-string + existence only, **never file size**. A 0-byte log passes, is read as `""`, and `Test-BuildLogFailure` fails-open to `failed=false` (`build-queue-hygiene.ps1:1148/1151-1153/1186`) → `build_fidelity: verified`.
- `Remove-PoisonedArtifacts` runs only when `$buildFailed` is already true (`build-queue-runner.ps1:161-164`) — it is a cleanup, never an output-produced gate, and never runs on an exit-0 "clean" build.
- **Contrast (test ops have this safeguard, build ops don't):** `build-queue-runner.ps1:167-172` maps test-op exit 3→`result_fidelity: no-output` and exit 5→`no-tests-matched`; for any build op `result_fidelity` is `n/a`. `build_fidelity`'s domain is only `log-failure-override | verified | n/a` (schema `:30`) — **no `no-output` / positive-artifact-produced branch for build ops.**

**Root cause C — test-op log-capture flush race (single-shot read, no barrier):**
- Test ops inherit the runner's stdout handle (no per-process redirect — `build-queue-runner.ps1:106-116` gates `RedirectStandardOutput` behind `if ($isBuildOp)`); that handle is the wrapper's `-RedirectStandardOutput $logPath` (`build-queue.ps1:343-348`).
- The runner parses that same log with a single-shot `[System.IO.File]::ReadAllText` (`build-queue-runner.ps1:183`) and regex-scans for the last `Results:` line (`:184-191`) — but the write handle is owned by the wrapper and not closed until the runner exits (`:248`). The read can miss trailing lines (incl. `Results:`), yielding `counts=$null`.
- **Asymmetry = the fix pattern:** the counts read (`:179-192`) and build-log read (`:138-144`) are single-shot with NO retry, while the sibling `active.lock` read already retries 3×/50ms (`build-queue-runner.ps1:234-241`, mirrored `build-queue.ps1:462-469`). Converge the fidelity-bearing reads onto that existing retry/settle pattern.

### Runtime Evidence

Last-2h session scan (`user/skills/mine-sessions/scripts/scan_build_queue_friction.py`) over Cognito worktrees B/C/D, 10 sessions (14:19–16:05, 2026-07-03):
- **12 hook-denys** in-window (10 `mixed-inspect-ref`, 1 `readonly-inspect`, 1 `real-build`) — includes read-only `cat results/<seq>.json` denies (adjacent to the just-fixed inspect-deny bug) and real bypass builds.
- **13 outcome-confusion hits** in-window — the L465/L252/L400/L236/L882 citations above.
- Bypass + manual-kill triggers: `ef43777c` L435/L438, `81e40be6` L412/L415/L651.
- Full findings: `scratchpad/bq-friction.json` (62 denys / 345 confusions all-time; 12 / 13 in-window).

### Git History

Recent claude-config commits are the just-completed `build-queue-outcome-opacity-and-inspect-deny` fix (banner + inspect-deny re-anchor + `no-tests-matched`). That bug is **adjacent but non-overlapping**: it made outcomes *legible* (banner) and stopped denying read-only inspection; it did NOT add per-project quarantine or build-output fidelity. The `build-queue-enforce.sh` hook is currently **temporarily disabled** (uncommitted `exit 0` block) at the user's request while other agents run — to be re-enabled only after THIS bug is fixed (user decision, 2026-07-03).

### Related Documentation

- `build-queue-no-artifact-or-process-hygiene-on-crash` (Concluded) — birthplace of `Remove-PoisonedArtifacts` + the `<WorktreeRoot>/bin|obj` sweep scope + `result_fidelity`. Its Locked Decision 3 required sweeping *both* bin/ and obj/ — but only at the worktree root. **This bug extends that decision to per-project subdirs.**
- `build-queue-copy-lock-stale-dll-false-success` (Concluded) — birthplace of `build_fidelity` + `Test-BuildLogFailure` (log-text override) + the exit-4 `Test-StaleTestDll` guard. Confirms `build_fidelity` is a log-text parse, not an output-produced check.
- `build-queue-outcome-opacity-and-inspect-deny` (Concluded, just completed) — banner + inspect-deny re-anchor + `no-tests-matched`. Adjacent; the new banner is the natural surface for the new fidelity values this bug adds.
- Neither these nor `docs/bugs/_archive/` cover (a) per-project quarantine sweep or (b) build-op output fidelity. Confirmed new territory.

## Theories

### Theory 1: Quarantine sweep is worktree-root-scoped, blind to per-project artifacts
- **Hypothesis:** `Remove-PoisonedArtifacts` only walks `<WorktreeRoot>/bin|obj`; multi-project solutions keep poisoned artifacts under `<Project>/bin|obj`, so they survive and poison the incremental build.
- **Supporting evidence:** `build-queue-hygiene.ps1:620-625/632`; user's 0-byte `Cognito/bin/...` artifact; `Get-DllLockers` docstring claims a `**/bin` recursion the sweep lacks.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

### Theory 2: No positive build-output fidelity — exit-0 empty-log build is trusted as PASS
- **Hypothesis:** `build_fidelity` is a negative log-signature parse only; a build that exits 0 with an empty log and touches no DLL falls into the `else → verified` branch.
- **Supporting evidence:** `build-queue-runner.ps1:139/150-152`; `Test-BuildLogFailure` fail-open on empty input; test-op `no-output` (exit 3) has no build-op analog (`:167-172`); sessions ef43777c/81e40be6.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

### Theory 3: Test-op log capture has a flush/close race with no retry barrier
- **Hypothesis:** the runner reads the wrapper-owned log single-shot before it's flushed/closed, dropping trailing per-test lines and the `Results:` summary → `counts=null` and unreadable detail → agents bypass.
- **Supporting evidence:** `build-queue-runner.ps1:106-116/183/248` + `build-queue.ps1:343-348`; the retry asymmetry vs `active.lock` (`:234-241`); session 79ed5a88 L236/L882.
- **Contradicting evidence:** per-test lines DO eventually land in the file (the loss is timing, not routing) — so this is a read-timing/flush defect, not a capture-omission defect.
- **Status:** Confirmed (mechanism = flush/read-ordering race).

## Proven Findings

1. **Per-project bin/obj are never quarantined** (root cause A) — `Remove-PoisonedArtifacts` sweep scope is worktree-root-only. Fix: recurse into per-project `**/bin` + `**/obj` (converge on the `Get-DllLockers` `**/bin` pattern its docstring already advertises), keeping the fail-open per-file delete and the 0-byte / non-`MZ` poison test.
2. **No build-output fidelity gate** (root cause B) — add a positive check for build ops: a build that exits 0 must have produced a non-empty captured log AND/OR touched its expected output DLL(s); otherwise record a new `build_fidelity` value (e.g. `no-output`) that maps to a non-PASS banner, mirroring the test-op exit-3 `no-output` safeguard.
3. **Fidelity-bearing log reads race the flush** (root cause C) — the counts read + build-log read must adopt the existing 3×/50ms retry/settle pattern already used for `active.lock` so a not-yet-flushed `Results:` line does not read as empty.
4. **Trust-erosion (symptom 4) is downstream of 1-3** — no separate remediation is required *if* 1-3 restore honest outcomes; but the fix should confirm the queue's process-hygiene (Job-Object reap + occupancy-gated recycle) still owns cleanup so agents have no reason to manually `Stop-Process`. Re-enabling `build-queue-enforce.sh` is gated on this bug being FIXED.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Quarantine sweep | `user/scripts/build-queue-hygiene.ps1` (`Remove-PoisonedArtifacts` ~576-683; `Get-DllLockers` sweep-scope reference ~917-918) | Recurse per-project bin/obj; the P0 fix |
| Build-output fidelity | `user/scripts/build-queue-runner.ps1` (`:137-153` build_fidelity; `:167-172` fidelity mapping; `:30`/`:87` schema) | New `no-output` build-op fidelity + non-empty-log / DLL-touched gate |
| Log-capture flush | `user/scripts/build-queue-runner.ps1` (`:179-192` counts read, `:138-144` build-log read, `:234-241` retry exemplar); `user/scripts/build-queue.ps1` (`:343-348` redirect owner) | Adopt retry/settle on fidelity-bearing reads |
| Outcome surface | `user/scripts/build-queue-hygiene.ps1` (`Format-BuildQueueBanner`); `build-queue-status.ps1` | New fidelity values must render in banner + status |
| Skills (banner-trust prose) | `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` | If a new build-op fidelity value is added, mirror the banner next-action guidance |
| Enforcement gate | `user/hooks/build-queue-enforce.sh` | Currently disabled; re-enable only after fix |
| Tests | `build-queue-hygiene.Tests.ps1`, `test-filtered.Tests.ps1`, `user/scripts/test_hooks.py` | New Pester coverage for per-project sweep + build-output fidelity + flush retry |

## Open Questions

- **Build-output detection method:** non-empty-log check, expected-DLL-touched (timestamp-newer-than-source) check, or both? An empty-log check is cheap and catches symptom 2 directly; a DLL-touched check is stronger but needs the expected output path per op/project. Resolve in `/plan-bug`.
- **New fidelity value naming:** reuse `no-output` for build ops (currently test-op-only, exit 3) or introduce a distinct `no-artifact` / `no-compilation` value? Affects the banner enum + skill prose.
- **Per-project sweep cost:** a `<WorktreeRoot>/**/bin|obj` recursive scan on a large multi-project solution — is the walk fast enough on every build, or should it be scoped to the projects touched by the op? Measure during fix.
- **DLL locker sweep parity:** should `Get-DllLockers` and `Remove-PoisonedArtifacts` share one per-project root-enumeration helper (its docstring already implies they should match)?
