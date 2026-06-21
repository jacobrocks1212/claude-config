# Implementation Phases — Stale `TestStateScriptParity` fixtures missing the `--reassert-owner` + `requires_host` fail-fast surfaces

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress

**MCP runtime:** not-required — pure-Python unit-test fixture text edit in `user/scripts/test_lazy_parity.py`; no AlgoBooth app surface, no Tauri/MCP-reachable behavior (per `docs/features/mcp-testing/SPEC.md`: build/test tooling is the "untestable" class). Verification is `python -m pytest user/scripts/test_lazy_parity.py -q`.

## Provenance

This bug is **test-fixture staleness only** (SPEC `## Proven Findings`, Theory 1 Confirmed). `audit_state_script_parity` (`user/scripts/lazy_parity_audit.py:334`) now checks **four** coupled-pair surfaces per state script:

| # | Surface | Required token(s) in a stub | Added by |
|---|---------|-----------------------------|----------|
| 1 | active-repo binding | `set_active_repo_root(args.repo_root)` (optionally `lazy_core.`-prefixed) | `multi-repo-concurrent-runs` |
| 2 | operator-only reorder | `"--reorder-queue"` | `no-sanctioned-queue-reorder-command` |
| 3 | orchestrator-only re-arm | `"--reassert-owner"` | `single-slot-marker-ownership-race-disarms-owning-run` (Phase 2) |
| 4 | host-capability fail-fast | `format_unknown_host_capability_blocker` **AND** `unknown-host-capability` | `host-capability-declaration-for-gated-features` (Phase 6) |

The three synthetic `tmp_path` fixtures (`test_lazy_parity.py:638`–`702`) write minimal stubs carrying only surfaces **1+2** — they predate surfaces 3 and 4. So the clean-fixture stub trips both new assertions (2 scripts × 2 surfaces = "4 more items"), and the two fires-when-missing stubs assert a stale `len == 1` while the audit now emits more.

**Real-repo audit is GREEN** (`python user/scripts/lazy_parity_audit.py --repo-root .` exits 0): the real `lazy-state.py`/`bug-state.py` carry all four surfaces. **No production code change** — the guard is correct; only its own unit-test fixtures lag it. The fix is confined to `user/scripts/test_lazy_parity.py`.

**Coupling note:** this PHASES.md follows the resolved prior-art bug `docs/bugs/_archive/adhoc-parity-merged-view-fixture-stale-archive-fixed` (same class — stale parity fixtures missing a newly-added audit predicate). The fix touches no `lazy_parity_audit.py` logic and no state-script source; it edits only the fixture stub strings + the fires-when-missing expectations so each test isolates exactly ONE missing surface.

## Touchpoint Audit (verified this cycle via Read — no Agent dispatch; inline per dispatch override)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / directive |
|--------------|---------|-------------------------|--------|-------------------|
| `user/scripts/test_lazy_parity.py` | yes | `class TestStateScriptParity` — `test_live_state_scripts_bind_active_repo` (`:627`, real-repo, PASSES), `test_audit_state_script_parity_fires_when_binding_missing` (`:638`), `_fires_when_reorder_queue_missing` (`:663`), `_clean_when_both_bind` (`:685`) | edit (fixture stub strings + expectations) | Add surfaces 3+4 tokens to each stub; keep each fires-when-missing fixture dropping exactly ONE surface so `len == 1` holds. |
| `user/scripts/lazy_parity_audit.py` | yes | `audit_state_script_parity` (`:334`), the four surface regexes (`:299`/`:305`/`:310`/`:328`+`:331`) | NO CHANGE | Authoritative four-surface contract the fixtures must match. |
| `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` | yes | the real four-surface implementations | NO CHANGE | Real scripts already carry all four (real-repo audit exit 0). |

**Blast radius:** the audit function's only fixture-consumers are the four tests in `TestStateScriptParity`. No production caller reads these stub strings; the edit is fixture-text only. No symbol signature changes.

---

### Phase 1: Update the three `TestStateScriptParity` fixtures to the full four-surface token set

**Scope:** In `user/scripts/test_lazy_parity.py`, rewrite the `tmp_path` stub strings (and the fires-when-missing expectations) in the three failing tests so each stub carries the surfaces it should and drops exactly the one surface the test asserts on. Surfaces 3 (`"--reassert-owner"`) and 4 (`format_unknown_host_capability_blocker` + `unknown-host-capability`) are added to every stub that is not deliberately dropping them. No `lazy_parity_audit.py` change, no state-script change.

