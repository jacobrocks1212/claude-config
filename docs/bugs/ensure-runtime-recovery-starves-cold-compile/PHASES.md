# Implementation Phases — `--ensure-runtime` recovery loop starves a cold `tauri dev` compile

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure harness-script change to `user/scripts/lazy_core.py` (and its CLI seam in `lazy-state.py`), validated entirely by the in-file `--test` smoke harness + `test_lazy_core.py` via injected probe/restart/stale_check/sleep callables. There is no AlgoBooth app surface, store, audio path, UI, or event reachable from MCP here (the dev runtime is the *subject under test*, not an MCP-testable target). Per `docs/bugs/CLAUDE.md`, harness-script defects have no MCP-reachable surface — the hermetic state-machine smoke tests ARE the runtime validation.

## Cross-feature Integration Notes

The bug SPEC's `**Related:**` line is not a machine-parseable `**Depends on:**` block (bug pipeline), so no upstream PHASES.md look-back fires. The fix nonetheless integrates against two **already-shipped, Complete** harness features whose contracts are load-bearing here:

- **`long-build-and-runtime-ownership` (Complete 2026-06-20) — the LD3 bounded-recovery contract + the ownership/transient-build machinery.** This fix REWORKS the LD3 contract: the ≤5×backoff `_recover_runtime` loop is re-scoped to recover an *already-healthy runtime that later crashed*, and the cold-boot / new-crate-STALE long compile is routed instead through the **orchestrator-owned long-build path** (`run_transient_build` at `lazy_core.py:7103`, the existing M3.2 Transient Build contract). Phase 2/3 below must preserve the existing recovery loop's invariants for the genuine crash-recovery case (the `test_ensure_runtime_m4_*_recovers_*` / `*_exhausts_to_blocked` / `*_hijacked_*` fixtures must stay green), changing ONLY which classifications enter the bounded loop vs. the patient owned-wait.
- **`env-transient-counts-against-validation-retry-budget` (sidecar-pipe readiness, Leg A).** The `sidecar_check` callable already threads through `_recover_runtime` / `_ensure_runtime_m4`. The new two-port "actually-serving" readiness assertion (`:3333` `/health` 200) MUST compose with the existing sidecar assertion — a recovered/booted runtime is READY only when health=200 AND (when asserted) the sidecar pipe is connected. Phase 1/2 add the `:1420` probe alongside, never replacing, the existing `:3333`+sidecar gate.

## Validated Assumptions

The SPEC's root cause is CONFIRMED from source + two independent session logs; the fix surface is code-read-provable (the recovery loop, classifier, and config dict are all read verbatim into the Affected Area). The ONE runtime-coupled assumption — that `tauri dev` brings Vite up on `:1420` fast while `:3333` `/health` only serves after the Rust compile finishes (the two-port discriminator) — is the live signal the fix INTRODUCES, and the SPEC itself flags it as never-yet-instrumented (Theory mining: `:1420` is "essentially never probed today"). Therefore Phase 1 carries an explicit **`- [ ]` runtime-spike row**: the two-port split must be confirmed against a real cold `tauri dev` boot on a workstation before the patient-wait logic is trusted in production. It is hermetically testable in the harness via injected two-port probes (no real runtime), but the live signal's truth is a workstation-deferred runtime observation, NOT a code read.

---

### Phase 1: Two-port probe + compiling-vs-dead discriminator (config + pure helper)

**Scope:** Add the net-new `:1420` (Vite) probe to the ensure-runtime config and a pure classifier helper that maps the two-port observation to one of {serving, compiling, dead}. This is the cheapest cross-platform "backend still compiling, not dead" signal (SPEC Proven Findings → "The missing signal"). No control-flow rewiring yet — this phase delivers the signal and its hermetic tests in isolation so Phase 2 can consume it.

