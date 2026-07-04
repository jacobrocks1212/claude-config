---
kind: implementation-plan
feature_id: cross-repo-fleet-view
status: In Progress
created: 2026-07-04
complexity: medium
phases: [1, 2, 3, 4]
---

> **Plan** — single self-contained part covering all 4 phases.
> To execute: `/execute-plan docs/features/cross-repo-fleet-view/plans/all-phases-cross-repo-fleet-view-part-1.md`

# Implementation Plan — cross-repo-fleet-view (Phases 1–4)

**PHASES.md:** `docs/features/cross-repo-fleet-view/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/cross-repo-fleet-view/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest user/scripts/test_pipeline_visualizer.py -q        # per phase
# final acceptance (from user/scripts): the full LANE gate suite —
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py test_project_skills.py -q
python3 test_toolify_miner.py && python3 lazy-state.py --test && python3 bug-state.py --test
python3 lazy_coord.py --test && python3 lazy_parity_audit.py --repo-root <root>
python3 lint-skills.py --skills-dir <root>/user/skills --repos-dir <root>/repos
```

## Key design contract (read before WU-1.1)

- **Pure read.** The fleet layer NEVER calls `lazy_core.read_run_marker` (delete-on-read),
  NEVER calls `claude_state_dir(create=True)`, NEVER flips `set_active_repo_root`, adds ZERO
  POST routes. Marker paths are composed raw: `<state_base>/<lazy_core.repo_key(root)>/
  lazy-run-marker.json` (flat when `LAZY_STATE_DIR` governs).
- **Shallow rows.** Fleet rows read `queue.json` (both pipelines), the raw marker, and
  halt-sentinel *presence* only. Zero state-script subprocesses on the fleet poll (pinned by a
  monkeypatched `probe._run_state_script` counter).
- **Single-repo mode byte-identical.** `make_server(repo_root=...)` with `fleet=False` builds
  today's handler; the pre-existing suite (86 tests) runs green with zero fixture edits.
- **Badges (D3):** `idle` / `run-active` (<2h) / `run-silent` (2h–24h) / `stale-marker` (≥24h,
  `_MARKER_STALE_SECONDS`-aligned). Age always carried.

---

## Phase 1 — Discovery + shallow probe library

- [x] WU-1.1 — Tests first: `TestFleetDiscovery` (registry glob, pins, excludes, marker-union,
  realpath dedup), `TestFleetMarkerRawRead` (raw read; ≥24h marker survives; corrupt marker
  survives), `TestFleetMarkerView` (badge grading, injected now), `TestFleetRow` (depths,
  halts, lazy_queue_doc, error row), `TestFleetSlugs` (collision fallback). Run → fail
  (module absent).
- [x] WU-1.2 — Implement `pipeline_visualizer/fleet.py`: `discover_repos`, `marker_path`,
  `read_marker_raw`, `marker_view`, `marker_fresh_present`, `slugify`/`assign_slugs`,
  `_queue_summary`, `fleet_row`. Re-run → green.
- [x] WU-1.3 — Full `test_pipeline_visualizer.py` green (existing 86 + new). Commit Phase 1.

## Phase 2 — `--fleet` serving mode

- [x] WU-2.1 — Tests first: `TestFleetServer` (`/api/fleet` shape; drill-in state == single-repo
  state modulo `server_time`; POST 404s; fleet reorder idle-OK / marker-409 byte-identical;
  unknown slug 404; zero `_run_state_script` on fleet polls; `/api/fleet` cache debounce via
  monkeypatched `server.fleet_payload`). Run → fail.
- [x] WU-2.2 — Implement: `server.py` fleet mode (fleet handler, slug map from cached payload,
  per-repo lazy `TtlCache` pairs, `_handle_queue_post` extraction with `locked` param — single-
  repo call order/behavior unchanged), `__main__.py --fleet`. Re-run → green.
- [x] WU-2.3 — Full suite green (single-repo tests untouched). Commit Phase 2.

## Phase 3 — Fleet home frontend

- [ ] WU-3.1 — Tests first: `TestFleetStaticServing` (fleet `/` serves fleet.html with table +
  triage markers; `/repo/<slug>/` serves index.html; `/repo/<slug>/static/app.js` served;
  `/repo/<slug>` 301 → trailing slash; relative-URL pin: index.html/app.js carry no absolute
  `/api/` or `/static/` references). Run → fail.
- [ ] WU-3.2 — Implement: `static/fleet.html`+`fleet.js`+`fleet.css` (table, triage strip,
  badges + age, error rows, poll > TTL); relative URLs in `index.html`/`app.js`; fleet static
  routing in `server.py`. Re-run → green.
- [ ] WU-3.3 — Full suite green. Commit Phase 3.

## Phase 4 — Aggregation hardening + docs

- [ ] WU-4.1 — Tests first: `TestFleetAggregationHardening` (12-repo fixture: wall-time bound +
  zero subprocess; error row end-to-end over HTTP; `lazy_queue_url` https/ssh/worktree/missing
  cases). Run → fail (fleet_payload sequential/url absent).
- [ ] WU-4.2 — Implement: `fleet_payload` ThreadPoolExecutor fan-out; `lazy_queue_url` plain-
  file `.git` derivation; `lazy-repos.json` schema in module docstring. Re-run → green.
- [ ] WU-4.3 — Docs: root `CLAUDE.md` pipeline_visualizer row (--fleet), `user/scripts/CLAUDE.md`
  keyed-state-dir section note (fleet raw read + lazy-repos.json). Full LANE gate suite green.
  Commit Phase 4.
