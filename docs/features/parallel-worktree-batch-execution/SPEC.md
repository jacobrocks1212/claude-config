# Sanctioned Parallel-Worktree Batch Execution — Feature Specification

> One repo = one lane today: every arbitration layer built so far (`refuse_run_start_clobber`,
> single-slot marker ownership, per-repo keyed state dirs, the containment hooks) exists to refuse
> *accidental* concurrency, and there is no sanctioned path to *deliberate* concurrency. This
> feature adds one: a coordinator that shards dependency-independent, `independent: true`-marked
> queue items across git worktree lanes — each lane an isolated checkout with its own branch, its
> own per-worktree keyed state dir, its own born-owner-bound run marker, and a `lazy_coord.py`
> fencing-token lease — while the coordinator remains the single writer of every contended
> resource (`queue.json`, ROADMAP, LAZY_QUEUE.md, the work branch) and merges lane branches back
> in deterministic queue order, demoting any conflicting item to a serial re-run. It extends the
> existing arbitration model; it never bypasses or weakens `refuse_run_start_clobber`, and the
> containment hook family governs every lane cycle unchanged. High ambition — multi-phase.

**Status:** Complete
**Priority:** P2
**Last updated:** 2026-07-04
**Friction-reduction feature:** yes — the friction is serial-only queue execution: independent
items wait behind each other even when nothing shared blocks them, and every existing arbitration
layer was built to PREVENT concurrency, not provide it (Executive Summary). Declared against the
existing registry row below.
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:**

- queue-dependency-dag — hard — the coordinator's independence/readiness predicate is the enforced deps field; without it sharding cannot prove two items are safe to parallelize.

> Substantive dependencies beyond the block are **implemented contracts**, not sibling specs:
> - `user/scripts/lazy_coord.py` — the concurrency plane: `os.mkdir` global lock
>   (`acquire_lock`/`release_lock`), fencing-token leases in `leases.json` (`acquire_lease` /
>   `heartbeat` / `verify_fencing` / `reclaim_expired` / `release_lease`, `FencingError`), and
>   worktree-pool provisioning + scrub-to-clean (`provision_pool`, `scrub_slot`).
> - `user/skills/lazy-worker/SKILL.md` — the single-item claim → implement → finalize-under-lock
>   worker shape this coordinator generalizes.
> - Single-slot marker ownership (born owner-bound `--run-start --session-id`,
>   `marker_owner_status`, `reassert_marker_owner`) + checkpoint-discriminated
>   `refuse_run_start_clobber` arbitration — extended per lane, never weakened (see
>   `docs/bugs/_archive/single-slot-marker-ownership-race-disarms-owning-run/` and
>   `docs/bugs/_archive/concurrent-same-branch-walkers-no-arbitration/`).
> - Per-repo keyed state dirs (`lazy_core.claude_state_dir()` / `repo_key(repo_root)`) — the
>   isolation mechanism that gives each worktree lane its own marker/registry/ledger for free.
> - The containment hook family (`lazy-cycle-containment.sh`, `lazy-dispatch-guard.sh`,
>   `lazy-route-inject.sh`, `block-sentinel-write-on-stray-branch.sh`) — unchanged, armed per lane
>   via the lane's own state dir and `work_branch`.
> - `build-queue.ps1` (machine-global FIFO build serializer) + `long-build-ownership-guard.sh` —
>   the already-solved heavy-build arbitration across worktrees on shared hosts.

---

## Executive Summary

Queue items that share no dependencies and no state still execute strictly serially per repo. The
harness has spent multiple hardening rounds making that serialization safe — `refuse_run_start_clobber`
refuses a second same-repo walker (checkpoint-discriminated), the run marker is born owner-bound so
a foreign session can never stamp the ownership slot first, per-repo keyed state dirs isolate runs
across repos, and the containment hooks fence every cycle subagent. All of it *prevents*
concurrency; none of it *provides* concurrency. Meanwhile the ingredients for sanctioned
parallelism already exist and are proven in isolation: `lazy_coord.py` ships a global lock,
fencing-token leases, and worktree pool provisioning (built for `lazy-worker` multi-session use);
`lazy-state.py --feature-id` scopes `compute_state()` to a single item; and the
`queue-dependency-dag` prerequisite turns "these items are independent" from prose into an
enforced, mechanical predicate. This is the single biggest throughput multiplier available to the
system — and the stub's operator constraints frame it correctly: extend arbitration, never bypass
it.

The proposed shape is a **coordinator** (a new orchestrator-level parallel mode of the
`/lazy-batch` family) that runs as ONE parent session owning ONE parent run marker at the main
repo root — so the existing same-repo second-walker refusal still protects the whole construction.
The coordinator claims N ready items whose deps are complete and which carry the existing
`independent: true` isolation marker, provisions a worktree lane per item (generalizing
`provision_pool`/`scrub_slot` off their Cognito-specific roots), arms each lane's own per-worktree
keyed state dir with a lane run marker born owner-bound to the coordinator's session
(`--run-start --repo-root <worktree> --session-id <coordinator>`), takes a fencing-token lease per
item, and dispatches ordinary cycle subagents into the lanes. Lanes do the parallel-safe front
half through implementation and retro inside their own checkout and branch; everything contended —
merging lane branches to the work branch (deterministic queue order; conflict ⇒ demote the item to
a serial re-run), MCP validation against the singleton runtime, `__mark_complete__` (receipt,
ROADMAP strike, queue trim), LAZY_QUEUE.md regeneration — is coordinator-owned, serialized under
the `lazy_coord` global lock. A lane that halts (BLOCKED / NEEDS_INPUT) is parked without touching
its siblings, its sentinel ported to the canonical tree at flush.

