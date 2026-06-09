# spec-buddy — Collaborative Partition-Walk Spec Skill — Feature Specification

> A senior-architect *pair-planning* skill (`/spec-buddy`) that reuses `/spec`'s machinery but restructures the brainstorm into a partition-by-partition co-design walk: per partition the agent runs autonomous subagent recon, arrives with a terse, bulleted, confidence-scored, evidence-cited check-in (with pseudo-code where relevant), uses liberal `AskUserQuestion` to decide with the user, and persists that part to a downstream-compatible `SPEC.md` before advancing.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-08

**Depends on:** (none)

<!-- Like review-pr-buddy, the substrate spec-buddy composes — the /spec skill and the shared
     _components/ files — is not a spec'd feature-id under docs/specs/, so there is nothing
     parseable to depend on (dep-block schema → (none)). Coupling is documented in Technical
     Design § Composed substrate. -->

---

## Executive Summary

`/spec` is already interactive, but its interactivity is "the agent pre-bakes 2–4 options, the user picks." The user is a *picker*, not a *co-author*. `/spec-buddy` changes the shape of the collaboration: it is a senior-architect partner that arrives at each check-in with a **well-prepared plan part** — already researched, with an opinionated recommendation, visible confidence, and cited evidence — and walks the user through the design **one discrete partition at a time**, iterating back and forth until both agree, then persisting that part before moving on.

The skill is a **separate command that reuses `/spec`'s machinery** (the same `_components/` files and the same `SPEC.md` output contract), so `/spec` stays lean and untouched and both skills evolve without drift. Its distinctive behavior is a **partition-walk loop**: an upfront planner subagent decomposes the feature into a partition list the user approves, then for each partition the agent (1) runs **just-in-time subagent recon** of the codebase and the `../cog-docs` PHASES.md corpus, (2) presents a **structured, no-fluff, confidence-scored, auditable check-in** with pseudo-code where relevant, (3) decides with the user via **liberal `AskUserQuestion`**, and (4) **persists the resolved part** into a standard, downstream-compatible `SPEC.md`.

The design goal is stated in the user's own words: by the end, the user is *familiar with the core plan* — because it was explained well, iterated to a mutually-agreed solution, grounded in confirmed reuse of existing systems and conventions, and the user was actively involved in planning the important components. The agent is "my partner, but also my librarian": opinionated only when evidence yields high confidence, and obligated to investigate further when confidence is low.

## Reuse Ledger

The reuse story is strong — nearly everything is an existing `_components/` file or a `/spec` phase. Net-new is the partition-walk control flow and the confidence-scored check-in format.

| Capability | Existing candidate | What it does today | Verdict | Evidence | Confidence |
|---|---|---|---|---|---|
| Collaboration stance (partner framing) | `_components/team-architect-stance.md` | Co-design / auditable / thorough stance, overridable per-repo | reuse-as-is | `/spec` SKILL.md:18 | high |
| Subagent exploration / partitioning | `_components/subagent-partitioning.md`, `subagent-launch.md`, `subagent-review.md` | Partitioning + parallel subagent dispatch for implementation fan-out | extend | adapt the partitioning/dispatch shape to interactive *design* partitions | high |
| Reuse-first discipline | `_components/reuse-first-discovery.md` | Capability → grounding → verdict taxonomy → ledger → confidence gate | reuse-as-is | `/spec` Step 1b.7 | high |
| Dep block + atomic decomposition | `_components/dep-block-schema.md`, `atomic-thinking.md` | Dep-block schema; first-principles decomposition | reuse-as-is | `/spec` Step 1b, 1c | high |
| Research phase (Gemini) + SPEC structure + validation criteria | `/spec` SKILL.md Phases 2–3, `_components/spec-testing-guidance.md` | Gemini prompt gen; final SPEC.md structure; validation-criteria table | reuse-as-is (delegate) | single source of truth for SPEC shape | high |
| Session recovery / checkpointing | `_components/decision-resume.md`, `post-compact-reread.md`, Task tools, `track-work.py` | Compaction-safe resume; WIP liveness | reuse-as-is | review-pr-buddy uses the same | high |
| Prior-art / pitfalls corpus ("librarian") | `../cog-docs` `docs/{features,bugs}/*/PHASES.md` | Prior implementation decisions, pitfalls, Implementation Notes | reuse-as-is (new consumer) | 8 PHASES.md present today (verified: `find cog-docs -name PHASES.md`) | high |
| Work log | `_components/work-log.md` | Interview-prep work-log append | reuse-as-is | `/spec` Step 4 | high |
| **Partition-walk loop + confidence-scored check-in format** | — | — | **build-new** | searched all `_components/` (50+ files); none implements an interactive per-partition confidence/evidence check-in or a design-partition walk loop. `subagent-partitioning.md` exists but targets implementation fan-out, not interactive design partitions | high |

