# Producers drop the per-row `<!-- verification-only -->` marker on freehand Runtime Verification rows — Investigation Spec

> The phase-authoring producers (`phases-runtime-verification.md` component, `/spec-phases`, `/add-phase`, `blocked-resolution.md`) mandate the canonical per-row `<!-- verification-only -->` marker (SSOT `lazy_core:_VERIFICATION_ONLY_MARKER`) on every `**Runtime Verification**` `- [ ]` row. But the marker is an invisible HTML comment, and subagents authoring REAL (non-template) verification rows treat it as example scaffolding and DROP it during content substitution. The rows then exempt only via the legacy `_VERIFICATION_SECTION_RE` deprecation shim, firing the `remaining_unchecked_are_verification_only` "verification-only marker absent (un-migrated producer)" `_DIAGNOSTICS` warning. This recurs on files authored AFTER the marker convention landed (2026-06-17), so it is a live producer-compliance gap, not pure legacy debt.

**Status:** Concluded
**Severity:** P3
**Discovered:** 2026-07-23
**Placement:** docs/bugs/verification-only-marker-dropped-on-freehand-rows
**Related:** hardening-log Round 7 (2026-07-06, add-phase per-row marker mandate — the doc-coverage precedent this round supersedes); `harness-hardening-retro-fixes` Phase 2 (the marker-first detector rekey, 2026-06-17)

---

## Verified Symptoms

`lazy-state.py --probe` emits the diagnostic (via `lazy_core.docmodel.remaining_unchecked_are_verification_only` → `_diag`, `docmodel.py:1616-1624`) twice, for two different AlgoBooth features. Reproduced by running the detector over every non-archived AlgoBooth `docs/**/PHASES.md`: SIX files currently fire the "verification-only marker absent (un-migrated producer)" warning because they have unchecked `**Runtime Verification**` rows exempted ONLY by the `_VERIFICATION_SECTION_RE` shim:

- `docs/features/audio/non-windows-audio-hardening/PHASES.md` (created 2026-06-29 — POST-convention)
- `docs/features/audio/polyphonic-parameter-modulation/PHASES.md` (created 2026-05-25 — legacy)
- `docs/features/distribution/cross-platform-distribution/PHASES.md` (created 2026-06-08 — legacy)
- `docs/features/managed-llm-credits/PHASES.md` (created 2026-07-10 — POST-convention)
- `docs/features/mixer/foot-switch-injectors/PHASES.md` (created 2026-05-27 — legacy)
- `docs/features/mixer/motorized-fader-sync/PHASES.md` (created 2026-06-27 — POST-convention)

Concrete evidence that this is a live producer gap, not just legacy debt:
- `motorized-fader-sync/PHASES.md` (created 10 days AFTER the convention landed) has THREE `**Runtime Verification**` subsections (lines 112-114, 151-152, 185+) with ZERO markers — the subagent copied the component's `**Runtime Verification**` header but dropped the per-row `<!-- verification-only -->` on every freehand row.
- `managed-llm-credits/PHASES.md` has the marker on ONE spike row (line 68) but NOT on the sibling rows authored in the same subsection (lines 69-70) — proving the drop happens per-row during content substitution, not wholesale.

## Root Cause

**Class: `ambiguous-prose` (producer-compliance / emission-mechanism fragility).**

The producers already prominently mandate the marker (component banner `phases-runtime-verification.md:127-151`; `spec-phases/SKILL.md:315,347-352`; `add-phase/SKILL.md:247`; `blocked-resolution.md:179-180`) and the marker-first detector is the correct STRUCTURAL design. But the EMISSION MECHANISM they recommend — a per-row HTML comment that must be re-typed on every `- [ ]` row — is fragile against how LLM subagents author: an invisible HTML comment shown on `{placeholder}` template rows reads as example scaffolding and is dropped when the agent substitutes real content. Round 7 already closed the doc-COVERAGE gap (every producer restates the mandate); the recurrence proves prose restatement alone cannot fix an emission-mechanism fragility.

The detector AND the completion-gate autotick BOTH already fully support HEADER-SCOPE marking (a marker on the `**Runtime Verification**` subsection header exempts every row beneath): `docmodel.py:1517,1549-1551,1608`; `gates.py:941,950-951,959-960`. A header-scope marker is authored ONCE on the fixed section-header string the producer controls directly, and survives freehand row authoring — structurally robust against the observed failure mode.

## Fix Scope

Producer-side (claude-config only — Prohibition #1 forbids editing the AlgoBooth target-repo working tree, including its PHASES.md):

1. `user/skills/_components/phases-runtime-verification.md` — emit the marker on the `**Runtime Verification**` HEADER line (header-scope) in the template, and flip the "per-row preferred" guidance (lines 147-150) to recommend header-scope as the robust PRIMARY form (authored once; survives freehand rows), keeping per-row as also-valid. Cite the failure-mode evidence.
2. `user/skills/spec-phases/SKILL.md` — mirror on its inline Phase-N template (`SKILL.md:349-352`).
3. `user/skills/add-phase/SKILL.md` — mirror on its `Verification rows carry the canonical marker` rule (`SKILL.md:247`).
4. `user/skills/_components/blocked-resolution.md` — mirror for the seam-audit subsection header (`SKILL.md:179-180`).

Keep the `_VERIFICATION_SECTION_RE` shim (no-regression back-compat for the many legacy/archived files; removal premature while live files still fire; keeping a shim is not gate-weakening).

Existing AlgoBooth PHASES.md migration: OUT OF SCOPE for the harden agent (target repo). Handed back to the AlgoBooth session as a recommendation with the exact 6-file list; robust migration is a single header-scope marker on each firing `**Runtime Verification**` header.
