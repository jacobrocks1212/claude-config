#!/bin/bash
# lazy-cycle-containment.sh — PreToolUse containment hook (lazy-cycle-containment
# C2; recursion/lifecycle re-targeted on agent_id by
# hardening-blind-to-process-friction Phase 1 / D4).
#
# TWO INDEPENDENT TRIPS:
#
# 1. agent_id-targeted (D4 — arming-free, the load-bearing routing/lifecycle trip):
#    a dispatched cycle subagent is EXACTLY the context where the PreToolUse
#    payload carries an `agent_id` field (Claude Code injects it ONLY when the
#    hook fires from within a subagent; it is ABSENT on the main thread —
#    confirmed against the installed version's hook-input schema). So whenever
#    `agent_id` is present this hook DENIES the lifecycle/routing ops a runaway
#    needs to form a loop: a nested /lazy-batch invocation, a /lazy* Skill call,
#    the orchestrator-only lazy-state.py/bug-state.py routing+lifecycle flags,
#    and dev:kill/dev:restart — with NO marker arming required. When `agent_id`
#    is ABSENT (the main-thread orchestrator) all of these are ALLOWED, so the
#    orchestrator is never self-denied (this fixes the Proven-Finding-#3
#    self-deny defect — the orchestrator's own legitimate cycle dispatch +
#    between-cycle lifecycle ops always pass).
#    NOTE (2026-07-09): recursive Agent/Task dispatch is NO LONGER denied — the
#    harness allows nested subagent dispatch, and denying it broke mandated
#    read-only fan-outs (touchpoint-audit-gate). A runaway can't advance the
#    pipeline through plain Agent dispatch alone; the ops above stay denied.
#    See docs/bugs/adhoc-containment-denies-mandated-explore-fanout.
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
# Test override: LAZY_CYCLE_STAGED_PATHS (newline-separated) substitutes for
# `git diff --cached --name-only` so the 2nd-feature tripwire is hermetically
# testable without a temp git repo.
#
# shared-hook-lib (Phase 3): python resolution, the scripts-dir derivation, the
# no-python breadcrumb, AND the pure-bash error breadcrumb (hook_emit_error_event)
# are provided by the SOURCED hook-prelude.sh (HOOK_PYTHON / HOOK_SCRIPTS_DIR /
# HOOK_NAME); the allow/deny emitters, the countable hook-events append, and the
# fail-open breadcrumb are provided by hook_lib (imported from HOOK_SCRIPTS_DIR by
# the inline body). The command-segment anchor pair (ENV_PREFIX / CMD_START) is
# ALSO consumed from hook_lib — the inline copies (the anchor triplication, SPEC
# D3) are gone. The keyed cycle-marker resolution still imports lazy_core directly
# (hook_lib deliberately does NOT re-export claude_state_dir); the PS-syntax audit,
# the heredoc mask, and COMMAND_TOOL_NAMES stay hook-local and unchanged.
#
# multi-repo-concurrent-runs (Phase 2 / WU-2.3): the cycle marker
# (lazy-cycle-active.json) is per-repo, a sibling of the run marker in the SAME
# keyed subdir (~/.claude/state/<repo-key>/) when LAZY_STATE_DIR is unset. The
# embedded Python resolves MARKER repo-aware via lazy_core.claude_state_dir()
# after binding the active repo to the PreToolUse cwd — repo_key derivation lives
# ONLY in Python (bash never re-derives it). When LAZY_STATE_DIR IS set (hermetic
# tests) the override dir is used exactly, preserving every existing pipe-test. We
# do NOT force-export LAZY_STATE_DIR here: the embedded Python must SEE whether it
# was genuinely set vs unset. HOOK_SCRIPTS_DIR is threaded so the Python can import
# both hook_lib and lazy_core.

