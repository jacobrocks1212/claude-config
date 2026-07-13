<!-- @requires item_name,spec_path,sentinel_path,resolution_summary,resolution_kind,chosen_path,item_id,cwd -->
<!-- dispatch-apply-resolution.md — emitted by emit_dispatch_prompt("apply-resolution", ...)
     Derived from decision-resume.md (Step 1g) + blocked-resolution.md (Step 1h) dispatch
     prompts. Covers FOUR shapes: resolution_kind="needs-input" (decision-resume),
     resolution_kind="blocked" (blocked-resolution), resolution_kind="provisional"
     (__provisional_accept__ propagation — park-provisional-acceptance; NEVER neutralizes),
     and resolution_kind="ratify-redirect" (provisional-ratification redirect — propagates
     the changed choice, authors the decision_commit-scoped corrective phase, neutralizes).
     The orchestrator sets resolution_kind from probe output before calling
     emit_dispatch_prompt. chosen_path / resolution_summary are BOUND FROM THE
     RECORDED DECISION (mechanize-prose-only-orchestrator-contracts (c) —
     lazy_core.bind_decision_record_context), not typed as --context args: run
     `lazy-state.py --record-decision --sentinel <sentinel_path> --chosen
     "<answer>" [--summary "<text>"]` FIRST (right after the operator answers
     AskUserQuestion), THEN call --emit-dispatch apply-resolution with
     sentinel_path in context — the emit reads chosen_path/resolution_summary
     from the record and REFUSES (naming the exact --record-decision command)
     if no record exists yet. This closes the hand-carry-across-compaction
     failure mode ("Why was the plan not updated after my decision?" /
     "My answers didn't go through") — the answer is on disk before the
     worker is ever dispatched.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section role pipelines=feature,bug modes=workstation,cloud -->
You are applying an operator-resolved design decision or blocker resolution back into the
{item_label} docs for the autonomous pipeline, then neutralizing the sentinel so the loop
can resume.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
Spec path:        {spec_path}
Sentinel file:    {sentinel_path}
Resolution kind:  {resolution_kind}
Chosen path:      {chosen_path}
Resolution summary: {resolution_summary}

<!-- @section needs-input-steps pipelines=feature,bug modes=workstation,cloud -->
<!-- Applies when resolution_kind == "needs-input" (decision-resume, Step 1g). -->

Steps (decision-resume path — resolution_kind: needs-input):

1. Read the sentinel file fully (the sentinel path shown above) — frontmatter, Decision Context
   body, and the appended ## Resolution section.

2. For EACH decision in the ## Decision Context, locate the section(s) of SPEC.md
   and/or PHASES.md (in the spec path shown above) that the choice impacts. Apply the choice surgically: update
   the design narrative, the implementation plan, API shape, schema choice, dependency
   selection — whatever the decision touches. Keep edits scoped; the choice is the operator's,
   your job is mechanical propagation. If a decision has no impact on either doc (rare — e.g.,
   the question was about future-phase scaffolding not drafted yet), record that in your summary
   and move on.

2b. TERMINAL DISPOSITION (receipt-EXEMPT close — enact ONLY when the operator directed it).
   If the operator's chosen resolution is to CLOSE / RETIRE this {item_label} WITHOUT a fix —
   a {receipt_exempt_status} disposition (the ## Resolution **Choice:**/**Notes:** direct
   resolving the item toward {receipt_exempt_status}, e.g. "close as working-as-designed",
   "won't fix", "retire", "superseded") — then SET the terminal status on SPEC.md:
   change the `**Status:**` line to `**Status:** {receipt_exempt_status}`. This IS the mechanical
   propagation of the operator's already-made close decision (they chose it via AskUserQuestion;
   your job is to enact it), and it is receipt-EXEMPT: {receipt_exempt_status} is retired-without-a-fix
   and the state script skips it unconditionally, so it NEVER carries a {receipt_name} receipt.
   DO NOT write {receipt_name} and DO NOT set the receipt-GATED status {receipt_gated_status}
   (that one stays receipt-owned). If the chosen resolution is an ordinary design choice that
   feeds back into planning (NOT a close), skip this step entirely — do the step-2 propagation only.

