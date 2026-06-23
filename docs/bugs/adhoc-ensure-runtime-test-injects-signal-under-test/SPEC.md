# ensure_runtime production-binding tests fake the OS signal they verify — Investigation Spec

> The `ensure_runtime` cold-boot/runtime-recovery "production-binding" tests in
> `test_lazy_core.py` reach green by injecting a hand-set stand-in for the very
> OS-level signal whose production derivation is under test — so a defect in that
> derivation ships behind a green test (a recurring false-green; three rounds).

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-23
**Placement:** docs/bugs/adhoc-ensure-runtime-test-injects-signal-under-test
**Related:**
- `docs/specs/turn-routing-enforcement/hardening-log/2026-06.md` — Round 32 (`a9ab567`, first occurrence), Round 33 (wrapper-exits-early refix, the spin-off origin), Round 34 (platform-blind `npm.cmd` spawn — the THIRD occurrence; explicitly recommends broadening this bug's scope to the spawn-invocation path)
- `docs/bugs/adhoc-ensure-runtime-test-injects-signal-under-test/ADHOC_BRIEF.md` — the spin-off brief
- `user/scripts/lazy_core.py` `ensure_runtime` / `_recover_runtime` / `_await_compile_serving` / `_classify_compile_state` — the production seam
- `user/scripts/CLAUDE.md` → "CLI surface" `--ensure-runtime` (the multi-round patient-wait / boot-liveness contract)

---

## Verified Symptoms

<!-- "VERIFIED" here = corroborated by on-disk hardening-log evidence + the test source,
     not by an interactive AskUserQuestion round (this is a --batch investigation of a
     harness-internal class whose ground truth is the committed log + code, not a human's
     live observation). -->

1. **[VERIFIED]** A test that *claims* to exercise the production derivation of an OS-level
   boot/runtime signal reaches green by INJECTING a hand-set fake of that exact signal —
   confirmed in the test source and the hardening log. Round 32's
   `test_ensure_runtime_production_boot_alive_live_handle_patient_waits` fed a `_FakeBootPopen`
   whose `.poll()` STAYS `None`; the assertion ("exactly ONE spawn / READY") was reached via the
   recovery loop, never exercising the Windows reality the production `boot_alive` must survive.
   Passed 782/782 while production still starved the cold boot.
2. **[VERIFIED]** The class has recurred at least **three times**, each caught only by a
   live-runtime failure AFTER a unit-green fix shipped:
   - Round 32 (`a9ab567`): `.poll()`-stays-`None` fake → live cold-boot starvation (5 kill-restarts in ~60s → false `mcp-runtime-unready` BLOCKED on `d2-sample-import-ui`).
   - Round 33: refix had to ADD a production-faithful wrapper-exits-early reproduction (`test_ensure_runtime_production_wrapper_exits_early_patient_waits_one_spawn` + its M4 sibling) — i.e. reproduce the OS *condition* rather than fake the *signal*.
   - Round 34 (`81f6060`): the production `restart()` spawn was PLATFORM-BLIND (`npm` = `npm.cmd`, unresolvable from a bare-token argv without a shell). Every test injected `restart` OR monkeypatched `lazy_core.subprocess` with a fake (`_FakeSubprocess.Popen(*a, **kw)`) that ALWAYS succeeds regardless of argv/shell — so the one thing that fails in production (the real spawn invocation) was never exercised. Round 34's log explicitly names this a NEW sub-case of THIS bug's class and recommends broadening scope to cover the spawn-invocation path.
3. **[VERIFIED]** No mechanical guard exists today that flags this pattern. The test-list block
   (`_TESTS`) is a flat name→callable registry; there is no convention or check that a test named
   / documented as "production-binding" must reach the signal through the real default closure.
   The repo's only test-discipline tooling (`lint-skills.py`) lints *skill files*, not
   `test_lazy_core.py`.

## Reproduction Steps

The bug is a **test-discipline defect**, so the repro is "a production-derivation defect ships
behind a green test", reproduced historically three times. Canonical (Round 32) form:

1. Production `boot_alive` is derived from `_boot_handle["proc"].poll()` (a real `Popen` handle whose `.poll()` semantics differ on Windows: the `npm`/`cmd` wrapper exits early while the detached `tauri dev` child compiles for ~3.5 min).
2. The "production-binding" test feeds a `_FakeBootPopen(exit_code=None)` whose `.poll()` is hand-set to STAY `None` (i.e. it injects the *answer* the derivation is supposed to compute).
3. The test asserts READY + one spawn and goes green.
4. **Observed (live):** production derives `boot_alive=False` (wrapper exited), classifies `dead`, and kill-restarts ≤5× in ~60s → false BLOCKED.

**Expected:** a "production-binding" test must drive a production-FAITHFUL OS condition (swap the
real default `restart`/clock/stamp/spawn seam and let the production closure DERIVE the signal),
so a defect in the derivation turns the test red.
**Actual:** the test injects a stand-in for the derived signal, so the derivation is never under
test and a defect ships green.
**Consistency:** structural — recurs whenever a future `ensure_runtime` derivation defect is
"covered" by a signal-injecting test (3 occurrences in 3 rounds).

## Evidence Collected

### Source Code

- `user/scripts/lazy_core.py:6998-7156` — the production derivation under test:
  - `_boot_handle` closure-shared holder; the default `restart()` (`:6999-7067`) spawns the boot `Popen`, stashes the handle, and calls `write_boot_stamp`. On Windows it now spawns via `shell=True` (Round 34 fix) so `npm.cmd` resolves.
  - the default `boot_alive()` (`:7143-7154`) reads `_boot_handle["proc"].poll()` then falls through to the persistent time-window grace `boot_recently_spawned(repo_root)`.
  - **These three production closures (`restart` spawn invocation, `boot_alive` derivation, the boot-stamp/grace clock) are the signals the cited tests must DERIVE, not inject.** The holder is private to `ensure_runtime` by design — the ONLY production-faithful way to reach it is by swapping `lazy_core.subprocess` / `lazy_core.time` and letting the default closures run.
- `user/scripts/test_lazy_core.py`:
  - `_FakeBootPopen` (`:20362`) — the smell vector: `.poll()` returns a hand-set `exit_code` (the injected signal).
  - `_FakeSubprocess` (`:20375`) — `.Popen(*a, **kw)` ALWAYS succeeds (masks the spawn-invocation defect — Round 34's sub-case).
  - `_WindowsSpawnSemanticsSubprocess` (`:20699`) — the GOOD pattern Round 34 added: a double that reproduces the OS *condition* (raises `FileNotFoundError` for a bare-token no-shell argv, succeeds only for `shell=True` + string) instead of faking the *answer*. **This is the seed/exemplar for the durable fix.**
  - The cited production-binding tests (`:20406`, `:20454`, `:20548`, `:20600`, `:20738`) — the ones the guard must classify and validate.

### Git History

- `a9ab567` (Round 32) — wired production `boot_alive` to the spawned `Popen` handle; added the two original signal-injecting "production-binding" tests.
- Round 33 commit — added wrapper-exits-early reproductions; updated the Round-32 dead-handle test whose expectation was premised on the removed wrapper-handle-only signal.
- `81f6060` (Round 34) — platform-blind `npm.cmd` spawn fix + `_WindowsSpawnSemanticsSubprocess`.
- `37f5ed2` — Round 35 hardening log + this spin-off enqueue.

### Related Documentation

- `docs/specs/turn-routing-enforcement/hardening-log/2026-06.md` Rounds 32-35 — the authoritative narrative of all three occurrences and the over-fit spin-off rationale (class-recurred-≥2). Round 34's "Orchestrator action recommended" block explicitly asks to (a) re-home this bug into a pipeline that will action it and (b) BROADEN scope to the production *spawn invocation* path, not only the liveness-signal sub-case.
- `user/scripts/CLAUDE.md` `--ensure-runtime` CLI surface — the full multi-round patient-wait / boot-liveness / cold-compile / sidecar contract the tests cover.

## Theories

### Theory 1: A naming/structure convention + a mechanical guard can force production-binding tests through the real default closures
- **Hypothesis:** Tests that bind a production OS-signal derivation should be marked by an explicit convention (a name prefix and/or a decorator/registry tag, e.g. `test_ensure_runtime_production_*` or a `@production_binding` marker), and a guard asserts that any so-marked test does NOT pass `boot_alive=` / `restart=` / `boot_stamp` injections to `ensure_runtime` (it must instead swap `lazy_core.subprocess` / `lazy_core.time` and let the production closure derive the signal). A so-marked test that injects the signal-under-test fails the guard.
- **Supporting evidence:** `_WindowsSpawnSemanticsSubprocess` already demonstrates the correct pattern (reproduce the OS condition, derive the signal); the cited bad tests are mechanically distinguishable (they pass `_FakeBootPopen` with a hand-set `.poll()` to a test whose docstring claims "PRODUCTION binding"). The `_TESTS` registry is already the single enumeration point.
- **Contradicting evidence:** A purely-static lint cannot perfectly distinguish a *legitimate* injection of an external collaborator (`probe` / `stale_check` / `sidecar_check`) from an *illegitimate* injection of the derived signal — the class boundary (ADHOC_BRIEF "Class boundary IN/OUT") must be encoded carefully so the guard does not false-positive on the hermetic `--test` contract.
- **Status:** Likely — this is the fix direction the brief and the Round-34 recommendation both point at.

### Theory 2: A live cold-boot smoke gate is the complement that catches the spawn-invocation sub-case
- **Hypothesis:** Static structure alone cannot catch Round 34's defect (a fake that succeeds for any argv masks the real `CreateProcess` resolution). The complement is a guard that any production-binding `restart`-spawn test drives a double with *real spawn-resolution semantics* (the `_WindowsSpawnSemanticsSubprocess` shape — raise for bare-token no-shell, succeed only for the production shell form), plus optionally a documented live cold-boot smoke step in the runtime-ensure contract.
- **Supporting evidence:** Round 34's live verification (`lazy-state.py --ensure-runtime` against AlgoBooth) was the ONLY thing that proved the fix; the unit suite was green throughout.
- **Contradicting evidence:** A live smoke gate is environment-dependent (needs a real AlgoBooth checkout + a cold runtime) and cannot run in claude-config's hermetic `--test`; it belongs as a documented manual/operator step, not an automated CI assertion in this repo.
- **Status:** Likely (as the structural-double half); the live-smoke half is a documented manual step, not in-repo automation.

## Proven Findings

1. **Root cause (PROVEN, class-level):** The cited `ensure_runtime` "production-binding" tests
   inject a hand-set fake of the OS-level signal whose production derivation is the subject of the
   assertion (`_FakeBootPopen.poll()` for the `boot_alive` liveness signal; `_FakeSubprocess.Popen`
   always-succeeds for the `restart` spawn invocation). Because the injected value IS the answer the
   derivation is supposed to compute, a defect in the derivation cannot turn the test red — three
   defects shipped behind green tests across Rounds 32/33/34, each caught only live.
2. **The correct pattern already exists in-repo** (`_WindowsSpawnSemanticsSubprocess`): reproduce
   the OS *condition* at the module-level seam (`lazy_core.subprocess`/`lazy_core.time`) and let the
   production closure DERIVE the signal. The durable fix generalizes this into a guard/convention.
3. **Scope is bounded** (ADHOC_BRIEF + Round-34 recommendation): IN = the `ensure_runtime` /
   `_recover_runtime` / `_await_compile_serving` / `boot_alive` production-binding tests that inject
   a stand-in for an OS-level liveness/timing/spawn signal. OUT = legitimate injection of genuinely
   external collaborators (`probe` / `stale_check` / `sidecar_check`), the hermetic `--test`
   contract itself, and a speculative repo-wide false-green linter.

## Fix Scope (for /plan-bug)

⚖ policy: guard shape (lint vs convention vs marker) → take the most complete in-cycle path

A scope-class decision (the options differ in completeness/sizing, not in user-visible product
behavior), so resolved in-cycle per D7. The recommended fix, smallest-that-subsumes the three
cited instances + near neighbors:

1. **A structural production-binding test-discipline guard** (a new check, runnable in CI alongside
   `lint-skills.py` — e.g. `user/scripts/lint-production-binding-tests.py`, or folded into the
   `--test` harness as a meta-test that introspects `_TESTS`):
   - Establish an explicit **convention** for a production-binding test: a stable name prefix
     (`test_ensure_runtime_production_*` is already in use) AND/OR an in-source registry tag, so the
     set is mechanically enumerable from `_TESTS` / source.
   - For each such test, assert it does NOT pass the SIGNAL-UNDER-TEST as an `ensure_runtime` keyword
     injection — specifically NOT `boot_alive=` and NOT `restart=` (those are the production
     derivations). It MUST instead reach the signal by swapping the module seams
     (`lazy_core.subprocess` / `lazy_core.time`) and exercising the real default closure. (A static
     AST/source check on the test function body is sufficient and hermetic.)
   - Allow-list the legitimate external-collaborator injections (`probe=`, `stale_check=`,
     `sidecar_check=`, `frontend_probe=`, `read_lock=`, `live_session_id=`, `kernel_start_time_fn=`,
     `sleep=`, `write_lock=`, `recover_identity=`) so the guard never false-positives on them or on
     the hermetic `--test` contract.
2. **A faithful-double assertion for the spawn-invocation sub-case** (Round 34): a production-binding
   `restart`-spawn test must drive a double with real spawn-resolution semantics (the
   `_WindowsSpawnSemanticsSubprocess` shape — raise for a bare-token no-shell argv, succeed only for
   the production `shell=True` string form), not a `_FakeSubprocess` that succeeds for any argv. The
   guard flags a production-binding spawn test that uses an always-succeeds subprocess double.
3. **A documented live cold-boot smoke step** in the `--ensure-runtime` contract (manual/operator,
   NOT in-repo CI) — the only thing that has ever caught the spawn-invocation defect — referenced
   from `user/scripts/CLAUDE.md`.

Out of scope (do NOT widen): a speculative repo-wide false-green linter; any change to the
production `ensure_runtime` derivation itself (it is correct as of Round 34); the cross-repo
re-home of this bug doc (an orchestrator action noted in Round 34/35, tracked separately).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Test-discipline guard (NEW) | `user/scripts/lint-production-binding-tests.py` (or a `--test` meta-test in `test_lazy_core.py`) | Mechanically flags a production-binding `ensure_runtime` test that injects the signal-under-test (`boot_alive=`/`restart=`) or uses an always-succeeds subprocess double |
| Production-binding tests | `user/scripts/test_lazy_core.py` (`_FakeBootPopen`, `_FakeSubprocess`, the `test_ensure_runtime_production_*` set, `_WindowsSpawnSemanticsSubprocess`) | Establish the convention; the guard validates them; any that inject the signal-under-test are corrected to derive it through the real closure |
| Runtime-ensure contract docs | `user/scripts/CLAUDE.md` (`--ensure-runtime` section) | Document the production-binding test convention + the manual live cold-boot smoke step |
| (Reference only — NOT modified) | `user/scripts/lazy_core.py` `ensure_runtime` derivation | The derivation is correct as of Round 34; the fix is test-discipline, not production logic |

## Open Questions

- **Guard home — standalone lint script vs `--test` meta-test.** A `--test` meta-test introspects
  `_TESTS` and the test source in-process (hermetic, runs with the existing suite); a standalone
  `lint-*.py` mirrors `lint-skills.py` and can run in a broader CI sweep. Resolvable at `/plan-bug`
  time as a mechanical/internal choice (no product-behavior divergence). Recommendation: a `--test`
  meta-test, to keep the guard co-located with the suite it polices and green-gated by the existing
  `lazy-state.py --test` / `test_lazy_core.py` runs.
- **Convention encoding — name-prefix vs explicit tag.** The `test_ensure_runtime_production_*`
  prefix is already in use and enumerable; an explicit tag is more robust but adds a registry field.
  Mechanical/internal; resolve at planning.
- (Out of band, orchestrator-owned) Re-homing this bug into a pipeline that will action it (Round
  34/35 noted claude-config's own bug queue is what the lazy-bug pipeline here works — which is
  correct for THIS cycle; the AlgoBooth-side re-home is a separate orchestrator concern).
