---
name: nxtest
description: Run frontend tests with filtered output (PASS/FAIL + errors only). Wraps client-test-filtered.ps1.
argument-hint: [-Project "project"] [-Pattern "path"] [-Filter "test name"] [-NoCoverage]
model: haiku
allowed-tools: ["Bash"]
---

# NxTest — Filtered Frontend Test Runner

Run frontend tests in the Nx monorepo showing only PASS/FAIL results, error details, and summary.

## Usage

- `/nxtest` — test cognito-spa (default)
- `/nxtest -Project "cognito-spa" -Pattern "Button"` — filter by file path
- `/nxtest -Project "@cognitoforms/model.js" -Filter "should render"` — filter by test name
- `/nxtest -NoCoverage` — skip coverage for faster runs

## Common Projects

`cognito-spa`, `cognito-client`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`

## Instructions

1. Construct the command:
   ```
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op nxtest -Exec "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1"
   ```

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Project "..."` — Nx project name (default: `cognito-spa`)
   - `-Pattern "..."` — testPathPattern (filter by file path)
   - `-Filter "..."` — testNamePattern (filter by test name)
   - `-NoCoverage` — skip coverage collection

3. Run the command using Bash with `timeout: 600000` (10 min). A test run can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast runs because Bash returns as soon as the command exits. Do not interpret or reformat the output. The invocation prints an authoritative one-line `build-queue: seq=<N> op=nxtest RESULT=<PASS|FAIL|NO-TESTS-MATCHED> tests=<T> failed=<F> (result_fidelity=...)` banner as its LAST stdout line — trust that line for the outcome. Do NOT `cat`/`grep` the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an `exit_code=0`. On `RESULT=NO-TESTS-MATCHED` widen the filter and retry; on `RESULT=FAIL` read `logs/<seq>.build.err.log`.

4. If the run is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead. The `build-queue: enqueued as seq=N` line it returns is NOT an outcome — never end your turn or report a result on it. Follow the run to its authoritative result with the await helper (foreground Bash, `timeout: 600000`):
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>
   ```
   It blocks until `results/<seq>.json` exists, re-emits the same authoritative `build-queue: seq=<N> op=nxtest RESULT=...` banner as its LAST stdout line, and exits with the run's exit code. On its distinct await-timeout exit (`124`, `result not yet present for seq=N`) the run is still going — re-run the helper or check `/build-queue-status`; NEVER treat a timeout as success, and do not hand-read `results/<seq>.json` instead.

   **Foreground-timeout recovery:** if a foreground run is killed by the 10-min Bash timeout before the banner prints, recover the seq from the `build-queue: enqueued as seq=N` line already in the output and run the same await helper — do NOT re-enqueue the run.
