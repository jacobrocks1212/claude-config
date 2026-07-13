# Implementation Phases — build-queue `$buildLogPath` child-scope discard forces `no-output` FAIL

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP dev runtime. This is a PowerShell
build-tooling defect (`build-queue-runner.ps1` variable scoping) validated via the Pester suite
(`build-queue-hygiene.Tests.ps1`) plus a REQUIRED operator-owned live re-verify (real Cognito
worktree + `/msbuild`) — the "build/script-tooling class per `docs/features/mcp-testing/SPEC.md`"
untestable-by-MCP class, same as the sibling `build-queue-hygiene-dot-source-discarded-in-child-scope`.

## Validated Assumptions

Root cause is **code-provable**, not runtime-coupled: `build-queue-runner.ps1`'s `$buildLogPath`
assignment sits inside a `Get-SafeValue { }` scriptblock, invoked via `& $Block` (a PowerShell
child scope) — this is directly readable from source (INVESTIGATION.md serving-path node 6) and
was additionally confirmed by an isolated deterministic micro-repro
(`scratchpad/repro.ps1` + `repro-child.ps1`, no production script touched). No further
runtime-assumption validation gate is required before the fix.

## Cross-feature Integration Notes

Sibling of `build-queue-hygiene-dot-source-discarded-in-child-scope` (same defect CLASS —
child-scope variable discard via `Get-SafeValue { }` / `& $Block` — a different variable; fixed
`2d9f8ae` 2026-07-06). This bug's WU-1 RED guard follows that sibling's regression-guard template
(`Describe 'scope-in-caller guard ...'` in `build-queue-hygiene.Tests.ps1`). No hard `**Depends
on:**` block — the SPEC carries only a `**Related:**` line.

---

### Phase: fix — build-queue `$buildLogPath` main-scope bind

**Scope:** Bind `$buildLogPath` in `build-queue-runner.ps1`'s main scope (not inside the
`Get-SafeValue { }` child scope) so the build-log classifier (`Test-BuildProducedNoOutput` /
`Test-BuildLogFailure`) reads the real captured log instead of `$null`, reviving both the
`no-output` gate and the co-defeated `log-failure-override` path.

**Status:** Complete

**Deliverables:**
- [x] WU-1 — RED regression guard: AST-based Pester assertion in `build-queue-hygiene.Tests.ps1`
      that `$buildLogPath = Join-Path ... "$Seq.build.log"` in `build-queue-runner.ps1` is a
      main/script-scope statement, not nested inside a `Get-SafeValue { }` scriptblock argument.
      Landed `27174696` (RED against the pre-fix runner).
- [x] WU-2 — Fix: moved `$buildLogPath = Join-Path $logsDir "$Seq.build.log"` and the
      `$startProcParams['RedirectStandardOutput'/'RedirectStandardError']` assignments out of the
      `Get-SafeValue { }` block into `build-queue-runner.ps1`'s main scope; only the fail-open
      `New-Item -ItemType Directory` dir-create stays wrapped. Turns WU-1 green. Landed `7108b2e8`.
      `$buildLogPath = $null` init (`:86`→ now `:124`) retained; classify branches
      (`Test-BuildProducedNoOutput` / `Test-BuildLogFailure`) untouched, per the investigation's
      "do NOT touch the classifier" constraint.
- [x] Re-verified intact after the later `801aec12` build-queue generalization commit (ops
      manifests / hygiene profiles / ETA+lanes) — `$buildLogPath` main-scope bind survived that
      refactor unchanged (confirmed by direct source read this session).

**Minimum Verifiable Behavior:** `powershell.exe -ExecutionPolicy Bypass -Command "Invoke-Pester
-Path 'user/scripts/build-queue-hygiene.Tests.ps1' -Output Detailed"` — WU-1's guard
(`'scope-in-caller guard -- buildLogPath assignment is main-scope, not Get-SafeValue child scope
(regression guard)'`) passes. **Verified 2026-07-12:** full suite 175/175 passed (0 failed).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (build-tooling
class); validation is the Pester suite + the operator-owned live re-verify below.

