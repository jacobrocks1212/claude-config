---
name: lazy-batch
description: Autonomous orchestrator for the AlgoBooth (or any queue.json-driven) feature pipeline. Loops on lazy-state.py and spawns Opus subagents per cycle. Halts on BLOCKED.md, NEEDS_INPUT.md (post-research decision halt), queue-blocked-on-research (passive — resume by re-invoking after uploading research), or max-cycles cap.
argument-hint: <max-cycles, e.g. 10>
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch — Autonomous Pipeline Orchestrator

Drives the per-feature autonomous tail (`/spec-phases` → `/write-plan` → `/execute-plan` → `/mcp-test` → `/retro` → mark-complete) by looping on `~/.claude/scripts/lazy-state.py`. Each cycle spawns an Opus subagent that invokes the named sub-skill; the orchestrator (this skill, running in the main session) never touches source code, never invokes a skill directly, and never parses sentinel files manually.

This is the **workstation** orchestrator. The cloud variant is `/lazy-batch-cloud` (under `repos/algobooth/.claude/skills/lazy-batch-cloud/`); the two are coupled per CLAUDE.md.

---

## HARD CONSTRAINTS (non-negotiable)

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` status lines when performing the `__mark_complete__` action (which is a documentation-level update by definition, not a source-code edit). `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-halt mode) after `AskUserQuestion` returns. All other `Write`/`Edit` operations — source code, test files, plan files, PHASES.md — require subagent dispatch.
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference is exclusively via `lazy-state.py`. Sentinel files MAY be read by the orchestrator to confirm a write or to drive a pseudo-skill action.
4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to decision-halt mode (Step 1g) ONLY.** Outside Step 1g, the orchestrator MUST NOT call `AskUserQuestion`. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`) and append a `## Resolution` section before halting.
6. **The orchestrator MUST re-print the rich `## Decision Context` to chat BEFORE calling `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print is the load-bearing context. Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` (one missing the `## Decision Context` H2 with H3 subsections matching `decisions:` 1:1) — surface the malformation as a quality issue and halt instead (see Step 1g.1).
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` fires, the orchestrator halts cleanly (Step 1f). The user's next `/lazy-batch` invocation is the resume signal; the implicit contract is that by the time they re-invoke, they've made the research available via one of the supported upload paths.

---

## Step 0: Parse Arguments

`$ARGUMENTS` must contain a positive integer max-cycles (e.g. `5`, `10`). If empty, default to `10`. If non-numeric or `< 1`, refuse with:

> `/lazy-batch` requires a positive integer max-cycles. Usage: `/lazy-batch <N>`. Default: 10.

Initialize counters and per-session state:
- `cycle = 0`
- `max_cycles = <parsed>`
- `cycle_log = []` — each entry: `{cycle, feature, action, subagent_summary}`
- `research_pending = set()` — feature_ids whose `RESEARCH.md` is missing and an `NEEDS_RESEARCH.md` sentinel was dropped this session. Drives `--skip-needs-research` and the Step 1f wait trigger.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle so subsequent `lazy-state.py` calls skip past research-pending features instead of re-halting.

Print the start bookend:

```
## /lazy-batch — Starting
**Max cycles:** {max_cycles}
**Repo root:** {cwd}
```

---

## Step 0.5: Pre-loop staged-research ingest check

Before entering the main loop, check whether the user staged Gemini research uploads between sessions. This is the "resume after halt" entry point — a previous `/lazy-batch` invocation may have halted in Step 1f (research-wait), the user uploaded research in the meantime, and this invocation should pick it up automatically.

**Algorithm:**

1. Probe for staged `.txt` files:

   ```bash
   find docs/gemini-sprint/results -maxdepth 1 -name '*.txt' -type f 2>/dev/null | head -1
   ```

   If empty → no staged research, skip to Step 1.

2. If staged `.txt` files exist, dispatch `/ingest-research` as cycle 1 (counts against `max_cycles`):

   ```
   Agent({
     description: "lazy-batch pre-loop ingest-research dispatch",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <the prompt below>
   })
   ```

   **Subagent prompt:**

   ```
   You are advancing one cycle of the autonomous feature pipeline. The
   orchestrator detected staged Gemini research at session start —
   .txt file(s) are present in docs/gemini-sprint/results/.

   Working directory: {cwd}

   Action for this cycle:
     Invoke the /ingest-research skill with no arguments. It will scan
     docs/gemini-sprint/results/ for every .txt, correlate each to a feature
     via the prompt symlinks under docs/gemini-sprint/prompts/, write
     per-feature RESEARCH.md + RESEARCH_SUMMARY.md, drop the > Draft
     (pre-Gemini) trailer in SPEC.md, clear queue.json "stub": true, move
     consumed .txt files to _consumed/, and commit per feature.

   Operating mode: batch (--batch is implicit for /ingest-research — see its
   SKILL.md hard constraints).

   After the skill returns:
     1. Report the final summary block /ingest-research printed.
     2. List any ambiguous correlations (NEEDS_INPUT.md sentinels written) —
        the next orchestrator cycle will halt at decision-halt mode (Step 1g).
     3. Report which feature_ids now have RESEARCH.md on disk.

   You may NOT spawn further subagents. You MAY use Edit/Write under docs/
   per /ingest-research's hard constraints.
   ```

3. After dispatch:
   - Append to `cycle_log`: `{1, "—", "/ingest-research (pre-loop)", "<subagent summary>"}`.
   - Increment `cycle` to 1.
   - Enter the main loop (Step 1).

Direct `RESEARCH.md` drops into canonical feature directories don't require ingestion — `lazy-state.py` sees them at Step 5 and routes to `/spec` Phase 3 naturally. Step 0.5 is specifically for the staged `.txt` upload path.

If the user provided a one-off file path via `/ingest-research <path>` (run BEFORE `/lazy-batch`), that invocation handled the ingest in its own session — by the time `/lazy-batch` runs, `RESEARCH.md` already exists in the canonical location, and Step 0.5 is a no-op for that feature.

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run lazy-state.py

```bash
python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]
```

Pass `--skip-needs-research` whenever `skip_needs_research == true`. (The flag is added by Step 4 the first time a `needs-research` halt fires; once on, it stays on for the rest of the session so subsequent state queries advance past research-pending features instead of re-halting on the same one.)

If the script exits non-zero, surface the error, push a PushNotification, print the final batch report (see Step 2), and STOP.

Parse the JSON output. Extract: `feature_id`, `feature_name`, `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`, `notify_message`, `diagnostics`.

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`**: PushNotification with `notify_message`, print final batch report, STOP. Do NOT modify the sentinel; the human resolves it manually.
- **`needs-input`**: see Step 1g (decision-halt mode). Do NOT print the final batch report yet — Step 1g must re-print the rich `## Decision Context`, run `AskUserQuestion`, and append `## Resolution` before halting.
- **`needs-research`**: see Step 4 (research halt). After Step 4 writes `NEEDS_RESEARCH.md` and adds `feature_id` to `research_pending`, **DO NOT increment cycle**, flip `skip_needs_research = true`, and return to Step 1a — the next state-script call passes `--skip-needs-research` and either advances to a ready feature or returns `queue-blocked-on-research`.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode). Only reachable while `skip_needs_research == true` and `research_pending` is non-empty.
- **`needs-spec-input`** / **`queue-missing`**: PushNotification with `notify_message`, print final batch report, STOP. The orchestrator cannot start from nothing.
- **`all-features-complete`**: PushNotification `"ALL FEATURES COMPLETE — roadmap finished after {cycle} /lazy-batch cycle(s)."`, print final batch report, STOP.
- **`cloud-queue-exhausted`**: Unreachable for `/lazy-batch` (workstation variant); treat as `all-features-complete` defensively.

