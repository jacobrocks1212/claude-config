# Phases-Slice Scoped Reads — script-owned PHASES.md/IMPLEMENTATION_NOTES.md slicing (`phases-slice.py`)

> Replace the ignored-in-the-field prose mandate ("grep for phase headings, then ranged-Read")
> with a deterministic script: `user/scripts/phases-slice.py` prints a phase index + the one
> phase slice the executor needs (+ the IMPLEMENTATION_NOTES.md section index), so
> `/execute-plan` orchestrators stop reading 40–100KB PHASES.md files whole at startup, every
> batch boundary, and every compaction recovery.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:**
- `lean-plan-files` — kind: hard — Complete. Same investigation thread (`/mine-sessions`
  attribution over 47 Cognito `/execute-plan` sessions); this feature closes the #1 measured
  pre-dispatch Read.

---

## Problem (mined 2026-07-09, 47 sessions across Cognito Forms + -B/-C/-D worktrees)

`attribute_predispatch.py` (new `mine-sessions` toolkit script) attributed the median 131K-token
first-dispatch context: `tool:Read` is the largest conversation-window category (median
112KB/session), and **PHASES.md is the single largest contributor** — 462KB across 9 sessions of
one feature (~51KB per full read; per-session PHASES bytes ranged 5–118KB). Decisive detail: the
prose slice-read mandate (shipped 2026-06-29 in `plan-skills-redesign`, in both `/execute-plan`
and `source-reread.md`) did NOT change behavior — sessions dated 07-08/07-09 still read PHASES.md
whole (43K, 49K, 65K). Prose choreography ("grep, then offset/limit Read") loses to the
one-call convenience of a whole-file Read; per the harness constitution, deterministic behavior
belongs in a script.

The same mining motivated keeping IMPLEMENTATION_NOTES.md (~20KB/read, 3 sessions) referenced
but sliced: it is the cross-WU hiccup memory (operator-confirmed requirement) — its *reference*
stays mandatory at Step B.0/L.0 and in lane-prompt composition; only the read mechanics change.

## Locked Decisions

1. **LD1 — The scoped read is script-owned.** `user/scripts/phases-slice.py` (stdlib-only, pure
   read, UTF-8-safe) prints: preamble PREVIEW (line- and char-capped, with explicit
   "range-Read for full content" escape hatch), phase index (heading, 1-based line range,
   `**Status:**`, checkbox tally `done/total`), the requested (`--phase <id>`, repeatable) or
   active (first with an unchecked deliverable) phase's FULL slice, and — when a sibling
   `IMPLEMENTATION_NOTES.md` exists — its per-phase section index. `--checklist` prints only a
   phase's checkbox lines (the cloud-saturation / completion-audit view); `--notes <id>|all`
   appends notes sections; `--index-only` suppresses bodies. Exit 0/1/2 (ok / file error /
   phase-not-found).
2. **LD2 — The phase boundary is the canonical marker, copied byte-identically.**
   `lazy_core._PHASE_HEADING_RE` (`^#{2,3}\s+Phase\s+…`) — the same regex `parse_phases()`
   keys off — so the slice anchor and the harness's phase counter can never disagree. The
   script stays import-free of `lazy_core` (usable on machines with only `~/.claude/scripts/`
   materialized); the sync obligation is documented in both script tables.
3. **LD3 — Mandate sites now invoke the script, keeping grep+ranged-Read only as the fallback.**
   Rewired: `source-reread.md` ("PHASES.md slice read" section — consumed by BOTH the generic
   Step B.0 and the Cognito lane Step L.0), `/execute-plan` (the slice-handling section, the
   Step 1a.6 cloud-saturation checklist enumeration via `--checklist`, and Compaction Recovery
   item 5), and the lane contract's L.0/L.1 (notes slicing via `--notes <id>` for lane prompts).
4. **LD4 — IMPLEMENTATION_NOTES.md keeps its pipeline slots** (operator decision, this session):
   referenced at Step B.0/L.0 (per-batch source re-read, sibling-then-embedded order) so later
   WUs don't repeat earlier WUs' hiccups, and forwarded into lane-agent prompts at L.1 item 3.
   The script's section index + `--notes <id>` slicing makes those reads scoped instead of
   whole-file.

## KPI Declaration

