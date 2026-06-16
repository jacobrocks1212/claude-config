#!/bin/bash
# lazy-cycle-containment.sh — PreToolUse containment hook (lazy-cycle-containment
# C2; recursion/lifecycle re-targeted on agent_id by
# hardening-blind-to-process-friction Phase 1 / D4).
#
# TWO INDEPENDENT TRIPS:
#
# 1. agent_id-targeted (D4 — arming-free, the load-bearing recursion trip):
#    a dispatched cycle subagent is EXACTLY the context where the PreToolUse
#    payload carries an `agent_id` field (Claude Code injects it ONLY when the
#    hook fires from within a subagent; it is ABSENT on the main thread —
#    confirmed against the installed version's hook-input schema). So whenever
#    `agent_id` is present this hook DENIES the recursion/lifecycle/routing ops
#    a runaway needs to form a loop: recursive Agent/Task dispatch, a nested
#    /lazy-batch invocation, the orchestrator-only lazy-state.py/bug-state.py
#    routing+lifecycle flags, and dev:kill/dev:restart — with NO marker arming
#    required. When `agent_id` is ABSENT (the main-thread orchestrator) all of
#    these are ALLOWED, so the orchestrator is never self-denied (this fixes the
#    Proven-Finding-#3 self-deny defect — the orchestrator's own legitimate
#    cycle dispatch + between-cycle lifecycle ops always pass).
#
# 2. marker-gated (retained complementary carrier): while the CYCLE-SUBAGENT
#    marker (~/.claude/state/lazy-cycle-active.json) is present, the 2nd-feature
#    commit tripwire + commit-count backstop fire (feature_id/commit_tally are
#    read from the marker). These stay marker-gated; only recursion/lifecycle/
#    routing moved to agent_id.
#
# Fast path: when the cycle marker is ABSENT *and* the payload carries no
# `agent_id` (the common interactive / main-thread case), the inline Python
# fast-allows immediately — zero deny evaluation. The bash side no longer
# short-circuits on marker-absence (the agent_id trip must run even with no
# marker), so the inline Python always evaluates; the no-marker+no-agent_id
# fast-allow keeps the common case cheap.
#
# Fail-OPEN: any internal error (malformed JSON, missing python, unexpected
# state) writes a hook-error.json breadcrumb and ALLOWS — a broken hook must
# never wedge the pipeline.  The C3 state-script refusal (lazy_core.py) is the
# backstop.  This mirrors lazy-route-inject.sh / lazy-dispatch-guard.sh.
#
# Python resolution: python3 preferred (WSL / Linux), falling back to python
# (Windows git-bash where python3 may not be on PATH).
#
# Test override: LAZY_CYCLE_STAGED_PATHS (newline-separated) substitutes for
# `git diff --cached --name-only` so the 2nd-feature tripwire is hermetically
# testable without a temp git repo.

# Resolve the state dir (mirrors lazy_core.claude_state_dir() logic).
STATE_DIR="${LAZY_STATE_DIR:-$HOME/.claude/state}"
MARKER="$STATE_DIR/lazy-cycle-active.json"

# NOTE (D4): the bash fast-path no longer exits on marker-absence — the inline
# Python must evaluate `agent_id` even when no marker is armed. The Python body
# fast-allows immediately for the common no-marker + no-agent_id case, so the
# only added cost for interactive/main-thread events is one short Python start.

# Resolve python interpreter: prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all → fail open (exit 0, no output). Best-effort breadcrumb.
  printf '{"hook":"lazy-cycle-containment","error":"no python interpreter on PATH","at":""}\n' \
    > "$STATE_DIR/hook-error.json" 2>/dev/null || true
  exit 0
fi

# All deny/allow logic + commit_tally mutation lives in this inline Python.
# It reads the PreToolUse JSON from stdin and emits an allow/deny
# hookSpecificOutput block (or nothing for a fast allow).  It NEVER exits
# non-zero on an internal error: a PreToolUse non-zero exit is a hard blocking
# error in Claude Code, so the contract is fail-OPEN-via-empty-output.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON
# piped into this hook.  With `-c`, the hook's real stdin (the payload) flows
# straight through to python's sys.stdin.
read -r -d '' _LCC_PY <<'PYEOF'
import json
import os
import re
import sys
import datetime

STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)
MARKER = os.path.join(STATE_DIR, "lazy-cycle-active.json")

CORRECTIVE = (
    "you are a single cycle subagent — STOP after your commit+push+report; "
    "routing the next cycle is the orchestrator's job. This op "
    "(lazy-state.py routing/lifecycle, dev:kill/restart, recursive Agent "
    "dispatch, or a second-feature/over-ceiling commit) is DENIED in-flight "
    "while a cycle dispatch is active."
)

# Commit-count backstop ceiling (SPEC §C2 Open Question — generous; tunable).
COMMIT_CEILING = 25

# Loop-formation flags: routing/lifecycle ops only the orchestrator may run.
# cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE, C2 side): --cycle-end
# / --cycle-begin added here so the arming-free agent_id subagent trip denies a
# subagent's attempt to clear/arm the containment marker — belt-and-suspenders
# with the C3 refuse_cycle_marker_mutation_if_subagent guard (lazy_core.py). The
# main-thread orchestrator (agent_id ABSENT) is never self-denied, so its own
# bracket (--cycle-begin before dispatch, --cycle-end after) always passes.
LOOP_FORMATION_FLAGS = (
    "--probe", "--emit-prompt", "--repeat-count", "--repeat-count-peek",
    "--run-start", "--run-end", "--apply-pseudo", "--enqueue-adhoc",
    "--emit-dispatch", "--cycle-end", "--cycle-begin",
)
# Narrow ops a legitimately-dispatched subagent needs — never denied.
ALLOW_LISTED_FLAGS = ("--neutralize-sentinel", "--verify-ledger")

# Runtime-lifecycle commands (orchestrator-only; a subagent must never restart
# the dev server / kill ports).
LIFECYCLE_PATTERNS = (
    "dev:kill", "dev:restart", "kill-port 3333", "kill-port 1420",
)

# Recursive batch invocation: a dispatched cycle subagent must never start a
# nested /lazy* batch orchestrator (the literal runaway path). Matches a
# /lazy-batch (or /lazy-bug-batch / -cloud) slash-command token anywhere in the
# Bash command.
_LAZY_BATCH_RE = re.compile(r"/lazy(?:-bug)?-batch(?:-cloud)?\b")

# Carve-out shared roots: always allowed in a commit even when not under the
# marker's feature dir (these are cross-feature shared state, not a 2nd feature).
CARVE_OUT_PATHS = ("docs/features/queue.json", "docs/features/ROADMAP.md", "CLAUDE.md")

_STATE_PY_RE = re.compile(r"\b(?:lazy-state|bug-state)\.py\b")
_FEATURE_DIR_RE = re.compile(r"docs/(?:features|bugs)/([^/]+)/")


