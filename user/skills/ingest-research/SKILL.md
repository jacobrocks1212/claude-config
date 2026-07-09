---
name: ingest-research
description: Ingest Gemini deep-research results into per-feature RESEARCH.md + RESEARCH_SUMMARY.md and clear stub markers. Scans docs/gemini-sprint/results/ by default; path args ingest one-off files. Dispatched by /lazy-batch Step 0.5 or standalone.
argument-hint: [<path-to-research-file> ...]
plan-mode: never
model: sonnet
allowed-tools: ["Bash", "Read", "Edit", "Write", "Grep"]
---

# Ingest Research — Gemini Deep-Research Bridge

Bridges the manual gap in AlgoBooth's Gemini deep-research workflow: takes Gemini result files (`.txt` or `.md`), correlates each to a feature in the queue, writes per-feature `RESEARCH.md` + `RESEARCH_SUMMARY.md`, and clears the stub markers that pre-Gemini drafts carry.

**Two invocation modes:**

1. **Default — scan staging dir (no args).** Processes every `.txt` file directly under `docs/gemini-sprint/results/`. This is the path `/lazy-batch`'s Step 0.5 pre-loop ingest check uses, and the path the user follows when they save Gemini outputs into the staging dir directly.

2. **One-off file path(s) (with args).** Each positional argument is treated as a path to a Gemini result file (absolute or relative to `$CWD`, including `~/`-expansion). The skill copies each file into `docs/gemini-sprint/results/` first (preserving basenames, suffixing with a timestamp on collision), then runs the standard correlation + ingest flow on it. This is how the user ingests research from outside the repo — e.g., `~/Downloads/voice-synthesis.txt`, a phone-synced cloud folder, or anywhere else the file landed before they got back to the repo.

Both modes share the same correlation, distillation, SPEC.md update, queue.json clear, and per-feature commit logic. The orchestrator pause/resume contract (announce upload paths, halt, resume on next user prompt) lives in `/lazy-batch` Step 1f; this skill is the mechanical converter.

**Hard constraints (non-negotiable):**

1. **Scope is `docs/` only — plus reads from arg paths.** This skill MUST NOT WRITE any repo files outside `docs/` — no source code, no tests, no config. The only files written are inside `docs/features/<.../>/<feature-id>/` (RESEARCH.md, RESEARCH_SUMMARY.md, SPEC.md edits), `docs/features/queue.json` (clear `"stub": true`), and under the staging path (`docs/gemini-sprint/results/` and its `_consumed/` subdirectory). External input paths supplied as args are **read-only** — Step 0.5 copies their content into the staging dir, it does NOT move or delete the original (the user may have the file in a synced folder where deletion would propagate across devices).
2. **Leaf skill — no sub-skill dispatch.** Do NOT call `/spec`, `/spec-phases`, or any other sub-skill. The state machine's Step 5 "integrate research" handles `/spec` Phase 3 on the next orchestrator cycle after this skill clears the research-pending state.
3. **`--batch`-by-default.** This skill has no interactive mode worth running. Ambiguous correlations escalate via `NEEDS_INPUT.md` per the rich-body convention in `~/.claude/skills/_components/sentinel-frontmatter.md`; the orchestrator surfaces them on its next cycle.
4. **NEVER actively wait.** Like the orchestrators it serves, this skill MUST NOT poll the filesystem, call `Monitor`, or use sleep loops to wait for files to appear. If args reference missing files, record them in `missing_inputs` and report at the end — do NOT retry.

---

## Step 0: Resolve inputs

Default staging path: `docs/gemini-sprint/results/` relative to the current working directory.

1. Resolve `<staging-dir>` = `${CWD}/docs/gemini-sprint/results`.

2. **Parse `$ARGUMENTS`.** Split into whitespace-separated tokens. Each token is treated as a path to a research file (absolute, relative to `$CWD`, or `~/`-prefixed for home expansion). For each token:

   a. Expand `~/` and resolve to an absolute path.
   b. Verify the path exists and is a regular file (not a directory, not a symlink to a non-existent target). If missing, record the path in a `missing_inputs` list and skip it — do NOT abort the whole skill; other inputs may still be processable.
   c. Verify the file is plausibly text (`.txt`, `.md`, or readable as UTF-8). If binary, record in `invalid_inputs` and skip.

   Build `<external_inputs>` = list of validated absolute paths from args.

3. **Decide the operating mode:**

   - **Args supplied AND `<external_inputs>` is non-empty:** "one-off mode" — Step 0.5 copies each external input into the staging dir, then Step 1 proceeds as normal. If `missing_inputs` or `invalid_inputs` are non-empty, surface them in the final summary but continue processing whatever IS valid.
   - **Args supplied AND `<external_inputs>` is empty (all missing/invalid):** print the input-validation failures and STOP. No staging dir scan — the user asked for specific files, none of which were usable.
   - **No args:** "default mode" — Step 0.5 is a no-op; Step 1 scans the staging dir directly.

