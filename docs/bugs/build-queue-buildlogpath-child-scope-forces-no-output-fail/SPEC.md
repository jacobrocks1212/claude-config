# Build-queue `$buildLogPath` child-scope discard forces `no-output` FAIL — Investigation Spec

> The runner assigns `$buildLogPath` inside a `Get-SafeValue { }` child scope, so the classifier reads `$null` and force-fails every genuinely-successful build op as `build_fidelity=no-output` — the entire build-log-honesty feature is inert.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-06
**Placement:** docs/bugs/build-queue-buildlogpath-child-scope-forces-no-output-fail
**Related:** docs/bugs/build-queue-hygiene-dot-source-discarded-in-child-scope (same child-scope-discard class, different variable — fixed 2d9f8ae 2026-07-06), docs/bugs/build-queue-false-green-on-silent-build-failure (origin of the `no-output` gate + `Test-BuildProducedNoOutput`, fd7a81a 2026-07-03), docs/bugs/build-queue-copy-lock-stale-dll-false-success (origin of `build_fidelity` + `Test-BuildLogFailure` / `log-failure-override`)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

<!-- Full evidence + hypothesis ledger + micro-repro output retained in sibling INVESTIGATION.md. -->

---

## Verified Symptoms

1. **[VERIFIED]** `/msbuild` through the build queue reports `RESULT=FAIL (build_fidelity=no-output)` → banner "build produced no output; delete obj/bin and rebuild" on genuinely-**successful** compiles. Observed on four consecutive builds this session (seq 707–710, 2026-07-06 12:16–12:26), including a full-solution rebuild. — confirmed by the user's live session (screenshots) + four on-disk receipts.
2. **[VERIFIED]** The banner's remedy ("delete obj/bin and rebuild") does nothing, so an agent loops — the reporting session burned ~18 min / 13.7k tokens escalating misdiagnoses (transient → script/env issue → capture misfire) and never converged. — confirmed by the user's session transcript.
3. **[VERIFIED]** Each `logs/<seq>.build.log` is populated with a 53-byte SUCCESS summary (`Building solution. / Build succeeded. / 0 Error(s)`), and `results/<seq>.json` records `exit_code:1` (forced — the grandchild exited 0). — confirmed by on-disk inspection of all four receipts.

## Reproduction Steps

