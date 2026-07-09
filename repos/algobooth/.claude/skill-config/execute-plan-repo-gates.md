<!-- AlgoBooth-specific /execute-plan gate policy. Injected into /execute-plan via
     `!cat .claude/skill-config/execute-plan-repo-gates.md` — resolves only when the session
     cwd is an AlgoBooth checkout with this file materialized; every other repo gets the
     one-line fallback comment. Extracted from /execute-plan's body (lean-plan-files follow-up)
     so non-AlgoBooth sessions stop paying ~3.4KB of AlgoBooth-only policy per invocation.
     The GENERIC escalation/batch-frequency rules live in
     ~/.claude/skills/_components/quality-gates.md — this file only maps them to AlgoBooth
     commands and carries the AlgoBooth-only F8 scenario lint. -->

#### Quality Gate escalation (AlgoBooth — MANDATORY when running QG)

When the plan's Quality Gates step runs, the gate level is right-sized per the **Batch frequency** rule in `~/.claude/skills/_components/quality-gates.md`. On AlgoBooth:
- Workspace Rust QG: `npm run qg -- rust` — clippy, rustfmt, and the full workspace test suite. REQUIRED at plan-part completion and on any escalation-triggering batch.
- Targeted `cargo test -p <crate>` is ACCEPTABLE on intermediate batches only (not the part's last batch, not an escalation-triggering batch).
- Mixed-language batches: `npm run qg` (all gates).

The full workspace gate must actually run AND pass before the plan part flips to `Complete` — record the part-end full-QG run + result in the Implementation Notes block. The `/lazy-batch-retro` auditor counts `Bash:qg` calls per cycle; ≥ 1 full-workspace `npm run qg` per plan part (plus one per escalation-triggering batch) is the audit signal — a part closed on targeted runs alone is INCOMPLETE.

#### MCP Scenario Surface Lint (F8 — if this batch authored or modified an mcp-tests scenario)

If a batch authored or modified **any** MCP test scenario under a feature's `mcp-tests/` or `docs/testing/mcp-tests/` directory, run the surface-existence lint as part of that batch's verification (between subagent dispatch and the PHASES.md update):

```bash
python ~/.claude/scripts/surface_resolver.py --lint --repo-root <repo-root> <path/to/scenario.md> [...]
```

**Exit 1 = blocking batch failure** — do NOT proceed to the PHASES.md update or commit. Each `ERROR: <file>:<line> asserts unregistered MCP tool '<name>'` names a scenario line asserting a tool absent from `src-tauri/src/ipc/mcp/registrations/` (and `GOLDEN_TOOL_NAMES`). Either implement the missing tool (add a PHASES.md deliverable), correct the tool name, or — for genuine non-MCP pseudo-steps — suppress with `--allow <name>` (built-in allowlist covers `sleep`).

Rationale (F8 / lazy-validation-readiness): surface gaps used to surface only at Step-9 `/mcp-test`, ~3 cycles after scenario authoring; this lint catches them in the authoring batch at near-zero cost. Skip if the batch touched no `mcp-tests/` scenario.
