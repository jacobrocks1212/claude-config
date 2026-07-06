# Build-queue hygiene dot-source runs in a discarded child scope — every hygiene function is undefined in both scripts — Investigation Spec

> Both `build-queue.ps1` (`:47-49`) and `build-queue-runner.ps1` (`:66-68`) load their shared helpers with `Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }`. `Get-SafeValue` invokes its block via `& $Block`, which runs in a **child scope**; dot-sourcing inside that child scope defines every hygiene function into the child scope, which is then discarded. So `Format-BuildQueueBanner`, `New-BuildJobObject`, `Add-ProcessToBuildJob`, `Stop-BuildJobTree`, `Reset-CompilerServer`, `Get-BuildQueueOccupancy`, `Read-WithRetry`, `Test-BuildLogFailure`, `Stop-DllLockers` — **all of it** — are undefined in the actual script scope of both callers. In the runner, the first undefined-function call (`New-BuildJobObject`) throws `CommandNotFoundException` under `$ErrorActionPreference='Stop'` + `Set-StrictMode`; the `trap`/`continue` abandons the rest of the `try`, so `$proc.WaitForExit()` is **skipped** and the runner exits in ~2s with the real build orphaned and still compiling. In the wrapper, the same undefined `Format-BuildQueueBanner` throws inside the fault-swallowing `Get-SafeValue` at Step 5, so the banner is **silently never printed**. This one bug is the common cause of: "the banner didn't print", the premature/verdict-less `results/<seq>.json`, the wasted re-runs, the broken machine-global one-build-at-a-time invariant, and the complete silent no-op of all build hygiene (VBCSCompiler recycle, Job-Object descendant reap, poisoned-DLL quarantine, fidelity classification) in production.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-06
**Placement:** docs/bugs/build-queue-hygiene-dot-source-discarded-in-child-scope
**Related:** `docs/bugs/build-queue-outcome-opacity-and-inspect-deny/` (added `Format-BuildQueueBanner` + `build_fidelity`/`result_fidelity` — all of which have been silently no-op in production because of this scoping bug); `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/` (result *absent* on wrapper kill — a distinct failure, but the orphaned-build half here overlaps its "outcome-recording on the detached child" concern); `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build/` (its `Get-BuildQueueOccupancy` occupancy gate is one of the functions rendered undefined here); `docs/specs/build-queue/`; `user/scripts/build-queue.ps1`; `user/scripts/build-queue-runner.ps1`; `user/scripts/build-queue-status.ps1`; `user/scripts/build-queue-hygiene.ps1`; `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest,build-queue-status}/SKILL.md`

<!-- Status lifecycle:
  - Investigating → root cause not yet proven.
  - Concluded     → root cause proven, affected area + fix scope understood; ready for /plan-bug.
-->
<!-- RESCOPED 2026-07-06: this bug was originally filed as `build-queue-verdict-not-persisted-to-result`,
     locking "the verdict is computed only in stdout, never persisted to results/<seq>.json" as root cause.
     An isolated runtime repro (see Runtime Evidence) REFUTED that as the cause: the verdict-less result file
     is a downstream SYMPTOM of the runner trapping out before it writes its rich result. The real, traced
     cause is the dot-source-in-child-scope bug below. The old lock violated the root-cause-trace-gate's
     symptom-verified ≠ cause-traced distinction; this rescope relocks on the traced cause. -->

---

## Verified Symptoms

<!-- Screenshot #1 evidence + the isolated runtime repro (subagent, 2026-07-06). -->

