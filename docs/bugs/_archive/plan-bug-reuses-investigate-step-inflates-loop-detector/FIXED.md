---
kind: fixed
feature_id: plan-bug-reuses-investigate-step-inflates-loop-detector
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: bug-state.py --test (in-file smoke harness); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

plan-bug-reuses-investigate-step-inflates-loop-detector marked Fixed on 2026-07-12 by
operator-directed interactive close-out. The code fix itself (STEP_PLAN_BUG) landed in commit
`879613d1` during the same hardening round that authored this bug's SPEC — this receipt records
the terminal state confirmed on disk during close-out (no code changed in this pass; PHASES.md was
authored retroactively since none existed).

## Symptom Reproduction (red -> green)

The `concluded-investigation-plan-bug` fixture in `bug-state.py`'s in-file `--test` harness is the
regression test: a Concluded-investigation bug with no `PHASES.md` must dispatch `plan-bug` under
a DISTINCT `current_step` (`STEP_PLAN_BUG`), not the reused `STEP_INVESTIGATE`. Per the fixture's
own comment (`bug-state.py:3905`), this was RED against the pre-fix code (which always reused
`STEP_INVESTIGATE`) and is GREEN at HEAD.

## Verification (this pass, 2026-07-12)

```
LAZY_STATE_DIR=<isolated temp dir> python user/scripts/bug-state.py --test
-> All smoke tests passed.
```

`concluded-investigation-plan-bug` and `concluded-investigation-guard-still-spec-bug` both PASS,
confirming: (1) plan-bug now routes under `STEP_PLAN_BUG`, and (2) the Concluded marker remains the
exclusive trigger (an Investigating SPEC still routes spec-bug/STEP_INVESTIGATE — no regression).

## Notes

Fully implemented in a prior session (`879613d1`, 2026-07-12): `STEP_PLAN_BUG` constant + dispatch
site in `bug-state.py`, the `curated_stage.py` stage mapping, and the regenerated
`bug-state-test-baseline.txt` row. This close-out pass authored the missing `PHASES.md`, flipped
`**Status:**` to Fixed in SPEC.md + PHASES.md, and writes this receipt.
