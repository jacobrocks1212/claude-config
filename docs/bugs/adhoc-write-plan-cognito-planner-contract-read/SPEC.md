# write-plan-cognito: planner-side lane-contract read is unmandated — Investigation Spec

> During the 2026-07-09 sandboxed v3 verification run, the `/write-plan-cognito` planner read the
> full ~17.8KB `execution-contract-cognito-lanes.md` at planning time even though SKILL.md only
> instructs the EXECUTOR to Read it (the instruction lives inside the pointer-block template).
> The read was a judgment call; the cost/benefit was undecided policy.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-09 (evidence: `attribute_predispatch.py --full` over the sandbox subagent transcript — contract read = 2nd largest Read at 17.8KB)
**Placement:** docs/bugs/adhoc-write-plan-cognito-planner-contract-read
**Related:** `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md`; `docs/bugs/adhoc-lane-plan-single-lane-seam-classification` (same run)

---

## Root cause

`write-plan-cognito/SKILL.md` carried no planner-side policy for the lane contract at all: the
only `Read`-the-contract instruction is executor-facing (inside the emitted pointer block), so a
planner deciding whether its `## Plan-specific execution notes` were contract-accurate had to
improvise — and the conservative improvisation is a full 17.8KB read.

## Decision (codified)

**Scoped consultation — never the full file.** The planner works from SKILL.md's own lane
semantics for partitioning/templates; it consults the contract ONLY when drafting a
plan-specific note that cites or deltas a specific contract behavior (e.g. L.2 typegen seam,
Part Completion), and then via heading index (`grep -n "^#"`) + ranged `Read` of just the
touched section(s) (~1–3KB). A plan with `(none — the two contracts govern unmodified)` notes
warrants zero contract reads. This keeps the observed benefit (contract-accurate notes citing
L.2 / Part-Completion semantics) at ~10–15% of the observed cost.

## Fix (shipped)

- New **"Planner-side contract consultation (scoped — never the full file)"** paragraph in
  `write-plan-cognito/SKILL.md` Step 3, directly after the v3 SPEC-excerpt discipline paragraph,
  naming the grep-headings + ranged-Read procedure and the expected planner-context cost.

## Verification

- `python user/scripts/project-skills.py` + `lint-skills.py` — clean (planner resolution check: "write-plan-cognito resolves; no execute-plan-cognito fork").
