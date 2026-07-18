---
kind: implemented
feature_id: external-owner-contracts-locked-without-consultation
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [7d8160f, 981191a, 2b97f91, aaf0336, 444e838, 4f6fca7]
decisions: []
---

# Implementation Ledger

**What shipped:** `/spec` can lock a decision that creates or changes a contract consumed by another team (events, sync schemas, exported columns) on purely in-repo evidence — the 57077 classic `organization.archived` CognitoEvent was locked this way, then reversed by one OW-team Slack message, deleting Phase 1+6 event work and invalidating an entire sibling Overwatch SPEC authored ~24h earlier.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
