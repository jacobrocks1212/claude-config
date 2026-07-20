<!-- @requires item_name,spec_path,gate_output,item_id,cwd -->
<!-- dispatch-coherence-recovery.md — emitted by emit_dispatch_prompt("coherence-recovery", ...)
     Derived from lazy-batch/SKILL.md Step 1c.5 __mark_complete__ gate-2 refusal path
     (completion-integrity gate) + --apply-pseudo mechanical third gate refusal path.
     When --apply-pseudo or Gate 2 returns ok: false due to PHASES.md coherence issues
     (unchecked boxes, wrong phase Status), the orchestrator dispatches this cycle to
     reconcile PHASES.md honestly before retrying the gate.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section role pipelines=feature,bug modes=workstation,cloud -->
You are running a COHERENCE-RECOVERY cycle for the autonomous pipeline. The completion gate refused to proceed because PHASES.md is in an incoherent state — phases have unchecked deliverable boxes, incorrect Status values, or missing verification evidence. Your job is to reconcile PHASES.md honestly so the gate can pass on the next attempt.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
Spec path:        {spec_path}
Gate refusal output: {gate_output}

<!-- @section job-steps pipelines=feature,bug modes=workstation,cloud -->
Coherence-recovery algorithm:

1. Read PHASES.md (in the spec path shown above) in full. Read the gate refusal output carefully to identify exactly which phases, WUs, or status fields are incoherent.

2. For each named incoherence, reconcile HONESTLY:
   - Unchecked WU boxes: tick ONLY when there is on-disk evidence that the work was actually done (code file exists, test passes, commit landed, sentinel written). If the evidence does not exist, DO NOT tick — instead add a brief note next to the box explaining what is missing and flag it for the next implementation cycle.
   - Phase Status mismatch: flip to Complete only when ALL deliverable boxes in the phase are ticked — verification rows INCLUDED (the --apply-pseudo third gate refuses on ANY unchecked box, including verification rows; by coherence-recovery time, the verification exemption's job is done). If the gate_output names specific unchecked verification rows as the refusal reason, those rows must also have on-disk evidence (VALIDATED.md or MCP_TEST_RESULTS.md) before they can be ticked. Re-open a phase (set back to In-progress) if any box is unticked.
   - Missing or wrong-format entries: correct the frontmatter to match the schema the gate expects.

3. Do NOT tick unverified boxes. Do NOT fabricate evidence. If work is genuinely incomplete, the honest outcome is an In-progress phase with unticked boxes — this is the correct signal that sends the pipeline back to implementation, not a gate defect to work around.

3a. **TERMINAL ESCALATION — honest-stuck on un-runnable verification rows (do NOT re-loop).** After reconciling, evaluate whether this cycle can make ANY forward progress. If ALL of the following hold, the loop CANNOT progress and you MUST escalate instead of returning a no-op that re-loops the gate:
   - you ticked / migrated / re-scoped **0 rows** this cycle (nothing changed — no commit would be produced by step 4), AND
   - **0 genuine incomplete IMPLEMENTATION deliverables** remain (every still-`- [ ]` blocking row is a Runtime-Verification / MCP-assertion row, NOT ordinary implementation work — a genuine implementation gap correctly routes back to implementation and is NOT this case), AND
   - **≥1** of those verification rows cannot be ticked because its verification **genuinely never ran on this host** (no on-disk evidence — infra-gated backend behaviour, or a buildable-but-unbuilt scenario), so no honest reconciliation this cycle OR any future identical cycle can clear it.

   When that holds, the `__mark_complete__` / `__mark_fixed__` mechanical gate will refuse identically on the next probe → an oscillation with no terminal. Break it: write a `NEEDS_INPUT.md` into the spec path shown above, escalating to the operator (this is the SAME step-4 escalation `completion-integrity-gate.md` already owns — you are invoking it from within its remediation loop). Use the canonical `kind: needs-input` schema with `written_by: completion-integrity-gate` (rule 5 of `sentinel-frontmatter.md` correctly excludes this writer from provisional auto-accept — an integrity halt the operator must resolve), `next_skill: lazy`, and one decision per the honest-stuck gap, e.g. *"managed-llm-credits blocked at completion only on verification rows that never ran on this host (Phase 1 live-OAuth JWT capture, Phase 4 credits-proxy reachability, Phase 7 Purchase-CTA ui_action, Phase 8 toggle cross-reopen) — resolve per turn-routing-enforcement NEEDS_INPUT decisions #2 (partial-VALIDATED completion), #5 (per-row host-capability deferral), #6 (corrective-coverage dispatch)."* In the `## Decision Context` body, list the un-runnable rows explicitly (phase + row text + why it could not run) and cross-reference decisions #2/#5/#6. **This is the ONLY sentinel this cycle is authorised to write, and ONLY in this terminal case** — you do NOT resolve the design fork (that is operator-owned), you SURFACE it deterministically so the pipeline halts on `needs-input` instead of oscillating. Commit it with message `docs(<item_id>): coherence-recovery escalation — un-runnable verification rows need operator input` and return the escalation summary. Do NOT also perform step 4 (there is nothing to reconcile).

4. Otherwise (you ticked/re-scoped ≥1 row, OR a genuine implementation deliverable remains → normal in-progress re-route): commit the updated PHASES.md with message `chore(<item_id>): coherence-recovery — reconcile PHASES.md for gate retry` (use the item id shown above). WORK-BRANCH-ONLY: commit to the CURRENT branch only (git rev-parse --abbrev-ref HEAD at start); NEVER create a new branch, NEVER --force.

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- You do NOT run git commit or git push without valid local changes ready to commit. Do not create empty commits.
- You do NOT run git commit or git push to any remote other than the current branch. NEVER force-push. NEVER create a new branch.
- You MAY NOT spawn further subagents (no Agent tool). Use Read/Grep/Glob/Bash/Edit/Write directly.
- Scope is STRICTLY PHASES.md coherence. Do not perform implementation work, do not modify SPEC.md content, do not write receipts or sentinels beyond what the reconciliation requires. The SOLE exception is the step-3a terminal escalation, which authorises writing `NEEDS_INPUT.md` (and only that sentinel) when the loop is honest-stuck on un-runnable verification rows.
- NEVER blind-tick: ticking an unchecked box without on-disk evidence is a gate integrity violation. The gate exists to ensure the evidence is real. When honest reconciliation cannot clear the residual verification rows because they never ran on this host, the correct action is the step-3a `NEEDS_INPUT` escalation — NOT ticking, and NOT silently re-looping.
- The {forbidden_status} status must NOT be set on any {item_label} doc unless a valid {receipt_name} receipt already exists.

<!-- @section push-rule-workstation pipelines=feature,bug modes=workstation -->
Push the work branch after committing: git push origin $(git rev-parse --abbrev-ref HEAD).

<!-- @section push-rule-cloud pipelines=feature,bug modes=cloud -->
Push IMMEDIATELY after committing (container-reclaim durability): git push origin $(git rev-parse --abbrev-ref HEAD).

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return a one-paragraph summary (under 6 lines) covering:
- Which phases and WUs were reconciled and how (ticked with evidence / left unticked with explanation / status corrected).
- Any WUs that could NOT be ticked due to missing evidence (name them explicitly so the next cycle knows what to implement).
- The commit hash (or "no commit needed" if PHASES.md was already coherent).
- **If you took the step-3a terminal escalation:** state `ESCALATED` explicitly, name the un-runnable verification rows, and give the `NEEDS_INPUT.md` commit hash — so the orchestrator knows the next probe surfaces `needs-input` and does NOT re-dispatch coherence-recovery.
