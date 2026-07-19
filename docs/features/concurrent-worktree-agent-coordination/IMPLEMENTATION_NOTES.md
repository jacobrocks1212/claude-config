# Concurrent Multi-Agent Worktree Coordination — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Awareness injection + reconcile "One writer per file"

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-18
**Work completed:**
- Chose the canonical awareness phrase (WU-1, reused verbatim everywhere else): "other agents may be working this same worktree/branch concurrently — an unexpected commit / moved HEAD is expected, not a defect. Genuine write contention is resolved by the coordination layer (git safety + the FIFO file-lock + conflict-routing) — not by halting." Taken directly from SPEC Requirement 1's canonical wording.
- Injected the note into `cycle-base-prompt.md`'s turn-end sections (both `modes=workstation` and `modes=cloud` variants), placed right after the R5 ATOMIC GATE+COMMIT item (per the plan's "R5 chain region" pointer) as an unnumbered paragraph so the existing numbered turn-end checklist (items 1/2/3) stayed intact.
- Added a new HARD CONSTRAINT (`/lazy-batch` #11, `/lazy-batch-parallel` P8, `/lazy-batch-cloud` #12) plus an appended sentence on the existing sub-subagent/lane dispatch-policy prose in each of `lazy-batch/SKILL.md`, `lazy-batch-parallel/SKILL.md`, and the AlgoBooth mirror `lazy-batch-cloud/SKILL.md`. `lazy-cloud/SKILL.md` (a thin single-item wrapper with no HARD CONSTRAINTS/dispatch-policy block) got the note as a new paragraph beside its existing `HARD REQUIREMENT` bullets.
- Reconciled `user/CLAUDE.md`'s `<orchestration>` "One writer per file" block: re-scoped the existing rule to "within a run you control" and added a new paragraph carving out sanctioned concurrent writers outside that tree (parallel lanes, a second session, a background harden), pointing at the coordination layer as arbiter instead of treating an unexpected commit/moved HEAD as a defect.
**Integration notes:**
- The canonical phrase is grep-anchored (`an unexpected commit / moved HEAD is expected`) in all 6 injection points named by the Deliverables list — verified via a single `grep -rl` across all 6 files before ticking checkboxes.
- Phase 6 (R7 — retiring `self_edit_mode` foreground-await defensiveness) will cite this phrase as the documented trust contract; do not reword it there — extend the surrounding prose instead.
**Pitfalls & guidance:**
- `lazy-batch-parallel/SKILL.md`'s Step 3 preamble sentence ends with a colon introducing a numbered list (`... unaffected):` → `1. **Probe:** ...`). Inserting a new sentence before that colon requires re-homing the colon onto the new final sentence, not leaving a stray `.:`. Caught and fixed during this batch — re-read the surrounding numbered-list-intro punctuation before finalizing an insert like this in list-generating prose.
- `lazy-batch-cloud/SKILL.md`'s HARD CONSTRAINTS preamble ("Constraints 1-9 mirror /lazy-batch's HARD CONSTRAINTS 1-9; constraint 10 is cloud-only") was already stale before this batch (constraint 11 existed undocumented); the new constraint 12 is consistent with that pre-existing gap and was left as-is (out of this phase's scope).
- This feature's `PHASES.md` template has no per-phase `**Status:**` line (unlike some other features' PHASES.md); left that convention alone rather than introducing a new field shape only for Phase 1.
**Files modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — awareness note in both turn-end variants.
- `user/skills/lazy-batch/SKILL.md` — new HARD CONSTRAINT 11 + dispatch-policy paragraph appendix.
- `user/skills/lazy-batch-parallel/SKILL.md` — new HARD CONSTRAINT P8 + Step 3 lane-loop paragraph appendix.
- `user/CLAUDE.md` — `<orchestration>` "One writer per file" reconciliation.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — new HARD CONSTRAINT 12 + Cloud-specific paragraph appendix.
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — new paragraph beside the HARD REQUIREMENT list.
- `docs/features/concurrent-worktree-agent-coordination/PHASES.md` — Phase 1 deliverables ticked.
- `docs/features/concurrent-worktree-agent-coordination/plans/all-phases-concurrent-worktree-agent-coordination-part-1.md` — WU-1..4 checkboxes ticked, frontmatter flipped to `Complete`.
