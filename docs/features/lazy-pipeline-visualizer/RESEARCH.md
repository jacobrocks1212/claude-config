# Research — Lazy Pipeline Visualizer

This feature has two research artifacts. **Part 1 is authoritative** (the full Gemini Deep Research report). **Part 2** is an earlier Gemini Pro synthesis (Deep Research was briefly down) — retained because it corroborates Part 1 and is occasionally more concise. Where they diverge, Part 1 wins; the divergences are called out in `RESEARCH_SUMMARY.md`.

---

# Part 1 — Deep Research report (authoritative)

> Source: Gemini Deep Research, "Architecture and Visualization Patterns for Autonomous Pipeline Control Planes". Uploaded 2026-06-15.

## Executive Summary

Visualizing items traversing a deterministic, fixed-stage DAG requires mitigating layout thrashing, cognitive overload, and backend thread blocking. High-impact patterns: **(1)** dynamic graph layouts (force-directed / generic layered) fail in live-polling environments due to positional jumping — instead compute a static left-to-right DAG layout once via a *headless* instance, then render live with a `preset` layout, animating token representations across fixed stage nodes. **(2)** "N items on a stage" needs multimodal scaling: animated tokens up to ~5, then clustered count badges, then tabular swimlanes for high-density bottlenecks. **(3)** Python's single-threaded `http.server` default guarantees UI freezing when polling invokes heavy git subprocesses — `ThreadingHTTPServer` + a server-side read-through TTL cache (2–3s) is mandatory. SSE's hanging-thread/connection-drop fragility on the stdlib server favors cached interval polling. **(4)** Concurrent file writes on Windows via `os.replace` are unsafe (antivirus file locking) — a deterministic **intent-log** pattern safely arbitrates UI-driven reordering against the orchestrator's writes.

## Prior Art: Pipeline, DAG, and Queue Visualizers

Critical distinction: most mature tools solve for *authoring* a DAG or tracking a *single isolated run*, not watching *multiple independent items flow through a static state machine simultaneously*.

| Tool Category | Examples | Visual Paradigm | Tradeoff for multi-item queues |
|---|---|---|---|
| CI/CD Pipelines | GitHub Actions, Jenkins Blue Ocean, GitLab CI | Left-to-right node graph; status by node color/icon | Optimized for single-run monitoring; can't represent multiple independent items on the same node — fails the core "N items on one stage" requirement |
| Workflow Orchestrators | Argo Workflows, Airflow, Temporal | Complex DAGs for dependency mapping, fan-out/fan-in | Nodes = compute tasks, not physical stages; high data density but overwhelming visual noise |
| Kanban / Queues | Linear, Trello, GitHub Projects | Vertical lists + fluid drag-reorder | Great for deep backlogs / 50+ items, but no topological / DAG / side-state relationships |
| Node-Graph Editors | Node-RED, n8n | Interactive authoring; tokens trace execution during debug | High interactivity but nodes are data-transformation maps, not state buckets |

Jenkins Blue Ocean standardizes the left-to-right pipeline aesthetic (hollow nodes fill with color on completion). Linear excels at high-density list management. The system must **hybridize**: a Kanban-style queue for intake/prioritization + a DAG for active execution state. The best paradigm for "one stage with N items" is **contextual scaling** — dynamically shift representation mode based on item volume to preserve glanceability.

## Items Traversing the Graph — the core challenge

### Representation Scaling (per-node, not global)

| Item Count | Strategy | Behavior / Rationale |
|---|---|---|
| 1–5 | **Animated tokens** | Discrete shapes (circles=features, squares=bugs) on/orbiting the node; track individual items; small ID badges or priority colors |
| 6–20 | **Count badges** | Tokens coalesce into one metric pill (e.g. "8 Features, 3 Bugs"); click to open a popover list |
| 20+ | **Swimlane / table** | Graphical DAG minimized in favor of a dense, sortable table grouped by stage; at extreme volume graphs fail and you need database-style filter/sort |

Transition is **calculated per-node**: a healthy 2-item Implement stage shows tokens while a 12-item Blocked side-state collapses to a badge. Active path stays visible; bottlenecks don't overrun the canvas.

### Stable Layouts and State-Transition Animation

Anti-pattern: **layout thrashing** (algorithm re-evaluates node positions on new data → graph shifts/vibrates). For a polling UI node positions must be immutable. Use `dagre` (cytoscape-dagre) with `rankDir: 'LR'` for the assembly-line look — but **not on every poll** (floating-point/bounding-box drift). Optimal: a **decoupled two-phase headless-to-live pipeline**:
1. On load, instantiate a *headless* Cytoscape (`headless: true, styleEnabled: false`), run `dagre` `rankDir:'LR'` over the fixed state-machine definition.
2. Extract the settled absolute `(x,y)` of every stage node.
3. Initialize the live visible instance with the `preset` layout, passing those coordinates. `preset` accepts explicit positions and prevents autonomous movement.

On a state transition, the **token** (a discrete node, separate from stage nodes) animates: detect target-stage change in the poll diff, compute target node's absolute coord + a deterministic offset (prevent overlap), call `TokenA.animate({ position:{x,y}, duration:400, easing:'ease-in-out-cubic' })`. The discrete jump between fixed coords reads as fluid motion without implying false intermediate stages.

