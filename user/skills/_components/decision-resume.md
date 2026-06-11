## Decision-resume mode (shared — `terminal_reason == "needs-input"`)

**Why this component exists.** The decision-resume handler (Step 1g of the batch
orchestrators) is identical across the feature and bug pipelines except for pipeline
vocabulary. It was previously hand-copied into each skill and drifted (a cloud copy
kept a broken `kind:`-flip neutralization and a 3-tuple signature). This is the single
source; each consumer binds the pipeline tokens below, then `!cat`s this file.

### Pipeline binding (the consuming skill sets these immediately before the include)

| token | feature pipeline | bug pipeline |
|-------|------------------|--------------|
| `{SKILL}` | `/lazy-batch` (or `/lazy-batch-cloud`) | `/lazy-bug-batch` |
| `{STATE_SCRIPT}` | `lazy-state.py` | `bug-state.py` |
| `{ITEM}` | feature | bug |
| `{PUSH_RULE}` (apply subagent) | workstation: standard end push · **cloud: push IMMEDIATELY after each commit (container-reclaim durability)** | workstation: standard end push |

Runtime placeholders (`{feature_id}`, `{feature_name}`, `{spec_path}`, `{cwd}`,
`{written_by}`, `{cycle}`, `{max_cycles}`) are filled from the state-script JSON — note
**both** pipelines use the JSON field name `feature_id` (the bug id rides in it).

Triggered when `{STATE_SCRIPT}` reports `needs-input`. A batch-mode sub-skill (post-research only — per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`) wrote `NEEDS_INPUT.md` with a genuine design choice. The orchestrator first auto-resolves any **scope-class** decisions per the completeness-first standing policy (step 1b — D7, both modes, never asked), then surfaces the remaining product-class choice(s) to the user via `AskUserQuestion`, captures the answer, persists it to disk, **dispatches a Sonnet subagent to apply the choice to SPEC.md / PHASES.md and neutralize the sentinel**, and then **continues the loop** — there is no halt. The user retains decision-making autonomy over product-class choices (they answered the question); the apply step is mechanical propagation of the choice into the planning docs.

**Algorithm:**

1. **Read and validate the sentinel.** The state script's `spec_path` field names the {ITEM} dir; the sentinel is at `{spec_path}/NEEDS_INPUT.md`.

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

1b. **Completeness-policy scope resolution (D7 — runs FIRST, before composing any question; BOTH modes).** Apply the scope test from `~/.claude/skills/_components/completeness-policy.md` to EACH decision in the sentinel: would the end-state product behavior differ between the options? Every decision that is `class: scope` — or scope-shaped (options differ only in effort / sizing / sequencing / completeness) regardless of declared class — is auto-resolved to the **most complete option**, never asked:

   - Append a `## Resolution` block for the resolved decision(s) (same shape as step 4) carrying `resolved_by: completeness-policy`, with **Choice:** = the most complete option and **Notes:** = a one-line scope-test justification.
   - Emit one chat line per application — `⚖ policy: {decision, ≤8 words} → {chosen path}` — and record it for the run-end D7 digest.
   - If ALL decisions in the sentinel were scope-class: commit (step 5), dispatch the apply-resolution subagent (step 6 — note in the prompt that the choices were policy-resolved under D7, not operator-answered), and record-and-continue (step 7, with the `cycle_log` action `"▶ needs-input (D7 policy-resolved + applied)"`). Skip steps 2–3 entirely — no briefing, no `AskUserQuestion`.
   - If only SOME were scope-class: resolve those here, then proceed to step 2 with ONLY the remaining product-class decisions (the briefing, re-print, and `AskUserQuestion` cover only those).

   This step runs in default AND `--park` modes and PRECEDES the park/two-key logic — scope is resolved by standing policy (no two-key needed), mechanical two-key applies next (park mode, via `parked-flush.md`), and only the remaining product-class decisions are asked (or parked). Exceptions per the policy (Locked-Decision conflict, destructive/outward-facing ops, genuine ambiguity about "complete") stay product-class and fall through to the question.

2. **Print the Zero-Context Operator Briefing (2a), then re-print the rich body VERBATIM (2b).** Assume the operator has been away for hours and retains NO session context (and may be reading on mobile, where `AskUserQuestion` truncates). Emit BOTH, in order:

   **2a — Zero-Context Operator Briefing** (synthesized by the orchestrator; succinct — the operator should be fully caught up in under a minute):

   ```
   🛑 Decision needed — Operator Briefing

   **Where we are:** {2-4 sentences: which {ITEM}, what it is in plain terms, what pipeline
   stage we're at, what has already been done on it this session}
   **Why we halted:** {1-2 sentences per decision: the concrete issue that forced the halt,
   explained assuming zero prior context}
   **Original requirement at stake:** {1-2 sentences: the SPEC requirement / prior operator
   decision this choice affects}

   **Your options:**
   {For EACH decision, list EVERY option that will appear in AskUserQuestion, using the
   EXACT labels that will be used there. Per option: what it means in plain terms, pros,
   cons, and one line on fit — which is architecturally strongest, which best satisfies the
   original requirements. Close with the recommendation and WHY in 1-2 sentences.}
   ```

   The briefing explains the sentinel; it never replaces it. No analysis may appear only in the `AskUserQuestion` UI — everything the operator needs to decide must be in the briefing.

   **2b — Verbatim re-print.** This preserves the full sentinel context BEFORE the truncated `AskUserQuestion` UI fires:

   ```
   ❓ {SKILL} — Decision required (loop will resume after your answer)

   Feature: {feature_name} ({feature_id})
   Writer:  {written_by}
   File:    {spec_path}/NEEDS_INPUT.md

   ─── ## Decision Context (from NEEDS_INPUT.md) ───────────────────────────

   {entire `## Decision Context` section verbatim, including all H3 subsections,
   Problem/Options/Recommendation blocks, and any prose around them — copy/paste
   the section as-is, no summarization.}

   ─────────────────────────────────────────────────────────────────────────

   After you answer the AskUserQuestion prompts below, I will dispatch a
   Sonnet subagent to apply your choice(s) into SPEC.md / PHASES.md and
   neutralize NEEDS_INPUT.md, then immediately resume the loop. No
   manual re-run required.
   ```

3. **Call `AskUserQuestion` per decision.** For each `decisions[i]` (1..N, capped at 4 per HARD CONSTRAINT — see `sentinel-frontmatter.md` Producer responsibilities), build one entry in the `questions` array:

   - `question`: the H3 subsection title, exactly (matches `decisions[i]`).
   - `header`: an 8-12 char chip extracted from the title (e.g., title "Storage backend for cached voices" → header "Storage").
   - `options`: parsed from the H3's `**Options:**` list. Each `- **<name>** — <description>` bullet becomes one option:
     - `label`: the bold `<name>`.
     - `description`: the first sentence of `<description>`. AskUserQuestion will truncate longer descriptions — the full text is already above in chat (step 2), so the truncation is non-fatal.
   - `multiSelect`: `false` unless the H3 explicitly says "select all that apply" or similar (rare — most decisions are mutually exclusive). When in doubt, default to `false`.

   **The option set MUST exactly match the options presented in the step-2a briefing** — same labels, same count, recommendation marked `(Recommended)` and listed first. If the briefing and the sentinel's `**Options:**` list diverged, fix the briefing and re-print before calling `AskUserQuestion` — never introduce an option in the UI that wasn't explained in chat.

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

5. **Commit the resolved sentinel.** Stage `NEEDS_INPUT.md` (with the new `## Resolution`) and commit per the project's commit policy:

   - First try `.claude/skill-config/commit-policy.md`; if absent, follow the standard pattern.
   - Commit message: `docs({feature_id}): record decision resolution`

   Do NOT push (consistent with other orchestrator-inline commits).

