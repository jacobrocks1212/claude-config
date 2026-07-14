# build-queue-runner.Tests.ps1 has two top-level BeforeAll blocks — Pester 6 refuses discovery — Investigation Spec

> `user/scripts/build-queue-runner.Tests.ps1` declares TWO top-level `BeforeAll` blocks. This
> was valid under Pester 5 but Pester 6.0.0 (this machine's installed version) rejects it AT
> DISCOVERY with `BeforeAll is already defined in this block`, so the entire suite — one of the
> five `build-queue*.Tests.ps1` suites that constitute the build-queue L6 completion gate —
> fails to be discovered or run. A completion-integrity suite is silently un-runnable here.

**Status:** Concluded
**Severity:** Medium
**Discovered:** 2026-07-14
**Placement:** docs/bugs/build-queue-runner-tests-dual-beforeall-fails-pester6
**Related:** docs/features/generalized-build-test-runner-skills (its Phase 4 validation sweep surfaced this; could not fix — the file matches its L6 `build-queue*.ps1` byte-untouched guard), the other four `build-queue*.Tests.ps1` suites (pass 193/0), `user/scripts/build-queue-runner.ps1` (the code under test)

---

## Verified Symptoms

1. **[VERIFIED]** `powershell.exe -NoProfile -Command "Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1"`
   fails at DISCOVERY (before any test runs) with:
   `System.Management.Automation.RuntimeException: BeforeAll is already defined in this block.
   Each block can only have one BeforeAll. Combine the code into a single BeforeAll block.`
   — raised from `Pester.psm1:1413 (New-OneTimeTestSetup)`, attributed to
   `build-queue-runner.Tests.ps1: line 126` (the SECOND `BeforeAll`). Result:
   `Tests Passed: 0, Failed: 0 … Container failed: 1`.
2. **[VERIFIED]** The installed Pester is **6.0.0** (`Get-Module -ListAvailable Pester` →
   `6.0.0` and a legacy `3.4.0`). Pester 6 hard-enforces one `BeforeAll` per block at
   discovery; Pester 5 tolerated multiple and ran them in order — hence the file was green
   when authored and only silently un-runnable after the machine upgraded to Pester 6.
3. **[VERIFIED]** The other four `build-queue*.Tests.ps1` suites discover and run (193/0 per
   the referencing feature's sweep). This is the ONLY suite of the five that Pester 6 cannot
   discover — so the L6 build-queue gate can never fully run on this machine.

## Reproduction Steps

1. `cd C:/Users/Jacob/source/repos/claude-config`
2. `powershell.exe -NoProfile -Command "Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1"`

**Expected:** the suite discovers and runs its `Describe` blocks (green, modulo any genuinely
environmental Job-Object kill cases the build-queue-generalization receipt already documents).
**Actual:** `Discovery … failed with: BeforeAll is already defined in this block` — 0 tests
run, container failed.
**Consistency:** Always, under Pester 6.x.

## Evidence Collected — serving-path trace (cause: `traced`)

Surface: the Pester discovery-failure line, attributed by Pester to `…Tests.ps1: line 126`.

```
Invoke-Pester discovery walks the file's top-level script blocks
  → hits BeforeAll #1 at line 33  → New-OneTimeTestSetup registers the one-time setup
  → hits BeforeAll #2 at line 126 → New-OneTimeTestSetup sees setup already registered
      → throws "BeforeAll is already defined in this block"   [Pester.psm1:1413]
  → discovery aborts for the whole container → 0 tests discovered/run
```

- **BeforeAll #1** (lines 33–124): sets `$script:RunnerPath` / `$script:HygienePath`,
  dot-sources hygiene, and defines `Get-SafeValue`, `Invoke-DelayedBuildLogClassify`,
  `New-FixtureStateRoot`, `Write-FixtureActiveLock`, `New-StubExec`, `Invoke-Runner`.
- **BeforeAll #2** (lines 126–291): RE-sets `$script:RunnerPath` / `$script:HygienePath`
  (identical values), RE-dot-sources hygiene, adds `$script:ScriptsDir` / `$script:AwaitPath`
  / `$script:SpawnedPids`, and defines `New-RunnerSandbox`, `New-StateRoot`, `New-Worktree`,
  `New-ExecScript`, `New-RedBuildExec`, `New-GreenBuildExec`, `New-RedTestExec`,
  `Write-ActiveLock`, `Start-RunnerProcess`, `Get-ResultJson`, `Wait-Until`, `Invoke-Await`.

The two blocks' helper names are **disjoint** (the file's own header docstring notes this);
`Get-ResultJson` in block #2 uses `Get-SafeValue` from block #1. The ONLY overlap is the three
duplicated statements (`$script:RunnerPath`, `$script:HygienePath`, `. $script:HygienePath`),
which are idempotent. The file was authored as a "merged suite" (two bug-repro concern groups)
that kept each group's setup in its OWN `BeforeAll` — the exact construct Pester 6 forbids.

## Root Cause

**Class: script-defect** (a harness TEST file incompatible with the installed test runner).
Two top-level `BeforeAll` blocks in one container. Pester 5 ran both; Pester 6.0.0 refuses the
container at discovery. The fix site lies ON the traced serving path: the two `BeforeAll`
blocks at lines 33 and 126 are exactly what discovery rejects.

## Proposed Fix Scope

Merge the two top-level `BeforeAll` blocks into a single `BeforeAll` (Pester-6 requirement,
also valid under Pester 5 — one `BeforeAll` is legal in both). Preserve every setup statement
and helper: keep block #1's contents, drop block #2's three duplicate statements
(`$script:RunnerPath`/`$script:HygienePath` re-assignments + the second `. $script:HygienePath`),
and append block #2's unique variables + helper definitions. No test body, `Describe`, `It`,
or `AfterEach` changes. Behavior-preserving: the merged setup runs the same statements the two
sequential Pester-5 `BeforeAll`s ran, in the same order.

Verify: `Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1` discovers and runs
(green, or only genuinely-environmental Job-Object kill cases the build-queue-generalization
receipt already documents).
