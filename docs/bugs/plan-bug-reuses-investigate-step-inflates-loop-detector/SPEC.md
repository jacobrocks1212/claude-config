# `plan-bug` reuses the `STEP_INVESTIGATE` label — spec→plan transition mis-counts as step-oscillation — Investigation Spec

> The bug pipeline dispatches `plan-bug` under the SAME `current_step` label
> (`STEP_INVESTIGATE = "Step 4: investigate bug"`) it uses for `spec-bug`. Because the HEAD-blind
> `step_repeat_count` oscillation counter is keyed on `(feature_id, current_step)` ONLY
> (sub_skill-blind), a genuine `spec-bug → plan-bug` forward routing transition looks like the
> SAME step repeating. A normal `spec-bug (investigate, conclude) → plan-bug` sequence therefore
> accumulates `step_repeat_count` toward the `>= 3` STOP-and-inspect tripwire and the
> `(sonnet, loop-resolution)` cycle-model flip, on legitimate forward progress. The feature
> pipeline does NOT have this defect — `lazy-state.py` already gives `plan-feature` a DISTINCT
> `current_step` (`"Step 6: plan feature (phases + plan)"`). This is a bug-pipeline-only
> step-label-reuse defect.

**Status:** Concluded
**Priority:** P2
**Discovered:** 2026-07-12
**Last updated:** 2026-07-12
**Related:**
- `docs/bugs/loop-detector-false-positives-probes-and-cross-run-state/` (Concluded, P2) — its
  **Residual gap A (meta-class consumption still advances the step streak)** OWNS the
  complementary fix: `input-audit` (and other meta classes) defeat the F2 consume-debounce.
  That gap is a CONTRIBUTING factor to this friction but is neither necessary nor sufficient for
  it (see Root Cause); the two fixes are orthogonal and separately owned. This spec does NOT
  re-scope residual gap A.
- `lazy_core.update_repeat_counts` step-reset paths (`user/scripts/lazy_core.py` ~5751–6125) and
  the resolution-aware reset (`14d90bd`).
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (this round is the origin of
  this spec).

## Verified Symptom

Observed live in a claude-config `/lazy-bug-batch` run (item in flight
`descoped-row-recognition-needs-canonical-marker`), reconstructed and verified against the
current source:

- `spec-bug` (SPEC → `Concluded`), its mandatory Step-1d.5 input-audit meta cycle, and the FIRST
  `plan-bug` attempt ALL carry `current_step = STEP_INVESTIGATE = "Step 4: investigate bug"`
  (`bug-state.py:1434` routes `plan-bug` under the investigate label until `PHASES.md` exists).
- `step_repeat_count` is keyed on `(feature_id, current_step)` only (sub_skill/args-blind,
  `lazy_core.py:5863-5866`) and increments by 1 on each consecutive same-step dispatch-bound
  probe where a dispatch landed between probes (`lazy_core.py:6103-6104`). `spec-bug`'s own
  genuine cycles (investigate, then conclude) plus the `plan-bug` cycle therefore accumulate into
  ONE count at the shared label.
- At `step_repeat_count >= 3` the orchestrator STOPs to inspect and flips `cycle_model` to
  `(sonnet, loop-resolution)` (lazy-bug-batch/SKILL.md Step 1a, lines ~254-257) — here on a
  LEGITIMATE first `plan-bug` dispatch, i.e. a false LOOP-DETECTED signal.
- This run self-cleared because `plan-bug` authored `PHASES.md` and the next probe advanced
  `current_step` to `"Step 7a: ..."` (step-signature change → reset). A genuinely multi-cycle
  spec, or a `plan-bug` needing one honest retry before `PHASES.md` exists, would be pushed to a
  FALSE LOOP-DETECTED halt.

## Root Cause

**Classification: `script-defect` (step-taxonomy).** `bug-state.py::compute_state` (line 1434)
dispatches `SKILL_PLAN_BUG` ("plan-bug") with `current_step=STEP_INVESTIGATE` — reusing the
`spec-bug` routing label for a genuinely DISTINCT routing node (planning: author `PHASES.md` from
the concluded investigation). Because the step-oscillation counter is sub_skill-blind by design
(to catch the d8 write-plan loop where the same step re-routes through different skills), a
distinct routing node MUST carry a distinct `current_step` or its forward transition is
indistinguishable from oscillation.

The feature pipeline demonstrates the correct contract: `lazy-state.py:3158` dispatches
`plan-feature` with `current_step="Step 6: plan feature (phases + plan)"`, distinct from the
`/spec` step — so the feature spec→plan transition visibly advances the label and never
mis-counts. The bug pipeline diverges (the fixture comment at `bug-state.py:2864` explicitly
labels it a "reused step label"). The reuse, not the input-audit's consume, is the necessary and
sufficient cause: even with residual gap A fixed (input-audit consume excluded), `spec-bug`'s
genuine real-dispatch cycles still share the label with `plan-bug`'s real-dispatch cycles and
still accumulate past the tripwire.

## Fix Scope

Give the `plan-bug` routing node its OWN `current_step`, mirroring the feature pipeline's existing
distinct plan step. No gate is weakened — the change makes the label ACCURATE:

1. `bug-state.py`: add `STEP_PLAN_BUG = "Step 5: plan bug from concluded investigation"`; use it at
   the `Concluded`-no-PHASES `plan-bug` dispatch (line 1434). `spec-bug` (line 1440) keeps
   `STEP_INVESTIGATE`. Update the `concluded-investigation-plan-bug` fixture assertion + comment.
2. `pipeline_visualizer/curated_stage.py`: map the new step to the `Plan` stage (explicit
   `_BUG_STEP_TO_STAGE` entry + a `("Step 5:", "Plan")` bug prefix rule).
3. Regenerate the byte-pinned `tests/baselines/bug-state-test-baseline.txt` (the
   `concluded-investigation-plan-bug` row) via the sanctioned `_normalize_smoke_output` path —
   this is an INTENTIONAL output change, not a laundered regression.

**Not in scope:** residual gap A (meta-class consume debounce) — owned by
`loop-detector-false-positives-probes-and-cross-run-state`. Genuine oscillation detection is
UNCHANGED: `spec-bug`-only oscillation still accumulates at `STEP_INVESTIGATE`, and `plan-bug`-only
oscillation accumulates at the new `STEP_PLAN_BUG`.

## Post-fix verification

- `spec-bug → plan-bug` transition now advances the step label → `step_repeat_count` resets to 1
  at the first `plan-bug` probe (path 1, step-signature change).
- Regression: a fixture asserting `plan-bug` routes to `STEP_PLAN_BUG` (updated
  `concluded-investigation-plan-bug`), plus the byte-pinned baseline reflecting the new label.
- Full gate suite green (`test_lazy_core.py`, `lazy-state.py --test`, `bug-state.py --test`,
  `test_hooks.py`, `lint-skills.py`, `doc-drift-lint.py`, `lazy_parity_audit.py`).
