# Bug: coherence-recovery loop has no terminal when verification rows genuinely never ran

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** e5d9dbab
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-15, item in flight `managed-llm-credits`, AlgoBooth `/lazy-batch`)
**Root-cause class:** `missing-contract` (primary) + `missing-emit-section` (secondary, producer template)

## Symptom (verified)

At `__mark_complete__`, the mechanical third gate (`lazy_core.apply_pseudo` completion-coherence
gate) REFUSES with zero writes on ANY unchecked checkbox in a non-Superseded phase —
verification rows INCLUDED at completion time (deliberate strictness,
`_phase_completion_plan`). The Gate-2 prose (`completion-integrity-gate.md` step 1) EXEMPTS
unchecked verification rows when a validation sentinel (`VALIDATED.md`) is present. So the
orchestrator passes Gate 2, calls `--apply-pseudo __mark_complete__`, and the mechanical gate
refuses those same verification rows.

The mechanical-refusal remedy (`completion-integrity-gate.md` step 3, lines 142-149; wired at
`lazy-batch/SKILL.md` §1c.5 line 560 and `lazy-bug-batch/SKILL.md` line 569) routes a
**coherence-recovery** cycle. When the refusal's residual blocking rows are verification rows
whose verification GENUINELY never ran on this host (no on-disk evidence — infra-gated
behaviours, or a buildable-but-unbuilt `ui_action` scenario), coherence-recovery HONESTLY ticks
nothing and re-scopes nothing (its contract, `dispatch-coherence-recovery.md` step 3, forbids
blind-ticking) and returns to Step 1a. The next probe re-routes `__mark_complete__` → refuse →
coherence-recovery → refuse, **with no terminal / halt**. The loop is bounded only by the
`step_repeat_count >= 3` oscillation tripwire + manual intervention.

**Live case:** `managed-llm-credits` has a partial `VALIDATED.md`
(`result: validated-modulo-observation-gaps`) plus 4 unchecked verification rows across
Phase 1/4/7/8 (live-OAuth JWT-shape capture, credits-proxy reachability smoke, Purchase-CTA
`ui_action`, auto-refill toggle cross-reopen) that never ran on this workstation. The gate's own
refusal advisory says *"per-row host-deferral is an open design question"* and *"migrating a
shim row to the canonical marker lets the gate auto-tick it ONLY when its verification ACTUALLY
ran"*. The run's orchestrator broke the loop MANUALLY by hand-writing `NEEDS_INPUT.md`
(`written_by: completion-integrity-gate`) — the escalation that SHOULD be automatic.

## Root cause

**Primary — `missing-contract`.** The completion-gate refusal remediation loop has NO terminal
for the honest-stuck case. Root cause is NOT the mechanical gate's strictness (intentional,
Prohibition #2 — never weaken it) and NOT the Gate-2 prose exemption (intentional — verification
rows are exempt at the routing check). It is that coherence-recovery, when it can honestly
tick/migrate/re-scope 0 rows AND the only remaining blockers are verification rows that never ran
(0 genuine implementation deliverables), returns a no-op that re-loops instead of ESCALATING. The
DESIGN resolution of the oscillation (per-row host-deferral, corrective-coverage routing,
re-route to `mcp-test`) is already surfaced as operator-owned forks in
`turn-routing-enforcement/NEEDS_INPUT.md` decisions #2/#5/#6 — but until an operator resolves
those, the loop still needs a deterministic SAFE terminal. The safe terminal is the same
`NEEDS_INPUT` escalation `completion-integrity-gate.md` step 4 already owns
(`written_by: completion-integrity-gate`, which `sentinel-frontmatter.md` rule (5) correctly
excludes from provisional auto-accept). This was NEVER wired into the coherence-recovery loop —
prior rounds (33/42) surfaced the design forks but left the loop terminal-less, so the manual
improvisation recurs every time.

**Secondary — `missing-emit-section` (producer template).** `/spec-phases` emits its inline phase
templates (`spec-phases/SKILL.md` lines 315, 349-350) with Runtime-Verification `- [ ]` rows that
LACK the canonical `<!-- verification-only -->` marker
(`lazy_core:_VERIFICATION_ONLY_MARKER`) — even though the SAME skill `!cat`s the correct
`phases-runtime-verification.md` component (which emits the marker, lines 153-154) a few lines
later. The unmarked rows lean on the deprecated `_VERIFICATION_SECTION_RE` header shim (surfaced
4x in this run's probe diagnostics). `write-plan/SKILL.md` (lines 132-134) has the same gap in its
placement-rule prose. Round 7 already closed this for `/add-phase`; `/spec-phases` + `/write-plan`
are the remaining un-migrated producers. This is the DURABLE MARKER-FIRST fix (make the producer
emit the canonical marker), NOT another `_VERIFICATION_SECTION_RE` shim-regex append.

## Fix scope

1. **`dispatch-coherence-recovery.md`** — add a TERMINAL escalation step: after honest
   reconciliation, if the cycle ticked/migrated/re-scoped 0 rows AND the only remaining blockers
   are verification rows lacking on-disk evidence (0 genuine implementation deliverables), the
   cycle writes `{spec_path}/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`,
   cross-referencing decisions #2/#5/#6) instead of returning a no-op — narrowly authorising this
   single sentinel write in this terminal case only. Next probe surfaces `needs-input`; the loop
   terminates deterministically.
2. **`completion-integrity-gate.md`** step 3 — note the routed coherence cycle may ESCALATE to the
   step-4 `NEEDS_INPUT` terminal in the honest-stuck verification-row case (not re-loop).
3. **`lazy-batch/SKILL.md` §1c.5 + `lazy-bug-batch/SKILL.md`** (coupled pair) — note the
   coherence-recovery terminal so the orchestrator does not re-dispatch on the escalation return.
4. **`spec-phases/SKILL.md` + `write-plan/SKILL.md`** — migrate the inline RV-row templates / prose
   to emit the canonical `<!-- verification-only -->` marker, matching the shared component.

**Explicitly OUT of scope (operator-owned, do not bake):** the design resolution of the
oscillation — per-row host-deferral marker (#5), corrective-coverage vs Step-10→mcp-test routing
(#6), what mints a matrix-complete `VALIDATED.md` (#2). This fix only adds the SAFE deterministic
terminal that surfaces those decisions; it never makes completion reachable and never weakens the
gate.
