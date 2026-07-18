# lazy-cycle-containment.sh inline python exceeds the Windows command-line limit → silent fail-open (guard disarmed)

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-18
**Related:** `docs/bugs/guard-fail-open-leaves-no-trace` (E2BIG slips between that fix's "no-python"
and python-catch-all breadcrumb sites — a NEW untraced fail-open class); `user/hooks/CLAUDE.md`
→ "Fail-OPEN is mandatory" / "Fail-open observability". Discovered incidentally by
`/harden-harness` Round 95 while running the `test_hooks.py` gate for
`adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker`.

## Trigger

Running `python user/scripts/test_hooks.py` yields 22 `test_containment_*` failures on this
Windows workstation (DESKTOP-GHTC5K6): every test that writes a cycle marker and expects the
`lazy-cycle-containment.sh` hook to DENY instead sees empty stdout (fast-path allow). NOT caused
by the live cycle marker (fails identically with an isolated `LAZY_STATE_DIR`) and NOT by env
bloat (total env is ~3.7KB).

## Reproduction Steps

1. `python user/scripts/test_hooks.py` → `226/248 passed, 22 failed`, all `test_containment_*`.
2. Drive the hook directly: write a `lazy-cycle-active.json` cycle marker into a temp state dir
   and pipe a subagent PreToolUse payload into `bash user/hooks/lazy-cycle-containment.sh` with
   `LAZY_STATE_DIR` pointed at it. Observe on stderr:
   `lazy-cycle-containment.sh: line 809: <...>/python3: Argument list too long` and exit 0 with
   EMPTY stdout (fail-open — no deny, no breadcrumb).

## Root cause (Concluded)

Root-cause class: **hook-defect (platform command-line-length limit)**.

Line 809 invokes the hook's embedded python body as a `-c` argument:
`LCC_SCRIPTS_DIR="$LCC_SCRIPTS_DIR" "$PYTHON" -c "$_LCC_PY"`. The `$_LCC_PY` here-doc body is
**33,575 bytes**, which exceeds the Windows `CreateProcess` command-line limit of **32,767
characters**. So on Windows (Git Bash → native `python3`) the process is never spawned — bash
reports `Argument list too long` (E2BIG) — and the hook falls through to its unconditional
`exit 0` (line 813). The containment guard is therefore **silently disarmed on this Windows
workstation**: a runaway cycle subagent is not contained, and 22 pinned regression tests are red.

The fail-open is **untraced** — E2BIG is neither the "no-python" bash fallback (python IS
resolvable) nor reachable by the python-side `except` breadcrumb (the process never starts), so
`guard-fail-open-leaves-no-trace`'s observability does not fire. A prior harden round grew the
inline body past the platform limit (last hook touch: `cb666120`).

## Fix scope (proposed — NOT implemented this round)

Stop passing the body as a `-c` argument. Feed `$_LCC_PY` to python over **stdin** (`"$PYTHON" -
<<<"$_LCC_PY"` or a `printf ... | "$PYTHON" -`) or write it to a temp `.py` file and run that —
neither is bounded by the command-line limit. The current design already pipes the PreToolUse
payload to python via real stdin, so switching the SCRIPT to a temp-file invocation (keeping the
payload on stdin) is the cleaner shape. Add a Windows-side regression: assert the containment hook
DENIES (not fail-opens) for a subagent routing op under a marker on Windows, and/or a size guard
that fails if `$_LCC_PY` approaches the 32K limit.

This is a load-bearing guard on a separate hook and warrants its own investigated implementation
round — it is deliberately not fixed inline by the Round-95 test-isolation harden.

## Sibling check

The other python-bearing hooks with large embedded bodies (`lazy-dispatch-guard.sh`,
`lazy-route-inject.sh`, `block-*`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`)
should be audited for the same `-c "$BODY"` shape and body size during the fix — the E2BIG class
is plane-wide wherever an inline body approaches 32K.
