---
kind: implemented
feature_id: pr-review-rereview-low-fidelity-metadata
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [add1ddb, 16f6d7b, 285237a, 133d143, 50f6415]
decisions: []
---

# Implementation Ledger

**What shipped:** On re-reviews, `/cognito-pr-review:review-pr` produces an iteration-diff that omits genuinely-changed files (and includes unrelated merge churn) and lifespan counters that are numerically absurd — both forcing downstream agents/humans to distrust and manually compensate for the re-review metadata.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
