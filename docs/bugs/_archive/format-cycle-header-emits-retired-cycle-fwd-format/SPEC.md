# format_cycle_header emits the retired `### Cycle fwd N/M · …` heading — Investigation Spec

> `lazy_core.format_cycle_header` (the forward-cycle `--probe` enrichment) emits
> `### Cycle fwd {fwd}/{max} · meta {meta} · {feature} · {sub_skill}` — a heading format the
> orchestrator contract **explicitly retired** and forbids from reappearing. The orchestrator
> echoes the probe's `cycle_header` verbatim, so the retired format lands on every forward cycle.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-12
**Placement:** docs/bugs/format-cycle-header-emits-retired-cycle-fwd-format
**Related:** `user/skills/lazy-batch/SKILL.md:1272` + `user/skills/lazy-bug-batch/SKILL.md:959` (the retirement clause); `user/skills/_components/orchestrator-voice.md` T2 (the `### {Step} — {summary} [{n}/{max}]` sanctioned shape + the probe-presence verbatim-echo guard); `lazy_core.emit_dispatch_prompt` (the META path, which already emits the sanctioned `### {Step} — {summary} [meta {m}]` shape).

---

## Verified Symptom

`lazy_core.format_cycle_header` returns
`### Cycle fwd {fwd}/{max} · meta {meta} · {feature} · {sub_skill}` (line ~6680). It is wired
into the `--probe --forward-cycles` enrichment on BOTH state scripts
(`lazy-state.py:12722`, `bug-state.py:7956`, via the shared helper) as `state["cycle_header"]`.

The orchestrator contract (`lazy-batch/SKILL.md:1272`, `lazy-bug-batch/SKILL.md:959`) states
verbatim: *"The retired formats — the `### Cycle fwd N/M · meta K/L` heading, the
`· {feature_name} · {sub_skill}` heading suffix … must NOT reappear."* The `orchestrator-voice.md`
T2 probe-presence guard mandates that a probe-carried `cycle_header` be **echoed verbatim** as the
cycle heading. Composition: the forward-cycle heading emitted to the operator/grader is the
retired format, on every forward cycle where a run marker is present.

The META dispatch path (`emit_dispatch_prompt`, line ~7517) already emits the SANCTIONED
`### {Step} — {summary} [meta {m}]` shape, so forward and meta headings are inconsistent AND the
forward one is explicitly forbidden.

## Root Cause

**Class: script-defect.** `format_cycle_header` was authored at WU-5 (2026-06-14) before the
heading contract was reshaped (T2 `### {Step} — {summary} [{n}/{max}]`) and the old format was
retired. The helper was never migrated to the sanctioned shape, and because its output is echoed
verbatim under the probe-presence guard, it re-emits the forbidden format rather than merely
storing dead text. Both scripts call the single shared helper, so there is no parity divergence to
reconcile — the one helper is the single fix site.

## Fix Scope

Reshape `format_cycle_header` to the sanctioned T2 forward shape, mirroring the meta path's
established convention (coarse verbatim summary; keeps the anti–record-vs-behavior verbatim-echo
mechanism intact rather than removing the header and reopening the headerless-forward R-V gap):

- Emit `### {Step} — {summary} [{fwd}/{max}]`:
  - `{Step}` derived from `sub_skill` via a new `SUB_SKILL_STEP_NAMES` map (sibling of
    `DISPATCH_STEP_NAMES`; canonical T2 names Spec / Investigate / Plan / Implement / Retro /
    Validate / Realign / Research / Mark Complete / Mark Fixed; unmapped → the normalized
    sub_skill, `Cycle` when sub_skill is absent).
  - `{summary}` = `feature_id` or the `—` sentinel.
  - counter `[{fwd}/{max}]`, `?` placeholders when a counter is None.
- Update the two `test_lazy_core.py` characterization tests
  (`test_format_cycle_header_full`, `test_format_cycle_header_missing_fields`) to the new shape.
- Shared `lazy_core` change ⇒ both pipelines inherit it; no coupled-pair script mirror owed.
  The retired `· … ·` suffix is eliminated. Byte-pinned smoke baselines do NOT contain
  `Cycle fwd` (verified) — no baseline regeneration.
