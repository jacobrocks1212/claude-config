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
- [ ] New `user/scripts/build-queue-runner.ps1` with params: `-Exec` (abs path to filtered script, mandatory), `-Seq` (int, mandatory), `-StateRoot` (optional `[string]`, default `$HOME/.claude/state/build-queue`), and `[Parameter(ValueFromRemainingArguments=$true)] $ExecArgs` for verbatim build args.
- [ ] Invoke the filtered script as a **nested child process** via the call operator: `& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Exec @ExecArgs`, then capture `$LASTEXITCODE`. (See Integration Notes — calling the filtered `.ps1` directly via `& $Exec` is wrong: its trailing `exit` would terminate the runner before bookkeeping runs. Native `@ExecArgs` splatting handles grandchild quoting, so no manual re-quoting is needed inside the runner.)
- [ ] Idempotent result write: atomic `results/$Seq.tmp` → `[System.IO.File]::Replace` into `results/<seq>.json` (`{seq, exit_code, ended_at}`), with a `WriteAllText` fallback — reusing the `build-queue.ps1:301-308` pattern. Safe to repeat (same content) so a surviving wrapper writing the same result is harmless.
- [ ] Seq-scoped lock release: read `active.lock` JSON under `Get-SafeValue`; remove it **only if** its `.seq` equals `-Seq` (never delete a successor's lock). No-op if absent or seq-mismatched.
- [ ] `exit` with the captured code.
- [ ] House style: `Set-StrictMode -Version Latest`, `Get-SafeValue` guards on all file I/O + JSON parsing, `@()`-wrapping before any count/iteration (PS 5.1 scalar-unwrap), pure ASCII, tabs + CRLF, single header doc-comment only.
- [ ] Tests: standalone runner exercise (see Testing Strategy) — no Cognito build needed.

**Minimum Verifiable Behavior:** Run the runner directly against a stub `-Exec` (a throwaway script that sleeps ~2s then `exit 1`) with a seeded `-StateRoot` whose `active.lock` carries the matching seq. On completion: `results/<seq>.json` exists with `exit_code = 1`, `active.lock` is gone, and the runner process itself exits `1`.

**Runtime Verification** *(checked by manual/multi-process testing — NOT by an implementation agent):*
- [ ] Runner against stub `exit 0` and stub `exit 1`: `results/<seq>.json` written with the matching `exit_code`; runner's own exit code matches.
- [ ] Seq-scoped guard: seed `active.lock` with a **different** seq; runner completes, writes its result, and leaves that `active.lock` **untouched**.
- [ ] Idempotency: invoke the result-write path twice for the same seq; final `results/<seq>.json` is well-formed and unchanged in content.

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
- [ ] Step 4 launch (`build-queue.ps1:283-288`): `Start-Process … -File <build-queue-runner.ps1>` with an `-ArgumentList` string built by the existing `Format-ProcArg` (271-281), carrying `-Exec (Format-ProcArg $Exec)`, `-Seq $seq`, `-StateRoot (Format-ProcArg $stateRoot)`, then the forwarded `$execArgsArr` verbatim. `$proc` is the runner; `$buildPid = $proc.Id`; `active.lock.build_pid` is the runner PID (stale-reclaim semantics unchanged).
- [ ] Tail loop (`317-358`) unchanged — wrapper still streams the runner's stdout/err (which carries the filtered script's output) to its own stdout for live feedback.
- [ ] Step 5 (`360-376`) demoted to **idempotent + seq-scoped best-effort**: result-write uses the same atomic tmp→Replace (matching the runner); `active.lock` removal reads the JSON and removes **only if** `.seq == $seq`. Keep `exit $proc.ExitCode` as the wrapper's exit code when it survives.
- [ ] Tests: full kill-wrapper-mid-build repro + happy-path/concurrency regression (see Testing Strategy).

**Minimum Verifiable Behavior:** Launch via the wrapper against a ~30s sleep + `exit 1` stub `-Exec`. Once the build is running, send the wrapper a terminating signal (or let a tight foreground timeout SIGTERM it). Let the runner finish: `results/<seq>.json` appears with `exit_code = 1` and `active.lock` is gone — **with no wrapper alive to have written either**.

**Runtime Verification** *(checked by manual/multi-process testing — NOT by an implementation agent):*
- [ ] **Orphan path (the fix):** wrapper killed mid-build → runner completes → `results/<seq>.json` written with the real exit code; `active.lock` released; no orphaned slot lingering for the next waiter.
- [ ] **Happy path (regression):** wrapper survives a normal build → exactly **one** `results/<seq>.json` (correct `exit_code`), `active.lock` released exactly once, wrapper exit code propagates (run stubs exiting 0 and 1). No double-write/double-delete from wrapper + runner both finishing.
- [ ] **Concurrency (regression):** two worktrees launch concurrently against sleep stubs → still serialized (no overlapping START/END), FIFO seq order preserved, both results recorded, both slots released.
- [ ] **Stale-reclaim still works:** kill the runner (`build_pid`) outright → a waiter reclaims the slot ~3 ticks after the PID dies (unchanged from today).

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
