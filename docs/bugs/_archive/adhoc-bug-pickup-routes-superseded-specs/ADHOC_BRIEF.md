---
kind: adhoc-brief
bug_id: adhoc-bug-pickup-routes-superseded-specs
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: On-disk bug pickup routes Superseded SPECs into investigation

During the 2026-07-18 run the merged head returned block-terminal-kill-matches-separators-inside-quoted-args (Status: Superseded, successor fix shipped 2026-07-13) and bug-state.py routed it to spec-bug Step 4 - the on-disk open-bug pickup (_find_open_bug_dirs) does not treat Superseded as a closed disposition, so a superseded SPEC re-enters the pipeline as investigable work. Fix shape: exclude Superseded (and Won't-fix, if not already) from the open-bug pickup and from merged ordering; add a regression fixture; consider whether Superseded bug dirs should have a sanctioned archive route like --archive-fixed. 7th/8th facet of the nondispatchable exclude-set class - cross-reference docs/features/merged-head-actionability-oracle as the generalization. Orchestrator mitigation tonight: DEFERRED.md written into the bug dir (operator-defer facet, which IS excluded).
