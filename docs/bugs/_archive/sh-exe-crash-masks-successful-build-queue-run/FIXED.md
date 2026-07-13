---
kind: fixed
feature_id: sh-exe-crash-masks-successful-build-queue-run
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

sh-exe-crash-masks-successful-build-queue-run marked fixed on 2026-07-09 by the interactive subagent orchestration Jacob directed
("orchestrate the implementation ... update the SPECs when done"). This receipt was written by
the orchestrator, not the pipeline's __mark_fixed__ gate -- provenance is deliberately
operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

Docs-only fix (root cause is an out-of-scope sh.exe/MSYS2 segfault; no build-queue code defect): 'shell crash != build failure' guidance added to Cognito CLAUDE.local.md Build & Test Workflow and the /build-queue-status skill (named the recovery entry point: check status, then <seq>.log / .build.log / results/<seq>.json before re-running). Verified by inspection (doc-only).
