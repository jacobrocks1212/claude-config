# Build Queue — Feature Specification

> A machine-global FIFO serializer for the four expensive Cognito Forms build/test operations, so that across all parallel worktrees only one build ever runs at a time — with a PreToolUse hook that forces every agent through it.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-23

**Depends on:** (none)

> Authored in the `claude-config` repo (`docs/specs/build-queue/`). This is a harness-infrastructure change implemented by hand, outside the autonomous lazy pipeline (see `docs/specs/CLAUDE.md`). It has no upstream feature specs; it builds on existing claude-config infrastructure enumerated in the Reuse Ledger below.

---

## Executive Summary

Jacob works the Cognito Forms repo across four git worktrees (`Cognito Forms`, `Cognito Forms-B/C/D`), routinely with 2–3 active in parallel. Backend builds (`dotnet build Cognito.sln`) and, to a lesser degree, frontend builds (`nx`) are time- and resource-expensive. The acute pain is **parallel** builds: two worktrees compiling at once thrash the machine's finite CPU/RAM and stall everything, including the build that triggered the contention.

This feature introduces a **machine-global FIFO build queue**. All four sanctioned build/test entry points — the existing `/msbuild`, `/nxbuild`, `/mstest`, `/nxtest` skills — are re-pointed to call a new wrapper, `build-queue.ps1`, which acquires a single global slot before running the underlying per-worktree filtered script and releases it when done. Because the queue's state lives under `~/.claude/state/` (shared across all worktrees by construction), exactly one build executes at any instant regardless of which worktree or Claude session requested it, and requests are served in arrival order.

The queue is only useful if it cannot be bypassed. Transcript mining across all Cognito worktree sessions (4,710 Bash invocations) shows agents bypass the skills ~295 times via raw `dotnet build` (61), `dotnet test` (100), and `npx nx build/test` (134). A new PreToolUse(Bash) hook — modeled on the existing `long-build-ownership-guard.sh` — denies exactly those raw invocations (plus direct `*-filtered.ps1` calls, which would also skip the queue) and redirects the agent to the correct skill. An explicit `BUILD_QUEUE_BYPASS=1` env prefix is the human override.

`machine-perf.ps1` integrates at the observability layer only: each build start records a machine snapshot, and a `/build-queue-status` view shows queue depth plus current load. No throttling behavior in v1.

## User Experience

### Normal flow (queued build)

1. An agent (or Jacob) invokes `/msbuild` in worktree B while a `/mstest` is already running in worktree A.
2. `build-queue.ps1` allocates a FIFO sequence number, writes a ticket, and **blocks**, emitting a heartbeat: `Queued at position 2 (1 build ahead: mstest in Cognito Forms-A, PID 12345, running 47s). Waiting…`.
3. When the worktree-A test finishes and releases the slot, worktree B's request becomes the lowest live ticket, claims the active-lock, and starts. Output streams to the caller as it does today.
4. On completion the slot is released; the next waiter (if any) proceeds.

### Long-wait / timeout resilience

The Claude Code Bash tool caps a single call at 600s. A long queue wait plus a long build can exceed that. To prevent a client timeout from killing an *in-progress* build:

- While **waiting**, the client holds only a ticket — cheap to lose. If the client's Bash call times out or the session is killed, the ticket is reclaimed (PID-death) and the slot is unaffected.
- Once at the head, the client launches the actual build as a **detached process** (independent of the client's process lifetime) writing to a log file, records the *build's* PID in the active-lock, and tails the log to its own stdout. If the client times out mid-build, the detached build runs to completion anyway; its result is recorded to disk and surfaced by the next invocation or by `/build-queue-status`.

### Bypass attempt (enforcement)

An agent runs a raw `dotnet test … --filter …`. The PreToolUse hook denies it with:

```
BLOCKED — raw build/test invocations bypass the machine-global build queue, which
serializes builds across your 4 worktrees so they don't thrash the machine. Use the
/mstest skill instead (it routes through the queue): /mstest -Filter "ClassName~Foo".
Deliberate one-off outside the queue: prefix BUILD_QUEUE_BYPASS=1.
```

### Status view

`/build-queue-status` prints: the active build (op, worktree, PID, elapsed, log path), the ordered list of waiters, and a one-line `machine-perf` load summary (CPU %, mem used/free).

## Technical Design

### Component inventory

| Component | New/changed | Location |
|---|---|---|
| `build-queue.ps1` — the FIFO wrapper | **new** | `claude-config/user/scripts/` → `~/.claude/scripts/build-queue.ps1` (machine-global symlink) |
| `build-queue-status.ps1` — status reader | **new** | `claude-config/user/scripts/` → `~/.claude/scripts/` |
| `/build-queue-status` skill | **new** | `claude-config/repos/cognito-forms/.claude/skills/build-queue-status/` |
| `build-queue-enforce.sh` — PreToolUse hook | **new** | `claude-config/user/hooks/` → `~/.claude/hooks/` |
| `/msbuild`, `/nxbuild`, `/mstest`, `/nxtest` | **changed** (re-point to wrapper) | `claude-config/repos/cognito-forms/.claude/skills/*/SKILL.md` |
| `user/settings.json` PreToolUse[Bash] chain | **changed** (register hook) | `claude-config/user/settings.json` |
| `*-filtered.ps1` build executors | **unchanged** | per-worktree `Cognito Forms*/.claude/scripts/` |
| `machine-perf.ps1` | **unchanged** (consumed via `-Json`) | `claude-config/user/scripts/` |

### Queue state layout (`~/.claude/state/build-queue/`)

Machine-global, shared by all worktrees because `~/.claude/state/` resolves to one home directory. Mirrors the `LAZY_STATE_DIR` convention.

```
~/.claude/state/build-queue/
  seq.counter            # monotonic sequence allocator (integer)
  tickets/<seq>.json     # one per waiter: {seq, pid, worktree, op, started_wait_at}
  active.lock            # current holder (created atomically): {seq, build_pid, op, worktree, started_at, log_path, machine_perf}
  logs/<seq>.log         # build stdout/stderr (for detached tailing + post-timeout retrieval)
  results/<seq>.json     # {seq, exit_code, ended_at} written on completion
```

### Acquire algorithm (each client process)

1. **Allocate seq** — atomically read-increment-write `seq.counter` guarded by an exclusive file open (`[System.IO.File]::Open(..., CreateNew)` on a transient `seq.counter.lock`, with bounded retry). The allocated integer is strictly increasing → arrival order.
2. **Enqueue** — write `tickets/<seq>.json` with this client's PID and worktree.
3. **Poll loop (~1s tick):**
   a. **Reclaim stale** — for every `tickets/*.json` and for `active.lock`, if the recorded PID is no longer alive, delete that file (crash recovery; PID-death reclaim only — no runtime watchdog).
   b. **Head check** — if `active.lock` is absent **and** this client's `seq` is the lowest live ticket, attempt to **win**: atomically create `active.lock` via `CreateNew` (this create is the real mutex — only one creator succeeds). On success, delete this client's ticket and break out. On failure (someone created it first) or if not head, sleep and loop, emitting a heartbeat with current position.
4. **Run detached** — launch the underlying filtered script as an independent process (`Start-Process`, redirected to `logs/<seq>.log`); record its PID as `build_pid` in `active.lock`; capture a `machine-perf.ps1 -Json` snapshot into `active.lock`. Tail the log to the client's stdout.
5. **Release** — on build completion, write `results/<seq>.json` (exit code + end time) and delete `active.lock`. Propagate the build's exit code as the wrapper's exit code.

### FIFO + crash-recovery correctness

- Sequence numbers are unique and strictly increasing; the lowest live ticket always wins → strict arrival order.
- Only the lowest-seq waiter attempts to claim, and `CreateNew` on `active.lock` guards the residual race → never two concurrent holders.
- A client crash while **waiting** drops its ticket (reclaimed by any peer's poll); its slot is skipped harmlessly.
- A client crash while **holding** does not stop the build: `active.lock` records the **detached build's** PID, not the client's, so the lock is only reclaimed when the *build itself* dies. A genuinely-hung-but-alive build holds the slot until killed manually (accepted trade-off — never kill a legitimately-slow build).

### Single global lock (scope)

All four operation types — backend build, backend test, frontend build, frontend test — share **one** `active.lock`. There are no separate backend/frontend lanes: "only one build ever runs" is literal. A frontend test waits behind a backend build even though they stress different toolchains; this is the intended maximal-protection trade-off.

### Skill re-pointing

Each skill's `SKILL.md` changes its constructed command from calling the filtered script directly to calling the wrapper, passing the filtered script as the exec target and forwarding `$ARGUMENTS` verbatim. Sketch for `/mstest`:

```
REPO_ROOT=$(git rev-parse --show-toplevel) && powershell.exe -ExecutionPolicy Bypass \
  -File "$HOME/.claude/scripts/build-queue.ps1" \
  -Op mstest -Exec "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -ExecArgs "<$ARGUMENTS verbatim>"
```

The wrapper runs the filtered script **inside PowerShell** (`Start-Process`/`&`), not as a Bash tool call, so the enforcement hook (which matches the Bash tool boundary) never sees the inner `dotnet`/`nx` and no bypass token is needed for the sanctioned path.

### Enforcement hook (`build-queue-enforce.sh`)

PreToolUse(Bash) guard, cloned structurally from `user/hooks/long-build-ownership-guard.sh`: inline-Python, deny-via-JSON (`permissionDecision: deny`), **fail-open on any error** (a broken hook must never block legitimate work), best-effort breadcrumb to the state dir.

- **Scope gate (fires only in Cognito Forms worktrees):** before matching, resolve the git remote of the command's working directory; proceed only if it matches `cognitoforms/cognito`. Never blocks `dotnet build` in Overwatch, `mcp/`, or any other repo. (Detection by remote, not directory name, is robust across the `Cognito Forms`/`-B`/`-C`/`-D` worktree names.)
- **Deny surface (Conservative — grounded in transcript evidence):** the command's first real token (after optional leading `NAME=value` env assignments) is one of:
  - `dotnet build`
  - `dotnet test`
  - `nx` / `npx nx` with a `build` / `test` / `run-many` target
  - a direct invocation of `build-filtered.ps1` / `test-filtered.ps1` / `client-build-filtered.ps1` / `client-test-filtered.ps1` (bypasses the queue wrapper)
- **Never denied:** `dotnet restore` / `--version` / `dotnet ef` / `nx lint` / `nx typecheck` / `format`, the wrapper `build-queue.ps1`, and anything prefixed `BUILD_QUEUE_BYPASS=1`. `msbuild` / `dotnet msbuild` / `npm` / `pnpm run build|test` are deliberately **out of the deny surface** — transcript mining found zero genuine Cognito heavy builds via those routes, so including them buys no coverage and only adds false-positive risk.
- **Bypass token:** a command prefixed with `BUILD_QUEUE_BYPASS=1` is allowed through unchanged. The deny message names the override but the hook does not advertise it prominently.
- **Redirect message:** names the correct skill for the matched op and shows the equivalent skill invocation (e.g. raw `dotnet test --filter X` → "use `/mstest -Filter X`").

### machine-perf integration (observability only)

- `build-queue.ps1` calls `machine-perf.ps1 -Json` at build start and stores the snapshot in `active.lock`.
- `build-queue-status.ps1` (and the `/build-queue-status` skill) prints queue depth + the active build's start-time snapshot, and runs a fresh `machine-perf.ps1 -Json` for a live one-line load summary.
- No pre-run health gate, no throttling, no auto-defer in v1 (the queue already removes build-vs-build contention; gating on build-vs-other-load is deferred — see Open Questions).

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown (5 phases, refined by a touchpoint audit: no `manifest.psd1` edit needed, remote-based scope gate, and the wrapper CLI contract owned by Phase 1).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|---|---|---|---|
| Single build at a time across worktrees | Invoke `/msbuild` in A and `/mstest` in B simultaneously | Only one `dotnet` process tree runs at once; the second starts only after the first releases | `Get-Process dotnet`; `active.lock` holds one seq at a time; `logs/<seq>.log` timestamps non-overlapping |
| FIFO order preserved | Enqueue 3 requests in known order | They execute in arrival order | `tickets/*.json` seq ordering vs `results/*.json` `ended_at` ordering |
| Detached build survives client timeout | Start a build, kill the client process mid-build | Build completes; result recorded | `results/<seq>.json` exit_code written despite client gone; `active.lock` cleared afterward |
| Stale lock reclaimed on holder death | Kill a detached build's PID | Next waiter proceeds | `active.lock` deleted on next poll; waiter's `results` entry appears |
| Raw `dotnet build` denied in Cognito worktree | Run `dotnet build` via Bash in a Cognito worktree | Denied with `/msbuild` redirect | PreToolUse `permissionDecision: deny`; command does not execute |
| Raw build allowed outside Cognito | Run `dotnet build` in `Overwatch/` | Allowed | Command executes; no deny |
| Bypass token honored | Run `BUILD_QUEUE_BYPASS=1 dotnet build …` | Allowed | Command executes; no deny |
| Direct filtered-script call denied | Run `build-filtered.ps1` directly via Bash in a Cognito worktree | Denied with skill redirect | PreToolUse deny |
| Skill path runs unimpeded | Invoke `/msbuild` | Build runs through the queue | No deny; `active.lock` created; output streams |
| Status view reflects queue + load | Run `/build-queue-status` with a build active | Shows active op/worktree/PID/elapsed + waiters + load | Output matches `active.lock` + `tickets/*`; load line from `machine-perf.ps1 -Json` |

## Locked Decisions

| ID | Decision |
|----|----------|
| L1 | **FIFO mechanism: file-based ticket queue** under `~/.claude/state/build-queue/` (monotonic seq + per-waiter ticket + atomic `active.lock`). Not a named Mutex (no FIFO guarantee) and not a broker daemon (too heavyweight for one dev box). |
| L2 | **Serialization scope: single global lock** covering all four op types. No backend/frontend lanes. |
| L3 | **Blocking model: block-while-waiting + detached build** so a Bash-tool 600s timeout cannot kill an in-progress build. `active.lock` records the build PID (not the client PID). |
| L4 | **machine-perf: observability only.** Snapshot at build start + live summary in `/build-queue-status`. No health gate / throttle in v1. |
| L5 | **Enforcement surface: conservative + filtered-script closure.** Deny raw `dotnet build`, `dotnet test`, `nx`/`npx nx` build\|test\|run-many, and direct `*-filtered.ps1` Bash calls. Exclude `msbuild`/`npm`/`pnpm` (zero genuine usage in evidence). |
| L6 | **Escape hatch: `BUILD_QUEUE_BYPASS=1` env prefix** allows a deliberate raw build through the hook. |
| L7 | **Stale reclaim: PID-death only.** No max-runtime watchdog — never reclaim a legitimately-long build. |
| L8 | **Hook scope: Cognito Forms worktrees only,** detected by git remote matching `cognitoforms/cognito`. |
| L9 | **Hook contract: fail-open, deny-via-JSON,** cloned from `long-build-ownership-guard.sh`. A broken hook never blocks work. |

## Reuse Ledger

| Capability | Verdict | Evidence / basis |
|---|---|---|
| Filtered build/test execution | reuse-as-is | Per-worktree `Cognito Forms*/.claude/scripts/{build,test,client-build,client-test}-filtered.ps1`, already invoked by the four skills. The wrapper runs these unchanged. |
| Skill → script wiring | extend | `claude-config/repos/cognito-forms/.claude/skills/{msbuild,nxbuild,mstest,nxtest}/SKILL.md` — symlinked, so one edit propagates to all worktrees. Re-pointed to the wrapper. |
| Enforcement hook pattern | wrap (clone) | `claude-config/user/hooks/long-build-ownership-guard.sh` — PreToolUse(Bash), inline-Python, deny-via-JSON, fail-open. Registered in `user/settings.json` PreToolUse[Bash] chain alongside `block-work-repo-git-push.sh` et al. |
| Machine-global shared state | reuse-as-is | `~/.claude/state/` (`LAZY_STATE_DIR` convention) + `~/.claude/scripts/` ← `user/scripts/` symlink (`manifest.psd1`). Shared across all four worktrees by construction. New subtree: `~/.claude/state/build-queue/`. |
| Machine health snapshot | reuse-as-is | `user/scripts/machine-perf.ps1 -Json` emits a structured object — consumed at build start and in the status view. |
| The queue/lock itself | build-new | No existing queue/lock in claude-config (grep-clean). The one genuinely new component: `build-queue.ps1`. |

## Open Questions

- **Pre-run health gate (deferred from L4).** If, after v1, build-vs-*other*-load (e.g. Jacob running something heavy outside Claude) still stalls builds, revisit a `machine-perf`-driven gate that defers the head build until load drops below a threshold. Deferred because the queue already eliminates build-vs-build contention, and a flaky threshold is its own failure mode.
- **Cross-worktree priority / preemption.** v1 is strict FIFO. A future "this worktree's build is urgent, jump the queue" affordance is possible but unspecified.
- **Heartbeat cadence vs. log noise.** The ~1s poll tick and position heartbeats may be chatty in transcripts; tune during Phase 1 (e.g. only emit a heartbeat when position changes).

## Research References

None. Gemini deep research (Phase 2) was intentionally skipped — this is bounded, single-user harness tooling with no meaningful prior art to mine. Design decisions are grounded in (a) direct inspection of the existing claude-config hook/script/state infrastructure and (b) transcript mining of 4,710 Bash invocations across all Cognito worktree sessions, which quantified the raw-bypass routes that motivate the conservative enforcement surface (L5).
