---
kind: implemented
feature_id: probe-full-read-before-dispatch
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [ac67713, 2b593e7, fb2abb0, dc53e2a, 4310bd7, 901fcee, 19096d7]
decisions: []
---

# Implementation Ledger

**What shipped:** The orchestrators' `probe→emit→dispatch atomicity` rule mandates a *fresh* re-probe before every dispatch but never says to consume the **whole** probe JSON. An orchestrator can field-extract a subset of keys (e.g. `pending_hardening`, `terminal_reason`) and route on that, risking a missed routing signal — `diagnostics`, `git_guards`, `self_edit_mode`, `route_overridden_by`, `cycle_prompt_refused`, `device_deferred_features`, etc. Observed as a self-corrected near-miss in a live AlgoBooth run.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
