---
name: lazy-batch-cloud
description: Cloud-environment variant of /lazy-batch — loops on lazy-state.py --cloud, spawns one Opus subagent per cycle, and defers any step requiring the Tauri desktop or MCP HTTP server (Step 9 MCP test writes DEFERRED_NON_CLOUD.md). The Step 8 retro step is unwired (operator decision 2026-06) — once phases are complete the pipeline routes directly to the MCP gate. Drives the /spec → /plan-feature → /execute-plan → (defer MCP) pipeline via lazy-state.py --cloud, with cloud-queue-exhausted as the normal terminal when all remaining features await workstation MCP validation. A halt for any reason other than max-cycles presents an AskUserQuestion resolution path and resumes — only max-cycles, all-features-complete, cloud/device-queue-exhausted, and missing-queue remain clean stops.
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip] [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue] [--park]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch Cloud — Autonomous Pipeline Orchestrator (Cloud Mode)

Cloud variant of `/lazy-batch`. Identical orchestration shape: loop on the state script, spawn one Opus subagent per cycle, halt on the same terminal conditions — but the state script runs in `--cloud` mode, so:

- Step 2 skips cloud-saturated features (DEFERRED_NON_CLOUD.md + no VALIDATED.md, on a feature past implementation).
- **Step 8 (retro) is UNWIRED** (operator decision, 2026-06) — once all phases are complete the pipeline routes directly to the Step 9 MCP gate; `lazy-state.py --cloud` never emits `retro-feature`. The `/retro-feature` skill remains in the catalog (restore path).
- Step 9 returns `__write_deferred_non_cloud__` instead of dispatching `/mcp-test`. The orchestrator writes the deferral sentinel inline (Step 1c.5 pseudo-skill handling) — the next cycle either advances to a ready feature or halts on `cloud-queue-exhausted`.
- Step 10 (mark complete) is unreachable from cloud unless a workstation has already produced VALIDATED.md. `cloud-queue-exhausted` is the normal terminal state when every remaining feature is awaiting workstation MCP testing.

**Per-cycle dispatch order:** `/spec` → `/plan-feature` (Step 6, = `/spec-phases` + `/write-plan` in one cycle) → `/execute-plan` → `/mcp-test` (Step 9, cloud defers) → mark-complete (Step 10, cloud halts). (Retro unwired — no Step 8 between execute-plan and the MCP gate.)

This skill is coupled to `/lazy-batch` per CLAUDE.md — their only intended divergences are documented in the "Differences from /lazy-batch" block below.

> **Parity note:** before editing this skill, run `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-batch-cloud` to confirm parity with its canonical twin is clean, and run `pytest user/scripts/test_lazy_parity.py` after to confirm your change introduces no drift. Intentional divergences are recorded in `user/scripts/lazy-parity-manifest.json` (the source of truth).

---

## HARD CONSTRAINTS (non-negotiable)

Constraints 1-9 mirror `/lazy-batch`'s HARD CONSTRAINTS 1-9; constraint 10 is cloud-only:

1. The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `COMPLETED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` / `PHASES.md` status lines when performing the `__mark_complete__` action. `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns — or by the Step 1g D7 scope resolution (`resolved_by: completeness-policy`, no question); the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. **`BLOCKED.md` may likewise be appended to** (not overwritten) with a `## Resolution` section by Step 1h (blocked-resolution mode) after `AskUserQuestion` returns — or by the Step 1h D7 sequencing-only auto-resolution (no question); the orchestrator then dispatches an Opus subagent to enact the chosen resolution path (e.g. `/add-phase`, queue reorder) and neutralize the sentinel by **rename** (lazy-state.py keys the halt on the `BLOCKED.md` filename). All other `Write`/`Edit` operations require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool. Every sub-skill goes through a spawned `Agent` subagent. Pseudo-skills (`__*__`) are not real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files. State inference is exclusively via `lazy-state.py --cloud`. Sentinel files MAY be read by the orchestrator to confirm a write or drive a pseudo-skill action.
4. One cycle = one subagent dispatch FOR REAL WORK SKILLS. Pseudo-skill cycles (sentinel writes) are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to the resolution modes — decision-resume (Step 1g), blocked-resolution (Step 1h), and operator-directed halt-resolution (Step 1i) — ONLY for the orchestrator itself.** The guiding rule: a halt for ANY reason other than `max-cycles` (and the genuine all-done success / environment-exhaustion / no-queue stops listed in Step 1i) presents the operator an `AskUserQuestion` resolution path and continues the loop, rather than dead-ending — except that scope-class decisions and sequencing-only blockers are auto-resolved per `~/.claude/skills/_components/completeness-policy.md` (D7), not asked: the standing policy reduces questions, never adds them, and the resolution modes ask only for what remains product-class. Outside Step 1g / 1h / 1i (the §1g-flush batched `AskUserQuestion` is part of the Step 1g resolution scope), the orchestrator MUST NOT call `AskUserQuestion` — with four additional permitted uses (mirrored from `/lazy-batch` HARD CONSTRAINT 5): (i) the one-time echo-back confirmation when a mid-run operator message implies a budget change, standing resolution mode, or early stop (the Step 0 standing-directive protocol); (ii) the budget-and-queue guard question when the run would otherwise end with budget and queue both remaining; (iii) the Step 0.45 `--enqueue-adhoc` task-details prompt when `--adhoc` is supplied with no text and the task cannot be unambiguously inferred from the conversation; and (iv) the Step 5 in-session resume multi-feature disambiguation question when research arrives for an ambiguous feature ("which feature does this research belong to?"). Uses (i) and (ii) are orchestrator-level confirmations of operator intent; uses (iii) and (iv) are bounded single-question disambiguation prompts at well-defined pre-loop and resume boundaries. None are resolution-mode decisions about feature content. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. Inside Step 1h, the orchestrator MUST `AskUserQuestion` for the resolution path against a `BLOCKED.md` (re-printing its body first), record the choice, dispatch the apply-resolution subagent to enact it, and **continue the loop** — `blocked` no longer halts the orchestrator either (except the operator-chosen "Halt for manual fix" path). The user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation. **This constraint scopes the orchestrator, not subagents it dispatches.** A `/spec` subagent dispatched at state-machine Step 4.5 (stub-spec detected — see "Stub specs vs structured-research-pending specs" near Step 4) is allowed and expected to call `AskUserQuestion` during Phase 1 brainstorming; the orchestrator dispatches that cycle exactly the same way it dispatches any other real-skill cycle (one `Agent` call). Whatever the dispatched skill does internally is its own contract.
6. **The orchestrator MUST print a Zero-Context Operator Briefing AND re-print the load-bearing context to chat BEFORE calling `AskUserQuestion`.** The operator may have been away for hours and retains NO session context (and may be reading on mobile, where `AskUserQuestion` truncates). In **Step 1g** the briefing (step 2a of the decision-resume component) catches them up from zero — what's being worked, why we halted, every option with pros/cons and fit against the original requirements, and a recommendation — followed by the verbatim `## Decision Context` re-print (step 2b); the `AskUserQuestion` option set MUST exactly match the options in the briefing (same labels, 1:1 — no UI-only options). Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` (one missing the `## Decision Context` H2 with H3 subsections matching `decisions:` 1:1); surface the malformation as a quality issue and halt instead (see Step 1g.1). In **Step 1h** this is the `BLOCKED.md` body verbatim (no mandated rich-body schema — a thin body is NOT a malformation halt); in **Step 1i** it is the obstacle context the shared `_components/halt-resolution.md` mandates. The same zero-context briefing discipline applies to Step 1h/1i.
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch-cloud` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **TWO session-global monotonic counters replace the single `cycle` counter.** Identical model to `/lazy-batch` HARD CONSTRAINT 8 — both initialized once in Step 0 and NEITHER reset on feature transitions.
   - **`forward_cycles`** — counts pipeline-advancing work. Ceiling: `max_cycles`. Incremented by: real-skill dispatch cycles (Step 1e) and pipeline-advancing pseudo-skills at Step 1c.5 (`__mark_complete__`, `__write_deferred_non_cloud__`, `__write_validated_from_results__`, `__write_validated_from_skip__`, `__flip_plan_complete_cloud_saturated__`). **Capped at Step 1c** (`if forward_cycles >= max_cycles` → the existing max-cycles halt).
   - **`meta_cycles`** — counts resolution/recovery/cleanup work. **NO ceiling — uncapped by design (operator decision 2026-06-14).** Incremented by: Step 1g (decision-resume), Step 1h (blocked-resolution), Step 1i (operator-directed halt-resolution), LOOP-DETECTED / recovery dispatches, and the stale-plan flip pseudo-skill `__flip_plan_complete_stale__`. The meta loop is NOT bounded by a meta cap; the run's only hard stop is the `forward_cycles >= max_cycles` cap at Step 1c. `meta_cycles` is still tracked and displayed (as a bare count), but there is NO `if meta_cycles >= …` halt — Step 1g/1h/1i have no meta-cap check.
   - **Input-audit (Step 1d.5):** audits share the cycle's slot in `cycle_log` and do NOT increment either counter.
   - **Running total for cycle_log index:** use `forward_cycles + meta_cycles` as the monotonic N.
   - A feature transition is NOT a fresh batch; the orchestrator runs ONE log across every feature it touches.

9. **Dispatch ONLY against the feature `lazy-state.py --cloud` returned THIS cycle; never fabricate a feature.** Identical to `/lazy-batch` HARD CONSTRAINT 9: dispatch against exactly the `feature_id` + `spec_path` from the current cycle's state-script output, verbatim. NEVER invent/infer/hand-edit a slug the script didn't emit. The state script already skips queue entries whose `spec_dir` doesn't resolve on disk (`dangling queue entry` diagnostic), so a real feature always has an on-disk `spec_path`. The cycle subagent prompt MUST forbid CREATING a feature's `SPEC.md`/`RESEARCH.md`/`queue.json`/`ROADMAP.md` from a bare slug (only `--enqueue-adhoc` and a `/spec` dispatch against an already-seeded dir may create dirs). A `feature_id` with no on-disk `spec_path` is a bug to surface, never a cue to manufacture the feature.

10. **(CLOUD-ONLY, not in `/lazy-batch`) NEVER passively wait on a background-cycle completion notification across a container-reclaim boundary.** After ANY `SessionStart:resume` in cloud, the orchestrator MUST treat any in-flight background cycle agent as **unknown — reconcile from git + `lazy-state.py --cloud`** (Step 0.6), NEVER as "still running, awaiting its completion notification." A background-agent completion notification will NOT arrive across a container-reclaim boundary: the agent and the container it ran in are gone, so the signal can never fire. The orchestrator MUST re-probe and drive forward from the reconciled on-disk + remote state — it must never block waiting for that dead signal. **This is the OPPOSITE of HARD CONSTRAINT 7's rule, not a violation of it:** HARD CONSTRAINT 7 forbids *actively* polling/sleeping while research is in flight; HARD CONSTRAINT 10 forbids *passively* blocking on a notification that can never come. Both push the orchestrator to the same behavior — never block; reconcile and act on a single-turn signal.

11. **HARD CONSTRAINT — stop-authorization (cloud mirror of `/lazy-batch` HARD CONSTRAINT 10, adapted for unattended runs).** The orchestrator MUST NOT end a cloud run except on `max-cycles` or a genuine script-emitted terminal. The ONLY legitimate no-`AskUserQuestion` stops are: (a) `forward_cycles >= max_cycles`, and (b) a `terminal_reason` in {`all-features-complete`, `max-cycles`, `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-missing`, `blocked-halt-for-manual`, `needs-research`, `queue-blocked-on-research`} returned by `lazy-state.py --cloud` in the CURRENT cycle's probe. Cloud/scheduled runs are unattended by construction (the run marker carries `attended: false` when `--run-start --unattended` is passed — Step 0.55), so the budget-and-queue guard's `AskUserQuestion` path is unreachable live; an early stop is sanctioned ONLY as a CHECKPOINT (see unattended-checkpoint arm, Step 0.55), and only when a reliability trigger holds (≥2 guard denials or an operator pause message). When ending on a genuine terminal, pass `--run-end --reason terminal --terminal-reason <reason>` (sanctioned set above, or `--operator-authorized` required); omitting `--terminal-reason` is back-compat but deprecated. (Phase 7 / lazy-validation-readiness. Incident reference: 2026-06-14.)

**Cloud-specific:** the cycle subagent operates under the same cloud-environment limitations documented in `/lazy-cloud` — no Tauri runtime, no MCP HTTP server, no audio device, no Windows-only tooling. **Additionally, the cloud cycle subagent does NOT have the `Agent` tool — recursive sub-subagent dispatch is not supported from inside a cloud subagent.** This forces a load-bearing override of any dispatched skill's sub-subagent contract: skills that nominally dispatch sub-subagents (e.g. `/execute-plan` → Sonnet test-agent + impl-agent fanout, `/retro` → research subagents A–G) are performed INLINE inside the cycle subagent itself using `Edit`/`Write`/`Read` directly. The cycle subagent's prompt (Step 1d below) makes both limitations explicit and enumerates the per-skill inline overrides. **This override applies only at the cycle-subagent level** — the orchestrator still dispatches exactly one `Agent` per cycle, identical to `/lazy-batch`. The override never expands the orchestrator's `Write`/`Edit` scope (HARD CONSTRAINT 1 still holds — the orchestrator edits only sentinels).

> **Known cloud limitation — TDD agent-separation is traded away.** On workstation, `/execute-plan` enforces test-first discipline *structurally*: a dedicated Sonnet test-agent writes failing tests, then a separate impl-agent makes them pass (the separation `R-EP-2`/`R-EP-3` exist to enforce). The cloud override collapses this into ONE inline cycle subagent that writes both tests and implementation, so that structural test-first guarantee is GONE in cloud — it cannot be enforced from sub-subagent dispatch evidence. This is an intentional tradeoff, not a defect. The compensating controls are: (1) per-batch **quality gates** (`R-EP-6`) still run and must pass 100%; (2) the workstation **`/retro`** pass audits the landed work; (3) the deferred **MCP-validation** pass on workstation (which writes `VALIDATED.md`) gates final completion. The inline cycle subagent SHOULD still write **tests-before-impl within each batch** — read the test expectations, write the failing tests, then implement — even though the ordering can't be structurally verified. `/lazy-batch-retro` knows this: its Step 4b cloud branch grades `R-EP-2`/`R-EP-3` as `n/a (cloud-override)` rather than `fail`.

**Meta-dispatch by-reference — PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites (mirrors `/lazy-batch` Phase 7 / lazy-validation-readiness).** Every `lazy-state.py --cloud --emit-dispatch <class>` call emits BOTH `dispatch_prompt` (verbatim text) AND `dispatch_prompt_ref` (`@@lazy-ref nonce=<hex>`). When dispatching any meta-dispatch prompt (hardening, recovery, apply-resolution, coherence-recovery, input-audit, investigation, needs-runtime-redispatch, etc.), PREFER `dispatch_prompt_ref` over the verbatim `dispatch_prompt`. The PreToolUse guard resolves the token to the registered bytes, eliminating byte-exact hand-transcription as a failure surface. Fall back to `dispatch_prompt` verbatim ONLY when `dispatch_prompt_ref` is absent or null in the emit output. This applies uniformly at every meta-dispatch site in this skill. See `/lazy-batch`'s "Meta-dispatch by-reference" paragraph (§1d) for the full rationale.

## OUTPUT CONTRACT — orchestrator voice (read at run start)

**ALL orchestrator chat output MUST follow `~/.claude/skills/_components/orchestrator-voice.md`** — the turn-template contract (T1 run banner, T2 dispatch / T3 return / T4 inline-gate cycle blocks, T5 park line, T6 rich zones, T7 final report; mechanics silent; rules cited only on deviation; probe JSON never restated in prose). **ZERO-TEXT RULE:** Claude Code's general "say what you're about to do before tool calls / give brief updates" guidance is OVERRIDDEN for this run — the UI already prints every tool call; between tool calls emit NOTHING unless it is byte-shaped as a template (sanctioned output starts with `## `, `### Cycle `, a template field line, `⏸`/`⚖`/`⚠`, or a T6/T7 body — anything else, don't type it). The entire run-start sequence (preflight, contract/policy reads, Step 0.4 sync, queue read) is SILENT, executed back-to-back; the FIRST text this invocation emits is the T1 banner (preflight failure / sync divergence are the T6 exceptions). **Read it at run start, and RE-READ it after any compaction boundary** (alongside `lazy-dispatch-template.md` — Step 1d's compaction discipline); the contract survives summarization by re-read, not by memory. Where an older passage in this skill prescribes a different chat-output shape (e.g. the retired `▶ … (dispatched)` background-dispatch line), the contract's Precedence clause wins; the verbatim re-print / Zero-Context Operator Briefing requirements (HARD CONSTRAINT 6, `decision-resume.md`, `blocked-resolution.md`, `parked-flush.md`, `halt-resolution.md`) are sanctioned T6 rich zones and are never overridden. Graded by `/lazy-batch-retro`'s R-V-* rules.

**STANDING POLICY — completeness-first (D7).** Read `~/.claude/skills/_components/completeness-policy.md` at run start, and RE-READ it after any compaction boundary (it is on the Step 1d compaction re-read list). It is pre-authorized: decisions whose options differ only in effort / sizing / sequencing / completeness (`class: scope`) are auto-resolved to the MOST COMPLETE option in BOTH modes — logged (`⚖ policy:` line, `resolved_by: completeness-policy`, run-end D7 digest in the T7 report), never asked. It governs the cycle and input-audit subagent prompts, Step 1g (scope-class sentinel resolution runs first), Step 1h (sequencing-only blockers auto-resolve; spin-offs pre-authorized, notify + log), and the `__mark_complete__` coverage-audit outcome at Step 1c.5 (author coverage / test-exempt, never ask — the scenario RUN defers to workstation per the normal cloud MCP deferral). D7 only REMOVES questions — product-class decisions still ask exactly as before. Graded by `/lazy-batch-retro`'s R-D7-* rules.

---

## Step 0.0: Environment Preflight (FIRST — before the start banner and before remote sync)

**Read and follow `~/.claude/skills/_components/lazy-preflight.md` as the very first action of this
invocation — before the start banner, before Step 0.4 remote sync, before the first state probe.**
Run its read-only check block (skills symlink resolves, `~/.claude/scripts/lazy-state.py` exists,
`python3` runs, node resolvable — prepending `/c/nvm4w/nodejs` if needed). If any check fails, print the
component's setup recipe and **STOP — zero cycles consumed** (do not print the banner, do not call the
state script, do not enter the loop). On success, node is on PATH for the whole session (no per-call
`export PATH`), and you continue to the banner / Step 0.4 as normal.

---

## Step 0: Parse Arguments

Same shape as `/lazy-batch` Step 0. `$ARGUMENTS` is tokenized:
- positive integer → `max_cycles` (default `10`)
- `--allow-research-skip` (optional) → `allow_research_skip = true` (default `false`)
- `--adhoc` (optional) → sets `adhoc_task` to the remainder of `$ARGUMENTS` after the token (empty → infer from conversation). Triggers **Step 0.45 (Ad-hoc Enqueue)** before the loop. Off by default. Place `<N>` / `--allow-research-skip` BEFORE `--adhoc` since it consumes the rest of the string.
- `--park` (optional) → sets `park_mode = true` (default `false`). Enables "park-and-continue" mode. **This flag is opt-in and off by default. Without it, the orchestrator's behavior is byte-for-byte the existing one** — a `NEEDS_INPUT.md` halts the loop into the existing Step 1g resolution-and-wait. The `--park` flag may appear in any position relative to the cycle-count arg (e.g. `/lazy-batch-cloud --park 30` and `/lazy-batch-cloud 30 --park` are equivalent). The full park/flush/auto-accept semantics are defined in Steps 1g, 1h, and 1i of this skill — this token purely enables the mode.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 0 for the full flag semantics and rationale. The cloud variant inherits the same default-strict / opt-in-batched dichotomy — research-pending features halt the loop immediately by default; pass `--allow-research-skip` only when the remaining queue is known to be independent.

