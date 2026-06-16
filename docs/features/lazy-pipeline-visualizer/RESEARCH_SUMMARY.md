# Research Summary — Lazy Pipeline Visualizer

Sources: `RESEARCH.md` Part 1 (Gemini **Deep Research**, authoritative) + Part 2 (Gemini Pro, corroborating). Both ingested 2026-06-15.

## Bottom line

Deep Research **confirms the entire locked stack** (local web app, stdlib `http.server`, Cytoscape.js, interval polling, single repo, drag-reorder) and supplies a precise implementation playbook. It **overturns one locked product decision** (separate feature/bug graphs → it argues for a *unified two-track* graph) and **sharpens the concurrency choice** (run-marker refusal alone is insufficient on Windows; it recommends an *intent log*). Three product-behavior decisions are routed to the operator below; everything else is baked into the SPEC.

## Findings adopted into the SPEC (mechanical / research-confirmed — no decision)

**Graph rendering**
1. **Headless→preset layout decoupling.** On load, run `dagre` `rankDir:'LR'` in a *headless* Cytoscape, extract settled `(x,y)`, then render the live canvas with the `preset` layout (immutable positions). Never run a layout on poll. Never use `cola`/`cose`/`elk` continuous physics.
2. **Stages and tokens are flat peers — NOT compound nodes.** Stage nodes use static preset coords; tokens are smaller, higher `z-index`, manually positioned in a micro-grid around their current stage. (Compound nodes cause fatal jitter.)
3. **Token animation** = `token.animate({position:{x,y}, duration:400, easing:'ease-in-out-cubic'})` onto target stage coord + offset. For multi-stage jumps, **arc/fade** instead of tweening through skipped nodes (no false-intermediate-state implication).
4. **Per-node representation scaling:** 1–5 = animated tokens (circle=feature, square=bug); 6–20 = count badge (click → popover list); 20+ = collapse that node to a sortable swimlane/table. Applied per-node, not globally.
5. **Poll diffing:** `cy.add()` new IDs, `cy.remove()` gone IDs, `animate()` IDs whose stage changed. Never clear+redraw. Keeps 60fps for hundreds of tokens.
6. **Side-states** (Blocked / Needs-Input / Deferred) branch off the main track on a parallel Y-axis; token "ejects" out of the flow; settled node border-pulses.

**Backend**
7. **`ThreadingHTTPServer`** (not `HTTPServer`) — subclass `SimpleHTTPRequestHandler`, handle API routes, defer static assets to super.
8. **Server-side read-through TTL cache** with double-checked locking (`threading.Lock`) over the git-shelling probe. **UI poll 2.5s / server TTL 2.0s** (inside the research's 2–3s band). This is the load-bearing perf fix.
9. **Interval polling, not SSE** (SSE → zombie threads / `WinError 10054` / leaks on the stdlib server).

**Information architecture**
10. **Three-pane layout:** Graph = top/hero full-width; Queues = bottom-left (two parallel vertical lists); Fleet = bottom-right (grid of worktree-slot cards). Fleet cards badge the leased item's ID + shape/color + heartbeat (bridge physical↔abstract).
11. **Redundant color+shape encoding** (colorblind-safe): Pending gray/hollow; Running blue/▶; Complete green/✓ (fade to 50% after 10s); Needs-Input orange/**hexagon**; Blocked red/**octagon**; Deferred purple/dashed-ghost. Intervention states break the circle/square geometry on purpose.
12. **"Connection Lost" guard + live dot:** a poll fail/timeout dims the screen + banner; a footer dot tied to 200-OKs flips red instantly. (Never present stale data as live.)
13. **Atomic write + AV-lock retry:** any `os.replace` wrapped in 3× / 50ms retry catching `PermissionError [WinError 5]/[WinError 32]` (Windows Defender file locks).

## Decisions routed to the operator (product-behavior — picker follows)

1. **Feature/bug graph topology — OVERTURNS locked Decision 5.** Deep Research argues a **unified two-track graph** (Features = top track of circles, Bugs = bottom track of squares, sharing one canvas) beats separate/switchable graphs because tab-switching causes "change blindness" and hides shared-fleet allocation. The Pro synthesis (and our locked D5) said separate/switchable. → operator decides.
2. **Concurrency model for reorder.** Run-marker refusal alone leaves a Windows TOCTOU + AV-lock gap. Options span self-contained (refuse + retry) → coordinated (shared advisory lock) → **intent-log** (research's "most structurally sound", but requires the orchestrator to drain intent files on wake — a cross-system change to `lazy-state.py`/`lazy-batch`). → operator decides.
3. **Complete-state handling.** Research suggests fade-to-50%-after-10s but doesn't bound unbounded history growth on the single Complete node. → operator decides how completed items leave the graph.

## What changed vs the baseline
- **Decision 5 is now contested** (unified vs separate) — re-surfaced as operator Decision 1 above.
- **Decision 6 (refuse-during-run)** is preserved as a *floor* but research says it's insufficient alone — re-surfaced as operator Decision 2 (what to add on top).
- All other locked decisions stand, now with concrete implementation detail.
