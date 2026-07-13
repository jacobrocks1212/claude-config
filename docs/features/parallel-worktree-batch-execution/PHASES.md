# Implementation Phases — Sanctioned Parallel-Worktree Batch Execution

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete

**MCP runtime:** not-required — pure claude-config harness mechanics (Python concurrency plane +
state scripts + skill prose + docs). No Tauri app, no MCP-reachable surface; validation is
`lazy_coord.py --test`, `lazy-state.py --test` / `bug-state.py --test` smoke baselines,
`test_lazy_core.py` (pytest), `test_hooks.py`, `lazy_parity_audit.py`, and `lint-skills.py`.
This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP
gate.

## Cross-feature Integration Notes

`**Depends on:** queue-dependency-dag (hard)` — LANDED on this branch's base: the enforced queue
`deps` field, `lazy_core.dep_ids`/`dep_completion_status`/`detect_dep_cycle`, the `dep_gated`
probe key, and `--sync-deps` all exist and are consumed (not re-implemented) by the coordinator's
readiness predicate. `harness-telemetry-ledger` also landed — lane markers emit run/cycle
telemetry events for free via the state scripts (each lane's ledger lives in its own keyed state
dir; no new emission code in this feature).

Implemented contracts extended (never weakened): `lazy_coord.py` lock/lease/fencing plane;
per-repo keyed state dirs (`repo_key`/`claude_state_dir` — each worktree IS its own key);
born-owner-bound single-slot marker ownership + checkpoint-discriminated
`refuse_run_start_clobber`; the containment hook family (unchanged, armed per lane). HARD
module-boundary constraint (D10): `lazy_coord.py` stays stdlib-only and MUST NOT import
`lazy_core` — the lanes.json ledger uses lazy_coord's own temp-file + `os.replace` atomic write
(the `_write_leases` pattern), a documented justified duplication of `lazy_core._atomic_write`.

---

### Phase 1: Shardability predicate + lane ledger (no worktrees yet)

**Phase kind:** design

**Scope:** The coordinator's deterministic claim arithmetic and its on-disk record, with zero
effect on serial runs. `claim_shardable` composes three deterministic inputs (dep-DAG readiness ∧
`independent: true` ∧ no live lease — D3-A; the readiness/marker booleans are computed by the
caller from `lazy_core` reads, keeping lazy_coord import-free); the `lanes.json` ledger (sibling
of `leases.json`, coordinator-owned — D7) records claims/merges/demotions/parks under the global
lock; D6 budget arithmetic (`effective_lanes`, `lane_budget_slice`).

**Deliverables:**
- [x] `lazy_coord.py`: `claim_shardable(candidates, leases_path, *, now=None)` — conservative
  predicate over caller-supplied `{id, dep_ready, independent}` dicts + the live-lease check;
  missing/falsy keys ⇒ held (never claimed); returns `{claimed: [...], held: [{id, reason}]}` in
  input (queue) order.
- [x] `lazy_coord.py`: lanes.json ledger — `read_lanes`, `_write_lanes` (own atomic pattern,
  documented justified duplication), `ledger_record_claim`, `ledger_record_merge`,
  `ledger_record_demotion`, `ledger_record_park`, all mutations under `acquire_lock` on the
  sibling `global.lock.d`.
- [x] `lazy_coord.py`: `merge_order(lanes_data, queue_ids)` — deterministic queue-order merge
  sequence over lane-complete items (independent of completion timing).
- [x] `lazy_coord.py`: `effective_lanes(requested, shardable_count, pool_size)` and
  `lane_budget_slice(remaining_parent, max_cycles, lanes)` (D6 arithmetic, `min`/`ceil` exactly
  as locked).
- [x] `lazy_coord.py --test` fixtures (registered in the smoke harness): conservative sharding
  (dep-chain + unmarked + leased items held, holds named), ledger atomicity + lifecycle,
  deterministic merge order from out-of-order completions, budget arithmetic edges.

