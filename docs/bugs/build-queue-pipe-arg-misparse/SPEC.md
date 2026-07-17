---
kind: bug
slug: build-queue-pipe-arg-misparse
written_by: harden-harness
date: 2026-07-17
status: Fixed
---

# Build Queue Silent Failure on Pipe-Containing Arguments

## Symptom

`build-queue.ps1` fails silently with zero diagnostic output when forwarding an argument containing pipe characters (`|`) to a filtered exec script (e.g., `client-test-filtered.ps1`). The run produces:
- stdout: only the exec script's header line (e.g., `Running tests for cognito-spa (pattern: ...)...`), no downstream tool output
- stderr: empty (0 lines)
- exit code: 1
- duration: ~19-20s (too fast for actual test execution)

## Verified Symptom — Repro

**Working patterns (individual):**
- `-Pattern "DocumentFieldSettings"` → PASS, full jest output captured, 10/10 tests
- `-Pattern "DocumentLockSettings"` → PASS, full jest output, 9/9 tests
- `-Pattern "RequireSigningBySelector"` → PASS, full jest output, 28/28 tests

**Failing pattern (combined):**
- `-Pattern "DocumentFieldSettings|DocumentLockSettings|RequireSigningBySelector"` → FAIL, zero output, empty logs, exit 1

**Command:**
```bash
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" \
  -Op nxtest \
  -Exec "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1" \
  -Project "cognito-spa" \
  -Pattern "DocumentFieldSettings|DocumentLockSettings|RequireSigningBySelector" \
  -NoCoverage
```

Produced: seq=1255 and seq=1256, both with identical empty-log failure signature.

## Root Cause — CONFIRMED

**File:** `~/.claude/scripts/build-queue.ps1`, lines 467–473

**Function:** `Format-ProcArg`

```powershell
function Format-ProcArg {
    param([string]$Value)
    if ($Value -eq '' -or $Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}
```

**The bug:** The regex pattern `[\s"]` (line 469) only matches whitespace and double quotes, **not pipe characters**. When an argument like `"DocumentFieldSettings|DocumentLockSettings|RequireSigningBySelector"` is passed to `Format-ProcArg`, it fails the regex check and is returned unquoted.

**Why this breaks:**

1. The unquoted pattern is added to `$procArgList` (line 488).
2. `$procArgList` is joined into a single string: `$procArgString = $procArgList -join ' '` (line 489).
3. This string is passed to `Start-Process -ArgumentList $procArgString` (line 492).
4. When `Start-Process` invokes `powershell.exe` with this argument list, PowerShell re-parses the string as a command line.
5. Any unquoted pipes in the string are interpreted as **pipe operators** (`|`), not as literal characters in the argument value.
6. The downstream command context is broken: instead of passing `--testPathPattern="DocumentFieldSettings|DocumentLockSettings|RequireSigningBySelector"` to Jest, the pipes are treated as shell operators, causing the command to fail silently.

**Why individual patterns work:** Arguments without special characters (or with only spaces, which are already handled) pass through correctly.

**Why the failure is silent:** The broken pipe context causes `npx` to receive an unexpected/malformed command, which exits with a cryptic failure; the filtered exec script (`client-test-filtered.ps1`) catches this via `$LASTEXITCODE` but outputs nothing because there's no Jest output to filter.

## Fix Scope

Update `Format-ProcArg` to quote any argument containing special PowerShell characters that could be misinterpreted as operators or escape sequences when the argument list is re-parsed by PowerShell. Specifically:
- Pipe characters: `|`
- Redirect operators: `>`, `<`
- Ampersand: `&`
- Semicolon: `;`
- Dollar sign: `$`
- Backtick: `` ` ``
- Parentheses: `()`, braces: `{}`

The safest approach: use a negative character class — quote anything that's **not** a safe alphanumeric + a minimal set of safe path/name characters (`A-Za-z0-9_./-:`).

This is a mechanical, targeted fix to the character-class regex in `Format-ProcArg`; no other changes to build-queue logic or runner behavior.
