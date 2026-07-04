---
kind: implemented
feature_id: incident-auto-capture
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [b421939, 4e0faf6]
decisions: []
---

# Implementation Ledger

**What shipped:** Hooks write `hook-error.json` breadcrumbs and the dispatch guard writes deny-ledger entries, but turning a runaway/deny-loop into a `docs/bugs/` entry is manual retro work. A deterministic collector that scans breadcrumbs + repeated-deny patterns, clusters them, applies a per-signal recurrence bar, dedups against open/archived bug slugs, and enqueues stub-status bugs via the existing `--enqueue-adhoc --type bug` path closes the observe→harden loop without waiting for `/lazy-batch-retro`. The collector proposes evidence; `/spec-bug` still owns root cause.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
