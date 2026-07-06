---
kind: investigation
feature_id: build-queue-buildlogpath-child-scope-forces-no-output-fail
date: 2026-07-06
trigger: manual
status: root-cause-confirmed
investigated_commit: c90e2dbccbea15c50724fceb9c3b430c5d078730
---

# Investigation — build-queue `$buildLogPath` child-scope discard forces `no-output` FAIL

## Symptom
`/msbuild` through the build queue reported `RESULT=FAIL (build_fidelity=no-output)`
→ banner "build produced no output; delete obj/bin and rebuild" on FOUR consecutive
genuinely-successful compiles this session (seq 707–710, 2026-07-06T12:16–12:26).

Exact on-disk evidence (all four identical):
- `results/<seq>.json`: `"exit_code":1` (FORCED — grandchild exited 0), `"build_fidelity":"no-output"`.
- `logs/<seq>.build.log`: **53 bytes**, populated, a SUCCESS log:
  ```
  Building solution...
  Build succeeded.
      0 Error(s)
  ```
- `logs/<seq>.build.err.log`: 0 bytes.
- `logs/<seq>.log` (runner stdout): the stray `True\n` (6 bytes) — a separate minor
  output-leak, not the cause.

## Root cause (CONFIRMED — a PowerShell variable-scope bug, none of T1/T2/T3)
`$buildLogPath` is assigned **inside a `Get-SafeValue { … }` scriptblock**, which
`Get-SafeValue` invokes via `& $Block` — a CHILD scope. A bare `$buildLogPath = …`
there creates a child-scope local and does NOT write through to the runner's
main-scope `$buildLogPath` (initialized `$null` at line 86). So at classify time the
outer `$buildLogPath` is still `$null`.

The redirect still works because `$startProcParams['RedirectStandardOutput'] = …` is a
**hashtable-index mutation** (reference type → propagates), so the grandchild's stdout
IS captured to the 53-byte file. But the classifier reads the **variable**, which is
`$null`, so it short-circuits on `[string]::IsNullOrWhiteSpace($buildLogPath)` and
**never reads the file**. `$script:buildLogTextForClassify` stays `$null` →
`Test-BuildProducedNoOutput($null)` returns `$true` → `build_fidelity='no-output'` →
forced `exit 1` / FAIL.

This is a sibling of the already-fixed `build-queue-hygiene-dot-source-discarded-in-child-scope`
(fixed 2026-07-06 2d9f8ae) — the SAME child-scope-discard class, a different variable that
that fix did not cover.

**Why now / why not caught for years:** the `$buildLogPath`-in-child-scope assignment is
from 2026-07-01 (bf31d55), but was harmless until the `no-output` gate landed 2026-07-03
(fd7a81a) — before that, a null classify-text only affected `Test-BuildLogFailure`, which
fails OPEN to non-failure. After fd7a81a, null classify-text means FAIL. The scope bug also
silently defeats the `log-failure-override` path (the parse block short-circuits before ever
reading real failure content), so the whole build-log-classification feature is inert; the
`no-output` branch is merely the one that fires (on null) and forces the false FAIL.

## Serving-path trace (root-cause-trace-gate artifact; file:line hops)
1. Banner text "build produced no output; delete obj/bin and rebuild"
   ← `Format-BuildQueueBanner` `build-queue-hygiene.ps1:1505-1506` (fires when
   `resultLabel != PASS` and `BuildFidelity -eq 'no-output'`); FAIL label set at
   `build-queue-hygiene.ps1:1480` because `ExitCode -ne 0`.
2. `build_fidelity='no-output'` + forced `exit 1` set at `build-queue-runner.ps1:178-180`.
3. That elseif fires because `Test-BuildProducedNoOutput -LogText $script:buildLogTextForClassify`
   is `$true` — `build-queue-runner.ps1:170`.
4. `Test-BuildProducedNoOutput($null)` → `$true` via `IsNullOrWhiteSpace` — `build-queue-hygiene.ps1:161`.
5. `$script:buildLogTextForClassify` is `$null` because the `Read-WithRetry` parse block
   short-circuited at `build-queue-runner.ps1:152` (`IsNullOrWhiteSpace($buildLogPath)` true)
   and never reached the `ReadAllText` + assignment at `:155-159`.
6. `$buildLogPath` is `$null` at `:152` because it was assigned in a `Get-SafeValue { }`
   CHILD scope at **`build-queue-runner.ps1:112`** (the DEFECT NODE) and the outer var from
   `:86` was never written. The redirect at `:113` works via hashtable mutation, so the file
   at `logs/<seq>.build.log` is correctly written — the classifier just never opens it.

`Read-WithRetry` default window: `MaxAttempts=3`, `DelayMs=50` (`build-queue-hygiene.ps1:91-93`)
= up to 3 reads, ≤100ms total settle (2 inter-attempt sleeps). Irrelevant here: the short-circuit
returns a non-null benign result on attempt 1, so no retry/settle ever runs.

