# CLAUDE.md — user/hooks/

PreToolUse / PostToolUse shell hooks wired in `../settings.json`. A hook inspects a pending
tool call and allows or denies it. The canonical per-hook trigger/purpose table lives in the
**root `CLAUDE.md`** Hooks section — this file documents the load-bearing patterns every hook
here shares.

## Fail-OPEN is mandatory

Every hook **allows the tool call on any internal error** (no python, missing marker, malformed
payload, git failure). A hook is a guardrail, not a gate of last resort: a bug in a hook must
never wedge the pipeline. A blocking hook that failed closed would strand every run. When adding
a hook, make every error path fall through to allow — and drop a `hook-error.json` breadcrumb
(this is now a REQUIREMENT, not merely "if useful" — see Countable deny/error events below;
`guard-fail-open-leaves-no-trace`).

**Fail-open observability, including the no-python case.** A dead guard plane must never be
silent. Every one of the 7 python-bearing hooks (`lazy-cycle-containment.sh`,
`block-noncanonical-blocker-write.sh`, `block-sentinel-write-on-stray-branch.sh`,
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`, `lazy-dispatch-guard.sh`,
`lazy-route-inject.sh`) writes a breadcrumb in its no-python fail-open branch too — the severest
failure class (neither `python3` nor `python` resolvable) is exactly the one no python-side
appender can record, so a small **pure-bash** fallback (only `date`/`mkdir`/`printf`, every write
`2>/dev/null || true`) writes both `hook-error.json` and one `hook-events.jsonl` line before
`exit 0`. Kept as an identical copied block across all 7 hooks (interim — no shared-hook-lib
feature exists in this repo yet; keep the copies in lockstep by inspection, same discipline as the
`_normalize_ps_syntax` triple). Pipe-tested by forcing `PATH=""` via the properly-resolved Git
Bash executable — **not** a bare `"bash"` subprocess token, which Windows `CreateProcess` resolves
via `System32` (the WSL launcher) regardless of the child env's `PATH`, silently defeating the
no-python simulation with WSL's own independent python3.

**Known limitation — hook-timeout kills are untraced.** Every hook is registered with
`"timeout": 5` in `user/settings.json`. No hook installs a trap or start/finish marker pair, so a
hook killed by the harness at the timeout leaves the same nothing as a hook that never ran. This
was flagged UNVERIFIED in `docs/bugs/guard-fail-open-leaves-no-trace` (would require staging a
deliberately slow hook against the live harness timeout — outside what a subprocess pipe test can
exercise) and is documented here as a known limitation per that bug's own D3 fallback, not
silently dropped.

**Known limitation — `bash -c` / `sh -c` string-wraps evade every `_CMD_START`-anchored matcher
(`long-build-and-build-queue-matcher-bypasses` D2, accepted, not fixed).** Every anchored matcher
in this plane (`lazy-cycle-containment.sh`'s recursion/routing/lifecycle denies,
`long-build-ownership-guard.sh`'s `_LONG_BUILD_RE`, `build-queue-enforce.sh`'s deny surface + the
`_WRAPPER_DIRECT_RE`/`_WRAPPER_POWERSHELL_RE` wrapper recognizer) requires the token it matches to
sit at a top-level command-segment start (`_CMD_START`'s separator class: string start, or
`&& || | ; ( {` / newline). A `bash -c "cargo build --release"` or `sh -c "dotnet build ..."`
places the denied token inside a **quoted STRING ARGUMENT** to `bash`/`sh` — one level of
indirection none of these matchers unwraps — so the build is invisible to the anchor and the
command ALLOWs. This is distinct from (and NOT fixed by) the existing
`powershell/pwsh -Command "..."` nesting normalization (`_normalize_ps_syntax`), which DOES unwrap
one level for that specific PowerShell form; no equivalent unwrap exists for `bash -c`/`sh -c`.
Two fixes were considered when this residual was investigated (`docs/bugs/long-build-and-build-queue-matcher-bypasses`):
a `bash -c`/`sh -c` nested-command subscan (re-run every anchored matcher against the quoted
argument as a synthetic segment, mirroring the PowerShell unwrap), or leaving it as a documented
gap. The subscan was DEFERRED (not attempted) — it is plane-wide (would touch all three hooks'
shared `_CMD_START` idiom, not one), and a real shell-quote-aware argument extraction is
meaningfully more failure-prone than the flat string operations every other normalization here
uses. The gap is pinned as an explicit, intentional residual by
`test_longbuild_guard_bash_dash_c_wrap_accepted_residual` and
`test_bqe_bash_dash_c_wrapper_reference_accepted_residual` in `test_hooks.py` — a future fix
landing here should update BOTH tests (RED→GREEN) rather than leaving them as stale residual pins.

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
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`) and every `hook-error.json` breadcrumb
site — the generic catch-all `except Exception` tail of ALL 7 python-bearing hooks (per
`guard-fail-open-leaves-no-trace`, every hook's tail now calls `_breadcrumb(exc)`; previously two
of the seven, the Write/Edit sentinel pair, had no catch-all observability at all), plus each
hook's pure-bash no-python fallback, plus `lazy_guard.py` — ALSO appends one
`{ts, kind: "error"|"deny", hook, repo_root, signature, detail}` line to **`hook-events.jsonl`**
(incident-auto-capture D2; keyed state dir when the repo resolves, else the base dir). The
appender is **fail-open like everything else here** — an append failure never changes the
deny/allow output, and `hook-error.json` keeps being written byte-identically (it stays the
at-a-glance "is a hook broken" file; the events file is the countable history `incident-scan.py`
clusters). `lazy_guard.py`'s DENIES deliberately do NOT append (they already persist to the deny
ledger — double-writing would double-count one incident across two signal classes). When adding a
deny site, pass a **stable signature token** (the collector's cluster key), not free text.
Pipe-tested in `test_hooks.py` (`test_events_*`: event-on-deny, byte-identical output with the
append failing, no event on allow; `test_all_python_bearing_hooks_breadcrumb_on_no_python` sweeps
the no-python path across all 7 hooks in one test).

## Write-time complements

A few hooks mechanically backstop a prose rule by refusing the bad *write*:
`block-noncanonical-blocker-write.sh` (a misnamed `BLOCKED*` sentinel) and
`block-sentinel-write-on-stray-branch.sh` (a sentinel written on the wrong branch). Both are the
write-time half of a state-script read-time check — keep the pair in mind when changing either.

`block-noncanonical-blocker-write.sh` is **path-scoped** to `docs/features/**` and `docs/bugs/**`
(`_SENTINEL_SCOPE_RE`, matched against the full file path, ALONGSIDE the basename-shape check) —
the only two trees a pipeline sentinel ever has a reason to exist in. A blocker-shaped basename
anywhere else in the repo (e.g. a skill component literally named `blocked-resolution.md`) must
never deny (`adhoc-blocker-write-hook-overbroad-scope`). Its read-time sibling
(`lazy_core.detect_noncanonical_blocker`) never needed this check because its only caller always
passes a specific item directory — this write-time hook fires on every Write/Edit in the repo, so
it needs the scoping explicitly.

## Deliberately unwired

`fix-line-endings.ps1` and `run-eslint.ps1` exist but are **NOT registered** (`settings.json`
`PostToolUse` is `[]`). `fix-line-endings.ps1` normalizes *to* CRLF, which would increase
`\r`-bearing writes hitting `\n`-only downstream validators — do not blind-wire it. Per-repo
formatting is registered in repo-scoped settings instead. Read the root `CLAUDE.md` Hooks-table
note before wiring either.
