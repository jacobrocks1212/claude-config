---
kind: fixed
feature_id: build-queue-recycle-kills-concurrent-worktree-build
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-recycle-kills-concurrent-worktree-build marked fixed on 2026-07-09 by the interactive subagent orchestration Jacob directed
("orchestrate the implementation ... update the SPECs when done"). This receipt was written by
the orchestrator, not the pipeline's __mark_fixed__ gate -- provenance is deliberately
operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

Phases 1-2 (occupancy-gated recycle, the core symptom fix) landed previously and verified on disk. Phases 3-4 landed this session: segment-aware BUILD_QUEUE_BYPASS=1 recognition in build-queue-enforce.sh (cd-prefixed bypass allowed; un-bypassed segment still denied) + wiped-obj auto-restore guard in build-filtered.ps1 (drops --no-restore with WARN when project.assets.json missing) + .build.log-vs-.log skill docs. VERIFIED offline: test_hooks.py 138/138 (5 new), Pester 27/27 (new build-filtered.Tests.ps1), parse checks. OUTSTANDING (operator): one real-worktree /msbuild runtime row in PHASES Phase 4.
