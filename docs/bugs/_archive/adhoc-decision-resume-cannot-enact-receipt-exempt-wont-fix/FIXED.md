---
kind: fixed
bug_id: adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: lint-skills.py --check-projected --check-capabilities; project-skills.py (clean re-projection, spot-checked); lazy_parity_audit.py --repo-root . ; pytest user/scripts/test_lazy_core.py -k "terminal_disposition or split_terminal_statuses" ; NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix` marked fixed on 2026-07-12 by a
skills-lane bug-subagent verification pass. **The fix itself was pre-landed before this pass
started** — see "Pre-landed vs. verified" below. This receipt records the verification trail and
closes this bug's own tracking artifacts (SPEC.md/PHASES.md), which the pre-landing commit's scope
did not touch.

## Root cause (unchanged from SPEC.md, restated for the record)

The decision-resume apply-resolution flow
(`user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`) had no step to set a
terminal `**Status:** Won't-fix`, and its line-197 constraint ("Fixed or Won't-fix must NOT be set
unless a valid FIXED.md receipt exists") blocked receipt-exempt closes — so an operator-chosen
Won't-fix looped forever (neutralize sentinel → re-probe → re-halt on needs-input, forever).

## Pre-landed vs. verified — what this pass did and did not do

**Pre-landed (found on inspection, NOT written by this pass):** commit
`fc5f5371f0992184f3d32374393a3296237f899e` ("harden(dispatch-template): let apply-resolution enact
operator-chosen receipt-exempt Won't-fix close"), authored during the same Round-31 hardening pass
that produced this bug's own SPEC.md, implements this SPEC's entire Fix Scope:

1. `lazy_core._standard_dispatch_bindings` — split the compound `forbidden_status` into additive
   `receipt_gated_status` (`Fixed`/`Complete`) + `receipt_exempt_status` (`Won't-fix`/`Superseded`),
   leaving `forbidden_status` itself unchanged for the other templates that correctly use the
   blanket ban.
2. `dispatch-apply-resolution.md` — added needs-input step **2b (TERMINAL DISPOSITION)**: when the
   operator's resolution directs closing the item toward `{receipt_exempt_status}`, sets
   `**Status:** {receipt_exempt_status}` on SPEC.md; reworded the CONSTRAINTS-section ban to govern
   only the receipt-GATED status and explicitly permit the receipt-EXEMPT close via step 2b.
3. `decision-resume.md` — mirrored the terminal-disposition note into the reference contract.
4. First instance: enacted `**Status:** Won't-fix` on `adhoc-incident-hook-deny-19343d/SPEC.md`.
5. Regression tests in `test_lazy_core.py`: `test_standard_bindings_split_terminal_statuses` +
   `test_apply_resolution_emits_terminal_disposition_close`.

**Verified this pass (no code/prose changes made):**
- Read the full diff of `fc5f5371` and confirmed it maps 1:1 onto this SPEC's five Fix Scope items
  — same root cause framing, same split-token design, same first-instance target.
- Read the current `dispatch-apply-resolution.md` in full: step 2b (lines 42–53) and the reworded
  CONSTRAINTS line (215) are present and read as specified — the receipt-gated ban is narrowed to
  govern only `Fixed`/`Complete`, never permitting them without a receipt; the receipt-exempt close
  is explicitly gated to "when the operator's chosen resolution directs closing."
- Read `decision-resume.md`'s mirrored step 2b — present, matches.
- Read `user/scripts/test_lazy_core.py` ~L33546–33589 — both tests present, asserting against the
  REAL rendered template (`emit_dispatch_prompt(..., template_dir=_REAL_TEMPLATE_DIR)`), not a
  mock; both pass.
- Read `docs/bugs/_archive/adhoc-incident-hook-deny-19343d/SPEC.md` — `**Status:** Won't-fix` is
  present with its `## Resolution` intact, AND the bug is filed under `_archive/`, confirming the
  fix worked end-to-end in the field (the loop the SPEC describes did not re-form; the item reached
  a genuine terminal state and archived cleanly).
- Authored `PHASES.md` for this bug (previously absent) documenting the above as a single
  verification-only phase.
- Flipped this bug's own `SPEC.md` `**Status:**` `Concluded` → `Fixed` — the one artifact the
  pre-landing commit's scope did not include (that commit updated
  `adhoc-incident-hook-deny-19343d/SPEC.md`'s status, not this bug's).

