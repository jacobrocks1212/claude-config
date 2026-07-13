---
kind: implementation-plan
feature_id: cycle-prompt-environment-dialect
status: In-progress
created: 2026-07-12
complexity: mechanical
phases: [2, 3]
---

> **Plan** — single self-contained part covering the SKILLS-lane slice of Phases 2 and 3
> (template-side deliverables only). Phase 1 and Phase 4, and Phase 3's cross-repo row, are
> OUT OF SCOPE for this plan (STATE-lane / cross-repo ownership — see `PHASES.md`
> Implementation Notes for the exact wanted diffs).
> To execute: worked inline by the SKILLS-lane agent (this session).

# Implementation Plan — cycle-prompt-environment-dialect (Phases 2–3, SKILLS-lane slice)

**PHASES.md:** `docs/features/cycle-prompt-environment-dialect/PHASES.md` (4 phases; this plan
covers the template-side halves of 2 and 3)
**SPEC.md:** `docs/features/cycle-prompt-environment-dialect/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** Worked inline with `Read`/`Edit` (no `Agent` delegation) — a
> single-file component edit, not a TDD-shaped code change. The "test" here is the existing
> `test_lazy_core.py::test_emit_cycle_prompt_*` suite run read-only against the edited real
> template, plus the standing skill gates.

**Gate suite (run after the edit):**
```bash
python user/scripts/generate-coupled-skills.py --check --repo-root .
python user/scripts/lazy_parity_audit.py --repo-root .
python user/scripts/project-skills.py
python user/scripts/lint-skills.py --check-projected --check-capabilities
python -m pytest user/scripts/test_lazy_core.py -k emit_cycle_prompt -q
```

## Key design contract (read before WU-1)

- **File ownership boundary:** this plan touches EXACTLY ONE file —
  `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`. It does NOT touch
  `user/scripts/lazy_core.py` (the emitter's selection-loop wiring for the new `hosts=`
  attribute is STATE-lane work, recorded as a wanted diff in `PHASES.md` Phase 2 and this
  session's final report — not applied here).
- **Grammar-additive, not grammar-breaking:** the new `hosts=windows` attribute on
  `env-dialect-windows` parses today via the EXISTING generic `key=value` capture in
  `_parse_section_attrs` (no crash, no change needed to make it parse) — it is simply not yet
  READ by the selection loop. This plan's v1 behavior is therefore: the Windows section is
  selected whenever its `pipelines`/`modes`/`skills` match, on every host, same as any
  pre-existing section — a strict superset of the target (host-filtered) behavior, never a
  narrower one, so shipping the template half first is safe.
- **Byte budget is a hand-check, not a new test:** Phase 2's D4 unit test lives in
  `test_lazy_core.py` (STATE lane). This plan verifies the budget by running the same
  `_parse_cycle_template` extraction logic as a one-off script against the real file
  (see WU-2 below) rather than adding a test to a file outside this lane's ownership.
- **Zero new tokens:** both new sections use only already-bound tokens (`{cwd}`,
  `{pipeline_phrase}`, `{spec_path}`) — no `_PROMPT_RESIDUE_RE` risk, confirmed by grep.

---

## Phase 2 (template-side slice) — `hosts=` grammar doc + dialect sections

- [x] WU-2.1 — Author `<!-- @section env-dialect-core pipelines=feature,bug
  modes=workstation,cloud skills=all -->` in `cycle-base-prompt.md`, inserted after the cloud
  `task` section and before `d7` (environment context belongs early, before policy sections).
  Content: stdin-pipe cross-process rule, `--marker-status --repo-root {cwd}` probe mandate
  (bug pipeline: `bug-state.py`), `phases-slice.py {spec_path} [--phase <id>]` PHASES-read
  mandate. Measured 1,110 bytes.
- [x] WU-2.2 — Author `<!-- @section env-dialect-windows pipelines=feature,bug
  modes=workstation skills=all hosts=windows -->` immediately after WU-2.1's section.
  Content: no-trailing-backslash-before-closing-quote rule (Git-Bash EOF failure mode),
  no `/mnt/c` (WSL dialect on a non-WSL shell), `$HOME`-anchored `sys.path` for
  `lazy_core`/state-script imports. Measured 820 bytes.
- [x] WU-2.3 — Extend the template header's **SECTION MARKER GRAMMAR** doc comment with a
  `hosts=` paragraph: documents the attribute, its `windows` value, that it parses today via
  the existing generic capture, and explicitly names the STATE-lane wiring still owed
  (mirrors the `park=` filter shape, both selection loops).
- [x] WU-2.4 — Update the **RULE INVENTORY** (each rule survives exactly once): add R18
  (environment dialect, host-conditional) and R19 (PHASES-read mandate — stated once in
  `env-dialect-core`, referenced not restated by the RECONCILE step).
- [x] WU-2.5 — Byte-budget verification: one-off Python script parsing the real file through
  the same marker-split logic as `_parse_cycle_template`, printing each `env-dialect-*`
  section's UTF-8 byte length. Both < 2,048 (D4 budget held).
- [x] WU-2.6 — Gate suite: `generate-coupled-skills.py --check` (exit 0, unchanged — this
  component is pointer-referenced only, never inlined into a coupled derived file),
  `lazy_parity_audit.py --repo-root .` (exit 0), `project-skills.py` (clean, 88 skills / 97
  components across all 3 discovered repos), `lint-skills.py --check-projected
  --check-capabilities` (exit 0), `pytest test_lazy_core.py -k emit_cycle_prompt` (28/28
  pass, read-only regression check against the edited real template).

## Phase 3 (template-side slice) — PHASES-read mandate sweep

- [x] WU-3.1 — Audit `cycle-base-prompt.md` for remaining direct-PHASES-walk instructions
  (grep for `PHASES.md`). Found exactly one: the RECONCILE PHASES step inside
  `skill-mcp-test-common` — "walk {spec_path}'s PHASES.md and, for EVERY unchecked Runtime
  Verification row...".
- [x] WU-3.2 — Edit that line to route through the WU-2.1 mandate instead of restating it:
  "read {spec_path}'s PHASES.md via the env-dialect-core mandate above (`phases-slice.py
  {spec_path} --phase <id>`, never a whole-file Read) and, for EVERY unchecked Runtime
  Verification row, ...". Confirmed no other whole-file PHASES walk remains (the mcp-test
  variant's `**MCP runtime:**` line lookup is a targeted single-line read via
  `_read_mcp_runtime_decision`, not a whole-file walk — out of scope by construction).
- [ ] WU-3.3 — AlgoBooth `MCP_USAGE_GUIDE.md` cluster-(g) one-liner — **NOT in this plan's
  scope** (file lives outside this workspace; see `PHASES.md` Phase 3 for the exact wanted
  line).

---

## Out of scope for this plan (see `PHASES.md` for exact wanted diffs)

- **Phase 1** — `lazy-state.py`/`bug-state.py` `--marker-status` subcommand (STATE lane).
- **Phase 2 remainder** — `lazy_core.emit_cycle_prompt`'s `hosts=` selection filter (both
  selection loops) + the three new `test_lazy_core.py` fixtures (STATE lane).
- **Phase 3 remainder** — the AlgoBooth `MCP_USAGE_GUIDE.md` line (cross-repo, unreachable).
- **Phase 4** — `kpi-scorecard.py` selector registration (STATE lane; read-only `--lint`
  spot-check already run clean this session).
