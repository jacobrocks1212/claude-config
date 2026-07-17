"""lazy_core.runtimeplane — the runtime-ownership / spawn / transient-build plane.

Extracted VERBATIM from lazy_core/_monolith.py (lazy-core-package-decomposition
Phase 4, WU-4) — a move-only refactor with zero behavior change. Owns
``ensure_runtime`` + the M4 identity/staleness/health evaluation and bounded
recovery (cold-compile + pre-Vite boot-liveness patient-waits), the runtime
probes (``_default_runtime_probe`` / sidecar / frontend / stale-check), the
detached-spawn primitive (``spawn_detached``) and the M3.2 Transient Build
contract (``run_transient_build`` / ``promote_artifact_atomically``), the
cycle-begin git-consistency reconciliation, kernel start-time extraction,
the runtime lock + boot stamp, ``verify_runtime_ownership``, and the
host-capability ACTIVE probe primitives (``probe_binary_capability`` /
``probe_env_capability`` / ``probe_platform_capability`` — the invoke-not-
``which()`` primitives ``hostcaps._default_host_probes`` binds via its
deferred import, re-pointed here this WU).

Write-path move sanctioned by the two archived bug receipts (SPEC D2
Constraint 3): docs/bugs/_archive/mark-complete-partial-apply-noop-unrecoverable/
FIXED.md and docs/bugs/_archive/production-sentinel-writes-bypass-atomic-write/
FIXED.md.

``_git`` / ``_current_head`` / ``git_head_short_sha`` / ``git_guard_status``
and the self-edit detection plane are module-resident since the Phase-5 WU-3
residue sweep (this module owns the git-helper plane).

Production-binding test convention (mechanically guarded by the
``tests/test_lazy_core/test_runtimeplane.py`` meta-guards): tests reach the OS
signal by swapping ``lazy_core.runtimeplane.subprocess`` /
``lazy_core.runtimeplane.time`` — the modules this plane's default closures
resolve against post-move.
"""

from __future__ import annotations

import datetime
import json
import os
import platform
import shlex
import subprocess
import sys
import time

from pathlib import Path
from typing import Any

import stale_binary

from ._ctx import _atomic_write
from .docmodel import _FALSY_ENV_VALUES


# ===========================================================================
# unified-pipeline-orchestrator Phase 5 — first three subcommands
#
# Three retro-named deterministic dances promoted from skill prose to code:
#   1. ensure_runtime() — the Step-1d.0 runtime-ensure dance.
#   2. gate_coverage()  — the Gate-1 MCP-coverage audit (mcp-coverage-audit.md).
#   3. apply_pseudo __mark_complete__ enhancement (ROADMAP strike + resolved
#      spec_dir queue trim) — lives in the existing apply_pseudo above.
# ===========================================================================

# Default AlgoBooth runtime config. These specifics (TCP 3333 health endpoint,
# the dev:restart command, the native-source globs, and the MCP tool name we
# assert) are AlgoBooth-coupled — but lazy-state.py is the repo-AGNOSTIC harness
# script, so they are PARAMETERIZED here as a default dict, NOT hard-coded into
# the control flow. A different repo overrides via the `config` argument (or the
# orchestrator passes a repo-specific config). The SPEC's Locked Decision puts
# --ensure-runtime ON lazy-state.py; this default dict is the clean
# parameterization that keeps the AlgoBooth specifics out of the algorithm.
_ENSURE_RUNTIME_DEFAULT_CONFIG: dict[str, Any] = {
    "health_url": "http://localhost:3333/health",
    "restart_command": "npm run dev:restart",
    "mcp_tool_name": "",          # empty → mcp_tools_present check is skipped
    "native_globs": ["src-tauri", "crates"],
    # Runtime-ownership sentinel (long-build-and-runtime-ownership Phase 1, LD1).
    # The `.runtime.lock.json` filename and the runtime's TCP port are
    # PARAMETERIZED here, NOT hard-coded into the read/write flow — a different
    # repo overrides via the `config` argument, keeping the shared harness
    # function repo-agnostic (same discipline as the keys above).
    "lock_filename": ".runtime.lock.json",
    "port": 3333,
    # Sidecar-pipe (is_connected) readiness dimension
    # (env-transient-counts-against-validation-retry-budget Phase 1, Leg A).
    # A runtime can be HTTP-healthy (/health 200) while the MCP sidecar named
    # pipe is dead (a zombie node process holding it after a dev:restart). The
    # HTTP-only gate then dispatches an mcp-test cycle against an
    # MCP-functionally-dead runtime, and the env transient gets mislabeled
    # `mcp-validation`. When `assert_sidecar_connected` is truthy, the M4 Health
    # phase additionally asserts `get_sidecar_status.is_connected: true` and
    # routes a pipe-dead-but-HTTP-200 runtime through recovery → BLOCKED
    # (mcp-runtime-unready, escalation-immune) instead of a bare READY.
    # Default OFF → repo-agnostic (non-AlgoBooth repos are unaffected); AlgoBooth
    # opts in via its config override.
    "assert_sidecar_connected": False,
    "sidecar_status_url": "http://localhost:3333/tools/get_sidecar_status",
    # Two-port cold-compile discriminator
    # (ensure-runtime-recovery-starves-cold-compile, Phase 1). A cold `tauri dev`
    # boot brings the Vite dev server up on :1420 within seconds, while the Rust
    # backend's :3333 /health endpoint refuses connections until the (potentially
    # multi-minute) cold Rust compile finishes. Probing ONLY :3333 cannot tell a
    # still-compiling backend (be patient) from a genuinely-dead one (recover) —
    # so a :3333-down/:1420-up observation is "compiling", not "dead". These keys
    # parameterize the Vite-up signal exactly like the :3333 keys above; a repo
    # without a :1420 frontend simply omits them (or overrides) and the
    # discriminator degrades to today's :3333-only DEAD behavior (frontend_probe
    # binds to lambda: False — see ensure_runtime). Read via .get() everywhere so
    # a legacy config override lacking the keys never raises.
    "frontend_health_url": "http://localhost:1420",
    "frontend_port": 1420,
    # Pre-Vite boot-liveness signal
    # (ensure-runtime-starves-pre-vite-sidecar-build, Phase 1). The two-port
    # discriminator above can only tell a still-booting cold runtime from a dead
    # one by Vite (:1420) being up — but a cold `tauri dev` spends its first
    # ~1-2 min in `BeforeDevCommand` (`npm run sidecar:build && vite`) with BOTH
    # ports down while the spawned boot process is alive. During that pre-Vite
    # window `frontend_up` is False, so the discriminator returned `dead` and
    # kill-restarted a healthy cold boot into a false BLOCKED. When this key is
    # truthy, ensure_runtime binds a real boot-liveness source (the liveness of
    # the `restart()`-spawned boot process, read from the in-process `Popen`
    # handle the harness already owns — NOT a URL probe, so no `_default_*` URL
    # helper is needed) and a both-ports-down-but-live-boot observation
    # classifies `compiling` (patient-wait), not `dead`. Default ABSENT → the
    # boot-liveness branch is INERT (boot_alive binds `lambda: False`), so every
    # repo without the key degrades to today's `dead` behavior — read via .get()
    # everywhere so a legacy override lacking the key never raises (mirror the
    # `assert_sidecar_connected` / `frontend_health_url` back-compat pattern).
    #
    # ensure-runtime-starves-pre-vite-sidecar-build Phase 3 (CLI-seam wiring):
    # ENABLED in the base default. The signal is fail-safe BY CONSTRUCTION — the
    # boot-liveness source is the liveness of the `restart()`-spawned `Popen`
    # handle THIS harness owns in-process (see `ensure_runtime`). When no boot was
    # spawned this call (or the spawn failed), `boot_alive()` reports NOT-booting,
    # so a non-AlgoBooth repo with both ports down still classifies `dead` and
    # reaches bounded recovery — byte-identical to the inert default. The signal
    # can only flip a both-ports-down observation to the patient-wait `compiling`
    # when this harness genuinely has a live boot process running, which is
    # exactly the cold pre-Vite `BeforeDevCommand`/`sidecar:build` window the M4
    # classifier was starving. The only production caller
    # (`lazy-state.py --ensure-runtime`) passes NO config override, so flipping the
    # base default here is what wires the signal end-to-end — a per-repo override
    # may still set it `False` to opt OUT.
    "boot_liveness": True,
}


def _sidecar_is_connected(payload: dict | None) -> bool:
    """True iff the get_sidecar_status payload reports ``is_connected: true``.

    Strict: only a literal boolean ``True`` counts as connected — a missing
    field, a non-dict payload, or a truthy-but-non-bool value (e.g. the string
    ``"true"``) is treated as NOT connected (fail-safe toward recovery). Pure
    payload-parsing helper, never raises.
    """
    if not isinstance(payload, dict):
        return False
    return payload.get("is_connected") is True


def _default_sidecar_probe(sidecar_status_url: str) -> bool:
    """Real get_sidecar_status probe (stdlib urllib) → ``is_connected`` bool.

    Mirrors ``_default_runtime_probe``: best-effort + never raises (any error →
    False so the caller treats the sidecar as disconnected and enters recovery).
    Only invoked when ``ensure_runtime`` is called WITHOUT an injected
    ``sidecar_check`` AND the config asserts the sidecar (production); tests
    always inject a ``sidecar_check``.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(sidecar_status_url, timeout=5) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            payload = None
        return _sidecar_is_connected(payload)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _default_frontend_probe(frontend_health_url: str) -> bool:
    """Real Vite (:1420) reachability probe (stdlib urllib) → bool.

    The cold-compile discriminator's "frontend up" signal
    (ensure-runtime-recovery-starves-cold-compile, Phase 1). A cold `tauri dev`
    brings Vite up on :1420 within seconds; reachability there while :3333
    /health still refuses means the Rust backend is still COMPILING (be patient),
    not dead. Mirrors ``_default_sidecar_probe``: best-effort + never raises (any
    error — connection refused, timeout, DNS — → False, so the caller treats the
    frontend as down and the runtime as dead). Only invoked when ``ensure_runtime``
    is called WITHOUT an injected ``frontend_probe`` AND the config carries the
    frontend keys (production); tests always inject a ``frontend_probe``. Any 2xx
    OR a connection that completes the HTTP round-trip counts as up — Vite answers
    on :1420 regardless of the path, so a non-200 status still proves reachability.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(frontend_health_url, timeout=5):  # noqa: S310
            return True
    except urllib.error.HTTPError:
        # An HTTP error response (4xx/5xx) still means Vite is LISTENING and
        # answered — the frontend is up (compiling backend, not a dead host).
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _classify_compile_state(
    backend_code: int, frontend_up: bool, boot_alive: bool = False
) -> str:
    """Map a two-port (+ boot-liveness) observation to
    ``"serving" | "compiling" | "dead"`` (pure).

    The cold-compile discriminator (ensure-runtime-recovery-starves-cold-compile,
    Phase 1) EXTENDED for the pre-Vite window
    (ensure-runtime-starves-pre-vite-sidecar-build, Phase 1). No I/O — the caller
    supplies the already-probed backend /health code, the frontend-up boolean,
    and (optionally) the boot-process-liveness boolean:

      - ``backend_code == 200`` ⇒ ``"serving"`` (the backend answers — regardless
        of the frontend OR boot-liveness signal; a serving backend is ready by
        definition).
      - ``backend_code != 200`` AND ``frontend_up`` ⇒ ``"compiling"`` (Vite is up
        but the backend is not yet serving — the cold Rust compile is still
        running; be PATIENT, do NOT kill-restart). UNCHANGED by ``boot_alive``.
      - ``backend_code != 200`` AND NOT ``frontend_up`` AND ``boot_alive`` ⇒
        ``"compiling"`` (the NEW pre-Vite branch — both ports down, but the
        orchestrator-spawned boot process is still ALIVE, i.e. the multi-minute
        ``BeforeDevCommand``/``sidecar:build`` window before Vite binds :1420.
        This is a cold boot in progress, NOT a crash — patient-wait it on the
        SAME path as the Vite-up compiling case rather than kill-restarting it.
        Reuses the ``"compiling"`` label so no new state ripples through the
        routers — ensure-runtime-starves-pre-vite-sidecar-build Phase 1).
      - ``backend_code != 200`` AND NOT ``frontend_up`` AND NOT ``boot_alive`` ⇒
        ``"dead"`` (nothing is listening AND no live boot — never booted or truly
        crashed and not restarting; the bounded crash-recovery loop is correct
        here). UNCHANGED — ``boot_alive`` DEFAULTS to ``False`` so every existing
        positional caller is byte-identical to the prior three-branch table.
    """
    if backend_code == 200:
        return "serving"
    if frontend_up:
        return "compiling"
    if boot_alive:
        return "compiling"
    return "dead"


