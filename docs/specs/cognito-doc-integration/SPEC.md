# Cognito Doc Integration — Feature Specification

> Generalize the file-driven `/lazy` pipeline to source its work queue from Azure DevOps work items via a deterministic local mirror kept fresh out-of-band, add a cross-source work dashboard (including teammates), run **parallel implementation across a persistent pool of git worktrees driven by independent worker sessions**, and extend the orchestrator to shepherd GitHub PRs — keeping SPEC.md/PHASES.md as the canonical input format and preserving halt-for-genuine-decisions.

**Status:** Final
**Priority:** P1
**Last updated:** 2026-06-02

**Depends on:** (none)

<!-- This feature *composes* the lazy family engine (user/scripts/lazy-state.py, bug-state.py) and
     the Cognito-forms ADO/GH integration commands (/work-item, /review-pr). Neither is represented
     as a spec'd feature directory under docs/specs/, so there is no parseable feature-id to depend
     on. Recorded as (none) per dep-block schema; coupling is documented in Technical Design
     § "Composed substrate". -->

---

## Executive Summary

The `/lazy` family is a file-driven autonomous pipeline: `lazy-state.py` (features) and
`bug-state.py` (bugs) compute the next action purely from on-disk bytes — `queue.json` plus
per-item `SPEC.md`/`PHASES.md`/sentinels — never from conversational memory. This feature extends
*where the queue comes from* and *how many items advance at once*: it sources work from **Azure
DevOps work items** (assigned to the user and their team) through a deterministic local mirror kept
fresh out-of-band, and it runs **implementation in parallel across a persistent pool of git
worktrees** consumed by **independent worker sessions** — all on a single Windows workstation.

Four layers:

1. **Deterministic ADO sync** — a headless poller mirrors the WI set to a read-only on-disk file via
   scheduled WIQL polling against a `System.ChangedDate` high-watermark (verbatim copy, no inference).
2. **Work dashboard** — `/work-status`, a read-only cross-source view: my mirrored WIs, queued items
   + live lazy state, which worker/worktree owns each in-flight item, teammates' WIs, linked GH PRs.
3. **Materialization + orchestration** — a discrete, logged, idempotent step turns a selected WI into
   the canonical doc conventions (`ADHOC_BRIEF.md` + stub `SPEC.md`, or a bug spec), auto-routed by WI
   type, and hands it to `/lazy`.
4. **Parallel execution** — multiple independent worker sessions pull implement-ready items from the
   shared queue, each claiming a crash-safe **lease** (+ fencing token) and a **persistent worktree
   pool slot**, running implement→PR concurrently while every short state transition is serialized by
   a single atomic **mkdir-lock**.

The north star: Claude semi-autonomously works through ADO work items assigned to the user —
materializing docs, planning, implementing **several at once**, opening GitHub PRs, triggering
reviews/fixes — halting only for genuine decisions, exactly as `/lazy-batch` already halts on
`BLOCKED.md` / `NEEDS_INPUT.md` / `needs-research`.

### The determinism contract (load-bearing)

The **sync, materialize, and dashboard** layers are inference-free pure transforms of on-disk/API
bytes. *All* judgment lives inside the dispatched skills (`/spec`, `/fix`, …), which already gate
ambiguity via `NEEDS_INPUT.md`/`BLOCKED.md`/`needs-research`. Parallelism does not relax this:
concurrent workers run only the *implement* step in isolation; every shared-state mutation happens
under one lock, and a fencing token prevents a revived "zombie" worker from corrupting the queue —
so "next action = pure f(on-disk bytes)" holds with N workers. (Research: `RESEARCH.md`.)

## Locked Decisions

**Round 1 — foundation:** (1) Hybrid topology — generic engine in `claude-config` user-level,
Cognito wiring in `repos/cognito-forms/.claude/`. (2) Scheduled + on-demand poll. (3) v1 = mirror +
dashboard + WI→doc materialization + parallel implement; PR shepherding deferred. (4) GitHub is the
PR system of record (provider seam keeps ADO Repos re-addable).

**Round 2 — queue & surfaces:** (5) Read-only mirror + explicit materialization. (6) Auto-route by
WI type (Bug→bugs, Story/Task/PBI→features). (7) Teammate scope = dashboard read-only. (8) Dashboard
= terminal skill `/work-status`.

