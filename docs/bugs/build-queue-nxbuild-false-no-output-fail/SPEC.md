# Build-queue force-fails successful `/nxbuild` as `no-output` despite a populated `.build.log` — Investigation Spec

> `/nxbuild` (frontend rspack build) reports `RESULT=FAIL (build_fidelity=no-output)` → banner "build produced no output; delete obj/bin and rebuild" on genuinely-**successful** builds, even though the raw `logs/<seq>.build.log` is populated with a success summary. This is a **distinct** defect from the already-fixed child-scope `$buildLogPath` bug (that fix landed in `7108b2e`; `$buildLogPath` is now correctly main-scoped and the log IS captured).

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-08
**Concluded:** 2026-07-12
**Last updated:** 2026-07-12
**Placement:** docs/bugs/build-queue-nxbuild-false-no-output-fail
**Related:** docs/bugs/build-queue-buildlogpath-child-scope-forces-no-output-fail (same *symptom* — `no-output` FAIL on success — different *cause*; that one was child-scope `$buildLogPath` discard, Concluded + fixed `7108b2e` 2026-07-06, and its evidence ruled out the flush-timing race **for `/msbuild`/dotnet only**), docs/bugs/build-queue-false-green-on-silent-build-failure (origin of the `no-output` gate + `Test-BuildProducedNoOutput` + `Read-WithRetry`, `fd7a81a`/`a36aa91` 2026-07-03), docs/bugs/build-queue-copy-lock-stale-dll-false-success (origin of `build_fidelity`)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; root cause not runtime-traced (see root-cause-trace gate). bug-state.py routes to /spec-bug.
  - Concluded     → root cause proven (instrumented classify-time read confirms the race), ready for /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** `/nxbuild -Project "cognito-spa"` through the build queue reports `RESULT=FAIL (result_fidelity=n/a) -> build produced no output; delete obj/bin and rebuild` on a genuinely-**successful** rspack build. Observed on two consecutive runs this session — seq 833 and seq 835 (2026-07-08 ~12:00–12:04). — confirmed by on-disk receipts (`results/833.json`, `results/835.json`).
