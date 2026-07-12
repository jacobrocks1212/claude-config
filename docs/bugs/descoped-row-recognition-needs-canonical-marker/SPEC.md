# Descoped PHASES rows need a canonical structural marker (free-text DROPPED form is a shim) — Investigation Spec

> `remaining_unchecked_are_verification_only()` recognizes a deliberately-dropped PHASES
> deliverable only when it is struck through AND tagged with one of THREE hardcoded free-text
> keywords (`DROPPED`/`DESCOPED`/`WON'T-FIX`). That keyword set is an over-fit shim on a symbol
> whose "not-to-be-done row unrecognized" class has recurred 4+ times; the durable fix mirrors the
> `_VERIFICATION_ONLY_MARKER` precedent — producers emit a CANONICAL STRUCTURAL descope marker and
> the free-text form becomes a deprecation shim.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-12
**Placement:** docs/bugs/descoped-row-recognition-needs-canonical-marker
**Related:** `docs/bugs/verification-only-bypass-blind-to-descoped-rows` (the ORIGIN — this item is that bug's explicitly front-enqueued "over-fit generalization" spin-off; its Resolution names this slug and its Fix-Scope "Generalization" paragraph is this SPEC's charter). Canonical-marker precedent this bug follows: `lazy_core.py:_VERIFICATION_ONLY_MARKER` (structural marker) + `_VERIFICATION_SECTION_RE` (retained deprecation shim + migration-gap diagnostic), documented in `user/scripts/CLAUDE.md` → "Verification-only canonical marker". Same recurring class in `docs/specs/turn-routing-enforcement/hardening-log/` (Rounds 24/25/30 + recording-panel round).

---

## Verified Symptoms

<!-- This is a harness self-improvement (over-fit spin-off), not a live user-reported failure.
     The predecessor bug's live symptom is the reproducible surface; the generalization symptom
     is the recurrence risk the shim leaves open. Both are cited, not user-confirmed (batch). -->

