# Implementation Phases — Bash-Tool Timeout Tree-Kill Reaps the Detached Build-Queue Runner

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — the entire fix is Windows-only PowerShell build-queue tooling exercised by Pester; per the mcp-testing SPEC's "build tooling / no app integration" untestable class there is no Tauri/MCP-reachable surface. claude-config has no MCP dev-runtime at all.

> **Reconciliation note (fix already landed 2026-07-10).** The crash-safe-release fix this SPEC concluded was implemented out-of-pipeline the same day (see SPEC `## Fix (implemented 2026-07-10)` and the passing `build-queue-runner.Tests.ps1`, 8/8 Pester). These phases faithfully decompose the fix that is **already on disk** so the bug pipeline can reconcile it through `/write-plan` → `/execute-plan` → validation → the gated `__mark_fixed__` receipt. The deliverables below describe landed work; the executor should verify each against the current source and its Pester coverage rather than re-authoring it. (The `is_fixed_unreconciled` gate did not divert this bug because the SPEC recorded the fix under a `## Fix (implemented …)` heading rather than the `**Fixed:**` evidence annotation the gate keys on — noted for harness hardening.)

## Root Cause (from SPEC — all links traced)

Foreground-wrapper timeout tree-kill (exit 143, Trace 3) × unprotected post-build critical section in the runner (Trace 1) × RED-only multi-minute quarantine sweep that widens the kill window from ~1s to minutes (Trace 2). The runner writes `results/<seq>.json` and releases `active.lock` ONLY at the very end of its `finally` block — both sit AFTER the multi-minute hygiene/sweep. An OS kill anywhere after build-exit and before the result write strands the queue: no result ever written, `active.lock` held by a dead pid, `await` returns a misleading 124.

**Fix scope (operator-locked): crash-safe release** — shrink the unprotected window by writing the truthful result IMMEDIATELY after the exit code is known (BEFORE hygiene), so a kill mid-sweep leaves a truthful `hygiene.status: "pending"` result instead of nothing.

### Phase 1: Two-phase crash-safe result write (the operator-locked fix)

**Scope:** Restructure the runner's `finally` block so the truthful build outcome is written the moment the exit code and fidelity classification are known — BEFORE any hygiene work (`Stop-BuildJobTree` → occupancy-gated `Reset-CompilerServer` → the RED-only `Remove-PoisonedArtifacts` sweep). Introduce the fail-open atomic result writer in the hygiene module. The pre-existing inline write remains as the FINAL write that merges real hygiene fields and flips `hygiene.status: pending → complete`. A kill mid-sweep now leaves a truthful pending result that `build-queue-await.ps1` picks up as the real RED outcome instead of 124.

**Deliverables:**
- [ ] `build-queue-hygiene.ps1`: new `Write-BuildQueueResult` — fail-open atomic result writer (temp + `File.Replace`, direct-write fallback) implementing the EARLY write; a Pester-testable reference for the result schema.
- [ ] `build-queue-runner.ps1` `finally` block: crash-safe EARLY write via `Write-BuildQueueResult` with `hygiene.status: "pending"` (real hygiene fields defaulted) once `$exitCode` + fidelity classification are known, guarded so it is skipped when `$exitCode` is unknown.
- [ ] `build-queue-runner.ps1`: `$resultFidelity` / `$counts` / `$durationSeconds` moved into the `finally` (they depend only on the exit code + already-complete logs); `duration_seconds` captured at build exit (exec-run time, hygiene excluded) and reused verbatim by the final write + stats ring.
- [ ] `build-queue-runner.ps1`: FINAL inline write kept INLINE (not routed through `Write-BuildQueueResult`) so the result contract survives a failed hygiene-module dot-source; it merges real hygiene fields (`vbcscompiler_recycled`, `recycle_skipped_reason`, `quarantined_artifacts`, `lockers_reaped`, …) with `hygiene.status: "complete"`.
- [ ] `build-queue-runner.ps1`: `exit 1` (was `exit $null`) on the degraded spawn-exception path where `$exitCode` is unknown.
- [ ] Result-schema doc (runner header) updated with the `hygiene.status: "pending" | "complete"` field and the two-phase contract.
- [ ] Tests: `build-queue-runner.Tests.ps1` — launch the REAL runner detached against a temp StateRoot with a shim hygiene module (real module dot-sourced; `Reset-CompilerServer`/`Stop-DllLockers` overridden for machine safety; `Remove-PoisonedArtifacts` made to block ~120s to model the Cognito RED sweep), a fake RED exec (`exit 1`), then kill the runner with TerminateProcess mid-sweep; assert `results/<seq>.json` EXISTS with truthful `exit_code: 1` + `hygiene.status: "pending"`, `active.lock` honestly still held, and fast-path tests pinning the FINAL write merging real hygiene over the early write (`status: complete`, quarantine/recycle fields, lock released, stats ring appended). Unit tests cover `Write-BuildQueueResult` (atomicity, final-over-early overwrite, legacy no-op field omission, fail-open).

**Minimum Verifiable Behavior:** `Invoke-Pester user/scripts/build-queue-runner.Tests.ps1` — the crash-safe early-write Describe block passes: a runner killed mid-sweep leaves `results/<seq>.json` with `exit_code: 1` and `hygiene.status: "pending"`, and the final-write Describe shows `status: complete` with merged hygiene fields.

