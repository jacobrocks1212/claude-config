---
kind: fixed
feature_id: bug-state-verification-only-remainder-loops-write-plan
date: 2026-07-18
provenance: backfilled-unverified
validated_via: bug-state.py --test (new fixture verification-only-remainder-no-plan, green) + pytest tests/test_lazy_core (1238/1238) + lazy_parity_audit exit 0 + bug-state --fsck ok; NOT pipeline-gated
auto_ticked_rows: 0
fixed_commit: 0258a5b8
---

# Completion Receipt

`bug-state-verification-only-remainder-loops-write-plan` fixed OUT-OF-PIPELINE in commit
`0258a5b8` during harden-harness Round 93 (a dispatched hardening cycle). This receipt was
written by hand, not by the bug pipeline's `__mark_fixed__` gate — provenance is deliberately
`backfilled-unverified`.

## Fix

`bug-state.py::compute_state`'s Step-7 plan-needed predicate now mirrors the feature-side
(lazy-state.py) two-discriminator bypass byte-faithfully: the workstation path bypasses to the
Step-9 validation tail whenever the unchecked remainder is entirely verification-only, WITHOUT
requiring `_has_any_complete_plan`. This closes the infinite write-plan loop that stranded any
bug whose fix landed out-of-pipeline (impl rows `[x]`, no `plans/` dir) with a sole
`<!-- verification-only -->` unchecked row.

## Evidence

- New `bug-state.py --test` fixture `verification-only-remainder-no-plan` routes to
  `Step 9: run MCP tests` (was: infinite `write-plan`). RED without the fix (would route
  write-plan), GREEN with it.
- Byte-pinned baseline `tests/baselines/bug-state-test-baseline.txt` updated with exactly one
  additive PASS line (no other delta).
- Full gates green (see the harden Round 93 log entry,
  `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`).
