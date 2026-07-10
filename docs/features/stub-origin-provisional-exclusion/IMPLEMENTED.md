---
kind: implemented
feature_id: stub-origin-provisional-exclusion
date: 2026-07-09
provenance: pipeline-gated
derivation: message-grep
commits: [bba6fca]
decisions: []
---

# Implementation Ledger

**What shipped:** Special-case stub-origin decisions in the provisional-acceptance tier: a `NEEDS_INPUT.md` whose decisions shaped a BASELINE the operator has never seen (a park-mode stub-spec `/spec` Phase-1 round, or a `/spec-bug` pre-conclusion halt) is marked `stub_origin: true` by its producer and is NEVER provisionally accepted — baseline-gating forks always park for the operator, no matter how low their per-decision divergence grades look.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
