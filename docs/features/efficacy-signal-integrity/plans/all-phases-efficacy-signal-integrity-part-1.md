---
kind: implementation-plan
feature_id: efficacy-signal-integrity
status: Complete
created: 2026-07-12
complexity: complex
phases: [1, 2, 3]
---

> **Plan** — single self-contained part covering all 3 phases.
> To execute: worked inline by this lane (feature-implementation subagent, 2026-07-12).

# Implementation Plan — efficacy-signal-integrity (Phases 1–3)

**PHASES.md:** `docs/features/efficacy-signal-integrity/PHASES.md` (3 phases)
**SPEC.md:** `docs/features/efficacy-signal-integrity/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every new behavior — a failing test precedes its
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python -m pytest user/scripts/test_efficacy_eval.py user/scripts/test_kpi_scorecard.py -q
python user/scripts/kpi-scorecard.py --lint --repo-root .
python user/scripts/kpi-scorecard.py --repo-root . --stdout > /tmp/r1.txt
python user/scripts/kpi-scorecard.py --repo-root . --stdout > /tmp/r2.txt
diff /tmp/r1.txt /tmp/r2.txt   # byte-stable double render
```

## Key design contract (read before WU-1.1)

- **File ownership (concurrent agents active):** `docs/features/efficacy-signal-integrity/**`,
  `user/scripts/efficacy-eval.py` + `test_efficacy_eval.py`, `user/scripts/kpi-scorecard.py` +
  `test_kpi_scorecard.py`, `docs/kpi/**`, `docs/interventions/**`. NOT owned:
  `lazy_core.py`/`lazy-state.py`/`bug-state.py` (STATE lane), `user/skills/**` (SKILLS lane) —
  a needed seam there is IMPLEMENTED EVERYWHERE ELSE and reported exactly, never hand-edited.
- **Sub-signal resolver stays inside `efficacy-eval.py`.** `_resolve_target_signal` is a
  standalone function (not shared with `lazy_core._intervention_signal_event`), so the D1 seam
  is fully implementable within this feature's ownership on the EVALUATION side. The CAPTURE-side
  vocabulary check (`lazy_core.validate_intervention_target_signal`) is a separate, STATE-owned
  gate that does not yet accept the `/<signature>` suffix — tests work around it via the existing
  `--rebaseline` re-freeze path (never a hand-rolled record).
- **`_same_signal` replaces exact-string equality** in the D6 confounder cap — same event type +
  either side bare (no signature) → overlap (conservative); same type + different signatures →
  disjoint; different types → never overlap (unchanged).
- **`kpi-scorecard.py` stays a standalone pure-read renderer** — `_canary_health_summary`
  deliberately DUPLICATES the small canary-age/post-run-count helpers rather than importing
  `efficacy-eval.py` (the `lazy_coord.py`/`lazy_core.py` documented small-helper-duplication
  precedent, not a new pattern).
- **`row_status`/`render_scorecard`'s new kwargs are ALL optional** (`repo_root`, `host`,
  `canary_health`) — every existing caller (incl. `--lint`, prior tests) is byte-identical
  without them. Vantage classification only fires when the caller supplies BOTH the row's
  declared dimension AND the corresponding argument.
- **Honesty ladder is unchanged, extended:** NO-DATA → WRONG-VANTAGE (new, D3) →
  PENDING-BASELINE → OK/WARN/BREACH. A `None` value is WRONG-VANTAGE only when vantage
  genuinely mismatches; otherwise NO-DATA as before.
- **Registry rows never fabricate a baseline** — the 3 new rows ship `provenance: pending`,
  `band: null`, matching every other pending row in this registry.

---

## Phase 1 — Sub-signal seam

- [x] WU-1.1 — `test_efficacy_eval.py`: `_seed_runs` gains an optional `data` kwarg (defaults
  preserve byte-identical prior behavior); `_set_target_signal` + `_capture_subsignal` fixture
  helpers (mirror the existing `_add_canary` pattern — real record IO, one field fixture-mutated
  past the un-closed capture-side vocabulary gate); `test_sub_signal_targets_grade_disjointly` +
  `test_bare_target_still_confounds_sub_signal` — written FIRST, failing (module unmodified).
