# Research — First-Class Dependency DAG in queue.json

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The SPEC `**Depends on:**` block** (`user/skills/_components/dep-block-schema.md`) is the
  existing dependency SSOT: em-dash-separated `feature-id — kind — reason` lines with
  `hard`/`soft`/`composes` kinds, a documented parsing protocol, upstream resolution rules, and a
  completion check. Its machine parser already exists — `parse_dep_block` in
  `user/scripts/lazy-state.py` (~line 1158) — and is already consumed at probe time by the
  skip-ahead branch. This feature does not invent a dependency model; it projects the enforceable
  slice of the existing one into `queue.json`.
- **The skip-ahead readiness predicate** (`lazy_core.skip_ahead_ready`, ~line 12214 of
  `lazy_core.py`) is the shape the stub directs the enforcement toward: key 1 blocks a candidate
  with a `hard` dep on a gated id; key 2 requires the `independent: true` isolation marker
  (`lazy_core.parse_independent_marker`, two-source: SPEC frontmatter + queue entry). The SPEC's
  D2 analysis is grounded in the difference between that skip (leapfrogging halted-but-workable
  work — needs the isolation rail) and a dep-gate (order correction — must NOT need it).
- **Fail-fast precedents** the D4 error surface reuses: malformed `queue.json` → `_die` exit 2
  (`load_queue`, `lazy-state.py` ~line 495); an unregistered `requires_host:` capability id →
  canonical `BLOCKED.md` `blocker_kind: unknown-host-capability` written by `compute_state`
  (because a silent defer on an unsatisfiable gate is infinite queue starvation — the identical
  argument for dangling dep ids); clean saturated terminals `host-capability-saturated` /
  `queue-exhausted-all-parked` / `queue-exhausted-budget-deferred` in
  `lazy_core.SANCTIONED_STOP_TERMINAL` (the naming pattern `queue-exhausted-dependency-gated`
  follows).
- **Script-owned queue mutation chokepoints** the D5 feeder mirrors: `lazy_core.reorder_queue`
  (load → validate → mutate → `_atomic_write`, `noop: true` byte-stable no-ops, `_die` on missing
  id), `enqueue_adhoc`, and `lazy_core.clear_queue_stub` (the precedent for the state script — not
  the orchestrator — mutating a single queue-entry field). HARD CONSTRAINT: no hand-edits to
  `queue.json`.
- **Receipt-gated completion** (`docs/features/CLAUDE.md`; `lazy_core.has_completion_receipt`,
  `write_completed_receipt(kind=)`) — the D3 completion oracle. The bug pipeline's archive-on-fix
  terminal (`__mark_fixed__` → `docs/bugs/_archive/<slug>/`) is why bug-side dep resolution must
  look under `_archive/`.
- **Coupled-pair parity discipline**: `lazy_parity_audit.py --repo-root .` (no `--report` flag),
  the justified-divergence register (bug pipeline has no skip-ahead — `bug-state.py` accepts
  `--strict-research-halt` for argparse parity and discards it, ~line 631), and the pinned
  `--test` baselines (`tests/baselines/*.txt` via `_normalize_smoke_output`) that make
  "byte-identical when the field is absent" a checkable claim rather than an intention.
- **Read-only consumers** that will eventually render the new probe key without re-inference:
  `pipeline_visualizer` and `lazy-queue-doc.py` (both shell the state scripts; both are pure-read
  by contract — mobile-queue-control SPEC).

## External prior art & concepts

(Training-knowledge survey, not live research.)

- **Build systems (Make, Bazel, Buck, Ninja):** dependency edges are *constraints*, ordering is
  *scheduling preference* — a target list's order never overrides the graph. This is the cleanest
  articulation of the SPEC's D8 stance: `--reorder-queue` stays pure preference, the DAG stays
  pure constraint, and enforcement at evaluation time (probe time) is what lets the two compose.
  Bazel additionally validates the graph eagerly and fails the whole evaluation on a cycle —
  the D4 `_die` recommendation matches that posture for machine-owned graph state.
