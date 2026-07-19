# Implementation Phases — Merged-head oracle: model operator-defer in feature compute_state

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

**MCP runtime:** not-required — pure static state-machine logic in `lazy-state.py` / `lazy_core`; no Tauri/MCP-reachable surface. Verified deterministically by the in-file `--test` smoke harnesses + `pytest tests/test_lazy_core/` + `lazy_parity_audit.py` (the claude-config invariant gate battery), never by a live runtime.

## Touchpoint Audit (verified inline — dispatch unavailable, per spec-phases Step B fallback)

`verified: inline (dispatch unavailable — cycle subagent)`. Every path read against the live tree.

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy-state.py` | yes | `compute_state` walk loop; scoped cloud/device/host skip branches (~2051–2260); scoped `TR_*_SCOPED`/`STEP_*_SCOPED` constants (414–438); **no** `_OPERATOR_DEFERRED` accumulator, **no** bare-`DEFERRED.md` branch (comment at :407 documents the absence) | refactor | ADD a bare-`DEFERRED.md` operator-defer skip branch mirroring `bug-state.py:1126–1160`. Reuse `_scoped_skip_state(...)` (already used by every sibling scoped branch), `docmodel.spec_dir_operator_deferred(...)`, and `_diag(...)`. ADD feature-side `TR_OPERATOR_DEFERRED_SCOPED` / `STEP_OPERATOR_DEFERRED_SCOPED` constants + `_OPERATOR_DEFERRED` module list + `operator_deferred` probe key + an `all-remaining-deferred`-shaped global terminal — the feature twins of the bug-side literals below. |
| `user/scripts/bug-state.py` | yes | `_OPERATOR_DEFERRED` (293), operator-defer branch (1126–1158), `TR_OPERATOR_DEFERRED_SCOPED="operator-deferred"` (187), `TR_ALL_DEFERRED="all-remaining-deferred"` (157), global terminal (1460–1469), `--test` fixtures `operator-deferred-skip` / `all-operator-deferred` (3310, 3346) + scoped fixtures (5262) | **reference-only (NOT edited)** | The exact parity MODEL. Byte-untouched — the feature side mirrors it. |
| `user/scripts/lazy_core/dispatch.py` | yes | `_candidate_operator_deferred(iid)` (770–774), `_op_defer_dir` map plumbing (750–768), walk-loop application (822–829), primary `is_dispatchable(scoped_probe(iid))` (830) | refactor | RETIRE the `_candidate_operator_deferred` supplement + its `_op_defer_dir` plumbing + the 822–829 application, **gated on** the R102 oracle regression staying green with the primary `is_dispatchable` mechanism alone (which now covers features once Phase 1 lands). |
| `user/scripts/lazy_core/docmodel.py` | yes | `spec_dir_operator_deferred` (2299–2339) — docstring at 2324–2330 asserts the FEATURE `compute_state` "ignores it, so the merged-head oracle's file-predicate is the ONLY thing that excludes such a feature" | edit docstring; **KEEP the symbol** | Rewrite the "ONLY thing" / "feature pipeline has no operator-`DEFERRED.md` dispatch branch" language — the feature `compute_state` now models operator-defer. The predicate itself STAYS (still consumed by BOTH `compute_state`s' own park/skip classification). |
| `user/scripts/lazy_core/depdag.py` | yes | merged-worklist docstring (1437–1445) citing the file-predicate at the merged head | edit docstring | Reflect that the primary `is_dispatchable` re-inference now covers both pipelines. |
| `user/scripts/lazy_parity_audit.py` | yes | `audit_state_script_parity` | verify (no edit expected) | Confirm the new feature-side branch is a JUSTIFIED divergence or a mirrored surface; `lazy_parity_audit.py --repo-root .` must stay exit 0. |
| `user/scripts/tests/test_lazy_core/test_dispatch.py` | yes | R102 oracle regression suite | edit | Keep the R102 regression (operator-deferred cross-pipeline feature excluded from the merged head) green with the SUPPLEMENT REMOVED — the primary mechanism must now carry it. |
| `user/scripts/tests/baselines/lazy-state-test-baseline.txt` | yes | byte-pinned `lazy-state.py --test` output | regenerate | New feature-side fixtures change the output; regenerate ONLY via the `_normalize_smoke_output` helper (never by hand). |
| `lazy-state.py` in-file `--test` harness | yes (same file) | fixture-list block + `def test_*` fns | add | Add feature-side fixtures mirroring `bug-state.py`'s `operator-deferred-skip` / `all-operator-deferred` / scoped-operator-deferred fixtures. |

No premise-grade contradictions: the SPEC's serving-path trace matches the live code exactly (feature `compute_state` has no operator-defer branch; oracle carries the supplement). All audit findings are anchor-grade and already-true — nothing to correct or halt on.

## Runtime Assumption Validation

**Gate skipped** — every load-bearing assumption is code-provable. This is pure static state-machine logic (SPEC Consistency: "always … not runtime-coupled"): the fix adds a deterministic branch read from an on-disk `DEFERRED.md` predicate, asserted by the hermetic `--test` fixtures + `pytest`. No user-facing surface exists (a CLI state machine), so the reachability axiom is N/A. MCP tool-existence audit: no-op (claude-config declares no `mcp-tool-catalog.md`). SPEC-example capability audit: the SPEC's only "code examples" are the reproduction commands (`lazy-state.py --feature-id <slug>`) and the `bug-state.py` parity model — all verified-present surfaces, zero rejected capabilities.

## Fix-planning decisions (both scope-class, D7 — end-state product behavior identical)

- ⚖ policy: retire vs keep oracle supplement → RETIRE (the durable generalization; gated on R102 regression green). Operator-deferred features are excluded from the merged head + never `/spec`-dispatched either way — this only differs in whether the churn-prone patch survives. Retiring IS the bug's stated intent; kept as belt-and-suspenders it re-invites the four-round churn. Taken in-cycle (Phase 2), gated on the R102 regression passing with the primary mechanism alone.
- ⚖ policy: feature scoped-identity terminal shape → MIRROR bug-side (`TR_OPERATOR_DEFERRED_SCOPED`). A `--feature-id`-scoped probe on a deferred feature returns its own identity (not a null-identity global terminal), exactly as `bug-state.py:1138–1150` — the most complete `--feature-id` probe symmetry.

---

### Phase 1: Feature-side operator-defer branch (fixes the near-neighbor)  ✅ Complete

**Scope:** Give the FEATURE `compute_state` walk loop a bare-`DEFERRED.md` operator-defer skip branch, mirroring `bug-state.py:1126–1160`. This directly fixes Reproduction A (the feature pipeline dispatching `/spec` on an operator-EXCLUDED feature) and makes `is_dispatchable(scoped_probe(feature))` return false for an operator-deferred feature — the precondition Phase 2's supplement-retirement depends on.

**Deliverables:**
- [x] Feature-side scoped constants in `lazy-state.py`: `TR_OPERATOR_DEFERRED_SCOPED` + `STEP_OPERATOR_DEFERRED_SCOPED` (twins of `bug-state.py:187,253`), alongside the existing `TR_*_SCOPED` block (~414–438).
- [x] Module-level `_OPERATOR_DEFERRED: list[str]` accumulator + its per-`compute_state` `.clear()` (twin of `bug-state.py:293,865`), surfaced in the probe dict as an `operator_deferred` key (twin of `bug-state.py:372`).
- [x] The operator-defer skip branch in the `compute_state` walk loop: on `(spec_path / "DEFERRED.md").exists()`, a scoped `--feature-id` match returns `_scoped_skip_state(... TR_OPERATOR_DEFERRED_SCOPED ...)`; otherwise append to `_OPERATOR_DEFERRED`, `_diag(...)`, `continue`. Placed to mirror the bug-side ordering (before the park branches). Reuse `docmodel.spec_dir_operator_deferred` for the predicate.
- [x] Global `all-remaining-deferred`-shaped feature terminal in the `current is None` block (twin of `bug-state.py:1460–1469`), fired when `_OPERATOR_DEFERRED` non-empty and no workable successor. (NOT added to `lazy_core.SANCTIONED_STOP_TERMINAL` — verified the bug-side literal is NOT registered there either; matched the bug side exactly.)
- [x] Tests: feature-side `--test` fixtures — `operator-deferred-skip` (a `DEFERRED.md` feature parked, an actionable feature dispatched), `all-operator-deferred` (only feature has `DEFERRED.md` → global terminal), scoped-operator-deferred + unscoped-regression twin, and `operator-deferred-control` (no `DEFERRED.md` → dispatchable via `/spec`). Regenerated `tests/baselines/lazy-state-test-baseline.txt` via `_normalize_smoke_output`.

**Implementation Notes (2026-07-19):**
- Landed in `lazy-state.py`: constants `TR_OPERATOR_DEFERRED_SCOPED="operator-deferred"` / `TR_ALL_DEFERRED="all-remaining-deferred"` / `STEP_OPERATOR_DEFERRED_SCOPED` (beside the `TR_*_SCOPED` block), module list `_OPERATOR_DEFERRED` + `.clear()` (beside `_HOST_SATURATED.clear()`), the always-present `operator_deferred` probe key, the walk-loop skip branch (after the host-capability block, before `skip_needs_research` — mirrors bug-side ordering), and the global `all-remaining-deferred` terminal (after `host-capability-saturated`, before the research terminal).
- The stale divergence comment at `lazy-state.py:~407` ("has NO operator-DEFERRED.md branch — bug-pipeline-only JUSTIFIED divergence") was UPDATED to record the divergence is now CLOSED.
- Predicate reuse: the branch calls `lazy_core.spec_dir_operator_deferred(spec_path)` (never an inline `DEFERRED.md` existence check); the `_diag` reason reads via `parse_sentinel`.
- `_OPERATOR_DEFERRED` accumulates the feature DISPLAY name (mirrors bug-side `_OPERATOR_DEFERRED.append(bug_name)` and the feature-side `_DEVICE_DEFERRED.append(name)`).
- Gates green: `lazy-state.py --test`, `bug-state.py --test`, full `pytest tests/test_lazy_core/` (exit 0), `lazy_parity_audit.py --repo-root .` (exit 0 — bug-state.py untouched; feature side gained the branch the bug side already had, a CLOSED divergence).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` passes with the new fixtures, and a scoped probe on a `DEFERRED.md` feature dir routes NOT to `/spec`: `python3 user/scripts/lazy-state.py --repo-root <tmp> --feature-id <deferred-slug>` returns a `terminal_reason` of `operator-deferred` (scoped), never `sub_skill: /spec`. Both are runnable commands driving the real state machine.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior outside the deterministic `--test`/probe surface.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — new constants, `_OPERATOR_DEFERRED` accumulator, walk-loop branch, global terminal, `--test` fixtures.
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated output.

