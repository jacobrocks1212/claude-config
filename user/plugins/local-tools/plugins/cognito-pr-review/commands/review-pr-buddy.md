---
description: "Interactive senior-architect pair-review: walk a PR chunk-by-chunk over the review pipeline"
argument-hint: "[PR_ID | local] [aspects: all|csharp|frontend|api|consistency|testing] [sequential]"
allowed-tools: ["Agent", "Bash", "Read", "Write", "Glob", "Grep", "AskUserQuestion"]
---

# Cognito PR Review — Buddy Mode

An interactive, senior-architect pair-review command. Unlike the autonomous `/review-pr`, this command walks you through the PR's review guide chunk-by-chunk — teaching what changed, surfacing pre-computed findings, prompting you to reason, and capturing your dispositions — then produces a curated review document reflecting only what _you_ decided matters.

**Arguments:** "$ARGUMENTS"

**Plugin root:** `~/.claude/plugins/local-tools/plugins/cognito-pr-review`

---

## Overview

Three phases:

1. **Phase 0 — Non-interactive prep.** Delegates entirely to `commands/review-pr.md` Steps 1–8. Produces the journey file and `{cacheDir}/processed-findings.json` (including reuse findings) without involving you.
2. **Phase 1 — Interactive walk.** Steps through every `### Step N: {Group}` chunk in the journey file's `## Manual Review Guide`, teaching you what changed, surfacing findings from `processed-findings.json`, asking Socratic questions, and capturing your verdict on each finding via `AskUserQuestion`. Progress is checkpointed continuously to `{cacheDir}/buddy-session.json`.
3. **Phase 2 — Curated synthesis.** Writes the final `PR-{id}.md` review in synthesizer-v2 format containing _only_ the findings you kept, your own observations, and your will-comment notes. The autonomous synthesizer agent is NOT invoked — the interactive session IS the synthesis.

---

## Argument Parsing

Parse arguments exactly as `commands/review-pr.md` specifies:

- **PR_ID**: First numeric token → PR Mode (e.g. `17890`)
- **No PR ID / "local"**: Local Mode
- **aspects**: `all`, `csharp`, `frontend`, `api`, `consistency`, `testing` — defaults to `all`
- **sequential**: If present, pipeline agents run sequentially instead of in parallel
- **--local**: Force local mode
- **--base <branch>**: Target branch for local diff (default: `main`)
- **--include-untracked**: Include untracked files in local mode

Derive `cacheDir`:
- PR Mode: `.claude/pr-cache/{pr_id}/`
- Local Mode: `.claude/pr-cache/local/`

---

## Phase 0 — Non-Interactive Prep (Delegation)

Execute the steps defined in `commands/review-pr.md` Step 1 through Step 8 — prep → cache marker → cog-docs dest → journey → triage → planner-validate → reuse-candidacy + investigation + sweep → aggregate → post-process. Do not re-specify them here; `commands/review-pr.md` is the single source of truth for those step bodies.

On successful completion of Step 8:
- The journey file is at `.claude.local/reviews/PR-{pr_id}-journey.md` (or `-journey.md` for local mode)
- `{cacheDir}/processed-findings.json` is on disk, including `source:"reuse"` findings from Step 5b

Announce to the reviewer:

> "Prep complete. Journey file and processed findings are ready. Starting the interactive walk now."

Initialize Task-tool tracking for the three high-level phases:
- Phase 0 (complete)
- Phase 1 (in-progress)
- Phase 2 (pending)

---

## Phase 1 — Interactive Walk Along the Manual Review Guide

### Setup

Read the journey file (`.claude.local/reviews/PR-{pr_id}-journey.md`) and locate the `## Manual Review Guide` section. Extract every `### Step N: {Group Name}` chunk — each chunk has `**Files:**`, `**What to look for:**`, and `**Key questions:**`.

Read `{cacheDir}/processed-findings.json` into memory. Findings carry a `file` field; a finding belongs to a chunk if its `file` appears in that chunk's `**Files:**` list.

Initialize `{cacheDir}/buddy-session.json` (see schema below). If the file already exists (compaction recovery — see below), read it and resume from the first chunk whose `"status"` is not `"done"`.

### Per-Chunk Loop

