# Implementation Phases — Lazy Pipeline Visualizer

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

<!-- Implementation of all four phases is complete (part-1 P1, part-2 P2, part-3
     P3+P4). Top-level Status is In-progress: the validation tail (repo pytest +
     lint + operator SKIP_MCP_TEST.md) and the gate-owned Complete flip + COMPLETED.md
     receipt are still pending. NEVER hand-flip this to Complete — owned by
     __mark_complete__. -->


**MCP runtime:** not-required — claude-config has no MCP server and no Tauri runtime (`.claude/skill-config/capabilities.txt` declares zero capabilities; `quality-gates.md` "MCP exemption"). Validation is the repo's own pytest + lint suite plus a documented manual browser smoke; the Step-9 MCP gate is operator-exempt via `SKIP_MCP_TEST.md`.

## Cross-feature Integration Notes

No hard deps on sibling SPECs (this repo carries no `queue.json` dependency graph; SPEC `**Depends on:** (none)`). The substantive dependencies are **implemented data contracts**, verified against source during this decomposition (anchor discipline):

- **`lazy-state.py` JSON output** (`user/scripts/lazy-state.py`) — confirmed emits `feature_id`, `feature_name`, `spec_path`, `current_step`, `sub_skill`, `terminal_reason`, `notify_message`, `diagnostics` [VERIFY: grep -n '"current_step"\|"terminal_reason"\|"diagnostics"' user/scripts/lazy-state.py]. The visualizer is a **read renderer** over this contract; it MUST NOT re-implement state inference.
- **`bug-state.py` JSON output** (`user/scripts/bug-state.py`) — the bug-track analog of the above [VERIFY: user/scripts/bug-state.py].
- **`leases.json` schema** (`user/scripts/lazy_coord.py`) — Open Question #1 RESOLVED: the SPEC-estimated field names are confirmed exact. Each lease entry is `{worker_pid: int, worktree_slot: str, term_token: int, heartbeat_timestamp: "<ISO-8601 UTC 'Z'>", ttl_seconds: int}`, keyed by `wi_id` [VERIFY: grep -n 'worker_pid\|worktree_slot\|heartbeat_timestamp\|ttl_seconds' user/scripts/lazy_coord.py]. Heartbeat freshness = `_parse_iso(heartbeat_timestamp) + ttl_seconds >= now`. The SPEC's `term_token` (not a `branch` field) is the fencing token; the `p/<id>-<slug>` branch shown on Fleet cards is derived from the leased item, not stored in `leases.json`.
- **`docs/features/queue.json` / `docs/bugs/queue.json` / `ROADMAP.md`** — read for queue ordering + badges (tier / ad-hoc / stub) [VERIFY: user/scripts/lazy-state.py queue handling].

## Where the code lives