- **Workflow orchestrators (Airflow, Temporal, GitHub Actions `needs:`):** tasks declare upstream
  ids; the scheduler dispatches only tasks whose upstreams reached a terminal success state, and a
  dangling `needs:` reference is a validation error at load, not a silent pass. GitHub Actions'
  flat `needs: [job-id, ...]` — ids only, no kinds — is the exact shape D1's recommendation A
  proposes; kind semantics (Airflow's trigger rules) are the vN generalization if ever needed.
- **Topological-sort tooling (`tsort`, Kahn's algorithm):** cycle detection over a queue-sized
  graph is trivial (O(V+E), tens of nodes) and standard; there is no need for incremental or
  lazy cycle checking at this scale.
- **Package managers (cargo, npm):** resolve dependency identity by namespace to avoid ambiguity —
  the motivation for reserving `bug:`/`feature:` prefixes (D6) instead of letting bare ids become
  ambiguous when cross-pipeline deps arrive.

## Alternatives analysis

- **Field shape (D1).** Kind-annotated queue records were rejected as a duplicated representation:
  the only machine consumer of kinds (`skip_ahead_ready`) deliberately ignores `soft`/`composes`
  because those kinds gate on *existence*, not completion (`dep-block-schema.md`), and existence
  is satisfied the moment a SPEC dir exists — i.e. always, for anything queued. Enforcement
  therefore only ever acts on `hard`, so the queue field carrying anything else is decoration with
  a drift cost. A string list also upgrades additively to records later behind one read helper.
- **Enforcement placement (D2).** Reusing the gated-head machinery (adding dep-gated ids to
  `gated_ids` and forcing successors through the two-key predicate) was rejected because it would
  demand `independent: true` of the *dependency itself* before it could be worked first — the
  opposite of the feature's purpose. A separate `continue` with its own probe surface keeps the
  two skips semantically distinct and keeps `--strict-research-halt`'s documented contract
  (skip-ahead on/off) untouched. Transitivity needs no traversal: "queued ⇒ incomplete" makes each
  item's local check sufficient.
- **Completion oracle (D3).** ROADMAP-strikethrough (allowed by the prose schema's completion
  check) was rejected for the state machine: ROADMAP is human-facing and hand-formatted; the
  receipt gate is the machine contract and already hard-errors on receiptless `Complete`.
- **Graph-error posture (D4).** Degrade-and-continue was seriously weighed (a broken edge halting
  a whole repo's pipeline is a real cost) and rejected: the writer is script-owned (D5), so a
  cycle/dangling id indicates a feeder bug or hand-edit — precisely the states the harness wants
  loud. The dangling-id middle ground ("treat as satisfied with a warning") silently un-gates on a
  typo, the exact drift-to-silence class the mission text forbids.
- **Feeder timing (D5).** Mark-complete-time reconciliation runs on the wrong item (the upstream)
  and too late (the dependent must be gated from planning); manual-only guarantees decay.
  `/spec-phases` is where dep look-back already happens (`dep-block-schema.md` consumer table), so
  the sync lands where the information is already in hand.
- **Cross-pipeline (D6).** v1 prefixed cross-queue resolution was rejected on evidence: zero
  cross-pipeline dep exists in current prose, the parallel-worktree consumer shards within one
  pipeline per run, and the `--next-merged` precedent shows cross-queue reads are deliberately
  scoped to ordering-only today. Reserving the prefix costs one `_die` branch and buys a clean vN.

## Pitfalls & risks

- **Silent divergence between prose and queue.** If `--sync-deps` is forgotten and the drift
  diagnostic is ignored, the queue field can lag the SPEC block. Mitigated by wiring the sync into
  `/spec-phases` (the pipeline path every item takes) and by D7's union semantics — skip-ahead
  still sees the prose even when the queue lags. Residual risk: the dep-gate itself reads only the
  queue field; the drift `_diag` is the tripwire. If drift recurs in retros, promote the
  diagnostic to a gate (a harness-bug follow-up, per the self-improvement loop).
- **Over-gating stranding the queue.** A wrong `hard` dep (should have been `soft`) holds work
  behind an upstream that never needed to finish. The all-gated terminal + flush names every hold
  and its missing deps, so the operator sees exactly which edge to fix (`--sync-deps` after a SPEC
  edit, or `--reorder-queue --to remove`). This is the falsifiability story: every hold is
  attributable to a named edge, never inferred.
- **`_die`-on-cycle blast radius.** A cycle bricks probes (including `/lazy-status`) until fixed.
  Accepted deliberately (D4), but the `_die` message must name the members and the corrective
  commands, or the operator lands in a dead pipeline with no map. Validation row pins the message.
- **Baseline churn.** Enforcement touches the hottest loop in `compute_state()`; the byte-identity
  claim must be proven by the pinned baselines, not asserted. Phase 1 re-pins only via
  `_normalize_smoke_output` (never by hand).
- **Bug-pipeline asymmetries.** Archive-aware resolution (`docs/bugs/_archive/`) and the absent
  skip-ahead are easy to mis-mirror; both are named justified divergences with parity-audit
  coverage to keep them deliberate.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 field shape | Flat hard-only `"deps": ["<id>"]`; SPEC block stays SSOT for kinds | High (OPEN — operator) |
| D2 enforcement | Independent dep-gate `continue` before skip-ahead; active under strict flag | High (auto) |
| D3 completion oracle | Receipt-gated on-disk check; Superseded ⇒ not complete | High (auto) |
| D4 error surface | Cycle `_die` 2; dangling/Superseded → `BLOCKED.md` `unknown-dependency`; `queue-exhausted-dependency-gated` terminal | Medium-high (OPEN — operator) |
| D5 feeder + drift | `--sync-deps` at `/spec-phases`; probe-time drift `_diag`; `--enqueue-adhoc --deps` | High (OPEN — operator) |
| D6 cross-pipeline | v1 same-pipeline; reserve `bug:`/`feature:` prefixes | High (OPEN — operator) |
| D7 skip-ahead input | Queue deps ∪ SPEC hard deps feed key 1 | High (auto) |
| D8 reorder interaction | No reorder-time validation; probe-time enforcement composes | High (auto) |
| D9 parity | Mirror field/gate/CLI to bug pipeline; archive-aware; no skip-ahead mirror | High (auto) |
| D10 probe surface | `dep_gated: [{id, missing}]` + `_diag` audit lines | High (auto) |
