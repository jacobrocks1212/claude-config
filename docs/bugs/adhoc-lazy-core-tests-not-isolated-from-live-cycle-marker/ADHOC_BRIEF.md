---
kind: adhoc-brief
bug_id: adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: test_lazy_core apply_pseudo tests hit the live cycle marker (no LAZY_STATE_DIR isolation)

Running pytest user/scripts/tests/test_lazy_core/ from inside a live /lazy-batch cycle yields ~82 SystemExit(3) failures: apply_pseudo tests do not isolate LAZY_STATE_DIR so they read the REAL live cycle marker and take the refuse_if_cycle_active path. Reproduces on unmodified main; cleared entirely by pointing LAZY_STATE_DIR at an isolated temp dir. Fix: a conftest/fixture that always sets an isolated LAZY_STATE_DIR for the suite so the battery is runnable mid-run (cycle subagents run gates during live cycles by design).
