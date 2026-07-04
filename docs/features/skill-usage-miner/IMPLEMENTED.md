---
kind: implemented
feature_id: skill-usage-miner
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [166bcae, 8f1c6ba, cadfd81, '2070734', d8669d1, 1be14ed, 2cfdbe2, 950a057]
decisions: []
---

# Implementation Ledger

**What shipped:** The skills tree only grows — 83 user-level skills plus 29 repo-scoped ones today, with stray non-skill artifacts checked in alongside them — and nothing measures which skills are load-bearing. This feature ships a stdlib-only, **read-only** miner over the same session-log corpus `toolify-miner.py` reads, counting per-skill invocations via two honest detectors (Skill-tool calls and slash-command markers), and emits a ranked usage report with a never-invoked list, a hygiene sweep of non-skill files, and toolify-bar cross-links for high-frequency prose skills. It **proposes, never auto-archives** — archival stays a deliberate operator move into `archived/` with its audit-trail row.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
