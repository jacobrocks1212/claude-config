#!/bin/bash
# cycle-subagent-bg-gate-guard.sh — PreToolUse(Bash|PowerShell) hook
# (adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke, Phase 2 /
#  Gap 1 — mechanical foreground enforcement).
#
# THE GAP-1 MECHANICAL FOREGROUND-ENFORCEMENT GUARD. A long verification suite /
# gate (`npm run qg`, `npm run test`, `pytest`, `vitest`, `cargo test`,
# `dotnet test`, the `gate-battery` aggregate) launched `run_in_background: true`
# from inside a DISPATCHED cycle subagent DIES when that subagent's turn ends —
# its process tree is torn down with the turn. The subagent then returns an
# ambiguous "suite at N%, the background waiter will re-invoke me, holding"
# non-result, which the orchestrator cannot distinguish from a genuine resultless
# return and mishandles into a redundant recovery dispatch that collides
# (one-writer) with the harness-re-invoked agent. This guard denies that
# backgrounded launch AT ITS SOURCE, forcing the mandated foreground-await (run
# the individual under-cap sub-components synchronously) so the ambiguous return
# is never produced.
#
# The prose mandate this makes mechanical is `cycle-base-prompt.md` turn-end §1 /
# `turn-end-gate.md` ("Never background a long gate from inside this cycle
# subagent — its process tree is torn down when your turn ends").
#
# DELINEATION (three distinct concerns — NOT redundant):
#   * THIS guard  — the backgrounded gate/test-SUITE class inside an ARMED cycle
#                   subagent (marker-gated + agent_id-gated + run_in_background).
#   * long-build-ownership-guard.sh — exact long-BUILD invocations, request-time
#                   (any position, no marker/background needed). Registered
#                   BEFORE this guard so a raw long BUILD surfaces the
#                   ownership-takeover signature first; this guard targets the
#                   gate/test-suite class the ownership guard does not cover
#                   (e.g. a bare `npm run qg`, `pytest`, `vitest`).
#   * lazy-cycle-containment.sh — routing/lifecycle ops (marker-gated).
#
# DENY PREDICATE (ALL must hold):
#   (1) tool is a command tool (Bash|PowerShell — COMMAND_TOOL_NAMES),
#   (2) the payload carries `agent_id` (a dispatched subagent — the field Claude
#       Code injects ONLY from within a subagent, ABSENT on the main thread), so
#       the main-session orchestrator legitimately backgrounding a long gate is
#       NEVER denied,
#   (3) `tool_input.run_in_background` is truthy,
#   (4) the command's first real command-segment token matches the conservative
#       gate/test-suite set, AND
#   (5) the cycle-subagent marker (lazy-cycle-active.json) is present for this
#       repo (an armed cycle).
# Everything else ALLOWS.
#
# NOTE on "fail-open block": a PreToolUse blocks via the JSON
# `permissionDecision: deny` — a non-zero exit is a HARD error, not a soft block.
# So the block is a `deny` JSON naming the foreground-await mandate; that IS the
# fail-open block in this framework, matching every sibling guard.
#
# FAIL-OPEN: any parse/match/resolution error (malformed JSON, missing python,
# unexpected payload shape, unresolvable marker) ALLOWS the command + writes a
# best-effort breadcrumb — a broken guard must never wedge the pipeline.
#
# shared-hook-lib: python resolution + scripts-dir + the no-python breadcrumb are
# provided by the SOURCED hook-prelude.sh (HOOK_PYTHON / HOOK_SCRIPTS_DIR /
# HOOK_NAME); the allow/deny emitters, the countable hook-events append, the
# fail-open breadcrumb, AND the command-segment anchors (CMD_START / PATH_PREFIX)
# come from hook_lib. The PS-syntax audit (_normalize_ps_syntax), the heredoc
# mask, COMMAND_TOOL_NAMES, and the keyed cycle-marker resolution (imports
# lazy_core directly — hook_lib deliberately does NOT re-export claude_state_dir)
# stay hook-local, mirroring lazy-cycle-containment.sh / long-build-ownership-guard.sh.

