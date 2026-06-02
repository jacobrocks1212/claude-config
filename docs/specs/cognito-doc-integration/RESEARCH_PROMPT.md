# Deterministically mirroring Azure DevOps work items into a local, file-driven autonomous-agent work queue — with parallel git-worktree implementation and GitHub PR shepherding

## Research Question

I am building a local-first "work dashboard" that feeds an autonomous AI coding pipeline. The
pipeline is **file-driven and deterministic**: a state machine computes "what to do next" purely
from on-disk bytes (a `queue.json`, per-item `SPEC.md`/`PHASES.md`, and YAML sentinel files),
never from conversational memory or LLM inference. I want to **source that queue from Azure DevOps
(ADO) work items** assigned to me and my team, keep a local mirror of those work items **fresh
automatically and deterministically**, render a cross-source dashboard, **run implementation in
parallel across a pool of git worktrees driven by multiple independent worker sessions**, and
eventually let the agent semi-autonomously shepherd the resulting **GitHub** pull requests.

The central question has two halves: **(1) what is the most robust, deterministic, low-operational-
burden architecture for keeping a local on-disk mirror of ADO work items continuously fresh, and
for bridging those work items into a local doc-convention-based work queue (including how GitHub
PRs link back to ADO work items)?** and **(2) how do I safely run multiple independent worker
processes that pull from one shared on-disk queue and implement in parallel across a persistent
pool of git worktrees — without races, double-claims, or cross-item contamination, while keeping
the whole thing deterministic and auditable?** Validate or challenge my baseline design below,
surface prior art, and identify pitfalls. (There is **no cloud / multi-machine** concern — this is
a single workstation; coordination is local-filesystem only.)

## Context

- **Environment:** A single developer workstation (Windows, WSL2 available). The pipeline and its
  state machine are Python scripts; the agent is Claude Code (a CLI coding agent). Work items live
  in **Azure DevOps Boards**; source code and pull requests live in **GitHub** (git remote is
  GitHub; ADO holds work items only). An Azure DevOps **MCP server** is available *inside* an agent
  session but NOT to headless background jobs.
- **Existing deterministic pipeline:** A queue of work items walks a fixed lifecycle
  (spec → research → phases → plan → implement → retro → validate → complete). "Next action" is a
  pure function of files on disk. The design value I must preserve: **the bridge from the external
  system into the queue must not infer or guess** — it copies verbatim; all genuine decisions are
  made later, inside gated steps that halt and ask a human.
- **Why "deterministic, without inference":** I want reproducibility and auditability. Given the
  same ADO state, the mirror file and the resulting queue actions must be identical run-to-run. I
  originally guessed "maybe websockets," but I suspect polling and/or webhooks are more appropriate.

## Baseline Design Summary (to validate / challenge)

1. **Sync mechanism:** A scheduled headless poller (Windows Task Scheduler) runs a configurable
   **WIQL** query via the **ADO REST API** authenticated with a **Personal Access Token (PAT)**,
   and writes a local `ado-mirror.json` atomically (temp-file + rename). The agent session can also
   refresh on-demand via the ADO MCP. I am treating **ADO Service Hooks (webhooks)** as a later
   "push" upgrade, and rejecting websockets/SignalR as least-native.
2. **Queue model:** The mirror is **read-only awareness**; a work item only enters the actual work
   queue via a discrete, logged **materialization** step (not auto-enqueue).
3. **Materialization:** Thin **verbatim copy** of WI title/description/acceptance-criteria into a
   brief, auto-routed by WI **type** (Bug vs User Story/Task) into two sub-pipelines. Real spec
   shaping happens afterward in a gated, halt-capable step.
4. **WI↔PR link:** Use the **Azure Boards–GitHub app** convention (`AB#<id>` mentions in PR/commit)
   so PRs link bidirectionally to work items; fall back to parsing the work-item id from the branch
   name if that app connection is not enabled.
5. **Parallel execution:** **Multiple independent worker sessions** (separate processes/terminals,
   no parent orchestrator) pull implement-ready items from the shared queue. A **single
   coordination lock** serializes every short state transition (claiming, front-half steps,
   post-implement state flips) so there is exactly one writer at a time; the **only** long operation
   that runs *outside* the lock is the implement→PR stage, which runs in an isolated git worktree —
   so multiple implements overlap. Each in-flight item holds an **item lease** (with TTL + heartbeat
   for crash reclamation) and a **persistent worktree-pool slot** that is **scrubbed to a clean
   known state** (`git fetch` + `git checkout -B <branch> origin/main` + `git clean -fdx`) before
   reuse. The N worktrees share one git object store. Pool size = configurable max-parallel.
6. **PR shepherding (later):** Poll GitHub PR state (`gh` CLI / GitHub API) for materialized work
   items; drive review/fix actions on state transitions; merge is a human decision. Never
   auto-reply to PR comments.

