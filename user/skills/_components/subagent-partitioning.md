## Partition into Subagent Work Units (MANDATORY — DO NOT SKIP)

### What is a Work Unit?

A work unit is **one logical boundary** — one cohesive deliverable, one concern, one function/class/module that makes sense as a standalone assignment. A subagent receives exactly one work unit.

### Sizing Rules

1. **Default: 1 deliverable = 1 work unit.** Start here. Every PHASES.md checkbox item (or distinct fix concern) is its own work unit unless rule 2 applies.
2. **Merge only when tightly coupled:** Two deliverables may share a work unit ONLY when they are mutually dependent — implementing one without the other produces broken or untestable code (e.g., a type definition and its single consumer written in the same file). Maximum 2-3 deliverables per work unit, and only under this condition.
3. **Never merge for convenience.** Sharing a file, being "related", or being "small" are NOT reasons to merge deliverables into one work unit. A 10-line work unit is fine.
4. **When unsure, split.** Granularity is always safer than aggregation. Two small agents that each do one thing well outperform one large agent trying to do two things.

### File-Overlap Rule

**No two work units in the same batch may modify the same file.** When work units overlap on files:

1. **Do NOT merge them into a single larger work unit.** Each work unit keeps its own scope and identity.
2. **Place overlapping work units in separate sequential batches.** The first batch completes and passes review before the next begins.
3. **Order by dependency:** If WU-B depends on WU-A's output, WU-A goes in an earlier batch. If no dependency exists, order by complexity (simpler first — it establishes the file's baseline for the next agent).

This means more sequential batches. That is intentional — each batch boundary is a review gate (via `subagent-review.md`), which catches mistakes before they compound.

### Partitioning Algorithm

Apply these steps in order:

1. **List deliverables.** Extract every unchecked deliverable (`- [ ]`) from the target phase (or every file/concern from the fix analysis).
2. **Assign one work unit per deliverable.** Label them WU-1, WU-2, etc.
3. **Check for tight coupling.** For each pair of adjacent work units: can WU-A be implemented and tested without WU-B? If yes, keep them separate. If no (mutual dependency, single-file co-creation where splitting is impossible), merge into one work unit. Document the coupling reason.
4. **Map files.** For each work unit, list every file it will create or modify.
5. **Detect overlaps.** Build a file-to-work-unit index. Any file claimed by 2+ work units is an overlap.
6. **Assign batches.** Place all non-overlapping work units in Batch 1. For each overlap: move the later-dependency (or more complex) work unit to Batch 2. Repeat overlap detection within Batch 2 — push further conflicts to Batch 3, etc.
7. **Verify.** Confirm: (a) no two work units in the same batch share a file, (b) no work unit exceeds 3 deliverables, (c) the default is 1 deliverable per work unit.

### Anti-Patterns (NEVER do these)

- Bundling 4+ deliverables into one "mega work unit" because they touch related files
- Merging work units to "reduce the number of batches" — more batches with review gates is the goal
- Creating a work unit scoped to "all remaining deliverables" or "everything else"
- Letting a single subagent modify 5+ files across unrelated concerns
