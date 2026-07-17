# A `partial` MCP_TEST_RESULTS.md whose only uncovered rows are all test-exempt/deferred has no *authorable* path to VALIDATED.md

**Status:** Concluded
**Class:** product (workflow-contract + gate-semantics fork — operator-owned)
**Date:** 2026-07-17
**Related:** `docs/specs/lazy-validation-readiness/`, `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decisions #2 (Round 45) + #9 (Round 47) — adjacent open observation-gap / partial-VALIDATED forks. Origin: AlgoBooth bugs `sidecar-integrity-gate-blocks-user-modified-sidecar` and `adhoc-hydra-load-code-mcp-tool` (both flagged this class "for a future claude-config harden" in their `NEEDS_INPUT.md`).

## Symptom (verified)

The AlgoBooth bug `sidecar-integrity-gate-blocks-user-modified-sidecar` is fully implemented,
Rust-validated, and pushed; PHASES.md is coherent. Its `/mcp-test` cycle wrote
`MCP_TEST_RESULTS.md` with `result: partial` (pass_count 4 / total 4) whose ONLY two uncovered
Phase-2 verification rows are both legitimately un-MCP-drivable this cycle:
- row 1 — a Tauri command with NO registered MCP-tool mirror ("Cannot Prove" class per
  `docs/features/mcp-testing/SPEC.md`), and
- row 2 — a `Mismatch` branch reachable only against a packaged build ("build-artifact-deferred").

`__write_validated_from_results__` refuses any non-`all-passing` result, so the state machine
loops on mcp-test forever — a D7-test-exempt-completable item can never reach `__mark_fixed__`.

## Root cause (proven)

`ambiguous-prose` + `missing-contract`. A scoped-validated escape hatch **already exists** in the
gate scripts — but there is no *authorable* way to produce the shape it accepts, and the class it
covers is narrower than the observed rows.

1. **The mechanism exists but is undiscoverable to the producer.** `observation_gap_promotable`
   (`user/scripts/lazy_core/gates.py:608`) promotes a `result: partial` to a scoped VALIDATED.md
   (`result: validated-modulo-observation-gaps`) when its `observation_gap_exemptions` list is
   non-empty and EVERY entry carries a non-empty `spec_class`, AND the MCP-driveable scope fully
   passes (`pass_count == total_count`). It is wired to THREE sites — the
   `__write_validated_from_results__` apply gate (`pseudo.py:631`), the completion-integrity gate
   (`gates.py` `evaluate_completion_evidence`), and Step-9 routing — and documented in
   `user/skills/_components/sentinel-frontmatter.md:538-552`.

   BUT the **`mcp-test` SKILL.md** (`repos/algobooth/.claude/skills/mcp-test/SKILL.md`) never
   surfaces it: it teaches `partial` = *"does NOT complete the feature"* (SKILL.md:338) and *"the
   model NEVER authors sentinels — the engine writes them"* (SKILL.md:248). Unaware of the
   mechanism, the AlgoBooth agent invented a `carve_outs:` block (`kind: host-artifact`) instead —
   which is the WRONG block: `carve_outs` softens an *otherwise-all-passing* run
   (sentinel-frontmatter.md:532-537); it does NOT promote a partial. So the apply gate correctly
   refused, and the NEEDS_INPUT authors concluded "no path exists" when a path exists but is
   unreachable from the producer's documented workflow.

2. **No viable authoring path given "engine writes sentinels".** `MCP_TEST_RESULTS.md` is written
   by the deterministic engine (`scripts/mcp-test/run.ts`, in the AlgoBooth target repo — OUT of
   this harness's scope). `observation_gap_exemptions` requires a `spec_class` judgment (which
   uncovered row maps to which documented untestable class) that the engine cannot make. So no
   shipped path ever emits the block; it can only appear if the MODEL amends the engine-written
   results file — which directly contradicts the "model NEVER authors sentinels" invariant. This
   is the real structural gap.

3. **The observed rows are not all the documented observation-gap class.** The mechanism's class is
   narrow: *"no MCP control-API tool exists AND SPEC-locked to the unit/WDIO test tier."* Row 1
   fits. Row 2 ("build-artifact-deferred") does NOT — the assertion IS MCP-driveable; it just needs
   a packaged build absent from the dev session. That is a *deferral* (closer to
   `DEFERRED_REQUIRES_DEVICE.md` / `DEFERRED_REQUIRES_HOST.md`), not a structural observation gap.
   Whether "build-artifact-deferred" qualifies for observation-gap promotion, or needs its own
   disposition, is a gate-semantics/contract question.

## Scope note — the two AlgoBooth bugs are different classes

- `sidecar-integrity-gate-blocks-user-modified-sidecar` IS this class (write-validated deadlock on
  an all-exempt-rows partial).
- `adhoc-hydra-load-code-mcp-tool` is ADJACENT but DISTINCT: it already HAS a `VALIDATED.md`
  (all-passing for its reachability scenario); its blocker is the COMPLETION gate refusing an
  unchecked verification row (row 3) that is genuinely blocked on an EXTERNAL sibling bug (a broken
  hydra `dist` ESM build). That is a true external-dependency block, correctly escalated by its own
  NEEDS_INPUT — not a write-validated defect. Recorded here so the fix is not mis-scoped to cover it.

## Affected area / fix scope (operator-owned)

Candidate designs (surfaced, NOT baked):
- Bless a MODEL-authored (or model-amended) `observation_gap_exemptions` block on the
  engine-written results file — a deliberate carve-out of the "engine writes sentinels" invariant,
  scoped to the exemptions block only; and/or add a claude-config-side emit path that stamps it.
- Decide whether "build-artifact-deferred" is a valid observation-gap `spec_class` or needs a
  distinct partial-completable disposition.
- Surface the escape hatch in the `mcp-test` SKILL.md producer prose (mechanical once the authoring
  contract is decided — folded into the decision because it is only actionable if the model MAY
  author the block).

## Disposition

`NEEDS_INPUT` — see `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #13. Bundles with
open decisions #2 and #9. Not fixed mechanically: the core asks (relax the "engine writes sentinels"
invariant for the exemptions block; classify build-artifact-deferred) are workflow-contract +
gate-semantics forks, and the engine that writes the file is out of harness scope.
