# Implementation Phases — No docs/gemini-sprint/ staging structure in claude-config

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — documentation-only fix; the bug is a docs/convention gap (the runtime already degrades gracefully per the SPEC's Proven Findings), and claude-config has no app surface, no MCP-reachable behavior. No code/skill/script/hook change.

**Status:** Fixed

## Summary

The investigation (SPEC `**Status:** Concluded`) proved this is a **capability gap, not a code defect**: both consumers of the gemini-sprint staging path already degrade gracefully when claude-config has no `docs/gemini-sprint/` structure —

- `/lazy*` Step 0.5: an empty `find docs/gemini-sprint/results …` (missing dir) silently skips to the main loop.
- `/ingest-research` (no args, missing staging dir): clean exit 0, explicitly "a no-op, not an error."

The only working research-resume route for claude-config is **dropping `RESEARCH.md` directly** into the feature dir (routed by `lazy-state.py` Step 5 → `/spec` Phase 3). This already worked end-to-end for the origin feature `long-build-and-runtime-ownership`. The fix is to **document the direct-`RESEARCH.md`-drop as the blessed research-resume path** for self-edit / staging-less repos so it is recognized as the intended path rather than a workaround — no `docs/gemini-sprint/` machinery is added (it would be unused for a repo with negligible research volume).

⚖ policy: gemini-sprint staging in claude-config → document direct-RESEARCH.md-drop as blessed path (no unused staging machinery)

Single phase — documentation edits to two convention files. No code, no skills, no scripts, no hooks.

---

### Phase 1: Document the blessed direct-`RESEARCH.md`-drop resume path

**Status:** Complete
**Phase kind:** corrective

**Scope:** Add a short, durable note — in `docs/bugs/CLAUDE.md` and the repo-root `CLAUDE.md` — stating that claude-config has no `docs/gemini-sprint/` staging by design, and that research resume in this repo is a direct `RESEARCH.md` drop into the feature directory (routed by `lazy-state.py` Step 5 → `/spec` Phase 3). Cross-link the `/ingest-research` per-repo adoption note as the documented escape hatch should a future high-research-volume self-edit workflow ever warrant the full staging structure.

**Deliverables:**
- [x] `docs/bugs/CLAUDE.md` — add a short note (a "Research resume" line or paragraph) recording that claude-config has no gemini-sprint staging by design; the blessed resume route is a direct `RESEARCH.md` drop into the canonical feature dir (picked up by `lazy-state.py` Step 5 → `/spec` Phase 3). Cite that both consumers (`/lazy*` Step 0.5 empty-find skip; `/ingest-research` no-op exit 0) degrade gracefully when the staging dir is absent.
- [x] `CLAUDE.md` (repo root) — add a one-paragraph note in the Skills/Research-adjacent section: claude-config has no `docs/gemini-sprint/` staging; research resume is the direct `RESEARCH.md` drop. Reference `user/skills/ingest-research/SKILL.md` line ~65 ("per-repo adoption" — parameterize via `.claude/skill-config/gemini-sprint.md`) as the escape hatch for a future high-volume case.
- [x] No change to `user/skills/ingest-research/SKILL.md` — its line ~65 already documents the per-repo adoption escape hatch (read-only reference only).
- [x] Tests: none — documentation-only change, no executable behavior. Verification is a content read confirming both notes are present and accurate (see Minimum Verifiable Behavior).

**Minimum Verifiable Behavior:** `grep -l "gemini-sprint" docs/bugs/CLAUDE.md CLAUDE.md` returns both files, and each note names the direct-`RESEARCH.md`-drop as the blessed resume route and points at the `/ingest-research` per-repo adoption escape hatch. (No runtime behavior to assert — the runtime degradation is already correct per the SPEC's Proven Findings; this phase only records the convention.)

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `docs/bugs/CLAUDE.md` — add the blessed-direct-drop research-resume note.
- `CLAUDE.md` (repo root) — add the optional research-resume convention paragraph.

**Testing Strategy:** Read both edited files and confirm the notes are present, factually match the SPEC's Proven Findings (graceful degradation in both consumers; direct drop is the working route), and cross-link the `/ingest-research` adoption escape hatch. No code paths change, so no unit/integration tests apply.

**Completion (gate-owned):** The top-level SPEC/PHASES `**Status:**` flip to Fixed and the `FIXED.md` receipt are owned exclusively by the orchestrator's `__mark_fixed__` gate after the validation tail — NOT authored as a deliverable here.

**Integration Notes for Next Phase:** None — single-phase fix.

#### Implementation Notes

**Date:** 2026-06-20
**Files modified:** `docs/bugs/CLAUDE.md` (added `## Research resume` subsection), `CLAUDE.md` repo root (added `### Research resume in claude-config` paragraph in Scripts section).
**What landed:** Both notes document that claude-config has no `docs/gemini-sprint/` staging by design; the blessed research-resume route is a direct `RESEARCH.md` drop into the canonical feature/bug dir (routed by `lazy-state.py` Step 5 → `/spec` Phase 3). Both cross-link `user/skills/ingest-research/SKILL.md` line ~65 as the escape hatch for a future high-volume case. No change to `ingest-research/SKILL.md`. No code/skill/script/hook changed.
**MCP runtime:** not-required (confirmed — no app surface, no runtime behavior to validate).
**Review verdict:** PASS — notes are factually consistent with SPEC Proven Findings; both consumers' graceful-degradation behavior described correctly; escape hatch cross-linked; no existing content deleted.

---
