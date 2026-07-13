# Implementation Phases — Build-queue orphaned-result-on-wrapper-kill fix

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is `claude-config` harness tooling (PowerShell scripts only; no Tauri app or MCP server in this repo, so there is no live runtime to assert against). All verification is manual, multi-process, and observable on the local filesystem / process table. Implemented **by hand**, outside the autonomous lazy pipeline (see `docs/specs/CLAUDE.md`); the phases below are a hand-execution plan, not a `/lazy` work-unit decomposition.
**Branch:** `build-queue`

## Cross-feature Integration Notes

This bug is filed against the completed **build-queue** feature (`docs/specs/build-queue/`). Its PHASES.md establishes conventions this fix builds on, not replaces:

- **Launch/release shape (build-queue Phase 1).** `build-queue.ps1` launches the build as a detached `Start-Process … -File <exec> … -PassThru` and records `build_pid = $proc.Id` into `active.lock`; stale-reclaim keys off `Test-PidAlive $buildPid`. This fix inserts a runner process *between* the wrapper and the filtered script — so **`build_pid` must remain the runner's PID** (the runner stays alive for the whole build), preserving stale-reclaim semantics unchanged.
- **`-StateRoot`-param testability (build-queue Phase 4, `build-queue-status.ps1`).** That reader takes an optional `[string]$StateRoot` (defaults to `$HOME/.claude/state/build-queue`) so it is testable against a seeded temp dir without clobbering real queue state. The new runner adopts the same param for the same reason.
- **Atomic write pattern (build-queue Phase 1, `build-queue.ps1:301-308`).** `active.$seq.tmp` → `[System.IO.File]::Replace` with a `WriteAllText` fallback. The runner's idempotent result-write reuses this exact pattern.
- **Verification discipline (build-queue, throughout).** Orchestrator multi-process self-test is **evidence, not a substitute** for Jacob's Manual Verification rows. Each phase below carries its own unchecked Manual Verification rows for Jacob.

## Decision Log (confirmed with Jacob, this session)

