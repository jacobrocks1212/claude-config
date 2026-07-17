# CLAUDE.md Maintenance v2 — Feature Specification

> Two coupled bodies of work: (1) trim ~16.5 KB of non-durable bloat out of the 12 Cognito Forms
> `CLAUDE.local.md` files, and (2) fix the skill prescription that produced it — by inverting the
> post-implementation default from "review-and-usually-write" to "no-update-unless-it-passes-the-bar"
> and importing `/retro`'s existing generalization test into the shared `claude-md-review.md` component.

**Status:** Complete
**Priority:** P2
**Last updated:** 2026-07-17
**Friction-reduction feature:** yes

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented mechanisms read/extended,
> not sibling specs** (the doc-drift-linter / code-doc-provenance-linkage pattern):
> - `user/skills/_components/claude-md-review.md` — the single leaf every implementation skill points
>   at (9 consumers; see Reuse Ledger). This feature rewrites it.
> - `/retro` (`user/skills/retro/SKILL.md`) — the source of the generalization-test + durability
>   checklist being imported. Read-only source; not modified.
> - `friction-kpi-registry` — `docs/kpi/registry.json` + `user/scripts/kpi-scorecard.py`. This feature
>   drafts + promotes one new registry row (see KPI Declaration). Mechanism must exist; not a spec dep.

---

## Executive Summary

The 12 `CLAUDE.local.md` files under `Cognito Forms/` total **50,182 bytes**, of which an
evidence-audit classifies **~67% durable / ~33% (16.5 KB) non-durable**. The non-durable third is
concentrated, not spread: two paragraphs in `apps/spa/CLAUDE.local.md` (pasted validation-report
prose about one feature's current wiring) are 45% of that file; "Key Files" / API-catalog tables
across `QueueJob`, `model.js`, `apps/client`, and `UnitTests` (~9 KB, the single largest bloat class)
restate what Glob and the tree-sitter MCP return on demand; and `Cognito/CLAUDE.local.md` carries a
paused-feature narrative plus a **false claim stamped `verified 2026-07-17`** ("no
`PurgeOrganizationException` anywhere" — the type exists and is thrown at
`Cognito/Tasks/PurgeOrganizationQueueMessage.cs:46`).

The bloat's cause is not a missing rule. `claude-md-review.md` — the shared component every
implementation skill (`/execute-plan`, `/fix`, `/implement-phase`, `/write-plan-cognito`, …) routes
through — **already** says "Lean and durable only" and "Do NOT add volatile info (test counts, line
numbers, version strings, dates that will rot)." That rule exists and lost anyway. Two structural
tells point at why: the step is framed **"MANDATORY — DO NOT SKIP"** around a *review*, with the
"no updates required" exit buried on the last line (so producing an update reads as compliance,
producing nothing reads as skipping); and `/retro` already holds a far stronger, unused bar — a
4-question generalization test, a durability checklist, and an explicit *"Do NOT convert
implementation defects into CLAUDE.md rules"* anti-trigger — that was never wired into the component
the implementation skills use.

This feature does both halves: a one-shot rubric-driven trim of all 12 files (≈50 KB → ≈34 KB),
and a rewrite of `claude-md-review.md` that inverts the default and imports `/retro`'s test so the
implementation skills and the retro skill share one bar. Success is measured mechanically: the
auto-loaded corpus byte count, registered as a friction KPI with a byte-regrowth band.

## User Experience

The "user" is any Claude Code agent (and Jacob) operating in the Cognito Forms repo. Observable
changes:

- **Every session loads a leaner corpus.** `CLAUDE.local.md` files are auto-loaded on session start;
  cutting ~16 KB reduces the baseline context every Cognito session pays, and removes the divergent /
  stale content an agent could act on wrongly (e.g. the false purge-exception claim, the conflicting
  testing-conventions advice, the three stale filesystem inventories that already omit real dirs).
- **After implementation work, agents stop over-writing to these files.** The reframed post-phase
  step makes "no CLAUDE.md update" the expected, unremarkable outcome. An update happens only when the
  knowledge passes the imported generalization test — so the GetFieldPath/ModelSource-class gotchas
  (durable, incident-anchored, general) still get captured, while the validation-report-shaped prose
  that produced the bloat does not.