A self-contained tool, not an edit to the state machine: backend Python package `user/scripts/pipeline_visualizer/` (stdlib only, no new deps), static frontend under `user/scripts/pipeline_visualizer/static/` (vendored Cytoscape.js + dagre UMD, no build step), tests as `user/scripts/test_pipeline_visualizer.py` (matches the repo's `test_*.py` convention). The state scripts (`lazy-state.py`, `bug-state.py`, `lazy_coord.py`) are **read-only** to this feature — the only write target is `queue.json`.

---

### Phase 1: Backend read layer + curated-stage mapping

**Scope:** A `ThreadingHTTPServer` that shells the existing state scripts across all queue items, parses their JSON, attaches a `curated_stage`, and reads `queue.json` / `leases.json` / `ROADMAP.md`. Exposes `GET /api/state` and `GET /api/queue`. Server-side read-through TTL cache (double-checked `threading.Lock`) over the probe. This phase deliberately closes the full data loop end-to-end (CLI process → JSON parse → HTTP response) so no later phase discovers the contract is wrong — the analog of the "Phase 1 crosses the boundary" rule for this process/serialization seam.

**Deliverables:**
- [x] `pipeline_visualizer/server.py` — `ThreadingHTTPServer` subclassing `SimpleHTTPRequestHandler`; explicit routing for `/api/state` and `/api/queue` (GET), all other paths deferred to `super()` for static assets.
- [x] `pipeline_visualizer/probe.py` — shells `lazy-state.py --repo-root <root> --feature-id <id>` and `bug-state.py --bug-id <id>` per queue item via `subprocess.run` (capture stdout, `json.loads`); reads `queue.json` (features + bugs), `leases.json`, `ROADMAP.md`. Returns a single aggregate state dict.
- [x] `pipeline_visualizer/cache.py` — read-through TTL cache (TTL 2.0s) with double-checked `threading.Lock`; one heavy probe runs at most once / 2.0s regardless of concurrent requests.
- [x] `pipeline_visualizer/curated_stage.py` — the static rollup table from SPEC "Curated-node rollup": maps each literal `current_step` / `terminal_reason` → one of `Pending | Spec | Research | Plan | Implement | Validate | Complete | Blocked | Needs-input | Deferred`, separately for feature vs bug literals — unknown / `None` `current_step` (queued-but-unstarted) falls back to `Pending` (the dedicated entry node), NOT `Spec`. Pure function; no script changes.
- [x] `pipeline_visualizer/leases.py` — parse `leases.json`; compute per-entry heartbeat freshness using `lazy_coord.py`'s rule (`heartbeat_epoch + ttl_seconds >= now`); expose `{wi_id, worker_pid, worktree_slot, term_token, heartbeat_fresh, age_seconds}`.
- [x] `pipeline_visualizer/__main__.py` — CLI entry: `--repo-root` (default cwd), `--port` (default e.g. 8765), `--host` (default 127.0.0.1). Prints the serve URL.
- [x] Tests: `test_pipeline_visualizer.py` — curated_stage mapping table (every documented literal → expected node, incl. all side-states); cache debounce (N concurrent reads → 1 probe within TTL window, asserted via a probe-call counter + monkeypatched clock); leases freshness boundary (fresh vs expired at `ttl_seconds` edge); probe JSON-parse against a captured real `lazy-state.py` fixture; `/api/state` and `/api/queue` return well-formed JSON over a live `ThreadingHTTPServer` on an ephemeral port.

**Minimum Verifiable Behavior:** `python -m pipeline_visualizer --repo-root C:\Users\Jacob\source\repos\claude-config --port 0` boots, and `GET /api/state` returns JSON whose every item's `curated_stage` matches the `current_step` reported by directly running `lazy-state.py --feature-id <id>` for the same item (the SPEC's "Token on correct stage" validation row, asserted at the API layer before any UI exists).

