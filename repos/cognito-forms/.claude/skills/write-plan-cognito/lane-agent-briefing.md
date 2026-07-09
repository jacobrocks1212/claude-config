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
4. **Run the tests and capture the GREEN state.** All tests in your lane's filter must pass. **Turn-end gate:** the RED and GREEN captures must come from COMPLETED runs — never end your turn on a backgrounded/enqueued build or a bare `build-queue: enqueued as seq=N` line. If a run was backgrounded or its wrapper died before the banner, run `~/.claude/scripts/build-queue-await.ps1 -Seq N` to block until the authoritative `RESULT=` banner; if you genuinely cannot complete verification, say so explicitly in your report — never imply green.

If your lane has deliverables with no testable behavior (pure config, scaffolding), implement them directly and say so in the report.

### Bug-fix lanes — serving-path regression test (MANDATORY)

If your lane implements a **bug fix**, its failing-test-first test MUST be a **serving-path
regression test** — a test that exercises the symptom's *actual serving path* (the path the SPEC's
root-cause trace cites as producing the observed symptom), asserting on the **observable symptom**,
not on the fix's *internal target*. A test that asserts a stored value / facet / private helper the
symptom's surface never reads does **NOT** qualify — it certifies the proxy, not the symptom.

- *Example (linked-person pill):* assert on `GetLinkedPersonAsync` / the `linked-person` serving
  path — **not** on `CompositeEntryIndex.SubmitterPersonEntryId` (an internal facet the pill does
  not read).
- Capture and paste the **RED output where the test reproduces the ORIGINAL symptom** (the assertion
  fails because the symptom is present pre-fix), then the **GREEN output** after your fix (symptom
  gone). Label both clearly in your report's TDD evidence — this RED→GREEN on the serving path is the
  bug's completion evidence (`~/.claude/skills/_components/symptom-reproduction-gate.md`).

## Verification Commands (Tier 1 — use these EXACTLY)

All build/test runs MUST go through the queue-routed skills (`Skill` tool). They serialize machine-globally against other worktrees/sessions and emit filtered output. NEVER run raw `dotnet`/`npx nx` and NEVER run a full-solution `/msbuild` (no `-Project`).

**Backend lane:**

```
# Build (incremental, test project only — queue-serialized + filtered):
/msbuild -Project "Cognito.UnitTests/Cognito.UnitTests.csproj"
# Test (no rebuild, filtered to your lane's test classes):
/mstest -Filter "ClassName~<YourTestClass>"
```

- `/mstest` is already `--no-build` + filtered. Do NOT pass `-Project` for the full solution and do NOT run unfiltered test projects.
- DLL-lock contention (MSB3027/MSB3021) is handled by the queue — do not kill processes or work around it yourself; just rerun the skill.

**Frontend lane:**

```
/nxtest -Project <nx-project> -Pattern "<pattern>" -NoCoverage
```

**Outcome signal:** every queue-routed run prints an authoritative one-line `build-queue: seq=<N> op=<op> RESULT=<PASS|FAIL|NO-TESTS-MATCHED> …` banner as its LAST stdout line — trust that line for the outcome; do not re-derive it from the surrounding output.

**Fallback (only if the `Skill` tool is missing from your toolset):** invoke the queue wrapper directly via Bash — it is the same sanctioned entry point the skills use and is hook-allowed:

```
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op mstest -Exec "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -Filter "ClassName~<YourTestClass>"
```

(`-Op msbuild -Exec "$REPO_ROOT/.claude/scripts/build-filtered.ps1" -Project "…"` for incremental builds; `-Op nxtest -Exec "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1" …` for frontend.) Never fall back to raw `dotnet`/`npx nx` — those run off-queue and are hook-blocked.

## Hard Boundaries

- Touch ONLY files inside your lane scope. If correctness genuinely requires touching a file outside it, STOP work on that deliverable and report the conflict instead of editing.
- Do NOT run `generate-server-types.ps1` or edit anything under `Cognito.Web.Client/libs/types/server-types/` — type regeneration is the orchestrator's job.
- Do NOT commit, push, or run git mutations of any kind.
- Build and test ONLY through the queue-routed skills (`/msbuild -Project …`, `/mstest -Filter …`, `/nxtest …`). Never run raw `dotnet`/`npx nx`, never a full-solution `/msbuild` (no `-Project`), and never an unfiltered test run.

## Report Format (MANDATORY)

Do not produce this report until your build/tests have COMPLETED (never backgrounded) and the outcome banner has printed — a bare `build-queue: enqueued as seq=N` line is not a result; await it via `~/.claude/scripts/build-queue-await.ps1 -Seq N` first, or state explicitly that verification is incomplete.

End your report with:

1. **Summary:** deliverables completed, files created/modified, deviations from the lane definition (with rationale).
2. **TDD evidence:** the RED-state test output (failures with reasons) and the GREEN-state output, clearly labeled.
3. **A fenced `GROUND-TRUTH OUTPUT` block** containing the *verbatim, unedited* output of, run fresh at the end of your work:
   - `git status --short`
   - `wc -l <file>` for every file you created or modified
   - `grep -n '<symbol>' <file>` for every new public symbol you added
   - your Tier 1 test skill command (`/mstest -Filter …` or `/nxtest -Project … -Pattern … -NoCoverage`) and its full pass/fail summary

The orchestrator independently re-runs the equivalent skill command. Any PASS/FAIL mismatch between your paste and the fresh re-run is treated as a falsified report and the lane is reworked — paste real output only.
