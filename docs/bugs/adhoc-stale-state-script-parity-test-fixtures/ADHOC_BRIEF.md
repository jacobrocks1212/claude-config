---
kind: adhoc-brief
bug_id: adhoc-stale-state-script-parity-test-fixtures
enqueued_by: lazy-adhoc
date: 2026-06-20
---

# Ad-hoc bug: Stale TestStateScriptParity fixtures fail after --reassert-owner parity assertion added

test_lazy_parity.py::TestStateScriptParity has 3 failing tests (test_audit_state_script_parity_fires_when_binding_missing, _fires_when_reorder_queue_missing, _clean_when_both_bind). Root cause: when the single-slot-marker-ownership-race fix added the --reassert-owner assertion to lazy_parity_audit.audit_state_script_parity (alongside the earlier --reorder-queue assertion from no-sanctioned-queue-reorder-command), the synthetic tmp_path fixtures in test_lazy_parity.py::TestStateScriptParity were not updated to add --reassert-owner to the minimal state-script stubs. The audit now requires both flags, so the clean-fixture test returns 2 extra parity-violation strings and the fires-when-missing tests assert the wrong expected set. The load-bearing lazy_parity_audit.py --repo-root . passes (real scripts carry both flags); only the audit's own unit-test fixtures are stale. Fix: update the TestStateScriptParity fixtures to add --reassert-owner to the both-bind stub and adjust the fires-when-missing expectations. No production code change.
