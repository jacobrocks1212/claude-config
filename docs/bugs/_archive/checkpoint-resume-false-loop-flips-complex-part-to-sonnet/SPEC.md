# Checkpoint-resume false LOOP DETECTED + complexity:complex execute-plan part flipped to sonnet — Investigation Spec

> On a checkpoint-resume run whose `next_route` is an `/execute-plan` of a plan part tagged
> `complexity: complex`, the state script returns a FALSE `LOOP DETECTED` and flips
> `cycle_model` to `sonnet`. Two coupled harness gaps compound: (1) the loop-debounce
> baseline is lost across the checkpoint `--run-end` → `--run-start` boundary (the prompt
> registry is deleted and recreated fresh), so the FIRST re-probe of a route that was NEVER
> re-dispatched inflates `repeat_count` to 2 with no failed dispatch between; and (2) the
> loop-flip-to-sonnet ignores the plan part's declared complexity tier — a `complexity: complex`
> part on sonnet is HARD-refused by the cycle prompt (`BLOCKED model-tier-mismatch`), so the
> flip only climbs the stall streak toward a halt.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-12
**Placement:** docs/bugs/checkpoint-resume-false-loop-flips-complex-part-to-sonnet
**Related:** `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (Round 29 origin); `docs/bugs/loop-detected-false-positives-from-probe-and-reboot-churn` (the F1/F2 double-probe debounce this extends); `docs/bugs/cycle-bracket-break-on-checkpoint-resume` (hardening Round 35 — the sibling "checkpoint `--run-start` re-mints run-scoped state" class, fixed for the run identity/counters via `RUN_CONTINUITY_FIELDS`); `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md:260,287` (the `model-tier-mismatch` refusal); `lazy_core.plan_complexity` (the declared-tier source).

---

## Verified Symptom

Observed live this run (`live-settings-split-brain` part-3): `forward_cycles=10` resumed from a
checkpoint; `next_route = /execute-plan part-3` (`complexity: complex`; parts 1 & 2 `Complete`;
clean + pushed tree). The probe returned `repeat_count=2` + `LOOP DETECTED` + `cycle_model=sonnet`.
The orchestrator worked around it by hand-overriding the model to opus (surfaced as a **T6
deviation**), after which the cycle completed cleanly.

The two symptoms are independent and each reproducible in isolation:

- **Gap 1 — false LOOP DETECTED.** `lazy_core.update_repeat_counts` keys its double-probe
  debounce (both the dispatch-tuple `repeat_count` and the step-level `step_repeat_count`) on the
  registry's `consumed_emission_count()`: the count is HELD only when the prior probe's persisted
  `consume_count` equals the current one (proving no dispatch landed between the two probes). The
  persisted `consume_count` lives in the OS-temp signature file (`lazy-state-last-<hash>.json`),
  which SURVIVES `--run-end`. But `--run-end` deletes the prompt registry and the resuming
  `--run-start` recreates it fresh, so `consumed_emission_count()` resets to 0 while the signature
  file still carries the PRE-checkpoint count (e.g. 5). The first re-probe of the SAME `next_route`
  (which a checkpoint resume deterministically re-probes) sees `prior_consume (5) != current (0)`,
  cannot prove the re-read, and falls through to `count = prior_count + 1` → `repeat_count=2` →
  `LOOP DETECTED`. A `probe → checkpoint → probe` is NOT a stall; a genuine stall requires a
  DISPATCH that failed to advance between two probes.

- **Gap 2 — complex part downgraded to sonnet.** `lazy_core.emit_cycle_prompt` sets
  `model = "sonnet"` UNCONDITIONALLY when the loop block is appended (`repeat_count >= 2`),
  regardless of the `/execute-plan` part's declared `complexity:` tier. The cycle prompt
  (`cycle-base-prompt.md:260,287`) HARD-instructs the subagent: *"If the dispatched part's real
  work exceeds its declared `complexity:` tier (e.g. complex work under a Sonnet dispatch), STOP
  with BLOCKED.md `blocker_kind: model-tier-mismatch`."* So a `complexity: complex` part dispatched
  on sonnet cannot advance — repeated sonnet dispatches only climb the streak toward a halt. The
  pre-existing comment (`lazy_core.py:7172`) documented this as intended (`sonnet ∧ sonnet =
  sonnet`); that composition is the defect.

## Root Cause

**Class: script-defect (two coupled sites in `lazy_core.py`).**

1. **Gap 1 — stale registry-relative debounce baseline across a run boundary.** The
   `consume_count` oracle is registry-relative, but the registry is deleted at `--run-end` and
   recreated fresh at the resuming `--run-start`. Nothing re-baselines the signature file's
   `consume_count` against the fresh registry, so the first post-resume probe of an unchanged route
   mis-reads a registry reset as a landed dispatch. This is the same *class* as
   `cycle-bracket-break-on-checkpoint-resume` (checkpoint `--run-start` re-mints run-scoped state
   that must be continuous), but for the loop-debounce oracle rather than the run identity/counters.

2. **Gap 2 — loop-flip ignores the declared complexity floor.** The loop-block downgrade at
   `emit_cycle_prompt` composes with the per-part complexity tiering by always moving toward sonnet;
   there is no floor keeping a complexity-pinned-opus `/execute-plan` cycle at opus. The floor MUST
   match the subagent's refusal condition, which is keyed on the plan part's declared tier via
   `plan_complexity` (untagged/unknown defaults to the SAFE `complex` → opus).

## Fix Scope

Two surgical, structural changes in the single shared `lazy_core.py` (both inherited by
`bug-state.py`), plus the two state-script call sites for Gap 1:

- **Gap 1 — `lazy_core.rebaseline_loop_signature_after_registry_reset(repo_root, *, pipeline)`.**
  A new helper that rewrites ONLY the signature file's `consume_count` to the current
  (freshly-cleared) `consumed_emission_count()`, preserving the persisted `signature` / `count` /
  `step_count` — so a GENUINE pre-pause loop streak survives (the loop block still fires) while a
  never-re-attempted route HOLDS on its first re-probe. No-op when no signature file exists, when it
  is unreadable/corrupt, or when no run marker is present; never raises. Called in the
  checkpoint-resume block (`if checkpoint is not None:`) of BOTH `lazy-state.py` and `bug-state.py`
  run-start handlers (coupled-pair mirror; the helper is shared, the call site is per-script).

- **Gap 2 — complexity floor on the loop-flip in `emit_cycle_prompt`.** For an `/execute-plan`
  cycle, resolve the part's `plan_complexity` once: `mechanical` → `model = "sonnet"` (unchanged);
  anything else (`complex` or the untagged/unknown default) → mark the cycle `complexity_pinned_opus`.
  The loop-block downgrade then sets `model = "sonnet"` ONLY when NOT `complexity_pinned_opus`.
  Every non-execute-plan and mechanical cycle downgrades to sonnet on loop exactly as before; only a
  complexity-pinned-opus `/execute-plan` cycle keeps opus. The floor boundary matches the subagent's
  `model-tier-mismatch` refusal condition (declared-tier-driven; conservative default `complex`).

- **Tests + doc lockstep.** New `test_lazy_core.py` fixtures for both gaps; update the two existing
  tests that pinned the OLD (buggy) behavior (`test_emit_cycle_prompt_loop_append_and_model_flip`
  used a defaulting-to-complex `/execute-plan` cycle to assert the sonnet flip →
  retarget to a non-pinned skill; `test_emit_cycle_prompt_complex_part_loop_cycle_model_sonnet` →
  rename + assert opus). Update the stale comment block at `lazy_core.py:7168–7174` and the test
  header comment at `test_lazy_core.py:8377`. Full gate suite; the byte-pinned smoke baselines are
  unaffected (no `--run-start` checkpoint-resume fixture carries a pre-existing signature file, and
  the loop-flip change does not alter any smoke-path emission).

## Out of Scope

- **Fresh (non-checkpoint) `--run-start` with a stale signature file.** The same stale-baseline
  class can inflate the first probe of a genuinely-new run when its route coincidentally matches a
  prior run's last-probed route. It is a NEAR NEIGHBOR of Gap 1 but is not the observed instance (a
  checkpoint resume deterministically re-probes the SAME route; a fresh run rarely does), and the
  fix is scoped to the checkpoint-resume boundary to keep the change tight. If observed in the
  field, widen the same helper's call to the non-checkpoint run-start path.
