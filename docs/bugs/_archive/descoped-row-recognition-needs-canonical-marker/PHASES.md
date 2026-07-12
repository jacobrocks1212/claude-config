# Implementation Phases — Descoped PHASES rows need a canonical structural marker

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure Python state-machine helper + Markdown component change (`user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`, `user/skills/_components/completeness-policy.md`). No app/UI/audio surface; nothing MCP-reachable. Per `docs/features/mcp-testing/SPEC.md`'s untestable classes, this is build-tooling/docs-adjacent script logic — verified entirely by the `--test` harness + `test_lazy_core.py` (pytest).

## Cross-feature Integration Notes

No hard (`kind: hard`) upstream dependencies — `**Depends on:** (none)` was not stated explicitly in SPEC.md, but the SPEC's "Related" links are informational precedent only (the `_VERIFICATION_ONLY_MARKER` precedent it mirrors), not a dependency edge. Skipping Step 1.5/1.6 (no dep block to sync).

## Touchpoint Audit (verified against live source, 2026-07-12)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|--------------------------|--------|-----------------------------|
| `user/scripts/lazy_core.py` | yes | `_VERIFICATION_ONLY_MARKER` (:2192), `_VERIFICATION_SECTION_RE` (:2203), `_DESCOPE_STRIKETHROUGH_RE` (:2258), `_DESCOPE_MARKER_RE` (:2259), `_row_is_descoped_in_place` (:2265), `remaining_unchecked_are_verification_only` (:2278-2456) | refactor | Mirror the `_VERIFICATION_ONLY_MARKER` structural-marker pattern (row-scope via `row_has_marker`/`section_has_marker`, header-scope via the bold/heading branches at :2369/:2391) onto the descope axis. Reuse the existing `warned_headers`/`_diag` shim-diagnostic mechanism (:2436-2446) — do not invent a second diagnostics path. |
| `user/scripts/test_lazy_core.py` | yes | `test_verification_only_descoped_dropped_row_is_true` (:926), `test_verification_only_plain_unchecked_row_still_false` (:950), `test_verification_only_struck_without_descope_marker_still_false` (:966), registered in `_TESTS` (:16453-16456); `test_ruvonly_marker_lockstep_producers_match_ssot` (:24237) is the lockstep-test precedent to mirror | refactor + create | Keep the 3 existing fixtures passing unmodified (conservatism regression net); ADD new fixtures for the marker path + shim diagnostic + header-scope, and a new lockstep test mirroring `test_ruvonly_marker_lockstep_producers_match_ssot`. |
| `user/skills/_components/completeness-policy.md` | yes | `## Resolution rules by decision site` numbered list (items 1-5, lines 26-56); `## The scope test` (lines 14-24) | refactor | Add the marker-authoring instruction to item 1 (cycle-subagent scope resolution) and item 2 (NEEDS_INPUT `class: scope` auto-resolution) — the two sites the SPEC's Evidence Collected section identifies as where descope-in-place rows are actually authored ad hoc today. Reference the SSOT constant `lazy_core:_DESCOPED_MARKER` **by name**, never re-hardcode the string. |
| AlgoBooth `scripts/check-docs-consistency.ts` | not touched this round | — | note only | Per SPEC item 5 and the `_VERIFICATION_ONLY_MARKER` precedent: the marker is a ROW ANNOTATION, not a sentinel — it does NOT enter `SENTINEL_SCHEMAS`, so no edit is expected. Recorded here as a documented no-op, matching the precedent's own note. |

No contradictions found — the existing code and tests match the SPEC's cited `file:line` trace exactly (verified by direct read, not inference).

---

### Phase 1: Canonical structural descope marker + detector promotion + regression fixtures

