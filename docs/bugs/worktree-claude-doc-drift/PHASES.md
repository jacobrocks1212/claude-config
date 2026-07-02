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
- [ ] Append the remaining 10 nested subpaths to `RootFiles` in manifest.psd1.
- [ ] Delete all remaining `-B`/`-C` stopgap copies of those 10 docs.
- [ ] Run `.\setup.ps1 bootstrap -Target Repos`; `git add` (`-f` if Phase 1 showed it necessary) the 10 relocated sources in claude-config.
- [ ] Tests: `.\setup.ps1 check` shows OK for all 11 subdir mappings across all present worktrees.

**Minimum Verifiable Behavior:** `.\setup.ps1 check` prints `OK` for all 11 subdir `CLAUDE.local.md` mappings in every present worktree (main/-B/-C/-D); no `WARN`/`REAL`/`MISSING` rows for any subdir doc; -D now carries all 11 as symlinks.

**Runtime Verification**
- [ ] <!-- verification-only --> `setup.ps1 check` reports OK for all 11 subdir mappings × all present worktrees; zero WARN/REAL/MISSING rows for subdir docs.
- [ ] <!-- verification-only --> -D worktree gains working symlinks for docs it previously lacked entirely.

**MCP Integration Test Assertions:** N/A — same class as Phase 1 (filesystem/symlink tooling).

**Prerequisites:** Phase 1 (mechanism validated; staging approach known).

**Files likely modified:** `manifest.psd1`; 10 relocated `repos\cognito-forms\**\CLAUDE.local.md` (net-new via bootstrap MOVE); deleted `-B`/`-C` stopgaps.

**Testing Strategy:** `setup.ps1 check` full pass; spot-check content integrity on 2-3 relocated docs.

**Integration Notes for Next Phase:** after this phase the manifest RootFiles is the complete registry of subdir docs — Phase 3's UNREGISTERED backfill guard should now find ZERO unregistered subdir docs (any hit is a real new-drift signal, not a false positive).

---

### Phase 3: Warn-only Invoke-Check additions — team-owned-doc drift detector + unregistered-subdir backfill guard

**Scope:** Add two warn-only passes to `setup.ps1`'s `Invoke-Check`, modeled on the existing warn-only hook-registration advisory block (setup.ps1:215-259). Neither pass mutates anything or changes the exit code (`$broken` unchanged).

**Deliverables:**
- [ ] Team-owned-doc drift pass: for each worktree, compare its tracked `AGENTS.md`, `CLAUDE.md`, `Cognito.Web.Client\AGENTS.md` against the MAIN worktree working copy. Emit `DRIFT` when content differs; emit `BEHIND` (separate advisory) when the file is absent because the branch is stale. Warn-only — never copy/symlink/mutate git-tracked content.
- [ ] Unregistered-subdir backfill guard: scan the main worktree for `*/CLAUDE.local.md` files not present in the manifest RootFiles; emit `UNREGISTERED` for each (re-drift prevention).
- [ ] Guard against absent worktrees (`-A` and any future missing path): passes must no-op via `Test-Path` rather than erroring.
- [ ] Tests: `.\setup.ps1 check` exercises both passes; exit code / `$broken` count unchanged from before.

**Minimum Verifiable Behavior:** running `.\setup.ps1 check` prints `BEHIND` advisories for -D's three missing team-owned docs (stale branch inno/documents-and-signing), prints ZERO `UNREGISTERED` rows (all 11 subdir docs registered in Phase 2), prints no `DRIFT` for worktrees whose team docs match main, and the final `Check: N OK, M broken, K absent` broken count is identical to a pre-Phase-3 run (warn-only).

**Runtime Verification**
- [ ] <!-- verification-only --> `setup.ps1 check` emits `BEHIND` for AGENTS.md / CLAUDE.md / Cognito.Web.Client\AGENTS.md in -D (branch predates their addition); does NOT emit `DRIFT` for those (absence ≠ content drift).
- [ ] <!-- verification-only --> `setup.ps1 check` emits zero `UNREGISTERED` rows after Phase 2 (all subdir docs registered).
- [ ] <!-- verification-only --> the `Check:` summary `broken` count is unchanged vs a pre-Phase-3 run — the passes are warn-only and do not affect exit code.
- [ ] <!-- verification-only --> passes no-op cleanly when a worktree directory is absent (no exception thrown).

**MCP Integration Test Assertions:** N/A — PowerShell tooling; verification is `setup.ps1 check` console output + exit code.

**Prerequisites:** Phase 2 (soft) — so the UNREGISTERED backfill guard has zero false positives. Independent of Phases 1-2 at the file level (touches `setup.ps1` only; Phases 1-2 touch `manifest.psd1` + filesystem).

**Files likely modified:** `setup.ps1` — `Invoke-Check` only.

**Testing Strategy:** run `setup.ps1 check` before and after; assert new advisory lines appear and the numeric broken/exit result is unchanged. -D is the natural BEHIND fixture; no git-tracked content is mutated to test DRIFT.

**Integration Notes for Next Phase:** none (terminal phase).

---

## Review Notes

**Batch: PHASES.md authoring — Review verdict:** PASS (2026-07-02)

- Ground-truth verified: yes — fresh `wc -l`/`grep` re-run matched the writer's GROUND-TRUTH block (89 lines, 8 `verification-only` markers, phases at 7/35/63).
- Both SPEC root-cause tracks covered; all four Open Questions resolved (drift ref = main worktree working copy with `BEHIND` for stale-branch absence; `RootFiles` overload — zero `setup.ps1` code change; `-A`/absent-worktree no-op via `Test-Path`; backfill guard included as `UNREGISTERED`).
- Phase 1 is an explicit runtime-validation spike for the load-bearing "nested `Join-Path` symlink works" assumption (satisfied only by observing the real `setup.ps1` run); falsification halts Phase 2.
- Verification distributed per phase via `setup.ps1 check`; the three `MCP: N/A` declarations are honest (claude-config has no MCP/app surface), not deferrals.
- Authoring rules satisfied: marker-tagged RV rows, no gate-owned rows, no `**Branch:**` stamp (on `main`), Cross-feature Integration Notes correctly omitted (no hard deps).
