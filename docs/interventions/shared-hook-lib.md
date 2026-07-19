---
kind: intervention
intervention_id: shared-hook-lib
pipeline: feature
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 1d33c956daa8e23f209e78115268a00b99556400
commit_set: 1d33c956daa8e23f209e78115268a00b99556400
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T16:50:52Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-18'
  window_runs: 10
  surfaces:
  - user/hooks/block-noncanonical-blocker-write.sh
  - user/hooks/block-sentinel-write-on-stray-branch.sh
  - user/hooks/build-queue-enforce.sh
  - user/hooks/hook-prelude.sh
  - user/hooks/lazy-cycle-containment.sh
  - user/hooks/lazy-dispatch-guard.sh
  - user/hooks/lazy-route-inject.sh
  - user/hooks/long-build-ownership-guard.sh
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/depdag.py
  - user/scripts/lazy_core/docmodel.py
  commit_set:
  - 5d1f950
  - baf07a6
  - 560d5eb
  - d2db402
  - '9069465'
  - 70caf70
  - 9f715c3
  - e4fd093
  - 962c06a
  - f7a7a9e
  - 33cafa0
  - f1095e0
  - e5d9dba
  - b4308f0
  - 6ec23c1
  - 6c2e970
  - ca8ca8b
  - f157bca
  - 3d69974
  - b88fc5a
  - cb940ef
  - e04753f
  - e66c02f
  - beae3aa
  - 2be204c
  - 716dfd3
  - b82bf97
  - a78845f
  - 5e0f4d7
  - 5dee2ed
  - ed37a2d
  - 79070c7
  - b8b2259
  - 0b6051e
  - f4cf28f
  - 0c56616
  - becaea6
  - f7f9493
  - 65f709e
  - 64bf865
  - f08f83b
  - 0dc1da2
  - c800431
  - ff83d28
  - 247b897
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: shared-hook-lib

Hypothesis: shipping `shared-hook-lib` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
