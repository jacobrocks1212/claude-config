---
kind: fixed
feature_id: adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker
date: 2026-07-18
provenance: backfilled-unverified
validated_via: pytest (full user/scripts/tests/test_lazy_core/ package — 1254 passed under a LIVE cycle marker, the exact condition that produced the 80 SystemExit(3) failures); NOT pipeline-gated (fixed OUT-OF-PIPELINE via a harden commit)
auto_ticked_rows: 0
---

# Completion Receipt

`adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker` fixed OUT-OF-PIPELINE by
`/harden-harness` Round 95 (2026-07-18). Fix commit: `1684f20b`
(`harden(test): isolate LAZY_STATE_DIR at the test_lazy_core import chokepoint`).
This receipt was written by the dispatched harden subagent, not the bug pipeline's
`__mark_fixed__` gate — provenance is `backfilled-unverified`.

## Notes

`tests/test_lazy_core/_util.py` now seeds an isolated per-process temp `LAZY_STATE_DIR`
via `os.environ.setdefault(...)` at the shared import chokepoint (imported by every shard
in both pytest and the standalone runners), BEFORE `_ORIGINAL_LAZY_STATE_DIR` is captured
so the `_clear_state_dir` restore path stays isolated too. `setdefault` preserves the
documented operator override. Structural single-chokepoint fix, not 80 per-test edits.

## Verification

Under a live `/lazy-batch` cycle marker (the exact failing condition): the two previously
red suites went `274 passed` (was `80 failed, 194 passed`), and the full lazy_core pytest
package went `1254 passed`. `lazy-state.py --test` / `bug-state.py --test` remain green.