4. **Verify the staging dir is reachable.**

   - If `<staging-dir>` does not exist AND no args were supplied: exit cleanly with a one-line report:

     > `/ingest-research`: no staging directory at `docs/gemini-sprint/results/` — nothing to ingest.

     Return exit code 0. This is a no-op, not an error.

   - If `<staging-dir>` does not exist AND args were supplied: create it (`mkdir -p`). Step 0.5 needs it as the copy destination.

   - If `<staging-dir>` exists AND no args were supplied AND it contains zero `.txt` files (excluding `_consumed/`): exit cleanly with:

     > `/ingest-research`: staging directory empty — nothing to ingest.

(Per-repo configurability is deferred — AlgoBooth is the only consumer today. If another repo adopts the pattern, parameterize the staging path via a per-repo `.claude/skill-config/gemini-sprint.md` later.)

---

## Step 0.5: Stage external inputs (one-off mode only)

Skip this step in default mode (no args).

For each path in `<external_inputs>`:

1. Compute the destination basename. Prefer the original basename. If the original extension is `.md`, rename to `.txt` for staging (the staging dir convention is `.txt`; the format is identical, only the extension matters).
2. Compute `<staged-path>` = `<staging-dir>/<basename>`.
3. If `<staged-path>` already exists (collision with a previously staged or current-batch file), suffix the basename with `-<ISO8601-compact-timestamp>` (e.g., `voice-synthesis-20260521T103045Z.txt`) so the original staged file is not clobbered.
4. **Copy** the external file to `<staged-path>` using `Bash` (`cp` — NOT move). Preserving the original on disk is intentional: the user may have the file in a synced folder where deletion would propagate to other devices.
5. Record the mapping `(original_path → staged_path)` for the final summary.

After all external inputs are copied, the staging dir contains every `.txt` to process — both the user's standalone uploads (if any pre-existed) AND the newly-staged external inputs. Step 1 onward treats them uniformly.

---

## Step 1: Inventory results and prompts

1. List all `.txt` files directly under `<staging-dir>` (NOT recursive — `_consumed/` is excluded). Record absolute paths.
2. List all `RESEARCH_PROMPT.md` symlinks (or files) under `docs/gemini-sprint/prompts/`. These point back into individual feature directories — read each and record:
   - `<prompt-path>` (the symlink/file in `prompts/`)
   - `<prompt-target>` (the resolved real path, which lives under `docs/features/.../<feature-id>/RESEARCH_PROMPT.md`)
   - `<feature-id>` (the parent directory of the resolved path)
   - First ~30 lines of the prompt (themes, named entities, open questions) — used for correlation in Step 2.

If `docs/gemini-sprint/prompts/` does not exist or is empty, every `.txt` file becomes "ambiguous correlation" — write `NEEDS_INPUT.md` per Step 4 for each, do not write any `RESEARCH.md`, and report.

---

## Step 2: Correlate each `.txt` to a feature

For each `<result-txt>` from Step 1:

### 2a. Read the result

`Read` the `.txt` file in full (capped at ~50KB for the heuristic check; the full file is what gets written to RESEARCH.md in Step 3).

### 2b. Score against each prompt

For each prompt from Step 1's inventory, compute a coarse correlation:

- **Strong signal:** the `.txt` body directly mentions the feature-id (slug form, e.g. `voice-synthesis-v2`) OR the feature's human-readable name OR multiple named entities/headings that appear in the prompt's first 30 lines.
- **Moderate signal:** the `.txt` answers ≥2 of the prompt's listed open questions / research topics (heading match or topical paraphrase).
- **Weak signal:** generic topical overlap only (no named entities, no question alignment).

Pick the highest-scoring prompt. The correlation is **unambiguous** when:

- Exactly one prompt has a Strong signal, OR
- Exactly one prompt has Moderate signal AND no other prompt has any signal, OR
- The `.txt` file's basename matches the feature-id directly (e.g. `voice-synthesis-v2.txt` → `voice-synthesis-v2/`). Filename match alone is sufficient.

Otherwise the correlation is **ambiguous** — multiple prompts tie, or no prompt scores above Weak.

### 2c. Handle the correlation

- **Unambiguous:** proceed to Step 3 for this `<result-txt>`.
- **Ambiguous:** write `NEEDS_INPUT.md` per Step 4 — scoped to this single `.txt` only, do NOT halt the other ingestions. The other `.txt` files continue independently.

