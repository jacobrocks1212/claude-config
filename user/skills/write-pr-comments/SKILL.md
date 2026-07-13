---
name: write-pr-comments
description: Draft reviewer-authored informational comments for a GitHub PR — explaining non-obvious behavior, design decisions, and deletions to future readers (not change requests). Produces a staging markdown file for review before posting. Triggers on 'write pr comments', 'leave info comments on the PR', 'propose informational PR comments'.
argument-hint: "[optional: PR number or branch]"
---

# Write PR Comments

Use this skill when the user wants reviewer-authored **informational** comments for a GitHub PR: comments that explain non-obvious behavior, design decisions, and non-obvious deletions to future readers, rather than requesting changes. Produces a staging markdown file of proposed comments in the feature doc directory; the user reviews it before anything is posted.

## Trigger Phrases
- "write pr comments"
- "leave info comments on the PR"
- "propose informational PR comments"
- "explain the non-obvious changes on the PR"

## What This Skill Produces

A single markdown file (default name `PR_INFO_COMMENTS.md`) in the branch's feature doc directory, containing a list of proposed comments. Each comment:

- Is prefixed with `_Info:_ ` (unless the user specifies a different prefix).
- Explains **one** non-obvious thing at a **high level**: the *why*, not a line-by-line restatement of the *what*.
- Has an **anchor** naming the file, the **exact line number(s)** (against the branch HEAD version of the file), and the symbol/area it attaches to, so the user knows precisely where to drop it on the PR.
- Where test coverage is relevant, ends with a `Covered by <comma-delimited test classes/methods>` footer.

Do NOT use markdown blockquotes (`>`) anywhere in the file. Write the `_Info:_` comment and the `Covered by` footer as plain paragraphs. Blockquoting makes the text harder to copy cleanly into a GitHub comment box.

**Never use em dashes (`—`) in comment or footer text.** Use a comma, colon, parentheses, or two separate sentences instead. This applies to the prose you generate, not to file names or code identifiers (which are backticked anyway). En dashes in line-number ranges (e.g. `433-435`) use a hyphen, not an em dash.

This file is a staging doc. Do NOT post to GitHub unless the user explicitly asks, then use the `pull-request` skill / `gh`.

## What Deserves a Comment (and What Does Not)

Comment on:
- **Non-obvious deletions**: code removed or moved whose absence would puzzle a reader (e.g. an event that used to fire eagerly now fires from a different place based on outcome). Always explain where the behavior went and why.
- **Design decisions with a rationale that isn't visible in the diff**: fail-closed vs fail-open choices, accepted data loss, idempotency guarantees, tri-state return contracts, single-verdict-decided-once patterns.
- **Non-obvious behavior**: reflection-based type resolution, feature-flag-gated branches, "only for support users" carve-outs, pagination/filtering gotchas, recursion depth caps.
- **Cross-cutting counterparts**: where a write-side change has a matching read-side change elsewhere, point each at the other.

Do NOT comment on:
- Obvious, self-explanatory changes (renames, mechanical refactors, trivial additions).
- Anything that reads as review feedback ("consider renaming", "this could be simpler"); this skill is informational only.
- Code comments in the source itself. These are PR comments, and per repo convention source code is not commented.

Favor quality over quantity. A dense PR might warrant ~10 comments; a small one, 2-3.

## Process

### Step 1: Identify the PR, branch, and feature doc directory

- Resolve the current branch and the PR it backs (PR number from the feature docs, `WIP.md`/`REVIEWED.md`, or `gh pr view`).
- Infer the feature doc directory the same way `write-pr-description` does: a `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/<feature>/` directory referenced this session, or resolved from the branch. Read `SPEC.md`/`PHASES.md`/`PR_DESCRIPTION.md` there for context on intent so comments explain the *why* accurately.

### Step 2: Get the NET branch diff

Diff against the merge-base so only net changes are considered (added-then-deleted files correctly disappear):

```bash
MERGE_BASE=$(git merge-base main HEAD)
git diff --stat $MERGE_BASE..HEAD
git diff $MERGE_BASE..HEAD -- <production source files>
```

Read the production file diffs in full. Skim test and generated/snapshot files; they inform coverage footers but rarely warrant their own comment.

### Step 3: Draft one comment per non-obvious item

For each item that clears the bar in "What Deserves a Comment":
- Write a high-level explanation prefixed with `_Info:_ ` as a plain paragraph (no blockquote). Explain the *why* and the cross-file consequence; do not narrate the diff.
- Record an **anchor**: the file, the exact line number(s), and the symbol the comment attaches to. Get the exact line numbers from the branch HEAD version of the file, e.g. `git show HEAD:<file> | grep -nE "<symbol>"`. For a **deleted** line (which has no HEAD line), anchor to the surrounding HEAD context lines and say so (e.g. `File.cs:433-435`, the removed X, previously between Y and Z).
- Keep each comment to a few sentences. If it needs more, it is probably two comments.

### Step 4: Attach verified test-coverage footers

When a comment describes behavior that tests pin, append a footer:

`Covered by <comma-delimited test classes/methods>`

**Verify the names against the source; do not trust the PR description or memory.** Cognito test suites use **nested** `[TestClass]` classes, so the real reference is often `OuterClass.NestedClass.MethodName` (e.g. `CoreServiceTests.PurgeOrganization.PurgeOrganization_...`), not the flat method name. Confirm the enclosing class chain before writing the footer:

```bash
# Find the file and enclosing nested class for a test method
git grep -n "SomeTestMethodName" HEAD -- 'Cognito.UnitTests/*'
git show HEAD:<test-file> | grep -nE "public class .* :|public (async )?(void|Task) "
```

For frontend Jest specs, reference the spec file plus the `it(...)` descriptions in quotes.

### Step 5: Enforce backticks

All identifiers (file names, class names, method names, properties, event names, enum values, feature flags, test names) MUST be wrapped in backticks. Do not bold identifiers. Prose about behavior stays plain text, and per the produce-spec above it never uses em dashes.

### Step 6: Write the staging file

- Write `PR_INFO_COMMENTS.md` into the feature doc directory (update in place if it already exists). Lead with a one-paragraph header naming the PR (`PR #<n>`) and stating these are proposed, un-posted, informational comments grouped by file.
- Group entries by file, each with a bold **Anchor:** line (including exact line numbers), the plain-paragraph `_Info:_` comment, and the coverage footer. No blockquotes.
- Note in the file's header paragraph that line numbers are against the branch HEAD version of the files.
- If no feature doc directory can be inferred, do NOT write a file. Return the content in a single fenced code block for copy-paste (use a four-backtick outer fence since entries contain backticks).
- Tell the user the path written, and offer to post the comments to the PR (via the `pull-request` skill / `gh`) as a separate, explicit step.

### Step 7: Validate before delivering

- Every comment prefixed with `_Info:_ ` (or the user's chosen prefix), written as a plain paragraph with no blockquote (`>`).
- Every comment explains non-obvious *why*, not obvious *what*; no review-feedback phrasing.
- No em dashes (`—`) anywhere in the generated comment or footer text.
- Every anchor names a real file, exact line number(s) against HEAD, and a locatable symbol.
- Every coverage footer's class/method chain verified against source, including nested test classes.
- All identifiers in backticks; no source-code comments proposed.
