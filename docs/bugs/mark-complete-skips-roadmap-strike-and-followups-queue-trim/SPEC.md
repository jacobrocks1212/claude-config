# __mark_complete__ does not auto-strike the ROADMAP row and mis-trims `-followups` queue ids — Investigation Spec (stub)

> When a feature completes, the `__mark_complete__` pseudo-action does not strike through the corresponding ROADMAP row (the operator hand-edited ROADMAP 5× in one run) and its automatic queue-trim silently misses ids ending in `-followups` because it matches on directory basename rather than the resolved spec_dir / full queue id. The orphaned entry then trips the `queue.no-completed` gate, forcing a separate recovery cycle just to delete one JSON line. Both failures were hit twice in a single run.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/mark-complete-skips-roadmap-strike-and-followups-queue-trim
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy_core.py` (`__mark_complete__` apply-pseudo trim, basename vs resolved spec_dir); `user/skills/lazy-batch/SKILL.md` Step 1c.5.

---

## Verified Symptoms
1. **[OBSERVED in logs]** `queue_trimmed: false` recurs because the apply-pseudo trim matches dir-basename but `-followups` queue ids don't match — session `deb9f0cf` @ `2026-06-16T23:17:40Z`: "The `queue_trimmed: false` recurs (2nd time — the apply-pseudo trim matches dir-basename but `-followups` queue ids don't match; a harness gap worth hardening). Trimming the orphaned d7 entry via recovery to clear the `queue.no-completed` gate error."
2. **[OBSERVED in logs]** Operator hand-edited ROADMAP 5×; basename-vs-`-followups`-id mismatch forced 2 queue-trim recovery dispatches — session `deb9f0cf` orchestrator retro @ `2026-06-17T01:22:05Z`: "Fold ROADMAP-strike + `spec_dir`-based queue-trim into `--apply-pseudo __mark_complete__` — I hand-edited ROADMAP 5×, and the basename-vs-`-followups`-id mismatch forced 2 queue-trim recovery dispatches."

## Evidence Collected (from session logs)
- session `deb9f0cf` @ `2026-06-16T23:17:40Z`: "The `queue_trimmed: false` recurs (2nd time — the apply-pseudo trim matches dir-basename but `-followups` queue ids don't match; a harness gap worth hardening). Trimming the orphaned d7 entry via recovery to clear the `queue.no-completed` gate error." — the trim keys on directory basename (e.g. `snapshot-system`) which does not equal the queue id (`snapshot-system-followups`), so the entry is left in queue.json and the `queue.no-completed` gate errors; recovery deletes the orphaned entry by hand.
- session `deb9f0cf` orchestrator retro @ `2026-06-17T01:22:05Z`: "Fold ROADMAP-strike + `spec_dir`-based queue-trim into `--apply-pseudo __mark_complete__` — I hand-edited ROADMAP 5×, and the basename-vs-`-followups`-id mismatch forced 2 queue-trim recovery dispatches." — operator's own retro answer quantifies the friction: 5 manual ROADMAP strikes and 2 extra recovery dispatches for the queue-trim mismatch in one run; proposes folding ROADMAP-strike and spec_dir-based trim into the pseudo-action.

## Why this is friction
Completion is not actually fully automated: the operator must manually strike the ROADMAP row every time (5× in one run), and the auto queue-trim silently misses `-followups` ids because it compares basename instead of the resolved spec_dir / full queue id (basename `snapshot-system` ≠ id `snapshot-system-followups`). The orphaned entry trips the `queue.no-completed` gate, forcing a separate recovery cycle to delete a single JSON line. Both failures recurred within the same run.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Should `__mark_complete__` own the ROADMAP-strike, and how does it reliably locate the row to strike?
- What is the correct match key for the queue-trim — full queue id, resolved spec_dir, or something else — and does basename matching break for ids beyond the `-followups` suffix?
- Are there other queue-id shapes (besides `-followups`) where basename matching diverges from the queue id?
- Should the `queue.no-completed` gate distinguish a genuinely-orphaned entry from a trim-key mismatch?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
