# Research — Sanctioned Parallel-Worktree Batch Execution

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`user/scripts/lazy_coord.py` — the concurrency plane, already built.** Stdlib-only,
  deliberately separate from `lazy_core` (must not import it): `acquire_lock`/`release_lock`
  (atomic `os.mkdir`, exponential backoff, `TimeoutError`; never `fcntl`/`flock`),
  `acquire_lease`/`heartbeat`/`verify_fencing`/`reclaim_expired`/`release_lease` over a LOCKED
  `leases.json` schema (`worker_pid`, `worktree_slot`, `term_token`, `heartbeat_timestamp`,
  `ttl_seconds`), `FencingError`, injected `now` for deterministic tests, and
  `provision_pool`/`scrub_slot` worktree management (the exact ordered scrub: index.lock removal
  with backoff → fetch under lock → `checkout --detach origin/main` → `reset --hard` →
  `clean -fdx` → branch; no submodule step). Five smoke fixtures (`lazy_coord.py --test`) pin
  lease-ops-don't-perturb-queue, no-double-claim, reclamation, fencing, and mkdir mutual
  exclusion. The coordinator is largely composition over this module.
- **`user/skills/lazy-worker/SKILL.md`** — the worker contract the coordinator generalizes: lock
  only around shared-state mutation, real work outside the lock, heartbeat every ~300s (≤ ttl/3),
  MANDATORY `verify_fencing` before any `queue.json` mutation, zombie workers abort on
  `FencingError`, finalize under re-acquired lock. Its Cognito specifics (`<COG_DOCS>` paths,
  `materialized.json`, `p/<wi_id>-<slug>` PR branches, PR-and-stop) are what D1/D10 parameterize
  away for the main-based repos.
- **The two archived arbitration bugs — the contract being extended.**
  `concurrent-same-branch-walkers-no-arbitration` (fixed 2026-06-20): unarbitrated same-repo
  same-pipeline walkers clobbered the run marker; fixed by checkpoint-discriminated refusal in
  `refuse_run_start_clobber`; its "Alternative considered" section explicitly points intentional
  parallelism at "the `lazy-worker` + `lazy_coord.py` path, not `/lazy-batch` on a shared branch"
  — this SPEC is that path, made autonomous. `single-slot-marker-ownership-race-disarms-owning-run`
  (fixed 2026-06-20): markers are now born owner-bound (`--run-start --session-id`), with
  `marker_owner_status` detect + `reassert_marker_owner` re-arm; the bug's Proven Finding 3 names
  `lazy_coord`'s `term_token` fencing as the in-codebase precedent the marker deliberately lacks —
  the coordinator pairs each lane marker with a lease token to get exactly that protection for
  contended writes.
- **Per-repo keyed state dirs** (`multi-repo-concurrent-runs`): `claude_state_dir()` resolves
  `~/.claude/state/<repo_key>/` with `repo_key = sha1(normalized realpath)`. A git worktree is a
  different realpath, so lanes inherit isolated markers/registries/ledgers with zero engine change
  — the load-bearing observation behind D2's recommendation. The enforcement hooks already resolve
  per-cwd (`--marker-present --repo-root <cwd>`), so containment arms per lane for free.
- **Marker plumbing the lanes reuse verbatim:** `work_branch` stamping via `_emit_work_branch` at
  `--run-start` (consumed by `block-sentinel-write-on-stray-branch.sh` — lane sentinels on lane
  branches pass; ports to the work branch at the main root pass); the 24h staleness reclaim
  (coordinator-death recovery); `RUN_CONTINUITY_FIELDS`/`RUN_FRESH_FIELDS` with the
  completeness test that forces the new `parent_run` field to be classified explicitly.
- **The serial tail's singletons:** `--ensure-runtime` manages ONE dev runtime/MCP server (port
  3333, `.runtime.lock.json`, HIJACKED-never-SIGKILL) — two lanes cannot validate concurrently,
  grounding D4's coordinator-owned tail. `__mark_complete__` owns the receipt + ROADMAP strike +
  queue trim; `lazy-queue-doc.py` rides the per-cycle commit. All main-root, coordinator-only.
- **Heavy-build arbitration, already solved:** `build-queue.ps1` is explicitly a "machine-global
  FIFO build serializer … so only ONE build runs at a time across all worktrees" (Cognito), and
  `long-build-ownership-guard.sh` + the `run_transient_build` Transient Build contract route
  subagent long builds to orchestrator ownership — in parallel mode, to the coordinator (D8).
