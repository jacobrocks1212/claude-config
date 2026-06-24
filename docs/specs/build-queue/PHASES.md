# Implementation Phases — Build Queue

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is `claude-config` harness tooling (PowerShell scripts, a bash PreToolUse hook, and skill markdown). There is no Tauri app or MCP server in this repo, so there is no live runtime to assert against. All verification is manual, multi-process, and observable on the local filesystem / process table. This feature is implemented **by hand**, outside the autonomous lazy pipeline (see `docs/specs/CLAUDE.md`); the phases below are a hand-execution plan, not a `/lazy` work-unit decomposition.

## Validated Assumptions (from the /spec-phases touchpoint audit)

These were verified against the real repo before authoring; the phases below build on them, not on the SPEC's pre-audit wording.

- **No `manifest.psd1` edit or `setup.ps1` bootstrap is required for any new file.** `manifest.psd1:4-6` symlinks `~/.claude/{skills,hooks,scripts}` as whole **Directory** symlinks, and the `cognito-forms` repo entry (`manifest.psd1:32`) symlinks `.claude/skills` as a directory (with `-B/-C/-D` aliasing `cognito-forms`). A new file dropped into `user/scripts/`, `user/hooks/`, or `repos/cognito-forms/.claude/skills/<name>/` therefore appears at every live path in all four worktrees automatically. The only manifest-governed file this feature *edits* is `user/settings.json` (a **File** symlink — editing the repo source propagates).
- **The enforce-hook scope gate must resolve the git remote, not the work email.** The reference hook `block-work-repo-git-push.sh:19-20` gates on `git config user.email == jacob@cognitoforms.com`. That is too broad here: Overwatch and `mcp/` are also work-email repos and must NOT be gated. L8's "remote matching `cognitoforms/cognito`" is the correct, narrower test. Resolve it from the hook's own cwd (the worktree the session runs in), matching how the sibling hooks already operate.
- **The four skills append `$ARGUMENTS` verbatim to the constructed command** (confirmed in `mstest/SKILL.md:28-37`). The wrapper's CLI contract must preserve that verbatim pass-through (see Phase 1 deliverable: `ValueFromRemainingArguments`), or arg-forwarding breaks on quoting. This is why the wrapper contract is owned by Phase 1 and merely consumed by Phase 2.
- **The clone template `long-build-ownership-guard.sh` is confirmed** to use the python-via-`-c` + stdin-JSON + deny-via-JSON + fail-open-on-any-error pattern, with an env-prefix regex (`_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"`) the enforce hook reuses for leading `NAME=value` tolerance.

---

### Phase 1: Queue core (`build-queue.ps1`)

**Scope:** The one genuinely new component — a machine-global FIFO serializer that allocates a sequence number, enqueues a ticket, claims the single `active.lock`, runs the underlying filtered script as a detached process, and releases the slot. Establishes `~/.claude/state/build-queue/` and the wrapper CLI contract that every other phase consumes.

**Deliverables:**
- [x] `user/scripts/build-queue.ps1` implementing the acquire algorithm (SPEC §"Acquire algorithm"): atomic seq allocation (`CreateNew` on a transient `seq.counter.lock`, bounded retry), ticket enqueue, ~1s poll loop with PID-death reclaim of stale tickets/`active.lock`, head-check + `CreateNew`-on-`active.lock` claim, detached `Start-Process` run redirected to `logs/<seq>.log`, `build_pid` recorded in `active.lock`, log tail to the wrapper's stdout, `results/<seq>.json` write on completion, `active.lock` delete, build exit code propagated as the wrapper's exit code.
- [x] Wrapper CLI contract: `-Op <msbuild|mstest|nxbuild|nxtest>`, `-Exec <path to filtered script>`, and trailing pass-through args via `[Parameter(ValueFromRemainingArguments=$true)] $ExecArgs` so the skills' verbatim `$ARGUMENTS` forward cleanly without a single-quoted `-ExecArgs` string.
- [x] `machine-perf.ps1 -Json` snapshot captured at build start and stored in `active.lock` (the snapshot *write* lives here; the *reader* is Phase 4).
- [x] Position heartbeat emitted while waiting; emit only when position changes (resolves the SPEC "heartbeat cadence vs log noise" open question by construction).
- [x] `~/.claude/state/build-queue/` subtree created on first run (`seq.counter`, `tickets/`, `logs/`, `results/`).

