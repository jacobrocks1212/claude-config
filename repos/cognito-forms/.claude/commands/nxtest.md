# NxTest Command

Run frontend tests with **filtered output** (PASS/FAIL, errors, and summary only).

**IMPORTANT:** All commands below use `$REPO_ROOT` as a placeholder. Before running, resolve it:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

## Run Tests for Default Project (cognito-spa)
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1"
```

## Run Tests for Specific Project
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1" -Project "cognito-spa"
```

## Run with Path Pattern
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1" -Project "cognito-spa" -Pattern "Button"
```

## Run with Test Name Filter
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1" -Project "cognito-spa" -Filter "should render"
```

## Run Without Coverage (Faster)
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1" -Project "@cognitoforms/model.js" -NoCoverage
```

## Notes
- Output filtered to PASS/FAIL test names, error messages, and summary only
- `-Pattern` maps to Jest's `--testPathPattern` (filters by file path)
- `-Filter` maps to Jest's `--testNamePattern` (filters by test name)
- `-FailureLines` controls max error detail lines per failure (default: 10)
- Common project names: `cognito-spa`, `cognito-client`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`
- For unfiltered output, run `npx nx test <project>` directly in a terminal
