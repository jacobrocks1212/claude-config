#!/usr/bin/env python3
"""
lazy_guard.py — PreToolUse guard CLI for the lazy-dispatch-guard.sh hook.

Reads a Claude Code PreToolUse hook-input JSON from stdin and decides whether
to allow or deny the Agent dispatch by checking the prompt registry.

Exit code: always 0 (deny is expressed in JSON, not exit code).  Fail-OPEN
semantics: any internal exception exits 0 silently (the dispatch is allowed)
and writes a hook-error.json breadcrumb in the state dir so the next inject
turn can surface the breakage.

Decision logic (all paths require a valid run marker; no marker → exit 0):
  1. Hash tool_input.prompt (sha256, CRLF-normalized) and look up registry.
     If tool_input has NO ``prompt`` key at all → silent allow (exit 0, no
     output); there is nothing to validate.  A present-but-empty or
     unregistered prompt stays on the deny path.
  2. ALLOW path (Phase 9 WU-9.2: BOTH allow sub-paths bind an UNBOUND marker to
     the caller's session_id, best-effort/fail-open — only the orchestrator can
     produce an allow, so this is the unforgeable bind anchor that replaced
     inject's bind-on-first-hook-firing; a DENY never binds):
       - Unconsumed fresh hit: consume nonce recording the consumer tool_use_id;
         print allow JSON.  Phase 8 WU-8.2: if the matched entry's class is
         "hardening", best-effort ack the oldest unacked deny-ledger entry here
         (debt clears only when a hardening dispatch actually reaches execution;
         ack moved from emission-time).  An ack failure never changes the allow.
       - Idempotent re-fire: hit already consumed BY THE SAME tool_use_id.
         This is a deliberate defensive extension beyond the E4 spike note
         (RUNTIME_SPIKE.md E4 observed double-fire on a DENIED call and noted
         "consumed = deny"); the allow-refire-same-consumer rule goes further
         and turns the second fire of an ALLOWED call into an allow too, so the
         orchestrator never receives a spurious deny for a dispatch it already
         legitimately executed.
  3. DENY path (miss / stale / consumed-by-other):
       - Default deny: permissionDecisionReason instructs the canonical corrective
         recipe: re-run the Step 1a probe + --emit-prompt + --emit-dispatch hardening.
       - Hardening depth-cap deny: when the matched registry entry has class
         "hardening" (whether consumed-by-other OR stale/expired unconsumed),
         the recursion guard fires — the reason instead instructs halt +
         PushNotification and does NOT recommend --emit-dispatch hardening
         (depth hard-cap 1).  A denial of a hardening dispatch must never
         recommend recursive hardening, regardless of why the entry was denied.
  4. ANY exception → fail-OPEN: exit 0, nothing on stdout, write hook-error.json.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution — lazy_core lives in the same directory as this script.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    import lazy_core  # type: ignore[import]
except ImportError as _import_err:
    # Without lazy_core we cannot do anything useful — fail open.
    sys.exit(0)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HOOK_NAME = "lazy-dispatch-guard"


# ---------------------------------------------------------------------------
# Breadcrumb writer (best-effort — never raises)
# ---------------------------------------------------------------------------

def _write_breadcrumb(error_msg: str) -> None:
    """Write a hook-error.json breadcrumb into the state dir.

    Best-effort: if the write fails for any reason, the exception is
    swallowed.  The guard must NEVER raise from this function.
    """
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
        pass  # Absolutely must not raise from the error handler.


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _allow_json(reason: str) -> str:
    """Return a compact allow JSON string."""
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        }
    })


def _deny_json(reason: str) -> str:
    """Return a compact deny JSON string."""
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


# ---------------------------------------------------------------------------
# Deny reason builders
# ---------------------------------------------------------------------------

_CORRECTIVE_RECIPE = (
    "dispatch prompt not script-emitted this turn — "
    "re-run the Step 1a probe (`--emit-prompt`) and dispatch its `cycle_prompt` verbatim; "
    "if the probe refuses or no route exists, dispatch the hardening stage via "
    "`--emit-dispatch hardening`; "
    "additionally, this denial itself must also be routed to the hardening stage "
    "(`--emit-dispatch hardening`, trigger_kind=validate-deny) per the inline-unbounded cadence "
    "(locked decision 4: a hand-composed prompt reaching the guard is a harness gap — "
    "inline, unbounded, no dedup)"
)

_HARDENING_DEPTH_CAP_REASON = (
    "hardening dispatch recursion guard: a hardening-class dispatch was already "
    "consumed by a different tool_use_id — depth is hard-capped at 1 to prevent "
    "self-recursion.  halt this cycle and send a PushNotification to the operator "
    "describing the routing failure.  Do NOT dispatch another hardening stage."
)


def _default_deny_reason() -> str:
    """Return the standard corrective deny reason for an unregistered/stale prompt."""
    return _CORRECTIVE_RECIPE


def _hardening_cap_deny_reason() -> str:
    """Return the depth-1 hardening cap reason (contains halt + PushNotification,
    must NOT contain --emit-dispatch hardening)."""
    return _HARDENING_DEPTH_CAP_REASON


# ---------------------------------------------------------------------------
# Probe logic: look up and decide
# ---------------------------------------------------------------------------

def _find_entry_by_sha(sha: str, tool_use_id: str = "") -> dict | None:
    """Find any registry entry (consumed or not) matching the given sha256.

    This is used by the idempotent re-fire and hardening-cap logic to inspect
    entries that lookup_emission() would skip (already consumed).

    Selection priority (in order):
      1. Any entry whose ``consumed_by`` exactly matches ``tool_use_id`` — the
         idempotent re-fire case: this consumer already owns the nonce.
      2. Otherwise, the NEWEST matching entry (iterate in reverse insertion order)
         — when the same prompt is registered in two successive cycles and
         consumed by different tool_use_ids, we must not mistake the first
         consumer's nonce for the second consumer's re-fire (which would
         incorrectly deny the second consumer as "consumed-by-other").

    Returns None when no entry with this sha exists.

    Loads the registry directly rather than going through lookup_emission so
    we can see consumed entries too.
    """
    # Access the internal registry loader via lazy_core.
    # lazy_core._load_registry is a private function but we're a sibling module
    # in the same package — this is acceptable for guard logic.
    try:
        data = lazy_core._load_registry()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None

    entries = data.get("entries", [])

    # Priority 1: prefer any entry already consumed by this exact tool_use_id.
    if tool_use_id:
        for entry in entries:
            if entry.get("prompt_sha256") == sha and entry.get("consumed_by") == tool_use_id:
                return entry

    # Priority 2: return the NEWEST matching entry (last in insertion order).
    for entry in reversed(entries):
        if entry.get("prompt_sha256") == sha:
            return entry

    return None


def _assert_registry_readable() -> None:
    """Raise ValueError when the registry file exists but is not valid JSON.

    lazy_core._load_registry() deliberately swallows parse errors (fail-open,
    corrupt file → start fresh).  The guard has stricter requirements: a corrupt
    registry is an internal error that must trigger the fail-open breadcrumb path
    rather than silently allowing or denying the dispatch.  This check raises
    BEFORE lookup_emission() is called so that main() catches the exception and
    writes hook-error.json.

    If the file is absent, the check is a no-op (absent registry is normal).
    """
    try:
        state_dir = lazy_core.claude_state_dir(create=False)
        registry_path = state_dir / "lazy-prompt-registry.json"
        if not registry_path.exists():
            return
        # Read raw bytes and attempt UTF-8 decode + JSON parse.  Any failure
        # here means the file is corrupt and we must raise to trigger fail-open.
        raw_bytes = registry_path.read_bytes()
        raw_text = raw_bytes.decode("utf-8", errors="strict")
        data = json.loads(raw_text)
        # Validate that the parsed value is the expected shape.
        if not (isinstance(data, dict) and isinstance(data.get("entries"), list)):
            raise ValueError(
                f"registry has unexpected shape: {type(data).__name__}"
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        # Re-raise as a RuntimeError so it propagates through guard() and is
        # caught by main()'s except-all handler, triggering the breadcrumb write.
        raise RuntimeError(
            "lazy-prompt-registry.json is corrupt or unreadable — "
            "failing open and writing hook-error.json breadcrumb"
        ) from None


def _ack_if_hardening(entry: dict) -> None:
    """Phase 8 WU-8.2: when the guard ALLOWS a hardening-class dispatch for the
    FIRST time, retire one unit of routed hardening debt (FIFO ack of the oldest
    unacked deny-ledger entry).

    Ack moved here from emission-time (Phase 7) so the debt clears only when a
    hardening dispatch actually reaches execution — a repeated --emit-dispatch
    hardening can no longer drain the ledger without a dispatch occurring.

    Best-effort / fail-open: any failure is swallowed.  An ack failure must NEVER
    change the allow output (the dispatch still proceeds).

    Caller contract: invoke ONLY on a first-time consumption of a hardening
    entry, never on an idempotent re-fire of an already-consumed entry (that
    would double-ack — the re-fire is the SAME logical dispatch).
    """
    try:
        if entry.get("class") == "hardening":
            lazy_core.ack_oldest_deny()
    except Exception:  # noqa: BLE001
        pass


def _bind_marker_on_allow(session_id: str | None) -> None:
    """Phase 9 WU-9.2: bind an UNBOUND run marker to the caller's session_id when
    the guard reaches an ALLOW (a registered-prompt hit — fresh consumption OR
    idempotent re-fire).

    This is the bind anchor that replaced inject's bind-on-first-hook-firing
    (Phase 9 WU-9.1): only the ORCHESTRATOR can produce an ALLOW (an allow
    requires a registry hit, and only the orchestrator dispatches script-emitted
    prompts), so binding here is unforgeable by a concurrent bystander session —
    closing the wrong-session bind race (live incident 2026-06-12 ~19:33Z).

    Best-effort / FAIL-OPEN: any failure is swallowed.  A bind failure must NEVER
    change the allow output (the dispatch still proceeds).  bind_marker_session
    is itself idempotent — a no-op when the marker is already bound — so calling
    it on every allow (including the bound-owner re-fire) is safe and cheap.

    Skips silently when the caller session_id is None/absent (nothing to bind to).

    Deny paths never call this — only an ALLOW binds.
    """
    try:
        if session_id:
            lazy_core.bind_marker_session(session_id)
    except Exception:  # noqa: BLE001
        pass


def _deny_and_ledger(
    reason: str,
    *,
    tool_use_id: str,
    sha: str,
    prompt: str,
) -> str:
    """Build the deny JSON AND best-effort append a deny-ledger entry.

    Phase 7 WU-7.1: EVERY deny appends one JSON line to lazy-deny-ledger.jsonl in
    the state dir so the routed hardening debt is mechanically auditable (the
    probe surfaces pending_hardening; --emit-dispatch hardening FIFO-acks; --run-end
    refuses on unacked entries).  The ledger append is wrapped in try/except AND
    lazy_core.append_deny_ledger_entry is itself fail-open, so a ledger-write
    failure can NEVER change the deny output or exit code — fail-open is sacred.

    The deny path is the ONLY writer; the allow paths never touch the ledger.
    """
    try:
        lazy_core.append_deny_ledger_entry(
            tool_use_id=tool_use_id,
            denied_sha12=sha[:12],
            reason_head=reason,
            prompt_head=prompt,
        )
    except Exception:  # noqa: BLE001
        # A ledger failure must never affect the deny — swallow and proceed.
        pass
    return _deny_json(reason)


def guard(stdin_text: str) -> str | None:
    """Core guard logic.  Returns a JSON string to print, or None to print nothing.

    Raises freely — the caller wraps in try/except for fail-OPEN handling.
    """
    # Parse hook input JSON.
    hook_input = json.loads(stdin_text)

    # Extract the prompt from tool_input.
    tool_input = hook_input.get("tool_input") or {}
    tool_use_id: str = hook_input.get("tool_use_id", "")
    session_id: str | None = hook_input.get("session_id") or None

    # Item 6: if tool_input has NO "prompt" key at all → silent allow (exit 0,
    # no output).  There is nothing to validate — this is not an Agent dispatch
    # the guard needs to police (e.g. a different tool type that happens to share
    # the PreToolUse hook matcher, or a tool_input with no dispatch prompt).
    # A present-but-empty or unregistered prompt stays on the deny path.
    if "prompt" not in tool_input:
        return None

    prompt = tool_input["prompt"]

    # Check whether a valid run marker is present.
    # Pass the hook-input session_id so staleness path B (session mismatch) can
    # fire in production: if the marker is bound to a different session_id (a
    # concurrent NON-owner session), read_run_marker returns None — allowing the
    # current (non-orchestrator) session through. Phase 8 WU-8.1: path B is
    # NON-DESTRUCTIVE — the marker is LEFT ON DISK so the owning run stays armed
    # (this guard firing from a non-owner session must never disarm the owner).
    marker = lazy_core.read_run_marker(session_id=session_id)
    if marker is None:
        # No active run — fast path allow (marker-absent path is handled by the
        # bash wrapper before reaching python, but guard against it here too).
        return None

    # Explicitly verify the registry is readable/valid before delegating to
    # lookup_emission().  lazy_core._load_registry() is fail-open (corrupt →
    # empty), but the guard must not silently deny when the registry is corrupt:
    # that would block legitimate dispatches.  If this call raises, main() will
    # catch it and write the hook-error.json breadcrumb (fail-open).
    _assert_registry_readable()

    # Hash the prompt (CRLF-normalized).
    sha = lazy_core.prompt_sha256(prompt)

    # --- 1. Try an unconsumed fresh lookup first. ----------------------------
    entry = lazy_core.lookup_emission(prompt)

    if entry is not None:
        # Unconsumed fresh hit → allow, consume recording the consumer.
        # This is the ONLY first-time-consumption allow path (the idempotent
        # re-fire path below is a re-fire of an ALREADY-consumed entry, so it
        # must NOT ack — that would double-ack the same logical dispatch).
        nonce = entry["nonce"]
        lazy_core.consume_nonce(nonce, consumer=tool_use_id)
        # Phase 8 WU-8.2: if this is a hardening-class dispatch reaching
        # execution, retire one unit of routed hardening debt (best-effort).
        _ack_if_hardening(entry)
        # Phase 9 WU-9.2: bind an unbound marker to the orchestrator session on
        # this ALLOW (best-effort / fail-open — never changes the allow output).
        _bind_marker_on_allow(session_id)
        reason = f"dispatch allowed — nonce {nonce} consumed by {tool_use_id}"
        return _allow_json(reason)

    # --- 2. No unconsumed fresh hit — look for any entry with this sha. ------
    # Pass tool_use_id so _find_entry_by_sha can prefer an entry already
    # consumed by this exact consumer (idempotent re-fire fast-path).
    any_entry = _find_entry_by_sha(sha, tool_use_id=tool_use_id)

    if any_entry is not None:
        entry_class = any_entry.get("class", "")
        is_consumed = any_entry.get("consumed", False)

        if is_consumed:
            consumed_by = any_entry.get("consumed_by")

            # Idempotent re-fire: SAME tool_use_id already consumed this nonce.
            # This is a deliberate defensive extension beyond the E4 spike note
            # (which observed double-fire on a DENIED call): we also allow a
            # second fire when the SAME consumer already owns the nonce from a
            # prior ALLOW, so the orchestrator never receives a spurious deny.
            if consumed_by is not None and consumed_by == tool_use_id:
                nonce = any_entry["nonce"]
                # Phase 9 WU-9.2: the idempotent re-fire is also an ALLOW of a
                # registered-prompt hit, so it binds an unbound marker too (per
                # the interface contract: BOTH allow paths bind).  Idempotent —
                # if the first allow already bound the marker, this is a no-op.
                _bind_marker_on_allow(session_id)
                reason = (
                    f"idempotent re-fire — nonce {nonce} was already consumed by "
                    f"this tool_use_id ({tool_use_id}); allowing again."
                )
                return _allow_json(reason)

            # Consumed by a DIFFERENT tool_use_id — deny.
            if entry_class == "hardening":
                # Depth-1 hardening cap: a hardening dispatch consumed by another
                # consumer must not trigger recursive hardening.
                return _deny_and_ledger(
                    _hardening_cap_deny_reason(),
                    tool_use_id=tool_use_id, sha=sha, prompt=prompt,
                )

            # Default deny for consumed-by-other (non-hardening).
            return _deny_and_ledger(
                _default_deny_reason(),
                tool_use_id=tool_use_id, sha=sha, prompt=prompt,
            )

        else:
            # Entry exists but is NOT consumed — it failed the freshness/TTL
            # gate in lookup_emission (stale emitted_at or predates current run).
            # Apply the hardening cap here too: a denial of a hardening-class
            # entry must NEVER recommend recursive hardening, regardless of
            # whether it failed because consumed-by-other or because it is
            # stale/expired unconsumed (SPEC: "a denial of a hardening dispatch
            # must never recommend recursive hardening").
            if entry_class == "hardening":
                return _deny_and_ledger(
                    _hardening_cap_deny_reason(),
                    tool_use_id=tool_use_id, sha=sha, prompt=prompt,
                )

            # Non-hardening stale/expired entry → standard corrective deny.
            return _deny_and_ledger(
                _default_deny_reason(),
                tool_use_id=tool_use_id, sha=sha, prompt=prompt,
            )

    # --- 3. No matching entry at all. ----------------------------------------
    # Standard deny with corrective recipe.
    return _deny_and_ledger(
        _default_deny_reason(),
        tool_use_id=tool_use_id, sha=sha, prompt=prompt,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Main entry point.  Reads stdin, runs guard logic, writes result to stdout.

    Fail-OPEN contract: any unhandled exception → exit 0 silently (the dispatch
    is allowed), write hook-error.json breadcrumb.
    """
    try:
        stdin_text = sys.stdin.read()
        result = guard(stdin_text)
        if result is not None:
            sys.stdout.write(result + "\n")
        return 0
    except Exception as exc:  # noqa: BLE001
        # Fail-OPEN: write breadcrumb, exit 0, nothing on stdout.
        _write_breadcrumb(str(exc))
        return 0


if __name__ == "__main__":
    sys.exit(main())
