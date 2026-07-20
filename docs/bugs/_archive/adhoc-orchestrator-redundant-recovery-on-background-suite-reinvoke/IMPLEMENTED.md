---
kind: implemented
feature_id: adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: ['3451039', f56959d, 7dbcaf9, aef06e3, 08bcfbd, 8dded98, '1118807', 18bd635, 641cd85,
  43d4ac9, fbd4433]
decisions: []
---

# Implementation Ledger

**What shipped:** A cycle /execute-plan subagent backgrounds its long verification suite and returns "holding, will re-invoke" instead of foreground-awaiting; the orchestrator, unable to distinguish that pause from a resultless return, dispatches a redundant recovery cycle that collides (one-writer) with the harness-re-invoked agent.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
