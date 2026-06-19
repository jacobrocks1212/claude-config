# LOOP-DETECTED tripwire fires on benign re-probes, runtime reboots, and intervening resolutions — Investigation Spec (stub)

> In real `/lazy-batch` runs, the `step_repeat_count` / HEAD-aware loop tripwire fires on benign churn — repeated probes for the same cycle, runtime reboot turns with no commits, and needs-input resolutions that don't reset the streak. The orchestrator is then forced to stop and justify or inspect a false loop signal, even though no actual no-progress loop is occurring.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/loop-detected-false-positives-from-probe-and-reboot-churn
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy_core.py` (`step_repeat_count` / HEAD-aware repeat counter); `user/skills/lazy-batch/SKILL.md` Step 1d loop-guard.

---

## Verified Symptoms
1. **[OBSERVED in logs]** Tripwire trips on a fully-understood benign cause — session `e076ed30` @ 2026-06-12T14:38:27: "step_repeat_count has reached the tripwire — but the cause is fully understood and benign".
2. **[OBSERVED in logs]** Re-probes across reboot turns counted as a streak though no cycle ran — session `e076ed30` @ 2026-06-13T03:13:58: "the mcp-test cycle has never actually run (I re-probed across reboot turns with no commits landing, which is exactly what the HEAD-aware streak counts)".
3. **[OBSERVED in logs]** Intervening needs-input resolution does not reset the streak — session `e076ed30` @ 2026-06-12T20:44:53: "the LOOP-DETECTED framing is a step-counter artifact (the intervening needs-input resolution didn't reset the streak)".
4. **[OBSERVED in logs]** Two `--repeat-count` probes for one cycle advance the per-step counter — session `2f6f27dc` @ ~07:23: "Spurious loop-streak from my probe hygiene. My first execute-plan probe this cycle … used --repeat-count but I discarded its cycle_prompt and re-probed to recover it — two --repeat-count probes for one cycle with no commit between advanced the per-step repeat counter."
5. **[OBSERVED in logs — related masking pattern, not a separate bug]** Forward HEAD movement (commits landing on doc fixes) masks no-progress routing loops, so the step-repeat tripwire is the only thing that catches them.

## Evidence Collected (from session logs)
- session `e076ed30` @ 2026-06-12T14:38:27 — "step_repeat_count has reached the tripwire — but the cause is fully understood and benign". — Interpretation: tripwire fired on a known-benign condition.
- session `e076ed30` @ 2026-06-13T03:13:58 — "the mcp-test cycle has never actually run (I re-probed across reboot turns with no commits landing, which is exactly what the HEAD-aware streak counts)". — Interpretation: reboot-turn re-probes with no commits inflate the HEAD-aware streak.
- session `e076ed30` @ 2026-06-12T20:44:53 — "the LOOP-DETECTED framing is a step-counter artifact (the intervening needs-input resolution didn't reset the streak)". — Interpretation: a needs-input resolution between steps should break the streak but doesn't.
- session `2f6f27dc` @ ~07:23 — "Spurious loop-streak from my probe hygiene. My first execute-plan probe this cycle … used --repeat-count but I discarded its cycle_prompt and re-probed to recover it — two --repeat-count probes for one cycle with no commit between advanced the per-step repeat counter." — Interpretation: probe-recovery hygiene double-counts a single cycle's probes.

## Why this is friction
The orchestrator is forced to stop and justify or inspect on a false loop signal; re-probes, reboots, and needs-input resolutions are counted as "no progress" even though the run is healthy. This costs autonomy (manual adjudication of a benign trip) and erodes trust in the one tripwire that catches genuine no-progress routing loops masked by forward HEAD movement.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Which events should reset the streak (needs-input resolution, reboot, probe-recovery re-probe) and which should not?
- How should a single cycle's multiple `--repeat-count` probes be deduplicated so probe hygiene doesn't inflate the counter?
- Can the HEAD-aware counter distinguish "re-probed across reboot, no commit" from a genuine no-progress loop without losing the masking-detection it currently provides?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
