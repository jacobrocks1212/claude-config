# Implementation Phases — Step-10 → mcp-test re-route on uncovered verification rows

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is the harness repo; it has NO Tauri/dev-runtime/MCP surface. This is a pure Python state-machine + marker/PHASES-parsing change. Validation is the in-file `--test` smoke harness (`lazy-state.py --test` / `bug-state.py --test`, byte-pinned baselines) + the `pytest` `tests/test_lazy_core/` seam suites — the mcp-testing SPEC's "structurally outside MCP reach (build/harness tooling)" class.

## Touchpoint Audit (verified inline — dispatch available; contained 3-file change)

`verified: inline (tree-sitter/Read/Grep, not from memory)`

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core/docmodel.py` | yes | `_VERIFICATION_ONLY_MARKER` (:1069), `_DESCOPED_MARKER` (:1163), `remaining_unchecked_are_verification_only` (:1183) | add | Add a per-row host-defer recognizer next to `_DESCOPED_MARKER`, mirroring the marker pattern EXACTLY — a module constant + a pure `row_requires_host(row_text)->str\|None`. Do NOT re-implement PHASES parsing; reuse the same row/fence/header conventions. |
| `user/scripts/lazy_core/gates.py` | yes | `observation_gap_promotable` (:608), `autotick_verification_rows` (:781), `evaluate_completion_evidence`, `_UNCHECKED_ROW_RE` (:774) | add | Add ONE pure predicate helper composing `remaining_unchecked_are_verification_only`'s row-walk logic + `observation_gap_promotable` (clause a) + the Phase-1 `row_requires_host` (clause b) + `autotick`-cardinality/evidence reasoning (clause c). Reuse `_UNCHECKED_ROW_RE` + `_VERIFICATION_ONLY_MARKER` — do NOT hand-roll a new checkbox regex. |
| `user/scripts/lazy_core/__init__.py` | yes | explicit name→submodule map (`remaining_unchecked_are_verification_only`:101, `autotick_verification_rows`:193, `observation_gap_promotable`:200) | refactor | Add the new `docmodel` + `gates` public helper names to the facade map so `lazy_core.<name>` resolves. |
| `user/scripts/lazy-state.py` | yes | Step-10 entry gate (:4034 `entry_ok`), `__mark_complete__` dispatch (:4087–4092); top-of-file `from lazy_core import (...)` block (:109–121) | refactor | Insert the re-route branch immediately BEFORE the :4087 `return _state(... sub_skill="__mark_complete__" ...)`. Add the new helper name(s) to the top import block. |
| `user/scripts/bug-state.py` | yes | Step-10 mark-fixed (:2112), `__mark_fixed__` dispatch (:2148–2153) — IDENTICAL unconditional-dispatch shape after the same cloud/provisional guards | refactor | **Coupled-pair mirror** (parity, NOT a divergence): insert the SAME re-route branch before :2148, routing `sub_skill="mcp-test"`. |
| `user/scripts/tests/test_lazy_core/test_docmodel.py` | yes | pytest seam suite | add | Unit tests for `row_requires_host`. |
| `user/scripts/tests/test_lazy_core/test_gates.py` | yes | pytest seam suite | add | Unit tests for the new predicate (all coverage/exempt/host-defer branches + termination). |
| `user/scripts/lazy-state.py` (`--test`) + `user/scripts/bug-state.py` (`--test`) | yes | in-file smoke harnesses | add | State-machine fixtures: uncovered subset ⇒ re-route to mcp-test; all-covered/host-deferred/exempt ⇒ falls through to terminal (TERMINATION); host-deferred/observation-gap rows never re-trigger. |

**Contradictions:** none. The SPEC's serving-path trace (`lazy-state.py:4034→4087`) matches reality; both state scripts confirmed to share the identical dispatch shape (anchor-grade audit only — no premise-grade findings).

## Root Cause (from SPEC — traced)

`lazy-state.py:4087` (and its `bug-state.py:2148` twin) dispatches the terminal pseudo-skill unconditionally once `VALIDATED.md` is present at Step 10, with no coverage-completeness check. A matrix-incomplete `VALIDATED.md` (a legitimate partial-results run) forces the completion route, which the coherence gate refuses on the unchecked verification rows → oscillation (symptom 1) / stranded coverage (symptom 2). The fix is a MISSING re-route branch, composed from existing predicate ingredients + one minimal new per-row host-defer recognizer.

---

### Phase 1: Per-row host-defer recognizer (`<!-- requires-host: <cap> -->`)

**Status:** Complete

**Scope:** Land the minimal per-row host-defer marker recognizer that clause (b) of the re-route predicate depends on (per SPEC **Locked Decision 1** — landed as a phase of THIS bug, NOT a queue `deps` on the decision-5 sibling). A pure string recognizer mirroring `_VERIFICATION_ONLY_MARKER` / `_DESCOPED_MARKER`: given a PHASES.md row's text, return the declared host-capability id (or `None`). This is the ONLY new primitive; everything downstream composes existing helpers.

**Deliverables:**
- [x] `_REQUIRES_HOST_ROW_RE` (or an equivalent module constant) in `docmodel.py`, placed beside `_DESCOPED_MARKER` (~:1163), matching `<!-- requires-host: <cap> -->` where `<cap>` matches the existing closed-registry id shape `^[a-z0-9][a-z0-9-]*$` (consistent with `lazy_core.parse_requires_host` capability ids).
- [x] `row_requires_host(row_text: str) -> str | None` — pure, returns the capability id when the row (or, mirroring the marker convention, its enclosing subsection header) carries the marker; `None` otherwise. Header-scope handling mirrors `remaining_unchecked_are_verification_only`.
- [x] Facade export: add `_REQUIRES_HOST_ROW_RE`/`row_requires_host` to the `__init__.py` name→submodule map (`docmodel`).
- [x] Tests: `test_docmodel.py` — a bare row (no marker) ⇒ `None`; a row carrying `<!-- requires-host: real-audio-device -->` ⇒ `"real-audio-device"`; an invalid id ⇒ `None`; a row inside a ``` fence ⇒ `None` (illustrative, per the existing fence convention).