3. Neutralize the sentinel so the state script stops returning terminal_reason=needs-input on
   the next cycle:

<!-- @section neutralize-feature pipelines=feature modes=workstation,cloud -->
     python3 ~/.claude/scripts/lazy-state.py --neutralize-sentinel <sentinel_path>

<!-- @section neutralize-bug pipelines=bug modes=workstation,cloud -->
     python3 ~/.claude/scripts/bug-state.py --neutralize-sentinel <sentinel_path>

<!-- @section neutralize-note pipelines=feature,bug modes=workstation,cloud -->
   The script performs the canonical rename to *_RESOLVED_<YYYY-MM-DD>.md (git-mv-aware,
   collision-safe — appends a numeric suffix if the target name already exists), preserving
   the audit trail. Manual fallback (only if the script is unavailable): git mv the file to a
   *_RESOLVED_<date>.md name. DO NOT merely edit the frontmatter kind: field — the state
   script keys its halt on the FILENAME, so a kind: flip leaves the file named as-is and the
   halt fires again (this is a real bug that was hit in practice).

3b. Promote any follow-up sentinel (input-audit overflow). After the neutralization in step 3,
   check the spec dir for NEEDS_INPUT_FOLLOWUP_*.md files. If any exist, rename the
   LOWEST-numbered one to NEEDS_INPUT.md (git mv) and note the promotion in your summary.
   The state script keys the needs-input halt on the EXACT filename NEEDS_INPUT.md, so this
   promotion is what makes the next probe re-surface the follow-up decisions.

4. Commit per .claude/skill-config/commit-policy.md (or the standard pattern).
   Commit message (use the item id shown above): `docs(<item_id>): apply decision resolution to SPEC/PHASES`.
   WORK-BRANCH-ONLY: commit to the CURRENT branch only (git rev-parse --abbrev-ref HEAD at
   start); NEVER create a new branch, NEVER --force.

<!-- @section blocked-steps pipelines=feature,bug modes=workstation,cloud -->
<!-- Applies when resolution_kind == "blocked" (blocked-resolution, Step 1h). -->

Steps (blocked-resolution path — resolution_kind: blocked):

Read BLOCKED.md (the sentinel path shown above) fully — frontmatter, blocker body, and the
appended ## Resolution section (chosen path + operator notes). Then enact EXACTLY the chosen path:

  "Add a phase to resolve the blocker":
    Invoke the /add-phase skill (via the Skill tool — you MAY use it; you may NOT use
    Agent) against this {item_label} (the item id shown above), authoring a new phase whose scope is the blocker described
    in BLOCKED.md (and any recovery the cycle subagent suggested). It appends the phase to
    PHASES.md (In-progress, with unchecked deliverables) per its own contract. Then
    NEUTRALIZE BLOCKED.md (see below). The next loop cycle's state script routes the
    {item_label} to plan/implement the new phase.
    SEAM-BATCHED SCOPE (HARD, mcp-validation blockers at ANY retry_count): the new phase
    MUST carry a full-chain seam-audit deliverable scoped to the FULL ## Seam Enumeration
    section BLOCKED.md's validation cycle already wrote (every probed-FAIL + unprobed row)
    — live-probe each seam post-fix BEFORE full re-validation. Do NOT author a single-layer
    fix phase scoped to only the one failure named in the blocker body.
    ESCALATION (ADDITIONALLY, only when the orchestrator flagged validation-escalation —
    blocker_kind mcp-validation + retry_count >= 2): the phase must ALSO consume
    INVESTIGATION.md from the spec path shown above (if present) — its Seam Table and
    confirmed Hypothesis-Ledger rows are citable runtime evidence; its Recommended Fix Scope
    seeds the phase's file list. Do NOT bake unproven narrative into the phase as fact —
    unproven hunches are the investigation's job, not the corrective phase's.

  "Defer this {item_label}; continue the rest of the queue":
    Edit the queue.json for this pipeline: move this {item_label}'s entry to the END of
    the queue array (preserve valid JSON). LEAVE BLOCKED.md IN PLACE — do NOT neutralize
    it. The {item_label} stays blocked; it simply no longer heads the queue.

  "Other" (custom directive):
    Enact the operator's NOTES from the ## Resolution section as faithfully as you can
    with Edit/Write/Read/Bash and (if a skill fits) the Skill tool. If the directive
    resolves the blocker, neutralize BLOCKED.md; if it only changes course, follow the
    note's intent and say so in your summary.

  Neutralizing BLOCKED.md (for every path EXCEPT "Defer"): the state script keys the
  blocked halt on the FILENAME BLOCKED.md (NOT a frontmatter field), so a kind: edit does
  NOT clear the halt:

