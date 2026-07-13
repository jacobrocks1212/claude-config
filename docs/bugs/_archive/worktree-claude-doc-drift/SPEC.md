# Worktree CLAUDE/AGENTS Doc Drift — Investigation Spec

> Per-repo Claude docs are inconsistent across the Cognito Forms git worktrees: personal subdir `CLAUDE.local.md` files exist only in the main worktree, and team-owned tracked docs vary by branch — because the claude-config symlink manifest covers neither.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-02
**Placement:** claude-config/docs/bugs/worktree-claude-doc-drift/
**Related:** `manifest.psd1`, `setup.ps1`, `repos/cognito-forms/`

---

## Verified Symptoms

<!-- Confirmed via direct filesystem/git inspection this session; design intent confirmed with Jacob via AskUserQuestion -->

1. **[VERIFIED]** The 11 subdirectory `*/CLAUDE.local.md` docs (`Cognito.Core/`, `Cognito/`, `Cognito.Services/`, `Cognito.QueueJob/`, `Cognito.UnitTests/`, `Cognito.Web.Client/` + `apps/spa`, `apps/client`, `libs/model.js`, `libs/vuemodel`, `libs/types`) exist **only in the main worktree** (`Cognito Forms`). They are missing from `-B`, `-C`, and `-D`. — confirmed by per-worktree presence scan.
2. **[VERIFIED]** These subdir docs are **regular gitignored files** (`git check-ignore` matches; `readlink` shows no symlink), have **no copy in `claude-config`**, and **no `manifest.psd1` entry**. Git therefore cannot carry them between worktrees, and the symlink system does not manage them. — confirmed by `find -printf`, `git check-ignore`, and manifest read.
3. **[VERIFIED]** Team-owned docs `AGENTS.md`, `CLAUDE.md`, `Cognito.Web.Client/AGENTS.md` are **git-tracked** (`git ls-files --error-unmatch` succeeds). `-D` lacks them only because its branch (`inno/documents-and-signing`) predates their addition on `main`; `-B`/`-C` have them via git. — confirmed by tracked/ignored probe across worktrees.
4. **[VERIFIED]** Only the **root** `CLAUDE.local.md` is claude-config-managed: all four worktrees symlink it to `claude-config/repos/cognito-forms/CLAUDE.local.md`. — confirmed by `readlink` on all four roots + `manifest.psd1:27`.
5. **[VERIFIED]** `Cognito Forms-A` directory does not exist on disk despite having no manifest entry issue — there is no `-A` worktree to project into. — confirmed by directory scan.

## Reproduction Steps

1. From the main worktree, note a subdir doc exists, e.g. `Cognito.Core/CLAUDE.local.md`.
2. `cd` into any other worktree (`Cognito Forms-B/C/D`).
3. Look for the same file.

**Expected:** The same per-repo Claude guidance is present in every worktree (single source of truth).
**Actual:** Subdir `CLAUDE.local.md` docs are absent in non-main worktrees; team-owned tracked docs match only if the branch is current with `main`.
**Consistency:** Always, for any worktree other than the one where a given doc was authored.

## Evidence Collected

### Worktree doc-presence matrix (verified this session)

| Worktree | Branch | Tracked docs (AGENTS.md / CLAUDE.md / Web.Client AGENTS.md) | Subdir `*/CLAUDE.local.md` (11) |
|---|---|---|---|
| Cognito Forms (main) | p/cog-pay-account-notifications | present | **present (source of truth)** |
| Cognito Forms-A | — | directory absent | — |
| Cognito Forms-B | p/cogpay-notification-banner-defects | present (via git) | missing → stopgap-copied this session |
| Cognito Forms-C | p/ps-ff-tests | present (via git) | missing → stopgap-copied this session |
| Cognito Forms-D | inno/documents-and-signing | missing (stale branch) | missing |

### Symlink manifest / mechanism
- `manifest.psd1:27` — `RootFiles = ('CLAUDE.local.md', 'worktree-wizard.ps1')`: only root-level personal files are symlinked.
- `manifest.psd1:28–35` — comments establish the design invariant: team-owned, git-tracked files are **intentionally not symlinked**; only personal/gitignored files are.
- `manifest.psd1:47–58` — `cognito-forms-B/C/D` are `Alias = 'cognito-forms'`, so `setup.ps1` symlinks the same `claude-config/repos/cognito-forms/` source into each worktree path.
- `setup.ps1:67–76` — RootFiles mapping uses `Live = Join-Path $livePath $f` / `Repo = Expand-RepoPath "repos\$configName\$f"`. **A nested `$f` (e.g. `Cognito.Core\CLAUDE.local.md`) already resolves correctly** — no code change needed to support subdir symlinks.
- `setup.ps1:122–126` and `:158–163` — parent directories are created on both the repo and live sides before linking, so nested targets link cleanly (recovery LINK path at `:163`).
- `setup.ps1:149–151` — **WARN + skip when both live and repo are real files.** Consequence: the B/C stopgap copies (real files) must be deleted before `bootstrap`/`repair`, or they will be skipped rather than converted to symlinks.

### claude-config state
- `claude-config/repos/cognito-forms/` currently contains only the root `CLAUDE.local.md` (+ `.claude/` tree) — no subdir docs.
- `claude-config/docs/bugs/` exists and was empty; this spec is the first entry.
- claude-config is on branch `main`.

## Theories