This serves the **efficient** mission criterion (wall-parallel progress on independent items with
zero relaxation of the integrity model) and stays **best-practice-aligned**: fencing tokens and
single-writer merge discipline are the textbook mechanisms for exactly this shape, and both
already live in this repo. The feature is deliberately multi-phase; each phase lands
independently, and the serial pipeline remains byte-identical whenever the parallel mode is not
invoked.

## Design Decisions

### D1. Coordinator shape and v1 scope

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended option taken)`
- **Question:** What is the operator-facing entry point, and which environments does v1 cover?
  This decides whether parallelism is a mode of the autonomous batch family or a scaling-out of
  the manual `lazy-worker` sessions.
- **Options:**
  - **A — New coordinator skill `/lazy-batch-parallel <max-cycles> --lanes N` (recommended):** one
    parent session; the coordinator loop shards ready items into lanes and dispatches lane cycle
    subagents (background Agent dispatches), reusing `lazy_coord.py` primitives for claim
    arbitration and the existing cycle-prompt machinery (`--emit-prompt` / `--feature-id` scoping)
    per lane. Pros: one budget, one terminal report, one privileged actor, the existing
    `/lazy-batch` orchestration contract (bookends, park-mode, flush) carries over; nothing new
    runs unattended. Cons: a new coupled skill to keep in lockstep with the batch family.
  - **B — Scale out `/lazy-worker`:** the operator starts N worker sessions; each claims a lease
    and one item. Pros: machinery exists today. Cons: N operator-started sessions with no parent
    budget, no unified flush, no merge owner (workers open PRs — a Cognito-shaped flow, not the
    main-based claude-config/AlgoBooth flow); `lazy-worker` is Cognito-flavored (`<COG_DOCS>`
    paths, `materialized.json`, `p/<wi_id>-<slug>` PR branches); and nothing owns queue.json
    reconciliation between workers beyond raw lease discipline.
  - **C — Flag on `/lazy-batch` (`--lanes N`):** same engine as A but no new skill. Cons: the
    serial skill's prose is already the most coupling-sensitive file pair in the repo
    (`/lazy-batch` ↔ `/lazy-batch-cloud`); threading lane logic through it multiplies the
    mirrored-edit surface for every future serial change.
  - **v1 environment scope (either A or C):** workstation-only, repos that work on and push
    `main`-based work branches (claude-config, AlgoBooth). Cloud is vN: the cloud batch already
    defers MCP and runs in a single container where worktrees are possible but the payoff is
    smaller and the checkpoint/resume machinery would need lane-awareness.
- **Recommendation:** A, workstation-only v1. A new skill keeps the serial orchestrators frozen
  (their prose is regression-sensitive), makes the parallel mode auditable as one unit, and gives
  the retro/hardening loop a clean skill identity to grade. It composes with, rather than edits,
  the `/lazy-batch` contract; `lazy-worker` remains the Cognito multi-session path.
- **Resolution:** RESOLVED — **A** (new skill `user/skills/lazy-batch-parallel/SKILL.md`,
  workstation-only v1: claude-config + AlgoBooth). *(operator-approved 2026-07-04 — recommended
  option taken)*

### D2. Marker and arbitration model for lanes

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended option taken)`
- **Question:** How do sanctioned lanes coexist with the single-slot run-marker ownership model,
  and how does `refuse_run_start_clobber` tell a sanctioned lane from a rogue second walker —
  without weakening either?
- **Options:**
  - **A — Per-worktree keyed lane markers under one parent marker (recommended):**
    `repo_key(repo_root)` is the sha1 of the *normalized real path*, so each worktree already
    resolves to its OWN `~/.claude/state/<repo_key>/` — a lane armed via
    `lazy-state.py --run-start --repo-root <worktree> --session-id <coordinator-session>` gets its
    own born-owner-bound marker, prompt registry, and deny ledger with ZERO changes to the
    ownership model. The parent run marker lives at the main root as today. Arbitration
    consequences, all emergent from existing rules: a rogue second walker at the main root is
    refused by the parent marker (same-pipeline, live, no checkpoint — the
    `concurrent-same-branch-walkers-no-arbitration` fix, untouched); a rogue walker started inside
    a lane worktree is refused by that lane's marker; lanes never contend for any slot because no
    two lanes share a state dir. Lane markers additionally carry an identifying
    `parent_run: {repo_root, started_at}` field so audits (and `--run-end` sweeps) can prove a
    lane marker is sanctioned — a new marker key, which the
    `test_run_marker_continuity_partition_is_complete_and_disjoint` completeness test forces to be
    explicitly classified into `RUN_FRESH_FIELDS` (it is run-invariant identity, re-derived at
    run-start). On top of markers, each claimed item holds a `lazy_coord` lease (fencing token);
    the coordinator carries the token and verifies fencing before every contended write, so a
    zombie/abandoned lane can never corrupt shared state even if its marker lingers.
  - **B — Marker-per-lane inside the MAIN root's state dir:** turn the single marker file into a
    lane map. Cons: rewrites the single-slot ownership contract every hook and guard reads
    (`--marker-present`, `--marker-work-branch`, staleness paths, owner detect/re-arm) — exactly
    the "weaken the model" path the stub forbids.
  - **C — Markerless lanes (leases only):** lanes run with no run marker. Cons: every lane
    dispatch runs guard-disarmed (the marker is what arms the dispatch guard, containment, and the
    sentinel-branch hook) — parallelism would run with LESS enforcement than serial, an integrity
    regression.