- **Where `.agents/agent-docs/` already covers a topic (often better), the `CLAUDE.local.md` points
  at it** instead of restating it — following the cross-reference pattern `Cognito.Core/CLAUDE.local.md`
  already uses well.

Out of scope (considered, declined — see Locked Decisions): fixing the AGENTS.md ↔ CLAUDE.local.md
raw-`dotnet`-vs-`/msbuild` contradiction (field evidence: agents are reliably choosing the skills);
any lint/size-budget enforcement (the guardrail is the reframed prescription, not a gate); a
recurring re-audit skill.

## Technical Design

### Part A — Fix the prescription (`claude-md-review.md`)

Single-file edit with a ~9-consumer blast radius (all reference-based or one `!cat` in `/fix`; no
consumer needs its own change — they inherit the component). Rewrite so:

1. **Default inverts.** Lead with the expectation that most implementation work warrants **no**
   CLAUDE.md update; the heading stops framing the *review* as the mandatory deliverable. Producing
   nothing is the normal path, not a skip.
2. **Import `/retro`'s bar.** Fold in the generalization test (the 4-question table: "would this
   prevent ≥3 distinct mistakes?", "understandable without knowing what produced it?", "does it
   duplicate what the target already handles?", "so broad it false-positives?") and the durability
   checklist (no phase/batch/feature-name refs, no "just added/recently changed", useful in 6 months
   with no context). An update must affirmatively pass this bar to be written.
3. **Keep the escape hatch, promote it.** "If no updates are needed, state so and move on" moves from
   buried-last-line to a first-class expected outcome.
4. **Name `CLAUDE.local.md` explicitly.** The component (and the orchestrator write-carve-out lines
   that gate it — `The ONLY files you may modify directly: PHASES.md, CLAUDE.md, …`) currently name
   only `CLAUDE.md`. Cognito Forms uses `CLAUDE.local.md` exclusively, so add it to the component's
   target list and to the carve-out lines that reach this repo. (Mechanical correctness fix — the
   prescription has been applied by analogy to a file it never named.)

Coupling to respect: `/retro`'s own copy of the test stays the source of truth for retro; the
component gets an aligned copy (not a `!cat` of retro internals — retro's section is embedded in a
larger skill, not a shareable component). Note the intended parity in both files so a future edit to
one prompts a check of the other.

### Part B — Trim the 12 files (one-shot)

Apply a fixed rubric to each file. Every paragraph/section is classed and acted on:

| Class | Action |
|-------|--------|
| DURABLE (structure, conventions, incident-anchored gotchas, "never X because Y") | **Keep** |
| INVENTORY (Key-Files tables, API/class catalogs, filesystem mirrors, Nx/queue-name lists) | **Delete** — recoverable via Glob / tree-sitter on demand |
| IMPLEMENTATION-NOTE (validation-report prose, `(bug NNNNN)` / `(PR #NNNNN)` tails, dated stamps, "accepted residual gap", per-feature wiring at expression detail) | **Delete** — or, if a durable rule is buried inside, extract the rule and drop the narrative |
| STALE / UNVERIFIABLE | **Delete or correct** (correct only if the durable form is quick to verify; else delete) |
| Duplicates `.agents/agent-docs/*` where agent-docs is equal-or-richer | **Replace with a one-line pointer** to the agent-doc |

