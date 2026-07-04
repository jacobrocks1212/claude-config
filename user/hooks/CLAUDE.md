# CLAUDE.md — user/hooks/

PreToolUse / PostToolUse shell hooks wired in `../settings.json`. A hook inspects a pending
tool call and allows or denies it. The canonical per-hook trigger/purpose table lives in the
**root `CLAUDE.md`** Hooks section — this file documents the load-bearing patterns every hook
here shares.

## Fail-OPEN is mandatory

Every hook **allows the tool call on any internal error** (no python, missing marker, malformed
payload, git failure). A hook is a guardrail, not a gate of last resort: a bug in a hook must
never wedge the pipeline. A blocking hook that failed closed would strand every run. When adding
a hook, make every error path fall through to allow — and drop a `hook-error.json` breadcrumb if
useful for diagnosis.

## Deny is JSON, not an exit code

A PreToolUse non-zero exit is a hard harness error. To block a call, emit
`{"permissionDecision": "deny", ...}` with a message — never `exit 2`. The message should name
the corrective action (the right branch, the canonical filename, the owning session), because
that text is what the agent reads and acts on.

## Per-repo keyed, not global-marker

The lazy enforcement hooks (`lazy-dispatch-guard.sh`, `lazy-route-inject.sh`,
`lazy-cycle-containment.sh`) scope to the **current repo** by calling
`lazy-state.py --marker-present --repo-root <cwd>` (read-only; exit 0 present / 1 absent). They
do NOT key off the mere existence of a run marker — a live run in repo A must not arm guards in a
session for repo B. **Bash never re-derives repo identity or branch**; it asks the Python
(`--marker-present`, `--marker-work-branch`). See `../scripts/CLAUDE.md` → per-repo keyed state dir.

## Request-time vs marker-armed

Two distinct activation models — don't conflate them:
- **Marker-armed** (`lazy-cycle-containment.sh`) — active only while a cycle marker is present;
  contains a runaway cycle subagent.
- **Request-time** (`long-build-ownership-guard.sh`) — always active; matches the command itself
  (an exact long-build invocation) regardless of any marker.

## Countable deny/error events (`hook-events.jsonl`)

Every deny site in the five enforcement hooks (`lazy-cycle-containment.sh`,
`block-noncanonical-blocker-write.sh`, `block-sentinel-write-on-stray-branch.sh`,
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`) and every existing
`hook-error.json` breadcrumb site (those three bash writers + `lazy_guard.py`) ALSO appends one
`{ts, kind: "error"|"deny", hook, repo_root, signature, detail}` line to **`hook-events.jsonl`**
(incident-auto-capture D2; keyed state dir when the repo resolves, else the base dir). The
appender is **fail-open like everything else here** — an append failure never changes the
deny/allow output, and `hook-error.json` keeps being written byte-identically (it stays the
at-a-glance "is a hook broken" file; the events file is the countable history `incident-scan.py`
clusters). `lazy_guard.py`'s DENIES deliberately do NOT append (they already persist to the deny
ledger — double-writing would double-count one incident across two signal classes). When adding a
deny site, pass a **stable signature token** (the collector's cluster key), not free text.
Pipe-tested in `test_hooks.py` (`test_events_*`: event-on-deny, byte-identical output with the
append failing, no event on allow).

## Write-time complements

A few hooks mechanically backstop a prose rule by refusing the bad *write*:
`block-noncanonical-blocker-write.sh` (a misnamed `BLOCKED*` sentinel) and
`block-sentinel-write-on-stray-branch.sh` (a sentinel written on the wrong branch). Both are the
write-time half of a state-script read-time check — keep the pair in mind when changing either.

## Deliberately unwired

`fix-line-endings.ps1` and `run-eslint.ps1` exist but are **NOT registered** (`settings.json`
`PostToolUse` is `[]`). `fix-line-endings.ps1` normalizes *to* CRLF, which would increase
`\r`-bearing writes hitting `\n`-only downstream validators — do not blind-wire it. Per-repo
formatting is registered in repo-scoped settings instead. Read the root `CLAUDE.md` Hooks-table
note before wiring either.
