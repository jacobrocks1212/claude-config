# Implementation Phases — Step-7 verification-only bypass blind to descoped rows

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a pure-Python
PHASES.md-parsing defect verified via `test_lazy_core.py` (pytest) alone.

**Close-out note (2026-07-12):** the SPEC's own `## Resolution` section already documents that the
instance fix landed via `/harden-harness` (Round 30, commits `0628422` SPEC + `6012c727` fix + 3
regression tests). A subsequent generalization pass (also pre-landed at HEAD:
`32475406 fix(lazy-core): canonical _DESCOPED_MARKER descope marker + shim demotion (part 1)` and
`498a5f02 fix(descoped-row-recognition-needs-canonical-marker): Phase 2 — producers emit the
canonical descope marker + lockstep test`) went further than this SPEC's own Fix Scope required,
shipping the spun-off canonical `<!-- descoped -->` structural marker too. This PHASES.md documents
the pre-landed state against the SPEC's Fix Scope (D1-D3); no new code was written in this pass.

---

### Phase 1: Descoped-in-place row exemption (instance fix)

**Status:** Complete (pre-landed, `6012c727`, per the SPEC's own `## Resolution` section)

**Scope:** Treat an unchecked PHASES.md row that is BOTH markdown-struck-through (`~~...~~`) AND
carries an explicit descope marker (`**DROPPED**`/`**DESCOPED**`/`**WON'T-FIX**`, case-insensitive)
as exempt in `remaining_unchecked_are_verification_only()` — counting it toward the all-remaining-
exempt → `True` return like a Superseded-phase row. Conservative by construction (D1): a plain
unchecked row, or a struck row without a descope marker, still returns `False`.

**Deliverables:**
- [x] `_row_is_descoped_in_place` + `_DESCOPE_STRIKETHROUGH_RE`/`_DESCOPE_MARKER_RE` added to shared `lazy_core.py` (confirmed present: `user/scripts/lazy_core.py:2287-2332` at time of this audit).
- [x] `remaining_unchecked_are_verification_only` wired with the new `saw_descoped_unchecked` flag (confirmed: `:2400-2519`), completion-time strictness (`classify_blocking_unchecked_rows` / `_phase_completion_plan`) deliberately left untouched per D3.
- [x] Regression fixtures registered and green: struck DROPPED note → `True`; plain unchecked → `False`; struck-without-marker → `False`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "verification_only_descoped" -q` is green.

**Runtime Verification:**
- [x] <!-- verification-only --> A struck-through `**DROPPED**` row is the sole remaining unchecked box → `remaining_unchecked_are_verification_only` returns `True` (Step-7 bypass fires, no infinite write-plan loop). **Verified (pre-landed):** `test_verification_only_descoped_dropped_row_is_true` — GREEN.
- [x] <!-- verification-only --> A plain unchecked row, or a struck row lacking a descope marker, still returns `False` (no over-exemption of genuine work). **Verified (pre-landed):** `test_verification_only_plain_unchecked_row_still_false`, `test_verification_only_struck_without_descope_marker_still_false` — GREEN.

**MCP Integration Test Assertions:** N/A — no app runtime surface; pytest is the verification tier.

**Prerequisites:** None (first phase; also the sole phase this SPEC's own Fix Scope requires).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py` (pre-landed; no edits made in this pass).

---

### Phase 2: Generalization — canonical structural descope marker (spun off, landed anyway)

**Status:** Complete (pre-landed, `32475406` + `498a5f02` — beyond this SPEC's own Fix Scope, which explicitly deferred the generalization to a spin-off; documented here for completeness since it landed on the same symbol before this close-out pass)

**Scope:** Per the SPEC's own "Generalization (spun off, not this round)" note, producers now emit
a canonical `<!-- descoped -->` structural marker (mirroring `_VERIFICATION_ONLY_MARKER`); the
free-text `~~...~~ **DROPPED**` form is a deprecation shim, surfaced via a `_DIAGNOSTICS` migration
warning when it — not the canonical marker — is what exempts a row.

**Deliverables:**
- [x] `_DESCOPED_MARKER = "<!-- descoped -->"` canonical marker (confirmed: `user/scripts/lazy_core.py:2294-2315`).
- [x] Row-scope AND header-scope (`section_has_descope_marker`) exemption paths wired.
- [x] Lockstep test asserting producers reference the marker BY VALUE (`test_descoped_marker_lockstep_producer_matches_ssot`).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k descoped_marker -q` is green.

**Runtime Verification:**
- [x] <!-- verification-only --> A row carrying `<!-- descoped -->` (no strikethrough required) is exempt with no migration diagnostic. **Verified (pre-landed):** `test_verification_only_descoped_marker_only_row_is_true`, `test_verification_only_descoped_marker_no_diagnostic` — GREEN.
- [x] <!-- verification-only --> A bold header carrying the marker exempts every row beneath it. **Verified (pre-landed):** `test_verification_only_descoped_header_scope_marker_exempts_rows_beneath` — GREEN.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1.

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py` (pre-landed; no edits made in this pass).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug. Not a checkbox — done out-of-pipeline
this round per `docs/bugs/CLAUDE.md` ("Fixing a bug OUT-OF-PIPELINE").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

Close-out audit (2026-07-12): both phases confirmed landed at HEAD via direct code read. Full
suite: `python -m pytest user/scripts/test_lazy_core.py -q` → 1064 passed.
