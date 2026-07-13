# Operator checkpoint-resume should reset cycle counters — Investigation Spec

> When an operator concludes a `/lazy-batch` run by an **operator-authorized checkpoint**, clears context, and re-invokes `/lazy-batch <N>`, the resumed run currently *restores* the paused `forward_cycles`/`meta_cycles` instead of starting a fresh budget. The operator wants them reset to 0 in this case.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-17
**Placement:** docs/bugs/operator-checkpoint-resume-counter-reset
**Related:** `user/scripts/CLAUDE.md` → "Per-repo keyed state dir"; `lazy_core.py` HARD CONSTRAINT 8 (monotonic counters); the 2026-06-14 "mid-run counter reset" root-cause fix (`restore_checkpoint_counters`)

---

## Verified Symptoms

1. **[VERIFIED]** After concluding a `/lazy-batch` run via checkpoint, clearing context, and re-invoking `/lazy-batch`, the `fwd` and `meta` cycle counters carry over from the checkpoint rather than resetting — confirmed by the operator's report.
2. **[VERIFIED]** The operator wants **both** `forward_cycles` and `meta_cycles` reset to 0 on this resume — confirmed via AskUserQuestion.
3. **[VERIFIED]** The reset should apply **only to deliberate operator re-invocations** (operator-authorized checkpoints), NOT to automatic mid-run reliability checkpoints (e.g. cloud hitting ≥2 guard denials), which must keep carrying counters forward so an auto-resume cannot silently exceed the authorized `max_cycles` — confirmed via AskUserQuestion.

## Reproduction Steps

1. Run `/lazy-batch <N>` interactively (attended; `attended=True` since `--unattended` is not passed).
2. Reach a few forward + meta cycles (e.g. `fwd 8/20 · meta 5`).
3. Conclude via the budget-and-queue-guard checkpoint: `lazy-state.py --run-end --reason checkpoint --next-route "<route>" --operator-authorized`. This writes `lazy-run-checkpoint.json` carrying `{forward_cycles, meta_cycles, max_cycles}`.
4. Clear context. Re-invoke `/lazy-batch <N>` → `lazy-state.py --run-start`.

**Expected (desired):** the resumed run starts at `fwd 0/<N> · meta 0` — a fresh authorized budget.
**Actual:** `--run-start` consumes the checkpoint and `restore_checkpoint_counters()` re-applies `forward_cycles=8`, `meta_cycles=5` to the fresh marker, so the run resumes mid-budget (only `N-8` forward cycles remain).
**Consistency:** Always, for any checkpoint-resume.

## Evidence Collected

### Source Code

The carry-over is **intentional**, introduced as the 2026-06-14 "mid-run counter reset" root-cause fix. Two code seams:

- **Checkpoint write** — `user/scripts/lazy-state.py:6358-6371`. On `--run-end --reason checkpoint`, reads the live marker and writes `lazy-run-checkpoint.json` with `counters = {forward_cycles, meta_cycles, max_cycles}`. **Does NOT currently record whether the checkpoint was `--operator-authorized`.** The flag `args.operator_authorized` is in scope (parsed at `lazy-state.py:6018`; used in the attended stop-gate at `:6305`).
- **Checkpoint write helper** — `user/scripts/lazy_core.py:8368-8394` (`write_run_checkpoint`). Persists `{reason, next_route, counters, ts}`. No `operator_authorized` field in the schema.
- **Resume restore** — `user/scripts/lazy-state.py:6210-6226`. On `--run-start`, `consume_run_checkpoint()` reads + deletes the checkpoint, then `restore_checkpoint_counters(checkpoint)` re-applies the paused counts to the just-zeroed marker.
- **Restore helper** — `user/scripts/lazy_core.py:8427-8495` (`restore_checkpoint_counters`). Overwrites `forward_cycles`/`meta_cycles` from `checkpoint["counters"]` and resets `last_advance_consume_count` to 0. Docstring: *"a checkpoint resume is the SAME logical run continuing after a sanctioned pause, so the resumed marker must CARRY FORWARD the paused counts."*

### The discriminator already exists

The attended workstation checkpoint is written with `--operator-authorized` (only after the budget-and-queue-guard AskUserQuestion confirmed the stop — see `/lazy-batch` SKILL Step 1c / line 82). Automatic cloud reliability checkpoints (`≥2 guard denials` or an operator pause message; unattended) are NOT written with that flag. So `operator_authorized` at checkpoint-write time is exactly the "deliberate operator re-invoke vs. automatic mid-run pause" signal the desired behavior needs — it just isn't threaded into the checkpoint JSON yet.

### Contradiction in the harness (root cause class)

The `/lazy-batch` **SKILL prose already states the desired behavior**, but the **script does the opposite**:

