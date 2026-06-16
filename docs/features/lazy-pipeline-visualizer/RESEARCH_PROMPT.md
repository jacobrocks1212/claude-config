# Research Question

I am building a **local, single-user web "control plane" for an autonomous software-development pipeline** — a tool that visualizes and lets me interact with a deterministic, file-driven work queue. I need deep research on the **best-practice UX, visualization, and architecture patterns** for this class of tool so I can finalize a feature spec. Focus on what actually works in production developer tools, with concrete examples and tradeoffs — not generic UI advice.

## Context

The pipeline being visualized ("the lazy pipeline") works like this:
- A **queue** of work items (two parallel queues: *features* and *bugs*) is stored as a JSON array. **Array order = processing order.**
- A deterministic Python script inspects files on disk (spec docs, plan docs, sentinel marker files with YAML frontmatter) and computes, for each item, its **current stage** in a fixed state machine. It emits machine-readable JSON. The UI is a pure **renderer** over this JSON — it does not re-implement state inference.
- The state machine has ~16 literal step-states + ~11 terminal states per pipeline, which I am **rolling up into ~7 curated stages**: Spec → Research → Plan → Implement → Validate → Complete, plus side-states Blocked / Needs-input / Deferred.
- An autonomous orchestrator can run the pipeline unattended, advancing items stage-by-stage. Work executes in a pool of **git worktrees** (slots `wt-00`, `wt-01`, …), each on a branch named `p/<id>-<slug>`, tracked by a `leases.json` (slot → item → branch → heartbeat → worker pid).

### Locked technical decisions (do NOT re-litigate these; research should refine *within* them)
- **Local web app**: Python **stdlib `http.server`** backend (no web framework), browser frontend, served as static files.
- **Graph rendering**: **Cytoscape.js**, no build step / no bundler.
- **Liveness**: **interval polling** (backend re-probes on a timer; frontend diffs + animates), not websockets/fs-watch for v1.
- **Interactivity**: drag-to-reorder the queue, which writes the queue JSON back to disk. Reorder is **refused while an autonomous run is active** (a run-marker file is present) to avoid two concurrent writers to one file.
- **Single repo** per server instance (`--repo-root`).
- Platform is **Windows** (PowerShell environment); robustness on Windows matters.

## Three views the UI must deliver
1. **Queues** — ordered lists (feature + bug), drag-to-reorder, badges (priority/tier, ad-hoc, stub).
2. **Fleet** — one card per worktree slot: branch, leased item, heartbeat freshness, worker pid, and the item's current stage.
3. **Pipeline graph** — a directed graph; **stage = node, outcome = edge** (success / blocked / needs-input / deferred); each queue item is a **token placed on its current node**; tokens **animate to new nodes** as items progress ("watch features traverse the pipeline").

## Research Areas

### 1. Prior art — pipeline / DAG / queue visualizers
Survey how mature tools visualize a fixed-stage pipeline with many items flowing through it, and what I should steal or avoid:
- **CI/CD & workflow tools**: GitHub Actions, GitLab pipelines, Jenkins Blue Ocean, CircleCI, Argo Workflows / Argo CD, Tekton, Temporal Web UI, Apache Airflow / Dagster / Prefect (DAG + run views), n8n / Node-RED (node-graph editors).
- **Kanban / queue tools**: Linear, Trello, GitHub Projects — how they handle drag-reorder, WIP, and large lists.
- For each relevant example: how do they represent **one stage with N items on it**? Swimlanes? Counts/badges on a node? A particle/token animation? A table-per-stage? Which scales and which collapses visually?

### 2. "Items traversing a graph" — the core visualization challenge
This is the hardest UX problem. Research concrete techniques and their tradeoffs:
- **Token-on-node vs. count-on-node vs. swimlane-row-per-item.** When do animated tokens help comprehension vs. become noise (e.g. with 5 items vs. 50)?
- Best practices for **animating a state transition** on a poll interval (typical poll cadence for live dev dashboards; how to animate a discrete jump so it reads as motion without implying false intermediate states).
- How to show items **stuck** in a side-state (Blocked / Needs-input) so they're visually salient without dominating.
- Layout algorithms for a mostly-linear pipeline with side-branches — Cytoscape.js layout options (`dagre`, `breadthfirst`, `elk`, manual preset). Which gives a stable, left-to-right "assembly line" feel where node positions don't jump between polls?
- Graph **stability across re-renders**: techniques to keep node positions fixed while only tokens move (critical for a polling UI).

