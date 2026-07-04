---
kind: implemented
feature_id: feature-queue-lacks-on-disk-autodiscovery
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [03e59af, febc24e, 084c523, 928aa5f, d01f578, 1f310c5]
decisions: []
---

# Implementation Ledger

**What shipped:** `bug-state.py` auto-discovers open bug dirs on disk (hybrid load over `docs/bugs/queue.json`), but `lazy-state.py` reads features **only** from `docs/features/queue.json` — so a new `docs/features/<slug>/SPEC.md` is inert until explicitly `--enqueue-adhoc`'d. The operator wants claude-config opted into feature auto-discovery, mirroring bugs.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