**Round 3 — integration mechanics:** (9) WI↔PR link — see Round 5 revision. (10) Thin deterministic
copy at materialization. (11) Headless poller auth = ADO PAT. (12) Mirror scope = configurable WIQL
query (`@Me OR AreaPath UNDER <team>`).

**Round 4 — parallel execution:** (13) Multiple independent worker sessions (worker pool), no single
orchestrator. (14) Shared canonical `docs/` state; worktrees code-only. (15) Fan out at
implement→PR; front half lock-serialized. (16) Persistent worktree pool with scrub-on-reuse.

**Round 5 — post-research finalization (this spec):**
17. **Execution environment — Native Windows PowerShell.** The pipeline runs natively on Windows
    (reusing the `create-branch-worktree.ps1` pattern); the Python state machine + coordination run on
    NTFS. This deliberately **avoids the WSL2/DrvFs boundary** that research flags as the danger zone
    for file locks and file-mode churn.
18. **Coordination state location — In-repo `docs/work/` (NTFS) with an `os.mkdir()` atomic lock.**
    Keeps state co-located, git-tracked, and consistent with the lazy `docs/` convention. `mkdir` is
    atomic on NTFS (and ext4), so it is the safe primitive here — **never** `fcntl`/`flock`/`LockFileEx`.
19. **WI↔PR link — Branch-name primary with the team `p/` prefix.** Convention `p/AB<id>-<slug>`,
    parsed by local regex `^p/AB(\d+)-` — fully deterministic, no API, works even if the Azure
    Boards–GitHub app is disconnected. PR bodies still include `Resolves AB#<id>` for ADO's benefit;
    `AB#`/HierarchyQuery resolution is a Phase 5 enrichment, not a v1 dependency.
20. **Upstream divergence — `STALE_UPSTREAM.md` sentinel + halt-at-next-gate.** If a materialized
    item's `ChangedDate` advances upstream, never clobber `SPEC.md`; diff, drop the sentinel, finish
    the current atomic step, then halt at the next natural lifecycle gate for a human absorb/reject.
21. **Secret storage — Windows Credential Manager via `keyring`** (DPAPI-encrypted); PAT scoped to
    **`vso.work` (Work Items – Read) only**.

## User Experience

### Surfaces (v1)

- **`/work-status`** — read-only cross-source dashboard:
  - *My queue* — items in the feature/bug queues + live lazy state (current step, blockers, sentinels).
  - *In flight* — leased items with `worker_pid`, worktree slot, stage, lease health (heartbeat age).
  - *My ADO inbox* — mirrored WIs assigned to me, **not yet materialized** (type/state/linked PR).
  - *Team* — teammates' WIs + linked GH PR states (read-only).
  - *Pool & sync health* — worktree-slot occupancy, mirror `syncedAt`/staleness, last poll result,
    any `STALE_UPSTREAM.md` flags.
- **`/materialize-wi <WI_ID>`** — thin-copies the WI into the right pipeline (auto-routed by type),
  enqueues via `--enqueue-adhoc`, stamps `Resolves AB#<id>` + URL into doc frontmatter, marks it in
  `materialized.json`. Batchable (`--all-mine`, type/area filters) for autonomous runs.
- **Worker session** — `/lazy-worker` (working name) run in 1..K terminals. Each loop: claim an
  actionable item under the lock; for an implement-ready item, claim a worktree slot, scrub it,
  implement → open a GitHub PR on a `p/AB<id>-<slug>` branch; release lease + slot.

### Primary workflow

1. Scheduled poller keeps `docs/work/ado-mirror.json` fresh.
2. `/work-status` shows inbox + queue + in-flight + team in one view.
3. Materialize one or more WIs (auto-routed). They enter the queues as ad-hoc items.
4. Launch K workers. The front half (spec→research→phases→plan) advances lock-serialized, halting via
   `NEEDS_INPUT.md` for genuine decisions. As items reach implement, workers fan out across the
   worktree pool, implementing concurrently and opening GH PRs.
5. If an upstream WI changes mid-flight, a `STALE_UPSTREAM.md` sentinel halts that item at its next
   gate for a human absorb/reject; other items continue.
