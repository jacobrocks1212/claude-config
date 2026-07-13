# build-queue foreground run blocks past a recorded terminal outcome — Investigation Spec

> A foreground `/mstest` (`build-queue.ps1`) run emits its terminal "no more work" WARN, yet the
> Bash call keeps running toward the 10-minute tool timeout instead of returning promptly. The
> wrapper's exit is gated on full runner-process liveness (through post-WARN hygiene), not on the
> already-recorded terminal outcome.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-13
**Fixed:** 2026-07-13
**Fix commit:** 87b0579
**Placement:** docs/bugs/build-queue-foreground-wait-blocks-past-terminal-outcome
**Related:** `docs/bugs/_archive/subagent-backgrounds-verification-ends-turn-before-green` (the `build-queue-await.ps1` turn-end gate — the *background* path that DOES key on the result file), `docs/features/build-queue-generalization` (hygiene profiles / poison-sweep), `docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash` (origin of the exit-3 `no-output` WARN)

<!-- Status lifecycle: Concluded → root cause traced (serving path cited file:line, fix site on
     path), ready for /plan-bug to author PHASES.md. -->

---

## Verified Symptoms

1. **[VERIFIED]** A **foreground** `/mstest` run (invoked directly, NOT `run_in_background` + `build-queue-await.ps1`) emitted `WARN: No test results captured (zero tests matched filter or summary not parsed)` and then **did not return promptly** — the Bash call stayed alive toward the 10-minute tool timeout instead of exiting right after the terminal WARN. — confirmed with the user (AskUserQuestion, 2026-07-13) against the screenshot (seq=1115, op=mstest, filter `FullyQualifiedName~EntityMetaServiceTests.UserFormMeta.Diag_GetArchivedForms_SupportUser`).
2. **[REPORTED]** The exact stall duration is not measured — the screenshot captured `(1m 0s · timeout 10m)` at the moment the WARN appeared. The user's framing ("didn't exit", "so the agent knows ASAP") is that control was not returned promptly after the terminal signal; the wall-clock ceiling is the 10-minute Bash timeout.

## Reproduction Steps

1. In a Cognito Forms worktree, run `/mstest` **in the foreground** (a single Bash call, `timeout ≈ 600000`) with a filter that matches zero tests OR whose `dotnet test` run produces no parseable summary — e.g.:
   ```
   REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass -File \
     "$HOME/.claude/scripts/build-queue.ps1" -Op mstest \
     -Exec "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -Filter "FullyQualifiedName~SomethingThatMatchesNothing"
   ```
2. Watch the streamed log: `dotnet test` runs, then `test-filtered.ps1` prints `WARN: No test results captured …` (exit 3) or `WARN: Filter matched zero tests …` (exit 5) and the grandchild exits.
3. Observe: the foreground Bash call does **not** return at the WARN. It continues while the detached runner finishes its post-WARN hygiene, then finally prints the RESULT banner and returns.

**Expected:** Once the run's terminal outcome is recorded (the runner's early `results/<seq>.json` write / the terminal WARN), the foreground wrapper surfaces the authoritative `build-queue: seq=… RESULT=…` banner and **returns promptly**; residual hygiene finishes without holding the agent's turn.
**Actual:** The foreground wrapper blocks on full runner-process liveness (`build-queue.ps1:508`), staying alive through the runner's post-WARN hygiene phase (compiler recycle + a full-worktree poison-DLL sweep) before it returns.
**Consistency:** Deterministic for any foreground run whose runner does non-trivial post-exec hygiene (any non-zero test exit — 3/5 — triggers the build-op poison sweep; see Theory 2).

## Evidence Collected

### Source Code

