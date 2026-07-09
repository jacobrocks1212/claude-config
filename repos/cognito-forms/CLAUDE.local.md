<local-constitution>
  <project>
    Cognito Forms: Multi-tenant form builder platform
    Backend: C# on .NET Framework 4.7.2 (SDK-style csproj), Azure (Table/Blob/Cosmos, App Service)
    Frontend: Vue 2.7 Composition API, TypeScript, Nx monorepo (pnpm)
  </project>

  <structure>
    Backend: Cognito.Core/ (domain), Cognito/ (business logic), Cognito.Services/ (web/API), Cognito.Queue*/ (jobs)
    Frontend: Cognito.Web.Client/apps/{spa,client,marketing,website}, libs/{model.js,vuemodel,element-ui,types,api,utils,shared-components,styles,content-data-layer,importers,workflow-diagram}
    Tests: Cognito.UnitTests/ (unit), Cognito.Forms.UnitTests/ (Selenium/browser integration) — both MSTest
  </structure>

  <subdirectory-docs>
    These directories have their own CLAUDE.local.md with detailed patterns:
    Cognito.Core/ (domain layer, DI), Cognito/ (services, data layer, storage), Cognito.Services/ (MVC controllers, routing),
    Cognito.Web.Client/ (Nx monorepo map), libs/model.js/ (reactive entity framework), libs/vuemodel/ (Vue 2 bridge),
    apps/client/ (form rendering: extensions, converters, web-api), apps/spa/ (builder/admin: GlobalState, composables, Element UI)
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

  <subagent-dispatch>
    Prefer restricted agent types for read-only work: Explore (or an agent with an explicit narrow
    tools list) instead of a default "All tools" general-purpose agent. Unrestricted subagents in
    this repo inherit the full skill/plugin/MCP surface (~2–4x the baseline tokens of a restricted
    agent) — reserve them for work that actually edits files or runs builds.
  </subagent-dispatch>

  <claude-config>
    Claude Code config for this repo is authored in the `claude-config` repo and symlinked in.
    This file itself (`CLAUDE.local.md`), plus `.claude/{CLAUDE.md, settings.json, settings.local.json,
    skill-config, skills, commands, knowledge}`, are symlinks into
    `~/source/repos/claude-config/repos/cognito-forms/`.

    - The Edit tool refuses to write through symlinks — edit the real target under
      `claude-config/repos/cognito-forms/`. These files are NOT tracked by this repo's git;
      commit config changes in the `claude-config` repo.
    - Mappings live in `claude-config/manifest.psd1`; `claude-config/setup.ps1 check|repair` verifies them.
    - See `~/source/repos/CLAUDE.md` ("Claude Config") and `claude-config/CLAUDE.md` for the full system.
  </claude-config>
</local-constitution>

# Build & Test Workflow

**The build/test skills are the ONLY sanctioned way to build or test in this repo: `/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`.** They route every build/test through the machine-global build queue, which serializes runs across worktrees/sessions and emits filtered output (errors + summary only — prevents context bloat). Raw `dotnet build` / `dotnet test` / `npx nx build|test` run off-queue: they are blocked by a PreToolUse hook in Cognito worktrees, reintroduce cross-worktree DLL-copy-lock contention (MSB3027/MSB3021), and dump unfiltered output into context. Any raw command shapes shown below are reference only (the skills wrap them).

**Shell crash ≠ build failure.** Git Bash's `sh.exe` can intermittently segfault around a build-queue invocation (exit 139, `Segmentation fault`, a `sh.exe.stackdump` in the repo root) even though the detached build ran to completion. On any shell-level crash or abrupt tool error around a queue call, do not trust the shell's exit signal: run `/build-queue-status`, then read the seq's own artifacts (`~/.claude/state/build-queue/logs/<seq>.log`, `<seq>.build.log`, `results/<seq>.json`) for the real outcome before re-running or investigating a "failure".

## Building (backend)

- **`/msbuild`** — full-solution filtered build (also regenerates server types). The authoritative build.
- **`/msbuild -Project "<relative/path/to.csproj>"`** — fast single-project incremental build (e.g. `Cognito.UnitTests/Cognito.UnitTests.csproj`). The sanctioned targeted-compile path; use it in-loop instead of a full-solution build.
- Underlying command (reference): `dotnet build "…\Cognito.sln" -verbosity:minimal`.

## Backend Tests