6. `/work-status` shows each in-flight item, its worktree, stage, and (once open) its linked PR + CI.

### Deferred workflow (Phase 5)

7. PR shepherding: poll GH PR state (`gh pr view --json statusCheckRollup,reviews`); on
   changes-requested/CI-fail, route feedback to `FEEDBACK.md` and transition `wait_on_pr → implement`;
   **merge stays human-gated**; **never auto-reply to PR comments** (honors `user/CLAUDE.local.md`).
   On merge, the worktree slot is scrubbed and returned to the pool.

## Technical Design

### Composed substrate (not modified destructively)

- **`user/scripts/lazy-state.py` / `bug-state.py`** — file-driven state machines. This feature feeds
  their queues and adds a **`--feature-id` scoping flag** (so a worker advances *its leased item*;
  absent the flag, behavior is byte-identical to today — single-current). Coupling rule from
  `user/scripts/CLAUDE.md` applies; new `--test` fixtures cover the scoped + leased paths.
- **`enqueue_adhoc()`** — reused verbatim by materialization.
- **Cognito `/work-item`, `/review-pr`, `create-branch-worktree.ps1`, `review-pr.ps1`** — existing
  ADO-MCP + PowerShell worktree primitives that the worker, pool, and shepherding layers build on.

### Layer 1 — Deterministic ADO sync

- **Engine:** `user/scripts/ado-sync.py` (project-agnostic). Auth = PAT via `keyring`
  (`keyring.get_password("ado-local-poller", "vso_pat_readonly")`), scope **`vso.work` read-only**.
- **WIQL (delta):** `SELECT … FROM workitems WHERE (AssignedTo = @Me OR AreaPath UNDER 'Project\Team')
  AND ChangedDate >= '<lastSync-UTC>Z' ORDER BY ChangedDate ASC`. Dates **must** be UTC + `Z`.
- **Pagination (critical):** the WIQL endpoint returns ≤20,000 ids, but hydration
  (`wit/workitems?ids=…&$expand=all`) is capped at **200 ids/batch** — the poller **chunks ids into
  ≤200** or hits HTTP 400.
- **Output:** writes `docs/work/ado-mirror.json` **atomically** (`os.replace` of a temp file). The
  high-watermark (max `ChangedDate` seen) persists so the next poll is incremental + crash-recovering.
- **Schedule:** Windows Task Scheduler runs `ado-sync.py` every N min, headless. In-session, the
  worker / `/work-status` may refresh on-demand via the **ADO MCP** against the same schema.
- **Mirror schema:** `syncedAt`, `watermark`, `query` identity, `workItems[]` of `{id, type, title,
  state, assignedTo, areaPath, iteration, url, acceptanceCriteria, description, changedDate,
  linkedPRs[], materialized}`.

### Layer 2 — Work dashboard

- **Engine:** `user/scripts/work-status.py` reads `ado-mirror.json`, both `queue.json`s,
  `materialized.json`, `leases.json`, scans for `STALE_UPSTREAM.md`, and calls
  `lazy-state.py`/`bug-state.py` for live per-item status. Emits JSON the skill formats.
- **Skill:** `user/skills/work-status/SKILL.md` — read-only terminal render; optional `--markdown`
  writes `docs/work/DASHBOARD.md`. No mutation of any artifact.

### Layer 3 — Materialization + orchestration

- **Materialize** (`lazy-state.py --materialize-wi <id>` or sibling): resolve WI in the mirror,
  **auto-route by `type`**, thin-copy title/description/acceptance verbatim into `ADHOC_BRIEF.md`,
  seed a stub `SPEC.md` carrying `**Work Item:** AB#<id> (<url>)`, call `enqueue_adhoc()`, append
  `{wi_id → feature_id, materialized_changedDate}` to `materialized.json`. Deterministic + idempotent.
- **Orchestration:** unchanged front-half `/lazy`, now invokable per item via `--feature-id`. The
  branch is `p/AB<id>-<slug>`; the PR body includes `Resolves AB#<id>`.
