# lazy-core-package-decomposition — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Facade + `_ctx` skeleton

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-13
**Work completed:**
- Package skeleton (WU-1): `git mv user/scripts/lazy_core.py user/scripts/lazy_core/_monolith.py` (R100, zero content edits in the move itself); hand-authored `lazy_core/__init__.py` — permanent PEP 562 lazy facade (`_SUBMODULE_BY_NAME` overrides, `_FALLBACK_SUBMODULE="_monolith"`, `_ALL_SUBMODULES=("_ctx","_monolith")`, non-memoizing `__getattr__` with a submodule-name branch, `__dir__`, `load_all()`).
- Scripted patch-target redirect (WU-1, ratified L1 mechanism 3): every `lazy_core.<name>` → `lazy_core._monolith.<name>` in `test_lazy_core.py` for the 25 census names. **Receipt:** 165 occurrences rewritten, 0 residual; per-name assignment-site counts matched the census exactly and sum to **50 assignment sites** (the plan's "43" headline was arithmetic slippage — its own per-name table sums to 50). Zero `monkeypatch.setattr(lazy_core`/`patch.object(lazy_core` anywhere.
- `_ctx.py` extraction (WU-2, TDD — 4 contract tests written RED-first by an independent test agent): owns `_DIAGNOSTICS` (same list object — identity-pinned across facade/_ctx/_monolith), `_diag`, `clear_diagnostics` (in-place `.clear()`, identity-pinned), `_atomic_write` (shared kernel, byte-identical move), and accessor-based storage for the rebindables (`get_active_repo_root`/`set_active_repo_root_value`, `legacy_state_migrated`/`set_legacy_state_migrated`). `_monolith` rebind/read sites rewired through the accessors (set_active_repo_root body, active_repo_root read, migration guard); mechanism-3 test redirects for `_legacy_state_migrated`/`_active_repo_root` → `_ctx` (the resolving module); the 2 `_monolith._atomic_write` patch sites deliberately stay at `_monolith`.
- L2 `_SCRIPTS_DIR` anchor (WU-3): `_ctx._SCRIPTS_DIR = Path(__file__).resolve().parent.parent`; all six `__file__`-relative lookups repointed (harness-gate.py, validate-plan.py, cycle-template dir, `_here` sys.path fallback, 2× skill-path candidates). Zero `__file__` refs remain in `_monolith.py`.
- Doc row + manifest + canary (WU-4): `user/scripts/CLAUDE.md` row → `lazy_core/` (dir form); `docs/gate/control-surfaces.json` + `_CANARY_CONTROL_SURFACES_FALLBACK` → `user/scripts/lazy_core/**` (glob semantics verified against `_canary_glob_to_re`); 3 canary test fixtures retargeted intent-preservingly; `GATE_VERDICT.md` recorded (overfit flag-justified, tautology flag-justified, gate_weakening pass, complexity declared; checker: in_scope, no gate-weakening hit).
- `load_all()` wiring (WU-5, commit 1b): eager `lazy_core.load_all()` as first statement of `main()` in BOTH state scripts (coupled-pair lockstep; SPEC D4-A ImportError-timing mitigation; hooks deliberately not wired).

**Receipts (per-commit invariants):**
- Full battery green before commit 1a: pytest `user/scripts/` **2216 passed, 0 failed**; `lazy-state.py --test` + `bug-state.py --test` byte-pinned baselines pass (ZERO baseline regeneration); `lazy_parity_audit.py` exit 0; `cli_surface_gen.py --check` OK; `doc-drift-lint.py` 0 findings; `lint-skills.py` OK.
- Count+names receipt: pre-split collect = **1135 names**; post-Phase-1 = **1139** = the same 1135 preserved byte-identically + exactly the 4 sanctioned `_ctx` contract tests (`test_ctx_diagnostics_identity`, `test_ctx_mutation_visible_through_facade`, `test_ctx_rebindable_globals_via_accessors`, `test_monolith_patch_target_effective`); diff shows zero removals/renames.
- Benchmark re-run (`benchmark_lazy_core_import.py`, 2026-07-13, post-move): cold `import lazy_core` **best 36.34 ms / median 38.89 ms** vs the 88.7/93.7 ms Phase-0 baseline — the lazy facade defers the 20k-line `_monolith` import on bare import, a ~59% cut (better than the "may be a wash" expectation; the honest caveat: an eager consumer that touches any monolith attribute still pays the full load, so hook-path savings apply only to probes that never touch `_monolith` attributes). Collection 1139 in 0.85 s. LoC census: `_monolith.py` 20,289 (over the 4K ceiling — expected at Phase 1; later phases shrink it).
- Hooks-live check: `lazy-state.py --marker-present --repo-root .` exits cleanly, no traceback.

**Integration notes:**
- The facade NEVER memoizes forwarded attributes (patchability contract); only the eager `_DIAGNOSTICS` identity re-export is bound into facade globals (sanctioned — mutated in place, never rebound).
- Patch-redirect rule for later phases: a test patching by module-attribute assignment targets the module whose function-under-test RESOLVES the name. When a name moves out of `_monolith` into a new submodule, its patch sites move with it (the WU-2 `_ctx` redirects are the template), and `_SUBMODULE_BY_NAME` gets the new entries.
- `_ctx.py` is a leaf: it must never import `_monolith` or the facade.
- `test_monolith_patch_target_effective` pins `_notify_identity`'s clock read — revisit that pin when `_notify_identity` moves out of `_monolith`.

**Pitfalls & guidance (for later phases + retro):**
- **Plan enumeration gap (inbound seams):** the plan fixed all six OUTBOUND `__file__` lookups but enumerated no WU for INBOUND flat-file loaders of `lazy_core.py`. Two existed: `validate-plan.py::_load_lazy_core` (production — its failure was converted to a silent `{'ok': True}` by the structural backstop's broad fail-open, a false-green caught only by the batch-3 reviewer) and `test_validate_plan.py:34-38` (collection error). Both fixed to package imports; included in commit 1a as a documented importer-diff-guard deviation.
- **In-flight-state racing incident (initially logged as a falsified report — corrected):** the WU-3 impl agent's session outlived its first completion notification and kept working through the later batches; the red `plan_structural_backstop` state the batch-3 reviewer and the orchestrator observed was its IN-FLIGHT tree, and its final tree was genuinely 1139-green. The reviewer's independent re-run still added real value (it surfaced the validate-plan inbound seam early and precisely). Orchestration lesson for the retro: a subagent's completion notification is not proof its writes have settled — re-verify on a quiesced tree, and never stage (`git add -A`) while any dispatched agent may still be writing.
- **`_resolve_ntfy_send` shim (landed in commit 1a via the long-lived WU-3 session; reviewed post-hoc, PASS-WITH-NOTES):** `notify_halt`'s two `sender` closures now resolve the ntfy sender via `_monolith._resolve_ntfy_send()`, which honors a facade-level `lazy_core._ntfy_send = fake` patch (a plain `sys.modules["lazy_core"].__dict__` read — never triggers the facade `__getattr__`; unpatched behavior byte-identical). Rationale: the state scripts' in-file `[notify-halt-call-site]` smoke fixtures patch at facade level and were outside Phase-1's writable scope. This is a SECOND patch-visibility mechanism alongside ratified mechanism-3 — flagged to harden-harness to either bless it as the pattern for external-harness facade patches or redirect those fixtures in a later phase and retire the shim.
- **Canary fixture staleness:** swapping the manifest literal to a glob broke 3 canary tests whose fixtures used the exact old path; fixtures retargeted (`_monolith.py` for touch-fixtures, the glob literal for tuple-membership asserts).
- Harden-harness follow-ups spun off (see run report): (a) `run_structural_checks`'s fail-open converts loader crashes into silent structural-gate passes — should degrade to an ERROR finding; (b) stale path-arithmetic prose at `_monolith.py:7726` and ~12300/~12392 and the `migrate_legacy_state_dir` docstring.

**Review verdicts (batch audit trail):**
- Batch 1 (WU-1): PASS. Batch 2 (WU-2): PASS. Batch 3 (WU-3): NEEDS-REWORK (inbound validate-plan seam) → fixed → re-verified green. Batch 4 (WU-4 + canary fixtures): PASS (inline, deviation noted — all edits deterministically gate-verified).

**Files modified:**
- `user/scripts/lazy_core/{__init__.py,_ctx.py,_monolith.py}` — package skeleton (facade / kernel / moved body with sanctioned L2/L3 edits)
- `user/scripts/test_lazy_core.py` — mechanism-3 redirects (165 occurrences), 4 new `_ctx` contract tests (+ `_TESTS` registration), path/collector/canary accommodations
- `user/scripts/validate-plan.py`, `user/scripts/test_validate_plan.py` — inbound loaders → package imports (plan-gap fixes)
- `user/scripts/CLAUDE.md` — `lazy_core/` package row
- `docs/gate/control-surfaces.json` — `user/scripts/lazy_core/**` glob (+ in-body canary mirror)
- `docs/features/lazy-core-package-decomposition/GATE_VERDICT.md` — recorded gate verdict
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` — eager `load_all()` in `main()` (commit 1b)
