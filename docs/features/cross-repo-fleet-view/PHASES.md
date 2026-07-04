# Implementation Phases — Cross-Repo Fleet Home Page

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (a stdlib Python package
extension + static frontend assets). No Tauri app, no MCP-reachable surface; validation is
`pytest` on `test_pipeline_visualizer.py` (plus the full harness gate suite). This is the
`standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. Substantive dependencies are implemented data contracts:

- **`lazy-pipeline-visualizer` (Complete):** the shipped per-repo server this extends —
  `make_server` (closure over one `repo_root`), `/api/state` + `/api/queue` (+ guarded POST),
  `TtlCache`, `probe.probe_state`. Its Decision 8 deferred multi-repo to v2; this is that v2.
  Single-repo `--repo-root` mode must stay byte-identical (existing suite green, unmodified).
- **`harness-telemetry-ledger` (landed on this base):** `pipeline_visualizer/trends.py`, the
  `/api/trends` route (own `TtlCache`), and the Trends tab in `static/`. The fleet drill-in
  nests it as `/repo/<slug>/api/trends`; its tests must stay green.
- **`multi-repo-concurrent-runs` (Complete):** per-repo keyed state dirs
  `~/.claude/state/<repo_key>/`; `lazy_core.repo_key` is the ONE canonical derivation (Python
  owns it; the fleet layer composes the keyed marker path from it, never re-derives elsewhere).
  `read_run_marker` is DELETE-ON-READ at 24h — forbidden for the fleet read (D3); the raw-read
  precedent is `write_run_checkpoint`.
- **`mobile-queue-control` (Complete):** the repo-discovery convention D1 reuses
  (`~/source/repos/*/docs/{features,bugs}/queue.json` + `~/.claude/lazy-repos.json`
  pins/excludes — first written by THIS feature) and the `LAZY_QUEUE.md` peer channel the fleet
  page links to.

---

### Phase 1: Discovery + shallow probe library (`fleet.py`)

**Phase kind:** design

**Scope:** New stdlib-only module `user/scripts/pipeline_visualizer/fleet.py`: D1 discovery
(registry glob + `lazy-repos.json` pins/excludes + live-marker union, realpath-deduped), the raw
(never-deleting) marker read + D3 badge grading, the D5 shallow per-repo row (queue depths +
halt-sentinel presence), and D7 slug assignment. No server change yet.

**Deliverables:**
- [x] `fleet.py`: `discover_repos(repos_base=None, lazy_repos_path=None, state_base=None)` —
  union of (a) `<repos_base>/*/docs/{features,bugs}/queue.json` glob, (b) `lazy-repos.json`
  `pins`, (c) raw `repo_root` fields scanned from `<state_base>/*/lazy-run-marker.json` (keyed
  layout; a flat `lazy-run-marker.json` directly under the base is also honored for
  `LAZY_STATE_DIR`-style dirs); realpath-deduped, `excludes` applied last, sorted.
- [x] `fleet.py`: `marker_path(repo_root, state_base=None)` + `read_marker_raw(repo_root, ...)`
  — raw JSON read of the keyed marker path composed via `lazy_core.repo_key`; NEVER calls
  `read_run_marker`, never writes, never deletes, never calls `claude_state_dir(create=True)`.
  Honors `LAZY_STATE_DIR` (flat, un-keyed) when no explicit `state_base` is given.
- [x] `fleet.py`: `marker_view(raw, now)` — D3 badge grading: `idle` / `run-active` (< 2h) /
  `run-silent` (2h–24h) / `stale-marker` (≥ 24h, aligned with `_MARKER_STALE_SECONDS`);
  `age_seconds` always carried; unparseable marker/`started_at` → `stale-marker` with
  `age_seconds: null` (honest, still never deleted).
- [x] `fleet.py`: `marker_fresh_present(repo_root, ...)` — presence + age < 24h only (the fleet-
  mode substitute for `server._run_marker_present`, race-free across threads, no delete).
- [x] `fleet.py`: `fleet_row(repo_root, slug, now, state_base)` → `{slug, repo_root, name,
  marker: {present, age_seconds, badge, pipeline, work_branch}, features: {depth, halts:[{id,
  kind}]}, bugs: {…}, lazy_queue_doc, lazy_queue_url, error}`; halt detection is presence-stat
  of `NEEDS_INPUT.md`/`BLOCKED.md` in `<pipeline_dir>/<spec_dir or id>` (the `_item_dir`
  fallback shape); any internal exception degrades to an error row (`error` set), never a raise.
- [x] `fleet.py`: `slugify` + `assign_slugs(roots)` — basename slug; on collision append a short
  `repo_key` prefix (D7).
- [x] Tests (`test_pipeline_visualizer.py`, new fleet section): discovery union/dedup/excludes/
  pins (incl. an out-of-tree live-marker repo), ≥24h marker STILL ON DISK after
  `read_marker_raw` + `fleet_row` + repeated polls, badge grading at 60s/3h/25h/absent, queue
  depths equal `len(queue)`, halts listed with kinds, slug collision fallback, error-row
  degradation.

**Minimum Verifiable Behavior:** With a temp `repos_base` of two lazy-enabled repos plus one
out-of-tree repo represented only by a live keyed marker, `discover_repos` returns all three
(deduped, excludes honored); `fleet_row` over a repo carrying a 25h-old marker reports
`stale-marker` + age and the marker file still exists afterwards.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] ≥24h-old marker survives N fleet reads (file existence + mtime unchanged). *(Evidence: `test_pipeline_visualizer.py` `TestFleetMarkerRawRead`.)* <!-- verification-only -->
- [x] Discovery union matches D1 across fixture sources. *(Evidence: `TestFleetDiscovery`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/pipeline_visualizer/fleet.py` (new),
`user/scripts/test_pipeline_visualizer.py`.

**Testing Strategy:** Hermetic tmp_path fixtures: fabricated repos (queue.json + item dirs +
sentinels), a keyed `state_base` built via `lazy_core.repo_key`, injected `now` for age
grading. No `HOME` mutation; no network; no subprocess.

**Integration Notes for Next Phase:** Phase 2 consumes `fleet_payload`/`fleet_row`,
`assign_slugs`, and `marker_fresh_present`; the server never touches marker files directly.

---

### Phase 2: `--fleet` serving mode

**Phase kind:** integration

**Scope:** `make_server` gains a fleet mode (additive kwargs; single-repo path byte-identical):
`/api/fleet` behind its own `TtlCache` (~5s), slug-parameterized per-repo routes
`/repo/<slug>/api/{state,queue,trends}` + guarded `POST /repo/<slug>/api/queue`, per-repo probe
caches allocated lazily on first drill-in, raw keyed-path marker read for fleet-mode
`queue_locked`. `__main__.py` gains `--fleet`.

**Deliverables:**
- [x] `server.py`: `make_server(repo_root=None, ..., fleet=False, repos_base=None,
  lazy_repos_path=None, state_base=None)` — `fleet=False` constructs exactly today's handler
  (existing suite green, no fixture edits). Fleet handler: `GET /api/fleet` (own
  `TtlCache(FLEET_TTL_SECONDS)`, server-owned slug map refreshed with the payload);
  `GET /repo/<slug>/api/state|queue|trends` (per-repo `TtlCache` pair, lazily allocated);
  `POST /repo/<slug>/api/queue` (same permutation-validated atomic write, refusal via
  `fleet.marker_fresh_present` — raw read, no `set_active_repo_root` flip); unknown slug → 404;
  `POST` to `/api/fleet` or any other fleet path → 404.
- [x] `server.py`: `fleet_payload` referenced as a module attribute (monkeypatch pattern, like
  `probe_state`/`trends_payload`).
- [x] `__main__.py`: `--fleet` flag (fleet home at `/`); `--repo-root` mode unchanged.
- [x] Tests: `/api/fleet` JSON shape; drill-in `/repo/<slug>/api/state` payload identical to
  single-repo `/api/state` for the same root (modulo `server_time`); POST to fleet routes →
  404; fleet reorder POST works idle and 409s under a fresh keyed marker (queue bytes
  unchanged); unknown slug 404; zero `probe._run_state_script` calls on `/api/fleet` polls
  (monkeypatched counter); `/api/fleet` served through its cache (monkeypatched
  `server.fleet_payload` counter); existing single-repo suite green unmodified.

**Minimum Verifiable Behavior:** One `--fleet` server over a two-repo fixture serves
`/api/fleet` rows for both repos and `/repo/<slug>/api/state` equal to what a single-repo
server over the same root serves; POSTing to `/api/fleet` returns 404.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Zero state-script subprocesses spawned by fleet polls. *(Evidence: `TestFleetServer` monkeypatched `_run_state_script` counter.)* <!-- verification-only -->
- [x] Single-repo mode byte-identical: full pre-existing `test_pipeline_visualizer.py` suite green with zero fixture edits. *(Evidence: suite run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1.

**Files likely modified:** `user/scripts/pipeline_visualizer/server.py`,
`user/scripts/pipeline_visualizer/__main__.py`, `user/scripts/test_pipeline_visualizer.py`.

**Testing Strategy:** Ephemeral-port servers in daemon threads (existing harness pattern);
keyed `state_base` fixtures; module-attribute monkeypatch counters for cache/debounce and
zero-subprocess assertions.

**Integration Notes for Next Phase:** Phase 3's fleet page polls `GET /api/fleet` and links to
`/repo/<slug>/`; the per-repo frontend must resolve its API/assets RELATIVE so it works nested
(single-repo `/` behavior unchanged).

---

### Phase 3: Fleet home frontend

**Phase kind:** integration

**Scope:** Static fleet page (`static/fleet.html` + `fleet.js` + `fleet.css`) — compact table
(repo, D3 badge + age, feature/bug depths, halt count) + cross-repo "Needs attention" triage
strip + drill-in links + `LAZY_QUEUE.md` GitHub links (D4-B). No build step. Switch the
per-repo frontend's absolute API/asset URLs to relative so the same page serves nested under
`/repo/<slug>/`.

**Deliverables:**
- [x] `static/fleet.html` / `static/fleet.js` / `static/fleet.css`: table + triage strip +
  badges (`run-active`/`run-silent`/`stale-marker`/`idle`, age always shown) + error rows +
  refresh age indicator; polls `/api/fleet` (interval > fleet TTL); stale-marker badge names
  the age and is information-only (no delete button).
- [x] `static/index.html` + `static/app.js`: absolute `/static/...` and `/api/...` references →
  relative (`static/...`, `api/...`) so the page works at both `/` and `/repo/<slug>/`.
- [x] `server.py` fleet routing for the page: `/` → `fleet.html`; `/repo/<slug>` →
  301 `/repo/<slug>/`; `/repo/<slug>/` → per-repo `index.html`; `/repo/<slug>/static/<x>` →
  bundled asset.
- [x] Tests: fleet mode `/` serves the fleet page (contains table + triage markers);
  `/repo/<slug>/` serves the per-repo index; `/repo/<slug>/static/app.js` served; no-slash
  redirect; single-repo `/` still serves the per-repo index (existing tests).

**Minimum Verifiable Behavior:** `python -m pipeline_visualizer --fleet` renders a landing page
whose rows and triage strip reflect a multi-repo fixture, each row linking into the shipped
three-pane per-repo view.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Fleet page + nested per-repo page served with correct routing. *(Evidence: `TestFleetStaticServing`.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** visual render check of the fleet
  landing page + drill-in in a real browser against the operator's live multi-repo layout
  (`~/source/repos`) — this container has no browser and no real repo fleet; the DOM contract
  is pinned by the served-asset tests above.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 2.

**Files likely modified:** `user/scripts/pipeline_visualizer/static/fleet.html` (new),
`static/fleet.js` (new), `static/fleet.css` (new), `static/index.html`, `static/app.js`,
`user/scripts/pipeline_visualizer/server.py`, `user/scripts/test_pipeline_visualizer.py`.

**Testing Strategy:** Served-asset assertions over the fleet server (status, content-type,
load-bearing DOM markers); JS logic kept trivially data-driven (render-only over the
`/api/fleet` payload).

**Integration Notes for Next Phase:** Phase 4 hardens aggregation behind the same payload
shape — the frontend needs no change for it.

---

### Phase 4: Aggregation hardening + docs

**Phase kind:** integration

**Scope:** Parallel shallow fan-out (`concurrent.futures.ThreadPoolExecutor`), per-repo error
rows proven end-to-end, ≥10-repo wall-time bound, `LAZY_QUEUE.md` GitHub-link derivation from
plain `.git` file reads, `~/.claude/lazy-repos.json` schema documentation, CLAUDE.md rows.

**Deliverables:**
- [ ] `fleet.py`: `fleet_payload(...)` — ThreadPoolExecutor fan-out over `fleet_row`, rows
  sorted by slug; `{repos: [...], fleet_ttl_seconds, server_time}`.
- [ ] `fleet.py`: `lazy_queue_url(repo_root)` — GitHub blob URL for a committed `LAZY_QUEUE.md`
  from plain-file reads of `.git/config` (origin URL, ssh→https normalized) + `.git/HEAD`
  (branch); worktree `.git` file followed; any failure → `None`.
- [ ] `fleet.py` module docstring: the `~/.claude/lazy-repos.json` schema (first consumer):
  `{"pins": ["<abs repo path>", ...], "excludes": ["<abs repo path>", ...]}`, `~` expanded,
  realpath-matched; malformed file → ignored (fail-open discovery, never a crash).
- [ ] Tests: ≥10-repo fixture fleet poll bounded wall-time with zero `_run_state_script`
  spawns; error row rendered (not omitted) for a broken repo; `lazy_queue_url` https/ssh/
  missing-git/no-doc cases.
- [ ] Docs: root `CLAUDE.md` `pipeline_visualizer/` script-table row extended with `--fleet`;
  `user/scripts/CLAUDE.md` per-repo-keyed-state-dir section notes the fleet raw read +
  `lazy-repos.json` schema pointer.

**Minimum Verifiable Behavior:** A 12-repo fixture `/api/fleet` poll completes within the
bounded wall-time with zero state-script subprocesses; a repo whose row computation raises
renders an explicit error row.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] ≥10-repo fixture poll under the wall-time bound, zero subprocesses. *(Evidence: `TestFleetAggregationHardening`.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** shallow-poll wall time against the
  operator's REAL repo set (fleet size + real disk latency) — requires the workstation's
  `~/source/repos`; the fixture bound covers the algorithmic claim.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/scripts/pipeline_visualizer/fleet.py`,
`user/scripts/test_pipeline_visualizer.py`, `CLAUDE.md`, `user/scripts/CLAUDE.md`.

**Testing Strategy:** Wall-clock bound generous enough to be flake-free (stat-level reads are
milliseconds; bound at seconds); monkeypatched counters for the zero-subprocess invariant;
`.git` fixtures written as plain files (no git subprocess in tests either).

**Integration Notes for Next Phase:** None — final phase.
