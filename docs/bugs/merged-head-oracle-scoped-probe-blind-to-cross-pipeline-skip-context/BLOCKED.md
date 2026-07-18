---
kind: blocked
feature_id: merged-head-oracle-scoped-probe-blind-to-cross-pipeline-skip-context
phase: "Investigation Concluded — fix design hard-parked for operator ratification"
blocked_at: 2026-07-18T00:00:00Z
retry_count: 0
blocker_kind: needs-operator-decision
recovery_suggestion: "Ratify the STRUCTURAL design fork in docs/specs/turn-routing-enforcement/NEEDS_INPUT_2026-07-18-merged-head-oracle-cross-pipeline-context.md (revises Locked Decision L3 of the COMPLETED merged-head-actionability-oracle feature). Once ratified, /plan-bug this spec to implement the chosen cross-pipeline classification (recommended: higher-priority-of-two-full-probe-heads). Do NOT auto-drive: the fix overrides a completed feature's locked decision and is coupled-pair mirrored across three sites in two state scripts."
---

## Details

The root cause is CONCLUDED and deterministically reproduced (see `SPEC.md`), but the fix revises a
LOCKED DECISION (L3) of the completed `merged-head-actionability-oracle` feature and touches core
cross-pipeline dispatch routing (coupled-pair mirrored, three exclude-set construction sites). Per
the `/harden-harness` park-provisional structural carve-out, the fix architecture is
operator-owned. This `BLOCKED.md` keeps the bug pipeline from planning/implementing an un-ratified
structural change; it re-enters automatically once the NEEDS_INPUT sentinel is ratified and this
blocker is neutralized.