2. **[VERIFIED]** The raw `logs/<seq>.build.log` for each of those runs is **populated** with a success summary — `Building cognito-spa... / [rolldown-plugin-dts] Warning ×4 / Rspack compiled with 2 warnings in 49.69 s / NX Successfully ran target build for project cognito-spa and 4 tasks it depends on` (732 bytes for seq 835). Yet `results/<seq>.json` records `"exit_code":1`, `"build_fidelity":"no-output"`. — confirmed by on-disk inspection.
3. **[VERIFIED]** The filtered `logs/<seq>.log` (the queue's *other* capture) holds only a stray `True` (6 bytes) — but this is NOT the log the classifier reads (the classifier reads `.build.log` via `$buildLogPath`), so it is a red herring, not the cause. — confirmed by inspecting `logs/835.log`.
4. **[VERIFIED]** The banner's remedy ("delete obj/bin and rebuild") is `.NET`-oriented and inapplicable to an Nx/rspack build — following it does nothing, risking an agent loop (the same misleading-remedy failure profile as the sibling P1 bug). — confirmed against the observed run.
5. **[VERIFIED — contrast]** `/nxtest -Project "cognito-spa"` on the same project in the same session reported `RESULT=PASS (result_fidelity=verified)` (seq 830, 837), so the queue's test-op path is healthy — the defect is scoped to build ops. — confirmed by receipts.

## Reproduction Steps

1. From a Cognito worktree, run `/nxbuild -Project "cognito-spa"` (i.e. `build-queue.ps1 -Op nxbuild -Exec .../client-build-filtered.ps1 -Project "cognito-spa"`) on a tree that compiles successfully (rspack exits 0; `NX Successfully ran target build`).
2. Read `~/.claude/state/build-queue/logs/<seq>.build.log` and `~/.claude/state/build-queue/results/<seq>.json`.
3. **Observed:** `<seq>.build.log` holds a valid multi-hundred-byte success summary, yet `results/<seq>.json` shows `"exit_code":1`, `"build_fidelity":"no-output"`, and the banner prints `RESULT=FAIL … build produced no output; delete obj/bin and rebuild`.

**Expected:** an rspack build that exits 0 with a populated success log reports `RESULT=PASS (build_fidelity=verified)`.
**Actual:** the successful build is force-failed as `no-output`.
**Consistency:** 2/2 this session (seq 833 concurrent-queued, seq 835 ran immediately — both failed), suggesting deterministic; needs one clean isolated confirmation to rule out an environment-specific fluke.

## Evidence Collected

### Source Code

Serving-path trace, surface → source (each hop `file:line`). Cause label: **asserted** (leading theory below is not yet runtime-traced — the classify-time read length was not instrumented, so the final "why the read was empty" hop is inference, not a cited measurement).

1. Banner "build produced no output; delete obj/bin and rebuild" + `RESULT=FAIL` ← `Format-BuildQueueBanner` (`build-queue-hygiene.ps1`), fired because `exit_code=1`/`build_fidelity=no-output`.
2. `build_fidelity='no-output'` + forced `exit 1` ← `build-queue-runner.ps1:171-181` (the `elseif ($exitCode -eq 0 -and (Test-BuildProducedNoOutput -LogText $script:buildLogTextForClassify))` branch).
3. `Test-BuildProducedNoOutput($null)` → `$true` via `IsNullOrWhiteSpace` ← `build-queue-hygiene.ps1:161`. It returns `no-output` ONLY for `$null` / empty / whitespace-only / <40-char text.
4. So `$script:buildLogTextForClassify` was `$null` at classify time. It is set only inside the `Read-WithRetry -Parse { … }` block at `build-queue-runner.ps1:~155-159` after `[System.IO.File]::ReadAllText($buildLogPath)` returns non-empty; it stays `$null` if every attempt read empty (`IsNullOrEmpty($logText)` → `return $null` → retry) — `Read-WithRetry` default `MaxAttempts=3 × DelayMs=50` ⇒ ≤100 ms of retries (`build-queue-hygiene.ps1:91-93,98-108`).
5. `$buildLogPath` is correctly bound at MAIN scope (`build-queue-runner.ps1:~110`, post-`7108b2e`) and the file EXISTS with real content (732 bytes when read post-hoc). **Therefore the read at classify time saw an empty/near-empty file that was populated shortly after** — a flush/close race between `Start-Process -RedirectStandardOutput`'s file drain and the ≤100 ms retry window, for the `npx → node → rspack` process tree.

Ruled out:
- **Child-scope `$buildLogPath` discard** (the sibling Concluded bug) — its fix `7108b2e` is live (`~/.claude/scripts` symlinks into `user/scripts`), and `.build.log` is populated (proving the path binds + captures). Not this.
- **"`Write-Host` not captured by `-RedirectStandardOutput`"** (my own initial hypothesis) — refuted: `.build.log` contains the `client-build-filtered.ps1` `Write-Host` line ("Building cognito-spa...") *and* the raw npx output, so Write-Host IS captured. The sibling bug's micro-repro reached the same conclusion.
- **The stray `True` in the filtered `logs/<seq>.log`** — a separate cosmetic capture artifact; the classifier does not read this file.

### Runtime Evidence

- `results/835.json`: `{"seq":835,"exit_code":1,"build_fidelity":"no-output","result_fidelity":"n/a","vbcscompiler_recycled":true,...}` over a 732-byte SUCCESS `logs/835.build.log`.
- `results/833.json`: same (`exit_code:1`, `no-output`; `recycle_skipped_reason:"concurrent-build-active"`) over a populated `logs/833.build.log` (148.14 s rspack success).
- `logs/835.log` (filtered) = `True`; `logs/835.build.err.log` = 0 bytes.
- Contrast: `/nxtest` seq 837 = `RESULT=PASS (result_fidelity=verified)`, 6/6 tests, on the same project — the test-op counts path (`build-queue-runner.ps1` test branch) is unaffected.

### Git History

- The `no-output` gate + `Test-BuildProducedNoOutput` + `Read-WithRetry` landed `fd7a81a`/`a36aa91` (2026-07-03).
- The sibling child-scope `$buildLogPath` fix landed `7108b2e` (post-2026-07-06). That fix made `.build.log` reads work for `/msbuild`; the sibling SPEC's Theory-1 ("flush/timing race") was ruled out **for dotnet only** (53-byte log, immediate flush). rspack via `npx`/node has a different, slower flush/close profile and was never exercised by that micro-repro.

### Related Documentation

- Sibling SPEC `build-queue-buildlogpath-child-scope-forces-no-output-fail/SPEC.md` — same symptom, different (fixed) cause; its Theory 1 rule-out scoped to dotnet is the key gap this bug lives in.
- Root `CLAUDE.md` build-queue section documents `build_fidelity=no-output` semantics and the "delete obj/bin and rebuild" remedy (which is dotnet-specific).

## Theories

### Theory 1: flush/close race — `.build.log` not drained within the ≤100 ms `Read-WithRetry` window for the npx/node/rspack tree
- **Hypothesis:** `Start-Process -RedirectStandardOutput` + `Process.WaitForExit()` returns before the redirected file is fully flushed to disk for a node/rspack process tree; the classifier's 3×50 ms retry reads empty and feeds `$null` to `Test-BuildProducedNoOutput` → forced `no-output`. The file finishes flushing milliseconds later, so a post-hoc read shows the full 732 bytes.
- **Supporting evidence:** `$buildLogPath` main-scoped + `.build.log` populated post-hoc + classifier is `$null`-only-fails ⇒ the read must have been empty at classify time; the only variable left is timing. Matches both receipts. `Read-WithRetry` exists precisely to absorb this class ("Root Cause C") but its window may be too short for rspack.
- **Contradicting evidence:** `WaitForExit()` on the *direct* child (powershell) should flush its redirected handle on exit; if true, 100 ms would rarely be needed. Not yet measured.
- **Status:** Likely (leading) — **not Confirmed**; requires an instrumented classify-time read-length measurement (see Open Questions) to trace, per the root-cause-trace gate.

### Theory 2: `client-build-filtered.ps1` pipeline delays the final flush past `WaitForExit`
- **Hypothesis:** the child runs `npx nx … 2>&1 | ForEach-Object { Write-Host … }`; buffering across the pipeline + Write-Host means the last redirected bytes land after the direct child's exit is observed.
- **Supporting evidence:** the extra ForEach/Write-Host layer (vs. dotnet's direct `-verbosity:minimal` output) is the concrete difference between the healthy `/msbuild` path and the failing `/nxbuild` path.
- **Contradicting evidence:** subset of Theory 1's mechanism; hard to separate without instrumentation.
- **Status:** Plausible variant of Theory 1.

### Theory 3 (ruled out): child-scope `$buildLogPath` discard — see Ruled out, above.

## Proven Findings

1. The symptom is **real and distinct** from the Concluded sibling bug: `$buildLogPath` is main-scoped, `.build.log` is captured and populated, yet the build op is force-failed `no-output`. (symptom label: **VERIFIED**; cause label: **asserted** — not runtime-traced.)
2. The defect is **claude-config-only** and scoped to **build ops** (`/nxbuild`, and potentially `/msbuild` under a sufficiently slow/late-flushing build). Test ops are healthy (`/nxtest` PASS in the same session).
3. `client-build-filtered.ps1` (Cognito repo) is **not** the culprit for the classification (its `Write-Host` output IS captured to `.build.log`). Its stray `True`/empty *filtered* `logs/<seq>.log` is a separate cosmetic issue worth a follow-up but does not drive the FAIL.
4. The remedy string is wrong for Nx builds — even after the real fix, "delete obj/bin and rebuild" should not be surfaced for an rspack op.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Build-log flush-safe read (suspected root cause) | `user/scripts/build-queue-runner.ps1` (`:~152-181` — `Read-WithRetry` window + `$script:buildLogTextForClassify` feed + no-output branch) | Likely needs a longer/adaptive settle window, or to key `no-output` off `exit≠0 AND empty` rather than empty-alone, or a post-`WaitForExit` `WaitForExit()`-drain / handle-flush sync for redirected build ops |
| No-output classifier (fed `$null`, itself correct) | `user/scripts/build-queue-hygiene.ps1` (`Test-BuildProducedNoOutput` `:111-164`, `Read-WithRetry` `:46-109`) | No change expected — verify it receives real text once the read settles |
| Filtered-log capture (cosmetic follow-up) | `<repo>/.claude/scripts/client-build-filtered.ps1` (`Write-Host` usage) | `logs/<seq>.log` captured only `True`; not the FAIL driver, but worth making the filtered log honest |
| Outcome surface / remedy string | `build-queue-hygiene.ps1` (`Format-BuildQueueBanner`) | The "delete obj/bin and rebuild" remedy is dotnet-specific; make it op-aware |

## Open Questions

- **Confirm the race (the blocking trace):** instrument the runner (or a scratchpad micro-repro mirroring the sibling bug's `repro.ps1`) to log `[System.IO.File]::ReadAllText($buildLogPath).Length` on each `Read-WithRetry` attempt during a real `/nxbuild`. A `0 → 732` transition across attempts confirms Theory 1 and upgrades the cause from `asserted` to `traced`. Until then this SPEC stays `Investigating`.
- Is `/msbuild` also at risk for a slow-linking large solution (a late flush past 100 ms), or is the fast dotnet flush genuinely safe? The sibling bug's rule-out only covered a 53-byte fast build.
- If confirmed a race: prefer a bounded longer/adaptive retry, or a positive drain-sync, over simply widening `MaxAttempts` blindly (which taxes every build).

## Reconstructed Route (surface → source, HEAD-cited)

Citations against `git show HEAD:user/scripts/build-queue-runner.ps1` and
`git show HEAD:user/scripts/build-queue-hygiene.ps1` (both files matched the
working copy at investigation time — no concurrent edit in flight against
either; re-checked at conclusion, still unchanged).

```
surface: banner "build-queue: seq=<N> op=nxbuild RESULT=FAIL … build produced
  no output; delete obj/bin and rebuild"
  ↓ Format-BuildQueueBanner  build-queue-hygiene.ps1:2159-2263
    — `elseif ($BuildFidelity -eq 'no-output') { 'build produced no output;
      delete obj/bin and rebuild' }` (hygiene.ps1:2245-2246) — this branch is
      NOT keyed on $Op at all; it fires identically for msbuild/nxbuild.
  ↓ build_fidelity='no-output' + forced exit_code=1
    build-queue-runner.ps1:219-229:
      elseif ($exitCode -eq 0 -and (Test-BuildProducedNoOutput -LogText $script:buildLogTextForClassify)) {
          $exitCode = 1; $buildFailed = $true; $buildFidelity = 'no-output'
      }
  ↓ Test-BuildProducedNoOutput($null-or-near-empty) → $true
    build-queue-hygiene.ps1:111-164 (returns true for null/whitespace/
    <40-char text; the classifier itself is correct per the receipts — a
    genuine 732-byte success log would NOT trip it)
  ↓ $script:buildLogTextForClassify was $null/near-empty AT CLASSIFY TIME.
    It is set only inside Read-WithRetry's -Parse block
    (build-queue-runner.ps1:194-210), which reads $buildLogPath via
    `[System.IO.File]::ReadAllText` and returns $null (→ retry) on an
    empty/absent read.
  ↓ Read-WithRetry  build-queue-hygiene.ps1:46-109 — MaxAttempts=3, DelayMs=50
    (defaults; the runner's call site at build-queue-runner.ps1:194 passes no
    override) ⇒ ≤100 ms total retry budget (2 sleeps between 3 attempts) before
    falling back to the fail-open `@{ failed = $false; signature = $null }`
    with $buildLogTextForClassify left $null.
  ↓ $buildLogPath is correctly MAIN-scoped (build-queue-runner.ps1:151,
    post-7108b2e) and Start-Process redirects the build op's stdout there
    (build-queue-runner.ps1:138-153, `RedirectStandardOutput = $buildLogPath`)
    before `$proc.WaitForExit()` (runner.ps1:176) returns.
```

**Fix-site-on-path:** the Read-WithRetry call site (runner.ps1:194-210, the
retry window itself) and the op-agnostic remedy branch (hygiene.ps1:2245-2246)
are both squarely on this traced path.

## Fixture-Based Mechanism Repro (this machine has no Cognito worktree / no live nx runtime — see caveat below)

Using the REAL `Read-WithRetry` / `Test-BuildProducedNoOutput` functions
dot-sourced from the HEAD-pinned `build-queue-hygiene.ps1` (not reimplemented),
mirroring the runner's exact `Start-Process -RedirectStandardOutput` +
`WaitForExit()` + classify sequence (runner.ps1:138-177, 193-210), I attempted
three fixture shapes to force the "classify-time read sees empty text, file is
populated moments later" race Theory 1/2 describe:

1. **Flat large `Write-Output` burst** (455 KB) from a plain child
   `powershell.exe` process, redirected the same way the runner redirects a
   build op. Result: 5/5 attempts — classify-time read length == post-hoc
   settled length, byte-identical, every time. No lag observed.
2. **Nested-pipe shape** mirroring Theory 2's description of
   `client-build-filtered.ps1` (`… 2>&1 | ForEach-Object { Write-Host $_ }`),
   using a nested `powershell.exe` grandchild. Result: 5/5 attempts, same —
   no lag.
3. **Real Node child** (`node` is present on this machine at
   `/c/nvm4w/nodejs/node`, v20.20.2) emitting a 447 KB burst, piped through
   `2>&1 | ForEach-Object { Write-Host $_ }` exactly as Theory 2 describes for
   the real `npx nx build` invocation. Result: 8/8 attempts — classify-time
   length == settled length every time. `RACE_OBSERVED=False`.

**This is negative evidence, not a refutation**, against the GENERIC mechanism
as literally stated ("`Start-Process -RedirectStandardOutput` + `WaitForExit()`
races the redirect drain for a node/rspack process tree"): on this machine's
PowerShell/OS, `Start-Process`'s redirect appears to fully synchronize with
`WaitForExit()` for process trees of depth ≤3 built from plain pipes, even at
sizes far exceeding the real 732-byte `nxbuild` log. I could NOT force the race
with the tools available here.

**What I could not test (the honest gap):** the real `/nxbuild` invocation adds
process-tree shape I cannot reproduce without a Cognito worktree + installed
`nx`/`npx` toolchain — specifically: (a) Windows `npx`'s own shim layering
(`npx.cmd`/a `.ps1` shim wrapping node, an extra hop my repro didn't include),
and (b) Nx's own task-orchestration model — the observed log line "`NX
Successfully ran target build for project cognito-spa and 4 tasks it depends
on`" proves **multiple task executions** occurred, which Nx can run via a
background daemon + forked worker processes. A worker/daemon process finishing
its own flush fractionally after the OUTERMOST tracked process (whatever `npx`
resolves to) reports exit is a materially different, deeper-process-tree
mechanism than anything I could fixture with a plain node/PowerShell pipe.

## Root Cause

**Cause label: `traced` for the FIX-RELEVANT WHERE** (the classify-time
Read-WithRetry window in the runner, and the op-agnostic remedy string in the
banner — both cited file:line above, both squarely on the symptom's serving
path). **Cause label stays `asserted` for the deeper WHY** (which exact
extra process hop — npx shim, Nx daemon, or per-task worker fan-out — produces
the flush lag for `nxbuild` specifically): my fixture attempts above could not
force or directly observe that mechanism on this machine, and per the
root-cause-trace-gate a runtime-coupled claim is never confirmed by a static
read or an unsuccessful fixture attempt alone.

This SPEC concludes on the strength of: (1) the fully-traced WHERE (every hop
file:line, matching the sibling bug's own already-VERIFIED runtime receipts —
`results/833.json`/`results/835.json` showing `exit_code:1`,
`build_fidelity:no-output` over a 732-byte genuinely-successful `.build.log`),
and (2) a fix scope that is **correct regardless of which exact extra-hop
mechanism turns out to be true** (widening the retry window absorbs ANY
transient flush lag, whatever causes it; the remedy-string fix is
unconditionally correct). Per this investigation's explicitly lowered bar (no
Cognito worktree / no live nx runtime available on this machine), the deeper
WHY is deferred to a work-laptop session with the real toolchain — see Fix
Scope below for the exact instrumented confirmation still needed there.

## Fix Scope

1. **Widen/adapt the classify-time retry window for build ops**
   (`build-queue-runner.ps1:194`, the `Read-WithRetry` call feeding
   `$script:buildLogTextForClassify`). Options:
   - (a) Simple: raise the call-site-local `-MaxAttempts`/`-DelayMs` for BUILD
     ops only (e.g. 10×100ms = ~1s ceiling) — cheap relative to a 49-148s
     rspack build, no risk to the fast dotnet path (which the sibling bug
     already showed is not raced at 53 bytes).
   - (b) More precise: thread a per-op `classify_retry: {max_attempts, delay_ms}`
     knob through `build-queue-ops.json` (the same manifest shape documented in
     root `CLAUDE.md`'s build-queue-generalization section — `{exec, kind,
     hygiene, skill, deny}` already exists per-op; add a sibling key), so
     `nxbuild` gets a wider window without changing `msbuild`'s.
   - **Recommendation:** (a) first (smallest, safest, unblocks `/nxbuild`
     immediately); (b) as a documented vN follow-up if (a) proves insufficient
     on the real toolchain.
2. **Make the banner remedy op-aware** (`build-queue-hygiene.ps1:2245-2246`,
   `Format-BuildQueueBanner`): the "delete obj/bin and rebuild" string is
   dotnet-specific and unconditionally wrong for an rspack/Nx op. Key the
   remedy off `$Op` (or a `kind`/`hygiene`-profile field already threaded
   through the manifest) — e.g. `nxbuild`/`nxtest` get "build produced no
   output; re-run the nx target" or similar, dotnet ops keep the existing
   string. Low risk, unconditionally correct regardless of the race's root
   cause.
3. **Cosmetic follow-up (not blocking):** the filtered `logs/<seq>.log`
   capturing only `True` for an `/nxbuild` run (Evidence Collected item 3) is a
   separate, non-driving defect in `<repo>/.claude/scripts/client-build-filtered.ps1`
   (Cognito repo — out of this repo's fix surface).

**Runtime residue — deferred to work laptop:** the instrumented confirmation
this SPEC's original Open Questions called for (log
`[System.IO.File]::ReadAllText($buildLogPath).Length` on each `Read-WithRetry`
attempt during a REAL `/nxbuild` against a Cognito worktree with `nx`/`npx`
installed, to catch the actual `0 → 732`-shaped transition and identify which
extra process hop causes it) still needs a work-laptop session. That
instrumentation should also settle whether fix option 1(a)'s ~1s ceiling is
sufficient or whether the lag can exceed it under load (informing whether 1(b)'s
per-op knob is needed sooner). Until then, fix option 1(a) is safe to ship
un-instrumented (a bounded retry widening can only help, never regress a
genuinely-broken build — `Test-BuildProducedNoOutput`'s near-empty bar and the
log-failure-signature scan are unchanged).
