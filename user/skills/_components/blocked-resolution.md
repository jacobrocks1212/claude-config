## Blocked-resolution mode (shared — `terminal_reason == "blocked"`)

**Why this component exists.** The blocked-resolution handler (Step 1h of the batch
orchestrators) is identical across the feature and bug pipelines except for pipeline
vocabulary. This is the single source; each consumer binds the pipeline tokens below,
then `!cat`s this file (the sibling of `decision-resume.md`).

### Pipeline binding (the consuming skill sets these immediately before the include)

| token | feature pipeline | bug pipeline |
|-------|------------------|--------------|
| `{SKILL}` | `/lazy-batch` (or `/lazy-batch-cloud`) | `/lazy-bug-batch` |
| `{STATE_SCRIPT}` | `lazy-state.py` | `bug-state.py` |
| `{ITEM}` | feature | bug |
| `{SPEC_ROOT}` | `docs/features` | `docs/bugs` |
| `{ADD_PHASE}` | `/add-phase` | `/add-phase` (or `/plan-bug` if `PHASES.md` is absent) |
| `{PUSH_RULE}` (apply subagent) | workstation: standard push · **cloud: push IMMEDIATELY after each commit (container-reclaim durability)** | workstation: standard push |

Runtime placeholders (`{feature_id}`, `{feature_name}`, `{spec_path}`, `{cwd}`, `{phase}`,
`{retry_count}`, `{blocker_kind}`, `{cycle}`, `{max_cycles}`) are filled from the
state-script JSON — **both** pipelines use the JSON field `feature_id` (the bug id rides in it).

Triggered when `{STATE_SCRIPT}` reports `blocked` — a cycle subagent (or a hand edit) wrote `BLOCKED.md` because it hit a genuine blocker it could not resolve autonomously (a missing upstream surface, an ambiguous failure, a real bug needing a planning decision). **`blocked` is no longer a terminal halt — and most blockers no longer ask.** STEP ONE is the blocker classification per `~/.claude/skills/_components/completeness-policy.md` §3 (step 1b below): a **sequencing-only** blocker — every resolution path converges on the same product behavior — is auto-resolved by standing policy (add-phase + fix now, or spin-off + dependency-gate + requeue), logged + push-notified, and the loop continues with NO question. Only a blocker embedding a **genuine product fork** takes the operator path: the orchestrator surfaces it via `AskUserQuestion`, captures the chosen resolution path, records it, dispatches an Opus apply-resolution subagent to ENACT that path (neutralizing `BLOCKED.md`), and **continues the loop**. The sole stopping exception is the explicit **Halt for manual fix** choice, which preserves the legacy stop-for-human behavior.

This replaces the old **zero-context halt** (a bare `PushNotification` + STOP that handed the operator a one-line `notify_message` and nothing actionable). The operator now sees the full blocker context in chat and directs how the pipeline proceeds.

**Algorithm:**

1. **Read the sentinel.** `{spec_path}/BLOCKED.md`. Parse the YAML frontmatter (`kind`, `feature_id`, `phase`, `blocked_at`, `retry_count`, and `blocker_kind` if present) and read the markdown body. Unlike `NEEDS_INPUT.md`, `BLOCKED.md` has no mandated rich-body schema — a thin body is NOT a malformation halt; proceed, noting in chat if the blocker context is sparse.

1b. **Classify the blocker FIRST (completeness-policy §3 — STEP ONE, before any re-print or question).** Apply the scope test from `~/.claude/skills/_components/completeness-policy.md`: does every resolution path converge on the same product behavior (the standard "fix now / defer / halt" shape)? If **YES — sequencing-only** — auto-resolve per the policy, NO `AskUserQuestion`. Pick the matching resolution:

   - **In-scope defect** (missing / under-scoped work within this {ITEM} — the common case) → the complete path: `{ADD_PHASE}` + fix now. Append the `## Resolution` block to `BLOCKED.md` (step 5 shape, with `**Chosen path:** Add a phase to resolve the blocker` and a `resolved_by: completeness-policy` line), then dispatch the apply-resolution subagent (step 6) with that path — the same machinery, minus the question.
   - **Discovered defect beyond this {ITEM}'s scope** → spin off `/spec-bug`: the apply subagent authors the bug doc directly (per the established dispatched-subagent pattern), cross-references BOTH docs (the new doc names its origin; the origin names the spin-off), dependency-gates the current {ITEM} if it cannot proceed without the fix, and requeues it to the END of `{SPEC_ROOT}/queue.json` (the Defer mechanics from step 3's option list). Record the chosen path in the `## Resolution` block (`resolved_by: completeness-policy`) before dispatch.
   - **Feature-scope growth** (the blocker reveals work that is a new feature, not a defect) → spin off a new {ITEM} via the `--enqueue-adhoc` bootstrap + a brief, cross-reference both ways, dependency-gate as needed. Same `## Resolution` + apply-subagent machinery.

   For every auto-resolution: emit one chat line — `⚖ policy: {blocker, ≤8 words} → {chosen path}[ · spun off {id}]` — fire `PushNotification` (`"spun off {id} — {reason}"` for spin-offs; the resolution one-liner otherwise), record a D7-digest entry, then record-and-continue per step 7. Spin-offs are pre-authorized (notify + log, no cap — never ask permission to spin off). Neutralization rules are unchanged: every path except a pure requeue-to-tail neutralizes `BLOCKED.md` by rename (see step 6); a dependency-gated requeue leaves `BLOCKED.md` in place exactly like the operator "Defer" path.

   If **NO** — the resolution paths embed a **genuine product fork** (two complete-but-different end states, a conflict with a SPEC Locked Decision, or a destructive / outward-facing operation) — fall through to steps 2–7: the existing verbatim re-print + `AskUserQuestion` flow, unchanged.

