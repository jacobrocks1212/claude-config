# AlgoBooth — `qg:docs-consistency` rules pending implementation

> Source: 2026-05-28 audit-walk retrospective on branch `claude/audit-lazy-batch-features-4BkA0` (199 decisions × 20 features). These four rules close gaps the walk surfaced — they live in `scripts/check-docs-consistency.ts` in the AlgoBooth repo. This file is the **spec**; the implementation lands in a separate AlgoBooth-branch PR.

## Rule 1 — `phases.coherence.phases-complete-but-spec-draft`

**Symmetric to the existing `phases.coherence.spec-complete-phases-not` / `all-phases-complete-but-top-not` pair.** Catches the inverse drift the existing rules miss.

**Trigger:** every phase in `PHASES.md` is `Complete` AND `SPEC.md` `Status:` is `Draft`.

**Severity:** error.

**Output:** `phases.coherence.phases-complete-but-spec-draft: <feature_id> — every phase in PHASES.md is Complete but SPEC.md Status is still Draft. Promote SPEC to Complete or surface the drift via /retro.`

**Motivating example:** feature 19 (`d8-stem-management`) — every PHASES.md phase landed but SPEC.md `Status: Draft` stayed for ~2 months before the audit walk caught it.

**Detection heuristic:**
1. Parse `PHASES.md` and collect every per-phase `**Status:**` line value.
2. Parse `SPEC.md`'s `**Status:**` field.
3. Fire iff `all(p == "Complete" for p in phase_statuses)` AND `spec_status == "Draft"`.

---

## Rule 2 — `spec.resolved-research-checklist-drift`

**Catches the SPEC drift the /retro Step 6b.5 spec-body-fixer (in claude-config commit 4c73fda) propagates inline.** This rule is the defense-in-depth check that catches cases where /retro didn't run (e.g., the feature predates Step 6b.5, the user ran /spec without /retro, the fixer skipped the row).

**Trigger:** `SPEC.md` has a section titled `Needs Research` (or `Open Questions`) whose items are all `- [ ]` unchecked AND `RESEARCH.md` OR `RESEARCH_SUMMARY.md` exists in the same feature dir AND that research file contains a `Locked Decisions` or `Resolution Matrix` table (or equivalent decisions-resolved surface).

**Severity:** warning (the heuristic is best-effort; some legitimately-unresolved questions might survive in a `Needs Research` block).

**Output:** `spec.resolved-research-checklist-drift: <feature_id> — SPEC.md "<section title>" has all-unchecked items but RESEARCH.md (or RESEARCH_SUMMARY.md) records resolutions. Run /retro to propagate, or rename the SPEC section.`

**Motivating examples:** features 10 and 19 — `Needs Research` checklists with 5 unchecked items each, despite research having resolved every one.

**Detection heuristic:**
1. Read `SPEC.md`, find every H2 / H3 whose title matches `^(Needs Research|Open Questions)\b` (case-insensitive).
2. Within each matched section, count `- [ ]` vs `- [x]` items. Fire condition: ≥ 1 `- [ ]` items, zero `- [x]` items.
3. Probe for `RESEARCH.md` / `RESEARCH_SUMMARY.md` in the same feature dir.
4. Within those research files, grep for `Locked Decisions`, `Resolution Matrix`, `Resolved`, or any H2 / H3 whose title matches `^(Locked Decisions|Resolution Matrix|Resolved)\b`. Fire iff at least one matches.

---

## Rule 3 — `phases.deliverables.duplicates`

**Trigger:** within a single phase block in `PHASES.md`, the same deliverable text appears in both `- [ ]` (unchecked) and `- [x]` (checked) form. Literal duplicate (after normalizing whitespace).

**Severity:** error.

**Output:** `phases.deliverables.duplicates: <feature_id> Phase <N> — deliverable "<text>" appears both unchecked and checked.`

**Motivating example:** feature 15 Phase 3 — same deliverable listed `[ ]` AND `[x]`.

**Detection heuristic:**
1. Parse `PHASES.md` into per-phase blocks (split on H2/H3 headings matching `^### Phase \d+`).
2. Within each phase block, collect every `- [ ]` text and every `- [x]` text (strip the prefix, normalize whitespace runs).
3. Fire for each text that appears in both lists.

---

## Rule 4 — `spec.status-stale-vs-last-updated`

**Trigger:** `SPEC.md` `Status: Draft` AND `Last updated:` is more than 30 days old AND `PHASES.md` exists with at least one phase `Complete`.

**Severity:** warning.

**Output:** `spec.status-stale-vs-last-updated: <feature_id> — SPEC Status: Draft + Last updated <date> (>30d old) + PHASES has Complete phases. Promote Status or refresh Last updated.`

**Motivating example:** feature 19 — Draft status persisted for ~2 months.

**Detection heuristic:**
1. Parse `SPEC.md`'s `**Status:**` value and `**Last updated:**` value (try ISO date and `YYYY-MM-DD` forms).
2. Compute `today - last_updated`. If absent, default to `infinity` (definitely stale).
3. Parse `PHASES.md` per-phase `**Status:**` values. Fire iff `spec_status == "Draft"` AND `(today - last_updated).days > 30` AND `any(p == "Complete" for p in phase_statuses)`.

---

## Implementation notes for the AlgoBooth-side PR

- `scripts/check-docs-consistency.ts` lives in the AlgoBooth repo root. Extend its existing rule registry — don't replace.
- Keep the existing `phases.coherence.spec-complete-phases-not` / `all-phases-complete-but-top-not` rule pair intact; Rule 1 is the symmetric add, not a replacement.
- The gate is invoked via `npm run qg -- docs` (or similar) per `quality-gates.md`. Existing pattern: each rule reports `{rule_id, feature_id, severity, message}`; the gate exits non-zero if any `error` fires.
- Suggested test fixture coverage: feature 19 historical state (Rule 1 + Rule 4), feature 15 Phase 3 historical state (Rule 3), feature 10 historical state (Rule 2).
- Run the existing docs-consistency test suite first to confirm no false positives against the current AlgoBooth `docs/features/` tree, then commit.

## When to delete this file

Delete `docs-consistency-rules-pending.md` after the AlgoBooth-side PR lands the four rules and the test fixtures pass. At that point this spec has rotted into the implementation and is redundant.
