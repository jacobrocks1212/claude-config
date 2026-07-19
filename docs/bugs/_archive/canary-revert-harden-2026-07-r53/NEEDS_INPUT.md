---
kind: needs-input
feature_id: canary-revert-harden-2026-07-r53
written_by: spec-bug
next_skill: spec-bug
class: product
divergence: structural
stub_origin: true
decisions:
  - Triage disposition for the harden-2026-07-r53 canary trip (close-as-noise / revert / redesign)
date: 2026-07-19
---

## Decision Context

### 1. Triage disposition for the harden-2026-07-r53 canary trip (close-as-noise / revert / redesign)

**Problem:** The `harden-2026-07-r53` canary tripped (2026-07-18) because the friction signal `event:containment-refusal` rose +333.8% vs its frozen baseline (72.9 → 316.25 events/run; band ±25%) in the change's post-ship window. A "canary" here is an automatic watcher that flags a shipped harness change when a friction signal it's tied to moves the wrong way; it only flags and files this bug — **nothing was reverted automatically**. The shipped change under review (commit `8a7bc738`, feature `no-sanctioned-cli-for-queue-state-mutations`) added operator-only CLI commands for editing the pipeline's work queue (set a bug's severity, set a feature's tier, add/remove dependencies, un-pin) so operators no longer have to hand-edit `queue.json`. That change spans a **parity-guarded coupled pair** — `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — so any revert must cover all three halves and end with a green `python3 user/scripts/lazy_parity_audit.py --repo-root .`.

Investigation traced the signal to its source and found the trip is a **false-positive**: `event:containment-refusal` is emitted ONLY by three guard functions in `user/scripts/lazy_core/markers.py` (`refuse_if_cycle_active`, `refuse_cycle_marker_mutation_if_subagent`, `refuse_run_start_clobber`), which fire per guard-hit during routine pipeline activity. Commit `8a7bc738` **does not touch `markers.py`** — its new CLI ops are operator-authorized and never run during a normal cycle, so the change cannot produce this signal at all. The trip was "band-only" with **zero** incidents attributed to the change's own files, and its window (2026-07-16→18) overlapped a burst of other hardening rounds targeting the same signal (r48, r72, r75, r89) — the classic confounder that inflates a pipeline-activity-volume aggregate. Separately, the intervention record itself was mis-declared (it expected this signal to *decrease*, which the change is architecturally incapable of doing — hand-editing `queue.json` never emitted `containment-refusal` in the first place). The disposition is nonetheless a product-class call because revert/redesign change user-visible behavior (removing a shipped operator CLI surface). **This decision carries `stub_origin: true` (a baseline the operator has not seen) — it always parks and is never provisionally auto-accepted.**

**Options:**
- **Close-as-noise (Recommended)** — Accept the trip as a confounded, band-only false-positive and keep the shipped feature exactly as-is. Rationale: the change is provably not on the regressed signal's serving path; there is nothing to revert or redesign. Close-as-noise is a first-class, tracked outcome (the `canary-trip-precision` KPI measures exactly this). Cost: near-zero; the sanctioned-CLI feature stays available. Optional non-blocking follow-ups (a separate canary-tuning item, NOT this bug's fix): re-base/re-declare the r53 intervention record via `efficacy-eval.py --rebaseline` so its target signal/direction match the change's real scope, and consider tuning the ±25% band for volume-aggregate `event:*` signals so band-only, zero-attribution trips don't fire. Reversibility: fully reversible — reopening later costs nothing.
- **Revert** — `git revert 8a7bc738` across the whole coupled pair and end with a green `lazy_parity_audit.py`. Removes the operator queue-mutation CLI (`--set-tier`/`--set-severity`/`--add-deps`/`--remove-deps`/`--unpin`) and restores the pre-change state. Choose this only if you want the feature gone for an independent reason (e.g. you distrust an unmeasurable feature); the canary evidence does NOT support it — the change did not cause the signal movement. Cost: structural (multi-file revert, coupled-pair scope, parity re-audit), and it re-opens the original `no-sanctioned-cli-for-queue-state-mutations` friction (operators back to hand-editing `queue.json`, which the harness forbids).
- **Redesign** — Keep the feature but re-work it. There is no traced defect in the shipped feature to redesign; the only mis-design found is in the *intervention/canary declaration* (target signal + direction), which is corrected via the record's own tooling (`efficacy-eval.py --rebaseline`), not by changing the feature's code. Choose only if a specific feature-level concern exists beyond the canary trip. Cost: bounded-to-contained, but aimed at a surface the evidence does not implicate.

**Recommendation:** Close-as-noise — the shipped change is provably not on the regressed signal's serving path (its sole emitter `markers.py` is untouched; the ops never fire in a normal cycle), the trip was band-only with zero surface-attributed incidents inside a same-signal-confounded window, and reverting a useful, correct feature over a confounded aggregate false-positive would re-open real friction for no benefit; pursue the canary/record mis-declaration as a separate tuning follow-up.