**Minimum Verifiable Behavior:** From two different worktrees, launch the wrapper concurrently against a short sleep-stub exec (e.g. `-Exec` pointing at a script that sleeps 10s):
```
# worktree A and worktree B, started within ~1s of each other:
powershell.exe -File ~/.claude/scripts/build-queue.ps1 -Op msbuild -Exec <sleep-stub>
```
Confirm: only one runs at a time, the second's `tickets/<seq>.json` shows the higher seq, and `results/*.json` `ended_at` ordering matches the seq ordering. `active.lock` holds exactly one seq at any instant.

**Manual Verification:**
- [ ] Two concurrent wrappers serialize; `active.lock` never contains two holders (poll `Get-Content active.lock` during the run).
- [ ] FIFO: three staggered launches execute in arrival (seq) order.
- [ ] Exit code of the inner build propagates as the wrapper's exit code (run a stub that exits 1; assert wrapper exits 1).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/build-queue.ps1` — net-new; the queue core.

**Reuse:** runs the per-worktree `Cognito Forms*/.claude/scripts/{build,test,client-build,client-test}-filtered.ps1` **unchanged** as `-Exec` targets (SPEC Reuse Ledger: "Filtered build/test execution — reuse-as-is"). Consumes `user/scripts/machine-perf.ps1 -Json` (Reuse Ledger: "Machine health snapshot"). State subtree follows the `~/.claude/state/` (`LAZY_STATE_DIR`) convention (Reuse Ledger: "Machine-global shared state").

**Testing Strategy:** Pure multi-process manual test with a sleep-stub exec — no Cognito build needed to prove the queue's serialization/FIFO/exit-code contract. Isolate from real builds until the concurrency invariants hold.

**Integration Notes for Next Phase:**
- The CLI contract (`-Op` / `-Exec` / trailing `$ExecArgs`) is frozen here; Phase 2's four skills depend on it verbatim. Any later change to the param shape is a breaking change to all four skills.
- The wrapper runs the filtered script **inside PowerShell** (`Start-Process` / `&`), not as a Bash tool call — so the Phase 3 enforce hook (matched at the Bash-tool boundary) never sees the inner `dotnet`/`nx`, and the sanctioned path needs no bypass token.
- `active.lock` records the **build's** PID, not the wrapper client's — this is what makes a client timeout survivable (Phase 5 stresses it).

**Implementation Notes (authored — `build-queue.ps1`):**

*Frozen CLI contract (Phase 2 depends on this verbatim):*
```
build-queue.ps1 -Op <msbuild|mstest|nxbuild|nxtest> -Exec <abs path to filtered script> [<pass-through args>...]
```
`-Op` is `ValidateSet`-constrained; `-Exec` is the filtered script run UNCHANGED inside a detached PowerShell; trailing args bind to `[Parameter(ValueFromRemainingArguments=$true)] $ExecArgs` and forward verbatim. Wrapper exit code == inner build exit code.

*State-file shapes (`$HOME/.claude/state/build-queue/`):*
- `seq.counter` — integer text; `seq.counter.lock` — transient `CreateNew` mutex guarding allocation (bounded 200×20ms retry).
- `tickets/<seq>.json` — `{seq, pid, worktree, op, started_wait_at}` (one per waiter; `pid` is the wrapper client, used for PID-death reclaim of abandoned tickets).
- `active.lock` — `{seq, build_pid, op, worktree, started_at, log_path, machine_perf}`. `build_pid` is the **detached build** PID (not the client) — the key to surviving a client/Bash-tool timeout.
- `logs/<seq>.log` + `logs/<seq>.err.log`; `results/<seq>.json` — `{seq, exit_code, ended_at}`.

*Concurrency design (hardened beyond the naive SPEC sketch during authoring — see Review Notes):*
- Claim is `[System.IO.File]::Open(active.lock, CreateNew, …, None)` — atomic single-winner. The winner writes a **provisional** body (`build_pid=$PID` placeholder) into the create stream immediately, then later atomically `File.Replace`s it with the real `build_pid` after `Start-Process`. This closes the window where a freshly-created-but-empty lock could be read as garbage by a peer.
- Reclaim uses a **grace period**: a lock that reads `dead`/`unknown` is only reclaimed after `staleThreshold=3` consecutive stale polls, and **only by the lowest-seq live waiter**. This prevents a single transient bad read from letting a peer delete a validly-held lock (the original double-claim bug).
- Liveness is fail-safe: `Test-PidAlive` returns `$true` on any non-`ArgumentException` error, so a transient query failure never reads as "dead."
- `Get-ActiveLockStatus` is non-destructive (returns `absent|unknown|alive|dead`; never deletes) — deletion is the poll loop's decision, gated by the grace period.

