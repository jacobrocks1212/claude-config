## Operator-Directed Halt-Resolution (shared — convert a problem-terminal into an AskUserQuestion-driven resume)

**Why this component exists.** A lazy-family batch orchestrator must NOT dead-end the
operator on a recoverable obstacle. The guiding rule: **when the orchestrator would
halt for ANY reason other than the cost bound (`max-cycles`) or genuine completion,
it instead re-prints the obstacle context, asks the operator (via `AskUserQuestion`)
how to proceed, enacts the choice, and CONTINUES the loop.** Only the operator's
explicit "Halt for manual fix" choice stops the run.

This is the catch-all handler. Two problem-terminals have their own richer
specialized handlers and are NOT routed here — they already follow the
ask-then-continue shape:

- `needs-input` → **decision-resume mode** (parses the rich `## Decision Context`,
  one `AskUserQuestion` per `decisions[i]`).
- `blocked` → **blocked-resolution mode** (re-prints the `BLOCKED.md` body, offers
  add-a-phase / defer / halt resolution paths).

THIS component handles the REMAINING problem-terminals that previously bare-`STOP`ed:
`completion-unverified`, `needs-spec-input`, and (where the skill has them)
`needs-research` / `queue-blocked-on-research`.

**Explicitly NOT routed here (these remain their existing terminal behavior):**

- `max-cycles` — the cost bound. A hard stop by design; never converted (the cap
  exists to bound runaway spend).
- `all-features-complete` / `all-bugs-fixed` — genuine success. The queue is done;
  there is nothing to resolve. Clean success stop.
- `cloud-queue-exhausted` / `device-queue-exhausted` — environment exhaustion. The
  resolution is environmental (re-run on a real-device host / workstation), not an
  in-session operator choice. Keep the existing informative stop (its
  `notify_message` already tells the operator which host to use).
- `queue-missing` — there is no queue to continue; nothing to ask about. Keep the
  existing stop (the operator must create `queue.json` / point the orchestrator at a
  directory first).

### Inputs

- `terminal_reason` — the state-script terminal that fired (one of the routed set above).
- `feature_name` / `feature_id` (`bug_id` in the bug pipeline) and `spec_path` — the
  feature the terminal is about (present for every routed terminal — all are
  feature-scoped).
- `notify_message`, `diagnostics` — from the state-script JSON.
- `{cwd}` — repo root.

### Algorithm

1. **Re-print the obstacle context to chat VERBATIM** (the load-bearing context BEFORE
   the truncated `AskUserQuestion` UI — the antidote to a zero-context halt):

   ```
   ⏯  /lazy-batch — {terminal_reason} (loop resumes after you choose a resolution path)

   Feature: {feature_name} ({feature_id})
   State:   {notify_message}
   File:    {spec_path}/   (relevant sentinel, if any, named below)

   ─── Context ─────────────────────────────────────────────────────────────

   {For a terminal backed by a sentinel/file, READ it and paste the relevant
   body verbatim — e.g. for completion-unverified, the SPEC `**Status:**` line +
   whether a receipt (COMPLETED.md / FIXED.md) exists; for needs-spec-input, what
   the dir contains; for needs-research, the RESEARCH_PROMPT.md head + char count.
   For a terminal with no file, paste notify_message + every `diagnostics` line.}

   ─────────────────────────────────────────────────────────────────────────

   Choose how the pipeline should proceed. After you answer, I enact your choice
   and resume the loop — unless you choose "Halt for manual fix".
   ```

2. **Call `AskUserQuestion` with ONE question — the resolution path.** `header`:
   "Resolution". Build the option set from the matrix below (the terminal-specific
   fix option first, then the universal options). The auto-provided **Other** lets
   the operator type a custom directive enacted verbatim. `multiSelect: false`.

   | terminal | terminal-specific fix option(s) (first) | universal options (always appended) |
   |----------|------------------------------------------|--------------------------------------|
   | `completion-unverified` | **Reopen & re-validate** — set `**Status:** In-progress` and let the pipeline re-run retro + MCP so a *gated* receipt is earned. · **Grandfather the receipt** — only if the work was genuinely validated before the gate existed: write a `provenance: backfilled-unverified` receipt (honest debt). | Defer & continue queue · Halt for manual fix |
   | `needs-spec-input` | **Provide spec direction** — operator's notes seed the SPEC baseline (the apply subagent dispatches `/spec` / `/spec-bug` with the direction, or writes an `ADHOC_BRIEF.md`-style seed). | Defer & continue queue · Halt for manual fix |
   | `needs-research` / `queue-blocked-on-research` | **Upload research now** — operator pastes/attaches the Gemini result in their NEXT message; the in-session resume protocol ingests it. · **Defer this research-pending feature & continue** — work the rest of the queue first. | Halt for manual fix |

   **Universal options (definitions):**
   - **Defer & continue queue** — move this feature's `queue.json` entry to the END
     of the `queue` array so the next actionable feature becomes current; leave any
     blocking sentinel in place. The feature resurfaces after the rest of the queue.
   - **Halt for manual fix** — keep all state untouched, `PushNotification` with
     `notify_message`, print the final batch report, STOP. The legacy escape hatch.

