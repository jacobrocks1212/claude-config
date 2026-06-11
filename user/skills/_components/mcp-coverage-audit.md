## MCP-Coverage Audit (inline, docs-only — gate for `__mark_complete__`)

**Why this component exists.** The audit walk surfaced 6 of 20 features whose `__mark_complete__` flipped SPEC to Complete despite the feature's MCP test scenarios not covering every Locked Decision in the SPEC's audit-decision matrix. Root cause: `__mark_complete__` only checks that `VALIDATED.md` + `RETRO_DONE.md` are present — `VALIDATED.md` may attest to the *original* AQ-\* assertions while new decisions added later (via research / research-followup / inline edits) never got carved into MCP scenarios. The flip happens silently and the operator only catches it during a downstream audit walk (the recurring 16-hour retroactive realignment cost the audit-walk retro identified).

This component is the gate. The `__mark_complete__` consumer runs it BEFORE the actual ROADMAP/SPEC flip. If any Locked Decision is uncovered, the consumer refuses the flip this cycle and — per the completeness-first standing policy (D7, `~/.claude/skills/_components/completeness-policy.md` §4) — routes directly to **authoring the missing coverage** (or, for documented MCP-untestable decisions, recording a test-exempt acknowledgement). Gate 1 never asks the operator: no `NEEDS_INPUT.md` is written for coverage gaps. (Pre-D7, this gate wrote `NEEDS_INPUT.md` per Q2 of the audit-walk retro design and deferred to the decision-resume mechanism — that outcome is superseded.)

The audit is docs-only — it reads SPEC.md and `mcp-tests/*.md` and runs no Tauri / no MCP server / no shell execution beyond `grep`. It therefore runs identically in cloud and workstation.

### Inputs

- `{spec_path}` — the feature directory (e.g. `docs/features/d8/d8-stem-management/`).
- `{feature_id}` — the feature directory basename.

### Algorithm

1. **Enumerate the SPEC's Locked Decisions.** Parse `{spec_path}/SPEC.md` for the canonical Locked-Decision surface. Candidates, in priority order — use the first one that exists in the SPEC:
   - A `## Locked Decisions` H2 with a table whose first column is the decision ID (e.g. `L1`, `L2`, ...) or a one-line decision title.
   - A `## Resolved by Research` H2 with `- [x]` bullets (each bullet is one resolved decision).
   - A numbered key-decisions block under a `## Key Decisions` / `## Design Decisions` H2 (each numbered item is one decision).

   For each decision, extract:
   - `id` — the decision identifier (`L1`, `R3`, `K2`, etc.) OR, if the SPEC doesn't number them, a stable slug derived from the first 4 significant words of the decision title.
   - `keywords` — the 2-4 most distinctive content words from the decision title (drop articles, prepositions, generic verbs). Used as anchor terms for the MCP-coverage grep.

   If NO Locked-Decision surface exists in the SPEC, log a chat-output note (`ℹ MCP-coverage audit: SPEC has no Locked Decisions table — no decisions to cover, audit passes vacuously.`) and return clean. (Older specs without a Locked-Decision section have no audit surface; the rule is best-effort and does not gate on its own absence.)

