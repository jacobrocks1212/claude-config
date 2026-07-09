# Execute-Plan Skill Diet — halve the executor's resident body (44.7KB → 22.7KB)

> `/execute-plan`'s SKILL.md body expands verbatim into every executing session's context
> (measured: ~52–59KB of user-text in all 47 mined Cognito sessions — the second-largest
> attributable pre-dispatch cost). Rewrite it as a lean executor-specific layer over the
> execution contract: dedupe contract restatements, compress incident-rationale prose to the
> rules + citations, move AlgoBooth-only policy to a per-repo skill-config injection, and move
> the completion-report templates to a completion-time component read from disk.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**
- `lean-plan-files` — kind: hard — Complete (established the pointer/contract architecture and
  removed the `!cat subagent-review.md` injection this rewrite builds on).
- `phases-slice-scoped-reads` — kind: hard — Complete (the script the rewritten scoped-read
  sections point at).

---

## Problem (mined 2026-07-09)

Every one of the 47 mined `/execute-plan` sessions carried a ~52–59KB user-text turn — the
expanded SKILL.md body (verified by turn inspection: session `036a133f`, 59,404 B, begins "Base
directory for this skill: …/execute-plan") — resident from turn 1 to end-of-session and re-paid
after every compaction. Much of it duplicated the single-sourced
`~/.claude/skills/_components/execution-contract.md` the skill itself orders the executor to
read (role tables, component-loading rules, review-gate prose), carried AlgoBooth-only policy
into every repo's sessions (workspace-QG command mapping, the F8 MCP scenario lint), and inlined
completion-report templates needed only in the run's final minutes.

## Locked Decisions

1. **LD1 — The skill is the executor-specific layer ONLY.** Everything the execution contract
   already owns (execution model, component loading, per-batch protocol, blocking protocol) is
   referenced, not restated. What stays inline: the four hard requirements, batch mode, the
   Step 1 gates (status protocol / part-integrity / cloud-saturation / run marker), task
   tracking, the golden rule, contract pointers + precedence, scoped PHASES.md reads, the
   enforcement trip-wire + dispatch census, the per-step protocol glue (drift reconciliation,
   review gate, WU-checkbox/PHASES.md dual ledger, atomic gate+commit), halt handling, Step 4
   completion rules, compaction recovery. Every rule and incident citation survives; only
   rationale prose is compressed.
2. **LD2 — Repo-specific policy moves to per-repo skill-config injection.** New injection point
   `!cat .claude/skill-config/execute-plan-repo-gates.md || <fallback comment>` (same pattern as
   `cog-doc-track-open` / `post-phase-code-review-checkpoint`). The AlgoBooth QG-escalation
   command mapping + F8 MCP scenario surface lint (~3.4KB) relocate to
   `repos/algobooth/.claude/skill-config/execute-plan-repo-gates.md`; the generic
   escalation/batch-frequency rules were already in `quality-gates.md` (verified — no rule loss).
   Non-AlgoBooth sessions now expand a one-line comment instead.
3. **LD3 — Completion-report templates become a completion-time component.**
   `~/.claude/skills/_components/execution-completion-summary.md` (NEW) carries the Step 4b/4c/4d
   templates (behavior-enabled summary, conditional feature-level summary, dispatch + QG census);
   the skill keeps a 3-line MANDATORY read instruction. The census requirement (including the
   lane-plan both-kinds counting rule) is preserved verbatim in the component.
4. **LD4 — Scoped-read sections delegate to `phases-slice.py`** (see
   `phases-slice-scoped-reads`) instead of restating grep choreography.

## KPI Declaration

Drafted row (full schema; signal = projected skill size on disk, trivially re-measurable):

```json
{
  "id": "execute-plan-resident-skill-bytes",
  "system": "execute-plan",
  "title": "Bytes of /execute-plan skill body resident per executing session",
  "friction": "The expanded SKILL.md was ~52-59KB of user-text in 100% of mined sessions (~13-15K tokens), resident pre-dispatch and re-paid across compactions.",
  "signal": { "source": "session-log-mining", "selector": "predispatch-skill-body-bytes" },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": { "value": 52224, "captured_at": "2026-07-09", "window": "30d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "all",
  "notes": "Baseline = median user-text bytes/session (the expanded skill body dominates it) over the 30d mined corpus, via attribute_predispatch.py — the manual collector for the session-log-mining source (scorecard compute is honest NO-DATA until a collector is wired). Deterministic proxy: source SKILL.md 44,726 B pre-rewrite -> 22,678 B post; projected _default 44,694 -> 22,798; projected Cognito Forms 26,065 (repo injections inlined, AlgoBooth blocks correctly absent). Guard: additions to this skill go to the contract/components/repo-config unless genuinely executor-specific."
}
```

## What Shipped

| File | Change |
|------|--------|
| `user/skills/execute-plan/SKILL.md` | Full rewrite, 460 → ~250 lines / 44,726 → 22,678 B (−49%). All gates/rules/citations preserved; contract restatements deduped; scoped reads via `phases-slice.py` |
| `repos/algobooth/.claude/skill-config/execute-plan-repo-gates.md` | **NEW** — relocated AlgoBooth QG-escalation mapping + F8 scenario lint (LD2) |
| `user/skills/_components/execution-completion-summary.md` | **NEW** — Step 4b–4d completion templates + census (LD3), read at completion time only |

## Validation Criteria — evidence

- [x] `project-skills.py` clean (89 skills, 97 components); `lint-skills.py` OK (no broken/embedded
      `!cat`); `doc-drift-lint.py` 0 findings.
- [x] Projection check: `_default` and `Cognito Forms` projections expand the new injection to
      the fallback comment (AlgoBooth-only policy no longer reaches other repos' sessions);
      Cognito projected body 26,065 B vs ~58.5KB pre-lean-plan-files.
- [x] Rule-preservation review: the four hard requirements, 1a.5/1a.6/1a.6a gates, marker
      lifecycle, WU-checkbox machine-source-of-truth rule, ground-truth review gate, SEAM B
      bug-completion bar, runtime/MCP-gate flip rule + backstop note, atomic gate+commit
      3-step sequence, and census reporting all present in the rewritten body (or the LD3
      component).
- [ ] Field verification (next `/execute-plan` run): executor reads the completion-summary
      component at Step 4 and emits all three blocks; AlgoBooth cloud run picks up
      `execute-plan-repo-gates.md` (see follow-up below).

## Expected Impact

- −22KB (~5.5K tokens) resident in every `/execute-plan` session in every repo, from the skill
  body alone; Cognito sessions additionally shed the AlgoBooth-only ~3.4KB.
- Cumulative with `lean-plan-files`: the executor-side fixed cost fell from ~58.5KB (pre-06-29
  projected, with the `subagent-review.md` injection) to ~26KB projected in Cognito.

## Out of Scope / Follow-ups

- **AlgoBooth pickup path:** `repos/algobooth/` has no `manifest.psd1` Repos entry (live repo
  deleted locally — deliberate divergence). The new skill-config file reaches AlgoBooth cloud
  sessions only if that environment materializes `repos/algobooth/.claude/` (as it does for the
  lazy-cloud skills); verify on the next nightly AlgoBooth run — the graceful fallback (comment +
  generic `quality-gates.md` rules) means a miss degrades politely, not silently wrong.
- Applying the same diet to other large always-expanded skills (audit candidates via
  `skill-usage-miner.py` + projected sizes).