*PowerShell 5.1 / StrictMode pitfalls handled:* `@()`-wrap all function returns before `.Count`/`[0]` (scalar-unwrap trap); `$null = $proc.Handle` so `.ExitCode` is readable after a detached `Start-Process`; `[NullString]::Value` (not `$null`) for `File.Replace`'s backup arg; pure-ASCII source (no-BOM files are read as Windows-1252).

**Review Notes / verdict:** PASS-WITH-FIXES. Subagent-authored draft was functionally incomplete on concurrency: it had a real double-claim race (a peer reclaimed a freshly-won lock on one bad read, ~1/9 runs) and several PS-5.1 correctness bugs (detached build not truly detached, null exit code, `File.Replace` arg marshaling, non-ASCII mojibake). The orchestrator applied fixes that exceeded trivial scope — recorded transparently here rather than hidden. Post-fix, the queue passed multi-process verification by the orchestrator: serialization (zero overlapping START/END across ~14 rounds at 4–5 concurrent), FIFO seq ordering, exit-code propagation (0 and 1), verbatim arg forwarding, and dead-holder reclaim (~10s after killing the detached `build_pid`, a waiter reclaims, builds, writes `results/`, clears `active.lock`). This is orchestrator self-test evidence — it does **not** substitute for Jacob's Manual Verification rows below.

---

### Phase 2: Skill re-pointing

**Scope:** Re-point the four sanctioned entry-point skills to call the wrapper instead of the filtered script directly, forwarding their existing arguments unchanged. One edit per skill; symlinked, so each propagates to all four worktrees.

**Deliverables:**
- [ ] `…/skills/msbuild/SKILL.md` — step-1 command calls `build-queue.ps1 -Op msbuild -Exec "$REPO_ROOT/.claude/scripts/build-filtered.ps1"` with `$ARGUMENTS` appended verbatim.
- [ ] `…/skills/mstest/SKILL.md` — `-Op mstest -Exec "$REPO_ROOT/.claude/scripts/test-filtered.ps1"`.
- [ ] `…/skills/nxbuild/SKILL.md` — `-Op nxbuild -Exec "$REPO_ROOT/.claude/scripts/client-build-filtered.ps1"`.
- [ ] `…/skills/nxtest/SKILL.md` — `-Op nxtest -Exec "$REPO_ROOT/.claude/scripts/client-test-filtered.ps1"`.
- [ ] `$REPO_ROOT=$(git rev-parse --show-toplevel)` is retained in each (the filtered scripts are per-worktree; the wrapper is machine-global at `$HOME/.claude/scripts/`).

**Minimum Verifiable Behavior:** Invoke `/mstest -Filter "ClassName~SomethingSmall"` in one worktree. It runs through the queue (an `active.lock` appears for the duration) and the filter reaches the underlying `test-filtered.ps1` unchanged (only the filtered class runs).

**Manual Verification:**
- [ ] Each skill's pre-existing arguments (`-Filter`, `-TestDll`, `-Project`, `-Pattern`, etc.) still reach the underlying filtered script byte-identically — diff the effective command before/after.
- [ ] With a build active in worktree A, invoking the skill in worktree B queues behind it (position heartbeat shown) rather than running immediately.

**Prerequisites:**
- Phase 1: the wrapper and its CLI contract must exist.

**Files likely modified:**
- `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` — re-point step-1 command; symlinked to all worktrees.

**Reuse:** extends the existing skill→script wiring (SPEC Reuse Ledger: "Skill → script wiring — extend"). No new skill behavior; only the exec indirection changes.

**Testing Strategy:** Verified by invoking each skill and confirming (a) arg pass-through is unchanged and (b) the queue engages. No new code, so correctness rests on the Phase 1 contract holding.

**Integration Notes for Next Phase:**
- After this phase the skills are the *only* sanctioned heavy-build path — which is the precondition for Phase 3's hook to redirect raw invocations to them without redirecting to a path that itself bypasses the queue.

---

### Phase 3: Enforcement hook

**Scope:** A PreToolUse(Bash) hook that denies raw heavy-build invocations in Cognito worktrees and redirects to the matching skill, cloned structurally from `long-build-ownership-guard.sh`. Registered last in the existing `PreToolUse[Bash]` chain.