**Deliverables:**
- [x] Add `frontend_health_url` (default `"http://localhost:1420"`) and `frontend_port` (default `1420`) keys to `_ENSURE_RUNTIME_DEFAULT_CONFIG` (`lazy_core.py:6323`), documented as the Vite-up/compiling signal and parameterized (repo-agnostic) exactly like the existing `:3333` keys. A legacy config override lacking the keys must read via `.get()` and never raise (mirror the `assert_sidecar_connected` back-compat pattern).
- [x] Add `_default_frontend_probe(frontend_health_url)` — a best-effort stdlib `urllib` reachability probe returning a bool (Vite reachable), modeled on `_default_runtime_probe` / `_default_sidecar_probe`; never raises (any error → False).
- [x] Add a pure classifier `_classify_compile_state(backend_code, frontend_up) -> "serving" | "compiling" | "dead"`: `backend_code == 200` ⇒ `serving`; `backend_code != 200 and frontend_up` ⇒ `compiling` (Vite up, backend not yet serving — be patient, do NOT kill); `backend_code != 200 and not frontend_up` ⇒ `dead`. Pure function, no I/O.
- [x] Thread an optional injected `frontend_probe` callable through `ensure_runtime(...)` (default-bound to `_default_frontend_probe` when the config carries the frontend keys, else `lambda: False` so the discriminator degrades to today's `:3333`-only DEAD behavior — repo-agnostic, byte-identical for a non-`:1420` repo).
- [x] Tests: `test_lazy_core.py` — `_classify_compile_state` truth table (all three branches); `_default_frontend_probe` returns False on a connection error; the new config keys default correctly and a legacy config dict without them does not crash `ensure_runtime`.

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` (or the targeted new tests) passes with the classifier returning `compiling` for `(0, True)`, `serving` for `(200, anything)`, and `dead` for `(0, False)`; `python3 user/scripts/lazy-state.py --test` stays green (no behavior change for the default `:3333`-only path).

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> runtime spike (two-port discriminator — workstation-eligible): on a real cold `tauri dev` boot from a clean `target/`, observe that `:1420` becomes reachable within seconds while `:3333` `/health` refuses until the Rust compile completes, confirming the `compiling` classification fires for the real cold-boot window (NOT a static code trace — observe the running ports). Record the observed timings as evidence.

**MCP Integration Test Assertions:** N/A — no MCP-runtime-observable behavior; this is a pure-helper + config phase whose contract is the hermetic `--test` harness (the dev runtime is the subject under test, not an MCP target).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add config keys to `_ENSURE_RUNTIME_DEFAULT_CONFIG` (verified at `:6323`); add `_default_frontend_probe` + `_classify_compile_state` (net-new functions, sited next to `_default_sidecar_probe` at `:6365`); thread `frontend_probe` into `ensure_runtime` (verified at `:6546`) — REUSE the existing `sidecar_check` default-binding pattern (`:6655-6669`), do NOT invent a new injection scheme.
- `user/scripts/test_lazy_core.py` — new hermetic tests next to the existing `test_ensure_runtime_sidecar_*` block (verified at `:19046`).

**Testing Strategy:** Pure-function + injected-probe unit tests, hermetic (no real runtime/network). The `_classify_compile_state` truth table is exhaustively covered; the config-default and back-compat assertions mirror `test_ensure_runtime_legacy_config_without_sidecar_key_does_not_crash` (`:19105`).

**Integration Notes for Next Phase:**
- `_classify_compile_state` is the discriminator Phase 2 consumes to decide patient-wait vs. bounded-recovery vs. dead.
- The `frontend_probe` injection seam exactly mirrors `sidecar_check`; Phase 2 binds the same way for its patient-wait re-probe.
- Default-off semantics are load-bearing: a repo without `:1420` (no frontend keys / `frontend_probe → False`) must see byte-identical behavior to today, so Phase 2's new branch must be reachable ONLY when the frontend signal is present.

#### Implementation Notes (Phase 1 — 2026-06-21)
- **Work completed:** Added `frontend_health_url`/`frontend_port` keys to `_ENSURE_RUNTIME_DEFAULT_CONFIG`; added `_default_frontend_probe` (urllib best-effort, HTTPError ⇒ up since Vite answered, never raises) and the pure `_classify_compile_state` next to `_default_sidecar_probe`; threaded an injected `frontend_probe` through `ensure_runtime` (default-bound from `cfg.get("frontend_health_url")` else `lambda: False`) and plumbed it into `_ensure_runtime_m4`'s signature (NOT yet consumed — Phase 2 wires the branch).
- **Integration notes:** The `frontend_probe` seam mirrors `sidecar_check` exactly. `_ensure_runtime_m4` accepts but does not yet read `frontend_probe` — the test `test_ensure_runtime_threads_injected_frontend_probe_to_m4` asserts the seam is wired without crashing; observable consumption is asserted on Phase 2's compiling fixtures.
- **TDD:** 6 hermetic tests written first (4 RED for the right reason — missing symbols/keys/param; 2 default-off tests green by construction), then implementation made all 6 pass.
- **Gates:** `test_lazy_core.py` 742/742; `lazy-state.py --test` + `bug-state.py --test` green (baselines unchanged — no default-path fixture changed); `lazy_parity_audit.py --repo-root .` exit 0.
- **Review verdict:** PASS (inline review; pure-helper + config + plumbing, default-off byte-identical preserved).
- **Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

---

### Phase 2: Patient compiling-aware wait — route cold/first-boot DEAD + new-crate STALE off the crash-recovery loop

**Scope:** Rework `_ensure_runtime_m4` / `_recover_runtime` so a runtime classified `compiling` (Vite up, backend not yet serving) is **waited on** with a cold-compile-sized, owned patience budget that ends on "actually serving" (`:3333` `/health` 200 — AND, when asserted, sidecar connected), rather than being kill-restarted by the ≤5×backoff loop. Reserve the bounded crash-recovery loop strictly for a genuinely `dead` runtime (Vite also down → never booted or truly crashed). This is the LD3 re-scoping from the Locked Decision's half (B) ownership-routing + half (A) two-port readiness, satisfied inside the existing M4 evaluation without a real SIGKILL of anything.

**Deliverables:**
- [x] In `_ensure_runtime_m4` (`lazy_core.py:6783`), at each point that today routes a non-serving runtime into `_recover_runtime` with `from_state="DEAD"` (the no-lock-down case `:6819`, the dead-PID case `:6842`, the owned-health-refused case `:6888`) AND for the STALE case (`:6858`), consult `_classify_compile_state(code, frontend_probe())`: when the classification is `compiling`, enter the **patient wait** (new path below) instead of the kill-restart loop. A `dead` classification keeps today's `_recover_runtime` crash-recovery behavior unchanged.
- [x] Add `_await_compile_serving(cfg, *, probe, frontend_probe, sleep, sidecar_check, ...)` — a patient, NON-killing wait: poll `probe()` (and `frontend_probe()`) on a cold-compile-sized cadence/ceiling (sized like the existing production `restart()` awaiter's `90 × 5s` ≈ 7.5-min ceiling at `:6643`, NOT the 31s crash budget); it NEVER calls `restart()`/`kill` while the runtime is `compiling`. Ends READY on `:3333` 200 (+ sidecar connected when asserted); if the frontend goes down mid-wait (`compiling → dead`), fall through to bounded `_recover_runtime`; on ceiling-exhaustion-while-still-compiling, BLOCKED with a DISTINCT terminal_blocker (see next deliverable).
- [x] Add a distinct `_cold_compile_timeout_blocker()` message (Open Question 5, decided below) so a patient-wait that exhausts its cold-compile ceiling surfaces as a recognizably-distinct cold-compile-timeout blocker, NOT the generic recovery-exhausted `_blocked_blocker`. Both still map to `blocker_kind: mcp-runtime-unready` at the orchestrator (no new blocker_kind), but the verdict text tells starvation-vs-real-hang apart for the operator.
- [x] Preserve every existing invariant: HIJACKED still never restarts/kills (`:6847`); the bounded loop still caps at 5 with exponential backoff for the genuine `dead` case; `recover_identity`/`write_lock` lock-rewrite on recovery is unchanged; the sidecar assertion still composes (a serving-but-pipe-dead runtime is NOT READY).
- [x] Tests (hermetic, injected two-port probes — extend the existing `_M4_CONFIG`/`_owned_lock`/`_SESSION` fixtures):
  - `compiling` (`:3333` down, `:1420` up) → patient wait, restart NEVER called, READY once `:3333` answers 200 within the patience ceiling.
  - `compiling` that crosses to `dead` (`:1420` goes down mid-wait) → falls through to bounded `_recover_runtime`.
  - `compiling` that never serves within the ceiling → BLOCKED with the DISTINCT cold-compile-timeout blocker text; restart STILL never called during the compiling wait.
  - genuine `dead` (both ports down) → UNCHANGED bounded `_recover_runtime` (the existing `_recovers_within_five` / `_exhausts_to_blocked` behavior is preserved, asserted by keeping those fixtures green).
  - default-off (no frontend signal) → byte-identical to today's DEAD→recovery path.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/test_lazy_core.py` pass with a new fixture proving a `compiling`-classified runtime reaches READY with `restart` call-count == 0 (the starvation root cause is structurally gone: a cold compile is waited on, never kill-restarted), and the genuine-crash fixtures still cap restart at 5.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> runtime spike (cold-boot no-longer-starved — workstation-eligible): on a real cold `tauri dev` boot from a clean `target/`, run `python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <algobooth>` with a live run marker and confirm it returns `state: READY` after patiently waiting out the cold Rust compile (NOT `BLOCKED` after 5 starved kill-restarts) — the exact symptom from sessions `ea0c2bf8` / `3b08f4e8`, now resolved. Record the verdict JSON + the observed wait duration as evidence.

**MCP Integration Test Assertions:** N/A — the runtime is the subject under test; the live proof is the `--ensure-runtime` verdict above, not an MCP tool call.

**Prerequisites:**
- Phase 1: `_classify_compile_state`, `_default_frontend_probe`, the `frontend_probe` injection seam, and the config keys must exist (this phase consumes all four).

**Files likely modified:**
- `user/scripts/lazy_core.py` — rewire the `_recover_runtime` entry points in `_ensure_runtime_m4` (verified `:6783-6893`) to branch on `_classify_compile_state`; add `_await_compile_serving` (net-new, sited next to `_recover_runtime` at `:6896`); add `_cold_compile_timeout_blocker` (net-new, next to `_blocked_blocker` at `:6773`). REUSE the existing `restart()` production-awaiter's `90 × 5s` ceiling sizing (`:6643`) as the patience budget; REUSE the existing `sidecar_check` composition — do NOT add a parallel readiness scheme.
- `user/scripts/test_lazy_core.py` — extend the `test_ensure_runtime_m4_*` recovery block (verified `:18864-19045`) with two-port fixtures.

**Testing Strategy:** Hermetic injected-probe fixtures asserting the call-count invariant (`restart == 0` during a compiling wait), the bounded-loop preservation for genuine crashes, the distinct timeout blocker, and the default-off byte-identical path. No real runtime.

**Integration Notes for Next Phase:**
- The verdict shape is UNCHANGED (still `{state, ownership_verified, health_code, mcp_tools_present, terminal_blocker, status}`) — a patient-wait READY is indistinguishable in shape from a recovery READY, so Phase 3's CLI/consumer wiring needs no schema change.
- The distinct cold-compile-timeout blocker is verdict *text* only (still `blocker_kind: mcp-runtime-unready` downstream); Phase 3 documents the text distinction without adding a new blocker_kind.
- `bug-state.py` shares NONE of this (ensure-runtime lives only in `lazy-state.py`'s CLI + `lazy_core`'s shared helpers, but `bug-state.py` has no `--ensure-runtime` handler), so there is NO coupled-pair mirror for the CLI seam — only the `lazy_core` helper change is shared, and it is feature-pipeline-reached via `lazy-state.py` alone (correct divergence; the `--ensure-runtime` CLI is feature-pipeline-only).

#### Implementation Notes (Phase 2 — 2026-06-21)
- **Work completed:** Added `_await_compile_serving` (patient, NEVER-restart wait on a `_COLD_COMPILE_WAIT_MAX_POLLS=90 × _COLD_COMPILE_WAIT_INTERVAL=5s` ≈ 7.5-min ceiling — reusing the production restart-awaiter sizing, NOT the 31s crash budget) and `_cold_compile_timeout_blocker` (distinct text, same `mcp-runtime-unready` blocker_kind). Rewired all four `_recover_runtime` entry points (no-lock-down, dead-PID, owned-health-refused, STALE) + the sidecar-disconnect-at-200 point through a new in-function `_route_non_serving` helper that consults `_classify_compile_state(code, frontend_probe())`: `compiling` → patient wait; `dead`/default-off/`serving`-but-stale → unchanged `_recover_runtime`. A `compiling→dead` mid-wait returns the `_COMPILE_WENT_DEAD` sentinel and falls through to bounded recovery. The patient wait composes the sidecar assertion + rewrites the ownership lock on serving, exactly like `_recover_runtime`.
- **Integration notes:** The starvation root cause is structurally gone — a `compiling` runtime reaches READY with `restart` call-count == 0 (asserted). HIJACKED never-restart/never-kill, the ≤5 cap + exponential backoff for genuine crashes, and the sidecar composition are all preserved (existing fixtures stay green). `_ensure_runtime_m4` defensively binds `frontend_probe=lambda: False` when None (legacy/un-threaded callers) → no-frontend ⇒ never `compiling` ⇒ today's path.
- **Test-fixture note:** Because the base `_ENSURE_RUNTIME_DEFAULT_CONFIG` now always carries the `:1420` key (the AlgoBooth-flavored harness default), the five existing genuine-DEAD fixtures were made deterministic by injecting `frontend_probe=lambda: False` (Vite down → genuinely dead), and the new default-off test opts out via an empty `frontend_health_url` override — exercising the real config-driven default binding rather than an injected probe. These are fixture-determinism updates, not assertion weakening (the genuine-crash recovery assertions are unchanged).
- **TDD:** 7 new hermetic tests written first (4 RED for the right reason — missing blocker fn + compiling currently kill-restarting; 3 green by construction via the existing recovery path), then implementation made all 7 pass + restored the 5 existing fixtures.
- **Gates:** `test_lazy_core.py` 749/749; `lazy-state.py --test` + `bug-state.py --test` green (baselines unchanged); `lazy_parity_audit.py --repo-root .` exit 0.
- **Review verdict:** PASS (inline review; never-kill invariant asserted via restart==0, distinct blocker text asserted, all preserved-path fixtures green, default-off byte-identical).
- **Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

---

### Phase 3: CLI-seam wiring + consumer/doc alignment + parity confirmation

**Scope:** Bind the new `frontend_probe` to the real `_default_frontend_probe` in the `lazy-state.py --ensure-runtime` handler (so production gets the two-port discriminator, with the existing live-marker→`live_session_id` threading unchanged), align the `lazy-batch` Step 1d.0 consumer prose so the operator understands a patient-wait READY and the distinct cold-compile-timeout blocker, and confirm the `lazy_parity_audit.py` parity audit + both `--test` baselines.

**Deliverables:**
- [ ] In the `lazy-state.py --ensure-runtime` handler (verified `:7982-7994`), pass the real frontend probe into `lazy_core.ensure_runtime(...)` (or rely on Phase 1's config-driven default binding so the handler needs no new argument — choose whichever keeps the handler a thin pass-through, documented inline). The existing best-effort `live_session_id` threading from the run marker stays UNCHANGED.
- [ ] Update `user/skills/lazy-batch/SKILL.md` Step 1d.0 (verified `:586-611`) so the `state` routing prose notes: a `state: DEAD`-class cold/first boot or new-crate STALE is now PATIENTLY WAITED (Vite-up/backend-down ⇒ compiling, not killed) and reaches READY without starvation; and a recovery-exhausted BLOCKED may now carry the distinct cold-compile-timeout text (still `blocker_kind: mcp-runtime-unready`). Keep the existing READY/STALE/HIJACKED/BLOCKED table intact — ADD the patient-wait note, do not rewrite the table.
- [ ] Add a REVERSE-REFERENCE entry to this bug in the related shipped feature's record per the spin-off contract: note in `lazy_core.py`'s ensure-runtime docstring (or an inline comment at the reworked `_ensure_runtime_m4` site) that the LD3 bounded-recovery contract was re-scoped by `docs/bugs/ensure-runtime-recovery-starves-cold-compile` (cold compile → patient owned wait; bounded loop → genuine-crash only).
- [ ] Confirm `python3 user/scripts/lazy_parity_audit.py` passes (the `--ensure-runtime` CLI is feature-pipeline-only, so NO new bug-state.py mirror is owed — confirm the audit does not regress, and document the justified divergence).
- [ ] Re-generate / confirm both byte-pinned `--test` baselines (`tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt`) ONLY if `--test` output legitimately changed; otherwise confirm they are untouched.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test`, `python3 user/scripts/bug-state.py --test`, `python3 user/scripts/test_lazy_core.py`, and `python3 user/scripts/lazy_parity_audit.py` all pass; `python3 ~/.claude/scripts/lint-skills.py` passes against the edited `lazy-batch/SKILL.md`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> reachability smoke (workstation-eligible): `python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <algobooth>` returns a well-formed verdict JSON (the production handler binds the real frontend probe without error) — surface is callable end-to-end; the behavioral cold-boot proof is Phase 2's runtime spike.

**MCP Integration Test Assertions:** N/A — CLI/doc wiring; the live proof is the `--ensure-runtime` verdict reachability smoke above.

**Prerequisites:**
- Phase 2: the patient-wait branch + distinct blocker must exist (this phase wires them to production + documents them for the consumer).

**Files likely modified:**
- `user/scripts/lazy-state.py` — `--ensure-runtime` handler (verified `:7982`), thin pass-through binding only.
- `user/skills/lazy-batch/SKILL.md` — Step 1d.0 routing prose (verified `:586-611`), additive note only.
- `user/scripts/lazy_core.py` — reverse-reference comment at the reworked ensure-runtime site.
- `user/scripts/lazy_parity_audit.py` — read-only confirmation (no expected change; the CLI is feature-only).
- `tests/baselines/*.txt` — confirm-only (regenerate only on a legitimate `--test` delta, via the `_normalize_smoke_output` helper, never by hand — per `user/scripts/CLAUDE.md`).

**Testing Strategy:** Full state-machine smoke suite + parity audit + skill lint. The CLI handler change is covered by the existing `test_ensure_runtime_handler_wiring_*` block (verified `:19177-19216`), extended for the frontend-probe binding if the handler signature changes.

**Integration Notes for Next Phase:** Terminal phase. On completion, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to the validation tail; the `__mark_fixed__` gate owns the SPEC/PHASES `Fixed` flip + FIXED.md receipt (gate-owned, never authored here).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to `Fixed` and writes the `FIXED.md` receipt once the validation tail certifies this phase's runtime verification. This PHASES.md never flips those itself.

---

## Open Questions resolved at planning time

- **Open Question 5 (SPEC) — `BLOCKED` semantics when a compile genuinely never finishes.** RESOLVED in-plan (Phase 2): a patient-wait that exhausts its cold-compile ceiling surfaces a **DISTINCT terminal_blocker text** (`_cold_compile_timeout_blocker`) so the operator can tell starvation-aware cold-compile-timeout from a generic recovery-exhaustion hang — but it maps to the SAME existing `blocker_kind: mcp-runtime-unready` downstream (no new blocker_kind, no orchestrator/state-script change, no new sentinel schema). ⚖ policy: distinct timeout text vs new blocker_kind → distinct text only (scope-class: end-state operator-visible behavior is the clearer blocker message either way; adding a new blocker_kind would ripple into the orchestrator routing table, SENTINEL_SCHEMAS, and check-docs-consistency.ts for no product gain — the most complete in-cycle path is the verdict-text distinction without the cross-surface blocker_kind churn).

## Implementation Notes

- **Coupling:** `--ensure-runtime` is a feature-pipeline-only CLI seam (`lazy-state.py` + shared `lazy_core` helpers); `bug-state.py` has no `--ensure-runtime` handler. The shared `lazy_core` changes are reached only via `lazy-state.py`. NO coupled-pair mirror is owed for the CLI seam (justified divergence — confirmed against `lazy_parity_audit.py` in Phase 3). This is the SAME divergence shape the host-capability DEFER path documents in `user/scripts/CLAUDE.md`.
- **Default-off / repo-agnostic:** every new behavior is gated on the presence of the `:1420` frontend signal; a repo without it (no frontend config keys, `frontend_probe → False`) sees byte-identical behavior to today. The `--test` baselines must not change unless a default-path fixture legitimately changes.
- **Reuse over reinvention (from the touchpoint audit):** Phase 1 mirrors the `sidecar_check` injection + back-compat `.get()` pattern (`lazy_core.py:6655-6669`); Phase 2 reuses the existing `restart()` production awaiter's `90 × 5s` ceiling (`:6643`) as the patience budget and the existing sidecar composition. No new readiness/injection scheme is introduced.
