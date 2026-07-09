---
kind: fixed
feature_id: subagent-backgrounds-verification-ends-turn-before-green
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

subagent-backgrounds-verification-ends-turn-before-green marked fixed on 2026-07-09 by the
interactive subagent orchestration Jacob directed. This receipt was written by the orchestrator,
not the pipeline's __mark_fixed__ gate -- provenance is deliberately operator-directed-interactive.

## Notes

All three phases landed: build-queue-await.ps1 followable-wait primitive (bounded poll on results/<seq>.json, re-emits the real Format-BuildQueueBanner line, mirrors the build exit code; distinct exit 124 await-timeout / 125 malformed-result), the four Cognito build skills' section-4 background-enqueue -> await-to-banner contract (enqueued-as-seq is NOT an outcome; 124 = keep waiting, never success), and the turn-end gate in implementation-agent.md / tdd-test-agent.md / lane-agent-briefing.md (no ending a turn on a bare enqueue). VERIFIED offline: TDD RED (1/8) -> GREEN (8/8 Pester, incl. banner byte-parity vs the real Format-BuildQueueBanner, log-failure-override forced-FAIL, and a deferred-write case where the await genuinely blocks then banners); project-skills + lint-skills clean; gate text confirmed in projected skills. PLAUSIBLE: phases 2-3 are projection-verified prose. OUTSTANDING (operator): live end-to-end -- a real subagent backgrounding a real Cognito build and awaiting it to the banner. KNOWN LIMIT: current results/<seq>.json carries no op field, so the awaited banner shows op= empty for now (build-queue-eta-priority-lanes duration capture would populate it).
