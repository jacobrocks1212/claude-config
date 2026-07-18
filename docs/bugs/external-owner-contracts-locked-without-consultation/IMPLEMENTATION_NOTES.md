# External-Owner Contracts Locked Without Consultation — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — External-owner consultation gate + Cognito OW-sync convention knowledge

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-18
**Work completed:**
- `user/skills/spec/SKILL.md` — verified (not re-authored) the **External-owner surface rule** is present and matches Fix Scope #1 verbatim: `grep -n "external-owner" user/skills/spec/SKILL.md` hits at line 403 (block spans lines 401–410); read the surrounding context and confirmed it tags `external-owner: <team/repo>`, bans locking on in-repo evidence alone, offers the "lock WITHOUT owner confirmation — risk accepted" escape hatch, keys the trigger on the model's own recognition, and names the 57077 LD4 anti-pattern.
- `repos/cognito-forms/Cognito/CLAUDE.local.md` — verified (not re-authored) the **Overwatch integration convention** line is present and matches Fix Scope #2 verbatim: `grep -ni "phased out" repos/cognito-forms/Cognito/CLAUDE.local.md` hits at line 8, carrying the OW-sync mechanism, the classic-CognitoEvent-phase-out warning, the consult-first instruction, and the Slack/George Perez source citation.
- No authoring was required — both deliverables were already landed out-of-pipeline on 2026-07-10, per the plan's Plan-specific execution notes.

**Integration notes:**
- Both content pieces are load-bearing prose an LLM consults at `/spec` decision-lock time — no code path, no runtime surface. Nothing further to wire.
- The shared-file ordering constraint on `user/skills/spec/SKILL.md` with sibling bug `premise-contradictions-demoted-not-escalated` remains honored (no concurrent edit made here).

**Pitfalls & guidance:**
- None — this phase was a pure verify-and-confirm pass; both greps hit on the first try and semantics matched the SPEC Fix Scope exactly.

**Files modified:**
- `docs/bugs/external-owner-contracts-locked-without-consultation/PHASES.md` — ticked the 3 Phase 1 deliverable checkboxes (2 content rows + the "no automated test" row).
- `docs/bugs/external-owner-contracts-locked-without-consultation/plans/fix-external-owner-consultation-gate.md` — ticked WU-1/WU-2, flipped frontmatter `status: Complete`.
- `docs/bugs/external-owner-contracts-locked-without-consultation/IMPLEMENTATION_NOTES.md` — this file (created).
