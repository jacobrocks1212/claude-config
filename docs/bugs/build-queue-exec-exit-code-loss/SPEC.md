---
title: "Build-queue exec scripts lose child process exit code through pipe"
status: Concluded
priority: Critical
date: 2026-07-16
---

## Verified Symptom

Three build-queue exec scripts in `repos/cognito-forms/.claude/scripts/` pipe a child process (`npx nx` or `dotnet`) through `ForEach-Object` for line filtering WITHOUT capturing the child process exit code BEFORE the pipe. This causes `$LASTEXITCODE` to reflect the ForEach-Object/pipeline tail exit code (typically 0) instead of the actual tool exit code.

**Observed impact:** A test run with 3 failing tests still banners `RESULT=PASS` to the build queue; a build with compilation errors still exits 0.

## Root Cause

The pattern used in these scripts is:
```powershell
& dotnet @args 2>&1 | ForEach-Object { ... }
$toolExit = $LASTEXITCODE  # WRONG: reflects ForEach-Object, not dotnet
```

PowerShell's `$LASTEXITCODE` reflects the exit code of the LAST command in a pipeline — in this case, the ForEach-Object scriptblock or its collection assignment, not the child process exit code. The exit code from `dotnet` or `npx nx` is lost.

## Classification

**Root cause class:** script-defect

**Files affected:**
- `repos/cognito-forms/.claude/scripts/client-build-filtered.ps1` (line 64, no exit code capture)
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (line 153, exit code captured on line 199 AFTER pipe)
- `repos/cognito-forms/.claude/scripts/build-filtered.ps1` (two instances: lines 99 and 147, exit codes captured on lines 127 and 186 AFTER pipes)

**Fixed reference:** `repos/cognito-forms/.claude/scripts/client-test-filtered.ps1` (lines 84–88) demonstrates the correct pattern:
```powershell
$allOutput = @(& npx nx @nxArgs 2>&1)
$nxExit = $LASTEXITCODE  # CORRECT: captured before pipe
```

## Proposed Fix Scope

**Mechanical fix for each script:**
1. Capture child process output into an array variable BEFORE piping: `$allOutput = @(& tool @args 2>&1)`
2. Capture exit code immediately after: `$toolExit = $LASTEXITCODE`
3. Pipe the captured array through ForEach-Object for filtering
4. Exit with the captured (not pipeline) exit code at script end: `exit $toolExit`

This is the idiomatic PowerShell pattern and matches the fix already successfully applied to `client-test-filtered.ps1` this session.

**Defect class:** Applies to ANY build-queue exec script that pipes a child process through ForEach-Object, Tee-Object, Select-Object, or Select-String. The audit found 3 affected files in the cognito-forms repo; the class is generalizable to any output-filtering script.