- **Recommendation:** A. It is the only option where every existing invariant applies verbatim,
  per lane: markers stay single-slot and born owner-bound (`single-slot-marker-ownership` fix
  extended, not weakened — the coordinator session owns all lane slots), `refuse_run_start_clobber`
  keeps its exact semantics at every root it is evaluated against, containment hooks arm per lane
  because they already key off `--marker-present --repo-root <cwd>`, and
  `block-sentinel-write-on-stray-branch.sh` works because each lane marker's `work_branch` is the
  lane branch. The fencing-token lease supplies the zombie-writer protection the marker model
  deliberately lacks (the archived ownership bug names `lazy_coord`'s `term_token` as the
  in-codebase precedent).
- **Resolution:** RESOLVED — **A** (per-worktree keyed lane markers born owner-bound to the
  coordinator session under one parent marker + `lazy_coord` fencing leases per item; the new
  marker content field `parent_run: {repo_root, started_at}` is classified into
  `RUN_FRESH_FIELDS`). *(operator-approved 2026-07-04 — recommended option taken)*

### D3. Independence criterion: DAG readiness + isolation marker; no file-overlap prediction

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended option taken)`
- **Question:** What proves two items safe to run concurrently? The stub explicitly asks whether
  predicted file overlap should augment dep-DAG readiness.
- **Options:**
  - **A — Dep-ready + `independent: true`, conflicts caught at merge (recommended):** an item is
    shardable iff (1) every queue `deps` id is Complete-with-receipt (the `queue-dependency-dag`
    predicate), and (2) it carries the affirmative `independent: true` / `no_shared_state: true`
    marker (`lazy_core.parse_independent_marker` — the same rail that makes default-on skip-ahead
    safe; absent ⇒ NOT shardable, conservative by default). Mutual independence within the claimed
    set falls out of (1): if B hard-deps A, A is incomplete while claimed, so B is not dep-ready.
    Actual overlap that slips through both rails is caught deterministically by git at merge time
    and demoted to serial (D5) — detection, not prediction.
  - **B — Additionally predict file overlap:** intersect predicted touched-file sets (from plans /
    SPEC prose / an LLM guess) before claiming. Cons: at claim time most items have no plan yet
    (lanes run the front half too), so the prediction is LLM-inferred — precisely the
    state-inference the harness bans ("deterministic script-owned state over LLM-inferred state");
    a false-negative prediction gives unearned confidence, a false positive silently serializes;
    and the cost lands on every claim while the merge safety net exists anyway.
  - **C — Dep-ready only (no isolation marker):** maximizes lane fill but abandons the
    shared-state rail the skip-ahead feature deliberately introduced; unmarked items were judged
    unsafe to leapfrog *serially* — running them *concurrently* is strictly riskier.
- **Recommendation:** A. Lean conservative: both inputs are deterministic on-disk reads, the
  operator/spec (not a model) asserts isolation, and the merge gate makes the residual risk a
  bounded, recoverable event rather than a corruption. If retros show demotions clustering on
  predictable overlaps, a deterministic overlap heuristic (e.g. declared `spec_dir`-adjacent path
  globs) is a vN refinement — flagged, not silently added.
- **Resolution:** RESOLVED — **A** (independence = dep-DAG readiness ∧
  `parse_independent_marker` true ∧ no live lease; NO file-overlap prediction; merge-conflict
  demotion is the deterministic safety net). *(operator-approved 2026-07-04 — recommended option
  taken)*

### D4. Lane lifecycle scope and merge policy

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended option taken)`
- **Question:** Which lifecycle steps run inside a lane vs serially in the coordinator, and how do
  lane branches land on the work branch?
