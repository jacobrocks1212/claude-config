# Interventions/telemetry repo-scope split-brain starves the efficacy loop — Investigation Spec

> Intervention records live in claude-config (`docs/interventions/`, 25 records), but the telemetry
> that must grade them lives in the TARGET repo's keyed state dir (AlgoBooth: 1,248 events / 32 runs).
> Every sanctioned vantage of `efficacy-eval.py` sees one side or the other, never both — so the
> now-mechanically-enforced end-of-run flush is a permanent clean no-op that still satisfies the
> `--run-end` breadcrumb gate. Zero verdicts have ever been produced; no review will ever come due.

**Status:** Fixed
**Fixed:** 2026-07-12
**Fix commit:** c0b39e35
**Priority:** P1
**Last updated:** 2026-07-11
**Related:** `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` (sibling — its fix, the
run-end breadcrumb gate, shipped 2026-07-11 in `7d49490`; this bug is why that gate verifies
INVOCATION but not COVERAGE); `docs/bugs/no-mid-run-observed-friction-harden-dispatch/` (sibling —
its fix-scope §6 requires measurable intervention records, which this split-brain makes ungradeable);
`docs/bugs/hardening-intervention-records-unmeasurable-or-missing/` (the capture-side defects on the
same records); `docs/features/efficacy-signal-integrity/` (the follow-the-fix measurement-plane
feature); `docs/interventions/intervention-efficacy-tracking.md` (the loop);
`docs/features/multi-repo-concurrent-runs/` (origin of the per-repo state-dir keying that created
the two vantages).

## Verified Symptom

The intervention-efficacy loop is structurally dead — not skipped (the sibling bug fixed skipping),
but **incapable of producing a verdict from any vantage it is invoked at**:

- **Records live in claude-config.** `/harden-harness` Step 4 captures every mechanical-fix round
  with `--record-intervention … --repo-root <claude-config-root>` (`user/skills/harden-harness/SKILL.md:319`),
  so all 25 intervention records sit in `<claude-config>/docs/interventions/` (verified on disk:
  12 `harden-2026-07-r*` + 13 feature/adhoc records).
- **The enforced flush runs from the target repo.** The end-of-run flush the breadcrumb gate now
  enforces is `python3 ~/.claude/scripts/efficacy-eval.py --repo-root .` run in the orchestrator
  session (`user/skills/lazy-batch/SKILL.md:476` and `:478`, mirrored in the coupled trio) — i.e.
  with the TARGET repo (AlgoBooth) as `--repo-root`. AlgoBooth has **no** `docs/interventions/`,
  `docs/kpi/`, or `docs/telemetry/` (verified absent) → the evaluator finds zero records, exits as
  a clean no-op — and still drops the `lazy-efficacy-flush.json` breadcrumb
  (`efficacy-eval.py:1114` → `lazy_core.drop_efficacy_breadcrumb`, `lazy_core.py:15633`; the drop
  is deliberately unconditional on non-dry-run so a clean no-op discharges the gate,
  `lazy-state.py:11905-11931`). The breadcrumb payload is `{run_started_at, ts}` only — **the gate
  verifies the trio was INVOKED, not which repo-scopes it covered.**
- **Evaluating from claude-config cannot work either.** `efficacy-eval.py` binds
  `set_active_repo_root(--repo-root)` (`efficacy-eval.py:~1100`), and
  `lazy_core.read_intervention_telemetry` (`lazy_core.py:16117-16146`) merges (a) the state-dir
  ledger keyed by `repo_key(repo_root)` (`lazy_core.py:7725`) and (b) committed cloud segments under
  `<repo_root>/docs/telemetry/cloud/`. claude-config's keyed state dir
  (`~/.claude/state/853ac81ed4c78fc48ca40112a1426e224f3475bb/` — key verified by recomputing the
  SHA-1) contains only `hook-events.jsonl` + `lazy-deny-ledger.jsonl`, **no `lazy-telemetry.jsonl`**;
  its sole cloud segment is `docs/telemetry/cloud/2026-07-04T143818Z.jsonl` — **one run** (840
  events). Meanwhile **1,248 events across 32 runs** sit in the AlgoBooth-keyed dir
  (`~/.claude/state/37850b6e228d3857d45ce468af6d1d3862acb0b0/lazy-telemetry.jsonl`), invisible to
  any claude-config-rooted read.
