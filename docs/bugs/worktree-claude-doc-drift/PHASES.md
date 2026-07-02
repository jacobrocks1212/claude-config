# Implementation Phases — Worktree CLAUDE/AGENTS Doc Drift

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config symlink/PowerShell tooling; no app runtime or MCP server in this repo (verification is filesystem/symlink state via `setup.ps1 check`).

### Phase 1: Tracer — relocate & register ONE subdir doc; validate the nested-symlink mechanism end-to-end

**Scope:** De-risk the whole personal-docs fix by proving the "nested RootFiles → working symlink across all worktrees, no setup.ps1 change" assumption on ONE doc (`Cognito.Core\CLAUDE.local.md`) before touching the other 10. This is an explicit runtime-validation spike — it must be satisfied by observing the real `setup.ps1` run, not by reading code.

**Deliverables:**
- [x] Append `Cognito.Core\CLAUDE.local.md` to `RootFiles` in manifest.psd1 (cognito-forms entry).
- [x] Delete the `-B` and `-C` stopgap real-file copies of `Cognito.Core\CLAUDE.local.md`.
- [x] Run `.\setup.ps1 bootstrap -Target Repos` and confirm main MOVEs the real file into `claude-config\repos\cognito-forms\Cognito.Core\CLAUDE.local.md` (+ recovery-LINK on -B/-C/-D).
- [x] Verify the relocated source is git-trackable in claude-config (`git check-ignore`; `git add -f` if ignored). Tests: `.\setup.ps1 check` shows OK for this nested mapping across all present worktrees.

**Minimum Verifiable Behavior:** `.\setup.ps1 check` prints `OK` for the `Cognito.Core\CLAUDE.local.md` mapping in main, -B, -C, and -D; `Get-Item` on main's `Cognito.Core\CLAUDE.local.md` shows a ReparsePoint whose target resolves to the claude-config source; file content is byte-identical to the pre-move original.

**Runtime Verification**
- [x] <!-- verification-only --> `setup.ps1 check` reports `OK` (symlink → claude-config) for `Cognito.Core\CLAUDE.local.md` in main + -B + -C + -D (present worktrees).
- [x] <!-- verification-only --> main worktree's `Cognito.Core\CLAUDE.local.md` is a symlink (ReparsePoint), not a real file, and its content is unchanged.

**MCP Integration Test Assertions:** N/A — claude-config PowerShell/symlink tooling; no runtime-observable app behavior (verification is filesystem/symlink state via setup.ps1 check).

**Prerequisites:** None (first phase).

**Files likely modified:** `manifest.psd1` (RootFiles append); relocated file `repos\cognito-forms\Cognito.Core\CLAUDE.local.md` (net-new via bootstrap MOVE); deleted `-B`/`-C` stopgaps.

**Testing Strategy:** single-file blast radius; `setup.ps1 check` is the observable. If bootstrap does NOT produce a working nested symlink (Windows path-with-spaces + nested dir edge case), STOP — the "no setup.ps1 change" assumption is falsified and Phase 2 must not proceed until setup.ps1 is fixed.

**Integration Notes for Next Phase:** carry gotchas 1-3 above. Record whether `git add -f` was required (tells Phase 2 how to stage the other 10). Confirm the nested `Join-Path` mapping resolved correctly so Phase 2 can bulk-register with confidence.

---

### Phase 2: Bulk relocate & register the remaining 10 subdir docs

**Scope:** Apply the Phase-1-validated mechanism to the other 10 subdir CLAUDE.local.md docs.

**Deliverables:**
- [x] Append the remaining 10 nested subpaths to `RootFiles` in manifest.psd1.
- [x] Delete all remaining `-B`/`-C` stopgap copies of those 10 docs.
- [x] Run `.\setup.ps1 bootstrap -Target Repos`; `git add` (`-f` if Phase 1 showed it necessary) the 10 relocated sources in claude-config.
- [x] Tests: `.\setup.ps1 check` shows OK for all 11 subdir mappings across all present worktrees.

**Minimum Verifiable Behavior:** `.\setup.ps1 check` prints `OK` for all 11 subdir `CLAUDE.local.md` mappings in every present worktree (main/-B/-C/-D); no `WARN`/`REAL`/`MISSING` rows for any subdir doc; -D now carries all 11 as symlinks.

**Runtime Verification**
- [x] <!-- verification-only --> `setup.ps1 check` reports OK for all 11 subdir mappings × all present worktrees; zero WARN/REAL/MISSING rows for subdir docs.
- [x] <!-- verification-only --> -D worktree gains working symlinks for docs it previously lacked entirely.

**MCP Integration Test Assertions:** N/A — same class as Phase 1 (filesystem/symlink tooling).

**Prerequisites:** Phase 1 (mechanism validated; staging approach known).

