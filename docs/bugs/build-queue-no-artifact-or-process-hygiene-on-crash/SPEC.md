# Build queue has no artifact/process hygiene on build crash — Investigation Spec

> A crashed or killed build leaves orphaned compiler/test child processes and a truncated 0-byte output artifact behind. The queue serializes invocations but never reaps those processes or validates output, so MSBuild's timestamp-based incremental check then *skips recompiling* the poisoned artifact and every subsequent serialized build fails downstream (CS0009 / MSB4166 / CS0234) until a human manually kills the stragglers and deletes the bad DLL. A related, broader failure of the same kind: the queue records a build's **`exit_code=0` as an authoritative pass without validating that the run produced meaningful output** — so a test run that matched zero tests (or whose filtered-output script emitted no summary) is recorded as a clean success, indistinguishable from a genuine all-passing run.

> **Scope note (expanded 2026-06-30):** this spec's root theme is *the queue trusts signals that don't certify success.* Three vectors share that theme: (a) intra-worktree 0-byte/truncated artifact trusted by **timestamp**; (b) cross-worktree orphaned machine-global compiler/worker processes; (c) **result fidelity** — `exit_code=0` trusted as pass even when the run produced no test summary / matched zero tests. Vectors (a)/(b) are crash hygiene; (c) is a *successful-looking* run. All three are folded here per operator request; the directory slug is unchanged.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-30
**Placement:** docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash
**Related:** `docs/specs/build-queue/` (feature spec + plans); `docs/bugs/build-queue-orphaned-result-on-wrapper-kill/` (sibling defect — *result reporting* on wrapper death, fixed by the self-releasing runner; THIS bug is *process + artifact hygiene* on build crash, which the runner does not address); `user/scripts/build-queue.ps1`; `user/scripts/build-queue-runner.ps1`

<!-- Status lifecycle:
  - Investigating → root cause not yet proven.
  - Concluded     → root cause proven, affected area + fix scope understood; ready for /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** A crashed/killed build leaves a **0-byte (or truncated) output DLL** in the worktree's `bin/Debug` **and `obj/Debug`**. Confirmed first-hand this session: `Cognito Forms-B/Cognito/bin/Debug/netstandard2.0/Cognito.dll` was a 0-byte file (`ls -la` showed size `0`), and deleting it + rebuilding was required to recover. Confirmed again in a later session (screenshot evidence): MSBuild logged *"CoreCompile is being skipped because all output files are up-to-date"* — the 0-byte DLL's newer-than-source timestamp made the incremental engine treat it as fresh — and recovery required deleting the 0-byte DLL from **both** `Cognito\bin\Debug\netstandard2.0\Cognito.dll` **and** `Cognito\obj\Debug\netstandard2.0\Cognito.dll`. The quarantine sweep must therefore cover the `obj/` tree, not just `bin/`.
2. **[VERIFIED]** Orphaned build child processes survive past the build that spawned them. Confirmed first-hand: 15 `dotnet` processes (start times clustered at 3:46–3:48 PM) were still resident after the build that launched them had ended; `Get-Process dotnet,testhost,MSBuild,VBCSCompiler | Stop-Process -Force` was required to clear them.
3. **[VERIFIED]** Subsequent serialized builds fail downstream with `CS0009 "PE image doesn't contain managed metadata"`, `MSB4166 "Child node exited prematurely"`, and `CS0234` type-not-found cascades — the signature of a build reading an empty reference assembly and/or reusing a dead MSBuild worker node. Observed across multiple CI/local build attempts this session and in prior sessions (the same infra-flake signature was used to distinguish flaky CI from real failures).
4. **[VERIFIED]** Recovery is **manual** and not automated anywhere in the queue: kill orphaned `dotnet`/`testhost`/`MSBuild`/`VBCSCompiler` processes, then delete the 0-byte artifact, then rebuild. This procedure is documented as tribal knowledge in the Cognito repo's `CLAUDE.local.md`, not handled by the queue itself.
5. **[VERIFIED — result-fidelity vector]** A queued **test** run that produces **no test-summary output still exits `0` and is recorded by the queue as a pass**, indistinguishable from a genuine all-passing run. Confirmed first-hand this session (screenshot evidence): a `/mstest` run with a **5-way OR filter** logged only the 239-byte header with `exit_code=0` and an empty error log — `test-filtered.ps1` captured no per-test or summary line. The operator's own note records the trap: *"a zero-match filter also exits 0"* and *"3-way+ OR filters yield empty filtered output (a `test-filtered.ps1` display quirk — the proven-printing 2-way pairs at seq 251/258 worked)."* Because `dotnet test` exits `0` for **both** "all tests passed" and "zero tests matched the filter," and `test-filtered.ps1` only echoes lines matching its passed/failed/summary regexes (and has **no zero-output guard**), an empty-output run is silently a "pass." The operator had to manually re-run as 2-way pairs to obtain an authoritative count — exactly the manual-recovery smell as vectors (a)/(b).

