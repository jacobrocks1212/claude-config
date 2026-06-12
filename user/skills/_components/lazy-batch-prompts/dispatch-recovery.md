<!-- @requires item_name,spec_path,failure_summary,cwd,item_id -->
<!-- dispatch-recovery.md — emitted by emit_dispatch_prompt("recovery", ...)
     Derived from lazy-batch/SKILL.md Step 1e.4a (post-execute-plan ledger-consistency
     guard recovery dispatch) and Step 0.6 recovery patterns. This template is the
     script-emitted, registry-registered form of the recovery cycle the orchestrator
     previously composed by hand after a ledger guard or consistency check failure.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section role pipelines=feature,bug modes=workstation,cloud -->
You are running a RECOVERY cycle for the autonomous pipeline. A prior cycle ended with an inconsistent or incomplete state that the orchestrator detected via its ledger-consistency guard. Your sole job is to bring the working tree and sentinel state back to a consistent baseline so the next normal cycle can proceed.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
Spec path:        {spec_path}
Failure summary:  {failure_summary}

<!-- @section job-steps pipelines=feature,bug modes=workstation,cloud -->
Recovery algorithm:

1. Read the failure summary carefully. The named failing_check identifies exactly what is inconsistent — do not guess or broaden scope beyond what the check named.

2. Reconcile per the failing_check:
   - clean_tree: stage + commit any uncommitted residue (legitimate artifacts only — do not commit unrelated work or speculative changes). Then push.
   - head_matches_origin: push the current branch to origin (git push origin <current-branch>).
   - plan_complete: the plan-part frontmatter status: field is not Complete even though all its WUs are ticked. Re-flip status: to Complete. Commit + push.
   - deliverables_done: tick a verification box ONLY when there is on-disk evidence that verification actually ran (VALIDATED.md or MCP_TEST_RESULTS.md present in the spec path shown above and covering that row). If verification boxes are unticked AND no such evidence exists, DO NOT tick them — instead write NEEDS_INPUT.md into that spec path (written_by: recovery, describing the gap) and commit it. Surface the issue; do not silently tick unverified boxes.

3. After reconciling, re-run the verify-ledger check to confirm ok. Report its output in your return summary.

   When the failure summary above names a specific plan file (e.g. "plan_complete failing for
   plans/part-3.md"), use the plan-scoped form — this avoids false-fails from still-pending
   later plan parts (cite: live-run false alarm 2026-06-11 where a plan-level check
   incorrectly flagged In-progress parts beyond the one just executed):

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- You do NOT run git commit or git push without valid local changes ready to commit. Do not create empty commits.
- You do NOT run git commit or git push to any remote other than the current branch. NEVER force-push. NEVER create a new branch.
- You MAY NOT spawn further subagents (no Agent tool). Use Read/Grep/Glob/Bash/Edit/Write directly.
- Scope is STRICTLY the named failing_check. Do not perform implementation work, do not touch SPEC.md or PHASES.md content beyond the specific flip/commit needed to reconcile the guard.
- The {forbidden_status} status must NOT be set on any {item_label} doc unless a valid {receipt_name} receipt already exists.

<!-- @section verify-ledger-feature pipelines=feature modes=workstation,cloud -->
Re-run verify-ledger (feature pipeline). Substitute <cwd> with the working directory and
<spec_path> with the spec path, both shown above:
  # Standard form (feature-level — use when the failure summary above names no plan file):
   python3 ~/.claude/scripts/lazy-state.py --repo-root <cwd> --verify-ledger <spec_path>
  # Plan-scoped form (use when the failure summary above names a plan file <plan_file>):
  #   python3 ~/.claude/scripts/lazy-state.py --repo-root <cwd> --verify-ledger <spec_path> --plan <plan_file>
  # The plan-scoped form checks only the named plan part's WUs — later plan parts
  # that are still In-progress do NOT cause a false-fail (the false-alarm fix).

<!-- @section verify-ledger-bug pipelines=bug modes=workstation,cloud -->
Re-run verify-ledger (bug pipeline). Substitute <cwd> with the working directory and
<spec_path> with the spec path, both shown above:
  # Standard form (bug-level — use when the failure summary above names no plan file):
   python3 ~/.claude/scripts/bug-state.py --repo-root <cwd> --verify-ledger <spec_path>
  # Plan-scoped form (use when the failure summary above names a plan file <plan_file>):
  #   python3 ~/.claude/scripts/bug-state.py --repo-root <cwd> --verify-ledger <spec_path> --plan <plan_file>
  # The plan-scoped form checks only the named plan part's WUs — later plan parts
  # that are still In-progress do NOT cause a false-fail (the false-alarm fix).

<!-- @section push-rule-workstation pipelines=feature,bug modes=workstation -->
Push the work branch after each commit: git push origin $(git rev-parse --abbrev-ref HEAD).

<!-- @section push-rule-cloud pipelines=feature,bug modes=cloud -->
Push IMMEDIATELY after each commit (container-reclaim durability): git push origin $(git rev-parse --abbrev-ref HEAD) after every commit.

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return a one-paragraph summary (under 6 lines) covering:
- The named failing_check and what action was taken to reconcile it.
- Files changed (if any) and the commit hash (or "no commit needed" if the state was already consistent).
- The verify-ledger re-check result (ok: true / ok: false with failing_check named).