- **Options (lifecycle):**
  - **A — Lane runs spec → research-gate → phases → plan → implement → retro; coordinator owns
    validation + completion (recommended):** everything docs+code and item-local parallelizes;
    the tail is inherently serial anyway — MCP validation talks to the singleton runtime
    (`--ensure-runtime`, one port-3333 process per machine; two lanes cannot validate
    concurrently), and `__mark_complete__` mutates the contended trio (receipt+SPEC flip on the
    canonical tree, ROADMAP strike, queue trim) and must run on the post-merge work branch so the
    receipt-gated completion lands on the tree the next probe reads.
  - **B — Lane runs the full lifecycle including mark-complete:** each lane's `__mark_complete__`
    trims its own worktree copy of `queue.json` and strikes its ROADMAP copy — guaranteeing
    pairwise merge conflicts on the two hottest shared files, and putting the completion receipt
    on a branch the main-root state machine cannot see until merge. Structurally wrong.
- **Options (merge policy):**
  - **Queue-order merge (recommended):** completed lane branches merge to the work branch in the
    items' queue order, serialized under the `lazy_coord` global lock, coordinator-only. A lane
    finishing early waits for earlier-queued siblings before merging (its subagent is done; only
    the merge waits). Pros: the final history is deterministic and independent of lane timing —
    the stub's "deterministic ordering" constraint honored literally; conflict attribution is
    unambiguous (an item conflicts against a fixed, reproducible base). Cons: a slow early-queued
    lane delays later merges (bounded by per-lane budget, D6).
  - **Completion-order merge:** merge as lanes finish; record order in a ledger. Pros: lower merge
    latency. Cons: history depends on timing — reruns are not reproducible, and the stub's
    deterministic-ordering direction is only satisfied "as recorded", not "as constructed".
  - **Conflict handling (both):** `git merge` of a lane branch fails ⇒ `git merge --abort`, mark
    the item `demoted: serial` in the lane ledger, preserve the lane branch for salvage/reference,
    and leave the queue entry in place — after the parallel wave, the coordinator re-runs demoted
    items serially on the up-to-date work branch (fresh cycles see merged reality; the stub's
    "conflicts demote to serial" constraint). Doc-side conflicts are impossible by construction:
    each lane exclusively owns `docs/{features,bugs}/<slug>/` (disjoint dirs) and never touches
    `queue.json`/ROADMAP/LAZY_QUEUE.md (D7) — so demotion only ever fires on real code overlap,
    which is exactly the signal that the `independent: true` marker was wrong (surfaced in the
    flush as a marker-audit finding).
- **Recommendation:** Lifecycle A + queue-order merge + abort-and-demote. Grounded in the runtime
  singleton, the receipt-visibility requirement, and the stub's two explicit constraints
  (deterministic ordering; demote on conflict).
- **Resolution:** RESOLVED — **Lifecycle A + queue-order merge + abort-and-demote** (lanes run
  spec→implementation; the coordinator owns the validation+completion serial tail at the main
  root: `--ensure-runtime`, `/mcp-test`, `__mark_complete__`, ROADMAP strike, queue trim,
  LAZY_QUEUE.md regen; queue-order merge under the global lock; `git merge --abort` ⇒
  `demoted: serial` in the ledger, lane branch preserved). *(operator-approved 2026-07-04 —
  recommended option taken)*

