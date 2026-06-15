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
2. **Phase 1 — Interactive walk.** Steps through every `### Step N: {Group}` chunk in the journey file's `## Manual Review Guide` using a two-pass loop: first an independent read (orientation + reviewer reasoning before pre-computed findings are revealed), then a reconciliation pass against tool findings. Captures a severity disposition (Blocking / Important / Suggestion / Dismiss) for every finding — tool-surfaced and reviewer-authored — via `AskUserQuestion`. Progress is checkpointed continuously to `{cacheDir}/buddy-session.json`.
3. **Phase 2 — Curated synthesis.** Writes the final `PR-{id}.md` review in synthesizer-v2 format containing _only_ the findings you kept (with their severity and optional comment notes). The autonomous synthesizer agent is NOT invoked — the interactive session IS the synthesis.

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

Derive `cacheDir` from the Step 1 manifest output (its `cacheDir` field):
- PR Mode: `<cogDocsItemDir>/.pr-review/pr-cache/{pr_id}/` — under the resolved cog-docs item dir
- Local Mode: `.claude/pr-cache/local/`

---

## Phase 0 — Non-Interactive Prep (Delegation)

Execute the steps defined in `commands/review-pr.md` Step 1 through Step 8 — prep → cache marker → cog-docs dest → journey → triage → planner-validate → reuse-candidacy + investigation + sweep → aggregate → post-process. Do not re-specify them here; `commands/review-pr.md` is the single source of truth for those step bodies.

On successful completion of Step 8:
- The journey file is at `<cogDocsItemDir>/PR-{pr_id}-journey.md` (PR mode) or `.claude.local/reviews/` for local mode
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

Read the journey file (`<cogDocsItemDir>/PR-{pr_id}-journey.md` in PR mode) and locate the `## Manual Review Guide` section. Extract every `### Step N: {Group Name}` chunk — each chunk has `**Files:**`, `**Perspective:**`, `**Predictive questions:**`, `**Complexity:**`, and `**loc_estimate:**`.

Read `{cacheDir}/processed-findings.json` into memory. Findings carry a `file` field; a finding belongs to a chunk if its `file` appears in that chunk's `**Files:**` list.

Initialize `{cacheDir}/buddy-session.json` (see schema below). If the file already exists (compaction recovery — see below), read it and resume from the first chunk whose `"status"` is not `"done"`.

### Per-Chunk Loop

For each chunk, in order, run these six steps:

#### 1. Orient

State a one-line objective for this chunk. If the chunk's `**Complexity:**` is `non-trivial` (or missing/ambiguous — treat as `non-trivial`), additionally give a senior-architect teach of what changed and why it matters relative to the journey Objective: concise, insightful, grounded in the cached diff and journey context — not a dump of the raw diff. For `trivial` chunks, the one-liner is the whole orientation. Deep teaching beyond the standard orient is available on explicit reviewer request ("explain this in depth").

Under the same `non-trivial` gate (not a new branch — this rides the existing condition), additionally render at least one compact ASCII diagram of the chunk's behavioral thread alongside the prose teach. For `trivial` chunks, no diagram is rendered.

**Diagram-type selection:** pick the type that best fits the thread's shape — one is the norm; use more than one only when the thread genuinely warrants it:
- **data-flow** (value or request moving across layers) — the default for a cross-layer behavioral thread
- **component/dependency** (which components the thread touches and how they relate)
- **sequence/control-flow** (ordered steps for stateful or async logic)

