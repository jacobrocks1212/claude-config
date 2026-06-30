<!-- @requires item_name,spec_path,uncovered_summary,gate_output,item_id,cwd -->
<!-- dispatch-corrective-coverage.md — emitted by emit_dispatch_prompt("corrective-coverage", ...)
     Derived from mcp-coverage-audit.md Step 4 (D7) + completion-integrity-gate.md, the
     __mark_complete__ / __mark_fixed__ Gate-1 corrective-coverage routing in
     lazy-batch / lazy-bug-batch / lazy-batch-cloud SKILL.md Step 1c.5.
     This template is the script-emitted, registry-registered form of the corrective
     MCP-coverage cycle the orchestrator previously had NO emit path for — so under an
     active run marker the validate-deny guard denied the hand-composed coverage prompt
     and the orchestrator was forced to tear down the run marker (--run-end), dispatch
     un-marked, then --run-start again (harden Round 44, 2026-06-29). With this class the
     coverage cycle is dispatchable marker-active: --emit-dispatch corrective-coverage.
     TOKENS: standard pipeline tokens + @requires keys above. -->

<!-- @section role pipelines=feature,bug modes=workstation,cloud -->
You are running a CORRECTIVE MCP-COVERAGE cycle for the autonomous pipeline. The
`{mark_pseudo}` Gate-1 MCP-coverage audit REFUSED the completion flip because one or more
SPEC Locked Decisions are not covered by any scenario in the {item_label}'s own
`mcp-tests/` directory. Your job: make every uncovered decision covered — by authoring +
running real MCP coverage for the MCP-testable ones, and recording a documented test-exempt
acknowledgement for the genuinely MCP-untestable ones — NEVER by faking coverage. The
completeness-first standing policy (D7) governs: prefer authoring real coverage; exempt only
a decision that falls in a DOCUMENTED untestable class.

{item_label}: {item_name} ({item_id})
Working directory: {cwd}
Spec path:        {spec_path}
Uncovered decisions (from the Gate-1 audit): {uncovered_summary}
Gate refusal output: {gate_output}

<!-- @section job-steps pipelines=feature,bug modes=workstation,cloud -->
Corrective-coverage algorithm:

1. Read `<spec_path>/SPEC.md` (the spec path shown above; the full `## Locked Decisions` surface)
   and `docs/features/mcp-testing/SPEC.md` (the AUTHORITATIVE list of MCP-untestable classes — you
   MUST ground any test-exempt claim in a documented class there; do not improvise an exemption).
   Run the deterministic verdict to see exactly which decisions are uncovered:
     python3 ~/.claude/scripts/lazy-state.py --gate-coverage <spec_path>
   (for a bug, substitute `bug-state.py`). It prints JSON {ok, decisions, uncovered, scenario_count};
   exit 0 iff every decision is covered.

