## Completion-Integrity Gate (inline, docs-only — gate for `__mark_complete__`)

**Why this component exists.** Three real failures showed that `__mark_complete__`'s
completion was trustworthy only by *convention*, not by *construction*:

1. A feature reached `Complete` while `PHASES.md` still had unchecked deliverables (SPEC/PHASES status incoherence).
2. A feature was flipped `Complete` on an ordinary implementation commit — bypassing `/retro` + `/mcp-test` entirely — and `is_workstation_complete()` happily skipped it forever, with **no durable evidence** that it ever passed a gate.
3. After a legitimate completion, `__mark_complete__` *deleted* `VALIDATED.md` / `RETRO_DONE.md`, so a real completion and an un-gated one became indistinguishable on disk.

This gate is the structural fix. It runs INSIDE `__mark_complete__`, AFTER the
`mcp-coverage-audit` returns `clean`, and BEFORE the ROADMAP/SPEC flip. It does
two things: (a) **verifies** completion preconditions, refusing the flip if they
don't hold; and (b) **writes a durable `COMPLETED.md` receipt** that folds in the
validation evidence, so completion is provable forever after. `lazy-state.py`
Step 2 keys on that receipt — a `Complete` claim without a receipt is a
`completion-unverified` hard-halt, which is what makes failure (2) impossible to
repeat.

The gate is docs-only — it reads `SPEC.md`, `PHASES.md`, and the validation
sentinels and runs no Tauri / no MCP server / no shell beyond `git`. It runs
identically in cloud and workstation.

### Inputs

- `{spec_path}` — the feature directory.
- `{feature_id}` — the feature directory basename.
- `{cloud}` — whether this is a cloud orchestrator (`/lazy-cloud`, `/lazy-batch-cloud`). Cloud has an extra rule below.

### Algorithm (run AFTER mcp-coverage-audit returns `clean`, BEFORE the flip)

1. **Phase-coherence check.** Read `{spec_path}/PHASES.md`. Count unchecked
   deliverables (`- [ ]` lines). The flip requires ZERO unchecked deliverables,
   EXCEPT rows under a Runtime-Verification / MCP-assertion subsection (the same
   verification-only carve-out `lazy-state.py::remaining_unchecked_are_verification_only`
   applies — those are ticked at MCP-test time and may legitimately remain if
   the validation sentinel attests they ran). Also confirm the top-level
   `PHASES.md **Status:**` is not still `Draft`/`Ready` (it should be
   `In-progress` or `Complete` by now). If a non-verification deliverable is
   still `- [ ]`, the feature is NOT done → **refuse** (Step 4 below).

2. **Validation-sentinel check.** Confirm at least one of these attests the MCP
   gate was satisfied:
   - `{spec_path}/VALIDATED.md` (full pass), OR
   - `{spec_path}/SKIP_MCP_TEST.md` (justified skip), OR
   - (`{cloud}` only) `{spec_path}/DEFERRED_NON_CLOUD.md` — cloud legitimately
     defers MCP to workstation. **Workstation must NOT accept a bare deferral as
     completion** — a workstation flip requires `VALIDATED.md` or
     `SKIP_MCP_TEST.md`.

   Also confirm `{spec_path}/RETRO_DONE.md` exists (retro ran). If neither a
   validation sentinel nor RETRO_DONE.md is present → **refuse** (Step 4).

3. **All preconditions pass → write the receipt, then flip.** Write
   `{spec_path}/COMPLETED.md` (`kind: completed`, `provenance: gated`) per
   `sentinel-frontmatter.md`, FOLDING the validation evidence into it BEFORE the
   next step deletes those sentinels:
   - `completed_commit:` — fill in after the flip commit (or omit; the commit
     that writes the receipt is itself the record).
   - `validated_via:` — `mcp` if `VALIDATED.md` present, `skip-mcp-test` if only
     `SKIP_MCP_TEST.md`, `deferred-non-cloud` if cloud-deferred.
   - `mcp_pass_count` / `mcp_total_count` — copy from `MCP_TEST_RESULTS.md` /
     `VALIDATED.md` if present.
   - Body — paste the one-paragraph validation summary from `VALIDATED.md` (or
     the skip rationale, or the deferral note) so the evidence survives the
     sentinel deletion in the flip steps.

   Then perform the flip the consumer already documents: ROADMAP
   strikethrough+`COMPLETE`, set `SPEC.md **Status:** Complete` (and `PHASES.md`
   to `Complete`), delete `VALIDATED.md` / `RETRO_DONE.md` /
   `DEFERRED_NON_CLOUD.md` (their content now lives in the receipt), KEEP
   `SKIP_MCP_TEST.md` / `MCP_TEST_RESULTS.md` / `COMPLETED.md` / `plans/`,
   commit per project policy.

4. **Refuse path (any precondition in steps 1–2 fails).** Do NOT flip. Do NOT
   write `COMPLETED.md`. This means the state script emitted `__mark_complete__`
   for a feature that isn't actually finishable — a genuine inconsistency. Write
   `{spec_path}/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`,
   `next_skill: lazy`) with one decision describing the gap (e.g. "PHASES.md has
   3 unchecked implementation deliverables but Step 10 was reached" or "no
   VALIDATED.md/SKIP_MCP_TEST.md present at mark-complete"), commit it, and
   return `refused:<reason>` to the consumer. The consumer halts this cycle
   exactly as it does for the mcp-coverage-audit `uncovered:N` case; the next
   state-script call surfaces `needs-input` and the operator reconciles.

### Return status to the consumer

- `gated` — receipt written, preconditions met; consumer proceeds with the flip.
- `refused:<reason>` — `NEEDS_INPUT.md` written; consumer MUST NOT flip this
  cycle. Print a one-line halt note (`🛑 completion-integrity gate: <reason> — NEEDS_INPUT.md written; mark-complete deferred.`) and return.

### Coupling note

Consumed by `__mark_complete__` in all four /lazy-family skills, ALWAYS as the
second gate after `mcp-coverage-audit.md`:
- `user/skills/lazy/SKILL.md` Step 3 `__mark_complete__`
- `user/skills/lazy-batch/SKILL.md` Step 1c.5 `__mark_complete__`
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` Step 3 `__mark_complete__`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` Step 1c.5 `__mark_complete__`

When editing this component, run `grep -rl "completion-integrity-gate.md" ~/.claude/skills/ ~/.claude/skills/_components/ --include="*.md"` to confirm the blast radius matches the four files above.