### 1c. Check the max-cycles cap

If `cycle >= max_cycles`:

```
PushNotification({ message: "lazy-batch hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP. Do NOT try to renew the cap automatically — the cap exists to bound runaway costs.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small sentinel-file write + commit, NOT a real skill that performs implementation work. Perform the action inline (orchestrator session) instead of dispatching a subagent. This is the spirit-preserving relaxation of HARD CONSTRAINT 1: sentinel files are documentation, and dispatching an Opus subagent to write a 10-line YAML block + run `git commit` wastes a full subagent's worth of context.

Follow `~/.claude/skills/lazy/SKILL.md` Step 3's protocol for each pseudo-skill exactly (the wrapper and orchestrator do the same thing here):

- **`__write_validated_from_skip__`** — read `<spec_path>/SKIP_MCP_TEST.md` frontmatter, write `<spec_path>/VALIDATED.md` (kind: validated, mcp_scenarios: [], result: all-passing, body note about the prior skip), then commit per the project's commit policy.
- **`__write_validated_from_results__`** — read `<spec_path>/MCP_TEST_RESULTS.md` frontmatter, extract `scenarios`, write `<spec_path>/VALIDATED.md` with those scenarios, then commit.
- **`__mark_complete__`** — update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token), delete `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` sentinels, set `<spec_path>/SPEC.md`'s `**Status:**` to `Complete`, then commit per project policy.

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: {sub_skill} on {feature_name} → <inline outcome>"`.
3. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