- **`/mstest`** — filtered test runner (passed/failed, errors, summary), queue-routed.
- Default project: `Cognito.UnitTests` — **all** service/unit tests live here (including `EntryIndexServiceTests`, `PersonSubmissionIndexingTests`, `ShouldInvalidateIndexTests`, etc.). Use `-TestDll "Cognito.Forms.UnitTests"` ONLY for Selenium/browser integration tests.
- Filter syntax: `ClassName~Foo`, `Name~Bar`, `FullyQualifiedName~Baz`.
- Tests run with `--no-build` — build first with `/msbuild` if needed.
- **Do not relocate test output to dodge DLL-copy-lock contention.** `dotnet test --artifacts-path`/`--output` to a temp dir breaks net472 tests that resolve content files at relative paths (`bin\Cognito.Services\Web.config`, `_snapshots/*`, FakeAzure data) — they fail en masse with `DirectoryNotFoundException`, masquerading as a logic regression. If `bin\Debug\*.dll` is locked (MSB3027/MSB3021), the build queue automatically reaps leftover build processes, recycles VBCSCompiler, and quarantines 0-byte/truncated DLLs between runs — check `/build-queue-status` for the per-build hygiene outcome before manually killing anything.
- **When removing/renaming a serialized or persisted property, the snapshot tests are the authority — not grep.** Snapshot/golden keys are transformed from the C# name (e.g. `Enabled` → `PeopleFormSettings_Enabled` in the schema snapshot, `Settings_PeopleForm_Enabled` in the OpenAPI snapshot), so a grep for the source symbol misses re-keyed fixtures. Run the snapshot suite (`SchemaGeneratorTests`, `JsonUtility*SerializationTests`, etc.) and let failures enumerate every fixture needing updates.

## Frontend Build & Tests

- **`/nxbuild`** — filtered frontend build. Options: `-Project "cognito-spa"`, `-All`.
- **`/nxtest`** — filtered frontend test runner. Options: `-Project "cognito-spa"` (default), `-Pattern "Button"` (file path filter), `-Filter "should render"` (test name filter), `-NoCoverage`.
- Nx project names (NOT directory names): `cognito-client`, `cognito-spa`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`, … — `npx nx show projects` lists all.
- First run may be slow due to dependency builds (model.js, vuemodel, element-ui).

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
    C# version varies by project — check the .csproj LangVersion before using newer syntax.
    Most projects use LangVersion 8.0; Cognito.Core and Cognito.Services use LangVersion 10.
    - SAFE EVERYWHERE (C# 8): nullable reference types, using declarations, switch expressions,
      async streams, indices/ranges (^1, ..), ??=, property/positional pattern matching
    - SAFE IN CORE/SERVICES ONLY (C# 9-10): records, init-only setters, target-typed new, and/or/not patterns
    - AVOID EVERYWHERE: file-scoped namespaces (not used in this codebase); required members,
      raw string literals, generic attributes (C# 11+)
  </syntax-rules>
</csharp-workflow>

<frontend-workflow>
  <mandatory-skills>
    When editing frontend files in Cognito.Web.Client/:
    .vue files: vue, vue-composition-api | .ts/.tsx: typescript-advanced-types |
    styling: tailwind-design-system (if Tailwind) | always: nx-workspace-patterns, frontend-design (UI work)
  </mandatory-skills>

  <conventions>
    - Vue 2.7 with Composition API (NOT Vue 3); TypeScript strict mode
    - Nx monorepo: apps/{spa,client,marketing,website}
    - Use composables for shared logic; prefer ref() over reactive() for primitives
  </conventions>
</frontend-workflow>

<work-logging>
  Scoped to Cognito Forms sessions only (2026-06-11) — other repos no longer log.

  Call the `work-logging-plugin` MCP tool `work_log_append` at the **end** of any session that
  produces meaningful engineering output (completed plans, real code changes). Skip for trivial
  edits, config tweaks, or exploratory research. Records persist to `~/.interview-prep/work-log.jsonl`.

  Required: `skill`, `project` ("cognito-forms"), `title`, `summary` (1-3 sentences), `files_modified`.
  Include when available: `branch`, `commit`, `phases_md`, `spec_md`, `technologies`, `patterns`,
  `technical_context`. (Full parameter docs are on the tool schema.)
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

Most `p/*` work branches are backed by a docs directory under `../cog-docs/docs/bugs/<id>-<slug>/` or `../cog-docs/docs/features/<slug>/` (SPEC.md, PHASES.md, plans/). A `SessionStart` hook (`load-branch-docs-context.sh`) resolves the current branch to that directory via a `**Branch:** <branch>` line in its SPEC.md or PHASES.md and injects a pointer at session start.

- **When the hook surfaces a pointer:** read that directory's SPEC.md and PHASES.md before doing any work on the branch.
- **When the hook is silent but branch docs likely exist:** list `../cog-docs/docs/{bugs,features}`, resolve the directory by slug or work-item id, review it, and backfill a `**Branch:** <current-branch>` line into its SPEC.md or PHASES.md so future sessions resolve automatically.
