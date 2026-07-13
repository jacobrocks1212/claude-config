# Implementation Phases — Build-queue force-fails successful `/nxbuild` as `no-output`

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; the fix is verified
via **Pester unit/integration tests** over `user/scripts/build-queue-hygiene.ps1` /
`user/scripts/build-queue-runner.ps1` (the repo's established build-queue verification harness),
the "build-tooling / repo-config, no app integration" untestable class. There is no
`mcp-tool-catalog.md` in this repo, so the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The SPEC's traced WHERE is fix-relevant regardless of the deeper WHY.** The SPEC concludes
  with cause label `traced` for the classify-time `Read-WithRetry` call site
  (`build-queue-runner.ps1:194`, ≤100ms budget) and the op-agnostic remedy branch
  (`build-queue-hygiene.ps1` `Format-BuildQueueBanner`), and `asserted` (not runtime-traced) for
  which exact extra process hop (npx shim / Nx daemon / per-task worker fan-out) produces the
  flush lag. Per the SPEC's own honest gap ("this machine has no Cognito worktree / no live nx
  runtime"), Phase 1 does not attempt to reproduce that deeper mechanism — it widens the retry
  window (which absorbs ANY transient flush lag, whatever causes it — SPEC Fix Scope framing) and
  proves the widening's *arithmetic* against a controlled, real-file-write delay using the actual
  `Read-WithRetry`/`Test-BuildProducedNoOutput` functions (not reimplemented, not mocked).
- **The real `Start-Process -RedirectStandardOutput` race is not reproducible on this machine**
  (SPEC "Fixture-Based Mechanism Repro": 3 fixture shapes, up to 455KB / a real node child, 5-8
  attempts each, `RACE_OBSERVED=False` every time). Phase 1's red/green test therefore does NOT
  attempt to force that specific OS-level race through the real runner's `-Exec` pipeline (a
  documented dead end); it isolates the retry-window arithmetic instead, via a background-thread
  delayed write to a plain file the real `Read-WithRetry` reads — the same technique, at the same
  honesty level, as the SPEC's own fixture repro.

## Cross-feature Integration Notes

