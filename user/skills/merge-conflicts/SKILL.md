---
name: merge-conflicts
description: Analyze in-progress merge conflicts and advise on resolution
---

# Merge Conflicts

A merge is already in progress with unresolved conflicts. Analyze every conflict, advise on resolution strategy, then apply fixes after the user picks sides.

---

## Step 1: Surface the Conflicts

List all conflicted files:

```
git diff --name-only --diff-filter=U
```

Then locate every conflict marker with line numbers:

```
git diff --check HEAD
```

---

## Step 2: Detect Whole-File Whitespace Reformats

For any file where the conflict spans most or all of the file (e.g., a single `<<<<<<<`/`>>>>>>>` block covering thousands of lines), check whether the diff is primarily whitespace:

```
git diff --stat -w <merge-base> HEAD -- <file>
git diff --stat -w <merge-base> main -- <file>
```

If `-w` reduces a 4000+ line diff to a handful of real changes, call it out: "This file was whitespace-reformatted on main. Only N lines are real changes." Then use `git diff -w` output to identify the actual semantic differences on each side — don't waste time reading the raw conflict.

---

## Step 3: Analyze Each Conflict

For every conflicted file, read the region around each conflict marker set (`<<<<<<<` / `=======` / `>>>>>>>`). For each conflict, determine:

1. **What ours (HEAD) changed** — the intent of the current branch's version
2. **What theirs (merging branch) changed** — the intent of the incoming version
3. **Whether they overlap** — is this a true semantic conflict or a textual collision?

Classify each conflict as one of:

| Resolution | When |
|---|---|
| **Take ours** | The incoming change is stale, reverted, or irrelevant to this branch's work |
| **Take theirs** | The current branch didn't intentionally modify this area; theirs is strictly newer |
| **Combination** | Both sides made meaningful changes that need to coexist — specify which side is closer and what needs adding back |

---

## Step 4: Identify Common Patterns and Present the Plan

Before presenting per-conflict advice, look for a shared pattern across conflicts. Common patterns:

- **Refactor vs. feature addition** — one side restructured/renamed existing code, the other added new functionality. Resolution: take the refactor as base, patch back the feature additions.
- **Two independent features** — both sides added new constructor params, new methods, new imports. Resolution: take either side, add back the other's additions.
- **Formatting + real changes** — one side reformatted (whitespace, import ordering), the other made semantic changes. Resolution: take the formatted side, patch back semantic changes.

When all (or most) conflicts share the same pattern, present a **single batch recommendation**:

> "All N conflicts follow the same pattern: [description]. Recommendation: accept [side] for all files, then I'll patch back [what's missing]."

This avoids the user making N identical decisions. Only itemize individual conflicts when they genuinely differ.

For each conflicted file, report:

- File path and number of conflict regions
- For each conflict: the classification (ours / theirs / combination) and a one-sentence rationale
- For **combination** conflicts: which side to accept as the base, and exactly what logic to add back

Wait for user confirmation before proceeding.

---

## Step 5: User Resolves Markers

The user picks a side for each conflict in their editor (or uses `git checkout --ours`/`--theirs` per file). They tell you which side they accepted.

If the user accepted the "closer" side for combination conflicts, proceed to Step 6. If they deviated, re-assess what needs patching.

---

## Step 6: Patch Combination Conflicts

For each combination conflict where the user accepted one side:

1. Read the file's current state (post-resolution, pre-stage)
2. Apply targeted edits to add back the missing logic from the other side
3. Verify no conflict markers remain: `git diff --check HEAD`

---

## Step 7: Verify

1. Confirm zero remaining conflict markers across all files
2. If the project has a build command, run it to catch compile errors introduced by the merge
3. Report the final state to the user — they can stage and commit when ready