For each chunk, in order, run these six steps:

#### 1. Teach

Provide a senior-architect explanation of what changed in this chunk, why it matters relative to the journey Objective, and how the author approached it. Ground the explanation in the cached diff and journey context — do NOT dump the raw diff at the reviewer. Aim for the tone of a peer explaining it over the shoulder: concise, insightful, contextual.

#### 2. Surface Findings

From `processed-findings.json`, collect findings whose `file` is in this chunk's `**Files:**` list. Present them grouped by source:

- **Investigation findings** (`source:"investigation"`) — bugs, edge cases, correctness issues
- **Sweep rule hits** (`source:"sweep"`) — pattern violations, rule matches
- **Reuse & duplication flags** (`source:"reuse"`) — verdict (e.g. `refactor`, `extend`, `wrap`, `acceptable-new`), existing-system candidate, suggested action
- **Intra-file reuse & consistency** (`source:"intrafile"`) — verdict (`refactor`/`reuse` for in-file duplication, `inconsistent` for surrounding-code divergence), in-file `file:line`/symbol candidate, suggested action

Highlight important and blocking findings. Do not bury them in a flat list.

If no findings exist for this chunk, state that explicitly: "No pre-computed findings for this group."

#### 3. Socratic Prompt

Pose the chunk's journey `**Key questions:**` verbatim, then add 1–2 additional questions of your own as a senior architect. Invite the reviewer to reason through the chunk before reaching their verdict. Do not answer the questions — prompt for the reviewer's thinking.

#### 4. Capture Verdict

Use `AskUserQuestion` to ask the reviewer to disposition each surfaced finding. Present the options clearly:

```
For each finding, choose:
  keep          — include in the final review as-is
  dismiss       — drop it (optional: add a note explaining why)
  will-comment  — include in final review as a PR comment note
  add-own       — skip this finding; I have my own observation to record instead
```

If there are no pre-computed findings for this chunk, use `AskUserQuestion` to ask whether the reviewer wants to add their own observation before continuing.

When the reviewer uses `add-own`, prompt for: file path, optional line number, and their observation text.

#### 5. Checkpoint

Write (or update) `{cacheDir}/buddy-session.json` with this chunk's completed dispositions and status `"done"`. See schema below.

#### 6. Advance

Announce the chunk is complete and move to the next one.

### Interruption Handling

At any point in the walk, the reviewer may:

- **Ask to dig deeper** into a file or concept — answer using cached context and your architectural knowledge
- **Request to open a local file** — this is an investigation-style carve-out: you may read the local codebase on the `main` branch (not the PR branch) to provide context, just as the investigation agent does. This is NOT sweep's cache-only restriction. State this explicitly: "Reading from the local codebase on `main` for context — this is not the PR branch state."
- **Revisit a prior chunk** — re-open that chunk's session state, present its dispositions, and allow the reviewer to change verdicts. Update `buddy-session.json` accordingly.

### Compaction Recovery

On session start, before looping, check whether `{cacheDir}/buddy-session.json` already exists. If it does:

1. Read it and find the first chunk whose `"status"` is not `"done"`.
2. Resume the walk from that chunk — do not re-run completed chunks.
3. Announce: "Resuming buddy session at chunk {n} of {total}: '{group name}'."

If all chunks are `"done"`, skip to Phase 2.

### `buddy-session.json` Schema

```json
{
	"pr_id": "<id or 'local'>",
	"cache_dir": "<path>",
	"phase": "0|1|2",
	"current_chunk_index": 0,
	"total_chunks": 0,
	"chunks": [
		{
			"index": 0,
			"group": "<journey step name>",
			"status": "pending|in-progress|done",
			"dispositions": [
				{
					"finding_ref": "<file:line or id>",
					"verdict": "keep|dismiss|will-comment|add-own",
					"note": "<optional>"
				}
			]
		}
	],
	"added_observations": [
		{
			"file": "<file path>",
			"line": 0,
			"note": "<reviewer's own observation>"
		}
	]
}
```

Write this file after every chunk completes. This is the recovery anchor for compaction or session interruption.

---

## Phase 2 — Human-Curated Synthesis

When all chunks are complete (all `"status": "done"`), update the Task tracker: Phase 1 complete, Phase 2 in-progress.