# Source the shared hook prelude, fail-open-guarded (shared-hook-lib SPEC D2).
# A missing/broken prelude ALLOWS (exit 0), never wedges. Derive this hook's own
# directory here ONLY to locate the prelude; the prelude then provides
# HOOK_PYTHON (python3→python resolution; total absence ⇒ pure-bash breadcrumb
# + exit 0 — guard-fail-open-leaves-no-trace §1), HOOK_SCRIPTS_DIR, HOOK_NAME,
# and hook_emit_error_event. Builtins only ($0 may carry Windows backslashes;
# `dirname` is not guaranteed on a non-login git-bash PATH).
SELF="${0//\\//}"
case "$SELF" in
  */*) _HOOK_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   _HOOK_DIR="$(pwd)" ;;
esac
. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0

# shared-hook-lib (SPEC D2): if hook_lib is unavailable in the scripts dir, leave
# a prelude-side trace (hook_emit_error_event — the shared pure-bash breadcrumb)
# and fail OPEN. This restores the "leave a trace even when the shared module is
# unavailable" property the pre-migration inline lazy_core fallback carried; the
# inline body's `except ImportError: sys.exit(0)` stays the silent last-resort for
# a present-but-unimportable hook_lib.
if [ ! -f "$HOOK_SCRIPTS_DIR/hook_lib.py" ]; then
  hook_emit_error_event "$HOOK_NAME" "" "hook_lib.py not found in scripts dir"
  exit 0
fi

# All deny/allow logic + commit_tally mutation lives in this inline Python.
# It reads the PreToolUse JSON from stdin and emits an allow/deny
# hookSpecificOutput block (or nothing for a fast allow).  It NEVER exits
# non-zero on an internal error: a PreToolUse non-zero exit is a hard blocking
# error in Claude Code, so the contract is fail-OPEN-via-empty-output.
#
# windows-32k-cmdline-e2big-silently-disarms-containment: the Python body is
# handed to the interpreter via a `mktemp`'d TEMP FILE, NOT `-c "$_LCC_PY"`.
# The body is large; on Windows (Git Bash -> native python.exe) a `-c`
# invocation this large exceeds CreateProcess's 32,767-char command-line
# limit, so the process silently fails to spawn (E2BIG) and the hook falls
# through to its unconditional `exit 0` -- the containment guard is disarmed
# with NO trace. Writing the body to a temp file keeps the invoked command
# line short (interpreter + one path) regardless of body size.
#
# The PreToolUse JSON payload STAYS ON STDIN (it is never written into the
# temp file, and the temp file's path is never fed on stdin): a heredoc-bound
# stdin would swallow the payload the embedded body reads via
# `sys.stdin.read()` below, so python is invoked as `python <tmpfile>` with
# the hook's real stdin flowing straight through untouched -- the same
# stdin-preservation the old `-c` form provided.
read -r -d '' _LCC_PY <<'PYEOF'
import json
import os
import re
import sys

# shared-hook-lib (SPEC D2): seed sys.path from HOOK_SCRIPTS_DIR (threaded via
# env) and import hook_lib for the allow/deny emitters, the countable
# hook-events append, the fail-open breadcrumb, AND the shared command-segment
# anchor pair (ENV_PREFIX / CMD_START — the anchor triplication collapse, SPEC
# D3). A missing/failed import must ALLOW, never wedge — the ONLY retained inline
# fallback is this minimal `except ImportError: sys.exit(0)` (the bash guard above
# writes the prelude-side trace for the file-absent case).
try:
    _sd = os.environ.get("HOOK_SCRIPTS_DIR")
    if _sd and _sd not in sys.path:
        sys.path.insert(0, _sd)
    import hook_lib
except ImportError:
    sys.exit(0)

_HOOK = "lazy-cycle-containment"

# powershell-tool-bypasses-bash-matched-guards: the harness exposes more than
# one command-execution tool (Bash, PowerShell) sharing the same
# tool_input.command shape. A guard gated on `tool_name == "Bash"` is silently
# bypassed by an equivalent command run through any OTHER member of this set.
# Kept as a hook-local literal (not a shared lazy_core import) so this hook's
# fail-open contract never depends on an external module resolving — the
# identical literal is embedded in long-build-ownership-guard.sh and
# build-queue-enforce.sh; keep the three in lockstep by inspection (and via
# the cross-guard registration meta-test in test_hooks.py) if this set ever
# grows a member.
COMMAND_TOOL_NAMES = frozenset({"Bash", "PowerShell"})

# Breadcrumb base dir: the un-keyed base (or the LAZY_STATE_DIR override). The
# breadcrumb is a best-effort diagnostic and stays at the base — it never needs
# repo-keying. multi-repo-concurrent-runs (Phase 2 / WU-2.3): MARKER, by
# contrast, is resolved REPO-AWARE in main() once the PreToolUse cwd is known
# (see _resolve_marker_path) — the cycle marker is a sibling of the run marker
# in the per-repo keyed subdir when LAZY_STATE_DIR is unset.
STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)
# MARKER starts at the base (fallback for any pre-resolution failure) and is
# re-bound to the keyed path in main() after the cwd is parsed.
MARKER = os.path.join(STATE_DIR, "lazy-cycle-active.json")


def _resolve_marker_path(cwd):
    """Return the cycle-marker path for the current repo.

    multi-repo-concurrent-runs (Phase 2 / WU-2.3): the cycle marker lives in the
    SAME keyed state subdir as the run marker. Resolution mirrors
    lazy_core.claude_state_dir() EXACTLY — repo_key derivation lives ONLY in
    Python (this never re-implements it in bash):
      - LAZY_STATE_DIR set (hermetic tests) → use it exactly (no keying), so
        every existing pipe-test path is byte-for-byte unchanged.
      - LAZY_STATE_DIR unset (production) → import lazy_core, bind the active
        repo to `cwd`, and ask claude_state_dir(create=False) for the keyed dir.
    Fail-OPEN: if lazy_core cannot be imported / resolved, fall back to the base
    (un-keyed) path. A wrong marker path only weakens the marker-gated commit
    tripwires for one event; the load-bearing agent_id recursion trip does not
    consult the marker, so containment is never broken by a resolution miss.
    """
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
        return MARKER  # base-dir fallback (fail-open)

CORRECTIVE = (
    "you are a single cycle subagent — STOP after your commit+push+report; "
    "routing the next cycle is the orchestrator's job. This op "
    "(lazy-state.py routing/lifecycle, dev:kill/restart, a /lazy* skill or "
    "nested batch invocation, or a second-feature/over-ceiling commit) is "
    "DENIED in-flight while a cycle dispatch is active."
)

# cycle-containment-allows-background-subagent-dispatch-deadlock: a cycle
# subagent must dispatch sub-agents SYNCHRONOUSLY (foreground) and await their
# return. A background (run_in_background: true) Agent/Task dispatch then blocks
# on a child->parent SendMessage that can NEVER arrive (backgrounded children
# reach only the MAIN thread, not their dispatching parent subagent), deadlocking
# the cycle. Synchronous/foreground Agent/Task dispatch stays ALLOWED (the
# 2026-07-09 decision preserving mandated read-only Explore fan-outs).
BACKGROUND_CORRECTIVE = (
    "a cycle subagent must dispatch sub-agents SYNCHRONOUSLY (foreground) and "
    "await their return. A background (run_in_background: true) Agent/Task "
    "dispatch blocks on a child->parent message that can never arrive "
    "(backgrounded children reach only the main thread), deadlocking the cycle. "
    "Re-dispatch WITHOUT run_in_background."
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

# lazy-cycle-containment-lifecycle-patterns-still-unanchored: LIFECYCLE_PATTERNS
# used to be matched via unanchored `pat in command` — a subagent commit whose
# MESSAGE BODY merely mentions e.g. `dev:kill` as prose (`git commit -m "docs:
# explain the npm run dev:kill teardown behavior"`) was wrongly denied, the
# same reference-only-mention false-deny class already fixed for
# _LAZY_BATCH_*_RE / _STATE_PY_INVOKE_RE below. A genuine INVOCATION is either
# segment-leading (a bare `dev:kill` / `kill-port 3333` command) OR immediately
# after a recognized task-runner verb (`npm run` / `pnpm run` / `yarn run`) —
# the form the two pinned tests (`npm run dev:kill`, bare `dev:kill`) require
# to keep denying. The trailing lookahead requires whitespace/end/separator
# right after the token so a longer script name (`dev:kill-all`) cannot
# partial-match.

# Command-position anchor (mirrors build-queue-enforce.sh / long-build-ownership-guard.sh):
# a nested batch is a runaway only when the token INVOKES a command — either the
# start of the string, or immediately after a shell separator (`&&`, `||`, `|`,
# `;`, `(`, `{`, newline), with optional leading `NAME=value` env assignments.
# A `lazy-batch*` token appearing as an ARGUMENT to a read verb
# (`cat user/skills/lazy-batch/SKILL.md`, `grep ... lazy-bug-batch/`) does NOT
# begin a command segment and so must NOT trip the recursion deny — this is the
# false-positive fixed in docs/bugs/adhoc-incident-hook-deny-4b767b.
#
# shared-hook-lib (SPEC D3): the segment anchor pair (ENV_PREFIX / CMD_START) now
# comes from hook_lib — the single home of what used to be hand-copied here and in
# the sibling guards. The PowerShell-syntax audit that motivated ENV_PREFIX's
# two-shell shape lives with the constant in hook_lib.

# A PowerShell backtick at end-of-line is a LINE CONTINUATION (the next line is
# part of the SAME logical command) — not a segment boundary. Left unhandled,
# the `\n` in CMD_START's separator class would wrongly split a continued
# invocation (`cargo build `` + newline + `--release`) into two segments,
# hiding the build from every anchored pattern below. Normalized once in
# main() before any matching: a backtick-newline collapses to a single space.
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")

# PowerShell nesting: `powershell(.exe)?|pwsh ... -Command "..."` executes its
# quoted STRING argument as a command line — a token inside that string is not
# at a top-level segment-start position under the anchors above, so a runaway
# op hidden inside a nested -Command string would otherwise walk past every
# deny below. Purely additive: the tail following the opening quote is
# reappended as a synthetic segment (newline-prefixed, a recognized CMD_START
# separator) so the existing anchored patterns can still find it.
_PS_NESTED_COMMAND_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*?-[Cc]ommand\s+[\"']"
)


def _normalize_ps_syntax(command):
    """Collapse backtick line-continuations and unwrap one level of nested
    `powershell/pwsh -Command "..."` so the anchored patterns below see a
    flat, segment-splittable command string. Purely additive/normalizing —
    never narrows what the existing matchers can already detect.

    Indexes against `original` (not the growing `command`) so multiple
    nested matches never slice with stale offsets. The appended tail's
    trailing quote (the -Command string's own closing delimiter) is
    stripped — otherwise an invocation that is the LAST token before the
    closing quote fails a boundary check requiring whitespace-or-end right
    after the matched token."""
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
# kill.sh, this hook, long-build-ownership-guard.sh,
# build-queue-enforce.sh) — same lockstep-copy discipline as
# _normalize_ps_syntax / COMMAND_TOOL_NAMES; keep the copies in sync by
# inspection.
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


# Recursive batch invocation: a dispatched cycle subagent must never start a
# nested /lazy* batch orchestrator (the literal runaway path). Two anchored
# signals (either match = deny):
#   Direct form   — a /lazy(-bug)?-batch(-cloud)? slash-command that BEGINS a
#                   command segment. The `(?!/)` lookahead ensures a
#                   `.../lazy-batch/...` PATH segment (token followed by `/`)
#                   never matches.
#   Nested-spawn  — a headless `claude -p '/lazy-batch …'` runaway, with `claude`
#                   ALSO anchored to a command-segment start so the `.claude/`
#                   path component never false-matches.
_LAZY_BATCH_DIRECT_RE = re.compile(
    hook_lib.CMD_START + r"/lazy(?:-bug)?-batch(?:-cloud)?\b(?!/)"
)
_LAZY_BATCH_NESTED_RE = re.compile(
    hook_lib.CMD_START + r"claude\b[^\n;&|]*/lazy(?:-bug)?-batch(?:-cloud)?\b"
)

