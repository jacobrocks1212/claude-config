## Dirty Tree Check (MANDATORY PREREQUISITE — BEFORE PLAN MODE)

Before entering plan mode or starting any implementation work, verify the working tree is clean. A dirty tree causes noise in quality gates, contaminates diffs, and makes it impossible to attribute failures to your changes.

### Protocol

1. Run `git status --porcelain` to check for uncommitted changes.
2. If output is empty → working tree is clean. Proceed to the next step.
3. If output is non-empty → dirty tree detected. Execute the cleanup sequence below.

### Cleanup Sequence

1. **Announce:** Print "Dirty tree detected — committing existing changes before starting phased work."
2. **Run `git diff --stat`** to understand the scope of uncommitted changes.
3. **Stage all modified/untracked files:** `git add -A` (this is an exception to the "specific files" rule — we're checkpointing unknown prior work, not our own changes).
4. **Commit** with message: `chore: checkpoint uncommitted changes before phased implementation`
5. **Determine push eligibility:** Run `git config user.email`
   - If `jacob@cognitoforms.com` → do NOT push (work repo — hook blocks it)
   - Otherwise → `git push origin main`
6. **Run quality gates** to establish a clean baseline:
   - Run the project's quality gates (see the quality-gates component or project CLAUDE.md for commands)
7. **Evaluate QG results:**
   - All pass → proceed to plan mode. The baseline is clean.
   - Failures detected → these are **pre-existing failures** from the checkpointed work. Print a warning:
     ```
     ⚠️ Pre-existing QG failures detected in checkpointed changes:
     [list failing gates]
     These failures exist BEFORE our work begins. Proceeding — but be aware
     that QG results during implementation may include these pre-existing issues.
     ```
   - Proceed regardless — the checkpoint commit establishes the boundary between "their mess" and "our work."