## Reproduction Steps

1. Run a queued build (`/msbuild`, `/mstest`, etc.) that crashes or is killed mid-compile — e.g. an MSBuild worker node dies (`MSB4166`), the foreground wrapper is killed (Bash 2-min timeout → exit 143), or processes are force-killed.
2. Observe that (a) the build's grandchild processes (MSBuild `/m` worker nodes, the machine-global `VBCSCompiler` server, `dotnet`/`testhost`) are **not** reaped, and (b) a partially-written output assembly is left in `bin/Debug` with a modification time newer than its source inputs.
3. Run the next queued build in the same worktree.

**Expected:** The queue detects the failed/aborted build, reaps the build's orphaned child processes, and ensures no corrupt artifact is left that a later build will treat as up-to-date. The next build either recompiles the artifact cleanly or fails loudly with a clear "previous build left corrupt output" message.
**Actual:** Orphaned processes linger; the 0-byte artifact's newer timestamp causes MSBuild's incremental up-to-date check to **skip** recompiling it; downstream projects reference the empty assembly and fail with `CS0009`/`CS0234`, or reuse a dead worker node and fail with `MSB4166`. The queue serializes every retry into the same poisoned failure. Only manual process-kill + artifact-delete recovers.
**Consistency:** Deterministic once a crashed build has left a poisoned artifact and/or orphaned nodes. Recurs across sessions and worktrees because the contaminating processes are machine-global.

## Evidence Collected

### Source Code

All citations are `user/scripts/build-queue.ps1` and `user/scripts/build-queue-runner.ps1`.

