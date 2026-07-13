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
`completion-unverified`, `stale_upstream`, `needs-spec-input` (**feature pipeline only**
— `bug-state.py` never emits it), and (feature pipeline only, and only under
`--allow-research-skip`) `needs-research` / `queue-blocked-on-research`.

**Consumers — batch loop vs single-dispatch (post-enact behavior differs).** The
batch orchestrators (`/lazy-batch`, `/lazy-bug-batch`) run a loop, so after enacting
they **continue the loop** (step 5c). The single-dispatch wrappers (`/lazy`,
`/lazy-bug`, `/lazy-cloud`) do exactly ONE meaningful action per invocation, so after
enacting they **STOP** — the enactment was this invocation's action and the NEXT
invocation continues from the enacted state. Everything before that (re-print →
`AskUserQuestion` → enact → neutralize-by-rename) is identical. Additionally, the
batch skills keep their richer bespoke `needs-input` (decision-resume) and `blocked`
(blocked-resolution) handlers; the **single-dispatch wrappers route `needs-input` and
`blocked` HERE too** (matrix rows below) since they have no bespoke handler.

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
- `all-remaining-deferred` (bug pipeline only — `bug-state.py`) — every open bug is
  operator-parked via `DEFERRED.md`. A deliberate park, not an obstacle: keep the
  informative stop (re-include a bug by deleting its `DEFERRED.md`).

### Inputs

- `terminal_reason` — the state-script terminal that fired (one of the routed set above).
- `feature_name` / `feature_id` (`bug_id` in the bug pipeline) and `spec_path` — the
  feature the terminal is about (present for every routed terminal — all are
  feature-scoped).
- `notify_message`, `diagnostics` — from the state-script JSON.
- `{cwd}` — repo root.

### Algorithm

**No meta-cap check** — `meta_cycles` is uncapped (operator decision 2026-06-14); the meta loop has no halt. The run's only hard stop remains the `forward_cycles >= max_cycles` cap (the forward-cycle ceiling at Step 1c of the calling orchestrator). `meta_cycles` is still tracked and displayed (as a bare count), but there is no `if meta_cycles >= …` halt in any resolution mode.

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
   and proceed (batch: resume the loop; single-dispatch: this invocation's action
   is done and the next run continues) — unless you choose "Halt for manual fix".
   ```

2. **Call `AskUserQuestion` with ONE question — the resolution path.** `header`:
   "Resolution". Build the option set from the matrix below (the terminal-specific
   fix option first, then the universal options). The auto-provided **Other** lets
   the operator type a custom directive enacted verbatim. `multiSelect: false`.

   | terminal | terminal-specific fix option(s) (first) | universal options (always appended) |
   |----------|------------------------------------------|--------------------------------------|
   | `completion-unverified` | **Reopen & re-validate** — set `**Status:** In-progress` and let the pipeline re-run MCP validation so a *gated* receipt is earned. (Retro is unwired — 2026-06; re-validate goes directly to the MCP gate.) · **Grandfather the receipt** — only if the work was genuinely validated before the gate existed: write a `provenance: backfilled-unverified` receipt (honest debt). | Defer & continue queue · Halt for manual fix |
   | `stale_upstream` (both pipelines — `STALE_UPSTREAM.md`) | **Re-materialize / absorb** — accept the changed upstream and re-run the materialize/realign step (the apply subagent dispatches `/realign-spec` or re-materializes), then neutralize `STALE_UPSTREAM.md` by rename. · **Reject** — the upstream change does not affect this item; neutralize the sentinel and proceed unchanged. | Defer & continue queue · Halt for manual fix |
   | `needs-spec-input` (**feature pipeline only**) | **Provide spec direction** — operator's notes seed the SPEC baseline (the apply subagent dispatches `/spec` with the direction, or writes an `ADHOC_BRIEF.md`-style seed). | Defer & continue queue · Halt for manual fix |
   | `needs-research` / `queue-blocked-on-research` (**feature pipeline only**, reachable here only under `--allow-research-skip`; the default strict-halt path stops at Step 4 before routing here) | **Upload research now** — operator pastes/attaches the Gemini result in their NEXT message; the in-session resume protocol ingests it. · **Defer this research-pending feature & continue** — work the rest of the queue first. | Halt for manual fix |
   | `blocked` (single-dispatch wrappers only — batch skills use bespoke Step 1h) | **Add a phase to resolve the blocker** — `/add-phase` (or `/plan-bug`) scoped to the blocker, then neutralize `BLOCKED.md`. SEAM-BATCHED SCOPE (mcp-validation blockers, ANY `retry_count`): the corrective phase MUST be scoped to the FULL `## Seam Enumeration` set BLOCKED.md already carries (every `probed-FAIL` + `unprobed` row), never a single-layer fix. VALIDATION ESCALATION (ADDITIONALLY, `retry_count >= 2` — state script flags `validation_escalation: true`): first dispatch an `/investigate` cycle per `~/.claude/skills/_components/investigation-dispatch.md` if no current `INVESTIGATION.md` exists; the corrective phase then ALSO consumes the artifact (confirmed ledger rows + fix scope) — never a fix built on orchestrator inference (see blocked-resolution.md step 1a). · **Other** custom directive. | Defer & continue queue · Halt for manual fix |
   | `needs-input` (single-dispatch wrappers only — batch skills use bespoke Step 1g) | **Resolve the decision(s)** — re-print the `## Decision Context` and `AskUserQuestion` the listed `decisions[i]` (one per decision, ≤ 4); the apply subagent propagates the choices into SPEC/PHASES and neutralizes `NEEDS_INPUT.md`. | Defer & continue queue · Halt for manual fix |

   **Universal options (definitions):**
   - **Defer & continue queue** — move this feature's `queue.json` entry to the END
     of the `queue` array so the next actionable feature becomes current; leave any
     blocking sentinel in place. The feature resurfaces after the rest of the queue.
   - **Halt for manual fix** — keep all state untouched, `PushNotification` with
     `notify_message`, print the final batch report, STOP. The legacy escape hatch.

