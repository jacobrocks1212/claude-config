# Subagent-written non-canonical blocker filenames are invisible to the state machine → infinite loop risk — Investigation Spec (stub)

> In a real `/lazy-batch` run, a cycle-subagent wrote its blocker file under a descriptive, date-suffixed name instead of the canonical `BLOCKED.md`. Because `lazy-state.py` keys halt detection on the exact filename `BLOCKED.md`, the halt was invisible and the state machine re-routed straight back to the same wall — an infinite-loop trigger that was only caught by chance.

**Status:** Investigating
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/noncanonical-blocker-filename-invisible-to-state-machine
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy-state.py` (halt detection keys on literal `BLOCKED.md`); cycle-subagent prompt in `user/skills/lazy-batch/SKILL.md`; `user/skills/_components/sentinel-frontmatter.md`.

---

## Verified Symptoms
1. **[OBSERVED in logs]** Subagent wrote a date-suffixed blocker name; halt went undetected and re-routed — session `8ae22371` @ ~line 134: "The subagent wrote the blocker as `BLOCKED_2026-06-09-track-source-silent.md` (date-suffixed) instead of `BLOCKED.md`, so lazy-state doesn't see the halt and re-routes to mcp-test — which would loop on the same silent-source wall."

## Evidence Collected (from session logs)
- session `8ae22371` @ ~line 134 — "The subagent wrote the blocker as `BLOCKED_2026-06-09-track-source-silent.md` (date-suffixed) instead of `BLOCKED.md`, so lazy-state doesn't see the halt and re-routes to mcp-test — which would loop on the same silent-source wall." — Interpretation: a non-canonical blocker filename bypasses literal-filename halt detection, so the state machine never sees the halt and re-dispatches into the same wall.

## Why this is friction
`lazy-state.py` keys halt detection on the exact filename `BLOCKED.md`; a descriptive or date-suffixed name means the halt is invisible and the state machine re-routes to the same wall — an infinite-loop trigger. The orchestrator only caught it by chance (it happened to read the directory); nothing mechanical enforced the filename contract at write time, so autonomy depends on luck rather than a gate.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Should the filename contract be enforced mechanically at write time (e.g., a hook or sentinel-frontmatter validation), or should halt detection be broadened to recognize blocker variants?
- What naming variants are subagents actually producing, and where in the prompt/contract does the canonical-name expectation get lost?
- If detection is broadened, how does the state machine avoid mistaking unrelated `BLOCKED_*` artifacts for active halts?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
