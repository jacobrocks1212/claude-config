# Implementation Phases — Build queue's machine-wide VBCSCompiler recycle can kill a concurrent worktree's build

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a PowerShell build-queue + bash-hook harness defect (state-machine/process-hygiene logic on Windows) with no MCP-reachable surface: no app, no dev runtime, no audio/UI. Verification is PowerShell/Pester + observed process state, not MCP.

## Validated Assumptions

Load-bearing assumptions for these phases, classified per the Runtime Assumption Validation gate. All were confirmed **code-provable** from the touchpoint audit (2026-07-02) — no runtime spike required; skip reason recorded inline.

- **The recycle is machine-wide (code-provable).** `Reset-CompilerServer` calls `dotnet build-server shutdown` (all user build servers, `build-queue-hygiene.ps1:380`) and `Get-Process -Name 'VBCSCompiler' | Stop-Process -Force` (every VBCSCompiler on the machine, `:388-392`). It is called in the runner `finally` (`build-queue-runner.ps1:148`) and the wrapper release path (`build-queue.ps1:399`).
- **The recycle's safety rests on serialization (code-provable).** The docstring states it verbatim: *"safe ONLY because the build queue serializes builds machine-wide"* (`build-queue-hygiene.ps1:360-361`). This is the invariant this bug shows is violable.
- **Output is per-worktree — cross-worktree file clobber is ruled out (code-provable).** `build-filtered.ps1:13,22` resolves the target from the current worktree; no `OutputPath`/`Directory.Build.props` override exists. The cross-worktree damage channel is the shared *compiler process*, not shared files.
- **No occupancy helper exists yet (code-provable).** `build-queue-hygiene.ps1` exposes no "is any other build active" query; `build-queue.ps1` computes `$lowestSeq` / live ticket seqs inline in its poll loop (`Get-LiveTicketSeqs`). Phase 2 must add a reusable occupancy query callable from the detached runner.
- **Residual (accepted, per Locked Decision below):** an occupancy gate can only see queue-visible builds. Off-queue bypass builds (`BUILD_QUEUE_BYPASS=1`) remain invisible to it — Vector B stays partially open by design; Phases 1 & 3 shrink the window rather than closing it.

## Locked Decisions

- **Phase 2 fix direction = occupancy-gate the recycle** (user decision, 2026-07-02). Keep shared compilation (and its cross-build warm-cache speed); recycle only when this build is the sole known-active queue seq. Rejected alternatives: disabling shared compilation for queued builds (closes Vector A+B but loses warm cache) and graceful-only shutdown (runtime-uncertain drain of a busy server, risks reintroducing MSB4166). Off-queue Vector B is an accepted residual, mitigated (not closed) by Phases 1 & 3.

## Cross-feature Integration Notes

Builds directly on the shipped hygiene fix `docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/` (Concluded, implemented). That fix's Phase 2 introduced `Reset-CompilerServer` on the explicit premise *"Safe because the queue serializes — no concurrent build's server is ever killed"* (its PHASES.md Phase 2, and the `build-queue-hygiene.ps1:356-368` docstring). This plan does **not** revert that fix — the Job-Object descendant reap (its Phase 1) is correctly worktree-scoped and stays as-is. It narrows only the one machine-wide step (the VBCSCompiler recycle) whose safety depended on an invariant the queue does not guarantee, and hardens the lock so the invariant holds more often. Its `results/<seq>.json` `hygiene` sub-object (`vbcscompiler_recycled`, `quarantined_artifacts`, `result_fidelity`, `build_fidelity`, `lockers_reaped`) is extended, not restructured.

---

### Phase 1: Close Vector A — atomic provisional lock write + reclaim hardening

**Scope:** Eliminate the stale-lock-reclaim race that can admit a second concurrent queued build. Two changes to `build-queue.ps1`: (1) write the provisional `active.lock` atomically so a racing reader can never observe a truncated/empty file, and (2) harden the reclaim so it advances the stale counter only on a *confirmed-dead* pid, treating `'unknown'` (unreadable lock) as inconclusive rather than as evidence of a dead holder.