3. **If the choice is "Halt for manual fix":** do NOT mutate any state. Append
   `{cycle+1, feature_name, "🛑 {terminal_reason} (operator chose manual halt)", "<one line>"}`
   to `cycle_log`, `PushNotification` with `notify_message`, print the final batch
   report, and **STOP**. This is the ONLY path here that halts.

4. **If the choice is "Upload research now"** (research terminals only): do NOT
   dispatch an apply subagent. Print one line — "▶ Waiting for your research upload in
   the next message; I'll ingest it in-session and resume." — append a `cycle_log`
   note, and END THE TURN cleanly (this is a single-turn handoff, NOT an active wait —
   HARD CONSTRAINT 7). The operator's next-message upload triggers the in-session
   resume protocol; if they instead re-invoke later, the pre-loop ingest check picks
   it up. (This preserves the existing research-resume design while making "defer &
   keep working" a first-class alternative.)

5. **Otherwise, record + enact + continue.**
   a. Record the choice: for a sentinel-backed terminal, append a `## Resolution`
      block (chosen path + operator notes + timestamp) to that sentinel and commit
      (`docs({feature_id}): record {terminal_reason} resolution path`); for a
      file-less terminal, just carry the choice into the dispatch prompt.
   b. **Dispatch the Opus apply-resolution subagent** to ENACT the chosen path:

      ```
      You are enacting an operator-chosen resolution for a {terminal_reason} state in
      the autonomous pipeline, then clearing the obstacle so the loop can resume.

      Feature: {feature_name} ({feature_id})
      Working directory: {cwd}
      Spec path:         {spec_path}
      CHOSEN PATH: {option label}   NOTES: {operator note or "—"}

      Enact EXACTLY the chosen path (see the resolution matrix the orchestrator
      surfaced). Common enactments:
        • "Reopen & re-validate": set the SPEC `**Status:**` back to `In-progress`
          (and PHASES top-level if applicable); delete any premature receipt; the
          next loop cycle routes the feature back through retro + MCP. Do NOT write a
          gated receipt yourself.
        • "Grandfather the receipt": write the `provenance: backfilled-unverified`
          receipt (COMPLETED.md / FIXED.md) per the sentinel schema, with an honest
          body noting validation predates the gate. (Only if the operator's notes
          confirm the work was genuinely validated.)
        • "Provide spec direction": seed the SPEC from the operator's NOTES — invoke
          /spec (or /spec-bug) via the Skill tool with the direction, or write the
          baseline/brief the state machine needs to advance.
        • "Defer & continue queue": move this feature's docs/features/queue.json
          (or docs/bugs queue) entry to the END of the `queue` array (preserve valid
          JSON; a queue.topo-order advisory warning is acceptable for an
          operator-chosen defer). Leave sentinels in place.
        • "Other": enact the operator's NOTES faithfully with Edit/Write/Read/Bash
          and (if a skill fits) the Skill tool.

      NEUTRALIZING A BLOCKING SENTINEL (when the path resolves it): the state script
      keys its halts on the sentinel FILENAME (e.g. NEEDS_INPUT.md, BLOCKED.md,
      NEEDS_RESEARCH.md), NOT a frontmatter field — so RENAME the file (git mv to a
      *_RESOLVED*.md name) rather than flipping a `kind:` field, which would leave the
      halt firing next cycle.

      Commit per .claude/skill-config/commit-policy.md (or the standard pattern):
      `docs({feature_id}): enact {terminal_reason} resolution (<path>)`. Push the work
      branch. Report a one-paragraph summary (≤ 8 lines): what you enacted, which
      files/status/sentinels changed, and the commit hash.

      You may NOT spawn further subagents (no Agent). You MAY use the Skill tool and
      Edit/Write/Read/Bash.
      ```

      Dispatch `Agent({ description: "lazy-batch halt-resolve: {feature_name}",
      subagent_type: "general-purpose", model: "opus", prompt: <above> })`.

   c. **Record and continue the loop.** Append to `cycle_log`
      `{cycle+1, feature_name, "▶ {terminal_reason} (resolved: <path>)", "<subagent summary>"}`;
      emit the canonical per-cycle update block (`### Cycle {cycle+1}/{max_cycles} ·
      {feature_name} · {terminal_reason}`, `**Result:**` = "<path> enacted — <first
      line of summary>"); update `prev_cycle_signature = (feature_id,
      "__resolve_halt__", sub_skill_args, current_step)`; increment `cycle`; return to
      Step 1a. **DO NOT halt, DO NOT print the final batch report** (except the Halt
      path in step 3).

### Re-prompt note

If "Defer & continue queue" is chosen and the deferred feature is the ONLY remaining
actionable entry, the next probe returns the same terminal again and this handler
re-prompts — correct (there is nothing else to work). The operator breaks the cycle
by choosing the fix option, Other, or Halt. `max_cycles` bounds it regardless.

### Coupling note

Consumed by the batch orchestrators' Step 1b for the routed problem-terminals:
- `user/skills/lazy-batch/SKILL.md`
- `user/skills/lazy-bug-batch/SKILL.md`
- (cloud variants `lazy-batch-cloud` / `lazy-cloud` when propagated)

`needs-input` (decision-resume) and `blocked` (blocked-resolution) keep their own
bespoke handlers; this component is the catch-all for the rest.
