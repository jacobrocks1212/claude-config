---
kind: research-summary
feature_id: doc-drift-linter
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — doc-drift-linter

Internal harness mechanics; no external prior art needed. Evidence base is a live survey of every
claim surface and reality surface the SPEC's four checks compare, performed 2026-07-04 at lane
baseline (`b5c1021`).

## Surfaces verified (claim side)

1. **Root `CLAUDE.md`** — all three tables present and parseable as pipe tables:
   - `## Hooks` table (lines ~198–210): 11 rows — 9 registered-claim rows + 2 `**NOT
     registered**` rows (`fix-line-endings.ps1`, `run-eslint.ps1`).
   - `## Scripts` table (lines ~165–178): 12 rows, first cell backtick-quoted filename;
     `pipeline_visualizer/` is a trailing-slash directory row.
   - `### Coupled Skill Pairs` table (lines ~156–159): 2 rows, Files cell carries the two
     backticked SKILL.md paths joined by `↔`.
2. **`user/scripts/CLAUDE.md`** — `## Files in this directory` table (lines ~30–38): 7 rows
   (`lazy-state.py`, `lazy_core.py`, `bug-state.py`, `lazy_coord.py`, `toolify-miner.py`,
   `claude-bash-env.sh`, `lazy-queue-doc.py`); all exist on disk. The table is CURATED (dir holds
   ~40 files) → confirms the SPEC's doc→disk-only direction for the scripts check.
3. **`user/hooks/CLAUDE.md`** — prose only, no tables. Confirms D3's "scanned, zero structured
   claims in v1" honesty note. Its "Deliberately unwired" prose agrees with the root table's two
   NOT-registered rows.
4. **`manifest.psd1`** — shape confirmed: top-level `@{}` with `User`/`Personal`/`Workspace`
   arrays of `@{ Live=..; Repo=..; Type=.. }` and a `Repos = @{ 'name' = @{ ... } }` block.
   Repos keys: `cognito-forms` (Path + RootFiles + DotClaudeFiles + DotClaudeDirs),
   `cognito-forms-B/C/D` (Path + `Alias = 'cognito-forms'`), `cognito-docs` (Path +
   DotClaudeFiles). Single-quoted strings, `@()` arrays, `#` comments — nothing outside the D5
   parser's supported shape.

## Surfaces verified (reality side)

- **`user/settings.json` hooks object:** `SessionStart` (2 groups: `load-branch-docs-context.sh`
  on `startup|resume|clear|compact`; an inline `bash -c` plan-recovery command on `compact` —
  no hooks-path reference, correctly invisible to the extraction rule), `PreToolUse` (matchers
  `Read`, `Bash` ×5 hooks, `Agent`, `Skill`, `Write|Edit` ×2 hooks), `PostToolUse: []`.
- **`user/hooks/` on disk:** 12 `.sh` files + `CLAUDE.md`. Includes `lazy-dispatch-guard.sh` and
  `lazy-route-inject.sh`, which are neither table rows nor registered in tracked settings —
  consistent on the table↔settings axis (no v1 finding; their registration story lives in
  prose/untracked settings, out of scope per D1).
- **`user/scripts/lazy-parity-manifest.json`:** `{mechanic_sets, pairs}`; `pairs[]` = 5 entries,
  each with `canonical`/`derived` repo-relative paths + `axis` (`bug`|`cloud`) + `mechanic_set`.
- **`repos/` dirs:** `algobooth`, `cognito-docs`, `cognito-forms` (+ `CLAUDE.md`).

## Live drift inventory (what Phase 2 must fix)

| # | Check | Finding | Disposition |
|---|-------|---------|-------------|
| 1 | hooks | `block-work-repo-git-writes.sh` row claims `PreToolUse (Bash)`; registered NOWHERE in `user/settings.json` (never was, per `git log -S` over full history) | Fix doc: row becomes a NOT-registered row (script exists; overlaps `block-work-repo-git-push.sh`) |
| 2 | hooks | `pr-review-cache-guard.sh` row claims `PreToolUse (Bash)`; actually registered under matcher `Read` | Fix doc: trigger → `PreToolUse (Read)` |
| 3 | hooks | `load-branch-docs-context.sh` registered (`SessionStart`, `startup\|resume\|clear\|compact`) with no table row | Fix doc: add row |
| 4 | coupled-pairs | Manifest pairs `lazy↔lazy-bug`, `lazy-batch↔lazy-bug-batch`, `lazy-status↔lazy-bug-status` (the bug axis) absent from the root Coupled Skill Pairs table | Fix doc: add 3 rows |
| 5 | manifest | `repos/algobooth/` exists; no `Repos` entry. DELIBERATE — commit `47b4fa4` removed the entry when the live repo was deleted; `repos/algobooth/.claude/skills/` stays tracked as the cloud halves of the /lazy coupled pairs | Annotate with the D2 marker in `manifest.psd1` |

Checks with zero findings at baseline: scripts (all documented entries exist), manifest forward
direction (both non-alias entries have dirs; all three aliases resolve).

## Spec assumptions validated / corrected

- Stub's "coupled-pair tables ↔ `lazy-parity-manifest.json`" assumption holds; the manifest is
  the richer side (5 pairs vs. 2 doc rows) — the check direction matters both ways.
- Stub's CI mention (`claude-config-ci`) confirmed out of scope (that feature is a separate
  queue stub); the pytest self-check stands in.
- No `~/.claude` symlinks exist in this environment — the linter takes `--repo-root` and resolves
  everything repo-relative (matches D4).

## Integration points

- `user/scripts/test_doc_drift_lint.py` joins the lane gate suite (pytest).
- No `lazy_core` import, no state-script coupling, no parity-audit exposure (the linter is not a
  coupled pair; `lazy_parity_audit.py` untouched).
- Phase-2 doc edits touch root `CLAUDE.md` + `manifest.psd1` only in the drifted rows/comments
  (tight scope per lane rules).