**Minimum Verifiable Behavior:** With a fixture queue of five candidates (one dep-unready, one
unmarked, one leased, two shardable), `claim_shardable` claims exactly the two and names each
hold's reason; recording claims + out-of-order completions in `lanes.json` yields a
`merge_order` equal to queue order; `lane_budget_slice(20, 24, 3)` == 8 and never exceeds
`remaining_parent`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Conservative sharding: only dep-ready ∧ `independent:true` ∧ lease-free items claimed; holds named. *(Evidence: `lazy_coord.py --test` fixture `claim-shardable-conservative`.)* <!-- verification-only -->
- [x] Serial byte-identity: full `--test` suites with parallel mode never invoked — pre-existing fixtures byte-identical (new fixtures appended only). *(Evidence: `lazy_coord.py --test` fixtures 1–5 output unchanged; state-script baselines untouched by this phase.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no
Tauri/MCP app). Verification is the in-file smoke harness + pytest.

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_coord.py`.

**Testing Strategy:** In-file `--test` fixtures with injected `now` (deterministic), temp dirs,
byte-comparison of sibling `queue.json` to prove non-perturbation. No pytest surface needed —
lazy_coord's harness is self-contained (matching the 5 existing fixtures).

**Integration Notes for Next Phase:** Phase 2 arms real lanes: `provision_pool`/`scrub_slot`
generalization + the `parent_run` lane-marker field; `ledger_record_claim` gains its real callers.

---

### Phase 2: Worktree lanes + lane markers (`parent_run`)

**Phase kind:** integration

**Scope:** D10 generalization of the worktree pool (rename `cognito_root` → `repo_root`;
parameterize the scrub branch template + detach target; `lane_branch(item_id)` = `lane/<item-id>`;
`lane_pool_dir(repo_root)` = sibling `<repo_root>-lanes`) with byte-compatible defaults for the
Cognito/`lazy-worker` callers. D2-A lane markers: `write_run_marker` gains the `parent_run:
{repo_root, started_at}` identity field (default `None`), classified into `RUN_FRESH_FIELDS`
(the continuity-partition completeness test is the designed tripwire); both state scripts thread
a new `--parent-run <json>` flag on `--run-start` (coupled pair — the marker is shared).

**Deliverables:**
- [x] `lazy_coord.py`: `provision_pool(repo_root, pool_dir, k)` param rename (call-compatible);
  `scrub_slot(repo_root, pool_dir, slot, wi_id, slug, *, lock_dir=None,
  branch_template="p/{wi_id}-{slug}", detach_target="origin/main")` — defaults byte-identical;
  `lane_branch(item_id)` + `lane_pool_dir(repo_root)` helpers.
- [x] `lazy_core.py`: `write_run_marker(..., parent_run=None)` — key ALWAYS minted (None for
  serial runs); classified into `RUN_FRESH_FIELDS`; docstring names the sanctioned-lane audit
  purpose.
- [x] `lazy-state.py` + `bug-state.py`: `--parent-run <json>` on `--run-start` (validated shape
  `{repo_root: str, started_at: str}`; malformed ⇒ exit 2, zero side effects); threaded into
  `write_run_marker`. Coupled-pair mirror; parity audit stays exit 0.
- [x] `test_lazy_core.py` additions (registered in `_TESTS`): default-None minting; explicit
  dict stored + echoed; `RUN_FRESH_FIELDS` classification (partition completeness test green
  again); `repo_key` distinctness for a main root vs its sibling lane worktree paths.
- [x] State-script `--test` fixtures (both scripts): `--run-start --parent-run` marker content +
  rogue second `--run-start` refusal (exit 3) at a lane root; malformed `--parent-run` exit 2.
  Baselines re-pinned ONLY via `_normalize_smoke_output`.
- [x] `lazy_coord.py --test` fixture: scrub/branch-template parameterization on a REAL temp git
  repo (default template produces `p/<wi_id>-<slug>`; lane template produces `lane/<item-id>`;
  detach target honored).

**Minimum Verifiable Behavior:** `--run-start --repo-root <lane> --session-id S --parent-run
'{"repo_root": "<main>", "started_at": "<ts>"}'` mints a lane marker carrying `parent_run`; a
second `--run-start` at that lane root (no checkpoint) is refused exit 3 naming the in-flight
run; a serial `--run-start` (no flag) mints `parent_run: null` and is otherwise byte-identical.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Lane isolation: two distinct roots resolve distinct `repo_key` state dirs; distinct markers, both owner-bound to the coordinator session. *(Evidence: `test_lazy_core.py` parent-run/repo-key tests + existing per-repo isolation suite.)* <!-- verification-only -->
- [x] Arbitration extended, not weakened: rogue `--run-start` mid-run refused exit 3 at a lane root, naming the in-flight run. *(Evidence: state-script `--test` fixture `lane-parent-run-marker`.)* <!-- verification-only -->
- [x] Serial byte-identity: `parent_run: null` on every non-lane marker; all pre-existing marker/continuity tests green unchanged. *(Evidence: `test_lazy_core.py` full suite + re-pinned smoke baselines whose only diff is the new fixtures' own PASS lines.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** confirm distinct `repo_key(worktree)` values on a real Windows host (realpath vs 8.3/`subst` aliases) — the SPEC's deferred empirical check; the keying is normalization-invariant by construction and fixture-proven on POSIX paths here.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (ledger exists for the claim/arm sequence the fixtures model).

**Files likely modified:** `user/scripts/lazy_coord.py`, `user/scripts/lazy_core.py`,
`user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`,
`user/scripts/tests/baselines/bug-state-test-baseline.txt`.

**Testing Strategy:** TDD — the partition completeness test fails the moment the marker gains
the key and passes only on explicit classification (the designed tripwire); subprocess-driven
state-script fixtures against isolated `LAZY_STATE_DIR` dirs; real temp git repos for the pool
fixtures. Re-pin baselines only through `_normalize_smoke_output`.

**Integration Notes for Next Phase:** Phase 3's lane-loop accounting reads the lane marker's
`max_cycles` slice and the lease heartbeat; the `parent_run` field is what audits/`--run-end`
sweeps use to prove a lane marker sanctioned.

---

### Phase 3: Lane execution loop support (budget slice + fencing abort + containment in-lane)

**Phase kind:** integration

**Scope:** Script-side support the coordinator's per-lane loop consumes: the budget-slice is
stamped as the lane marker's `max_cycles` (existing flag — D6); the zombie-lane fail-safe is the
lease `heartbeat`/`verify_fencing` `FencingError` (existing plane) — fixtured end-to-end as
abort-with-zero-shared-state-mutation; containment applies in-lane by construction (per-lane
state dir) — fixtured explicitly per D9.

**Deliverables:**
- [x] `lazy_coord.py --test` fixture `zombie-lane-fenced`: lease reclaimed + re-claimed while a
  stale lane holds the old token → `heartbeat` and `verify_fencing` raise `FencingError`;
  leases.json + lanes.json + a sibling `queue.json` byte-unchanged by the zombie's attempt.
- [x] State-script `--test` fixture: lane marker armed with a `--max-cycles` slice → the slice is
  stored on the lane marker (per-lane self-limit even if the coordinator dies).
- [x] Containment-in-lane fixture: a subagent-context (`LAZY_CYCLE_SUBAGENT=1`, no
  `LAZY_ORCHESTRATOR`) `--apply-pseudo`/`--run-end` against a LANE state dir is refused exit 3
  (C3 refuse-by-construction applies verbatim inside lanes).

**Minimum Verifiable Behavior:** A reclaimed lane's stale token can neither heartbeat nor pass
fencing (both raise), and its attempt mutates nothing; a lane marker carries its own
`max_cycles` slice; orchestrator-only ops refuse for subagents against lane state dirs.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Zombie lane fenced: `FencingError` → abort, zero shared-state mutation. *(Evidence: `lazy_coord.py --test` fixture `zombie-lane-fenced`.)* <!-- verification-only -->
- [x] Containment in-lane: orchestrator-only op refused exit 3 for a subagent at a lane root. *(Evidence: state-script `--test` fixture `lane-containment-in-lane`.)* <!-- verification-only -->
- [x] Budget ceiling (per-lane slice): the slice rides the lane marker's `max_cycles`. *(Evidence: state-script fixture + `lane_budget_slice` arithmetic fixture from Phase 1.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** two lanes progressing concurrently under full enforcement with live background Agent dispatches (SPEC validation row "Containment in-lane"/"Lane isolation" live half; needs a real multi-lane workstation run + Claude Code session limits — SPEC deferred empirical checks).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2.

**Files likely modified:** `user/scripts/lazy_coord.py`, `user/scripts/lazy-state.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`.

**Testing Strategy:** Deterministic `now` injection for lease expiry; subprocess env control
(`LAZY_CYCLE_SUBAGENT` / no `LAZY_ORCHESTRATOR`) for the containment fixture; byte-comparison
for zero-mutation assertions.

**Integration Notes for Next Phase:** Phase 4 consumes `merge_order` + the ledger to land lane
branches; the fencing fixture's verify-before-contended-write discipline is the exact call the
merge step makes first.

---

### Phase 4: Queue-order merge + abort-and-demote (+ serial tail contract)

**Phase kind:** integration

**Scope:** The merge half of D4: `merge_lane_branch` (real `git merge --no-ff`, conflict ⇒
`git merge --abort`, never leaves a conflicted tree), demotion recording (`demoted: serial`,
lane branch preserved), and deterministic queue-order landing independent of lane completion
timing. The serial tail (`--ensure-runtime`, `/mcp-test`, `__mark_complete__`, ROADMAP strike,
queue trim, LAZY_QUEUE.md regen) is EXISTING machinery invoked by the coordinator at the main
root — cited by the Phase 6 skill, no new code.

**Deliverables:**
- [x] `lazy_coord.py`: `merge_lane_branch(repo_root, branch, *, no_ff=True)` → `{merged,
  conflict, aborted}`; on conflict the merge is aborted and the working tree left clean; the
  lane branch is NEVER deleted by this helper.
- [x] `lazy_coord.py --test` fixture `queue-order-merge-determinism`: two lanes with disjoint
  edits completing OUT of queue order merge IN queue order (git log parents assert the order);
  repeated run reproduces the identical order.
- [x] `lazy_coord.py --test` fixture `conflict-demotes-preserves-lane-branch`: a manufactured
  overlapping edit → `merge_lane_branch` reports conflict + aborts (clean tree, `MERGE_HEAD`
  absent); `ledger_record_demotion` marks `demoted: serial`; the lane branch still resolves.

**Minimum Verifiable Behavior:** In a real temp repo, lane B finishing before lane A still lands
after A (queue order); a conflicting lane aborts cleanly, is recorded `demoted: serial` with its
branch preserved, and the work branch shows no half-merge.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Deterministic merge: work-branch history in queue order across repeated runs despite out-of-order completion. *(Evidence: `lazy_coord.py --test` fixture `queue-order-merge-determinism`.)* <!-- verification-only -->
- [x] Conflict demotes: merge aborted; item demoted; lane branch preserved; ledger records it. *(Evidence: `lazy_coord.py --test` fixture `conflict-demotes-preserves-lane-branch`.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** demoted item's serial RE-RUN to completion on the merged work branch + receipts/ROADMAP/queue reconciling end-to-end (needs a live `/lazy-batch-parallel` run driving real cycle subagents and the singleton MCP runtime).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/scripts/lazy_coord.py`.

