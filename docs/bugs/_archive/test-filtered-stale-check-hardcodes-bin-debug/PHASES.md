# Implementation Phases — test-filtered.ps1 stale-check `bin\Debug\` hardcode

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — PowerShell script + Pester unit tests; no app/runtime surface (docs-and-tooling change, structurally outside any MCP reach).

## Cross-feature Integration Notes

No hard deps. Parent spec `build-queue-copy-lock-stale-dll-false-success` (Concluded) shipped the `Test-StaleTestDll` guard this phase corrects; this is a scoped follow-up to its Phase 3, not a dependency edge.

---

### Phase 1: Resolve the actual test-DLL location instead of assuming `bin\Debug\`

**Scope:** Replace the hardcoded `bin\Debug\` path derivation at `test-filtered.ps1:92` with a pure resolver that finds where the named test project's DLL actually lands, so the staleness guard stops false-firing exit 4 for projects whose Debug `OutputPath` is not `bin\Debug\` (e.g. `Cognito.Forms.UnitTests` → `bin\`). Preserve all three existing exit contracts.

**Deliverables:**
- [x] New pure helper `Resolve-TestDllPath -ProjectDir <dir> -TestDll <name>` in `test-filtered.ps1`, dot-source-safe (defined above `Invoke-Main`, guarded like the existing helpers so Pester can load it without invoking dotnet). Behavior:
  - Search `<ProjectDir>\bin` recursively for `<TestDll>.dll`.
  - **Selection rule (handles multi-copy layouts):** prefer the shallowest match — the DLL directly under a Debug output dir — over deeper config-variant copies (`bin\AutoTest\`, `bin\AutoTest-Firefox\`, … present for `Cognito.Forms.UnitTests`). Concretely: return the match with the fewest path segments below `bin\`; break ties by newest `LastWriteTime`. This mirrors the artifact `dotnet test --no-build` resolves for the default (Debug) configuration.
  - **Not-built fallback:** if no `<TestDll>.dll` exists anywhere under `bin`, return the conventional `<ProjectDir>\bin\Debug\<TestDll>.dll` path (a path that won't exist) so the downstream `Test-StaleTestDll` "missing → stale" branch still fires exit 4 for a genuinely-unbuilt project. Never throw.
- [x] `Invoke-Main` rewired: line 92's `$testDllPath = "$projectRoot\$TestDll\bin\Debug\$TestDll.dll"` becomes `$testDllPath = Resolve-TestDllPath -ProjectDir $testDllProjectDir -TestDll $TestDll`. `Test-StaleTestDll`'s signature and body are unchanged (it already takes `$DllPath`).
- [x] Improve the exit-4 WARN to print the resolved path actually checked (not a fixed string), so a genuine stale/missing case is debuggable.
- [x] Tests: `Describe "Resolve-TestDllPath"` in `test-filtered.Tests.ps1` covering — (a) `bin\Debug\<name>.dll` layout resolves to that path; (b) `bin\<name>.dll` layout (no `Debug` subdir) resolves to the `bin\` copy — **the case that reproduces this bug**; (c) multi-copy layout (`bin\<name>.dll` + `bin\AutoTest\<name>.dll`) resolves to the shallow `bin\` copy, not the deeper one; (d) not-built (no DLL anywhere under `bin`) returns a `bin\Debug\` path that does not exist and does not throw.

**Minimum Verifiable Behavior:** `Invoke-Pester test-filtered.Tests.ps1` is green including the new `Resolve-TestDllPath` `Describe`, and case (b) fails against the pre-fix code (RED) — proving the resolver, not the freshness comparison, is what changed. Manually: from a Cognito worktree with `Cognito.Forms.UnitTests\bin\Cognito.Forms.UnitTests.dll` present and fresh, `/mstest -TestDll "Cognito.Forms.UnitTests"` no longer exits 4 with the stale WARN and proceeds to run tests.

**Runtime Verification** *(checked by manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `/mstest -TestDll "Cognito.Forms.UnitTests"` against a fresh build runs the tests instead of false-firing exit 4.
- [ ] <!-- verification-only --> `/mstest` (default `Cognito.UnitTests`, `bin\Debug\` layout) still resolves and runs unchanged — no regression for the default project.
- [ ] <!-- verification-only --> Exit 4 still fires (correctly) when the target project was never built — resolver returns the non-existent `bin\Debug\` path and `Test-StaleTestDll` reports missing.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior reachable via MCP (PowerShell build-tooling script; verified by Pester + manual `/mstest`).

**Prerequisites:** None.

**Files likely modified:**
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` — add `Resolve-TestDllPath`; rewire `Invoke-Main` line 92; improve exit-4 WARN message. (Single canonical file, symlinked into all worktrees — one edit covers every worktree.)
- `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1` — add `Describe "Resolve-TestDllPath"` (4 cases above). This closes the coverage gap that let Phase 3 ship the `bin\Debug\` assumption: no existing test exercised a non-`bin\Debug\` layout.

**Testing Strategy:** Pure-function Pester unit tests, mirroring the existing `Test-StaleTestDll` `Describe` (temp dirs under `$env:TEMP`, real files, `Start-Sleep` for mtime ordering). No dotnet invocation; the dot-source guard (`$MyInvocation.InvocationName -ne '.'`) keeps `Invoke-Main` from running on import. Run: `Invoke-Pester repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1`.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** and writes FIXED.md once this phase's Runtime Verification passes — do not author those as checkbox rows.

**Integration Notes for Next Phase:** None — single-phase fix.

#### Implementation Notes (2026-07-01)

**Work completed (TDD, orchestrator + Sonnet subagents):**
- Added pure helper `Resolve-TestDllPath([string]$ProjectDir, [string]$TestDll)` at `test-filtered.ps1:84`, between `Test-StaleTestDll` and `Invoke-Main`. Computes `$binDir` + `$fallback` (`bin\Debug\<TestDll>.dll`) up front; recursive `Get-ChildItem -Filter "$TestDll.dll" -File`; selects the shallowest match by relative-path segment count ascending, ties broken by `LastWriteTime` descending; whole body in `try/catch` returning `$fallback` so it never throws. Absent `bin` or zero matches → `$fallback`.
- Rewired `Invoke-Main`: `$testDllProjectDir` now assigned before use (`:117`), `$testDllPath = Resolve-TestDllPath ...` (`:118`) replaces the hardcoded `bin\Debug\` literal. `Test-StaleTestDll` signature/body unchanged.
- Exit-4 WARN (`:120`) now interpolates the *resolved* `$testDllPath` — no hardcoded `bin\Debug\` literal remains.
- Tests: added `Describe "Resolve-TestDllPath"` (4 cases) at `test-filtered.Tests.ps1:99`, mirroring the `Test-StaleTestDll` temp-dir pattern. Case (b) (`bin\` layout) proven RED against pre-fix code (function absent → `CommandNotFoundException`) before implementation.

**Verification:** `Invoke-Pester test-filtered.Tests.ps1` → 14/14 passing (4 new + 10 pre-existing, no regression). Ground-truth verified: yes (integrity checks re-run independently, matched subagent blocks exactly). Assertion-vs-intent read: all 4 new tests discriminating, not tautological.

**Pitfalls / notes:** helper uses `$matches` as a local (shadows the PowerShell automatic `$Matches`); harmless here since no `-match` is used in scope. Single canonical file symlinked into all Cognito worktrees — one edit covers every worktree.

**Files modified:**
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (+26 lines: helper + rewire)
- `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1` (+61 lines: `Describe "Resolve-TestDllPath"`)

**Review verdict:** PASS

---

## Review Notes

**Batch 1 (WU-1) — 2026-07-01 — Verdict: PASS.** Ground-truth verified: yes. Helper logic, `Invoke-Main` rewire ordering, WARN de-hardcoding, and 4 discriminating Pester cases all correct; 14/14 green. Propagation check clean (no cross-file consumers — sole caller `Invoke-Main` migrated). Mount-site verified (`Invoke-Main:118`). No actionable items.

**Re-verification — 2026-07-12.** SPEC.md **Status:** had been left at `Concluded` despite the fix being implemented + committed (`3f7a1638`) on 2026-07-01. Re-ran the full Pester gate on the workstation to confirm no regression before flipping to `Fixed`: only Pester 3.4.0 was pre-installed (cannot run this file's top-level `BeforeAll` outside a `Describe` block); bootstrapped `Install-PackageProvider NuGet` + `Install-Module Pester -Scope CurrentUser -MinimumVersion 5.0.0` (landed 6.0.0) and re-ran — **18/18 passed, 0 failed**, including all 4 `Resolve-TestDllPath` cases. No code changes this session. See `FIXED.md` for the full receipt.