**Deliverables:**
- [x] `test_audit_state_script_parity_clean_when_both_bind` (`:685`–`702`): both stub scripts (`lazy-state.py`, `bug-state.py`) carry ALL FOUR surface tokens — binding + `"--reorder-queue"` + `"--reassert-owner"` + `format_unknown_host_capability_blocker` + `unknown-host-capability` — so `audit_state_script_parity(tmp_path) == []`. (Preserve the existing bare-vs-`lazy_core.`-prefixed binding-form coverage across the two stubs.)
- [x] `test_audit_state_script_parity_fires_when_binding_missing` (`:638`–`661`): both stubs carry surfaces 2+3+4; only `bug-state.py` drops the binding (surface 1) → `len(findings) == 1` naming the binding gap. Add `"--reassert-owner"` + the host-capability tokens to BOTH stubs (the `lazy-state.py` stub already has binding + reorder; the `bug-state.py` stub keeps reorder + the two new surfaces but still omits the binding).
- [x] `test_audit_state_script_parity_fires_when_reorder_queue_missing` (`:663`–`683`): both stubs carry surfaces 1+3+4; only `bug-state.py` drops `"--reorder-queue"` (surface 2) → `len(findings) == 1` naming `--reorder-queue`. Add `"--reassert-owner"` + the host-capability tokens to BOTH stubs.
- [x] Keep each fires-when-missing fixture isolating EXACTLY ONE missing surface (the other three fully present) so the `len == 1` assertion remains exact and the finding string names the intended surface.
- [x] Docstring cross-reference (SPEC future-proofing note): add a one-line note to the `TestStateScriptParity` class docstring stating these stubs must mirror `audit_state_script_parity`'s `_STATE_SCRIPTS` surface list in lockstep — any future coupled-pair surface added to the audit must update these stubs too.
- [x] Tests: the existing four `TestStateScriptParity` tests ARE the test surface — no NEW test is authored. The edited fixtures are the test data; their assertions already encode the contract (clean → `[]`; each fires-when-missing → `len == 1` on its own surface). The fix is verified by the class turning fully green.

**Implementation Notes (2026-06-20):** Edited the three failing `tmp_path` fixtures + the class docstring in `user/scripts/test_lazy_parity.py`. Added surface-3 (`parser.add_argument("--reassert-owner")`) and surface-4 (`lazy_core.format_unknown_host_capability_blocker(...)  # blocker_kind: unknown-host-capability` — one line carries BOTH required tokens) to every stub that should not drop them: clean fixture → both stubs carry all four (bare vs `lazy_core.`-prefixed binding split preserved); `fires_when_binding_missing` → both carry 2+3+4, `bug-state.py` still omits binding; `fires_when_reorder_queue_missing` → both carry 1+3+4, `bug-state.py` still omits `--reorder-queue`. RED→GREEN: targeted class `3 failed, 1 passed` → `4 passed`; full module `30 passed`; whole `user/scripts/` suite `1034 passed, 0 failed`; real-repo `lazy_parity_audit.py --repo-root .` exit 0 (no production change). No `lazy_parity_audit.py` / state-script source touched.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_parity.py::TestStateScriptParity -q` reports `4 passed, 0 failed` (currently `3 failed, 1 passed`). The real-repo `test_live_state_scripts_bind_active_repo` stays green, AND the full module `python -m pytest user/scripts/test_lazy_parity.py -q` is fully green. `python user/scripts/lazy_parity_audit.py --repo-root .` stays exit 0 (no production change).

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/test_lazy_parity.py` — the three `TestStateScriptParity` fixture stubs + their expectations + the class docstring note. No other file changes.

**Testing Strategy:**
Pure-function audit over fixed fixture text — fully deterministic, no mocks, no runtime, no network. Run the targeted reproduction (`python -m pytest user/scripts/test_lazy_parity.py::TestStateScriptParity -q`) first to confirm the RED (`3 failed, 1 passed`), apply the edits, then re-run to confirm `4 passed`. Each fires-when-missing test must STILL fire on its OWN surface after the edit — adding surfaces 3+4 to the present-stubs must not change which finding the deliberately-dropped surface produces. A regression would manifest as a fires-when-missing test reporting `len != 1` (an over- or under-count); the exact `len == 1` + finding-string-substring assertions catch it. Finish with the whole module green and the real-repo audit still exit 0.

**Integration Notes for Next Phase:**
- None — single-phase fix. When this work lands, the top-level PHASES `**Status:**` flips to `In-progress` (implementation done, validation pending); the state machine routes to the validation tail. The `__mark_fixed__` gate (orchestrator-owned) writes `FIXED.md` and flips SPEC/PHASES to `Fixed` after the tail — never hand-flipped here.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md top-level `**Status:**` to `Fixed` and writes `FIXED.md` once this fix's verification (full-module green) is certified by the validation tail. Not authored as a checkbox row here.