- **Smoking gun — frozen stale baselines.** The six measurable `event:gate-refusal` records
  (r14, r15, r16, r18, r20, r21) all carry the identical frozen baseline `runs: 1 / events: 15 /
  value: 15.0` with `window_start_run == window_end_run == last_run_id == '2026-07-04T14:38:18Z'` —
  the fingerprint of that single stale cloud run (capture ran with `--repo-root <claude-config>`
  and saw nothing else). With `review_after_runs: 20` and a post-window that accrues only NEW
  `run_id`s visible from the claude-config vantage — where workstation runs never land (they append
  to the AlgoBooth-keyed ledger) — **no review will EVER come due**.
- **Consequence (verified):** zero `## Review <date>` sections across all 25 records (grep: only
  the boilerplate "Reviews are appended below" line), zero canary closes or trips, 19 canary blocks
  all `status: open`. The loop's whole output surface is empty after 22 hardening rounds.

## Root Cause

**Classification: `missing-contract` (repo-scope split-brain).** The intervention-efficacy design
bound its two data planes to different repo scopes and never declared which scope an evaluation
covers: records follow the FIX (claude-config, where harness changes ship), telemetry follows the
RUN (the target repo's keyed state dir, per the multi-repo-concurrent-runs isolation). Every
`efficacy-eval.py --repo-root <X>` invocation intersects the two planes at a single `X`, and no `X`
contains both. The sibling fix (`7d49490`) mechanically guarantees the flush *fires*, which makes
the gap strictly worse-hidden: the gate is discharged by a structurally-empty no-op, run after run.

## Fix Scope (Concluded)

Give the trio invocation an explicit **telemetry-scope contract** so records and the telemetry that
grades them meet in one evaluation:

1. **Flush covers the interventions-bearing repo.** The end-of-run flush (coupled-trio §1c.6)
   additionally runs the trio against claude-config (the repo where intervention records live) —
   not only `--repo-root .` in the target repo. The claude-config-rooted evaluation must see the
   originating runs' telemetry (point 2).
2. **`read_intervention_telemetry` merges originating target-repo ledgers.** The run marker already
   carries the target `repo_root` (`write_run_marker`, `lazy_core.py:10498`), and `repo_key` is
   deterministic — so the evaluator can resolve and merge the keyed ledgers of the repos whose runs
   the post-ship window spans (at minimum: the current run's target repo; design fork D1 covers the
   general set). The existing dedup key `(run_id, ts, event, item_id)` already makes the merge safe.
3. **Tighten the breadcrumb to record coverage.** `drop_efficacy_breadcrumb` records which
   repo-scopes (repo keys / roots) the flush actually evaluated; the `--run-end` gate refuses when
   the interventions-bearing scope was not covered (mirroring how the sibling gate refuses on a
   missing breadcrumb). Fail-open posture preserved everywhere else.
4. **Backfill/re-baseline the poisoned records.** The six `runs:1/events:15` gate-refusal records
   (r14-r16, r18, r20-r21) get their baselines re-frozen from the real merged ledger (the D9
   manual-backfill path; `record_intervention` is never-clobbering by existence, so re-baselining
   is an explicit evaluator/CLI act, not a re-capture). r5/r7 are excluded — their target signals
   are vocabulary-invalid (see the sibling capture-defects bug).
5. **Coupled-trio mirroring + tests:** lazy-batch / lazy-bug-batch / lazy-batch-cloud prose updated
   to state the two-scope flush; `test_lazy_core.py` coverage for the merged read, the
   coverage-bearing breadcrumb, and the tightened gate; full gates.

## Decisions

- **D1 — Which target-repo ledgers does a claude-config-rooted evaluation merge?** Recommended:
  the ledgers of every repo named by a live-or-recent run marker plus any repo roots recorded in
  the records' post-window provenance; simplest sound v1 is "the current run's target repo + all
  committed cloud segments". If implementation shows record-side provenance is needed (a record
  must know which repos' runs count toward ITS window), surface that schema addition as a
  NEEDS_INPUT rather than baking it.
- **D2 — Where the second flush runs from:** the orchestrator session already owns the run-end
  commit sequence in the target repo; the claude-config-scoped flush is an additional invocation
  with `--repo-root <claude-config>` (path resolvable from the skill's own config table), keeping
  doc-write/commit ownership unchanged. The alternative — teaching a single invocation to walk both
  scopes internally — is acceptable if the merge (fix §2) makes the second invocation redundant;
  either way the breadcrumb must attest coverage of the interventions-bearing scope.
- **D3 — Re-baseline provenance honesty:** re-frozen baselines carry an explicit provenance note
  (backfilled-from-merged-ledger, date) — a re-baseline is visible debt-repayment, never silently
  equal to the original capture (the `backfilled-unverified` receipt precedent).
