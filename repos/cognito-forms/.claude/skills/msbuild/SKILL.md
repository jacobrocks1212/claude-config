---
name: msbuild
description: Build Cognito.sln with filtered output (errors + summary only). Wraps build-filtered.ps1.
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
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op msbuild -Exec "$REPO_ROOT/.claude/scripts/build-filtered.ps1"
   ```

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Project "..."` — build a single project (path relative to the repo root, e.g. `Cognito.Core/Cognito.Core.csproj`) instead of the whole `Cognito.sln`. Forward or back slashes both work. Same filtered output, still serialized through the queue.
   - `-Restore` — enable NuGet package restore before building
   - `-Test` — also run tests after building
   - `-TestProject "..."` — custom test project path (default: `Cognito.Forms.UnitTests/Cognito.Forms.UnitTests.csproj`)

3. Run the command using Bash with `timeout: 600000` (10 min). A full build can legitimately exceed the default 2-min Bash timeout; the higher ceiling costs nothing for fast builds because Bash returns as soon as the command exits. Do not interpret or reformat the output.

4. If the build is expected to exceed 10 minutes, run the same command with `run_in_background: true` instead, then poll its log and read `$HOME/.claude/state/build-queue/results/<seq>.json` (the `exit_code` field) for the outcome — the `seq` is printed in the `build-queue: enqueued as seq=N` line.
