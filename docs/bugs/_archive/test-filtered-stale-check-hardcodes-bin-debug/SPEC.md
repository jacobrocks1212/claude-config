# test-filtered.ps1 stale-check hardcodes `bin\Debug\` — permanent false positive for non-default OutputPath test projects — Investigation Spec

> The Phase-3 stale-DLL guard assumes every test project outputs to `bin\Debug\`, so it fires exit-4 "stale" on *every* `/mstest -TestDll "Cognito.Forms.UnitTests"` run — a false positive no rebuild can clear, which drives agents to bypass the sanctioned test path with hand-rolled `--no-build` scratchpad runners.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-01
**Placement:** docs/bugs/test-filtered-stale-check-hardcodes-bin-debug
**Related:** `docs/bugs/_archive/build-queue-copy-lock-stale-dll-false-success/` (parent — this is a defect in that spec's shipped Phase 3 "test honesty"); `docs/bugs/_archive/build-queue-no-artifact-or-process-hygiene-on-crash/`

---

## Verified Symptoms

1. **[VERIFIED]** `/mstest -TestDll "Cognito.Forms.UnitTests"` reports the test DLL "stale or missing" and exits 4 on every run, even when the DLL is freshly built — confirmed by the user (image #1: "the DLL is actually fresh"; mtime 12:13, newer than source) and by filesystem inspection.
2. **[VERIFIED]** The false positive is unclearable — rebuilding does not help, because the DLL will never appear at the path the guard checks (`bin\Debug\`). It lives at `bin\`.
3. **[VERIFIED]** Agents route *around* the sanctioned path in response: the user's other agent dropped to `run-diag.ps1 --no-build` explicitly to "bypass the broken stale check" (image #1), and a second agent hand-rolled a `run-trx.ps1` in scratchpad hardcoding the csproj + a TRX logger, running `dotnet test --no-build` off-queue (image #2).
4. **[VERIFIED]** The bypass pattern is widespread — 115 of ~sampled Cognito-Forms sessions across 5 worktrees carry a bypass signature (`run-trx` / `run-diag` / `dotnet test --no-build` / scratchpad `.ps1` test runners). (`/mine-sessions`, 2026-07-01.)

## Reproduction Steps

1. In a Cognito worktree, build so `Cognito.Forms.UnitTests\bin\Cognito.Forms.UnitTests.dll` is current.
2. Run `/mstest -TestDll "Cognito.Forms.UnitTests"` (a documented, sanctioned usage — `mstest/SKILL.md:17`).
3. Observe: `WARN: ...\Cognito.Forms.UnitTests\bin\Debug\Cognito.Forms.UnitTests.dll is stale or missing... Run /msbuild first`, exit 4.

**Expected:** The guard resolves the DLL's *actual* output location, finds it fresh, and runs the tests.
**Actual:** The guard checks a path that never exists, treats "missing" as "stale," and refuses to run.
**Consistency:** Always, for any test project whose Debug output is not `bin\Debug\`.

## Evidence Collected

### Source Code — the defect (single line)
`repos/cognito-forms/.claude/scripts/test-filtered.ps1:92`:

```powershell
$testDllPath = "$projectRoot\$TestDll\bin\Debug\$TestDll.dll"   # hardcoded bin\Debug\
```

`Test-StaleTestDll` (lines 43–82) returns `$true` when `-not (Test-Path $DllPath)` (line 45). For `Cognito.Forms.UnitTests` the computed path never exists, so the "missing → stale" branch fires unconditionally → `Invoke-Main` exits 4 (lines 94–97). The DLL-path derivation, not the freshness comparison, is wrong.

This is the **only** stale-check site. `build-queue.ps1`, `build-queue-runner.ps1`, and `build-queue-hygiene.ps1` do not re-derive DLL paths (confirmed by source-analysis subagent). The file is symlinked from `claude-config` into every worktree, so it is one canonical file — one fix.

### Root Cause — divergent OutputPath conventions
Both test projects set `<AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>`, but their Debug OutputPath differs:

| Project | csproj OutputPath (Debug) | Actual DLL | Matches hardcoded `bin\Debug\`? |
|---------|---------------------------|------------|----------------------------------|
| `Cognito.UnitTests` (default `$TestDll`) | (default) | `Cognito.UnitTests\bin\Debug\Cognito.UnitTests.dll` | ✅ yes — guard works |
| `Cognito.Forms.UnitTests` (Selenium) | `<OutputPath>bin\</OutputPath>` + no framework append | `Cognito.Forms.UnitTests\bin\Cognito.Forms.UnitTests.dll` | ❌ no — guard false-fires |

The Phase-3 fix (commit `1880012`) baked in `bin\Debug\`, correct only for the default project. The guard was never exercised against `-TestDll "Cognito.Forms.UnitTests"`.

### Git History
- `bf31d55` — Phase 1 build honesty
- `1880012` — Phases 2+3; introduced `Test-StaleTestDll` and the hardcoded `bin\Debug\` path (this defect)
- `08c67f9` — Phase 4 surface build_fidelity/lockers_reaped

### Related Documentation
- Parent spec `build-queue-copy-lock-stale-dll-false-success` — **Concluded**, Phase 3 marked complete. Its own Open Questions already flagged "per-test-project output paths" as unresolved; this bug is that gap manifesting.
- `mstest/SKILL.md:17` documents `-TestDll "Cognito.Forms.UnitTests"` as the sanctioned way to run Selenium tests — so the false-firing path is a first-class, documented usage.

## Theories

### Theory 1: Hardcoded `bin\Debug\` vs per-project OutputPath
- **Hypothesis:** The guard computes a fixed `bin\Debug\` DLL path; projects with a custom `OutputPath` (no framework-append) output elsewhere, so the path never exists and "missing" reads as "stale."
- **Supporting evidence:** Filesystem shows `Cognito.Forms.UnitTests\bin\...dll` and csproj `<OutputPath>bin\</OutputPath>`; `Cognito.UnitTests` (default) resolves to `bin\Debug\` and does *not* false-fire.
- **Contradicting evidence:** None.
- **Status:** **Confirmed.**

## Proven Findings

1. **Root cause:** `test-filtered.ps1:92` hardcodes the Debug output subdirectory (`bin\Debug\`) instead of resolving the project's actual output location. Correct for `Cognito.UnitTests`, wrong for `Cognito.Forms.UnitTests` and any test project with a non-default `OutputPath`.
2. **Blast radius:** exit-4 false positive on every `-TestDll "Cognito.Forms.UnitTests"` run; unclearable by rebuild.
3. **Second-order harm (the friction the user flagged):** the guard was intended to make the sanctioned `/mstest` path *trustworthy* so agents stop hand-rolling off-queue test runners. A permanent false positive inverts that — it *creates* a new, legitimate-seeming reason to bypass the queue, reintroducing exactly the cross-worktree copy-lock contention (MSB3027/MSB3021) the queue exists to prevent.

## Fix Direction (decided with user — for `/plan-bug`)

**Resolve the actual DLL location** rather than assuming `bin\Debug\`. Approach: glob for `<TestDll>.dll` under `$projectRoot\$TestDll\bin` and select the artifact `dotnet test --no-build` would actually load; fall back to a genuinely-missing → stale result only when no DLL exists anywhere under `bin`. Robust to any `OutputPath` / `AppendTargetFrameworkToOutputPath` convention, present and future.

**Design constraints for the plan:**
- `Cognito.Forms.UnitTests\bin` also contains sibling config outputs (`bin\AutoTest\`, `bin\AutoTest-Firefox\`, …) each with a copy of the DLL. Resolution must prefer the DLL directly under the Debug OutputPath (the one `dotnet test --no-build` resolves), not the newest across all subdirs, or the guard could compare the wrong artifact.
- Preserve the three existing exit contracts: 1 (not a git repo), 3 (zero test output), 4 (genuinely stale/missing). Exit 4 must still fire when the project was never built.
- The parent spec's Open Question ("should the guard assert output freshness generally, catching copy-skip beyond MSB3027") is adjacent; keep this fix scoped to path resolution unless the plan folds them deliberately.
- Add a `test-filtered.Tests.ps1` case covering a `bin\`-only (no `Debug` subdir) layout — the missing coverage that let Phase 3 ship the assumption.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Stale-DLL guard | `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (line 92; `Test-StaleTestDll` 43–82; `Invoke-Main` 84–97) | Permanent exit-4 false positive for non-`bin\Debug\` test projects |
| Guard unit tests | `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1` | No coverage for `bin\`-only layout — the gap that shipped the bug |
| Sanctioned test path (behavioral) | `mstest/SKILL.md`, build queue | Documented `-TestDll "Cognito.Forms.UnitTests"` usage is unusable → drives off-queue bypass |

## Open Questions

- Should the fix also emit the resolved DLL path in the WARN message so a genuine exit-4 is debuggable (vs. today's misleading hardcoded path)?
- Is any *other* named test project likely to adopt a custom `OutputPath`? (Today only `Cognito.Forms.UnitTests` among test projects; `Cognito.Amender` / `ExoModel.*` share the convention but aren't test targets.)