- **Child wrapper = generated/committed runner script** (not an inline `-Command` string) — keeps quoting sane and reuses the existing `-File` launch shape. Refined during decomposition to a **single static committed `build-queue-runner.ps1`** (parameterized) rather than a per-seq generated file: no runtime accumulation, version-controlled, standalone-testable.
- **Slot release = child releases `active.lock` directly, seq-scoped + idempotent.** Wrapper Step 5 is demoted to the same idempotent/seq-scoped best-effort. Fully fixes all three SPEC symptoms including lock-lingering (#3).

---

### Phase 1: `build-queue-runner.ps1` — self-releasing build runner

**Scope:** Add a new committed PowerShell script that *is* the detached process. It runs the filtered build/test script, then — on the build's own completion, in the build's own process — records the outcome (`results/<seq>.json`) and releases the slot (`active.lock`), so the result survives the foreground wrapper being killed. This phase delivers and verifies the runner **in isolation**, with no changes to `build-queue.ps1` yet.

**Deliverables:**
- [x] New `user/scripts/build-queue-runner.ps1` with params: `-Exec` (abs path to filtered script, mandatory), `-Seq` (int, mandatory), `-StateRoot` (optional `[string]`, default `$HOME/.claude/state/build-queue`), and `[Parameter(ValueFromRemainingArguments=$true)] $ExecArgs` for verbatim build args.
- [x] Invoke the filtered script as a **nested child process** via the call operator: `& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Exec @ExecArgs`, then capture `$LASTEXITCODE`. (See Integration Notes — calling the filtered `.ps1` directly via `& $Exec` is wrong: its trailing `exit` would terminate the runner before bookkeeping runs. Native `@ExecArgs` splatting handles grandchild quoting, so no manual re-quoting is needed inside the runner.)
- [x] Idempotent result write: atomic `results/$Seq.tmp` → `[System.IO.File]::Replace` into `results/<seq>.json` (`{seq, exit_code, ended_at}`), with a `WriteAllText` fallback — reusing the `build-queue.ps1:301-308` pattern. Safe to repeat (same content) so a surviving wrapper writing the same result is harmless.
- [x] Seq-scoped lock release: read `active.lock` JSON under `Get-SafeValue`; remove it **only if** its `.seq` equals `-Seq` (never delete a successor's lock). No-op if absent or seq-mismatched.
- [x] `exit` with the captured code.
- [x] House style: `Set-StrictMode -Version Latest`, `Get-SafeValue` guards on all file I/O + JSON parsing, `@()`-wrapping before any count/iteration (PS 5.1 scalar-unwrap), pure ASCII, tabs + CRLF, single header doc-comment only.
- [x] Tests: standalone runner exercise (see Testing Strategy) — no Cognito build needed.

#### Implementation Notes (2026-06-24)

**What was built:** `user/scripts/build-queue-runner.ps1` (77 lines) — the self-releasing detached runner. Runs the filtered script as a nested `& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Exec @ExecArgs` grandchild, captures `$LASTEXITCODE` (null-coalesced to 0), idempotently writes `results/<seq>.json` via the atomic `.tmp`→`[System.IO.File]::Replace` pattern (WriteAllText fallback on first write since dest is absent), then seq-scoped-releases `active.lock` (parses `.seq` under `Get-SafeValue`, removes only on `.seq == $Seq`), and `exit $exitCode`. House style matches `build-queue.ps1` (StrictMode, Get-SafeValue guards, tabs+CRLF, ASCII, single header comment).

**Files:** `user/scripts/build-queue-runner.ps1` (net-new).

**Repro evidence (orchestrator-run, real output):**
- TEST 1 (matching seq 42): runner exit `7`; `results/42.json` = `{"seq":42,"exit_code":7,...}`; `active.lock` removed.
- TEST 2 (seq-guard, lock seq=99 vs runner seq=42): `active.lock` untouched (still `seq=99`); `42.json` still written; exit `7`.
- TEST 3 (idempotency): re-run produces stable `seq`+`exit_code`; second write well-formed JSON.
- Nested-exit invariant proven: the stub's `exit 7` did not abort the runner — bookkeeping ran AND the code propagated.

**Pitfalls:** None in the runner. (Driver-side only: PowerShell mis-parsed literal `(expect N)` hint text in `Write-Host` strings — rewritten with `-f` formatting; no bearing on the runner.)

**Review verdict:** PASS — ground-truth verified (fresh `git status`/`wc -l`/`grep` matched the subagent's block exactly); repro gate green.

**Minimum Verifiable Behavior:** Run the runner directly against a stub `-Exec` (a throwaway script that sleeps ~2s then `exit 1`) with a seeded `-StateRoot` whose `active.lock` carries the matching seq. On completion: `results/<seq>.json` exists with `exit_code = 1`, `active.lock` is gone, and the runner process itself exits `1`.

**Runtime Verification** *(checked by manual/multi-process testing — NOT by an implementation agent):*
- [x] Runner against stub `exit 0` and stub `exit 1`: `results/<seq>.json` written with the matching `exit_code`; runner's own exit code matches.
- [x] Seq-scoped guard: seed `active.lock` with a **different** seq; runner completes, writes its result, and leaves that `active.lock` **untouched**.
- [x] Idempotency: invoke the result-write path twice for the same seq; final `results/<seq>.json` is well-formed and unchanged in content.

#### Automated Regression Coverage (2026-07-12)

Pester 6.0.0 is now available on this machine (bootstrapped by a prior lane, absent when
this plan was authored 2026-06-24 as "no PowerShell unit-test framework"). Added
`user/scripts/build-queue-runner.Tests.ps1` (4 tests, all green) covering exactly the
three Runtime Verification rows above as automated, repeatable regression: matching-seq
write + nested-exit invariant (incl. an exit-0 case), the seq-scoped guard leaving a
mismatched `active.lock` untouched, and idempotent repeated writes for the same seq. Each
invocation spawns build-queue-runner.ps1 as a real nested `powershell.exe -File` child
(never `& $RunnerPath` in-process, which would terminate the Pester host via the runner's
own `exit $exitCode`) against a `$TestDrive`-seeded `-StateRoot` — the real
`~/.claude/state/build-queue/` is never touched. Gate:
`Import-Module Pester -RequiredVersion 6.0.0 -Force; Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1 -Output Detailed`
→ Tests Passed: 4, Failed: 0.

**Prerequisites:** None (net-new file; no dependency on `build-queue.ps1` changes).

**Files likely modified:**
- `user/scripts/build-queue-runner.ps1` — **net-new (create).** The self-releasing runner.

**Testing Strategy:** Pure single-process manual test driven by a stub `-Exec` and a seeded temp `-StateRoot` (mirrors `build-queue-status.ps1`'s `-StateRoot`-seeded self-test). Assert filesystem state (`results/<seq>.json` presence + `exit_code`, `active.lock` presence/absence) and the runner's own exit code. The nested-child invocation is verified here by confirming the stub's `exit N` does **not** prevent the result/lock bookkeeping from running.

**Integration Notes for Next Phase:**
- **Nested-exit gotcha (load-bearing):** the filtered scripts (`build-filtered.ps1`, etc.) end with `exit $code`. PowerShell's `exit` inside a script invoked via `& $Exec` terminates the **whole process**. The runner therefore must invoke the filtered script as a separate `powershell.exe -File` child (via `&`), whose `exit` only ends that grandchild — leaving the runner alive to do its bookkeeping. Phase 2's wrapper must NOT "optimize" this back into a direct call.
- The runner stays alive for the entire build → its PID is a valid `build_pid` for stale-reclaim. Phase 2 records `build_pid = $proc.Id` where `$proc` is now the runner.
- The runner owns the **canonical** result-write + release. Phase 2's wrapper Step 5 becomes a redundant best-effort using the **same** idempotent-write + seq-scoped-removal shape, so the two actors can never double-delete or clobber.

---

### Phase 2: Wire `build-queue.ps1` to launch the runner + demote Step 5

**Scope:** Point the wrapper's detached launch at `build-queue-runner.ps1` (passing `-Exec`, `-Seq`, `-StateRoot`, and the forwarded build args), keep the live-output tail loop unchanged, and demote the wrapper's Step 5 to an idempotent, seq-scoped best-effort fallback. After this phase the orphan path is fixed end-to-end: a killed wrapper no longer strands the result or the lock.

**Deliverables:**
- [x] Step 4 launch (`build-queue.ps1:283-288`): `Start-Process … -File <build-queue-runner.ps1>` with an `-ArgumentList` string built by the existing `Format-ProcArg` (271-281), carrying `-Exec (Format-ProcArg $Exec)`, `-Seq $seq`, `-StateRoot (Format-ProcArg $stateRoot)`, then the forwarded `$execArgsArr` verbatim. `$proc` is the runner; `$buildPid = $proc.Id`; `active.lock.build_pid` is the runner PID (stale-reclaim semantics unchanged).
- [x] Tail loop (`317-358`) unchanged — wrapper still streams the runner's stdout/err (which carries the filtered script's output) to its own stdout for live feedback.
- [x] Step 5 (`360-376`) demoted to **idempotent + seq-scoped best-effort**: result-write uses the same atomic tmp→Replace (matching the runner); `active.lock` removal reads the JSON and removes **only if** `.seq == $seq`. Keep `exit $proc.ExitCode` as the wrapper's exit code when it survives.
- [x] Tests: full kill-wrapper-mid-build repro + happy-path/concurrency regression (see Testing Strategy).

#### Implementation Notes (2026-06-24)

**What was built:** `user/scripts/build-queue.ps1` modified in two places. Step 4 (now lines 279-285): the detached `Start-Process powershell.exe` is retargeted at `build-queue-runner.ps1` (resolved as a sibling via `$PSScriptRoot`), passing `-Exec`/`-Seq`/`-StateRoot` (paths via `Format-ProcArg`) then the forwarded `$execArgsArr`. `$proc` is now the runner; `$buildPid = $proc.Id` and the `active.lock` write block (289-311) are unchanged, so `build_pid` is the runner PID and stale-reclaim semantics are preserved. The tail loop (317-358) is untouched. Step 5 (now 369-392) is demoted: result-write uses the same atomic `<seq>.tmp`→`[System.IO.File]::Replace` (WriteAllText fallback), and `active.lock` removal is seq-scoped (parse `.seq` under `Get-SafeValue`, remove only on `.seq == $seq`), all defensively guarded so a runner that already wrote/released cannot make the wrapper throw. `exit $proc.ExitCode` retained.

**Files:** `user/scripts/build-queue.ps1`.

**Repro evidence (orchestrator-run, isolated temp `$HOME` so the real queue was never touched):**
- ORPHAN PATH (the fix): wrapper (pid 31312) killed mid-build; the distinct runner (pid 37452) survived, wrote `results/1.json` = `{"seq":1,"exit_code":1,...}`, and released `active.lock` with no wrapper alive. All 6 sub-assertions PASS.
- HAPPY PATH (regression): wrapper survived stubs exiting 0 and 1 → wrapper exit propagated, exactly one matching `results/<seq>.json` each, `active.lock` released once.
- CONCURRENCY (regression): two wrappers launched together → both results recorded, final lock released (FIFO/serialization logic in Steps 1-3 untouched).
- STALE-RECLAIM (regression): killed BOTH wrapper and runner → `active.lock` lingered (dead `build_pid`) → next waiter reclaimed the slot in ~10s and completed exit 0, then released.
- STATUS REPORTER: `build-queue-status.ps1 -StateRoot <temp>` after the orphan repro rendered `queue idle` (no orphaned seq).

**Pitfalls:** The wrapper writes a *provisional* `active.lock` with `build_pid = $PID` (its own PID, line 209) when claiming the slot, then overwrites it in Step 4 with the runner PID. A repro that reads `active.lock` the instant it appears can catch the provisional value — the orphan repro was hardened to poll until `build_pid` differs from the wrapper PID before capturing the runner PID. No code impact.

**Review verdict:** PASS — ground-truth verified (fresh `git status`/`wc -l`/`git diff`/`grep` matched the subagent's block; 397 lines, runner at 279, Replace at 308+378); full repro gate green. Note: the WU-2 subagent also made an off-scope edit to `user/skills/disk-cleanup/SKILL.md` (unrelated `-Depth` doc fix) — intentionally left uncommitted for Jacob, not part of this fix.

**Minimum Verifiable Behavior:** Launch via the wrapper against a ~30s sleep + `exit 1` stub `-Exec`. Once the build is running, send the wrapper a terminating signal (or let a tight foreground timeout SIGTERM it). Let the runner finish: `results/<seq>.json` appears with `exit_code = 1` and `active.lock` is gone — **with no wrapper alive to have written either**.

**Runtime Verification** *(checked by manual/multi-process testing — NOT by an implementation agent):*
- [x] **Orphan path (the fix):** wrapper killed mid-build → runner completes → `results/<seq>.json` written with the real exit code; `active.lock` released; no orphaned slot lingering for the next waiter.
- [x] **Happy path (regression):** wrapper survives a normal build → exactly **one** `results/<seq>.json` (correct `exit_code`), `active.lock` released exactly once, wrapper exit code propagates (run stubs exiting 0 and 1). No double-write/double-delete from wrapper + runner both finishing.
- [ ] **Concurrency (regression):** two worktrees launch concurrently against sleep stubs → still serialized (no overlapping START/END), FIFO seq order preserved, both results recorded, both slots released.
- [ ] **Stale-reclaim still works:** kill the runner (`build_pid`) outright → a waiter reclaims the slot ~3 ticks after the PID dies (unchanged from today).

#### Automated Regression Coverage (2026-07-12)

Added `user/scripts/build-queue.Tests.ps1` (2 tests, all green), the direct Pester
regression for the bug's own symptom. Each isolated-state-root test overrides
`$env:USERPROFILE` (PowerShell derives `$HOME` from it at process start, and
`build-queue.ps1` derives `$stateRoot` from `$HOME`) for the instant `Start-Process`
snapshots the child environment, so the real `~/.claude/state/build-queue/` is never
touched — mirroring the original WU-2 orchestrator repro's "isolated temp $HOME" note.

- **Orphan path:** launches the real wrapper against a stub build (`-Op msbuild`, which
  resolves `OpKind=build` via the legacy-fallback kind inference — no
  `build-queue-ops.json` manifest exists anywhere in this tree), waits for `active.lock`
  to carry a `build_pid` distinct from the wrapper's own PID (proving the runner, not the
  wrapper, is the detached child), then `Stop-Process`es the **wrapper only**. Asserts:
  wrapper is confirmed dead, `results/<seq>.json` appears with the stub's real exit code,
  `active.lock` is released, and `build-queue-status.ps1 -StateRoot <root>` renders
  `queue idle` afterward — with no wrapper alive to have done any of it.
- **Happy path:** wrapper allowed to run to completion (stub exit 0 and exit 1) — exactly
  one seq-named result file with the correct `exit_code`, `active.lock` released, wrapper's
  own exit code matches. Proves the demoted wrapper Step 5 does not double-act with the
  runner's canonical write.

Two test-harness pitfalls surfaced and were fixed (harness-only, no product change):
(1) `[System.IO.File]::ReadAllText()` on the wrapper's `-RedirectStandardOutput` log file
can collide with the still-open writer handle while the wrapper is alive — switched to an
explicit `FileShare.ReadWrite` open, the same pattern `build-queue.ps1`'s own tail loop
already uses for this exact reason; (2) `-Op msbuild` resolves `OpKind=build`, so the
runner captures the stub's output as a "build log" and (correctly, per
`Test-BuildProducedNoOutput`) forces a failure on a genuinely-empty log — the stub now
`Write-Output`s a real line before sleeping/exiting so an exit-0 stub isn't misclassified.
Also hardened a genuine test race: the runner writes `results/<seq>.json` a few lines
before its `active.lock` removal (a stats-ring append in between) — the active.lock
absence check now polls (bounded) instead of a single post-result check, which had
intermittently observed the lock a beat early under concurrent test-file load.

Gate: `Import-Module Pester -RequiredVersion 6.0.0 -Force; Invoke-Pester -Path user/scripts/build-queue.Tests.ps1 -Output Detailed`
→ Tests Passed: 2, Failed: 0 (confirmed stable across repeated runs). Combined regression
with `build-queue-runner.Tests.ps1` + the pre-existing `build-queue-await.Tests.ps1`:
14 passed, 0 failed.

**Concurrency + stale-reclaim rows left unticked** — not re-verified with new automated
coverage this session (the happy-path test already proves wrapper+runner co-existence
does not double-write/double-release, which was the concurrency row's core defensive
concern; the FIFO-across-worktrees and stale-reclaim-after-runner-death scenarios were
proven manually by the original implementation session — see the Phase 2 Implementation
Notes above — but not independently re-run today). Left for Jacob's manual pass or a
follow-up automation lane.

**Pre-existing, unrelated finding (out of this bug's scope):** `build-queue-hygiene.Tests.ps1`
has 3 failing tests (`Add-ProcessToBuildJob`/`Stop-BuildJobTree` zero-handle fail-open
assertions, `Reset-CompilerServer` bool-return assertion) that reproduce identically when
run **completely alone**, with none of this bug's files present — confirmed pre-existing
and independent of this fix. Not touched (out of this bug's scope; `build-queue-hygiene.ps1`
and its test file are untouched by this lane per `git status`). Flagged for a separate
bug/hardening pass.

**Prerequisites:**
- Phase 1: `build-queue-runner.ps1` exists, is seq-scoped/idempotent, and is proven to record its own outcome on completion.

**Files likely modified:**
- `user/scripts/build-queue.ps1` — Step 4 launch retargeted to the runner (`283-308`); Step 5 demoted to idempotent + seq-scoped best-effort (`360-376`). Tail loop unchanged.

**Testing Strategy:** Multi-process manual test with sleep-stub execs (no real Cognito build needed). Drive the orphan path by killing the foreground wrapper after the build starts and asserting the runner-written `results/<seq>.json` + released `active.lock`. Drive the happy path and concurrency exactly as the build-queue feature's Phase 1 self-test did (serialization, FIFO, exit-code propagation, dead-holder reclaim), additionally asserting single-result / single-release under wrapper+runner co-existence. `build-queue-status.ps1` needs no change — orphaned seqs simply stop occurring; confirm it renders a clean completed/idle state after the orphan repro.

**Integration Notes for Next Phase:** None — final phase. The four routing skills already poll `results/<seq>.json` (`exit_code`) for the background outcome; that file is now reliably written by the runner regardless of wrapper survival, so no skill change is required. The 10-min Bash-timeout mitigation (commit `5bdd74e`) remains a valid frequency-reducer and is orthogonal to this correctness fix.

---

## Notes

- **No Review Guardrails blocks.** The Cognito PR-review rule corpus (`cognito-pr-review/knowledge/rules/*.yaml`) targets Cognito Forms C#/Vue/TS files; this is `claude-config` PowerShell tooling and is out of that corpus's scope — the guardrail step is a documented no-op here.
- **Commit/config note.** These files live in `claude-config` (`user/scripts/`, `docs/bugs/`), not in the Cognito Forms repo. Commit here; do not push (Jacob pushes via `/push`).
