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
     Optional park attribute (park-provisional-acceptance, SPEC D13):
       park=park  → the section is selected ONLY when the emitting probe ran
       under --park-needs-input (emit_cycle_prompt park_mode=True). Absent (or
       park=both) → always selected, byte-identical to the pre-park grammar.
     Optional hosts attribute (cycle-prompt-environment-dialect, SPEC D2 —
     DECLARED HERE, SELECTION LOGIC PENDING in lazy_core.py as of this WU):
       hosts=windows  → intended to be selected ONLY when the emitting probe
       runs on a Windows host (os.name == "nt"). Absent → always selected
       (grammar-additive, same shape as park=). `_parse_section_attrs` already
       captures any key=value token, so this attribute parses today WITHOUT
       error — it is simply not yet READ by the selection loop, so a
       hosts=windows section is (for now) selected on every host its
       pipelines/modes/skills match, same as before this attribute existed.
       Emitter wiring (STATE lane): filter `attrs.get("hosts")` against the
       real host in `emit_cycle_prompt`'s selection loop, mirroring the park=
       filter immediately below it (base template AND repo addenda loops).
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
     R3  sub-subagent dispatch policy ............ sections: workstation-dispatch (permitted + guardrails) / cloud-override (inline, ban retained)
     R4  test-first within each batch ........... sections: skill-execute-plan / skill-execute-plan-cloud
     R5  atomic gate+commit (chained command) ... section: turn-end (referenced by skill-execute-plan)
     R6  substantive review, skip falsification . sections: skill-execute-plan / skill-execute-plan-cloud
     R7  status honesty (no premature flip) ..... section: status-honesty
     R8  resume safety (plan-part + per-WU) ...... section: resume-safety
     R9  canonical sentinel filenames ........... section: hard-contract (item 1)
     R10 work-branch-only commits ............... section: hard-contract (item 2)
     R11 after-the-skill commit policy .......... section: hard-contract (item 3)
     R12 report contract (no sha) ............... section: hard-contract (item 4)
     R13 turn-end contract (EXECUTED verify gate) section: turn-end
     R14 mcp-test rules ......................... sections: skill-mcp-test-common + variant sections
     R15 loop block (separate file) ............. loop-block.md (appended by emitter)
     R16 cloud deltas ........................... section: cloud-override (+ commit-push folded into hard-contract item 3 / turn-end via modes)
     R17 terminal stop (C4) ..................... section: terminal-stop
     R18 environment dialect (host-conditional) .. sections: env-dialect-core (every host) / env-dialect-windows (hosts=windows)
     R19 PHASES read mandate (phases-slice.py) ... section: env-dialect-core (stated once; skill-mcp-test-common's RECONCILE step references it, does not restate it)

     The ONE sanctioned restatement is the turn-end pre-return checklist, which
     is now the contract of an EXECUTED `--verify-ledger` terminal gate (item 3
     in `turn-end`) — its `ok:true` verdict certifies the four conditions rather
     than the subagent self-walking them as advisory prose. (A checklist may
     re-walk rules; prose may not.)

     ── PROVENANCE ─────────────────────────────────────────────────────────
     Workstation deltas come from this file's prior monolithic form; cloud
     deltas were folded in from lazy-batch-cloud/SKILL.md's hand-synced inline
     copy (a later WU deletes that inline copy); bug/feature differences are
     tokenized so lazy-bug-batch's substitution list + "No premature Fixed"
     block become dead. -->

<!-- @section task pipelines=feature,bug modes=workstation skills=all -->
Run exactly one skill, then stop. You are one worker in the {pipeline_phrase}.

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
Run exactly one skill, then stop. You are one worker in the {pipeline_phrase},
running in a CLOUD Linux session. This container has: no Tauri desktop runtime,
no MCP HTTP server, no audio device, no Windows-only tooling, and NO persistent
state (it is reclaimed after the session).

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

<!-- @section env-dialect-core pipelines=feature,bug modes=workstation,cloud skills=all -->
Environment dialect (core — every host, {pipeline_phrase}):
  - Cross-process handoff: pipe data via STDIN, never a shared temp file — a
    Bash-written path is not guaranteed readable by a separately-invoked
    interpreter (dialect mismatch between the shell and the runtime that
    reads it). Prefer `<producer> | python3 -c "import sys, json; d =
    json.load(sys.stdin)"` over writing then re-`open()`-ing a temp file.
  - Probe the run marker with `python3 ~/.claude/scripts/lazy-state.py
    --repo-root {cwd} --marker-status` (bug pipeline: `bug-state.py`) — it
    ALWAYS exits 0 and prints `{"present": bool, ...}`, absent marker,
    corrupt JSON, or no state dir alike. Never hand-roll a
    `cat <marker> 2>/dev/null | python -c "json.load(sys.stdin)"` idiom — an
    absent file raises on empty stdin.
  - Read PHASES.md ONLY through
    `python3 ~/.claude/scripts/phases-slice.py {spec_path} [--phase <id>]` —
    never a whole-file Read. A mature feature's PHASES.md routinely exceeds
    the Read tool's cap; the slicer returns the phase index plus only the
    phase(s) you name.

<!-- @section env-dialect-windows pipelines=feature,bug modes=workstation skills=all hosts=windows -->
Environment dialect (this host: Windows / Git Bash):
  - No trailing `\` before a closing quote in a Windows path — `"C:\...\dir\"`
    reads as an unterminated string to Git Bash (the `\"` escapes the quote,
    so the shell waits for EOF). Use forward slashes (`"C:/.../dir"`) or make
    sure the path's last character before the quote is never `\`.
  - No `/mnt/c/...` — that is the WSL path dialect. This Bash tool is Git
    Bash on native Windows, not WSL; use the native `C:/...` path (or a
    relative path from {cwd}).
  - Import `lazy_core`/state-script modules via a `$HOME`-anchored
    `sys.path` (`sys.path.insert(0, os.path.expanduser("~/.claude/scripts"))`
    or run the script by its `~/.claude/scripts/<name>.py` path directly) —
    never a hardcoded `/root/...` or WSL-guessed absolute path.

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

<!-- @section park-divergence-grade pipelines=feature,bug modes=workstation,cloud skills=all park=park -->
Park-mode divergence self-grade (park-provisional-acceptance — PRODUCER duty):
  This is a PARK-MODE run (--park-needs-input active). When you write a
  NEEDS_INPUT.md for product-class decisions, ALSO record a file-level
  `divergence:` grade in its frontmatter — the rework blast radius if the
  operator later redirected away from your recommended option:
    isolated   — options differ inside one module/doc surface; a redirect is
                 a small local edit.
    contained  — a few files, no architectural fork; a redirect is a bounded
                 corrective phase.
    structural — options fork architecture, persistent data, or user-visible
                 workflow; a redirect would be significant rework.
  Most severe across the file's decisions wins; grade CONSERVATIVELY (unsure →
  the more severe grade; absent is treated as structural — never provisional).
  Every decision's Options list stays recommendation-FIRST with a
  **Recommendation:** line (the provisional machinery extracts the label).
  Vocabulary + eligibility rules: ~/.claude/skills/_components/sentinel-frontmatter.md.

