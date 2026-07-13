---
kind: fixed
feature_id: test-filtered-stale-check-hardcodes-bin-debug
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

test-filtered-stale-check-hardcodes-bin-debug marked fixed on 2026-07-12 by the interactive
subagent orchestration Jacob directed (BUILD-QUEUE lane wave). This receipt was written by a
bug-fix subagent, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
operator-directed-interactive.

## Notes

The fix (`Resolve-TestDllPath` helper + `Invoke-Main` rewire + resolved-path WARN in
`repos/cognito-forms/.claude/scripts/test-filtered.ps1`) and its Pester coverage
(`Describe "Resolve-TestDllPath"`, 4 cases, in `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1`)
were already implemented and committed in a prior session (`3f7a1638`, 2026-07-01,
"fix(cognito-scripts): resolve actual test-DLL path instead of assuming bin/Debug"), per
PHASES.md's Implementation Notes — which record case (b), the `bin\`-only layout (the exact
repro of this bug), proven RED against the pre-fix code (function absent) before the helper
existed. `SPEC.md` **Status:** had been left at `Concluded` since; this session's job was to
re-verify the gate is still green and complete the fixed-receipt admin.

This session re-ran the full Pester gate on the workstation to confirm GREEN still holds. The
only pre-installed Pester was 3.4.0 (Windows PowerShell built-in), which cannot run this file's
Describe-scoped top-level `BeforeAll` (`RuntimeException: The BeforeAll command may only be used
inside a Describe block`) — this session bootstrapped `Install-PackageProvider NuGet` +
`Install-Module Pester -Scope CurrentUser -MinimumVersion 5.0.0` (landed 6.0.0), then re-ran
clean.

## Symptom Reproduction (red -> green)

The bug's exact symptom — a permanent exit-4 false positive for a test project whose Debug
`OutputPath` is not `bin\Debug\` (`Cognito.Forms.UnitTests` -> `bin\`) — is reproduced by
`Describe "Resolve-TestDllPath"` case (b), `test-filtered.Tests.ps1:120` ("resolves a
bin\<name>.dll layout with no Debug subdirectory to the bin copy"): only
`<ProjectDir>\bin\Foo.dll` exists (no `Debug` subdir); asserts
`Resolve-TestDllPath -ProjectDir $projectDir -TestDll "Foo"` returns that path.

- **RED** (documented, PHASES.md Implementation Notes, 2026-07-01): before the fix,
  `Resolve-TestDllPath` did not exist, so this case failed (`CommandNotFoundException`) — the
  same failure class as the shipped bug (a `bin\`-only layout resolves to nothing usable, so
  `Test-StaleTestDll` sees "missing" and `Invoke-Main` exits 4 unconditionally, unclearable by
  rebuild).
- **GREEN** (this session, workstation, Pester 6.0.0):
  `powershell.exe -Command "Invoke-Pester -Path 'C:\Users\Jacob\source\repos\claude-config\repos\cognito-forms\.claude\scripts\test-filtered.Tests.ps1' -Output Detailed"`
  -> **Tests Passed: 18, Failed: 0, Skipped: 0** (6 `Test-SummaryLine` + 4 `Test-StaleTestDll` +
  4 `Resolve-TestDllPath` + 4 `Get-TestOutcomeExitCode` — no regression). The `bin\`-only case now
  resolves to the real DLL path instead of false-firing.

## Outstanding (operator — Runtime Verification rows, NOT ticked; Pester cannot cover live dotnet/mstest)

PHASES.md's three Runtime Verification rows are marked `<!-- verification-only -->` and are
explicitly gate-owned by Jacob's manual `/mstest` check per the plan's execution notes ("checked
by manual testing — NOT by the implementation agent"). Left unticked, not blind-ticked:

- `/mstest -TestDll "Cognito.Forms.UnitTests"` against a fresh build runs tests instead of
  false-firing exit 4 — needs a live Cognito worktree + build queue.
- `/mstest` (default `Cognito.UnitTests`, `bin\Debug\` layout) still resolves and runs unchanged —
  needs a live run.
- Exit 4 still fires (correctly) when the target project was never built — needs a live run.