Print the start banner — **T1 per `~/.claude/skills/_components/orchestrator-voice.md`** (≤4 lines; nothing else before the first cycle block):

```
## /lazy-batch-cloud — run start
mode   cloud (no Tauri/MCP) · park {on|off} · research {strict|batched}
budget fwd {max_cycles} · meta no cap
queue  {N} feature(s) · first: {first queue entry id}
```

The `queue` line is best-effort (one `Bash` read of `docs/features/queue.json` for the entry count — a banner fact, not state inference); omit the line if the queue file can't be read cheaply. The repo root and flag parsing are mechanics — not announced.

---

## Step 0.4: Resume-time remote sync (HARD REQUIREMENT — cloud reclaim recovery)

**Runs once, immediately after Step 0 (arg parsing) and BEFORE Step 0.5 / the Step 1a first state probe.** This is a single-turn git reconciliation, NOT polling — it does not violate HARD CONSTRAINT 7 (no active waiting). It does NOT touch the orchestrator's `Write`/`Edit` sentinel-only scope (HARD CONSTRAINT 1) — these are `Bash` git operations, not file edits.

**Rationale (cloud-acute):** a `/lazy-batch-cloud` session that resumes in a *fresh* container can check out a STALE local snapshot of the work branch — well behind the true remote tip — because the prior container (and its local commits beyond the last push) was reclaimed. The pushed history is safe on `origin`, but if the orchestrator runs `lazy-state.py --cloud` against the stale local tree it will infer state from out-of-date local files (plans, sentinels, SPEC) and either re-do or corrupt already-pushed work. The orchestrator MUST reconcile local to the remote tip BEFORE any local-state inference.

**Algorithm:**

1. Determine the work branch:

   ```bash
   branch=$(git rev-parse --abbrev-ref HEAD)
   ```

2. Fetch the remote tip (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error — this bounded retry is a single git op, not an active wait):

   ```bash
   git fetch origin "$branch"
   ```

   If the branch does not exist on `origin` yet (brand-new work branch never pushed — `fetch` reports no such ref), there is nothing to reconcile: skip the rest of Step 0.4 and continue to Step 0.5.

3. Fast-forward local to the remote tip:

   ```bash
   git merge --ff-only "origin/$branch"
   ```

4. **If the fast-forward FAILS because local has DIVERGED from `origin`** (non-fast-forwardable — local commits exist that `origin` does not have, which should never happen on a solo work branch), **do NOT clobber.** Do NOT `git reset --hard`, do NOT force anything. Surface the divergence to chat and halt for human resolution:

   ```
   🛑 /lazy-batch-cloud — work branch diverged from origin

   Local `{branch}` has commits that origin/{branch} does not, and origin has
   commits local does not (non-fast-forwardable). This should not happen on a
   solo work branch and may indicate concurrent edits from another container
   or a force-push. Refusing to auto-reconcile to avoid losing work.

   Resolve manually (inspect `git log --oneline --graph {branch} origin/{branch}`),
   then re-invoke /lazy-batch-cloud.
   ```

   PushNotification with the same one-line summary, then STOP. Do NOT run `lazy-state.py`.

5. On a clean fast-forward (or when local was already up to date / the branch was unpushed), continue to Step 0.5 **silently** — a successful sync is mechanics per the orchestrator-voice contract (silence means the machinery worked). Only the step-4 divergence halt is announced (a T6 error — recipe printed in full).

---

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

**Runs once, after Step 0.4 (remote sync) and BEFORE Step 0.5 / the first state probe.** Skipped entirely when the `--adhoc` flag was absent. It runs AFTER the remote ff-sync deliberately: enqueuing mutates `queue.json` in the working tree, so it must happen on the reconciled remote tip — acute in cloud, where the local snapshot may be stale after container reclaim.

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