**Files likely modified:** `manifest.psd1`; 10 relocated `repos\cognito-forms\**\CLAUDE.local.md` (net-new via bootstrap MOVE); deleted `-B`/`-C` stopgaps.

**Testing Strategy:** `setup.ps1 check` full pass; spot-check content integrity on 2-3 relocated docs.

**Integration Notes for Next Phase:** after this phase the manifest RootFiles is the complete registry of subdir docs — Phase 3's UNREGISTERED backfill guard should now find ZERO unregistered subdir docs (any hit is a real new-drift signal, not a false positive).

#### Implementation Notes — Phase 2 (2026-07-02)

**Work completed:** Appended the 10 remaining subdir subpaths to `RootFiles` (now 13 entries: root + worktree-wizard + 11 subdir docs). Deleted 20 stopgap copies (10 in -B, 10 in -C). Bootstrapped: 10 docs MOVEd from main into `claude-config/repos/cognito-forms/**`, recovery-LINKed across -B/-C/-D. Staged all 10 relocated sources with `git add` (no `-f` needed — confirms Part 1's trackability finding). Closing `setup.ps1 check -Target Repos` = **123 OK, 2 broken, 0 absent**; the 2 broken are the pre-existing unrelated REAL files (`cognito-docs\settings.local.json`, `cognito-forms\normalize-crlf.ps1`) — identical to baseline, no increase. All 11 subdir mappings OK × 4 present worktrees; zero subdir WARN/REAL/MISSING/WRONG. Content integrity verified: moved files' on-disk byte sizes match the audit table exactly (Cognito.Services=7744, Cognito=3533, model.js=3083).

**Pitfall / environment gotcha (carry into Phase 3):** `powershell.exe` (Windows PowerShell 5.1) on this machine **cannot** run `setup.ps1` — two blockers: (1) polluted `PSModulePath` (PS7 paths prepended) shadows the 5.1 built-in `Microsoft.PowerShell.Utility`, so `Import-PowerShellDataFile` is undiscoverable; and (2) 5.1's `New-Item -ItemType SymbolicLink` does NOT pass the `ALLOW_UNPRIVILEGED_CREATE` flag, so symlink creation fails "Administrator privilege required" even with Developer Mode ON + non-elevated. **Fix: run setup.ps1 under `pwsh` (PowerShell 7.5.5, installed)** — it passes the unprivileged flag (Dev Mode makes symlink creation work non-elevated) and has `Import-PowerShellDataFile` natively. The aborted 5.1 bootstrap left `Cognito\CLAUDE.local.md` half-moved (MOVE succeeded, symlink failed); the pwsh re-run's recovery-LINK path cleanly reconciled it (repo present + live absent → LINK).

**Review verdict:** PASS — ground truth verified via orchestrator's own `setup.ps1 check` + byte-size spot-check; zero subagents dispatched (config/filesystem batch, no forbidden-extension source files, TDD=no per plan).

---

### Phase 3: Warn-only Invoke-Check additions — team-owned-doc drift detector + unregistered-subdir backfill guard

**Scope:** Add two warn-only passes to `setup.ps1`'s `Invoke-Check`, modeled on the existing warn-only hook-registration advisory block (setup.ps1:215-259). Neither pass mutates anything or changes the exit code (`$broken` unchanged).

**Deliverables:**
- [x] Team-owned-doc drift pass: for each worktree, compare its tracked `AGENTS.md`, `CLAUDE.md`, `Cognito.Web.Client\AGENTS.md` against the MAIN worktree working copy. Emit `DRIFT` when content differs; emit `BEHIND` (separate advisory) when the file is absent because the branch is stale. Warn-only — never copy/symlink/mutate git-tracked content.
- [x] Unregistered-subdir backfill guard: scan the main worktree for `*/CLAUDE.local.md` files not present in the manifest RootFiles; emit `UNREGISTERED` for each (re-drift prevention).
- [x] Guard against absent worktrees (`-A` and any future missing path): passes must no-op via `Test-Path` rather than erroring.
- [x] Tests: `.\setup.ps1 check` exercises both passes; exit code / `$broken` count unchanged from before.

**Minimum Verifiable Behavior:** running `.\setup.ps1 check` prints `BEHIND` advisories for -D's three missing team-owned docs (stale branch inno/documents-and-signing), prints ZERO `UNREGISTERED` rows (all 11 subdir docs registered in Phase 2), prints no `DRIFT` for worktrees whose team docs match main, and the final `Check: N OK, M broken, K absent` broken count is identical to a pre-Phase-3 run (warn-only).

**Runtime Verification**
- [x] <!-- verification-only --> `setup.ps1 check` emits `BEHIND` for AGENTS.md / CLAUDE.md / Cognito.Web.Client\AGENTS.md in -D (branch predates their addition); does NOT emit `DRIFT` for those (absence ≠ content drift).
- [x] <!-- verification-only --> `setup.ps1 check` emits zero `UNREGISTERED` rows after Phase 2 (all subdir docs registered).
- [x] <!-- verification-only --> the `Check:` summary `broken` count is unchanged vs a pre-Phase-3 run — the passes are warn-only and do not affect exit code.
- [x] <!-- verification-only --> passes no-op cleanly when a worktree directory is absent (no exception thrown).

**MCP Integration Test Assertions:** N/A — PowerShell tooling; verification is `setup.ps1 check` console output + exit code.

**Prerequisites:** Phase 2 (soft) — so the UNREGISTERED backfill guard has zero false positives. Independent of Phases 1-2 at the file level (touches `setup.ps1` only; Phases 1-2 touch `manifest.psd1` + filesystem).

**Files likely modified:** `setup.ps1` — `Invoke-Check` only.

**Testing Strategy:** run `setup.ps1 check` before and after; assert new advisory lines appear and the numeric broken/exit result is unchanged. -D is the natural BEHIND fixture; no git-tracked content is mutated to test DRIFT.

**Integration Notes for Next Phase:** none (terminal phase).

#### Implementation Notes — Phase 3 (2026-07-02)

**Work completed:** Added two warn-only advisory passes to `Invoke-Check` in `setup.ps1` (75 insertions), inserted after the existing hook-registration advisory block and before `return ($broken -eq 0)`, wrapped in a single try/catch that emits `WARN ... worktree doc-drift check skipped` on any failure. Re-imports `manifest.psd1`; main worktree = `Repos['cognito-forms'].Path`; other worktrees = every `Repos` entry with `.Alias -eq 'cognito-forms'` (-B/-C/-D). **Pass 1 (DRIFT/BEHIND):** for `AGENTS.md`, `CLAUDE.md`, `Cognito.Web.Client\AGENTS.md`, reads the MAIN copy as canonical reference, Test-Path-guards each worktree root (absent → no-op, covers -A), emits `BEHIND` on absent doc and `DRIFT` on `Get-Content -Raw` inequality. **Pass 2 (UNREGISTERED):** manual stack walk of main pruning `node_modules`/`.git`/`.claude` directories (perf — avoids traversing node_modules), flags any `CLAUDE.local.md` whose worktree-relative subpath is not in `RootFiles` (root doc skipped). Neither pass touches `$broken`.

**Runtime evidence:** `setup.ps1 check -Target Repos` → BEHIND=3 (-D × 3 team docs), DRIFT=0 (-B/-C match main), UNREGISTERED=0 (all 12 main docs = root + 11 registered subdir), `Check: 123 OK, 2 broken, 0 absent` (broken identical to the pre-Phase-3 run), no exception thrown (`doc-drift check skipped` count = 0), `$LASTEXITCODE` unset exactly as at baseline (the script returns a boolean and never calls `exit`; exit behavior unchanged).

**Pitfall:** must run under `pwsh` (PowerShell 7), NOT `powershell.exe` (5.1) — see the Phase 2 note (PSModulePath pollution hides `Import-PowerShellDataFile`; 5.1's `New-Item -ItemType SymbolicLink` can't create symlinks unprivileged). Do NOT use inline `if(){}else{}` expressions in string concatenation in 5.1; the code uses full if/else statement blocks.

**Review verdict:** PASS — ground truth verified via orchestrator's own `setup.ps1 check` (advisory counts + unchanged broken/exit); zero subagents dispatched (single-file `.ps1` batch, plan authorizes direct editing, TDD=no, no test harness).

---

## Review Notes

**Batch: PHASES.md authoring — Review verdict:** PASS (2026-07-02)

- Ground-truth verified: yes — fresh `wc -l`/`grep` re-run matched the writer's GROUND-TRUTH block (89 lines, 8 `verification-only` markers, phases at 7/35/63).
- Both SPEC root-cause tracks covered; all four Open Questions resolved (drift ref = main worktree working copy with `BEHIND` for stale-branch absence; `RootFiles` overload — zero `setup.ps1` code change; `-A`/absent-worktree no-op via `Test-Path`; backfill guard included as `UNREGISTERED`).
- Phase 1 is an explicit runtime-validation spike for the load-bearing "nested `Join-Path` symlink works" assumption (satisfied only by observing the real `setup.ps1` run); falsification halts Phase 2.
- Verification distributed per phase via `setup.ps1 check`; the three `MCP: N/A` declarations are honest (claude-config has no MCP/app surface), not deferrals.
- Authoring rules satisfied: marker-tagged RV rows, no gate-owned rows, no `**Branch:**` stamp (on `main`), Cross-feature Integration Notes correctly omitted (no hard deps).