**Runtime Verification** *(checked by pytest + a one-line curl/Invoke-WebRequest smoke):*
- [ ] `GET /api/state` over a live server returns 200 + parseable JSON with a `features[]` + `bugs[]` array, each item carrying `curated_stage`. (reachability-smoke — workstation-eligible)
- [ ] `GET /api/queue` returns the current `queue.json` order for both pipelines. (reachability-smoke — workstation-eligible)
- [ ] Cache: instrument the probe with a call counter; 5 rapid `/api/state` hits inside one 2.0s window trigger exactly 1 underlying probe.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/pipeline_visualizer/server.py` — new
- `user/scripts/pipeline_visualizer/probe.py` — new
- `user/scripts/pipeline_visualizer/cache.py` — new
- `user/scripts/pipeline_visualizer/curated_stage.py` — new
- `user/scripts/pipeline_visualizer/leases.py` — new
- `user/scripts/pipeline_visualizer/__main__.py` — new
- `user/scripts/test_pipeline_visualizer.py` — new

**Testing Strategy:**
Pure-function units (curated_stage, leases freshness) tested directly. Cache tested with a monkeypatched clock + probe-call counter (no sleeps). Server tested by binding an ephemeral port, issuing real HTTP requests via `http.client`, asserting status + JSON shape. Probe tested against a captured real-script-output fixture so a contract drift in `lazy-state.py` surfaces as a test failure, not a silent UI mismatch.

**Integration Notes for Next Phase:**
- The `/api/state` JSON shape is the contract the frontend renders against — lock its top-level shape here (`{features: [...], bugs: [...], leases: [...], roadmap: {...}, server_time: "<ISO>"}`) and document it so Phase 2/3 build to it.
- `curated_stage` values are the canonical stage IDs Phase 3's preset layout will key node coordinates on; the side-state values (`Blocked`/`Needs-input`/`Deferred`) drive both the graph side-track AND the Phase 2 triage strip.
- Keep the cache TTL (2.0s) a single named constant — Phase 2's UI poll interval (2.5s) must stay strictly greater, per Decision 12.

**Implementation Notes (2026-06-15 — part-1 / Phase 1, executed inline by /lazy-batch):**
- **Status:** In-progress (all Phase 1 deliverables implemented + tested; top-level validation tail pending).
- **WU-1 (done):** `pipeline_visualizer/__init__.py`, `curated_stage.py`, `leases.py`. `curated_stage()` is a pure mapping built from the literal `current_step` strings grepped from `lazy-state.py` (feature track) and the `STEP_*` constants in `bug-state.py` (bug track), plus the shared `terminal_reason` side-states. terminal_reason DOMINATES (a side-state terminal wins over any workflow step). Unknown/None/empty step → `Pending` (NOT Spec). Gotcha: the prefix-fallback rules are colon/dot-anchored (`"Step 9:"`, not `"Step 9"`) so an unknown `"Step 99: ..."` falls through to Pending instead of matching the Validate phase. `leases.py` imports `lazy_coord._parse_iso` when importable and replicates the exact `strptime("%Y-%m-%dT%H:%M:%SZ")` parse as a documented fallback; freshness uses `>=` so exactly-at-expiry is fresh, one second past is stale.
- **WU-2 (done):** `probe.py`, `cache.py`. `cache.TtlCache` is a read-through double-checked-`threading.Lock` cache; `DEFAULT_TTL_SECONDS = 2.0` is the single named constant. `probe.probe_state(repo_root)` shells `lazy-state.py --repo-root <root>` and `bug-state.py --repo-root <root>` via `subprocess.run(capture_output=True, text=True)`, parses JSON, attaches `curated_stage`, and reads `docs/features/queue.json` / `docs/bugs/queue.json` / `leases.json` / `ROADMAP.md`. Malformed script output is flagged on the item (`error` key, `curated_stage=Pending`) rather than crashing. Returns the aggregate `{features, bugs, leases, roadmap, server_time}` shape locked above.
- **WU-3 (done):** `server.py`, `__main__.py`. `server.py` subclasses `SimpleHTTPRequestHandler` under `ThreadingHTTPServer`; `/api/state` (cached probe) + `/api/queue` handled explicitly (GET), all other paths → 404 here (static serving is Phase 2). `__main__.py` is the CLI (`--repo-root` default cwd, `--port` default 8765, `--host` default 127.0.0.1) and prints the serve URL.
- **Tests:** `user/scripts/test_pipeline_visualizer.py` (38 tests) — curated rollup for every documented literal incl. all side-states (feature + bug), leases boundary, cache debounce via injected fake clock + call counter (no sleeps), probe parse + malformed handling, and a live `ThreadingHTTPServer` on an ephemeral port driving the REAL `lazy-state.py` against a temp fixture (proves the contract end-to-end). Quality gate: full `python -m pytest user/scripts/ -q` green.

---

### Phase 2: Static frontend shell + read-only three-pane render

**Scope:** The browser frontend: three-pane layout (hero graph region + bottom-left queues + bottom-right fleet), color/shape encoding, headless→preset layout bootstrap, polling loop with the live dot + Connection-Lost guard. Read-only — no graph traversal animation yet (Phase 3), no reorder writes yet (Phase 4). The graph region renders the static stage map with tokens at their current stage (no animation).

**Deliverables:**
- [x] `pipeline_visualizer/static/index.html` — three-pane shell (hero graph / queues / fleet) + persistent triage strip + footer live dot. (WU-5)
- [x] `pipeline_visualizer/static/app.js` — poll loop (interval 2.5s) `fetch('/api/state')`; on 200 render panes; on fail/timeout flip the live dot red, dim the screen, show "Connection Lost" banner (never render stale-as-live). (WU-5; AbortController hard timeout 2.0s trips the guard on a hung probe.)
- [x] `pipeline_visualizer/static/cytoscape.umd.js` + `dagre.js` + the Cytoscape-dagre adapter — vendored UMD (no build step), referenced by `<script>` per Decision 7. (WU-4: cytoscape@3.30.2, dagre@0.8.5, cytoscape-dagre@2.5.0 committed as-is.)
- [x] Layout bootstrap: on first load, build the stage-node graph, run `dagre rankDir:'LR'` in a **headless** Cytoscape instance, extract settled `(x,y)` for both tracks, then render the live canvas with the `preset` layout (immutable positions). Never run a layout on poll. (WU-5; settled coords exposed as `window.PV_STAGE_COORDS` for Phase 3.)
- [x] Color + shape encoding (redundant / colorblind-safe) from the SPEC table: Pending gray/hollow, Running blue/▶, Complete green/✓, Needs-Input orange/hexagon, Blocked red/octagon, Deferred purple/dashed-ghost. (WU-5)
- [x] Queues pane: two parallel vertical lists (Features, Bugs) from `/api/queue`; rows show ID + tier/ad-hoc/stub badges. Static (drag wiring is Phase 4). (WU-5; rendered from `/api/state` features/bugs which carry `queue_meta` badges — same order as `/api/queue`.)
- [x] Fleet pane: grid of `wt-NN` slot cards from `leases[]`; each badges leased item ID + shape/color + derived branch + heartbeat freshness + worker pid. Empty when `leases[]` is empty (single-threaded `/lazy-batch`). (WU-5; explicit "no active workers" empty state.)
- [x] Triage strip: "Action Required" bar listing every item whose `curated_stage` is a side-state (Blocked / Needs-Input / Deferred). (WU-5)
- [x] Tests: a Python-side test asserting the static assets are served (`GET /` → `index.html` 200, `GET /static/app.js` → 200) and a documented manual browser smoke checklist (the UI behaviors are validated manually — claude-config has no headless-browser harness; recorded in MANUAL_TESTING.md). (WU-4: `TestStaticServing` 7 cases incl. API-wins-over-static regression + path-traversal guard. Manual checklist authored in WU-5.)

**Minimum Verifiable Behavior:** Opening `http://127.0.0.1:<port>/` in a browser renders all three panes populated from live `/api/state`; each queue item's token sits on the curated stage matching the script's `current_step`; killing the server flips the live dot red + shows the Connection-Lost banner within one poll interval. (Manual browser smoke — claude-config has no DOM test harness; the static-asset serving is the automated slice.)

