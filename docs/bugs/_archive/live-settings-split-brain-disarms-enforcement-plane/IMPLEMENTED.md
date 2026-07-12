---
kind: implemented
feature_id: live-settings-split-brain-disarms-enforcement-plane
date: 2026-07-12
provenance: pipeline-gated
derivation: commit-brackets
commits: [f0c33cb, fa244ed, 0f44611, 1b23a9b, 271dbf7, 30ebf73, 308fa60, 01ae5e4, a43808e,
  3404c9e, 4edd224, 004336f, 2132b3b, 6c03084, 719c98a, 6770f44, 0628422, 6012c72,
  8df3f35, 9948a55]
decisions: []
---

# Implementation Ledger

**What shipped:** The live `~/.claude/settings.json` on this laptop is an untracked plain file registering ONLY the two turn-routing hooks, while the tracked `user/settings.json` registers the ~10 OTHER enforcement hooks and has NEVER carried the dispatch guard. Each half of the enforcement plane is dead wherever the other file rules: on this laptop none of the containment/sentinel/build/ push/kill guards have been registered since Jun 11; on any symlink-intact machine (and the cloud bootstrap) the verbatim-dispatch guard is unwired. No automatic check detects either half.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