- **Upstream-divergence check:** on each sync/probe, for every materialized item compare mirror
  `changedDate` to the recorded `materialized_changedDate`; if newer, write `STALE_UPSTREAM.md`
  (sentinel; body = the field-level diff). The state machine finishes the current atomic step, then
  halts the item at its next gate for a human absorb/reject; absorb re-copies into `SPEC.md` and
  updates the recorded watermark.

### Layer 4 — Parallel execution (the concurrency plane)

- **Coordination files (`docs/work/`, all mutated only under the global lock):** `queue.json`,
  `leases.json`, `materialized.json`. Reads use atomic-rename so the dashboard never sees torn JSON.
- **Global lock = `os.mkdir("docs/work/global.lock.d")`.** Atomic on NTFS + ext4. Acquire = mkdir
  succeeds; `FileExistsError` = held, yield + retry. **Never** `fcntl`/`flock` (broken over DrvFs) or
  `LockFileEx` (not WSL-portable). Held only for sub-second transitions.
- **Lease schema (`leases.json`):** `{ "<wi_id>": { worker_pid, worktree_slot, term_token,
  heartbeat_timestamp, ttl_seconds } }`.
  - *Acquire:* under lock → reclaim expired leases (`heartbeat + ttl < now`, scrub their slots) →
    claim a free slot → **increment `term_token` (fencing)** → write pid + timestamp → release lock.
  - *Heartbeat:* a worker thread every `ttl/3` asserts the lock, verifies its `term_token`, refreshes
    `heartbeat_timestamp`.
  - *Fencing:* before **every** `queue.json` state transition, the worker re-asserts the lock and
    verifies its `term_token` still matches — a revived zombie whose lease expired fails this and
    cannot corrupt the queue.
- **Worktree pool:** K persistent worktrees (`scratch/pool/wt-01..wt-NN`) sized to max-parallel.
  **Git concurrency defenses (mandatory):** `git config gc.auto 0` at repo root; **serialize all
  network ref ops (`fetch`/`push`) under the global lock** (prevents `packed-refs` corruption);
  exponential backoff/retry on `index.lock` contention; `core.filemode false`, `core.autocrlf input`.
- **Deterministic scrub-to-clean (on slot reuse, ordered):**
  1. `rm -f .git/worktrees/<slot>/index.lock` (clear phantom locks from crashed runs)
  2. (under global lock) `git fetch origin`
  3. `git checkout --detach origin/main` → `git reset --hard origin/main`
  4. `git clean -fdx`
  5. submodules (if any): `git submodule update --init --recursive --force`; `foreach reset --hard`;
     `foreach clean -fdx`
  6. `git checkout -b p/AB<id>-<slug>`
- **Worker loop:** acquire lock → reclaim expired → pick highest-priority actionable item w/o live
  lease (front-half step *or* implement-ready) → lease it (+ slot if implementing) → release lock →
  do the work (front-half = short, in-lock model; implement→PR = long, in the leased worktree, with
  heartbeat) → acquire lock → flip state (fencing-checked), drop lease, free+flag-scrub slot, update
  `materialized.json` → release lock. Crash safety via heartbeat TTL.

### Cross-machine deployment

Authored in `claude-config`; deployed to the Windows work machine via `manifest.psd1` + `setup.ps1`.
Generic engine under `~/.claude/`; Cognito config + the worktree-pool scratch dir under the work repo.

## Implementation Phases

- **Phase 1 — Deterministic ADO sync.** `ado-sync.py` (keyring auth, WIQL delta watermark, 200-id
  chunked hydration, atomic write) + mirror schema + WIQL/cadence config + Task Scheduler setup +
  `--test` fixtures (incl. chunking + watermark recovery).
- **Phase 2 — Work dashboard.** `work-status.py` + `/work-status` skill (inbox / queue+state /
  in-flight / team / pool+sync health / stale flags). Read-only.
- **Phase 3 — WI→doc materialization.** Auto-route by type, thin copy, `enqueue_adhoc` reuse, AB#
  stamp, `materialized.json` idempotency, `STALE_UPSTREAM.md` divergence detection + gate. Hand-off
  verified into `/lazy`.
- **Phase 4 — Parallel execution.** `--feature-id` scoping in the state machines; mkdir-lock +
  `leases.json` (fencing token, heartbeat, reclamation); persistent worktree pool + scrub protocol +
  git concurrency config; `/lazy-worker` wrapper; concurrency cap. `--test` fixtures for scoped +
  leased + reclamation paths.
