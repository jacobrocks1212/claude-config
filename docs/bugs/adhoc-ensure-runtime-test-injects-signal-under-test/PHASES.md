# Implementation Phases — ensure_runtime production-binding test-discipline guard

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a hermetic Python test-discipline guard over `user/scripts/test_lazy_core.py`. There is no app behavior, store, audio, UI, or event surface — nothing reachable via the MCP HTTP server. The entire deliverable runs under `pytest user/scripts/ -q` + the in-file `--test` harness (no Tauri/MCP/device). (Cross-checked against the mcp-testing untestable classes: this is "build/test tooling", structurally outside MCP reach.)

## Validated Assumptions

All load-bearing assumptions for this plan are **code-provable** (static AST/source introspection of a Python test module), so the Step 2.7 runtime-assumption gate is **skipped with reason**: no assumption depends on running-system behavior crossing a boundary. Confirmed from source during the touchpoint audit:

- The recommended guard home — a `--test` meta-test that introspects the test module via `Path(__file__).read_text()` + a pure AST collector — is a **live, proven pattern in the same file**: `test_no_orphaned_test_functions` (`test_lazy_core.py:22248`) + its negative fixture `test_dead_coverage_guard_detects_orphan_by_name` (`:22269`) + the pure collector `_collect_orphaned_test_names` (`:22214`). The new guard mirrors this shape exactly.
- The cited production-binding tests reach `ensure_runtime` through the real default `restart`/`boot_alive` closures by swapping `lazy_core.subprocess`/`lazy_core.time` and passing **neither** `restart=` nor `boot_alive=` (verified at `:20406`, `:20454`, `:20548`, `:20600`, `:20738`). The smell is mechanically distinguishable: a `boot_alive=`/`restart=` keyword in the `ensure_runtime(...)` call of a `test_ensure_runtime_production_*` function.
- The spawn-invocation sub-case (Round 34) is distinguished by the subprocess double class: `_FakeSubprocess` (`:20375`) `.Popen(*a, **kw)` ALWAYS succeeds (the smell); `_WindowsSpawnSemanticsSubprocess` (`:20699`) reproduces the OS condition (the good pattern).
- `ensure_runtime`'s legitimate external-collaborator injection kwargs are read from its signature in `lazy_core.py` and the cited tests: `probe`, `stale_check`, `sidecar_check`, `frontend_probe`, `read_lock`, `live_session_id`, `kernel_start_time_fn`, `sleep`, `write_lock`, `recover_identity`, `config`. These are allow-listed so the guard never false-positives on the hermetic `--test` contract.
- No `.claude/skill-config/mcp-tool-catalog.md` exists in claude-config → the Step 2.7 **MCP tool-existence audit no-ops** (recorded skip). The **SPEC-example capability audit** also no-ops: the SPEC carries no code examples consuming a production API surface (its examples are test-discipline narrative).

## Touchpoint Audit (verified — read-only, performed inline)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/test_lazy_core.py` | yes | `_TESTS` registry (appended blocks), `_FakeBootPopen` (`:20362`), `_FakeSubprocess` (`:20375`), `_WindowsSpawnSemanticsSubprocess` (`:20699`), the `test_ensure_runtime_production_*` set (`:20406/20454/20548/20600/20738`), `test_no_orphaned_test_functions` (`:22248`) + negative fixture (`:22269`) + `_collect_orphaned_test_names` (`:22214`), `__main__` runner (`:26458`) | modify | REUSE the `test_no_orphaned_test_functions` meta-test pattern: add a pure module-level collector `_collect_production_binding_smells(module_source)` + a positive self-checking meta-test + a negative-fixture test; register all in `_TESTS`. Do NOT create a standalone lint script. |
| `user/scripts/lazy_core.py` | yes | `ensure_runtime(...)` signature (injected `probe`/`restart`/`stale_check`/`boot_alive`/`sidecar_check`/`frontend_probe`/`read_lock`/`live_session_id`/`kernel_start_time_fn`/`sleep`/`write_lock`/`recover_identity`/`config`); default `restart` closure (`:6999`), default `boot_alive` (`:7143`) | reference only (NOT modified) | The derivation is correct as of Round 34. The guard's allow-list is derived from this signature; production logic is untouched. |
| `user/scripts/CLAUDE.md` | yes | `--ensure-runtime` CLI surface section | modify | Append the production-binding test convention + the manual live cold-boot smoke step. |