**Deliverables:**
- [ ] `user/hooks/build-queue-enforce.sh` — clone of `long-build-ownership-guard.sh` (python-via-`-c`, stdin-JSON, deny-via-JSON, fail-open on any error, best-effort breadcrumb).
- [ ] **Scope gate:** resolve the git remote from the hook's cwd; proceed only if it matches `cognitoforms/cognito`. Fail-open (allow) if the remote can't be resolved.
- [ ] **Deny surface (Conservative, SPEC L5):** first real token (after leading `NAME=value` env assignments) is `dotnet build`, `dotnet test`, `nx`/`npx nx` with a `build`/`test`/`run-many` target, or a direct `*-filtered.ps1` invocation (`build|test|client-build|client-test`).
- [ ] **Never denied:** `dotnet restore`/`--version`/`ef`, `nx lint`/`typecheck`/`format`, the wrapper `build-queue.ps1`, and anything prefixed `BUILD_QUEUE_BYPASS=1`. `msbuild`/`dotnet msbuild`/`npm`/`pnpm` deliberately excluded (zero genuine usage in evidence).
- [ ] **Redirect message:** names the matched op's skill and shows the equivalent invocation (raw `dotnet test --filter X` → "use `/mstest -Filter X`"); names `BUILD_QUEUE_BYPASS=1` as the override without advertising it prominently.
- [ ] Register `bash ~/.claude/hooks/build-queue-enforce.sh` as the 5th entry in `user/settings.json` `PreToolUse[Bash]` (after `long-build-ownership-guard.sh`), `timeout: 5`.

**Minimum Verifiable Behavior:** In a Cognito worktree, a Bash call of `dotnet build Cognito.sln` is denied with a `/msbuild` redirect and does not execute; `BUILD_QUEUE_BYPASS=1 dotnet build Cognito.sln` executes.

**Manual Verification (drive sample payloads through the hook via stdin):**
- [ ] Raw `dotnet build` / `dotnet test` / `npx nx build` in a Cognito worktree → `permissionDecision: deny` with the correct skill in the redirect.
- [ ] Direct `build-filtered.ps1` invocation in a Cognito worktree → denied (queue-bypass closure).
- [ ] `dotnet build` in `Overwatch/` (work-email repo, different remote) → **allowed** (proves remote gate ≠ email gate).
- [ ] `BUILD_QUEUE_BYPASS=1 dotnet build …` → allowed.
- [ ] `dotnet restore`, `nx lint`, and the wrapper `build-queue.ps1` itself → allowed.
- [ ] Malformed/empty payload and missing-python path → fail-open (allow), with a breadcrumb written.

**Prerequisites:**
- Phase 2: the redirect targets (skills) must already route through the queue, or the hook would redirect to a path that still bypasses it.

**Files likely modified:**
- `user/hooks/build-queue-enforce.sh` — net-new (clone).
- `user/settings.json` — register the hook in `PreToolUse[Bash]`.

**Reuse:** clones the enforcement-hook pattern (SPEC Reuse Ledger: "Enforcement hook pattern — wrap (clone)"); reuses the env-prefix regex idiom and the fail-open/deny-JSON contract from `long-build-ownership-guard.sh`. Borrows the "resolve which repo am I in" idea from `block-work-repo-git-push.sh` but substitutes remote-matching for email-matching (per Validated Assumptions).

**Testing Strategy:** Feed crafted PreToolUse JSON payloads to the hook over stdin and assert on its stdout (deny JSON vs empty allow) — no live build needed. Exercise each deny/allow row and both fail-open paths. Cover the scope gate by running the hook from an Overwatch cwd vs a Cognito-worktree cwd.

**Integration Notes for Next Phase:**
- The `cd`-prefixed-command blind spot (a command that `cd`s into a different repo before building) is shared with the sibling hooks and accepted for v1 — document it in the hook header, don't try to parse `cd` chains.
- Registering the hook *after* Phases 1–2 are working is deliberate: enabling enforcement before a working queue path exists would block builds with no sanctioned alternative.

---

### Phase 4: Status view + machine-perf surface

**Scope:** A read-only status command that reports the active build, the ordered waiters, and a live load summary. Reader only — the snapshot *write* was delivered in Phase 1.

**Deliverables:**
- [ ] `user/scripts/build-queue-status.ps1` — reads `active.lock` (active op/worktree/`build_pid`/elapsed/log path + stored start-time `machine-perf` snapshot) and `tickets/*.json` (ordered waiters), and runs a fresh `machine-perf.ps1 -Json` for a one-line live load summary (CPU %, mem used/free).
- [ ] `repos/cognito-forms/.claude/skills/build-queue-status/SKILL.md` — `/build-queue-status` skill (`model: haiku`, `allowed-tools: ["Bash"]`) that runs the reader and relays output verbatim.
- [ ] Graceful empty state: with no active build and no waiters, print "queue idle" + the live load line.

