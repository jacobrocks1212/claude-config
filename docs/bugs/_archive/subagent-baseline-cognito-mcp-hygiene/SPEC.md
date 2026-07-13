# Subagent Baseline: Cognito MCP Surface Hygiene — Investigation Spec

> The GitHub Copilot MCP server loads in every Cognito session despite `enabledMcpjsonServers: ["ado"]`, because `enableAllProjectMcpServers: true` overrides the allowlist. gh CLI already covers GitHub operations per workspace policy.

**Status:** Fixed
**Fixed:** 2026-07-09 (in-session, outside the bug-pipeline queue — no FIXED.md receipt by design)
**Severity:** P2 (low token impact today — schemas defer via ToolSearch at CC 2.1.205 — but wrong-surface hygiene)
**Discovered:** 2026-07-09
**Placement:** docs/bugs/subagent-baseline-cognito-mcp-hygiene
**Related:** docs/bugs/subagent-baseline-cognito-plugin-scoping (same incident: Cognito subagent 50–70k token baseline)

---

## Verified Symptoms

1. **[VERIFIED]** `Cognito Forms/.mcp.json` (tracked by the **work repo's** git, not claude-config) defines two servers: `ado` (`@azure-devops/mcp cognitoforms`) and `github` (HTTP, api.githubcopilot.com) — read directly.
2. **[VERIFIED]** `repos/cognito-forms/.claude/settings.local.json` sets **both** `"enableAllProjectMcpServers": true` **and** `"enabledMcpjsonServers": ["ado"]`. The enable-all flag wins, so `github` connects despite the allowlist naming only `ado`.
3. **[VERIFIED]** Workspace policy (workspace/CLAUDE.md "Remaining sharp edge") already directs GitHub operations through the `gh` CLI; the GitHub MCP is redundant surface in this repo.

## Reproduction Steps

1. Open a session in `~/source/repos/Cognito Forms`.
2. Run `/mcp` (or inspect deferred-tool names in the system reminder).
3. Observe both `ado` and `github` servers connected/listed.

**Expected:** Only `ado` loads (the allowlist's intent).
**Actual:** `github` also loads because `enableAllProjectMcpServers: true` bypasses the allowlist.
**Consistency:** Always (structural).

## Evidence Collected

- File reads quoted above.
- Token impact today is small: recent Cognito transcripts (v2.1.205) show ToolSearch/deferred MCP loading active, so schemas cost names only. The defect is that the allowlist is silently dead config — intent and behavior diverge.
- ADO MCP supports domain filtering (narrower tool name list), but that requires editing the work-repo-tracked `.mcp.json` — a team-visible change.

## Proven Findings

**Cause (traced):** `repos/cognito-forms/.claude/settings.local.json` `enableAllProjectMcpServers: true` → MCP loader enables every `.mcp.json` server regardless of `enabledMcpjsonServers` → `github` server connects in all four worktrees (settings symlinked via manifest). Fix site (the flag itself) is on the path.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cognito local settings | `repos/cognito-forms/.claude/settings.local.json` | Flip `enableAllProjectMcpServers` to `false`; `enabledMcpjsonServers: ["ado"]` becomes authoritative |
| Work repo `.mcp.json` | (not claude-config-owned) | ADO domain filter — deferred, operator/team decision |

## Fix Scope

1. Set `"enableAllProjectMcpServers": false` in `repos/cognito-forms/.claude/settings.local.json` (covers all worktrees via symlink).
2. **Deferred follow-up (operator):** add domain filtering to the ADO MCP args in the work repo's `.mcp.json` (e.g. limit to work-items + repos domains) — team-visible commit, so not applied autonomously.
3. Verification: fresh Cognito session → `/mcp` shows only `ado` (+ global `tree-sitter`).

## Fix Applied

`enableAllProjectMcpServers` flipped `true → false` in `repos/cognito-forms/.claude/settings.local.json`; `enabledMcpjsonServers: ["ado"]` (pre-existing) is now authoritative. The ADO domain-filter follow-up remains open for the operator (work-repo-tracked `.mcp.json`).
