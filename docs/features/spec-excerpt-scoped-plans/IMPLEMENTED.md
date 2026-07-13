---
kind: implemented
feature_id: spec-excerpt-scoped-plans
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [1a3dffd]
decisions: []
---

# Implementation Ledger

**What shipped:** `/write-plan-cognito` plans now embed a per-phase `#### SPEC excerpts` block — verbatim quotes of the Locked Decision rows / requirements / acceptance criteria the phase's lanes implement, each tagged with its SPEC section — so the `/execute-plan` orchestrator never reads SPEC.md (a measured ~14–38KB read in nearly every mined session). The planner reads the full SPEC once at planning time; the executor works from excerpts with a targeted escalation path.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
