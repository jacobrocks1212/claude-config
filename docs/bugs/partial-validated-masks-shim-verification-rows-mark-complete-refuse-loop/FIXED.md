---
kind: fixed
feature_id: partial-validated-masks-shim-verification-rows-mark-complete-refuse-loop
date: 2026-07-21
provenance: backfilled-unverified
validated_via: tests/test_lazy_core/ 1354/1354 + test_hooks.py 288/288 + both state scripts' --test smoke harnesses + bug-state.py --fsck clean; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

partial-validated-masks-shim-verification-rows-mark-complete-refuse-loop marked Fixed on 2026-07-21
by a `/harden-harness` round (Round 137,
`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`). This receipt was written by the
harden agent, not the bug pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`.

## Notes

Fix commit `000c441f` (bug spec `3af27ddc` committed first). `_collect_uncovered_verification_rows`
is now shim-aware and `uncovered_verification_rows_remain` credits only canonical (autotickable)
rows against `pass_count`, so an un-canonically-marked verification row now re-routes to mcp-test
(the missing forward route) instead of routing a doomed `__mark_complete__` into a stuck loop. 3
regression tests added to `test_gates.py`. Green gate battery cited above.

The RESIDUAL canonical-row partial-coverage masking (per-row coverage attribution) is explicitly
out of this bug's scope — it is the OPEN operator-owned `turn-routing-enforcement/NEEDS_INPUT.md`
decision #6 (documented in the SPEC's Residual section), NOT a gap in this fix.
