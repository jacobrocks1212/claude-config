---
kind: implemented
feature_id: adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [8447b3d, 88d55d5, '4580428', 6c35072]
decisions: []
---

# Implementation Ledger

**What shipped:** harness-gate.py runs its structural detectors over EVERY file in the diff range, so off-manifest generated docs (LAZY_QUEUE.md), PHASES.md prose rows, and unrelated bug/feature SPEC.md files swept into a range produce `gate_weakening=hit` / `overfit=flag` false positives — forcing redundant operator sign-off on plane-strengthening changes.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