**Related (same symptom, different already-fixed cause):**
`docs/bugs/build-queue-buildlogpath-child-scope-forces-no-output-fail` (Concluded/Fixed `7108b2e`)
— that bug fixed the child-scope `$buildLogPath` discard; this bug's fix is additive on top of
that fix (the log path is already correctly main-scoped; this widens how long the classifier
waits for that correctly-scoped file to settle). No shared files require sequencing; both fixes
compose cleanly (this phase does not touch `$buildLogPath`'s scope).

**Related (origin of the mechanisms touched here):**
`docs/bugs/build-queue-false-green-on-silent-build-failure` (origin of `Test-BuildProducedNoOutput`
+ `Read-WithRetry`) and `docs/bugs/build-queue-copy-lock-stale-dll-false-success` (origin of
`build_fidelity`) — both already landed; this phase edits their functions in place (widens a call
site's parameters, adds an op-aware branch) without changing their public contracts.

---

### Phase 1: Widen the build-log classify retry window + make the no-output remedy op-aware

**Scope:** Both SPEC Fix Scope deliverables, implemented together (same files, same Pester gate,
no sequencing benefit to splitting):

1. Widen the classify-time `Read-WithRetry` window feeding `$script:buildLogTextForClassify`
   (`build-queue-runner.ps1:194`, the no-output branch) from the default 3×50ms (~100ms ceiling)
   to 10×100ms (~1s ceiling) — SPEC Fix Scope recommendation (a), applied to every build op (not
   op-scoped) since a fast dotnet build already settles on attempt 1 and is unaffected.
2. Make `Format-BuildQueueBanner`'s no-output remedy op-aware (`build-queue-hygiene.ps1`): an
   `$Op` matching `^nx` gets an Nx-appropriate remedy string; every other op (including msbuild,
   and any unrecognized future op) keeps the original dotnet-oriented "delete obj/bin and rebuild"
   text — a safe, non-worsening default.

**TDD:** yes. Pester RED first: a build-log classify simulated at 150ms elapsed (past the OLD
100ms budget) misclassifies no-output under the pre-fix parameters; GREEN after widening. The
banner remedy cases are pinned expectations extended in the same change (msbuild's existing pinned
string is preserved verbatim; a new nxbuild case is added).

**Status:** Complete

**Deliverables:**
- [x] `build-queue-runner.ps1:194` (the no-output classify `Read-WithRetry` call, inside the
  `if ($isBuildOp)` block) now passes `-MaxAttempts 10 -DelayMs 100` explicitly, widening the
  settle budget from ~100ms to ~1s. The two OTHER `Read-WithRetry` call sites in the same file
  (the test-counts parse at `$counts = Read-WithRetry -Parse {...}` and the `active.lock`
  re-read at `$lockSeq = Read-WithRetry -Parse {...}`) are UNCHANGED — still the library default
  3×50ms — the widening is scoped to the build-log no-output classify path only.
- [x] `build-queue-hygiene.ps1` `Format-BuildQueueBanner`: the `$BuildFidelity -eq 'no-output'`
  remedy branch now checks `$Op -match '^nx'` first (Nx ops are `hygiene: dotnet`-profiled too per
  the Cognito ops manifest, so the hygiene profile can't disambiguate this — keyed on the op NAME
  instead) and returns `'build produced no output; re-run the nx target (npx nx build)'` for a
  matching op, else the original `'build produced no output; delete obj/bin and rebuild'` text.
- [x] Docstrings for both functions updated to describe the widened window / op-aware remedy
  (not just the code — the SPEC's own citation-by-`file:line` convention depends on the docstrings
  staying accurate).
- [x] Pester: new RED/GREEN pair in `build-queue-runner.Tests.ps1` (`Invoke-DelayedBuildLogClassify`
  helper, background-thread-delayed real file write, drives the REAL `Read-WithRetry` /
  `Test-BuildProducedNoOutput` functions) proving (a) the old 3×50ms budget misclassifies a
  150ms-delayed log as no-output, (b) the new 10×100ms budget classifies the SAME log correctly,
  (c) a log that never arrives (5000ms) still classifies no-output — the widening absorbs a
  transient lag, it does not mask a genuine failure. Plus two source-pin assertions: the runner's
  classify call site carries the widened literal; the other two call sites do not.
- [x] Pester: new cases in `build-queue-hygiene.Tests.ps1` `Format-BuildQueueBanner` — `nxbuild`
  no-output gets the nx remedy; `msbuild` no-output KEEPS the original pinned string (no
  regression, sits alongside the existing WU-1 pin); an unrecognized op falls back to the dotnet
  remedy (safe default).

**Implementation Notes (2026-07-12):** Both fixes are small, surgical, call-site-local edits — no
function signatures changed, no new parameters added to either public function (the widened
values are literals at the ONE call site that needed them; `Format-BuildQueueBanner`'s existing
`-Op` parameter already carried everything the remedy branch needs). The retry-window fix could
not be proven against the SPEC's own suspected root mechanism (the real `Start-Process` npx/Nx
process-tree flush lag — SPEC's fixture repro found this unreproducible on this machine even with
a real node child at 447KB); Phase 1's Pester test instead proves the fix's *arithmetic* — that
widening the retry budget changes the classify outcome for a log that becomes available between
the old and new ceilings — using the real production functions, which is the correct and only
testable unit at this level per the SPEC's own documented honesty about the deeper mechanism.
Gate: `build-queue-hygiene.Tests.ps1` → **178/178** (was 175/175 + 3 new); `build-queue-runner.Tests.ps1`
→ **9/9** (was 4/4 + 5 new); `build-queue.Tests.ps1` → **2/2** (unchanged, regression check);
`build-queue-await.Tests.ps1` → **8/8** (unchanged, regression check). Files:
`user/scripts/build-queue-runner.ps1`, `user/scripts/build-queue-hygiene.ps1`,
`user/scripts/build-queue-hygiene.Tests.ps1`, `user/scripts/build-queue-runner.Tests.ps1`.

**Minimum Verifiable Behavior:** `Import-Module Pester -RequiredVersion 6.0.0 -Force;
Invoke-Pester -Path user/scripts/build-queue-hygiene.Tests.ps1,user/scripts/build-queue-runner.Tests.ps1,user/scripts/build-queue.Tests.ps1,user/scripts/build-queue-await.Tests.ps1`
is green (197/197 total across the four suites), including the new RED-proven-then-fixed
retry-window pair and the op-aware banner cases.

**Runtime Verification** *(checked by Pester — no Tauri/MCP app surface; see the deferred row
below for the one assertion Pester structurally cannot make on this machine):*
- [x] <!-- verification-only --> A build-log classify simulated at 150ms elapsed misclassifies
  no-output under the OLD 3×50ms budget and classifies correctly under the NEW 10×100ms budget,
  using the real `Read-WithRetry`/`Test-BuildProducedNoOutput` functions. **Verified 2026-07-12:**
  `build-queue-runner.Tests.ps1` "widened build-log classify retry window" Describe block, all 5
  cases green (RED-for-the-right-reason case explicitly asserts the pre-fix-shaped misclassification
  still occurs at the OLD parameters — proving the test is not vacuous).
- [x] <!-- verification-only --> `Format-BuildQueueBanner` selects the Nx-appropriate remedy for
  an `nx*` op and preserves the original dotnet remedy for `msbuild`/unknown ops.
  **Verified 2026-07-12:** `build-queue-hygiene.Tests.ps1` "op-aware no-output remedy" Describe
  block, all 3 cases green.
- [ ] <!-- deferred-requires-host: work-laptop with Cognito worktree + nx/npx toolchain --> The
  SPEC's own still-open instrumented confirmation (log
  `[System.IO.File]::ReadAllText($buildLogPath).Length` on each `Read-WithRetry` attempt during a
  REAL `/nxbuild` against a live Cognito worktree, to catch the actual `0 → 732`-byte transition
  and identify which extra process hop causes it, and to confirm the ~1s widened ceiling is
  sufficient under load) is **deferred to a work-laptop session** — this machine has no Cognito
  worktree / no installed `nx`/`npx` toolchain (SPEC's own documented constraint, unchanged by this
  fix). Until that session runs, ship the widened window un-instrumented per the SPEC's own
  closing argument: "a bounded retry widening can only help, never regress a genuinely-broken
  build."

