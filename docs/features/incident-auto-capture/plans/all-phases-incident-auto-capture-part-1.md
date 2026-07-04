---
kind: implementation-plan
feature_id: incident-auto-capture
status: Complete
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4]
---

> **Plan** — single self-contained part covering all 4 phases.
> To execute: `/execute-plan docs/features/incident-auto-capture/plans/all-phases-incident-auto-capture-part-1.md`

# Implementation Plan — incident-auto-capture (Phases 1–4)

**PHASES.md:** `docs/features/incident-auto-capture/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/incident-auto-capture/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py \
  test_project_skills.py test_incident_scan.py -q
python3 test_toolify_miner.py
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <worktree-root>
python3 lint-skills.py --skills-dir <root>/user/skills --repos-dir <root>/repos
```

## Key design contract (read before WU-1.1)

- **Fail-open is sacred.** An events-append failure may NEVER change a hook's deny/allow output,
  exit code, or `hook-error.json` behavior. Every appender call is inside the appender's own
  try/except (swallow-everything, `append_friction_ledger_entry` contract).
- **Additive-only hook edits.** New function + new call lines; existing deny JSON strings,
  breadcrumb writes, and control flow byte-unchanged. `test_hooks.py`'s existing matrices are the
  regression pin.
- **Collector is read-only.** Its ONLY mutations: (1) the `--enqueue-adhoc --type bug`
  subprocess, (2) the `INCIDENT.md` capsule via `lazy_core._atomic_write`. `--dry-run` performs
  neither. Tests hash the input trees before/after.
- **Determinism.** Cluster key = pure string composition (D4); thresholds = config constants;
  `--now` injectable; same inputs ⇒ same slugs (idempotent scans).
- **Not on the compute path.** No state script imports `incident-scan.py`; `lazy_parity_audit.py`
  must stay exit 0 (no lazy-state/bug-state edits at all in this feature).
- **HARD:** every new `test_*` in `test_hooks.py` appended to `_TESTS`; `test_lazy_core.py`
  additions appended to its `_TESTS` registry.

---

## Phase 1 — Event persistence (D2)

- [x] WU-1.1 — TEST FIRST: `test_lazy_core.py::test_append_hook_event_shape_and_fail_open`
  (registered in `_TESTS`): appends one parseable JSONL line `{ts, kind, hook, repo_root,
  signature, detail}` to `LAZY_STATE_DIR/hook-events.jsonl`; truncates detail; returns False
  (never raises) when the events path is a directory. RED → implement
  `lazy_core.append_hook_event` → GREEN.
- [x] WU-1.2 — TEST FIRST: `test_hooks.py::test_events_longbuild_deny_appends_event` +
  `test_events_longbuild_deny_byte_identical_and_fail_open_unwritable` (deny JSON byte-compared
  against the pre-edit literal; `hook-events.jsonl` created as a DIR → deny unchanged, no crash).
  RED → wire `_append_hook_event` (inline snippet) into `long-build-ownership-guard.sh` deny +
  `_breadcrumb` sites → GREEN.
- [x] WU-1.3 — TEST FIRST: `test_events_noncanonical_deny_appends_event`,
  `test_events_straybranch_deny_appends_event` (stray-branch fixture reuses the existing
  git-fixture helper). RED → wire `block-noncanonical-blocker-write.sh` +
  `block-sentinel-write-on-stray-branch.sh` deny sites → GREEN.
- [x] WU-1.4 — TEST FIRST: `test_events_containment_deny_appends_event` (recursive-Agent deny →
  `signature: recursive-agent-dispatch`) + `test_events_bqe_deny_appends_event`
  (`dotnet-build`). RED → wire `lazy-cycle-containment.sh` (per-trip signatures + `_breadcrumb`)
  and `build-queue-enforce.sh` (classified op + `_breadcrumb`) → GREEN.
