# No first-class queue-reorder command — operator queue mutations must round-trip through a BLOCKED.md + apply-resolution subagent — Investigation Spec (stub)

> When the operator directs a queue reorder (e.g., move features to the tail), there is no sanctioned queue-reorder command in `lazy-state.py`, and HARD CONSTRAINT 1 bars the orchestrator from editing `queue.json` directly. So the orchestrator turns a simple deterministic state mutation into a sentinel write (BLOCKED.md) plus a fully dispatched apply-resolution subagent — a whole meta-cycle to accomplish a reorder. This is a standing capability gap between HARD CONSTRAINT 1 and the absent reorder primitive.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/no-sanctioned-queue-reorder-command
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy-state.py` (`--enqueue-adhoc` exists; no reorder / defer-to-tail primitive); `user/skills/lazy-batch/SKILL.md` HARD CONSTRAINT 1 (orchestrator may not edit queue.json directly)

---

## Verified Symptoms
1. **[OBSERVED in logs]** A simple operator-directed queue reorder had no first-class command, so the orchestrator routed it through a BLOCKED.md sentinel + a dispatched apply-resolution subagent — session `a0eae4be` @ `2026-06-18T15:39:39.548Z`: "No sanctioned queue-reorder script command exists, and HARD CONSTRAINT 1 bars me from editing `queue.json` directly — so I'll enact this through the established Defer mechanism: record the operator directive on a BLOCKED.md and dispatch an apply-resolution subagent to … move the 3 audio-analysis features to the queue tail.".

## Evidence Collected (from session logs)
- session `a0eae4be` @ `2026-06-18T15:39:39.548Z`: "No sanctioned queue-reorder script command exists, and HARD CONSTRAINT 1 bars me from editing `queue.json` directly — so I'll enact this through the established Defer mechanism: record the operator directive on a BLOCKED.md and dispatch an apply-resolution subagent to … move the 3 audio-analysis features to the queue tail." — a deterministic reorder is forced into a sentinel write plus a full subagent dispatch because no reorder primitive exists.

## Why this is friction
When the operator directs a queue reorder / skip-removal, the absence of a first-class command forces the orchestrator to convert a simple deterministic `queue.json` mutation into a BLOCKED.md sentinel write plus a fully dispatched apply-resolution subagent — a meta-cycle. HARD CONSTRAINT 1 (correctly) forbids the orchestrator from editing `queue.json` directly, but with no sanctioned reorder primitive there is no cheap deterministic path, so routine operator intent costs a whole dispatch.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- What is the right surface for a sanctioned queue mutation (e.g., a `lazy-state.py --reorder` / `--defer-to-tail` / `--remove` primitive) that respects HARD CONSTRAINT 1?
- Which operator queue mutations need to be first-class (reorder, defer-to-tail, remove/skip, reprioritize), and which can remain via the ad-hoc enqueue path?
- Should such a command be operator-only / out-of-cycle, mirroring how `--enqueue-adhoc` and `--ack-unhardened` are gated?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
