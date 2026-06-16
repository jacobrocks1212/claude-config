---
name: lazy-batch
description: Autonomous orchestrator for the AlgoBooth (or any queue.json-driven) feature pipeline. Loops on lazy-state.py, spawns one Opus subagent per cycle, and drives the full tail (/spec → /plan-feature → /execute-plan → /mcp-test → __mark_complete__). A halt for any reason other than max-cycles presents an AskUserQuestion resolution path and resumes — only max-cycles, all-features-complete, environment-exhaustion, and missing-queue remain clean stops. Terminal action is __mark_complete__, gated by the MCP-coverage audit + completion-integrity gate. (The /retro step is unwired — 2026-06.)
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip] [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue] [--park]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch — Autonomous Pipeline Orchestrator

Drives the per-feature autonomous tail (`/plan-feature` (= `/spec-phases` + `/write-plan` in one cycle) → `/execute-plan` → `/mcp-test` → mark-complete) by looping on `~/.claude/scripts/lazy-state.py`. Each cycle spawns an Opus subagent that invokes the named sub-skill; the orchestrator (this skill, running in the main session) never touches source code, never invokes a skill directly, and never parses sentinel files manually.

**Step ordering note:** the `/retro` step has been UNWIRED (operator decision, 2026-06). Once all phases are complete the pipeline routes directly to `/mcp-test` (Step 9 MCP gate); `lazy-state.py` never emits `retro-feature`. `/mcp-test` only runs on workstation (cloud defers). Behavior inside the loop is otherwise unchanged — the orchestrator dispatches whatever `lazy-state.py` returns. (The `/retro-feature` skill remains in the catalog; git history is the restore path.)

This is the **workstation** orchestrator. The cloud variant is `/lazy-batch-cloud` (under `repos/algobooth/.claude/skills/lazy-batch-cloud/`); the two are coupled per CLAUDE.md.

---

