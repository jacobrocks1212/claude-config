### Cognito Forms Quality Gates

The Cognito backend build is slow, and a full `Cognito.sln` build (`/msbuild`) also triggers server-type generation and builds the Web/Services/Queue projects — almost always wasted work for a backend unit-test work unit. So gates are **tiered**: cheap, targeted, incremental builds while iterating; one authoritative full build at phase/part end.

#### Tier 1 — In-loop gate (intermediate batches: any batch that is NOT the last in the phase/part)

Build only the affected project, incrementally, then run filtered tests against the already-built output:

- **C# (backend unit tests):**
  - Build (incremental, no restore, test project only — NOT the solution):
    `dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" -c Debug --no-restore -v minimal --nologo`
  - Test (no rebuild, always filtered to the batch's class/area):
    `dotnet test "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.UnitTests\Cognito.UnitTests.csproj" -c Debug --no-build -v minimal --nologo --filter "FullyQualifiedName~<ClassUnderTest>"`
  - Do **not** build `Cognito.sln` and do **not** run `/msbuild` in Tier 1. `--no-restore` is safe after the first build of the session; if a brand-new package reference was added, drop `--no-restore` for that one build only.
- **Frontend:** targeted project test only — `/nxtest -Project "<project>" -Pattern "<path>" -NoCoverage` (or `npx nx test <project> -- --testPathPattern="<pattern>" --no-coverage`). Do **not** run `/nxbuild` in Tier 1 unless the batch changed generated/shared types.

**Do NOT re-run the C# suite as an independent orchestrator gate in Tier 1.** The implementation agent already pasted a verbatim `GROUND-TRUTH OUTPUT` test block (passed/failed counts) — that is the in-loop signal. Re-building + re-running the same filtered suite per batch just to confirm the agent's already-pasted result is the redundant build we are eliminating. Read the agent's `GROUND-TRUTH OUTPUT` block, diff it against the expected deliverables, and proceed. The authoritative orchestrator re-run happens once, at Tier 2.

When you compose implementation/test agent prompts, give them the **Tier 1 commands above** as their verification command (targeted `.csproj` + `--no-build` test) — not `/msbuild` or a full `Cognito.sln` build.

#### Tier 2 — Authoritative gate (phase/part completion — MANDATORY, 100% pass, no exceptions)

Before the phase/part is marked Complete, run the full authoritative gate once. This is the backstop that catches anything a Tier 1 targeted run or a (now-trusted) agent ground-truth block missed:

- **C# changes:** `/msbuild` (full `Cognito.sln` build) → `/mstest` (filtered to all touched test classes; never the whole unfiltered project per repo policy).
- **Frontend changes:** `/nxbuild` (touched projects) → `/nxtest` (touched projects).
- **Mixed:** run the C# pair then the frontend pair.

A **single-batch phase/part is the last batch by definition** → it runs the Tier 2 authoritative gate, not Tier 1.

#### Full-suite escalation (forces Tier 2 immediately, regardless of batch position)

If a batch changed server-side types the frontend consumes, added a field to a widely-constructed entity/type, renamed/re-exported a module, or otherwise tripped the escalation triggers in the generic quality-gates component, run the **Tier 2** gate for that batch immediately before it proceeds — including the full `Cognito.sln` build, since server-type generation must run.
