---
name: msbuild
description: Build Cognito.sln with filtered output (errors + summary only). Wraps build-filtered.ps1.
argument-hint: [-Restore] [-Test] [-TestProject "path/to/test.csproj"]
model: haiku
allowed-tools: ["Bash"]
---

# MSBuild — Filtered .NET Build

Build the Cognito solution showing only errors and the build summary.

## Usage

- `/msbuild` — build solution (no restore)
- `/msbuild -Restore` — build with NuGet package restore
- `/msbuild -Test` — build then run tests
- `/msbuild -Restore -Test` — restore, build, and test

## Instructions

1. Construct the command:
   ```
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/build-filtered.ps1"
   ```

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Restore` — enable NuGet package restore before building
   - `-Test` — also run tests after building
   - `-TestProject "..."` — custom test project path (default: `Cognito.Forms.UnitTests/Cognito.Forms.UnitTests.csproj`)

3. Run the command using Bash. Do not interpret or reformat the output.
