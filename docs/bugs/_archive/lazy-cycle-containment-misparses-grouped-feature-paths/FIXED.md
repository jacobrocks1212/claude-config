---
kind: fixed
feature_id: lazy-cycle-containment-misparses-grouped-feature-paths
date: 2026-07-18
provenance: operator-directed-interactive
validated_via: code-audit (fix verified present in current tree)
auto_ticked_rows: 0
---

# Completion Receipt

Fix shipped in commit(s):
- 251187c8 — harden(hook): make lazy-cycle-containment 2nd-feature tripwire group-aware
- cb666120 — harden(hook): containment tripwire — deep-grouped paths + ingest-research batch (gaps 6,7)

Verified present in the current tree by the 2026-07-18 bug-backlog audit (read-only
verification agents confirmed the SPEC's named fix sites in current code; a commit-message
claim alone was not accepted as evidence).

Receipt + archive performed OUT-OF-PIPELINE per the docs/bugs/CLAUDE.md reconciliation
contract ("Fixing a bug OUT-OF-PIPELINE"): the fix landed via harden rounds / feature work
that never ran the __mark_fixed__ -> --archive-fixed tail, leaving a Concluded SPEC with a
shipped fix.
