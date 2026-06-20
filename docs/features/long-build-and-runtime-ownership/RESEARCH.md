# Owning a Long-Lived Child Process Across an Ephemeral Agent-Turn Boundary — Gemini Deep Research

> Source: Gemini deep research run against `RESEARCH_PROMPT.md`, ingested 2026-06-20 (direct-drop, workstation). Stdlib-only Python process supervision across Windows 10/11 Developer Mode + WSL/POSIX.

## Recommendation Up Front

For a standard-library-only Python controller operating across Windows 10/11 Developer Mode and WSL/POSIX environments, the recommended architecture is a **hybrid detached supervisor utilizing verifiable on-disk sentinels**. This architecture relies on a controller-spawned detached process tracked by a cryptographic-like identity fingerprint (combining the Process ID, kernel-derived absolute start-time, and orchestrator session ID) stored in a structured JSON artifact.

This approach is chosen over full OS service-level runtimes (Windows Services, root-level systemd daemons) because it circumvents the need for administrative host privileges during installation, preserving the hermetic, injectable nature of the test environment. It is chosen over a fully daemonized custom-built supervisor because native stdlib primitives — `subprocess.Popen` with precise bitwise creation flags on Windows, and `systemd-run --user` (or `start_new_session=True` + persistent keep-alive) on WSL — are sufficiently robust to decouple the child from the ephemeral subagent's process tree. By generating a temporal identity fingerprint via `ctypes` bindings to the respective OS kernels, the orchestrator can verifiably prove ownership of a runtime state — natively distinguishing a live, orchestrator-owned background process from a stale orphan or a hijacked TCP port — satisfying deterministic liveness recovery without hand-rolled polling loops.

## Cross-Platform Spawn Recipes

The foundational challenge in surviving the ephemeral agent-turn boundary is defeating the OS default behavior of aggressively reaping child processes when the parent environment is torn down. LLM subagents are typically wrapped in restricted terminal sessions, CI jobs, or strict orchestration brackets that terminate the entire process tree at turn end.

### Windows OS Primitives

On Windows, process hierarchy is governed by **Job Objects**. If the orchestrator/shell invoking the subagent is part of a Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, any subprocess spawned by the subagent is forcibly terminated when the subagent exits, regardless of standard detachment flags. This is common in automated test harnesses and CI runners.

To bypass this natively with only `subprocess`, combine three `creationflags` via bitwise OR:
- `DETACHED_PROCESS` (`0x00000008`) — separates the new process from the parent's console, preventing console termination cascades.
- `CREATE_NEW_PROCESS_GROUP` (`0x00000200`) — isolates Ctrl+C signal propagation.
- `CREATE_BREAKAWAY_FROM_JOB` (`0x01000000`) — explicitly escapes the parent's kill-on-close job boundary.

A robust implementation must anticipate `ERROR_ACCESS_DENIED`: if the parent Job Object enforces `JOB_OBJECT_LIMIT_BREAKAWAY_OK = false`, the breakaway attempt fails immediately. The recipe must fall back gracefully to standard detachment, recognizing the environment strictly forbids background daemonization.

```python
import subprocess
import os

def spawn_detached_windows(cmd_list, env=None):
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000

    flags_breakaway = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
    flags_standard = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env or os.environ.copy(),
        "close_fds": True,
    }
    try:
        # Attempt primary breakaway from the parent Job Object
        return subprocess.Popen(cmd_list, creationflags=flags_breakaway, **kwargs)
    except OSError:
        # Fallback if the Job Object explicitly restricts breakaway
        return subprocess.Popen(cmd_list, creationflags=flags_standard, **kwargs)
```

### POSIX and WSL Primitives

In standard POSIX, `os.setsid()` inside a double-fork (or `start_new_session=True` in `subprocess.Popen`) creates a new session and process group, allowing the child to be reparented to init (PID 1) on controller exit, surviving the ephemeral boundary. Note `prctl(PR_SET_PDEATHSIG)` is **counterproductive** here — it makes the child die when the parent dies, contradicting the requirement that the child outlive the controller.

**WSL introduces a unique hardware-virtualization lifecycle constraint that breaks naive POSIX detachment.** WSL monitors active interactive sessions. When the last interactive terminal exits, the `instanceIdleTimeout` / `vmIdleTimeout` timers (`%USERPROFILE%\.wslconfig`; defaults ~15s instance, ~60s VM) forcibly suspend/shut down the WSL instance or the lightweight utility VM, abruptly terminating all background daemonized processes regardless of session leadership.

To ensure verifiable survival in WSL, integrate with systemd or use artificial keep-alives. Recent WSL distros run systemd as PID 1; running the long-lived service as a transient unit via `systemd-run --user` ensures persistence in a dedicated `user.slice`. If systemd is unavailable, couple standard POSIX detachment with an infinite sleeper (`nohup sleep infinity & disown`) injected into the base session to keep the instance alive by tricking `instanceIdleTimeout`.