**Net-new (build) surface — minimal, each composes the above:**
- `user/skills/spec-buddy/SKILL.md` — the partition-walk orchestration shell. The only genuinely new control flow.
- A new shared component for the **confidence-scored check-in format** (so the format is one source of truth and could later be reused).

## User Experience

### `/spec-buddy <feature description>`

**Phase 0 — autonomous groundwork (no user interaction).** The agent runs `/spec`'s mechanical discovery to completion: project-context discovery, dep-block search, reuse-first discovery (Reuse Ledger), and the one-shot atomic decomposition. This is the "well-prepared" base the partner arrives with. The Reuse Ledger is held to be walked as the **first partition** (Phase 2), so the user co-signs every reuse / extend / build-new verdict.

**Phase 1 — partition planning (one approval gate).** A planner subagent decomposes *this* feature into a proposed **partition list** — discrete design topics sized to the feature, with the **Reuse Ledger as the first partition**, followed by design topics (e.g. "data model", "core loop", "edge cases & failure", "validation criteria"). Each partition is **tagged with a tier — important or minor**. The user approves / edits / reorders the list **and adjusts tiers** before the walk begins. The approved list is the visible spine ("N parts, here's where we are").

**Phase 2 — the partition walk (the core loop).** For each partition, in order (Reuse Ledger first). **Check-in depth is proportional to the partition's tier:** *important* partitions get the full treatment below; *minor* partitions get a condensed one-line recommendation + a quick confirm.

1. **Recon (autonomous, between rounds).** Dispatch just-in-time subagent(s) to gather evidence: relevant codebase systems/types/conventions and relevant `../cog-docs` PHASES.md prior art + pitfalls. Each returns cited findings with a confidence read. (Minor partitions may skip or lighten recon.)
2. **Check-in (structured, every time).** Present a no-fluff brief: what this partition is, the recommendation, **bulleted** supporting evidence with citations (`file:line` / symbol / `PHASES.md`), **visible confidence** (high / med / low), and **pseudo-code where relevant** (important partitions). The agent is opinionated only at high confidence; at low confidence it proposes further investigation rather than forcing a call.
3. **Decide (liberal `AskUserQuestion`).** Capture the user's call. Iterate back and forth within the partition until both agree.
4. **Persist.** Write the resolved partition into `SPEC.md` immediately, with confidence/evidence woven in; unresolved low-confidence items go to Open Questions. Checkpoint partition status to a session-state file for compaction recovery.
5. **Advance** to the next partition. The user may revisit a prior partition or dig deeper at any point.

**Phase 3 — Gemini research (user-only invocation).** spec-buddy does **not** proactively offer research. If the user explicitly asks for an external-prior-art pass, the agent runs `/spec`'s Gemini deep-research gate and integrates the results as in `/spec` Phase 3. Otherwise the walk proceeds without it.

**Phase 4 — finalize.** Complete the standard `SPEC.md` (Validation Criteria table, dep-block finalization checkpoint, cross-boundary validation), write `RESEARCH_SUMMARY.md` if research ran, and append the work log. Output is downstream-compatible with `/spec-phases`, `/write-plan`, and `/lazy`.

### The check-in format (build-new — the heart of the skill)

Every partition check-in follows one fixed shape so the experience is predictable:

- **Partition:** name + one-line purpose.
- **Recommendation:** the agent's opinionated call (only stated as a call at high confidence).
- **Evidence:** bulleted, each line cited (`file:line` / symbol / `PHASES.md` path).
- **Confidence:** high / med / low, with a one-line reason. Low confidence ⇒ a proposed investigation, not a decision.
- **Pseudo-code:** where the partition is code-shaped.
- **Open question(s):** anything deferred.

Simple terms, no fluff, bulleted where applicable, auditable, confidence visible — every time. *Minor*-tier partitions condense this to the recommendation + confidence + a quick confirm.

## Technical Design

### Composed substrate

- **Skill home:** `user/skills/spec-buddy/SKILL.md` in `claude-config` (projected to `~/.claude/skills/spec-buddy/`; tracked via `manifest.psd1`).
- **Shared with `/spec`:** the same `_components/` files, `!cat`'d in place (no copies): `team-architect-stance.md`, `reuse-first-discovery.md`, `dep-block-schema.md`, `atomic-thinking.md`, `spec-testing-guidance.md`, `cog-doc-track-open.md`, `work-log.md`. The final `SPEC.md` structure and the Gemini research flow are delegated to `/spec`'s logic so there is one source of truth.
- **New shared component:** the confidence-scored check-in format, extracted to `_components/` so it is reusable and drift-free.

