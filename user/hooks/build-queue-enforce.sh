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
# shared-hook-lib (Phase 3): python resolution, the scripts-dir derivation, the
# no-python breadcrumb, AND the pure-bash error breadcrumb (hook_emit_error_event)
# are provided by the SOURCED hook-prelude.sh (HOOK_PYTHON / HOOK_SCRIPTS_DIR /
# HOOK_NAME); the allow/deny emitters, the countable hook-events append, and the
# fail-open breadcrumb are provided by hook_lib (imported from HOOK_SCRIPTS_DIR by
# the inline body). The command-segment anchor regexes (ENV_PREFIX / CMD_START /
# PATH_PREFIX) are ALSO consumed from hook_lib — their inline copies (the anchor
# triplication, incl. the two env-prefix literals kept in lockstep and the three
# inline path-prefix literals, SPEC D3) are gone. The PS-syntax regex audit
# (_normalize_ps_syntax), the heredoc mask, and the COMMAND_TOOL_NAMES tool-name
# gate stay hook-local and unchanged.

# Source the shared hook prelude, fail-open-guarded (shared-hook-lib SPEC D2).
# A missing/broken prelude ALLOWS (exit 0), never wedges. Derive this hook's own
# directory here ONLY to locate the prelude; the prelude then provides
# HOOK_PYTHON (python3→python resolution; total absence ⇒ pure-bash breadcrumb
# + exit 0 — guard-fail-open-leaves-no-trace §1), HOOK_SCRIPTS_DIR (the sibling
# user/scripts/ dir), HOOK_NAME, and hook_emit_error_event. Builtins only ($0 may
# carry Windows backslashes; `dirname` is not guaranteed on a non-login git-bash
# PATH).
SELF="${0//\\//}"
case "$SELF" in
  */*) _HOOK_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   _HOOK_DIR="$(pwd)" ;;
esac
. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0

# shared-hook-lib (SPEC D2): if hook_lib is unavailable in the scripts dir, leave
# a prelude-side trace (hook_emit_error_event — the shared pure-bash breadcrumb)
# and fail OPEN. Restores the "trace even when the shared module is unavailable"
# property the pre-migration inline lazy_core fallback carried; the inline body's
# `except ImportError: sys.exit(0)` is the silent last-resort for a
# present-but-unimportable hook_lib.
if [ ! -f "$HOOK_SCRIPTS_DIR/hook_lib.py" ]; then
  hook_emit_error_event "$HOOK_NAME" "" "hook_lib.py not found in scripts dir"
  exit 0
fi

read -r -d '' _BQE_PY <<'PYEOF'
import json
import os
import re
import subprocess
import sys

# shared-hook-lib (SPEC D2): seed sys.path from HOOK_SCRIPTS_DIR (threaded via
# env) and import hook_lib for the allow/deny emitters, the countable
# hook-events append, the fail-open breadcrumb, AND the shared command-segment
# anchor regexes (ENV_PREFIX / CMD_START / PATH_PREFIX — the anchor triplication
# collapse, SPEC D3). A missing/failed import must ALLOW, never wedge — the ONLY
# retained inline fallback is this minimal `except ImportError: sys.exit(0)`.
try:
    _sd = os.environ.get("HOOK_SCRIPTS_DIR")
    if _sd and _sd not in sys.path:
        sys.path.insert(0, _sd)
    import hook_lib
except ImportError:
    sys.exit(0)

_HOOK = "build-queue-enforce"

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

# The bypass token is recognized in EITHER shell's env-assignment form, with an
# optional leading env-prefix (either form, repeated) before it. shared-hook-lib
# (SPEC D3): the env-prefix now comes from hook_lib.ENV_PREFIX — the single home
# of the anchor pair that used to be hand-copied here (as BOTH _ENV_PREFIX_ANY
# and _ENV_PREFIX, which the old file kept "in lockstep by inspection") and in
# the sibling guards.
_BYPASS_TOKEN_RE = (
    r"(?:BUILD_QUEUE_BYPASS=1(?:\s|$)"
    r"|\$env:BUILD_QUEUE_BYPASS\s*=\s*(?:'1'|\"1\"|1)\s*;?)"
)
# Match the bypass token as a leading env assignment. Applied to the whole
# command (fast-path allow) AND per segment via _suppress_bypassed_segments.
_BYPASS_RE = re.compile(r"^\s*" + hook_lib.ENV_PREFIX + _BYPASS_TOKEN_RE)

# Shell separators that begin a new command segment (mirrors CMD_START's
# character class). Splitting on these yields per-segment strings _BYPASS_RE
# can be matched against, so the bypass token is recognized when it leads the
# build's own segment behind a `cd "..." && ` (or `;`/pipeline) prefix.
_SEGMENT_SPLIT_RE = re.compile(r"([\n;&|({])")

# Match the sanctioned wrapper — allow before any deny-check.
#
# long-build-and-build-queue-matcher-bypasses (Fix Scope #2): this used to be
# an UNANCHORED substring match over the whole command
# (`re.compile(r"build-queue\.ps1")`), checked BEFORE either deny surface —
# so ANY command merely *mentioning* the wrapper filename anywhere (an echo,
# a grep, a comment string, a path argument in an unrelated later segment)
# was fully exempt from the deny surface the rest of this hook painstakingly
# anchors. Verified live: `echo build-queue.ps1; dotnet build MySln.sln` and
# `grep foo build-queue.ps1 && dotnet build MySln.sln` both wrongly ALLOWed.
# Replaced with the SAME invoke-vs-reference discrimination the deny surface
# already uses (mirrors `_FILTERED_SCRIPT_DIRECT_RE` / `_FILTERED_SCRIPT_POWERSHELL_RE`
# below) — two anchored forms, either match = allow:
#   (a) a command-segment-start invocation whose token path ends in
#       `build-queue.ps1` (hook_lib.CMD_START + hook_lib.PATH_PREFIX).
#   (b) the `powershell(.exe)?|pwsh ... -File <path>build-queue.ps1` form (this
#       is the sanctioned skills' real invocation shape — see
#       `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md`
#       — and was ALREADY anchored correctly by construction: `-File` requires
#       an adjacent path argument, not a bare mention).
# `echo build-queue.ps1; dotnet build` now correctly DENIES on the second
# segment (the `echo` segment matches neither form).
_WRAPPER_DIRECT_RE = re.compile(
    hook_lib.CMD_START
    + hook_lib.PATH_PREFIX + r"build-queue\.ps1(?:\s|$|\")",
    re.IGNORECASE,
)
_WRAPPER_POWERSHELL_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*-File\s+\S*build-queue\.ps1",
    re.IGNORECASE,
)

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

# PowerShell backtick line-continuation: the next physical line is part of the
# SAME logical command — not a segment boundary. Collapsed to a space before
# the deny scan so a continued invocation (`dotnet build `` + newline +
# `Cognito.sln`) is not hidden from the anchored patterns below by
# CMD_START's `\n` separator.
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")

# PowerShell nesting: `powershell(.exe)?|pwsh ... -Command "..."` executes its
# quoted STRING argument as a command line — a heavy build hidden inside that
# string is not at a top-level segment-start position under CMD_START.
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


# block-terminal-kill-false-denies-heredoc-body-tokens: a heredoc body
# (`<<WORD` / `<< 'WORD'` / `<<"WORD"` / `<<-WORD` introducer through its
# terminator line) is inert DATA — file/message CONTENT, never executed —
# but its interior newlines satisfy CMD_START's `\n` segment-separator
# class exactly like a real command boundary, so a deny token sitting at
# the start of a body line (e.g. a commit-message body, an appended log
# line) fabricates a false command-segment start and false-denies a
# completely benign command. THIRD variant of the same false-deny class
# (1: bare word-boundary → segment-start anchoring; 2: quoted-argument
# values → _mask_quoted; 3: this — heredoc bodies). Kept as an identical
# hook-local copy across every CMD_START-anchored guard (block-terminal-
# kill.sh, lazy-cycle-containment.sh, long-build-ownership-guard.sh, this
# hook) — same lockstep-copy discipline as _normalize_ps_syntax /
# COMMAND_TOOL_NAMES; keep the copies in sync by inspection.
_HEREDOC_INTRODUCER_RE = re.compile(
    r"<<(-)?[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|([^\s'\"<>|;&()]+))"
)


def _mask_heredoc(command):
    """Blank the INTERIOR of every heredoc body, offsets preserved.

    A flat single-pass scan over `re.finditer` matches on the *original*
    command (never a shell parser, same discipline as _mask_quoted /
    _normalize_ps_syntax): each introducer resolves to a body span
    `[body_start, body_end)` via the first terminator-shaped line found
    at-or-after it. Unlike _mask_quoted (which keeps interior "\n" so a
    multi-line quoted span still contributes real segment boundaries
    elsewhere), this blanks EVERY interior char of the body -- INCLUDING
    its newlines -- to a single space: the false segment starts this bug
    fixes ARE the body's own newlines, so they must stop being newlines.
    The introducer line and the terminator WORD line itself are left
    untouched, so a real deny token chained AFTER the terminator line (a
    genuine top-level segment start) is outside the masked span and still
    denies.

    A `<<-WORD` introducer allows the terminator line to carry leading
    tabs/spaces (real bash `<<-` semantics); a plain `<<WORD` terminator
    must start the line with no leading whitespace. A later introducer
    match that falls INSIDE an already-masked span (a `<<`-looking token
    inside masked body text) is skipped -- that text is already inert. An
    unterminated heredoc (no terminator line before end-of-string) masks
    through end-of-string -- conservative, never a crash.
    """
    out = list(command)
    consumed_until = 0
    for m in _HEREDOC_INTRODUCER_RE.finditer(command):
        if m.start() < consumed_until:
            continue  # inside an already-masked body -- inert, skip
        word = m.group(2)
        if word is None:
            word = m.group(3)
        if word is None:
            word = m.group(4)
        if not word:
            continue  # empty/degenerate delimiter -- nothing to anchor on
        nl = command.find("\n", m.end())
        if nl == -1:
            continue  # introducer with no body at all
        body_start = nl + 1
        if m.group(1) is not None:  # `<<-WORD` -- leading ws stripped
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


# Deny patterns. Run against the SUPPRESSED command (safe variants blanked out).
_DOTNET_BUILD_RE = re.compile(hook_lib.CMD_START + r"dotnet\s+build(?:\s|$)", re.IGNORECASE)
_DOTNET_TEST_RE = re.compile(hook_lib.CMD_START + r"dotnet\s+test(?:\s|$)", re.IGNORECASE)
# nx / npx nx with build, test, or run-many target.
# Matches: nx build X, nx test X, nx run-many --target=build/test,
#          npx nx build X, npx nx test X, npx nx run-many --target=build/test
_NX_BUILD_TEST_RE = re.compile(
    hook_lib.CMD_START + r"(?:npx\s+)?nx\s+"
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
    hook_lib.CMD_START
    + hook_lib.PATH_PREFIX
    + r"(?:build-filtered|test-filtered|client-build-filtered|client-test-filtered)\.ps1"
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


def _allow():
    hook_lib.allow()


def _deny(reason, signature="build-queue-enforced"):
    # incident-auto-capture D2: countable deny event (fail-open, additive) —
    # each deny site passes its classified op as the signature. The event
    # append + the deny JSON both live in hook_lib now (shared-hook-lib D3).
    hook_lib.append_hook_event("deny", _HOOK, signature, reason, repo_root=_EVT_CWD)
    hook_lib.deny(reason)


def _breadcrumb(err):
    hook_lib.breadcrumb(_HOOK, err)


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
    anchored at hook_lib.CMD_START — the invoke-vs-reference discrimination the
    Cognito denies already carry. Returns a list of compiled regexes
    (empty for a blank/unusable pattern)."""
    p = (pattern or "").strip()
    if not p:
        return []
    if p.lower().endswith(".ps1"):
        name = re.escape(os.path.basename(p.replace("\\", "/")))
        direct = re.compile(
            hook_lib.CMD_START
            + hook_lib.PATH_PREFIX + name + r"(?:\s|$|\")",
            re.IGNORECASE,
        )
        psfile = re.compile(
            r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*-File\s+\S*" + name,
            re.IGNORECASE,
        )
        return [direct, psfile]
    body = r"\s+".join(re.escape(tok) for tok in p.split())
    return [re.compile(hook_lib.CMD_START + body + r"(?:\s|$)", re.IGNORECASE)]


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
    # Blank heredoc-body interiors (newlines included) so a build-queue-gated
    # token sitting at a heredoc-body line start (a commit-message body, an
    # appended log line) cannot fabricate a false segment start (see
    # _mask_heredoc).
    command = _mask_heredoc(command)

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
    if _WRAPPER_DIRECT_RE.search(command) or _WRAPPER_POWERSHELL_RE.search(command):
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
    hook_lib.breadcrumb(_HOOK, exc)
    sys.exit(0)
PYEOF

# windows-32k-cmdline-e2big-silently-disarms-containment: write the captured
# body to a mktemp'd temp file and invoke python against THAT PATH (not `-c`)
# so the spawned command line stays short regardless of body size. Plain
# `mktemp` honors TMPDIR (the standard POSIX seam) so a test can force this
# step to fail by pointing TMPDIR at a non-existent parent. Both the mktemp
# step AND the subsequent write are guarded — either failing takes the SAME
# traced fail-open branch (breadcrumb + hook-events line via the prelude's
# hook_emit_error_event), distinct from the no-python breadcrumb by its
# `detail` text.
_bqe_tmpwrite_failed=0
tmpfile="$(mktemp --suffix=.py 2>/dev/null)"
if [ -z "$tmpfile" ] || [ ! -f "$tmpfile" ]; then
  _bqe_tmpwrite_failed=1
else
  trap 'rm -f "$tmpfile"' EXIT
  if ! printf '%s' "$_BQE_PY" > "$tmpfile" 2>/dev/null; then
    _bqe_tmpwrite_failed=1
  fi
fi

if [ "$_bqe_tmpwrite_failed" = "1" ]; then
  # Traced fail-open (guard-fail-open-leaves-no-trace): the prelude's shared
  # pure-bash breadcrumb, with a DISTINCT detail string so this temp-write
  # cause is distinguishable from the no-python cause in
  # hook-error.json / hook-events.jsonl.
  hook_emit_error_event "$HOOK_NAME" "" "temp-file write failed"
  exit 0
fi

# Windows Git Bash's `/tmp/...` MSYS path may not resolve for a native
# python.exe — convert to a Windows path when `cygpath` is available (a no-op
# elsewhere: WSL/Linux/macOS python reads the raw path fine, and `cygpath`
# simply won't be on PATH there).
if command -v cygpath >/dev/null 2>&1; then
  tmppath="$(cygpath -w "$tmpfile")"
else
  tmppath="$tmpfile"
fi

# Invoke python against the temp-file PATH, not `-c`. The hook's real stdin
# (the PreToolUse payload) still flows straight through to python's
# sys.stdin — nothing pipes into this invocation on stdin, so it is
# untouched, exactly as the old `-c` form preserved it.
#
# HOOK_SCRIPTS_DIR is threaded via env so the inline body can import hook_lib
# for the emitters + the keyed hook-events append.
HOOK_SCRIPTS_DIR="$HOOK_SCRIPTS_DIR" "$HOOK_PYTHON" "$tmppath"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