3. **If the choice is "Halt for manual fix":** do NOT mutate any state.
   `PushNotification` with `notify_message`, then STOP per the wrapper's terminal
   output (batch: append the `cycle_log` halt entry + print the final batch report;
   single-dispatch: print the after-status bookend "halted on {terminal_reason}").
   This is the ONLY path here that halts.

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
          next loop cycle routes the feature back through MCP validation. (Retro is
          unwired — 2026-06; routing goes directly to the MCP gate.) Do NOT write a
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
      branch. WORK-BRANCH-ONLY: commit and push to the CURRENT branch only
      (`git rev-parse --abbrev-ref HEAD` at start); NEVER create a new branch,
      NEVER --force. Report a one-paragraph summary (≤ 8 lines): what you enacted,
      which files/status/sentinels changed, and the commit hash.

      You may NOT spawn further subagents (no Agent). You MAY use the Skill tool and
      Edit/Write/Read/Bash.
      ```

      Dispatch `Agent({ description: "lazy-batch halt-resolve: {feature_name}",
      subagent_type: "general-purpose", model: "opus", prompt: <above> })`.

   c. **Record, then continue (batch) or stop (single-dispatch).**
      - **Batch orchestrators (`/lazy-batch`, `/lazy-bug-batch`):** append to
        `cycle_log` `{forward_cycles + meta_cycles + 1, feature_name, "▶ {terminal_reason} (resolved: <path>)",
        "<subagent summary>"}`; emit the canonical per-cycle block per orchestrator-voice.md
        (heading `### Resolve — {terminal_reason} on {feature_name} [meta {meta_cycles+1}]`,
        `done` line = "<path> enacted — <first line of summary>"); update
        `prev_cycle_signature = (feature_id, "__resolve_halt__", sub_skill_args,
        current_step)`; increment `meta_cycles`; **return to Step 1a** (DO NOT halt, DO NOT
        print the final batch report — except the Halt path in step 3).
      - **Single-dispatch wrappers (`/lazy`, `/lazy-bug`, `/lazy-cloud`):** the
        enactment was this invocation's ONE meaningful action. Print the after-status
        bookend (Completed: "{terminal_reason} resolved — <path> enacted"; Next `/lazy`
        will: "continue from the enacted state") and **STOP**. The next invocation
        re-runs the state script and proceeds from the now-neutralized state.

### Re-prompt note

If "Defer & continue queue" is chosen and the deferred feature is the ONLY remaining
actionable entry, the next probe returns the same terminal again and this handler
re-prompts — correct (there is nothing else to work). The operator breaks the cycle
by choosing the fix option, Other, or Halt. The meta loop is **uncapped** (operator
decision 2026-06-14) — there is no meta-cycle ceiling and no meta halt. Each
re-prompt still increments `meta_cycles` (tracked + displayed as a bare count), but
the run's only hard stop is the forward-cycle cap (`forward_cycles >= max_cycles`).

### Coupling note

Consumed by, for the routed problem-terminals:
- **Batch orchestrators** (Step 1i): `user/skills/lazy-batch/SKILL.md`,
  `user/skills/lazy-bug-batch/SKILL.md`, and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.
- **Single-dispatch wrappers** (Step 2a): `user/skills/lazy/SKILL.md`,
  `user/skills/lazy-bug/SKILL.md`, and `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`.

In the **batch** consumers, `needs-input` (decision-resume) and `blocked`
(blocked-resolution) keep their own bespoke Step 1g/1h handlers; this component is the
catch-all for the rest. In the **single-dispatch** consumers, `needs-input` and `blocked`
ALSO route here (matrix rows above) — they have no bespoke handler.

Pipeline scoping: `needs-spec-input` and the research terminals are **feature pipeline
only** (`bug-state.py` does not emit them); `all-remaining-deferred` is **bug pipeline
only**. `stale_upstream` and the rest apply to both.
