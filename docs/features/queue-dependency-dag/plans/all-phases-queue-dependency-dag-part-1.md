---
kind: implementation-plan
feature_id: queue-dependency-dag
status: In Progress
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4, 5]
---

> **Plan** — lane implementation plan (spec-implementation batch, 2026-07-04).
> To execute: worked inline in this lane worktree, phase by phase, TDD.
> Single self-contained part covering all 5 phases.

# Implementation Plan — queue-dependency-dag (Phases 1–5)

**PHASES.md:** `docs/features/queue-dependency-dag/PHASES.md` (5 phases)
**SPEC.md:** `docs/features/queue-dependency-dag/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_lazy_parity.py -q     (from user/scripts)
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <root>/user/skills --repos-dir <root>/repos   (after skill edits)
```
Full lane gate suite (all ten pytest files + lazy_coord + toolify) at the end.

## Key design contract (read before WU-1.1)

- **All queue writes via `lazy_core._atomic_write`; all breadcrumbs via `lazy_core._diag`.**
- **Byte-identity rail:** every new behavior is gated on the entry actually carrying `deps`
  (dep-gate: `dep_ids(entry)` non-empty; drift diag: `"deps" in entry`); probe keys follow the
  `gated_heads` present-only-when-non-empty discipline. Dep-less queues are byte-identical.
- **D3 completion oracle:** `dep_completion_status` is a pure on-disk receipt-gated read
  (feature: `Complete` + valid `COMPLETED.md`; bug: `Fixed` + valid `FIXED.md`, archive-aware).
  `Superseded` / `Won't-fix` classify `unsatisfiable-*` → the D4 fail-fast, never complete.
- **D4 split:** cycle/shape/prefix errors are LOAD-time `_die` exit 2 (`validate_queue_deps`);
  dangling/unsatisfiable deps are WALK-time canonical `BLOCKED.md`
  (`blocker_kind: unknown-dependency`) on the DEPENDENT.
- **D6:** bare same-pipeline ids only; `bug:`/`feature:` prefixes `_die` with a reserved-for-vN
  message at every id-validation chokepoint (load, sync, enqueue).
- **Coupled pair:** everything except the skip-ahead union mirrors onto `bug-state.py`;
  `--sync-deps` becomes parity-audit surface #6 (update `test_lazy_parity.py` stubs in lockstep).
- **Baselines:** regenerate ONLY by piping live `--test` output through
  `test_lazy_core._normalize_smoke_output` (never hand-edit).
- **Merge hygiene (sibling lane):** one contiguous dep-gate block per walk loop; argparse flags
  appended after the existing operator-op group; fixture ids `feat-dg-*` / `bug-dg-*`.

---

## Phase 1 — Schema + loader + graph validation

- [x] WU-1.1 — TESTS FIRST (`test_lazy_core.py`, registered in `_TESTS`): `parse_dep_block`
  importable from `lazy_core` with the exact current behavior (Form A/B, malformed-line skip);
  `dep_ids` shape cases; `detect_dep_cycle` (None on clean/dangling-edge, members on 2-cycle +
  self-loop + 3-chain); `validate_queue_deps` `_die` cases (non-list, bad id, reserved prefix,
  cycle) + clean pass returns None. Run → confirm failing for the right reason (helpers absent).
- [x] WU-1.2 — `lazy_core.py`: relocate `parse_dep_block` (+ `_DEP_ID_RE`, `_RESERVED_DEP_PREFIXES`),
  add `dep_ids` / `detect_dep_cycle` / `validate_queue_deps`. `lazy-state.py`: drop the local
  definition, re-export from `lazy_core`.
- [x] WU-1.3 — wire `validate_queue_deps` into `load_queue` (post-parse, pre-autodiscover-merge)
  and `load_bug_queue` (post-parse, pre-disk-merge).
- [x] WU-1.4 — gates: pytest green; BOTH `--test` suites green with ZERO baseline diff.

## Phase 2 — Dep-gate enforcement

