# Recovery / LOOP-DETECTED paths can self-certify verification rows without on-disk evidence — Investigation Spec

> When a `/lazy-batch` run enters a ledger-recovery or LOOP-DETECTED path, the recovery subagent could tick runtime-verification checkboxes and author validation/skip receipts (VALIDATED.md, SKIP_MCP_TEST.md) without on-disk evidence. **Investigation finding: both side-doors were already closed by two prior fixes (commits `dfbcfa0`, `3f6253f`); the observed incidents predate the landed guards.** Residual scope is a regression test that pins both guards on disk so they can't silently regress.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-06-19
**Fixed:** 2026-06-19
**Fix commit:** 8727905
**Placement:** docs/bugs/recovery-self-certifies-verification-rows-without-evidence
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md` (recovery dispatch); `user/skills/_components/lazy-batch-prompts/loop-block.md` (LOOP-DETECTED block); `user/skills/lazy-batch/SKILL.md` Step 1c.5 verify-ledger recovery; `user/skills/_components/completion-integrity-gate.md`; feature `docs/features/lazy-cycle-containment/` §C5 (the sanctioned fix for the recovery over-tick).

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[OBSERVED in logs]** Recovery ticked binary-dependent runtime-verification boxes with no on-disk VALIDATED evidence — session `14de0c30` @ `2026-06-15T23:46:53.575Z`: "The recovery overstepped scope — it ticked 4 binary-dependent runtime-verification boxes without on-disk VALIDATED evidence".
2. **[OBSERVED in logs]** Retro confirmed the same recovery overstep as a HIGH finding — session `14de0c30` retro @ `2026-06-16T01:24:47.188Z`: "secondary HIGH finding: the cycle-3 recovery subagent also overstepped… `b0adf405`… fix is to make recovery refuse to tick verification rows without an on-disk evidence grep."
3. **[OBSERVED in logs]** LOOP-DETECTED block licenses a subagent to author VALIDATED.md / SKIP_MCP_TEST.md directly — session `c8882908` audit @ `2026-06-10 15:21`: "LOOP-DETECTED block licenses a Sonnet subagent to author VALIDATED.md and SKIP_MCP_TEST.md directly … A stuck loop is exactly when state is confusing; this is a one-shot bypass."
4. **[OBSERVED in logs]** Step 1e.4a ledger recovery instructs ticking remaining verification boxes for ledger consistency — session `c8882908` audit @ `2026-06-10 15:21`: "Step 1e.4a ledger 'recovery' instructs an agent to 'tick the remaining PHASES.md verification boxes' to make the ledger consistent — self-certification of verification that never ran."

## Reproduction Steps

The reported behavior is no longer reproducible against the current tree — the two code paths that licensed it have since been gated. Static reproduction of the *original* defect (now closed):

1. (Symptom 1/2/4, recovery path) A post-`/execute-plan` `--verify-ledger` failure routes a `recovery` dispatch (`--emit-dispatch recovery`). The dispatched subagent's prompt is `dispatch-recovery.md`.
2. (Symptom 3, loop path) A repeated state tuple (`repeat_count >= 2`) appends `loop-block.md` to the cycle prompt; the loop-breaker subagent runs.

**Expected (and now actual):** A recovery / loop-breaker subagent MAY NOT tick a Runtime-Verification box, nor author `VALIDATED.md` / `SKIP_MCP_TEST.md` / `COMPLETED.md` / `FIXED.md`, without on-disk evidence (a cited `grep` hit). Absent evidence, the box stays unticked and the absence is reported.
**Actual (at time of incidents, before the fixes landed):** The recovery prose said "tick ONLY with on-disk evidence" but did not *enforce* it (no grep-and-cite), and the loop block did not enumerate the banned receipts — so a subagent could self-certify.
**Consistency:** Was reproducible on confusing-state cycles (cycle-3 recovery; stuck loop). Closed after `dfbcfa0` (loop) and `3f6253f` (recovery).

## Evidence Collected

### Source Code (current tree — guards present)

- `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md` lines 26–27 carry the **GREP-AND-CITE GATE (Runtime-Verification rows — HARD, SPEC §C5)**: before ticking ANY verification box the recovery subagent MUST `grep` for a covering `VALIDATED.md` / `MCP_TEST_RESULTS.md`, tick ONLY on a cited hit, and on a miss leave the box unticked and REPORT the absence. The in-line comment states this "closes the cycle-3 over-tick observed in the AlgoBooth run" (symptoms 1/2/4).
- `user/skills/_components/lazy-batch-prompts/loop-block.md` lines 28–36 restrict the loop-breaker to authoring ONLY `NEEDS_INPUT.md` and `BLOCKED.md`, and explicitly ban direct writes of `VALIDATED.md`, `SKIP_MCP_TEST.md`, `COMPLETED.md`, `FIXED.md`, "or any other completion or validation receipt — those sentinels must be earned through their proper gate" (symptom 3).
- `user/skills/lazy-batch/SKILL.md` line 789 (the `--verify-ledger` `deliverables_done` recovery prose) already requires on-disk evidence ("ONLY when there is on-disk evidence that verification actually ran… e.g. `VALIDATED.md` or `MCP_TEST_RESULTS.md`"); `--verify-ledger`'s `deliverables_done` also exempts verification-only rows so it does not false-fail and tempt a blind tick.
- `user/skills/_components/completion-integrity-gate.md` lines 100–108: the coherence-recovery route instructs ticking "WITH on-disk evidence, or re-scope rows it cannot prove — never blind-tick to satisfy the gate." The receipt write + status flip are the script's (`apply_pseudo`) responsibility, not the subagent's.

### Git History (the two landed fixes)

- `3f6253f feat(lazy-cycle-containment): recovery grep-and-cite gate (P7, C5)` — **2026-06-15 21:11** — added the grep-and-cite gate to `dispatch-recovery.md`. Closes symptoms 1/2/4.
- `dfbcfa0 feat(lazy-hardening): Phase 6 Batch 1 — lazy-batch componentization (WU-2) …` — **2026-06-10 17:12** — added the receipt-authoring ban to `loop-block.md`. Closes symptom 3.
- Timeline note: the recovery over-tick was *observed in a run* whose cycle-3 executed before `3f6253f` landed; the retro at `2026-06-16T01:24` named the fix as the remediation target, which `3f6253f` (same evening, 21:11) had already delivered. The loop-block incident (`2026-06-10 15:21`) is ~2 h before its fix `dfbcfa0` (17:12).

### Related Documentation

- `docs/features/lazy-cycle-containment/SPEC.md` §C5 ("Recovery-dispatch scope hardening") and `PHASES.md` Phase 7 — the sanctioned design for the recovery grep-and-cite gate. Phase 7 deliverable + verification boxes are all `- [x]`, with passing tests `test_dispatch_recovery_component_carries_grep_and_cite_gate` and `test_recovery_emit_carries_grep_and_cite_gate_every_variant` (assert the ASSEMBLED recovery prompt carries the gate across all feature/bug × workstation/cloud variants).

## Theories

### Theory 1: Recovery/loop side-doors are open in the current harness
- **Hypothesis:** The contract still permits a recovery/loop subagent to self-certify verification without evidence.
- **Supporting evidence:** The SPEC stub's symptoms (all sourced from logs).
- **Contradicting evidence:** Current `dispatch-recovery.md`, `loop-block.md`, SKILL.md line 789, and `completion-integrity-gate.md` all enforce the evidence requirement; the governing feature `lazy-cycle-containment` §C5 is Complete with passing tests.
- **Status:** **Ruled Out.**

### Theory 2: The symptoms are a regression that already landed fixes (incidents predate the guards)
- **Hypothesis:** The observed oversteps occurred before the two hardening commits and are not reproducible now.
- **Supporting evidence:** `dfbcfa0` (loop ban, 2026-06-10 17:12) and `3f6253f` (recovery grep-and-cite, 2026-06-15 21:11) both post-date or coincide with the incident timestamps; the fix prose explicitly names "the cycle-3 over-tick observed in the AlgoBooth run."
- **Contradicting evidence:** None.
- **Status:** **Confirmed.**

## Proven Findings

1. **Root cause (historic):** Both recovery surfaces stated "tick only with on-disk evidence" as *advisory prose* without a *self-enforcing* mechanism (no mandated grep-and-cite on the recovery path; no enumerated receipt ban on the loop path). Under confusing recovery/loop state, a subagent could satisfy "ledger consistency" by self-certifying instead of re-running verification.
2. **Already remediated:** `dfbcfa0` (loop-block receipt ban) and `3f6253f` (recovery grep-and-cite gate, governed by `lazy-cycle-containment` §C5) close all four symptoms. The `--verify-ledger` SKILL prose and the completion-integrity-gate coherence-recovery route carry the same evidence requirement.
3. **Residual gap (this bug's fix scope):** Coverage is asymmetric. The recovery gate has two dedicated regression tests, but the **`loop-block.md` receipt-authoring ban has no pinning test** — a future edit could silently drop the `VALIDATED.md`/`SKIP_MCP_TEST.md`/`COMPLETED.md`/`FIXED.md` ban without any test failing. Fix scope is to add a static docs-consistency test asserting the loop-block ban text is on disk (mirroring the existing `test_dispatch_recovery_component_carries_grep_and_cite_gate`), so both evidence-side-doors are regression-pinned symmetrically.

## Fix Scope

- **In scope:** Add a static (docs-consistency / `pytest`) regression test asserting `loop-block.md` carries the receipt-authoring ban (the loop-breaker may author ONLY `NEEDS_INPUT.md` / `BLOCKED.md`; the four completion/validation receipts are named-and-banned). Co-locate with the existing recovery-gate tests in `user/scripts/test_project_skills.py` (which already holds `test_dispatch_recovery_component_carries_grep_and_cite_gate`).
- **Out of scope:** Re-writing the recovery / loop / verify-ledger prose (already correct), and any runtime enforcement hook (the prose-level grep-and-cite + receipt ban, plus the script-as-sole-author of receipts in `apply_pseudo`, are the agreed enforcement layer — see `lazy-cycle-containment` §C5 design).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Recovery dispatch | `user/skills/_components/lazy-batch-prompts/dispatch-recovery.md` | Already gated (grep-and-cite). No change. |
| LOOP-DETECTED block | `user/skills/_components/lazy-batch-prompts/loop-block.md` | Already gated (receipt ban). Needs a pinning test. |
| verify-ledger recovery | `user/skills/lazy-batch/SKILL.md` line 789 | Already gated. No change. |
| Completion-integrity gate | `user/skills/_components/completion-integrity-gate.md` | Already gated (tick-with-evidence / re-scope). No change. |
| Regression test | `user/scripts/test_project_skills.py` | Add loop-block receipt-ban assertion. |

## Open Questions

- None blocking. The single open design choice (test mechanism: static docs-consistency grep vs. driving the assembled loop-block emit) is mechanical-internal and is settled by mirroring the existing recovery-gate test pattern in `test_project_skills.py`.
