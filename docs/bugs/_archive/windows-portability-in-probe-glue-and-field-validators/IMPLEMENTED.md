---
kind: implemented
feature_id: windows-portability-in-probe-glue-and-field-validators
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [a3a862b, d20154e, 13a8425, b872c37, c8ea24b, f6d6625, 056686c, a381ad3, 0c92310]
decisions: []
---

# Implementation Ledger

**What shipped:** During `/lazy-batch` runs on AlgoBooth (Windows), the orchestrator's improvised probe glue writes `lazy-state.py` output to a POSIX `/tmp/` path and then reads it back with Windows-native Python, which has no `/tmp`, so the read crashes with `FileNotFoundError` and a redundant re-probe is forced. Separately, sentinel/plan files carrying a trailing carriage return (`\r`) fail AlgoBooth's `check-docs-consistency.ts` field validators on values that are otherwise legitimately correct, triggering mid-run normalization detours. Both are Windows-portability defects observed across multiple real runs; their fix loci differ (Symptom A → claude-config probe-glue prose; Symptom B → AlgoBooth-side validator).

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
