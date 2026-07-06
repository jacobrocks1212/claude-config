# Implementation Phases — Build Queue Copy-Lock Stale-DLL False Success

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a PowerShell/Python harness repo with no Tauri/MCP surface; verification is Pester + direct script execution. (MCP tool-existence audit: no-op — no `repos/cognito-forms/.claude/skill-config/mcp-tool-catalog.md`.)

## Validated Assumptions

- **`dotnet build` can log "Build FAILED" while exiting 0 under MSB3027.** VALIDATED by the captured seq-346 incident (SPEC Verified Symptom 1): the queue recorded `exit_code: 0` while the build log read "Build FAILED, 2 Error(s)" (MSB3027/MSB3021). The Phase-1 log-parse override is grounded in observed runtime, not a code read.
- **Modern `dotnet test` summary format is `Passed!  - Failed: X, Passed: Y, Skipped: Z, Total: N, Duration: ...`.** OBSERVED in the second session's screenshot (SPEC Verified Symptom 5). Phase 3's regex targets this literal form and re-confirms against a live `/mstest` run.
- **Runtime-coupled, not yet validated (in-phase spikes):** (P2) that reaping the prior-run locker actually frees the `bin/Debug` handle so the copy succeeds; (P3) that the extended regex matches real emitted output end-to-end. Each carries a Runtime Verification spike below.

## Touchpoint Audit (verified — Explore agent, read-only)

