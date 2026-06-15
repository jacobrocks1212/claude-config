# Buddy Guidance Enhancement — Feature Specification

> Restructure how `review-pr-buddy` partitions a PR and guides an expert reviewer through it, grounded in research-backed best practices for code review and expert cognition — defeating anchoring/automation bias, respecting empirical cognitive ceilings, and capturing severity-weighted judgments.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-15

**Depends on:**

- cognito-pr-review-v2 — composes — extends the journey-file Manual Review Guide (partitioning) and the buddy walk loop (guiding) defined in that spec

---

## Executive Summary

The `cognito-pr-review` plugin's interactive `review-pr-buddy` command walks one experienced reviewer through a PR chunk-by-chunk. Gemini Deep Research (see `RESEARCH.md` / `RESEARCH_SUMMARY.md`) evaluated our two design surfaces — **partitioning** (`agents/journey-planner.md`) and **guiding** (`commands/review-pr-buddy.md`) — against the empirical literature and found our current per-chunk loop is **ordered backwards for an expert**: it front-loads teaching (expertise-reversal harm) and shows automated findings before the reviewer forms an independent judgment (anchoring + automation bias), steering the expert toward the shallow issues the tool caught and away from the deep logic bugs LLM analysis inherently misses ("Abstraction Bias," NDSS 2026; RevMate ~7–8% direct acceptance, Mozilla/Ubisoft).

This enhancement restructures the buddy walk into a **two-pass loop** (independent read → reconciliation against tool findings), scales teaching to chunk complexity, replaces the disposition verbs with a **severity taxonomy**, and re-bases partitioning on **behavioral/dependency clustering** with tests bundled alongside the code they exercise, a **hard 400-LOC chunk-split rule**, and **perspective-based, predictive Socratic prompts**. All changes are prompt-level edits to two files plus a `buddy-session.json` schema bump — no new tooling and no change to the prep/finding-generation pipeline.

## Scope

**In scope (v1):**
- Partitioning strategy in `journey-planner.md`: review unit, ordering, chunk-size cap, per-chunk persona + questions, test placement.
- Guiding methodology in `review-pr-buddy.md`: the per-chunk interaction loop, teach policy, finding-reveal timing, disposition model.
- `buddy-session.json` schema update to carry severities and independent-read observations.
- Curated-synthesis (Phase 2) mapping of severities to the synthesizer-v2 section tiers.

**Optimization target:** thorough defect detection for an experienced senior engineer (Jacob). Speed/friction is secondary; novice onboarding is explicitly *not* a v1 target.

**Out of scope (v1):**
- The autonomous `/review-pr` finding-generation agents (investigation/sweep/reuse) — their *output* is consumed but their behavior is unchanged.
- Deterministic AST/data-flow untangling tooling (SmartCommit-style). Behavioral clustering is done at the prompt level by the Opus journey-planner; deterministic tooling is a possible future Tier-2 follow-up.
- The weight/calibration system and prep/caching mechanics.
- Session-time pacing/fatigue enforcement (60-min ceiling, break prompts) — deliberately **dropped** for a solo expert (see Decision 6).

## Background — current behavior

**Partitioning (`journey-planner.md`):** Manual Review Guide emits ordered `### Step N: {Group}` chunks grouped "logically, not by directory," **core-first/tests-last**, each with Files / What to look for / Key questions. Tests are a separate "after core" group.

**Guiding (`review-pr-buddy.md` Phase 1):** per-chunk loop = **Teach → Surface Findings → Socratic Prompt → Capture Verdict (keep / dismiss / will-comment / add-own) → Checkpoint → Advance.**

## Technical Design

### 1. Partitioning changes — `agents/journey-planner.md`

**1a. Review unit = behavioral / dependency thread (Decision 4).** Replace directory/logical-file grouping guidance with explicit behavioral clustering: each `### Step N` chunk is a self-contained behavioral thread traced across architectural layers (e.g. *migration + data-access change + business-logic that achieve one objective*), not a bag of co-located files. Add anti-pattern guidance: do not group by directory; do not split a single behavioral thread across chunks. This is LLM-judged by the Opus planner using the cached diffs + structural-context — no new tooling.

**1b. Tests alongside, not last (Decision 5).** A behavioral chunk's tests are bundled **with** that chunk's implementation and presented together as the change's executable oracle. Remove the standalone "Tests | after core" row from the File Change Map and the "tests last" ordering instruction. A chunk's guidance explicitly pairs each test with the behavior it exercises.