Drafted row (full schema; not yet registered in `docs/kpi/registry.json` — the signal source is
the session-log corpus via `attribute_predispatch.py`, an on-demand miner, not a state-script
collector):

```json
{
  "id": "execute-plan-phases-read-bytes",
  "system": "execute-plan",
  "title": "PHASES.md bytes read into the orchestrator before first dispatch",
  "friction": "Median 131K-token first-dispatch context in Cognito /execute-plan sessions; PHASES.md whole-file reads were the #1 Read contributor (~51KB per read on mature features, repeated at batch boundaries and compaction recoveries).",
  "signal": { "source": "session-log-mining", "selector": "predispatch-phases-read-bytes" },
  "unit": "bytes",
  "direction": "down-is-good",
  "baseline": { "value": 22528, "captured_at": "2026-07-09", "window": "30d", "provenance": "measured" },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "Baseline window: 47 execute-plan sessions 2026-06-09..07-09 (median per-session PHASES bytes ~22K; max 118K), mined via mine-sessions attribute_predispatch.py — the manual collector for the session-log-mining source (compute is honest NO-DATA in the scorecard until a collector is wired). Target: index+slice output 5-15KB on a 51KB file (measured: default 15.5K incl. preamble preview; --phase N --no-preamble <10K; --checklist ~3-13K). Re-measure over post-2026-07-09 sessions."
}
```

## What Shipped

| File | Change |
|------|--------|
| `user/scripts/phases-slice.py` | **NEW** — the deterministic slice reader (LD1/LD2) |
| `user/scripts/test_phases_slice.py` | **NEW** — 13 unit tests (parsing boundaries/tallies, non-phase headings, active-phase selection, `--phase`/`--index-only`/`--checklist`/`--notes`, feature-dir target, exit codes) |
| `user/skills/_components/source-reread.md` | Slice-read section rewritten script-first (grep fallback retained); prior-notes item reworded to name its purpose (don't repeat earlier WUs' hiccups) |
| `user/skills/execute-plan/SKILL.md` | Scoped-read section + Step 1a.6 + Compaction Recovery now invoke the script (part of the parallel `execute-plan-skill-diet` rewrite) |
| `repos/cognito-forms/.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` | L.0 re-read + L.1 lane-prompt notes sourcing route through the script |
| `CLAUDE.md`, `user/scripts/CLAUDE.md` | Script-table rows (doc-drift-lint-checked) |
| `user/skills/mine-sessions/scripts/attribute_predispatch.py` (+ SKILL.md toolkit entry) | **NEW** — the measurement tool that produced this feature's evidence; persisted per the mine-sessions toolkit contract |

## Validation Criteria — evidence

- [x] `python user/scripts/test_phases_slice.py` — 13/13 OK.
- [x] Live trial on the worst measured file (notification-emails PHASES.md, 51,133 B / 1013
      lines / 17 phases incl. dotted ids "3.5"/"4.6"): default scoped output 15,464 B;
      `--index-only` 10,747 B; `--phase 5 --checklist` 13,323 B; dotted-id selection works;
      IMPLEMENTATION_NOTES.md index emitted.
- [x] `project-skills.py` (89 skills, 97 components, all projections) + `lint-skills.py` +
      `doc-drift-lint.py --repo-root .` (4 checks, 0 drift) — all clean after the rewiring.
- [ ] Field verification (next real `/execute-plan` run in Cognito Forms): orchestrator calls
      `phases-slice.py` instead of whole-file PHASES.md Reads; re-run `attribute_predispatch.py`
      over post-07-09 sessions and compare the `read:*PHASES.md` contributor line.

## Expected Impact

- ~51KB → ~5–15KB per PHASES.md consultation on mature features (≥70% reduction), applied at
  startup + every batch boundary + every compaction recovery. Against the mined corpus median
  that is roughly 3–8K tokens per session of the ~63K-token pre-dispatch delta.
- Honesty note: the prose mandate failed twice (06-29 ship, still violated 07-08/07-09); the
  bet here is that a one-command path gets followed because it is *easier* than the whole-file
  Read, not just mandated. The field-verification box above is the test of that bet.

## Out of Scope / Follow-ups

- Registering the KPI row with an automated collector (needs a state-script-adjacent signal).
- A `--json` output mode for machine consumers (only human/agent-readable text ships).
- Teaching `lazy_core` to import/export the shared regex from one home (currently documented
  byte-identical copy).