- **Phase 5 (deferred) — PR shepherding + autonomous loop + teammate guards.** `gh`-based provider
  module, PR-state polling, `FEEDBACK.md` → `implement` transition, `AB#`/HierarchyQuery enrichment,
  provider seam, teammate guardrails, human-gated merge.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Mirror is deterministic | Run `ado-sync.py` twice on unchanged ADO state | Byte-identical mirror (modulo `syncedAt`) | `ado-mirror.json` |
| Delta watermark recovers after downtime | Skip several polls, then run | One poll fetches all accumulated changes in final state | mirror vs ADO |
| Hydration chunking | Sync a WI set > 200 | Ids sliced into ≤200/batch; no HTTP 400 | poller logs |
| No inference at materialize boundary | Materialize a WI | Brief is a verbatim subset of WI fields | diff brief vs mirror |
| Auto-route by type | Materialize a Bug and a Story | Bug→`docs/bugs/…`, Story→`docs/features/…` | doc paths + queues |
| Idempotent materialization | Materialize same WI twice | Second run no-ops | `materialized.json`, queue length |
| Stale-upstream gate | Edit a materialized WI upstream | `STALE_UPSTREAM.md` written; item halts at next gate, SPEC.md untouched | item dir, dashboard |
| No double-claim under contention | K workers on a small ready set | Each item leased by exactly one worker; no shared-file corruption | `leases.json`, git status |
| Fencing prevents zombie writes | Force a lease to expire, revive the worker | Stale `term_token` fails the transition; queue uncorrupted | `leases.json`, queue.json |
| mkdir-lock mutual exclusion | Concurrent transitions | Exactly one holder at a time; others retry | lock dir presence |
| Worktree isolation + scrub | Reuse a slot for a second item | Slot starts clean from `origin/main`; no leftovers | per-slot `git status` |
| gc disabled | Inspect repo config | `gc.auto = 0` | `git config` |
| Branch-name link parse | Open PR on `p/AB1234-…` | Dashboard links PR↔WI via regex (no API) | `/work-status` |
| `--feature-id` preserves default | Run with/without the flag | Without = single-current baseline; with = scoped item | `--test` |
| Determinism end-to-end | Materialize → parallel `/lazy-worker` | Judgment surfaces via NEEDS_INPUT/BLOCKED only | sentinels |

## Open Questions

- **PAT mint** (verify at work machine) — confirm a `vso.work` read-only PAT can be created; else
  `az`/MCP-only fallback for the headless poller.
- **Azure Boards–GitHub app** (verify) — only gates the Phase 5 `AB#` enrichment; v1 link path
  (branch-name) is independent.
- **Branch slug shape** — confirm `p/AB<id>-<kebab-title>` matches team convention exactly (prefix
  `p/` is fixed; id-embedding is for deterministic parsing).
- **Pool size K / lease TTL / heartbeat** defaults — recommend K≈3–4; TTL ≈ a few × the longest
  expected implement step; heartbeat `ttl/3`.
- **Submodule presence** in the Cognito repo (determines whether the scrub's submodule steps run).
- **`/work-item` reconciliation** — does the new materialize+worker path supersede the existing
  `/work-item` command, or coexist? (Recommend: `/work-item` becomes a thin manual alias over
  materialize.)

## Research References

`RESEARCH.md` (full report) and `RESEARCH_SUMMARY.md` (synthesis). Key load-bearing findings:
scheduled-polling + `ChangedDate` watermark over webhooks; 200-id hydration chunking; `vso.work` PAT
in Windows Credential Manager (`keyring`/DPAPI); `STALE_UPSTREAM` reconciliation; opaque
`vstfs:///GitHub/PullRequest/<repoInternalId>%2F<pr>` and the undocumented `Contribution/
HierarchyQuery` resolver (→ branch-name primary instead); `os.mkdir` atomic lock over broken
`fcntl`/`flock` on DrvFs; fencing-token leases; `gc.auto 0` + serialized `fetch`/`push` +
`index.lock` backoff; the deterministic scrub-to-clean sequence.