- `user/skills/lazy-batch/SKILL.md` Step 1f (line 827): *"The new `/lazy-batch` invocation gets a fresh `max_cycles` budget. The previous session's cycle count is gone (no persistence layer)... each `/lazy-batch <N>` run is a bounded budget the user authorizes."*
- `user/skills/lazy-batch/SKILL.md` Step 5 (line 1291): *"It does NOT preserve cycle accounting across the halt."*
- vs. `lazy_core.restore_checkpoint_counters` which DOES persist + restore across the checkpoint boundary.

The prose was written before the 2026-06-14 fix and was never reconciled. The fix made the script monotonic across checkpoints to stop the *displayed* count going backward mid-run — but it did so unconditionally, conflating the automatic-reliability-pause case (where monotonic carry-over is correct) with the operator-authorized-stop case (where a fresh budget is intended).

### Git History

The carry-over fix is recent (2026-06-14, per in-code docstrings). The most recent commits on `main` are `harness-hardening-retro-fixes` work — unrelated to the checkpoint counter path.

### Related Documentation

- `docs/bugs/CLAUDE.md` — harness-defect investigation conventions (this doc follows them).
- `user/scripts/CLAUDE.md` → "Per-repo keyed state dir" — `lazy-run-checkpoint.json` lives in the per-repo keyed state dir alongside the marker.

## Theories

### Theory 1: Unconditional restore conflates two distinct resume semantics — CONFIRMED
- **Hypothesis:** `restore_checkpoint_counters` always carries counters forward, regardless of whether the checkpoint was an operator-authorized stop (fresh budget intended) or an automatic reliability pause (monotonic continuation intended).
- **Supporting evidence:** `lazy_core.py:8427-8495` has no branch on checkpoint provenance; `write_run_checkpoint` (`:8368`) never records provenance; the SKILL prose (Step 1f/Step 5) documents the fresh-budget intent that the code violates.
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

- The bug is a **missing conditional**, not a broken counter. The counter machinery (advance/fold/persist) is correct.
- The discriminator (`operator_authorized` at checkpoint-write time) exists and is reliable; it is simply not persisted into the checkpoint JSON or consulted at restore.
- **Fix scope (for `/plan-bug`):**
  1. Thread `args.operator_authorized` into the checkpoint write (`lazy-state.py:6369`) and add an `operator_authorized: bool` field to the `write_run_checkpoint` schema (`lazy_core.py:8386-8391`).
  2. In `restore_checkpoint_counters` (`lazy_core.py:8427`) — or at the `--run-start` consume site (`lazy-state.py:6211-6226`) — **skip the restore when `checkpoint["operator_authorized"]` is truthy**, leaving the marker's by-design `0/0` start. Restore (current behavior) only when the field is falsy/absent (automatic reliability pause; also preserves backward-compatibility with pre-fix checkpoint files).
  3. Reconcile the SKILL prose: the contradiction in `/lazy-batch` Step 1f / Step 5 should be made accurate — fresh budget on operator-authorized re-invoke, monotonic carry-over on automatic reliability resume. Mirror into `/lazy-batch-cloud` per the coupling rule.
  4. Add/extend `lazy-state.py --test` (and `test_lazy_core.py`) fixtures: operator-authorized checkpoint → resume resets to 0/0; non-authorized checkpoint → resume restores. Keep the existing monotonic-carry fixture green for the non-authorized path.
- **Coupling note:** `restore_checkpoint_counters` / `write_run_checkpoint` live in `lazy_core.py`, shared by `bug-state.py`. The same provenance-conditional reset applies to the bug pipeline for free; verify `bug-state.py --test` stays green.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Checkpoint write | `user/scripts/lazy-state.py:6358-6371`, `user/scripts/lazy_core.py:8368-8394` | Add `operator_authorized` to checkpoint payload |
| Checkpoint restore | `user/scripts/lazy_core.py:8427-8495`, `user/scripts/lazy-state.py:6210-6226` | Branch on provenance: skip restore for operator-authorized |
| SKILL prose | `user/skills/lazy-batch/SKILL.md` (Step 1f, Step 5), `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Reconcile contradiction; document the two resume semantics |
| Tests | `user/scripts/lazy-state.py` (--test), `user/scripts/test_lazy_core.py`, `bug-state.py` (--test) | New fixtures for both resume paths |

## Open Questions

- Where to place the provenance branch: inside `restore_checkpoint_counters` (keeps the decision in one helper, shared with the bug pipeline) vs. at the `--run-start` consume site (keeps the helper a pure restore primitive). Recommend inside the helper. — for `/plan-bug` to settle.
- Cloud "operator pause message" checkpoints currently do NOT pass `--operator-authorized` (the cloud `--run-end --reason checkpoint` command omits it). Confirm during planning whether an operator pause in cloud should also reset (likely yes) and, if so, thread the flag through the cloud checkpoint write too.
