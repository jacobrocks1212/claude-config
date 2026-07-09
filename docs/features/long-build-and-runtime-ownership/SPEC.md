# Long-Build + Runtime Ownership — Feature Specification

> Long-running builds and the dev/MCP runtime are owned at a level that survives the subagent turn boundary, so `/mcp-test` never meets a reaped runtime and no production edit is orphaned by a build dying mid-cycle.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-06-20

**Depends on:**

- unified-pipeline-orchestrator — composes — this feature extends that feature's `lazy-state.py --ensure-runtime` subcommand and the orchestrator-loop / cycle-subagent (Step 1d.0) model it owns.

---

## Executive Summary

A long-running build (`tauri build`) or the dev/MCP runtime (`tauri dev` + the MCP HTTP server on TCP 3333) is a **process**. A process started from inside a cycle subagent's turn lives in that subagent's process tree, and Claude Code reaps that tree when the subagent's turn ends. The result is three recurring failure modes observed in the AlgoBooth `/lazy-batch` corpus (2026-06-19 session audit):

1. **Reaped runtime** — `/mcp-test` runs in a later cycle and finds a dead runtime, because the runtime was booted inside an earlier subagent's subprocess (session `18e1d3d7`: `--ensure-runtime` booted + asserted tools *within its own Bash subprocess*, whose process tree was torn down on return — `health_code: 0` was the tell).
2. **Orphaned production edits** — a `tauri build` backgrounded inside a cycle subagent dies with that subagent's turn, leaving real production edits uncommitted and the cycle orphaned (session `5c33b6ba`).
3. **Hand-rolled poll loops** — the orchestrator compensates by hand-building repeated rebuild → health-poll → inspect-telemetry until-loops, each the same shape (~6+ times in one session), boilerplate that should be a single deterministic primitive.

The harness already has the *two halves* of the answer in partial form: the long-build half is a **prose rule** (`repos/algobooth/.claude/skill-config/long-build-ownership.md` — "orchestrator owns long builds, run them `run_in_background` from the main session, never from inside a cycle subagent"), and the runtime half is a **deterministic subcommand** (`lazy-state.py --ensure-runtime` → `lazy_core.ensure_runtime`, the probe → stale-check → `dev:restart` bg → curl-until-200 → assert-MCP-tool dance collapsed into one call). The friction is that (a) the prose rule is **advisory** — a subagent can and does violate it, with no enforcement; (b) `--ensure-runtime`'s background process is **only survival-correct when invoked from the orchestrator session** — invoked from inside a subagent's subprocess it is reaped exactly like any other; and (c) there is **no harness-tracked liveness/recovery primitive** that lets the orchestrator stop hand-rolling poll loops and lets `/mcp-test` cheaply assert "the runtime I need is up, current, and mine."

This feature mechanizes process ownership so a build/runtime started during a feature cycle is provably owned by a session that outlives the cycle subagent's turn. Deep research (`RESEARCH.md`, 2026-06-20) locked the mechanism: a **controller-spawned detached process tracked by a verifiable on-disk sentinel** — a JSON sidecar fingerprinting the process's temporal identity `(pid, kernel start_time, controller_session_id)` so ownership is *verifiable*, not merely "something answers `/health`." A single unified cross-platform spawn primitive (Windows Job-Object breakaway / POSIX `systemd-run --user`) serves both shapes, bifurcated into two supervisory API contracts (persistent service vs. transient build). The advisory prose rule becomes an enforced `PreToolUse` ownership-boundary guard, and the hand-rolled poll loops collapse into one deterministic liveness/recovery state machine.

## User Experience

