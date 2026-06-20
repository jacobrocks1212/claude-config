# docs/bugs/ — claude-config harness defect investigations

Investigation specs for **defects in the harness itself** (skills, scripts, hooks,
templates) discovered from real `/lazy*` runs. This is the bug-pipeline analog of
`docs/specs/` (which holds harness *feature* work).

## Naming

One directory per defect: `docs/bugs/<slug>/SPEC.md`, where `<slug>` is a short
kebab-case description of the defect (e.g. `hardening-blind-to-process-friction`).
There is no work-item tracker for the harness repo, so slugs are descriptive.

## Lifecycle

Same investigation-spec contract as `/spec-bug`:

- `**Status:** Investigating` — active investigation; root cause not yet proven.
- `**Status:** Concluded` — root cause proven, affected area + fix scope understood;
  ready for `/plan-bug` (authors `PHASES.md`) → `/fix` / `/execute-plan`.

Prior-art harness specs live under `docs/specs/` — cross-link them in `**Related:**`
(notably `turn-routing-enforcement/` for the hardening stage and `lazy-hardening/`).

## Research resume

claude-config has **no `docs/gemini-sprint/` staging structure by design** — the repo
has negligible research volume, so the full staging machinery (results/, prompts/ symlinks,
_consumed/) would be unused.

The **blessed research-resume route** for this repo is a **direct `RESEARCH.md` drop** into
the canonical feature or bug directory (e.g. `docs/features/<slug>/RESEARCH.md` or
`docs/bugs/<slug>/RESEARCH.md`). `lazy-state.py` Step 5 detects it and routes to `/spec`
Phase 3 naturally — no ingestion step needed.

Both staging consumers already degrade gracefully when the staging dir is absent:
- `/lazy*` Step 0.5: `find docs/gemini-sprint/results …` returns empty → silently skips
  to the main loop.
- `/ingest-research` (no args, missing staging dir): exits 0 with "nothing to ingest"
  — an explicit no-op, not an error.

**Escape hatch:** should a future high-research-volume self-edit workflow ever warrant the
full staging structure, see `user/skills/ingest-research/SKILL.md` line ~65 ("per-repo
adoption" note) — parameterize the staging path via `.claude/skill-config/gemini-sprint.md`.
