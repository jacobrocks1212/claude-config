# Worktree CLAUDE/AGENTS Doc Drift — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Tracer: validate the nested-symlink mechanism on ONE doc

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-02
**Work completed:**
- Append to `RootFiles`: added `'Cognito.Core\CLAUDE.local.md'` as the 3rd entry of the `cognito-forms` `RootFiles` array in `manifest.psd1` (no `RootFilesNested` key — SPEC "Decided Approach" overload confirmed; no `setup.ps1` change needed). Verified parse via `Import-PowerShellDataFile`.
- Delete stopgaps: removed the real-file stopgap copies of `Cognito.Core\CLAUDE.local.md` from `Cognito Forms-B` and `Cognito Forms-C` (guarded to delete only real files, not symlinks) so `setup.ps1:149-151` would recovery-LINK rather than WARN-skip them.
- Bootstrap MOVE + recovery-LINK: real `.\setup.ps1 bootstrap -Target Repos` console showed `Bootstrap: 1 moved, 6 linked, 76 skipped, 2 warnings` — `MOVE Repo:cognito-forms | CLAUDE.local.md` (main's nested real file → `claude-config\repos\cognito-forms\Cognito.Core\CLAUDE.local.md`, then symlinked) and `LINK ... (recovery)` for the nested doc on -B/-C/-D. (Bootstrap also opportunistically recovered the 3 pre-existing `MISSING normalize-crlf.ps1` links — unrelated to this WU, lives in the Cognito worktrees not claude-config git.)
- Trackability + validation: `git check-ignore` exit 1 (NOT ignored → trackable); `git add` succeeded **without `-f`**. `.\setup.ps1 check -Target Repos` → `Check: 83 OK, 2 broken, 0 absent` (Mappings 81→85). Broken went 5→2 (did NOT increase vs baseline 5). Direct filesystem check: all 4 worktrees (main/-B/-C/-D) resolve `Cognito.Core\CLAUDE.local.md` as a ReparsePoint targeting the claude-config source (VERDICT=OK ×4). main's content byte-identical (SHA256 `7F6D28EB…2833`, 5572 bytes, matched pre-move hash).

**Integration notes (for Phase 2):**
- **`git add -f` NOT required.** claude-config does not gitignore `repos/cognito-forms/**/CLAUDE.local.md` — Phase 2 can `git add` the other 10 relocated sources plainly (no `-f`).
- **Nested `Join-Path` mapping resolves correctly** — the load-bearing "nested RootFiles → working symlink across all worktrees, zero `setup.ps1` change" assumption is VALIDATED end-to-end. Phase 2 can bulk-register the remaining 10 with confidence; **no `setup.ps1` fix needed**, FALSIFICATION HALT not triggered.
- **Delete -B/-C stopgaps BEFORE bootstrap** for each of the 10 (same WARN-skip gate at `setup.ps1:149-151`).
- **`check` displays nested RootFiles by basename** (`CLAUDE.local.md`), not the full subpath — do NOT grep the check output for `Cognito.Core` to confirm OK; use the broken-count delta + direct filesystem reparse check instead.

**Pitfalls & guidance:**
- **`powershell.exe` (Windows PowerShell 5.1) launched via the Bash tool is broken here:** its `PSModulePath` is polluted with PowerShell 7's `Microsoft.PowerShell.Utility` v7.0.0.0, which won't bind into the 5.1 engine, so `Import-PowerShellDataFile` (used by `setup.ps1:39`) throws `CommandNotFoundException`. Ran `setup.ps1` via **`pwsh` (PowerShell 7.5.5)** instead — the nested-symlink mechanism (`New-Item -ItemType SymbolicLink`, `Join-Path`, reparse detection) is engine-independent, so this does not affect the tracer's validity. Phase 2 should likewise invoke `setup.ps1` via `pwsh` from the Bash tool (or fix the 5.1 `PSModulePath`).
- A symlink's own `Get-Item ... .Length` reports 0; verify content byte-identity via `Get-FileHash` (resolves through the link), not `.Length`.

**Files modified:**
- `manifest.psd1` — appended `'Cognito.Core\CLAUDE.local.md'` to `cognito-forms` `RootFiles` (line 27).
- `repos/cognito-forms/Cognito.Core/CLAUDE.local.md` — net-new relocated source (created by bootstrap MOVE; byte-identical 5572-byte copy), `git add`ed.
- Deleted (in Cognito worktrees, not claude-config git): `Cognito Forms-B\Cognito.Core\CLAUDE.local.md`, `Cognito Forms-C\Cognito.Core\CLAUDE.local.md` stopgaps.

**Review verdict:** PASS (2026-07-02) — inline review (2 files / 93 lines, 92 of which are the byte-identical relocated doc). Ground-truth verified: yes (no subagents dispatched — runtime-observation spike per plan override; all verification commands self-executed by the orchestrator). Nested-symlink assumption validated; FALSIFICATION HALT not triggered.
