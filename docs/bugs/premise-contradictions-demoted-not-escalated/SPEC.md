# Premise Contradictions Demoted, Not Escalated — Investigation Spec

> Every pipeline gate audits *downward* (does the plan match SPEC/code anchors?) and none audits *upward* (does contradicting field evidence falsify a SPEC premise?) — so contradicting evidence that was already inside the pipeline three separate times got reconciled into local wrinkles instead of invalidating the wrong premise, which a human reviewer then refuted in one conversation.

**Status:** Fixed
**Fixed:** 2026-07-10 — implemented out-of-pipeline (operator-directed subagent orchestration; fix scope in this SPEC)
**Severity:** P1
**Discovered:** 2026-07-10
**Placement:** docs/bugs/premise-contradictions-demoted-not-escalated
**Related:** 57077 case study, `_components/touchpoint-audit-gate.md`, `user/skills/spec/SKILL.md` (Step 9), sibling bugs `planning-validation-misses-serving-path-and-data-reach`, `external-owner-contracts-locked-without-consultation`

---

## Verified Symptoms

1. **[VERIFIED]** Two `/spec` evidence subagents directly contradicted each other on whether a separate CognitoPay Cosmos exists — subagent 1 affirmed it with citations (`CognitoPayCosmosOptions`, `CosmosClientFactory.CreateCognitoPayClient`, session `878aa447` #70); subagent 2 denied it (#152). The orchestrator adopted the later report wholesale as a SPEC "Premise correction (code-verified)" without re-examining subagent 1's citations. The adopted claim was wrong. — Sessions `878aa447` #70/#152/#160.
2. **[VERIFIED]** The wrong premise was subsequently contradicted three more times in-pipeline and each contradiction was demoted: (a) the CognitoPayout "separate store" wrinkle was synthesized as entity-local (`c78da220` #60); (b) the `/write-plan-cognito` audit found "`CognitoOrder`/`CognitoPayment`/`CognitoDispute`… are `ICosmosEntity` (not `IEntity`) → not swept by `DeleteAllProjectEntities`… may be a no-op" and classified it "mechanical drift correction… none rise to a genuine design fork requiring a halt" (`ed5be46c` #34); (c) the purge snapshot test's own exclusion filter (`typeof(ICosmosEntity).IsAssignableFrom(type)…`, CoreServiceTests:256-257) was read and reported without re-opening the premise (`ed5be46c` #33-region).
3. **[VERIFIED]** A Locked-decision-grade operational claim ("support views via Overwatch") was refuted by evidence gathered later in the same `/spec` session (retained data classified Cosmos-only with no Overwatch mirror, `878aa447` #152/#199) and never reconciled — the v1→v2 re-baseline (Phases 1–2 wasted) landed on exactly this gap. — `878aa447` #78/#80 vs #152/#199.
4. **[VERIFIED]** The human PR reviewer (Taylor) refuted the premise in one review round ("the cosmos entities are not automatically deleted by anything"), forcing corrective Phase 9 to strip dead carve-out code the pipeline had built AND hardened (Phase 6 round-trip tests against a TestStore fiction). — `e6c05b98` #91, PHASES.md:533-616.

## Reproduction Steps

1. Run `/spec` with parallel evidence subagents on a question where two subagents return contradictory factual claims (e.g. "does store X exist?").
2. Observe: no step forces reconciliation of the two reports' cited evidence; the synthesis adopts one (in practice the later/more-confident one) and the SPEC records it as "code-verified".
3. Run `/spec-phases` / `/write-plan` over that SPEC; have an audit agent return a finding that contradicts a SPEC Executive-Summary premise or Locked Decision.
4. Observe: `touchpoint-audit-gate.md` Step E corrects the finding "in the plan itself" (anchor-grade treatment); there is no severity ladder that classifies a premise-grade contradiction as a HALT.

**Expected:** premise-grade contradictions halt planning and re-open the SPEC premise (AskUserQuestion / NEEDS_INPUT); contradictory subagent reports are reconciled against each other's citations before either enters the SPEC.
**Actual:** contradictions are absorbed as plan-local drift corrections or phase-time "trace deliverables"; adoption-of-latest wins between subagents.
**Consistency:** structural — the skill texts contain no premise-escalation provision (skill-audit Q-scan: NO PROVISION).

## Evidence Collected

### Serving-path trace (root cause — `traced`)

```
wrong "code-verified" premise survives into built+hardened code
  → user/skills/spec/SKILL.md — evidence-gathering fan-out has NO reconciliation rule for
      contradictory subagent factual claims (adoption is unconstrained)      ← FIX SITE 1
  → user/skills/spec/SKILL.md:610 (Step 9 "Cross-Boundary Validation") — validates quantities/
      formulas/boundary contracts only; never re-audits Locked Decisions' operational claims
      against the session's own gathered evidence                            ← FIX SITE 2
  → user/skills/_components/touchpoint-audit-gate.md:43 (the "Contradiction:" reporting field)
      and :83 (per-contradiction handling) — every contradiction is corrected *in the plan*,
      with no anchor-grade vs premise-grade classification and no halt path  ← FIX SITE 3
  → downstream gates (spec-phases Step 6 review, write-plan audits) inherit the SPEC premise as
      context in agent prompts, so contradicting findings are reconciled downward
```

Fix-site-on-path: yes — all three sites are the code (skill text) that produced the observed demotions.

## Proven Findings

1. The pipeline is excellent at verifying what it already believes (anchors, symbols, read paths) and structurally blind to premise falsification; the correct answer was inside the pipeline at least three times.
2. "Validated Assumptions" as produced is anchor-drift correction ("not the SPEC's original anchors where they drifted", `ed5be46c` #16) — SPEC Executive-Summary premises were never in the candidate assumption set.
3. The litmus that separates the two grades is: does this finding, if true, change **what** we build (premise) or **where** we edit (anchor)?

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Touchpoint audit | `user/skills/_components/touchpoint-audit-gate.md` | contradiction handling lacks severity ladder |
| Spec skill | `user/skills/spec/SKILL.md` | no subagent-contradiction reconciliation; Step 9 blind to decision claims |
| (read-only consumers) | `spec-phases`, `write-plan*` (inject the component) | inherit the fix via injection — no direct edits |

## Fix Scope (locked with operator, 2026-07-10)

1. **`_components/touchpoint-audit-gate.md` — contradiction severity ladder:** classify every audit contradiction as **anchor-grade** (changes where we edit → correct in the plan, current behavior) or **premise-grade** (contradicts a SPEC Executive-Summary claim, Premise-correction paragraph, Locked Decision, or Validated Assumption → changes what we build). Premise-grade = HALT: interactive → surface and re-open the premise via AskUserQuestion; batch → `NEEDS_INPUT.md`. Demoting a premise-grade contradiction to a phase-time "trace deliverable" is explicitly banned, with the 57077 ICosmosEntity demotion as the named anti-pattern. State the what-vs-where litmus.
2. **`user/skills/spec/SKILL.md` — subagent-contradiction reconciliation rule** (in the evidence-synthesis step): when two evidence reports contradict on a factual claim, adoption is banned; dispatch a targeted reconciler against BOTH reports' specific citations before the claim may enter the SPEC; record the reconciliation in the SPEC ("premise verified against both: …").
3. **`user/skills/spec/SKILL.md` Step 9 — decision-evidence reconciliation pass:** before finalizing, re-audit each Locked/recommended decision's load-bearing operational claims against all evidence gathered in the session; a decision whose claim is refuted or unverified is re-surfaced (it may not silently survive to Final). Name the 57077 "support views via Overwatch" case as the anti-pattern.

## Open Questions

- (none — fix scope locked)