<!-- @section neutralize-blocked-feature pipelines=feature modes=workstation,cloud -->
     python3 ~/.claude/scripts/lazy-state.py --neutralize-sentinel <sentinel_path>

<!-- @section neutralize-blocked-bug pipelines=bug modes=workstation,cloud -->
     python3 ~/.claude/scripts/bug-state.py --neutralize-sentinel <sentinel_path>

<!-- @section neutralize-blocked-note pipelines=feature,bug modes=workstation,cloud -->
  The script performs the canonical rename to BLOCKED_RESOLVED_<YYYY-MM-DD>.md
  (git-mv-aware, collision-safe — appends a numeric suffix if the target name already
  exists). Manual fallback (only if the script is unavailable): git mv. NEVER just flip
  a frontmatter field (this is a real bug that was hit in practice — the rename is
  mandatory).

  Then commit per .claude/skill-config/commit-policy.md (or the standard pattern); message
  (substitute the item id and chosen path shown above): `docs(<item_id>): enact blocker resolution (<chosen_path>)`.
  WORK-BRANCH-ONLY: commit to the CURRENT branch only (git rev-parse --abbrev-ref HEAD at
  start); NEVER create a new branch, NEVER --force.

<!-- @section provisional-steps pipelines=feature,bug modes=workstation,cloud -->
<!-- Applies when resolution_kind == "provisional" (__provisional_accept__, park-provisional-acceptance). -->

Steps (provisional-accept path — resolution_kind: provisional):

The sentinel (the sentinel path shown above — NEEDS_INPUT_PROVISIONAL.md) was ALREADY
provisionally accepted by the script (`--provisionalize-sentinel`): its ## Resolution
carries resolved_by: auto-provisional, a decision_commit sha, and per-decision
**Choice:** lines naming the recommended options taken. Your job is PROPAGATION ONLY:

