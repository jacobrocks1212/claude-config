# Subagent Baseline: Global Plugin Surface in Cognito — Investigation Spec

> Plugins enabled at user scope (Notion, warp, context7-plugin, pr-review-toolkit) inject their skills, commands, and agent descriptions into every Cognito Forms session and subagent, where they are unused or redundant.

**Status:** Fixed
**Fixed:** 2026-07-09 (in-session, outside the bug-pipeline queue — no FIXED.md receipt by design)
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/subagent-baseline-cognito-plugin-scoping
**Related:** docs/bugs/subagent-baseline-skill-surface-bloat (same incident: Cognito subagent 50–70k token baseline)

---

## Verified Symptoms

1. **[VERIFIED]** `user/settings.json` `enabledPlugins` enables `notion@claude-plugins-official`, `warp@claude-code-warp`, `context7-plugin@context7-marketplace`, and `pr-review-toolkit@claude-plugins-official` globally — read directly from the tracked settings file.
2. **[VERIFIED]** pr-review-toolkit contributes 6 agents with 6,651 bytes of frontmatter (descriptions carry full multi-`<example>` blocks) to the agent list of every session; Notion contributes ~12 skills/commands; all appear in Cognito sessions' system prompts (observed in this session's own skill/agent lists, same config).
3. **[VERIFIED]** Cognito Forms has its own dedicated review plugin (`cognito-pr-review@local-tools`, 13 agents) — pr-review-toolkit is redundant there.

## Reproduction Steps

1. Open a session in `~/source/repos/Cognito Forms`.
2. Run `/context` and inspect the tools/skills breakdown (or read the available-skills + agents sections of any transcript's system prompt).
3. Observe Notion skills (`Notion:create-page`, …), warp, context7, and pr-review-toolkit agents (`pr-review-toolkit:code-reviewer`, …) present.

**Expected:** Cognito sessions carry only the plugins used for Cognito work (cognito-pr-review, work-logging-plugin, csharp-lsp, typescript-lsp).
**Actual:** All user-enabled plugins inject their full surface.
**Consistency:** Always (structural).

## Evidence Collected

- `user/settings.json` `enabledPlugins` map (tracked, symlinked to `~/.claude/settings.json`).
- Plugin cache inventory: pr-review-toolkit 6 agents / 6,651B frontmatter; cognito-pr-review 13 agents / 2,873B; Notion plugin skills visible in session skill list.
- `repos/cognito-forms/.claude/settings.json` currently contains only `hooks` — no `enabledPlugins` key. Project-scope settings take precedence over user scope for `enabledPlugins`, so a per-repo `false` override is the supported mechanism.
- The file is symlinked into all four worktrees (manifest.psd1 `cognito-forms` + `-B/-C/-D` aliases), so one edit covers Cognito Forms, -B, -C, -D.

## Proven Findings

**Cause (traced):** `user/settings.json` → `enabledPlugins` (manifest.psd1:14 symlink to `~/.claude/settings.json`) → plugin skills/commands/agents injected into system prompt of every session and subagent in every repo → measured baseline. Fix site — a project-scope `enabledPlugins` override in `repos/cognito-forms/.claude/settings.json` — is on this path (it is the documented precedence point for the same key).

**Kept enabled in Cognito (deliberate):** `work-logging-plugin@local-tools` (the cognito skills' `work-log.md` component and interview-prep logging depend on its MCP tools), `cognito-pr-review@local-tools`, `csharp-lsp`, `typescript-lsp`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cognito project settings | `repos/cognito-forms/.claude/settings.json` | Add `enabledPlugins` block disabling notion, warp, context7-plugin, pr-review-toolkit |

## Fix Scope

1. Add to `repos/cognito-forms/.claude/settings.json`:
   `"enabledPlugins": { "notion@claude-plugins-official": false, "warp@claude-code-warp": false, "context7-plugin@context7-marketplace": false, "pr-review-toolkit@claude-plugins-official": false }`
2. Verification: open a Cognito session, run `/context`, confirm the Notion/warp/context7/pr-review-toolkit surfaces are gone and baseline dropped ~4–6k tokens. (Manual — needs a fresh Cognito session.)

## Fix Applied

`repos/cognito-forms/.claude/settings.json` now carries the `enabledPlugins` block above (top of file, before `hooks`). Covers Cognito Forms + -B/-C/-D via the manifest symlinks. **Residual verification for operator:** fresh Cognito session → `/context` — if the four surfaces still appear, project-scope `enabledPlugins: false` overrides need to move to `.claude/settings.local.json` instead.
