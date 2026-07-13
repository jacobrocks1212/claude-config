---
kind: implemented
feature_id: anti-overfit-design-gate
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 2cf3289, 7bf8c9b, 501ac8c, dde89ea, '9243257']
decisions: []
---

# Implementation Ledger

**What shipped:** A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single incidents, weaken its own gates, and grade itself with metrics it controls. This feature generalizes the existing `/harden-harness` anti-overfit reflex into a mechanical + adversarial review gate on harness self-modifications — overfit-smell detection (incident-literal rules), tautological-metric detection (via the intervention record's signal-independence declaration), gate-weakening detection (loosened thresholds / broadened exemptions demand explicit operator sign-off), and a complexity budget ("what does this retire?") — with every verdict recorded so the gate's own judgment is auditable and later falsifiable by efficacy data it does not control.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
