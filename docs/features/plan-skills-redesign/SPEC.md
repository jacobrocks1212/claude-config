# Plan-Skills Redesign (`/write-plan` + `/execute-plan`) — Feature Specification

> Redesign the plan-generation/execution skill pair so plans are lean (policy lives in one shared component, not duplicated into every plan), the correct planner runs deterministically, startup context stays well under today's ~116K plateau, and the executor exploits the build/test queue with real same-message agent parallelism and backgrounded builds.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-29

**Depends on:** (none)

<!-- The build/test queue (/msbuild, /mstest, /nxbuild, /nxtest → build-queue.ps1 + enforce hook) this redesign exploits is shipped infrastructure, not a tracked feature. No feature in docs/features/ declares a dep on plan-skills-redesign; the lazy pipeline (unified-pipeline-orchestrator) *consumes* these skills but the redesign does not hinge on its contract — coupling is the reverse and is informational (see Downstream Coupling). -->

---

## Atomic Decomposition (load-bearing terms)

- **plan** → a markdown file under `cog-docs/docs/{features,bugs}/<id>/plans/*.md` decomposing a feature into work units (WUs) with file/symbol anchors, a batch schedule, and seam classification; consumed by `/execute-plan`.
- **plan-load context bloat** → resident tokens before any work begins; ~116K plateau (~85%), first-assistant-turn floor median 65.6K across 56 execute sessions.
- **the skill collision** → two skills named `write-plan` (generic user-level `user/skills/write-plan/` 649L + Cognito repo-scoped lane variant `repos/cognito-forms/.claude/skills/write-plan/` 385L). **Resolved at spec time:** Claude Code skill precedence is **enterprise > personal > project** ([skills docs](https://code.claude.com/docs/en/skills.md)), so the user-level generic *always shadows* the repo-scoped Cognito variant — the Cognito one never registers or runs. The menu advertises the (unreachable) lane variant while the generic always executes. There is **no** Cognito `execute-plan` — execution always runs the generic 419L executor.
- **lane variant** → the Cognito planner that partitions WUs into backend/frontend lanes with tiered gates and a typegen seam (orchestrator-owned incremental `Cognito.Services` build + `-UpdateInPlace`).
- **boilerplate** → ~150–190 verbatim lines/plan restating policy the `/execute-plan` skill already holds in-context — ~32–44% of a plan, ~3–3.5K redundant tok/plan; dual-sourced policy (§3.3).
- **PHASES.md growth** → grows monotonically (≈29K/540L for cognito-pay) because `/execute-plan` appends an Implementation Notes block per batch; re-read in full at startup, per `source-reread`, and per compaction → paid 5–10×/session.
- **true parallelism** → emitting multiple `Agent` dispatches in a single assistant message so the harness runs them concurrently (today every dispatch is batch-size-1 across separate turns → serial; 15–20 min gaps).
- **ground-truth gate** → the orchestrator re-running `git status`/`wc -l`/`grep -n` + the **full test suite** per WU to verify a subagent's report; caught 0 falsified reports in ~16 batches.

**Reconstructed problem:** Plan files and their executor are heavier and slower than they need to be — plans duplicate ~32–44% of policy already resident in the skill; the planner resolves nondeterministically to the generic variant (and Cognito has no dedicated executor), forfeiting the lane optimizations; PHASES.md/SPEC.md are re-read in full many times per session; provably file-disjoint dispatches are serialized; and the per-WU gate re-runs the full suite for zero caught defects.

---

## Reuse Ledger

| Capability needed | Existing system | Verdict | Evidence |
|---|---|---|---|
| Plan authoring (partitioning, anchor `[VERIFY:]` gates, dirty-tree, parts split) | generic `write-plan/SKILL.md` (649L) | reuse-as-is / extend | INVESTIGATION §3.8 — partitioning + pre-draft gates healthy, "do NOT regress" (§4) |
| Cognito lane planning (BE/FE lanes, tiered gates, typegen seam) | `repos/cognito-forms/.claude/skills/write-plan/` (385L) + `lane-agent-briefing.md` (72L) | extend / promote | INVESTIGATION §3.1, §3.6 — typegen seam works in 13 sessions |
| Plan execution (phase loop, batch dispatch, GT gate, recovery) | generic `execute-plan/SKILL.md` (419L) | refactor | INVESTIGATION §3.2, §3.3, §3.6, §3.7 |
| Build/test serialization | `build-queue.ps1` + `/msbuild`/`/mstest`/`/nxbuild`/`/nxtest` + enforce hook | reuse-as-is | INVESTIGATION §3.6 — contention cheap; compliance total post-cutover |
| Shared execution policy | `_components/{subagent-review,subagent-launch,tdd-*,phases-update,task-tracking,source-reread,quality-gates}.md` | reuse / extend | INVESTIGATION §6 — components exist; re-read up to 4× uncached |
| Post-compaction recovery anchors | Tasks tool + PHASES.md + compaction summary + `git status` | reuse-as-is | INVESTIGATION §3.5 — recovery clean 7/7; four redundant anchors |

---

## Executive Summary

`/write-plan` and `/execute-plan` were designed before the machine-global build/test queue and before the harness's same-message Agent-parallelism semantics were understood. The result is three compounding costs the session-mining investigation (`INVESTIGATION.md`, 2026-06-29, 77 plan-bearing sessions / 130 MB) quantified: **(1)** a ~116K context plateau before any work begins, ~32–44% of which is plan boilerplate that re-states policy the executor skill already holds, plus a PHASES.md re-read in full 5–10× per session; **(2)** a nondeterministic planner — the menu advertises the Cognito lane variant (tiered gates + typegen seam) while the generic per-WU-TDD planner historically ran, and Cognito has *no* dedicated executor at all, so it always runs the generic one; **(3)** zero real agent parallelism (every dispatch is batch-size-1 across separate turns → serial, with 15–20 min gaps) and a per-WU ground-truth gate that re-runs the full test suite for a defect-catch rate of 0/16.

This feature redesigns the pair along five locked directions: **single-source the execution policy** into a new shared `_components/execution-contract.md` that both the executor skill and each plan reference by path (plans carry only unique content — WUs, file/symbol anchors, batch schedule, seam classification); **resolve the planner collision deterministically** by renaming *only* the colliding Cognito planner to a distinct name (`/write-plan-cognito`) — verified necessary because Claude Code resolves skill names personal-over-project, so the user-level generic always shadows a same-named repo-scoped skill and renaming is the only path that makes the Cognito variant reachable (the collision audit confirmed `write-plan` is the *sole* user/repo collision; there is no repo-scoped `execute-plan` to rename, so execution stays on the single generic `/execute-plan` and the universal D2/D4/D5 wins land there); **relocate the growing Implementation Notes** out of PHASES.md into a sibling `IMPLEMENTATION_NOTES.md` so PHASES.md stays a thin checklist that is cheap to re-read — applied **universally with tolerant readers** (the shared `phases-update` writer emits the sibling; every reader — the harness `phases_show_implementation()` gate plus the ~8 generic consumer skills that mine Implementation Notes — checks sibling-then-embedded so in-flight features still resolve); and **encode true parallelism** — file-disjoint WUs dispatched in one message plus backgrounded long/Tier-2/typegen builds overlapped with the next independent dispatch — while **lightening the ground-truth gate** to cheap integrity checks + the assertion-vs-intent read by default, re-running tests only on mismatch.

The healthy parts the investigation calls out (§4) are explicitly preserved: partitioning logic, the pre-draft anchor/touchpoint `[VERIFY:]` gates, dirty-tree handling, pre-dispatch drift reconciliation, Tasks-based recovery (kept as one of several anchors), the typegen seam, and right-sized builds.

## User Experience

The "user" of this harness-internals feature is the orchestrator (Claude running `/write-plan` / `/execute-plan`) and, by extension, Jacob — who invokes these skills directly and reads their runs. There is **no end-user product surface**; every decision below is a harness-internal mechanism choice. Observable behaviors after the redesign:

- **The advertised planner is the one that runs.** Invoking `/write-plan-cognito` in a Cognito worktree deterministically runs the Cognito lane planner (BE/FE lanes, tiered gates, typegen seam) — never the generic per-WU-TDD planner — in every worktree, with no shadowing. The skill catalog and what executes agree.
- **Plans are lean and policy is single-sourced.** A generated plan carries only its unique content (work units, file/symbol anchors, batch schedule, seam classification) plus a one-line pointer to `_components/execution-contract.md`. Plans shrink ~32–44%. Fixing an execution-policy rule means editing one component, not regenerating every plan.
- **Startup context is materially lower.** `/execute-plan` reads only the current-phase slice of PHASES.md plus a compact completed-phases index — not the whole accumulating file. Implementation Notes live in a sibling `IMPLEMENTATION_NOTES.md` that is not re-read in full at every batch boundary. The ~116K plateau drops by the plan-boilerplate + PHASES-re-read deltas.
- **Execution stays on one generic executor.** Cognito has no separate executor skill: `/write-plan-cognito` authors lane/typegen/tiered-gate behavior into the *plan* and repo components (`lane-agent-briefing.md`), and the single generic `/execute-plan` runs it. The universal D2/D4/D5 improvements live in that one executor, so every repo benefits.
- **The executor runs disjoint work concurrently.** File-disjoint WUs are dispatched as multiple `Agent` blocks in a *single* message (the harness's only real-parallelism path); long/Tier-2/typegen builds are backgrounded and the next independent agent is dispatched while they run. Builds remain a serial spine; agent think/edit/test-author time overlaps. Target ~1.5–2× wall-clock per phase.
- **The per-WU gate is cheap by default.** The orchestrator verifies each WU with `git status`/`wc -l`/`grep -n` integrity checks plus the assertion-vs-intent read, re-running tests only when an integrity check disagrees. A review-subagent API 529 falls back to inline review after 1–2 strikes instead of burning ~16 min retrying.

## Technical Design

> Five directions from `INVESTIGATION.md §5`, scoped to v1 by the Phase-1 decisions. Recovery-card (#6) and MCP-surface trimming (#7) are deferred to a follow-up. OQ1 (skill-resolution precedence) is resolved at spec time; the collision audit (2026-06-29) further confirmed `write-plan` is the *only* user/repo skill collision and that D3 carries cross-pipeline blast radius (see D3).

### D1 — Deterministic planner resolution (INVESTIGATION §3.1)

**Resolved at spec time (OQ1).** Two facts settle this:
1. All four Cognito worktrees now carry the repo-scoped `write-plan` (the investigation's worktree-symlink-gap hypothesis is stale as of ~2026-06-24).
2. Claude Code skill-name precedence is **enterprise > personal > project** ([skills docs](https://code.claude.com/docs/en/skills.md)). A user-level skill *completely shadows* a same-named repo-scoped skill — the repo one never registers, never appears in the catalog, never runs. There is no "repo shadows user" precedence to rely on; this is documented and deterministic.

This explains the investigation's core finding outright: the generic planner ran in every mined Cognito session because the repo-scoped `write-plan` was **unreachable by construction**, not merely missing in some worktrees.

- **Mechanism (the only path that makes the Cognito variant reachable — renaming the generic was rejected in Phase 1, so the colliding Cognito skill is renamed instead):**
  - **Rename the colliding Cognito planner to a distinct name** — `/write-plan-cognito`. The collision audit (2026-06-29) confirmed `write-plan` is the *sole* user/repo collision; there is **no** repo-scoped `execute-plan` to rename and none is authored — execution stays on the single generic `/execute-plan`. Distinct names do not collide, so both `/write-plan` (generic) and `/write-plan-cognito` register and are independently invocable. The generic `/write-plan` + `/execute-plan` names are left untouched.
  - **Update the Cognito skill catalog/menu** to advertise `/write-plan-cognito` — so what is advertised matches what runs — and point Cognito-context `/lazy` Steps 6/7 at the renamed planner (the executor stage already points at the generic `/execute-plan`).
  - *(Alternative considered, not chosen: the nested-directory trick `.claude/skills/cognito/write-plan/` → `/cognito:write-plan`. The flat `-cognito` suffix is simpler and equally deterministic; revisit only if a namespace grouping is wanted.)*
- **Also:** strip personal-project residue (Tauri, MCP-validation, `/lazy-batch` Step 9 references) from the Cognito planner.

### D2 — Single-source execution policy (INVESTIGATION §3.3)

- New shared component **`_components/execution-contract.md`** holds the execution policy currently duplicated into every plan (EXECUTION MODEL, COMPONENT LOADING PROTOCOL, MANDATORY RULES, Execution Protocol / Phase-Selection Loop / per-batch steps, Blocking Issue Protocol, Completion, Work Log).
- The `/execute-plan` skill body references the component by path and reads it (cacheable). Each generated plan carries a **one-line pointer** to the component instead of ~150–190 verbatim lines.
- `/write-plan` stops emitting the boilerplate sections; plans carry only unique content. Net: ~32–44% smaller plans, single-source policy (editing one file fixes a policy bug everywhere).

### D3 — Thin PHASES.md + sibling Implementation Notes (INVESTIGATION §3.2, §3.4)

**Scope: universal, with tolerant readers** (collision-audit decision, 2026-06-29). The Implementation Notes block currently lives *inside* PHASES.md and is mined by the harness and ~8 generic consumer skills; the audit confirmed the relocation cannot be Cognito-only without forking that whole surface. Resolution: flip the single shared *writer* to the sibling and make every *reader* tolerant of both shapes (sibling-then-embedded fallback), so in-flight features whose PHASES.md still carries embedded notes keep resolving — no flag-day.

- **Writer (one shared seam):** the shared `_components/phases-update.md` component (called by `/execute-plan`) appends per-batch Implementation Notes to a sibling **`IMPLEMENTATION_NOTES.md`** (one file with per-phase sections; OQ3), NOT to PHASES.md. PHASES.md stays a thin checklist (phase headings + `- [ ]`/`- [x]` items + anchors). Because the writer is a single component, flipping it changes write behavior for every repo at once.
- **Harness reader (critical):** `lazy_core.py::phases_show_implementation()` currently greps PHASES.md for the `## Implementation Notes` heading to gate the research step. It must check the sibling `IMPLEMENTATION_NOTES.md` first, then fall back to the embedded heading — otherwise a relocated-notes feature reads as "not yet implemented" and gets re-routed to research. `remaining_unchecked_are_verification_only()` and `verify_ledger_gate()` are unaffected (they never parse Notes internals). `test_lazy_core.py` (esp. `test_phases_show_impl_implementation_notes_true`) gains sibling-file coverage.
- **Skill readers (tolerant sibling-then-embedded):** the generic consumer skills that mine Implementation Notes today — `add-phase`, `lazy`, `lazy-batch`, `realign-spec`, `implement-phase`, `implement-phase-batch`, `spec-phases-batch`, and `/spec-phases`' upstream look-back (Step 1.5) — plus the shared `source-reread.md` component, must read the sibling when present and fall back to the embedded block otherwise. These are GENERIC-skill edits (per the locked "universal wins in generic skills" rule), not new `-cognito` variants.
- Startup / `source-reread` / compaction-recovery read only the **current-phase slice** of PHASES.md (offset/limit on stable phase-boundary markers; OQ2) plus a **compact completed-phases index** — never the whole file. The thin-checklist shape must remain the gate-readable surface; `/spec-phases` (authors PHASES.md) keeps emitting it.

### D4 — Executor parallelism + background builds (INVESTIGATION §3.6)

- **Same-message batching:** the executor dispatches provably file-disjoint WUs as multiple `Agent` blocks in one assistant message (the harness's only real-parallelism path). The existing file-overlap rule already guarantees disjoint-WU safety; seam classification gates what is disjoint.
- **Background builds:** long / Tier-2 / typegen builds run `run_in_background: true` from the orchestrator session; the next independent agent is dispatched while the build runs. Builds remain a serial spine through the queue; agent think/edit/test-author time overlaps.
- **Constraint:** a backgrounded build's output must not be consumed by a dependent agent before completion — enforced by the disjoint-file + seam-classification rules, not by new queue machinery.

### D5 — Lighten the ground-truth gate (INVESTIGATION §3.7)

- **Default per WU:** cheap integrity checks (`git status` / `wc -l` / `grep -n`) + the assertion-vs-intent read (the only mechanism that caught the one real defect in the corpus). **Re-run tests only on integrity mismatch.**
- **529 inline-fallback:** after 1–2 failed review-subagent dispatch attempts (API 529), fall back to inline review immediately instead of retrying (fixes the §3.7 ~16-min retry burn).
- Keep the review mechanism hybrid/scope-gated (small batches inline, larger via review subagent at the orchestrator's model) — that part is healthy.

### Determinism / harness principles (non-negotiable)

- Skill resolution must be **deterministic** — either a verified precedence rule or distinct names, never "whichever the harness happens to pick."
- Single-source policy: execution policy lives in exactly one file; plans and the skill point at it.
- Do not regress the healthy parts (§4): partitioning, pre-draft `[VERIFY:]` anchor gates, dirty-tree handling, pre-dispatch drift reconciliation, Tasks recovery anchor, typegen seam, right-sized builds.

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the finalized phase breakdown (verified touchpoint audit, per-phase deliverables, testing strategy, and dependency ordering). Phase index:

1. **Rename the Cognito planner + lock resolution (D1).**
2. **Single-source execution policy (D2).**
3. **Thin PHASES.md + sibling notes: writer + harness reader (D3 core).**
4. **Propagate the D3 split across generic consumers (D3 blast radius).**
5. **Executor parallelism + background builds (D4).**
6. **Lighten the ground-truth gate (D5).**

Ordering: phases 1 and 2 are independent (1 first by risk); 3→4; 5 and 6 both require 2.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Advertised planner is the one that runs | `/write-plan-cognito` in each Cognito worktree (+ fresh session) | Lane-variant signatures (`Lane partitioning`, `lane-agent-briefing`, typegen seam) present; generic signatures (`8-WU cap`, test-agent+impl-agent) absent; both `/write-plan` and `/write-plan-cognito` independently invocable (no shadowing) | run transcript; resolved skill path |
| Plans carry no duplicated policy | Generate a plan via redesigned `/write-plan` | Plan contains only unique content + a one-line pointer to `execution-contract.md`; no EXECUTION MODEL / MANDATORY RULES blocks | generated plan file; line-count delta vs old plans |
| Single-source policy | Edit a rule in `_components/execution-contract.md` | Behavior changes with no plan regeneration | component diff; next `/execute-plan` run |
| PHASES.md stays thin; notes relocated | Run `/execute-plan` across multiple batches | Implementation Notes append to `IMPLEMENTATION_NOTES.md`; PHASES.md stays a checklist; startup reads only current-phase slice + index | PHASES.md size over batches; read calls in transcript |
| Harness state gate tolerates the split | Feature with notes in sibling `IMPLEMENTATION_NOTES.md`, none embedded | `phases_show_implementation()` returns True (sibling-then-embedded); research step not re-triggered; `test_lazy_core.py` sibling case green | unit test run; `lazy-state.py` routing |
| Consumers read relocated notes | `add-phase` / `realign-spec` / `implement-phase` against a feature with sibling notes | Skill surfaces the relocated Implementation Notes; falls back to embedded for legacy features | skill transcript; read calls |
| One generic executor, no Cognito fork | `/execute-plan` in Cognito | Single generic executor runs the lane/typegen-aware *plan* authored by `/write-plan-cognito`; no `/execute-plan-cognito` exists | resolved skill path; skills dir listing |
| Disjoint WUs run concurrently | Phase with ≥2 file-disjoint WUs | Multiple `Agent` blocks in ONE assistant message; wall-clock < serial sum | dispatch transcript; timestamps |
| Long builds backgrounded with overlap | Phase triggering a Tier-2/typegen build | Build dispatched `run_in_background`; next independent agent dispatched before build completes | transcript; build-queue log |
| GT gate cheap by default | Each WU verification | `git status`/`wc`/`grep` + assertion read; full-suite re-run only on mismatch | per-WU verification transcript |
| 529 inline-fallback | Review-subagent dispatch hits API 529 | Falls back to inline review within 1–2 strikes; no multi-minute retry loop | review transcript |
| Healthy parts not regressed | `/write-plan` end-to-end | Partitioning, `[VERIFY:]` anchor gates, dirty-tree, drift reconciliation, Tasks recovery, typegen seam all still fire | write-plan transcript; pre-draft gate output |

## Open Questions

- **OQ1 — RESOLVED (2026-06-29).** Claude Code skill precedence is **enterprise > personal > project** ([skills docs](https://code.claude.com/docs/en/skills.md)); user-level *always* shadows a same-named repo-scoped skill. There is no repo-shadow to rely on, so renaming the colliding Cognito planner (`/write-plan-cognito`) is the mandatory and chosen path (D1). The collision audit further confirmed `write-plan` is the **only** user/repo skill collision — no `execute-plan-cognito`, and `/spec`, `/spec-phases`, `/consistency-check` need no `-cognito` variants. No longer a research target.
- **OQ2 (mechanical):** Exact phase-boundary marker format to slice PHASES.md on (offset/limit anchor) — resolved during `/spec-phases`.
- **OQ3 (mechanical):** Whether `IMPLEMENTATION_NOTES.md` is one file with per-phase sections or per-phase files — resolved during implementation; one-file-with-sections is the working default.
- **OQ4 (mechanical):** Precise long-build signature set to background (which builds count as Tier-2/typegen) — resolved during implementation against the queue skills.

## Downstream Coupling (in-scope consumer updates + informational notes)

- **In scope (Phase 4, from the collision audit):** the D3 split forces tolerant-reader edits in the generic consumer skills that mine Implementation Notes — `add-phase`, `lazy`, `lazy-batch`, `realign-spec`, `implement-phase`, `implement-phase-batch`, `spec-phases-batch`, `/spec-phases` Step 1.5 — plus the `source-reread.md` component and the harness `lazy_core.py` gate (Phase 3). These are universal generic-skill edits, not new `-cognito` variants.
- **Pipeline dispatch:** the lazy pipeline (`unified-pipeline-orchestrator`, `/lazy` Step 6) dispatches the Cognito planner by name; it must emit `/write-plan-cognito` for Cognito repos (Phase 1). Step 7 already dispatches the generic `/execute-plan` and is unaffected by the rename.
- **Informational (not a dependency):** if the executor contract changes (plan shape, PHASES split, recovery), `/lazy` prose and the completion/coherence gates may need a light touch. The redesign does not hinge on the orchestrator's contract — coupling is the reverse.

## Research References

- **`INVESTIGATION.md`** (2026-06-29) — the empirical evidence base: 5 parallel session-mining agents over 77 plan-bearing Cognito sessions (130 MB). All §3 findings and §5 scope directions cited throughout this spec. This is the load-bearing research for the feature.
- **Gemini deep-research pass: intentionally skipped** (Phase-1 decision, 2026-06-29). The investigation already constitutes the empirical research; the one load-bearing external unknown (OQ1, skill-resolution precedence) was resolved authoritatively against the [Claude Code skills docs](https://code.claude.com/docs/en/skills.md). Remaining open questions (OQ2–OQ4) are mechanical, resolved during `/spec-phases` / implementation.