**Grounding and rendering constraints:**
- Derived from the cached diff and structural context; must reflect the **actual** changed components/edges — do not invent architecture or draw a generic whole-system map.
- **ASCII / box-drawing characters only** — no Mermaid fences (no ` ```mermaid `), no image links, no HTML (`<img>`, `<svg>`, `<table>`, etc.).
- **Compact** — fit a terminal pane; favor a focused thread view over a whole-system map.
- **Label nodes with real file/type/layer names** drawn from the chunk's `**Files:**` list.

Example shape (illustrative template only — not a required literal output):

```
  Controller
      |
      v
  Service
      |
      v
  StorageRepository
```

_AI-role framing:_ The diagram is a facilitation and orientation aid — a tool for quickly visualizing the behavioral thread. It is NOT a claim about business-logic correctness. The reviewer remains the sole arbiter of domain intent and correctness; the diagram cannot reason about that.

#### 2. Independent Read — Pass 1

Present the chunk's implementation and its bundled tests. Pose the chunk's `**Perspective:**` persona and `**Predictive questions:**` verbatim. Invite the reviewer to read cold and record their own observations.

**Pre-computed tool findings are NOT shown in this pass.** This is the anti-anchoring step — the reviewer reasons independently before seeing what the pipeline flagged.

_AI-role framing:_ The buddy's role in this pass is facilitation — orientation, persona framing, and predictive questioning. The reviewer is the sole arbiter of business-logic correctness and must not defer to the tool on logic. The tool cannot reason about domain intent.

Use `AskUserQuestion` to collect the reviewer's Pass-1 observations (file, optional line, note) before proceeding to Pass 2. Record these in `pass1_observations[]` in the chunk's session record.

#### 3. Reconcile — Pass 2

Reveal the chunk's pre-computed findings from `processed-findings.json` (investigation, sweep, reuse, intrafile) as a reconciliation against the reviewer's Pass-1 take: where they overlap, where the tool flagged something the reviewer didn't catch, and that the tool may have missed domain-intent issues the reviewer caught.

Present findings grouped by source:

- **Investigation findings** (`source:"investigation"`) — bugs, edge cases, correctness issues
- **Sweep rule hits** (`source:"sweep"`) — pattern violations, rule matches
- **Reuse & duplication flags** (`source:"reuse"`) — verdict (e.g. `refactor`, `extend`, `wrap`, `acceptable-new`), existing-system candidate, suggested action
- **Intra-file reuse & consistency** (`source:"intrafile"`) — verdict (`refactor`/`reuse` for in-file duplication, `inconsistent` for surrounding-code divergence), in-file `file:line`/symbol candidate, suggested action

Highlight blocking and important findings. Do not bury them in a flat list. If no pre-computed findings exist, state: "No pre-computed findings for this group."

_AI-role framing:_ These are mechanical-triage and cross-file-dependency aids — not the arbiter of business-logic correctness. The reviewer's Pass-1 observations take precedence on domain intent.

#### 4. Disposition

Use `AskUserQuestion` to ask the reviewer to disposition every finding — tool-surfaced (Pass 2) AND reviewer-authored Pass-1 observations. Present the severity options clearly:

```
For each finding, assign a severity:
  Blocking    — critical logic / security / data-corruption / requirement violation
  Important   — architectural degradation, missing edge case, significant perf issue
  Suggestion  — style / nit / optional refactor
  Dismiss     — drop this finding (optional note explaining why)
```

Any non-dismissed finding may carry an optional free-text comment note. Prompt for it after the severity choice.

Reviewer-authored Pass-1 observations become severity-tagged findings with `source: "reviewer"`. If there are no tool findings and the reviewer recorded no Pass-1 observations, use `AskUserQuestion` to ask whether they want to add an observation before moving on.

#### 5. Checkpoint

Write (or update) `{cacheDir}/buddy-session.json` with this chunk's completed `pass1_observations`, `dispositions`, and status `"done"`. See schema below.

#### 6. Advance

Announce the chunk is complete and move to the next one.

### Interruption Handling

At any point in the walk, the reviewer may:

- **Ask to dig deeper** into a file or concept — answer using cached context and your architectural knowledge; this also covers requests for a diagram on a `trivial` chunk (which normally renders none) or for a richer or alternative diagram on any chunk — satisfy these from cached context and architectural knowledge using the same ASCII-only, compact, diff-grounded constraints defined in §1 Orient above
- **Request to open a local file** — this is an investigation-style carve-out: you may read the local codebase on the `main` branch (not the PR branch) to provide context, just as the investigation agent does. This is NOT sweep's cache-only restriction. State this explicitly: "Reading from the local codebase on `main` for context — this is not the PR branch state."
- **Revisit a prior chunk** — re-open that chunk's session state, present its dispositions, and allow the reviewer to change verdicts. Update `buddy-session.json` accordingly.

### Compaction Recovery

On session start, before looping, check whether `{cacheDir}/buddy-session.json` already exists. If it does:

1. Read it and find the first chunk whose `"status"` is not `"done"`.
2. Resume the two-pass loop from that chunk — do not re-run completed chunks.
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
			"group": "<behavioral thread name>",
			"complexity": "trivial|non-trivial",
			"loc_estimate": 0,
			"status": "pending|in-progress|done",
			"pass1_observations": [
				{ "file": "<path>", "line": 0, "note": "<reviewer's independent observation>" }
			],
			"dispositions": [
				{
					"finding_ref": "<file:line or id>",
					"source": "investigation|sweep|reuse|intrafile|reviewer",
					"severity": "blocking|important|suggestion|dismiss",
					"note": "<optional comment text>"
				}
			]
		}
	],
	"added_observations": [
		{ "file": "<file path>", "line": 0, "note": "<reviewer's own observation>" }
	]
}
```

Write this file after every chunk completes. This is the recovery anchor for compaction or session interruption.

---

## Phase 2 — Human-Curated Synthesis

When all chunks are complete (all `"status": "done"`), update the Task tracker: Phase 1 complete, Phase 2 in-progress.

### Collect Curated Content

From `buddy-session.json`:

Map severity dispositions to synthesizer-v2 output sections:

- **Blocking** (`severity: "blocking"`) — include in `## Critical Findings` (for `source:"investigation"` findings) or `### Important` subsections (for `source:"sweep"`, `source:"reuse"`, `source:"intrafile"` findings)
- **Important** (`severity: "important"`) — include in the appropriate `### Important` subsections
- **Suggestion** (`severity: "suggestion"`) — include in the existing `### Minor` (nit) subsections — never introduce a new suggestion-level heading; map these into the Minor tier only
- **Dismiss** (`severity: "dismiss"`) — EXCLUDED from the final review

Reviewer-authored findings (`source: "reviewer"`) from `pass1_observations[]` are included per their severity disposition. A non-dismissed finding's optional `note` is carried as its comment text.

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

Read `{cacheDir}/pr-context.json` for the `cogDocsItemDir` field (always set in PR mode) — mirror the write logic from `commands/review-pr.md` Step 10 exactly:

**PR Mode:**
- Write `<cogDocsItemDir>/PR-{pr_id}.md`
- Finalize `<cogDocsItemDir>/PR-{pr_id}-journey.md` (already created there in Phase 0)

**Local Mode:** Write `.claude.local/reviews/LOCAL-{branch}-{timestamp}.md`

### REVIEWED.md Sentinel

Mirror the sentinel behavior from `commands/review-pr.md` Step 12.6 exactly.

If `cogDocsItemDir` is non-null, write `<cogDocsItemDir>/REVIEWED.md` with YAML frontmatter carrying PR identity, today's date, and the finding counts from the curated review. Derive counts from the severity tally: `critical` = count of `blocking` dispositions, `important` = count of `important` dispositions, `minor` = count of `suggestion` dispositions. `findings_total` = total non-dismissed findings (including reviewer-authored). Follow the frontmatter with a one-line human-readable body.

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

Local Mode (no work item): no-op — skip the sentinel. On write failure: WARN the reviewer and continue — never block on this write.

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
- Finding counts: blocking / important / suggestion / dismissed (including reviewer-authored)
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
