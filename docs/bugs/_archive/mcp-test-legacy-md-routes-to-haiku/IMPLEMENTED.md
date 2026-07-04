---
kind: implemented
feature_id: mcp-test-legacy-md-routes-to-haiku
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [46aa133, 411a49e, 20fe661, 2ec4a35, a790499, 19096d7]
decisions: []
---

# Implementation Ledger

**What shipped:** The autonomous `/lazy-batch` (and `-cloud` / `-bug-batch`) orchestrator fixes the mcp-test cycle model to **haiku** at dispatch time — before the subagent resolves which scenario it will run — so a scenario that exists only as a legacy `.md` (no converted `corpus/live/*.yaml` counterpart) lands on haiku, which cannot author the `.md`→v1-YAML conversion and writes `BLOCKED.md`. The `route_mcp_test_tier()` signal that *would* escalate such a scenario to Sonnet exists but is consulted only by the interactive `mcp-test` skill prose, never by the state script's cycle-model emit.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