**Scope explicitly NOT expanded:** the dispatch brief for this pass asked to also check
`blocked-resolution.md` / `parked-flush.md` for the identical defect. Both route BLOCKED items
through the same `dispatch-apply-resolution.md` "blocked" section, but that section's own option
menu (Add-a-phase / Defer / Halt / Other) has no "close without a fix" affordance — Won't-fix /
Superseded closes are a needs-input-only concept in this codebase. The shared CONSTRAINTS
section's receipt-exempt permission is deliberately scoped to "the needs-input terminal-disposition
step 2b above," narrower than the blocked path (matching that the blocked path never offers a
close option). A theoretical gap remains if an operator ever directs a close via the blocked path's
"Other" catch-all, but this is **out of this SPEC's Fix Scope** (which named the needs-input path
and `decision-resume.md` only, and stated "Scope is narrow" deliberately) — flagged here as a
discovered-but-unscoped observation, not folded into this fix.

## Symptom reproduction — the concrete before/after contract excerpt

**Before (the gap, per the SPEC's Root Cause — line 197 of the pre-fix
`dispatch-apply-resolution.md`):**

```
- The {forbidden_status} status must NOT be set on any {item_label} doc unless a valid
  {receipt_name} receipt already exists.
```

`forbidden_status` for the bug pipeline was the compound `"Fixed or Won't-fix"` — so this one line
forbade `Won't-fix` exactly as strictly as it forbade `Fixed`, even though `Won't-fix` carries no
receipt by design. An operator-chosen "close as working-as-designed" resolution could only
neutralize `NEEDS_INPUT.md`, never set the terminal status — the bug stayed `Investigating`, and
the next probe re-routed it back into spec-bug → root-cause-trace gate → re-halt on needs-input.
Infinite loop.

**After (the fix, current `dispatch-apply-resolution.md` CONSTRAINTS line + step 2b):**

```
2b. TERMINAL DISPOSITION (receipt-EXEMPT close — enact ONLY when the operator directed it).
   If the operator's chosen resolution is to CLOSE / RETIRE this {item_label} WITHOUT a fix —
   a {receipt_exempt_status} disposition ... — then SET the terminal status on SPEC.md ...
```
```
- The receipt-GATED terminal status ({receipt_gated_status}) must NOT be set on any {item_label}
  doc unless a valid {receipt_name} receipt already exists ... The receipt-EXEMPT terminal status
  ({receipt_exempt_status}) is DIFFERENT ... you MAY set it, but ONLY when the operator's chosen
  resolution directs closing this {item_label} ...
```

The same "close as working-as-designed" resolution now sets `**Status:** Won't-fix` in step 2b
before neutralizing the sentinel — the bug reaches a genuine terminal state and the next probe sees
a closed item, not a re-openable `Investigating` one. **Field evidence:** the triggering bug
`adhoc-incident-hook-deny-19343d` is exactly this scenario, now `**Status:** Won't-fix` and archived
— the loop that motivated this SPEC did not re-form.

## Gates run

- `python user/scripts/lazy_parity_audit.py --repo-root .` → exit 0.
- `python user/scripts/lint-skills.py --check-projected --check-capabilities` → exit 0 ("no broken
  or embedded !cat patterns", "no unexpanded !cat patterns in projected output", "no capability
  namespace pollution detected").
- `python user/scripts/project-skills.py` → clean re-projection (`Skills projected (_default): 88`,
  `Errors (_default): none`, all 3 discovered repos re-projected with 0 errors).
- `pytest`-equivalent targeted run: `test_standard_bindings_split_terminal_statuses` and
  `test_apply_resolution_emits_terminal_disposition_close` in `user/scripts/test_lazy_core.py` —
  both green, asserting on the real on-disk template.

## Files touched

- `docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix/SPEC.md` — `**Status:**`
  Concluded → Fixed.
- `docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix/PHASES.md` — authored (new
  file); single verification-only Phase 1, ticked, `**Status:** Complete`.
- `docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix/FIXED.md` — this receipt
  (new).

No hook, state-script, skill-component, or test file was edited by this pass — the fix (in
`user/scripts/lazy_core.py`, `user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`,
`user/skills/_components/decision-resume.md`, and `user/scripts/test_lazy_core.py`) was already
present from commit `fc5f5371`.

## Cross-lane edits needed but not made

None required to close THIS bug. One observation for a future hardening item (not blocking, not
folded in here): `blocked-resolution.md` / `parked-flush.md`'s "blocked" resolution path shares
`dispatch-apply-resolution.md`'s CONSTRAINTS section but has no equivalent terminal-disposition step
of its own — if an operator ever directs a Won't-fix/Superseded close via that path's "Other"
catch-all, the same class of gap could theoretically recur there. Out of this SPEC's Fix Scope
(deliberately narrowed to the needs-input path); flagged for a possible future
`harden-harness`/adhoc bug item, not acted on in this pass.
