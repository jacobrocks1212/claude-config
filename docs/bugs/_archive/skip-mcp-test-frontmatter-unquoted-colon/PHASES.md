# Implementation Phases — SKIP_MCP_TEST frontmatter unquoted-colon breaks the strict sentinel parser

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is state-script / sentinel-parser work in claude-config, a repo with NO app surface (no `src-tauri/`, no `package.json` — confirmed this cycle). It is structurally outside MCP reach (the "no MCP-reachable surface" untestable class per `docs/features/mcp-testing/SPEC.md`); every deliverable is validated by the in-file `--test` smoke harnesses (`lazy-state.py --test`, `bug-state.py --test`) and the `test_lazy_core.py` pytest suite.

## Validated Assumptions

Per `/spec-phases` Step 2.7 — every load-bearing assumption here is **code-provable** (pure-Python YAML parsing over flat `key: value` frontmatter), so no runtime spike is scheduled:

- **PyYAML raises (does not silently mis-parse) on a single-line unquoted colon-space value.** Already empirically confirmed in the SPEC's `## Evidence Collected → Runtime Evidence` (`ScannerError: mapping values are not allowed here`) and re-confirmed this cycle (PyYAML 6.0.1 present). This is why the primary fix is a tolerant RE-parse on the `YAMLError` path, not a nested-mapping unwrap.
- **`parse_sentinel`'s `yaml.safe_load` + `_die`-on-`YAMLError` is the single chokepoint** (`lazy_core.py:816-820`, read this cycle) — every Step-9 consumer reaches the fault through it.
- **`yaml.safe_dump` already quotes colon-bearing scalar values.** The `safe_dump`-based writers (`lazy-state.py:_write_yaml_sentinel` / `_write_yaml_blocked_sentinel`, `bug-state.py` `safe_dump` branch) emit `reason: 'a: b'` correctly today — so "quote-on-write" is already satisfied for pipeline-authored artifacts EXCEPT the degenerate no-PyYAML manual fallback in `bug-state.py:_write_yaml_sentinel` (lines ~1712-1716, `f"{k}: {v}"`), which does NOT quote. That degenerate path is the only quote-on-write gap.

**SPEC-example capability audit:** the SPEC's only "code examples" are YAML frontmatter snippets consumed by `yaml.safe_load` — every construct (flat `key: value` sentinel frontmatter, `yaml.safe_load`, `yaml.safe_dump`) is present and supported (PyYAML 6.0.1; `parse_sentinel` exists exactly as described). No explicitly-rejected capability. Clean — no planning-time halt.

**MCP tool-existence audit:** no-op — claude-config declares no `.claude/skill-config/mcp-tool-catalog.md` (confirmed absent this cycle). Repo has no MCP surface.

## Touchpoint Audit Table (verified this cycle via Read/Grep)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `parse_sentinel` (784), the `yaml.safe_load`+`_die` block (816-820), `_die` (121), `skip_waiver_refusal` (899), `__write_validated_from_skip__` in `apply_pseudo` (3969) | refactor | The fix lands in `parse_sentinel`'s `except yaml.YAMLError` arm (816-820). Add a tolerant RE-parse helper (new module-level fn, e.g. `_yaml_load_tolerant`) invoked ONLY on the error path; `_die` stays the final fallback. Do NOT touch `skip_waiver_refusal` / `__write_validated_from_skip__` — they consume `parse_sentinel`'s return unchanged. |
| `user/scripts/test_lazy_core.py` | yes | pytest suite over `lazy_core` helpers | modify | Add `parse_sentinel` tolerance cases next to existing sentinel-parse tests. |
| `user/scripts/lazy-state.py` | yes | Step-9 readers `skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {}, repo_root)` (3336, 3361); `_write_yaml_sentinel` (3499, `safe_dump` — already safe); in-file `--test` harness (`_build_fixture` ~3536) | modify (tests only) | Add a `--test` fixture proving an unquoted-colon operator SKIP_MCP_TEST.md routes Step 9 → `__write_validated_from_skip__` (no `_die`). No production-code change here — the parser fix in `lazy_core.py` is what repairs this leg. |
| `user/scripts/bug-state.py` | yes | mirrored Step-9 read; `_write_yaml_sentinel` (1706) with a no-PyYAML `f"{k}: {v}"` fallback (1712-1716) that does NOT quote colon-bearing values | modify | (Ph2) add the mirrored `--test` fixture (coupled pair). (Ph3) harden the ImportError fallback to quote colon-bearing scalar values. |
| `user/skills/_components/sentinel-frontmatter.md` | yes | canonical `SKIP_MCP_TEST.md` schema (`reason`, `skipped_by`, `granted_by`, `spec_class`) | modify | Document the new read tolerance (unquoted colon-space in a scalar value is read as a literal) + the cross-repo lockstep note. |

