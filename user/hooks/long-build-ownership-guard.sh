#!/bin/bash
# long-build-ownership-guard.sh — PreToolUse(Bash) hook
# (long-build-and-runtime-ownership, Phase 3 / WU-1; M5 Prevent / LD4).
#
# THE M5-PREVENT REQUEST-TIME GUARD. A long build (`tauri build`,
# `cargo build --release`, `npm run build`) backgrounded from inside a dispatched
# cycle subagent DIES when that subagent's turn ends — its process tree is torn
# down with the turn, leaving no artifact and no error. This guard redirects
# exactly those long-build signatures to ORCHESTRATOR ownership so the build runs
# under controller supervision and survives a subagent tear by construction. It
# is the long-build analog of the existing lazy-cycle-containment deny-set, and a
# sibling of block-noncanonical-blocker-write.sh in the fail-OPEN guard family.
#
# RULE: deny a Bash command that contains an EXACT long-build binary invocation
# ANYWHERE in it (not only at the start), so a build chained behind a leading
# command — `cd "..." && cargo build --release`, a pipeline, a `;`-chain — is
# still caught:
#   * `tauri build`
#   * `cargo build --release`
#   * `npm run build`
#   * `npm run qg -- {rust,ts,sidecar}` (and the `quality-gate` alias) — the
#     heavy AlgoBooth quality gates (qg-rust = Rust build+clippy+fmt+test,
#     ~5-10 min; qg-ts = vue-tsc+eslint+vitest+vite build, ~4-6 min; qg-sidecar
#     = the heavy sidecar gate). These exceed a single subagent turn exactly
#     like the packaged builds and die the same way when backgrounded from a
#     cycle subagent (the qg-rust queue wrapper orphans cargo + leaves a stale
#     active.lock; a bare qg-ts vite build simply vanishes) — so they are
#     orchestrator-owned too. The fast qg groups (`arch`, `docs`, `lint`, …) are
#     deliberately NOT matched (enumerated heavy targets only — the guard's
#     near-zero-false-positive charter, D1).
# On match → DENY with a corrective reason naming the orchestrator-takeover
# signature LONG-BUILD-OWNERSHIP-TAKEOVER, so the orchestrator can deterministically
# recognize the redirect and re-launch the build itself (Bash run_in_background
# from the main session). The matcher is scoped to exact long-build binary
# invocations to keep the false-positive rate near zero — it NEVER redirects
# `ls` / `cat` / `npm run lint` / `cargo check --release` (the fast pre-build
# check the long-build rule recommends) / `npm run build:docs`. It is preceded by
# a word boundary so a long-build token glued onto a longer word does not match,
# but it WILL match a real invocation that follows a `cd ... &&`.
#
# QUEUE ROUTING HINT (build-queue-generalization D5, locked 2026-07-09): when
# the repo the command runs in carries a build-queue ops manifest
# (.claude/skill-config/build-queue-ops.json) registering the matched build as
# an op, the deny reason ADDITIONALLY names the op + the queue-wrapper
# invocation the orchestrator's takeover re-launch must use (transient builds
# route THROUGH the queue). Purely additive: the takeover signature and deny
# semantics are unchanged, and a repo without a manifest gets the
# byte-identical legacy message. The hook stays ordered BEFORE
# build-queue-enforce.sh in settings.json (ownership is the more fundamental
# correction; queue routing is the orchestrator's job after takeover).
#
# NOTE on "fail-open block": SPEC §M5 prose says the guard "fail-open blocks
# (exit 2)". In Claude Code a PreToolUse blocks via the JSON
# `permissionDecision: deny` — a non-zero exit is a HARD error, not a soft block.
# So the BLOCK is expressed as a `deny` JSON whose reason names the takeover
# signature; that IS the "fail-open block" in this hook framework, matching every
# sibling guard.
#
# FAIL-OPEN: any parse/match error (malformed JSON, missing python, unexpected
# payload shape) ALLOWS the command — a broken hook must never block legitimate
# work. The contract is fail-OPEN-via-empty-output (exit 0, no decision = allow).
# A best-effort breadcrumb is written to the state dir on an internal error,
# mirroring the sibling guards.
#
# shared-hook-lib (Phase 3): python resolution, the scripts-dir derivation, and
# the no-python breadcrumb are provided by the SOURCED hook-prelude.sh
# (HOOK_PYTHON / HOOK_SCRIPTS_DIR); the allow/deny emitters, the countable
# hook-events append, and the fail-open breadcrumb are provided by hook_lib
# (imported from HOOK_SCRIPTS_DIR by the inline body). The command-segment anchor
# regexes (ENV_PREFIX / CMD_START / PATH_PREFIX) are ALSO consumed from hook_lib —
# their inline copies (the anchor triplication, SPEC D3) are gone. The PS-syntax
# regex audit (_normalize_ps_syntax), the heredoc mask, and the COMMAND_TOOL_NAMES
# tool-name gate stay hook-local and unchanged.

