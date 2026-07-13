# Implementation Phases — Production sentinel writes bypass _atomic_write, violating the repo's own contract

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure script-hygiene fix inside `user/scripts/`; claude-config has
no Tauri/MCP app surface. Verification is the repo's own deterministic gates: `pytest
user/scripts/test_lazy_core.py` (including two new mechanical lint-gate meta-tests + their
negative-fixture non-vacuity proofs) plus the existing `--test` smoke harnesses on both state
scripts, which already exercise every touched writer hundreds of times via their fixture builders.

## Validated Assumptions

- **`lazy_core.py` already complied** (SPEC D1) — confirmed via grep: zero `.write_text(` calls
  anywhere in `lazy_core.py`, before or after this fix.
- **Every named writer builds its full content string BEFORE writing** — the SPEC's claimed
  "mechanical substitution, no behavior change" verified true for all seven inventory rows;
  `path.write_text(text, encoding="utf-8")` → `lazy_core._atomic_write(path, text)` is a byte-for-
  byte-output-preserving swap (`_atomic_write` always writes UTF-8, matching every existing call
  site's explicit `encoding="utf-8"`).
- **bug-state.py's per-call PyYAML `except ImportError` fallback in the two sentinel writers was
  DEAD CODE** (SPEC D3, confirmed): `bug-state.py`'s own `import lazy_core` (module-level) already
  hard-exits the process at import time when PyYAML is absent (`lazy_core.py`'s own
  `try: import yaml / except ImportError: sys.exit(2)`) — the fallback branch inside
  `_write_yaml_sentinel`/`_write_yaml_blocked_sentinel` could never execute in any real invocation,
  confirmed by grep showing `bug-state.py` had no OTHER top-level `import yaml` at all before this
  fix (every `yaml.` use lived inside these two local `try` blocks).
- **The bonus finding (`_current_head` duplicate) is a true F811 shadow, not a red herring** —
  confirmed identical bodies at two module-level `def _current_head(repo_root)` sites in
  `lazy_core.py`; the second silently shadowed the first at module load with zero import-time
  signal (this repo has no `.github/workflows/` and no ruff/pyflakes/flake8 config anywhere).

## Cross-feature Integration Notes

- No file overlap with the sibling bugs `mark-complete-partial-apply-noop-unrecoverable` /
  `coord-lock-no-stale-reclaim` (same crash-consistency THEME — script-owned state atomicity —
  different code paths; those own `apply_pseudo`'s completion sequence and `lazy_coord.py`'s
  lock-reclaim respectively, neither touched here).
- `docs/features/host-capability-declaration-for-gated-features/` (Complete) introduced the two
  `_write_yaml_blocked_sentinel` production call sites this bug fixes (the unknown-host-capability
  fail-fasts) — this fix changes only the WRITE MECHANISM inside the shared helper, not any caller
  or the BLOCKED.md content/schema those call sites produce.
- `docs/features/doc-drift-linter/` — precedent cited by the SPEC for "a mechanical prose-to-code
  enforcement gate in this repo"; this bug's two new lint-gate meta-tests follow the SAME
  established idiom already used elsewhere in `test_lazy_core.py`
  (`_collect_orphaned_test_names`/`test_no_orphaned_test_functions`,
  `_collect_telemetry_event_literals`/`test_intervention_event_vocabulary_matches_live_emit_set`,
  `_collect_production_binding_smells`/`test_ensure_runtime_production_tests_derive_not_inject_signal`)
  rather than a bespoke new mechanism — pure AST collector + self-checking meta-test + a
  negative-fixture non-vacuity proof.

---

### Phase 1: Route every production write through `_atomic_write` + reconcile the PyYAML-fallback asymmetry + resolve the `_current_head` duplicate

**Scope:** the seven rows in the SPEC's inventory table across both state scripts
(`_write_yaml_sentinel` / `_write_yaml_blocked_sentinel` in `lazy-state.py` + `bug-state.py`,
`_write_step10_needs_input`, the ad-hoc ROADMAP append, the ad-hoc brief/spec writes inside
`enqueue_adhoc` / `enqueue_adhoc_bug` / `materialize_wi`), the two sentinel writers'
misclassified section placement (re-banner, SPEC Fix Scope item 1's "move or re-banner" option),
the PyYAML-fallback reconciliation (Fix Scope item 4, D3 — hard-exit posture on both scripts), and
the bonus-finding `_current_head` duplicate (Fix Scope item 3's duplicate-def half).

**TDD:** yes — the Phase 2 mechanical lint-gate collector was authored against THIS phase's
already-fixed tree as its GREEN self-check; its RED-for-the-right-reason is proven by feeding the
collector a synthetic negative fixture shaped exactly like the pre-fix violation (a bare
`path.write_text(...)` call before a file's fixture-region marker) rather than by re-running it
against a saved pre-fix snapshot — the inventory table itself (SPEC, cited line numbers) is the
proof the violations were real and are now gone (verified by grep, see Minimum Verifiable
Behavior).

**Status:** Complete

**Deliverables:**
- [x] `lazy-state.py`: `_write_step10_needs_input`'s `NEEDS_INPUT.md` write, `enqueue_adhoc`'s
      brief + ROADMAP writes (both the append and the fresh-file branch), `enqueue_adhoc_bug`'s
      brief write, `materialize_wi`'s feature-route brief (both the fresh-write and
      augmented-append branches) + bug-route brief + the shared stub `SPEC.md` write — ALL routed
      through `_atomic_write`.
- [x] `lazy-state.py`: `_write_yaml_sentinel` / `_write_yaml_blocked_sentinel` bodies routed
      through `_atomic_write`; re-bannered ABOVE a relocated "# Fixture smoke tests" banner (moved
      to sit immediately before `_build_fixture`, the true start of the fixture-only region) so the
      file's own layout now matches reality — these are production helpers, one of them
      (`_write_yaml_blocked_sentinel`) called from Step-3 `compute_state` fail-fasts ~1700 lines
      earlier.
- [x] `bug-state.py`: `_write_yaml_sentinel` / `_write_yaml_blocked_sentinel` mirrored identically
      — bodies routed through `_atomic_write`, re-bannered above a relocated
      "SMOKE FIXTURES + --test" banner (now sitting immediately before `_build_bug_fixture`).
- [x] `bug-state.py`: the per-call PyYAML `except ImportError` fallback in both writers DELETED
      (dead code, D3) — an explicit top-level `try: import yaml / except ImportError: sys.exit(2)`
      block added near the top of `bug-state.py` (mirroring `lazy-state.py`'s own posture: one
      PyYAML posture across both scripts, not two). The "byte-for-byte mirror of the
      lazy-state.py helper" docstring claim in `_write_yaml_blocked_sentinel` is now literally true
      (both bodies: build `fm`, `yaml.safe_dump`, `_atomic_write` — no divergence).
- [x] `lazy_core.py` bonus finding: the duplicate `_current_head` definition (identical bodies at
      two module-level locations — an undetected F811 shadow) resolved. Kept the later,
      more-documented WU-4-section definition; the earlier one replaced with an explanatory
      comment pointing at the survivor (no caller update needed — same module, same name, callers
      were already unambiguous at runtime; only the SOURCE duplication is removed).

**Implementation Notes (2026-07-12):** Verified via grep that after this phase, every remaining
`.write_text(` call in `lazy-state.py` and `bug-state.py` sits AT OR AFTER each file's
fixture-region banner (the fixture-builder functions `_build_fixture`/`_build_bug_fixture` and
their many hermetic temp-dir fixtures, correctly out of scope per SPEC D1), and `lazy_core.py` has
zero `.write_text(` calls at all. `python -c "import ast; ..."` duplicate-def scan over
`lazy_core.py` confirms zero remaining duplicate top-level definitions. Files:
`user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/lazy_core.py`.

**Minimum Verifiable Behavior:** `grep -n "\.write_text(" user/scripts/lazy-state.py
user/scripts/bug-state.py user/scripts/lazy_core.py` shows every remaining hit at/after each file's
fixture-region banner (`lazy_core.py`: zero hits); `python -m pytest
user/scripts/test_lazy_core.py -q` fully green (see Phase 2 for the mechanical self-check that
pins this).

**Runtime Verification** *(script hygiene — no app runtime)*:
- [x] <!-- verification-only --> `python user/scripts/lazy-state.py --test` and
  `python user/scripts/bug-state.py --test` both exit 0 — every sentinel-write path the smoke
  harnesses exercise (hundreds of `BLOCKED.md` / `NEEDS_INPUT.md` / `ROADMAP.md` / `SPEC.md` writes
  across their fixtures) still produces parseable sentinels via the now-atomic path (Fix Scope
  item 5's "smoke-harness fixtures asserting parseable sentinels via the atomic path" — already
  covered by the PRE-EXISTING extensive fixture coverage re-run against the fixed writers, no new
  fixture needed). Verified 2026-07-12.

**MCP Integration Test Assertions:** N/A — no MCP-observable surface; the observable is on-disk
file atomicity + the `--test` smoke suites' continued green status.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` (verified exists — all named writers + banner move).
- `user/scripts/bug-state.py` (verified exists — mirrored writers + banner move + new top-level
  `import yaml` block).
- `user/scripts/lazy_core.py` (verified exists — duplicate `_current_head` removed).

**Testing Strategy:** Full gates (see bottom of this document) + the Phase 2 mechanical lint gates
that pin this phase's fix mechanically rather than by one-time grep alone.

**Integration Notes for Next Phase:** Phase 2 adds the MECHANICAL enforcement (Fix Scope item 2:
"the NEXT bare write cannot land silently") and the F811-class duplicate-def guard substitute
(Fix Scope item 3) so this phase's fix cannot silently regress.

---

### Phase 2: Mechanical lint gates — bare-write guard + F811-class duplicate-def guard

**Scope:** Add pure-AST collectors + self-checking meta-tests to `test_lazy_core.py` proving (a)
zero bare `.write_text(`/`open(..., "w"/"a"...)` calls remain in the production regions of
`lazy-state.py`, `bug-state.py`, `lazy_core.py`, and (b) zero duplicate top-level
`def`/`async def`/`class` names exist in those same three files — plus negative-fixture tests
proving each collector is genuinely discriminating (catches a planted violation, does not
false-positive on a clean/exempt case).

**TDD:** yes — RED-for-the-right-reason proven via the negative-fixture non-vacuity tests (a
synthetic planted bare write / duplicate def IS caught by name/line; a clean synthetic module, and
a fixture-region-scoped write, are NOT flagged).

**Status:** Complete

**Deliverables:**
- [x] `_bare_write_exempt_line` + `_collect_bare_production_writes` (pure AST collectors) added to
      `test_lazy_core.py`, scoped per-file via each state script's own fixture-region banner text
      (`"# Fixture smoke tests"` for `lazy-state.py`, `"SMOKE FIXTURES + --test"` for
      `bug-state.py`); `lazy_core.py` has no declared marker (100% production-scoped — the
      conservative default when a file has no exempt region at all).
- [x] `test_no_bare_production_sentinel_writes` — self-checking meta-test (GREEN on the live,
      post-Phase-1 tree; names file + line on any future regression).
- [x] `test_bare_write_lint_guard_detects_planted_violation` +
      `test_bare_write_lint_guard_catches_open_write_mode_and_ignores_read` — negative-fixture
      non-vacuity proofs: a synthetic bare `.write_text(` call BEFORE the marker is caught, the
      same call AFTER the marker (inside the fixture region) is not; a write/append-mode
      `open(...)` is caught, a read-mode/mode-less `open(...)` is not.
- [x] `_collect_duplicate_top_level_defs` (pure AST collector) +
      `test_no_duplicate_top_level_defs_in_state_scripts` (self-checking meta-test) +
      `test_duplicate_def_guard_detects_planted_violation` (negative fixture) — the F811-class
      gate substitute (SPEC D2: "the grep/AST-based check alone still closes the contract gap" —
      chosen over adding a `ruff` dependency to a repo with zero existing external lint tooling,
      per D2's own documented latitude; this fully covers the bug's own concrete "bonus finding"
      defect class — a silently-shadowed top-level definition).

**Implementation Notes (2026-07-12):** All new tests registered in the module's `_TESTS`
dead-coverage-guard list (this file's own `test_no_orphaned_test_functions` meta-test enforces
that every `def test_*` is registered — an unregistered new test is itself a mechanical failure,
caught and fixed during this phase's authoring). Gate:
`python -m pytest user/scripts/test_lazy_core.py -q` → 1030 passed (0 failed), including all 5 new
lint-gate tests plus the 8 stale-runtime-bug tests landed alongside in the same session. Files:
`user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k
"bare_production_write or duplicate_top_level_def or duplicate_def_guard" -q` is GREEN; the two
negative-fixture tests independently prove the collectors are not tautological (they report `[]`
on a clean synthetic module and non-empty on a planted violation).

**Runtime Verification:** N/A <!-- verification-only --> — lint-gate correctness is proven by the
negative-fixture tests themselves (their own assertions ARE the runtime verification of each
guard's discriminating power); no app runtime exists to additionally verify against.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 — the self-checking meta-tests must run against the ALREADY-fixed tree
to be GREEN today; they exist to prevent regression, not to have driven Phase 1's fix (which was
verified directly via grep + the full test suite).

**Files likely modified:** `user/scripts/test_lazy_core.py` (verified exists).

**Testing Strategy:** `pytest -k` targeting the five new lint-gate tests individually, then the
full suite.

**Integration Notes for Next Phase:** None — final phase.

**Completion (gate-owned):** N/A for this bug — `**Status:**` and `FIXED.md` are written directly
per this bug's operator-directed workflow (PHASES then implement, no pipeline `__mark_fixed__` gate
invoked in this lane) — see `FIXED.md`.

---

## Deferred Follow-Up (NOT gating this bug's Fixed status)

- **Fix Scope's alternate lint vehicle** — `ruff check --select F` (SPEC D2's preferred-if-adding-
  a-dependency-is-acceptable option) was NOT adopted. The stdlib AST duplicate-def guard above
  fully covers the concrete defect class this bug's "bonus finding" identified (a silently-shadowed
  top-level definition), without adding a new tooling dependency to a repo that currently has zero
  external lint tooling anywhere. A future harden-harness round wanting BROADER pyflakes-class
  coverage (unused imports, unused local variables, etc. — a wider class than just duplicate defs)
  can still adopt `ruff --select F` as an ADDITIONAL `--test`-wired gate; this is an open option,
  tracked here rather than silently dropped.

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews. This
bug's fix landed via a direct operator-directed bug-fix subagent pass — PHASES then implement, no
pipeline `__mark_fixed__` gate invoked in this lane.)_
