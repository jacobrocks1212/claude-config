# Implementation Phases — build-queue foreground wait blocks past a recorded terminal outcome

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete

**MCP runtime:** not-required — claude-config PowerShell harness scripts; no `src-tauri/` and no `package.json`, so no app runtime or MCP-reachable surface. Verification is Pester on the extracted serving-path helpers (the symptom's actual serving path).

### Phase 1: Foreground early-return on recorded terminal outcome (primary)

**Scope:** The foreground `build-queue.ps1` tail loop (`while (-not $proc.HasExited)`, ~:508) bound the wrapper's lifetime to the detached runner's whole lifetime — so after the runner recorded its terminal `results/<seq>.json` (the crash-safe EARLY write, `build-queue-runner.ps1:355-369`, BEFORE hygiene) the wrapper kept running through post-outcome hygiene (compiler recycle + poison sweep) before returning, stalling the foreground Bash toward the 10-min timeout. Converge the foreground path onto the proven result-file-keyed model already used by `build-queue-await.ps1`.

**Deliverables:**
- [x] Extract `Wait-ForRecordedOutcome` into `build-queue-hygiene.ps1` (pure, Pester-testable): polls `results/<seq>.json` via the shared `Read-WithRetry`, runs an injected `-TailAction` each poll (keeps live-tailing the log), returns `@{Outcome; Result; ExitCode}` the instant a terminal result with a readable non-null `exit_code` is present (`result-recorded`), else `process-exited` when the runner dies first with no readable result. A null `exit_code` is treated as not-ready (no false green). Injected `-IsProcessAlive`/`-Sleep`/`-Now` seams for hermetic tests.
- [x] Rewrite `build-queue.ps1`'s foreground wait: replace the `while (-not $proc.HasExited)` loop with a `Wait-ForRecordedOutcome` call driven by a script-scoped `$streamTail` closure (log cursor advanced across polls). On `result-recorded`, compose the authoritative banner from the recorded result (mirroring `build-queue-await.ps1`) and `exit` PROMPTLY — running NO wrapper release/recycle (the detached runner owns them; running them concurrently would race the live runner). The legacy results-merge / `active.lock` release / recycle / banner block now runs ONLY on the fallback path (runner exited without recording a readable result — a hard crash).
- [x] Generalize across every recorded terminal outcome — normal pass/fail, stale-DLL (exit 4), no-output (exit 3), zero-match (exit 5) — since the trigger is uniformly "a terminal result is recorded".
- [x] <!-- verification-only --> Serving-path regression tests (`build-queue-foreground-outcome.Tests.ps1`): `Wait-ForRecordedOutcome` returns `result-recorded` WITHOUT consulting process-liveness or sleeping when the result is already present (the exact symptom — proves it no longer waits for full runner exit); PASS / no-output exit-3 / NO-TESTS-MATCHED exit-5 banner re-emission; `process-exited` fallback; null-`exit_code` treated not-ready.

**Minimum Verifiable Behavior:** `Invoke-Pester build-queue-foreground-outcome.Tests.ps1` green (15/0); the "returns without consulting process-liveness or sleeping" It-block FAILS against the pre-fix process-liveness loop and passes after. `build-queue-await.Tests.ps1` (8/0) confirms banner parity / no regression on the sibling background path.

#### Implementation Notes (2026-07-13)

**Status:** Fixed
**Review verdict:** PASS.

- Finalization ownership verified safe: the detached runner independently does the FINAL result write (`build-queue-runner.ps1:407-435`), the seq-scoped `active.lock` release (`:446-464`), and the occupancy-gated VBCSCompiler recycle (`:377-384`). Pre-fix the wrapper only reached its own release AFTER `$proc.HasExited` — i.e. after the runner had already finalized — so the wrapper's release was always redundant cleanup. Early-return skips that redundant work; the fallback path retains it for the hard-crash case.
- Gate: `Invoke-Pester build-queue-foreground-outcome.Tests.ps1` → 15 passed, 0 failed; `build-queue-await.Tests.ps1` → 8/0; `build-queue-hygiene.Tests.ps1` → 178/0. All three edited files `Parser::ParseFile` clean.

### Phase 2: Build-op-only poison-DLL sweep (secondary)

**Scope:** `build-queue-runner.ps1:~386` computed `$buildFailed = ($exitCode -ne 0)`, TRUE for a zero-result TEST op (exit 3/5), so `Remove-PoisonedArtifacts` walked the whole worktree `bin/`+`obj/` for a `--no-build` test op that compiles nothing — pointless work that inflated the post-outcome window.

**Deliverables:**
- [x] Extract `Test-ShouldSweepPoisonedArtifacts` into `build-queue-hygiene.ps1` — the build-op poison-sweep predicate (`IsBuildOp ∧ buildFailed ∧ dotnet-dll ∧ worktree`).
- [x] Retarget the runner's sweep gate onto the helper (fail-open to an `$isBuildOp`-gated inline predicate if the hygiene module is absent). Build-op behavior byte-identical.
- [x] <!-- verification-only --> Tests: 8 `Test-ShouldSweepPoisonedArtifacts` cases (test op exit 3/5 → no sweep; failed build op → sweep; green build/test → no; non-dotnet-dll → no; no worktree → no).

**Minimum Verifiable Behavior:** the 8 gate It-blocks green within `build-queue-foreground-outcome.Tests.ps1`.

#### Implementation Notes (2026-07-13)

**Status:** Fixed
**Review verdict:** PASS.

- Files modified: `user/scripts/build-queue.ps1`, `user/scripts/build-queue-hygiene.ps1`, `user/scripts/build-queue-runner.ps1`, `CLAUDE.md`, `user/scripts/build-queue-foreground-outcome.Tests.ps1` (new). Shipped in commit `a0b97bf`.
