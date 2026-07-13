---
kind: implementation-plan
feature_id: bug-queue-aging-backpressure
status: In-progress
created: 2026-07-13
complexity: moderate
phases: [1, 2, 3]
---

> **Plan** — single self-contained part. Phases 1, 2, 3 worked INLINE this session (STATE-lane
> single-agent implementation batch, 2026-07-13). The feature is provisional-blocked
> (`NEEDS_INPUT_PROVISIONAL.md`, D1) and cannot complete until the operator ratifies the
> comparator-escalation-vs-quota choice.

# Implementation Plan — bug-queue-aging-backpressure (Phases 1–3, all worked)

**PHASES.md:** `docs/features/bug-queue-aging-backpressure/PHASES.md`
**SPEC.md:** `docs/features/bug-queue-aging-backpressure/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** executed INLINE with `Read`/`Edit`/`Write`/`Bash` (no `Agent` delegation).

**Gate suite (run before marking done):**
```bash
python3 -m pytest user/scripts/test_lazy_core.py user/scripts/test_kpi_scorecard.py \
    user/scripts/test_lazy_queue_doc.py -q
python3 user/scripts/lazy-state.py --test
python3 user/scripts/bug-state.py --test
python3 user/scripts/lazy_parity_audit.py --repo-root .
python3 user/scripts/kpi-scorecard.py --lint
python3 user/scripts/doc-drift-lint.py --repo-root .
python3 user/scripts/cli_surface_gen.py --repo-root . --check
```

## Work units

### WU-1 (Phase 1) — Age-escalation formula + merged-comparator wiring

- `user/scripts/lazy_core.py`: `age_escalated_rank`, `pin_is_active`, `bug_priority_marker`;
  `merged_priority` bug branch rewritten (explicit-severity aging + pin-expiry fallback);
  `merged_worklist`/`next_merged` gain an optional `today` kwarg.
- `user/scripts/bug-state.py`: `_find_open_bug_dirs` sort key mirrors the age term (optional
  `today` kwarg); `load_bug_queue` populates `discovered`/`spec_severity`/`pinned_at`/
  `pinned_until` on every returned bug item (optional `today` kwarg, threaded to
  `_find_open_bug_dirs`).
- Tests: `test_lazy_core.py` — escalation formula (quantum/floor/fail-open), merged_priority bug
  branch (explicit severity, active pin suppression, expired pin fallback, legacy null-no-pin
  unchanged), the tier-2-feature-beaten-but-not-P0 fixture.

### WU-2 (Phase 2) — Pin lifecycle + queue-doc surfacing

- `user/scripts/bug-state.py`: `pin_bug_severity` (shared with the CLI handler); `--pin`/`--until`
  argparse flags + dispatch (gated `refuse_if_cycle_active`).
- `user/scripts/pipeline_visualizer/probe.py`: bug `queue_meta` carries `pinned_at`/`pinned_until`.
- `user/scripts/lazy-queue-doc.py`: `_bug_spec_field`/`_bug_aging_cell`; bug table gains an
  "aging" column (features table unchanged).
- Tests: `test_lazy_core.py` — `pin_is_active` (active/expired-until/expired-default/never-pinned/
  malformed), `pin_bug_severity` (update/create/malformed-until/unknown-id),
  `bug_priority_marker` (pinned/escalated/none). `test_lazy_queue_doc.py` — aging column render +
  byte-stability regression.

### WU-3 (Phase 3) — KPI selectors + registry rows

- `user/scripts/kpi-scorecard.py`: `_SOURCES["sentinel-scan"]` gains the two selector names;
  `_iter_open_bug_dirs`, `_sel_oldest_open_bug_age_days`, `_sel_concluded_unfixed_count`;
  dispatcher wiring.
- `docs/kpi/registry.json`: two new rows (promoted from the SPEC's `jsonc` → `json` fences).
- `docs/kpi/SCORECARD.md`: regenerated.
- Tests: `test_kpi_scorecard.py` — both selectors (empty tree, no-Discovered exclusion,
  Fixed/Won't-fix exclusion, Concluded counting, `--lint`/`--lint --spec` still exit 0).

## Completion gate

`__mark_complete__` is REFUSED while `NEEDS_INPUT_PROVISIONAL.md` exists (D1 unratified). This
plan's work is done; the feature waits at the ratification gate, not at implementation.

## Work Units

- [x] WU-1 age_escalated_rank/pin_is_active/bug_priority_marker in lazy_core + merged_priority rewire (landed 337e41de)
- [x] WU-2 bug-state.py --pin/--until CLI + loader field population (landed 337e41de)
- [x] WU-3 kpi-scorecard sentinel-scan selectors + registry rows + scorecard regen (landed 337e41de)
- [x] WU-4 lazy-queue-doc + visualizer aging column (landed 337e41de)
- [x] WU-5 tests: 17 lazy_core + 9 kpi + 6 queue-doc (landed 337e41de)

> Retroactive checklist added 2026-07-13 (plan predates the plan-structural gate landing mid-run); states reflect actual execution.
