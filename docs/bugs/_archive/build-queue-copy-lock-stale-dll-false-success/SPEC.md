# Build Queue Certifies Success on a Copy-Lock Failure → Stale-DLL False Pass — Investigation Spec

> An MSB3027 copy-lock failure (obj/ rebuilt fresh, copy to bin/Debug blocked by a leftover locker) makes MSBuild log "Build FAILED" while still exiting 0. The build queue trusts the exit code, records `exit_code: 0`, skips every staleness guard, and `/mstest --no-build` then runs the stale `bin/Debug` DLL — costing agents huge investigation loops. The same "signal can't be trusted" theme has a **test-side twin**: `test-filtered.ps1`'s stale summary regex fails to parse modern `dotnet test` output, so a *passing* run can't be certified green either. Both ends of "did this actually pass?" fail open.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-01
**Fixed:** 2026-07-13
**Fix commit:** 7ece6da
**Placement:** docs/bugs/build-queue-copy-lock-stale-dll-false-success
**Related:** [`PHASES.md`](./PHASES.md) (fix decomposition), `docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/` (Concluded — Phases 1–5; this is a distinct, uncovered failure mode extending that work), `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/`, `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/`

<!-- Status lifecycle: Investigating → Concluded. Root cause proven; ready for /plan-bug. -->

---

## Verified Symptoms

1. **[VERIFIED]** A single-project `/msbuild` (seq 346) reported success while the compile actually failed — `obj/Debug/Cognito.UnitTests.dll` rebuilt fresh (Jul 1 08:51) but `bin/Debug/Cognito.UnitTests.dll` stayed stale (Jun 30 18:09). — confirmed directly in the user-provided session screenshots (build log showed "Build FAILED, 2 Error(s)" with MSB3027/MSB3021; queue result recorded `exit_code: 0`).
2. **[VERIFIED]** The copy failed because a leftover `testhost (40380)` process from a prior test run held a lock on the `bin/Debug` DLL. — named explicitly in the seq 346 build log per the screenshots.
3. **[VERIFIED]** `/mstest` ran the **stale** `bin/Debug` DLL (via `--no-build`) — the test asserting the old `?id=` param ran and failed, even though the source file on disk correctly asserted `?accountId=`. — confirmed in screenshots.
4. **[VERIFIED]** The agent spent ~8m46s / 70k+ tokens chasing "my edit didn't persist" before reaching root cause. — visible in the screenshot footer; this is the friction cost being targeted.
5. **[VERIFIED]** `test-filtered.ps1`'s summary regex does **not** match modern `dotnet test` output (`Passed! - Failed: 0, Passed: N, ...`), so a genuinely-passing run produced **no summary line and no TRX** — the Phase-4 result-fidelity guard could not certify a green, and the agent was forced to verify pass/fail by manual code↔test inspection instead of trusting an automated result. — confirmed in the second session's screenshot ("test-filtered.ps1 silently swallows results when it can't parse the summary format"; the only TRX on disk was a stale April one, a red herring). This is the **test-side twin** of the build-side exit-code lie: the queue's result signal cannot be trusted from *either* end.
6. **[REPORTED]** This class of confusion recurs. Session mining across 264 Cognito Forms session files surfaced 5 recurring build/test-staleness patterns (stale test DLL, exit-code-lies, `--no-build` staleness, async typegen, parallel PDB-lock), several sessions with 50+ friction-keyword hits. — mining is partly inferred from keyword density; recurrence is real but per-episode root cause is not individually re-verified.

## Reproduction Steps

1. Leave a `testhost`/`dotnet` process from a prior/aborted test run alive, holding an open handle on a `bin/Debug/*.dll`.
2. Edit the corresponding source, then run `/msbuild -Project "<that project>"` (routes through `build-queue.ps1` → `build-queue-runner.ps1` → `build-filtered.ps1`).
3. MSBuild recompiles into `obj/Debug` but the copy to `bin/Debug` fails with MSB3027 ("cannot copy — file in use") → log says "Build FAILED, N Error(s)".
4. Run `/mstest` for that project.

**Expected:** The build queue reports the build as FAILED (a copy-lock is a real failure), quarantines/refuses the stale artifact, and/or `/mstest` refuses to test against a bin DLL that lost the copy race — the agent gets a clear "build failed: locked, killed locker, rebuild" signal.
**Actual:** Queue records `exit_code: 0` (false success); staleness guards are skipped; `/mstest --no-build` silently runs the stale `bin/Debug` DLL; the agent is left to reverse-engineer a "my edit didn't persist" mystery.
**Consistency:** Deterministic given the precondition (a leftover locker + a build whose only failure is the blocked copy). The precondition itself is intermittent.

