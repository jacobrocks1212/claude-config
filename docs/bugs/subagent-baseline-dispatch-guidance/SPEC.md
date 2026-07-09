# Subagent Baseline: Unrestricted Dispatch Inherits Full Tool Surface — Investigation Spec

> Subagents dispatched with unrestricted tools ("All tools" / default general-purpose) inherit the entire skill + plugin + MCP surface (~64k first-turn tokens in Cognito), while restricted agent types start as low as ~14k. No guidance steers Cognito orchestration toward restricted types for read-only fan-outs.

**Status:** Fixed
**Fixed:** 2026-07-09 (in-session, outside the bug-pipeline queue — no FIXED.md receipt by design)
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/subagent-baseline-dispatch-guidance
**Related:** docs/bugs/subagent-baseline-skill-surface-bloat, docs/bugs/subagent-baseline-cognito-plugin-scoping (same incident)

---

## Verified Symptoms

1. **[VERIFIED]** Cognito subagent first-turn baselines span 14,152 → 64,540 tokens (n=48, median 36,432), measured from `subagents/agent-*.jsonl` transcripts. The spread correlates with tool surface: restricted agents (e.g. Explore-style, LSP-only) sit at the low end; "All tools" agents at the high end near main-session baseline.
2. **[VERIFIED]** All 13 cognito-pr-review agents declare `Tools: All tools` (agent list inspection), so every review fan-out pays near-full baseline per agent.
3. **[VERIFIED]** Neither `repos/cognito-forms/CLAUDE.local.md` nor the workspace doc carries any guidance on preferring restricted agent types for read-only work.

## Reproduction Steps

1. In a Cognito session, dispatch a read-only search via a default general-purpose agent and via an Explore agent.
2. Compare first-turn `usage` in the two `agent-*.jsonl` transcripts.
3. Observe ~2–4× baseline difference for identical work.

**Expected:** Read-only fan-outs use restricted agent types by default.
**Actual:** Habit + agent definitions default to full surface.
**Consistency:** Always (structural).

## Proven Findings

**Cause (traced):** agent-type definition `tools:` (or its absence) → harness assembles subagent system prompt with the full skill/plugin/MCP surface for unrestricted types → measured per-agent baseline. Fix sites: (a) dispatch-time agent-type choice — steered by repo guidance docs on the always-loaded path (`repos/cognito-forms/CLAUDE.local.md`); (b) `tools:` frontmatter of the cognito-pr-review agent definitions.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cognito root doc | `repos/cognito-forms/CLAUDE.local.md` | Add 3-line dispatch guidance (restricted types for read-only fan-outs) |
| Review-plugin agents | `user/plugins/local-tools/plugins/cognito-pr-review/agents/*.md` | **Deferred:** scoping each agent's `tools:` needs per-agent behavior review (they may legitimately run builds/tests); flagged for the plugin's own tuning cycle |

## Fix Scope

1. Add a short "Subagent dispatch" guidance block to `repos/cognito-forms/CLAUDE.local.md` (lands inside the claude-md-diet trim, net-negative bytes overall).
2. Deferred: audit cognito-pr-review agents for restrictable `tools:` lists.

## Fix Applied

`<subagent-dispatch>` block added to the `<local-constitution>` in `repos/cognito-forms/CLAUDE.local.md`: prefer Explore/narrow-tools agent types for read-only work; reserve unrestricted agents for work that edits files or runs builds. The cognito-pr-review `tools:` audit remains a deferred follow-up.
