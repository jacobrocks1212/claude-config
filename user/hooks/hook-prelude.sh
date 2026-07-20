# hook-prelude.sh — shared, SOURCED (never executed) bash prelude for the
# python-bearing hooks in this directory (shared-hook-lib feature, Phase 1).
#
# Consumed via the fail-open source-site guard, as the FIRST real line of each
# consuming hook (after it has captured stdin and derived its own directory):
#
#     . "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0
#
# A missing/broken prelude ALLOWS (exit 0), never wedges — the sacred
# fail-OPEN invariant. This file is SOURCED, so `exit 0` inside it exits the
# CONSUMING hook (that is intentional: the no-python branch below exits the
# hook cleanly after leaving a breadcrumb).
#
# What it provides to the consuming hook's shell scope:
#   - HOOK_PYTHON        the resolved interpreter (`python3` preferred, then
#                        `python`). On TOTAL absence it writes a pure-bash
#                        breadcrumb (hook-error.json + one hook-events.jsonl
#                        line) and `exit 0`s the hook — the severest failure
#                        class (the entire python-bearing guard plane is dead)
#                        is precisely the one no python-side appender can
#                        record (guard-fail-open-leaves-no-trace §1).
#   - HOOK_SCRIPTS_DIR   the sibling `user/scripts/` directory, derived from the
#                        consuming hook's own path ($0, preserved across
#                        `source`) with builtins only (no `dirname` — a
#                        coreutils binary NOT guaranteed on a non-login
#                        git-bash PATH). This is the `sys.path` seed the
#                        python-bearing hooks pass to `import hook_lib`.
#   - hook_emit_error_event(hook, signature, detail)
#                        a best-effort, printf/`date`-only append of one
#                        {"ts":<int>,"kind":"error",...} line to
#                        hook-events.jsonl PLUS a single-line hook-error.json
#                        overwrite, honoring LAZY_STATE_DIR. No python needed.
#   - HOOK_NAME          the consuming hook's basename sans `.sh` (breadcrumb
#                        identity; derived from $0).
#
# Every function here is best-effort / fail-open. Builtins only on the
# no-python path (printf/echo builtins; `date`/`mkdir` are the only external
# commands and every use is `2>/dev/null` + `|| true`/`|| echo 0`), so the
# breadcrumb still lands (into a pre-existing dir) even with an emptied PATH.

# --- HOOK_NAME: the consuming hook's identity, from $0 (source-preserved) ---
# $0 may carry Windows backslashes (invoked as `bash C:\...\hook.sh`);
# normalize to forward slashes with builtin string ops before splitting.
_HOOK_PRELUDE_SELF="${0//\\//}"
HOOK_NAME="${_HOOK_PRELUDE_SELF##*/}"   # basename
HOOK_NAME="${HOOK_NAME%.sh}"            # strip .sh

# --- hook_emit_error_event: pure-bash JSONL append + hook-error.json ---
# Mirrors lazy_core.append_hook_event's on-disk shape closely enough for
# incident-scan.py to cluster (integer-second `ts` parses as a float-compatible
# number — Open Question 1 resolved). Best-effort: every write is
# `2>/dev/null || true` so a breadcrumb failure never becomes a deny or a
# non-zero exit.
hook_emit_error_event() {
  _hee_hook="$1"
  _hee_sig="$2"
  _hee_detail="$3"
  _hee_base="${LAZY_STATE_DIR:-$HOME/.claude/state}"
  _hee_ts="$(date +%s 2>/dev/null || echo 0)"
  mkdir -p "$_hee_base" 2>/dev/null
  # hook-error.json — the at-a-glance "is a hook broken" file (overwritten).
  printf '{"hook":"%s","error":"%s","at":"%s"}' \
    "$_hee_hook" "$_hee_detail" "$_hee_ts" \
    > "$_hee_base/hook-error.json" 2>/dev/null || true
  # hook-events.jsonl — the countable history incident-scan.py clusters.
  printf '{"ts":%s,"kind":"error","hook":"%s","repo_root":"","signature":"%s","detail":"%s"}\n' \
    "$_hee_ts" "$_hee_hook" "$_hee_sig" "$_hee_detail" \
    >> "$_hee_base/hook-events.jsonl" 2>/dev/null || true
}

# --- HOOK_PYTHON: python3 → python → pure-bash breadcrumb + exit 0 ---
if command -v python3 >/dev/null 2>&1; then
  HOOK_PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  HOOK_PYTHON=python
else
  # No python at all — fail open (exit 0, no output) AFTER leaving a trace.
  # This `exit 0` exits the CONSUMING hook (sourced file, same shell).
  hook_emit_error_event "$HOOK_NAME" "" "no python interpreter on PATH"
  exit 0
fi

# --- HOOK_SCRIPTS_DIR: the sibling user/scripts/ dir, builtins-only ---
# Resolve the consuming hook's own directory from $0 (source-preserved), then
# point at the sibling `../scripts`. `cd`/`pwd` are builtins; `dirname` is not
# guaranteed on PATH under a non-login git-bash (observed: "dirname: command
# not found" → mangled path), so string ops only.
case "$_HOOK_PRELUDE_SELF" in
  */*) _HOOK_PRELUDE_DIR="$(cd "${_HOOK_PRELUDE_SELF%/*}" && pwd)" ;;
  *)   _HOOK_PRELUDE_DIR="$(pwd)" ;;
esac
HOOK_SCRIPTS_DIR="$_HOOK_PRELUDE_DIR/../scripts"