## HARD CONSTRAINTS (non-negotiable)

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `COMPLETED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` / `PHASES.md` status lines when performing the `__mark_complete__` action (which is a documentation-level update by definition, not a source-code edit). `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns — or by the Step 1g D7 scope resolution (`resolved_by: completeness-policy`, no question); the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. **`BLOCKED.md` may likewise be appended to** (not overwritten) with a `## Resolution` section by Step 1h (blocked-resolution mode) after `AskUserQuestion` returns — or by the Step 1h D7 sequencing-only auto-resolution (no question); the orchestrator then dispatches an Opus subagent to enact the chosen resolution path (e.g. `/add-phase`, queue reorder) and neutralize the sentinel by **rename** (lazy-state.py keys the halt on the `BLOCKED.md` filename). All other `Write`/`Edit` operations — source code, test files, plan files, PHASES.md — require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference is exclusively via `lazy-state.py`. Sentinel files MAY be read by the orchestrator to confirm a write or to drive a pseudo-skill action.
4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to the resolution modes — decision-resume (Step 1g), blocked-resolution (Step 1h), and operator-directed halt-resolution (Step 1i) — ONLY for the orchestrator itself.** The guiding rule: a halt for ANY reason other than `max-cycles` (and the genuine all-done success / environment-exhaustion / no-queue stops listed in Step 1i) presents the operator an `AskUserQuestion` resolution path and continues the loop, rather than dead-ending — except that scope-class decisions and sequencing-only blockers are auto-resolved per `~/.claude/skills/_components/completeness-policy.md` (D7), not asked: the standing policy reduces questions, never adds them, and the resolution modes ask only for what remains product-class. Outside Step 1g / 1h / 1i, the orchestrator MUST NOT call `AskUserQuestion` — with four additional permitted uses: (i) the one-time echo-back confirmation when a mid-run operator message implies a budget change, standing resolution mode, or early stop (Step 0 standing-directive protocol); (ii) the budget-and-queue guard question when the run would otherwise end with budget and queue both remaining; (iii) the Step 0.45 `--enqueue-adhoc` task-details prompt when `--adhoc` is supplied with no text and the task cannot be unambiguously inferred from the conversation; and (iv) the Step 5 in-session resume multi-feature disambiguation question when research arrives for an ambiguous feature ("which feature does this research belong to?"). Uses (i) and (ii) are orchestrator-level confirmations of operator intent; uses (iii) and (iv) are bounded single-question disambiguation prompts at well-defined pre-loop and resume boundaries. None are resolution-mode decisions about feature/bug content. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. Inside Step 1h, the orchestrator MUST `AskUserQuestion` for the resolution path against a `BLOCKED.md` (re-printing its body first), record the choice, dispatch the apply-resolution subagent to enact it, and **continue the loop** — `blocked` no longer halts the orchestrator either (except the operator-chosen "Halt for manual fix" path). (The legacy halt-on-needs-input behavior is gone; the user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation.) **This constraint scopes the orchestrator, not subagents it dispatches.** A `/spec` subagent dispatched at state-machine Step 4.5 (stub-spec detected) is allowed and expected to call `AskUserQuestion` during Phase 1 brainstorming — that's the legitimate design-conversation channel for a SPEC whose baseline doesn't exist yet. The orchestrator dispatches `/spec` exactly the same way it dispatches `/execute-plan` (one Agent call per cycle); whatever the dispatched skill does internally is its own contract. See "Stub specs vs structured-research-pending specs" below for the disambiguation rule.
6. **The orchestrator MUST print a Zero-Context Operator Briefing AND re-print the load-bearing context to chat BEFORE calling `AskUserQuestion`.** The operator may have been away for hours and retains NO session context (and may be reading on mobile, where `AskUserQuestion` truncates). In **Step 1g** the briefing (step 2a of the decision-resume component) catches them up from zero — what's being worked, why we halted, every option with pros/cons and fit against the original requirements, and a recommendation — followed by the verbatim `## Decision Context` re-print (step 2b); the `AskUserQuestion` option set MUST exactly match the options presented in the briefing (same labels, 1:1 — no option may appear in the UI that wasn't explained in chat first). Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` (one missing the `## Decision Context` H2 with H3 subsections matching `decisions:` 1:1) — surface the malformation as a quality issue and halt instead (see Step 1g.1). In **Step 1h** the load-bearing context is the `BLOCKED.md` body verbatim (no mandated rich-body schema — a thin body is NOT a malformation halt; re-print whatever is there and note in chat if it is sparse); in **Step 1i** it is the obstacle context the shared `halt-resolution.md` mandates. The same zero-context briefing discipline (catch the away operator up from zero before asking) applies to Step 1h/1i.
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **TWO session-global monotonic counters replace the single `cycle` counter.** Both are initialized once in Step 0 and NEITHER is ever reset on feature transitions.
   - **`forward_cycles`** — counts pipeline-advancing work. Ceiling: `max_cycles`. Incremented by: (a) real-skill dispatch cycles (Step 1e step 5) and (b) pipeline-advancing pseudo-skills at Step 1c.5 (`__mark_complete__`, `__mark_fixed__`, `__write_deferred_non_cloud__` (cloud variant only — workstation `lazy-state.py` never emits this), `__write_validated_from_results__`, `__write_validated_from_skip__`, `__grant_skip_no_mcp_surface__`, `__flip_plan_complete_cloud_saturated__`). **Capped at Step 1c** (`if forward_cycles >= max_cycles` → the existing max-cycles halt).
   - **`meta_cycles`** — counts resolution / recovery / audit / cleanup work. **NO ceiling — uncapped by design (operator decision 2026-06-14).** Incremented by: Step 1g (decision-resume), Step 1h (blocked-resolution), Step 1i (operator-directed halt-resolution), LOOP-DETECTED / Step 1e.4a recovery dispatches, the input-audit cycle at Step 1d.5, and the stale-plan flip pseudo-skill `__flip_plan_complete_stale__`. The meta loop is NOT bounded by a meta cap; the run's only hard stop is the `forward_cycles >= max_cycles` cap at Step 1c. `meta_cycles` is still tracked and displayed (as a bare count), but there is NO `if meta_cycles >= …` halt anywhere — Step 1g/1h/1i have no meta-cap check.
   - **Input-audit (Step 1d.5):** audits are NOT counted as separate cycles (they share the real-skill cycle's slot in `cycle_log` and do NOT increment either counter). This keeps audit costs outside the budget.
   - **Running total for cycle_log index:** use `forward_cycles + meta_cycles` as the monotonic `N` in cycle-log entries and per-cycle headings (i.e., the N-th action in this invocation regardless of type). `prev_cycle_signature` is a tuple of ids, unaffected.
   - Cycle N's per-cycle heading always refers to the N-th action in this invocation, regardless of which feature it operated on. A feature transition is NOT a fresh batch; the orchestrator runs ONE log across every feature it touches.

9. **Dispatch ONLY against the feature `lazy-state.py` returned THIS cycle; never fabricate a feature.** The orchestrator dispatches a cycle subagent against exactly the `feature_id` + `spec_path` from the current cycle's `lazy-state.py` output, verbatim. It MUST NOT invent, infer, or hand-edit a `feature_id`/slug that the state script did not emit. The state script (Step 2) already skips any queue entry whose `spec_dir` does not resolve on disk (emitting a `dangling queue entry` diagnostic) — so a real feature ALWAYS has an on-disk `spec_path` before dispatch. The cycle subagent prompt MUST forbid the subagent from CREATING a feature's `SPEC.md`/`RESEARCH.md`/`queue.json`/`ROADMAP.md` entries from a bare slug: the only sanctioned dir-creating paths are the `--enqueue-adhoc` bootstrap (Step 0.45) and a `/spec` dispatch against an already-seeded directory. If a cycle's `feature_id` does not correspond to an on-disk `spec_path`, that is a bug to surface (halt + report) — NEVER a cue to manufacture the feature. (This guards the observed failure where a hallucinated slug caused a subagent to fabricate an entire feature.)

10. **HARD CONSTRAINT — stop-authorization: the orchestrator MUST NOT end a run except on `max-cycles` or a genuine script-emitted terminal it JUST received from the state probe.** The ONLY legitimate no-`AskUserQuestion` stops are: (a) `forward_cycles >= max_cycles` (Step 1c), and (b) a `terminal_reason` in {`all-features-complete`, `all-bugs-fixed`, `max-cycles`, `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-missing`, `blocked-halt-for-manual`, `needs-research`, `queue-blocked-on-research`} returned by the state script in the CURRENT cycle's probe. Any DESIRE to stop for ANY other reason — context pressure, orchestrator-context load, reliability friction, "I think I should checkpoint", or ≥2 guard denials in an **attended** run — is NOT license to end the run. The orchestrator MUST first route through the budget-and-queue-guard `AskUserQuestion`. A checkpoint stop MAY then proceed only after the operator confirms and only by calling `lazy-state.py --run-end --reason checkpoint --operator-authorized`. The script now **mechanically enforces** this: an attended `--run-end --reason checkpoint` without `--operator-authorized` is REFUSED (exit 1, marker kept) — an orchestrator that unilaterally decides to checkpoint will be denied and must continue or ask. *Motivating incident (2026-06-14 / lazy-validation-readiness Phase 7):* during an attended `/lazy-batch 50` run the orchestrator permanently stopped at 5/50 cycles via `--run-end --reason checkpoint` without presenting an `AskUserQuestion` — the ≥2-denial prose trigger was read as license to stop unilaterally in an attended run; it is not. When passing `--run-end` on a genuine terminal, INCLUDE `--terminal-reason <reason>` (from the sanctioned set above) for stop-authorization validation; omitting it is back-compat but deprecated.

**Cycle-subagent execution model (recursive dispatch is NOT available — inline edits required).** The cycle subagent dispatched at Step 1d does **not** have the `Agent` tool: recursive sub-subagent dispatch is not supported from inside a dispatched subagent, even on workstation. (This was confirmed empirically — an `/execute-plan` cycle subagent that tried to dispatch Sonnet test/impl agents found the tool unavailable and could only halt.) This forces a load-bearing override of any dispatched skill's sub-subagent contract: skills that nominally fan out to sub-subagents (e.g. `/execute-plan` → Sonnet test-agent + impl-agent, `/retro` → research subagents A–G) MUST be performed INLINE inside the cycle subagent itself using `Edit`/`Write`/`Read` directly. **This override applies only at the cycle-subagent level** — the orchestrator still dispatches exactly one `Agent` per cycle, and the override never expands the orchestrator's `Write`/`Edit` scope (HARD CONSTRAINT 1 still holds; the orchestrator edits only sentinels). This is the same execution model as `/lazy-batch-cloud`; the two orchestrators are coupled per CLAUDE.md. (Unlike cloud, workstation retains the Tauri runtime, MCP HTTP server, audio device, and Windows tooling — only the recursive-dispatch limit and its inline-edit override are shared.)

> **Known limitation — TDD agent-separation is traded away.** Collapsing `/execute-plan`'s test-agent→impl-agent split into ONE inline cycle subagent means the *structural* test-first guarantee (a separate agent writes failing tests before a separate agent implements — the `R-EP-2`/`R-EP-3` separation) is GONE: it cannot be enforced from sub-subagent dispatch evidence when there is no dispatch. This is an intentional tradeoff given the no-recursive-dispatch reality, not a defect. Compensating controls: (1) per-batch **quality gates** (`R-EP-6`) still run and must pass 100%; (2) the **`/retro`** pass audits the landed work; (3) the **MCP-validation** pass (which writes `VALIDATED.md`) gates final completion. The inline cycle subagent SHOULD still write **tests-before-impl within each batch** — read the test expectations, write the failing tests, confirm they fail for the right reason, THEN implement — even though the ordering can't be structurally verified. `/lazy-batch-retro`'s cloud branch already grades `R-EP-2`/`R-EP-3` as `n/a (cloud-override)`; the same grading applies to inline workstation cycles.

## OUTPUT CONTRACT — orchestrator voice (read at run start)

**ALL orchestrator chat output MUST follow `~/.claude/skills/_components/orchestrator-voice.md`** — the turn-template contract (T1 run banner, T2 dispatch / T3 return / T4 inline-gate cycle blocks, T5 park line, T6 rich zones, T7 final report; mechanics silent; rules cited only on deviation; probe JSON never restated in prose). **ZERO-TEXT RULE:** Claude Code's general "say what you're about to do before tool calls / give brief updates" guidance is OVERRIDDEN for this run — the UI already prints every tool call; between tool calls emit NOTHING unless it is byte-shaped as a template (sanctioned output starts with `## `, `### Cycle `, a template field line, `⏸`/`⚖`/`⚠`, or a T6/T7 body — anything else, don't type it). No transition sentences, no "reading X", no "preflight passed", no "composing the dispatch". **Read it at run start, and RE-READ it after any compaction boundary** (alongside `lazy-dispatch-template.md` — see Step 1d's compaction discipline); the contract survives summarization by re-read, not by memory. Where an older passage in this skill prescribes a different chat-output shape, the contract's Precedence clause wins; the verbatim re-print / Zero-Context Operator Briefing requirements (HARD CONSTRAINT 6, `decision-resume.md`, `blocked-resolution.md`, `parked-flush.md`, `halt-resolution.md`) are sanctioned T6 rich zones and are never overridden. Graded by `/lazy-batch-retro`'s R-V-* rules.

**STANDING POLICY — completeness-first (D7).** Read `~/.claude/skills/_components/completeness-policy.md` at run start, and RE-READ it after any compaction boundary (it is on the Step 1d compaction re-read list). It is pre-authorized: decisions whose options differ only in effort / sizing / sequencing / completeness (`class: scope`) are auto-resolved to the MOST COMPLETE option in BOTH modes — logged (`⚖ policy:` line, `resolved_by: completeness-policy`, run-end D7 digest in the T7 report), never asked. It governs the cycle and input-audit subagent prompts (source suppression), Step 1g (scope-class sentinel resolution runs first), Step 1h (sequencing-only blockers auto-resolve; spin-offs pre-authorized, notify + log), and the Gate-1 coverage outcome at Step 1c.5 (author coverage / test-exempt, never ask). D7 only REMOVES questions — product-class decisions still ask exactly as before. Graded by `/lazy-batch-retro`'s R-D7-* rules.

`$ARGUMENTS` is tokenized on whitespace. Recognized tokens:

- **Positive integer** → `max_cycles`. If absent, default to `10`. If a non-numeric / `< 1` integer is supplied, refuse with:

  > `/lazy-batch` requires a positive integer max-cycles. Usage: `/lazy-batch <N> [--allow-research-skip] [--adhoc "<task>"] [--park]`. Default: 10.

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

**Budget-and-queue guard:** the orchestrator MUST NOT end a run with both budget remaining (`forward_cycles < max_cycles`) AND active queue items remaining (features that are neither complete, deferred, nor blocked on research) without first asking the operator (one `AskUserQuestion`) whether to continue into a new run or stop now. This prevents silent early exits where the orchestrator halts mid-queue without the operator realising. The `AskUserQuestion` path is the **attended default**. After the operator confirms a stop, the orchestrator passes `--operator-authorized` to `lazy-state.py --run-end --reason checkpoint`; without that confirmation flag the script REFUSES the checkpoint (exit 1, marker kept) — see HARD CONSTRAINT 10.

**Unattended-checkpoint arm (sanctioned early stop — UNATTENDED runs only).** In an **unattended** run (a scheduled / cron / overnight run that passed `--run-start --unattended` — see Step 0.55; interactive `/lazy-batch` invocations are **attended** and this arm does NOT apply), an early stop is sanctioned ONLY as a CHECKPOINT, and ONLY when a reliability trigger holds: **≥2 guard denials this run, OR an explicit operator pause message.** The reliability trigger sanctions an unattended checkpoint because no operator can answer the `AskUserQuestion` in a scheduled run. In an **attended** run — even if ≥2 guard denials occurred — the orchestrator MUST route through the budget-and-queue-guard `AskUserQuestion` (above) and may checkpoint only after the operator confirms. The script enforces this: an attended `--run-end --reason checkpoint` without `--operator-authorized` is REFUSED (exit 1, marker kept), so an orchestrator that "decides to checkpoint" without asking will be denied and must continue or ask. A checkpoint (unattended OR operator-authorized) requires ALL THREE of: (1) `python3 ~/.claude/scripts/lazy-state.py --run-end --reason checkpoint --next-route "<the probed next route>" [--operator-authorized]` (writes `lazy-run-checkpoint.json` so the next `--run-start` resumes from it; `--operator-authorized` is included when and only when the budget-and-queue-guard `AskUserQuestion` confirmed the stop); (2) a PushNotification carrying the next route + the trigger reason; (3) the T7 final report naming the trigger. An early stop WITHOUT the checkpoint `--run-end` (or without a holding trigger, or without operator authorization for an attended run) remains a contract violation — the unattended arm narrows, never widens, the silent-exit ban. **Resume side:** `--run-start` echoes `resumed_from_checkpoint` (and deletes the checkpoint file) when it consumes one; surface it on the T1 run-start block as one line (see Step 0.55 / orchestrator-voice.md T1).

Initialize counters and per-session state:
- `forward_cycles = 0` — initialized once per `/lazy-batch` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py` returns a new `feature_id`). Counts pipeline-advancing work; ceiling is `max_cycles`.
- `meta_cycles = 0` — initialized once per `/lazy-batch` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset on feature transitions). Counts resolution/recovery/cleanup work; **uncapped — no ceiling, no cap enforcement** (operator decision 2026-06-14). Only `forward_cycles` is capped (at `max_cycles`).
- `max_cycles = <parsed>`
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `cycle_log = []` — each entry: `{forward_cycles + meta_cycles, feature, action, subagent_summary}` (the running total is the monotonic N-th action in this invocation).
- `research_pending = set()` — feature_ids whose `RESEARCH.md` is missing and a `NEEDS_RESEARCH.md` sentinel was dropped this session. Only used when `allow_research_skip == true`. In the default (strict-halt) path this set never accumulates because Step 4 halts on the first feature; it stays empty.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. In the default path this stays `false` for the entire session because Step 4 halts before the loop continues.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched. **`sub_skill_args` is part of the tuple deliberately:** a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3) returns the same `(feature_id, sub_skill, current_step)` on every part but a *different* `sub_skill_args` (the plan-part path), which is real forward progress, not a loop. Omitting `sub_skill_args` made the loop-guard false-trigger on every multi-part plan. Including it lets the guard fire only on a genuine no-progress repeat (identical part re-returned).
- `adhoc_task = <parsed>` — the ad-hoc task text from `--adhoc` (empty string if the flag was present with no text; unset/`None` if the flag was absent). See Step 0.45.
- `park_mode = <parsed>` — `true` if `--park` was present, `false` otherwise. When `false`, all halt behavior is byte-for-byte the existing one.

---

## Step 0.0: Environment Preflight (FIRST — before the start banner and before remote sync)

**Read and follow `~/.claude/skills/_components/lazy-preflight.md` as the very first action of this
invocation — before the start banner, before Step 0.4 remote sync, before the first state probe.**
Run its read-only check block (skills symlink resolves, `~/.claude/scripts/lazy-state.py` exists,
`python3` runs, node resolvable — prepending `/c/nvm4w/nodejs` if needed). If any check fails, print the
component's setup recipe and **STOP — zero cycles consumed** (do not print the banner, do not call the
state script, do not enter the loop). On success, node is on PATH for the whole session (no per-call
`export PATH`), and you continue to the banner / Step 0.4 as normal.

**The entire run-start sequence is SILENT (zero-text rule):** the preflight, the contract/policy
reads, Step 0.4 remote sync, and the queue read for the banner are executed back-to-back with NO
text between the tool calls — no "I'll start by…", no "preflight passed", no "let me read…", no
"sync clean". The FIRST text this invocation emits is the T1 banner (preflight failure and sync
divergence are the T6 exceptions).

---

Print the start banner — **T1 per `~/.claude/skills/_components/orchestrator-voice.md`** (≤4 lines; nothing else before the first cycle block):

```
## /lazy-batch — run start
mode   workstation · park {on|off} · research {strict|batched}
budget fwd {max_cycles} · meta no cap
queue  {N} feature(s) · first: {first queue entry id}
```

The `queue` line is best-effort (one `Bash` read of `docs/features/queue.json` for the entry count — a banner fact, not state inference; state inference remains exclusively `lazy-state.py` per HARD CONSTRAINT 3); omit the line if the queue file can't be read cheaply. The repo root and flag parsing are mechanics — not announced.

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

5. On a clean fast-forward (or when local was already up to date / the branch was unpushed), continue to Step 0.5 **silently** — a successful sync is mechanics per the orchestrator-voice contract (silence means the machinery worked). Only the step-4 divergence halt is announced (a T6 error — recipe printed in full).

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

## Step 0.52: Validation-readiness pre-screen (advisory — F5 / lazy-validation-readiness)

**Purpose:** Before front-loading `DEFERRED_NON_CLOUD` features, emit a per-feature verdict table
showing whether each candidate's MCP test scenarios assert tools that are already registered in
the repo.  This surfaces "the scenario asserts a tool that doesn't exist yet" early — at curation
time — rather than three cycles later at the Step-9 mcp-test boundary.

**Run:**
```bash
python3 ~/.claude/scripts/validation_readiness.py --repo-root {cwd}
```

The script lives at `~/.claude/scripts/validation_readiness.py` (symlinked from
`user/scripts/validation_readiness.py` in the claude-config repo).

**Output format (example):**
```
validation_readiness — DEFERRED_NON_CLOUD pre-screen verdict
======================================================================
  FEATURE                                   VERDICT                 MISSING TOOLS
  ----------------------------------------  ----------------------  ------------------------------
  sidecar-watchdog                          ready
  d8-session-format                         needs-work              evaluate_code
  polyphonic-stems                          needs-work              get_diagnostic_counters
  ...
advisory: operator may still front-load a needs-work feature.
```

**This step is ADVISORY — not a hard gate.** The operator may still choose to front-load a
`needs-work` feature deliberately (e.g., the plan for this session IS to implement the missing
surface first). However, the verdict is logged so that if the run later hits a deep blocker at
Step 9, the blocker is traceable to an ignored pre-screen warning rather than appearing as a
surprise.  Features with no `DEFERRED_NON_CLOUD.md` are silently skipped (not front-load
candidates); features with `DEFERRED_NON_CLOUD.md` but no `mcp-tests/` scenarios are shown as
`ready (no scenarios)`.

**If the script is absent** (first run after the `claude-config` symlink was set up, or a
machine where the `~/.claude/scripts/` symlink hasn't been refreshed), skip this step silently
and continue to Step 0.55 — this is a zero-text-rule advisory, never a blocker.

---

## Step 0.55: Write the run marker (IMMEDIATELY before the T1 banner / loop entry)

After Step 0.5 (pre-loop ingest check) completes — and before printing the T1 banner or entering the Step 1 loop — write the run marker:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --run-start --max-cycles {max_cycles} \
  --repo-root {cwd}
```

**Attendedness:** interactive `/lazy-batch` invocations (the operator is present in the session) call `--run-start` WITHOUT `--unattended` — the marker records `attended: true` (the default). Only a scheduled/cron driver (a cloud task, an overnight automation) passes `--unattended`, recording `attended: false`. The `attended` field governs whether `--run-end --reason checkpoint` requires `--operator-authorized` (see HARD CONSTRAINT 10 and the budget-and-queue guard above). Legacy markers lacking the field are treated as attended — the stricter gate is the safe default.

**What this does.** The marker (`~/.claude/state/lazy-run-marker.json`) is the single on/off switch for the inject + validate-deny hooks. While the marker is present:
- The inject hook (`lazy-route-inject.sh`) fires on every UserPromptSubmit turn, runs the full probe form, and injects the route (`LAZY-ROUTE (hook-injected, turn N): …`) into the model's context via `additionalContext` — the orchestrator does NOT need to remember to probe; the probe arrives with the turn.
- The validate-deny guard (`lazy-dispatch-guard.sh`) checks every `Agent` dispatch against the prompt registry; an unregistered prompt is denied with a corrective recipe.

Interactive sessions (no marker) are **completely untouched** — both hooks exit instantly on the `test -f` fast path. The marker is script-owned: `--run-start` writes it; `--run-end` deletes it. The orchestrator never hand-writes the marker file.

**Session state pinned in the marker:** `pipeline=feature`, `cloud=false`, `repo_root`, `max_cycles`, `session_id` (bound on first hook firing), `nonce_seed`. Counters (`forward_cycles`, `meta_cycles`) are persisted in the marker from this point forward — the inject hook reads them without needing CLI flags.

**Resume from a checkpoint.** If a prior run ended via the unattended-checkpoint arm (Step 0 budget-and-queue guard), `--run-start` consumes `lazy-run-checkpoint.json` and echoes its content as `resumed_from_checkpoint` in the run-start output (then deletes the file — single-use). When the run-start output carries `resumed_from_checkpoint`, surface it on the T1 banner as one extra line — `resume <next_route> (checkpoint <date>)` (orchestrator-voice.md T1) — so the operator sees the run picked up where the checkpoint left off.

**`--run-end` is MANDATORY on every terminal/halt path** — see §1c.6 for the enumeration. A missed deletion is self-healing (24h staleness + session-id mismatch cleanup) but is a protocol violation the retro grades.

If `--run-start` fails (script error), surface a T6 `⚠` and STOP before printing the banner — a run with no marker is a run with no enforcement, which is still safe for the pipeline (it degrades to pre-Phase-5 behavior) but should not silently proceed without the operator knowing enforcement is off.

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run lazy-state.py

**LAZY-ROUTE banner check (FIRST — before deciding to run the probe).** The inject hook (`lazy-route-inject.sh`) fires on every UserPromptSubmit turn while the run marker is present. When the hook fires, it runs the full probe form itself and injects the result into the turn context as a single `additionalContext` string with the following structure:

```
LAZY-ROUTE (hook-injected, turn N): {"feature_id": "...", "sub_skill": "...", "cycle_prompt": "...", "cycle_model": "opus", ...} nonce=<hex-value>
```

On a post-compaction re-entry (the hook event is `PostCompact` or `SessionStart` with `source=="compact"`), the string also carries a `POST-COMPACTION RE-ENTRY:` paragraph after the nonce line. If the inject hook itself errored (fail-open breadcrumb), a `HOOK_ERROR: <error text>` suffix appears at the end of the string. The probe JSON is compact (no indentation) and contains all the same fields as a manual `lazy-state.py --repeat-count --emit-prompt --probe` invocation. **If the current turn carries a `LAZY-ROUTE (hook-injected, turn N):` banner**, consume it directly — extract `feature_id`, `sub_skill`, `cycle_prompt`, `cycle_model`, and all other probe fields from the injected JSON. **Do NOT run another `lazy-state.py` probe on this turn.** Re-probing when a banner is already present advances the persisted counters TWICE for one logical cycle — a protocol violation the retro grades. The counter in `cycle_header` is POST-advance (1-based current-cycle semantics — the script already incremented before injecting). If no LAZY-ROUTE banner is present (hook was inactive, or the turn is the first turn after a compaction boundary before the hook re-armed), run the probe as below.

```bash
python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]
```

Pass `--skip-needs-research` **only when `allow_research_skip == true` AND `skip_needs_research == true`**. The double-gate matters: in the default (strict-halt) path, `skip_needs_research` never flips to `true` because Step 4 halts the loop on the first `needs-research`, so the script is always called without the flag and returns `terminal_reason: needs-research` for the first research-pending feature in queue order. Only the `--allow-research-skip` path arms the legacy batching behavior.

**Probe enrichment (optional — folds repeat-count, git guards, and cycle header into one payload).** The orchestrator MAY call the probe with additional flags to fold `repeat_count`, `git_guards`, and `cycle_header` into the JSON in a single invocation:

```bash
python3 ~/.claude/scripts/lazy-state.py --repeat-count --emit-prompt --probe \
  --max-cycles {max_cycles} \
  [--skip-needs-research]
```

The `--forward-cycles` and `--meta-cycles` flags are NO LONGER passed on probe invocations. The marker persists the counters (`forward_cycles`, `meta_cycles`) from the moment `--run-start` wrote it; the inject hook and probe read them directly from the marker without needing CLI flags. The flags remain in the CLI for backward compatibility but MUST NOT be passed by the orchestrator — passing them would override the marker's persisted state with stale in-memory values.

`--repeat-count` enriches the output with a `repeat_count` field (how many consecutive cycles returned the same `(feature_id, sub_skill, sub_skill_args, current_step)` tuple) for mechanical loop detection. It ALSO emits a `step_repeat_count` field (how many consecutive cycles reached the same `(feature_id, current_step)` STEP — `sub_skill`/`sub_skill_args`-blind, and with NO head-advance reset). **Probe hygiene:** `--repeat-count` ADVANCES both persisted streaks, so it is reserved for the SINGLE dispatch-bound probe per cycle (the one whose result you actually dispatch on). Any diagnostic / inspection probe — re-checking state out of band, sanity-reading the routing — MUST use `--repeat-count-peek` instead (it reads the would-be streaks WITHOUT advancing the persisted state). The dispatch-tuple `repeat_count` is HEAD-aware: the same tuple plus new commits since the last probe RESETS it to 1 (a re-validation after landed commits is forward progress, not a loop). **`step_repeat_count` is the oscillation tripwire (T6): when it is `>= 3`, STOP — do NOT keep dispatching the emitted action mechanically.** Surface the warning `⚠ step '<current_step>' reached <step_repeat_count> times without advancing — inspect routing before dispatching`, then inspect WHY the state machine keeps returning to that step before continuing. Unlike `repeat_count`, the step counter does NOT reset when HEAD advances — it is built to catch "productive-looking" oscillation where each cycle commits a file (HEAD moves → the dispatch streak resets every iteration) yet routing never leaves the step (the live d8 write-plan loop on a gate-owned PHASES row, 2026-06-11). A high `step_repeat_count` with a low `repeat_count` is exactly that signature. Never redirect probe or diagnostic output into the repo tree — write to the OS temp dir (`$TMPDIR` / `%TEMP%`) if you must capture it. `--probe` (combined with the three counter flags) folds `git_guards` (clean-tree + origin-parity) and a pre-formatted `cycle_header` string into the response. `--emit-prompt` (composed with `--repeat-count`) folds the fully-assembled cycle dispatch prompt into the JSON: `cycle_prompt` (the complete, token-bound prompt — the loop block already appended when `repeat_count >= 2`, the mcp-test runtime variant already selected from the spec's PHASES.md `**MCP runtime:**` line) and `cycle_model` (`"opus"`, or `"sonnet"` when the loop block was appended). Both are `null` on pseudo-skill (`__*`) and terminal/idle probes; on an assembly failure for a real skill `cycle_prompt_refused` carries the reason instead. These flags are purely additive — the base JSON fields are unchanged. **`--emit-prompt` SHOULD be passed on EVERY probe** — it is `null` on pseudo-skill/terminal probes, so it is always safe to request, and folding prompt assembly into the same probe call is what makes Step 1d a pure consume-and-dispatch.

**Step 1a — probe ONCE per cycle (F2 double-probe debounce).** Run exactly ONE advancing, dispatch-bound `--repeat-count --emit-prompt` probe per cycle — the one whose `cycle_prompt` you actually dispatch — and use `--repeat-count-peek` for EVERY inspection / sanity / out-of-band probe so that only the single dispatch-bound probe advances the streaks. Probing a route twice with no dispatch between (an inspection probe, then the dispatch-bound probe) is a re-read, not a re-attempt, and historically inflated `step_repeat_count` into false `LOOP DETECTED` blocks. `update_repeat_counts` now defends this in depth: when a run marker is present it debounces a re-read via the registry consume-count delta (an unchanged consumed-emission count between two identical step probes ⇒ no dispatch landed ⇒ `step_repeat_count` is HELD, not incremented), so a genuine same-step oscillation (a real dispatch — hence a consume — between repeats) still trips while a benign double-probe no longer does. This note is the behavioral complement: even with the script debounce, keep to one advancing probe + peek for inspection.

**Investigation triggers + the inline-diagnosis budget (see `~/.claude/skills/_components/investigation-dispatch.md` — the dispatch template lives THERE, reference it, never inline-copy; the orchestrator emits the dispatch via `python3 ~/.claude/scripts/lazy-state.py --emit-dispatch investigation --context item_name=… --context spec_path=… --context symptom=… --context trigger=… --context inherited_hypotheses=… --context item_id=… --context cwd=…` and dispatches `dispatch_prompt` VERBATIM).** Root-cause diagnosis is dispatched work, not orchestrator work. Three triggers: (1) the probe JSON carries `validation_escalation: true` and no current `INVESTIGATION.md` exists in `{spec_path}` → the blocked-resolution path dispatches `/investigate` BEFORE any corrective phase (Step 1h carries the wiring); (2) **failed fix** — a fix cycle landed but the post-fix live/validation check shows the symptom unchanged → the next dispatch for that issue is `/investigate`, NOT another fix cycle (a headless-green fix built to an unverified orchestrator hypothesis once burned ~266k tokens and seeded the next bug); (3) **inline-diagnosis budget** — if you have spent more than ~8 of your own diagnostic tool calls (source reads, log greps, live probes) on one issue, STOP probing and dispatch `/investigate`; quick checks stay inline, sustained diagnosis does not (measured cost of unbounded inline diagnosis: ~60% of orchestrator activity + a mid-diagnosis compaction in the 2026-06-11 live run). **No-narrative-as-fact:** your dispatch prompts cite `INVESTIGATION.md` (artifact path + ledger rows) or say "cause unknown — investigation pending"; unproven hunches go to the investigation labeled `unproven`, never to a fix cycle as "strong hypothesis" headers.

**Park-mode probe flag (`--park` only).** When `park_mode == true` (the `--park` invocation flag), append `--park-needs-input` to EVERY `lazy-state.py` probe invocation in this step (base or enriched form alike). With the flag, the script skips features carrying an unresolved `NEEDS_INPUT.md` instead of halting on `needs-input` and reports them in a `parked[]` array on the JSON output — the input to the Step 1g park path and the §1c.6 park notifications. When `park_mode == false`, call the script plain (no `--park-needs-input`) — existing behavior, byte-for-byte; the `parked[]` key never appears.

If the script exits non-zero, run `python3 ~/.claude/scripts/lazy-state.py --run-end` (idempotent — safe even if the marker is absent), surface the error, push a PushNotification, print the final batch report (see Step 2), and STOP.

Parse the JSON output. Extract: `feature_id`, `feature_name`, `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`, `notify_message`, `diagnostics`.

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`**: see Step 1h (blocked-resolution mode). **Not a terminal halt anymore — and most blockers no longer ask.** Step 1h classifies the blocker FIRST per `completeness-policy.md` §3: a sequencing-only blocker (every resolution path converges on the same product behavior) is auto-resolved — add-phase + fix now, or `/spec-bug` / ad-hoc spin-off + dependency-gate + requeue-to-tail — logged + push-notified, no question. Only a genuine product fork takes the operator path: re-print the `BLOCKED.md` body verbatim, run `AskUserQuestion` for the resolution path (add a phase / defer to queue tail / halt-for-manual / custom), record the choice, dispatch the Opus apply-resolution subagent to enact it (neutralizing `BLOCKED.md` via rename), and return to Step 1a. The loop continues; do NOT print the final batch report — UNLESS the operator chooses "Halt for manual fix", which keeps `BLOCKED.md` untouched and STOPs (the legacy behavior, now one option among several).
- **`needs-input`**: see Step 1g (decision-resume mode). **Not a terminal state for the orchestrator anymore.** Step 1g first auto-resolves any scope-class decisions per `completeness-policy.md` (D7 — step 1b of the component, both modes, never asked); for the remaining product-class decisions it re-prints the rich `## Decision Context`, runs `AskUserQuestion`, appends `## Resolution`, dispatches the Sonnet apply-resolution subagent (which edits SPEC.md / PHASES.md and neutralizes the sentinel), and returns to Step 1a. The loop continues; do NOT print the final batch report.
- **`needs-research`**: see Step 4 (research halt). Behavior depends on `allow_research_skip`:
  - **Default (`allow_research_skip == false`)**: Step 4 writes `NEEDS_RESEARCH.md`, prints the inline-prompt halt announcement, PushNotifications, prints the final batch report, and STOPs. The orchestrator does NOT advance past the research-pending feature — this is critical for ordered queues where downstream features depend on upstream work.
  - **Opt-in (`allow_research_skip == true`)**: legacy batching behavior — Step 4 writes `NEEDS_RESEARCH.md`, adds `feature_id` to `research_pending`, **DOES NOT increment either counter**, flips `skip_needs_research = true`, and returns to Step 1a so the next state-script call passes `--skip-needs-research` and either advances to a ready feature or returns `queue-blocked-on-research`.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode). **Only reachable when `allow_research_skip == true`** — in the default path Step 4 halts before this terminal can fire.
- **`needs-spec-input`**: see Step 1i (operator-directed halt-resolution) — the orchestrator re-prints what the dir contains and `AskUserQuestion`s the path (provide spec direction → seed the baseline / defer & continue queue / halt). It no longer bare-STOPs "cannot start from nothing".
- **`queue-missing`**: Run `--run-end`, then PushNotification with `notify_message`, print final batch report, STOP. (There is no queue to continue — the operator must create `queue.json` first; NOT routed to Step 1i per the halt-resolution component's exclusion list.)
- **`completion-unverified`**: a feature's SPEC/ROADMAP claims `Complete` but no `COMPLETED.md` receipt exists — it was flipped OUTSIDE the validation gate (a cycle subagent or hand edit bypassing `/mcp-test` + the coverage audit). See Step 1i (operator-directed halt-resolution): re-print the gap and `AskUserQuestion` the path — reopen & re-validate (`**Status:** In-progress` → let the pipeline re-run MCP validation) / grandfather the receipt (`lazy-state.py --backfill-receipts`, only if genuinely validated before the gate) / defer & continue / halt. Do NOT auto-flip, auto-reopen, or auto-backfill — that judgment is the operator's, now surfaced as a choice rather than a bare halt. (This is the terminal that makes failure mode 1 self-announcing instead of silent.)
- **`stale_upstream`**: an upstream feature/work-item this feature was materialized from changed since materialize. See Step 1i (operator-directed halt-resolution): re-print the gap and `AskUserQuestion` the path (re-materialize/absorb → re-run materialize or `/realign-spec` / reject the change / defer & continue / halt). `lazy-state.py` emits this (Step 2.9); do NOT auto-resolve.
- **`all-features-complete`**: Run `--run-end`, then PushNotification `"ALL FEATURES COMPLETE — roadmap finished after {forward_cycles} forward + {meta_cycles} meta /lazy-batch cycle(s)."`, print final batch report, STOP.
- **`cloud-queue-exhausted`**: Unreachable for `/lazy-batch` (workstation variant); treat as `all-features-complete` defensively — run `python3 ~/.claude/scripts/lazy-state.py --run-end` first, then PushNotification, print final batch report, STOP.
- **`device-queue-exhausted`**: Reachable only on a **no-real-device** workstation (WSL2/CI, where the audio backend is the HeadlessPumpDriver). Every remaining feature carries `DEFERRED_REQUIRES_DEVICE.md` (real-device-only MCP assertions that cannot be certified here). Run `--run-end`, then PushNotification with `notify_message`, print final batch report, STOP. The honest resume is a real-device host: tell the user to set `ALGOBOOTH_REAL_AUDIO_DEVICE=1` (or run on native hardware) and re-run `/lazy-batch` — there the same features RE-OPEN (Step 9 dispatches `/mcp-test` scoped to the deferred scenario IDs as ordinary cycles) and complete. This is the device-axis mirror of `cloud-queue-exhausted`. Note: the **re-open dispatch itself needs no special handling** — on a real-device host the state script emits `sub_skill: mcp-test` for the deferred scenarios, which runs as a normal cycle.

### 1c. Check the max-cycles cap

If `forward_cycles >= max_cycles`:

```bash
python3 ~/.claude/scripts/lazy-state.py --run-end
```

```
PushNotification({ message: "lazy-batch hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP. Do NOT try to renew the cap automatically — the cap exists to bound runaway costs.

### 1c.6. PushNotification policy (park / halt / flush / run-end)

The orchestrator fires `PushNotification` at exactly four canonical event points so the operator receives a phone notification whenever the run changes state. `PushNotification` is always called by the **orchestrator** — state scripts never call it.

1. **park** (`--park` mode only) — fired once per newly-parked item when `park_mode == true` and the probe returns a non-empty `parked[]` array (the script's queue-walk park skip; `parked[]` arrives on ordinary Step 1a probes and lists ALL currently-parked items, not just new ones). **Dedup rule:** maintain an in-session set of already-notified parked ids; on each probe, fire only for ids in `parked[]` that are NOT yet in the set, then add them. Never re-fire for an id already in the set. (After a compaction boundary the set may be lost — one duplicate notification per item after a compact is acceptable; re-seed the set from the current `parked[]` on the first post-compact probe without firing.) Message carries the **running parked-count**: `"parked {feature_name} — {N} decision(s) parked so far this run"`. **Chat line (T5):** each newly-notified park also emits the single-line T5 park block to chat — `⏸ parked {feature_name} — {N} decision(s) · notified ({parked_count} parked this run)` — governed by the SAME dedup set as the notification (fire once per newly-parked id; never re-fire; re-seed silently after a compaction boundary).
2. **halt** (both modes) — fired on every terminal/halt: `NEEDS_INPUT` halt, `BLOCKED` halt-for-manual, `needs-research` strict halt, `queue-blocked-on-research`, `queue-missing`, `all-features-complete`, `max-cycles`, `device-queue-exhausted`, script-error, and any future obstacle terminal. Most of these already carry per-terminal `PushNotification` calls above — this point names the policy explicitly so no terminal can be added without a notification.

   **`--run-end` is MANDATORY before EVERY terminal/halt PushNotification.** On every path listed above, call `python3 ~/.claude/scripts/lazy-state.py --run-end` BEFORE the PushNotification fires. `--run-end` deletes the run marker AND the prompt registry (all run-scoped enforcement state). A missed deletion is self-healing (24h staleness + session-id mismatch cleanup) but is a protocol violation the retro grades. The call is idempotent — if the marker is already absent (e.g. `--run-start` failed earlier), `--run-end` exits cleanly.

   **Dev-runtime teardown is MANDATORY on run-end (ISSUE 4 — d8-effect-chains run, 2026-06-14).** The orchestrator OWNS the dev runtime it pre-booted in Step 1d.0 (`npm run dev:restart`), so it MUST tear it down when the run ends — otherwise the runtime (Vite 1420 + MCP 3333 + sidecar + Tauri binary) leaks across runs (a stray dev process was left running after the d8 run). On EVERY terminal/halt path, AFTER `--run-end` and BEFORE the PushNotification, run the full kill in the orchestrator session:

   ```bash
   npm run dev:kill   # workstation only; no-op-safe if nothing is running
   ```

   `dev:kill` (`scripts/kill-dev.js`) is the only reliable full teardown — it kills Vite, the MCP server, named-pipe-surviving sidecar processes, and orphaned Tauri binaries. Run it UNCONDITIONALLY on workstation runs (it is safe even if the runtime was never booted — e.g. an all-`not-required` queue). It is N/A for `/lazy-batch-cloud` (no desktop runtime is ever booted). The mcp-test cycle subagent does NOT kill the orchestrator-owned runtime mid-run (it may be reused next cycle); teardown is the orchestrator's responsibility at run boundary — see mcp-test SKILL.md Step 7.

   **`--terminal-reason <reason>` (SHOULD — deprecated to omit).** When ending a run on a genuine terminal (not an operator-authorized checkpoint), pass `--run-end --reason terminal --terminal-reason <reason>` where `<reason>` is one of the sanctioned set: `all-features-complete`, `all-bugs-fixed`, `max-cycles`, `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-missing`, `blocked-halt-for-manual`, `needs-research`, `queue-blocked-on-research`. The script validates `<reason>` against `lazy_core.SANCTIONED_STOP_TERMINAL` — an unsanctioned reason requires `--operator-authorized` or the call is refused (exit 1, marker kept). Omitting `--terminal-reason` is back-compat (the script infers `terminal` if `--reason` is absent) but is deprecated; include it for stop-authorization validation and retro auditability. (Phase 7 / lazy-validation-readiness.)
3. **flush** (`--park` mode only) — fired when parked decisions are collected and sent to the operator via the batched `AskUserQuestion` (the WU-4 flush protocol). The notification signals that the operator's input is being requested. Message: `"lazy-batch flush — {N} parked decision(s) ready for your input"`.
4. **run-end** (both modes) — fired when the run terminates and the final batch report is printed. This point largely coincides with the terminal halts above; stating it as a named point ensures every run termination path fires a notification, even if a new exit path is added that does not fit one of the named terminal reasons.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small sentinel-file write + commit, NOT a real skill that performs implementation work. Perform the action inline (orchestrator session) instead of dispatching a subagent. This is the spirit-preserving relaxation of HARD CONSTRAINT 1: sentinel files are documentation, and dispatching an Opus subagent to write a 10-line YAML block + run `git commit` wastes a full subagent's worth of context.

Follow `~/.claude/skills/lazy/SKILL.md` Step 3's protocol for each pseudo-skill exactly (the wrapper and orchestrator do the same thing here):

- **`__grant_skip_no_mcp_surface__`** — emitted at Step 9 (workstation only) when the feature's PHASES declares `**MCP runtime:** not-required` AND the repo has no app surface (no `src-tauri/`, no `package.json`). Run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __grant_skip_no_mcp_surface__ <spec_path>` (the script is the single author of the SKIP_MCP_TEST.md write — `granted_by: pipeline-structural`, re-verified by `skip_waiver_refusal`; idempotent; refuses if the repo has an app surface or PHASES is not `not-required`), then commit + push per policy. This is the structural short-circuit that avoids dispatching a wasted `/mcp-test` Opus cycle whose only job would be to confirm there is nothing to test. The next probe routes to `__write_validated_from_skip__`. Pipeline-advancing → `forward_cycles`.
- **`__write_validated_from_skip__`** — run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __write_validated_from_skip__ <spec_path>` (the script is the single author of the VALIDATED.md write — it reads SKIP_MCP_TEST.md, writes VALIDATED.md, and is idempotent), then commit + push per policy.
- **`__write_validated_from_results__`** — run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __write_validated_from_results__ <spec_path>` (the script reads MCP_TEST_RESULTS.md, writes VALIDATED.md with the extracted scenarios, and is idempotent), then commit + push per policy. **The script is the SINGLE author of VALIDATED.md — hand-writing it is the one remaining integrity side-door and is banned** (the 2026-06-11 run's endgame bypass). The apply is **gated**: it refuses (`refused:<reason>`, zero writes, exit 1) on missing/wrong-kind MCP_TEST_RESULTS.md, on `result` ≠ `all-passing`, on `pass_count != total_count`, and on a `validated_commit` that doesn't match HEAD (stale results). On a refusal, do NOT retry blindly and do NOT hand-write the sentinel — the refusal names expected vs found; the honest route is a fresh `/mcp-test` cycle that produces genuinely passing, fresh results (the refusal on stale/partial results IS the pipeline working).
- **`__mark_complete__`** — **gated by TWO inline docs-only gates, in order, BEFORE the flip runs.** **Gate 1 — MCP-coverage audit** per the shared `~/.claude/skills/_components/mcp-coverage-audit.md` component (read SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface; grep each `<spec_path>/mcp-tests/*.md` for each decision's id + keywords). If any decision is uncovered, follow the component's D7 outcome (`completeness-policy.md` §4 — Gate 1 never asks, no NEEDS_INPUT.md): documented-MCP-untestable decisions get an inline SPEC test-exempt note (a docs-level `__mark_complete__` edit — HARD CONSTRAINT 1 holds); the rest route to a **corrective coverage cycle** — dispatch a cycle subagent to author the `mcp-tests/` scenario(s) and run them (meta cycle), emit the `⚖ policy:` line(s) + D7-digest entries, then on Gate-1 halt: append `{forward_cycles + meta_cycles + 1, feature_name, "__mark_complete__ (gate 1 halted)", "{N} uncovered → corrective coverage cycle"}` to `cycle_log`, increment `forward_cycles` (gate-halted mark-complete is still a forward-advancing attempt), and return to Step 1a — the next mark-complete attempt re-audits `clean`. **Gate 2 — completion-integrity gate** per the shared `~/.claude/skills/_components/completion-integrity-gate.md` component (runs ONLY after gate 1 returns `clean`): verify phase-coherence (zero non-verification unchecked deliverables in PHASES.md) and that a validation sentinel (`VALIDATED.md`, or `SKIP_MCP_TEST.md`; workstation does NOT accept a bare `DEFERRED_NON_CLOUD.md`) exists. (`RETRO_DONE.md` is NO LONGER required here — retro is unwired, 2026-06.) If a precondition fails, the orchestrator writes `<spec_path>/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`) describing the gap and commits it; append `{forward_cycles + meta_cycles + 1, feature_name, "__mark_complete__ (gate 2 halted)", "<reason> → NEEDS_INPUT.md"}` to `cycle_log`, increment `forward_cycles`, return to Step 1a — the next state-script call returns `terminal_reason: needs-input` and Step 1g handles it before the next mark-complete attempt (Gate 2's integrity gaps are NOT scope decisions; they keep the needs-input path). Only when BOTH gates pass does the orchestrator proceed: run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __mark_complete__ <spec_path>` — the script is the single author of COMPLETED.md (kind: completed, provenance: gated, folding the validation evidence from VALIDATED.md/MCP_TEST_RESULTS.md into the receipt body — the durable proof `lazy-state.py` Step 2 keys on), the SPEC.md/PHASES.md `**Status:** Complete` flip, and the deletion of the consumed VALIDATED.md/RETRO_DONE.md/DEFERRED_NON_CLOUD.md sentinels (COMPLETED.md/SKIP_MCP_TEST.md/MCP_TEST_RESULTS.md are kept). **Mechanical third gate:** `--apply-pseudo` itself ALSO enforces per-phase coherence before writing — it auto-flips all-ticked phases to Complete and REFUSES (`refused:<reason>`, zero writes) if any phase retains an unchecked box (verification rows included) or a non-Complete/Superseded Status. On `ok: false` + this refusal, do NOT retry blindly — route a corrective coherence cycle. Emit the dispatch via the script (registry-registered, guard allows it):

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch coherence-recovery \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context gate_output="<the --apply-pseudo refusal reason string>" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch coherence-recovery` are: `item_name`, `spec_path`, `gate_output`, `item_id`, `cwd`. The subagent reconciles PHASES.md honestly (tick-with-evidence or re-scope, never blind-tick) then returns to Step 1a. Exactly as a Gate-1 halt routes. After the script returns, update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token) — this is the one remaining orchestrator step. Then commit + push per project policy. See the component files for the full gate algorithms. **Both gates are docs-only** (read SPEC.md / PHASES.md / `mcp-tests/*.md` / sentinels, no Tauri / no MCP server) — they run identically in workstation and cloud.
- **`__flip_plan_complete_cloud_saturated__`** — emitted only by `lazy-state.py --cloud` at Step 7a when an `In-progress` plan's only unchecked WUs (scoped to the plan's `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. `sub_skill_args` is the absolute plan-file path. Run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __flip_plan_complete_cloud_saturated__ <spec_path> --plan <plan_file_path>` (the script edits only the `status:` line in the plan frontmatter → `Complete`, is idempotent, and does NOT touch SPEC.md, ROADMAP.md, or any sentinel). Derive the plan part number from the plan's `phases:` field for the commit message (e.g. `phases: [6]` → part 6; fall back to the plan filename's leading `part-N` / `phase-N` token). Commit per project policy with message `chore(<feature_id>): mark plan part N Complete (cloud-saturated)`, then push. This is a **forward cycle** — increment `forward_cycles`.
- **`__flip_plan_complete_stale__`** — emitted by `lazy-state.py` at Step 7a (in both cloud and workstation mode) when EVERY work-unit a Ready/In-progress plan references is already `[x]` — the plan is stale/already-applied but the frontmatter `status:` was never flipped. `sub_skill_args` is the absolute plan-file path. **Action (stays inline — `--apply-pseudo` does NOT implement stale):** read the plan's YAML frontmatter, edit ONLY the `status:` line in place (`Ready` or `In-progress` → `Complete`) — leave every other field and the markdown body untouched. Derive the plan part number from the plan's `phases:` field; fall back to the plan filename's leading `part-N` / `phase-N` token if `phases:` is missing. Stage the plan file and commit per project policy with message `chore(<feature_id>): mark plan part N Complete (stale — already applied)`. Do NOT touch SPEC.md, ROADMAP.md, or any other sentinel. **Distinction from `__flip_plan_complete_cloud_saturated__`:** stale fires in BOTH cloud and workstation (it is not cloud-only) and means every WU was already `[x]` — not deferred to workstation, genuinely done. Without this flip the `Step 7a: execute plan` probe would return an In-progress plan with all WUs done, the orchestrator would dispatch `/execute-plan` against it, the subagent would find no work, make no commit, and the next cycle would return the same state — a no-op loop. This is a **meta cycle** — increment `meta_cycles` (flipping a stale plan is cleanup, not forward implementation work).

After the inline action:

1. Append to `cycle_log`: `{forward_cycles + meta_cycles, feature_name, sub_skill, "inline: <one-line summary>"}` (use the UPDATED total after the increment in step 5 below, i.e. the N-th total action completed this invocation).
2. **Push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** The inline pseudo-skill committed a sentinel / plan-frontmatter change locally; push it now — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This backstops inline cycles the orchestrator owns directly — a `git push` of an already-committed change, NOT a Write/Edit, so HARD CONSTRAINT 1 still holds. "Up to date" is a fine result (a prior cycle's push already carried it).
3. Emit the T4 inline pseudo-skill block (Step 3 / orchestrator-voice.md): the canonical step heading (`### {Step name} — {work summary} [x/y]`), an `act` line (`{sub_skill} → {feature_id}`), a `gates` line when gates ran (`__mark_complete__`), a `done` line (inline outcome), and a `next` line. Nothing else. A gate REFUSAL switches to T6-refusal (rich) — the refusal evidence and the NEEDS_INPUT routing deserve full detail.
4. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` (same uniform post-cycle update as Step 1e — keeps loop-guard accurate across mixed pseudo-skill / real-skill cycles).
5. Increment the appropriate counter: `forward_cycles` for pipeline-advancing pseudo-skills (`__mark_complete__`, `__mark_fixed__`, `__write_deferred_non_cloud__` (cloud variant only — workstation `lazy-state.py` never emits this), `__write_validated_from_results__`, `__write_validated_from_skip__`, `__grant_skip_no_mcp_surface__`, `__flip_plan_complete_cloud_saturated__`); `meta_cycles` for cleanup pseudo-skills (`__flip_plan_complete_stale__`). Return to Step 1a — DO NOT fall through to Step 1d.

This saves one Opus dispatch per pseudo-skill action. On a typical feature lifecycle (workstation: 1 × `__write_validated_*` + 1 × `__mark_complete__` = 2 dispatches reclaimed; cloud: 1 × `__write_deferred_non_cloud__` minimum) the savings compound across a multi-feature queue pass.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

**Compaction discipline — re-read the dispatch template AND the output contract first.** Before composing this dispatch — and ALWAYS as the first action after any compaction boundary — re-read `~/.claude/skills/_components/lazy-dispatch-template.md`, `~/.claude/skills/_components/orchestrator-voice.md` (the chat-output contract — its turn templates survive summarization by re-read, not by memory; the re-reads themselves are silent mechanics), AND `~/.claude/skills/_components/completeness-policy.md` (the D7 standing policy — its auto-resolve rules likewise survive compaction by re-read, not memory). The dispatch template is the on-disk canonical dispatch skeleton (`subagent_type`, the REQUIRED `model:` field, prompt **envelope**) and carries the **Read-before-Edit rule**: compaction resets read-state, so re-`Read` any file (PHASES.md, plans, SKILLs, components) before you `Edit`/`Write` it. The prompt **contents** are NOT reconstructed by hand — they arrive pre-bound from the probe's `cycle_prompt` (the `--emit-prompt` field); the template governs only the dispatch ENVELOPE (which fields, which model). 41% of post-compaction spawns in the 2026-06-10 audit dropped the `model:` field — re-reading this template before each dispatch, and copying `cycle_model` into it rather than reconstructing prompts from memory, is what prevents that.

**Post-compaction re-entry protocol (HARD — the first post-compaction action is NEVER a dispatch).** Compaction is the measured protocol cliff (2026-06-11 run: after the compaction boundary the counters never recovered, probes stopped entirely, and prompts went hand-authored for the rest of the run). On the first turn after any compaction boundary, BEFORE any `Agent` call: (1) re-read Step 1a of this SKILL plus the three components named above; (2) the session counters (`forward_cycles`, `meta_cycles`) are persisted in the run marker — the post-compaction probe reads them from the marker directly, so no manual reconstruction is needed. As a cross-check, verify the surviving T1/T2/T4 context broadly agrees with the marker's counters; if there is a discrepancy, trust the marker (it is the script-owned source of truth) and record any notable divergence in a single T6 `⚠` line; (3) run the FULL Step 1a probe form (`--repeat-count --emit-prompt --probe --max-cycles …`) — note: `--forward-cycles`/`--meta-cycles` are NOT passed (the marker owns the counters); proceed only from its output. Dispatching from a pre-compaction probe held in memory, or from a hand-reconstructed prompt, is a contract violation.

**Governing-file reload discipline (self-edit mode — C8).** When the Step 1a probe reports `self_edit_mode: true`, this `/lazy-batch` run is editing the very harness it executes from, so a cycle that commits to the orchestrator's own in-context governing prose makes the copy you hold stale. After EVERY cycle, intersect the cycle's commit (`git diff --name-only`, or read the probe's `governing_files_touched` list — the script computes the same intersection for you) with the **governing-file set** — the files the orchestrator holds in-context and does NOT get for free from a fresh subprocess / disk-read:
- `user/skills/lazy-batch/SKILL.md` (+ the `user/skills/lazy-bug-batch/SKILL.md` and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` twins for those orchestrators)
- `user/skills/_components/orchestrator-voice.md`, `user/skills/_components/completeness-policy.md`, `user/skills/_components/lazy-dispatch-template.md`

For ANY hit, re-`Read` that file via its `~/.claude/...` path BEFORE composing the next dispatch. This is the SAME re-read as the compaction discipline above — triggered by a self-edit commit instead of a compaction boundary — and the governing-file set MUST stay in lockstep with that compaction re-read list (if the compaction list grows, this set grows with it). The re-read is a silent mechanic (no chat narration).

**Auto-refresh boundary (documented no-ops — MUST NOT be reloaded; they were never stale).** These surfaces are ALREADY live on the next probe/dispatch and are EXCLUDED from the governing-file set by construction — never re-read them as part of the reload check: `lazy_core.py` / `lazy-state.py` / `bug-state.py` (a fresh `python3` subprocess runs every probe); `lazy-batch-prompts/cycle-base-prompt.md` + its addenda + `loop-block.md` (re-read by `emit_cycle_prompt` from disk every probe); hook `.sh` bodies (`bash ~/.claude/hooks/X.sh` reads the file each invocation); and downstream skill prose (each dispatched subagent loads its skill fresh).

**New-hook-registration restart surfacing (T6).** If a cycle's commit added or REMOVED a hook ENTRY in `settings.json` (a new `PreToolUse`/`PostToolUse` wiring object — NOT merely an edit to an already-wired script body, which is an auto-refresh no-op above), surface a single T6 line: `⚠ settings.json hook wiring changed — restart the session to (de)register; the running session still uses the old wiring`. Do NOT claim the change is live — hook registration is read at session start, so only a session restart re-registers it. Distinguish an ENTRY add/remove (restart-required) from a script-body edit (already live) explicitly.

**Never hand-append to `cycle_prompt`.** Repo-specific instructions (an audio-INVARIANTS gate, a project HARD requirement) live in `<repo>/.claude/skill-config/cycle-prompt-addenda.md` (same `@section` grammar as the base template) — the SCRIPT reads that file and appends the matching sections to `cycle_prompt`, token-bound and residue-checked. A live orchestrator hand-spliced the AlgoBooth audio gate onto the emitted prompt on 2026-06-11; that path is now closed — if a repo gate is missing, add a section to the addenda file, do not edit the dispatch.

**Long-build ownership (harness-tracked).** Any build or test that may exceed a single subagent turn is **orchestrator-owned**: start it with `Bash` `run_in_background: true` from this (the orchestrator) session and track it via the harness — NEVER background it from inside a dispatched cycle subagent, whose process tree is torn down when its turn ends (a `tauri build` backgrounded that way once silently vanished). Before committing to a 20–40 min packaged `tauri build`, run `cargo check --release` first to catch compile errors in minutes. Full rule: `.claude/skill-config/long-build-ownership.md`. This is `Bash`-only process ownership — it does not expand the orchestrator's sentinel-only `Write`/`Edit` scope (HARD CONSTRAINT 1 holds).

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else.

#### 1d.0. Pre-boot the dev runtime for `/mcp-test` cycles (WORKSTATION ONLY — runs BEFORE prompt composition)

**Applies ONLY when `sub_skill == "mcp-test"`.** Skip this sub-step entirely for every other `sub_skill`. (This sub-step does not exist in `/lazy-batch-cloud` — cloud's Step 9 returns `__write_deferred_non_cloud__`, never `mcp-test`, so the cloud orchestrator never reaches it.)

**Why this exists (the failure it fixes).** The cycle subagent has NO `Agent` tool (HARD CONSTRAINT block above) and runs `/mcp-test` INLINE. The mcp-test SKILL.md Step 2 boots `npm run tauri:dev` as a **background** task, then Step 4 waits for readiness. Empirically, an inline cycle subagent that started a background build and then ENDED ITS TURN waiting on it produced a premature, resultless return: the background build process did NOT survive the subagent's turn boundary, and the orchestrator (SendMessage unavailable in this workstation environment) could not resume the dead subagent. Net: a validation cycle that wrote no result and no sentinel, burning the whole cycle. The structural fix is for the **orchestrator's own session** — which is long-lived and persists across subagent turns — to OWN the dev-runtime background process, so the runtime is already up and MCP-ready when the mcp-test subagent connects to it.

**Procedure (orchestrator session, all `Bash` — NOT file edits):**

0. **Plan-declared structural untestability — skip the boot entirely (routing only, NOT a waiver).** Check the feature's PHASES.md for an `**MCP runtime:**` header line (authored by `/spec-phases` at decomposition time):

   ```bash
   grep -m1 '^\*\*MCP runtime:\*\*' "{spec_path}/PHASES.md"
   ```

   - Line says `not-required` → **skip steps 1–3 entirely** (no probe, no `dev:restart`, no readiness block — the ~3–7.5 min boot is pure waste when the deliverable has no MCP surface). The mcp-test prompt VARIANT (runtime-up vs no-runtime, with `{untestability_reason}` bound) is chosen by the SCRIPT — `emit_cycle_prompt` reads the same PHASES.md `**MCP runtime:**` line and selects the matching section, so the orchestrator does NOT swap any prompt block by hand here; the script-assembled `cycle_prompt` already carries the correct variant. The skip AUTHORITY stays with the mcp-test cycle (it verifies the plan's claim against `docs/features/mcp-testing/SPEC.md` and writes the `granted_by: mcp-test` + `spec_class` sentinel only if it concurs) — the plan field is routing, never a grant.
   - Line absent or `required` → proceed with steps 1–3 as written.

   **NEEDS_RUNTIME recovery:** if a no-runtime mcp-test cycle returns the single line `NEEDS_RUNTIME` (it found an MCP-testable surface the plan missed), run steps 1–3 NOW, then emit the re-dispatch via the script (registry-registered, guard allows it):

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch needs-runtime-redispatch \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context original_cycle_prompt_note="mcp-test cycle found MCP-testable surface; plan declared not-required" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch needs-runtime-redispatch` are: `item_name`, `spec_path`, `original_cycle_prompt_note`, `item_id`, `cwd`. The failed attempt + re-dispatch together consume ONE forward cycle (increment once, after the re-dispatched cycle returns); tag the re-dispatch `disp` line `(opus, recovery)`. A disagreement costs one extra dispatch round-trip — never correctness.

1. **Probe whether the dev runtime + MCP HTTP server are already up.** Per the AlgoBooth canonical reference (`docs/development/CLAUDE.md`, referenced from the root CLAUDE.md), the MCP HTTP server listens on **TCP 3333** and `GET http://localhost:3333/health` returns 200 when ready:

   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3333/health
   ```

   If this prints `200`, the runtime is already up — proceed to step 1a (stale-binary check) before skipping the boot.  **Do NOT amend the prompt by hand:** step 4 is the BOOT decision only — `emit_cycle_prompt` already selected the RUNTIME-IS-ALREADY-UP variant and bound every token, so the runtime-up case requires ZERO prompt edits. Splicing a "fresh-restart" / diligence paragraph into the RUNTIME-IS-ALREADY-UP block (or any other byte) mutates the hash and the validate-deny guard denies the dispatch — the exact recurrence the script-owns-the-variant rule (step 4) exists to make impossible.

1a. **Stale-binary check — force a `dev:restart` when native source advanced since boot (F7 / lazy-validation-readiness).** `GET /health == 200` proves the runtime is *alive*, but NOT that it is *current*: after a Rust MCP tool is added in a new commit, the still-running binary passes the health check but lacks the new tool.  An mcp-test cycle against that binary will 404 on a tool that actually exists in source.

   **Why this fires *before* dispatch, not after boot:** a binary that was already up when step 1 ran may have been running since before the latest native commit.  The stale check is the only gate that catches this.

   **Procedure:**

   a. Read the runtime's boot stamp.  **Prefer the session-log boot stamp** if it is available (AlgoBooth writes a `boot_time` ISO-8601 field into the session's opening event; re-resolve the active session dir — NEVER cache a `logs/session-{ts}/` path — and read it with `jq` or `grep`).  If the session-log stamp is unavailable, use a `boot_time` field from the health payload (an AlgoBooth-side follow-up: extend `GET /health` with a `boot_commit`/`boot_time` field; noted here as the minimal extension to make the boot stamp always machine-readable without log parsing).

   b. Run the stale-binary predicate (Python; never raises; fail-safe → False on any error):

      ```bash
      python3 ~/.claude/scripts/stale_binary.py \
        --repo-root "{cwd}" \
        --boot-iso "{boot_stamp_iso}"
      ```

      The script is at `~/.claude/scripts/stale_binary.py` (symlinked from
      `user/scripts/stale_binary.py` in the claude-config repo).  Globs default to
      `src-tauri` and `crates` (the AlgoBooth native-source roots).  Override with
      `--glob <path>` for non-AlgoBooth repos.

   c. If the script prints **`STALE`**: the native source advanced since boot → **force a `dev:restart`** now (steps 2–3 below), rather than trusting health=200.  The restart re-compiles the Rust binary and ensures the mcp-test cycle sees the current tool registry.

   d. If the script prints **`FRESH`** (or the boot stamp is unavailable and the script errors → `FRESH` / fail-safe): skip the boot (steps 2–3) and go to step 4.

   **Fail-safe note:** on any error (git not found, parse failure, no native commits) the script returns `FRESH` and the orchestrator proceeds without a restart — the existing health=200 gate is still the primary guard.  A spurious `FRESH` wastes nothing; a spurious `STALE` would trigger an unnecessary 3–7-min recompile on every cycle.  The fail-safe direction is chosen accordingly.

   *(Spec reference: F7 in `docs/specs/lazy-validation-readiness/SPEC.md`; predicate in `user/scripts/stale_binary.py`.)*

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

4. **No prompt amendment by hand — the script owns the runtime variant.** The mcp-test prompt variant (RUNTIME IS ALREADY UP vs RUNTIME NOT PRE-BOOTED) is selected by `emit_cycle_prompt` from the PHASES.md `**MCP runtime:**` line (step 0 above), so the probe's `cycle_prompt` already carries the right block — the orchestrator does NOT splice in a runtime paragraph. The orchestrator's ONLY job in this sub-step is the BOOT decision (steps 0–3): skip the boot on `not-required`, otherwise pre-boot the orchestrator-owned runtime so it is MCP-ready when the subagent connects. (NEEDS_RUNTIME re-dispatch handling is above in step 0.)

**HARD CONSTRAINT 1 is NOT relaxed by this.** Step 1d.0 is `Bash` only — a `run_in_background` process plus a `curl`/`sleep` readiness loop. It performs ZERO `Write`/`Edit` on any file (the orchestrator's sentinel-only edit scope is untouched). Owning a background process and polling a health endpoint are not file edits, exactly as Step 0.4's git reconciliation (also `Bash`-only) does not expand the edit scope.

**Consume the script-assembled prompt — do NOT hand-bind the template.** The probe's `cycle_prompt` field (from `--emit-prompt`) is the FULLY ASSEMBLED, token-bound cycle dispatch prompt: `emit_cycle_prompt` parsed the sectioned `cycle-base-prompt.md`, selected the right per-skill / per-pipeline / per-mode sections, bound every token (`{item_name}`, `{item_id}`, `{cwd}`, `{current_step}`, `{sub_skill}`, `{sub_skill_args}`, `{work_branch}`, … — the full 14-token list is in the component's header), appended the loop block when warranted, and chose the model. Use `cycle_prompt` **VERBATIM** as the Agent `prompt:` and `cycle_model` as the Agent `model:` — the orchestrator no longer reads `cycle-base-prompt.md` or `loop-block.md` by hand, and no longer substitutes `{tokens}`. **Loop-block inclusion and the opus/sonnet selection are SCRIPT-OWNED**, driven by the persisted per-pipeline `repeat_count` the script reads itself (loop block appended + `cycle_model: "sonnet"` when `repeat_count >= 2`, else `cycle_model: "opus"`).

**Continuation cycles re-emit — there is NO hand-composed real-skill prompt, EVER (probe→emit→dispatch atomicity).** A real-skill dispatch is valid ONLY when its `prompt:` is the `cycle_prompt` produced by an `--emit-prompt` probe run in the SAME turn as the `Agent` call. There is no sanctioned "continuation prompt": when a cycle returns partial, needs a retry, or work "continues" on the same feature, return to Step 1a and RE-PROBE — the script re-assembles the correct prompt for the new on-disk state, including any continuation context the sentinels now carry. The 2026-06-11 run's only two measured protocol failures (an orphaned 227k-token return whose prompt lacked the turn-end contract; a `result: pass` schema miss whose prompt lacked the schema section) were both hand-composed continuation prompts — drift began at the first continuation need and ratcheted, while the emitted path ran 12 consecutive cycles with zero failures. The ONLY exception is the documented `cycle_prompt_refused` degraded fallback below, which must be announced with its T6 `⚠` line.

**Freshness — never dispatch an emission from an earlier turn (applies to `cycle_prompt` AND every `--emit-dispatch <class>` output).** The emitted text is only dispatchable while it is verbatim in your context within the SAME turn it was emitted. If ANY turn boundary, compaction/summarization, or edit intervened since the emit, the in-context copy is no longer trustworthy — RE-EMIT fresh (a new probe / a new `--emit-dispatch`) and dispatch within that same turn. Hand-editing emitted text is the failure class this rule names: appending a note, "cleaning it up", re-typing it, or splicing in context all mutate the hash and trip the guard (the three self-inflicted prompt mutations in the first enforced run). The template's `--context key=value` slots are the ONLY sanctioned customization point — everything outside them is copied mechanically, byte-for-byte.

**In-session loop-guard — the orchestrator's CROSS-CHECK (retained):** Independently of the script, compute the current cycle's signature as the tuple `(feature_id, sub_skill, sub_skill_args, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)`, the state returned the same tuple two cycles in a row — almost always a missing terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`) or a plan/sentinel write the previous cycle should have made but didn't. **`sub_skill_args` MUST be part of the compared tuple** — otherwise a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3, same `feature_id`/`sub_skill`/`current_step` but a different plan-part path in `sub_skill_args`) false-triggers on every part despite genuine forward progress. This in-session guard still drives the T2 `(sonnet, loop-resolution)` `disp` tag. The guard and the script normally agree (the persisted `repeat_count` and the in-session signature track the same streak). **If the in-session guard fires but `cycle_model` came back `"opus"`** — e.g. the probe was run WITHOUT `--repeat-count` so the script saw no streak — **re-run the probe WITH `--repeat-count --emit-prompt --max-cycles {max_cycles}`** (no `--forward-cycles`/`--meta-cycles` — counters live in the marker) so the script re-assembles `cycle_prompt` with the loop block appended and flips `cycle_model` to `"sonnet"`. Do NOT hand-append the loop block or hand-flip the model — let the script own both.

The loop-guard evaluation itself is silent — never announce "no loop-guard fires" (orchestrator-voice.md hard ban); the only visible trace of a fired guard is the `(sonnet, loop-resolution)` tag on the T2 `disp` line.

**Fallback (degraded path, NOT the norm):** if `cycle_prompt` is `null`/refused for a REAL (non-pseudo, non-terminal) skill — the probe returned `cycle_prompt_refused` with a reason (e.g. unbound-token residue or an unknown section reference) — surface it as a T6 deviation line (`⚠ cycle_prompt refused: <reason> — falling back to hand-binding`) and fall back to reading `~/.claude/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (+ `loop-block.md` when the in-session guard fires) and binding the tokens by hand per the component's header comment. This is a degraded recovery path for an assembly bug, not the normal flow — the normal flow is consume `cycle_prompt` verbatim.

**Emit the T2 cycle-dispatch block (Step 3 / orchestrator-voice.md) immediately before the Agent call:** the canonical step heading (`### {Step name} — {work summary, ≤12 words} [x/y]`) + the `disp` line (`{sub_skill} → {feature_id} ({model}[, loop-resolution|recovery])`). Nothing else between the block and the dispatch. **Probe-presence guard:** the heading line MUST carry the dispatch-bound probe's `cycle_header` field VERBATIM (the `--probe` enrichment emits it pre-formatted) — never re-type or re-compose it from memory. A probe-shaped heading with no same-turn probe behind it is template-conforming narration over non-conforming behavior — the exact signature of the 2026-06-11 run's 5-hour zero-probe gap (12 probe-shaped headings, zero probes) — and is graded as a probe-cadence violation.

**Cycle-marker dispatch bracket (C1 — lazy-cycle-containment).** EVERY `Agent` dispatch this orchestrator issues — the real-skill cycle dispatch below AND every meta-dispatch (input-audit §1d.5, apply-resolution §1g/§1h, recovery §1c.5/guardrail-D, coherence-recovery §1c.5, hardening §1d.1, needs-runtime-redispatch §1d.0, investigation) — MUST be bracketed by the cycle-subagent marker so the C2 PreToolUse hook (`lazy-cycle-containment.sh`) and the C3 state-script refusals know a single cycle is in flight:

```bash
# IMMEDIATELY before the Agent dispatch (real cycle: --kind real; any meta-dispatch: --kind meta):
python3 ~/.claude/scripts/lazy-state.py --cycle-begin --feature-id {feature_id} --nonce {dispatch_nonce} --kind real
```

`--cycle-begin` writes `~/.claude/state/lazy-cycle-active.json` (self-healing: a stale marker from a crashed prior dispatch is overwritten + logged — the orchestrator is single-threaded, only one dispatch is ever in flight). `{dispatch_nonce}` is the dispatch's nonce (reuse the probe's `cycle_prompt_ref`/registry nonce when present, else any fresh hex). Pass `--feature-id` matching the feature this dispatch is for — the hook's 2nd-feature commit tripwire keys on it. `--cycle-begin` is NOT C3-guarded (the orchestrator owns the bracket); it is callable between cycles.

```bash
# IMMEDIATELY after the Agent returns — on EVERY return path (success, halt-with-sentinel, error):
python3 ~/.claude/scripts/lazy-state.py --cycle-end
```

`--cycle-end` clears the marker and is idempotent (zero error if already absent). Clear it explicitly on ALL THREE return paths — success, halt (the subagent wrote a sentinel), and error (the dispatch threw / returned malformed) — because a `--cycle-begin` left dangling would block the orchestrator's own next ops (`--run-end`, `--apply-pseudo`, the next probe's `--emit-dispatch`) via the C3 refusal. The script's self-healing staleness is a crash-only backstop, NOT a substitute for clearing on every return path. The `--cycle-end` is a silent mechanic (no chat narration).

Dispatch:

```
# 1. Set the cycle marker (C1):
python3 ~/.claude/scripts/lazy-state.py --cycle-begin --feature-id {feature_id} --nonce {dispatch_nonce} --kind real

# 2. Dispatch:
Agent({
  description: "lazy-batch cycle {forward_cycles + meta_cycles + 1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: <the probe's cycle_model>,
  prompt: <the probe's cycle_prompt_ref if present, otherwise cycle_prompt verbatim>
})

# 3. Clear the cycle marker (C1) — on EVERY return path (success / halt / error):
python3 ~/.claude/scripts/lazy-state.py --cycle-end
```

**F2a dispatch-by-reference (PREFERRED when available).** When the probe emits `cycle_prompt_ref` (a `@@lazy-ref nonce=<hex>` token), use it as the `prompt:` field instead of the full `cycle_prompt` text. The PreToolUse guard resolves the token → registered bytes and rewrites the tool input before the subagent runs — the subagent receives the full prompt unchanged. This eliminates the transcription-slip class: the guard rejects mismatched hashes, so an orchestrator that accidentally paraphrases the prompt gets denied, not silently dispatched. Fall back to `cycle_prompt` verbatim ONLY when `cycle_prompt_ref` is absent or null.

**Meta-dispatch by-reference — PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites (Phase 7 / lazy-validation-readiness).** Every `--emit-dispatch <class>` call (hardening, input-audit, recovery, coherence-recovery, apply-resolution, needs-runtime-redispatch, investigation, and any future class) now emits BOTH `dispatch_prompt` (verbatim text) AND `dispatch_prompt_ref` (a `@@lazy-ref nonce=<hex>` token) in its JSON output. When dispatching any of these meta-dispatch prompts, PREFER `dispatch_prompt_ref` over the verbatim `dispatch_prompt` — the PreToolUse guard resolves the token to the registered bytes, eliminating byte-exact hand-transcription as a failure surface (the 2026-06-14 incident's 2 guard denials were caused by transcription drift on a verbatim meta-dispatch). Fall back to `dispatch_prompt` verbatim ONLY when `dispatch_prompt_ref` is absent or null in the emit output. This rule applies uniformly to every emit site in §1c.5, §1d, §1d.1, §1d.5, §1e, §1g, §1h, §1i, and any future dispatch site.

**Model selection — script-owned.** The orchestrator no longer chooses the model: copy `cycle_model` from the probe into the `model:` field (never omit it — see the dispatch template). The script makes the choice — `"sonnet"` ONLY when it appended the loop block (persisted `repeat_count >= 2`), `"opus"` otherwise. The rationale is unchanged: normal real-skill cycles run Opus because they can involve novel implementation decisions, while the loop-resolution cycle is mechanical (the prompt already carries the diagnosis — read the canonical sentinel schema, identify which sentinel's preconditions are met, write it, commit), so Sonnet suffices at roughly 5× the cost-efficiency. Because loop-resolution selection is mechanical and driven by the persisted streak, the script can own it deterministically.

#### 1d.1. Denial recovery (validate-deny guard + hardening dispatch)

The validate-deny guard (`lazy-dispatch-guard.sh`) fires on every `Agent` tool call when the run marker is present. If the guard denies the dispatch (the `permissionDecisionReason` contains a corrective recipe — prompt hash mismatch or stale/consumed nonce), follow this recovery sequence:

**Pending hardening debt (script-routed — the probe WITHHOLDS the forward route).** Every guard deny is appended to the deny ledger (`lazy-deny-ledger.jsonl`), and a marker-gated probe surfaces the outstanding count as `pending_hardening: <int>` (with `pending_denials: [<reason summaries>]` when `> 0`). While debt is pending, the probe does NOT emit a `cycle_prompt` at all — it returns `route_overridden_by: "pending-hardening-debt"` plus `hardening_emit_command`, a pre-composed `--emit-dispatch hardening` command with the `--context` bindings auto-derived from the oldest unacked denial. Run that command verbatim and dispatch its `dispatch_prompt`; the ledger entry is acked when the GUARD ALLOWS the hardening dispatch (not at emission — emitting without dispatching clears nothing). Repeat probe → hardening until the probe returns a normal forward route. **Consume the FULL probe JSON:** piping probe output through field-extractors (e.g. `python3 -c "...print(d['cycle_model'])"`) is BANNED — it blinds the orchestrator to `route_overridden_by` and any future routing field; read the whole JSON object every probe (the probe also prints a `⚠ pending_hardening` warning to stderr while debt is live). Hardening debt is also a run-end gate: `--run-end` REFUSES (exit 1) while any unacked denial remains. The `--ack-unhardened` override exists for operator authorization ONLY (it forces a clean run-end and prints the override into the run-end message, which retros grade) — the orchestrator never passes it autonomously.

**Trigger 1 — validate-deny (denied dispatch):**
1. Re-run the dispatch-bound probe: `python3 ~/.claude/scripts/lazy-state.py --repeat-count --probe --emit-prompt --max-cycles {max_cycles}`. The fresh `cycle_prompt` carries a newly registered nonce.
2. Dispatch the fresh `cycle_prompt` **VERBATIM** (do NOT paraphrase or re-compose — the guard validates the exact hash).
3. **IN ADDITION**, on EVERY guard denial emit a hardening dispatch (locked decision 4: a denial means a hand-composed prompt reached the guard, which is a harness gap by definition — inline, unbounded, no dedup):

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=validate-deny \
  --context item_id={feature_id} \
  --context denied_prompt_summary="<one-line summary of the denied prompt>" \
  --context denial_reason="<the permissionDecisionReason from the guard>" \
  --context probe_json="<probe JSON from this turn>" \
  --context registry_state="<relevant registry entries as JSON string, or 'empty'>" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM as an `Agent` call using `dispatch_model`. The hardening dispatch is emitted REGARDLESS of whether the re-probe dispatch (step 2) succeeds or fails — the denial itself is the trigger. **Depth-cap exception:** a denial OF a hardening dispatch never dispatches another hardening stage (see Depth cap below). If the step-2 re-dispatch is also denied, proceed to trigger 2.

**Trigger 2 — no-route (cycle_prompt_refused, unknown/contradictory state, marker/state divergence):**  
If the probe returns `cycle_prompt_refused`, or the state is contradictory/unknown and no valid route exists, emit a hardening dispatch:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=no-route \
  --context item_id={feature_id} \
  --context denied_prompt_summary="<one-line summary of the refused/failed prompt>" \
  --context denial_reason="<cycle_prompt_refused reason or no-route description>" \
  --context probe_json="<probe JSON from this turn>" \
  --context registry_state="<relevant registry entries as JSON string, or 'empty'>" \
  --context cwd="{cwd}"
```

**Trigger 3 — HOOK_ERROR breadcrumb in an injected banner:**  
If a LAZY-ROUTE banner carries a `HOOK_ERROR` breadcrumb (the inject hook failed open and recorded the error), emit a hardening dispatch with `trigger_kind=inject-hook-error` and `denial_reason` set to the breadcrumb text.

**Trigger 4 — process-friction (a `kind: process-friction` deny-ledger entry):**  
If the probe returns `route_overridden_by: "pending-hardening-debt"` and the oldest unacked ledger entry carries `kind: process-friction` (written by `--cycle-end` on a torn cycle bracket or unexpected commits), emit a hardening dispatch with `trigger_kind=process-friction`. Use the `hardening_emit_command` from the probe JSON verbatim — it already binds `friction_reason` and `friction_detail` in the `--context` keys instead of `denied_prompt_summary`/`denial_reason` (the `build_hardening_emit_command` function in `lazy_core.py` handles this automatically based on the entry's `kind`). This trigger fires **even when the runaway's work was salvaged** (D2: signal, not noise — accepting the output and hardening the bypass are orthogonal).

**All four triggers → hardening dispatch:**  
Parse the `--emit-dispatch hardening` output JSON (`dispatch_prompt`, `dispatch_model`, `dispatch_class`) and dispatch `dispatch_prompt` VERBATIM as an `Agent` call using `dispatch_model` (always `"opus"`). The prompt was registered at emit time; the guard will ALLOW it. Reference: `~/.claude/skills/_components/hardening-dispatch.md` for the full seven required `--context` keys.

**Depth cap (HARD — no recursion).** A denial of a hardening dispatch has TWO shapes; the guard's reason text discriminates them, and the recovery branches differently.

- **(a) Ordinary corrective recipe on the hardening dispatch (hash mismatch — a transcription slip on YOUR copy of the emitted `dispatch_prompt`).** The guard returns its normal corrective recipe (NOT a halt reason), meaning the prompt you dispatched did not byte-match the registered emission — you hand-edited it. This is NOT depth-1 recursion. Recovery: re-run `python3 ~/.claude/scripts/lazy-state.py --emit-dispatch hardening …` (fresh nonce, same `--context` keys) and make exactly ONE verbatim re-dispatch attempt, copying `dispatch_prompt` mechanically (no edits). A second recipe denial then falls through to the halt protocol below — never a third attempt.
- **(b) The guard's HALT REASON (its text contains "halt" and "PushNotification") OR a SECOND recipe denial.** The halt reason fires when the denied prompt matched a registered hardening-class entry — genuine depth-1 recursion (the depth-1 self-recursion guard). On this denial — OR after the single re-dispatch in (a) is itself denied — run the 4-step halt protocol (unchanged):
  1. Run `python3 ~/.claude/scripts/lazy-state.py --run-end`.
  2. Surface: `⚠ hardening dispatch denied — depth cap reached; halting run` (T6 rich zone).
  3. PushNotification: `"lazy-batch halted — hardening dispatch denied at depth cap; operator review required."`.
  4. Print final batch report, STOP. Do NOT attempt a hardening dispatch beyond the single (a) re-attempt under any circumstances.

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

**Dispatch (emit-dispatch — registry-validated):**

Emit the input-audit dispatch prompt via the script (registry-registered, so the validate-deny guard will ALLOW it):

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch input-audit \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context cycle_kind="{sub_skill}" \
  --context cycle_summary="{cycle_summary}" \
  --context cycle_commit_sha="{cycle_commit_sha or HEAD~1}" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Parse the output JSON and dispatch `dispatch_prompt` VERBATIM using `dispatch_model`:

```
Agent({
  description: "lazy-batch input-audit (cycle {forward_cycles + meta_cycles}): {feature_name}",
  subagent_type: "general-purpose",
  model: <dispatch_model from emit output>,
  prompt: <dispatch_prompt VERBATIM — do NOT paraphrase or re-compose>
})
```

The `@requires` keys for `--emit-dispatch input-audit` are: `item_name`, `spec_path`, `cycle_kind`, `cycle_summary`, `cycle_commit_sha`, `item_id`, `cwd`. The component file `~/.claude/skills/_components/lazy-batch-prompts/dispatch-input-audit.md` describes the subagent's job — do NOT delete that file reference; it is the subagent's contract, not the orchestrator's composition source.

**After the audit subagent returns:**
1. If it wrote `NEEDS_INPUT.md`, carry it on the cycle's T3 `audit` line (Step 3 / orchestrator-voice.md): `audit  {N} product-behavior decision(s) surfaced → NEEDS_INPUT.md` (one line, no further prose).
2. If it returned "clean — no product-behavior decisions baked in", emit a REQUIRED skip-disclosure `audit` line — the NEEDS_INPUT-skip is NEVER silent (an operator must be able to tell a deliberate, justified skip from an audit that never ran). Format: `audit  needs-input skipped — {N} decision(s) reviewed, all {mechanical-internal | scope-class (D7) | none arose}; no product-behavior call at stake — {≤12-word justification from the audit's return}`. The justification comes from the audit subagent's clean-return summary (see `_components/lazy-batch-prompts/input-audit-prompt.md` step 5 / dispatch-input-audit.md). This is the canonical NEEDS_INPUT skip-disclosure rule (`_components/sentinel-frontmatter.md` → "Producer responsibilities" #7); it is graded by `/lazy-batch-retro` R-V-*.
3. If it flagged a missing/malformed Decision-Classification Ledger, surface it as a T6 deviation line: `⚠ /spec --batch cycle returned no Decision-Classification Ledger (contract violation)`. This surfaces the contract issue without halting.
4. Audit costs are NOT separate cycles — the audit shares the cycle's slot in `cycle_log` and does not increment the cycle counter. The audit subagent is bounded (read SPEC/RESEARCH/diff, classify, optionally write one sentinel), so its context footprint is small.
5. Proceed to Step 1e. The next state-script call at Step 1a will surface `needs-input` if the audit wrote `NEEDS_INPUT.md`, and Step 1g handles resolution inline (no loop halt).

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{forward_cycles + meta_cycles + 1, feature_name, sub_skill, subagent's one-paragraph summary}` (use the total BEFORE the increment below, so the entry matches the in-flight cycle number).
2. Emit the T3 cycle-return block (Step 3 / orchestrator-voice.md) under the cycle's T2 heading: a `done` line (ONE line — duration + the load-bearing outcome); on an `/execute-plan` cycle an `audit` line — REQUIRED, this is the inline-override audit signal `/lazy-batch-retro` grades: confirm the subagent performed the edits inline (zero Agent() calls) with test-first discipline per batch plus the gate outcome (e.g. `audit  RED→GREEN 33/33 · gates qg:ts green · inline, zero Agent()`); a `ledger` line (the step 4/4a guard outcome — `clean · pushed` when healthy); and a `next` line (the fresh probe's routing, or `terminal: <reason>`). The retired 3–5-bullet cycle summary must NOT reappear — details live in the commit and the docs the subagent wrote.
3. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` so the next cycle's Step 1d loop-guard can compare against this cycle.
3a. **Spin-off notification (any cycle return reporting a spin-off).** If the returned summary reports that the cycle spun off a bug doc or an `--enqueue-adhoc` feature (the cycle owns the reverse-reference in the origin feature's doc per `cycle-base-prompt.md`), the orchestrator fires `PushNotification("spun off {id} — {reason}")` and adds a D7 digest entry (`completeness-policy.md` §Logging — the run-end T7 digest table). Spin-offs are pre-authorized (`completeness-policy.md` §5); this is notify + log, never a question.
4. **Post-cycle push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** Verify the work branch is pushed — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). The cycle subagent's Step 1d already commits and pushes to the current branch at end-of-cycle, so this normally reports "up to date" — it is the backstop for any cycle that did not push itself. A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 still holds.
4a. **Post-`/execute-plan` (and `/mcp-test`) ledger-consistency guard (guardrail D — codifies the previously-ad-hoc operator check).** When the cycle that just returned was `/execute-plan` or `/mcp-test`, run a SINGLE-TURN consistency check BEFORE the next state probe (Step 1a). This is one scripted check fired on the cycle's completion notification — NOT polling, so HARD CONSTRAINT 7 (no active waiting) holds; these are `Bash` reads, so HARD CONSTRAINT 1 holds too. The cycle subagent is supposed to leave a clean, consistent ledger via the atomic gate+commit (Step 1d `/execute-plan` override), but it empirically loses its turn between gates and commit — this guard catches the residue deterministically instead of relying on operator memory.

   First fetch so `@{u}` is current (the `--verify-ledger` `head_matches_origin` check compares HEAD to `@{u}` and does NOT fetch itself):
   ```bash
   git fetch origin $(git rev-parse --abbrev-ref HEAD)
   ```
   Then run — **plan-scoped on `/execute-plan` cycles, feature-level on `/mcp-test` cycles:**
   ```bash
   # /execute-plan cycle — scope the guard to the plan part this cycle just executed
   # ({plan_file} = the probe's sub_skill_args, the absolute plan-file path):
   python3 ~/.claude/scripts/lazy-state.py --repo-root <repo_root> --verify-ledger {spec_path} --plan {plan_file}
   # /mcp-test cycle (no plan part) — feature-level call, unchanged:
   python3 ~/.claude/scripts/lazy-state.py --repo-root <repo_root> --verify-ledger {spec_path}
   ```
   With `--plan`, `plan_complete` checks THIS plan part's frontmatter flipped `Complete` and `deliverables_done` reads THIS plan part's own `- [ ] WU-N` checkboxes (the machine source of truth since the 2026-06-15 d8-effect-chains review — NOT the PHASES.md phase-level deliverable rows). Because the plan part is the unit of execution and its WUs never span parts or phases, a still-pending LATER plan part no longer false-fails the guard (cite: live-run false alarm 2026-06-11), AND the two PHASES-scoping false-fails the old read suffered are gone: (a) cross-part (a phase's deliverable row belonging to a different plan part of the same phase) and (b) cross-phase attribution (a deliverable filed under Phase N but built in corrective Phase N+1). Read the JSON `ok`/`failing_check`/`checks` fields plus the diagnostic `deliverables_source` (`plan-wu-checkboxes` normal; `phases-fallback …` = a legacy pre-ISSUE-6 plan with no per-WU rows). (`--cloud` is NOT needed for `--verify-ledger`; the plan-Complete check is the same in both modes.)

   If `ok` is true → continue to step 5. If `ok` is false → reconcile per the named `failing_check`:
   - `clean_tree` or `head_matches_origin` failing → auto-dispatch a recovery cycle subagent (NOT a numbered cycle, does NOT increment `forward_cycles`) whose sole job is to stage + commit + push any uncommitted/unpushed residue, then re-run `--verify-ledger` until ok.
   - `plan_complete` failing (`/execute-plan` only) → the recovery subagent re-flips the plan-part frontmatter `status:` to `Complete`, then re-runs the guard.
   - `deliverables_done` failing → the failing surface is the plan part's `- [ ] WU-N` checkboxes (when `deliverables_source` is `plan-wu-checkboxes`). The common reconciliation is: a landed WU whose plan-body box is merely unticked → tick it `- [x]`, commit + push. This does NOT require chasing PHASES.md deliverable rows in other parts/phases — those no longer gate. The recovery subagent may tick a **verification** WU box (one under a "Runtime Verification / MCP Integration Test" subsection) ONLY when there is on-disk evidence that verification actually ran for that row (e.g. `VALIDATED.md` or `MCP_TEST_RESULTS.md` present in `{spec_path}/` and covering it). If a non-verification WU is genuinely incomplete it is real outstanding work → route back to execute-plan, or if blocked write `{spec_path}/NEEDS_INPUT.md` describing the gap and surface it — do not silently tick unverified or incomplete boxes. Note: `--verify-ledger`'s `deliverables_done` already exempts verification-only WU rows, so it will not false-fail on legitimately-pending Runtime-Verification boxes.

   Emit the recovery dispatch via the script (registry-registered, guard allows it):

   ```bash
   python3 ~/.claude/scripts/lazy-state.py \
     --emit-dispatch recovery \
     --context item_name="{feature_name}" \
     --context spec_path="{spec_path}" \
     --context failure_summary="<failing_check name: <description of what failed>>" \
     --context item_id="{feature_id}" \
     --context cwd="{cwd}"
   ```

   Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch recovery` are: `item_name`, `spec_path`, `failure_summary`, `cwd`, `item_id`. The component file `~/.claude/skills/_components/lazy-batch-prompts/dispatch-recovery.md` describes the subagent's job — do NOT delete it. Surface the failed check per T6 (`⚠ verify-ledger {failing_check} failed` → evidence → recovery action taken), and record the post-recovery outcome on the cycle's T3 `ledger` line. Do NOT advance to Step 1a until the guard passes.
5. Increment `forward_cycles`. Return to Step 1a. **Both counters are monotonic across feature transitions (HARD CONSTRAINT 8).** If the next state-script call returns a different `feature_id` — e.g. because this cycle's `__mark_complete__` finished the prior feature, or the queue rolled forward to the next ready feature for any other reason — the counters continue from where they were. Do NOT reset either counter on the boundary.

**Note:** Step 1c.5 (pseudo-skill inline handling) MUST also update `prev_cycle_signature` to the cycle's `(feature_id, sub_skill, sub_skill_args, current_step)` tuple before returning to Step 1a. Otherwise a real-skill cycle following a pseudo-skill cycle would compare against a stale signature and miss loops that span both kinds. The orchestrator should treat the prev-signature update as a uniform post-cycle action regardless of whether the cycle dispatched a subagent or ran inline. The same applies to the counter increments: they are uniform post-cycle actions that happen once per cycle (real, pseudo, or decision-resume) and never reset.

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

**Reachable only when `allow_research_skip == true`.** Triggered when `lazy-state.py --skip-needs-research` reports `queue-blocked-on-research` AND `research_pending` is non-empty (the orchestrator has already dropped at least one `NEEDS_RESEARCH.md` this session). The user's Gemini deep-research step is the blocker. In the default (strict-halt) path this state is unreachable because Step 4 halts on the first `needs-research` before the loop ever reaches `queue-blocked-on-research`.

**This is a passive halt, NOT an active wait.** The orchestrator MUST NOT use `Monitor`, `sleep`, polling loops, or any other mechanism to block on filesystem events (HARD CONSTRAINT 7). Research arrives on the user's timeline — they may be away from their device for hours or days. The orchestrator announces the halt, surfaces every supported upload path, fires a PushNotification, and stops. The user's next `/lazy-batch` invocation is the implicit resume signal; Step 0.5 (pre-loop ingest check) and `lazy-state.py`'s normal flow auto-detect uploads on re-entry — no special detection is needed at resume time.

**Algorithm:**

1. **Read every pending feature's RESEARCH_PROMPT.md.** For each `feature_id` in `research_pending`, locate the prompt file (the path is recorded in the just-written `NEEDS_RESEARCH.md` sentinel's `research_prompt_path` field, resolved relative to that feature's `spec_path`). Read its content; measure its character count.

2. **Announce the halt with inline prompts (a sanctioned T6 rich zone — print in full).** The mobile-friendliness goal: every prompt the user needs to paste into Gemini is in chat, in a fenced code block, ready for long-press-copy. No GitHub UI navigation required. **Read `~/.claude/skills/_components/lazy-batch-prompts/research-halt-announcement.md` now** and use **Variant B** (the `queue-blocked-on-research` multi-feature path). Print the opening block, then the per-feature block for EACH `feature_id` in `research_pending` (binding {feature_id}, {feature_name}, {spec_path}, {RESEARCH_PROMPT content}, {NNNN chars}, {within|over}), then the unified upload instructions (binding {max_cycles}). The `[length: ...]` line is a soft indicator. When over cap, append the addendum `(may need manual trimming before paste)` so the operator notices on mobile without scrolling back. Do NOT refuse to print — over-cap prompts are still printed in full; the warning is informational.

3. **Run `--run-end`:**

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --run-end
   ```

4. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {N} feature(s) awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

5. **Append to `cycle_log`:** `{forward_cycles + meta_cycles + 1, "—", "⏸ research-wait (halt)", "{N} feature(s) pending: {feature_ids}"}`. DO NOT increment either counter — the halt is not a real cycle.

6. **Print the final batch report (Step 2)** with `terminal_reason = "queue-blocked-on-research"` and STOP. The orchestrator's turn ends; the user's next invocation re-enters via Step 0 → Step 0.5 → Step 1.

**Resume contract.** When the user re-invokes `/lazy-batch`, the natural flow handles every supported upload path:

| Upload path | Detected by | Handled by |
|-------------|-------------|------------|
| ① Staged `.txt` in `docs/gemini-sprint/results/` | Step 0.5's `find` probe | Step 0.5 dispatches `/ingest-research` (1 cycle) |
| ② Direct `RESEARCH.md` in feature dir | `lazy-state.py` Step 5 | normal main-loop dispatch of `/spec` Phase 3 |
| ③ One-off path | User ran `/ingest-research <path>` separately before `/lazy-batch`; that invocation copied the file to the staging dir and processed it. By the time `/lazy-batch` starts, `RESEARCH.md` is already in the canonical location | normal main-loop dispatch (path ② applies) |

No special resume detection is needed in `/lazy-batch`'s main loop — every upload path lands in a state the existing logic already handles.

**Cycle accounting at resume.** The new `/lazy-batch` invocation gets a fresh `max_cycles` budget. The previous session's cycle count is gone (no persistence layer — see Notes). This is by design: each `/lazy-batch <N>` run is a bounded budget the user authorizes.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

**No meta-cap check** — `meta_cycles` is uncapped (operator decision 2026-06-14); the meta loop has no halt. The run's only hard stop remains the `forward_cycles >= max_cycles` cap at Step 1c.

**Pipeline binding for the shared handler below** — `{SKILL}` = `/lazy-batch`, `{STATE_SCRIPT}` = `lazy-state.py`, `{ITEM}` = feature, `{PUSH_RULE}` = workstation (the apply subagent's standard end-of-work push suffices). The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`** (decision-resume is a meta cycle). The per-cycle update block heading uses the two-counter format (Step 3 template). Then read and apply the shared decision-resume handler exactly (single source across the feature / bug / cloud batch orchestrators):

**Apply-resolution dispatch (emit-dispatch — registry-validated).** When the shared handler instructs you to dispatch the apply-resolution subagent, emit it via the script rather than hand-composing:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch apply-resolution \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context sentinel_path="{spec_path}/NEEDS_INPUT.md" \
  --context resolution_summary="<one-line summary of the chosen resolution>" \
  --context resolution_kind="needs-input" \
  --context chosen_path="<the option label the operator chose>" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch apply-resolution` are: `item_name`, `spec_path`, `sentinel_path`, `resolution_summary`, `resolution_kind`, `chosen_path`, `item_id`, `cwd`.

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

**No meta-cap check** — `meta_cycles` is uncapped (operator decision 2026-06-14); the meta loop has no halt. The run's only hard stop remains the `forward_cycles >= max_cycles` cap at Step 1c.

**Pipeline binding for the shared handler below** — `{SKILL}` = `/lazy-batch`, `{STATE_SCRIPT}` = `lazy-state.py`, `{ITEM}` = feature, `{SPEC_ROOT}` = `docs/features`, `{ADD_PHASE}` = `/add-phase`, `{PUSH_RULE}` = workstation (standard push). The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`** (blocked-resolution is a meta cycle). Then read and apply the shared blocked-resolution handler exactly (single source across the feature / bug / cloud batch orchestrators):

**Apply-resolution dispatch (emit-dispatch — registry-validated).** When the shared handler instructs you to dispatch the apply-resolution subagent, emit it via the script rather than hand-composing:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch apply-resolution \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context sentinel_path="{spec_path}/BLOCKED.md" \
  --context resolution_summary="<one-line summary of the chosen resolution>" \
  --context resolution_kind="blocked" \
  --context chosen_path="<the option label the operator chose>" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Dispatch `dispatch_prompt` VERBATIM using `dispatch_model`. The `@requires` keys for `--emit-dispatch apply-resolution` are: `item_name`, `spec_path`, `sentinel_path`, `resolution_summary`, `resolution_kind`, `chosen_path`, `item_id`, `cwd`.

`~/.claude/skills/_components/blocked-resolution.md`

---

### 1i. Operator-directed halt-resolution (other non-max-cycles problem-terminals)

**No meta-cap check** — `meta_cycles` is uncapped (operator decision 2026-06-14); the meta loop has no halt. The run's only hard stop remains the `forward_cycles >= max_cycles` cap at Step 1c.

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
     • A sentinel that should have been written wasn't (VALIDATED.md,
       DEFERRED_NON_CLOUD.md, SKIP_MCP_TEST.md).
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
**Meta cycles used:** {meta_cycles}
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

*(Print the following table whenever the run applied the completeness-first standing policy at least once — BOTH modes, alongside the park auto-accept digest above when both fired. Omit entirely when no D7 applications occurred.)*

```
### Completeness-policy applications (D7)

| Feature | Decision / blocker | Chosen path | Spin-off | Link |
|---------|--------------------|-------------|----------|------|
| {feature_name} ({feature_id}) | {≤8-word summary} | {most-complete path taken} | {spun-off id or —} | `{resolved sentinel / SPEC note / scenario path}` |
| ... | ... | ... | ... | ... |
```

*(One row per `⚖ policy:` application across the run — Step 1g scope resolutions, Step 1h sequencing-only blocker resolutions, parked-flush Step 2.4 backstop resolutions, Gate-1 coverage routings, and cycle-subagent in-cycle applications disclosed in their summaries. This table is the run-end audit trail required by `completeness-policy.md` Logging; an application with no row here is an R-D7-2 fail.)*

Framing prose around the final report is capped at **≤2 sentences total (T7 per orchestrator-voice.md)** — the cycle table, counters, parked/auto-accept/D7 digests, terminal reason, and Next-step lines carry all required content.

STOP.

---

## Step 3: Cycle Output Discipline (orchestrator-voice.md is the binding contract)

Per-cycle chat output follows the turn templates in `~/.claude/skills/_components/orchestrator-voice.md` — re-read it after any compaction boundary. Every cycle — real-skill (Step 1e), inline pseudo-skill (Step 1c.5), decision-resume (Step 1g), blocked-resolution (Step 1h), or halt-resolution (Step 1i) — emits exactly its template blocks under the canonical step heading, and nothing else:

```
### {Step name} — {work summary, ≤12 words} [{n}/{max}]                   ← T2 heading
disp   {sub_skill} → {feature_id} ({model}[, loop-resolution|recovery])   ← T2, at dispatch
done   {duration} · {load-bearing outcome}                                 ← T3, at return
audit  {…}                                                                ← only where Steps 1e / 1d.5 require it
ledger {clean · pushed | …}                                               ← post-cycle guard outcome
next   {fresh probe routing | terminal: <reason>}
```

The heading leads with the **pipeline step being advanced to** (T2's canonical names: Spec / Investigate / Plan / Implement / Retro / Validate / Realign / Research / Mark Complete / Mark Fixed), then a **≤12-word summary of the work this cycle is about to do** (specific to the item, not a restatement of the step name), then the **counter**: `[{forward_cycles}/{max_cycles}]` for forward cycles (post-increment), `[meta {meta_cycles}]` for meta cycles (count only, no denominator — meta is uncapped) (decision-resume 1g, blocked-resolution 1h, halt-resolution 1i, stale-plan flip). Both counters are still tracked and both appear in the T7 final report. Inline pseudo-skill cycles emit T4 (`act` / `gates` / `done` / `next`) instead of T2+T3, under the same heading shape. The retired formats — the `### Cycle fwd N/M · meta K/L` heading, the `· {feature_name} · {sub_skill}` heading suffix, the `**Result:**`/`**Commit:**` bullet block, and any 3–5-line cycle summary — must NOT reappear; the contract's Precedence clause governs.

**Rules (all follow from the contract's "mechanics are silent" principle):**

- **The template blocks ARE the cycle's entire chat footprint.** No prose before, between, or after them.
- **No dispatch narration, no commit-strategy narration, no probe restating.** Loop mechanics, commit ownership, and probe JSON are a fixed contract, never per-cycle news — the cycle block's fields already carry `feature_id` / `sub_skill` / step.
- **Ignore commit prompts silently.** If a Stop hook or any other prompt asks whether to commit between cycles, do NOT answer with prose. The commit policy is already fixed; proceed to the next state probe without narration.
- **Deviations are T6, not extra bullets.** A failed guard, a gate refusal, a contract violation: `⚠ <symptom>` → evidence (quoted output, ≤10 lines) → action taken → the rule violated, cited here and only here.
- **Halt/terminal announcements, resolution briefings, and echo-backs are T6 rich zones; the final report is T7.** The Step 4 research halt, Step 1f research-wait, Step 1g malformed-sentinel halt, the Step 1g/1h/1i resolution briefings (verbatim sentinel re-prints + 1:1 AskUserQuestion option sets — HARD CONSTRAINT 6 stands in full), the standing-directive echo-back, and the Step 2 final report keep their own functional templated shapes — those are sanctioned rich output, not per-cycle narration.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

The state script returns `needs-research` when `RESEARCH.md` is missing but `RESEARCH_PROMPT.md` exists. This step has **two paths**, gated by the `allow_research_skip` flag parsed in Step 0.

The default path (strict halt) is the safer choice for ordered queues with cross-feature dependencies: the FIRST research-pending feature in queue order halts the loop, so downstream features that may depend on the in-flight one never start work prematurely. The opt-in path (`--allow-research-skip`) restores the legacy "batch all pending research, halt once" behavior — only safe when the operator has verified the remaining queue is independent.

### ANTI-EXEMPTION RULE — a dependency/sibling having RESEARCH.md is NOT a waiver (HARD)

**A `needs-research` terminal is NEVER exempted, down-graded, or "fast-pathed" because a dependency, sibling, or upstream feature already has its own `RESEARCH.md`.** The feature the state script halted on requires its OWN `RESEARCH.md`, full stop. Do NOT improvise framings like "research already exists in the Complete sibling, no Gemini run needed," "they ship as a unit so the upstream research covers this," or "the dependency is Complete so this is just a formality." None of those waive the halt. `lazy-state.py` emits `needs-research` precisely because THIS feature's `RESEARCH.md` is missing; only THIS feature's `RESEARCH.md` (or a `RESEARCH_SUMMARY.md` it produces) clears it. If the operator genuinely wants to proceed without per-feature research, that is an explicit operator decision (`--allow-research-skip` or a manual `RESEARCH.md` drop) — never an orchestrator inference.

> **Burned on `d8-effect-chains`, 2026-06-14.** `d8-effect-chains` "ships as a unit" with `d8-track-infrastructure` (Complete, has its own `RESEARCH.md`). The orchestrator used that to invent a "fast path — research already exists in the Complete sibling" exemption and effectively down-graded the halt instead of surfacing the research prompt. A dependency having research is NOT a research waiver. The correct response was (and is): surface THIS feature's research prompt (resolving the pointer — see below) and HALT for `d8-effect-chains`'s own `RESEARCH.md`.

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

HARD CONSTRAINT 5 scopes the orchestrator's `AskUserQuestion` to the resolution modes (Steps 1g / 1h / 1i) plus the four enumerated exceptions (i)–(iv) listed there (standing-directive echo-back, budget-and-queue guard, Step 0.45 `--adhoc` task-details prompt, Step 5 resume disambiguation) — that constraint does NOT bind subagents the orchestrator dispatches. A `/spec` cycle subagent at Step 4.5 is allowed and expected to call `AskUserQuestion` during Phase 1; that's the legitimate design-conversation channel.

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

1. **Read the prompt content, RESOLVING any pointer.** Open `{spec_path}/RESEARCH_PROMPT.md`. Then apply **pointer resolution** (HARD — see below) to obtain the *effective* prompt content that will be surfaced. Measure the character count of the EFFECTIVE (resolved) content, not the bare pointer. (If the file is somehow missing — the state script should never emit `needs-research` without it — print a defensive warning and fall through to the announcement with `<RESEARCH_PROMPT.md not found at expected path>` as the body.)

   **Pointer resolution (HARD — bounded, one level — LEGACY FALLBACK).** As of 2026-06-14, `/spec` Phase 2 writes every `RESEARCH_PROMPT.md` self-contained by construction (see `~/.claude/skills/spec/SKILL.md` Phase 2 — combined-unit features get the full combined prompt duplicated into each member, never a pointer stub), so a freshly generated prompt should NEVER need resolution. This block remains as **defense-in-depth for LEGACY pointer files that predate that fix** (e.g. the original `d8-effect-chains` stub). Some legacy `RESEARCH_PROMPT.md` files are POINTER docs, not the real prompt: a short file (typically <~600 chars / a handful of lines) whose body is mostly a reference/link to ANOTHER feature's `RESEARCH_PROMPT.md` (e.g. "Combined with `<other-feature>` research (they ship as a unit)" + a Markdown link like `[…](../<other-feature>/RESEARCH_PROMPT.md)`, often with a focus note such as "Sections 4 and 7 are most relevant"). A bare pointer is USELESS to paste into Gemini, so it MUST be resolved before surfacing:
   - **Detect.** Treat the file as a pointer when it contains a relative link to another feature directory's `RESEARCH_PROMPT.md` AND carries little prompt body of its own (a pointer phrase like "Combined with", "ships as a unit", "See:", "Combined deep research").
   - **Follow ONE level.** Read the referenced `RESEARCH_PROMPT.md` (resolve the relative path against `{spec_path}`). Do NOT chain further — if the referenced file is itself a pointer, surface it as-is with a note (`<referenced prompt is also a pointer — surfaced verbatim>`); do not recurse.
   - **Bound the surfaced content.** If the referenced prompt names specific focus sections (e.g. "Sections 4 and 7 are most relevant"), surface those named sections plus the prompt's `## Context` / identity preamble, and prepend the focus note verbatim so the operator knows what to emphasize. If it names no sections, surface the whole referenced file. (Either way the operator gets a pastable prompt, not a 3-line pointer.)
   - **Resolution NEVER skips the halt.** Pointer resolution changes only WHAT is surfaced — it never converts the halt into a "the sibling already has research, no run needed" exemption (that is exactly the d8-effect-chains defect-1 mistake). The halt still fires for THIS feature, which still needs its OWN `RESEARCH.md`. Honoring "combined-unit" features means surfacing the real combined prompt AND halting — not waiving.

2. **Print the halt announcement to chat — HARD, NON-SKIPPABLE (a sanctioned T6 rich zone — print in full).** This is the load-bearing step of the entire halt: the operator can only act on a prompt they can SEE. The turn MUST print the research prompt in a fenced ` ```text ` code block. A needs-research halt that writes the sentinel and prints the T7 report but NEVER prints the prompt code block is a CONTRACT VIOLATION (it strands the operator). **Read `~/.claude/skills/_components/lazy-batch-prompts/research-halt-announcement.md` now** and use **Variant A** (the single-feature `needs-research` halt path), binding {feature_name}, {feature_id}, {spec_path}, {RESEARCH_PROMPT content (the EFFECTIVE/resolved content from step 1, including any prepended focus note)}, {NNNN chars}, {within|over}, {max_cycles}. The announcement MUST include both the fenced prompt block AND the FASTEST-RESUME in-session-upload instructions (paste/attach in your next message → Step 5 ingests inline). **Code-block hygiene (HARD):** the fenced ` ```text ` block contains ONLY the prompt content — every operator instruction (where to paste, the FASTEST-RESUME steps, the char-count line) stays OUTSIDE the fence, and any meta-fluff (a leading "> Combined with … ship as a unit" blockquote, "Mode: deep-research" / "Model: gemini-2.5-pro" headers, "Send this to Gemini") is STRIPPED before the content goes in the fence — see the CODE-BLOCK HYGIENE good/bad example in `research-halt-announcement.md`. `{within | over}` is chosen by comparing the measured char count to 24,000 (Gemini's practical web-UI character cap; see `~/.claude/skills/spec/SKILL.md` Phase 2 for source notes). When over, append `(may need manual trimming before paste)` to that line — informational only, do NOT refuse to print.

3. **Run `--run-end`:**

   ```bash
   python3 ~/.claude/scripts/lazy-state.py --run-end
   ```

4. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {feature_name} awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

5. **Append to `cycle_log`:** `{forward_cycles + meta_cycles + 1, feature_name, "⏸ needs-research (strict halt)", "NEEDS_RESEARCH.md written; prompt printed inline ({NNNN} chars)"}`. DO NOT increment either counter — the halt is not a real cycle.

6. **Print the final batch report (Step 2)** with `terminal_reason = "needs-research"` and STOP. Do NOT call the state script again. Do NOT touch `skip_needs_research` — it stays `false`. Do NOT add the feature to `research_pending` — it stays empty. The user's next `/lazy-batch` invocation re-enters via Step 0 → Step 0.5 → Step 1 and either ingests the uploaded research or hits this same halt again.

> **HARD ordering invariant for the default-path halt turn.** The turn must perform steps 2 (announcement WITH the fenced prompt block) AND 4 (PushNotification) — they are NOT optional. The valid terminal shape is: sentinel write → **fenced prompt code block + FASTEST-RESUME instructions (step 2)** → `--run-end` → **PushNotification (step 4)** → T7 report → STOP. A turn that ends with only the sentinel + the T7 table (skipping step 2's prompt block) is the d8-effect-chains defect-2 failure and is FORBIDDEN: the prompt block is what makes the halt actionable. If you find yourself about to STOP without having printed the prompt in a fenced code block, you have NOT completed the halt — go back and print it.

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

   Correlate each piece of content to a pending feature via the most recently halted invocation's pending list (the `Pending: <feature_ids>` line from Step 1f, or the single `feature_id` from Step 4). When the upload is unambiguously for one feature (only one was pending, or the user named the feature in the message), proceed directly. When multiple features were pending and the correlation is ambiguous, ask ONE `AskUserQuestion` clarifying "which feature does this research belong to?" before continuing — this is permitted use (iv) under HARD CONSTRAINT 5 (the Step 5 in-session-resume disambiguation), surfaced only at the resume boundary.

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

4. **Re-invoke `/lazy-batch` automatically.** After the subagent reports success, immediately invoke `/lazy-batch <N>` where `<N>` is the original `max_cycles` from the halted invocation (or the remaining budget if the user prefers — default to the original cap; the default is mechanics and is not announced, and the operator can adjust the budget at any time via a standing directive). The re-invocation re-enters via Step 0 → Step 0.5 (which is now a no-op because the .txt has been moved to `_consumed/` by `/ingest-research`) → Step 1, and the previously research-pending feature is now ready for `/spec` Phase 3.

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
- Commit policy: the orchestrator's direct commits are its sentinel and plan-frontmatter writes — Step 1c.5 pseudo-skill actions (`__mark_complete__`, `__write_deferred_non_cloud__`, `__write_validated_from_results__`, `__write_validated_from_skip__`, `__grant_skip_no_mcp_surface__`, `__flip_plan_complete_cloud_saturated__`, `__flip_plan_complete_stale__`), resolution-mode sentinel renames (BLOCKED.md → BLOCKED_RESOLVED_<date>.md, NEEDS_INPUT.md → NEEDS_INPUT_RESOLVED_<date>.md), gate-written NEEDS_INPUT.md (from the completion-integrity gate), and Gate-1 D7 routings (SPEC test-exempt notes per mcp-coverage-audit's completeness-policy outcome — Gate 1 no longer writes NEEDS_INPUT.md). NEEDS_RESEARCH.md is written inline (loop has already exited) and committed by the user's next `/lazy-batch` run or the first cycle subagent that picks it up. All cycle source/test commits are delegated to the cycle subagent (which follows the project's `.claude/skill-config/commit-policy.md` or standard pattern).
- **Hook machinery (Phase 5 — turn-routing-enforcement).** `--run-start` (Step 0.55) activates two hooks scoped to the run: the inject hook (`lazy-route-inject.sh`) pre-probes every turn and injects routing into the model's context; the validate-deny guard (`lazy-dispatch-guard.sh`) validates every `Agent` dispatch against the prompt registry. Both hooks are no-ops when no marker is present (interactive sessions untouched). `--run-end` (every terminal path, §1c.6) deletes the marker + registry. The hardening dispatch (`--emit-dispatch hardening`) is the self-repair signal for misroute/no-route/HOOK_ERROR — the guard recognizes its class tag and never blocks it; depth is hard-capped at 1. All non-cycle dispatch classes (`apply-resolution`, `input-audit`, `investigation`, `recovery`, `coherence-recovery`, `needs-runtime-redispatch`) are now emitted via `--emit-dispatch <class>` and dispatched VERBATIM — hand-composed dispatch prompts are no longer sanctioned for any class.
- **Cycle-containment machinery (lazy-cycle-containment — C1/C2/C3).** EVERY `Agent` dispatch (real cycle §1d + every meta-dispatch) is bracketed: `lazy-state.py --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]` IMMEDIATELY before, `lazy-state.py --cycle-end` IMMEDIATELY after on EVERY return path (success / halt / error). The begin writes the cycle-subagent marker (`~/.claude/state/lazy-cycle-active.json`, sibling of the run marker); while it is present the C2 PreToolUse hook (`lazy-cycle-containment.sh`) DENIES in-flight the ops a runaway subagent needs (next-route probe/emit, run-lifecycle, 2nd-feature commit, recursive `Agent`) and the C3 state-script refusals reject `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`--emit-dispatch` (exit 3, zero side effects). The orchestrator clears the marker before its own next ops, so the refusal bites ONLY a subagent calling them mid-dispatch — orchestrator flow is unaffected. The bracket is identical across the coupled trio (cloud passes `--cloud` to `lazy-state.py`; the bug orchestrator brackets with `bug-state.py`).

<!-- COUPLED-PAIR DIFF (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud) — Phase 5 turn-routing-enforcement
     lazy-batch (workstation, feature pipeline) vs lazy-bug-batch (workstation, bug pipeline):
       - State script: lazy-state.py (feature) vs bug-state.py (bug)
       - Spec root: docs/features/ vs docs/bugs/
       - Entity vocab: feature_id/feature_name vs bug_id/bug_name
       - Terminal success: all-features-complete vs all-bugs-fixed
       - Completion receipt: COMPLETED.md / __mark_complete__ vs FIXED.md / __mark_fixed__
       - Step 0.55 --run-start: --repo-root (feature) — same flag, same script; bug uses bug-state.py
     lazy-batch (workstation) vs lazy-batch-cloud (cloud):
       - Step 0.55 --run-start: lazy-batch passes no --cloud; lazy-batch-cloud passes --cloud
       - cloud adds Step 0.6 resume-reconciliation and HARD CONSTRAINT 10
       - cloud pseudo-skills include __write_deferred_non_cloud__; workstation never emits it
       - cloud Step 9 defers mcp-test (returns __write_deferred_non_cloud__); workstation boots runtime
     All three: structurally identical for Changes A–G (hook activation, run-end on terminals,
       LAZY-ROUTE banner consumption, denial recovery, emit-dispatch dispatch sites,
       post-compaction counter from marker, coupled-pair diff comment). -->

<!-- COUPLED-PAIR DIFF (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud) — Phase 7 turn-routing-enforcement
     Mirrored identically across all three SKILL.mds (cloud keeps its --cloud / unattended-default deltas):
       - WU-7.1: §1d.1 "Pending hardening debt" block — pending_hardening>0 ⇒ FIFO emit+dispatch before
         any forward route; --run-end refuses on unacked denials; --ack-unhardened is operator-only.
       - WU-7.2: §1d.1 Depth-cap paragraph split into shape-(a) recipe denial (one verbatim re-dispatch,
         fresh nonce) vs shape-(b) halt-reason / second-recipe denial (existing 4-step halt). Never a 3rd.
       - WU-7.3c: §1d "Continuation cycles re-emit" gained the Freshness rule — never dispatch an emission
         from an earlier turn; re-emit fresh same-turn; --context slots are the only customization point.
       - WU-7.4: Budget-and-queue guard gained the unattended-checkpoint arm (reliability-triggered,
         --run-end --reason checkpoint --next-route + PushNotification + T7 trigger). Step 0.55 surfaces
         resumed_from_checkpoint on T1.
       - WU-7.5c: Step 1e gained step 3a — fire PushNotification("spun off {id} — {reason}") + D7 digest
         entry on any cycle return reporting a spin-off. (cloud mirrors at its Step 1e equivalent.)
       Bug-pipeline (lazy-bug-batch) keeps bug-state.py / bug_id|bug_name bindings; cloud keeps --cloud. -->
<!-- Phase 8 (turn-routing-enforcement, 2026-06-12) — coupled-pair mirror note:
       - WU-8.2/8.3: §1d.1 "Pending hardening debt" rewritten — probe WITHHOLDS the forward route
         (route_overridden_by + hardening_emit_command); ack moved to guard-allow time (emission
         no longer acks); full-probe-JSON consumption rule (field-extractor piping BANNED).
       Mirrored verbatim across lazy-batch / lazy-bug-batch / lazy-batch-cloud (cloud keeps
       lazy-state.py --cloud paths). Script contract: lazy_core.py read_run_marker path B is now
       non-destructive (concurrent interactive sessions never delete a live run's marker). -->
<!-- lazy-cycle-containment Phase 5 (2026-06-15) — coupled-trio mirror note:
       - C1 dispatch bracket: §1d "Cycle-marker dispatch bracket" — `--cycle-begin` IMMEDIATELY
         before every Agent dispatch (real + every meta-dispatch), `--cycle-end` IMMEDIATELY after
         on EVERY return path (success/halt/error). Idempotent end; self-healing begin.
       - Hook-machinery Note: added the C1/C2/C3 cycle-containment bullet to the Notes section.
       - C8 governing-file reload discipline + auto-refresh boundary + new-hook-registration
         restart surfacing (§1d): authored canonically in lazy-batch (Phase 1); MIRRORED here into
         lazy-bug-batch + lazy-batch-cloud in this same Phase-5 coupled-trio cycle.
       Mirrored across all three: bug orchestrator brackets with bug-state.py (--bug-id maps to the
       marker's feature_id); cloud passes --cloud to lazy-state.py. The bracket itself is NOT a
       cloud divergence (identical shape). -->