**Testing Strategy:** In-file `--test` fixtures (hermetic temp-dir feature queues) assert: parked-vs-dispatched skip, scoped identity preservation, all-deferred terminal, control re-inclusion. TDD: write the fixtures first (RED — feature currently routes `/spec` on a `DEFERRED.md` dir), then add the branch (GREEN). Run `pytest tests/test_lazy_core/` to confirm no shared-helper regressions.

**Integration Notes for Next Phase:**
- After this lands, `is_dispatchable(scoped_probe(feature))` returns false for an operator-deferred feature (it surfaces a scoped operator-deferred terminal like the bug pipeline). Phase 2 depends on this being true before removing the oracle's file-predicate.
- Keep `docmodel.spec_dir_operator_deferred` importable — the new feature branch consumes it (as does the bug branch); it is NOT retired.

---

### Phase 2: Retire the oracle file-predicate supplement (the durable generalization)  ✅ Complete

**Scope:** Remove the `_candidate_operator_deferred` supplement and its `_op_defer_dir` plumbing from `dispatch.py::merged_head_nondispatchable_ids`. With Phase 1 landed, the oracle's PRIMARY mechanism — `is_dispatchable(scoped_probe(iid))` at `dispatch.py:830` — now excludes operator-deferred features on its own for BOTH pipelines, so the churn-prone per-signal patch (re-added across R56/R57/R101/R102) retires. This fixes Reproduction B at its source.

