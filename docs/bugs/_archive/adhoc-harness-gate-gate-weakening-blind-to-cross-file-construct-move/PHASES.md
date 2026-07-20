# Implementation Phases — harness-gate `gate_weakening` blind to a cross-file construct move

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure stdlib Python diff-analysis function (`harness-gate.py` is READ-ONLY over git, not on any state-script path); the entire deliverable is verified by `pytest` fixtures over synthetic diffs, structurally outside any MCP-reachable app surface.

## Validated Assumptions

Every load-bearing assumption is **code-provable** (a pure function over a synthetic diff — no runtime, build, IPC, or app surface), so the Step-2.7 Runtime Assumption Validation gate is **skipped by rule**. Ground truth confirmed by direct source read during the touchpoint audit:

- `detect_gate_weakening` (`user/scripts/harness-gate.py`) builds `removed_deny`/`added_deny` and `removed_test_defs`/`added_test_defs` tallies **keyed per file** (`h.file`), then flags `net = removed[f] - added.get(f, 0) > 0` in two structurally-identical per-file loops. A construct removed from file A and re-added in a sibling file B within the same change nets `+1` on A and is misread as an unreplaced removal. (SPEC cited lines 298–304/284–289; the live loops sit at ~302–322 after prior hardening rounds — anchor-grade mechanical drift, corrected here, no behavior change.)
- `Hunk` exposes `.file`, `.removed` (removed line bodies), `.added` (added line bodies); `parse_diff` yields one `Hunk` per file-hunk. `_DENY_BRANCH_RE` (`permissionDecision…deny | \bexit 3\b | refuse_[a-z_]+\s*\(`) and `_TEST_DEF_RE` (`^\s*def\s+test_*`) are the construct matchers, already used with `.findall`/`.match`.
- The existing **same-file** net-count reconciliation is a COUNT parity check, not text-identity: the reformat FP fixture (`test_gate_weakening_reformatted_refuse_call_not_flagged`) removes `refuse_if_cycle_active("…")` and adds `refuse_if_cycle_active(` — DIFFERENT text, but 1 removed match == 1 added match within the file → net zero. This behavior MUST be preserved (the cross-file fix is additive, not a replacement of the count-net logic).

## Locked Decisions honored

**Locked Decision 1 (SPEC):** cross-file reconciliation uses **(b) content-identity move detection** — a removal in file A is reconciled (treated as a MOVE, not a removal) ONLY when the *same construct text* is added in file B within the same change. Aggregate-net (a) and exemption-marker (c) shapes are explicitly NOT implemented. This bounds the false-negative surface: an unrelated deny construct added in file B never masks a genuine removal in file A (they are different texts).

## Anti-overfit / harness-change-gate note (control-surface edit)