**1c. Hard 400-LOC chunk-split (Decision 6).** A hard planner rule: if a behavioral chunk's changed LOC exceeds **400**, it MUST be subdivided along data-flow / architectural boundaries into sub-chunks, each ≤ 400 LOC. No session-time ceiling is emitted (no 60-min / rate warnings). Record the LOC estimate per chunk in the journey so the buddy can verify the cap held.

**1d. Per-chunk persona + predictive questions (Decision 7).** Replace the generic "What to look for" / "Key questions" fields with:
- **Perspective:** a risk-matched PBR persona for the chunk (e.g. *security auditor* for an API/data-access change, *DBA* for a migration, *performance tester* for a hot path, *concurrency auditor* for shared mutable state).
- **Predictive questions:** boundary-condition / failure-mode questions that force predictive simulation ("if this transaction is interrupted before commit, what state remains?"), not descriptive recall.

**1e. Teach-complexity signal (Decision 2).** Each chunk carries a `complexity` hint (`trivial` | `non-trivial`) the planner sets from intrinsic difficulty (cross-layer span, unfamiliar subsystem, algorithmic density). The buddy uses it to scale teach depth. Default to `non-trivial` when uncertain (orientation is cheap; missing it on a hard chunk is costly).

**1f. Ordering.** Among behavioral threads, retain **risk-first** ordering (critical threads first). Re-review priority order is unchanged (changed-since-last-iteration → unresolved-comment → unchanged-critical → rest), now applied at the behavioral-thread level.

### 2. Guiding-loop changes — `commands/review-pr-buddy.md` Phase 1

Replace the six-step per-chunk loop with a **two-pass loop** (Decision 1):

1. **Orient (Decision 2).** Always state a one-line chunk objective. If the chunk's `complexity` is `non-trivial`, additionally give a senior-architect teach of what changed and why it matters vs. the journey Objective. For `trivial` chunks, the one-liner is the whole orientation. Deep teaching is otherwise available on explicit reviewer request ("explain this in depth").
2. **Independent read — Pass 1 (Decision 1).** Present the chunk (implementation + its bundled tests). Pose the chunk's **PBR persona + predictive questions**. The reviewer reads cold and records their own observations/concerns. **Pre-computed tool findings are NOT shown in this pass** — this is the anti-anchoring step. State the AI-role framing explicitly: the buddy is a facilitator; the reviewer is the sole arbiter of logic correctness.
3. **Reconcile — Pass 2 (Decision 1).** Reveal the chunk's pre-computed findings (investigation / sweep / reuse / intrafile) as a reconciliation against the reviewer's independent take: surface where they overlap, where the tool flagged something the reviewer didn't, and (implicitly) that the tool may have missed what the reviewer caught.
4. **Disposition (Decision 3).** For every finding — tool-surfaced and reviewer-authored — capture a **severity** via `AskUserQuestion`: **Blocking** (critical logic/security/data-corruption/requirement violation) · **Important** (architectural degradation, missing edge case, significant perf) · **Suggestion** (style/nit/optional refactor) · **Dismiss** (drop, optional note). An optional free-text comment note may accompany any non-dismissed finding (this subsumes the old "will-comment"). "add-own" remains the mechanism by which a Pass-1 observation becomes a severity-tagged finding.
5. **Checkpoint.** Persist to `buddy-session.json` (schema below).
6. **Advance.**

Interruption handling and compaction recovery are unchanged in mechanism; recovery resumes at the first chunk whose `status` is not `done`.

### 3. `buddy-session.json` schema update

