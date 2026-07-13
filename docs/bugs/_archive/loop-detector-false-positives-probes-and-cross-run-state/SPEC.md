# Loop-detector counters advance on probes/denials and leak across runs — Investigation Spec

> The `repeat_count` / `step_repeat_count` loop tripwires false-fired on benign churn (probes,
> denied dispatches, resolved blockers) and their state — plus the deny ledger — survives
> `--run-end`, so a fresh run can open with a false-loop T6 warning and a mandatory hardening
> dispatch for a PRIOR-RUN denial. The probe/deny/resolution classes are FIXED in current
> code (F1/F2 consume-debounce, peek probes, `de39d3a` ordered-advance, `14d90bd`
> resolution-reset). The REMAINING defects: (a) meta-class dispatch consumption still
> advances the step streak, and (b) neither the streak files nor the deny ledger is scoped
> to the run-marker lifetime.

**Status:** Fixed
**Priority:** P2
**Last updated:** 2026-07-12
**Related:** `docs/bugs/_archive/loop-detected-false-positives-from-probe-and-reboot-churn/` (Fixed 2026-06-19, commit `14d90bd` — closed the probe/reboot/resolution classes; this spec generalizes its residual); `docs/specs/lazy-pipeline-ergonomics/` Phase 2 (F2 step-debounce, `973339b`) + `docs/specs/lazy-validation-readiness/` Phase 1 (F1 dispatch-tuple debounce, `774ef23`); commit `de39d3a` (2026-06-14, ordered multi-part advancement exemption); `docs/bugs/operator-checkpoint-resume-counter-reset/` (Fixed 2026-06-17) and `docs/bugs/adhoc-align-cycle-commit-count-with-budget-population/` (queued) + `docs/bugs/_archive/byref-dispatch-undercounts-forward-cycles/` — the `forward_cycles`/`meta_cycles` ACCOUNTING symptom is owned there and scoped OUT here; `docs/specs/turn-routing-enforcement/` (deny ledger, `--run-end` gates).

## Verified Symptom

Live AlgoBooth `/lazy-batch` run, session `e076ed30-8dcf-429a` (ended 2026-06-15):

1. **Debt-drain probes advanced a tuple's streak → false LOOP DETECTED** (turn ~2168).
2. **`step_repeat_count` hit 8 while the cause was already fixed** (turns ~97, ~134): a denied dispatch made no commit, so the HEAD-aware streak never reset; repeated re-probes kept incrementing.
3. **A needs-input resolution did not reset the streak** — the post-resolution write-plan probe was flagged as a loop (turn ~355).
4. **Streaks AND deny-ledger entries survived `--run-end`** — the NEXT run opened with a false-loop T6 warning (turn ~4750) and a mandatory hardening dispatch to clear a stale PRIOR-RUN denial (turn ~4743).
5. **Checkpoint recorded `forward_cycles: 11, meta_cycles: 0` after ~2 real dispatches + 2 recoveries** (turn ~4657) — SCOPED OUT: cycle-count ACCOUNTING is owned by `operator-checkpoint-resume-counter-reset` (Fixed 2026-06-17 — counters now marker-persisted), `_archive/byref-dispatch-undercounts-forward-cycles` (fixed), and the queued `adhoc-align-cycle-commit-count-with-budget-population` brief.

## Root Cause

**Classification: `fixed-in-part` / `missing-lifecycle-scoping` (the residual).** The counter authority is `lazy_core.update_repeat_counts` (`user/scripts/lazy_core.py` ~5687–6061). Current-code characterization (verified 2026-07-11):

### Already fixed (do NOT re-plan these)

