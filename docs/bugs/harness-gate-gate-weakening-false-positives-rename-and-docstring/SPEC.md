# harness-gate `gate_weakening` false-positives on renamed test defs + docstring/list-literal additions

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-17 (recurring — the docstring FP was explicitly noted as a verified false positive in hardening-log Rounds 62-67; Round 67's over-fit note names `test_markers.py: ... membership added: """`)
**Related:** `anti-overfit-design-gate` (`harness-gate.py` — the mechanical design-gate checker); the `/harden-harness` over-fit detector (§Step 3, which shells `harness-gate.py`).

## Trigger

The `gate_weakening` detector (`harness-gate.py::detect_gate_weakening`) is `NEVER judgment-passable` — a HIT routes to operator sign-off (SPEC D4). It false-positives on legitimate, coverage-neutral-or-strengthening edits, forcing the operator (or a harden round) to hand-prove each is spurious. Two recurring shapes:

1. **Renamed test def.** A `def test_old(...)` → `def test_new(...)` rename produces one removed + one added `def test_*`. The detector flags EVERY removed `def test_*` as "gate-test definition removed" WITHOUT checking for a replacement — so a rename (coverage preserved) or a split (coverage strengthened, N removed < M added) trips a HIT.
2. **Docstring / list-literal misread as a membership-set (allowlist/enum) addition.** `_LIST_ELEMENT_RE` (`^\+\s*(['"]).*\1\s*,?\s*$`) matches an added triple-quoted docstring line (e.g. `+    """some text."""` or a bare `+    """`), and the membership check flags it as an `exemption/sanction-set membership added` whenever an `_EXEMPTION_SET_NAMES` token merely appears within the 6-line context window — even a bare REFERENCE (`assert x in SANCTIONED_STOP_TERMINAL`), not a set being grown. Test-fixture list literals near such a reference trip identically.

## Reconstructed route (divergence point)

`detect_gate_weakening` (harness-gate.py ~239):
- removed-line loop: `if _TEST_DEF_RE.match(body): evidence.append("gate-test definition removed")` — no offset against added test defs.
- added-line loop: `if _LIST_ELEMENT_RE.match(plus): if any(name in nearby ...): evidence.append("exemption/sanction-set membership added")` — `nearby = ctx[-6:] + [body]`, a bare substring test with no docstring exclusion and no "is the set actually being defined/extended here" check.

**Divergence point:** the detector keys on the diff SHAPE of a removed test-def line / an added quoted line + a nearby name, without the structural discriminators (net test-def count; docstring exclusion; the exemption name in a collection-OPENING position) that separate a genuine weakening from a rename / docstring / fixture.

## Root cause

**`root_cause_class: script-defect`** — the two heuristics are structurally under-specified:
- the test-def removal check is per-line and replacement-blind, so it cannot see a rename;
- the membership-addition check treats a triple-quote line as a list element and treats any nearby MENTION of an exemption name as proof the set is being grown.

## Fix scope

Tighten `detect_gate_weakening` WITHOUT blunting the true-positive path (Prohibition #2 — a real weakening must still HIT):

- **Rename/strengthen guard.** Aggregate `def test_*` removals vs additions PER FILE. Only emit "gate-test definition removed" for the NET excess (`removed − added > 0`), naming that many. A rename (1/1) or a split (1/2) → no HIT; a genuine removal with no replacement (1/0) → HIT unchanged.
- **Docstring exclusion.** A triple-quoted line (`"""` / `'''`) is never a membership element — skip it before the `_LIST_ELEMENT_RE` membership check (both `detect_overfit` and `detect_gate_weakening` share the element regex; the gate-weakening path is the D4 one that hard-routes to operator, so it is the priority).
- **Collection-opening requirement.** The membership-addition HIT fires only when the exemption set name appears in the nearby context in a DEFINITION/EXTENSION position (an assignment/opening-bracket line: `NAME = {` / `NAME = (` / `NAME = [` / `NAME: T = [` / `NAME = frozenset({`), NOT a bare reference (an `in`/call/import mention). A fixture that only references the name does not trip.
- **Deny-construct reformat guard (near-neighbor, added during this hardening — same net-count mechanism).** The `_DENY_BRANCH_RE` removal check (`refuse_*()` / `exit 3` / `permissionDecision: deny`) is the SAME structural FP as the test-def rename: a construct REFORMATTED single-line→multi-line removes AND re-adds it (coverage-neutral). Apply the identical per-file NET-count: only a net removal (removed matches > added matches) HITs. Surfaced by this very hardening commit, which reformatted `refuse_if_cycle_active(...)` to multi-line and tripped `gate-refusal construct removed` on a construct it did not remove. A genuine deletion (removed, none re-added) still HITs.

## Verified symptom → target signal

- **FP fixtures (must be `gate_weakening_hit: false` after the fix):** (a) a renamed test def (`def test_old` removed + `def test_new` added); (b) an added docstring line near an exemption name; (c) a test-fixture list element near a bare `in`-reference to an exemption name.
- **TP fixtures (must STILL `hit`):** (a) an exemption element appended to an actual `NAME = {` set; (b) a `def test_*` removed with no replacement; (c) a removed `refuse_*(...)` / `exit 3` / `permissionDecision: deny` construct; the existing GAP-2 named fixture (exemption-add + gate-test deletion) still hits.
- No closed ledger-event tracks a `gate_weakening` false positive (the checker is advisory/recording, not a run-time ledger emitter) → the intervention's measurement target is honestly `undeclared`; the durable guarantee is the FP-false / TP-true regression fixtures.
