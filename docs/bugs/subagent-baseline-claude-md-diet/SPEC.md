# Subagent Baseline: CLAUDE.md Stack Bloat (incl. nested CLAUDE.local.md) — Investigation Spec

> The always-loaded CLAUDE.md stack for Cognito sessions is 33.6KB (~8–9k tokens), carries stale claims (deleted repos listed as active, "hardlinked" skills that are actually one symlinked tree), and ~4KB of git-credential design history. The 11 nested CLAUDE.local.md files (48.7KB, lazy-loaded on directory access) carry similar redundancy. Scope expanded per operator to lean out ALL nested CLAUDE.local.md files.

**Status:** Fixed
**Fixed:** 2026-07-09 (in-session, outside the bug-pipeline queue — no FIXED.md receipt by design)
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/subagent-baseline-claude-md-diet
**Related:** docs/bugs/subagent-baseline-skill-surface-bloat (same incident: Cognito subagent 50–70k token baseline)

---

## Verified Symptoms

1. **[VERIFIED]** Always-loaded stack in a Cognito session = 33.6KB: `user/CLAUDE.md` 5,156B + `workspace/CLAUDE.md` 11,361B + `repos/cognito-forms/CLAUDE.local.md` 16,123B + team-owned `.claude/CLAUDE.md` 660B (byte-measured). ≈8–9k tokens of the 63–74k measured baseline, loaded into every main session and subagent.
2. **[VERIFIED]** `workspace/CLAUDE.md` is stale: "Key Repositories" lists `maestro`, `algobooth`, `work-dashboard`, `zen-mcp-server`, `scene-remixer`, `housing-locator`, `semantic-docs` as local repos — none exist under `~/source/repos` (verified by `ls`); the "Skill File Relationship" section claims skills are *hardlinked* between `~/.claude/skills` and `~/.claude-personal/skills`, but both are directory **symlinks** to `claude-config/user/skills` (verified `os.path.islink` = True for both).
3. **[VERIFIED]** `workspace/CLAUDE.md` carries ~4KB of git-credential mechanism narrative (history of the old bash helper, seeding recipes) that is reference material, not per-session guidance.
4. **[VERIFIED]** 11 nested `CLAUDE.local.md` files under `repos/cognito-forms/` total 48,724B (spa 9,204B, Cognito.Services 7,744B, Cognito.Core 6,358B, Cognito.UnitTests 4,866B, Cognito.QueueJob 3,702B, Cognito 3,533B, Cognito.Web.Client 3,338B, libs/model.js 3,083B, libs/types 2,643B, apps/client 2,243B, libs/vuemodel 2,010B). These load lazily on directory access — they cost mid-session context, not baseline — and the operator confirmed they need the same leaning-out.

## Reproduction Steps

1. Open a session in `~/source/repos/Cognito Forms`; the claudeMd system-reminder contains user + workspace + repo CLAUDE files (~33.6KB).
2. Read/edit any file under e.g. `Cognito.Core/` — its `CLAUDE.local.md` (6.4KB) is additionally injected.
3. Compare injected content against reality: several listed repos do not exist; the hardlink claim is false.

**Expected:** Stack carries only current, load-bearing constraints; reference narrative lives in on-demand docs.
**Actual:** ~33.6KB always-on + 48.7KB lazy, with stale claims and narrative history.
**Consistency:** Always (structural).

## Evidence Collected

- Byte measurements above (`wc -c`).
- All 12 Cognito CLAUDE.local.md files are claude-config-owned and symlinked into every worktree via manifest.psd1 `RootFiles` — one edit propagates to main + B/C/D.
- `user/CLAUDE.md` (5.2KB) is dense and current — excluded from trimming (its auto-invoke list references `nx-monorepo` in the personal copy vs `nx-workspace-patterns` in the tracked copy; personal copy is a separate untracked file, out of scope).
- Team-owned `.claude/CLAUDE.md` (660B) is not claude-config-owned — out of scope.

## Proven Findings

**Cause (traced):** `workspace/CLAUDE.md` + `repos/cognito-forms/*CLAUDE.local.md` (claude-config sources) → manifest.psd1 symlinks → harness claudeMd injection at session start (root files) / directory access (nested files) → measured baseline and mid-session cost. Fix site (the markdown content itself) is the path's source node.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Workspace doc | `workspace/CLAUDE.md` | Trim stale repos, false hardlink claim, credential narrative → `docs/git-identity.md` |
| Cognito root doc | `repos/cognito-forms/CLAUDE.local.md` | Trim ~40% (always-loaded) |
| Nested docs | 11 × `repos/cognito-forms/**/CLAUDE.local.md` | Trim redundancy/stale content (lazy-loaded) |
| New reference doc | `docs/git-identity.md` (claude-config) | Receives relocated credential mechanism narrative |

## Fix Scope

1. `workspace/CLAUDE.md`: rewrite Key Repositories to reality; correct skills-relationship claim (one symlinked tree); compress git-identity section to the operative table + pinning rule + a pointer; move mechanism history/seeding recipes to `claude-config/docs/git-identity.md`.
2. `repos/cognito-forms/CLAUDE.local.md`: lean out (always-loaded, biggest single file).
3. All 11 nested CLAUDE.local.md: remove content derivable from code, duplicated-across-files sections, and verbose narrative; keep build commands, contracts, gotchas. One writer per file.
4. Preserve every load-bearing constraint — trims are redundancy/staleness removal, not information loss.

## Fix Applied

**Always-loaded stack: 33,623 → 24,092 bytes (−28%, ~2.4k tokens per session/subagent):**

- `workspace/CLAUDE.md` 11,361 → 6,926B (−39%): stale repo list corrected (deleted personal repos removed; AlgoBooth marked cloud-only; cog-docs added), false "hardlinked skills" claim replaced with the symlink reality, credential mechanism/seeding/history relocated to new `docs/git-identity.md` (2,984B, on-demand).
- `repos/cognito-forms/CLAUDE.local.md` 16,123 → 11,350B (−30%): the four duplicate build/test "Verification" sections consolidated into one section per op; work-logging parameter tables + example compressed to essentials (schema lives on the MCP tool); C# syntax rules and frontend-workflow compacted; Backend Gotchas + branch-docs protocol kept intact. Also gained the `<subagent-dispatch>` block (sibling bug subagent-baseline-dispatch-guidance).

**Nested CLAUDE.local.md files (lazy-loaded): 48,724 → 30,705 bytes (−37%),** trimmed by four parallel single-writer agents; every warning/never/must constraint reported preserved (spa's 12 gotchas, DLL-lock rules, snapshot-authority rule, typegen safety warnings, model.js/vuemodel reactivity semantics). Per-file: spa 9,204→6,407; Services 7,744→4,632; Core 6,358→4,385; UnitTests 4,866→3,103; QueueJob 3,702→2,004; Cognito 3,533→2,455; Web.Client 3,338→1,762; model.js 3,083→1,997; types 2,643→1,381; client 2,243→1,371; vuemodel 2,010→1,208.

`doc-drift-lint.py` clean after all edits (0 findings).