Two mechanical companions applied to all 12:
- **Standardize the `Maintenance:` footer** (the "do NOT add version numbers, line numbers, or test
  counts" meta-rule) onto every file. It currently exists on 3 of 12 — and the 2 least-bloated files
  (Services 6%, Core 10%) both carry it; the 2 worst (spa 55%, UnitTests 39%) do not.
- **Fix the two live defects by hand** regardless of class: (1) the false `verified 2026-07-17`
  purge-exception claim in `Cognito/CLAUDE.local.md`; (2) the three stale filesystem inventories in
  the root file (`<structure>` libs list, `<subdirectory-docs>` list) — deleted per the INVENTORY
  rule rather than corrected, since they are hand-maintained mirrors that will re-drift.

Expected result: ≈50,182 B → ≈34,000 B. Per-file targets are guidance, not gates; the rubric is the
authority. `Services` and `Core` are already clean and serve as the reference exemplars — the trim
brings the other 10 toward their durable-density.

**Editing mechanics.** These 12 files are symlinks into `claude-config/repos/cognito-forms/`; the
Edit tool refuses to write through a symlink, so all edits target the real paths under
`claude-config/repos/cognito-forms/<subdir>/CLAUDE.local.md`. Changes are committed in `claude-config`,
not the Cognito repo (the files are untracked there).

### Part C — Register the KPI

Draft one new `docs/kpi/registry.json` row (full D2 schema, promoted at spec-finalization via
`kpi-scorecard.py --promote-drafted-rows`) measuring the auto-loaded corpus byte count. Baseline
50,182 B captured today; direction down-is-good; band alerts on regrowth past a threshold above the
post-trim target. Measurement is a pure `wc -c` sweep of the 12 files — no runner, no model in the
loop.

## Implementation Phases

- **Phase 0 — Prescription rewrite (Part A).** Rewrite `claude-md-review.md`: invert default, import
  the generalization test + durability checklist, promote the escape hatch, add `CLAUDE.local.md` to
  target lists and the orchestrator write-carve-out lines. Add parity notes between the component and
  `/retro`. No consumer-skill edits needed (they inherit). Verify by reading each of the ~9 consumers
  to confirm the inherited text reads correctly in context.
- **Phase 1 — Trim the backend + root files (Part B, batch 1).** Root `CLAUDE.local.md`, `Cognito/`,
  `Cognito.Core/`, `Cognito.Services/`, `Cognito.UnitTests/`, `Cognito.QueueJob/`. Apply rubric; fix
  the two live defects; standardize footer.
- **Phase 2 — Trim the frontend files (Part B, batch 2).** `Cognito.Web.Client/` + `apps/spa`,
  `apps/client`, `libs/model.js`, `libs/types`, `libs/vuemodel`. Apply rubric; standardize footer;
  resolve the element-ui-fork ×3 and server-types ×2/×3 duplications down to one authoritative
  statement + pointers.
- **Phase 3 — Register + baseline the KPI (Part C).** Confirm the drafted row promoted into
  `registry.json`; capture the post-trim byte count; set the band.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Corpus is trimmed to target | after Phases 1–2 | `wc -c` sum of the 12 files ≈ 34 KB (≥ 30% reduction from 50,182 B) | shell `wc -c` over the 12 paths |
| No file loses a durable gotcha | after Phases 1–2 | every DURABLE row from the audit still present (spot-check the incident-anchored ones: GetFieldPath/ModelSource, Stripe await-before-cast, flush-per-iteration, DequeueCount off-by-one) | diff each file vs. pre-trim |
| The false purge claim is gone | after Phase 1 | no "zero matches repo-wide" / "no PurgeOrganizationException" text in `Cognito/CLAUDE.local.md` | grep the file |
| Footer standardized | after Phases 1–2 | all 12 files carry the `Maintenance:` meta-rule footer | grep for footer marker across the 12 |
| Prescription inverts the default | after Phase 0 | `claude-md-review.md` leads with "no update expected" framing + contains the 4-question test | read the component |
| KPI row is measurable | after Phase 3 | `kpi-scorecard.py --capture-baseline claude-md-corpus-bytes` resolves and writes a value | run the subcommand |

## Locked Decisions

| ID | Decision |
|----|----------|
| L1 | **Prescription fix = invert default + import `/retro`'s test** (not: add another durability rule — that already exists and lost; not: delete the prescription and route via `/retro` only — loses in-the-moment capture of durable gotchas; not: byte-budget lint — byte count can't distinguish durable from bloat). |
| L2 | **AGENTS.md ↔ CLAUDE.local.md build-command contradiction left as-is** — not resolved in this spec. Field evidence: agents have been reliably choosing `/msbuild`/`/mstest` over the raw `dotnet` commands AGENTS.md prescribes. Recorded here so it is not "rediscovered" and mistakenly fixed later; AGENTS.md is correct for teammates/Copilot who have neither the skills nor the hook. |
| L3 | **`.agents/agent-docs/` overlap → pointers.** Where agent-docs covers a topic equal-or-better, the `CLAUDE.local.md` replaces its restatement with a one-line pointer. Cuts auto-loaded tokens every session and kills the divergent testing-conventions advice. |
| L4 | **Cleanup scope = all 12 files, one trim pass** (not just the 6 offenders — leaves the root file's actively-wrong inventories; not scratch-rewrite — 67% is already durable and incident-earned). Plus standardize the `Maintenance:` footer onto all 12. |
| L5 | **"Key Files" / API-catalog inventory tables → delete** (largest bloat class, ~9 KB; they go stale silently — all three current inventories already omit real dirs; recoverable via Glob/tree-sitter). |
| L6 | **Success KPI = auto-loaded corpus bytes** (mechanical `wc -c`; baseline 50,182 B; down-is-good; band on regrowth). Durable-ratio deferred — needs a model pass every measurement. |

## KPI Declaration

```json
{
  "id": "claude-md-corpus-bytes",
  "system": "claude-md-maintenance",
  "title": "Cognito CLAUDE.local.md auto-loaded corpus size",
  "friction": "Every Cognito Forms session auto-loads all 12 CLAUDE.local.md files; non-durable bloat (inventory tables, validation-report prose, stale filesystem mirrors) inflates the per-session context cost and can be acted on wrongly when it is stale or false.",
  "signal": {
    "source": "sentinel-scan",
    "selector": "claude-md-corpus-bytes"
  },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": {
    "value": 40830,
    "captured_at": "2026-07-17",
    "window": "1d",
    "provenance": "measured"
  },
  "band": {
    "warn": 44000,
    "breach": 48000
  },
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "wc -c sum over the 12 Cognito Forms CLAUDE.local.md files (repos/cognito-forms/**/CLAUDE.local.md). Compute is wired (kpi-scorecard.py _sel_claude_md_corpus_bytes, sentinel-scan class) — a pure-read on-disk scan runnable on any host, no model in the loop. Pre-trim 50,182 B; post-trim measured 40,830 B (the rubric is the authority, not a byte target — Cognito.Core/Services were already-clean exemplars trimmed near-zero). Band set above the achieved 40,830: warn 44 KB absorbs ~3 KB of legit durable additions, breach 48 KB flags regression back toward the pre-trim 50 KB."
}
```

## Open Questions

_(resolved during Phase 3)_

- ~~Band thresholds are a first guess.~~ **Resolved:** post-trim measured 40,830 B (Phase 3);
  band recalibrated to warn 44 KB / breach 48 KB around the achieved value. The row renders GREEN.
- ~~The `sentinel-scan` selector has no wired compute yet.~~ **Resolved:** wired
  `_sel_claude_md_corpus_bytes` in `kpi-scorecard.py` (a pure-read `st_size` sum over
  `repos/cognito-forms/**/CLAUDE.local.md`); `--capture-baseline claude-md-corpus-bytes` now
  resolves and writes the value directly — no host dependency, no NO-DATA fallback.
- **Trim landed at 40,830 B, not the aspirational ~34 KB.** By design: `Cognito.Core` (90% durable)
  and `Cognito.Services` (94% durable) are reference exemplars, and the rubric forbids gutting the
  durable majority to hit a number. −18.6% with every incident-anchored gotcha preserved is the
  intended outcome; the byte target was always guidance, not a gate.

## Research References

Gemini deep research skipped — this is an internal codebase-survey + harness-prescription feature.
Two parallel evidence audits (2026-07-17) are the research substrate:
- **Prescription audit** — every `CLAUDE.md`/`CLAUDE.local.md` update-prescription across `claude-config`
  skills/components, classified A/B/C. Headline: all prescriptions name `CLAUDE.md`, none name
  `CLAUDE.local.md`; the shared leaf `claude-md-review.md` already carries the lean-and-durable rule.
- **Bloat audit** — all 12 files read in full and classified DURABLE/INVENTORY/IMPLEMENTATION-NOTE/STALE,
  with spot-verification against the working tree (surfaced the false `verified 2026-07-17` purge claim
  and the three stale filesystem inventories).
