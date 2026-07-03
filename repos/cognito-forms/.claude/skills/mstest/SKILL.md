---
name: mstest
description: Run backend tests with filtered output (pass/fail + errors only). Wraps test-filtered.ps1.
argument-hint: [-Filter "ClassName~Foo"] [-TestDll "Cognito.Forms.UnitTests"]
model: haiku
allowed-tools: ["Bash"]
---

# MSTest — Filtered .NET Test Runner

Run backend tests showing only passed/failed test names, error messages, and summary. Runs with `--no-build` — build first if needed. For a fast targeted compile of just the project under test, run `/msbuild -Project "<relative/path/to.csproj>"` before this (both stay serialized through the build queue).

## Usage

- `/mstest` — run all unit tests (Cognito.UnitTests — this is where ALL service/unit tests live)
- `/mstest -Filter "ClassName~MyTestClass"` — run filtered tests
- `/mstest -TestDll "Cognito.Forms.UnitTests"` — run Selenium/browser integration tests (NOT service tests)
- `/mstest -TestDll "Cognito.Forms.UnitTests" -Filter "ClassName~Foo"` — filtered browser tests

**Important:** `Cognito.UnitTests` contains all service-level tests (EntryIndexServiceTests, PersonSubmissionIndexingTests, ShouldInvalidateIndexTests, etc.). `Cognito.Forms.UnitTests` is only for Selenium browser tests. When in doubt, use the default (no `-TestDll` flag).

## Filter Syntax

MSTest filter expressions: `ClassName~Foo`, `Name~Bar`, `FullyQualifiedName~Baz`

## Instructions

1. Construct the command:
   ```
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op mstest -Exec "$REPO_ROOT/.claude/scripts/test-filtered.ps1"
   ```

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Filter "..."` — MSTest filter expression
   - `-TestDll "..."` — test project name without extension (default: `Cognito.UnitTests`)

3. Run the command using Bash with `timeout: 600000` (10 min). A test run can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast runs because Bash returns as soon as the command exits. Do not interpret or reformat the output. The invocation prints an authoritative one-line `build-queue: seq=<N> op=mstest RESULT=<PASS|FAIL|NO-TESTS-MATCHED> tests=<T> failed=<F> (result_fidelity=...)` banner as its LAST stdout line — trust that line for the outcome. Do NOT `cat`/`grep` the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an `exit_code=0`. See the exit-code guidance below for the banner's next-actions.

4. If the run is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead, then poll its log and read `$HOME/.claude/state/build-queue/results/<seq>.json` (the `exit_code` field) for the outcome — the `seq` is printed in the `build-queue: enqueued as seq=N` line.

## Stale-DLL trap (--no-build)

Because this skill runs `--no-build`, a red result can be bogus if the DLL under test is stale — e.g. the last build silently lost a DLL copy race (MSB3027 copy-lock). `test-filtered.ps1` now guards against this: it emits a staleness WARN and exits **`4`** when the target test DLL is missing, predates its source (`.cs`/`.csproj`) files, or the last build's hygiene recorded `build_fidelity: log-failure-override`. (Other distinct exit codes: `1` = not in a git repo, `3` = zero test output captured, `5` = filter matched zero tests.)

**On the staleness WARN / exit 4 (banner `RESULT=FAIL`): rebuild with `/msbuild` before trusting a red.** A failing test against a stale DLL is not a real failure — rebuild, then re-run `/mstest`.

**On banner `RESULT=NO-TESTS-MATCHED` (exit 5): the filter matched zero tests — widen the `-Filter` and re-run.** A zero-match run is not a pass; the banner distinguishes it from a real all-pass (`result_fidelity=no-tests-matched` vs `verified`), so trust the banner rather than reading a bare `exit_code`.
