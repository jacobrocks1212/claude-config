# Phase-Count Circuit Breaker Miscalibrated for Review Rounds — Investigation Spec

> The `/add-phase` phase-count circuit breaker fired 4 times on 57077 and was operator-overridden all 4 times; its only offered remedy (full `/realign-spec` + `/spec-phases` rebuild) is disproportionate during a normal open-PR review round, so the breaker has become a rubber-stamp ceremony — pure friction with no protective effect.

**Status:** Concluded
**Fixed:** 2026-07-10 — implemented out-of-pipeline (operator-directed subagent orchestration; fix scope in this SPEC)
**Severity:** Low
**Discovered:** 2026-07-10
**Placement:** docs/bugs/phase-count-breaker-miscalibrated-for-review-rounds
**Related:** 57077 case study (Phases 8–12 context blocks), `user/skills/add-phase/SKILL.md` (Step 2.5), sibling bug `premise-contradictions-demoted-not-escalated` (source of the middle-remedy this fix offers)

---

## Verified Symptoms

1. **[VERIFIED]** Four fires, four overrides, zero realigns on one feature: Phase 8 (+60%, model itself called it "a *misfire* of the mechanical rule"), Phase 9 (+80%, model called it "a true positive… I've stopped without drafting" — still overridden), Phase 10 (+100%, "override… A full spec rebuild is disproportionate"), Phase 12 (~+140%, "I believe it's a false positive"). — Sessions `0b7e7d8f` #155-159, `e6c05b98` #99-105, `b7828015` #25-27, `7e32d136` #132-134.
2. **[VERIFIED]** `/realign-spec` was named as the recommended path in all four fires and never taken; each override is recorded only as a ⚠ context-block line. — PHASES.md:541, :748.
3. **[VERIFIED]** Phase 12's own context block documents the counting defect: "the heuristic that estimates the original count as the pre-first-corrective prefix undercounts here" — corrective phases interleaved with legitimate design phases inflate the ratio against a stale denominator. — PHASES.md:748.
4. **[VERIFIED]** The expansions that triggered fires 2–4 were sourced from a normal open-PR `CHANGES_REQUESTED` review round (bounded, well-understood asks) — exactly the situation where a full rebuild of a 9/11-complete feature is never the right remedy.

## Reproduction Steps

1. Complete ≥5 phases of a feature; open the PR; receive a normal multi-comment review round.
2. Run `/resolve-review` → `/add-phase` for each corrective phase.
3. Observe Step 2.5 (`add-phase/SKILL.md:69-141`): ratio `(T−O)/O` crosses 0.50 by the second or third review-sourced phase; the breaker STOPs and offers only (a) full `/realign-spec` + `/spec-phases` rebuild or (b) `--override-circuit-breaker`.
4. The operator overrides every time (a rebuild of a nearly-complete, in-review feature is strictly worse); the breaker's signal value decays to zero.

**Expected:** review-round-sourced corrective phases are weighted so a normal review round doesn't trip the breaker, and/or the breaker offers a proportionate middle remedy (a premise re-audit) between "proceed" and "full rebuild".
**Actual:** all-or-nothing remedy priced for decomposition failure fires on routine review response; 4/4 override rate.
**Consistency:** always, mechanically (ratio + threshold are deterministic).

## Evidence Collected

### Serving-path trace (root cause — `traced`)

```
4× fire → 4× override ceremony
  → user/skills/add-phase/SKILL.md:69-141 (Step 2.5)                        ← THE FIX SITE
      • :74-85  O estimated via 4-tier heuristic (pre-first-corrective prefix) — undercounts
                when correctives interleave with design phases (Phase 12's documented case)
      • :90-91  single threshold 0.50, all phases weighted equally — review-round correctives
                count the same as decomposition-failure correctives
      • :103    only remedy offered: "/realign-spec … re-run /spec-phases" (full rebuild)
      • :106    only alternative: --override-circuit-breaker
```

Fix-site-on-path: yes — Step 2.5 authors both the counting rule and the remedy menu.

## Proven Findings

1. The breaker's *detection* concept is sound (it exists because two features expanded 9→19 and 18→30); the miscalibration is in **weighting** (review-sourced correctives) and **remedy granularity** (nothing between proceed and rebuild).
2. A signal overridden 100% of the time protects nothing and trains the operator to rubber-stamp — the next true positive will be overridden too.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Circuit breaker | `user/skills/add-phase/SKILL.md` (Step 2.5, :69-141) | weighting + remedy menu |

## Fix Scope (locked with operator, 2026-07-10)

Recalibrate Step 2.5 in `user/skills/add-phase/SKILL.md` (single writer, single file):

1. **Review-round weighting:** a corrective phase whose source is an open-PR review round (invoked via `/resolve-review`, or the phase description cites PR review comments) counts at **half weight** in the expansion ratio. Keep full weight for correctives sourced from runtime defects, premise reversals, and internal discoveries — those are the decomposition-failure signal the breaker exists for.
2. **Middle remedy:** when the breaker fires, offer three paths (not two): (a) full `/realign-spec` + `/spec-phases` rebuild (unchanged, for genuine decomposition failure); (b) **NEW — premise re-audit**: re-check the SPEC's Locked Decisions / premises against accumulated corrective evidence (the `premise-contradictions-demoted-not-escalated` ladder) without rebuilding phases; (c) override (unchanged, still logged with the ⚠ context-block line).
3. **Denominator note:** record the known undercount mode (correctives interleaved with design phases) next to the O-heuristic so future fires state it honestly (Phase 12's context block wording is the model).
4. Keep the batch (`NEEDS_INPUT.md`) shape and override logging byte-compatible otherwise.

## Open Questions

- (none — fix scope locked)