**Contradiction correction (mechanical, applied in-plan):** the SPEC's `## Affected Area` lists the Step-9 read legs at `lazy-state.py:~3336/~3361` as places "where a human-authored waiver first reaches the strict parse." Verified: those call sites are consumers of `parse_sentinel` and need NO production edit — fixing `parse_sentinel` repairs them transparently. The plan therefore schedules those files for **test-only** changes (regression fixtures), not production edits. This narrows the SPEC's affected-area to the true single production chokepoint (`parse_sentinel`) plus the `bug-state.py` write-fallback.

## Phase 1: Tolerant read at `parse_sentinel` (the single production chokepoint)

**Scope:** Make `parse_sentinel` (`lazy_core.py`) read an unquoted colon-space (or trailing-colon) in a flat scalar *value* as a literal instead of `_die`-ing, while preserving strict schema semantics for keys/kinds and preserving `_die` for genuinely-malformed frontmatter. Implemented as a **try-strict-then-tolerant** re-parse: `yaml.safe_load` is attempted first (well-formed files stay byte-identical); ONLY on `yaml.YAMLError` does a tolerant helper quote each flat `^key: value` line's value (when not already quoted / a flow collection / a block scalar) and re-load. If the tolerant re-parse also fails or yields a non-mapping, `_die` fires exactly as today.

**Deliverables:**
- [x] New module-level tolerant-load helper in `lazy_core.py` (e.g. `_yaml_load_tolerant(yaml_body) -> dict | None`) that quotes colon-bearing flat scalar values on a per-line basis and re-invokes `yaml.safe_load`.
- [x] `parse_sentinel`'s `except yaml.YAMLError` arm (816-820) calls the tolerant helper before falling through to `_die` — `_die` remains the final fallback for non-rescuable errors.
- [x] Tests (`test_lazy_core.py`): unquoted colon-space `reason` parses to the literal string; a `skipped_by` value naming a `key: value` pair parses; a trailing-colon value parses; **control** — a colon with no following space (`reason: build:step`) stays a plain scalar (unchanged); **non-vacuity** — a genuinely-malformed frontmatter (e.g. a broken block structure / non-mapping) STILL `_die`s (the tolerant path does not mask real errors); a well-formed file's parse result is byte-identical to pre-change.

#### Implementation Notes (Phase 1 — 2026-07-04, cloud)
- Added `_FLAT_SCALAR_LINE_RE` + `_yaml_load_tolerant(yaml_body)` in `lazy_core.py` immediately before `parse_sentinel`. The helper runs ONLY on the `yaml.YAMLError` path: it single-quotes each flat top-level `key: value` plain scalar value (leaving already-quoted / flow-collection `[`/`{` / block-scalar `|`/`>` / anchor-tag `&`/`*`/`!`/`#` / empty values untouched) and re-invokes `yaml.safe_load`, returning the dict on success or `None` so `parse_sentinel` falls through to the unchanged `_die`.
- Wired into `parse_sentinel`'s `except yaml.YAMLError` arm: tolerant re-parse first, `_die` retained as the final fallback (well-formed files never reach the tolerant path — strict `safe_load` succeeds, byte-identical).
- 6 new tests in `test_lazy_core.py` (registered in `_TESTS` — the dead-coverage guard `test_no_orphaned_test_functions` requires it): 3 tolerance (colon-space `reason`, `key: value`-bearing value, trailing colon), 1 control (`build:step` colon-no-space), 1 non-vacuity (unclosed flow collection still `SystemExit`s), 1 regression (well-formed no-colon byte-identical). Confirmed RED before impl (SystemExit 2 via `_die`), GREEN after.
- **Review verdict:** PASS (self-review: tolerant path narrowly scoped to VALUE quoting on the error path only; strict schema for keys/kinds preserved; non-vacuity test guards over-tolerance).
- Note: the repo-wide `pytest` run shows ~71 pre-existing failures in the `apply_pseudo`/`__mark_*__` family — these are C3 cycle-containment refusals (this cloud cycle runs with `lazy-cycle-active.json` armed), NOT regressions; identical on the clean tree. Parser/test changes here add zero new failures.

