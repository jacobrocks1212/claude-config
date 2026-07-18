---
kind: fixed
feature_id: byref-forward-cycles-frozen-on-multicycle-same-step
date: 2026-07-18
provenance: operator-directed-interactive
validated_via: code-audit (fix verified present in current tree)
auto_ticked_rows: 0
---

# Completion Receipt

Fix shipped in commit(s):
- e91bd305 — harden(script): count cycle budget at --cycle-end bracket, not on probes
- 74af39de — harden(script): advance forward_cycles on consume rise for same-step cycles
- a97e8060 — harden(script): mirror consume_gate=True to bug-state probe path (parity)

Verified present in the current tree by the 2026-07-18 bug-backlog audit (read-only
verification agents confirmed the SPEC's named fix sites in current code; a commit-message
claim alone was not accepted as evidence).

Receipt + archive performed OUT-OF-PIPELINE per the docs/bugs/CLAUDE.md reconciliation
contract ("Fixing a bug OUT-OF-PIPELINE"): the fix landed via harden rounds / feature work
that never ran the __mark_fixed__ -> --archive-fixed tail, leaving a Concluded SPEC with a
shipped fix.
