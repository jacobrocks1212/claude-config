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