- **Park-mode vocabulary** (`--park-needs-input`/`--park-blocked`, `parked[]`,
  `queue-exhausted-all-parked`) — the failure-isolation semantics D5 extends to lanes.
- **`queue-dependency-dag` (sibling SPEC, hard dep)** — supplies the enforced readiness predicate;
  `parse_independent_marker` (`independent: true`/`no_shared_state: true`) supplies the isolation
  rail. Together they are the shard predicate's only inputs (D3).

## External prior art & concepts

(Training-knowledge survey, not live research.)

- **Fencing tokens (Kleppmann, *DDIA*; Chubby/GFS leases):** a lease alone cannot stop a paused
  ("zombie") holder from writing after expiry; a monotonically increasing token checked at the
  resource fixes it. `lazy_coord.term_token` + `verify_fencing` is a faithful implementation; the
  coordinator's rule "fence before every contended write" is the standard discipline.
- **Merge queues (bors/homu, GitHub merge queue, Zuul):** parallel work integrates through a
  single serializing agent that applies changes in a deterministic order and ejects conflicting
  items for rework rather than resolving in place. D4's queue-order merge + abort-and-demote is
  this pattern; "demote to serial re-run on the updated base" is bors' eject-and-retry.
- **CI fan-out (GitHub Actions `strategy.matrix` + `needs:`):** shard only what the dependency
  graph proves independent; one shard's failure does not cancel siblings unless `fail-fast` — the
  D5 park-don't-halt default.
- **Build-system parallelism (Make `-j`, Bazel remote execution):** parallelize only
  graph-independent nodes; correctness comes from declared edges plus sandboxed/isolated
  workspaces, not from predicting file overlap — supporting D3's rejection of overlap prediction
  in favor of declared independence + isolation + deterministic conflict detection.
- **Git worktrees for agent fleets:** the emerging convention for multi-agent coding (isolated
  checkouts sharing one object store; sibling `-lanes/` dirs; branch-per-task) — including the
  known operational hazards `scrub_slot` already handles: shared `.git` index locks, fetch
  contention, and stale-slot hygiene.
- **Work-stealing/task pools:** freed lane slots claiming the next ready item (D5) is plain
  work-queue practice; the lease TTL + reclaim sweep is the standard liveness mechanism for
  crashed workers.

## Alternatives analysis

- **Coordinator shape (D1).** Scaling out `lazy-worker` sessions was rejected for v1 because it
  externalizes exactly the things the batch family exists to own — budget, flush, terminal
  honesty, and single-writer reconciliation — onto N operator-started sessions; and its PR-based
  finalization does not fit the main-based repos this v1 targets. A flag on `/lazy-batch` was
  rejected on coupling economics: that skill's prose is one half of the most regression-sensitive
  coupled pair in the repo (`/lazy-batch` ↔ `/lazy-batch-cloud`), and threading lane logic through
  it taxes every future serial edit. A sibling skill composes the same components while keeping
  the serial orchestrators frozen.
- **Marker model (D2).** The lane-map marker (one file, N slots) was rejected because every
  consumer of the marker — the dispatch guard's owner scoping, `--marker-present`,
  `--marker-work-branch`, staleness paths A/B, `marker_owner_status`, checkpoint continuity —
  assumes single-slot semantics; changing that contract is the definition of "weakening the
  ownership model." Markerless lanes were rejected as an enforcement downgrade (unarmed guards).
  Per-worktree keyed markers require zero semantic change: the mechanism built to isolate REPOS
  isolates WORKTREES because the key is a path hash — sanctioned lanes and rogue walkers are
  distinguished structurally (different state dirs) rather than by a new discriminator field.
- **Independence criterion (D3).** File-overlap prediction fails the repo's own bar twice: at
  claim time most items have no plan, so predicted file sets would be LLM-inferred (banned as
  state), and even plan-derived sets are estimates — while git's merge is a deterministic overlap
  detector that already exists. Conservative inputs (declared deps + declared isolation) plus
  deterministic detection (merge) plus a bounded recovery (demote) dominates prediction on both
  reliability and cost. The demotion event doubles as the falsifier for a wrong
  `independent: true` marker — surfaced, never silently absorbed.
- **Merge ordering (D4).** Completion-order merging was genuinely attractive (lower latency, no
  waiting lane branches) but loses run reproducibility — the final history depends on scheduler
  timing — and the stub's direction says "deterministic ordering." Queue-order merging makes the
  merged history a pure function of the queue and the lane outcomes; the latency cost is bounded
  by per-lane budget slices.
