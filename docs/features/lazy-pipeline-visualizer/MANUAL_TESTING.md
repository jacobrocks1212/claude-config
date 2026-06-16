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

---

# Manual Testing — Phase 3 (unified two-track graph + traversal animation)

> Phase 3 upgrades the static render into the live two-track graph with poll-diff
> animation, per-node scaling, side-state ejection, drill-down, and Complete
> fade-and-drop (Decisions 10 + 13). The backend `receipt_present` slice is
> automated (`TestReceiptPresent`); the graph behaviors below are manual.

## Setup (fixture with multiple stages)

Seed a temp repo whose items span several curated stages so the graph has
something to animate. Easiest path: copy this repo's `docs/features/queue.json`
(or hand-author one) with 2–3 features at different `current_step`s, plus a
`docs/bugs/queue.json` with a bug or two, then boot as in the Phase 2 setup and
open the page. To exercise an advance, hand-edit a fixture sentinel / SPEC status
between polls and watch the next poll animate the token.

## Checklist

### Unified two-track graph (Decision 10)
- [ ] **One shared canvas, two tracks.** Feature tokens (circles) ride the **top**
      track; bug tokens (squares) ride the **bottom** track; stage columns are
      vertically aligned so a shared-fleet contention reads at a glance.
- [ ] **No clear+redraw.** Watch the graph across several polls with the data
      unchanged — tokens do NOT flicker/disappear-and-reappear each poll (the
      poll path is a `cy.add`/`cy.remove`/`animate` diff, never a full redraw).

### Traversal animation
- [ ] **Single-stage advance tweens.** Advance one item by one curated stage
      (edit a fixture). On the next poll its token **animates** (~400ms,
      ease-in-out-cubic) to the next stage's coordinate — it does not teleport.
- [ ] **Multi-stage jump arcs/fades.** Advance an item by 2+ curated stages at
      once. The token **arcs (or fades out/in)** to the destination rather than
      sliding through the skipped node(s) — no false "it was here" implication.

### Per-node representation scaling
- [ ] **1–5 items = individual tokens.** A stage holding ≤5 items shows each as a
      separate token in a micro-grid.
- [ ] **6–20 items = count badge.** A stage holding 6–20 items collapses to a
      single **count badge**; clicking it opens a **popover** listing the items.
- [ ] **20+ items = swimlane.** A stage holding 20+ items collapses to a sortable
      swimlane/table (or, at minimum, a clearly distinct high-count treatment).

### Side-state ejection
- [ ] **Off-track ejection.** A Blocked / Needs-input / Deferred token visibly
      **ejects** onto a parallel Y-axis off the main track (not sitting inline).
- [ ] **Shapes hold.** Needs-input = hexagon, Blocked = octagon, Deferred =
      dashed/ghosted — same encoding as Phase 2.
- [ ] **Settled-node border-pulse.** The stage node the ejected token came from
      **border-pulses** so the eye is drawn to the stall.

### Drill-down
- [ ] **Click a curated node → panel.** Clicking any curated stage node opens a
      panel listing the literal `current_step` / `terminal_reason` value(s) the
      items on that node roll up (the full machine behind the curated rollup).
- [ ] **Dismiss.** Clicking elsewhere / a close affordance dismisses the panel.

### Complete fade-and-drop (Decision 13)
- [ ] **Fade ~10s after Complete.** A token reaching **Complete** stays full
      opacity briefly, then fades to ~50% about 10s later.
- [ ] **Drop once receipted.** Once the item's `COMPLETED.md` / `FIXED.md`
      receipt exists (`receipt_present:true` from the backend), the faded token
      **drops off** the graph on the next poll.
- [ ] **Collapsed completion log.** Older completions are not lost — the Complete
      node carries an expandable count/log of recently-dropped items.

---

# Manual Testing — Phase 4 (queue drag-reorder write path)

> Phase 4 makes the Queues pane rows drag-reorderable, writing `queue.json` back
> via `POST /api/queue` (atomic + AV-lock retry), refused entirely while a batch
> run-marker is present, with disabled-handle UX. The write path itself is fully
> automated (`TestQueueWriter*`, `TestPostQueueRoute`); the drag UX + locked
> visuals below are manual. Decisions 6 + 11.

## Setup

Boot as in the Phase 2 setup against a repo with ≥2 features (and/or ≥2 bugs) in
`queue.json` so there is something to reorder. To exercise the locked state,
start a `/lazy-batch` run (or hand-write `~/.claude/state/lazy-run-marker.json`,
or set `LAZY_STATE_DIR` to a temp dir and drop a marker there) so the server's
run-marker detection trips.

## Checklist

### Drag-reorder (idle — no run-marker)
- [ ] **Rows are draggable.** Each Queues row (Features and Bugs) shows a drag
      handle / grab cursor; you can pick a row up and drop it in a new position.
- [ ] **Drop persists.** After a drop, the new order is written: re-run
      `python user/scripts/lazy-state.py --repo-root .` (or reload the page) and
      the front-of-queue reflects the new order. `queue.json` on disk shows the
      reordered array (indent=2, trailing newline intact).
- [ ] **Optimistic + reconciled.** The row visibly moves immediately on drop
      (optimistic); the next poll (≤2.5s) reconciles against the server's order
      — no flicker-back-then-forward if the write succeeded.
- [ ] **Features and Bugs are independent.** Reordering Features does not disturb
      the Bugs list and vice-versa (separate `pipeline` in the POST).

### Locked state (run-marker present)
- [ ] **Banner shows.** A "Queue Locked: orchestrator executing" banner appears
      over/above the Queues pane while the run-marker is present.
- [ ] **Handles disabled, never hidden.** Drag handles remain visible but are
      visibly disabled — cursor is `not-allowed` over a row; attempting to drag
      does nothing (no POST is sent). The rows are NOT removed/hidden.
- [ ] **Tooltip explains why.** Hovering a disabled row shows a tooltip
      explaining the queue is locked because the orchestrator is running.
- [ ] **409 is not destructive.** If a drag somehow fires while locked, the
      server returns 409 and `queue.json` is byte-identical (no lost/changed
      order) — the UI snaps the row back on the next poll.

### Unlock recovery
- [ ] **Clears on run end.** Remove the run-marker (end the `/lazy-batch` run /
      delete the marker file). Within ≤1 poll the banner clears, handles
      re-enable (grab cursor returns), and drag-reorder works again.
