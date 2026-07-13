---
kind: implementation-plan
feature_id: adhoc-run-end-tests-leak-real-repo-state
status: Complete
---

# PHASES — `--run-end`/`--marker-present` hermetic subprocess tests leak real repo state

Single-phase fix (test-only; see SPEC.md Affected Area — production code is unchanged).

## Phase 1: Isolate `--repo-root` + extend the efficacy-breadcrumb fixture, pin the 2 masked gates

**Status:** Complete

### Deliverables

- [x] Add a hermetic `repo_dir` (temp, non-git, mkdir'd) to all 8 named tests and pass
      `--repo-root <repo_dir>` on every `lazy-state.py` subprocess invocation in each test — never
      the argparse default `os.getcwd()` (the real checkout). Files:
      `user/scripts/test_lazy_core.py`, the 8 test bodies:
      `test_p7_run_end_checkpoint_attended_no_auth_refuses`,
      `test_p7_run_end_checkpoint_attended_with_auth_succeeds`,
      `test_p7_run_end_checkpoint_unattended_no_auth_allowed`,
      `test_p7_run_end_terminal_sanctioned_reason_allowed`,
      `test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth`,
      `test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed`,
      `test_p7_run_end_terminal_no_terminal_reason_adds_deprecation`,
      `test_marker_present_cli_absent_then_present_and_readonly`.
- [x] Extend `_seed_efficacy_breadcrumb(state_dir)` to seed its OWN disposable
      interventions-bearing fixture directory (a sibling of `state_dir`, carrying a throwaway
      `docs/interventions/adhoc-test-fixture.md`) and pass it EXPLICITLY as
      `covered_repo_root=` to `lazy_core.drop_efficacy_breadcrumb(...)` — so the breadcrumb's
      `interventions_covered` flag no longer depends on the live marker's `repo_root` field (and
      therefore never reads the real repo's `docs/interventions/`). Signature unchanged — all 10
      pre-existing call sites (this family's + others') are unaffected. File:
      `user/scripts/test_lazy_core.py::_seed_efficacy_breadcrumb`.
- [x] Fix the 2 fixture-masked tests so they exercise the gate their name/docstring claims, not
      the earlier-positioned efficacy-breadcrumb gate: `_seed_efficacy_breadcrumb(state_dir)`
      before the asserting `--run-end` call in both
      `test_p7_run_end_checkpoint_attended_no_auth_refuses` and
      `test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth`; strengthened each
      test's assertion to pin the specific gate (`"Stop-authorization gate" in out["refused"]`,
      plus the gate-specific echoed field/substring), so a future regression that re-masks these
      two behind an even-earlier gate fails loudly instead of silently passing for the wrong
      reason.

### Runtime Verification <!-- verification-only -->

- [x] `python -m pytest user/scripts/test_lazy_core.py -k "test_p7_run_end or test_marker_present" -q`
      → 8 passed (pre- and post-fix by count; POST-fix confirmed to pass for the RIGHT reason via
      manual reproduction of the two previously-masked tests' refusal text — see SPEC.md Runtime
      Evidence). <!-- verification-only -->
- [x] Full bare suite: `python -m pytest user/scripts/test_lazy_core.py -q` from the real
      checkout → 1125/1125 green post-fix. <!-- verification-only -->
- [x] Ambient-marker immunity (TARGETED — the scope of this fix): the 8 fixed tests re-run with
      the process-level `LAZY_STATE_DIR` pointed at a THROWAWAY dir deliberately seeded with a
      synthetic LIVE run marker + synthetic LIVE cycle-subagent marker → 8/8 green. Honest
      negative finding recorded: the FULL suite under that same marker-POLLUTED override shows
      75 failures (e.g. in-process `apply_pseudo` paths refused exit 3 by
      `refuse_if_cycle_active` reading the synthetic cycle marker) — PROVEN PRE-EXISTING by
      re-running two of the failing tests at the pre-fix revision (`git stash`) under identical
      pollution (same 2 failures, same refusal text). That configuration is OUTSIDE the
      documented contract (`_ORIGINAL_LAZY_STATE_DIR`'s live-cycle mitigation prescribes a CLEAN
      temp dir), is unchanged by this fix, and is left as-is — a candidate observation for a
      future hardening pass, not this bug's scope. <!-- verification-only -->
- [x] Zero-diff proof: a full recursive sha256+mtime snapshot of the REAL keyed state dir
      (`~/.claude/state/`) taken before the first run and after the last is byte-identical
      (no added/removed/changed file across the bare full suite, the polluted-override full
      suite, and all targeted runs) — the toolify-miner read-only discipline applied to the
      state dir. <!-- verification-only -->
- [x] `python user/scripts/lazy_parity_audit.py --repo-root .` → exit 0.
- [x] `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0.

### Implementation Notes

No production code changed. The trace (SPEC.md Evidence Collected) confirmed `claude_state_dir()`'s
`LAZY_STATE_DIR` override IS the correct, already-working isolation seam for every marker/ledger/
registry write these tests make; the only gap was that `--repo-root` (a pre-existing, always-available
explicit CLI flag) was never passed, so it silently defaulted to `os.getcwd()`. No new production seam
was needed — the fix is entirely at the fixture layer, mirroring the existing sibling
`telemetry-ledger-chokepoints` in-file smoke fixture's pattern (`lazy-state.py`'s own `--test` harness,
`fix_tl`/`_tl_env`), which already isolates BOTH `LAZY_STATE_DIR` and `--repo-root` per its own tempdir.