- **Lifecycle split (D4).** Running `__mark_complete__` in-lane was rejected structurally: it
  mutates the three files every lane shares (queue.json trim, ROADMAP strike, plus LAZY_QUEUE
  regen at commit), guaranteeing conflicts, and puts receipts on branches the main-root state
  machine cannot see — a completion the probe can't read is not a completion.
- **Failure isolation (D5).** Halt-on-first-sentinel wastes N−1 lanes on one ambiguous question
  (the anti-goal). In-lane auto-resolution was deferred: needs-input resolution is an attended,
  AskUserQuestion-shaped flow owned by the parent orchestrator; pushing it into background lanes
  would either stall silently or answer without the operator.

## Pitfalls & risks

- **Cross-lane state bleed via shared `.git`.** Worktrees share one object store and refs;
  concurrent fetches/branch ops contend on internal locks. Mitigated by `scrub_slot`'s
  fetch-under-lock + index.lock retry discipline; Phase 3/5 must fixture three-lane contention
  (deferred empirical check). Residual: a pathological git version bug — accept, observe in
  retros.
- **Friction-detector false positives across lanes.** `--cycle-end`'s process-friction check
  compares per-run HEAD snapshots; with N lanes it must only ever see its OWN lane's HEAD
  (per-worktree state dirs should guarantee this, but it is exactly the kind of implicit
  assumption that has bitten before — pinned as a named fixture, D9).
- **Budget accounting drift.** Two counters (parent aggregate, lane slices) can diverge under
  coordinator crash/resume. The lane marker slice is the fail-safe ceiling; reconciliation happens
  at lane end; a crashed run's honest answer is "≤ authorized" (slices sum to ≤ parent), never
  ">" — verified by the budget validation row.
- **Demotion churn.** If `independent: true` markers are over-applied, demotions eat the budget
  serially and the feature underdelivers. The flush's marker-audit finding + retro feed is the
  measurement loop: demotion rate per run is the feature's own KPI; a high rate is a signal to
  tighten marking practice, not to add prediction machinery reflexively.
- **Throughput theater (falsifiability).** The feature's claim is wall-time throughput on
  independent items. The lane ledger records per-lane cycles and outcomes, so a retro can compute
  "cycles-in-parallel vs serial-equivalent" per run; if measured speedup on real queues is ~1×
  (e.g. queues are usually dependency-chained), the honest conclusion is that the queue shape —
  not the harness — is the bottleneck, and the feature should stay parked rather than grow.
- **Coordinator as a new privileged actor.** Its new ops (claim, merge, port, demote) must be
  cycle-guarded (`refuse_if_cycle_active`) and orchestrator-only like `--reorder-queue`, or a lane
  subagent could recursively coordinate — the containment hooks' Skill-tool deny already blocks
  `/lazy*` recursion; the CLI guards close the script side.
- **Windows path realities.** `repo_key` normalization was built for repo roots; worktree paths
  (junctions, `subst`, 8.3 names) must be confirmed to key distinctly and stably (deferred
  empirical check before Phase 2 lands).

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 coordinator shape + scope | New `/lazy-batch-parallel` skill; workstation-only v1 | Medium-high (OPEN — operator) |
| D2 marker/arbitration model | Per-worktree keyed lane markers (owner-bound to coordinator) under one parent marker + `lazy_coord` fencing leases | High (OPEN — operator) |
| D3 independence criterion | Dep-DAG readiness + `independent: true`; no overlap prediction; merge detects | High (OPEN — operator) |
| D4 lifecycle + merge policy | Lanes through implement/retro; coordinator tail; queue-order merge; abort-and-demote | Medium-high (OPEN — operator) |
| D5 failure isolation | Park lane, siblings continue, sentinel ported at flush, branch preserved | High (OPEN — operator) |
| D6 lanes/budget | `min(N, shardable, pool_size)`; parent `max_cycles` aggregate SSOT + lane slices | High (auto) |
| D7 contended writes | Coordinator single-writer at main root under lock, fenced | High (auto — operator-set constraint) |
| D8 heavy builds | Existing build-queue + long-build takeover machinery; no new arbitration | High (auto) |
| D9 containment | Unchanged hooks armed per lane; one new friction-detector fixture obligation | High (auto — operator-set constraint) |
| D10 pool generalization | Parameterize `provision_pool`/`scrub_slot` roots + branch template; `lane/<id>`; sibling `-lanes/` pool | High (auto) |