### "Blocked" / "Needs-Input" side-states

Render as nodes **branched off the main flow** on a parallel Y-axis (above/below the critical path). On entering a side-state, the token's animation drops/shoots out of the main flow (ejection from the assembly line). Once settled, a subtle CSS **border pulse** draws peripheral vision. For colorblind safety use **redundant** high-contrast patterns (thick dashed stroke) and distinct **shapes** (triangle/octagon) alongside red/orange.

## Cytoscape.js Specifics

Reference standalone UMD/ES build via `<script>` (no bundler) — stable for long-lived internal tools. Performance ceiling is high (thousands of static elements), but iterative `animate()` on poll intervals degrades if the DOM is bogged by complex labels or **compound-node** constraint math.

### Avoid compound nodes for dynamic tokens

Modeling stages as compound (parent) nodes with work-items as children is a fatal temptation: grid layouts on children fail / parent bounding boxes resize unpredictably during animation; the physics engine recomputing compound bounds causes jitter and breaks the stable LR structure. **Strict recommendation: stages and tokens are flat peers.** Stage nodes use static `preset` coords; token nodes are smaller, higher `z-index`, positioned manually relative to their current stage. E.g. Implement fixed at (100,200) with three tokens → micro-grid: animate to (90,190),(110,190),(100,210). Stage stays immutable.

### Diffing & DOM performance

Never clear+redraw the canvas each poll (destroys context + animation). Diff: iterate incoming JSON — ID in JSON but not in cy → `cy.add()`; ID in cy but not JSON → `cy.remove()`; ID in both → compare target stage, and if changed trigger `animate()` to the new micro-coordinates. Updating only the delta keeps Cytoscape at 60fps for hundreds of tokens.

## Backend Architecture with Python http.server

### Threading imperative
Default `HTTPServer` is single-threaded/serial. A poll that shells to git can take hundreds of ms–seconds; a second request (CSS fetch, drag-reorder) stalls until it finishes. **`ThreadingHTTPServer` (3.7+) or `ThreadingMixIn` is non-negotiable.** Subclass `SimpleHTTPRequestHandler` to handle API routes and defer to the superclass for static assets.

### Caching the state probe
Threading alone isn't enough — multiple concurrent threads shelling `git status` thrash disk IO/CPU on Windows. Use a **server-side read-through TTL cache** as a debounce: class-level dict storing last-computed state + high-res timestamp. On `/api/state`, if `now - ts < TTL` return cached JSON; if stale, acquire a `threading.Lock()`, **double-check** staleness, run the heavy probe, update cache+timestamp, release, return. **TTL 2–3s** is the sweet spot: even at 500ms UI polling the heavy probe runs only every few seconds.

### SSE vs interval polling
SSE needs an indefinitely-alive connection (`yield "data: ...\n\n"` loop) and a permanent thread per tab; on refresh/close/sleep, Windows sockets often fail to signal clean termination → zombie threads, `[WinError 10054]`, memory leaks, thread-pool exhaustion over a long session. For a single-user stdlib tool **plain interval polling wins**: stateless, immune to zombie leaks, composes with TTL caching. The 0ms-vs-2000ms latency difference is imperceptible for async CI/file monitoring.

## Safe Concurrent File Writes on Windows

### The illusion of os.replace on Windows
On POSIX, `os.replace(tmp,target)` is atomic. On Windows it's "fundamentally flawed and actively dangerous": when a new file is written and `os.replace` called, AV engines (Defender/CrowdStrike) intercept the handle to scan, **locking the file**; Python's call is rejected with `PermissionError [WinError 5]` / `[WinError 32]`. Atomic JSON rewrite from the UI endpoint will sporadically fail → lost reorders. Retry-with-backoff partially mitigates but blocks the HTTP thread and offers no guarantee.

### The Intent Log architecture (recommended)
The run-marker refusal prevents *logical* races but not the AV read/write lock if the orchestrator wakes at the exact ms the UI writes. Most provably-safe model for a UI editing a file an autonomous process owns: **Intent Log / event sourcing**.
1. On drag-reorder the UI POSTs to the backend.
2. Backend writes an **append-only** `.reorder_intent_<timestamp>.json` (desired array or transposition op). Uniquely-named new file → no overwrite conflict.
3. The orchestrator, on its next wake (**before** doing pipeline work), consumes all `.reorder_intent_*` in timestamp order.
4. Orchestrator applies intents to the master queue in memory, deletes the intent files, writes authoritative `queue.json`.

UI can optimistically update local DOM while waiting for the next poll to confirm. Simpler variant: UI verifies no run-marker, takes an OS advisory lock (`msvcrt.locking` / cross-platform `filelock`), does a safe read-modify-write with retry, releases. **Intent Log remains the most structurally sound.**

### Communicating refusal gracefully
When the run-marker exists, instantly disable drag-reorder: cursor → `not-allowed` on handles; global banner/badge "Queue Locked: Autonomous Orchestrator is executing Stage X". **Do not hide** the handles (users assume the app is broken when interactive elements vanish) — keep them visible but low-opacity with a descriptive tooltip.

