---
name: mstest
description: Run backend tests with filtered output (pass/fail + errors only). Wraps test-filtered.ps1.
argument-hint: [-Filter "ClassName~Foo"] [-TestDll "Cognito.Forms.UnitTests"]
model: haiku
allowed-tools: ["Bash"]
---

# MSTest — Filtered .NET Test Runner

Run backend tests showing only passed/failed test names, error messages, and summary. Runs with `--no-build` — build first with `/msbuild` if needed.

## Usage

- `/mstest` — run all unit tests (Cognito.UnitTests — this is where ALL service/unit tests live)
- `/mstest -Filter "ClassName~MyTestClass"` — run filtered tests
- `/mstest -TestDll "Cognito.Forms.UnitTests"` — run Selenium/browser integration tests (NOT service tests)
- `/mstest -TestDll "Cognito.Forms.UnitTests" -Filter "ClassName~Foo"` — filtered browser tests

**Important:** `Cognito.UnitTests` contains all service-level tests (EntryIndexServiceTests, PersonSubmissionIndexingTests, ShouldInvalidateIndexTests, etc.). `Cognito.Forms.UnitTests` is only for Selenium browser tests. When in doubt, use the default (no `-TestDll` flag).

## Filter Syntax

MSTest filter expressions: `ClassName~Foo`, `Name~Bar`, `FullyQualifiedName~Baz`

## Instructions

1. Construct the command:
   ```
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$REPO_ROOT/.claude/scripts/test-filtered.ps1"
   ```

2. If `$ARGUMENTS` is provided, append it verbatim to the command. The script accepts:
   - `-Filter "..."` — MSTest filter expression
   - `-TestDll "..."` — test project name without extension (default: `Cognito.UnitTests`)

3. Run the command using Bash. Do not interpret or reformat the output.