# Source the shared hook prelude, fail-open-guarded (shared-hook-lib SPEC D2).
# A missing/broken prelude ALLOWS (exit 0), never wedges. Derive this hook's own
# directory here ONLY to locate the prelude; the prelude then provides
# HOOK_PYTHON (python3→python resolution; total absence ⇒ pure-bash breadcrumb
# + exit 0 — guard-fail-open-leaves-no-trace §1) and HOOK_SCRIPTS_DIR (the
# sibling user/scripts/ dir). Builtins only ($0 may carry Windows backslashes;
# `dirname` is not guaranteed on a non-login git-bash PATH).
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

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin and emits an allow/deny hookSpecificOutput block (or nothing for a
# fast allow). It NEVER exits non-zero on an internal error.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON
# piped into this hook. With `-c`, the hook's real stdin (the payload) flows
# straight through to python's sys.stdin.
read -r -d '' _LBO_PY <<'PYEOF'
import json
import os
import re
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

_HOOK = "long-build-ownership-guard"

# powershell-tool-bypasses-bash-matched-guards: the harness exposes more than
# one command-execution tool (Bash, PowerShell) sharing the same
# tool_input.command shape. A guard gated on `tool_name == "Bash"` is silently
# bypassed by an equivalent command run through any OTHER member of this set.
# Kept as a hook-local literal (not a shared lazy_core import) so this hook's
# fail-open contract never depends on an external module resolving — the
# identical literal is embedded in lazy-cycle-containment.sh and
# build-queue-enforce.sh; keep the three in lockstep by inspection (and via
# the cross-guard registration meta-test in test_hooks.py) if this set ever
# grows a member.
COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})

# The orchestrator-takeover signature the deny reason MUST name (SSOT; part 5
# consumes the same literal to deterministically recognize the redirect).
TAKEOVER_SIGNATURE = "LONG-BUILD-OWNERSHIP-TAKEOVER"

