---
kind: implemented
feature_id: test-only-production-seams
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [d8e74c3, '3049454', 99d2b00, cb1a959, d99f795]
decisions: []
---

# Implementation Ledger

**What shipped:** The agentic implementation workflow systematically ships speculative production code whose only purpose is to enable test coverage/observability (test-only hooks invoked in production hot paths, settable override properties read only by tests, and reaching for the codebase-forbidden `[InternalsVisibleTo]`), because no authoring guardrail, execute/review gate, constitution rule, or PR-review detector covers this specific class.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
