---
kind: fixed
feature_id: harden-harness-feature-spec-lands-in-unmanaged-docs-specs
date: 2026-07-18
provenance: operator-directed-interactive
validated_via: code-audit (fix verified present in current tree)
auto_ticked_rows: 0
---

# Completion Receipt

Fix shipped in commit(s):
- d128c7f6 — harden(skill-prose): route feature-scope harden specs to docs/features + enqueue

Verified present in the current tree by the 2026-07-18 bug-backlog audit (read-only
verification agents confirmed the SPEC's named fix sites in current code; a commit-message
claim alone was not accepted as evidence).

Receipt + archive performed OUT-OF-PIPELINE per the docs/bugs/CLAUDE.md reconciliation
contract ("Fixing a bug OUT-OF-PIPELINE"): the fix landed via harden rounds / feature work
that never ran the __mark_fixed__ -> --archive-fixed tail, leaving a Concluded SPEC with a
shipped fix.
