# PHASES — lazy-core-package-decomposition

**Status:** Complete
**MCP runtime:** not-required (pure state-plane refactor; SKIP_MCP_TEST class)
**Friction-reduction feature:** yes (KPI row `lazy-core-monolith-intervention-drag`)
**Last updated:** 2026-07-13

> **Sequencing reality (2026-07-13).** Phase 0 is the only phase that lands behavior-preservingly
> without resolving landmine **L1** (monkeypatch-by-attribute-assignment; see SPEC Decision Ledger +
> RESEARCH_SUMMARY). L1 is a PRODUCT fork requiring operator ratification of the facade mechanism
> (qualified-rewrite / forwarding-module-class / redirect-patches). Per the park-provisional protocol
> the run does NOT force a mechanism; it parks and stops at the last fully-green phase (Phase 0).
> **RATIFIED 2026-07-13 (operator, interactive): mechanism 3 — redirect-the-patches.** D4 = PEP 562
> lazy facade; D6 = ruff advisory-first. Test patch-target lines are the sanctioned edit surface
> (1125-test count + names preserved per move commit; byte baselines untouched).
> Each extraction phase below carries the **per-commit invariants**: move-only (modulo the L2/L3
> required anchors), full `test_lazy_core` suite + `lazy-state.py --test` + `bug-state.py --test`
> byte-baselines green, `lazy_parity_audit.py` exit 0, `cli_surface_gen.py --check` exit 0,
> `doc-drift-lint.py` exit 0, `lint-skills.py` exit 0 — with ZERO baseline regeneration.

## Phase 0 — Preconditions + benchmark harness ✅ COMPLETE (green)

- [x] Verify both hard-dep bug receipts exist (Fixed + archived).
      Evidence: `docs/bugs/_archive/mark-complete-partial-apply-noop-unrecoverable/FIXED.md`
      (`provenance: operator-directed-interactive`) and
      `docs/bugs/_archive/production-sentinel-writes-bypass-atomic-write/FIXED.md`.
- [x] Commit `user/scripts/benchmark_lazy_core_import.py` (stdlib, pure-read, additive — touches no
      existing behavior). Measures cold `import lazy_core` ms, pytest collect count/time, and the
      largest-module LoC census (flags >4K).
- [x] Stamp the measured baseline: cold import **88.7 ms best / 93.7 median**; collection **1125 tests
      / 0.30 s in-proc**; `lazy_core.py` **20,172 LoC** (over the 4K ceiling — the monolith).
- [x] Record the spec-refresh deltas (stale anchors) into RESEARCH_SUMMARY + SPEC Decision Ledger.

Proven done: receipts verified; benchmark runs and prints the baseline; no existing file's behavior
changed (only additive script + docs). Suite unaffected (no `lazy_core.py` edit).

## Phase 1 — Facade + `_ctx` skeleton (unblocked — L1 ratified)

- [x] Ratify the L1 facade mechanism (operator) — **RATIFIED 2026-07-13: mechanism 3,
      redirect-the-patches** (interactive session).
- [x] Create `user/scripts/lazy_core/` package; move the monolith body into it behind the ratified
      facade so `import lazy_core`, `from lazy_core import _atomic_write`, `lazy_core.notify_halt(...)`,
      and **module-attribute monkeypatching** all keep working byte-identically.
- [x] **L2 fix (required, not optional):** expose a `_SCRIPTS_DIR` anchor
      (`Path(__file__).resolve().parent.parent`) and repoint the six `__file__`-relative lookups
      (harness-gate@3141, validate-plan@3975, cycle-template@7659, `__file__`@7871, skill-path
      @12244/@12339) at it.
- [x] **L3 fix:** `_ctx.py` owns `_DIAGNOSTICS` (same list object), `_active_repo_root` +
      `_legacy_state_migrated` behind getter/setter; identity test
      `lazy_core._DIAGNOSTICS is lazy_core._ctx._DIAGNOSTICS` + a mutate-through-facade visibility test.
- [x] Update the `user/scripts/CLAUDE.md` `lazy_core.py` row → `lazy_core/` package in the SAME commit
      (doc-drift-lint doc→disk gate).
- [x] Importer-diff guard: no file outside the package + its tests (+ the doc row) is touched
      (commit 1a deviation, documented: `validate-plan.py` + `test_validate_plan.py` inbound flat-file
      loaders were a plan enumeration gap — reviewer-mandated fixes, included to keep the battery green).