<!-- @section park-spec-sentinel-mediation pipelines=feature,bug modes=workstation,cloud skills=spec,spec-bug park=park -->
PARK-MODE INTERACTION CONTRACT (/spec under park mode — SPEC D13, LOAD-BEARING):
  This is an UNATTENDED park-mode run: no operator is watching, so an
  AskUserQuestion round would silently hang the lane. You MUST NOT call
  AskUserQuestion — even where /spec's Phase-1 brainstorming (stub-spec
  baseline shaping) normally permits it. Instead, run fully sentinel-mediated:
  1. DRAFT THE BASELINE FIRST (the "Phase 1 under --batch" contract): author
     the best-supported baseline SPEC from the stub/brief + repo evidence.
  2. Apply the D7 completeness policy IN-CYCLE for every scope-class decision
     (disclose with ⚖ policy: lines — see the Completeness-first section).
  3. Surface the ≤4 genuinely baseline-GATING product forks via NEEDS_INPUT.md
     (rich `## Decision Context` body per sentinel-frontmatter.md,
     recommendation-first Options, a **Recommendation:** per decision, the
     file-level `divergence:` self-grade above, AND `stub_origin: true` —
     MANDATORY on a stub-spec baseline round: these decisions shape a baseline
     the operator has never seen, so they are excluded from provisional
     acceptance and always park for the operator
     (stub-origin-provisional-exclusion)) — the park machinery picks the
     sentinel up on the next probe; the input-audit supplies the independent
     `audit_divergence` second key and backstops the stub-origin marker.
  Research-answerable questions still go into RESEARCH_PROMPT.md, never the
  sentinel. A brief too ambiguous even for a placeholder baseline writes
  BLOCKED.md (blocker_kind: pre-research-input-required) exactly as the
  non-park batch contract specifies.