2. **Enumerate the MCP scenarios that own this feature.** List `{spec_path}/mcp-tests/*.md` (the per-feature scenario symlinks `/lazy` maintains). For each, read the file content. If the directory is empty AND `{spec_path}/SKIP_MCP_TEST.md` exists, check its `granted_by` field:
   - `granted_by: operator` (or `granted_by` absent — legacy files without the field are treated as operator-granted for backward compatibility): treat the skip as a legitimate test-exempt grant (audit passes vacuously — an operator already decided MCP testing isn't applicable for this feature).
   - `granted_by: pipeline`: **do NOT treat as a valid coverage waiver.** A pipeline-self-granted skip is not an operator-confirmed decision. Treat it exactly as if no `SKIP_MCP_TEST.md` existed — ALL decisions are uncovered and route to the Step 4 D7 outcome (author real coverage — the most complete path — unless a decision is documented MCP-untestable, in which case the test-exempt acknowledgement supersedes the unconfirmed skip for that decision).
   If the directory is empty AND no `SKIP_MCP_TEST.md`, treat ALL decisions as uncovered (Step 4 routes them to coverage authoring — the consolidated-scenario pattern is the default).

3. **Cross-reference each decision against the scenario content.** For each Locked Decision:
   - Grep each `mcp-tests/*.md` file for the decision's `id` (literal match, e.g. `L4`) AND for any of the `keywords` (case-insensitive substring match).
   - A decision is **covered** iff at least one scenario file contains the `id` literal OR contains at least 2 of the decision's `keywords` (the 2-keyword threshold avoids false positives from single common words).
   - A decision carrying a **test-exempt acknowledgement** in SPEC.md (an exemption note in `## Locked Decisions` or a `## MCP Coverage Exemptions` section — written by a prior Step 4 pass or by hand) also counts as **covered**.
   - A decision is **uncovered** if neither holds.

4. **If any decisions are uncovered — apply the completeness-first standing policy (D7 §4): Gate 1 never asks.** Do NOT write `NEEDS_INPUT.md` and do NOT call `AskUserQuestion`. Classify each uncovered decision:

   - **MCP-testable (the default)** → **route to authoring the missing coverage.** The consumer carries the work through its own cycle machinery as a corrective cycle: author the `mcp-tests/` scenario AND run it. Authoring follows the established patterns — one consolidated `mcp-tests/<feature-id>-decision-audit.md` with N steps × M assertions, each assertion block citing the audit decisions it validates (the dominant pattern the audit walk applied retroactively, 10/20 features; best when ≥ 2 decisions are uncovered), or an assertion block citing `<id>` appended to an existing scenario whose setup already exercises the relevant code path (best for 1-2 decisions). The batch orchestrators dispatch this as a corrective cycle subagent (scenario authoring + `/mcp-test` run); the single-dispatch wrappers perform the docs-only authoring as this invocation's remaining action and let the next invocation run the scenario. The flip stays deferred until the coverage exists (and, on a runtime-capable host, passes).
   - **Documented MCP-untestable** — the decision falls in an untestable class per `docs/features/mcp-testing/SPEC.md` (CHECK that SPEC before claiming this; do not improvise an exemption) → **record a test-exempt acknowledgement**: write a per-decision exemption note into `SPEC.md`'s `## Locked Decisions` section (or a new `## MCP Coverage Exemptions` section) carrying the one-line reason, the mcp-testing SPEC class it falls under, and the alternative validation (e.g. "covered by unit tests in <path>"). Step 3 treats an acknowledged decision as covered on re-run. Still no question.

   Either way, emit one `⚖ policy:` line per uncovered decision (`⚖ policy: coverage for {id} → author scenario | test-exempt ({class})`), add each to the consumer's run-end D7 digest, commit any SPEC exemption notes (`git commit -m "{feature_id}: mcp-coverage audit — test-exempt acknowledgement(s) for <ids>"`), and push the work branch (`git push origin $(git rev-parse --abbrev-ref HEAD)`, 4× backoff retry on network error; work branch only, never main, never force).

5. **Return status to the consumer:**
   - `clean` — no uncovered decisions (including the case where step 4's test-exempt acknowledgements resolved every gap — re-run step 3 against the updated SPEC before returning); consumer proceeds with the actual `__mark_complete__` flip.
   - `uncovered:N` — N decisions still need authored coverage; consumer MUST refuse the flip this cycle, print a one-line halt note (`🛑 mcp-coverage audit: {N} uncovered locked decision(s) — routing to corrective coverage authoring; mark-complete deferred.`), route the authoring work per Step 4 (corrective cycle in batch; this-invocation docs action in the wrappers), and return. NO `NEEDS_INPUT.md`, no operator question — once the scenario(s) exist (and pass where runnable), the next mark-complete attempt's audit returns `clean`.

### Interactive vs `--batch` / cloud behavior

The audit logic is identical in all three contexts. Only the corrective-cycle routing differs (under D7, NO context asks the operator):

| Context | `uncovered:N` behavior |
|---------|------------------------|
| `/lazy` interactive | Wrapper prints the halt note; the invocation's remaining action is the docs-only coverage authoring (scenario file / exemption note) per Step 4. The next `/lazy` invocation runs the new scenario via `/mcp-test` and then re-attempts `__mark_complete__` — the re-run audit returns `clean`. |
| `/lazy-cloud` interactive | Same authoring (docs-only, runs in cloud); the scenario RUN defers to workstation per the normal cloud MCP deferral. |
| `/lazy-batch` / `/lazy-batch-cloud` Step 1c.5 (`__mark_complete__` pseudo-skill) | Orchestrator records the halt note in `cycle_log`, dispatches a corrective cycle subagent to author the scenario(s) (+ run them on workstation; cloud defers the run), emits the `⚖ policy:` line(s) + D7-digest entries, and returns to Step 1a. No `needs-input` terminal fires for coverage gaps; the next mark-complete attempt re-audits `clean`. |
| `/lazy-bug` `__mark_fixed__` (Gate 1) | Same pre-flip audit logic and D7 routing; consumers pass `{bug_id}` where feature consumers pass `{feature_id}`. |
| `/lazy-bug-batch` Step 1c.5 `__mark_fixed__` (Gate 1) | Same as the feature batch orchestrators — corrective cycle, then the next mark-fixed attempt re-audits. |

### Coupling note

This component is consumed by `__mark_complete__` in all four /lazy-family skills and by `__mark_fixed__` in the bug pipeline (consumers pass `{bug_id}` rather than `{feature_id}`):
- `user/skills/lazy/SKILL.md` Step 3 `__mark_complete__`
- `user/skills/lazy-batch/SKILL.md` Step 1c.5 `__mark_complete__` pseudo-skill
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` Step 3 `__mark_complete__`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` Step 1c.5 `__mark_complete__` pseudo-skill
- `user/skills/lazy-bug/SKILL.md` `__mark_fixed__` (Gate 1)
- `user/skills/lazy-bug-batch/SKILL.md` Step 1c.5 `__mark_fixed__` (Gate 1)

When editing this component, run `grep -r "mcp-coverage-audit.md" ~/.claude/skills/ ~/.claude/skills/_components/ --include="*.md" -l` to confirm the blast radius matches the six files above.
