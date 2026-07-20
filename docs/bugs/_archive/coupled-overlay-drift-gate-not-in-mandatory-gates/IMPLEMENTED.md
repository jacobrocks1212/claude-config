---
kind: implemented
feature_id: coupled-overlay-drift-gate-not-in-mandatory-gates
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [a8224f6, 9c214f3, 67ff89f]
decisions: []
---

# Implementation Ledger

**What shipped:** The overlay-drift gate exists but is not wired into the mandatory authoring/commit-time gate battery, so per-pair overlays silently drifted from their committed hand-authored SKILL.md across three commits before being caught reactively mid-run.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
