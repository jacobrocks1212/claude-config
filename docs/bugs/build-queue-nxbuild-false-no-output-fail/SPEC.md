# Build-queue force-fails successful `/nxbuild` as `no-output` despite a populated `.build.log` — Investigation Spec

> `/nxbuild` (frontend rspack build) reports `RESULT=FAIL (build_fidelity=no-output)` → banner "build produced no output; delete obj/bin and rebuild" on genuinely-**successful** builds, even though the raw `logs/<seq>.build.log` is populated with a success summary. This is a **distinct** defect from the already-fixed child-scope `$buildLogPath` bug (that fix landed in `7108b2e`; `$buildLogPath` is now correctly main-scoped and the log IS captured).

**Status:** Investigating
**Severity:** P1
**Discovered:** 2026-07-08
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
