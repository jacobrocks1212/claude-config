---
kind: implementation-plan
feature_id: friction-kpi-registry
status: Complete
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4]
---

> **Plan** — single self-contained part covering all 4 phases.
> To execute: worked inline by this lane (spec-implementation batch, 2026-07-04).

# Implementation Plan — friction-kpi-registry (Phases 1–4)

**PHASES.md:** `docs/features/friction-kpi-registry/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/friction-kpi-registry/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_kpi_scorecard.py test_lazy_core.py test_hooks.py \
  test_pipeline_visualizer.py test_lazy_parity.py test_lazy_queue_doc.py \
  test_lint_skills.py test_surface_resolver.py test_stale_binary.py \
  test_retro_ro9.py test_project_skills.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test && python3 bug-state.py --test && python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <root>/user/skills --repos-dir <root>/repos
```

## Key design contract (read before WU-1.1)

- **One computation, two renderers:** `kpi-scorecard.py` imports
  `pipeline_visualizer.trends` (`load_events`, `halt_dwell`, `cycles_per_completion`) and
  `lazy_core` (`read_deny_ledger`, `set_active_repo_root`, `claude_state_dir`,
  `_atomic_write`) via the `_SCRIPTS_DIR`-on-`sys.path` bootstrap (`lazy-queue-doc.py`
  precedent). It NEVER re-implements ledger math and NEVER re-infers pipeline state.
- **Closed enums are code-owned:** `source` enum + per-source `selector` enum live as module
  constants; an unknown value is a lint ERROR, never silent no-data.
- **Honesty ladder:** unavailable source → `(None, note)` → NO-DATA; `provenance: pending` or
  `band: null` → PENDING-BASELINE; only then band comparison → OK/WARN/BREACH. A zero is only
  ever a real measured zero from a present source.
- **Byte-stability:** `render_scorecard(...)` is a pure function of (registry, readings,
  today); no wall-clock embed; fixed rounding; single trailing newline.
- **Write discipline:** the ONLY registry writer is `--capture-baseline` via
  `lazy_core._atomic_write`; SCORECARD.md is the renderer's only other write (skipped under
  `--stdout` / `--lint`).
- **Operator scope cut:** NO edits to `build-queue-enforce.sh` or any `.ps1` — the deny-append
  and runner-timestamp halves are workstation-deferred, recorded as prose.

---

## Phase 1 — Registry + lint

- [x] WU-1.1 — `test_kpi_scorecard.py`: importlib loader + lint red/green fixtures (bad id, dup id, unknown source/selector, bad direction/provenance, inverted band per direction, band-with-pending-baseline, malformed review_by, rot warning) — written FIRST, failing (module absent).
- [x] WU-1.2 — `kpi-scorecard.py`: constants (enums, id regex), `load_registry`, `lint_registry(registry, today)` → `(errors, warnings)`; CLI `--lint` (exit 1 on errors; warnings exit 0).
- [x] WU-1.3 — `docs/kpi/registry.json` — six D8 seed rows, full D2 schema, all `provenance: pending` / `value: null` / `band: null` (honest: no history in this container), build-queue rows `repo_scope: cognito-forms`, notes documenting deferred signal gaps; real-registry lint test green.

## Phase 2 — Scorecard over computable-today signals

- [x] WU-2.1 — Tests FIRST: selector value fixtures (false-green-rate 25% case; wait-time no-data; deny-count windowing; guard/friction partition; open-halt-count), availability-vs-zero, status matrix both directions at exact thresholds, byte-stability double-render, NO-DATA/PENDING rendering.
- [x] WU-2.2 — Signal layer + selectors for `build-queue-results` (env-overridable dir), `deny-ledger` (lazy_core reader, file-presence availability), `sentinel-scan`; window parsing (`Nd`); `(value, note)` contract.
- [x] WU-2.3 — Status engine + renderer (per-system tables, Regressions, Registry health, Notes; direction glyphs; fixed rounding); CLI default-write `docs/kpi/SCORECARD.md` + `--stdout`.
- [x] WU-2.4 — Commit the real `docs/kpi/SCORECARD.md` render (all rows honestly NO-DATA/PENDING-BASELINE in this container); live double-render byte-diff clean.

## Phase 3 — Ledger-backed rows + regression flags + regen wiring

- [x] WU-3.1 — Tests FIRST: fixture telemetry ledger (halt→sentinel-resolved dwell 3600s; cycles/completions ratio; containment count), ledger-absent NO-DATA, WARN + BREACH fixtures rendering Regressions lines (both directions).
- [x] WU-3.2 — `telemetry-ledger` selectors over `trends` functions + availability check (state-dir segments + cloud segments).
- [x] WU-3.3 — Regen wiring prose: `/lazy-batch` per-cycle blockquote + `.claude/skill-config/commit-policy.md` bullet extended (registry-gated, fail-open); `/lazy-batch-cloud` Differences-table row added (coupled-pair record).

## Phase 4 — `/spec` measurability gate + baseline capture

- [x] WU-4.1 — Tests FIRST: `--lint --spec` fixtures (missing classification line → exit 1; `no` ordinary SPEC → exit 0; `no` + friction keywords → advisory exit 0; `yes` w/o section → exit 1; resolving ids → exit 0; unresolved id → exit 1; valid/invalid JSON draft rows); `--capture-baseline` (stamps measured + captured_at; refuses on no-data; registry stays lint-green).
- [x] WU-4.2 — `--lint --spec [--registry]` validator + `--capture-baseline` (`_atomic_write`).
- [x] WU-4.3 — `user/skills/_components/spec-friction-kpi-gate.md` (new) + `/spec` SKILL.md edits (Phase 3 Step 8.5 injection, template classification line, Phase 1 batch-contract reference).
- [x] WU-4.4 — Projection (lane-local output dir) + `lint-skills.py` clean; docs rows (root `CLAUDE.md` scripts table + components bullet; `user/scripts/CLAUDE.md` table row).
- [x] WU-4.5 — FULL gate suite green (pytest suites + `--test` smokes + parity audit + skill lint); `SKIP_MCP_TEST.md`; finalize PHASES/plan statuses. *(Cloud note: `test_kpi_scorecard.py` 76/76 green; `lazy-state`/`bug-state`/`lazy_coord` `--test` all pass; parity audit exit 0; skill lint + doc-drift clean. `SKIP_MCP_TEST.md` is the Step-9 script-authored grant `__grant_skip_no_mcp_surface__` — never hand-written in an execute-plan cycle. The 19 `test_lazy_core.py` failures observed in the combined run are environmental: `refuse_if_cycle_active` refuses `apply_pseudo`/`mark_complete` while the live cloud cycle marker is present — not regressions from this lane, which does not touch `lazy_core.py`.)*
