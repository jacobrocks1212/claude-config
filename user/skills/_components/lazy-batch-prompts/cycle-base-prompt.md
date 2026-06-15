# lazy-batch cycle subagent — sectioned base prompt template

<!-- SECTIONED, DEDUPLICATED, PARAMETERIZED cycle-dispatch template.

     This file is NOT bound by hand. The Python emitter
     (`lazy_core.emit_cycle_prompt`) parses the `@section` markers below,
     selects sections by (pipeline, mode, sub_skill), binds the tokens, and
     assembles the final cycle prompt. Everything BEFORE the first `@section`
     marker is template metadata (this HTML comment header) and is NEVER
     emitted.

     ── SECTION MARKER GRAMMAR (the emitter parses exactly this) ────────────
     A marker line, alone on its own line:
       <!-- @section <name> pipelines=<feature|bug|feature,bug> modes=<workstation|cloud|workstation,cloud> skills=<all|csv-of-skill-names> -->
     Optional extra attribute on mcp-test variant sections only:
       variant=runtime-up   |   variant=no-runtime
     A section's content runs from the line AFTER its marker to the line
     BEFORE the next marker (or EOF). Skill names in `skills=` are bare (no
     leading slash): execute-plan, retro, retro-feature, mcp-test.

     ── SELECTION SEMANTICS (for the emitter author) ───────────────────────
     Include a section IFF:
       pipeline matches  AND  mode matches  AND
       (skills=all  OR  the dispatched sub_skill — normalized without a
        leading "/" — is in the skills csv).
     Sections carrying a `variant=` attribute are ADDITIONALLY filtered: for a
     mcp-test cycle the emitter picks EXACTLY ONE variant, chosen by the spec's
     PHASES.md `**MCP runtime:**` line (`not-required` → variant=no-runtime,
     else variant=runtime-up). Sections are emitted in FILE ORDER, joined by a
     single blank line.

     ── TOKENS (bound by the emitter — use ONLY these) ─────────────────────
     {item_label} (Feature|Bug) · {pipeline_phrase} ("feature pipeline"|"bug
     pipeline") · {item_name} · {item_id} · {cwd} · {current_step} ·
     {sub_skill} · {sub_skill_args} · {spec_path} · {work_branch} ·
     {receipt_name} (COMPLETED.md|FIXED.md) · {mark_pseudo}
     (__mark_complete__|__mark_fixed__) · {forbidden_status} ("Complete"|"Fixed
     or Won't-fix") · {untestability_reason} (mcp-test no-runtime variant only).
     Any literal {…} that is NOT one of these 14 tokens is residue the emitter
     refuses on — use <angle-bracket> placeholders for non-token braces.

     ── RULE INVENTORY (each rule survives EXACTLY ONCE, in one section) ────
     R1  batch mode .............................. section: task
     R2  D7 completeness-first ................... section: d7
     R3  inline override (no Agent tool) ......... section: inline-override
     R4  test-first within each batch ........... section: skill-execute-plan
     R5  atomic gate+commit (chained command) ... section: turn-end (referenced by skill-execute-plan)
     R6  substantive review, skip falsification . section: skill-execute-plan
     R7  status honesty (no premature flip) ..... section: status-honesty
     R8  resume safety (plan-part + per-WU) ...... section: resume-safety
     R9  canonical sentinel filenames ........... section: hard-contract (item 1)
     R10 work-branch-only commits ............... section: hard-contract (item 2)
     R11 after-the-skill commit policy .......... section: hard-contract (item 3)
     R12 report contract (no sha) ............... section: hard-contract (item 4)
     R13 turn-end contract ...................... section: turn-end
     R14 mcp-test rules ......................... sections: skill-mcp-test-common + variant sections
     R15 loop block (separate file) ............. loop-block.md (appended by emitter)
     R16 cloud deltas ........................... section: cloud-override (+ commit-push folded into hard-contract item 3 / turn-end via modes)

     The ONE sanctioned restatement is the pre-return checklist in `turn-end`
     (a checklist may re-walk rules; prose may not).

     ── PROVENANCE ─────────────────────────────────────────────────────────
     Workstation deltas come from this file's prior monolithic form; cloud
     deltas were folded in from lazy-batch-cloud/SKILL.md's hand-synced inline
     copy (a later WU deletes that inline copy); bug/feature differences are
     tokenized so lazy-bug-batch's substitution list + "No premature Fixed"
     block become dead. -->

<!-- @section task pipelines=feature,bug modes=workstation skills=all -->
You are advancing one cycle of the autonomous {pipeline_phrase}.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Invoke the {sub_skill} skill with args: {sub_skill_args} --batch

Operating mode: batch
  - Do NOT ask interactive questions. Skills accept --batch and either
    auto-accept a recommended option or write NEEDS_INPUT.md and halt.
  - If the skill writes NEEDS_INPUT.md, do NOT attempt to resolve the
    decision — that halt is for a human.

<!-- @section task pipelines=feature,bug modes=cloud skills=all -->
You are advancing one cycle of the autonomous {pipeline_phrase} in a CLOUD
Linux session. This container has: no Tauri desktop runtime, no MCP HTTP
server, no audio device, no Windows-only tooling, and NO persistent state
(it is reclaimed after the session).

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Invoke the {sub_skill} skill with args: {sub_skill_args} --batch

Operating mode: batch
  - Do NOT ask interactive questions. Skills accept --batch and either
    auto-accept a recommended option or write NEEDS_INPUT.md and halt.
  - If the skill writes NEEDS_INPUT.md, do NOT attempt to resolve the decision.
  - The state script (--cloud variant) already guaranteed this skill is safe
    to run in cloud (genuine cloud-runtime limits are handled per the CLOUD
    OVERRIDE below).

<!-- @section d7 pipelines=feature,bug modes=workstation,cloud skills=all -->
Completeness-first (D7 — standing policy, pre-authorized, both modes):
  Before writing NEEDS_INPUT.md for ANY decision, apply the scope test: would
  the end-state PRODUCT behavior differ between the options? If NO — they
  differ only in effort / sizing / sequencing / completeness — it is
  scope-class: take the MOST COMPLETE path IN-CYCLE and disclose it, one line
  per application:
    ⚖ policy: <decision, ≤8 words> → <chosen path>
  Silently descoping WITHOUT the ⚖ line is the violation (not a missing
  question). Reserve NEEDS_INPUT.md for PRODUCT-class decisions (options diverge
  in user-visible behavior, UX, API, or data semantics, or conflict with a SPEC
  Locked Decision). Full policy: ~/.claude/skills/_components/completeness-policy.md.

  SPIN-OFF LEGS (when this cycle spins off a bug doc or an --enqueue-adhoc
  feature for discovered out-of-scope work): both directions are mandatory.
  (1) Add a REVERSE-REFERENCE in the ORIGIN item's doc naming the spun-off
  id/path — the PHASES.md Implementation Notes, or the blocker sentinel's
  resolution body if the spin-off resolved a blocker. (2) REPORT the spin-off
  in your return summary (its id + a one-line reason) so the orchestrator fires
  a PushNotification ("spun off <id> — <reason>") and adds the D7 digest entry.
  Cross-references in BOTH directions are the contract — the new doc names its
  origin; the origin names the spin-off.

<!-- @section inline-override pipelines=feature,bug modes=workstation skills=all -->
Sub-subagent dispatch policy (INLINE OVERRIDE — LOAD-BEARING):
  This subagent does NOT have the `Agent` tool — any Agent() call fails and
  wastes the cycle. Regardless of what the dispatched skill's SKILL.md says about
  spawning sub-subagents (test-agent, impl-agent, research subagents A–G, etc.),
  perform ALL of it INLINE with Read / Edit / Write. The only surviving
  prohibition: never invoke another /lazy or /lazy-batch. Do NOT write BLOCKED.md
  because of this dispatch limit — handling it inline is what this override is
  for. The dispatched skill's SKILL.md stays authoritative for everything else
  (batch ordering, sentinels, commit policy, file-shape invariants, plan-checkbox
  semantics) — re-read it from disk if any non-dispatch detail is unclear.

<!-- @section cloud-override pipelines=feature,bug modes=cloud skills=all -->
Sub-subagent dispatch policy (CLOUD OVERRIDE — LOAD-BEARING):
  This cloud subagent does NOT have the `Agent` tool — any Agent() call fails
  and wastes the cycle. Perform ALL skill-mandated sub-subagent work (test-agent,
  impl-agent, research subagents A–G, etc.) INLINE with Read / Edit / Write. The
  only surviving prohibition: never invoke another /lazy or /lazy-batch. Do NOT
  write BLOCKED.md because of this dispatch limit (BLOCKED.md is still correct for
  genuine cloud-RUNTIME limits — Tauri, MCP, audio, Windows-only tooling — via
  blocker_kind: cloud-limitation).
  Zero sub-subagent dispatches in a cloud /execute-plan cycle is the EXPECTED state — NOT a contract violation.
  The dispatched skill's SKILL.md stays authoritative for everything else —
  re-read it from disk if unclear.

  Cloud runtime deferral: this container has no Tauri runtime and no MCP HTTP
  server, so MCP validation is DEFERRED to a later workstation pass — a cloud
  cycle never dispatches /mcp-test, and `Complete` (which asserts MCP-validated)
  is never honest here; the honest cloud terminal is `In-progress`.

<!-- @section skill-execute-plan pipelines=feature,bug modes=workstation,cloud skills=execute-plan,retro-feature -->
/execute-plan (and retro-feature's inner execute-plan loop) — inline execution:
  - TEST-FIRST PER BATCH (R4): the inline path collapses the test-agent/impl-agent
    split, so keep the discipline manually — write the failing tests FIRST,
    confirm they fail for the right reason, THEN implement until they pass. Edit
    source/test files (.ts/.js/.cs/.vue/.py/.rs/.tsx/.jsx) directly.
  - SUBSTANTIVE REVIEW, NOT FALSIFICATION RE-RUN (R6): skip subagent-review.md's
    Step 1.5 re-run-and-diff (it polices a SEPARATE untrusted subagent's report;
    you wrote the tests and code yourself). Still do the substantive review (spec
    alignment, deliverable coverage, edge cases, propagation) and run the gates.
  - ATOMIC GATE+COMMIT (R5): the final action of each batch / plan-part
    completion is the ONE chained command from the turn-end contract below.

<!-- @section skill-retro pipelines=feature,bug modes=workstation,cloud skills=retro,retro-feature -->
<!-- DORMANT — retro unwired from the autonomous pipeline 2026-06; emit_cycle_prompt never selects this section (sub_skill=retro is no longer emitted by lazy-state.py). Retained so section-lookup / residue checks remain stable. -->
/retro — inline execution:
  Do the Step 3 A–G research INLINE and SERIALLY (read each input, synthesize)
  rather than fanning out parallel research subagents; the deliverable is
  identical (the retro plan + RETRO_DONE.md when there are no significant
  divergences) — only the parallelism is dropped.

<!-- @section skill-retro-feature pipelines=feature,bug modes=workstation,cloud skills=retro-feature -->
<!-- DORMANT — retro unwired from the autonomous pipeline 2026-06; emit_cycle_prompt never selects this section (sub_skill=retro-feature is no longer emitted by lazy-state.py). Retained so section-lookup / residue checks remain stable. -->
/retro-feature — composed orchestrator, inline:
  It loops /retro + /execute-plan IN YOUR CONTEXT (via the Skill tool, NOT Agent
  dispatch) until RETRO_DONE.md is on disk, a BLOCKED.md / NEEDS_INPUT.md halt
  fires, or max-rounds is reached. Both inner skills run under the inline
  override above — perform all their internal work inline.

<!-- @section skill-mcp-test-common pipelines=feature,bug modes=workstation skills=mcp-test -->
/mcp-test — run the Step 5 test work INLINE (read the MCP usage guide, drive the
MCP HTTP tools yourself, analyze the session logs) instead of dispatching a
Sonnet test subagent. These rules apply to EVERY mcp-test cycle:
  - VALIDATED_COMMIT (REQUIRED): any MCP_TEST_RESULTS.md you write MUST carry
    `validated_commit: <git rev-parse HEAD at validation time>` (capture it when
    the run completes, BEFORE any further commits). The sha-freshness gate
    compares it to HEAD — a results file without it cannot certify the code.
    Schema: ~/.claude/skills/_components/sentinel-frontmatter.md.
  - INLINE-FIX POLICY (D5 — LOCKED): you MAY fix a production-code bug while
    validating, but ONLY (1) test-first — write the failing test FIRST, confirm
    it fails for the right reason, then fix — and (2) fully disclosed in your
    summary (files, change, pinning test). A cycle that touched production code
    MUST NOT write VALIDATED.md; end it in a needs-re-verify state
    (MCP_TEST_RESULTS.md flagging the change, or BLOCKED.md if incomplete). Only
    a SUBSEQUENT CLEAN cycle (no production edits) certifies via VALIDATED.md —
    so a cycle never self-certifies its own un-reviewed change.
  - NO FIRE-AND-FORGET: drive validation to a DEFINITIVE pass/fail WITH a written
    sentinel within THIS turn; if you must wait on anything (readiness re-check,
    sidecar connect) use a BLOCKING foreground wait — never end the turn on a
    pending background job. Before returning, the owed sentinel is on disk:
    VALIDATED.md (full pass, UNLESS you edited production code this cycle) /
    MCP_TEST_RESULTS.md (partial or production-edited) /
    DEFERRED_REQUIRES_DEVICE.md (per Step 4.5) / SKIP_MCP_TEST.md (per the
    mcp-testing SPEC) / BLOCKED.md naming a CONCRETE blocker.
  - SKIP PROVENANCE: any SKIP_MCP_TEST.md MUST carry `granted_by: mcp-test` AND
    `spec_class: <the untestable class you verified against
    docs/features/mcp-testing/SPEC.md>`. The state scripts REFUSE a pipeline skip
    that omits either field and halt for operator confirmation. Audio IS
    MCP-testable (load_test_tone + get_audio_buffer), so audio untestability
    claims are usually WRONG — cross-check the SPEC before claiming a class.
  - RECONCILE PHASES (after VALIDATED.md): walk {spec_path}'s PHASES.md and, for
    EVERY unchecked Runtime Verification row, either tick it with a brief evidence
    annotation when THIS validation run covers it, or — when it does NOT — re-scope
    it honestly (convert to a non-checkbox follow-up note, or downgrade your result
    to an MCP_TEST_RESULTS.md partial if it is genuinely a blocking gap) under a
    `⚖` disclosure line. Then flip each phase's `**Status:**` to Complete once
    nothing in it remains unchecked (per-phase flips are permitted — R7). WHY: the
    completion gate refuses an incoherent flip, so an unreconciled PHASES strands
    the feature at mark-complete.
  - SEAM ENUMERATION (escalation — when writing BLOCKED.md at retry_count >= 2):
    if the BLOCKED.md you are writing carries `blocker_kind: mcp-validation` and
    `retry_count >= 2` (this is the 2nd+ validation failure for this {item_label}),
    its body MUST include a `## Seam Enumeration` section listing EVERY boundary
    in the failing chain (user surface → sidecar/IPC → engine → final observable),
    each with a per-seam status: `probed-OK` / `probed-FAIL` / `unprobed`. You are
    already inside the live runtime — you are the cheapest enumeration point. The
    corrective phase consumes this as its seam-audit checklist so the NEXT
    validation round does not discover the next layer cold (a feature once burned
    three ~1M-token rounds peeling one layer per round).

<!-- @section mcp-test-runtime pipelines=feature,bug modes=workstation skills=mcp-test variant=runtime-up -->
RUNTIME IS ALREADY UP (orchestrator-managed): the orchestrator pre-booted the
dev runtime and BLOCKED on `GET http://localhost:3333/health == 200` in its own
session BEFORE dispatching you. The dev runtime + MCP HTTP server on :3333 are
ALREADY running and MCP-ready. Do NOT run `npm run tauri:dev` / `dev:restart`
and do NOT kill-port / restart the server. SKIP the skill's Step 2 (Server
Lifecycle) and the Step 4 health-poll — treat `server_was_running` as true and
start at the Step 4 readiness check (session-events / sidecar / smoke test), a
fast in-turn verification against the live server, not a boot wait. Re-resolve
any session-log dir from the live server (GET /tools/get_session_meta →
log_dir); NEVER reuse a cached `logs/session-*` path (HARD REQUIREMENT,
docs/development/CLAUDE.md).

<!-- @section mcp-test-runtime pipelines=feature,bug modes=workstation skills=mcp-test variant=no-runtime -->
RUNTIME NOT PRE-BOOTED (plan asserts structural MCP-untestability): this item's
PHASES.md declares `**MCP runtime:** not-required` — {untestability_reason}. The
orchestrator did NOT boot the dev runtime; no MCP HTTP server is running. That
declaration is ROUTING, not a waiver — YOU own the skip decision. FIRST verify
the assessment against docs/features/mcp-testing/SPEC.md (the genuinely
untestable classes are the "What We Cannot Prove" observation gaps and the
raw-PCM-injection-into-the-Rust-callback path; "Audio IS MCP-testable" via
load_test_tone + get_audio_buffer, so audio claims are usually WRONG).
  - CONCUR (no MCP-reachable surface exists): write SKIP_MCP_TEST.md per
    sentinel-frontmatter.md with `granted_by: mcp-test` AND `spec_class: <the
    class you verified>`, a scoped reason, and `alternative_validation` citing
    the non-MCP evidence (e.g. the cargo/vitest suites). Commit + push. Do NOT
    attempt any MCP HTTP call and do NOT boot the runtime.
  - DISAGREE (ANY MCP-testable surface exists): do NOT boot the runtime (your
    background processes die at turn end) and do NOT write any sentinel. Return
    the single line NEEDS_RUNTIME as your ENTIRE report — the orchestrator boots
    the runtime in its own session and re-dispatches you against a live server.

<!-- @section status-honesty pipelines=feature,bug modes=workstation,cloud skills=all -->
Status honesty (PIPELINE-GATE — HARD):
  Never flip the top-level `**Status:**` of SPEC.md or PHASES.md to
  {forbidden_status}, and never write {receipt_name} yourself — both are owned
  EXCLUSIVELY by the orchestrator's {mark_pseudo} gate, which fires only after
  the validation tail (/mcp-test → coverage audit). A rogue flip leaves
  no {receipt_name} receipt, so the state script HARD-HALTS on
  `completion-unverified` until a human reconciles (it does NOT skip the tail).
  You MAY flip the PLAN-PART frontmatter `status:` and the per-PHASE checkboxes /
  `Status:` line for the phase you just implemented; when the LAST phase's work
  lands, set the top-level PHASES `**Status:**` to `In-progress` (NOT
  {forbidden_status}) — implementation done, validation pending. Let the state
  machine route to /mcp-test next. (The /retro step is unwired — 2026-06.)

<!-- @section resume-safety pipelines=feature,bug modes=workstation skills=execute-plan,retro,retro-feature -->
Resume safety (plan-part + per-WU granularity):
  Keep the plan part's on-disk status accurate AS THE WORK LANDS so an
  interrupted cycle resumes at the first unchecked box: flip the plan-part
  frontmatter `status:` Ready → In-progress and commit BEFORE starting work-unit
  work; tick each `- [ ]` → `- [x]` + commit as that WU lands. Prefer parseable
  `- [ ]` checkboxes (one per WU); if a part is prose-only, say so in your summary.

<!-- @section resume-safety pipelines=feature,bug modes=cloud skills=execute-plan,retro,retro-feature -->
Resume safety (plan-part + per-WU granularity — cloud, PUSH each flip):
  A cloud cycle can be killed mid-run by a container reclaim, so keep the plan
  part's on-disk status accurate AS THE WORK LANDS and PUSH each change
  immediately (an unpushed commit is lost on reclaim): flip the plan-part
  frontmatter `status:` Ready → In-progress, then commit AND push that single
  change BEFORE starting work-unit work; tick each `- [ ]` → `- [x]` + commit AND
  push as that work-unit lands (per-WU resume granularity — a kill loses at most
  the in-flight WU). Prefer parseable `- [ ]` checkboxes (one per WU); if a part
  is prose-only, flag it in your summary. Do NOT flip the plan part to `Complete`
  when DEFERRED_NON_CLOUD.md exists and VALIDATED.md does not — `In-progress` is
  the honest cloud terminal.

<!-- @section hard-contract pipelines=feature,bug modes=workstation skills=all -->
Hard contract (sentinel + git hygiene + report):
  1. CANONICAL SENTINEL FILENAMES — write pipeline sentinels with their EXACT
     canonical names (never lowercased / abbreviated / pluralized / renamed); a
     mis-named sentinel is invisible to the state scripts and silently loops the
     pipeline. Re-read ~/.claude/skills/_components/sentinel-frontmatter.md for
     the exact name + schema before writing ANY sentinel. Your completion receipt
     is {receipt_name}. NEEDS_INPUT_FOLLOWUP_<N>.md is orchestrator-only — cycle
     subagents never write it.
  2. WORK-BRANCH-ONLY COMMITS — Work branch: {work_branch}. Every commit/push
     goes to {work_branch} only; never create a branch, never --force. If `git
     rev-parse --abbrev-ref HEAD` is not {work_branch}, STOP and report.
  3. AFTER THE SKILL RETURNS — if .claude/skill-config/commit-policy.md exists,
     follow it; else commit per the standard pattern and push to {work_branch}.
     Skip only if the skill produced no file changes.
  4. REPORT — one paragraph (≤8 lines): state advanced, files modified, whether
     work is committed+pushed (or "no commit"), any `⚖ policy:` lines, any issues.
     NO commit sha. On /execute-plan or /retro-feature cycles, also confirm
     you executed INLINE (zero Agent() calls) and wrote failing tests before
     implementing each batch (test-first).

<!-- @section hard-contract pipelines=feature,bug modes=cloud skills=all -->
Hard contract (sentinel + git hygiene + cloud push + report):
  1. CANONICAL SENTINEL FILENAMES — write pipeline sentinels with their EXACT
     canonical names (never lowercased / abbreviated / pluralized / renamed); a
     mis-named sentinel is invisible to the state scripts and silently loops the
     pipeline. Re-read ~/.claude/skills/_components/sentinel-frontmatter.md for
     the exact name + frontmatter schema before writing ANY sentinel. Your
     pipeline's completion receipt is {receipt_name}. NEEDS_INPUT_FOLLOWUP_<N>.md
     is orchestrator-only — cycle subagents never write it.
  2. WORK-BRANCH-ONLY COMMITS — Work branch: {work_branch}. Every commit and push
     goes to {work_branch} ONLY; never create a branch, never --force. If `git
     rev-parse --abbrev-ref HEAD` is not {work_branch}, STOP and report.
  3. COMMIT + PUSH EACH BATCH (cloud durability) — the container is reclaimed on
     inactivity and any UNPUSHED commit is permanently lost, so after EACH batch /
     work-unit commit IMMEDIATELY `git push origin {work_branch}` (retry a NETWORK
     error up to 4× with 2s/4s/8s/16s backoff); never defer pushing to cycle end.
     If .claude/skill-config/commit-policy.md exists, follow it for the final
     commit; never force-push (a non-fast-forward rejection → STOP and report).
  4. REPORT — one paragraph (≤8 lines): state advanced, files modified, whether
     work is committed+pushed (or "no commit"), any `⚖ policy:` lines, and any
     issues. NO commit sha. On /execute-plan or /retro cycles, also confirm
     you executed INLINE (zero Agent() calls), wrote failing tests before
     implementing each batch (test-first), and pushed each batch as it landed.

<!-- @section turn-end pipelines=feature,bug modes=workstation skills=all -->
TURN-END CONTRACT (HARD — read LAST because it is checked LAST):
  Your background processes DIE when your turn ends — they do not keep running
  (a cycle ending "waiting" on a backgrounded job returns resultless with
  uncommitted work).
  1. NEVER end your turn while a process you started is still running. If a long
     gate/test/build was auto-backgrounded, block on it (await it or poll its
     output in a bounded foreground loop) before returning.
  2. ATOMIC GATE+COMMIT (R5): launch any long gate/test/build as ONE chained
     command that carries its own commit —
     `<gate> && git add -A && git commit -m "..." && git push` — so even an
     interrupted turn leaves committed, pushed state. This is the final action of
     each /execute-plan batch and of plan-part completion.
  3. Pre-return checklist, in order, EVERY cycle: (a) no background job of yours
     still running; (b) `git status --short` is EMPTY; (c) the branch is pushed;
     (d) the result sentinel or plan/PHASES flip your skill owes is ON DISK.
  A return that fails any of these is a resultless return — a contract violation,
  not an acceptable partial.

<!-- @section turn-end pipelines=feature,bug modes=cloud skills=all -->
TURN-END CONTRACT (HARD — read LAST because it is checked LAST):
  Your background processes DIE when your turn ends — they do not keep running
  (a cycle that ends "waiting" on a backgrounded gate/test/build loses the job's
  process tree and returns resultless with uncommitted work).
  1. NEVER end your turn while a process you started is still running. If a long
     gate/test/build was auto-backgrounded, block on it before returning.
  2. ATOMIC GATE+COMMIT (R5): launch any long gate/test/build as ONE chained
     command that carries its own commit+push —
     `<gate> && git add -A && git commit -m "..." && git push` — so even an
     interrupted turn leaves committed, pushed state. This is the final action of
     each /execute-plan batch and of plan-part completion.
  3. Pre-return checklist, in order, EVERY cycle: (a) no background job of yours
     still running; (b) `git status --short` is EMPTY; (c) the branch is pushed;
     (d) the result sentinel or plan/PHASES flip your skill owes is ON DISK.
  A return that fails any of these is a resultless return — a contract violation,
  not an acceptable partial.