2. **Re-print the blocker context to chat VERBATIM** (HARD CONSTRAINT 6 applies here too — the load-bearing context BEFORE the truncated `AskUserQuestion` UI; this is the antidote to the old zero-context halt):

   ```
   🚧 {SKILL} — Blocked (loop resumes after you choose a resolution path)

   Feature: {feature_name} ({feature_id})
   Phase:   {phase}   ·   retry_count: {retry_count}   ·   blocker_kind: {blocker_kind or "—"}
   File:    {spec_path}/BLOCKED.md

   ─── BLOCKED.md body (verbatim) ──────────────────────────────────────────

   {entire markdown body — blocker description, evidence, and any recovery
   suggestion the cycle subagent recorded — copy/paste as-is, no summarization.}

   ─────────────────────────────────────────────────────────────────────────

   Choose how the pipeline should proceed. After you answer, I dispatch an Opus
   subagent to enact your choice (and neutralize BLOCKED.md), then resume the
   loop — unless you choose "Halt for manual fix".
   ```

3. **Call `AskUserQuestion` with ONE question — the resolution path.** `header`: "Resolution". Where the `BLOCKED.md` body names a concrete recovery (e.g. "add an `{ADD_PHASE}` Phase N for X"), adapt the matching option's `description` to reference it so the recommended path is specific to this blocker. The archetype options:

   - **Add a phase to resolve the blocker** — dispatch `{ADD_PHASE}` against this {ITEM} with the blocker as the new phase's motivation, then neutralize `BLOCKED.md`. The pipeline re-plans → implements → re-validates the {ITEM}. *Recommended when the blocker is missing / under-scoped work (the common case — e.g. a missing MCP surface a validation step needs).*
   - **Defer this {ITEM}; continue the rest of the queue** — move this {ITEM}'s `{SPEC_ROOT}/queue.json` entry to the END of the queue (`BLOCKED.md` kept in place) so the next actionable {ITEM} becomes current. The blocked {ITEM} resurfaces only after the rest of the queue is worked.
   - **Halt for manual fix** — keep `BLOCKED.md` untouched, `PushNotification`, print the final batch report, STOP. The legacy escape hatch for blockers you want to handle by hand.

   The auto-provided **Other** lets the operator type a custom directive, enacted verbatim by the apply subagent. Capture the choice + any free-text note. (`multiSelect: false` — the paths are mutually exclusive.)

4. **If the choice is "Halt for manual fix":** do NOT modify `BLOCKED.md`. Append `{cycle+1, feature_name, "🛑 blocked (operator chose manual halt)", "{phase}"}` to `cycle_log`, `PushNotification` with `notify_message`, print the final batch report (Step 2), and **STOP**. This is the ONLY path here that halts.

5. **Otherwise, append a `## Resolution` section to `BLOCKED.md`** recording the chosen path, the operator's note (if any), and a timestamp — same `Edit`-append pattern as decision-resume step 4 (HARD CONSTRAINT 1 permits appending `## Resolution` to `BLOCKED.md`):

   ```markdown

   ## Resolution

   *Recorded on <YYYY-MM-DD HH:MM:SS UTC>.*

   **Chosen path:** <option label>
   **Notes:** <operator's free-text note, or empty>
   ```

   Commit `BLOCKED.md` with message `docs({feature_id}): record blocker resolution path`. Do NOT push (consistent with other orchestrator-inline commits; the apply subagent pushes).

