# Cognito Doc Integration — Feature Specification

> Generalize the file-driven `/lazy` pipeline to source its work queue from Azure DevOps work items via a deterministic local mirror kept fresh out-of-band, add a cross-source work dashboard (including teammates), run **parallel implementation across a persistent pool of git worktrees driven by independent worker sessions**, and extend the orchestrator to shepherd GitHub PRs — keeping SPEC.md/PHASES.md as the canonical input format and preserving halt-for-genuine-decisions.

**Status:** Final (codebase-grounded)
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
WI type via an explicit config map over the *custom* process types (bug-like→bugs,
story-like→features; unknown→skip-and-log) — see Technical Design § Layer 3 for the grounded table. (7) Teammate scope = dashboard read-only. (8) Dashboard
= terminal skill `/work-status`.

**Round 3 — integration mechanics:** (9) WI↔PR link — see Round 5 revision. (10) Thin deterministic
copy at materialization. (11) Headless poller auth = ADO PAT. (12) Mirror scope = configurable WIQL
query (`@Me OR AreaPath UNDER <team>`).

**Round 4 — parallel execution:** (13) Multiple independent worker sessions (worker pool), no single
orchestrator. (14) Shared canonical `docs/` state; worktrees code-only. (15) Fan out at
implement→PR; front half lock-serialized. (16) Persistent worktree pool with scrub-on-reuse.

**Round 5 — post-research finalization (this spec):**
17. **Execution environment — Native Windows PowerShell.** The pipeline runs natively on Windows; the
    Python state machine + coordination run on NTFS. This deliberately **avoids the WSL2/DrvFs
    boundary** that research flags as the danger zone for file locks and file-mode churn. (Grounding:
    there is no pre-existing `create-branch-worktree.ps1` to reuse — the worktree pool is built fresh
    on `git worktree add`; see § "Composed substrate".)
18. **Coordination state location — A dedicated `cog-docs` git repo (NTFS) with an `os.mkdir()` atomic
    lock.** *(Revised at grounding — original draft put state in-repo at `cognito/docs/work/`.)* The
    canonical `docs/` tree (specs, bugs, queues) **and** all coordination files live in a **new,
    standalone git repo `cog-docs`** — separate from the `cognitoforms/cognito` checkout —
    `lazy-state.py --repo-root <COG_DOCS>` points there (`<COG_DOCS>/docs/{features,bugs,work}`).
    `cog-docs` is a sibling of the cognito checkout (`repos/cog-docs`); if instead nested under the
    cognito working tree, cognito's `.gitignore` must exclude it. This separation is required because
    the cognito repo blocks direct pushes and uses a squash-only workflow — committing lease/heartbeat
    churn there would pollute PRs and fight the push-block hook. `cog-docs` gives the docs and queues
    their own version history without that coupling. Worktrees remain **code-only** checkouts of the
    cognito repo; the shared docs/state never enter cognito's git history. `mkdir` is atomic on NTFS, so
    it is the safe lock primitive — **never** `fcntl`/`flock`/`LockFileEx`. (Coordination files such as
    `leases.json`/`global.lock.d` are runtime-only and should be `.gitignore`d within `cog-docs`.)
19. **WI↔PR link — ADO-fields primary; branch-name regex for self-authored items only.** *(Revised at
    grounding.)* The mirror captures PR/CI linkage **directly from ADO**: the `ArtifactLink` relations
    (`vstfs:///GitHub/PullRequest/<repoGuid>%2f<prNumber>` — the repo GUID is constant for the single
    `cognitoforms/cognito` repo, so the PR number parses with no HierarchyQuery), plus the org's custom
    fields `Custom.PR` (PR title), `Custom.PRStatus`, and `Custom.Autotest{Status,BuildID,Run}` (CI
    mirrored onto the WI). This covers **teammates' PRs**, who do **not** follow our branch convention.
    For items **we** author, the branch is `p/<wi_id>-<slug>` (regex `^p/(\d+)-`, matching the repo's
    existing `<initial>/<id>-<slug>` pattern) as the deterministic self-link. PR bodies still include
    `Resolves AB#<id>` for ADO's benefit. The undocumented `Contribution/HierarchyQuery` resolver is
    **not needed** at any phase.
20. **Upstream divergence — `STALE_UPSTREAM.md` sentinel + halt-at-next-gate.** If a materialized
    item's `ChangedDate` advances upstream, never clobber `SPEC.md`; diff, drop the sentinel, finish
    the current atomic step, then halt at the next natural lifecycle gate for a human absorb/reject.