# Carve-out shared roots: always allowed in a commit even when not under the
# marker's feature dir (these are cross-feature shared state, not a 2nd feature).
CARVE_OUT_PATHS = ("docs/features/queue.json", "docs/features/ROADMAP.md", "CLAUDE.md")

# reference-only-mention false-deny (harden 2026-07,
# docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions):
# a state-script INVOCATION begins a command segment (optionally behind a
# `python`/`python3` interpreter + a path prefix), mirroring
# build-queue-enforce.sh's CMD_START segment anchoring and the _LAZY_BATCH_*_RE
# anchors above. A `lazy-state.py`/`bug-state.py` token appearing as an ARGUMENT
# to another verb (`git add user/scripts/lazy-state.py`) or inside a commit
# MESSAGE body (`git commit -m "...routes via lazy-state.py --emit-dispatch..."`)
# does NOT begin a command segment and MUST NOT trip the loop-formation deny.
_STATE_PY_TAIL = (
    r"(?:python3?\s+)?(?:[^\s;&|]*[\\/])?(?:lazy-state|bug-state)\.py\b"
)
_STATE_PY_INVOKE_RE = re.compile(hook_lib.CMD_START + _STATE_PY_TAIL)
# Per-segment anchored form: the command is split on the same separators the
# CMD_START class recognizes, then each segment is matched from its start
# (absorbing leading whitespace + NAME=value env assignments), so the
# routing-flag check can be scoped to the INVOKING segment only — a routing flag
# mentioned in an unrelated later segment (a commit message) cannot trip it.
_STATE_PY_INVOKE_SEG_RE = re.compile(r"^\s*" + hook_lib.ENV_PREFIX + _STATE_PY_TAIL)
_SEGMENT_SPLIT_RE = re.compile(r"[\n;&|({]")

