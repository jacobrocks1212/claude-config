---
kind: implemented
feature_id: adhoc-cycle-begin-real-requires-sub-skill
date: 2026-07-06
provenance: pipeline-gated
derivation: commit-brackets
commits: [35bdb2d, 8eddf7b, e84207d]
decisions: []
---

# Implementation Ledger

**What shipped:** A real cycle marker written with `sub_skill=None` (orchestrator omitted `--sub-skill`) makes the `--cycle-end` commit-budget indeterminate — the recurring unexpected-commits false-positive class. Harden the WRITE side so the marker can never be born sub_skill-less on a real cycle.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