### Partition-walk loop

The loop is the only new control flow. State is tracked in a session-state file (e.g. `{spec-dir}/spec-buddy/buddy-session.json`) recording the approved partition list, per-partition status (pending / in-progress / resolved), and per-partition decisions + confidence, so a mid-walk compaction resumes at the right partition. Task tools track the high-level phases.

### Recon subagents (the "librarian")

Per-partition recon reuses the `subagent-launch` / `subagent-partitioning` dispatch shape. Each recon agent is grounded in: the local codebase (tree-sitter MCP + Grep/Glob), the reuse-first grounding catalog (domain skills / agent-docs), and the `../cog-docs` PHASES.md corpus (prior decisions + pitfalls). A recon agent that finds nothing returns the explicit negative trail, mirroring reuse-first discovery.

### Downstream compatibility

`SPEC.md` and `RESEARCH_SUMMARY.md` match `/spec`'s contract exactly, so `/spec-phases`, `/write-plan`, and `/lazy` consume spec-buddy output unchanged. Confidence/evidence are woven into the existing sections (and Open Questions); no schema change to the SPEC.

## Implementation Phases

See `PHASES.md` (authored later by `/spec-phases`). Intended ordering:

1. **Check-in format component** — extract the confidence-scored check-in format to `_components/`; lint + projection green. (Foundational.)
2. **Partition-walk shell** — author `SKILL.md`: Phase 0 delegation to `/spec` discovery, Phase 1 planner + tiered partition list + approval, Phase 2 loop (recon → tier-proportional check-in → decide → persist) with Reuse Ledger as the first partition, session-state + recovery.
3. **Recon + librarian wiring** — per-partition subagent recon grounded in codebase + cog-docs PHASES.md; negative-trail discipline.
4. **Research + finalize delegation** — optional Gemini gate; delegate final SPEC.md/validation/work-log to `/spec`'s logic.
5. **Integration + docs** — register in `manifest.psd1`; projection; smoke test on a real feature.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|---|---|---|---|
| Groundwork runs before the walk | `/spec-buddy <feature>` | Reuse Ledger + dep block + atomic decomposition produced before Phase 1 | chat transcript ordering |
| User approves the partition list first | start of a session | a proposed, tiered partition list is presented and editable (incl. tiers) before any partition is walked | transcript; `buddy-session.json` |
| Reuse Ledger is the first walked partition | start of the walk | the first partition presented is the Reuse Ledger; user co-signs each verdict | transcript; `SPEC.md` Reuse Ledger |
| Check-in depth tracks tier | walking partitions | important partitions get full check-in + pseudo-code; minor ones get a condensed confirm | transcript |
| Recon precedes every check-in | each partition | subagent recon dispatched before the partition's check-in | transcript; agent dispatch order |
| Check-in carries visible confidence + citations | each partition | check-in includes recommendation + bulleted cited evidence + high/med/low confidence | transcript |
| Low confidence triggers investigation, not a forced call | a low-confidence partition | agent proposes further recon instead of an opinionated recommendation | transcript |
| Partitions persist incrementally | resolve a partition | `SPEC.md` updated with that part before the next partition | `SPEC.md` diff per partition |
| State is recoverable | simulate compaction mid-walk | resume returns to the right partition | `buddy-session.json` |
| Output is downstream-compatible | finish a session | `SPEC.md` parses for `/spec-phases` / `/write-plan` (valid dep block, validation table) | dep-block checkpoint; spec-phases dry run |
| cog-docs PHASES.md is consulted | a partition with relevant prior art | check-in cites a relevant `../cog-docs/.../PHASES.md` finding/pitfall | transcript citations |

## Open Questions

- **Session-state file shape** — exact schema of `buddy-session.json` (partition list + tiers + per-partition status/decision/confidence) to be finalized during Phase 2 authoring; reuse `decision-resume.md` conventions where they fit. (mechanical — resolve at implementation)
- **Minor-tier recon** — whether minor partitions skip recon entirely or run a single lightweight lookup; tune during a real smoke test. (resolve during Phase 5)

## Research References

None — research was explicitly skipped for this feature (`/spec-buddy` skip-research). The design is grounded in direct reading of the `/spec` skill, its `_components/`, and the `review-pr-buddy` spec across this brainstorm session.