21. **Secret storage — Windows Credential Manager via `keyring`** (DPAPI-encrypted); PAT scoped to
    **`vso.work` (Work Items – Read) only**.

### Codebase grounding (verified 2026-06-02, in-repo + ADO + GH MCP)

Facts the design now binds to, replacing draft assumptions:

- **Project / team / area:** ADO project `Cognito Forms` (id `54d9f307-…`); user's product team **Poseidon**
  (also member of `Cognito`, `Architects`). Area path = **`Cognito Forms\Poseidon`**, `includeChildren=false`.
- **Work-item types are a custom process** (not Agile "Story/Task/PBI"). Observed: story-like = `User Story`,
  `Refactor Story`, `Enabler Story`, `Requirement`; bug-like = `Bug`, `Defect`, `Story Bug`, `Engineering Bug`.
  WIs nest via `System.Parent` (e.g. a `Story Bug` under a `User Story`).
- **PR/CI already on the WI:** real `ArtifactLink` PR + Commit relations exist (Azure Boards–GitHub app **is**
  connected), and custom fields `Custom.PR`, `Custom.PRStatus`, `Custom.AutotestStatus/BuildID/Run` mirror PR
  title, PR review state, and CI result onto each WI.
- **Branch reality:** remote branches use per-developer initials (`m/ d/ h/ s/ j/ p/ …`); WI-id embedding,
  where present, is bare `<id>-<slug>` (e.g. `h/56089-unpaid-dunning-logic`), never `AB<id>`. Our convention
  is `p/<wi_id>-<slug>`. Teammates are not expected to conform.
- **No submodules** (`.gitmodules` absent) → the submodule steps of the scrub protocol are removed.
- **Substrate that exists:** `claude-config/user/scripts/{lazy-state.py,bug-state.py}`; `enqueue_adhoc()` +
  `--enqueue-adhoc` (seeds `ADHOC_BRIEF.md`, ROADMAP row, queue entry); `lazy-state.py` docs root =
  `--repo-root` (default `$PWD`) → `<root>/docs/{features,bugs}`. Cognito repo skills
  `.agents/skills/pull-request/` and `.agents/skills/ado-work-items/`; user skills `work-item`, `review-pr`,
  `write-pr-description`; the `using-git-worktrees` skill (bash `git worktree add -b`).
- **Substrate that does NOT exist:** `create-branch-worktree.ps1`, `review-pr.ps1` — the SPEC's prior
  references to reusing these are removed; the worktree pool and PR steps are built on the primitives above.

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
  implement → open a GitHub PR on a `p/<wi_id>-<slug>` branch; release lease + slot.

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
- **Cognito skills `work-item`, `review-pr`, `write-pr-description`; `.agents/skills/pull-request/` +
  `ado-work-items/`; the `using-git-worktrees` skill; and `gh` CLI** — the real existing primitives the
  worker, pool, and shepherding layers build on. *(Grounding: the previously-named
  `create-branch-worktree.ps1` / `review-pr.ps1` do not exist; the worktree pool is built fresh on
  `git worktree add -b`, and PR steps go through the `pull-request` skill + `gh`.)*

### Layer 1 — Deterministic ADO sync

- **Engine:** `user/scripts/ado-sync.py` (project-agnostic). Auth = PAT via `keyring`
  (`keyring.get_password("ado-local-poller", "vso_pat_readonly")`), scope **`vso.work` read-only**.
- **WIQL (delta):** `SELECT … FROM workitems WHERE (AssignedTo = @Me OR AreaPath UNDER 'Cognito
  Forms\Poseidon') AND ChangedDate >= '<lastSync-UTC>Z' ORDER BY ChangedDate ASC`. Dates **must** be
  UTC + `Z`. (Grounded: project name has a space; Poseidon is a single area, no sub-areas.)
- **Pagination (critical):** the WIQL endpoint returns ≤20,000 ids, but hydration
  (`wit/workitems?ids=…&$expand=all`) is capped at **200 ids/batch** — the poller **chunks ids into
  ≤200** or hits HTTP 400.
- **Output:** writes `<COG_DOCS>/docs/work/ado-mirror.json` **atomically** (`os.replace` of a temp file). The
  high-watermark (max `ChangedDate` seen) persists so the next poll is incremental + crash-recovering.
- **Schedule:** Windows Task Scheduler runs `ado-sync.py` every N min, headless. In-session, the
  worker / `/work-status` may refresh on-demand via the **ADO MCP** against the same schema.
