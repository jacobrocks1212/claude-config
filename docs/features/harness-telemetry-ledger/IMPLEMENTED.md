---
kind: implemented
feature_id: harness-telemetry-ledger
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [c2522e6, 90a594c, bb18150, 352d395, 3508db9, 7ed28f1, e28882c, 72e9c5b, '9243257']
decisions: []
---

# Implementation Ledger

**What shipped:** Retros find friction qualitatively; nothing measures it. Both state scripts gain a deterministic, append-only JSONL telemetry ledger written at their existing chokepoints (run/cycle brackets, dispatch, gate refusals, halt observation, sentinel resolution, pseudo-skill completion), modeled byte-for-byte on the proven `lazy-deny-ledger.jsonl` writer. A pure-read trends aggregator and a `pipeline_visualizer` trends page derive the metrics (cycles-per-completion, gate-refusal rate, halt dwell, run duration) reader-side, and `/lazy-batch-retro` cites ledger deltas instead of narrative-only claims — so "did that harness change actually reduce coherence-recovery cycles?" becomes answerable with data.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
