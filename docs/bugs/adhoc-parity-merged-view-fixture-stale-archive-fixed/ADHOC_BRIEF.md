---
kind: adhoc-brief
bug_id: adhoc-parity-merged-view-fixture-stale-archive-fixed
enqueued_by: lazy-adhoc
date: 2026-06-19
---

# Ad-hoc bug: Stale merged-view parity fixtures missing --archive-fixed predicate

The merged-view dispatch parity audit unit tests test_passes_when_both_drivers_consistent and test_fires_when_no_regression_guard_absent in user/scripts/test_lazy_parity.py use stale hermetic 'full' SKILL.md fixture text that omits the '--archive-fixed' predicate now required by _MERGED_VIEW_PREDICATES in lazy_parity_audit.py. test_passes_when_both_drivers_consistent therefore fails (the 'consistent' fixture yields a finding for the missing --archive-fixed pattern), turning 'pytest user/scripts/ -q' red (1 failed, 882 passed). The real lazy-batch/lazy-batch-cloud SKILLs DO carry --archive-fixed so the real-repo lazy_parity_audit.py audit is clean; only the hermetic fixtures are stale. Fix: add an '--archive-fixed' bug-archive clause to the 'full' fixture SKILL.md text in BOTH tests so they satisfy all 6 _MERGED_VIEW_PREDICATES; confirm 'pytest user/scripts/ -q' is fully green. This red test was masked behind a '| tail' pipe and blocks the completion-coherence-gate-reconciliation feature's full-suite verification row (its origin).
