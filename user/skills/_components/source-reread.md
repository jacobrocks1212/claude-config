## Re-read Source Documents (MANDATORY — DO NOT SKIP)

Before launching any subagent in this batch, the orchestrating agent must re-read from disk:

1. **The current phase's section in PHASES.md** (deliverables, prerequisites, testing strategy, integration notes) — the file may have been updated by prior batches in this same phase
2. **All prior phases' Implementation Notes** in the same PHASES.md (patterns, imports, gotchas, actual file paths that may differ from the plan)
3. **The relevant sections of SPEC.md** that this phase implements (as listed in the per-phase plan's "SPEC.md references" field)

This re-read is required because the context window may have been compacted since the plan was drafted. The orchestrating agent must have fresh, accurate content before composing subagent prompts.

**Do NOT rely on cached/remembered content — read the files.**

4. **The plan file** (if this is an `/implement-phase-batch` execution) — re-read the current phase's section from the plan file at `~/.claude-personal/plans/`. After compaction, your awareness of the plan's execution model, mandatory rules, and batch structure may be stale. If you cannot recall which batch you're on or what the plan's constraints are, re-read the full plan header + current phase section.
