---
title: "build-queue: nxbuild produces false RESULT=FAIL 'no-output' when npx stdout settles late"
status: Investigating
kind: correctness
severity: high
author: harden-harness
date: 2026-07-17
---

## Verified Symptom

**Build:** `seq=1239 op=nxbuild` for cognito-spa project  
**Observed behavior:** `/nxbuild -Project "cognito-spa"` command reported:
```
build-queue: seq=1239 op=nxbuild RESULT=FAIL (result_fidelity=n/a) -> build produced no output
```

**Actual outcome:** Build succeeded. Verified by:
- `logs/1239.build.log` contains 733 bytes with complete Rspack output
- `logs/1239.build.log` line content:
  ```
  Building cognito-spa...
  [rolldown-plugin-dts] Warning: Failed to emit declaration file. Please try to enable `eager` option (`dts.eager` for tsdown).
  (x4)
  Rspack compiled with 2 warnings in 121.35 s
  NX  Successfully ran target build for project cognito-spa and 4 tasks it depends on
  ```
- Exit code was 0 (success)
- Nx banner at end confirms target succeeded

**False negative root cause:** The `no-output` classifier in `build-queue-runner.ps1` reported `build_fidelity='no-output'` (triggering `buildFailed` → RESULT=FAIL override) despite the build log containing full, successful output.

## Root Cause Classification

**Script-defect** in `build-queue-runner.ps1` build-log fidelity classification path (lines 220-245).

### Evidence

1. **File content exists:** `logs/1239.build.log` has 733 bytes ✓
2. **File path is correct:** Runner uses `logs/<seq>.build.log` where `seq=1239` ✓
3. **Classification runs:** The `build_fidelity` field was written to results JSON, proving the classifier ran
4. **Classifier returned "no-output":** Despite output being present
5. **Nxbuild-specific:** Comment on lines 204-209 in runner documents this exact failure mode

### Hypothesis

The `Read-WithRetry` block (lines 220-236) attempts to read `$buildLogPath` with a 10-attempt, 100ms-delay budget (1-second window total). For **slow npx/Nx I/O**, the file may:

1. **Not exist yet** when the first attempt runs (if wrapper's redirect hasn't created it), causing line 221-222 to return early with `@{ failed = $false }`, leaving `$script:buildLogTextForClassify` unset as `$null`
2. **Exist but be empty** on initial attempts (child process hasn't flushed stdout buffers yet), causing line 225-226 to return `$null` and retry
3. **Settle after 10 attempts exhaust**, causing `Read-WithRetry` to return the `-Fallback` value while `$script:buildLogTextForClassify` remains `$null`

Then line 245 calls `Test-BuildProducedNoOutput -LogText $null`, which returns `$true` (classifying as no-output).

### Why This Happened Now

- **Lines 204-209 document a prior nxbuild false-negative fix:** "WIDENED WINDOW (build-queue-nxbuild-false-no-output-fail)" mentions increasing from 3x/50ms to 10x/100ms for npx/Node.js I/O settlement
- **That fix exists in code (line 220):** `Read-WithRetry -MaxAttempts 10 -DelayMs 100`
- **But there is a secondary defect:** Even with the widened window, if all 10 attempts fail to read content (file not yet created, still being flushed), the classifier's `$script:buildLogTextForClassify` is never populated from the successful read, remaining `$null`, and Test-BuildProducedNoOutput classifies based on `$null` (returns `$true`)

The issue is that the Fallback value does NOT attempt to capture the log text as a side effect—it only returns a hash. Once exhaustion happens, the classifier loses access to the log content even if a later read would have succeeded.

## Proposed Fix Scope

**Narrow, mechanical fix:** Ensure that successful log reads update `$script:buildLogTextForClassify` **before** the Read-WithRetry returns, so the classifier always has access to the log text even if the first successful read happens on a later attempt.

**Specific change:** In the `Read-WithRetry` block (lines 220-236), assign the read log text to `$script:buildLogTextForClassify` outside the retry loop, not inside the parse block's early-return path.

Alternative: Extend the retry window further (15x/150ms = 2.25s) to give npx/Nx daemon extra settle time, but this is belt-and-suspenders—the primary fix is more robust.

**Testing:** Verify with actual `pnpm nx build cognito-spa` run; confirm `build_fidelity='verified'` in results and no `[BUILD LIED - produced no output]` banner on successful builds.

## Impact

- **Blast radius:** Build-op classifier only (test ops unaffected; msbuild likely unaffected due to faster flush)
- **Severity:** False build-failure blocks development; data loss (real outcome hidden by false negative)
- **Frequency:** Intermittent, dependent on system load and Nx daemon state
- **Affected projects:** Cognito Forms and any other repo using nxbuild via the queue

---

## Investigation Artifacts

- Real build log: `~/.claude/state/build-queue/logs/1239.build.log` (733 bytes, verified success)
- Empty/stale log: `~/.claude/state/build-queue/logs/1239.log` (0 bytes, runner's own stdout—irrelevant)
- Runner code: `build-queue-runner.ps1` lines 220-245 (fidelity classification)
- Classifier function: `build-queue-hygiene.ps1` lines 111-164 (`Test-BuildProducedNoOutput`)
- Prior art: comments lines 204-209 (nxbuild false-negative history)
