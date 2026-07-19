---
kind: implemented
feature_id: decision-11-dispatch-time-forward-advance
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [2d68e34, bbb5803, f205c2d]
decisions: []
---

# Implementation Ledger

**What shipped:** Implement turn-routing-enforcement NEEDS_INPUT decision 11: `forward_cycles` must advance at the real dispatch bracket, never on the every-turn inject-hook `--repeat-count` probe. The core mechanism already landed (commit `e91bd305`); the residual is retargeting two pinned tests that still assert the retired probe-path advance, retiring the now-dead `consume_gate` trigger, and reconciling stale docs.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