### Theory 1: Manifest coverage gap for personal subdir docs
- **Hypothesis:** Subdir `CLAUDE.local.md` drift because `RootFiles` only lists root-level names and the subdir docs were authored directly in the main worktree, never registered in the manifest.
- **Supporting evidence:** `manifest.psd1:27`; subdir docs absent from `claude-config`; gitignored so git can't propagate them.
- **Contradicting evidence:** none.
- **Status:** Confirmed.

### Theory 2: Team-owned docs drift is a git branch-freshness artifact, not a symlink gap
- **Hypothesis:** `AGENTS.md`/`CLAUDE.md` differ across worktrees because each worktree is on a different branch; they are delivered by git, and symlinking them is impossible without breaking git-tracking.
- **Supporting evidence:** files are `git ls-files`-tracked; `-D` on a pre-addition branch lacks them; `manifest.psd1:28–35` deliberately excludes team-owned files from symlinking.
- **Contradicting evidence:** none — a path cannot simultaneously be a tracked regular file and a symlink into claude-config.
- **Status:** Confirmed.

## Proven Findings

1. **Root cause (personal docs):** the symlink manifest does not register subdir `CLAUDE.local.md` files; being gitignored, they cannot travel via git either, so they exist only where authored. **Fix: relocate them into `claude-config/repos/cognito-forms/` (mirroring paths) and add manifest entries so `setup.ps1` symlinks them into every worktree.** No `setup.ps1` change required — `RootFiles` already handles nested paths (`setup.ps1:70`, `:122–126`, `:158–163`).
2. **Root cause (team-owned docs):** these are git-tracked and must stay real files in the repo (teammates who don't use claude-config depend on them). They cannot be symlinked without a git type-change conflict. Cross-worktree consistency for them is a git branch-freshness concern. **Fix: add a drift *detector* to `setup.ps1 check` that reports when a worktree's tracked copy diverges from (or is missing vs.) a canonical reference — warn only, never mutate git-tracked content.**

## Decided Approach (confirmed with Jacob)

- **Team-owned files → drift detection (warn only).** `setup.ps1 check` compares each worktree's tracked team-owned docs against a canonical reference (main worktree / `origin/main`) and reports divergence or absence. It does not copy or symlink them; remediation stays a human git action. Preserves the `manifest.psd1:28–35` invariant.
- **Personal subdir docs → claude-config owns all subdir `CLAUDE.local.md`.** Move all 11 into `claude-config/repos/cognito-forms/` (mirroring the repo-relative subpaths), register each in the manifest (extend `RootFiles`, or a dedicated `RootFilesNested` list, with subdir paths), and let `setup.ps1` symlink them into main + B + C + D.
- **Stopgap copies → replace with symlinks during the fix.** Delete the regular-file copies added to `-B` and `-C` this session first (so `setup.ps1:149–151` doesn't WARN/skip), then `setup.ps1 bootstrap -Target Repos` re-creates them as symlinks.

## Reuse Ledger

| Capability | Existing system | Verdict | Evidence |
|---|---|---|---|
| Symlink personal files into all worktrees (incl. aliased B/C/D) | `RootFiles` + setup mapping loop + `Alias` | **extend** — add subdir `CLAUDE.local.md` paths to the manifest | `manifest.psd1:27,47–58`; `setup.ps1:67–76` |
| Symlink into subdirectories (nested Live/Repo) | `Join-Path`-based mapping + parent-dir creation | **reuse-as-is** — already supported, no code change | `setup.ps1:70,122–126,158–163` |
| Convert existing real files → managed symlinks | bootstrap MOVE / COPYLINK / recovery-LINK paths | **reuse-as-is** (delete B/C copies first to avoid WARN/skip) | `setup.ps1:128–165` (WARN gate `:149–151`) |
| Prevent team-owned tracked-file drift | none — deliberately excluded from symlinking | **build-new** — drift detector in `setup.ps1 check` | `manifest.psd1:28–35` |

## Affected Area

| Component | Files | Impact |
|---|---|---|
| Symlink manifest | `claude-config/manifest.psd1` | Add subdir `CLAUDE.local.md` entries for `cognito-forms` |
| Symlink source | `claude-config/repos/cognito-forms/**/CLAUDE.local.md` (new) | Relocate 11 docs here as the single source of truth |
| Setup tooling | `claude-config/setup.ps1` | Add team-owned-file drift detection to `check` (new); no change needed for nested symlinks |
| Worktrees | `Cognito Forms`, `-B`, `-C`, `-D` | main: docs move out to symlinks; B/C: delete stopgap copies then symlink; D: gains symlinks |

## Open Questions

- **Canonical reference for the drift check:** compare tracked docs against the main worktree's working copy, or against `origin/main` (network) — and should a `-D`-style "file entirely absent because branch is stale" read as drift, or be reported separately as "branch behind main"?
- **Manifest shape for nested paths:** overload `RootFiles` with subpaths, or introduce an explicit `RootFilesNested` key for readability? (Behavior is identical; this is a legibility choice.)
- **`-A` and future worktrees:** `-A` has no directory today; confirm the drift check and bootstrap simply no-op on absent worktree paths (they should, given `Test-Path` guards) rather than erroring.
- **Backfill of new subdir docs:** once relocated, is there a lint/check to catch a *new* subdir `CLAUDE.local.md` authored directly in a worktree (re-introducing the same drift) before it's registered in the manifest?