```python
def spawn_detached_posix(cmd_list, env=None, is_wsl=False, has_systemd=False):
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env or os.environ.copy(),
        "start_new_session": True,
    }
    if is_wsl and has_systemd:
        # Wrap in a systemd transient scope to bypass instanceIdleTimeout
        cmd_list = ["systemd-run", "--user", "--scope", "--quiet", "--same-dir"] + cmd_list
        return subprocess.Popen(cmd_list, **kwargs)
    # Standard POSIX detachment; requires separate keep-alive in WSL without systemd
    return subprocess.Popen(cmd_list, **kwargs)
```

## Verifiable-Ownership Record

Demonstrating that a persistent process is owned by the current legitimate orchestrator requires far more rigor than checking that a process answers on a port (200 OK on TCP 3333). PIDs are rapidly reused; a stale `tauri dev` from an aborted session can still be bound to the port, answering health checks perfectly while operating on an outdated source tree. Relying solely on liveness lets the harness trust a hijacked or orphaned process.

To establish verifiable ownership natively, the orchestrator records a **sentinel** state file fingerprinting the exact temporal identity of the spawned process.

### Sentinel Schema and Defenses

A strictly structured JSON artifact (e.g. `.runtime.lock.json`) written to the project root immediately after a successful OS-level spawn. Required fields:

| Field | Type | Description |
|-------|------|-------------|
| `controller_session_id` | String | UUID generated at the start of the overarching orchestration bracket. |
| `pid` | Integer | OS-assigned PID of the spawned child. |
| `start_time` | Float | Absolute process start time from kernel metrics — ensures PID-reuse safety. |
| `port` | Integer | Designated TCP port claimed by the runtime. |
| `artifact_hash` | String | Commit hash / modified-timestamp of source at boot, for staleness checks. |

Comparing the kernel-reported `start_time` against the sentinel confirms the PID has not been recycled by a foreign process. Comparing `controller_session_id` against the live session id verifies the runtime belongs to the current active orchestrator (vs. one from a previous crashed controller).

### Kernel Start-Time Extraction via Stdlib

Python's `os`/`subprocess` don't expose process creation time, so query the kernels via `ctypes`.

**Windows** — `GetProcessTimes` (kernel32) populates a `FILETIME` (100-ns intervals since 1601-01-01 UTC); open a handle with `OpenProcess` + `PROCESS_QUERY_LIMITED_INFORMATION` (`0x1000`):

```python
import ctypes
from ctypes.wintypes import DWORD

class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", DWORD), ("dwHighDateTime", DWORD)]

def get_windows_process_start_time(pid):
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h_process:
        return None
    creation_time = FILETIME(); exit_time = FILETIME()
    kernel_time = FILETIME(); user_time = FILETIME()
    success = kernel32.GetProcessTimes(
        h_process, ctypes.byref(creation_time), ctypes.byref(exit_time),
        ctypes.byref(kernel_time), ctypes.byref(user_time))
    kernel32.CloseHandle(h_process)
    if success:
        time_100ns = (creation_time.dwHighDateTime << 32) | creation_time.dwLowDateTime
        return (time_100ns - 116444736000000000) / 10000000.0  # → Unix epoch sec
    return None
```

**POSIX/WSL** — no direct ctypes syscall; parse `/proc/[pid]/stat`. Field 22 (index 21) is `starttime` in jiffies since boot. Convert via `os.sysconf('SC_CLK_TCK')`, then add absolute boot time (`time.time() - /proc/uptime`):

```python
import os, time

def get_posix_process_start_time(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat_fields = f.read().split()
        start_time_ticks = int(stat_fields[21])           # field 22
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
        ticks_per_sec = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
        boot_time = time.time() - uptime_seconds
        return boot_time + (start_time_ticks / ticks_per_sec)
    except (FileNotFoundError, IndexError):
        return None
```

Augment the JSON sentinel with **advisory file locks**: Windows `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` (non-blocking, raises `OSError` if another orchestrator holds it); POSIX `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`. Strict temporal fingerprinting + advisory OS locks = an impenetrable verifiable ownership record.

## Liveness/Recovery Primitive

Once ownership is established, eliminate hand-rolled polling loops (the fragile rebuild → health-poll → telemetry-inspect chains) with a unified deterministic state machine driven by a single primitive. The existing `ensure_runtime` subcommand is the exact enforcement seam for this consolidation.

### Structured Liveness Verdict Schema

