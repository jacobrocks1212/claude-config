# Self-inflicted environment transients (stale named-pipe / runtime not ready) are counted against the feature's validation-retry budget — Investigation Spec (stub)

> During a `/lazy-batch` run on AlgoBooth, an orchestrator-caused environment transient — a stale Windows named-pipe handle / zombie node process left behind by a `dev:restart` — prevented the dev sidecar from booting. Because the runtime never came up, every MCP assertion went pending and the failure surfaced as a *validation BLOCKED at retry 5*, inflating the feature's validation-escalation count even though no code was wrong. The validation-retry accounting does not distinguish a self-inflicted environment transient from a genuine code failure.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/env-transient-counts-against-validation-retry-budget
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` mcp-test gate + validation_escalation retry accounting; dev runtime restart sequence (`dev:restart` / `dev:kill`)

---

## Verified Symptoms
1. **[OBSERVED in logs]** An orchestrator-caused infra transient was charged to the validation-retry budget as a BLOCKED at retry 5 — session `5d4b6c93` @ `2026-06-17T12:52:40Z`: "7/15 — ENVIRONMENT failure, not code: sidecar never booted ('Failed to create pipe server: Access is denied, os error 5')… This BLOCKED (retry 5) is a transient infra failure I caused — my `dev:restart` left a stale Windows named-pipe handle."
2. **[OBSERVED in logs]** A surviving zombie node process held the named pipe across kill attempts — session `5d4b6c93` @ `2026-06-17T12:58:52`: "One node process (8680) survived both `dev:kill`s… A zombie sidecar holding the named pipe would explain the recurring 'Access denied.'".

## Evidence Collected (from session logs)
- session `5d4b6c93` @ `2026-06-17T12:52:40Z` — "7/15 — ENVIRONMENT failure, not code: sidecar never booted ('Failed to create pipe server: Access is denied, os error 5')… This BLOCKED (retry 5) is a transient infra failure I caused — my `dev:restart` left a stale Windows named-pipe handle." (Interpretation: a self-inflicted env transient made all MCP assertions pending, yet was counted as a validation BLOCKED at retry 5, inflating escalation even though no code was wrong.)
- session `5d4b6c93` @ `2026-06-17T12:58:52` — "One node process (8680) survived both `dev:kill`s… A zombie sidecar holding the named pipe would explain the recurring 'Access denied.'" (Interpretation: the `dev:restart` left a zombie node process holding the named pipe, which is the source of the recurring "Access denied" and the env transient.)

## Why this is friction
An orchestrator-caused environment transient (stale named-pipe / zombie node from `dev:restart`) made all MCP assertions go pending and surfaced as a *validation BLOCKED at retry 5*, inflating the feature's escalation count even though no code was wrong. Validation-retry accounting does not distinguish an env-transient from a genuine code failure, so a self-inflicted infra hiccup can burn a feature's retry budget and push it toward escalation/halt for the wrong reason.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Should env-transient failures (runtime not ready / pipe access denied) be excluded from the validation-retry budget, and if so how are they reliably distinguished from genuine code failures at the gate?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
