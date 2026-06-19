# __mark_complete__ does not auto-strike the ROADMAP row and mis-trims `-followups` queue ids — Investigation Spec

> When a feature completes, the `__mark_complete__` pseudo-action did not strike through the corresponding ROADMAP row (the operator hand-edited ROADMAP 5× in one run) and its automatic queue-trim silently missed ids ending in `-followups` because it matched on directory basename rather than the resolved spec_dir / full queue id. **Root cause confirmed — and the fix is ALREADY ON DISK** (commit `1b81210`, `unified-pipeline-orchestrator` Phase 5 WU-3), with dedicated regression tests passing.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-19
**Fixed:** 2026-06-19
**Fix commit:** a5bdc14
**Placement:** docs/bugs/mark-complete-skips-roadmap-strike-and-followups-queue-trim
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy_core.py` (`apply_pseudo __mark_complete__`: `_strike_roadmap_row`, `_resolve_under_repo` queue trim); `user/skills/lazy-batch/SKILL.md` Step 1c.5; `docs/features/unified-pipeline-orchestrator/` Phase 5 WU-3.

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[OBSERVED in logs]** `queue_trimmed: false` recurred because the apply-pseudo trim matched dir-basename but `-followups` queue ids did not match — session `deb9f0cf` @ `2026-06-16T23:17:40Z`: "The `queue_trimmed: false` recurs (2nd time — the apply-pseudo trim matches dir-basename but `-followups` queue ids don't match; a harness gap worth hardening). Trimming the orphaned d7 entry via recovery to clear the `queue.no-completed` gate error."
2. **[OBSERVED in logs]** Operator hand-edited ROADMAP 5×; basename-vs-`-followups`-id mismatch forced 2 queue-trim recovery dispatches — session `deb9f0cf` orchestrator retro @ `2026-06-17T01:22:05Z`: "Fold ROADMAP-strike + `spec_dir`-based queue-trim into `--apply-pseudo __mark_complete__` — I hand-edited ROADMAP 5×, and the basename-vs-`-followups`-id mismatch forced 2 queue-trim recovery dispatches."

Both symptoms are corroborated by the operator's own retro and describe behavior of the **pre-WU-3** `apply_pseudo` (basename-only trim, no ROADMAP strike).

## Reproduction Steps

The two failure modes, as they existed before the fix landed:

1. Complete a feature whose queue.json entry's stored `spec_dir` is a path-form value (e.g. `docs/features/foo-followups`) that does not equal the bare dir basename, with an `id` that also differs from the `feature_id`.
2. Run `--apply-pseudo __mark_complete__`.
3. **(legacy) Observed:** the queue entry survived the trim (`queue_trimmed: false`), tripping AlgoBooth's `queue.no-completed` consistency error and forcing a separate recovery cycle to delete one JSON line; the ROADMAP row was never struck, requiring a manual edit.

**Expected:** `__mark_complete__` strikes the ROADMAP row AND trims the queue entry by resolved spec_dir, in the same deterministic write.
**Actual (current code):** matches expected — both behaviors are implemented and tested.
**Consistency:** the legacy miss was deterministic for any queue id whose `spec_dir`/`id` diverged from the completing dir basename (`-followups` was the observed instance).

## Evidence Collected

### Source Code (confirms fix present)
`user/scripts/lazy_core.py`, `apply_pseudo()` `__mark_complete__` branch:

- **Queue trim (lines ~3201-3253)** now matches by the RESOLVED spec_dir, not just basename. `_resolve_under_repo(repo_root, value)` (lines ~2274-2291) canonicalizes absolute/repo-relative/basename forms into one comparable lowercased forward-slashed real-path. The inner `_entry_matches` (lines ~3224-3231) keeps the legacy `spec_dir == basename` / `id == feature_id` keys AND adds the resolved-path comparison, so a `-followups` entry whose stored `spec_dir` is a path-form value is caught. Returns `queue_trimmed`. Malformed queue degrades to a non-fatal `warnings[]` (completion still stands).
- **ROADMAP strike (lines ~3255-3280)** is now folded INTO `apply_pseudo` (previously an orchestrator-inline step). `_strike_roadmap_row` (lines ~2299-2351) wraps the matching row(s) in `~~`-strikethrough and appends a `✅ COMPLETE` token; idempotent (a row already carrying the token is skipped). Matches by `feature_id` OR spec-dir basename as a whole word. Returns `roadmap_struck`. Only the feature (non-`is_fixed`) path strikes; bugs have no feature ROADMAP.

### Git History
Both behaviors landed in a single commit:
- `1b81210` — `feat(unified-pipeline-orchestrator): Phase 5 WU-1/2/3 — ensure-runtime + gate-coverage + mark-complete ROADMAP strike & resolved-spec_dir trim`. (`git log -S` for both `_strike_roadmap_row` and `_resolve_under_repo` returns only this commit.)

This fix predates the 2026-06-19 session-log audit that filed this stub. The audit captured friction from sessions on 2026-06-16/17, which ran the pre-WU-3 code; the fix was already merged by the time the bug doc was created.

### Test Coverage (confirms fix works)
`user/scripts/test_lazy_core.py` — dedicated regression tests, all green (583/583 pass):
- `test_apply_pseudo_mark_complete_trims_by_resolved_spec_dir_followups` (lines ~18427-18471) — the exact `-followups` class: queue entry whose stored `spec_dir` is a path-form value differing from the basename AND whose `id` differs from `feature_id`. Asserts `queue_trimmed is True`. The OLD basename-only match would have missed it.
- `test_apply_pseudo_mark_complete_strikes_roadmap_row` (lines ~18348) — asserts `roadmap_struck is True`.
- `test_apply_pseudo_mark_complete_no_roadmap_is_noop_strike` (lines ~18385) — no ROADMAP.md → `roadmap_struck False`, completion still succeeds.
- `test_apply_pseudo_mark_complete_trims_feature_queue` / `..._queue_trim_behind_receipt_noop` / `..._mark_fixed_does_not_trim_feature_queue` / `..._malformed_queue_warns_not_refuses` — surrounding queue-trim coverage.

### Related Documentation
`user/scripts/CLAUDE.md` documents the WU-3 contract under the `--apply-pseudo` CLI surface: "`__mark_complete__` (feature path) now ALSO strikes the docs/features/ROADMAP.md row (moved IN from orchestrator-inline; returns roadmap_struck) and trims docs/features/queue.json by the RESOLVED spec_dir (returns queue_trimmed — kills the -followups queue.no-completed miss class)."

## Theories

### Theory 1: basename-only queue match misses divergent spec_dir/id ids
- **Hypothesis:** the legacy trim compared the queue entry's `spec_dir`/`id` against the completing dir basename only, so any entry whose stored `spec_dir` was a path-form value (`-followups` being the observed case) was never trimmed.
- **Supporting evidence:** operator retro + session log naming the exact mismatch; the regression test reproduces it; the WU-3 fix adds a resolved-path comparison precisely for this.
- **Status:** Confirmed (and fixed).

### Theory 2: ROADMAP strike was an orchestrator-inline step, not owned by the completion
- **Hypothesis:** the ROADMAP strikethrough was a manual/orchestrator-inline step after `__mark_complete__`, so it was skipped/forgotten (hand-edited 5×).
- **Supporting evidence:** operator retro ("I hand-edited ROADMAP 5×"); WU-3 comment in source ("the ROADMAP strikethrough was previously an orchestrator-inline step ... Moving it INTO apply_pseudo makes the completion a single deterministic author").
- **Status:** Confirmed (and fixed).

## Proven Findings

1. **Both reported failure modes are real and root-caused** — basename-only queue matching (Theory 1) and an orchestrator-inline ROADMAP strike (Theory 2).
2. **Both are already fixed on disk** by commit `1b81210` (`unified-pipeline-orchestrator` Phase 5 WU-3). `apply_pseudo __mark_complete__` is now the single deterministic author of the SPEC/PHASES/queue/ROADMAP completion writes.
3. **The fix is verified** by dedicated, passing regression tests — including one that reproduces the exact `-followups` path-form-spec_dir miss.
4. **This bug doc is a duplicate of already-shipped work** — the session-log audit that filed it sampled runs that executed the pre-WU-3 code. No further code change is required; the appropriate next step is to confirm-and-archive (no PHASES needed).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| `apply_pseudo __mark_complete__` queue trim | `user/scripts/lazy_core.py` (`_resolve_under_repo`, `_entry_matches`) | FIXED — resolved-spec_dir match catches `-followups` / divergent ids |
| `apply_pseudo __mark_complete__` ROADMAP strike | `user/scripts/lazy_core.py` (`_strike_roadmap_row`) | FIXED — strike folded into the completion; idempotent |
| Regression coverage | `user/scripts/test_lazy_core.py` | Present, green (583/583) |

## Open Questions

- None blocking. The investigation confirms the fix is present, correct, and tested. The original stub's open questions are resolved:
  - *Should `__mark_complete__` own the ROADMAP-strike?* — Yes; it does (WU-3).
  - *Correct match key for the queue-trim?* — Resolved spec_dir (canonical real-path), retaining basename + id as backward-compatible keys.
  - *Other queue-id shapes beyond `-followups` where basename diverges?* — Any path-form or divergent `id`/`spec_dir`; the resolved-path match is general and covers them all.
  - *Should `queue.no-completed` distinguish orphan vs trim-key mismatch?* — Moot: the trim no longer mismatches, so no spurious orphan reaches the gate.

> **Note for /plan-bug:** No production code change is warranted — the fix shipped in `1b81210` with passing regression tests. This concludes as a confirmed-duplicate / already-fixed item. PHASES, if authored, should be a no-op verification phase that records the existing tests as the evidence and routes to archive.
