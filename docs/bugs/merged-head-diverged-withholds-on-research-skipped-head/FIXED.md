---
kind: fixed
feature_id: merged-head-diverged-withholds-on-research-skipped-head
date: 2026-07-18
provenance: backfilled-unverified
validated_via: harden Round 91 fix commit baf07a6d under full gates (test_dispatch.py 160/160 incl. 2 new regression tests; test_lazy_core.py 1237/1237 isolated; both state-script --test OK); live-run symptom re-verified gone by the orchestrator's next probe; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

merged-head-diverged-withholds-on-research-skipped-head marked Fixed on 2026-07-18 by the
/lazy-batch-parallel orchestrator honoring the harden-harness Round 91 reconciliation
handback (docs/bugs/CLAUDE.md out-of-pipeline contract; the dispatched harden agent is
cycle-blocked from `--archive-fixed`). Receipt written by the orchestrator, not the
pipeline's `__mark_fixed__` gate — provenance is deliberately `backfilled-unverified`.

## Notes

Fix shipped as commit `baf07a6d` (Round 91, hardening-log `560d5eb2`; spec `5d1f950d`):
under `--skip-needs-research`, a research-pending merged head (NEEDS_RESEARCH.md present,
RESEARCH.md absent) fell through BOTH halves of the merged-head exclude set
(`nondispatchable_item_ids` ∪ `probe_skipped_ids`), so `merged_head_override` withheld every
downstream forward route (`route_overridden_by: merged-head-diverged`, null cycle_prompt) and
stalled the run — the 5th facet of the merged-head exclude-set recurring class. Fixed by
`docmodel.spec_dir_research_pending` + a flag-gated `skip_needs_research` kwarg on
`nondispatchable_item_ids` (default False — byte-identical off the flag), wired at the
`lazy-state.py --emit-prompt` merged-head caller. Discovered live in THIS run (cycle-13 stall
after `subagent-wedge-backstop-hook` entered research-skip); the follow-up generalization is
the spun-off feature `merged-head-actionability-oracle`.