The "user" of this harness-internals feature is the orchestrator (and, by extension, Jacob reading a `/lazy-batch` run's behavior). There is **no end-user-facing AlgoBooth product surface** — every decision below is a harness-internal mechanism choice. The observable behaviors:

- **A cycle subagent never owns a turn-crossing process.** When a cycle needs a long build or the dev/MCP runtime, the *orchestrator* owns the process (started detached in the main session), and the subagent interacts with it through a harness-tracked handle — never by backgrounding it inside its own turn. An attempt by a subagent to background a turn-crossing build/runtime is prevented or redirected (the `PreToolUse` guard, fail-open `exit 2`), not silently reaped.
- **`/mcp-test` cheaply asserts a live, current, owned runtime.** The mcp-test cycle calls one primitive returning a structured verdict (`{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}`) and never meets a reaped runtime. If the runtime cannot be brought up MCP-ready, the orchestrator surfaces a `BLOCKED.md` (`blocker_kind: mcp-runtime-unready`) rather than dispatching a subagent against a dead runtime.
- **The orchestrator stops hand-rolling poll loops.** The rebuild → health-poll → inspect-telemetry shape is a single deterministic subcommand the orchestrator calls; it does not hand-compose the loop per cycle.
- **A torn-mid-build cycle does not orphan production edits.** A `PreToolUse` guard prevents the build from being subagent-owned in the first place (so it survives), and Atomic Artifact Promotion plus a `--cycle-begin` git-consistency check guarantee no silent uncommitted production delta if the controller itself is torn mid-build.

## Technical Design

> The load-bearing mechanism choices below were Open Questions in the baseline draft and are now **research-locked** (`RESEARCH.md` → "Actionable Mapping"). They are recorded in `## Locked Decisions` and integrated here. `/spec-phases` finalizes phase ordering.

### Current state (what exists today)

- **Long-build prose rule** — `repos/algobooth/.claude/skill-config/long-build-ownership.md`: orchestrator owns long builds, runs them `Bash run_in_background: true` from the main session, `cargo check --release` before a packaged `tauri build`. Advisory; no enforcement.
- **`--ensure-runtime` subcommand** — `lazy_core.ensure_runtime(repo_root, *, config, probe, restart, stale_check)` (`user/scripts/lazy_core.py` ~L6166), surfaced as `lazy-state.py --ensure-runtime`. Probe `/health` → `stale_check` (native source newer than boot stamp) → `restart()` (background `dev:restart`, bounded curl-until-200) → assert MCP tool present. Returns `{status, mcp_tools_present, health_code}`. AlgoBooth specifics parameterized in `_ENSURE_RUNTIME_DEFAULT_CONFIG`; injectable callables keep `--test` hermetic. Called from `/lazy-batch` Step 1d.0 (orchestrator session).
- **Cycle-subagent containment** — `lazy-cycle-containment.sh` + `lazy-state.py --cycle-begin/--cycle-end` already deny a subagent a defined set of orchestrator-only ops (routing/lifecycle flags, `dev:kill`/`dev:restart`, etc.; the former recursive-dispatch deny was removed 2026-07-09 — see `docs/bugs/adhoc-containment-denies-mandated-explore-fanout`). This is the existing enforcement seam the long-build/runtime ownership rule extends.

### Locked mechanism (post-research)

**M1 — Ownership = controller-spawned detached process + verifiable on-disk sentinel.**
The orchestrator spawns the child detached from its (and any subagent's) process tree, then writes a JSON sidecar `.runtime.lock.json` at the project root fingerprinting the process's temporal identity. Required fields:

| Field | Type | Description |
|-------|------|-------------|
| `controller_session_id` | string (UUID) | Generated at the start of the orchestration bracket; proves current-orchestrator ownership. |
| `pid` | int | OS-assigned PID of the spawned child. |
| `start_time` | float | Kernel-reported absolute process start time (Unix epoch sec); defeats PID reuse. |
| `port` | int | TCP port the runtime claims (3333 for the MCP server). |
| `artifact_hash` | string | Commit hash / source mtime at boot, for staleness checks. |

Ownership is **verifiable**: compare the kernel-reported `start_time` against the sentinel (a reused PID held by a foreign process diverges) and `controller_session_id` against the live session (a previous crashed controller's runtime fails this). This replaces "200 on `/health` ⇒ ours," which the baseline's `health_code: 0` / zombie-port modes proved unsafe. `start_time` is extracted stdlib-only via `ctypes` → `kernel32.GetProcessTimes` (Windows) and `/proc/[pid]/stat` field 22 → epoch via `SC_CLK_TCK` (POSIX/WSL). Optionally hardened with advisory file locks (`msvcrt.locking` / `fcntl.flock`).

**M2 — One cross-platform spawn primitive (stdlib-only).** A single `spawn_detached(...)` wrapper in `lazy_core`:
- **Windows:** `subprocess.Popen(creationflags = DETACHED_PROCESS(0x8) | CREATE_NEW_PROCESS_GROUP(0x200) | CREATE_BREAKAWAY_FROM_JOB(0x01000000))`, wrapped `try/except OSError` to fall back to `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` when a parent Job Object forbids breakaway (`ERROR_ACCESS_DENIED`). Job Objects with `KILL_ON_JOB_CLOSE` are the reaping mechanism being escaped.
- **POSIX/WSL:** `start_new_session=True`, wrapped in `systemd-run --user --scope --quiet --same-dir` on WSL to bypass `instanceIdleTimeout`/`vmIdleTimeout` (the WSL utility VM suspends ~15s after the last interactive terminal exits). Fallback: `setsid` + a `nohup sleep infinity` keep-alive when systemd is unavailable. `PR_SET_PDEATHSIG` is NOT used (it would kill the child with the parent — the opposite of the requirement).

**M3 — Two supervisory API contracts over the one spawn primitive.** Mirrors CI prior art (terminating builds vs. long-lived services):
1. **Persistent Service contract** (the dev/MCP runtime) — sentinel + active `/health` polling + the full READY/STALE/DEAD state machine; deliberately leaves the process detached and behind for re-attach in subsequent cycles. This is the reworked `--ensure-runtime`.
2. **Transient Build contract** (`tauri build` / `cargo build --release`) — synchronous wait-and-promote; spawned detached only to survive subagent reaping, but the orchestrator explicitly awaits the build's conclusion (gathering stdout for telemetry), then applies Atomic Artifact Promotion. Does NOT abandon the process for a future cycle.

**M4 — Single liveness/recovery state machine (replaces hand-rolled loops).** `--ensure-runtime` is reworked (extended in place — NOT replaced) into an idempotent gatekeeper returning the verdict `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}` with `state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}`. Phases: **Identity** (parse sentinel, query kernel start_time for the recorded PID — divergent start_time ⇒ HIJACKED, missing PID ⇒ DEAD) → **Staleness** (injected `stale_check(artifact_hash)`) → **Health** (injected `probe()` → `/health`; refused despite live PID ⇒ DEAD). Recovery contract:
- **STALE / DEAD** → auto-recover: `restart()` in a bounded exponential-backoff loop **capped at 5 attempts**; on success rewrite `.runtime.lock.json`, return READY.
- **HIJACKED** → strict fail-safe: **never `SIGKILL` a process not verifiably owned** (security/stability risk). Surface a `terminal_blocker` → BLOCKED.
- **BLOCKED** → halt the orchestration loop, surface the blocker (`BLOCKED.md` `blocker_kind: mcp-runtime-unready`), no retries.

Shared impl in `lazy_core` (repo-agnostic, parameterized config), hermetic under `--test` via injected `probe`/`restart`/`stale_check` callables — same shape as today's `ensure_runtime`.

**M5 — Torn-build orphan handling = hybrid Prevent-and-Detect.**
- **Prevent (request-time guard):** a `PreToolUse` hook parses the tokenized Bash command; if it matches an exact long-build signature (`^tauri build`, `^cargo build --release`, `^npm run build`) it **fail-open blocks (`exit 2`)**, bubbling a specific signature that signals the orchestrator to take over the spawn — so the build runs under controller supervision and survives a subagent tear by construction. The matcher is scoped to exact long-build binary invocations to keep the false-positive rate low (never redirects `ls`/`cat`). This is the long-build analog of the existing `lazy-cycle-containment` deny-set.
- **Detect-and-recover (torn-bracket safety):** **Atomic Artifact Promotion** — build into a staging dir (`target/release_staging`), `os.replace()` the artifact into `target/release` only on `exit(0)` (atomic NTFS `MoveFileEx` / POSIX `rename`), so a mid-flight tear never corrupts the production artifact. Composed with a `--cycle-begin` git-consistency check: a pre-boot `.git/index.lock` (creation time older than orchestrator boot) ⇒ a previous op was torn ⇒ remove the lock and `git clean` the staging dir, neutralizing the uncommitted delta before the next cycle. Integrates with the existing `--cycle-end` friction detector (`detect_cycle_bracket_friction` / `unexpected-commits` / `cycle-bracket-break`).

### Determinism / harness principles (non-negotiable)

- Ownership/liveness state is **script-owned and read from on-disk signals** (`.runtime.lock.json` + the existing run marker), never LLM-inferred.
- Every new subcommand lives in `lazy_core` (shared, repo-agnostic) with AlgoBooth specifics in a parameterized config dict, hermetic under `--test` via injected `probe`/`restart`/`stale_check`/`spawn`-style callables — mirroring `ensure_runtime`.
- Enforcement is **fail-OPEN** where it gates a subagent op (consistent with `lazy-cycle-containment`); the existing `--cycle-begin/--cycle-end` bracket + deny-ledger is the friction-recording seam, not a new parallel mechanism.

## Implementation Phases

*(Indicative phasing — finalized by `/spec-phases`. The research lock removes the prior "mechanism TBD" gating.)*

- **Phase 1 — Cross-platform detached-spawn primitive + verifiable sentinel.** `spawn_detached(...)` (M2) and the `.runtime.lock.json` read/write + kernel-start-time extraction (M1) in `lazy_core`, hermetic `--test` coverage for both OS branches via injected callables and the breakaway-denied fallback path.
- **Phase 2 — Rework `--ensure-runtime` into the liveness/recovery state machine.** Extend (not replace) `ensure_runtime` to assert verifiable ownership and return the M4 verdict, with the bounded-retry recovery contract and HIJACKED/BLOCKED fail-safe. Persistent Service contract (M3.1).
- **Phase 3 — Enforce the long-build ownership boundary.** The `PreToolUse` guard (M5 Prevent) that fail-open-blocks subagent-owned long builds and signals the orchestrator to take over; Transient Build contract (M3.2) wait-and-promote. Tests in the containment/guard harness.
- **Phase 4 — Torn-build atomic-promotion + `--cycle-begin` git-consistency recovery.** Atomic Artifact Promotion staging→`os.replace` (M5 Detect) and the pre-boot `.git/index.lock` / `git clean` reconciliation, integrated with the `--cycle-end` friction detector.
- **Phase 5 — Wire the orchestrator.** Replace the hand-rolled `/lazy-batch` Step 1d.0 poll loop with the single liveness primitive call; mirror into the `/lazy-batch-cloud` and `/lazy`/`/lazy-cloud` coupled variants per their coupling rules.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Subagent cannot own a turn-crossing build | Cycle subagent backgrounds `tauri build` / `cargo build --release` | `PreToolUse` guard `exit 2`; op redirected to orchestrator; no reaped-mid-build orphan | guard test fixtures; deny-ledger |
| Detached spawn survives the subagent boundary on both OSes | Spawn via `spawn_detached` under simulated Job-Object / WSL-idle reaping | Child survives parent-tree teardown; breakaway-denied path falls back cleanly | `lazy_core` hermetic `--test` (Windows + POSIX branches) |
| Ownership is verifiable, not just health=200 | Query runtime ownership: orchestrator-spawned vs. (simulated) PID-reused / foreign-port-holder | Verdict `ownership_verified: true` only when `start_time` + `controller_session_id` match; HIJACKED on divergence | `lazy_core` hermetic `--test` |
| Runtime survives + is current across cycles | Boot runtime one cycle, run `/mcp-test` a later cycle | Verdict `state ∈ READY\|STALE→READY`, `mcp_tools_present: true`, `ownership_verified: true` | `lazy-state.py --ensure-runtime` JSON; live mcp-test cycle |
| Recovery is bounded, never infinite | Force STALE/DEAD repeatedly | `restart()` retried ≤5 with backoff, then BLOCKED — no unbounded loop | `lazy_core` hermetic `--test` |
| Hijacked port surfaces a blocker, never SIGKILL | Foreign process holds port 3333; recorded PID dead | `state: HIJACKED` → `terminal_blocker` set → `BLOCKED.md`; no kill of the foreign PID | `lazy_core` `--test`; BLOCKED.md sentinel |
| Orchestrator stops hand-rolling poll loops | mcp-test cycle in `/lazy-batch` | One subcommand call returns the structured verdict; no hand-composed until-loop in the cycle prompt | `/lazy-batch` Step 1d.0 prose; cycle transcript |
| No orphaned/corrupt artifact on a mid-build tear | Tear the controller while its build is in flight | Production artifact never half-written (staging + `os.replace`); pre-boot `.git/index.lock` reconciled at `--cycle-begin`; friction recorded | `git status`; `--cycle-end` friction ledger; staging dir state |

## Locked Decisions

> Resolved by `RESEARCH.md` (2026-06-20). All six baseline Open Questions are research-resolved with single strongly-recommended answers; none is a product-behavior fork (harness-internals feature, no AlgoBooth end-user surface). The MCP-coverage audit reads this section.

1. **LD1 — Ownership mechanism:** controller-spawned **detached process + verifiable on-disk JSON sentinel** (`.runtime.lock.json`), extending `--ensure-runtime` + the cycle-marker machinery. (Not an OS service; not a custom daemon.) [baseline Q1]
2. **LD2 — `--ensure-runtime` disposition:** **reworked/extended in place**, retained as the enforcement seam — NOT replaced by a distinct primitive. [baseline Q2]
3. **LD3 — Liveness verdict + recovery contract:** verdict `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}`, `state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}`; STALE/DEAD auto-recover with bounded backoff **≤5 attempts**, HIJACKED/BLOCKED surface a blocker and halt (never SIGKILL an unowned process). [baseline Q3]
4. **LD4 — Torn-build contract:** **hybrid Prevent-and-Detect** — `PreToolUse` fail-open guard (prevent) + Atomic Artifact Promotion (`staging` dir + `os.replace` on `exit(0)`) and `--cycle-begin` `.git/index.lock` / `git clean` reconciliation (detect-and-recover). [baseline Q4]
5. **LD5 — One mechanism or two:** **one** cross-platform `spawn_detached` OS primitive, **two** supervisory API contracts in `lazy_core` (Persistent Service vs. Transient Build). [baseline Q5]
6. **LD6 — Cross-platform supervision (stdlib-only):** Windows `creationflags` breakaway with `OSError` fallback; POSIX/WSL `systemd-run --user --scope` with `setsid` + keep-alive fallback. Temporal-identity extraction via `kernel32.GetProcessTimes` (Windows) and `/proc/[pid]/stat` (POSIX/WSL). [baseline Q6]

## Open Questions

None remaining at spec time — all six baseline Open Questions were research-answerable and are now locked in `## Locked Decisions`. Implementation-detail forks (e.g. exact backoff base/cap timing, the precise long-build signature regex set, whether to add advisory file locks in v1) are mechanical and resolved during `/spec-phases` / implementation, not product-behavior decisions.

## Research References

- `RESEARCH.md` (2026-06-20, Gemini deep research) — "Owning a Long-Lived Child Process Across an Ephemeral Agent-Turn Boundary." Key sections: Cross-Platform Spawn Recipes (LD6), Verifiable-Ownership Record (LD1), Liveness/Recovery Primitive (LD3), Torn-Build Orphan Handling (LD4), One Mechanism or Two (LD5), Actionable Mapping (answers to all eight prompt questions).
- `RESEARCH_SUMMARY.md` — distilled findings, adoptions, pitfalls, and the baseline-question resolution table.

Grounding context already in-repo:

- `repos/algobooth/.claude/skill-config/long-build-ownership.md` — the existing advisory long-build prose rule (becomes the M5 enforced guard).
- `user/scripts/lazy_core.py` (`ensure_runtime`, `_ENSURE_RUNTIME_DEFAULT_CONFIG`, ~L6166) — the existing runtime-ensure subcommand impl (reworked per LD2/M4).
- `user/skills/lazy-batch/SKILL.md` Step 1d.0 — where `--ensure-runtime` is called from the orchestrator session (rewired in Phase 5).
- `user/scripts/CLAUDE.md` — `--cycle-begin/--cycle-end` bracket + `detect_cycle_bracket_friction` (torn-bracket / unexpected-commits friction recording; the M5 detect seam).
- Session-log evidence: `8ae22371` (runtime dies at turn boundary), `18e1d3d7` (`--ensure-runtime` reaped in subagent subprocess; `health_code: 0` tell), `5c33b6ba` (orphaned `tauri build` + hand-rolled poll loops).
