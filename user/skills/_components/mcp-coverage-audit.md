## MCP-Coverage Audit (inline, docs-only — gate for `__mark_complete__`)

**Why this component exists.** The audit walk surfaced 6 of 20 features whose `__mark_complete__` flipped SPEC to Complete despite the feature's MCP test scenarios not covering every Locked Decision in the SPEC's audit-decision matrix. Root cause: `__mark_complete__` only checks that `VALIDATED.md` + `RETRO_DONE.md` are present — `VALIDATED.md` may attest to the *original* AQ-\* assertions while new decisions added later (via research / research-followup / inline edits) never got carved into MCP scenarios. The flip happens silently and the operator only catches it during a downstream audit walk (the recurring 16-hour retroactive realignment cost the audit-walk retro identified).

This component is the gate. The `__mark_complete__` consumer runs it BEFORE the actual ROADMAP/SPEC flip. If any Locked Decision is uncovered, the consumer writes `NEEDS_INPUT.md` with one entry per uncovered decision (per Q2 of the audit-walk retro design) and refuses to mark complete this cycle. The existing decision-resume mechanism (`/lazy-batch` Step 1g, `/lazy` Step 2 needs-input handling) takes over on the next cycle.

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

2. **Enumerate the MCP scenarios that own this feature.** List `{spec_path}/mcp-tests/*.md` (the per-feature scenario symlinks `/lazy` maintains). For each, read the file content. If the directory is empty AND `{spec_path}/SKIP_MCP_TEST.md` exists, treat the skip rationale as a test-exempt grant (audit passes vacuously — the operator already decided MCP testing isn't applicable). If the directory is empty AND no `SKIP_MCP_TEST.md`, treat ALL decisions as uncovered (the audit will write `NEEDS_INPUT.md` proposing the default consolidated-scenario option per Step 4).

3. **Cross-reference each decision against the scenario content.** For each Locked Decision:
   - Grep each `mcp-tests/*.md` file for the decision's `id` (literal match, e.g. `L4`) AND for any of the `keywords` (case-insensitive substring match).
   - A decision is **covered** iff at least one scenario file contains the `id` literal OR contains at least 2 of the decision's `keywords` (the 2-keyword threshold avoids false positives from single common words).
   - A decision is **uncovered** if neither match holds in any scenario file.

4. **If any decisions are uncovered:** write `{spec_path}/NEEDS_INPUT.md` per the canonical schema in `~/.claude/skills/_components/sentinel-frontmatter.md`. Frontmatter:

   ```yaml
   ---
   kind: needs-input
   feature_id: {feature_id}
   written_by: mcp-coverage-audit
   decisions:
     - "MCP coverage for Locked Decision <id-1>: <decision title>"
     - "MCP coverage for Locked Decision <id-2>: <decision title>"
     ...
   date: <today>
   next_skill: lazy
   ---
   ```

   Body MUST follow the rich-body convention. For EACH uncovered decision, emit an H3 subsection:

   ```markdown
   ### N. MCP coverage for Locked Decision <id>: <decision title>

   **Problem:** SPEC.md `## Locked Decisions` records `<id>: <decision title>` but no `mcp-tests/*.md` scenario in this feature cites this decision (by id literal or its keywords: <kw1, kw2, kw3>). `__mark_complete__` is gated on every locked decision being represented in MCP coverage so the audit walk does not retroactively discover Complete features with un-tested decision surfaces.

   **Options:**
   - **Author consolidated scenario covering all uncovered decisions (Recommended)** — one new `mcp-tests/<feature-id>-decision-audit.md` with N steps × M assertions, each step's assertion block citing the audit decisions it validates. This is the dominant pattern the audit walk applied retroactively (10/20 features). Best when ≥ 2 decisions are uncovered.
   - **Add assertion to existing scenario** — pick one of the existing `mcp-tests/*.md` files and append a new assertion block that cites `<id>`. Best when only 1-2 decisions are uncovered and an existing scenario's setup already exercises the relevant code path.
   - **Acknowledge as test-exempt** — record a one-line reason (e.g. "documentation-only decision, no observable runtime behavior"; "MCP server has no surface for this — covered by unit tests in <path>"). Writes a per-decision exemption note into `SPEC.md`'s `## Locked Decisions` section (or a new `## MCP Coverage Exemptions` section).

   **Recommendation:** Author consolidated scenario covering all uncovered decisions — matches the retroactive-realignment pattern the audit walk validated as the cleanest fix.
   ```

   Cap to 4 decisions per `NEEDS_INPUT.md` (per `AskUserQuestion`'s 4-question limit and the schema's producer responsibilities). If more than 4 are uncovered, surface the top 4 by SPEC position (earliest in the Locked Decisions table) and append a `## Open Questions` body section listing the rest for a follow-up audit cycle. Commit:

   ```
   git add {spec_path}/NEEDS_INPUT.md
   git commit -m "{feature_id}: mcp-coverage audit surfaced N uncovered locked decision(s) for user confirmation"
   ```

   Push the work branch (`git push origin $(git rev-parse --abbrev-ref HEAD)`, 4× backoff retry on network error; work branch only, never main, never force).

5. **Return status to the consumer:**
   - `clean` — no uncovered decisions; consumer proceeds with the actual `__mark_complete__` flip.
   - `uncovered:N` — N decisions surfaced via `NEEDS_INPUT.md`; consumer MUST refuse the flip this cycle, print a one-line halt note (`🛑 mcp-coverage audit: {N} uncovered locked decision(s) — NEEDS_INPUT.md written; mark-complete deferred to next cycle.`), and return. The next state-script call surfaces `needs-input` and the existing Step 1g resolution path (in batch) or Step 2 needs-input handling (in /lazy) takes over.

### Interactive vs `--batch` / cloud behavior

The audit logic is identical in all three contexts. Only the post-write surfacing differs:

| Context | Post-write behavior |
|---------|---------------------|
| `/lazy` interactive | Wrapper prints the halt note + the file path; user inspects `NEEDS_INPUT.md` and chooses. Next `/lazy` invocation calls Step 2's `needs-input` terminal handler which surfaces the decisions; user then resolves via `## Resolution` block in `NEEDS_INPUT.md` (or by editing the appropriate `mcp-tests/*.md` and re-running). |
| `/lazy-cloud` interactive | Same as `/lazy` — docs-only check works in cloud. |
| `/lazy-batch` / `/lazy-batch-cloud` Step 1c.5 (`__mark_complete__` pseudo-skill) | Orchestrator at Step 1c.5 calls this audit before the flip; on `uncovered:N`, the orchestrator does NOT increment cycle in the "successfully marked complete" sense — it records the halt note in `cycle_log` and returns to Step 1a. The next state-script call returns `terminal_reason: needs-input`, Step 1g surfaces the decisions via `AskUserQuestion`, the apply-resolution Sonnet subagent edits `mcp-tests/*.md` (or SPEC.md for the exemption case) and removes `NEEDS_INPUT.md`, and the loop continues. |

### Coupling note

This component is consumed by `__mark_complete__` in all four /lazy-family skills:
- `user/skills/lazy/SKILL.md` Step 3 `__mark_complete__`
- `user/skills/lazy-batch/SKILL.md` Step 1c.5 `__mark_complete__` pseudo-skill
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` Step 3 `__mark_complete__`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` Step 1c.5 `__mark_complete__` pseudo-skill

When editing this component, run `grep -r "mcp-coverage-audit.md" ~/.claude/skills/ ~/.claude/skills/_components/ --include="*.md" -l` to confirm the blast radius matches the four files above.