**Drift correction:** none. No contradictions surfaced; the SPEC's recommended guard home is confirmed by the in-file `test_no_orphaned_test_functions` precedent. The two SPEC Open Questions (lint-vs-meta-test home, name-prefix-vs-tag convention) are mechanical/internal — resolved in-cycle (see ⚖ below).

⚖ policy: guard home (standalone lint vs `--test` meta-test) → `--test` meta-test (most complete in-cycle; co-located with the suite it polices, green-gated by the existing runs, mirrors the live `test_no_orphaned_test_functions` precedent — no new CI wiring needed).

⚖ policy: convention encoding (name-prefix vs explicit tag) → reuse the existing `test_ensure_runtime_production_*` name prefix (already in use + enumerable; no new registry field; smallest-that-subsumes the three cited instances).

## Cross-feature Integration Notes

(No `**Depends on:**` hard deps on Complete upstreams — this is a self-contained test-discipline guard in `user/scripts/`.)

---

### Phase 1: Production-binding smell collector + signal-injection guard

**Scope:** Add a pure, AST-based collector `_collect_production_binding_smells(module_source)` to `test_lazy_core.py` that enumerates every `test_ensure_runtime_production_*` function and flags the **signal-injection smell** — a `boot_alive=` or `restart=` keyword passed to an `ensure_runtime(...)` call inside that function's body. Wire it into a positive self-checking meta-test (PASSES on the current, corrected suite) plus a negative-fixture test (proves the guard catches a synthetic violator). This mirrors the existing `_collect_orphaned_test_names` / `test_no_orphaned_test_functions` / `test_dead_coverage_guard_detects_orphan_by_name` trio exactly.

**Deliverables:**
- [ ] `_collect_production_binding_smells(module_source: str) -> list[dict|str]` — pure collector: `ast.parse` the source, walk every top-level `def test_ensure_runtime_production_*`, and within each scan for a `Call` whose function is named `ensure_runtime` carrying a `keyword` arg `boot_alive` or `restart`. Return a sorted, stable list naming each offending `(test_name, injected_kwarg)`. Allow-list the legitimate external-collaborator kwargs (`probe`, `stale_check`, `sidecar_check`, `frontend_probe`, `read_lock`, `live_session_id`, `kernel_start_time_fn`, `sleep`, `write_lock`, `recover_identity`, `config`) — these are NEVER flagged. AST over regex (ignores docstring/comment occurrences), matching the `_collect_orphaned_test_names` rationale.
- [ ] `test_ensure_runtime_production_tests_derive_not_inject_signal()` — positive self-checking meta-test: reads `Path(__file__).read_text()`, asserts `_collect_production_binding_smells(...) == []` on the live suite (the cited tests already derive the signal through the real closures, so this PASSES today). On a future regression — a new `test_ensure_runtime_production_*` that passes `boot_alive=`/`restart=` — it FAILS naming the offender and the injected kwarg.
- [ ] `test_production_binding_guard_detects_signal_injection()` — negative fixture: feed synthetic module source containing a `test_ensure_runtime_production_injects()` whose body calls `ensure_runtime(..., boot_alive=lambda: True)`, assert the collector reports it by name (proving non-vacuous), and feed a sibling that injects only `probe=`/`stale_check=` and assert it is NOT flagged (allow-list proof).
- [ ] Register all three (collector is a helper, two tests) in `_TESTS` so the manual `--test`/`__main__` runner collects them.
- [ ] Tests: the two meta-tests above ARE the verification; run `pytest user/scripts/test_lazy_core.py -q` and `python user/scripts/test_lazy_core.py` (manual runner) green.

