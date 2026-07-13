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

1. **Phase 0 — Non-interactive prep (delegated subagent).** Dispatches ONE `general-purpose` subagent that executes `commands/review-pr.md` Steps 1–8.5 end-to-end — dispatching the pipeline's specialist agents itself — and returns only the small `phase0-result.json` envelope. The orchestrator never reads `review-pr.md`, the journey, triage JSON, agent outputs, or `processed-findings.json` whole; its window stays near-fresh for the walk.
2. **Phase 1 — Interactive walk.** Steps through every chunk in `{cacheDir}/chunk-index.json` (derived from the journey's `## Manual Review Guide`), lazy-loading exactly one chunk's journey slice, diffs, and findings shard at a time, using a two-pass loop: first an independent read (orientation + reviewer reasoning before pre-computed findings are revealed), then a reconciliation pass against tool findings. Captures a severity disposition (Blocking / Important / Suggestion / Dismiss) for every finding — tool-surfaced and reviewer-authored — via `AskUserQuestion`. Progress is checkpointed continuously to `{cacheDir}/buddy-session.json`.
3. **Phase 2 — Curated synthesis.** Writes the final `PR-{id}.md` review in synthesizer-v2 format containing _only_ the findings you kept (with their severity and optional comment notes). The autonomous synthesizer agent is NOT invoked — the interactive session IS the synthesis.

---

## Argument Parsing

Parse arguments exactly as `commands/review-pr.md` specifies:

- **PR_ID**: First numeric token → PR Mode (e.g. `17890`)
- **No PR ID / "local"**: Local Mode
- **aspects**: `all`, `csharp`, `frontend`, `api`, `consistency`, `testing` — defaults to `all`
- **sequential**: If present, pipeline agents run sequentially instead of in parallel
- **--full**: Force the full pipeline in the Phase-0 delegate (overrides review-pr.md Step 1.7 size routing)
- **--spot**: Force the downshifted path in the Phase-0 delegate (overrides Step 1.7 routing)
- **--local**: Force local mode
- **--base <branch>**: Target branch for local diff (default: `main`)
- **--include-untracked**: Include untracked files in local mode

Derive `cacheDir` from the Phase-0 result envelope (its `cacheDir` field — see Phase 0 below):
- PR Mode: `<cogDocsItemDir>/.pr-review/pr-cache/{pr_id}/` — under the resolved cog-docs item dir
- Local Mode: `.claude/pr-cache/local/`

---

## Phase 0 — Non-Interactive Prep (Delegated Subagent)

Phase 0 executes OUTSIDE your context window. Do NOT read `commands/review-pr.md`, the journey file, triage output, agent outputs, or `processed-findings.json` in this phase — the delegate does all of that. `commands/review-pr.md` remains the single source of pipeline truth; this is delegation, not duplication.

**Dispatch ONE Phase-0 delegate:**

```
Agent:
  subagent_type: general-purpose
  prompt: |
    You are the Phase-0 prep delegate for an interactive buddy review of PR {pr_id | "local"}.

    Read ~/.claude/plugins/local-tools/plugins/cognito-pr-review/commands/review-pr.md and
    execute Step 1 through Step 8.5 EXACTLY as written — including the Step 1.7 size route —
    with these arguments: {forward PR_ID / aspects / sequential / --full / --spot / --local /
    --base / --include-untracked verbatim}.

    You dispatch the pipeline's specialist agents yourself (journey-planner, triage,
    investigation, sweep, reuse-candidacy, intra-file consistency). Write every artifact to
    disk exactly where review-pr.md specifies.

    Buddy-specific carve-outs:
    - STOP after Step 8.5. Do NOT execute Step 9 (synthesizer) or any later step — the
      interactive buddy session IS the synthesis.
    - If Step 1.7 routes DOWNSHIFTED: execute D1–D3 and D5, SKIP D4 (inline synthesis —
      the buddy walk replaces it), run the Step 8.5 emitter, then stop. Do NOT resume at
      Step 10.

    Your final message: ONLY the verbatim contents of {cacheDir}/phase0-result.json — no
    commentary, no summaries, no artifact bodies. On any pipeline failure, instead return
    "PHASE0-FAILED:" followed by the failing step number and the error verbatim.
```

**On delegate return:**

- Reply starts with `PHASE0-FAILED:` → report the delegate's error to the reviewer **verbatim** and STOP — the same contract as a Step-1 prep failure.
- Otherwise parse the envelope JSON — `{pr_id, cacheDir, cogDocsItemDir, journey_path, chunk_count, finding_counts, chunk_index_path}`. This envelope is the ONLY Phase-0 data that enters your window; everything else stays on disk for lazy per-chunk loading.

Announce to the reviewer:

> "Prep complete (delegated): {sum of finding_counts} findings across {chunk_count} chunks. Starting the interactive walk now."

Initialize Task-tool tracking for the three high-level phases:
- Phase 0 (complete)
- Phase 1 (in-progress)
- Phase 2 (pending)

**Downshifted-route note:** on a small PR the envelope may carry `journey_path: null` and `chunk_count: 1` — review-pr.md Step 1.7 downshifted the run and the chunk index holds one synthetic whole-PR chunk. The walk handles this uniformly: orientation teaches from the chunk's diffs and findings directly, and there are no journey `**Perspective:**`/`**Predictive questions:**` prompts to pose.

---

## Phase 1 — Interactive Walk Along the Manual Review Guide

### Setup

Read `{chunk_index_path}` (from the envelope) — `chunk-index.json` — and NOTHING else. Each chunk entry carries `{index, group, complexity, files, journey_lines, diff_paths, finding_refs}`; the finding↔chunk join was computed deterministically at Step 8.5 (a finding belongs to a chunk if its `file` appears in that chunk's journey `**Files:**` list — the same rule this command used to apply inline). Do NOT read the journey file whole and do NOT read `processed-findings.json` whole — per-chunk data is loaded lazily inside the loop below.

Initialize `{cacheDir}/buddy-session.json` (see schema below) from the envelope + chunk index: one `chunks[]` entry per chunk-index entry (status `"pending"`; `loc_estimate` is filled in from the journey slice when the chunk is loaded, `0` until then), `total_chunks` = `chunk_count`, plus the additive top-level `chunk_index_path`. If the file already exists (compaction recovery — see below), read it and resume from the first chunk whose `"status"` is not `"done"`.

### Finding ID Convention

Every finding must be referenced by a single canonical ID everywhere it appears — in the orient narration, reconcile list, disposition prompt, and the persisted `finding_ref` field. Use this scheme without exception:

- **Line-bearing findings:** canonical ID is `<file>:<line>` (e.g. `identify-submitter.ts:9`). This is the **leading token** of every `finding_ref` value.
- **Line-less findings** (e.g. some investigation findings with no specific line): canonical ID is `<file>#<short-slug>` (e.g. `identify-submitter.ts#null-guard`). Use a stable, lowercase-hyphenated slug derived from the finding's subject.

A human-readable descriptor MAY follow in parentheses — e.g. `identify-submitter.ts:9 (reuse vs token.Scope)` — but the **leading `<file>:<line>` or `<file>#<slug>` token is the canonical ID**, not the descriptor. Phase 4's `scripts/disposition-calibration.ts` joins `buddy-session.json` dispositions to `processed-findings.json` by parsing that leading token and matching it (by source + line + basename) against the findings file — so the ID shown in the prompt **must equal the `finding_ref` persisted**. Do not invent ad-hoc IDs (`F0`, `①`, `[F0]`, `Q2`, etc.); these break the calibration join.

### Per-Chunk Loop

**Stream hygiene:** During the walk, the harness may emit `<task-notification>` lines (Task-tool status updates). Do NOT echo these into the reviewer-facing output — suppress them entirely. Surface only the orient / teach / diagram / disposition content to the reviewer.

For each chunk, in order, run these seven steps:

#### 0. Load (lazy — this chunk only)

Load exactly chunk *k*'s working set, nothing more:

- **Journey slice:** if the chunk's `journey_lines` is non-null, do a ranged Read of `journey_path` covering lines `[start, end]` — this yields the chunk's `**Files:**`, `**Perspective:**`, `**Predictive questions:**`, `**Complexity:**`, and `**loc_estimate:**`. If `journey_lines` is null (downshifted route or the catch-all chunk), there is no journey prose — orient from the diffs and findings directly.
- **Diffs:** the chunk's `diff_paths` (plus cached files for surrounding context as needed).
- **Findings shard:** `{cacheDir}/findings-by-chunk/chunk-{k}.json` — the chunk's full finding objects. The shard union across chunks equals `processed-findings.json`; never open the whole findings file during the walk.

Nothing outside chunk *k* enters the window.

#### 1. Orient

Open the chunk with a titled header: `### {chunk title} — {files}`. The
`{chunk title}` is a short, semantically logical title you compose (≈ 2–6 words)
based on what actually changed in the chunk — sharpen the journey group name into a
crisper title when one fits; don't just echo file names. `{files}` lists **every**
file in the chunk's `**Files:**`. For a file that appears in only this chunk, the
bare path is enough; for a file that appears in **more than one chunk's** `**Files:**`,
append this chunk's line range (`path:start-end`, comma-separated if several) so the
reviewer knows which portion of the file this chunk covers.

Then state a one-line objective for this chunk. If the chunk's `**Complexity:**` is `non-trivial` (or missing/ambiguous — treat as `non-trivial`), additionally give a senior-architect teach of what changed and why it matters relative to the journey Objective: concise, insightful, grounded in the cached diff and journey context — not a dump of the raw diff. For `trivial` chunks, the one-liner is the whole orientation. Deep teaching beyond the standard orient is available on explicit reviewer request ("explain this in depth").

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

Present the chunk's implementation and its bundled tests. Pose the chunk's `**Perspective:**` persona and `**Predictive questions:**` verbatim (from the journey slice; on a journey-less chunk there are none — invite a cold read of the diffs without persona framing). Invite the reviewer to read cold and record their own observations.

**Pre-computed tool findings are NOT shown in this pass.** This is the anti-anchoring step — the reviewer reasons independently before seeing what the pipeline flagged.

_AI-role framing:_ The buddy's role in this pass is facilitation — orientation, persona framing, and predictive questioning. The reviewer is the sole arbiter of business-logic correctness and must not defer to the tool on logic. The tool cannot reason about domain intent.

Use `AskUserQuestion` to collect the reviewer's Pass-1 observations (file, optional line, note) before proceeding to Pass 2. Record these in `pass1_observations[]` in the chunk's session record.

#### 3. Reconcile — Pass 2

**Pre-filter: already-commented and stale Copilot threads**

Before presenting findings, apply two filters using `{cacheDir}/pr-context.json` and `{cacheDir}/pr-timeline.json`:

**Already-commented findings:** Cross-check each finding's canonical ID (`<file>:<line>` or `<file>#<slug>`) against the open PR threads in `pr-context.json`. A finding that corresponds to an existing comment or thread already posted on the PR is classified as **already-commented** and is NOT routed through the disposition prompt. Record it immediately in `buddy-session.json` as:

```json
{
  "finding_ref": "<canonical-id>",
  "source": "<original source>",
  "severity": "already-commented",
  "note": "already raised on the PR — not re-litigated"
}
```

Surface it to the reviewer as a one-line informational note — e.g. "↩ `identify-submitter.ts:42` — already raised on the PR (not re-litigated)" — grouped at the top of the reconcile output so the reviewer can see coverage without being asked to disposition it again. These entries count as fully handled for the WU-5a Completeness Sweep.

**Stale Copilot-thread reconciliation:** Read the commit SHA list from `pr-timeline.json` (the array of commit SHAs in chronological order, newest last). The **current head SHA** is the last entry. For each Copilot review thread in `pr-context.json` that carries an `originalCommitId` (or equivalent anchor SHA):

- If that anchor SHA equals the **current head SHA** → the thread is **live**: treat it normally.
- If that anchor SHA is any **earlier SHA** in the timeline → the thread is **stale**: the code it commented on has since changed. Mark it stale and skip/down-rank it — do NOT re-surface it as a live finding in the walk. Log it as stale in the reconcile output: "⚠ Copilot thread on `<file>:<line>` anchored to `<short-SHA>` (outdated — head is `<head-short-SHA>`) — skipped."

Both filters run before the grouped finding display below. Only findings that pass both filters reach the disposition prompt.

---

Reveal the chunk's pre-computed findings from its findings shard (`findings-by-chunk/chunk-{k}.json` — investigation, sweep, reuse, intrafile) as a reconciliation against the reviewer's Pass-1 take: where they overlap, where the tool flagged something the reviewer didn't catch, and that the tool may have missed domain-intent issues the reviewer caught.

Present each finding that passes both pre-filters in the **Standardized Issue Block** — the same shape `synthesizer-v2.md` defines (`## Standardized Issue Block`) and Phase 2 emits post-disposition. The block is the reveal display; the Step-4 disposition prompt below is unchanged.

```
### {Issue title}
**Severity:** {recommended — see below}   **Source:** {investigation | sweep | reuse | intrafile}   **Location:** {file}:{line}   **Confidence:** {CONFIRMED | UNVERIFIED | —}
**What:** {1–2 line statement of the issue and why it matters}
**Proposed fix:** {concrete before→after snippet when cheap & available; precise prose otherwise — sweep is always prose}
**Proposed PR comment:** {ready-to-paste draft, terse, reviewer-voiced, references file:line; never auto-posted}
```

Keep findings **grouped by source** under their section headings, and keep the pre-computed `tier → severity → effective_weight` order within each group — **do not re-sort**:

- **Investigation findings** (`source:"investigation"`) — bugs, edge cases, correctness issues
- **Sweep rule hits** (`source:"sweep"`) — pattern violations, rule matches
- **Reuse & duplication flags** (`source:"reuse"`) — verdict (e.g. `refactor`, `extend`, `wrap`, `acceptable-new`), existing-system candidate, suggested action
- **Intra-file reuse & consistency** (`source:"intrafile"`) — verdict (`refactor`/`reuse` for in-file duplication, `inconsistent` for surrounding-code divergence), in-file `file:line`/symbol candidate, suggested action

Highlight blocking and important findings. Do not bury them in a flat list. If no pre-computed findings exist (after the pre-filters), state: "No pre-computed findings for this group."

**Pre-disposition `**Severity:**` semantics (explicit).** Here, the block's `**Severity:**` field carries the pipeline's **recommended / tool-computed** severity — read from the finding object's `tier` (in the chunk's shard), or for reuse/intrafile from the verdict→severity mapping (`refactor`/`reuse` → important, `extend`/`wrap` → nit/suggestion, `inconsistent` → nit/suggestion). This is a **recommendation only — NOT the reviewer's disposition**, which is captured by the Step-4 prompt that immediately follows (the reviewer may override it). Note that **post-disposition** (Phase 2's `PR-{id}.md` and in-chat digest) the same `**Severity:**` field carries the reviewer's *chosen* severity — so the pre- and post-disposition surfaces use one field with two clearly-scoped meanings and do not read as contradictory. `**Confidence:**` carries the existing `CONFIRMED` / `UNVERIFIED` / `—` label, identical to the Step-4 inline label.

