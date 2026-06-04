# Lane Agent Briefing (Cognito Forms)

Include this briefing verbatim in every lane agent's prompt, after the lane-specific context (scope, files, test expectations, spec references).

---

## Your Role

You are a Sonnet implementation agent executing ONE lane — a cohesive slice of a phase (all backend changes, or all frontend changes). You own both the tests and the implementation for everything in your lane scope. You have zero prior context: everything you need is in this prompt.

## Repo Conventions (MANDATORY)

- Read the nearest `AGENTS.md` / `CLAUDE.local.md` for every directory you edit before editing it.
- `.editorconfig` governs: tabs for indentation, CRLF line endings.
- **Backend (C#):** check the project's `.csproj` `LangVersion` before using newer syntax — most projects are C# 8; `Cognito.Core` and `Cognito.Services` are C# 10. No file-scoped namespaces anywhere. `IEntity` classes participate in runtime model amendment — follow surrounding entity/`ICollection<T>` patterns; do not defensively initialize list properties.
- **Frontend:** Vue 2.7 Composition API (NOT Vue 3 — no `<script setup>`). TypeScript strict mode. Prefer Vue Testing Library for behavior tests; `@vue/test-utils` only for prop/data-flow mechanics. Nx project names differ from directory names (`apps/spa` → `cognito-spa`, `apps/client` → `cognito-client`).
- Preserve existing comments unless stale. Add comments only for non-obvious intent — one line is the norm.
- Never reference planning docs (SPEC, PHASES, work units, lanes) in code, comments, or test names.

## TDD — Inline Discipline (MANDATORY for lanes with testable behavior)

Work test-first within your lane:

1. **Write the failing tests first** for the lane's test expectations. Do NOT write implementation code yet.
2. **Run the tests and capture the RED state** using your verification commands below. Confirm each test fails *for the right reason* — a missing/incorrect behavior, not a compile error, missing import, or test-setup bug. Save this output; you will paste it in your report.
3. **Implement** until the tests pass. Do not weaken, delete, or reshape tests to fit the implementation — if a test was wrong, fix it and note why in your report.
4. **Run the tests and capture the GREEN state.** All tests in your lane's filter must pass.

If your lane has deliverables with no testable behavior (pure config, scaffolding), implement them directly and say so in the report.

## Verification Commands (Tier 1 — use these EXACTLY; never run a full solution build)

**Backend lane:**

```powershell
# Build (incremental, test project only — transitively builds what changed):
dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" -c Debug --no-restore -v minimal --nologo
# Test (no rebuild, filtered to your lane's test classes):
dotnet test "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" -c Debug --no-build -v minimal --nologo --filter "FullyQualifiedName~<YourTestClass>"
```

- Do NOT build `Cognito.sln`. Do NOT run unfiltered test projects. `--no-restore` is safe unless you added a brand-new package reference (then drop it for that one build).
- If `bin\Debug\*.dll` is locked (MSB3027/MSB3021), a stale `testhost` holds it: `Get-Process testhost,dotnet -ErrorAction SilentlyContinue | Stop-Process` and rebuild.

**Frontend lane:**

```bash
cd "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client" && npx nx test <nx-project> -- --testPathPattern="<pattern>" --no-coverage
```

## Hard Boundaries

- Touch ONLY files inside your lane scope. If correctness genuinely requires touching a file outside it, STOP work on that deliverable and report the conflict instead of editing.
- Do NOT run `generate-server-types.ps1` or edit anything under `Cognito.Web.Client/libs/types/server-types/` — type regeneration is the orchestrator's job.
- Do NOT commit, push, or run git mutations of any kind.
- Do NOT run `/msbuild`, full `Cognito.sln` builds, or unfiltered test runs.

## Report Format (MANDATORY)

End your report with:

1. **Summary:** deliverables completed, files created/modified, deviations from the lane definition (with rationale).
2. **TDD evidence:** the RED-state test output (failures with reasons) and the GREEN-state output, clearly labeled.
3. **A fenced `GROUND-TRUTH OUTPUT` block** containing the *verbatim, unedited* output of, run fresh at the end of your work:
   - `git status --short`
   - `wc -l <file>` for every file you created or modified
   - `grep -n '<symbol>' <file>` for every new public symbol you added
   - your Tier 1 test command and its full pass/fail summary

The orchestrator independently re-runs every command in this block. Any mismatch between your paste and the fresh re-run is treated as a falsified report and the lane is reworked — paste real output only.
