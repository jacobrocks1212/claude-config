---
kind: fixed
feature_id: pr-review-plugin-cache-split-brain-freezes-weights
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

pr-review-plugin-cache-split-brain-freezes-weights marked fixed on 2026-07-09 by the interactive subagent orchestration Jacob directed
("orchestrate the implementation ... update the SPECs when done"). This receipt was written by
the orchestrator, not the pipeline's __mark_fixed__ gate -- provenance is deliberately
operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

Candidate Fix 1 implemented: mutable weights relocated to state file ~/.claude/state/cognito-pr-review/weights.yaml (seeded from knowledge/weights.yaml; all loaders + prep-pr snapshot prefer state). Calibration now survives version bumps; scripts take effect without bumps (invoked via symlink path). VERIFIED: script-side write->read convergence chain (sandboxed). PLAUSIBLE/pending: live buddy round-trip; definition-side staleness still requires the version bump + reinstall (done at orchestration close). NOT DONE (deliberate): Candidate Fix 4 @skills-dir migration -- would invalidate the repo-scoping enablement key; future operator decision. prep-pr.ts gained a source-vs-installed version-divergence stderr warning.
