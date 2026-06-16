---
kind: needs-input
feature_id: lazy-pipeline-visualizer
written_by: lazy-batch-input-audit
decisions:
  - Where does a queued-but-unstarted item render on the graph — its own Pending/Queue node, or collapsed onto Spec?
date: 2026-06-15
next_skill: spec
audit_concurs: false
---

## Decision Context

The plan-feature cycle (PHASES.md + 3-part plan, commit `a84669c`) decomposed the
visualizer without surfacing any operator decisions — its return summary classified
every call as `mechanical-internal` or SPEC-locked, and listed "default-stage fallback"
among the auto-accepted mechanical decisions. The three genuine product-behavior calls
(graph topology, concurrency model, complete-state handling) were correctly resolved by
the operator in the prior `/spec` rounds (SPEC Locked Decisions 10/11/13) and stand.

One decision the plan introduced, however, sits on a user-visible surface AND conflicts
with a SPEC-locked surface, so it is surfaced here rather than baked in silently.

### Where does a queued-but-unstarted item render on the graph?

- **Problem:** Plan part 1
  (`plans/all-phases-lazy-pipeline-visualizer-part-1.md`, the `curated_stage` test
  deliverable: *"Assert an unknown/`None` step falls back to a documented default
  (e.g. `Spec` for a queued-but-unstarted item) — pick the safe default and assert it."*)
  bakes in the rule **unknown/`None` `current_step` → curated node `Spec`**. But the
  SPEC's own **Color & shape encoding** table (`SPEC.md` line 69) defines a distinct
  **`Pending / Queue`** state (Gray `#888888`, hollow outline, static thin border) — a
  state with no corresponding entry in the **Curated-node rollup** table (`SPEC.md`
  lines 94–104, which only enumerates Spec → Complete + Blocked/Needs-input/Deferred).
  So the SPEC models a queued item as a *Pending/Queue* token, while the plan renders it
  on the *Spec* workflow node. These are different things the operator sees on first run:
  whether a freshly-enqueued feature that has not yet had `/spec` run appears as an
  inert gray "waiting in line" token or as an active token already sitting on the Spec
  stage. RESEARCH_SUMMARY finding #11 (colorblind encoding) carries the Pending/Queue
  treatment forward but does not place it on the stage graph — the gap is real.

- **Options:**
  - **Auto-accepted by cycle subagent: collapse Pending/Queue onto `Spec`.** Unknown/`None`
    step → the `Spec` curated node; the SPEC's Gray/hollow "Pending" treatment is applied
    as the token's *style* while it sits on Spec. Simplest (no new node, no layout change);
    but it visually conflates "queued, untouched" with "actively being spec'd," weakening the
    glance test for backlog depth and making a long queue look like a Spec-stage pile-up.
  - **Add a dedicated `Pending/Queue` entry node** at the head of each track (left of Spec),
    matching the SPEC encoding table's distinct state. Queued-but-unstarted tokens live there
    (Gray/hollow) and animate into Spec when `/spec` starts. Highest fidelity to the SPEC's
    own state model and the clearest backlog signal; costs one extra preset column + one
    rollup-table row (Pending ← unknown/`None`/queued-not-started literals) — a small,
    one-time layout addition, reversible.
  - **Render queued items only in the Queues pane, not on the graph at all** (graph shows
    only items with a real `current_step`; the Queues Kanban already lists the full backlog).
    Keeps the hero graph to in-flight work; but a brand-new repo with everything queued shows
    an empty graph, which reads as "nothing happening / broken" — weakest empty-state.

- **Recommendation:** **Add a dedicated `Pending/Queue` entry node** — it is the only option
  that honors the SPEC's already-locked encoding table (which deliberately defines
  Pending/Queue as a first-class redundant-encoded state) and gives the operator an honest
  backlog-depth signal, at the cost of one preset column and one rollup row.
