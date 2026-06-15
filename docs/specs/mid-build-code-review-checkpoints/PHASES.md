# Implementation Phases — Mid-Build Code-Review Checkpoints

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — config-repo skill/prose change; no app behavior, store, audio, or UI surface to validate via MCP. The deliverables are a markdown skill-config component, a one-line injection edit to a skill file, and a `project-skills.py` projection check.

## Validated Assumptions

- **The `_FALLBACK_ECHO` injection form resolves to a no-op for repos lacking the component.** Confirmed against `user/scripts/project-skills.py` (`_FALLBACK_ECHO` regex: `!\`cat .claude/skill-config/X 2>/dev/null || echo "Y"\``) and against two live in-repo precedents: `user/skills/investigate/SKILL.md:89` and `user/skills/_components/quality-gates.md:7`. The injected content only renders where the cwd-relative `.claude/skill-config/<file>` exists (the Cognito Forms repo, symlinked from `repos/cognito-forms/.claude/skill-config/`); everywhere else the `echo` no-op fires.
- **Insertion point is unambiguous.** `user/skills/execute-plan/SKILL.md` Step 3 "Per-Step Protocol" is a 1–9 numbered list; item 8 = "Commit the batch atomically", item 9 = "Proceed". The checkpoint fires after the commit lands (item 8) and before proceeding (item 9). Verified by reading the file this session.

## Cross-feature Integration Notes

No hard dependencies on completed upstream features (`**Depends on:** (none)` in SPEC.md). No upstream PHASES.md to integrate against.

---

### Phase 1: Cognito-Forms-scoped per-batch Why↔How checkpoint

**Status:** Complete (2026-06-15)

**Scope:** Add a non-blocking, interactive-only, per-batch code-review checkpoint to the Cognito Forms projection of `/execute-plan`. After each committed batch, the orchestrator emits a concise Why↔How chat message (purpose → `file:symbol` locations) and immediately continues. Delivered via the `.claude/skill-config/` injection convention so the behavior is Cognito-Forms-only; every other repo / the `_default` projection resolves the injection to a no-op echo.

