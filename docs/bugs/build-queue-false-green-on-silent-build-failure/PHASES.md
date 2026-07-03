# Implementation Phases — Build Queue False-Green on Silent Build Failure

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config PowerShell harness scripts; no app runtime or MCP-reachable surface. Verification is Pester + a live `build-queue.ps1` invocation in a Cognito worktree.

### Phase 1: Per-project quarantine sweep (Root Cause A, the P0)

**Scope:** `Remove-PoisonedArtifacts` currently sweeps only `<WorktreeRoot>/bin` + `<WorktreeRoot>/obj`, so a poisoned per-project artifact (e.g. `<worktree>/Cognito/bin/Debug/netstandard2.0/Cognito.dll`, 0-byte) survives and poisons the incremental build. `Get-DllLockers` has the same worktree-root blindness — its docstring falsely claims it mirrors a per-project `<root>/**/bin/Debug` sweep, but it only walks `<root>/bin`. Extract a single shared per-project enumeration helper and retarget both functions onto it, resolving the SPEC's DLL-locker-sweep-parity open question.

**Deliverables:**
- [x] New parameterized helper in `user/scripts/build-queue-hygiene.ps1` that recursively enumerates `*.dll` under the worktree root across every project subdir (`<root>/**/bin` + `<root>/**/obj`), accepting an optional path-segment filter (e.g. `bin/Debug`) so callers can restrict scope. Fail-open enumeration via the repo idiom (`Get-SafeValue { ... } @()`).
- [x] Rewrite `Remove-PoisonedArtifacts` (currently lines 576-683; roots built at 622-625; recurse at 632; poison test 0-byte-OR-first-2-bytes-not-MZ at 646-663; per-file delete fail-open via `Get-SafeValue` at 669-678) to call the helper with no path filter, sweeping both bin and obj across all project subdirs and all configs. Preserve the exact poison test and the fail-open per-file delete semantics.
- [x] Retarget `Get-DllLockers` (lines 898-~1010; enum at 953-964, currently `Join-Path $WorktreeRoot 'bin'` + `-Recurse` + `Where-Object {$_.FullName -match '[\\/]bin[\\/]Debug[\\/]'}`) onto the same helper with the `bin/Debug` path filter, so both functions share one per-project root enumeration and the docstring's "mirroring" claim becomes true.
- [x] Tests: seed a 0-byte DLL under `<worktree>/Cognito/bin/Debug/netstandard2.0/` and a truncated (non-MZ) DLL under `<worktree>/Cognito.Core/obj/Debug/`; assert both are quarantined by `Remove-PoisonedArtifacts`; assert a valid-PE DLL under a project subdir is left alone; assert `Get-DllLockers` detects a locker under a project subdir; add a scoping test pinning the divergence (a `bin/Release` or non-bin/obj DLL is handled per each function's own filter).

**Minimum Verifiable Behavior:** `Invoke-Pester user/scripts/build-queue-hygiene.Tests.ps1` green, including the new "poisoned DLL under `Cognito/bin/Debug` is quarantined" It-block, which FAILS against the current worktree-root-only sweep.

#### Implementation Notes (2026-07-03)

**Status:** Complete (Pester-green; runtime e2e deferred to Phase 4/Part 3 per plan).
**Review verdict:** PASS.

- Added shared `Get-ProjectDlls -WorktreeRoot <r> [-PathSegmentFilter 'bin/Debug']` (`build-queue-hygiene.ps1:576`): recurses the whole worktree for `*.dll`, restricts to paths containing a `[\\/](bin|obj)[\\/]` segment, then optionally applies a consecutive-segment filter (e.g. `bin/Debug` → `[\\/]bin[\\/]Debug[\\/]`). Fail-open to `@()` via `Get-SafeValue`.
- `Remove-PoisonedArtifacts` now calls the helper with **no** filter (`:704`), replacing the `<root>/bin` + `<root>/obj`-only roots loop; the 0-byte-OR-non-`MZ` poison test and the fail-open per-file `Get-SafeValue` delete are preserved byte-for-byte.
- `Get-DllLockers` now calls the helper with `-PathSegmentFilter 'bin/Debug'` (`:1024`), replacing its `<root>/bin`-only enumeration — so both consumers share ONE per-project enumeration and the docstring's "mirroring" claim is now true.
- **Pitfall found + fixed during impl:** the helper first `return`ed `,$dlls` (comma operator); an empty result then surfaced to callers (via `@(...)`) as a one-element array containing `@()`, so `foreach ($dll ...)` iterated once over an empty array and `$dll.FullName` threw — breaking the 3 pre-existing worktree-root `Remove-PoisonedArtifacts` tests. Changed to plain `return $dlls` (callers already `@()`-wrap). All originals green again.
- **Gate:** `Invoke-Pester build-queue-hygiene.Tests.ps1` → 76 passed, 3 failed. The 3 failures (`Add-ProcessToBuildJob`/`Stop-BuildJobTree` zero-handle, `Reset-CompilerServer` `[bool]`) are the KNOWN pre-existing environment quirks documented in the test file (line ~203) — identical to the pre-change baseline (65→76 passing exactly matches the 11 new WU-1 It-blocks). Parse-check `PARSE OK`.
- **Files modified:** `user/scripts/build-queue-hygiene.ps1`, `user/scripts/build-queue-hygiene.Tests.ps1`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
N/A — fully covered by Pester in Deliverables.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config PowerShell harness).

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — extract shared per-project `<root>/**/{bin,obj}` DLL enumerator (net-new helper); rewrite `Remove-PoisonedArtifacts` (576-683) onto it; retarget `Get-DllLockers` (898-~1010) onto it with a `bin/Debug` filter.
- `user/scripts/build-queue-hygiene.Tests.ps1` — extend Pester coverage for the per-project sweep and locker detection.