| Field | Type | Description |
|-------|------|-------------|
| `state` | String | `READY`, `STALE`, `HIJACKED`, `DEAD`, or `BLOCKED`. |
| `ownership_verified` | Boolean | True if PID + start time match the sentinel. |
| `health_code` | Integer | `/health` HTTP status (200, 503, or 0 = connection refused). |
| `mcp_tools_present` | Boolean | True if required MCP tools are actively registered. |
| `terminal_blocker` | String/Null | Actionable error if `BLOCKED`, indicating why recovery is impossible. |

### Recovery State Machine and Semantics

Strict contract for idempotency, loop-prevention, and hermetic testing via injected callables:

1. **Identity Phase (ownership check).** Parse sentinel, query kernel for recorded PID. PID exists but `start_time` diverges → port held by a foreign process → `HIJACKED`. PID does not exist → crashed → `DEAD`. Both align → ownership verified.
2. **Staleness Phase.** If owned, invoke injected `stale_check(artifact_hash)` — source files newer than runtime `start_time` → outdated logic → `STALE`.
3. **Health Phase.** If owned + not stale, invoke injected `probe()` → HTTP GET `/health`. Connection refused (0) despite a live PID (zombie/defunct) → `DEAD`. 200 OK → ready.

**Recovery contract actions:**
- **STALE or DEAD** → auto-recover boundary. Trigger `restart()` in a bounded exponential-backoff loop (strictly capped at 5 attempts). On successful spawn + health, rewrite `.runtime.lock.json` and return `READY`.
- **HIJACKED** → strict fail-safe: do NOT `SIGKILL` a process it does not verifiably own (severe security/stability risk). Surface a `terminal_blocker` (e.g. "Port 3333 bound by foreign process PID 943; manual intervention required") → `BLOCKED`.
- **BLOCKED** → orchestration halts entirely. Framework intercepts the blocker, stops the agent loop, bubbles the error to UI/telemetry. No further retries.

This makes `ensure_runtime` an idempotent gatekeeper that cleanly replaces ad-hoc polling with a provably correct state assertion.

## Torn-Build Orphan Handling

Terminating, artifact-producing processes (`tauri build` / `cargo build --release`) mutate disk heavily (intermediate files, object caches, partial binaries). A subagent torn mid-build generates an orphaned build state. Use a **hybrid Prevent-and-Detect model**.

### Prevent by Ownership

Long builds must be prevented from running inside the ephemeral worker's process tree via a **`PreToolUse` hook** acting as a request-time guard. It parses the tokenized/AST form of the Bash command; if it matches a long-lived build signature (e.g. `^tauri build`, `^npm run build`), it **fail-open blocks** by exiting code 2 — intercepting the command before the subagent's shell, bubbling a specific error signature, and signaling the controller to take over the spawn. Executing the build under controller supervision means it survives the subagent's termination by construction.

### Detect-and-Recover (Torn-Bracket Safety)

If the controller itself crashes / is SIGKILL'd mid-build, the repo is left corrupted (`.git/index.lock`, half-written `target/release` binaries). Make torn builds mathematically safe via **Atomic Artifact Promotion**: build outputs to an isolated staging dir (`target/release_staging`); only on `exit(0)` does the controller `os.replace('target/release_staging/app.exe', 'target/release/app.exe')`. Because `os.replace` uses atomic POSIX `rename()` / NTFS `MoveFileEx`, a mid-flight tear never leaves the production artifact corrupted.

Compose with a Git-consistency check in the `--cycle-begin` hook: if a `.git/index.lock` exists with a creation timestamp older than the orchestrator boot time, a previous op was torn — execute `rm -f .git/index.lock` and `git clean -fdx target/release_staging`, neutralizing the uncommitted delta and restoring a pristine tree before the next cycle.

## One Mechanism or Two?

CI platforms (GitHub Actions, GitLab Runners, Buildkite, devcontainers) consistently **separate** the orchestration of terminating builds from long-lived services: service containers are daemonized / docker-mapped / init-supervised, while build steps run as synchronous transient processes attached to the runner's stdout pipes for real-time telemetry.

Despite this product-level separation, the underlying **OS Python primitives should be unified**: the same `spawn_detached_windows` / `spawn_detached_posix` (CREATE_BREAKAWAY_FROM_JOB / systemd-run) for BOTH the `tauri build` artifact and the `tauri dev` MCP runtime. But the **supervisory API contracts in `lazy_core.py` must be bifurcated**:

1. **Persistent Service Contract** — Verifiable Sentinel (JSON lockfile), active `/health` polling, full READY/STALE/DEAD state machine. Deliberately detaches and leaves the process behind for seamless re-attach in subsequent cycles.
2. **Transient Build Contract** — synchronous wait-and-promote. Spawned with detached OS flags to protect from subagent reaping, but the orchestrator explicitly awaits the build's conclusion (or gathers stdout for telemetry), then applies Atomic Artifact Promotion. Does NOT abandon the process for a future cycle.

