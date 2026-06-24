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

3. Run the command using Bash. Do not interpret or reformat the output.
