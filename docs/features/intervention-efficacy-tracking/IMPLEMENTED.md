---
kind: implemented
feature_id: intervention-efficacy-tracking
date: 2026-07-04
provenance: pipeline-gated
derivation: message-grep
commits: [08942d8, 42d662b, 8941af1, 3c1446a, a270835, f242be2, '9243257']
decisions: []
---

# Implementation Ledger

**What shipped:** Every harness change is an implicit hypothesis ("this gate/hook/contract change will reduce friction signal X") that is never tested. This feature records the hypothesis at ship time — targeted signal, frozen baseline stats, expected direction, review-by threshold — as a deterministic, script-owned intervention record, then evaluates it against post-ship telemetry and writes a CONFIRMED / REFUTED / INCONCLUSIVE verdict. A REFUTED intervention auto-enqueues a reconsideration bug item (evidence attached, recurrence-guarded) instead of quietly persisting as dead weight; INCONCLUSIVE past N reviews escalates to operator triage; CONFIRMED closes the hypothesis. Verdicts become inputs to `/lazy-batch-retro`, replacing narrative success claims.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