Unifying the low-level spawn while separating the API contract reduces OS-specific branching while keeping appropriate lifecycle semantics per process shape.

## Pitfalls and Failure Modes

- **Windows Job Object traps.** Restricted CI runners / PowerShell constraints may revoke `JOB_OBJECT_LIMIT_BREAKAWAY_OK`; passing `CREATE_BREAKAWAY_FROM_JOB` then raises `ERROR_ACCESS_DENIED`. Catch the `OSError`, fall back to `DETACHED_PROCESS` without breakaway. If still reaped by job closure, fail cleanly and notify the user that the host forbids background daemonization.
- **WSL VM reaping quirks.** Two separate timers: `instanceIdleTimeout` (instance, ~15s of terminal inactivity) and `vmIdleTimeout` (Hyper-V utility VM). Even `vmIdleTimeout=-1` can still terminate background processes if systemd is not enabled via `wsl.conf` — `start_new_session=True` fails as the whole Linux instance suspends despite reparenting to init. `systemd-run --user` bypasses this (systemd holds the session hooks preventing instance idle termination).
- **Active port hijacking vs. staleness.** A crashed process whose orphaned child thread (e.g. a node worker) still holds the TCP port = a "Zombie Port": sentinel PID validation fails (recorded parent died) yet `/health` passes. The primitive must respect `HIJACKED` and refuse to blindly kill — `SIGKILL` on unknown PIDs by port occupancy is a massive security risk.
- **Fail-open false-positives.** The `PreToolUse` ownership-boundary guard must scope its matcher to exact binary invocations (literal `cargo build`, `npm run dev`) to avoid redirecting legitimate short-lived subprocesses (`ls`, `cat`) into heavy controller logic — prioritize a low false-positive rate to preserve subagent speed.

## Actionable Mapping (answers to Open Questions 1–8)

1. **Central fork — which ownership level?** → **(A)** Controller-spawned detached process tracked via a structured JSON sentinel (PID + start-time), natively enhanced by `systemd-run --user` on WSL. Uniform, hermetically testable, no admin host services / third-party daemon supervisors.
2. **Windows, no third-party deps.** → `subprocess.Popen` with `creationflags = 0x00000008 | 0x00000200 | 0x01000000` (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB), wrapped in `try/except OSError` to gracefully fall back when the Job Object forbids breakaway.
3. **POSIX/WSL, stdlib-reachable.** → Wrap in `systemd-run --user --scope --same-dir --quiet`. If systemd inactive in WSL, fall back to `start_new_session=True` + a background `nohup sleep infinity` keep-alive to bypass `instanceIdleTimeout`.
4. **Verifiable-ownership record.** → `.runtime.lock.json` sidecar with `controller_session_id`, `pid`, `start_time` (Unix epoch float), `artifact_hash`. Validate via `kernel32.GetProcessTimes` (Windows) and `/proc/[pid]/stat` jiffies→epoch (POSIX, via `SC_CLK_TCK`).
5. **Liveness verdict schema + recovery semantics.** → `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}`. State machine: `READY → STALE → DEAD` (auto-restart, ≤5 attempts) → `HIJACKED` → `BLOCKED` (halts execution, surfaces blocker). Auto-recover boundary = STALE/DEAD; surface-blocker = HIJACKED/BLOCKED.
6. **Torn-build safety.** → Atomic artifact promotion (`os.replace` from a staging dir) + a pre-cycle orchestrator check that detects/deletes orphaned `.git/index.lock` files and reconciles via `git clean`.
7. **One mechanism or two?** → One OS-level spawning primitive (the detached-process wrapper), two distinct supervisory API contracts in `lazy_core.py`: persistent service = backgrounded Verifiable-Sentinel contract; transient build = synchronous wait-and-promote — mirroring CI patterns.
8. **Fail-open ownership-boundary guard.** → `PreToolUse` hook parsing the requested Bash AST; if it exactly matches a long-lived signature (e.g. `tauri dev`), exit code 2 (fail-open block), bubble a specific signature, trigger the orchestrator to take over the spawn.

## Selected Sources

Microsoft conductor #195 (CREATE_BREAKAWAY_FROM_JOB); Python `subprocess` docs; mozprocess `winprocess.py`; microsoft/WSL #10138, #8654, discussion #8659 (vmIdleTimeout); Microsoft Learn "Use systemd to manage Linux services with WSL"; systemd-run transient services; Win32 `GetProcessTimes` / `FILETIME` docs; psutil #2521 (`/proc/[pid]/stat` start-time); Python `msvcrt` docs (`LK_NBLCK`); `.git/index.lock` recovery guides; "Deterministic Governance and Proactive Protection for Autonomous Coding Agents"; Claude Code hooks docs.