## Evidence Collected

### Source Code (the false-success mechanism)

- **`user/scripts/build-queue-runner.ps1:88–95`** — success is decided **solely** by the grandchild's `$proc.ExitCode`; `$buildFailed = ($exitCode -ne 0)`. There is **no** parse of the build log for `Build FAILED` / `MSB3021` / `MSB3027`. This is the core defect.
- **`build-filtered.ps1`** (Cognito filtered build script) — has **no explicit `exit`**, so PowerShell inherits `$LASTEXITCODE` from the last `dotnet build`. Under MSB3027, `dotnet build` can log "Build FAILED" yet exit 0 → the runner sees 0.
- **`user/scripts/build-queue-runner.ps1:96–98`** — `Remove-PoisonedArtifacts` (the Phase-3 quarantine sweep) runs **only when `$buildFailed == true`**. A copy-lock that exits 0 skips quarantine entirely.
- **`test-filtered.ps1:26`** + **`repos/cognito-forms/.claude/skills/mstest/SKILL.md:11`** — `/mstest` hardcodes `--no-build`; it tests whatever DLL exists in `bin/Debug`, stale or not.
- **Job Object reaping** (`build-queue-runner.ps1:83–92`, `build-queue-hygiene.ps1:221–266`) — reaps only **descendants of the current build**, and only in the `finally` **after** `WaitForExit`. A `testhost` from a *prior* run is not a descendant → never reaped **before** this build's copy step (the exact window where the lock matters).
- **Phase-4 result-fidelity guard** (`test-filtered.ps1:74–77`, exit 3 on zero test output) — a *test*-side fidelity check exists; there is **no build-side counterpart** asserting the compile actually produced/refreshed its outputs.
- **`test-filtered.ps1` summary-regex staleness** (~line 29 filter + the `resultLineCount`/`summarySeen` logic feeding the exit-3 guard) — the summary/result regex does not match modern `dotnet test` output (`Passed!  - Failed: 0, Passed: N, Skipped: 0, Total: N, ...`). A passing run therefore emits **no** parsed summary line, so the fidelity guard sees zero output and the run cannot be certified green — a false-negative twin of the build-side false-positive. No TRX is produced either (the only on-disk TRX in the repro was a stale April file — a red herring).

### Runtime Evidence

- Session screenshots (this conversation): seq 346 log = "Build FAILED, 2 Error(s)" MSB3027/MSB3021, locker `testhost (40380)`; queue wrapper `exit_code: 0`; `obj/` DLL Jul 1 08:51 vs `bin/Debug` DLL Jun 30 18:09.
- Session mining: 264 files matched build/test friction keywords; 5 recurring root-cause families; multiple sessions with dense (50+) friction-keyword clusters.

### Related Documentation

- `build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md` (Concluded) mentions MSB3027/MSB3021 only as *tribal-knowledge context* ("kill the holding testhost/dotnet"), and its Phase-3 quarantine deletes **only 0-byte/truncated (non-PE) DLLs** — never stale-but-valid ones. The copy-lock/false-exit-0 path is explicitly outside its scope.

## Theories

### Theory 1: Exit-code trust — the queue certifies success on a lie
- **Hypothesis:** Because `build-queue-runner.ps1` trusts `$LASTEXITCODE` and never parses the log, an MSB3027 copy failure that exits 0 is recorded as success, disabling every downstream guard.
- **Supporting evidence:** `build-queue-runner.ps1:88–95` (no log parse); `build-filtered.ps1` (no explicit exit); screenshot shows "Build FAILED" + `exit_code: 0`.
- **Contradicting evidence:** None found.
- **Status:** Confirmed.

### Theory 2: Guards gated behind `$buildFailed` are structurally blind to exit-0 failures
- **Hypothesis:** Quarantine (and by extension staleness detection) only runs when `$buildFailed`, so any failure that exits 0 bypasses cleanup.
- **Supporting evidence:** `build-queue-runner.ps1:96`.
- **Status:** Confirmed.

### Theory 3: Pre-build locker reaping is missing; `--no-build` compounds it
- **Hypothesis:** No mechanism kills a prior-run locker *before* the copy step, and `/mstest --no-build` then trusts the un-refreshed bin DLL.
- **Supporting evidence:** Job Object reaps only current-build descendants, post-exit; `test-filtered.ps1:26`.
- **Status:** Confirmed.