1. In a Cognito worktree (repro'd in `Cognito Forms-B`), run `/msbuild` via the build queue on a clean, warning-free solution that compiles successfully (grandchild `dotnet build` exits 0).
2. Read the resulting `~/.claude/state/build-queue/logs/<seq>.build.log` and `results/<seq>.json`.
3. **Observed:** `<seq>.build.log` holds a valid 53-byte "Build succeeded. / 0 Error(s)" summary, yet `results/<seq>.json` shows `"exit_code":1`, `"build_fidelity":"no-output"`, and the banner prints `RESULT=FAIL … build produced no output; delete obj/bin and rebuild`.

**Expected:** an exit-0 compile with a populated success log reports `RESULT=PASS (build_fidelity=verified)`.
**Actual:** every successful build op is force-failed as `no-output`.
**Consistency:** deterministic — every successful build op, every run (not timing-dependent). Regression window 2026-07-03 (fd7a81a) → present. A genuinely-failing build (exit≠0) still reports FAIL correctly via exit code.

## Evidence Collected

### Source Code

Serving-path trace, surface → source (root-cause-trace-gate artifact; each hop `file:line`; cause = **traced**, fix-site on the path):

1. Banner "build produced no output; delete obj/bin and rebuild" ← `Format-BuildQueueBanner` `build-queue-hygiene.ps1:1505-1506`; FAIL label set at `:1480` because `ExitCode -ne 0`.
2. `build_fidelity='no-output'` + forced `exit 1` ← `build-queue-runner.ps1:178-180`.
3. That branch fires because `Test-BuildProducedNoOutput -LogText $script:buildLogTextForClassify` is `$true` ← `build-queue-runner.ps1:170`.
4. `Test-BuildProducedNoOutput($null)` → `$true` via `IsNullOrWhiteSpace` ← `build-queue-hygiene.ps1:161`.
5. `$script:buildLogTextForClassify` is `$null` because the `Read-WithRetry` parse block short-circuited at `build-queue-runner.ps1:152` (`IsNullOrWhiteSpace($buildLogPath)` true) and never reached the `ReadAllText` + assignment at `:155-159`.
6. **DEFECT NODE — `build-queue-runner.ps1:112`:** `$buildLogPath = …` is executed inside a `Get-SafeValue { }` scriptblock, which `Get-SafeValue` runs via `& $Block` (a CHILD scope). The bare assignment creates a child-local; the runner's main-scope `$buildLogPath` (initialized `$null` at `:86`) is never written. The redirect at `:113` still works because `$startProcParams['RedirectStandardOutput'] = …` is a hashtable-index mutation (reference type — propagates), so `<seq>.build.log` IS captured — the classifier just never opens it.

Supporting facts:
- `Read-WithRetry` default window: `MaxAttempts=3 × DelayMs=50` (≤100 ms) — `build-queue-hygiene.ps1:91-93`. Never exercised (short-circuit returns non-null on attempt 1).
- `build-filtered.ps1` (Cognito repo) emits via `Write-Host` and is **correct** — `Start-Process -RedirectStandardOutput` does capture `Write-Host`; the 3-line log is intentional (`-verbosity:minimal` regex-filtered to banner/error-count lines).

### Runtime Evidence

Isolated deterministic micro-repro (`scratchpad/repro.ps1` + `repro-child.ps1`, no production script modified), replicating runner `:86` + `:106-116` + the `WaitForExit`→read path:

```
outer $buildLogPath after Get-SafeValue block = []          # discarded → null
IsNullOrWhiteSpace($buildLogPath) = True
RedirectStandardOutput key in hashtable = [...child.out.log]  # redirect OK (hashtable mutation)
immediate read length = 53        # T1 refuted — full the instant WaitForExit returns
delayed(+300ms) read length = 53  # no empty→full transition
classifier short-circuits (never reads file) = True
```

Four real receipts (seq 707–710) at HEAD c90e2db corroborate: all `build_fidelity:no-output`, `exit_code:1`, over a populated 53-byte SUCCESS `.build.log`.

### Git History

- `$buildLogPath`-in-child-scope assignment dates to bf31d55 (2026-07-01) — harmless until the `no-output` gate landed.
- fd7a81a (2026-07-03) added `Test-BuildProducedNoOutput` and made a `$null` classify-text force FAIL — this is the regression trigger. Before it, a `$null` fed only `Test-BuildLogFailure`, which fails OPEN.
- 2d9f8ae (2026-07-06) fixed the *sibling* child-scope-discard bug (hygiene dot-source) but did not cover this variable.

### Related Documentation

Root `CLAUDE.md` build-queue section documents `build_fidelity` `no-output` semantics; the parent bug `build-queue-false-green-on-silent-build-failure` deferred the "expected-output-DLL" check as an Open Question — that check would independently disambiguate genuine no-artifact from a fed-null classifier, but is not required for this fix.

## Theories

### Theory 1: flush/timing race (log not flushed at classify)
- **Status:** Ruled Out — micro-repro reads 53 bytes immediately after `WaitForExit()` and again at +300 ms; no empty→full transition.

### Theory 2: `Write-Host` not captured by `-RedirectStandardOutput`
- **Status:** Ruled Out — micro-repro child emits solely via `Write-Host`; redirected file = 53 bytes exact content.

### Theory 3: 53-byte summary trips the near-empty threshold
- **Status:** Ruled Out — trimmed length 52 ≥ `MinChars` 40, and moot since the classifier never reads the file.

### Theory 4: child-scope discard of `$buildLogPath`
- **Hypothesis:** `$buildLogPath` assigned inside `Get-SafeValue { }` is `$null` in main scope at classify, so the parse short-circuits and feeds `$null` to the classifier.
- **Supporting evidence:** micro-repro (outer var `[]`, `IsNullOrWhiteSpace`=True, hashtable redirect key set); matches all four receipts; identical class to fixed sibling 2d9f8ae.
- **Contradicting evidence:** none.
- **Status:** **Confirmed.**

## Proven Findings

1. **Root cause = child-scope variable discard** at `build-queue-runner.ps1:112`. The main-scope `$buildLogPath` is never written, so the classifier reads `$null` and force-fails every successful build op as `no-output`. (cause label: **traced**.)
2. **The whole build-log-classification feature is inert**, not just `no-output`. The same short-circuit means `Test-BuildLogFailure` / `log-failure-override` never reads real failure content either — the fix must re-verify that path also revives.
3. **Fix is claude-config-only.** `build-filtered.ps1` (Cognito repo) is correct — no Cognito-side change. Fix at `build-queue-runner.ps1:106-116`: assign `$buildLogPath` in the runner's MAIN scope (compute the path outside the `Get-SafeValue` and keep only `New-Item` inside; or return the path from the block; or mirror the existing `$script:buildLogTextForClassify` with `$script:buildLogPath`). Do NOT touch the `no-output` classifier or `Read-WithRetry` — they are correct, just fed `$null`.
4. **Test ops are unaffected** — the counts path (`:218-233`) recomputes `$testLogPath` locally in its own scriptblock; blast radius is build ops only (`/msbuild`, `/nxbuild`).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Build-log path binding (root cause) | `user/scripts/build-queue-runner.ps1` (`:86` init, `:106-116` child-scope assignment, `:152` short-circuit) | Assign `$buildLogPath` in main scope so the classifier reads the real path |
| Build-output classifier (fed `$null`, itself correct) | `user/scripts/build-queue-hygiene.ps1` (`Test-BuildProducedNoOutput` `:111-165`) | No change — verify it now receives real text |
| Log-failure override (co-defeated) | `user/scripts/build-queue-runner.ps1` (`:170-177`), `build-queue-hygiene.ps1` (`Test-BuildLogFailure`) | Re-verify the failure-signature path revives once the path is bound |
| Outcome surface | `user/scripts/build-queue-hygiene.ps1` (`Format-BuildQueueBanner`), `build-queue-status.ps1` | Should render PASS/verified on exit-0 once fixed |
| Tests | `build-queue-hygiene.Tests.ps1` (+ any runner-scope test) | Add a guard asserting `$buildLogPath` is non-null after the `if ($isBuildOp)` block on an exit-0 build |

## Open Questions

- None blocking the fix. (Optional hardening: the parent bug's deferred expected-output-DLL check would add a second, path-independent no-output signal — track separately if desired, not required here.)
