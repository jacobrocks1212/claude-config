#!/usr/bin/env python3
"""
lazy_inject.py — UserPromptSubmit / SessionStart / PostCompact inject helper.

Called by lazy-route-inject.sh when a run marker is present.  Reads the
Claude Code hook-input JSON from stdin and emits a hookSpecificOutput JSON
block with additionalContext containing:
  - The LAZY-ROUTE banner
  - The result of the full probe invocation (--repeat-count --probe --emit-prompt)
  - The most recent nonce from the registry (if available)
  - For SessionStart(compact) / PostCompact events: the post-compaction
    re-entry protocol and marker counters (SPEC inject item 3)
  - If a hook-error.json breadcrumb exists: its contents surfaced as
    "HOOK_ERROR: <contents>" (self-announcing guard breakage)

An UNBOUND marker (session_id=None, bind-pending) yields a SILENT no-op:
no banner, no probe, no registration, no counter advance, no marker mutation.
Phase 9 WU-9.1 moved session binding OUT of inject entirely — the guard binds
on its first ALLOW (lazy_guard.py), an anchor bystander sessions cannot forge.

Exit code: always 0.  Internal errors write hook-error.json and exit 0
(fail-open semantics, same as lazy_guard.py).
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    import lazy_core  # type: ignore[import]
except ImportError:
    sys.exit(0)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HOOK_NAME = "lazy-route-inject"


# ---------------------------------------------------------------------------
# Breadcrumb helpers (mirrors lazy_guard.py)
# ---------------------------------------------------------------------------

def _write_breadcrumb(error_msg: str) -> None:
    """Write a hook-error.json breadcrumb into the state dir (best-effort)."""
    try:
        state_dir = lazy_core.claude_state_dir(create=True)
        breadcrumb = {
            "hook": _HOOK_NAME,
            "error": error_msg,
            "at": datetime.datetime.now(tz=datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        crumb_path = state_dir / "hook-error.json"
        crumb_path.write_text(json.dumps(breadcrumb, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _read_and_clear_breadcrumb() -> str | None:
    """Read hook-error.json if present, delete it, and return its raw text.

    Returns None when the file is absent.  Deletes the breadcrumb after
    reading so it is only surfaced once (the next inject turn will not see it
    again unless a new error occurs).
    """
    try:
        state_dir = lazy_core.claude_state_dir(create=False)
        crumb_path = state_dir / "hook-error.json"
        if not crumb_path.exists():
            return None
        content = crumb_path.read_text(encoding="utf-8")
        try:
            crumb_path.unlink()
        except OSError:
            pass
        return content
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Probe runner
# ---------------------------------------------------------------------------

def _merged_head_type(repo_root: str) -> str | None:
    """Return the MERGED work-list head's type (``"bug"`` / ``"feature"``) or
    ``None`` when it cannot be resolved.

    dispatch-probe-and-inject-bypass-merged-head: the injected banner must
    reflect the MERGED head (what the unified driver's ``--next-merged``
    type-dispatch would produce), NOT the marker's sticky ``pipeline`` field.
    Shell the canonical ``lazy-state.py --next-merged`` surface (read-only
    ordering; it never re-infers per-item state or advances any counter) and
    return its ``type``. Best-effort: any failure returns ``None`` so the caller
    FAILS OPEN to the marker pipeline (a broken merged probe must never disable
    injection or crash the hook).
    """
    if not repo_root:
        return None
    script_path = _SCRIPTS_DIR / "lazy-state.py"
    if not script_path.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(script_path),
             "--next-merged", "--repo-root", repo_root],
            capture_output=True, text=True, env=dict(os.environ), timeout=30,
        )
        stdout = (result.stdout or "").strip()
        if not stdout:
            return None
        head = json.loads(stdout)
        if isinstance(head, dict):
            htype = head.get("type")
            if htype in ("bug", "feature"):
                return htype
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return None


def _run_probe(marker: dict) -> dict | None:
    """Run the full probe form of the appropriate state script.

    Command: python <script> --repeat-count --probe --emit-prompt
             --repo-root <marker.repo_root> [--cloud]

    Returns the parsed JSON dict from the probe's stdout, or None on failure.
    The probe registers the emitted prompt (nonce + hash) in the registry as a
    side effect — this is the production entry point, same as the orchestrator
    would call.
    """
    pipeline = marker.get("pipeline", "feature")
    repo_root = marker.get("repo_root", "")
    cloud = marker.get("cloud", False)

    # dispatch-probe-and-inject-bypass-merged-head: select the state script by
    # the MERGED work-list head's TYPE, not the marker's STICKY pipeline field.
    # The unified driver (lazy-batch/SKILL.md Step 1a) type-dispatches on the
    # --next-merged head each cycle; the marker's pipeline is a per-run constant
    # written once at --run-start, so a P0 bug that jumps the bug-queue head
    # mid-feature-run would otherwise keep injecting a stale `feature` banner
    # that the orchestrator consumes DIRECTLY (Step 1a "consume the banner, do
    # NOT re-probe") — silently skipping the bug. Route by the merged head's
    # type; FAIL OPEN to the marker pipeline when the merged probe can't resolve.
    _head_type = _merged_head_type(repo_root)
    effective_pipeline = _head_type if _head_type in ("bug", "feature") else pipeline

    # Select the correct state script based on the effective (merged-head) type.
    if effective_pipeline == "bug":
        script_name = "bug-state.py"
    else:
        script_name = "lazy-state.py"

    script_path = _SCRIPTS_DIR / script_name

    # Build the command list.
    python_exe = sys.executable
    cmd = [
        python_exe, str(script_path),
        "--repeat-count", "--probe", "--emit-prompt",
        "--repo-root", repo_root,
    ]
    if cloud:
        cmd.append("--cloud")

    # Inherit the environment including LAZY_STATE_DIR so the probe writes into
    # the same state dir as this hook.
    env = dict(os.environ)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        if result.returncode != 0:
            # Probe failed — return whatever stdout we got (may still be usable JSON).
            # Fall through to the JSON parse attempt below.
            pass
        stdout = result.stdout.strip()
        if not stdout:
            return None
        probe_data = json.loads(stdout)
        if isinstance(probe_data, dict):
            return probe_data
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Nonce resolver
# ---------------------------------------------------------------------------

def _latest_nonce() -> str | None:
    """Return the most recent unconsumed nonce from the registry, or None.

    This is the nonce that was just registered by the probe invocation.  We
    read the raw registry rather than re-hashing (the probe already registered
    the entry via register_emission_if_marked).
    """
    try:
        data = lazy_core._load_registry()  # type: ignore[attr-defined]
        entries = data.get("entries", [])
        # Entries are appended in order; the last unconsumed one is the newest.
        for entry in reversed(entries):
            if not entry.get("consumed", True):
                return entry.get("nonce")
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Turn counter
# ---------------------------------------------------------------------------

def _turn_n(marker: dict) -> int:
    """Return a monotone turn counter from the marker's forward+meta counters.

    The turn number is the sum of forward_cycles + meta_cycles + 1 (1-based,
    matching the post-advance counter semantics from Phase 1: after the probe
    increments the counter, the next turn is one higher).

    This is intentionally a simple sum — it is a labeling aid for retro graders,
    not a precise per-hook-invocation counter.  The comment in Phase 2 planning
    says "pick one, comment it."
    """
    forward = marker.get("forward_cycles", 0) or 0
    meta = marker.get("meta_cycles", 0) or 0
    return forward + meta + 1


# ---------------------------------------------------------------------------
# Live-settings split-brain advisory (Fix Scope 4 / D2)
# ---------------------------------------------------------------------------

def _load_doc_drift_module():
    """Load the sibling doc-drift-lint.py (hyphenated → importlib). Module-level
    seam so the advisory stays monkeypatchable in tests."""
    import importlib.util
    p = Path(__file__).parent / "doc-drift-lint.py"
    spec = importlib.util.spec_from_file_location("_doc_drift_for_live_advisory", str(p))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load doc-drift-lint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _live_settings_advisory(repo_root, live_path=None):
    """One advisory banner line when the live ~/.claude/settings.json has drifted
    from the tracked SSOT, else None. FAIL-OPEN: any error (helper unloadable /
    raises) returns None so the banner is NEVER broken (bug: live-settings
    split-brain, Fix Scope 4 / D2). O(1) — a cheap symlink+resolve stat; this
    fires every prompt-submit in a marked run."""
    try:
        ddl = _load_doc_drift_module()
        # live-settings-probe-false-positive-in-consumer-repo (Gap 2): resolve
        # the tracked settings SSOT against the claude-config checkout when the
        # marked run targets a consumer repo (no user/settings.json), so the
        # banner never false-fires 'settings drift' in AlgoBooth.
        ssot_root = ddl.settings_ssot_root(repo_root)
        ok, detail = ddl.live_settings_status(ssot_root, live_path=live_path)
        if ok:
            return None
        return f"⚠ live settings drift: {detail}"
    except Exception:  # noqa: BLE001 — fail-open, banner must never break
        return None


# ---------------------------------------------------------------------------
# Main inject logic
# ---------------------------------------------------------------------------

def inject(stdin_text: str) -> str | None:
    """Core inject logic.  Returns the JSON string to emit, or None for silence.

    Raises freely — caller wraps in try/except for fail-open handling.
    """
    # Parse the hook-input JSON to get the event name.
    hook_input = json.loads(stdin_text)
    hook_event_name = hook_input.get("hook_event_name", "UserPromptSubmit")
    session_id: str | None = hook_input.get("session_id") or None

    # Read the run marker — this is the primary gate.
    # Pass the hook-input session_id so staleness path B (session-id mismatch)
    # can fire in production. Phase 8 WU-8.1: path B is NON-DESTRUCTIVE — when a
    # concurrent NON-owner session (e.g. an interactive session running while a
    # marked /lazy-batch run is live) fires this hook, read_run_marker returns
    # None (this hook injects nothing, fast-path) but LEAVES the owner's marker
    # on disk so the live run stays armed. (Pre-Phase-8 this deleted the marker,
    # silently disarming enforcement mid-run when a concurrent session fired.)
    marker = lazy_core.read_run_marker(session_id=session_id)
    if marker is None:
        # No active run → silent exit (bash wrapper handles this, but guard here too).
        return None

    # Phase 9 WU-9.1 — INJECT NEVER BINDS.  When the marker is UNBOUND
    # (session_id=None, "bind-pending"), exit SILENTLY before any side effect:
    # no banner, no probe run, no emission registration, no counter advance, no
    # marker mutation.  Binding now lives EXCLUSIVELY in the guard
    # (lazy_guard.py binds on the first ALLOW of a registered prompt — Phase 9
    # WU-9.2).
    #
    # Rationale (live incident 2026-06-12 ~19:33Z): the inject hook fires BEFORE
    # a turn's work, so the orchestrator's own invocation turn cannot bind — the
    # FIRST hook firing anywhere wins.  A concurrent interactive session's
    # message therefore bound the live run's marker to the WRONG session,
    # silently disarming the batch run's guard (non-owner fast-path) while
    # spraying banners, spurious registry emissions, and repeat-counter
    # inflation into the interactive session.  By making inject a pure no-op on
    # an unbound marker and moving the bind to the guard's ALLOW path (which only
    # the orchestrator can reach — an allow requires a registry hit, and only the
    # orchestrator dispatches script-emitted prompts), the binding anchor becomes
    # unforgeable by bystanders.
    #
    # Note: read_run_marker(session_id=...) treats a bind-pending marker as NOT
    # session-stale (it is never stale on session-id alone — see read_run_marker
    # path B), so it RETURNS the unbound marker here.  This explicit check is the
    # gate that turns that returned-but-unbound marker into a silent no-op.
    if marker.get("session_id") is None:
        return None

    # Surface any existing breadcrumb from a previous hook error.
    breadcrumb_text = _read_and_clear_breadcrumb()

    # Run the full probe form.  The probe also registers the emitted prompt
    # (nonce + hash) as a side effect so the guard can validate the next dispatch.
    probe_data = _run_probe(marker)

    # Retrieve the most recent nonce from the registry (registered by the probe).
    nonce = _latest_nonce()

    # Build the additionalContext string.
    turn = _turn_n(marker)

    # Start with the LAZY-ROUTE banner.
    parts: list[str] = [f"LAZY-ROUTE (hook-injected, turn {turn}):"]

    # Embed the probe JSON evidence.
    if probe_data is not None:
        parts.append(json.dumps(probe_data, separators=(", ", ": ")))
    else:
        parts.append("[probe failed — re-run manually: --repeat-count --probe --emit-prompt]")

    # Surface the registered nonce as EVIDENCE that this turn's inject probe
    # registered a cycle emission. We deliberately do NOT emit a copyable
    # `by-ref: @@lazy-ref nonce=<hex>` dispatch line anymore.
    #
    # 2026-07-11 banner-ref divergence: the by-ref line invited the
    # orchestrator to dispatch by-reference straight from the banner. That is
    # only ever valid on the SAME turn the banner is injected (the emission was
    # registered on this turn's UserPromptSubmit). But a banner persists in
    # context across turn boundaries, so a copy-paste-ready by-ref line is a
    # carryover hazard: dispatched a turn later it violates the emit→dispatch
    # Freshness rule (lazy-batch SKILL "never dispatch an emission from an
    # earlier turn") — by then the nonce is stale/consumed/superseded, the
    # guard's F2a cannot resolve it, and a near-miss copy (the token WITH the
    # surrounding banner text) is not a bare-ref match, so under a
    # session-diverged marker the literal token can slip through to the
    # subagent (0 tool uses, "no task attached"). The banner already carries
    # the full `cycle_prompt` for same-turn verbatim dispatch, so the by-ref
    # line was pure convenience with no essential role — dropping it removes
    # the hazard while the same-turn path keeps working via `cycle_prompt`.
    if nonce is not None:
        parts.append(
            f"nonce={nonce} (evidence: this turn's probe registered an emission; "
            f"NOT a carry-over dispatch token — by-ref is valid only the SAME turn "
            f"it is injected. If a turn boundary intervened, this banner is STALE: "
            f"dispatch the banner's `cycle_prompt` verbatim this turn, or re-probe "
            f"with `--emit-prompt` and dispatch that fresh ref.)"
        )

    # For SessionStart(compact) and PostCompact: inject the post-compaction
    # re-entry protocol and marker counters (SPEC inject item 3).
    # SessionStart with source=="compact" or any PostCompact event.
    source = hook_input.get("source", "")
    is_post_compact = (
        hook_event_name == "PostCompact"
        or (hook_event_name == "SessionStart" and source == "compact")
    )
    if is_post_compact:
        forward = marker.get("forward_cycles", 0) or 0
        meta = marker.get("meta_cycles", 0) or 0
        parts.append(
            f"POST-COMPACTION RE-ENTRY: the run marker is still active "
            f"(forward_cycles={forward}, meta_cycles={meta}). "
            f"Read the LAZY-ROUTE above for the current cycle state. "
            f"Follow the Step 1d HARD rule: NEVER re-execute a step already "
            f"marked complete in the transcript — resume from the current step only."
        )

    # Surface any previous guard error (self-announcing breakage).
    if breadcrumb_text is not None:
        parts.append(f"HOOK_ERROR: {breadcrumb_text}")

    # live-settings split-brain drift advisory (Fix Scope 4 / D2): one extra line
    # when the live settings.json no longer reflects the tracked SSOT. Fail-open.
    try:
        _adv = _live_settings_advisory(marker.get("repo_root") or Path.cwd())
        if _adv:
            parts.append(_adv)
    except Exception:  # noqa: BLE001 — fail-open, banner must never break
        pass

    additional_context = " ".join(parts)

    # Emit the hookSpecificOutput JSON.
    payload = {
        "hookSpecificOutput": {
            "hookEventName": hook_event_name,
            "additionalContext": additional_context,
        }
    }
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Main entry point.  Reads stdin, runs inject logic, writes result to stdout."""
    try:
        stdin_text = sys.stdin.read()
        result = inject(stdin_text)
        if result is not None:
            sys.stdout.write(result + "\n")
        return 0
    except Exception as exc:  # noqa: BLE001
        _write_breadcrumb(str(exc))
        return 0


if __name__ == "__main__":
    sys.exit(main())