# Command-position matcher: a long-build invocation that sits at a COMMAND
# position — the start of the string (after optional leading `NAME=value` env
# assignments) OR immediately after a shell command separator (`&&`, `||`, `|`,
# `;`, `(`, `{`, newline, with optional surrounding env assignments). This catches
# a build chained behind a leading command (`cd "..." && cargo build --release`,
# pipelines, `;`-chains) while still NOT matching a long-build token buried inside
# an argument string (e.g. `echo tauri build` — `build` there follows `echo`, not
# a command separator). `npm run build` is matched as a whole token followed by
# end-of-string or whitespace, so `npm run build:docs` / `npm run build-foo` do
# NOT match. `cargo build` REQUIRES `--release` (a plain `cargo build` debug build
# is fast and not redirected; `cargo check --release` is a different verb).
# shared-hook-lib (SPEC D3): CMD_START (built on ENV_PREFIX) and PATH_PREFIX now
# come from hook_lib — the single home of the anchor pair + path prefix that used
# to be hand-copied here and in lazy-cycle-containment.sh / build-queue-enforce.sh.
# The PowerShell-syntax audit that motivated ENV_PREFIX's two-shell shape lives
# with the constant in hook_lib.
#
# long-build-and-build-queue-matcher-bypasses (Fix Scope #1): hook_lib.PATH_PREFIX
# is an optional path prefix so a path-qualified binary token
# (`/abs/path/cargo build --release`) still matches — the same idiom
# `build-queue-enforce.sh` uses for `_FILTERED_SCRIPT_DIRECT_RE`. Purely additive:
# every existing match position is unaffected because both groups are optional.
#
# long-build-and-build-queue-matcher-bypasses (Fix Scope #1): the ORIGINAL
# enumeration only matched the raw binary token itself (`tauri build`,
# `cargo build --release`, `npm run build`) — verified live to walk straight
# past the dominant real-world invocation shapes: a runner-prefixed Tauri
# build (`npx tauri build`, `npm run tauri build` — the CANONICAL form per the
# Tauri docs and AlgoBooth's own scripts — `cargo tauri build`), and a
# path-qualified cargo invocation. The `(?:npx\s+|npm\s+run\s+|cargo\s+)?`
# optional-prefix group enumerates exactly those three runner forms (D1: an
# enumerated allowlist, not a generic "any token before tauri" wildcard, per
# the guard's near-zero false-positive charter) ahead of `tauri\s+build` — this
# ALSO naturally covers bare `tauri build` (prefix group matches nothing) and
# `cargo tauri build` (the `cargo\s+` alternative is shared with the
# `cargo build --release` arm, so no separate `cargo\s+tauri\s+build`
# alternative is needed). The negative space is unchanged: `npm run tauri dev`
# and `cargo tauri dev` fail the mandatory literal `build` after `tauri\s+`;
# `npm run build:docs` fails both the tauri arm (no `tauri` token) and the
# `npm\s+run\s+build(?:\s|$)` arm (the trailing `:` is neither whitespace nor
# end-of-string); a plain debug `cargo build` (no `--release`) fails the
# `cargo\s+build\s+--release` arm outright.
#
# bash -c / sh -c STRING-WRAP RESIDUAL (D2, documented-limitation — see
# `user/hooks/CLAUDE.md` "Known limitation — bash -c / sh -c string-wraps" and
# the sibling note in `build-queue-enforce.sh`): a quoted-string wrap
# (`bash -c "cargo build --release"`) smuggles the build past CMD_START
# because the build token is not a top-level segment start — it sits inside a
# STRING ARGUMENT to `bash`/`sh`, one level of indirection CMD_START
# deliberately does not unwrap (unlike the `powershell/pwsh -Command "..."`
# case, which normalization DOES unwrap — a bash/sh nested-command subscan was
# considered and deferred; see the CLAUDE.md note for the full rationale).
# This is an ACCEPTED, DELIBERATE residual, not an oversight — pinned by
# `test_longbuild_guard_bash_dash_c_wrap_accepted_residual` in test_hooks.py.
# long-build-ownership-guard-misses-qg-gates (Gap 1): the heavy AlgoBooth
# quality gates run as long as the packaged builds and die the same way when a
# cycle subagent backgrounds them (qg-rust orphans cargo + leaves a stale
# active.lock; qg-ts's vite build vanishes) — so they are orchestrator-owned
# too. The `npm\s+run\s+(?:qg|quality-gate)\s+--\s+(?:rust|ts|sidecar)` arm
# enumerates EXACTLY the heavy targets (D1 near-zero-false-positive charter):
# it matches `npm run qg -- rust`, `npm run qg -- ts`, `npm run qg -- sidecar`
# and the `quality-gate` alias, and deliberately does NOT match the fast qg
# groups (`npm run qg -- arch` / `-- docs` / `-- lint`) or a bare `npm run qg`
# with no target. qg-rust/qg-sidecar ALSO carry a build-queue-ops manifest
# entry, so `_queue_routing_hint` additionally names the queue wrapper for them;
# qg-ts is ownership-tracked but not queue-serialized (no manifest op), so it
# gets a plain ownership redirect with no queue hint — both correct.
_LONG_BUILD_RE = re.compile(
    hook_lib.CMD_START + hook_lib.PATH_PREFIX + r"(?:"
    r"(?:npx\s+|npm\s+run\s+|cargo\s+)?tauri\s+build(?:\s|$)"
    r"|cargo\s+build\s+--release(?:\s|$)"
    r"|npm\s+run\s+build(?:\s|$)"
    r"|npm\s+run\s+(?:qg|quality-gate)\s+--\s+(?:rust|ts|sidecar)(?:\s|$)"
    r")"
)

# PowerShell backtick line-continuation: the next physical line is part of the
# SAME logical command — not a segment boundary. Collapsed to a space before
# matching so a continued invocation (`cargo build `` + newline + `--release`)
# is not hidden from _LONG_BUILD_RE by CMD_START's `\n` separator.
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")

# PowerShell nesting: `powershell(.exe)?|pwsh ... -Command "..."` executes its
# quoted STRING argument as a command line — a build hidden inside that string
# is not at a top-level segment-start position under CMD_START. Purely
# additive: the tail following the opening quote is reappended as a synthetic
# newline-prefixed segment so _LONG_BUILD_RE can still find it.
_PS_NESTED_COMMAND_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*?-[Cc]ommand\s+[\"']"
)


def _normalize_ps_syntax(command):
    """Collapse backtick line-continuations and unwrap one level of nested
    `powershell/pwsh -Command "..."` so _LONG_BUILD_RE sees a flat,
    segment-splittable command string. Purely additive/normalizing — never
    narrows what the existing matcher can already detect.

    Indexes against `original` (not the growing `command`) so multiple
    nested matches never slice with stale offsets. The appended tail's
    trailing quote (the -Command string's own closing delimiter) is
    stripped — otherwise a build that is the LAST token before the closing
    quote (`pwsh -Command "cargo build --release"`) fails the build
    pattern's own `(?:\\s|$)` end-of-invocation boundary against a stray
    trailing `"`."""
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
# kill.sh, lazy-cycle-containment.sh, this hook, build-queue-enforce.sh) —
# same lockstep-copy discipline as _normalize_ps_syntax / COMMAND_TOOL_NAMES;
# keep the copies in sync by inspection.
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


