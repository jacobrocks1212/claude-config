---
kind: implemented
feature_id: build-queue-foreground-wait-blocks-past-terminal-outcome
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [87b0579, e643de0, a0b97bf]
decisions: []
---

# Implementation Ledger

**What shipped:** A foreground `/mstest` (`build-queue.ps1`) run emits its terminal "no more work" WARN, yet the Bash call keeps running toward the 10-minute tool timeout instead of returning promptly. The wrapper's exit is gated on full runner-process liveness (through post-WARN hygiene), not on the already-recorded terminal outcome.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: skip-mcp-test. Receipt: FIXED.md (provenance: gated).**