1. Read the sentinel fully (frontmatter + ## Decision Context + ## Resolution).
2. For EACH decision, propagate the auto-accepted **Choice:** into SPEC.md and/or
   PHASES.md exactly as the needs-input path's step 2 describes — surgical, mechanical,
   no scope changes. Note in your summary any decision with no doc impact.
3. DO NOT NEUTRALIZE AND DO NOT RENAME the sentinel. NEEDS_INPUT_PROVISIONAL.md is the
   operator's ratification claim-check: it must SURVIVE until the operator ratifies or
   redirects (the completion gates key on it). Renaming or resolving it here would
   silently waive the operator's deferred authority — that is the one hard failure mode
   of this path.
4. Commit per .claude/skill-config/commit-policy.md (or the standard pattern); message:
   `docs(<item_id>): propagate provisionally-accepted decision(s) into SPEC/PHASES`.
   WORK-BRANCH-ONLY, never a new branch, never --force.

<!-- @section ratify-redirect-steps pipelines=feature,bug modes=workstation,cloud -->
<!-- Applies when resolution_kind == "ratify-redirect" (provisional-ratification redirect). -->

Steps (ratification-redirect path — resolution_kind: ratify-redirect):

The operator REDIRECTED one or more provisionally-accepted decisions: the sentinel's
appended ## Ratification section (outcome: redirected) names the NEW choice(s); the
earlier ## Resolution (resolved_by: auto-provisional) names the OLD auto-accepted
choice(s) and the decision_commit sha recorded at acceptance time.

1. Read the sentinel fully (Decision Context + Resolution + Ratification).
2. Propagate each REDIRECTED choice into SPEC.md / PHASES.md, replacing the design
   narrative the provisional propagation wrote for the old choice. Ratified (unchanged)
   decisions need no edits.
3. Scope the implementation correction: run
   `git diff --stat <decision_commit>..HEAD -- <the {item_label}'s paths>` — that diff is
   the ONLY code that could embody the old choice. Author ONE corrective phase in
   PHASES.md (follow the /add-phase conventions — you MAY use the Skill tool to invoke
   /add-phase): `**Phase kind:** corrective`, In-progress, unchecked deliverables that
   re-align exactly the affected surfaces from that diff to the redirected choice. Do NOT
   revert commits; forward-fix.
4. Neutralize the sentinel so the halt clears:

<!-- @section neutralize-provisional-feature pipelines=feature modes=workstation,cloud -->
     python3 ~/.claude/scripts/lazy-state.py --neutralize-sentinel <sentinel_path>

<!-- @section neutralize-provisional-bug pipelines=bug modes=workstation,cloud -->
     python3 ~/.claude/scripts/bug-state.py --neutralize-sentinel <sentinel_path>

<!-- @section ratify-redirect-tail pipelines=feature,bug modes=workstation,cloud -->
   (canonical rename → NEEDS_INPUT_PROVISIONAL_RESOLVED_<YYYY-MM-DD>.md, git-mv-aware,
   collision-safe; never a frontmatter kind: flip). The corrective phase's unchecked
   deliverables re-enter the {item_label} in the queue naturally on the next probe.
5. Commit; message: `docs(<item_id>): apply ratification redirect (<chosen_path>) + corrective phase`.
   WORK-BRANCH-ONLY, never a new branch, never --force.

<!-- @section push-rule-workstation pipelines=feature,bug modes=workstation -->
Push the work branch after committing: git push origin $(git rev-parse --abbrev-ref HEAD).

<!-- @section push-rule-cloud pipelines=feature,bug modes=cloud -->
Push IMMEDIATELY after each commit (container-reclaim durability): git push origin $(git rev-parse --abbrev-ref HEAD) after every commit, not just at the end.

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- You do NOT run git commit or git push without valid local changes ready to commit. Do not create empty commits.
- You do NOT run git commit or git push to any remote other than the current branch. NEVER force-push. NEVER create a new branch.
- You MAY NOT spawn further subagents (no Agent tool). You MAY use the Skill tool for /add-phase or /plan-bug if the resolution calls for it, and Edit/Write/Read/Bash for all other work.
- You MAY edit SPEC.md, PHASES.md, and the sentinel file — this dispatch exists to authorize exactly those edits.
- Sentinel neutralization (rename) is mandatory for all paths EXCEPT (a) the "Defer" blocked-resolution path, which deliberately LEAVES BLOCKED.md IN PLACE, and (b) the resolution_kind: provisional path, which MUST NOT touch the NEEDS_INPUT_PROVISIONAL.md filename (it is the operator's ratification claim-check).
- The receipt-GATED terminal status ({receipt_gated_status}) must NOT be set on any {item_label} doc unless a valid {receipt_name} receipt already exists — it is receipt-owned. The receipt-EXEMPT terminal status ({receipt_exempt_status}) is DIFFERENT: it carries no receipt (retired-without-a-fix), so the receipt gate does not apply to it — you MAY set it, but ONLY when the operator's chosen resolution directs closing this {item_label} (the needs-input terminal-disposition step 2b above). Never set {receipt_exempt_status} on your own initiative.

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return a one-paragraph summary (under 8 lines) covering:
- Which files were edited and which sections changed.
- How each choice was applied (or why it was a no-op against SPEC/PHASES).
- Whether the sentinel was neutralized (and to what filename) or deliberately kept (Defer path).
- If step 3b promoted a follow-up sentinel (needs-input path), name which file was promoted.
- The commit hash.
