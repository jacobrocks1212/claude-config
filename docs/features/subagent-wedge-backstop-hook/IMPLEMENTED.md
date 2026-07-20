---
kind: implemented
feature_id: subagent-wedge-backstop-hook
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [464c924, d6e9465, 127d102, 72df8fe, 5f15d5a]
decisions: []
---

# Implementation Ledger

**What shipped:** A `SubagentStop` hook that mechanically catches a GENUINELY-WEDGED dispatched subagent — one that tries to stop/return with pending plan work still incomplete — and blocks its premature stop once, forcing it to commit + complete (or write `BLOCKED.md`) instead of returning dead and stranding the pipeline. The mechanical complement to the SENDER-side `turn-end-gate.md` prose (which a wedged/erroring agent cannot self-enforce).

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
