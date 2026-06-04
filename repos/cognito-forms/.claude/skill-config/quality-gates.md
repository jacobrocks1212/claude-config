### Cognito Forms Quality Gates

The Cognito backend build is slow, and a full `Cognito.sln` build (`/msbuild`) also triggers server-type generation and builds the Web/Services/Queue projects — almost always wasted work for a backend unit-test work unit. So gates are **tiered**: cheap, targeted, incremental builds while iterating; one authoritative full build at part end.

#### Tier 1 — In-loop gate (any batch that is NOT the last in the plan part)

Build only the affected project, incrementally, then run filtered tests against the already-built output:

- **C# (backend unit tests):**
  - Build (incremental, no restore, test project only — NOT the solution):
    `dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" -c Debug --no-restore -v minimal --nologo`
  - Test (no rebuild, always filtered to the batch's class/area):
    `dotnet test "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" -c Debug --no-build -v minimal --nologo --filter "FullyQualifiedName~<ClassUnderTest>"`
  - Do **not** build `Cognito.sln` and do **not** run `/msbuild` in Tier 1. `--no-restore` is safe after the first build of the session; if a brand-new package reference was added, drop `--no-restore` for that one build only.
- **Frontend:** targeted project test only — `/nxtest -Project "<project>" -Pattern "<path>" -NoCoverage` (or `npx nx test <project> -- --testPathPattern="<pattern>" --no-coverage`). Do **not** run `/nxbuild` in Tier 1 unless the batch changed generated/shared types.

**Orchestrator re-runs in Tier 1 are limited to the review protocol's ground-truth verification** — re-running the agent's pasted, filtered `--no-build` test command once per work unit/lane to detect falsified reports. That re-run is cheap and required. What is forbidden in Tier 1: rebuilding, running broader filters than the agent used, or running additional independent test passes "to be sure". The authoritative orchestrator gate happens once, at Tier 2.

When you compose implementation/test agent prompts, give them the **Tier 1 commands above** as their verification command (targeted `.csproj` + `--no-build` test) — not `/msbuild` or a full `Cognito.sln` build.

#### Server-type regeneration does NOT require a full build

`generate-server-types.ps1` reflects over already-built DLLs in `Cognito.Services/bin` — it compiles nothing itself. To regenerate types mid-plan after backend contract changes:

1. `dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Services\Cognito.Services.csproj" -c Debug --no-restore -v minimal --nologo` (incremental — transitively rebuilds Core/Cognito only as needed)
2. `powershell.exe -Command "cd 'C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client\libs\types\typegen'; ./generate-server-types.ps1 -UpdateInPlace"`
3. Review `git diff -- "Cognito.Web.Client/libs/types/server-types/"` against the backend contract changes.

Do NOT run `/msbuild` just to regenerate types.

#### Tier 2 — Authoritative gate (plan-part completion — MANDATORY, 100% pass, no exceptions)

Before a plan part is reported complete (or, for skills that don't partition into parts, before the final phase is marked done), run the full authoritative gate once. This is the backstop that catches anything a Tier 1 targeted run or a (now-trusted) agent ground-truth block missed — including compile breaks in projects off the incremental chain (Queue projects, test projects):

- **C# changes:** `/msbuild` (full `Cognito.sln` build) → `/mstest` (filtered to all touched test classes; never the whole unfiltered project per repo policy).
- **Frontend changes:** `/nxbuild` (touched projects) → `/nxtest` (touched projects).
- **Mixed:** run the C# pair then the frontend pair.
- After a full build, check `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` — a new diff means an earlier typegen run missed something; reconcile it before declaring the gate green.

A **single-batch part is the last batch by definition** → it runs the Tier 2 authoritative gate, not Tier 1.

#### Full-suite escalation (forces Tier 2 immediately, regardless of batch position)

If a batch changed server-side types the frontend consumes (beyond what an in-loop typegen run already reconciled), added a field to a widely-constructed entity/type, renamed/re-exported a module, or otherwise tripped the escalation triggers in the generic quality-gates component, run the **Tier 2** gate for that batch immediately before it proceeds — including the full `Cognito.sln` build.