1. **[REPORTED]** A fully-implemented feature/bug whose SOLE remaining unchecked PHASES row is a deliberately-dropped deliverable loops `/write-plan` forever — UNLESS the descope note happens to use one of the three hardcoded keywords. Live instance of the recognized case: `live-settings-split-brain-disarms-enforcement-plane` PHASES line 128, 2026-07-12 (predecessor bug's Verified Symptom).
2. **[REPORTED]** The recognition vocabulary is a fixed keyword set (`_DESCOPE_MARKER_RE`, `lazy_core.py:2259` — `DROPPED`/`DESCOPED`/`WON'T-FIX`). A semantically-equivalent descope note authored with different phrasing (`**REMOVED**`, `**CUT**`, `**N/A**`, `**not doing this**`, a bare struck row with a prose reason) is NOT recognized, so the identical infinite-`/write-plan` loop recurs on the un-covered phrasing — source-verified by reading the regex alternation (closed set, no marker fallback).
3. **[REPORTED]** Over-fit signals both present, matching the precedent's promotion criteria: (signal 1) the detector is a keyword set rather than a structural marker; (signal 2) the "Step-7 bypass returns `False` on a genuinely-not-to-be-done row it does not recognize" class has recurred repeatedly on this exact symbol (hardening-log Rounds 24 reachability-smoke, 25 seam-audit, 30 descope-in-place, + the recording-panel round). Two-signals-present is exactly what promoted `_VERIFICATION_SECTION_RE` (free-text header regex) to the `_VERIFICATION_ONLY_MARKER` structural marker.

## Reproduction Steps

1. Author a PHASES.md for an otherwise-complete item (all phases `**Status:** Complete`, all implementation plan parts `status: Complete`, SPEC `Concluded`/pre-`__mark_fixed__`) whose sole remaining unchecked box is a deliberately-dropped deliverable using a descope phrasing OUTSIDE the hardcoded set, e.g.:
   ```
   - [ ] ~~`setup.py` gains the parallel live check~~ **REMOVED** (decision 2, NEEDS_INPUT resolution): scope note only — no code deliverable here.
   ```
2. Run the router: `python3 user/scripts/bug-state.py --repo-root <repo>` (or `lazy-state.py` for a feature). `find_implementation_plans` filters out the `Complete` parts (`plans == []`), so the Step-7 bypass is gated on `remaining_unchecked_are_verification_only(phases_text)`.
3. Observe the route: the helper returns `False` (the `**REMOVED**` marker is not in `_DESCOPE_MARKER_RE`, the row is not verification-marked, not Superseded), so the `elif not plans:` branch dispatches `/write-plan` on an already-done item.

**Expected:** any deliberately-dropped-in-place deliverable — regardless of the exact descope word — is recognized as not-to-be-done and counts toward the "all remaining unchecked are exempt → `True`" bypass, so the router falls through to the completion tail instead of looping `/write-plan`.
**Actual:** only the three hardcoded keywords are recognized; any other descope phrasing falls through to the `return False` implementation-row path → no-progress `/write-plan` loop (`repeat_count`/`step_repeat` climb toward a false `LOOP DETECTED` / max-cycles halt).
**Consistency:** deterministic — a pure function of the row text vs. the closed keyword regex.

## Evidence Collected

### Source Code

Serving-path trace (surface → source), each hop cited `file:line`:

```
surface: Step-7 route dispatches /write-plan on an already-done item (no-progress loop)
  → lazy-state.py / bug-state.py  Step-7 `elif not plans:` branch, gated on
        remaining_unchecked_are_verification_only(phases_text)     (bug-state.py ~:1452 + lazy-state.py mirror)
  → lazy_core.remaining_unchecked_are_verification_only            lazy_core.py:2287 (def) … :2456
        (return saw_unchecked or saw_superseded_unchecked or saw_descoped_unchecked)
  → the descope-recognition branch                                 lazy_core.py:2423
        (if _row_is_descoped_in_place(stripped): saw_descoped_unchecked = True; continue)
  → _row_is_descoped_in_place                                      lazy_core.py:2265
        (requires BOTH _DESCOPE_STRIKETHROUGH_RE AND _DESCOPE_MARKER_RE)
  → _DESCOPE_MARKER_RE                                             lazy_core.py:2259 ← FIX SITE
        r"\*\*\s*(?:DROPPED|DESCOPED|WON['’]?T[-\s]?FIX)\s*\*\*"  — the over-fit closed keyword set
```

The block at `lazy_core.py:2253-2257` already SELF-DOCUMENTS the shim status and the durable fix:
> "OVER-FIT NOTE: the descope-marker vocabulary below is a keyword set; the durable fix is a CANONICAL STRUCTURAL descope marker emitted by producers (parallel to `_VERIFICATION_ONLY_MARKER`, with this free-text form retained as a deprecation shim like `_VERIFICATION_SECTION_RE`). That generalization is spun off as its own item — until it lands, this is the free-text shim."

Canonical precedent to mirror (`lazy_core.py:2170-2212`): `_VERIFICATION_ONLY_MARKER = "<!-- verification-only -->"` (per-row HTML comment, invisible in rendered markdown, header-text-independent) is the PRIMARY detector; `_VERIFICATION_SECTION_RE` is retained ONLY as a deprecation shim that appends a `_DIAGNOSTICS` warning naming the un-migrated subsection each time the regex (and not the marker) is what exempts a row, so the migration gap is VISIBLE and a future cycle can retire the regex once the shim stops firing. A lockstep test (`test_ruvonly_marker_lockstep_producers_match_ssot`) asserts producer prose == the SSOT constant.

Producers of descope-in-place rows (who must emit the new marker): unlike verification rows (mechanically emitted by `_components/phases-runtime-verification.md` + `_components/blocked-resolution.md`), descope-in-place rows are authored ad hoc during PHASES editing — primarily at `NEEDS_INPUT.md`-resolution time (the live instance's provenance) and under the `_components/completeness-policy.md` descope-decision path (`class: scope`). The related-but-distinct `- [~] ~~...~~ — superseded` form emitted by `/add-phase` (`user/skills/add-phase/SKILL.md:263-272`) is a SEPARATE axis already handled by `in_superseded_phase`/`saw_superseded_unchecked`; it is NOT this bug's target.

### Runtime Evidence

None required. The defect is a pure deterministic string-recognition function; the trace above is fully established by static read (no timing/ordering/cache/environment coupling). The predecessor's live instance (`live-settings-split-brain-disarms-enforcement-plane`, 2026-07-12) is the runtime confirmation that the loop symptom is real for an unrecognized descope row.

### Git History

Predecessor instance fix shipped via `/harden-harness`, hardening-log Round 30: spec at `0628422`, fix + 3 regression tests at `6012c72` (added `_row_is_descoped_in_place` + `_DESCOPE_STRIKETHROUGH_RE`/`_DESCOPE_MARKER_RE` + the `saw_descoped_unchecked` flag). This SPEC is the deferred generalization that fix explicitly front-enqueued.

### Related Documentation

- `user/scripts/CLAUDE.md` → "Verification-only canonical marker (harness-hardening-retro-fixes Phase 2)" — the full template this generalization follows (structural marker + deprecation shim + migration diagnostic + producer lockstep test + `check-docs-consistency.ts` row-annotation note).
- `docs/bugs/verification-only-bypass-blind-to-descoped-rows/SPEC.md` — the origin; its "Generalization (spun off, not this round)" paragraph is this SPEC's charter.

## Theories

### Theory 1: Over-fit keyword set on a recurrence-prone symbol; canonical structural marker is the durable fix
- **Hypothesis:** recognizing descope-in-place rows by a hardcoded keyword alternation leaves the exact "unrecognized not-to-be-done row loops `/write-plan`" class open for every phrasing outside the set; the recurrence-proven durable fix (already validated on the sibling verification-row axis) is a structural marker.
- **Supporting evidence:** the source self-documents this (`lazy_core.py:2253-2257`); the class has recurred 4+ times on this symbol; the `_VERIFICATION_ONLY_MARKER` precedent solved the byte-identical problem shape.
- **Contradicting evidence:** none. The keyword set is conservative (requires BOTH strikethrough and marker) so it never over-exempts genuine work — but that conservatism does not close the under-recognition gap.
- **Status:** Confirmed.

## Proven Findings

**Root cause (`traced`, `script-defect`).** The descope-in-place recognition in `lazy_core.py` keys on a closed free-text keyword set (`_DESCOPE_MARKER_RE`, `:2259`) instead of a structural marker. The serving path from the looping-`/write-plan` surface to that regex is traced above (each hop `file:line`), and the fix site (`_DESCOPE_MARKER_RE` / `_row_is_descoped_in_place` recognition + the producers that author descope rows) lies ON that path — the marker string the fix introduces is exactly the value `_row_is_descoped_in_place` reads on the way to producing the `saw_descoped_unchecked` exemption. `symptom-verified` ≠ `cause-traced` is satisfied: the cause is `traced` (not `asserted`), and the claim is not runtime-coupled (deterministic string matching, no runtime artifact owed).

**Fix scope (Concluded — for `/plan-bug`):**

1. **Add a canonical structural descope marker** in `lazy_core.py`, mirroring `_VERIFICATION_ONLY_MARKER`: a per-row HTML comment SSOT constant (proposed `_DESCOPED_MARKER = "<!-- descoped -->"`, invisible in rendered markdown, phrasing-independent). Make `_row_is_descoped_in_place` (or the branch at `:2423`) treat the marker as the PRIMARY exemption signal — a row carrying it (or under a header carrying it) counts toward the bypass regardless of the free-text word used.
2. **Demote `_DESCOPE_MARKER_RE` (+ `_DESCOPE_STRIKETHROUGH_RE`) to a deprecation shim**, parallel to `_VERIFICATION_SECTION_RE`: retain it so un-migrated PHASES.md keeps exempting cleanly (no regression), but when the free-text form (not the marker) is what exempts a row, append a `_DIAGNOSTICS` warning naming the un-migrated row/subsection so the migration gap is VISIBLE (a future cycle retires the shim once it stops firing).
3. **Producers emit the marker.** Update the descope-authoring surfaces — `_components/completeness-policy.md` (the `class: scope` descope path) and the `NEEDS_INPUT.md`-resolution PHASES-edit guidance — to author the canonical marker on each dropped row, referencing the SSOT constant BY NAME (never re-hardcoding the string). Add a lockstep test asserting producer prose == the SSOT constant (the `test_ruvonly_marker_lockstep_producers_match_ssot` analog).
4. **Regression fixtures** in `test_lazy_core.py`: marked descoped row → `True`; legacy struck `**DROPPED**` (shim) → `True` + a migration diagnostic; plain unchecked row → `False`; struck row without marker-or-keyword → `False` (conservatism preserved — never over-exempt genuine work).
5. **`check-docs-consistency.ts` (AlgoBooth sibling):** the marker is a ROW ANNOTATION, not a sentinel — like `_VERIFICATION_ONLY_MARKER` it does NOT enter `SENTINEL_SCHEMAS`; note the same fallback (if that validator can't handle the HTML-comment form, fall back to a canonical form and re-sync the constant + producers).

Shared `lazy_core` helper, so BOTH pipelines inherit the fix (parity-audited); the completion-time gate (`_phase_completion_plan`/`classify_blocking_unchecked_rows`) is out of scope this round exactly as in the predecessor (the loop is at mid-item routing, not completion).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Descope recognition (SSOT) | `user/scripts/lazy_core.py` (`_DESCOPE_MARKER_RE` :2259, `_row_is_descoped_in_place` :2265, `remaining_unchecked_are_verification_only` branch :2423) | Add structural-marker primary detector; demote keyword regex to shim + migration diagnostic |
| Producers | `user/skills/_components/completeness-policy.md`, NEEDS_INPUT-resolution PHASES-edit guidance | Emit the canonical marker by name on each dropped row |
| Tests | `user/scripts/test_lazy_core.py` | Marker/shim/conservatism fixtures + producer-lockstep assertion |
| Sibling validator (note only) | AlgoBooth `scripts/check-docs-consistency.ts` | Row-annotation, not a sentinel — no schema change expected |

## Open Questions

- **Marker string form** (`<!-- descoped -->` per-row HTML comment vs. a canonical subsection-header form) — design detail, resolvable at `/plan-bug`. The precedent's Open Question 2 already resolved the analog toward the per-row HTML-comment form for header-text-independent robustness; recommend mirroring it. Not a product-behavior fork (both forms yield identical recognition end-state).
- **Header-scope vs. row-scope** for the marker (does a marker on a `**Descoped:**` subsection header exempt every row beneath it, as `_VERIFICATION_ONLY_MARKER` does?) — recommend mirroring the precedent (support both). Resolvable at `/plan-bug`.