**Minimum Verifiable Behavior:** `python3 -m pytest user/scripts/test_lazy_core.py -k parse_sentinel` passes, including the new tolerance + non-vacuity cases. (Runnable command; the tolerant behavior is directly asserted.)

**Runtime Verification** *(N/A for this repo — no MCP/dev runtime; the pytest run above IS the observable proof):*
- N/A — no runtime-observable behavior outside the Python test suite.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (pure-Python parser change in a repo with no MCP surface).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `_yaml_load_tolerant`; wire it into `parse_sentinel`'s `YAMLError` arm.
- `user/scripts/test_lazy_core.py` — tolerance + control + non-vacuity cases.

**Testing Strategy:** Pure unit test of `parse_sentinel` in isolation via `test_lazy_core.py`. No mocks needed — drive real frontmatter strings through the real parser. The control + non-vacuity cases guard against over-tolerance (masking real malformation) and behavior drift on well-formed files.

**Integration Notes for Next Phase:**
- After this phase, EVERY consumer of `parse_sentinel` (the Step-9 `skip_waiver_refusal` legs, `__write_validated_from_skip__`) transparently tolerates colon-bearing values — Phase 2 proves that at the real consumer site without further production change.
- The helper must quote ONLY flat top-level `key: value` scalar lines; leave already-quoted values, flow collections (`[...]`/`{...}`), and block-scalar indicators (`|`/`>`) untouched so it never corrupts a legitimately-structured value.

---

## Phase 2: End-to-end completion-gate regression fixtures (coupled pair — both state scripts)

**Scope:** Prove the fix at the ACTUAL failure site — the Step-9 completion leg — by adding a fixture to each state script's in-file `--test` harness where a fully-implemented item carries an operator-granted `SKIP_MCP_TEST.md` whose `reason:` contains an unquoted colon-space. Assert the probe reaches the skip→validated route (`__write_validated_from_skip__`) instead of exiting 2. This is the integration slice: it drives the real `compute_state` path that the bug hard-halted at the finish line.

**Deliverables:**
- [x] `lazy-state.py --test` fixture: a feature past implementation, no `VALIDATED.md`, `SKIP_MCP_TEST.md` with `granted_by: operator` and an unquoted colon-space `reason` → probe returns `sub_skill == "__write_validated_from_skip__"` (not a `_die`/exit-2).
- [x] `bug-state.py --test` fixture: the mirrored bug-pipeline case (coupled pair) proving the same acceptance on the bug Step-9 read.
- [x] Regenerate the byte-pinned `--test` baselines (`tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt`) via the sanctioned `_normalize_smoke_output` path (never by hand) so both suites stay green.

#### Implementation Notes (Phase 2 — 2026-07-04, cloud)
- Added fixture `skip-operator-colon-reason-validates` to `lazy-state.py::_build_fixture` (+ its assertion row expecting `sub_skill == "__write_validated_from_skip__"`, `feature_id == "feat-socr"`, `current_step == "Step 9: skip-mcp-test → validated"`).
- Added the coupled-pair mirror `step9-skip-colon-reason` to `bug-state.py::_build_bug_fixture` (+ assertion row: `current_step == STEP_MCP_SKIP`, `sub_skill == "__write_validated_from_skip__"`).
- **Load-bearing detail:** both fixtures write `SKIP_MCP_TEST.md` RAW via `.write_text()` (NOT `_write_yaml_sentinel`, whose `yaml.safe_dump` auto-quotes and would mask the bug) so the on-disk frontmatter carries the exact hand-authored unquoted colon-space `reason: untestable on this host: no real audio device` that reproduced the fault.
- Regenerated both byte-pinned baselines through `_normalize_smoke_output` (isolated `LAZY_STATE_DIR`) — diff is exactly one new PASS line per baseline. `test_lazy_state_test_output_matches_baseline` + `test_bug_state_test_output_matches_baseline` green.
- Coupled-pair HARD gate: `lazy_parity_audit.py --repo-root .` exit 0 after both edits.
- **Review verdict:** PASS (self-review: fixtures drive the REAL `compute_state` Step-9 route end-to-end; RAW-write reproduces the fault shape; assertion targets the exact skip→validated sub_skill).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both pass with the new fixtures; the previously-`_die`-ing colon-bearing waiver now routes to `__write_validated_from_skip__`.