**Author the Proposed fix + Proposed PR comment at reveal time, for every revealed finding** — including findings the reviewer may subsequently dismiss. This authoring moves earlier than Phase 2 (it used to happen in Phase 2's "Collect Curated Content"); Phase 2 **reuses** what was authored here for the kept findings — do NOT re-author from scratch there.

- **Proposed fix** — a concrete before→after snippet/diff when the fix is small/local and you have the code in hand; precise prose resolution steps otherwise. The buddy MAY ground the snippet from the **local codebase on `main`** (the investigation-style carve-out — the same access used in the Phase-1 walk's "Open a local file" interruption): it may use a fresher/richer snippet than the cache-only synthesizer-v2 path, **including for `sweep` findings** (which carry no `evidence.snippet`). State the read explicitly: "Reading from the local codebase on `main` for context — not the PR branch state." The block **FORMAT** stays identical to synthesizer-v2's; only snippet richness may differ — the documented cache-only-vs-local asymmetry (synthesizer-v2 is cache-only and must source snippets from `evidence.snippet` alone).
- **Proposed PR comment** — a ready-to-paste draft: terse, reviewer-voiced, references `file:line`; never auto-posted (per `user/CLAUDE.local.md`). If a Pass-1 reviewer observation / `note` exists for the finding, it seeds the draft comment.

_AI-role framing:_ These are mechanical-triage and cross-file-dependency aids — not the arbiter of business-logic correctness. The reviewer's Pass-1 observations take precedence on domain intent.

#### 4. Disposition

**Default — batched multi-disposition prompt:** Use a single `AskUserQuestion` with one question per finding (the multi-question form) to disposition ALL of a chunk's findings in one prompt — tool-surfaced (Pass 2) AND reviewer-authored Pass-1 observations. Do NOT issue 6–16 separate one-at-a-time asks; that is the fallback only when a single finding genuinely needs isolated deliberation (e.g. the reviewer explicitly asks to discuss one finding in depth before continuing). Batching is the default; one-at-a-time is the exception.

For each finding in the batched prompt, display its confidence label inline — read from the `confidence` field on the finding object in the chunk's shard — BEFORE presenting the severity choices:
- `CONFIRMED` — the pipeline self-verified this finding
- `UNVERIFIED` — the pipeline could not self-verify this finding
- If the `confidence` field is absent or null, show `—` (do not guess or invent a label)

Use the exact label strings `CONFIRMED` and `UNVERIFIED` — do not remap, translate, or substitute other wording.

**Taxonomy invariant:** the prompt MUST present all four values — `Blocking / Important / Suggestion / Dismiss` — in that stable order, on every disposition prompt, for every finding. Never omit `Blocking`, never reorder the four values, never collapse to fewer options, and never substitute the older `Keep / Will-comment / Dismiss / Add-own` vocabulary. This taxonomy must remain stable so that Phase 4 calibration signal is comparable across sessions.

```
For each finding [confidence label shown inline], assign a severity:
  Blocking    — critical logic / security / data-corruption / requirement violation
  Important   — architectural degradation, missing edge case, significant perf issue
  Suggestion  — style / nit / optional refactor
  Dismiss     — drop this finding (optional note explaining why)
```

Any non-dismissed finding may carry an optional free-text comment note. Prompt for it after the severity choice.

**Early escape hatch — dismiss-heavy chunks:** If a chunk is trending dismiss-heavy (the reviewer has dismissed several findings in a row, or explicitly signals they would dismiss or accept all the rest), offer this option early:

> "Want to auto-disposition all remaining findings at their recommended severities? This records an explicit verdict for each one — no findings are silently skipped or dropped."

If the reviewer accepts: iterate over every remaining undispositioned finding, assign its recommended severity (using the tool-supplied severity or, if absent, `dismiss` as the default for flagged-low-priority findings — always use the most specific recommended value available), and write an explicit `dispositions[]` entry for each in `buddy-session.json`. This path is NOT a skip or drop — it produces real, recorded dispositions that Phase 4's calibration and the WU-5a Completeness Sweep can consume. An undispositioned finding yields no calibration signal; the escape hatch converts "I'd dismiss/accept all the rest" into explicit recorded signal. The Completeness Sweep gate (Phase 2) treats escape-hatch-dispositioned findings as fully satisfied — they have explicit verdicts. Calibration-wise the hatch is bounded: `disposition-calibration.ts` aggregates per-PR (one EMA step per lane/rule per run), so a mass-dismissal session moves a weight by a single bounded step — it cannot cliff a weight through repeated per-disposition decay.

Reviewer-authored Pass-1 observations become severity-tagged findings with `source: "reviewer"`. If there are no tool findings and the reviewer recorded no Pass-1 observations, use `AskUserQuestion` to ask whether they want to add an observation before moving on.

#### 5. Checkpoint

Write (or update) `{cacheDir}/buddy-session.json` with this chunk's completed `pass1_observations`, `dispositions`, and status `"done"`. See schema below.

**Serialization requirement:** Serialize the ENTIRE session object using a proper JSON serializer (`JSON.stringify`) — NEVER hand-assemble JSON with raw path strings. Windows cache paths contain backslashes (`C:\Users\…`) which MUST be escaped to `C:\\Users\\…` in JSON; hand-built JSON with raw backslashes produces invalid JSON that fails on resume. **Reload check (hard requirement):** after writing, verify the file round-trips cleanly — `JSON.parse(fs.readFileSync(..., 'utf8'))` must not throw. If it does, re-serialize and rewrite before advancing.

#### 6. Advance

Announce the chunk is complete and move to the next one.

### Interruption Handling

At any point in the walk, the reviewer may:

- **Ask to dig deeper** into a file or concept — answer using cached context and your architectural knowledge; this also covers requests for a diagram on a `trivial` chunk (which normally renders none) or for a richer or alternative diagram on any chunk — satisfy these from cached context and architectural knowledge using the same ASCII-only, compact, diff-grounded constraints defined in §1 Orient above
- **Request to open a local file** — this is an investigation-style carve-out: you may read the local codebase on the `main` branch (not the PR branch) to provide context, just as the investigation agent does. This is NOT sweep's cache-only restriction. State this explicitly: "Reading from the local codebase on `main` for context — this is not the PR branch state."
- **Revisit a prior chunk** — re-open that chunk's session state, present its dispositions, and allow the reviewer to change verdicts. Update `buddy-session.json` accordingly.

### Compaction Recovery

On session start, before looping, check whether `{cacheDir}/buddy-session.json` already exists. If it does:

1. Read it; recover `chunk_index_path` from its top level (fallbacks: `{cacheDir}/chunk-index.json`, and `{cacheDir}/phase0-result.json` for the full envelope). Find the first chunk whose `"status"` is not `"done"`.
2. Read the chunk index + that chunk's findings shard ONLY — not the whole journey, not `processed-findings.json` — and resume the two-pass loop from that chunk (strictly less data than a full re-read). Do not re-run completed chunks.
3. Announce: "Resuming buddy session at chunk {n} of {total}: '{group name}'."

If all chunks are `"done"`, skip to Phase 2.

### `buddy-session.json` Schema

```json
{
	"pr_id": "<id or 'local'>",
	"cache_dir": "<path>",
	"chunk_index_path": "<path to {cacheDir}/chunk-index.json — additive; recovery anchor for lazy loads>",
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
					"finding_ref": "<file:line or file#slug> — leading token is the canonical ID from the Finding ID Convention above; the calibration join depends on it",
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

Write this file after every chunk completes — always via `JSON.stringify`, never hand-assembled. Windows paths in `cache_dir`, `finding_ref`, and similar fields MUST be properly escaped (`C:\\Users\\…`). Verify the written file `JSON.parse`s cleanly on every write; rewrite if it does not. This is the recovery anchor for compaction or session interruption.

---

## Phase 2 — Human-Curated Synthesis

When all chunks are complete (all `"status": "done"`), update the Task tracker: Phase 1 complete, Phase 2 in-progress.

### Completeness Sweep (pre-synthesis gate)

Before collecting curated content, assert that every finding presented in Phase 1 has a recorded disposition in `buddy-session.json`:

- Every tool finding from every chunk's findings shard (`findings-by-chunk/chunk-{k}.json` for every chunk in the index — the shard union equals `processed-findings.json` by construction, so sweeping the shards is a complete sweep). Verify by count: compare total sharded findings against the envelope's `finding_counts` sum.
- Every reviewer Pass-1 observation captured in `pass1_observations[]`.

No finding may proceed to synthesis undispositioned. If any are missing a disposition entry in `dispositions[]`:

1. Route them back through the Disposition step (#4) — or the early escape hatch — and capture an explicit severity verdict from the reviewer via `AskUserQuestion`.
2. Record the explicit disposition in `buddy-session.json` before proceeding.

**Never silently skip or auto-drop an undispositioned finding.** An abandoned finding yields no calibration signal (the signal only comes from an explicit reviewer verdict, by design — do not fabricate one). The only correct resolution is an explicit disposition. This completeness is also what keeps Phase 4's disposition signal meaningful and complete.

### Collect Curated Content

From `buddy-session.json`, collect every non-dismissed finding (Blocking / Important / Suggestion). Dismissed findings (`severity: "dismiss"`) are EXCLUDED from the final review.

Map each kept finding to its synthesizer-v2 source section by `source`:

- `source:"investigation"` → `## Critical Findings`
- `source:"sweep"` → `## Rule-Based Findings`
- `source:"reuse"` → `## Reuse & Duplication`
- `source:"intrafile"` → `## Intra-File Consistency`
- `source:"reviewer"` (reviewer-authored Pass-1 observations) → the section matching the observation's nature, else `## Critical Findings`

The disposition severity (Blocking / Important / Suggestion) is carried in the **Standardized Issue Block**'s inline `**Severity:**` field — there is no separate `### Important`/`### Minor` sub-bucketing (the synthesizer-v2 format is uniform per Phase 1). Within each section, findings keep their pre-computed `tier → severity → effective_weight` order; do not re-sort.

**Reuse the Proposed fix and Proposed PR comment authored at reveal time.** These were already authored per finding during Phase 1's "Reconcile — Pass 2" reveal (for every revealed finding, kept or not) — reuse them here for the kept findings; do NOT re-author from scratch. If a kept finding somehow lacks one (e.g. an escape-hatch auto-disposition), author it now using the same rules. This is net-new buddy-authored inline synthesis — NOT an agent invocation (see the note below):

- **Proposed fix** — a concrete before→after snippet/diff when the fix is small/local and you have the code in hand; precise prose resolution steps (what to change, where, and why) otherwise. The buddy MAY ground the snippet from the **local codebase on `main`** (the investigation-style carve-out — same access used in the Phase-1 walk's "Open a local file" interruption): it may use a fresher/richer snippet than the cache-only synthesizer-v2 path, **including for `sweep` findings** (which carry no `evidence.snippet`). State the read explicitly: "Reading from the local codebase on `main` for context — not the PR branch state." The block **FORMAT** stays identical to synthesizer-v2's; only snippet richness may differ — this is the documented cache-only-vs-local asymmetry (synthesizer-v2 is cache-only and must source snippets from `evidence.snippet` alone).
- **Proposed PR comment** — a ready-to-paste draft: terse, reviewer-voiced, references `file:line`. If the kept finding carries a reviewer `note`, fold it into / seed the draft comment (the `note` is the reviewer's own intended comment text). Never auto-posted (per `user/CLAUDE.local.md`).

Reviewer-authored findings (`source: "reviewer"`) from `pass1_observations[]` are included per their severity disposition and also get a Proposed fix + Proposed PR comment (their optional `note` seeds the draft comment).

Do NOT invoke the `synthesizer-v2` agent. The interactive session IS the synthesis step — the fix/comment authoring above is buddy-authored inline synthesis, not an agent call. You (the orchestrating agent) write the review directly from the curated content above.

### Review Document Format

Produce the review document following the exact synthesizer-v2 output format defined in `agents/synthesizer-v2.md` — same header, same section names, and the **Standardized Issue Block** that `synthesizer-v2.md` defines for every kept finding. Each kept finding, in every section, renders in that standardized block — `### {Issue title}` followed by `**Severity:** / **Source:** / **Location:** / **Confidence:**`, then `**What:**`, `**Proposed fix:**`, and `**Proposed PR comment:**` — NOT the old heterogeneous per-source shapes (no `File/Severity/Evidence/Suggestion` investigation subsection, no one-line `- {title} [{file}:{line}]` sweep/reuse/intrafile bullets, no `### Important`/`### Minor` sub-bucketing). The `## Reuse & Duplication` section uses that exact name and lists kept `source:"reuse"` findings. The `## Intra-File Consistency` section uses that exact name and lists kept `source:"intrafile"` findings. Findings keep their pre-computed `tier → severity → effective_weight` order within each section (do not re-sort). Omit sections that have no content (e.g. omit `## Re-Review Status` for initial reviews, omit `## Reuse & Duplication` if no reuse findings were kept, omit `## Intra-File Consistency` if no intra-file findings were kept).

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

Use `cogDocsItemDir` from the Phase-0 envelope (always set in PR mode) — mirror the write logic from `commands/review-pr.md` Step 10 exactly:

**PR Mode:**
- Write `<cogDocsItemDir>/PR-{pr_id}.md`
- Finalize `<cogDocsItemDir>/PR-{pr_id}-journey.md` (already created there in Phase 0; skip when the envelope's `journey_path` is null — the downshifted route produces no journey)

**Local Mode:** Write `.claude.local/reviews/LOCAL-{branch}-{timestamp}.md`

### Machine-Readable Sidecar (`PR-{id}-findings.json`)

Alongside the curated review, ALSO write the machine-readable findings sidecar `PR-{id}-findings.json` in the same directory as `PR-{id}.md` — the same sidecar `agents/synthesizer-v2.md` defines (see its "Machine-Readable Sidecar" section; keep the schemas identical). Content: a JSON array of exactly the kept (non-dismissed) findings you rendered, in rendered order, each with `id` / `title` / `file` / `line` / `severity` / `source` / `verdict` / `rule_id` / `confidence`:

- `id` follows the buddy finding-ref convention: `{basename}:{line}`; line-less findings use `{basename}#{kebab-case-slug}`.
- `severity` is the reviewer's disposition severity (`blocking | important | suggestion`); reviewer-authored findings carry `source: "reviewer"`.
- Field values come from the session's finding objects verbatim — do not re-derive them.
- Emit the sidecar even when zero findings were kept (`[]`).
- Local Mode: write `LOCAL-{branch}-{timestamp}-findings.json` beside the local review artifact.

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

### Auto-Recalibrate from Dispositions

Silently invoke the shared `disposition-calibration.ts` helper against this session's data. Do NOT ask the user — recalibration runs unconditionally at Phase 2 close (the operator-validated decision: buddy auto-recalibrates inline, unlike `review-pr.md` which only writes a `pending-calibration` marker and defers to `/learn-from-pr`).

```bash
npx tsx {plugin_root}/scripts/disposition-calibration.ts \
  --session {cacheDir}/buddy-session.json \
  --findings {cacheDir}/processed-findings.json \
  --weights ~/.claude/state/cognito-pr-review/weights.yaml
```

The `--weights` target is the **mutable state file** (seeded from the plugin's `knowledge/weights.yaml` on first use), not the plugin's knowledge copy — calibration written to the state path survives plugin version bumps.

This is the **same single implementation** used by `/learn-from-pr` — one helper, not a buddy-specific copy.

Print a summary of the weight deltas reported by the helper: per-rule and per-source old→new values. This summary is the only user-visible output of this step.

If the session has zero usable dispositions, the helper no-ops and leaves the state file byte-identical — print "No dispositions recorded — weights unchanged."

Non-fatal: if the helper invocation fails, WARN the reviewer and continue. Never block the session close on calibration.

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

**In-chat standardized digest (rendered alongside the above — not instead of it).** After reporting the paths, counts, and status, render every kept finding in chat using the same **Standardized Issue Block** emitted in `PR-{id}.md` — `### {Issue title}` + `**Severity:** / **Source:** / **Location:** / **Confidence:**`, then `**What:**`, `**Proposed fix:**`, and `**Proposed PR comment:**`. Order the digest **most-important-first** (the same pre-computed `tier → severity → effective_weight` order — do not re-sort). Dismissed findings are excluded. This gives the reviewer the full proposed fix and the ready-to-paste draft PR comment for every kept issue at session close, mirroring the persisted artifact; the paths, counts, and REVIEWED.md status above remain present.

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
