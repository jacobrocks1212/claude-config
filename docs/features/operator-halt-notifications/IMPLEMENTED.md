---
kind: implemented
feature_id: operator-halt-notifications
date: 2026-07-04
provenance: pipeline-gated
derivation: message-grep
commits: [7ba88e9, 9824db2, 0e00073, 43671e1, 0000fd6, 7f07b58, c83db10]
decisions: []
---

# Implementation Ledger

**What shipped:** A `NEEDS_INPUT.md`/`BLOCKED.md` halt currently sits silently until the operator checks in — a batch run can idle for hours on a decision that takes ten seconds to answer. This feature wires a **script-owned notifier** into the state scripts' halt path: a shared `lazy_core.notify_halt()` helper, called by both `lazy-state.py` and `bug-state.py` at the terminal-emission chokepoint, pushes the halt (kind, item, the sentinel's decision titles, a deep link) to the operator's phone over an HTTP push channel. Notification is dedup-gated per sentinel identity, fail-OPEN (a send failure never blocks or corrupts the halt), and inert when no channel is configured. v1's answer path is "notice fast, answer in chat as today"; a mobile-committable resolution surface is the `native-android-pipeline-steering` sibling's territory, not built here.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
