---
kind: implementation-plan
feature_id: parallel-worktree-batch-execution
status: Complete
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4, 5, 6]
---

> **Plan** — generated inline on 2026-07-04.
> To execute: `/execute-plan docs/features/parallel-worktree-batch-execution/plans/all-phases-parallel-worktree-batch-execution-part-1.md`
> Single self-contained part covering all 6 phases.

# Implementation Plan — parallel-worktree-batch-execution (Phases 1–6)

**PHASES.md:** `docs/features/parallel-worktree-batch-execution/PHASES.md` (6 phases)
**SPEC.md:** `docs/features/parallel-worktree-batch-execution/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py \
  test_project_skills.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <root>/user/skills --repos-dir <root>/repos
```

## Key design contract (read before WU-1.1)

- **Module boundary (D10, HARD):** `lazy_coord.py` is stdlib-only and MUST NOT import
  `lazy_core`. The lanes.json ledger uses lazy_coord's own temp-file + `os.replace` atomic
  write (the `_write_leases` pattern) — a documented justified duplication of
  `lazy_core._atomic_write`. The coordinator (skill) composes the two modules.
- **Conservative sharding (D3-A):** `claim_shardable` treats a missing/falsy `dep_ready` or
  `independent` key as HELD. The booleans are computed by the coordinator from
  `lazy_core.dep_completion_status` / `parse_independent_marker` reads — lazy_coord never
  re-derives them.
- **Marker partition tripwire (D2-A):** adding `parent_run` to the `write_run_marker` literal
  makes `test_run_marker_continuity_partition_is_complete_and_disjoint` FAIL until the key is
  explicitly classified into `RUN_FRESH_FIELDS` — run the test at both points to prove the
  tripwire fired.
- **Baselines:** re-pin `lazy-state-test-baseline.txt` / `bug-state-test-baseline.txt` ONLY by
  piping live `--test` output through `_normalize_smoke_output`.
- **Defaults byte-compatible (D10):** `provision_pool`/`scrub_slot` keep existing behavior for
  positional callers; new keyword params default to the Cognito conventions
  (`p/{wi_id}-{slug}`, `origin/main`).

---

## Phase 1 — Shardability + lane ledger

- [x] WU-1.1 — Fixture `claim-shardable-conservative` (failing first: `claim_shardable` absent) →
  implement `claim_shardable(candidates, leases_path, *, now=None)`; holds named
  (`dep-unready` / `no-independent-marker` / `live-lease`); input order preserved.
- [x] WU-1.2 — Fixture `lanes-ledger-lifecycle` → implement `read_lanes` / `_write_lanes`
  (atomic, under lock) / `ledger_record_claim` / `ledger_record_merge` /
  `ledger_record_demotion` / `ledger_record_park`; sibling `queue.json` byte-unchanged.
- [x] WU-1.3 — Fixture `merge-order-deterministic` → implement `merge_order(lanes_data,
  queue_ids)` (queue order, completion-timing independent).
- [x] WU-1.4 — Fixture `budget-arithmetic` → implement `effective_lanes` +
  `lane_budget_slice` (D6 formulas; edge: remaining_parent < slice; zero lanes guard).
- [x] WU-1.5 — Gate suite green; existing 5 lazy_coord fixtures byte-identical.

## Phase 2 — Worktree lanes + `parent_run` marker

- [x] WU-2.1 — Rename `provision_pool(cognito_root→repo_root, ...)` +
  `scrub_slot(cognito_root→repo_root, ..., branch_template=, detach_target=)`; add
  `lane_branch(item_id)` / `lane_pool_dir(repo_root)`. Fixture `scrub-branch-template` on a
  real temp git repo (default → `p/...`, lane template → `lane/<id>`, detach target honored).
- [x] WU-2.2 — pytest `test_write_run_marker_parent_run_*` (failing first) → add
  `parent_run=None` param + always-minted key to `write_run_marker`; observe
  `test_run_marker_continuity_partition_is_complete_and_disjoint` FAIL (tripwire) → classify
  into `RUN_FRESH_FIELDS` → suite green. Register new tests in `_TESTS`.
