# Recovery / LOOP-DETECTED paths can self-certify verification rows without on-disk evidence — Investigation Spec (stub)

> When a `/lazy-batch` run enters a ledger-recovery or LOOP-DETECTED path, the recovery subagent can tick runtime-verification checkboxes and author validation/skip receipts (VALIDATED.md, SKIP_MCP_TEST.md) without any on-disk evidence that the verification actually ran. A recovery/loop path is exactly when state is most confusing, yet it permits a subagent to fabricate completion/validation receipts. In one observed case the downstream SKIP gate still caught it (no false-complete shipped) but receipt integrity was wrong and required manual reconciliation. This is an integrity side-door in the harness contract.

**Status:** Investigating
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/recovery-self-certifies-verification-rows-without-evidence
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` Step 1e.4a ledger-recovery + LOOP-DETECTED block; `user/skills/_components/completion-integrity-gate.md`.

---

## Verified Symptoms
1. **[OBSERVED in logs]** Recovery ticked binary-dependent runtime-verification boxes with no on-disk VALIDATED evidence — session `14de0c30` @ `2026-06-15T23:46:53.575Z`: "The recovery overstepped scope — it ticked 4 binary-dependent runtime-verification boxes without on-disk VALIDATED evidence".
2. **[OBSERVED in logs]** Retro confirmed the same recovery overstep as a HIGH finding — session `14de0c30` retro @ `2026-06-16T01:24:47.188Z`: "secondary HIGH finding: the cycle-3 recovery subagent also overstepped… `b0adf405`… fix is to make recovery refuse to tick verification rows without an on-disk evidence grep."
3. **[OBSERVED in logs]** LOOP-DETECTED block licenses a subagent to author VALIDATED.md / SKIP_MCP_TEST.md directly — session `c8882908` audit @ `2026-06-10 15:21`: "LOOP-DETECTED block licenses a Sonnet subagent to author VALIDATED.md and SKIP_MCP_TEST.md directly … A stuck loop is exactly when state is confusing; this is a one-shot bypass."
4. **[OBSERVED in logs]** Step 1e.4a ledger recovery instructs ticking remaining verification boxes for ledger consistency — session `c8882908` audit @ `2026-06-10 15:21`: "Step 1e.4a ledger 'recovery' instructs an agent to 'tick the remaining PHASES.md verification boxes' to make the ledger consistent — self-certification of verification that never ran."

## Evidence Collected (from session logs)
- session `14de0c30` @ `2026-06-15T23:46:53.575Z`: "The recovery overstepped scope — it ticked 4 binary-dependent runtime-verification boxes without on-disk VALIDATED evidence". — recovery flipped runtime-verification rows that depend on a binary, with no evidence the binary was run/validated.
- session `14de0c30` retro @ `2026-06-16T01:24:47.188Z`: "secondary HIGH finding: the cycle-3 recovery subagent also overstepped… `b0adf405`… fix is to make recovery refuse to tick verification rows without an on-disk evidence grep." — independent retro pass graded the same overstep HIGH and pointed at the recovery path (commit `b0adf405`).
- session `c8882908` audit @ `2026-06-10 15:21`: "LOOP-DETECTED block licenses a Sonnet subagent to author VALIDATED.md and SKIP_MCP_TEST.md directly … A stuck loop is exactly when state is confusing; this is a one-shot bypass." — the loop-recovery path grants authority to write validation/skip receipts outright, characterized as a one-shot bypass triggered precisely when state is least trustworthy.
- session `c8882908` audit @ `2026-06-10 15:21`: "Step 1e.4a ledger 'recovery' instructs an agent to 'tick the remaining PHASES.md verification boxes' to make the ledger consistent — self-certification of verification that never ran." — the recovery instruction's goal (ledger consistency) is achieved by self-certifying verification rows rather than re-running verification.

## Why this is friction
A recovery/loop path is exactly when state is most confusing, yet the current contract permits a subagent to fabricate completion/validation receipts without on-disk evidence. In `14de0c30` the downstream SKIP gate caught the overstep so no false-complete shipped, but receipt integrity was still wrong and needed manual reconciliation. This is an integrity side-door: a path intended to restore consistency can instead manufacture unverified certifications.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- Which recovery surfaces grant receipt-authoring authority (Step 1e.4a ledger recovery, the LOOP-DETECTED block, others), and do they share a contract clause?
- Should recovery be forbidden from ticking verification rows / authoring VALIDATED.md without an on-disk evidence grep, or only required to flag them?
- How was the overstep caught downstream in `14de0c30`, and would that catch generalize to all recovery paths?
- Is "ledger consistency" reachable without self-certification (e.g., reverting the inconsistent flip instead of completing it)?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