Proven done: all 20 importers + 2 hooks + auditors green with zero edits; identity + patchability
tests pass; benchmark re-run recorded (facade alone may not cut hook cost — record the honest number).

## Phase 2 — Cleanest seams (docmodel, depdag, hostcaps, notify) ✅ COMPLETE (green)

- [x] Move `docmodel.py` / `depdag.py` / `hostcaps.py` / `notifyplane.py` out of the body.
      (Commits e1d31e28 / d35306c9 / c730a6bb / 5b1a57db — one move-only commit per seam.)
- [x] Retire the `_resolve_ntfy_send` facade-patch shim at the notifyplane extraction (operator
      ratified Option C, 2026-07-13, resolving the Phase-1 NEEDS_INPUT): redirect the two
      state-script `[notify-halt-call-site]` fixtures to `lazy_core.notifyplane._ntfy_send`,
      delete the shim — mechanism-3 becomes the SINGLE patch-visibility rule for all callers.
      Receipt: `grep -rn "_resolve_ntfy_send" user/scripts/` → ZERO hits (commit 5b1a57db).
- [x] Land the hook-touched `claude_state_dir`/`_load_registry`/`append_hook_event` in a small
      submodule so the D4 latency cut is realizable + re-measured. (`statedir.py`, 295 LoC;
      TDD pin `test_hook_surface_imports_without_monolith` RED→GREEN.)
- [x] Per-commit invariants green; import-ms delta in receipt. (Hook surface best 42.64 /
      median 43.98 ms, `monolith_loaded_samples=0`, vs the 88.7/93.7 ms Phase-0 full-monolith
      baseline — honest number: the <15 ms KPI aspiration is NOT met, interpreter+facade
      baseline dominates; guard marker paths still load `_monolith` until Phase 5.)

Proven done: 5 move-only commits, each with the full battery green (pytest `user/scripts/`
2219→2220 passed, both byte baselines untouched, parity/cli-surface/doc-drift/lint-skills exit 0);
suite 1141→1142 (one sanctioned TDD pin added); monolith 20,289 → 16,784 LoC.

## Phase 3 — Test split ✅ COMPLETE (green)

- [x] `tests/` per-seam files + `conftest.py` `tmp_repo` fixture (726 hand-rolled `TemporaryDirectory`
      sites today). Value here is editor ergonomics + per-seam selection, not collection time.
- [x] 1125-test count receipt-checked per move commit; names preserved. (Live count at execution:
      **1142** — the plan/PHASES literals were stale; receipt = 1142 pre == 1142 post, bare-name
      multiset identical. See Implementation Notes Phase 3.)

## Phase 4 — Medium seams (gates, ledgers, dispatch, runtime) ✅ COMPLETE (green)

- [x] `gates.py` / `ledgers.py` / `dispatch.py` / `runtimeplane.py`. Re-verify both bug receipts at the
      gate. Smoke byte-baselines byte-identical. (Receipts re-verified pre-edit; 4 move-only commits
      4d0988b5 / 26ce9313 / 27a592ed / <this> — battery 7/7 green per commit, ZERO baseline
      regeneration; collect-only 2230 pre == 2230 post per commit, bare-name multiset identical.
      `_monolith.py` 16,784 -> 7,858 LoC. See Implementation Notes Phase 4.)

## Phase 5 — Marker plane + pseudo (riskiest, last) ✅ COMPLETE (green)

- [x] `markers.py`, `pseudo.py` (`apply_pseudo`@4738, ~1,362 ln, moved INTACT — no internal refactor).
      (Commits a9e0581a / 4bd51536 — markers 56 names / pseudo one contiguous 1,576-line slice;
      apply_pseudo 1,354 lines BYTE-IDENTICAL by difflib receipt, zero internal edits.)
- [x] Body module deleted; every seam ≤4K LoC (benchmark census asserts).
      (Commit 147fd912 residue sweep + the WU-4 phase-receipt commit: `_monolith.py` git rm'd; facade map explicit-total
      486 entries, no fallback; census `over_4k_ceiling: []`, largest = ledgers 3,921 LoC.
      Battery 7/7 green per commit; collect 2230 pre == 2230 post (WU-1..3), 2231 post-WU-4
      (= 2230 + the one sanctioned TDD pin `test_facade_map_total_and_collision_free`);
      ZERO baseline regeneration. See IMPLEMENTATION_NOTES.md Phase 5.)

