# Mid-Build Code-Review Checkpoints — Feature Specification

> During `/execute-plan` (Cognito Forms projection only), emit a concise non-blocking Why↔How explanation after each committed batch so the user can steer mid-run without ever pausing execution.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-06-15

**Depends on:** (none)

---

## Executive Summary

`/execute-plan` runs a plan end-to-end as an autonomous orchestrator: it dispatches Sonnet sub-subagents per batch, reviews their diffs in the mandatory Batch Review Gate (Step 3 item 4), commits, updates PHASES.md, and proceeds to the next batch. Today the only narration the user sees is at *full completion* (Step 4b "Behavior enabled by this execution" and Step 4c feature-level summary). Because plan execution is long-running, the user has no visibility into *what is being built and why* until the entire plan part is done — by which point steering a wrong turn means unwinding committed work.

This feature adds a **per-batch code-review checkpoint**: immediately after each batch commits, the orchestrator emits a short chat message mapping the batch's **purpose (Why)** to the **specific code locations that fulfill it (How)** — e.g. "The purpose of this batch is to do A and B; A is accomplished in `C` and B in `D`." The orchestrator already holds this material as a byproduct of the Batch Review Gate it just performed, so the checkpoint is cheap to produce. Critically, it is **non-blocking**: the orchestrator drops the explanation and immediately continues to the next batch. The user can interrupt to steer if something looks wrong, but the run never waits.

The behavior is scoped to the **Cognito Forms projection of `/execute-plan` only**, delivered through the established `.claude/skill-config/` injection convention. A one-line injection point is added to the global `execute-plan/SKILL.md`; the checkpoint content lives in a new Cognito-Forms-only skill-config component, and every other repo resolves the injection to a no-op echo. It is further gated to **interactive runs only** — suppressed under `--batch` (autonomous `/lazy-batch` cycles have no chat audience).

## User Experience

**Who:** Jacob (or any engineer) running `/execute-plan <plan>` interactively against the Cognito Forms repo.

**Workflow:**

1. User invokes `/execute-plan <plan-path>` interactively in the Cognito Forms repo.
2. The orchestrator executes Batch N: dispatches test/impl sub-subagents, runs the Batch Review Gate, ticks the plan-WU checkbox, updates PHASES.md, and commits the batch atomically (Step 3 items 1–8).
3. **New:** immediately after the commit lands, the orchestrator prints a concise checkpoint to chat:
   - 2–5 sentences.
   - States the batch's **purpose** (the Why), drawn from the phase/WU intent in PHASES.md/SPEC.md.
   - Maps each part of that purpose to the **concrete code locations** that accomplish it (the How), using `file:symbol` anchors.
   - Framing example: *"The purpose of this batch is to do A and B. A is accomplished in `FormsService.ResolveX()` (`Cognito/.../FormsService.cs`); B is accomplished by the new `XConverter` (`Cognito.Core/.../XConverter.cs`)."*
4. **The orchestrator does not stop.** No `AskUserQuestion`, no "ready for review?" pause. It proceeds directly to Batch N+1 (Step 3 item 9).
5. If the explanation reveals a wrong direction, the user **interrupts** (their normal Esc/interject flow) to steer. Absent an interrupt, execution continues uninterrupted to completion.

**Format example (the rendered checkpoint):**

```
📋 Batch 2 checkpoint — Why → How

Purpose: persist the resolved customer entry id onto the order projection so
deferred auto-created person entries backfill correctly (PHASES.md Phase 3, WU-2).

- Resolution of the id is done in `EntryIndexService.ResolveCustomerEntryIdAsync`
  (Cognito.Core/Services/Forms/EntryIndexService.cs).
- Backfill onto the projection is wired in `OrderProjectionBuilder.Apply`
  (Cognito/.../OrderProjectionBuilder.cs).

Continuing to Batch 3.
```

**Out of scope (UX):** no interactive approval gate, no diff rendering, no per-file walkthrough, no change to the completion-time Step 4b/4c summaries (those remain and are complementary — completion summaries are capability-oriented; checkpoints are intent→implementation-oriented).

## Technical Design

### Delivery mechanism — `.claude/skill-config/` injection

`/execute-plan` already consumes project-specific config through `project-skills.py`'s recognized `!cat` forms (`user/scripts/project-skills.py`). The existing precedent is Step 2's task-tracking injection:

```
!`cat .claude/skill-config/cog-doc-track-open.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-open.md`
```

This feature uses the **fallback-echo form** (`_FALLBACK_ECHO` in `project-skills.py`) so that repos *without* the component get a literal no-op rather than a global default:

```
!`cat .claude/skill-config/post-phase-code-review-checkpoint.md 2>/dev/null || echo "<!-- no per-batch code-review checkpoint configured for this repo -->"`
```

