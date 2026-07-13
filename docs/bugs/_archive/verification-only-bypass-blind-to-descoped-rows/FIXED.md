---
kind: fixed
feature_id: verification-only-bypass-blind-to-descoped-rows
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

verification-only-bypass-blind-to-descoped-rows marked Fixed on 2026-07-12 during an
operator-directed multi-item STATE-lane close-out pass. This receipt was written by the
orchestrating subagent, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`.

## Notes

The instance fix (Fix Scope, D1-D3) was already landed and self-documented in the SPEC's own
`## Resolution (2026-07-12 — mechanical fix shipped)` section (hardening-log Round 30, commits
`0628422` + `6012c727`). A subsequent, broader generalization pass (the spun-off canonical
`<!-- descoped -->` structural marker) also landed at HEAD before this close-out
(`32475406`, `498a5f02`). This pass authored `PHASES.md` documenting both against the SPEC's Fix
Scope, verified the regression tests are present and green, and closed the bug — no production
code changed this session.

Verification: `python -m pytest user/scripts/test_lazy_core.py -q` → 1064 passed (includes
`test_verification_only_descoped_dropped_row_is_true`,
`test_verification_only_plain_unchecked_row_still_false`,
`test_verification_only_struck_without_descope_marker_still_false`,
`test_verification_only_descoped_marker_only_row_is_true`,
`test_verification_only_descoped_marker_no_diagnostic`,
`test_verification_only_descoped_header_scope_marker_exempts_rows_beneath`,
`test_descoped_marker_lockstep_producer_matches_ssot`).