6. **Dispatch the Sonnet apply-resolution subagent.** Build the prompt:

   ```
   You are applying a user-resolved design decision back into the {ITEM} docs.

   Feature: {feature_name} ({feature_id})
   Working directory: {cwd}
   Sentinel file:    {spec_path}/NEEDS_INPUT.md

   The user just answered the decision(s) in NEEDS_INPUT.md's `## Decision
   Context` section. Their answers are in the appended `## Resolution` section
   at the bottom of that file (date, per-decision Choice + optional Notes).
   Your job is to propagate those choices into the {ITEM}'s planning docs and
   neutralize the sentinel so the orchestrator's next {STATE_SCRIPT} call does
   not halt on it again.

   Steps:
     1. Read NEEDS_INPUT.md fully (frontmatter + Decision Context + Resolution).
     2. For EACH decision, locate the section(s) of {spec_path}/SPEC.md and/or
        {spec_path}/PHASES.md that the choice impacts. Apply the choice
        surgically: update the design narrative, the implementation plan, API
        shape, schema choice, dependency selection — whatever the decision
        touches. Keep edits scoped; the choice is the user's, your job is
        mechanical propagation. If a decision has no impact on either doc
        (rare — e.g., the question was about future-phase scaffolding not
        drafted yet), record that in your summary and move on.
     3. Neutralize NEEDS_INPUT.md so {STATE_SCRIPT} stops returning
        terminal_reason=needs-input on the next cycle. Run:
          python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel {spec_path}/NEEDS_INPUT.md
        The script performs the canonical RENAME to
        NEEDS_INPUT_RESOLVED_<YYYY-MM-DD>.md (git-mv-aware, collision-safe —
        it appends a numeric suffix if the target name already exists),
        preserving the audit trail at the new path. Manual fallback (only if
        the script is unavailable): `git mv {spec_path}/NEEDS_INPUT.md
        {spec_path}/NEEDS_INPUT_RESOLVED_<YYYY-MM-DD>.md`.
        DO NOT merely edit the frontmatter `kind:` field — {STATE_SCRIPT} keys
        the needs-input halt on the FILENAME `NEEDS_INPUT.md`, so a `kind:` flip
        leaves the file named NEEDS_INPUT.md and the halt FIRES AGAIN next cycle
        (this is a real bug that was hit in practice; it also leaves a
        `sentinel-kind-matches-filename` docs-consistency violation). The
        Decision Context + Resolution body MUST be preserved verbatim under the
        new filename.
     3b. Promote any follow-up sentinel (input-audit overflow). After the
        neutralization in step 3, check the spec dir for
        NEEDS_INPUT_FOLLOWUP_*.md files (written by the input-audit when more
        than 4 decisions overflowed the primary sentinel). If any exist, rename
        the LOWEST-numbered one to NEEDS_INPUT.md
        (`git mv {spec_path}/NEEDS_INPUT_FOLLOWUP_{N}.md {spec_path}/NEEDS_INPUT.md`)
        and note the promotion in your summary. {STATE_SCRIPT} keys the
        needs-input halt on the EXACT filename NEEDS_INPUT.md, so this promotion
        is what makes the next probe re-surface the follow-up decisions — a file
        left named NEEDS_INPUT_FOLLOWUP_{N}.md is invisible to the state script.
     4. Commit per .claude/skill-config/commit-policy.md (or standard pattern).
        Commit message: `docs({feature_id}): apply decision resolution to
        SPEC/PHASES`. {PUSH_RULE}
        WORK-BRANCH-ONLY: commit and push to the CURRENT branch only
        (`git rev-parse --abbrev-ref HEAD` at start); NEVER create a new
        branch, NEVER --force.
     5. Report a one-paragraph summary (under 8 lines): which files were
        edited, which sections changed, how each choice was applied, commit
        hash. If any decision was a no-op against SPEC/PHASES, say so
        explicitly so the orchestrator's cycle log is accurate. If step 3b
        promoted a follow-up sentinel, say so (which file was promoted) — the
        orchestrator notes it in the cycle summary and the next probe
        re-surfaces it.

   You may NOT spawn further subagents. You MAY use Edit/Write on SPEC.md,
   PHASES.md, and the sentinel — this dispatch exists to authorize exactly
   those edits.
   ```

   Dispatch:

   ```
   Agent({
     description: "{SKILL} decision-apply: {feature_name}",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <the prompt above>
   })
   ```

7. **Record and continue the loop.**
   - Append to `cycle_log`: `{cycle+1, feature_name, "▶ needs-input (resolved + applied)", "<N> decision(s); <one-line subagent summary>"}`.
   - Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · needs-input`, `**Result:**` = "decision(s) resolved + applied — {first-line-of-subagent-summary}". No other prose.
   - Update `prev_cycle_signature = (feature_id, "__apply_needs_input__", sub_skill_args, current_step)` — the **4-tuple** (matching every other signature; the Step 1d loop-guard compares 4-tuples). The synthetic sub_skill token distinguishes this from any real-skill cycle.
   - Increment `cycle`. Return to Step 1a. **DO NOT halt, DO NOT print the final batch report.** The next state-script call should see the neutralized sentinel and route to the natural next step for the {ITEM} (typically resuming the skill that wrote NEEDS_INPUT.md — `/write-plan` or `/execute-plan` — now that the design ambiguity is resolved).

This eliminates the legacy "answer → halt → manual SPEC/PHASES edit → re-run" friction. The user's autonomy is preserved in step 3 (the choice itself); steps 6–7 are bounded mechanical work delegated to Sonnet so the orchestrator's Opus context stays lean.

### Coupling note

Consumed (as Step 1g) by the batch orchestrators: `user/skills/lazy-batch/SKILL.md`,
`user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.
The single-dispatch wrappers (`/lazy`, `/lazy-bug`, `/lazy-cloud`) route `needs-input`
through `_components/halt-resolution.md` (Step 2a) instead — they do ONE action then STOP,
they don't loop. When editing this component, run
`grep -rl "decision-resume.md" ~/.claude/skills/` to confirm the consumer set.