<!-- @section workstation-dispatch pipelines=feature,bug modes=workstation skills=all -->
Sub-subagent dispatch policy (WORKSTATION DISPATCH — LOAD-BEARING):
  You MAY use the `Agent` tool (workstation-recursive-subagent-dispatch,
  2026-07-09 — the former INLINE-OVERRIDE ban is lifted on workstation; cloud
  cycles keep it). When the dispatched skill's SKILL.md defines a sub-subagent
  orchestration model — /execute-plan's Sonnet test-agent + impl-agent split,
  /retro's research subagents, read-only Explore fan-outs — FOLLOW that model:
  the skill's own contract is authoritative again, including its structural
  test-first agent separation. Dispatch is a tool, not an obligation — for a
  small mechanical batch, inline Read/Edit/Write remains the cheaper right
  choice.
  GUARDRAILS (each is load-bearing):
  - The TERMINAL STOP categorical ban binds you AND every sub-subagent you
    dispatch: no /lazy*-family skill invocations, no run-lifecycle/routing ops
    (--run-start / --run-end / --apply-pseudo / --enqueue-adhoc /
    --cycle-begin / --cycle-end / dev:kill / dev:restart), no second-feature
    commits. RESTATE this prohibition in EVERY sub-subagent prompt you
    compose — the containment hook is the backstop, not the contract.
  - Single-writer discipline: never run two sub-subagents that edit the same
    files concurrently. You remain the cycle's single integrator — the
    turn-end verify/commit gates are YOURS, and a sub-subagent's completion
    claim is not evidence (verify the work on disk before ticking anything).
  - Scope containment: sub-subagents work ONLY inside this {item_label}'s
    scope. Delegating the entire cycle wholesale to one sub-subagent is
    re-dispatching, not orchestrating — forbidden.
  - SYNCHRONOUS AWAIT — never block on a child→parent message channel
    (2026-07-11 sub-subagent deadlock). When you dispatch a sub-subagent with
    the `Agent` tool, you AWAIT that dispatch and CONSUME the child's returned
    final result DIRECTLY — the child's result comes back to you as the tool
    result of the `Agent` call. No SendMessage is needed, EVER, to collect a
    child's work. A dispatched child CANNOT reach its spawning parent by name
    (only the top-level orchestrator / `main` is reachable by name from a
    child — a child's `SendMessage` to its parent FAILS with "the
    general-purpose agent isn't reachable by that name"). Therefore: NEVER
    dispatch children "in the background" / asynchronously and then wait for
    them to SendMessage their results back to you — that is a DEADLOCK: the
    child's reply never arrives and you return RESULTLESS mid-cycle ("waiting
    on the resumed test agents before dispatching impl agents"), which then
    needs a manual orchestrator resume. Sequence dependent children
    SYNCHRONOUSLY: for /execute-plan's test-first split, AWAIT the test-agent
    dispatch and consume the failing tests it returns, THEN dispatch and AWAIT
    the impl-agent — do NOT launch both and block on inter-agent messages.
    Independent children may be dispatched in one batch (parallel), but you
    still AWAIT their returned results — you never wait on a message FROM them.
    "Waiting for a sub-subagent's message" is NEVER a valid cycle state: if you
    catch yourself in it you have already diverged — dispatch-and-await each
    child, or do the batch inline with Read/Edit/Write.
  - WEDGE RESILIENCE — a dispatched sub-subagent that WEDGES never strands your
    cycle; you fall back to INLINE (2026-07-18 depth-2 nested-dispatch wedge). A
    total tool-execution wedge is a dispatched child whose EVERY tool call errors
    before executing — e.g. the Claude Code `No tools needed for summary`
    message — a platform limitation of depth-2 (grandchild) dispatch under
    async/background agents; YOUR OWN depth-1 Read/Grep/Glob/Bash keep working.
    When a child you dispatched comes back wedged (an empty / all-errored result,
    not real work): do NOT wait for it, and do NOT re-dispatch it — it wedges
    identically. Instead PERFORM THAT WORK INLINE yourself with Read/Grep/Glob/
    Bash and finish the cycle. A wedged fan-out is NEVER an excuse to return
    without your skill's deliverable — if the spec-phases capability/reuse audits,
    the plan-feature / spec-phases(-batch) / write-plan Sonnet fan-out, or an
    /execute-plan test/impl split wedge, do their reads INLINE and still produce
    PHASES.md / the plan / the tested code this cycle. "Waiting for the remaining
    wedged agents" is the same forbidden cycle state as waiting on a child
    message above — collapse to inline the instant a dispatch returns wedged.
    (Resilience, not avoidance — this composes with a "trust the coordination
    layer, don't defensively serialize" contract; you still PREFER dispatch when
    it works, and only fall back on an observed wedge.)

<!-- @section cloud-override pipelines=feature,bug modes=cloud skills=all -->
Sub-subagent dispatch policy (CLOUD OVERRIDE — LOAD-BEARING):
  Do NOT use the `Agent` tool — sub-subagent dispatch is FORBIDDEN in a cloud
  cycle (policy; do not rely on the tool being absent or on a hook denying it).
  Perform ALL skill-mandated sub-subagent work (test-agent,
  impl-agent, research subagents A–G, etc.) INLINE with Read / Edit / Write. The
  dispatch-level prohibition (in addition to the TERMINAL STOP categorical ban on
  pipeline ops): never invoke another /lazy or /lazy-batch. Do NOT write BLOCKED.md
  because of this dispatch limit (BLOCKED.md is still correct for genuine
  cloud-RUNTIME limits — Tauri, MCP, audio, Windows-only tooling — via
  blocker_kind: cloud-limitation).
  Zero sub-subagent dispatches in a cloud /execute-plan cycle is the EXPECTED state — NOT a contract violation.
  The dispatched skill's SKILL.md stays authoritative for everything else —
  re-read it from disk if unclear.

  Cloud runtime deferral: this container has no Tauri runtime and no MCP HTTP
  server, so MCP validation is DEFERRED to a later workstation pass — a cloud
  cycle never dispatches /mcp-test, and `Complete` (which asserts MCP-validated)
  is never honest here; the honest cloud terminal is `In-progress`.

<!-- @section skill-execute-plan pipelines=feature,bug modes=workstation skills=execute-plan,retro-feature -->
/execute-plan (and retro-feature's inner execute-plan loop) — execution:
  - EXECUTE ONLY THE DISPATCHED PLAN PART (HARD — ISSUE 2, d8-effect-chains run):
    run EXACTLY the plan file passed to you — never a sibling part, never "the part
    that's actually ready." Check the dispatched part's `> **Entry criteria:**` /
    `Plan series` "execute parts strictly in order" prerequisites FIRST. If a
    prerequisite part is not `status: Complete`, STOP and write BLOCKED.md
    (`blocker_kind: prerequisite-part-incomplete`) naming the unmet part — do NOT
    silently switch to it. (Live incident: dispatched on Sonnet for the mechanical
    part-2, the subagent silently executed the complex part-1 instead, then died
    resultless.) If the dispatched part's real work exceeds its declared
    `complexity:` tier (e.g. complex work under a Sonnet dispatch), STOP with
    BLOCKED.md `blocker_kind: model-tier-mismatch` rather than grinding it out.
  - TEST-FIRST PER BATCH (R4): follow the plan's test-agent → impl-agent
    sub-subagent model per the WORKSTATION DISPATCH policy above — the failing
    tests land (and fail for the right reason) BEFORE implementation. When you
    judge a small mechanical batch cheaper inline, keep the same discipline
    manually: failing tests first, then implement until they pass.
  - SUBSTANTIVE REVIEW (R6): for work done by sub-subagents, apply the
    dispatched skill's subagent-review contract (their reports are untrusted —
    re-verify against the working tree). For work you did inline yourself, skip
    subagent-review.md's Step 1.5 re-run-and-diff (it polices a SEPARATE
    subagent's report) but still do the substantive review (spec alignment,
    deliverable coverage, edge cases, propagation) and run the gates.
  - ATOMIC GATE+COMMIT (R5): the final action of each batch / plan-part
    completion is the ONE chained command from the turn-end contract below.

