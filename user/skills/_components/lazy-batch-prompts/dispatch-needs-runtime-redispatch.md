<!-- @requires item_name,spec_path,original_cycle_prompt_note,item_id,cwd -->
<!-- dispatch-needs-runtime-redispatch.md — emitted by emit_dispatch_prompt("needs-runtime-redispatch", ...)
     Derived from lazy-batch/SKILL.md Step 1d.0 NEEDS_RUNTIME recovery. When a no-runtime
     mcp-test cycle returns the single line NEEDS_RUNTIME (it found an MCP-testable surface
     the plan declared as not-required), the orchestrator boots the runtime and re-dispatches
     the same cycle with the RUNTIME IS ALREADY UP block. This template is the registered
     form of that re-dispatch so the validate hook can verify it.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section header pipelines=feature,bug modes=workstation,cloud -->
You are running a NEEDS-RUNTIME re-dispatch of an mcp-test cycle for the autonomous pipeline. A prior mcp-test run returned NEEDS_RUNTIME — it discovered an MCP-testable surface that the plan's "MCP runtime: not-required" declaration missed.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
Spec path:        {spec_path}
Original cycle note: {original_cycle_prompt_note}

<!-- @section role pipelines=feature,bug modes=workstation -->
The orchestrator has now booted the Tauri dev runtime. Your job is to run the mcp-test cycle properly against the live runtime.

<!-- @section role-cloud pipelines=feature,bug modes=cloud -->
Cloud runs cannot boot the Tauri runtime, so this re-dispatch cannot complete here — record the trigger and defer to a workstation run (see below).

<!-- @section workstation-job pipelines=feature,bug modes=workstation -->
RUNTIME IS ALREADY UP — the orchestrator pre-booted tauri:dev before this dispatch. The MCP HTTP server is ready. Proceed with the /mcp-test skill exactly as if the runtime had always been required: invoke /mcp-test via the Skill tool in batch mode, connect to the live MCP server, execute the test scenarios from the mcp-tests/ directory under the spec path shown above, write MCP_TEST_RESULTS.md with the results, and return the skill's structured summary.

Steps:
1. Invoke the /mcp-test skill (via the Skill tool) in batch mode. This cycle is a REAL mcp-test cycle — run it fully and inline (no Agent tool available inside the dispatched subagent).
2. Write MCP_TEST_RESULTS.md to the spec path shown above per the sentinel schema (result, pass_count, total_count, validated_commit: HEAD, scenarios).
3. Commit with message `test(<item_id>): mcp-test results (runtime re-dispatch)` (use the item id shown above). WORK-BRANCH-ONLY.
4. Push the work branch.

<!-- @section cloud-job pipelines=feature,bug modes=cloud -->
CLOUD RUN — the Tauri dev runtime is not available in this cloud session. Record this NEEDS_RUNTIME trigger (one line in the cycle log and in BLOCKED.md or notes under the spec path shown above) and DEFER the mcp-test dispatch to a workstation run. Write a brief note explaining: the plan declared MCP runtime as not-required but the test cycle found a testable surface; a workstation run is needed to complete validation.

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- You do NOT run git commit or git push without valid local changes ready to commit. Do not create empty commits.
- You do NOT run git commit or git push to any remote other than the current branch. NEVER force-push. NEVER create a new branch.
- The failed attempt + this re-dispatch together consume ONE forward cycle (the orchestrator increments once, after this re-dispatched cycle returns).
- The {forbidden_status} status must NOT be set on any {item_label} doc unless a valid {receipt_name} receipt already exists.

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return the /mcp-test skill's structured summary containing:
- result (all-passing / partial / failed / deferred-cloud)
- pass_count and total_count
- validated_commit (HEAD at test time, or "deferred" for cloud)
- scenario outcomes (name, status, assertion details for each)
- MCP_TEST_RESULTS.md path (or "deferred" for cloud runs)
- commit hash (or "deferred" for cloud runs)