**Deliverables:**
- [x] Provisional lock claim (`build-queue.ps1:202-224`) writes atomically: build the body to a temp file (`active.$seq.tmp`) and `[System.IO.File]::Replace` / move into place, mirroring the final-write pattern already at `:301-317`, instead of the raw `Write`/`Flush` into the `CreateNew` handle. The `FileMode::CreateNew` mutual-exclusion guarantee (only one claimant creates the file) must be preserved.
- [x] `Get-ActiveLockStatus` (`:162-176`) / the reclaim loop (`:182-200`) no longer counts a single `'unknown'` read toward `staleThreshold`. Reclaim advances only on `'dead'` (pid confirmed not alive via `Test-PidAlive`); an `'unknown'` read is inconclusive (hold or reset the tick, do not increment). `'absent'` still means free-to-claim.
- [x] Reads that can race the claim window (`:165`, `:391`, and the runner's read) tolerate a transient partial/locked read without misclassifying — a re-read or a bounded retry, so a mid-write observation resolves to the real status, not `'unknown'`.
- [x] Tests: a lock-body round-trip test (write→read yields intact JSON) and a concurrent-reader-vs-partial-write test asserting the reader never returns `'unknown'` for a lock that is merely mid-write.

**Implementation Notes** (2026-07-02)
- **Work completed (WU-1):** Added 3 fail-open pure decision helpers to `build-queue-hygiene.ps1` — `Set-LockFileAtomic` (:513, temp+`File.Replace`/`Move` with `WriteAllText` fallback), `Get-ActiveLockStatusFromText` (:590, injected-liveness classification → `alive|dead|unknown`, probe-throws fails safe to `alive`), `Test-ShouldReclaimLock` (:660, reclaim iff `IsLowestSeq` AND ≥`StaleThreshold` consecutive `'dead'`; any non-`'dead'` resets). Wired into `build-queue.ps1`: split `Get-ActiveLockStatus` → `Get-ActiveLockStatusOnce` + a 3-attempt bounded re-read on `'unknown'`; provisional write disposes the `CreateNew` claim handle then writes via `Set-LockFileAtomic`; reclaim loop maintains a capped `$recentStatuses` buffer → `Test-ShouldReclaimLock`; release-time `.seq` read is a bounded 3-attempt re-read. Same bounded re-read applied to `build-queue-runner.ps1`'s release-time read.
- **Robustness:** every helper call is `Get-Command`-guarded with an equivalent inline fallback, so a failed hygiene dot-source never breaks the queue's core lock path (fail-open preserved). The `CreateNew` mutual-exclusion arbiter is untouched.
- **Test note:** the plan's "concurrent-reader-vs-partial-write" timing-bound test was realized (per WU-1's Test Expectations + SPEC Open Question — the atomic-write invariant is the only assertable guard) as the unit-level round-trip + classification + confirmed-dead-only-reclaim tests. New tests use the assign-on-own-line Pester pattern to avoid the file's known child-scope quirk.
- **Files modified:** `user/scripts/build-queue-hygiene.ps1`, `user/scripts/build-queue.ps1`, `user/scripts/build-queue-runner.ps1`, `user/scripts/build-queue-hygiene.Tests.ps1`.
- **Gate:** `Invoke-Pester build-queue-hygiene.Tests.ps1` → 48 passed / 3 failed (the 3 are the documented pre-existing child-scope-quirk failures — no new failures vs. baseline). Both wired scripts parse clean.
- **Review verdict:** PASS (2026-07-02).

**Minimum Verifiable Behavior:** A test (or a scripted two-process harness) that races a reader against the provisional-write window asserts the reader observes either `'absent'` or the fully-written `'alive'` lock — never a truncated read that resolves to `'unknown'` — so the reclaim cannot fire against a live holder.