**Deliverables:**
- [x] Remove `_candidate_operator_deferred(iid)` (`dispatch.py:770–774`) and the `_op_defer_dir` map construction (`dispatch.py:750–768`).
- [x] Remove the walk-loop application (`dispatch.py:822–829`), so each candidate falls through to the primary `is_dispatchable(scoped_probe(iid))` classification. Preserve the `break`-on-first-dispatchable-head / `exclude`-and-continue control flow.
- [x] Confirm no other caller references `_candidate_operator_deferred` / `_op_defer_dir` (grep the module — clean); left `spec_dir_operator_deferred` (docmodel) intact — still consumed by both `compute_state`s (removed only the now-unused `from .docmodel import spec_dir_operator_deferred` import inside the oracle).
- [x] Tests: kept the R102 oracle regression GREEN with the supplement gone (re-pointed its injected `scoped_probe` to model Phase-1 reality — the feature `compute_state` now returns the scoped operator-deferred terminal → excluded via `is_dispatchable(scoped_probe)` alone). Added a new SERVING-PATH subprocess regression (`test_subprocess_bug_emit_prompt_oracle_excludes_operator_deferred_feature_head_no_withhold`) driving the real `bug-state.py --emit-prompt` with an operator-deferred feature at the merged head → NO withhold, workable bug dispatched, NO file-predicate. R56/R57/R101 oracle regressions stay green.