### D5. Failure isolation: parked-lane semantics

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, recommended option taken)`
- **Question:** A lane halts on `BLOCKED.md` / `NEEDS_INPUT.md` (written inside its worktree, on
  its lane branch — invisible to the main root until surfaced). What happens to the lane, its
  siblings, and the sentinel?
- **Options:**
  - **A — Park the lane, siblings continue, sentinel ported at flush (recommended):** the
    coordinator reads the lane's probe (`lazy-state.py --repo-root <worktree> --feature-id <id>`),
    records the item in the run's `parked[]` (reusing the `--park-needs-input`/`--park-blocked`
    park-mode vocabulary and the `queue-exhausted-all-parked`-style accounting), ends the lane's
    marker (`--run-end --repo-root <worktree>`), releases its lease, KEEPS the lane branch +
    worktree contents, and — at end-of-run flush, under the lock, on the work branch — copies the
    sentinel verbatim into the canonical `docs/{features,bugs}/<slug>/` so the next serial run and
    the read-only surfaces (LAZY_QUEUE.md "Needs attention", visualizer) see it. The freed slot
    may claim the next ready item if budget remains. The flush report groups parked items exactly
    as the serial batch flush does.
  - **B — Halt the whole run on first lane sentinel:** the serial semantics, transplanted. Rejects
    the feature's core promise (the stub names failure isolation explicitly); one ambiguous
    NEEDS_INPUT would idle N−1 healthy lanes.
  - **C — Auto-resolve in-lane:** dispatch resolution subagents inside lanes. Rejected for v1:
    resolution rounds are operator-interactive (AskUserQuestion) and belong to the parent
    orchestrator's attended flow, not a background lane.
- **Recommendation:** A. It reuses the park-mode mental model the operator already has, keeps the
  sentinel write-path canonical (the port is a verbatim copy of a pipeline-written sentinel onto
  the marker's own `work_branch` — satisfying both `block-noncanonical-blocker-write.sh` and
  `block-sentinel-write-on-stray-branch.sh`), and loses no information (lane branch preserved).
- **Resolution:** RESOLVED — **A** (park-on-sentinel: the lane parks, siblings continue, the
  sentinel is ported verbatim to the canonical `docs/{features,bugs}/<slug>/` at flush, the lane
  branch is preserved). *(operator-approved 2026-07-04 — recommended option taken)*

### D6. Lane count and budget accounting

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How many lanes, and how does the parent `max_cycles` budget govern them?
- **Recommendation / shape:** effective lanes = `min(requested N, count of shardable items,
  pool_size)` (pool_size from config, the `lazy-worker` bound). The parent `max_cycles` is the
  aggregate SSOT: the coordinator debits every lane cycle against it and stops claiming/dispatching
  when exhausted; each lane marker carries a per-lane ceiling slice (`min(remaining_parent,
  ceil(max_cycles / lanes))`) so a runaway lane self-limits even if the coordinator dies —
  reconciled at lane end. Demoted-to-serial re-runs draw from the same parent budget (no hidden
  budget growth). HARD CONSTRAINT 8's spirit is preserved: total dispatched cycles across all
  lanes never exceed the operator-authorized `max_cycles`.
- **Resolution:** RESOLVED — as shaped (lanes = min(requested N, shardable count, pool_size);
  parent `max_cycles` is the aggregate SSOT; per-lane ceiling slice
  `min(remaining_parent, ceil(max_cycles / lanes))`; demoted re-runs draw from the same parent
  budget). *(operator-approved / locked 2026-07-04)*

### D7. Contended-resource discipline: coordinator single-writer

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Who may write `queue.json`, `ROADMAP.md`, `LAZY_QUEUE.md`, the work branch, and
  the lane ledger?
- **Recommendation / shape:** Only the coordinator, only at the main root, only under
  `lazy_coord.acquire_lock`, and only after `verify_fencing` for the item concerned — the
  `lazy-worker` Step 9 contract, promoted to the coordinator. Lanes never invoke `--apply-pseudo
  __mark_complete__`/`__mark_fixed__`, never touch their worktree copies of the contended trio,
  and exclusively own their disjoint `docs/.../<slug>/` dirs. The lane ledger (`lanes.json`,
  sibling of `leases.json` in the coordinator's state) records claims, lane branches, merge
  order, demotions, and parks — written via `lazy_core._atomic_write`. This restates the stub's
  single-writer constraint as the implementation invariant (also the user-level constitution's
  "one writer per file" orchestration rule).
- **Resolution:** RESOLVED — as shaped (contended-resource single-writer: ONLY the coordinator,
  at the main root, under `lazy_coord.acquire_lock`, after `verify_fencing`; `lanes.json` is the
  coordinator-owned ledger). *(operator-approved / locked 2026-07-04)*

### D8. Build-queue and long-build interaction on shared hosts

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** N lanes can trigger N concurrent heavy builds on one machine.
- **Recommendation / shape:** already solved twice over; cite, don't rebuild. (1) On Cognito-remote
  repos, `build-queue-enforce.sh` hook-denies raw heavy builds in any worktree and the skills
  route through `build-queue.ps1`, the machine-global FIFO — lanes are just more worktrees to it.
  (2) On AlgoBooth-class repos, `long-build-ownership-guard.sh` denies a subagent's exact
  long-build invocation with the `LONG-BUILD-OWNERSHIP-TAKEOVER` signature; in parallel mode the
  takeover bubbles to the coordinator, which runs Transient Builds (`run_transient_build` +
  `promote_artifact_atomically`) serialized in the parent session — one compiler at a time by
  construction. v1 adds no new build arbitration; retros watch for lane starvation under build
  contention as a vN signal.
- **Resolution:** RESOLVED — cite existing machinery (`build-queue.ps1` FIFO +
  `long-build-ownership-guard.sh` takeover), add none. *(operator-approved / locked 2026-07-04)*

### D9. Containment: unchanged hooks, armed per lane

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How do the containment guarantees extend to lane subagents?
- **Recommendation / shape:** Unchanged by constraint. Each lane dispatch is bracketed
  `--cycle-begin --repo-root <worktree> ... --cycle-end` (the coordinator exports
  `LAZY_ORCHESTRATOR=1` once, as the three orchestrators do at Step 0.55), so
  `lazy-cycle-containment.sh` arms against the lane's own state dir via
  `--marker-present --repo-root <cwd>`; C3 refuse-by-construction (orchestrator-only ops exit 3
  for subagents) applies verbatim inside lanes; `block-sentinel-write-on-stray-branch.sh` enforces
  each lane's `work_branch`. The coordinator is the ONLY new privileged actor (the stub's
  constraint), and its new ops (claim, merge, port, demote) are orchestrator-only, cycle-guarded
  like `--reorder-queue`. One genuinely new hardening surface: N cycle markers can be live in N
  state dirs simultaneously — the `--cycle-end` friction detector runs per lane against per-lane
  HEADs, which Phase 5 must fixture explicitly.
- **Resolution:** RESOLVED — containment hooks unchanged, armed per lane; ONE new obligation:
  per-lane `--cycle-end` friction-detector fixtures. *(operator-approved / locked 2026-07-04)*

### D10. Worktree pool generalization

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** `provision_pool(cognito_root, pool_dir, k)` and `scrub_slot(...)` are
  Cognito-parameterized (literal `cognito_root` arg; `p/<wi_id>-<slug>` PR branches).
- **Recommendation / shape:** rename the root param (`repo_root`) and parameterize the branch
  template — lanes use `lane/<item-id>` (the `p/...` convention stays `lazy-worker`/Cognito's PR
  discovery contract and must not be squatted). Pool location: a sibling dir
  `<repo_root>-lanes/wt-NN` (git-worktree-conventional; keeps worktrees out of the repo tree and
  out of `repo_key` ambiguity). `scrub_slot`'s exact ordered reset (index.lock removal → fetch
  under lock → `checkout --detach origin/main` → `reset --hard` → `clean -fdx` → branch) is reused
  as-is, except the detach target parameterizes to the run's base branch. `lazy_coord.py` stays
  stdlib-only and MUST NOT import `lazy_core` (its stated contract); the coordinator composes the
  two modules, they never import each other.
- **Resolution:** RESOLVED — rename `cognito_root` → `repo_root`; branch template parameterized
  (lanes use `lane/<item-id>`); pool location = sibling dir `<repo_root>-lanes/wt-NN`; detach
  target parameterizes to the run base branch; `lazy_coord.py` stays stdlib-only and MUST NOT
  import `lazy_core` (justified atomic-write duplication documented in-module). No behavioral
  change for existing callers (`lazy-worker` fixtures stay green — `lazy_coord.py --test`).
  *(operator-approved / locked 2026-07-04)*

## User Experience

**Invocation (D1 recommendation):**

```
/lazy-batch-parallel 24 --lanes 3
```

The coordinator prints a shard report before dispatching:

```
parallel run: parent marker armed (main root), budget 24 cycles
shardable (dep-ready + independent:true): feat-a, feat-b, feat-c, feat-e
lanes (3): wt-00 → feat-a (lane/feat-a) · wt-01 → feat-b (lane/feat-b) · wt-02 → feat-c (lane/feat-c)
held serial: feat-d (deps: [feat-a]) · feat-f (no independent marker)
```

**During the run** the operator watches the same surfaces as today, extended: `/lazy-status`
gains lane rows (read from the lane ledger + per-worktree probes); `LAZY_QUEUE.md` still
regenerates only at coordinator commits on the work branch. A parked lane shows as
`⬡ needs-input (lane parked)` without stopping siblings.

**End of run — flush report:**

```
merged (queue order): feat-a ✓ feat-b ✓
demoted to serial (merge conflict on src/mixer.rs): feat-c — lane branch lane/feat-c preserved;
  re-run serially this run (2 cycles remaining) — independent:true marker flagged for audit