### Collect Curated Content

From `buddy-session.json`:

- **Kept findings** (`verdict: "keep"`) — include in the final review
- **Will-comment findings** (`verdict: "will-comment"`) — include in the final review with a "Comment" label
- **Add-own observations** from `added_observations[]` — include as reviewer-authored findings
- **Dismissed findings** (`verdict: "dismiss"`) — EXCLUDED from the final review

Do NOT invoke the `synthesizer-v2` agent. The interactive session IS the synthesis step. You (the orchestrating agent) write the review directly from the curated content above.

### Review Document Format

Produce the review document following the exact synthesizer-v2 output format defined in `agents/synthesizer-v2.md` — same header, same section names. The `## Reuse & Duplication` section uses that exact name and lists kept `source:"reuse"` findings. The `## Intra-File Consistency` section uses that exact name and lists kept `source:"intrafile"` findings. Omit sections that have no content (e.g. omit `## Re-Review Status` for initial reviews, omit `## Reuse & Duplication` if no reuse findings were kept, omit `## Intra-File Consistency` if no intra-file findings were kept).

Header:

```markdown
# Cognito PR Review — PR #{id}: {title}

**Author:** {author}
**Branch:** {source} → {target}
**Date:** {date}
**Review type:** {Initial | Re-review (iteration {n})}
```

Sections: Summary, Requirements Coverage, Critical Findings, Rule-Based Findings, Reuse & Duplication, Intra-File Consistency, Re-Review Status (re-review only), Strengths.

The Summary section should reflect the reviewer's overall assessment as shaped by the interactive session — note what was kept, what was dismissed, and the reviewer's own observations.

### Write Review Artifact

Read `{cacheDir}/pr-context.json` and check the `cogDocsItemDir` field — mirror the write logic from `commands/review-pr.md` Step 10 exactly:

**PR Mode — cogDocsItemDir non-null:**
- Write `<cogDocsItemDir>/PR-{pr_id}.md`
- Write `<cogDocsItemDir>/PR-{pr_id}-journey.md` (copy/finalize from `.claude.local/reviews/`)

**PR Mode — cogDocsItemDir null:**
- Write `.claude.local/reviews/PR-{pr_id}.md`
- Write `.claude.local/reviews/PR-{pr_id}-journey.md`

**Local Mode:** Write `.claude.local/reviews/LOCAL-{branch}-{timestamp}.md`

### REVIEWED.md Sentinel

Mirror the sentinel behavior from `commands/review-pr.md` Step 12.6 exactly.

If `cogDocsItemDir` is non-null, write `<cogDocsItemDir>/REVIEWED.md` with YAML frontmatter carrying PR identity, today's date, and the finding counts from the curated review (total kept + add-own, per-tier counts from the synthesized sections). Follow the frontmatter with a one-line human-readable body.

Use the same template as Step 12.6:

```bash
cat > "<cogDocsItemDir>/REVIEWED.md" << 'EOF'
---
kind: reviewed
pr: {pr_id}
date: "{YYYY-MM-DD}"
findings_total: {total_kept_count}
critical: {critical_count}
important: {important_count}
minor: {minor_count}
---
# Reviewed
EOF
```

If `cogDocsItemDir` is null/absent: no-op. On write failure: WARN the reviewer and continue — never block on this write.

### Cleanup and Report

Remove the cache boundary marker:

```bash
rm -f .claude/pr-cache/pr-review-active.json
```

Update `buddy-session.json`: set `"phase": "2"` and note completion.

Update the Task tracker: Phase 2 complete.

Report to the reviewer:
- Review artifact path
- Journey file path
- Finding counts: kept / dismissed / add-own / will-comment
- REVIEWED.md status (written / skipped / failed)

---

## Usage Examples

**Buddy review of a specific PR:**
```
/cognito-pr-review:review-pr-buddy 17890
```

**Buddy review of local uncommitted changes:**
```
/cognito-pr-review:review-pr-buddy
```

**Buddy review, C# aspects only:**
```
/cognito-pr-review:review-pr-buddy 17890 csharp
```

**Buddy review with sequential pipeline (slower but lower memory pressure):**
```
/cognito-pr-review:review-pr-buddy 17890 sequential
```