---

## Step 3: Write per-feature artifacts (unambiguous correlations only)

For each unambiguous `(<result-txt>, <feature-id>, <feature-dir>)` pairing:

### 3a. RESEARCH.md

Compute `<research-md>` = `<feature-dir>/RESEARCH.md`.

- **If `<research-md>` already exists:** skip the write and record a warning for the final report: `"already had RESEARCH.md — skipping <feature-id>"`. Do NOT overwrite. Do NOT move the `.txt` to `_consumed/` either — the human may want to compare. Continue to the next `.txt`.
- **Otherwise:** write the `.txt` content verbatim to `<research-md>`. No frontmatter, no preamble — this is the raw Gemini output, preserved as-is for audit.

### 3b. RESEARCH_SUMMARY.md

Compute `<research-summary-md>` = `<feature-dir>/RESEARCH_SUMMARY.md`.

Distill the research per `/spec`'s Phase 3 pattern:

```markdown
# Research Summary — <feature human name>

*Distilled from Gemini deep research; full source in `RESEARCH.md`.*

## Executive summary

<One paragraph (3-5 sentences) capturing the core finding(s) the spec
finalization needs. Frame it from the implementor's perspective — what
constraints does this impose, what options does it open up, what's the
recommended path.>

## Key answers

- **<Open question 1 from prompt>:** <one- or two-sentence answer drawn from RESEARCH.md.>
- **<Open question 2>:** <answer.>
- **<Open question 3>:** <answer.>
  ... (one bullet per question the prompt enumerated; if the prompt was open-ended, use the major topical sections of the research instead.)

## Risks / caveats

- <Any unresolved ambiguity, conflicting sources, or "verify during Phase N" call-outs.>
- <Anything Gemini flagged as low-confidence or speculative.>

## References

<List any URLs, papers, or repos Gemini cited. If none, omit this section.>
```

Write to `<research-summary-md>`. If the file already exists, skip and warn (mirror RESEARCH.md handling).

### 3c. SPEC.md trailer + Status

`Read` `<feature-dir>/SPEC.md`.

1. **Drop the `> Draft (pre-Gemini)` trailer** — typically a blockquote at the bottom of SPEC.md noting that this is a stub-style draft pending research. Match the canonical AlgoBooth pattern (a blockquote starting with `> Draft (pre-Gemini)` or similar prefix; be lenient about phrasing). Remove the entire trailer block (the contiguous lines starting with `> ` that contain "pre-Gemini" or "Draft (pre-Gemini)"), and the blank line preceding it if present. If no such trailer exists, this step is a no-op.
2. **Bump `**Status:**`** from `Draft` to `Ready` IF the current Status line reads `**Status:** Draft` (or any of the pre-Gemini draft variants like `Draft (research stub)`, `Draft (pre-Gemini)`). Other Status values (`Ready`, `Complete`, `Superseded`) are left alone. The status bump signals that the spec is no longer pending research — `/spec` Phase 3 will own any further status transitions during finalization.