**Terminal WARN is emitted by the grandchild, which exits immediately (no hang here):**
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1:204` — `$outcomeCode = Get-TestOutcomeExitCode …` (computed AFTER `dotnet test` completes; needs `$dotnetExit`).
- `test-filtered.ps1:205-208` — WARN branches: exit 5 → `"Filter matched zero tests (summary reported Total=0)"`; exit 3 → `"No test results captured (zero tests matched filter or summary not parsed)"` (the string in the screenshot).
- `test-filtered.ps1:210` — `exit $outcomeCode`. **Unconditional exit right after the WARN — no loop/poll/wait in the exec.**
- `Get-TestOutcomeExitCode` (`test-filtered.ps1:45-55`): line 52 `-not $SummarySeen -and $ResultLineCount -eq 0 → 3`; line 53 `$SummarySeen -and $Total -eq 0 → 5`.

**The runner records the terminal outcome EARLY (before hygiene):**
- `build-queue-runner.ps1:192-194` — `$proc.WaitForExit()` / `$exitCode = $proc.ExitCode` (grandchild exit captured; coerced to non-null).
- `build-queue-runner.ps1:285-290` — fidelity classification: exit 3 → `no-output`, exit 5 → `no-tests-matched`, else `verified`.
- `build-queue-runner.ps1:355-369` — **crash-safe EARLY write** of `results/<seq>.json` (guarded only by `if ($null -ne $exitCode)`; status `pending`, real `exit_code` + `result_fidelity`) — fires **before any hygiene**.
- `build-queue-runner.ps1:396-435` — final write flips status to `complete`; then `exit` (~:470).

**The foreground wrapper waits on the RUNNER PROCESS, not the recorded result — the gap:**
- `build-queue.ps1:508` — `while (-not $proc.HasExited) { … Start-Sleep 500ms }` — the tail loop's lifetime == the detached runner's lifetime. It does **not** watch `results/<seq>.json` or the WARN.
- `build-queue.ps1:551` — `$exitCode = $proc.ExitCode` read (and banner emitted) only **after** the loop, i.e. after the runner fully exits.

**Post-WARN hygiene that keeps the runner (and thus the wrapper) alive:**
- `build-queue-runner.ps1:376` `Stop-BuildJobTree`; `:377-384` `Reset-CompilerServer` (VBCSCompiler recycle, occupancy-gated; the `dotnet` profile `mstest` uses).
- `build-queue-runner.ps1:386-389` — poison sweep gate: `$buildFailed = … ($exitCode -ne 0) …` → **TRUE for a zero-result test op** (exit 3/5 are non-zero) → `Remove-PoisonedArtifacts` (`build-queue-hygiene.ps1:821`) walks the whole worktree's `bin/`+`obj/` — for a *test* op that produced no compiled output to poison. (See Theory 2.)

### Runtime Evidence
Single screenshot (seq=1115): `build-queue: enqueued as seq=1115 (op=mstest, lane=fast)` → `build started (pid=22428…)` → `Running tests (filter: …)…` → `WARN: No test results captured …` → `(1m 0s · timeout 10m)` foreground Bash spinner still active. No `results/<seq>.json` / runner-log artifact was captured for this seq; exact post-WARN duration unmeasured (Theory 2 magnitude is `asserted`, not runtime-confirmed).

### Git History
Recent build-queue fixes (all touching this exact chain): `ae12a74` crash-safe two-phase result write (the EARLY write this fix leans on), `00b210a` await primitive + turn-end gate (the *background* path that already keys on `results/<seq>.json`), `c895e8d` zero-match distinct `no-tests-matched` fidelity, `7a503f8` no-output classify.

### Related Documentation
- `mstest/SKILL.md:43-49` — §4 background-enqueue contract: `run_in_background: true` + `build-queue-await.ps1 -Seq <N>`; `enqueued as seq=N` is not an outcome. **The background path already terminates promptly on the result file — only the foreground wrapper has this gap.**
- Root `CLAUDE.md` build-queue rows — authoritative one-line banner contract; hygiene profile registry.

## Theories

### Theory 1: Foreground wrapper's exit is gated on full runner lifetime, not the recorded terminal outcome — **[traced]**
- **Hypothesis:** The foreground wrapper stays alive after the terminal WARN because `build-queue.ps1:508` blocks on `$proc.HasExited` (runner-process liveness) and only surfaces the banner post-loop (`:551`). The runner's terminal outcome is already durably recorded by its EARLY `results/<seq>.json` write (`build-queue-runner.ps1:355-369`) well before the runner exits, but the foreground path never consults it — unlike `build-queue-await.ps1:76-91`, which polls exactly that file and returns promptly.
- **Serving path (surface → source):**
  ```
  foreground Bash still running after WARN                         (surface)
    → build-queue.ps1:508   while (-not $proc.HasExited)           ← wait bound to runner lifetime, ignores recorded result
    → build-queue.ps1:551   $exitCode = $proc.ExitCode + banner    (only after loop)
    → build-queue-runner.ps1:192  WaitForExit(grandchild) → exit captured
    → build-queue-runner.ps1:355-369  EARLY results/<seq>.json write   ← terminal outcome ALREADY recorded here
    → build-queue-runner.ps1:376-389  post-WARN hygiene (recycle + poison sweep)  ← extends runner lifetime
    → build-queue-runner.ps1:~470     runner exit → loop at :508 ends → wrapper returns
  ```
- **Fix site (ON the path):** `build-queue.ps1:508` — make the tail loop terminal-aware: break as soon as the runner's authoritative `results/<seq>.json` (early write) is present / the terminal banner is composable, emit the banner, and return; let residual hygiene finish detached. Mirrors the proven `build-queue-await.ps1` result-file poll. This is the node that holds the surface alive, so the fix is consumed on the symptom's serving path.
- **Supporting evidence:** background path terminates promptly on the same recorded outcome (`await.ps1:76-91`); the early write is guaranteed for any known exit code (`:355-369`). Both agents' independent traces converge.
- **Contradicting evidence:** none for the structural claim. The DURATION magnitude (whether it truly nears 10m) is not measured — but the symptom (does not return promptly after the terminal signal) holds regardless of magnitude.
- **Status:** Confirmed (structural, code-traced).

### Theory 2: Poison-DLL sweep mis-gated for test ops inflates the post-WARN hygiene window — **[asserted / likely]**
- **Hypothesis:** `build-queue-runner.ps1:386` computes `$buildFailed = ($exitCode -ne 0)`, which is TRUE for a zero-result **test** op (exit 3/5), so `Remove-PoisonedArtifacts` (`build-queue-hygiene.ps1:821`) walks the entire worktree `bin/`+`obj/` tree — pointless work for a test op (it compiles no DLLs), and a plausible dominant contributor to the post-WARN delay.
- **Supporting evidence:** the gate is exit-code-only, with no `$isBuildOp`/`$isTestOp` discriminator; poison DLLs are a build-op concern (the profile poison-sweep is `dotnet-dll`).
- **Contradicting evidence:** magnitude is unmeasured — the sweep cost depends on worktree `bin`/`obj` size; the compiler recycle (`:377-384`) also contributes. Runtime-coupled; not confirmed by an artifact.
- **Status:** Likely — a secondary, cheap-to-fix contributor. NOT the primary cause (Theory 1 is the structural gap; even with zero hygiene, the foreground wrapper would still wait on `$proc.HasExited`).

## Proven Findings

- The terminal WARN and grandchild exit are prompt (`test-filtered.ps1:210`) — **the exec does not hang.** (Both traces, confirmed.)
- The terminal outcome is durably recorded EARLY, before hygiene (`build-queue-runner.ps1:355-369`) — the same file the background `await` path returns on.
- The foreground wrapper alone ignores that recorded outcome and blocks on full runner-process liveness (`build-queue.ps1:508`) — **the primary defect (Theory 1, traced).**

## Desired Behavior (confirmed with user)

- **Return + banner ASAP** (all terminal no-work outcomes, generalized across ops — stale-DLL exit 4, no-output exit 3, zero-match exit 5, and normal pass/fail): once the authoritative outcome is recorded, the foreground wrapper surfaces the RESULT banner and returns promptly; residual hygiene finishes without holding the turn.
- **Make terminal WARNs louder/distinct**: every terminal "no more work" warning should carry an unambiguous terminal marker the agent can key on immediately (so the signal is legible even before the banner).
- Explicitly IN SCOPE per the user: generalize to all terminal outcomes, not just the test-op zero-result path.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Foreground wait model (primary) | `user/scripts/build-queue.ps1` (~:508, :551) | Blocks on runner liveness instead of recorded terminal outcome — the root cause of the not-returning-promptly symptom. |
| Runner post-exec hygiene (secondary) | `user/scripts/build-queue-runner.ps1` (:386-389 poison-sweep gate; :376-384 recycle) | Mis-gated build-op sweep runs for zero-result test ops, inflating the post-WARN window. |
| Terminal WARN legibility | `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (:205-208); banner (`build-queue-hygiene.ps1` `Format-BuildQueueBanner`) | "Louder/distinct" terminal markers so the agent keys on the terminal signal ASAP. |
| Regression fixtures | `user/scripts/build-queue-await.Tests.ps1`, `build-queue-hygiene.Tests.ps1` | Foreground early-return + test-op-hygiene-skip need Pester coverage. |

## Open Questions

- Return-vs-detach mechanics: after an early-return banner, should residual hygiene continue in the detached runner (already detached — likely free) and does the wrapper still need to perform its own release/recycle (`build-queue.ps1:605-616`)? Confirm the release ownership so a promptly-returning wrapper never orphans `active.lock` or skips the compiler recycle. (Design detail for `/plan-bug`.)
- Exact terminal-marker form for "louder WARNs" — a distinct stdout token vs. relying on the existing RESULT banner as the sole terminal marker. (Design detail for `/plan-bug`.)