**Runtime Verification** *(checked by Pester regression suite — NOT by the implementation agent):*
- [ ] <!-- verification-only --> A detached runner killed (TerminateProcess) mid-`Remove-PoisonedArtifacts` leaves `results/<seq>.json` on disk with `exit_code: 1` and `hygiene.status: "pending"` (truthful RED result survives the untrappable kill).
- [ ] <!-- verification-only --> A runner that completes hygiene normally produces a FINAL result with `hygiene.status: "complete"`, real quarantine/recycle fields merged over the early write, `active.lock` released, and the stats ring appended.
- [ ] <!-- verification-only --> `build-queue-await.ps1 -Seq <n>` after a mid-sweep kill exits **1** re-emitting the authoritative `RESULT=FAIL` banner (reading the early result) instead of exiting 124 with "may still be running".

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface; validation is Pester-only (Windows workstation build tooling).

**Prerequisites:** None (first phase — the core fix).

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — add `Write-BuildQueueResult` (atomic fail-open result writer) near the other queue-state helpers.
- `user/scripts/build-queue-runner.ps1` — restructure the `finally` (:260–:437 region): early write, moved fidelity/counts/duration, final merge write, degraded-path `exit 1`, header schema doc.
- `user/scripts/build-queue-runner.Tests.ps1` — net-new Pester suite (crash-safe early-write + final-merge + `Write-BuildQueueResult` unit tests).

**Testing Strategy:** Pester 5.x against a temp StateRoot with a machine-safe shim hygiene module and a fake RED exec; TerminateProcess the real detached runner mid-sweep to reproduce the exit-143 serving path. No live build, no MCP.

**Integration Notes for Next Phase:**
- The FINAL write stays INLINE (not via `Write-BuildQueueResult`) deliberately — it must survive a failed hygiene-module dot-source; do not "simplify" it to call the helper.
- Lock-release position is UNCHANGED (AFTER hygiene — it serializes hygiene against the next build); a post-early-write kill still strands the lock, self-healed by the existing next-enqueue 3-dead-tick reclaim. This is by design, not a gap.
- `duration_seconds` is exec-run time (runner start → build exit), hygiene excluded — the schema contract Phase 2's counts fix shares the same `logs/<seq>.log` source with.

---

### Phase 2: Adjacent same-serving-path defects (stdout bare-`True` leak + counts sharing violation)

**Scope:** Two defects found ON the same runner serving path while implementing Phase 1, fixed together because both corrupt the truthful result the crash-safe write must emit. (a) The unassigned `Get-SafeValue { Stop-BuildJobTree … }` returns leaked a bare `True` into `logs/<seq>.log`, which the test-counts regex parses. (b) The counts parse read `logs/<seq>.log` via `[System.IO.File]::ReadAllText` (FileShare.Read) — but that file IS the runner's own redirected stdout whose write handle stays open for the runner's lifetime, a deterministic sharing violation that silently nulled `counts` for every live test op (at the old post-hygiene position just as much as at the new early one).

**Deliverables:**
- [ ] `build-queue-runner.ps1`: both unassigned `Get-SafeValue { Stop-BuildJobTree … }` returns (trap + finally) `$null =`-assigned, so no stray `True` reaches `logs/<seq>.log`.
- [ ] `build-queue-runner.ps1`: the test-counts parse opens `logs/<seq>.log` with `FileShare.ReadWrite` (the wrapper live-tail pattern) instead of `ReadAllText`/`FileShare.Read`, so a live test op's counts are read correctly.
- [ ] Tests: `build-queue-runner.Tests.ps1` — the RED-test-op kill test asserts the parsed `counts` are present in the early (pending) result and the `await` banner reports `tests=<n> failed=<k>`; a fast-path test pins the no-bare-`True` stdout guarantee.

**Minimum Verifiable Behavior:** The RED-test-op Pester test shows `counts` populated in the pending result and `build-queue-await.ps1` re-emitting a banner with `tests=5 failed=2`; the fast-path test confirms `logs/<seq>.log` carries no stray `True` line.

**Runtime Verification** *(checked by Pester regression suite — NOT by the implementation agent):*
- [ ] <!-- verification-only --> A RED **test** op killed mid-hygiene produces an early result carrying the parsed `counts`, and `build-queue-await.ps1` reports `tests=<n> failed=<k>` in the `RESULT=FAIL` banner.
- [ ] <!-- verification-only --> `logs/<seq>.log` contains no stray bare `True` line after a normal runner completion (the counts regex is not corrupted by leaked `Stop-BuildJobTree` output).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface; Pester-only.

**Prerequisites:**
- Phase 1: the `finally`-block restructure and the early/final write must exist — these counts/stdout fixes live inside that same restructured region and feed the same result body.

**Files likely modified:**
- `user/scripts/build-queue-runner.ps1` — trap + finally `$null =` assignments (:143, :376) and the FileShare.ReadWrite counts open (:316).
- `user/scripts/build-queue-runner.Tests.ps1` — RED-test-op counts assertions + no-bare-`True` stdout pin.

**Testing Strategy:** Same Pester harness as Phase 1; a fake RED test op emitting a parseable counts line drives the counts assertions, and a normal-completion fast-path test inspects `logs/<seq>.log` for the absence of the leaked `True`.

**Integration Notes for Next Phase:**
- These two fixes are position-independent of the early/late write choice — they were latent at the OLD post-hygiene position too; the crash-safe move merely made a correct counts read newly load-bearing for the early result.
- `build-queue-await.ps1` / `build-queue.ps1` need NO changes: await already polls for the result file (so it returns as soon as the early write lands) and the wrapper's read-merge-write only ever runs after the runner exits (post-final-write), so the two runner writes + the wrapper merge cannot clobber each other.

---

## Completion (gate-owned)

The `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed`, writes `FIXED.md`, and archives the bug dir once the validation tail passes. These phases never author a Status flip / receipt / archive row.
