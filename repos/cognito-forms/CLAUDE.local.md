<local-constitution>
  <project>
    Cognito Forms: Multi-tenant form builder platform
    Backend: C# on .NET Framework 4.7.2 (SDK-style csproj), Azure (Table/Blob/Cosmos, App Service)
    Frontend: Vue 2.7 Composition API, TypeScript, Nx monorepo (pnpm)
  </project>

  <structure>
    Backend: Cognito.Core/ (domain), Cognito/ (business logic), Cognito.Services/ (web/API), Cognito.Queue*/ (jobs)
    Frontend: Cognito.Web.Client/apps/{spa,client,marketing,website}, libs/{model.js,vuemodel,element-ui,types,api,utils,shared-components,styles,content-data-layer,importers,workflow-diagram}
    Tests: Cognito.UnitTests/ (unit), Cognito.Forms.UnitTests/ (integration) — both MSTest
  </structure>

  <subdirectory-docs>
    These directories have their own CLAUDE.local.md with detailed patterns:
    - Cognito.Core/          — Domain layer: model hierarchy, service interfaces, DI
    - Cognito/               — Business logic: service hierarchy, data layer, storage patterns
    - Cognito.Services/      — Web/API: ASP.NET MVC controllers, BaseController, routing
    - Cognito.Web.Client/    — Frontend monorepo: Nx project mapping, apps, libs
    - Cognito.Web.Client/libs/model.js/  — Reactive entity/type/property/rule framework
    - Cognito.Web.Client/libs/vuemodel/  — Vue 2 reactivity bridge for model.js
    - Cognito.Web.Client/apps/client/    — Form rendering app: extensions, converters, web-api
    - Cognito.Web.Client/apps/spa/       — Builder/admin: GlobalState, composables, Element UI
  </subdirectory-docs>

  <knowledge-base>
    Feature docs in `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/` (sibling cog-docs repo)
  </knowledge-base>

  <coding-conventions>
    - Never reference personal/planning documentation (SPEC, PHASES, WU, work-item docs, etc.) in
      code, test names, comments, commit messages, or anything checked into the repo. These are
      local artifacts that mean nothing to other contributors.
    - Do not write code comments. The only exception is a doc comment on a public/service interface
      definition where genuinely warranted. Never delete a human's existing comment just to satisfy
      this rule.
    - Never reference the implementation process in assert messages or test names — no TDD state
      ("RED before fix", "PASS before and after fix"), no "currently fails because...", no test-ordering
      labels like "(a)/(b)/(c)". Describe only the required behavior; these artifacts go stale the
      moment the fix lands.
  </coding-conventions>

  <claude-config>
    Claude Code config for this repo is authored in the `claude-config` repo and symlinked in.
    This file itself (`CLAUDE.local.md`), plus `.claude/{CLAUDE.md, settings.json, settings.local.json,
    skill-config, skills, commands, knowledge}`, are symlinks into
    `~/source/repos/claude-config/repos/cognito-forms/`.

    - Editing through a symlink writes through to `claude-config` — but the Edit tool refuses to
      write through symlinks, so edit the real target under `claude-config/repos/cognito-forms/`.
    - These files are NOT tracked by this repo's git; `git status` here never shows them. Commit
      config changes in the `claude-config` repo instead.
    - Mappings live in `claude-config/manifest.psd1`; `claude-config/setup.ps1 check|repair` verifies them.
    - See `~/source/repos/CLAUDE.md` ("Claude Config") and `claude-config/CLAUDE.md` for the full system.
  </claude-config>
</local-constitution>

# Build & Test Workflow

**The build/test skills are the ONLY sanctioned way to build or test in this repo: `/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`.** They route every build/test through the machine-global build queue, which serializes runs across worktrees/sessions and emits filtered output. Raw `dotnet build` / `dotnet test` / `npx nx test` run off-queue: they are blocked by a PreToolUse hook in Cognito worktrees, reintroduce the cross-worktree DLL-copy-lock contention (MSB3027/MSB3021) the queue exists to prevent, and dump unfiltered output into context. Do NOT invoke raw `dotnet`/`npx nx` to build or test — always use a skill. The raw command shapes shown below are reference only (the skills wrap them).

## Building
- **`/msbuild`** — full-solution filtered build (also regenerates server types). The authoritative build.
- **`/msbuild -Project "<relative/path/to.csproj>"`** — fast single-project incremental build (path relative to repo root, e.g. `Cognito.UnitTests/Cognito.UnitTests.csproj`). The sanctioned targeted-compile path; use it in-loop instead of a full-solution build.
- Underlying command (reference): `dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.sln" -verbosity:minimal`.