**Runtime Verification** *(checked by test or manual runtime — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Two `/msbuild` invocations started near-simultaneously in different worktrees serialize: exactly one holds `active.lock` at a time, and the waiter never reclaims the slot while the holder's `build_pid` is alive (observe `active.lock` contents + `Get-Process` during the overlap).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (PowerShell state-machine logic).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/build-queue.ps1` — atomic provisional write (`:202-224`); reclaim/status hardening (`:162-200`); tolerant reads (`:165`, `:391`).
- Test file — location per whatever PowerShell/Pester harness the repo uses; if none exists, a self-contained repro script under the bug dir's `plans/` or a `tests/` sibling (decide in `/write-plan`).

**Testing Strategy:** Unit-level Pester (or a stdlib PowerShell repro) for the lock round-trip and the partial-read classification. The full race is timing-dependent and need not be reproduced deterministically — the atomic-write + confirmed-dead-only reclaim are the assertable invariants (see SPEC Open Questions).

**Integration Notes for Next Phase:**
- After Phase 1, two *queued* builds can no longer overlap via the reclaim race — so Phase 2's occupancy gate is belt-and-suspenders for the queued case and the primary defense only for anything that slips (and cannot help the off-queue Vector B, by construction).
- The atomic-write helper introduced here should be reused, not re-implemented, if Phase 2 needs to write any state.

---

### Phase 2: Occupancy-gate the VBCSCompiler recycle

**Scope:** Make `Reset-CompilerServer` fire only when this build is the sole known-active queue seq, so a build finishing in worktree A cannot force-kill the shared VBCSCompiler that a concurrent queued build in worktree B is using. Add a reusable occupancy query (callable from the detached runner, which currently has no queue-state accessor) and gate both recycle callsites on it. Shared compilation stays enabled (Locked Decision).

**Deliverables:**
- [x] A reusable occupancy query — "are there live queue seqs other than mine?" — determined by reading the live tickets + `active.lock` under `$stateRoot`. Place it where both the wrapper and the detached runner can call it (candidate: `build-queue-hygiene.ps1` as a new helper, or a shared read of the state dir; `build-queue.ps1` already has `Get-LiveTicketSeqs` to reuse/lift). Names a concrete `file:symbol` in `/write-plan`.  ← **`Get-BuildQueueOccupancy -StateRoot -SelfSeq` in `build-queue-hygiene.ps1` (WU-2)**
- [x] `Reset-CompilerServer` (`build-queue-hygiene.ps1:342-402`) is gated: when another build is active, it **skips** the machine-wide kill (both `dotnet build-server shutdown` at `:380` and `Stop-Process -Force VBCSCompiler` at `:388-392`) and records why. Preferred shape: the caller passes an occupancy predicate/flag; the function stays fail-open.  ← **`-OtherBuildActive [bool]` gate (WU-2)**
- [ ] Both callsites gated consistently: the runner `finally` (`build-queue-runner.ps1:148`) and the wrapper release path (`build-queue.ps1:399`).  ← **WU-3 (batch 2, pending)**
- [ ] The skip is recorded in `results/<seq>.json`: extend the `hygiene` sub-object (`build-queue-runner.ps1:172-183`) so `vbcscompiler_recycled` distinguishes recycled / skipped-concurrent (e.g. a `false` plus a reason, or a new `recycle_skipped_reason`). `build-queue-status.ps1` should surface it (a skipped recycle under concurrency is expected, not an error).  ← **WU-3 (`recycle_skipped_reason`) + WU-4 (status surface), batch 2, pending**
- [x] Update the `build-queue-hygiene.ps1:356-368` safety-invariant docstring: it no longer *assumes* serialization — it now *checks* occupancy and documents the off-queue residual.  ← **WU-2**
- [x] Tests: the occupancy query returns the right count for 0/1/2 live seqs; the gate skips the kill when occupancy>self and performs it when sole.  ← **WU-2**

**Implementation Notes** (2026-07-02)
- **WU-2 (batch 1):** Added fail-open `Get-BuildQueueOccupancy -StateRoot <root> -SelfSeq <seq>` (`build-queue-hygiene.ps1:342`) → `[int]` count of OTHER live queue seqs (union-by-seq over `tickets/*.json` + `active.lock`, inline `GetProcessById` pid-liveness fail-safe-to-alive, self excluded, dead-pid uncounted, self-contained — no `build-queue.ps1` dependency). Fail-open bias is TOWARD recycle: any read failure → count 0. Gated `Reset-CompilerServer` with `-OtherBuildActive [bool]` (default `$false`): `$true` → early `return $false` skipping BOTH the graceful shutdown and the `Stop-Process` fallback; `$false`/omitted → existing recycle path unchanged (back-compat, still `[bool]`). Rewrote the safety-invariant docstring to document the occupancy-gated design + the two accepted residuals (off-queue bypass invisibility; fail-open-toward-recycle). Locked Decision 2 static guard still passes (the VBCSCompiler recycle is unchanged, just gated).
- **WU-3/WU-4 (batch 2):** pending — wire the two callsites + record `recycle_skipped_reason` + surface it in status.
- **Gate (batch 1):** `build-queue-hygiene.Tests.ps1` → 58 passed / 3 failed (3 pre-existing child-scope-quirk failures; no new failures). Parse-check clean.
- **Review verdict (WU-2):** PASS (2026-07-02).

**Minimum Verifiable Behavior:** With two builds forced to overlap (a concurrent queued build, or a bypass build running alongside a queued one), the queued build's completion does **not** kill the other's VBCSCompiler: `Get-Process VBCSCompiler` shows the concurrent build's server surviving, and the concurrent build completes without MSB4166.

**Runtime Verification** *(checked by manual runtime — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Run a queued build alongside a second concurrent build; on the first's completion, the second's VBCSCompiler is NOT force-killed and the second build finishes cleanly (no "child node exited prematurely" / MSB4166).
- [ ] <!-- verification-only --> Run a SOLE queued build (no concurrency): the recycle still fires (`Get-Process VBCSCompiler` returns nothing afterward), preserving the original hygiene fix's behavior — the gate did not disable the recycle wholesale.
- [ ] <!-- verification-only --> `build-queue-status.ps1` surfaces the recycle outcome (recycled vs skipped-concurrent) for the last build.

**MCP Integration Test Assertions:** N/A — process-state and PowerShell logic, no MCP surface.

**Prerequisites:**
- Phase 1: atomic lock + reclaim hardening (so the occupancy read is against a trustworthy `active.lock`, and the queued-concurrent case is already largely prevented).

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — gate `Reset-CompilerServer` on occupancy; docstring update; possibly host the occupancy helper.
- `user/scripts/build-queue.ps1` — provide/expose occupancy (reuse `Get-LiveTicketSeqs`); gate the wrapper recycle (`:399`).
- `user/scripts/build-queue-runner.ps1` — gate the runner recycle (`:148`); extend the `hygiene` result body (`:172-183`).
- `user/scripts/build-queue-status.ps1` — surface the recycle-skipped-concurrent outcome.

**Testing Strategy:** Unit test the occupancy query against synthetic tickets/`active.lock` states. Runtime-verify the gate with two deliberately-overlapped builds (the recycle is machine-global; observe VBCSCompiler before/after). Confirm the sole-build path is unchanged.

**Integration Notes for Next Phase:**
- The occupancy gate is queue-visibility-bound: it CANNOT see off-queue bypass builds. Phase 3 addresses bypass ergonomics; note that easier bypass slightly widens the off-queue window the gate can't cover — the honest mitigation is discouraging casual bypass, not enlarging it. Keep the deny message's "route through the skill" framing primary.

---

### Phase 3: Bypass ergonomics — tolerate a command-prefixed BUILD_QUEUE_BYPASS

**Scope:** Fix the asymmetry where the deny surface is unanchored (a build is caught anywhere in the command) but the bypass token is leading-anchored, so a legitimate `cd "…" && BUILD_QUEUE_BYPASS=1 …` is denied. Make the bypass recognizable when it leads the *build segment* (after a `cd …&&` or similar command prefix), and fix the misleading deny message.

**Deliverables:**
- [ ] `build-queue-enforce.sh` `_BYPASS_RE` (`:76`) recognizes `BUILD_QUEUE_BYPASS=1` when it prefixes the build invocation even behind a leading `cd …&&` (or a `;`/pipeline segment) — i.e. per-segment bypass detection, matching the now-unanchored deny's segment awareness. Keep the scope gate (Cognito worktree) and fail-open contract intact.
- [ ] Deny messages (`_redirect_reason`, `:175-239`) state the constraint explicitly — that the bypass token must lead the build command (or, once fixed, that the recognized forms include a `cd …&&` prefix) — so an agent's first bypass attempt succeeds.
- [ ] Guard against the inverse regression: a real un-bypassed build behind `cd …&&` must STILL be denied (don't let segment-aware bypass detection re-open the enforcement escape the `cd-prefix-bypass` fix closed).
- [ ] Tests: `cd … && BUILD_QUEUE_BYPASS=1 <build>` → allowed; `cd … && <build>` (no token) → denied; bare `BUILD_QUEUE_BYPASS=1 <build>` → allowed (unchanged); `NAME=val BUILD_QUEUE_BYPASS=1 <build>` → allowed (unchanged).

**Minimum Verifiable Behavior:** Piping a `cd "<cognito-worktree>" && BUILD_QUEUE_BYPASS=1 powershell … build-filtered.ps1 …` payload through the hook returns allow (exit 0, no `permissionDecision: deny`), while the same command without the token returns the deny JSON.

**Runtime Verification** *(checked by test — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Hook unit cases: the four bypass/deny combinations above resolve as specified (fed as JSON payloads to the hook, asserting allow vs deny).

**MCP Integration Test Assertions:** N/A — bash PreToolUse hook, no MCP surface.

**Prerequisites:** None (independent of Phases 1-2). Can run in parallel with Phase 4.

**Files likely modified:**
- `user/hooks/build-queue-enforce.sh` — `_BYPASS_RE` (`:76`) segment-aware; deny-message text (`:175-239`).
- Hook test file — location per the `cd-prefix-bypass` spec's Open Question (where hook unit tests live); co-locate the new cases with any existing enforce-hook tests.

**Testing Strategy:** Feed crafted JSON payloads to the hook via stdin and assert allow/deny, exactly as the deny-side is (or should be) tested. No live build needed.

**Integration Notes for Next Phase:**
- This is the coupled Secondary defect from the SPEC. Consider whether it belongs as a follow-up phase on `build-queue-enforce-cd-prefix-bypass` instead (same hook, same regex family) — flagged as a SPEC Open Question; if the user prefers, this phase moves there and this plan drops to 3 phases.

---

### Phase 4: Diagnostics & minor build robustness

**Scope:** Remove two friction contributors surfaced in the investigation: agents reading the empty `<seq>.log` instead of the real `<seq>.build.log`, and the `--no-restore`-after-`obj/`-wipe silent no-op.

**Deliverables:**
- [ ] `/msbuild` + `/mstest` skill docs (`repos/cognito-forms/.claude/skills/{msbuild,mstest}/SKILL.md`) state that for build ops the real transcript is `<seq>.build.log` (and `<seq>.build.err.log`), not the empty `<seq>.log` — so agents read the right file when diagnosing a stale/failed build.
- [ ] `build-filtered.ps1` (`:24-26`) detects the `--no-restore` no-op: when restore is skipped but `project.assets.json` is missing for the target (a wiped `obj/`), it auto-restores (or errors loudly with a clear message) instead of silently building nothing. Keep `--no-restore` the default for the normal incremental case (per SPEC: don't flip the default).
- [ ] Tests: a build against a wiped `obj/` with the default flags either restores-then-builds or fails with the diagnostic — never silently no-ops.

**Minimum Verifiable Behavior:** With `obj/` removed for the target project, a default `/msbuild` (no `-Restore`) either produces an updated DLL (auto-restore fired) or exits non-zero with a message naming the missing `project.assets.json` — it does not report success while producing nothing.

**Runtime Verification** *(checked by manual runtime — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Delete a project's `obj/`, run default `/msbuild`; confirm the target DLL is rebuilt (or a clear restore-needed error), not a silent success with a stale DLL.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (independent). Can run in parallel with Phase 3.

**Files likely modified:**
- `repos/cognito-forms/.claude/skills/msbuild/SKILL.md`, `repos/cognito-forms/.claude/skills/mstest/SKILL.md` — `<seq>.build.log` guidance.
- `user/scripts/build-filtered.ps1` — missing-`project.assets.json` detection (`:24-26` region).

**Testing Strategy:** A scripted build against a wiped `obj/` asserting non-silent-no-op. Doc changes verified by inspection.

**Integration Notes:**
- The `--no-restore` obj-wipe fix is the ONLY restore-related change; the default stays `--no-restore` per the SPEC's proven finding. If the user would rather track the obj-wipe no-op as its own bug dir (SPEC Open Question), drop it from this phase.

---

**Completion (gate-owned):** the bug pipeline's `__mark_fixed__` gate flips SPEC.md **Status:** from Concluded to Fixed and writes `FIXED.md` once all phases' runtime verification passes and the `mcp-coverage-audit` (Locked-Decisions coverage) is satisfied. Do NOT author a checkbox for the status flip / receipt write / ROADMAP mark — those are gate-owned, not deliverables.

## Open Questions
- Where do PowerShell/bash hook unit tests live in this repo (so Phases 1 & 3 land their cases in the right place)? Inherited from the `cd-prefix-bypass` SPEC's Open Question.
- Should Phase 3 (bypass ergonomics) fold into the `build-queue-enforce-cd-prefix-bypass` spec as a follow-up phase instead of living here? (Same hook/regex family.)
- Should Phase 4's `--no-restore` obj-wipe no-op be its own bug dir rather than a phase here?
- Can Vector A be given a deterministic regression test, or is the atomic-write invariant the only assertable guard (the race itself being timing-bound)?

## Review Notes

**Review verdict:** PASS (2026-07-02) — authored directly by the orchestrator (planning doc, not an implementation batch). Mechanical self-review: all Runtime Verification rows carry the canonical `<!-- verification-only -->` marker; no gate-owned STATUS/receipt/archive checkbox rows (completion is a prose gate-owned note); every touchpoint path + line number is audit-verified against current source (2 read-only Explore agents, 2026-07-02); Phase 2 direction reflects the user's locked "occupancy-gate" decision. No MCP surface (harness PowerShell/bash) — MCP assertions correctly N/A.