Apply both edits via `Edit` tool calls. If the file does not exist (shouldn't happen if the prompt symlink resolved here, but defensively), skip and warn.

### 3d. queue.json — clear `"stub": true`

`Read` `docs/features/queue.json`. Find the queue entry where `id == <feature-id>`. If the entry has `"stub": true`, remove that key (NOT set to `false` — remove the key entirely so the on-disk shape stays minimal). Other fields are untouched. Write the file back, preserving its existing JSON formatting (2-space indent, trailing newline) as closely as possible.

If `queue.json` does not exist or the entry is missing, skip and warn — `/ingest-research` should not invent queue entries.

### 3e. Move the consumed `.txt`

Create `<staging-dir>/_consumed/` if it does not exist.

Move `<result-txt>` to `<staging-dir>/_consumed/<basename>`. Use `Bash` (`mv`) — this is a filesystem move, not a content edit. If a file with the same basename already exists in `_consumed/` (re-ingest of the same `.txt`), suffix with `-<ISO8601-timestamp>` before moving.

### 3f. Per-feature commit

Stage the writes for this `<feature-id>` and commit per the project's commit policy:

- Try `.claude/skill-config/commit-policy.md` first.
- If absent, use the standard pattern.
- Commit message: `docs(<feature-id>): ingest Gemini research`

Files in the commit (when present): `<feature-dir>/RESEARCH.md`, `<feature-dir>/RESEARCH_SUMMARY.md`, `<feature-dir>/SPEC.md`, `docs/features/queue.json`, `<staging-dir>/_consumed/<basename>` (the move).

Do NOT push. The orchestrator (or the human) decides when to push.

---

## Step 4: Ambiguous correlation — write `NEEDS_INPUT.md`

For each ambiguous `<result-txt>`, write a per-`.txt` `NEEDS_INPUT.md` at the staging dir level so a human can resolve the correlation:

Compute `<sentinel-path>` = `<staging-dir>/<basename-without-ext>.NEEDS_INPUT.md`. (One sentinel per ambiguous `.txt`, named to disambiguate when multiple ambiguities exist in one run.)

Write per `~/.claude/skills/_components/sentinel-frontmatter.md`. The frontmatter:

```yaml
---
kind: needs-input
feature_id: gemini-sprint-ingestion
written_by: ingest-research
decisions:
  - "Correlate <basename>.txt to a feature in the queue"
date: <today>
next_skill: ingest-research
partial_artifacts: []
---
```

The body MUST use the **rich-body convention** (`## Decision Context` H2 with one H3 per `decisions[i]`, each carrying `**Problem:**` / `**Options:**` / `**Recommendation:**`). Skeleton:

```markdown
# /ingest-research — Needs Input

## Decision Context

### 1. Correlate <basename>.txt to a feature in the queue

**Problem:** The Gemini result at `<staging-dir>/<basename>.txt` did not score
unambiguously against any single feature's `RESEARCH_PROMPT.md`. Top candidates
(by signal strength): <list 2-4 candidates with their scoring rationale —
e.g., "feature-A: filename overlap only; feature-B: 2 question matches but no
named entities">. Picking arbitrarily risks writing the wrong RESEARCH.md and
poisoning Phase 3 finalization.

**Options:**
- **<feature-A>** — <description of why this might be the intended target; what the .txt covers that aligns with feature-A's prompt; tradeoff if wrong: <impact>.>
- **<feature-B>** — <same shape.>
- **<feature-C>** — <same shape; optional, max 4 options.>
- **Discard / re-run Gemini** — the `.txt` doesn't match any active feature in `queue.json`; move it out of `results/` and re-run Gemini against a correctly-staged prompt.

**Recommendation:** <feature-X> — <one-sentence justification, or "no strong signal — discard and re-run Gemini" if all options are equally weak.>
```

**Echo the entire `## Decision Context` section to chat output** before returning (per Producer responsibilities in `sentinel-frontmatter.md`). The orchestrator (`/lazy-batch`) will re-print the body and call `AskUserQuestion` on its next cycle.

Do NOT move the ambiguous `.txt` to `_consumed/` — leave it in place so the human can decide.

---

## Step 5: Final summary

After all `.txt` files have been processed (ingested or escalated), print a summary block:

```
## /ingest-research — Done

**Mode:** <"default (staging-dir scan)" | "one-off (N path args)">
**Staging:** <staging-dir>
**Staged external inputs:** <list of (original_path → staged_path), or "none" in default mode>
**Input validation failures:** <list of (path, reason) for missing/invalid args, or "none">
**Ingested:** N features
  - <feature-id-1>: RESEARCH.md (<bytes>), RESEARCH_SUMMARY.md (<bytes>), SPEC.md trailer dropped, queue.json stub cleared
  - <feature-id-2>: ...
**Ambiguous (NEEDS_INPUT.md written):** M
  - <basename>.txt → <sentinel-path>
**Skipped (already had RESEARCH.md):** K
  - <feature-id-K>: <result-txt-K> left in place
**Consumed:** <basename>.txt files moved to <staging-dir>/_consumed/

Next step:
  - If invoked standalone: re-run /lazy-batch (or /lazy-batch-cloud) to resume the autonomous pipeline. The state machine will pick up Step 5 ("integrate research" → /spec Phase 3) for every feature that now has RESEARCH.md.
  - If invoked via /lazy-batch Step 0.5 (pre-loop) or Step 1f (post-pause): control returns to the orchestrator, which continues the main loop.
  - If ambiguous correlations exist, the next orchestrator cycle will hit decision-halt mode (Step 1g) and prompt you to pick the right feature.
```

STOP.

---

## Notes

- This skill never invokes the work-log MCP tool. The dispatch counts as one orchestrator cycle, and the per-feature commits provide the audit trail.
- The skill is intentionally narrow — it does not run `/spec` Phase 3 itself. That's the next state-machine cycle's job, and keeping it separated lets `/spec` perform its own dep-block validation, cross-boundary checks, and finalization logic per its skill prose without coupling to ingestion mechanics.
- Idempotency: re-running this skill against an empty (or fully-consumed) staging directory is a clean no-op (Step 0 reports nothing to ingest). Re-running with the same `.txt` already in `_consumed/` is also fine — Step 3e timestamps the destination filename to avoid clobbering.
