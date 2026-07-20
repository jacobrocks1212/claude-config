---
kind: needs-input
feature_id: subagent-wedge-backstop-hook
written_by: harness-change-gate
class: product
decisions:
  - Operator sign-off on the harness-change gate_weakening flag (enforcement-plane change) before marking the feature Complete
date: 2026-07-18
next_skill: __mark_complete__
---

# Harness-Change Design Gate — operator sign-off required (gate_weakening)

## Decision Context

### Operator sign-off on the gate_weakening flag

**Problem.** The subagent-wedge-backstop-hook feature added a NEW SubagentStop enforcement hook
(`user/hooks/subagent-wedge-backstop.sh`) + settings.json registration — control-surface scope — so
the design gate ran and raised `gate_weakening: hit`, blocking `__mark_complete__` until signed.

**The flag is a verified false positive (same class you just approved for containment-hook).** Its
SOLE evidence is **LAZY_QUEUE.md numeric-literal changes** — the auto-generated queue-status doc's
counts renumbering as items complete (`## Bugs (17) → (16)`, index shifts). LAZY_QUEUE.md is a
generated doc, not a gate. The feature diff ADDS enforcement (a new blocks-once hook); no test
deleted, no deny/refuse/exit-3 branch removed, no `*_BYPASS=` added.

**Recommendation:** Sign off — plane-strengthening change, no gate weakened, flag is a
harness-gate.py precision artifact on a generated doc. (Separately spinning off a bug to harden
harness-gate.py so it stops scanning generated docs / PHASES.md prose for gate-weakening patterns —
this is the 2nd such false positive this run.)