def _default_runtime_probe(health_url: str):
    """Real /health probe (stdlib urllib). Returns (http_code, payload_dict).

    Best-effort + never raises: any error → (0, None) so the caller treats the
    runtime as down. Only invoked when ``ensure_runtime`` is called WITHOUT an
    injected ``probe`` (production); tests always inject.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(health_url, timeout=5) as resp:  # noqa: S310
            code = resp.getcode() or 0
            body = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                payload = None
        except (ValueError, TypeError):
            payload = None
        return (code, payload)
    except (urllib.error.URLError, OSError, ValueError):
        return (0, None)


def _default_stale_check(repo_root, cfg: dict) -> bool:
    """Production default binding for ``ensure_runtime``'s ``stale_check`` seam —
    wires the previously-orphaned F7 freshness predicate
    (``stale_binary.native_source_newer_than``) so the STALE verdict is REACHABLE
    in production (``docs/bugs/stale-runtime-health-200-false-blocked``).

    Boot signal (D1 — reuses what already exists, no new state):
      1. ``read_boot_stamp(repo_root)`` — the persisted ``dev:restart`` spawn
         epoch (``.runtime.boot.json``), written by ``ensure_runtime``'s own
         default ``restart()`` closure.
      2. Fallback: the ``.runtime.lock.json`` recorded kernel ``start_time`` (the
         owning process's boot time) via ``read_runtime_lock`` — covers a
         runtime that booted before a boot stamp existed (legacy-booted /
         foreign-adopted lock) so a genuinely stale binary is still caught.
      3. No signal at all → **not stale** (fail-safe; D2 below).

    The native-source glob list is ``cfg["native_globs"]`` (per-repo
    configurable via ``_ENSURE_RUNTIME_DEFAULT_CONFIG`` / a repo's ``config``
    override — AlgoBooth: ``src-tauri``, ``crates``, plus sidecar-bundle globs
    the repo config adds), never hard-coded here.

    Fail-safe direction (D2, unchanged from ``stale_binary.py``'s own contract):
    ANY missing/unreadable boot signal, unparseable epoch, or predicate error
    reports **False** (not stale) — the health=200 gate stays the primary guard.
    A spurious False costs nothing further; a spurious True would force a
    gratuitous multi-minute rebuild every cycle. Never raises.

    Only invoked when ``ensure_runtime`` is called WITHOUT an injected
    ``stale_check`` (production); ``--test`` always injects one directly (a
    legitimate allow-listed seam — see test_lazy_core.py's production-binding
    discipline note, ``_PRODUCTION_BINDING_ALLOWED_KWARGS``).
    """
    boot_epoch = None
    try:
        boot_epoch = read_boot_stamp(repo_root)
    except Exception:  # noqa: BLE001 — fail-safe: fall through to the lock
        boot_epoch = None
    if boot_epoch is None:
        lock = None
        try:
            lock = read_runtime_lock(repo_root, config=cfg)
        except Exception:  # noqa: BLE001 — fail-safe: no fallback signal
            lock = None
        if isinstance(lock, dict):
            boot_epoch = lock.get("start_time")
    if boot_epoch is None:
        return False
    try:
        boot_iso = datetime.datetime.fromtimestamp(
            float(boot_epoch), tz=datetime.timezone.utc
        ).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return False
    globs = cfg.get("native_globs") or _ENSURE_RUNTIME_DEFAULT_CONFIG["native_globs"]
    try:
        return bool(
            stale_binary.native_source_newer_than(
                boot_iso, Path(repo_root), globs=list(globs)
            )
        )
    except Exception:  # noqa: BLE001 — native_source_newer_than never raises by
        # its own contract, but a defensive guard keeps this binding fail-safe
        # even against a future change to that contract.
        return False


def _mcp_tool_in_payload(payload: dict | None, tool_name: str) -> bool:
    """True iff ``tool_name`` appears in the health payload's tool listing.

    Tolerant of the two shapes a /health payload may carry the tool set in:
      - ``{"tools": ["a", "b"]}`` (list of names), or
      - ``{"tools": [{"name": "a"}, ...]}`` (list of dicts).
    Empty ``tool_name`` → vacuously True (no assertion configured).
    """
    if not tool_name:
        return True
    if not isinstance(payload, dict):
        return False
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return False
    for t in tools:
        if isinstance(t, str) and t == tool_name:
            return True
        if isinstance(t, dict) and t.get("name") == tool_name:
            return True
    return False


def _mcp_tools_present_honest(payload: dict | None, tool_name: str,
                             health_code: int) -> bool:
    """``mcp_tools_present`` that is NOT vacuously True for a non-serving runtime
    (ensure-runtime-legacy-mode-optimistic-ready-verdict, Phase 1 / SPEC Open
    Question 3).

    ``_mcp_tool_in_payload`` returns vacuously True for an empty ``tool_name`` (no
    assertion configured). That is correct for a SERVING runtime (health 200), but
    misleading for one that is not serving — it claimed ``mcp_tools_present: true``
    alongside ``health_code: 0``. Here: an empty ``tool_name`` paired with a
    non-200 ``health_code`` reports ``False`` (the runtime is demonstrably not
    serving its tools); a 200 health code with no configured tool name keeps the
    vacuous-True default; a configured tool name defers to ``_mcp_tool_in_payload``
    in every case (unchanged).
    """
    if not tool_name and int(health_code or 0) != 200:
        return False
    return _mcp_tool_in_payload(payload, tool_name)


# long-build-and-runtime-ownership Phase 2 (LD3) — the M4 liveness/recovery
# verdict state enum. A `.runtime.lock.json`-owned runtime evaluates through
# Identity → Staleness → Health into exactly one of these (BLOCKED is the
# recovery-exhausted terminal added in WU-2).
_RUNTIME_STATES = ("READY", "STALE", "HIJACKED", "DEAD", "BLOCKED")

# Legacy `status` ↔ M4 `state` mapping (LD2 — the verdict is a SUPERSET of the
# old {status,...} dict so part-5 migration is incremental). The pre-M4 flow
# only ever yielded a *good* runtime (booted/ready/stale-rebuilt all end at
# health=200), so each maps to a non-terminal verdict state.
_LEGACY_STATUS_TO_STATE = {
    "ready": "READY",
    "booted": "READY",
    "stale-rebuilt": "STALE",
}


# long-build-and-runtime-ownership Phase 2 (LD3) — the bounded-recovery cap. A
# STALE/DEAD runtime auto-recovers via restart() in an exponential-backoff loop
# capped at this many attempts; on exhaustion the verdict is BLOCKED. The cap is
# the loop-prevention guarantee that replaces the hand-rolled poll loops.
_RUNTIME_RECOVERY_MAX_ATTEMPTS = 5
# Exponential-backoff base seconds (1, 2, 4, 8, 16 …) — multiplied by the
# injected/real sleep so --test asserts the schedule without real sleeps.
_RUNTIME_RECOVERY_BACKOFF_BASE = 1.0

# Cold-compile patient-wait ceiling (ensure-runtime-recovery-starves-cold-compile,
# Phase 2). A runtime classified `compiling` (Vite :1420 up, backend :3333 not yet
# serving) is WAITED on — never kill-restarted — on a cold-compile-sized budget.
# REUSES the existing production restart()-awaiter's `90 × 5s` ≈ 7.5-min sizing
# (NOT the ≤5×backoff ~31s crash budget, which would starve a cold Rust compile —
# the root cause). Injected sleep keeps --test hermetic (no real 7.5-min wait).
_COLD_COMPILE_WAIT_MAX_POLLS = 90
_COLD_COMPILE_WAIT_INTERVAL = 5.0

# Boot-spawn grace window (ensure-runtime-recovery-starves-cold-compile-round-2 —
# the Windows-wrapper-exits-early refix). The pre-Vite boot-liveness signal cannot
# rely SOLELY on the `restart()`-spawned `Popen.poll()` being None, because on
# Windows the production `restart_command` (`npm run dev:restart` =
# `node scripts/kill-dev.js && cross-env … tauri dev`) spawns a SHORT-LIVED
# npm/cmd shell-chain WRAPPER whose handle `.poll()` returns an exit code within
# seconds — long before the detached `tauri dev` / `cargo build` child finishes
# the ~3.5-min cold compile. Reading only that wrapper handle misclassifies a
# genuinely-compiling cold boot as `dead` (the Round-32 false-green: its test
# fed a fake `Popen` whose `.poll()` stayed None, so it never exercised the
# wrapper-exits-early production reality). The robust signal is a TIME-WINDOW
# grace: when a boot was spawned within this many seconds, a both-ports-down
# observation is the cold-compile window in progress — patient-wait it. The
# window is sized to the cold-compile ceiling (`_COLD_COMPILE_WAIT_MAX_POLLS ×
# _COLD_COMPILE_WAIT_INTERVAL` ≈ 7.5 min) so a boot that is genuinely stuck past
# the patient-wait budget still ages out of the grace and reaches bounded
# recovery → BLOCKED (fail-safe: a dead host is never patient-waited forever).
_BOOT_SPAWN_GRACE_SECONDS = _COLD_COMPILE_WAIT_MAX_POLLS * _COLD_COMPILE_WAIT_INTERVAL


# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features — Phase 2
#   Active-invocation probe primitives (hermetic, injected).
#
# Each per-capability host check is an injected callable, modeled on
# ensure_runtime's probe/restart/stale_check contract (real defaults bound only
# when the callable is None). Binary capabilities use ACTIVE INVOCATION — run the
# tool and check its exit code — NEVER shutil.which()/os.path.exists(). That is
# load-bearing on this Windows host: a zero-byte `python3.exe`/`python.exe` App
# Execution Alias stub in \WindowsApps on $PATH resolves under which() but its
# invocation opens a GUI Microsoft Store prompt and silently HANGS the pipeline
# (research Area 2). Stale path caches are the same hazard class. The exit-code
# gate (and the short timeout in the real default) is what guards against it.
# ---------------------------------------------------------------------------

# The real-default binary-probe invocation timeout (seconds). A probe that hangs
# is the exact failure mode active invocation exists to prevent, so bound it.
_BINARY_PROBE_TIMEOUT_SECONDS = 5


def probe_binary_capability(argv, *, run=None) -> bool:
    """Return True iff invoking ``argv`` exits 0 — the active-invocation binary
    capability probe (host-capability-declaration Phase 2).

    Runs ``argv`` (e.g. ``[tool, "--version"]``) via the injected ``run``
    callable and returns ``exit code == 0``. NEVER consults the filesystem for
    presence (no ``shutil.which`` / ``os.path.exists``) — that is the
    \\WindowsApps App-Execution-Alias false-positive guard.

    The default ``run`` is a real ``subprocess.run`` with a short timeout,
    ``capture_output=True`` and ``shell=False``; ``--test`` injects a stub so no
    real binary is ever invoked. Any invocation error (timeout, OSError, a stub
    that raises) is swallowed and reported as ``False`` — an un-runnable tool is
    an absent capability, never a propagated exception that bricks the probe.

    Args:
        argv: the command + args to invoke (list of str).
        run: injectable invoker returning an object with a ``returncode`` attr
            (a ``subprocess.CompletedProcess``-shape). ``None`` ⇒ real default.

    Returns:
        ``True`` iff the invocation completed with exit code 0, else ``False``.
    """
    if run is None:
        def run(_argv, **_kwargs):  # noqa: ANN001 — real default
            return subprocess.run(
                _argv,
                capture_output=True,
                shell=False,
                timeout=_BINARY_PROBE_TIMEOUT_SECONDS,
            )
    try:
        completed = run(argv)
    except Exception:  # noqa: BLE001 — any invocation failure ⇒ absent
        return False
    return getattr(completed, "returncode", 1) == 0


def probe_env_capability(var_name, *, environ=None) -> bool:
    """Return True iff env var ``var_name`` is set to a non-falsy value — the
    env-var capability probe (host-capability-declaration Phase 2).

    Generalizes the ``$ALGOBOOTH_REAL_AUDIO_DEVICE`` device read. Truthy iff the
    var is present AND its stripped, lowercased value is NOT in the shared
    ``_FALSY_ENV_VALUES`` set (``""``/``0``/``false``/``no``/``off``) — so an
    inherited empty export does not register a capability as present.

    Args:
        var_name: the environment variable name.
        environ: injectable mapping (``--test`` passes a dict). ``None`` ⇒
            the real ``os.environ``.

    Returns:
        ``True`` iff set to a non-falsy value, else ``False``.
    """
    env = os.environ if environ is None else environ
    val = env.get(var_name)
    if val is None:
        return False
    return str(val).strip().lower() not in _FALSY_ENV_VALUES


# Predicate vocabulary for the "platform" probe kind (host-capability OS axis).
# A predicate name maps to a pure function of the host OS name (platform.system()
# returns "Windows"/"Linux"/"Darwin"). Closed set — an unknown predicate yields a
# constant-False probe (fail-safe absent, never a crash), mirroring the registry's
# missing-config fallback.
_PLATFORM_PREDICATES: dict[str, object] = {
    # The OS is anything OTHER than Windows (Linux or macOS). Backs the
    # non-windows-host capability: cfg(unix) code is un-runnable on Windows, so a
    # Windows host reports the capability ABSENT and defers (host-capability-
    # saturated) instead of looping a real-device re-open.
    "non-windows": (lambda system_name: system_name.strip().lower() != "windows"),
}


def probe_platform_capability(predicate, *, system_fn=platform.system) -> bool:
    """Return True iff the host OS satisfies ``predicate`` — the OS/platform
    capability probe (device-vs-host mis-classification, Round 41, 2026-06-29).

    The OS is DETERMINISTICALLY detectable (unlike a network peer), so this is a
    real probe, not a constant-False placeholder. ``predicate`` is a key into the
    closed ``_PLATFORM_PREDICATES`` map; each value is a pure function of the OS
    name string returned by ``system_fn`` ("Windows"/"Linux"/"Darwin"). An unknown
    predicate (or any evaluation error) reports ``False`` — an unrecognized OS
    constraint is an absent capability, never a propagated exception.

    Args:
        predicate: a key into ``_PLATFORM_PREDICATES`` (e.g. ``"non-windows"``).
        system_fn: injectable OS-name source (``--test`` / unit tests pass a stub
            returning ``"Windows"`` / ``"Linux"``). ``platform.system`` ⇒ the real
            host OS.

    Returns:
        ``True`` iff the host OS satisfies the named predicate, else ``False``.
    """
    fn = _PLATFORM_PREDICATES.get(predicate)
    if fn is None:
        return False
    try:
        return bool(fn(system_fn()))
    except Exception:  # noqa: BLE001 — any probe failure ⇒ absent
        return False


def ensure_runtime(
    repo_root: Path,
    *,
    config: dict | None = None,
    probe=None,
    restart=None,
    stale_check=None,
    read_lock=None,
    live_session_id=None,
    kernel_start_time_fn=None,
    sleep=None,
    write_lock=None,
    recover_identity=None,
    kill=None,
    sidecar_check=None,
    frontend_probe=None,
    boot_alive=None,
) -> dict:
    """Ensure the dev runtime + MCP server are up, CURRENT, **and verifiably
    owned**; return the M4 liveness/recovery verdict.

    REVERSE-REFERENCE (ensure-runtime-recovery-starves-cold-compile): the
    long-build-and-runtime-ownership LD3 bounded-recovery contract below was
    RE-SCOPED by ``docs/bugs/ensure-runtime-recovery-starves-cold-compile``. The
    ≤5×backoff ``_recover_runtime`` loop is now reserved for a genuinely *dead*
    runtime (both ports down — a real crash); a runtime still *compiling* (the
    cold Rust build: Vite :1420 up, backend :3333 not yet serving) is instead
    PATIENTLY WAITED on via ``_await_compile_serving`` (never kill-restarted),
    because restart-and-immediately-probe starved a multi-minute cold compile
    into 5 wasted kill-restarts → a false BLOCKED. See ``_ensure_runtime_m4`` /
    ``_classify_compile_state`` / ``_await_compile_serving``.

    REVERSE-REFERENCE (ensure-runtime-starves-pre-vite-sidecar-build): the
    cold-compile re-scope above covered only the *Vite-up* window (its sole
    "still booting" signal is Vite :1420 being up). The PRE-VITE window — the
    multi-minute ``BeforeDevCommand``/``sidecar:build`` phase where BOTH ports are
    still down while the spawned boot process is alive — was still misclassified
    ``dead`` and kill-restarted. ``docs/bugs/ensure-runtime-starves-pre-vite-
    sidecar-build`` (the pre-Vite sibling of ``ensure-runtime-recovery-starves-
    cold-compile``) adds a SECOND "still booting" signal, ``boot_alive`` (the
    liveness of the ``restart()``-spawned boot process), threaded here alongside
    ``frontend_probe``: a both-ports-down-but-live-boot observation now classifies
    ``compiling`` (patient-wait), not ``dead``. Default-off (``boot_liveness``
    config key absent / ``boot_alive → False``) is byte-identical to the prior
    behavior. See ``_classify_compile_state`` (3rd ``boot_alive`` arg),
    ``_route_legacy_non_serving`` / ``_route_non_serving``, and
    ``_await_compile_serving`` (the went-dead check is now an OR of both signals).

    long-build-and-runtime-ownership Phase 2 (LD2/LD3) reworks this IN PLACE
    into the idempotent M4 gatekeeper. The verdict is a **superset** of the
    legacy ``{status, mcp_tools_present, health_code}`` shape::

        {"state": "READY"|"STALE"|"HIJACKED"|"DEAD"|"BLOCKED",
         "ownership_verified": bool,
         "health_code": int,
         "mcp_tools_present": bool,
         "terminal_blocker": str | None,
         "status": "ready"|"booted"|"stale-rebuilt"}   # legacy, retained

    Two call modes (backward-compatible):

      - **M4 mode** (Identity engaged) — the caller injects a `live_session_id`
        (and/or `read_lock` / `kernel_start_time_fn`). ``ensure_runtime`` runs
        the three-phase evaluation:

          1. **Identity** — ``read_lock()`` parses ``.runtime.lock.json``;
             ``verify_runtime_ownership`` compares the recorded
             ``(start_time, controller_session_id)`` against the live kernel /
             session. A live PID whose ownership does NOT verify (divergent
             start_time / foreign session) while ``/health`` answers is a foreign
             port-holder ⇒ ``HIJACKED``. A missing/dead PID (kernel start_time
             ``None``) ⇒ ``DEAD``. No lock + ``/health`` answering ⇒ ``HIJACKED``
             (health=200 is NOT proof of ownership — LD1); no lock + nothing
             answering ⇒ ``DEAD``.
          2. **Staleness** — for an owned runtime, ``stale_check()`` True ⇒
             ``STALE`` (default binding: ``_default_stale_check`` — the boot
             stamp vs. native-source-commit freshness predicate; see below).
          3. **Health** — for an owned, current runtime, ``probe()`` 200 ⇒
             ``READY``; a refused ``/health`` despite a live owned PID ⇒
             ``DEAD``.

        (WU-1 CLASSIFIES; the bounded-recovery / BLOCKED / never-SIGKILL
        fail-safe land in WU-2 — STALE/DEAD here do NOT yet auto-recover.)

      - **Legacy mode** (no Identity callables) — the pre-M4 boot/stale/ready
        flow runs unchanged (DOWN→restart→booted; UP+stale→restart→stale-rebuilt;
        UP+current→ready). The returned dict is upgraded to the verdict superset
        (``state`` derived via ``_LEGACY_STATUS_TO_STATE``, ``ownership_verified:
        False``, ``terminal_blocker: None``) so a caller never sees a missing key.

    Determinism / injection (the parameters that make ``--test`` hermetic):
      - ``probe``               — callable() -> (http_code:int, payload:dict|None).
      - ``restart``             — callable() -> bool (truthy on success).
      - ``stale_check``         — callable() -> bool (True == stale binary).
      - ``read_lock``           — callable() -> lock dict | None (default: a
                                  best-effort ``read_runtime_lock`` over the
                                  config's ``lock_filename``).
      - ``live_session_id``     — the controller session id threaded into
                                  ``verify_runtime_ownership`` (None ⇒ legacy mode).
      - ``kernel_start_time_fn``— callable(pid, *, platform) -> float|None
                                  (default: the real ``kernel_start_time``).

    AlgoBooth specifics (port, restart command, globs, the asserted MCP tool,
    the lock filename) are read from ``config`` (default
    ``_ENSURE_RUNTIME_DEFAULT_CONFIG``) — NOT hard-coded into the control flow,
    keeping this shared-harness function repo-agnostic.
    """
    cfg = dict(_ENSURE_RUNTIME_DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    health_url = cfg["health_url"]
    tool_name = cfg.get("mcp_tool_name", "")

    if probe is None:
        probe = lambda: _default_runtime_probe(health_url)
    # Pre-Vite boot-liveness holder (ensure-runtime-starves-pre-vite-sidecar-build
    # Phase 3 — production-seam wiring). The default `restart()` closure below
    # spawns the `dev:restart` boot process and STASHES the resulting `Popen`
    # handle here; the default `boot_alive()` (bound further down when
    # `boot_liveness` is configured) reads it back via `.poll()` — None ⇒ the boot
    # process is still running ⇒ the cold pre-Vite `BeforeDevCommand`/`sidecar:build`
    # window is in progress, NOT a dead host. A plain dict (not `nonlocal`) is the
    # closure-shared holder so BOTH the `restart` and `boot_alive` closures mutate /
    # read the SAME live handle without rebinding. When `restart` is INJECTED (every
    # `--test` path), this holder stays empty, so the default `boot_alive` reports
    # NOT-booting (fail-safe) — and an injected `boot_alive` overrides it entirely,
    # so the test contract "injected boot_alive still wins" is preserved.
    _boot_handle: dict[str, Any] = {"proc": None}
    if restart is None:
        def restart() -> bool:
            # Fire dev:restart in the background, then poll /health to 200.
            #
            # ensure-runtime-cold-boot-starvation-round-3 (the LIVE-confirmed root
            # cause the two prior unit-test-green fixes never reached): the spawn is
            # PLATFORM-BLIND. `restart_command` is `npm run dev:restart`, and on
            # Windows `npm` is `npm.cmd` — a batch shim that Windows `CreateProcess`
            # will NOT resolve from a bare-token argv (no `.cmd`/PATHEXT lookup
            # without a shell). So `subprocess.Popen(shlex.split("npm run …"))` with
            # the default `shell=False` raises `FileNotFoundError` ([WinError 2]) —
            # caught by the `(OSError, ValueError)` guard below, which returns False
            # BEFORE the boot is ever spawned, BEFORE `_boot_handle` is stashed, and
            # BEFORE `write_boot_stamp` runs. The whole boot-liveness / time-window-
            # grace / patient-wait machinery (rounds 32 + 2) is therefore DEAD on
            # Windows: no boot ⇒ no stamp ⇒ `boot_alive()` always False ⇒ every
            # `_recover_runtime` iteration classifies `dead` and "kill-restarts" a
            # boot that never launched, exhausting the ≤5× cap in ~60-80s → false
            # `mcp-runtime-unready` BLOCKED. (The manual `npm run dev:restart` works
            # because the interactive shell DOES resolve `npm.cmd`; the asymmetry is
            # exactly the shell.) Both prior fixes were unit-green because EVERY test
            # either injects `restart` or monkeypatches `lazy_core.subprocess` with a
            # fake whose `.Popen` always succeeds — so the real, platform-blind spawn
            # was never exercised.
            #
            # Fix: on Windows, spawn through the shell (`shell=True` with the command
            # STRING — a list arg is ignored under `shell=True` on Windows) so the
            # `.cmd` shim resolves exactly as it does for a manual invocation. On
            # POSIX keep the safer no-shell shlex-split argv (the command is a repo
            # config value, and `cmd.exe`/`/bin/sh` quoting differences are avoided).
            try:
                if os.name == "nt":
                    proc = subprocess.Popen(  # noqa: S602 — repo-config command, not user input
                        cfg["restart_command"],
                        cwd=str(repo_root),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=True,
                    )
                else:
                    proc = subprocess.Popen(  # noqa: S603 — repo-config command, not user input
                        shlex.split(cfg["restart_command"]),
                        cwd=str(repo_root),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            except (OSError, ValueError):
                return False
            # Stash the live boot handle so the boot-liveness signal can read its
            # `.poll()` during the pre-Vite window while BOTH ports are still down.
            _boot_handle["proc"] = proc
            # ALSO record the spawn epoch to a persistent stamp file
            # (ensure-runtime-recovery-starves-cold-compile-round-2). The handle
            # `.poll()` is NOT trustworthy on Windows — `restart_command` spawns a
            # short-lived npm/cmd shell-chain wrapper that exits seconds after
            # launching the detached `tauri dev`/`cargo build` child, so its
            # `.poll()` reports an exit code long before the ~3.5-min cold compile
            # finishes. The persistent stamp drives the time-window grace in
            # `boot_alive()` below, which survives the wrapper exiting AND survives
            # across the bounded `_recover_runtime` loop (so the loop's first
            # restart spawns ONE compile and every subsequent iteration sees "a
            # boot is in progress" and STOPS re-killing it — the murder-site fix).
            write_boot_stamp(repo_root, spawn_ts=time.time())
            for _ in range(90):  # ~7.5 min ceiling (90 × 5s)
                code, _payload = probe()
                if code == 200:
                    return True
                time.sleep(5)
            return False
    if stale_check is None:
        # stale-runtime-health-200-false-blocked: bind the REAL freshness
        # predicate (previously this defaulted to `lambda: False`, making the
        # STALE verdict UNREACHABLE in production — stale_binary.py shipped as
        # an orphaned predicate with no production caller). The fail-safe
        # direction (missing signal / any error → not stale) is preserved
        # INSIDE `_default_stale_check` itself, so the health=200 gate stays
        # the primary guard exactly as before whenever no boot signal exists.
        stale_check = lambda: _default_stale_check(repo_root, cfg)
    if sidecar_check is None:
        # Sidecar-pipe readiness (Leg A,
        # env-transient-counts-against-validation-retry-budget). When the config
        # asserts the sidecar, bind the real get_sidecar_status probe; otherwise
        # the assertion is skipped (the sidecar is treated as connected — the
        # default-off, repo-agnostic path). A legacy config dict without the key
        # is tolerated via .get(), so an un-migrated override never raises.
        if cfg.get("assert_sidecar_connected"):
            _sidecar_url = cfg.get(
                "sidecar_status_url",
                _ENSURE_RUNTIME_DEFAULT_CONFIG["sidecar_status_url"],
            )
            sidecar_check = lambda: _default_sidecar_probe(_sidecar_url)
        else:
            sidecar_check = lambda: True
    if frontend_probe is None:
        # Two-port cold-compile discriminator
        # (ensure-runtime-recovery-starves-cold-compile, Phase 1). When the config
        # carries the :1420 frontend keys, bind the real Vite reachability probe;
        # otherwise the discriminator degrades to today's :3333-only behavior
        # (frontend treated as DOWN → a non-serving backend classifies as `dead`,
        # the bounded-recovery path — byte-identical to today for a non-:1420
        # repo). A legacy config dict without the key is tolerated via .get(), so
        # an un-migrated override never raises. Mirrors the sidecar_check binding.
        _frontend_url = cfg.get("frontend_health_url")
        if _frontend_url:
            frontend_probe = lambda: _default_frontend_probe(_frontend_url)
        else:
            frontend_probe = lambda: False
    if boot_alive is None:
        # Pre-Vite boot-liveness signal
        # (ensure-runtime-starves-pre-vite-sidecar-build, Phase 1). When the
        # config asserts the boot-liveness signal, bind the real source — the
        # liveness of the `restart()`-spawned boot process. That boot process is
        # the `Popen` the production `restart()` closure already owns (see the
        # default `restart` above): in production a boot-liveness read consults
        # that in-process handle's `.poll()` (None ⇒ still running ⇒ alive), so
        # NO URL probe / `_default_*` helper is needed — the handle reaches the
        # classifier in-process via this same `ensure_runtime` call. Tests always
        # INJECT `boot_alive`, so the production-only branch below is a documented
        # placeholder that fail-safes toward NOT-booting (lambda: False) until the
        # CLI-seam handle-threading wires a live handle (Phase 3 / consumer). A
        # legacy config dict without the key is tolerated via .get(), so an
        # un-migrated override never raises. Mirrors the frontend_probe binding.
        if cfg.get("boot_liveness"):
            # Production source: the in-process boot-process `Popen` handle's
            # liveness (ensure-runtime-starves-pre-vite-sidecar-build Phase 3 —
            # the CLI-seam wiring this branch's placeholder was waiting on). The
            # default `restart()` closure above stashes the spawned boot handle in
            # `_boot_handle["proc"]`; a live signal reads it back here:
            #   - no handle yet (restart not called / spawn failed) ⇒ None ⇒ NOT
            #     booting (fail-safe — a genuinely dead host still reaches bounded
            #     recovery, never a forever patient-wait);
            #   - handle present + `.poll()` is None ⇒ the boot process is STILL
            #     RUNNING ⇒ the pre-Vite cold window is in progress ⇒ alive
            #     (`_classify_compile_state` returns `compiling`, patient-wait);
            #   - handle present + `.poll()` is an exit code ⇒ the boot process
            #     EXITED. On Windows this is the COMMON case while the compile is
            #     still running — the npm/cmd wrapper exits early
            #     (ensure-runtime-recovery-starves-cold-compile-round-2). So an
            #     exited handle does NOT by itself mean "dead": fall through to the
            #     persistent boot-spawn TIME-WINDOW grace, which reports the cold
            #     boot as still in progress for `_BOOT_SPAWN_GRACE_SECONDS` after
            #     the spawn regardless of the wrapper handle's fate.
            #   - no handle AND no fresh stamp ⇒ NOT booting (fail-safe — a
            #     genuinely dead host still reaches bounded recovery and ages out of
            #     the grace into BLOCKED; never a forever patient-wait).
            # `.poll()` never raises for a valid handle; a defensive guard keeps a
            # surprising handle state fail-safe toward the grace check.
            def boot_alive() -> bool:
                proc = _boot_handle.get("proc")
                if proc is not None:
                    try:
                        if proc.poll() is None:
                            return True  # wrapper still alive ⇒ definitely booting
                    except Exception:  # noqa: BLE001 — fall through to the grace
                        pass
                # Wrapper exited (or no handle this call): trust the persistent
                # time-window grace — the Windows-robust cold-boot-in-progress
                # detector that survives the npm/cmd wrapper exiting early.
                return boot_recently_spawned(repo_root)
        else:
            boot_alive = lambda: False

    # ---- M4 mode: Identity engaged (LD3) -------------------------------------
    # Identity is "engaged" iff the caller threads a controller session id OR an
    # explicit lock/kernel reader — i.e. it wants verifiable-ownership routing.
    identity_engaged = (
        live_session_id is not None
        or read_lock is not None
        or kernel_start_time_fn is not None
    )
    if identity_engaged:
        if read_lock is None:
            read_lock = lambda: read_runtime_lock(repo_root, config=cfg)
        if kernel_start_time_fn is None:
            kernel_start_time_fn = kernel_start_time
        if sleep is None:
            sleep = time.sleep
        if write_lock is None:
            def write_lock(**kw):
                write_runtime_lock(repo_root, config=cfg, **kw)
        # recover_identity / kill default to None — recovery rewrites the lock
        # only when an identity discovery callable is supplied, and the HIJACKED
        # fail-safe NEVER kills (kill is wired only so a test can assert it is
        # not called; production passes None and no kill path exists).
        return _ensure_runtime_m4(
            cfg,
            probe=probe,
            restart=restart,
            stale_check=stale_check,
            read_lock=read_lock,
            live_session_id=live_session_id,
            kernel_start_time_fn=kernel_start_time_fn,
            sleep=sleep,
            write_lock=write_lock,
            recover_identity=recover_identity,
            tool_name=tool_name,
            sidecar_check=sidecar_check,
            frontend_probe=frontend_probe,
            boot_alive=boot_alive,
        )

    # ---- Legacy mode: pre-M4 boot/stale/ready flow ---------------------------
    # ensure-runtime-legacy-mode-optimistic-ready-verdict (Phase 1): the down /
    # stale-rebuild arms used to hard-set status='booted'/'stale-rebuilt'
    # UNCONDITIONALLY after the post-restart re-probe, so a still-dead runtime
    # returned state: READY with a non-200 health_code (the optimistic lie). The
    # verdict is now DERIVED from the re-probe code, reusing the SAME honest M4
    # routing helpers (_classify_compile_state → patient-wait / bounded-recovery)
    # so a non-200 re-probe yields DEAD→READY-on-200|BLOCKED, never a false READY.
    # The 200 paths are byte-identical to before (booted / stale-rebuilt / ready).
    if sleep is None:
        sleep = time.sleep

    code, payload = probe()
    if code != 200:
        # Runtime DOWN → boot it, then re-probe.
        restart()
        code, payload = probe()
        if code == 200:
            status = "booted"  # recovered on the first restart (unchanged)
        else:
            # Still non-serving after the boot attempt. Route the re-probe code
            # through the same honest classifier the M4 path uses instead of
            # claiming READY: a `compiling` runtime (frontend up) is patiently
            # waited on; a genuinely `dead` runtime enters bounded recovery and
            # ends READY only on a healthy re-probe, else BLOCKED.
            return _route_legacy_non_serving(
                cfg, code=code, payload=payload, probe=probe, restart=restart,
                frontend_probe=frontend_probe, sleep=sleep, tool_name=tool_name,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            )
    elif stale_check():
        # Runtime UP but binary STALE → force a rebuild, then re-probe.
        restart()
        code, payload = probe()
        if code == 200:
            status = "stale-rebuilt"  # rebuilt and serving (unchanged)
        else:
            # The rebuild left the runtime non-serving — do NOT claim STALE/READY
            # honestly; route the re-probe through the same recovery machinery.
            return _route_legacy_non_serving(
                cfg, code=code, payload=payload, probe=probe, restart=restart,
                frontend_probe=frontend_probe, sleep=sleep, tool_name=tool_name,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            )
    else:
        # Runtime UP and CURRENT.
        status = "ready"

    # 200-path verdict (booted / stale-rebuilt / ready) — unchanged honest shape.
    # (code == 200 here, so _mcp_tools_present_honest is byte-identical to the
    # bare _mcp_tool_in_payload; used for consistency with the verdict builder.)
    return {
        "status": status,
        "state": _LEGACY_STATUS_TO_STATE.get(status, "READY"),
        "ownership_verified": False,
        "mcp_tools_present": _mcp_tools_present_honest(payload, tool_name, code),
        "health_code": code,
        "terminal_blocker": None,
    }


def _route_legacy_non_serving(
    cfg, *, code, payload, probe, restart, frontend_probe, sleep, tool_name,
    sidecar_check=None, boot_alive=None,
):
    """Honest verdict for a legacy-mode runtime still non-serving after a boot /
    rebuild attempt (ensure-runtime-legacy-mode-optimistic-ready-verdict, Phase 1).

    Mirrors the M4 path's ``_route_non_serving``: branch the non-200 re-probe on
    ``_classify_compile_state(code, frontend_up, boot_alive)`` — a ``compiling``
    runtime (Vite :1420 up, backend not yet serving — OR, per
    ensure-runtime-starves-pre-vite-sidecar-build Phase 2, BOTH ports down but the
    boot process still ALIVE: the pre-Vite ``BeforeDevCommand``/``sidecar:build``
    window) is PATIENTLY WAITED on via ``_await_compile_serving`` (never
    kill-restarted); a genuinely ``dead`` runtime (frontend also down AND no live
    boot) enters the bounded ``_recover_runtime`` crash loop → READY on a healthy
    re-probe, else BLOCKED.

    Legacy mode has no ownership identity, so ``ownership_verified=False`` and the
    lock-rewrite is skipped (``recover_identity=None``, ``write_lock`` a no-op).
    The result is the verdict SUPERSET — it NEVER returns ``state: READY`` with a
    non-200 ``health_code`` (the honest invariant). ``mcp_tools_present`` is read
    from whatever payload the recovery machinery resolves, so a non-serving
    runtime with no configured tool name reports ``False`` (not vacuously True).
    """
    if boot_alive is None:
        boot_alive = lambda: False
    try:
        frontend_up = bool(frontend_probe())
    except Exception:  # noqa: BLE001 — a probe error is treated as down (dead)
        frontend_up = False
    try:
        boot_up = bool(boot_alive())
    except Exception:  # noqa: BLE001 — a probe error is treated as not-booting
        boot_up = False

    def _noop_write_lock(**_kw):
        # Legacy mode has no ownership lock to rewrite.
        return None

    if _classify_compile_state(code, frontend_up, boot_up) == "compiling":
        verdict = _await_compile_serving(
            cfg, ownership_verified=False, probe=probe,
            frontend_probe=frontend_probe, sleep=sleep, write_lock=_noop_write_lock,
            recover_identity=None, tool_name=tool_name,
            initial_code=code, initial_payload=payload,
            sidecar_check=sidecar_check, boot_alive=boot_alive,
        )
        if verdict is not _COMPILE_WENT_DEAD:
            return verdict
        # compiling → dead mid-wait: fall through to bounded crash recovery.
    return _recover_runtime(
        cfg, "DEAD", ownership_verified=False, probe=probe, restart=restart,
        sleep=sleep, write_lock=_noop_write_lock, recover_identity=None,
        tool_name=tool_name, initial_code=code, initial_payload=payload,
        sidecar_check=sidecar_check,
        # ensure-runtime-recovery-starves-cold-compile-round-2: the legacy path gets
        # the SAME murder-site handoff as M4 — once the bounded loop's first
        # restart() puts a real compile in flight (fresh boot stamp), hand off to the
        # patient wait instead of re-killing it. Without this, the legacy
        # no-run-marker `--ensure-runtime` call (live_session_id None) was still
        # starved.
        frontend_probe=frontend_probe, boot_alive=boot_alive,
        await_compile=lambda init_code, init_payload: _await_compile_serving(
            cfg, ownership_verified=False, probe=probe,
            frontend_probe=frontend_probe, sleep=sleep, write_lock=_noop_write_lock,
            recover_identity=None, tool_name=tool_name,
            initial_code=init_code, initial_payload=init_payload,
            sidecar_check=sidecar_check, boot_alive=boot_alive,
        ),
    )


def _runtime_verdict(state, *, ownership_verified, health_code, payload,
                     tool_name, terminal_blocker=None, status=None):
    """Build the M4 verdict dict (the superset shape).

    ``status`` (the legacy field) is derived from ``state`` when not supplied so
    every caller — old or new — sees both keys. ``READY``→``ready``,
    ``STALE``→``stale-rebuilt``, ``HIJACKED``/``DEAD``/``BLOCKED``→``booted``
    (the legacy flow never modelled a failed runtime; the legacy field is purely
    for the un-migrated part-5 reader and is superseded by ``state``)."""
    if status is None:
        status = {
            "READY": "ready",
            "STALE": "stale-rebuilt",
        }.get(state, "booted")
    return {
        "status": status,
        "state": state,
        "ownership_verified": bool(ownership_verified),
        "mcp_tools_present": _mcp_tools_present_honest(
            payload, tool_name, health_code
        ),
        "health_code": int(health_code or 0),
        "terminal_blocker": terminal_blocker,
    }


def _hijacked_blocker(lock):
    """The HIJACKED terminal_blocker message (LD3). Names the foreign port-holder
    and the never-SIGKILL safety rule so Phase 5 can surface it verbatim into a
    BLOCKED.md ``blocker_kind: mcp-runtime-unready``."""
    port = lock.get("port") if isinstance(lock, dict) else None
    where = f"port {port}" if port else "the runtime port"
    return (
        f"Runtime ownership could not be verified — a foreign process is holding "
        f"{where} (recorded PID/start_time/session diverges from the live kernel). "
        f"Refusing to SIGKILL an unowned process (LD3 safety/stability rule); "
        f"surface as BLOCKED (blocker_kind: mcp-runtime-unready) for operator "
        f"intervention."
    )


def _blocked_blocker(attempts):
    """The recovery-exhausted BLOCKED terminal_blocker message (LD3)."""
    return (
        f"Runtime recovery exhausted — restart() retried {attempts} times "
        f"(bounded cap {_RUNTIME_RECOVERY_MAX_ATTEMPTS}) with exponential backoff "
        f"without restoring a healthy, owned runtime. Halting with no further "
        f"retries (blocker_kind: mcp-runtime-unready)."
    )


def _cold_compile_timeout_blocker():
    """The patient-wait cold-compile-timeout terminal_blocker message
    (ensure-runtime-recovery-starves-cold-compile, Phase 2 / Open Question 5).

    DISTINCT verbatim text from ``_blocked_blocker`` so the operator can tell a
    cold-compile that genuinely never finished apart from a generic
    crash-recovery exhaustion — but it still maps to the SAME downstream
    ``blocker_kind: mcp-runtime-unready`` (no new blocker_kind). It describes the
    patient-wait semantics: the runtime was COMPILING (Vite up, backend not yet
    serving) and was WAITED on — never kill-restarted — for the full
    cold-compile budget without the backend ever reaching a serving state.
    """
    secs = int(_COLD_COMPILE_WAIT_MAX_POLLS * _COLD_COMPILE_WAIT_INTERVAL)
    return (
        f"Cold compile timed out — the runtime was still COMPILING (Vite dev "
        f"server up, backend /health not yet serving) and was patiently waited "
        f"on for ~{secs}s ({_COLD_COMPILE_WAIT_MAX_POLLS} polls) WITHOUT a "
        f"kill-restart, but the backend never reached a serving state. The "
        f"compile genuinely never finished (not a crash-recovery exhaustion). "
        f"Halting (blocker_kind: mcp-runtime-unready)."
    )


def _ensure_runtime_m4(
    cfg,
    *,
    probe,
    restart,
    stale_check,
    read_lock,
    live_session_id,
    kernel_start_time_fn,
    sleep,
    write_lock,
    recover_identity,
    tool_name,
    sidecar_check=None,
    frontend_probe=None,
    boot_alive=None,
):
    """The M4 Identity → Staleness → Health classifier + bounded recovery (LD3).

    Identity classifies the runtime; HIJACKED is a strict fail-safe (terminal
    blocker, NEVER restart/kill); STALE/DEAD enter the bounded exponential-backoff
    recovery loop (≤ ``_RUNTIME_RECOVERY_MAX_ATTEMPTS`` restarts) → READY on a
    re-probe success (lock rewritten) or BLOCKED on exhaustion.

    ensure-runtime-recovery-starves-cold-compile (Phase 2): the LD3 bounded loop is
    RE-SCOPED to genuine crashes. Each point that today routes a non-serving runtime
    into ``_recover_runtime`` now first consults ``_classify_compile_state(code,
    frontend_probe())``: a ``compiling`` runtime (Vite :1420 up, backend :3333 not
    yet serving — a cold Rust compile in progress) is PATIENTLY WAITED on via
    ``_await_compile_serving`` (never kill-restarted); only a genuinely ``dead``
    runtime (both ports down) enters the ≤5×backoff crash loop. A ``compiling → dead``
    transition mid-wait falls through to that same crash loop. Default-off: when no
    frontend signal is present (``frontend_probe → False``), every non-serving runtime
    classifies as ``dead`` ⇒ byte-identical to today's recovery behavior.
    """
    if frontend_probe is None:
        # Defensive default for legacy/un-threaded callers (e.g. a test that does
        # not inject one): no frontend signal ⇒ never `compiling` ⇒ today's path.
        frontend_probe = lambda: False
    if boot_alive is None:
        # Defensive default (ensure-runtime-starves-pre-vite-sidecar-build): no
        # boot-liveness signal ⇒ a both-ports-down runtime is never the pre-Vite
        # `compiling` case ⇒ today's `dead`/recovery path. Default-off byte-
        # identity preserved for every legacy/un-threaded caller.
        boot_alive = lambda: False
    code, payload = probe()
    lock = read_lock()

    def _route_non_serving(from_state, *, ownership_verified, code, payload):
        """Branch a non-serving runtime on the two-port (+ boot-liveness)
        classifier: `compiling` → patient wait (never restart); `dead`/default-off
        → bounded crash recovery. A `compiling` here covers BOTH the Vite-up
        backend-compiling window AND the pre-Vite both-ports-down-but-live-boot
        window (ensure-runtime-starves-pre-vite-sidecar-build Phase 2). A
        `compiling → dead` transition during the patient wait routes back here as
        the bounded crash loop."""
        try:
            frontend_up = bool(frontend_probe())
        except Exception:  # noqa: BLE001 — a probe error is treated as down (dead)
            frontend_up = False
        try:
            boot_up = bool(boot_alive())
        except Exception:  # noqa: BLE001 — a probe error is treated as not-booting
            boot_up = False
        if _classify_compile_state(code, frontend_up, boot_up) == "compiling":
            verdict = _await_compile_serving(
                cfg, ownership_verified=ownership_verified, probe=probe,
                frontend_probe=frontend_probe, sleep=sleep, write_lock=write_lock,
                recover_identity=recover_identity, tool_name=tool_name,
                initial_code=code, initial_payload=payload,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            )
            if verdict is not _COMPILE_WENT_DEAD:
                return verdict
            # compiling → dead mid-wait: fall through to bounded crash recovery.
        return _recover_runtime(
            cfg, from_state, ownership_verified=ownership_verified, probe=probe,
            restart=restart, sleep=sleep, write_lock=write_lock,
            recover_identity=recover_identity, tool_name=tool_name,
            initial_code=code, initial_payload=payload, sidecar_check=sidecar_check,
            # ensure-runtime-recovery-starves-cold-compile-round-2: thread the
            # cold-boot-in-progress signals so the bounded crash loop HANDS OFF to
            # the patient wait the instant its own first `restart()` puts a genuine
            # compile in flight — instead of re-killing it on the next iteration.
            frontend_probe=frontend_probe, boot_alive=boot_alive,
            await_compile=lambda init_code, init_payload: _await_compile_serving(
                cfg, ownership_verified=ownership_verified, probe=probe,
                frontend_probe=frontend_probe, sleep=sleep, write_lock=write_lock,
                recover_identity=recover_identity, tool_name=tool_name,
                initial_code=init_code, initial_payload=init_payload,
                sidecar_check=sidecar_check, boot_alive=boot_alive,
            ),
        )

    # ---- Phase 1: Identity ---------------------------------------------------
    if not isinstance(lock, dict):
        # No recorded ownership. A /health that answers is, by default, an
        # unverified foreign port-holder (health=200 is NOT proof of ownership —
        # LD1) ⇒ HIJACKED (strict fail-safe: never kill it); nothing answering ⇒
        # DEAD (recover).
        #
        # Gap-2 soft owned-unverified-serving READY on the lock-is-None (and
        # lock-diverged) branch (harness-mcp-observation-gap-disposition-and-
        # hijacked-runtime, Phase 2). The post-mcp-test HIJACKED case falls HERE:
        # an /mcp-test cycle does its OWN dev:restart / engine boot inside the
        # cycle subagent, which overwrites or invalidates `.runtime.lock.json`'s
        # ownership record (the lock no longer matches the live kernel/session, or
        # is absent), so read_lock() returns None on the orchestrator's next
        # --ensure-runtime probe. Pre-fix this returned terminal HIJACKED even
        # though the serving runtime is PROVABLY this app's (its MCP tools are
        # present in `payload`), forcing a dev:kill + cold reboot every cycle
        # (which re-introduces cold-boot flake). The lock divergence is
        # bookkeeping-only here, NOT a foreign takeover.
        #
        # `_mcp_tools_present_honest(payload, tool_name, code)` is the honest
        # "serving MY app" signal — the SAME signal the lock-present soft-READY
        # path at the `owned == False` branch below consults (see the
        # is_owned_unverified_serving rationale further down). When it confirms
        # THIS app's tool surface at health 200, re-adopt ownership by rewriting
        # the lock for the live serving process and return a non-terminal soft
        # READY (ownership_verified False) instead of the terminal HIJACKED
        # fail-safe. A genuinely foreign port-holder serving a DIFFERENT app's tool
        # surface FAILS `_mcp_tools_present_honest` and stays terminal HIJACKED —
        # so the LD3 strict fail-safe (never SIGKILL / never re-adopt a foreign
        # process) is preserved. A stale-but-serving runtime is NOT masked: route
        # it through STALE/rebuild FIRST (mirrors the owned-unverified ordering so
        # the soft-READY shortcut never short-circuits a stale rebuild).
        if code == 200 and _mcp_tools_present_honest(payload, tool_name, code):
            if stale_check():
                # Stale binary on a lock-diverged-but-serving-our-tools runtime:
                # route through STALE/rebuild (do NOT mask with a soft READY).
                return _route_non_serving(
                    "STALE", ownership_verified=False, code=code, payload=payload,
                )
            # Re-adopt ownership: rewrite `.runtime.lock.json` for the live serving
            # process (best-effort, mirroring the existing recover_identity →
            # write_lock pattern used on the post-recovery READY path) so the NEXT
            # cycle verifies against the now-recorded ownership instead of
            # re-deriving lock-is-None.
            if recover_identity is not None:
                try:
                    ident = recover_identity()
                except Exception:  # noqa: BLE001 — identity discovery is best-effort
                    ident = None
                if isinstance(ident, dict):
                    try:
                        write_lock(
                            pid=ident.get("pid"),
                            start_time=ident.get("start_time"),
                            port=cfg.get("port"),
                            artifact_hash=ident.get("artifact_hash"),
                            controller_session_id=ident.get("controller_session_id"),
                        )
                    except Exception:  # noqa: BLE001 — a lock-write error never
                        # downgrades a provably-ours serving runtime to HIJACKED.
                        pass
            return _runtime_verdict(
                "READY", ownership_verified=False, health_code=code,
                payload=payload, tool_name=tool_name, terminal_blocker=None,
            )
        if code == 200:
            # Health answers but the tool surface is NOT ours (or the honest signal
            # reports not-serving) — an unverified foreign port-holder. HIJACKED
            # strict fail-safe: never kill, never re-adopt (LD3).
            return _runtime_verdict(
                "HIJACKED", ownership_verified=False, health_code=code,
                payload=payload, tool_name=tool_name,
                terminal_blocker=_hijacked_blocker(lock),
            )
        return _route_non_serving(
            "DEAD", ownership_verified=False, code=code, payload=payload,
        )

    owned = verify_runtime_ownership(
        lock,
        live_session_id=live_session_id,
        kernel_start_time_fn=kernel_start_time_fn,
    )
    if not owned:
        # The recorded PID is either dead (kernel start_time None ⇒ DEAD, a
        # recovery candidate) or held by a foreign process whose start_time/
        # session diverges (a LIVE foreign owner ⇒ HIJACKED, NEVER killed).
        live_start = None
        try:
            live_start = kernel_start_time_fn(lock.get("pid"))
        except TypeError:
            live_start = kernel_start_time_fn(lock.get("pid"), platform=sys.platform)
        except Exception:  # noqa: BLE001 — best-effort
            live_start = None
        if live_start is None:
            return _route_non_serving(
                "DEAD", ownership_verified=False, code=code, payload=payload,
            )
        # ensure-runtime-false-hijacked-on-owned-serving-runtime (P1) — SOFT
        # owned-unverified READY. `verify_runtime_ownership` is False here, but a
        # live PID whose kernel start_time MATCHES the recorded lock start_time is
        # the run's OWN booted process (start_time match defeats PID reuse — a
        # foreign port-holder via a reused PID reports a divergent start_time). So
        # if ALL of: (a) the lock PID is that same serving process
        # (`live_start == lock['start_time']`), (b) /health answers 200, AND
        # (c) the runtime is provably serving THIS app's MCP tools
        # (`_mcp_tools_present_honest`, derived the SAME way the verdict builder
        # does so guard and verdict agree) — then the divergence is bookkeeping-
        # only (the lock's controller_session_id and the threaded live_session_id
        # come from different sources; see verify_runtime_ownership). The runtime
        # is provably alive, ours, and serving, so we proceed with a non-terminal
        # READY (`ownership_verified: False`) instead of the terminal HIJACKED
        # fail-safe — and we NEVER SIGKILL (no restart on this path). If any
        # condition is False we fall through to the unchanged terminal HIJACKED
        # below. A genuinely STALE binary is NOT masked: stale_check() runs FIRST,
        # routing a stale-but-owned-unverified-serving runtime through the same
        # STALE/rebuild path a verified-owned one takes (the soft-READY shortcut
        # never short-circuits a stale rebuild).
        is_owned_unverified_serving = (
            code == 200
            and _mcp_tools_present_honest(payload, tool_name, code)
            and live_start == lock.get("start_time")
        )
        if is_owned_unverified_serving:
            if stale_check():
                # Stale binary on an owned-unverified-but-serving runtime: route
                # through STALE/rebuild (do NOT mask it with a soft READY).
                return _route_non_serving(
                    "STALE", ownership_verified=False, code=code, payload=payload,
                )
            return _runtime_verdict(
                "READY", ownership_verified=False, health_code=code,
                payload=payload, tool_name=tool_name, terminal_blocker=None,
            )
        # Live foreign PID — HIJACKED strict fail-safe: set the terminal_blocker
        # and return WITHOUT restart() or any kill of the foreign process (LD3).
        return _runtime_verdict(
            "HIJACKED", ownership_verified=False, health_code=code,
            payload=payload, tool_name=tool_name,
            terminal_blocker=_hijacked_blocker(lock),
        )

    # Ownership verified (the recorded PID is ours, alive, current session).
    # ---- Phase 2: Staleness --------------------------------------------------
    if stale_check():
        # A serving-but-stale runtime (code==200) classifies as `serving`, so it
        # rebuilds via _recover_runtime (the existing STALE→rebuild path). A stale
        # runtime that is ALSO not yet serving while Vite is up (a new-crate STALE
        # during a cold compile) classifies `compiling` ⇒ patient wait, not a
        # starved kill-restart (the cold-compile re-scope).
        return _route_non_serving(
            "STALE", ownership_verified=True, code=code, payload=payload,
        )

    # ---- Phase 3: Health -----------------------------------------------------
    if code == 200:
        # HTTP-healthy. But a runtime can be /health-200 while the MCP sidecar
        # named pipe is dead (a zombie node process holding it after a
        # dev:restart — env-transient-counts-against-validation-retry-budget,
        # Leg A). When the config asserts the sidecar, a disconnected pipe is NOT
        # READY: route into recovery (a dev:restart that reaps the stale pipe).
        # Default-off (sidecar_check None or lambda: True) preserves the bare
        # READY byte-for-byte. The recovery re-probe re-asserts the pipe, so a
        # restart that fixes HTTP but not the pipe ends BLOCKED, never READY.
        if sidecar_check is not None and not sidecar_check():
            # code==200 ⇒ classifies `serving`, so _route_non_serving falls through
            # to the existing _recover_runtime pipe-reap path (unchanged behavior).
            return _route_non_serving(
                "DEAD", ownership_verified=True, code=code, payload=payload,
            )
        return _runtime_verdict(
            "READY", ownership_verified=True, health_code=code,
            payload=payload, tool_name=tool_name,
        )
    # Owned, alive, current — but /health refused ⇒ the runtime endpoint is not
    # serving. Branch on the two-port classifier: a cold compile (Vite up) is
    # PATIENTLY WAITED on (the starvation fix); a genuinely dead backend (Vite
    # also down) enters today's bounded crash recovery.
    return _route_non_serving(
        "DEAD", ownership_verified=True, code=code, payload=payload,
    )


_COMPILE_WENT_DEAD = object()
"""Sentinel returned by ``_await_compile_serving`` when the runtime crossed from
``compiling`` to ``dead`` mid-wait (Vite went down) — the M4 caller routes this
into the bounded ``_recover_runtime`` crash path. NOT a verdict dict, so a caller
must check identity before treating the return as a verdict."""


def _await_compile_serving(
    cfg,
    *,
    ownership_verified,
    probe,
    frontend_probe,
    sleep,
    write_lock,
    recover_identity,
    tool_name,
    initial_code,
    initial_payload,
    sidecar_check=None,
    boot_alive=None,
):
    """Patient, NON-killing wait for a `compiling` runtime to reach serving
    (ensure-runtime-recovery-starves-cold-compile, Phase 2; pre-Vite extension
    ensure-runtime-starves-pre-vite-sidecar-build, Phase 2).

    A runtime classified ``compiling`` (Vite :1420 up, backend :3333 not yet
    serving — OR both ports down but the boot process still ALIVE: the pre-Vite
    ``BeforeDevCommand``/``sidecar:build`` window) is the cold boot/compile still
    in progress — it must be WAITED on, never kill-restarted (the starvation root
    cause). This poller:

      - polls ``probe()`` on the cold-compile-sized ceiling
        (``_COLD_COMPILE_WAIT_MAX_POLLS × _COLD_COMPILE_WAIT_INTERVAL`` ≈ 7.5 min,
        REUSING the production restart()-awaiter sizing — NOT the ≤5×backoff crash
        budget), NEVER calling ``restart()``/``kill`` while compiling;
      - returns a READY verdict once ``probe()`` answers 200 (AND, when
        ``sidecar_check`` is asserted, the sidecar pipe is connected — REUSING the
        existing recovery sidecar composition; rewriting the ownership lock via
        ``recover_identity``/``write_lock`` exactly like ``_recover_runtime``);
      - returns the ``_COMPILE_WENT_DEAD`` sentinel if the runtime goes dead
        mid-wait — the frontend goes down AND the boot process is no longer alive
        (``compiling → dead``) — so the M4 caller falls through to bounded
        ``_recover_runtime``. The pre-Vite analog of the Vite-up went-dead check:
        a live boot crossing to dead (``boot_alive`` going false) with both ports
        still down is the same fall-through (ensure-runtime-starves-pre-vite-
        sidecar-build Phase 2);
      - on ceiling exhaustion while STILL compiling, returns a BLOCKED verdict
        whose ``terminal_blocker`` is the DISTINCT ``_cold_compile_timeout_blocker``
        text (still ``blocker_kind: mcp-runtime-unready`` downstream).

    ``sleep`` is injected so ``--test`` is hermetic (no real 7.5-min wait).
    """
    if boot_alive is None:
        # Defensive default: no boot-liveness signal ⇒ the went-dead check is the
        # frontend-only check (byte-identical to the Vite-up-only prior behavior).
        boot_alive = lambda: False
    code, payload = initial_code, initial_payload
    for poll in range(_COLD_COMPILE_WAIT_MAX_POLLS):
        if code == 200:
            # Backend is serving. Compose the sidecar assertion (a serving-but-
            # pipe-dead runtime is NOT ready — keep waiting for the pipe, exactly
            # as _recover_runtime does on its healthy re-probe).
            if sidecar_check is not None and not sidecar_check():
                pass  # fall through to the re-poll below (pipe not yet connected)
            else:
                # Serving + (sidecar connected | not asserted) → READY. Rewrite
                # the ownership lock so the NEXT cycle verifies against the now-
                # serving process (best-effort, mirroring _recover_runtime).
                if recover_identity is not None:
                    try:
                        ident = recover_identity()
                    except Exception:  # noqa: BLE001
                        ident = None
                    if isinstance(ident, dict):
                        try:
                            write_lock(
                                pid=ident.get("pid"),
                                start_time=ident.get("start_time"),
                                port=cfg.get("port"),
                                artifact_hash=ident.get("artifact_hash"),
                                controller_session_id=ident.get("controller_session_id"),
                            )
                        except Exception:  # noqa: BLE001
                            pass
                return _runtime_verdict(
                    "READY", ownership_verified=ownership_verified,
                    health_code=code, payload=payload, tool_name=tool_name,
                )
        else:
            # Backend not yet serving — is it still compiling (Vite up OR boot
            # process alive) or has it crossed to dead (BOTH false)? The pre-Vite
            # window keeps the runtime `compiling` on the boot-liveness signal even
            # while Vite is still down (ensure-runtime-starves-pre-vite-sidecar-
            # build Phase 2). Only when NEITHER signal reports "still alive" does
            # the runtime cross to dead.
            try:
                still_frontend = bool(frontend_probe())
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as down
                still_frontend = False
            try:
                still_boot = bool(boot_alive())
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as not-booting
                still_boot = False
            if not still_frontend and not still_boot:
                # compiling → dead: abandon the patient wait, route to bounded
                # crash-recovery (the M4 caller checks the sentinel identity).
                return _COMPILE_WENT_DEAD
        # Still compiling (or serving-but-pipe-dead). Wait — NEVER restart/kill.
        try:
            sleep(_COLD_COMPILE_WAIT_INTERVAL)
        except Exception:  # noqa: BLE001 — a sleep error never aborts the wait
            pass
        code, payload = probe()

    # Final re-check after the loop's last probe: a 200 that landed exactly on the
    # last poll should still resolve READY rather than time out.
    if code == 200 and (sidecar_check is None or sidecar_check()):
        return _runtime_verdict(
            "READY", ownership_verified=ownership_verified,
            health_code=code, payload=payload, tool_name=tool_name,
        )

    # Ceiling exhausted while still compiling (or pipe never reconnected) → a
    # DISTINCT cold-compile-timeout BLOCKED (same blocker_kind downstream).
    return _runtime_verdict(
        "BLOCKED", ownership_verified=ownership_verified, health_code=code,
        payload=payload, tool_name=tool_name,
        terminal_blocker=_cold_compile_timeout_blocker(),
    )


def _recover_runtime(
    cfg,
    from_state,
    *,
    ownership_verified,
    probe,
    restart,
    sleep,
    write_lock,
    recover_identity,
    tool_name,
    initial_code,
    initial_payload,
    sidecar_check=None,
    frontend_probe=None,
    boot_alive=None,
    await_compile=None,
):
    """Bounded exponential-backoff recovery for a STALE/DEAD runtime (LD3).

    Up to ``_RUNTIME_RECOVERY_MAX_ATTEMPTS`` iterations of:
    ``sleep(backoff)`` → ``restart()`` → re-``probe()``. On a 200 re-probe the
    runtime is back: rewrite ``.runtime.lock.json`` with the recovered identity
    (when ``recover_identity`` supplies one) and return READY. On exhaustion
    (no healthy re-probe within the cap) return BLOCKED with a terminal_blocker —
    the loop-prevention guarantee that replaces the hand-rolled poll loops.

    ``sidecar_check`` (env-transient-counts-against-validation-retry-budget,
    Leg A): when supplied (the config asserts the sidecar), a healthy HTTP
    re-probe is NOT sufficient — the recovered runtime must ALSO reconnect the
    sidecar pipe. A restart that restores /health 200 but leaves the pipe dead
    (the zombie persists) does NOT count as recovered: the loop continues and,
    on exhaustion, the verdict is BLOCKED — never a READY against a pipe-dead
    runtime. ``None`` (legacy / default-off) preserves the HTTP-only contract.

    ``frontend_probe`` / ``boot_alive`` / ``await_compile`` (ensure-runtime-
    recovery-starves-cold-compile-round-2): the cold-boot-in-progress HANDOFF. The
    first ``restart()`` here legitimately spawns a cold ``tauri dev`` whose Rust
    compile runs ~3.5 min with both ports down. After EACH restart, if the re-probe
    is non-200 but ``_classify_compile_state`` reports ``compiling`` (Vite up OR the
    boot-spawn time-window grace is fresh), the loop HANDS OFF to the patient,
    non-killing ``await_compile`` instead of looping a second kill-``restart()``
    that would murder the in-progress compile (the root cause of the 5-restarts-in-
    60s starvation). Only the M4 path threads these (production); the legacy /
    default-off callers pass ``None`` and are byte-identical to the prior
    HTTP-only crash loop.
    """
    code, payload = initial_code, initial_payload
    attempts = 0
    for attempt in range(_RUNTIME_RECOVERY_MAX_ATTEMPTS):
        # Exponential backoff BEFORE each restart (1, 2, 4, 8, 16 …s). Injected
        # sleep makes --test assert the schedule with no real wait.
        try:
            sleep(_RUNTIME_RECOVERY_BACKOFF_BASE * (2 ** attempt))
        except Exception:  # noqa: BLE001 — a sleep error never aborts recovery
            pass
        attempts += 1
        try:
            restart()
        except Exception:  # noqa: BLE001 — a restart raising is a failed attempt
            continue
        code, payload = probe()
        # ensure-runtime-recovery-starves-cold-compile-round-2 — the murder-site
        # handoff. This `restart()` may have legitimately put a COLD COMPILE in
        # flight (the production `restart_command` kills then re-spawns `tauri dev`;
        # the Rust build then takes ~3.5 min with both ports down). If the re-probe
        # is still non-200 BUT the cold boot is genuinely in progress — Vite up, OR
        # the time-window boot-spawn grace reports a fresh spawn — DO NOT loop to a
        # second kill-`restart()` (which would run `kill-dev.js` and MURDER the
        # compile). Hand off to the patient, NON-killing `_await_compile_serving`
        # instead. The grace ages out past the cold-compile ceiling, so a host that
        # never actually compiles still exhausts the wait and reaches BLOCKED —
        # never a forever patient-wait of a dead host (fail-safe preserved). Only
        # wired in the M4 path (await_compile supplied); the legacy/None callers are
        # byte-identical to before.
        if code != 200 and await_compile is not None:
            try:
                fe_up = bool(frontend_probe()) if frontend_probe is not None else False
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as down
                fe_up = False
            try:
                boot_up = bool(boot_alive()) if boot_alive is not None else False
            except Exception:  # noqa: BLE001 — a probe error ⇒ treat as not-booting
                boot_up = False
            if _classify_compile_state(code, fe_up, boot_up) == "compiling":
                verdict = await_compile(code, payload)
                if verdict is not _COMPILE_WENT_DEAD:
                    return verdict
                # compiling → dead during the patient wait: resume the bounded
                # crash loop where we left off (the kill is now warranted — the
                # boot really did die).
                code, payload = probe()
        if code == 200:
            # HTTP is back — but if the config asserts the sidecar, the pipe must
            # ALSO be reconnected for this to count as recovered. A restart that
            # fixes /health but not the zombie-held pipe keeps retrying (and
            # ultimately BLOCKs) rather than declaring a pipe-dead runtime READY.
            if sidecar_check is not None and not sidecar_check():
                continue
            # Recovered. Rewrite the ownership lock with the new identity so the
            # NEXT cycle verifies against the restarted process (Persistent
            # Service re-attach contract). Best-effort: a missing identity or a
            # write error never downgrades a healthy runtime.
            if recover_identity is not None:
                try:
                    ident = recover_identity()
                except Exception:  # noqa: BLE001
                    ident = None
                if isinstance(ident, dict):
                    try:
                        write_lock(
                            pid=ident.get("pid"),
                            start_time=ident.get("start_time"),
                            port=cfg.get("port"),
                            artifact_hash=ident.get("artifact_hash"),
                            controller_session_id=ident.get("controller_session_id"),
                        )
                    except Exception:  # noqa: BLE001
                        pass
            return _runtime_verdict(
                "READY", ownership_verified=True, health_code=code,
                payload=payload, tool_name=tool_name,
            )

    # Exhausted the bounded cap without restoring health → BLOCKED, no retries.
    return _runtime_verdict(
        "BLOCKED", ownership_verified=ownership_verified, health_code=code,
        payload=payload, tool_name=tool_name,
        terminal_blocker=_blocked_blocker(attempts),
    )


# ===========================================================================
# Long-Build + Runtime Ownership (Phase 1) — cross-platform detached-spawn
# primitive + verifiable on-disk ownership sentinel.
#
# Four stdlib-only, hermetically-testable primitives consumed by Phase 2's
# reworked ``ensure_runtime`` M4 state machine:
#   spawn_detached          — one cross-platform wrapper that spawns a child
#                             detached from the parent (and any subagent)
#                             process tree (SPEC M2 / LD6).
#   kernel_start_time       — temporal-identity extraction, the PID-reuse
#                             defense (SPEC M1 / LD6).
#   write/read_runtime_lock — atomic `.runtime.lock.json` persistence (LD1).
#   verify_runtime_ownership — the verifiability predicate (LD1) — "200 on
#                             /health" is NOT proof of ownership.
#
# Every external interaction is an injected callable (``spawn`` / ``platform``
# / ``which`` / ``kernel_start_time_fn`` / ``replace``) so ``--test`` is
# hermetic without a real cross-platform host — mirroring how ``ensure_runtime``
# injects ``probe``/``restart``/``stale_check``.
# ===========================================================================

# Windows process-creation flags (SPEC M2 / LD6). The breakaway flag escapes a
# parent Job Object's KILL_ON_JOB_CLOSE reaping; the OSError fallback drops it
# when the parent Job forbids breakaway (ERROR_ACCESS_DENIED).
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# FILETIME epoch offset: 100ns intervals between 1601-01-01 and 1970-01-01.
_FILETIME_EPOCH_OFFSET = 116444736000000000
_FILETIME_TICKS_PER_SEC = 10_000_000


def spawn_detached(
    cmd,
    *,
    cwd,
    spawn=None,
    platform=None,
    which=None,
    kernel_start_time_fn=None,
):
    """Spawn ``cmd`` as a child detached from the parent (and any subagent)
    process tree; return ``{"pid": int, "start_time": float | None}``.

    The one cross-platform spawn primitive (SPEC M2 / LD6). It escapes the two
    process-tree-teardown reaping mechanisms a feature-cycle subagent boundary
    triggers:

      - **Windows** — Job Objects with ``KILL_ON_JOB_CLOSE``. The first spawn
        carries ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP |
        CREATE_BREAKAWAY_FROM_JOB``; if the parent Job forbids breakaway the
        OS raises ``OSError`` (``ERROR_ACCESS_DENIED``) and we retry WITHOUT
        the breakaway flag (plain ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP``).
      - **POSIX/WSL** — the WSL utility-VM idle suspend. ``start_new_session=True``
        always; on WSL the command is wrapped in
        ``systemd-run --user --scope --quiet --same-dir`` (bypasses
        ``instanceIdleTimeout``/``vmIdleTimeout``) when ``systemd-run`` is on
        PATH, else a ``setsid`` + ``nohup … sleep infinity`` keep-alive fallback.

    ``PR_SET_PDEATHSIG`` is DELIBERATELY NOT USED — it would kill the child WITH
    the parent, the exact opposite of the requirement.

    Determinism / injection (keeps ``--test`` hermetic):
      - ``spawn`` — callable(cmd, **kwargs) -> object with a ``.pid``. Default:
        ``subprocess.Popen``.
      - ``platform`` — OS sniff override (``sys.platform`` value). Default:
        ``sys.platform``.
      - ``which`` — callable(name) -> path|None (PATH lookup). Default:
        ``shutil.which``.
      - ``kernel_start_time_fn`` — callable(pid, *, platform) -> float|None,
        used to fill ``start_time`` from the live child PID (WU-2). Default:
        None → ``start_time`` is None (WU-1 is independently testable; Phase 2
        binds the real extractor).
    """
    if spawn is None:
        spawn = subprocess.Popen  # noqa: S603 — repo-config command, not user input
    if platform is None:
        platform = sys.platform
    if which is None:
        import shutil
        which = shutil.which

    is_windows = str(platform).startswith("win")

    if is_windows:
        # Try the breakaway flag first; fall back without it on a Job-Object
        # ERROR_ACCESS_DENIED (the parent Job forbids breakaway).
        breakaway = (
            _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_BREAKAWAY_FROM_JOB
        )
        try:
            proc = spawn(cmd, cwd=str(cwd), creationflags=breakaway)
        except OSError:
            plain = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
            proc = spawn(cmd, cwd=str(cwd), creationflags=plain)
    else:
        # POSIX/WSL — wrap the command so the child outlives both the subagent
        # turn and (on WSL) the utility-VM idle suspend.
        launch = list(cmd)
        if which("systemd-run"):
            launch = [
                "systemd-run", "--user", "--scope", "--quiet", "--same-dir",
            ] + launch
        elif which("setsid"):
            # setsid detaches into a new session; nohup + a keep-alive guards
            # the WSL idle-suspend race when systemd-run is unavailable.
            launch = ["setsid", "nohup"] + launch
        proc = spawn(launch, cwd=str(cwd), start_new_session=True)

    pid = proc.pid
    start_time = None
    if kernel_start_time_fn is not None:
        try:
            start_time = kernel_start_time_fn(pid, platform=platform)
        except Exception:  # noqa: BLE001 — best-effort; start_time stays None
            start_time = None
    return {"pid": pid, "start_time": start_time}


def run_transient_build(
    cmd,
    *,
    cwd,
    spawn=None,
    wait=None,
    platform=None,
    which=None,
    kernel_start_time_fn=None,
):
    """Run a TRANSIENT long build under the M3.2 Transient Build contract; return
    ``{"exit_code": int, "stdout": str, "pid": int, "start_time": float | None}``.

    One of LD5's two supervisory contracts over the single ``spawn_detached``
    primitive. The build is spawned **detached** ONLY to survive a feature-cycle
    subagent boundary's process-tree reaping — but unlike the Persistent Service
    contract (``ensure_runtime``), this contract:

      - **synchronously AWAITS** the build's conclusion (gathering stdout for
        telemetry), then returns the exit code, and
      - does **NOT** write ``.runtime.lock.json`` and does **NOT** leave the
        process behind for a later cycle to re-attach to.

    Atomic Artifact Promotion (Phase 4 / M5 Detect) is composed AROUND this — it
    is deliberately kept OUT of ``run_transient_build`` itself, so this function
    stays a pure spawn-detached-and-await primitive.

    Determinism / injection (keeps ``--test`` hermetic):
      - ``spawn`` / ``platform`` / ``which`` / ``kernel_start_time_fn`` — passed
        straight through to ``spawn_detached`` (see its docstring).
      - ``wait`` — callable(proc) -> ``(exit_code: int, stdout: str)``. Awaits the
        spawned process and returns its result. Default: a real awaiter that
        ``proc.communicate()``-style waits and reads captured stdout.
    """
    spawned = spawn_detached(
        cmd,
        cwd=cwd,
        spawn=spawn,
        platform=platform,
        which=which,
        kernel_start_time_fn=kernel_start_time_fn,
    )

    if wait is None:
        wait = _default_build_wait

    # NOTE: spawn_detached returns {"pid", "start_time"} (NOT the Popen handle),
    # so the default awaiter re-attaches by PID. Tests ALWAYS inject ``wait``
    # (hermetic), so the default path is exercised only in production where a
    # real awaiter is supplied by the caller's config; we pass the spawn result
    # dict through so an injected awaiter can use the pid.
    exit_code, stdout = wait(spawned)

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "pid": spawned.get("pid"),
        "start_time": spawned.get("start_time"),
    }


def _default_build_wait(spawned):
    """Default production awaiter for ``run_transient_build``: block on the
    detached child by PID and return ``(exit_code, stdout)``.

    Tests inject ``wait`` so this is exercised only in production. spawn_detached
    returns a ``{pid, start_time}`` dict (not the Popen handle, which would be
    torn down with the orchestrator turn if held), so the default awaiter polls
    the PID via ``os.waitpid`` where the child is a direct child, falling back to
    a best-effort liveness poll otherwise. stdout capture in the no-handle case is
    best-effort; production callers that need full stdout telemetry inject a
    ``wait`` that owns the pipe.
    """
    pid = spawned.get("pid")
    if pid is None:
        return (None, "")
    try:
        _, status = os.waitpid(int(pid), 0)
        # POSIX exit-status decode; on Windows os.waitpid returns the exit code
        # shifted, so normalize via os.waitstatus_to_exitcode when available.
        if hasattr(os, "waitstatus_to_exitcode"):
            return (os.waitstatus_to_exitcode(status), "")
        return (status, "")
    except (ChildProcessError, OSError, ValueError):
        # Not a direct child (detached) or already reaped — best-effort poll.
        return (None, "")


def promote_artifact_atomically(
    staging_dir,
    final_dir,
    *,
    exit_code,
    replace=None,
):
    """Atomically promote a staging build artifact into its production path —
    ONLY on a clean build exit. Returns ``{"promoted": bool, "reason": str}``.

    The detect-half of LD4 (SPEC M5 Detect / Atomic Artifact Promotion). It is
    deliberately composed AROUND ``run_transient_build`` (NOT folded inside it),
    so the build target writes into ``staging_dir`` and this function swaps it
    into ``final_dir`` in a SINGLE atomic ``os.replace`` rename — atomic on NTFS
    (``MoveFileEx``) and POSIX (``rename``) — but ONLY when ``exit_code == 0``.

    A non-zero ``exit_code`` (a failed or torn-mid-flight build) is the
    load-bearing safety case: ``replace`` is NEVER called, so the production
    artifact at ``final_dir`` is left byte-for-byte untouched and the partial
    output stays quarantined in ``staging_dir``. A torn build is therefore
    mathematically harmless to production.

    Atomicity contract: promotion is a single ``os.replace`` (rename), never a
    copy-then-delete. Tests inject ``replace`` and assert it is the only mutation
    + called staging→final exactly once.

    Args:
        staging_dir: path the build wrote into (``target/release_staging``).
        final_dir: the production artifact path (``target/release``).
        exit_code: the build's exit code. Promotion happens iff this is 0.
        replace: injectable ``callable(src, dst)`` performing the atomic rename
            (default: ``os.replace``). Hermetic tests inject a spy.

    Returns:
        ``{"promoted": True}`` on a clean-exit promotion, or
        ``{"promoted": False, "reason": <str>}`` when promotion was withheld
        (non-zero exit) or the rename failed (best-effort — a rename error never
        raises; it returns ``promoted: False`` with the error reason).
    """
    if replace is None:
        replace = os.replace

    if exit_code != 0:
        return {
            "promoted": False,
            "reason": (
                f"build exit_code={exit_code} (non-zero) — production artifact "
                "left untouched, partial output quarantined in staging"
            ),
        }

    try:
        replace(staging_dir, final_dir)
    except OSError as exc:  # noqa: BLE001
        # A rename failure must not crash the promotion caller — report it as a
        # non-promotion so the production artifact is treated as unchanged.
        return {
            "promoted": False,
            "reason": f"atomic replace failed: {exc!r}",
        }
    return {"promoted": True}


def reconcile_cycle_begin_git_consistency(
    repo_root,
    *,
    boot_stamp,
    staging_dir=None,
    lock_mtime=None,
    remove=None,
    git_clean=None,
):
    """At --cycle-begin, neutralize a torn-build uncommitted delta left by a
    PREVIOUS torn cycle: a pre-boot ``.git/index.lock`` ⇒ remove it and
    ``git clean -fdx`` the staging dir. Returns a reconciliation record.

    The git-consistency detect-half of LD4 (SPEC M5 Detect). The discriminator
    is the lock's modification time vs ``boot_stamp`` (the orchestrator/run-marker
    boot epoch): a lock OLDER than the boot stamp was left by a torn op that ran
    BEFORE this run booted, so it is safe to clear; a lock NEWER than the boot
    stamp is a LIVE in-flight git op of the current run and is PRESERVED (never
    clobber a live lock).

    Best-effort + FAIL-OPEN (consistent with lazy-cycle-containment): a non-git
    tree, no lock, an unreadable mtime, or a git/remove error all degrade to a
    no-op and NEVER raise — the --cycle-begin marker write must always proceed.

    Crucially this COMPOSES with the --cycle-end friction detector rather than
    duplicating it: it makes NO commits and never touches the run marker, so HEAD
    and the run identity are unchanged. detect_cycle_bracket_friction therefore
    sees zero advanced commits and an intact run identity — a reconciled delta
    cannot false-trip ``unexpected-commits`` / ``cycle-bracket-break``.

    Args:
        repo_root: the repo whose ``.git/index.lock`` is examined.
        boot_stamp: the orchestrator/run boot epoch float (e.g. the run marker's
            ``started_at`` parsed to epoch). A lock with mtime < this is stale.
            None disables the staleness comparison → no removal (fail-safe: a
            missing boot stamp must not clobber any lock).
        staging_dir: the build staging dir to ``git clean -fdx`` when a stale lock
            is reconciled. None → skip the clean (lock removal still happens).
        lock_mtime: injectable lock mtime epoch float (hermetic tests / overriding
            the on-disk stat). None → stat the lock file.
        remove: injectable ``callable(path)`` removing the lock (default os.remove).
        git_clean: injectable ``callable(repo_root, staging_dir) -> bool`` running
            the staging clean (default: a real ``git clean -fdx <staging>``).

    Returns:
        ``{"reconciled": bool, "removed_lock": bool, "staging_cleaned": bool,
        "reason": str}``. ``reconciled`` is True iff a stale lock was removed.
    """
    result = {
        "reconciled": False,
        "removed_lock": False,
        "staging_cleaned": False,
        "reason": "",
    }
    try:
        root = Path(repo_root)
        git_dir = root / ".git"
        # Non-git tree (no .git dir/file) → fail-open no-op.
        if not git_dir.exists():
            result["reason"] = "not a git tree — no-op"
            return result

        lock_path = git_dir / "index.lock"
        if not lock_path.exists():
            result["reason"] = "no index.lock — no-op"
            return result

        # Resolve the lock's mtime (injectable for hermetic tests).
        if lock_mtime is None:
            try:
                lock_mtime = lock_path.stat().st_mtime
            except OSError as exc:
                result["reason"] = f"could not stat index.lock: {exc!r} — no-op"
                return result

        # A missing boot stamp must NOT clobber a lock (fail-safe).
        if boot_stamp is None:
            result["reason"] = "no boot stamp — lock preserved"
            return result

        # Fresh/own lock (mtime >= boot stamp) → a live git op; PRESERVE it.
        if lock_mtime >= boot_stamp:
            result["reason"] = (
                f"fresh lock (mtime={lock_mtime} >= boot_stamp={boot_stamp}) — "
                "live git op, preserved"
            )
            return result

        # Stale pre-boot lock → remove it.
        if remove is None:
            remove = os.remove
        try:
            remove(str(lock_path))
            result["removed_lock"] = True
            result["reconciled"] = True
        except OSError as exc:
            result["reason"] = f"stale lock removal failed: {exc!r} — no-op"
            return result

        # git clean -fdx the staging dir (best-effort).
        if staging_dir is not None:
            if git_clean is None:
                git_clean = _default_git_clean_staging
            try:
                cleaned = git_clean(root, staging_dir)
                result["staging_cleaned"] = bool(cleaned)
            except Exception as exc:  # noqa: BLE001
                # Lock removal already succeeded; a clean failure is non-fatal.
                result["reason"] = (
                    f"stale lock removed; staging clean failed: {exc!r}"
                )
                return result

        result["reason"] = "stale pre-boot index.lock reconciled"
        return result
    except Exception as exc:  # noqa: BLE001
        # FAIL-OPEN: any unexpected error degrades to a no-op record.
        result["reason"] = f"reconciliation error (fail-open): {exc!r}"
        return result


def _default_git_clean_staging(repo_root: Path, staging_dir: str) -> bool:
    """Default production staging cleaner: ``git clean -fdx <staging_dir>``.

    Best-effort — returns True on a clean exit, False otherwise; never raises
    (the caller wraps it, but keep this defensive too)."""
    try:
        proc = _git(repo_root, "clean", "-fdx", str(staging_dir))
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def kernel_start_time(
    pid,
    *,
    platform=None,
    read_stat=None,
    get_process_times=None,
    boot_time=None,
    clk_tck=None,
):
    """Return the kernel-reported absolute start time of ``pid`` as a Unix epoch
    float, or ``None`` on any error (best-effort, NEVER raises).

    The temporal-identity half of LD1 — the PID-reuse defense. A reused PID held
    by a foreign process reports a DIFFERENT start_time, so ``verify_runtime_ownership``
    can reject it. ``None`` flows cleanly into Phase 2's DEAD/HIJACKED classification.

    Extraction (stdlib-only, SPEC M1 / LD6):
      - **Windows** — ``ctypes`` → ``kernel32.GetProcessTimes`` returns a
        creation FILETIME (100ns intervals since 1601-01-01); converted to a
        Unix epoch float.
      - **POSIX/WSL** — ``/proc/[pid]/stat`` field 22 (``starttime``, in clock
        ticks since boot) → epoch via ``boot_time + ticks / SC_CLK_TCK``.

    Injection (hermetic ``--test``):
      - ``read_stat`` — callable(pid) -> the raw ``/proc/[pid]/stat`` line.
      - ``get_process_times`` — callable(pid) -> creation FILETIME int.
      - ``boot_time`` / ``clk_tck`` — POSIX constants (default: read live).
    """
    if platform is None:
        platform = sys.platform
    is_windows = str(platform).startswith("win")

    try:
        if is_windows:
            if get_process_times is None:
                get_process_times = _win_process_creation_filetime
            filetime = get_process_times(pid)
            if filetime is None:
                return None
            return (filetime - _FILETIME_EPOCH_OFFSET) / _FILETIME_TICKS_PER_SEC

        # POSIX/WSL: /proc/[pid]/stat field 22 (starttime, clock ticks).
        if read_stat is None:
            def read_stat(p):
                return Path(f"/proc/{p}/stat").read_text(encoding="utf-8", errors="replace")
        if clk_tck is None:
            clk_tck = os.sysconf("SC_CLK_TCK")
        if boot_time is None:
            boot_time = _posix_boot_time()
        if boot_time is None or not clk_tck:
            return None

        raw = read_stat(pid)
        # Field 2 (comm) may contain spaces/parens; it is wrapped in (...).
        # Split off everything through the LAST ')' so the remaining fields are
        # whitespace-delimitable. Field 22 (starttime) is index 19 of the tail
        # (tail starts at field 3 = state).
        rparen = raw.rfind(")")
        if rparen < 0:
            return None
        tail = raw[rparen + 1:].split()
        # tail[0] is field 3 (state); field 22 is tail index 19.
        if len(tail) < 20:
            return None
        ticks = int(tail[19])
        return boot_time + (ticks / clk_tck)
    except Exception:  # noqa: BLE001 — best-effort, never raises
        return None


def _win_process_creation_filetime(pid):
    """Default Windows creation-FILETIME extractor via ctypes →
    kernel32.GetProcessTimes. Returns the creation FILETIME int, or None on any
    error. Only invoked when ``kernel_start_time`` is called WITHOUT an injected
    ``get_process_times`` (production); tests inject."""
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_t = wintypes.FILETIME()
            kernel_t = wintypes.FILETIME()
            user_t = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_t),
                ctypes.byref(kernel_t), ctypes.byref(user_t),
            )
            if not ok:
                return None
            return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return None


def _posix_boot_time():
    """Read system boot time (Unix epoch sec) from /proc/stat ``btime``.
    Returns None on any error."""
    try:
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except Exception:  # noqa: BLE001
        return None
    return None


def _runtime_lock_path(repo_root, config=None):
    """Resolve the `.runtime.lock.json` path at the repo root from the config
    dict's ``lock_filename`` (parameterized, NOT a hard-coded literal)."""
    cfg = dict(_ENSURE_RUNTIME_DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    return Path(repo_root) / cfg["lock_filename"]


def write_runtime_lock(
    repo_root,
    *,
    pid,
    start_time,
    port,
    artifact_hash,
    controller_session_id,
    config=None,
):
    """Atomically write the `.runtime.lock.json` ownership sentinel (LD1) at the
    repo root with the five LD1 fields.

    Uses the shared ``_atomic_write`` (temp file in the same dir + ``os.replace``)
    so a mid-write failure never leaves a partial production sentinel — the same
    atomic-write discipline as the cycle marker / tally writers already in tree.
    The lock filename comes from ``config['lock_filename']`` (default config),
    never a literal in the flow.
    """
    lock = {
        "controller_session_id": controller_session_id,
        "pid": pid,
        "start_time": start_time,
        "port": port,
        "artifact_hash": artifact_hash,
    }
    path = _runtime_lock_path(repo_root, config)
    _atomic_write(path, json.dumps(lock, indent=2) + "\n")


def read_runtime_lock(repo_root, *, config=None):
    """Best-effort read of the `.runtime.lock.json` sentinel → dict, or ``None``
    on missing/corrupt (NEVER raises)."""
    path = _runtime_lock_path(repo_root, config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Boot-spawn stamp (ensure-runtime-recovery-starves-cold-compile-round-2). A tiny
# per-repo sidecar to `.runtime.lock.json` recording WHEN the last `dev:restart`
# boot was spawned. It is the persistence behind the `_BOOT_SPAWN_GRACE_SECONDS`
# time-window grace: the production `boot_alive()` reads it to answer "is a cold
# boot in progress?" ROBUSTLY — independent of the short-lived npm/cmd wrapper
# `Popen` handle whose `.poll()` exits early on Windows (the Round-32 false-green).
#
# Why a FILE (not just an in-process holder): the murder site is the bounded
# `_recover_runtime` loop INSIDE a SINGLE `ensure_runtime` call — its first
# `restart()` legitimately spawns the compile, and every SUBSEQUENT loop iteration
# must see "a boot is in progress" to STOP re-killing it. The stamp written by that
# first `restart()` is read back by `boot_alive()` later in the SAME call (and by a
# follow-up `--ensure-runtime` invocation), so the grace survives both the wrapper
# exiting AND the process boundary between orchestrator calls.
# ---------------------------------------------------------------------------

_BOOT_STAMP_FILENAME = ".runtime.boot.json"


def _boot_stamp_path(repo_root) -> Path:
    """Resolve the boot-spawn stamp path at the repo root (sibling of the runtime
    lock). A fixed filename — the stamp is repo-scoped, never port-/config-scoped."""
    return Path(repo_root) / _BOOT_STAMP_FILENAME


def write_boot_stamp(repo_root, *, spawn_ts: float) -> None:
    """Atomically record the boot-spawn epoch (best-effort, never raises). Written
    by the production `restart()` closure the instant it spawns `dev:restart`."""
    try:
        _atomic_write(
            _boot_stamp_path(repo_root),
            json.dumps({"spawn_ts": float(spawn_ts)}, indent=2) + "\n",
        )
    except Exception:  # noqa: BLE001 — a stamp-write failure must never abort a boot
        pass


def read_boot_stamp(repo_root) -> float | None:
    """Best-effort read of the boot-spawn epoch → float, or ``None`` on
    missing/corrupt (NEVER raises)."""
    try:
        data = json.loads(_boot_stamp_path(repo_root).read_text(encoding="utf-8"))
        ts = data.get("spawn_ts") if isinstance(data, dict) else None
        return float(ts) if ts is not None else None
    except (OSError, ValueError, TypeError):
        return None


def boot_recently_spawned(
    repo_root, *, now: float | None = None,
    grace_seconds: float = _BOOT_SPAWN_GRACE_SECONDS,
) -> bool:
    """True iff a `dev:restart` boot was spawned within ``grace_seconds`` of ``now``
    (the time-window grace). The Windows-robust cold-boot-in-progress detector: a
    fresh stamp means a compile is genuinely underway regardless of whether the
    short-lived npm/cmd wrapper `Popen` has already exited. Ages out past the
    cold-compile ceiling so a stuck/dead host is never patient-waited forever."""
    stamp = read_boot_stamp(repo_root)
    if stamp is None:
        return False
    current = time.time() if now is None else now
    return (current - stamp) < grace_seconds


def verify_runtime_ownership(lock, *, live_session_id, kernel_start_time_fn):
    """Return ``True`` iff the recorded runtime is provably owned by the live
    controller (LD1) — the verifiability predicate.

    ``True`` iff BOTH:
      - the recorded ``start_time`` matches the kernel-reported start_time for
        ``lock['pid']`` (defeats PID reuse — a foreign process holding a reused
        PID reports a different start_time, and a dead PID reports ``None``), AND
      - ``lock['controller_session_id'] == live_session_id`` (defeats a previous
        crashed controller's leftover runtime).

    "200 on /health" is NOT proof of ownership — only this ``(start_time,
    controller_session_id)`` match is. ``kernel_start_time_fn`` is injected
    (callable(pid, *, platform) -> float|None) so the predicate is hermetic.
    """
    if not isinstance(lock, dict):
        return False
    if lock.get("controller_session_id") != live_session_id:
        return False
    recorded = lock.get("start_time")
    if recorded is None:
        return False
    try:
        live = kernel_start_time_fn(lock.get("pid"))
    except TypeError:
        # Tolerate a fn that requires the keyword (production binds platform).
        live = kernel_start_time_fn(lock.get("pid"), platform=sys.platform)
    except Exception:  # noqa: BLE001 — best-effort
        return False
    if live is None:
        return False
    return live == recorded


# lazy-core-package-decomposition Phase 5 WU-3 (residue sweep): the git helpers
# (_git / _current_head / git_head_short_sha / git_guard_status) and the
# self-edit detection plane (GOVERNING_FILE_SET / self_edit_mode /
# governing_files_touched) moved here from _monolith.py — verbatim.

# ---------------------------------------------------------------------------
# Persisted probe signature / loop detection — WU-4
# ---------------------------------------------------------------------------

def _current_head(repo_root: Path) -> str | None:
    """Resolve repo_root's HEAD commit sha, or None when repo_root is not a git
    repo / git is unavailable.

    Best-effort and never raises: a missing git binary, a non-repo path, or any
    subprocess error all map to None. update_repeat_count uses this for the
    Phase 9 WU-2 HEAD-aware streak — None on both sides (e.g. a non-git
    repo_root) preserves the pre-Phase-9 same-tuple-increments behavior.

    This mirrors lazy-state.py's own _current_head (which lazy-state keeps for
    its Step-9 MCP-results freshness gate); the duplication is deliberate — the
    two scripts are independently importable and lazy_core must not depend on a
    sibling script. Both share the same best-effort contract.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# ---------------------------------------------------------------------------
# WU-5: Single-probe payload helpers
# ---------------------------------------------------------------------------

def _git(repo_root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a git command against repo_root, capturing output. Never raises on
    non-zero exit (callers check .returncode); raises only on OS-level failure,
    which callers wrap."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def git_head_short_sha(repo_root: Path) -> str | None:
    """Return the short SHA of ``git rev-parse --short HEAD`` for ``repo_root``,
    or ``None`` on any failure (non-git tree, OS error, non-zero exit).

    Fail-open by design (feature-budget-guard-and-skip-ahead Phase 2): the budget
    guard's ``budget_guard.commit_hash`` audit field is best-effort context, never
    a gate — a degraded snapshot must not break trip evaluation.
    """
    try:
        proc = _git(repo_root, "rev-parse", "--short", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None

def git_guard_status(repo_root: Path) -> dict:
    """Return a three-key git status snapshot for the probe payload.

    Runs three lightweight git commands against ``repo_root`` and returns a
    dict with the following keys:

    ``clean_tree`` (bool)
        True when ``git status --short`` produces no output (no staged,
        unstaged, or untracked changes).

    ``head_matches_origin`` (bool)
        True when ``git rev-parse HEAD`` equals ``git rev-parse @{u}``.
        False when the repo has no upstream configured or any git command
        fails.

    ``unpushed`` (bool)
        True when ``git rev-list --count @{u}..HEAD`` returns an integer > 0
        (local commits are ahead of the upstream tracking ref).  False on any
        git failure or when no upstream is configured.

    Error-handling contract (best-effort, mirrors verify_ledger / _current_head):
    - Each of the three checks is independent; a failure in one does not
      prevent the others from running.
    - Any ``OSError`` or ``subprocess.SubprocessError`` (including timeout)
      silently produces the safe-default value for that check.
    - When ``@{u}`` does not resolve (no upstream), both ``head_matches_origin``
      and ``unpushed`` are False; ``clean_tree`` still reflects the status
      command result if it succeeded.
    """
    # --- check 1: clean working tree -----------------------------------------
    # Mirror the subprocess style used in verify_ledger: capture_output + text
    # + explicit timeout + catch OSError/SubprocessError.
    try:
        status_result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Require a zero returncode in addition to empty stdout.  When
        # repo_root is not a git repo, `git status --short` exits 128 with
        # empty stdout — without the returncode guard that would produce a
        # false-positive clean_tree=True (contradicting the docstring contract
        # that an invalid repo → safe-dirty False, matching checks 2 and 3).
        clean_tree = (status_result.returncode == 0 and status_result.stdout.strip() == "")
    except (OSError, subprocess.SubprocessError):
        # Git unavailable or repo_root invalid — assume dirty so callers don't
        # proceed with a false-positive clean signal.
        clean_tree = False

    # --- check 2: HEAD matches upstream tracking ref -------------------------
    # Both rev-parse commands must succeed and return identical SHA strings.
    # @{u} fails with a non-zero returncode when no upstream is configured.
    try:
        head_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        upstream_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if head_result.returncode == 0 and upstream_result.returncode == 0:
            head_sha = head_result.stdout.strip()
            upstream_sha = upstream_result.stdout.strip()
            # Require both SHAs to be non-empty before comparing.
            head_matches_origin = bool(head_sha and upstream_sha and head_sha == upstream_sha)
        else:
            # @{u} can fail when no upstream is configured; treat as mismatch.
            head_matches_origin = False
    except (OSError, subprocess.SubprocessError):
        head_matches_origin = False

    # --- check 3: unpushed local commits -------------------------------------
    # rev-list --count @{u}..HEAD returns the number of commits ahead of the
    # upstream.  A non-zero integer means at least one local commit is unpushed.
    try:
        revlist_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", "@{u}..HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if revlist_result.returncode == 0:
            unpushed = int(revlist_result.stdout.strip()) > 0
        else:
            # No upstream or other git error — cannot determine ahead-count.
            unpushed = False
    except (OSError, subprocess.SubprocessError, ValueError):
        # ValueError covers int() failing on unexpected output.
        unpushed = False

    return {
        "clean_tree": clean_tree,
        "head_matches_origin": head_matches_origin,
        "unpushed": unpushed,
    }


# ---------------------------------------------------------------------------
# Phase 1 (lazy-cycle-containment, C8) — Self-edit reload discipline.
#
# When a /lazy-batch run executes *inside* claude-config it is editing the very
# harness it runs from. Most of that harness self-refreshes mid-run and needs NO
# reload — the AUTO-REFRESH BOUNDARY below. The ONLY surfaces that go stale are
# the orchestrator's own in-context governing prose: GOVERNING_FILE_SET.
#
# AUTO-REFRESH BOUNDARY (documented no-ops — MUST NOT be flagged for reload;
# they were never stale):
#   * lazy_core.py / lazy-state.py / bug-state.py — a fresh `python3` subprocess
#     runs on every probe, so an edit is live on the next probe.
#   * lazy-batch-prompts/cycle-base-prompt.md (+ addenda + loop-block.md) —
#     re-read by emit_cycle_prompt() from disk on every probe.
#   * hook .sh bodies — `bash ~/.claude/hooks/X.sh` reads the file each
#     invocation, so a body edit is live on the next tool call.
#   * downstream skill prose (SKILL.md a dispatched subagent loads) — each
#     dispatched subagent loads its skill fresh, so the edit is live next dispatch.
# These are EXCLUDED from GOVERNING_FILE_SET by construction.
#
# The governing-file set MUST stay in lockstep with the orchestrator's
# compaction re-read list (lazy-dispatch-template.md + orchestrator-voice.md +
# completeness-policy.md + the orchestrator's own SKILL.md) — the self-edit
# reload is the SAME re-read, triggered by a self-edit commit instead of a
# compaction boundary. Paths are repo-root-relative POSIX strings (the form
# `git diff --name-only` emits).
# ---------------------------------------------------------------------------
GOVERNING_FILE_SET: frozenset[str] = frozenset({
    # Orchestrator SKILLs the running orchestrator holds in-context (coupled trio).
    "user/skills/lazy-batch/SKILL.md",
    "user/skills/lazy-bug-batch/SKILL.md",
    "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
    # Components the orchestrator holds in-context (the compaction re-read list).
    "user/skills/_components/orchestrator-voice.md",
    "user/skills/_components/completeness-policy.md",
    "user/skills/_components/lazy-dispatch-template.md",
})


def self_edit_mode(repo_root: "str | Path") -> bool:
    """True iff this run is editing the harness it executes from.

    Returns True when ``~/.claude/skills``, ``~/.claude/scripts``, AND
    ``~/.claude/hooks`` ALL resolve (after ``os.path.realpath`` symlink
    resolution) to a path UNDER the run's ``git rev-parse --show-toplevel``.

    This is the semantically-correct predicate — robust to the repo being cloned
    to any path (it compares resolved real paths, NOT a brittle cwd-basename
    match). ``~`` is resolved via ``os.path.expanduser``.

    Returns False (never raises) when:
      * ``repo_root`` is not a git repo (``--show-toplevel`` fails);
      * any of the three ``~/.claude/*`` paths is missing or resolves OUTSIDE
        the toplevel;
      * any OS/subprocess error occurs.
    """
    # Resolve the run's git toplevel; non-git repo or any git failure → False.
    try:
        proc = _git(Path(repo_root), "rev-parse", "--show-toplevel", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    toplevel_raw = proc.stdout.strip()
    if not toplevel_raw:
        return False
    toplevel = os.path.realpath(toplevel_raw)

    for name in ("skills", "scripts", "hooks"):
        candidate = os.path.join(os.path.expanduser("~"), ".claude", name)
        if not os.path.exists(candidate):
            return False
        resolved = os.path.realpath(candidate)
        # Membership test on the resolved real paths: resolved must be the
        # toplevel itself or a descendant of it.
        try:
            common = os.path.commonpath([toplevel, resolved])
        except ValueError:
            # Different drives (Windows) or otherwise incomparable → not under.
            return False
        if common != toplevel:
            return False
    return True


def governing_files_touched(repo_root: "str | Path") -> list[str]:
    """Return the GOVERNING_FILE_SET members touched by the last commit.

    Intersects the last commit's changed files (``git diff --name-only HEAD~1
    HEAD``; falls back to the root-commit file list when there is no parent)
    with GOVERNING_FILE_SET. Auto-refresh surfaces never appear (they are not in
    the set). Best-effort: any git failure returns ``[]`` (the orchestrator's
    reload check then simply finds nothing to reload).
    """
    try:
        proc = _git(repo_root if isinstance(repo_root, Path) else Path(repo_root),
                    "diff", "--name-only", "HEAD~1", "HEAD", timeout=30)
        if proc.returncode != 0:
            # No parent commit (root commit): list the commit's own files.
            proc = _git(repo_root if isinstance(repo_root, Path) else Path(repo_root),
                        "show", "--name-only", "--pretty=format:", "HEAD",
                        timeout=30)
            if proc.returncode != 0:
                return []
    except (OSError, subprocess.SubprocessError):
        return []
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return sorted(changed & GOVERNING_FILE_SET)