This saves one Opus dispatch per pseudo-skill action. On a typical feature lifecycle (workstation: 1 × `__write_validated_*` + 1 × `__mark_complete__` = 2 dispatches reclaimed; cloud: 1 × `__write_deferred_non_cloud__` minimum) the savings compound across a multi-feature queue pass.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else:

```
You are advancing one cycle of the autonomous feature pipeline.

Feature: {feature_name} ({feature_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Invoke the {sub_skill} skill with args: {sub_skill_args} --batch

Operating mode: batch
  - Do NOT ask interactive questions. Skills accept --batch and either auto-accept
    a recommended option or write NEEDS_INPUT.md and halt.
  - If the skill writes NEEDS_INPUT.md, do NOT attempt to resolve the decision —
    that's a halt for a human.

After the skill returns:
  1. If a commit policy file exists at .claude/skill-config/commit-policy.md,
     follow it. Otherwise commit per the standard pattern and push to the
     current branch. Skip commit only if the skill produced no file changes.
  2. Report a one-paragraph summary: what state was advanced, files modified,
     commit hash (or "no commit"), and any issues. Keep it under 8 lines so the
     orchestrator's per-cycle log stays compact.

You may NOT spawn further subagents. You MAY use Edit/Write on source code if
the dispatched skill requires it (e.g. /execute-plan does); follow the skill's
internal subagent-vs-orchestrator rules.
```

Dispatch:

```
Agent({
  description: "lazy-batch cycle {cycle+1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <the prompt above>
})
```

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, subagent's one-paragraph summary}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: /{sub_skill} on {feature_name} → {first-line-of-summary}"`.
3. Increment `cycle`. Return to Step 1a.

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

Triggered when `lazy-state.py --skip-needs-research` reports `queue-blocked-on-research` AND `research_pending` is non-empty (the orchestrator has already dropped at least one `NEEDS_RESEARCH.md` this session). The user's Gemini deep-research step is the blocker.

**This is a passive halt, NOT an active wait.** The orchestrator MUST NOT use `Monitor`, `sleep`, polling loops, or any other mechanism to block on filesystem events (HARD CONSTRAINT 7). Research arrives on the user's timeline — they may be away from their device for hours or days. The orchestrator announces the halt, surfaces every supported upload path, fires a PushNotification, and stops. The user's next `/lazy-batch` invocation is the implicit resume signal; Step 0.5 (pre-loop ingest check) and `lazy-state.py`'s normal flow auto-detect uploads on re-entry — no special detection is needed at resume time.

**Algorithm:**

1. **Announce the halt with upload instructions.** Print:

   ```
   ⏸  /lazy-batch paused — {N} feature(s) awaiting Gemini research.

   Pending: {comma-separated feature_ids from research_pending}

   When you have the research, choose any of these upload paths:

     ① Staged (recommended for the gemini-sprint workflow):
        Save the Gemini output as docs/gemini-sprint/results/<feature-id>.txt
        (one file per feature). On your next /lazy-batch run, Step 0.5 will
        auto-dispatch /ingest-research to correlate, distill, and integrate.

     ② Canonical drop (skip ingestion):
        Write the research directly as
        docs/features/.../<feature-id>/RESEARCH.md
        On your next /lazy-batch run, lazy-state.py routes straight to Step 5
        (integrate research → /spec Phase 3) — no ingestion step needed.

     ③ One-off file path (e.g. ~/Downloads/<file>.txt, phone-synced folder,
        anywhere outside the repo):
        Run /ingest-research <absolute-or-relative-path-to-the-file> first.
        That skill copies the file into the staging dir, correlates it, and
        writes RESEARCH.md + RESEARCH_SUMMARY.md. Then re-run /lazy-batch
        to resume the pipeline.

   Re-invoke with /lazy-batch {max_cycles} when ready.
   ```

   The instructions are intentionally verbose — this is the user's main contact point with the pipeline's pause state, and they may be reading it from a phone notification long after the cycle ran. Include every path so they can pick whichever matches their current device / workflow.

2. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {N} feature(s) awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

3. **Append to `cycle_log`:** `{cycle+1, "—", "⏸ research-wait (halt)", "{N} feature(s) pending: {feature_ids}"}`. DO NOT increment `cycle` — the halt is not a real cycle.

4. **Print the final batch report (Step 2)** with `terminal_reason = "queue-blocked-on-research"` and STOP. The orchestrator's turn ends; the user's next invocation re-enters via Step 0 → Step 0.5 → Step 1.

**Resume contract.** When the user re-invokes `/lazy-batch`, the natural flow handles every supported upload path:

| Upload path | Detected by | Handled by |
|-------------|-------------|------------|
| ① Staged `.txt` in `docs/gemini-sprint/results/` | Step 0.5's `find` probe | Step 0.5 dispatches `/ingest-research` (1 cycle) |
| ② Direct `RESEARCH.md` in feature dir | `lazy-state.py` Step 5 | normal main-loop dispatch of `/spec` Phase 3 |
| ③ One-off path | User ran `/ingest-research <path>` separately before `/lazy-batch`; that invocation copied the file to the staging dir and processed it. By the time `/lazy-batch` starts, `RESEARCH.md` is already in the canonical location | normal main-loop dispatch (path ② applies) |

No special resume detection is needed in `/lazy-batch`'s main loop — every upload path lands in a state the existing logic already handles.

**Cycle accounting at resume.** The new `/lazy-batch` invocation gets a fresh `max_cycles` budget. The previous session's cycle count is gone (no persistence layer — see Notes). This is by design: each `/lazy-batch <N>` run is a bounded budget the user authorizes.

### 1g. Decision-halt mode (`terminal_reason == "needs-input"`)

Triggered when `lazy-state.py` reports `needs-input`. A batch-mode sub-skill (post-research only — per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`) wrote `NEEDS_INPUT.md` with a genuine design choice. The orchestrator surfaces the choice to the user via `AskUserQuestion`, captures the answer, persists it to disk, and halts the loop.

**Algorithm:**

1. **Read and validate the sentinel.** The state script's `spec_path` field names the feature dir; the sentinel is at `{spec_path}/NEEDS_INPUT.md`.

   - Parse the YAML frontmatter (kind, feature_id, written_by, decisions, date).
   - Read the markdown body.
   - **Schema check:** the body MUST contain a `## Decision Context` H2 with one H3 subsection per `decisions[i]` (matching titles, 1:1). Each H3 MUST carry `**Problem:**`, `**Options:**`, and `**Recommendation:**` blocks per the rich-body convention in `sentinel-frontmatter.md`.
   - **If malformed** (missing `## Decision Context`, mismatched count, missing required subsections):

     ```
     ⚠️  NEEDS_INPUT.md missing required '## Decision Context' section (or
     subsections do not match decisions: 1:1). Writer skill: {written_by}.
     Halting without prompting — fix the skill so future halts emit the rich
     body, or supply input manually.

     File: {spec_path}/NEEDS_INPUT.md
     ```

     PushNotification with the same message, append `{cycle+1, feature_name, "🛑 needs-input (malformed)", "<writer> wrote NEEDS_INPUT.md without rich body"}` to `cycle_log`, print the final batch report, STOP. Do NOT call `AskUserQuestion` against a malformed file (HARD CONSTRAINT 6).

2. **Re-print the rich body to chat VERBATIM.** This is the load-bearing context the user needs BEFORE the truncated `AskUserQuestion` UI fires:

   ```
   🛑 /lazy-batch — Decision required

   Feature: {feature_name} ({feature_id})
   Writer:  {written_by}
   File:    {spec_path}/NEEDS_INPUT.md

   ─── ## Decision Context (from NEEDS_INPUT.md) ───────────────────────────

   {entire `## Decision Context` section verbatim, including all H3 subsections,
   Problem/Options/Recommendation blocks, and any prose around them — copy/paste
   the section as-is, no summarization.}

   ─────────────────────────────────────────────────────────────────────────
   ```

3. **Call `AskUserQuestion` per decision.** For each `decisions[i]` (1..N, capped at 4 per HARD CONSTRAINT — see `sentinel-frontmatter.md` Producer responsibilities), build one entry in the `questions` array:

   - `question`: the H3 subsection title, exactly (matches `decisions[i]`).
   - `header`: an 8-12 char chip extracted from the title (e.g., title "Storage backend for cached voices" → header "Storage").
   - `options`: parsed from the H3's `**Options:**` list. Each `- **<name>** — <description>` bullet becomes one option:
     - `label`: the bold `<name>`.
     - `description`: the first sentence of `<description>`. AskUserQuestion will truncate longer descriptions — the full text is already above in chat (step 2), so the truncation is non-fatal.
   - `multiSelect`: `false` unless the H3 explicitly says "select all that apply" or similar (rare — most decisions are mutually exclusive). When in doubt, default to `false`.

   Call `AskUserQuestion` once with all N questions in a single `questions` array (the tool supports up to 4 questions per call). Capture the response.

4. **Append `## Resolution` to NEEDS_INPUT.md.** Construct the Resolution block:

   ```markdown

   ## Resolution

   *Recorded on <YYYY-MM-DD HH:MM:SS UTC>.*

   ### 1. <decision[0] title>

   **Choice:** <selected option label>
   **Notes:** <user's free-text note if they chose "Other", or empty string>

   ### 2. <decision[1] title>

   **Choice:** ...
   ```

   Use the `Edit` tool to append this block to the existing `NEEDS_INPUT.md` — do NOT overwrite. Use the `Write` tool only as a fallback if `Edit` cannot find a unique insertion point at end-of-file (in practice, append by reading the file, concatenating the new section, and `Write`-ing the combined content back). HARD CONSTRAINT 1 allows this specific append.

