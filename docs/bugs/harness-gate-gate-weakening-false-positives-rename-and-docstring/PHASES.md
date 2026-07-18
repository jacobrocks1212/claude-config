# Implementation Phases — harness-gate `gate_weakening` false-positives (rename + docstring/list-literal)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure stdlib Python script (`harness-gate.py`) + its hermetic pytest suite (`test_harness_gate.py`); claude-config has no Tauri/MCP surface, so the whole deliverable is structurally outside MCP reach (docs/tooling class per the mcp-testing untestable taxonomy).

## Validated Assumptions

- **The fix scope already landed out-of-pipeline (verified 2026-07-18).** Every element of the SPEC's `## Fix scope` is present and committed in `user/scripts/harness-gate.py`:
  - **Rename/strengthen guard** — per-file NET test-def count (`removed_test_defs` / `added_test_defs`, `net > 0` gate) at `harness-gate.py:273-297`.
  - **Deny-construct reformat guard** — per-file NET `_DENY_BRANCH_RE` match count (`removed_deny` / `added_deny`, `net > 0` gate) at `harness-gate.py:284-304`.
  - **Docstring exclusion** — `_TRIPLE_QUOTE_RE` skip before the membership check at `harness-gate.py:99-103,312-313`.
  - **Collection-opening requirement** — `_exemption_opens_collection(nearby_line, name)` (assignment/opening-bracket predicate) gating the membership HIT at `harness-gate.py:110-114,320-324`.
  - Provenance: commits `7dd6ad78` (rename/docstring/fixture FPs) and `cf105d9a` (deny-construct reformat FP), both `harden(script)` rounds.
- **The durable regression guarantee already exists and is green (verified 2026-07-18).** `python -m pytest user/scripts/test_harness_gate.py` → **32 passed**. Every FP-false and TP-true fixture the SPEC names is present:
  - FP-false: `test_gate_weakening_renamed_test_def_not_flagged`, `test_gate_weakening_split_test_def_strengthening_not_flagged`, `test_gate_weakening_added_docstring_not_membership`, `test_gate_weakening_bare_triple_quote_line_not_membership`, `test_gate_weakening_fixture_list_near_bare_reference_not_membership`, `test_gate_weakening_reformatted_refuse_call_not_flagged`, `test_gate_weakening_renamed_def_signature_not_flagged`.
  - TP-true (still HITs): `test_gate_weakening_exemption_add_to_real_set_still_hits`, `test_gate_weakening_genuine_test_removal_still_hits`, `test_gate_weakening_removed_refuse_construct_still_hits`, and the pre-existing GAP-2 fixture `test_gate_weakening_gap2_exemption_add_plus_test_deletion`.

Because the implementation and its regression coverage already shipped, this plan carries **one verification phase** — no new production or test code is authored. The executor confirms each fix element is on disk and the suite is green, rather than re-implementing.

### Phase 1: Verify the landed gate_weakening FP fix + confirm regression coverage locks it

**Status:** Complete — verified 2026-07-18 (all fix elements + 7 named fixtures present; suite 32 passed).

**Scope:** Confirm — against the live tree — that the four heuristic tightenings from the SPEC's `## Fix scope` are present in `harness-gate.py::detect_gate_weakening`, that the FP-false and TP-true regression fixtures exist in `test_harness_gate.py`, and that the full suite passes. No code changes: the fix landed via commits `7dd6ad78` + `cf105d9a`; this phase certifies it and locks the regression guarantee that is the bug's honest measurement target (`gate_weakening` has no run-time ledger event, per the SPEC).

**Deliverables:**
- [x] Confirm the rename/strengthen NET-count guard for `def test_*` removals is present (`harness-gate.py` — per-file `removed − added > 0` gate; a 1/1 rename and 1/2 split do NOT HIT, a 1/0 removal still HITs).
- [x] Confirm the deny-construct reformat NET-count guard is present (`_DENY_BRANCH_RE` per-file match counts, `removed > added` gate; a single-line→multi-line `refuse_*(...)` reformat does NOT HIT).
- [x] Confirm the docstring exclusion (`_TRIPLE_QUOTE_RE`) skips a triple-quoted line before the `_LIST_ELEMENT_RE` membership check in `detect_gate_weakening`.
- [x] Confirm the collection-opening requirement (`_exemption_opens_collection`) gates the membership-addition HIT to a DEFINITION/EXTENSION position, so a bare `in`/reference near an exemption name does not trip.
- [x] Confirm all FP-false and TP-true regression fixtures named in the SPEC's "Verified symptom → target signal" section exist in `test_harness_gate.py`.
- [x] Tests: `python -m pytest user/scripts/test_harness_gate.py` passes with every named fixture green (baseline observed 2026-07-18: 32 passed).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_harness_gate.py -q` exits 0 with all FP-false fixtures asserting `gate_weakening` result `pass`/no-hit and all TP-true fixtures asserting a HIT — the deterministic proof the FP class is closed without blunting the true-positive path.

**Runtime Verification** *(checked by running the suite — NOT by the implementation agent):*
- [x] <!-- verification-only --> `python -m pytest user/scripts/test_harness_gate.py` returns exit 0, all tests pass (the FP-false fixtures prove the false positives are gone; the TP-true fixtures prove a genuine weakening still HITs). — VERIFIED 2026-07-18: 32 passed.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; the gate is a deterministic diff checker validated entirely by its hermetic pytest suite.

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/harness-gate.py` — verify only (fix already present at lines 67-114, 255-328); modify ONLY if a confirmation step finds an element absent/regressed.
- `user/scripts/test_harness_gate.py` — verify only (all named fixtures present); modify ONLY if a named fixture is found missing.

**Testing Strategy:** Run the hermetic suite `python -m pytest user/scripts/test_harness_gate.py`. Each FP-false fixture drives a renamed-def / docstring / fixture-near-reference / reformatted-deny diff through `detect_gate_weakening` and asserts no HIT; each TP-true fixture drives a genuine set-growth / test-deletion / deny-removal and asserts a HIT. Green suite = FP class closed, TP path intact.

**Integration Notes for Next Phase:** None — single-phase plan. If the executor finds any fix element or fixture absent (regression since the harden commits), it re-applies the specific SPEC fix-scope element and re-runs the suite before ticking; otherwise this is a pure verify-and-tick phase.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once this phase's runtime verification (the green suite) is confirmed by the validation tail — never authored as a checkbox row here.