**Runtime Verification** *(N/A — the two `--test` runs above are the observable proof):*
- N/A — no runtime-observable behavior outside the Python `--test` harnesses.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (state-machine fixture work in a repo with no MCP surface).

**Prerequisites:**
- Phase 1: `parse_sentinel` tolerance must be in place — these fixtures are RED before Phase 1 (the harness `_die`s / exits 2 on the colon-bearing waiver) and GREEN after.

**Files likely modified:**
- `user/scripts/lazy-state.py` — new `--test` fixture (+ registration in the test-list block).
- `user/scripts/bug-state.py` — mirrored `--test` fixture (+ registration).
- `tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt` — regenerated.

**Testing Strategy:** Build a temp-dir fixture (mirror an existing skip-related fixture) and assert the computed state's `sub_skill`. The coupled-pair rule (root `CLAUDE.md`, Coupling Rule #4 / `user/scripts/CLAUDE.md`) requires the bug-pipeline mirror; run `lazy_parity_audit.py --repo-root .` to confirm the pair stays green after editing both harnesses.

**Integration Notes for Next Phase:**
- With the read path proven end-to-end, Phase 3 is defense-in-depth on the WRITE side + the schema-doc lockstep — it changes no read behavior.

---

## Phase 3: Quote-on-write hardening + schema-doc lockstep (defense-in-depth)

**Scope:** Close the one remaining unsafe writer and document the read tolerance. `yaml.safe_dump`-based writers already quote colon-bearing values, so the only gap is `bug-state.py`'s no-PyYAML `_write_yaml_sentinel` ImportError fallback (`f"{k}: {v}"`), which must quote colon-bearing scalar values. Then update the canonical sentinel schema doc to state the read tolerance and flag the cross-repo `.ts`-validator lockstep.

**Deliverables:**
- [x] Harden `bug-state.py:_write_yaml_sentinel`'s ImportError fallback (lines ~1712-1716) to single-quote any scalar value containing a colon-space or trailing colon (parity with what `safe_dump` emits), so a pipeline-authored sentinel is valid YAML even on the no-PyYAML path.
- [x] A note/assert confirming the `safe_dump` writers (`lazy-state.py:_write_yaml_sentinel` + both `_write_yaml_blocked_sentinel`) already emit quoted colon-bearing values — no change needed there (record the confirmation in `#### Implementation Notes`).