1. **[VERIFIED]** A `/nxbuild` invocation printed `enqueued as seq=688` → `waiting to claim slot...` → `build started (pid=…, seq=688, log=…\688.log)` and then the wrapper's Bash call **returned with no `RESULT` banner**. *(User screenshot #1; reproduced in isolation.)*
2. **[VERIFIED]** Polling `results/688.json` returned the **bare 3-field fallback** `{seq, exit_code:0, ended_at}` — no verdict, no `counts`, no `hygiene` — with a 0-byte log. `exit_code=0` was not trustworthy as PASS. *(User screenshot #1; reproduced — the repro's `results/1.json` was byte-shape-identical.)*
3. **[VERIFIED]** With no authoritative verdict from either the (absent) banner or the (bare) result file, the agent **re-ran the entire `nxbuild`** — wasted work on an expensive build; the thrashing eventually forced a compaction. *(User screenshot #1; user confirmed "wasted work"; mined session `f13805a3…` confirmed the re-run + compaction.)*
4. **[VERIFIED]** "The banner didn't print" recurs across **multiple** live Cognito sessions, on essentially **every** build — not an intermittent race. *(User report; consistent with the deterministic cause below.)*
5. **[VERIFIED — cause `traced`]** The root cause is a **PowerShell dot-source scoping bug**: hygiene functions are defined into a discarded child scope and are undefined in both scripts' actual scope. Necessary and sufficient — proven by isolated repro + minimal isolation + verified fix. *(Runtime Evidence below.)*

## Reproduction Steps

1. From a Cognito worktree, invoke the queue for any build (e.g. `/nxbuild`), synchronously (default).
2. Observe: the wrapper prints up to `build started (pid=…)`, then returns in ~1-2s (not after the real build finishes) with **exit 0 and no `RESULT` banner**.
3. Read `results/<seq>.json`: it is the bare `{seq, exit_code:0, ended_at}` fallback (no `counts`/`hygiene`), written while the actual build is still compiling.
4. Confirm the machine-global invariant is broken: `active.lock` for that seq is gone within ~2s while the build's grandchild process is still running (orphaned).

**Minimal cause isolation** (no build queue needed):
```powershell
. .\build-queue-hygiene.ps1;              (Get-Command New-BuildJobObject -EA SilentlyContinue) -ne $null   # -> True
function Get-SafeValue { param($b) try { & $b } catch {} }
Get-SafeValue { . .\build-queue-hygiene.ps1 }; (Get-Command New-BuildJobObject -EA SilentlyContinue) -ne $null   # -> False  ← the bug
```

**Expected:** Hygiene functions are defined in each script's scope; the runner waits for the real build (`WaitForExit`), writes the rich verdict-bearing result, and the wrapper prints the `RESULT` banner as its last stdout line.
**Actual:** Hygiene functions are undefined; the runner traps out before `WaitForExit`, the result is the premature bare fallback, and the banner call silently throws-and-swallows.
**Consistency:** Deterministic — the scope discard happens on every invocation of both scripts.

## Evidence Collected

### Source Code

**The defect (both callers, identical shape).**
- `build-queue.ps1:42-45` defines `Get-SafeValue { param([scriptblock]$Block, $Fallback=$null) try { & $Block } catch { $Fallback } }` — note `& $Block`, a **child-scope** invocation.
- `build-queue.ps1:47-49` — `Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }`. The dot-source runs inside the `& $Block` child scope, so every function it defines lands in that scope and is discarded on return. Nothing reaches the wrapper's script scope.
- `build-queue-runner.ps1:61-64` / `:66-68` — byte-identical `Get-SafeValue` definition and the same wrapped dot-source. Same discard.
- `build-queue-status.ps1:21-24` / `:31` — **third instance** (found by the blast-radius sweep). Same `Get-SafeValue { . hygiene.ps1 }`. Its only hygiene consumer is `Get-HygieneHighlight` (called at `:189`), so the per-build status highlight (e.g. the red `[BUILD LIED - produced no output]`) is **undefined on every run** and silently degrades to a plain line. The `:26-30` comment anticipates this only "on a load error" — in reality the scope discard makes it the *permanent* state.

**Runtime cascade — symptom → source, each hop `file:line`:**

```
RUNNER (build-queue-runner.ps1), $ErrorActionPreference='Stop' + Set-StrictMode -Version Latest:
  :66-68  Get-SafeValue { . hygiene.ps1 }        ← functions defined into discarded child scope
  :88-91  trap { Get-SafeValue { Stop-BuildJobTree … }; continue }
  :93     try {
  :125      $proc = Start-Process @startProcParams   ← grandchild build launches OK (no hygiene needed)
  :128      $job = New-BuildJobObject                ← CommandNotFoundException (undefined) → TERMINATING under Stop
             → trap fires → `continue` abandons the rest of the try block
  :133      $proc.WaitForExit()                      ← SKIPPED  (runner never waits for the build)
  :244-257  resultBody = { seq, exit_code, ended_at, counts, hygiene{…} }  ← NEVER REACHED
        runner falls out & exits ~2s, exit 0, build orphaned + still compiling

WRAPPER (build-queue.ps1):
  :377    while (-not $proc.HasExited) { tail }      ← tracks the RUNNER, which really exited at ~2s → loop ends correctly (this is NOT an early-return bug)
  :429-444  read-merge OR bare fallback { seq, exit_code:0, ended_at }  ← runner's rich file never existed → bare fallback written (matches seq=688)
  :455-472  Get-SafeValue { … Read-WithRetry … Remove-Item $activeLock }  ← active.lock released at ~2s while build still runs → FIFO invariant broken
  :474-477  Get-SafeValue { Get-BuildQueueOccupancy … Reset-CompilerServer … }  ← both undefined → silently no-op
  :479-498  Get-SafeValue { … Format-BuildQueueBanner … Write-Output $banner }  ← Format-BuildQueueBanner undefined → throws → SWALLOWED → banner never printed
  :500    exit $exitCode                             ← exit 0 (the runner's early exit code)
```

**Fix-site-on-path confirmation:** the fix (move each dot-source out of the `Get-SafeValue`/`& $Block` child scope into the script scope) lands at `build-queue.ps1:47-49` and `build-queue-runner.ps1:66-68` — the exact nodes whose child-scope discard the trace shows is the origin of every downstream hop. On-path, not adjacent.

### Runtime Evidence

Isolated runtime repro (2026-07-06, general-purpose subagent; byte-copy of the three production scripts into scratch, `$stateRoot` repointed to `$env:TEMP\bq-repro-state`, synthetic 25s "build" — **production `~/.claude/state/build-queue/` never touched**):

- **Leading hypothesis REFUTED.** `Start-Process … -PassThru` + `$proc.HasExited`/`WaitForExit()` work correctly in isolation — the exact wrapper shape (`-RedirectStandardOutput/-RedirectStandardError -WindowStyle Hidden`) tracked a 25s sleep for the full duration. The early return is NOT a `Start-Process`/`HasExited` interaction.
- **Broken run** (production copy, only `stateRoot` repointed + DBG lines): wrapper exited the tail loop after ~2s (`iter=4 HasExited=True ExitCode=0`) not ~25s; reached `exit 0`; the "banner composed" DBG line **never fired**. `results/1.json` = `{seq:1, exit_code:0, ended_at:…}` (bare, no `counts`/`hygiene`) — byte-shape-identical to the seq=688 screenshot.
- **Instrumented runner**: `hygiene dot-sourced. New-BuildJobObject present? False` → `grandchild launched` → `TRAP FIRED: 'New-BuildJobObject' is not recognized` → follow-on `'$exitCode' cannot be retrieved because it has not been set` — proving `WaitForExit()`/`$exitCode` were skipped.
- **Minimal isolation**: `. hygiene.ps1` (top level) → function present `True`; `Get-SafeValue { . hygiene.ps1 }` → present `False`. Definitive.
- **Verified fix**: with both dot-sources moved to script scope, the same 25s build waited the full ~25s (`WaitForExit returned … ExitCode=0`) and the wrapper printed `build-queue: seq=1 op=nxbuild RESULT=PASS (result_fidelity=n/a)`.

Screenshot #1 (seq=688): `{"seq":688,"exit_code":0,"ended_at":"2026-07-06T09:43:58…"}` bare fallback, 0-byte log, no banner — consistent with the cascade above.

### Git History

The `build-queue-outcome-opacity-and-inspect-deny` hardening added `Format-BuildQueueBanner` and the `build_fidelity`/`result_fidelity` fields to `build-queue-hygiene.ps1`. Because the dot-source that would import those functions has always run in a discarded child scope, **none of that hardening has ever executed in production** — the queue "worked" only via the `if (Get-Command X -ErrorAction SilentlyContinue)` fallback branches (which take their degraded path precisely because the function is absent).

### Related Documentation

- Root `CLAUDE.md` build-queue section documents the banner as the authoritative one-line outcome and the per-build `hygiene` block (recycle/quarantine/fidelity) as active — all of which are currently silently disabled by this bug.
- `nxbuild/SKILL.md:36,38` (and siblings) tell agents to trust the banner and offer a `results/<seq>.json` poll fallback — both are undermined while the banner never prints and the result file is the premature bare fallback.

## Theories

### Theory 1: Hygiene dot-source runs in `Get-SafeValue`'s child scope, so every hygiene function is undefined in both scripts — CONFIRMED (`traced`)
- **Hypothesis:** `Get-SafeValue { . hygiene.ps1 }` invokes the block via `& $Block` (child scope); functions defined by the dot-source never reach the script scope. The runner then throws `CommandNotFoundException` on the first hygiene call (`New-BuildJobObject`, `:128`) → trap/continue skips `WaitForExit` → premature bare result + orphaned build; the wrapper's `Format-BuildQueueBanner` (`:496`) is undefined → the enclosing `Get-SafeValue` swallows the throw → no banner.
- **Supporting evidence:** the serving-path trace above; the isolated repro (broken vs. fixed); the minimal `Get-Command` isolation; the instrumented runner's trap sequence; the byte-shape match to seq=688.
- **Contradicting evidence:** none.
- **Status:** Confirmed — locked root cause. Necessary (removing it fixes all symptoms in the repro) and sufficient (introducing only it reproduces all symptoms).

### Theory 2 (former lock): The verdict is never persisted into `results/<seq>.json` — REFUTED as root cause; a real but secondary gap
- **Original claim:** the composed `RESULT` verdict is `Write-Output`-only and never merged into the result file, so consumers lack a verdict and re-run.
- **Why refuted as the cause:** the verdict-less/premature result file is a **downstream symptom** — the runner traps out before it ever writes its rich (`counts`/`hygiene`-bearing) result, so the wrapper falls back to the bare 3-field shape. Persisting a verdict would not help while `Format-BuildQueueBanner` (the verdict producer) is itself undefined and the runner never reaches its result write. The repro confirms: fixing only the scope bug restores the rich result **and** the banner without any verdict-persistence change.
- **Residual value:** persisting the composed verdict into `results/<seq>.json` remains a worthwhile **defense-in-depth** hardening for the genuine background-poll path (`nxbuild/SKILL.md:38`) and converges with `build-queue-orphaned-result-on-wrapper-kill`. Carried as an OPTIONAL follow-up in Affected Area, not the primary fix.
- **Status:** Refuted as root cause; retained as an optional secondary hardening.

### Theory 3: Foreground wrapper early-return via `Start-Process`/`HasExited` — REFUTED
- **Original suspicion:** the wrapper's `while (-not $proc.HasExited)` fell through immediately after `Start-Process`.
- **Why refuted:** the isolated repro proved `Start-Process -PassThru`/`HasExited`/`WaitForExit` track a long child correctly. The wrapper's loop *does* end at ~2s, but correctly — because the process it tracks (the runner) genuinely exited at ~2s (having trapped out). The premature exit originates in the runner, not the wrapper's process-watch.
- **Status:** Refuted.

## Proven Findings

1. `Get-SafeValue { . hygiene.ps1 }` discards the dot-sourced functions into a child scope in **both** `build-queue.ps1:47-49` and `build-queue-runner.ps1:66-68`; every hygiene function is undefined in each script's scope (minimal `Get-Command` isolation).
2. In the runner this causes `New-BuildJobObject` (`:128`) to throw under `Stop`+StrictMode; the `trap`/`continue` (`:88-91`) abandons the `try`, skipping `$proc.WaitForExit()` (`:133`), so the runner exits in ~2s with the build orphaned and its rich result (`:244-257`) never written.
3. In the wrapper the undefined `Format-BuildQueueBanner` (`:496`) throws inside the Step-5 `Get-SafeValue` (`:479`) and is silently swallowed → the banner is never printed; the wrapper writes the premature bare-fallback result (`:440-444`) and releases `active.lock` (`:455-472`) at ~2s.
4. All build hygiene (VBCSCompiler recycle, Job-Object descendant reap, poisoned-DLL quarantine, `Get-BuildQueueOccupancy` gating, `build_fidelity`/`result_fidelity` classification, `Stop-DllLockers`) has been **silently no-op in production** for the life of this bug — only the `Get-Command`-guarded fallback branches ran.
5. The machine-global "only ONE build at a time" invariant is broken: `active.lock` is released ~2s into a build that is still compiling, so a concurrent worktree can claim the slot alongside the orphan.
6. Fix is a two-line-per-file scope correction on the exact nodes the trace identifies; the repro verifies it restores banner, synchronous wait, rich result, `active.lock` lifetime, and hygiene simultaneously.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Wrapper — hygiene load | `user/scripts/build-queue.ps1:47-49` | **PRIMARY.** Move the dot-source out of `Get-SafeValue`/`& $Block` into a top-level `try { . … } catch { }` (script-scope preserving, still fail-open). Restores `Format-BuildQueueBanner`, `Reset-CompilerServer`, `Get-BuildQueueOccupancy`, `Read-WithRetry`. |
| Runner — hygiene load | `user/scripts/build-queue-runner.ps1:66-68` | **PRIMARY.** Same fix, independently. Restores `New-BuildJobObject`/`Add-ProcessToBuildJob`/`Stop-BuildJobTree`, `Test-BuildLogFailure`, `Stop-DllLockers`, so `WaitForExit` is reached and the rich result is written. |
| Status view — hygiene load | `user/scripts/build-queue-status.ps1:31` | **PRIMARY (3rd instance).** Same fix. Restores `Get-HygieneHighlight` so `/build-queue-status` renders the per-build highlight instead of the silently-degraded plain line. Fix the `:26-30` comment (the degrade is permanent today, not load-error-only). |
| Hygiene helpers | `user/scripts/build-queue-hygiene.ps1` | No change — functions are correct; only how they are imported is wrong. Confirm no top-level side-effecting statements rely on child-scope isolation. |
| Regression guard | (new) Pester test or a self-check | After each script sources hygiene, assert `Get-Command Format-BuildQueueBanner`/`New-BuildJobObject` resolve in script scope — the exact `Get-Command` isolation that distinguishes broken vs. fixed. Prevents silent re-regression if someone re-wraps the dot-source. |
| Build/test skills — poll fallback | `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` | Secondary. Once the banner reliably prints, the Step-4 background-poll contract needs a verdict-bearing field to poll (see optional verdict-persistence below); until then the poll path stays on `exit_code` only. |
| OPTIONAL — verdict persistence | `build-queue-runner.ps1:244-257` / `build-queue.ps1:429-498` | Defense-in-depth (former Theory 2): also persist the composed verdict into `results/<seq>.json` for the genuine background-poll path. Converges with `build-queue-orphaned-result-on-wrapper-kill`. Not required to fix the primary symptoms. |

## Open Questions

- **Fix form:** `try { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') } catch { }` at top level in each script (script-scope preserving, fail-open) is the recommended shape. Confirm we want to keep fail-open (a missing hygiene file → degraded fallback branches) vs. hard-fail loudly now that we know the fallback path masked a total hygiene outage for so long. Recommendation: keep fail-open, but add the regression guard so the *scope* mistake can't recur silently.
- **Should the OPTIONAL verdict-persistence follow-up be folded into this bug's `/plan-bug`**, spun back out as its own item (re-using the original `verdict-not-persisted` framing but now correctly scoped as hardening), or merged into `build-queue-orphaned-result-on-wrapper-kill`? Recommendation: land the two-line scope fix first (unblocks every Cognito build immediately), then decide verdict-persistence separately.
- **Blast-radius audit — DONE (2026-07-06).** A `grep -rnP "(Get-SafeValue|&)\s*\{\s*\.\s"` sweep over `user/scripts/*.ps1` found exactly **three** instances of the bug: `build-queue.ps1:47`, `build-queue-runner.ps1:66`, and `build-queue-status.ps1:31` — all three now in Affected Area. No other dot-source-in-child-scope pattern exists in the tree. The fix must patch all three; a fourth would be a new occurrence caught by the regression guard.