**Runtime Verification** *(checked by pytest for serving + manual browser checklist for UI):*
- [x] `GET /` and `GET /static/app.js` return 200 with the expected content-type. (reachability-smoke — workstation-eligible; `TestStaticServing` + an integration boot against this repo confirmed `/`→text/html, `/static/app.js`→text/javascript, `/static/styles.css`→text/css, `/static/cytoscape.umd.js`→200, `/api/state`+`/api/queue`→200 JSON.)
- [ ] Manual: three panes render; tokens land on correct stages vs `lazy-state.py` JSON; live dot is green while polling succeeds. *(human — MANUAL_TESTING.md; ticked by the validation tail)*
- [ ] Manual: stop the server → live dot red + "Connection Lost" banner within ≤1 poll (2.5s); no stale data shown as live. *(human — MANUAL_TESTING.md; ticked by the validation tail)*

**Implementation Notes (Phase 2):**
- Vendored UMD (committed as-is, no build step — Decision 7): cytoscape@3.30.2, dagre@0.8.5, cytoscape-dagre@2.5.0 under `static/`.
- Static serving: `server.py` roots `SimpleHTTPRequestHandler` at `static/` via the `directory=` kwarg; `do_GET` matches `/api/*` (query-string-tolerant) BEFORE the static fallthrough, rewrites `/static/<x>`→`/<x>`. The `directory=` root confines reads (path-traversal can't reach backend source — asserted).
- `__main__.py` self-adds `user/scripts/` to `sys.path` so the probe's canonical `import lazy_coord` resolves when launched from outside the scripts dir (else it falls back to a replicated `_parse_iso`). The `-m pipeline_visualizer` invocation itself still needs cwd=`user/scripts` or `PYTHONPATH` — both documented in MANUAL_TESTING.md.
- Layout: headless dagre `rankDir:'LR'` settles once; live canvas uses `preset` (immutable). Settled stage→(x,y) map exposed as `window.PV_STAGE_COORDS` — the Phase 3 animation substrate. Tokens are FLAT peers (no `parent:` / compound nodes), z-index 10 above stage nodes. Full re-render per poll (Phase 3 swaps to cy.add/remove + animate diff).
- The repo under test currently has no `docs/features/queue.json`, so a live boot shows empty panes — populated rendering is verified against a seeded fixture per the manual checklist.

**Prerequisites:**
- Phase 1: `/api/state` + `/api/queue` JSON contract and static-asset serving from the `ThreadingHTTPServer`.

**Files likely modified:**
- `user/scripts/pipeline_visualizer/static/index.html` — new
- `user/scripts/pipeline_visualizer/static/app.js` — new
- `user/scripts/pipeline_visualizer/static/styles.css` — new
- `user/scripts/pipeline_visualizer/static/cytoscape.umd.js` — new (vendored)
- `user/scripts/pipeline_visualizer/static/dagre.js` — new (vendored)
- `user/scripts/pipeline_visualizer/static/cytoscape-dagre.js` — new (vendored)
- `user/scripts/pipeline_visualizer/server.py` — wire static-root resolution
- `user/scripts/test_pipeline_visualizer.py` — extend with static-serving assertions
- `docs/features/lazy-pipeline-visualizer/MANUAL_TESTING.md` — new (browser smoke checklist)

**Testing Strategy:**
Automated: HTTP-level assertions that static assets serve with correct status/content-type. UI behavior (rendering, color/shape, live dot, Connection-Lost) is validated via the documented manual browser checklist, since this repo has no headless-browser harness and adding one is out of scope (v1). The layout-bootstrap correctness (headless→preset) is observable in the manual smoke (no jitter, stable node positions across polls).

**Integration Notes for Next Phase:**
- The preset coordinate map (stage ID → `(x,y)`) computed here is the fixed substrate Phase 3 animates tokens across. Expose it as a single module-level object so Phase 3's animation reads the same coords.
- Tokens are rendered as flat peers (NOT compound nodes) at a higher z-index — Phase 3's per-node scaling + animation depends on this flat model. Do not switch to compound nodes (fatal jitter per research finding 2).
- The poll loop is the diff site Phase 3 hooks: Phase 2 does full re-render per poll; Phase 3 replaces that with `cy.add`/`cy.remove`/`animate` diffing.

---

### Phase 3: Unified two-track graph + traversal animation

**Scope:** Upgrade the static render into the live unified two-track graph (Decision 10): Features = top track of circle tokens, Bugs = bottom track of square tokens on one shared canvas. Add poll-diff traversal animation, per-node representation scaling, side-state ejection, node drill-down, and Complete-state fade-and-drop (Decision 13). This is the hero-telemetry phase.

**Deliverables:**
- [x] Unified two-track layout: feature track (top, circles) + bug track (bottom, squares) share one canvas with aligned stage columns so shared-fleet contention is visible.
- [x] Token model: each item is a separate token positioned in a micro-grid around its current stage node; tokens carry ID + priority color.
- [x] Per-node representation scaling: 1–5 items = individual animated tokens; 6–20 = count badge (click → popover list); 20+ = node collapses to a sortable swimlane/table. Applied per-node.
- [x] Poll-diff animation: on each poll, `cy.add()` new IDs, `cy.remove()` gone IDs, `animate({position, duration:400, easing:'ease-in-out-cubic'})` IDs whose `curated_stage` changed. Never clear+redraw.
- [x] Multi-stage-jump handling: a token whose stage advanced more than one curated node **arcs/fades** to the destination rather than tweening through skipped nodes (no false-intermediate-state).
- [x] Side-state branching: Blocked / Needs-Input / Deferred tokens eject onto a parallel Y-axis off the main track; the settled node border-pulses; encoding uses the hexagon/octagon/dashed shapes from Phase 2.
- [x] Node drill-down: clicking a curated node opens a panel listing the literal `current_step` / `terminal_reason` values it rolls up (the full ~16-step / ~11-terminal machine behind the curated 6).
- [x] Complete-state fade-and-drop (Decision 13): a token reaching Complete fades to ~50% opacity ~10s later, then drops off the graph once its `COMPLETED.md` / `FIXED.md` receipt exists (signaled by the backend); older completions collapse into an expandable count/log on the Complete node.
- [x] Backend support: `/api/state` exposes per-item `receipt_present` (COMPLETED.md / FIXED.md existence) so the frontend knows when to drop a completed token — a read-only stat check, no script change.
- [x] Tests: backend `receipt_present` detection (COMPLETED.md present/absent fixtures); the curated-rollup drill-down content is derived from the same Phase-1 table, so its correctness is the existing mapping test. UI animation/scaling/drill-down/fade-drop validated via the manual browser checklist.

**Minimum Verifiable Behavior:** With a repo whose items span multiple stages, the graph shows feature tokens on the top track and bug tokens on the bottom track on one canvas; advancing an item one stage (re-run a `/lazy` cycle, or hand-edit a fixture sentinel) causes its token to animate to the next stage on the next poll; a multi-stage jump arcs rather than tweening through skipped nodes. (Manual browser smoke; backend `receipt_present` slice is automated.)

**Runtime Verification** *(backend automated + manual browser checklist):*
- [ ] Backend: `receipt_present` is `true` exactly when `COMPLETED.md`/`FIXED.md` exists for the item (fixture-driven pytest).
- [ ] Manual: token animates to the next stage on a single-stage advance; a multi-stage jump arcs/fades (no tween through skipped node).
- [ ] Manual: a node with >5 items shows a count badge (click → list); a side-state item ejects off-track with the right shape + border-pulse.
- [ ] Manual: a Completed item fades ~10s after Complete, then drops once `receipt_present`; older completions appear in the Complete-node collapsed log.

**Prerequisites:**
- Phase 2: preset coordinate map, flat-token render model, poll loop, color/shape encoding.

**Files likely modified:**
- `user/scripts/pipeline_visualizer/static/app.js` — token model, diff animation, scaling, side-state, drill-down, fade-drop
- `user/scripts/pipeline_visualizer/static/styles.css` — track layout, side-state offsets, fade treatment
- `user/scripts/pipeline_visualizer/probe.py` — add `receipt_present` per item (stat COMPLETED.md / FIXED.md)
- `user/scripts/test_pipeline_visualizer.py` — `receipt_present` detection tests
- `docs/features/lazy-pipeline-visualizer/MANUAL_TESTING.md` — extend with graph/animation checklist

**Testing Strategy:**
The backend additions (`receipt_present`) are unit-tested with present/absent fixtures. Animation, per-node scaling, side-state ejection, drill-down content, and fade-and-drop are validated through the documented manual browser checklist (no DOM harness in this repo). The drill-down's literal→curated content is guaranteed by the Phase-1 mapping test (single source of truth), so the UI only renders that table.

**Integration Notes for Next Phase:**
- The Complete-state drop relies on `receipt_present` from the backend — Phase 4's reorder must not interfere with the receipt-driven removal (they touch different items / panes).
- The queue pane rows (Phase 2, static) become drag-reorderable in Phase 4; the graph tokens are NOT draggable — keep the two interaction models separate so a graph drag never mutates queue order.

**Implementation Notes (2026-06-15 — part-3 / Phase 3, executed inline by /lazy-batch):**
- **Status:** In-progress (all Phase 3 deliverables implemented + backend tested; manual UI checklist + top-level validation tail pending).
- **WU-6 backend (TDD, done):** `probe.py` adds a read-only `receipt_present` per item — `receipt_present(item_dir, "COMPLETED.md")` for features, `"FIXED.md"` for bugs. `item_dir` is resolved from the state script's OWN `spec_path` output (authoritative absolute path), falling back to `<pipeline_dir>/<spec_dir|id>`. It is a plain `.exists()` stat, NOT the content-validity gate (`lazy_core.has_completion_receipt`) — the UI only needs presence to know when to drop a token (Decision 13). Tests: `TestReceiptPresent` (5) — feature/bug present+absent + a per-item-path isolation case (receipt in feat-a's dir does not mark feat-b). Full `pytest user/scripts/ -q` green (562).
- **WU-6 UI (manual-checklist, done):** `app.js` `renderGraphTokens` rewritten from Phase-2 full-redraw to a **poll-diff** model — `cy.getElementById` per token; `cy.add` new IDs, `animate({position,duration:400,easing:'ease-in-out-cubic'})` moved IDs, `cy.remove` vanished IDs; a module-level `tokenSeen` map is the diff source of truth (never clear+redraw). Multi-stage jumps (|Δstage|>1) **arc/fade** (opacity 1→0, reposition, 0→1) instead of tweening through skipped nodes. Per-node scaling: ≤5 = individual tokens, 6–20 = a count `badge` node (click → popover listing members), 20+ = `swimlane`-styled badge. Side-states (Blocked/Needs-input/Deferred) eject onto a further-off parallel Y-lane and add a `.pulse` class to the settled stage node (oscillating border width via `startPulseAnimation`). Drill-down: tapping a `stage` node opens `#drill-panel` listing the live literal `current_step`/`terminal_reason` rows for that curated node (read from `PV._lastState`); tapping a badge lists its members; tapping empty canvas dismisses. Complete fade-and-drop: token reaching Complete records `completeSince`, fades to 0.5 opacity after `COMPLETE_FADE_MS` (10s), and drops once `receipt_present` (recorded into `completionLog`). `window.PV` moved ABOVE `start()` (renderAll writes `PV._lastState` synchronously on the first poll). `node --check` clean.
- **Gotcha:** the count-badge path REMOVES any individual tokens previously rendered on that node (and their `tokenSeen` entries) so a node crossing the 5→6 boundary collapses cleanly to the badge without orphaned tokens.

