---
kind: implemented
feature_id: adhoc-stale-state-script-parity-test-fixtures
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [fe16344, '7667072', 2e691ef, 95a3177, c52b297, 30a752f, 4fbc3a8]
decisions: []
---

# Implementation Ledger

**What shipped:** `test_lazy_parity.py::TestStateScriptParity`'s synthetic `tmp_path` stubs predate the `--reassert-owner` and `requires_host` fail-fast parity assertions added to `audit_state_script_parity`, so the audit returns extra findings the fixtures don't expect. Test-fixture-only; no production drift.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