# lazy-cycle-containment-misparses-grouped-feature-paths (harden 2026-07):
# _FEATURE_DIR_RE captures ONLY the FIRST path segment after docs/(features|bugs)/.
# For a GROUPED feature (docs/features/audio/<slug>/, docs/features/mixer/<slug>/,
# … — the layout AlgoBooth's queue produces via each item's `spec_dir`) that
# segment is the DOMAIN GROUP ('audio'), NOT the feature slug, so a
# `group(1) == feature_id` comparison NEVER matched a grouped feature's own paths
# and the tripwire false-denied legitimate same-feature commits. The regex is now
# RETAINED ONLY as an "is this path anywhere under the features/bugs tree?"
# predicate; feature membership is decided group-aware by _path_under_feature,
# keyed on the marker's feature_id (the queue item's bare slug), which anchors the
# slug as a FULL path segment whether the feature is grouped (one optional group
# segment) or ungrouped.
_FEATURE_DIR_RE = re.compile(r"docs/(?:features|bugs)/([^/]+)/")


def _path_under_feature(path, feature_id):
    """True iff *path* lies within *feature_id*'s own docs dir, group-aware.

    Matches every layout the queue produces:
      - ungrouped:        docs/(features|bugs)/<feature_id>/...
      - single-level:     docs/(features|bugs)/<group>/<feature_id>/...
      - multi-level:      docs/(features|bugs)/<g1>/<g2>/.../<feature_id>/...
    The zero-or-more `(?:[^/]+/)*` grouping prefix plus the trailing `/` anchor
    the (re.escape'd) feature_id as a FULL path segment at ANY grouping depth, so
    it can never partial-match a longer sibling slug. An empty/None feature_id →
    False (nothing owns the path).

    lazy-batch-parallel-run-harness-gaps gap 6 (harden 2026-07): the queue now
    produces DEEP grouping (e.g. `docs/features/ui/secondary-ui-v2/domains/<slug>/`
    — three grouping segments before the slug). The prior single-optional-segment
    `(?:[^/]+/)?` matched at most one group segment and false-denied a legitimate
    same-feature commit under a deeper group — a regression of the concluded bug
    `lazy-cycle-containment-misparses-grouped-feature-paths`, which had explicitly
    scoped multi-level grouping OUT ("the queue does not produce it"). It does now,
    so the grouping prefix is generalized to zero-or-more."""
    if not feature_id:
        return False
    norm = path.replace("\\", "/")
    return re.search(
        r"docs/(?:features|bugs)/(?:[^/]+/)*" + re.escape(feature_id) + r"/",
        norm,
    ) is not None

