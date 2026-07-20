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
silent. Every one of the 8 python-bearing hooks (`lazy-cycle-containment.sh`,
`block-noncanonical-blocker-write.sh`, `block-sentinel-write-on-stray-branch.sh`,
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`, `lazy-dispatch-guard.sh`,
`lazy-route-inject.sh`, `subagent-wedge-backstop.sh`) writes a breadcrumb in its no-python
fail-open branch too — the severest
failure class (neither `python3` nor `python` resolvable) is exactly the one no python-side
appender can record, so a small **pure-bash** fallback (only `date`/`mkdir`/`printf`, every write
`2>/dev/null || true`) writes both `hook-error.json` and one `hook-events.jsonl` line before
`exit 0`. Kept as an identical copied block across all 8 hooks (interim — no shared-hook-lib
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

> **`lazy-cycle-containment.sh` is ALSO registered on `Agent|Task`** (in addition to its
> `Bash|PowerShell` command-content registration and its `Skill` registration) — but NOT because it
> is a command-content guard on that family. Its `Agent|Task` registration exists solely so its
> **background-dispatch deny** (a cycle subagent dispatching `Agent`/`Task` with
> `run_in_background: true` deadlocks awaiting a child→parent message that can never arrive) actually
> receives the Agent/Task tool calls its branch inspects. That deny was **dead code** until
> 2026-07-19 — the hook was registered only on `Bash|PowerShell` + `Skill`, so the branch never ran
> in production (`containment-background-dispatch-deny-unreachable-on-agent-task`). Wiring is pinned
> by `test_containment_registered_on_agent_task_matcher` in `test_hooks.py`, distinct from the
> `Bash|PowerShell` widened-matcher meta-test. A FOREGROUND Agent/Task dispatch from a subagent stays
> ALLOWED there (the 2026-07-09 Explore-fan-out allowance); only the background flag is denied.

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
awk/PowerShell script-block literal) from matching. A **second** operator-observed false-positive
class on the same hook (`block-terminal-kill-false-denies-quoted-argument-tokens`, 2026-07-13)
extends this to the shell-QUOTING level: segment-start anchoring is blind to a separator/keyword
that sits at a segment-start position *inside a quoted string literal* (a `git commit -m
'… || exit 1'` guard clause; an `--emit-dispatch --context "…exit…"` prose string) — one quoting
level below the command line the hook guards. `_mask_quoted` blanks the CONTENT of single-/
double-quoted spans (quote chars + every offset preserved) before the anchored matchers run, so a
keyword outside every quote still denies (a real `&& kill` after a quoted message is untouched)
while an in-quote one is masked away. This is a flat single-pass char scan, the same
not-a-shell-parser discipline as `_normalize_ps_syntax`; the accepted residual is a keyword inside
a `bash -c "kill …"` string argument (the plane-wide quoted-argument residual above).
Because `_mask_quoted` blanks *every* interior char of a quoted span (a separator character
`; & | (` inside quotes becomes a space, so `_CMD_START` cannot fire on it), it also covers the
separator-inside-quotes case — a `grep 'foo|kill'` regex alternation or a `python -c "…;exit(0)"`
body is allowed while a genuine post-quote `echo "a;b" && kill 1` still denies (the reported
`/build-queue-await` result-read incident, `block-terminal-kill-matches-separators-inside-quoted-args`).

A **third** operator-observed false-positive class on the same hook
(`block-terminal-kill-false-denies-heredoc-body-tokens`, 2026-07-15) targets a construct neither
`_mask_quoted` nor segment-start anchoring can see: a **heredoc body**. `<<WORD` / `<< 'WORD'` /
`<<"WORD"` / `<<-WORD` introduces a span of inert DATA (a commit message via `git commit -F -
<<'EOF'`, appended file content via `cat >> f << 'EOF'`) running from the newline after the
introducer through the terminator line — never executed — but the body's own interior newlines
satisfy `_CMD_START`'s `\n` separator class exactly like a real command boundary, so a deny token
sitting at the start of a body line (a commit-message body mentioning `kill`, a log line starting
`exit 0`) fabricates a false segment start. `_mask_heredoc` (a flat single-pass scan over
`re.finditer` introducer matches on the *original* command, the same not-a-shell-parser discipline
as `_mask_quoted`/`_normalize_ps_syntax`) resolves each introducer to a body span via the first
terminator-shaped line found at-or-after it and blanks **every** interior char of that span —
**including its newlines** (unlike `_mask_quoted`, which keeps `\n`; the false segment starts
here ARE the body's own newlines, so they must stop being newlines). The introducer line and the
terminator WORD line itself are left untouched, so a real deny token chained AFTER the terminator
(a genuine top-level segment start) still denies. Applied in `main()` BEFORE `_mask_quoted` (the
two compose cleanly: a heredoc introducer's own `'WORD'`/`"WORD"` quoting is left for `_mask_quoted`
to consume normally afterward, harmlessly). `<<-WORD` additionally tolerates a leading-whitespace
terminator line (real bash `<<-` semantics); an unterminated heredoc masks through end-of-string
(conservative, never a crash).

Kept as an **identical hook-local copy** across every `_CMD_START`-anchored command guard —
`block-terminal-kill.sh`, `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`,
`build-queue-enforce.sh` — the same lockstep-copy discipline as `_normalize_ps_syntax` /
`COMMAND_TOOL_NAMES` above; keep the four copies in sync by inspection. All four were confirmed
vulnerable (each anchors its own deny tokens on `_CMD_START` and gets the identical fix + a
heredoc-allow test + an after-terminator-still-denies regression test in `test_hooks.py`).
`block-work-repo-git-push.sh` is the one command guard **NOT** touched: it carries no
`_CMD_START` anchoring at all — its `git push` detection is an unanchored `\bgit\s+push\b`
substring search over the whole raw command — so the heredoc-newline-fabricates-a-segment-start
mechanism this fix targets does not apply to it structurally (a `git push` mention anywhere,
heredoc or not, was already caught by the pre-existing unanchored match; a separate, wider,
out-of-scope false-positive surface). Pinned by
`test_push_unaffected_by_heredoc_body_no_cmd_start_anchoring`.

**Accepted residual (NOT fixed this round) — PowerShell here-strings.** `@'...'@` / `@"..."@` are
a distinct construct from POSIX heredocs; `_mask_heredoc` only recognizes `<<WORD` forms, so a PS
here-string body is invisible to it. `_mask_quoted` coincidentally masks a well-formed here-string
body (its `'`/`"` delimiter chars are read as an ordinary quote pair), but an apostrophe inside the
body (`don't`) prematurely closes that fake quote span — the remaining body text, including a
line-leading deny token, then reaches the matchers fully unmasked and still false-denies. Pinned
(not silently left as a gap) by
`test_termkill_ps_herestring_apostrophe_body_kill_accepted_residual` — a future PS here-string
masker is a conscious behavior change, not an accidental one.

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

### Second-feature tripwire scopes to the commit's effective pathspec

`lazy-cycle-containment.sh`'s marker-armed second-feature-commit tripwire evaluates only the paths
the pending `git commit` will actually include — its **effective pathspec**, parsed from the
`git commit` invocation (`_commit_pathspecs` / `_commit_effective_paths`) — NOT the whole staged
index. A **bare** `git commit -m "…"`, a `git commit -a`/`--all`, or any parse ambiguity falls back
to the WHOLE index (deny preserved), so the genuine "a bare commit flushes a concurrent lane's
staged foreign files into one commit" cross-contamination catch is intact. The re-scope closes a
false-deny (`adhoc-incident-hook-deny-057921`) where, under a shared worktree, a concurrent lane's
foreign `docs/{features,bugs}/<other>/…` path staged in the shared index made a legitimately
pathspec-scoped same-feature commit deny. Safe-fallback bias: the filter narrows the evaluated set
ONLY when the commit is confidently pathspec-scoped — it may false-DENY on ambiguity, never
false-ALLOW a foreign path.

## Countable deny/error events (`hook-events.jsonl`)

Every deny site in the five enforcement hooks (`lazy-cycle-containment.sh`,
`block-noncanonical-blocker-write.sh`, `block-sentinel-write-on-stray-branch.sh`,
`long-build-ownership-guard.sh`, `build-queue-enforce.sh`) and every `hook-error.json` breadcrumb
site — the generic catch-all `except Exception` tail of ALL 8 python-bearing hooks (per
`guard-fail-open-leaves-no-trace`, every hook's tail now calls `_breadcrumb(exc)`; previously two
of the original seven, the Write/Edit sentinel pair, had no catch-all observability at all; the
8th is the `subagent-wedge-backstop.sh` SubagentStop hook), plus each
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
the no-python path across all 8 hooks in one test).

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