**Testing Strategy:** New `Describe` block(s) in `build-queue-hygiene.Tests.ps1` seeding a multi-project worktree fixture (`Cognito/bin/Debug/...`, `Cognito.Core/obj/Debug/...`) alongside the existing worktree-root fixtures; run via `Invoke-Pester user/scripts/build-queue-hygiene.Tests.ps1` in isolation before touching Phase 2/3 code.

**Integration Notes for Next Phase:** Phase 3's no-output gate forces `$buildFailed = $true` on a build op with no output, which means the per-project sweep from this phase now also fires on that path — Phase 3 must confirm (not re-implement) that interaction.

---

### Phase 2: Flush-retry helper for fidelity-bearing reads (Root Cause C)

**Scope:** The runner's counts read (`build-queue-runner.ps1:179-192`, single-shot `[System.IO.File]::ReadAllText` + regex for the last `Results:` line, no retry) and build-log read (`:138-144`, single-shot `ReadAllText`) race the wrapper-owned log flush/close, dropping trailing lines → `counts=$null` / misparse → agents bypass the capture. The `active.lock` read already retries 3x/50ms (runner `:234-241`, inline; mirrored in wrapper `build-queue.ps1:462-469`) — this phase extracts that proven pattern into a reusable, testable helper and converges the fidelity-bearing reads onto it.

**Deliverables:**
- [x] `Read-WithRetry`-style helper added to `user/scripts/build-queue-hygiene.ps1` (dot-sourced so it is Pester-testable), parameterized: a parse `[scriptblock]` returning the parsed payload or `$null` on failure, `-MaxAttempts` (default 3), `-DelayMs` (default 50); returns the first non-null result or a fallback sentinel after exhausting attempts. Modeled on the active.lock loop verbatim (attempts 1..Max, `Start-Sleep -Milliseconds` between attempts, no sleep after the last attempt).
- [ ] Converge the runner's counts read (179-192) and build-log read (138-144) in `build-queue-runner.ps1` onto the helper.
- [ ] Optional: converge the two active.lock loops (runner 234-241 + wrapper `build-queue.ps1:462-469`) onto the helper for dedupe/parity — call out as optional, not required for this phase's completion.
- [x] Tests: helper returns on the first non-null attempt; helper retries up to `-MaxAttempts` on a parse block that always returns `$null`; helper returns the fallback sentinel after `-MaxAttempts` exhausted; helper respects a parse block that succeeds only on the Nth attempt (simulated via a counter closure).

