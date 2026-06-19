# Cycle subagents violate the turn-end contract — uncommitted deliverables, unticked plan boxes, half-flipped frontmatter — Investigation Spec (stub)

> Across multiple `/lazy-batch` runs, cycle subagents do the real work but fail to finish the turn cleanly: deliverables are left uncommitted (HEAD unchanged), PHASES.md/plan-file checkboxes are left unticked, and SPEC/plan frontmatter is flipped to Complete without the body ledger being reconciled. The `verify-ledger` step catches these every time, but each catch forces an extra recovery-cycle dispatch — pure meta overhead. This was the most consistent cross-session friction pattern in the audit.

**Status:** Investigating
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/cycle-subagent-leaves-work-uncommitted-or-unticked
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` cycle-subagent execution model + verify-ledger; `user/skills/_components/` execute-plan / implementation-agent components.

---

## Verified Symptoms
1. **[OBSERVED in logs]** Truncated cycle committed one WU but left the next WU's residue uncommitted — session `deb9f0cf` @ `2026-06-16T23:37:34Z`: "the truncated cycle committed WU-1… but left WU-2's residue uncommitted: DEFERRED_NON_CLOUD.md, PHASES.md, the mcp-tests entry, and the plan-Complete flip."
2. **[OBSERVED in logs]** Write-plan cycle left its deliverable uncommitted with HEAD unchanged — session `5d4b6c93` @ `2026-06-17T04:59:23`: "The write-plan cycle left its deliverable uncommitted (`?? phase-9-analyzer-subscribe-wire.md`, HEAD still at 5b79bafc) — a turn-end-contract violation."
3. **[OBSERVED in logs]** Execute-plan subagent flipped frontmatter Complete but did not tick body boxes — session `5d4b6c93` @ `2026-06-17T14:25:19`: "the execute-plan subagent flipped the frontmatter Complete but didn't tick the body boxes. That's the `deliverables_done` failure."
4. **[OBSERVED in logs]** Plan ledger left half-flipped — frontmatter In-progress with unticked boxes despite all WUs landing — session `61d6ddcf` @ `2026-06-09T17:14:42`: "part-11's plan frontmatter is `In-progress` with 5 unticked plan-file boxes despite all three WUs landing… subagent ticked PHASES.md deliverables but left the plan ledger half-flipped."
5. **[OBSERVED in logs]** Orphaned cycle left real uncommitted work; HEAD == origin so nothing of the cycle is committed — session `5c33b6ba` @ `2026-06-11T19:11:45`: "The orphaned cycle left real uncommitted work — the fix (looper/voice.rs) + a new storm regression test + scenario doc updates + the WU checkboxes. HEAD == origin … so none of cycle-20 is committed."

## Evidence Collected (from session logs)
- session `deb9f0cf` @ `2026-06-16T23:37:34Z`: "the truncated cycle committed WU-1… but left WU-2's residue uncommitted: DEFERRED_NON_CLOUD.md, PHASES.md, the mcp-tests entry, and the plan-Complete flip." — partial commit; a single cycle landed some artifacts but stranded a multi-artifact residue (state doc, plan ledger, mcp-tests entry, Complete flip).
- session `5d4b6c93` @ `2026-06-17T04:59:23`: "The write-plan cycle left its deliverable uncommitted (`?? phase-9-analyzer-subscribe-wire.md`, HEAD still at 5b79bafc) — a turn-end-contract violation." — deliverable authored on disk but never committed; HEAD pinned to a pre-cycle commit.
- session `5d4b6c93` @ `2026-06-17T14:25:19`: "the execute-plan subagent flipped the frontmatter Complete but didn't tick the body boxes. That's the `deliverables_done` failure." — frontmatter/body divergence; the `deliverables_done` invariant fails because the body ledger contradicts the flipped frontmatter.
- session `61d6ddcf` @ `2026-06-09T17:14:42`: "part-11's plan frontmatter is `In-progress` with 5 unticked plan-file boxes despite all three WUs landing… subagent ticked PHASES.md deliverables but left the plan ledger half-flipped." — two ledgers (PHASES.md vs plan file) updated inconsistently; one ticked, the other left stale.
- session `5c33b6ba` @ `2026-06-11T19:11:45`: "The orphaned cycle left real uncommitted work — the fix (looper/voice.rs) + a new storm regression test + scenario doc updates + the WU checkboxes. HEAD == origin … so none of cycle-20 is committed." — an entire cycle's output (source fix, new test, doc updates, checkboxes) stranded uncommitted.

## Why this is friction
Subagents reliably complete the actual work but violate the turn-end contract by failing to commit and/or reconcile the ledger before the turn ends. `verify-ledger` correctly catches each instance, but every catch costs an extra recovery-cycle dispatch — recurring meta overhead observed in at least four distinct sessions, making this the most consistent cross-session friction pattern in the audit.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Which exact turn-end steps (commit, PHASES.md tick, plan-file tick, frontmatter flip) are most often skipped, and is there a common ordering or truncation point?
- Is the contract under-specified in the subagent prompt, or specified but unenforced at turn boundary?
- Should the fix tighten the contract prose, add a deterministic turn-end gate, or both?
- Why does partial commit occur (some artifacts committed, others stranded) within a single cycle?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
