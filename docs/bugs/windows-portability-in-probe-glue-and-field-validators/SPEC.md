# Windows path & line-ending portability defects in orchestrator probe glue and docs-consistency field validators — Investigation Spec (stub)

> During `/lazy-batch` runs on AlgoBooth (Windows), the orchestrator's probe glue writes `lazy-state.py` output to a POSIX `/tmp/` path and then reads it back with Windows-native Python, which has no `/tmp`, so the read crashes with `FileNotFoundError` and a redundant re-probe is forced. Separately, sentinel/plan files carrying a trailing carriage return (`\r`) fail the docs-consistency field validators on values that are otherwise legitimately correct, triggering mid-run normalization detours. Both are Windows-portability defects observed across multiple real runs.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/windows-portability-in-probe-glue-and-field-validators
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` probe glue; AlgoBooth `scripts/normalize-docs-consistency.ts` / `qg:docs-consistency`; `user/hooks/fix-line-endings.ps1`; `user/skills/_components/lazy-preflight.md`

---

## Verified Symptoms
1. **[OBSERVED in logs]** Probe round-trip via `/tmp/` crashes on Windows-native Python (STILL LIVE — hit today 2026-06-19) — session `80dbeeaf` @ `2026-06-19T14:37:56.491Z`: "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/probe.json'".
2. **[OBSERVED in logs]** Orchestrator recovery confirms the cross-convention root cause — session `80dbeeaf` @ `2026-06-19T14:38:15`: "The temp-file path crossed Git-Bash/Windows-python conventions. Re-running the probe directly."
3. **[OBSERVED in logs]** CRLF (`\r`) contamination fails field-type validators on otherwise-valid values (observed 2026-06-08; verify still live) — session `f2437fdb` @ `2026-06-08T17:40:34`: "plan 'created' must match YYYY-MM-DD, got \"2026-05-18\r\"".

## Evidence Collected (from session logs)
- **Symptom A — `/tmp` probe round-trip (STILL LIVE):**
  - session `80dbeeaf` @ `2026-06-19T14:37:56.491Z` — "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/probe.json'"; recovery @ `14:38:15` — "The temp-file path crossed Git-Bash/Windows-python conventions. Re-running the probe directly." (Interpretation: probe JSON written to a POSIX `/tmp/` path then read back with Windows-native python that has no `/tmp`; forces a redundant re-probe.)
  - session `9d5b0983` @ `2026-06-16T17:11:03.962Z` — same "FileNotFoundError … '/tmp/probe.json'". (Interpretation: same defect, recurring across runs days apart.)
  - session `deb9f0cf` @ `2026-06-16T19:14:16` — "FileNotFoundError: '/tmp/probe.out'". (Interpretation: orchestrator redirects `lazy-state.py` output to `/tmp/probe.out` then reads it back with Windows-native python which has no `/tmp`.)
  - session `e076ed30` — 6 occurrences of `/tmp/probe*.json` FileNotFoundError (e.g. `2026-06-12T20:44:01` `/tmp/probe_clap.json`). (Interpretation: not a one-off; the pattern repeats many times within a single run.)
- **Symptom B — CRLF (`\r`) contamination fails field-type validators:**
  - session `f2437fdb` @ `2026-06-08T17:40:34` — "plan 'created' must match YYYY-MM-DD, got \"2026-05-18\r\"". (Interpretation: a trailing `\r` defeats a date-format validator on a correct date.)
  - session `f2437fdb` @ `2026-06-08T17:40:52` — "SKIP_MCP_TEST.md field 'skipped_by' must be one of {lazy | lazy-cloud}, got \"lazy\r\"". (Interpretation: trailing `\r` defeats an enum validator on a valid enum value.)
  - session `f2437fdb` @ `2026-06-08T18:05:07` / `18:32:29` — "MCP_TEST_RESULTS.md field 'total_count' must be an integer, got \"11\r\"" / "\"13\r\"". (Interpretation: trailing `\r` defeats an integer validator on valid integers, twice in one run.)

## Why this is friction
The probe round-trip defect wastes a probe cycle every time it fires (still happening 2026-06-19) because the orchestrator must detect the crash and re-probe directly. The CRLF contamination causes the docs-consistency field validators to reject sentinel/plan values that are actually correct, forcing mid-run normalization detours. Both are pure platform-portability defects — no feature logic is wrong — yet they consume orchestrator cycles on every occurrence.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Are both symptoms still live? A `lazy-preflight.md` component and a `fix-line-endings.ps1` PostToolUse hook already exist and may have partially addressed the CRLF (Symptom B) issue — confirm which of the two symptoms remain reproducible as of 2026-06-19.
- Symptom A was hit today (2026-06-19), so the `/tmp` round-trip appears unaddressed — confirm whether any preflight/probe-glue change is expected to have covered it.

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
