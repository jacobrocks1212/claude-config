### Cognito Forms Quality Gates

The Cognito backend build is slow, and a full `Cognito.sln` build (`/msbuild`) also triggers server-type generation and builds the Web/Services/Queue projects — almost always wasted work for a backend unit-test work unit. So gates are **tiered**: cheap, targeted, incremental builds while iterating; one authoritative full build at part end.

#### Tier 1 — In-loop gate (any batch that is NOT the last in the plan part)

Build only the affected project, incrementally, then run filtered tests against the already-built output:

All build/test runs route through the queue skills (`/msbuild` `/mstest` `/nxbuild` `/nxtest`) — they serialize machine-globally and emit filtered output. Never run raw `dotnet`/`npx nx`.

- **C# (backend unit tests):**
  - Build (incremental, single project — NOT the full solution):
    `/msbuild -Project "Cognito.UnitTests/Cognito.UnitTests.csproj"`
  - Test (no rebuild, always filtered to the batch's class/area):
    `/mstest -Filter "ClassName~<ClassUnderTest>"`
  - Do **not** run a full-solution `/msbuild` (no `-Project`) in Tier 1. The `-Project` form is the sanctioned incremental build path.
- **Frontend:** targeted project test only — `/nxtest -Project "<project>" -Pattern "<path>" -NoCoverage`. Do **not** run `/nxbuild` in Tier 1 unless the batch changed generated/shared types.

**Orchestrator re-runs in Tier 1 are limited to the review protocol's ground-truth verification** — re-running the equivalent filtered `/mstest -Filter …` (or `/nxtest`) once per work unit/lane to detect falsified reports (PASS/FAIL comparison, not byte-identical output). `/mstest` is already `--no-build`, so the re-run is cheap and required. What is forbidden in Tier 1: rebuilding, running broader filters than the agent used, or running additional independent test passes "to be sure". The authoritative orchestrator gate happens once, at Tier 2.

When you compose implementation/test agent prompts, give them the **Tier 1 skill commands above** as their verification commands (`/msbuild -Project "…"` + `/mstest -Filter …` / `/nxtest …`) — never raw `dotnet`/`npx nx` and never a full-solution `/msbuild`.

#### Server-type regeneration does NOT require a full build

`generate-server-types.ps1` reflects over already-built DLLs in `Cognito.Services/bin` — it compiles nothing itself. To regenerate types mid-plan after backend contract changes:

1. `/msbuild -Project "Cognito.Services/Cognito.Services.csproj"` (incremental — transitively rebuilds Core/Cognito only as needed; queue-serialized + filtered)
2. `powershell.exe -Command "cd 'C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client\libs\types\typegen'; ./generate-server-types.ps1 -UpdateInPlace"`
3. Review `git diff -- "Cognito.Web.Client/libs/types/server-types/"` against the backend contract changes.

Use the single-project `/msbuild -Project "…"` form, NOT a full-solution `/msbuild` — a full build is wasted work for type regeneration.

#### Tier 2 — Authoritative gate (plan-part completion — MANDATORY, 100% pass, no exceptions)

Before a plan part is reported complete (or, for skills that don't partition into parts, before the final phase is marked done), run the full authoritative gate once. This is the backstop that catches anything a Tier 1 targeted run or a (now-trusted) agent ground-truth block missed — including compile breaks in projects off the incremental chain (Queue projects, test projects):

- **C# changes:** `/msbuild` (full `Cognito.sln` build) → `/mstest` (filtered to all touched test classes; never the whole unfiltered project per repo policy).
- **Frontend changes:** `/nxbuild` (touched projects) → `/nxtest` (touched projects).
- **Mixed:** run the C# pair then the frontend pair.
- After a full build, check `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` — a new diff means an earlier typegen run missed something; reconcile it before declaring the gate green.

A **single-batch part is the last batch by definition** → it runs the Tier 2 authoritative gate, not Tier 1.

#### Full-suite escalation (forces Tier 2 immediately, regardless of batch position)

If a batch changed server-side types the frontend consumes (beyond what an in-loop typegen run already reconciled), added a field to a widely-constructed entity/type, renamed/re-exported a module, or otherwise tripped the escalation triggers in the generic quality-gates component, run the **Tier 2** gate for that batch immediately before it proceeds — including the full `Cognito.sln` build.
