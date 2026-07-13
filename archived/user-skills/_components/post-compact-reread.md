## Post-Compaction Plan Re-Read

Context compaction evicts plan details from your working memory. After compaction, you may proceed on stale or incomplete information — leading to drift from the plan.

### Rule

**On every batch boundary (Step B.0), re-read the plan file if one exists.** Do NOT rely on memory of the plan — compaction may have occurred between batches without explicit notification.

### How to re-read

1. Check if a plan file path was established earlier in the session (typically in `~/.claude-personal/plans/`)
2. If found, `Read` the plan file — focus on:
   - The **Execution Schedule** (which phase/batch is next)
   - The **current phase's Per-Phase Plan** (work units, batch overview, file paths)
   - Any **Mandatory Rules** or **Execution Model** constraints
3. Cross-reference with Implementation Notes (apply sibling-then-embedded: check `IMPLEMENTATION_NOTES.md` sibling of PHASES.md first; fall back to embedded notes in PHASES.md — notes take priority over the plan where they diverge)

### Automatic safety net

A `SessionStart` hook with `compact` matcher is configured to auto-inject the plan file header after compaction. However, this only provides the first ~200 lines. For large plans, you MUST still re-read the relevant sections manually.

### Signs you've drifted from the plan

- You're unsure which batch comes next
- You're improvising file paths not mentioned in the plan
- You're skipping steps (review, QG, PHASES.md update)
- You can't recall the Execution Model constraints (no inline Edit/Write on source files)

If any of these are true: STOP. Re-read the plan. Resume from the correct position.