- **Mirror schema:** `syncedAt`, `watermark`, `query` identity, `workItems[]` of `{id, type, title,
  state, assignedTo, areaPath, iteration, parentId, url, acceptanceCriteria, description, changedDate,
  linkedPRs[], pr, prStatus, autotestStatus, autotestBuildId, autotestRun, materialized}`.
  `linkedPRs[]` is parsed from the WI's `ArtifactLink` relations
  (`vstfs:///GitHub/PullRequest/<repoGuid>%2f<prNumber>` → `{prNumber, repo: "cognitoforms/cognito"}`;
  the repo GUID is constant so no resolver is needed). `pr`/`prStatus`/`autotest*` copy the org custom
  fields `Custom.PR` / `Custom.PRStatus` / `Custom.Autotest{Status,BuildID,Run}` verbatim — this is how
  the dashboard shows **teammates'** PR + CI state without their branches following our convention.

### Layer 2 — Work dashboard

- **Engine:** `user/scripts/work-status.py` reads `ado-mirror.json`, both `queue.json`s,
  `materialized.json`, `leases.json`, scans for `STALE_UPSTREAM.md`, and calls
  `lazy-state.py`/`bug-state.py` for live per-item status. Emits JSON the skill formats.
- **Skill:** `user/skills/work-status/SKILL.md` — read-only terminal render; optional `--markdown`
  writes `docs/work/DASHBOARD.md`. No mutation of any artifact.

### Layer 3 — Materialization + orchestration

- **Materialize** (`lazy-state.py --materialize-wi <id>` or sibling): resolve WI in the mirror,
  **auto-route by `type`** via the explicit map below, thin-copy title/description/acceptance verbatim
  into `ADHOC_BRIEF.md`, seed a stub `SPEC.md` carrying `**Work Item:** AB#<id> (<url>)`, call
  `enqueue_adhoc()`, append `{wi_id → feature_id, materialized_changedDate}` to `materialized.json`.
  Deterministic + idempotent.
- **Type→pipeline map (grounded in the custom process; config-driven so new types are a data edit):**
  - **bugs** (`bug-state.py`): `Bug`, `Defect`, `Story Bug`, `Engineering Bug`.
  - **features** (`lazy-state.py`): `User Story`, `Refactor Story`, `Enabler Story`, `Requirement`.
  - **Unknown type → no silent default:** skip + log (or write a `NEEDS_INPUT.md`-style note), never
    guess a pipeline. The map lives in Cognito config (`repos/cognito-forms/.claude/`), not hardcoded.
- **Orchestration:** unchanged front-half `/lazy`, now invokable per item via `--feature-id`. The
  branch is `p/<wi_id>-<slug>` (regex `^p/(\d+)-`); the PR body includes `Resolves AB#<id>`.
- **Upstream-divergence check:** on each sync/probe, for every materialized item compare mirror
  `changedDate` to the recorded `materialized_changedDate`; if newer, write `STALE_UPSTREAM.md`
  (sentinel; body = the field-level diff). The state machine finishes the current atomic step, then
  halts the item at its next gate for a human absorb/reject; absorb re-copies into `SPEC.md` and
  updates the recorded watermark.

### Layer 4 — Parallel execution (the concurrency plane)

- **Coordination files (`<COG_DOCS>/docs/work/`, all mutated only under the global lock):** `queue.json`,
  `leases.json`, `materialized.json`. Reads use atomic-rename so the dashboard never sees torn JSON.
- **Global lock = `os.mkdir("<COG_DOCS>/docs/work/global.lock.d")`.** Atomic on NTFS. Acquire = mkdir
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
- **Worktree pool:** K persistent worktrees added from the **cognito** clone (`git -C <cognito>
  worktree add <COG_DOCS>/pool/wt-NN`), sized to max-parallel; the `pool/` dir is `.gitignore`d in
  `cog-docs`. **Git concurrency defenses (mandatory), applied to the cognito repo:** `git config
  gc.auto 0` at its root; **serialize all network ref ops (`fetch`/`push`) under the global lock**
  (prevents `packed-refs` corruption); exponential backoff/retry on `index.lock` contention;
  `core.filemode false`, `core.autocrlf input`.
