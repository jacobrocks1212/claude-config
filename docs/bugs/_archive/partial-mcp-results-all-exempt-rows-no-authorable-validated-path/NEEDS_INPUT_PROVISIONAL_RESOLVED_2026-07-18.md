---
kind: needs-input
feature_id: partial-mcp-results-all-exempt-rows-no-authorable-validated-path
written_by: harden-harness
divergence: contained
audit_divergence: contained
decisions:
  - "Make the shipped observation_gap_exemptions -> scoped-VALIDATED escape hatch REACHABLE: bless a narrow model-authored exemptions amendment on the engine-written MCP_TEST_RESULTS.md, surface it in mcp-test/SKILL.md, and admit build-artifact-deferred as a spec_class?"
date: 2026-07-17
class: product
next_skill: harden-harness
---

## Decision Context

*Relocated from `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #13
(harden Round 59) into its own provisional-eligible sentinel so it can be
resolved independently of that file's structural/gate-weakening bundle (which
stays a blocking park). Provisionally resolved under the park-provisional
protocol at harden Round 61 — see the `## Resolution` block appended by
`--provisionalize-sentinel`.*

### 1. A `partial` MCP_TEST_RESULTS.md whose only uncovered rows are all test-exempt/build-deferred has no AUTHORABLE path to VALIDATED.md

**Problem:** A fully-implemented, Rust-validated AlgoBooth bug fix
(`sidecar-integrity-gate-blocks-user-modified-sidecar`) with a coherent PHASES.md
produced a `result: partial` `MCP_TEST_RESULTS.md` (pass 4/4) whose ONLY two
uncovered verification rows are each legitimately un-MCP-drivable this cycle —
row 1 a Tauri command with no registered MCP-tool mirror ("Cannot Prove" class),
row 2 a `Mismatch` branch reachable only against a packaged build
("build-artifact-deferred"). `__write_validated_from_results__` refuses any
non-`all-passing` result, so the state machine loops on `/mcp-test` forever and
the item never reaches `__mark_fixed__`.

A scoped-validated escape hatch ALREADY EXISTS — `observation_gap_promotable`
(`user/scripts/lazy_core/gates.py:608`) promotes a `partial` to a
`validated-modulo-observation-gaps` VALIDATED.md when its
`observation_gap_exemptions` list is non-empty with a non-empty `spec_class` on
every entry AND `pass_count == total_count`, wired to the apply gate
(`pseudo.py:631`), the completion gate, and Step-9, documented in
`sentinel-frontmatter.md:538-552`. But three things block reaching it: (a) the
`mcp-test` SKILL never surfaces it — it teaches `partial` = "does NOT complete"
(SKILL.md:338) and "the model NEVER authors sentinels" (SKILL.md:248) — so the
agent invented a `carve_outs:` block (`kind: host-artifact`), which SOFTENS an
otherwise-all-passing run and does NOT promote a partial, and the gate correctly
refused; (b) `MCP_TEST_RESULTS.md` is written by the deterministic engine
(`scripts/mcp-test/run.ts`, in the AlgoBooth target repo — out of harness scope),
which cannot make the `spec_class` judgment the exemptions block requires, so no
shipped path emits it; (c) "build-artifact-deferred" is not the documented
observation-gap class.

**Scope note:** the two AlgoBooth bugs are DIFFERENT classes.
`sidecar-integrity-gate-blocks-user-modified-sidecar` IS this write-validated
deadlock. `adhoc-hydra-load-code-mcp-tool` already HAS a `VALIDATED.md`; its
blocker is the completion gate refusing an unchecked row genuinely blocked on an
EXTERNAL sibling bug (a broken hydra `dist` ESM build), correctly escalated by
its own NEEDS_INPUT — NOT a write-validated defect. The fix must not be
mis-scoped to cover it.

