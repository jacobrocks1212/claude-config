---
name: lazy-batch-parallel
description: Sanctioned parallel-worktree coordinator for the feature pipeline — shards independent queue items across worktree lanes, merges lane branches in queue order, runs the validation tail serially. Concurrency contract in SKILL.md.
argument-hint: <max-cycles, e.g. 24> [--lanes <N, default 2>] [--park] [--park-provisional] [--adhoc "<task>"]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch Parallel — Sanctioned Worktree-Lane Coordinator

ONE parent session that shards **dependency-independent, `independent: true`-marked** feature
queue items across **git worktree lanes** and coordinates them to completion. Lanes do the
parallel-safe front half (spec → research-gate → phases → plan → implement) inside their own
checkout, branch, and per-worktree keyed state dir; everything contended — the queue-order merge
to the work branch, MCP validation against the singleton runtime, `__mark_complete__`
(receipt + ROADMAP strike + queue trim), `LAZY_QUEUE.md` regeneration — is coordinator-owned and
serialized under the `lazy_coord` global lock, after `verify_fencing` per item.

**Workstation-only v1** (claude-config + AlgoBooth — repos that work on and push `main`-based
work branches). Cloud is vN. This skill COMPOSES the `/lazy-batch` contract rather than editing
it: the serial orchestrators stay frozen; a serial run remains byte-identical whenever this mode
is not invoked.

**Composition, not reimplementation:** state inference is exclusively `lazy-state.py`
(per lane via `--repo-root <worktree> --feature-id <id>`); concurrency primitives are exclusively
`~/.claude/scripts/lazy_coord.py` (lock, fencing leases, worktree pool, `lanes.json` ledger);
independence booleans come from `lazy_core`'s deterministic reads. The two modules never import
each other — this coordinator is the composition point.

---

## HARD CONSTRAINTS (non-negotiable; additive to the /lazy-batch set)

**All ten `/lazy-batch` HARD CONSTRAINTS apply verbatim to the coordinator** (sentinel-only
Write/Edit scope, no direct Skill invocation, no manual state parsing, one dispatch per cycle,
resolution-mode-scoped `AskUserQuestion`, monotonic counters, dispatch-only-probed-features,
stop-authorization). Read `~/.claude/skills/lazy-batch/SKILL.md`'s HARD CONSTRAINTS block at run
start. The parallel mode ADDS:

P1. **Single-writer trio (D7).** `docs/features/queue.json`, `docs/features/ROADMAP.md`,
    `LAZY_QUEUE.md`, and the work branch are written ONLY by the coordinator, ONLY at the main
    root, ONLY under `lazy_coord.acquire_lock`, and ONLY after `lazy_coord.verify_fencing` for
    the item concerned. Lanes NEVER invoke `--apply-pseudo __mark_complete__`/`__mark_fixed__`,
    never touch their worktree copies of the trio, and exclusively own their disjoint
    `docs/features/<slug>/` dirs.

P2. **One parent marker; lanes are sanctioned children.** The coordinator arms ONE parent run
    marker at the main root (`--run-start --session-id <this session>` — the existing
    `refuse_run_start_clobber` protects the whole construction). Each lane marker is armed at
    its WORKTREE root, born owner-bound to the SAME coordinator session, stamped
    `--parent-run '{"repo_root": <main root>, "started_at": <parent marker started_at>}'`, and
    carries its per-lane budget slice as `--max-cycles`. No arbitration rule is bypassed or
    weakened — every existing invariant applies verbatim per lane root.

P3. **Fencing before every contended write.** The coordinator captures each claim's
    `term_token` and calls `verify_fencing(leases_path, item_id, term_token)` immediately before
    ANY contended write for that item (merge, demotion record, serial tail, queue trim). A
    `FencingError` means this coordinator is a zombie for that item: abort the item's action,
    record it, never write.

