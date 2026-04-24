# MSTest Command

Run backend tests with **filtered output** (passed/failed tests, errors, and summary only).

**IMPORTANT:** All commands below use `$REPO_ROOT` as a placeholder. Before running, resolve it:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

## Run All Unit Tests (Filtered)
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/test-filtered.ps1"
```

## Run with Filter
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -Filter "ClassName~MyTestClass"
```

## Run Integration Tests
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -TestDll "Cognito.Forms.UnitTests"
```

## Run Integration Tests with Filter
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -TestDll "Cognito.Forms.UnitTests" -Filter "ClassName~MyTestClass"
```

## Notes
- Runs with `--no-build` — build first with `/msbuild` if needed
- Output filtered to passed/failed test names, error messages, and summary only
- Filter syntax: `ClassName~Foo`, `Name~Bar`, `FullyQualifiedName~Baz`
- Default project: `Cognito.UnitTests`. Use `-TestDll` for other test projects