- [x] WU-1.5 — TEST FIRST (landed as `test_hooks.py::test_events_guard_breadcrumb_appends_error_event` — the guard is pipe-tested there, not in test_lazy_core): 
  (drive `lazy_guard.main()` with garbage stdin under `LAZY_STATE_DIR`; breadcrumb byte-shape
  unchanged + one `kind: error` event). RED → add `lazy_core.append_hook_event(...)` call in
  `lazy_guard._write_breadcrumb` → GREEN.
- [x] WU-1.6 — Register all new tests in `_TESTS` lists; run test_hooks (self-runner AND pytest)
  + test_lazy_core + both `--test` baselines; commit Phase 1.

## Phase 2 — Collector core

- [x] WU-2.1 — TEST FIRST: `test_incident_scan.py` skeleton + fixture builders (temp repo root
  with `docs/bugs/`, temp `LAZY_STATE_DIR`, ledger/event seeders, tree-hash helper);
  `test_dry_run_empty_state_summary_line_exit_0`. RED (script absent) → `incident-scan.py`
  skeleton (config block, arg parsing, readers, empty report) → GREEN.
- [x] WU-2.2 — TEST FIRST: clustering fixtures — 3 same-signature denies in 24h → 1 above-bar
  cluster; 2 → none; friction ≥2 any-window; hook-error ≥2/7d; hook-deny ≥3/24h; acked denies
  count; `auto_readmit`/by-reference lines skipped; out-of-window entries excluded (via
  `--now`). RED → implement readers + D4 clustering + D3 bars → GREEN.
- [x] WU-2.3 — TEST FIRST: dedup fixtures — key present in an open `docs/bugs/*/INCIDENT.md` →
  deduped; key present ONLY in `_archive/` → proposed with `recurrence_of`; slug determinism
  (two runs, same slugs). RED → implement dedup scan + slug/key derivation → GREEN.
- [x] WU-2.4 — TEST FIRST: read-only hash guard — dry-run leaves state dir + `docs/bugs/`
  byte-identical. GREEN with implementation; commit Phase 2.

## Phase 3 — Enqueue integration (D7)

- [x] WU-3.1 — TEST FIRST: end-to-end — bar-clearing fixture + real enqueue subprocess →
  queue head = stub, `ADHOC_BRIEF.md` + `INCIDENT.md` present, capsule frontmatter fields
  correct, body carries verbatim excerpt lines (capped); state dir untouched (hash). RED →
  implement enqueue + capsule writer + announce/summary lines → GREEN.
- [x] WU-3.2 — TEST FIRST: idempotency — second scan over the same inputs enqueues 0 (dedup vs
  the new open key); removed-then-recurring: dir with `INCIDENT.md` still present (queue entry
  removed) → no re-enqueue. GREEN.
- [x] WU-3.3 — TEST FIRST: cap — 5 bar-clearing clusters → exactly 2 enqueued
  (highest-recurrence first), 3 reported-only; archived-recurrence stub carries
  `recurrence_of: <archived-slug>` and a non-colliding slug. GREEN; commit Phase 3.

## Phase 4 — Wiring + docs (D6-A)

- [x] WU-4.1 — `user/skills/incident-scan/SKILL.md` (thin wrapper; `--dry-run` pass-through;
  pure presentation). Verify `project-skills.py` (lane-local `--output-dir`) + `lint-skills.py`
  clean.
- [x] WU-4.2 — `/lazy-batch` §1c.6 end-of-run incident-scan paragraph (BEFORE `--run-end`;
  non-blocking) + `/lazy-batch-cloud` mirror (no divergence). `lazy_parity_audit.py` exit 0.
- [x] WU-4.3 — Doc rows: root `CLAUDE.md` Scripts table, `user/scripts/CLAUDE.md` files table,
  `user/hooks/CLAUDE.md` appender note. Manual `--dry-run` smoke on this repo.
- [x] WU-4.4 — FULL gate suite green; `SKIP_MCP_TEST.md`; finalize PHASES/plan statuses; commit
  Phase 4.
- [ ] WU-4.5 — **Deferred:** live-ledger threshold tuning + first-capture false-positive review
  (requires workstation ledger history / a real batch run — not reachable in this cloud lane;
  see PHASES Phase 4 deferred row).