`build-filtered.ps1` emit mechanism: `Write-Host` (`.claude/scripts/build-filtered.ps1:20,42-46,61`);
only 3 lines because `dotnet … -verbosity:minimal` output is filtered through a regex
(`build-filtered.ps1:29,37-48`) that emits only banner / error-count / build-status lines.

## Hypothesis Ledger
| hypothesis | origin | verdict | evidence |
|---|---|---|---|
| T1 flush/timing race (log not flushed at classify) | inherited | **refuted** | micro-repro: read IMMEDIATELY after `WaitForExit()` = 53 bytes; +300ms = 53 bytes. No empty-then-full transition; file is complete the instant the grandchild exits. |
| T2 `Write-Host` not captured by `-RedirectStandardOutput` | inherited | **refuted** | micro-repro child emits solely via `Write-Host`; redirected file = 53 bytes, exact content. `Start-Process -RedirectStandardOutput` DOES capture `Write-Host`. |
| T3 53-byte summary trips near-empty threshold | inherited | **refuted** | trimmed len 52 ≥ MinChars 40; and moot — classifier never reads the file. |
| Child-scope discard: `$buildLogPath` assigned in `Get-SafeValue{}` is `$null` in main scope at classify | this round | **confirmed** | micro-repro: after the `Get-SafeValue{ $buildLogPath=… }` block, outer `$buildLogPath`=`[]`, `IsNullOrWhiteSpace`=True, while the hashtable `RedirectStandardOutput` key IS set → classifier short-circuit = True (never reads). Matches all four seq 707–710 receipts. |

## Repro Recipe
Real (already captured, current at HEAD c90e2db): four receipts seq 707–710 in
`~/.claude/state/build-queue/{results,logs}/` — every one `build_fidelity:no-output`,
`exit_code:1`, over a 53-byte SUCCESS `.build.log`. The runner is unchanged since 2d5f…
(2d9f8ae, 2026-07-06 11:34) which predates the 12:16 run, so HEAD == the producing code.

Isolated deterministic micro-repro (touches no production script):
`scratchpad/repro.ps1` + `repro-child.ps1` replicate runner `:86` + `:106-116` + the
`WaitForExit`→read path exactly. Output:
```
outer $buildLogPath after Get-SafeValue block = []
IsNullOrWhiteSpace($buildLogPath) = True
RedirectStandardOutput key in hashtable = [...child.out.log]   # redirect OK
immediate read length = 53
delayed(+300ms) read length = 53
classifier short-circuits (never reads file) = True
```
Deterministic every run — not timing-dependent.

## Recommended Fix Scope
- **Repo:** claude-config only. `build-filtered.ps1` (Cognito repo) is CORRECT — `Write-Host`
  reaches the redirect; no Cognito-side change.
- **Fix site (on the traced path):** node 6 — `build-queue-runner.ps1:106-116`. Assign
  `$buildLogPath` in the runner's MAIN scope so the classifier at `:152` and
  `Test-BuildProducedNoOutput` at `:170` see the real path. Minimal options: compute the path
  at main scope and keep only `New-Item` inside the fail-open wrapper; or `$buildLogPath =
  Get-SafeValue { …; $p }` (return the path); or `$script:buildLogPath` (mirrors the existing
  `$script:buildLogTextForClassify` pattern already in the same block). Do NOT touch the
  `no-output` classifier logic or `Read-WithRetry` — they are correct; they were just fed `$null`.
- **Fix must NOT touch:** the test-op counts path (`:218-233`) — it recomputes `$testLogPath`
  locally inside its own scriptblock and is unaffected.
- **Post-fix verification the fix cycle owes:** re-run `/msbuild` on a clean solution in a
  Cognito worktree; assert `RESULT=PASS build_fidelity=verified` on exit-0; and add a runner
  `--test`-style / Pester assertion that after the `if ($isBuildOp){…}` block `$buildLogPath`
  is non-null. Also re-verify the `log-failure-override` path now actually reads real failure
  content (it was co-defeated by this scope bug).

## Blast Radius
- **Build ops only** (`/msbuild`, `/nxbuild`) — the classify block is gated `if ($isBuildOp)`
  (`:137`). Test ops (`/mstest`, `/nxtest`) derive fidelity from exit code and use a
  self-contained log path, so they are unaffected. Verified by the four all-`build` receipts.
- **Deterministic, every successful build op** (not intermittent). A genuinely-FAILING build
  (exit≠0) still reports FAIL correctly (via exit code, not the log gate), so the bug is
  purely a false-RED on success. Regression window: 2026-07-03 (fd7a81a) → present.
- Severity: high-friction (every clean build op reads as FAIL, and the queue's entire
  build-log-honesty feature — both `no-output` and `log-failure-override` — is inert), but
  non-destructive.
