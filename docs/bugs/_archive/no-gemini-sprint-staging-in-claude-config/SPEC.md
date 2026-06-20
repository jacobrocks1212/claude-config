# No docs/gemini-sprint/ staging structure in claude-config — Investigation Spec

> When claude-config is itself the pipeline-driven repo, a needs-research halt cannot use the staged-`.txt` ingest path because the repo has no `docs/gemini-sprint/` staging structure — so research must be dropped directly as `RESEARCH.md`.

**Status:** Fixed
**Severity:** Low
**Discovered:** 2026-06-20
**Fixed:** 2026-06-20
**Fix commit:** 48819e0
**Placement:** docs/bugs/no-gemini-sprint-staging-in-claude-config
**Related:** `docs/features/long-build-and-runtime-ownership/` (origin — its needs-research resume surfaced this), `user/skills/ingest-research/SKILL.md`, `user/skills/lazy-batch/SKILL.md` (Step 0.5)

---

## Verified Symptoms

1. **[VERIFIED]** claude-config has no `docs/gemini-sprint/` staging structure — no `results/`, no `prompts/` symlinks, no `_consumed/`. Confirmed by filesystem scan: `find . -type d -name gemini-sprint` returns nothing; `docs/` contains only `bugs/ features/ specs/`.
2. **[VERIFIED]** Consequently, when claude-config is the pipeline-driven repo, the `/lazy*` Step 0.5 staged-`.txt` ingest path and `/ingest-research`'s prompt-symlink correlation path are inapplicable. Confirmed by reading both consumers (see Evidence).
3. **[VERIFIED]** Observed 2026-06-20: the `long-build-and-runtime-ownership` needs-research resume fell back to a direct `RESEARCH.md` drop because `/ingest-research` was inapplicable. Source: ADHOC_BRIEF.md; origin feature dir confirmed present with `RESEARCH.md` on disk.

## Reproduction Steps

1. Run a `/lazy*` feature pipeline with claude-config as the working repo.
2. Reach a `needs-research` halt for a feature.
3. Attempt to resume via the staged-`.txt` upload path (save Gemini output into `docs/gemini-sprint/results/`).

**Expected (naive):** Step 0.5 picks up the staged `.txt`, dispatches `/ingest-research`, correlates via `docs/gemini-sprint/prompts/` symlinks, writes per-feature `RESEARCH.md`.
**Actual:** No staging dir exists; Step 0.5's `find` probe returns empty and silently skips to Step 1; `/ingest-research` (no args) reports "no staging directory … nothing to ingest" and exits 0. The only working resume path is dropping `RESEARCH.md` directly into the feature dir.
**Consistency:** Always — structural, not intermittent.

## Evidence Collected

### Source Code

- **`user/skills/lazy-batch/SKILL.md` Step 0.5 (lines 198-204):** the probe is `find docs/gemini-sprint/results -maxdepth 1 -name '*.txt' -type f 2>/dev/null | head -1`; "If empty → no staged research, skip to Step 1." **Already degrades gracefully** — a missing dir yields an empty find, not an error.
- **`user/skills/lazy-batch/SKILL.md` line 252:** "Direct `RESEARCH.md` drops into canonical feature directories don't require ingestion — `lazy-state.py` sees them at Step 5 and routes to `/spec` Phase 3 naturally. Step 0.5 is specifically for the staged `.txt` upload path." → the direct-drop path is **already a documented, supported resume route.**
- **`user/skills/ingest-research/SKILL.md` lines 53-57:** no-args + missing staging dir → exit 0 with "no staging directory … nothing to ingest. … This is a no-op, not an error." **Already degrades gracefully.**
- **`user/skills/ingest-research/SKILL.md` line 65:** "Per-repo configurability is deferred — AlgoBooth is the only consumer today. If another repo adopts the pattern, parameterize the staging path via a per-repo `.claude/skill-config/gemini-sprint.md` later." → the adoption path is **already specified** should a staging structure ever be warranted.