**Implementation Notes (2026-07-19):** Landed `_REQUIRES_HOST_ROW_RE` (capturing `<!--\s*requires-host\s*:\s*([^>]*?)\s*-->`, case-insensitive) + `_REQUIRES_HOST_CAP_ID_RE` (mirrors `hostcaps._HOST_CAPABILITY_ID_RE` shape, kept local with a keep-in-sync comment to preserve docmodel's light import surface — the `_PHASE_HEADING_RE`-copy precedent) + pure `row_requires_host` in `docmodel.py`, facade-exported. The function is position-agnostic (works on row OR header text) — the caller's walk (WU-2) owns fence/phase context; the "fenced illustrative marker ⇒ excluded" behavior is therefore asserted in WU-2's `test_gates.py` walk, while `test_docmodel.py` pins the pure recognizer (bare/valid/invalid/header-line/context-free). 5 unit tests, all green.

**Minimum Verifiable Behavior:** `python3 -c "import sys; sys.path.insert(0, 'user/scripts'); import lazy_core; print(lazy_core.row_requires_host('- [ ] <!-- verification-only --> <!-- requires-host: real-audio-device --> foo'))"` prints `real-audio-device`; the same call on an unmarked row prints `None`.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (pure string parser; validated by pytest).

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core/docmodel.py` — new constant + `row_requires_host`.
- `user/scripts/lazy_core/__init__.py` — facade map entries.
- `user/scripts/tests/test_lazy_core/test_docmodel.py` — unit tests.

**Testing Strategy:** Pure unit tests (`pytest user/scripts/tests/test_lazy_core/test_docmodel.py`). No state machine involved.

**Integration Notes for Next Phase:**
- The recognizer is the "non-host-deferred" clause (b) input for Phase 2. A row for which `row_requires_host(...) is not None` is EXCLUDED from the re-route predicate (a host-deferred row is a valid termination state, never an uncovered row).
- The marker is a ROW ANNOTATION, not a sentinel — do NOT add it to `check-docs-consistency.ts` `SENTINEL_SCHEMAS` (same posture as `_VERIFICATION_ONLY_MARKER` / `_DESCOPED_MARKER`).

---

### Phase 2: Shared uncovered-verification-row predicate (pure helper)

**Status:** Complete

**Scope:** Add ONE pure `lazy_core` helper — the SHARED predicate both state scripts call (SPEC: "ONE predicate serving both symptoms"). Given the feature/bug dir + PHASES.md text + repo root, it answers: *does a non-Superseded phase have an unchecked runtime-verification row that is (a) NOT observation-gap-exempt, (b) NOT host-deferred, and (c) not covered by recorded evidence?* Returns a small structured result (`{reroute: bool, uncovered: [...], reason: ...}`) so the routing `_diag` can name why. Pure/side-effect-free (no PHASES.md mutation — it REASONS about what `autotick_verification_rows` would tick; it does not tick).

**Deliverables:**
- [x] `uncovered_verification_rows_remain(feature_dir, phases_text, repo_root) -> dict` in `gates.py`, composing:
  - the row-walk of `remaining_unchecked_are_verification_only` (unchecked `- [ ]` rows carrying `_VERIFICATION_ONLY_MARKER`, fence-aware, Superseded/descoped-aware) to enumerate candidate rows — reuse `_UNCHECKED_ROW_RE` + `_VERIFICATION_ONLY_MARKER`, do NOT re-implement;
  - clause (a): exclude rows when the recorded `MCP_TEST_RESULTS.md` meta is a sanctioned observation-gap partial (`observation_gap_promotable(meta)` True);
  - clause (b): exclude a row for which `row_requires_host(row) is not None` (Phase 1);
  - clause (c): a row is "covered" iff the recorded evidence would tick it — i.e. `evaluate_completion_evidence` authorizes (`exempt-and-tick`/`warn-exempt`) AND the autotick cardinality is sufficient (`pass_count >=` the count of covered candidate rows). A subset/partial `VALIDATED.md` (pass_count < candidate rows) leaves the excess rows UNCOVERED ⇒ `reroute: True`.
- [x] The helper is CONSERVATIVE per the operator-locked fix shape: "still uncovered after evidence reasoning" ⇒ re-route; one redundant mcp-test pass on a genuinely-complete-but-unticked matrix is tolerable.
- [x] Facade export in `__init__.py` (`gates`).
- [x] Tests: `test_gates.py` — (1) partial VALIDATED over ≥2 verification rows, evidence covers only 1 ⇒ `reroute: True`, `uncovered` lists the excess; (2) all rows covered by evidence ⇒ `reroute: False` (TERMINATION); (3) uncovered row but `row_requires_host` set ⇒ excluded ⇒ `reroute: False`; (4) `result: partial` with valid `observation_gap_exemptions` ⇒ excluded ⇒ `reroute: False`; (5) all rows Superseded/descoped ⇒ `reroute: False`; (6) no VALIDATED.md is a caller precondition, not this helper's concern (document it).

**Implementation Notes (2026-07-19):** Landed `uncovered_verification_rows_remain` + the shared `_collect_uncovered_verification_rows` row-walk in `gates.py`, facade-exported. Clause (c) mirrors `autotick_verification_rows`' all-or-nothing cardinality lock exactly: rows are covered iff `len(rows) <= pass_count` (autotick ticks all) else the abort leaves them uncovered — `pass_count` read from `evaluate_completion_evidence` (refuse verdict → 0). Clause (a) routes through `observation_gap_promotable` (whole-file exempt). Clause (b) excludes host-deferred rows from `reroutable`; when ONLY host-deferred rows remain uncovered the predicate returns `reroute: False` (termination — decision-5 owns their completion exemption). 6 unit tests cover all branches + the caller-precondition doc; all green.

**Minimum Verifiable Behavior:** `pytest user/scripts/tests/test_lazy_core/test_gates.py` — the six branches above pass, proving the predicate both fires on a genuine subset AND terminates on covered/host-deferred/exempt matrices.

**MCP Integration Test Assertions:** N/A — pure predicate; validated by pytest.

**Prerequisites:**
- Phase 1: `row_requires_host` (clause b).

**Files likely modified:**
- `user/scripts/lazy_core/gates.py` — new predicate helper.
- `user/scripts/lazy_core/__init__.py` — facade map entry.
- `user/scripts/tests/test_lazy_core/test_gates.py` — unit tests.

**Integration Notes for Next Phase:**
- TERMINATION is the load-bearing contract: the predicate MUST return `reroute: False` once every uncovered row is covered/ticked, host-deferred-marked, or exempt — Phase 3's fixtures assert the re-route fires ONCE then falls through.
- The helper is PURE (reasons about autotick, never mutates PHASES.md) — safe to call on the read-only `compute_state` probe path (HARD CONSTRAINT: a probe never writes).
- Scope edge (record in the SPEC's Implementation Notes): a host-deferred row is EXCLUDED from the re-route so the loop terminates; the completion gate's own handling of host-deferred rows is governed by the existing host-capability axis (`DEFERRED_REQUIRES_HOST.md`) machinery and is NOT re-litigated here (matches the SPEC's re-route-only fix scope + the Coverage-precision-dial Open Question deferral).

---

### Phase 3: Wire the re-route into both state scripts (coupled pair) + regression fixtures

**Scope:** Insert the re-route branch immediately before the terminal-pseudo-skill dispatch in BOTH state scripts — `lazy-state.py` before :4087 (`__mark_complete__`) and `bug-state.py` before :2148 (`__mark_fixed__`) — routing `sub_skill="mcp-test"` when `uncovered_verification_rows_remain(...).reroute` is True. This resolves the SPEC's `bug-state.py`-coupling Open Question as a MIRROR (both scripts share the identical unconditional-dispatch shape and reach the same VALIDATED gate — a coupled-pair edit, parity-audited, not a divergence). Add the `--test` fixtures that pin the re-route AND its termination.

**Deliverables:**
- [ ] `lazy-state.py`: between the provisional-sentinel guard (~:4083) and the `__mark_complete__` dispatch (:4087), a re-route branch calling the Phase-2 predicate; on `reroute: True` return `_state(..., current_step="Step 10: re-route to mcp-test (uncovered verification rows)", sub_skill="mcp-test", sub_skill_args=...)` with a `lazy_core._diag(...)` naming the uncovered row(s). Add the predicate name to the top-of-file `from lazy_core import (...)` block (:109–121).
- [ ] `bug-state.py`: the byte-mirrored branch before :2148 (`__mark_fixed__`), same predicate, same `mcp-test` route, mirrored `_diag`.
- [ ] `lazy-state.py --test` fixtures: (a) matrix-incomplete VALIDATED.md + uncovered verification row ⇒ probe returns `sub_skill="mcp-test"` (NOT `__mark_complete__`); (b) all rows covered/host-deferred/exempt ⇒ probe returns `sub_skill="__mark_complete__"` (TERMINATION — the re-route does NOT fire); (c) a host-deferred / observation-gap row never re-triggers the route.
- [ ] `bug-state.py --test` mirrored fixtures (`__mark_fixed__` in place of `__mark_complete__`).
- [ ] Register each new `def test_<name>()` in its script's `--test` list block.
- [ ] Regenerate the byte-pinned `--test` baselines ONLY via the sanctioned `_normalize_smoke_output` pipe (never by hand) if the new fixtures change baseline output.

**Runtime Verification** *(checked by the mcp-test cycle / manual verification — NOT the implementer):*
- [ ] <!-- verification-only --> The full `--test` harness is GREEN on both scripts (`python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test`), and `pytest user/scripts/tests/test_lazy_core/` passes.
- [ ] <!-- verification-only --> The parity audit is exit 0: `python3 user/scripts/lazy_parity_audit.py --repo-root .` (the coupled-pair mirror is registered/clean).

**MCP Integration Test Assertions:** N/A — the state machine is validated by the hermetic in-file `--test` harness + pytest, not an MCP runtime (claude-config has none).

**Prerequisites:**
- Phase 2: `uncovered_verification_rows_remain` (the shared predicate).

**Files likely modified:**
- `user/scripts/lazy-state.py` — re-route branch + import + `--test` fixtures.
- `user/scripts/bug-state.py` — mirrored re-route branch + `--test` fixtures.
- `tests/baselines/lazy-state-test-baseline.txt` / `tests/baselines/bug-state-test-baseline.txt` — regenerated via `_normalize_smoke_output` IF output changed.

**Testing Strategy:** In-file `--test` smoke fixtures (hermetic temp-dir feature/bug dirs) assert the computed `sub_skill` for the re-route and the termination case. Parity audit confirms the coupled-pair mirror. `pytest tests/test_lazy_core/` characterizes the shared helpers.

**Integration Notes for Next Phase:** (final phase)
- **Completion (gate-owned):** the `__mark_complete__` / `__mark_fixed__` gate owns the terminal `**Status:**` flip + receipt; this bug's implementation NEVER flips top-level status or writes `FIXED.md`. When Phase 3's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to `/mcp-test`.
- **Coupling record:** the `bug-state.py`-coupling Open Question is resolved to MIRROR (parity). Record in the SPEC's Implementation Notes that `lazy_parity_audit.py` must stay exit 0.

## Cross-feature Integration Notes

No hard deps on Complete upstreams (`**Depends on:**` is not declared in the SPEC; the decision-5 sibling bug is referenced but, per Locked Decision 1, is NOT a queue `deps` — its minimal recognizer is landed here as Phase 1).