**Minimum Verifiable Behavior:** With a build active (start one via `/msbuild`), run `/build-queue-status` and see the active op, worktree, PID, elapsed, log path, any waiters, and the load line — matching `active.lock` + `tickets/*` on disk.

**Manual Verification:**
- [ ] Active build + ≥1 waiter → status lists the active holder and the waiters in seq order.
- [ ] Idle queue → "queue idle" + load line, no error.
- [ ] The load line's numbers track `machine-perf.ps1 -Json` run independently at the same moment.

**Prerequisites:**
- Phase 1: the state layout and the `active.lock` `machine_perf` field must exist.

**Files likely modified:**
- `user/scripts/build-queue-status.ps1` — net-new (reader).
- `repos/cognito-forms/.claude/skills/build-queue-status/SKILL.md` — net-new skill.

**Reuse:** consumes `machine-perf.ps1 -Json` (SPEC Reuse Ledger: "Machine health snapshot — reuse-as-is"); reads the Phase 1 state subtree. The new skill mirrors the existing `machine-perf` skill shape (`model: haiku`, thin script wrapper).

**Testing Strategy:** Read-only; verified by snapshotting `active.lock`/`tickets/*` on disk and diffing against the rendered status during a live queued build.

**Integration Notes for Next Phase:**
- This reader is the human-facing surface that also makes Phase 5's crash scenarios observable (e.g. confirming a stale lock has cleared).

---

### Phase 5: Crash-recovery hardening

**Scope:** Adversarial failure-injection against the Phase 1 reclaim logic. Phase 1 already proves the happy path; this phase proves the queue self-heals under client death, build death, and corrupt state — the riskiest correctness surface, given the whole point is resilience to the 600s Bash-tool timeout.

**Deliverables:**
- [ ] Failure-injection verification of all four recovery modes (below). No new production code expected; any defect found here is fixed in `build-queue.ps1` (Phase 1's file) and re-verified.
- [ ] Document the verified recovery behavior in the SPEC's validation section / a short note, so the resilience contract is recorded.

**Minimum Verifiable Behavior:** Start a build via the wrapper, kill the **wrapper client** process mid-build, and confirm the detached build runs to completion: `results/<seq>.json` gets an `exit_code`, and `active.lock` is cleared afterward — exactly as if the client had never died.

**Manual Verification (failure injection):**
- [ ] **Kill while waiting** — kill a queued client; its `tickets/<seq>.json` is reclaimed (PID-death) by a peer's poll; the slot is unaffected; remaining waiters renumber correctly.
- [ ] **Kill while holding** — kill the wrapper client mid-build; the detached build (its own PID in `active.lock`) survives, completes, writes `results/<seq>.json`, and releases `active.lock`.
- [ ] **Stale lock reclaim** — kill the *detached build's* PID directly; the next waiter's poll detects the dead `build_pid`, deletes `active.lock`, and proceeds.
- [ ] **Corrupt / partial state** — truncate or corrupt `active.lock` / a ticket / `seq.counter`; the wrapper tolerates it (fail-open / self-heal) rather than wedging the queue.
- [ ] **Legitimately-slow build is never reclaimed** — confirm a long-but-alive build holds the slot indefinitely (no max-runtime watchdog, per L7).

**Prerequisites:**
- Phase 1: the reclaim/claim logic under test.
- Phase 4 (helpful, not required): `/build-queue-status` makes the recovered states easy to observe.

**Files likely modified:**
- `user/scripts/build-queue.ps1` — only if a recovery defect is found (otherwise unchanged; this phase is verification).

**Reuse:** exercises Phase 1's PID-death reclaim (SPEC L7) and the build-PID-in-lock design (SPEC L3); no new components.

**Testing Strategy:** Process-level fault injection (`Stop-Process` on the client vs. the detached build PID) plus state-file corruption, each followed by asserting the queue returns to a correct state. This is the dedicated adversarial pass that the happy-path Phase 1 test deliberately does not cover.

**Integration Notes for Next Phase:** None — final phase. On completion, flip the SPEC `**Status:**` to `Complete` by hand (this feature is outside the autonomous pipeline, so there is no gate to do it automatically).