- **Symptom 1 (probes advance streaks):** the F1 (dispatch-tuple, ~5903–5920) and F2 (step, ~6021–6038) **consume-count debounces** HOLD both counters when the signature is unchanged AND the registry consumed-emission count did not move between two marked probes ("no dispatch landed ⇒ re-read, not re-attempt"). Additionally `--repeat-count-peek` (`peek=True`, ~6045) computes without persisting, and SKILL.md Step 1a mandates exactly ONE advancing probe per cycle. Landed `973339b` + `774ef23` (2026-06-13, after the observations).
- **Symptom 2 (denied dispatch never HEAD-resets):** a guard DENY consumes no nonce, so the consume-count is unchanged and the debounce now holds across a deny→re-probe sequence. Also `de39d3a` (2026-06-14) reset-to-1 when `sub_skill_args` ADVANCED at an unchanged step (ordered multi-part /execute-plan), closing the multi-part false-trip.
- **Symptom 3 (resolution doesn't reset):** the **resolution-aware reset** (`14d90bd`, 2026-06-19 — `_resolution_reset`, ~5958–6020): the apply-resolution bracket persists a one-shot `last_resolution_step_key` on the run marker (`record_resolution_signal`, CLI `--record-resolution-signal` in both state scripts), and the next same-step probe resets `step_count` to 1, consume-and-clear.

### Residual gap A — meta-class consumption still advances the step streak

The debounce's oracle is `consumed_emission_count()` — it counts **any** guard-ALLOW consumption, including META classes (`hardening`, `recovery`, `coherence-recovery`, `investigation`, `input-audit`, …). A mid-step hardening/recovery dispatch raises the consume-count, the F2 precondition fails, and the next same-step probe **increments** `step_repeat_count` even though the intervening dispatch was not a forward attempt at the step. `14d90bd` special-cased exactly ONE meta class (resolutions, via the marker signal); every other meta class still defeats the hold. This is the mechanism behind the symptom-2 flavor "streak kept climbing while denials were being hardened out" — probe→deny→hardening-dispatch(consumes)→probe increments.

### Residual gap B — no run-lifetime scoping of streaks or deny ledger

- **Streak files** live at `<tempdir>/lazy-state-last-<repo-hash>.json` (and `bug-state-last-…`). NOTHING clears them: `--run-end` → `delete_run_marker(clear_registry=True)` (`lazy_core.py` ~10922) deletes the marker + prompt registry only; `--run-start` writes the marker and touches no streak state. A next run whose first probe lands on the same `(feature_id, current_step)` INHERITS the dead run's streak → the false-loop T6 warning at run open (symptom 4). The record carries no run identity to gate on.
- **Deny ledger** (`lazy-deny-ledger.jsonl`): entries carry `ts` but NO run identity (`append_deny_ledger_entry`, ~14230); `pending_hardening()` (~15564) counts ALL unacked entries machine-wide. A run that ends cleanly is forced to drain (the `--run-end` gate refuses on unacked debt), but a **crashed/killed run leaks unacked entries into the next run**, which must dispatch a full hardening round (or `--ack-unhardened`) for a denial it never saw (symptom 4). By contrast the prompt REGISTRY is correctly run-scoped twice over (cleared at run-end + `emitted_at >= marker.started_at` gate in `lookup_emission`) — the streaks and the ledger simply never received the same treatment.

## Fix Scope (Concluded)

1. **Streaks keyed to forward-attempt outcomes only** — refine the debounce oracle so only CYCLE-class consumptions count as "a dispatch landed between probes" (the registry entry already carries `class`; count consumed `cycle` entries instead of all entries), OR generalize the one-shot reset signal to every `--emit-dispatch` meta class. Either way: probe invocations and guard denials continue to never mutate counters (already true), and meta dispatches stop advancing the step streak. The d8 design constraint is untouched: a genuine same-step oscillation dispatches a CYCLE each repeat, so it still trips (HEAD-blindness preserved, no commit-reset added).
2. **Run-lifetime scoping of streak state** — stamp the streak record with the run marker's `started_at` (the established run identity) and treat a record from a different/absent run as no-prior; AND/OR delete the signature file in `delete_run_marker` alongside the registry. `--run-end` and `--run-start` both converge to "a new run starts with fresh streaks".
3. **Run-scoping of deny-ledger DEBT** — stamp new entries with `run_started_at`; `pending_hardening()` / `pending_denial_reasons()` / the probe-withholding and `--run-end` gates count only the LIVE run's unacked entries. Prior-run leftovers (crashed run) remain in the file for retro/incident mining but surface as a T6 informational line, not mandatory debt. (Alternative — clearing at `--run-end` — is weaker: it cannot help the crashed-run case, which is the one that actually leaks.)
4. **Coupled-pair mirroring** (`bug-state.py` shares `update_repeat_counts` and the ledger via `lazy_core` — verify no bug-pipeline-only call sites regress) + `test_lazy_core.py` fixtures: (a) meta-consumption hold, (b) cross-run fresh streak, (c) prior-run ledger debt demoted, (d) negative fixture proving the d8 commit-masked cycle-class oscillation still trips.

## Decisions

- **D1 — Oracle refinement vs signal generalization (fix-planning):** counting only cycle-class consumptions is one localized change to the oracle read; generalizing the marker signal requires every meta emit path to record it. Prefer the oracle refinement unless planning finds a meta class that legitimately IS a forward attempt. Mechanical-internal; resolve at `/plan-bug`.
- **D2 — Prior-run debt disposition (NEEDS OPERATOR if changed from §3):** demote-to-informational (recommended — preserves the incident-mining record) vs hard-clear at `--run-start`. Demotion keeps the `--ack-unhardened` audit trail meaningful.
- **D3 — Scope boundary (RESOLVED):** `forward_cycles`/`meta_cycles` checkpoint accounting is owned by the three cross-linked counter bugs; this spec touches only the repeat/streak counters and ledger lifecycle.