**Scope:** Add the SSOT structural marker `_DESCOPED_MARKER = "<!-- descoped -->"` to `lazy_core.py`, mirroring `_VERIFICATION_ONLY_MARKER` exactly (per-row HTML comment, invisible in rendered markdown, phrasing-independent). Make it the PRIMARY signal in the descope-recognition path — a row (or its enclosing subsection header) carrying the marker is exempt regardless of the free-text keyword. Demote `_DESCOPE_STRIKETHROUGH_RE` + `_DESCOPE_MARKER_RE` to a deprecation shim: still exempt (no regression for un-migrated PHASES.md rows), but when the LEGACY strikethrough+keyword path (not the marker) is what exempts a row, append a `_DIAGNOSTICS` warning naming the row so the migration gap is visible — exactly the `_VERIFICATION_SECTION_RE` shim pattern already in this file (lines 2195-2212, 2435-2447).

**Deliverables:**
- [x] `_DESCOPED_MARKER = "<!-- descoped -->"` constant added to `lazy_core.py`, adjacent to `_DESCOPE_STRIKETHROUGH_RE`/`_DESCOPE_MARKER_RE` (:2258-2262), with a docstring/comment block mirroring the `_VERIFICATION_ONLY_MARKER` rationale comment (:2164-2191) — including the same "check-docs-consistency.ts fallback: row annotation, not a sentinel" note.
- [x] `_row_is_descoped_in_place` (or the row-scanning branch at :2409-2449 that calls it) updated so a row carrying `_DESCOPED_MARKER` is exempt as the PRIMARY signal, independent of `_DESCOPE_MARKER_RE`. Support BOTH row-level (`<!-- descoped -->` on the `- [ ]` line itself) AND header-scope (the marker on an enclosing bold/heading subsection line, e.g. `**Descoped:**`) — mirroring the existing `row_has_marker`/`section_has_marker` split for verification rows (:2369, :2391, :2427-2431). Resolves SPEC Open Question 2 toward "support both" per its own recommendation.
- [x] `_DESCOPE_STRIKETHROUGH_RE` + `_DESCOPE_MARKER_RE` demoted to a deprecation shim: when a row is exempted via the LEGACY strikethrough+keyword path and NOT via the marker, emit a `_diag(...)` warning naming the row text (reuse the existing dedup-by-text-or-header pattern from `warned_headers`, :2325-2326/2436-2437 — do not invent a second diagnostics mechanism). The shim continues to exempt (no regression); the warning surfaces the un-migrated gap only.
- [x] The strikethrough requirement (`_DESCOPE_STRIKETHROUGH_RE`) is **retained as a requirement of the legacy shim path only** — a marker-carrying row is exempt on the marker's presence alone (mirrors `_VERIFICATION_ONLY_MARKER`, which needs no accompanying regex match). Document this distinction inline so a future reader does not conflate the two paths.
- [x] Regression fixtures in `test_lazy_core.py` (co-located with the existing descoped-in-place tests at :921-982):
  - Marker-only row (NO free-text keyword, e.g. `- [ ] <!-- descoped --> some dropped note` with no `**DROPPED**`) → `remaining_unchecked_are_verification_only` returns `True`, no diagnostic emitted (marker path, not shim path).
  - Legacy struck `**DROPPED**` row (the existing `test_verification_only_descoped_dropped_row_is_true` shape, unchanged) → still `True` (no regression) **AND** a `_DIAGNOSTICS` migration warning is present naming the un-migrated row (extend the existing test or add a sibling asserting on `lazy_core._DIAGNOSTICS` / the diagnostics-returning entry point used by the `_VERIFICATION_SECTION_RE` shim's own test precedent — inspect how the verification shim's diagnostic is asserted in existing tests and mirror that exact mechanism).
  - Plain unchecked row (existing `test_verification_only_plain_unchecked_row_still_false`) → unchanged, still `False`.
  - Struck row without marker-or-keyword (existing `test_verification_only_struck_without_descope_marker_still_false`) → unchanged, still `False`.
  - Header-scope marker (a bold/heading subsection line carrying `_DESCOPED_MARKER`, with one or more unchecked rows beneath it and no per-row marker) → `True`, mirroring the verification marker's header-scope test coverage.
  - Register every new fixture in the `_TESTS` list (mirror the registration block at :16453-16456).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` (or the repo's pytest invocation) passes with the new fixtures included, and `python3 user/scripts/lazy-state.py --test` + `python3 user/scripts/bug-state.py --test` (shared `lazy_core` import) both stay green — this is a pure logic change with no runtime/MCP surface, so unit-test green IS the verification for this phase (no `- [ ]` Runtime Verification section needed; this phase's behavior is fully code-provable, not runtime-coupled — the Step 2.7 gate is satisfied by that classification, not by a spike).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `_DESCOPED_MARKER`, promote it to primary signal, demote the regex pair to a shim with a migration diagnostic.
- `user/scripts/test_lazy_core.py` — new regression fixtures + `_TESTS` registration.

**Testing Strategy:** Pure unit-level fixture testing via the existing `_guard()` + hand-built `phases_text` string pattern already used by the 3 sibling tests (:926-981). No mocks needed beyond what's already established. Run `python3 user/scripts/test_lazy_core.py` and both state scripts' `--test` harnesses (they share `lazy_core`) before moving to Phase 2.

**Integration Notes for Next Phase:**
- The SSOT constant name is `_DESCOPED_MARKER` (module `lazy_core`) — Phase 2's producer-facing prose must reference it **by this exact name**, never restate the literal `<!-- descoped -->` string as an independent source of truth (mirrors the `_VERIFICATION_ONLY_MARKER` lockstep discipline).
- Confirm during Phase 1 whether the existing verification-shim diagnostic is asserted via a dedicated public accessor (e.g. a `lazy_core._DIAGNOSTICS` list read in tests) — reuse that exact mechanism for the descope-shim diagnostic assertion in Phase 1's own fixtures, and note the accessor name here for anyone auditing Phase 2's lockstep test.

**Implementation Notes (2026-07-12, Phase 1 complete):**
- **Status: Complete.** Implemented via TDD (test agent RED → impl agent GREEN), plan part 1.
- **SSOT constant:** `lazy_core._DESCOPED_MARKER = "<!-- descoped -->"` at `lazy_core.py:2286`, with a rationale comment block mirroring `_VERIFICATION_ONLY_MARKER` (incl. the check-docs-consistency.ts "row annotation, not a sentinel" fallback note). **Phase 2 must reference this constant BY NAME** in `completeness-policy.md`, never re-hardcode the literal string.
- **Detection (in `remaining_unchecked_are_verification_only`):** two new tracked flags — `section_has_descope_marker` and `warned_descope_rows: set[str]` (init ~:2377-2378). Header-scope handled in both the `#`-heading branch (`section_has_descope_marker = _DESCOPED_MARKER in line`, reset on Phase headings) and the bold-header branch (independent block ~:2426-2429: set True on the marker, reset on a verification/deliverables subsection boundary). Row branch (~:2472): PRIMARY path `if _DESCOPED_MARKER in line or section_has_descope_marker` exempts with NO diagnostic; the legacy `_row_is_descoped_in_place` (struck + keyword, marker absent) still exempts BUT emits a per-row-deduped `_diag(...)` migration warning.
- **Diagnostic accessor (for Phase 2's audit):** the shim diagnostic is read in tests via `lazy_core.clear_diagnostics()` (reset) then reading the module-level `lazy_core._DIAGNOSTICS` list — the exact mechanism the verification-shim test (`test_ruvonly_novel_header_without_marker_warns_and_fails`) uses. Phase 1's fixtures reuse it; no new accessor was needed.
- **Conservatism preserved:** a plain unchecked row, or a struck row without keyword-and-marker, matches neither descope branch and falls through to the verification path → `False`. The 3 pre-existing sibling tests pass unchanged.
- **Tests:** 4 new fixtures + `_TESTS` registration in `test_lazy_core.py` (`test_verification_only_descoped_marker_only_row_is_true`, `..._legacy_dropped_row_still_true_with_migration_diagnostic`, `..._descoped_marker_no_diagnostic`, `..._descoped_header_scope_marker_exempts_rows_beneath`). All green.
- **Verification (this repo's gate):** `test_lazy_core.py` → PASS=752, FAIL=4; both `lazy-state.py --test` and `bug-state.py --test` → "All smoke tests passed". The 4 FAILs are exclusively the pre-existing `test_checkpoint_*` tests, which fail because a LIVE `/lazy-batch` run marker refuses their `--run-start` subprocesses (exit 3) — environmental to the in-flight run, unrelated to this change (they failed identically before this work), and out of scope. The suite was run with `LAZY_ORCHESTRATOR=1` to bypass the same live-run refuse guard on in-process fixtures.
- **Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

---

### Phase 2: Producers emit the canonical marker + lockstep test

**Scope:** Update the two ad hoc descope-authoring surfaces the SPEC's Evidence Collected section identifies — `_components/completeness-policy.md`'s scope-decision resolution rules (item 1: cycle-subagent scope resolution; item 2: `NEEDS_INPUT.md class: scope` auto-resolution, the live incident's actual provenance) — so that when a PHASES.md deliverable is resolved as "descope in place" rather than fully implemented, the row is authored with the canonical `_DESCOPED_MARKER` (referenced by name) in addition to (not instead of, for readability) the existing free-text keyword. Add a lockstep test asserting the producer prose references the SSOT constant by name, mirroring `test_ruvonly_marker_lockstep_producers_match_ssot` (:24237-24259).

**Deliverables:**
- [x] `_components/completeness-policy.md` "Resolution rules by decision site" item 1 (cycle subagents, lines ~28-32) updated: when the resolved-in-cycle scope decision results in a row being struck through/dropped in PHASES.md rather than implemented, the row MUST carry the canonical structural marker (name the SSOT constant `lazy_core:_DESCOPED_MARKER`) alongside the existing human-readable `**DROPPED**`/`**DESCOPED**`/`**WON'T-FIX**` note — not a replacement for the free-text note (which stays for human readability), an addition for machine recognition.
- [x] `_components/completeness-policy.md` item 2 (NEEDS_INPUT `class: scope` auto-resolution, lines ~33-36) updated with the same instruction — this is the exact site the live incident (`live-settings-split-brain-disarms-enforcement-plane` PHASES line 128) went through, per SPEC's "Producers" analysis.
- [x] A worked example row added inline in the updated component text (e.g. `- [ ] ~~<text>~~ **DROPPED** <!-- descoped --> (decision N, NEEDS_INPUT.md resolution, <date>)`) so a future producer sees the exact shape, not just prose.
- [x] New lockstep test in `test_lazy_core.py`, co-located near `test_ruvonly_marker_lockstep_producers_match_ssot` (:24237-24282): `test_descoped_marker_lockstep_producer_matches_ssot` — reads `_components/completeness-policy.md` from disk, asserts `lazy_core._DESCOPED_MARKER` appears in it by value (mirrors the RUVOnly lockstep test's exact structure: guard, path-exists assertion, `marker in text` assertion). Register it in `_TESTS`.
- [x] Re-project skills after the component edit: `python ~/.claude/scripts/project-skills.py` (validates the edit did not break injection) — confirm no lint regressions with `python ~/.claude/scripts/lint-skills.py`.

**Implementation Notes (2026-07-12, Phase 2 complete):**
- **Status: Complete.** Implemented via TDD (test agent RED → impl agent GREEN), plan part 2. Prerequisite (part 1: `_DESCOPED_MARKER` in `lazy_core.py:2286`) confirmed `status: Complete` before start.
- **Producer edits (`user/skills/_components/completeness-policy.md`, 97→108 lines):** item 1 (cycle subagents, ~:32-37) and item 2 (NEEDS_INPUT `class: scope`, ~:41-48) both now instruct that a struck/dropped PHASES.md row MUST carry the canonical structural marker, naming the SSOT constant `lazy_core:_DESCOPED_MARKER` BY NAME. Item 2 cites the live incident (`live-settings-split-brain-disarms-enforcement-plane`) as its provenance and carries the fenced worked example `- [ ] ~~<text>~~ **DROPPED** <!-- descoped --> (decision N, NEEDS_INPUT.md resolution, <date>)`.
- **SSOT discipline:** the literal `<!-- descoped -->` string appears EXACTLY ONCE in the file (the worked example, :47); both prose sentences reference the constant by name only — mirroring the `_VERIFICATION_ONLY_MARKER` precedent.
- **Lockstep test:** `test_descoped_marker_lockstep_producer_matches_ssot` added to `test_lazy_core.py` (:24405) immediately after `test_ruvonly_marker_lockstep_producers_match_ssot`, with a new `_COMPLETENESS_POLICY_PATH` constant (:24287) alongside the two precedent path constants, and a sibling `_TESTS` append block (:24424). Authored RED (marker absent from the component) → GREEN after the WU-4 edit.
- **Verification (this repo's gate):** the new test and the precedent `test_ruvonly_marker_lockstep_producers_match_ssot` + the verification-only marker tests all PASS in isolation (run under a hermetic `LAZY_STATE_DIR`, cycle-env neutralized). `project-skills.py` (88 skills / 97 components, no errors) and `lint-skills.py` ("OK — no broken or embedded !cat patterns") both exit clean. Note: the full `python3 user/scripts/test_lazy_core.py` cannot run to a clean `Results:` line while THIS `/lazy-bug-batch` cycle is live — several `apply_pseudo`/`mark_*` tests hit the cycle-containment refusal (`SystemExit(3)`) which escapes the in-file harness's `except Exception`; a markdown + string-presence change cannot affect those paths (documented harness quirk, unrelated to this change).
- **Review verdict:** PASS (WU-3 + WU-4 ground-truth verified: yes; assertion-vs-intent clean; SSOT literal-count == 1).
- **Files modified:** `user/skills/_components/completeness-policy.md`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` passes including the new lockstep test, and `python ~/.claude/scripts/lint-skills.py` reports no new findings against `completeness-policy.md`. Code-provable (pure doc + assertion), no runtime coupling — unit-test green is the verification.

**Prerequisites:**
- Phase 1: `_DESCOPED_MARKER` must exist in `lazy_core.py` before this phase's lockstep test can import and assert against it.

**Files likely modified:**
- `user/skills/_components/completeness-policy.md` — descope-authoring guidance at resolution sites 1 and 2.
- `user/scripts/test_lazy_core.py` — new lockstep test + `_TESTS` registration.

**Testing Strategy:** Mirror the existing lockstep-test pattern exactly (`test_ruvonly_marker_lockstep_producers_match_ssot`); no new test infrastructure needed. Re-run `python ~/.claude/scripts/project-skills.py` + `lint-skills.py` as the docs-side verification (per this repo's own skills workflow in root `CLAUDE.md`).

**Completion (gate-owned):** the `__mark_fixed__` gate flips `SPEC.md` **Status:** to `Fixed` and writes `FIXED.md` once this phase's tests are green and the mcp-coverage-audit (N/A here — `**MCP runtime:** not-required`) / no-MCP-surface grant clears. No checkbox is authored for this — it is the orchestrator's gate action, not implementation work.

**Integration Notes for Next Phase:** None — this is the final phase. The bug's fix scope (SPEC's 5-item Fix Scope list) is fully covered across these two phases: items 1-2 (marker + shim demotion) and part of item 4 (regression fixtures) land in Phase 1; item 3 (producers) and the remainder of item 4 (lockstep test) land in Phase 2; item 5 (AlgoBooth note) is a documented no-op captured in the Touchpoint Audit table above, not a checkbox.