---

### Phase 4: Queue drag-reorder write path

**Scope:** The single write path: `POST /api/queue` reorders `queue.json` via temp file + `os.replace` + AV-lock retry (Decision 11), refused entirely while a batch run-marker is present, with disabled-handle UX (banner, `not-allowed` cursor, tooltip). Honors the "one writer per file" rule.

**Deliverables:**
- [x] `POST /api/queue` endpoint: body = new ID order for one pipeline (features OR bugs); validates the new order is a permutation of the existing IDs (no add/drop), then writes.
- [x] Atomic write: read `queue.json` → reorder the array → write temp file → `os.replace`, wrapped in a 3× / 50ms retry catching `PermissionError` for `[WinError 5]` / `[WinError 32]` (Windows Defender file locks). On exhausted retries, return 503 + a clear error the UI surfaces (never silently lose a reorder).
- [x] Run-marker refusal: detect the batch run-marker; while present, `POST /api/queue` returns 409 and the GET state exposes a `queue_locked: true` flag. Refusal is the floor (Decision 6/11) — intent-log is the documented v2 upgrade, NOT built here.
- [x] Frontend drag-reorder: queue rows become draggable (HTML5 DnD or a tiny vendored sortable); on drop, `POST /api/queue` with the new order; optimistic reorder reconciled against the next poll.
- [x] Locked-state UX: when `queue_locked`, drag handles are visibly disabled (cursor `not-allowed`), a "Queue Locked: orchestrator executing" banner shows, and a tooltip explains why — handles are disabled, never hidden (Decision 11).
- [x] Tests: permutation validation (reject add/drop/dupe); atomic-write round-trip (reorder persists, file remains valid JSON, trailing newline preserved to match `lazy-state.py`'s `_atomic_write`); AV-lock retry (monkeypatch `os.replace` to raise `PermissionError [WinError 32]` twice then succeed → write completes within 3 tries, asserted via call count); run-marker refusal (marker present → `POST` returns 409 + `queue.json` byte-identical).

**Minimum Verifiable Behavior:** With no run-marker present, `POST /api/queue` with a reordered ID list updates `queue.json`'s array order atomically and a subsequent `lazy-state.py` run picks the new front-of-queue item; with a run-marker present, the same POST returns 409 and `queue.json` is byte-identical (the SPEC's "Reorder persists (idle)" and "Reorder refused (run active)" validation rows, asserted at the API layer).

