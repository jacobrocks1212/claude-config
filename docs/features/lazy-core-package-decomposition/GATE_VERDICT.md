---
kind: gate-verdict
feature_id: lazy-core-package-decomposition
gate_version: 1
date: 2026-07-13
scope_hit: [docs/gate/control-surfaces.json, user/scripts/lazy_core/__init__.py, user/scripts/lazy_core/_ctx.py, user/scripts/lazy_core/_monolith.py]
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: the flat single-file `user/scripts/lazy_core.py` monolith module and its single-file control-surface glob (replaced by the `user/scripts/lazy_core/` package behind a permanent PEP 562 facade + the scope-preserving-and-widening manifest glob `user/scripts/lazy_core/**`)
override: absent
---

# GATE_VERDICT — lazy-core-package-decomposition Phase 1 (commit 1a diff)

Checker run: `python3 user/scripts/harness-gate.py --repo-root . --staged --feature-dir docs/features/lazy-core-package-decomposition --json` (2026-07-13, staged Phase-1 diff at pre-commit-1a tree). `in_scope: true`, `gate_weakening_hit: false`, `verdict_required: true` (overfit flag + tautology flag + complexity declaration-required).

## Adversarial answers

### overfit

The detector fired on ~40 "literal element appended to a membership construct" evidence lines. Partitioned honestly:

1. **Detector noise (the majority):** docstring lines and pytest assertion-message strings inside the new `_ctx.py` module and the four new `_ctx` contract tests (e.g. `"same list object"`, `"legacy_state_migrated()"`). These are message literals in additive test/docstring code, not matcher entries — no rule was extended.
2. **The real membership adds:** (a) the facade's `_SUBMODULE_BY_NAME` entries (`_DIAGNOSTICS`/`_diag`/`clear_diagnostics`/`_atomic_write`/`_SCRIPTS_DIR` → `_ctx`) and `_ALL_SUBMODULES = ("_ctx", "_monolith")`; (b) the manifest swap `user/scripts/lazy_core.py` → `user/scripts/lazy_core/**` (mirrored in `_CANARY_CONTROL_SURFACES_FALLBACK`).

**Nearest recurrence this does NOT catch:** a future decomposition phase extracting a new submodule (e.g. `_notify.py`) whose names are forgotten in `_SUBMODULE_BY_NAME`. That miss is STRUCTURALLY covered, not literal-covered: the facade's `__getattr__` falls back to `_monolith` for any unmapped name, and once a name physically leaves `_monolith` the 1139-test suite fails loudly on the first `lazy_core.<name>` access — the map is the routing mechanism itself (keyed on submodule ownership of names), not an incident-fitted allow-list. The manifest glob keys on the STRUCTURE that generates the class (any file under the package = state-machine core), which is strictly wider than the retired single-file literal — coverage widens; nothing is exempted.

### tautology

Checker: `no ## Intervention Hypothesis block` in the SPEC. **If this change were broken, how would its success metric look?** Different, loudly: the phase's success signals are all emitted by systems the change does not control — (a) the 1135-test pre-split pytest suite + the byte-pinned `--test` baselines (`user/scripts/tests/baselines/*`, ZERO regeneration allowed), whose red/green is computed by pytest over independent fixtures; (b) the collected-name-set receipt (pre-split 1135 names preserved exactly, +4 sanctioned `_ctx` contract pins); (c) the declared friction KPI row `lazy-core-monolith-intervention-drag` in `docs/kpi/registry.json` (PHASES preamble: `**Friction-reduction feature:** yes`), scored by `kpi-scorecard.py` over the telemetry ledger — not by this diff. A broken facade cannot make those look identical to working (`signal_independence: independent`).

### gate_weakening

`result: pass` — no test deletions (the suite GREW 1135 → 1139), no numeric gate change, no exemption/sanction membership add, no bypass env-var, no deny-branch removal. The manifest glob swap is scope-preserving-and-widening (single file → whole package superset); the three canary test-fixture updates retarget the same assertions at the new glob/paths without weakening any assertion. The test patch-redirect edits (`lazy_core.<name>` → `lazy_core._monolith.<name>`/`_ctx`) are the operator-ratified L1 mechanism-3 sanctioned surface (2026-07-13), count+names receipt attached in IMPLEMENTATION_NOTES.md.

### complexity

`retires:` the flat 20,289-line `user/scripts/lazy_core.py` module as a single unsplittable surface, and its single-file manifest glob. Net-new surface added: `lazy_core/__init__.py` (83-line facade) + `lazy_core/_ctx.py` (98-line kernel) — the machinery that makes the remaining decomposition phases possible; the retire is real (the old path no longer exists on disk; `doc-drift-lint.py` and the manifest both track the package form; the old glob stops matching anything).

---

# GATE_VERDICT — lazy-core-package-decomposition Phase 4 (medium seams, 4 move-only commits)

Checker run: `python3 user/scripts/harness-gate.py --repo-root . --staged --feature-dir docs/features/lazy-core-package-decomposition --json` (2026-07-13, staged WU-1 `gates.py` diff). `in_scope: true`, `gate_weakening: pass`, `verdict_required: true` (overfit flag + tautology flag + complexity declaration-required). This entry covers all four Phase-4 seam commits (`gates.py` / `ledgers.py` / `dispatch.py` / `runtimeplane.py`) — identical diff shape: verbatim slice out of `_monolith.py`, facade-map membership adds, by-value import-backs, sanctioned deferred function-local imports, mechanism-3 test patch-target redirects.

## Adversarial answers (Phase 4)