- **Deterministic scrub-to-clean (on slot reuse, ordered):**
  1. `rm -f .git/worktrees/<slot>/index.lock` (clear phantom locks from crashed runs)
  2. (under global lock) `git fetch origin`
  3. `git checkout --detach origin/main` → `git reset --hard origin/main`
  4. `git clean -fdx`
  5. `git checkout -b p/<wi_id>-<slug>`
  *(No submodule step — the cognito repo has no `.gitmodules`; if one is ever added, reinstate
  `submodule update --init --recursive --force` + `foreach reset --hard` + `foreach clean -fdx`.)*
- **Worker loop:** acquire lock → reclaim expired → pick highest-priority actionable item w/o live
  lease (front-half step *or* implement-ready) → lease it (+ slot if implementing) → release lock →
  do the work (front-half = short, in-lock model; implement→PR = long, in the leased worktree, with
  heartbeat) → acquire lock → flip state (fencing-checked), drop lease, free+flag-scrub slot, update
  `materialized.json` → release lock. Crash safety via heartbeat TTL.

### Cross-machine deployment

Authored in `claude-config`; deployed to the Windows work machine via `manifest.psd1` + `setup.ps1`.
Generic engine under `~/.claude/`; Cognito config (type→pipeline map, WIQL identity, pool size) under
`repos/cognito-forms/.claude/`. Canonical docs + coordination state live in the dedicated **`cog-docs`**
git repo; the worktree pool is gitignored under `cog-docs/pool/`, with each slot a `git worktree` of the
cognito checkout.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown. Summary: **Phase 0** bootstrap
(`cog-docs` repo + Cognito config + secrets/deps), **Phase 1** deterministic ADO sync, **Phase 2**
work dashboard, **Phase 3** WI→doc materialization, **Phase 4** parallel execution, **Phase 5**
(deferred) PR shepherding.

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
| Branch-name link parse (self) | Open PR on `p/1234-…` | Dashboard links PR↔WI via regex `^p/(\d+)-` (no API) | `/work-status` |
| Teammate PR/CI linkage (ADO) | Sync a teammate WI with a linked PR | `linkedPRs[]` + `pr`/`prStatus`/`autotest*` populated from ArtifactLink + custom fields | `ado-mirror.json`, Team panel |
| `--feature-id` preserves default | Run with/without the flag | Without = single-current baseline; with = scoped item | `--test` |
| Determinism end-to-end | Materialize → parallel `/lazy-worker` | Judgment surfaces via NEEDS_INPUT/BLOCKED only | sentinels |

## Open Questions

- **PAT mint** (still verify at work machine) — confirm a `vso.work` read-only PAT can be created; else
  `az`/MCP-only fallback for the headless poller.
- **Pool size K / lease TTL / heartbeat** defaults — recommend K≈3–4; TTL ≈ a few × the longest
  expected implement step; heartbeat `ttl/3`.
- **`/work-item` reconciliation** — does the new materialize+worker path supersede the existing
  `work-item` skill, or coexist? (Recommend: `work-item` becomes a thin manual alias over materialize.)
- **`cog-docs` repo provisioning** — create the new repo (sibling `repos/cog-docs`), seed
  `docs/{features,bugs,work}`, `.gitignore` runtime coordination + `pool/`, and a remote if the docs
  history should be shareable. (Setup task, not a design unknown.)

**Resolved at grounding (2026-06-02):**
- ~~Azure Boards–GitHub app~~ — **connected**; WIs carry `ArtifactLink` PR/Commit relations + custom
  PR/CI fields. No HierarchyQuery needed (single repo ⇒ constant repo GUID).
- ~~Branch slug shape~~ — **`p/<wi_id>-<slug>`** (raw id, no `AB`), regex `^p/(\d+)-`; matches the repo's
  existing `<initial>/<id>-<slug>` pattern. Teammates won't conform → their linkage comes from ADO.
- ~~Submodule presence~~ — **none** (`.gitmodules` absent); submodule scrub steps removed.

## Research References

`RESEARCH.md` (full report) and `RESEARCH_SUMMARY.md` (synthesis). Key load-bearing findings:
scheduled-polling + `ChangedDate` watermark over webhooks; 200-id hydration chunking; `vso.work` PAT
in Windows Credential Manager (`keyring`/DPAPI); `STALE_UPSTREAM` reconciliation; opaque
`vstfs:///GitHub/PullRequest/<repoInternalId>%2F<pr>` and the undocumented `Contribution/
HierarchyQuery` resolver (→ branch-name primary instead); `os.mkdir` atomic lock over broken
`fcntl`/`flock` on DrvFs; fencing-token leases; `gc.auto 0` + serialized `fetch`/`push` +
`index.lock` backoff; the deterministic scrub-to-clean sequence.