**Runtime Verification** *(automated pytest + manual browser checklist):*
- [ ] `POST /api/queue` (idle) reorders `queue.json` atomically; re-running the state script reflects the new order. (reachability-smoke — workstation-eligible)
- [ ] `POST /api/queue` (run-marker present) → 409; `queue.json` byte-identical.
- [ ] Retry: `os.replace` raising `PermissionError [WinError 32]` twice then succeeding → write completes (≤3 tries), reorder not lost.
- [ ] Manual: drag a queue row when idle → persists; with run-marker → handles disabled + banner + `not-allowed` cursor + tooltip.

**Prerequisites:**
- Phase 1: `/api/queue` GET + `queue.json` read; the `ThreadingHTTPServer` routing.
- Phase 2: queue pane rows to attach drag handles to.

**Files likely modified:**
- `user/scripts/pipeline_visualizer/server.py` — `POST /api/queue` route + run-marker detection + `queue_locked` flag on GET
- `user/scripts/pipeline_visualizer/queue_writer.py` — new: permutation-validated atomic reorder write with AV-lock retry
- `user/scripts/pipeline_visualizer/static/app.js` — drag wiring + POST + locked-state UX
- `user/scripts/pipeline_visualizer/static/styles.css` — disabled-handle + locked banner styling
- `user/scripts/test_pipeline_visualizer.py` — permutation validation, atomic round-trip, retry, refusal tests
- `docs/features/lazy-pipeline-visualizer/MANUAL_TESTING.md` — extend with reorder checklist