parked: feat-e — NEEDS_INPUT.md ported to docs/features/feat-e/ (2 decisions)
budget: 19/24 cycles used (lanes 16, serial re-run 3)
```

**Failure modes the operator can trust:** a second `/lazy-batch` started mid-run is refused by
the parent marker exactly as today (exit 3, naming the in-flight run); killing the coordinator
leaves lanes reclaimable — lease TTLs expire, `reclaim_expired` scrubs slots on the next
invocation, and stale lane markers age out via the 24h staleness gate. No path requires hand
cleanup of `queue.json`.

## Technical Design

```
                    ┌── main root ~/.claude/state/<key(main)>/  parent run marker (owner-bound)
                    │        lanes.json + leases.json (fencing tokens)   [coordinator-owned]
  /lazy-batch-parallel (ONE parent session, LAZY_ORCHESTRATOR=1)
        │ claim under acquire_lock: shardable = dep-ready ∧ independent:true ∧ no live lease
        ├─ lane 0: <repo>-lanes/wt-00  branch lane/feat-a  state <key(wt-00)>: lane marker
        │          cycle subagents (contained; --feature-id feat-a; heartbeat lease)
        ├─ lane 1: <repo>-lanes/wt-01  branch lane/feat-b  state <key(wt-01)>: lane marker
        │              ...
        ▼ lane complete → verify_fencing → (wait for queue order) → merge to work branch
          under lock → conflict? abort + demote serial : proceed
        ▼ coordinator serial tail on work branch: /mcp-test → __mark_complete__
          (receipt + ROADMAP strike + queue trim) → LAZY_QUEUE.md regen → release lease → scrub slot
