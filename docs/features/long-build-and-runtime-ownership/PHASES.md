# Implementation Phases — Long-Build + Runtime Ownership

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a harness-internals feature entirely in `lazy_core`/`lazy-state.py` Python, a stdlib bash `PreToolUse` hook, `settings.json`, and harness prose/skill docs. There is NO AlgoBooth app surface, store, audio path, UI state, or MCP-reachable behavior in any deliverable (the SPEC's "User Experience" section states explicitly: "There is **no end-user-facing AlgoBooth product surface**"). All verification is via the hermetic Python `--test` smoke harnesses and bash hook-pipe tests — the `mcp-testing/SPEC.md` "build tooling / harness script" untestable class. The "runtime" this feature OWNS is the dev/MCP server as a *managed process*, not a surface this feature's own tests assert through MCP.

## Cross-feature Integration Notes

The SPEC's only `**Depends on:**` entry is `unified-pipeline-orchestrator` with `kind=composes` (NOT `hard`) — so per the Depends-on resolution protocol no mandatory upstream PHASES.md reality-check is required. It is nonetheless Complete with a PHASES.md, and this feature builds directly atop two of its Phase-5 deliverables, so the load-bearing integration points are recorded here:

- **unified-pipeline-orchestrator (kind=composes, Complete):** This feature EXTENDS that feature's `lazy-state.py --ensure-runtime` subcommand (`lazy_core.ensure_runtime`, `lazy_core.py` ~L6166) and the orchestrator-loop / cycle-subagent bracket model (`--cycle-begin`/`--cycle-end`, `detect_cycle_bracket_friction`, `cycle_end_friction_check`) it owns. The integration contracts locked by the upstream and consumed below:
  - `ensure_runtime(repo_root, *, config, probe, restart, stale_check)` returns `{status, mcp_tools_present, health_code}` today. **LD2 requires this be reworked/extended IN PLACE (not replaced)** to additionally emit the M4 verdict `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}`. The injected-callable hermeticity contract (`probe`/`restart`/`stale_check`) is preserved and extended with a `spawn`-style callable (Phase 1).
  - `_ENSURE_RUNTIME_DEFAULT_CONFIG` (L6110) is the AlgoBooth-specifics parameterization dict (health_url, restart_command, native_globs, mcp_tool_name). New config keys (lock path, staging dir, port) are added here — NOT hard-coded into the shared flow.
  - The cycle-bracket friction seam (`detect_cycle_bracket_friction` L7194 / `cycle_end_friction_check` L7349 / `append_friction_ledger_entry`, `kind: process-friction` deny-ledger) is the EXISTING torn-bracket/unexpected-commits detector that Phase 4's `--cycle-begin` git-consistency reconciliation composes with — NOT a new parallel mechanism.
  - Step 1d.0 of `lazy-batch/SKILL.md` (L552-599) is where `--ensure-runtime` is called from the orchestrator session; Phase 5 rewires it to consume the verdict, mirrored into the coupled `/lazy`, `/lazy-cloud`, `/lazy-batch-cloud` wrappers per the CLAUDE.md coupled-pair rules.

## Validated Assumptions

This feature's load-bearing assumptions are **code-provable** (the existing `ensure_runtime` shape, the injected-callable hermeticity contract, the cycle-marker fields, the hook-input `agent_id`/`cwd` schema) — all verified by Read/Grep during the touchpoint audit, not by a code-read of runtime behavior. The two genuinely **runtime-coupled** mechanisms (cross-platform detached spawn surviving a process-tree teardown; kernel `start_time` extraction on each OS) are NOT assertable from source and are therefore made **explicit early deliverables**: Phase 1 carries hermetic `--test` coverage driving BOTH OS branches (Windows `creationflags` + breakaway-denied fallback; POSIX/WSL `start_new_session`/`systemd-run`) through injected spawn callables, and a Runtime Verification spike row driving a REAL detached child through a simulated parent-tree teardown. No load-bearing runtime assumption rides unverified into a later phase.

**SPEC-example capability audit:** the SPEC's code/API examples consume stdlib-only surfaces — `subprocess.Popen(creationflags=...)`, `ctypes`→`kernel32.GetProcessTimes`, `/proc/[pid]/stat` field 22, `os.replace`, `subprocess.Popen(start_new_session=True)`, `systemd-run --user --scope`, `msvcrt.locking`/`fcntl.flock`. These are Python stdlib / OS facilities, not a project API that could carry an `unimplemented!`/`return Err` rejection path; the negative-evidence grep target (an explicitly-rejected project capability) does not apply — there is no in-repo implementation that rejects these constructs. The one in-repo surface a SPEC example extends, `ensure_runtime`, was read in full (L6166-6263) and supports the documented extension (injected callables, config dict, status return) with no rejection path. No capability-audit halt.

### Phase 1: Cross-platform detached-spawn primitive + verifiable on-disk sentinel

**Scope:** The two M1/M2 foundations in `lazy_core.py`, both stdlib-only and hermetically testable via injected callables: (a) `spawn_detached(...)` — one cross-platform wrapper that spawns a child detached from the parent (and any subagent) process tree, with the Windows `creationflags` breakaway + `OSError` fallback and the POSIX/WSL `start_new_session` / `systemd-run --user --scope` + `setsid` keep-alive fallback; (b) the `.runtime.lock.json` sentinel read/write plus kernel-`start_time` extraction (`kernel32.GetProcessTimes` via `ctypes` on Windows; `/proc/[pid]/stat` field 22 → epoch via `SC_CLK_TCK` on POSIX/WSL) and the ownership-verification predicate (compare recorded `(pid, start_time, controller_session_id)` against the live kernel/session). No `ensure_runtime` rework yet — this phase delivers the primitives the later phases compose.

**Deliverables:**
- [x] `spawn_detached(cmd, *, cwd, spawn=None, platform=None) -> {pid, start_time}` in `lazy_core.py` — Windows branch (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB`) with `try/except OSError` → plain `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` fallback on `ERROR_ACCESS_DENIED`; POSIX/WSL branch (`start_new_session=True`, wrapped in `systemd-run --user --scope --quiet --same-dir` when available, `setsid` + `nohup` keep-alive fallback). Injectable `spawn`/`platform` for hermetic tests. `PR_SET_PDEATHSIG` deliberately NOT used (documented inline).
- [x] `kernel_start_time(pid, *, platform=None) -> float | None` in `lazy_core.py` — Windows `ctypes`→`kernel32.GetProcessTimes`; POSIX/WSL `/proc/[pid]/stat` field 22 → epoch via `SC_CLK_TCK`. Best-effort, never raises (None on any error — the DEAD/HIJACKED classification consumes None).
- [x] `write_runtime_lock(repo_root, *, pid, start_time, port, artifact_hash, controller_session_id)` and `read_runtime_lock(repo_root) -> dict | None` in `lazy_core.py` — atomic temp-file `os.replace` write of `.runtime.lock.json` at the project root with the five LD1 fields; best-effort read returns None on missing/corrupt.
- [x] `verify_runtime_ownership(lock, *, live_session_id, kernel_start_time_fn) -> bool` in `lazy_core.py` — True iff recorded `start_time` matches the kernel-reported start_time for `lock['pid']` AND `controller_session_id == live_session_id`; defeats PID-reuse + foreign-controller cases.
- [x] New config keys in `_ENSURE_RUNTIME_DEFAULT_CONFIG` (lock filename, port) — parameterized, NOT hard-coded into the flow.
- [x] Tests: covering BOTH OS branches of `spawn_detached` (success + breakaway-denied fallback) via injected `spawn`/`platform`; `kernel_start_time` parse fixtures (a synthetic `/proc/stat` line + a stubbed `GetProcessTimes`); `verify_runtime_ownership` matrix (match → True; divergent start_time → False; foreign session → False; missing pid → False); `.runtime.lock.json` round-trip + corrupt-read → None. (Landed in `test_lazy_core.py` — the file that characterizes shared `lazy_core` helpers per scripts/CLAUDE.md — rather than `lazy-state.py --test`, keeping the byte-pinned state-machine baselines unshifted; ⚖ see Implementation Notes.)

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` exercises the new `spawn_detached` / `kernel_start_time` / `write_runtime_lock` / `verify_runtime_ownership` fixtures and the full smoke suite stays green (byte-pinned baseline regenerated through `_normalize_smoke_output`).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Detached-spawn survival spike (runtime spike — workstation-eligible): a REAL child spawned via `spawn_detached` from a short-lived parent process OUTLIVES the parent's exit (observe the child PID still alive after the parent returns, on this host's OS branch). This is a runtime artifact (observed live PID survival), NOT a static code trace — it is the one assumption (M2 detached survival) source cannot prove.

**MCP Integration Test Assertions:** N/A — no runtime-observable AlgoBooth/MCP surface in this phase (pure `lazy_core` Python primitives, asserted by the hermetic `--test` harness; the cross-OS survival assumption is covered by the Runtime Verification spike row above, not via MCP).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `spawn_detached`, `kernel_start_time`, `write_runtime_lock`/`read_runtime_lock`, `verify_runtime_ownership`; extend `_ENSURE_RUNTIME_DEFAULT_CONFIG` with lock/port keys. (verified: `_ENSURE_RUNTIME_DEFAULT_CONFIG` L6110, `ensure_runtime` L6166, `claude_state_dir` L6539 — net-new functions sit alongside.)
- `user/scripts/lazy-state.py` — add `--test` fixtures for the new primitives (in-file smoke harness; verified existing harness ~L6591+).
- `user/scripts/test_lazy_core.py` — characterize the new shared helpers directly (verified: this file characterizes `lazy_core` helpers per scripts/CLAUDE.md).

**Testing Strategy:** Fully hermetic. Both OS branches are driven through injected `spawn`/`platform`/`kernel_start_time_fn` callables — no real cross-platform host needed for the unit layer (mirrors how `ensure_runtime` injects `probe`/`restart`/`stale_check`). The ONE genuinely runtime-coupled assumption (a detached child surviving its parent's teardown) is the Runtime Verification spike, run live on whatever host executes the validation cycle.

**Integration Notes for Next Phase:**
- The verdict-emitting `ensure_runtime` rework (Phase 2) consumes `read_runtime_lock` + `verify_runtime_ownership` + `kernel_start_time` directly — these are the Identity-phase inputs of the M4 state machine.
- `controller_session_id` is generated once at the orchestration bracket start; Phase 2/5 thread the live session id into `verify_runtime_ownership`. Establish in this phase WHERE the session id originates (the run marker's identity, `run_started_at`/`session_id`, already on the cycle marker — see `write_cycle_marker` L6904) so Phase 2 reuses it rather than minting a second id.
- Keep AlgoBooth specifics (port 3333, lock filename) in the config dict — Phase 2's reworked `ensure_runtime` reads them from `cfg`, never literals.

**Implementation Notes (2026-06-20 — part-1 `/execute-plan`, landed):**
- All four M1/M2 primitives landed in `lazy_core.py` (after `ensure_runtime`, before the `gate_coverage` block). Signatures established for Phase 2:
  - `spawn_detached(cmd, *, cwd, spawn=None, platform=None, which=None, kernel_start_time_fn=None) -> {"pid": int, "start_time": float|None}`. Windows: first spawn carries `creationflags = DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_BREAKAWAY_FROM_JOB` (module consts `_DETACHED_PROCESS`/`_CREATE_NEW_PROCESS_GROUP`/`_CREATE_BREAKAWAY_FROM_JOB`); `OSError` → retry without breakaway. POSIX: `start_new_session=True`, `systemd-run --user --scope --quiet --same-dir` wrap when `which("systemd-run")`, else `["setsid","nohup"]` prefix. `start_time` is filled by an injected `kernel_start_time_fn` (Phase 2 binds the real `kernel_start_time`); None when omitted. Two extra injected callables (`which`, `kernel_start_time_fn`) beyond the PHASES signature — additive, keyword-only, defaulted; ⚖ see below.
  - `kernel_start_time(pid, *, platform=None, read_stat=None, get_process_times=None, boot_time=None, clk_tck=None) -> float|None`. POSIX: parses `/proc/[pid]/stat` field 22 by splitting after the LAST `)` (comm-with-spaces safe), `boot_time + ticks/clk_tck`; default `boot_time` from `/proc/stat` `btime`, `clk_tck` from `os.sysconf("SC_CLK_TCK")`. Windows: `_win_process_creation_filetime` via `ctypes`→`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`+`GetProcessTimes`, FILETIME→epoch via `_FILETIME_EPOCH_OFFSET`/`_FILETIME_TICKS_PER_SEC`. Never raises (None on any error).
  - `write_runtime_lock(repo_root, *, pid, start_time, port, artifact_hash, controller_session_id, config=None)` + `read_runtime_lock(repo_root, *, config=None) -> dict|None`. Atomic via the shared `_atomic_write` (temp + `os.replace`). Path from `cfg["lock_filename"]` via `_runtime_lock_path` helper. Read returns None on missing/corrupt.
  - `verify_runtime_ownership(lock, *, live_session_id, kernel_start_time_fn) -> bool` — True iff `controller_session_id == live_session_id` AND recorded `start_time == kernel_start_time_fn(pid)` (None/dead pid → False). Calls the fn positionally first, falling back to `platform=` keyword for production binding.
- `_ENSURE_RUNTIME_DEFAULT_CONFIG` gained `lock_filename: ".runtime.lock.json"` + `port: 3333` (parameterized, not literals in the flow).
- ⚖ policy: tests in `test_lazy_core.py` vs new `--test` fixtures → landed in `test_lazy_core.py` (scope-class — same end-state coverage; `test_lazy_core.py` is the canonical home for shared `lazy_core` helpers per scripts/CLAUDE.md, and it keeps the byte-pinned `lazy-state.py`/`bug-state.py --test` baselines unshifted). 21 new tests; full gate suite green (`lazy-state.py`/`bug-state.py`/`lazy_coord.py --test` + `test_lazy_core.py` 644/644).
- ⚖ policy: added `which`/`kernel_start_time_fn` injected params → in-cycle (scope-class — same product behavior, strictly more hermetic; the PHASES `spawn_detached(... spawn=None, platform=None)` signature is the minimum, these are additive keyword-only defaults Phase 2 needs to bind the real extractor + PATH lookup).
- OS-branch gotcha for Phase 2: the POSIX `/proc/stat` parse is `rfind(")")`-anchored — do NOT switch to a naive `split()[21]` (comm names with spaces break it). The Windows FILETIME path requires `PROCESS_QUERY_LIMITED_INFORMATION` access (works for same-user processes).

---

### Phase 2: Rework `--ensure-runtime` into the liveness/recovery state machine (Persistent Service contract)

**Scope:** Extend (NOT replace — LD2) `ensure_runtime` into the idempotent M4 gatekeeper that returns the verdict `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker}` with `state ∈ {READY, STALE, HIJACKED, DEAD, BLOCKED}`. Implements the three-phase evaluation (Identity → Staleness → Health) using the Phase-1 primitives, plus the bounded-recovery contract: STALE/DEAD auto-recover via `restart()` in a bounded exponential-backoff loop capped at **5 attempts** (rewriting `.runtime.lock.json` on success → READY); HIJACKED is a strict fail-safe that NEVER SIGKILLs an unowned process and surfaces a `terminal_blocker`; BLOCKED halts with no retries. This is the M3.1 Persistent Service contract — deliberately leaves the process detached/behind for re-attach next cycle. The old `{status, mcp_tools_present, health_code}` callers (lazy-batch Step 1d.0) are migrated in Phase 5; this phase keeps the function backward-readable (the new verdict is a superset; `health_code`/`mcp_tools_present` retained).

**Deliverables:**
- [x] `ensure_runtime` extended in place to run Identity (parse `.runtime.lock.json` → `verify_runtime_ownership` → divergent `start_time` ⇒ HIJACKED, missing PID ⇒ DEAD) → Staleness (injected `stale_check(artifact_hash)`) → Health (injected `probe()` → `/health`; refused despite a live owned PID ⇒ DEAD), returning the M4 verdict dict.
- [x] Bounded recovery: STALE/DEAD → `restart()` in an exponential-backoff loop **capped at 5 attempts**; on a re-probe success rewrite the lock (new pid/start_time) and return READY; on exhaustion return BLOCKED with `terminal_blocker`.
- [x] HIJACKED fail-safe: when the recorded PID is dead but `/health` answers (a foreign port-holder) OR the live `start_time`/session diverges, set `state: HIJACKED` + `terminal_blocker` and return WITHOUT killing the foreign process. Inline comment citing the security/stability rule (LD3).
- [x] BLOCKED handling: `state: BLOCKED` + `terminal_blocker` set, no retries — the orchestrator (Phase 5) maps this to `BLOCKED.md` `blocker_kind: mcp-runtime-unready`.
- [x] Verdict surfaced through `lazy-state.py --ensure-runtime` JSON (the existing subcommand handler prints the new dict).
- [x] `user/scripts/CLAUDE.md` `--ensure-runtime` CLI doc updated to the new verdict schema + `state` enum.
- [x] Tests: hermetic `--test` matrix over all five states via injected `probe`/`restart`/`stale_check`/`kernel_start_time_fn` — READY (owned + healthy + current), STALE→READY (stale then recovers), DEAD→READY (down then recovers), DEAD→BLOCKED (recovery exhausts at attempt 5), HIJACKED (foreign port-holder, recorded PID dead → terminal_blocker, restart NEVER called); bounded-retry assertion (`restart` invoked ≤5, backoff applied).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <fixture>` (with injected callables under `--test`) returns a verdict whose `state` matches the injected scenario; the `--test` suite asserts all five state transitions + the ≤5-attempt bound and the HIJACKED no-kill invariant.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Cross-cycle ownership spike (runtime spike — workstation-eligible): boot the runtime via the reworked `ensure_runtime` in one process, then in a SEPARATE process call `--ensure-runtime` again and observe `state: READY` with `ownership_verified: true` (the `.runtime.lock.json` written by the first process verifies under the second's live session) — confirming the Persistent Service re-attach contract across the (simulated) cycle boundary. Runtime artifact (observed verdict from a second live invocation), not a code trace.

**MCP Integration Test Assertions:** N/A — no AlgoBooth MCP surface. The verdict is asserted by the hermetic `--test` matrix; the cross-cycle re-attach (the one runtime-coupled claim) is the Runtime Verification spike above.

**Prerequisites:**
- Phase 1: `read_runtime_lock`, `verify_runtime_ownership`, `kernel_start_time`, `write_runtime_lock` (the Identity-phase inputs and the lock-rewrite-on-recovery).

**Files likely modified:**
- `user/scripts/lazy_core.py` — extend `ensure_runtime` (L6166) in place to the M4 verdict + bounded recovery + HIJACKED/BLOCKED fail-safe; reuse `_default_runtime_probe` (L6118) + `stale_binary.native_source_newer_than` as the default injected callables (verified existing).
- `user/scripts/lazy-state.py` — `--ensure-runtime` handler (L6896 arg) prints the new verdict; add `--test` state-machine fixtures.
- `user/scripts/CLAUDE.md` — update the `--ensure-runtime` CLI doc block (verified: documents the current `{status,...}` shape).

**Testing Strategy:** Hermetic `--test` only — every external interaction (`probe`, `restart`, `stale_check`, kernel start_time) is an injected callable, so the five-state matrix and the bounded-retry/no-kill invariants are deterministic without a live runtime. Backoff timing is asserted via an injected clock/sleep callable (no real sleeps in tests), same pattern as the existing `restart` poll loop.

**Integration Notes for Next Phase:**
- The verdict's `terminal_blocker` field is the BLOCKED.md routing signal Phase 5 consumes; its message text is authored here (Phase 5 only surfaces it).
- The HIJACKED never-SIGKILL invariant is a LOCKED safety contract — Phase 5 must NOT add an orchestrator-side kill path "to recover faster."
- Phase 3's Transient Build contract (M3.2) reuses `spawn_detached` but does NOT call this Persistent Service `ensure_runtime` — keep the two contracts as separate `lazy_core` entry points over the one spawn primitive (LD5).

**Implementation Notes (2026-06-20 — part-2 `/execute-plan`, landed — Phase 2 implementation complete, validation pending):**
- `ensure_runtime` reworked IN PLACE (LD2) into the M4 verdict superset (`lazy_core.py`). New keyword-only injected params (all defaulted → backward-compatible): `read_lock`, `live_session_id`, `kernel_start_time_fn`, `sleep`, `write_lock`, `recover_identity`, `kill`. The verdict dict is:
  ```
  {"state": "READY"|"STALE"|"HIJACKED"|"DEAD"|"BLOCKED",
   "ownership_verified": bool,
   "health_code": int,
   "mcp_tools_present": bool,
   "terminal_blocker": str|None,
   "status": "ready"|"booted"|"stale-rebuilt"}   # legacy, RETAINED (superset)
  ```
- **Two call modes** (the backward-compat seam Phase 5 migrates over): *M4 mode* engages when the caller threads `live_session_id` (and/or `read_lock`/`kernel_start_time_fn`) — runs Identity→Staleness→Health + bounded recovery. *Legacy mode* (no Identity callables) keeps the pre-M4 boot/stale/ready flow and is UPGRADED to the verdict superset (`state` derived via `_LEGACY_STATUS_TO_STATE`, `ownership_verified: False`, `terminal_blocker: None`). A caller never sees a missing key.
- **Classification helpers** (`lazy_core.py`): `_ensure_runtime_m4` (Identity→Staleness→Health) → `_recover_runtime` (the bounded backoff loop). Constants `_RUNTIME_RECOVERY_MAX_ATTEMPTS = 5`, `_RUNTIME_RECOVERY_BACKOFF_BASE = 1.0` (schedule 1,2,4,8,16s via the injected/real `sleep`), `_RUNTIME_STATES`, `_LEGACY_STATUS_TO_STATE`.
- **`terminal_blocker` message text for Phase 5** (authored here, Phase 5 surfaces verbatim into `BLOCKED.md` `blocker_kind: mcp-runtime-unready`):
  - HIJACKED (`_hijacked_blocker(lock)`): *"Runtime ownership could not be verified — a foreign process is holding port {port} (recorded PID/start_time/session diverges from the live kernel). Refusing to SIGKILL an unowned process (LD3 safety/stability rule); surface as BLOCKED (blocker_kind: mcp-runtime-unready) for operator intervention."*
  - BLOCKED-exhausted (`_blocked_blocker(attempts)`): *"Runtime recovery exhausted — restart() retried {N} times (bounded cap 5) with exponential backoff without restoring a healthy, owned runtime. Halting with no further retries (blocker_kind: mcp-runtime-unready)."*
- **HIJACKED never-SIGKILL** is enforced by construction: the HIJACKED branch returns immediately with the `terminal_blocker` set and NEVER calls `restart()` or any kill path. The `kill` injected param exists ONLY so a test can assert it is not invoked; production passes None and there is no kill code path. (Validation row "Hijacked port surfaces a blocker, never SIGKILL".)
- **`--ensure-runtime` handler** (`lazy-state.py`) threads the live run marker's `session_id` as `live_session_id` (the Phase-1 Integration Note — the run marker is the stable run identity / `controller_session_id`, NOT a second minted id). No live marker ⇒ `live_session_id=None` ⇒ legacy mode. Best-effort: a marker-read error degrades to legacy mode, never blocks the subcommand.
- **Lock-rewrite on recovery:** `_recover_runtime` calls the injected `write_lock` with the `recover_identity()`-supplied `{pid, start_time, ...}` on a healthy re-probe, so the NEXT cycle verifies against the restarted process (Persistent Service re-attach contract). Phase 5's production wiring must supply a `recover_identity` (e.g. from the `spawn_detached` result) for the lock to actually rewrite — absent one, recovery still returns READY but leaves the lock stale (best-effort; documented).
- **Tests** (`test_lazy_core.py`, +16 → 660/660): WU-1 Identity classification (8, incl. legacy-superset + DEAD/HIJACKED routing), WU-2 bounded recovery/backoff/no-kill (5), WU-3 CLI handler wiring + a real `lazy-state.py --ensure-runtime` subprocess smoke pinned to a HIJACKED scenario so it returns IMMEDIATELY (no real `dev:restart` / 7.5-min health poll). Full hermetic gate suite (`lazy-state.py`/`bug-state.py`/`lazy_coord.py --test` + `test_lazy_core.py`) green; the byte-pinned smoke baselines are UNSHIFTED (no `lazy-state.py --test` fixtures added — the M4 matrix lives in `test_lazy_core.py`, the canonical home for shared `lazy_core` helpers).
- ⚖ policy: M4 matrix in `test_lazy_core.py` vs new `lazy-state.py --test` fixtures → `test_lazy_core.py` (scope-class — same end-state coverage; keeps the byte-pinned `--test` baselines unshifted, mirroring the part-1 decision).
- ⚖ policy: handler JSON-shape test → in-process handler-wiring assertion + a HIJACKED-scenario subprocess smoke (scope-class — same end-state JSON contract; avoids firing a real `npm run dev:restart` / urllib health-poll hang that a READY/DEAD subprocess fixture would trigger).

---

### Phase 3: Enforce the long-build ownership boundary (PreToolUse guard + Transient Build contract)

**Scope:** The M5-Prevent half plus the M3.2 Transient Build contract. (a) A NEW standalone `PreToolUse` Bash hook `long-build-ownership-guard.sh` that tokenizes the candidate Bash command and, when it matches an EXACT long-build signature (`^tauri build`, `^cargo build --release`, `^npm run build`), **fail-open blocks (`exit 2`)** with a deny message bubbling a specific signature that signals the orchestrator to take over the spawn — scoped to exact long-build binary invocations so it never redirects `ls`/`cat`. This is modeled on the existing standalone-guard shape (`block-noncanonical-blocker-write.sh`), NOT folded into `lazy-cycle-containment.sh` (which keys off `agent_id`/marker for recursion/lifecycle; this guard is a request-time long-build signature matcher with a distinct purpose). (b) The Transient Build contract in `lazy_core`: a synchronous wait-and-promote entry point that spawns the build detached (via Phase-1 `spawn_detached`, so it survives a subagent tear) but the orchestrator explicitly AWAITS its conclusion (gathering stdout for telemetry) — it does NOT abandon the process for a future cycle. Atomic Artifact Promotion itself is Phase 4; this phase delivers the contract's spawn+await+telemetry shape and the guard.

**Deliverables:**
- [x] `user/hooks/long-build-ownership-guard.sh` (net-new) — fail-OPEN PreToolUse Bash hook; inline Python matcher anchored to exact long-build signatures (`^\s*tauri build`, `^\s*cargo build --release`, `^\s*npm run build`, tolerant of leading env-var assignments / `&&` chaining per the tokenizer); on a match, emits a `deny` with a corrective message naming the orchestrator-takeover signature; ANY internal error → allow (breadcrumb), mirroring the other guards. NOT armed by a marker — a request-time matcher.
- [x] Register the hook in `user/settings.json` as an additional entry in the existing `"matcher": "Bash"` PreToolUse array (alongside the three current Bash hooks, L58-77).
- [x] `run_transient_build(cmd, *, cwd, spawn=None, wait=None) -> {exit_code, stdout, ...}` in `lazy_core.py` — the M3.2 contract: spawn detached via `spawn_detached`, await conclusion, capture stdout for telemetry; does NOT write `.runtime.lock.json` and does NOT leave the process for a later cycle (distinct from the Persistent Service contract). Injectable `spawn`/`wait` for hermetic tests.
- [ ] Update `repos/algobooth/.claude/skill-config/long-build-ownership.md`: the advisory prose rule becomes the documented enforced guard + the Transient Build contract reference (the rule is now load-bearing, not advisory).
- [x] Tests: hook-pipe tests for `long-build-ownership-guard.sh` (each long-build signature → deny `exit`-2-style block with the takeover signature; `ls`/`cat`/`git status`/a short `npm run lint` → allow; malformed payload → fail-open allow); hermetic `lazy_core` `--test` for `run_transient_build` (injected spawn/wait → returns exit_code+stdout; survives a simulated parent teardown via the detached spawn).

**Minimum Verifiable Behavior:** Piping a synthetic PreToolUse payload whose Bash command is `tauri build` through `bash user/hooks/long-build-ownership-guard.sh` emits a `permissionDecision: deny` JSON naming the orchestrator-takeover signature; piping `ls -la` (and a non-long `npm run lint`) emits nothing (allow). The `lazy_core --test` suite asserts `run_transient_build` spawns-detached-and-awaits.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Guard-redirect spike (runtime spike — workstation-eligible): with the hook registered in `settings.json`, a real (or simulated) cycle-context attempt to background `cargo build --release` is BLOCKED by the guard (`exit 2`, deny message present) and the build does NOT start under the subagent — observed live via the hook firing, not a static read of the matcher regex.
- [ ] <!-- verification-only --> Transient-build survival: a build launched through `run_transient_build` from a short-lived parent process runs to completion (its `exit_code`/`stdout` are captured) even though the parent returned before it finished — the detached-spawn survival property applied to the build shape.

**MCP Integration Test Assertions:** N/A — the guard and Transient Build contract have no AlgoBooth MCP surface; verification is the hook-pipe tests + the Runtime Verification spikes above (the guard's redirect behavior and the build's survival are the runtime-coupled claims, covered by spikes, not MCP).

**Prerequisites:**
- Phase 1: `spawn_detached` (the Transient Build contract spawns through it).
- Phase 2: the Persistent Service contract exists, so the two contracts (LD5: one spawn primitive, two contracts) are visibly distinct in `lazy_core`.

**Files likely modified:**
- `user/hooks/long-build-ownership-guard.sh` — NET-NEW guard (modeled on `block-noncanonical-blocker-write.sh` fail-open inline-Python shape).
- `user/settings.json` — register the guard in the `"matcher": "Bash"` PreToolUse array (verified L58-77).
- `user/scripts/lazy_core.py` — add `run_transient_build` (Transient Build contract over `spawn_detached`).
- `repos/algobooth/.claude/skill-config/long-build-ownership.md` — advisory→enforced prose update (verified existing, 23 lines).
- `user/scripts/test_lazy_core.py` — `run_transient_build` characterization.
- `CLAUDE.md` (repo root, Hooks table) — add the new guard row (the Hooks table documents every registered hook).

**Testing Strategy:** The guard is verified by hook-pipe tests (synthetic PreToolUse JSON on stdin → assert the emitted deny/allow), the established pattern for the other Bash guards — no live build needed for the matcher layer. The Transient Build contract is hermetic via injected `spawn`/`wait`. Its one runtime-coupled property (the build surviving a parent tear) is a Runtime Verification spike. False-positive scope (never redirecting short subprocesses) is asserted by explicit allow cases in the pipe tests.

**Integration Notes for Next Phase:**
- The guard's deny/takeover signature string is the contract Phase 5's orchestrator listens for to take over the spawn — author it here, consume it in Phase 5.
- `run_transient_build` returns stdout/exit_code; Phase 4 wraps the build target in the staging-dir + `os.replace` Atomic Artifact Promotion so a torn build never corrupts the production artifact. Keep promotion OUT of `run_transient_build` itself — Phase 4 composes it around the build target.
- The Hooks-table row in the repo-root CLAUDE.md must state the guard is fail-OPEN and request-time (not marker-armed), to keep the documented hook taxonomy accurate.

**Implementation Notes (2026-06-20 — part-3 `/execute-plan`, Batch 1 landed):**
- **Batch 1 (WU-1 ∥ WU-2) complete.** Implemented INLINE under the lazy-pipeline override (zero `Agent()` calls); RED tests written and confirmed failing for the right reason BEFORE each implementation, then driven GREEN.
- **WU-1 — `user/hooks/long-build-ownership-guard.sh` (net-new) + `settings.json` registration.** Fail-OPEN PreToolUse(Bash) guard modeled on `block-noncanonical-blocker-write.sh` (inline Python via `-c`, deny expressed as `permissionDecision: deny` JSON, ANY internal error → exit 0 allow + a `hook-error.json` breadcrumb). Matcher: `^\s*` + optional `NAME=value` env-assignment prefix run, then EXACTLY one of `tauri build` / `cargo build --release` / `npm run build` (each anchored so a buried substring like `echo tauri build` does NOT match, and `npm run build:docs` / plain `cargo build` / `cargo check --release` ALLOW). Registered as a 4th entry in the existing `PreToolUse "matcher": "Bash"` array in `user/settings.json` (settings.json re-validated as JSON).
- **TAKEOVER SIGNATURE (part-5 contract):** the deny reason carries the literal **`LONG-BUILD-OWNERSHIP-TAKEOVER`** (SSOT in both the hook and `test_hooks.py`). Phase 5's orchestrator listens for this token to take over the spawn under the Transient Build contract.
- **WU-2 — `run_transient_build(cmd, *, cwd, spawn=None, wait=None, platform=None, which=None, kernel_start_time_fn=None)` in `lazy_core.py`.** The M3.2 contract: spawns through `spawn_detached` (survives a subagent tear by construction), synchronously AWAITS conclusion via an injectable `wait(spawned) -> (exit_code, stdout)`, returns `{exit_code, stdout, pid, start_time}`. Does NOT call `write_runtime_lock` and does NOT leave a process for a future cycle (LD5 two-contracts distinction — asserted by a spy test + a no-lock-file-at-repo-root test). Atomic Artifact Promotion kept OUT (Phase 4 composes it around). Default production awaiter `_default_build_wait` re-attaches by PID; tests always inject `wait` (hermetic).
- **Review verdict:** PASS (inline review under the lazy override — substantive spec-alignment + edge-case + false-positive-scope review done; subagent-falsification re-run skipped per R6 since tests + code were authored in-session).
- **Gates (Batch 1):** `test_hooks.py` 85/85, `test_lazy_core.py` 667/667, `lazy-state.py --test` / `bug-state.py --test` / `lazy_coord.py --test` all green; `settings.json` valid JSON.

---

### Phase 4: Torn-build atomic-promotion + `--cycle-begin` git-consistency recovery (M5 Detect)

**Scope:** The M5-Detect half — the detect-and-recover safety net that makes a torn build mathematically harmless even if the controller itself is torn mid-build. (a) Atomic Artifact Promotion: the build writes into a staging dir (`target/release_staging`), and the artifact is `os.replace()`'d into `target/release` ONLY on `exit(0)` (atomic NTFS `MoveFileEx` / POSIX `rename`), so a mid-flight tear never leaves a half-written production artifact. (b) A `--cycle-begin` git-consistency check: a pre-boot `.git/index.lock` whose creation time predates the orchestrator boot ⇒ a previous op was torn ⇒ remove the stale lock and `git clean` the staging dir, neutralizing the uncommitted delta before the next cycle. This composes with — does NOT duplicate — the EXISTING `--cycle-end` friction detector (`detect_cycle_bracket_friction` / `cycle_end_friction_check`, `unexpected-commits` / `cycle-bracket-break` reasons).

**Deliverables:**
- [ ] `promote_artifact_atomically(staging_dir, final_dir, *, exit_code, replace=None) -> {promoted: bool, reason}` in `lazy_core.py` — `os.replace()` the staging artifact into the final path ONLY when `exit_code == 0`; a non-zero exit leaves the production artifact untouched (no partial promotion). Injectable `replace` for hermetic tests. Composes around the Phase-3 `run_transient_build` target.
- [ ] `--cycle-begin` git-consistency reconciliation in `lazy_core` / the `--cycle-begin` handler: detect a pre-boot `.git/index.lock` (creation time older than the orchestrator/run-marker boot stamp) → remove it and `git clean -fdx` the staging dir; record the reconciliation. Best-effort + fail-open (a degraded git tree / no lock → no-op, never blocks the cycle bracket).
- [ ] Integration with the `--cycle-end` friction detector: the reconciliation is recorded so a torn-build delta neutralized at `--cycle-begin` does not subsequently false-trip `unexpected-commits`/`cycle-bracket-break` at `--cycle-end` (verified-coherent with `detect_cycle_bracket_friction` L7194).
- [ ] Tests: hermetic `--test` for `promote_artifact_atomically` (exit 0 → staging replaces final; exit≠0 → final untouched, no partial write; injected `replace` asserts atomicity ordering); `--cycle-begin` reconciliation fixtures (stale pre-boot `index.lock` → removed + staging cleaned; fresh/own lock → preserved; no lock / non-git tree → no-op); a friction-detector composition fixture proving a reconciled torn-build delta does not false-trip the `--cycle-end` signals.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` exercises `promote_artifact_atomically` (exit-0 promotes, exit-≠0 leaves production untouched) and the `--cycle-begin` stale-`index.lock` reconciliation fixtures; the full smoke suite + `test_lazy_core.py` stay green.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Torn-build no-orphan spike (runtime spike — workstation-eligible): tear a controller while its build is in flight (or simulate via a non-zero `exit_code` mid-promotion) and observe the production artifact is NEVER half-written (staging holds the partial; `target/release` is unchanged), AND a subsequent `--cycle-begin` removes the pre-boot `.git/index.lock` and `git clean`s the staging dir so `git status` is clean before the next cycle. Runtime artifact: observed `git status` clean + intact production artifact, not a code trace.

**MCP Integration Test Assertions:** N/A — no AlgoBooth MCP surface. The atomic-promotion + git-consistency invariants are asserted by the hermetic `--test` fixtures; the one cross-process/torn-mid-build claim is the Runtime Verification spike above.

**Prerequisites:**
- Phase 3: `run_transient_build` (the build target promotion wraps).
- unified-pipeline-orchestrator (composes): the existing `--cycle-begin`/`--cycle-end` bracket + `detect_cycle_bracket_friction`/`cycle_end_friction_check` (the seam this composes with, NOT replaces).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `promote_artifact_atomically`; the `--cycle-begin` git-consistency reconciliation helper (composed with `detect_cycle_bracket_friction` L7194 / `cycle_end_friction_check` L7349 — verified existing).
- `user/scripts/lazy-state.py` — wire the reconciliation into the `--cycle-begin` handler (verified handler exists, args ~L6921); add `--test` fixtures. `bug-state.py` mirrors via shared `lazy_core` (audited by `lazy_parity_audit.py`).
- `user/scripts/test_lazy_core.py` — `promote_artifact_atomically` + reconciliation characterization.

**Testing Strategy:** Hermetic. Atomic promotion is asserted via an injected `replace` callable (ordering + exit-gating) — no real 20-40 min build. The git-consistency reconciliation is fixture-driven (temp git tree with a planted stale `index.lock`). The single torn-mid-build cross-process claim is the Runtime Verification spike. The friction-detector composition is asserted directly against `detect_cycle_bracket_friction` so the new reconciliation provably does not introduce a false-positive.

**Integration Notes for Next Phase:**
- Phase 5's orchestrator path uses `run_transient_build` + `promote_artifact_atomically` together when it takes over a guard-redirected build — author the compose order (spawn-await → promote-on-exit-0) so Phase 5 calls them as a pair.
- The `--cycle-begin` reconciliation is now part of the cycle bracket — Phase 5's loop wiring must call `--cycle-begin` (which now also reconciles) before each dispatch, unchanged in shape from today's bracket.

---

### Phase 5: Wire the orchestrator (consume the verdict + the coupled-wrapper mirror)

**Scope:** Replace the hand-rolled `/lazy-batch` Step 1d.0 poll loop with the single liveness primitive call, now consuming the Phase-2 M4 verdict (`{state, ownership_verified, ...}`) instead of the old `{status, ...}` shape: READY/STALE→READY proceed; HIJACKED/BLOCKED → surface `BLOCKED.md` `blocker_kind: mcp-runtime-unready` (never dispatch a subagent against a dead/hijacked runtime). Wire the guard-redirect takeover (when `long-build-ownership-guard.sh` blocks a subagent build, the orchestrator takes over the spawn via the Phase-3 Transient Build contract + Phase-4 atomic promotion). Then MIRROR every wrapper-prose change into the coupled variants per the CLAUDE.md coupled-pair rules: `/lazy` ↔ `/lazy-cloud`, `/lazy-batch` ↔ `/lazy-batch-cloud`. No state-machine logic moves into wrappers — the verdict-consumption is prose that routes on the script's JSON.

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md` Step 1d.0 (L552-599) rewired: consume the M4 verdict from `--ensure-runtime`; map `state ∈ {HIJACKED, BLOCKED}` (and unrecoverable `mcp_tools_present: false`) to a `BLOCKED.md` `blocker_kind: mcp-runtime-unready` halt; READY/STALE→READY/booted proceed. The hand-rolled rebuild→health-poll→inspect loop is the single subcommand call (no hand-composed until-loop in the cycle prompt).
- [ ] Guard-takeover wiring in `/lazy-batch`: when `long-build-ownership-guard.sh` denies a subagent long build (the takeover signature surfaces), the orchestrator session runs the build under the Transient Build contract (`run_transient_build` + `promote_artifact_atomically`) instead of the subagent — documented in the orchestrator's long-build handling prose.
- [ ] Mirror into `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` per the coupled-pair rule — cloud Step 9 returns `__write_deferred_non_cloud__` and never reaches Step 1d.0, so the cloud mirror records the divergence (the verdict-consumption block is workstation-only) in its "Differences from /lazy-batch" table rather than duplicating the runtime boot.
- [ ] Mirror the relevant wrapper prose into `user/skills/lazy/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` (the `/lazy` ↔ `/lazy-cloud` coupled pair) — only the shared dispatch glue that references the runtime verdict, keeping the cloud-divergence (`--cloud`) intact.
- [ ] Update each coupled file's State Machine Summary / "Differences" block so the dispatch table reflects the verdict-based routing + the BLOCKED.md `mcp-runtime-unready` terminal.
- [ ] `lazy_parity_audit.py` run clean after the wrapper edits (the coupled-pair + bug-state mirror audit).
- [ ] Tests: `lazy-state.py --test`, `bug-state.py --test`, `lazy_coord.py --test`, `test_lazy_core.py` all green (full set per the scripts/CLAUDE.md change-here-run-all rule); `python ~/.claude/scripts/project-skills.py` re-run so the per-repo projection picks up the wrapper + skill-config edits.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <repo>` returns the M4 verdict, and the rewired Step 1d.0 prose routes on `state` (verifiable by reading the routing block against the verdict schema); `python3 user/scripts/lazy_parity_audit.py` reports the coupled wrappers in lockstep; the full `--test` set is green.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> End-to-end orchestrator spike (runtime spike — workstation-eligible): a `/lazy-batch` mcp-test cycle calls `--ensure-runtime` ONCE, receives a `state: READY`/`booted` verdict, and the `/mcp-test` subagent connects to a live, current, orchestrator-OWNED runtime (no reaped-runtime, no hand-rolled poll loop in the cycle prompt). Observed via the live run's Step 1d.0 single-call behavior + the subagent meeting a live runtime — a runtime artifact, not a prose read.

**MCP Integration Test Assertions:**
```
ASSERTIONS:
1. After an mcp-test cycle runs --ensure-runtime in /lazy-batch: the cycle prompt contains exactly ONE --ensure-runtime subcommand call and ZERO hand-composed rebuild→health-poll until-loops (SPEC Validation row "Orchestrator stops hand-rolling poll loops").
2. After --ensure-runtime returns state ∈ {HIJACKED, BLOCKED}: a BLOCKED.md with blocker_kind: mcp-runtime-unready is written and NO subagent is dispatched against the dead runtime (SPEC Validation row "Hijacked port surfaces a blocker, never SIGKILL").
```
(These are observable in the live `/lazy-batch` run transcript + the BLOCKED.md sentinel — NOT an AlgoBooth MCP-server surface. There is no `load_test_tone`/`get_audio_buffer`-style assertion because the feature has no app surface; the "runtime" asserted is the managed-process behavior, surfaced in the run transcript and sentinels.)

**Prerequisites:**
- Phase 2: the M4 verdict (`--ensure-runtime` returns `{state, ...}`).
- Phase 3: the guard + Transient Build contract (the takeover path).
- Phase 4: atomic promotion (composed into the takeover build).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — Step 1d.0 rewire + guard-takeover prose (verified L552-599).
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled mirror / divergence record (verified coupled pair per CLAUDE.md).
- `user/skills/lazy/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` — coupled-pair wrapper mirror.
- `user/scripts/CLAUDE.md` — note the verdict-based Step 1d.0 routing in the lifecycle/CLI doc.

**Testing Strategy:** The wrapper edits are prose; correctness is verified by (a) `lazy_parity_audit.py` confirming the coupled pairs stay in lockstep, (b) the full hermetic `--test` set staying green (no state-machine logic changed — only verdict-consumption prose + the already-tested Phase-2 verdict), (c) `project-skills.py` re-projection confirming the components/skill-config expand cleanly. The one end-to-end runtime claim (a live cycle meeting an owned runtime) is the Runtime Verification spike.

**Completion (gate-owned):** the `__mark_complete__` gate flips SPEC.md **Status:** to Complete, strikes the ROADMAP row, trims the queue, and writes COMPLETED.md once this phase's runtime verification passes and the MCP-coverage audit (Gate 1) over the SPEC's `## Locked Decisions` is satisfied. This PHASES.md never flips the top-level status itself.

**Integration Notes for Next Phase:** None — final phase. The coupled-pair mirror is the last structural step; after it, the feature routes to the validation tail (the `not-required` MCP gate → coverage audit → `__mark_complete__`) owned by the orchestrator.
