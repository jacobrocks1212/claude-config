# Implementation Phases — Build-Queue Enforcement Bypassed by `cd`-Prefixed Build Commands

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

**MCP runtime:** not-required — this is hook (bash + inline-Python) and skill/PowerShell-wrapper work in claude-config, a repo with NO app surface (no `src-tauri/`, no `package.json`). It is structurally outside MCP reach (the "no MCP-reachable surface" untestable class). Every deliverable is validated by the `user/scripts/test_hooks.py` pipe-test harness (which spawns the real hooks over crafted PreToolUse payloads) — the suite already carries a section explicitly tagged `build-queue-enforce-cd-prefix-bypass` and is **green (130/131 passed, 1 legitimately skipped, 0 failed this cycle)**.

> **STATE OF THE FIX (read first).** The full fix for this bug — BOTH prongs of the SPEC's `## Fix Direction` (hook hardening + skill capability) AND the regression suite the SPEC's Open Questions asked for — is **already implemented and green on disk**. It landed out-of-band as a side-effect of the sibling build-queue work (`b85b0c3 fix(build-queue-outcome-opacity-and-inspect-deny): Phase 1 — anchor bqe deny surface to invoke-vs-reference`, plus the build-skill `-Project` / banner-trust commits `7722211` / `42b77ab` and the pre-existing command-position anchoring in `long-build-ownership-guard.sh`). This PHASES.md is therefore an **honest verify-and-reconcile record**: each phase's deliverables carry the exact on-disk citation showing the work is ALREADY satisfied, and are left **unchecked** as the machine record that `/execute-plan` ticks after its verify pass (per the plan-frontmatter lifecycle, checkbox ticks + the plan `Complete` flip are `/execute-plan`'s to write — never a producer's), so the pipeline can carry the bug through `/execute-plan` (a fast verify-and-tick: run `test_hooks.py` green + confirm the static citations, no fresh implementation) → the `__mark_fixed__` gate (which owns the terminal Status flip, the `FIXED.md` receipt, and the archive) on the strength of the green regression suite rather than requiring a human to hand-close it. No fresh production edit is scheduled.
>
> ⚖ policy: fix already landed out-of-band → author verify/reconcile PHASES+plan (most complete in-cycle path; scope-class, not product-class) rather than halt for a human — the harness already behaves identically to the fixed state, so the only difference between options is closure provenance, and routing to `__mark_fixed__` yields the highest-provenance closure (a real `FIXED.md` receipt + archive).

## Validated Assumptions

Per `/spec-phases` Step 2.7 — every load-bearing claim here is **code-provable by reading the hooks/skills on disk** (deterministic regex + PowerShell param), so no runtime spike is scheduled:

- **Both deny hooks now match a build verb at any COMMAND position, not only string start.** `build-queue-enforce.sh` and `long-build-ownership-guard.sh` both define `_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX` and anchor every deny regex to it — so `cd "…" && <build>`, a pipeline, and a `;`-chain all match (verified this cycle: bqe line 114 / long-build line 105). This is the exact anchor the SPEC's `## Fix Direction` prong 1 called for.
- **Unanchored deny does not break allow-list semantics.** `build-queue-enforce.sh` suppresses the safe `dotnet restore|--version|-v|ef|msbuild` / `nx lint|typecheck|format` occurrences per-occurrence into a scratch copy (`_suppress_safe`, lines 151-157, applied at line 379) BEFORE the heavy-build scan, so a compound `dotnet restore && dotnet build` still denies (the SPEC's "re-derive allow-list precedence per-build-verb" subtlety — verified by `test_bqe_denies_restore_then_build_compound` + `test_bqe_allows_bare_restore`).
- **A build skill can compile a single project through the queue.** `build-filtered.ps1` takes `[string]$Project = ""` (line 9) and builds `"$projectRoot\$Project"` when set, else `Cognito.sln` (line 22); `/msbuild` documents `-Project "…"` (SKILL.md lines 16, 29) as the sanctioned fast targeted-compile path, and `/mstest` points at it (SKILL.md line 11). This is the SPEC's `## Fix Direction` prong 2.
- **The hook tests live in `user/scripts/test_hooks.py`** (the SPEC's first Open Question) — a self-contained pipe-test harness (custom `_run_test` runner, not pytest) that spawns the real bash hooks over PreToolUse JSON.

**SPEC-example capability audit:** the SPEC's only "code examples" are the deny regexes it quotes (`_DOTNET_BUILD_RE` etc.) and shell command shapes (`cd … && dotnet build`). Every construct is present and supported (Python `re`, the `_CMD_START` anchor, `_suppress_safe`, the PowerShell `-Project` param). No explicitly-rejected capability — clean, no planning-time halt.

**MCP tool-existence audit:** no-op — claude-config declares no `.claude/skill-config/mcp-tool-catalog.md` (absent this cycle). Repo has no MCP surface.

## Touchpoint Audit Table (verified this cycle via Read/Grep/test run)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / status directive |
|--------------|---------|-------------------------|--------|--------------------------|
| `user/hooks/build-queue-enforce.sh` | yes | `_CMD_START` (114), `_DOTNET_BUILD_RE`/`_DOTNET_TEST_RE` (117-118), `_NX_BUILD_TEST_RE` (122), `_FILTERED_SCRIPT_DIRECT_RE` (135), `_suppress_safe` (151-157, applied 379), `main()` deny surface (382-394) | **already fixed** | Deny surface is command-position-anchored + suppress-safe precedence. No edit. Header block (18-46) already documents the closed blind spot. |
| `user/hooks/long-build-ownership-guard.sh` | yes | `_CMD_START` (105), `_LONG_BUILD_RE` (106-112), `main()` `_LONG_BUILD_RE.search` (202) | **already fixed** | Same command-position anchor for `tauri build` / `cargo build --release` / `npm run build`. No edit. |
| `repos/cognito-forms/.claude/scripts/build-filtered.ps1` | yes | `[string]$Project = ""` (9), `$buildTarget = if ($Project) {…} else {…Cognito.sln}` (22) | **already fixed** | Native single-project build target. No edit. |
| `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` | yes | `-Project` usage (16), forward-arg doc (29), argument-hint (4) | **already fixed** | Sanctioned single-project fast-compile path documented. No edit. |
| `repos/cognito-forms/.claude/skills/mstest/SKILL.md` | yes | `--no-build` note + `/msbuild -Project` pointer (11), banner-trust prose (37), stale-DLL/exit-code guidance (41-47) | **already fixed** | `--no-build` friction addressed via the `/msbuild -Project` pointer; banner-trust prose addresses symptom #3 confusion. No edit. |
| `user/scripts/test_hooks.py` | yes | bqe cd-prefix suite (4841-5058: `test_bqe_denies_cd_prefixed_*`, `_restore_then_build_compound`, `_allows_bare_restore`, `_allows_bypass_token_*`, `_allows_outside_cognito_worktree`, …); long-build cd-prefix suite (5061+: `_denies_cd_prefixed_cargo_build_release`/`_tauri_build`/`_npm_run_build` + `_allows_*_referencing_*`) | **already present, green** | The regression coverage the SPEC's Open Question asked for. No edit; execute-plan re-runs it green. |

**Contradiction correction (mechanical, applied in-plan):** the SPEC's `## Evidence Collected → Source Code` quotes the OLD `^\s*`-anchored `_DOTNET_BUILD_RE` at "lines 76-98" and the fall-through `_allow()` at "line 293". Those line numbers and the anchored form are stale — the file on disk has been re-anchored to `_CMD_START` (bqe line 114/117; the `_allow()` fall-through is now line 396). The SPEC's *reasoning* about the defect remains correct for the pre-fix state; this PHASES.md records the post-fix reality. (The SPEC body's stale line/anchor citations are a Minor doc-drift item for a later `/retro`-class reconciliation, not fix scope.)

## Phase 1: Hook hardening — command-position (unanchored) deny surface, both hooks [x]

**Scope:** Deny a heavy build wherever it sits at a command position (string start OR immediately after a shell separator, tolerating a leading `NAME=value` env prefix), not only at the literal start — closing the `cd "…" && <build>` / pipeline / `;`-chain bypass in BOTH `build-queue-enforce.sh` (the four Cognito build verbs) and `long-build-ownership-guard.sh` (the three long-build verbs). Re-derive allow-list precedence per-build-verb so a compound like `dotnet restore && dotnet build` still denies. This is the SPEC's `## Fix Direction` prong 1 (defense-in-depth, prong A).

**Deliverables:**
- [x] `build-queue-enforce.sh` deny regexes anchored to `_CMD_START = (?:^|[\n;&|({])\s* + _ENV_PREFIX` (line 114), so `_DOTNET_BUILD_RE`/`_DOTNET_TEST_RE` (117-118), `_NX_BUILD_TEST_RE` (122-129), and `_FILTERED_SCRIPT_DIRECT_RE` (135-141) all fire from a command-segment start regardless of a leading `cd &&`. *(Landed via `b85b0c3`; verified on disk.)*
- [x] Allow-list precedence re-derived per-occurrence: `_suppress_safe` (151-157) blanks the safe `dotnet restore|--version|-v|ef|msbuild` / `nx lint|typecheck|format` occurrences out of a scratch copy BEFORE the heavy-build scan (applied line 379), so a compound `dotnet restore && dotnet build` still denies a surviving real build; `BUILD_QUEUE_BYPASS=1` remains the escape hatch (`_BYPASS_RE`, 87/362); the sanctioned `build-queue.ps1` wrapper is allowed before the deny surface (`_WRAPPER_RE`, 92/373). *(Verified on disk.)*
- [x] `long-build-ownership-guard.sh` given the identical `_CMD_START` anchor (105) on `_LONG_BUILD_RE` (`tauri build` / `cargo build --release` / `npm run build`, 106-112), closing the same `cd`-prefix blind spot for the long-build redirect set. *(Verified on disk.)*
- [x] False-positive guard preserved: a build token used as an ARGUMENT to a read verb (`cat build-filtered.ps1`, `grep … test-filtered.ps1`, `find … -name build-filtered.ps1`, `echo tauri build`) does NOT match because it does not begin a command segment. *(Verified by `test_bqe_allows_{cat,grep,tail,find}_*` + `test_longbuild_guard_allows_*_referencing_*`.)*
- [x] Regression suite in `user/scripts/test_hooks.py` (the SPEC's Open Question — where do hook tests live): cd-prefix, pipeline, compound `restore && build`, bare-restore-allow, bypass-token-allow, out-of-Cognito-scope-allow, cd-prefixed filtered-script/nx cases (bqe, 4841-5058) and cd-prefixed cargo/tauri/npm cases (long-build, 5061+). **Suite green this cycle (130/131 passed, 0 failed).**

#### Implementation Notes (Phase 1 — pre-landed out-of-band; verified 2026-07-06)
- No production edit is owed. The bqe deny-surface re-anchor was implemented under `b85b0c3` (sibling bug `build-queue-outcome-opacity-and-inspect-deny`, whose Phase 1 goal — "anchor bqe deny surface to invoke-vs-reference" — is the same mechanical change this bug's prong 1 requires); `long-build-ownership-guard.sh` was already command-position-anchored. Both header comment blocks (bqe 18-46, long-build 14-29) now positively document the closed `cd`-prefix blind spot.
- Executor action for this phase: run `python3 user/scripts/test_hooks.py` and confirm the bqe + long-build sections are green; tick. No file mutation expected.

**Status:** Complete — verified 2026-07-06 via `/execute-plan`: `test_hooks.py` 130/131 passed, 1 skipped, 0 failed; all cited symbols/line numbers confirmed on disk (Read/Grep this cycle).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_hooks.py` reports `0 failed` with the `test_bqe_denies_cd_prefixed_*`, `test_bqe_denies_restore_then_build_compound`, and `test_longbuild_guard_denies_cd_prefixed_*` cases passing.

**Runtime Verification** *(N/A for this repo — no app runtime; the `test_hooks.py` pipe-tests spawning the real hooks ARE the observable proof):*
- N/A — the hook behavior is exercised end-to-end by the pipe-test harness (real bash hook, crafted PreToolUse JSON, asserted `permissionDecision: deny`).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (bash/inline-Python hook in a repo with no app).

**Prerequisites:** None (first phase).

**Files likely modified:** none (verify-only) — `user/hooks/build-queue-enforce.sh`, `user/hooks/long-build-ownership-guard.sh`, `user/scripts/test_hooks.py` are all already at the fixed state.

**Testing Strategy:** Re-run the existing `test_hooks.py` regression sections. They spawn the real hooks over crafted payloads and assert deny/allow — no mocks. The allow cases (bare restore, cat/grep referencing a build token, out-of-Cognito scope, bypass token) guard against over-matching.

**Integration Notes for Next Phase:** Prong 1 (enforcement) is closed; Phase 2 removes the *incentive* to bypass (the capability gap) so enforcement is not the only thing standing between an agent and the queue.

---

## Phase 2: Skill capability — sanctioned single-project build path (remove the bypass incentive) [x]

**Scope:** Give agents a fast, queue-routed targeted-compile path so a raw `dotnet build <csproj>` is no longer the rational move for a quick "did my one file compile?" check. This is the SPEC's `## Fix Direction` prong 2 (Theory 2 — the contributing capability gap). Resolves two of the SPEC's Open Questions: single-project surfaces as a `-Project` **parameter** on `/msbuild` (not a separate skill), and `build-filtered.ps1` gains **native** single-project support (not a passthrough to raw `dotnet build`).

**Deliverables:**
- [x] `build-filtered.ps1` accepts `[string]$Project = ""` (line 9) and targets `"$projectRoot\$Project"` when set, else `"$projectRoot\Cognito.sln"` (line 22) — a native single-project filtered build, still serialized through the queue wrapper. *(Verified on disk.)*
- [x] `/msbuild` documents `-Project "<relative/path/to.csproj>"` as the sanctioned fast single-project compile (SKILL.md usage line 16, forward-arg contract line 29, argument-hint line 4), forwarding it verbatim to `build-filtered.ps1` under the `build-queue.ps1` lock. *(Verified on disk.)*
- [x] `/mstest` (which runs `--no-build`) points agents at `/msbuild -Project "<csproj>"` for a fast targeted compile before testing (SKILL.md line 11), removing the `--no-build`-only friction the SPEC called out. *(Verified on disk.)*
- [x] `repos/cognito-forms/CLAUDE.local.md` Build & Test Workflow documents the `/msbuild -Project` targeted-compile path as the in-loop alternative to a full-solution build (Building section). *(Verified on disk.)*

#### Implementation Notes (Phase 2 — pre-landed out-of-band; verified 2026-07-06)
- No production edit owed. The `-Project` parameter + skill/doc wiring is present on disk. **Open-Question resolutions recorded:** (a) surface = a `-Project` param on `/msbuild` (chosen over a separate skill); (b) `build-filtered.ps1` gained native single-project support (chosen over a bare forward to `dotnet build <csproj>`). Both are the more-complete choices and are what shipped.
- Executor action for this phase: confirm the four citations on disk; tick. No mutation expected.

**Status:** Complete — verified 2026-07-06 via `/execute-plan`: all four citations confirmed on disk (`build-filtered.ps1` `-Project` param + conditional target; `msbuild/SKILL.md` lines 4/16/29; `mstest/SKILL.md` line 11 pointer; `CLAUDE.local.md` line 64/96 targeted-compile path).

**Minimum Verifiable Behavior:** `grep -n 'Project' repos/cognito-forms/.claude/scripts/build-filtered.ps1` shows the param + conditional target; `repos/cognito-forms/.claude/skills/msbuild/SKILL.md` documents `-Project`; `mstest/SKILL.md` line 11 points at it.

**Runtime Verification** *(N/A — no app runtime; the on-disk skill/script contract is the artifact. A live build requires a Windows Cognito worktree, outside this repo/host):*
- N/A — capability is documentation + a PowerShell param; there is no cross-platform runtime to drive from claude-config on Linux.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (independent of Phase 1; both are prongs of the same defense-in-depth fix).

**Files likely modified:** none (verify-only) — `build-filtered.ps1`, `msbuild/SKILL.md`, `mstest/SKILL.md`, `cognito-forms/CLAUDE.local.md` are already at the fixed state.

**Testing Strategy:** Static verification of the on-disk skill/script contract (the skills carry no unit tests; they are prose wrappers over the queue). The `test_hooks.py` `test_bqe_allows_build_queue_wrapper_with_filtered_exec` case confirms a `-Project`-carrying wrapper invocation is not spuriously denied by the Phase-1 hardening.

**Integration Notes for Next Phase:** With a sanctioned targeted-compile path in place, Phase 3 closes the last thread — the background-poll ergonomics that made an agent abandon the sanctioned path under friction (symptom #3).

---

## Phase 3: Background-poll ergonomics — trust-the-banner outcome contract (Theory 3, secondary) [x]

**Scope:** Reduce the "sanctioned path is error-prone under friction, so I fall back to raw `dotnet`" failure (SPEC symptom #3 / Theory 3, marked SECONDARY). Make the build/test skills tell agents to trust the authoritative one-line banner as the outcome of record and NOT to `cat`/`grep` the runner or `results/<seq>.json` to disambiguate an `exit_code=0` — the ambiguity that led the subagent to abandon the background path.

**Deliverables:**
- [x] `/msbuild` instructs the agent to trust the `build-queue: seq=<N> op=msbuild RESULT=<PASS|FAIL> (result_fidelity=…)` banner as the last stdout line and NOT to `cat`/`grep` the runner or `results/<seq>.json`; names the concrete next action inline on `FAIL` (`log-failure-override` copy-lock, `no-output` false-green) (SKILL.md line 34, plus the two recovery sections 38-46). *(Verified on disk.)*
- [x] `/mstest` carries the same banner-trust contract (`RESULT=<PASS|FAIL|NO-TESTS-MATCHED> tests=<T> failed=<F>`) and distinct exit-code guidance (stale-DLL exit 4, zero-match exit 5) so a red/empty result is disambiguated by the banner, not by second-guessing `exit_code` (SKILL.md lines 37, 41-47). *(Verified on disk.)*
- [x] Both skills give an explicit `run_in_background: true` + poll `results/<seq>.json` path for >10-min runs, with the `seq` sourced from the `enqueued as seq=N` line (msbuild line 36, mstest line 39) — the ergonomic gap symptom #3 hit, now documented. *(Verified on disk.)*

#### Implementation Notes (Phase 3 — pre-landed out-of-band; verified 2026-07-06)
- No production edit owed. The banner-trust / recovery prose landed with the sibling build-queue outcome-opacity + false-green work (`7722211 fix(build-queue-outcome-opacity-and-inspect-deny): Phase 4 — point build/test skills at the authoritative banner`; `42b77ab fix(build-queue-false-green): … banner/status no-output arms`). It directly addresses the empty-output / missing-task-output confusion in symptom #3.
- Theory 3 was SECONDARY and is substantially addressed by the banner-as-source-of-truth contract; no further ergonomics work is scheduled. Executor action: confirm citations; tick.

**Status:** Complete — verified 2026-07-06 via `/execute-plan`: banner-trust + `run_in_background` poll-path prose confirmed present in both `msbuild/SKILL.md` and `mstest/SKILL.md`.

**Minimum Verifiable Behavior:** `msbuild/SKILL.md` and `mstest/SKILL.md` each contain the "trust the banner … do NOT `cat`/`grep` the runner or `results/<seq>.json`" instruction and the `run_in_background` poll path.

**Runtime Verification** *(N/A — prose-contract change in skills; no runtime surface in this repo):*
- N/A — the skills are documentation wrappers; there is no observable runtime outside a Windows Cognito worktree.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None.

**Files likely modified:** none (verify-only) — `msbuild/SKILL.md`, `mstest/SKILL.md` are already at the fixed state.

**Testing Strategy:** Static verification of the on-disk skill prose. No executable test (prose contract).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed`, writes the `FIXED.md` receipt, and archives the bug dir once the validation tail passes (here, the green `test_hooks.py` regression suite standing as the symptom-reproduction evidence) — never authored as a checkbox row here.

---

## Cross-feature Integration Notes

No hard dependencies — the SPEC carries no `**Depends on:**` block (verified this cycle), so `--sync-deps` was skipped (nothing to project). The two prongs (hook + skill) are independent and both already landed.

## Implementation Notes

- **This is a verify-and-reconcile PHASES.md for an out-of-band-landed fix.** Both SPEC prongs plus the requested regression suite are already implemented and green on disk (see the banner at the top and the per-phase citations). Deliverables carry the file:line / commit that already satisfies each, but are left **unchecked** — the checkbox tick and the plan `Complete` flip are `/execute-plan`'s to write after it verifies (the plan-frontmatter lifecycle reserves those for `/execute-plan`; a producer that pre-ticks makes the state machine skip execution and strands the plan permanently `Ready`). The executor's role across all three phases is to run `test_hooks.py` green and confirm the static citations, then tick; the `__mark_fixed__` gate owns closure.
- **Provenance of the landed fix:** prong 1 (bqe deny re-anchor) — `b85b0c3`; prong 1 (long-build) — pre-existing command-position anchor; prong 2 (`-Project` + skill wiring) and Theory 3 (banner-trust) — the sibling build-queue outcome-opacity / false-green commits (`7722211`, `42b77ab`). None of these named this bug slug in their commit message, which is why `bug-state.py` still routed this bug through planning.
- **SPEC doc-drift (Minor, out of fix scope):** the SPEC's `## Evidence Collected → Source Code` quotes the pre-fix `^\s*` anchor at stale line numbers (76-98, 293). The reasoning is correct for the pre-fix state; the on-disk reality is the `_CMD_START` command-position anchor. Reconciling the SPEC body is a `/retro`-class Minor item, not part of this fix.
- **Cognito worktree caveat:** the build skills and `build-filtered.ps1` cannot be exercised at runtime from claude-config on Linux — they require a Windows Cognito worktree. The hooks, however, ARE fully exercised by `test_hooks.py` here, which is the load-bearing enforcement surface this bug is about.