# lazy-cycle-containment-lifecycle-patterns-still-unanchored: an anchored
# invocation form for LIFECYCLE_PATTERNS, mirroring _STATE_PY_INVOKE_RE's
# CMD_START anchoring. Matches either a bare segment-leading token
# (`dev:kill`, `kill-port 3333`) or the token immediately after a recognized
# task-runner verb (`npm run` / `pnpm run` / `yarn run`) — never a mention
# elsewhere in the command (e.g. inside a quoted commit-message body).
_LIFECYCLE_TAIL = (
    r"(?:" + "|".join(re.escape(p) for p in LIFECYCLE_PATTERNS) + r")"
    r"(?=$|[\s;&|)}])"
)
_LIFECYCLE_INVOKE_RE = re.compile(
    hook_lib.CMD_START + r"(?:(?:npm|pnpm|yarn)\s+run\s+)?" + _LIFECYCLE_TAIL
)


# incident-auto-capture Phase 1 (D2): the tool-call cwd, captured in main() so
# the event appender can attribute the event to the active repo. Best-effort.
_EVT_CWD = ""


def _allow():
    """Fast allow: emit nothing (PreToolUse with no decision = allow)."""
    hook_lib.allow()


def _deny(reason, signature="containment-deny"):
    # incident-auto-capture D2: countable deny event (fail-open, additive) —
    # each deny site passes its stable per-trip signature token. The event
    # append + the deny JSON both live in hook_lib now (shared-hook-lib D3).
    hook_lib.append_hook_event("deny", _HOOK, signature, reason, repo_root=_EVT_CWD)
    hook_lib.deny(reason)


def _breadcrumb(err):
    """Write a fail-open breadcrumb via hook_lib; never raise."""
    hook_lib.breadcrumb(_HOOK, err)


def _is_truthy_background(val):
    """Return True iff *val* is a truthy background-dispatch flag.

    Accepts the JSON boolean True (the real Agent/Task tool_input shape) and the
    common string encodings ('true'/'1'/'yes'/'on'). Anything else (absent,
    False, '', 'false', 0) is falsy → a synchronous/foreground dispatch."""
    if val is True:
        return True
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return val != 0
    return False


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


