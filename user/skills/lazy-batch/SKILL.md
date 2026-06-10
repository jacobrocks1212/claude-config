---
name: lazy-batch
description: Autonomous orchestrator for the AlgoBooth (or any queue.json-driven) feature pipeline. Loops on lazy-state.py, spawns one Opus subagent per cycle, and drives the full tail (/spec → /plan-feature → /execute-plan → /retro → /mcp-test → __mark_complete__). A halt for any reason other than max-cycles presents an AskUserQuestion resolution path and resumes — only max-cycles, all-features-complete, environment-exhaustion, and missing-queue remain clean stops. Terminal action is __mark_complete__, gated by the MCP-coverage audit + completion-integrity gate.
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip] [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch — Autonomous Pipeline Orchestrator

Drives the per-feature autonomous tail (`/plan-feature` (= `/spec-phases` + `/write-plan` in one cycle) → `/execute-plan` → `/retro` → `/mcp-test` → mark-complete) by looping on `~/.claude/scripts/lazy-state.py`. Each cycle spawns an Opus subagent that invokes the named sub-skill; the orchestrator (this skill, running in the main session) never touches source code, never invokes a skill directly, and never parses sentinel files manually.

**Step ordering note:** `/retro` runs BEFORE `/mcp-test` (Step 8 retro → Step 9 MCP). `/retro` is a docs/analysis pass and runs identically in cloud and workstation; `/mcp-test` only runs on workstation (cloud defers). Behavior inside the loop is unchanged — the orchestrator dispatches whatever `lazy-state.py` returns.

This is the **workstation** orchestrator. The cloud variant is `/lazy-batch-cloud` (under `repos/algobooth/.claude/skills/lazy-batch-cloud/`); the two are coupled per CLAUDE.md.

---

## HARD CONSTRAINTS (non-negotiable)

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `COMPLETED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` / `PHASES.md` status lines when performing the `__mark_complete__` action (which is a documentation-level update by definition, not a source-code edit). `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns; the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. **`BLOCKED.md` may likewise be appended to** (not overwritten) with a `## Resolution` section by Step 1h (blocked-resolution mode) after `AskUserQuestion` returns; the orchestrator then dispatches an Opus subagent to enact the chosen resolution path (e.g. `/add-phase`, queue reorder) and neutralize the sentinel by **rename** (lazy-state.py keys the halt on the `BLOCKED.md` filename). All other `Write`/`Edit` operations — source code, test files, plan files, PHASES.md — require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference is exclusively via `lazy-state.py`. Sentinel files MAY be read by the orchestrator to confirm a write or to drive a pseudo-skill action.
4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to the resolution modes — decision-resume (Step 1g), blocked-resolution (Step 1h), and operator-directed halt-resolution (Step 1i) — ONLY for the orchestrator itself.** The guiding rule: a halt for ANY reason other than `max-cycles` (and the genuine all-done success / environment-exhaustion / no-queue stops listed in Step 1i) presents the operator an `AskUserQuestion` resolution path and continues the loop, rather than dead-ending. Outside Step 1g / 1h / 1i, the orchestrator MUST NOT call `AskUserQuestion` — with two additional permitted uses added by the Step 0 standing-directive protocol: (i) the one-time echo-back confirmation when a mid-run operator message implies a budget change, standing resolution mode, or early stop; and (ii) the budget-and-queue guard question when the run would otherwise end with budget and queue both remaining. These two uses are orchestrator-level confirmations of operator intent, not resolution-mode decisions about feature/bug content. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. Inside Step 1h, the orchestrator MUST `AskUserQuestion` for the resolution path against a `BLOCKED.md` (re-printing its body first), record the choice, dispatch the apply-resolution subagent to enact it, and **continue the loop** — `blocked` no longer halts the orchestrator either (except the operator-chosen "Halt for manual fix" path). (The legacy halt-on-needs-input behavior is gone; the user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation.) **This constraint scopes the orchestrator, not subagents it dispatches.** A `/spec` subagent dispatched at state-machine Step 4.5 (stub-spec detected) is allowed and expected to call `AskUserQuestion` during Phase 1 brainstorming — that's the legitimate design-conversation channel for a SPEC whose baseline doesn't exist yet. The orchestrator dispatches `/spec` exactly the same way it dispatches `/execute-plan` (one Agent call per cycle); whatever the dispatched skill does internally is its own contract. See "Stub specs vs structured-research-pending specs" below for the disambiguation rule.
6. **The orchestrator MUST print a Zero-Context Operator Briefing AND re-print the load-bearing context to chat BEFORE calling `AskUserQuestion`.** The operator may have been away for hours and retains NO session context (and may be reading on mobile, where `AskUserQuestion` truncates). In **Step 1g** the briefing (step 2a of the decision-resume component) catches them up from zero — what's being worked, why we halted, every option with pros/cons and fit against the original requirements, and a recommendation — followed by the verbatim `## Decision Context` re-print (step 2b); the `AskUserQuestion` option set MUST exactly match the options presented in the briefing (same labels, 1:1 — no option may appear in the UI that wasn't explained in chat first). Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` (one missing the `## Decision Context` H2 with H3 subsections matching `decisions:` 1:1) — surface the malformation as a quality issue and halt instead (see Step 1g.1). In **Step 1h** the load-bearing context is the `BLOCKED.md` body verbatim (no mandated rich-body schema — a thin body is NOT a malformation halt; re-print whatever is there and note in chat if it is sparse); in **Step 1i** it is the obstacle context the shared `halt-resolution.md` mandates. The same zero-context briefing discipline (catch the away operator up from zero before asking) applies to Step 1h/1i.
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **TWO session-global monotonic counters replace the single `cycle` counter.** Both are initialized once in Step 0 and NEITHER is ever reset on feature transitions.
   - **`forward_cycles`** — counts pipeline-advancing work. Ceiling: `max_cycles`. Incremented by: (a) real-skill dispatch cycles (Step 1e step 5) and (b) pipeline-advancing pseudo-skills at Step 1c.5 (`__mark_complete__`, `__mark_fixed__`, `__write_deferred_non_cloud__`, `__write_validated_from_results__`, `__write_validated_from_skip__`, `__flip_plan_complete_cloud_saturated__`). **Capped at Step 1c** (`if forward_cycles >= max_cycles` → the existing max-cycles halt).
   - **`meta_cycles`** — counts resolution / recovery / audit / cleanup work. Ceiling: `2 * max_cycles`. Incremented by: Step 1g (decision-resume), Step 1h (blocked-resolution), Step 1i (operator-directed halt-resolution), LOOP-DETECTED / Step 1e.4a recovery dispatches, the input-audit cycle at Step 1d.5, and the stale-plan flip pseudo-skill `__flip_plan_complete_stale__`. **Capped at the TOP of every resolution mode**: the `if meta_cycles >= 2 * max_cycles:` check is inserted at the START of Step 1g, Step 1h, and Step 1i, which halts with a clear "meta-cycle cap (2× max_cycles) reached" message + PushNotification + final report. This cap check is what makes the resolution-path loop BOUNDED — without it, a Defer→same-terminal re-prompt cycle is unbounded.
   - **Input-audit (Step 1d.5):** audits are NOT counted as separate cycles (they share the real-skill cycle's slot in `cycle_log` and do NOT increment either counter). This keeps audit costs outside the budget. The meta cap still bounds the surrounding loop.
   - **Running total for cycle_log index:** use `forward_cycles + meta_cycles` as the monotonic `N` in cycle-log entries and per-cycle headings (i.e., the N-th action in this invocation regardless of type). `prev_cycle_signature` is a tuple of ids, unaffected.
   - Cycle N's per-cycle heading always refers to the N-th action in this invocation, regardless of which feature it operated on. A feature transition is NOT a fresh batch; the orchestrator runs ONE log across every feature it touches.

9. **Dispatch ONLY against the feature `lazy-state.py` returned THIS cycle; never fabricate a feature.** The orchestrator dispatches a cycle subagent against exactly the `feature_id` + `spec_path` from the current cycle's `lazy-state.py` output, verbatim. It MUST NOT invent, infer, or hand-edit a `feature_id`/slug that the state script did not emit. The state script (Step 2) already skips any queue entry whose `spec_dir` does not resolve on disk (emitting a `dangling queue entry` diagnostic) — so a real feature ALWAYS has an on-disk `spec_path` before dispatch. The cycle subagent prompt MUST forbid the subagent from CREATING a feature's `SPEC.md`/`RESEARCH.md`/`queue.json`/`ROADMAP.md` entries from a bare slug: the only sanctioned dir-creating paths are the `--enqueue-adhoc` bootstrap (Step 0.45) and a `/spec` dispatch against an already-seeded directory. If a cycle's `feature_id` does not correspond to an on-disk `spec_path`, that is a bug to surface (halt + report) — NEVER a cue to manufacture the feature. (This guards the observed failure where a hallucinated slug caused a subagent to fabricate an entire feature.)

**Cycle-subagent execution model (recursive dispatch is NOT available — inline edits required).** The cycle subagent dispatched at Step 1d does **not** have the `Agent` tool: recursive sub-subagent dispatch is not supported from inside a dispatched subagent, even on workstation. (This was confirmed empirically — an `/execute-plan` cycle subagent that tried to dispatch Sonnet test/impl agents found the tool unavailable and could only halt.) This forces a load-bearing override of any dispatched skill's sub-subagent contract: skills that nominally fan out to sub-subagents (e.g. `/execute-plan` → Sonnet test-agent + impl-agent, `/retro` → research subagents A–G) MUST be performed INLINE inside the cycle subagent itself using `Edit`/`Write`/`Read` directly. **This override applies only at the cycle-subagent level** — the orchestrator still dispatches exactly one `Agent` per cycle, and the override never expands the orchestrator's `Write`/`Edit` scope (HARD CONSTRAINT 1 still holds; the orchestrator edits only sentinels). This is the same execution model as `/lazy-batch-cloud`; the two orchestrators are coupled per CLAUDE.md. (Unlike cloud, workstation retains the Tauri runtime, MCP HTTP server, audio device, and Windows tooling — only the recursive-dispatch limit and its inline-edit override are shared.)

> **Known limitation — TDD agent-separation is traded away.** Collapsing `/execute-plan`'s test-agent→impl-agent split into ONE inline cycle subagent means the *structural* test-first guarantee (a separate agent writes failing tests before a separate agent implements — the `R-EP-2`/`R-EP-3` separation) is GONE: it cannot be enforced from sub-subagent dispatch evidence when there is no dispatch. This is an intentional tradeoff given the no-recursive-dispatch reality, not a defect. Compensating controls: (1) per-batch **quality gates** (`R-EP-6`) still run and must pass 100%; (2) the **`/retro`** pass audits the landed work; (3) the **MCP-validation** pass (which writes `VALIDATED.md`) gates final completion. The inline cycle subagent SHOULD still write **tests-before-impl within each batch** — read the test expectations, write the failing tests, confirm they fail for the right reason, THEN implement — even though the ordering can't be structurally verified. `/lazy-batch-retro`'s cloud branch already grades `R-EP-2`/`R-EP-3` as `n/a (cloud-override)`; the same grading applies to inline workstation cycles.

`$ARGUMENTS` is tokenized on whitespace. Recognized tokens:

- **Positive integer** → `max_cycles`. If absent, default to `10`. If a non-numeric / `< 1` integer is supplied, refuse with:

  > `/lazy-batch` requires a positive integer max-cycles. Usage: `/lazy-batch <N> [--allow-research-skip]`. Default: 10.

  **Ambiguous max-cycles (Deliverable D — clarify, never silently coerce):** if the token is present but non-integer in a way that suggests a _quantity_ the user had in mind — e.g. `"infinity"`, `"lots"`, `"max"`, `"all"`, `"unlimited"` — do NOT silently translate it to a hard-coded default. Instead, ask ONE clarifying `AskUserQuestion` before proceeding:

  > You passed `'{token}'` for max-cycles — how many cycles should I run? (e.g. `10` / `30` / `100`)

- **`--allow-research-skip`** (optional flag) → sets `allow_research_skip = true`. Default `false`. When set, the orchestrator restores the legacy "batch the research backlog" behavior: `lazy-state.py` is called with `--skip-needs-research`, Step 4 drops a `NEEDS_RESEARCH.md` sentinel for each research-pending feature without halting, and the loop halts on `queue-blocked-on-research` once every remaining feature is research-pending. This flag is for sessions where you have manually verified the remaining queue is independent — i.e., starting work on a downstream feature is safe even though an upstream feature is awaiting research. **Use case is rare.** The DEFAULT (flag absent) is to halt strictly on the FIRST `needs-research` so an ordered queue with dependencies cannot leak work onto unsafe downstream features.

- **`--adhoc`** (optional flag) → sets `adhoc_task` to the remainder of `$ARGUMENTS` after the `--adhoc` token (everything following it, verbatim). If `--adhoc` is the last token with no trailing text, `adhoc_task` is empty and the task is inferred from the conversation (see Step 0.45). When `adhoc_task` is set (flag present), the orchestrator runs **Step 0.45 (Ad-hoc Enqueue)** before the main loop so the referenced work is enqueued at the top of the queue. Off by default (flag absent → no ad-hoc enqueue). Because `--adhoc` consumes the rest of the string, place `<N>` and `--allow-research-skip` BEFORE it.

- **`--park`** (optional flag) → sets `park_mode = true`. Default `false`. Enables "park-and-continue" mode. **This flag is opt-in and off by default. Without it, the orchestrator's behavior is byte-for-byte the existing one** — a `NEEDS_INPUT.md` halts the loop into the existing Step 1g resolution-and-wait. The `--park` flag may appear in any position relative to the cycle-count arg (e.g. `/lazy-batch --park 30` and `/lazy-batch 30 --park` are equivalent). The full park/flush/auto-accept semantics (what happens when park mode is active) are defined in Steps 1g, 1h, and 1i of this skill — this token purely enables the mode.

Unknown tokens are an error:

> `/lazy-batch`: unrecognized argument `{token}`. Usage: `/lazy-batch <N> [--allow-research-skip] [--adhoc "<task>"] [--park]`.

**Standing-directive echo-back protocol (Deliverable C):** mid-run operator messages that imply a change to the orchestrator's operating mode MUST be acknowledged with a single `AskUserQuestion` echo-back BEFORE the mode takes effect. A "standing directive" is any message that implies one of:

- **(a) Budget change** — the operator wants to extend or reduce `max_cycles` (e.g. "run 20 more cycles", "stop after this feature").
- **(b) Standing resolution mode** — the operator wants a recurring resolution policy applied automatically until some condition (e.g. "auto-resolve all blockers as add-phase-and-fix until feature X completes").
- **(c) Early stop** — the operator wants to terminate the current run sooner than `max_cycles` (e.g. "stop after this cycle", "pause after the next commit").

Echo-back format (one `AskUserQuestion`, phrased in active terms):

> `{Interpretation of the directive in active terms, e.g. "Extend to N cycles and auto-resolve blockers as add-phase-and-fix until X completes — confirm?"}` — Yes / No (adjust: ...)

Only enter the new mode after the operator confirms. If they say No or provide a correction, re-parse and echo again.

**Budget-and-queue guard:** the orchestrator MUST NOT end a run with both budget remaining (`forward_cycles < max_cycles`) AND active queue items remaining (features that are neither complete, deferred, nor blocked on research) without first asking the operator (one `AskUserQuestion`) whether to continue into a new run or stop now. This prevents silent early exits where the orchestrator halts mid-queue without the operator realising.

Initialize counters and per-session state:
- `forward_cycles = 0` — initialized once per `/lazy-batch` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py` returns a new `feature_id`). Counts pipeline-advancing work; ceiling is `max_cycles`.
- `meta_cycles = 0` — initialized once per `/lazy-batch` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset on feature transitions). Counts resolution/recovery/cleanup work; ceiling is `2 * max_cycles`.
- `max_cycles = <parsed>`
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `cycle_log = []` — each entry: `{forward_cycles + meta_cycles, feature, action, subagent_summary}` (the running total is the monotonic N-th action in this invocation).
- `research_pending = set()` — feature_ids whose `RESEARCH.md` is missing and a `NEEDS_RESEARCH.md` sentinel was dropped this session. Only used when `allow_research_skip == true`. In the default (strict-halt) path this set never accumulates because Step 4 halts on the first feature; it stays empty.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. In the default path this stays `false` for the entire session because Step 4 halts before the loop continues.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched. **`sub_skill_args` is part of the tuple deliberately:** a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3) returns the same `(feature_id, sub_skill, current_step)` on every part but a *different* `sub_skill_args` (the plan-part path), which is real forward progress, not a loop. Omitting `sub_skill_args` made the loop-guard false-trigger on every multi-part plan. Including it lets the guard fire only on a genuine no-progress repeat (identical part re-returned).
- `adhoc_task = <parsed>` — the ad-hoc task text from `--adhoc` (empty string if the flag was present with no text; unset/`None` if the flag was absent). See Step 0.45.
- `park_mode = <parsed>` — `true` if `--park` was present, `false` otherwise. When `false`, all halt behavior is byte-for-byte the existing one.

Print the start bookend:

```
## /lazy-batch — Starting
**Max cycles:** {max_cycles}
**Research mode:** {strict halt on first needs-research (default) | batched (--allow-research-skip)}
**Park mode:** {on (--park) | off (default)}
**Repo root:** {cwd}
```

---

## Step 0.4: Resume-time remote sync (HARD REQUIREMENT)

**Runs once, immediately after Step 0 (arg parsing) and BEFORE Step 0.5 / the Step 1a first state probe.** This is a single-turn git reconciliation, NOT polling — it does not violate HARD CONSTRAINT 7 (no active waiting). It does NOT touch the orchestrator's `Write`/`Edit` sentinel-only scope (HARD CONSTRAINT 1) — these are `Bash` git operations, not file edits.

**Rationale:** a `/lazy-batch` session can be interrupted (machine sleep, crash, terminal close) and resumed later, or the work branch's remote may have advanced from another machine (or a cloud `/lazy-batch-cloud` run on the same branch). If the orchestrator runs `lazy-state.py` against a local tree behind the remote tip, it infers state from stale local files (plans, sentinels, SPEC) and may re-do or corrupt already-pushed work. Reconcile local to the remote tip BEFORE any local-state inference. (This guardrail is mirrored from `/lazy-batch-cloud` Step 0.4, where the same failure mode is acute because of container reclaim.)

**Algorithm:**

1. Determine the work branch:

   ```bash
   branch=$(git rev-parse --abbrev-ref HEAD)
   ```

2. Fetch the remote tip (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error — bounded retry, not an active wait):

   ```bash
   git fetch origin "$branch"
   ```

   If the branch does not exist on `origin` yet (brand-new work branch never pushed), there is nothing to reconcile: skip the rest of Step 0.4 and continue to Step 0.5.

3. Fast-forward local to the remote tip:

   ```bash
   git merge --ff-only "origin/$branch"
   ```

4. **If the fast-forward FAILS because local has DIVERGED from `origin`** (non-fast-forwardable — local has commits origin lacks AND origin has commits local lacks), **do NOT clobber.** Do NOT `git reset --hard`, do NOT force anything. Surface the divergence to chat and halt for human resolution:

   ```
   🛑 /lazy-batch — work branch diverged from origin

   Local `{branch}` and origin/{branch} have both moved independently
   (non-fast-forwardable). This may indicate concurrent edits from another
   machine or a force-push. Refusing to auto-reconcile to avoid losing work.

   Resolve manually (inspect `git log --oneline --graph {branch} origin/{branch}`),
   then re-invoke /lazy-batch.
   ```

   PushNotification with the same one-line summary, then STOP. Do NOT run `lazy-state.py`.

5. On a clean fast-forward (or when local was already up to date / the branch was unpushed), print a one-line confirmation and continue to Step 0.5:

   ```
   🔄 Synced local {branch} to origin tip ({short-sha}) before resuming.
   ```

---

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

**Runs once, after Step 0.4 (remote sync) and BEFORE Step 0.5 / the first state probe.** Skipped entirely when the `--adhoc` flag was absent. It runs AFTER the remote ff-sync deliberately: enqueuing mutates `queue.json` in the working tree, so it must happen on the reconciled remote tip, not a stale local snapshot that the Step 0.4 fast-forward would then conflict with.

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

After the enqueue returns, continue to Step 0.5. The first cycle's state probe will return the ad-hoc feature first and route it to `/spec`; its end-of-cycle commit+push carries the bootstrap files (`queue.json`, `ROADMAP.md`, the spec dir + `ADHOC_BRIEF.md`) to origin.

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
   - Append to `cycle_log`: `{forward_cycles + meta_cycles + 1, "—", "/ingest-research (pre-loop)", "<subagent summary>"}`.
   - Increment `forward_cycles` to 1 (ingesting research is pipeline-advancing work).
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

Pass `--skip-needs-research` **only when `allow_research_skip == true` AND `skip_needs_research == true`**. The double-gate matters: in the default (strict-halt) path, `skip_needs_research` never flips to `true` because Step 4 halts the loop on the first `needs-research`, so the script is always called without the flag and returns `terminal_reason: needs-research` for the first research-pending feature in queue order. Only the `--allow-research-skip` path arms the legacy batching behavior.

**Probe enrichment (optional — folds repeat-count, git guards, and cycle header into one payload).** The orchestrator MAY call the probe with additional flags to fold `repeat_count`, `git_guards`, and `cycle_header` into the JSON in a single invocation:

```bash
python3 ~/.claude/scripts/lazy-state.py --repeat-count --probe \
  --forward-cycles {forward_cycles} --meta-cycles {meta_cycles} --max-cycles {max_cycles} \
  [--skip-needs-research]
```

`--repeat-count` enriches the output with a `repeat_count` field (how many consecutive cycles returned the same `(feature_id, sub_skill, sub_skill_args, current_step)` tuple) for mechanical loop detection. `--probe` (combined with the three counter flags) folds `git_guards` (clean-tree + origin-parity) and a pre-formatted `cycle_header` string into the response. These flags are purely additive — the base JSON fields are unchanged.

If the script exits non-zero, surface the error, push a PushNotification, print the final batch report (see Step 2), and STOP.

Parse the JSON output. Extract: `feature_id`, `feature_name`, `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`, `notify_message`, `diagnostics`.

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`**: see Step 1h (blocked-resolution mode). **Not a terminal halt anymore.** Step 1h re-prints the `BLOCKED.md` body verbatim, runs `AskUserQuestion` for the resolution path (add a phase / defer to queue tail / halt-for-manual / custom), records the choice, dispatches the Opus apply-resolution subagent to enact it (neutralizing `BLOCKED.md` via rename), and returns to Step 1a. The loop continues; do NOT print the final batch report — UNLESS the operator chooses "Halt for manual fix", which keeps `BLOCKED.md` untouched and STOPs (the legacy behavior, now one option among several).
- **`needs-input`**: see Step 1g (decision-resume mode). **Not a terminal state for the orchestrator anymore.** Step 1g re-prints the rich `## Decision Context`, runs `AskUserQuestion`, appends `## Resolution`, dispatches the Sonnet apply-resolution subagent (which edits SPEC.md / PHASES.md and neutralizes the sentinel), and returns to Step 1a. The loop continues; do NOT print the final batch report.
- **`needs-research`**: see Step 4 (research halt). Behavior depends on `allow_research_skip`:
  - **Default (`allow_research_skip == false`)**: Step 4 writes `NEEDS_RESEARCH.md`, prints the inline-prompt halt announcement, PushNotifications, prints the final batch report, and STOPs. The orchestrator does NOT advance past the research-pending feature — this is critical for ordered queues where downstream features depend on upstream work.
  - **Opt-in (`allow_research_skip == true`)**: legacy batching behavior — Step 4 writes `NEEDS_RESEARCH.md`, adds `feature_id` to `research_pending`, **DOES NOT increment either counter**, flips `skip_needs_research = true`, and returns to Step 1a so the next state-script call passes `--skip-needs-research` and either advances to a ready feature or returns `queue-blocked-on-research`.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode). **Only reachable when `allow_research_skip == true`** — in the default path Step 4 halts before this terminal can fire.