2. Ensure the {item_label}'s `mcp-tests/` directory exists and REGISTER every scenario that
   already passed for this item (a symlink into the corpus is the convention — inspect a
   neighboring item's `mcp-tests/` dir to match the exact pattern; symlinks work on this machine).
   A registered passing scenario whose body names a decision's id/keywords already covers it.

3. For EACH still-uncovered decision, classify and act (D7 — never ask, never write NEEDS_INPUT.md):
   - **MCP-testable (the default, prefer this):** author the missing coverage. Either a
     consolidated `mcp-tests/<item-id>-decision-audit.md` whose assertion blocks EACH cite the
     decision id(s) they validate, or an assertion block citing `<id>` appended to an existing
     scenario whose setup already exercises the path. The audit greps scenario files for the
     literal id (e.g. `L3`) OR ≥2 of the decision's keywords.
   - **Documented-MCP-untestable:** the decision falls in an untestable class per
     `docs/features/mcp-testing/SPEC.md` (internal dependency/impl choices with no MCP-observable
     behavior are the canonical case) → write a per-decision test-exempt acknowledgement into
     SPEC.md (in `## Locked Decisions` or a new `## MCP Coverage Exemptions` section) carrying the
     one-line reason, the mcp-testing/SPEC.md class it falls under, and the alternative validation
     (cite the concrete unit-test path). The audit treats an acknowledged decision as covered.

4. Re-run `--gate-coverage <spec_path>` and iterate (register / author / exempt) until it returns
   `ok: true`, `uncovered: []`, exit 0. Then run `npm run qg:docs-consistency` and confirm errors=0
   for this item.

5. Do NOT flip SPEC/PHASES top Status to {forbidden_status} and do NOT write the {receipt_name}
   receipt — the orchestrator owns the final completion flip after re-auditing. Your job ends at:
   gate-coverage clean + committed + pushed.

<!-- @section run-scenarios-workstation pipelines=feature,bug modes=workstation -->
RUNNING NEW SCENARIOS (workstation): the live dev runtime is orchestrator-owned and already UP
(MCP server on the configured port, health 200). REUSE it — do NOT boot/restart/kill it (no
`npm run dev:*`, no `dev:kill`). Run any new/updated scenario against the live runtime exactly as
`/mcp-test` does (the deterministic engine `scripts/mcp-test/run.ts`, or direct MCP tool calls), and
confirm it passes before ticking. If a new scenario you authored cannot pass against the live
runtime, that is real outstanding work — leave the decision uncovered and report it; do not fake a pass.

<!-- @section run-scenarios-cloud pipelines=feature,bug modes=cloud -->
RUNNING NEW SCENARIOS (cloud): cloud has NO Tauri / no MCP server / no audio device, so you CANNOT
run a scenario here. AUTHOR the `mcp-tests/` coverage (and the SPEC test-exempt notes) docs-only, and
let the scenario RUN defer to workstation per the normal cloud MCP deferral — the next workstation
`/lazy` run executes the new scenario. Gate-1 coverage is a docs-only audit (it greps scenario files),
so authoring the scenario file here is sufficient to clear the audit; the RUN is what defers.

<!-- @section constraints pipelines=feature,bug modes=workstation,cloud -->
CONSTRAINTS:
- WORK-BRANCH-ONLY: commit + push to the CURRENT branch only (`git rev-parse --abbrev-ref HEAD` at
  start); NEVER create a branch, NEVER `git checkout -b` / `git switch -c` / `git branch <new>`,
  NEVER --force. A stray branch strands your scenario/SPEC edits where the state scripts cannot see them.
- NEVER fake coverage: a scenario that does not genuinely assert a decision, or a test-exempt note
  not grounded in a documented mcp-testing/SPEC.md class, is a Gate-1 integrity violation.
- You MAY NOT spawn further subagents (no Agent tool). Use Read/Grep/Glob/Bash/Edit/Write + MCP tools.
- Scope is STRICTLY MCP-coverage for the uncovered decisions. Do not perform unrelated implementation,
  do not touch unrelated SPEC/PHASES content. Do not write the {receipt_name} receipt or flip top Status.
- The {forbidden_status} status must NOT be set on any {item_label} doc unless a valid {receipt_name}
  receipt already exists.

<!-- @section push-rule-workstation pipelines=feature,bug modes=workstation -->
Push the work branch after committing: git push origin $(git rev-parse --abbrev-ref HEAD).

<!-- @section push-rule-cloud pipelines=feature,bug modes=cloud -->
Push IMMEDIATELY after each commit (container-reclaim durability): git push origin $(git rev-parse --abbrev-ref HEAD) after every commit.

<!-- @section return-format pipelines=feature,bug modes=workstation,cloud -->
GROUND-TRUTH OUTPUT — return a one-paragraph summary (under 8 lines) covering:
- Per-decision disposition: covered-by-registered-scenario / authored-scenario (+ pass result on
  workstation, or deferred-run on cloud) / test-exempt (+ the documented class + cited unit-test path).
- The final `--gate-coverage` verdict (MUST be ok/clean, exit 0) and the qg:docs-consistency result.
- Files changed and the commit hash(es) pushed.
- Anything you could NOT cover honestly (name the decision + why) — an honest gap is the correct
  signal, not a defect to fake around.