#### Implementation Notes (Phase 3 — 2026-07-04, cloud)
- Added shared helper `lazy_core._yaml_fallback_scalar(value)` — single-quotes a scalar string containing a colon-space or trailing colon (doubling embedded single quotes); renders colon-free strings, colon-WITHOUT-space strings (`build:step`), and non-strings unchanged via `str()`.
- Wired it into `bug-state.py`'s ImportError fallbacks: `_write_yaml_sentinel` (WU-3 scope) AND, for completeness, the sibling `_write_yaml_blocked_sentinel` fallback which carried the identical latent `f"{k}: {v}"` unquoted defect (⚖ policy below).
- **`safe_dump`-writer confirmation (empirically verified this cycle):** `yaml.safe_dump({'reason':'untestable on this host: no real audio device'})` → `reason: 'untestable on this host: no real audio device'` (quoted); `'waiting on:'` → `'waiting on:'` (quoted); `'build:step'` → `build:step` (unquoted). So `lazy-state.py:_write_yaml_sentinel`, both `_write_yaml_blocked_sentinel` `safe_dump` branches, and `bug-state.py`'s `safe_dump` branch already emit correctly quoted colon-bearing values — NO change needed there. `_yaml_fallback_scalar` matches this behavior exactly (parity).
- **Helper location (⚖ policy: fallback quoter location → shared `lazy_core.py`):** the plan phrases the fix as "harden `bug-state.py`'s fallback." The quoting logic lives in `lazy_core.py` (shared, importable) so `test_lazy_core.py` can round-trip it directly (`bug-state.py` is dash-named / not importable); the WIRING is in `bug-state.py`'s fallback as specified. End-state behavior is identical to inlining — a mechanical-internal factoring choice.
- **Completeness (⚖ policy: harden sibling blocked-sentinel fallback too → yes):** WU-3 names only `_write_yaml_sentinel`, but `_write_yaml_blocked_sentinel`'s ImportError fallback had the same one-line unquoted-colon defect class; hardened it with the same helper in-cycle (identical fix, zero product-behavior divergence between the options).
- 2 new tests in `test_lazy_core.py` (registered in `_TESTS`): quote-and-round-trip (colon-space → single-quoted → `parse_sentinel` literal + trailing-colon quoted) and leaves-plain-unchanged (`operator`/`build:step`/`5`). RED before impl (`AttributeError` — helper absent), GREEN after. `--test` baselines unaffected (fallback only runs when PyYAML is absent; PyYAML present in-env so `safe_dump` runs).
- Coupled-pair HARD gate: `lazy_parity_audit.py --repo-root .` exit 0 (bug-state.py edited; the fallback-hardening is a justified feature/bug divergence — lazy-state.py's `_write_yaml_sentinel` has no ImportError fallback since `lazy_core` hard-requires PyYAML).
- **Review verdict:** PASS.
- [x] Update `user/skills/_components/sentinel-frontmatter.md`: document that the sentinel reader now tolerates an unquoted colon-space in a scalar value (read as a literal), and add the standing cross-repo lockstep note that AlgoBooth's `check-docs-consistency.ts` / `check-bugs-consistency.ts` `SENTINEL_SCHEMAS` must mirror the tolerance if/when they adopt it (those `.ts` validators live in AlgoBooth, NOT this repo — a documented follow-up, not editable from here). *(WU-4 — landed in Batch 1; read-tolerance note in the Parsing protocol + a pointer at the SKIP_MCP_TEST `reason` field + the cross-repo `.ts`-lockstep note. `project-skills.py`/`lint-skills.py`/`doc-drift-lint.py` clean — no `!cat` markers touched.)*

**Minimum Verifiable Behavior:** A unit assertion (in `test_lazy_core.py` or a `bug-state.py --test` fixture) that the hardened fallback output, when re-read by `parse_sentinel`, round-trips a colon-bearing `reason` to the literal string; `python3 user/scripts/lint-skills.py` and `python3 user/scripts/doc-drift-lint.py --repo-root .` stay clean after the component-doc edit.

**Runtime Verification** *(N/A — the unit round-trip + lints above are the observable proof):*
- N/A — no runtime-observable behavior outside the Python test/lint runs.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (write-path hardening + docs in a repo with no MCP surface).

**Prerequisites:**
- Phase 1: the tolerant read is what makes the round-trip assertion meaningful (and makes the safe_dump path's existing quoting non-load-bearing for correctness — it's defense-in-depth, not the fix).

**Files likely modified:**
- `user/scripts/bug-state.py` — quote colon-bearing values in the ImportError fallback.
- `user/skills/_components/sentinel-frontmatter.md` — read-tolerance + cross-repo lockstep note.
- `user/scripts/test_lazy_core.py` (or a `bug-state.py --test` fixture) — round-trip assertion.

**Testing Strategy:** Round-trip test (write via the hardened fallback → read via `parse_sentinel` → assert literal value). Doc edit verified by the existing `lint-skills.py` + `doc-drift-lint.py` clean runs (the component is injected into skills; keep injections intact).

**Integration Notes for Next Phase:** Final phase.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed`, writes the `FIXED.md` receipt, and archives the bug dir once the validation tail passes — never authored as a checkbox row here.

---

## Cross-feature Integration Notes

No hard dependencies — the SPEC carries no `**Depends on:**` block (verified this cycle), so `--sync-deps` was skipped (nothing to project). This is a self-contained parser/state-script fix.

## Implementation Notes

- **Coupled pair (HARD).** Phase 2 edits both `lazy-state.py` and `bug-state.py` `--test` harnesses, and Phase 3 edits `bug-state.py`. Run `python3 user/scripts/lazy_parity_audit.py --repo-root .` (exit 0) after those edits — the sentinel read is a coupled-pair surface (Coupling Rule #4).
- **Baselines are byte-pinned.** Regenerate `--test` baselines only through `_normalize_smoke_output` (per `user/scripts/CLAUDE.md` → Testing), never by hand.
- **Over-tolerance is the risk to guard.** The Phase-1 non-vacuity test (a genuinely-malformed file still `_die`s) is load-bearing — the tolerant re-parse must rescue ONLY the unquoted-colon-in-scalar case, not silently accept structurally-broken frontmatter.
- **Cross-repo lockstep is a documented follow-up, not an in-repo edit.** AlgoBooth's `check-docs-consistency.ts` / `check-bugs-consistency.ts` are not in claude-config; Phase 3 only records the mirror obligation in `sentinel-frontmatter.md`.
