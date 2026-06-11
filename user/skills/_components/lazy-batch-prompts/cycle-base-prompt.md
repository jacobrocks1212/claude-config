# lazy-batch cycle subagent — base prompt template

<!-- Verbatim cycle dispatch prompt for /lazy-batch workstation cycles.
     Bind {feature_name}, {feature_id}, {cwd}, {current_step},
     {sub_skill}, {sub_skill_args} before dispatch.
     Append the LOOP DETECTED block (loop-block.md) AFTER the final paragraph
     when the loop-guard fires (prev_cycle_signature == current signature).
     Do NOT include the loop block on the first cycle or when signatures differ. -->

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

Sub-subagent dispatch policy (INLINE OVERRIDE — LOAD-BEARING):
  This subagent does NOT have the `Agent` tool — you CANNOT spawn further
  sub-subagents from inside this cycle. Any Agent() call you attempt will fail
  (tool unavailable) and waste the cycle. (Recursive sub-subagent dispatch is
  not supported from inside a dispatched subagent, on workstation as in cloud.)

  Therefore, regardless of what the dispatched skill's SKILL.md says about
  spawning sub-subagents (test-agent, impl-agent, research subagents A–G,
  etc.), you MUST perform that work INLINE in this subagent session using
  Edit / Write / Read directly. The cycle subagent SUPERSEDES the dispatched
  skill's sub-subagent dispatch contract — this is the documented inline
  override, not a hard contract violation. The only prohibition you still
  carry is "no parallel pipeline orchestrators" (do NOT invoke another /lazy
  or /lazy-batch).

  Per-skill inline overrides (override the SKILL.md dispatch contract):
    • /execute-plan — IGNORE Step 3's "Execution Model Enforcement". Do NOT
      attempt Agent({model: "sonnet"}) test-agent / impl-agent dispatches.
      Perform each batch's test additions and implementation edits INLINE
      with Edit / Write / Read on source/test files directly
      (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files included).
      Follow the rest of /execute-plan as written (batch ordering, commits,
      plan-file checkbox flips, sentinel emissions). Zero sub-subagent
      dispatches in an /execute-plan cycle is the EXPECTED state — NOT a
      contract violation.
      ATOMIC GATE+COMMIT (HARD): per /execute-plan's "Atomic gate+commit"
      rule, the FINAL action of each batch AND of plan-part completion MUST be
      ONE chained Bash command — `<gate> && git add -A && git commit -m "..."
      && git push` — so the auto-backgrounded gate job commits + pushes itself.
      This closes the turn-loss gap (the recurring failure where the cycle ends
      between "gates passed" and "commit", leaving the tree dirty or the dual
      ledger half-flipped). Before reporting, tick EVERY PHASES.md verification
      box for the completed phase(s) and confirm `git status --short` is empty.
      SKIP THE GROUND-TRUTH RE-RUN: subagent-review.md Step 1.5 exists to
      detect a *separate* untrusted subagent falsifying its report by
      re-running every command (git status / wc -l / grep / test runner) and
      diffing. In this inline path YOU wrote both the tests and the
      implementation in this same session — there is no separate subagent
      report to police, so that mechanical re-run is pure redundant work. Do
      NOT re-run-and-diff your own commands. Still perform the SUBSTANTIVE
      correctness review (spec alignment, deliverable coverage, logic/edge-case
      check, propagation check per subagent-review.md Step 2.5) and still run
      the quality gates — only the falsification-detection re-run is dropped.
      KNOWN LIMITATION: collapsing the test-agent/impl-agent split into one
      inline session trades away the STRUCTURAL test-first guarantee. You MUST
      still preserve test-first DISCIPLINE within each batch: write the failing
      tests FIRST (per the plan's test expectations), confirm they fail for the
      right reason, THEN implement until they pass.
    • /retro — IGNORE Step 3's parallel research-subagent fanout (A–G). Do the
      research INLINE: read each input serially, synthesize, and write the
      retro plan + RETRO_DONE.md directly. The deliverable is identical; only
      the parallelism is dropped.
    • /mcp-test — perform the Step 5 test work INLINE (read the MCP usage
      guide, run the MCP HTTP tools yourself, analyze the session logs) rather
      than dispatching a Sonnet test subagent. Workstation retains the Tauri
      runtime + MCP HTTP server, so the runtime work itself is unchanged — only
      the sub-subagent dispatch is replaced with inline execution.
      RUNTIME IS ALREADY UP (orchestrator-managed): the orchestrator pre-booted
      `npm run dev:restart` and BLOCKED on `GET http://localhost:3333/health`
      == 200 in its own long-lived session BEFORE dispatching you (Step 1d.0).
      The dev runtime + MCP HTTP server on :3333 are therefore ALREADY RUNNING
      and MCP-ready. Do NOT run `npm run tauri:dev` / `npm run dev:restart` and
      do NOT `npx kill-port`/restart the server. SKIP mcp-test SKILL.md Step 2
      (Server Lifecycle) and the Step 4 health-poll: treat `server_was_running`
      as true and connect directly to the already-running server — start at the
      Step 4 *readiness* check (session-events / sidecar / smoke test), which is
      a fast in-turn verification against the live server, not a boot wait.
      Re-resolve any session-log dir from the live server (GET
      /tools/get_session_meta → log_dir); NEVER reuse a cached `logs/session-*`
      path (HARD REQUIREMENT, docs/development/CLAUDE.md).
      INLINE-FIX POLICY (D5 — LOCKED): while validating you MAY fix a
      production-code bug inline, but ONLY test-first and fully disclosed:
        1. Write the failing test FIRST — confirm it reproduces the bug and
           fails for the right reason — THEN apply the fix.
        2. Disclose the production-code change explicitly in your cycle summary:
           which files changed, what changed, and which test pins it.
        3. A cycle that modified production code MUST NOT write `VALIDATED.md`.
           Even if the MCP run now passes, end the cycle WITHOUT `VALIDATED.md`:
           write `MCP_TEST_RESULTS.md` (recording the run and flagging that
           production code changed this cycle, so it needs re-verification) or
           `BLOCKED.md` if the fix is incomplete. This puts the cycle in a
           needs-re-verify state.
        4. Only a subsequent CLEAN `/mcp-test` cycle — one that made NO
           production-code edits — may write `VALIDATED.md`. That cycle re-runs
           MCP against the now-unchanged code and, if it passes cleanly,
           certifies via `VALIDATED.md`. Rationale: a cycle that both changed
           the code AND self-certified it has validated its own un-reviewed
           change — the exact self-certification side-door this policy closes.
      NO FIRE-AND-FORGET (CONTRACT — a resultless return is a violation): you
      MUST NOT start any long build/process as a background task and then end
      your turn waiting on background events. You either (a) connect to the
      orchestrator-managed running runtime and drive the validation to a
      DEFINITIVE pass/fail WITH a written sentinel within THIS turn, or (b) if
      you must wait on anything (e.g. readiness re-check, sidecar connect), use
      a BLOCKING foreground wait (a `curl`/`sleep` `until`-loop, or a Monitor
      you await) — never end the turn on a pending background `run_in_background`
      job. Before returning you MUST have written the contract result sentinel
      (`VALIDATED.md` on full pass — UNLESS you modified production code this
      cycle, in which case write `MCP_TEST_RESULTS.md` / `BLOCKED.md` and let a
      subsequent clean cycle certify / `MCP_TEST_RESULTS.md` on partial /
      `DEFERRED_REQUIRES_DEVICE.md` per Step 4.5 / `SKIP_MCP_TEST.md` per the
      mcp-testing SPEC) OR a `BLOCKED.md` naming a CONCRETE blocker. Returning
      with no sentinel and no result is a contract violation that wastes the
      whole cycle — do not do it.
    • retro-feature — composed orchestrator; same override — perform all
      internal work inline rather than dispatching nested sub-subagents.
    • plan-feature — composed orchestrator; runs /spec-phases THEN /write-plan
      via the Skill tool (in-context, NOT Agent dispatch). Both sub-skills are
      docs-only (PHASES.md + plan files) and orchestrator-only, so no recursive
      Agent dispatch is needed — invoke /plan-feature once and let it run its
      two sub-skills in your context. This is what lazy-state.py emits at
      Step 6 (replacing the separate /spec-phases dispatch).
    • /spec, /spec-phases, /write-plan, /add-phase, /ingest-research —
      already orchestrator-only; no change.

  If you find yourself about to write Agent({...}) inside this cycle, STOP and
  replace it with the equivalent Edit / Write / Read sequence. Do NOT write
  BLOCKED.md because of the recursive-dispatch limit — that limit is exactly
  what this override exists to handle.

  The dispatched skill's own SKILL.md remains authoritative for everything
  else: batch ordering, sentinel emissions, commit policy, file-shape
  invariants, plan-checkbox semantics. Re-read it from disk if any
  non-dispatch detail is unclear — do NOT rely on memory.

Source/test file edits:
  - All paths: perform Edit / Write on source/test files
    (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files) DIRECTLY in this
    subagent session. The inline override above removes the /execute-plan
    sub-subagent dispatch requirement and replaces it with inline edits.

No premature Complete (PIPELINE-GATE HONESTY — HARD REQUIREMENT):
  - You MUST NOT set the top-level `**Status:**` of SPEC.md or PHASES.md to
    `Complete`. That flip is reserved EXCLUSIVELY for the orchestrator's
    `__mark_complete__` pseudo-skill, which runs ONLY after the feature has
    passed the full downstream tail: /retro (writes RETRO_DONE.md) → /mcp-test
    (writes VALIDATED.md or a justified SKIP_MCP_TEST.md) → the __mark_complete__
    MCP-coverage audit. If a phase-implementation cycle flips SPEC/PHASES
    `**Status:** Complete` itself, the feature has NO COMPLETED.md receipt, so
    lazy-state.py Step 2 now HARD-HALTS on `completion-unverified` instead of
    advancing — your rogue flip does not skip the tail, it stops the whole loop
    until a human reconciles. (Previously this silently skipped /retro +
    /mcp-test + the coverage audit; the receipt gate is the mechanism that makes
    this guard self-enforcing rather than honor-system.) Do NOT write a
    COMPLETED.md yourself either — only the orchestrator's __mark_complete__
    integrity gate may, after the validation tail passes.
  - What you MAY flip when an /execute-plan part finishes: the PLAN-PART
    frontmatter `status:` (Ready → In-progress → Complete) and the per-PHASE
    checkboxes/`Status:` line for the phase you just implemented (e.g. Phase 3
    deliverables → checked, that phase → Complete). When the last phase's work
    lands, set the top-level PHASES `**Status:**` to `In-progress` (NOT
    `Complete`) — implementation is done but validation is still pending. The
    feature reaches `Complete` only through __mark_complete__.
  - If you believe the feature is genuinely finished and validated, STILL do not
    flip the top-level Status — let the state machine route to /retro and
    /mcp-test next. Those passes are cheap insurance, and __mark_complete__'s
    coverage audit is the single authorized place the SPEC flips to Complete.

Plan-part status + per-WU granularity (RESUME SAFETY):
  To make an interrupted cycle resume cleanly instead of redoing a whole plan
  part, keep the plan part's on-disk status and per-WU checkboxes accurate AS
  THE WORK LANDS, not only at end-of-cycle:
    • For /execute-plan (and any /retro / realign cycle that mutates a plan
      part): the dispatched skill MUST flip the plan part frontmatter `status:`
      `Ready` → `In-progress` and commit it BEFORE starting work-unit work, and
      tick each `- [ ]` → `- [x]` checkbox + commit as that work-unit lands. An
      interrupted session then resumes at the first still-unchecked box with
      accurate In-progress state instead of redoing the part from a stale
      `Ready`.
    • Prefer plan work-units authored as parseable `- [ ]` markdown checkboxes
      (one per WU) so resume granularity is per-WU, not per-part. If a part is
      prose-only, note it in your summary so it can be re-authored with
      checkboxes.
  (On workstation, local commits survive an interrupted session, so the
  end-of-cycle push in the commit step below is sufficient durability — pushing
  each flip/tick immediately is a cloud-only requirement in /lazy-batch-cloud.)

Sentinel + git hygiene (HARD — prevents the recurring subagent deviations):
  - CANONICAL SENTINEL FILENAMES: when you write a pipeline sentinel, use the
    EXACT canonical filename — never a variant (lowercased, abbreviated,
    pluralized, or otherwise renamed). A mis-named sentinel is invisible to
    lazy-state.py / bug-state.py and silently breaks the gate, looping the
    pipeline. Canonical set:
      BLOCKED.md · NEEDS_INPUT.md · NEEDS_RESEARCH.md · RETRO_DONE.md ·
      VALIDATED.md · MCP_TEST_RESULTS.md · SKIP_MCP_TEST.md · COMPLETED.md ·
      FIXED.md · DEFERRED_NON_CLOUD.md · DEFERRED_REQUIRES_DEVICE.md
    Re-read ~/.claude/skills/_components/sentinel-frontmatter.md for the exact
    name + frontmatter schema before writing any sentinel — do NOT rely on
    memory of the filename. (FIXED.md is bug-pipeline only; COMPLETED.md is
    feature-pipeline only — use the one for your pipeline.)
  - WORK-BRANCH-ONLY COMMITS: every commit and push goes to the CURRENT work
    branch ONLY. NEVER commit or push to main / master, NEVER --force /
    --force-with-lease, NEVER create a new branch. If `git rev-parse
    --abbrev-ref HEAD` shows main / master, STOP and report rather than
    committing — do not "fix" it by branching.

After the skill returns:
  1. If a commit policy file exists at .claude/skill-config/commit-policy.md,
     follow it. Otherwise commit per the standard pattern and push to the
     current branch. Skip commit only if the skill produced no file changes.
  2. Report a one-paragraph summary: what state was advanced, files modified,
     commit hash (or "no commit"), and any issues. Keep it under 8 lines so the
     orchestrator's per-cycle log stays compact. If you ran /execute-plan,
     CONFIRM you performed the test + implementation edits INLINE (zero Agent()
     calls) — this is the inline-override audit signal, and note for each batch
     that you wrote the failing tests before implementing (test-first
     discipline).
```
