# Manual Runtime Gates Unowned in No-MCP Workflows — Investigation Spec

> `/execute-plan` flips phases/plans to `Complete` past unchecked `verification-only` runtime rows on the assumption that a downstream MCP/`__mark_complete__` gate will hold them — but in manual (non-lazy) workflows and no-MCP repos (Cognito) that gate never runs, so "complete" claims ship with the feature's central premise unverified.

**Status:** Fixed
**Fixed:** 2026-07-10 — implemented out-of-pipeline (operator-directed subagent orchestration; fix scope in this SPEC)
**Severity:** P1
**Discovered:** 2026-07-10
**Placement:** docs/bugs/manual-runtime-gates-unowned-in-no-mcp-workflows
**Related:** 57077 case study (`cog-docs/docs/features/57077-cognito-pay-account-deletion/`), `_components/completion-integrity-gate.md`, `_components/phases-runtime-verification.md`, sibling bug `planning-validation-misses-serving-path-and-data-reach`

---

## Verified Symptoms

1. **[VERIFIED]** Phase 4 of 57077 ("In-app support view renders retained CP data (backend + manual)") was marked `✅ Complete (backend) — review PASS, ground-truth verified` with its manual Overwatch `:7775` runtime-verification checkboxes never run. — Session `036a133f` #120–#131; PHASES.md:217-264.
2. **[VERIFIED]** The run's final summary told the operator "**With this, the feature is complete across all 5 phases**", with the pending manual gate relegated to a trailing footnote ("Two items remain owned by your manual testing"). — Session `036a133f` #188.
3. **[VERIFIED]** Two days later the operator's first manual test hit HTTP 500: a support user impersonating the archived org could not load the org home page (`NullReferenceException` in `PlansService.GetEffectiveSubscription`, PlansService.cs:351, via `CognitoAuthorizeAttribute.CheckAuthorization`). The skipped manual walkthrough was exactly the step that would have caught it. Corrective Phase 8 was required. — Session `0b7e7d8f` #3, #133, #155; PHASES.md:470-532.
4. **[VERIFIED]** Five phases completed across two same-day sessions with zero manual verification anywhere in the chain; later phases built on Phase 4's unverified completion. — Sessions `8cb51ab5` (Phases 1–3), `036a133f` (Phases 4–5).

## Reproduction Steps

1. In a repo whose plans declare `MCP runtime: not-required` (e.g. Cognito Forms), author a plan whose phase carries `<!-- verification-only -->` / `**Runtime Verification**` manual rows.
2. Run `/execute-plan` on that plan manually (not via `/lazy-batch`).
3. Observe at Step 4: the plan frontmatter flips `Ready → Complete`, the phase status line is stamped `✅ Complete`, and the final summary leads with a completion claim.

**Expected:** completion output leads with "N MANUAL RUNTIME GATES PENDING — feature not verified end-to-end"; a durable ledger of pending gates exists; nothing reads as "done".
**Actual:** completion framing leads; pending rows are a footnote with no consequence attached; no ledger, no aggregation, no PR-time surfacing.
**Consistency:** always — this is the skill's written contract, not a deviation.

## Evidence Collected

### Serving-path trace (root cause — `traced`)

The false "complete" claim is served by this chain:

```
"feature is complete" claim (final summary + PHASES status line + plan frontmatter Complete)
  → user/skills/execute-plan/SKILL.md:201  ← "A runtime/MCP-validation gate is NOT unfinished
      plan work — flip to `Complete` anyway. … Leave the verification row itself UNCHECKED in
      PHASES.md (`/mcp-test` ticks it); remaining_unchecked_are_verification_only() recognizes
      the remainder and advances."                     ← THE FIX SITE (assumption of a downstream owner)
  → the assumed owners never run in this workflow:
      • /mcp-test — repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md ("No MCP
        integration test step"; plans declare `MCP runtime: not-required`)
      • __mark_complete__ / completion-integrity-gate — user/skills/_components/
        completion-integrity-gate.md:29-35 treats verification-only rows as a carve-out that
        PERMITS completion, and only executes inside the /lazy* pipeline, which this manual
        /execute-plan workflow never enters (SPEC.md for 57077 still reads `Status: Draft`)
  → repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md:228-262
      (Part Completion) — Tier 2 build/test gate only; no aggregation or surfacing of pending
      manual/runtime rows for feature work (bug fixes get a symptom gate at :237; features get nothing)
```

Fix-site-on-path: yes — the completion behavior is authored at `execute-plan/SKILL.md:201` (generic) and `execution-contract-cognito-lanes.md:228-262` (Cognito part completion); both are on the chain that produces the false claim.

### Runtime evidence
- `036a133f` #120 review PASS rationale was entirely unit-level (`/mstest` 533/533, git-status/wc/grep integrity, assertion-vs-intent) — nothing runtime.
- `0b7e7d8f` #155/#169: the model itself named the causal link twice ("Phase 4 was marked '✅ Complete (backend)' but its manual Overwatch runtime-verification checkboxes were never checked — and that manual step is exactly what would have caught [this]").

## Proven Findings

1. The completion-integrity chain broke at a **workflow seam, not dishonesty**: every artifact honestly noted the unchecked rows, but the only enforcement mechanism for `verification-only` rows lives in a pipeline this workflow never invokes. The rows had a named owner ("owned by Jacob") but no mechanism.
2. There is **no aggregation** of pending manual gates anywhere: not at phase completion, not at run end, not at PR authoring. The headline claim semantically overrides the footnote.
3. The generic skill's advice is correct **for the lazy pipeline** (leaving the plan In-progress would loop `lazy-state.py`); the defect is that the same text governs manual/no-MCP runs where the compensating gate is absent.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Generic executor completion | `user/skills/execute-plan/SKILL.md` (Step 4, line ~201) | authors the unconditional Complete flip |
| Cognito part completion | `repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` (:228-262) | no pending-gate surfacing for feature work |
| New shared component | `user/skills/_components/pending-runtime-gates.md` (NEW) | the fix vehicle |

## Fix Scope (locked with operator, 2026-07-10)

1. **New component `user/skills/_components/pending-runtime-gates.md`:** at completion time, enumerate every unchecked `<!-- verification-only -->` / Runtime-Verification row across the executed phases; write/update a `RUNTIME_GATES.md` ledger in the feature dir (row text, how to run it, owning phase, date deferred); the final summary MUST lead with `N MANUAL RUNTIME GATES PENDING — feature not verified end-to-end` before any completion language; phase status-line wording gains `— RUNTIME GATES PENDING (N)`.
2. **Inject into `/execute-plan` Step 4:** keep the Complete flip (lazy-pipeline correctness) but make the ledger + summary-ordering mandatory. When the plan/repo declares `MCP runtime: not-required` (no downstream owner), state explicitly in the summary that the ledger is the ONLY owner of these rows.
3. **Inject into the Cognito Part Completion contract** (`execution-contract-cognito-lanes.md`): same ledger + leading-summary contract for feature parts (bug parts already have the SEAM B symptom gate at :237).
4. Do NOT change `completion-integrity-gate.md` / `lazy_core.remaining_unchecked_are_verification_only()` semantics — the lazy pipeline's carve-out is correct because `/mcp-test` + the validation sentinel own the rows there. This fix is additive for the manual seam only.

## Open Questions

- (none — fix scope locked; PR-time surfacing of `RUNTIME_GATES.md` by `/write-pr-description` is a nice-to-have follow-up, deliberately out of scope here)
