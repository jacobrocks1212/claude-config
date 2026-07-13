# `lazy-queue-doc.py` renders bogus `[unknown]`/Pending rows for stale-complete queue entries — Investigation Spec

> `python user/scripts/lazy-queue-doc.py --repo-root . --stdout` rendered three
> `[unknown](docs/features/unknown/SPEC.md) | Pending` rows and showed several genuinely-Complete
> features as `Pending`, though `docs/features/queue.json` still listed 19 entries and 5 of them
> were already Complete with a valid `COMPLETED.md` receipt. Three independent, compounding
> defects were found and fixed.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-13
**Fixed:** 2026-07-13
**Fix commit:** 30f9d5ae
**Placement:** docs/bugs/lazy-queue-doc-renders-bogus-rows-for-stale-complete-entries
**Related:** `docs/features/mobile-queue-control/` (introduced `lazy-queue-doc.py` +
`pipeline_visualizer.probe`)

---

## Verified Symptoms

1. **[VERIFIED — reproduced]** `lazy-queue-doc.py --stdout` rendered 3 `unknown`/Pending rows and
   listed `friction-kpi-registry`, `parallel-worktree-batch-execution`,
   `harness-change-canary-rollback`, `build-queue-generalization`, and
   `build-queue-eta-priority-lanes` as `Pending`/queued despite each having a `COMPLETED.md`
   receipt on disk.
2. **[VERIFIED — code-traced]** `lazy-state.py --repo-root . --feature-id
   friction-kpi-registry` (the exact subprocess `pipeline_visualizer.probe._run_state_script`
   shells) returned `terminal_reason: all-features-complete` with `feature_id: null` — the
   walk-loop's completion-claimed branch (`if completion_claimed(...): if ... or
   has_completion_receipt(...): continue`) `continue`d past the SCOPED match instead of returning
   its own identity, so under `--feature-id` scoping every OTHER entry was also skipped
   (scope-mismatch) and the walk fell through to the global exhaustion terminal with no identity
   attached. `bug-state.py` had the identical defect in its Won't-fix/Fixed+receipted branches.
3. **[VERIFIED — code-traced]** `pipeline_visualizer.probe.parse_item_state` did not backfill
   `feature_id`/`bug_id` from the queue entry's own known id when the state script's JSON lacked
   one — so ANY state-script hard failure that still printed a well-formed JSON object with no
   identity field (see finding 4) rendered as an `unknown` row downstream.
4. **[VERIFIED — reproduced]** `lazy-state.py --repo-root . --feature-id
   bug-queue-aging-backpressure` exited 2 with `{"error": "invalid YAML frontmatter: ...", "path":
   "...NEEDS_INPUT_PROVISIONAL.md"}` — that sentinel's `decisions:` list item spanned two
   physical lines and contained an un-quoted `: ` (colon-space) mid-scalar, which YAML parses as
   an attempted nested mapping key, producing a scan error at the next top-level key (`date:`).

## Root Cause

**Class: script-defect (×2) + malformed-sentinel-content (×1).**
1. `lazy-state.py`/`bug-state.py`: the completion-claimed / Won't-fix-or-Fixed+receipted branches
   lacked the same scoped-identity-preservation pattern already used by every OTHER
   "skipped-but-matched" branch (cloud/device/host/parked) in the same walk loop.
2. `pipeline_visualizer.probe`: no identity backfill from the known queue-entry id onto a
   state-script result that omitted its own `feature_id`/`bug_id`.
3. `docs/features/bug-queue-aging-backpressure/NEEDS_INPUT_PROVISIONAL.md`: invalid YAML in the
   `decisions:` frontmatter field (a content bug in one sentinel, not a script defect).

## Fix Scope

- `lazy-state.py`: new `TR_COMPLETE_SCOPED`/`STEP_COMPLETE_SCOPED` constants; the
  completion-claimed branch now returns a scoped, identity-preserving `_scoped_skip_state` when
  `scope_feature_id` matches a Superseded/Complete+receipted entry, instead of `continue`-ing.
- `bug-state.py`: coupled-pair mirror — new `TR_FIXED_SCOPED`/`STEP_FIXED_SCOPED`; the
  Won't-fix and Fixed+receipted branches return the same scoped shape on a `--bug-id` match.
- `pipeline_visualizer/curated_stage.py`: maps both new terminals to `Complete`.
- `pipeline_visualizer/probe.py`: `parse_item_state` gains an `item_id` parameter and backfills
  `feature_id` from it when the state script's own JSON omits one (defense-in-depth against ANY
  future state-script hard failure, not just this one).
- `docs/features/bug-queue-aging-backpressure/NEEDS_INPUT_PROVISIONAL.md`: quoted the `decisions:`
  list item as a single-line YAML string (content fix, not a script change).
- `docs/features/queue.json`: the 5 stale Complete+receipted entries (left behind by prior
  `operator-directed-interactive` completions that bypassed `__mark_complete__`'s queue-trim step)
  removed via the sanctioned `lazy-state.py --reorder-queue --id <id> --to remove` — never
  hand-edited.
- `LAZY_QUEUE.md` regenerated: 14 features (down from 19), every row names a real item with a
  sane curated state; zero `unknown` rows.

## Proven Findings

- `python -m pytest user/scripts/test_pipeline_visualizer.py user/scripts/test_lazy_queue_doc.py
  -q` — 180 passed, 0 failed (no regressions from the probe.py/curated_stage.py changes).
- `python user/scripts/lazy-state.py --test` / `python user/scripts/bug-state.py --test` — both
  "All smoke tests passed." (existing fixtures unaffected; the new scoped branch is additive).
- `python user/scripts/lazy-queue-doc.py --repo-root . --stdout` post-fix: 14 features, 4 bugs,
  every row resolves to a real `docs/features/<id>/SPEC.md` / `docs/bugs/<id>/SPEC.md` with the
  correct curated state (Complete / Pending / Research / Plan / Needs-input as appropriate).