## Information Architecture & At-A-Glance Design

The **glance test**: process global state in <3s without scrolling/clicking/switching.

### Three-pane layout
1. **Top / hero — Pipeline Graph** (full width): primary telemetry, systemic health + throughput.
2. **Bottom-left — Queues**: two parallel vertical Kanban lists (Features, Bugs); backlog/intake funnel.
3. **Bottom-right — Fleet**: dense grid of small telemetry cards = git worktree slots (wt-00…), granular execution status.

### Parallel pipelines + shared fleet — UNIFIED graph
For two pipelines sharing one worktree pool, a **unified graph is vastly superior to a tabbed interface**: tabbing creates "change blindness", forcing the operator to hold state in short-term memory and losing track of global resource allocation. Render **two parallel horizontal tracks**: top = Feature pipeline (Spec → Research → Plan → Implement → Validate → Complete), nodes = circles; bottom = Bug pipeline (Reproduce → Plan → Implement → Validate → Complete), nodes = squares. Fleet worktree cards **bridge physical↔abstract**: each card badges itself with the leased item's ID + shape/color (e.g. wt-03 shows a blue circle "FEAT-14" + flashing green "PID 1049" heartbeat).

### Color & shape encoding (redundant — colorblind safe)

| State | Color (CB-safe) | Shape / Icon | Treatment |
|---|---|---|---|
| Pending / Queue | Neutral Gray `#888888` | Hollow outline (matches pipeline type) | Static thin border |
| Running | Blue `#0074D9` | Solid fill + "play" triangle | Pulsing heartbeat on Fleet card |
| Done / Complete | Green `#2ECC40` | Checkmark | **Fades to 50% opacity after 10s** to reduce noise |
| Needs-Input | Orange `#FF851B` | **Hexagon** | High-frequency pulse, bold border, pushed to top of backlog |
| Blocked | Red `#FF4136` | **Octagon (stop sign)** | Thick dashed border, alert icon, offset from main DAG |
| Deferred | Purple `#B10DC9` | Dashed outline | Ghosted / 40% opacity |

Breaking the geometric pattern (hexagon/octagon vs circle/square) for intervention states accelerates anomaly detection — multiple visual dimensions change at once.

## Pitfalls & Anti-Patterns Checklist
- **Stale data presented as live** — on poll fail/timeout/error, dim the screen + "Connection Lost" banner. Never leave stale tokens looking active.
- **False interpolation in animation** — tweening A→C must not physically cross B if logically bypassed; arc over the graph (Bezier) to avoid implying false intermediate states.
- **Overloading the poller** — fast poll (500ms) + uncached git-shelling backend = localized DoS (subprocess storm, disk thrash). Strict server-side TTL caching is non-negotiable.
- **Continuous layout thrashing** — `cola`/`cose`/`elk` physics layouts on a polling dashboard vibrate/reorganize every refresh. Pre-compute via headless DAG layout; production canvas uses immutable `preset`.
- **Direct file mutation on Windows** — `open('w')`/`os.replace` are not concurrency-safe (async AV locks). Use Intent Logs, or robust retry-loops explicitly catching `[WinError 5]`/`[WinError 32]`.
- **Single-threaded default Python server** — `HTTPServer` without threading hangs the whole UI on one slow request. `ThreadingHTTPServer` required.

## Works cited
(32 sources — Cytoscape dagre/preset layout docs & discussions, compound-node layout issues, Python `http.server` threading, SSE tutorials, Windows `os.replace`/`[WinError 5]` AV-lock bug reports, `msvcrt`/`filelock` advisory locking. Full list in the uploaded source file.)

---

# Part 2 — Gemini Pro corroborating synthesis (secondary)

> Source: Gemini Pro (used while Deep Research was down). Confirms Part 1 on the stack, layout decoupling, threading, TTL cache, and polling. Diverges from Part 1 on two points (see RESEARCH_SUMMARY.md): it recommended *separate/switchable* feature-vs-bug graphs (Part 1 recommends a unified two-track graph) and *optimistic concurrency* version+409 (Part 1 recommends an intent log).

Highlights unique to or sharper in the Pro synthesis:
- **Token→count thresholds** phrased as 1–4 tokens / 5–19 badge / 20+ warning badge (Part 1: 1–5 / 6–20 / 20+ swimlane). Part 1's three-tier (tokens→badge→table) is the more complete model.
- **Triage Bar:** a persistent horizontal "Action Required" bar above queue+graph mirroring every side-state item so a stalled fleet is never hunted for. (Complements Part 1's side-state salience.)
- **Live indicator:** a pulsating green "live" dot tied to 200-OK polls; flips red instantly on a failed/timed-out poll. (Same intent as Part 1's "Connection Lost" anti-pattern.)
- **Antivirus retry detail:** wrap `os.replace` in 3× / 50ms retry catching `PermissionError` (the simpler variant Part 1 also mentions, below the intent log).
- **Sweet spot numbers:** UI poll 2.5s, server TTL cache 2.0s (a concrete point inside Part 1's 2–3s range).
