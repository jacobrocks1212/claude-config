# Implementation Phases — Merged-head actionability oracle

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure state-machine refactor entirely inside the `--emit-prompt` /
`--next-merged` merged-head divergence computation. No MCP-reachable surface (no app behavior, no
stores, no UI, no events); validated by the in-file `--test` smoke harness + `pytest
tests/test_lazy_core/test_dispatch.py`. SPEC `## Locked Decisions` closes "Required MCP tooling:
none". This is the mcp-testing "build-tooling / harness-internal, no app integration" untestable
class.

## Cross-feature Integration Notes

No hard deps on Complete upstreams — the SPEC's `**Depends on:**` block is `(none)` (the merged-head
machinery this refactors is already shipped/archived under `docs/bugs/_archive/merged-head-*`). No
`## Cross-feature Integration Notes` rows are owed.

## Validated Assumptions

Grounded at planning time by the `/spec-phases` touchpoint audit (inline verification against the
live tree, dispatch available but a 5-file Python read is cheaper — read-only, no source edited):

- **All named touchpoints exist with the SPEC's symbols.** `lazy_core/dispatch.py` carries
  `merged_head_override` (line 358), `probe_skipped_ids` (434), `research_halt_head` (531);
  `lazy_core/depdag.py` carries `next_merged` (1477), `nondispatchable_item_ids` (1496).
  `is_dispatchable` / `merged_head_nondispatchable_ids` are net-new (zero grep hits) — code-provable.
- **`nondispatchable_item_ids` has exactly four real call sites, ALL of them merged-head exclude-set
  sites** — `bug-state.py:9715`, `lazy-state.py:12580` (`--next-merged` `_nm_excluded`),
  `lazy-state.py:13935` (`research_halt` `_rh_excluded`), `lazy-state.py:14104` (`--emit-prompt`
  merged-override `_mo_excluded`). No consumer survives outside the merged-head path. This
  **preemptively resolves SPEC Open Question 2** (grep-confirmed at planning time, re-confirmed in
  Phase 3): the helper is DELETED outright in Phase 3, not merely unwired — including its lazy-facade
  entry `lazy_core/__init__.py:492` (`"nondispatchable_item_ids": "depdag"`) and its `test_dispatch.py`
  references. Code-provable (a static grep is authoritative for "who calls this symbol").
- **Site-count asymmetry across the coupled pair is BY DESIGN, not a contradiction of SPEC L6.**
  `lazy-state.py` has three exclude-set sites; `bug-state.py` has ONE (the merged-override site) —
  `--next-merged` and research-halt surfacing are feature-pipeline mechanics (research gating is a
  documented feature/bug divergence). L6's "the three sites must be mirrored" is satisfied by
  mechanical parity (`lazy_parity_audit.py --repo-root .` exit 0), NOT by literal per-script site-count
  symmetry — this is exactly how the current code already works. Anchor-grade nuance, corrected in-plan;
  no premise-grade contradiction, no halt.
- **The oracle's dispatch decision is byte-identical for dispatchable heads BY CONSTRUCTION** — the
  oracle *is* the scoped `compute_state` dispatch decision the withhold already trusts (SPEC Executive
  Summary). This is a code-provable structural identity (same decision, one call site), asserted by the
  Phase 2 byte-identity `--test` fixture + the frozen smoke baselines, not a runtime observation.

**Runtime-coupled load-bearing assumption — deferred to a Phase 1 deliverable, NOT ridden unverified.**
The one assumption source-reading can mislead on is **in-process scoped-`compute_state` isolation**:
`compute_state` resets and mutates module-level accumulators (`_SKIP_AHEAD_BLOCKED`, `_GATED_HEADS`,
`_DIAGNOSTICS`, `_DEP_GATED`, …) as it walks, so running N scoped probes in-process AFTER the primary
emit probe's `state` is captured could corrupt that already-computed `state`. This is not observable by
reading types — it depends on the actual mutation behavior of a repeated in-process call. It is made an
explicit Phase 1 deliverable (the isolation characterization test + the snapshot/restore-or-read-only-
dict decision that resolves SPEC Open Question 1 / L4), never carried silently into a later phase. The
gate is satisfied because this assumption is enumerated and scheduled as the earliest phase's work, with
its verification a deterministic test driving the REAL `compute_state` (not a mock). This feature has NO
user-facing surface, so the reachability axiom does not apply (recorded skip reason: harness-internal
routing computation, no user-reachable surface).

