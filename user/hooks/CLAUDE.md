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

## Every command-execution tool the harness exposes, not just Bash

The harness exposes more than one command-execution tool with an identical `tool_input.command`
payload shape — currently `Bash` and `PowerShell`. A guard hook matched (in `settings.json`) or
gated (inline, on `tool_name`) on `"Bash"` alone is **cleanly bypassed** by an equivalent command
run through any other command tool (`powershell-tool-bypasses-bash-matched-guards`). Every
command-content guard (`block-work-repo-git-push.sh`, `block-terminal-kill.sh`,
`lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`) is
therefore:

- **Registered under `matcher: "Bash|PowerShell"`** in `settings.json` (never bare `"Bash"`).
- **Tool-name-agnostic in its inline gate**, checking membership in a `COMMAND_TOOL_NAMES`
  frozenset rather than equality against the literal `"Bash"`. Kept as an identical HOOK-LOCAL
  literal in each of the three widened hooks (`lazy-cycle-containment.sh`,
  `long-build-ownership-guard.sh`, `build-queue-enforce.sh`) — **not** a shared `lazy_core` import
  — so no hook's fail-open contract ever depends on an external module resolving. Keep the three
  copies in lockstep by inspection if the set ever grows a member.
- **Covered by a cross-guard meta-test** (`test_all_command_guards_registered_with_widened_matcher`
  in `test_hooks.py`) asserting every hook in that enumerated set carries a matcher containing both
  `Bash` and `PowerShell` — a future command-guard hook that forgets to widen fails immediately.

`lazy-dispatch-guard.sh` (`Agent|Task`) and the `Write|Edit` sentinel pair are **not** in this set —
they gate a different tool family, not command-content execution.

### PowerShell-syntax regex audit

The command-content patterns above were originally authored against POSIX/bash syntax. Three
concrete PS idioms needed handling (or explicit non-handling) once the matcher widened:

- **Env-assignment prefixes** differ: bash's `NAME=value cmd` vs PowerShell's `$env:NAME='value';
  cmd`. `_ENV_PREFIX` in `lazy-cycle-containment.sh` / `long-build-ownership-guard.sh` /
  `build-queue-enforce.sh`, and the bypass-token regexes (`BUILD_QUEUE_BYPASS` /
  `CLAUDE_PUSH_APPROVED`), recognize both forms.
- **Backtick line-continuation**: a PowerShell command line ending in `` ` `` continues on the next
  physical line — the SAME logical command, not a new segment. Left unhandled, the `\n` in
  `_CMD_START`'s separator class would wrongly split a continued build invocation into two
  segments, hiding it from every anchored pattern. Each of the three hooks above collapses
  `` `\r?\n `` to a single space before matching (`_normalize_ps_syntax`).
- **`powershell(.exe)?|pwsh ... -Command "..."` nesting**: the quoted string argument is itself
  executed as a command line, so a token inside it is not at a top-level segment-start position.
  `_normalize_ps_syntax` unwraps one level by re-appending the tail following the opening quote as
  a synthetic newline-prefixed segment (purely additive — never narrows what the unwrapped matcher
  could already detect). Distinct from the pre-existing, narrower
  `_FILTERED_SCRIPT_POWERSHELL_RE` in `build-queue-enforce.sh`, which already handled the `-File
  <path>` invocation form specifically.
- **`&`/`&&`/`||` call and chain operators** needed no fix: `re.search` tries every offset, so the
  existing single-char separator class already finds a valid segment-start position at (or after)
  any `&`/`|` occurrence regardless of whether it appears singly (bash) or doubled (PowerShell 7
  `&&`/`||`).

`block-terminal-kill.sh`'s **segment-start anchoring** (a distinct, operator-observed fix, same
bug) tightens its bare `\b(kill|exit|...)\b` word-boundary matches — which false-denied innocent
embedded text (an awk `'{exit}'` script body, a pytest `-k "...kill..."` expression) — to deny only
when the token BEGINS a command segment, mirroring `build-queue-enforce.sh`'s `_CMD_START`. `{`
counts as a segment separator only when followed by whitespace (bash's `{ cmd; }` grouping
requires a blank after the reserved word), which is exactly what keeps a no-space `{exit}` (an
awk/PowerShell script-block literal) from matching.

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

A third scoping model rides request-time: `build-queue-enforce.sh` scopes by **ops-manifest
presence** (`.claude/skill-config/build-queue-ops.json` at the payload cwd's git toplevel), with a
Cognito remote-match legacy fallback for a missing/unreadable manifest (`build-queue-generalization`
locked D4). Ordering is load-bearing: the ownership guard is registered BEFORE the enforce hook so
a subagent's raw long build surfaces the takeover signature first; the takeover re-launch then
routes through the queue wrapper, which the enforce hook exempts (locked D5 — no ping-pong).

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
