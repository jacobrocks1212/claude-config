<!-- @requires item_name,spec_path,symptom,trigger,inherited_hypotheses,item_id,cwd -->
<!-- dispatch-investigation.md — emitted by emit_dispatch_prompt("investigation", ...)
     Derived from investigation-dispatch.md. This template is the script-emitted,
     registry-registered form of the on-demand /investigate cycle dispatch that the
     orchestrator previously composed by hand. Emitted by the orchestrator at one of
     three triggers: validation escalation, failed-fix repeat, or inline-diagnosis
     budget exhaustion. Cloud runs defer dispatch to a workstation run.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section role pipelines=feature,bug modes=workstation,cloud -->
You are running an on-demand root-cause INVESTIGATION cycle for the autonomous pipeline. Invoke the /investigate skill (via the Skill tool) and follow it exactly. You may NOT spawn subagents (no Agent tool). You MAY use the Skill tool for /investigate, and Read/Grep/Glob/Bash/Edit/Write for the investigation itself.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
{item_label} dir:  {spec_path}
Trigger:           {trigger}
Symptom:           {symptom}

<!-- @section inherited-hypotheses pipelines=feature,bug modes=workstation,cloud -->
Inherited hypotheses (ALL status: unproven — these are hypotheses to TEST, not evidence;
refute them as readily as you confirm them):
{inherited_hypotheses}

<!-- @section contract-reminders pipelines=feature,bug modes=workstation,cloud -->
Contract reminders (the skill carries the full rules — these are the ones that void the cycle if violated):
- NO production fixes. Allowed commits: INVESTIGATION.md, diag({item_id}): off-hot-path instrumentation (revert or disclose-retained), tests driving REAL components.
- NO fire-and-forget: blocking foreground waits; INVESTIGATION.md is on disk before you return, whatever the status.
- Verify binary freshness before trusting any observation.
- Every hypothesis verdict cites an evidence artifact; "inconclusive" with an honest seam table beats a confident guess.
- NO narrative as fact: do NOT pass orchestrator hypotheses forward as "strong hypothesis" or "solid evidence" headers. Unproven hunches are labeled "unproven" explicitly (the no-narrative-as-fact rule in investigation-dispatch.md is binding).
- WORK-BRANCH-ONLY: commit and push to the CURRENT branch only (git rev-parse --abbrev-ref HEAD at start); NEVER create a new branch, NEVER --force.

<!-- @section workstation-note pipelines=feature,bug modes=workstation -->
This is a workstation run — the Tauri runtime, MCP HTTP server, audio device, and all live probes are available. Dispatch immediately.

<!-- @section cloud-note pipelines=feature,bug modes=cloud -->
CLOUD RUN: /investigate needs the live runtime. Record this trigger (one line in the cycle log and in BLOCKED.md/notes) and DEFER dispatch to a workstation run instead of dispatching now. Do NOT attempt to run /investigate in this cloud session.

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- You do NOT run git commit or git push without valid local changes ready to commit. Do not create empty commits.
- You do NOT run git commit or git push to any remote other than the current branch. NEVER force-push. NEVER create a new branch.
- The {forbidden_status} status must NOT be set on any {item_label} doc unless a valid {receipt_name} receipt already exists.

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return the /investigate skill's structured summary containing:
- status (confirmed / inconclusive / deferred-to-workstation)
- seam-table delta (which seams were probed, which were confirmed/refuted/inconclusive)
- hypothesis verdicts (each labeled confirmed / refuted / inconclusive with cited evidence artifact)
- instrumentation disposition (reverted / retained-disclosed / none)
- artifact path ({spec_path}/INVESTIGATION.md or "deferred" for cloud runs)
