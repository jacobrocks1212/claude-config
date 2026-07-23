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
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op mstest
   ```

   The `mstest` op is registered in this repo's ops manifest (`.claude/skill-config/build-queue-ops.json` — the queue's per-repo op registry), which is the authoritative source of the exec script (`test-filtered.ps1`). Do NOT pass `-Exec` — the manifest resolves it. (`-Exec` remains an optional override; a passed-or-manifest exec that does not exist now fails fast with a distinct `exec script not found` error before anything is enqueued.)

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Filter "..."` — MSTest filter expression
   - `-TestDll "..."` — test project name without extension (default: `Cognito.UnitTests`)

3. Run the command using Bash with `timeout: 600000` (10 min). A test run can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast runs because Bash returns as soon as the command exits. Do not interpret or reformat the output. The invocation prints an authoritative one-line `build-queue: seq=<N> op=mstest RESULT=<PASS|FAIL|NO-TESTS-MATCHED> tests=<T> failed=<F> (result_fidelity=...)` banner as its LAST stdout line — trust that line for the outcome. Do NOT `cat`/`grep` the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an `exit_code=0`. See the exit-code guidance below for the banner's next-actions.
ETA note: the enqueue echo and waiting-position lines may carry advisory predictions (`eta-start≈` / `eta-done≈`, `?` when history is cold) computed from recent run durations. They are predictions, never outcomes — the authoritative outcome remains the final `build-queue: ... RESULT=` banner line.


4. If the run is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead. The `build-queue: enqueued as seq=N` line it returns is NOT an outcome — never end your turn or report a result on it. Follow the run to its authoritative result with the await helper (foreground Bash, `timeout: 600000`):
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>
   ```
   It blocks until `results/<seq>.json` exists, re-emits the same authoritative `build-queue: seq=<N> op=mstest RESULT=...` banner as its LAST stdout line, and exits with the run's exit code. On its distinct await-timeout exit (`124`, `result not yet present for seq=N`) the run is still going — re-run the helper or check `/build-queue-status`; NEVER treat a timeout as success, and do not hand-read `results/<seq>.json` instead.

   **Foreground-timeout recovery:** if a foreground run is killed by the 10-min Bash timeout before the banner prints, recover the seq from the `build-queue: enqueued as seq=N` line already in the output and run the same await helper — do NOT re-enqueue the run.

## Log files: `<seq>.build.log` vs `<seq>.log`

Test-run output for this op lands in `~/.claude/state/build-queue/logs/<seq>.log`. But when a red run traces back to a build problem (e.g. the stale-DLL exit 4 below sends you to `/msbuild`), note that a **build** op's real transcript is that seq's `<seq>.build.log` (stderr: `<seq>.build.err.log`) — for build ops the sibling `<seq>.log` is the runner's own near-empty log, not the build output.

## Stale-DLL trap (--no-build)

Because this skill runs `--no-build`, a red result can be bogus if the DLL under test is stale — e.g. the last build silently lost a DLL copy race (MSB3027 copy-lock). `test-filtered.ps1` now guards against this: it emits a staleness WARN and exits **`4`** when the target test DLL is missing, predates its source (`.cs`/`.csproj`) files, or the last build's hygiene recorded `build_fidelity: log-failure-override`. (Other distinct exit codes: `1` = not in a git repo, `3` = zero test output captured, `5` = filter matched zero tests.)

**On the staleness WARN / exit 4 (banner `RESULT=FAIL`): rebuild with `/msbuild` before trusting a red.** A failing test against a stale DLL is not a real failure — rebuild, then re-run `/mstest`.

**On banner `RESULT=NO-TESTS-MATCHED` (exit 5): the filter matched zero tests — widen the `-Filter` and re-run.** A zero-match run is not a pass; the banner distinguishes it from a real all-pass (`result_fidelity=no-tests-matched` vs `verified`), so trust the banner rather than reading a bare `exit_code`.