Per-chunk record gains a `pass1_observations[]` array (reviewer's independent-read notes) and the disposition `verdict` enum changes from `keep|dismiss|will-comment|add-own` to a `severity` field:

```json
{
  "index": 0,
  "group": "<behavioral thread name>",
  "complexity": "trivial|non-trivial",
  "loc_estimate": 0,
  "status": "pending|in-progress|done",
  "pass1_observations": [
    { "file": "<path>", "line": 0, "note": "<reviewer's independent observation>" }
  ],
  "dispositions": [
    {
      "finding_ref": "<file:line or id>",
      "source": "investigation|sweep|reuse|intrafile|reviewer",
      "severity": "blocking|important|suggestion|dismiss",
      "note": "<optional comment text>"
    }
  ]
}
```

### 4. Curated synthesis (Phase 2) mapping

The interactive session remains the synthesis (no synthesizer-v2 agent invoked). Map severities onto the existing synthesizer-v2 sections: **Blocking → Critical Findings**, **Important → Rule-Based / Important Findings**, **Suggestion → minor**. Dismissed findings are excluded. Note: synthesizer-v2's minor tier is keyed `nit` under `### Minor` subsections — the reviewer-facing **Suggestion** disposition writes into those existing `### Minor` buckets; do **not** introduce a new `### Suggestion` section (it would break synthesizer-v2 format parity). `REVIEWED.md` finding counts are derived from the severity tally (`critical` = blocking count, `important` = important count, `minor` = suggestion count).

### 5. AI-role scoping (cross-cutting)

Per the research, the buddy frames automated findings as mechanical-triage / cross-file-dependency aids and the AI as a facilitator (orientation, persona assignment, predictive questioning, reconciliation) — never as the arbiter of business-logic correctness. This framing appears in the Pass-1 and Pass-2 copy so the reviewer does not defer to the tool on logic.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.

- **Phase 1 — Partitioning (`journey-planner.md`):** behavioral-thread review unit (1a), tests-alongside (1b), hard 400-LOC split (1c), persona + predictive questions (1d), complexity signal + loc_estimate (1e), risk-first ordering (1f).
- **Phase 2 — Guiding loop (`review-pr-buddy.md`):** two-pass loop, teach-by-complexity, severity disposition, AI-role framing, `buddy-session.json` schema bump, severity→section mapping + `REVIEWED.md` counts.
- **Phase 3 — Validation + docs:** re-run buddy on prior PRs (no-regression + behavioral-clustering check), update `README.md` buddy section.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Chunks are behavioral threads, not directory groups | Run buddy on a multi-layer PR | Each Manual Review Guide chunk spans the files of one behavioral objective across layers; no directory-named groups | `PR-{id}-journey.md` Manual Review Guide |
| Tests bundled with their code | Run buddy on a PR with tests | No standalone "tests last" chunk; each chunk lists its tests alongside the implementation they exercise | Journey file + buddy walk |
| Hard 400-LOC split holds | Run buddy on a large PR | No chunk's `loc_estimate` exceeds 400; oversized threads are subdivided | Journey file / `buddy-session.json` |
| Findings withheld until Pass 2 | Walk a chunk in buddy | Tool findings are not shown during the independent read; revealed only at the reconcile step | `review-pr-buddy.md` behavior / session transcript |
| Teach scales to complexity | Walk a trivial vs. non-trivial chunk | Trivial → one-line orientation only; non-trivial → fuller teach | Buddy walk |
| Severity captured per finding | Disposition a finding | Each non-dismissed finding carries blocking/important/suggestion; review doc sections reflect the severities | `buddy-session.json` + `PR-{id}.md` |
| Personas + predictive questions emitted | Walk any chunk | Chunk poses a risk-matched persona and boundary-condition/predictive questions, not descriptive recall | Journey file Perspective/questions fields |
| No regression in defect surfacing | Re-run buddy on past reviewed PRs | Reviewer surfaces ≥ the findings caught under the old flow | Compare to prior `PR-{id}.md` |

## Open Questions

- The behavioral-clustering quality is LLM-judged; if prompt-level clustering proves unreliable in practice, revisit deterministic AST/data-flow tooling (Tier-2 follow-up, out of scope here).
- Whether the `complexity` signal should be a richer scale than `trivial`/`non-trivial` (estimated — verify during Phase 3 validation).

## Research References

- `RESEARCH.md` — full Gemini Deep Research report (2026-06-15).
- `RESEARCH_SUMMARY.md` — analysis and the decisions that shaped this spec.
- Key sources: SmartBear/Cisco review metrics (~2006); Expertise-Reversal Effect (Kalyuga, CLT); Test-Driven Code Review (Bacchelli et al., ICSE 2019); Perspective-Based Reading inspection studies; "Abstraction Bias" / Familiar Pattern Attacks (NDSS 2026); RevMate LLM-review case study (Mozilla/Ubisoft).
- Baseline system: `../cognito-pr-review-v2/SPEC.md`.