### 3. Cytoscape.js specifics
- Patterns for **compound/parent nodes** or node badges to show "N items at this stage" and drill-down on click.
- Recommended approach for **animating an element (token) moving from node A to node B** in Cytoscape (`animate()`, position tweening) on each poll diff.
- Performance ceiling: how many nodes + edges + token elements before Cytoscape gets sluggish in a browser; when to switch to counts instead of individual tokens.
- Preset/fixed layout vs. re-running layout each update — how to avoid layout thrash.

### 4. Backend architecture with stdlib `http.server`
- Idiomatic patterns for a **read-mostly local JSON API + static file server** on Python's `http.server` / `socketserver` (threading mixin, routing without a framework, serving an SPA-ish static bundle). Known pitfalls (blocking handler, single-threaded default, Windows socket quirks).
- Whether **polling that shells out to a subprocess** (the state script) per request is acceptable, or whether to add a short-lived **server-side cache** with a TTL to avoid hammering git on every poll. Recommended cache/debounce pattern for "expensive probe behind a polling UI."
- **Server-Sent Events (SSE)** as a middle ground between naive polling and websockets on stdlib `http.server` — is it worth it, or does plain interval polling win for a single-user local tool? Tradeoffs.

### 5. Safe concurrent file writes (queue reorder vs. autonomous orchestrator)
- Best practice for **atomic JSON rewrite on Windows** (temp file + `os.replace`), and the gotchas (Windows rename-over-existing semantics, antivirus/file-lock interference).
- Beyond "refuse while a run-marker exists": what's the **robust pattern for a UI editing a file an autonomous process also owns** — advisory lockfiles, mtime/hash optimistic-concurrency checks, append-only intent logs? What do real tools do here, and what's the simplest model that's actually safe?
- How to make the "reorder refused during a run" state **clear and non-frustrating** in the UI (precedent from tools that disable editing during a running job).

### 6. Information architecture & at-a-glance design
- For a single-user **operator dashboard** (one person watching an autonomous system they own), what's the right default density and the right "glance test" — what must be visible without interaction?
- Conventions for **status color/shape encoding** (running / blocked / needs-human / done / deferred) that are colorblind-safe and unambiguous.
- Patterns for surfacing **"needs my input" / blocked** items urgently (the human is the bottleneck the autonomous system waits on) — notification, sorting, visual priority.
- How comparable tools handle **two parallel pipelines** (here: features and bugs) — toggle/tabs vs. unified — and a **shared resource pool** (the worktree fleet) that serves both.

### 7. Pitfalls & anti-patterns
- Common failure modes of homegrown pipeline dashboards (stale data presented as live, animation that misleads, layout thrash, polling that melts the backend).
- Accessibility and "boring tech" considerations for a tool meant to last and be low-maintenance (no-build-step longevity, dependency rot in vendored JS libs).

## Specific Questions
1. For "N items on one stage," what representation scales best from 1 to ~50 items — animated tokens, a count badge with click-to-expand, or a swimlane table — and at what item count should the UI switch modes?
2. What Cytoscape.js layout + configuration gives a **stable, left-to-right pipeline** where node positions never jump between polls, and how do I animate a token from node A→B on a diff?
3. What poll interval is the sweet spot for a "live but cheap" local dev dashboard, and should I cache the (expensive, git-shelling) state probe server-side behind a TTL?
4. Is SSE meaningfully better than plain interval polling for a **single-user local** tool, given a stdlib `http.server` backend, or is the added complexity unjustified?
5. What is the simplest **provably-safe** model for the UI to reorder a queue file that an autonomous orchestrator also writes — and where does "refuse during active run + atomic replace" fall short?
6. What are the best real-world examples of visualizing **work items flowing through a fixed-stage pipeline** (not authoring a DAG, but watching instances traverse one), and what specifically do they do well?
7. For an operator who is the human-in-the-loop bottleneck, how should **Blocked / Needs-input** items be surfaced to minimize the time they sit unnoticed?
8. Any well-known **anti-patterns** in polling dashboards or graph-animation that I should explicitly design against?

## Output Format Request
Return structured findings:
- A short **executive summary** of the 3–5 highest-impact recommendations.
- One section per Research Area above, each with **concrete examples** (named tools, with what they do well/badly) and **actionable recommendations** scoped to my locked stack (stdlib `http.server` + Cytoscape.js + polling + Windows).
- A dedicated **"items traversing the graph"** deep-dive (this is the make-or-break view) with specific Cytoscape.js technique recommendations.
- A **pitfalls / anti-patterns** checklist I can design against.
- Where research contradicts one of my locked decisions, say so explicitly and explain the tradeoff — but assume I'm keeping the locked stack unless the case is overwhelming.