## Research Areas

### A. Keeping the ADO mirror fresh — deterministically
- **Polling vs ADO Service Hooks vs the Analytics/ODATA feed vs `$expand`/batch APIs:** for a
  single-developer local mirror of work items assigned to me + my team, what is the right freshness
  mechanism? Compare on determinism, operational burden, latency, and failure modes.
- **Incremental sync:** Does ADO expose a reliable **delta/watermark** (e.g. `System.ChangedDate`,
  `wit/reporting/workitemrevisions`, or the Analytics OData `$filter` on change date) so the poller
  can fetch only changes since the last sync rather than re-querying everything? How do people make
  ADO sync idempotent and reproducible?
- **Service Hooks reality check:** What work-item events does ADO Service Hooks support, what is the
  delivery/retry/ordering guarantee, and what infrastructure does a local receiver actually need
  (public endpoint, tunnel, retries, replay)? Is a webhook→local-file design *more* or *less*
  deterministic than polling, given at-least-once delivery and possible out-of-order events?
- **WIQL specifics:** Best-practice WIQL for "assigned to me OR under my team's Area Path," handling
  of `@Me`, area-path recursion (`UNDER`), iteration scoping, and field projection to keep payloads
  small. Pagination limits (the ~200 WI id batch limit) and how to hydrate fields efficiently.

### B. Authentication for headless jobs
- **PAT vs `az` CLI / az login vs service principal / managed identity** for an unattended scheduled
  job hitting ADO REST: tradeoffs in expiry, scope minimization (read-only Work Items scope),
  rotation, and secret storage on a Windows workstation (Credential Manager, DPAPI, env). What is
  the minimum PAT scope for reading work items + queries?

### C. ADO ↔ GitHub linkage
- **Azure Boards–GitHub integration:** How does `AB#<id>` linking actually work end-to-end (the
  Azure Boards GitHub app, the connection setup, what gets linked: commits/branches/PRs)? Where is
  the link readable — on the ADO work-item side (relations) or only in GitHub? Can a local poller
  read the linked PR(s) for a work item via the ADO REST API, and read PR state via the GitHub API?
- **Fallback conventions:** If the app isn't connected, what deterministic conventions do teams use
  to associate GitHub PRs with ADO work items (branch naming, PR title tokens, commit trailers)?
  Which is least brittle?

### D. Prior art — external-tracker → local-agent-queue bridges
- Tools/patterns that mirror an external issue tracker (Jira/Linear/ADO/GitHub Issues) into a local
  or file-based representation that an automation/agent consumes. What did they get right/wrong on
  freshness, idempotency, conflict handling, and avoiding "the queue churns every time someone edits
  a ticket"? Examples: `git-bug`, `bugwarrior`, Linear/Jira CLI mirrors, autonomous-agent task
  queues.
- **Conflict/staleness handling:** When a source ticket changes *after* it's been materialized into
  a local work item that's mid-flight, what reconciliation strategies work (source-of-truth rules,
  re-sync prompts, divergence warnings)? How to avoid clobbering local progress.

### E. Multi-process coordination on a single workstation (NEW — high priority)
- **Atomic claim / mutual exclusion on a local filesystem, cross-platform (Windows + WSL2):** I have
  N independent worker processes pulling from one shared `queue.json` + `leases.json`, and exactly
  one may mutate shared state at a time. Compare the robust primitives: a **directory/`mkdir` lock**,
  `O_CREAT|O_EXCL` lockfile, `flock`/`fcntl` (POSIX), `msvcrt.locking`/`LockFileEx` (Windows), and
  libraries like `portalocker`/`filelock`. Which give a *truly atomic* acquire that works on NTFS,
  on WSL2's view of the Windows filesystem (DrvFs), and on native ext4 — and which silently fail
  (e.g. advisory-only, NFS caveats, lock not released on crash)? What's the recommended primitive for
  a Python tool that may be invoked from both Windows and WSL2 against the *same* repo path?
- **Crash-safe leases:** Best practice for lease ownership + heartbeat + TTL so a dead worker's claim
  (and the worktree slot it held) can be safely reclaimed without a coordinator. How to set the TTL
  relative to a long, variable implement step; how to avoid the two-workers-think-they-own-it race
  on reclamation; whether a lock-generation/fencing token is warranted for a single-host design.
- **Atomic state-file updates under concurrency:** temp-file + `os.replace` rename atomicity
  guarantees on NTFS vs ext4 vs DrvFs; read-modify-write patterns for `queue.json`/`leases.json`
  that never present a torn or lost-update view to a concurrent reader (the dashboard) or writer.
- **Determinism under concurrency:** how to keep "next action = pure function of on-disk bytes" true
  when N workers interleave — what must be serialized vs what can run lock-free.

