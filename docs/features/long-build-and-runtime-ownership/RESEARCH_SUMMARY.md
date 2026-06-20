# Research Summary — Long-Build + Runtime Ownership

> Distilled from `RESEARCH.md` (Gemini deep research, ingested 2026-06-20). This file gates downstream `/spec-phases` / `/write-plan`. It records what the research locked, what we adopt, the pitfalls to design around, and which baseline-spec Open Questions are now resolved.

## Key Findings (relevant to our baseline)

1. **Ownership = controller-spawned detached process + a verifiable on-disk sentinel.** The recommended architecture is a *hybrid detached supervisor with verifiable on-disk sentinels*: the orchestrator spawns the child detached from its (and any subagent's) process tree, then records a temporal identity fingerprint — `(pid, kernel start_time, controller_session_id)` — in a JSON sidecar (`.runtime.lock.json`). This is preferred over OS-service-level runtimes (need admin privileges; break hermetic `--test`) and over a custom daemon (native stdlib primitives suffice). It cleanly extends the existing `--ensure-runtime` + cycle-marker machinery rather than replacing it. **(Answers Open Q1 → option (a).)**

2. **Liveness is necessary but not sufficient — ownership must be *verifiable*.** A 200 on `/health` does NOT prove the runtime is ours: PIDs get reused, and a stale `tauri dev` from an aborted session can hold port 3333 and answer health perfectly while serving an outdated source tree (the `health_code: 0` / hijacked-port failure modes in the baseline). The fix is the temporal fingerprint: compare the kernel-reported `start_time` against the sentinel to defeat PID reuse, and compare `controller_session_id` against the live session to prove current-orchestrator ownership. Extract `start_time` via stdlib: `kernel32.GetProcessTimes` through `ctypes` (Windows), `/proc/[pid]/stat` field 22 → epoch via `SC_CLK_TCK` (POSIX/WSL). Optionally harden with advisory file locks (`msvcrt.locking` / `fcntl.flock`).

3. **Cross-platform spawn recipes are concrete and stdlib-only.**
   - **Windows:** `subprocess.Popen(creationflags = DETACHED_PROCESS(0x8) | CREATE_NEW_PROCESS_GROUP(0x200) | CREATE_BREAKAWAY_FROM_JOB(0x01000000))`, wrapped in `try/except OSError` to fall back to detachment-without-breakaway when a Job Object forbids breakaway (`ERROR_ACCESS_DENIED`). Job Objects with `KILL_ON_JOB_CLOSE` are the exact reaping mechanism we are escaping.
   - **POSIX/WSL:** `start_new_session=True` (setsid), wrapped in `systemd-run --user --scope --quiet --same-dir` on WSL to bypass WSL's `instanceIdleTimeout`/`vmIdleTimeout` (the lightweight VM suspends ~15s after the last interactive terminal exits, killing naive detached children regardless of session leadership). If systemd is unavailable, fall back to setsid + a `nohup sleep infinity` keep-alive. `PR_SET_PDEATHSIG` is **counterproductive** here (it would kill the child with the parent).

4. **One OS-level spawn primitive, two supervisory API contracts.** CI platforms (GH Actions, GitLab, Buildkite) universally *separate* terminating builds from long-lived services, but the *underlying OS primitive should be unified*. Research recommendation: ONE `spawn_detached_*` wrapper shared by both `tauri build` and `tauri dev`, but **two distinct `lazy_core` contracts** — (a) **Persistent Service** (sentinel + `/health` polling + full READY/STALE/DEAD state machine; deliberately leaves the process behind for re-attach next cycle) and (b) **Transient Build** (synchronous wait-and-promote; detached only to survive subagent reaping, orchestrator awaits conclusion, does NOT abandon for a future cycle). **(Answers Open Q5.)**

5. **Liveness/recovery is a single deterministic state machine, replacing hand-rolled poll loops.** Verdict schema `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}` with `state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}`. Phases: Identity (sentinel + kernel start_time) → Staleness (injected `stale_check`) → Health (injected `probe`). Recovery contract: STALE/DEAD → bounded `restart()` (exponential backoff, **≤5 attempts**), rewrite the lock, return READY; **HIJACKED → never SIGKILL a process we don't own** (security/stability risk) → surface `terminal_blocker` → BLOCKED; BLOCKED → halt the agent loop, no retries. Hermetic via injected callables — same shape as today's `ensure_runtime`. **(Answers Open Q3.)**

6. **Torn-build orphan handling = hybrid Prevent-and-Detect.**
   - **Prevent:** a `PreToolUse` hook acts as a request-time guard, parsing the tokenized Bash command; if it matches a long-build signature (`^tauri build`, `^cargo build --release`, `^npm run build`) it **fail-open blocks (exit 2)**, bubbling a signature that signals the controller to take over the spawn — so the build runs under controller supervision and survives the subagent tear by construction. Scope the matcher to exact binary invocations to avoid redirecting `ls`/`cat` (low false-positive rate).
   - **Detect-and-recover:** make torn builds *mathematically* safe via **Atomic Artifact Promotion** — build into a staging dir, `os.replace()` the artifact into place only on `exit(0)` (atomic NTFS `MoveFileEx` / POSIX `rename`), so a mid-flight tear never corrupts the production artifact. Compose with a `--cycle-begin` git-consistency check that deletes a pre-boot `.git/index.lock` and `git clean`s the staging dir, neutralizing any uncommitted delta before the next cycle. **(Answers Open Q4 → both.)**

## Ideas to Adopt (from prior art)

- **Temporal identity fingerprint over PID-only tracking** (the PID-reuse / zombie-port defense) — adopt the `(pid, start_time, controller_session_id)` triple in the sentinel.
- **`systemd-run --user --scope`** as the WSL survival mechanism — adopt as the POSIX/WSL spawn wrapper, with the setsid + keep-alive fallback.
- **Atomic Artifact Promotion via a staging dir + `os.replace`** — adopt for the transient-build contract.
- **Unified spawn primitive, bifurcated supervisory API** — adopt directly; it minimizes OS-specific branching while keeping per-shape lifecycle semantics.
- **Bounded exponential-backoff recovery capped at 5 attempts** — adopt as the loop-prevention contract for the liveness primitive.

## Pitfalls / Concerns to Design Around

- **Windows Job Object breakaway denial.** `CREATE_BREAKAWAY_FROM_JOB` raises `ERROR_ACCESS_DENIED` when the parent Job Object sets `BREAKAWAY_OK = false`. Catch the `OSError`, fall back to plain `DETACHED_PROCESS`; if still reaped, fail cleanly and tell the operator the host forbids background daemonization (do not silently produce a reaped runtime).
- **WSL VM idle reaping.** Two timers (`instanceIdleTimeout` ~15s, `vmIdleTimeout`). Even `vmIdleTimeout=-1` can still kill background processes if systemd is not enabled in `wsl.conf` — `systemd-run --user` is the robust bypass.
- **Zombie port (hijack) vs staleness.** An orphaned child thread holding the TCP port passes `/health` while the recorded parent PID is dead → HIJACKED. The primitive MUST refuse to blindly `SIGKILL` an unverified port-holder; surface a blocker instead.
- **Fail-open guard false positives.** The `PreToolUse` ownership-boundary guard must scope its matcher to exact long-build binary invocations to avoid redirecting legitimate short-lived subprocesses into heavy controller logic.

## Baseline Decisions Revisited / Resolved

| Baseline Open Question | Research verdict | Disposition |
|------------------------|------------------|-------------|
| Q1 — ownership mechanism (orchestrator+handle vs daemon vs OS-service) | (a) controller-spawned detached process + JSON sentinel, extends `--ensure-runtime` | **Resolved** — locked to (a) |
| Q2 — `--ensure-runtime` rework vs replace | Rework/extend in place; keep it as the enforcement seam | **Resolved** — extend, not replace |
| Q3 — liveness verdict + recovery contract | `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}`; STALE/DEAD auto-recover ≤5, HIJACKED/BLOCKED surface | **Resolved** |
| Q4 — torn-build contract (prevent / detect / both) | Both — PreToolUse prevent + atomic-promotion detect-and-recover | **Resolved** — both |
| Q5 — one mechanism or two | One spawn primitive, two supervisory API contracts | **Resolved** |
| Q6 — cross-platform supervision | Windows creationflags-breakaway; POSIX/WSL `systemd-run --user` + setsid fallback; stdlib-only | **Resolved** |

All six baseline Open Questions are now research-resolved with single strongly-recommended answers; none is a product-behavior fork (this is a harness-internals feature with no AlgoBooth end-user surface — the "user" is the orchestrator). The recommendations are integrated into the finalized SPEC's Technical Design and `## Locked Decisions`.