- **In the Cognito Forms repo:** cwd-relative `.claude/skill-config/post-phase-code-review-checkpoint.md` resolves (symlinked from `claude-config/repos/cognito-forms/.claude/skill-config/`) and the checkpoint instructions render into the executing skill.
- **In every other repo / the `_default` projection:** the file is absent, the `echo` no-op fires, and no checkpoint behavior is introduced. This is what makes the feature "Cognito Forms only" despite the injection line living in the shared global skill.

### Component contents (new file)

`claude-config/repos/cognito-forms/.claude/skill-config/post-phase-code-review-checkpoint.md` — an instruction block the orchestrator follows. It MUST specify:

1. **Trigger:** after the batch's atomic gate+commit lands (Step 3 item 8) and before proceeding to the next batch (item 9). One checkpoint per committed batch.
2. **Interactive-only guard:** *skip entirely under `--batch`.* `/execute-plan` strips and is aware of the `--batch` flag; under autonomous `/lazy-batch` there is no chat audience, so the orchestrator emits nothing.
3. **Content contract:** concise Why↔How prose (2–5 sentences). State the batch's purpose (from PHASES.md/SPEC.md intent + the WU scope), then map each part of the purpose to the concrete `file:symbol` locations that fulfill it. Reuse the material from the Batch Review Gate the orchestrator just completed — do not re-analyze from scratch.
4. **Non-blocking mandate:** the orchestrator MUST NOT call `AskUserQuestion`, MUST NOT pause, and MUST proceed immediately to the next batch after printing. Steering is the user's responsibility via interrupt; the run never waits.
5. **No new artifacts:** the checkpoint is chat-only — it writes no files and does not alter PHASES.md, the plan, or commits.

### Injection point (edit to global skill)

`user/skills/execute-plan/SKILL.md`, Step 3 "Per-Step Protocol": insert a new sub-step between item 8 ("Commit the batch atomically") and item 9 ("Proceed"). The new step references the component via the fallback-echo line above, with a one-line framing sentence so the no-op case still reads coherently.

### Why per-batch (not per-plan-part)

`/execute-plan`'s real iteration/commit unit is the **batch** (Step 3 items 5/8 tick the plan-WU checkbox, update PHASES.md, and commit per batch). Firing per batch gives the earliest possible steering signal and aligns the checkpoint with the unit of committed, already-reviewed work. A plan part spanning multiple batches yields multiple checkpoints by design.

### Interaction with existing narration

| Existing | When | Orientation | Relationship |
|----------|------|-------------|--------------|
| Step 4b "Behavior enabled by this execution" | full plan-part completion | capability list (what the system can now do) | unchanged; complementary |
| Step 4c feature-level summary | only when SPEC fully complete | cumulative feature capabilities | unchanged; complementary |
| **New: per-batch checkpoint** | after each committed batch | intent → implementation (Why↔How) | net-new; the mid-build analog |

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.

Single-session, prose-only change to the config repo (no product code): author the Cognito-Forms-only skill-config component, add the fallback-echo injection sub-step to `execute-plan/SKILL.md`, and verify the projection.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Checkpoint instructions reach the Cognito Forms projection | Run `project-skills.py` | Rendered Why↔How checkpoint block present | `skills-projected/cognito-forms/execute-plan/SKILL.md` |
| No checkpoint in default/other repos | Run `project-skills.py` | Only the `<!-- no per-batch ... -->` no-op echo present; no checkpoint instructions | `skills-projected/_default/execute-plan/SKILL.md` |
| Per-batch, post-commit firing | Interactive `/execute-plan` dry-read of the projected skill | Checkpoint step sits between Per-Step item 8 (commit) and item 9 (proceed) | projected `cognito-forms` SKILL.md Step 3 |
| Non-blocking | Inspect component contract | Explicit "MUST NOT call AskUserQuestion / MUST proceed immediately" clause | `post-phase-code-review-checkpoint.md` |
| Suppressed under `--batch` | Inspect component contract | Explicit interactive-only / skip-under-`--batch` guard | `post-phase-code-review-checkpoint.md` |
| Why↔How content shape | Inspect component contract | Requires purpose statement + `file:symbol` anchors, 2–5 sentences | `post-phase-code-review-checkpoint.md` |

## Open Questions

- **Checkpoint header/label:** the rendered block uses a `📋 Batch N checkpoint — Why → How` header in the example. Final wording is a low-stakes implementation detail; defer to authoring.
- **Very small/mechanical batches:** the spec fires on *every* interactive batch. If checkpoint noise on trivial batches proves annoying in practice, a future tweak could let the orchestrator collapse a one-line checkpoint for purely mechanical batches. Not in v1 — keep it unconditional for predictability.

## Research References

None — feature was scoped without deep research at the user's request. Design is grounded in the existing `/execute-plan` skill (`user/skills/execute-plan/SKILL.md`), the `.claude/skill-config/` injection convention, and `project-skills.py`'s recognized `!cat` forms.