## Running Tests
Use the **`/mstest` skill** — filtered test output (passed/failed tests, errors, summary), routed through the queue. Underlying command (reference only — do not run directly):
```bash
dotnet test "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" --filter "ClassName~MyTestClass" --verbosity minimal
```
- Default project: `Cognito.UnitTests` — **all** service/unit tests live here (including `EntryIndexServiceTests`, `PersonSubmissionIndexingTests`, `ShouldInvalidateIndexTests`, etc.)
- `Cognito.Forms.UnitTests` is the **Selenium/browser integration** test project — only use `-TestDll "Cognito.Forms.UnitTests"` for browser-based tests
- Filter syntax: `ClassName~Foo`, `Name~Bar`, `FullyQualifiedName~Baz`
- Tests run with `--no-build` — build first with `/msbuild` if needed
- **Do not relocate test output to dodge DLL-copy-lock contention.** `dotnet test --artifacts-path`/`--output` to a temp dir breaks net472 tests that resolve content files at relative paths (e.g. `bin\Cognito.Services\Web.config`, `_snapshots/*`, FakeAzure data) — they fail en masse with `DirectoryNotFoundException`/`AggregateException`, which masquerades as a logic regression. If `bin\Debug\*.dll` is locked (MSB3027/MSB3021 "used by another process"), kill the holding `testhost`/`dotnet` process (`Get-Process testhost,dotnet | Stop-Process`) and rerun against the normal `bin/Debug` instead.
- **When removing/renaming a serialized or persisted property, the snapshot tests are the authority — not grep.** Snapshot/golden keys are transformed from the C# name (e.g. `Enabled` → `PeopleFormSettings_Enabled` in the schema snapshot, `Settings_PeopleForm_Enabled` in the OpenAPI snapshot). A grep for the source symbol will miss re-keyed fixtures. After the change, run the snapshot suite (`SchemaGeneratorTests`, `JsonUtility*SerializationTests`, etc.) and let failures enumerate every fixture that needs updating.

## Running Frontend Tests
Use the **`/nxtest` skill** (queue-routed, filtered). Underlying command (reference only — do not run directly):
```bash
cd "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client" && npx nx test <project> -- --testPathPattern="<pattern>" --no-coverage
```
- Nx project names (NOT directory names): `cognito-client`, `cognito-spa`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`, etc.
- Use `npx nx show projects` to list all available project names
- `--testPathPattern` filters by file path (e.g., `"migrate-selection-fields"`)
- First run may be slow due to dependency builds (model.js, vuemodel, element-ui)

## Build Verification

For build verification in plans, use the `/msbuild` skill which runs the filtered build script:
```
/msbuild
```

This runs `build-filtered.ps1` which shows only errors + summary (prevents context bloat). Pass `-Project "<csproj>"` for a fast single-project incremental build instead of the full solution.

Do not run `dotnet build` directly — it bypasses the queue and is blocked by a hook in Cognito worktrees.

## Test Verification

For running backend tests, use the `/mstest` skill which runs the filtered test script:
```
/mstest
```

This runs `test-filtered.ps1` which shows only passed/failed tests, errors, and summary (prevents context bloat).

Do not run `dotnet test` directly — it bypasses the queue and is blocked by a hook in Cognito worktrees.

## Frontend Build Verification

For frontend build verification, use the `/nxbuild` skill:
```
/nxbuild
```

This runs `client-build-filtered.ps1` which shows only errors + summary (prevents context bloat).

Options:
- `-Project "cognito-spa"` — build specific project
- `-All` — build all projects
- Common projects: `cognito-spa`, `cognito-client`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`

## Frontend Test Verification

For running frontend tests, use the `/nxtest` skill:
```
/nxtest
```

This runs `client-test-filtered.ps1` which shows only PASS/FAIL tests, errors, and summary (prevents context bloat).

Options:
- `-Project "cognito-spa"` — test specific project (default: cognito-spa)
- `-Pattern "Button"` — filter by file path (--testPathPattern)
- `-Filter "should render"` — filter by test name (--testNamePattern)
- `-NoCoverage` — skip coverage for faster runs