**Minimum Verifiable Behavior:** `pytest user/scripts/test_lazy_core.py -k production_binding -q` runs the new positive + negative meta-tests and both pass (positive: live suite clean; negative: synthetic violator reported, allow-listed injection not reported). `python user/scripts/test_lazy_core.py` exits 0 with the two new tests in the count.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; the guard is a hermetic AST introspection asserted by pytest.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/test_lazy_core.py` — add the collector + two meta-tests; append to `_TESTS`. Reuse the `_collect_orphaned_test_names` trio shape verbatim (do NOT introduce a new file).

**Testing Strategy:** Self-contained. The positive meta-test green-proves the live suite is already clean; the negative fixture green-proves the guard would catch a real signal-injecting regression. Both run under the existing pytest gate AND the manual `_TESTS` runner — no new harness.

**Integration Notes for Next Phase:**
- The collector returns structured `(test_name, injected_kwarg)` records — Phase 2 extends the SAME collector (or adds a sibling) for the spawn-double sub-case rather than duplicating the AST walk.
- The allow-list of legitimate kwargs is the load-bearing class boundary (ADHOC_BRIEF "IN/OUT"); Phase 2 must not flag `_WindowsSpawnSemanticsSubprocess` usage (the GOOD pattern).

---

### Phase 2: Spawn-invocation faithful-double assertion (Round 34 sub-case)

**Scope:** Extend the guard so a production-binding `restart`-spawn test (one that swaps `lazy_core.subprocess` instead of injecting `restart=`) is flagged when it uses an **always-succeeds** subprocess double (`_FakeSubprocess`, whose `.Popen(*a, **kw)` succeeds for any argv) rather than a faithful double with real spawn-resolution semantics (`_WindowsSpawnSemanticsSubprocess`, which raises for a bare-token no-shell argv and succeeds only for the `shell=True` string form). This catches the Round-34 class: a fake that succeeds for any argv masks the real `CreateProcess` resolution defect.

**Deliverables:**
- [ ] Extend `_collect_production_binding_smells` (or add `_collect_spawn_double_smells(module_source)` sharing the AST walk) to detect, within a `test_ensure_runtime_production_*` function that swaps `lazy_core.subprocess` (assignment `lazy_core.subprocess = <fake>`) AND does NOT inject `restart=`, whether the assigned subprocess double is constructed from `_FakeSubprocess` (the always-succeeds smell) vs `_WindowsSpawnSemanticsSubprocess` (the faithful double). Flag the `_FakeSubprocess` case for spawn-binding tests; never flag the faithful double.
- [ ] Encode the discriminator precisely so a NON-spawn-binding production test that legitimately uses `_FakeSubprocess` for the liveness/timing sub-case (e.g. `test_ensure_runtime_production_boot_alive_live_handle_patient_waits`, which exercises `.poll()` liveness, NOT spawn resolution) is NOT a false positive: a spawn-binding test is one whose assertions reference spawn resolution (`shell_spawns`) OR whose intent is the spawn-invocation path. Resolve the boundary conservatively — prefer a name/marker convention (`*_spawn_*` / a registry tag) over over-broad AST inference, recording the chosen discriminator inline. (⚖ scope-class: see policy note below.)
- [ ] `test_spawn_binding_production_tests_use_faithful_double()` — positive meta-test: assert the live suite is clean (`test_ensure_runtime_production_restart_spawns_via_shell_on_windows_cold_boot` already uses `_WindowsSpawnSemanticsSubprocess`, so PASSES today).
- [ ] `test_spawn_double_guard_detects_always_succeeds_double()` — negative fixture: synthetic spawn-binding production test using an always-succeeds `_FakeSubprocess` is reported; one using the faithful double is not.
- [ ] Register the new test(s) in `_TESTS`.
- [ ] Tests: `pytest user/scripts/test_lazy_core.py -q` + manual runner green.

**Minimum Verifiable Behavior:** `pytest user/scripts/test_lazy_core.py -k 'spawn_double or spawn_binding' -q` runs the new positive + negative meta-tests and both pass (live suite clean; synthetic always-succeeds spawn double reported, faithful double not reported).

**MCP Integration Test Assertions:** N/A — hermetic AST introspection, asserted by pytest.

**Prerequisites:**
- Phase 1: the `_collect_production_binding_smells` collector + the `test_ensure_runtime_production_*` enumeration + the allow-list class boundary. Phase 2 extends the same walk.

**Files likely modified:**
- `user/scripts/test_lazy_core.py` — extend the collector (or add a sibling) + add the two meta-tests; append to `_TESTS`.

**Testing Strategy:** Same self-contained shape as Phase 1. The positive meta-test green-proves the live spawn test already uses the faithful double; the negative fixture green-proves the guard catches an always-succeeds-double spawn-binding regression. The discriminator must be tight enough not to false-positive on the liveness/timing production tests that legitimately use `_FakeSubprocess` — the negative fixture's allow-listed sibling proves this.

**Integration Notes for Next Phase:**
- The convention chosen here (spawn-binding discriminator) is documented in Phase 3's CLAUDE.md note so a future author knows which double to use for which sub-case.

---

### Phase 3: Document the production-binding test convention + manual live cold-boot smoke step

**Scope:** Document the convention the Phase 1–2 guard enforces in `user/scripts/CLAUDE.md`'s `--ensure-runtime` section, and add the **manual/operator** live cold-boot smoke step (the only thing that has ever caught the spawn-invocation defect — NOT in-repo CI, environment-dependent). This is the human-facing half of the two-seam contract: the guard is the mechanical half; the smoke step is the operator's complement.

**Deliverables:**
- [ ] Add a "production-binding ensure_runtime test convention" note to `user/scripts/CLAUDE.md` (near the `--ensure-runtime` CLI surface): a `test_ensure_runtime_production_*` test MUST reach the OS signal under test by swapping `lazy_core.subprocess`/`lazy_core.time` and letting the default closure DERIVE the signal — it MUST NOT pass `boot_alive=`/`restart=` (the derivations). Name the legitimate external-collaborator allow-list and point at the Phase 1–2 guard tests as the enforcer. Reference the bug doc.
- [ ] Add a "manual live cold-boot smoke" step: the operator runs `python3 user/scripts/lazy-state.py --ensure-runtime --repo-root <real-AlgoBooth-checkout>` against a genuinely cold runtime (both ports down, no warm build) and confirms it reaches READY (not a false `mcp-runtime-unready` BLOCKED) — the live verification Round 34 used. Mark it explicitly as operator/manual, NOT a claude-config CI assertion (environment-dependent: needs a real checkout + cold runtime).
- [ ] Tests: docs-only phase — no automated test. Verification is a doc review (the CLAUDE.md note is present, accurate, cross-references the bug + the Phase 1–2 guard tests).

**Minimum Verifiable Behavior:** The `user/scripts/CLAUDE.md` `--ensure-runtime` section contains the production-binding convention note + the manual smoke step, cross-referencing `docs/bugs/adhoc-ensure-runtime-test-injects-signal-under-test/` and the Phase 1–2 guard test names. (Docs-only; verified by reading the rendered section.)

**MCP Integration Test Assertions:** N/A — documentation only.

**Prerequisites:**
- Phase 1 + Phase 2: the guard tests exist and their names are stable (the doc references them by name).

**Files likely modified:**
- `user/scripts/CLAUDE.md` — append the convention note + the manual smoke step to the `--ensure-runtime` surface documentation.

**Testing Strategy:** Doc review against the bug's Fix Scope item 3. No code; no automated gate. The cross-references to the Phase 1–2 guard tests must match the test names landed in those phases.

**Integration Notes for Next Phase:** Terminal phase. When this phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route forward.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed` and writes `FIXED.md` once this bug's validation tail passes — never authored as a checkbox row here.

