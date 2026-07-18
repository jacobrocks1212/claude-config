---
kind: fixed
feature_id: end-of-run-flush-commit-absorbs-concurrent-writer-staged-files
date: 2026-07-18
provenance: backfilled-unverified
validated_via: fix shipped as lazy_core.flush_commit_artifacts (ledgers.py:3924, exported) + the slug-attributed pathspec-scoped flush-commit staging contract in lazy-batch SKILL.md section 1c.6 (line ~517); the discipline was applied live throughout the 2026-07-18 run (every orchestrator flush commit pathspec-scoped; foreign harden-agent staged files never absorbed despite an active concurrent writer); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

end-of-run-flush-commit-absorbs-concurrent-writer-staged-files marked Fixed on 2026-07-18 by
the /lazy-batch-parallel orchestrator applying the docs/bugs/CLAUDE.md out-of-pipeline
reconciliation contract (13th unreconciled fixed-out-of-pipeline SPEC found this run).
Receipt written by the orchestrator, not the pipeline's __mark_fixed__ gate - provenance is
deliberately backfilled-unverified.

## Notes

The fix shipped out-of-pipeline: the section-1c.6 flush-commit staging contract mandates
pathspec-scoped commits (never blanket git add -A over docs/*) with
lazy_core.flush_commit_artifacts as the tested embodiment. Exercised live this run under an
ACTIVE concurrent writer (the AlgoBooth run's harden agent editing this checkout): the
orchestrator's dozens of flush/reconciliation commits were all pathspec-scoped and no foreign
staged/dirty file was absorbed - the exact incident (115a991a) this SPEC investigated cannot
recur through the contracted path.