- [x] WU-2.3 — `--parent-run <json>` flag + validation (`_die` exit 2 on malformed) + threading
  into both `--run-start` handlers (`lazy-state.py`, `bug-state.py` — coupled pair).
- [x] WU-2.4 — State-script fixtures `lane-parent-run-marker` (both scripts): marker carries
  `parent_run`; rogue second `--run-start` exit 3; malformed flag exit 2. Re-pin BOTH baselines
  via `_normalize_smoke_output`.
- [x] WU-2.5 — pytest `test_repo_key_lane_worktree_distinct` (main root vs sibling
  `<root>-lanes/wt-00`). Gate suite + parity audit green.

## Phase 3 — Lane execution loop support

- [x] WU-3.1 — Fixture `zombie-lane-fenced`: reclaim + re-claim; stale token heartbeat /
  verify_fencing raise FencingError; leases/lanes/queue byte-unchanged by the zombie attempt.
- [x] WU-3.2 — State-script fixture `lane-max-cycles-slice`: lane marker stores its
  `--max-cycles` slice (folded into the `lane-parent-run-marker` fixture).
- [x] WU-3.3 — State-script fixture `lane-containment-in-lane`: subagent-context
  `--apply-pseudo`/`--run-end` at a lane state dir → exit 3, zero side effects (folded into the
  `lane-parent-run-marker` fixture where practical).
- [x] WU-3.4 — Gate suite green; baselines re-pinned if fixture output changed.

## Phase 4 — Merge + demote

- [x] WU-4.1 — Fixture `queue-order-merge-determinism` (failing first: `merge_lane_branch`
  absent) → implement `merge_lane_branch(repo_root, branch, *, no_ff=True)`; two disjoint lanes
  completing out of queue order land in queue order; repeat-run identical.
- [x] WU-4.2 — Fixture `conflict-demotes-preserves-lane-branch`: manufactured conflict → abort
  (clean tree, no MERGE_HEAD), `ledger_record_demotion` writes `demoted: serial`, lane branch
  still resolvable.
- [x] WU-4.3 — Gate suite green.

## Phase 5 — Failure isolation + flush + per-lane friction

- [x] WU-5.1 — Fixture `park-isolates-siblings` → implement `flush_summary(lanes_data)`;
  parked lane + merged sibling grouped correctly; branch/worktree preserved in ledger.
- [x] WU-5.2 — Fixture `coordinator-death-recovery`: TTL reclaim scrubs slots + clears leases;
  lanes.json audit trail intact.
- [x] WU-5.3 — State-script fixture `lane-friction-no-cross-trip` (D9 obligation): two lane
  state dirs + two real git repos; sibling commits never cross-trip a lane's `--cycle-end`
  friction detector. Re-pin baseline via `_normalize_smoke_output`.
- [x] WU-5.4 — Gate suite green.

## Phase 6 — Skill + surfaces + docs

- [x] WU-6.1 — `user/skills/lazy-batch-parallel/SKILL.md` (new): frontmatter, hard constraints,
  bookends, ad-hoc enqueue injection (`adhoc-enqueue.md`), shard report, claim/provision/arm,
  lane loop, park, queue-order merge + demote, serial tail, flush report, differences table.
- [x] WU-6.2 — `/lazy-status` lane rows (ledger + per-worktree probes; absent ⇒ byte-identical).
- [x] WU-6.3 — `/lazy-batch-retro` demotion + false-`independent` audit feed.
- [x] WU-6.4 — `user/scripts/CLAUDE.md` concurrency-plane section + lazy_coord row + CLI ref;
  root `CLAUDE.md` rows.
- [x] WU-6.5 — Projection into lane-local dir + `lint-skills.py` clean; parity audit exit 0;
  FULL gate suite green; PHASES/plan checkboxes reconciled.