5. **Commit the resolved sentinel.** Stage `NEEDS_INPUT.md` and commit per the project's commit policy:

   - First try `.claude/skill-config/commit-policy.md`; if absent, follow the standard pattern.
   - Commit message: `docs({feature_id}): record decision-halt resolution`

   Do NOT push (consistent with other orchestrator-inline commits).

6. **Append to `cycle_log`:** `{cycle+1, feature_name, "🛑 needs-input", "<N> decision(s) resolved; Resolution appended"}`. Increment `cycle` by 1.

7. **Halt with the final batch report.** Print the standard Step 2 report. The "Next step" guidance for `needs-input` reads:

   ```
   Apply the resolution(s) in {spec_path}/NEEDS_INPUT.md to the relevant
   SPEC.md / PHASES.md sections, delete NEEDS_INPUT.md (or leave it as the
   audit trail and delete the kind: needs-input frontmatter to neutralize
   the state-script halt), then re-run /lazy-batch to continue.
   ```

8. **DO NOT auto-edit SPEC.md / PHASES.md based on the user's choice.** Applying a design decision can ripple across multiple sections in non-obvious ways — the user has explicitly retained that authority ("the goal is to eliminate my waiting, not my decision-making autonomy"). The `## Resolution` section is the audit trail; the human's manual edit is what commits the decision to the spec/phases docs.

---

## Step 2: Final Batch Report

When the loop exits (terminal state or max-cycles), print:

```
## /lazy-batch — Done

**Cycles completed:** {cycle}/{max_cycles}
**Terminal reason:** {terminal_reason or "max-cycles"}
**Last notification:** {notify_message or "—"}

### Cycle log
| # | Feature | Action | Summary |
|---|---------|--------|---------|
| 1 | ... | /spec-phases | ... |
| 2 | ... | /write-plan | ... |
| ... |

**Next step:**
  - If terminal_reason is "blocked": resolve {spec_path}/BLOCKED.md
  - If terminal_reason is "needs-input": apply the `## Resolution` in {spec_path}/NEEDS_INPUT.md to SPEC.md / PHASES.md, delete the sentinel (or neutralize its frontmatter to keep the audit trail), then re-run `/lazy-batch {max_cycles}`
  - If terminal_reason is "queue-blocked-on-research": upload the research via any of the three paths shown in Step 1f's announcement (staged .txt in docs/gemini-sprint/results/, direct RESEARCH.md drop into the feature dir, or /ingest-research <path> for a one-off file path). Then re-run `/lazy-batch {max_cycles}`.
  - If terminal_reason is "needs-research": should not appear here — Step 4 drops the sentinel and continues the loop. Defensive fallback: upload research per the queue-blocked-on-research guidance above.
  - If max-cycles: re-run `/lazy-batch {max_cycles}` from a fresh session