### Git History

The `long-build-and-runtime-ownership` feature (origin) is complete on `main` with `RESEARCH.md` present in its dir, confirming the direct-drop fallback worked end-to-end.

### Related Documentation

- `docs/bugs/CLAUDE.md` — confirms this repo's bug pipeline; slugs are descriptive (no work-item tracker).
- `docs/features/long-build-and-runtime-ownership/` — the origin feature whose research resume exposed the gap.

## Theories

### Theory 1: Missing staging structure is a hard defect that breaks research resume
- **Hypothesis:** Without `docs/gemini-sprint/`, research resume in claude-config is broken.
- **Supporting evidence:** The staged-`.txt` ingest path is genuinely unavailable.
- **Contradicting evidence:** The direct-`RESEARCH.md`-drop path works and is documented (lazy-batch line 252); the long-build resume succeeded via it. Both consumers degrade cleanly (no crash).
- **Status:** Ruled Out — research resume is NOT broken; only the staged-upload convenience path is absent.

### Theory 2: Both consumers already degrade gracefully; the gap is a missing (optional) capability, not a defect
- **Hypothesis:** The "bug" is the absence of an optional convenience structure, with both consumers already no-op'ing cleanly when it's absent.
- **Supporting evidence:** Step 0.5 empty-find skip; `/ingest-research` no-op exit 0; documented direct-drop path; documented per-repo adoption path (skill-config/gemini-sprint.md).
- **Status:** Confirmed.

## Proven Findings

**Root cause:** This is a capability gap, not a code defect. The graceful-degradation behavior the brief asks about **already exists** in both consumers:
1. `/lazy*` Step 0.5 — empty `find` (missing dir) silently skips to the main loop.
2. `/ingest-research` (no args, missing staging dir) — clean exit 0, explicitly "a no-op, not an error."

The only thing absent is the staging structure itself, which makes the staged-`.txt` upload path unavailable in claude-config. The **direct-`RESEARCH.md`-drop is already the documented, working resume route** for canonical feature dirs (lazy-batch line 252), and it is the natural fit for a self-edit repo with low research volume.

**Fix scope (chosen — see ⚖ policy below):** Do NOT add a full `docs/gemini-sprint/` staging structure (results/ + prompts/ symlinks + _consumed/) to claude-config — it would be unused machinery for a repo with negligible research volume. Instead **document the direct-`RESEARCH.md`-drop as the blessed research-resume path for self-edit / staging-less repos**, so the long-build-style fallback is recognized as the intended path rather than a workaround. The documentation touch points:
- `docs/bugs/CLAUDE.md` and/or the repo-root `CLAUDE.md` Skills/Research section — a one-paragraph note that claude-config has no gemini-sprint staging by design; research resume is a direct `RESEARCH.md` drop into the feature dir (routed by `lazy-state.py` Step 5 → `/spec` Phase 3).
- Optionally cross-link `user/skills/ingest-research/SKILL.md` line 65's "per-repo adoption" note as the escape hatch should a future high-research-volume self-edit workflow ever warrant the full structure.

No skill/script/hook code changes are required — the runtime behavior is already correct. This is a documentation-only fix.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Bug-pipeline docs convention | `docs/bugs/CLAUDE.md` | Add blessed-direct-drop note for self-edit repos |
| Repo constitution | `CLAUDE.md` (repo root) | Optional: Research/resume note in the Scripts/Skills section |
| ingest-research adoption note | `user/skills/ingest-research/SKILL.md` (line 65, read-only ref) | No change needed; already documents the per-repo adoption escape hatch |

## Open Questions

None blocking. The fix is documentation-only and the runtime degradation is already correct. PHASES.md (authored next by `/plan-bug`) will sequence the doc edits.

---

⚖ policy: gemini-sprint staging in claude-config → document direct-RESEARCH.md-drop as blessed path (no unused staging machinery)
