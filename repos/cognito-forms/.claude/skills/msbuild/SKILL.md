---
name: msbuild
description: Build Cognito.slnx with filtered output (errors + summary only). Wraps build-filtered.ps1.
argument-hint: [-Project "path/to.csproj"] [-Restore] [-Test] [-TestProject "path/to/test.csproj"]
model: haiku
allowed-tools: ["Bash"]
---

# MSBuild — Filtered .NET Build

Build the Cognito solution showing only errors and the build summary.

## Usage

- `/msbuild` — build the whole solution (no restore)
- `/msbuild -Project "Cognito.Core/Cognito.Core.csproj"` — fast single-project filtered build (still serialized through the queue); use this for a quick "did my change compile?" check instead of a full solution build
- `/msbuild -Restore` — build with NuGet package restore
- `/msbuild -Test` — build then run tests
- `/msbuild -Restore -Test` — restore, build, and test

## Instructions

1. Construct the command:
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op msbuild
   ```

   The `msbuild` op is registered in this repo's ops manifest (`.claude/skill-config/build-queue-ops.json` — the queue's per-repo op registry), which is the authoritative source of the exec script (`build-filtered.ps1`). Do NOT pass `-Exec` — the manifest resolves it. (`-Exec` remains an optional override; a passed-or-manifest exec that does not exist now fails fast with a distinct `exec script not found` error before anything is enqueued, so a wrong path is never mistaken for a build failure.)

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Project "..."` — build a single project (path relative to the repo root, e.g. `Cognito.Core/Cognito.Core.csproj`) instead of the whole `Cognito.slnx`. Forward or back slashes both work. Same filtered output, still serialized through the queue.
   - `-Restore` — enable NuGet package restore before building
   - `-Test` — also run tests after building
   - `-TestProject "..."` — custom test project path (default: `Cognito.Forms.UnitTests/Cognito.Forms.UnitTests.csproj`)

3. Run the command using Bash with `timeout: 600000` (10 min). A full build can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast builds because Bash returns as soon as the command exits. Do not interpret or reformat the output. The invocation prints an authoritative one-line `build-queue: seq=<N> op=msbuild RESULT=<PASS|FAIL> (result_fidelity=...)` banner as its LAST stdout line — trust that line for the outcome. Do NOT `cat`/`grep` the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an `exit_code=0`. On `RESULT=FAIL` the banner names the next action inline — read `logs/<seq>.build.log` (the stdout transcript where MSBuild writes CS errors and `Build FAILED`; the sibling `logs/<seq>.build.err.log` stderr sidecar is typically empty), or `build produced no output; delete obj/bin and rebuild` on a `build_fidelity: no-output` false-green (see below), or the copy-lock case on `build_fidelity: log-failure-override` (see below).
ETA note: the enqueue echo and waiting-position lines may carry advisory predictions (`eta-start≈` / `eta-done≈`, `?` when history is cold) computed from recent run durations. They are predictions, never outcomes — the authoritative outcome remains the final `build-queue: ... RESULT=` banner line.


4. If the build is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead. The `build-queue: enqueued as seq=N` line it returns is NOT an outcome — never end your turn or report a result on it. Follow the run to its authoritative result with the await helper (foreground Bash, `timeout: 600000`):
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>
   ```
   It blocks until `results/<seq>.json` exists, re-emits the same authoritative `build-queue: seq=<N> op=msbuild RESULT=...` banner as its LAST stdout line, and exits with the build's exit code. On its distinct await-timeout exit (`124`, `result not yet present for seq=N`) the build is still running — re-run the helper or check `/build-queue-status`; NEVER treat a timeout as success, and do not hand-read `results/<seq>.json` instead.

   **Foreground-timeout recovery:** if a foreground run is killed by the 10-min Bash timeout before the banner prints, recover the seq from the `build-queue: enqueued as seq=N` line already in the output and run the same await helper — do NOT re-enqueue the build.

## Log files: `<seq>.build.log` vs `<seq>.log`

For build ops the real build transcript is `~/.claude/state/build-queue/logs/<seq>.build.log` (stderr: `<seq>.build.err.log`). The sibling `<seq>.log` is the queue runner's own log and is typically near-empty for a build op — reading it and concluding "the build produced no output" is a false diagnosis. When diagnosing a stale or failed build, read `<seq>.build.log`.

## Recognizing a copy-lock false-success

Under DLL copy-lock contention, `dotnet build` can log `Build FAILED` with `error MSB3027`/`error MSB3021` ("being used by another process") yet still exit 0 — a false success. The build queue detects this exited-0-but-FAILED case, overrides the exit to a failure, and records `build_fidelity: log-failure-override` in the per-build hygiene (visible via `/build-queue-status`).

The queue also auto-reaps leftover `testhost`/`dotnet` processes holding a `bin/Debug` DLL handle before the copy step, so a copy-lock should now self-heal. If one recurs anyway, check `/build-queue-status` for the per-build hygiene outcome (recycled / quarantined / build_fidelity / lockers_reaped) before manually killing anything. See the repo's `CLAUDE.local.md` "Build & Test Workflow" section for the full MSB3027/quarantine story.

## Recognizing a no-output false-green (`build_fidelity: no-output`)

A build can exit 0 while compiling nothing — the log is empty/near-empty and no artifact is produced. Scanning only for known failure signatures misses this, so such a build used to be reported as a clean PASS. The build queue now positively classifies it: an exit-0 build op whose captured log is missing / empty / whitespace-only / near-empty is forced to `RESULT=FAIL` with `build_fidelity: no-output` (visible via `/build-queue-status` as a red `[BUILD LIED - produced no output]`), and its poisoned artifacts are swept. Trust the banner — the corrective action is exactly what it names: **delete `obj`/`bin` and rebuild** (do NOT `cat` the runner or `results/<seq>.json` to second-guess it).
