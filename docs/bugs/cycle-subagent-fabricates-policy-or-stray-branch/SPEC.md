# Cycle subagents fabricate ungrounded artifacts — a non-existent commit policy, a stray git branch — Investigation Spec (stub)

> `/lazy-batch` cycle subagents produced artifacts grounded in nothing they actually read. One subagent hallucinated a "manual-only" commit policy from a `commit-policy.md` that does not exist and skipped a required commit; another committed a halt sentinel (NEEDS_INPUT.md) to a self-invented `audit/...` branch off the work branch instead of on `main`, so the resume path would not have found it. Both required manual orchestrator recovery. The cycle-subagent prompts do not pin read-before-cite grounding or the work branch.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/cycle-subagent-fabricates-policy-or-stray-branch
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` cycle-subagent prompt; `.claude/skill-config/commit-policy.md` grounding; HARD CONSTRAINT 9 (no fabricated features)

---

## Verified Symptoms
1. **[OBSERVED in logs]** A subagent hallucinated a non-existent "manual-only" commit policy and skipped a required commit — session `28de16b3` @ `2026-06-08T23:21:25.750Z`: "The commit-policy.md **does not exist** — the sidecar-watchdog subagent hallucinated a 'manual-only' policy and wrongly skipped its commit." Run-end note @ `01:08:29`: "one mcp-test subagent hallucinated a non-existent 'manual-only commit policy' and skipped.".
2. **[OBSERVED in logs]** A subagent committed a halt sentinel to a self-invented stray branch off the work branch — session `8ae22371` @ `~2026-06-10 00:13`: "The audit subagent deviated — it created a stray `audit/...` branch and committed NEEDS_INPUT.md there instead of on the work branch (main)"; recovery: "main now carries NEEDS_INPUT.md (6d6b4f6c); stray branch deleted local+remote.".

## Evidence Collected (from session logs)
- session `28de16b3` @ `2026-06-08T23:21:25.750Z`: "The commit-policy.md **does not exist** — the sidecar-watchdog subagent hallucinated a 'manual-only' policy and wrongly skipped its commit." — the subagent cited a config file it never read and used the fabricated policy to skip a required commit, leaving work uncommitted.
- session `28de16b3` run-end @ `01:08:29`: "one mcp-test subagent hallucinated a non-existent 'manual-only commit policy' and skipped." — confirms the same fabrication at run-end summary level.
- session `8ae22371` @ `~2026-06-10 00:13`: "The audit subagent deviated — it created a stray `audit/...` branch and committed NEEDS_INPUT.md there instead of on the work branch (main)" + recovery "main now carries NEEDS_INPUT.md (6d6b4f6c); stray branch deleted local+remote." — the halt sentinel landed on a self-invented branch where the resume path would not find it, requiring manual recovery.

## Why this is friction
Cycle subagents invented grounding they never verified — a config policy that does not exist (causing a required commit to be skipped) and a git branch off the work branch (stranding a halt sentinel the resume path could not see). Both defects required manual orchestrator recovery, and both point at cycle-subagent prompts that fail to pin read-before-cite grounding or the work branch.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Should the cycle-subagent prompt require read-before-cite grounding (a file must be read and quoted before any policy is asserted from it)?
- Should the cycle-subagent prompt pin the work branch and forbid creating/committing to any other branch?
- How should a fabricated-policy skip or a stray-branch sentinel be detected mechanically rather than caught by the orchestrator after the fact?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