# adhoc-incident-hook-deny-057921: the second-feature tripwire below must
# evaluate only the commit's EFFECTIVE PATHSPEC, not the whole staged index —
# a foreign path staged by a concurrent lane in a shared worktree index must
# not false-deny a commit that will not include it. `_commit_pathspecs`
# resolves the explicit pathspec token list for a `git commit` invocation (or
# None when the commit is index-wide: bare, `-a`/`--all`, or any parse
# ambiguity — safe-fallback bias, never a false-ALLOW of a foreign path).
# Flat string scan, same not-a-shell-parser discipline as `_mask_heredoc` /
# `_normalize_ps_syntax` — NOT a real shell tokenizer, but quote-aware enough
# that a `-m '...path-looking text...'` message value is consumed as ONE
# token (never split into stray pathspec-looking fragments by its own
# internal whitespace).
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")

# Option/value pairs that consume the FOLLOWING token as their value (both
# `--opt value` and `--opt=value` forms) — so the value is never mistaken for
# a pathspec token. `-S`/`--gpg-sign` takes an OPTIONAL value in real git; kept
# conservative here (only consumed when the following token is not itself
# option-shaped).
_COMMIT_VALUE_OPTS = frozenset((
    "-m", "--message", "-F", "--file", "-C", "--reuse-message",
    "-c", "--reedit-message", "--author", "--date", "-t", "--template",
    "--fixup", "--squash", "--cleanup", "-S", "--gpg-sign",
))

# Separator chars that end the `git commit` invocation's own segment — mirrors
# `_SEGMENT_SPLIT_RE`'s separator class, but consulted QUOTE-AWARE here (a
# separator char sitting inside a quoted commit-message value must not
# fabricate a false segment boundary).
_COMMIT_SEG_SEPARATOR_CHARS = frozenset("\n;&|({")


def _commit_pathspecs(command):
    """Return the explicit pathspec token list for a `git commit` invocation
    in *command*, or None when the commit is index-wide (bare, `-a`/`--all`,
    or any parse ambiguity — deny-safe: callers fall back to the whole staged
    index on None, never a false-ALLOW of a foreign path).

    Scoped to the `git commit` invocation's own segment (up to the next
    top-level separator, quote-aware) so a later `&&`-chained segment never
    leaks tokens in. Tokenization is a flat, quote-aware whitespace split — a
    single-/double-quoted span (its `-m` message value, typically) is kept as
    ONE token regardless of internal whitespace, so a message that merely
    MENTIONS a path as prose is never split into a spurious pathspec-looking
    fragment. An unterminated quote is a parse ambiguity -> None.
    """
    m = _GIT_COMMIT_RE.search(command)
    if m is None:
        return None
    tail = command[m.end():]

    tokens = []
    buf = []
    quote = None
    for ch in tail:
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch in _COMMIT_SEG_SEPARATOR_CHARS:
            break  # end of this invocation's own command segment
        if ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if quote is not None:
        return None  # unterminated quote -- ambiguous, deny-safe fallback
    if buf:
        tokens.append("".join(buf))

    pathspecs = []
    saw_all = False
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "--":
            pathspecs.extend(t for t in tokens[i + 1:] if t)
            break
        if tok in ("-a", "--all"):
            saw_all = True
            i += 1
            continue
        if tok.startswith("--") and "=" in tok:
            # --opt=value: the value is attached to this one token -- skip it
            # whole, no separate value token to consume.
            i += 1
            continue
        if tok in _COMMIT_VALUE_OPTS:
            if i + 1 < n:
                nxt = tokens[i + 1]
                if tok in ("-S", "--gpg-sign") and nxt.startswith("-"):
                    # optional value not supplied -- don't consume nxt.
                    i += 1
                    continue
                i += 2  # consume the option AND its value token
                continue
            i += 1  # trailing option with no value token at all
            continue
        if tok.startswith("-"):
            i += 1  # an ordinary no-value flag (-q, --amend, --no-verify, ...)
            continue
        pathspecs.append(tok)
        i += 1

    if saw_all:
        return None
    if not pathspecs:
        return None
    return pathspecs


def _commit_effective_paths(command, staged):
    """Return the subset of *staged* the pending `git commit` in *command*
    will actually include -- its effective pathspec -- or *staged* unchanged
    when the commit is index-wide (see `_commit_pathspecs`)."""
    pathspecs = _commit_pathspecs(command)
    if pathspecs is None:
        return staged
    norm_specs = [p.replace("\\", "/").rstrip("/") for p in pathspecs]
    effective = []
    for p in staged:
        norm_p = p.replace("\\", "/")
        for spec in norm_specs:
            if norm_p == spec or norm_p.startswith(spec + "/"):
                effective.append(p)
                break
    return effective