**SPEC-example capability audit:** the SPEC's code examples consume only existing in-repo constructs —
`next_merged`, `probe_skipped_ids`, `merged_head_override`, `research_halt_head`, and the `--feature-id`
/ `--bug-id` scoped `compute_state` (all grep-confirmed present above; the scoped-id flag is documented
in `user/scripts/CLAUDE.md` → "Concurrency plane"). No construct resolves to an explicit rejection path.
Ledger: all constructs `registered? = yes` (`how-confirmed: grep`). No planning-time capability halt.

**MCP tool-existence audit:** no-op — claude-config declares no `.claude/skill-config/mcp-tool-catalog.md`
(no MCP surface), and the SPEC's validation calls zero MCP tools. Recorded skip reason: `no
mcp-tool-catalog.md configured for this repo`.

**Provenance lookup:** the files the phases touch (`lazy_core/dispatch.py`, `lazy_core/depdag.py`,
`lazy-state.py`, `bug-state.py`) are governed by the archived merged-head facet bugs' decision records;
phases are drafted to PRESERVE those facet exclusions (each is a Phase 1 characterization fixture), never
to contradict them — the oracle must keep every facet excluded, by construction.

---

### Phase 1: Oracle core (pure, hermetic)

**Status:** Complete

**Scope:** Introduce the actionability oracle as a pure, dependency-injected function pair in
`lazy_core.dispatch` — no state-script wiring yet. `is_dispatchable(scoped_state)` (the small closed
classifier, L3) plus `merged_head_nondispatchable_ids(...)` (the hybrid exclude-set builder: same-pipeline
`probe_skipped_ids` unchanged + cross-pipeline scoped-probe oracle, bounded at-or-above the emitted item
with first-dispatchable-head short-circuit, L5). Scoped-probe callables are INJECTED so `--test` is
hermetic. Characterize against every currently-enumerated facet fixture AND the previously-uncovered
categories (cloud-deferred / completion-unverified). Resolve the in-process isolation question (L4 / Open
Question 1) with a real-`compute_state` isolation characterization test.

**Deliverables:**
- [x] `is_dispatchable(scoped_state: dict) -> bool` in `lazy_core/dispatch.py` — dispatchable iff
  `sub_skill` is a non-empty, non-`__`-prefixed real skill AND `terminal_reason` is not a
  skip/defer/park/gate/halt reason. Derive the non-dispatch `terminal_reason` set EXHAUSTIVELY from
  `compute_state`'s terminal vocabulary (Open Question 3 — do NOT hand-list a drift-prone enumeration;
  key off the closed terminal-reason surface / sanctioned-stop + halt sets already in `lazy_core`).
- [x] `merged_head_nondispatchable_ids(feature_items, bug_items, repo_root, current_item_id, *,
  same_pipeline, same_pipeline_state, scoped_probe, <run flags>) -> set[str]` in `lazy_core/dispatch.py`,
  building the exclude set as: (1) same-pipeline → `probe_skipped_ids(same_pipeline_state,
  same_pipeline_items)` UNCHANGED (L2 — do NOT replace); (2) cross-pipeline → the INJECTED `scoped_probe`
  callable per candidate, classified non-dispatchable iff `is_dispatchable(scoped_state)` is false, with
  the SAME run flags the emit probe used; (3) `.discard(current_item_id)` (invariant preserved).
- [x] Bound the cross-pipeline oracle to candidates ranked at-or-above the emitted item in the merged
  ordering, short-circuiting at the first dispatchable head (L5) — reuse the canonical `next_merged` /
  `merged_worklist` ordering, never a second ordering rule.
- [x] The research-surface preservation contract (L3 tail): a `needs-research` head WITHOUT
  `--skip-needs-research` classifies non-dispatchable here (it halts) and is excluded — `research_halt_head`
  RE-INCLUDES it in Phase 3 exactly as today (assert the oracle EXCLUDES it here; the re-include is Phase 3).
- [x] `probe_skipped_ids`, `merged_head_override`, `research_halt_head` signatures UNCHANGED (they still
  accept a pre-built `exclude_ids` set) — verified by a no-signature-change assertion in the test.
- [x] Tests: in `tests/test_lazy_core/test_dispatch.py` — the five/six enumerated-facet regressions
  (parked / operator-deferred / device-deferred / dep-unready / research-skipped / research-exclusion)
  each still excluded UNDER THE ORACLE (with a stub `scoped_probe` returning the facet's non-dispatch
  state); NEW coverage for a previously-uncovered category (cloud-deferred / completion-unverified head
  → `is_dispatchable` false → excluded); the `is_dispatchable` closed-predicate table (each terminal
  vocabulary value → expected bool); and the **in-process isolation characterization** (Open Question 1 /
  L4) — a test driving the REAL `compute_state` scoped N times and asserting the primary `state` /
  `_SKIP_AHEAD_BLOCKED` / `_DIAGNOSTICS` are uncorrupted, resolving whether snapshot/restore is needed vs.
  read-only-dict suffices. Record the resolved isolation strategy in this phase's Implementation Notes.

**Minimum Verifiable Behavior:** `python3 -m pytest user/scripts/tests/test_lazy_core/test_dispatch.py -q`
passes with the new oracle unit tests green (facet regressions + new-category + isolation fixture); the
oracle is pure + hermetic (no real subprocess, no real state script) because the scoped probe is injected.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (pure `lazy_core` function pair;
deterministic tests are the whole verification and the implementer runs and ticks them).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core/dispatch.py` — add `is_dispatchable` + `merged_head_nondispatchable_ids`
  (REUSE `probe_skipped_ids` unchanged; do NOT touch `merged_head_override` / `research_halt_head`).
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — oracle unit tests, facet regressions, isolation
  characterization.