## Phase 6 — Lint gate + follow-up hooks ✅ COMPLETE (green)

- [x] Ruff F-rules on `user/scripts/`, advisory → enforcing. Note: headline F811 (`_current_head`)
      already fixed, so this is a forward guard, not a baseline-fix.
      (`ruff.toml` at repo root: `include = ["user/scripts/**/*.py"]`, `lint.select = ["F"]`,
      `dummy-variable-rgx = "^$"` — the last discovered necessary by the fixture red-check: ruff's
      default underscore-dummy convention silently exempted the exact `_current_head`-shaped
      motivating case from F811. Fixture red-check: an isolated planted duplicate-def fixture and
      an in-tree untracked probe both confirmed F811 fires; `ruff check .` from repo root confirmed
      scope resolution (2 stray out-of-scope `E501` findings come from a pre-existing, unrelated
      nested `pyproject.toml` in `user/plugins/local-tools/...` — ruff's own hierarchical config
      discovery, not a gate defect; `ruff check user/scripts` is the strictly-scoped invocation).
      Baseline: **145 findings** (F401 101 / F841 24 / F541 19 / F811 1) — advisory only, zero
      `lazy_core/` production edits. Documented in `user/scripts/CLAUDE.md` + root `CLAUDE.md`
      Lint Commands.)
- [x] Per-function-size measurement hook for the D7 compute_state follow-up.
      (`benchmark_lazy_core_import.py --function-sizes`: `ast`-based top-level function LoC
      census of `lazy-state.py` / `bug-state.py`, flagging each file's `compute_state` explicitly.
      Baseline: `lazy-state.py::compute_state` **2,144 ln** (line 1642), `bug-state.py::compute_state`
      **1,239 ln** (line 709) — measurement only, neither function refactored. TDD:
      `test_benchmark_function_sizes_reports_compute_state_monoliths` (`tests/test_lazy_core/test_misc.py`)
      asserts both entries present by name with plausible (>500) LoC.
      **Final KPI proxy re-measure (feature closing receipt, 2026-07-13):**
      (a) cold `import lazy_core`: best 39.30 / median 43.38 ms — vs the 88.7/93.7 ms Phase-0
      baseline (a real cut) but the <15 ms D4 aspiration is NOT met (interpreter+facade floor
      dominates, as every phase since Phase 2 has honestly recorded); hook surface: best 45.44 /
      median 48.39 ms, `monolith_loaded_samples=0` (structural since Phase 5's deletion, not merely
      observed). (b) collection: **1144** tests in the `test_lazy_core` suite (0.87s) — 1143 live
      pre-WU-2 + this WU's one sanctioned TDD pin; full `user/scripts/` suite **2232** (2231 pre +
      the same +1). (c) largest module: **3,921 LoC** (`lazy_core/ledgers.py`), `over_4k_ceiling: []`
      — target MET. (d) F-findings (WU-1): **145** (F401 101 / F841 24 / F541 19 / F811 1) —
      advisory baseline, not a target (D6 is advisory-first; enforcing-flip is future work).
      **KPI registry capture attempted and REFUSED (recorded verbatim, not fabricated):**
      `kpi-scorecard.py --capture-baseline lazy-core-monolith-intervention-drag --repo-root .` →
      `"no KPI row with id 'lazy-core-monolith-intervention-drag' in docs/kpi/registry.json"`
      (exit 1). The SPEC's `## KPI Declaration` drafted this row full-schema INLINE (per the
      friction-kpi-gate's sanctioned "full-schema drafted row" allowance) but it was never
      appended to the committed `docs/kpi/registry.json` — a gap in the drafted-row-to-registry
      promotion path, not a WU-2 defect; out of this phase's file-set to fix (registry.json is not
      an allowed WU-2 edit target). Flagged to `/harden-harness` (see Implementation Notes).)

## Implementation Notes

- The single behavior-preserving move tonight was Phase 0 (additive). Every subsequent phase edits the
  20K-line body and is gated on L1 — correctly parked, not forced.
- `lazy_coord.py` independence (must NOT import `lazy_core`) is a standing invariant across all phases.
- `phases-slice.py` keeps its byte-identical `_PHASE_HEADING_RE` copy — the docmodel split must not
  break the "keep in sync" obligation.
