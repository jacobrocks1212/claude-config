---
kind: implemented
feature_id: merged-head-oracle-per-signal-supplement-churn
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [0f6f801, 1904e35, 1fe889e, e2e2773, 461d42d, 7f8b39a]
decisions: []
---

# Implementation Ledger

**What shipped:** The merged-head actionability oracle re-adds a per-signal `DEFERRED.md` file-predicate every recurrence (R56/R57/R101/R102) because the FEATURE `compute_state` has no operator-defer branch, so the oracle's `is_dispatchable` re-inference is structurally blind to operator-deferred features. Model operator-defer directly in the feature `compute_state` so the premise holds universally and the supplement retires.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