**Deliverables:**
- [x] Net-new component `repos/cognito-forms/.claude/skill-config/post-phase-code-review-checkpoint.md` implementing the SPEC's component contract: (1) trigger = after the batch's atomic gate+commit (Step 3 item 8), once per committed batch; (2) interactive-only guard — skip entirely under `--batch`; (3) Why↔How content contract — 2–5 sentences mapping the batch's purpose (from PHASES.md/SPEC.md + WU scope) to concrete `file:symbol` anchors, reusing material from the Batch Review Gate just completed; (4) non-blocking mandate — MUST NOT call `AskUserQuestion`, MUST NOT pause, MUST proceed immediately; (5) no new artifacts (chat-only, writes no files, does not touch PHASES.md/plan/commits).
- [x] Injection sub-step added to `user/skills/execute-plan/SKILL.md` Step 3 "Per-Step Protocol", inserted between item 8 ("Commit the batch atomically") and item 9 ("Proceed"), using the `_FALLBACK_ECHO` form: `!`cat .claude/skill-config/post-phase-code-review-checkpoint.md 2>/dev/null || echo "<!-- no per-batch code-review checkpoint configured for this repo -->"``. Includes a one-line framing sentence so the no-op case still reads coherently. Subsequent items renumbered (item 9 "Proceed" becomes item 10).
- [x] Tests: none — markdown skill-config + prose injection; no compiled code, no test surface. Verification is by projection + inspection (below), not by a test runner.

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/project-skills.py` runs clean, and the rendered checkpoint instructions appear in `skills-projected/cognito-forms/execute-plan/SKILL.md` while only the `<!-- no per-batch ... -->` no-op echo appears in `skills-projected/_default/execute-plan/SKILL.md`.

**Runtime Verification** *(checked by manual inspection of the projection output — NOT by the implementation agent):*
- [x] After `project-skills.py` runs: `skills-projected/Cognito Forms/execute-plan/SKILL.md` contains the Why↔How checkpoint instruction block, positioned between the commit step (item 8) and the proceed step (item 10).
- [x] After `project-skills.py` runs: `skills-projected/_default/execute-plan/SKILL.md` contains ONLY the no-op echo comment at the injection point — no checkpoint instructions.
- [x] The component contract text explicitly contains the interactive-only / skip-under-`--batch` guard (line 3) and the non-blocking "MUST NOT call AskUserQuestion / proceed immediately" mandate (line 9).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; this is skill-config prose validated by projection + inspection.

**Prerequisites:** None (single-phase feature).

**Files likely modified:**
- `repos/cognito-forms/.claude/skill-config/post-phase-code-review-checkpoint.md` — **net-new (create)**; the checkpoint instruction component.
- `user/skills/execute-plan/SKILL.md` — add the one-line `_FALLBACK_ECHO` injection sub-step in Step 3 Per-Step Protocol (between items 8 and 9) + framing sentence; renumber following item.

**Reuse:** extends the established `.claude/skill-config/` injection convention — directly mirrors the existing fallback-echo precedents `user/skills/investigate/SKILL.md:89` and `user/skills/_components/quality-gates.md:7`, and the fallback-cat precedent already inside execute-plan (`SKILL.md:141`, `cog-doc-track-open.md`). No new mechanism introduced. See SPEC "Delivery mechanism — `.claude/skill-config/` injection".

**Testing Strategy:** Run `python ~/.claude/scripts/project-skills.py` (auto-discovers repos with `.claude/skill-config/` and emits `skills-projected/_default/` + `skills-projected/cognito-forms/`). Diff the two projected `execute-plan/SKILL.md` outputs at the injection point: Cognito Forms = rendered checkpoint instructions; `_default` = no-op echo. Spot-check the component contract text for the interactive-only guard and the non-blocking mandate.

**Integration Notes for Next Phase:** None — terminal phase. On completion, the SPEC's `**Status:**` flips to Complete (gate/manual) and the config change is committed in the `claude-config` repo (these files are not tracked by the Cognito Forms host repo).

#### Implementation Notes (2026-06-15)

**Work completed:** Both work units landed in a single batch via two parallel Sonnet impl agents.

**Files modified:**
- `repos/cognito-forms/.claude/skill-config/post-phase-code-review-checkpoint.md` — net-new (29 lines). Encodes all five SPEC contract points: trigger after item-8 commit / once per batch (line 5); skip-entirely-under-`--batch` interactive-only guard (line 3); 2–5-sentence Why→How content contract reusing Batch-Review-Gate material (line 7); non-blocking MUST-NOT-`AskUserQuestion`/MUST-NOT-pause mandate (line 9); chat-only no-artifacts clause (line 11); plus a rendered format guide matching the SPEC example.
- `user/skills/execute-plan/SKILL.md` — inserted new Step 3 Per-Step-Protocol item 9 ("Mid-build checkpoint (project-scoped)") between item 8 (commit) and the former item 9 (Proceed, renumbered to item 10), carrying the exact `_FALLBACK_ECHO` injection line. No cross-reference fixes needed (only `item 5`/`item 4` references exist, both still correct).

**Verification:** `project-skills.py` ran clean (exit 0, no errors, 7 repos). Projection diff confirmed: the `Cognito Forms` projection renders the full Why→How checkpoint block between item 8 and item 10; the `_default` projection resolves the injection to only the `<!-- no per-batch code-review checkpoint configured for this repo -->` no-op comment. All six SPEC Validation Criteria rows satisfied.

**Pitfall noted:** the plan referenced the projection output dir as `skills-projected/cognito-forms/`, but the actual auto-discovered dir name is `skills-projected/Cognito Forms/` (repo dir name with a space). Mechanism unaffected — the cwd-relative `.claude/skill-config/` resolution is what gates Cognito-Forms-only rendering, not the projected dir name.

**Review verdict:** PASS — ground-truth verified (yes for both WUs); both projections render correctly; component contract complete and free of planning-artifact leakage.

---
