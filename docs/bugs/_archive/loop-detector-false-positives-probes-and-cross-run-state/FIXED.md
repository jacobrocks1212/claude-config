---
kind: fixed
feature_id: loop-detector-false-positives-probes-and-cross-run-state
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest user/scripts/test_lazy_core.py (10 new fixtures, full suite 1040 passed); both state scripts' --test smoke harnesses
auto_ticked_rows: 0
---

# Completion Receipt

loop-detector-false-positives-probes-and-cross-run-state marked Fixed on 2026-07-12 by
operator-directed interactive close-out, implementing the SPEC's Fix Scope items 1-4 (Residual gaps
A and B; symptoms 1-3 were already fixed per the SPEC's own Root Cause characterization).

## Symptom Reproduction (red -> green)

- **Residual gap A** (meta-class consumption defeats the debounce): before the fix, a mid-step
  hardening/investigation/recovery dispatch's registry consume raised the F1/F2 oracle's count
  regardless of class, so the next same-step/same-tuple probe incremented the streak even though no
  forward attempt occurred. Fixed by filtering `consumed_emission_count` to `cls="cycle"` at the
  oracle's single call site in `update_repeat_counts`.
- **Residual gap B (streaks)** (cross-run leakage): before the fix, the OS-temp signature file was
  keyed only on `repo_root`, so a crashed run's last streak was silently inherited by the next
  run's first probe on the same `(feature_id, current_step)` tuple. Fixed by stamping/comparing the
  record's `run_started_at` against the live marker's identity.
- **Residual gap B (deny ledger)**: before the fix, `pending_hardening()` counted ALL unacked
  entries machine-wide, so a crashed run's undrained denial forced the NEXT run's `--run-end`/probe-
  withholding gates to dispatch a hardening round for a denial it never saw. Fixed by stamping
  entries with `run_started_at` and scoping the mandatory-debt reads to the live run, with a new
  `prior_run_pending_hardening()` informational surface for the leftover.

## Verification

```
python -m pytest user/scripts/test_lazy_core.py -q
-> 1040 passed (1030 baseline + 10 new fixtures)

LAZY_STATE_DIR=<isolated> python user/scripts/lazy-state.py --test  -> All smoke tests passed.
LAZY_STATE_DIR=<isolated> python user/scripts/bug-state.py --test   -> All smoke tests passed.
python3 user/scripts/lazy_parity_audit.py --repo-root .             -> exit 0
python user/scripts/doc-drift-lint.py --repo-root .                 -> exit 0
```

## Notes

D2 (prior-run debt disposition) resolved per the SPEC's recommendation: demote-to-informational —
prior-run deny-ledger entries remain in the file (never hard-cleared) and surface via the new
`prior_run_pending_hardening()` informational field, preserving the incident-mining record while no
longer blocking the current run.

D1 (oracle refinement vs signal generalization) resolved per the SPEC's preference: oracle
refinement (`consumed_emission_count(cls="cycle")`) rather than generalizing the one-shot marker
signal to every meta class — one localized change to the existing oracle read.

See PHASES.md for the full per-phase implementation notes, including one honest TDD note: an
initial stronger draft of the Residual-gap-B cross-run-reset condition was caught RED against two
pre-existing legacy-migration-tolerance fixtures and narrowed to the provable-mismatch-only form
that shipped.
