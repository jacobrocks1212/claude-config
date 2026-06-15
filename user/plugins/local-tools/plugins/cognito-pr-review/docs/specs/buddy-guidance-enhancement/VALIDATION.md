# Validation -- Buddy Guidance Enhancement

Acceptance checklist for the buddy-guidance-enhancement feature. Jacob fills in Result and Notes during a manual buddy walk after shipping.

| Behavior | Trigger | Expected Evidence | Result [ ] pass / [ ] fail | Notes |
|---|---|---|---|---|
| Chunks are behavioral threads, not directory groups | Run buddy on a multi-layer PR | Each Manual Review Guide chunk spans the files of one behavioral objective across layers; no directory-named groups |  |  |
| Tests bundled with their code | Run buddy on a PR with tests | No standalone "tests last" chunk; each chunk lists its tests alongside the implementation they exercise |  |  |
| Hard 400-LOC split holds | Run buddy on a large PR | No chunk's `loc_estimate` exceeds 400; oversized threads are subdivided |  |  |
| Findings withheld until Pass 2 | Walk a chunk in buddy | Tool findings are not shown during the independent read; revealed only at the reconcile step |  |  |
| Teach scales to complexity | Walk a trivial vs. non-trivial chunk | Trivial: one-line orientation only; non-trivial: fuller teach |  |  |
| Severity captured per finding | Disposition a finding | Each non-dismissed finding carries blocking/important/suggestion; review doc sections reflect the severities |  |  |
| Personas + predictive questions emitted | Walk any chunk | Chunk poses a risk-matched persona and boundary-condition/predictive questions, not descriptive recall |  |  |
| No regression in defect surfacing | Re-run buddy on past reviewed PRs | Reviewer surfaces >= the findings caught under the old flow |  |  |

**Behavioral-clustering quality:** ( ) reliable  ( ) needs Tier-2 follow-up