def _breadcrumb(err):
    """Write a fail-open breadcrumb; never raise."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "hook-error.json"), "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "hook": "lazy-cycle-containment",
                    "error": str(err),
                    "at": datetime.datetime.now(tz=datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
                fh,
            )
    except Exception:
        pass


def _allow():
    """Fast allow: emit nothing (PreToolUse with no decision = allow)."""
    sys.exit(0)


def _deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _read_marker():
    """Return the cycle marker dict, or None if absent/unreadable.

    D4: the marker may legitimately be ABSENT (the agent_id trip is arming-free).
    An unreadable/corrupt marker reads as None — the marker-gated tripwires then
    no-op, while the agent_id trip is unaffected (it does not consult the marker).
    """
    try:
        with open(MARKER, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _staged_paths():
    """Resolve staged paths from the test override or `git diff --cached`."""
    override = os.environ.get("LAZY_CYCLE_STAGED_PATHS")
    if override is not None:
        return [p.strip() for p in override.splitlines() if p.strip()]
    import subprocess
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True,
    )
    return [p.strip() for p in out.stdout.splitlines() if p.strip()]


def _is_carve_out(path, feature_id):
    norm = path.replace("\\", "/")
    if norm in CARVE_OUT_PATHS:
        return True
    # The feature's own dir (features OR bugs) is always allowed.
    m = _FEATURE_DIR_RE.search(norm)
    if m and m.group(1) == feature_id:
        return True
    return False


def _increment_tally(marker):
    """Read-modify-write commit_tally on an allowed commit; best-effort."""
    try:
        marker["commit_tally"] = int(marker.get("commit_tally", 0)) + 1
        tmp = MARKER + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(marker, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, MARKER)
    except Exception as exc:
        _breadcrumb(f"commit_tally increment failed: {exc}")


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)            # JSONDecodeError → caught → fail-open
    marker = _read_marker()              # may be None (D4: arming-free trip)

    # D4: a dispatched cycle subagent is exactly the context where `agent_id` is
    # present. It drives the recursion/lifecycle/routing deny — with no marker
    # arming required. The main-thread orchestrator (agent_id absent) is never
    # self-denied for these ops.
    is_subagent = bool(payload.get("agent_id"))

    # Fast-allow the common cheap case: not a subagent AND no marker → there is
    # nothing this hook can trip (recursion/lifecycle/routing need a subagent;
    # the commit tripwires need a marker).
    if not is_subagent and marker is None:
        _allow()

    tool_name = payload.get("tool_name", "")

    # --- Recursive dispatch: Agent/Task tool call from a subagent is denied. ---
    if tool_name in ("Agent", "Task"):
        if is_subagent:
            _deny(CORRECTIVE)
        # main-thread orchestrator dispatch → allow (no self-deny).
        _allow()

    if tool_name != "Bash":
        _allow()

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        _allow()

    if is_subagent:
        # --- Recursive batch invocation (the literal runaway path). ---
        if _LAZY_BATCH_RE.search(command):
            _deny(CORRECTIVE)

        # --- Loop-formation: lazy-state.py / bug-state.py routing flags. ---
        if _STATE_PY_RE.search(command):
            if any(flag in command for flag in ALLOW_LISTED_FLAGS):
                _allow()
            if any(flag in command for flag in LOOP_FORMATION_FLAGS):
                _deny(CORRECTIVE)
            # state-script call with no routing flag (e.g. a read) → allow.
            _allow()

        # --- Runtime-lifecycle commands. ---
        for pat in LIFECYCLE_PATTERNS:
            if pat in command:
                _deny(CORRECTIVE)

    # --- git commit: 2nd-feature tripwire + commit-count backstop. ---
    # Retained marker-gated (feature_id/commit_tally live on the marker); skip
    # entirely when no marker is armed.
    if marker is not None and re.search(r"\bgit\s+commit\b", command):
        feature_id = marker.get("feature_id")
        # Commit-count backstop (read BEFORE incrementing).
        if int(marker.get("commit_tally", 0)) >= COMMIT_CEILING:
            _deny(
                f"commit-count backstop: this dispatch has already made "
                f"{marker.get('commit_tally')} commits (ceiling {COMMIT_CEILING}). "
                + CORRECTIVE
            )
        # Second-feature tripwire.
        staged = _staged_paths()
        offending = [
            p for p in staged if not _is_carve_out(p, feature_id)
            and _FEATURE_DIR_RE.search(p.replace("\\", "/"))
            and _FEATURE_DIR_RE.search(p.replace("\\", "/")).group(1) != feature_id
        ]
        if offending:
            _deny(
                f"second-feature commit tripwire: staged path(s) {offending} are "
                f"under a different feature than the active dispatch ({feature_id!r}). "
                + CORRECTIVE
            )
        # Allowed commit → increment the tally, then allow.
        _increment_tally(marker)
        _allow()

    # Anything else (the subagent's real work) → allow.
    _allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 — fail-OPEN on ANY error.
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — that is expected; the
# variable is populated.  Run python with the captured body via -c so the
# hook's real stdin (the PreToolUse payload) reaches python untouched.
LAZY_STATE_DIR="$STATE_DIR" "$PYTHON" -c "$_LCC_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
