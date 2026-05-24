## Ad-hoc Enqueue Protocol (shared)

**Off by default.** This protocol runs ONLY when the invocation supplied an ad-hoc task (see this skill's Step 0 argument parsing for the exact trigger). A normal invocation with no ad-hoc task skips this entirely and proceeds straight to the main loop.

**Goal:** insert the work the user is referencing at the **top** of `docs/features/queue.json` so the very next state probe picks it up first, ahead of the planned roadmap. The ad-hoc item is persisted like a real feature (real `spec_dir` under `docs/features/`, a ROADMAP.md row, and an `ADHOC_BRIEF.md` seed that routes the pipeline to `/spec`). From there it flows through the identical full pipeline (`/spec` → research gate → `/plan-feature` → `/execute-plan` → `/retro` → MCP → mark-complete) as any queued feature — nothing downstream is special-cased.

This runs **once**, before the loop. It is a bootstrap, not a per-cycle action.

### Steps

1. **Resolve the task text.**
   - If the invocation supplied explicit text, use it verbatim as the basis.
   - If the ad-hoc trigger was given with NO text, infer the task from the most recent user messages in this conversation. State your inference in one sentence and proceed. Only if the conversation is genuinely ambiguous (no clear single task), ask once via `AskUserQuestion` before continuing.

2. **Derive three values:**
   - `feature_id` — a kebab-case slug prefixed `adhoc-` (e.g. `adhoc-fix-login-redirect`). Lowercase letters, digits, and hyphens only.
   - `name` — a short human title (e.g. "Fix login redirect loop").
   - `brief` — ONE concise plain-text paragraph capturing what to do and why. No embedded newlines or quote characters that would break shell quoting. `/spec` expands this into the full SPEC; the brief is just a seed.

3. **Enqueue via the state script.** This is a deterministic file mutation — it prepends the queue entry (`tier: 0`, `adhoc: true`), creates `docs/features/<feature_id>/`, seeds `ADHOC_BRIEF.md`, and adds a ROADMAP.md row (creating `queue.json` / `ROADMAP.md` if absent):

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --enqueue-adhoc \
     --id "<feature_id>" --name "<name>" --brief "<brief>"
   ```

   Parse the JSON result (`enqueued`, `feature_id`, `spec_path`, `queue_position`, `queue_length`). If the script exits non-zero (e.g. the id is already queued, or `queue.json` is malformed), surface the error and STOP — do NOT proceed to the loop.

4. **Announce and proceed.** Print one line:

   ```
   ➕ Enqueued ad-hoc **{name}** (`{feature_id}`) at the top of the queue → {spec_path}
   ```

   Then continue to this skill's normal Step 1 loop. The next state probe returns the ad-hoc feature first and routes it to `/spec` (the state machine's Step 4 detects `ADHOC_BRIEF.md`).

### Notes

- **All file mutations are performed by the state script via `Bash`**, not by `Write`/`Edit`. For the batch orchestrators this means the enqueue does NOT touch the orchestrator's sentinel-only `Write`/`Edit` scope (HARD CONSTRAINT 1 is unaffected — the bootstrap is a `Bash` script call, not a file edit), and it is NOT a `Skill` dispatch (HARD CONSTRAINT 2 is unaffected).
- The bootstrap files (`queue.json`, `ROADMAP.md`, the spec dir + `ADHOC_BRIEF.md`) are committed by the first sub-skill cycle's commit alongside its own changes — the same way queue/ROADMAP edits ride along elsewhere in the pipeline. No separate commit is required from the wrapper/orchestrator.
- For single-dispatch skills (`/lazy`, `/lazy-cloud`): the enqueue is a `Bash` bootstrap, not a `Skill` call, so it does NOT count against the one-skill-per-invocation rule. The single allowed dispatch this invocation is the `/spec` the probe then returns.
