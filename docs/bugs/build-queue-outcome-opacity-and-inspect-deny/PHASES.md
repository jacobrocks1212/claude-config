# Implementation Phases — Build-Queue Outcome Opacity + Enforce-Hook Over-Blocks Read-Only Inspection

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is the claude-config harness repo (bash hooks / PowerShell scripts / skill markdown / Python+Pester tests); there is no Tauri/MCP/app surface. Verification is via test_hooks.py (bash pipe-tests), Pester (test-filtered.Tests.ps1), and manual /mstest observation on a Cognito worktree — the "no app integration / build tooling" untestable class per docs/features/mcp-testing/SPEC.md.

### Phase 1: Hook — invoke-vs-reference discrimination + regression tests

**Scope:** Stop `build-queue-enforce.sh` denying read-only inspection commands that merely reference a build token (e.g. `cat`/`grep`/`tail` on `results/*.json` or `logs/*.log`, or a filtered script's own source). A build must only be denied when it is the INVOKED command, not when a build token appears as an argument to a read verb.

**Deliverables:**
- [x] Rework the deny surface in `user/hooks/build-queue-enforce.sh` (`_DOTNET_BUILD_RE`/`_DOTNET_TEST_RE` lines 96-97, `_NX_BUILD_TEST_RE` 101-108, `_FILTERED_SCRIPT_RE` 110-113) so each only denies when the build token begins a command segment — string start or immediately after a shell separator (`&& || | ; ( {` or newline), with an optional `NAME=value` env-assignment prefix — mirroring `long-build-ownership-guard.sh`'s `_CMD_START`/`_ENV_PREFIX` (line 94) — OR appears as the `-File <...-filtered.ps1>` argument to a `powershell(.exe)` invocation.
- [x] Ensure a build token appearing only as an argument to a read verb (`cat`, `less`, `head`, `tail`, `grep`, `rg`, `find`, `ls`, `Get-Content`, `Select-String`, `type`), inside a quoted `results/`/`logs/` path, or inside `git diff`/`echo` text does NOT trigger a deny.
- [x] Preserve existing behavior: the `cd "..." && dotnet build` pattern still DENIES (the build token still leads its own segment after `&&`); `BUILD_QUEUE_BYPASS=1` (`_BYPASS_RE`, line 76) and the `build-queue.ps1` wrapper (`_WRAPPER_RE`, line 81) exemptions; the Cognito-remote scope gate (lines 159-172); fail-OPEN via JSON `permissionDecision: deny` (never a non-zero hook exit).
- [x] Audit `user/hooks/long-build-ownership-guard.sh`'s existing `_CMD_START`-anchored `_LONG_BUILD_RE` (lines 94-101) for any reference-only case it currently denies; change it ONLY if such a case is found (expected: no change needed, already correct). — **Audited, no change needed** (already `_CMD_START`-anchored; the 3 new `test_longbuild_guard_*` reference-only ALLOW cases pass against it unchanged).
- [x] Tests (TDD — write failing first) appended to the `test_bqe_*` block in `user/scripts/test_hooks.py` and registered in the `_ALL_TESTS` list, reusing `_init_cognito_worktree`/`_bqe_payload`/`_run_bash`/`_containment_decision`:
  - ALLOW: `cat "$HOME/.claude/state/build-queue/results/614.json"`
  - ALLOW: `grep -n "stale|exit 4" test-filtered.ps1`
  - ALLOW: `tail logs/500.build.err.log`
  - ALLOW: `find . -name build-filtered.ps1`
  - ALLOW: `cat build-filtered.ps1 | head -100`
  - ALLOW: `git diff user/settings.json`
  - DENY: bare `dotnet build`
  - DENY: `cd "..." && dotnet test`
  - DENY: `dotnet restore && dotnet build`
  - DENY: bare `powershell -File .../test-filtered.ps1` invocation
  - DENY: direct `./build-filtered.ps1`
- [x] Regression tests appended to the `test_longbuild_guard_*` block (via `_run_longbuild_guard`/`_bash_preToolUse_json`) covering the same reference-only ALLOW cases against `long-build-ownership-guard.sh`, to lock in that it already discriminates correctly.

**Implementation Notes (2026-07-03):** Added module-level `_ENV_PREFIX` + `_CMD_START` (verbatim idiom copied from `long-build-ownership-guard.sh`) to `build-queue-enforce.sh` and prefixed `_CMD_START` onto `_DOTNET_BUILD_RE`, `_DOTNET_TEST_RE`, and `_NX_BUILD_TEST_RE`. Split the old `_FILTERED_SCRIPT_RE` into two: `_FILTERED_SCRIPT_DIRECT_RE` (segment-leading direct invocation, with optional `./` / `.\` / abs-path prefix so `./build-filtered.ps1` still denies) and `_FILTERED_SCRIPT_POWERSHELL_RE` (`powershell(.exe)?`/`pwsh … -File <…filtered.ps1>`). Callsite (line ~326) ORs both. `_suppress_safe` scan target, `_BYPASS_RE`, `_WRAPPER_RE`, scope-gate, and fail-OPEN wrapper untouched. **Tests:** all 12 new `test_bqe_*`/`test_longbuild_guard_*` cases pass; full suite 118/119 (lone failure `test_pipe_tests_wsl` is a pre-existing WSL-environment failure, present in the RED baseline, unrelated to this change). `long-build-ownership-guard.sh` unchanged. **Files modified:** `user/hooks/build-queue-enforce.sh` (+`test_hooks.py` tests were pre-written this session).

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` exits 0 with all `test_bqe_*` and `test_longbuild_guard_*` cases passing, including every new ALLOW/DENY case listed above.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (harness tooling; see MCP runtime header).

**Prerequisites:** None. Independent of Phase 2 — may be implemented in parallel.

**Files likely modified:**
- `user/hooks/build-queue-enforce.sh` — anchor the three deny regexes to command-start position (mirroring `long-build-ownership-guard.sh`'s `_CMD_START`/`_ENV_PREFIX`) plus a `-File <...-filtered.ps1>` powershell-argument case; exemptions/scope-gate/fail-open untouched.
- `user/hooks/long-build-ownership-guard.sh` — audited; code change only if a reference-only deny is actually found (not expected).
- `user/scripts/test_hooks.py` — new ALLOW/DENY cases appended to `test_bqe_*` and `test_longbuild_guard_*`, registered in `_TESTS`.

**Testing Strategy:** TDD. Write the new test cases first (they should FAIL against the current unanchored regexes), then apply the anchoring fix, then confirm all cases pass via `python user/scripts/test_hooks.py`. No Pester or runtime component in this phase — pure bash-hook logic.

**Integration Notes for Next Phase:** Phase 1 is orthogonal to the fidelity/banner work (Phases 2-4) — it only changes what the hook denies, not what the build tooling reports. No shared state or ordering dependency.

TDD: yes.

---

### Phase 2: Zero-match fidelity detection

**Scope:** Make a zero-match test filter (a filter expression that matches no tests) exit as a distinct, non-`verified` fidelity instead of silently reporting `exit 0` indistinguishable from a genuine all-pass run.

**Deliverables:**
- [x] `repos/cognito-forms/.claude/scripts/test-filtered.ps1`: when the modern SDK summary is seen (`$summarySeen = $true`) AND `$summary.total -eq 0` (zero tests matched the filter), signal this distinctly instead of falling through to `exit $dotnetExit` (currently 0) at the tail of the existing zero-output check (lines 185-188 area). Reuse the existing exit-3 zero-output path if the author determines the two zero-tests-observed states (no summary at all vs. a summary reporting Total: 0) can share a code with a distinguishing field in the emitted output, OR introduce a new distinct exit code — document whichever is chosen in a comment at the check site. Keep the existing exit 1 (not-in-git-repo), exit 3 (genuine zero-output, no summary seen), and exit 4 (stale/missing DLL) semantics fully intact and non-overlapping.
- [x] `user/scripts/build-queue-runner.ps1`: extend the `result_fidelity` computation (lines 161-166) to map the new zero-match signal to a distinct value, e.g. `no-tests-matched`, alongside the existing `n/a` (non-test ops), `no-output` (test op exit 3), and `verified` (else). Update the schema doc comment (lines 24-25) to document the new `result_fidelity` value.
- [x] Pester cases added to `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1`:
  - A filter matching zero tests (e.g. `-Filter "ClassName~DoesNotExist"`) → the new distinct signal, not silent exit 0.
  - A real all-pass run → unaffected, still resolves to `verified` fidelity downstream.
  - A genuine zero-output run (no summary line at all) → still exits 3, unaffected by the new check.

**Implementation Notes (2026-07-03):** WU-2 — extracted a pure `Get-TestOutcomeExitCode -SummarySeen -Total -ResultLineCount -DotnetExit` helper in `test-filtered.ps1` (returns 3 for no-summary+zero-output, **5** for summary-seen+Total=0, else passthrough `$DotnetExit`), wired into `Invoke-Main`'s tail (captures `$summaryTotal`, single `exit $outcomeCode`, distinct WARN per code). Exit codes 1/3/4 semantics intact and non-overlapping; chose a new distinct exit **5** (documented at the check site) over reusing 3. Pester: 4 new `Get-TestOutcomeExitCode` cases; full file 18/18 GREEN. WU-3 — added `elseif ($exitCode -eq 5) { 'no-tests-matched' }` to the runner's `$resultFidelity` map (before `else { 'verified' }`) + updated the schema doc comment enum. AST parse clean.

**Minimum Verifiable Behavior:** The new Pester test `Invoke-Pester repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1` asserts the zero-match case's exit code/signal differs from both the all-pass case and the genuine-zero-output case, and all three assertions pass.

**Runtime Verification** *(checked by integration test or manual testing)*:
- [ ] <!-- verification-only --> Running `/mstest -Filter "ClassName~DoesNotExist"` on a Cognito worktree produces a `results/<seq>.json` with `hygiene.result_fidelity == "no-tests-matched"` (or the chosen distinct value), not `"verified"`.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (harness tooling; see MCP runtime header).

**Prerequisites:** None. Independent of Phase 1.

**Files likely modified:**
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` — add the `$summary.total -eq 0` check alongside the existing zero-output check (~lines 185-188) to emit a distinct signal.
- `user/scripts/build-queue-runner.ps1` — extend `result_fidelity` mapping (lines 161-166) and schema doc comment (lines 24-25) with the new value.
- `repos/cognito-forms/.claude/scripts/test-filtered.Tests.ps1` — new zero-match / all-pass / genuine-zero-output Pester cases.

**Testing Strategy:** TDD — write the three Pester cases first (zero-match case should fail against current behavior since it silently exits 0), then implement the `test-filtered.ps1` check and the runner's fidelity mapping, then confirm all Pester cases pass. Runtime confirmation via a live `/mstest` invocation with a deliberately non-matching filter on a Cognito worktree (manual — this repo has no MCP or CI gate for it).

**Integration Notes for Next Phase:** Phase 3's banner surfaces this new `result_fidelity` value (`RESULT=NO-TESTS-MATCHED`) — Phase 3 has a hard prerequisite on this phase existing first.

TDD: yes.

---

### Phase 3: Inline outcome banner (seq + RESULT + counts + next action)

**Scope:** Print one unambiguous outcome line to the invocation's own stdout (`build-queue.ps1`'s foreground output) so agents never need to inspect the runner script or results JSON to disambiguate an `exit_code=0`. Also carry counts through to the results JSON so the background-poll path (large builds) is equally legible, and fix the wrapper's clobber of the runner's hygiene block.

**Deliverables:**
- [x] Add a pure banner-formatting helper function to `user/scripts/build-queue-hygiene.ps1` (alongside the existing 13 functions) taking `{seq, op, exit_code, result_fidelity, build_fidelity, counts}` and returning a single-line string, e.g. `build-queue: seq=614 op=mstest RESULT=PASS tests=312 failed=0 (result_fidelity=verified)`. Branches: `RESULT=NO-TESTS-MATCHED` (non-green) when `result_fidelity == no-tests-matched`; `RESULT=FAIL` on non-zero exit code or `build_fidelity == log-failure-override`; `RESULT=PASS` otherwise. Any non-clean `RESULT` appends an explicit next-action suffix: rebuild guidance on staleness (exit 4), "widen filter" on `NO-TESTS-MATCHED`, "read logs/<seq>.build.err.log" on `log-failure-override`.
- [x] `user/scripts/build-queue-runner.ps1`: capture test-filtered's Passed/Failed/Total counts into the hygiene JSON (either by parsing the runner's captured view of test-filtered's stdout for the existing `Results: Passed=P Failed=F Total=T` line, or by having `test-filtered.ps1` also emit a canonical machine-readable line the runner captures — author decides and documents the choice) so the background-poll path (results JSON read directly, no wrapper stdout) is equally legible.
- [x] `user/scripts/build-queue.ps1`: after reading `$proc.ExitCode`, read the runner's rich `results/<seq>.json`, compose the banner via the new helper, and print it as the LAST line of the wrapper's own stdout.
- [x] Fix the Step-5 clobber in `user/scripts/build-queue.ps1` (lines 425-438): the wrapper currently overwrites the runner's hygiene-rich `results/<seq>.json` with a minimal `{seq, exit_code, ended_at}` form, discarding `result_fidelity`/`build_fidelity`/etc. Either drop the wrapper's redundant write entirely (the runner already owns writing this file) or merge-preserve the existing hygiene block when the wrapper writes — the hygiene fields MUST survive intact after the wrapper's Step 5 runs (author decides the mechanism).
- [x] Pester unit tests for the new banner helper in `build-queue-hygiene.ps1`'s Pester coverage: one case per `RESULT` branch (`PASS`, `FAIL`, `NO-TESTS-MATCHED`), asserting the exact next-action suffix appears for each non-clean case.

**Minimum Verifiable Behavior:** A Pester run of the banner helper's unit tests passes for all three `RESULT` branches, each producing the exact expected one-line string format.

**Runtime Verification** *(checked by integration test or manual testing)*:
- [ ] <!-- verification-only --> Running `/mstest` (real filter, all-pass) on a Cognito worktree prints a `build-queue: seq=<N> op=mstest RESULT=PASS tests=<T> failed=0 (result_fidelity=verified)` line as the last line of stdout.
- [ ] <!-- verification-only --> Running `/mstest -Filter "ClassName~DoesNotExist"` on a Cognito worktree prints a banner with `RESULT=NO-TESTS-MATCHED` and a "widen filter" next-action suffix.
- [ ] <!-- verification-only --> After either run, `results/<seq>.json` still contains the full `hygiene` block (`result_fidelity`, `build_fidelity`, `vbcscompiler_recycled`, etc.) — confirming the Step-5 clobber fix holds.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (harness tooling; see MCP runtime header).

**Prerequisites:** Phase 2 (the `no-tests-matched` result_fidelity value the banner surfaces must exist first).

**Files likely modified:**
- `user/scripts/build-queue-hygiene.ps1` — new pure banner-formatting helper function.
- `user/scripts/build-queue-runner.ps1` — capture and persist Passed/Failed/Total counts into the hygiene JSON.
- `user/scripts/build-queue.ps1` — compose and print the banner after `$proc.ExitCode`; fix the Step-5 clobber (lines 425-438) to preserve the runner's hygiene block.

**Testing Strategy:** Pester unit tests on the pure banner helper (all RESULT branches, no process/filesystem dependency). Runtime confirmation via live `/mstest` pass and zero-match invocations on a Cognito worktree, observing the printed banner and inspecting `results/<seq>.json` to confirm hygiene survives the wrapper's Step 5 (manual — this repo has no MCP or CI gate for it).

**Integration Notes for Next Phase:** Phase 4 (skill docs) has a hard prerequisite on this phase — the banner must exist before skills can be told to trust it. **The wrapper-clobbers-hygiene fix is a required correctness fix for this phase**, not optional polish: without it the banner (or any later hygiene consumer, e.g. `build-queue-status.ps1`) would read the minimal post-clobber JSON and lose `result_fidelity`/`build_fidelity` entirely. Separately, the nx `client-build-filtered.ps1`/`client-test-filtered.ps1` scripts' missing reliable process exit-code propagation is an **accepted out-of-scope limitation** for this bug — do not expand scope to fix nx exit-code propagation here.

TDD: Pester-unit-testable (banner helper) + manual runtime confirmation; not a red/green TDD cycle in the strict sense since the helper is new formatting logic, not a bugfix to existing behavior.

---

### Phase 4: Skills — trust the banner (docs-only)

**Scope:** Point agents at the now-authoritative banner line so they stop `cat`-ing the runner script or results JSON to disambiguate an `exit_code=0` outcome.

**Deliverables:**
- [x] `repos/cognito-forms/.claude/skills/msbuild/SKILL.md`, `mstest/SKILL.md`, `nxbuild/SKILL.md`, `nxtest/SKILL.md`: add guidance that the invocation prints an authoritative one-line `build-queue: ... RESULT=...` banner as its last stdout line — trust it; do NOT `cat` the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an `exit_code=0`. Keep each skill's existing step-4 background-read-by-exact-seq path unchanged (no glob fallback exists to remove — the SPEC's original over-scoping is not carried into this phase). Reinforce the next-action the banner already names inline: rebuild on staleness (exit 4), widen filter on `RESULT=NO-TESTS-MATCHED`, read `logs/<seq>.build.err.log` on `log-failure-override`. Keep each skill's existing "Do not interpret or reformat the output" instruction intact — the banner is the queue's own output, not agent reformatting.

**Minimum Verifiable Behavior:** Each of the four SKILL.md files contains the new banner-trust guidance and the "do not inspect runner/results to disambiguate" instruction, reviewable by reading the diff — no runtime component to this phase.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (harness tooling; see MCP runtime header).

**Prerequisites:** Phase 3 (the banner must exist before skills can be told to trust it).

**Files likely modified:**
- `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` — add banner-trust guidance.
- `repos/cognito-forms/.claude/skills/mstest/SKILL.md` — add banner-trust guidance; reinforce existing exit-4 staleness/rebuild note alongside the new NO-TESTS-MATCHED next-action.
- `repos/cognito-forms/.claude/skills/nxbuild/SKILL.md` — add banner-trust guidance.
- `repos/cognito-forms/.claude/skills/nxtest/SKILL.md` — add banner-trust guidance.

**Testing Strategy:** Docs consistency review only (read-through of the four SKILL.md diffs); no runtime verification for this phase.

**Integration Notes for Next Phase:** Terminal phase — no downstream phase depends on this one.

**Completion (gate-owned):** the `__mark_fixed__` gate writes FIXED.md and flips SPEC.md **Status** once this phase's runtime verification passes.

TDD: docs-only, not applicable.

---

## Review Notes

**Review verdict (decomposition, 2026-07-03):** PASS. Boundaries verified against a completed touchpoint audit — every path in this plan exists (no net-new files; tests append to the existing `test_hooks.py` `test_bqe_*` harness and the `test-filtered.Tests.ps1` Pester file). Two SPEC scope corrections were baked in: (1) the "glob `results/*.json`" fallback the SPEC told skills to remove does not exist — Phase 4 does not carry it; (2) a latent clobber bug (`build-queue.ps1` Step 5 overwriting the runner's hygiene-rich `results/<seq>.json`) was discovered during the audit and folded into Phase 3 as a required correctness fix. No red flags (no circular deps; P1 independent, P2→P3→P4 linear; verification distributed per-phase). Banner surface decision (wrapper stdout + results JSON) confirmed with the user.
