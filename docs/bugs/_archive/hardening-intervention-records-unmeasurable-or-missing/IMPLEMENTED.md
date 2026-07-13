---
kind: implemented
feature_id: hardening-intervention-records-unmeasurable-or-missing
date: 2026-07-12
provenance: pipeline-gated
derivation: commit-brackets
commits: [0f07a97, 20de8c6, 06a6293, 5e42afc, ec5ed77, 923274a, 4c2b0ce, 7fbeaea, 95dbfd6,
  843d7aa]
decisions: []
---

# Implementation Ledger

**What shipped:** The `/harden-harness` Step-4 capture contract produces records the evaluator can never grade: two records name telemetry event types that do not exist in the emit vocabulary (accepted silently — `record_intervention` validates nothing), 17 of 25 records are `target_signal: undeclared`, and round-vs-record coverage is prose-only self-attestation — a round's "Intervention record: none" exemption line is checked by no one.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
