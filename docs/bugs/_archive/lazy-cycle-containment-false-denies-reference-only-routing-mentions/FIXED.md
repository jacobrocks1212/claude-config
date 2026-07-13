---
kind: fixed
feature_id: lazy-cycle-containment-false-denies-reference-only-routing-mentions
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (not pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

lazy-cycle-containment-false-denies-reference-only-routing-mentions marked fixed on 2026-07-12
during an interactive HOOKS-lane close-out pass (Jacob directed a sweep of three named bugs;
this receipt was written by that session, not the pipeline's `__mark_fixed__` gate — provenance
is deliberately `operator-directed-interactive`).

## Notes

The fix (`_STATE_PY_INVOKE_RE`/`_STATE_PY_INVOKE_SEG_RE` segment-anchored invocation matching for
routing flags, plus the sibling `_LIFECYCLE_INVOKE_RE` anchoring) was found **already fully
implemented and tested** in `user/hooks/lazy-cycle-containment.sh` at the start of this pass — no
code changes were made for this bug. All six regression tests the SPEC's Fix Scope names were
present in `user/scripts/test_hooks.py` and GREEN:
`test_containment_allows_state_script_reference_only_mention`,
`test_containment_still_denies_real_state_script_invocation`,
`test_containment_denies_lifecycle_commands`,
`test_containment_allows_lifecycle_reference_only_mention`,
`test_containment_agentid_present_denies_lifecycle_no_marker`,
`test_containment_agentid_absent_allows_lifecycle_no_marker`.

Symptom reproduction (red→green pipe-test legs, per the SPEC's own Verified Symptom section): the
SPEC records the ORIGINAL red-against-the-unanchored-matcher run
(`test_containment_allows_state_script_reference_only_mention`, RED pre-fix) and a live post-fix
proof (commit `8494a4f0`, a `harden(hook):` commit whose message contains
`lazy-state.py`/`bug-state.py`/`routing`/`--run-start` and was ALLOWED). This close-out pass
re-confirmed GREEN: `python -m pytest user/scripts/test_hooks.py -q -k
"test_containment_allows_state_script_reference_only_mention or
test_containment_still_denies_real_state_script_invocation or
test_containment_denies_lifecycle_commands or
test_containment_allows_lifecycle_reference_only_mention or
test_containment_agentid_present_denies_lifecycle_no_marker or
test_containment_agentid_absent_allows_lifecycle_no_marker"` → 6 passed. Full suite: `python -m
pytest user/scripts/test_hooks.py -q` → 217 passed. `python user/scripts/doc-drift-lint.py
--repo-root .` → exit 0 (no Hooks-table changes were needed for this bug — the hook's row is
unaffected by an internal regex change).

PHASES.md authored in this pass (was missing) to document the pre-landed state with evidence per
the standard close-out contract.
