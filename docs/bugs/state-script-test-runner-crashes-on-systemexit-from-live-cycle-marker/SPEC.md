---
kind: investigation-spec
bug_id: state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker
---

# The state-scripts' in-file `--test` runner crashes partway when run from inside a live cycle marker (SystemExit(3) escapes `except Exception`) — Investigation Spec

> Spun off from the harden-harness round that fixed `lazy-cycle-containment-false-denies-reference-only-routing-mentions` (2026-07-12). SECONDARY-1: a cycle subagent cannot run the documented quality gate `python lazy-state.py --test` / `bug-state.py --test` mid-run — the suite aborts partway.

**Status:** Investigating
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/state-script-test-runner-crashes-on-systemexit-from-live-cycle-marker
**Related:** `docs/bugs/lazy-cycle-containment-false-denies-reference-only-routing-mentions` (the round that observed this); `lazy_core.refuse_if_cycle_active` (raises SystemExit(3)); the in-file `--test` harness in `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` (coupled pair)

---

## Observed Symptom (verified this round)

Running `python user/scripts/lazy-state.py --test` from a session with a LIVE cycle marker in the production keyed state dir aborts at:

```
FAILURES:
  - [apply-pseudo-provisional-refusal] SystemExit: 3
```

The `[apply-pseudo-provisional-refusal]` fixture reaches a code path that calls `refuse_if_cycle_active`, which raises `SystemExit(3)` (the C3 cycle-containment refusal, exit-code 3). `SystemExit` is a `BaseException`, not an `Exception`, so the `--test` runner's per-fixture `except Exception` does NOT catch it — it escapes and crashes the suite partway. Confirmed environmental, not a code regression: the SAME `--test` passes fully under a hermetic `LAZY_STATE_DIR` (empty temp dir, no cycle marker).

## Impact

A cycle subagent (agent_id present, or a live cycle marker) cannot run the two documented state-script quality gates mid-run without the hermetic `LAZY_STATE_DIR=<empty>` workaround. This silently undermines gate-runnability for every future cycle/hardening subagent.

## Candidate Fixes (to be decided by /spec-bug)

1. **Catch `BaseException`/`SystemExit` per-fixture** in the `--test` runner so a `SystemExit(3)` from a fixture is reported as a normal handled result (or asserted), not a suite crash. Lowest-scope; makes the runner robust to any guarded op a fixture legitimately exercises.
2. **Hermetically isolate the offending fixture(s)** — ensure `[apply-pseudo-provisional-refusal]` (and any sibling that calls a `refuse_if_cycle_active`-guarded op) always sets its own `LAZY_STATE_DIR` so it never reads the ambient production cycle marker.

Prefer (1) as a defense-in-depth backstop and (2) for correctness, possibly both. Coupled pair — apply to BOTH `lazy-state.py` and `bug-state.py` test harnesses.

## Notes

Not fixed inline in the originating round (scope discipline + coupled-pair change to both state-script test harnesses); the originating round certified its PRIMARY fix via the hermetic `LAZY_STATE_DIR` run, which is the legitimate/standard way these hermetic suites run.