**Implementation Notes (2026-07-19):**
- `dispatch.py::merged_head_nondispatchable_ids`: removed the `_op_defer_dir` map construction, the `_candidate_operator_deferred` helper, its walk-loop application, the rationale comment block, and the now-unused `from .docmodel import spec_dir_operator_deferred` import. The walk loop now classifies every candidate solely via `is_dispatchable(scoped_probe(iid))` (the primary mechanism), preserving break-on-first-dispatchable / exclude-and-continue.
- Acceptance gate MET: the R102 regression (both the re-pointed unit test AND the new real-serving-path subprocess test) stays green with the supplement gone — Phase 1's feature branch carries the exclusion. No `BLOCKED.md` needed.
- `spec_dir_operator_deferred` KEPT in docmodel.py — now consumed by both `compute_state`s' own park/skip classification (Phase 1's new feature branch is a consumer) rather than by the retired oracle supplement.
- Registered the new test in `test_dispatch.py`'s `_TESTS` list (the `test_no_orphaned_test_functions` dead-coverage guard requires it).
- Gates green: `pytest tests/test_lazy_core/` (851 passed — the whole suite, incl. `test_dispatch.py` 180, `test_depdag.py` 28, `test_markers.py` baseline 221, the orphan guard), `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py --repo-root .` (exit 0).

**Minimum Verifiable Behavior:** `pytest tests/test_lazy_core/test_dispatch.py` passes with the supplement removed — specifically the operator-deferred-cross-pipeline-feature exclusion regression passes using only `is_dispatchable(scoped_probe(...))`. Runnable command; drives the real oracle.

**MCP Integration Test Assertions:** N/A — deterministic pytest coverage of the pure oracle function.

**Prerequisites:**
- Phase 1: the feature `compute_state` operator-defer branch must exist so `is_dispatchable(scoped_probe(feature))` returns false for a deferred feature — otherwise removing the supplement re-opens Reproduction B. This gate is the deliverable's acceptance condition (the R102 regression staying green IS the proof).

**Files likely modified:**
- `user/scripts/lazy_core/dispatch.py` — remove supplement + plumbing + application.
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — R102 regression retained/adjusted for the primary-mechanism-only path; new feature-exclusion regression.

**Testing Strategy:** Run `pytest tests/test_lazy_core/test_dispatch.py` (oracle unit suite) plus the full `pytest tests/test_lazy_core/`. The R102 regression is the load-bearing acceptance test: if it fails after removal, Phase 1's feature branch is not covering the case and the retirement is blocked (fall back to keeping the supplement — the ⚖ retire decision is gated exactly here).

**Integration Notes for Next Phase:**
- Once removed, the "ONLY thing that excludes such a feature" docstring claims in `docmodel.py` / `depdag.py` are stale — Phase 3 corrects them.

---

### Phase 3: Docstring correction, parity confirmation, and full gate battery

**Scope:** Update the docstrings the R102 fix left asserting the feature `compute_state` "ignores" operator-defer, confirm state-script parity treats the new feature branch correctly, and run the full claude-config invariant gate battery to certify no regression across the state machine.