**Testing Strategy:** Hermetic — the cross-pipeline `scoped_probe` is an injected callable, so every
facet and new-category case is a table-driven unit test with no subprocess and no real state script. The
isolation test is the one case that drives the REAL `compute_state` (per SPEC's "No cross-probe
corruption" Validation Criteria row + the runtime-coupled gate: it must observe the actual mutation
behavior, not a mock).

**Integration Notes for Next Phase:**
- The oracle takes an INJECTED `scoped_probe` in the pure form; Phase 2 binds it to the REAL cross-pipeline
  scoped `compute_state` (in-process — the resolved L4 strategy from this phase's isolation test; subprocess
  `--bug-id`/`--feature-id` is the documented fallback if in-process proved fragile).
- The exact non-dispatch `terminal_reason` set is DERIVED from `compute_state`'s vocabulary here — Phase 2/3
  callers must not re-hand-list it; consume `is_dispatchable` as the single classifier.
- `probe_skipped_ids` is the same-pipeline source and is UNCHANGED — Phase 2 keeps passing the same-pipeline
  `state` + items to it exactly as today.

---

### Phase 2: Emit-path migration + parity + byte-identity

**Status:** Complete

**Scope:** Rewire the `--emit-prompt` merged-override exclude-set construction on BOTH state scripts
(`lazy-state.py:14104` `_mo_excluded`, `bug-state.py:9715` `_mo_excluded`) to call the oracle
(`merged_head_nondispatchable_ids`) with the REAL cross-pipeline scoped `compute_state` bound to the
injected callable, instead of `nondispatchable_item_ids ∪ probe_skipped_ids`. Prove byte-identity for
dispatchable heads and keep the coupled pair in parity. `--next-merged` and `research_halt` sites stay on
the legacy construction until Phase 3 (incremental migration — the oracle and the legacy helper coexist
this phase).

**Deliverables:**
- [x] `lazy-state.py` `--emit-prompt` merged-override site (`_mo_excluded`, ~14104): replace the
  `nondispatchable_item_ids(...) | probe_skipped_ids(state, _mo_feats)` construction with
  `merged_head_nondispatchable_ids(...)` — same-pipeline = features (`probe_skipped_ids(state, _mo_feats)`
  preserved inside the oracle), cross-pipeline = bugs via the real bug-scoped `compute_state` (`--bug-id`
  in-process, the `--next-merged` importlib precedent). The `.discard(current)` invariant and the existing
  observability `_diag` line (skipped gated/deferred head) are preserved.
