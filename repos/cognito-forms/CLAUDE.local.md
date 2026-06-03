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
    - Write comments only for non-obvious behavior — intent, invariants, contracts, or subtle edge
      cases. Do not narrate straightforward code.
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

All projects use SDK-style .csproj. `dotnet build` and `dotnet test` are the primary commands.

## Building
```bash
dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.sln" -verbosity:minimal
```
- **Prefer `/msbuild` skill** — runs filtered build showing only errors + summary
- `dotnet build` restores by default; pass `--no-restore` to skip

## Running Tests
```bash
dotnet test "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" --filter "ClassName~MyTestClass" --verbosity minimal
```
- **Prefer `/mstest` skill** — runs filtered test output showing only passed/failed tests, errors, and summary
- Default project: `Cognito.UnitTests` — **all** service/unit tests live here (including `EntryIndexServiceTests`, `PersonSubmissionIndexingTests`, `ShouldInvalidateIndexTests`, etc.)
- `Cognito.Forms.UnitTests` is the **Selenium/browser integration** test project — only use `-TestDll "Cognito.Forms.UnitTests"` for browser-based tests
- Filter syntax: `ClassName~Foo`, `Name~Bar`, `FullyQualifiedName~Baz`
- Tests run with `--no-build` — build first with `/msbuild` if needed
- **Do not relocate test output to dodge DLL-copy-lock contention.** `dotnet test --artifacts-path`/`--output` to a temp dir breaks net472 tests that resolve content files at relative paths (e.g. `bin\Cognito.Services\Web.config`, `_snapshots/*`, FakeAzure data) — they fail en masse with `DirectoryNotFoundException`/`AggregateException`, which masquerades as a logic regression. If `bin\Debug\*.dll` is locked (MSB3027/MSB3021 "used by another process"), kill the holding `testhost`/`dotnet` process (`Get-Process testhost,dotnet | Stop-Process`) and rerun against the normal `bin/Debug` instead.
- **When removing/renaming a serialized or persisted property, the snapshot tests are the authority — not grep.** Snapshot/golden keys are transformed from the C# name (e.g. `Enabled` → `PeopleFormSettings_Enabled` in the schema snapshot, `Settings_PeopleForm_Enabled` in the OpenAPI snapshot). A grep for the source symbol will miss re-keyed fixtures. After the change, run the snapshot suite (`SchemaGeneratorTests`, `JsonUtility*SerializationTests`, etc.) and let failures enumerate every fixture that needs updating.

## Running Frontend Tests
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

This runs `build-filtered.ps1` which shows only errors + summary (prevents context bloat).

If running `dotnet build` directly, output may be verbose — prefer the skill for cleaner results.

## Test Verification

For running backend tests, use the `/mstest` skill which runs the filtered test script:
```
/mstest
```

This runs `test-filtered.ps1` which shows only passed/failed tests, errors, and summary (prevents context bloat).

If running `dotnet test` directly, output may be verbose — prefer the skill for cleaner results.

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
