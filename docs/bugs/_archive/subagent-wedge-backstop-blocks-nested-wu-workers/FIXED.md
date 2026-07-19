---
kind: fixed
feature_id: subagent-wedge-backstop-blocks-nested-wu-workers
date: 2026-07-19
provenance: backfilled-unverified
validated_via: test_hooks.py 284/284 (pytest + in-file runner); lazy-state.py --test + bug-state.py --test smoke harnesses; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`subagent-wedge-backstop-blocks-nested-wu-workers` marked Fixed on 2026-07-19 during hardening
Round 109 (observed-friction harden dispatch, item in flight `hydra-overlay`). This receipt was
written by the dispatched harden agent OUT-OF-PIPELINE (a `harden(...)` commit, not the bug
pipeline's `__mark_fixed__` gate) — provenance is deliberately `backfilled-unverified`.

## Notes

Fixed via the recommended **Option A** (self-managed integrator-`agent_id` breadcrumb), implemented
in commit `5312b9dba365251cd42a9a5328dd3eef1bfeb733`:

- `lazy-cycle-containment.sh` (PreToolUse, already receives `agent_id`) records the FIRST `agent_id`
  observed under each cycle-marker generation as the cycle integrator, keyed by the marker nonce,
  into a sibling breadcrumb `<state>/cycle-integrator/<nonce>.json` (first-writer-wins;
  best-effort/fail-open; never affects allow/deny).
- `subagent-wedge-backstop.sh` (SubagentStop) BLOCKS only when the stopping `agent_id` IS the
  recorded integrator; a nested WU worker (a distinct `agent_id`) is EXEMPTED. An unattributable
  stop (breadcrumb absent) biases to ALLOW (false-negative), preserving the hook's allow-on-doubt
  posture. The cycle-integrator dir is swept on the same staleness threshold as `subagent-stops/`.

The platform assumption that blocked Round 108 (does `SubagentStop` expose a lineage field?) was
resolved this run by a `claude-code-guide` consultation, which confirmed there is NO
`parent_agent_id`/`depth` lineage field — eliminating Option B and confirming Option A is
non-platform-dependent (it uses only the documented `agent_id` + the serial-tool-call ordering the
guard's consumed-fence already relies on).

**Design decision PROVISIONALLY accepted (ratification-pending).** The `divergence: structural`
decision was provisionally accepted under explicit operator authorization — see
`docs/specs/turn-routing-enforcement/NEEDS_INPUT_PROVISIONAL_2026-07-19-wedge-backstop-integrator-vs-worker-identity.md`
(`resolved_by: auto-provisional`, `decision_commit: 5312b9db`). Operator ratify/redirect via the
provisional-ratification affordance.

## Verification

- `python user/scripts/test_hooks.py` → 284/284 passed (includes the new Option-A regression tests:
  `test_wedge_integrator_blocks_distinct_worker_exempt`, `test_wedge_no_integrator_breadcrumb_allows`,
  `test_containment_records_cycle_integrator_first_writer_wins`; all block-expecting wedge tests
  updated to record the integrator).
- `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` — all
  smoke tests passed.