```

- **Claim step (coordinator, under `acquire_lock`):** `reclaim_expired` sweep → compute shardable
  set (queue `deps` all Complete-with-receipt — the `queue-dependency-dag` helpers — AND
  `parse_independent_marker` true AND no live lease) → `acquire_lease(leases_path, item_id, pid,
  slot, ttl)` per claim, capturing `term_token`. Then, outside the lock: `provision_pool` /
  `scrub_slot` the slot, `--run-start --repo-root <worktree> --session-id <coordinator>
  --max-cycles <slice>` to arm the lane (born owner-bound; `work_branch` = lane branch via the
  existing `_emit_work_branch`).
- **Lane execution:** the coordinator's per-lane loop mirrors the serial cycle loop against the
  lane root — probe (`--repeat-count --probe ... --repo-root <worktree> --feature-id <id>`),
  bracket (`--cycle-begin`/`--cycle-end`), dispatch one cycle subagent (background Agent), lease
  `heartbeat` each cycle (abort the lane on `FencingError` — the zombie-lane fail-safe). Lane
  terminal states: item reaches the validation gate (ready for the serial tail), sentinel (park,
  D5), budget slice exhausted (park as budget-deferred), or repeated-probe loop detection
  (existing machinery, per lane).
- **Merge + tail (coordinator, serialized):** queue-order merge with abort-and-demote (D4);
  serial tail runs `--ensure-runtime` once per validation cycle then the normal Step 9/10 path
  (`--gate-coverage`, `/mcp-test`, `--apply-pseudo __mark_complete__`) at the MAIN root — receipts
  land on the canonical tree; queue trim + ROADMAP strike stay inside `__mark_complete__` exactly
  as today.
- **House invariants honored:** script-owned deterministic state (shardability, leases, ledger,
  merges — all on-disk, no LLM inference anywhere in arbitration); `lazy_core._atomic_write` for
  every ledger/queue write, `lazy_coord`'s temp-file `os.replace` for leases; fail-OPEN hooks
  untouched; per-repo keyed state dirs are the isolation primitive (not worked around —
  leveraged); coupled-pair parity (a parallel bug-pipeline variant is vN — v1 is
  feature-pipeline-only, a justified divergence to document and parity-audit-annotate, since bug
  fixes are typically small/serial and the archive-on-fix terminal complicates lane tails);
  receipt-gated completion unchanged; stdlib-only Python throughout.
- **New/changed surfaces (all real, minimal):** `lazy_coord.py` param generalization (D10) + new
  `claim_shardable` helper; `lazy-state.py` lane-support flags reuse existing ones
  (`--repo-root`, `--feature-id`, `--session-id`, `--max-cycles`, `--run-start/--run-end`) — the
  only new marker content is the `parent_run` identity field; the new skill
  `user/skills/lazy-batch-parallel/SKILL.md` composing the existing components
  (`adhoc-enqueue.md`, `subagent-launch.md`, cycle-prompt emission).

## Implementation Phases

- **Phase 1 — Shardability + lane ledger (no worktrees yet).** `claim_shardable` predicate over
  the `queue-dependency-dag` readiness helpers + `parse_independent_marker` + live-lease check;
  `lanes.json` ledger schema + atomic writers; `lazy_coord.py --test` fixtures for claim/ledger
  (deterministic `now`). Proves: the coordinator can compute a correct, conservative shard set and
  record it, with zero effect on serial runs.
- **Phase 2 — Worktree lanes + lane markers.** D10 generalization of `provision_pool`/`scrub_slot`
  (Cognito callers unchanged); lane arm/disarm via `--run-start`/`--run-end --repo-root
  <worktree>`; `parent_run` marker field + continuity-partition classification; fixtures proving
  per-worktree `repo_key` isolation and that `refuse_run_start_clobber` still refuses rogue
  walkers at both the main root and inside a lane. Proves: N armed lanes, all existing arbitration
  green.
- **Phase 3 — Lane execution loop.** Per-lane probe/bracket/dispatch/heartbeat cycle; budget-slice
  accounting against the parent marker; `FencingError` abort path; containment verified in-lane
  (hook fixtures piped per lane state dir). Proves: two lanes progress concurrently under full
  enforcement on a real repo fixture.
- **Phase 4 — Merge + serial tail.** Queue-order merge under lock; abort-and-demote with lane
  branch preservation + ledger record; demoted serial re-run drawing from the parent budget;
  coordinator-owned validation tail + `__mark_complete__` at the main root; LAZY_QUEUE.md rides
  the coordinator commit. Proves: two clean lanes merge deterministically; a manufactured conflict
  demotes and re-runs serially; receipts/ROADMAP/queue all reconcile.
- **Phase 5 — Failure isolation + flush.** Park-on-sentinel (lane end, lease release, slot
  handling); sentinel port to the work branch at flush (hook-compatible); flush report (merged /
  demoted / parked / budget); per-lane friction-detector fixtures (D9's new obligation); terminal
  handling incl. coordinator-death recovery (TTL reclaim + stale lane markers). Proves: one lane's
  halt never stalls siblings and nothing is lost.
- **Phase 6 — Skill + docs + hardening.** `user/skills/lazy-batch-parallel/SKILL.md` (bookends,
  status output, flush shapes); `user/scripts/CLAUDE.md` concurrency-plane section + root
  `CLAUDE.md` updates; justified-divergence annotations in `lazy_parity_audit.py`; retro
  instrumentation (demotion + false-`independent` marker audit feed for `/lazy-batch-retro`).
  Full gate: `lazy_coord.py --test`, `lazy-state.py --test`, `bug-state.py --test`,
  `test_lazy_core.py`, parity audit.

Estimate: ~6 sessions (one per phase; Phases 4 and 5 are the risk-dense ones).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Serial byte-identity | Full `--test` suites with parallel mode never invoked | Pinned baselines unchanged | `tests/baselines/*.txt` |
| Conservative sharding | Queue with dep-chains + unmarked items | Only dep-ready ∧ `independent:true` items claimed; holds named | Shard report + `lanes.json` |
| Lane isolation | Two lanes armed | Distinct `repo_key` state dirs; distinct markers, both owner-bound to coordinator | State-dir fixture |
| Arbitration extended, not weakened | Rogue `--run-start` at main root and inside a lane, mid-run | Exit 3 both times, naming the in-flight run | CLI fixtures |
| Zombie lane fenced | Lease reclaimed, old lane attempts contended write | `FencingError` → abort, zero shared-state mutation | `lazy_coord` fixture |
| Containment in-lane | Lane subagent attempts orchestrator op / recursive `/lazy*` | Denied (exit 3 / hook deny) per existing signatures | Hook-pipe + CLI fixtures |
| Deterministic merge | Lanes finish out of queue order | Work-branch history in queue order across repeated runs | Git log fixture |
| Conflict demotes | Manufactured overlapping edit in two lanes | Merge aborted; item demoted; lane branch preserved; serial re-run succeeds; marker flagged in flush | Ledger + git + flush report |
| Failure isolation | One lane writes NEEDS_INPUT.md | Siblings complete; item parked; sentinel ported to work branch; hooks allow the port | Flush + on-disk sentinel |
| Budget ceiling | Aggregate lane cycles reach `max_cycles` | No further claims/dispatches; flush accounts every cycle | Parent marker + report |
| Single-writer trio | Full run | Every `queue.json`/ROADMAP/LAZY_QUEUE.md write is coordinator-at-main-root under lock | Ledger audit + git blame of run commits |
| Coordinator death recovery | Kill coordinator mid-run; re-invoke later | TTL reclaim scrubs slots; stale lane markers age out; no manual queue repair needed | Reclaim fixture + live check |
| Heavy-build serialization | Lane triggers an exact long-build token | `LONG-BUILD-OWNERSHIP-TAKEOVER` deny; coordinator runs it serially | Hook fixture + session log |

## KPI Declaration

Existing registry row (`docs/kpi/registry.json`) — `pipeline-efficiency` system:

- kpi: cycles-per-completion

**Honesty note on fit:** this feature's currency is explicitly the forward-cycle budget, not a
wall-clock timer — D6 makes the operator-authorized `max_cycles` the aggregate SSOT and every
lane cycle, merge, and demoted re-run debits the SAME parent budget (Technical Design; D6). A
parallel wave that lands N independent items by sharing the coordinator's one claim/merge/tail
overhead across them, instead of each item paying its own serial overhead in turn, should show up
as a lower `cycles-per-completion` for the run — that is the nearest existing lens on this
feature's orchestration-efficiency effect. It does NOT directly measure wall-clock speedup (no
signal source in this repo captures wall-clock parallelism today), and a demotion-heavy run
(false-`independent` markers, D4) would blunt or reverse the improvement — which is itself the
correct, honest signal that lane sharding is mis-tuned. A dedicated lane-throughput /
demotion-rate metric is a documented vN gap (`/lazy-batch-retro`'s Step 6f demotion audit feed is
today's qualitative substitute; see "Concurrency plane" in `user/scripts/CLAUDE.md`), not drafted
here because its selector would need new computation wiring this feature has no remaining phase
to carry.

## Open Questions

None remaining — D1–D5 were resolved at their recommended options and D6–D10 locked as shaped by
the operator on 2026-07-04 (see each decision's **Resolution** line above).

- **Deferred empirical checks (implementation-time, not decisions):** confirm distinct
  `repo_key(worktree)` values on Windows (realpath vs 8.3/`subst` aliases — the keying is
  normalization-invariant but worktrees were not its original fixture set); measure worktree
  provision/scrub cost on NTFS to size `pool_size` defaults; confirm concurrent background Agent
  dispatch limits per session for the lane loop; verify the `--cycle-end` friction detector's
  per-lane HEAD snapshots never cross-trip between lanes (estimated — verify during Phase 3/5);
  confirm `git worktree` index.lock contention under three concurrent lanes is fully absorbed by
  `scrub_slot`'s retry + fetch-under-lock discipline.

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the in-repo `lazy_coord` lease/fencing plane and the two
  archived arbitration bugs; external merge-queue practice (bors-style serialize-integration) and
  fencing-token literature for the zombie-writer model.
- `docs/features/queue-dependency-dag/SPEC.md` — the hard dependency: the readiness predicate the
  shard step consumes.
- `docs/bugs/_archive/concurrent-same-branch-walkers-no-arbitration/SPEC.md` and
  `docs/bugs/_archive/single-slot-marker-ownership-race-disarms-owning-run/SPEC.md` — the
  arbitration/ownership contracts this feature extends; the former explicitly names
  "`lazy-worker` + `lazy_coord.py`, not `/lazy-batch` on a shared branch" as the sanctioned path
  to intentional parallelism this SPEC now builds.
- `user/skills/lazy-worker/SKILL.md` — the claim/heartbeat/finalize-under-lock worker contract
  generalized here.
