## Friction-KPI Measurability Gate (injected into `/spec` Phase 3 — refuse-to-finalize)

**Why this component exists.** Friction-reduction systems ship with narrative success criteria and
are never measured again — the harness certifies feature *completion* with receipts but certifies
harness *efficacy* with nothing (`friction-kpi-registry` SPEC, Executive Summary). This gate closes
that at the authoring moment: a feature whose stated purpose is reducing harness/process friction
**cannot lock its baseline without declaring how its success will be measured** — declared KPI rows
in `docs/kpi/registry.json`, referenced or drafted. An un-measurable friction claim becomes a
planning-time halt, not a retro finding — the same "gate that refuses early over a review that
catches late" posture as `phases-runtime-validation.md` (planning-time capability audit) and
`mcp-coverage-audit.md` (completion-time coverage gate). This is the third member of that family.

The gate is **docs-only** — it reads SPEC.md and shells a deterministic linter (`grep`-class, no
Tauri / no MCP / no runtime). It runs identically in cloud and workstation.

### Inputs

- `{spec_path}` — the feature directory (e.g. `docs/features/friction-kpi-registry/`).
- The in-progress `SPEC.md` content at the Phase 3 finalization checkpoint (before writing Final).

### Algorithm

1. **Classify the feature (mandatory line).** Every SPEC MUST carry, in its header block, exactly
   one classification line:

   ```
   **Friction-reduction feature:** yes|no
   ```

   Answer the question: *is reducing harness/process friction part of THIS feature's stated
   purpose?* (efficiency wins, wasted-cycle reduction, retry/toil reduction, faster halts, cheaper
   builds — anything whose Problem/Summary sells a friction reduction). This is a reviewed judgment,
   not a keyword match. Record the verdict as the line above. Under `--batch`, record it in the
   Decision-Classification Ledger so the Step 1d.5 input-audit subagent can cross-check it.

2. **Declare the KPIs (only when `yes`).** A `yes` classification REQUIRES a `## KPI Declaration`
   section in the SPEC before finalization, listing one or both of:

   - **Existing registry rows** — one per line: `- kpi: <registry-row-id>` (each must resolve to a
     row in `docs/kpi/registry.json`).
   - **New drafted rows** — a fenced ```json block per row carrying the FULL D2 schema
     (`id`/`system`/`title`/`friction`/`signal{source,selector}`/`unit`/`direction`/
     `baseline{value,captured_at,window,provenance}`/`band`/`review_by`, optional
     `repo_scope`/`notes`). A brand-new friction system drafts its rows here; a real registry row
     is then added in the feature's own implementation.

3. **Shell the deterministic backstop.** Run the validator (the prose-gate-points-at-subcommand
   promotion `mcp-coverage-audit.md` → `--gate-coverage` established):

   ```bash
   python3 ~/.claude/scripts/kpi-scorecard.py --lint --spec {spec_path}/SPEC.md \
     [--registry <path>]      # default: <repo-root>/docs/kpi/registry.json
   # exit 0 = declaration valid (or classification 'no'); exit 1 = a gap it names on stdout
   ```

   The validator enforces: missing classification line → error; `no` → clean; `no` + friction
   vocabulary → **advisory warning** (non-blocking, D6-B); `yes` without `## KPI Declaration` →
   error; every `- kpi: <id>` must resolve; every drafted json row must pass row-level lint.

4. **Route on the verdict.**
   - **exit 0** — the declaration is valid (or the feature is legitimately `no`). Proceed to
     finalize SPEC.md. If the validator printed an advisory `WARNING` (a `no` classification that
     nonetheless carries friction vocabulary), surface the contradiction — under `--batch`, add it
     to the `NEEDS_INPUT.md` round rather than silently proceeding; interactively, confirm the `no`
     with the user. It is advisory, never a hard block.
   - **exit 1** — the declaration is missing or invalid. Treat it as an **unresolved
     product-behavior decision**, exactly like the Step 8 dep-block checkpoint's fail path:
     - **Under `--batch`:** write `{spec_path}/NEEDS_INPUT.md` with a `## Decision Context` entry
       ("this feature claims friction reduction — which KPI rows measure its success?"), quoting the
       validator's named gap. Do NOT write the Final SPEC.md. The orchestrator's Step 1g
       `AskUserQuestion` flow surfaces it and resumes.
     - **Interactively:** REFUSE to finalize, naming the missing/invalid declaration; loop back to
       add the `## KPI Declaration` section (or correct the classification) before writing SPEC.md.

### Interactive vs `--batch` behavior

| Context | classification `no` | classification `yes`, valid declaration | classification `yes`, missing/invalid declaration | missing classification line |
|---------|---------------------|------------------------------------------|--------------------------------------------------|-----------------------------|
| `/spec` interactive | proceed (advisory-confirm on keyword hit) | proceed to finalize | REFUSE-to-finalize; name the gap; loop back | REFUSE; demand the line |
| `/spec --batch` | proceed (keyword hit → fold into NEEDS_INPUT round) | proceed to finalize | `NEEDS_INPUT.md` Decision Context; do not finalize | `NEEDS_INPUT.md`; do not finalize |

The gate logic is identical in both; only the halt mechanism differs (refuse-in-conversation vs
`NEEDS_INPUT.md` + Step 1g), mirroring the Phase 3 dep-block checkpoint.

### Registry residency for non-claude-config repos

The canonical registry is `docs/kpi/registry.json` in **claude-config** (D1 — every first
registrant is a claude-config-owned system). A friction-reduction feature specced in another repo
that has no local registry drafts its rows FULLY (fenced json, full schema) so the validator can
row-lint them without id resolution, and points the backstop at the claude-config registry with
`--registry <path>` when referencing existing rows. Do NOT scatter per-repo registries — the
registrants are harness-global systems.

### Coupling note

This component is injected into `user/skills/spec/SKILL.md` at the Phase 3 finalization checkpoint
(the new **Step 8.5**, beside the Step 8 dep-block checkpoint), with a Phase 1 `--batch` contract
reference for the classification line and the `**Friction-reduction feature:** {yes|no}` line added
to the Phase 3 SPEC template. The deterministic backstop is `kpi-scorecard.py --lint --spec`
(`lint_spec`). When editing this component, run
`grep -rl "spec-friction-kpi-gate.md" ~/.claude/skills/ ~/.claude/skills/_components/` and re-project
(`project-skills.py`) + `lint-skills.py` per house rule.
