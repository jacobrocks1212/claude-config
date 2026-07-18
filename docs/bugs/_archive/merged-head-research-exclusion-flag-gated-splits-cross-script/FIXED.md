---
kind: fixed
feature_id: merged-head-research-exclusion-flag-gated-splits-cross-script
date: 2026-07-18
provenance: backfilled-unverified
validated_via: harden Round 92 fix commit 981191ae under full gates (test_dispatch.py 161/161 incl. 1 new cross-script regression fixture; test_lazy_core.py 1238/1238 isolated LAZY_STATE_DIR; lazy-state.py/bug-state.py --test OK; lazy_parity_audit exit 0; bug-state --fsck ok); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

merged-head-research-exclusion-flag-gated-splits-cross-script marked Fixed on 2026-07-18 by the
harden-harness Round 92 inline reconciliation (docs/bugs/CLAUDE.md out-of-pipeline contract).
Receipt written by the harden agent (not the pipeline's `__mark_fixed__` gate) — provenance is
deliberately `backfilled-unverified`. The orchestrator-only reconciliation ops
(`--archive-fixed` / `--link-provenance`) ran directly (not cycle-refused in this harden context).

## Notes

Fix shipped as commit `981191ae` (Round 92, hardening-log; spec `7d8160f8`). This is the 6th
facet of the merged-head exclude-set class and the follow-up incompleteness of Round 91
(`baf07a6d`): Round 91 added the research-pending exclusion but flag-gated it on
`--skip-needs-research`, wiring it ONLY at the `lazy-state.py` merged-head caller. `bug-state.py`'s
merged-head-override reads the feature queue too but has no such flag and cannot fold a feature head
into its bug-scoped `probe_skipped_ids`, so the file predicate was its only reachable exclusion —
and the flag-gate made it inert there. The two scripts computed DIFFERENT merged heads for the same
on-disk state (a research-skipped feature head + a Concluded on-disk bug): feature side excluded the
research head → bug at head; bug side did not → research feature at head. Each withheld its own emit
(`route_overridden_by: merged-head-diverged`), neither dispatched: cross-script split-brain deadlock.

Fixed by dropping the `skip_needs_research and` gate in `lazy_core/depdag.py::nondispatchable_item_ids`
so `docmodel.spec_dir_research_pending` is an UNCONDITIONAL member — the on-disk sentinel is the
SSOT research-defer decision, so both coupled scripts now compute the same exclude set → the same
merged head → the bug route emits. Byte-identical for `lazy-state.py` forward routing. Regression:
`test_research_pending_exclusion_consistent_across_state_scripts` asserts both callers' exclude sets
are equal and land the bug at the merged head. The structural generalization (a single per-item
actionability oracle) remains the spun-off `merged-head-actionability-oracle` item (Round 91 handback).
