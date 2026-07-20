---
kind: fixed
feature_id: verify-ledger-deliverables-done-fails-pre-decomposition-feature
date: 2026-07-20
provenance: backfilled-unverified
validated_via: pytest (user/scripts/tests/test_lazy_core/ — 1339 passed, incl. 3 new registered regression tests) + lazy-state/bug-state --test + test_hooks (286) + lint-skills + bug-state --fsck; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`verify-ledger-deliverables-done-fails-pre-decomposition-feature` marked Fixed on 2026-07-20.
Fixed OUT-OF-PIPELINE via hardening Round 118 (`/harden-harness`, observed-friction dispatch on
`inspector-track-dashboard`), NOT the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Fix

Commit `5529a973` (`harden(script): treat absent PHASES.md on a pre-decomposition feature as
not-applicable in deliverables_done`). In `lazy_core/gates.py::verify_ledger`, the feature-level
branch of check 4 now gates its `False`-on-absent-`PHASES.md` on `_implementation_plans_exist`
(the same discriminator the sibling check 3 already uses for `plan_complete`). When no PHASES.md
AND no implementation plan exist (a pre-decomposition scope stub), `deliverables_done` is now
`True` (not-applicable) with a `_diag` breadcrumb and a distinct `deliverables_source`; when an
implementation plan exists but PHASES.md is missing it stays `False` (regression guard). All
other states are byte-identical.

## Verification

- Live repro: `lazy-state.py --verify-ledger <inspector-track-dashboard dir>` flipped
  `ok:false` (failing_check `deliverables_done`, note "PHASES.md absent") → `ok:true`
  (`deliverables_source: not-applicable (pre-decomposition …)`) at `5529a973`.
- `python -m pytest user/scripts/tests/test_lazy_core/` → 1339 passed, including three new
  registered regression tests (pre-decomposition pass, source-diagnostic, and the
  impl-plan-present regression guard) and the orphan-registration guard.
- `test_hooks.py` 286/286; `lazy-state.py --test` / `bug-state.py --test` OK;
  `lint-skills.py --check-projected --check-capabilities` OK; `bug-state.py --fsck` clean;
  `harness-gate.py --range origin/main..HEAD` → `gate_weakening: pass`.

## Reconciliation handback

This receipt was written by the dispatched harden subagent under an active cycle marker, which
is refused the orchestrator-only queue-mutating ops. The `--archive-fixed` +
`--link-provenance --commits 5529a973` calls are handed back to the orchestrator to run at the
harden-return seam (`/lazy-batch` §1d.1) — see hardening-log Round 118 Reconciliation.
