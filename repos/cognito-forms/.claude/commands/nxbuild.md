# NxBuild Command

Build the frontend with **filtered output** (errors and summary only).

**IMPORTANT:** All commands below use `$REPO_ROOT` as a placeholder. Before running, resolve it:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

## Build Default Project (cognito-spa)
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-build-filtered.ps1"
```

## Build Specific Project
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-build-filtered.ps1" -Project "cognito-spa"
```

## Build All Projects
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-build-filtered.ps1" -All
```

## Build Specific Library
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/client-build-filtered.ps1" -Project "@cognitoforms/model.js"
```

## After Building

**Use `/nxtest` to run tests with filtered output.** The nxtest command provides the same filtered output for test results (PASS/FAIL, errors, summary only).

## Notes
- Output filtered to errors and build summary only (no verbose Nx/Rspack output)
- Common project names: `cognito-spa`, `cognito-client`, `@cognitoforms/model.js`, `@cognitoforms/vuemodel`
- Use `npx nx show projects` in Cognito.Web.Client to list all available projects
- For unfiltered output, run `npx nx build <project>` directly in a terminal
