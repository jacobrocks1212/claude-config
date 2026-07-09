---
name: nxbuild
description: Build frontend projects with filtered output (errors + summary only). Wraps client-build-filtered.ps1.
argument-hint: [-Project "project-name"] [-All] [-Targets "build","lint"]
model: haiku
allowed-tools: ["Bash"]
---

# NxBuild — Filtered Frontend Build

Build frontend projects in the Nx monorepo showing only errors and build summary.

## Usage

- `/nxbuild` — build cognito-spa (default)
- `/nxbuild -Project "cognito-client"` — build specific project
- `/nxbuild -Project "@cognitoforms/model.js"` — build a library
- `/nxbuild -All` — build all projects

## Common Projects

`cognito-spa`, `cognito-client`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`

## Instructions

1. Construct the command:
   ```
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op nxbuild -Exec "$REPO_ROOT/.claude/scripts/client-build-filtered.ps1"
   ```

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Project "..."` — specific Nx project name
   - `-All` — build all projects
   - `-Targets "build","lint"` — custom target list (default: `build`)

3. Run the command using Bash with `timeout: 600000` (10 min). A build can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast builds because Bash returns as soon as the command exits. Do not interpret or reformat the output. The invocation prints an authoritative one-line `build-queue: seq=<N> op=nxbuild RESULT=<PASS|FAIL> (result_fidelity=...)` banner as its LAST stdout line — trust that line for the outcome. Do NOT `cat`/`grep` the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an `exit_code=0`. On `RESULT=FAIL` the banner names the next action inline — read `logs/<seq>.build.err.log`, or `build produced no output; delete obj/bin and rebuild` on a `build_fidelity: no-output` false-green (see below).

4. If the build is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead. The `build-queue: enqueued as seq=N` line it returns is NOT an outcome — never end your turn or report a result on it. Follow the run to its authoritative result with the await helper (foreground Bash, `timeout: 600000`):
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>
   ```
   It blocks until `results/<seq>.json` exists, re-emits the same authoritative `build-queue: seq=<N> op=nxbuild RESULT=...` banner as its LAST stdout line, and exits with the build's exit code. On its distinct await-timeout exit (`124`, `result not yet present for seq=N`) the build is still running — re-run the helper or check `/build-queue-status`; NEVER treat a timeout as success, and do not hand-read `results/<seq>.json` instead.

   **Foreground-timeout recovery:** if a foreground run is killed by the 10-min Bash timeout before the banner prints, recover the seq from the `build-queue: enqueued as seq=N` line already in the output and run the same await helper — do NOT re-enqueue the build.

## Recognizing a no-output false-green (`build_fidelity: no-output`)

A build can exit 0 while compiling nothing — the captured log is empty/near-empty and no artifact is produced. Scanning only for known failure signatures misses this, so such a build used to report a clean PASS. The build queue now positively classifies it: an exit-0 build op whose captured log is missing / empty / whitespace-only / near-empty is forced to `RESULT=FAIL` with `build_fidelity: no-output` (surfaced via `/build-queue-status` as a red `[BUILD LIED - produced no output]`). Trust the banner — the corrective action is exactly what it names: **delete `obj`/`bin` and rebuild** (do NOT `cat` the runner script or `results/<seq>.json` to second-guess an `exit_code=0`).
