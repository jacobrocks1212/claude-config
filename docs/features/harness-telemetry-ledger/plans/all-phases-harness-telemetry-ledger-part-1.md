---
kind: implementation-plan
feature_id: harness-telemetry-ledger
status: Complete
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4]
---

> **Plan** — single self-contained part covering all 4 phases.
> To execute: worked inline in this lane (spec-implementation batch).

# Implementation Plan — harness-telemetry-ledger (Phases 1–4)

**PHASES.md:** `docs/features/harness-telemetry-ledger/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/harness-telemetry-ledger/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <worktree-root>/user/skills --repos-dir <worktree-root>/repos
```

## Key design contract (read before WU-1.1)

- **One writer, two callers.** `append_telemetry_event` lives in `lazy_core`; the state scripts
  only call it. The exit-3 refusal emissions live INSIDE the shared refusal helpers.
- **Non-destructive gating.** The emitter reads the run marker RAW (parse + 24h age check, no
  unlink, no session gating) — `read_run_marker` is destructive and must not be used here.
- **Plain append, never `_atomic_write`** for the ledger (deny-ledger precedent); `_atomic_write`
  IS used for the one-shot cloud segment (a rewrite, not an append-only file).
- **No `_diag` from the emitter** — a failed append must not perturb `diagnostics[]` on the
  `--emit-prompt` path (byte-identity even on failure).
- **Baselines**: regenerate ONLY by piping live `--test` output through
  `test_lazy_core._normalize_smoke_output`.
- **HARD:** every new no-arg `test_*` in `test_lazy_core.py` MUST be appended to a `_TESTS`
  block (the Round-24 dead-coverage trap); in-file `--test` fixtures print their own PASS lines.

---

## Phase 1 — Emitter substrate in `lazy_core`

- [x] WU-1.1 — RED: pytest cases for envelope/gating/fail-open/torn-line/unknown-v/rotation/
  non-destructive-marker/cloud-flush in `test_lazy_core.py` (+ `_TESTS` registration); run →
  fail (symbols missing).
- [x] WU-1.2 — GREEN: constants + `_telemetry_run_marker` + `append_telemetry_event` +
  `read_telemetry_events` (+provenance) + `TELEMETRY_HALT_TERMINAL_REASONS` +
  `_rotate_telemetry_segments` + `flush_cloud_telemetry_segment` in `lazy_core.py`; re-run → pass.
- [x] WU-1.3 — Full gate suite green; no existing test perturbed. Commit Phase 1.

## Phase 2 — Chokepoint wiring in both state scripts

- [x] WU-2.1 — RED: in-file `--test` fixtures in `lazy-state.py` (bracket emission incl. cloud
  flush; probe purity; containment-refusal capture; gate-refusal capture) — run → fail (no
  emission yet).
- [x] WU-2.2 — GREEN: wire emissions in `lazy-state.py` handlers + the three `lazy_core` refusal
  helpers + the `--run-end` flush; fixtures pass.
- [x] WU-2.3 — Mirror: same fixtures + wiring in `bug-state.py` (coupled-pair comments;
  `--bug-id`; no `--gate-coverage`).
- [x] WU-2.4 — Regenerate both `--test` baselines via `_normalize_smoke_output`; pytest baseline
  tests green; `lazy_parity_audit.py` exit 0. Commit Phase 2.

## Phase 3 — Trends aggregator + visualizer page

- [x] WU-3.1 — RED: `test_pipeline_visualizer.py` trends fixtures (pure aggregates vs
  hand-computed values; halt-dwell pairing; empty-ledger honesty; `/api/trends` route + cache
  debounce; CLI `run_summary` shape) — run → fail (module missing).
- [x] WU-3.2 — GREEN: `pipeline_visualizer/trends.py` (pure functions + loaders +
  `trends_payload` + `run_summary` + `main`); `/api/trends` in `server.py` (second `TtlCache`,
  module-attribute producer).
- [x] WU-3.3 — Static Trends tab: `index.html` + `app.js` + `styles.css`; existing static/API
  tests stay green. Commit Phase 3.

## Phase 4 — Consumers + residency follow-through

- [x] WU-4.1 — `/lazy-batch-retro` "Ledger deltas" step (additive; CLI shell + citations +
  honest-miss prose).
- [x] WU-4.2 — `/lazy-batch-cloud` run-end telemetry-segment commit prose + "Differences from
  /lazy-batch" table row.
- [x] WU-4.3 — Lane-local projection (`project-skills.py --output-dir /tmp/proj-…`) +
  `lint-skills.py` clean; full gate suite; `SKIP_MCP_TEST.md`; finalize statuses. Commit Phase 4.
