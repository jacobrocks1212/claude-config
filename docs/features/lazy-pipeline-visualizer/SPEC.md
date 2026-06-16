# Lazy Pipeline Visualizer — Feature Specification

> A live, local web control-plane for the lazy feature **and** bug pipelines: view and drag-reorder the queues, see the worktree/branch fleet and what each is working on, and watch items traverse a unified directed stage-graph computed from the existing `lazy-state.py` / `bug-state.py` JSON.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-15

**Depends on:** (none)

> Formally no dep-block entries (this repo's specs carry no `queue.json` dependency graph). Substantive (non-block) dependencies are **implemented data contracts**, not sibling specs:
> - `lazy-state.py` / `bug-state.py` JSON output (per-item pipeline state) — `user/scripts/`. The visualizer is a **read renderer** over this contract; it must not re-implement state inference.
> - `lazy_coord.py` lease model — `leases.json` (`wi_id → wt-NN slot → p/<id>-<slug>` branch, heartbeat, worker pid). *Fleet view is populated only when the concurrency plane (`/lazy-worker` + `lazy_coord.py`) is active; single-threaded `/lazy-batch` leases nothing, so the Fleet pane is empty under a plain workstation run.*
> - `docs/features/queue.json` + `ROADMAP.md`; `docs/bugs/queue.json` (+ on-disk discovery fallback).
> - Sentinel files (YAML frontmatter): `BLOCKED.md`, `NEEDS_INPUT.md`, `VALIDATED.md`, `COMPLETED.md` / `FIXED.md`, `DEFERRED*.md`, etc.
>
> These artifacts live in the **consuming repo** (e.g. algobooth, or claude-config itself), not necessarily in the repo the visualizer is launched from — it targets one repo via `--repo-root`.

---

## Executive Summary

The lazy pipeline is fully deterministic: `lazy-state.py` (features) and `bug-state.py` (bugs) infer every item's state from on-disk sentinels and emit machine-readable JSON. Today the only windows onto that state are two **text** dashboards (`/lazy-status`, `/lazy-bug-status`). There is no way to *see* the pipeline as a shape, watch work move through it, or reorder the queue without hand-editing JSON.

This feature adds a **local web control-plane** — a thin Python (stdlib `http.server`) backend wrapping the existing state-script JSON + `queue.json` + `leases.json`, and a browser frontend (Cytoscape.js, no build step) rendering a **three-pane** operator dashboard: a full-width **pipeline graph** (hero), the **queues** (bottom-left, drag-to-reorder), and the **worktree fleet** (bottom-right). Both pipelines share one **unified two-track graph** — Features on the top track (circle nodes), Bugs on the bottom track (square nodes) — so contention over the shared worktree pool is visible at a glance. Each queue item is a **token** placed on its current curated stage; tokens animate to new stages on each poll. Liveness is **interval polling** (UI 2.5s) over a **TTL-cached** (2.0s) backend probe.

The backend is a **renderer, not a second state machine**: it shells the existing scripts for state and never re-implements inference. The only write path is queue reorder, guarded by run-marker refusal + atomic-replace-with-retry per the "one writer per file" rule.

## Locked Decisions

**Round 1 — foundations**
1. **Form factor — local web app** (Python backend + browser frontend).
2. **v1 is interactive, including queue drag-reorder** (writes `queue.json` back, guarded).
3. **Curated ~7-stage graph with drill-down** — Spec → Research → Plan → Implement → Validate → Complete + Blocked / Needs-input / Deferred side-states; click a node for the literal sub-states it rolls up.
4. **Liveness via interval polling.**

**Round 2 — shape**
5. ~~Separate switchable graphs~~ → **superseded by Decision 10 (unified two-track graph)** after Deep Research.
6. **Reorder refused while a batch run-marker is present** — preserved as the floor; hardened by Decision 11.
7. **Cytoscape.js, no build step** (standalone UMD/ES `<script>`).
8. **Single project via `--repo-root`** (default cwd); multi-repo is v2.
9. **Backend: stdlib `http.server`** — zero new deps. *Refined by Decision 12 → `ThreadingHTTPServer`.*

**Round 3 — post-research (authoritative: Gemini Deep Research)**
10. **Unified two-track graph.** Features = top track (circle nodes), Bugs = bottom track (square nodes), one shared canvas. Avoids the "change blindness" of tab-switching and surfaces shared-fleet contention. (Supersedes Decision 5.)
11. **Reorder safety = run-marker refusal + atomic-replace-with-retry.** When the run-marker is present, drag handles are visibly disabled (cursor `not-allowed`, banner "Queue Locked: orchestrator executing"), never hidden. When idle, writes go via temp file + `os.replace`, wrapped in a 3× / 50ms retry catching `PermissionError [WinError 5]/[WinError 32]` (Windows Defender file locks). Intent-log (the research gold standard) is the documented v2 upgrade if mid-run reorder becomes a real need.
12. **Backend hardening:** `ThreadingHTTPServer` (not `HTTPServer`) + a server-side **read-through TTL cache** (double-checked `threading.Lock`) over the git-shelling probe. **UI poll 2.5s / server TTL 2.0s.** Interval polling, not SSE.
13. **Complete-state handling:** a completed item fades to ~50% opacity ~10s after reaching Complete, then **drops off the graph** once its `COMPLETED.md` / `FIXED.md` receipt exists; older completions collapse into an expandable count/log on the Complete node. Bounds the canvas while keeping the "what just finished" signal.

## User Experience

### Three-pane layout (the "glance test" — read global state in <3s)
- **Top / hero — Pipeline Graph** (full width): the unified two-track DAG; primary telemetry.
- **Bottom-left — Queues**: two parallel vertical Kanban lists (Features, Bugs); drag-to-reorder; badges for tier / ad-hoc / stub.
- **Bottom-right — Fleet**: grid of worktree-slot cards (`wt-NN`), each badging its leased item's ID + shape/color + branch (`p/<id>-<slug>`) + heartbeat freshness + worker pid. Empty under single-threaded `/lazy-batch`.
- **Triage strip**: a persistent "Action Required" bar mirroring every side-state (Blocked / Needs-Input / Deferred) item so a stalled fleet is never hunted for.
- **Live indicator**: a footer dot tied to 200-OK polls; flips red + dims the screen with a "Connection Lost" banner on any poll fail/timeout (never present stale data as live).

### Graph behavior
- **Tokens, not compound nodes.** Stage nodes are a fixed background map; each item is a separate token (circle=feature, square=bug) positioned in a micro-grid around its current stage. Tokens carry ID + priority color.
- **Per-node representation scaling:** 1–5 items = individual animated tokens; 6–20 = a count badge (click → popover list); 20+ = that node collapses to a sortable swimlane/table. Applied per-node.
- **Traversal animation:** on a poll diff, a token whose stage changed animates (`duration:400, ease-in-out-cubic`) to the new stage's coordinate. Multi-stage jumps **arc/fade** rather than tweening through skipped nodes (no false-intermediate-state implication).
- **Side-states** branch off the track on a parallel Y-axis; the token visibly "ejects" from the flow; the settled node border-pulses.
- **Drill-down:** clicking a curated node opens a panel listing the literal `current_step` / `terminal_reason` values it rolls up (the full ~16-step / ~11-terminal machine stays behind this).

### Color & shape encoding (redundant — colorblind-safe)
| State | Color | Shape / icon | Treatment |
|---|---|---|---|
| Pending / Queue | Gray `#888888` | hollow outline | static thin border |
| Running | Blue `#0074D9` | solid + ▶ | pulsing heartbeat on Fleet card |
| Complete | Green `#2ECC40` | ✓ | fade to 50% after 10s, then drop once receipted (Decision 13) |
| Needs-Input | Orange `#FF851B` | **hexagon** | high-frequency pulse, bold border, pushed to top of backlog |
| Blocked | Red `#FF4136` | **octagon** | thick dashed border, offset from main track |
| Deferred | Purple `#B10DC9` | dashed outline | ghosted 40% |

Intervention states deliberately break the circle/square geometry so anomalies are pre-attentive.

## Technical Design

```
browser frontend  ──HTTP poll 2.5s──▶  ThreadingHTTPServer  ──(TTL 2.0s cache)──▶ lazy-state.py --feature-id … (JSON)
(Cytoscape graph  ◀──JSON────────────  (stdlib renderer)     ──shell────────────▶ bug-state.py  --bug-id …    (JSON)
 + queues + fleet) ──POST reorder────▶                       ──read─────────────▶ queue.json / leases.json / ROADMAP.md
                                                             ──write (guarded)──▶ queue.json  (temp + os.replace + retry)
```

- **State is never re-inferred.** The backend calls the existing scripts (`--feature-id <id>` / `--bug-id <id>` scoping already exists) and parses their JSON. Verified empirically: `lazy-state.py --repo-root .` emits `{feature_id, feature_name, spec_path, current_step, sub_skill, terminal_reason, notify_message, diagnostics, device_deferred_features}`.
- **Curated-node rollup is a display concern** — a static table mapping each literal `current_step` / `terminal_reason` → curated node (below). The backend attaches a `curated_stage` field; it does not change the scripts.
- **Layout:** on load, run `dagre` `rankDir:'LR'` in a **headless** Cytoscape, extract settled `(x,y)` for both tracks, then render the live canvas with the **`preset`** layout (immutable positions). Never run a layout on poll; never use `cola`/`cose`/`elk`.
- **Backend:** `ThreadingHTTPServer` subclassing `SimpleHTTPRequestHandler` — API routes (`/api/state`, `/api/queue` GET/POST) handled explicitly, static frontend assets deferred to super. Read-through TTL cache (double-checked lock) over the probe.
- **Reorder write:** read queue.json → mutate array order → temp file → `os.replace` (3×/50ms retry). Refused entirely while run-marker present.

### Curated-node rollup (display mapping)
| Curated node | Feature literal states | Bug literal states |
|---|---|---|
| Spec | Step 4 / 4.5 / 4.6 (spec, stub, realign) | Step 4 (spec-bug / investigate) |
| Research | Step 5 (prompt / integrate / needs-research) | — (bug track omits Research) |
| Plan | Step 6, Step 7a write-plan | Step 6 write-plan |
| Implement | Step 7a execute-plan + flip pseudo-skills | Step 6/7 execute-plan |
| Validate | Step 9 mcp-test + validated pseudo-skills | Step 9 mcp-test + validated |
| Complete | Step 10 `__mark_complete__` / COMPLETED.md | Step 10 `__mark_fixed__` / FIXED.md |
| Blocked (side) | terminal `blocked` | terminal `blocked` |
| Needs-input (side) | `needs-input` / `needs-research` / `needs-spec-input` | `needs-input` |
| Deferred (side) | cloud/device deferral terminals | cloud/device deferral terminals |

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.

- **Phase 1 — Backend read layer.** `ThreadingHTTPServer` + TTL cache; shell `lazy-state.py` / `bug-state.py` across all queue items; parse JSON; attach `curated_stage`; read `queue.json` / `leases.json` / `ROADMAP.md`. Expose `/api/state`, `/api/queue`. (`leases.json` field names CONFIRMED against `lazy_coord.py` during /spec-phases — see Open Questions.)
- **Phase 2 — Static frontend + read-only render.** Three-pane shell; queues + fleet panes; headless→preset layout bootstrap; color/shape encoding; live dot + Connection-Lost guard.
- **Phase 3 — Unified two-track graph + traversal.** Token collection, per-node scaling (tokens/badge/swimlane), poll-diff animation with arc/fade for multi-stage jumps, side-state offset + pulse, node drill-down, Complete-state fade-and-drop.
- **Phase 4 — Queue drag-reorder write path.** POST reorder → temp + `os.replace` + retry; run-marker refusal with disabled-handle UX (banner, `not-allowed`, tooltip).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|---|---|---|---|
| Token on correct stage | Load graph vs a repo with known states | Token sits on the curated node matching the script's `current_step` | Compare UI to `lazy-state.py --feature-id <id>` JSON |
| Traversal animates | An item advances a stage during a poll window | Token animates to the next stage on the next poll; multi-stage jump arcs (no tween through skipped node) | Visual + backend poll log |
| Reorder persists (idle) | Drag a queue row when no run-marker | `queue.json` array order updated atomically; `/lazy` picks new order | Read queue.json; re-run state script |
| Reorder refused (run active) | Attempt reorder with run-marker present | Handles disabled + banner; `queue.json` unchanged | Run-marker present; queue.json byte-identical |
| Write survives AV lock | Reorder while Defender scans | Write succeeds within ≤3 retries; no lost reorder | Backend retry log |
| Backend stays responsive | Poll during a slow git probe | Static assets + `/api/queue` still serve concurrently | Concurrent request timing |
| Cache debounces probe | UI polls every 2.5s | Heavy probe runs ≤ once / 2.0s | Probe invocation count |
| Complete item bounded | Item reaches Complete + gets receipt | Token fades ~10s then drops; appears in collapsed log | Visual + COMPLETED.md present |
| Fleet reflects leases | A worker leases a slot (concurrency plane active) | Slot card shows branch + item + fresh heartbeat | Compare to leases.json |

## Open Questions
- ~~Exact `leases.json` field names~~ — **RESOLVED during /spec-phases (2026-06-15):** confirmed exact against `lazy_coord.py`. Each lease entry keyed by `wi_id` is `{worker_pid: int, worktree_slot: str, term_token: int, heartbeat_timestamp: "<ISO-8601 UTC 'Z'>", ttl_seconds: int}`; heartbeat freshness = `heartbeat_epoch + ttl_seconds >= now`. The estimate was correct. The `p/<id>-<slug>` branch on Fleet cards is derived from the leased item (not stored in `leases.json`). See PHASES.md Cross-feature Integration Notes.
- Whether `/lazy-status` / `/lazy-bug-status` text dashboards link to this UI (assume coexist for v1).
- Multi-repo switcher (v2), filesystem-watch liveness (v2), intent-log concurrency upgrade (v2).

## Research References
- `RESEARCH.md` Part 1 — Gemini Deep Research (authoritative): headless→preset layout, flat tokens-not-compound-nodes, per-node scaling, `ThreadingHTTPServer` + TTL cache, polling-over-SSE, intent-log vs `os.replace`, three-pane IA, unified two-track graph, colorblind shape encoding, anti-patterns.
- `RESEARCH.md` Part 2 — Gemini Pro (corroborating): triage bar, live dot, 2.5s/2.0s sweet spot, AV-lock retry detail.
- `RESEARCH_SUMMARY.md` — reconciliation + the three operator decisions (graph topology, concurrency model, complete-state handling) resolved into Decisions 10/11/13.
