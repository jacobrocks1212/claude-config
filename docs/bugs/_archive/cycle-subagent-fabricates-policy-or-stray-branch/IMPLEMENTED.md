---
kind: implemented
feature_id: cycle-subagent-fabricates-policy-or-stray-branch
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [2db19c7, 2f444bc, 034a30d, 92c28c3, cee8c0b, bc2fe31, 703fbb7, e4c019e, 9862ee9]
decisions: []
---

# Implementation Ledger

**What shipped:** `/lazy-batch` cycle subagents produced artifacts grounded in nothing they actually read. One subagent hallucinated a "manual-only" commit policy from a `commit-policy.md` that does not exist and skipped a required commit; another committed a halt sentinel (NEEDS_INPUT.md) to a self-invented `audit/...` branch off the work branch instead of on `main`, so the resume path would not have found it. Both required manual orchestrator recovery. Root cause: the **cycle-base prompt template** (`_components/lazy-batch-prompts/cycle-base-prompt.md`) — the script-assembled prompt every cycle subagent receives — pins neither read-before-cite grounding for `commit-policy.md` nor a forbid-branch-creation clause; and there is no mechanical detector for either failure.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
