---
name: explain
description: "Interactively teach a set of code changes — walk them chunk-by-chunk explaining what changed and why, with Socratic prompts. Use when asked to explain/walk through a diff, PR, commit range, or local changes."
argument-hint: "[nothing=working tree | <commit> | <range e.g. main..HEAD> | <path>]"
plan-mode: never
allowed-tools: ["Bash", "Read", "Glob", "Grep", "AskUserQuestion"]
---

# /explain — Teach Me These Changes

Interactively walk a set of code changes the way a senior engineer would explain
them in person: group the changes into logical chunks, teach what changed and why
each chunk matters, and prompt you to reason about it — without dumping raw diff.

This is the teaching mechanic from `cognito-pr-review`'s buddy review, generalized
to any repo and language and stripped of the review-specific verdict/synthesis
machinery. It explains; it does not produce a review document.

**Arguments:** "$ARGUMENTS"

---

## Step 1 — Resolve the Change Set

Determine what to explain from the argument. Resolve in this order:

1. **No argument (or `local`/`.`)** — the working-tree changes. Get them with
   `git diff HEAD` (staged + unstaged tracked changes). If that is empty, fall back
   to the last commit: `git show HEAD`. Mention which one you used.
2. **A commit range** (contains `..`, e.g. `main..HEAD`, `HEAD~3..HEAD`) — `git diff <range>`.
3. **A single commit-ish** (SHA, tag, or branch name that resolves) — `git show <ref>`.
4. **A path** (file or directory that exists) — explain the working-tree changes
   limited to that path (`git diff HEAD -- <path>`). If there are no changes there,
   explain the *existing* code at that path as a walkthrough of how it works.

If the argument is ambiguous or resolves to nothing, ask the user what they want to
explain before proceeding — don't guess.

Read the resolved diff plus enough surrounding context (adjacent files, callers,
definitions) to explain the changes accurately. If a `{goal}` is available — a PR
title, the commit message(s), or a task description the user gave — capture it; it
grounds the "why it matters" framing in the walkthrough.

## Step 2 — Walk the Changes

Drive the walkthrough using the protocol below with **`{pacing}` = continuous**:
present the chunk plan first, then teach **every** chunk in one pass — what changed,
why it matters, how the author approached it, and the open Socratic questions for
each. Do **not** stop and wait for the user to ask for the next chunk; the single
response covers the full change set end to end (chunk plan → all chunks → closing).
The user can follow up afterward to dig into any chunk.

!`cat ~/.claude/skills/_components/change-walkthrough.md`

---

## Notes

- This skill is **read-only** — it teaches, it never edits code or writes artifacts.
- For teaching a whole *system or topic* (not a specific diff), use `/teach` instead,
  which researches the area and produces a written reference document.
- Works in any repo. When the surrounding codebase is unfamiliar, read what you need
  to ground the explanation — but stay focused on the change set the user asked about.

## Usage Examples

```
/explain                     # walk my current uncommitted changes
/explain main..HEAD          # walk everything on this branch vs main
/explain HEAD                # walk the last commit
/explain a1b2c3d             # walk a specific commit
/explain src/auth/           # walk changes under src/auth/ (or that code, if unchanged)
```
