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

3. Run the command using Bash with `timeout: 600000` (10 min). A test run can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast runs because Bash returns as soon as the command exits. Do not interpret or reformat the output.

4. If the run is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead, then poll its log and read `$HOME/.claude/state/build-queue/results/<seq>.json` (the `exit_code` field) for the outcome — the `seq` is printed in the `build-queue: enqueued as seq=N` line.