<!-- @section skill-execute-plan-cloud pipelines=feature,bug modes=cloud skills=execute-plan,retro-feature -->
/execute-plan (and retro-feature's inner execute-plan loop) — inline execution:
  - EXECUTE ONLY THE DISPATCHED PLAN PART (HARD — ISSUE 2, d8-effect-chains run):
    run EXACTLY the plan file passed to you — never a sibling part, never "the part
    that's actually ready." Check the dispatched part's `> **Entry criteria:**` /
    `Plan series` "execute parts strictly in order" prerequisites FIRST. If a
    prerequisite part is not `status: Complete`, STOP and write BLOCKED.md
    (`blocker_kind: prerequisite-part-incomplete`) naming the unmet part — do NOT
    silently switch to it. (Live incident: dispatched on Sonnet for the mechanical
    part-2, the subagent silently executed the complex part-1 instead, then died
    resultless.) If the dispatched part's real work exceeds its declared
    `complexity:` tier (e.g. complex work under a Sonnet dispatch), STOP with
    BLOCKED.md `blocker_kind: model-tier-mismatch` rather than grinding it out.
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

<!-- @section provenance-lookup pipelines=feature,bug modes=workstation,cloud skills=execute-plan,retro-feature -->
Provenance lookup before editing (code-doc-provenance-linkage D6-A):
  Before your FIRST edit to each source/script file this cycle, run the cheap
  pure-read lookup:
    python3 ~/.claude/scripts/lazy-state.py --provenance-lookup <file> --repo-root {cwd}
  It lists the decision records governing that file (<id, doc, decisions>
  rows from docs/provenance-index.json). Open the cited IMPLEMENTED.md ONLY
  when the decision ids are unfamiliar to the task at hand — do not re-read
  ledgers you already know. Empty governed_by / no index → proceed (the step
  is a no-op where no index exists). This is how you avoid re-deriving — or
  contradicting — a past Locked Decision that governs the file under edit.

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
    mcp-testing SPEC) / BLOCKED.md naming a CONCRETE blocker. A scenario whose
    real unmet prerequisite is a HOST CAPABILITY this machine lacks (a 2nd network
    peer / a different OS / an external binary), NOT an audio device, is NOT a
    device deferral — declare `requires_host: <id>` (SPEC frontmatter / queue.json)
    so the state machine defers it to a capability-host (host-capability-saturated)
    instead of DEFERRED_REQUIRES_DEVICE, which re-opens and LOOPS on a real-device
    host (litmus: would a real audio device on THIS machine certify it? no → host).
  - VALIDATION-BLOCKED IS FOR CODE/ENGINE FAILURES ONLY: a `BLOCKED.md` with
    `blocker_kind: mcp-validation` certifies that the CODE under test failed (the
    engine ran and assertions did not pass). A RUNTIME-READINESS condition — the
    sidecar pipe is dead despite `/health == 200` (`get_sidecar_status` →
    `is_connected: false`), a self-inflicted env transient — is EXPLICITLY
    EXCLUDED: it routes to the runtime-readiness terminal (NEEDS_RUNTIME in the
    runtime-up variant; `blocker_kind: mcp-runtime-unready`, escalation-immune,
    when the orchestrator gate catches it upstream), so the env transient is
    NEVER charged to the validation-retry/escalation budget.
  - SKIP PROVENANCE: any SKIP_MCP_TEST.md MUST carry `granted_by: mcp-test` AND
    `spec_class: <the untestable class you verified against
    docs/features/mcp-testing/SPEC.md>`. The state scripts REFUSE a pipeline skip
    that omits either field and halt for operator confirmation. Audio IS
    MCP-testable (load_test_tone + get_audio_buffer), so audio untestability
    claims are usually WRONG — cross-check the SPEC before claiming a class.
  - RECONCILE PHASES (after VALIDATED.md): read {spec_path}'s PHASES.md via the
    env-dialect-core mandate above (`phases-slice.py {spec_path} --phase <id>`,
    never a whole-file Read) and, for EVERY unchecked Runtime Verification row,
    either tick it with a brief evidence
    annotation when THIS validation run covers it, or — when it does NOT — re-scope
    it honestly (convert to a non-checkbox follow-up note, or downgrade your result
    to an MCP_TEST_RESULTS.md partial if it is genuinely a blocking gap) under a
    `⚖` disclosure line. Then flip each phase's `**Status:**` to Complete once
    nothing in it remains unchecked (per-phase flips are permitted — R7). WHY: the
    completion gate refuses an incoherent flip, so an unreconciled PHASES strands
    the feature at mark-complete.
  - SEAM ENUMERATION (EVERY mcp-validation BLOCKED.md — enumerate at the FIRST
    failure, not only on escalation): if the BLOCKED.md you are writing carries
    `blocker_kind: mcp-validation`, at ANY `retry_count` (including 0 — the
    FIRST validation failure for this {item_label}), its body MUST include a
    `## Seam Enumeration` section listing EVERY boundary in the failing chain
    (user surface → sidecar/IPC → engine → final observable) PLUS any
    obviously-adjacent unwired seam, each with a per-seam status: `probed-OK` /
    `probed-FAIL` / `unprobed`. You are already inside the live runtime — you
    are the cheapest enumeration point, and probing one more boundary costs a
    single tool call, not a full pipeline loop. The corrective phase consumes
    this as its seam-audit checklist so the NEXT validation round does not
    discover the next layer cold (a feature once burned three ~1M-token rounds
    peeling one layer per round — the historical pattern this mandate now heads
    off from round 1, not just round 3). At `retry_count >= 2` (repeated
    failure despite an already-batched seam fix) the escalation tier ALSO
    requires `/investigate` before the next corrective phase — see
    `blocked-resolution.md` step 1a.

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
  - SIDECAR-PIPE READINESS (runtime-readiness terminal — NOT a validation
    failure): the dev HTTP server boots INDEPENDENTLY of the MCP sidecar named
    pipe, so `/health == 200` does NOT prove the sidecar is connected. A zombie
    node process left holding the `:3333` pipe after a `dev:restart` leaves the
    runtime HTTP-healthy but MCP-functionally DEAD — a self-inflicted ENVIRONMENT
    transient, NOT a code failure. BEFORE running the engine, probe
    `GET http://localhost:3333/tools/get_sidecar_status`. If it reports
    `is_connected: false`, do NOT run the engine and do NOT write an
    `mcp-validation` `BLOCKED.md` (that would charge an env transient to the
    feature's validation-retry/escalation budget). Instead return the single line
    NEEDS_RUNTIME as your ENTIRE report — the orchestrator re-boots the runtime
    cleanly (reaping the zombie) in its own session and re-dispatches you against
    a live, sidecar-connected server. (Same escape as the `no-runtime` variant's
    DISAGREE path — the env transient routes to runtime-readiness, never to
    `mcp-validation`.)

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
     goes to {work_branch} only; never create a branch, never --force. NEVER run
     `git checkout -b`, `git switch -c`, or `git branch <new>` mid-cycle — creating
     a branch strands every sentinel you write where the state scripts cannot see
     it. If `git rev-parse --abbrev-ref HEAD` is not {work_branch}, STOP and report.
     RE-ASSERT this immediately BEFORE every commit/push, not only at cycle entry:
     re-run `git rev-parse --abbrev-ref HEAD` and confirm it equals {work_branch}
     before each `git commit`/`git push`; if it drifted, STOP and report.
  3. AFTER THE SKILL RETURNS — the commit policy is whatever is ON DISK at
     .claude/skill-config/commit-policy.md. `Read` that file and observe its
     contents before asserting ANY rule from it; NEVER assert its contents from
     memory, and an ABSENT file is NOT a policy. Absent the file, the standing
     default is: commit + push per the standard pattern to {work_branch}. NEVER
     skip a required commit on the basis of an unread or absent policy. Skip
     committing ONLY if the skill produced no file changes.
  4. REPORT — one paragraph (≤8 lines): state advanced, files modified, whether
     work is committed+pushed (or "no commit"), any `⚖ policy:` lines, any issues.
     NO commit sha. On any cycle that COULD write NEEDS_INPUT.md (/spec,
     /spec-phases, /write-plan, /add-phase), state the NEEDS_INPUT
     disposition EXPLICITLY — either "wrote NEEDS_INPUT.md ({N} decision(s))" or,
     when none was needed, a skip disclosure: "no NEEDS_INPUT — {N} reviewed, all
     {mechanical-internal | scope-class (D7) | none arose}; {≤12-word reason}".
     The no-sentinel outcome is NEVER silent (sentinel-frontmatter.md Producer
     responsibilities #7). On /execute-plan or /retro-feature cycles, also confirm
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
     goes to {work_branch} ONLY; never create a branch, never --force. NEVER run
     `git checkout -b`, `git switch -c`, or `git branch <new>` mid-cycle — creating
     a branch strands every sentinel you write where the state scripts cannot see
     it. If `git rev-parse --abbrev-ref HEAD` is not {work_branch}, STOP and report.
     RE-ASSERT this immediately BEFORE every commit/push, not only at cycle entry:
     re-run `git rev-parse --abbrev-ref HEAD` and confirm it equals {work_branch}
     before each `git commit`/`git push`; if it drifted, STOP and report.
  3. COMMIT + PUSH EACH BATCH (cloud durability) — the container is reclaimed on
     inactivity and any UNPUSHED commit is permanently lost, so after EACH batch /
     work-unit commit IMMEDIATELY `git push origin {work_branch}` (retry a NETWORK
     error up to 4× with 2s/4s/8s/16s backoff); never defer pushing to cycle end.
     The commit policy is whatever is ON DISK at
     .claude/skill-config/commit-policy.md: `Read` that file and observe its
     contents before asserting ANY rule from it; NEVER assert its contents from
     memory, and an ABSENT file is NOT a policy. Absent the file, the standing
     default is commit + push to {work_branch}; NEVER skip a required commit on the
     basis of an unread or absent policy. Never force-push (a non-fast-forward
     rejection → STOP and report).
  4. REPORT — one paragraph (≤8 lines): state advanced, files modified, whether
     work is committed+pushed (or "no commit"), any `⚖ policy:` lines, and any
     issues. NO commit sha. On any cycle that COULD write NEEDS_INPUT.md (/spec,
     /spec-phases, /write-plan, /add-phase, /retro), state the NEEDS_INPUT
     disposition EXPLICITLY — either "wrote NEEDS_INPUT.md ({N} decision(s))" or,
     when none was needed, a skip disclosure: "no NEEDS_INPUT — {N} reviewed, all
     {mechanical-internal | scope-class (D7) | none arose}; {≤12-word reason}".
     The no-sentinel outcome is NEVER silent (sentinel-frontmatter.md Producer
     responsibilities #7). On /execute-plan or /retro cycles, also confirm
     you executed INLINE (zero Agent() calls), wrote failing tests before
     implementing each batch (test-first), and pushed each batch as it landed.

<!-- @section terminal-stop pipelines=feature,bug modes=workstation,cloud skills=all -->
TERMINAL STOP (HARD — your dispatch is ONE cycle):
  Your dispatch is exactly ONE cycle. After your single skill returns and you
  have committed + pushed + written your report, STOP. Do NOT run
  `lazy-state.py`/`bug-state.py` to find or route a next action. Do NOT begin a
  second feature. Do NOT run pipeline/orchestration or lifecycle commands, and do
  not invoke any `/lazy*` skill — those are orchestrator-only and the harness will
  DENY them in-flight. Routing the next cycle is the orchestrator's job; your job
  ends at the report.

<!-- @section turn-end pipelines=feature,bug modes=workstation skills=all -->
TURN-END CONTRACT (HARD — read LAST because it is checked LAST):
  Your background processes DIE when your turn ends — they do not keep running
  (a cycle ending "waiting" on a backgrounded job returns resultless with
  uncommitted work).
  1. NEVER end your turn while a process you started is still running. If a long
     gate/test/build was auto-backgrounded, block on it (await it or poll its
     output in a bounded foreground loop) before returning. PREVENT the
     auto-background: when a required gate command would EXCEED the ~10-min Bash
     cap (so the harness auto-backgrounds it), do NOT reach for the aggregate —
     re-running the aggregate foreground just re-hits the cap and re-backgrounds.
     Run its individual UNDER-cap sub-components synchronously in the foreground
     instead (each drives to a real pass/fail within the cap). Never background a
     long gate from inside this cycle subagent — its process tree is torn down
     when your turn ends.
  2. ATOMIC GATE+COMMIT (R5): launch any long gate/test/build as ONE chained
     command that carries its own commit —
     `<gate> && git add -A && git commit -m "..." && git push` — so even an
     interrupted turn leaves committed, pushed state. This is the final action of
     each /execute-plan batch and of plan-part completion.
  3. TERMINAL VERIFY GATE (EXECUTED, not self-walked) — your FINAL action is a
     real command, not a mental checklist. In order:
     (i) FINALIZE all reconciliation writes FIRST: tick the landed WU/PHASES
         checkboxes (`- [ ]` → `- [x]`), flip the plan-part frontmatter `status:`,
         and write the owed result sentinel — so no post-gate write can strand.
     (ii) Then run the deterministic ledger verifier as a SEPARATE final step
         (NOT appended to the R5 chain above — a non-zero verify exit must not
         abort the commit). Select the script by pipeline (the bug pipeline uses
         `bug-state.py`; the feature pipeline uses `lazy-state.py`):
           `python3 ~/.claude/scripts/<lazy-state.py|bug-state.py> --repo-root <cwd> --verify-ledger <spec_path> [--plan <plan_file>]`
         `--plan <plan_file>` is OPTIONAL — include it ONLY on plan-scoped
         (execute-plan) cycles so the verifier reads `deliverables_done` from the
         plan-part WU boxes.
     (iii) If the result's `ok` is false, RECONCILE the named failing check
         in-turn — commit + push residue, tick the boxes, flip the plan status —
         and RE-RUN the verifier until `ok` is true. Only an `ok:true` terminal
         verdict authorizes return; a return without it is a resultless return.
     The `ok:true` verdict is what CERTIFIES the four turn-end conditions —
     (a) no background job of yours still running; (b) `git status --short` EMPTY;
     (c) the branch is pushed; (d) the result sentinel or plan/PHASES flip your
     skill owes is ON DISK — so the checklist is this EXECUTED gate's contract,
     not separate advisory prose to self-walk.
  A return that fails any of these is a resultless return — a contract violation,
  not an acceptable partial.

<!-- @section turn-end pipelines=feature,bug modes=cloud skills=all -->
TURN-END CONTRACT (HARD — read LAST because it is checked LAST):
  Your background processes DIE when your turn ends — they do not keep running
  (a cycle that ends "waiting" on a backgrounded gate/test/build loses the job's
  process tree and returns resultless with uncommitted work).
  1. NEVER end your turn while a process you started is still running. If a long
     gate/test/build was auto-backgrounded, block on it before returning. PREVENT
     the auto-background: when a required gate command would EXCEED the ~10-min
     Bash cap (so the harness auto-backgrounds it), do NOT reach for the aggregate
     — re-running the aggregate foreground just re-hits the cap and re-backgrounds.
     Run its individual UNDER-cap sub-components synchronously in the foreground
     instead (each drives to a real pass/fail within the cap). Never background a
     long gate from inside this cycle subagent — its process tree is torn down
     when your turn ends.
  2. ATOMIC GATE+COMMIT (R5): launch any long gate/test/build as ONE chained
     command that carries its own commit+push —
     `<gate> && git add -A && git commit -m "..." && git push` — so even an
     interrupted turn leaves committed, pushed state. This is the final action of
     each /execute-plan batch and of plan-part completion.
  3. TERMINAL VERIFY GATE (EXECUTED, not self-walked) — your FINAL action is a
     real command, not a mental checklist. In order:
     (i) FINALIZE all reconciliation writes FIRST: tick the landed WU/PHASES
         checkboxes (`- [ ]` → `- [x]`), flip the plan-part frontmatter `status:`,
         and write the owed result sentinel — committing AND pushing each (an
         unpushed commit is lost on container reclaim) — so no post-gate write
         can strand.
     (ii) Then run the deterministic ledger verifier as a SEPARATE final step
         (NOT appended to the R5 commit+push chain above — a non-zero verify exit
         must not abort the commit). Select the script by pipeline (the bug
         pipeline uses `bug-state.py`; the feature pipeline uses `lazy-state.py`):
           `python3 ~/.claude/scripts/<lazy-state.py|bug-state.py> --repo-root <cwd> --verify-ledger <spec_path> [--plan <plan_file>]`
         `--plan <plan_file>` is OPTIONAL — include it ONLY on plan-scoped
         (execute-plan) cycles so the verifier reads `deliverables_done` from the
         plan-part WU boxes.
     (iii) If the result's `ok` is false, RECONCILE the named failing check
         in-turn — commit + push residue, tick the boxes, flip the plan status —
         and RE-RUN the verifier until `ok` is true. Only an `ok:true` terminal
         verdict authorizes return; a return without it is a resultless return.
     The `ok:true` verdict is what CERTIFIES the four turn-end conditions —
     (a) no background job of yours still running; (b) `git status --short` EMPTY;
     (c) the branch is pushed; (d) the result sentinel or plan/PHASES flip your
     skill owes is ON DISK — so the checklist is this EXECUTED gate's contract,
     not separate advisory prose to self-walk.
  A return that fails any of these is a resultless return — a contract violation,
  not an acceptable partial.