**Deliverables:**
- [x] Update `docmodel.py::spec_dir_operator_deferred` docstring (2299–2339): rewrite the "the FEATURE `compute_state` … ignores it, so the merged-head oracle's file-predicate is the ONLY thing that excludes such a feature" and "the feature pipeline has no operator-`DEFERRED.md` dispatch branch" language to state the feature `compute_state` now models operator-defer (mirroring the bug pipeline); note the predicate is still consumed by both `compute_state`s.
- [x] Update `depdag.py` merged-worklist docstring (1437–1445): reflect that the primary `is_dispatchable` re-inference now covers both pipelines' operator-deferred items (the file-predicate supplement retired).
- [x] Confirm `python3 user/scripts/lazy_parity_audit.py --repo-root .` is exit 0 — the feature-side operator-defer branch is a justified feature/bug divergence or a mirrored surface (document which in the audit's parity manifest if it needs a divergence note).
- [x] Update the root `CLAUDE.md` / `user/scripts/CLAUDE.md` prose where they document the feature side as having "NO operator-`DEFERRED.md` branch (bug-pipeline-only — JUSTIFIED divergence)" (e.g. `lazy-state.py:405–407` comment + the scripts-doc parity notes), so the docs no longer describe the now-closed divergence.
- [x] Tests: run the full battery — `python3 user/scripts/lazy-state.py --test`, `python3 user/scripts/bug-state.py --test`, `pytest tests/test_lazy_core/`, `lazy_parity_audit.py --repo-root .`, `python3 user/scripts/doc-drift-lint.py --repo-root .`, and `lint-skills.py` — all green.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0 AND both `--test` baselines match, proving the feature-side change preserved parity and state-machine behavior. Runnable commands.

**MCP Integration Test Assertions:** N/A — docs + deterministic gate battery only.

**Prerequisites:**
- Phase 2: the supplement must be removed before its "ONLY thing" docstrings can be corrected without lying about live code.

**Files likely modified:**
- `user/scripts/lazy_core/docmodel.py` — docstring.
- `user/scripts/lazy_core/depdag.py` — docstring.
- `user/scripts/lazy-state.py` — the `:405–407` "no operator-DEFERRED branch" comment (now describes the present branch).
- `user/scripts/CLAUDE.md`, root `CLAUDE.md` — parity-divergence prose, if it names this divergence.
- `user/scripts/lazy-parity-manifest.json` — only if a divergence note is needed for the new branch.

**Testing Strategy:** Run the full invariant gate battery (both state-script `--test` harnesses, `pytest tests/test_lazy_core/`, the parity audit, the doc-drift lint). Doc-drift lint is the specific guard that the CLAUDE.md prose edits stay consistent with reality.

**Integration Notes for Next Phase:** None — final phase. When this phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending); the state machine routes to the validation tail and the orchestrator's `__mark_fixed__` gate owns the terminal flip + `FIXED.md` receipt.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed, writes `FIXED.md`, and archives the bug dir once the validation tail passes — never authored as a checkbox here.

**Implementation Notes (2026-07-19):**
- Dispatched a Sonnet implementation agent (non-TDD, documentation-only) to correct the two stale docstrings — both are `.py` files, so the orchestrator contract required a subagent dispatch rather than a direct `Edit`.
- `docmodel.py::spec_dir_operator_deferred`'s docstring (paragraphs 3–4) rewritten: no longer claims the feature pipeline "has no operator-`DEFERRED.md` dispatch branch" or that the oracle's file-predicate is "the ONLY thing" excluding an operator-deferred feature. Now states the predicate is consumed directly by BOTH state scripts' own `compute_state` (bug-state.py's original branch + lazy-state.py's Phase-1 branch), and that the oracle's direct file-predicate application was retired in Phase 2 as no longer necessary (its primary `is_dispatchable`/scoped-probe re-inference now covers both pipelines).
- `depdag.py`'s `merged_worklist` docstring (the `exclude_ids` param, ~1436–1450) rewritten: no longer claims the oracle "STILL applies the `spec_dir_operator_deferred` file-predicate directly" — now states the primary re-inference covers both pipelines uniformly and the file-predicate supplement was retired.
- The `lazy-state.py` `~:405–407` comment deliverable turned out to be a **no-op**: it was already corrected during Phase 1's implementation (commit `e2e2773e`) as a natural side effect of adding the feature-side branch — grep confirmed zero remaining "JUSTIFIED divergence" / "no operator-DEFERRED" occurrences before this phase started.
- The root `CLAUDE.md` / `user/scripts/CLAUDE.md` deliverable is also a **no-op** — grepped both files for "operator-defer" (case-insensitive) and found zero mentions of the now-closed divergence; nothing to correct there.
- `lazy_core/dispatch.py::merged_head_nondispatchable_ids` was verified (not edited) — its own docstring already accurately describes the retired supplement (no `spec_dir_operator_deferred` call remains in its body).
- `lazy_parity_audit.py --repo-root .` exits 0 with no findings — no divergence note was needed in `lazy-parity-manifest.json` (the predicate is a shared `lazy_core` helper consumed identically by both scripts' `compute_state`, not a coupled-pair skill-file surface the audit tracks).
- Full invariant gate battery run and green: `lazy-state.py --test` (all smoke fixtures pass), `bug-state.py --test` (all smoke fixtures pass), `pytest user/scripts/tests/test_lazy_core/ -q` (1280 passed), `lazy_parity_audit.py --repo-root .` (exit 0), `doc-drift-lint.py --repo-root .` (exit 0, 2 pre-existing unrelated exempted divergences), `lint-skills.py` (exit 0).
- No production behavior changed — docstring/prose edits only, verified via `ast.parse` on both touched files.
