# MSBuild Command

Build the Cognito solution with **filtered output** (errors and summary only).

**IMPORTANT:** All commands below use `$REPO_ROOT` as a placeholder. Before running, resolve it:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

## Build Solution (Filtered)
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/build-filtered.ps1"
```

## Build with NuGet Restore
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/build-filtered.ps1" -Restore
```

## Build and Run Tests
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/build-filtered.ps1" -Test
```

## Full Combo (Restore + Build + Test)
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/build-filtered.ps1" -Restore -Test
```

## After Building

**Use `/mstest` to run tests with filtered output.** The mstest command provides the same filtered output for test results (passed/failed tests, errors, summary only).

## Notes
- Output filtered to errors and build summary only (no warnings, no project output)
- Use the wrapper script above to prevent context bloat
- For unfiltered output, run MSBuild directly in a terminal
