---
kind: implemented
feature_id: multi-repo-concurrent-runs
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [d5365ce, 00f0831, 8b39bf1, f9f3eb8, 80e4b40, f8672f8, e02f9f8, 0b65e7a, 3593db0,
  14b64e7, 715b4da]
decisions: []
---

# Implementation Ledger

**What shipped:** Make the lazy run-marker and its enforcement hooks per-repo, so a lazy-batch run in one repo neither blocks nor is blocked by a run in another repo.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