# Source the shared hook prelude, fail-open-guarded. A missing/broken prelude
# ALLOWS (exit 0), never wedges. Builtins only ($0 may carry Windows backslashes;
# `dirname` is not guaranteed on a non-login git-bash PATH).
SELF="${0//\\//}"
case "$SELF" in
  */*) _HOOK_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   _HOOK_DIR="$(pwd)" ;;
esac
. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0

# If hook_lib is unavailable, leave a prelude-side trace and fail OPEN.
if [ ! -f "$HOOK_SCRIPTS_DIR/hook_lib.py" ]; then
  hook_emit_error_event "$HOOK_NAME" "" "hook_lib.py not found in scripts dir"
  exit 0
fi

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin and emits an allow/deny hookSpecificOutput block (or nothing for a
# fast allow). It NEVER exits non-zero on an internal error. The body is passed
# via `-c` (NOT a heredoc): a heredoc would BIND python's stdin to the body,
# swallowing the PreToolUse JSON piped into this hook.
read -r -d '' _BGG_PY <<'PYEOF'
import json
import os
import re
import sys

try:
    _sd = os.environ.get("HOOK_SCRIPTS_DIR")
    if _sd and _sd not in sys.path:
        sys.path.insert(0, _sd)
    import hook_lib
except ImportError:
    sys.exit(0)

_HOOK = "cycle-subagent-bg-gate-guard"
_SIGNATURE = "CYCLE-BG-GATE-FOREGROUND"

# powershell-tool-bypasses-bash-matched-guards: hook-local literal (not a shared
# import) so the fail-open contract never depends on an external module — kept in
# lockstep with the sibling command guards by inspection + the cross-guard
# registration meta-test in test_hooks.py.
COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})

# The cycle-subagent marker (a sibling of the run marker in the SAME per-repo
# keyed state dir under LAZY_STATE_DIR-unset production; the exact override dir
# under a hermetic test). Base fallback for any pre-resolution failure.
STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)
MARKER = os.path.join(STATE_DIR, "lazy-cycle-active.json")


def _resolve_marker_path(cwd):
    """Return the cycle-marker path for the current repo — mirrors
    lazy-cycle-containment.sh._resolve_marker_path EXACTLY (repo_key derivation
    lives ONLY in Python). LAZY_STATE_DIR set → use it exactly; unset →
    lazy_core.claude_state_dir(create=False) keyed on the PreToolUse cwd.
    FAIL-OPEN: any resolution failure falls back to the base (un-keyed) path — a
    missed marker only weakens THIS guard for one event (defaults to allow)."""
    if os.environ.get("LAZY_STATE_DIR"):
        return os.path.join(os.environ["LAZY_STATE_DIR"], "lazy-cycle-active.json")
    try:
        scripts_dir = os.environ.get("HOOK_SCRIPTS_DIR")
        if scripts_dir and scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import lazy_core
        lazy_core.set_active_repo_root(cwd or None)
        keyed = lazy_core.claude_state_dir(create=False)
        return os.path.join(str(keyed), "lazy-cycle-active.json")
    except Exception:
        return MARKER


# PowerShell backtick line-continuation → single space; one level of nested
# `powershell/pwsh -Command "..."` unwrapped. Hook-local copy (lockstep with the
# sibling guards).
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")
_PS_NESTED_COMMAND_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*?-[Cc]ommand\s+[\"']"
)


def _normalize_ps_syntax(command):
    command = _PS_LINE_CONTINUATION_RE.sub(" ", command)
    original = command
    for m in _PS_NESTED_COMMAND_RE.finditer(original):
        tail = original[m.end():].rstrip("\"'")
        if tail:
            command += "\n" + tail
    return command


# Heredoc-body masking (blank the interior incl. newlines) — hook-local copy,
# lockstep with the sibling CMD_START-anchored guards.
_HEREDOC_INTRODUCER_RE = re.compile(
    r"<<(-)?[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|([^\s'\"<>|;&()]+))"
)


def _mask_heredoc(command):
    out = list(command)
    consumed_until = 0
    for m in _HEREDOC_INTRODUCER_RE.finditer(command):
        if m.start() < consumed_until:
            continue
        word = m.group(2)
        if word is None:
            word = m.group(3)
        if word is None:
            word = m.group(4)
        if not word:
            continue
        nl = command.find("\n", m.end())
        if nl == -1:
            continue
        body_start = nl + 1
        if m.group(1) is not None:
            term_re = re.compile(
                r"^[ \t]*" + re.escape(word) + r"[ \t]*$", re.MULTILINE
            )
        else:
            term_re = re.compile(
                r"^" + re.escape(word) + r"[ \t]*$", re.MULTILINE
            )
        term_match = term_re.search(command, body_start)
        body_end = term_match.start() if term_match else len(command)
        for i in range(body_start, body_end):
            out[i] = " "
        consumed_until = body_end
    return "".join(out)


# Conservative gate/test-SUITE token set at a COMMAND position (segment start,
# after optional env prefix + optional path prefix), mirroring
# long-build-ownership-guard.sh's _LONG_BUILD_RE construction. Enumerated
# (near-zero false-positive charter): only these long-running suites, never a
# fast check. `python[3] -m pytest` is covered (the dominant real invocation);
# `npm run build:docs` / a buried `pytest` argument never match (segment anchor).
_GATE_SUITE_RE = re.compile(
    hook_lib.CMD_START + hook_lib.PATH_PREFIX + r"(?:"
    r"(?:python3?\s+-m\s+)?pytest(?:\s|$)"
    r"|vitest(?:\s|$)"
    r"|cargo\s+test(?:\s|$)"
    r"|dotnet\s+test(?:\s|$)"
    r"|npm\s+run\s+qg(?:[\s:]|$)"
    r"|npm\s+run\s+test(?:[\s:]|$)"
    r"|(?:python3?\s+)?(?:[^\s;&|]*[\\/])?gate-battery(?:\.py)?(?:\s|$)"
    r")"
)


def _is_truthy_background(val):
    """True iff *val* is a truthy background-dispatch flag (JSON True or the
    common string encodings). Anything else is a foreground dispatch."""
    if val is True:
        return True
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return val != 0
    return False


CORRECTIVE = (
    "BACKGROUNDED LONG GATE DENIED IN A CYCLE SUBAGENT "
    f"[{_SIGNATURE}]: a long verification suite / gate "
    "(`npm run qg` / `npm run test` / `pytest` / `vitest` / `cargo test` / "
    "`dotnet test` / `gate-battery`) launched `run_in_background: true` from "
    "inside a dispatched cycle subagent DIES when your turn ends — its process "
    "tree is torn down with the turn, leaving an ambiguous 'holding, will "
    "re-invoke' return that the orchestrator mishandles into a redundant "
    "recovery dispatch. Do NOT background this gate: run its individual "
    "UNDER-cap sub-components SYNCHRONOUSLY in the FOREGROUND (each drives to a "
    "real pass/fail within the Bash cap), then commit. Re-run WITHOUT "
    "run_in_background."
)


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)  # JSONDecodeError → caught below → fail-open
    if payload.get("tool_name", "") not in COMMAND_TOOL_NAMES:
        hook_lib.allow()
    # Main-thread orchestrator (no agent_id) legitimately backgrounds long gates.
    if not payload.get("agent_id"):
        hook_lib.allow()
    ti = payload.get("tool_input") or {}
    command = ti.get("command", "")
    if not isinstance(command, str) or not command:
        hook_lib.allow()
    # Only a BACKGROUNDED launch is the concern.
    if not _is_truthy_background(ti.get("run_in_background")):
        hook_lib.allow()
    command = _normalize_ps_syntax(command)
    command = _mask_heredoc(command)
    # Cheap gate-token match BEFORE the (heavier) marker resolution.
    if not _GATE_SUITE_RE.search(command):
        hook_lib.allow()
    # Armed only while THIS repo's cycle-subagent marker is present.
    marker_path = _resolve_marker_path(payload.get("cwd", "") or "")
    if not os.path.isfile(marker_path):
        hook_lib.allow()
    # All predicate conditions hold → deny (countable event + JSON deny).
    hook_lib.append_hook_event(
        "deny", _HOOK, _SIGNATURE, command,
        repo_root=payload.get("cwd") or "",
    )
    hook_lib.deny(CORRECTIVE)


try:
    main()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 — fail-OPEN on ANY error.
    hook_lib.breadcrumb(_HOOK, exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — expected; the variable
# is populated. Run python with the captured body via -c so the hook's real
# stdin (the PreToolUse payload) reaches python untouched. HOOK_SCRIPTS_DIR is
# threaded via env so the inline body can import hook_lib (+ lazy_core for the
# keyed marker resolution).
HOOK_SCRIPTS_DIR="$HOOK_SCRIPTS_DIR" "$HOOK_PYTHON" -c "$_BGG_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
