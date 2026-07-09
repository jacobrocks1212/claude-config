---
kind: fixed
feature_id: pr-review-artifact-format-drift-breaks-lifespan-parsers
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

pr-review-artifact-format-drift-breaks-lifespan-parsers marked fixed on 2026-07-09 by the interactive subagent orchestration Jacob directed
("orchestrate the implementation ... update the SPECs when done"). This receipt was written by
the orchestrator, not the pipeline's __mark_fixed__ gate -- provenance is deliberately
operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

parsePreviousReview gained Pattern 4 (**Location:** + ###-title association); legacy **File:** patterns kept. Machine-readable sidecar PR-{id}-findings.json now emitted by synthesizer-v2 AND buddy Phase 2. Serving path B mooted by calibrate-weights.ts archival. VERIFIED offline: real artifacts both formats parse (new-format PR-16816 lifespan=1; legacy PR-16543 lifespan=1). PLAUSIBLE: sidecar emitters are prose -- first real review proves them.
