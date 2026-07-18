# Planning Validation Misses Serving-Path Reachability and Data Reach — Investigation Spec

> The planning-time runtime-assumption gate classifies sub-facts but never mandates (1) tracing the end-to-end serving path a feature's premise depends on ("can the user even reach the surface?"), or (2) tracing the write-side store binding of each entity a plan retains/deletes ("does the purge actually reach this data?") — producing the 57077 HTTP-500 (Phase 8) and the dead-code carve-outs (Phase 9).

**Status:** Fixed
**Fixed:** 2026-07-10 — implemented out-of-pipeline (operator-directed subagent orchestration; fix scope in this SPEC)
**Severity:** P1
**Discovered:** 2026-07-10
**Placement:** docs/bugs/planning-validation-misses-serving-path-and-data-reach
**Related:** 57077 case study, `_components/phases-runtime-validation.md`, sibling bugs `manual-runtime-gates-unowned-in-no-mcp-workflows`, `premise-contradictions-demoted-not-escalated`

---

## Verified Symptoms

1. **[VERIFIED]** The support-impersonation serving path was traced only up to session synthesis + the CP data read services; nobody traced what the SPA renders after landing on an archived shell. The plan deliberately kept the Plans-module teardown running with no check of what the render path reads from Plans config; the org-home render NRE'd (`PlansService.GetEffectiveSubscription`, PlansService.cs:351) on every support login. — Sessions `c78da220` #50/#60/#64; `0b7e7d8f` #133/#141; PHASES.md:470-532 (Phase 8).
2. **[VERIFIED]** "The support session renders at all on a gutted shell" — the SPEC's central premise, plainly runtime-coupled — was never enumerated as an assumption in the Validated Assumptions block; only its CP-data subset was. The runtime check was deferred to a tail-phase manual gate scoped to the four CP screens. — `c78da220` #64/#112.
3. **[VERIFIED]** For the retention set, no agent ever opened `OrderRepository`/`PaymentRepository`/`DisputeRepository` → `CognitoPayCosmosClient` (the write-side store binding). Reachability-by-purge was answered from entity-class evidence (`[JsonProperty("OrganizationId")]`, `SetPartitionKey`) — "Reachable by purge" — for types the purge cannot reach. The one correct per-entity trace (`PayoutRepository`) happened only because the SPEC pre-flagged that entity. — `c78da220` #51.
4. **[VERIFIED]** The audit prompt asked the right question ("critically — its PARTITION scheme… a differently-partitioned entity may not be reached by it") but the agent answered from entity class files, not the repository binding; the touchpoint audit validated what the VIEWS read thoroughly and what the purge deletes per-entity only for the pre-flagged one. — `c78da220` #51; `s42d69d3d` #484.
5. **[VERIFIED]** Test topology masked the defect: purge unit tests fake the Cosmos repos into the org TestStore, so dead carve-out entries looked load-bearing in tests ("TestStore fiction"). — `e6c05b98` #91/#125; PHASES.md:548.

## Reproduction Steps

1. `/spec-phases` (or `/add-phase`) a feature whose premise is "user category X can view data Y at surface Z" where the plan also degrades shared infrastructure (module teardown, auth, routing).
2. Observe Step 2.7 (`phases-runtime-validation.md`): assumptions get classified code-provable vs runtime-coupled, but no rule forces "X can reach Z at all" into the assumption set, and no rule forces the first phase that mutates the serving path to carry the reachability smoke — the runtime gate lands in a tail phase scoped to the feature's own screens.
3. `/spec-phases` a plan that retains/deletes/migrates a set of entity types.
4. Observe: no rule requires tracing each type's write-side binding (repository → client → store) or verifying the mutation path reaches that store; entity-class evidence passes the audit.

**Expected:** (a) primary-surface reachability is always enumerated as a load-bearing runtime-coupled assumption and its smoke is scheduled no later than the first phase that mutates the serving path; (b) each retained/deleted/migrated entity type carries a store-binding trace, with entity-class evidence declared insufficient; test-vs-prod topology divergence is called out.
**Actual:** both are unprovided; the gate's examples steer at sub-fact granularity (skill-audit Q2/Q3: serving-path trace mandated only for BUG plans via `root-cause-trace-gate.md`; storage topology NO PROVISION).
**Consistency:** structural.

## Evidence Collected

### Serving-path trace (root cause — `traced`)

```
Phase-8 500 + Phase-9 dead carve-outs (two symptoms, one gate)
  → user/skills/_components/phases-runtime-validation.md:1-27               ← THE FIX SITE
      • :8   "For each runtime-coupled, load-bearing assumption" — assumption SET is whatever
             the planner enumerates; no reachability axiom forces the end-to-end serving path in
      • :25  skip-rule keys on "every load-bearing assumption is code-provable" — with the
             serving-path assumption never enumerated, the gate can pass while the premise rides
      • (whole file) no data-reach/write-binding rule; nothing says entity-class evidence
             (interfaces, partition keys, attributes) is insufficient for "the purge reaches it"
  → injected at spec-phases Step 2.7 and add-phase Step 3.5 — both runs executed the gate
      faithfully against an incomplete assumption set (c78da220 #112: sub-facts like the
      CognitoPayoutBalanceTransactions partition were classified; the premise was not)
  → note: the serving-path trace requirement EXISTS for bugs (root-cause-trace-gate.md, SEAM A)
      but is gated to kind: fix-plan — features have no equivalent
```

Fix-site-on-path: yes — the gate component authors exactly the assumption-enumeration behavior that produced both misses.

## Proven Findings

1. The gate's classification machinery is sound; the defect is in what is *forced into* the assumption set (enumeration), not in how assumptions are treated once enumerated.
2. Reachability preconditions ("can the user get to the screen?") were covered by NO automated layer: mocked service tests structurally cannot touch session establishment, and the manual gate was scoped one layer too late.
3. Write-side store binding is a different question from type shape, and the audit answered the former with the latter.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Runtime-validation gate | `user/skills/_components/phases-runtime-validation.md` | missing reachability axiom + data-reach audit |
| (read-only consumers) | `spec-phases` Step 2.7, `add-phase` Step 3.5 | inherit via injection — no direct edits |

## Fix Scope (locked with operator, 2026-07-10)

Extend `user/skills/_components/phases-runtime-validation.md` (single writer; per-repo override form preserved):

1. **Reachability axiom:** "the intended user can reach the feature's primary surface end-to-end" is ALWAYS a load-bearing runtime-coupled assumption — enumerate it explicitly in every plan whose feature has a user-facing surface. When the plan degrades shared infrastructure (module teardown, auth, session, routing), the serving-path reachability smoke must be scheduled no later than the FIRST phase that mutates the serving path — never only in a tail phase scoped to the feature's own screens. Name the 57077 Phase-4/Phase-8 case as the anti-pattern (gate scoped to CP screens; failure at login).
2. **Data-reach audit:** when a plan retains/deletes/migrates a set of entity/data types, each type requires a write-side binding trace (repository → client → store, cited file:line) AND confirmation the mutation path actually reaches that store. Entity-class evidence (interfaces, partition keys, attributes) is declared insufficient — the repository/DI binding is authoritative. Where the test store re-homes entities (topology divergence), the plan must carry an explicit test-vs-prod note ("TestStore fiction" anti-pattern, 57077 Phase 9).
3. Keep both additions inside this component (they fire at spec-phases Step 2.7 and add-phase Step 3.5 automatically); no consumer skill edits.

## Open Questions

- (none — fix scope locked)