**Why this is provisional-eligible, not a hard-park (`divergence: contained`):**
the promotion gate `observation_gap_promotable` and its refusals are UNCHANGED —
`spec_class` is a free-form non-empty provenance string (not a closed
vocabulary), so admitting `build-artifact-deferred` needs NO gate code change,
and a genuine-failure (`pass < total`) / provenance-less partial STILL refuses.
The change is (i) making an ALREADY-SHIPPED mechanism reachable via `mcp-test`
SKILL prose and (ii) a NARROW, scoped carve-out of the "engine writes sentinels"
workflow discipline (model may add the exemptions block ONLY; counts + result
literal stay engine-owned). Neither removes/softens a gate, threshold, denial, or
validation. It is reversible via prose if the operator prefers option 2.

**Options:**
- **Bless a narrow model-authored `observation_gap_exemptions` amendment + surface it in mcp-test/SKILL.md, admitting build-artifact-deferred as a spec_class (Recommended)** — Permit the model, when the engine writes a `result: partial` whose uncovered rows are all documented-untestable, to amend the engine-written results file's `observation_gap_exemptions` block (each entry `spec_class`-cited) — scoped to that block only. Surface the hatch + the `carve_outs`-vs-`observation_gap_exemptions` distinction in `mcp-test/SKILL.md`, and document `build-artifact-deferred` (MCP-driveable only against a packaged build; Rust-covered, PHASES-classified) as a recognized `spec_class`. Reuses the shipped promotion gate; unblocks the D7-test-exempt-completable class without touching the AlgoBooth engine. The `spec_class` provenance + `pass == total` cross-check + the gate's existing refusals bound the blast radius.
- **Add a claude-config-side emit path** that stamps `observation_gap_exemptions` from structured input (an `--emit-observation-gap` state-script op the cycle drives after the engine run), keeping the model out of the file. Preserves "engine writes sentinels" but adds a new emit surface, and the model still supplies the `spec_class` judgment as input — the same trust question one layer out.
- **Teach the AlgoBooth engine (`run.ts`) to emit exemptions** — OUT of harness scope (target-repo change); listed only to note the boundary.

**Recommendation:** Option 1 — it reuses the shipped promotion gate, needs no
gate code change (`spec_class` is free-form so `build-artifact-deferred` is
already admissible), and is the smallest change that subsumes the observed
instance (`sidecar-integrity-gate-blocks-user-modified-sidecar`) and its near
neighbor (the "Cannot Prove" no-MCP-tool class) without covering the distinct
external-dependency-block class of `adhoc-hydra-load-code-mcp-tool`. The
"engine writes sentinels" relaxation is deliberately scoped to the exemptions
block; the operator owns whether that narrow carve-out is acceptable versus
option 2's out-of-band emit path.

## Resolution

*Recorded on 2026-07-17. Provisionally auto-accepted on recommendation (`--park-provisional` divergence two-key). Ratify or redirect via the provisional-ratification affordance before completion.*

resolved_by: auto-provisional
decision_commit: 15cf1fe6715e96518b6f4d7f518175841d74382b

### 1. 1. A `partial` MCP_TEST_RESULTS.md whose only uncovered rows are all test-exempt/build-deferred has no AUTHORABLE path to VALIDATED.md

**Choice:** Bless a narrow model-authored `observation_gap_exemptions` amendment + surface it in mcp-test/SKILL.md, admitting build-artifact-deferred as a spec_class
**Notes:** Provisionally accepted — divergence graded contained (producer) / contained (input-audit); pending operator ratification.

## Ratification

- **outcome:** ratified
- **decision:** the provisionally-accepted design stands — the narrow model-authored
  `observation_gap_exemptions` amendment on the engine-written MCP_TEST_RESULTS.md, surfaced in
  mcp-test/SKILL.md, with `build-artifact-deferred` admitted as a spec_class.
- ratified_by: operator (AskUserQuestion, 2026-07-18, run wind-down)
- date: 2026-07-18
