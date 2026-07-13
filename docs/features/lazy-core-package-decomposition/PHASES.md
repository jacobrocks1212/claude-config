# PHASES — lazy-core-package-decomposition

**Status:** In-progress (Phase 0 Complete; L1 ratified 2026-07-13 → mechanism 3 redirect-the-patches; Phases 1–6 unblocked)
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
- [ ] Create `user/scripts/lazy_core/` package; move the monolith body into it behind the ratified
      facade so `import lazy_core`, `from lazy_core import _atomic_write`, `lazy_core.notify_halt(...)`,
      and **module-attribute monkeypatching** all keep working byte-identically.
- [ ] **L2 fix (required, not optional):** expose a `_SCRIPTS_DIR` anchor
      (`Path(__file__).resolve().parent.parent`) and repoint the six `__file__`-relative lookups
      (harness-gate@3141, validate-plan@3975, cycle-template@7659, `__file__`@7871, skill-path
      @12244/@12339) at it.
- [ ] **L3 fix:** `_ctx.py` owns `_DIAGNOSTICS` (same list object), `_active_repo_root` +
      `_legacy_state_migrated` behind getter/setter; identity test
      `lazy_core._DIAGNOSTICS is lazy_core._ctx._DIAGNOSTICS` + a mutate-through-facade visibility test.
- [ ] Update the `user/scripts/CLAUDE.md` `lazy_core.py` row → `lazy_core/` package in the SAME commit
      (doc-drift-lint doc→disk gate).
- [ ] Importer-diff guard: no file outside the package + its tests (+ the doc row) is touched.

Proven done: all 20 importers + 2 hooks + auditors green with zero edits; identity + patchability
tests pass; benchmark re-run recorded (facade alone may not cut hook cost — record the honest number).

## Phase 2 — Cleanest seams (docmodel, depdag, hostcaps, notify) ⛔ after Phase 1

- [ ] Move `docmodel.py` / `depdag.py` / `hostcaps.py` / `notifyplane.py` out of the body.
- [ ] Land the hook-touched `claude_state_dir`/`_load_registry`/`append_hook_event` in a small
      submodule so the D4 latency cut is realizable + re-measured.
- [ ] Per-commit invariants green; import-ms delta in receipt.

## Phase 3 — Test split ⛔ after Phase 2 (de-prioritized — collection already 0.30 s)

- [ ] `tests/` per-seam files + `conftest.py` `tmp_repo` fixture (726 hand-rolled `TemporaryDirectory`
      sites today). Value here is editor ergonomics + per-seam selection, not collection time.
- [ ] 1125-test count receipt-checked per move commit; names preserved.

## Phase 4 — Medium seams (gates, ledgers, dispatch, runtime) ⛔ write-path; Phase-0 re-check

- [ ] `gates.py` / `ledgers.py` / `dispatch.py` / `runtimeplane.py`. Re-verify both bug receipts at the
      gate. Smoke byte-baselines byte-identical.

## Phase 5 — Marker plane + pseudo (riskiest, last) ⛔

- [ ] `markers.py`, `pseudo.py` (`apply_pseudo`@4738, ~1,362 ln, moved INTACT — no internal refactor).
- [ ] Body module deleted; every seam ≤4K LoC (benchmark census asserts).

## Phase 6 — Lint gate + follow-up hooks ⛔

- [ ] Ruff F-rules on `user/scripts/`, advisory → enforcing. Note: headline F811 (`_current_head`)
      already fixed, so this is a forward guard, not a baseline-fix.
- [ ] Per-function-size measurement hook for the D7 compute_state follow-up.

## Implementation Notes

- The single behavior-preserving move tonight was Phase 0 (additive). Every subsequent phase edits the
  20K-line body and is gated on L1 — correctly parked, not forced.
- `lazy_coord.py` independence (must NOT import `lazy_core`) is a standing invariant across all phases.
- `phases-slice.py` keeps its byte-identical `_PHASE_HEADING_RE` copy — the docmodel split must not
  break the "keep in sync" obligation.