- [x] `bug-state.py` `--emit-prompt` merged-override site (`_mo_excluded`, ~9715): the coupled-pair mirror —
  same-pipeline = bugs (`probe_skipped_ids(state, _mo_bugs)`), cross-pipeline = features via the real
  feature-scoped `compute_state` (`--feature-id` in-process). Mirror the divergences the current code
  already carries (the feature-side `--skip-needs-research` asymmetry stays a documented divergence).
- [x] The in-process scoped probe honors the SAME run flags the emit probe used (park facets,
  `skip_needs_research`, `cloud`, `real_device`, `strict_research_halt`) per L2/Technical Design, and does
  NOT corrupt the primary probe's already-captured `state` (the Phase 1 isolation strategy applied at the
  real call site).
- [x] Tests: byte-identity for dispatchable heads (a P0 bug jumping the queue mid-feature-run → the
  `merged-head-diverged` withhold fires IDENTICALLY to pre-oracle) as a `test_dispatch.py` fixture; the
  cross-probe isolation fixture at the REAL emit call site (primary `state` unchanged after N scoped
  probes); both scripts' in-file `--test` suites green; the frozen smoke baselines re-pinned only if the
  legitimate additive diagnostics changed (regenerate ONLY via `_normalize_smoke_output`, never by hand).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test && python3 user/scripts/bug-state.py --test`
both green, AND `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0, AND
`python3 -m pytest user/scripts/tests/test_lazy_core/test_dispatch.py -q` green (byte-identity +
real-call-site isolation fixtures).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (state-machine routing;
deterministic `--test` + pytest + parity audit are the whole verification).

**Prerequisites:**
- Phase 1: `is_dispatchable` + `merged_head_nondispatchable_ids` exist in `lazy_core.dispatch` with the
  injected-`scoped_probe` seam and the resolved in-process isolation strategy.

**Files likely modified:**
- `user/scripts/lazy-state.py` — the `_mo_excluded` construction at the `--emit-prompt` merged-override site.
- `user/scripts/bug-state.py` — the `_mo_excluded` construction at its merged-override site (coupled mirror).
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — byte-identity + real-call-site isolation fixtures.
- (regenerate-only) `tests/baselines/lazy-state-test-baseline.txt` / `bug-state-test-baseline.txt` — ONLY
  if additive diagnostics legitimately change the smoke output; via `_normalize_smoke_output`.

**Testing Strategy:** The byte-identity fixture is the load-bearing regression net (the oracle IS the
dispatch decision the withhold already trusts, so a dispatchable head MUST route identically). The parity
audit is the coupled-pair gate. The smoke baselines guard against any unintended emit-path behavior change.

**Integration Notes for Next Phase:**
- After this phase two of the three feature-side exclude-set sites (`--next-merged`, `research_halt`) still
  call `nondispatchable_item_ids` — Phase 3 migrates them and only THEN can the helper be retired.
- `research_halt_head` still RE-INCLUDES research-gated ids from the caller's FULL exclude set; Phase 3's
  `_rh_excluded` must build that FULL set from the oracle so the re-include (byte-identity invariant, L3
  tail) is preserved.

---

### Phase 3: Remaining-site migration + helper retirement + baseline re-pin

**Scope:** Migrate the two remaining feature-side exclude-set sites (`--next-merged` `_nm_excluded`:12580,
`research_halt` `_rh_excluded`:13935) to the oracle, then RETIRE `nondispatchable_item_ids` from the
merged-head path. Because the planning-time grep confirmed zero non-merged consumers survive (re-confirm
here), the helper is DELETED outright — its definition (`depdag.py:1496`), its lazy-facade map entry
(`__init__.py:492`), and its `test_dispatch.py` references — with a `retires:` declaration for the
anti-overfit complexity check (L7). Re-pin the full smoke baselines.

**Deliverables:**
- [ ] `lazy-state.py` `--next-merged` site (`_nm_excluded`, ~12580): build the exclude set via
  `merged_head_nondispatchable_ids` (same-pipeline features via `probe_skipped_ids` + cross-pipeline bugs
  via the scoped oracle), replacing `nondispatchable_item_ids`. `next_merged` / `merged_head_override`
  signatures unchanged (still take a pre-built `exclude_ids`).
