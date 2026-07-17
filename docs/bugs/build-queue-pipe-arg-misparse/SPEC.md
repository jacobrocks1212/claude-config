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

## CORRECTED Root Cause — CONFIRMED via direct repro

The `Format-ProcArg` finding above was **necessary but not sufficient**. A peer re-ran the exact repro after the `Format-ProcArg` fix landed and it still failed identically (seq=1259). Direct reproduction then isolated the true breakage point.

**Instrumented repro (from `Cognito.Web.Client`, `& npx nx test cognito-spa -- --testPathPattern=DocumentFieldSettings|DocumentLockSettings ...`) captured this decisive output:**

```
> nx run cognito-spa:test --testPathPattern=DocumentFieldSettings|DocumentLockSettings --no-coverage --listTests
'DocumentLockSettings' is not recognized as an internal or external command,
operable program or batch file.
NX   Running target test for project cognito-spa ... failed
```

**What actually happens:**

1. From PowerShell, `& npx` resolves to `npx.ps1` (verified: `npx.ps1:29 & $NODE_EXE $NPX_CLI_JS $args`), which invokes `node.exe` directly — there is **no cmd.exe hop at the first (npx) hop**.
2. nx receives the `--testPathPattern=A|B|C` argument **intact** (it echoes the full pattern in its `> nx run ...` display line).
3. nx then spawns the **jest executor as a child process through a shell (`cmd.exe`) on Windows**. A bare `|` on *that* inner command line is interpreted by cmd.exe as a **pipe operator**, splitting the command — so `DocumentLockSettings ...` is treated as a second command to pipe into, and cmd.exe reports `'DocumentLockSettings' is not recognized as an internal or external command`.
4. The task exits near-instantly (~8-20s) with no jest ever running the intended files, hence the empty log + `counts:null` + exit 1.

**Why embedded quotes did not save it:** the original client script already built `--testPathPattern="$Pattern"` with embedded double-quotes. Those quotes do not survive the full PowerShell 5.1 → npx → node → nx → cmd.exe relay: PowerShell 5.1 does not properly escape embedded quotes when marshalling arguments to native commands (the pre-7.3 argument-passing limitation), so the quotes are stripped before nx re-serializes to its jest child, re-exposing the bare pipe.

## Fix Scope — TWO parts

**Part 1 (build-queue arg relay — necessary, landed first):** `Format-ProcArg` in BOTH `user/scripts/build-queue.ps1` and `user/scripts/build-queue-runner.ps1` used regex `[\s"]`, failing to quote pipes when re-emitting the argument string for `Start-Process powershell.exe`. Fixed to a whitelist character class `^[A-Za-z0-9_./:=-]*$` (quote anything not purely safe path/name chars). This correctly delivers the literal `|` pattern value through the build-queue → runner → client hops.

**Part 2 (the actual silent-failure fix):** `repos/cognito-forms/.claude/scripts/client-test-filtered.ps1` — split the `-Pattern` value on `|` and pass each fragment as a **separate positional jest argument** instead of a single `--testPathPattern="A|B|C"`. Jest treats multiple positional arguments as testPathPattern regexes combined with OR, so this is semantically identical to the alternation regex while keeping every command-line argument free of shell-hostile characters — nothing for nx's jest-spawn cmd.exe to misinterpret. A pattern with no `|` yields a single positional arg (equivalent to the prior `--testPathPattern` behavior). The `-Filter`/`--testNamePattern` path is left unchanged (out of scope; only `-Pattern` was affected).

**Secondary (banner hint):** `Format-BuildQueueBanner` in `user/scripts/build-queue-hygiene.ps1` printed `-> read logs/<seq>.build.err.log` on any non-PASS, but the runner writes the `.build.` capture only for build ops; test ops (mstest/nxtest) have only `<seq>.log`/`<seq>.err.log`. Made the hint op-aware (build ops → `.build.err.log`, else → `.err.log`).

## Verification

Exact operator repro re-run via build-queue (seq=1260):
```
PASS src/views/build/DocumentLockSettings.unit.ts
PASS src/views/build/DocumentFieldSettings.unit.ts
PASS src/views/build/RequireSigningBySelector.unit.ts
Test Suites: 3 passed, 3 total
Tests:       47 passed, 47 total
Ran all test suites matching /DocumentFieldSettings|DocumentLockSettings|RequireSigningBySelector/i.
build-queue: seq=1260 op=nxtest RESULT=PASS (result_fidelity=verified)
```
All three files matched, 47 tests passed (10+9+28 — matching the sum of the individual-pattern runs), full jest tree printed, genuine PASS. The silent-empty-log failure is eliminated.
