# Implementation Phases — Long-build + build-queue matcher bypasses

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; these are shell hooks
verified via subprocess **pipe tests** in `user/scripts/test_hooks.py`, the "build-tooling /
repo-config, no app integration" untestable class.

## Close-out note (2026-07-12) — Status NOT flipped to Fixed

This bug's Fix Scope has **two independent decisions**: D1 (enumerate known runner-prefix forms
— the SPEC states a clear recommendation, implemented as-is) and D2 (`bash -c`/`sh -c` string-wrap
scope — the SPEC explicitly leaves this **unresolved at investigation close**, with no
recommended option, requiring "the planner to pick subscan vs documented-limitation
plane-wide"). Fix Scope items 1, 2, and 4 (the two matcher-gap closures + regression tests) are
implemented and fully tested (TDD, RED confirmed against the pre-fix regexes before the fix
landed — see Phase 1/Phase 2 below). D2 is a **genuine fork with no SPEC recommendation** — per
the park-provisional protocol, this session adopted a documented-limitation choice and recorded it
in `NEEDS_INPUT_PROVISIONAL.md` rather than halting, but **this bug's `SPEC.md` Status stays
`Concluded`, NOT `Fixed`, pending operator ratification of that choice.** No `FIXED.md` is written
this pass.

---

### Phase 1: Extend `_LONG_BUILD_RE` (long-build-ownership-guard.sh) — runner-prefix + path-prefix coverage

**Scope:** Close the verified matcher-coverage gaps in the long-build ownership guard: the
canonical runner-prefixed Tauri invocation (`npx tauri build`, `npm run tauri build`,
`cargo tauri build`) and a path-qualified `cargo build --release` all walked past the
raw-binary-token-only enumeration. Keep the existing negative space intact.

**Status:** Complete

**Deliverables:**
- [x] Added a module-level `_PATH_PREFIX` constant (`(?:\.?[\\/])?(?:[^\s;&|]*[\\/])?`, the same
  idiom `build-queue-enforce.sh`'s `_FILTERED_SCRIPT_DIRECT_RE` already uses) so a path-qualified
  binary token still matches.
- [x] Extended `_LONG_BUILD_RE`'s tauri arm to `(?:npx\s+|npm\s+run\s+|cargo\s+)?tauri\s+build(?:\s|$)`
  — an ENUMERATED optional-runner-prefix group (D1: enumeration, not a generic wildcard, per the
  guard's near-zero false-positive charter). This one alternative covers bare `tauri build`,
  `npx tauri build`, `npm run tauri build` (the canonical form), AND `cargo tauri build` (the
  shared `cargo\s+` alternative), with no separate alternative needed for the cargo-subcommand
  form.
- [x] Applied `_PATH_PREFIX` ahead of the whole alternation so `/abs/path/cargo build --release`
  matches.
- [x] Negative space preserved and pinned by test: `npm run tauri dev` and `cargo tauri dev` stay
  ALLOW (the mandatory literal `build` after `tauri\s+` fails); `npm run build:docs` stays ALLOW
  (the trailing `:` fails the `(?:\s|$)` boundary); plain debug `cargo build` (no `--release`)
  stays ALLOW; `cargo check --release` stays ALLOW.
- [x] Regression tests in `test_hooks.py` (all written this session, all GREEN — confirmed RED
  against the pre-fix `_LONG_BUILD_RE` before the extension landed):
  `test_longbuild_guard_denies_npx_tauri_build`,
  `test_longbuild_guard_denies_npm_run_tauri_build`,
  `test_longbuild_guard_denies_cargo_tauri_build`,
  `test_longbuild_guard_denies_path_prefixed_cargo_build_release`,
  `test_longbuild_guard_allows_npm_run_tauri_dev` (negative),
  `test_longbuild_guard_allows_cargo_tauri_dev` (negative).

**Implementation Notes (2026-07-12):** `user/hooks/long-build-ownership-guard.sh` — reworked
`_LONG_BUILD_RE`'s construction (added `_PATH_PREFIX`, rewrote the tauri alternative to the
enumerated optional-runner-prefix form). Verified RED-for-the-right-reason: ran the 4 new
positive tests against the pre-edit hook first (all failed — `npx tauri build` etc. allowed, not
denied), then applied the fix and re-ran — all green. Full suite: `python -m pytest
user/scripts/test_hooks.py -q` → 217 passed (206 baseline + 11 new across both hooks in this bug).
**Files modified:** `user/hooks/long-build-ownership-guard.sh`, `user/scripts/test_hooks.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q -k
"longbuild_guard"` passes, including all 6 new cases above plus every pre-existing
`test_longbuild_guard_*` case (no regression).

**Runtime Verification** *(checked by the pipe tests — the hook's runtime IS the subprocess
pipe)*:
- [x] <!-- verification-only --> `npx tauri build` / `npm run tauri build` / `cargo tauri build` /
  `/usr/local/bin/cargo build --release` → DENY; `npm run tauri dev` / `cargo tauri dev` → ALLOW.
  **Verified 2026-07-12** via the 6 tests named above (all GREEN;
  `python -m pytest user/scripts/test_hooks.py -q -k "longbuild_guard_denies_npx or
  longbuild_guard_denies_npm_run_tauri or longbuild_guard_denies_cargo_tauri or
  longbuild_guard_denies_path_prefixed or longbuild_guard_allows_npm_run_tauri_dev or
  longbuild_guard_allows_cargo_tauri_dev"` → 6 passed).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo.

**Prerequisites:** None. Independent of Phase 2.

**Files likely modified:**
- `user/hooks/long-build-ownership-guard.sh` — `_LONG_BUILD_RE` + new `_PATH_PREFIX` constant.
- `user/scripts/test_hooks.py` — 6 new tests.

**Testing Strategy:** TDD — new positive tests written and run RED against the pre-fix regex
first, then the extension landed and all turned GREEN.

**Integration Notes for Next Phase:** Orthogonal to Phase 2 (different hook, different matcher) —
no shared state.

TDD: yes.

---

### Phase 2: Anchor `_WRAPPER_RE` (build-queue-enforce.sh) — invoke-vs-reference discrimination

**Scope:** Replace the unanchored substring `_WRAPPER_RE` (which exempted ANY command merely
mentioning `build-queue.ps1` anywhere — an echo, a grep, a comment — from the ENTIRE deny surface)
with an anchored invoke-vs-reference pair, mirroring the discrimination the deny surface itself
already uses for `*-filtered.ps1`.

**Status:** Complete

**Deliverables:**
- [x] `_WRAPPER_DIRECT_RE` — a command-segment-start invocation whose token path ends in
  `build-queue.ps1` (`_CMD_START` + the same optional path-prefix idiom used by
  `_FILTERED_SCRIPT_DIRECT_RE`).
- [x] `_WRAPPER_POWERSHELL_RE` — the `powershell(.exe)?|pwsh ... -File <path>build-queue.ps1`
  form (mirrors the pre-existing `_FILTERED_SCRIPT_POWERSHELL_RE` exactly — this is the
  sanctioned skills' real invocation shape).
- [x] Callsite ORs both (`if _WRAPPER_DIRECT_RE.search(command) or
  _WRAPPER_POWERSHELL_RE.search(command): _allow()`), replacing the single unanchored
  `_WRAPPER_RE.search(command)` check.
- [x] The two regexes are defined AFTER `_CMD_START`'s own definition in the file (a Python
  module-load-order requirement — `_CMD_START` must already be bound) with an explanatory NOTE
  left at the original comment location, so a future reader is not confused by the apparent
  forward reference.
- [x] Preserved: the sanctioned wrapper invocation (`REPO_ROOT=... && powershell.exe
  -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op ... -Exec ...`, the
  real shape all four `{msbuild,mstest,nxbuild,nxtest}` skills use) still allows; the manifest-path
  wrapper exemption (`test_bqe_manifest_allows_wrapper_invocation`) still allows; `BUILD_QUEUE_BYPASS=1`
  and the Cognito-remote scope gate untouched; fail-OPEN via JSON `permissionDecision: deny`
  (never a non-zero hook exit) untouched.
- [x] Regression tests in `test_hooks.py` (all written this session, all GREEN — confirmed RED
  against the pre-fix unanchored `_WRAPPER_RE` before the anchoring landed):
  `test_bqe_denies_echo_mention_then_real_build` (`echo build-queue.ps1; dotnet build MySln.sln`
  → DENY — the exact verified bypass row from the SPEC),
  `test_bqe_denies_grep_mention_then_real_build` (`grep foo build-queue.ps1 && dotnet build
  MySln.sln` → DENY),
  `test_bqe_allows_direct_wrapper_invocation_segment_leading` (a direct, non-`-File` segment-leading
  invocation still allows — negative/positive-for-the-legit-path).
- [x] Pre-existing wrapper-allow tests confirmed still GREEN (no regression):
  `test_bqe_allows_build_queue_wrapper_with_filtered_exec`,
  `test_bqe_manifest_allows_wrapper_invocation`.

**Implementation Notes (2026-07-12):** `user/hooks/build-queue-enforce.sh` — replaced the single
unanchored `_WRAPPER_RE = re.compile(r"build-queue\.ps1", re.IGNORECASE)` with the anchored pair.
Verified RED-for-the-right-reason: ran the two new echo/grep-mention DENY tests against the
pre-edit hook first (both failed — the mention wrongly allowed everything after it), then applied
the anchoring and re-ran — both green, plus every pre-existing wrapper-allow test stayed green.
Full suite: `python -m pytest user/scripts/test_hooks.py -q` → 217 passed. **Files modified:**
`user/hooks/build-queue-enforce.sh`, `user/scripts/test_hooks.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q -k "bqe"` passes,
including all new cases above plus every pre-existing `test_bqe_*` case (no regression;
118+/119+ baseline preserved, now higher with the new additions).

**Runtime Verification** *(checked by the pipe tests)*:
- [x] <!-- verification-only --> `echo build-queue.ps1; dotnet build MySln.sln` and `grep foo
  build-queue.ps1 && dotnet build MySln.sln` → DENY on the real-build segment; the sanctioned
  wrapper invocation (direct or `-File`) → ALLOW. **Verified 2026-07-12** via
  `test_bqe_denies_echo_mention_then_real_build`, `test_bqe_denies_grep_mention_then_real_build`,
  `test_bqe_allows_direct_wrapper_invocation_segment_leading`,
  `test_bqe_allows_build_queue_wrapper_with_filtered_exec`,
  `test_bqe_manifest_allows_wrapper_invocation` (all GREEN).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo.

**Prerequisites:** None. Independent of Phase 1.

**Files likely modified:**
- `user/hooks/build-queue-enforce.sh` — `_WRAPPER_RE` replaced by the anchored pair.
- `user/scripts/test_hooks.py` — 3 new tests + 2 pre-existing tests re-confirmed.

**Testing Strategy:** TDD — new positive (DENY) tests written and run RED against the pre-fix
unanchored regex first, then the anchoring landed and all turned GREEN; existing wrapper-allow
tests re-run to confirm no regression.

**Integration Notes for Next Phase:** Orthogonal to Phase 1 (different hook, different matcher) —
no shared state. Phase 3 (below) covers the SPEC's Fix Scope item 3 (D2) and item 5
(anchor-pair coordination), which are cross-cutting across all three anchored hooks.

TDD: yes.

---

### Phase 3: `bash -c` / `sh -c` string-wrap scope (D2) + anchor-pair coordination note (item 5)

**Scope:** The SPEC's Fix Scope item 3 requires a DECISION (subscan vs documented-limitation),
not silent drift; item 5 requires that if the anchor semantics of `_ENV_PREFIX`/`_CMD_START`
change, the change must land in all three hooks that carry a copy of the pair
(`lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`).

**Status:** Provisional — NOT gate-complete (see `../NEEDS_INPUT_PROVISIONAL.md`)

**Deliverables:**
- [x] Decision made and recorded: **documented-limitation** (option B), NOT a nested-command
  subscan (option A) — see `NEEDS_INPUT_PROVISIONAL.md` for the full rationale. Since this choice
  does NOT change `_ENV_PREFIX`/`_CMD_START`'s anchor SEMANTICS (no new unwrap logic is added),
  item 5's "must land in all three hooks" trigger does not fire — `lazy-cycle-containment.sh` is
  untouched by this bug.
- [x] The residual documented in three places: the `_LONG_BUILD_RE` docstring in
  `long-build-ownership-guard.sh`, the `_WRAPPER_RE`-replacement comment in
  `build-queue-enforce.sh`, and a new "Known limitation — `bash -c` / `sh -c` string-wraps"
  section in `user/hooks/CLAUDE.md`.
- [x] Regression tests pinning the CURRENT (unfixed) ALLOW behavior as a deliberate, documented
  residual (not a silent gap): `test_longbuild_guard_bash_dash_c_wrap_accepted_residual`,
  `test_bqe_bash_dash_c_wrapper_reference_accepted_residual` — both GREEN (asserting ALLOW).
- [ ] <!-- verification-only --> **Operator ratification of the D2 choice** — this is the ONE
  item this phase cannot self-certify. See `NEEDS_INPUT_PROVISIONAL.md`.

**Implementation Notes (2026-07-12):** This session judged D2 a genuine fork with no SPEC-stated
recommendation (unlike D1, which the SPEC does resolve). Per the park-provisional protocol, the
documented-limitation choice was adopted and implemented (the three-location documentation +
the two pinning tests), but the bug's overall completion is gated on operator review — see
`NEEDS_INPUT_PROVISIONAL.md` for the full decision context, options considered, and rationale.
**Files modified:** `user/hooks/CLAUDE.md` (new "Known limitation" section),
`user/hooks/long-build-ownership-guard.sh` (docstring only, no logic change beyond Phase 1),
`user/hooks/build-queue-enforce.sh` (comment only, no logic change beyond Phase 2),
`user/scripts/test_hooks.py` (2 new residual-pinning tests),
`../NEEDS_INPUT_PROVISIONAL.md` (new).

**Minimum Verifiable Behavior:** The two residual-pinning tests pass (asserting the documented
ALLOW behavior); `user/hooks/CLAUDE.md` contains the new "Known limitation" section.

**Runtime Verification** *(checked by the pipe tests)*:
- [x] <!-- verification-only --> `bash -c "cargo build --release"` (long-build guard) and
  `bash -c "dotnet build MySln.sln"` (build-queue-enforce) both → ALLOW (the documented, pinned
  residual). **Verified 2026-07-12** via `test_longbuild_guard_bash_dash_c_wrap_accepted_residual`
  and `test_bqe_bash_dash_c_wrapper_reference_accepted_residual` (both GREEN).
- [ ] <!-- verification-only --> Operator ratifies (or redirects) the D2 choice — NOT
  self-certifiable this session; see `NEEDS_INPUT_PROVISIONAL.md`.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo.

**Prerequisites:** Phases 1 and 2 (the anchor-pair discussion references both hooks' finished
anchoring).

**Files likely modified:**
- `user/hooks/CLAUDE.md` — new "Known limitation" section.
- `../NEEDS_INPUT_PROVISIONAL.md` — new.
- `user/scripts/test_hooks.py` — 2 new residual-pinning tests.

**Testing Strategy:** Pin the CURRENT behavior explicitly with a regression test per hook, so a
future fix (turning these tests RED, then fixing them to DENY) is a conscious decision.

**Integration Notes for Next Phase:** None — terminal phase for this bug's Fix Scope. **This
bug's `SPEC.md` Status stays `Concluded`, not `Fixed`, and no `FIXED.md` is written, until the
operator ratifies or redirects the D2 choice recorded in `NEEDS_INPUT_PROVISIONAL.md`.**

TDD: yes (the residual-pinning tests characterize existing behavior rather than driving a code
change, but were written and run deliberately as part of this phase's evidence).

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
