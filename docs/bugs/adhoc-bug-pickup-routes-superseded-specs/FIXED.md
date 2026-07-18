---
kind: fixed
feature_id: adhoc-bug-pickup-routes-superseded-specs
date: 2026-07-18
provenance: backfilled-unverified
validated_via: bug-state.py --test (in-file smoke harness — new `superseded-dir-excluded-from-pickup` fixture green; full lazy_core pytest package green; live probe of the in-flight bug now routes plan-bug with route_overridden_by null); NOT pipeline-gated (fixed OUT-OF-PIPELINE via a harden commit)
auto_ticked_rows: 0
---

# Completion Receipt

`adhoc-bug-pickup-routes-superseded-specs` fixed OUT-OF-PIPELINE by `/harden-harness`
Round 97 (2026-07-18). Fix commit: `04ecf963`
(`harden(script): exclude Superseded bug dirs from _find_open_bug_dirs pickup`).
This receipt was written by the dispatched harden subagent, not the bug pipeline's
`__mark_fixed__` gate — provenance is `backfilled-unverified`.

## Notes

`bug-state.py::_find_open_bug_dirs` filtered only `Won't-fix` and receipted `Fixed`, so a
resolved-but-unarchived `**Status:** Superseded` bug dir was auto-discovered as open work,
entered `merged_worklist`, became the merged head, and triggered a universal
`merged-head-diverged` withhold that wedged the run. Restored parity with the feature-side
loader `_find_open_feature_dirs` (which already skips `Superseded`, receipt-exempt): added
`BUG_STATUS_SUPERSEDED` and an unconditional skip branch beside the `Won't-fix` branch, so a
`Superseded` dir never enters the work list or merged view. Regression fixture in the
`--test` smoke harness; bug-state smoke baseline regenerated via `_normalize_smoke_output`.

## Verification

`bug-state.py --bug-id containment-hook-inline-python-exceeds-windows-cmdline-limit --emit-prompt --probe`
now returns `route_overridden_by: null`, `merged_head: null`, `sub_skill: plan-bug` (real
`cycle_prompt` present) — was universally withholding on the Superseded merged head.
`lazy-state.py --next-merged` returns the actionable in-flight bug, not the Superseded one.
New smoke fixture `superseded-dir-excluded-from-pickup` PASS; full lazy_core pytest package
green; `lazy-state.py --test` / `bug-state.py --test` green; `bug-state.py --fsck` clean.
