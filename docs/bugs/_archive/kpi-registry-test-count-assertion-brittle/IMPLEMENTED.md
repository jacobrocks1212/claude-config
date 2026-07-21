---
kind: implemented
feature_id: kpi-registry-test-count-assertion-brittle
date: 2026-07-20
provenance: manual
linked_by: operator
derivation: commit-range
commits: [0b85cf3]
decisions: []
---

# Implementation Ledger

**What shipped:** Discovered during unrelated work (not caused by it): `python3 -m pytest user/scripts/test_kpi_scorecard.py -q` fails with `assert 26 == 25` in `TestLintGreen::test_real_seeded_registry_lints_green`. `/harden-harness` invoked directly by the operator against this isolated, pre-existing defect.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)