<csharp-workflow>
  <mandatory-skills>
    When editing ANY .cs file, you MUST invoke these skills FIRST:
    1. csharp-cognito - C# patterns and Cognito conventions
    2. architecture-patterns - Clean architecture, DDD, service patterns

    DO NOT proceed with C# edits until these skills are loaded.
  </mandatory-skills>

  <file-management>
    SDK-style projects auto-include .cs files. Do NOT manually add Compile items
    unless setting metadata (DependentUpon, etc.). Follow existing folder/namespace conventions.
  </file-management>

  <syntax-rules>
    C# version varies by project — check the project's .csproj LangVersion before using newer syntax.
    Most projects use LangVersion 8.0; Cognito.Core and Cognito.Services use LangVersion 10.

    SAFE EVERYWHERE (C# 8):
    - Nullable reference types (#nullable enable)
    - Using declarations (using var x = ...)
    - Switch expressions (x switch { ... })
    - Async streams (IAsyncEnumerable)
    - Indices and ranges (^1, ..)
    - Null-coalescing assignment (??=)
    - Pattern matching with property/positional patterns

    SAFE IN CORE/SERVICES ONLY (C# 9-10):
    - Records, init-only setters, target-typed new
    - Pattern matching with and/or/not

    AVOID EVERYWHERE:
    - File-scoped namespaces (namespace X;) — not used in this codebase
    - Required members, raw string literals, generic attributes (C# 11+)
  </syntax-rules>
</csharp-workflow>

<frontend-workflow>
  <mandatory-skills>
    When editing frontend files in Cognito.Web.Client/, invoke relevant skills:

    For .vue files: vue, vue-composition-api, vuejs-development
    For .ts/.tsx files: typescript-advanced-types
    For styling: tailwind-design-system (if using Tailwind)
    Always: nx-monorepo, frontend-design (for UI work)
  </mandatory-skills>

  <conventions>
    - Vue 2.7 with Composition API (NOT Vue 3)
    - TypeScript strict mode
    - Nx monorepo structure: apps/{spa,client,marketing,website}
    - Use composables for shared logic
    - Prefer ref() over reactive() for primitives
  </conventions>
</frontend-workflow>

<work-logging>
  ## Work Logging

  Scoped to Cognito Forms sessions only (2026-06-11) — other repos no longer log.

  The `work-logging-plugin` MCP server exposes `work_log_append` — an append-only JSONL logger
  that captures significant engineering work for future interview prep, portfolio generation, and career analysis.
  Records are persisted to `~/.interview-prep/work-log.jsonl`.

  ### When to call it
  Call `work_log_append` at the **end** of any session that produces meaningful engineering output.
  This includes completing a `/write-plan`, or any other skill-driven work that results in real code changes.
  Skip it for trivial edits, config tweaks, or exploratory research that doesn't produce artifacts.

  ### Required parameters
  | Parameter | Type | Description |
  |-----------|------|-------------|
  | `skill` | string | Skill name that completed (e.g., "write-plan") |
  | `project` | string | Project identifier (e.g., "cognito-forms") |
  | `title` | string | One-line title of the work |
  | `summary` | string | 1-3 sentence narrative of what was accomplished |
  | `files_modified` | string[] | Paths of all changed files |

  ### Optional parameters (include when available)
  | Parameter | Type | Description |
  |-----------|------|-------------|
  | `branch` | string | Git branch name |
  | `commit` | string | Git commit SHA |
  | `phases_md` | string | Path to PHASES.md (if phased implementation) |
  | `spec_md` | string | Path to SPEC.md (if implementing a spec) |
  | `technologies` | string[] | Tech stack used (e.g., ["Rust", "TypeScript"]) |
  | `patterns` | string[] | Design patterns applied (e.g., ["observer-pattern", "memoization"]) |
  | `technical_context` | string | Architecture decisions, tradeoffs, constraints |
  | `extra` | object | Arbitrary additional fields merged into the record |

  ### Example
  ```
  work_log_append(
    skill="write-plan",
    project="cognito-forms",
    title="DC bias regression in voice synthesis",
    summary="Fixed pw parameter defaulting to 0 causing DC output. Added boundary validation in set_pw().",
    files_modified=["src/voice.rs", "tests/voice_test.rs"],
    branch="bugfix/dc-bias",
    commit="abc1234",
    technologies=["Rust"],
    patterns=["boundary-validation"]
  )
  ```
</work-logging>

## Backend Gotchas

### Reading entry field values from a `GetFieldPath` result

Never use `ModelInstance.GetValue(string)` or `instance.GetReference(leafProperty)` to read a value resolved from `form.GetFieldPath(...)`. Field paths can be nested (e.g. a field inside a Section, path `"Section.Email"`), but:

- `ModelInstance.GetValue(string property)` does a direct property-name lookup (`Type.Values[property]`) — it does NOT walk dotted paths, so nested paths silently return nothing.
- `instance.GetReference(leafProp)` against the root instance is wrong when the leaf property is declared on a nested child type.

Always resolve through `ModelSource`, which walks the full dotted path:

```csharp
var formType = form.ToModelType(registerRules: true, useLookupSourceTypes: false, organization: Organization);
if (ModelSource.TryGetSource(formType, fieldPath.Value, out var source))
{
    var value = source.GetValue(instance);     // or source.GetReference(instance)
}
```

Canonical example: `EntryIndexService.ResolveCustomerEntryIdAsync` (PersonField case, `Cognito.Core/Services/Forms/EntryIndexService.cs`). See also `IndexBuilder.cs` and `AutoCreateEntriesService.cs`. (Mistake originally shipped in PR #16543.)

## Branch-aware doc context

Most `p/*` work branches are backed by a docs directory under `../cog-docs/docs/bugs/<id>-<slug>/` or `../cog-docs/docs/features/<slug>/` (SPEC.md, PHASES.md, plans/). A `SessionStart` hook (`load-branch-docs-context.sh`) resolves the current branch to that directory via a `**Branch:**` field in its SPEC.md or PHASES.md and injects a pointer at session start.

- **When the hook surfaces a pointer:** before doing any work on the branch, read that directory's SPEC.md and PHASES.md to re-familiarize yourself with the in-progress work.
- **When the hook is silent but branch docs likely exist** (an un-stamped dir): list `../cog-docs/docs/{bugs,features}`, resolve the directory by slug or work-item id, review it, and add a `**Branch:** <current-branch>` line to that SPEC.md or PHASES.md so future sessions resolve automatically (self-heal/backfill).
- The field format the hook matches: a line `**Branch:** <branch>` (the value may be backticked and may carry a trailing parenthetical note).
