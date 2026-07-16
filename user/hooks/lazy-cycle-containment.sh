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
# Python resolution: python3 preferred (WSL / Linux), falling back to python
# (Windows git-bash where python3 may not be on PATH).
#
# Test override: LAZY_CYCLE_STAGED_PATHS (newline-separated) substitutes for
# `git diff --cached --name-only` so the 2nd-feature tripwire is hermetically
# testable without a temp git repo.

# multi-repo-concurrent-runs (Phase 2 / WU-2.3): the cycle marker
# (lazy-cycle-active.json) is now per-repo, a sibling of the run marker in the
# SAME keyed subdir (~/.claude/state/<repo-key>/) when LAZY_STATE_DIR is unset.
# The embedded Python resolves MARKER repo-aware via lazy_core.claude_state_dir()
# after binding the active repo to the PreToolUse cwd — repo_key derivation lives
# ONLY in Python (bash never re-derives it). When LAZY_STATE_DIR IS set (hermetic
# tests) the override dir is used exactly, preserving every existing pipe-test.
#
# We do NOT force-export LAZY_STATE_DIR here: the embedded Python must SEE whether
# it was genuinely set vs unset (set → exact dir; unset → keyed). We pass the
# scripts dir so the Python can import lazy_core, plus a fallback base dir for the
# breadcrumb path if the import is unavailable.
LCC_BASE_DIR="${LAZY_STATE_DIR:-$HOME/.claude/state}"
MARKER="$LCC_BASE_DIR/lazy-cycle-active.json"  # fallback path for early failures

# Resolve the scripts dir relative to this hook's own directory so the embedded
# Python can import lazy_core for the keyed state-dir resolution. Builtins only
# (${0%/*}, cd, pwd) — `dirname` is not guaranteed on PATH for non-login git-bash.
# $0 may carry Windows backslashes; normalize to forward slashes first.
SELF="${0//\\//}"
case "$SELF" in
  */*) LCC_SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   LCC_SCRIPT_DIR="$(pwd)" ;;
esac
LCC_SCRIPTS_DIR="$LCC_SCRIPT_DIR/../scripts"

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
  # No python at all → fail open (exit 0, no output). guard-fail-open-leaves-no-trace
  # CONFIRMED DEFECT (b): this breadcrumb previously targeted the unset $STATE_DIR
  # — that name exists ONLY inside the inline Python body below; the bash-scope
  # base dir var is $LCC_BASE_DIR (set above the python resolution). The write
  # silently landed at the filesystem root (or failed outright) and was swallowed
  # by `2>/dev/null || true`, so this breadcrumb had never actually worked. Fixed
  # to use $LCC_BASE_DIR, and extended with the same hook-events.jsonl append the
  # other python-bearing hooks carry (interim copied block per
  # docs/bugs/guard-fail-open-leaves-no-trace D4 — keep the copies in lockstep).
  _HOOK_NOPY_TS="$(date +%s 2>/dev/null || echo 0)"
  mkdir -p "$LCC_BASE_DIR" 2>/dev/null
  printf '{"hook":"lazy-cycle-containment","error":"no python interpreter on PATH","at":"%s"}' \
    "$_HOOK_NOPY_TS" > "$LCC_BASE_DIR/hook-error.json" 2>/dev/null || true
  printf '{"ts":%s,"kind":"error","hook":"lazy-cycle-containment","repo_root":"","signature":"","detail":"no python interpreter on PATH"}\n' \
    "$_HOOK_NOPY_TS" >> "$LCC_BASE_DIR/hook-events.jsonl" 2>/dev/null || true
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
        scripts_dir = os.environ.get("LCC_SCRIPTS_DIR")
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
# _LAZY_BATCH_*_RE / _STATE_PY_INVOKE_RE above. A genuine INVOCATION is either
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
# PowerShell-syntax regex audit (powershell-tool-bypasses-bash-matched-guards):
# env-assignment prefixes differ between shells (`NAME=value` in bash vs
# `$env:NAME='value';` in PowerShell) — _ENV_PREFIX now recognizes both forms
# so a routing-flag invocation prefixed either way is still scoped correctly.
_ENV_PREFIX = (
    r"(?:"
    r"[A-Za-z_][A-Za-z0-9_]*=\S+\s+"
    r"|\$env:[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:'[^']*'|\"[^\"]*\"|\S+)\s*;\s*"
    r")*"
)
_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX

# A PowerShell backtick at end-of-line is a LINE CONTINUATION (the next line is
# part of the SAME logical command) — not a segment boundary. Left unhandled,
# the `\n` in _CMD_START's separator class would wrongly split a continued
# invocation (`cargo build `` + newline + `--release`) into two segments,
# hiding the build from every anchored pattern below. Normalized once in
# main() before any matching: a backtick-newline collapses to a single space.
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")

# PowerShell nesting: `powershell(.exe)?|pwsh ... -Command "..."` executes its
# quoted STRING argument as a command line — a token inside that string is not
# at a top-level segment-start position under the anchors above, so a runaway
# op hidden inside a nested -Command string would otherwise walk past every
# deny below. Purely additive: the tail following the opening quote is
# reappended as a synthetic segment (newline-prefixed, a recognized _CMD_START
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
    _CMD_START + r"/lazy(?:-bug)?-batch(?:-cloud)?\b(?!/)"
)
_LAZY_BATCH_NESTED_RE = re.compile(
    _CMD_START + r"claude\b[^\n;&|]*/lazy(?:-bug)?-batch(?:-cloud)?\b"
)

# Carve-out shared roots: always allowed in a commit even when not under the
# marker's feature dir (these are cross-feature shared state, not a 2nd feature).
CARVE_OUT_PATHS = ("docs/features/queue.json", "docs/features/ROADMAP.md", "CLAUDE.md")

