# Manual Testing — Lazy Pipeline Visualizer (Phase 2)

> Behavior-focused browser smoke checklist for the read-only three-pane frontend.
> claude-config has no headless-browser harness, so the UI behaviors below are
> verified by a human in a real browser. The static-asset serving slice is the
> automated counterpart (`test_pipeline_visualizer.py::TestStaticServing`).

## Setup

1. Boot the server. The package lives under `user/scripts/`, so either run from
   that directory or put it on `PYTHONPATH`:
   ```powershell
   # Option A — from the scripts dir:
   cd C:\Users\Jacob\source\repos\claude-config\user\scripts
   python -m pipeline_visualizer --repo-root C:\Users\Jacob\source\repos\claude-config --port 8765

   # Option B — from anywhere, via PYTHONPATH:
   $env:PYTHONPATH = "C:\Users\Jacob\source\repos\claude-config\user\scripts"
   python -m pipeline_visualizer --repo-root C:\Users\Jacob\source\repos\claude-config --port 8765
   ```
   It prints `Lazy Pipeline Visualizer serving at http://127.0.0.1:8765/`.
2. Open `http://127.0.0.1:8765/` in a browser.

## Checklist

### Layout / structure
- [ ] **Three panes render.** A full-width hero **graph** region across the top;
      a **Queues** pane bottom-left; a **Fleet** pane bottom-right. No pane
      overlaps; the page fills the viewport.
- [ ] **Triage strip present.** An "Action Required" bar is visible (empty state
      shows a quiet "nothing requires action" message, not a broken/blank box).
- [ ] **Footer live dot present.** A small status dot + label sits in the footer.

### Graph (read-only — no animation in Phase 2)
- [ ] **Two tracks.** The graph shows a Features track (top) and a Bugs track
      (bottom), each opening with a **Pending** entry node, then Spec → (Research,
      features only) → Plan → Implement → Validate → Complete left-to-right.
- [ ] **Stable layout, no jitter.** Reload the page a few times — node positions
      are identical every time (headless dagre → `preset`, immutable coords). The
      graph never re-flows or drifts while the poll loop runs.
- [ ] **Token on correct stage.** Each queue item appears as a token (circle =
      feature, square = bug) sitting on the curated stage node. Cross-check one
      item against the script:
      ```
      python user/scripts/lazy-state.py --repo-root . --feature-id <id>
      ```
      The token's stage must match the `current_step` rollup (e.g. `Step 7a:
      execute plan` → the token sits on **Implement**).
- [ ] **Queued-but-unstarted on Pending.** An item with no `/spec` yet (null
      `current_step`) renders on the **Pending** entry node, gray/hollow — not
      collapsed onto Spec.

### Color & shape encoding (colorblind-safe — color AND shape both encode)
- [ ] Pending = gray `#888888`, hollow outline.
- [ ] Running = blue `#0074D9`, solid, ▶ marker.
- [ ] Complete = green `#2ECC40`, ✓ marker.
- [ ] Needs-Input = orange `#FF851B`, **hexagon**.
- [ ] Blocked = red `#FF4136`, **octagon**.
- [ ] Deferred = purple `#B10DC9`, dashed/ghosted outline.

### Queues pane
- [ ] Two vertical lists: **Features** and **Bugs**, in `queue.json` order.
- [ ] Each row shows the item ID + badges for tier / ad-hoc / stub when present.
- [ ] (Drag-to-reorder is **Phase 4** — rows are static here; no drag handles
      need to work yet.)

### Fleet pane
- [ ] One card per `wt-NN` worktree slot from `leases[]`. Each card shows the
      leased item ID + the item's shape/color + derived branch `p/<id>-<slug>` +
      heartbeat freshness (fresh/stale) + worker pid.
- [ ] **Empty state.** Under single-threaded `/lazy-batch` (no leases),
      the pane shows an explicit "no active workers" message — not a blank box.

### Triage strip
- [ ] Every item whose `curated_stage` is **Blocked**, **Needs-input**, or
      **Deferred** is listed in the Action-Required bar (mirrors the graph
      side-states so a stalled fleet is never hunted for).

### Liveness — the load-bearing honesty guarantee
- [ ] **Live dot green while polling.** With the server running, the dot is green
      and the data refreshes ~every 2.5s.
- [ ] **Connection-Lost guard fires on kill.** Stop the server (Ctrl-C). Within
      **≤1 poll interval (2.5s)** the dot flips **red**, the screen **dims**, and
      a **"Connection Lost"** banner appears. The last data is visibly dimmed —
      never presented as live.
- [ ] **Recovery.** Restart the server; on the next successful poll the dot
      returns green, the dim/banner clear, and data resumes.