def _queue_routing_hint(command, cwd):
    """build-queue-generalization D5 (locked 2026-07-09): transient builds
    route THROUGH the queue. When the repo the command runs in carries a
    build-queue ops manifest registering this build as an op, append a hint
    naming the op + the wrapper invocation the orchestrator's takeover
    re-launch must use. PURELY ADDITIVE to the takeover deny — the
    LONG-BUILD-OWNERSHIP-TAKEOVER signature and deny semantics are unchanged,
    and a repo with no manifest gets the byte-identical legacy message.
    FAIL-OPEN: any error → empty hint."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode != 0:
            return ""
        toplevel = result.stdout.strip()
        if not toplevel:
            return ""
        path = os.path.join(
            toplevel, ".claude", "skill-config", "build-queue-ops.json"
        )
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        ops = manifest.get("ops") if isinstance(manifest, dict) else None
        if not isinstance(ops, dict):
            return ""
        for op_name, entry in ops.items():
            if not isinstance(entry, dict):
                continue
            patterns = entry.get("deny") or []
            if not isinstance(patterns, list):
                continue
            for pat in patterns:
                if not isinstance(pat, str) or not pat.strip():
                    continue
                body = r"\s+".join(re.escape(t) for t in pat.split())
                if re.search(
                    hook_lib.CMD_START + body + r"(?:\s|$)", command, re.IGNORECASE
                ):
                    skill = entry.get("skill") or ""
                    skill_txt = f" (skill: {skill})" if skill else ""
                    return (
                        " QUEUE ROUTING (build-queue-generalization D5): this "
                        f"repo's build-queue ops manifest registers this build "
                        f"as op '{op_name}'{skill_txt} — the orchestrator's "
                        "re-launch must route THROUGH the machine-global "
                        "serializer, i.e. run the queue wrapper "
                        f"(build-queue.ps1 -Op {op_name}) via "
                        "run_transient_build's detached spawn instead of the "
                        "bare build command, gaining serialization + hygiene "
                        "+ the authoritative outcome banner."
                    )
        return ""
    except Exception:
        return ""


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)  # JSONDecodeError → caught below → fail-open
    if payload.get("tool_name", "") not in COMMAND_TOOL_NAMES:
        hook_lib.allow()
    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        hook_lib.allow()
    command = _normalize_ps_syntax(command)
    # Blank heredoc-body interiors (newlines included) so a long-build token
    # sitting at a heredoc-body line start (a commit-message body, an
    # appended log line) cannot fabricate a false segment start (see
    # _mask_heredoc).
    command = _mask_heredoc(command)
    if _LONG_BUILD_RE.search(command):
        # incident-auto-capture D2: countable deny event (fail-open, additive).
        hook_lib.append_hook_event(
            "deny", _HOOK, TAKEOVER_SIGNATURE, command,
            repo_root=payload.get("cwd") or "",
        )
        hook_lib.deny(
            "LONG BUILD REDIRECTED TO ORCHESTRATOR "
            f"[{TAKEOVER_SIGNATURE}]: a long build or heavy gate "
            "(`tauri build` / `cargo build --release` / `npm run build` / "
            "`npm run qg -- {rust,ts,sidecar}`) "
            "backgrounded from inside a cycle subagent DIES when the subagent's "
            "turn ends — its process tree is torn down with the turn, leaving no "
            "artifact and no error. This build is ORCHESTRATOR-OWNED: the main "
            "(non-subagent) session must re-launch it via `Bash run_in_background: "
            "true` and drive it through harness task-tracking so it survives "
            "subagent turn boundaries. Run `cargo check --release` first to surface "
            "compile errors fast before committing to the long build."
            + _queue_routing_hint(command, payload.get("cwd") or "")
        )
    hook_lib.allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 — fail-OPEN on ANY error.
    hook_lib.breadcrumb(_HOOK, exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — that is expected; the
# variable is populated. Run python with the captured body via -c so the hook's
# real stdin (the PreToolUse payload) reaches python untouched. HOOK_SCRIPTS_DIR
# is threaded via env so the inline body can import hook_lib.
HOOK_SCRIPTS_DIR="$HOOK_SCRIPTS_DIR" "$HOOK_PYTHON" -c "$_LBO_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