**Minimum Verifiable Behavior:** `Invoke-Pester user/scripts/build-queue-hygiene.Tests.ps1` green for the new `Read-WithRetry` `Describe` block, including the "succeeds on Nth attempt" It-block; the runner's counts/build-log reads route through the helper (verified by code inspection + the existing counts-parsing tests continuing to pass).

#### Implementation Notes — WU-2 (2026-07-03)

**Review verdict:** PASS.

- Added `Read-WithRetry -Parse <scriptblock> [-MaxAttempts 3] [-DelayMs 50] [-Fallback $null]` (`build-queue-hygiene.ps1`, placed right after `Get-SafeValue`). Loop is the active.lock exemplar verbatim: attempts `1..MaxAttempts`, return first non-`$null`, `Start-Sleep -Milliseconds $DelayMs` ONLY between attempts (no sleep after the last), `$Fallback` after exhaustion. A `$null` parse result = "not ready, retry".
- 5 new counter-closure Pester It-blocks (`-DelayMs 0`, no filesystem/timing dependency): first-attempt success (1 invocation), always-`$null` → exactly `MaxAttempts` invocations + fallback sentinel, default-`$null` fallback after exhaustion, Nth-attempt success (exactly N invocations).
- **Gate:** `Invoke-Pester` → 81 passed, 3 pre-existing env-quirk failures. Parse-check `PARSE OK`.
- Runner convergence (deliverable 2) + optional active.lock convergence (deliverable 3) are WU-3 — next batch.
- **Files modified:** `user/scripts/build-queue-hygiene.ps1`, `user/scripts/build-queue-hygiene.Tests.ps1`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
N/A — fully covered by Pester in Deliverables.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config PowerShell harness).

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — add `Read-WithRetry` helper.
- `user/scripts/build-queue-runner.ps1` — converge counts read (179-192) + build-log read (138-144) onto `Read-WithRetry`.
- `user/scripts/build-queue.ps1` — optional: converge active.lock retry (462-469) onto `Read-WithRetry`.
- `user/scripts/build-queue-hygiene.Tests.ps1` — extend Pester coverage for the new helper.

**Testing Strategy:** New `Describe 'Read-WithRetry'` block in `build-queue-hygiene.Tests.ps1` using counter-closure scriptblocks to simulate delayed-success, always-fail, and immediate-success parse conditions — no real filesystem timing dependency, deterministic and fast.

**Integration Notes for Next Phase:** Phase 3's build-output classifier reads the (now retry-hardened) build log; Phase 3 should call the classifier AFTER the Phase 2 read completes, not re-read the log itself, so the no-output determination is made on the same flush-safe read.

---

### Phase 3: Build-output fidelity gate (Root Cause B)

**Scope:** For a build op, `build_fidelity` is set only by the negative `Test-BuildLogFailure` log-signature scan (`build-queue-runner.ps1:137-153`); the log guard at `:139` tests path/existence only, never file size; a 0-byte log reads as `""`, `Test-BuildLogFailure` fails-open to `failed=$false`, and the `else` at 150-152 labels it `verified` — so a build that produced nothing is reported as a clean PASS. Test ops already have an analog (exit-3 `no-output`, `:167-172`); build ops do not. The per-project sweep from Phase 1 only runs when `$buildFailed` is already true (`:161-164`, guarded on `$buildFailed -and $Worktree`, not `$isBuildOp`), so it never fires on the exit-0 false-green today. This phase adds a positive build-output classifier and forces the exit code/fidelity when no output was produced.