def _is_carve_out(path, feature_id):
    norm = path.replace("\\", "/")
    if norm in CARVE_OUT_PATHS:
        return True
    # The feature's own dir (features OR bugs) is always allowed — group-aware,
    # keyed on the marker's feature_id, so a GROUPED feature's own paths
    # (docs/features/<group>/<feature_id>/…) are correctly recognized as its own.
    return _path_under_feature(norm, feature_id)


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
    global MARKER, _EVT_CWD
    raw = sys.stdin.read()
    payload = json.loads(raw)            # JSONDecodeError → caught → fail-open
    # D2: capture the tool-call cwd for hook-event repo attribution.
    _EVT_CWD = payload.get("cwd", "") or ""
    # multi-repo-concurrent-runs (Phase 2 / WU-2.3): re-bind MARKER to the
    # per-repo keyed path using the PreToolUse cwd BEFORE reading it, so the
    # marker-gated commit tripwires consult THIS repo's cycle marker (a sibling
    # of its run marker). Fail-open: _resolve_marker_path falls back to the base
    # path if lazy_core is unavailable.
    MARKER = _resolve_marker_path(payload.get("cwd", "") or "")
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

    # --- Recursive dispatch: DELIBERATELY NOT DENIED (operator decision 2026-07-09).
    #     The harness DOES allow subagents to dispatch Agent/Task (verified live:
    #     a general-purpose subagent's Agent call reaches this hook), and blanket-
    #     denying it broke legitimate mandated fan-outs (touchpoint-audit-gate's
    #     Explore dispatch — docs/bugs/adhoc-containment-denies-mandated-explore-fanout).
    #     Runaway containment does NOT need it: a runaway cannot advance the
    #     pipeline without lazy-state.py routing/lifecycle ops, /lazy* skills, or
    #     a nested batch invocation — all still denied below. ---

    # --- Skill-tool /lazy* intercept (cycle-subagent-runs-orchestrator-work Phase 3,
    #     defense-in-depth): a subagent must not invoke /lazy* via the Skill tool,
    #     bypassing every Bash/Agent guard. When agent_id is present AND the skill
    #     name matches the lazy family regex → DENY. Fail-OPEN: a missing or
    #     non-string skill name allows (never wedge the pipeline). Main-thread
    #     (agent_id absent) → allow (orchestrator self-invocation is legitimate). ---
    _LAZY_SKILL_RE = re.compile(r"^/?lazy(?:-bug)?(?:-batch)?(?:-cloud)?$")
    if tool_name == "Skill":
        if is_subagent:
            skill_name = (payload.get("tool_input") or {}).get("skill", "") or ""
            if isinstance(skill_name, str) and _LAZY_SKILL_RE.match(skill_name.strip()):
                _deny(CORRECTIVE, "skill-lazy-family")
        # Main-thread or non-lazy skill → allow.
        _allow()

    # --- Background Agent/Task dispatch from a subagent: DENY (deadlock).
    #     cycle-containment-allows-background-subagent-dispatch-deadlock: a cycle
    #     subagent that backgrounds a sub-subagent then blocks on a child->parent
    #     message that can never arrive. Synchronous (foreground) Agent/Task
    #     dispatch stays ALLOWED (the 2026-07-09 Explore-fan-out decision).
    #     Main-thread (agent_id absent) background dispatch is ALLOWED (the main
    #     thread receives child messages; the deadlock is subagent-parent-only). ---
    if is_subagent and tool_name in ("Agent", "Task"):
        ti = payload.get("tool_input") or {}
        if _is_truthy_background(ti.get("run_in_background")):
            _deny(BACKGROUND_CORRECTIVE, "background-dispatch")
        # Foreground Agent/Task from a subagent → allow (fall through).
        _allow()

    if tool_name not in COMMAND_TOOL_NAMES:
        _allow()

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        _allow()
    command = _normalize_ps_syntax(command)
    # Blank heredoc-body interiors (newlines included) so a routing/lifecycle
    # token sitting at a heredoc-body line start (a commit-message body, an
    # appended log line) cannot fabricate a false segment start (see
    # _mask_heredoc).
    command = _mask_heredoc(command)

    if is_subagent:
        # --- Recursive batch invocation (the literal runaway path). ---
        if _LAZY_BATCH_DIRECT_RE.search(command) or _LAZY_BATCH_NESTED_RE.search(command):
            _deny(CORRECTIVE, "lazy-batch-invocation")

        # --- Loop-formation: lazy-state.py / bug-state.py routing flags. ---
        # Match only a REAL invocation (segment-leading), never an incidental
        # filename argument (`git add user/scripts/lazy-state.py`) or a
        # commit-message mention (reference-only-mention false-deny). The
        # routing-flag check is scoped to the INVOKING segment so a routing flag
        # in an unrelated later segment (e.g. a commit message body) cannot trip
        # it.
        if _STATE_PY_INVOKE_RE.search(command):
            for _seg in _SEGMENT_SPLIT_RE.split(command):
                if not _STATE_PY_INVOKE_SEG_RE.match(_seg):
                    continue
                # A narrow ALLOW_LISTED op in this invoking segment is fine.
                if any(flag in _seg for flag in ALLOW_LISTED_FLAGS):
                    continue
                if any(flag in _seg for flag in LOOP_FORMATION_FLAGS):
                    _deny(CORRECTIVE, "loop-formation-flag")
            # A real state-script invocation with no routing flag (a read) → allow.
            _allow()

        # --- Runtime-lifecycle commands. ---
        # lazy-cycle-containment-lifecycle-patterns-still-unanchored: anchored
        # invocation match (segment-leading, or after a task-runner verb) —
        # NOT the old unanchored `pat in command` substring scan, which
        # false-denied a commit message merely mentioning one of these tokens.
        if _LIFECYCLE_INVOKE_RE.search(command):
            _deny(CORRECTIVE, "lifecycle-command")

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
                + CORRECTIVE,
                "commit-count-backstop",
            )
        # lazy-batch-parallel-run-harness-gaps gap 7 (harden 2026-07): a
        # SANCTIONED BATCH docs-writer cycle legitimately spans N features in one
        # commit, so the single-feature_id tripwire must not police it. The only
        # such cycle today is /ingest-research (batch mode writes RESEARCH.md /
        # RESEARCH_SUMMARY.md + clears stub markers across every pending-research
        # feature — docs/features/<slug>/ artifacts only, never source). Keyed on
        # the cycle marker's own sub_skill (set by the --cycle-begin --sub-skill
        # ingest-research bracket — zero orchestrator change). The commit-count
        # backstop above STILL applies (a runaway ingest cannot commit unbounded).
        sub_skill = marker.get("sub_skill")
        _batch_docs_writer = sub_skill in ("ingest-research",)
        # Second-feature tripwire. A path is a 2nd-feature commit iff it is under
        # SOME feature/bug dir (_FEATURE_DIR_RE, used purely as a tree predicate)
        # but NOT a carve-out for THIS feature. _is_carve_out is now the sole
        # group-aware membership authority (keyed on feature_id), so the old buggy
        # `.group(1) != feature_id` comparison — which mis-parsed grouped features
        # — is gone.
        staged = _commit_effective_paths(command, _staged_paths())
        offending = [] if _batch_docs_writer else [
            p for p in staged
            if _FEATURE_DIR_RE.search(p.replace("\\", "/"))
            and not _is_carve_out(p, feature_id)
        ]
        if offending:
            _deny(
                f"second-feature commit tripwire: staged path(s) {offending} are "
                f"under a different feature than the active dispatch ({feature_id!r}). "
                + CORRECTIVE,
                "second-feature-commit",
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
    hook_lib.breadcrumb(_HOOK, exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — that is expected; the
# variable is populated.
#
# windows-32k-cmdline-e2big-silently-disarms-containment: write the captured
# body to a mktemp'd temp file and invoke python against THAT PATH (not `-c`)
# so the spawned command line stays short regardless of body size. Plain
# `mktemp` honors TMPDIR (the standard POSIX seam) so a test can force this
# step to fail by pointing TMPDIR at a non-existent parent. Both the mktemp
# step AND the subsequent write are guarded — either failing takes the SAME
# traced fail-open branch (breadcrumb + hook-events line via the prelude's
# hook_emit_error_event), distinct from the no-python breadcrumb by its
# `detail` text.
_lcc_tmpwrite_failed=0
tmpfile="$(mktemp --suffix=.py 2>/dev/null)"
if [ -z "$tmpfile" ] || [ ! -f "$tmpfile" ]; then
  _lcc_tmpwrite_failed=1
else
  trap 'rm -f "$tmpfile"' EXIT
  if ! printf '%s' "$_LCC_PY" > "$tmpfile" 2>/dev/null; then
    _lcc_tmpwrite_failed=1
  fi
fi

if [ "$_lcc_tmpwrite_failed" = "1" ]; then
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
# multi-repo-concurrent-runs (Phase 2 / WU-2.3): do NOT force-export
# LAZY_STATE_DIR — the embedded Python must see whether it was genuinely set
# (hermetic test → exact dir) or unset (production → keyed dir via lazy_core).
# LAZY_STATE_DIR (if set in this hook's environment) already passes through to
# the child. We export HOOK_SCRIPTS_DIR so the Python can import hook_lib (the
# emitters + append) AND lazy_core (the keyed marker resolution).
HOOK_SCRIPTS_DIR="$HOOK_SCRIPTS_DIR" "$HOOK_PYTHON" "$tmppath"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