**Cloud durability note (divergence from `/lazy-batch`):** the bootstrap files are tracked, but to survive container reclaim before the first cycle commits, push the work branch immediately after the enqueue — `git push origin $(git rev-parse --abbrev-ref HEAD)` (4× exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This folds into guardrail B's per-batch push discipline. The `queue.json` mutation was made by the `Bash` script (not `Write`/`Edit`), and a `git push` of committed work is not a `Write`/`Edit`, so HARD CONSTRAINT 1 still holds. (If the bootstrap files are not yet committed, stage and commit them via `Bash` git with message `chore({feature_id}): enqueue ad-hoc task at top of queue`, then push.) Continue to Step 0.5.

---

## Step 0.5: Pre-loop staged-research ingest check

**Identical to `/lazy-batch` Step 0.5** — before entering the main loop, probe for staged `.txt` files in `docs/gemini-sprint/results/` and dispatch `/ingest-research` as cycle 1 if any exist. This is the "resume after halt" entry point that lets the user upload research between sessions without any active waiting.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 0.5 for the full algorithm. Cloud-specific nuance: none — `/ingest-research`'s hard constraints already scope it to `docs/`-only writes (no Tauri / no MCP runtime required), so it runs identically in cloud and workstation.

---

## Step 0.6: Resume-reconciliation (HARD REQUIREMENT — cloud reclaim recovery)

**Runs once, after Step 0.5 and BEFORE the Step 1 main loop dispatches any real-work cycle. MANDATORY at the start of every `/lazy-batch-cloud` invocation AND treated as mandatory after any `SessionStart:resume`.** Like Step 0.4 this is single-turn git + state reconciliation, NOT polling (HARD CONSTRAINT 7 holds). It uses `Bash` git ops + the read-only state probe; the orchestrator itself performs no source `Write`/`Edit` (HARD CONSTRAINT 1 holds — the only file edits it may trigger are sentinel/SPEC/plan writes performed by a dispatched finalize subagent or by the inline pseudo-skill path, never by the orchestrator outside its sentinel scope).

**Rationale.** A cloud cycle (especially a 20-45 min `/execute-plan`) can be killed by a container reclaim mid-run. Per HARD CONSTRAINT 10 the orchestrator must NOT assume that killed cycle is "still running" and wait on its completion notification — that notification can never arrive. Instead it must reconcile the true state from git + `lazy-state.py --cloud` and drive forward. A killed cycle leaves up to three residues that MUST be handled before re-entering the loop, or the loop will redo finished work, hang, or discard correct partial work:

**Algorithm:**

1. **Push any unpushed local commits.** A same-container `SessionStart:resume` (not a fresh-container reclaim) can leave local commits that never pushed — the killed cycle committed but died before its per-WU push (Step 1d Commit + PUSH policy) or before the Step 1e backstop. Push them now so the remote is the source of truth for steps 2-4:

   ```bash
   git push origin "$(git rev-parse --abbrev-ref HEAD)"
   ```

   Retry up to 4× with exponential backoff (2s/4s/8s/16s) on network error; WORK BRANCH only, never main, never force. "Up to date" is fine. (After a true fresh-container reclaim there are no local-only commits — those died with the prior container; this step is then a no-op, and the durable state is whatever the per-WU pushes already landed on `origin`.)

2. **Probe state.** Run `python3 ~/.claude/scripts/lazy-state.py --cloud` (no `--skip-needs-research` — this is a reconciliation probe, identical invocation to Step 1a's default path). Parse the JSON. This is read-only.

3. **Detect + handle the "finished-but-not-finalized" case.** A killed cycle commonly leaves a plan part whose WUs/phases are already DONE on the remote (per-WU pushes landed) but whose finalization never ran — the plan frontmatter is still `Ready`/`In-progress`, PHASES.md per-phase status is unticked, or deliverable checkboxes are unticked. Detect it by cross-checking, for the current feature's active plan part:
   - `git log --oneline` shows the part's WU/batch commits are present, AND
   - the plan file's `- [ ]` checkboxes are all (or nearly all) `- [x]`, AND
   - the plan frontmatter `status:` is still `Ready` or `In-progress` (not `Complete`), OR PHASES.md's per-phase status / deliverable checkboxes for that phase are not yet ticked.

   When this holds, do NOT dispatch a full re-execution of the part. Dispatch a SHORT finalize cycle instead (one subagent — Sonnet is sufficient, the work is mechanical) with a bounded job:
     - verify the part's quality gates are green (run them; if RED, this is NOT finished-but-not-finalized — fall through to normal Step 1 loop execution to fix the failures);
     - flip the plan part frontmatter `status:` → `Complete`, **subject to the No-premature-Complete guard** — if `DEFERRED_NON_CLOUD.md` exists and `VALIDATED.md` does not, leave it `In-progress` and let the cloud-saturated `__flip_plan_complete_cloud_saturated__` flow carry it;
     - set PHASES.md per-phase status + tick that phase's deliverable checkboxes;
     - commit AND push each change (per the Step 1d Commit + PUSH policy).
   Record it as one cycle (append to `cycle_log`, update `prev_cycle_signature`, increment `meta_cycles` — Step 0.6 finalize is reconciliation/recovery, not forward implementation), then return to the Step 1 loop. This converts a "redo the whole part" into a few-second finalize.

4. **Reconcile a dirty working tree.** If `git status --porcelain` is non-empty, a killed agent left uncommitted partial work. Do NOT blindly `git checkout` / `git reset` it away — discarding work as a shortcut is forbidden. Read the diff (`git diff` + `git status`) and decide: if the partial work is correct-but-uncommitted, KEEP it and finish it (dispatch a bounded continue/finalize subagent, since source edits require a subagent per HARD CONSTRAINT 1 — the orchestrator must not edit source files itself); if a hunk is genuinely corrupt/half-applied, surface that diff to chat first and revert ONLY the broken hunk, never the whole tree. When in doubt, dispatch the bounded subagent to read the diff and either complete the in-flight WU or cleanly revert just the broken portion.

After steps 1-4: if anything was actually reconciled (unpushed commits pushed, a part finalized, a dirty tree handled), surface it as a one-line T6 recovery note — `🔧 Resume-reconciliation: pushed {N} commit(s); finalized plan part {X}; reconciled dirty tree.` (recoveries are a sanctioned rich zone per orchestrator-voice.md) — then enter the Step 1 loop. When steps 1-4 find nothing to reconcile (clean tree, nothing unpushed, no finished-but-not-finalized part), Step 0.6 is a **silent** fast no-op — mechanics are not announced. This is the normal fresh-start case.

---

## Step 0.55: Write Run Marker

**Runs once, immediately after Step 0.6 and BEFORE the Step 1 cycle loop.** This writes the run marker that activates the inject hook and validate-deny guard for the session. It is script-owned — the orchestrator does not manage the marker file directly; `--run-start` creates it and `--run-end` deletes it.

```bash
# C3 self-immunity signal (cycle-subagent-runs-orchestrator-work, Phase 1): the
# orchestrator asserts its identity by EXPORTING LAZY_ORCHESTRATOR=1 into the
# session env it runs every lazy-state.py lifecycle/routing call from. This is
# the positive, marker-independent carrier `refuse_if_cycle_active` /
# `refuse_cycle_marker_mutation_if_subagent` key on (lazy_core.py priority 1) —
# it makes the orchestrator STRUCTURALLY IMMUNE to a stale/live cycle marker (its
# own --cycle-end clears the marker while the marker is still present), and the
# ABSENCE of the var is what marks a cycle subagent (a subagent's Bash subprocess
# never inherits this export). Carry it on EVERY lifecycle/routing call below
# (--run-start/--run-end/--cycle-begin/--cycle-end/--apply-pseudo/--enqueue-adhoc/
# --emit-dispatch); export once for the session so it persists.
export LAZY_ORCHESTRATOR=1

python3 ~/.claude/scripts/lazy-state.py \
  --cloud --run-start --unattended --max-cycles {max_cycles} \
  --repo-root {cwd}
```

**Attendedness — cloud runs are unattended by construction.** The `--unattended` flag records `attended: false` in the run marker. This governs `--run-end --reason checkpoint` behavior: on an unattended marker, `--run-end --reason checkpoint` is ALLOWED (the unattended-checkpoint arm, sanctioned early stop); on an attended marker it is REFUSED without `--operator-authorized`. Cloud/scheduled drivers always pass `--unattended`; interactive workstation invocations of `/lazy-batch` do NOT (see `/lazy-batch` Step 0.55 and HARD CONSTRAINT 11 above). Legacy markers lacking the `attended` field are treated as attended — the stricter gate is the safe default, even if it means the cloud unattended-checkpoint arm won't fire on a legacy run.

The marker (`~/.claude/state/lazy-run-marker.json`) records `pipeline=feature`, `cloud=true`, `repo_root`, `session_id`, `started_at`, `max_cycles`, `attended=false`, and seeds the `nonce_seed` used by the prompt registry. While the marker exists:
- The **inject hook** (`lazy-route-inject.sh`) fires on every `UserPromptSubmit` turn and injects a `LAZY-ROUTE (hook-injected, turn N):` banner with the pre-run probe JSON + cycle route into the session context. When Step 1a sees this banner, it MUST use the injected route instead of re-probing (re-probing would advance counters twice).
- The **validate-deny guard** (`lazy-dispatch-guard.sh`) fires on every `Agent`/`Task` pre-tool call, hashes the prompt, and verifies it against the prompt registry. An unregistered prompt is DENIED with a corrective recipe; a registered prompt is ALLOWED.

Both hooks are inactive for interactive (non-lazy-batch) sessions — the marker is the on/off switch.

The marker is **script-owned**: `--run-end` is the only path that deletes it; the orchestrator MUST run `--run-end` on every terminal/halt path (§1c.6). Missed deletion is self-healing (24-hour staleness + session-id mismatch on the next run) but is a protocol violation the retro grades.

**Resume from a checkpoint.** If a prior run ended via the unattended-checkpoint arm (below), `--cloud --run-start` consumes `lazy-run-checkpoint.json` and echoes its content as `resumed_from_checkpoint` in the run-start output (then deletes the file — single-use). When present, surface it on the T1 banner as one extra line — `resume <next_route> (checkpoint <date>)` (orchestrator-voice.md T1).

**Unattended-checkpoint arm (sanctioned early stop — the cloud default is unattended).** Cloud runs are unattended by construction (no operator reply expected — HARD CONSTRAINT 10), so the budget-and-queue guard's `AskUserQuestion` path (HARD CONSTRAINT 5 (ii)) cannot be answered live; an early stop is sanctioned ONLY as a CHECKPOINT, and ONLY when a reliability trigger holds (**≥2 guard denials this run, OR an explicit operator pause message**). A checkpoint requires ALL THREE of: (1) `python3 ~/.claude/scripts/lazy-state.py --cloud --run-end --reason checkpoint --next-route "<the probed next route>"` (writes `lazy-run-checkpoint.json` so the next `--cloud --run-start` resumes); (2) a PushNotification carrying the next route + trigger reason; (3) the T7 final report naming the trigger. An early stop WITHOUT the checkpoint `--run-end` (or without a holding trigger) remains a contract violation.

**Checkpoint provenance — cloud checkpoints stay carry-forward (operator-checkpoint-resume-counter-reset, 2026-06-17).** The cloud `--run-end --reason checkpoint` command above deliberately does NOT pass `--operator-authorized`, for BOTH reliability triggers (≥2 guard denials AND an explicit operator pause message). Rationale: a cloud checkpoint is an *automatic mid-run pause of the same logical run*, resumed automatically on the next `--cloud --run-start` — NOT a fresh authorized budget. Carrying the counters forward is what keeps an auto-resume from silently exceeding the authorized `max_cycles` (HARD CONSTRAINT 8), exactly as the feature-pipeline reliability pause does (VERIFIED symptom #3 — reset is reserved for deliberate operator re-invocations, which in cloud is a *new* `/lazy-batch-cloud <N>` invocation with no checkpoint on disk, not a checkpoint resume). The Phase-1 mechanism (`write_run_checkpoint`'s `operator_authorized` param) already supports threading the flag here if a future cloud workflow wants a checkpoint-backed fresh-budget resume; that is a deliberate future change, not the current behavior. (⚖ scope-class: omitting the flag is the no-behavior-change default — the cloud command emitted no flag before this fix either.)

If `--run-start` fails (script exits non-zero or errors), surface a T6 `⚠` and STOP before printing the banner — a run with no marker is a run with no enforcement, which is still safe for the pipeline (it degrades to pre-Phase-5 behavior) but should not silently proceed without the operator knowing enforcement is off.

This step is **silent** on success — do not announce it in chat output (mechanics are not narrated per orchestrator-voice.md).

---

## Step 1: Cycle Loop

Initialize per-session state — identical shape to `/lazy-batch` Step 0. **This init is logically part of Step 0 (arg parse): it happens ONCE, before Steps 0.4 / 0.5 / 0.6 run, so any pre-loop cycle they record (Step 0.5's ingest dispatch, Step 0.6's finalize dispatch) increments the appropriate counter (`forward_cycles` for the 0.5 ingest cycle, `meta_cycles` for the 0.6 finalize cycle) / sets `prev_cycle_signature` forward from these values — the loop entry NEVER re-initializes them.**
- `forward_cycles = 0` — initialized once per `/lazy-batch-cloud` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py --cloud` returns a new `feature_id`). Counts pipeline-advancing work; ceiling is `max_cycles`.
- `meta_cycles = 0` — initialized once per `/lazy-batch-cloud` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset on feature transitions). Counts resolution/recovery/cleanup work; **uncapped — no ceiling, no cap enforcement** (operator decision 2026-06-14). Only `forward_cycles` is capped (at `max_cycles`).
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `research_pending = set()` — feature_ids that hit `needs-research` this session. Only used when `allow_research_skip == true`; empty under the default strict-halt path.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. Stays `false` under the default path.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched. **`sub_skill_args` is part of the tuple deliberately** (mirrored from `/lazy-batch`): a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3) returns the same `(feature_id, sub_skill, current_step)` on every part but a *different* `sub_skill_args` (the plan-part path) — real forward progress, not a loop. Omitting `sub_skill_args` made the loop-guard false-trigger on every multi-part plan.
- `adhoc_task = <parsed>` — the ad-hoc task text from `--adhoc` (empty string if the flag was present with no text; unset/`None` if absent). See Step 0.45.
- `park_mode = <parsed>` — `true` if `--park` was present, `false` otherwise. When `false`, all halt behavior is byte-for-byte the existing one.

> **Unified driver — merged-view dispatch (single driver, two state scripts; unified-pipeline-orchestrator Phase 2).**
> `/lazy-batch-cloud` is the cloud mirror of the unified `/lazy-batch` driver — it drives BOTH the feature
> and bug pipelines. Each cycle it probes the merged work-list head with
> `python3 ~/.claude/scripts/lazy-state.py --cloud --next-merged --repo-root {cwd}` (Phase-1 surface —
> read-only ORDERING ONLY; it never re-infers per-item state) to learn the next actionable item's
> `{item_id, type, repo_root}`, then **type-dispatches the rest of the cycle to the matching state
> script**:
>
> - **`type == "feature"`** → drive this cycle with `lazy-state.py --cloud` exactly as Steps 1a–1e
>   describe; the type-correct terminal action is `__mark_complete__` (writes `COMPLETED.md`; in cloud,
>   reachable only once a workstation produced `VALIDATED.md` — otherwise Step 9 defers via
>   `__write_deferred_non_cloud__`).
> - **`type == "bug"`** → drive this cycle with `bug-state.py --cloud` (same JSON contract, `docs/bugs/`,
>   `--bug-id` scoping); the type-correct terminal action is `__mark_fixed__` (writes `FIXED.md`).
>
> The merged view normalizes the two queues' divergent ordering fields (feature `tier` / bug `severity`)
> onto one effective-priority scale and breaks ties bug-before-feature — that ordering lives ENTIRELY in
> `lazy_core.merged_priority` (Phase 1), NOT in this prose: the driver only CONSUMES the merged head, it
> never re-implements ordering. Both state machines and all gates run UNCHANGED — this skill carries NO
> new state-machine logic; the merged probe is the only addition. **This is a coupled-pair mirror of
> `/lazy-batch`'s merged-view dispatch shape; `--cloud` (already carried on every state-script call) is
> the only delta — the merged-view branch itself is NOT a cloud divergence.**
>
> **No-regression (single-type runs are unchanged).** When only ONE queue is populated, the merged head
> is simply that queue's head, so the cycle sequence is byte-for-byte identical to the pre-unification
> per-type batch (a features-only queue runs exactly as `/lazy-batch-cloud` always did, terminal
> `__mark_complete__`; a bugs-only queue runs exactly as the standalone bug loop, terminal
> `__mark_fixed__`). Asserted by `lazy_parity_audit.py --merged-view` + a single-type fixture.
>
> Steps 1a–1e below are written against `lazy-state.py --cloud` (the feature path). For a `type == "bug"`
> cycle, substitute `bug-state.py --cloud` for `lazy-state.py --cloud` and `__mark_fixed__` for
> `__mark_complete__` throughout the cycle body; the dispatch SHAPE is otherwise identical. See the
> **Differences from `/lazy-batch`** table for the merged-view-dispatch row.

### 1a. Run lazy-state.py --cloud

**Check for inject-hook banner FIRST.** If the current turn's context contains a `LAZY-ROUTE (hook-injected, turn N):` banner (written by `lazy-route-inject.sh`), the inject hook already ran the probe and routed the turn. The banner is a single `additionalContext` string with the structure:

```
LAZY-ROUTE (hook-injected, turn N): {"feature_id": "...", "sub_skill": "...", "cycle_prompt": "...", "cycle_model": "opus", ...} nonce=<hex-value>
```

On post-compaction re-entry a `POST-COMPACTION RE-ENTRY:` paragraph follows the nonce; if the inject hook errored, a `HOOK_ERROR: <error text>` suffix appears at the end. When the banner is present:
- Use the injected probe JSON (feature_id, sub_skill, cycle_prompt, cycle_model, counters) **as-is** — do NOT re-run the probe.
- Re-probing when a banner is present advances the persisted counters TWICE for one logical cycle — a protocol violation the retro grades.

When **no banner** is present, run the probe as normal:

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]
```

Pass `--skip-needs-research` **only when `allow_research_skip == true` AND `skip_needs_research == true`**. Under the default strict-halt path the flag is never added, so the script returns `terminal_reason: needs-research` for the first research-pending feature in queue order — see `~/.claude/skills/lazy-batch/SKILL.md` Step 1a for the double-gate rationale. Parse JSON output as in `/lazy-batch`.

**Probe enrichment (optional — folds repeat-count, git guards, and cycle header into one payload).** The orchestrator MAY call the probe with additional flags to fold `repeat_count`, `git_guards`, and `cycle_header` into the JSON in a single invocation:

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud --repeat-count --emit-prompt --probe \
  --max-cycles {max_cycles} \
  [--skip-needs-research]
```

The `--forward-cycles` and `--meta-cycles` flags are **NOT passed** — counters are persisted in the run marker and read directly by the script. Passing them on the CLI would override the marker values and create counter drift. The `cycle_header` field returned by `--probe` is POST-advance and 1-based (reflects the current cycle number after incrementing).

`--repeat-count` enriches the output with a `repeat_count` field (how many consecutive cycles returned the same `(feature_id, sub_skill, sub_skill_args, current_step)` tuple) for mechanical loop detection. It ALSO emits a `step_repeat_count` field (consecutive cycles reaching the same `(feature_id, current_step)` STEP — `sub_skill`/`sub_skill_args`-blind, NO head-advance reset). **Probe hygiene:** `--repeat-count` ADVANCES both persisted streaks, so it is reserved for the SINGLE dispatch-bound probe per cycle; any diagnostic / inspection probe MUST use `--repeat-count-peek` instead (reads the would-be streaks WITHOUT advancing them). The dispatch-tuple `repeat_count` is HEAD-aware: the same tuple plus new commits since the last probe RESETS it to 1 (re-validation after landed commits is forward progress, not a loop). **`step_repeat_count` is the oscillation tripwire (T6): when it is `>= 3`, STOP — do NOT keep dispatching the emitted action mechanically.** Surface `⚠ step '<current_step>' reached <step_repeat_count> times without advancing — inspect routing before dispatching`, then investigate why routing keeps returning to that step. The step counter deliberately does NOT reset on HEAD advance — it catches "productive-looking" oscillation where each cycle commits a file (HEAD moves → the dispatch streak resets every iteration) yet routing never leaves the step (the live d8 write-plan loop, 2026-06-11); a high `step_repeat_count` with a low `repeat_count` is that signature. (Doubly relevant under cloud, where each spurious cycle's stray commit gets pushed.) Never redirect probe or diagnostic output into the repo tree — write to the OS temp dir if you must capture it (doubly important under cloud, where stray repo files get committed + pushed). `--probe` folds `git_guards` (clean-tree + origin-parity) and a pre-formatted `cycle_header` string into the response. `--emit-prompt` folds the fully-assembled `cycle_prompt` / `cycle_model` (`cycle_prompt_refused` on assembly failure) into the JSON — with `--cloud` the emitter selects the cloud-mode sections (cloud preamble, `CLOUD OVERRIDE — LOAD-BEARING`, cloud push discipline, cloud turn-end) and binds every token. SHOULD be passed on every probe (null on pseudo-skill/terminal probes, always safe); Step 1d consumes it verbatim. These flags are purely additive — the base JSON fields are unchanged.

**Step 1a — probe ONCE per cycle (F2 double-probe debounce).** Run exactly ONE advancing, dispatch-bound `--repeat-count --emit-prompt` probe per cycle — the one whose `cycle_prompt` you actually dispatch — and use `--repeat-count-peek` for EVERY inspection / sanity / out-of-band probe so that only the single dispatch-bound probe advances the streaks. Probing a route twice with no dispatch between (an inspection probe, then the dispatch-bound probe) is a re-read, not a re-attempt, and historically inflated `step_repeat_count` into false `LOOP DETECTED` blocks. `update_repeat_counts` now defends this in depth: when a run marker is present it debounces a re-read via the registry consume-count delta (an unchanged consumed-emission count between two identical step probes ⇒ no dispatch landed ⇒ `step_repeat_count` is HELD, not incremented), so a genuine same-step oscillation (a real dispatch — hence a consume — between repeats) still trips while a benign double-probe no longer does. This note is the behavioral complement: even with the script debounce, keep to one advancing probe + peek for inspection.

**Post-compaction re-entry:** The session counters (`forward_cycles`, `meta_cycles`) are persisted in the run marker — the post-compaction probe reads them from the marker directly. Do NOT attempt to reconstruct counters from session memory or T2/T4 headings. Trust the marker. After compaction, run the full probe form (`--cloud --repeat-count --emit-prompt --probe --max-cycles …`) and proceed only from its output.

**Investigation triggers (cloud variant — record and DEFER).** The three `/investigate` triggers and the no-narrative-as-fact rule from `/lazy-batch` Step 1a (see `~/.claude/skills/_components/investigation-dispatch.md`) apply. Note: `--emit-dispatch investigation` now exists — the orchestrator SHOULD emit a registered investigation dispatch rather than composing a hand-crafted prompt; however since `/investigate` is **workstation-class work** (it needs the live Tauri/MCP runtime), a cloud orchestrator does NOT dispatch it immediately. On a trigger, record it — one cycle-log line plus a note in the BLOCKED.md `## Resolution` (or the feature's deferral notes) naming the trigger and the symptom — and defer the dispatch to a workstation run. The no-narrative-as-fact rule still binds cloud dispatch prompts fully: cite a current `INVESTIGATION.md` or state "cause unknown — investigation pending"; never author causal narratives as fact.

**Park-mode probe flag (`--park` only).** When `park_mode == true` (the `--park` invocation flag), append BOTH `--park-needs-input` AND `--park-blocked` to EVERY `lazy-state.py --cloud` probe invocation in this step (base or enriched form alike). With these flags, the script skips features carrying an unresolved `NEEDS_INPUT.md` (instead of halting on `needs-input`) OR a feature-local `BLOCKED.md` (instead of halting on `blocked`), and reports them in a `parked[]` array on the JSON output — each entry tagged `sentinel_kind` (`needs-input` | `blocked`) — the input to the Step 1g park path, the Step 1g-flush, and the §1c.6 park notifications. When every remaining feature is parked, the script returns the distinct `queue-exhausted-all-parked` terminal (handled in Step 1b). When `park_mode == false`, call the script plain (NEITHER flag) — existing behavior, byte-for-byte; the `parked[]` key never appears, and a feature-local `BLOCKED.md` still halts on `blocked` (Step 1h). Park is environment-agnostic — this is identical to `/lazy-batch` (no cloud divergence).

If the script exits non-zero, run `python3 ~/.claude/scripts/lazy-state.py --run-end` (idempotent — safe even if the marker is absent), surface the error, push a PushNotification, print the final batch report (see Step 2), and STOP.

### 1b. Handle terminal states

Same handling as `/lazy-batch` for `blocked`, `needs-input`, `needs-spec-input`, `queue-missing`, `all-features-complete`, `completion-unverified`, `stale_upstream` — the resolution-mode routing below is the SAME as `/lazy-batch` (it is docs-only: `AskUserQuestion` + docs edits + `/add-phase` + queue reorder, none of which need Tauri/MCP, so it runs identically in cloud). Cloud-specific terminals are called out separately.

If `terminal_reason` is set:

- **`blocked`**: see Step 1h (blocked-resolution mode). **Not a terminal halt anymore — and most blockers no longer ask.** Step 1h classifies the blocker FIRST per `completeness-policy.md` §3: a sequencing-only blocker auto-resolves (add-phase + fix now, or `/spec-bug` / ad-hoc spin-off + dependency-gate + requeue-to-tail), logged + push-notified, no question. Only a genuine product fork re-prints the `BLOCKED.md` body verbatim, runs `AskUserQuestion` for the resolution path (add a phase / defer to queue tail / halt-for-manual / custom), records the choice, dispatches the Opus apply-resolution subagent to enact it (neutralizing `BLOCKED.md` via rename), and returns to Step 1a. The loop continues; do NOT print the final batch report — UNLESS the operator chooses "Halt for manual fix", which keeps `BLOCKED.md` untouched and STOPs (the legacy behavior, now one option among several). **Park-mode exception (`park_mode == true`):** this terminal is NOT reached for a feature-local block — the `--park-blocked` probe flag (Step 1a) parks the blocked feature into `parked[]` and advances the queue, so Step 1h does NOT fire for it; the block is deferred to the Step 1g-flush. Per SPEC D5 this includes escalation/mcp-validation per-feature blocks. Identical to `/lazy-batch` (park is environment-agnostic).
- **`needs-input`**: see Step 1g (decision-resume mode — identical to `/lazy-batch` Step 1g). **Not a terminal state for the orchestrator anymore** — Step 1g auto-resolves scope-class decisions per D7 first (never asked), resolves the remaining product-class decision(s) via `AskUserQuestion`, dispatches the Sonnet apply-resolution subagent, and returns to Step 1a. Do NOT print the final batch report.
- **`needs-spec-input`**: see Step 1i (operator-directed halt-resolution) — the orchestrator re-prints what the dir contains and `AskUserQuestion`s the path (provide spec direction → seed the baseline / defer & continue queue / halt). It no longer bare-STOPs "cannot start from nothing".
- **`completion-unverified`**: a feature claims `Complete` with no `COMPLETED.md` receipt (flipped outside the validation gate). See Step 1i (operator-directed halt-resolution): re-print the gap and `AskUserQuestion` the path — reopen & re-validate (`**Status:** In-progress` → let the pipeline re-run retro + MCP) / grandfather the receipt (`lazy-state.py --backfill-receipts`, only if genuinely validated before the gate) / defer & continue / halt. Do NOT auto-flip, auto-reopen, or auto-backfill — that judgment is the operator's, now surfaced as a choice rather than a bare halt.
- **`stale_upstream`**: an upstream feature/work-item this feature was materialized from changed since materialize. See Step 1i (operator-directed halt-resolution): re-print the gap and `AskUserQuestion` the path (re-materialize/absorb → re-run materialize or `/realign-spec` / reject the change / defer & continue / halt). Do NOT auto-resolve.
- **`cloud-queue-exhausted`**: Run `python3 ~/.claude/scripts/lazy-state.py --run-end`. PushNotification `"Cloud queue exhausted after {forward_cycles} forward + {meta_cycles} meta cycle(s) — N feature(s) awaiting workstation /lazy for MCP test."` Print final batch report, STOP. (Environment exhaustion — per the halt-resolution component's exclusion list, NOT routed to Step 1i; the resolution is environmental, not an in-session operator choice.)
- **`device-queue-exhausted`**: A remaining feature carries `DEFERRED_REQUIRES_DEVICE.md` (real-device-only assertions) but no `DEFERRED_NON_CLOUD.md`, so the cloud-saturated skip didn't catch it. Cloud has no audio device either, so cloud cannot certify it. Run `python3 ~/.claude/scripts/lazy-state.py --run-end`. PushNotification with `notify_message`, print final batch report, STOP — surface that a **real-device** /lazy host (`ALGOBOOTH_REAL_AUDIO_DEVICE=1` or native hardware) is needed to re-open and certify the deferred scenarios. Rare in cloud: cloud-saturated features normally carry `DEFERRED_NON_CLOUD.md` and hit `cloud-queue-exhausted` first.
- **`needs-research`**: see Step 4 (research halt — same dual-path shape as `/lazy-batch`, but the sentinel's `written_by` is `lazy-batch-cloud`). Default (strict halt) writes the sentinel, runs `python3 ~/.claude/scripts/lazy-state.py --run-end`, prints the inline-prompt halt announcement, PushNotifies, prints the final batch report, and STOPs. Opt-in (`--allow-research-skip`) drops the sentinel, flips `skip_needs_research = true`, returns to Step 1a.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode — identical to `/lazy-batch` Step 1f). **Only reachable when `allow_research_skip == true`.**
- **`queue-missing`**: Run `python3 ~/.claude/scripts/lazy-state.py --run-end`. PushNotification with `notify_message`, print final batch report, STOP. (There is no queue to continue — the operator must create `queue.json` first; NOT routed to Step 1i per the halt-resolution component's exclusion list.)
- **`all-features-complete`**: Run `python3 ~/.claude/scripts/lazy-state.py --run-end`. PushNotification `"ALL FEATURES COMPLETE — roadmap finished after {forward_cycles} forward + {meta_cycles} meta /lazy-batch-cloud cycle(s)."`, print final batch report, STOP. (Genuine success — NOT routed to Step 1i; the queue is done, there is nothing to resolve.)
- **`queue-exhausted-all-parked`** (`--park` mode only): the queue advanced past every workable feature and every remaining feature is parked (blocked and/or needs-input). HONEST distinct terminal — NOT `all-features-complete` (the roadmap is not finished) and distinct from `cloud-queue-exhausted` (workstation-MCP wait). FIRST fire the Step 1g-flush (triggers (b)/(c)) so every parked item — needs-input AND blocked (`sentinel_kind`) — is surfaced and resolved at run-end (docs-only; runs identically in cloud); THEN run `python3 ~/.claude/scripts/lazy-state.py --run-end`, PushNotification `"Queue exhausted — {parked_count} feature(s) parked (blocked/needs-input); surfaced at flush."`, print final batch report, STOP. Do NOT report success. Identical to `/lazy-batch` (park is environment-agnostic).

### 1c. Check the max-cycles cap

If `forward_cycles >= max_cycles` (same shape as `/lazy-batch`):

```bash
python3 ~/.claude/scripts/lazy-state.py --run-end
```

```
PushNotification({ message: "lazy-batch-cloud hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP.

### 1c.6. PushNotification policy (park / halt / flush / run-end)

The orchestrator fires `PushNotification` at exactly four canonical event points so the operator receives a phone notification whenever the run changes state. `PushNotification` is always called by the **orchestrator** — state scripts never call it.

1. **park** (`--park` mode only) — fired once per newly-parked item when `park_mode == true` and the probe returns a non-empty `parked[]` array (the script's queue-walk park skip; `parked[]` arrives on ordinary Step 1a probes and lists ALL currently-parked items, not just new ones). **Dedup rule:** maintain an in-session set of already-notified parked ids; on each probe, fire only for ids in `parked[]` that are NOT yet in the set, then add them. Never re-fire for an id already in the set. (After a compaction boundary the set may be lost — one duplicate notification per item after a compact is acceptable; re-seed the set from the current `parked[]` on the first post-compact probe without firing.) **Wording branches on the entry's `sentinel_kind` (identical to `/lazy-batch` §1c.6 item 1):** a **needs-input** park fires `"parked {feature_name} — {N} decision(s) parked so far this run"` (T5 chat line `⏸ parked {feature_name} — {N} decision(s) · notified ({parked_count} parked this run)`); a **blocked** park (`sentinel_kind == "blocked"`, `decision_count == 0`) fires `"parked {feature_name} — BLOCKED ({phase}); deferred to flush ({parked_count} parked this run)"` (T5 chat line `⏸ parked {feature_name} — BLOCKED ({phase}) · notified ({parked_count} parked this run)`, `{phase}` from the parked entry / `BLOCKED.md` frontmatter). Both branches share the SAME dedup set (fire once per newly-parked id; never re-fire; re-seed silently after a compaction boundary).
2. **halt** (both modes) — fired on every terminal/halt: `NEEDS_INPUT` halt, `BLOCKED` halt-for-manual, `needs-research` strict halt, `queue-blocked-on-research`, `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-missing`, `all-features-complete`, `queue-exhausted-all-parked` (`--park` mode — after the flush), `max-cycles`, script-error, and any future obstacle terminal. Most of these already carry per-terminal `PushNotification` calls above — this point names the policy explicitly so no terminal can be added without a notification. **MANDATORY: run `python3 ~/.claude/scripts/lazy-state.py --run-end` on EVERY terminal/halt path, BEFORE firing the PushNotification.** `--run-end` deletes the run marker AND the prompt registry. Missed deletion is self-healing (24h staleness + session-id mismatch on re-run) but is a protocol violation the retro grades.
3. **flush** (`--park` mode only) — fired when parked decisions are collected and sent to the operator via the batched `AskUserQuestion` (the WU-4 flush protocol). The notification signals that the operator's input is being requested. Message: `"lazy-batch-cloud flush — {N} parked decision(s) ready for your input"`.
4. **run-end** (both modes) — fired when the run terminates and the final batch report is printed. This point largely coincides with the terminal halts above; stating it as a named point ensures every run termination path fires a notification, even if a new exit path is added that does not fit one of the named terminal reasons.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small sentinel-file write + commit, NOT a real skill that performs implementation work. Perform the action inline (orchestrator session) instead of dispatching a subagent. Same rationale as `/lazy-batch` Step 1c.5: sentinel files are documentation, and dispatching an Opus subagent for a 10-line YAML write + commit wastes a full subagent's worth of context. On the cloud path this is especially costly because `__write_deferred_non_cloud__` fires once per feature in the normal flow.

Follow `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` Step 3's protocol for each pseudo-skill exactly (the wrapper and orchestrator do the same thing here):

- **`__write_deferred_non_cloud__`** — run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __write_deferred_non_cloud__ <spec_path> --deferred-step 8 --reason "Cloud Linux environment cannot run tauri:dev or reach the MCP HTTP server."` (the script is the single author of the DEFERRED_NON_CLOUD.md write — it writes kind: deferred-non-cloud with the supplied deferred_step, reason, deferred_by, and today's date, and is idempotent if the file already exists), then commit + push per policy.
- **`__write_validated_from_skip__`** — run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __write_validated_from_skip__ <spec_path>` (the script is the single author of the VALIDATED.md write — it reads SKIP_MCP_TEST.md, writes VALIDATED.md, and is idempotent), then commit + push per policy.
- **`__grant_skip_no_mcp_surface__`** — **workstation-only; the cloud variant NEVER emits it.** The structural MCP-skip short-circuit (a `**MCP runtime:** not-required` feature in a repo with no `src-tauri/` + no `package.json`) lives in `lazy-state.py`'s WORKSTATION Step 9 branch; under `--cloud` Step 9 always defers via `__write_deferred_non_cloud__` first, so the short-circuit never fires here. Listed for coupled-trio parity only — like `mcp-test`, it is a workstation-only routing target. (Workstation handling: `/lazy-batch` Step 1c.5.)
- **`__mark_complete__`** — only reachable from cloud if `VALIDATED.md` already exists (cloud cannot produce VALIDATED.md from MCP results — workstation did; retro is unwired, so `RETRO_DONE.md` is no longer a precondition). **Hard guard (no premature Complete):** before flipping anything, confirm `<spec_path>/VALIDATED.md` exists. If `<spec_path>/DEFERRED_NON_CLOUD.md` exists AND `VALIDATED.md` does NOT, REFUSE to mark complete — the MCP-validation pass that writes `VALIDATED.md` has not run yet, so `Complete` would be a lie. In that case do NOT touch SPEC/ROADMAP status; treat the cycle as a no-op forward-progress issue (the state script should not have emitted `__mark_complete__` here — surface it) and continue. **Second gate: MCP-coverage audit** via the deterministic `--gate-coverage` subcommand (unified-pipeline-orchestrator Phase 5; mirrored from `/lazy-batch`): run `python3 ~/.claude/scripts/lazy-state.py --gate-coverage <spec_path>` — it reads SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface and greps each `<spec_path>/mcp-tests/*.md` (RESOLVING symlink/64-byte-pointer targets — the Windows blindspot) for each decision's id + keywords, returning JSON `{ok, decisions, uncovered:[id], scenario_count}` (exit 1 iff `uncovered[]` is non-empty). The algorithm spec + the D7 routing live in `~/.claude/skills/_components/mcp-coverage-audit.md`. If `uncovered[]` is non-empty, follow the component's D7 outcome (`completeness-policy.md` §4 — Gate 1 never asks, no NEEDS_INPUT.md): documented-MCP-untestable decisions get an inline SPEC test-exempt note (a docs-level `__mark_complete__` edit — HARD CONSTRAINT 1 holds); the rest route to a corrective coverage cycle — dispatch a cycle subagent to author the `mcp-tests/` scenario(s) (docs-only, runs in cloud; the scenario RUN defers to workstation per the normal cloud MCP deferral), emit the `⚖ policy:` line(s) + D7-digest entries, commit + push immediately (container-reclaim durability). Append `{forward_cycles + meta_cycles + 1, feature_name, "__mark_complete__ (audit halted)", "{N} uncovered decisions → corrective coverage cycle"}` to `cycle_log`, increment `forward_cycles` (gate-halted mark-complete is still forward-advancing), return to Step 1a — the next mark-complete attempt re-audits `clean` once the coverage/exemptions exist. **The audit is docs-only** (reads SPEC.md + `mcp-tests/*.md`, no Tauri / no MCP server) — it runs identically in cloud and workstation. **Third gate: completion-integrity gate** (runs only after the coverage audit returns `clean`, fed by the shared `~/.claude/skills/_components/completion-integrity-gate.md` component, with `{cloud}=true`). The orchestrator inlines it: verify phase-coherence (zero non-verification unchecked deliverables in PHASES.md) and that a validation sentinel exists (in cloud, `DEFERRED_NON_CLOUD.md` counts ONLY alongside `VALIDATED.md` — which the first guard already requires). `RETRO_DONE.md` is NO LONGER required (retro unwired). If a precondition fails, write `<spec_path>/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`), commit + push, append `{forward_cycles + meta_cycles + 1, feature_name, "__mark_complete__ (gate halted)", "<reason> → NEEDS_INPUT.md"}` to `cycle_log`, increment `forward_cycles`, return to Step 1a. Only when ALL THREE gates pass (VALIDATED.md present AND audit `clean` AND integrity `gated`): run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __mark_complete__ <spec_path>` — the script is the single author of COMPLETED.md (kind: completed, provenance: gated, folding the validation evidence from VALIDATED.md/MCP_TEST_RESULTS.md into the receipt body — the durable proof `lazy-state.py` Step 2 keys on), the SPEC.md/PHASES.md `**Status:** Complete` flip, the deletion of the consumed VALIDATED.md/RETRO_DONE.md/DEFERRED_NON_CLOUD.md sentinels (COMPLETED.md/SKIP_MCP_TEST.md/MCP_TEST_RESULTS.md are kept), the `docs/features/queue.json` trim (now by RESOLVED `spec_dir`, killing the `-followups` queue.no-completed class), AND the `docs/features/ROADMAP.md` strikethrough (moved INTO `--apply-pseudo` as of unified-pipeline-orchestrator Phase 5; the subcommand returns `roadmap_struck`/`queue_trimmed`). **Mechanical coherence gate inside `--apply-pseudo`:** the script auto-flips all-ticked phases to Complete and REFUSES (`refused:<reason>`, zero writes) if any phase retains an unchecked box (verification rows included) or a non-Complete/Superseded Status. On `ok: false` + this refusal, do NOT retry blindly — route a corrective coherence cycle via `--emit-dispatch coherence-recovery` and dispatch it verbatim (the subagent reconciles PHASES.md honestly — tick-with-evidence or re-scope, never blind-tick — commit + push, then return to Step 1a), exactly as a coverage-audit halt routes. Emit: `python3 ~/.claude/scripts/lazy-state.py --emit-dispatch coherence-recovery --context item_name="{feature_name}" --context spec_path="{spec_path}" --context gate_output="{the refused: reason from --apply-pseudo}" --context item_id="{feature_id}" --context cwd="{cwd}"`. Use `dispatch_prompt` VERBATIM as the Agent `prompt:` and `dispatch_model` as the `model:`. The ROADMAP strikethrough is NO LONGER an orchestrator step — `--apply-pseudo __mark_complete__` strikes the `docs/features/ROADMAP.md` row itself (unified-pipeline-orchestrator Phase 5; returns `roadmap_struck`). Then commit + push per project policy. This closes the 30%-of-features Reopened-Complete gap the audit walk surfaced AND the un-gated-completion gap (a `Complete` with no receipt now hard-halts).
- **`__flip_plan_complete_cloud_saturated__`** — emitted by `lazy-state.py --cloud` at Step 7a when an `In-progress` plan's only unchecked WUs (scoped to the plan's `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. This is the cloud-only common path; it fires once per saturated plan part. `sub_skill_args` is the absolute plan-file path. Run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __flip_plan_complete_cloud_saturated__ <spec_path> --plan <plan_file_path>` (the script edits only the `status:` line in the plan frontmatter → `Complete`, is idempotent, and does NOT touch SPEC.md, ROADMAP.md, or any sentinel). Derive the plan part number from the plan's `phases:` field for the commit message (e.g. `phases: [6]` → part 6; fall back to the plan filename's leading `part-N` / `phase-N` token). Commit per project policy with message `chore(<feature_id>): mark plan part N Complete (cloud-saturated)`, then push. This pseudo-skill is what prevents the `Step 7a: execute plan` no-op loop hit on `audio-thread-panic-catching` plan part 6: previously the orchestrator would dispatch `/execute-plan` against an In-progress plan whose only remainder was workstation-gated, the cycle would correctly diagnose "no cloud work" but make no commit, and the next cycle would receive the same state — burning Opus dispatches without advancing the queue. This is a **forward cycle** — increment `forward_cycles`.
- **`__flip_plan_complete_stale__`** — emitted by `lazy-state.py --cloud` at Step 7a (and by `lazy-state.py` without `--cloud`) when EVERY work-unit a Ready/In-progress plan references is already `[x]` — the plan is stale/already-applied but the frontmatter `status:` was never flipped. `sub_skill_args` is the absolute plan-file path. **Action (stays inline — `--apply-pseudo` does NOT implement stale):** read the plan's YAML frontmatter, edit ONLY the `status:` line in place (`Ready` or `In-progress` → `Complete`) — leave every other field and the markdown body untouched. Derive the plan part number from the plan's `phases:` field; fall back to the plan filename's leading `part-N` / `phase-N` token if `phases:` is missing. Stage the plan file and commit per project policy with message `chore(<feature_id>): mark plan part N Complete (stale — already applied)`. Do NOT touch SPEC.md, ROADMAP.md, or any sentinel. **Distinction from `__flip_plan_complete_cloud_saturated__`:** stale fires in BOTH cloud and workstation (not cloud-only) and means every WU was already `[x]` — not deferred to workstation, genuinely done. Without this flip the `Step 7a: execute plan` probe would return an In-progress plan with all WUs done, loop on `/execute-plan`, and make no progress. This is a **meta cycle** — increment `meta_cycles` (flipping a stale plan is cleanup, not forward implementation work).

After the inline action:

1. Append to `cycle_log`: `{forward_cycles + meta_cycles, feature_name, sub_skill, "inline: <one-line summary>"}` (use the UPDATED total after the increment in step 5 below).
2. **Push backstop (HARD REQUIREMENT — cloud reclaim safety).** The inline pseudo-skill committed a sentinel / plan-frontmatter change locally; push it now so it survives container reclaim — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This is the backstop for inline cycles that the orchestrator owns directly — a `git push` of an already-committed change, NOT a Write/Edit, so HARD CONSTRAINT 1 still holds. If the push reports "up to date," that is fine (a prior cycle's push already carried it).
3. Emit the T4 inline pseudo-skill block (Step 3 / orchestrator-voice.md): the canonical step heading (`### {Step name} — {work summary} [x/y]`), an `act` line (`{sub_skill} → {feature_id}`), a `gates` line when gates ran (`__mark_complete__`), a `done` line (inline outcome), and a `next` line. Nothing else. A gate REFUSAL switches to T6-refusal (rich) — the refusal evidence and the NEEDS_INPUT routing deserve full detail.
4. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` (same uniform post-cycle update as Step 1e — keeps the loop-guard accurate across mixed pseudo-skill / real-skill cycles).
5. Increment the appropriate counter: `forward_cycles` for pipeline-advancing pseudo-skills (`__mark_complete__`, `__write_deferred_non_cloud__`, `__write_validated_from_results__`, `__write_validated_from_skip__`, `__flip_plan_complete_cloud_saturated__`); `meta_cycles` for cleanup pseudo-skills (`__flip_plan_complete_stale__`). Return to Step 1a — DO NOT fall through to Step 1d.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

**Compaction discipline — re-read the dispatch template AND the output contract first.** Before composing this dispatch — and ALWAYS as the first action after any compaction boundary — re-read `~/.claude/skills/_components/lazy-dispatch-template.md`, `~/.claude/skills/_components/orchestrator-voice.md` (the chat-output contract — its turn templates survive summarization by re-read, not by memory; the re-reads themselves are silent mechanics), AND `~/.claude/skills/_components/completeness-policy.md` (the D7 standing policy — its auto-resolve rules likewise survive compaction by re-read, not memory). The dispatch template is the on-disk canonical dispatch skeleton (`subagent_type`, the REQUIRED `model:` field, prompt envelope) and carries the **Read-before-Edit rule**: compaction resets read-state, so re-`Read` any file (PHASES.md, plans, SKILLs, components) before you `Edit`/`Write` it. 41% of post-compaction spawns in the 2026-06-10 audit dropped the `model:` field — re-reading this template before each dispatch is what prevents that.

**Post-compaction re-entry protocol (HARD — the first post-compaction action is NEVER a dispatch; mirrored from `/lazy-batch` Step 1d).** Compaction is the measured protocol cliff (2026-06-11 run: counters never recovered, probes stopped, prompts went hand-authored post-boundary). On the first turn after any compaction boundary, BEFORE any `Agent` call: (1) re-read Step 1a of this SKILL plus the three components named above; (2) the session counters (`forward_cycles`, `meta_cycles`) are persisted in the run marker — the post-compaction probe reads them from the marker directly; do NOT attempt to reconstruct counters from the summarized session memory; where `max_cycles` or `prev_cycle_signature` is unclear, re-derive conservatively from on-disk evidence (`git log` since the run-start commit + sentinel mtimes) and record any uncertainty in a single T6 `⚠` line; (3) run the FULL Step 1a probe form (`--cloud --repeat-count --emit-prompt --probe --max-cycles …`) and proceed only from its output. Dispatching from a pre-compaction probe held in memory, or from a hand-reconstructed prompt, is a contract violation. Trust the marker.

**Long-build ownership (harness-tracked).** Cloud has no Tauri runtime, so packaged `tauri build` does not run here — but the ownership rule is universal: any build or test that may exceed a single subagent turn (e.g. a multi-minute `cargo` run inside a long `/execute-plan` cycle) is **orchestrator-owned**: start it with `Bash` `run_in_background: true` from this (the orchestrator) session and track it via the harness — NEVER background it from inside a dispatched cycle subagent, whose process tree is torn down when its turn ends. Full rule: `.claude/skill-config/long-build-ownership.md`. This is `Bash`-only process ownership — it does not expand the orchestrator's sentinel-only `Write`/`Edit` scope (HARD CONSTRAINT 1 holds).

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build the dispatch by CONSUMING the script-assembled prompt — the cloud cycle prompt is NO LONGER inlined here.

**Consume the script-assembled cloud prompt — do NOT hand-bind or inline it.** The probe (`python3 ~/.claude/scripts/lazy-state.py --cloud … --repeat-count --emit-prompt`, Step 1a) returns `cycle_prompt` already assembled for cloud: `emit_cycle_prompt` selected the cloud-mode sections (the cloud preamble — no Tauri / MCP / audio / Windows-only tooling, no persistent state; the `CLOUD OVERRIDE — LOAD-BEARING` sub-subagent / per-skill inline-edit override; the cloud per-batch push discipline; and the cloud TURN-END CONTRACT) and bound every token (`{item_name}`, `{item_id}`, `{cwd}`, `{current_step}`, `{sub_skill}`, `{sub_skill_args}`, `{work_branch}`, … — the full 14-token list is in the component's header). Use `cycle_prompt` **VERBATIM** as the Agent `prompt:` and `cycle_model` as the Agent `model:`. The orchestrator no longer maintains a hand-synced copy of the cloud cycle prompt — the sectioned `cycle-base-prompt.md` (with its `modes=cloud` sections) is the single source, and the `--cloud` emit selects it. **Same null/refused fallback rule as `/lazy-batch`** — see `~/.claude/skills/lazy-batch/SKILL.md` Step 1d: on a `cycle_prompt_refused` for a REAL skill, surface a T6 deviation and fall back to reading + hand-binding the component (degraded path).

**Continuation cycles re-emit — there is NO hand-composed real-skill prompt, EVER (mirrored from `/lazy-batch` Step 1d).** A real-skill dispatch is valid ONLY when its `prompt:` is the `cycle_prompt` produced by an `--emit-prompt` probe run in the SAME turn as the `Agent` call. When a cycle returns partial, needs a retry, or work "continues" on the same feature, return to Step 1a and RE-PROBE — the script re-assembles the correct prompt for the new on-disk state. Both measured protocol failures in the 2026-06-11 run were hand-composed continuation prompts; the emitted path had zero failures. The ONLY exception is the announced `cycle_prompt_refused` degraded fallback above. **Freshness — never dispatch an emission from an earlier turn** (applies to `cycle_prompt` AND every `--emit-dispatch <class>` output): the emitted text is dispatchable only while verbatim in context within the SAME turn it was emitted, and cloud-reclaim / `SessionStart:resume` boundaries make a stale in-context copy especially likely. If any turn boundary, summarization, or edit intervened since the emit, RE-EMIT fresh and dispatch within that same turn. Hand-editing emitted text (appending notes, "cleaning up", re-typing) is the failure class; the template's `--context` slots are the ONLY customization point.

**Loop-guard cross-check (identical shape to `/lazy-batch` Step 1d):** BEFORE dispatching, independently compute the current cycle's signature as the tuple `(feature_id, sub_skill, sub_skill_args, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)`, the state returned the same tuple two cycles in a row — almost always a missing terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`). **`sub_skill_args` MUST be part of the compared tuple** — otherwise a multi-part `/execute-plan` sequence (different plan-part path per part, same other fields) false-triggers the guard on every part despite genuine forward progress. **Loop-block inclusion and the opus/sonnet selection are SCRIPT-OWNED** (driven by the persisted per-pipeline `repeat_count`): `cycle_prompt` arrives with the loop block already appended and `cycle_model` already `"sonnet"` when `repeat_count >= 2`. The in-session signature is retained as the cross-check (it still drives the T2 `(sonnet, loop-resolution)` `disp` tag); if it fires but `cycle_model` came back `"opus"`, re-run the probe WITH `--repeat-count --emit-prompt` rather than hand-appending the block.

<!-- The cloud cycle base prompt is no longer inlined in this SKILL. Its content (cloud preamble,
     CLOUD OVERRIDE — LOAD-BEARING, cloud Commit + PUSH policy, cloud TURN-END CONTRACT, and the
     LOOP DETECTED block) lives in the sectioned component
     `~/.claude/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (modes=cloud sections)
     + `loop-block.md`, and is emitted, fully token-bound, as the probe's `cycle_prompt`. NEVER
     re-inline it here — that hand-synced copy was exactly what Phase 8 deleted. -->

The loop-guard evaluation itself is silent — never announce "no loop-guard fires" (orchestrator-voice.md hard ban); the only visible trace of a fired guard is the `(sonnet, loop-resolution)` tag on the T2 `disp` line.

**Emit the T2 cycle-dispatch block (Step 3 / orchestrator-voice.md) immediately before the Agent call:** the canonical step heading (`### {Step name} — {work summary, ≤12 words} [x/y]`) + the `disp` line (`{sub_skill} → {feature_id} ({model}[, loop-resolution|recovery])`). Nothing else between the block and the dispatch. **Probe-presence guard (mirrored from `/lazy-batch`):** the heading line MUST carry the dispatch-bound probe's `cycle_header` field VERBATIM — never re-typed from memory. A probe-shaped heading with no same-turn probe behind it is graded as a probe-cadence violation.

**Governing-file reload discipline (self-edit mode — C8; mirrored from `/lazy-batch` §1d).** When the Step 1a `--cloud` probe reports `self_edit_mode: true`, this run is editing the harness it executes from, so a cycle that commits to the orchestrator's own in-context governing prose makes the copy you hold stale. After EVERY cycle, intersect the cycle's commit (`git diff --name-only`, or read the probe's `governing_files_touched` list) with the **governing-file set** and re-`Read` any hit via its `~/.claude/...` path BEFORE composing the next dispatch:
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (THIS file) + the `user/skills/lazy-batch/SKILL.md` and `user/skills/lazy-bug-batch/SKILL.md` twins
- `user/skills/_components/orchestrator-voice.md`, `user/skills/_components/completeness-policy.md`, `user/skills/_components/lazy-dispatch-template.md`

This is the SAME re-read as the compaction discipline above (triggered by a self-edit commit instead of a compaction boundary) and the governing-file set MUST stay in lockstep with that compaction re-read list. The re-read is a silent mechanic. **Auto-refresh boundary (documented no-ops — never reload):** `lazy_core.py`/`lazy-state.py`/`bug-state.py` (fresh subprocess every probe), `lazy-batch-prompts/cycle-base-prompt.md` + addenda + `loop-block.md` (re-read by `emit_cycle_prompt` every probe), hook `.sh` bodies, and downstream skill prose are ALREADY live on the next probe/dispatch and are EXCLUDED by construction. **New-hook-registration restart surfacing (T6):** if a cycle's commit added/removed a hook ENTRY in `settings.json` (NOT merely a script-body edit), surface `⚠ settings.json hook wiring changed — restart the session to (de)register; the running session still uses the old wiring` — do NOT claim the change is live. (Cloud note: the bracket and reload discipline are NOT cloud divergences — identical shape to `/lazy-batch`.)

**Cycle-marker dispatch bracket (C1 — lazy-cycle-containment; identical to `/lazy-batch` §1d, cloud passes `--cloud`).** EVERY `Agent` dispatch (the real-skill cycle below AND every meta-dispatch: input-audit, apply-resolution, recovery, coherence-recovery, hardening §1d.1, investigation) MUST be bracketed: `lazy-state.py --cloud --cycle-begin --feature-id {feature_id} --nonce {dispatch_nonce} --kind real|meta --sub-skill {sub_skill} --sub-skill-args {sub_skill_args}` IMMEDIATELY before, `lazy-state.py --cloud --cycle-end` IMMEDIATELY after on EVERY return path (success / halt / error). The begin writes the cycle-subagent marker (`~/.claude/state/lazy-cycle-active.json`); it is self-healing (a stale marker is overwritten + logged) and NOT C3-guarded. **`--sub-skill {sub_skill}` is MANDATORY on EVERY bracket — real AND meta (`--kind meta` is NOT a licence to omit it)** — bind it to the probe's `sub_skill` VERBATIM, INCLUDING a pseudo-skill name like `__mark_complete__` when the meta cycle is a Gate-1 corrective-coverage / completion-gate dispatch. It persists into the marker so `--cycle-end`'s process-friction detector picks the correct per-sub_skill commit budget — without it the detector falls back to the conservative default (budget 1) and false-positives `unexpected-commits` on a legitimate multi-commit cycle (the real-cycle `execute-plan` test+impl case, budget 3, AND the meta `__mark_complete__` completion cycle whose `--apply-pseudo` receipt+flip and corrective-coverage commits exceed 1, budget 3 — the 2026-06-16 recurrence). **`--sub-skill-args {sub_skill_args}` is EQUALLY MANDATORY on a real `execute-plan` cycle (and any cycle whose probe returns a non-null `sub_skill_args`) — bind it to the probe's `sub_skill_args` VERBATIM (the absolute plan-part path).** `--cycle-end` scales the `execute-plan` budget by the plan part's WORK-UNIT count (`max(phase_count, wu_count) + slack`), but it can only read the plan when the marker carries `sub_skill_args` — omitting it makes the scaled override return `None`, the detector falls back to the FIXED table budget of 3, and a WU-dense plan part (>3 work units) **false-positives `unexpected-commits`** even though `--sub-skill execute-plan` was supplied correctly (the 2026-06-16 `adhoc-mcp-runner-payload-interpolation` recurrence: 4 commits vs `budget=3`). Pass BOTH flags together (doubly important under cloud, where each spurious friction-trip cycle's stray commit gets pushed). The end is idempotent (zero error if absent) — clear it on ALL THREE return paths because a dangling `--cycle-begin` would block the orchestrator's own next ops (`--run-end`, `--apply-pseudo`, the next probe's `--emit-dispatch`) via the C3 refusal; self-healing staleness is a crash-only backstop, not a substitute. Both are silent mechanics. (`--cloud` is the ONLY cloud divergence in the bracket — the shape is identical.)

Dispatch:

```
# 1. Set the cycle marker (C1) — --sub-skill AND --sub-skill-args are MANDATORY on real
#    AND meta brackets (--kind meta is NOT a licence to omit --sub-skill; bind the probe's
#    sub_skill verbatim, including a pseudo-skill like __mark_complete__ for a completion-gate
#    meta cycle; bind --sub-skill-args to the probe's sub_skill_args verbatim — the plan-part
#    path on execute-plan cycles — so --cycle-end can WU-scale the commit budget):
python3 ~/.claude/scripts/lazy-state.py --cloud --cycle-begin --feature-id {feature_id} --nonce {dispatch_nonce} --kind {real|meta} --sub-skill {sub_skill} --sub-skill-args {sub_skill_args}

# 2. Dispatch:
Agent({
  description: "lazy-batch-cloud cycle {forward_cycles + meta_cycles + 1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: <the probe's cycle_model>,
  prompt: <the probe's cycle_prompt_ref if present, otherwise cycle_prompt verbatim>
})

# 3. Clear the cycle marker (C1) — on EVERY return path (success / halt / error):
python3 ~/.claude/scripts/lazy-state.py --cloud --cycle-end
```

**F2a dispatch-by-reference (PREFERRED when available, mirrored from `/lazy-batch` Step 1d).** When the probe emits `cycle_prompt_ref` (a `@@lazy-ref nonce=<hex>` token), use it as the `prompt:` field instead of the full `cycle_prompt` text. The PreToolUse guard resolves the token → registered bytes and rewrites the tool input before the subagent runs. Fall back to `cycle_prompt` verbatim ONLY when `cycle_prompt_ref` is absent or null.

**Model selection — script-owned (mirrored with `/lazy-batch`).** The orchestrator no longer chooses the model: copy `cycle_model` from the `--cloud … --emit-prompt` probe into the `model:` field (never omit it — see the dispatch template). The script makes the choice — `"sonnet"` ONLY when it appended the loop block (persisted `repeat_count >= 2`), `"opus"` otherwise. The rationale is unchanged: normal real-skill cycles run Opus because they can involve novel implementation decisions, while the loop-resolution cycle is mechanical (the cloud `cycle_prompt` already carries the diagnosis — read the canonical sentinel schema, identify which sentinel's preconditions are met, write it, commit), so Sonnet suffices at roughly 5× the cost-efficiency.

### 1d.1. Denial recovery

If the `Agent` dispatch of `cycle_prompt` is **DENIED** by the validate-deny guard (`lazy-dispatch-guard.sh`):

**Pending hardening debt (script-routed — the probe WITHHOLDS the forward route).** Every guard deny is appended to the deny ledger (`lazy-deny-ledger.jsonl`); a marker-gated probe surfaces `pending_hardening: <int>` (with `pending_denials: [<reason summaries>]` when `> 0`). While debt is pending, the probe emits NO `cycle_prompt` — it returns `route_overridden_by: "pending-hardening-debt"` plus `hardening_emit_command`, a pre-composed `--emit-dispatch hardening` command bound from the oldest unacked denial. Run it verbatim and dispatch its `dispatch_prompt`; the entry is acked when the GUARD ALLOWS the hardening dispatch (not at emission — emitting without dispatching clears nothing). Repeat probe → hardening until a normal forward route returns. **Consume the FULL probe JSON** — piping probe output through field-extractors is BANNED (it blinds the orchestrator to `route_overridden_by`); the probe also warns on stderr while debt is live. `python3 ~/.claude/scripts/lazy-state.py --run-end` REFUSES (exit 1) while any unacked denial remains; the `--ack-unhardened` override is operator-authorization-ONLY (printed into the run-end message for retro grading) — never passed autonomously.

**Trigger 1 — validate-deny on a cycle prompt:** The guard denied the prompt (nonce mismatch, stale registry entry, or prompt was re-composed rather than used verbatim). Recovery steps:
1. Re-run the dispatch-bound probe in the same turn: `python3 ~/.claude/scripts/lazy-state.py --cloud --repeat-count --emit-prompt --probe --max-cycles {max_cycles}`. This emits a fresh `cycle_prompt` registered with a new nonce.
2. Dispatch the fresh `cycle_prompt` **VERBATIM** as the `Agent` prompt. Do NOT paraphrase or re-compose it.
3. **IN ADDITION**, on EVERY guard denial emit a hardening dispatch (locked decision 4: a denial means a hand-composed prompt reached the guard, which is a harness gap by definition — inline, unbounded, no dedup):

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=validate-deny \
  --context item_id={feature_id} \
  --context denied_prompt_summary="<one-line summary of the denied prompt>" \
  --context denial_reason="<the permissionDecisionReason from the guard>" \
  --context probe_json="<full probe JSON output>" \
  --context registry_state="<relevant registry entries or 'empty'>" \
  --context cwd="{cwd}"
```

Dispatch the `dispatch_prompt` **VERBATIM** as an Opus `Agent` call. The hardening dispatch is emitted REGARDLESS of whether the re-probe dispatch (step 2) succeeds or fails — the denial itself is the trigger. **Depth-cap exception:** a denial OF a hardening dispatch never dispatches another hardening stage (see Depth cap below). If the step-2 re-dispatch is also denied, proceed to trigger 2.

**Trigger 2 — probe refuses or no-route (`cycle_prompt_refused`):** The probe could not assemble a valid cycle prompt (unknown step, contradictory state, or marker/state divergence). Emit a hardening dispatch:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch hardening \
  --context trigger_kind=no-route \
  --context item_id={feature_id} \
  --context denied_prompt_summary="cycle probe returned cycle_prompt_refused" \
  --context denial_reason="{cycle_prompt_refused value from probe}" \
  --context probe_json="{full probe JSON output}" \
  --context registry_state="{relevant registry entries or 'empty'}" \
  --context cwd="{cwd}"
```

Dispatch the `dispatch_prompt` **VERBATIM** as an Opus `Agent` call. Because it is registered at emit time, the validate-deny guard will allow the exact prompt.

**Trigger 3 — inject hook HOOK_ERROR breadcrumb:** If the `LAZY-ROUTE (hook-injected, turn N):` banner contains a `HOOK_ERROR` marker (the inject hook itself errored during probe execution), treat this as a no-route condition and follow Trigger 2 above with `trigger_kind=inject-hook-error`.

**Trigger 4 — process-friction (a `kind: process-friction` deny-ledger entry):**  
If the probe returns `route_overridden_by: "pending-hardening-debt"` and the oldest unacked ledger entry carries `kind: process-friction` (written by `lazy-state.py --cloud --cycle-end` on a torn cycle bracket or unexpected commits), emit a hardening dispatch with `trigger_kind=process-friction`. Use the `hardening_emit_command` from the probe JSON verbatim — it already binds `friction_reason` and `friction_detail` in the `--context` keys instead of `denied_prompt_summary`/`denial_reason` (the `build_hardening_emit_command` function in `lazy_core.py` handles this automatically based on the entry's `kind`). This trigger fires **even when the runaway's work was salvaged** (D2: signal, not noise — accepting the output and hardening the bypass are orthogonal). This trigger is **shared** with `/lazy-batch` (not a cloud divergence) — the process-friction ledger entry is written by the same `lazy_core.cycle_end_friction_check` function regardless of cloud flag.

**Depth cap (two deny shapes — the guard's reason text discriminates):**

- **(a) Ordinary corrective recipe on the hardening dispatch (hash mismatch — a transcription slip on YOUR copy of the emitted `dispatch_prompt`, NOT recursion):** re-run `python3 ~/.claude/scripts/lazy-state.py --emit-dispatch hardening …` (fresh nonce, same `--context` keys) and make exactly ONE verbatim re-dispatch attempt, copying `dispatch_prompt` mechanically. A second recipe denial then falls through to the halt protocol below.
- **(b) The guard's HALT REASON (text contains "halt" and "PushNotification" — the denied prompt matched a registered hardening-class entry, i.e. genuine depth-1 recursion) OR a SECOND recipe denial:** the orchestrator MUST:
  1. Surface a T6 `⚠` with the denial evidence.
  2. Run `python3 ~/.claude/scripts/lazy-state.py --run-end`.
  3. PushNotification: `"lazy-batch-cloud HALT — hardening dispatch denied; depth cap reached. Manual investigation required."`.
  4. Print final batch report, STOP.

The orchestrator MUST NOT dispatch a hardening stage beyond the single (a) re-attempt.

### 1d.5. Post-cycle input audit (Opus — runs only on `/spec` and `plan-feature` cycles)

**MIRRORED with `/lazy-batch` Step 1d.5.** See `~/.claude/skills/lazy-batch/SKILL.md` Step 1d.5 for the full algorithm, skip conditions, post-return handling, and `audit_concurs` recording. The audit subagent's contract is identical in cloud and workstation: docs-only writes (only `{spec_path}/NEEDS_INPUT.md`), no source/test edits, no recursive dispatch, no Skill-tool calls. The cycle subagent that just ran was forbidden from using the `Agent` tool (cloud-override per Step 1d), but the audit subagent is dispatched by the orchestrator (main session, which retains `Agent`), so dispatch works identically.

**Emit the registered audit dispatch (do not hand-compose the prompt):**

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch input-audit \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context cycle_kind="{sub_skill}" \
  --context cycle_summary="{one-line summary of what the cycle did}" \
  --context cycle_commit_sha="{HEAD commit sha after the cycle}" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Use the returned `dispatch_prompt` **VERBATIM** as the Agent `prompt:` and `dispatch_model` as the Agent `model:`. The emit registered the prompt in the prompt registry; the validate-deny guard will allow it.

**Cloud-specific nuance: none.** The audit subagent does not require the Tauri desktop, the MCP HTTP server, or any cloud-restricted capability — it reads files in `{spec_path}/`, classifies decisions, and (optionally) writes one sentinel file. The sentinel commit + push folds into the cycle's normal post-cycle push (guardrail B end-of-cycle push catches it; guardrail C backstop at Step 1e verifies). Cloud-reclaim safety is preserved: NEEDS_INPUT.md is committed and pushed before the orchestrator returns to Step 1a.

**Skip conditions, dispatch, audit prompt, post-return bullet rules:** verbatim from `/lazy-batch` Step 1d.5. The product-behavior smells checklist the auditor applies lives in `~/.claude/skills/spec/SKILL.md` ("Product-behavior smells — concrete checklist"); the Decision-Classification Ledger contract the auditor verifies against also lives there.

**`audit_concurs` recording is INCLUDED in this mirrored contract.** `/lazy-batch` Step 1d.5 step 7 specifies that when the sentinel under audit carries `class: mechanical`, the audit subagent independently re-classifies all decisions and records `audit_concurs: true | false` in the frontmatter. That step is part of the "verbatim" contract above — the cloud audit subagent performs the same recording. Cloud-reclaim safety: the `audit_concurs` frontmatter edit is committed and pushed immediately (same commit as the sentinel write, or a follow-on commit if the sentinel pre-existed), so the field survives container reclaim. Effect: if the cloud audit concurs (`audit_concurs: true`) and the cycle subagent classified `class: mechanical`, the parked-flush (when the cloud run ends or a flush trigger fires) may auto-accept the decision via D2 two-key — the same path as workstation `/lazy-batch`.

### 1e. Record cycle outcome and loop

Append to `cycle_log` `{forward_cycles + meta_cycles + 1, feature_name, sub_skill, subagent's one-paragraph summary}`, emit the T3 cycle-return block (Step 3 / orchestrator-voice.md) under the cycle's T2 heading — a `done` line (duration + load-bearing outcome); an `audit` line where required (the `/execute-plan` inline/test-first audit signal — REQUIRED on `/execute-plan` cycles, mirroring `/lazy-batch` Step 1e item 2 — or, on `/spec` / `plan-feature` cycles, the Step 1d.5 input-audit's NEEDS_INPUT disposition, REQUIRED on every such cycle in BOTH cases: surfaced → `audit  {N} product-behavior decision(s) surfaced → NEEDS_INPUT.md`, or skipped → `audit  needs-input skipped — {N} reviewed, all {mechanical-internal | scope-class (D7) | none arose}; {≤12-word justification}` — the NEEDS_INPUT skip is never silent, per `_components/sentinel-frontmatter.md` Producer responsibilities #7 and `/lazy-batch` Step 1d.5 item 2); a `ledger` line (post-cycle guard outcome); a `next` line (the fresh probe's routing) — no other prose. Then update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)`, increment `forward_cycles`, loop. **Spin-off notification:** if the cycle return reports spinning off a bug doc or an `--enqueue-adhoc` feature (the cycle owns the reverse-reference in the origin feature's doc per `cycle-base-prompt.md`), the orchestrator fires `PushNotification("spun off {id} — {reason}")` and adds a D7 digest entry (`completeness-policy.md` §Logging / §5 — pre-authorized, notify + log, never a question). **Post-cycle push backstop (HARD REQUIREMENT — cloud reclaim safety):** after the cycle subagent returns, the orchestrator verifies the work branch is pushed — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). Under guardrail B the cycle subagent already pushed every batch commit, so this normally reports "up to date" — it is the backstop for any cycle (or future skill) that did not push itself. A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 still holds. The prev-signature update is the uniform post-cycle action that keeps the Step 1d loop-guard accurate across both real-skill and pseudo-skill cycles. **The `forward_cycles` increment is also a uniform post-cycle action that NEVER resets on feature transitions (HARD CONSTRAINT 8) — when the next `lazy-state.py --cloud` call returns a different `feature_id` (e.g. after `__mark_complete__`, after `__write_deferred_non_cloud__` rolls the queue to the next ready feature, or any other queue-advance), `forward_cycles` continues incrementing from where it was.**

**Post-`/execute-plan` ledger-consistency guard (guardrail D — mirrored from `/lazy-batch` Step 1e item 4a).** When the cycle that just returned was `/execute-plan`, run a SINGLE-TURN consistency check BEFORE the next state probe (Step 1a). This is NOT polling (HARD CONSTRAINT 7 holds); these are `Bash` reads + one script call, so HARD CONSTRAINT 1 (sentinel-only Write/Edit) holds too. The cycle subagent is supposed to leave a clean, consistent ledger via the atomic gate+commit (Step 1d `/execute-plan` override), but it empirically loses its turn between gates and commit — and under cloud reclaim that residue is doubly dangerous. This guard catches it deterministically instead of relying on operator memory. `/mcp-test` defers in cloud, so this guard fires on `/execute-plan` cycles only.

   First fetch so `@{u}` is current (the `--verify-ledger` `head_matches_origin` check compares HEAD to `@{u}` and does NOT fetch itself):
   ```bash
   git fetch origin $(git rev-parse --abbrev-ref HEAD)
   ```
   Then run — **plan-scoped** (this guard fires on `/execute-plan` cycles only, so a plan part always exists; `{plan_file}` = the probe's `sub_skill_args`, the absolute plan-file path):
   ```bash
   python3 ~/.claude/scripts/lazy-state.py --cloud --repo-root <repo_root> --verify-ledger {spec_path} --plan {plan_file}
   ```
   With `--plan`, `plan_complete` checks THIS plan part's frontmatter flipped `Complete` and `deliverables_done` reads THIS plan part's own `- [ ] WU-N` checkboxes (the machine source of truth since the 2026-06-15 d8-effect-chains review — NOT the PHASES.md phase-level deliverable rows). Because the plan part is the unit of execution and its WUs never span parts or phases, a still-pending LATER plan part no longer false-fails the guard (cite: live-run false alarm 2026-06-11), AND the cross-part + cross-phase-attribution false-fails the old PHASES read suffered are gone. Read the JSON `ok`/`failing_check`/`checks` fields plus the diagnostic `deliverables_source` (`plan-wu-checkboxes` normal; `phases-fallback …` = a legacy pre-ISSUE-6 plan). (`--cloud` is included here so the plan-Complete check uses cloud-mode semantics, matching what `lazy-state.py --cloud` infers in Step 1a.)

   If `ok` is true → proceed to the `forward_cycles` increment. If `ok` is false → emit and dispatch a recovery subagent (an allowed corrective dispatch — NOT a numbered cycle, does NOT increment `forward_cycles`). Emit the registered recovery dispatch:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py \
     --emit-dispatch recovery \
     --context item_name="{feature_name}" \
     --context spec_path="{spec_path}" \
     --context failure_summary="{failing_check}: {one-line description of what failed}" \
     --context item_id="{feature_id}" \
     --context cwd="{cwd}"
   ```

   Use the returned `dispatch_prompt` **VERBATIM** as the Agent `prompt:` and `dispatch_model` as the Agent `model:`. The recovery subagent reconciles per the named `failing_check` and carries the work-branch-only clause (commit and push to the current branch only — `git rev-parse --abbrev-ref HEAD` at start — never a new branch, never --force). Then re-run the guard. Recovery guidance per `failing_check`:
   - `clean_tree` or `head_matches_origin` failing → the recovery subagent stages + commits any residue and pushes (cloud-reclaim-safe per-batch push, work branch only).
   - `plan_complete` failing → the recovery subagent re-flips the plan-part frontmatter `status:` → `Complete` and ticks any still-unchecked PHASES.md non-verification boxes that have on-disk evidence of completion, then commits + pushes.
   - `deliverables_done` failing → the failing surface is the plan part's `- [ ] WU-N` checkboxes (when `deliverables_source` is `plan-wu-checkboxes`). The common reconciliation is: a landed WU whose plan-body box is merely unticked → tick it `- [x]`, commit + push. This does NOT require chasing PHASES.md deliverable rows in other parts/phases — those no longer gate. The recovery subagent may tick a **verification** WU box (one under a "Runtime Verification / MCP Integration Test" subsection) ONLY when there is on-disk evidence that verification actually ran for that row (e.g. `VALIDATED.md` or `MCP_TEST_RESULTS.md` present in `{spec_path}/` and covering it). If a non-verification WU is genuinely incomplete it is real outstanding work → route back to execute-plan, or if blocked write `{spec_path}/NEEDS_INPUT.md` describing the gap and surface it — do not silently tick unverified or incomplete boxes. Note: `--verify-ledger`'s `deliverables_done` already exempts verification-only WU rows, so it will not false-fail on legitimately-pending Runtime-Verification boxes.

   Surface the failed check per T6 (`⚠ verify-ledger {failing_check} failed` → evidence → recovery action taken), and record the post-recovery outcome on the cycle's T3 `ledger` line. Do NOT advance to Step 1a until the guard passes.

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

**Reachable only when `allow_research_skip == true`.** Identical shape to `/lazy-batch` Step 1f — passive halt with inline RESEARCH_PROMPT.md content for every pending feature (fenced ```text block for mobile long-press-copy into Gemini), char-count over/under indicator against the 24,000-char Gemini web-UI cap, all three upload paths. Run `python3 ~/.claude/scripts/lazy-state.py --run-end` before the PushNotification. PushNotification, final batch report, STOP.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1f for the full algorithm and the announcement template — replace "/lazy-batch" with "/lazy-batch-cloud" in the chat text. Cloud-specific upload nuance:

- **FASTEST RESUME (cloud-recommended): in-session upload via chat.** Upload the research in your NEXT MESSAGE — file attachment, pasted text, or any chat-uploaded file. The orchestrator (per Step 5) dispatches `/ingest-research` in-session, which writes the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` into the feature directory BEFORE the cloud container is reclaimed. This is the only fully-durable cloud resume path that does not require leaving the conversation.
- **Upload path ① (staged .txt, gitignored — non-durable in cloud):** save each Gemini output as `docs/gemini-sprint/results/<feature-id>.txt`. **The `docs/gemini-sprint/results/` path is gitignored**, so a bare `.txt` stage from a cloud session will NOT survive container reclaim — it only works if you also commit/push the staged file from a workstation (GitHub UI push), or if `/ingest-research` runs in-session to convert the staged .txt into the tracked RESEARCH.md + RESEARCH_SUMMARY.md before the container goes away. The in-session resume above does exactly that.
- **Upload path ② (direct RESEARCH.md drop, durable):** write the research directly to `docs/features/.../<feature_id>/RESEARCH.md`. This file IS tracked, so it survives cloud reclaim. From cloud, you still need to commit the file inside the container (the cycle subagent on the next run will commit it as part of normal work, or you can commit it explicitly). The next `/lazy-batch-cloud` run routes straight to `/spec` Phase 3.
- **Upload path ③ (`/ingest-research <path>`)** is workstation-only — it operates on absolute file paths the cloud container cannot see. If you're working from a phone via the cloud branch, use the in-session resume path or path ②.

The user can mix environments: drop `RESEARCH.md` directly from workstation, then resume from cloud; or upload research via chat in the cloud session and let the in-session resume protocol handle it end-to-end.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

**No meta-cap check** — `meta_cycles` is uncapped (operator decision 2026-06-14); the meta loop has no halt. The run's only hard stop remains the `forward_cycles >= max_cycles` cap at Step 1c.

**Pipeline binding for the shared handler below** — `{SKILL}` = `/lazy-batch-cloud`, `{STATE_SCRIPT}` = `lazy-state.py` (run with `--cloud`), `{ITEM}` = feature, `{PUSH_RULE}` = **cloud: the apply subagent MUST push the work branch IMMEDIATELY after each commit (container-reclaim durability — a local-only commit is lost if the container is reclaimed)**. The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`** (decision-resume is a meta cycle). The per-cycle update block heading uses the two-counter format (Step 3 template). Then read and apply the shared decision-resume handler exactly (single source across the feature / bug / cloud batch orchestrators):

`~/.claude/skills/_components/decision-resume.md`

**Apply-resolution dispatch (MUST use `--emit-dispatch apply-resolution` — do not hand-compose):** When the shared handler instructs the orchestrator to dispatch the apply-resolution subagent:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch apply-resolution \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context sentinel_path="{spec_path}/NEEDS_INPUT.md" \
  --context resolution_summary="{one-line description of the chosen resolution}" \
  --context resolution_kind="needs-input" \
  --context chosen_path="{the operator's chosen option label}" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Use the returned `dispatch_prompt` **VERBATIM** as the Agent `prompt:` and `dispatch_model` as the Agent `model:`. Emission registers the prompt; the validate-deny guard will allow it.

**Park mode — processing `parked[]` output (Phase 4, `--park` only):** When `park_mode == true` and the probe returns a non-empty `parked[]` array, the orchestrator skips the `AskUserQuestion` resolution flow for each item in that array and instead parks it: for each newly-parked `feature_name`, increment `parked_count` and fire `PushNotification({ message: "parked {feature_name} — {parked_count} decision(s) parked so far this run" })` (per the §1c.6 park policy). Continue the queue walk without halting. The batched flush of all parked decisions occurs later via the WU-4 flush protocol (see §1g-flush below).

---

### 1g-flush. Parked-decision flush (`--park` only)

**Guard:** runs only when `park_mode == true`. When `park_mode == false` this step is entirely
skipped — behavior is byte-for-byte the existing one.

**Pipeline binding for the shared flush component below** — `{SKILL}` = `/lazy-batch-cloud`,
`{STATE_SCRIPT}` = `lazy-state.py` (run with `--cloud`), `{ITEM}` = feature, `{PUSH_RULE}` =
**cloud: the apply subagent MUST push the work branch IMMEDIATELY after each commit
(container-reclaim durability — a local-only commit is lost if the container is reclaimed)**.
The meta-cycle accounting translates to **increment `meta_cycles`** per applied decision,
matching every other resolution mode.

**Three flush triggers (fire at the FIRST of):**

- **(a) Operator message mid-run:** any mid-run operator message while `park_mode == true` and
  unresolved parked items exist triggers an immediate flush before processing the message further
  (after echo-back if the message implies a standing-directive change).
- **(b) No unparked work remains:** when `lazy-state.py --cloud` returns `cloud-queue-exhausted`
  or `all-features-complete` and unresolved parked items still exist, flush FIRST — do NOT treat
  queue-exhausted as a real STOP while unresolved parked items remain. The cloud pipeline's normal
  terminal is `cloud-queue-exhausted` (features deferred for workstation MCP testing); the guard
  applies equally there.
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

**Pipeline binding for the shared handler below** — `{SKILL}` = `/lazy-batch-cloud`, `{STATE_SCRIPT}` = `lazy-state.py` (run with `--cloud`), `{ITEM}` = feature, `{SPEC_ROOT}` = `docs/features`, `{ADD_PHASE}` = `/add-phase`, `{PUSH_RULE}` = **cloud: push the work branch IMMEDIATELY after each commit (container-reclaim durability)**. The shared handler's "increment `cycle`" step translates to **increment `meta_cycles`** (blocked-resolution is a meta cycle). The enactment is docs-only (no Tauri/MCP), so it runs identically in cloud. Then read and apply the shared blocked-resolution handler exactly (single source across the feature / bug / cloud batch orchestrators):

`~/.claude/skills/_components/blocked-resolution.md`

**Apply-resolution dispatch (MUST use `--emit-dispatch apply-resolution` — do not hand-compose):** When the shared handler instructs the orchestrator to dispatch the apply-resolution subagent:

```bash
python3 ~/.claude/scripts/lazy-state.py \
  --emit-dispatch apply-resolution \
  --context item_name="{feature_name}" \
  --context spec_path="{spec_path}" \
  --context sentinel_path="{spec_path}/BLOCKED.md" \
  --context resolution_summary="{one-line description of the chosen resolution}" \
  --context resolution_kind="blocked" \
  --context chosen_path="{the operator's chosen option label}" \
  --context item_id="{feature_id}" \
  --context cwd="{cwd}"
```

Use the returned `dispatch_prompt` **VERBATIM** as the Agent `prompt:` and `dispatch_model` as the Agent `model:`. Emission registers the prompt; the validate-deny guard will allow it.

---

### 1i. Operator-directed halt-resolution (other non-max-cycles problem-terminals)

**No meta-cap check** — `meta_cycles` is uncapped (operator decision 2026-06-14); the meta loop has no halt. The run's only hard stop remains the `forward_cycles >= max_cycles` cap at Step 1c.

For every remaining problem-terminal that previously bare-`STOP`ed — `completion-unverified`, `needs-spec-input`, `stale_upstream` (and any future obstacle terminal) — the orchestrator routes here instead of halting. Rather than dead-ending, it re-prints the obstacle context, `AskUserQuestion`s a resolution path (reopen & re-validate / provide direction / defer & continue / halt-for-manual / custom), enacts the choice via an Opus apply-resolution subagent, and continues the loop. Follow the shared component (read and apply it exactly):

`~/.claude/skills/_components/halt-resolution.md`

Per that component's exclusion list, these terminals are NOT routed here and keep their existing behavior: `max-cycles` (cost bound — hard stop), `all-features-complete` (genuine success), `cloud-queue-exhausted` / `device-queue-exhausted` (environment — re-run on the right host), and `queue-missing` (no queue to continue). The research-pending terminals (`needs-research` / `queue-blocked-on-research`) keep their specialized Step 4 / Step 1f handling, which already lets the operator continue (in-session chat upload or re-invoke) rather than dead-ending; the component's "defer this research-pending feature & continue" option is available there as an enhancement when the queue has independent downstream work.

**Cloud parity note.** Every enactment the component lists (re-print → `AskUserQuestion` → SPEC/ROADMAP status edit / `/realign-spec` / `/spec` seed / queue reorder → neutralize-by-rename → commit) is docs-only — no Tauri runtime, no MCP HTTP server, no audio device. Step 1i therefore runs **identically to `/lazy-batch` Step 1i** in cloud; the only cloud nuance is that the apply subagent pushes immediately for container-reclaim durability.

The Step 1i cycle records like any other (cycle_log entry, per-cycle block, `prev_cycle_signature = (feature_id, "__resolve_halt__", sub_skill_args, current_step)`, **increment `meta_cycles`**), and only the operator-chosen "Halt for manual fix" path stops the run.

---

## Step 1.5: Forward-Progress Verification (informally "Step 2.5"; runs after loop exit, before the Step 2 batch report)

**Identical algorithm to `/lazy-batch` Step 1.5** — see `~/.claude/skills/lazy-batch/SKILL.md` Step 1.5 for the full protocol. Cloud variant uses `python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]` for the probe, identical to Step 1a.

Skip the probe entirely when `terminal_reason in {"blocked", "needs-input", "queue-missing"}`. (Note: a `blocked` loop-exit now occurs ONLY when the operator chose "Halt for manual fix" in Step 1h — every other Step 1h path resumes the loop, so it never reaches loop-exit as `blocked`.) For every other exit — including `all-features-complete`, `cloud-queue-exhausted`, `needs-research`, `queue-blocked-on-research`, and max-cycles — run the probe, compare its `(feature_id, sub_skill, sub_skill_args, current_step)` tuple against `prev_cycle_signature`, and prepend ONE of these blocks to the Step 2 final batch report:

- **Forward-progress confirmed** (probe differs from prev_cycle_signature OR probe terminal):

  ```
  ✅ Next /lazy-batch-cloud invocation will: <human-readable summary>
  ```

- **Forward-progress WARNING** (probe matches prev_cycle_signature; no terminal reason):

  ```
  ⚠ FORWARD-PROGRESS WARNING: the next /lazy-batch-cloud invocation will
  return the same state as the cycle we just finished
  (feature_id={feature_id}, sub_skill={sub_skill},
  sub_skill_args={sub_skill_args}, current_step={current_step}).

  This run did not advance the queue. Likely causes (cloud-specific):
    • A sentinel that should have been written wasn't (DEFERRED_NON_CLOUD.md,
      VALIDATED.md, SKIP_MCP_TEST.md).
    • A plan-frontmatter status flip the last cycle was supposed to perform
      did not land — most commonly, the cloud-saturated In-progress →
      Complete flip that __flip_plan_complete_cloud_saturated__ exists to
      perform. Inspect {spec_path}/plans/ frontmatter for any
      `status: In-progress` plan whose unchecked WUs are all listed in
      DEFERRED_NON_CLOUD.md.
    • lazy-state.py --cloud is stuck on a condition no cloud-runnable skill
      is resolving.

  Inspect {spec_path}/ sentinels and plan frontmatter before re-invoking.
  ```

  Plus PushNotification `"lazy-batch-cloud forward-progress WARNING — queue did not advance; inspect {feature_name} sentinels."`.

The probe is read-only — never mutates `forward_cycles`/`meta_cycles`, `cycle_log`, or sentinels. A non-zero probe exit prints `⚠ FORWARD-PROGRESS PROBE FAILED: lazy-state.py exited non-zero — re-invoke /lazy-batch-cloud to retry.` and the loop's already-produced final report still prints. The cloud-specific WARNING block adds the cloud-saturated-flip bullet because that is the failure mode most likely to silently strand a `/lazy-batch-cloud` run.

---

## Step 2: Final Batch Report

When the loop exits (terminal state, forward-cycles cap, or meta-cycles cap), print:

```
## /lazy-batch-cloud — Done

**Forward cycles used:** {forward_cycles}/{max_cycles}
**Meta cycles used:** {meta_cycles}
**Terminal reason:** {terminal_reason or "forward-cycles-cap"}
**Last notification:** {notify_message or "—"}
**Park mode:** {on | off}

### Cycle log
| # | Feature | Action | Summary |
|---|---------|--------|---------|
{cycle_log rows}
```

Header is `## /lazy-batch-cloud — Done`. Cloud-specific "Next step" guidance:

```
**Next step:**
  - If terminal_reason is "blocked": this is reached ONLY when the operator chose "Halt for manual fix" in Step 1h (every other Step 1h path resumes the loop). Resolve {spec_path}/BLOCKED.md by hand, then re-run `/lazy-batch-cloud {max_cycles}` — the next run re-enters Step 1h if BLOCKED.md is still present.
  - If terminal_reason is "needs-research" (DEFAULT path, strict halt): the fastest (and only fully-durable cloud) resume path is to upload Gemini research in your NEXT MESSAGE in this conversation — the in-session resume protocol (Step 5) will dispatch /ingest-research and re-invoke /lazy-batch-cloud automatically, writing the tracked RESEARCH.md before container reclaim. Otherwise, drop RESEARCH.md directly (path ②) and re-run `/lazy-batch-cloud {max_cycles}` from a fresh session.
  - If terminal_reason is "queue-blocked-on-research" (only reachable under --allow-research-skip): same as needs-research — upload research in chat for fastest resume, or use path ② and re-run `/lazy-batch-cloud {max_cycles} [--allow-research-skip]`.
  - (needs-input is no longer a terminal state — Step 1g resolves and resumes within the same /lazy-batch-cloud invocation. blocked, completion-unverified, needs-spec-input, and stale_upstream are likewise no longer dead-ends — Step 1h / Step 1i ask for a resolution path and resume; only the operator-chosen "Halt for manual fix" reaches this report.)
  - If terminal_reason is "cloud-queue-exhausted": run /lazy on workstation to run MCP tests
  - If forward-cycles-cap: re-run `/lazy-batch-cloud {max_cycles}` from a fresh session
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

*(One row per `⚖ policy:` application across the run — Step 1g scope resolutions, Step 1h sequencing-only blocker resolutions, parked-flush Step 2.4 backstop resolutions, coverage-audit routings, and cycle-subagent in-cycle applications disclosed in their summaries. Required by `completeness-policy.md` Logging; graded by R-D7-2.)*

Framing prose around the final report is capped at **≤2 sentences total (T7 per orchestrator-voice.md)** — the cycle table, counters, parked/auto-accept/D7 digests, terminal reason, and Next-step lines carry all required content.

STOP.

---

## Step 3: Cycle Output Discipline (orchestrator-voice.md is the binding contract)

**Identical contract to `/lazy-batch` Step 3** — per-cycle chat output for every cycle (real-skill Step 1e, inline pseudo-skill Step 1c.5, decision-resume Step 1g, blocked-resolution Step 1h, or halt-resolution Step 1i) is the T2 dispatch block + T3 return block (or T4 for inline pseudo-skills) from `~/.claude/skills/_components/orchestrator-voice.md`, under the canonical step heading, and nothing else:

```
### {Step name} — {work summary, ≤12 words} [{n}/{max}]                   ← T2 heading
disp   {sub_skill} → {feature_id} ({model}[, loop-resolution|recovery])   ← T2, at dispatch
done   {duration} · {load-bearing outcome}                                 ← T3, at return
audit  {…}                                                                ← only where Steps 1e / 1d.5 require it
ledger {clean · pushed | …}                                               ← post-cycle guard outcome
next   {fresh probe routing | terminal: <reason>}
```

The heading leads with the pipeline step being advanced to (T2's canonical names: Spec / Plan / Implement / Retro / Validate / Realign / Research / Mark Complete), then a ≤12-word summary of this cycle's work, then the counter — `[{forward_cycles}/{max_cycles}]` for forward cycles, `[meta {meta_cycles}]` for meta cycles (count only, no denominator — meta is uncapped) (values AFTER incrementing — the heading reads the completed state; the `/lazy-batch` reference uses the same convention). The retired `### Cycle fwd N/M · meta K/L` heading must not reappear. All contract rules carry over verbatim: mechanics silent (no dispatch narration, no commit-strategy narration, no probe restating), between-cycle commit prompts ignored silently, deviations surfaced as T6 (`⚠` → evidence → action → rule), halt/terminal announcements and resolution briefings (including the Step 1h blocked-resolution prompt + its "Halt for manual fix" stop, and the Step 1i halt-resolution prompt + its Halt stop) are T6 rich zones, final report is T7. The retired formats — the `· {feature_name} · {sub_skill}` heading suffix and the `**Result:**`/`**Commit:**` bullet block — must NOT reappear. See `~/.claude/skills/lazy-batch/SKILL.md` Step 3 for the full rules.

**Cloud nuance (background dispatch).** A cloud cycle subagent may be dispatched to run in the background (HARD CONSTRAINT 10 references in-flight background cycle agents). The T2 block emitted at dispatch is the ONLY output permitted before the result — the former `▶ … (dispatched)` line format is retired (T2 already marks the dispatch; the contract's Precedence clause governs). Specifically do NOT narrate "running in the background", "waiting on the completion notification", or any commit-race reasoning while it runs (this is exactly the noise the discipline removes). When the cycle completes, emit the T3 return block.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

**Identical dual-path shape to `/lazy-batch` Step 4.** Two paths gated by `allow_research_skip`: default (strict halt on first `needs-research`, inline-prompt announcement, run `python3 ~/.claude/scripts/lazy-state.py --run-end`, STOP) and opt-in (`--allow-research-skip`, drop sentinel, advance loop, halt later on `queue-blocked-on-research`). See `~/.claude/skills/lazy-batch/SKILL.md` Step 4 for the full algorithm.

**Mirrored from `/lazy-batch` Step 4 (kept in lockstep per the CLAUDE.md coupling rule):**

- **ANTI-EXEMPTION RULE (HARD).** A dependency / sibling / upstream feature having its own `RESEARCH.md` (even a Complete one) does NOT waive THIS feature's `needs-research` halt. Never improvise a "research already exists in the Complete sibling, no run needed" / "ships as a unit" fast path — the halted feature requires its OWN `RESEARCH.md`. Burned on `d8-effect-chains`, 2026-06-14.
- **Pointer resolution (HARD, bounded one level — LEGACY FALLBACK).** As of 2026-06-14 `/spec` Phase 2 writes every `RESEARCH_PROMPT.md` self-contained by construction (combined-unit features get the full combined prompt duplicated into each member, never a pointer stub — see `~/.claude/skills/spec/SKILL.md` Phase 2), so new prompts never need resolving. This remains as defense-in-depth for LEGACY pointer files predating that fix: when `{spec_path}/RESEARCH_PROMPT.md` is a POINTER doc (short body that links to another feature's `RESEARCH_PROMPT.md` — e.g. "Combined with `<other>` research (they ship as a unit)" + a relative link, often with a focus note like "Sections 4 and 7 are most relevant"), follow the link ONE level and surface the REFERENCED prompt's content (named focus sections + Context preamble, or the whole file if no sections are named), prepending the focus note verbatim — NEVER the bare pointer. Resolution changes WHAT is surfaced; it never skips the halt.
- **Prompt-block surfacing is HARD and NON-SKIPPABLE.** The default-path halt turn MUST print the (resolved) research prompt in a fenced ` ```text ` code block plus the FASTEST-RESUME in-session-upload instructions, then PushNotify. A turn that ends with only the sentinel write + the T7 report (no fenced prompt block) is a CONTRACT VIOLATION (defect-2 on the d8-effect-chains run) — the operator cannot act on a halt they cannot see.
- **Code block = prompt content ONLY (HARD).** The fenced ` ```text ` block contains nothing but the research prompt; all operator instructions (where to paste, FASTEST-RESUME, char-count line) stay OUTSIDE the fence, and meta-fluff (a leading "> Combined with … ship as a unit" blockquote, "Mode: deep-research" / "Model: gemini-2.5-pro" headers, "Send/Paste this into Gemini" lines) is STRIPPED before the content goes in the fence. The operator copies the fence verbatim into Gemini — see the CODE-BLOCK HYGIENE good/bad example in `research-halt-announcement.md`.

### Stub specs vs structured-research-pending specs (disambiguation rule)

Identical to `/lazy-batch` Step 4's disambiguation block (mirrored per the CLAUDE.md coupling rule — see `~/.claude/skills/lazy-batch/SKILL.md` Step 4 for the full rationale and the two-row table). Summary: `needs-research` fires ONLY for structured-but-research-pending specs (baseline locked, deep research missing). Stub specs (no baseline yet — detected by `is_stub_spec(spec_text, queue_entry)` in `lazy-state.py`: canonical `> Draft (pre-Gemini)` trailer, queue.json `"stub": true`, or a legacy marker) are routed at Step 4.5 instead and dispatched as a normal `/spec` cycle. The dispatched `/spec` subagent can call `AskUserQuestion` during Phase 1 brainstorming — HARD CONSTRAINT 5 binds the orchestrator only, not subagents it dispatches. **Cloud parity note:** the docs-only stub detection works identically in cloud (no Tauri / no MCP server required); the dispatched `/spec` cycle inherits the cloud cycle-subagent limitations documented in the unnumbered "Cloud-specific" paragraph after the HARD CONSTRAINTS (no recursive `Agent` dispatch — `/spec` runs inline edits inside the cycle subagent itself).

**Cloud divergences:**

- **`written_by` in the sentinel frontmatter is `lazy-batch-cloud`** (not `lazy-batch`). The rest of the YAML matches:

  ```yaml
  ---
  kind: needs-research
  feature_id: {feature_id}
  research_prompt_path: <relative path>
  written_by: lazy-batch-cloud
  date: <today>
  ---
  ```

- **Default-path halt announcement uses `/lazy-batch-cloud` in the chat heading and re-invoke line.** Replace every `/lazy-batch` token in the announcement template with `/lazy-batch-cloud`. The fenced ```text prompt block and char-count over/under indicator (against the 24,000-char Gemini cap) are unchanged. The "FASTEST RESUME" block (in-session chat upload → /ingest-research → re-invoke) is identical, only the re-invoke command name differs.

- **The cloud announcement reorders the alternative upload paths to reflect cloud reality.** In cloud:
  - **Path ① (staged .txt)** is gitignored and therefore NON-DURABLE across container reclaim unless ingested in-session. Surface this with the prefix `(gitignored — non-durable unless ingested in-session; in-session resume above does that automatically)`.
  - **Path ② (direct RESEARCH.md drop)** is durable. Recommended fallback when not using the in-session resume.
  - **Path ③ (`/ingest-research <path>`)** is workstation-only — cloud cannot reach file paths outside the container's repo working tree. Surface as `(workstation only)`.

- **In-session resume is the primary cloud-recommended path.** The default-path announcement's "FASTEST RESUME" block (per Step 5) is the load-bearing cloud durability guarantee: `/ingest-research` runs in-session and writes the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` BEFORE the cloud container is reclaimed. Without this protocol, a cloud user uploading a `.txt` to the gitignored staging dir would lose the file on reclaim.

Cloud cannot run Gemini itself — but the user provides research via any of the upload paths the announcement lists. Step 5 (in-session resume), Step 0.5's pre-loop check, and the natural state-script flow handle each path appropriately.

---

## Step 5: In-Session Resume Protocol (research uploaded via chat)

**Identical to `/lazy-batch` Step 5** — see `~/.claude/skills/lazy-batch/SKILL.md` Step 5 for the full algorithm. Summary:

1. User uploads research in their NEXT MESSAGE after a Step 4 / Step 1f halt (file attachment, pasted text, or absolute path).
2. Assistant correlates each upload to a pending feature (single AskUserQuestion permitted at this boundary if multi-feature ambiguity exists).
3. Materialize content into `docs/gemini-sprint/results/<feature_id>.txt`.
4. Dispatch `/ingest-research` as a Sonnet subagent. This writes the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` into the feature directory, clears the `> Draft (pre-Gemini)` SPEC trailer, clears `queue.json "stub": true`, moves consumed `.txt` to `_consumed/`, and commits per feature.
5. Re-invoke `/lazy-batch-cloud <N>` automatically (where `<N>` is the original `max_cycles`).
6. Print a brief resume status line so the user sees the bridge.

**Cloud-specific load-bearing rationale.** The `docs/gemini-sprint/results/` staging dir is gitignored. A bare `.txt` stage in cloud does NOT survive container reclaim. Step 5's in-session ingestion converts the non-durable staged `.txt` into the durable tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` BEFORE the container can be reclaimed — that is the cloud durability guarantee for the chat-upload path. Workstation users get the same convenience but without the durability stakes (their staged `.txt` survives between sessions on local disk).

**Cycle accounting at resume — two classes (mirrors `/lazy-batch` Step 1f).** Resume counter semantics depend on the resuming checkpoint's `operator_authorized` flag (recorded at `--run-end --reason checkpoint` time):

- **Operator-authorized resume** (a deliberate `/lazy-batch-cloud <N>` re-invoke after an operator-authorized checkpoint) gets a **fresh `0/0` budget** — `lazy_core.restore_checkpoint_counters` no-ops, leaving the marker's by-design start.
- **Automatic reliability resume** carries the counters forward monotonically so an auto-resume cannot exceed the authorized `max_cycles` (HARD CONSTRAINT 8). A pre-fix checkpoint file lacking the flag takes this path too.

**Cloud-specific:** cloud checkpoints (the unattended-checkpoint arm below) are written WITHOUT `--operator-authorized`, so a cloud resume ALWAYS takes the carry-forward path — see the unattended-checkpoint arm for the rationale.

HARD CONSTRAINT 7 (no active waiting) still holds: the halt is clean, the resume is single-turn-event-driven (the user's next chat message), and nothing polls the filesystem between halt and resume.

---

## Differences from `/lazy-batch`

| Aspect | `/lazy-batch` | `/lazy-batch-cloud` |
|--------|---------------|---------------------|
| State script invocation | `python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]` | `python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]` |
| Merged-view dispatch (unified-pipeline-orchestrator Phase 2) | **MIRRORED** — unified driver: each cycle probes the merged head (`lazy-state.py --next-merged`), type-dispatches feature → `lazy-state.py` + `__mark_complete__`, bug → `bug-state.py` + `__mark_fixed__`; ordering is `lazy_core.merged_priority`-owned; single-type runs unchanged (no-regression). State Machine Summary table documents the per-type dispatch. | **same merged-view shape**, `--cloud` carried on every state-script call (`lazy-state.py --cloud --next-merged`; bug cycles drive `bug-state.py --cloud`). The merged-view branch itself is NOT a cloud divergence — only `--cloud` differs. Cloud's normal feature terminal stays the deferral chain (`__write_deferred_non_cloud__` at Step 9 until a workstation produces `VALIDATED.md`); the bug terminal `__mark_fixed__` is reachable in cloud (bug validation is docs-only). |
| `cloud-queue-exhausted` terminal | defensive (unreachable in practice) | normal halt when remaining features await workstation MCP testing |
| Checkpoint-resume counter semantics (operator-checkpoint-resume-counter-reset) | **two classes** — operator-authorized checkpoint resume → fresh `0/0` budget (`restore_checkpoint_counters` no-ops); automatic reliability pause / pre-fix file → monotonic carry-forward. The attended workstation checkpoint is written WITH `--operator-authorized`. | **same helper logic** (shared `lazy_core`), but the unattended-checkpoint arm writes checkpoints WITHOUT `--operator-authorized` for BOTH triggers (≥2 denials, operator-pause), so a cloud checkpoint resume ALWAYS carries forward — a cloud fresh budget comes only from a brand-new `/lazy-batch-cloud <N>` (no checkpoint on disk). The Phase-1 mechanism supports threading the flag in cloud later if a checkpoint-backed fresh resume is ever wanted; current behavior omits it (no-behavior-change default). |
| `__write_deferred_non_cloud__` pseudo-skill | not emitted by state script | normal Step 9 action — handled INLINE in Step 1c.5, no subagent dispatch |
| `__write_validated_from_results__` pseudo-skill | normal Step 9 action — inline | not emitted (cloud cannot produce MCP results) |
| Step 0.52 validation-readiness pre-screen | advisory F5 pre-screen — front-loads DEFERRED_NON_CLOUD cohort with readiness verdicts before the loop | omitted — cloud never produces DEFERRED_NON_CLOUD.md entries until Step 9 fires, so the pre-screen has no candidates |
| `__flip_plan_complete_cloud_saturated__` pseudo-skill | listed in Step 1c.5 handlers as defensive (rare under workstation execution; included so any future state-script change that emits it under `--cloud=false` is still handled). | normal Step 7a action — emitted by `lazy-state.py --cloud` when an In-progress plan's only unchecked WUs are documented as workstation-only in `DEFERRED_NON_CLOUD.md`. Handled INLINE in Step 1c.5, no subagent dispatch. Prevents the `Step 7a: execute plan` no-op loop. |
| No-premature-Complete guard (SPEC/PHASES `**Status:**`) | **NOW MIRRORED (was a divergence).** Workstation's Step 1d cycle prompt carries a "No premature Complete (PIPELINE-GATE HONESTY)" guard: the cycle subagent MUST NOT flip top-level SPEC/PHASES `**Status:**` to `Complete` — reserved for `__mark_complete__` after /mcp-test (VALIDATED.md) → coverage audit. (/retro is unwired — 2026-06.) Added because an `/execute-plan` cycle flipping `Complete` itself was observed to roll the queue forward and SILENTLY SKIP the /mcp-test + coverage-audit tail. | both the cycle subagent prompt (Step 1d "No premature Complete") and the `__mark_complete__` inline handler (Step 1c.5) FORBID the cycle subagent flipping SPEC/PHASES top `**Status:**` to `Complete` under ANY condition; doubly enforced when `DEFERRED_NON_CLOUD.md` exists and `VALIDATED.md` is absent — MCP validation is deferred to a workstation pass in cloud, so `Complete` before it runs is dishonest. Honest terminal cloud state is `In-progress`. `/lazy-batch-retro` adds matching low-severity rule **R-C-4**. |
| Cycle subagent prompt (real skills only) | **same script-assembled prompt** — the orchestrator consumes the probe's `cycle_prompt` verbatim; the workstation sections are selected by the emitter. | **same script-assembled prompt, cloud sections selected by `--cloud`** — `lazy-state.py --cloud … --emit-prompt` makes the emitter add the cloud-environment limitations block AND the `CLOUD OVERRIDE — LOAD-BEARING` block (cycle subagent has NO `Agent` tool → performs all source/test edits and research INLINE using Edit / Write / Read, SUPERSEDING each dispatched skill's sub-subagent contract). The per-skill overrides (/execute-plan, /retro (dormant — unwired 2026-06), retro-feature (dormant — unwired 2026-06)) live in the sectioned `cycle-base-prompt.md` `modes=cloud` sections — NOT inlined in this SKILL (Phase 8 deleted the hand-synced copy). **Known cloud limitation:** collapsing /execute-plan's test-agent→impl-agent split into one inline subagent trades away the STRUCTURAL test-first guarantee (the cycle subagent must still write tests-before-impl by discipline). Compensating controls: per-batch quality gates + deferred MCP-validation pass. `/lazy-batch-retro` Step 4b cloud branch grades the corresponding R-EP-2/R-EP-3 as `n/a (cloud-override)`, not `fail`. |
| Ground-truth re-run (subagent-review.md Step 1.5) | **performed** — the orchestrator/review subagent re-runs each Sonnet sub-subagent's reported commands (git status / wc -l / grep / test runner) and diffs to detect falsified reports. Valuable because the implementer is a *separate* untrusted subagent. | **CLOUD-SCOPED DIVERGENCE — skipped.** In the inline path the cycle subagent wrote both tests and implementation itself, so there is no separate subagent report to police — the mechanical re-run is pure redundant work. The cloud /execute-plan override drops it (substantive correctness + propagation review still run). Consistent with `/lazy-batch-retro` already grading R-EP-4 as `n/a (cloud-override)` for cloud cycles. |
| Cycle subagent prompt — loop-guard (LOOP DETECTED block) | appended when prev_cycle_signature matches current (feature_id, sub_skill, sub_skill_args, current_step). **Same shape** in both. | appended on same condition; same block text — both orchestrators share the loop-break protocol. |
| Cycle subagent model selection | normal cycles → `model: "opus"`. LOOP DETECTED branch → `model: "sonnet"`. **Same in both** — the loop-resolution work is mechanical (read sentinel schema, identify which sentinel preconditions are met, write it, commit), and the diagnosis is already in the prompt. Sonnet handles it at ~5× the cost-efficiency. | same as workstation. |
| Cycle output discipline (Step 3) | **MIRRORED** — per-cycle chat output is the T2 dispatch block + T3 return block (T4 for inline pseudo-skills) per `~/.claude/skills/_components/orchestrator-voice.md`, under the canonical `### {Step name} — {work summary} [x/y]` heading; mechanics silent; deviations/briefings are T6; final report T7. **Same shape** in both. | same contract; one cloud nuance: a backgrounded cycle emits its T2 block at dispatch and the T3 block on completion — the former `▶ … (dispatched)` line format is retired; still no "running in the background" / "waiting on notification" / commit-race prose. |
| Forward-progress verification (Step 1.5 / "Step 2.5") | after loop exit, before final batch report. One additional read-only `lazy-state.py` invocation; compares probe tuple to `prev_cycle_signature`; prepends ✅ or ⚠ block to Step 2 report. Skipped on `blocked` / `needs-input` / `queue-missing`. **Same shape** in both. | same as workstation, but the WARNING block lists cloud-specific likely-cause bullets (notably the cloud-saturated In-progress → Complete plan-flip that `__flip_plan_complete_cloud_saturated__` exists to perform). |
| NEEDS_RESEARCH.md `written_by` | `lazy-batch` | `lazy-batch-cloud` |
| `--allow-research-skip` argument | parsed in Step 0; gates Step 4 path + Step 1a `--skip-needs-research` flag. **Same semantics** in both. | same as workstation — strict halt on first `needs-research` by default; opt in to batched-research via the flag. |
| Step 4 — default path (strict halt) | reads RESEARCH_PROMPT.md, prints fenced ```text inline halt announcement, PushNotifications, halts. **Same shape** in both. | same as workstation, but the announcement says `/lazy-batch-cloud` and upload path ③ is labeled `(workstation only)`. |
| Step 4 — opt-in path (`--allow-research-skip`) | drops sentinel, flips `skip_needs_research = true`, returns to loop. **Same shape** in both. | same as workstation; sentinel `written_by: lazy-batch-cloud`. |
| Research-wait mode (Step 1f) | passive halt — `terminal_reason: queue-blocked-on-research`. Reachable only under `--allow-research-skip`. Prints inline RESEARCH_PROMPT.md content for every pending feature, announces upload paths including in-session resume, PushNotification, STOP. Resume on next chat message (Step 5) OR next `/lazy-batch` invocation. **Same shape** in both. | passive halt — same as workstation, with cloud-specific path reordering: in-session resume primary, ② durable fallback, ① gitignored/non-durable, ③ workstation-only. |
| Decision-resume mode (Step 1g) | `terminal_reason: needs-input` — **NOT a halt** in either variant. AskUserQuestion → append Resolution → commit → dispatch Sonnet apply-resolution subagent (edits SPEC/PHASES, neutralizes sentinel **by RENAME** to `NEEDS_INPUT_RESOLVED.md` — a `kind:` flip leaves the halt firing) → return to Step 1a. **Same shape** in both. | same shape as workstation. SPEC/PHASES edits are docs-only, no cloud limitations apply. |
| Blocked-resolution mode (Step 1h) | `terminal_reason: blocked` — **NOT a halt by default** in either variant (was a divergence; now mirrored). Re-print BLOCKED.md body → AskUserQuestion the path (add a phase / defer to queue tail / halt-for-manual / custom) → append `## Resolution` → commit → dispatch Opus apply-resolution subagent (enacts via `/add-phase` or queue reorder, neutralizes BLOCKED.md **by RENAME**) → return to Step 1a. Only "Halt for manual fix" STOPs. **Same shape** in both. | same shape as workstation — the mode is docs-only (no Tauri/MCP), so it runs identically in cloud; the only nuance is the apply subagent pushes immediately for container-reclaim durability. |
| Park mode — `--park-blocked` + `queue-exhausted-all-parked` (bug park-mode-halts-on-blocked) | `--park` appends BOTH `--park-needs-input` AND `--park-blocked` to every probe; a feature-local `BLOCKED.md` is parked into `parked[]` (not Step-1h-resolved inline) and the queue advances; an all-parked queue returns the distinct `queue-exhausted-all-parked` terminal (flush-then-STOP); §1c.6 park wording branches on `sentinel_kind`. **Same shape** in both. | **NO cloud divergence** — park is environment-agnostic (the flush + resolution affordance are docs-only). Identical to workstation. Recorded here per the coupled-pair rule; no `--cloud` delta. |
| Operator-directed halt-resolution (Step 1i) | `completion-unverified` / `needs-spec-input` / `stale_upstream` — **NOT bare-STOPs anymore** in either variant (was a divergence; now mirrored). Routed through the shared `_components/halt-resolution.md`: re-print obstacle → AskUserQuestion (reopen & re-validate / provide direction / defer & continue / halt-for-manual / custom) → enact via Opus subagent → continue. Only "Halt for manual fix" STOPs. **Same shape** in both. | same shape as workstation — docs-only enactment, no cloud limitations; apply subagent pushes immediately for reclaim durability. |
| Post-cycle input audit (Step 1d.5) | **MIRRORED** — after every `/spec` or `plan-feature` cycle, dispatch a dedicated Opus input-audit subagent that reads SPEC.md / RESEARCH.md / cycle diff, independently re-classifies every decision against the product-behavior smells checklist (aggressive bias), verifies the cycle subagent's Decision-Classification Ledger, and writes `{spec_path}/NEEDS_INPUT.md` if any product-behavior calls were baked in silently. The auditor is scope-restricted to writing the sentinel — no source/test edits, no recursive dispatch. Surfaced decisions resolve inline on the next cycle via Step 1g (no loop halt). **Same shape** in both. | same as workstation — auditor is docs-only and dispatched by the orchestrator (which retains `Agent` even though the cycle subagent's cloud-override removes it). Sentinel commit + push folds into guardrail B / C. |
| In-Session Resume Protocol (Step 5) | chat-driven resume path for research uploads. User uploads research in next message → assistant materializes into staging dir → dispatches `/ingest-research` Sonnet subagent in-session → re-invokes `/lazy-batch` automatically. **Same shape** in both. | same shape as workstation, with the cloud-durability framing: in-session ingestion is the only path that writes tracked files (RESEARCH.md + RESEARCH_SUMMARY.md) before cloud-container reclaim. Re-invocation uses `/lazy-batch-cloud`. |
| Pre-loop ingest check (Step 0.5) | probes `docs/gemini-sprint/results/` at session start; dispatches `/ingest-research` as cycle 1 if staged `.txt` exists. **Same shape** in both. | same as workstation — `/ingest-research`'s hard constraints make it docs-only and cloud-safe. |
| Ad-hoc enqueue (Step 0.45, `--adhoc`) | **MIRRORED (shared component `_components/adhoc-enqueue.md`)** — when `--adhoc` is supplied, a one-time pre-loop bootstrap calls `lazy-state.py --enqueue-adhoc` (Bash) to prepend the referenced work to `queue.json`, seed `ADHOC_BRIEF.md`, and add a ROADMAP row; the first cycle's commit+push carries the bootstrap files. | same shared component + trigger, PLUS an immediate `git push` of the bootstrap right after enqueue (folds into guardrail B's per-batch push) so the new queue entry + brief survive container reclaim before the first cycle commits. |
| Resume-time remote sync (Step 0.4, guardrail A) | **MIRRORED** — `git fetch origin <branch>` + `git merge --ff-only` before the first state probe; halt-on-divergence (no clobber). Workstation framing: a resumed/interrupted session, or a remote advanced by another machine, can leave local behind. **Same shape** in both. | same algorithm; cloud framing is container-reclaim → stale local snapshot. This is the load-bearing recovery for the reclaim-mid-cycle data-loss mode. |
| In-cycle batch-level push (guardrail B) | **CLOUD-SCOPED DIVERGENCE — not mirrored.** Workstation cycle subagents already push at end-of-cycle (Step 1d "commit … and push to the current branch"), and local commits survive an interrupted workstation session, so per-batch (vs per-cycle) push granularity buys no durability on a persistent disk. | cycle subagent prompt (Step 1d) requires `git push origin <work-branch>` after EACH batch / work-unit commit (4× backoff retry, work-branch only, never main/force) — including the per-WU checkbox-tick commits (see "Early + granular plan-part status" row). Shrinks reclaim-loss exposure from "entire cycle runtime" to "one batch" — acute only because the cloud container is ephemeral and reclaim-prone. |
| Post-cycle push backstop (guardrail C) | **MIRRORED** — after every cycle (real-skill Step 1e AND inline pseudo-skill Step 1c.5) the orchestrator pushes / verifies-up-to-date the work branch (4× backoff, work-branch only). A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 holds. **Same shape** in both. | same as workstation; on cloud it is the backstop behind guardrail B's per-batch pushes (normally a no-op "up to date"). |
| Early + granular plan-part status (Ready → In-progress before WU work; per-WU checkbox ticks; prefer parseable `- [ ]` WUs) | **MIRRORED (shared)** — `/lazy-batch` Step 1d cycle prompt requires the dispatched skill to flip the plan part `status:` `Ready` → `In-progress` and commit BEFORE starting WU work, tick + commit each `- [ ]` → `- [x]` checkbox as the WU lands, and prefer parseable checkbox-per-WU authoring so an interrupted session resumes per-WU. Helps both environments. **The per-commit PUSH of each flip/tick is cloud-only** (workstation relies on end-of-cycle push + local-commit survival). | same shared status-flip + checkbox-tick discipline, PLUS each flip/tick is pushed immediately (folds into guardrail B's per-WU push) so the granularity survives container reclaim, not just interruption. |
| Resume-reconciliation step (Step 0.6) | **CLOUD-SCOPED DIVERGENCE — not mirrored.** A killed/interrupted workstation session keeps its local commits and dirty tree on persistent disk, and Step 0.4's ff-sync covers the remote-advanced case; there is no reclaim residue to reconcile. | new Step 0.6, mandatory every invocation and after any `SessionStart:resume`: (a) push unpushed commits; (b) read-only `lazy-state.py --cloud` probe; (c) detect "finished-but-not-finalized" (WUs committed/pushed but frontmatter still Ready/In-progress) and handle with a SHORT finalize dispatch instead of full re-execution; (d) reconcile a killed agent's dirty working tree (keep + finish correct partial work, never wholesale-discard). |
| No waiting on dead notifications (HARD CONSTRAINT 10) | **CLOUD-SCOPED DIVERGENCE — not mirrored.** No container-reclaim boundary exists on workstation, so a background cycle agent's completion notification is never lost; the concept does not apply. | new HARD CONSTRAINT 10: after any `SessionStart:resume` the orchestrator MUST treat an in-flight background cycle agent as "unknown — reconcile from git + lazy-state" (Step 0.6), never "still running, awaiting notification." A completion notification cannot cross a reclaim boundary. This is the OPPOSITE of HARD CONSTRAINT 7 (forbids passively blocking on a dead signal), not a violation of it. |
| Hook machinery (run marker, inject hook, validate-deny guard) | **MIRRORED** — `--run-start` writes the run marker at Step 0.55 (activates inject + validate-deny hooks); `--run-end` deletes it on every terminal/halt path; all non-cycle dispatches emitted via `--emit-dispatch <class>` and consumed verbatim. Counters persisted in marker; inject hook reads them without CLI flags. | **CLOUD-SCOPED DIVERGENCE (partial):** `--run-start` passes `--cloud` flag (workstation does not); the marker field `cloud=true` lets hooks select cloud-mode behavior. Everything else — `--run-end` at every terminal, LAZY-ROUTE banner check in Step 1a, `--emit-dispatch` for non-cycle dispatches, no `--forward-cycles`/`--meta-cycles` on probe — is **identical** in both. |
| `export LAZY_ORCHESTRATOR=1` at Step 0.55 (C3 self-immunity signal — cycle-subagent-runs-orchestrator-work P1) | **MIRRORED (shared)** — both orchestrators export `LAZY_ORCHESTRATOR=1` for the session immediately before `--run-start`, so `refuse_if_cycle_active` / `refuse_cycle_marker_mutation_if_subagent` (lazy_core priority 1) grant the orchestrator structural immunity to its own live cycle marker, and the var's ABSENCE marks a subagent. NOT a divergence. | same export, identical placement and rationale. |

All other behavior is identical — coupling is enforced by the state script (one source of truth), not by duplicated prose between the two orchestrators. Step 1c.5 (inline pseudo-skill handling) is shared shape; only the set of pseudo-skills emitted by the state script differs. Step 1f, Step 1g, Step 1h, and Step 1i are also shared shape; both orchestrators reach them via the same state-script terminal reasons. The blocked / needs-input / completion-unverified / needs-spec-input / stale_upstream handling is now the SAME in both (docs-only resolution modes); the only legitimate cloud divergences are the Tauri/MCP deferral, `DEFERRED_NON_CLOUD.md` + `__write_deferred_non_cloud__`, the 3-gate `__mark_complete__`, `__flip_plan_complete_cloud_saturated__`, cloud reclaim recovery (Steps 0.4 / 0.6, guardrails B/C, HARD CONSTRAINT 10), and per-batch/per-WU immediate pushes.

---

## State Machine Summary

`/lazy-batch-cloud` is the cloud mirror of the unified driver for the feature AND bug pipelines (unified-pipeline-orchestrator Phase 2). Each cycle probes the merged head (`lazy-state.py --cloud --next-merged`) and type-dispatches:

| Merged-head `type` | Cycle state script | Per-item lifecycle source | Terminal pseudo-skill | Completion receipt |
|--------------------|--------------------|---------------------------|-----------------------|--------------------|
| `feature` | `lazy-state.py --cloud` | `docs/features/` | `__write_deferred_non_cloud__` at Step 9 (defers MCP); `__mark_complete__` (`COMPLETED.md`) only once a workstation produced `VALIDATED.md` | `COMPLETED.md` |
| `bug` | `bug-state.py --cloud` | `docs/bugs/` (`--bug-id` scoping) | `__mark_fixed__` (bug validation is docs-only — reachable in cloud) | `FIXED.md` |

- **Ordering is script-owned** (`lazy_core.merged_priority`; equal priority → bug before feature). This skill consumes the head only — it never re-implements ordering.
- **No new state-machine logic in the skill.** Both state machines + gates run unchanged; the merged probe is the sole addition. `--cloud` is the only delta from `/lazy-batch` — the merged-view branch itself is NOT a cloud divergence.
- **No-regression.** A single-type queue drives the same cycle sequence as the pre-unification per-type batch. Asserted by `lazy_parity_audit.py --merged-view` + a single-type fixture.
- **Coupled pair.** Mirrors `/lazy-batch`'s State Machine Summary; see the **Differences from `/lazy-batch`** table for the merged-view-dispatch row and CLAUDE.md → Coupled Skill Pairs.
- **Checkpoint-resume counter semantics (two classes).** A checkpoint records `operator_authorized`. An operator-authorized resume starts a fresh `0/0` budget (`restore_checkpoint_counters` no-ops); an automatic reliability resume (and pre-fix files) carries counters forward monotonically (HARD CONSTRAINT 8). **Cloud-specific:** the unattended-checkpoint arm writes checkpoints WITHOUT `--operator-authorized` for both reliability triggers, so a cloud checkpoint resume ALWAYS carries forward — a cloud "fresh budget" comes only from a brand-new `/lazy-batch-cloud <N>` with no checkpoint on disk. Mirrors `/lazy-batch`'s Step 1f two-class rule (the cloud-always-carry-forward specialization is the documented divergence).

---

## Notes

- Coupling rule from CLAUDE.md: `/lazy-batch` ↔ `/lazy-batch-cloud` are coupled the same way `/lazy` ↔ `/lazy-cloud` are. Changes to one MUST be mirrored in the other unless explicitly cloud-scoped per the table above.
- The orchestrator never invokes the work-log tool directly. Cycle subagents log their own work.
- No persistence layer — restart is free. Sentinel files capture all durable state.
- **Hook machinery (Phase 5 — turn-routing-enforcement):** `--run-start --cloud` (Step 0.55) writes the run marker with `cloud=true`, activating the inject hook (`lazy-route-inject.sh`) and the validate-deny guard (`lazy-dispatch-guard.sh`) for the session. `--run-end` deletes the marker AND the prompt registry on every terminal/halt path (§1c.6 item 2). When a `LAZY-ROUTE (hook-injected, turn N):` banner is present in the session context, Step 1a MUST use the injected probe JSON and skip the explicit probe call (re-probing advances counters twice). All non-cycle Agent dispatches (input-audit, recovery, apply-resolution, coherence-recovery, investigation, hardening) are emitted via `--emit-dispatch <class>` and consumed **VERBATIM** — the emit registers the prompt in the prompt registry so the validate-deny guard will allow it. A hardening dispatch is the self-repair signal for misroute, no-route, and inject-hook errors; depth is hard-capped at 1 (§1d.1). Counters (`forward_cycles`, `meta_cycles`) are persisted in the marker; never pass `--forward-cycles`/`--meta-cycles` on probe invocations.
- **Cycle-containment machinery (lazy-cycle-containment — C1/C2/C3):** EVERY `Agent` dispatch (real cycle §1d + every meta-dispatch) is bracketed: `lazy-state.py --cloud --cycle-begin --feature-id <id> --nonce <hex> [--kind real|meta]` IMMEDIATELY before, `lazy-state.py --cloud --cycle-end` IMMEDIATELY after on EVERY return path (success / halt / error). The begin writes the cycle-subagent marker (`~/.claude/state/lazy-cycle-active.json`); while it is present the C2 PreToolUse hook (`lazy-cycle-containment.sh`) DENIES in-flight the ops a runaway needs (next-route probe/emit, run-lifecycle, 2nd-feature commit, recursive `Agent`) and the C3 state-script refusals reject `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc`/`--emit-dispatch` (exit 3, zero side effects). The orchestrator clears the marker before its own next ops, so the refusal bites ONLY a subagent calling them mid-dispatch. The bracket is IDENTICAL to `/lazy-batch` — `--cloud` is the only delta (the same `--cloud` already carried on every state-script call); it is NOT a behavioral divergence.

<!-- COUPLED-PAIR DIFF (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud) — Phase 5 turn-routing-enforcement
     This file: lazy-batch-cloud/SKILL.md

     Differences from lazy-batch (workstation):
     - Step 0.55 --run-start: passes --cloud flag (lazy-batch does not)
     - Step 0.6: resume-reconciliation step (cloud-only, not mirrored)
     - HARD CONSTRAINT 10: no waiting on dead notifications (cloud-only)
     - In-cycle batch-level push (guardrail B): cloud-only
     - State script: always --cloud flag on all invocations
     - cloud-queue-exhausted: normal terminal (workstation: defensive)
     - __write_deferred_non_cloud__, __write_validated_from_results__, __flip_plan_complete_cloud_saturated__: cloud-specific pseudo-skills
     - Investigation triggers: record + defer (not dispatch) — /investigate is workstation-class
     - --run-end, LAZY-ROUTE banner check, --emit-dispatch, no --forward-cycles/--meta-cycles: IDENTICAL in both
     - C1 --cycle-begin/--cycle-end dispatch bracket (lazy-cycle-containment §1d): IDENTICAL in both — --cloud is the only delta (already carried on every state-script call), NOT a behavioral divergence
     - C8 governing-file reload discipline + auto-refresh boundary + new-hook restart surfacing (§1d): IDENTICAL in both

     Differences from lazy-bug-batch:
     - Uses lazy-state.py (not bug-state.py)
     - pipeline=feature (not bug)
     - feature/feature_name/feature_id terminology (not bug)
     - all-features-complete / cloud-queue-exhausted terminals (not all-bugs-fixed)
     - Steps 0.4, 0.6 (cloud reclaim recovery) are cloud-only additions
-->

<!-- COUPLED-PAIR DIFF (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud) — Phase 7 turn-routing-enforcement
     Mirrored identically with lazy-batch / lazy-bug-batch (cloud keeps --cloud on every state-script call;
     the WU-7.4 checkpoint arm lives at Step 0.55 here since cloud has no standalone Step 0 budget block,
     and is framed as the cloud-default-unattended case):
       - WU-7.1: §1d.1 "Pending hardening debt" — pending_hardening>0 ⇒ FIFO emit+dispatch before any
         forward route; --run-end refuses on unacked denials; --ack-unhardened operator-only.
       - WU-7.2: §1d.1 Depth-cap split into shape-(a) recipe denial (one verbatim re-dispatch, fresh
         nonce) vs shape-(b) halt-reason / second-recipe denial (existing halt). Never a 3rd.
       - WU-7.3c: §1d "Continuation cycles re-emit" gained the Freshness rule (no cross-turn dispatch —
         reclaim/SessionStart:resume boundaries called out; --context slots the only customization point).
       - WU-7.4: Step 0.55 gained the unattended-checkpoint arm + resumed_from_checkpoint surfacing
         (--cloud --run-end --reason checkpoint --next-route + PushNotification + T7 trigger).
       - WU-7.5c: Step 1e — PushNotification("spun off {id} — {reason}") + D7 digest on any cycle return
         reporting a spin-off. -->
<!-- Phase 8 (turn-routing-enforcement, 2026-06-12) — coupled-pair mirror note:
       - WU-8.2/8.3: §1d.1 "Pending hardening debt" rewritten — probe WITHHOLDS the forward route
         (route_overridden_by + hardening_emit_command); ack moved to guard-allow time (emission
         no longer acks); full-probe-JSON consumption rule (field-extractor piping BANNED).
       Mirrored verbatim across lazy-batch / lazy-bug-batch / lazy-batch-cloud (cloud keeps
       lazy-state.py --cloud paths). Script contract: lazy_core.py read_run_marker path B is now
       non-destructive (concurrent interactive sessions never delete a live run's marker). -->
<!-- lazy-cycle-containment Phase 5 (2026-06-15) — coupled-trio mirror note:
       - C1 dispatch bracket: §1d "Cycle-marker dispatch bracket" — lazy-state.py --cloud --cycle-begin
         IMMEDIATELY before every Agent dispatch (real + every meta-dispatch), --cloud --cycle-end
         IMMEDIATELY after on EVERY return path. IDENTICAL to /lazy-batch — --cloud is the only delta.
       - C8 governing-file reload discipline + auto-refresh boundary + new-hook restart surfacing
         (§1d): authored canonically in lazy-batch (Phase 1); MIRRORED here in this Phase-5 cycle.
       - Hook-machinery Note: added the C1/C2/C3 cycle-containment bullet; Differences table updated.
       Mirrored across all three; cloud passes --cloud; the bug orchestrator brackets with bug-state.py.
       The bracket itself is NOT a cloud divergence (identical shape). -->