- [ ] `lazy-state.py` `research_halt` site (`_rh_excluded`, ~13935): build the FULL merged-head exclude set
  via the oracle, then pass it to `research_halt_head` — which RE-INCLUDES the research-gated ids exactly
  as today (assert the needs-research halt still surfaces; byte-identity invariant, L3 tail). Preserve the
  existing `.discard(current)`.
- [ ] Re-confirm (grep) that `nondispatchable_item_ids` now has ZERO callers, then DELETE it: the definition
  in `lazy_core/depdag.py` (~1496), the `"nondispatchable_item_ids": "depdag"` entry in
  `lazy_core/__init__.py` (~492), and every `test_dispatch.py` reference. Add a `retires:` declaration
  (per L7 / the anti-overfit complexity check) naming the retired helper.
- [ ] Update the in-code cross-references that name `nondispatchable_item_ids` in prose/docstrings
  (`depdag.py:1440`, `dispatch.py:557`, `docmodel.py:2313`/`2340`) so no dangling reference to a deleted
  symbol survives — repoint them at the oracle.
- [ ] Tests: `--next-merged` and `research_halt` migration fixtures (exclude-set built via the oracle;
  research-halt surfacing byte-identical); a "helper gone" assertion (importing `nondispatchable_item_ids`
  from `lazy_core` fails / is absent from the facade map); full smoke baseline re-pin; final
  `lazy_parity_audit.py --repo-root .` exit 0.