**Prerequisites:** None (first/only phase; Concluded SPEC, root cause traced).

**Files modified:**
- `user/scripts/build-queue-hygiene.Tests.ps1` — WU-1 RED guard (commit `27174696`).
- `user/scripts/build-queue-runner.ps1` — WU-2 main-scope bind (commit `7108b2e8`).

**Testing Strategy:** AST-based structural regression guard (parses `build-queue-runner.ps1`,
finds the `$buildLogPath = Join-Path ... build.log` `AssignmentStatementAst`, asserts it has no
`ScriptBlockExpressionAst` ancestor) — mirrors the sibling bug's proven pattern. No mock/fake of
`Get-SafeValue` semantics; the guard reads the real caller source.

**Integration Notes for Next Phase:** Terminal phase — the runner-side fix is complete and
Pester-verified. The two Runtime Verification rows below require a live Cognito worktree + `/msbuild`
on a Windows host with a real Cognito checkout (absent on this machine per workspace `CLAUDE.md`);
they are operator-owned and deferred to the work laptop, not blocking `Fixed` status per the
`operator-directed-interactive` provenance track (precedent: `build-queue-recycle-kills-concurrent-worktree-build`
FIXED.md, which shipped with an identical outstanding real-worktree row).

#### Implementation Notes — fix (2026-07-12)

**Pre-landed (prior session, 2026-07-06):** WU-1 (`27174696`) and WU-2 (`7108b2e8`) were both
already committed to `main` before this session started. This session's work was verification +
closeout, not new implementation:
- Confirmed via `git log` + direct source read that the fix is intact after the intervening
  `801aec12` generalization commit (ops manifests / hygiene profiles / ETA+lanes) — no regression.
- Ran the full `build-queue-hygiene.Tests.ps1` suite: found 3 UNRELATED pre-existing failures
  (`Add-ProcessToBuildJob` / `Stop-BuildJobTree` / `Reset-CompilerServer` fail-open assertions),
  triaged as a DIFFERENT defect (Pester `{ $result = Foo } | Should -Not -Throw` child-scope
  discard IN THE TEST FILE ITSELF — same defect CLASS as this bug's production root cause, but a
  distinct instance already flagged in the test file's own in-place comments as "the 3 known
  pre-existing failures"). Fixed in the SAME commit as this closeout since the root cause is
  unambiguous, already documented in-file, and lies inside this file (see the secondary-task
  report for detail) — turns the suite 172/175 → 175/175.
- Ran the required regression set: `build-queue.Tests.ps1` (2/2), `build-queue-runner.Tests.ps1`
  (4/4), `build-queue-await.Tests.ps1` (8/8) — all green.
- Ran `python user/scripts/lint-skills.py` — clean (no-op for this change, as the plan predicted).

**Review verdict:** PASS — WU-1/WU-2 diffs re-read against the INVESTIGATION.md serving-path trace
and the "do NOT touch the classifier / Read-WithRetry" constraint; both honored. No new production
code risk introduced this session (the runner/classifier files were not touched — only the sibling
test-file fix, out of this phase's file list but in-scope per the secondary triage task).

## Runtime Verification

- [ ] <!-- verification-only --> Live `/msbuild` on a clean Cognito worktree reports `RESULT=PASS
  (build_fidelity=verified)` on an exit-0 compile (was false `no-output` FAIL). Operator, Windows
  host with a real Cognito checkout — **deferred to work laptop** (Cognito is intentionally absent
  on this machine per workspace `CLAUDE.md`).
- [ ] <!-- verification-only --> `log-failure-override` revives: a genuinely-broken build (MSBuild
  error signature, exit 0) reports `RESULT=FAIL (build_fidelity=log-failure-override)`, proving the
  classify block now reads the log. Operator, Windows host — **deferred to work laptop**.