**MCP Integration Test Assertions:** N/A — no app runtime; Pester is this repo's build-tooling
verification harness (see the header line above).

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/build-queue-runner.ps1` — widen the one classify-time `Read-WithRetry` call site
  (verified exists, `:194` pre-fix / now carries `-MaxAttempts 10 -DelayMs 100`).
- `user/scripts/build-queue-hygiene.ps1` — op-aware remedy branch inside `Format-BuildQueueBanner`
  (verified exists, function at `:2159`, remedy branch was at `:2245-2246`).
- `user/scripts/build-queue-runner.Tests.ps1` — new RED/GREEN Describe block + source pins.
- `user/scripts/build-queue-hygiene.Tests.ps1` — new op-aware banner Describe block.

**Testing Strategy:** Pure Pester unit/integration testing — no live Cognito worktree, no real
`nx`/`npx` invocation. The retry-window fix is proven at the level the SPEC's own repro found
testable (the retry arithmetic, via the real functions, against a controlled real-file-write
delay); the remedy fix is proven by direct `Format-BuildQueueBanner` string-equality pins.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate would
ordinarily flip `**Status:**` and write `FIXED.md`, but per the operator's explicit
`operator-directed-interactive` completion protocol for this session, that flip + receipt are
authored directly (mirroring `docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`) rather than
via the pipeline's gate — see `FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