### F. Parallel git worktrees sharing one object store (NEW — high priority)
- **Concurrency safety of multiple `git worktree`s on one repo:** N worktrees share a single `.git`
  object database and refs. What concurrent operations are safe vs racy: simultaneous
  `git fetch`/`checkout`/`commit`/`add` in different worktrees; `git worktree add`/`remove`;
  background `git gc`/auto-gc; ref updates and the `packed-refs`/loose-ref races; per-worktree
  `index.lock`. Where are the documented sharp edges, and how do I avoid them (e.g. disable auto-gc,
  serialize fetches, per-worktree config)?
- **Persistent worktree pool hygiene:** a reliable, deterministic **scrub-to-clean** sequence to
  reset a reused worktree to a pristine state off `origin/main` (untracked files, ignored build
  artifacts, submodules, partial merges, leftover `index.lock`, detached vs branch state). Is
  `git checkout -B <b> origin/main` + `git clean -fdx` sufficient, or are there gotchas (submodules,
  sparse-checkout, file-mode/CRLF churn on Windows)? How do mature systems (CI runners, `gitlab-
  runner`, `git-worktree`-based tools, monorepo task runners) keep reused checkouts clean and fast?
- **Pool sizing & contention:** practical guidance on worktree pool size on one machine (disk, IO,
  build-tool parallelism, antivirus on Windows), and create/destroy vs persistent-pool tradeoffs.
- **Prior art:** tools that run many agents/jobs across a worktree pool on one host — what their
  locking + scrub + pool-allocation designs look like, and their failure modes.

### G. Autonomous PR shepherding (later phase, lighter touch)
- Patterns for an agent that watches PR state (CI status, review state, requested changes) and takes
  bounded actions, with a human gate on merge. GitHub API/`gh`/GraphQL surfaces for PR state, check
  runs, and review threads. Rate-limit and polling-cadence guidance. Known failure modes of
  "autopilot" PR bots and how the good ones stay safe.

## Specific Questions

1. For a single-dev local mirror of ADO work items, is **scheduled polling with a `ChangedDate`
   watermark** the most deterministic+robust choice, or do Service Hooks meaningfully beat it
   despite at-least-once/out-of-order delivery? Give a concrete recommendation with reasoning.
2. What is the canonical ADO REST/WIQL recipe for "my + my team's work items," including delta sync
   and efficient field hydration, with pagination limits called out?
3. What is the **minimum-scope** auth for an unattended ADO read-only poller on Windows, and how
   should the secret be stored/rotated?
4. How exactly does `AB#<id>` GitHub linking work, and can both the ADO side (work-item relations)
   and the GitHub side (PR state) be read deterministically by local scripts? What's the best
   fallback if the Azure Boards GitHub app is not connected?
5. What incremental-sync / idempotency design prevents the local mirror (and the downstream queue)
   from churning when tickets are edited, while still reflecting genuine changes?
6. What reconciliation strategy is best when a source work item changes after materialization?
7. What are the top pitfalls (rate limits, clock skew, partial failures, PAT expiry, area-path
   recursion surprises, WIQL `@Me` under a service identity) for this kind of ADO mirror, and how
   do I defend against each deterministically?
8. **For N independent worker processes on one workstation (Windows + WSL2) sharing one
   `queue.json`/`leases.json`: which atomic-lock primitive should I use, and what is a correct
   crash-safe lease (ownership + heartbeat + TTL + safe reclamation) design with no coordinator?**
9. **What concurrent git operations across multiple worktrees sharing one object store are safe vs
   racy, and what is a deterministic scrub-to-clean sequence for reusing a persistent worktree off
   `origin/main` (covering untracked/ignored files, submodules, leftover `index.lock`, Windows
   CRLF/file-mode churn)?**
10. Any strong prior-art projects whose mirror/sync/idempotency, multi-process locking, or
    worktree-pool design I should copy or avoid?

## Output Format Request

Please return **structured findings** with:
- A clear **recommendation** for the sync mechanism (poll vs webhook vs hybrid) with justification
  tied to my determinism requirement.
- Concrete **ADO REST/WIQL** examples (queries, endpoints, delta-sync watermark fields, pagination).
- A short **auth recommendation** (mechanism + minimum scope + secret storage on Windows).
- A definitive explanation of **`AB#` GitHub linking** and a ranked list of fallback link
  conventions.
- A **multi-process coordination recommendation**: the specific atomic-lock primitive for Windows +
  WSL2 sharing one repo path, plus a concrete crash-safe lease (ownership/heartbeat/TTL/reclamation)
  design.
- A **git-worktree-pool recommendation**: which concurrent git ops to serialize/disable, and an
  exact deterministic scrub-to-clean sequence for reused worktrees.
- A **pitfalls table** (pitfall → why it bites → deterministic defense) covering both the ADO/sync
  side and the concurrency/worktree side.
- **Prior-art callouts** (project → what to copy → what to avoid).
- Where evidence is thin or version-dependent, say so explicitly and cite sources.
