---
kind: fixed
feature_id: adhoc-harden-bug-pipeline-gate-verdict-and-detector-gaps
provenance: backfilled-unverified
date: 2026-07-19
fix_commits:
  - 593ab6de
  - 1839ae4f
---

# Fixed — bug-pipeline gate-verdict + detector gaps

All four gaps fixed OUT-OF-PIPELINE via `/harden-harness` (inline manual):

- **GAP 1** (`593ab6de`) — new registered `gate-verdict` completion-time dispatch class +
  `dispatch-gate-verdict.md` template + `/lazy-batch` & `/lazy-bug-batch` routing; stale
  "SEAM-DEFERRED" docs reconciled.
- **GAP 2/3/4** (`1839ae4f`) — `spec_fix_implemented_heading` detector extension,
  `normalize_item_dir` spec-path polymorphism, audit-obligation `item_name` label fix.

**Evidence:** full `tests/test_lazy_core/` suite 1334 passed; `lazy-state.py --test` +
`bug-state.py --test` pass; `lazy_parity_audit.py` exit 0; `doc-drift-lint.py` exit 0;
`lint-skills.py` OK; `test_hooks.py` exit 0. New regression tests:
`test_gates.py` (GAP 2/3), `test_ledgers.py` (GAP 4), `test_dispatch.py` (GAP 1).

`provenance: backfilled-unverified` — receipt hand-written at the inline-manual harden
reconciliation seam (no pipeline `__mark_fixed__` gate ran).
