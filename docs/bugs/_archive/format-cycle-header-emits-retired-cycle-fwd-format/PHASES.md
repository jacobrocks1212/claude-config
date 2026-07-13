# Implementation Phases — format_cycle_header emits the retired heading

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure state-script string-formatting fix, verified via
`pytest user/scripts/test_lazy_core.py` characterization tests. No Tauri/MCP app surface in this
repo.

## Validated Assumptions

- The META dispatch path (`emit_dispatch_prompt`) already emits the sanctioned
  `### {Step} — {summary} [meta {m}]` shape — the established convention this fix mirrors for the
  forward path. Cited directly in the SPEC's Root Cause; re-confirmed on disk during close-out.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. The superseded stub
`docs/bugs/_archive/adhoc-cycle-header-emits-retired-format/` points at this bug as the canonical
owner — no action needed here (it is already `Superseded`/receipt-exempt and archived).

---

### Phase 1: Reshape `format_cycle_header` to the sanctioned T2 forward shape

**Status:** Complete

**TDD:** yes — `test_format_cycle_header_full` / `test_format_cycle_header_missing_fields` pin the
new T2 string shape (were pinned to the retired `### Cycle fwd N/M · meta K · feat · sub_skill`
shape before the fix).

**Deliverables:**
- [x] `format_cycle_header` emits `### {Step} — {summary} [{fwd}/{max}]`:
  - `{Step}` derived from `sub_skill` via a new `SUB_SKILL_STEP_NAMES` map (sibling of
    `DISPATCH_STEP_NAMES`); unmapped → the normalized sub_skill; absent/falsy sub_skill →
    `Cycle`.
  - `{summary}` = `feature_id` or the `—` (U+2014) sentinel.
  - counter `[{fwd}/{max}]`, `?` placeholders when a counter is `None`.
  - `meta_cycles` kept in the signature for back-compat but no longer rendered (meta cycles carry
    their own header via `emit_dispatch_prompt`).
- [x] `test_format_cycle_header_full` / `test_format_cycle_header_missing_fields` updated to the
  new shape.
- [x] Shared `lazy_core` change — both pipelines (`lazy-state.py`, `bug-state.py`) inherit it via
  the shared helper; no coupled-pair script mirror owed (single fix site).
- [x] Retired `· … ·` suffix eliminated; verified no byte-pinned smoke baseline contains
  `Cycle fwd` (no baseline regeneration needed).

**Implementation Notes:** Landed in commit `3404c9e1` ("harden(script): emit sanctioned T2 forward
cycle_header, drop retired format"), the same 2026-07-12 hardening round that authored this bug's
SPEC. This close-out pass authored the missing `PHASES.md` (none existed), verified the fix + tests
on disk, flipped `**Status:**` to Fixed in SPEC.md + PHASES.md, and writes `FIXED.md`. No code
changed in this pass.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k
format_cycle_header -q` → 2 passed, asserting the exact sanctioned-shape strings (not merely
"doesn't crash").

**Runtime Verification** *(pytest characterization — no app runtime in this repo)*:
- [x] <!-- verification-only --> `test_format_cycle_header_full`: full state (feature_id +
  `/execute-plan` sub_skill + all three counters) → exact string
  `"### Implement — audio-engine [2/8]"`. **Verified 2026-07-12** (this close-out pass):
  `python -m pytest user/scripts/test_lazy_core.py -k format_cycle_header -q` → 2 passed.
- [x] <!-- verification-only --> `test_format_cycle_header_missing_fields`: empty state + all
  `None` counters → exact string `"### Cycle — — [?/?]"` (placeholder contract). **Verified
  2026-07-12** — same run, PASS.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP; the function's
return string IS the observable surface, asserted directly by the pytest characterization tests.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `format_cycle_header` reshape + `SUB_SKILL_STEP_NAMES` map (landed
  `3404c9e1`).
- `user/scripts/test_lazy_core.py` — the two characterization tests (landed `3404c9e1`).

**Testing Strategy:** `python -m pytest user/scripts/test_lazy_core.py -k format_cycle_header -q`
targeted, plus the full suite for coupled-pair/parity confidence (this is a shared-helper change,
so both `lazy-state.py --probe --forward-cycles` and `bug-state.py --probe --forward-cycles`
inherit it identically — no separate bug-pipeline test needed, verified via the shared call sites
`lazy-state.py:12722`-area / `bug-state.py:7956`-area cited in the SPEC).

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate is
orchestrator/gate-owned; this close-out pass writes `FIXED.md` directly per the operator's
close-out instruction (provenance: operator-directed-interactive).

**Completion (gate-owned in the normal flow; done directly here per operator instruction):** SPEC.md
/ PHASES.md `**Status:**` flipped to `Fixed`; `FIXED.md` receipt written; bug dir archived.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

None — this PHASES.md was authored retroactively during close-out, after the fix (commit
`3404c9e1`) had already landed and passed gates.
