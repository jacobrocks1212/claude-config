# Research Summary — Efficacy Signal Integrity

Inline recon (no Gemini round — the finding set was already fully enumerated in the SPEC from
the 2026-07-11 repo-exploration session); this summary records what implementation actually
found while locking the SPEC's decisions, for the benefit of anyone reading this feature later.

## Confirmed against code

- **D1 sub-signal seam is real and two-sided.** `efficacy-eval.py::_resolve_target_signal`
  (evaluator) is a SEPARATE, standalone function from `lazy_core._intervention_signal_event`
  (capture) and `lazy_core.validate_intervention_target_signal` (capture-time vocabulary check).
  The evaluator side was extendable within this feature's file ownership (`efficacy-eval.py`);
  the capture side is NOT — `validate_intervention_target_signal` rejects any `event:` string
  whose UNSPLIT remainder is outside the closed `_INTERVENTION_EVENT_VOCABULARY`, so
  `event:gate-refusal/gate-coverage` degrades to `target_signal: undeclared` at capture time
  today. This is a real, currently-open STATE-lane gap (`lazy_core.py`), not a documentation nit
  — confirmed by writing a failing test first (see the report). Worked around for the evaluator's
  own tests via the existing `--rebaseline` re-freeze path (never a hand-rolled record).
- **The `data.gate` closed vocabulary is exactly six values**, verified by grepping every
  `append_telemetry_event("gate-refusal", data={"gate": ...})` call site in
  `lazy-state.py`/`bug-state.py`: `gate-coverage`, `unacked-hardening`,
  `efficacy-coverage-missing`, `checkpoint-auth`, `apply-pseudo`, `verify-ledger`. No other event
  type currently attaches a `data.gate`-shaped signature field, confirming the SPEC's v1 scope
  ("gate-refusal only").
- **`canary-trip-precision`'s selector was already implemented** (harness-change-canary-rollback
  Phase 4, now Complete) — the SPEC's own KPI Declaration correctly lists it as an EXISTING row
  this feature serves, not a new one to build.
- **The scorecard staleness was as described**: `docs/kpi/SCORECARD.md`'s last commit predated
  the registry's own last update at spec-authoring time; by this session the registry had grown a
  further row (`skill-config-broken-reference-reads`, landed by a concurrent lane) not yet
  reflected in the committed scorecard — independent confirmation of the freshness gap D4
  describes.

## Decisions locked

- **D1, D3 (`mechanical-internal (proposed)`):** auto-accepted per SPEC recommendation — no
  operator fork; implemented as specified (sub-signal resolver + D6 disjointness in
  `efficacy-eval.py`; `vantage` field + `WRONG-VANTAGE` status in `kpi-scorecard.py`).
- **D2, D4 (`product-behavior`):** adopted per the overnight park-provisional protocol; recorded
  in `NEEDS_INPUT_PROVISIONAL.md` for ratify-or-redirect. D2 fully implemented (in-lane). D4's
  code side is ready; the orchestrator-prose wiring is a SKILLS-lane cross-lane seam (reported,
  not implemented — see the completion report).

## Cross-lane findings (reported, not implemented here)

1. **`lazy_core.validate_intervention_target_signal` / `_intervention_signal_event`** do not
   parse `event:<type>/<signature>`. Closing this seam would let a sub-signal `target_signal`
   survive capture (SPEC-block or `--record-intervention` CLI) without the `--rebaseline`
   workaround this feature's own tests use.
2. **`user/skills/lazy-batch/SKILL.md` (+ `lazy-batch-cloud`) §1c.6** — the scorecard regen
   should additionally fire on the claude-config commit path (D4's chosen option), not only when
   `docs/kpi/registry.json` exists in the repo the run happens in.

Both are named precisely (function/file) in the completion report for the owning lane.