**Deliverables:**
- [ ] Build-output classifier function added to `user/scripts/build-queue-hygiene.ps1` (dot-sourced/testable): given the build log path (read via Phase 2's `Read-WithRetry`), decides whether the build produced output. Default detection: a build op that exits 0 with a missing / empty / whitespace-only / near-empty build log is classified no-output. An optional stronger check, gated on an expected-output-DLL path being known (DLL exists AND is newer than its sources), is documented as a follow-on knob and is NOT required for this phase.
- [ ] In `build-queue-runner.ps1`'s `if ($isBuildOp)` block: when exit is 0 but the classifier reports no-output, force `$exitCode = 1`, set `$buildFailed = $true`, and set `build_fidelity = 'no-output'` (reusing the existing test-op `result_fidelity` vocabulary rather than inventing a new banner enum concept) — mirroring the existing log-failure-override mechanism at lines 146-149. Note in a code comment that forcing `$buildFailed = $true` here also causes Phase 1's per-project sweep to fire on a no-output build.
- [ ] `Format-BuildQueueBanner` (`build-queue-hygiene.ps1:1190-1291`; label chain 1247-1253; next-action suffix 1271-1279): add a dedicated next-action arm for `build_fidelity: no-output` (e.g. "-> build produced no output; delete obj/bin and rebuild"), parallel to the existing log-failure-override guidance. RESULT=FAIL already falls out of the forced exit=1 via the existing `$ExitCode -ne 0` arm.
- [ ] `build-queue-status.ps1` (hygiene line at 181; special-case highlights at 182-185): add an `elseif` highlight arm for `build_fidelity: no-output` on build ops (e.g. red `[BUILD LIED - produced no output]`).
- [ ] Schema doc-comment for `build_fidelity` (`build-queue-runner.ps1:30`): add `no-output` to the documented domain (currently `log-failure-override | verified | n/a`).
- [ ] `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` (banner-shape + next-action at :34; copy-lock/`build_fidelity` explainer at :38-42): mirror the new banner RESULT/next-action for `no-output`.
- [ ] `repos/cognito-forms/.claude/skills/nxbuild/SKILL.md` (banner-shape + next-action at :36): mirror the new banner RESULT/next-action; add a short `build_fidelity` explainer block (nxbuild currently has none) for parity with msbuild.
- [ ] Tests: classifier returns no-output for a missing/empty/whitespace-only log and `verified`-equivalent (no override) for a real non-empty build log; `Format-BuildQueueBanner` renders `RESULT=FAIL` plus the new next-action text for `build_fidelity: no-output`; `build-queue-status.ps1`'s highlight logic selects the new arm for that fidelity value.

**Minimum Verifiable Behavior:** `Invoke-Pester user/scripts/build-queue-hygiene.Tests.ps1` green for the new classifier `Describe` block (including an It-block asserting a 0-byte log classifies as no-output) plus the banner and status test blocks covering `build_fidelity: no-output`. Note: the runner's inline wiring (the actual `if ($isBuildOp)` forcing of exit code) has no Pester harness — it is validated by the Phase 4 live build instead.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> A live no-output build in a Cognito worktree (via `/msbuild`) reports `RESULT=FAIL` with `build_fidelity: no-output` and the new banner next-action text — confirms the runner's inline wiring end-to-end (deferred to Phase 4's live e2e per the note above).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config PowerShell harness).

**Prerequisites:** Phase 2's `Read-WithRetry` (the classifier consumes a flush-safe log read) and Phase 1's per-project sweep (so a no-output build's forced `$buildFailed` correctly triggers full quarantine).

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — add build-output classifier fn + banner arm in `Format-BuildQueueBanner` (1247-1279).
- `user/scripts/build-queue-runner.ps1` — add no-output gate in the `if ($isBuildOp)` block (137-153) mirroring the log-failure-override mechanism (146-149) + schema doc-comment (:30).
- `user/scripts/build-queue-status.ps1` — add highlight `elseif` arm at 182 for the new build-op fidelity.
- `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` + `.../nxbuild/SKILL.md` — mirror new banner RESULT/next-action (nxbuild needs a new fidelity-explainer block for parity).
- `user/scripts/build-queue-hygiene.Tests.ps1` — extend Pester coverage for the classifier, banner, and status arms.

**Testing Strategy:** New `Describe` blocks in `build-queue-hygiene.Tests.ps1` for the classifier (missing/empty/whitespace/near-empty vs. real-content logs), for `Format-BuildQueueBanner` given a synthetic result object with `build_fidelity: no-output`, and for the status-script highlight selection logic. The runner's own body remains outside Pester coverage per the existing pattern — that gap is closed only by Phase 4's live run.

**Integration Notes for Next Phase:** Phase 4's live e2e must exercise all three fidelity outcomes end-to-end (poisoned-artifact FAIL, clean PASS/`verified`, no-output FAIL) since the runner's inline wiring has no other verification path.

---

### Phase 4: Re-enable enforcement hook + end-to-end verification

**Scope:** With Root Causes A, B, and C fixed and Pester-covered, restore `build-queue-enforce.sh` to enforcing (it was deliberately, temporarily disabled pending this bug per the SPEC's Git History note) and prove the full fix chain live in a real Cognito worktree, then update the harness documentation that describes the hygiene sweep scope and fidelity domain.

**Deliverables:**
- [ ] Remove the temporary disable block in `user/hooks/build-queue-enforce.sh` (lines 2-8: a `>>> TEMPORARILY DISABLED <<<` banner with `exit 0` at line 6 before all hook logic), restoring the hook to its prior enforcing behavior.
- [ ] Update the Scripts-table hygiene note in `C:\Users\JacobMadsen\source\repos\CLAUDE.md` to reflect the per-project sweep scope (Phase 1) and the new `no-output` build-output fidelity value (Phase 3).
- [ ] Update the equivalent Scripts-table hygiene note in `C:\Users\JacobMadsen\source\repos\claude-config\CLAUDE.md` to match.

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` passes its ~22 `test_bqe_*` deny/allow tests (defined from `:4795`) against the re-enabled hook (they cannot meaningfully pass against the disabled `exit 0` block today); all three Pester suites (`build-queue-hygiene.Tests.ps1`, `test-filtered.Tests.ps1` under `repos/cognito-forms/.claude/scripts/`, plus the new coverage from Phases 1-3) report green in the same run.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> In a Cognito worktree, seed a poisoned per-project DLL (e.g. 0-byte `Cognito/bin/Debug/netstandard2.0/Cognito.dll`) and run `/msbuild` via the build queue — confirm the banner reports `RESULT=FAIL` and the artifact is quarantined.
- [ ] <!-- verification-only --> Run a real clean `/msbuild` build in the same worktree — confirm `RESULT=PASS` with `build_fidelity: verified`.
- [ ] <!-- verification-only --> Force or observe a build that exits 0 with no compiled output — confirm `RESULT=FAIL` with `build_fidelity: no-output` and the corrective next-action text in the banner.
- [ ] <!-- verification-only --> Confirm `python user/scripts/test_hooks.py`'s `test_bqe_*` suite passes with the hook re-enabled (deny/allow behavior matches pre-disable expectations).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config PowerShell harness).

**Prerequisites:** Phases 1-3 complete (per-project sweep, flush-retry helper, and build-output fidelity gate all merged and Pester-green).

**Files likely modified:**
- `user/hooks/build-queue-enforce.sh` — remove the `exit 0` disable block (lines 2-8).
- `user/scripts/test_hooks.py` — run its `test_bqe_*` suite (no edit expected; the deny tests re-pass once the hook enforces).
- `C:\Users\JacobMadsen\source\repos\CLAUDE.md` + `claude-config/CLAUDE.md` — update the Scripts-table hygiene note.

**Testing Strategy:** Full-suite run: `python user/scripts/test_hooks.py` for hook deny/allow behavior, `Invoke-Pester` across `build-queue-hygiene.Tests.ps1` and `test-filtered.Tests.ps1` for the accumulated Phase 1-3 coverage, followed by the live Cognito-worktree e2e observations listed under Runtime Verification.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** and writes FIXED.md once this phase's live verification (all four Runtime Verification rows) passes.

**Integration Notes for Next Phase:** None — this is the terminal phase. The documentation updates and re-enabled hook are the durable record that the false-green defect is closed; any future hygiene-scope or fidelity-domain change should update the same CLAUDE.md notes touched here.