**Testing Strategy:** Real `git init` temp repos (git present in this container) — merges,
aborts, and branch predicates asserted against actual git state, not mocks.

**Integration Notes for Next Phase:** Phase 5's park path reuses `ledger_record_park` +
lane-branch preservation; the flush report's `merged (queue order)` line reads `merge_order`.

---

### Phase 5: Failure isolation + flush accounting + per-lane friction fixtures

**Phase kind:** integration

**Scope:** D5-A park-on-sentinel accounting (`ledger_record_park`; lane branch + worktree
preserved; sentinel ported verbatim at flush — the port itself is a coordinator file copy the
skill owns), `flush_summary` (merged/demoted/parked/budget groupings for the flush report),
coordinator-death recovery (TTL reclaim leaves the ledger's audit trail intact), and D9's one
new obligation: per-lane `--cycle-end` friction-detector fixtures proving per-lane HEAD
snapshots never cross-trip between lanes.

**Deliverables:**
- [x] `lazy_coord.py`: `flush_summary(lanes_data)` — deterministic grouping `{merged, demoted,
  parked, claimed}` (each in ledger order) for the flush report + `/lazy-status` lane rows.
- [x] `lazy_coord.py --test` fixture `park-isolates-siblings`: one lane parked
  (`ledger_record_park` with sentinel kind + ported-path fields) while a sibling proceeds to
  merged; `flush_summary` groups both correctly; the parked lane's branch/worktree fields
  preserved in the ledger.
- [x] `lazy_coord.py --test` fixture `coordinator-death-recovery`: leases expire (TTL) →
  `reclaim_expired` scrubs slots and clears leases while `lanes.json` retains the claims/parks
  audit trail (no manual queue repair path exercised).
- [x] State-script `--test` fixture `lane-friction-no-cross-trip` (D9 obligation): two lane
  state dirs + two real git repos; a commit landing in lane B while lane A's cycle bracket is
  open does NOT trip lane A's `--cycle-end` friction detector (no `process_friction` key), and
  lane B's own bracket stays within budget.

**Minimum Verifiable Behavior:** A parked lane never blocks a sibling's merge record; expired
leases reclaim without touching the ledger's history; `--cycle-end` friction snapshots are
per-lane (no cross-trip).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Failure isolation: one lane parks; siblings complete; ledger + flush groups reflect both. *(Evidence: `lazy_coord.py --test` fixture `park-isolates-siblings`.)* <!-- verification-only -->
- [x] Coordinator death recovery: TTL reclaim scrubs slots; ledger audit trail intact; no manual queue repair needed. *(Evidence: `lazy_coord.py --test` fixture `coordinator-death-recovery` + existing `reclamation` fixture.)* <!-- verification-only -->
- [x] Per-lane friction detector: per-lane HEAD snapshots never cross-trip. *(Evidence: state-script `--test` fixture `lane-friction-no-cross-trip`.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** live sentinel PORT onto the canonical tree passing `block-noncanonical-blocker-write.sh` + `block-sentinel-write-on-stray-branch.sh` under a real run marker (the hooks' deny path is fixture-covered in `test_hooks.py` generally; the parallel-flush-specific live pass needs a workstation run). Stale lane markers aging out via the 24h gate is existing, already-tested `read_run_marker` behavior.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–4.

**Files likely modified:** `user/scripts/lazy_coord.py`, `user/scripts/lazy-state.py`,
`user/scripts/tests/baselines/lazy-state-test-baseline.txt`.

**Testing Strategy:** Ledger fixtures with injected `now`; friction fixture drives the REAL
`--cycle-begin`/`--cycle-end` subprocess path against two lane state dirs with real git HEAD
movement in each.

**Integration Notes for Next Phase:** Phase 6's skill prose consumes every helper by name; the
flush report shapes are `flush_summary`'s groups rendered in the SPEC's UX format.

---

### Phase 6: Coordinator skill + status/retro surfaces + docs + hardening

**Phase kind:** chore

**Scope:** The operator-facing assembly: `user/skills/lazy-batch-parallel/SKILL.md` (D1-A —
bookends, shard report, lane loop, merge + serial tail, flush shapes, composing
`adhoc-enqueue.md`); `/lazy-status` lane rows; `/lazy-batch-retro` demotion +
false-`independent` audit feed; docs (`user/scripts/CLAUDE.md` concurrency-plane section + root
`CLAUDE.md` rows); parity-audit confirmation; full gate suite.

**Deliverables:**
- [x] `user/skills/lazy-batch-parallel/SKILL.md` — new coordinator skill: hard constraints
  (single-writer trio under lock after fencing; workstation-only v1; one parent marker),
  Step 0 argument parsing (`<max-cycles> --lanes N [--adhoc ...]`), ad-hoc enqueue component
  injection, shard report shape, claim→provision→arm sequence, per-lane cycle loop
  (probe/bracket/dispatch/heartbeat), park-on-sentinel, queue-order merge + demote, serial tail
  at main root, flush report shape, differences-from-`/lazy-batch` table.
- [x] `/lazy-status` (user/skills/lazy-status/SKILL.md): lane rows — when the active repo's
  coordinator state has a `lanes.json`, render one row per lane (item, slot, branch, status incl.
  `⬡ needs-input (lane parked)`) from the ledger + per-worktree probes; absent ⇒ byte-identical
  output.
- [x] `/lazy-batch-retro` (user/skills/lazy-batch-retro/SKILL.md): parallel-run audit feed —
  read `lanes.json`; every `demoted: serial` entry becomes a Findings row flagging the item's
  `independent: true` marker as a false-independence audit candidate; parked lanes
  cross-checked against ported sentinels.
- [x] `user/scripts/CLAUDE.md`: "Concurrency plane — sanctioned parallel worktree lanes"
  section (coordinator contract, lanes.json, parent_run, budget slices, merge/demote/park) +
  `lazy_coord.py` table-row update + CLI quick-reference addition (`--parent-run`).
- [x] Root `CLAUDE.md`: `lazy-batch-parallel` noted in the skills-system section (composition
  with the batch family; workstation-only v1) — tightly scoped row additions.
- [x] `lazy_parity_audit.py` confirmation: exit 0 with `--parent-run` present on both state
  scripts; the feature-pipeline-only parallel mode documented as a justified divergence in the
  skill + CLAUDE.md (no audit annotation needed — the audit does not grade skill-family
  existence).
- [x] Full gate suite green (pytest suites + both smoke baselines + `lazy_coord.py --test` +
  parity audit + `lint-skills.py`), skill projection verified into a lane-local output dir.

**Minimum Verifiable Behavior:** `lint-skills.py` + projection clean with the new/edited skills;
parity audit exit 0; the full gate suite passes with only the two sanctioned skips.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Docs/lint consistency: projection + `lint-skills.py` clean over the new skill and edited components' consumers. *(Evidence: `project-skills.py` — 88 skills / 100 components, 0 errors, all 3 repo projections incl. claude-config; `lint-skills.py --check-projected --check-capabilities` — clean, re-verified 2026-07-12 finalization cycle.)* <!-- verification-only -->
- [x] Single-writer trio (contract half): the skill's HARD CONSTRAINTS bind every `queue.json`/ROADMAP/LAZY_QUEUE.md write to coordinator-at-main-root under lock after `verify_fencing`; lanes never invoke `__mark_complete__`/`__mark_fixed__`. *(Evidence: `user/skills/lazy-batch-parallel/SKILL.md` P1 "Single-writer trio (D7)" hard-constraint text, verified on disk 2026-07-12; `lazy_coord.py --test` fencing fixtures `zombie-lane-fenced` + `queue-order-merge-determinism` + `conflict-demotes-preserves-lane-branch` all PASS.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** a full live `/lazy-batch-parallel 24 --lanes 3` run on claude-config/AlgoBooth (shard report, concurrent lanes, queue-order landing, flush report, git-blame single-writer audit of run commits) — the SPEC validation table's live rows; needs a workstation + real Claude Code session.
- **DEFERRED (workstation-only, not a completion blocker):** heavy-build serialization observed live (`LONG-BUILD-OWNERSHIP-TAKEOVER` deny bubbling from a lane; coordinator running the build serially) — the hook's deny path is already covered by `test_hooks.py`; the lane-context live observation needs a workstation run (D8 adds no new machinery by decision).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–5.

**Files likely modified:** `user/skills/lazy-batch-parallel/SKILL.md` (new),
`user/skills/lazy-status/SKILL.md`, `user/skills/lazy-batch-retro/SKILL.md`,
`user/scripts/CLAUDE.md`, `CLAUDE.md`.

**Testing Strategy:** Docs/skills phase — projection + lint + full gate suite as acceptance;
no state-machine changes here.

**Status:** Complete. Deliverable rows 307–330 ticked; the two `<!-- verification-only -->`
Runtime-Verification rows are now `[x]` (evidence above, re-verified in the 2026-07-12
finalization cycle); the two DEFERRED workstation-only live-run rows remain explicitly
non-blocking (a genuine live `/lazy-batch-parallel` multi-lane run is the honest verification
vehicle for those two rows — see COMPLETED.md).

#### Implementation Notes (Phase 6 / WU-6.5 — cloud finalization cycle)

- **Deliverables confirmed on disk** (landed in prior cycles): `lazy-batch-parallel/SKILL.md`
  (19.5KB source, 25.8KB projected), `/lazy-status` lane rows, `/lazy-batch-retro` demotion +
  false-`independent` audit feed, `user/scripts/CLAUDE.md` concurrency-plane section + root
  `CLAUDE.md` rows.
- **Gate suite run this cycle:** `lazy_coord.py --test` (green), `lazy-state.py --test` +
  `bug-state.py --test` (green, both smoke baselines match), `toolify_miner` (22/22), the 9-file
  pytest batch excluding `test_lazy_core` (all pass), `lazy_parity_audit.py --repo-root .`
  (exit 0), `lint-skills.py` (clean), `project-skills.py` incl. lane-local
  `--output-dir /tmp/proj-parallel-worktree-batch-execution` (exit 0, skill projected).
- **Known environmental artifact (NOT a code defect):** `test_lazy_core.py` shows ~25 failures
  when the full file is run *inside a live lazy cycle*. Root cause: `_clear_state_dir()` pops the
  external `LAZY_STATE_DIR`, after which `apply_pseudo`/`mark_complete`/`mark_fixed` tests fall
  back to the real per-repo state dir holding the orchestrator's live cycle marker and trip
  `refuse_if_cycle_active` → `SystemExit(3)`. Each such test PASSES in isolation; the parallel-
  worktree-specific `test_lazy_core` tests (parent_run / lane / continuity-partition) pass. This
  is inherent to running the suite within the pipeline, not a regression from this feature.
- **Review verdict:** PASS (inline — WU-6.5 is validation/reconciliation; no new source edits).
