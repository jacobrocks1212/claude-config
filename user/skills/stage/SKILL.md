---
description: Stage uncommitted work in logical partitions, one at a time, waiting for the user to commit between each
argument-hint: ""
allowed-tools: ["Bash", "Read", "Grep", "Glob", "AskUserQuestion"]
name: stage
---

# Stage

Split the working tree into logical commit-sized partitions and stage them **one at a time**. After each partition is staged, summarize it, propose a commit message, and wait for the user to commit before moving on.

**Never commit. Never push. Never discard work.** This command only stages.

---

## 1. Survey uncommitted work

Run in parallel:
- `git status --short`
- `git diff --stat HEAD`
- `git log --oneline -10` — match the repo's existing commit-message style (e.g. if the repo doesn't use conventional-commits prefixes, neither should you)
- `git diff HEAD` (only if the diff is small enough to be useful; otherwise sample it)

If the tree is clean, say so and stop.

## 2. Identify partitions from session context

Scan earlier turns in this conversation for natural partition boundaries. Strong signals:
- Plan-file "Work Units" (Unit A, Unit B, …)
- PR comments #1, #2, … each producing separate groups of edits
- A "primary task + follow-up" structure (e.g. "fix the code, then update the review rules")
- Distinct unrelated fixes in the same session
- User statements like "do these together" or "these are separate things"

Translate the signals into partition proposals. Each partition = one future commit.

## 3. Decide the partition plan

Pick one path:

- **Single partition** — small, single-topic work, or obvious atomic change. Proceed.
- **Obvious partitions from context** — use them. Announce the partitions and the order you picked (see §4).
- **Large or ambiguous** — use `AskUserQuestion` with 2–4 partitioning options before staging anything. Do not guess.

## 4. Choose an order

Order partitions so each commit is self-consistent and reviewable. Rules of thumb:
- Pure deletions/cleanup first when they clear the path
- Shared-type / backend changes before consumers that depend on them
- Code changes before tests that prove them (unless writing tests-first)
- In-repo code changes before out-of-repo side effects (e.g. plugin/skill updates in `~/.claude/`)

State the chosen order in one sentence before staging.

## 5. Stage partition N

Before staging:
- `git reset` (unstage anything previously staged, so we start from a known-clean index)

For each file belonging entirely to this partition:
- Modified/added: `git add <path>`
- Deleted: `git add -u <path>` (or `git rm --cached <path>` for files removed from disk)
- Untracked new file in partition: `git add <path>`

For files that span multiple partitions (one file, hunks belong to different commits):

### Preferred: `git add -p` with piped answers

`git add -p <path>` walks each hunk and reads `y`/`n`/`s`/`q` from stdin. When stdin is a pipe, git never prompts or opens an editor — it just reads your answers in order. Git does the patching internally, so **line endings are preserved exactly** (no CRLF/LF drift, which is what bites hand-crafted `git apply` patches on Windows).

Workflow:
1. Count hunks: `git diff <path> | grep -c "^@@"`
2. Inspect `git diff <path>` and decide for each hunk (top to bottom): `y` (accept), `n` (skip), or `s` (split into smaller hunks, then answer each sub-hunk)
3. Pipe the answer string:

   ```bash
   # Example: 3 hunks, accept #1 and #3, skip #2
   printf 'y\nn\ny\n' | git add -p <path>

   # Example: 2 hunks, split the first into two sub-hunks, accept only the second sub-hunk
   printf 's\nn\ny\nn\n' | git add -p <path>
   ```
4. Verify: `git diff --cached <path>` shows what landed; `git diff <path>` shows what's left.

**Tip:** Git may refuse to split a hunk if the changes are interleaved too tightly. If `s` produces a message like "Sorry, cannot split this hunk", fall back to the edit-file workaround below.

### Fallback: edit-stage-restore

When `git add -p` can't split a hunk cleanly (interleaved changes within a few lines of each other):
1. Use the Edit tool to **temporarily revert** the hunks belonging to *other* partitions, leaving only the current partition's changes in the working tree
2. `git add <path>` — stages the whole file, which now contains only this partition's changes. Line endings are preserved because the Edit tool is byte-faithful.
3. Use the Edit tool to **restore** the other partitions' changes back to the working tree for later staging

This costs two extra edits per cross-partition file but is 100% reliable.

### Last resort: stop and ask

If both approaches look unsafe (e.g. a hunk contains deeply interleaved logic from two partitions that share the same few lines), **stop and ask the user** to stage those specific hunks themselves in VS Code. Give the file path and a short description of which lines/logic belong to this partition. Do not guess.

### Never

Do not construct a patch with a heredoc/printf and apply it via `git apply --cached`. On Windows repos with CRLF files, heredoc introduces LF line endings, and the index ends up with mixed line endings vs. the working tree — producing a spurious whitespace diff that won't clear until the working tree is touched.

After staging, verify:
- `git diff --cached --stat` — shows what's in the index
- `git diff --stat` — shows what's left for future partitions

## 6. Summarize the partition

Output format (keep tight):

```
## Partition N of M — <short title>

**Addresses:** <1 sentence — what problem/ask this solves>
**Approach:** <1–2 sentences — how the changes solve it>

**Staged:**
- path/to/file — <one-line change description>
- path/to/other — <one-line change description>

**Proposed commit message:**

    <short, active-voice message matching the repo's style>

Only the changes above are staged. Run `git commit` (or `/commit`) when ready, then tell me to continue.
```

**Commit message rules:**
- Active voice, imperative mood ("Add X", "Fix Y", not "Added X")
- Short — aim for ≤ 70 chars on the first line
- Match the repo's observed style from `git log --oneline -10` (no `feat:`/`chore:` prefixes unless the repo uses them)
- No AI/Claude/automation attribution
- No trailing period
- Be specific ("Fix NRE in FormBuilderController" beats "Fix bug")

## 7. Wait

Stop. Do not proceed until the user signals they've committed — e.g. they say "next", "continue", "committed", or you can re-verify via `git log -1` / `git status` that the partition is gone from the working tree.

When resuming:
- `git status --short` — confirm what's left
- If anything unexpected is staged, reset the index before staging the next partition

## 8. Repeat

Continue until `git status --short` is empty. Then output a one-line confirmation:

```
All partitions staged and committed. Working tree clean.
```

---

## Hard rules

- **Stage only — never `git commit`**, never `git push`, never `--force`.
- **Never use `git reset --hard`, `git clean`, `git checkout --`, `git restore --source`** or any command that discards working-tree changes.
- **Never bypass hooks** (`--no-verify`, `--no-gpg-sign`) unless the user explicitly asks.
- **If unsure about a partition boundary, ask.** A misfiled commit is worse than a 30-second clarification.
- **Prefer whole-file staging** — partial-file staging is error-prone and should be a last resort.

## Output style

- No running commentary on git commands. State the plan, stage, summarize, wait.
- Match the repo's commit-message vocabulary (look at `git log --oneline -10`).
- If you see an in-session plan file (`.claude/plans/*.md` or `PHASES.md`), reference its work-unit names in partition titles when they map cleanly.