```

STOP.

---

## Step 3: Status Bookend Discipline (per cycle)

For each cycle, also produce a brief bookend pair (in addition to the one-line status in 1e):

**Before cycle N:**
```
### Cycle {N} — {feature_name} ({sub_skill})
```

**After cycle N:** part of the one-line status above. Keep it compact — many cycles fit in a single batch session.

---

## Step 4: Research Sentinel Drop (terminal_reason == "needs-research")

The state script returns `needs-research` when `RESEARCH.md` is missing but `RESEARCH_PROMPT.md` exists. **Unlike the prior version of this skill, Step 4 does NOT halt** — it drops a sentinel, records the feature, flips `skip_needs_research = true`, and returns to Step 1a so the loop advances past this feature. The actual wait happens in Step 1f when `queue-blocked-on-research` fires.

**Algorithm:**

1. Check whether `{spec_path}/NEEDS_RESEARCH.md` already exists (a prior cycle may have already dropped it — this can happen when the orchestrator session restarts).
2. If it does NOT exist, write it per `~/.claude/skills/_components/sentinel-frontmatter.md`:

   ```markdown
   ---
   kind: needs-research
   feature_id: {feature_id}
   research_prompt_path: <relative path to RESEARCH_PROMPT.md from spec_path>
   written_by: lazy-batch
   date: <today>
   ---

   # /lazy-batch — Needs Research

   Run Gemini deep research against the prompt below, then provide the result
   via any of these upload paths:

   ① Staged .txt (gemini-sprint workflow): save the output as
     `docs/gemini-sprint/results/{feature_id}.txt`. /lazy-batch's Step 0.5
     pre-loop check will auto-dispatch /ingest-research on the next run.

   ② Direct RESEARCH.md drop: write the result directly to RESEARCH.md
     alongside this file. lazy-state.py Step 5 will route to /spec Phase 3
     on the next /lazy-batch run.

   ③ One-off file path: if the file lives outside the repo (e.g.
     ~/Downloads/<file>.txt), run /ingest-research <path> before re-invoking
     /lazy-batch. That skill stages and ingests it into the canonical
     location, then /lazy-batch picks it up via path ②.

   /lazy-batch waits passively while research is in flight — re-invoke when
   ready. The orchestrator does NOT poll the filesystem.

   **Prompt file:** `{research_prompt_path}`
   ```

3. Add `feature_id` to `research_pending`. Set `skip_needs_research = true`.
4. Append to `cycle_log`: `{cycle+1, feature_name, "needs-research (sentinel drop)", "NEEDS_RESEARCH.md written; flagging for Step 1f research-wait"}`. **DO NOT increment `cycle`** — this is a no-op state transition, not a real cycle. Sentinel writes here don't count against `max_cycles` either; cost discipline is preserved because the actual work of generating the prompt and running Gemini happens elsewhere.
5. Return to Step 1a. The next `lazy-state.py --skip-needs-research` call will either advance to the next feature in the queue (if any are ready) or return `queue-blocked-on-research` — at which point Step 1f's research-wait fires.

**Special pre-step:** if the state script returns `sub_skill: "spec"` with args that include "skip to Phase 2", the orchestrator dispatches it normally (this generates the RESEARCH_PROMPT.md). On the next cycle, the state script returns `needs-research` and this Step 4 fires. That's the intended two-cycle handoff for a feature with no research at all.

**Multi-feature accumulation:** Steps 1a → 4 → 1a (skip) → 4 (next feature) ... can fire repeatedly during the first pass through the queue, each time appending another feature_id to `research_pending` and dropping another `NEEDS_RESEARCH.md`. The pass terminates when the state script returns `queue-blocked-on-research` (every remaining feature is research-pending) OR when a ready feature is found (the loop dispatches it normally). Either way, the orchestrator never halts on `needs-research` itself — it batches the research backlog and waits once in Step 1f.

---

## Notes

- This skill never invokes the work-log MCP tool. Each sub-skill invoked by the cycle subagents logs its own work.
- The orchestrator is single-session by design — there is no persistence layer. State lives in the filesystem sentinels; restart is free.
- Commit policy is delegated to the cycle subagent (which follows the project's `.claude/skill-config/commit-policy.md` or standard pattern). The orchestrator does not commit anything itself except the NEEDS_RESEARCH.md sentinel, which is committed by the next sub-skill cycle's subagent (since the loop has already exited by the time it's written).
