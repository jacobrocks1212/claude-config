---
kind: adhoc-brief
feature_id: merged-head-actionability-oracle
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc task: Merged-head actionability oracle (replace 5-facet exclude-set enumeration)

Round 91 spin-off (5th facet of the merged-head exclude-set recurring class; see docs/bugs/_archive/merged-head-diverged-withholds-on-research-skipped-head and the depdag docstring's named actionability generalization). Replace the category-enumerated merged-head exclude set (parked, operator-deferred, device-deferred, dep-unready, research-skipped) with a single per-item actionability oracle: would compute_state dispatch this item right now? The merged-head-diverged withhold should consult that oracle instead of an ever-growing facet list, so the NEXT nondispatchable category cannot re-introduce a stall. Route through /spec; keep byte-identical behavior for dispatchable heads.