P4. **Budget SSOT (D6).** The parent `max_cycles` is the aggregate ceiling: every lane cycle
    AND every demoted serial re-run cycle debits it. Effective lanes =
    `min(requested N, shardable count, pool_size)`; each lane's marker slice =
    `min(remaining_parent, ceil(max_cycles / lanes))` (`lazy_coord.lane_budget_slice`). Total
    dispatched cycles across all lanes never exceed the operator-authorized `max_cycles`.

P5. **Deterministic queue-order merge; conflict demotes (D4).** Completed lane branches merge
    to the work branch in QUEUE order (`lazy_coord.merge_order` — never completion order),
    coordinator-only, under the lock. A merge conflict ⇒ `git merge --abort` (the helper
    `merge_lane_branch` does this), `demoted: serial` in the ledger, lane branch PRESERVED, and
    the item re-runs serially after the wave on the up-to-date work branch. A demotion is also a
    marker-audit finding: the item's `independent: true` marker was wrong — surface it in the
    flush.

P6. **Park isolates (D5).** A lane halting on `BLOCKED.md`/`NEEDS_INPUT.md` parks: record it,
    end the lane's marker, release its lease, KEEP the lane branch + worktree; siblings
    continue. The sentinel is ported VERBATIM to the canonical `docs/features/<slug>/` at
    end-of-run flush, under the lock, on the work branch (satisfying both sentinel hooks — the
    port is a copy of a pipeline-written sentinel onto the marker's own `work_branch`).

P7. **Containment unchanged, armed per lane (D9).** Export `LAZY_ORCHESTRATOR=1` once (Step
    0.55) and carry it on every lifecycle/routing call. Every lane dispatch is bracketed
    `--cycle-begin --repo-root <worktree> … --cycle-end` so the containment hooks arm against
    the lane's own state dir; C3 refuse-by-construction applies verbatim inside lanes. Heavy
    builds: existing machinery only (D8) — a lane's `LONG-BUILD-OWNERSHIP-TAKEOVER` deny bubbles
    to the coordinator, which runs the build serially under the Transient Build contract.

P8. **Concurrent-writer awareness — no monsters-in-the-closet serialization.** Lanes ARE
    other agents committing to shared state (the trio + the work branch at merge time)
    concurrently with each other and with any outside session touching the same worktree/branch.
    An unexpected incoming commit / moved HEAD is EXPECTED, not a defect to panic on or halt for.
    Genuine write contention is resolved by the coordination layer (git safety + the FIFO
    file-lock + conflict-routing) — not by pre-serializing lane dispatches on the mere
    possibility of a collision.

---

## Step 0: Parse Arguments

`$ARGUMENTS` tokens: positive integer → `max_cycles` (default 10); `--lanes <N>` → requested
lane count (default 2; `< 1` → refuse); `--park` → park mode for the DEMOTED-serial phase and
resolution modes (lanes ALWAYS park-on-sentinel per P6 — that is the parallel mode's defining
failure isolation, not an opt-in); `--park-provisional` → provisional acceptance (park-provisional-acceptance, SPEC D10; requires `--park`): the coordinator passes
`--park-provisional` through to EVERY lane probe (with the lane's `--repo-root <worktree>`),
so an eligible `NEEDS_INPUT.md` routes `__provisional_accept__` INSIDE the lane — a
pipeline-advancing lane cycle (docs-only writes in the lane's own `docs/features/<slug>/`,
committed on the lane branch; P1 disjoint ownership holds; P6 park is unchanged for
everything else, and the acceptance is a probe ROUTE, not a sentinel halt, so P6 never fires
for it). The `NEEDS_INPUT_PROVISIONAL.md` + `## Resolution` ride the queue-order merge to the
work branch; the serial tail can VALIDATE the feature but `__mark_complete__` stays
mechanically blocked until ratification — the coordinator's flush (Step 6) surfaces the
ratification affordance (`provisional-ratification.md`) at the main root exactly like other
parked sentinels; `--adhoc "<task>"` → Step 0.45. Unknown tokens are an error
(same shape as `/lazy-batch`).

Initialize: `forward_cycles = 0`, `meta_cycles = 0` (monotonic, HARD CONSTRAINT 8), `cycle_log
= []`, and the lane table (empty until Step 1). Read
`~/.claude/skills/_components/orchestrator-voice.md` and
`~/.claude/skills/_components/completeness-policy.md` at run start (and re-read after any
compaction boundary), exactly as `/lazy-batch` does.

Paths used throughout (all coordinator state lives in the MAIN root's keyed state dir):

```bash
STATE_DIR=$(python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/scripts'); import lazy_core; lazy_core.set_active_repo_root('<main root>'); print(lazy_core.claude_state_dir())")
LEASES="$STATE_DIR/leases.json"     # fencing leases (lazy_coord)
LANES="$STATE_DIR/lanes.json"       # lane ledger (lazy_coord, coordinator-owned)
POOL=<main root>-lanes              # worktree pool (lazy_coord.lane_pool_dir)
```

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

## Step 0.55: Environment + parent marker (IMMEDIATELY before the shard report)

Run the `/lazy-batch` Step 0.0 preflight component first (`lazy-preflight.md`, read-only, STOP
on failure). Then:

```bash
export LAZY_ORCHESTRATOR=1     # C3 self-immunity — carried by every lifecycle/routing call
python3 ~/.claude/scripts/lazy-state.py --run-start --repo-root <main root> \
  --session-id <this session id> --max-cycles <max_cycles>
```

A refusal (exit 3) means another run is live in this repo — report it verbatim and STOP (the
same-repo second-walker protection covers the whole parallel construction). Record the echoed
marker's `started_at` — it is the `parent_run.started_at` every lane marker carries.

---

## Step 1: Claim (coordinator, under the global lock)

ONE deterministic Bash step — no LLM judgment anywhere in arbitration. Run the canonical
composition snippet (lazy_core supplies the readiness/independence booleans; lazy_coord owns the
lease check + the claim):

```bash
python3 - <<'PY'
import json, os, sys
sys.path.insert(0, os.path.expanduser("~/.claude/scripts"))
import importlib.util
def load(name, fn):
    spec = importlib.util.spec_from_file_location(
        name, os.path.expanduser(f"~/.claude/scripts/{fn}"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
lazy_core = load("lazy_core", "lazy_core.py")
lazy_coord = load("lazy_coord", "lazy_coord.py")

MAIN = "<main root>"; LEASES = "<STATE_DIR>/leases.json"
lazy_core.set_active_repo_root(MAIN)
queue = json.load(open(f"{MAIN}/docs/features/queue.json"))["queue"]
id_dir_map = {e["id"]: f"{MAIN}/docs/features/{e.get('spec_dir', e['id'])}" for e in queue}
candidates = []
for e in queue:
    spec_md = os.path.join(id_dir_map[e["id"]], "SPEC.md")
    spec_text = open(spec_md, encoding="utf-8").read() if os.path.exists(spec_md) else ""
    dep_ready = all(
        lazy_core.dep_completion_status(d, __import__("pathlib").Path(MAIN),
                                        pipeline="feature", id_dir_map=id_dir_map) == "complete"
        for d in lazy_core.dep_ids(e))
    candidates.append({"id": e["id"], "dep_ready": dep_ready,
                       "independent": lazy_core.parse_independent_marker(spec_text, e)})

# reclaim_expired + acquire_lease are SELF-LOCKING (each takes global.lock.d
# INTERNALLY via a non-reentrant os.mkdir lock); claim_shardable is a lock-free
# READ. Do NOT wrap them in an outer acquire_lock — the inner mkdir would fail on
# the dir this process already holds and TimeoutError after 10s (self-deadlock,
# lazy-batch-parallel-run-harness-gaps gap 2). The primitives are individually
# atomic; acquire_lease re-checks liveness under its own lock and returns None on
# a double-claim, so the sequence is safe without an outer hold.
lazy_coord.reclaim_expired(LEASES, "<POOL>")             # dead-lane sweep (self-locks)
print(json.dumps(lazy_coord.claim_shardable(candidates, LEASES)))  # lock-free read
PY
```

`claimed` (queue order) is the shard set; `held` names every hold (`dep-unready` /
`no-independent-marker` / `live-lease`). Effective lanes =
`lazy_coord.effective_lanes(requested, len(claimed), pool_size)`; truncate `claimed` to that
count — the remainder stays queued for the serial phase / a later wave. Take ONE
`acquire_lease(LEASES, item_id, pid, slot, ttl)` per claimed item (each call self-locks — do
NOT hold an outer lock across them), capturing each `term_token`, and
`ledger_record_claim(LANES, item_id, slot, lane_branch)`.

Print the **shard report** (T6 zone):

```
parallel run: parent marker armed (main root), budget {max_cycles} cycles
shardable (dep-ready + independent:true): {claimed ids, comma-separated}
lanes ({N}): wt-00 → {id-a} (lane/{id-a}) · wt-01 → {id-b} (lane/{id-b}) …
held serial: {id} ({hold reason}) · …
```

Zero shardable items → release the parent marker path is NOT taken; instead print the report
with `lanes (0)` and fall through to Step 5 (the run degrades to plain serial `/lazy-batch`
behavior for whatever the queue holds — never a silent stop).

## Step 2: Provision + arm lanes (outside the lock)

Per claimed item, in queue order:

```bash
# Worktree slot (idempotent) + scrub to the run's base branch with the lane branch template:
python3 -c "…lazy_coord…; lazy_coord.provision_pool('<main root>', '<POOL>', <N>)"
python3 -c "…lazy_coord…; lazy_coord.scrub_slot('<main root>', '<POOL>', '<slot>', '<item-id>',
            '<item-id>', branch_template='lane/{wi_id}', detach_target='<base branch>')"
# Lane marker — born owner-bound to THIS session, parent-stamped, budget-sliced:
python3 ~/.claude/scripts/lazy-state.py --run-start --repo-root "<POOL>/<slot>" \
  --session-id <this session id> \
  --max-cycles <lane_budget_slice(remaining_parent, max_cycles, lanes)> \
  --parent-run '{"repo_root": "<main root>", "started_at": "<parent started_at>"}'
```

Each lane resolves its OWN `repo_key` state dir — marker, prompt registry, deny ledger, cycle
marker, telemetry ledger all per lane, for free.

## Step 3: Lane execution loop

Mirror the `/lazy-batch` Step 1 cycle loop PER LANE, against the lane root. For each lane with
budget remaining (round-robin; a background `Agent` dispatch per lane may run concurrently —
lane subagents follow the `/lazy-batch` cycle-subagent execution model exactly, including the
workstation dispatch policy (workstation-recursive-subagent-dispatch, 2026-07-09): a lane cycle
subagent MAY dispatch sub-subagents per the emitted prompt's "WORKSTATION DISPATCH —
LOAD-BEARING" guardrails; sub-subagents inherit the terminal-stop ban and work only inside the
lane's worktree + item scope, so the fencing/lease/single-writer-trio model is unaffected).
**Concurrent-writer awareness:** other agents may be working this same worktree/branch
concurrently — an unexpected commit / moved HEAD is expected, not a defect. Genuine write
contention is resolved by the coordination layer (git safety + the FIFO file-lock +
conflict-routing) — not by halting:

1. **Probe:** `lazy-state.py --repeat-count --probe --repo-root <worktree> --feature-id <id>
   [--forward-cycles/--meta-cycles/--max-cycles from the LANE's counters]`.
2. **Route:**
   - real sub-skill / pipeline-advancing pseudo-skill through implementation → bracket
     (`--cycle-begin --repo-root <worktree> --feature-id <id> …`), dispatch ONE cycle subagent
     into the worktree (compose via `--emit-prompt`/`lazy-dispatch-template.md` exactly as
     `/lazy-batch` Step 1d; the prompt's cwd and every path is the LANE root), then
     `--cycle-end --repo-root <worktree>` on every return path. Debit the parent budget
     (`forward_cycles += 1` or `meta_cycles += 1` — same classifier as `/lazy-batch`).
   - `terminal_reason ∈ {needs-input, blocked}` → **PARK (P6):**
     `ledger_record_park(LANES, id, sentinel_kind)`, `--run-end --repo-root <worktree>
     --reason terminal --terminal-reason <reason>`, `release_lease`, KEEP branch + worktree,
     print the T5 park line `⬡ {id} parked (lane) — {sentinel}`. The freed slot MAY claim the
     next ready item (re-run Step 1's claim for one item) if parent budget remains.
   - item reaches the MCP gate / mark-complete route (`mcp-test`,
     `__write_validated_from_skip__`, `__mark_complete__`, …) → **STOP the lane** (the tail is
     coordinator-owned): `ledger_record_lane_complete(LANES, id)`, `--run-end --repo-root
     <worktree>` (clean lane retirement; the lease is HELD until the item's tail finishes).
   - lane slice exhausted → park as budget-deferred (ledger `parked`, `sentinel_kind:
     budget-deferred`), release lease, keep branch.
3. **Heartbeat:** `heartbeat(LEASES, id, term_token)` once per lane cycle. `FencingError` →
   abort the lane immediately (zombie fail-safe): no further dispatches, no writes; record in
   the ledger and the flush.

Repeated-probe loop detection, denial recovery, and the deny-ledger hardening debt all run
per lane exactly as in `/lazy-batch` (same machinery, lane-scoped state dirs).

## Step 4: Queue-order merge + serial tail (coordinator, at the main root)

When lanes settle (all `lane-complete`/`parked`/aborted), merge in QUEUE order — never
completion order:

```
for item in merge_order(read_lanes(LANES), queue ids):
    verify_fencing(LEASES, item, term_token)            # P3 — before ANY contended write
    acquire_lock(lock)
    try:
        res = merge_lane_branch("<main root>", "lane/<item>")   # --no-ff, abort-on-conflict
        if res.merged: ledger_record_merge(LANES, item)
        else:          ledger_record_demotion(LANES, item, res.detail)   # branch preserved
    finally: release_lock(lock)
```

Then, per MERGED item, the serial tail at the main root (existing machinery, one item at a
time): `--ensure-runtime` (once per validation cycle; route on the verdict exactly as
`/lazy-batch` Step 1d.0) → `/mcp-test` cycle dispatch (or the skip/defer pseudo-skill the probe
returns) → `--gate-coverage` → `--apply-pseudo __mark_complete__` (receipt + ROADMAP strike +
queue trim, exactly as today) → `python3 ~/.claude/scripts/lazy-queue-doc.py --repo-root <main
root>` riding the coordinator commit → `release_lease` → `scrub_slot` the freed slot. Tail
cycles debit the parent budget.

> **`--ensure-runtime` is FOREGROUND-ONLY (round-2 gap 9).** The tail's `--ensure-runtime` call
> is a FOREGROUND, blocking `Bash` call — NEVER `run_in_background`. It owns its own background
> `dev:restart` + a synchronous multi-minute health poll; backgrounding it under the active
> parent marker lets the recovery `dev:restart` → `kill-dev.js` sweep kill the background
> launcher's own process tree (observed: two instant zero-byte kills). See
> `user/scripts/CLAUDE.md` → `--ensure-runtime` FOREGROUND-ONLY CONTRACT.

> **Serial-tail `--emit-prompt` is lease-exempt from the merged-head guard (round-2 gap 8).** The
> tail's `--emit-prompt --feature-id <merged item>` runs at the MAIN root against the PARENT
> marker (`parent_run: null`), so the round-1 lane exemption does NOT apply. Because the probed
> item still holds its LIVE lease until `release_lease` (below), `lazy-state.py` exempts it from
> the `merged-head-diverged` withhold — completing the merged, lease-held item is the
> coordinator's obligation before any new head work, so a freshly-dispatchable merged head does
> NOT redirect the tail away from it. This is automatic (keyed on the item's own live lease); the
> coordinator does nothing special beyond keeping the lease held across the validation cycle.

## Step 5: Demoted serial re-runs

For each `demoted: serial` item, in queue order, while parent budget remains: run ordinary
serial cycles at the MAIN root (`lazy-state.py --feature-id <item>` probe → dispatch →
bracket), on the now-merged work branch — fresh cycles see merged reality. Demoted re-runs draw
from the SAME parent budget (P4; no hidden growth). Items held at Step 1 (`held serial`) are
NOT run here — they remain queued for the next serial/parallel invocation unless the operator
asked otherwise.

## Step 6: Flush + run end

Under the lock, on the work branch, at the main root:

1. **Port parked sentinels (P6):** for each ledger-`parked` item with a sentinel, copy the
   lane's `NEEDS_INPUT.md`/`BLOCKED.md` VERBATIM into canonical `docs/features/<slug>/`
   (`ledger_record_park`'s `ported_to` updated), commit. The next serial run and the read-only
   surfaces (LAZY_QUEUE.md "Needs attention", visualizer, `/lazy-status`) now see it.
2. **Flush report** (T6/T7 zone; groups from `lazy_coord.flush_summary(read_lanes(LANES))`):

```
merged (queue order): {ids ✓ …}
demoted to serial ({reason}): {id} — lane branch lane/{id} preserved; re-run {outcome}
  — independent:true marker flagged for audit
parked: {id} — {sentinel} ported to docs/features/{id}/ ({summary})
budget: {used}/{max_cycles} cycles used (lanes {n}, tail {n}, serial re-run {n})
```

3. The full §1c.6 end-of-run flush at the MAIN root, composed from `/lazy-batch` by reference —
   `incident-scan.py`, then `efficacy-eval.py --repo-root . --json`, then the harness-change canary
   watch `efficacy-eval.py --canary --repo-root . --json` (harness-change-canary-rollback D6-A;
   fail-open, NON-BLOCKING — a non-zero exit prints one warning and run-end continues; stage
   `docs/interventions/` + any `docs/bugs/canary-revert-*` seed in the run-end commit) — then
   `lazy-state.py --run-end --repo-root <main root> --reason terminal --terminal-reason
   <reason>` for the parent marker. Leases for finished items are already released; a crash
   before this point is recoverable by construction (TTL reclaim + stale lane markers age out —
   no manual queue repair).

---

## Differences from /lazy-batch (the coupling table)

| Surface | /lazy-batch (serial) | /lazy-batch-parallel |
|---|---|---|
| Run markers | one, at the repo root | one PARENT at the main root + one per-worktree lane marker per claimed item (owner-bound to the same session; `parent_run` stamped; `max_cycles` = budget slice) |
| Claim arbitration | none (queue head) | `claim_shardable` (dep-ready ∧ `independent:true` ∧ no live lease) + `acquire_lease` fencing token per item |
| Cycle loop | one loop | one loop PER LANE (same bracket/dispatch/recovery machinery, lane-scoped) + lease heartbeat |
| needs-input / blocked | Step 1g/1h resolution modes (or `--park`) | lanes ALWAYS park (P6); the coordinator's own serial phases keep the `/lazy-batch` resolution modes |
| Merge to work branch | n/a (work happens on it) | queue-order `merge_lane_branch` under lock; conflict ⇒ demote serial, branch preserved |
| Validation + completion | inline in the loop | coordinator-owned serial tail at the main root, after merge |
| Contended writes | orchestrator-inline | ONLY under `acquire_lock` + after `verify_fencing` (P1/P3) |
| Budget | `max_cycles` | same SSOT, debited by lane cycles + tail + demoted re-runs; per-lane marker slices (P4) |

**State machine summary:** claim → provision/arm lanes → lane loops (probe → bracket →
dispatch → heartbeat; park on sentinel; stop at the MCP gate) → queue-order merge
(abort-and-demote) → serial tail per merged item (`--ensure-runtime` → `/mcp-test` →
`__mark_complete__` → LAZY_QUEUE regen) → demoted serial re-runs → flush (sentinel port +
report) → parent `--run-end`. All shard/merge/park/budget state is on-disk
(`lanes.json` / `leases.json` / lane markers) — never conversational memory.