# reference-only-mention false-deny (harden 2026-07,
# docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions):
# a state-script INVOCATION begins a command segment (optionally behind a
# `python`/`python3` interpreter + a path prefix), mirroring
# build-queue-enforce.sh's _CMD_START segment anchoring and the _LAZY_BATCH_*_RE
# anchors above. A `lazy-state.py`/`bug-state.py` token appearing as an ARGUMENT
# to another verb (`git add user/scripts/lazy-state.py`) or inside a commit
# MESSAGE body (`git commit -m "...routes via lazy-state.py --emit-dispatch..."`)
# does NOT begin a command segment and MUST NOT trip the loop-formation deny.
_STATE_PY_TAIL = (
    r"(?:python3?\s+)?(?:[^\s;&|]*[\\/])?(?:lazy-state|bug-state)\.py\b"
)
_STATE_PY_INVOKE_RE = re.compile(_CMD_START + _STATE_PY_TAIL)
# Per-segment anchored form: the command is split on the same separators the
# _CMD_START class recognizes, then each segment is matched from its start
# (absorbing leading whitespace + NAME=value env assignments), so the
# routing-flag check can be scoped to the INVOKING segment only — a routing flag
# mentioned in an unrelated later segment (a commit message) cannot trip it.
_STATE_PY_INVOKE_SEG_RE = re.compile(r"^\s*" + _ENV_PREFIX + _STATE_PY_TAIL)
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

    Matches both layouts the queue produces:
      - ungrouped: docs/(features|bugs)/<feature_id>/...
      - grouped:   docs/(features|bugs)/<group>/<feature_id>/...
    The optional single `(?:[^/]+/)?` group segment plus the trailing `/` anchor
    the (re.escape'd) feature_id as a FULL path segment, so it can never
    partial-match a longer sibling slug. An empty/None feature_id → False (nothing
    owns the path). Multi-level grouping is deliberately out of scope — the queue
    does not produce it (see docs/bugs/lazy-cycle-containment-misparses-grouped-
    feature-paths)."""
    if not feature_id:
        return False
    norm = path.replace("\\", "/")
    return re.search(
        r"docs/(?:features|bugs)/(?:[^/]+/)?" + re.escape(feature_id) + r"/",
        norm,
    ) is not None

# lazy-cycle-containment-lifecycle-patterns-still-unanchored: an anchored
# invocation form for LIFECYCLE_PATTERNS, mirroring _STATE_PY_INVOKE_RE's
# _CMD_START anchoring. Matches either a bare segment-leading token
# (`dev:kill`, `kill-port 3333`) or the token immediately after a recognized
# task-runner verb (`npm run` / `pnpm run` / `yarn run`) — never a mention
# elsewhere in the command (e.g. inside a quoted commit-message body).
_LIFECYCLE_TAIL = (
    r"(?:" + "|".join(re.escape(p) for p in LIFECYCLE_PATTERNS) + r")"
    r"(?=$|[\s;&|)}])"
)
_LIFECYCLE_INVOKE_RE = re.compile(
    _CMD_START + r"(?:(?:npm|pnpm|yarn)\s+run\s+)?" + _LIFECYCLE_TAIL
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
            _sd = os.environ.get("LCC_SCRIPTS_DIR")
            if _sd and _sd not in sys.path:
                sys.path.insert(0, _sd)
            import lazy_core
            try:
                lazy_core.set_active_repo_root(_EVT_CWD or None)
                repo_root = str(lazy_core.active_repo_root() or "")
            except Exception:
                repo_root = _EVT_CWD or ""
            lazy_core.append_hook_event(
                kind, "lazy-cycle-containment", signature, detail,
                repo_root=repo_root,
            )
            return
        except ImportError:
            pass
        import time as _time
        os.makedirs(STATE_DIR, exist_ok=True)
        entry = {
            "ts": _time.time(), "kind": kind,
            "hook": "lazy-cycle-containment",
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
    # D2: the breadcrumb stays byte-identical; the countable history is the
    # additive hook-events line beside it (fail-open, never raises).
    _append_hook_event("error", "", str(err))


def _allow():
    """Fast allow: emit nothing (PreToolUse with no decision = allow)."""
    sys.exit(0)


def _deny(reason, signature="containment-deny"):
    # incident-auto-capture D2: countable deny event (fail-open, additive) —
    # each deny site passes its stable per-trip signature token.
    _append_hook_event("deny", signature, reason)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


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
        # Second-feature tripwire. A path is a 2nd-feature commit iff it is under
        # SOME feature/bug dir (_FEATURE_DIR_RE, used purely as a tree predicate)
        # but NOT a carve-out for THIS feature. _is_carve_out is now the sole
        # group-aware membership authority (keyed on feature_id), so the old buggy
        # `.group(1) != feature_id` comparison — which mis-parsed grouped features
        # — is gone.
        staged = _staged_paths()
        offending = [
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
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — that is expected; the
# variable is populated.  Run python with the captured body via -c so the
# hook's real stdin (the PreToolUse payload) reaches python untouched.
#
# multi-repo-concurrent-runs (Phase 2 / WU-2.3): do NOT force-export
# LAZY_STATE_DIR — the embedded Python must see whether it was genuinely set
# (hermetic test → exact dir) or unset (production → keyed dir via lazy_core).
# LAZY_STATE_DIR (if set in this hook's environment) already passes through to
# the child. We export LCC_SCRIPTS_DIR so the Python can import lazy_core for the
# keyed resolution; the embedded body resolves the keyed marker path itself.
LCC_SCRIPTS_DIR="$LCC_SCRIPTS_DIR" "$PYTHON" -c "$_LCC_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