---

## Implementation Notes

- **Origin / spin-off provenance:** this bug is the over-fit spin-off from harden-harness Round 33 (`docs/specs/turn-routing-enforcement/hardening-log/2026-06.md`), broadened by Round 34 to cover the spawn-invocation sub-case. No further spin-offs were created by this planning cycle.
- **Guard home decided in-cycle (⚖ D7):** `--test` meta-test (not a standalone `lint-production-binding-tests.py`) — co-located with the suite it polices, green-gated by the existing `pytest user/scripts/` + `python test_lazy_core.py` runs, mirroring the live `test_no_orphaned_test_functions` precedent. The SPEC named this as the recommendation; chosen because it is the most complete in-cycle path with no new CI wiring.
- **Convention encoding decided in-cycle (⚖ D7):** reuse the existing `test_ensure_runtime_production_*` name prefix (already in use, enumerable from source) rather than adding a new in-source registry tag. Smallest-that-subsumes the three cited instances; a future author can add a tag if the prefix proves too coarse.
- **Phase 2 spawn-binding discriminator (⚖ scope-class):** the boundary between a spawn-binding production test (must use the faithful double) and a liveness/timing production test (legitimately uses `_FakeSubprocess`) is encoded conservatively via a name/marker discriminator + the assertion surface (`shell_spawns`), preferred over over-broad AST inference to avoid false-positiving the liveness tests. The negative fixture's allow-listed sibling pins this.
- **Out of scope (SPEC, do NOT widen):** a speculative repo-wide false-green linter; any change to the production `ensure_runtime` derivation (correct as of Round 34); the AlgoBooth-side cross-repo re-home of this bug doc (orchestrator-owned, tracked separately).
