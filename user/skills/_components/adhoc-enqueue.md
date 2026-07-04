## Ad-hoc Enqueue Protocol (shared)

**Off by default.** This protocol runs ONLY when the invocation supplied an ad-hoc task (see this skill's Step 0 argument parsing for the exact trigger). A normal invocation with no ad-hoc task skips this entirely and proceeds straight to the main loop.

**Goal:** insert the work the user is referencing at the **top** of the correct queue so the very next state probe picks it up first, ahead of the planned roadmap. The item is persisted like a real work item (real `spec_dir`, an `ADHOC_BRIEF.md` seed). From there it flows through the identical full pipeline as any queued item — nothing downstream is special-cased.

- **Feature (default):** lands at the top of `docs/features/queue.json` (`tier: 0`, `adhoc: true`), with a `docs/features/<feature_id>/` spec dir, a ROADMAP.md row, and an `ADHOC_BRIEF.md` that routes the pipeline to `/spec` (full path: `/spec` → research gate → `/plan-feature` → `/execute-plan` → `/retro` → MCP → mark-complete).
- **Bug (`--type bug`):** lands at the top of `docs/bugs/queue.json` (via the **existing** `bug-state.py` enqueue — not a reimplementation), with a `docs/bugs/<bug_id>/` dir and an `ADHOC_BRIEF.md`. From there it flows through the bug pipeline (`/spec-bug` investigation → `/plan-bug` → `/execute-plan` → MCP → mark-fixed). Use this for a harden-harness spin-off or any "this is a defect, not a feature" item.

This runs **once**, before the loop. It is a bootstrap, not a per-cycle action.

### Steps

1. **Resolve the task text.**
   - If the invocation supplied explicit text, use it verbatim as the basis.
   - If the ad-hoc trigger was given with NO text, infer the task from the most recent user messages in this conversation. State your inference in one sentence and proceed. Only if the conversation is genuinely ambiguous (no clear single task), ask once via `AskUserQuestion` before continuing.

2. **Pick the type.** Default is `feature`. Choose `bug` ONLY when the item is a defect/regression (e.g. a `harden-harness` spin-off) — something that belongs in the bug pipeline, not the feature pipeline. If the calling skill's argument parsing did not specify a type, default to `feature` (behavior-equivalent to before this protocol gained types).

3. **Derive three values:**
   - `id` — a kebab-case slug prefixed `adhoc-` (e.g. `adhoc-fix-login-redirect`). Lowercase letters, digits, and hyphens only. (This is the `feature_id` for a feature, the `bug_id` for a bug.)
   - `name` — a short human title (e.g. "Fix login redirect loop").
   - `brief` — ONE concise plain-text paragraph capturing what to do and why. No embedded newlines or quote characters that would break shell quoting. `/spec` (feature) or `/spec-bug` (bug) expands this into the full SPEC; the brief is just a seed.

4. **Enqueue via the state script.** This is a deterministic file mutation — it prepends the queue entry, creates the spec dir, and seeds `ADHOC_BRIEF.md` (creating `queue.json` if absent). Run the variant for the chosen type:

   **Feature (default)** — prepends `tier: 0`, `adhoc: true` to `docs/features/queue.json`, creates `docs/features/<id>/`, adds a ROADMAP.md row:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --enqueue-adhoc \
     --id "<id>" --name "<name>" --brief "<brief>"
   ```

   **Bug (`--type bug`)** — routes into `docs/bugs/queue.json` via the existing `bug-state.py` enqueue, creates `docs/bugs/<id>/`:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --enqueue-adhoc --type bug \
     --id "<id>" --name "<name>" --brief "<brief>"
   ```

   (Equivalently `python3 ~/.claude/scripts/bug-state.py --enqueue-adhoc --type bug --id "<id>" --name "<name>"` — the `lazy-state.py --type bug` form delegates to it and additionally seeds the bug `ADHOC_BRIEF.md`.)

   **Optional `--deps a,b` (queue-dependency-dag):** when the ad-hoc item hard-depends on other queued/on-disk items of the SAME pipeline, append `--deps "<id>,<id>"` to either form. The ids land on the entry's `deps` field (the machine-enforced hard-dep projection), so the dep-gate holds the ad-hoc item until each dep is Complete/Fixed with a receipt instead of dispatching it out of order. Ids are validated (kebab-case; `bug:`/`feature:` prefixes are reserved for cross-pipeline vN and refused). Omit the flag for a dependency-free item — the entry shape is byte-identical to before.

   Parse the JSON result. If the script exits non-zero (e.g. the id is already queued, or `queue.json` is malformed), surface the error and STOP — do NOT proceed to the loop.

5. **Announce and proceed.** Print one line:

   ```
   ➕ Enqueued ad-hoc {type} **{name}** (`{id}`) at the top of the {features|bugs} queue
   ```

   Then continue to this skill's normal Step 1 loop. The next state probe returns the ad-hoc item first and routes a feature to `/spec` / a bug to `/spec-bug` (the state machine's Step 4 detects `ADHOC_BRIEF.md`).

### Notes

- **All file mutations are performed by the state script via `Bash`**, not by `Write`/`Edit`. For the batch orchestrators this means the enqueue does NOT touch the orchestrator's sentinel-only `Write`/`Edit` scope (HARD CONSTRAINT 1 is unaffected — the bootstrap is a `Bash` script call, not a file edit), and it is NOT a `Skill` dispatch (HARD CONSTRAINT 2 is unaffected).
- The bootstrap files (`queue.json`, `ROADMAP.md` for a feature, the spec dir + `ADHOC_BRIEF.md`) are committed by the first sub-skill cycle's commit alongside its own changes — the same way queue/ROADMAP edits ride along elsewhere in the pipeline. No separate commit is required from the wrapper/orchestrator.
- For single-dispatch skills (`/lazy`, `/lazy-cloud`): the enqueue is a `Bash` bootstrap, not a `Skill` call, so it does NOT count against the one-skill-per-invocation rule. The single allowed dispatch this invocation is the `/spec` (feature) or `/spec-bug` (bug) the probe then returns.
- **Type default is `feature`** — omit `--type` (or pass `--type feature`) and the behavior is byte-identical to before this protocol gained types. `--type bug` is purely additive: it changes only the destination queue + spec dir (`docs/bugs/` instead of `docs/features/`), reusing the existing `bug-state.py` enqueue rather than reimplementing it.
