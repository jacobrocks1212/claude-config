---
kind: investigation-spec
bug_id: adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix
---

# decision-resume apply-resolution cannot enact an operator-chosen receipt-exempt Won't-fix close (infinite needs-input loop) — Investigation Spec

> Harness-hardening round 31 (observed-friction). When the operator resolves a bug's `NEEDS_INPUT.md` by choosing a "close as working-as-designed → Won't-fix" disposition, the apply-resolution subagent had no path to set `**Status:** Won't-fix`. It neutralized the sentinel only, so the next probe re-routed the bug into the pipeline (spec-bug → root-cause-trace gate), which re-halted on needs-input — an infinite loop for ANY operator-chosen receipt-exempt close.

**Status:** Concluded
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix
**Related:** `docs/bugs/adhoc-incident-hook-deny-19343d` (the triggering bug whose Won't-fix close could not be enacted); hardening-log Round 14 (a DIFFERENT apply-resolution defect — `ambiguous-prose` about hand-composing); `user/skills/_components/decision-resume.md` + `dispatch-apply-resolution.md` (the apply-resolution contract + emitted prompt)

---

## Reconstructed Route (divergence point)

- Item in flight: `adhoc-incident-hook-deny-19343d` (claude-config bug pipeline).
- The operator resolved its `NEEDS_INPUT.md` (written_by `root-cause-trace-gate`, `class: product`) via decision-resume `AskUserQuestion`, choosing **"Close as working-as-designed — no code change"**, whose recorded `## Resolution` **Notes** direct "resolve this queue item toward `Won't-fix`".
- **Divergence point:** decision-resume Step 1g → the apply-resolution subagent (`resolution_kind=needs-input`, bug pipeline). The subagent correctly followed its emitted prompt: propagate the choice into SPEC/PHASES + neutralize the sentinel. But the emitted prompt (`dispatch-apply-resolution.md`) had NO step to set a terminal status, AND its constraint (line 197) read: *"The Fixed or Won't-fix status must NOT be set on any Bug doc unless a valid FIXED.md receipt already exists."* So the subagent neutralized `NEEDS_INPUT.md` **without** setting `**Status:** Won't-fix`, leaving the bug at `Status: Investigating`.
- Next probe: `bug-state.py` sees an open (non-done) bug with a neutralized sentinel → routes back to spec-bug/root-cause-trace gate → **re-halts on needs-input**. Infinite loop for any operator-chosen receipt-exempt close.

## Verified Symptom

- The triggering bug's dir on disk shows the exact failure state: `NEEDS_INPUT_RESOLVED_2026-07-12.md` present (neutralized) with the operator's `## Resolution` recording the Won't-fix close, yet `SPEC.md` still at `**Status:** Investigating` (verified pre-fix). `bug-state.py::_find_open_bug_dirs` only skips `Won't-fix`/`Fixed`+receipt, so `Investigating` is returned as open → re-routes.

## Root Cause

**Class: `missing-contract`.** The apply-resolution needs-input path was designed on the assumption that a resolution always feeds back into planning (edit SPEC/PHASES, resume the pipeline). It had NO contract for a resolution whose chosen path is a **terminal close** of the item. The mechanism is the over-broad constraint at `dispatch-apply-resolution.md:197`, which — via `forbidden_status = "Fixed or Won't-fix"` (`lazy_core.py:6841`) — conflated the receipt-GATED terminal (`Fixed`, needs `FIXED.md`) with the receipt-EXEMPT terminal (`Won't-fix`, retired-without-a-fix, `bug-state.py:29/567/751`). Since `Won't-fix` is definitionally receipt-exempt (no `FIXED.md` ever exists), the constraint made the operator's legitimate close **unsatisfiable**. No `bug-state.py` CLI action enacts Won't-fix (grep confirms none; the only `wont-fix-exempt` code is a test fixture), and the orchestrator cannot set status itself (sentinel-only writes), so the close could only be enacted by the apply-resolution subagent — which was forbidden.

## Fix Scope

1. **`lazy_core._standard_dispatch_bindings`** — split the compound `forbidden_status` into two additive tokens (leaving `forbidden_status` UNCHANGED for the other templates that correctly use the blanket ban): `receipt_gated_status` (`Fixed`/`Complete`) and `receipt_exempt_status` (`Won't-fix`/`Superseded`).
2. **`dispatch-apply-resolution.md`** — add needs-input **step 2b** (TERMINAL DISPOSITION): when the operator's chosen resolution directs closing the item toward `{receipt_exempt_status}`, SET `**Status:** {receipt_exempt_status}` on SPEC.md (mechanical propagation of the operator's own decision; receipt-exempt, never writes the receipt, never sets the gated status). Reword the constraint to govern ONLY the receipt-gated status and explicitly PERMIT the receipt-exempt close via step 2b.
3. **`decision-resume.md`** — mirror the terminal-disposition note into the reference contract so it does not drift (Round-14-style).
4. **First instance:** enact `**Status:** Won't-fix` on `adhoc-incident-hook-deny-19343d/SPEC.md` so this run advances (its `## Resolution` already records the working-as-designed disposition).
5. **Regression tests** in `test_lazy_core.py` (split-token bindings + emitted-prompt terminal-disposition step for both pipelines).

Scope is narrow and receipt-exempt only: it never permits setting `Fixed`/`Complete` without a receipt, so the completion-integrity gate is fully preserved (no gate weakened).

## Consequence / prevention

The apply-resolution needs-input path now has a defined contract for an operator-directed receipt-exempt close, so the "answer → neutralize → re-halt" loop can no longer form. Target signal: recurring needs-input halts on an already-resolved bug (`step_repeat_count` recurrence on the same needs-input step) should go to zero.
