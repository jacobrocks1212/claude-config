---
kind: investigation-spec
bug_id: clear-state-dir-teardown-strips-lazy-state-dir-override
---

# `test_lazy_core.py` `_clear_state_dir()` teardown strips the process-level `LAZY_STATE_DIR` override, false-failing the full suite during a live lazy cycle — Investigation Spec

> The documented mitigation for running the full `test_lazy_core.py` suite DURING a live lazy cycle is to set a process-level `LAZY_STATE_DIR=<temp>` so cycle-active guards (`refuse_if_cycle_active` reached via `apply_pseudo`) read a clean temp state dir instead of `~/.claude/state/<repo>/`. That mitigation is defeated because the per-test teardown `_clear_state_dir()` calls `os.environ.pop("LAZY_STATE_DIR", None)` UNCONDITIONALLY. An early cycle-marker test sets its own temp dir via `_set_state_dir()` and then, in teardown, pops the override — stripping the operator's process-level value too. Every subsequent test (and the guard it exercises) then reads the REAL state dir, sees the live cycle marker, and `test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes` false-fails.

**Status:** Concluded
**Severity:** Low
**Discovered:** 2026-07-12
**Placement:** docs/bugs/clear-state-dir-teardown-strips-lazy-state-dir-override
**Related:** `multi-repo-concurrent-runs` (`LAZY_STATE_DIR` resolution chokepoint `lazy_core.claude_state_dir`); hardening dispatch trigger `process-friction` on item `hardening-intervention-records-unmeasurable-or-missing` (batched GAP B)

---

## Verified Symptoms

1. **[VERIFIED — code-traced]** `user/scripts/test_lazy_core.py:13363-13365` — `_clear_state_dir()` is `os.environ.pop("LAZY_STATE_DIR", None)`, unconditional. `_set_state_dir()` (13358-13360) sets it to a per-test temp dir; the ~250 teardown call sites then pop it. There is no capture/restore of the value present at process launch.
2. **[REPORTED — run telemetry]** A subagent running the full suite during a live cycle observed `test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes` false-failing because `refuse_if_cycle_active` tripped on the live `lazy-cycle-active.json` marker after an early test's teardown removed the temp override.

## Reproduction Steps

1. Arm a live lazy cycle (a `lazy-cycle-active.json` marker present in the real keyed state dir).
2. Run `LAZY_STATE_DIR=/tmp/clean python3 user/scripts/test_lazy_core.py` (the documented mitigation).
3. Observe an early test that calls `_set_state_dir(<temp>)` then `_clear_state_dir()` in teardown.

**Observed (pre-fix):** after that teardown `LAZY_STATE_DIR` is absent; later `refuse_if_cycle_active`-reaching tests read the real state dir and false-fail on the live marker.
**Expected (post-fix):** `_clear_state_dir()` restores the process-launch `LAZY_STATE_DIR`, so the operator's override survives every teardown and the suite stays hermetic against the real state dir.

## Root Cause

**Class: script-defect** (test-harness teardown). `_clear_state_dir()` treats "no override" as the only baseline and deletes, rather than restoring whatever `LAZY_STATE_DIR` was present when the module was imported.

## Fix Scope

- Capture the process-launch value once at module import: `_ORIGINAL_LAZY_STATE_DIR = os.environ.get("LAZY_STATE_DIR")`.
- `_clear_state_dir()` restores that value when non-None, else pops (byte-identical to today when no override is set — every existing hermetic test unaffected).
- Add one registered regression test asserting the restore-not-strip behavior (hermetic: save/restore the module global + env around itself).
