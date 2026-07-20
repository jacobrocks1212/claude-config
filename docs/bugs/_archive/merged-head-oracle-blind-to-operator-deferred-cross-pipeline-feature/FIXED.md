---
kind: fixed
feature_id: merged-head-oracle-blind-to-operator-deferred-cross-pipeline-feature
date: 2026-07-19
provenance: backfilled-unverified
fix_commit: a1f98e4d
---

# Fix Receipt (hand-written by the /harden-harness Round 102 meta-cycle)

**Provenance:** `backfilled-unverified` — this bug was fixed OUT-OF-PIPELINE via a
`harden(script):` commit (not the bug pipeline's gated `__mark_fixed__` path), so the receipt is
hand-written per the `docs/bugs/CLAUDE.md` OUT-OF-PIPELINE contract.

**Fix commit:** `a1f98e4d` — `harden(script): merged-head oracle excludes operator-deferred
cross-pipeline feature`. Restores the pure `spec_dir_operator_deferred` file-predicate at the
single oracle landing site (`lazy_core.dispatch.merged_head_nondispatchable_ids`), excluding an
operator-deferred (`DEFERRED.md`) candidate — feature OR bug — from the merged head before the
scoped `is_dispatchable` check, closing the cross-pipeline-feature blindness.

**Bug spec (Step 2.5, committed BEFORE the fix):** `harden(docs): a1fc408b`.

**Regression evidence (green):**
`test_merged_head_nondispatchable_ids_excludes_operator_deferred_cross_pipeline_feature`
(deferred feature excluded → no `merged-head-diverged` withhold; non-vacuity: the
scoped-DISPATCHABLE feature deadlocks WITHOUT the fix; control: `DEFERRED.md` removed → the feature
is NOT excluded, proving the predicate keys on the FILE). Full gates:
- lazy_core pytest: 1279/1279
- test_hooks.py: 268/268
- lazy-state.py --test / bug-state.py --test: OK
- lazy_parity_audit.py: exit 0
- lint-skills.py --check-projected --check-capabilities: OK
- bug-state.py --fsck: ok

**Reconciliation handback:** `--archive-fixed` + `--link-provenance` are orchestrator-only
(cycle-refused for this dispatched harden meta-cycle). Handed back to the harden-return seam
(`/lazy-bug-batch` §1d.1) — see the Round-102 hardening-log entry `reconcile:` field.
