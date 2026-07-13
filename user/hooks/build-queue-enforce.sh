#!/bin/bash
# build-queue-enforce.sh — PreToolUse(Bash) hook
#
# MACHINE-GLOBAL BUILD-QUEUE SERIALIZER GATE (generalized per
# build-queue-generalization). A machine-global FIFO build queue
# (build-queue.ps1) serializes heavy builds so only one runs at a time across
# repos/worktrees. Thin per-repo skills route through that wrapper. This hook
# makes the queue un-bypassable: it DENIES raw heavy-build Bash invocations in
# queue-governed repos and redirects the agent to the correct skill.
#
# SCOPE GATE (D4, locked 2026-07-09): MANIFEST PRESENCE IS THE PRIMARY GATE.
# The payload cwd's git toplevel is resolved and
# `<toplevel>/.claude/skill-config/build-queue-ops.json` is read:
#   * valid manifest present → the deny set is compiled from the manifest's
#     per-op `deny` patterns (schema: {"version":1,"ops":{"<op>":{"exec":...,
#     "kind":"build"|"test","hygiene":...,"skill":"/<name>","deny":[...]}}});
#     the deny message names the op's `skill`.
#   * manifest MISSING or UNPARSEABLE in a repo whose remote matches
#     cognitoforms/cognito → LEGACY FALLBACK: today's hard-coded Cognito deny
#     set fires (a broken symlink must never silently disarm the only
#     enforcement protecting the copy-lock/recycle invariants). Remote is
#     resolved via `git -C <cwd> config --get remote.origin.url`; this
#     deliberately differs from block-work-repo-git-push.sh (which gates on
#     user.email) — Overwatch and mcp/ share the same work email but have
#     DIFFERENT remotes and MUST NOT be gated.
#   * neither manifest nor Cognito remote → allow everything (fail-open).
#
# PLATFORM GATE (D7, locked 2026-07-09): workstation-only v1 — the deny set is
# never armed off-Windows (no queue consumer exists there): non-nt python with
# no powershell.exe/pwsh on PATH → allow everything, silently.
# BQE_PLATFORM_OVERRIDE=inert|armed force-sets the check (tests only).
#
# DENY SURFACE: a heavy build appears ANYWHERE in the command (not only at the
# start), so a build chained behind a leading command — `cd "..." && dotnet
# build ...`, a pipeline, a `;`-chain — is still caught. The denied forms are:
#   * dotnet build
#   * dotnet test
#   * nx / npx nx with a build / test / run-many target
#   * a *-filtered.ps1 script invocation (build-filtered.ps1, test-filtered.ps1,
#     client-build-filtered.ps1, client-test-filtered.ps1)
#
# NEVER denied: dotnet restore, dotnet --version, dotnet ef, nx lint/typecheck/
# format, msbuild, dotnet msbuild, npm, pnpm, the build-queue.ps1 wrapper itself
# (the sanctioned path — allowed even though it carries a *-filtered.ps1 -Exec
# arg), or any command prefixed BUILD_QUEUE_BYPASS=1.
#
# ALLOW-LIST PRECEDENCE (unanchored): because deny is unanchored, a leading safe
# token can no longer short-circuit the whole command — `dotnet restore && dotnet
# build` MUST still deny (a real build is present). So the safe dotnet/nx variants
# are SUPPRESSED per-occurrence (blanked out of a scratch copy of the command)
# before the unanchored heavy-build scan; if any real heavy build survives the
# suppression, the command is denied.
#
# BYPASS TOKEN (L6): recognized PER SEGMENT, matching the deny surface's
# segment awareness. A whole command led by the token is allowed through
# immediately (before deny-matching); a token leading any LATER command
# segment (`cd "..." && BUILD_QUEUE_BYPASS=1 dotnet build ...`) suppresses
# that segment from the deny scan — but ONLY that segment: a real un-bypassed
# build in another segment still denies (the segment-aware bypass must not
# re-open the enforcement escape the cd-prefix-bypass fix closed).
#
# CLOSED BLIND SPOT: a `cd <dir> && dotnet build` no longer bypasses the deny
# matcher (the build verb is detected wherever it sits in the command). The
# Cognito-worktree SCOPE gate still keys on the payload cwd, so a build that
# `cd`s OUT of a Cognito worktree into a non-Cognito repo is still governed by
# the cwd at dispatch time (fail-open outside Cognito worktrees).
#
# FAIL-OPEN: any parse/match/subprocess error (malformed JSON, missing python,
# unexpected payload, git failure) ALLOWS the command — a broken hook must never
# block legitimate work. Deny is expressed via JSON permissionDecision: deny;
# a non-zero PreToolUse exit is a HARD error and is never used here.
#
# Python resolution: python3 preferred, falling back to python (Windows git-bash).

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all → fail open (exit 0, no output). guard-fail-open-leaves-no-trace:
  # this is the severest failure class (the ENTIRE python-bearing guard plane is
  # dead) and precisely the one no python-side appender can record, so the
  # breadcrumb is written here in pure bash (no python required). Best-effort —
  # every write is `2>/dev/null || true` so a breadcrumb failure never turns into
  # a deny or a non-zero exit. Kept as an identical copied block across every
  # python-bearing hook (interim per docs/bugs/guard-fail-open-leaves-no-trace D4
  # — the natural long-term home is a shared hook-prelude, not yet built; keep
  # the copies in lockstep).
  _HOOK_NOPY_BASE="${LAZY_STATE_DIR:-$HOME/.claude/state}"
  _HOOK_NOPY_TS="$(date +%s 2>/dev/null || echo 0)"
  mkdir -p "$_HOOK_NOPY_BASE" 2>/dev/null
  printf '{"hook":"build-queue-enforce","error":"no python interpreter on PATH","at":"%s"}' \
    "$_HOOK_NOPY_TS" > "$_HOOK_NOPY_BASE/hook-error.json" 2>/dev/null || true
  printf '{"ts":%s,"kind":"error","hook":"build-queue-enforce","repo_root":"","signature":"","detail":"no python interpreter on PATH"}\n' \
    "$_HOOK_NOPY_TS" >> "$_HOOK_NOPY_BASE/hook-events.jsonl" 2>/dev/null || true
  exit 0
