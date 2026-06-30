# Implementation Phases — Build queue artifact/process hygiene + result fidelity

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a PowerShell harness change to the Cognito build queue (`user/scripts/build-queue*.ps1` + the symlinked `repos/cognito-forms/.claude/scripts/test-filtered.ps1`). claude-config has no Tauri/MCP dev runtime; there is no MCP-reachable surface. Verification is by **manual operator runs** of the queue against a real Cognito worktree, plus optional Pester smoke for the pure helper functions.

## Validated Assumptions / Runtime-coupled gate (Step 2.7)

Most assumptions here are **code-provable** from the three scripts already read during the touchpoint audit (the runner runs the build as a `& powershell.exe -File $Exec` grandchild with no process/artifact cleanup; `test-filtered.ps1` echoes only regex-matched lines with no zero-output guard; both result writers record the raw `exit_code`). One assumption is **runtime-coupled and load-bearing** and is scheduled as an explicit early deliverable, NOT planned-around:

- **[RUNTIME-COUPLED — Phase 4 spike]** *Why* a ≥3-way-OR `/mstest` filter yields empty output (zero tests actually matched vs. a summary format `test-filtered.ps1`'s regex misses) cannot be proven by reading source. Phase 4's first deliverable is a runtime spike that observes a real ≥3-way-OR run's **unfiltered** `dotnet test` output and records the OBSERVED mechanism. The two defensive layers (zero-output guard + queue fidelity recording) are robust regardless of the spike's outcome; the spike only decides whether an *additional* root-cause fix (filter construction in the caller, or a regex widening) is warranted.

> **No hard upstream deps** (`**Depends on:** (none)` in SPEC). No Cross-feature Integration Notes section.

## Touchpoint Audit (verified — Step C)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/build-queue-runner.ps1` | yes | build invocation `& powershell.exe … -File $Exec @ExecArgs` (`:39`), `Get-SafeValue`, result-write + seq-scoped lock-release (`:42-77`) | refactor | Bracket the `:39` invocation with Job-Object scoping + reap + quarantine + VBCSCompiler recycle (`try/finally`); reuse `Get-SafeValue`; extend the result body (`:52-56`) with a `hygiene` sub-object |
| `user/scripts/build-queue.ps1` | yes | `Test-PidAlive` (`:47-58`), `Get-SafeValue`, `Get-LiveTicketSeqs`, `Get-ActiveLockStatus`, launch (`:287-314`), tail loop (`:321-341`), Step 5 release (`:364-392`) | refactor | Pass `-Worktree $worktree` to the runner; backstop reap/recycle on the abort/timeout path; mirror the extended result body (`:369-373`) |
| `repos/cognito-forms/.claude/scripts/test-filtered.ps1` | yes | `param($Filter,$TestDll)`, streaming `& dotnet @dotnetArgs … \| ForEach-Object` (`:30-64`), passed/failed/summary regexes (`:34,:39,:56`) | refactor | Add a `$resultLineCount`/`$summarySeen` counter; after the pipeline capture `$dotnetExit=$LASTEXITCODE`; zero-output ⇒ explicit warning + `exit 3` |
| `user/scripts/build-queue-status.ps1` | yes | `Get-SafeValue`, `Format-Elapsed`, `Get-PerfSnapshotLine`; reads `active.lock` + tickets (`:80-139`) | refactor | Read `results/<seq>.json`'s `hygiene` sub-object; surface poisoned/cleaned/unverified state |
| `user/scripts/build-queue-hygiene.ps1` | **NO (net-new — create)** | — | create | Dot-sourced module of pure + P/Invoke helpers: Job-Object create/assign/terminate, 0-byte/invalid-PE sweep, VBCSCompiler recycle, result-fidelity classifier. Sourced by the runner (and wrapper backstop). No existing reapable abstraction — this is the shared home |
| `repos/cognito-forms/CLAUDE.local.md` | yes | "Running Tests" / manual-recovery tribal-knowledge block | refactor (Phase 5) | Trim the "kill `testhost`/`dotnet` + delete bad DLL" manual recovery to note the queue now owns it |

All paths verified `exists: yes` except `build-queue-hygiene.ps1` (stamped **net-new**). No contradictions surfaced; no `NEEDS_INPUT.md` fork.

---

### Phase 1: Shared hygiene module + Job-Object descendant reaping

**Scope:** Create the dot-sourced `build-queue-hygiene.ps1` module and use a **Windows Job Object** (Locked Decision 2) to scope and reap the build's descendant process tree. The runner assigns its build grandchild to a Job Object at launch with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and explicitly `TerminateJobObject`s on the build's exit AND on the runner being aborted/killed (via `try/finally` + a trap). This crosses the **process boundary** (runner → grandchild → MSBuild `/m` workers / `testhost`) and is the highest-risk piece, so Phase 1 drives a real spawning build through the reap path and asserts no orphans survive.

**Deliverables:**
- [x] `user/scripts/build-queue-hygiene.ps1` created, dot-sourceable, with the Job-Object P/Invoke surface: `New-BuildJobObject` (CreateJobObject + SetInformationJobObject `KILL_ON_JOB_CLOSE`), `Add-ProcessToBuildJob` (AssignProcessToJobObject), `Stop-BuildJobTree` (TerminateJobObject + close handle). Guarded so a non-Windows / P-Invoke failure FAILS OPEN (logs, does not abort the build).
- [x] `build-queue-runner.ps1` refactored: replace the synchronous `& powershell.exe … -File $Exec` (`:39`) with `Start-Process -PassThru`, assign the returned process to a fresh Job Object, `Wait-Process`, and reap the job in a `finally` so it fires on normal exit, non-zero exit, and runner abort/kill.
- [x] The reap NEVER targets a sibling worktree's live build — scoping is by Job Object membership only (no global `Get-Process dotnet | Stop-Process`).
- [x] Optional Pester smoke (`build-queue-hygiene.Tests.ps1`) for the non-P/Invoke surface; the Job-Object reap itself is verified by the manual runtime check below.

**Minimum Verifiable Behavior:** Launch a synthetic build script via the runner that spawns child processes (e.g. `Start-Process` a few `powershell -c "Start-Sleep 120"`) then kill the runner mid-flight; confirm via `Get-Process` that **zero** spawned descendants survive.

**Runtime Verification** *(checked by manual operator testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Run a real `/msbuild` that is killed mid-compile (or the synthetic spawner above); after the runner exits, `Get-Process dotnet,testhost,MSBuild` shows no orphaned descendants from that build.
- [ ] <!-- verification-only --> A second worktree's concurrently-queued build (serialized behind the first) is NOT affected — its processes survive the first build's reap.

**MCP Integration Test Assertions:** N/A — no MCP surface; verified by manual queue runs.

**Prerequisites:** None (first phase; establishes the shared module).

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — **net-new** Job-Object helpers.
- `user/scripts/build-queue-runner.ps1` — dot-source the module; bracket the `:39` build invocation with job assignment + `finally` reap.

**Testing Strategy:** Manual runtime observation (the Job-Object reap needs real processes). Pester covers only the pure/guarded surface in isolation.

**Integration Notes for Next Phase:**
- The runner now owns a `try/finally` build bracket — Phases 2 & 3 hook their cleanup into the SAME `finally` (recycle + quarantine), not a new one.
- `Stop-BuildJobTree` reaps DESCENDANTS only. `VBCSCompiler` is launched detached (not a job member), so Phase 2's recycle is a separate, explicit step.
- The runner now needs the worktree path for Phase 3's quarantine — add `-Worktree` to the runner param block here (wrapper passes it in Phase 3) or stub it now.

---

### Phase 2: Force-recycle VBCSCompiler between queued builds

**Scope:** After each queued build completes or aborts, shut down the machine-global `VBCSCompiler` server (Locked Decision 1) so the next build cold-starts a fresh compiler server instead of reusing a half-dead node (the cross-worktree `MSB4166` vector). Owned by the runner's `finally` bracket (build lifetime), with a wrapper backstop on the abort/timeout path. Safe because the queue serializes — no concurrent build's server is ever killed.

**Deliverables:**
- [x] `Reset-CompilerServer` in `build-queue-hygiene.ps1`: prefer `dotnet build-server shutdown` (graceful, official); fall back to `Get-Process VBCSCompiler -ErrorAction SilentlyContinue | Stop-Process -Force`. Fail-open.
- [x] Wired into the runner's `finally` bracket (fires after the job reap, on every exit path).
- [x] Wrapper backstop: `build-queue.ps1` calls `Reset-CompilerServer` on the abort/timeout path (where the detached runner may have been torn down before its `finally` ran).
- [x] Result body records `vbcscompiler_recycled: true|false` (consumed by Phase 5).

**Minimum Verifiable Behavior:** After a queued build finishes, `Get-Process VBCSCompiler` returns nothing; the next queued build runs cleanly (no `MSB4166` "child node exited prematurely" from a reused dead node).

**Runtime Verification** *(manual):*
- [ ] <!-- verification-only --> Run a queued build, then immediately `Get-Process VBCSCompiler` — no server persists.
- [ ] <!-- verification-only --> Run two queued builds back-to-back in different worktrees; the second does not fail with `MSB4166` from a reused node.

**MCP Integration Test Assertions:** N/A — no MCP surface.

**Prerequisites:** Phase 1 — reuses the runner's `finally` bracket and the `build-queue-hygiene.ps1` module.

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — add `Reset-CompilerServer`.
- `user/scripts/build-queue-runner.ps1` — call it in `finally`; add `vbcscompiler_recycled` to the result body.
- `user/scripts/build-queue.ps1` — abort/timeout-path backstop call.

**Testing Strategy:** Manual runtime (server processes are machine-global; observe before/after). Measure the warm-start penalty once to confirm it is acceptable against the serialized cadence (record in the plan's notes).

**Integration Notes for Next Phase:**
- The recycle runs AFTER the job reap and BEFORE the result-body write, so Phase 3's quarantine slots between the reap and the recycle (all inside the one `finally`).

---

### Phase 3: Artifact validation / quarantine (0-byte + truncated `*.dll`, `bin/` and `obj/`)

**Scope:** On a non-zero or aborted build exit, sweep the worktree's `bin/` **and `obj/`** trees for 0-byte and truncated (invalid-PE) `*.dll` and delete them, so MSBuild's timestamp-based incremental up-to-date check cannot treat a poisoned artifact as current (Locked Decision 3). The `obj/` coverage is load-bearing — the second screenshot's recovery deleted the 0-byte DLL from both `bin\Debug\…\Cognito.dll` and `obj\Debug\…\Cognito.dll`.

**Deliverables:**
- [ ] `Remove-PoisonedArtifacts -WorktreeRoot <path>` in `build-queue-hygiene.ps1`: enumerate `*.dll` under `bin/` and `obj/`; delete any that are 0-byte OR fail a cheap PE-validity probe (size below a small threshold AND/OR missing the `MZ`/PE header magic bytes — final check decided by the plan per SPEC Open Question 2). Returns the list of quarantined paths. Fail-open per-file.
- [ ] Runner passes its `-Worktree` (threaded from the wrapper) to the sweep; sweep runs in the `finally` ONLY on non-zero/aborted exit (a clean exit leaves artifacts untouched).
- [ ] `build-queue.ps1` passes `-Worktree $worktree` (already computed at `:72-75`) to the runner invocation (`:280-285`).
- [ ] Result body records `quarantined_artifacts: [<paths>]` (consumed by Phase 5).
- [ ] Pester smoke for `Remove-PoisonedArtifacts` against a temp dir seeded with a 0-byte DLL, a truncated DLL, and a valid DLL (asserts only the first two are removed) — this function is pure file-I/O and IS unit-testable in isolation.

**Minimum Verifiable Behavior:** Seed a worktree's `bin/`+`obj/` with a 0-byte `Cognito.dll`, run a failing queued build; afterward the 0-byte DLLs are gone and the next build recompiles cleanly (no `CS0009`/`CS0234`).

**Runtime Verification** *(manual):*
- [ ] <!-- verification-only --> After a crashed build that left a 0-byte DLL in `bin/` and `obj/`, both are deleted and the next queued build produces a valid (non-zero, valid-PE) DLL.
- [ ] <!-- verification-only --> A clean (exit 0) build does NOT trigger the sweep — valid artifacts are preserved.

**MCP Integration Test Assertions:** N/A — no MCP surface.

**Prerequisites:** Phase 1 (`finally` bracket + module); the `-Worktree` runner param stubbed in Phase 1.

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — add `Remove-PoisonedArtifacts`.
- `user/scripts/build-queue-runner.ps1` — accept `-Worktree`; call the sweep in `finally` on non-zero/abort; add `quarantined_artifacts` to the result body.
- `user/scripts/build-queue.ps1` — pass `-Worktree $worktree` to the runner launch.
- `build-queue-hygiene.Tests.ps1` — sweep unit test.

**Testing Strategy:** Pester for the pure sweep; manual runtime for the end-to-end "next build recompiles" loop.

**Integration Notes for Next Phase:**
- The result body now carries `hygiene: { reaped_pids, vbcscompiler_recycled, quarantined_artifacts }` — Phase 4 adds `result_fidelity`, Phase 5 reads the whole sub-object.

---

### Phase 4: Result-fidelity guard (zero-output / ambiguous-pass detection) + ≥3-way-OR root-cause spike

**Scope:** Close the third vector — `exit_code=0` trusted as a pass when the run produced no meaningful output. Two defensive layers (Locked Decision 4): a **zero-output guard in `test-filtered.ps1`**, and **result-fidelity recording in the queue**. Begins with the runtime spike (Validated-Assumptions gate) that establishes WHY ≥3-way-OR filters emit empty output.

**Deliverables:**
- [ ] **(Runtime spike — must be satisfied by observing a real run, not a static read)** Run a real ≥3-way-OR `/mstest` filter with **unfiltered** `dotnet test` output captured; record whether zero tests matched (filter-construction bug) or tests ran but the summary format was unparsed (regex miss). Write the OBSERVED finding into the plan's notes; decide whether an additional root-cause fix beyond the defensive guard is warranted.
- [ ] `test-filtered.ps1`: track `$resultLineCount` (passed+failed lines seen) and `$summarySeen`; after the streaming pipeline, capture `$dotnetExit = $LASTEXITCODE`. If `$resultLineCount -eq 0 -and -not $summarySeen` ⇒ emit an explicit `⚠ No test results captured (zero tests matched filter or summary not parsed)` line and `exit 3` (distinguished non-zero); otherwise `exit $dotnetExit` (preserve the real verdict).
- [ ] (Conditional on spike outcome) If the spike proves a filter-construction bug, apply the minimal root-cause fix (caller filter construction in `mstest/SKILL.md`, or a `test-filtered.ps1` filter-arg correction). If it proves an unparsed-summary regex miss, widen the `:56` summary regex. Defensive guard above lands either way.
- [ ] Runner classifies `result_fidelity`: a test op (`mstest`/`nxtest`) whose child exited `3` (the distinguished no-output code) ⇒ `result_fidelity: "no-output"`; a normal pass ⇒ `"verified"`. Recorded into the result body's `hygiene` sub-object. Non-test ops record `"n/a"`.

**Minimum Verifiable Behavior:** A `/mstest -Filter "ClassName~DoesNotExist"` (guaranteed zero-match) run no longer records `exit_code=0` as a pass — `test-filtered.ps1` prints the warning and exits `3`, and `results/<seq>.json` carries `result_fidelity: "no-output"`.

**Runtime Verification** *(manual):*
- [ ] <!-- verification-only --> A zero-match `/mstest` filter exits non-zero with the explicit warning (NOT a silent `0`).
- [ ] <!-- verification-only --> A genuine all-passing `/mstest` run still exits `0` and records `result_fidelity: "verified"` (no false positive on real passes).
- [ ] <!-- verification-only --> The ≥3-way-OR filter case that previously logged only the header now either prints results (if root cause fixed) or is flagged `no-output` (defensive guard) — never a silent pass.

**MCP Integration Test Assertions:** N/A — no MCP surface.

**Prerequisites:** Phase 1 (result-body `hygiene` sub-object structure). Independent of Phases 2–3 in logic, but sequenced after them because all four touch the runner's result-body write (file-overlap; see batch note).

**Files likely modified:**
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` — zero-output guard + distinguished exit.
- `user/scripts/build-queue-runner.ps1` — `result_fidelity` classification into the result body.
- `repos/cognito-forms/.claude/skills/mstest/SKILL.md` — only if the spike proves a caller filter-construction bug.

**Testing Strategy:** The runtime spike + manual zero-match / all-pass runs. `test-filtered.ps1`'s counter logic is observable via the warning line; the queue's classification via `results/<seq>.json`.

**Integration Notes for Next Phase:**
- `result_fidelity` now lives in the `hygiene` sub-object alongside the Phase 1–3 fields — Phase 5's status reader surfaces all four.

---

### Phase 5: Surface hygiene state in status + trim tribal-knowledge recovery docs

**Scope:** Make the recorded hygiene/fidelity state visible and retire the manual-recovery tribal knowledge now that the queue owns it. Consolidates the `hygiene` sub-object schema (written by Phases 1–4) into the status reporter and updates the Cognito `CLAUDE.local.md`.

**Deliverables:**
- [ ] `build-queue-status.ps1` reads the most recent `results/<seq>.json` for the active/last build and surfaces a `hygiene:` line — reaped-PID count, `vbcscompiler_recycled`, quarantined-artifact count, and `result_fidelity` (highlighting `no-output`/`zero-match` so an unverified run is visible, not invisible).
- [ ] Document the extended `results/<seq>.json` schema (the `hygiene` sub-object: `reaped_pids`, `vbcscompiler_recycled`, `quarantined_artifacts`, `result_fidelity`) in the runner's header comment and the workspace `claude-config/CLAUDE.md` build-queue scripts table note.
- [ ] Trim `repos/cognito-forms/CLAUDE.local.md`'s manual-recovery block (the "kill `testhost`/`dotnet` + delete bad DLL" tribal knowledge) to state the queue now reaps descendants, recycles VBCSCompiler, and quarantines 0-byte artifacts automatically — keeping only a one-line "if it ever recurs, check `/build-queue-status`" pointer.

**Minimum Verifiable Behavior:** After a crashed build, `/build-queue-status` (or `build-queue-status.ps1`) prints a `hygiene:` line reflecting the reap/recycle/quarantine that occurred — state that was previously invisible.

**Runtime Verification** *(manual):*
- [ ] <!-- verification-only --> `build-queue-status.ps1` shows the hygiene summary for the last build (reaped count, recycled flag, quarantined count, fidelity).
- [ ] <!-- verification-only --> A `result_fidelity: no-output` run is clearly flagged in the status output.

**MCP Integration Test Assertions:** N/A — no MCP surface.

**Prerequisites:** Phases 1–4 (consumes every field they write into the `hygiene` sub-object).

**Files likely modified:**
- `user/scripts/build-queue-status.ps1` — read + surface the `hygiene` sub-object.
- `user/scripts/build-queue-runner.ps1` — header-comment schema doc (no logic change).
- `claude-config/CLAUDE.md` — build-queue scripts table note on the new schema.
- `repos/cognito-forms/CLAUDE.local.md` — trim the manual-recovery tribal knowledge.

**Testing Strategy:** Manual — run a crashed build, then read the status output; confirm the docs match the implemented schema.

**Completion (gate-owned):** the `__mark_fixed__` gate (bug pipeline) flips SPEC.md **Status** to `Fixed`, writes the `FIXED.md` receipt, strikes the ROADMAP/queue entry, and archives the bug dir once this phase's runtime verification passes. Do NOT author a status-flip/receipt checkbox.

---

## Batch / ordering note

These phases are **Sequenced, not parallel.** Phases 1–4 all edit `build-queue-runner.ps1` (the `try/finally` bracket and the result-body write), Phases 1–3 all edit `build-queue-hygiene.ps1`, and Phase 5 reads the schema the others produce. There is no file-disjoint subset to batch in one message — dispatch one work unit at a time, in phase order.
