# Implementation Phases — Stale merged-view parity fixtures missing `--archive-fixed` predicate

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Fixed

**MCP runtime:** not-required — pure-Python unit-test fixture text edit in `user/scripts/test_lazy_parity.py`; no app surface, no Tauri/MCP-reachable behavior (docs/features/mcp-testing/SPEC.md "untestable: build/test tooling" class). Verification is `pytest user/scripts/ -q`.

## Validated Assumptions

All load-bearing assumptions here are **code-provable** — the audit is a pure function over fixed fixture text (`audit_merged_view_dispatch_parity` greps each driver's SKILL.md string against the 6-tuple `_MERGED_VIEW_PREDICATES`). No runtime-coupled assumption exists; the Runtime Assumption Validation gate is skipped (every assumption is determinable from source). Ground truth confirmed by direct Read of both files this cycle:

- `user/scripts/lazy_parity_audit.py:360-377` — `_MERGED_VIEW_PREDICATES` is a 6-tuple: `--next-merged`, `__mark_complete__`, `__mark_fixed__`, `bug-state\.py`, `[Ss]ingle-type\b`, `--archive-fixed`. (verified)
- `audit_merged_view_dispatch_parity` (`:380-415`) emits one finding per `(driver, missing-predicate)` across both files in `_MERGED_VIEW_DRIVER_FILES`. (verified)
- The "full"/"consistent" hermetic fixture strings each carry the first 5 predicates but omit `--archive-fixed`. (verified — grep below)

## Touchpoint Audit (verified this cycle via Read/Grep — no Agent dispatch; inline per dispatch override)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / directive |
|--------------|---------|-------------------------|--------|-------------------|
| `user/scripts/test_lazy_parity.py` | yes | `class TestMergedViewDispatchParity` with `test_fires_when_cloud_missing_merged_branch` (L727-743), `test_fires_when_terminal_dispatch_inconsistent` (L745-773), `test_fires_when_no_regression_guard_absent` (L775-801), `test_passes_when_both_drivers_consistent` (L803-821) | edit (fixture strings) | Add an `--archive-fixed` bug-archive clause to each WORKSTATION/`full` fixture string so it satisfies all 6 predicates. Do NOT touch the deliberately-broken cloud fixtures (L735-737 `## Cloud driver`; L764-768 drops `__mark_fixed__`; L792-796 drops single-type) — their inconsistency is the test's point. |
| `user/scripts/lazy_parity_audit.py` | yes | `_MERGED_VIEW_PREDICATES`, `audit_merged_view_dispatch_parity` | NO CHANGE | Correct as-is — 6 predicates incl. `--archive-fixed`. |
| `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | yes | merged-view dispatch prose | NO CHANGE | Already carry `--archive-fixed` (grep 1 + 2); real-repo audit clean. |

**Blast radius:** the audit function is consumed only by the tests in `TestMergedViewDispatchParity` and `audit_all_pairs`. No production caller reads these fixture strings; the edit is fixture-text only. No symbol signature changes.

## Scope note — completeness (extends SPEC §"Scope decision (D7)")

The SPEC's D7 decision (SPEC line 96) resolved to fix all **stale "full" fixtures** uniformly, naming three tests. Ground-truth re-inspection this cycle found a **fourth** workstation-side `full`-style fixture carrying the same stale text:

- `test_fires_when_cloud_missing_merged_branch` (`:727-733`) — the `skills` (workstation) driver fixture also omits `--archive-fixed`. Its assertion is `any("lazy-batch-cloud" ... "next-merged" ...)`, so the latent `--archive-fixed` gap against the `skills` driver does not fail it today, exactly as with the other latent fixtures.

⚖ policy: fix 3 SPEC-named or all 4 stale workstation fixtures → fix all 4 in-cycle

This is the same scope-class as the SPEC's own D7 (no product-behavior divergence — the test intent that a "full"/consistent workstation fixture satisfies ALL current predicates is identical across all four). Taking the most-complete in-cycle path per the standing completeness policy: all FOUR workstation `full`/consistent fixtures get the `--archive-fixed` clause, so no future predicate-scope assertion change can re-expose the gap in any of them. The deliberately-inconsistent cloud-side fixtures are explicitly out of scope (their omissions are load-bearing to their tests). REVERSE-REFERENCE: this extension is recorded here; no separate bug/feature doc is spun off (it is in-scope completeness for this same fix, not out-of-scope discovered work).

## Cross-feature Integration Notes

No hard deps on Complete upstreams (this is a self-contained test-fixture defect; the `--archive-fixed` predicate's origin feature `lazy-batch-unified-driver-parity-and-accounting` is referenced for provenance only, not consumed as a contract). Omitted.

---

### Phase 1: Add the `--archive-fixed` clause to all stale workstation "full"/consistent merged-view fixtures

**Scope:** In `user/scripts/test_lazy_parity.py`, extend each WORKSTATION-side `full`/consistent hermetic fixture string in `TestMergedViewDispatchParity` so its merged-view dispatch prose names the `--archive-fixed` bug-archive follow-up — satisfying the 6th predicate (`--archive-fixed`) the `_MERGED_VIEW_PREDICATES` tuple now requires. The clause is added uniformly to all four workstation fixtures (the one failing test plus three latent ones). The deliberately-broken cloud-side fixtures are NOT touched.

**Deliverables:**
- [x] `test_passes_when_both_drivers_consistent` (`:812-818`) `full` string: add an `--archive-fixed` bug-archive clause (e.g. "; a fixed bug chains the `--archive-fixed` archive + de-queue follow-up"). This is the test that FAILS today; after the edit `audit_merged_view_dispatch_parity(tmp_path) == []` holds (both drivers write this same `full` string).
- [x] `test_fires_when_no_regression_guard_absent` (`:784-789`) workstation `full` string: add the same `--archive-fixed` clause. (The cloud fixture at `:792-796` is left omitting single-type — that omission is the test's assertion.)
- [x] `test_fires_when_terminal_dispatch_inconsistent` (`:756-761`) workstation `full` string: add the same `--archive-fixed` clause. (The cloud fixture at `:764-768` is left dropping `__mark_fixed__` — load-bearing to the test.)
- [x] `test_fires_when_cloud_missing_merged_branch` (`:727-733`) workstation `skills` fixture string: add the same `--archive-fixed` clause (D7 completeness extension above). (The cloud fixture at `:735-737` `## Cloud driver` is left without any merged branch — load-bearing.)
- [x] Tests: the existing `TestMergedViewDispatchParity` suite is the test surface — no NEW test is authored. The edited fixtures ARE the test data; their assertions already encode the contract (consistent → `[]`; inconsistent-on-a-DIFFERENT-predicate → still fires). The fix is verified by the suite turning fully green (Minimum Verifiable Behavior below).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_parity.py -q` reports `0 failed` (all `TestMergedViewDispatchParity` tests green, including `test_passes_when_both_drivers_consistent` which fails pre-fix), AND the targeted command from the SPEC's Reproduction Steps now passes: `python -m pytest user/scripts/test_lazy_parity.py -q -k "test_passes_when_both_drivers_consistent"` → `1 passed`. Full repo suite `python -m pytest user/scripts/ -q` is fully green (`0 failed`).

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/test_lazy_parity.py` — extend the four workstation `full`/consistent fixture strings in `TestMergedViewDispatchParity` to name `--archive-fixed`. No other file changes.

**Testing Strategy:**
Pure-function audit over fixed fixture text — fully deterministic, no mocks, no runtime. Run the targeted reproduction command first (must flip from `1 failed` to `1 passed`), then the whole `test_lazy_parity.py` module, then the whole `user/scripts/` suite. Each edited inconsistency test must STILL fire on its own predicate (single-type / `__mark_fixed__` / `next-merged`) — adding `--archive-fixed` to the workstation fixture must not change which finding the cloud-side omission produces, because the cloud fixtures are untouched. A regression here would manifest as one of the three `*_fires_*` tests flipping to no-longer-fires; the suite catches it.

**Integration Notes for Next Phase:**
- None — single-phase fix. Implementation done → top-level PHASES `**Status:**` flips to `In-progress` (validation pending); the state machine routes to the validation tail. The `__mark_fixed__` gate (orchestrator-owned) writes `FIXED.md` and flips SPEC/PHASES to `Fixed` after the tail — never hand-flipped here.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md top-level `**Status:**` to `Fixed` and writes `FIXED.md` once this fix's verification (full-suite green) is certified by the validation tail. Not authored as a checkbox row here.

#### Implementation Notes

**Date:** 2026-06-19
**Executed inline** (dispatch override — no Agent tool in bug-pipeline cycle subagent).

**RED → GREEN evidence:**
- Pre-fix: `python -m pytest user/scripts/test_lazy_parity.py -q -k "test_passes_when_both_drivers_consistent"` → `1 failed` with `missing bug archive --archive-fixed chain (pattern '--archive-fixed')`.
- Post-fix: `1 passed`.

**Fixtures edited (all workstation/skills side only — cloud fixtures byte-unchanged):**
1. `test_fires_when_cloud_missing_merged_branch` (`:727-733`) — appended `" A fixed bug chains the \`--archive-fixed\` archive + de-queue follow-up."` before the closing `\n`.
2. `test_fires_when_terminal_dispatch_inconsistent` (`:756-761`) — same clause appended.
3. `test_fires_when_no_regression_guard_absent` (`:784-789`) — same clause appended.
4. `test_passes_when_both_drivers_consistent` (`:812-818`) — same clause appended (this was the failing test; clause written to BOTH `skills` and `cloud` fixtures since they are identical in this test).

**Clause used (uniform across all 4):** ` A fixed bug chains the \`--archive-fixed\` archive + de-queue follow-up.`

**Cloud fixtures unchanged:** L735-737 (`## Cloud driver`), L764-768 (drops `__mark_fixed__`), L792-796 (drops single-type) — all untouched; their deliberate omissions remain load-bearing.
`_MERGED_VIEW_PREDICATES` and `audit_merged_view_dispatch_parity` in `lazy_parity_audit.py` — NOT touched.

**Quality gates:**
- `pytest user/scripts/test_lazy_parity.py -q -k test_passes_when_both_drivers_consistent` → `1 passed`
- `pytest user/scripts/test_lazy_parity.py -q` → `29 passed`
- `pytest user/scripts/ -q` → `883 passed, 0 failed`

**Review verdict:** PASS — only 4 workstation fixture strings changed; cloud fixtures byte-unchanged; `_MERGED_VIEW_PREDICATES` untouched; all `*_fires_*` tests still fire on their own predicates.

---
