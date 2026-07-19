# /execute-plan Strict-Order Prerequisite Audit Orders by Raw Part-Number, Ignoring `series_index` Reschedules — Investigation Spec

> The /execute-plan rule 1a.6a strict-order prerequisite audit ("for a `Plan series` mandating strict order, every prerequisite part must be `status: Complete` before a later part") is prose-driven — the execute-plan subagent (and the orchestrator's cycle-base-prompt mirror) audit prerequisite-ness by RAW PART-NUMBER (filename `-part-K`), ignoring the plan frontmatter `series_index:` field that records operator reschedules. When a part is deliberately rescheduled to run LAST via a high `series_index`, the audit still treats it as an unmet prerequisite of the earlier-`series_index` (but higher-part-number) parts, and false-blocks them.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-19
**Placement:** docs/bugs/execute-plan-strict-order-prereq-ignores-series-index-reschedule
**Related:** `docs/specs/turn-routing-enforcement/` (harden stage — this spec is the Step-2.5 audit trail for harden Round 110); `user/scripts/lazy_core/docmodel.py` (`_plan_series_index` / `_plan_sort_key` — the ROUTING ordering primitive that ALREADY honors `series_index`, and whose semantics the fixed audit prose now mirrors); `user/scripts/validate-plan.py` Rule 5 (`rule_series_dependency_order` — the authoring-side series-index closure)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** `hydra-overlay` (`docs/features/visuals/hydra-overlay`) part-10 carries frontmatter `series_index: 15  # RESCHEDULED: projector re-spike runs LAST (after parts 11-14) — operator decision 2026-07-19`, deliberately moving Phase 10 to execute LAST in the series. (Operator-reported incident, dispatch evidence for harden Round 110.)
2. **[VERIFIED]** Cycle-3's /execute-plan dispatch of part-12 audited part-10 as an unmet strict-order prerequisite purely because `part-number 10 < 12`, wrote `docs/features/visuals/hydra-overlay/BLOCKED.md` (`blocker_kind: prerequisite-part-incomplete`), and false-blocked part-12 — even though part-12's actual narrow entry criterion (Phase 11 preset schema/manager) was satisfied.
3. **[VERIFIED]** The ROUTING primitive is NOT the defect: `_plan_series_index` reads frontmatter `series_index` first (yaml.safe_load strips the inline `# RESCHEDULED …` comment), so `_plan_series_index(part-10)` returns `15` and `_plan_sort_key` orders part-12 (series 12) BEFORE part-10 (series 15). Confirmed empirically this investigation:
   ```
   series_index(part-10) = 15
   series_index(part-12) = 12
   sort_key(part-10) = (15, 10, 'all-phases-hydra-overlay-part-10.md')
   sort_key(part-12) = (12, 12, 'all-phases-hydra-overlay-part-12.md')
   part-12 sorts BEFORE part-10 (part-10 NOT a prereq of part-12): True
   ```
   So `find_implementation_plans` already routes the rescheduled part-10 last; the false-block is produced downstream by the SUBAGENT's own prose audit, which re-derives prerequisite ordering from filenames instead of trusting the series-index order.

## Root Cause

**Class: ambiguous-prose.**

The strict-order prerequisite audit has NO script that computes the prerequisite SET — it is a prose instruction executed by the /execute-plan subagent and mirrored in the orchestrator's cycle prompt:

- `user/skills/execute-plan/SKILL.md` rule 1a.6a #1 (line 73): "If the plan declares `> **Entry criteria:**` (or a `Plan series` preamble mandating strict order), verify every prerequisite part/phase is complete before ANY work."
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (workstation §skill-execute-plan lines 317-322; cloud §skill-execute-plan-cloud lines 344-349): "Check the dispatched part's `Plan series` 'execute parts strictly in order' prerequisites FIRST."

Neither prose site DEFINES which order determines "earlier"/"prerequisite" for a strict-order series. The subagent defaulted to the natural reading — raw part-number / filename order — and never consulted the frontmatter `series_index:` field that records the operator's reschedule. The `series_index:` field is authoritative for ROUTING (`_plan_sort_key` sorts by it FIRST), but the audit prose was never taught to use the same ordering.

The correct definition (operator-authorized 2026-07-19, 'Honor reschedule + harden audit'):

> For a strict-order `Plan series`, order parts by `series_index` when the field is present in a part's frontmatter, NOT raw part-number. A part **P** is a strict-order prerequisite of the dispatched part **D** iff `series_index(P) < series_index(D)` (same execution order `find_implementation_plans` routes by). A part rescheduled to run LAST (high `series_index`) is therefore NOT a prerequisite of earlier-`series_index` parts, even when its filename `-part-K` number is lower. Absent a `series_index` field, fall back to raw part-number — the current behavior, so un-rescheduled series are unaffected (no regression).

## Fix Scope

1. **Prose (primary):** rewrite `execute-plan/SKILL.md` rule 1a.6a #1 to define prerequisite-ness for a strict-order series by `series_index` execution order (frontmatter-honored), with the raw-part-number fallback stated explicitly.
2. **Mirror:** the same clarification in `cycle-base-prompt.md` workstation + cloud `skill-execute-plan[-cloud]` sections (coupled-prose lockstep).
3. **Producer note:** a one-line note on the `write-plan/SKILL.md` `Plan series` preamble that "Execute parts strictly in order" means `series_index` order (frontmatter override), so producers and readers share one definition.
4. **Regression test:** a `test_docmodel.py` case encoding the exact hydra-overlay scenario (part-10 `series_index: 15` with the inline `# RESCHEDULED` comment vs un-rescheduled part-12), asserting the high-`series_index` rescheduled part sorts AFTER — i.e. is not a prerequisite of — the lower-`series_index` later-part-numbered part, exercising the real `_plan_series_index` / `_plan_sort_key` production helpers the fixed audit prose now points to.

No script defect exists in the ordering primitive; no gate is weakened. The audit remains prose-driven — the fix makes the prose unambiguous and locks in the ordering primitive it depends on.