| Planned file | Exists? | Real symbols (line#) | Action | Reuse / refactor directive |
|--------------|---------|----------------------|--------|----------------------------|
| `repos/cognito-forms/.claude/scripts/build-filtered.ps1` | yes | `dotnet build` stream (L32); only explicit `exit 1` on git error (L16); **no `$LASTEXITCODE` capture** | refactor | Capture `$LASTEXITCODE` after L32 and `exit` it; add failure-signature scan over the streamed lines. Do NOT rewrite the filter pipeline. |
| `user/scripts/build-queue-hygiene.ps1` | yes | `Get-SafeValue` (39), `Remove-PoisonedArtifacts` (330–437; 0-byte L400, MZ-header L403–416), `Reset-CompilerServer` (268), `Stop-BuildJobTree` (221), `New/Add` job (119/170), P/Invoke class (46–117) | refactor+create | Add `Test-BuildLogFailure` (P1) and `Get-DllLockers`/`Stop-DllLockers` (P2) as NEW functions ~L330. Reuse `Get-SafeValue` fail-open wrapper and the P/Invoke pattern; do NOT duplicate the job-object machinery. |
| `user/scripts/build-queue-runner.ps1` | yes | `$exitCode` (89–90), `$buildFailed` (95), `Remove-PoisonedArtifacts` gate (96–98), `$resultFidelity` (101–107), `$resultBody`/hygiene JSON + atomic write (118–135) | refactor | Insert log-parse override after L90 (build ops); insert locker-reap before `New-BuildJobObject` (L83); add `build_fidelity` + `lockers_reaped` to the hygiene block (L118–127). Reuse the existing `$resultFidelity`/hygiene shape — mirror it, don't restructure. |
| `repos/cognito-forms/.claude/scripts/test-filtered.ps1` | yes | summary regex (L60: `'Test Run (Passed\|Failed)\|^Total tests:\|^\s+Passed\s*:\|^\s+Failed\s*:'`), `resultLineCount` (22/39/46), `summarySeen` (23/62), exit-3 (74–76), `--no-build` (L55) | refactor | Extend the L60 alternation; keep the exit-3 contract (genuine no-output only). Add staleness guard near L55. Do NOT remove `--no-build` (that's the queue's build/test split). |
| `user/scripts/build-queue-status.ps1` | yes | hygiene read/render (138–180) | refactor | Extend the existing hygiene render loop to print `build_fidelity` + `lockers_reaped`; the block already iterates hygiene fields. |
| `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` | yes | thin execution wrapper (1–37); no recovery prose | refactor | Add concise recognition/recovery prose; point at repo `CLAUDE.local.md` for depth. |
| `repos/cognito-forms/.claude/skills/mstest/SKILL.md` | yes | thin wrapper; `--no-build` noted L11; no staleness prose | refactor | Add stale-DLL / `--no-build` recovery prose. |
| `user/scripts/build-queue-hygiene.Tests.ps1` | yes | Pester v5; Describe blocks for surface, fail-open, Locked-Decision guards, `Remove-PoisonedArtifacts` | refactor | Add `Describe` blocks for `Test-BuildLogFailure`, `Get-DllLockers`/`Stop-DllLockers`, and (new file or here) the test-summary regex. Reuse the existing fixtures (0-byte/truncated-PE) pattern. |

No net-new paths outside those stamped `create` (`Test-BuildLogFailure`, `Get-DllLockers`, `Stop-DllLockers` are new functions inside an existing file). No genuine design fork surfaced — mechanical grounding only.

---

### Phase 1: Build honesty — a failed build reports failure

**Scope:** Stop the queue from certifying a copy-lock failure as success. Two seams, shipped together: (a) `build-filtered.ps1` propagates the real MSBuild exit code and detects the "exited-0-but-FAILED" case; (b) the runner overrides a bogus exit-0 on build ops so the existing `$buildFailed`-gated quarantine actually fires.

**Deliverables:**
- [x] `build-filtered.ps1`: capture `$LASTEXITCODE` immediately after the `dotnet build` invocation (L32) and `exit` with it (replacing the implicit fall-off-end exit 0).
- [x] `build-filtered.ps1`: scan the streamed build output for failure signatures — `Build FAILED`, `error MSB3027`, `error MSB3021`, and a nonzero `\d+ Error\(s\)` summary — and force a nonzero exit when any fire even if `dotnet` returned 0.
- [x] `build-queue-hygiene.ps1`: new `Test-BuildLogFailure` function (~L330) — pure, reads a captured build log (or line array) and returns a typed result (`$true` + matched signature) using the `Get-SafeValue` fail-open pattern. No side effects.
- [x] `build-queue-runner.ps1`: after `$exitCode` is read (L89–90), for build ops (`$execLeaf -match 'build-filtered\.ps1$'`) call `Test-BuildLogFailure` on the run's log; if it reports failure, set `$exitCode`/`$buildFailed` to failure so the L96–98 quarantine runs. Add a `build_fidelity` field (`verified` | `log-failure-override` | `n/a`) to the hygiene block (L118–127), mirroring `$resultFidelity`.
- [x] Tests: extend `build-queue-hygiene.Tests.ps1` with a `Describe 'Test-BuildLogFailure'` block — asserts the captured seq-346-style MSB3027 log → failure, a clean "Build succeeded" log → no failure, and fail-open on unreadable input.

**Minimum Verifiable Behavior:** `Invoke-Pester user/scripts/build-queue-hygiene.Tests.ps1` passes the new `Test-BuildLogFailure` block; feeding a saved MSB3027 build log through the runner's override path yields `exit_code != 0` and a non-empty `quarantined_artifacts`.

**Runtime Verification** *(checked by manual run — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Drive `build-filtered.ps1` against a project whose `bin/Debug` DLL is locked (repro the MSB3027 case) and confirm it exits nonzero (the pre-fix baseline exits 0).

**MCP Integration Test Assertions:** N/A — no runtime-observable MCP surface (harness scripts).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status** and writes `FIXED.md` once the feature's phases verify; do not author status/receipt checkboxes here.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `repos/cognito-forms/.claude/scripts/build-filtered.ps1` — exit-code capture + failure-signature scan.
- `user/scripts/build-queue-hygiene.ps1` — new `Test-BuildLogFailure`.
- `user/scripts/build-queue-runner.ps1` — log-parse override + `build_fidelity` field.
- `user/scripts/build-queue-hygiene.Tests.ps1` — new Describe block.

**Testing Strategy:** Pester unit test for `Test-BuildLogFailure` (pure function, easy to fixture from a captured log). Runner override tested by pointing it at a synthetic log; build-filtered exit propagation confirmed by the manual runtime row (a real locked-DLL build).

**Integration Notes for Next Phase:** `build_fidelity` is now a hygiene field — Phase 4 surfaces it. The override makes copy-lock failures VISIBLE as failures; Phase 2 makes them not happen in the first place. The two are independent (this phase = honesty, Phase 2 = prevention).

**Implementation Notes (2026-07-01):**
- **Work completed (WU-1/2/3, all deliverables):** `build-filtered.ps1` now sets `$buildLogFailure` on any streamed `Build FAILED`/`error MSB3027`/`error MSB3021`/nonzero `N Error(s)` line, captures `$buildExit = $LASTEXITCODE` after the stream, computes `$effectiveExit` (log-failure OR nonzero → nonzero, else 0), and `exit $effectiveExit` is now the LAST statement (a `-Test` run max-severity-combines its own exit). `build-queue-hygiene.ps1` gained the pure `Test-BuildLogFailure -Log <string|string[]>` → `@{failed; signature}`, Get-SafeValue-wrapped fail-open. `build-queue-runner.ps1` hoists `$execLeaf`/`$isBuildOp`, redirects a build op's child stdout to `logs/<seq>.build.log`, and after `$exitCode = $proc.ExitCode` overrides `$exitCode=1`+`$buildFailed=$true` when `Test-BuildLogFailure` reports failure on an exit-0 build — BEFORE the `finally` quarantine gate.
- **Integration seam (verified by read):** the override's `$exitCode=1` survives into the `finally`, where `$buildFailed` is *recomputed* from `$exitCode` (L141) → the existing `Remove-PoisonedArtifacts` quarantine fires. `build_fidelity` (`log-failure-override`|`verified`|`n/a`, initialized `n/a` up front) sits in the hygiene `[ordered]@{}` block alongside `result_fidelity`.
- **Files modified:** `repos/cognito-forms/.claude/scripts/build-filtered.ps1` (130L), `user/scripts/build-queue-hygiene.ps1` (519L), `user/scripts/build-queue-hygiene.Tests.ps1` (200L, +9 `Test-BuildLogFailure` tests), `user/scripts/build-queue-runner.ps1` (194L).
- **Gate:** `Invoke-Pester build-queue-hygiene.Tests.ps1` → 22 passed / 3 failed / 25 total. The 3 failures (`Add-ProcessToBuildJob`/`Stop-BuildJobTree`/`Reset-CompilerServer` zero-handle) are PRE-EXISTING Job-Object sandbox quirks — verified 13/3/16 on the stashed baseline (delta = exactly the +9 new passing tests, zero new failures). All parse-checks PARSE OK.
- **Pitfall:** the runner-override end-to-end (`Start-Process`/real `$proc`) is not cleanly Pester-unit-testable without spawning a real child; the pure classifier is exhaustively unit-tested and the override decision is a 6-line if/else composed from it. End-to-end is owned by the Phase-1 manual `<!-- verification-only -->` runtime row (a real locked-DLL build).
- **Plan-part-1 verify/reconcile (2026-07-06):** ground-truth re-verified on the work branch that all three WU deliverables are present and committed — `build-filtered.ps1` `$buildLogFailure`/`$buildExit`/`$effectiveExit`+`exit $effectiveExit` (L34/65/70-74/130), `Test-BuildLogFailure` in `build-queue-hygiene.ps1` (L1339-1417) with the `Describe 'Test-BuildLogFailure'` block (Tests L143-200: seq-346 MSB3027 shape→failure, clean→no-failure, fail-open null/empty/non-string), and the runner override + `build_fidelity` field in `build-queue-runner.ps1` (L160/168/179/192-194/254). `plans/all-phases-copy-lock-part-1.md` WU boxes ticked + frontmatter flipped `Ready`→`Complete`. Pester gate is Windows/PowerShell-only (no `pwsh` on the Linux cloud host) — the green run (22 passed / 3 pre-existing Job-Object sandbox failures) is recorded in the 2026-07-01 notes above; the manual `<!-- verification-only -->` runtime row (L44) stays unchecked, owned by manual Windows verification.

---

### Phase 2: Copy-lock prevention — reap the prior-run locker before the copy

**Scope:** Kill the leftover `testhost`/`dotnet` process holding a handle on the worktree's `bin/Debug` DLLs *before* the build's copy step, so the copy succeeds instead of failing MSB3027. Scoped to the worktree's own artifacts — never a global process kill (honors the hygiene work's Locked Decision 1).

**Deliverables:**
- [x] `build-queue-hygiene.ps1`: new `Get-DllLockers -WorktreeRoot` (~L513) — enumerate processes holding handles on `bin/Debug/**/*.dll` under the worktree. Prefer the Windows **Restart Manager** API (`RmStartSession`/`RmRegisterResources`/`RmGetList`) via `Add-Type` P/Invoke (reuse the existing native-methods pattern); return a typed locker list. Fail-open via `Get-SafeValue`.
- [x] `build-queue-hygiene.ps1`: new `Stop-DllLockers` (~L658) — terminate only the lockers `Get-DllLockers` returned that are within/for this worktree; never touch VBCSCompiler or out-of-worktree processes. Return the reaped PIDs.
- [x] `build-queue-runner.ps1`: call the reap before the build child launches (`Start-Process`, guarded on `$isBuildOp` + non-empty `$Worktree`); record `lockers_reaped` (PID list) in the hygiene block.
- [x] Tests: `build-queue-hygiene.Tests.ps1` — `Describe 'DLL Locker Reap'`: fail-open on a bad/absent worktree, no-op when nothing is locked, and (fixture) a spawned process holding a temp-file handle is identified by `Get-DllLockers` and freed by `Stop-DllLockers`.

**Minimum Verifiable Behavior:** the new `Describe 'DLL Locker Reap'` Pester block passes, including the spawned-process fixture where `Stop-DllLockers` frees a held handle.

**Runtime Verification** *(checked by manual run — NOT by the implementation agent):*
- [ ] <!-- verification-only --> **Runtime spike (must observe the running system, not a code trace):** reproduce a held `bin/Debug` lock (leftover `testhost`), run a build through the queue, and confirm (a) the locker is reaped before the copy and (b) the build's copy now succeeds (fresh `bin/Debug` timestamp) rather than tripping MSB3027. Record the observed PIDs + timestamps as evidence.

**MCP Integration Test Assertions:** N/A — harness scripts.

**Prerequisites:** Phase 1 (edits the same two files; serialize the `build-queue-hygiene.ps1` / `build-queue-runner.ps1` edits after Phase 1 to avoid clobber — one writer per file).

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — `Get-DllLockers` / `Stop-DllLockers`.
- `user/scripts/build-queue-runner.ps1` — pre-build reap call + `lockers_reaped` field.
- `user/scripts/build-queue-hygiene.Tests.ps1` — reap Describe block.

**Testing Strategy:** Pester with a spawned helper process holding a real file handle (Restart Manager reports it); assert identification + termination + fail-open. The end-to-end "copy now succeeds" claim is runtime-coupled → the spike row above, not a unit test.

**Integration Notes for Next Phase:** `lockers_reaped` joins the hygiene block for Phase 4 surfacing. Highest-risk phase — if Restart Manager P/Invoke proves flaky, the scoped `Get-Process testhost,dotnet` + worktree-path filter is the documented fallback (still never global).

**Implementation Notes (2026-07-01):**
- **Work completed (WU-4/WU-5, all deliverables):** `build-queue-hygiene.ps1` gained `Get-DllLockers -WorktreeRoot` (~L513) and `Stop-DllLockers -WorktreeRoot` (~L658). `Get-DllLockers` enumerates `bin/Debug/**/*.dll` under the worktree and resolves lockers via the **Windows Restart Manager** (`RmStartSession`→`RmRegisterResources`→`RmGetList` two-call size-then-fill), extending the existing `BuildQueueHygiene.NativeMethods` `Add-Type` block (one class, no duplicate P/Invoke). `Stop-DllLockers` reaps only the reported in-worktree lockers, EXEMPTs VBCSCompiler by name (Locked Decision 1), never a global/out-of-worktree kill (Locked Decision 2), returns the reaped `[int[]]`. Both bodies wrapped `Get-SafeValue { … } @()` (fail-open to empty). **Shipped path: Restart Manager** — the spawned-handle fixture worked reliably, so the documented `Get-Process testhost,dotnet` fallback was NOT needed.
- **Runner wiring (WU-5):** `build-queue-runner.ps1` (204L) reaps before the build child launches — `if ($isBuildOp -and -not [string]::IsNullOrWhiteSpace($Worktree)) { $lockersReaped = Get-SafeValue { @(Stop-DllLockers -WorktreeRoot $Worktree) } @() }` at L113-115, placed after the log-redirect block and BEFORE `$proc = Start-Process` (L117) so the leftover lock is cleared before MSBuild's copy step. `lockers_reaped` added to the hygiene `[ordered]@{}` block + documented in the results-schema doc-comment.
- **Files modified:** `user/scripts/build-queue-hygiene.ps1` (803L), `user/scripts/build-queue-hygiene.Tests.ps1` (357L, +9 `DLL Locker Reap` tests incl. spawned-handle fixture), `user/scripts/build-queue-runner.ps1` (204L).
- **Gate:** `Invoke-Pester build-queue-hygiene.Tests.ps1` → 32 passed / 3 failed / 35 total. The 3 failures are the SAME pre-existing Job-Object sandbox quirks carried from Phase 1 (`Add-ProcessToBuildJob`/`Stop-BuildJobTree` zero-handle, `returns a [bool]`) — zero new failures (delta = exactly the +9 new passing + the WU-3 field). PARSE OK.

---

### Phase 3: Test honesty — a passing run certifies green

**Scope:** Fix `test-filtered.ps1` so a genuinely-passing modern `dotnet test` run is recognized (real pass/fail count, no spurious exit-3), and refuse/warn when `/mstest --no-build` would run a stale `bin/Debug` DLL.

**Deliverables:**
- [x] `test-filtered.ps1`: extend the summary regex to also match modern output — `Passed!  - Failed: X, Passed: Y, Skipped: Z, Total: N` and the `Failed! - ...` variant — so `summarySeen` sets and `resultLineCount` reflects the real counts (via pure `Test-SummaryLine` helper). Preserve the exit-3 contract (fires ONLY on genuine zero-output).
- [x] `test-filtered.ps1`: emit a parsed pass/fail/total line to the filtered output so `/mstest` surfaces a real count.
- [x] `test-filtered.ps1`: staleness guard (pure `Test-StaleTestDll`, wired into `Invoke-Main` before `dotnet test`) — if the target `bin/Debug` test DLL is missing/older than its source project (or the newest build result's `build_fidelity == 'log-failure-override'`), emit a clear WARN naming the DLL and `exit 4` (distinct from `1`/`3`), telling the agent to `/msbuild` first rather than silently testing stale bits. Fail-open (any read error → treat as stale).
- [x] Tests: `test-filtered.Tests.ps1` — `Describe 'Test-SummaryLine'` (6 tests: modern + legacy output parse, `summarySeen`/count/exit behavior) and `Describe 'Test-StaleTestDll'` (4 tests: fresh→false, source-newer→true, missing→true, no-throw). 10/10 green.

**Minimum Verifiable Behavior:** the regex/summary Pester block passes for modern output (exit 0, `summarySeen` true, correct counts) and for empty output (exit 3); the staleness fixture triggers the guard.

**Runtime Verification** *(checked by manual run — NOT by the implementation agent):*
- [ ] <!-- verification-only --> **Runtime spike:** run a real `/mstest` against a passing project and confirm the emitted summary is parsed (real pass count shown, no spurious "no-output"/exit-3) — validating the regex against actual emitted output, not a fixture string.

**MCP Integration Test Assertions:** N/A — harness scripts.

**Prerequisites:** None functionally (independent file/seam from P1/P2); the staleness guard optionally consumes Phase 1's `build_fidelity` (soft — degrades to the DLL-timestamp check if absent).

**Files likely modified:**
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` — regex + count emission + staleness guard.
- `user/scripts/build-queue-hygiene.Tests.ps1` (or new `test-filtered.Tests.ps1`) — parsing + guard tests.

**Testing Strategy:** Pester over captured output-line fixtures (both formats) for the parse; a mtime-fixture for the guard. Real-output confirmation via the spike row.

**Integration Notes for Next Phase:** `/mstest` now yields a trustworthy pass count and a stale-DLL warning — Phase 4's skill prose references both signals.

**Implementation Notes (2026-07-01):**
- **Work completed (WU-6/WU-7, all deliverables):** `test-filtered.ps1` (171L) refactored so the summary parse is a pure `Test-SummaryLine([string]$line)` helper (returns `@{isSummary; passed; failed; total}`) — widened to match modern `Passed!  - Failed:X, Passed:Y, Skipped:Z, Total:N[, Duration…]` (and the `Failed! - …` variant) via a dedicated capturing regex, falling through to the unchanged legacy alternation. On a modern hit it emits `Results: Passed=X Failed=Y Total=Z`. Added pure `Test-StaleTestDll($DllPath, $ProjectDir)` (WU-7) → stale (`$true`) if the DLL is missing, older than the newest `.cs`/`.csproj` under the project dir, or the newest `results/<seq>.json` carries `hygiene.build_fidelity == 'log-failure-override'`; every read fail-open (defaults to stale on error).
- **Dot-source seam:** the whole main body is now `function Invoke-Main`, invoked only via `if ($MyInvocation.InvocationName -ne '.') { Invoke-Main }` at the bottom — so `test-filtered.Tests.ps1` dot-sources the helpers WITHOUT spawning `dotnet` (confirmed: GREEN runs emit no "Running tests…"/dotnet output). The staleness guard is wired into `Invoke-Main` before `& dotnet @dotnetArgs`: on stale → WARN naming the DLL + `/msbuild` guidance + `exit 4` (distinct from `1`=no-repo / `3`=no-output). `--no-build` preserved; exit-3 contract byte-identical.
- **Files modified:** `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (171L), `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1` (97L, net-new — `Describe 'Test-SummaryLine'` 6 tests + `Describe 'Test-StaleTestDll'` 4 tests).
- **Gate:** `Invoke-Pester test-filtered.Tests.ps1` → 10 passed / 0 failed / 10 total. PARSE OK both files. (File-disjoint from the hygiene suite — this repo is claude-config; edits are against the symlink source under `repos/cognito-forms/.claude/scripts/`, never the live worktree.)

---

### Phase 4: Visibility + guidance

**Scope:** Surface the new hygiene fields in the status view and give the agent fast recognition/recovery prose in the two skills. Low-risk display/docs layer — the thinnest layer, per the SPEC's answer to "should we update the skills?"

**Deliverables:**
- [x] `build-queue-status.ps1`: extend the hygiene render (L138–180) to print `build_fidelity` (flag `log-failure-override` prominently) and `lockers_reaped` (count/PIDs).
- [x] `repos/cognito-forms/.claude/skills/msbuild/SKILL.md`: concise prose — what a `build_fidelity: log-failure-override` result means, the MSB3027/copy-lock signature, and the recovery (locker reaped automatically; if it recurs, check `/build-queue-status`), pointing at repo `CLAUDE.local.md` for depth.
- [x] `repos/cognito-forms/.claude/skills/mstest/SKILL.md`: prose on the `--no-build` stale-DLL trap, the new staleness warning, and "rebuild before trusting a red" guidance.

**Minimum Verifiable Behavior:** `build-queue-status.ps1` on a results file carrying the new fields prints them (including the `log-failure-override` highlight); the two SKILL.md files render the new guidance.

**MCP Integration Test Assertions:** N/A — docs + status display.

**Prerequisites:** Phases 1–3 (surfaces `build_fidelity` from P1, `lockers_reaped` from P2; prose references P3's staleness warning).

**Files likely modified:**
- `user/scripts/build-queue-status.ps1`, `repos/cognito-forms/.claude/skills/msbuild/SKILL.md`, `repos/cognito-forms/.claude/skills/mstest/SKILL.md`.

**Testing Strategy:** run `build-queue-status.ps1` against a synthetic results JSON carrying the new fields; visual confirmation of prose.

**Integration Notes for Next Phase:** terminal phase. After this, `__mark_fixed__` gate-flips the SPEC to Fixed and writes `FIXED.md`.

**Implementation Notes (2026-07-01):**
- **Work completed (WU-8/WU-9/WU-10, all deliverables):** `build-queue-status.ps1` (191L) hygiene render extended to read `hygiene.build_fidelity` + `hygiene.lockers_reaped` via the existing `Get-SafeValue` fail-open pattern (normalize missing/legacy → `n/a`/`0`), append both to the summary line, and add a `Write-Host -ForegroundColor Red` branch — ordered BEFORE the existing yellow `no-output` branch — that fires on `build_fidelity=log-failure-override` tagging `[BUILD LIED - copy-lock override fired]`. `msbuild/SKILL.md` (42L) + `mstest/SKILL.md` (45L) each gained one appended concise subsection (frontmatter/Usage/Instructions untouched): msbuild `## Recognizing a copy-lock false-success` (MSB3027/MSB3021 exit-0 signature → queue override → `build_fidelity: log-failure-override` in `/build-queue-status`; auto-reap self-heal + check-status-before-manual-kill; `CLAUDE.local.md` pointer); mstest `## Stale-DLL trap (--no-build)` (`--no-build` tests stale bits → `test-filtered.ps1` WARN + distinct `exit 4` when DLL missing/older-than-source/`build_fidelity: log-failure-override`; naming exit 1/3; rebuild-with-`/msbuild`-before-trusting-a-red recovery).
- **StrictMode pitfall (WU-8, caught + fixed in-gate):** `@(if (...) {} else {})` collapses to `$null` under `Set-StrictMode`, and `@($varHoldingNull)` yields `Count=1` not `0` — so the naive form mis-rendered `lockers_reaped` on legacy results files. Final form `$lockersReaped = @(if ($null -ne $lockersReapedRaw) { $lockersReapedRaw })` is verified correct for both populated and absent cases.
- **Files modified:** `user/scripts/build-queue-status.ps1` (191L), `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` (42L), `repos/cognito-forms/.claude/skills/mstest/SKILL.md` (45L). All three file-disjoint — dispatched as one same-message Sonnet batch.
- **Gate:** independent status-render gate against a synthetic `results/<seq>.json` → `log-failure-override` renders Red with the `[BUILD LIED]` tag + `lockers_reaped=2 (40380,40381)`; legacy file (no new fields) renders `build_fidelity=n/a | lockers_reaped=0` without throwing. `project-skills.py` → exit 0, `lint-skills.py` → exit 0. (Both `/msbuild` + `/mstest` are repo-scoped skills, so they have no `skills-projected/` copy by design — the projector only expands the 85 user-level skills; edits verified through the source + symlink chain. NOTE: `python` on this host is a Microsoft Store app-execution-alias stub — use `py` to invoke the projector/lint.)

---

## Cross-cutting notes

- **One-writer-per-file / ordering:** Phases 1 and 2 both edit `build-queue-hygiene.ps1` and `build-queue-runner.ps1` — run them **sequentially**, not in parallel, to avoid clobber (constitution: one writer per file). Phase 3 (Cognito `test-filtered.ps1`) is file-disjoint and may proceed independently.
- **No terminal-only verification:** each phase carries its own Pester/script proof; the two genuinely runtime-coupled claims (P2 reap frees lock, P3 regex vs. live output) are explicit in-phase runtime spikes, not deferred.
- **This repo is claude-config, not a Cognito worktree** — the `build-filtered.ps1`/`test-filtered.ps1` edits live under `repos/cognito-forms/.claude/scripts/` (write through the claude-config symlink source; never edit the live symlinked worktree path).

## Review Notes

**Decomposition review (inline, /spec-phases Step 6) — 2026-07-01:** **Verdict: PASS.** All six SPEC fix elements map to phases (result-fidelity guard→P1, locker reap→P2, ungate staleness→P1 exit-override, test regex→P3, status surfacing→P4, skill prose→P4). Authoring discipline verified: gate-owned actions are prose (no status/receipt checkboxes), runtime rows carry the canonical `<!-- verification-only -->` marker, blanket MCP N/A is legitimate (no MCP surface — documented in header, not a terminal-stacking deferral). No red flags (no circular deps, bounded touchpoints, Pester-testable; P1/P2 shared-file edits ordered sequentially per one-writer-per-file).
