# A SPEC's drafted `## KPI Declaration` row is never promoted into `docs/kpi/registry.json` — Investigation Spec

> Discovered during `/harden-harness` triage of a harness gap surfaced mid-execution of
> `lazy-core-package-decomposition` (Phase 6, WU-2): its SPEC's drafted KPI row
> (`lazy-core-monolith-intervention-drag`) passed the `/spec` Phase-3 Step-8.5 measurability
> gate, but `kpi-scorecard.py --capture-baseline lazy-core-monolith-intervention-drag` fails —
> the row was never written to `docs/kpi/registry.json`.

**Status:** Concluded
**Priority:** P2
**Discovered:** 2026-07-13
**Related:** `docs/features/friction-kpi-registry/` (owns `kpi-scorecard.py` + the registry);
`user/skills/_components/spec-friction-kpi-gate.md` (the Step 8.5 gate); `docs/features/anti-overfit-design-gate/`
and `docs/features/lazy-core-package-decomposition/` (both used the "full-schema drafted row"
allowance and are affected instances — see `docs/kpi/registry.json`'s `anti-overfit-gate-*` rows,
which WERE hand-appended at ship time, unlike the `lazy-core-monolith-intervention-drag` row).

## Verified Symptom

```
$ python3 user/scripts/kpi-scorecard.py --capture-baseline lazy-core-monolith-intervention-drag --repo-root .
kpi-scorecard --capture-baseline: no KPI row with id 'lazy-core-monolith-intervention-drag' in .../docs/kpi/registry.json
```

exit 1, even though `docs/features/lazy-core-package-decomposition/SPEC.md` (lines 161-182) carries
a `## KPI Declaration` section with a full-schema drafted json row for exactly that id, and that
SPEC passed `/spec`'s Step 8.5 gate (`kpi-scorecard.py --lint --spec`) at finalization.

## Root Cause

**Classification: `missing-contract`.** The two halves of the friction-KPI measurability contract
were built independently and never connected:

- `spec-friction-kpi-gate.md` (`user/skills/_components/spec-friction-kpi-gate.md:41-45`) explicitly
  sanctions a "new drafted row" — a fenced ` ```json ` block carrying the full D2 schema — as an
  alternative to citing an existing registry row id, satisfying Step 8.5 at SPEC-finalization time.
- `kpi-scorecard.py::lint_spec` (`user/scripts/kpi-scorecard.py:1362-1419`) validates that drafted
  block via `lint_row` (row-level schema/enum lint) but **only lints it — it is never written
  anywhere.** `_extract_declaration_section`/`_parse_declaration` parse the block purely in memory.
- `kpi-scorecard.py::_cmd_capture_baseline` (`user/scripts/kpi-scorecard.py:1452-1467`) looks up a
  row by id **only** in `docs/kpi/registry.json` (`next((r for r in registry.get("kpis", [])...`);
  there is no reader that ever consults a SPEC's drafted block.

So a feature whose SPEC uses the drafted-row allowance instead of citing an existing id passes
planning-time measurability but can **structurally never** succeed a later `--capture-baseline`
call — the row simply does not exist anywhere the capture command looks. The `anti-overfit-gate-*`
rows in the current registry were rescued only because an operator hand-copied the SPEC's json
block into `registry.json` at ship time (see their `notes:` fields) — an undocumented, non-scaling
manual step, not a harness contract.

## Fix Scope (Concluded)

1. **`kpi-scorecard.py --promote-drafted-rows <spec_path> [--kpi-id <id>] [--registry <path>]`** —
   a new idempotent registry-writer subcommand reusing the EXISTING parse/lint machinery
   (`_extract_declaration_section`, `_parse_declaration`, `lint_row`, `lazy_core._atomic_write`,
   the re-lint-before-write discipline `_cmd_capture_baseline` already establishes). Read-only
   against the SPEC; appends each not-yet-present drafted row to `docs/kpi/registry.json` verbatim
   (never overwrites an existing id — same-id rows are skipped, reported, exit 0).
2. **Wire it into the Step 8.5 gate's exit-0 route** (`spec-friction-kpi-gate.md` +
   `user/skills/spec/SKILL.md` Step 8.5) so a SPEC that passes the measurability gate with drafted
   rows has them promoted into the registry at the SAME moment, before the SPEC is marked Final —
   closing the gap at its natural well-defined point instead of leaving a silent manual step.
3. **Concrete instance:** promote `lazy-core-monolith-intervention-drag` from
   `docs/features/lazy-core-package-decomposition/SPEC.md` into `docs/kpi/registry.json` via the
   new subcommand (read-only against the feature's SPEC.md/PHASES.md/plans — those are owned by a
   concurrent execution session and are not touched by this fix).