- **`needs-spec-input`**: see Step 1i (operator-directed halt-resolution) — the orchestrator re-prints what the dir contains and `AskUserQuestion`s the path (provide spec direction → seed the baseline / defer & continue queue / halt). It no longer bare-STOPs "cannot start from nothing".
- **`queue-missing`**: PushNotification with `notify_message`, print final batch report, STOP. (There is no queue to continue — the operator must create `queue.json` first; NOT routed to Step 1i per the halt-resolution component's exclusion list.)
- **`completion-unverified`**: a feature's SPEC/ROADMAP claims `Complete` but no `COMPLETED.md` receipt exists — it was flipped OUTSIDE the validation gate (a cycle subagent or hand edit bypassing `/retro` + `/mcp-test`). See Step 1i (operator-directed halt-resolution): re-print the gap and `AskUserQuestion` the path — reopen & re-validate (`**Status:** In-progress` → let the pipeline re-run retro + MCP) / grandfather the receipt (`lazy-state.py --backfill-receipts`, only if genuinely validated before the gate) / defer & continue / halt. Do NOT auto-flip, auto-reopen, or auto-backfill — that judgment is the operator's, now surfaced as a choice rather than a bare halt. (This is the terminal that makes failure mode 1 self-announcing instead of silent.)
- **`stale_upstream`**: an upstream feature/work-item this feature was materialized from changed since materialize. See Step 1i (operator-directed halt-resolution): re-print the gap and `AskUserQuestion` the path (re-materialize/absorb → re-run materialize or `/realign-spec` / reject the change / defer & continue / halt). `lazy-state.py` emits this (Step 2.9); do NOT auto-resolve.
- **`all-features-complete`**: PushNotification `"ALL FEATURES COMPLETE — roadmap finished after {forward_cycles} forward + {meta_cycles} meta /lazy-batch cycle(s)."`, print final batch report, STOP.
- **`cloud-queue-exhausted`**: Unreachable for `/lazy-batch` (workstation variant); treat as `all-features-complete` defensively.
- **`device-queue-exhausted`**: Reachable only on a **no-real-device** workstation (WSL2/CI, where the audio backend is the HeadlessPumpDriver). Every remaining feature carries `DEFERRED_REQUIRES_DEVICE.md` (real-device-only MCP assertions that cannot be certified here). PushNotification with `notify_message`, print final batch report, STOP. The honest resume is a real-device host: tell the user to set `ALGOBOOTH_REAL_AUDIO_DEVICE=1` (or run on native hardware) and re-run `/lazy-batch` — there the same features RE-OPEN (Step 9 dispatches `/mcp-test` scoped to the deferred scenario IDs as ordinary cycles) and complete. This is the device-axis mirror of `cloud-queue-exhausted`. Note: the **re-open dispatch itself needs no special handling** — on a real-device host the state script emits `sub_skill: mcp-test` for the deferred scenarios, which runs as a normal cycle.

### 1c. Check the max-cycles cap

If `forward_cycles >= max_cycles`:

```
PushNotification({ message: "lazy-batch hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP. Do NOT try to renew the cap automatically — the cap exists to bound runaway costs.

### 1c.6. PushNotification policy (park / halt / flush / run-end)

The orchestrator fires `PushNotification` at exactly four canonical event points so the operator receives a phone notification whenever the run changes state. `PushNotification` is always called by the **orchestrator** — state scripts never call it.

1. **park** (`--park` mode only) — fired once per newly-parked item when `park_mode == true` and the probe returns a non-empty `parked[]` array (the Step 1g queue-walk park path, new in Phase 4). Message carries the **running parked-count**: `"parked {feature_name} — {N} decision(s) parked so far this run"`. For each item in `parked[]`, fire the notification before continuing the queue walk.
2. **halt** (both modes) — fired on every terminal/halt: `NEEDS_INPUT` halt, `BLOCKED` halt-for-manual, `needs-research` strict halt, `queue-blocked-on-research`, `queue-missing`, `all-features-complete`, `max-cycles`, `meta-cap`, `device-queue-exhausted`, script-error, and any future obstacle terminal. Most of these already carry per-terminal `PushNotification` calls above — this point names the policy explicitly so no terminal can be added without a notification.
3. **flush** (`--park` mode only) — fired when parked decisions are collected and sent to the operator via the batched `AskUserQuestion` (the WU-4 flush protocol). The notification signals that the operator's input is being requested. Message: `"lazy-batch flush — {N} parked decision(s) ready for your input"`.
4. **run-end** (both modes) — fired when the run terminates and the final batch report is printed. This point largely coincides with the terminal halts above; stating it as a named point ensures every run termination path fires a notification, even if a new exit path is added that does not fit one of the named terminal reasons.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small sentinel-file write + commit, NOT a real skill that performs implementation work. Perform the action inline (orchestrator session) instead of dispatching a subagent. This is the spirit-preserving relaxation of HARD CONSTRAINT 1: sentinel files are documentation, and dispatching an Opus subagent to write a 10-line YAML block + run `git commit` wastes a full subagent's worth of context.

Follow `~/.claude/skills/lazy/SKILL.md` Step 3's protocol for each pseudo-skill exactly (the wrapper and orchestrator do the same thing here):

- **`__write_validated_from_skip__`** — run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __write_validated_from_skip__ <spec_path>` (the script is the single author of the VALIDATED.md write — it reads SKIP_MCP_TEST.md, writes VALIDATED.md, and is idempotent), then commit + push per policy.
- **`__write_validated_from_results__`** — run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __write_validated_from_results__ <spec_path>` (the script reads MCP_TEST_RESULTS.md, writes VALIDATED.md with the extracted scenarios, and is idempotent), then commit + push per policy.
- **`__mark_complete__`** — **gated by TWO inline docs-only gates, in order, BEFORE the flip runs.** **Gate 1 — MCP-coverage audit** per the shared `~/.claude/skills/_components/mcp-coverage-audit.md` component (read SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface; grep each `<spec_path>/mcp-tests/*.md` for each decision's id + keywords). If any decision is uncovered, the orchestrator (still inline, sentinel-write only — HARD CONSTRAINT 1 holds) writes `<spec_path>/NEEDS_INPUT.md` per the audit component's schema and commits it with `{feature_id}: mcp-coverage audit surfaced N uncovered locked decision(s) for user confirmation`. **Gate 2 — completion-integrity gate** per the shared `~/.claude/skills/_components/completion-integrity-gate.md` component (runs ONLY after gate 1 returns `clean`): verify phase-coherence (zero non-verification unchecked deliverables in PHASES.md) and that a validation sentinel (`VALIDATED.md`, or `SKIP_MCP_TEST.md`; workstation does NOT accept a bare `DEFERRED_NON_CLOUD.md`) plus `RETRO_DONE.md` exist. If a precondition fails, the orchestrator writes `<spec_path>/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`) describing the gap and commits it. On EITHER gate halting: append `{forward_cycles + meta_cycles + 1, feature_name, "__mark_complete__ (gate halted)", "<reason> → NEEDS_INPUT.md"}` to `cycle_log`, increment `forward_cycles` (gate-halted mark-complete is still a forward-advancing attempt), return to Step 1a — the next state-script call returns `terminal_reason: needs-input`, Step 1g surfaces it, and the apply-resolution Sonnet subagent reconciles before the next mark-complete attempt. Only when BOTH gates pass does the orchestrator proceed: run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __mark_complete__ <spec_path>` — the script is the single author of COMPLETED.md (kind: completed, provenance: gated, folding the validation evidence from VALIDATED.md/MCP_TEST_RESULTS.md into the receipt body — the durable proof `lazy-state.py` Step 2 keys on), the SPEC.md/PHASES.md `**Status:** Complete` flip, and the deletion of the consumed VALIDATED.md/RETRO_DONE.md/DEFERRED_NON_CLOUD.md sentinels (COMPLETED.md/SKIP_MCP_TEST.md/MCP_TEST_RESULTS.md are kept). After the script returns, update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token) — this is the one remaining orchestrator step. Then commit + push per project policy. See the component files for the full gate algorithms. **Both gates are docs-only** (read SPEC.md / PHASES.md / `mcp-tests/*.md` / sentinels, no Tauri / no MCP server) — they run identically in workstation and cloud.
- **`__flip_plan_complete_cloud_saturated__`** — emitted only by `lazy-state.py --cloud` at Step 7a when an `In-progress` plan's only unchecked WUs (scoped to the plan's `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. `sub_skill_args` is the absolute plan-file path. Run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __flip_plan_complete_cloud_saturated__ <spec_path> --plan <plan_file_path>` (the script edits only the `status:` line in the plan frontmatter → `Complete`, is idempotent, and does NOT touch SPEC.md, ROADMAP.md, or any sentinel). Derive the plan part number from the plan's `phases:` field for the commit message (e.g. `phases: [6]` → part 6; fall back to the plan filename's leading `part-N` / `phase-N` token). Commit per project policy with message `chore(<feature_id>): mark plan part N Complete (cloud-saturated)`, then push. This is a **forward cycle** — increment `forward_cycles`.
- **`__flip_plan_complete_stale__`** — emitted by `lazy-state.py` at Step 7a (in both cloud and workstation mode) when EVERY work-unit a Ready/In-progress plan references is already `[x]` — the plan is stale/already-applied but the frontmatter `status:` was never flipped. `sub_skill_args` is the absolute plan-file path. **Action (stays inline — `--apply-pseudo` does NOT implement stale):** read the plan's YAML frontmatter, edit ONLY the `status:` line in place (`Ready` or `In-progress` → `Complete`) — leave every other field and the markdown body untouched. Derive the plan part number from the plan's `phases:` field; fall back to the plan filename's leading `part-N` / `phase-N` token if `phases:` is missing. Stage the plan file and commit per project policy with message `chore(<feature_id>): mark plan part N Complete (stale — already applied)`. Do NOT touch SPEC.md, ROADMAP.md, or any other sentinel. **Distinction from `__flip_plan_complete_cloud_saturated__`:** stale fires in BOTH cloud and workstation (it is not cloud-only) and means every WU was already `[x]` — not deferred to workstation, genuinely done. Without this flip the `Step 7a: execute plan` probe would return an In-progress plan with all WUs done, the orchestrator would dispatch `/execute-plan` against it, the subagent would find no work, make no commit, and the next cycle would return the same state — a no-op loop. This is a **meta cycle** — increment `meta_cycles` (flipping a stale plan is cleanup, not forward implementation work).

After the inline action:

1. Append to `cycle_log`: `{forward_cycles + meta_cycles, feature_name, sub_skill, "inline: <one-line summary>"}` (use the UPDATED total after the increment in step 5 below, i.e. the N-th total action completed this invocation).
2. **Push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** The inline pseudo-skill committed a sentinel / plan-frontmatter change locally; push it now — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This backstops inline cycles the orchestrator owns directly — a `git push` of an already-committed change, NOT a Write/Edit, so HARD CONSTRAINT 1 still holds. "Up to date" is a fine result (a prior cycle's push already carried it).
3. Emit the canonical per-cycle update block (Step 3): heading `### Cycle fwd {forward_cycles}/{max_cycles} · meta {meta_cycles}/{2*max_cycles} · {feature_name} · {sub_skill}`, `**Result:**` = the inline outcome, `**Commit:**` = the sentinel/plan commit sha. Nothing else.
4. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` (same uniform post-cycle update as Step 1e — keeps loop-guard accurate across mixed pseudo-skill / real-skill cycles).
5. Increment the appropriate counter: `forward_cycles` for pipeline-advancing pseudo-skills (`__mark_complete__`, `__mark_fixed__`, `__write_deferred_non_cloud__`, `__write_validated_from_results__`, `__write_validated_from_skip__`, `__flip_plan_complete_cloud_saturated__`); `meta_cycles` for cleanup pseudo-skills (`__flip_plan_complete_stale__`). Return to Step 1a — DO NOT fall through to Step 1d.

This saves one Opus dispatch per pseudo-skill action. On a typical feature lifecycle (workstation: 1 × `__write_validated_*` + 1 × `__mark_complete__` = 2 dispatches reclaimed; cloud: 1 × `__write_deferred_non_cloud__` minimum) the savings compound across a multi-feature queue pass.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else.

#### 1d.0. Pre-boot the dev runtime for `/mcp-test` cycles (WORKSTATION ONLY — runs BEFORE prompt composition)

**Applies ONLY when `sub_skill == "mcp-test"`.** Skip this sub-step entirely for every other `sub_skill`. (This sub-step does not exist in `/lazy-batch-cloud` — cloud's Step 9 returns `__write_deferred_non_cloud__`, never `mcp-test`, so the cloud orchestrator never reaches it.)

**Why this exists (the failure it fixes).** The cycle subagent has NO `Agent` tool (HARD CONSTRAINT block above) and runs `/mcp-test` INLINE. The mcp-test SKILL.md Step 2 boots `npm run tauri:dev` as a **background** task, then Step 4 waits for readiness. Empirically, an inline cycle subagent that started a background build and then ENDED ITS TURN waiting on it produced a premature, resultless return: the background build process did NOT survive the subagent's turn boundary, and the orchestrator (SendMessage unavailable in this workstation environment) could not resume the dead subagent. Net: a validation cycle that wrote no result and no sentinel, burning the whole cycle. The structural fix is for the **orchestrator's own session** — which is long-lived and persists across subagent turns — to OWN the dev-runtime background process, so the runtime is already up and MCP-ready when the mcp-test subagent connects to it.

**Procedure (orchestrator session, all `Bash` — NOT file edits):**

1. **Probe whether the dev runtime + MCP HTTP server are already up.** Per the AlgoBooth canonical reference (`docs/development/CLAUDE.md`, referenced from the root CLAUDE.md), the MCP HTTP server listens on **TCP 3333** and `GET http://localhost:3333/health` returns 200 when ready:

   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3333/health
   ```

   If this prints `200`, the runtime is already up — skip to step 4 (amend the prompt only).

2. **If not up, start it (orchestrator-owned background process).** Use the canonical full-restart command (handles all three process types — Vite :1420, MCP :3333, sidecar named-pipe — per `docs/development/CLAUDE.md`):

   ```bash
   npm run dev:restart
   ```

   Start this with `Bash` `run_in_background: true`. The process is now owned by the **orchestrator** session, so it survives the upcoming subagent's turn boundary.

3. **BLOCK on an MCP-readiness probe (foreground `until`-loop — NOT a forbidden active wait).** This is a single bounded readiness gate the orchestrator runs synchronously before dispatch, not a poll for filesystem/research events — HARD CONSTRAINT 7 (never actively wait for *filesystem/research* events) is about waiting on the user's research upload, which is a different thing. A bounded readiness gate on a process the orchestrator just started is the same shape as the Step 0.4 single-turn git reconciliation: permitted, mechanical, bounded.

   ```bash
   for i in $(seq 1 90); do
     code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3333/health 2>/dev/null)
     if [ "$code" = "200" ]; then echo "MCP-READY"; break; fi
     sleep 5
   done
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3333/health
   ```

   (`tauri dev` takes ~3–5 min to compile + boot; 90 × 5s ≈ 7.5 min ceiling.) Health-200 is the readiness signal AlgoBooth's reference defines. Do NOT cache or reuse any `logs/session-{ts}/` path here — re-resolve the session dir from the live server if you ever need it (HARD REQUIREMENT in `docs/development/CLAUDE.md`); the readiness gate above is keyed on the stable health endpoint, not on any session-log path. If health never reaches 200 within the ceiling, surface a `BLOCKED.md` (blocker_kind: mcp-runtime-unready) rather than dispatching a subagent against a dead runtime — a subagent cannot recover a runtime the orchestrator failed to boot.

4. **Amend the mcp-test subagent prompt** (the dispatch in Step 1e) to state that the runtime is already orchestrator-managed — see the `/mcp-test` per-skill inline override below for the exact prompt language.

**HARD CONSTRAINT 1 is NOT relaxed by this.** Step 1d.0 is `Bash` only — a `run_in_background` process plus a `curl`/`sleep` readiness loop. It performs ZERO `Write`/`Edit` on any file (the orchestrator's sentinel-only edit scope is untouched). Owning a background process and polling a health endpoint are not file edits, exactly as Step 0.4's git reconciliation (also `Bash`-only) does not expand the edit scope.

**Loop-guard check (BEFORE composing the prompt):** Compute the current cycle's signature as the tuple `(feature_id, sub_skill, sub_skill_args, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)`, the state script has returned the same tuple two cycles in a row — almost always a sign that a terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`) is missing or that a plan/sentinel write the previous cycle was supposed to perform did not actually land. **`sub_skill_args` MUST be part of the compared tuple** — otherwise a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3, same `feature_id`/`sub_skill`/`current_step` but a different plan-part path in `sub_skill_args`) false-triggers the guard on every part despite genuine forward progress. The orchestrator MUST append the **LOOP DETECTED** block below to the subagent prompt so the subagent diagnoses the missing sentinel rather than producing yet another plan / running the same skill against unchanged state.

**Read `~/.claude/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` now** and use its verbatim fenced block as the cycle dispatch prompt, binding {feature_name}, {feature_id}, {cwd}, {current_step}, {sub_skill}, {sub_skill_args} before dispatch. The component file also notes how to append the LOOP DETECTED block (see below).

**LOOP DETECTED block (append only when the loop-guard fires):**

**Read `~/.claude/skills/_components/lazy-batch-prompts/loop-block.md` now** and append its verbatim fenced block AFTER the final paragraph of the cycle dispatch prompt, binding {feature_id}, {sub_skill}, {sub_skill_args}, {current_step}, {spec_path}. Append when and ONLY when the loop-guard condition holds (prev_cycle_signature == current signature). Do NOT include it on the first cycle (when `prev_cycle_signature is None`) or when the signature differs from the previous cycle.

Dispatch:

```
Agent({
  description: "lazy-batch cycle {forward_cycles + meta_cycles + 1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: <"sonnet" if LOOP DETECTED else "opus">,
  prompt: <the prompt above>
})
```

**Model selection.** Normal cycles dispatch on Opus because real-skill cycles can involve novel implementation decisions. The loop-resolution cycle (LOOP DETECTED branch) is mechanical — the prompt already contains the diagnosis (which sentinels to inspect, what conditions warrant which write) and the work is "read the canonical sentinel schema, identify which sentinel preconditions are met, write it, commit". Sonnet is sufficient at roughly 5× the cost-efficiency. Use `model: "sonnet"` when the LOOP DETECTED block was appended, `model: "opus"` otherwise.

### 1d.5. Post-cycle input audit (Opus — runs only on `/spec` and `plan-feature` cycles)

**Why this step exists.** The dispatched cycle subagent that ran `/spec` (or `plan-feature`, which composes `/spec-phases` + `/write-plan`) self-classifies its own decisions as product-behavior vs mechanical-internal and self-decides whether to halt via `NEEDS_INPUT.md`. In practice that self-classification gets short-shrift — the subagent juggles competing pressures (integrate research, draft updates, finalize SPEC, produce summary) and the classification step is biased toward "make progress". Across ~75 observed lazy-batch cycles, zero `NEEDS_INPUT.md` sentinels fired from `/spec`'s self-audit despite multiple cycles having surfaceable product-behavior calls. This step is the independent Opus second-opinion focused on one question: did any product-behavior decision get baked into SPEC.md / PHASES.md without surfacing to the user?

**Ordering (Deliverable A — close the routing-order gap):** Step 1d.5 runs IMMEDIATELY after the cycle subagent returns (i.e., after Step 1d dispatch completes), BEFORE the orchestrator performs the next state probe at Step 1a. This means the audit executes after EVERY `/spec` or `plan-feature` cycle — regardless of what the NEXT state probe will return. In particular, if the next probe routes to `needs-input` (Step 1g) or `blocked` (Step 1h), that routing does NOT retroactively exempt the just-completed cycle's audit. The audit fires first; Step 1g / 1h fires afterward (on the same cycle or the subsequent one). This closes the observed gap where product-behavior decisions baked into a `/spec` cycle escaped audit because the orchestrator jumped directly to needs-input/blocked resolution.

**Skip when ANY of:**
- `sub_skill` is NOT in {`/spec`, `plan-feature`}. (Most cycles — `/execute-plan`, `/retro`, `/mcp-test`, pseudo-skills — skip the audit; they don't author SPEC content.)
- The cycle was a pseudo-skill (Step 1c.5 already ran inline; no `/spec`-shaped decisions to audit).
- The cycle subagent already wrote `NEEDS_INPUT.md` for this feature this cycle (the cycle correctly surfaced; re-auditing would double-fire). Probe: `test -f {spec_path}/NEEDS_INPUT.md` AND `git diff HEAD~1 --name-only` lists it. **This double-fire guard is preserved** — a subsequent `needs-input` routing in Step 1g does NOT exempt the audit (different concern), but the cycle subagent itself having already written the sentinel for THIS cycle does.
- The cycle subagent returned a hard failure with no SPEC/PHASES delta (nothing to audit).

**Inputs to gather before dispatch:**
1. `spec_path` from this cycle's state-script result.
2. `feature_id`, `feature_name`, `sub_skill` from the same result.
3. The cycle subagent's one-paragraph summary, including its **Decision-Classification Ledger** section (mandatory under `/spec --batch` — see `~/.claude/skills/spec/SKILL.md`). If the ledger is missing or malformed, capture that fact for the audit prompt; do not synthesize one.
4. The SPEC/PHASES delta: `git diff HEAD~1 -- {spec_path}/SPEC.md {spec_path}/PHASES.md` (or against the cycle's commit sha if known).

**Dispatch:**

```
Agent({
  description: "lazy-batch input-audit (cycle {forward_cycles + meta_cycles}): {feature_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <audit prompt below>
})
```

**Audit prompt:**

**Read `~/.claude/skills/_components/lazy-batch-prompts/input-audit-prompt.md` now** and use its verbatim fenced block as the audit dispatch prompt, binding {feature_name}, {feature_id}, {spec_path}, {sub_skill}, {cycle_commit_sha or "HEAD~1"}, and {cycle_summary} before dispatch.

**After the audit subagent returns:**
1. If it wrote `NEEDS_INPUT.md`, append a `**Audit:**` bullet to the per-cycle output block (Step 3): `**Audit:** {N} product-behavior decision(s) surfaced` (one line, no further prose).
2. If it returned "clean — no product-behavior decisions baked in", append no audit bullet — the audit is silent on clean cycles to keep cycle output lean.
3. If it flagged a missing/malformed Decision-Classification Ledger, append a `**Note:**` bullet: `**Note:** /spec --batch cycle returned no Decision-Classification Ledger (contract violation)`. This surfaces the contract issue without halting.
4. Audit costs are NOT separate cycles — the audit shares the cycle's slot in `cycle_log` and does not increment the cycle counter. The audit subagent is bounded (read SPEC/RESEARCH/diff, classify, optionally write one sentinel), so its context footprint is small.
5. Proceed to Step 1e. The next state-script call at Step 1a will surface `needs-input` if the audit wrote `NEEDS_INPUT.md`, and Step 1g handles resolution inline (no loop halt).

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{forward_cycles + meta_cycles + 1, feature_name, sub_skill, subagent's one-paragraph summary}` (use the total BEFORE the increment below, so the entry matches the in-flight cycle number).
2. Emit the canonical per-cycle update block (Step 3): heading `### Cycle fwd {forward_cycles+1}/{max_cycles} · meta {meta_cycles}/{2*max_cycles} · {feature_name} · {sub_skill}`, `**Result:**` = the first line of the subagent summary, `**Commit:**` = the cycle's commit sha (or `—`). For an `/execute-plan` cycle, add the `**Inline:**` bullet confirming the subagent performed the edits inline (zero Agent() calls) with test-first discipline per batch — the inline-override audit signal. No other prose.
3. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` so the next cycle's Step 1d loop-guard can compare against this cycle.
4. **Post-cycle push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** Verify the work branch is pushed — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). The cycle subagent's Step 1d already commits and pushes to the current branch at end-of-cycle, so this normally reports "up to date" — it is the backstop for any cycle that did not push itself. A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 still holds.
4a. **Post-`/execute-plan` (and `/mcp-test`) ledger-consistency guard (guardrail D — codifies the previously-ad-hoc operator check).** When the cycle that just returned was `/execute-plan` or `/mcp-test`, run a SINGLE-TURN consistency check BEFORE the next state probe (Step 1a). This is one scripted check fired on the cycle's completion notification — NOT polling, so HARD CONSTRAINT 7 (no active waiting) holds; these are `Bash` reads, so HARD CONSTRAINT 1 holds too. The cycle subagent is supposed to leave a clean, consistent ledger via the atomic gate+commit (Step 1d `/execute-plan` override), but it empirically loses its turn between gates and commit — this guard catches the residue deterministically instead of relying on operator memory.

   First fetch so `@{u}` is current (the `--verify-ledger` `head_matches_origin` check compares HEAD to `@{u}` and does NOT fetch itself):
   ```bash
   git fetch origin $(git rev-parse --abbrev-ref HEAD)
   ```
   Then run:
   ```bash
   python3 ~/.claude/scripts/lazy-state.py --repo-root <repo_root> --verify-ledger {spec_path}
   ```
   Read the JSON `ok`/`failing_check`/`checks` fields. (`--cloud` is NOT needed for `--verify-ledger`; the plan-Complete check is the same in both modes.)

   If `ok` is true → continue to step 5. If `ok` is false → reconcile per the named `failing_check`:
   - `clean_tree` or `head_matches_origin` failing → auto-dispatch a recovery cycle subagent (NOT a numbered cycle, does NOT increment `forward_cycles`) whose sole job is to stage + commit + push any uncommitted/unpushed residue, then re-run `--verify-ledger` until ok.
   - `plan_complete` failing (`/execute-plan` only) → the recovery subagent re-flips the plan-part frontmatter `status:` to `Complete`, then re-runs the guard.
   - `deliverables_done` failing → the recovery subagent may tick a verification box ONLY when there is on-disk evidence that verification actually ran for that row (e.g. `VALIDATED.md` or `MCP_TEST_RESULTS.md` present in `{spec_path}/` and covering that row). If verification boxes are unticked AND no such evidence exists on disk, the recovery subagent MUST NOT tick them; instead it writes `{spec_path}/NEEDS_INPUT.md` describing the gap (which boxes are unticked, which evidence is missing) and surfaces it — do not silently tick unverified boxes. Note: `--verify-ledger`'s `deliverables_done` check already exempts verification-only rows (rows under "Runtime Verification / MCP Integration Test" subsections), so it will not false-fail on legitimately-pending Runtime-Verification boxes.

   Recovery dispatch prompt MUST name the specific `failing_check` and `{spec_path}`. Append a `**Recovery:**` bullet to the per-cycle output block noting which check failed. Do NOT advance to Step 1a until the guard passes.
5. Increment `forward_cycles`. Return to Step 1a. **Both counters are monotonic across feature transitions (HARD CONSTRAINT 8).** If the next state-script call returns a different `feature_id` — e.g. because this cycle's `__mark_complete__` finished the prior feature, or the queue rolled forward to the next ready feature for any other reason — the counters continue from where they were. Do NOT reset either counter on the boundary.

**Note:** Step 1c.5 (pseudo-skill inline handling) MUST also update `prev_cycle_signature` to the cycle's `(feature_id, sub_skill, sub_skill_args, current_step)` tuple before returning to Step 1a. Otherwise a real-skill cycle following a pseudo-skill cycle would compare against a stale signature and miss loops that span both kinds. The orchestrator should treat the prev-signature update as a uniform post-cycle action regardless of whether the cycle dispatched a subagent or ran inline. The same applies to the counter increments: they are uniform post-cycle actions that happen once per cycle (real, pseudo, or decision-resume) and never reset.

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

**Reachable only when `allow_research_skip == true`.** Triggered when `lazy-state.py --skip-needs-research` reports `queue-blocked-on-research` AND `research_pending` is non-empty (the orchestrator has already dropped at least one `NEEDS_RESEARCH.md` this session). The user's Gemini deep-research step is the blocker. In the default (strict-halt) path this state is unreachable because Step 4 halts on the first `needs-research` before the loop ever reaches `queue-blocked-on-research`.

**This is a passive halt, NOT an active wait.** The orchestrator MUST NOT use `Monitor`, `sleep`, polling loops, or any other mechanism to block on filesystem events (HARD CONSTRAINT 7). Research arrives on the user's timeline — they may be away from their device for hours or days. The orchestrator announces the halt, surfaces every supported upload path, fires a PushNotification, and stops. The user's next `/lazy-batch` invocation is the implicit resume signal; Step 0.5 (pre-loop ingest check) and `lazy-state.py`'s normal flow auto-detect uploads on re-entry — no special detection is needed at resume time.

**Algorithm:**

1. **Read every pending feature's RESEARCH_PROMPT.md.** For each `feature_id` in `research_pending`, locate the prompt file (the path is recorded in the just-written `NEEDS_RESEARCH.md` sentinel's `research_prompt_path` field, resolved relative to that feature's `spec_path`). Read its content; measure its character count.

2. **Announce the halt with inline prompts.** The mobile-friendliness goal: every prompt the user needs to paste into Gemini is in chat, in a fenced code block, ready for long-press-copy. No GitHub UI navigation required. **Read `~/.claude/skills/_components/lazy-batch-prompts/research-halt-announcement.md` now** and use **Variant B** (the `queue-blocked-on-research` multi-feature path). Print the opening block, then the per-feature block for EACH `feature_id` in `research_pending` (binding {feature_id}, {feature_name}, {spec_path}, {RESEARCH_PROMPT content}, {NNNN chars}, {within|over}), then the unified upload instructions (binding {max_cycles}). The `[length: ...]` line is a soft indicator. When over cap, append the addendum `(may need manual trimming before paste)` so the operator notices on mobile without scrolling back. Do NOT refuse to print — over-cap prompts are still printed in full; the warning is informational.

3. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {N} feature(s) awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

4. **Append to `cycle_log`:** `{forward_cycles + meta_cycles + 1, "—", "⏸ research-wait (halt)", "{N} feature(s) pending: {feature_ids}"}`. DO NOT increment either counter — the halt is not a real cycle.

5. **Print the final batch report (Step 2)** with `terminal_reason = "queue-blocked-on-research"` and STOP. The orchestrator's turn ends; the user's next invocation re-enters via Step 0 → Step 0.5 → Step 1.

**Resume contract.** When the user re-invokes `/lazy-batch`, the natural flow handles every supported upload path:

| Upload path | Detected by | Handled by |
|-------------|-------------|------------|
| ① Staged `.txt` in `docs/gemini-sprint/results/` | Step 0.5's `find` probe | Step 0.5 dispatches `/ingest-research` (1 cycle) |
| ② Direct `RESEARCH.md` in feature dir | `lazy-state.py` Step 5 | normal main-loop dispatch of `/spec` Phase 3 |
| ③ One-off path | User ran `/ingest-research <path>` separately before `/lazy-batch`; that invocation copied the file to the staging dir and processed it. By the time `/lazy-batch` starts, `RESEARCH.md` is already in the canonical location | normal main-loop dispatch (path ② applies) |

No special resume detection is needed in `/lazy-batch`'s main loop — every upload path lands in a state the existing logic already handles.

**Cycle accounting at resume.** The new `/lazy-batch` invocation gets a fresh `max_cycles` budget. The previous session's cycle count is gone (no persistence layer — see Notes). This is by design: each `/lazy-batch <N>` run is a bounded budget the user authorizes.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

**Meta-cap check (FIRST — before any other action in Step 1g):** `if meta_cycles >= 2 * max_cycles:` → halt with message `"lazy-batch meta-cycle cap (2× max_cycles = {2*max_cycles}) reached — too many resolution/recovery cycles. Restart from a fresh session."`, PushNotification with the same one-line summary, print final batch report, STOP. This is what guarantees a Defer→same-terminal re-prompt loop is bounded.

**Pipeline binding for the shared handler below** — `{SKILL}` = `/lazy-batch`, `{STATE_SCRIPT}` = `lazy-state.py`, `{ITEM}` = feature, `{PUSH_RULE}` = workstation (the apply subagent's standard end-of-work push suffices). The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`** (decision-resume is a meta cycle). The per-cycle update block heading uses the two-counter format (Step 3 template). Then read and apply the shared decision-resume handler exactly (single source across the feature / bug / cloud batch orchestrators):

`~/.claude/skills/_components/decision-resume.md`

**Park mode — processing `parked[]` output (Phase 4, `--park` only):** When `park_mode == true` and the probe returns a non-empty `parked[]` array, the orchestrator skips the `AskUserQuestion` resolution flow for each item in that array and instead parks it: for each newly-parked `feature_name`, increment `parked_count` and fire `PushNotification({ message: "parked {feature_name} — {parked_count} decision(s) parked so far this run" })` (per the §1c.6 park policy). Continue the queue walk without halting. The batched flush of all parked decisions occurs later via the WU-4 flush protocol (see §1g-flush below).

---

### 1g-flush. Parked-decision flush (`--park` only)

**Guard:** runs only when `park_mode == true`. When `park_mode == false` this step is entirely
skipped — behavior is byte-for-byte the existing one.

**Pipeline binding for the shared flush component below** — `{SKILL}` = `/lazy-batch`,
`{STATE_SCRIPT}` = `lazy-state.py`, `{ITEM}` = feature, `{PUSH_RULE}` = workstation (standard
end-of-work push; the apply subagent's standard push suffices). The meta-cycle accounting
translates to **increment `meta_cycles`** per applied decision, matching every other resolution
mode.

**Three flush triggers (fire at the FIRST of):**

- **(a) Operator message mid-run:** any mid-run operator message while `park_mode == true` and
  unresolved parked items exist triggers an immediate flush before processing the message further
  (after echo-back if the message implies a standing-directive change).
- **(b) No unparked work remains:** when `lazy-state.py` returns `all-features-complete` (or any
  queue-exhausted terminal) and unresolved parked items still exist, flush FIRST — do NOT treat
  all-complete as a real STOP while unresolved parked items remain.
- **(c) Run end:** flush before printing the final batch report whenever `parked_count > 0` with
  unresolved sentinels still present.

**Cache-boundary note:** Triggers **(b)** and **(c)** are also the natural Anthropic prompt-cache
rebuild boundaries — the orchestrator was already going to pause or stop, so the ≈5-minute TTL
lapses anyway. Batching parked decisions to flush at those points adds **no extra cache cost**.
Trigger **(a)** (operator message mid-run) is itself a natural interaction boundary — flush there
too rather than accumulating further. Consequence: **do not interleave unrelated long waits (or
unrelated blocking halts) between a park and its flush.** Parking is for advancing past a decision
so forward work continues; the flush should land at the next natural cache boundary ((b)/(c)) or
interaction point ((a)) — inserting idle time in between forces repeated cache rebuilds for no
benefit.

Then read and apply the shared parked-flush handler exactly (single source across all three batch
orchestrators):

`~/.claude/skills/_components/parked-flush.md`

---

### 1h. Blocked-resolution mode (`terminal_reason == "blocked"`)

**Meta-cap check (FIRST — before any other action in Step 1h):** `if meta_cycles >= 2 * max_cycles:` → halt with message `"lazy-batch meta-cycle cap (2× max_cycles = {2*max_cycles}) reached — too many resolution/recovery cycles. Restart from a fresh session."`, PushNotification with the same one-line summary, print final batch report, STOP.

**Pipeline binding for the shared handler below** — `{SKILL}` = `/lazy-batch`, `{STATE_SCRIPT}` = `lazy-state.py`, `{ITEM}` = feature, `{SPEC_ROOT}` = `docs/features`, `{ADD_PHASE}` = `/add-phase`, `{PUSH_RULE}` = workstation (standard push). The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`** (blocked-resolution is a meta cycle). Then read and apply the shared blocked-resolution handler exactly (single source across the feature / bug / cloud batch orchestrators):

`~/.claude/skills/_components/blocked-resolution.md`

---

### 1i. Operator-directed halt-resolution (other non-max-cycles problem-terminals)

**Meta-cap check (FIRST — before any other action in Step 1i):** `if meta_cycles >= 2 * max_cycles:` → halt with message `"lazy-batch meta-cycle cap (2× max_cycles = {2*max_cycles}) reached — too many resolution/recovery cycles. Restart from a fresh session."`, PushNotification with the same one-line summary, print final batch report, STOP.

For every remaining problem-terminal that previously bare-`STOP`ed — `completion-unverified`, `needs-spec-input`, `stale_upstream` (and any future obstacle terminal) — the orchestrator routes here instead of halting. Rather than dead-ending, it re-prints the obstacle context, `AskUserQuestion`s a resolution path (reopen & re-validate / provide direction / defer & continue / halt-for-manual / custom), enacts the choice via an Opus apply-resolution subagent, and continues the loop. Follow the shared component (read and apply it exactly):

`~/.claude/skills/_components/halt-resolution.md`

Per that component's exclusion list, these terminals are NOT routed here and keep their existing behavior: `max-cycles` (cost bound — hard stop), `all-features-complete` (genuine success), `cloud-queue-exhausted` / `device-queue-exhausted` (environment — re-run on the right host), and `queue-missing` (no queue to continue). The research-pending terminals (`needs-research` / `queue-blocked-on-research`) keep their specialized Step 4 / Step 1f handling, which already lets the operator continue (in-session chat upload or re-invoke) rather than dead-ending; the component's "defer this research-pending feature & continue" option is available there as an enhancement when the queue has independent downstream work.

The Step 1i cycle records like any other (cycle_log entry, per-cycle block, `prev_cycle_signature = (feature_id, "__resolve_halt__", sub_skill_args, current_step)`, **increment `meta_cycles`**), and only the operator-chosen "Halt for manual fix" path stops the run.

---

## Step 1.5: Forward-Progress Verification (informally "Step 2.5"; runs after loop exit, before the Step 2 batch report)

After the cycle loop exits with any terminal reason **other than** `blocked`, `needs-input`, or `queue-missing`, run a final read-only state probe to confirm the loop actually advanced the queue. This is cheap insurance against the silent-no-op failure mode where a cycle subagent reports success but does not write the sentinel that would let the next invocation move on.

Skip this step entirely when `terminal_reason in {"blocked", "needs-input", "queue-missing"}` — those halts describe states the orchestrator already cannot resolve, and the user will be looking at the sentinel / config directly. (Note: a `blocked` loop-exit now occurs ONLY when the operator chose "Halt for manual fix" in Step 1h — every other Step 1h path resumes the loop, so it never reaches loop-exit as `blocked`.) For every other exit (including `all-features-complete`, `needs-research`, `queue-blocked-on-research`, `cloud-queue-exhausted`, and max-cycles), execute the probe.

**Algorithm:**

1. Run the state script ONE more time, identically to Step 1a:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]
   ```

   Pass `--skip-needs-research` under the same double-gate condition as Step 1a (`allow_research_skip == true AND skip_needs_research == true`). Parse the JSON.

2. Compute the probe tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the new output (any field may be `null` for terminal exits — that is fine, the comparison still works).

3. Compare against `prev_cycle_signature` (the signature of the last real-skill or pseudo-skill cycle run during THIS invocation). Three cases:

   **(a) Forward-progress confirmed.** Probe tuple differs from `prev_cycle_signature`, OR the probe returned a terminal reason. Print one line at the top of the Step 2 final batch report:

   ```
   ✅ Next /lazy-batch invocation will: <human-readable summary>
   ```

   Construct `<human-readable summary>` from the probe output:
     - Terminal reason set → `"halt on {terminal_reason} ({notify_message})"`.
     - Pseudo-skill (`__*__`) → `"perform {sub_skill} on {feature_name} ({current_step})"`.
     - Real skill → `"dispatch /{sub_skill} on {feature_name} ({current_step})"`.

   **(b) Forward-progress WARNING.** Probe tuple equals `prev_cycle_signature` (same `feature_id`, same `sub_skill`, same `sub_skill_args`, same `current_step`, no terminal reason). This means the next `/lazy-batch` invocation would re-issue the cycle this run just finished — the queue did not advance. Print this block at the top of the Step 2 final batch report:

   ```
   ⚠ FORWARD-PROGRESS WARNING: the next /lazy-batch invocation will return
   the same state as the cycle we just finished
   (feature_id={feature_id}, sub_skill={sub_skill},
   sub_skill_args={sub_skill_args}, current_step={current_step}).

   This run did not advance the queue. Likely causes:
     • A sentinel that should have been written wasn't (RETRO_DONE.md,
       VALIDATED.md, DEFERRED_NON_CLOUD.md, SKIP_MCP_TEST.md).
     • A plan-frontmatter status flip the last cycle was supposed to perform
       did not land (e.g. cloud-saturated In-progress → Complete).
     • lazy-state.py is stuck on a condition no skill is resolving.

   Inspect {spec_path}/ sentinels and plan frontmatter before re-invoking.
   ```

   PushNotification with `"lazy-batch forward-progress WARNING — queue did not advance; inspect {feature_name} sentinels."` so the user sees the issue even if they only read the notification.

   **(c) `prev_cycle_signature is None`.** No real cycles ran this invocation (e.g. Step 0.5 ingest was the only action, or the very first state-script call was already terminal). Skip the comparison and print only the case-(a) "Next invocation will" line based on the probe.

4. The probe is **read-only**: do NOT mutate `cycle`, do NOT append to `cycle_log`, do NOT touch sentinels. Its sole output is the WARNING / NEXT line at the top of the Step 2 report.

5. If the probe itself exits non-zero (the script crashed), print `⚠ FORWARD-PROGRESS PROBE FAILED: lazy-state.py exited non-zero — re-invoke /lazy-batch to retry.` at the top of the Step 2 report and continue. Do NOT halt — the loop already finished; the probe failure is information, not a fatal error.

This step is the orchestrator's cheap end-of-run sanity check: it costs one extra `lazy-state.py` invocation (microseconds) and surfaces silent loop-perpetuation bugs at the moment they happen, instead of on the user's next `/lazy-batch` invocation.

---

## Step 2: Final Batch Report

When the loop exits (terminal state or max-cycles), print:

```
## /lazy-batch — Done

**Forward cycles used:** {forward_cycles}/{max_cycles}
**Meta cycles used:** {meta_cycles}/{2*max_cycles}
**Terminal reason:** {terminal_reason or "forward-cycles-cap"}
**Last notification:** {notify_message or "—"}
**Park mode:** {on | off}

### Cycle log
| # | Feature | Action | Summary |
|---|---------|--------|---------|
| 1 | ... | /plan-feature | ... |
| 2 | ... | /execute-plan | ... |
| ... |

**Next step:**
  - If terminal_reason is "blocked": this is reached ONLY when the operator chose "Halt for manual fix" in Step 1h (every other Step 1h path resumes the loop). Resolve {spec_path}/BLOCKED.md by hand, then re-run `/lazy-batch {max_cycles}` — the next run re-enters Step 1h if BLOCKED.md is still present.
  - If terminal_reason is "needs-research" (DEFAULT path, strict halt): the fastest resume path is to upload Gemini research in your NEXT MESSAGE in this conversation — the in-session resume protocol (Step 5) will dispatch /ingest-research and re-invoke /lazy-batch automatically. Otherwise, stage/drop the research per Step 4's halt announcement and re-run `/lazy-batch {max_cycles}` manually.
  - If terminal_reason is "queue-blocked-on-research" (only reachable under --allow-research-skip): same as needs-research — upload research in chat for fastest resume, or use one of the staged/drop paths and re-run `/lazy-batch {max_cycles} [--allow-research-skip]`.
  - (needs-input is no longer a terminal state — Step 1g resolves and resumes within the same /lazy-batch invocation.)
  - If forward-cycles-cap: re-run `/lazy-batch {max_cycles}` from a fresh session
  - If meta-cycles-cap (2× max_cycles): too many resolution/recovery cycles — investigate the cause before re-running.
```

*(Print the following table ONLY when `park_mode == true` AND `auto_accepted[]` is non-empty. Omit entirely otherwise — no change to default reports.)*

```
### Auto-accepted decisions (`--park` two-key)

| Feature | Decision | Chosen option | Resolved sentinel |
|---------|----------|---------------|-------------------|
| {feature_name} ({feature_id}) | {decision title} | {chosen option label} | `{resolved_sentinel_path}` |
| ... | ... | ... | ... |
```

*(One row per auto-accepted decision across all features. If a single sentinel carried multiple decisions, emit one row per decision with the same feature column repeated. This table is the run-end audit trail for all D2 two-key auto-accepted choices.)*

STOP.

---

## Step 3: Cycle Output Discipline (lean · consistent · scannable)

Every cycle — real-skill (Step 1e), inline pseudo-skill (Step 1c.5), decision-resume (Step 1g), blocked-resolution (Step 1h), or halt-resolution (Step 1i) — emits **EXACTLY ONE update block** in this shape, and nothing else:

```
### Cycle fwd {forward_cycles}/{max_cycles} · meta {meta_cycles}/{2*max_cycles} · {feature_name} · {sub_skill}
- **Result:** {one-line outcome}
- **Commit:** {short-sha | "—"}
```

For a forward cycle (real-skill or pipeline-advancing pseudo-skill), `forward_cycles` is the post-increment value. For a meta cycle (decision-resume 1g, blocked-resolution 1h, halt-resolution 1i, or stale-plan flip), `meta_cycles` is the post-increment value. `{sub_skill}` is the real skill name, the `__pseudo_skill__` token, `needs-input` for a decision-resume cycle, or `blocked` / `halt-resolution` as appropriate. `**Result:**` is the first line of the subagent summary, the inline action's effect, or the resolved decision — ONE line. `**Commit:**` is the cycle's commit sha (or `—` when nothing was committed).

**Rules (so many cycles stay scannable on a phone):**

- **ONE block per cycle.** The heading + bullets ARE the cycle's entire chat footprint. Do not precede or follow it with prose.
- **No dispatch narration.** Do NOT write "dispatching the subagent", "running in the background", "waiting on the completion notification before advancing", or similar. The loop mechanics are a fixed contract, not per-cycle news.
- **No commit-strategy narration.** Do NOT explain commit ownership or in-flight races ("these uncommitted changes are the agent's in-flight work", "committing now would race the agent", "I'll let it own the commits"). Commits are owned by the cycle subagent (real skills) or by the inline action (pseudo-skills) — a fixed rule, never re-explained per cycle.
- **Ignore commit prompts silently.** If a Stop hook or any other prompt asks whether to commit between cycles, do NOT answer with prose. The commit policy is already fixed; proceed to the next state probe without narration.
- **At most 2–3 bullets, one line each.** Add a third bullet ONLY for a genuinely notable signal — e.g. `**Inline:** edits performed inline, test-first per batch` on an `/execute-plan` cycle (the inline-override audit signal), `**Audit:** {N} product-behavior decision(s) surfaced` on a `/spec` or `plan-feature` cycle whose Step 1d.5 input-audit fired, or `**Note:** {flag}` for an issue worth surfacing.
- **Halt/terminal announcements are exempt.** The Step 4 research halt, Step 1f research-wait, Step 1g malformed-sentinel halt, the Step 1h blocked-resolution prompt (rich blocker re-print + AskUserQuestion) and its "Halt for manual fix" stop, the Step 1i halt-resolution prompt (obstacle re-print + AskUserQuestion) and its Halt stop, and the Step 2 final report keep their own templated shapes — those are functional (copy-paste prompts, decision context, next-step guidance), not per-cycle narration.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

The state script returns `needs-research` when `RESEARCH.md` is missing but `RESEARCH_PROMPT.md` exists. This step has **two paths**, gated by the `allow_research_skip` flag parsed in Step 0.

The default path (strict halt) is the safer choice for ordered queues with cross-feature dependencies: the FIRST research-pending feature in queue order halts the loop, so downstream features that may depend on the in-flight one never start work prematurely. The opt-in path (`--allow-research-skip`) restores the legacy "batch all pending research, halt once" behavior — only safe when the operator has verified the remaining queue is independent.

### Stub specs vs structured-research-pending specs (disambiguation rule)

`needs-research` fires ONLY for structured-but-research-pending specs — the baseline is locked, only deep research hasn't landed. Stub specs (no baseline yet) go through a different path: Step 4.5 of `lazy-state.py` dispatches `/spec` interactively to shape the baseline via `AskUserQuestion` rounds, and the orchestrator runs that as a normal cycle.

Detection happens inside `lazy-state.py::is_stub_spec(spec_text, queue_entry)`. A SPEC is a stub iff ANY of:
- SPEC body contains `Draft (pre-Gemini)` (canonical marker per AlgoBooth `docs/CLAUDE.md`).
- `queue_entry.get("stub") is True` (queue.json cross-check per AlgoBooth `docs/CLAUDE.md`).
- SPEC body contains a legacy marker (`**Status:** Draft (research stub)` or `> Stub generated from advanced feature research`).

| State | Signal | State-machine route | What the orchestrator does | User action needed |
|-------|--------|---------------------|-----------------------------|--------------------|
| Stub spec | `> Draft (pre-Gemini)` OR `queue.json "stub": true` OR legacy marker | Step 4.5 | Dispatch `/spec` as a normal cycle subagent; the subagent calls `AskUserQuestion` during Phase 1 brainstorming | Answer design questions inside the cycle (conversation) |
| Structured + research-pending | No stub markers; `RESEARCH.md` / `RESEARCH_SUMMARY.md` missing; `RESEARCH_PROMPT.md` present | Step 5 → terminal `needs-research` | Halt per Step 4 below (or batch per `--allow-research-skip`); the orchestrator does NOT dispatch `/spec` interactively | Upload Gemini research (single-turn action) |

HARD CONSTRAINT 5 scopes the orchestrator's `AskUserQuestion` to Step 1g — that constraint does NOT bind subagents the orchestrator dispatches. A `/spec` cycle subagent at Step 4.5 is allowed and expected to call `AskUserQuestion` during Phase 1; that's the legitimate design-conversation channel.

The `--allow-research-skip` flag described below applies to the STRUCTURED-research-pending case only. Stub specs never reach this step (they're dispatched at Step 4.5 before Step 5 fires).

### Step 4 — shared sentinel write (both paths)

Both paths write the same `NEEDS_RESEARCH.md` sentinel:

1. Check whether `{spec_path}/NEEDS_RESEARCH.md` already exists (a prior cycle / session may have dropped it). If it exists, skip the write — sentinel writes are idempotent.
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

   Run Gemini deep research against the prompt at `{research_prompt_path}`,
   then provide the result via any of these upload paths:

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

After the sentinel write, branch on `allow_research_skip`.

### Step 4 — DEFAULT path (`allow_research_skip == false`): immediate halt

This is the new default. The orchestrator halts on the FIRST `needs-research` it encounters — no `--skip-needs-research`, no accumulation, no advancing past the feature.

1. **Read the prompt content.** Open `{spec_path}/RESEARCH_PROMPT.md` and measure its character count. (If the file is somehow missing — the state script should never emit `needs-research` without it — print a defensive warning and fall through to the announcement with `<RESEARCH_PROMPT.md not found at expected path>` as the body.)

2. **Print the halt announcement to chat.** **Read `~/.claude/skills/_components/lazy-batch-prompts/research-halt-announcement.md` now** and use **Variant A** (the single-feature `needs-research` halt path), binding {feature_name}, {feature_id}, {spec_path}, {RESEARCH_PROMPT content}, {NNNN chars}, {within|over}, {max_cycles}. `{within | over}` is chosen by comparing the measured char count to 24,000 (Gemini's practical web-UI character cap; see `~/.claude/skills/spec/SKILL.md` Phase 2 for source notes). When over, append `(may need manual trimming before paste)` to that line — informational only, do NOT refuse to print.

3. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {feature_name} awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

4. **Append to `cycle_log`:** `{forward_cycles + meta_cycles + 1, feature_name, "⏸ needs-research (strict halt)", "NEEDS_RESEARCH.md written; prompt printed inline ({NNNN} chars)"}`. DO NOT increment either counter — the halt is not a real cycle.

5. **Print the final batch report (Step 2)** with `terminal_reason = "needs-research"` and STOP. Do NOT call the state script again. Do NOT touch `skip_needs_research` — it stays `false`. Do NOT add the feature to `research_pending` — it stays empty. The user's next `/lazy-batch` invocation re-enters via Step 0 → Step 0.5 → Step 1 and either ingests the uploaded research or hits this same halt again.

### Step 4 — OPT-IN path (`allow_research_skip == true`): legacy batch

This restores the pre-default-flip behavior. The orchestrator drops a sentinel, records the feature, flips `skip_needs_research = true`, and returns to Step 1a so the loop advances past this feature. The actual wait happens in Step 1f when `queue-blocked-on-research` fires.

1. Add `feature_id` to `research_pending`. Set `skip_needs_research = true`.
2. Append to `cycle_log`: `{forward_cycles + meta_cycles + 1, feature_name, "needs-research (sentinel drop, --allow-research-skip)", "NEEDS_RESEARCH.md written; flagging for Step 1f research-wait"}`. **DO NOT increment either counter** — this is a no-op state transition, not a real cycle. Sentinel writes here don't count against `max_cycles` either; cost discipline is preserved because the actual work of generating the prompt and running Gemini happens elsewhere.
3. Return to Step 1a. The next `lazy-state.py --skip-needs-research` call will either advance to the next feature in the queue (if any are ready) or return `queue-blocked-on-research` — at which point Step 1f's research-wait fires.

**Special pre-step (both paths):** if the state script returns `sub_skill: "spec"` with args that include "skip to Phase 2", the orchestrator dispatches it normally (this generates the RESEARCH_PROMPT.md). On the next cycle, the state script returns `needs-research` and this Step 4 fires. That's the intended two-cycle handoff for a feature with no research at all.

**Multi-feature accumulation (opt-in path only):** under `--allow-research-skip`, Steps 1a → 4 → 1a (skip) → 4 (next feature) ... can fire repeatedly during the first pass through the queue, each time appending another `feature_id` to `research_pending` and dropping another `NEEDS_RESEARCH.md`. The pass terminates when the state script returns `queue-blocked-on-research` (every remaining feature is research-pending) OR when a ready feature is found (the loop dispatches it normally). Under the default path this cannot happen because Step 4 halts on the first `needs-research`.

---

## Step 5: In-Session Resume Protocol (research uploaded via chat)

**When this protocol fires.** `/lazy-batch` halted (Step 4 default-path or Step 1f) on a research-pending state and printed the "Done" report. The user's NEXT MESSAGE in the same conversation contains research content for one or more pending features. This protocol is the chat-driven counterpart to Step 0.5's filesystem-driven pre-loop ingest — the user's upload IS the resume signal, and `/lazy-batch` re-enters immediately without the user typing `/lazy-batch` again.

**Why this exists.**

- **Eliminates the "rerun the skill" step.** The screenshot-canonical pre-change flow was: halt → user uploads research → assistant says "I'll stage this for the next /lazy-batch run" → user manually types /lazy-batch. The new flow collapses that to: halt → user uploads research → assistant ingests + re-invokes inline.
- **Resolves the cloud-gitignore friction.** `docs/gemini-sprint/results/` is gitignored in AlgoBooth (and other consumers following the gemini-sprint pattern). A bare `.txt` stage in a cloud container does not survive container reclaim — only the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` produced by `/ingest-research` are durable. Dispatching `/ingest-research` IN-SESSION guarantees the durable files exist before the container goes away.
- **HARD CONSTRAINT 7 still holds.** Responding to a single chat message is NOT polling. The orchestrator did not actively wait — it halted cleanly, the user took whatever time they needed (minutes, hours, days), and only when the user's next message arrives does this protocol activate. There is no `Monitor`/`sleep`/loop in the halt path.

**Protocol — what to do on the user's next-message research upload.**

This protocol is read by Claude on the turn AFTER the halt, with the halted `/lazy-batch` skill no longer loaded. The protocol lives here (and is surfaced verbatim in each halt announcement) so that Claude has clear instructions for the resume turn.

1. **Identify the research content and target feature(s).** The user's message may carry research as:
   - A file attachment (Claude Code-uploaded file path under `/root/.claude/uploads/...` or similar).
   - Pasted text — typically inside a fenced code block, but free-form prose is also valid.
   - An absolute file path (e.g. `~/Downloads/<file>.txt`, a phone-synced folder path).
   - Multiple of the above mixed in one message (e.g., one file per feature).

   Correlate each piece of content to a pending feature via the most recently halted invocation's pending list (the `Pending: <feature_ids>` line from Step 1f, or the single `feature_id` from Step 4). When the upload is unambiguously for one feature (only one was pending, or the user named the feature in the message), proceed directly. When multiple features were pending and the correlation is ambiguous, ask ONE `AskUserQuestion` clarifying "which feature does this research belong to?" before continuing — this is the only AskUserQuestion call permitted outside Step 1g, and only at the in-session resume boundary.

2. **Materialize the research into the staging dir.**
   - For file attachments / absolute paths: copy the file to `docs/gemini-sprint/results/<feature_id>.txt` (rename to match the feature_id for clean correlation by `/ingest-research`). Use `Bash` `cp` — do NOT move (the source file may be in a synced folder).
   - For pasted text: `Write` the pasted content to `docs/gemini-sprint/results/<feature_id>.txt` verbatim. Preserve any `## Project context` header or other framing the user provided.
   - For multi-feature uploads: repeat per feature.

3. **Dispatch `/ingest-research` IN-SESSION.** This is exactly the call Step 0.5 makes at the start of a fresh `/lazy-batch` invocation — running it now produces the same tracked outputs (`RESEARCH.md` + `RESEARCH_SUMMARY.md` per feature, `> Draft (pre-Gemini)` trailer cleared in SPEC.md, `queue.json "stub": true` cleared, consumed `.txt` moved to `_consumed/`, per-feature commits) before any container reclaim. Dispatch as a Sonnet subagent (matching `/ingest-research`'s model):

   ```
   Agent({
     description: "in-session resume: ingest uploaded research",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <prompt below>
   })
   ```

   Subagent prompt:

   ```
   The user has just uploaded Gemini deep-research result(s) mid-session,
   resuming a /lazy-batch run that halted on needs-research (or
   queue-blocked-on-research). The research file(s) have already been
   materialized into docs/gemini-sprint/results/ as <feature-id>.txt.

   Working directory: {cwd}
   Staged files (relative to repo root):
     - docs/gemini-sprint/results/{feature_id_1}.txt
     - docs/gemini-sprint/results/{feature_id_2}.txt  (if multiple)
     ...

   Action: Invoke /ingest-research with no arguments. It will scan the
   staging dir, correlate each .txt to a feature, write per-feature
   RESEARCH.md + RESEARCH_SUMMARY.md, drop the > Draft (pre-Gemini) SPEC
   trailer, clear queue.json "stub": true, move consumed .txt to
   _consumed/, and commit per feature.

   Cloud-durability note: docs/gemini-sprint/results/ is gitignored, so the
   staged .txt itself does NOT persist across container reclaim — but the
   RESEARCH.md + RESEARCH_SUMMARY.md files /ingest-research writes into
   docs/features/<.../>/{feature_id}/ ARE tracked and DO persist. That is
   the load-bearing durability guarantee of this resume path.

   After /ingest-research returns:
     1. Report its final summary block.
     2. Confirm which feature_ids now have RESEARCH.md on disk.
     3. Flag any ambiguous correlations (NEEDS_INPUT.md sentinels written) —
        the next /lazy-batch cycle will reach Step 1g (decision-resume mode)
        on them and AskUserQuestion the user.

   You may NOT spawn further subagents.
   ```

4. **Re-invoke `/lazy-batch` automatically.** After the subagent reports success, immediately invoke `/lazy-batch <N>` where `<N>` is the original `max_cycles` from the halted invocation (or the remaining budget if the user prefers — default to the original cap; surface the choice in the resume status line so the user can interject before the next halt). The re-invocation re-enters via Step 0 → Step 0.5 (which is now a no-op because the .txt has been moved to `_consumed/` by `/ingest-research`) → Step 1, and the previously research-pending feature is now ready for `/spec` Phase 3.

5. **Print a brief resume status line BEFORE the re-invocation, so the user sees the bridge:**

   ```
   ▶ In-session resume — ingested research for {comma-separated feature_ids}.
   Re-invoking /lazy-batch {max_cycles}...
   ```

   Then call `/lazy-batch`. No further user action required.

**What the in-session resume protocol does NOT do.**

- It does NOT skip `/ingest-research` (path ② — direct RESEARCH.md drop). Even if the user pastes content that looks like a finished `RESEARCH.md`, the standardized ingestion produces the matching `RESEARCH_SUMMARY.md`, drops the SPEC trailer, and clears the stub flag — those are mechanical chores worth doing every time.
- It does NOT auto-resume on a `needs-input` halt. `needs-input` is no longer a halt (Step 1g resumes inline); the in-session resume protocol is specifically for the research-pending halt classes (`needs-research` and `queue-blocked-on-research`).
- It does NOT preserve cycle accounting across the halt. The new `/lazy-batch <N>` invocation gets a fresh budget — each `/lazy-batch <N>` is an independent bounded run, consistent with the cycle-accounting note in Step 1f.

---

## Notes

- This skill never invokes the work-log MCP tool. Each sub-skill invoked by the cycle subagents logs its own work.
- The orchestrator is single-session by design — there is no persistence layer. State lives in the filesystem sentinels; restart is free.
- Commit policy is delegated to the cycle subagent (which follows the project's `.claude/skill-config/commit-policy.md` or standard pattern). The orchestrator does not commit anything itself except the NEEDS_RESEARCH.md sentinel, which is committed by the next sub-skill cycle's subagent (since the loop has already exited by the time it's written) — under the default strict-halt path, the user's next `/lazy-batch` run is what commits it (the first subagent dispatched against the now-research-ready feature picks up the unstaged sentinel and stages it alongside its own work, or the sentinel becomes stale and is overwritten when ingestion happens).