### Theory 4: The test-result signal is un-certifiable from the parse side, not just the exit side
- **Hypothesis:** `test-filtered.ps1`'s summary regex predates the current `dotnet test` output format, so a passing run yields no parsed summary and no TRX; the fidelity guard then can't distinguish "passed but unparseable" from "no tests ran," and the agent falls back to manual inspection.
- **Supporting evidence:** Second session screenshot — modern output `Passed! - Failed: 0, Passed: N` not matched; no summary line; only a stale April TRX on disk; agent verified by code↔test inspection because it "couldn't get a trustworthy automated green."
- **Contradicting evidence:** None found.
- **Status:** Confirmed.

## Proven Findings

- **Load-bearing defect is script-level, not skill-prose.** The queue's success signal is not certified — it inherits an exit code MSBuild sets unreliably under copy-lock. Skill-prose warnings only speed agent *recovery*; they cannot prevent the false `exit_code: 0`. (Directly answers the user's "should we update the test/build skills?" — yes, but as the secondary layer.)
- **Two-layer fix, per the harness mission ("gates that refuse early over reviews that catch late"; "deterministic script-owned state over LLM-inferred"):**
  1. **Primary (scripts):** add a **build result-fidelity guard** — parse the build log for `Build FAILED` / `MSB3021` / `MSB3027` (and assert the expected output was refreshed) and override a bogus `exit_code: 0` to a failure; **reap prior-run lockers** (processes holding handles on the worktree's `bin/Debug` DLLs) *before* the compile/copy; **ungate** staleness quarantine from `$buildFailed` so a stale-but-valid bin DLL that lost the copy race is detected. Surface the outcome in `build-queue-status.ps1` hygiene (mirrors Phase-4/5 shape).
  2. **Secondary (skills):** update `/msbuild` + `/mstest` prose so the agent recognizes a stale-DLL / copy-lock signal fast (and `/mstest` warns/refuses when the target bin DLL predates the source or a build-failure fidelity flag is set).
- **In scope (test-result parse fidelity):** fix `test-filtered.ps1`'s summary regex to match the current `dotnet test` output (`Passed! - Failed: X, Passed: Y, Skipped: Z, Total: N`) so a passing run produces a real parsed pass/fail count and the Phase-4 fidelity guard can distinguish "passed" from "no tests ran." Without this, the queue's *test* signal is as untrustworthy as its *build* signal — both ends of "did this actually pass?" fail open. The regex fix and the copy-lock guard are the two halves of one theme: **the queue must certify results, never infer them from an unparsed/uncertified signal.**
- **Distinct failure mode, not a regression or duplicate** of the Concluded hygiene bug: that work handles crash-time 0-byte/truncated artifacts and orphaned processes; this is a *successful-exit* build that silently failed to copy, leaving a valid-PE-but-stale DLL.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Build queue runner (success determination) | `user/scripts/build-queue-runner.ps1` | Primary — trusts exit code; gates guards on `$buildFailed` |
| Build queue hygiene lib | `user/scripts/build-queue-hygiene.ps1` | Add pre-build locker reap + stale-valid-DLL detection + log-based failure classification |
| Filtered build script | Cognito `build-filtered.ps1` | No explicit exit; needs to propagate real MSBuild failure |
| Test skill (`--no-build`) | `test-filtered.ps1`, `repos/cognito-forms/.claude/skills/mstest/SKILL.md` | Secondary — silently tests stale bin DLL; add staleness/fidelity refusal |
| Test-result parsing | `test-filtered.ps1` (summary/result regex + `resultLineCount`/`summarySeen`) | In scope — stale regex fails to match modern `dotnet test` output; passing runs yield no parsed count/TRX and can't be certified green |
| Build skill prose | `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` (+ nxbuild/nxtest as applicable) | Secondary — agent-facing recognition/recovery guidance |
| Status view | `user/scripts/build-queue-status.ps1` | Surface new build-fidelity/locker-reap hygiene outcome |

## Open Questions

- Can we cheaply enumerate handle-holders on a given `bin/Debug/*.dll` on Windows (restart-manager API vs. `handle.exe` vs. brute `Get-Process testhost,dotnet` scoped to the worktree) for a targeted pre-build reap that avoids the machine-global-kill footgun the hygiene work deliberately avoided?
- Should the build fidelity guard assert output freshness generally (each expected `bin` output newer-than-or-equal-to its `obj` counterpart), catching copy-skip failures beyond MSB3027 too (session mining hinted at `/SkipUnchangedFiles`-class staleness)?
- Does the same exit-0-on-failure risk exist for the Nx paths (`client-build-filtered.ps1` / `client-test-filtered.ps1`, which also lack explicit exits)? Likely in-scope for `/nxbuild` + `/nxtest` mirroring.