6. **Dispatch the Opus apply-resolution subagent to ENACT the chosen path.** Prompt:

   ```
   You are enacting an operator-chosen resolution for a BLOCKED {ITEM} in the
   autonomous pipeline, then neutralizing the blocker so the loop can resume.

   Feature: {feature_name} ({feature_id})
   Working directory: {cwd}
   Sentinel:          {spec_path}/BLOCKED.md  (read its body + the appended
                      `## Resolution` for the chosen path + operator notes)

   CHOSEN PATH: {option label}   NOTES: {operator note or "—"}

   Enact EXACTLY the chosen path:

   • "Add a phase to resolve the blocker":
       Invoke the {ADD_PHASE} skill (via the Skill tool — you MAY use it; you may
       NOT use Agent) against {feature_id}, authoring a new phase whose scope is
       the blocker described in BLOCKED.md (and any recovery the cycle subagent
       suggested). It appends the phase to PHASES.md (In-progress, with
       unchecked deliverables) per its own contract. Then NEUTRALIZE BLOCKED.md
       (see below). The next loop cycle's {STATE_SCRIPT} routes the {ITEM} to
       plan/implement the new phase.

   • "Defer this {ITEM}; continue the rest of the queue":
       Edit {SPEC_ROOT}/queue.json: move this {ITEM}'s entry to the END of the
       `queue` array (preserve valid JSON; the queue.topo-order rule may emit an
       advisory warning for a deferred hard-upstream — acceptable for an
       operator-chosen defer). LEAVE BLOCKED.md IN PLACE (the {ITEM} stays
       blocked; it simply no longer heads the queue). Do NOT neutralize.

   • "Other" (custom directive): enact the operator's NOTES as faithfully as you
     can with Edit/Write/Read/Bash and (if a skill fits) the Skill tool. If the
     directive resolves the blocker, neutralize BLOCKED.md; if it only changes
     course, follow the note's intent and say so in your summary.

   NEUTRALIZING BLOCKED.md (for every path EXCEPT "Defer"): {STATE_SCRIPT} keys the
   `blocked` halt on the FILENAME `BLOCKED.md` (NOT a frontmatter field), so a
   `kind:` edit does NOT clear the halt. Run:
     python3 ~/.claude/scripts/{STATE_SCRIPT} --neutralize-sentinel {spec_path}/BLOCKED.md
   The script performs the canonical rename to BLOCKED_RESOLVED_<YYYY-MM-DD>.md
   (git-mv-aware, collision-safe — it appends a numeric suffix if the target
   name already exists), preserving the audit trail including the `## Resolution`.
   Manual fallback (only if the script is unavailable):
   `git mv {spec_path}/BLOCKED.md {spec_path}/BLOCKED_RESOLVED_<YYYY-MM-DD>.md`.
   NEVER just flip a frontmatter field (this is a real bug that was hit in
   practice — the rename is mandatory).

   Then commit per .claude/skill-config/commit-policy.md (or the standard
   pattern); message `docs({feature_id}): enact blocker resolution (<path>)`.
   {PUSH_RULE}
   WORK-BRANCH-ONLY: commit and push to the CURRENT branch only
   (`git rev-parse --abbrev-ref HEAD` at start); NEVER create a new branch,
   NEVER --force.

   Report a one-paragraph summary (≤ 8 lines): what you enacted (the new phase
   title / the queue move / the custom edits), whether BLOCKED.md was neutralized
   (and to what filename) or deliberately kept, files touched, and the commit hash.

   You may NOT spawn further subagents (no Agent). You MAY use the Skill tool for
   {ADD_PHASE}, and Edit/Write/Read/Bash for everything else.
   ```

   Dispatch:

   ```
   Agent({
     description: "{SKILL} blocked-resolve: {feature_name}",
     subagent_type: "general-purpose",
     model: "opus",
     prompt: <the prompt above>
   })
   ```

7. **Record and continue the loop.**
   - Append to `cycle_log`: `{cycle+1, feature_name, "▶ blocked (resolved + enacted: <path>)", "<one-line subagent summary>"}`.
   - Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · blocked`, `**Result:**` = "<path> enacted — {first line of subagent summary}". No other prose.
   - Update `prev_cycle_signature = (feature_id, "__resolve_blocked__", sub_skill_args, current_step)` — the **4-tuple**. The synthetic sub_skill token distinguishes a blocked-resolution cycle from any real-skill cycle for the Step 1d loop-guard.
   - Increment `cycle`. Return to Step 1a. **DO NOT halt, DO NOT print the final batch report** (except the "Halt for manual fix" path at step 4). The next state-script call sees `BLOCKED.md` neutralized (Add-a-phase / Other) and routes the {ITEM} onward, or — for "Defer" — selects the next actionable {ITEM} now that the blocked one sits at the queue tail.

**Re-prompt note (Defer path).** If "Defer" is chosen and the blocked {ITEM} is the ONLY remaining actionable entry, the next probe returns `blocked` for it again and this handler re-prompts immediately — that is correct (there is nothing else to work). The operator breaks the cycle by choosing Add-a-phase, Other, or Halt. `max_cycles` bounds it regardless.

This eliminates the legacy zero-context blocked halt: sequencing-only blockers are auto-resolved under the completeness-first standing policy (logged + notified, never asked), and for genuine product forks the operator gets the full blocker context in chat and directs the pipeline (add a phase / defer / hand off) — the orchestrator enacts the choice and keeps going either way.

### Coupling note

Consumed (as Step 1h) by the batch orchestrators: `user/skills/lazy-batch/SKILL.md`,
`user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.
The single-dispatch wrappers route `blocked` through `_components/halt-resolution.md` (Step 2a).
When editing this component, run `grep -rl "blocked-resolution.md" ~/.claude/skills/` to confirm
the consumer set.
