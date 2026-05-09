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
    Feature docs in `.claude.local/knowledge/features/`
  </knowledge-base>
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
