# SPEC-Excerpt Scoped Plans — plans carry the SPEC rows they implement (`cognito-lanes-v3`)

> `/write-plan-cognito` plans now embed a per-phase `#### SPEC excerpts` block — verbatim quotes
> of the Locked Decision rows / requirements / acceptance criteria the phase's lanes implement,
> each tagged with its SPEC section — so the `/execute-plan` orchestrator never reads SPEC.md
> (a measured ~14–38KB read in nearly every mined session). The planner reads the full SPEC
> once at planning time; the executor works from excerpts with a targeted escalation path.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**
- `lean-plan-files` — kind: hard — Complete (the pointer-based `cognito-lanes-v2` plan format
  and versioned lane contract this feature extends to v3).

---

## Problem (mined 2026-07-09)

`attribute_predispatch.py` over 47 Cognito `/execute-plan` sessions: SPEC.md was read
pre-dispatch in 33 of 47 sessions, 6–38KB per session (typical 14–26KB) — e.g. the
notification-emails SPEC at ~22KB × 5 sessions, `79ed5a88` at 38KB. The executor needs only the
handful of requirement rows the current plan part implements; the surrounding narrative,
alternatives-considered, and other phases' decisions are planner-time content. The v2 plan
format already carried a `**SPEC.md references:** [sections]` field — a pointer that still
forces a file read; the sections it named were read whole.

## Locked Decisions

1. **LD1 — Excerpts ride in the plan, per phase.** Each per-phase plan section carries
   `#### SPEC excerpts (authoritative for this phase — executor does NOT read SPEC.md)`: one
   blockquote per requirement, quoted VERBATIM and tagged with its SPEC section heading / LD id.
   Sufficiency bar (drafting discipline in the skill): every LD row, requirement, and acceptance
   criterion the phase's lanes act on — but rows, not wholesale sections (wholesale quoting just
   relocates the bloat).
2. **LD2 — Targeted escalation, recorded.** The executor reads on-disk SPEC.md ONLY when an
   excerpt is ambiguous, contradicts observed code, or lacks context a lane needs — and then
   only the named section. Every escalation is recorded (with reason) in the phase's
   Implementation Notes: an escalation means the planner under-excerpted, and the record is the
   feedback signal.
3. **LD3 — Versioned as `cognito-lanes-v3`, backward compatible.** Plan header + pointer block +
   lane contract bump to v3; the contract's version note states the v2 fallback explicitly (a
   plan without excerpt blocks executes under the old rule: read the sections named by
   `SPEC.md references`). In-flight v2 plans keep executing unchanged.
4. **LD4 — Generic tier untouched.** `/write-plan` (generic) and `execution-contract.md` keep
   their current SPEC handling; the shared `source-reread.md` item 3 is written conditionally
   ("if the plan carries a SPEC-excerpts block…"), so generic plans are unaffected until the
   pattern is deliberately ported (follow-up).

## KPI Declaration

Drafted row (full schema; same measurement channel as the sibling features):

```json
{
  "id": "execute-plan-spec-read-bytes",
  "system": "write-plan-cognito",
  "title": "SPEC.md bytes read into the orchestrator before first dispatch",
  "friction": "SPEC.md read pre-dispatch in 33/47 mined Cognito execute-plan sessions, 6-38KB each (typical 14-26KB), for content reducible to the handful of requirement rows the plan part implements.",
  "signal": { "source": "session-log-mining", "selector": "predispatch-spec-read-bytes" },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": { "value": 15360, "captured_at": "2026-07-09", "window": "30d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "Baseline window: 47 execute-plan sessions 2026-06-09..07-09 (SPEC read in 33/47, 6-38KB each, median ~15K), mined via attribute_predispatch.py — the manual collector for the session-log-mining source (scorecard compute is honest NO-DATA until a collector is wired). Target: ~0KB on-disk SPEC reads for v3 plans in the happy path; each escalation is recorded in Implementation Notes, so escalation frequency doubles as the excerpt-sufficiency metric. Excerpt bytes added ~2-4KB/phase — net positive whenever the SPEC read exceeded that (held in every mined session)."
}
```

## What Shipped

| File | Change |
|------|--------|
| `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` | Per-phase template: `**SPEC.md references:**` replaced by the `#### SPEC excerpts` block + escalation rule; Step 3 gains the SPEC-excerpt drafting discipline paragraph; plan version + pointer block → `cognito-lanes-v3` |
| `repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` | Contract version → v3 (with explicit v2 fallback note); L.0 re-read sources SPEC content from the plan's excerpt block; L.1 lane-prompt item (2) forwards the excerpt block verbatim |
| `user/skills/_components/source-reread.md` | Item 3 rewritten excerpts-first with the conditional v2/generic fallback (LD4) |

## Validation Criteria — evidence

- [x] `project-skills.py` + `lint-skills.py` + `doc-drift-lint.py` all clean after the edits.
- [x] Backward compatibility: v2 fallback stated in the contract version note, the L.1 prompt
      rule, and `source-reread.md` item 3 — a v2 plan (no excerpt block) still resolves to a
      defined read path at every consumption site.
- [x] No lazy-parity coupled pair touched (`lazy_parity_audit` manifest does not cover these
      files; verified by inspection of the Coupled Skill Pairs table).
- [ ] Field verification (next `/write-plan-cognito` + `/execute-plan` cycle): the generated
      plan carries per-phase excerpt blocks; the executor makes zero full-SPEC reads; any
      escalation appears in Implementation Notes with a reason.

## Expected Impact

- ~14–26KB (≈3.5–6.5K tokens) removed from the typical Cognito `/execute-plan` session's
  pre-dispatch context, minus ~2–4KB of excerpt content added per plan phase (paid once, at
  planning time, where the full SPEC is already resident).
- Combined with `phases-slice-scoped-reads` + `execute-plan-skill-diet` (this session's set):
  expected ~15–25K tokens off the measured 131K median first-dispatch context. The remaining
  ~68K startup baseline (system prompt, tool/MCP schemas, plugin agents, CLAUDE.md chain) is
  untouched by all three and is the next investigation (`/context` snapshot in a live Cognito
  session).

## Out of Scope / Follow-ups

- Porting the excerpt pattern to the generic `/write-plan` (LD4).
- An excerpt-sufficiency lint (e.g. planner self-check that every lane's
  "Spec requirements" field cites an excerpt present in the block).
- The startup-baseline investigation (plugin/tool-schema audit) — separate feature.
