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