- **The queue's only concerns are FIFO serialization and result reporting.** `build-queue.ps1` allocates a seq (Step 1, 84-114), enqueues a ticket (Step 2, 119-129), polls/claims the single `active.lock` slot (Step 3, 180-246), launches the detached runner (Step 4, 287-314), tails its log (317-362), and records the result + releases the lock (Step 5, 364-392). **Nowhere does it inspect build output artifacts or enumerate/kill build child processes.**
- **The detached runner runs the build as a grandchild and exits — no process or artifact cleanup.** `build-queue-runner.ps1:39` is `& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Exec @ExecArgs`. MSBuild launched under it spawns `/m` worker nodes and connects to the persistent machine-global `VBCSCompiler` server; `dotnet test` spawns `testhost`. The runner captures only `$LASTEXITCODE` (40), writes `results/<seq>.json` (50-64), and releases `active.lock` if the seq matches (66-75). **There is no reaping of the grandchild's descendant processes and no validation/quarantine of build output** — on a crash, both are left behind.
- **`Test-PidAlive` / stale-reclaim track only the lock-holder pid, not build descendants.** `build-queue.ps1:47-58` and `Get-ActiveLockStatus` (158-172) reason solely about `build_pid` (the runner). When that pid dies, stale-reclaim (179-194) frees the *slot* — it has no notion of the worker-node / compiler-server / testhost descendants that outlive it.
- **No corrupt-artifact guard.** There is no pre-build "is the previous output sane?" check and no post-crash "delete partial outputs" step anywhere in either script. The queue trusts MSBuild's incremental engine, which trusts file timestamps — and a 0-byte DLL written by a dying build has a *newer* timestamp than the source, so it is treated as up-to-date and never rebuilt.
- **No result-fidelity guard — the queue records the raw exit code as the verdict.** `build-queue-runner.ps1:40` captures `$LASTEXITCODE` and `:52-56` writes `{seq, exit_code, ended_at}` to `results/<seq>.json`. `build-queue.ps1:364` does the same on the foreground path. **Neither inspects the build/test *output* for evidence the run actually did work** — exit `0` is recorded as success unconditionally. For a `dotnet test` op this is wrong: `dotnet test` exits `0` for a zero-match filter as well as for all-pass, so a no-op run is recorded as a pass.
- **`test-filtered.ps1` has no zero-output guard.** `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (symlinked into claude-config, git-tracked, so in-scope here) streams `dotnet test … | ForEach-Object` and emits a line **only** when it matches one of its passed/failed/summary regexes (`:34,:39,:56`). It tracks no "did I see any test-result or summary line at all?" counter, so when zero lines match — a zero-match filter, or a summary format the regex misses, or the observed ≥3-way-OR-filter empty-output quirk — it prints only the `Running tests…` header (`:18`) and passes through `dotnet`'s exit code. The `/mstest` skill (`repos/cognito-forms/.claude/skills/mstest/SKILL.md`) appends the caller's `$ARGUMENTS` (the OR filter) **verbatim** — the multi-class filter is constructed by the caller, so the empty-output-on-≥3-way-OR behavior is observed at runtime and its precise mechanism (malformed/zero-matching filter string vs. unparsed summary format) is not yet proven (see Open Questions).

### Cross-worktree vector (corrected from the original report)

The investigating subagent's report framed this as "a crashed MSBuild in worktree A poisons the **shared `bin/Debug`** that worktree B reads." That framing is **imprecise and likely incorrect**: each git worktree has its own working tree and therefore its own `bin/Debug`, so the **0-byte-artifact** poison is *intra-worktree* (this worktree's own crashed build poisons this worktree's next build). The genuine **cross-worktree** vector is different: MSBuild node-reuse worker nodes and the `VBCSCompiler` server are **machine-global shared processes**, so a crash in worktree A can leave orphaned/half-dead nodes that worktree B's next build reuses → `MSB4166`. Both vectors are real; the fix must address machine-global process hygiene (cross-worktree) *and* per-worktree artifact validation (intra-worktree).

### Git History

- `build-queue-runner.ps1` was introduced to make the **result** survive the foreground wrapper being killed (sibling bug `build-queue-orphaned-result-on-wrapper-kill`, Concluded). That fix is orthogonal to this one: it guarantees a `results/<seq>.json` is written, but a *successful* result file is not what is missing here — the builds **fail**, deterministically, because of leftover state the runner does not clean up.

### Related Documentation

- Cognito repo `CLAUDE.local.md` already documents the manual recovery ("If `bin\Debug\*.dll` is locked (MSB3027/MSB3021 'used by another process'), kill the holding `testhost`/`dotnet` process (`Get-Process testhost,dotnet | Stop-Process`) and rerun against the normal `bin/Debug`"). That this recovery is tribal knowledge a human must apply is itself evidence the queue should own it.

## Theories

### Theory 1: The queue serializes invocations but owns no build-environment hygiene — CONFIRMED
- **Hypothesis:** Because neither `build-queue.ps1` nor `build-queue-runner.ps1` reaps build descendant processes or validates output artifacts, a crashed build leaves machine-global orphaned nodes and a per-worktree 0-byte artifact; MSBuild's timestamp-based incremental check then skips the poisoned artifact and every subsequent serialized build fails until manual cleanup.
- **Supporting evidence:** No process-enumeration or artifact-inspection code exists in either script (see Source Code). First-hand confirmation of both the 0-byte DLL and the 15 orphaned `dotnet` processes this session. The `CS0009`/`MSB4166`/`CS0234` signature matches "empty reference assembly + dead worker node."
- **Contradicting evidence:** None found.
- **Status:** Confirmed.

### Theory 2: The queue records `exit_code` as the verdict without validating output fidelity — CONFIRMED
- **Hypothesis:** Because `build-queue-runner.ps1`/`build-queue.ps1` record the raw exit code as the result, and `test-filtered.ps1` has no zero-output guard, a test run that exits `0` while matching zero tests / emitting no summary is recorded as a pass — the same "trust a signal that doesn't certify success" failure mode as the timestamp-trusted 0-byte artifact.
- **Supporting evidence:** No output-inspection or zero-match-detection code in either queue script or in `test-filtered.ps1` (see Source Code). First-hand confirmation this session of a 5-way-OR `/mstest` run logging only the 239-byte header with `exit_code=0`. `dotnet test` exit-code semantics: `0` on zero-match.
- **Contradicting evidence:** None found.
- **Status:** Confirmed. (The *precise mechanism* of the ≥3-way-OR empty-output quirk — zero-matching filter vs. unparsed summary — is a separate, runtime-coupled question; the result-fidelity gap is confirmed regardless of which it is.)

## Proven Findings

1. The queue's responsibility boundary stops at FIFO ordering + result reporting. Build-environment hygiene (descendant processes, output artifacts) is owned by **nothing** — it falls through to manual human recovery.
2. Two distinct poisoning vectors, both unaddressed: (a) **intra-worktree** 0-byte/truncated artifact that MSBuild's incremental check skips because its timestamp is newer than source; (b) **cross-worktree** orphaned machine-global MSBuild worker nodes / `VBCSCompiler` server reused by a later build.
3. This is **not** the same defect as `build-queue-orphaned-result-on-wrapper-kill`. The runner fixed result-reporting durability; it did nothing for process/artifact cleanup. A build can now reliably *report that it failed* while still leaving the poison that makes the next build fail too.
4. The fix must place ownership of post-crash cleanup on something with the build's lifetime/scope — the runner is the natural home (it brackets the actual build invocation), with the wrapper as a backstop on the abort/timeout path.
5. **Result fidelity is a third unaddressed vector of the same theme.** The queue records `exit_code` as the verdict without confirming the run produced meaningful output; for test ops, `exit_code=0` is therefore ambiguous (all-pass vs. zero-match). The fix has two layers, both in claude-config-tracked files: (a) a **zero-output guard in `test-filtered.ps1`** so a run that emitted no test-result/summary line announces it explicitly and exits with a distinguished non-zero code rather than passing through `0`; and (b) **result-fidelity recording in the queue** so `results/<seq>.json` carries a `result_fidelity` field (`verified` / `no-output` / `zero-match`) that `build-queue-status.ps1` can surface. The *root cause* of the ≥3-way-OR empty-output quirk is runtime-coupled and is scheduled as a planning-time spike — the two defensive layers are robust regardless of that mechanism.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Detached build runner | `user/scripts/build-queue-runner.ps1` (39 build invocation; 40-77 result/release) | Runs build as grandchild; reaps no descendant processes and validates no output on crash |
| Queue wrapper — launch/tail/release | `user/scripts/build-queue.ps1` (287-314 launch, 317-362 tail, 364-392 Step 5) | No artifact inspection, no descendant-process reaping; abort/timeout path leaves everything behind |
| Stale-reclaim / liveness | `user/scripts/build-queue.ps1` (47-58, 158-172, 179-194) | Tracks only the lock-holder pid; blind to worker-node/compiler-server/testhost descendants |
| Status reporter | `user/scripts/build-queue-status.ps1` | Cannot surface "previous build left corrupt output / orphaned nodes / unverified result" because that state is never recorded |
| Result recording | `user/scripts/build-queue-runner.ps1` (40, 52-56); `user/scripts/build-queue.ps1` (364-373) | Records raw `exit_code` as the verdict; no output-fidelity inspection, so a zero-match test run (`exit_code=0`) is recorded as a pass |
| Filtered test output | `repos/cognito-forms/.claude/scripts/test-filtered.ps1` (18, 30-64) | Emits only regex-matched lines; no zero-output guard, so an empty/zero-match run prints only the header and passes through `dotnet`'s `0` exit code |
| Test skill | `repos/cognito-forms/.claude/skills/mstest/SKILL.md` (28-39) | Appends caller `$ARGUMENTS` (OR filter) verbatim; the ≥3-way-OR empty-output behavior is observed via this path (precise mechanism TBD by spike) |

## Proposed Fix Direction

Scope confirmed with the user as **three vectors** (artifacts + processes + result fidelity). The three design forks below were **resolved with the user** (2026-06-30) and are now Locked Decisions; the rest is for `/plan-bug` to refine.

- **Reap build descendants on completion and on abort.** Wrap the grandchild build in the runner so that, on the build's exit *or* on the runner being signalled/killed, it enumerates and terminates the build's descendant process tree (MSBuild `/m` worker nodes, `testhost`) scoped to that build.
- **Force-recycle `VBCSCompiler` between queued builds.** Shut down the machine-global `VBCSCompiler` server after each queued build, eliminating the cross-worktree dead-node-reuse vector at a small warm-start cost (safe because the queue already serializes — no concurrent build's node is ever killed).
- **Validate / quarantine output artifacts.** On a non-zero build exit (or abort), sweep the worktree's `bin/` **and `obj/`** for 0-byte / truncated `*.dll` and delete them so the next build's incremental up-to-date check cannot treat them as current.
- **Guard result fidelity.** Add a zero-output guard to `test-filtered.ps1` (no test-result/summary line seen ⇒ explicit warning + distinguished non-zero exit) and record a `result_fidelity` field in `results/<seq>.json`, surfaced by `build-queue-status.ps1`.
- **Record the hygiene outcome** into `results/<seq>.json` (e.g. `reaped_pids`, `quarantined_artifacts`, `vbcscompiler_recycled`, `result_fidelity`) so `build-queue-status.ps1` can surface a poisoned/cleaned/unverified state instead of leaving it invisible.

## Locked Decisions (resolved with user 2026-06-30)

1. **VBCSCompiler policy:** force-recycle every build (shut down between queued builds). Not reap-only-when-unhealthy.
2. **Descendant-process scoping:** **Windows Job Object** — assign the runner's build grandchild to a Job Object at launch; reap by terminating the job. Reliably scopes to exactly this build's tree and survives PID reuse; never kills a sibling worktree's live build. Not the parent-PID tree walk.
3. **Artifact quarantine granularity:** **targeted 0-byte/truncated `*.dll` sweep** over `bin/` and `obj/` on failed/aborted exit. Not a blanket force-clean.
4. **Result fidelity (new vector):** two defensive layers — zero-output guard in `test-filtered.ps1` + `result_fidelity` recording in the queue — land independent of the ≥3-way-OR root-cause spike.

## Open Questions

- **Root cause of the ≥3-way-OR empty-output quirk (runtime-coupled — scheduled as a planning-time spike).** Is the ≥3-way OR filter producing empty output because it matches **zero tests** (a malformed/over-long filter string built by the caller) or because `dotnet test --verbosity normal` emits a **summary format `test-filtered.ps1`'s regex misses** for that case? The 2-way pairs print correctly, which points at filter construction, but this must be confirmed by observing a real run before any root-cause fix (beyond the defensive zero-output guard) is committed.
- Truncated-but-nonzero artifacts: the 0-byte sweep must also catch a partially-written DLL whose size is nonzero but is not a valid PE image (`CS0009`). Decide the cheap validity check (size threshold vs. PE-header magic-bytes probe) at plan time.
