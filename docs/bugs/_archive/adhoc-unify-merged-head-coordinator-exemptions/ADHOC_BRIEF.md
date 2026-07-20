---
kind: adhoc-brief
bug_id: adhoc-unify-merged-head-coordinator-exemptions
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: Unify merged-head coordinator-emission exemptions

The emit-prompt merged-head guard now carries two coordinator-emission exemptions (lane parent_run round-85; serial-tail live-lease round-94). Generalize to one _is_coordinator_arbitrated_emission predicate before a third near-neighbor (demoted-serial-rerun) needs its own carve-out. Spun off by harden round 94.
