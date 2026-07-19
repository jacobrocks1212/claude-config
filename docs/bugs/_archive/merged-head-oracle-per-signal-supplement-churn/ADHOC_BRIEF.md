---
kind: adhoc-brief
bug_id: merged-head-oracle-per-signal-supplement-churn
enqueued_by: lazy-adhoc
date: 2026-07-19
---

# Ad-hoc bug: Merged-head oracle: model operator-defer in feature compute_state to retire per-signal file-predicate supplements

The merged-head actionability oracle's scoped is_dispatchable re-inference has needed repeated per-signal file-predicate supplements (harden rounds R56/R57/R101/R102) because the FEATURE compute_state has no operator-defer branch, so the oracle is structurally blind to operator-deferred features and each recurrence re-adds a file-predicate patch. Durable generalization handed back by R102: model operator-defer (DEFERRED.md operator-excluded) directly in the feature compute_state so the oracle's is_dispatchable premise holds universally and the per-signal file-predicate supplement can retire. This also fixes the near-neighbor where the feature pipeline would dispatch /spec on an operator-EXCLUDED feature. Provenance: spun off from docs/bugs/_archive/merged-head-oracle-blind-to-operator-deferred-cross-pipeline-feature (fix a1f98e4d).