fi

# incident-auto-capture Phase 1 (D2): resolve the scripts dir relative to this
# hook so the inline Python can import lazy_core for the keyed hook-events
# append (best-effort — the appender falls back to the base dir when the import
# is unavailable). Builtins only; $0 may carry Windows backslashes.
SELF="${0//\\//}"
case "$SELF" in
  */*) BQE_SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   BQE_SCRIPT_DIR="$(pwd)" ;;
esac
BQE_SCRIPTS_DIR="$BQE_SCRIPT_DIR/../scripts"

read -r -d '' _BQE_PY <<'PYEOF'
import datetime
import json
import os
import re
import subprocess
import sys

# powershell-tool-bypasses-bash-matched-guards: the harness exposes more than
# one command-execution tool (Bash, PowerShell) sharing the same
# tool_input.command shape. A guard gated on `tool_name == "Bash"` is silently
# bypassed by an equivalent command run through any OTHER member of this set.
# Kept as a hook-local literal (not a shared lazy_core import) so this hook's
# fail-open contract never depends on an external module resolving — the
# identical literal is embedded in lazy-cycle-containment.sh and
# long-build-ownership-guard.sh; keep the three in lockstep by inspection (and
# via the cross-guard registration meta-test in test_hooks.py) if this set
# ever grows a member.
COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})

STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)

# PowerShell-syntax regex audit (powershell-tool-bypasses-bash-matched-guards):
# env-assignment prefixes differ between shells (`NAME=value` in bash vs
# `$env:NAME='value';` in PowerShell). The bypass token is recognized in
# EITHER form, with an optional leading env-prefix (either form, repeated)
# before it.
_ENV_PREFIX_ANY = (
    r"(?:"
    r"[A-Za-z_][A-Za-z0-9_]*=\S+\s+"
    r"|\$env:[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:'[^']*'|\"[^\"]*\"|\S+)\s*;\s*"
    r")*"
)
_BYPASS_TOKEN_RE = (
    r"(?:BUILD_QUEUE_BYPASS=1(?:\s|$)"
    r"|\$env:BUILD_QUEUE_BYPASS\s*=\s*(?:'1'|\"1\"|1)\s*;?)"
)
# Match the bypass token as a leading env assignment. Applied to the whole
# command (fast-path allow) AND per segment via _suppress_bypassed_segments.
_BYPASS_RE = re.compile(r"^\s*" + _ENV_PREFIX_ANY + _BYPASS_TOKEN_RE)

# Shell separators that begin a new command segment (mirrors _CMD_START's
# character class). Splitting on these yields per-segment strings _BYPASS_RE
# can be matched against, so the bypass token is recognized when it leads the
# build's own segment behind a `cd "..." && ` (or `;`/pipeline) prefix.
_SEGMENT_SPLIT_RE = re.compile(r"([\n;&|({])")

# Match the sanctioned wrapper — allow before any deny-check.
# Matches the wrapper script name anywhere in the command (it may appear inside
# a quoted path as an argument to powershell.exe -File "...path.../build-queue.ps1").
_WRAPPER_RE = re.compile(r"build-queue\.ps1", re.IGNORECASE)

# Safe dotnet/nx variants that must NEVER count as a heavy build even though
# they share the "dotnet"/"nx" prefix. These occurrences are blanked out of a
# scratch copy of the command BEFORE the unanchored heavy-build scan, so a
# leading `dotnet restore` no longer masks a trailing `dotnet build`.
_DOTNET_SAFE_RE = re.compile(
    r"dotnet\s+(?:restore|--version|-v|ef|msbuild)\b", re.IGNORECASE
)
_NX_SAFE_RE = re.compile(
    r"(?:npx\s+)?nx\s+(?:lint|typecheck|format)\b", re.IGNORECASE
)

# Command-position anchor (mirrors long-build-ownership-guard.sh): a heavy
# build must be the INVOKED command — either the start of the string, or
# immediately after a shell separator (`&&`, `||`, `|`, `;`, `(`, `{`,
# newline), with optional leading `NAME=value` env assignments. This lets a
# build chained behind a leading command still deny (`cd "..." && dotnet
# build ...`) while a read verb referencing a build token as an ARGUMENT
# (`grep ... test-filtered.ps1`, `cat build-filtered.ps1 | head`) does not
# begin a command segment and so does not match.
#
# PowerShell-syntax regex audit (powershell-tool-bypasses-bash-matched-guards):
# env-assignment prefixes differ between shells (`NAME=value` in bash vs
# `$env:NAME='value';` in PowerShell) — mirrors _ENV_PREFIX_ANY above (the
# bypass-token prefix); kept as a separate literal because it is defined
# before _ENV_PREFIX_ANY in file order and both must stay in lockstep.
_ENV_PREFIX = (
    r"(?:"
    r"[A-Za-z_][A-Za-z0-9_]*=\S+\s+"
    r"|\$env:[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:'[^']*'|\"[^\"]*\"|\S+)\s*;\s*"
    r")*"
)
_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX

# PowerShell backtick line-continuation: the next physical line is part of the
# SAME logical command — not a segment boundary. Collapsed to a space before
# the deny scan so a continued invocation (`dotnet build `` + newline +
# `Cognito.sln`) is not hidden from the anchored patterns below by
# _CMD_START's `\n` separator.
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")

# PowerShell nesting: `powershell(.exe)?|pwsh ... -Command "..."` executes its
# quoted STRING argument as a command line — a heavy build hidden inside that
# string is not at a top-level segment-start position under _CMD_START.
# Purely additive: the tail following the opening quote is reappended as a
# synthetic newline-prefixed segment so the existing anchored patterns can
# still find it. (Distinct from _FILTERED_SCRIPT_POWERSHELL_RE below, which
# already handles the narrower `-File <path>` invocation form.)
_PS_NESTED_COMMAND_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*?-[Cc]ommand\s+[\"']"
)


def _normalize_ps_syntax(command):
    """Collapse backtick line-continuations and unwrap one level of nested
    `powershell/pwsh -Command "..."` so the deny scan sees a flat,
    segment-splittable command string. Purely additive/normalizing — never
    narrows what the existing matchers can already detect.

    Indexes against `original` (not the growing `command`) so multiple
    nested matches never slice with stale offsets. The appended tail's
    trailing quote (the -Command string's own closing delimiter) is
    stripped — otherwise a build that is the LAST token before the closing
    quote fails a boundary check that requires whitespace-or-end right
    after the matched invocation."""
    command = _PS_LINE_CONTINUATION_RE.sub(" ", command)
    original = command
    for m in _PS_NESTED_COMMAND_RE.finditer(original):
        tail = original[m.end():].rstrip("\"'")
        if tail:
            command += "\n" + tail
    return command

# Deny patterns. Run against the SUPPRESSED command (safe variants blanked out).
_DOTNET_BUILD_RE = re.compile(_CMD_START + r"dotnet\s+build(?:\s|$)", re.IGNORECASE)
_DOTNET_TEST_RE = re.compile(_CMD_START + r"dotnet\s+test(?:\s|$)", re.IGNORECASE)
# nx / npx nx with build, test, or run-many target.
# Matches: nx build X, nx test X, nx run-many --target=build/test,
#          npx nx build X, npx nx test X, npx nx run-many --target=build/test
_NX_BUILD_TEST_RE = re.compile(
    _CMD_START + r"(?:npx\s+)?nx\s+"
    r"(?:"
    r"(?:run-many\b.*?--target[= ]\s*(?:build|test)\b)"
    r"|(?:(?:build|test|run-many)\b)"
    r")",
    re.IGNORECASE | re.DOTALL,
)
# A *-filtered.ps1 script invoked directly (segment-leading, optionally with a
# path prefix so `./x`, `.\x`, and an absolute path still deny) — this does
# NOT match a bare `cat build-filtered.ps1` / `grep x test-filtered.ps1` /
# `find . -name build-filtered.ps1` because the script name there follows a
# read verb, not a command separator.
_FILTERED_SCRIPT_DIRECT_RE = re.compile(
    _CMD_START
    + r"(?:\.?[\\/])?(?:[^\s;&|]*[\\/])?"
    r"(?:build-filtered|test-filtered|client-build-filtered|client-test-filtered)\.ps1"
    r"(?:\s|$|\")",
    re.IGNORECASE,
)
# ...or invoked via `powershell(.exe)?`/`pwsh` with a `-File <path>` argument
# naming one of the four filtered scripts.
_FILTERED_SCRIPT_POWERSHELL_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*-File\s+\S*"
    r"(?:build-filtered|test-filtered|client-build-filtered|client-test-filtered)\.ps1",
    re.IGNORECASE,
)


def _suppress_safe(command):
    """Return a scratch copy of *command* with the safe dotnet/nx variant
    occurrences blanked out, so the unanchored heavy-build scan does not trip on
    them and a leading safe token cannot mask a trailing real build."""
    suppressed = _DOTNET_SAFE_RE.sub(" ", command)
    suppressed = _NX_SAFE_RE.sub(" ", suppressed)
    return suppressed


def _suppress_bypassed_segments(command):
    """Return a scratch copy of *command* with every segment led by
    BUILD_QUEUE_BYPASS=1 blanked out (length-preserving), so the deny scan
    skips a deliberately-bypassed build segment (`cd "..." &&
    BUILD_QUEUE_BYPASS=1 dotnet build ...`) while a real un-bypassed build in
    any OTHER segment still matches. Shell env-assignment semantics are
    per-segment, so per-segment recognition is the correct scope."""
    parts = _SEGMENT_SPLIT_RE.split(command)
    return "".join(
        " " * len(part) if _BYPASS_RE.match(part) else part
        for part in parts
    )


# incident-auto-capture Phase 1 (D2): the tool-call cwd, captured in main() so
# the event appender can attribute the event to the active repo. Best-effort.
_EVT_CWD = ""


def _append_hook_event(kind, signature, detail):
    """incident-auto-capture Phase 1 (D2): append one countable hook-event line
    (hook-events.jsonl). Best-effort / FAIL-OPEN — never raises, never changes
    the deny/allow output. Prefers the shared lazy_core appender (keyed state
    dir when the repo is resolvable; exact LAZY_STATE_DIR dir in tests); falls
    back to an inline append at the base dir when lazy_core is unavailable."""
    try:
        try:
            _sd = os.environ.get("BQE_SCRIPTS_DIR")
            if _sd and _sd not in sys.path:
                sys.path.insert(0, _sd)
            import lazy_core
            try:
                lazy_core.set_active_repo_root(_EVT_CWD or None)
                repo_root = str(lazy_core.active_repo_root() or "")
            except Exception:
                repo_root = _EVT_CWD or ""
            lazy_core.append_hook_event(
                kind, "build-queue-enforce", signature, detail,
                repo_root=repo_root,
            )
            return
        except ImportError:
            pass
        import time as _time
        os.makedirs(STATE_DIR, exist_ok=True)
        entry = {
            "ts": _time.time(), "kind": kind,
            "hook": "build-queue-enforce",
            "repo_root": _EVT_CWD or "", "signature": (signature or "")[:200],
            "detail": (detail or "")[:500],
        }
        with open(
            os.path.join(STATE_DIR, "hook-events.jsonl"), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _breadcrumb(err):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(
            os.path.join(STATE_DIR, "hook-error.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(
                {
                    "hook": "build-queue-enforce",
                    "error": str(err),
                    "at": datetime.datetime.now(tz=datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
                fh,
            )
    except Exception:
        pass
    # D2: the breadcrumb stays byte-identical; the countable history is the
    # additive hook-events line beside it (fail-open, never raises).
    _append_hook_event("error", "", str(err))


def _allow():
    sys.exit(0)


def _deny(reason, signature="build-queue-enforced"):
    # incident-auto-capture D2: countable deny event (fail-open, additive) —
    # each deny site passes its classified op as the signature.
    _append_hook_event("deny", signature, reason)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _is_cognito_worktree(cwd):
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return False
        url = result.stdout.strip().lower()
        return "cognitoforms/cognito" in url
    except Exception:
        return False


def _workstation_armed():
    """D7 (locked 2026-07-09): workstation-only v1 — the deny set is silently
    inert off-Windows (cloud/WSL-without-interop hosts run no queue builds).
    BQE_PLATFORM_OVERRIDE=inert|armed force-sets the verdict (tests only)."""
    override = os.environ.get("BQE_PLATFORM_OVERRIDE", "")
    if override == "inert":
        return False
    if override == "armed":
        return True
    if os.name == "nt":
        return True
    import shutil
    return bool(shutil.which("powershell.exe") or shutil.which("pwsh"))


def _git_toplevel(cwd):
    """Resolve the payload cwd's git toplevel (one subprocess, mirroring the
    remote check). None on any failure — fail-open family behavior."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return None
        top = result.stdout.strip()
        return top or None
    except Exception:
        return None


def _load_manifest(toplevel):
    """Read <toplevel>/.claude/skill-config/build-queue-ops.json.

    Returns (manifest_dict, None) on a valid manifest, (None, None) when the
    file is absent, and (None, error) when present but unreadable/malformed —
    callers branch on the distinction (D4: broken-in-Cognito → legacy
    fallback; broken elsewhere → allow + breadcrumb)."""
    path = os.path.join(toplevel, ".claude", "skill-config", "build-queue-ops.json")
    try:
        if not os.path.isfile(path):
            return None, None
    except Exception:
        return None, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        ops = data.get("ops") if isinstance(data, dict) else None
        if not isinstance(ops, dict) or not ops:
            raise ValueError("manifest carries no 'ops' mapping")
        return data, None
    except Exception as exc:
        return None, exc


def _compile_manifest_deny(pattern):
    """Compile one manifest `deny` entry onto the existing segment-start
    discipline. A `*.ps1` entry reuses the filtered-script shapes (direct
    segment-leading invocation with optional path prefix + the
    powershell -File form); any other entry is tokenized and joined with \\s+,
    anchored at _CMD_START — the invoke-vs-reference discrimination the
    Cognito denies already carry. Returns a list of compiled regexes
    (empty for a blank/unusable pattern)."""
    p = (pattern or "").strip()
    if not p:
        return []
    if p.lower().endswith(".ps1"):
        name = re.escape(os.path.basename(p.replace("\\", "/")))
        direct = re.compile(
            _CMD_START
            + r"(?:\.?[\\/])?(?:[^\s;&|]*[\\/])?" + name + r"(?:\s|$|\")",
            re.IGNORECASE,
        )
        psfile = re.compile(
            r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*-File\s+\S*" + name,
            re.IGNORECASE,
        )
        return [direct, psfile]
    body = r"\s+".join(re.escape(tok) for tok in p.split())
    return [re.compile(_CMD_START + body + r"(?:\s|$)", re.IGNORECASE)]


def _manifest_redirect_reason(op_name, skill, pattern):
    skill_txt = skill.strip() if isinstance(skill, str) and skill.strip() else (
        "the repo's registered build-queue skill"
    )
    return (
        f"BUILD QUEUE ENFORCED — use `{skill_txt}` instead of running "
        f"`{pattern}` directly.\n"
        f"This repo's build-queue ops manifest "
        f"(.claude/skill-config/build-queue-ops.json) registers this command "
        f"as op '{op_name}'. The machine-global build queue serializes heavy "
        f"builds across repos/worktrees so they do not thrash the machine; "
        f"{skill_txt} routes through the queue automatically.\n"
        f"  Correct: {skill_txt}\n"
        "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ... — the token must lead "
        "the build's own command segment (a `cd \"...\" && "
        "BUILD_QUEUE_BYPASS=1 ...` prefix is recognized)."
    )


def _scan_manifest_ops(manifest, scan, command):
    """Run the manifest-compiled deny surface over the suppressed scan copy.
    Denies (and exits) on the first match; returns silently when nothing
    matches. Malformed per-op entries are skipped — one bad entry must not
    disarm the rest (fail-open stays per-error-path, not per-file)."""
    ops = manifest.get("ops") or {}
    for op_name, entry in ops.items():
        if not isinstance(entry, dict):
            continue
        patterns = entry.get("deny") or []
        if not isinstance(patterns, list):
            continue
        for pat in patterns:
            if not isinstance(pat, str):
                continue
            for rx in _compile_manifest_deny(pat):
                if rx.search(scan):
                    _deny(
                        _manifest_redirect_reason(
                            op_name, entry.get("skill"), pat
                        ),
                        "manifest:" + str(op_name),
                    )


def _redirect_reason(op, command):
    if op == "dotnet-build":
        return (
            "BUILD QUEUE ENFORCED — use `/msbuild` instead of `dotnet build` directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/msbuild` routes through the queue "
            "automatically.\n"
            "  Correct: /msbuild\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 dotnet build ... — the token must "
            "lead the build's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 "
            "...` prefix is recognized)."
        )
    if op == "dotnet-test":
        # Try to extract a --filter value for the redirect hint.
        m = re.search(r"--filter\s+['\"]?([^'\"]+)['\"]?", command)
        filter_hint = f' -Filter "{m.group(1)}"' if m else ""
        return (
            f"BUILD QUEUE ENFORCED — use `/mstest{filter_hint}` instead of `dotnet test` directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/mstest` routes through the queue "
            "automatically.\n"
            f"  Correct: /mstest{filter_hint}\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 dotnet test ... — the token must "
            "lead the test's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 "
            "...` prefix is recognized)."
        )
    if op == "nx-build":
        return (
            "BUILD QUEUE ENFORCED — use `/nxbuild` instead of running nx build directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/nxbuild` routes through the queue "
            "automatically.\n"
            "  Correct: /nxbuild\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 npx nx build ... — the token must "
            "lead the build's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 "
            "...` prefix is recognized)."
        )
    if op == "nx-test":
        return (
            "BUILD QUEUE ENFORCED — use `/nxtest` instead of running nx test directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/nxtest` routes through the queue "
            "automatically.\n"
            "  Correct: /nxtest\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 npx nx test ... — the token must "
            "lead the test's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 "
            "...` prefix is recognized)."
        )
    if op == "filtered-build":
        return (
            "BUILD QUEUE ENFORCED — use `/msbuild` or `/nxbuild` instead of invoking "
            "*-filtered.ps1 directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. The skills route through the queue "
            "automatically.\n"
            "  Correct: /msbuild (backend) or /nxbuild (frontend)\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ... — the token must lead the "
            "build's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 ...` "
            "prefix is recognized)."
        )
    if op == "filtered-test":
        return (
            "BUILD QUEUE ENFORCED — use `/mstest` or `/nxtest` instead of invoking "
            "*-filtered.ps1 directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. The skills route through the queue "
            "automatically.\n"
            "  Correct: /mstest (backend) or /nxtest (frontend)\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ... — the token must lead the "
            "test's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 ...` "
            "prefix is recognized)."
        )
    return (
        "BUILD QUEUE ENFORCED — use the appropriate skill (/msbuild, /mstest, /nxbuild, /nxtest) "
        "instead of running the build command directly.\n"
        "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ... — the token must lead the "
        "build's own command segment (a `cd \"...\" && BUILD_QUEUE_BYPASS=1 ...` "
        "prefix is recognized)."
    )


def _classify_filtered_script(command):
    """Return 'filtered-build' or 'filtered-test' based on the matched script name."""
    lower = command.lower()
    if "test-filtered" in lower or "client-test-filtered" in lower:
        return "filtered-test"
    return "filtered-build"


def _classify_nx(command):
    """Return 'nx-build' or 'nx-test' based on target in the matched nx command."""
    lower = command.lower()
    # run-many with explicit --target
    m = re.search(r"--target[= ]\s*(build|test)", lower)
    if m:
        return "nx-build" if m.group(1) == "build" else "nx-test"
    # direct nx build/test
    if re.search(r"(?:npx\s+)?nx\s+test\b", lower):
        return "nx-test"
    return "nx-build"


def main():
    global _EVT_CWD
    raw = sys.stdin.read()
    payload = json.loads(raw)
    # D2: capture the tool-call cwd for hook-event repo attribution.
    _EVT_CWD = payload.get("cwd") or ""
    if payload.get("tool_name", "") not in COMMAND_TOOL_NAMES:
        _allow()
    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        _allow()
    command = _normalize_ps_syntax(command)

    # L6 bypass token — allow immediately.
    if _BYPASS_RE.match(command):
        _allow()

    # D7 platform gate — workstation-only v1; silently inert off-Windows.
    if not _workstation_armed():
        _allow()

    cwd = payload.get("cwd") or os.getcwd()

    # D4 scope gate — manifest presence is the PRIMARY gate.
    toplevel = _git_toplevel(cwd)
    manifest, manifest_err = (None, None)
    if toplevel:
        manifest, manifest_err = _load_manifest(toplevel)

    # Allow the sanctioned wrapper before either deny surface — it carries a
    # filtered-script path as its -Exec arg, which would otherwise trip the
    # script-invocation denies.
    if _WRAPPER_RE.search(command):
        _allow()

    if manifest is not None:
        # Manifest-driven deny surface (segment-aware bypass + safe-variant
        # suppression apply exactly as on the legacy path).
        scan = _suppress_safe(_suppress_bypassed_segments(command))
        _scan_manifest_ops(manifest, scan, command)
        _allow()

    # No valid manifest. D4-B legacy fallback: only Cognito Forms worktrees
    # keep the hard-coded deny set; everywhere else is fail-open.
    if not _is_cognito_worktree(cwd):
        if manifest_err is not None:
            # Unreadable manifest in a non-Cognito repo: allow + breadcrumb.
            _breadcrumb(
                "build-queue-ops.json unreadable (allowing, repo not "
                f"legacy-gated): {manifest_err}"
            )
        _allow()

    if manifest_err is not None:
        # Broken manifest in a Cognito worktree — enforcement degrades to the
        # legacy deny set (never silently disarms); leave a diagnosable trail.
        _breadcrumb(
            "build-queue-ops.json unreadable in a Cognito worktree — using "
            f"the legacy fallback deny set (D4): {manifest_err}"
        )

    # Suppress bypassed segments (BUILD_QUEUE_BYPASS=1 leading a segment) and
    # the safe dotnet/nx variants per-occurrence, then scan the scratch copy
    # for any surviving heavy build (unanchored). A leading `dotnet restore`
    # no longer masks a trailing `dotnet build`, and a `cd "..." &&
    # BUILD_QUEUE_BYPASS=1 <build>` is recognized as bypassed while a
    # token-less build behind the same prefix still denies.
    scan = _suppress_safe(_suppress_bypassed_segments(command))

    # Deny surface.
    if _DOTNET_BUILD_RE.search(scan):
        _deny(_redirect_reason("dotnet-build", command), "dotnet-build")

    if _DOTNET_TEST_RE.search(scan):
        _deny(_redirect_reason("dotnet-test", command), "dotnet-test")

    if _NX_BUILD_TEST_RE.search(scan):
        _nx_op = _classify_nx(command)
        _deny(_redirect_reason(_nx_op, command), _nx_op)

    if _FILTERED_SCRIPT_DIRECT_RE.search(scan) or _FILTERED_SCRIPT_POWERSHELL_RE.search(scan):
        _f_op = _classify_filtered_script(command)
        _deny(_redirect_reason(_f_op, command), _f_op)

    _allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

# BQE_SCRIPTS_DIR is threaded via env (D2) so the inline appender can import
# lazy_core for the keyed hook-events append.
BQE_SCRIPTS_DIR="$BQE_SCRIPTS_DIR" "$PYTHON" -c "$_BQE_PY"
exit 0
