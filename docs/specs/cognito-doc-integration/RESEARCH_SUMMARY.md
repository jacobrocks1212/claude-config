# Research Summary — cognito-doc-integration

Source: `RESEARCH.md` (Gemini Deep Research, "Deterministic Architecture for Local-First Autonomous
Agent Pipelines"). This summary gates downstream workflow; it records what the research **confirms**,
what it **adds**, what it **changes**, and the **decisions** it surfaces for Phase 3 finalization.

## Verdict: baseline validated, hardened with specifics

The report endorses every Round 1–4 decision and supplies concrete, citable mechanics for each.
No baseline decision is overturned. The notable *additions* are (a) a reconciliation strategy for
upstream edits, (b) a real complexity in `AB#` PR-link resolution, and (c) a strong steer on **where
coordination state must physically live** to survive the Windows/WSL2 boundary.

## Confirmed (adopt as-is — mostly mechanical)

- **Sync = scheduled polling + `System.ChangedDate` high-watermark.** Rated unequivocally superior;
  webhooks, OData Analytics, and the `workItemRevisions` firehose all explicitly rejected (dropped
  events / latency / over-broad). Crash-recovery is automatic: next poll fetches all accumulated
  changes in final state. → confirms Decision 2.
- **WIQL recipe:** `WHERE (AssignedTo = @Me OR AreaPath UNDER 'Project\Team') AND ChangedDate >=
  '<UTC>Z' ORDER BY ChangedDate ASC`. Dates MUST be UTC with `Z`. → confirms Decision 12.
- **Pagination trap (mechanical, important):** WIQL returns ≤20,000 ids, but the hydration endpoint
  `wit/workitems?ids=…&$expand=all` is capped at **200 ids/batch** — the poller must chunk ids into
  ≤200 or get HTTP 400.
- **Auth:** PAT scoped to **`vso.work` (Work Items – Read) only**; store in **Windows Credential
  Manager via the `keyring` library** (DPAPI-encrypted at rest), not env/plaintext. → confirms
  Decision 11 with a concrete secret-storage mechanism.
- **Atomic state writes:** temp-file + `os.replace` (atomic on NTFS and ext4) — concurrent dashboard
  readers never see torn JSON. → confirms baseline.
- **Lease schema:** `{worker_pid, worktree_slot, term_token (fencing), heartbeat_timestamp,
  ttl_seconds}`; heartbeat every `TTL/3`; **fencing-token check before every state transition** so a
  revived "zombie" worker can't corrupt the queue; expired-lease reclamation scrubs the orphaned
  slot. → confirms + hardens Decision 13's lease design.
- **Git worktree concurrency defenses:** exponential backoff/retry on `index.lock`; **serialize all
  network ref ops (`fetch`/`push`) under the global lock** (prevents `packed-refs` corruption);
  **`git config gc.auto 0`** (background GC can sever worktree refs mid-flight); manual GC only when
  all slots idle. → hardens Decision 16.
- **Deterministic scrub-to-clean (persistent pool reuse):** `rm -f .git/worktrees/<slot>/index.lock`
  → (under lock) `git fetch origin` → `git checkout --detach origin/main` → `git reset --hard
  origin/main` → `git clean -fdx` → submodule scrub (`update --init --recursive --force`, `foreach
  reset --hard`, `foreach clean -fdx`) → `git checkout -b <branch>`. Plus `core.filemode false`,
  `core.autocrlf input`, and WSL2 `/etc/wsl.conf` `metadata` mount flag to kill spurious
  "modified-file" churn. → hardens Decision 16's scrub protocol.
- **PR shepherding (deferred phase) mechanics:** `gh pr create --body "Resolves AB#1234"`; poll with
  `gh pr view <n> --json statusCheckRollup,reviews` and `gh pr checks`; on changes-requested/CI-fail,
  route feedback to a `FEEDBACK.md` in the item dir and transition `wait_on_pr → implement`; **merge
  stays human-gated**. → confirms Decision 4 / Phase 5.

## Added / changed (these need a decision in Phase 3)

1. **Upstream divergence reconciliation (NEW concrete strategy).** If `ado-mirror.json` shows a
   materialized item's `ChangedDate` advanced *after* materialization, **do not clobber `SPEC.md`**
   (that corrupts a running agent). Instead: diff original-vs-new, drop a **`STALE_UPSTREAM.md`
   sentinel**, let the current atomic step finish, then **halt at the next natural lifecycle gate**
   for a human absorb-or-reject decision. This answers a baseline Open Question and needs adoption +
   gate/UX confirmation.

2. **`AB#` link resolution is harder than assumed.** The ADO-side relation is an opaque
   `vstfs:///GitHub/PullRequest/<repoInternalId>%2F<prNumber>` artifact. The `<prNumber>` is
   recoverable, but mapping `<repoInternalId>` → an actual `github.com/org/repo` requires an
   **undocumented internal endpoint** (`Contribution/HierarchyQuery` with the
   `azure-boards-external-connection-data-provider`). Research ranks **branch-name encoding (e.g.
   `feature/AB1234-...`) as the MOST robust, least-brittle** link convention — pure local regex, no
   API. Given PR-shepherding is deferred, this reopens Decision 9's primary-vs-fallback ordering.

3. **Coordination state must avoid the DrvFs/9P boundary.** POSIX `fcntl`/`flock` are **broken over
   `/mnt/c`** (silent failure / data corruption); Windows `LockFileEx` can't run from WSL2. Robust
   options: **(a)** put `queue.json`/`leases.json` on the **native WSL2 ext4 disk** (`~/.agent-queue/`)
   and use `os.open(O_CREAT|O_EXCL)`; or **(b)** if state must sit on the NTFS repo path, use
   **`os.mkdir()` as the atomic lock** (atomic on both filesystems). My baseline put state in-repo at
   `docs/work/` (NTFS) — this is viable *only* with the mkdir-lock, and trades the ext4 safety margin
   for version-controlled, co-located state. Needs an explicit call, and it's entangled with **which
   environment runs the pipeline (WSL2 vs native Windows PowerShell)** — the existing `/work-item`
   path is PowerShell/native, but the research's locking + scrub recipes assume Linux git under WSL2.

## Open items unchanged by research (still verify at the work machine)

- PAT can actually be minted with `vso.work` scope (else `az`/MCP-only fallback).
- Whether the Azure Boards–GitHub app is connected (drives Decision 9 above).

## Decisions resolved in Phase 3 (see SPEC § Locked Decisions Round 5)

- **D-A: Execution environment → Native Windows PowerShell** (avoids the WSL2/DrvFs danger zone;
  reuses `create-branch-worktree.ps1`).
- **D-B: Coordination state → In-repo `docs/work/` (NTFS) with `os.mkdir()` atomic lock** (co-located,
  git-tracked; `mkdir` is the safe primitive — never `fcntl`/`flock`).
- **D-C: WI↔PR link → Branch-name primary with team `p/` prefix** (`p/AB<id>-<slug>`, regex parse);
  `AB#`/HierarchyQuery is a Phase 5 enrichment only.
- **D-D: Upstream divergence → `STALE_UPSTREAM.md` sentinel + halt-at-next-gate** + human absorb/reject.