- [ ] Doc-drift + facade integrity: `python3 user/scripts/doc-drift-lint.py --repo-root .` clean (the
  retired symbol must not linger in any doc/script table), and `lint-skills.py` unaffected.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test && python3 user/scripts/bug-state.py --test`
green, `python3 user/scripts/lazy_parity_audit.py --repo-root .` exit 0,
`python3 -m pytest user/scripts/tests/test_lazy_core/ -q` green (incl. the helper-gone assertion), and a
repo-wide grep for `nondispatchable_item_ids` returns only the archived-bug prose references (zero live code
callers, zero facade map entry).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior (state-machine routing; the
deterministic test + parity + doc-drift suite is the whole verification).

**Prerequisites:**
- Phase 2: the `--emit-prompt` merged-override site on both scripts already calls the oracle (so this phase
  migrates the LAST two sites and the helper drops to zero callers).

**Files likely modified:**
- `user/scripts/lazy-state.py` — `_nm_excluded` (`--next-merged`) + `_rh_excluded` (`research_halt`) sites.
- `user/scripts/lazy_core/depdag.py` — DELETE `nondispatchable_item_ids`; fix the prose cross-reference.
- `user/scripts/lazy_core/__init__.py` — remove the facade name→submodule map entry.
- `user/scripts/lazy_core/dispatch.py` / `docmodel.py` — repoint the retired-symbol prose references.
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — migration fixtures + helper-gone assertion; remove
  the now-dead `nondispatchable_item_ids` tests.
- (regenerate-only) `tests/baselines/lazy-state-test-baseline.txt` / `bug-state-test-baseline.txt` — full
  re-pin via `_normalize_smoke_output`.

**Testing Strategy:** The research-halt byte-identity fixture guards the L3-tail re-include invariant (a
needs-research head must still surface). The helper-gone assertion + doc-drift lint guarantee the retirement
is complete (no dangling symbol). The full smoke re-pin is the final state-machine regression net.

**Integration Notes for Next Phase:** None — final phase. After Phase 3 all three exclude-set sites route
through the single actionability oracle, `nondispatchable_item_ids` no longer exists, and the recurring
`merged-head-diverged-withholds-on-<X>` class is closed by construction (SPEC Success Measurement target: 0
recurrences).

## Implementation Notes

- **`retires:` declaration (L7 / anti-overfit complexity check).** Phase 3's deletion of
  `nondispatchable_item_ids` MUST carry a `retires:` declaration — this is a control-surface change
  (`lazy_core`, state scripts) that `harness-gate.py` will inspect; the complexity detector requires the
  `retires:` note, and the design gate's adversarial half records judgment in `GATE_VERDICT.md` at the
  completion-gate ship seam. Not a phase-authoring blocker; a completion-time obligation surfaced here.
- **Coupled-pair discipline (L6).** The merged marker is shared across `lazy-state.py` / `bug-state.py`.
  Every edit to a merged-head exclude-set construction runs `lazy_parity_audit.py --repo-root .` before
  the phase's commit. Site-count asymmetry (feature=3, bug=1) is by design (see Validated Assumptions) —
  parity is mechanical, not literal.
- **SPEC "five facets" vs. code's six.** The SPEC narrates five facets; the live code has evolved a sixth
  (`merged-head-research-exclusion-flag-gated-splits-cross-script`). Phase 1's facet regressions cover ALL
  currently-enumerated facets present in the code (whatever the count) — the oracle must keep every one
  excluded by construction. Not a contradiction — the SPEC's premise ("the enumeration is inherently
  incomplete and the oracle subsumes it") is strengthened, not falsified, by the extra facet.
- **Open Questions resolved at planning time:** OQ2 (helper full retirement) — grep-confirmed zero
  non-merged consumers → DELETE outright in Phase 3. OQ1/L4 (in-process vs subprocess) — deferred to the
  Phase 1 isolation characterization test (in-process preferred, subprocess documented fallback). OQ3
  (`is_dispatchable` terminal set) — derived exhaustively from `compute_state`'s vocabulary in Phase 1,
  never hand-listed.
- **Phase 1 resolved isolation strategy (OQ1 / L4).** The in-process isolation characterization test
  (`test_merged_head_nondispatchable_ids_in_process_isolation_characterization`) drives the REAL
  `compute_state` scoped N times and confirms: **reading only the returned dict SUFFICES — no
  snapshot/restore of module globals is required.** `compute_state` resets its module accumulators
  (`_GATED_HEADS` / `_SKIP_AHEAD_BLOCKED` / `_DEP_GATED` / `_DEVICE_DEFERRED` / `_HOST_DEFERRED`) at
  entry, and `_state()` returns a FRESH dict with `list()`-copied accumulator snapshots + `lazy_core._DIAGNOSTICS`
  is reset per invocation — so a subsequent scoped probe cannot corrupt the primary emit probe's
  already-captured `state`. Phase 2 therefore binds `scoped_probe` to a plain in-process cross-pipeline
  `compute_state` call and reads its returned dict (no defensive globals snapshot). The subprocess
  `--bug-id`/`--feature-id` fallback is NOT needed.
- **Phase 2 real-call-site isolation refinement.** The Phase-1 conclusion ("reading the returned dict
  suffices") holds for the primary `state` DICT, but the real cross-pipeline scoped probe runs the OTHER
  script's `compute_state`, which calls `clear_diagnostics()` on the SHARED `lazy_core._DIAGNOSTICS` list
  (both scripts import the same `lazy_core`). So each `_mo` site SNAPSHOTS `list(lazy_core._DIAGNOSTICS)`
  before the oracle call and RESTORES it in a `finally` — the cross-probe has ZERO observable diagnostics
  side effect on the emit path. The bug-state module is loaded once via a cached `_load_bug_state_module()`
  / `_load_feature_state_module()` (the `_load_*_queue_for_merged` importlib precedent). A candidate the
  probe cannot classify (module unloadable / probe exception) returns `{}` → non-dispatchable → fail toward
  EMITTING the workable item (never a spurious withhold). SEAM-DESIGN halts (blocked/needs-input/needs-research)
  ARE excluded per SPEC ("...gated / halted rather than actually worked") — surfaced by the item's own
  pipeline / notify / end-of-run flush, not by hijacking the cross-pipeline cycle.
- **Baselines unchanged (Phase 2).** Both `lazy-state.py --test` and `bug-state.py --test` stay green against
  the committed frozen baselines — the `_mo` rewrite changed no `--test`-observable smoke output (the emit
  subprocess fixtures live in the pytest seam suite, not the in-file smoke harness), so NO baseline re-pin was
  needed this phase.
- **Phase 1 oracle signature (mechanical-internal choice).** The Phase-1 pure form takes the
  `scoped_probe` callable INJECTED (the hermetic seam) rather than raw run-flag kwargs — the SPEC
  "Target shape" `<run flags>` placeholder is realized as the closure the caller (Phase 2) binds with
  those flags, so the oracle itself carries no dead run-flag parameters (constitution: no test-only
  seams). `today=` is accepted for bug-aging ordering determinism, mirroring `merged_head_override`.
- **Spin-offs:** none this cycle.