### overfit
The detector fires on the facade `_SUBMODULE_BY_NAME` membership adds (one entry per moved name) and `_ALL_SUBMODULES` growth. Same partition as the Phase-1 verdict: the map IS the routing mechanism (keyed on submodule ownership), not an incident-fitted allow-list. **Nearest recurrence not caught:** a later phase forgetting a name's entry — structurally covered by the `_monolith` fallback + the 2230-test suite failing loudly on first facade access of a physically-moved unmapped name (this phase moved 224 names; every one is exercised through the facade by the suite and the two byte-pinned `--test` baselines).

### tautology
Unchanged from Phase 1: the phase's success signals are computed by systems the diff does not control — the live pre-captured collect-only baseline (2230 tests / 1142 lazy_core, count + bare-name multiset preserved per commit), the byte-pinned `--test` baselines (ZERO regeneration), and the parity/cli-surface/doc-drift/lint gates. A broken move cannot render those identical to working (`signal_independence: independent`).

### gate_weakening
`pass` from the checker on every seam commit. No test deletions; the ONE sanctioned guard-code edit class this phase carries (WU-4: the production-binding meta-guard token comments in `test_runtimeplane.py`) RETARGETS `lazy_core._monolith.subprocess/time` → `lazy_core.runtimeplane.*` — the collectors themselves key on the STRUCTURAL `lazy_core.<any>.subprocess` attribute chain (no code change needed) and their positive meta-tests assert a non-empty matched population, with negative-fixture twins proving non-vacuity.

### complexity
`retires:` (incrementally, per the Phase-1 declaration) the monolithic residency of the completion-gate / ledger / dispatch / runtime planes inside `_monolith.py` — post-Phase-4 the monolith shrinks from 16,784 to a marker/pseudo core (Phase 5's remaining scope); no new mechanism is added beyond the four seam modules the SPEC's target structure names.

---

# GATE_VERDICT — lazy-core-package-decomposition Phase 5 (markers + pseudo + residue + monolith deletion, 4 commits)

Checker runs: `python3 user/scripts/harness-gate.py --repo-root . --staged --json` per commit (2026-07-13). All four commits `in_scope: true`, `verdict_required: true`. WU-1 (markers, a9e0581a) and WU-2 (pseudo, 4bd51536): overfit flag + **gate_weakening: hit** + complexity declaration-required. WU-3 (147fd912) / WU-4: overfit flag, gate_weakening pass.

## Adversarial answers (Phase 5)

### overfit
Same partition as the Phase-1/Phase-4 verdicts: the detector fires on the facade `_SUBMODULE_BY_NAME` membership adds (one per moved name — the map IS the routing mechanism, keyed on submodule ownership, not an incident allow-list) and on docstring/message literals inside the verbatim-moved code. **Nearest recurrence not caught:** post-WU-4 there is NO fallback — a forgotten map entry now fails LOUDLY (clean AttributeError on first facade access) instead of silently resolving, and `test_facade_map_total_and_collision_free` pins totality + per-name resolution + definition-site uniqueness mechanically. Coverage strictly tightened.

### tautology
Unchanged from Phases 1/4: success signals are computed by systems the diff does not control — the live pre-captured collect-only baseline (2230 tests, count + bare-name multiset preserved per move commit; 2231 after the one sanctioned RED-first pin), the byte-pinned `--test` baselines (ZERO regeneration), and the parity/cli-surface/doc-drift/lint gates (`signal_independence: independent`).

### gate_weakening
**WU-1/WU-2 checker result: `hit` — justified as the two sides of a byte-verbatim MOVE, not a weakening; operator sign-off owed and requested (D4 is never judgment-passable):**
- "gate-refusal construct removed" (`refuse_if_cycle_active` / `refuse_cycle_marker_mutation_if_subagent` / `refuse_run_start_clobber` deleted from `_monolith.py`): each function exists BYTE-IDENTICALLY in `markers.py` in the same commit (scripted verbatim-slice receipts; the refusal test population in `tests/test_lazy_core/test_markers.py` — exit-3 semantics, env-priority order, zero-side-effect contracts — ran green against the moved code in the same commit's battery).
- "exemption/sanction-set membership added" (`SANCTIONED_STOP_TERMINAL`, `CYCLE_REFUSED_OPS`, `_FORWARD_ADVANCING_PSEUDO_SKILLS`, `AUDITED_CYCLE_KINDS` re-appearing in `markers.py`): ZERO members added or removed — the sets moved verbatim; the facade map rows are routing entries, not sanction grants.
- No test was deleted (suite 2230 -> 2231); no numeric gate changed; no bypass env-var added; the WU-4 `__getattr__` fallback deletion is facade-mechanics (a STRICTER resolution — unmapped names now hard-fail), explicitly not a gate deletion (plan risk note d).
- The ONE deliberate assertion CHANGE this phase: `test_hook_surface_imports_without_monolith` re-pointed from the now-vacuous `_monolith not in sys.modules` to the STRICTER loaded-set-within-{facade, `_ctx`, `statedir`} assertion — a strengthening, with the D4 intent preserved.
Sign-off status: **pending operator ratification** — recorded provisionally per the park-provisional directive in `NEEDS_INPUT_PROVISIONAL.md` (this feature's gate machinery is itself structurally provisional under anti-overfit-design-gate D1/D3/D4/D7).

### complexity
`retires:` `_monolith.py` itself (the transitional body module — 20,289 LoC at Phase 1, 0 now; `git rm`'d), the facade's `_FALLBACK_SUBMODULE` mechanism, and every `# Phase-5 re-point` deferred-import IOU (24 sites re-pointed to final owners; 2 genuine-cycle function-local imports recorded). Net-new surface: `markers.py` + `pseudo.py` (the final two seam modules the SPEC's target roster names) + one facade-totality test. No new mechanism beyond the SPEC's fixed D1-A roster.