- [x] WU-1.2 — `efficacy-eval.py`: `_GATE_REFUSAL_SIGNATURES` closed set (grep-verified);
  `_target_signature`, `_event_matches_target`, `_same_signal`; `_resolve_target_signal` strips
  the `/<signature>` suffix (unchanged `(kind, event_type)` contract); `_compute_verdict`,
  `_canary_band_trip`, `_rebaseline_record` route counting through `_event_matches_target`;
  `_review_record`'s same-signal cap routes through `_same_signal`. Gate suite green (50/50 in
  `test_efficacy_eval.py`, including all pre-existing tests unchanged).

## Phase 2 — Canary health

- [x] WU-2.1 — `test_efficacy_eval.py`: `test_canary_staleness_alarm_precedes_ceiling`,
  `test_canary_staleness_notify_zero_projected_when_not_near_ceiling`,
  `test_canary_staleness_silent_when_no_open_canaries` — written FIRST, failing.
- [x] WU-2.2 — `efficacy-eval.py`: `CANARY_STALENESS_LOOKAHEAD_DAYS`, `_canary_age_days`;
  `run_canary`'s monitoring loop aggregates `staleness`/`staleness_notify`; the degraded-payload
  fallback carries honest all-zero staleness fields; the plain-text flush prints the notify line.
- [x] WU-2.3 — `test_kpi_scorecard.py`: `TestCanaryHealthSummary` (open/age/projection
  arithmetic incl. the observed-run leg via a `LAZY_STATE_DIR` telemetry fixture; render section
  populated + `(none open)` cases) — written FIRST, failing.
- [x] WU-2.4 — `kpi-scorecard.py`: `_CANARY_WINDOW_DAYS_CEILING` /
  `_CANARY_STALENESS_LOOKAHEAD_DAYS` (documented duplication), `_canary_age_days`,
  `_canary_post_run_count`, `_canary_health_summary`; `render_scorecard`'s new `## Canary health`
  section; `_cmd_render` computes + threads `canary_health`. Gate suite green.

## Phase 3 — Vantage + freshness

- [x] WU-3.1 — `test_kpi_scorecard.py`: `TestVantageLint`, `TestVantageStatus` (incl. the
  omitted-args backward-compat case) — written FIRST, failing.
- [x] WU-3.2 — `kpi-scorecard.py`: `_VANTAGE_HOSTS`, `lint_row`'s vantage validation,
  `_vantage_match`, `row_status(..., repo_root=None, host=None)`, `_STATUS_WRONG_VANTAGE`,
  `--host` CLI flag + `_resolve_host`.
- [x] WU-3.3 — `test_kpi_scorecard.py`: `TestConclusiveVerdictCount`,
  `TestConfoundedVerdictRatio`, `TestCanaryClosureLatency` (`_write_review_record`/
  `_write_canary_record` fixture helpers) — written FIRST, failing.
- [x] WU-3.4 — `kpi-scorecard.py`: `_SOURCES["intervention-records"]`,
  `_iter_review_sections`, `_sel_conclusive_verdict_count`, `_sel_confounded_verdict_ratio`,
  `_canary_closed_date`, `_sel_canary_closure_latency_p50`, `_sel_intervention_records`
  dispatcher wired into `compute_reading`.
- [x] WU-3.5 — `docs/kpi/registry.json`: three new rows (`efficacy-verdicts-produced`,
  `confounded-verdict-ratio`, `canary-closure-latency-p50`), flipped from the SPEC's fenced-json
  drafts to full lint-clean rows. `docs/kpi/SCORECARD.md` regenerated (real render over this
  repo's 28 open canaries + 11 registry rows).
- [x] WU-3.6 — `docs/interventions/CLAUDE.md`: documented the sub-signal syntax + the canary
  staleness alarm fields, so future authors find the mechanism without re-deriving it from code.

**Final gate run (this session):** `pytest user/scripts/test_efficacy_eval.py
user/scripts/test_kpi_scorecard.py -q` → 159 passed; `kpi-scorecard.py --lint --repo-root .` →
OK; double-render diff → byte-identical.