This fix edits a **control surface** (`harness-gate.py`, on the manifest's `gate_own` block) AND **relaxes a detector** (it makes `gate_weakening` `hit` on strictly fewer diffs). It therefore routes to operator `GATE_VERDICT.md` sign-off at the completion-gate ship seam (`lazy_core.gate_verdict_ok`), per `_components/harness-change-gate.md` D7 (gate-weakening always halts for sign-off). The relaxation is **precise, not a blanket loosening**: only a *content-identical* cross-file move is exempted; every genuine removal, every same-file reformat (unchanged), and every true-positive fixture stays flagged. The regression fixtures below are the adversarial evidence that the nearest genuine-removal recurrence this rule does NOT catch does not exist — a cross-file add of a *different* construct text still hits.

### Phase 1: Content-identity cross-file move reconciliation for `gate_weakening`

**Status:** Fixed

**Scope:** Make `detect_gate_weakening` reconcile removed-vs-added gate-refusal constructs (`_DENY_BRANCH_RE`) and `def test_*` definitions **across the whole change's file set** using content-identity (option b), so a construct/text removed from file A and re-added verbatim in file B within one change is a MOVE (not flagged), while genuine removals, same-file reformats, and cross-file adds of *different* constructs stay flagged. TDD — regression fixtures first (RED), then the detector change (GREEN).

**Deliverables:**
- [x] Cross-file-move FP regression fixtures added to `user/scripts/test_harness_gate.py`: (1) a deny-construct MOVE (`"permissionDecision": "deny",` removed from `block-sentinel-write-on-stray-branch.sh`, added to `hook-prelude.sh` in the same diff) asserts `result == "pass"`; (2) a `def test_*` MOVE between two test files asserts `result == "pass"`; (3) a cross-file NON-move (a genuine removal in file A + an add of a *different* deny construct text in file B) asserts `result == "hit"` (guards option (b)'s false-negative bound). These require a multi-file diff — build the diff string inline (or extend the single-file `_diff` helper with a small multi-file builder).
- [x] `detect_gate_weakening` (`user/scripts/harness-gate.py`) reconciles the per-file net removal against the same construct text added ELSEWHERE in the change: track the actual removed/added construct texts (the `_DENY_BRANCH_RE`-matched substrings and the `_TEST_DEF_RE` lines) per file, keep the existing same-file count-net reconciliation (reformat handling — UNCHANGED), and before flagging a file's residual net removal, subtract removals whose exact construct text appears in another file's adds. Apply the identical shape to BOTH the deny-construct loop and the `def test_*` loop (both are blind the same way).
- [x] Tests: the three new FP/TP fixtures above PASS, and every existing `test_gate_weakening_*` fixture stays green — specifically the same-file reformat FPs (`reformatted_refuse_call`, `renamed_test_def`, `renamed_def_signature`, `split_test_def_strengthening`) and the true positives (`removed_refuse_construct_still_hits`, `genuine_test_removal_still_hits`, `deny_branch_removal`).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_harness_gate.py` (or `pytest user/scripts/test_harness_gate.py`) is fully green, AND the SPEC's one-shot reproduction (a `"permissionDecision": "deny",` line moved from a hook into `hook-prelude.sh` in one diff) now prints `{'result': 'pass', 'evidence': []}` where it previously printed `{'result': 'hit', ...}`.

**Prerequisites:** None (single-phase fix).

**Files likely modified:**
- `user/scripts/harness-gate.py` — refactor the two per-file net-removal loops in `detect_gate_weakening` to add whole-change content-identity reconciliation (reuse `_DENY_BRANCH_RE` / `_TEST_DEF_RE`; keep the per-file count-net reformat handling).
- `user/scripts/test_harness_gate.py` — add the three cross-file-move fixtures; extend/inline a multi-file diff builder.

**Testing Strategy:**
Deterministic, hermetic — pure functions over synthetic diff strings via the existing in-file `pytest`/`_diff` harness. Red-then-green: the two MOVE fixtures fail on the current per-file loop (RED for the documented reason — the removal is not reconciled against the sibling add), pass after the reconciliation change (GREEN); the cross-file NON-move fixture and all existing same-file + true-positive fixtures pin that the relaxation is bounded and does not weaken genuine detection.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed`, writes `FIXED.md`, and archives the bug dir once this phase's tests pass and the validation tail clears. This control-surface / gate-relaxing edit additionally routes to an operator `GATE_VERDICT.md` sign-off at the ship seam (`harness-change-gate.md` D7).

**Integration Notes for Next Phase:**
- N/A — single phase. The reconciliation is additive: the per-file count-net logic (which handles same-file single→multi-line reformats where removed and added TEXT differ but COUNTS match) stays intact; content-identity only rescues removals whose exact construct text reappears in another file's adds. Do not collapse the two mechanisms — pure text-identity alone would break the same-file reformat FP fixtures (different text, count parity), and pure count-aggregate alone is option (a), which the Locked Decision rejects for its false-negative surface.

**Implementation Notes (landed 2026-07-19):**
- Added `from collections import Counter` and a new pure helper `_cross_file_reconciled_net(removed_texts, added_texts)` to `user/scripts/harness-gate.py`. It runs the two-stage reconciliation: (1) same-file COUNT-net (unchanged — preserves the reformat/rename/split FPs, gated on `net > 0`), then (2) cross-file content-identity — a shared `Counter` pool of each file's added texts that EXCEED its own removals absorbs a residual removal whose EXACT construct text appears in another file, consumed once per match (no double-crediting). Only a residual removal with no equivalent re-add anywhere still contributes to `net`.
- `detect_gate_weakening`'s two per-file count-dict loops were replaced with per-file TEXT lists (`removed_test_def_texts`/`added_test_def_texts` = matched `_TEST_DEF_RE` def lines; `removed_deny_texts`/`added_deny_texts` = matched `_DENY_BRANCH_RE` substrings), each fed through the shared helper. The evidence-message wording (`gate-test definition removed…` / `gate-refusal construct removed…`) and same-file-count numbers are preserved byte-for-byte, so the existing TP fixtures' `any("… removed" in e)` assertions stay green.
- SEAM B (bug completion evidence): the regression is on the symptom's ACTUAL serving path — `detect_gate_weakening` itself. `test_gate_weakening_cross_file_deny_move_not_flagged` IS the SPEC's one-shot reproduction (deny line moved into `hook-prelude.sh`); it was RED (`hit`, "net 1; 1 removed, 0 added") pre-fix and is GREEN (`{'result': 'pass', 'evidence': []}`) post-fix. Direct MVB re-run confirmed the same verdict.
- Gate result: `pytest user/scripts/test_harness_gate.py` → 41 passed (38 pre-existing + 3 new). This is a control-surface / detector-RELAXATION edit (fewer `hit`s) — it routes to operator `GATE_VERDICT.md` sign-off at the ship seam by design, NOT a reason to weaken the change.