- [x] WU-2.1 — TESTS FIRST: pytest for `dep_completion_status` (feature complete/incomplete/
  superseded/missing + spec_dir hint; bug open/archived/wont-fix/missing) and
  `format_unknown_dependency_blocker` (names id, status, known ids); smoke fixtures added to BOTH
  `run_smoke_tests` (hold+advance, transitive, unlock, dangling→BLOCKED, superseded/wont-fix→
  BLOCKED, all-gated terminal, reorder-composes). Run → red.
- [x] WU-2.2 — `lazy_core.py`: `dep_completion_status`, `format_unknown_dependency_blocker`,
  `SANCTIONED_STOP_TERMINAL += queue-exhausted-dependency-gated`.
- [x] WU-2.3 — `lazy-state.py`: `_DEP_GATED` global + reset + `_state()` key + walk-loop dep-gate
  block (after budget guard, before skip-ahead; unconditional w.r.t. `--strict-research-halt`) +
  terminal (after scoped-id, before all-parked).
- [x] WU-2.4 — `bug-state.py`: mirrored global/reset/key/gate (reads `entry["queue_entry"]`;
  archive-aware pipeline="bug") + terminal (after scoped-id, before all-parked).
- [x] WU-2.5 — gates green; re-pin BOTH baselines via `_normalize_smoke_output`; verify the
  baseline diff is purely additive (pre-existing lines unchanged).

## Phase 3 — Skip-ahead integration (feature only)

- [x] WU-3.1 — TEST FIRST: smoke fixture in the `feat-sa-*` suite — candidate with queue
  `deps: [gated-head]`, SPEC `(none)`, `independent: true` → NOT dispatched; audit diag carries
  `source=queue`. Run → red.
- [x] WU-3.2 — `lazy-state.py`: union queue deps into `_sa_deps` (kind `hard`, `source: queue`;
  SPEC-parsed deps tagged `source: spec` in the audit line).
- [x] WU-3.3 — gates green; re-pin lazy-state baseline.

## Phase 4 — Feeder + drift

- [x] WU-4.1 — TESTS FIRST: pytest for `validate_dep_id_list` + `sync_deps` (first-run write,
  second-run `noop: true` + byte-identical file, missing id `_die`, missing SPEC `_die`,
  hard-filter (soft/composes excluded), empty-hard-set removes the key); smoke fixtures for
  enqueue `--deps`, drift diag (fires on mismatch / silent without the key), `--sync-deps`
  cycle-subagent subprocess refusal exit 3. Run → red.
- [x] WU-4.2 — `lazy_core.py`: `validate_dep_id_list` + `sync_deps`.
- [x] WU-4.3 — `lazy-state.py`: `--sync-deps` CLI (refuse-first) + `--deps` on `--enqueue-adhoc`
  (validated, stored, forwarded on `--type bug`); `enqueue_adhoc(deps=...)`.
- [x] WU-4.4 — `bug-state.py`: mirrored `--sync-deps` + `--deps` (`enqueue_adhoc(deps=...)`).
- [x] WU-4.5 — probe-time drift `_diag` in both walk loops (gated on `"deps" in raw_entry`;
  reuses the existing per-entry SPEC read).
- [x] WU-4.6 — skill prose: `spec-phases/SKILL.md` sync step; `_components/adhoc-enqueue.md`
  `--deps` note; lane-local projection + lint.
- [x] WU-4.7 — gates green; re-pin BOTH baselines.

## Phase 5 — Parity + docs

- [ ] WU-5.1 — TESTS FIRST: `test_lazy_parity.py` — add the fires-when-sync-deps-missing case;
  extend the existing stubs with the `--sync-deps` token (they must stay green once the audit
  gains surface #6). Run → red (audit lacks the surface).
- [ ] WU-5.2 — `lazy_parity_audit.py`: `_SYNC_DEPS_RE` + finding in `audit_state_script_parity`;
  docstring updated.
- [ ] WU-5.3 — docs: `user/scripts/CLAUDE.md` (CLI rows + deps-field contributor note), root
  `CLAUDE.md` (scripts-section note + adhoc-enqueue bullet), `docs/features/CLAUDE.md` (queue.json
  schema note), `dep-block-schema.md` ("Queue projection" paragraph) + re-projection + lint.
- [ ] WU-5.4 — FULL lane gate suite green (all pytest files, both `--test`, `lazy_coord.py --test`,
  `test_toolify_miner.py`, parity audit, lint-skills).