**Testing Strategy:**
The write path is fully unit-testable in Python: permutation validation, atomic round-trip (assert resulting file is valid JSON matching `lazy-state.py`'s temp+`os.replace`+trailing-newline convention so `/lazy` reads it cleanly), AV-lock retry (monkeypatched `os.replace`), and run-marker refusal (marker fixture → 409 + byte-identical file). The drag UX + locked-state visuals are validated in the manual browser checklist.

**Completion (gate-owned):** SPEC.md / PHASES.md top-level `**Status:**` flips, the `COMPLETED.md` receipt, and the ROADMAP completion mark are owned by the `__mark_complete__` gate after the validation tail (full quality-gate suite + operator `SKIP_MCP_TEST.md`). They are intentionally NOT authored as deliverable checkboxes here.

**Integration Notes for Next Phase:**
- This is the last implementation phase. When Phase 4's work lands and all four phases' deliverables are checked, the implementer sets the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and lets the state machine route to the validation tail. Do NOT flip to Complete or write COMPLETED.md (gate-owned).
- v2 backlog (NOT in scope): multi-repo switcher, filesystem-watch liveness, intent-log mid-run reorder concurrency upgrade — recorded in SPEC Open Questions.

**Implementation Notes (2026-06-15 — part-3 / Phase 4, executed inline by /lazy-batch):**
- **Status:** In-progress (all Phase 4 deliverables implemented; WU-7 fully TDD-tested, WU-8 manual-checklist; top-level validation tail pending).
- **WU-7 (TDD, done):** new `queue_writer.py` — the single guarded write path. `reorder_queue(path, order)` reads queue.json (normalizes a bare list to `{"queue": [...]}`, preserving sibling top-level keys + per-entry fields), `validate_permutation` rejects add/drop/dupe (`PermutationError`, NO write), then writes `json.dumps(doc, indent=2) + "\n"` via `tempfile.mkstemp` in the same dir + `os.replace`, matching `lazy-state.py`'s `_atomic_write` convention so `/lazy` reads it cleanly. `os.replace` is wrapped in a 3×/50ms retry catching `PermissionError` whose `winerror ∈ {5,32}` (Windows Defender locks); exhaustion → `QueueWriteError`. `server.py` adds `POST /api/queue` (body `{pipeline, order}`) → `reorder_queue` mapping `PermutationError`→400, `QueueWriteError`→503; refuses with 409 while a run-marker is present BEFORE reading the body; `/api/state` adds a `queue_locked` flag computed at RESPONSE time (NOT cached with the heavy probe) via `_run_marker_present()` → `lazy_core.read_run_marker()` (the SoT; fails open to unlocked if lazy_core is unimportable). Tests: `TestQueueWriterPermutation` (4), `TestQueueWriterAtomic` (2), `TestQueueWriterRetry` (2), `TestPostQueueRoute` (5: idle-persist, 409+byte-identical, queue_locked true/false, bad-permutation 400). Run-marker fixtures use a `LAZY_STATE_DIR` temp override.
- **WU-8 (manual-checklist, done):** `app.js` — Queues rows gain a visible drag handle (`⠿`) and HTML5 DnD (no build step / no vendored lib): `dragstart`/`dragover`/`dragend` reorder the DOM, `commitDragOrder` POSTs the new order only when it changed. Optimistic reorder via a module-level `pendingReorder[track]` applied in `applyPendingOrder` and cleared once the server order reconciles on the next poll (a failed/409 POST drops the optimistic order so the row snaps back). Locked state: `queueLocked` mirrors `state.queue_locked`; locked rows get `queue-row--locked` (cursor `not-allowed`), a tooltip, `draggable=false`, and a "Queue Locked: orchestrator executing" banner (`#queue-lock-banner`) — handles stay VISIBLE, never hidden (Decision 11). Features/Bugs reorder independently (`pipeline` = `features`/`bugs`). `styles.css` adds handle/locked/banner/dragging styles; `index.html` adds the banner div. `node --check` clean. Write-path correctness is fully covered by WU-7's Python tests; the drag UX + locked visuals are in MANUAL_TESTING.md Phase 4.
- **Part-3 close:** full `python -m pytest user/scripts/ -q` green (575). All four phases' implementation deliverables checked. Per-phase `**Runtime Verification**` rows remain UNCHECKED — owned by the validation tail. Top-level PHASES `**Status:**` set to In-progress (implementation done, validation pending); SPEC/PHASES Complete flip + COMPLETED.md are gate-owned (`__mark_complete__`).
