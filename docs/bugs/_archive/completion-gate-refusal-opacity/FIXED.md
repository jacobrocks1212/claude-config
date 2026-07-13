---
kind: fixed
feature_id: completion-gate-refusal-opacity
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py — NOT MCP-gated, no app runtime in this repo)
auto_ticked_rows: 0
---

# Completion Receipt

completion-gate-refusal-opacity marked fixed on 2026-07-12 by an operator-directed interactive
subagent session (STATE-lane bug-fix pass covering five queued bugs). This receipt was written by
the session directly, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`.

## Notes

Implemented per Fix Scope in full: `verify_ledger` (`user/scripts/lazy_core.py`) now returns a
`failing_detail` object naming the offending items for every False check (dirty files, head/upstream
shas + ahead/behind counts, incomplete plan files/statuses, unchecked deliverable rows with line
numbers) instead of a bare boolean; the `__mark_complete__` coherence-gate advisory now prints the
`genuine` row excerpts (with line numbers) alongside the pre-existing `shim` excerpts; both
`lazy-state.py` and `bug-state.py`'s `gate-refusal` telemetry events gain a compact `detail_head`
summary. Coupled-pair mirroring verified (bug-state.py shares `lazy_core.verify_ledger` and forwards
the enriched payload with no separate code change needed). 17 new/verified pytest fixtures added to
`test_lazy_core.py`, all registered in the `_TESTS` manual registry (the dead-coverage guard stays
green). Gate: `python -m pytest user/scripts/test_lazy_core.py -k "verify_ledger_failing_detail or
summarize_failing_detail or classify_blocking_unchecked_rows or coherence_advisory_prints_genuine or
no_orphaned_test_functions" -q` → 17 passed.

**Deferred (out of the STATE lane, explicitly):** the SKILL-prose half of Fix Scope §4 ("the refusal
is now self-diagnosing — a second discovery probe is a deviation") touches `user/skills/**`, which
this session's assignment explicitly excludes. The mechanical fix (the enriched payload itself) is
fully live regardless of the prose update.
