---
kind: implementation-plan
feature_id: lazy-batch-skill-deflation
status: Draft
created: 2026-07-12
complexity: complex
phases: [1, 2]
---

> **Mobile plan** — generated 2026-07-12 for the WORK REMAINING after this feature's first
> session (which shipped Phase 3 — the size ratchet — and Phase 5 — three small follow-up
> items — plus ONE safe Phase-1 hotspot; see `COMPLETED.md`-pending / this session's final
> report for the full account). This plan covers ONLY what is left: the three deferred,
> dense Phase-1 hotspots + Phase 2 (HISTORY sidecar + long-line sweep).
> To execute: `/execute-plan docs/features/lazy-batch-skill-deflation/plans/remaining-hotspot-excision-plan.md`

# Implementation Plan — Remaining Hotspot Excision (lazy-batch-skill-deflation)

**PHASES.md:** `docs/features/lazy-batch-skill-deflation/PHASES.md` (Phase 1 remainder, Phase 2)
**SPEC.md:** `docs/features/lazy-batch-skill-deflation/SPEC.md`
**RESEARCH_SUMMARY.md:** `docs/features/lazy-batch-skill-deflation/RESEARCH_SUMMARY.md` — READ
FIRST. It documents WHY these three hotspots were deferred (they are denser / more
individually-incident-driven than the SPEC's original estimate) and sizes each at ~1 session.

## READ THIS FIRST — why this plan is conservative

The target file (`user/skills/lazy-batch/SKILL.md`) is the resident orchestrator prompt driving
an autonomous coding-agent pipeline in production use. A silently-dropped rule here is not a
cosmetic regression — it can corrupt the pipeline's routing or safety behavior with no visible
symptom until the exact case it covered recurs. **Do not batch all three hotspots into one pass.**
Do ONE hotspot per execution round, in this order (smallest/safest first):

1. §1c.5 — inline pseudo-skill handling (~18.5KB, lines ~533–577 as of 2026-07-12 — RE-LOCATE by
   heading, line numbers drift)
2. §1b/§1c.6 — terminal handling + PushNotification policy (~13.5KB + ~19KB, lines ~423–532)
3. §1d.0 — runtime pre-boot (~34KB, lines ~616–742 — the densest; do this LAST once the method
   is proven on the smaller two)

## MANDATORY method (per hotspot, per SPEC's Method section + D1)

1. **Re-read** the target section fresh (`Read` with `offset`/`limit` around the current heading
   — line numbers WILL have drifted since 2026-07-12; `grep -n "^### 1c\.5"` etc. to relocate).
2. **Build a rule-preservation checklist FIRST, before editing.** List every distinct
   rule/constraint/citation/edge-case in the section as a checklist item (one line each — e.g.
   "sub-case: HIJACKED never SIGKILLed", "cold-compile patient-wait uses the 90×5s ceiling, not
   the 5×backoff ceiling"). This checklist is the acceptance gate — do not skip it. Save it
   inline in this plan file (append under the relevant numbered hotspot below) or as a sibling
   artifact in `plans/`.
3. **Verify each rule's script-side owner** (a verdict field, a named config key, a specific
   `lazy_core` function) per D1's five-part rewrite rule: (1) trigger, (2) invocation, (3) a
   routing table over the EMITTED fields, (4) hard constraints binding orchestrator behavior,
   (5) one-line incident citations (`(burned: <slug>)`) where a rule exists because of a named
   incident — moving the narrative to `user/skills/lazy-batch/HISTORY.md` (Phase 2, D2 — the
   ratified sidecar; create it on the FIRST hotspot that has an incident to relocate, keyed by
   rule id/section).
4. **Rewrite**, then **diff the checklist against the rewritten text** — every item must still be
   present (as a rule, a citation, or a routing-table row). Nothing may silently disappear.
5. **Mirror into `lazy-batch-cloud`** per its existing divergence table for this section (grep
   the equivalent heading/paragraph there — do NOT assume the section boundaries match
   `lazy-batch`'s; the cloud file's own structure/tabulated divergences govern what to mirror vs.
   skip). `lazy-bug-batch` has no analog for §1c.5/§1b/§1c.6/§1d.0 as of 2026-07-12 (its own
   equivalent machinery is bug-pipeline-shaped) — grep first; do not assume.
6. **Regenerate + verify gates** (same sequence every round):
   ```bash
   python user/scripts/generate-coupled-skills.py --extract
   python user/scripts/generate-coupled-skills.py --check          # must be green
   python user/scripts/lazy_parity_audit.py --repo-root .           # exit 0
   python user/scripts/project-skills.py                            # clean
   python user/scripts/lint-skills.py --check-projected --check-capabilities --check-skill-size
   ```
   The skill-size ratchet (`skill-size-baseline.json`) will likely FAIL after a real excision —
   that's backwards from growth, so it means you improved: run
   `python user/scripts/skill-size-ratchet.py --lock-in user/skills/lazy-batch/SKILL.md` (and
   the cloud twin) to lower the ceiling to the new, smaller size. If it reports OVER-CEILING
   instead, you added bytes — investigate before proceeding (the whole point of Phase 3 is to
   catch exactly this).
7. **Commit each hotspot separately** (do not squash three risky edits into one commit — if a
   rule-preservation gap surfaces later, `git bisect`/revert needs to isolate one hotspot).

## Phase 2 (HISTORY sidecar) — runs ALONGSIDE the hotspot work, not after

Do not batch Phase 2 as a separate pass at the end — relocate each hotspot's dated "Motivating
incident" narrative to `HISTORY.md` in the SAME round that hotspot is excised (step 3 above).
After all three hotspots land, do one final long-line sweep pass over the rest of the file
(paragraphs not covered by the four named hotspots) using the same per-paragraph method,
re-running the byte/long-line census (`RESEARCH_SUMMARY.md`'s method) to confirm the SPEC's
target (`≤ ~150KB`, from 251,832 B pre-diet) is being approached.

## Completion

When all three hotspots + Phase 2 land: tick the corresponding PHASES.md checkboxes with
evidence (before/after byte counts per file, per the pattern this session's PHASES.md Phase 1/3
already establish), re-run the FULL gate suite one more time, and only then consider whether
`NEEDS_INPUT_PROVISIONAL.md` (D2) is ready for operator ratification — completion is blocked
until it is ratified (park-provisional contract), regardless of how much of the content diet
has landed.

## Work Units

- [ ] WU-1 excise §1c.5 hotspot per the method above (deferred — not executed this run)
- [ ] WU-2 excise §1b/§1c.6 hotspot (deferred)
- [ ] WU-3 excise §1d.0 hotspot (deferred)
- [ ] WU-4 mirror all excisions into lazy-batch-cloud + lazy-bug-batch, refresh overlays, ratchet baselines downward (deferred)

> Retroactive checklist added 2026-07-13 (plan predates the plan-structural gate landing mid-run); states reflect actual execution.
