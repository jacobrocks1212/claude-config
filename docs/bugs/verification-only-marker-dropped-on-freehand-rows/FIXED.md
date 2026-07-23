---
kind: fixed
feature_id: verification-only-marker-dropped-on-freehand-rows
date: 2026-07-23
provenance: backfilled-unverified
validated_via: pytest (user/scripts/tests/test_lazy_core/) 1356 passed + test_hooks.py 288/288 + both state scripts' --test + bug-state --fsck; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`verification-only-marker-dropped-on-freehand-rows` marked Fixed on 2026-07-23 during an inline
manual `/harden-harness` invocation (no lazy cycle marker). This receipt was written by the
harden agent, not the bug pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`.

Fix commit: `02993fc0` (`harden(skill-prose): recommend header-scope verification-only marker`).
Bug spec commit: `4ee9b9be`. Hardening-log: Round 145 (2026-07).

## Notes

Root cause was producer emission-mechanism fragility: the per-row `<!-- verification-only -->`
HTML comment is dropped by subagents when substituting real content over the phase templates'
placeholder rows, so `**Runtime Verification**` rows exempt only via the legacy
`_VERIFICATION_SECTION_RE` shim and fire the "verification-only marker absent (un-migrated
producer)" diagnostic. Fixed by making HEADER-SCOPE marking (the marker on the fixed
`**Runtime Verification**` header string, authored once, surviving freehand row authoring) the
robust PRIMARY emission form across `phases-runtime-verification.md`, `spec-phases/SKILL.md`,
`add-phase/SKILL.md`, and `blocked-resolution.md` — keeping per-row as also-valid. The detector
(`remaining_unchecked_are_verification_only`) and the completion-gate autotick
(`autotick_verification_rows`) already fully supported header-scope, so no gate/detector code
changed; this closes the authoring side. Regression `test_ruvonly_producer_emits_header_scope_marker`
pins the template header carries the marker AND the detector exempts unmarked rows beneath it.

The `_VERIFICATION_SECTION_RE` deprecation shim is deliberately KEPT (no-regression back-compat
for the 50+ legacy/archived PHASES.md; removal premature while live files still fire).

Migration of the six currently-firing AlgoBooth PHASES.md (target-repo working tree — out of
scope for the harden agent per Prohibition #1) was handed back to the AlgoBooth session as a
recommendation: add a header-scope `<!-- verification-only -->` marker to each firing
`**Runtime Verification**` header.

Verification: `python -m pytest user/scripts/tests/test_lazy_core/ -q` → 1356 passed;
`python user/scripts/test_hooks.py` → 288/288; `lazy-state.py --test` / `bug-state.py --test` OK;
`bug-state.py --fsck` → ok:true, no violations.
